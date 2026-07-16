import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import SecurityContext
from app.core.exceptions import BusinessException, ResourceNotFoundException
from app.db.minio import get_minio_client
from app.db.postgresql import get_db
from app.middleware.auth import get_current_user
from app.models.models import (
    ExtractionItem,
    ExtractionTask,
    KnowledgeCandidate,
    KnowledgeItem,
    KnowledgeVersionHistory,
)
from app.schemas.common import ApiResponse
from app.services.extraction import document_parser, extraction_service
from app.services.ontology.router import DEFAULT_CLASSES, DEFAULT_RELATIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/extraction", tags=["知识抽取"])


class ExtractionTaskRequest(BaseModel):
    candidate_id: Optional[str] = None
    domain: Optional[str] = None
    # 兼容旧前端仍会发送该字段，但后端不再信任它——实际写入 submitter_id/owner_id
    # 的值一律取自鉴权后的 ctx.user_id，避免任意登录用户伪造抽取任务的发起人。
    submitter_id: str = ""

    model_config = {"populate_by_name": True}


class ExtractionReviewActionRequest(BaseModel):
    item_id: str
    action: str
    # 同上：不再信任客户端传入的 reviewer_id，审核人一律取自鉴权后的 ctx.user_id。
    reviewer_id: str = ""
    comment: Optional[str] = None

    model_config = {"populate_by_name": True}


def _read_document_bytes(object_name: str) -> bytes:
    """同步阻塞地从 MinIO 读取文档字节内容，供 run_in_threadpool 调用。"""
    minio_client = get_minio_client()
    if minio_client is None:
        raise RuntimeError("对象存储服务不可用，无法读取文档内容")
    response = minio_client.get_object("phm-documents", object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def _get_candidate_text(candidate: KnowledgeCandidate) -> str:
    if candidate.source_type == "document":
        # MinIO 读取与后续的 PDF/DOCX 文本解析都是同步阻塞操作，放进线程池执行，
        # 避免在处理大文档时卡住事件循环、拖慢同一进程内其他并发请求。
        content = await run_in_threadpool(_read_document_bytes, candidate.raw_content)
        return await run_in_threadpool(
            document_parser.extract_text, content, candidate.source_name or candidate.raw_content
        )

    # expert_input 等来源：raw_content 是 JSON 字符串
    try:
        data = json.loads(candidate.raw_content) if candidate.raw_content else {}
        if isinstance(data, dict):
            return data.get("text") or json.dumps(data, ensure_ascii=False)
        return str(data)
    except (json.JSONDecodeError, TypeError):
        return candidate.raw_content or ""


async def _run_extraction_task(task_id: str, candidate_id: Optional[str], domain: Optional[str], submitter_id: str) -> None:
    from app.db.postgresql import async_session_factory

    async with async_session_factory() as db:
        task_result = await db.execute(select(ExtractionTask).where(ExtractionTask.id == task_id))
        task = task_result.scalar_one_or_none()
        if task is None:
            return
        try:
            candidate = None
            text = ""
            resolved_domain = domain

            if candidate_id:
                cand_result = await db.execute(select(KnowledgeCandidate).where(KnowledgeCandidate.id == candidate_id))
                candidate = cand_result.scalar_one_or_none()
                if candidate is None:
                    raise ValueError("候选对象不存在")
                text = await _get_candidate_text(candidate)
                resolved_domain = domain or candidate.domain

            if not resolved_domain:
                raise ValueError("必须提供 domain 或 candidate_id")
            if not text.strip():
                raise ValueError("未能获取到可供抽取的文本内容（可能是扫描件、空文档或不支持的格式）")

            extraction_result, used_llm = await extraction_service.run_extraction(
                text, resolved_domain, DEFAULT_CLASSES, DEFAULT_RELATIONS
            )

            for entity in extraction_result["entities"]:
                db.add(ExtractionItem(
                    id=f"EI{uuid4().hex[:10]}", task_id=task_id, candidate_id=candidate_id, domain=resolved_domain,
                    kind="entity", payload_json=json.dumps(entity, ensure_ascii=False),
                    confidence=entity["confidence"], status="pending",
                ))
            for relation in extraction_result["relations"]:
                db.add(ExtractionItem(
                    id=f"EI{uuid4().hex[:10]}", task_id=task_id, candidate_id=candidate_id, domain=resolved_domain,
                    kind="relation", payload_json=json.dumps(relation, ensure_ascii=False),
                    confidence=relation["confidence"], status="pending",
                ))

            summary = extraction_service.summarize_extraction(extraction_result)
            title = (candidate.source_name if candidate else None) or f"{resolved_domain} 知识草稿 {task_id}"
            knowledge_id = f"KI{uuid4().hex[:8].upper()}"
            db.add(KnowledgeItem(
                id=knowledge_id, domain=resolved_domain, type="case", title=title, content_summary=summary,
                classification_level=candidate.classification_level if candidate else "internal",
                status="draft", version=1, owner_id=submitter_id, source_candidate_id=candidate_id,
            ))
            db.add(KnowledgeVersionHistory(
                id=f"KV{uuid4().hex[:10]}", knowledge_id=knowledge_id, version=1,
                content_snapshot=summary, change_type="create", operator_id=submitter_id,
            ))

            if candidate is not None:
                candidate.status = "processed"

            task.status = "completed"
            task.used_real_llm = 1 if used_llm else 0
            task.entities_extracted = len(extraction_result["entities"])
            task.relations_extracted = len(extraction_result["relations"])
            task.knowledge_item_id = knowledge_id
            task.completed_at = datetime.now()
            await db.flush()

            try:
                from app.services.governance.conflict_service import detect_conflicts_for
                new_item_result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id))
                new_item = new_item_result.scalar_one()
                await detect_conflicts_for(db, new_item)
            except Exception:
                logger.exception("Conflict detection failed for extracted knowledge %s", knowledge_id)
        except Exception as exc:
            logger.exception("抽取任务 %s 失败", task_id)
            task.status = "failed"
            task.error_message = str(exc)
            task.completed_at = datetime.now()
            if candidate_id:
                cand_result = await db.execute(select(KnowledgeCandidate).where(KnowledgeCandidate.id == candidate_id))
                candidate = cand_result.scalar_one_or_none()
                if candidate is not None:
                    candidate.status = "failed"
        await db.commit()


@router.get("/tasks", response_model=ApiResponse)
async def list_extraction_tasks(
    domain: str = Query(None),
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(ExtractionTask).order_by(ExtractionTask.created_at.desc()).limit(50)
    if domain:
        stmt = stmt.where(ExtractionTask.domain == domain)
    if status:
        stmt = stmt.where(ExtractionTask.status == status)
    result = await db.execute(stmt)
    tasks = [
        {
            "taskId": t.id, "candidateId": t.candidate_id, "domain": t.domain, "status": t.status,
            "usedRealLlm": bool(t.used_real_llm), "entitiesExtracted": t.entities_extracted,
            "relationsExtracted": t.relations_extracted, "knowledgeItemId": t.knowledge_item_id,
            "errorMessage": t.error_message, "createdAt": t.created_at.isoformat(),
        }
        for t in result.scalars().all()
    ]
    return ApiResponse(data=tasks)


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_extraction_task(task_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(ExtractionTask).where(ExtractionTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundException("抽取任务不存在")
    return ApiResponse(data={
        "taskId": task.id, "candidateId": task.candidate_id, "domain": task.domain, "status": task.status,
        "usedRealLlm": bool(task.used_real_llm), "entitiesExtracted": task.entities_extracted,
        "relationsExtracted": task.relations_extracted, "knowledgeItemId": task.knowledge_item_id,
        "errorMessage": task.error_message,
    })


@router.post("/task", response_model=ApiResponse)
async def create_extraction_task(
    req: ExtractionTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    if not req.candidate_id and not req.domain:
        raise BusinessException(code=40001, message="必须提供 candidate_id 或 domain 之一")

    task_id = f"EXT{uuid4().hex[:8].upper()}"
    task = ExtractionTask(
        id=task_id, candidate_id=req.candidate_id, domain=req.domain,
        submitter_id=ctx.user_id, status="processing",
    )
    db.add(task)
    await db.commit()

    background_tasks.add_task(_run_extraction_task, task_id, req.candidate_id, req.domain, ctx.user_id)
    return ApiResponse(data={"taskId": task_id, "status": "processing"})


@router.post("/tasks/{candidate_id}/trigger", response_model=ApiResponse)
async def trigger_extraction(
    candidate_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    task_id = f"EXT{uuid4().hex[:8].upper()}"
    task = ExtractionTask(id=task_id, candidate_id=candidate_id, submitter_id=ctx.user_id, status="processing")
    db.add(task)
    await db.commit()

    background_tasks.add_task(_run_extraction_task, task_id, candidate_id, None, ctx.user_id)
    return ApiResponse(data={"candidateId": candidate_id, "taskId": task_id, "status": "processing"})


@router.get("/review-queue", response_model=ApiResponse)
async def get_review_queue(
    domain: str = Query(None),
    kind: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(ExtractionItem).where(ExtractionItem.status == "pending").order_by(ExtractionItem.created_at.desc()).limit(100)
    if domain:
        stmt = stmt.where(ExtractionItem.domain == domain)
    if kind:
        stmt = stmt.where(ExtractionItem.kind == kind)
    result = await db.execute(stmt)
    items = []
    for item in result.scalars().all():
        payload = json.loads(item.payload_json)
        items.append({
            "itemId": item.id, "taskId": item.task_id, "candidateId": item.candidate_id,
            "domain": item.domain, "kind": item.kind, "payload": payload,
            "confidence": float(item.confidence), "hasConflict": bool(item.has_conflict),
            "createdAt": item.created_at.isoformat(),
        })
    return ApiResponse(data=items)


@router.post("/review/action", response_model=ApiResponse)
async def review_action(
    req: ExtractionReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    if req.action not in ("approved", "rejected"):
        raise BusinessException(code=40001, message="action 必须是 approved 或 rejected")

    result = await db.execute(select(ExtractionItem).where(ExtractionItem.id == req.item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise ResourceNotFoundException("抽取候选项不存在")
    if item.status != "pending":
        raise BusinessException(code=40001, message="该候选项已被处理，不能重复审核")

    item.status = req.action
    item.reviewer_id = ctx.user_id
    item.reviewed_at = datetime.now()
    await db.commit()

    materialized = False
    if req.action == "approved":
        payload = json.loads(item.payload_json)
        try:
            from app.db.neo4j import driver as neo4j_driver
            from app.config import get_settings
            from app.services.ontology import graph_service
            if neo4j_driver is not None:
                settings = get_settings()
                async with neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
                    if item.kind == "entity":
                        await graph_service.upsert_entity(
                            session, payload["id"], payload["name"], payload["type"], payload.get("domain"),
                        )
                        materialized = True
                    else:
                        # 关系两端的实体若尚未入图（例如仅审核了关系、未审核实体），先补建最小节点
                        for node_id, node_name in ((payload["source_id"], payload["source_name"]), (payload["target_id"], payload["target_name"])):
                            await graph_service.upsert_entity(session, node_id, node_name, "Equipment", item.domain)
                        materialized = await graph_service.create_relation(
                            session, payload["source_id"], payload["target_id"], payload["relation"]
                        )
        except Exception:
            logger.exception("将抽取候选项 %s 物化进图谱失败", req.item_id)

    return ApiResponse(data={"itemId": req.item_id, "status": req.action, "materializedToGraph": materialized})


@router.get("/stats", response_model=ApiResponse)
async def get_extraction_stats(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    entities_today_result = await db.execute(
        select(func.count()).select_from(ExtractionItem)
        .where(ExtractionItem.kind == "entity", ExtractionItem.created_at >= today_start)
    )
    entities_today = entities_today_result.scalar() or 0

    relations_today_result = await db.execute(
        select(func.count()).select_from(ExtractionItem)
        .where(ExtractionItem.kind == "relation", ExtractionItem.created_at >= today_start)
    )
    relations_today = relations_today_result.scalar() or 0

    avg_confidence_result = await db.execute(select(func.avg(ExtractionItem.confidence)))
    avg_confidence = avg_confidence_result.scalar()

    total_result = await db.execute(select(func.count()).select_from(ExtractionItem))
    total = total_result.scalar() or 0
    pending_result = await db.execute(select(func.count()).select_from(ExtractionItem).where(ExtractionItem.status == "pending"))
    pending = pending_result.scalar() or 0
    pending_ratio = (pending / total) if total else None

    return ApiResponse(data={
        "entitiesToday": entities_today,
        "relationsToday": relations_today,
        "avgConfidence": round(float(avg_confidence), 3) if avg_confidence is not None else None,
        "pendingReviewRatio": round(pending_ratio, 3) if pending_ratio is not None else None,
    })
