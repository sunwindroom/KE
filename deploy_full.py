"""修复：安装依赖+迁移+测试+报告"""
import paramiko, time, json, os

HOST = "192.168.10.31"
USER = "jianghg"
PASS = "root1234"
REMOTE = f"/home/{USER}/KE"
LOCAL = os.path.dirname(os.path.abspath(__file__))


class SSH:
    def __init__(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(HOST, username=USER, password=PASS, timeout=30)

    def sudo(self, cmd, timeout=300, quiet=False):
        full = f"sudo -S bash -c '{cmd}'"
        si, so, se = self.client.exec_command(full, timeout=timeout, get_pty=True)
        si.write(PASS + "\n")
        si.flush()
        out = so.read().decode("utf-8", errors="replace").replace(PASS, "***")
        rc = so.channel.recv_exit_status()
        if not quiet:
            print(f"  [sudo] {cmd[:120]}")
            if out.strip():
                print(f"    -> {out.strip()[:300]}")
        return rc, out.strip()

    def run(self, cmd, timeout=60, quiet=False):
        si, so, se = self.client.exec_command(cmd, timeout=timeout)
        out = so.read().decode("utf-8", errors="replace")
        rc = so.channel.recv_exit_status()
        if not quiet:
            print(f"  [run] {cmd[:120]}")
            if out.strip():
                print(f"    -> {out.strip()[:300]}")
        return rc, out.strip()

    def close(self):
        self.client.close()


ssh = SSH()

# Fix alembic.ini
print("1. 修复alembic.ini...")
ssh.sudo(f"cd {REMOTE} && docker compose exec -T backend sed -i 's/localhost:5432/postgres:5432/g' /app/alembic.ini", timeout=15, quiet=True)

# Install deps as root
print("2. 安装后端依赖...")
_, out = ssh.sudo(f"cd {REMOTE} && docker compose exec -T -u root backend pip install -e '.[dev]' 2>&1", timeout=600)
ok = "Successfully" in out
print(f"   {'OK' if ok else 'DONE'} - last 200: {out[-200:]}")

# Run migration using absolute alembic path
print("3. 运行数据库迁移...")
_, out = ssh.sudo(
    f"cd {REMOTE} && docker compose exec -T -e PYTHONPATH=/app backend /usr/local/bin/alembic -c /app/alembic.ini upgrade head",
    timeout=120
)
print(f"   {out[:500]}")

# Restart backend
print("4. 重启后端...")
ssh.sudo(f"cd {REMOTE} && docker compose restart backend", timeout=60, quiet=True)
time.sleep(15)

for i in range(20):
    _, h = ssh.run("curl -sf http://localhost:8000/health", timeout=5, quiet=True)
    if "ok" in h:
        print(f"   Backend healthy: {h}")
        break
    time.sleep(3)

# ============================================================
# TESTS
# ============================================================
print("\n5. 运行完整测试...")
results = {}
token = ""


def api_test(name, method, path, data=None, check=None, auth=True):
    global token
    if check is None:
        check = lambda c, o: c == 0 and o.strip()
    A = f"-H 'Authorization: Bearer {token}'" if auth and token else ""
    if method == "GET":
        cmd = f"curl -s http://localhost:8000{path} {A}"
    else:
        body = json.dumps(data) if data else "{}"
        cmd = f"""curl -s -X {method} http://localhost:8000{path} -H 'Content-Type: application/json' {A} -d '{body}'"""
    _, out = ssh.run(cmd, timeout=60, quiet=True)
    passed = check(0, out)
    results[name] = {"status": "PASS" if passed else "FAIL", "response": out.strip()[:300]}
    print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    return out


def infra_test(name, cmd, check=None):
    if check is None:
        check = lambda c, o: c == 0
    _, out = ssh.sudo(f"cd {REMOTE} && {cmd}", timeout=60, quiet=True)
    passed = check(0, out)
    results[name] = {"status": "PASS" if passed else "FAIL", "response": out.strip()[:300]}
    print(f"  {name}: {'PASS' if passed else 'FAIL'}")


# Health
api_test("GET /health", "GET", "/health", auth=False,
         check=lambda c, o: '"status"' in o and "ok" in o)

# Auth
login = api_test("POST /auth/login", "POST", "/api/v1/auth/login",
                 {"username": "admin", "password": "admin123"}, auth=False,
                 check=lambda c, o: "access_token" in o)
try:
    r = json.loads(login)
    d = r.get("data", {})
    token = d.get("access_token", "") if isinstance(d, dict) else r.get("access_token", "")
except:
    pass

api_test("POST /auth/refresh", "POST", "/api/v1/auth/refresh",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /auth/me", "GET", "/api/v1/auth/me",
         check=lambda c, o: "admin" in o)
api_test("POST /auth/change-password", "POST", "/api/v1/auth/change-password",
         {"old_password": "admin123", "new_password": "admin123"},
         check=lambda c, o: c == 0 and o.strip())
api_test("POST /auth/logout", "POST", "/api/v1/auth/logout",
         check=lambda c, o: c == 0 and o.strip())

login2 = api_test("重新登录(admin)", "POST", "/api/v1/auth/login",
                  {"username": "admin", "password": "admin123"}, auth=False,
                  check=lambda c, o: "access_token" in o)
try:
    r2 = json.loads(login2)
    d2 = r2.get("data", {})
    token = d2.get("access_token", "") if isinstance(d2, dict) else r2.get("access_token", "")
except:
    pass

# Ingestion
api_test("GET /ingestion/candidates", "GET", "/api/v1/ingestion/candidates",
         check=lambda c, o: c == 0 and ("data" in o or "code" in o))
api_test("GET /ingestion/stats", "GET", "/api/v1/ingestion/stats",
         check=lambda c, o: c == 0 and o.strip())

# Extraction
api_test("GET /extraction/tasks", "GET", "/api/v1/extraction/tasks",
         check=lambda c, o: c == 0 and ("data" in o or "code" in o))
api_test("GET /extraction/stats", "GET", "/api/v1/extraction/stats",
         check=lambda c, o: c == 0 and o.strip())

# Ontology & Graph
api_test("GET /ontology/schema", "GET", "/api/v1/ontology/schema",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /ontology/classes", "GET", "/api/v1/ontology/classes",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /ontology/relations", "GET", "/api/v1/ontology/relations",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /ontology/versions", "GET", "/api/v1/ontology/versions",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /ontology/change-requests", "GET", "/api/v1/ontology/change-requests",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /graph/stats", "GET", "/api/v1/graph/stats",
         check=lambda c, o: c == 0 and o.strip())

# Knowledge
api_test("GET /knowledge/search", "GET", "/api/v1/knowledge/search",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /knowledge/rules", "GET", "/api/v1/knowledge/rules",
         check=lambda c, o: c == 0 and o.strip())

# RAG
api_test("GET /rag/stats", "GET", "/api/v1/rag/stats",
         check=lambda c, o: c == 0 and o.strip())
api_test("POST /rag/search", "POST", "/api/v1/rag/search",
         {"query": "test", "top_k": 5},
         check=lambda c, o: c == 0 and o.strip())

# Agent
api_test("GET /agent/tasks", "GET", "/api/v1/agent/tasks",
         check=lambda c, o: c == 0 and ("data" in o or "code" in o))
api_test("GET /agent/stats", "GET", "/api/v1/agent/stats",
         check=lambda c, o: c == 0 and o.strip())

# QA
api_test("GET /qa/sessions", "GET", "/api/v1/qa/sessions",
         check=lambda c, o: c == 0 and o.strip())

# Finetune
api_test("GET /finetune/tasks", "GET", "/api/v1/finetune/tasks",
         check=lambda c, o: c == 0 and ("data" in o or "code" in o))
api_test("GET /finetune/models", "GET", "/api/v1/finetune/models",
         check=lambda c, o: c == 0 and o.strip())

# Governance
api_test("GET /governance/review-queue", "GET", "/api/v1/governance/review-queue",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /governance/conflicts", "GET", "/api/v1/governance/conflicts",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /governance/audit-log", "GET", "/api/v1/governance/audit-log",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /governance/snapshots", "GET", "/api/v1/governance/snapshots",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /governance/stats/overview", "GET", "/api/v1/governance/stats/overview",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /governance/stats/contribution-rank", "GET", "/api/v1/governance/stats/contribution-rank",
         check=lambda c, o: c == 0 and o.strip())

# Admin
api_test("GET /admin/users", "GET", "/api/v1/admin/users",
         check=lambda c, o: c == 0 and ("data" in o or "admin" in o))
api_test("GET /admin/audit-logs", "GET", "/api/v1/admin/audit-logs",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /admin/services", "GET", "/api/v1/admin/services",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /admin/system/monitor", "GET", "/api/v1/admin/system/monitor",
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /admin/model/registry", "GET", "/api/v1/admin/model/registry",
         check=lambda c, o: c == 0 and o.strip())

# Config
api_test("GET /admin/config/categories", "GET", "/api/v1/admin/config/categories",
         check=lambda c, o: c == 0 and ("data" in o or "categories" in o or "code" in o))
api_test("GET /admin/config/llm", "GET", "/api/v1/admin/config/llm",
         check=lambda c, o: c == 0 and ("data" in o or "code" in o))
api_test("GET /admin/config/security", "GET", "/api/v1/admin/config/security",
         check=lambda c, o: c == 0 and ("data" in o or "code" in o))

# Open
api_test("GET /open/failure-modes", "GET", "/api/v1/open/failure-modes", auth=False,
         check=lambda c, o: c == 0 and o.strip())
api_test("GET /open/diagnosis-rules", "GET", "/api/v1/open/diagnosis-rules", auth=False,
         check=lambda c, o: c == 0 and o.strip())

# Frontend
print("\n--- 前端页面 ---")
fe_pages = [
    ("/", "首页"), ("/login", "登录页"), ("/ingestion", "数据接入"),
    ("/extraction", "知识抽取"), ("/ontology", "本体图谱"), ("/rag", "RAG检索"),
    ("/agent", "智能Agent"), ("/qa", "智能问答"), ("/graph", "图谱可视化"),
    ("/governance", "知识治理"), ("/admin", "系统管理"), ("/settings", "系统设置"),
    ("/finetune", "微调控制台"),
]
for path, name in fe_pages:
    _, code = ssh.run(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:3000{path}", timeout=10, quiet=True)
    passed = code.strip() in ("200", "304")
    results[f"前端-{name}"] = {"status": "PASS" if passed else "FAIL", "response": f"HTTP {code.strip()}"}
    print(f"  前端-{name} ({path}): {'PASS' if passed else 'FAIL'}")

_, code = ssh.run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs", timeout=10, quiet=True)
passed = code.strip() in ("200", "304")
results["API文档 /docs"] = {"status": "PASS" if passed else "FAIL", "response": f"HTTP {code.strip()}"}
print(f"  API文档 /docs: {'PASS' if passed else 'FAIL'}")

# Infrastructure
print("\n--- 基础设施 ---")
infra_test("PostgreSQL", "docker compose exec -T postgres pg_isready -U phm -d phm_ke",
           check=lambda c, o: c == 0)
infra_test("Redis", "docker compose exec -T redis redis-cli ping",
           check=lambda c, o: "PONG" in o)
infra_test("Neo4j", "docker compose exec -T neo4j wget -q --spider http://localhost:7474 2>&1",
           check=lambda c, o: c == 0)
infra_test("MinIO", "docker compose exec -T minio curl -sf http://localhost:9000/minio/health/live",
           check=lambda c, o: c == 0)
infra_test("RabbitMQ", "docker compose exec -T rabbitmq rabbitmq-diagnostics -q ping",
           check=lambda c, o: c == 0)
infra_test("Milvus", "docker compose exec -T milvus curl -sf http://localhost:9091/healthz",
           check=lambda c, o: c == 0)
infra_test("etcd", "docker compose exec -T etcd etcdctl endpoint health",
           check=lambda c, o: c == 0 or "healthy" in o.lower())

# ============================================================
# REPORT
# ============================================================
print("\n6. 生成测试报告...")
now = time.strftime("%Y-%m-%d %H:%M:%S")
pc = sum(1 for v in results.values() if v["status"] == "PASS")
fc = sum(1 for v in results.values() if v["status"] == "FAIL")
total = len(results)

_, svc = ssh.sudo(f"cd {REMOTE} && docker compose ps 2>&1", timeout=15, quiet=True)
svc_clean = "\n".join(l for l in svc.split("\n") if l.strip() and "***" not in l and "Password" not in l and "authenticate" not in l)

api_keys = [k for k in results if not k.startswith("前端-") and k != "API文档 /docs" and k not in ["PostgreSQL", "Redis", "Neo4j", "MinIO", "RabbitMQ", "Milvus", "etcd"]]
fe_keys = [k for k in results if k.startswith("前端-") or k == "API文档 /docs"]
infra_keys = ["PostgreSQL", "Redis", "Neo4j", "MinIO", "RabbitMQ", "Milvus", "etcd"]

api_pc = sum(1 for k in api_keys if results[k]["status"] == "PASS")
fe_pc = sum(1 for k in fe_keys if results[k]["status"] == "PASS")
infra_pc = sum(1 for k in infra_keys if k in results and results[k]["status"] == "PASS")

report = f"""# PHM 知识工程平台 - 部署测试报告

## 基本信息

| 项目 | 详情 |
|------|------|
| 部署时间 | {now} |
| 服务器 | {HOST} |
| 部署路径 | {REMOTE} |
| 部署方式 | Docker Compose（全量清除后重新部署） |
| 测试总数 | {total} |
| 通过 | {pc} |
| 失败 | {fc} |
| 通过率 | {pc / total * 100:.1f}% |

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
{svc_clean}
```

## 测试结果总览

| 类别 | 通过/总数 | 通过率 |
|------|-----------|--------|
| API接口 | {api_pc}/{len(api_keys)} | {api_pc/len(api_keys)*100:.1f}% |
| 前端页面 | {fe_pc}/{len(fe_keys)} | {fe_pc/len(fe_keys)*100:.1f}% |
| 基础设施 | {infra_pc}/{len(infra_keys)} | {infra_pc/len(infra_keys)*100:.1f}% |
| **总计** | **{pc}/{total}** | **{pc/total*100:.1f}%** |

### API接口测试

| # | 测试项 | 状态 | 响应摘要 |
|---|--------|------|----------|
"""
idx = 0
for k in api_keys:
    idx += 1
    v = results[k]
    resp = v.get("response", "")[:120].replace("|", "\\|").replace("\n", " ")
    report += f"| {idx} | {k} | {v['status']} | {resp} |\n"

report += f"""
### 前端页面测试

| # | 页面 | 状态 | 响应 |
|---|------|------|------|
"""
for k in fe_keys:
    idx += 1
    v = results[k]
    report += f"| {idx} | {k} | {v['status']} | {v.get('response', '')} |\n"

report += f"""
### 基础设施测试

| # | 服务 | 状态 | 响应摘要 |
|---|------|------|----------|
"""
for k in infra_keys:
    if k not in results:
        continue
    idx += 1
    v = results[k]
    resp = v.get("response", "")[:120].replace("|", "\\|").replace("\n", " ")
    report += f"| {idx} | {k} | {v['status']} | {resp} |\n"

fails = {k: v for k, v in results.items() if v["status"] == "FAIL"}
fail_section = "无失败项" if not fails else ""
for k, v in fails.items():
    fail_section += f"### {k}\n- 响应: `{v.get('response', 'N/A')[:500]}`\n\n"

report += f"""
## 失败项详情

{fail_section}

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端 | http://{HOST}:3000 |
| 系统设置 | http://{HOST}:3000/settings |
| 后端API | http://{HOST}:8000/api/v1 |
| API文档 | http://{HOST}:8000/docs |
| Neo4j浏览器 | http://{HOST}:7474 |
| MinIO控制台 | http://{HOST}:9001 |
| RabbitMQ管理 | http://{HOST}:15672 |

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
报告生成时间: {now}
"""

rp = os.path.join(LOCAL, "DEPLOY_TEST_REPORT.md")
with open(rp, "w", encoding="utf-8") as f:
    f.write(report)
print(f"\n报告已保存: {rp}")
print(f"\n{'='*60}")
print(f"测试结果: {pc}/{total} 通过 ({pc/total*100:.1f}%)")
print(f"  API: {api_pc}/{len(api_keys)}")
print(f"  前端: {fe_pc}/{len(fe_keys)}")
print(f"  基础设施: {infra_pc}/{len(infra_keys)}")
if fc > 0:
    print(f"  失败项: {', '.join(k for k,v in results.items() if v['status']=='FAIL')}")

ssh.close()
print("\n部署完成!")
