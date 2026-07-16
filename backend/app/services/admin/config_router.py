"""系统设置接口：让整个项目的生产环境配置都能通过 UI 完成，不需要登录服务器改文件。

覆盖范围：大模型 API、向量模型 API、登录与安全策略、上传与限流、CORS 白名单，
以及 PostgreSQL / Neo4j / Milvus / MinIO / Redis / RabbitMQ / 应用基础信息。
所有接口都要求 admin 角色，敏感字段落库前加密、出接口前打码，绝不明文回显。
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_config as rc
from app.core.auth import SecurityContext
from app.core.exceptions import BusinessException
from app.db.postgresql import get_db
from app.middleware.auth import require_role
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/config", tags=["系统设置"])


@router.get("/categories", response_model=ApiResponse)
async def list_categories(ctx: SecurityContext = Depends(require_role("admin"))):
    categories = sorted(rc.CATEGORIES, key=lambda c: c.order)
    return ApiResponse(
        data=[
            {
                "key": c.key,
                "label": c.label,
                "description": c.description,
                "restartRequired": c.restart_required,
            }
            for c in categories
        ]
    )


@router.get("/{category}", response_model=ApiResponse)
async def get_category(category: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role("admin"))):
    if category not in rc.CATEGORY_BY_KEY:
        raise BusinessException(40400, "未知的配置分类")
    items = await rc.get_category_values(db, category)
    return ApiResponse(data={"category": category, "fields": items})


class UpdateConfigRequest(BaseModel):
    values: dict[str, Any]


@router.put("/{category}", response_model=ApiResponse)
async def update_category(
    category: str,
    req: UpdateConfigRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(require_role("admin")),
):
    if category not in rc.CATEGORY_BY_KEY:
        raise BusinessException(40400, "未知的配置分类")
    restart_needed = await rc.update_category(db, category, req.values, updated_by=ctx.user_id)

    import uuid

    from app.models.models import AuditLog

    db.add(
        AuditLog(
            id=uuid.uuid4().hex[:32],
            user_id=ctx.user_id,
            action="update_system_config",
            resource_type=category,
        )
    )
    await db.commit()

    return ApiResponse(
        data={
            "category": category,
            "restartRequired": restart_needed,
            "message": "配置已保存并立即生效" if not restart_needed else "配置已保存，其中部分连接类配置需要重启后端服务才能生效",
        }
    )


@router.post("/{category}/reset", response_model=ApiResponse)
async def reset_category(category: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(require_role("admin"))):
    if category not in rc.CATEGORY_BY_KEY:
        raise BusinessException(40400, "未知的配置分类")
    await rc.reset_category(db, category)
    return ApiResponse(data={"category": category, "message": "已恢复为部署时的默认值（.env）"})


class TestLLMRequest(BaseModel):
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None


@router.post("/llm/test", response_model=ApiResponse)
async def test_llm(req: TestLLMRequest, ctx: SecurityContext = Depends(require_role("admin"))):
    import httpx

    from app.config import get_settings

    settings = get_settings()
    endpoint = (req.endpoint or settings.LLM_ENDPOINT).rstrip("/")
    api_key = req.api_key if req.api_key else settings.LLM_API_KEY
    model = req.model or settings.LLM_MODEL_NAME

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "请回复“连接成功”四个字用于测试。"}],
        "temperature": 0,
        "max_tokens": 16,
    }
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code >= 400:
            return ApiResponse(data={"success": False, "latencyMs": latency_ms, "message": f"服务返回错误状态码 {resp.status_code}：{resp.text[:200]}"})
        data = resp.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return ApiResponse(data={"success": True, "latencyMs": latency_ms, "message": "连接成功", "sample": reply[:100]})
    except httpx.TimeoutException:
        return ApiResponse(data={"success": False, "latencyMs": None, "message": "连接超时，请检查服务地址是否可达"})
    except Exception as e:
        logger.warning("LLM 测试连接失败: %s", e)
        return ApiResponse(data={"success": False, "latencyMs": None, "message": f"连接失败：{e}"})


class TestEmbeddingRequest(BaseModel):
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None


@router.post("/embedding/test", response_model=ApiResponse)
async def test_embedding(req: TestEmbeddingRequest, ctx: SecurityContext = Depends(require_role("admin"))):
    import httpx

    from app.config import get_settings

    settings = get_settings()
    endpoint = (req.endpoint or settings.EMBEDDING_ENDPOINT).rstrip("/")
    api_key = req.api_key if req.api_key else (rc.get_extra("EMBEDDING_API_KEY") or settings.LLM_API_KEY)
    model = req.model or settings.EMBEDDING_MODEL_NAME

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "input": ["连接测试"]}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{endpoint}/embeddings", json=payload, headers=headers)
        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code >= 400:
            return ApiResponse(data={"success": False, "latencyMs": latency_ms, "message": f"服务返回错误状态码 {resp.status_code}：{resp.text[:200]}"})
        data = resp.json()
        dim = len(data.get("data", [{}])[0].get("embedding", []))
        return ApiResponse(data={"success": True, "latencyMs": latency_ms, "message": "连接成功", "sample": f"返回向量维度: {dim}"})
    except httpx.TimeoutException:
        return ApiResponse(data={"success": False, "latencyMs": None, "message": "连接超时，请检查服务地址是否可达"})
    except Exception as e:
        logger.warning("Embedding 测试连接失败: %s", e)
        return ApiResponse(data={"success": False, "latencyMs": None, "message": f"连接失败：{e}"})


class TestInfraRequest(BaseModel):
    values: dict[str, Any] = {}


@router.post("/{category}/test", response_model=ApiResponse)
async def test_infra(category: str, req: TestInfraRequest, ctx: SecurityContext = Depends(require_role("admin"))):
    """基础设施类连接测试：使用表单里尚未保存的值直接探测连通性，保存前就能验证是否可用。"""
    from app.config import get_settings

    settings = get_settings()

    def val(key: str) -> Any:
        return req.values.get(key, getattr(settings, key, None))

    start = time.monotonic()
    try:
        if category == "database":
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(val("DATABASE_URL"), pool_pre_ping=True)
            async with engine.connect():
                pass
            await engine.dispose()
        elif category == "graph_neo4j":
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(val("NEO4J_URI"), auth=(val("NEO4J_USER"), val("NEO4J_PASSWORD")))
            async with driver.session(database=val("NEO4J_DATABASE")) as session:
                await session.run("RETURN 1")
            await driver.close()
        elif category == "vector_milvus":
            from pymilvus import MilvusClient

            client = MilvusClient(uri=f"http://{val('MILVUS_HOST')}:{val('MILVUS_PORT')}")
            client.list_collections()
            client.close()
        elif category == "storage_minio":
            from minio import Minio

            client = Minio(val("MINIO_ENDPOINT"), access_key=val("MINIO_ACCESS_KEY"), secret_key=val("MINIO_SECRET_KEY"), secure=bool(val("MINIO_SECURE")))
            client.list_buckets()
        elif category == "cache_redis":
            import redis.asyncio as aioredis

            client = aioredis.from_url(val("REDIS_URL"))
            await client.ping()
            await client.close()
        elif category == "mq_rabbitmq":
            import aio_pika

            connection = await aio_pika.connect(val("RABBITMQ_URL"), timeout=10)
            await connection.close()
        else:
            return ApiResponse(data={"success": False, "message": "该分类不支持连接测试"})
        latency_ms = int((time.monotonic() - start) * 1000)
        return ApiResponse(data={"success": True, "latencyMs": latency_ms, "message": "连接成功"})
    except Exception as e:
        logger.warning("[%s] 连接测试失败: %s", category, e)
        return ApiResponse(data={"success": False, "latencyMs": None, "message": f"连接失败：{e}"})
