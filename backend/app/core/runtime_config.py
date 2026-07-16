"""运行时配置中心。

目标：生产环境的全部可配置项都能通过“系统设置”界面完成，管理员不需要登录服务器修改
.env / docker-compose 文件。做法是：

1. `CONFIG_CATALOG` 是配置项的“元数据字典”——每一项对应 `app.config.Settings` 里的一个
   字段，附带分类、中文标签、类型、是否敏感信息、修改后是否需要重启才能生效等描述信息，
   专门供“系统设置”页面渲染表单使用。
2. 管理员在界面上保存的值写入数据库表 `system_config`（敏感值经过加密），同时立即把
   同名属性覆盖写回全局唯一的 `Settings` 单例（`get_settings()` 返回的对象），这样：
   - 大部分“热配置”（大模型、向量模型、登录策略、限流、上传限制等）无需重启即可生效；
   - 少数“冷配置”（数据库/消息队列/对象存储等连接串、CORS 白名单）会在下次重启后生效
     （因为这些资源的连接池只在进程启动时建立一次），页面会明确提示需要重启。
3. 应用启动时会先从数据库把已保存的覆盖值加载回 Settings 单例，再去初始化各个连接池，
   确保“重启后生效”的配置真的生效，而不是每次重启都被 .env 里的默认值覆盖回去。

注意：.env / 环境变量依然是“出厂默认值”的来源（尤其是首次部署、数据库还未就绪时的
兜底），系统设置表里的记录是“运维在界面上做过的覆盖”，优先级更高。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret, mask_secret

logger = logging.getLogger(__name__)


@dataclass
class ConfigField:
    key: str  # 必须与 Settings 的字段名一致
    category: str
    label: str
    type: str  # "string" | "int" | "float" | "bool" | "list" | "secret"
    description: str = ""
    secret: bool = False
    restart_required: bool = False
    placeholder: str = ""


@dataclass
class ConfigCategory:
    key: str
    label: str
    description: str
    restart_required: bool  # 该分组内多数字段是否需要重启才生效（用于 UI 提示横幅）
    order: int


CATEGORIES: list[ConfigCategory] = [
    ConfigCategory("llm", "大模型 API", "对话/生成所使用的 LLM 服务端点、密钥与模型名称，修改后立即生效。", False, 1),
    ConfigCategory("embedding", "向量模型 API", "知识检索所使用的 Embedding 服务，修改后立即生效。", False, 2),
    ConfigCategory("security", "登录与安全策略", "JWT 令牌有效期、登录失败锁定策略，修改后立即生效。", False, 3),
    ConfigCategory("upload", "上传与限流", "文件上传大小/类型限制、接口限流阈值，修改后立即生效。", False, 4),
    ConfigCategory("cors", "跨域白名单", "允许访问后端 API 的前端域名列表，修改后需要重启后端才能生效。", True, 5),
    ConfigCategory("database", "PostgreSQL 数据库", "主数据库连接信息，修改后需要重启后端才能生效。", True, 6),
    ConfigCategory("graph_neo4j", "Neo4j 图数据库", "知识图谱存储，修改后需要重启后端才能生效。", True, 7),
    ConfigCategory("vector_milvus", "Milvus 向量数据库", "向量检索存储，修改后需要重启后端才能生效。", True, 8),
    ConfigCategory("storage_minio", "MinIO 对象存储", "文档/附件/模型文件存储，修改后需要重启后端才能生效。", True, 9),
    ConfigCategory("cache_redis", "Redis 缓存", "令牌黑名单、限流计数器等缓存，修改后需要重启后端才能生效。", True, 10),
    ConfigCategory("mq_rabbitmq", "RabbitMQ 消息队列", "数据接入异步管道，修改后需要重启后端才能生效。", True, 11),
    ConfigCategory("app", "应用基础信息", "应用名称、调试模式、API 文档开关等，修改后需要重启后端才能生效。", True, 12),
]

CONFIG_CATALOG: list[ConfigField] = [
    # ---------------- LLM ----------------
    ConfigField("LLM_ENDPOINT", "llm", "服务地址", "string", "OpenAI 兼容的 Chat Completions 接口地址，如 https://api.example.com/v1", placeholder="http://localhost:8001/v1"),
    ConfigField("LLM_API_KEY", "llm", "API Key", "secret", "调用大模型服务所需的密钥，留空则系统自动降级为规则化实现。", secret=True),
    ConfigField("LLM_MODEL_NAME", "llm", "模型名称", "string", "如 qwen2.5-72b-instruct、gpt-4o 等，需与服务商实际支持的模型名一致。", placeholder="qwen2.5-72b-instruct"),
    ConfigField("LLM_TIMEOUT", "llm", "请求超时（秒）", "int", "单次请求的最长等待时间。"),
    # ---------------- Embedding ----------------
    ConfigField("EMBEDDING_ENDPOINT", "embedding", "服务地址", "string", "OpenAI 兼容的 Embeddings 接口地址。", placeholder="http://localhost:8002/v1"),
    ConfigField("EMBEDDING_API_KEY", "embedding", "API Key", "secret", "调用向量服务所需的密钥；留空时会复用大模型 API Key，仍为空则不发送鉴权头。", secret=True),
    ConfigField("EMBEDDING_MODEL_NAME", "embedding", "模型名称", "string", "如 bge-m3、text-embedding-3-large 等。", placeholder="bge-m3"),
    ConfigField("EMBEDDING_DIMENSION", "embedding", "向量维度", "int", "必须与 Milvus 集合的维度一致，修改后需要重建向量集合，请谨慎调整。"),
    # ---------------- Security ----------------
    ConfigField("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "security", "访问令牌有效期（分钟）", "int"),
    ConfigField("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "security", "刷新令牌有效期（天）", "int"),
    ConfigField("LOGIN_MAX_ATTEMPTS", "security", "登录失败锁定阈值", "int", "连续失败达到该次数后临时锁定账号。"),
    ConfigField("LOGIN_LOCKOUT_MINUTES", "security", "锁定时长（分钟）", "int"),
    ConfigField("JWT_SECRET_KEY", "security", "JWT 签名密钥", "secret", "生产环境必须使用高强度随机值；更换后所有已签发的登录态会立即失效，且会导致此前保存的其他敏感配置（API Key 等）无法解密，请谨慎更换。", secret=True, restart_required=False),
    # ---------------- Upload / rate limit ----------------
    ConfigField("UPLOAD_MAX_SIZE_MB", "upload", "单文件最大体积（MB）", "int"),
    ConfigField("UPLOAD_ALLOWED_EXTENSIONS", "upload", "允许的文件后缀", "list", "逗号分隔，如 .pdf,.docx,.png"),
    ConfigField("RATE_LIMIT_PER_MINUTE", "upload", "接口限流（次/分钟/IP）", "int"),
    ConfigField("TRUST_PROXY_HEADERS", "upload", "信任反向代理的真实 IP 请求头", "bool", "部署在 Nginx/负载均衡之后时开启，否则限流与登录锁定会把所有用户识别成同一个 IP；如果没有可信代理，开启后客户端可伪造该请求头绕过限流，请谨慎开启。"),
    # ---------------- CORS ----------------
    ConfigField("CORS_ORIGINS", "cors", "允许的前端域名", "list", "逗号分隔，如 https://ke.example.com，生产环境不要包含 localhost 或 *。", restart_required=True),
    # ---------------- Database ----------------
    ConfigField("DATABASE_URL", "database", "连接串", "secret", "形如 postgresql+asyncpg://user:pass@host:5432/dbname", secret=True, restart_required=True),
    ConfigField("DATABASE_POOL_SIZE", "database", "连接池大小", "int", restart_required=True),
    ConfigField("DATABASE_MAX_OVERFLOW", "database", "连接池溢出上限", "int", restart_required=True),
    # ---------------- Neo4j ----------------
    ConfigField("NEO4J_URI", "graph_neo4j", "连接地址", "string", placeholder="bolt://localhost:7687", restart_required=True),
    ConfigField("NEO4J_USER", "graph_neo4j", "用户名", "string", restart_required=True),
    ConfigField("NEO4J_PASSWORD", "graph_neo4j", "密码", "secret", secret=True, restart_required=True),
    ConfigField("NEO4J_DATABASE", "graph_neo4j", "数据库名", "string", restart_required=True),
    # ---------------- Milvus ----------------
    ConfigField("MILVUS_HOST", "vector_milvus", "主机地址", "string", restart_required=True),
    ConfigField("MILVUS_PORT", "vector_milvus", "端口", "int", restart_required=True),
    ConfigField("MILVUS_COLLECTION", "vector_milvus", "集合名称", "string", restart_required=True),
    # ---------------- MinIO ----------------
    ConfigField("MINIO_ENDPOINT", "storage_minio", "服务地址", "string", placeholder="localhost:9000", restart_required=True),
    ConfigField("MINIO_ACCESS_KEY", "storage_minio", "Access Key", "string", restart_required=True),
    ConfigField("MINIO_SECRET_KEY", "storage_minio", "Secret Key", "secret", secret=True, restart_required=True),
    ConfigField("MINIO_SECURE", "storage_minio", "启用 HTTPS", "bool", restart_required=True),
    # ---------------- Redis ----------------
    ConfigField("REDIS_URL", "cache_redis", "连接串", "secret", "形如 redis://[:password@]host:6379/0", secret=True, restart_required=True),
    # ---------------- RabbitMQ ----------------
    ConfigField("RABBITMQ_URL", "mq_rabbitmq", "连接串", "secret", "形如 amqp://user:pass@host:5672/", secret=True, restart_required=True),
    ConfigField("RABBITMQ_INGESTION_QUEUE", "mq_rabbitmq", "接入队列名", "string", restart_required=True),
    ConfigField("RABBITMQ_DLQ", "mq_rabbitmq", "死信队列名", "string", restart_required=True),
    # ---------------- App ----------------
    ConfigField("APP_NAME", "app", "应用名称", "string", restart_required=True),
    ConfigField("DEBUG", "app", "调试模式", "bool", "生产环境务必关闭。", restart_required=True),
    ConfigField("EXPOSE_API_DOCS", "app", "开放 API 文档（/docs）", "bool", restart_required=True),
    ConfigField("LOG_LEVEL", "app", "日志级别", "string", placeholder="INFO", restart_required=True),
]

CATALOG_BY_KEY: dict[str, ConfigField] = {f.key: f for f in CONFIG_CATALOG}
CATEGORY_BY_KEY: dict[str, ConfigCategory] = {c.key: c for c in CATEGORIES}

# EMBEDDING_API_KEY 不是 Settings 里的原生字段（复用 LLM_API_KEY 作为默认值），
# 单独维护，写入/读取方式与其余字段一致。
_EXTRA_KEYS = {"EMBEDDING_API_KEY"}


def _serialize(field_meta: ConfigField, value: Any) -> str:
    if value is None:
        return ""
    if field_meta.type == "list":
        if isinstance(value, list):
            return ",".join(str(v) for v in value)
        return str(value)
    if field_meta.type == "bool":
        return "true" if value else "false"
    return str(value)


def _deserialize(field_meta: ConfigField, raw: str) -> Any:
    if field_meta.type == "int":
        return int(raw)
    if field_meta.type == "float":
        return float(raw)
    if field_meta.type == "bool":
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if field_meta.type == "list":
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


# 进程内缓存：EMBEDDING_API_KEY 不属于 Settings 字段，单独存一份供 llm_client 读取。
_extra_runtime_values: dict[str, str] = {}


def get_extra(key: str, default: str = "") -> str:
    return _extra_runtime_values.get(key, default)


async def bootstrap(session: AsyncSession) -> None:
    """应用启动时调用：把数据库中保存的配置覆盖加载回 Settings 单例。"""
    await reload_from_db(session)
    logger.info("系统配置中心已从数据库加载运行时覆盖值")


async def reload_from_db(session: AsyncSession) -> None:
    from app.models.models import SystemConfig

    settings = get_settings()
    master_key = settings.JWT_SECRET_KEY
    result = await session.execute(select(SystemConfig))
    rows = result.scalars().all()
    for row in rows:
        field_meta = CATALOG_BY_KEY.get(row.key)
        is_extra = row.key in _EXTRA_KEYS
        if field_meta is None and not is_extra:
            continue
        raw_value = row.value or ""
        if row.is_secret:
            raw_value = decrypt_secret(raw_value, master_key)
        if not raw_value and (field_meta is None or field_meta.secret):
            # 敏感值解密失败或为空时，跳过覆盖，保留 .env 默认值，避免把可用配置清空。
            continue
        if is_extra:
            _extra_runtime_values[row.key] = raw_value
            continue
        try:
            setattr(settings, row.key, _deserialize(field_meta, raw_value))
        except (ValueError, TypeError):
            logger.warning("系统配置项 %s 的存储值无法解析，已忽略，沿用默认值", row.key)


async def get_category_values(session: AsyncSession, category: str) -> list[dict]:
    """返回某个分类下所有字段的“当前有效值”（供设置页展示），敏感值经过打码。"""
    settings = get_settings()
    fields = [f for f in CONFIG_CATALOG if f.category == category]
    items = []
    for f in fields:
        if f.secret:
            current = getattr(settings, f.key, "") if f.key != "EMBEDDING_API_KEY" else get_extra("EMBEDDING_API_KEY")
            display = mask_secret(current)
            configured = bool(current)
        else:
            current = getattr(settings, f.key, "")
            display = current
            configured = True
        items.append(
            {
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "description": f.description,
                "secret": f.secret,
                "restartRequired": f.restart_required,
                "placeholder": f.placeholder,
                "value": display,
                "configured": configured,
            }
        )
    return items


async def update_category(session: AsyncSession, category: str, values: dict[str, Any], updated_by: str) -> list[str]:
    """保存某个分类下的一批字段，返回其中"需要重启才能生效"的字段 key 列表。"""
    from app.models.models import SystemConfig

    settings = get_settings()
    master_key = settings.JWT_SECRET_KEY
    restart_needed: list[str] = []

    for key, raw_new_value in values.items():
        field_meta = CATALOG_BY_KEY.get(key)
        is_extra = key in _EXTRA_KEYS
        if field_meta is None and not is_extra:
            continue
        if field_meta and field_meta.category != category:
            continue

        # 约定：密钥类字段如果用户没有修改，前端根本不会把这个 key 放进提交的 payload
        # （见前端 settings 页），所以这里出现的都是"用户主动填写的新值"，直接覆盖即可；
        # 特殊值 "__CLEAR__" 表示用户主动清空该密钥。
        if raw_new_value == "__CLEAR__":
            raw_new_value = ""

        row_id = f"{category}.{key}"
        result = await session.execute(select(SystemConfig).where(SystemConfig.id == row_id))
        row = result.scalar_one_or_none()

        is_secret_field = bool(field_meta.secret) if field_meta else True
        if is_secret_field:
            store_value = encrypt_secret(str(raw_new_value), master_key)
        else:
            store_value = _serialize(field_meta, raw_new_value)

        if row is None:
            row = SystemConfig(id=row_id, category=category, key=key, value=store_value, is_secret=1 if is_secret_field else 0, updated_by=updated_by)
            session.add(row)
        else:
            row.value = store_value
            row.is_secret = 1 if is_secret_field else 0
            row.updated_by = updated_by

        # 立即应用到运行时（热配置立刻生效；冷配置也写入 Settings 单例，
        # 只是真正建立连接的代码要等下次重启才会重新读取）。
        if is_extra:
            _extra_runtime_values[key] = str(raw_new_value)
        else:
            try:
                setattr(settings, key, _deserialize(field_meta, str(raw_new_value)))
            except (ValueError, TypeError):
                continue

        if field_meta and field_meta.restart_required:
            restart_needed.append(key)

    await session.commit()
    return restart_needed


async def reset_category(session: AsyncSession, category: str) -> None:
    """删除该分类下所有数据库覆盖记录，恢复为 .env 中的出厂默认值（需要重启才能完全恢复冷配置）。"""
    from app.config import Settings as _Settings
    from app.models.models import SystemConfig

    result = await session.execute(select(SystemConfig).where(SystemConfig.category == category))
    rows = result.scalars().all()
    fresh_defaults = _Settings()
    settings = get_settings()
    for row in rows:
        field_meta = CATALOG_BY_KEY.get(row.key)
        if field_meta is not None:
            setattr(settings, row.key, getattr(fresh_defaults, row.key))
        elif row.key in _EXTRA_KEYS:
            _extra_runtime_values.pop(row.key, None)
        await session.delete(row)
    await session.commit()
