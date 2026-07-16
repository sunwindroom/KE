import io
import json
import logging
import uuid
from datetime import datetime

import aio_pika
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.postgresql import get_db
from app.db.rabbitmq import get_rabbitmq_channel
from app.db.minio import get_minio_client
from app.config import get_settings
from app.core.auth import SecurityContext
from app.core.exceptions import BusinessException, PermissionDeniedException, ServiceUnavailableException
from app.middleware.auth import get_current_user
from app.models.models import KnowledgeCandidate
from app.schemas.ingestion import ExpertInputRequest, DbSyncTriggerRequest, CandidateResponse, IngestionStatusResponse
from app.schemas.common import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/ingestion", tags=["数据接入"])
logger = logging.getLogger(__name__)


async def _publish_candidate(candidate_id: str) -> None:
    """将候选对象推送到抽取队列；MQ 不可用时记录日志但不阻断主流程。"""
    settings = get_settings()
    try:
        channel = get_rabbitmq_channel()
        if channel is None:
            logger.warning("RabbitMQ channel unavailable, candidate %s not queued", candidate_id)
            return
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps({"candidate_id": candidate_id}).encode()),
            routing_key=settings.RABBITMQ_INGESTION_QUEUE,
        )
    except Exception:
        logger.exception("Failed to publish candidate %s to ingestion queue", candidate_id)


@router.post("/document", response_model=ApiResponse[CandidateResponse])
async def upload_document(
    domain: str = Form(...),
    classification_level: str = Form("internal"),
    project_id: str = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    if not ctx.has_domain(domain):
        raise PermissionDeniedException(f"无权在领域「{domain}」下提交知识")
    if not ctx.can_access_classification(classification_level):
        raise PermissionDeniedException(f"你的密级权限不足以提交「{classification_level}」级内容")

    settings = get_settings()
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.UPLOAD_ALLOWED_EXTENSIONS:
        raise BusinessException(40001, f"不支持的文件格式: {ext}")

    content = await file.read()
    if len(content) > settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        raise BusinessException(40001, f"文件大小超过限制: {settings.UPLOAD_MAX_SIZE_MB}MB")
    if len(content) == 0:
        raise BusinessException(40001, "文件内容为空，请重新选择文件")

    minio_client = get_minio_client()
    if minio_client is None:
        raise ServiceUnavailableException("对象存储服务当前不可用，请稍后重试")

    object_name = f"{domain}/{uuid.uuid4().hex}/{file.filename}"
    try:
        # minio-py 的 put_object 要求 data 是一个具备 read() 方法的流对象（如 io.BytesIO），
        # 而不是裸的 bytes —— 之前这里直接传入 content（bytes），minio-py 内部会执行
        # getattr(data, "read")，bytes 没有该属性，导致每一次文档上传都会必现
        # AttributeError，请求以 500 失败（这正是"上传文档"功能此前必现"上传失败"的根因之一）。
        # 该调用也是同步阻塞 I/O，放进 run_in_threadpool 执行，避免卡住事件循环
        # 影响同一进程内其他并发请求的响应。
        await run_in_threadpool(
            minio_client.put_object,
            "phm-documents",
            object_name,
            io.BytesIO(content),
            len(content),
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        logger.exception("上传文档到对象存储失败: object_name=%s", object_name)
        raise ServiceUnavailableException("文档存储失败，请稍后重试") from None

    candidate_id = f"KC{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
    candidate = KnowledgeCandidate(
        id=candidate_id,
        source_type="document",
        domain=domain,
        raw_content=object_name,
        source_name=file.filename,
        project_id=project_id,
        classification_level=classification_level,
        submitter_id=ctx.user_id,
    )
    db.add(candidate)
    await db.commit()

    await _publish_candidate(candidate_id)
    return ApiResponse(data=CandidateResponse(candidateId=candidate_id, status="pending"))


@router.post("/expert-input", response_model=ApiResponse[CandidateResponse])
async def expert_input(
    req: ExpertInputRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    if not ctx.has_domain(req.domain):
        raise PermissionDeniedException(f"无权在领域「{req.domain}」下提交知识")
    if not ctx.can_access_classification(req.classification_level):
        raise PermissionDeniedException(f"你的密级权限不足以提交「{req.classification_level}」级内容")

    candidate_id = f"KC{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
    candidate = KnowledgeCandidate(
        id=candidate_id,
        source_type="expert_input",
        domain=req.domain,
        raw_content=json.dumps(req.content, ensure_ascii=False),
        source_name=req.title,
        classification_level=req.classification_level,
        # submitter_id 不再信任客户端传入值（旧实现允许任意已登录用户在请求体里
        # 填写别人的用户名，导致知识条目的"提交人"可被伪造），改为一律取自鉴权后
        # 的 SecurityContext，从令牌里解析出来的用户身份无法被请求体覆盖。
        submitter_id=ctx.user_id,
    )
    db.add(candidate)
    await db.commit()

    await _publish_candidate(candidate_id)
    return ApiResponse(data=CandidateResponse(candidateId=candidate_id, status="pending"))


@router.post("/db-sync/trigger", response_model=ApiResponse[CandidateResponse])
async def trigger_db_sync(
    req: DbSyncTriggerRequest,
    ctx: SecurityContext = Depends(get_current_user),
):
    candidate_id = f"KC{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
    return ApiResponse(data=CandidateResponse(candidateId=candidate_id, status="pending"))


@router.get("/status/{candidate_id}", response_model=ApiResponse[IngestionStatusResponse])
async def get_ingestion_status(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeCandidate).where(KnowledgeCandidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if candidate is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("候选对象不存在")

    from app.models.models import KnowledgeItem
    ki_result = await db.execute(select(KnowledgeItem.id).where(KnowledgeItem.source_candidate_id == candidate_id))
    extracted_ids = [row[0] for row in ki_result.all()]

    return ApiResponse(
        data=IngestionStatusResponse(candidateId=candidate.id, status=candidate.status, extractedKnowledgeIds=extracted_ids)
    )


@router.get("/candidates", response_model=ApiResponse[PaginatedResponse])
async def list_candidates(
    domain: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    query = select(KnowledgeCandidate).order_by(KnowledgeCandidate.created_at.desc())
    if domain:
        query = query.where(KnowledgeCandidate.domain == domain)
    if status:
        query = query.where(KnowledgeCandidate.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [
        {
            "candidateId": c.id, "sourceType": c.source_type, "domain": c.domain,
            "sourceName": c.source_name, "status": c.status,
            "classificationLevel": c.classification_level, "createdAt": c.created_at.isoformat(),
        }
        for c in result.scalars().all()
    ]
    return ApiResponse(data=PaginatedResponse(page=page, page_size=page_size, total=total, items=items))


@router.get("/stats", response_model=ApiResponse)
async def get_ingestion_stats(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    today_count_result = await db.execute(
        select(func.count()).select_from(KnowledgeCandidate).where(KnowledgeCandidate.created_at >= today_start)
    )
    today_count = today_count_result.scalar() or 0

    total_count_result = await db.execute(select(func.count()).select_from(KnowledgeCandidate))
    total_count = total_count_result.scalar() or 0

    failed_count_result = await db.execute(
        select(func.count()).select_from(KnowledgeCandidate).where(KnowledgeCandidate.status == "failed")
    )
    failed_count = failed_count_result.scalar() or 0

    success_rate = ((total_count - failed_count) / total_count) if total_count else None

    return ApiResponse(data={
        "todayCandidates": today_count,
        "successRate": round(success_rate, 3) if success_rate is not None else None,
        "dlqCount": failed_count,
        "totalCandidates": total_count,
    })


@router.get("/dlq", response_model=ApiResponse[PaginatedResponse])
async def get_dlq(
    domain: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    query = select(KnowledgeCandidate).where(KnowledgeCandidate.status == "failed")
    if domain:
        query = query.where(KnowledgeCandidate.domain == domain)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [{"candidateId": c.id, "domain": c.domain, "status": c.status} for c in result.scalars().all()]
    return ApiResponse(data=PaginatedResponse(page=page, page_size=page_size, total=len(items), items=items))