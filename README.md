# Aether PHM 知识工程平台

面向 PHM（故障预测与健康管理）领域的知识工程系统：数据接入、知识抽取、专家审核、
本体与知识图谱、RAG 检索问答、Agent 智能体编排、知识治理。

## 快速开始（Docker Compose）

```bash
cp .env.example .env
# 必须设置 JWT_SECRET_KEY，例如：
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env
# 生产部署务必修改 POSTGRES_PASSWORD / NEO4J_PASSWORD / MINIO_*_KEY / RABBITMQ_PASSWORD 为强随机值

docker compose up -d --build

# 首次启动后初始化数据库表结构 + 种子管理员账号
docker compose exec backend alembic upgrade head
```

初始管理员账号：`admin` / `admin123`（来自迁移 `001_seed_admin.py`）——**首次登录后请立即修改密码**
（`POST /api/v1/auth/change-password`），生产环境不要保留默认密码。

## 常见问题排查

**前端报错"上传失败：Failed to fetch"，或页面数据一直加载不出来 / 显示 `—`**

这是浏览器 `fetch()` 在网络层面就失败了（区别于后端返回了错误响应），常见原因和排查顺序：

1. **后端服务未就绪或未启动**：执行 `docker compose ps` 确认 `backend` 容器状态为 `healthy`；
   `docker compose logs backend` 查看是否因为等待 Postgres/Neo4j/Milvus/MinIO/Redis/RabbitMQ
   健康检查通过而卡在启动阶段。
2. **`VITE_API_BASE_URL` 配置错误**：该变量是 **构建期** 变量，会被 Vite 直接内联进前端产物；
   如果你是通过局域网 IP、域名或非 `localhost` 的地址访问前端，必须在构建前端镜像前设置好它，
   例如：
   ```bash
   VITE_API_BASE_URL=http://<你的服务器地址>:8000/api/v1 docker compose up -d --build frontend
   ```
   仅修改 `.env` 或 `docker-compose.yml` 里的 `environment:` 而不重新构建镜像是不会生效的。
3. **CORS 白名单不包含当前前端访问的源**：后端 `CORS_ORIGINS`（`.env` 中配置，或通过管理后台的
   "系统设置"覆盖）需要包含浏览器地址栏里的协议+域名+端口，例如
   `http://192.168.1.10:3000`；改动 `.env` 中的 `CORS_ORIGINS` 后需要
   `docker compose restart backend`，通过管理后台修改的运行时配置同样需要重启后端才生效。
4. **HTTPS 页面调用 HTTP 接口（混合内容）会被浏览器静默拦截**：如果前端通过 HTTPS 访问，
   `VITE_API_BASE_URL` 也必须是 `https://`，否则浏览器会直接拒绝请求且只报 `Failed to fetch`，
   不会有更详细的信息。

修复后的前端在网络请求失败时会给出更具体的诊断信息（当前配置的后端地址、可能原因），而不是原始的
`Failed to fetch`，便于按上面的顺序定位。

## 权限模型

用户角色：`engineer`（工程师）/ `expert`（专家）/ `manager`（主管）/ `admin`（管理员）。
知识条目审核、冲突仲裁、本体发布、知识库快照等操作要求 `expert`/`manager`/`admin` 角色，
普通 `engineer` 只能提交、不能自我审核（系统会拒绝审核自己提交的知识条目）。

知识条目还带有密级（`public`/`internal`/`confidential`/`secret`）与领域范围
（`energy`/`transportation`/`aerospace`/`general`）双重访问控制：检索、问答、图谱、
Agent 结果都会按当前用户的 `max_classification_level` 与 `domain_scope` 过滤，
拿不到超出自己权限范围的数据。

## 可选的外部模型接入

系统在没有配置真实 LLM/Embedding 服务时会自动降级为确定性的规则/摘要实现，
接口始终可用，但生成质量有限。要接入真实模型，在 `.env` 或 backend 的环境变量中设置：

```
LLM_ENDPOINT=<OpenAI 兼容的 chat completions 端点>
LLM_API_KEY=<key>
EMBEDDING_ENDPOINT=<OpenAI 兼容的 embeddings 端点>
```

## 目录结构

```
backend/    FastAPI 后端（见 backend/app/services/ 下按模块划分的路由与服务层）
frontend/   React + TanStack Router 前端
docker-compose.yml   本地/单机部署编排
```

## 开发

```bash
cd backend && pip install -e ".[dev]" && pytest
cd frontend && npm install && npm run build
```

## 安全提示

- `deploy_config.py` 及根目录若干运维脚本从环境变量读取部署凭据，不要把真实凭据写回代码提交到 git。
- `.gitignore` 已排除 `.env`；不要绕过它提交真实密钥。
- 生产环境建议关闭 `/docs`（设置 `EXPOSE_API_DOCS=false`），并把 `CORS_ORIGINS` 收紧为实际前端域名。
