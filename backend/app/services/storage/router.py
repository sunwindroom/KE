from typing import Optional
from uuid import uuid4
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.postgresql import get_db
from app.core.auth import SecurityContext
from app.core.exceptions import ResourceNotFoundException, PermissionDeniedException
from app.middleware.auth import get_current_user
from app.models.models import KnowledgeItem, KnowledgeVersionHistory
from app.schemas.common import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/knowledge", tags=["知识检索"])

_LEVEL_ORDER = {"public": 0, "internal": 1, "confidential": 2, "secret": 3}


def _allowed_levels(ctx: SecurityContext) -> list[str]:
    ceiling = _LEVEL_ORDER.get(ctx.max_classification_level, 0)
    return [level for level, order in _LEVEL_ORDER.items() if order <= ceiling]


class SemanticSearchRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    top_k: int = 10


class KnowledgeCreateRequest(BaseModel):
    domain: str
    type: str
    title: str
    content_summary: Optional[str] = None
    content_ref: Optional[str] = None
    classification_level: str = "internal"
    confidence: Optional[float] = None


class KnowledgeUpdateRequest(BaseModel):
    title: Optional[str] = None
    content_summary: Optional[str] = None
    content_ref: Optional[str] = None
    classification_level: Optional[str] = None
    confidence: Optional[float] = None


@router.post("", response_model=ApiResponse)
async def create_knowledge(
    req: KnowledgeCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    if not ctx.has_domain(req.domain):
        raise PermissionDeniedException(f"无权在领域「{req.domain}」下创建知识")
    if not ctx.can_access_classification(req.classification_level):
        raise PermissionDeniedException(f"你的密级权限不足以创建「{req.classification_level}」级知识")

    knowledge_id = f"KI{uuid4().hex[:8].upper()}"
    item = KnowledgeItem(
        id=knowledge_id, domain=req.domain, type=req.type, title=req.title,
        content_summary=req.content_summary, content_ref=req.content_ref,
        classification_level=req.classification_level, confidence=req.confidence,
        status="draft", version=1, owner_id=ctx.user_id,
    )
    db.add(item)
    db.add(KnowledgeVersionHistory(
        id=f"KV{uuid4().hex[:10]}", knowledge_id=knowledge_id, version=1,
        content_snapshot=req.content_summary, change_type="create", operator_id=ctx.user_id,
    ))
    await db.commit()

    try:
        from app.services.governance.conflict_service import detect_conflicts_for
        await detect_conflicts_for(db, item)
        await db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Conflict detection failed for knowledge %s", knowledge_id)

    return ApiResponse(data={"knowledgeId": knowledge_id, "status": "draft", "version": 1})


@router.put("/{knowledge_id}", response_model=ApiResponse)
async def update_knowledge(
    knowledge_id: str,
    req: KnowledgeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise ResourceNotFoundException("知识条目不存在")
    if item.owner_id != ctx.user_id and not ctx.has_role("admin", "expert", "manager"):
        raise PermissionDeniedException("只有责任人或专家/管理员可以编辑该知识条目")
    if req.classification_level is not None and not ctx.can_access_classification(req.classification_level):
        raise PermissionDeniedException(f"你的密级权限不足以设置为「{req.classification_level}」级")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.version += 1
    db.add(KnowledgeVersionHistory(
        id=f"KV{uuid4().hex[:10]}", knowledge_id=knowledge_id, version=item.version,
        content_snapshot=item.content_summary, change_type="update", operator_id=ctx.user_id,
    ))
    await db.commit()
    return ApiResponse(data={"knowledgeId": knowledge_id, "status": item.status, "version": item.version})


@router.delete("/{knowledge_id}", response_model=ApiResponse)
async def deprecate_knowledge(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise ResourceNotFoundException("知识条目不存在")
    if item.owner_id != ctx.user_id and not ctx.has_role("admin", "expert", "manager"):
        raise PermissionDeniedException("只有责任人或专家/管理员可以废弃该知识条目")
    item.status = "deprecated"
    db.add(KnowledgeVersionHistory(
        id=f"KV{uuid4().hex[:10]}", knowledge_id=knowledge_id, version=item.version,
        content_snapshot=None, change_type="deprecate", operator_id=ctx.user_id,
    ))
    await db.commit()

    try:
        from app.db.neo4j import driver as neo4j_driver
        from app.config import get_settings
        from app.services.ontology import graph_service
        if neo4j_driver is not None:
            settings = get_settings()
            async with neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
                await graph_service.remove_knowledge_node(session, knowledge_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to remove knowledge node %s from graph", knowledge_id)

    try:
        from app.db.milvus import get_milvus_client
        from app.config import get_settings as _get_settings
        from app.services.rag import rag_service
        milvus_client = get_milvus_client()
        if milvus_client is not None:
            await rag_service.remove_index(milvus_client, _get_settings().MILVUS_COLLECTION, knowledge_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to remove vector index for knowledge %s", knowledge_id)

    return ApiResponse(data={"knowledgeId": knowledge_id, "status": "deprecated"})


@router.get("/search", response_model=ApiResponse[PaginatedResponse])
async def search_knowledge(
    keyword: str = Query(None),
    domain: str = Query(None),
    type: str = Query(None),
    equipment_model: str = Query(None),
    time_range: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    query = select(KnowledgeItem).where(KnowledgeItem.status == "published")
    query = query.where(KnowledgeItem.classification_level.in_(_allowed_levels(ctx)))
    if "general" not in ctx.domain_scope:
        query = query.where(KnowledgeItem.domain.in_(ctx.domain_scope))
    if keyword:
        query = query.where(KnowledgeItem.title.ilike(f"%{keyword}%"))
    if domain:
        query = query.where(KnowledgeItem.domain == domain)
    if type:
        query = query.where(KnowledgeItem.type == type)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [
        {
            "knowledgeId": item.id,
            "title": item.title,
            "domain": item.domain,
            "type": item.type,
            "confidence": float(item.confidence) if item.confidence else None,
            "classificationLevel": item.classification_level,
            "summary": item.content_summary,
        }
        for item in result.scalars().all()
    ]
    return ApiResponse(data=PaginatedResponse(page=page, page_size=page_size, total=total, items=items))


@router.post("/semantic-search", response_model=ApiResponse)
async def semantic_search(req: SemanticSearchRequest, ctx: SecurityContext = Depends(get_current_user)):
    return ApiResponse(data={"items": [], "total": 0})


@router.get("/{knowledge_id}/similar", response_model=ApiResponse)
async def get_similar(knowledge_id: str, ctx: SecurityContext = Depends(get_current_user)):
    return ApiResponse(data=[])


@router.get("/rules", response_model=ApiResponse)
async def get_rules(failure_mode: str = Query(None), domain: str = Query(None), ctx: SecurityContext = Depends(get_current_user)):
    return ApiResponse(data=[])


@router.get("/{knowledge_id}", response_model=ApiResponse)
async def get_knowledge_detail(knowledge_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id))
    item = result.scalar_one_or_none()
    if item is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("知识条目不存在")
    if not ctx.can_access_classification(item.classification_level):
        raise PermissionDeniedException("你的密级权限不足以查看该知识条目")
    if not ctx.has_domain(item.domain):
        raise PermissionDeniedException("你无权访问该领域的知识")
    return ApiResponse(data={
        "knowledgeId": item.id, "title": item.title, "domain": item.domain,
        "type": item.type, "summary": item.content_summary, "confidence": float(item.confidence) if item.confidence else None,
        "classificationLevel": item.classification_level, "status": item.status, "version": item.version,
    })


@router.get("/{knowledge_id}/versions", response_model=ApiResponse)
async def get_knowledge_versions(knowledge_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(
        select(KnowledgeVersionHistory).where(KnowledgeVersionHistory.knowledge_id == knowledge_id).order_by(KnowledgeVersionHistory.version.desc())
    )
    versions = [{"versionId": v.id, "version": v.version, "changeType": v.change_type, "operatorId": v.operator_id, "operatedAt": str(v.operated_at)} for v in result.scalars().all()]
    return ApiResponse(data=versions)