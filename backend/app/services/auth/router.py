import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgresql import get_db
from app.core.auth import create_access_token, create_refresh_token, decode_token, revoke_token, SecurityContext
from app.core.security import verify_password, get_password_hash
from app.core.exceptions import AuthenticationException, BusinessException
from app.middleware.auth import get_current_user, security_scheme
from app.models.models import UserPermission
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest, UserInfo
from app.schemas.common import ApiResponse
from app.config import get_settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def _login_lockout_key(username: str) -> str:
    return f"phm:loginfail:{username}"


async def _check_login_lockout(username: str) -> None:
    from app.db.redis import get_redis

    redis = get_redis()
    if redis is None:
        return
    settings = get_settings()
    try:
        attempts = await redis.get(_login_lockout_key(username))
        if attempts and int(attempts) >= settings.LOGIN_MAX_ATTEMPTS:
            raise AuthenticationException(f"登录失败次数过多，请 {settings.LOGIN_LOCKOUT_MINUTES} 分钟后重试")
    except AuthenticationException:
        raise
    except Exception:
        logger.exception("检查登录失败锁定状态时出错")


async def _record_login_failure(username: str) -> None:
    from app.db.redis import get_redis

    redis = get_redis()
    if redis is None:
        return
    settings = get_settings()
    try:
        pipe = redis.pipeline()
        pipe.incr(_login_lockout_key(username))
        pipe.expire(_login_lockout_key(username), settings.LOGIN_LOCKOUT_MINUTES * 60)
        await pipe.execute()
    except Exception:
        logger.exception("记录登录失败次数时出错")


async def _clear_login_failures(username: str) -> None:
    from app.db.redis import get_redis

    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.delete(_login_lockout_key(username))
    except Exception:
        logger.exception("清除登录失败计数时出错")


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    await _check_login_lockout(req.username)

    result = await db.execute(
        select(UserPermission).where(
            (UserPermission.user_name == req.username) | (UserPermission.user_id == req.username)
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        await _record_login_failure(req.username)
        raise AuthenticationException("用户名或密码错误")
    if user.status != "active":
        raise AuthenticationException("账户已禁用")

    await _clear_login_failures(req.username)

    user.last_login_at = datetime.now()
    await db.commit()

    settings = get_settings()
    access_token = create_access_token({"sub": user.user_id, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.user_id})
    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise AuthenticationException("无效的刷新令牌")

    old_jti = payload.get("jti")
    from app.core.auth import is_token_revoked
    if old_jti and await is_token_revoked(old_jti):
        raise AuthenticationException("该刷新令牌已被使用过，请重新登录")

    user_id = payload.get("sub")
    result = await db.execute(select(UserPermission).where(UserPermission.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise AuthenticationException()

    # 刷新令牌一次性轮换：本次用过的 refresh token 立即失效，防止令牌被窃取后重复使用
    if old_jti:
        exp = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await revoke_token(old_jti, expires_at)

    settings = get_settings()
    access_token = create_access_token({"sub": user.user_id, "role": user.role})
    new_refresh_token = create_refresh_token({"sub": user.user_id})
    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.post("/logout", response_model=ApiResponse[None])
async def logout(
    req: LogoutRequest = LogoutRequest(),
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    ctx: SecurityContext = Depends(get_current_user),
):
    payload = decode_token(credentials.credentials)
    if payload and payload.get("jti"):
        exp = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await revoke_token(payload["jti"], expires_at)

    if req.refresh_token:
        refresh_payload = decode_token(req.refresh_token)
        if refresh_payload and refresh_payload.get("jti"):
            exp = refresh_payload.get("exp")
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
            await revoke_token(refresh_payload["jti"], expires_at)

    return ApiResponse(message="已登出")


@router.post("/change-password", response_model=ApiResponse[None])
async def change_password(req: ChangePasswordRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(UserPermission).where(UserPermission.user_id == ctx.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationException()
    if not verify_password(req.old_password, user.password_hash):
        raise BusinessException(code=40001, message="原密码不正确")
    if len(req.new_password) < 8:
        raise BusinessException(code=40001, message="新密码长度至少为 8 位")

    user.password_hash = get_password_hash(req.new_password)
    await db.commit()
    return ApiResponse(message="密码已更新，请重新登录")


@router.get("/me", response_model=ApiResponse[UserInfo])
async def get_me(ctx: SecurityContext = Depends(get_current_user)):
    return ApiResponse(
        data=UserInfo(
            userId=ctx.user_id,
            userName=ctx.user_name,
            role=ctx.role,
            domainScope=ctx.domain_scope,
            maxClassificationLevel=ctx.max_classification_level,
        )
    )
