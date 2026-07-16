"""Agent 编排服务：把 RAG 检索、图谱推理、大模型生成组合成有真实执行轨迹的任务流程。

每个 Agent 类型的公共约定：
- 返回 (trace, final_result, needs_confirmation)。
- trace 是一个 [{step, action, output}] 列表，记录每一步真实调用了什么、拿到了什么，
  用于在前端"执行轨迹"里展示，而不是伪造的固定文案。
- 涉及安全关键判断（故障诊断结论、维修策略建议、寿命预测方法）的 Agent 都要求人工确认
  （needs_confirmation=True），只有信息性的知识审校任务可以自动完成。
- 没有真实 LLM/Embedding/Neo4j 服务时会走已有服务层（rag_service/graph_service/
  llm_client）的降级路径，这里不重复实现降级逻辑，只负责编排。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.config import get_settings
from app.core.llm_client import llm_client
from app.db.milvus import get_milvus_client
from app.db.neo4j import driver as neo4j_driver
from app.services.ontology import graph_service
from app.services.rag import rag_service

logger = logging.getLogger(__name__)


async def _rag_context(db, query: str, domain: Optional[str], ctx, top_k: int = 5) -> tuple[list[dict], bool]:
    """复用 RAG 的混合检索（向量 + 关键词），不依赖某个具体路由。"""
    settings = get_settings()
    results: list[dict] = []
    used_real = True

    milvus_client = get_milvus_client()
    if milvus_client is not None:
        try:
            vector_hits, used_real = await rag_service.search(milvus_client, settings.MILVUS_COLLECTION, query, domain, top_k)
            results.extend(vector_hits)
        except Exception:
            logger.exception("Agent 编排中的向量检索失败，仅使用关键词兜底")

    from sqlalchemy import select
    from app.models.models import KnowledgeItem

    existing_ids = {r["knowledgeId"] for r in results}
    allowed_levels = [lvl for lvl in ("public", "internal", "confidential", "secret") if ctx.can_access_classification(lvl)]
    stmt = select(KnowledgeItem).where(KnowledgeItem.status == "published")
    stmt = stmt.where(KnowledgeItem.classification_level.in_(allowed_levels))
    if "general" not in ctx.domain_scope:
        stmt = stmt.where(KnowledgeItem.domain.in_(ctx.domain_scope))
    if domain:
        stmt = stmt.where(KnowledgeItem.domain == domain)
    stmt = stmt.where(
        KnowledgeItem.title.ilike(f"%{query}%") | KnowledgeItem.content_summary.ilike(f"%{query}%")
    ).limit(top_k)
    kw_result = await db.execute(stmt)
    for item in kw_result.scalars().all():
        if item.id in existing_ids:
            continue
        results.append({
            "knowledgeId": item.id, "title": item.title,
            "snippet": (item.content_summary or "")[:300], "score": 0.5, "source": "keyword",
        })
        existing_ids.add(item.id)

    results = await rag_service.filter_by_access(db, results, ctx)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k], used_real


async def _graph_context(query: str, domain: Optional[str]) -> Optional[dict]:
    """尝试把查询解析到图谱中的一个实体，返回其关系上下文；图数据库不可用/未命中时返回 None。"""
    if neo4j_driver is None:
        return None
    settings = get_settings()
    try:
        async with neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
            entity_id = await graph_service.resolve_entity_id(session, query, domain)
            if entity_id is None:
                return None
            return await graph_service.get_entity_detail(session, entity_id)
    except Exception:
        logger.exception("Agent 编排中的图谱查询失败")
        return None


def _format_context_for_llm(rag_results: list[dict], graph_entity: Optional[dict]) -> str:
    parts = []
    if graph_entity:
        rel_lines = "\n".join(f"  - {r['relation']} → {r['target']} ({r['targetType']})" for r in graph_entity.get("relations", [])[:10])
        parts.append(f"图谱实体《{graph_entity['name']}》({graph_entity['type']}) 的关联关系：\n{rel_lines}")
    for i, r in enumerate(rag_results):
        parts.append(f"[知识{i + 1}]《{r['title']}》：{r['snippet']}")
    return "\n\n".join(parts) if parts else "（未检索到相关知识或图谱证据）"


async def run_fault_diagnosis(db, query: str, domain: Optional[str], ctx) -> tuple[list[dict], str, bool]:
    trace = []

    rag_results, used_real_embedding = await _rag_context(db, query, domain, ctx)
    trace.append({
        "step": 1, "action": "RAG检索相关知识",
        "output": f"检索到 {len(rag_results)} 条相关知识" + ("" if used_real_embedding else "（降级为哈希伪向量+关键词）"),
    })

    graph_entity = await _graph_context(query, domain)
    if graph_entity:
        trace.append({
            "step": 2, "action": "图谱推理",
            "output": f"定位到实体《{graph_entity['name']}》，发现 {len(graph_entity.get('relations', []))} 条关联关系",
        })
    else:
        trace.append({"step": 2, "action": "图谱推理", "output": "未能在图谱中定位到匹配实体，跳过图谱推理"})

    context = _format_context_for_llm(rag_results, graph_entity)
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名 PHM 故障诊断助手，请依据给定的知识与图谱证据分析可能的故障原因和处置建议。"
                "不要编造证据中没有的信息；证据不足时要明确说明，并建议人工进一步排查。"
            ),
        },
        {"role": "user", "content": f"故障现象/问题描述：{query}\n\n检索到的证据：\n{context}\n\n请给出诊断分析和处置建议。"},
    ]
    try:
        conclusion = (await llm_client.chat(messages, temperature=0.3, max_tokens=800)).strip()
        trace.append({"step": 3, "action": "生成诊断结论", "output": "已基于检索证据生成诊断结论"})
    except Exception as exc:
        logger.warning("Agent 故障诊断降级为抽取式摘要: %s", exc)
        if rag_results:
            bullets = "\n".join(f"- 《{r['title']}》：{r['snippet'][:200]}" for r in rag_results[:3])
            conclusion = f"（未接入生成式大模型，以下为最相关的知识片段，请专家结合图谱关系人工判读）\n{bullets}"
        else:
            conclusion = "未检索到足够证据支持自动诊断，建议人工排查或补充故障现象描述后重试。"
        trace.append({"step": 3, "action": "生成诊断结论", "output": "LLM 不可用，降级为证据摘要"})

    return trace, conclusion, True


async def run_rul_prediction(db, query: str, domain: Optional[str], ctx) -> tuple[list[dict], str, bool]:
    trace = []

    graph_entity = await _graph_context(query, domain)
    applicable_models = []
    if graph_entity:
        applicable_models = [r["target"] for r in graph_entity.get("relations", []) if r["relation"] == "APPLIES_MODEL"]
        trace.append({
            "step": 1, "action": "图谱查询适用寿命预测模型",
            "output": (
                f"定位到实体《{graph_entity['name']}》，找到 {len(applicable_models)} 个关联的寿命预测模型"
                if applicable_models else f"定位到实体《{graph_entity['name']}》，暂无关联的寿命预测模型记录"
            ),
        })
    else:
        trace.append({"step": 1, "action": "图谱查询适用寿命预测模型", "output": "未能在图谱中定位到匹配部件/装备实体"})

    rag_results, used_real_embedding = await _rag_context(db, query, domain, ctx)
    trace.append({
        "step": 2, "action": "RAG检索寿命预测方法知识",
        "output": f"检索到 {len(rag_results)} 条相关方法论知识" + ("" if used_real_embedding else "（降级为哈希伪向量+关键词）"),
    })

    context = _format_context_for_llm(rag_results, graph_entity)
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名 PHM 寿命预测助手。你没有接入实时传感器数据和已标定的预测模型，"
                "因此不能给出具体的剩余寿命数值，只能依据检索到的知识说明适用的预测方法、"
                "所需输入数据和大致流程建议，并明确指出需要连接实时监测数据与标定模型才能给出数值结论。"
            ),
        },
        {"role": "user", "content": f"预测需求：{query}\n\n检索到的证据：\n{context}\n\n请说明推荐的寿命预测方法与所需数据。"},
    ]
    try:
        conclusion = (await llm_client.chat(messages, temperature=0.3, max_tokens=800)).strip()
        trace.append({"step": 3, "action": "生成方法建议", "output": "已生成寿命预测方法建议"})
    except Exception as exc:
        logger.warning("Agent 寿命预测降级为抽取式摘要: %s", exc)
        if rag_results:
            bullets = "\n".join(f"- 《{r['title']}》：{r['snippet'][:200]}" for r in rag_results[:3])
            conclusion = f"（未接入生成式大模型，以下为最相关的方法论知识片段，请专家人工判读）\n{bullets}"
        else:
            conclusion = "未检索到足够的方法论知识，且暂无实时监测数据接入，无法给出寿命预测建议。"
        trace.append({"step": 3, "action": "生成方法建议", "output": "LLM 不可用，降级为证据摘要"})

    conclusion += "\n\n（注：本结论不构成具体剩余寿命数值，数值预测需接入实时传感器数据与已标定的预测模型。）"
    return trace, conclusion, True


async def run_maintenance_strategy(db, query: str, domain: Optional[str], ctx) -> tuple[list[dict], str, bool]:
    trace = []

    graph_entity = await _graph_context(query, domain)
    strategies = []
    if graph_entity:
        strategies = [r["target"] for r in graph_entity.get("relations", []) if r["relation"] == "RESOLVED_BY"]
        trace.append({
            "step": 1, "action": "图谱查询关联维修策略",
            "output": (
                f"定位到实体《{graph_entity['name']}》，找到 {len(strategies)} 条关联维修策略"
                if strategies else f"定位到实体《{graph_entity['name']}》，暂无关联维修策略记录"
            ),
        })
    else:
        trace.append({"step": 1, "action": "图谱查询关联维修策略", "output": "未能在图谱中定位到匹配的故障模式/部件实体"})

    rag_results, used_real_embedding = await _rag_context(db, query, domain, ctx)
    trace.append({
        "step": 2, "action": "RAG检索维修规程知识",
        "output": f"检索到 {len(rag_results)} 条相关维修规程知识" + ("" if used_real_embedding else "（降级为哈希伪向量+关键词）"),
    })

    context = _format_context_for_llm(rag_results, graph_entity)
    messages = [
        {
            "role": "system",
            "content": "你是一名 PHM 维修策略助手，请依据给定证据推荐维修策略与步骤，不要编造证据中没有的信息。",
        },
        {"role": "user", "content": f"维修需求：{query}\n\n检索到的证据：\n{context}\n\n请给出维修策略建议。"},
    ]
    try:
        conclusion = (await llm_client.chat(messages, temperature=0.3, max_tokens=800)).strip()
        trace.append({"step": 3, "action": "生成维修策略建议", "output": "已生成维修策略建议"})
    except Exception as exc:
        logger.warning("Agent 维修策略降级为抽取式摘要: %s", exc)
        if rag_results:
            bullets = "\n".join(f"- 《{r['title']}》：{r['snippet'][:200]}" for r in rag_results[:3])
            conclusion = f"（未接入生成式大模型，以下为最相关的维修规程片段，请专家人工判读）\n{bullets}"
        else:
            conclusion = "未检索到足够证据支持维修策略推荐，建议人工制定方案。"
        trace.append({"step": 3, "action": "生成维修策略建议", "output": "LLM 不可用，降级为证据摘要"})

    return trace, conclusion, True


async def run_knowledge_review(db, query: str, domain: Optional[str], ctx=None) -> tuple[list[dict], str, bool]:
    """知识审校 Agent：复用治理模块的真实质量检查逻辑，纯信息性任务，无需人工确认。"""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models.models import KnowledgeItem

    trace = []
    issues = []

    stmt = select(KnowledgeItem).where(
        KnowledgeItem.status.in_(("draft", "pending", "published")),
        (KnowledgeItem.content_summary.is_(None)) | (KnowledgeItem.content_summary == ""),
    )
    if domain:
        stmt = stmt.where(KnowledgeItem.domain == domain)
    result = await db.execute(stmt.limit(20))
    missing_summary = result.scalars().all()
    for item in missing_summary:
        issues.append(f"《{item.title}》（{item.id}）缺少内容摘要")
    trace.append({"step": 1, "action": "检查缺失摘要的知识条目", "output": f"发现 {len(missing_summary)} 条缺少摘要"})

    cutoff = datetime.now() - timedelta(days=7)
    stale_stmt = select(KnowledgeItem).where(KnowledgeItem.status == "pending", KnowledgeItem.created_at < cutoff)
    if domain:
        stale_stmt = stale_stmt.where(KnowledgeItem.domain == domain)
    stale_result = await db.execute(stale_stmt.limit(20))
    stale_items = stale_result.scalars().all()
    for item in stale_items:
        issues.append(f"《{item.title}》（{item.id}）已停留待审核超过 7 天")
    trace.append({"step": 2, "action": "检查长期未审核条目", "output": f"发现 {len(stale_items)} 条长期未审核"})

    if issues:
        conclusion = f"共发现 {len(issues)} 个知识质量问题：\n" + "\n".join(f"- {i}" for i in issues)
    else:
        conclusion = "未发现知识质量问题。"
    trace.append({"step": 3, "action": "汇总审校结果", "output": f"共 {len(issues)} 个问题"})

    return trace, conclusion, False


AGENT_RUNNERS = {
    "fault_diagnosis": run_fault_diagnosis,
    "rul_prediction": run_rul_prediction,
    "maintenance_strategy": run_maintenance_strategy,
    "knowledge_review": run_knowledge_review,
}
