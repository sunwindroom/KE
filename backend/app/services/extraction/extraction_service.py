"""知识抽取服务层。

从候选知识（上传文档的文本内容 / 专家录入内容）中抽取结构化实体与关系，
产出结构与 app.services.ontology.graph_service 的本体建模（Entity 节点 + 关系类型）
完全对齐，抽取结果经人工复核通过后可直接物化进 Neo4j 图谱（见 extraction/router.py）。

同样遵循"没有真实 LLM 时优雅降级"的原则：
- 有 LLM：用提示词约束模型只能输出 JSON，且实体类型/关系类型必须来自给定的本体 schema，
  并要求模型给出置信度自评分。
- 无 LLM（或调用失败）：退化为基于规则的正则抽取器，识别"A导致B""A属于B"等中文
  PHM 领域常见表述模式，置信度固定给一个偏低的数值（明确反映规则抽取不如模型抽取可靠）。
  规则抽取器抽的是文本里真实出现的短语，不是编造的示例数据。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.core.llm_client import llm_client

logger = logging.getLogger(__name__)

# 中文关系触发词 -> 本体关系类型；用于规则抽取降级方案
RELATION_PATTERNS: list[tuple[str, str]] = [
    (r"(.{2,20}?)\s*(?:导致|引发|引起)\s*(.{2,20}?)(?:[。，,\n]|$)", "LEADS_TO"),
    (r"(.{2,20}?)\s*(?:属于|隶属于)\s*(.{2,20}?)(?:[。，,\n]|$)", "BELONGS_TO"),
    (r"(.{2,20}?)\s*(?:表现为|症状是|征兆是)\s*(.{2,20}?)(?:[。，,\n]|$)", "MANIFESTS_AS"),
    (r"(.{2,20}?)\s*(?:可通过|采用|通过)\s*(.{2,20}?)\s*(?:检测|诊断)(?:[。，,\n]|$)", "DETECTED_BY"),
    (r"(.{2,20}?)\s*(?:处置措施为|可通过更换|需要更换|维修方法是)\s*(.{2,20}?)(?:[。，,\n]|$)", "RESOLVED_BY"),
]

TYPE_KEYWORD_HINTS: list[tuple[str, str]] = [
    ("故障", "FailureMode"), ("失效", "FailureMode"), ("裂纹", "FailureMode"), ("磨损", "FailureMode"),
    ("征兆", "Symptom"), ("异常", "Symptom"), ("振动", "Symptom"), ("预警", "Symptom"),
    ("维修", "MaintenanceStrategy"), ("更换", "MaintenanceStrategy"), ("处置", "MaintenanceStrategy"),
    ("检测", "DiagnosisMethod"), ("诊断", "DiagnosisMethod"), ("监测", "DiagnosisMethod"),
    ("寿命", "RULModel"), ("预测", "RULModel"),
    ("轴承", "Component"), ("泵", "Component"), ("阀", "Component"), ("叶片", "Component"), ("转子", "Component"),
]


def _guess_entity_type(name: str) -> str:
    for keyword, entity_type in TYPE_KEYWORD_HINTS:
        if keyword in name:
            return entity_type
    return "Equipment"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name.strip())
    return slug[:40] or "entity"


def extract_with_rules(text: str, domain: str) -> dict:
    """基于正则的降级抽取器，抽取文本中真实出现的关系短语，不编造内容。"""
    text = (text or "")[:5000]
    entities: dict[str, dict] = {}
    relations: list[dict] = []

    def register_entity(name: str) -> str:
        name = name.strip(" \t、，,。.")
        entity_id = _slugify(name)
        if entity_id not in entities:
            entities[entity_id] = {
                "id": entity_id, "name": name, "type": _guess_entity_type(name), "domain": domain,
            }
        return entity_id

    for pattern, relation_type in RELATION_PATTERNS:
        for match in re.finditer(pattern, text):
            subject_raw, object_raw = match.group(1), match.group(2)
            if not subject_raw or not object_raw:
                continue
            subject_id = register_entity(subject_raw)
            object_id = register_entity(object_raw)
            if subject_id == object_id:
                continue
            relations.append({
                "source_id": subject_id, "source_name": entities[subject_id]["name"],
                "target_id": object_id, "target_name": entities[object_id]["name"],
                "relation": relation_type,
                "confidence": 0.55,
            })

    entity_list = [{**e, "confidence": 0.6} for e in entities.values()]
    return {"entities": entity_list, "relations": relations}


def _build_llm_prompt(text: str, domain: str, classes: list[dict], relations: list[dict]) -> list[dict]:
    class_names = ", ".join(c["className"] for c in classes)
    relation_defs = "\n".join(f'- {r["name"]}: {r["domain"]} -> {r["range"]}' for r in relations)
    system = (
        "你是一名 PHM（故障预测与健康管理）领域的知识抽取引擎。"
        "只能从给定文本中抽取真实出现的信息，禁止编造文本中没有的实体或关系。"
        "只允许输出合法 JSON，不要包含任何解释性文字或 Markdown 代码块标记。"
        f"实体类型必须是以下之一：{class_names}。\n"
        f"关系类型及其允许的方向：\n{relation_defs}\n"
        'JSON 格式为：{"entities":[{"id":"英文短id","name":"中文名称","type":"类型",'
        '"confidence":0到1的数字}],"relations":[{"source_id":"...","target_id":"...",'
        '"relation":"关系类型","confidence":0到1的数字}]}。'
        "confidence 表示你对该条抽取结果的把握程度，请如实评估，不要都给 1.0。"
    )
    user = f"领域：{domain}\n\n文本内容：\n{text[:4000]}\n\n请抽取实体与关系，只输出 JSON。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_llm_json(raw: str) -> Optional[dict]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or "entities" not in data or "relations" not in data:
        return None
    return data


def _clamp_confidence(value, default=0.7) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


async def extract_with_llm(text: str, domain: str, classes: list[dict], relations: list[dict]) -> Optional[dict]:
    messages = _build_llm_prompt(text, domain, classes, relations)
    raw = await llm_client.chat(messages, temperature=0.1, max_tokens=1500)
    data = _parse_llm_json(raw)
    if data is None:
        logger.warning("LLM 抽取输出无法解析为合法 JSON，回退到规则抽取")
        return None

    valid_types = {c["className"] for c in classes}
    valid_relations = {r["name"] for r in relations}

    entities = []
    for e in data.get("entities", []):
        if not isinstance(e, dict) or not e.get("name"):
            continue
        entities.append({
            "id": e.get("id") or _slugify(e["name"]),
            "name": e["name"],
            "type": e.get("type") if e.get("type") in valid_types else "Equipment",
            "domain": domain,
            "confidence": _clamp_confidence(e.get("confidence")),
        })

    entity_ids = {e["id"] for e in entities}
    parsed_relations = []
    for r in data.get("relations", []):
        if not isinstance(r, dict):
            continue
        if r.get("relation") not in valid_relations:
            continue
        source_id, target_id = r.get("source_id"), r.get("target_id")
        if source_id not in entity_ids or target_id not in entity_ids:
            continue
        source_name = next((e["name"] for e in entities if e["id"] == source_id), source_id)
        target_name = next((e["name"] for e in entities if e["id"] == target_id), target_id)
        parsed_relations.append({
            "source_id": source_id, "source_name": source_name,
            "target_id": target_id, "target_name": target_name,
            "relation": r["relation"],
            "confidence": _clamp_confidence(r.get("confidence")),
        })

    return {"entities": entities, "relations": parsed_relations}


async def run_extraction(text: str, domain: str, classes: list[dict], relations: list[dict]) -> tuple[dict, bool]:
    """返回 (抽取结果, 是否使用了真实 LLM)。"""
    try:
        result = await extract_with_llm(text, domain, classes, relations)
        if result is not None:
            return result, True
    except Exception as exc:
        logger.warning("LLM 抽取服务不可用，降级为规则抽取: %s", exc)
    return extract_with_rules(text, domain), False


def summarize_extraction(result: dict) -> str:
    """生成人类可读的抽取结果摘要，作为草稿知识条目的 content_summary。"""
    lines = []
    for e in result.get("entities", [])[:10]:
        lines.append(f"实体：{e['name']}（{e['type']}）")
    for r in result.get("relations", [])[:10]:
        lines.append(f"关系：{r['source_name']} --[{r['relation']}]--> {r['target_name']}")
    return "\n".join(lines) if lines else "未抽取到结构化实体或关系，请人工补充。"
