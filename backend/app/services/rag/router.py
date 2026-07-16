import json
import logging
import time
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth import SecurityContext
from app.core.exceptions import ResourceNotFoundException
from app.db.milvus import get_milvus_client
from app.db.postgresql import get_db
from app.middleware.auth import get_current_user
from app.models.models import KnowledgeItem, QaMessage, QaSession, RagIndexJob, RagQueryLog
from app.schemas.common import ApiResponse
from app.services.rag import rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["知识问答"])
rag_router = APIRouter(prefix="/rag", tags=["RAG检索"])


class AskRequest(BaseModel):
    session_id: Optional[str] = None
    question: str
    domain: Optional[str] = None

    model_config = {"populate_by_name": True}


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    helpful: bool
    comment: Optional[str] = None

    model_config = {"populate_by_name": True}


class RagSearchRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    top_k: Optional[int] = 10

    model_config = {"populate_by_name": True}


class RagIndexRequest(BaseModel):
    domain: str
    embedding_model: Optional[str] = "bge-m3"

    model_config = {"populate_by_name": True}


async def _hybrid_search(db: AsyncSession, query: str, domain: Optional[str], top_k: int, ctx: SecurityContext) -> tuple[list[dict], bool]:
    """向量检索 + 关键词检索的混合召回：向量库不可用/为空时仍能靠关键词兜底返回结果。
    结果会按调用者的密级与领域权限过滤，避免检索/问答绕过知识条目本身的访问控制。"""
    settings = get_settings()
    results: list[dict] = []
    used_real_embedding = True

    milvus_client = get_milvus_client()
    if milvus_client is not None:
        try:
            vector_hits, used_real_embedding = await rag_service.search(
                milvus_client, settings.MILVUS_COLLECTION, query, domain, top_k
            )
            results.extend(vector_hits)
        except Exception:
            logger.exception("向量检索失败，降级为纯关键词检索")

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
            "knowledgeId": item.id,
            "title": item.title,
            "snippet": (item.content_summary or "")[:300],
            "score": 0.5,
            "source": "keyword",
        })
        existing_ids.add(item.id)

    # 向量检索命中的部分还需要单独按访问权限过滤（关键词部分在 SQL 层已经过滤过，这里统一再过滤一遍即可，开销很小）
    results = await rag_service.filter_by_access(db, results, ctx)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k], used_real_embedding


async def _log_query(db: AsyncSession, query: str, domain: Optional[str], hit_count: int, latency_ms: int, used_real: bool) -> None:
    db.add(RagQueryLog(
        id=f"QL{uuid4().hex[:12]}", query=query, domain=domain, hit_count=hit_count,
        latency_ms=latency_ms, used_real_embedding=1 if used_real else 0,
    ))
    await db.commit()


def _confidence_hint(results: list[dict]) -> str:
    if not results:
        return "low"
    top_score = results[0]["score"]
    if top_score >= 0.8 and len(results) >= 3:
        return "high"
    if top_score >= 0.5:
        return "medium"
    return "low"


@router.post("/ask", response_model=ApiResponse)
async def ask(req: AskRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    started = time.monotonic()
    results, used_real = await _hybrid_search(db, req.question, req.domain, 5, ctx)
    latency_ms = int((time.monotonic() - started) * 1000)
    await _log_query(db, req.question, req.domain, len(results), latency_ms, used_real)

    answer, used_llm = await rag_service.generate_answer(req.question, results)

    session_id = req.session_id
    if session_id:
        session_result = await db.execute(select(QaSession).where(QaSession.id == session_id))
        session = session_result.scalar_one_or_none()
    else:
        session = None
    if session is None:
        session_id = f"QS{uuid4().hex[:10]}"
        session = QaSession(id=session_id, user_id=ctx.user_id, domain=req.domain, title=req.question[:50])
        db.add(session)

    citations = [{"knowledgeId": r["knowledgeId"], "title": r["title"], "snippetRef": r["snippet"][:80]} for r in results]

    db.add(QaMessage(
        id=f"QM{uuid4().hex[:10]}", session_id=session_id, role="user", content=req.question,
    ))
    assistant_message_id = f"QM{uuid4().hex[:10]}"
    db.add(QaMessage(
        id=assistant_message_id, session_id=session_id, role="assistant", content=answer,
        citations_json=json.dumps(citations, ensure_ascii=False),
        confidence_hint=_confidence_hint(results),
    ))
    await db.commit()

    return ApiResponse(data={
        "sessionId": session_id,
        "messageId": assistant_message_id,
        "answer": answer,
        "citations": citations,
        "confidenceHint": _confidence_hint(results),
        "disclaimer": "本回答为知识库辅助生成，涉及安全关键判断请以专家复核结论为准" + ("" if used_llm else "（当前为降级抽取式回答，未接入生成式大模型）"),
    })


@router.post("/ask-stream")
async def ask_stream(req: AskRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    from sse_starlette.sse import EventSourceResponse

    started = time.monotonic()
    results, used_real = await _hybrid_search(db, req.question, req.domain, 5, ctx)
    latency_ms = int((time.monotonic() - started) * 1000)
    await _log_query(db, req.question, req.domain, len(results), latency_ms, used_real)

    session_id = req.session_id
    if session_id:
        session_result = await db.execute(select(QaSession).where(QaSession.id == session_id))
        session = session_result.scalar_one_or_none()
    else:
        session = None
    if session is None:
        session_id = f"QS{uuid4().hex[:10]}"
        session = QaSession(id=session_id, user_id=ctx.user_id, domain=req.domain, title=req.question[:50])
        db.add(session)
    db.add(QaMessage(id=f"QM{uuid4().hex[:10]}", session_id=session_id, role="user", content=req.question))
    await db.commit()

    citations = [{"knowledgeId": r["knowledgeId"], "title": r["title"], "snippetRef": r["snippet"][:80]} for r in results]
    confidence_hint = _confidence_hint(results)
    assistant_message_id = f"QM{uuid4().hex[:10]}"

    async def event_generator():
        full_text = ""
        async for token in rag_service.generate_answer_stream(req.question, results):
            full_text += token
            yield {"event": "message", "data": json.dumps({"content": token, "done": False}, ensure_ascii=False)}
        yield {"event": "message", "data": json.dumps({
            "content": "", "citations": citations, "confidenceHint": confidence_hint,
            "sessionId": session_id, "messageId": assistant_message_id, "done": True,
        }, ensure_ascii=False)}

        try:
            from app.db.postgresql import async_session_factory
            async with async_session_factory() as save_session:
                save_session.add(QaMessage(
                    id=assistant_message_id, session_id=session_id, role="assistant", content=full_text,
                    citations_json=json.dumps(citations, ensure_ascii=False), confidence_hint=confidence_hint,
                ))
                await save_session.commit()
        except Exception:
            logger.exception("Failed to persist streamed QA answer for session %s", session_id)

    return EventSourceResponse(event_generator())


@router.post("/feedback", response_model=ApiResponse)
async def submit_feedback(req: FeedbackRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(QaMessage).where(QaMessage.id == req.message_id, QaMessage.session_id == req.session_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise ResourceNotFoundException("消息不存在")
    message.helpful = 1 if req.helpful else 0
    message.feedback_comment = req.comment
    await db.commit()
    return ApiResponse(message="反馈已提交")


@router.get("/sessions", response_model=ApiResponse)
async def list_sessions(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(
        select(QaSession).where(QaSession.user_id == ctx.user_id).order_by(QaSession.updated_at.desc()).limit(50)
    )
    sessions = [
        {"sessionId": s.id, "title": s.title, "domain": s.domain, "updatedAt": s.updated_at.isoformat()}
        for s in result.scalars().all()
    ]
    return ApiResponse(data=sessions)


@router.get("/sessions/{session_id}", response_model=ApiResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    session_result = await db.execute(select(QaSession).where(QaSession.id == session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise ResourceNotFoundException("会话不存在")
    msg_result = await db.execute(select(QaMessage).where(QaMessage.session_id == session_id).order_by(QaMessage.created_at.asc()))
    messages = [
        {
            "messageId": m.id, "role": m.role, "content": m.content,
            "citations": json.loads(m.citations_json) if m.citations_json else [],
            "confidenceHint": m.confidence_hint, "helpful": bool(m.helpful) if m.helpful is not None else None,
        }
        for m in msg_result.scalars().all()
    ]
    return ApiResponse(data={"sessionId": session_id, "messages": messages})


@rag_router.post("/search", response_model=ApiResponse)
async def rag_search(req: RagSearchRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    started = time.monotonic()
    results, used_real = await _hybrid_search(db, req.query, req.domain, req.top_k or 10, ctx)
    latency_ms = int((time.monotonic() - started) * 1000)
    await _log_query(db, req.query, req.domain, len(results), latency_ms, used_real)
    return ApiResponse(data=results)


async def _run_index_job(job_id: str, domain: Optional[str]) -> None:
    from app.db.postgresql import async_session_factory

    settings = get_settings()
    async with async_session_factory() as db:
        job_result = await db.execute(select(RagIndexJob).where(RagIndexJob.id == job_id))
        job = job_result.scalar_one_or_none()
        if job is None:
            return
        try:
            milvus_client = get_milvus_client()
            if milvus_client is None:
                raise RuntimeError("Milvus 客户端不可用")

            stmt = select(KnowledgeItem).where(KnowledgeItem.status == "published")
            if domain:
                stmt = stmt.where(KnowledgeItem.domain == domain)
            result = await db.execute(stmt)
            items = result.scalars().all()

            items_indexed = 0
            chunks_indexed = 0
            used_real_embedding = True
            for item in items:
                text = item.content_summary or item.title
                count = await rag_service.index_texts(
                    milvus_client, settings.MILVUS_COLLECTION, item.id, item.title, item.domain, text
                )
                if count > 0:
                    items_indexed += 1
                    chunks_indexed += count

            job.status = "completed"
            job.items_indexed = items_indexed
            job.chunks_indexed = chunks_indexed
            job.used_real_embedding = 1 if used_real_embedding else 0
            job.completed_at = datetime.now()
        except Exception as exc:
            logger.exception("RAG 索引任务 %s 失败", job_id)
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.now()
        await db.commit()


@rag_router.post("/index", response_model=ApiResponse)
async def create_rag_index(
    req: RagIndexRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    index_id = f"IDX{uuid4().hex[:8].upper()}"
    job = RagIndexJob(id=index_id, domain=req.domain, embedding_model=req.embedding_model or "bge-m3", status="building")
    db.add(job)
    await db.commit()
    background_tasks.add_task(_run_index_job, index_id, req.domain)
    return ApiResponse(data={"indexId": index_id, "status": "building"})


@rag_router.get("/index/{index_id}", response_model=ApiResponse)
async def get_index_status(index_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(RagIndexJob).where(RagIndexJob.id == index_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundException("索引任务不存在")
    return ApiResponse(data={
        "indexId": job.id, "domain": job.domain, "status": job.status,
        "itemsIndexed": job.items_indexed, "chunksIndexed": job.chunks_indexed,
        "usedRealEmbedding": bool(job.used_real_embedding), "errorMessage": job.error_message,
    })


@rag_router.get("/stats", response_model=ApiResponse)
async def get_rag_stats(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    settings = get_settings()
    total_chunks = 0
    milvus_client = get_milvus_client()
    if milvus_client is not None:
        try:
            stats = milvus_client.get_collection_stats(settings.MILVUS_COLLECTION)
            total_chunks = int(stats.get("row_count", 0))
        except Exception:
            logger.exception("Failed to fetch Milvus collection stats")

    avg_latency_result = await db.execute(select(func.avg(RagQueryLog.latency_ms)))
    avg_latency = avg_latency_result.scalar()

    total_queries_result = await db.execute(select(func.count()).select_from(RagQueryLog))
    total_queries = total_queries_result.scalar() or 0

    hit_queries_result = await db.execute(select(func.count()).select_from(RagQueryLog).where(RagQueryLog.hit_count > 0))
    hit_queries = hit_queries_result.scalar() or 0

    hit_rate = (hit_queries / total_queries) if total_queries else None

    return ApiResponse(data={
        "totalChunks": total_chunks,
        "avgLatencyMs": round(avg_latency, 1) if avg_latency is not None else None,
        "totalQueries": total_queries,
        "hitRate": round(hit_rate, 3) if hit_rate is not None else None,
    })


@rag_router.get("/eval", response_model=ApiResponse)
async def run_eval(
    queries: str = Query(..., description="以英文逗号分隔的评测查询列表"),
    domain: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    """基于真实检索链路的轻量评测：由于没有人工标注的相关性判定集，
    这里只能诚实地计算延迟、命中率一类指标，不伪造 Recall/MRR 等需要标注数据的指标。"""
    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    rows = []
    for q in query_list:
        started = time.monotonic()
        results, used_real = await _hybrid_search(db, q, domain, 10, ctx)
        latency_ms = int((time.monotonic() - started) * 1000)
        await _log_query(db, q, domain, len(results), latency_ms, used_real)
        rows.append({
            "query": q, "hitCount": len(results), "latencyMs": latency_ms,
            "usedRealEmbedding": used_real, "topScore": results[0]["score"] if results else 0.0,
        })

    hit_rate = sum(1 for r in rows if r["hitCount"] > 0) / len(rows) if rows else 0.0
    avg_latency = sum(r["latencyMs"] for r in rows) / len(rows) if rows else 0.0

    return ApiResponse(data={
        "queries": rows,
        "summary": {"hitRate": round(hit_rate, 3), "avgLatencyMs": round(avg_latency, 1), "queryCount": len(rows)},
    })
