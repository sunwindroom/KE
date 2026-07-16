import redis.asyncio as aioredis
from app.config import get_settings

redis_client: aioredis.Redis | None = None


async def init_redis():
    global redis_client
    settings = get_settings()
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()


def get_redis() -> aioredis.Redis:
    return redis_client