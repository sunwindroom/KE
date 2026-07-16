# PHM领域知识工程与智能知识库系统接口文档

**文档编号：** IFD-KE-2026-001
**版本：** V1.0
**编制日期：** 2026年7月
**上游依据：** 需求规格说明书（SRS-KE-2026-001）、架构设计文档（ADD-KE-2026-001）、详细设计文档（DDD-KE-2026-001）

---

## 修订记录

| 版本 | 日期 | 修订内容 |
|---|---|---|
| V1.0 | 2026-07 | 初稿创建 |

---

## 目录

1. 引言
2. 接口设计总则
3. 通用规范（认证、请求/响应格式、错误码）
4. 接口清单总览
5. 数据接入类接口
6. 知识检索与查询类接口
7. 知识问答（RAG）类接口
8. Agent智能体类接口
9. 知识运营与治理类接口
10. 知识图谱类接口
11. 系统管理与权限类接口
12. 外部业务系统集成接口
13. Webhook与异步通知机制
14. 接口版本管理与变更策略

---

## 1. 引言

### 1.1 编写目的

本文档定义本系统对内（各微服务间）、对外（业务系统集成、开放API）的接口规范，包括接口协议、请求/响应格式、字段定义、错误码，作为前后端联调、系统集成、第三方对接的统一依据。

### 1.2 适用范围

适用于本系统各微服务开发人员、业务系统集成人员、以及需要调用知识服务能力的外部系统开发团队。

---

## 2. 接口设计总则

- 统一采用 **RESTful风格API**，特殊场景（如高频流式问答）采用 **流式响应（SSE/WebSocket）**；
- 所有接口须经过统一API网关，网关负责鉴权、限流、日志记录、密级过滤前置校验；
- 接口版本通过URL路径体现（如 `/api/v1/...`），保证向后兼容性演进；
- 涉及敏感数据的接口，须在网关层与业务层双重校验用户权限（角色权限+领域权限+密级权限）。

---

## 3. 通用规范

### 3.1 认证方式

系统采用 **OAuth2.0 / JWT Token** 认证机制，与公司统一身份认证系统（SSO）集成。

**请求头示例：**

```
Authorization: Bearer <access_token>
Content-Type: application/json
X-Request-Id: <请求追踪ID，用于日志关联>
```

### 3.2 通用响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { },
  "request_id": "string",
  "timestamp": "2026-07-08T10:00:00Z"
}
```

| 字段 | 说明 |
|---|---|
| code | 业务状态码，0表示成功，非0参见错误码表 |
| message | 提示信息 |
| data | 业务数据主体 |
| request_id | 请求追踪ID，便于日志排查 |
| timestamp | 服务端响应时间戳 |

### 3.3 分页参数规范

```json
{
  "page": 1,
  "page_size": 20,
  "total": 123,
  "items": []
}
```

### 3.4 通用错误码

| 错误码 | 说明 |
|---|---|
| 0 | 成功 |
| 40001 | 参数校验失败 |
| 40100 | 未认证/Token失效 |
| 40300 | 无权限访问（角色/领域/密级权限不足） |
| 40400 | 资源不存在 |
| 40900 | 资源冲突（如知识条目正在审核中不可重复提交） |
| 42900 | 请求频率超限 |
| 50000 | 服务器内部错误 |
| 50300 | 依赖服务不可用（如大模型推理服务超时） |
| 50301 | 检索结果为空，无法生成可靠回答 |

---

## 4. 接口清单总览

| 分类 | 接口数量（首期） | 说明 |
|---|---|---|
| 数据接入类 | 5 | 文档/数据/专家录入接入 |
| 知识检索与查询类 | 6 | 关键词/语义/图谱检索 |
| 知识问答（RAG）类 | 4 | 智能问答、反馈 |
| Agent智能体类 | 4 | 任务提交、执行状态查询、结果获取、人工确认 |
| 知识运营与治理类 | 8 | 审核、版本、质量评估、统计 |
| 知识图谱类 | 5 | 图谱查询、可视化数据、本体管理 |
| 系统管理与权限类 | 6 | 用户、角色、权限、日志 |
| 外部业务系统集成类 | 4 | 面向PHM业务系统的知识服务开放接口 |

（以上为首期规划接口数量示意，实际以详细设计评审结果为准）

---

## 5. 数据接入类接口

### 5.1 文档上传接入

**接口地址：** `POST /api/v1/ingestion/document`

**请求参数（multipart/form-data）：**

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | file | 是 | 文档文件 |
| domain | string | 是 | 所属领域（energy/transportation/aerospace/general） |
| classification_level | string | 是 | 密级标签 |
| project_id | string | 否 | 关联项目编号 |
| submitter_id | string | 是 | 提交人ID |

**响应示例：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "candidate_id": "KC202607080001",
    "status": "pending"
  }
}
```

### 5.2 专家在线知识录入

**接口地址：** `POST /api/v1/ingestion/expert-input`

**请求体：**

```json
{
  "domain": "aerospace",
  "type": "case",
  "title": "某型航空发动机振动异常故障案例",
  "content": {
    "equipment": "XX型航空发动机",
    "component": "高压压气机轴承",
    "symptom": "振动值超限，频谱出现特征峰",
    "diagnosis": "轴承磨损导致不平衡",
    "action": "更换轴承，返厂检测"
  },
  "classification_level": "internal",
  "submitter_id": "U10023"
}
```

**响应示例：**

```json
{
  "code": 0,
  "message": "success",
  "data": {"candidate_id": "KC202607080002", "status": "pending"}
}
```

### 5.3 数据库批量同步触发

**接口地址：** `POST /api/v1/ingestion/db-sync/trigger`

**请求体：**

```json
{"source_system": "legacy_fault_db", "sync_mode": "incremental", "domain": "energy"}
```

### 5.4 接入状态查询

**接口地址：** `GET /api/v1/ingestion/status/{candidate_id}`

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "candidate_id": "KC202607080001",
    "status": "processed",
    "extracted_knowledge_ids": ["K20260708001", "K20260708002"]
  }
}
```

### 5.5 死信队列（失败数据）查询

**接口地址：** `GET /api/v1/ingestion/dlq?domain=energy&page=1&page_size=20`

---

## 6. 知识检索与查询类接口

### 6.1 综合检索（关键词/多维度筛选）

**接口地址：** `GET /api/v1/knowledge/search`

**请求参数：**

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| keyword | string | 否 | 关键词 |
| domain | string | 否 | 领域筛选 |
| type | string | 否 | 知识类型筛选 |
| equipment_model | string | 否 | 装备型号筛选 |
| time_range | string | 否 | 时间范围（如2024-01~2026-06） |
| page / page_size | int | 否 | 分页参数 |

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "total": 15,
    "items": [
      {
        "knowledge_id": "K20250312007",
        "title": "某型燃气轮机叶片裂纹故障分析",
        "domain": "energy",
        "type": "case",
        "confidence": 0.92,
        "classification_level": "internal",
        "summary": "……"
      }
    ]
  }
}
```

### 6.2 语义检索

**接口地址：** `POST /api/v1/knowledge/semantic-search`

**请求体：**

```json
{"query": "轴承振动异常伴随温度升高可能的原因", "domain": "energy", "top_k": 10}
```

### 6.3 相似案例推荐

**接口地址：** `GET /api/v1/knowledge/{knowledge_id}/similar`

### 6.4 知识条目详情查询

**接口地址：** `GET /api/v1/knowledge/{knowledge_id}`

### 6.5 知识条目版本历史查询

**接口地址：** `GET /api/v1/knowledge/{knowledge_id}/versions`

### 6.6 结构化规则/参数查询

**接口地址：** `GET /api/v1/knowledge/rules?failure_mode=轴承磨损&domain=energy`

---

## 7. 知识问答（RAG）类接口

### 7.1 智能问答（同步）

**接口地址：** `POST /api/v1/qa/ask`

**请求体：**

```json
{
  "session_id": "S20260708-001",
  "question": "某型风电机组齿轮箱异响，可能的故障原因及处置建议是什么？",
  "domain": "energy"
}
```

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "answer": "根据知识库中相关案例与诊断规则，齿轮箱异响可能原因包括……（具体内容省略）",
    "citations": [
      {"knowledge_id": "K20240521003", "title": "某型风电齿轮箱异响案例分析", "snippet_ref": "..."}
    ],
    "confidence_hint": "medium",
    "disclaimer": "本回答为知识库辅助生成，涉及安全关键判断请以专家复核结论为准"
  }
}
```

### 7.2 智能问答（流式）

**接口地址：** `POST /api/v1/qa/ask-stream`（SSE流式响应）

**说明：** 响应通过Server-Sent Events逐步返回生成内容片段，前端逐字展示，最终事件携带完整引用信息。

### 7.3 问答反馈提交

**接口地址：** `POST /api/v1/qa/feedback`

```json
{"session_id": "S20260708-001", "message_id": "M0001", "helpful": false, "comment": "回答未覆盖新型齿轮箱型号情况"}
```

### 7.4 历史会话查询

**接口地址：** `GET /api/v1/qa/sessions/{session_id}`

---

## 8. Agent智能体类接口

### 8.1 提交Agent任务

**接口地址：** `POST /api/v1/agent/task/submit`

**请求体：**

```json
{
  "agent_type": "fault_diagnosis_assist",
  "input": {
    "equipment_model": "XX型航空发动机",
    "symptom_description": "起飞阶段振动值瞬时超限并伴随温度异常"
  },
  "domain": "aerospace",
  "submitter_id": "U10088"
}
```

**响应示例：**

```json
{"code": 0, "data": {"task_id": "AG20260708001", "status": "running"}}
```

### 8.2 查询Agent任务执行状态

**接口地址：** `GET /api/v1/agent/task/{task_id}/status`

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "task_id": "AG20260708001",
    "status": "waiting_confirmation",
    "current_step": "根因假设已生成，等待专家确认"
  }
}
```

### 8.3 获取Agent执行轨迹与结果

**接口地址：** `GET /api/v1/agent/task/{task_id}/result`

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "task_id": "AG20260708001",
    "trace": [
      {"step": 1, "action": "检索历史相似案例", "output_ref": "..."},
      {"step": 2, "action": "图谱查询关联故障模式", "output_ref": "..."}
    ],
    "final_result": {
      "possible_causes": ["轴承磨损", "转子不平衡"],
      "recommended_actions": ["……"],
      "confidence_hint": "low",
      "human_confirmation_required": true
    }
  }
}
```

### 8.4 人工确认Agent关键节点

**接口地址：** `POST /api/v1/agent/task/{task_id}/confirm`

```json
{"confirmer_id": "U10001", "decision": "approved", "comment": "根因假设合理，建议进一步返厂检测确认"}
```

---

## 9. 知识运营与治理类接口

### 9.1 提交知识审核

**接口地址：** `POST /api/v1/governance/review/{knowledge_id}/submit`

### 9.2 审核操作（通过/驳回）

**接口地址：** `POST /api/v1/governance/review/{knowledge_id}/action`

```json
{"reviewer_id": "U10005", "action": "approve", "comment": "内容准确，符合入库标准"}
```

### 9.3 知识冲突仲裁

**接口地址：** `POST /api/v1/governance/conflict/{conflict_id}/resolve`

```json
{"resolver_id": "U10009", "resolution": "keep_new", "comment": "新提交案例数据来源更可靠，予以采纳"}
```

### 9.4 知识质量评估任务查询

**接口地址：** `GET /api/v1/governance/quality-check?status=pending_review`

### 9.5 知识资产统计

**接口地址：** `GET /api/v1/governance/stats/overview`

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "total_knowledge_count": 12500,
    "by_domain": {"energy": 4800, "transportation": 3200, "aerospace": 4000, "general": 500},
    "growth_last_30_days": 320
  }
}
```

### 9.6 专家贡献度排行

**接口地址：** `GET /api/v1/governance/stats/contribution-rank`

### 9.7 知识使用效果统计

**接口地址：** `GET /api/v1/governance/stats/usage`

### 9.8 待复核提醒清单

**接口地址：** `GET /api/v1/governance/review-reminders`

---

## 10. 知识图谱类接口

### 10.1 实体详情与关联查询

**接口地址：** `GET /api/v1/graph/entity/{entity_id}`

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "entity_id": "E20260001",
    "name": "高压压气机轴承",
    "type": "Component",
    "relations": [
      {"relation": "OCCURS_IN", "target": "轴承磨损", "target_type": "FailureMode"}
    ]
  }
}
```

### 10.2 多跳路径查询

**接口地址：** `POST /api/v1/graph/path-query`

```json
{"start_entity": "轴承磨损", "relation_pattern": "LEADS_TO", "max_hop": 3}
```

### 10.3 子图查询（可视化用）

**接口地址：** `GET /api/v1/graph/subgraph?center_entity=E20260001&depth=2`

### 10.4 本体定义查询

**接口地址：** `GET /api/v1/ontology/schema?domain=aerospace`

### 10.5 本体变更提交（专家/知识工程师）

**接口地址：** `POST /api/v1/ontology/change-request`

---

## 11. 系统管理与权限类接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/admin/users` | GET/POST | 用户列表查询/创建 |
| `/api/v1/admin/users/{user_id}/role` | PUT | 角色分配 |
| `/api/v1/admin/users/{user_id}/permission` | PUT | 领域/密级权限配置 |
| `/api/v1/admin/audit-logs` | GET | 审计日志查询 |
| `/api/v1/admin/system/monitor` | GET | 系统监控指标查询 |
| `/api/v1/admin/model/registry` | GET | 模型版本列表查询 |

---

## 12. 外部业务系统集成接口

面向公司现有PHM业务系统（故障诊断系统、健康评估系统、寿命预测系统、维修决策支持系统）提供的开放API，需通过API网关申请集成密钥（App Key/Secret）。

### 12.1 故障模式库查询（供故障诊断系统调用）

**接口地址：** `GET /api/v1/open/failure-modes?component=齿轮箱&domain=energy`

### 12.2 诊断规则查询（供诊断系统调用）

**接口地址：** `GET /api/v1/open/diagnosis-rules?symptom=振动超限`

### 12.3 相似案例查询（供健康评估/维修决策系统调用）

**接口地址：** `POST /api/v1/open/similar-cases`

```json
{"equipment_model": "XX型风电机组", "symptom_description": "齿轮箱油温异常升高", "top_k": 5}
```

### 12.4 业务系统结果反哺接口（诊断结论/复核结果回流知识库）

**接口地址：** `POST /api/v1/open/feedback-case`

```json
{
  "source_system": "fault_diagnosis_system",
  "equipment_id": "EQ20260099",
  "diagnosis_result": "确认为轴承内圈剥落",
  "expert_confirmed": true,
  "submitter_id": "SYS_FDS"
}
```

**说明：** 该接口用于将业务系统产生的经过专家复核的诊断结论回流至知识加工层，触发新一轮知识入库流程（进入待审核队列，而非直接自动发布）。

---

## 13. Webhook与异步通知机制

对于处理耗时较长的任务（如批量文档解析、Agent复杂任务、模型微调），系统支持Webhook异步通知：

**注册Webhook：** `POST /api/v1/notify/webhook/register`

```json
{"event_type": "ingestion.completed", "callback_url": "https://caller-system.internal/callback", "secret": "***"}
```

**通知负载示例：**

```json
{
  "event_type": "ingestion.completed",
  "candidate_id": "KC202607080001",
  "status": "processed",
  "timestamp": "2026-07-08T10:30:00Z",
  "sign": "HMAC签名，供接收方校验来源合法性"
}
```

支持的事件类型包括：`ingestion.completed`、`ingestion.failed`、`review.completed`、`agent_task.completed`、`agent_task.needs_confirmation`、`finetune.completed`。

---

## 14. 接口版本管理与变更策略

- 接口版本通过URL路径管理（`/api/v1/`、`/api/v2/`），不兼容变更须发布新版本，旧版本按约定周期（建议至少6个月）保留兼容运行；
- 新增字段遵循向后兼容原则（不删除、不修改已有字段语义）；
- 重大接口变更须提前通知所有已知调用方（内部业务系统、外部集成方），并更新本文档版本记录；
- 涉及密级/权限相关的接口调整，须额外履行安全评审流程。

---

*本文档为接口设计初版，具体字段与接口清单将在开发联调阶段根据实际实现情况同步更新，重大变更需履行版本评审流程。*
