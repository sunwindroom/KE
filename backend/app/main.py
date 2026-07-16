import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings, validate_production_config
from app.core.exceptions import BusinessException
from app.core.logging_config import setup_logging
from app.db.milvus import close_milvus, init_milvus
from app.db.minio import close_minio, init_minio
from app.db.neo4j import close_neo4j, init_neo4j
from app.db.postgresql import close_db, init_db
from app.db.rabbitmq import close_rabbitmq, init_rabbitmq
from app.db.redis import close_redis, init_redis
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()

    await init_db()

    from app.core.runtime_config import bootstrap as bootstrap_runtime_config
    from app.db.postgresql import async_session_factory

    try:
        async with async_session_factory() as session:
            await bootstrap_runtime_config(session)
    except Exception:
        logger.exception("加载数据库中的系统设置覆盖值失败，本次启动将只使用 .env 中的默认配置")

    # 放在数据库覆盖值加载完之后再校验，这样管理员在「系统设置」里填入的值
    # （而不仅仅是 .env 里的出厂默认值）也会被检查到。
    for warning in validate_production_config(settings):
        logger.warning("[配置安全警告] %s", warning)

    await init_neo4j()
    await init_milvus()
    await init_minio()
    await init_redis()
    await init_rabbitmq()
    logger.info("PHM 知识工程系统启动完成")
    yield
    await close_db()
    await close_neo4j()
    await close_milvus()
    await close_minio()
    await close_redis()
    await close_rabbitmq()
    logger.info("PHM 知识工程系统已关闭")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.EXPOSE_API_DOCS else None,
        redoc_url="/redoc" if settings.EXPOSE_API_DOCS else None,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(BusinessException)
    async def business_exception_handler(request: Request, exc: BusinessException):
        # exc.code 的前三位数字即对应的 HTTP 状态码 (e.g. 40100 -> 401, 40400 -> 404)
        http_status = exc.code // 100 if exc.code >= 40000 else 400
        return JSONResponse(
            status_code=http_status,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": None,
                "request_id": getattr(request.state, "request_id", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 兜底处理：任何未被 BusinessException 覆盖的异常都不能把内部堆栈/错误细节泄露给客户端，
        # 但要在服务端完整记录，并把 request_id 带回去方便运维根据日志定位。
        request_id = getattr(request.state, "request_id", "")
        logger.exception("Unhandled exception on %s %s (request_id=%s)", request.method, request.url.path, request_id)
        return JSONResponse(
            status_code=500,
            content={
                "code": 50000,
                "message": "服务器内部错误，请稍后重试",
                "data": None,
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    from app.services.admin.config_router import router as admin_config_router
    from app.services.admin.router import router as admin_router
    from app.services.agent.router import router as agent_router
    from app.services.auth.router import router as auth_router
    from app.services.extraction.router import router as extraction_router
    from app.services.finetune.router import router as finetune_router
    from app.services.governance.router import router as governance_router
    from app.services.ingestion.router import router as ingestion_router
    from app.services.ontology.router import router as ontology_router
    from app.services.open.router import router as open_router
    from app.services.rag.router import rag_router
    from app.services.rag.router import router as qa_router
    from app.services.storage.router import router as knowledge_router

    app.include_router(auth_router, prefix=settings.API_PREFIX, tags=["认证"])
    app.include_router(ingestion_router, prefix=settings.API_PREFIX, tags=["数据接入"])
    app.include_router(extraction_router, prefix=settings.API_PREFIX, tags=["知识抽取"])
    app.include_router(ontology_router, prefix=settings.API_PREFIX, tags=["本体与图谱"])
    app.include_router(knowledge_router, prefix=settings.API_PREFIX, tags=["知识检索"])
    app.include_router(qa_router, prefix=settings.API_PREFIX, tags=["知识问答"])
    app.include_router(rag_router, prefix=settings.API_PREFIX, tags=["RAG检索"])
    app.include_router(agent_router, prefix=settings.API_PREFIX, tags=["Agent智能体"])
    app.include_router(finetune_router, prefix=settings.API_PREFIX, tags=["领域微调"])
    app.include_router(governance_router, prefix=settings.API_PREFIX, tags=["知识治理"])
    app.include_router(admin_router, prefix=settings.API_PREFIX, tags=["系统管理"])
    app.include_router(admin_config_router, prefix=settings.API_PREFIX, tags=["系统设置"])
    app.include_router(open_router, prefix=settings.API_PREFIX, tags=["开放接口"])

    return app


app = create_app()
