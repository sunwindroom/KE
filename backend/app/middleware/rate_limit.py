from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.db.redis import get_redis


def get_client_ip(request: Request, trust_proxy_headers: bool) -> str:
    """提取客户端真实 IP。

    默认只信任 TCP 连接的对端地址（request.client.host），避免任何人通过伪造
    X-Forwarded-For 请求头绕过限流/伪造登录失败锁定的目标账号之外的“来源 IP”。
    只有管理员在「系统设置」里明确打开 TRUST_PROXY_HEADERS（确认部署在可信反向代理之后）
    时，才会改用 X-Forwarded-For 的第一段。
    """
    if trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        redis = get_redis()

        if redis is None:
            return await call_next(request)

        client_id = get_client_ip(request, settings.TRUST_PROXY_HEADERS)
        key = f"phm:ratelimit:{client_id}"

        try:
            current = await redis.get(key)
            if current and int(current) >= settings.RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={"code": 42900, "message": "请求频率超限", "data": None},
                )
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            await pipe.execute()
        except Exception:
            pass

        return await call_next(request)
