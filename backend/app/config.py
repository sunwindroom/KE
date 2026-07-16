from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "PHM Knowledge Engineering System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    EXPOSE_API_DOCS: bool = True
    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://phm:phm123@localhost:5432/phm_ke"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j123"
    NEO4J_DATABASE: str = "neo4j"

    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "knowledge_embeddings"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TOKEN_PREFIX: str = "phm:token:"
    REDIS_CACHE_PREFIX: str = "phm:cache:"

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_INGESTION_QUEUE: str = "km.ingestion.raw"
    RABBITMQ_DLQ: str = "km.ingestion.dlq"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    LLM_ENDPOINT: str = "http://localhost:8001/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL_NAME: str = "qwen2.5-72b-instruct"
    LLM_TIMEOUT: int = 120

    EMBEDDING_ENDPOINT: str = "http://localhost:8002/v1"
    EMBEDDING_MODEL_NAME: str = "bge-m3"
    EMBEDDING_DIMENSION: int = 1024

    UPLOAD_MAX_SIZE_MB: int = 200
    UPLOAD_ALLOWED_EXTENSIONS: list[str] = [".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".md"]

    RATE_LIMIT_PER_MINUTE: int = 100
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    # 部署在 Nginx/Caddy/云负载均衡等反向代理之后时，request.client.host 拿到的永远是
    # 代理自身的 IP，导致所有用户共享同一个限流桶——一个人就能把全站限流打满。
    # 打开该项后会改用 X-Forwarded-For 的第一段作为真实客户端 IP。
    # 注意：只有确认前面确实有可信代理时才应打开，否则客户端可以伪造该请求头绕过限流。
    TRUST_PROXY_HEADERS: bool = False

    # 原默认值里混入过一个具体开发机器的内网 IP（192.168.10.31），属于本不该提交的
    # 本地联调残留，现按生产模板惯例移除，只保留本地开发常用的 localhost 地址。
    # 生产环境请在「系统设置 → 跨域白名单」中填写实际的前端域名。
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_production_config(settings: Settings) -> list[str]:
    """返回一组配置层面的安全隐患警告；DEBUG=False（生产模式）时如果仍是不安全的默认值会被检测到。"""
    warnings = []
    if not settings.DEBUG:
        if len(settings.JWT_SECRET_KEY) < 32 or "change" in settings.JWT_SECRET_KEY.lower() or settings.JWT_SECRET_KEY == "secret":
            warnings.append("JWT_SECRET_KEY 疑似仍是占位/弱密钥（过短或包含 'change'），生产环境必须设置为随机高强度密钥（建议 openssl rand -hex 32）")
        if settings.MINIO_ACCESS_KEY == "minioadmin" and settings.MINIO_SECRET_KEY == "minioadmin":
            warnings.append("MinIO 仍使用默认的 minioadmin/minioadmin 凭据，生产环境应更换")
        if "localhost" in settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS:
            warnings.append("CORS_ORIGINS 包含 localhost 或通配符，生产环境应收紧为实际前端域名")
    return warnings