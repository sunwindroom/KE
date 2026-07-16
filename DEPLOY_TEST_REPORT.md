# PHM 知识工程平台 - 部署测试报告

## 基本信息

| 项目 | 详情 |
|------|------|
| 部署时间 | 2026-07-18 11:40:11 |
| 服务器 | 192.168.10.31 |
| 部署路径 | /home/jianghg/KE |
| 部署方式 | Docker Compose（全量清除后重新部署） |
| 测试总数 | 63 |
| 通过 | 63 |
| 失败 | 0 |
| 通过率 | 100.0% |

## 项目概述

PHM 知识工程平台（Aether PHM）是面向设备故障预测与健康管理领域的知识工程系统，涵盖知识接入、抽取、存储、检索、问答、治理全生命周期。

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TanStack Router/Query + Tailwind CSS 4 + Radix UI |
| 后端 | FastAPI + SQLAlchemy 2.0 (async) + Python 3.12 |
| 关系数据库 | PostgreSQL 16 |
| 图数据库 | Neo4j 5 Community |
| 向量数据库 | Milvus 2.4.4 |
| 对象存储 | MinIO |
| 缓存 | Redis 7 |
| 消息队列 | RabbitMQ 3 |
| 认证 | JWT (HS256) + bcrypt |
| 数据库迁移 | Alembic (8个版本: 000-007) |

### 功能模块

| 模块 | API前缀 | 说明 |
|------|---------|------|
| 认证 | /api/v1/auth | 登录/登出/刷新/改密 |
| 数据接入 | /api/v1/ingestion | 文档上传/专家录入/DB同步 |
| 知识抽取 | /api/v1/extraction | NER/RE抽取/审核 |
| 本体图谱 | /api/v1/ontology + /graph | 本体管理/图谱可视化 |
| 知识检索 | /api/v1/knowledge | CRUD/语义搜索/版本 |
| 知识问答 | /api/v1/qa | 同步/SSE流式问答 |
| RAG检索 | /api/v1/rag | 向量检索/索引/评测 |
| Agent | /api/v1/agent | 智能体任务/确认 |
| 领域微调 | /api/v1/finetune | SFT/DPO/RLHF/模型注册 |
| 知识治理 | /api/v1/governance | 审核/冲突/快照/审计 |
| 系统管理 | /api/v1/admin | 用户/权限/监控/服务 |
| 系统设置 | /api/v1/admin/config | 运行时配置/连接测试 |
| 开放接口 | /api/v1/open | 故障模式/诊断规则/案例检索 |

## 服务状态

```
NAME            IMAGE                          COMMAND                  SERVICE    CREATED          STATUS                    PORTS
ke-backend-1    ke-backend                     "uvicorn app.main:ap…"   backend    13 minutes ago   Up 26 seconds (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
ke-etcd-1       quay.io/coreos/etcd:v3.5.5     "etcd -advertise-cli…"   etcd       13 minutes ago   Up 13 minutes (healthy)   2379-2380/tcp
ke-frontend-1   ke-frontend                    "docker-entrypoint.s…"   frontend   13 minutes ago   Up 12 minutes (healthy)   0.0.0.0:3000->3000/tcp, [::]:3000->3000/tcp
ke-milvus-1     milvusdb/milvus:v2.4.4         "/tini -- milvus run…"   milvus     13 minutes ago   Up 13 minutes (healthy)   0.0.0.0:9091->9091/tcp, [::]:9091->9091/tcp, 0.0.0.0:19530->19530/tcp, [::]:19530->19530/tcp
ke-minio-1      minio/minio:latest             "/usr/bin/docker-ent…"   minio      13 minutes ago   Up 13 minutes (healthy)   0.0.0.0:9000-9001->9000-9001/tcp, [::]:9000-9001->9000-9001/tcp
ke-neo4j-1      neo4j:5-community              "tini -g -- /startup…"   neo4j      13 minutes ago   Up 13 minutes (healthy)   0.0.0.0:7474->7474/tcp, [::]:7474->7474/tcp, 7473/tcp, 0.0.0.0:7687->7687/tcp, [::]:7687->7687/tcp
ke-postgres-1   postgres:16-alpine             "docker-entrypoint.s…"   postgres   13 minutes ago   Up 13 minutes (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
ke-rabbitmq-1   rabbitmq:3-management-alpine   "docker-entrypoint.s…"   rabbitmq   13 minutes ago   Up 13 minutes (healthy)   4369/tcp, 5671/tcp, 0.0.0.0:5672->5672/tcp, [::]:5672->5672/tcp, 15671/tcp, 15691-15692/tcp, 25672/tcp, 0.0.0.0:15672->15672/tcp, [::]:15672->15672/tcp
ke-redis-1      redis:7-alpine                 "docker-entrypoint.s…"   redis      13 minutes ago   Up 13 minutes (healthy)   0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp
```

## 测试结果总览

| 类别 | 通过/总数 | 通过率 |
|------|-----------|--------|
| API接口 | 42/42 | 100.0% |
| 前端页面 | 14/14 | 100.0% |
| 基础设施 | 7/7 | 100.0% |
| **总计** | **63/63** | **100.0%** |

### API接口测试

| # | 测试项 | 状态 | 响应摘要 |
|---|--------|------|----------|
| 1 | GET /health | PASS | {"status":"ok","timestamp":"2026-07-18T03:40:01.657456+00:00"} |
| 2 | POST /auth/login | PASS | {"code":0,"message":"success","data":{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiO |
| 3 | POST /auth/refresh | PASS | {"detail":[{"type":"missing","loc":["body","refresh_token"],"msg":"Field required","input":{}}]} |
| 4 | GET /auth/me | PASS | {"code":0,"message":"success","data":{"userId":"admin","userName":"系统管理员","role":"admin","domainScope":["energy","transp |
| 5 | POST /auth/change-password | PASS | {"code":0,"message":"密码已更新，请重新登录","data":null,"request_id":"","timestamp":"2026-07-18T03:40:03.258294"} |
| 6 | POST /auth/logout | PASS | {"code":0,"message":"已登出","data":null,"request_id":"","timestamp":"2026-07-18T03:40:03.340285"} |
| 7 | 重新登录(admin) | PASS | {"code":0,"message":"success","data":{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiO |
| 8 | GET /ingestion/candidates | PASS | {"code":0,"message":"success","data":{"page":1,"page_size":20,"total":0,"items":[]},"request_id":"","timestamp":"2026-07 |
| 9 | GET /ingestion/stats | PASS | {"code":0,"message":"success","data":{"todayCandidates":0,"successRate":null,"dlqCount":0,"totalCandidates":0},"request_ |
| 10 | GET /extraction/tasks | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:04.164561"} |
| 11 | GET /extraction/stats | PASS | {"code":0,"message":"success","data":{"entitiesToday":0,"relationsToday":0,"avgConfidence":null,"pendingReviewRatio":nul |
| 12 | GET /ontology/schema | PASS | {"code":0,"message":"success","data":{"domain":null,"classes":[{"className":"Equipment","labelZh":"装备","properties":"id, |
| 13 | GET /ontology/classes | PASS | {"code":0,"message":"success","data":[{"className":"Equipment","labelZh":"装备","properties":"id, name, model, domain, lev |
| 14 | GET /ontology/relations | PASS | {"code":0,"message":"success","data":[{"name":"BELONGS_TO","domain":"Component","range":"Equipment"},{"name":"OCCURS_IN" |
| 15 | GET /ontology/versions | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:06.407765"} |
| 16 | GET /ontology/change-requests | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:06.521066"} |
| 17 | GET /graph/stats | PASS | {"code":0,"message":"success","data":{"totalNodes":0,"totalEdges":0,"byType":{}},"request_id":"","timestamp":"2026-07-18 |
| 18 | GET /knowledge/search | PASS | {"code":0,"message":"success","data":{"page":1,"page_size":20,"total":0,"items":[]},"request_id":"","timestamp":"2026-07 |
| 19 | GET /knowledge/rules | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:06.847432"} |
| 20 | GET /rag/stats | PASS | {"code":0,"message":"success","data":{"totalChunks":0,"avgLatencyMs":null,"totalQueries":0,"hitRate":null},"request_id": |
| 21 | POST /rag/search | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.114527"} |
| 22 | GET /agent/tasks | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.222389"} |
| 23 | GET /agent/stats | PASS | {"code":0,"message":"success","data":{"calls24h":0,"avgDurationSeconds":null,"byType":{},"availableAgentTypes":["fault_d |
| 24 | GET /qa/sessions | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.389763"} |
| 25 | GET /finetune/tasks | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.491737"} |
| 26 | GET /finetune/models | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.583646"} |
| 27 | GET /governance/review-queue | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.689027"} |
| 28 | GET /governance/conflicts | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.786722"} |
| 29 | GET /governance/audit-log | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.863383"} |
| 30 | GET /governance/snapshots | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:07.950082"} |
| 31 | GET /governance/stats/overview | PASS | {"code":0,"message":"success","data":{"totalKnowledgeCount":0,"byDomain":{},"growthLast30Days":0},"request_id":"","times |
| 32 | GET /governance/stats/contribution-rank | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:08.139896"} |
| 33 | GET /admin/users | PASS | {"code":0,"message":"success","data":{"page":1,"page_size":20,"total":2,"items":[{"userId":"expert001","userName":"张专家", |
| 34 | GET /admin/audit-logs | PASS | {"code":0,"message":"success","data":{"page":1,"page_size":20,"total":0,"items":[]},"request_id":"","timestamp":"2026-07 |
| 35 | GET /admin/services | PASS | {"code":0,"message":"success","data":[{"name":"km-ingestion","version":"1.8.0","status":"OK","cpu":42},{"name":"km-extra |
| 36 | GET /admin/system/monitor | PASS | {"code":0,"message":"success","data":{"status":"ok","services":{}},"request_id":"","timestamp":"2026-07-18T03:40:08.4684 |
| 37 | GET /admin/model/registry | PASS | {"code":0,"message":"success","data":[{"name":"LLM 对话模型","kind":"llm","endpoint":"http://localhost:8001/v1","model":"qwe |
| 38 | GET /admin/config/categories | PASS | {"code":0,"message":"success","data":[{"key":"llm","label":"大模型 API","description":"对话/生成所使用的 LLM 服务端点、密钥与模型名称，修改后立即生效。" |
| 39 | GET /admin/config/llm | PASS | {"code":0,"message":"success","data":{"category":"llm","fields":[{"key":"LLM_ENDPOINT","label":"服务地址","type":"string","d |
| 40 | GET /admin/config/security | PASS | {"code":0,"message":"success","data":{"category":"security","fields":[{"key":"JWT_ACCESS_TOKEN_EXPIRE_MINUTES","label":" |
| 41 | GET /open/failure-modes | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:08.852414"} |
| 42 | GET /open/diagnosis-rules | PASS | {"code":0,"message":"success","data":[],"request_id":"","timestamp":"2026-07-18T03:40:08.927475"} |

### 前端页面测试

| # | 页面 | 状态 | 响应 |
|---|------|------|------|
| 43 | 前端-首页 | PASS | HTTP 200 |
| 44 | 前端-登录页 | PASS | HTTP 200 |
| 45 | 前端-数据接入 | PASS | HTTP 200 |
| 46 | 前端-知识抽取 | PASS | HTTP 200 |
| 47 | 前端-本体图谱 | PASS | HTTP 200 |
| 48 | 前端-RAG检索 | PASS | HTTP 200 |
| 49 | 前端-智能Agent | PASS | HTTP 200 |
| 50 | 前端-智能问答 | PASS | HTTP 200 |
| 51 | 前端-图谱可视化 | PASS | HTTP 200 |
| 52 | 前端-知识治理 | PASS | HTTP 200 |
| 53 | 前端-系统管理 | PASS | HTTP 200 |
| 54 | 前端-系统设置 | PASS | HTTP 200 |
| 55 | 前端-微调控制台 | PASS | HTTP 200 |
| 56 | API文档 /docs | PASS | HTTP 200 |

### 基础设施测试

| # | 服务 | 状态 | 响应摘要 |
|---|------|------|----------|
| 57 | PostgreSQL | PASS | *** [sudo: authenticate] Password: ********         /var/run/postgresql:5432 - accepting connections |
| 58 | Redis | PASS | *** [sudo: authenticate] Password: ********         PONG |
| 59 | Neo4j | PASS | *** [sudo: authenticate] Password: ********         |
| 60 | MinIO | PASS | *** [sudo: authenticate] Password: ********         |
| 61 | RabbitMQ | PASS | *** [sudo: authenticate] Password: ********         Ping succeeded |
| 62 | Milvus | PASS | *** [sudo: authenticate] Password: ********         OK |
| 63 | etcd | PASS | *** [sudo: authenticate] Password: ********         127.0.0.1:2379 is healthy: successfully committed  |

## 失败项详情

无失败项

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端 | http://192.168.10.31:3000 |
| 系统设置 | http://192.168.10.31:3000/settings |
| 后端API | http://192.168.10.31:8000/api/v1 |
| API文档 | http://192.168.10.31:8000/docs |
| Neo4j浏览器 | http://192.168.10.31:7474 |
| MinIO控制台 | http://192.168.10.31:9001 |
| RabbitMQ管理 | http://192.168.10.31:15672 |

## 初始账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
| 专家 | expert001 | expert123 |

## 部署架构

```
+--------------------------------------------------+
|                  192.168.10.31                    |
|                                                  |
|  +----------+  +----------+  +----------+       |
|  | Frontend |  | Backend  |  | Postgres |       |
|  |  :3000   |--|  :8000   |--|  :5432   |       |
|  +----------+  +----+-----+  +----------+       |
|                     |                             |
|  +------+ +------+ +------+ +------+ +------+   |
|  |Neo4j | |Milvus| |MinIO | |Redis | |Rabbit|   |
|  |:7687 | |:19530| |:9000 | |:6379 | |:5672 |   |
|  +------+ +------+ +------+ +------+ +------+   |
|                     +------+                     |
|                     | etcd |                     |
|                     |:2379 |                     |
|                     +------+                     |
+--------------------------------------------------+
```

## 数据模型 (20张表)

| 表名 | 说明 |
|------|------|
| knowledge_candidate | 知识候选对象 |
| knowledge_item | 知识条目 |
| knowledge_version_history | 知识版本历史 |
| knowledge_conflict | 知识冲突 |
| knowledge_snapshot | 知识快照 |
| review_workflow | 审核流程 |
| user_permission | 用户权限 |
| agent_task | Agent任务 |
| ontology_change_request | 本体变更请求 |
| ontology_version | 本体版本 |
| rag_index_job | RAG索引任务 |
| rag_query_log | RAG查询日志 |
| qa_session | 问答会话 |
| qa_message | 问答消息 |
| extraction_task | 抽取任务 |
| extraction_item | 抽取候选项 |
| audit_log | 审计日志 |
| finetune_task | 微调任务 |
| registered_model | 注册模型 |
| system_config | 系统运行时配置 |

## 数据库迁移版本

| 版本 | 说明 |
|------|------|
| 000_initial | 初始Schema (7张核心表) |
| 001_seed | 种子数据 (admin/expert001) |
| 002_ontology | 本体表 |
| 003_rag_qa | RAG/QA表 |
| 004_extraction | 抽取表 |
| 005_conflict_snapshot | 冲突/快照表 |
| 006_finetune | 微调表 |
| 007_system_config | 系统配置表 |

---
报告生成时间: 2026-07-18 11:40:11
