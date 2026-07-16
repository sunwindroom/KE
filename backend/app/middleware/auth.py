from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgresql import get_db
from app.core.auth import decode_token, is_token_revoked, SecurityContext
from app.core.exceptions import AuthenticationException, PermissionDeniedException
from app.models.models import UserPermission

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> SecurityContext:
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise AuthenticationException()

    if await is_token_revoked(payload.get("jti")):
        raise AuthenticationException("登录已失效，请重新登录")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationException()

    result = await db.execute(select(UserPermission).where(UserPermission.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise AuthenticationException()

    return SecurityContext(
        user_id=user.user_id,
        user_name=user.user_name,
        role=user.role,
        domain_scope=user.domain_scope.split(","),
        max_classification_level=user.max_classification_level,
    )


def require_role(*roles: str):
    async def role_checker(ctx: SecurityContext = Depends(get_current_user)) -> SecurityContext:
        if not ctx.has_role(*roles):
            raise PermissionDeniedException(f"需要角色: {', '.join(roles)}")
        return ctx
    return role_checker


def require_domain(domain: str):
    async def domain_checker(ctx: SecurityContext = Depends(get_current_user)) -> SecurityContext:
        if not ctx.has_domain(domain):
            raise PermissionDeniedException(f"无权访问领域: {domain}")
        return ctx
    return domain_checker


def require_classification(level: str):
    """要求当前用户的最高密级达到给定级别，用于保护涉密操作/端点本身
    （而不是逐条数据的过滤，逐条过滤见 SecurityContext.can_access_classification 在业务代码中的用法）。"""
    async def classification_checker(ctx: SecurityContext = Depends(get_current_user)) -> SecurityContext:
        if not ctx.can_access_classification(level):
            raise PermissionDeniedException(f"需要密级: {level} 及以上")
        return ctx
    return classification_checker