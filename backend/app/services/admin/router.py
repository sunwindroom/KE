from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth import SecurityContext
from app.core.security import get_password_hash
from app.db.postgresql import get_db
from app.middleware.auth import require_role
from app.models.models import AuditLog, UserPermission
from app.schemas.common import ApiResponse, PaginatedResponse


def _mask_secret(value: str) -> str:
    """只暴露末 4 位，其余打码；未配置时返回空字符串。"""
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]

router = APIRouter(prefix="/admin", tags=["系统管理"])


class UserCreateRequest(BaseModel):
    user_id: str
    user_name: str
    password: str
    role: str = "engineer"
    domain_scope: str = "energy,transportation,aerospace,general"
    max_classification_level: str = "internal"


class RoleUpdateRequest(BaseModel):
    role: str


class PermissionUpdateRequest(BaseModel):
    domain_scope: Optional[str] = None
    max_classification_level: Optional[str] = None


@router.get("/users", response_model=ApiResponse[PaginatedResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(require_role("admin")),
):
    total_result = await db.execute(select(func.count()).select_from(UserPermission))
    total = total_result.scalar() or 0
    result = await db.execute(select(UserPermission).offset((page - 1) * page_size).limit(page_size))
    items = [
        {"userId": u.user_id, "userName": u.user_name, "role": u.role, "domainScope": u.domain_scope, "maxClassificationLevel": u.max_classification_level, "status": u.status}
        for u in result.scalars().all()
    ]
    return ApiResponse(data=PaginatedResponse(page=page, page_size=page_size, total=total, items=items))


@router.post("/users", response_model=ApiResponse)
async def create_user(req: UserCreateRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role("admin"))):
    user = UserPermission(
        user_id=req.user_id,
        user_name=req.user_name,
        password_hash=get_password_hash(req.password),
        role=req.role,
        domain_scope=req.domain_scope,
        max_classification_level=req.max_classification_level,
    )
    db.add(user)
    await db.commit()
    return ApiResponse(data={"userId": user.user_id})


@router.put("/users/{user_id}/role", response_model=ApiResponse)
async def update_role(user_id: str, req: RoleUpdateRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role("admin"))):
    result = await db.execute(select(UserPermission).where(UserPermission.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("用户不存在")
    user.role = req.role
    await db.commit()
    return ApiResponse(data={"userId": user_id, "role": req.role})


@router.put("/users/{user_id}/permission", response_model=ApiResponse)
async def update_permission(user_id: str, req: PermissionUpdateRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role("admin"))):
    result = await db.execute(select(UserPermission).where(UserPermission.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        from app.core.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException("用户不存在")
    if req.domain_scope:
        user.domain_scope = req.domain_scope
    if req.max_classification_level:
        user.max_classification_level = req.max_classification_level
    await db.commit()
    return ApiResponse(data={"userId": user_id})


@router.get("/audit-logs", response_model=ApiResponse[PaginatedResponse])
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Query(None),
    action: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(require_role("admin")),
):
    query = select(AuditLog)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    items = [{"id": log.id, "userId": log.user_id, "action": log.action, "resourceType": log.resource_type, "createdAt": str(log.created_at)} for log in result.scalars().all()]
    return ApiResponse(data=PaginatedResponse(page=page, page_size=page_size, total=total, items=items))


@router.get("/system/monitor", response_model=ApiResponse)
async def get_system_monitor(ctx: SecurityContext = Depends(require_role("admin"))):
    return ApiResponse(data={"status": "ok", "services": {}})


@router.get("/services", response_model=ApiResponse)
async def get_services(ctx: SecurityContext = Depends(require_role("admin"))):
    services = [
        {"name": "km-ingestion", "version": "1.8.0", "status": "OK", "cpu": 42},
        {"name": "km-extraction", "version": "2.1.4", "status": "OK", "cpu": 78},
        {"name": "km-graph", "version": "3.0.1", "status": "OK", "cpu": 35},
        {"name": "km-rag", "version": "1.5.2", "status": "OK", "cpu": 51},
        {"name": "km-agent", "version": "0.9.7", "status": "OK", "cpu": 28},
        {"name": "km-governance", "version": "1.2.0", "status": "OK", "cpu": 18},
        {"name": "km-gateway", "version": "2.4.0", "status": "OK", "cpu": 22},
        {"name": "km-scheduler", "version": "1.1.3", "status": "OK", "cpu": 12},
    ]
    return ApiResponse(data=services)


@router.get("/model/registry", response_model=ApiResponse)
async def get_model_registry(ctx: SecurityContext = Depends(require_role("admin"))):
    """返回当前系统接入的 LLM / Embedding 模型服务的真实配置状态（密钥打码）。

    只读展示接口，供仪表盘快速查看；完整的增删改与连接测试请使用
    /admin/config/llm 与 /admin/config/embedding（对应前端「系统设置」页面）。
    """
    from app.core.runtime_config import get_extra

    settings = get_settings()
    embedding_key = get_extra("EMBEDDING_API_KEY") or settings.LLM_API_KEY
    registry = [
        {
            "name": "LLM 对话模型",
            "kind": "llm",
            "endpoint": settings.LLM_ENDPOINT,
            "model": settings.LLM_MODEL_NAME,
            "apiKeyPreview": _mask_secret(settings.LLM_API_KEY),
            "configured": bool(settings.LLM_API_KEY),
            "status": "configured" if settings.LLM_API_KEY else "fallback_rule_based",
            "note": "未配置 API Key 时系统自动降级为确定性规则/摘要实现，接口仍可用但生成质量有限。可在「系统设置 → 大模型 API」中配置并测试连接。",
        },
        {
            "name": "Embedding 向量模型",
            "kind": "embedding",
            "endpoint": settings.EMBEDDING_ENDPOINT,
            "model": settings.EMBEDDING_MODEL_NAME,
            "apiKeyPreview": _mask_secret(embedding_key),
            "configured": bool(embedding_key),
            "status": "configured" if embedding_key else "fallback_rule_based",
            "note": f"向量维度 {settings.EMBEDDING_DIMENSION}，未配置时检索退化为关键字匹配。可在「系统设置 → 向量模型 API」中配置并测试连接。",
        },
    ]
    return ApiResponse(data=registry)
