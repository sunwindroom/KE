"""RAG（检索增强生成）服务层。

设计说明：
- 本项目部署环境可能暂时没有接入真实的 Embedding / LLM 服务（见 app.core.llm_client）。
  为了让检索链路（分块 → 向量化 → 入库 → 检索 → 生成）在没有真实模型时也能被
  完整跑通、便于联调和测试，这里提供了确定性的"降级"实现：
    - Embedding 不可用时，使用基于哈希的确定性伪向量（哈希词袋 + L2 归一化），
      不是随机数——同样的文本恒定产出同样的向量，词汇重叠越多向量越接近，
      因此仍能反映基础的词汇相似度，只是语义理解能力远不如真实的 bge-m3。
    - LLM 不可用时，使用抽取式摘要（直接拼接最相关的检索片段）代替生成式回答，
      不会编造内容。
  一旦在 .env 中配置了真实的 LLM_ENDPOINT / EMBEDDING_ENDPOINT，会自动优先使用
  真实模型；真实调用失败（连接失败/超时）才会回退到上述降级实现，并记录警告日志，
  方便定位"为什么现在用的是降级模式"。
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Optional

from app.config import get_settings
from app.core.llm_client import llm_client, embedding_client

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 128


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按字符数做滑动窗口分块（中文场景下按字符比按词更稳定）。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks


def _hash_embedding(text: str, dimension: int) -> list[float]:
    """确定性的哈希词袋伪向量，仅在没有真实 Embedding 服务时作为降级方案。"""
    vector = [0.0] * dimension
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    if not tokens:
        tokens = [text.lower()] if text else ["_empty_"]
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


async def filter_by_access(db, results: list[dict], ctx) -> list[dict]:
    """按用户的密级上限与领域范围过滤检索结果。ctx 需要提供
    can_access_classification(level) 和 has_domain(domain) 方法（即 SecurityContext）。"""
    if not results:
        return results

    from sqlalchemy import select
    from app.models.models import KnowledgeItem

    knowledge_ids = list({r["knowledgeId"] for r in results if r.get("knowledgeId")})
    if not knowledge_ids:
        return results

    rows = await db.execute(
        select(KnowledgeItem.id, KnowledgeItem.classification_level, KnowledgeItem.domain)
        .where(KnowledgeItem.id.in_(knowledge_ids))
    )
    access_map = {row[0]: (row[1], row[2]) for row in rows.all()}

    filtered = []
    for r in results:
        info = access_map.get(r.get("knowledgeId"))
        if info is None:
            # 找不到对应的知识条目元数据时，出于安全考虑默认不返回，而不是放行
            continue
        level, domain = info
        if not ctx.can_access_classification(level):
            continue
        if not ctx.has_domain(domain):
            continue
        filtered.append(r)
    return filtered


async def embed_texts(texts: list[str]) -> tuple[list[list[float]], bool]:
    """返回 (向量列表, 是否使用了真实模型)。真实服务不可用时自动降级为哈希伪向量。"""
    settings = get_settings()
    if not texts:
        return [], True
    try:
        vectors = await embedding_client.embed(texts)
        return vectors, True
    except Exception as exc:
        logger.warning("Embedding 服务不可用，降级为哈希伪向量: %s", exc)
        return [_hash_embedding(t, settings.EMBEDDING_DIMENSION) for t in texts], False


async def generate_answer(question: str, contexts: list[dict]) -> tuple[str, bool]:
    """返回 (回答文本, 是否使用了真实 LLM)。LLM 不可用时降级为抽取式摘要。"""
    if not contexts:
        return "知识库暂无充分依据回答此问题，请补充关键词后重试，或联系领域专家人工确认。", True

    context_block = "\n\n".join(
        f"[片段{i + 1}] (来自《{c['title']}》)\n{c['snippet']}" for i, c in enumerate(contexts)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名 PHM（故障预测与健康管理）领域知识助手。"
                "只能依据给定的检索片段回答问题，不要编造片段中没有的信息；"
                "如果片段不足以回答，请明确说明证据不足。回答末尾不需要再重复引用列表。"
            ),
        },
        {"role": "user", "content": f"问题：{question}\n\n检索到的知识片段：\n{context_block}\n\n请给出简明、有依据的回答。"},
    ]
    try:
        answer = await llm_client.chat(messages, temperature=0.3, max_tokens=800)
        return answer.strip(), True
    except Exception as exc:
        logger.warning("LLM 服务不可用，降级为抽取式摘要回答: %s", exc)
        # 抽取式降级：直接呈现最相关的片段，不编造总结性表述
        bullets = "\n".join(f"- 《{c['title']}》：{c['snippet'][:200]}" for c in contexts[:3])
        fallback = (
            f"（当前未接入生成式大模型，以下为知识库中与「{question}」最相关的原始片段，"
            f"请人工判读）\n{bullets}"
        )
        return fallback, False


async def generate_answer_stream(question: str, contexts: list[dict]):
    """流式回答：真实 LLM 可用时逐 token 转发；否则把降级回答整体作为一次性分片输出。"""
    if not contexts:
        yield "知识库暂无充分依据回答此问题，请补充关键词后重试，或联系领域专家人工确认。"
        return

    context_block = "\n\n".join(
        f"[片段{i + 1}] (来自《{c['title']}》)\n{c['snippet']}" for i, c in enumerate(contexts)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名 PHM（故障预测与健康管理）领域知识助手。"
                "只能依据给定的检索片段回答问题，不要编造片段中没有的信息；"
                "如果片段不足以回答，请明确说明证据不足。"
            ),
        },
        {"role": "user", "content": f"问题：{question}\n\n检索到的知识片段：\n{context_block}\n\n请给出简明、有依据的回答。"},
    ]
    try:
        got_any = False
        async for token in llm_client.chat_stream(messages, temperature=0.3, max_tokens=800):
            got_any = True
            yield token
        if not got_any:
            raise RuntimeError("empty stream")
    except Exception as exc:
        logger.warning("LLM 流式服务不可用，降级为抽取式摘要: %s", exc)
        bullets = "\n".join(f"- 《{c['title']}》：{c['snippet'][:200]}" for c in contexts[:3])
        fallback = (
            f"（当前未接入生成式大模型，以下为知识库中与「{question}」最相关的原始片段，"
            f"请人工判读）\n{bullets}"
        )
        # 模拟合理的分片输出，而不是一次性甩出全部文本
        for i in range(0, len(fallback), 20):
            yield fallback[i : i + 20]


async def index_texts(
    milvus_client,
    collection_name: str,
    knowledge_id: str,
    title: str,
    domain: str,
    text: str,
) -> int:
    """把一条知识的正文切块、向量化后写入 Milvus，返回写入的分块数。"""
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors, _ = await embed_texts(chunks)
    data = [
        {
            "vector": vec,
            "knowledge_id": knowledge_id,
            "title": title,
            "domain": domain,
            "chunk_index": i,
            "chunk_text": chunk,
        }
        for i, (vec, chunk) in enumerate(zip(vectors, chunks))
    ]
    milvus_client.delete(collection_name, filter=f'knowledge_id == "{knowledge_id}"')
    milvus_client.insert(collection_name, data=data)
    return len(data)


async def remove_index(milvus_client, collection_name: str, knowledge_id: str) -> None:
    milvus_client.delete(collection_name, filter=f'knowledge_id == "{knowledge_id}"')


async def search(
    milvus_client,
    collection_name: str,
    query: str,
    domain: Optional[str],
    top_k: int = 10,
) -> tuple[list[dict], bool]:
    """向量检索，返回 (结果列表, 是否使用了真实 embedding)。"""
    vectors, used_real = await embed_texts([query])
    if not vectors:
        return [], used_real
    filter_expr = f'domain == "{domain}"' if domain else ""
    raw = milvus_client.search(
        collection_name,
        data=[vectors[0]],
        filter=filter_expr,
        limit=top_k,
        output_fields=["knowledge_id", "title", "domain", "chunk_text"],
    )
    hits = raw[0] if raw else []
    results = []
    seen_knowledge_ids = set()
    for hit in hits:
        entity = hit.get("entity", hit)
        knowledge_id = entity.get("knowledge_id")
        if knowledge_id in seen_knowledge_ids:
            continue
        seen_knowledge_ids.add(knowledge_id)
        results.append({
            "knowledgeId": knowledge_id,
            "title": entity.get("title", ""),
            "snippet": (entity.get("chunk_text") or "")[:300],
            "score": float(hit.get("distance", 0.0)),
            "source": "vector",
        })
    return results, used_real
