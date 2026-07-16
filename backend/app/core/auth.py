import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.config import get_settings

logger = logging.getLogger(__name__)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access", "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def _blacklist_key(jti: str) -> str:
    settings = get_settings()
    return f"{settings.REDIS_TOKEN_PREFIX}blacklist:{jti}"


async def revoke_token(jti: str, expires_at: Optional[datetime] = None) -> None:
    """把某个 token 的 jti 加入 Redis 黑名单，TTL 与该 token 剩余有效期对齐。
    Redis 不可用时静默跳过（fail-open）——这是有意为之的可用性权衡：一次 Redis 抖动
    不应导致所有已登录用户被拒绝访问，代价是极端情况下撤销可能延迟生效。"""
    from app.db.redis import get_redis

    redis = get_redis()
    if redis is None:
        logger.warning("Redis 不可用，无法将 token %s 加入黑名单（本次登出/刷新轮换不会真正生效）", jti)
        return
    ttl_seconds = 3600
    if expires_at is not None:
        ttl_seconds = max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 1)
    try:
        await redis.set(_blacklist_key(jti), "1", ex=ttl_seconds)
    except Exception:
        logger.exception("Failed to write token blacklist entry for jti=%s", jti)


async def is_token_revoked(jti: Optional[str]) -> bool:
    if not jti:
        return False
    from app.db.redis import get_redis

    redis = get_redis()
    if redis is None:
        return False
    try:
        return bool(await redis.get(_blacklist_key(jti)))
    except Exception:
        logger.exception("Failed to check token blacklist for jti=%s", jti)
        return False


class SecurityContext:
    def __init__(self, user_id: str, user_name: str, role: str, domain_scope: list[str], max_classification_level: str):
        self.user_id = user_id
        self.user_name = user_name
        self.role = role
        self.domain_scope = domain_scope
        self.max_classification_level = max_classification_level

    def has_domain(self, domain: str) -> bool:
        return domain in self.domain_scope or "general" in self.domain_scope

    def can_access_classification(self, level: str) -> bool:
        level_order = {"public": 0, "internal": 1, "confidential": 2, "secret": 3}
        return level_order.get(level, 99) <= level_order.get(self.max_classification_level, 0)

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def is_admin(self) -> bool:
        return self.role == "admin"