from typing import Optional
from uuid import uuid4
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.postgresql import get_db
from app.core.auth import SecurityContext
from app.core.exceptions import PermissionDeniedException
from app.middleware.auth import get_current_user, require_role
from app.models.models import ReviewWorkflow, KnowledgeItem, KnowledgeVersionHistory, KnowledgeConflict, KnowledgeSnapshot, AuditLog
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/governance", tags=["知识治理"])

REVIEWER_ROLES = ("expert", "admin", "manager")


class ReviewActionRequest(BaseModel):
    reviewer_id: str
    action: str
    comment: Optional[str] = None


class ConflictResolveRequest(BaseModel):
    resolver_id: str
    resolution: str
    comment: Optional[str] = None


@router.post("/review/{knowledge_id}/submit", response_model=ApiResponse)
async def submit_review(knowledge_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    from datetime import datetime
    result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id))
    item = result.scalar_one_or_none()
    if item is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("知识条目不存在，无法提交审核")

    workflow = ReviewWorkflow(
        id=f"RW{uuid4().hex[:8]}",
        knowledge_id=knowledge_id,
        review_type="initial",
        current_stage="pending",
        reviewer_id=ctx.user_id,
        submitted_at=datetime.now(),
    )
    item.status = "pending"
    db.add(workflow)
    await db.commit()
    return ApiResponse(data={"workflowId": workflow.id, "status": "pending"})


@router.post("/review/{knowledge_id}/action", response_model=ApiResponse)
async def review_action(knowledge_id: str, req: ReviewActionRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role(*REVIEWER_ROLES))):
    from datetime import datetime

    result = await db.execute(
        select(ReviewWorkflow).where(ReviewWorkflow.knowledge_id == knowledge_id).order_by(ReviewWorkflow.submitted_at.desc())
    )
    workflow = result.scalars().first()
    if workflow is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("审核流程不存在")

    item_result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("知识条目不存在")

    if req.reviewer_id != ctx.user_id:
        raise PermissionDeniedException("reviewer_id 必须是当前登录用户本人")
    if item.owner_id and item.owner_id == ctx.user_id:
        raise PermissionDeniedException("不能审核自己提交的知识条目，请由其他专家复核")

    if req.action not in ("approved", "rejected", "escalated"):
        from app.core.exceptions import BusinessException
        raise BusinessException(code=40001, message="action 必须是 approved / rejected / escalated 之一")

    workflow.review_result = req.action
    workflow.review_comment = req.comment
    workflow.reviewer_id = req.reviewer_id
    workflow.reviewed_at = datetime.now()
    workflow.current_stage = "completed" if req.action != "escalated" else "escalated"

    if req.action == "approved":
        item.status = "published"
        db.add(KnowledgeVersionHistory(
            id=f"KV{uuid4().hex[:10]}", knowledge_id=knowledge_id, version=item.version,
            content_snapshot=item.content_summary, change_type="update", operator_id=req.reviewer_id,
        ))
    elif req.action == "rejected":
        item.status = "draft"

    db.add(AuditLog(
        id=f"AL{uuid4().hex[:12]}", user_id=req.reviewer_id, action=f"review_{req.action}",
        resource_type="knowledge_item", resource_id=knowledge_id, detail=req.comment or "",
    ))
    await db.commit()

    if req.action == "approved":
        try:
            from app.db.neo4j import driver as neo4j_driver
            from app.config import get_settings
            from app.services.ontology import graph_service
            if neo4j_driver is not None:
                settings = get_settings()
                async with neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
                    await graph_service.upsert_knowledge_node(
                        session, knowledge_id, item.title, item.domain, item.type,
                        item.classification_level, item.status,
                    )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to sync knowledge node %s to graph", knowledge_id)

        try:
            from app.db.milvus import get_milvus_client
            from app.config import get_settings as _get_settings
            from app.services.rag import rag_service
            milvus_client = get_milvus_client()
            if milvus_client is not None:
                await rag_service.index_texts(
                    milvus_client, _get_settings().MILVUS_COLLECTION, knowledge_id, item.title,
                    item.domain, item.content_summary or item.title,
                )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to index knowledge %s into RAG vector store", knowledge_id)

    return ApiResponse(data={"knowledgeId": knowledge_id, "result": req.action, "knowledgeStatus": item.status})


@router.get("/review-queue", response_model=ApiResponse)
async def get_knowledge_review_queue(
    domain: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(KnowledgeItem).where(KnowledgeItem.status == "pending").order_by(KnowledgeItem.created_at.desc()).limit(100)
    if domain:
        stmt = stmt.where(KnowledgeItem.domain == domain)
    result = await db.execute(stmt)
    items = [
        {
            "knowledgeId": k.id, "title": k.title, "domain": k.domain, "type": k.type,
            "classificationLevel": k.classification_level, "ownerId": k.owner_id,
            "createdAt": k.created_at.isoformat(),
        }
        for k in result.scalars().all()
    ]
    return ApiResponse(data=items)


@router.get("/conflicts", response_model=ApiResponse)
async def list_conflicts(
    status: str = Query("pending"),
    domain: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(KnowledgeConflict).order_by(KnowledgeConflict.created_at.desc()).limit(100)
    if status:
        stmt = stmt.where(KnowledgeConflict.status == status)
    if domain:
        stmt = stmt.where(KnowledgeConflict.domain == domain)
    result = await db.execute(stmt)
    conflicts = result.scalars().all()
    if not conflicts:
        return ApiResponse(data=[])

    knowledge_ids = {c.knowledge_id_a for c in conflicts} | {c.knowledge_id_b for c in conflicts}
    titles_result = await db.execute(select(KnowledgeItem.id, KnowledgeItem.title).where(KnowledgeItem.id.in_(knowledge_ids)))
    title_map = {row[0]: row[1] for row in titles_result.all()}

    return ApiResponse(data=[
        {
            "conflictId": c.id, "domain": c.domain, "conflictType": c.conflict_type,
            "knowledgeIdA": c.knowledge_id_a, "titleA": title_map.get(c.knowledge_id_a, c.knowledge_id_a),
            "knowledgeIdB": c.knowledge_id_b, "titleB": title_map.get(c.knowledge_id_b, c.knowledge_id_b),
            "description": c.description, "similarity": float(c.similarity) if c.similarity is not None else None,
            "status": c.status, "createdAt": c.created_at.isoformat(),
        }
        for c in conflicts
    ])


@router.post("/conflict/{conflict_id}/resolve", response_model=ApiResponse)
async def resolve_conflict(
    conflict_id: str, req: ConflictResolveRequest,
    db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role(*REVIEWER_ROLES)),
):
    from datetime import datetime

    if req.resolver_id != ctx.user_id:
        raise PermissionDeniedException("resolver_id 必须是当前登录用户本人")

    result = await db.execute(select(KnowledgeConflict).where(KnowledgeConflict.id == conflict_id))
    conflict = result.scalar_one_or_none()
    if conflict is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("冲突记录不存在")
    if conflict.status != "pending":
        from app.core.exceptions import BusinessException
        raise BusinessException(code=40001, message="该冲突已被处理")
    if req.resolution not in ("accept_a", "accept_b", "merge", "escalate"):
        from app.core.exceptions import BusinessException
        raise BusinessException(code=40001, message="resolution 必须是 accept_a / accept_b / merge / escalate 之一")

    conflict.status = "resolved"
    conflict.resolver_id = req.resolver_id
    conflict.resolution = req.resolution
    conflict.resolution_comment = req.comment
    conflict.resolved_at = datetime.now()

    loser_id = None
    if req.resolution == "accept_a":
        loser_id = conflict.knowledge_id_b
    elif req.resolution == "accept_b":
        loser_id = conflict.knowledge_id_a

    if loser_id:
        loser_result = await db.execute(select(KnowledgeItem).where(KnowledgeItem.id == loser_id))
        loser = loser_result.scalar_one_or_none()
        if loser is not None and loser.status != "deprecated":
            loser.status = "deprecated"
            db.add(KnowledgeVersionHistory(
                id=f"KV{uuid4().hex[:10]}", knowledge_id=loser_id, version=loser.version,
                content_snapshot=None, change_type="deprecate", operator_id=req.resolver_id,
            ))

    db.add(AuditLog(
        id=f"AL{uuid4().hex[:12]}", user_id=req.resolver_id, action="conflict_resolve",
        resource_type="knowledge_conflict", resource_id=conflict_id, detail=f"{req.resolution}: {req.comment or ''}",
    ))
    await db.commit()

    if loser_id:
        try:
            from app.db.neo4j import driver as neo4j_driver
            from app.config import get_settings
            from app.services.ontology import graph_service
            if neo4j_driver is not None:
                settings = get_settings()
                async with neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
                    await graph_service.remove_knowledge_node(session, loser_id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to remove deprecated knowledge %s from graph", loser_id)

    return ApiResponse(data={"conflictId": conflict_id, "resolution": req.resolution, "deprecatedKnowledgeId": loser_id})


@router.get("/quality-check", response_model=ApiResponse)
async def get_quality_check(status: str = Query("pending_review"), db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    """真实的知识质量检查：标记缺少摘要内容、长期停留在待审核状态的条目，而不是虚构问题列表。"""
    from datetime import datetime, timedelta

    issues = []
    no_summary_result = await db.execute(
        select(KnowledgeItem).where(
            KnowledgeItem.status.in_(("draft", "pending", "published")),
            (KnowledgeItem.content_summary.is_(None)) | (KnowledgeItem.content_summary == ""),
        ).limit(50)
    )
    for item in no_summary_result.scalars().all():
        issues.append({
            "knowledgeId": item.id, "title": item.title, "issueType": "missing_summary",
            "description": "缺少内容摘要，建议补充后再发布。",
        })

    stale_cutoff = datetime.now() - timedelta(days=7)
    stale_result = await db.execute(
        select(KnowledgeItem).where(KnowledgeItem.status == "pending", KnowledgeItem.created_at < stale_cutoff).limit(50)
    )
    for item in stale_result.scalars().all():
        issues.append({
            "knowledgeId": item.id, "title": item.title, "issueType": "stale_pending",
            "description": f"已停留在待审核状态超过 7 天（提交于 {item.created_at.date()}），建议尽快复核。",
        })

    return ApiResponse(data=issues)


@router.get("/stats/overview", response_model=ApiResponse)
async def get_stats_overview(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    from datetime import datetime, timedelta

    total = await db.execute(select(func.count()).select_from(KnowledgeItem).where(KnowledgeItem.status == "published"))
    total_count = total.scalar() or 0
    by_domain = await db.execute(
        select(KnowledgeItem.domain, func.count()).where(KnowledgeItem.status == "published").group_by(KnowledgeItem.domain)
    )
    domain_dist = {row[0]: row[1] for row in by_domain.all()}

    cutoff = datetime.now() - timedelta(days=30)
    growth_result = await db.execute(
        select(func.count()).select_from(KnowledgeItem).where(KnowledgeItem.status == "published", KnowledgeItem.created_at >= cutoff)
    )
    growth = growth_result.scalar() or 0

    return ApiResponse(data={"totalKnowledgeCount": total_count, "byDomain": domain_dist, "growthLast30Days": growth})


@router.get("/stats/contribution-rank", response_model=ApiResponse)
async def get_contribution_rank(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(
        select(KnowledgeItem.owner_id, func.count())
        .where(KnowledgeItem.status == "published", KnowledgeItem.owner_id.is_not(None))
        .group_by(KnowledgeItem.owner_id)
        .order_by(func.count().desc())
        .limit(20)
    )
    return ApiResponse(data=[{"userId": row[0], "publishedCount": row[1]} for row in result.all()])


@router.get("/stats/usage", response_model=ApiResponse)
async def get_usage_stats(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    from app.models.models import QaSession, RagQueryLog

    qa_sessions_result = await db.execute(select(func.count()).select_from(QaSession))
    qa_sessions = qa_sessions_result.scalar() or 0
    rag_queries_result = await db.execute(select(func.count()).select_from(RagQueryLog))
    rag_queries = rag_queries_result.scalar() or 0
    return ApiResponse(data={"qaSessions": qa_sessions, "ragQueries": rag_queries})


@router.get("/review-reminders", response_model=ApiResponse)
async def get_review_reminders(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=3)
    result = await db.execute(
        select(ReviewWorkflow).where(ReviewWorkflow.current_stage == "pending", ReviewWorkflow.submitted_at < cutoff).limit(50)
    )
    return ApiResponse(data=[
        {"workflowId": w.id, "knowledgeId": w.knowledge_id, "submittedAt": w.submitted_at.isoformat() if w.submitted_at else None}
        for w in result.scalars().all()
    ])


@router.get("/audit-log", response_model=ApiResponse)
async def get_audit_log(
    resource_type: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    result = await db.execute(stmt)
    return ApiResponse(data=[
        {
            "id": a.id, "userId": a.user_id, "action": a.action, "resourceType": a.resource_type,
            "resourceId": a.resource_id, "detail": a.detail, "createdAt": a.created_at.isoformat(),
        }
        for a in result.scalars().all()
    ])


class SnapshotCreateRequest(BaseModel):
    name: str
    comment: Optional[str] = None
    creator_id: str


@router.post("/snapshot", response_model=ApiResponse)
async def create_snapshot(req: SnapshotCreateRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role("admin", "manager"))):
    """创建知识库状态快照：记录当时的条目统计并写入审计日志，作为可追溯的时间点标记。
    注意：这不是数据库物理备份（物理备份/回滚是运维层面的职责，超出应用层范围）。"""
    import json as json_module

    total_result = await db.execute(select(func.count()).select_from(KnowledgeItem))
    total_count = total_result.scalar() or 0
    by_domain_result = await db.execute(select(KnowledgeItem.domain, func.count()).group_by(KnowledgeItem.domain))
    by_domain = {row[0]: row[1] for row in by_domain_result.all()}
    by_status_result = await db.execute(select(KnowledgeItem.status, func.count()).group_by(KnowledgeItem.status))
    by_status = {row[0]: row[1] for row in by_status_result.all()}

    snapshot_id = f"SNAP{uuid4().hex[:8].upper()}"
    snapshot = KnowledgeSnapshot(
        id=snapshot_id, name=req.name, comment=req.comment, total_knowledge_count=total_count,
        by_domain_json=json_module.dumps(by_domain, ensure_ascii=False),
        by_status_json=json_module.dumps(by_status, ensure_ascii=False),
        creator_id=req.creator_id,
    )
    db.add(snapshot)
    db.add(AuditLog(
        id=f"AL{uuid4().hex[:12]}", user_id=req.creator_id, action="snapshot_create",
        resource_type="knowledge_snapshot", resource_id=snapshot_id, detail=req.name,
    ))
    await db.commit()
    return ApiResponse(data={
        "snapshotId": snapshot_id, "name": req.name, "totalKnowledgeCount": total_count,
        "byDomain": by_domain, "byStatus": by_status, "createdAt": snapshot.created_at.isoformat(),
    })


@router.get("/snapshots", response_model=ApiResponse)
async def list_snapshots(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    import json as json_module

    result = await db.execute(select(KnowledgeSnapshot).order_by(KnowledgeSnapshot.created_at.desc()).limit(50))
    return ApiResponse(data=[
        {
            "snapshotId": s.id, "name": s.name, "comment": s.comment,
            "totalKnowledgeCount": s.total_knowledge_count,
            "byDomain": json_module.loads(s.by_domain_json) if s.by_domain_json else {},
            "byStatus": json_module.loads(s.by_status_json) if s.by_status_json else {},
            "creatorId": s.creator_id, "createdAt": s.created_at.isoformat(),
        }
        for s in result.scalars().all()
    ])