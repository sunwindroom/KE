# PHM领域知识工程与智能知识库系统详细设计文档

**文档编号：** DDD-KE-2026-001
**版本：** V1.0
**编制日期：** 2026年7月
**上游依据：** 需求规格说明书（SRS-KE-2026-001）、系统架构设计文档（ADD-KE-2026-001）

---

## 修订记录

| 版本 | 日期 | 修订内容 |
|---|---|---|
| V1.0 | 2026-07 | 初稿创建 |

---

## 目录

1. 引言
2. 模块划分总览
3. 数据接入模块详细设计
4. 知识抽取与加工模块详细设计
5. 本体与知识图谱模块详细设计
6. 知识存储模块详细设计（含数据库表结构设计）
7. RAG检索增强模块详细设计
8. Agent智能体模块详细设计
9. 领域微调模块详细设计
10. 知识问答与检索应用模块详细设计
11. 知识图谱可视化模块详细设计
12. 知识运营与治理模块详细设计
13. 系统管理模块详细设计
14. 异常处理与容错设计
15. 关键业务流程时序设计

---

## 1. 引言

### 1.1 编写目的

本文档在架构设计基础上，对各功能模块进行详细设计，明确模块内部结构、核心类/服务划分、数据库表结构、核心处理流程与算法逻辑，作为编码实现的直接依据。

### 1.2 设计约定

- 模块命名统一采用"业务域-功能"命名规范（如 `km-extraction-service` 表示知识加工域-抽取服务）；
- 各微服务对外统一通过知识服务层封装的接口交互，禁止跨层直接访问底层存储；
- 涉及密级过滤的查询，须在服务入口统一注入权限上下文（`SecurityContext`），不得在业务逻辑内部零散实现。

---

## 2. 模块划分总览

| 模块编号 | 模块名称 | 对应架构层 |
|---|---|---|
| M01 | 数据接入模块 | 数据接入层 |
| M02 | 知识抽取与加工模块 | 知识加工层 |
| M03 | 本体与知识图谱模块 | 知识加工层/知识存储层 |
| M04 | 知识存储模块 | 知识存储层 |
| M05 | RAG检索增强模块 | 模型与智能编排层 |
| M06 | Agent智能体模块 | 模型与智能编排层 |
| M07 | 领域微调模块 | 模型与智能编排层 |
| M08 | 知识问答与检索应用模块 | 应用层 |
| M09 | 知识图谱可视化模块 | 应用层 |
| M10 | 知识运营与治理模块 | 知识服务层/应用层 |
| M11 | 系统管理模块 | 横向支撑 |

---

## 3. 数据接入模块详细设计（M01）

### 3.1 子组件划分

| 子组件 | 职责 |
|---|---|
| DocCollector | 文档采集（目录扫描、文档系统对接、邮件附件抓取） |
| DBSyncAgent | 数据库同步（历史台账、传感器数据CDC/批量同步） |
| ExpertInputAPI | 专家在线录入接口服务 |
| ExternalStandardConnector | 外部标准规范接入连接器 |
| IngestionQueueProducer | 统一将采集数据封装为知识候选对象，写入消息队列 |

### 3.2 核心数据结构：知识候选对象（KnowledgeCandidate）

```json
{
  "candidate_id": "string，唯一标识",
  "source_type": "enum: document|database|expert_input|external_standard",
  "domain": "enum: energy|transportation|aerospace|general",
  "raw_content": "原始内容（文本/文件引用）",
  "attachments": ["文件存储引用列表"],
  "source_meta": {
    "source_name": "来源名称（如文档名/系统名/专家姓名）",
    "project_id": "关联项目编号（可选）",
    "classification_level": "密级标签",
    "submit_time": "提交时间"
  },
  "status": "enum: pending|processing|processed|failed"
}
```

### 3.3 处理逻辑

1. 各采集子组件完成数据拉取后，统一调用 `IngestionQueueProducer.publish(candidate)` 写入消息队列 `topic: km.ingestion.raw`；
2. 采集失败/格式异常数据写入死信队列 `topic: km.ingestion.dlq`，供人工介入处理；
3. 密级标签在接入环节即完成初步标注（默认继承来源系统密级，允许人工在审核环节调整）。

### 3.4 接口设计要点（详见接口文档）

- `POST /api/v1/ingestion/document`：文档上传接入
- `POST /api/v1/ingestion/expert-input`：专家在线录入
- `GET /api/v1/ingestion/status/{candidate_id}`：接入状态查询

---

## 4. 知识抽取与加工模块详细设计（M02）

### 4.1 子组件划分

| 子组件 | 职责 |
|---|---|
| DocParser | 文档解析（PDF/Word/扫描件解析、OCR、表格抽取） |
| Chunker | 文本分块，控制单块长度适配大模型上下文窗口 |
| ExtractionEngine | 基于LLM+规则的实体/关系/事件抽取 |
| TermNormalizer | 术语标准化（同义词映射） |
| ConfidenceScorer | 抽取结果置信度评分 |
| ConflictDetector | 与已有知识库的冲突检测 |
| FusionEngine | 多源同类知识融合 |
| ReviewQueueManager | 人工复核队列管理 |

### 4.2 核心处理流程

```
输入：知识候选对象(KnowledgeCandidate)

Step1: DocParser 解析原始内容 → 结构化文本(含表格/图片OCR结果)
Step2: Chunker 按语义边界分块 → List<TextChunk>
Step3: 对每个TextChunk：
   ExtractionEngine.extract(chunk, ontology_schema)
      → 输出候选实体列表、候选关系列表、候选事件链
Step4: TermNormalizer 对候选实体进行同义词归一化
Step5: ConfidenceScorer 对每条抽取结果评分
   IF confidence < threshold_low:
       → 丢弃或标记为"低置信度-建议舍弃"
   ELIF threshold_low <= confidence < threshold_high:
       → 进入 ReviewQueueManager 人工复核队列
   ELSE:
       → 进入 ConflictDetector 冲突检测
Step6: ConflictDetector：
   IF 与已有知识条目冲突:
       → 标记冲突，进入人工仲裁队列
   ELSE:
       → 进入 FusionEngine
Step7: FusionEngine 与同类已有知识融合/更新置信度加权
Step8: 输出结构化知识条目 → 写入待审核知识库（Pending状态）
```

### 4.3 抽取Schema设计（示例）

抽取引擎需依据本体定义的Schema进行约束抽取，示例（故障案例类知识）：

```json
{
  "entity_types": ["装备", "系统", "部件", "故障模式", "征兆", "传感器参数", "维修动作", "责任人"],
  "relation_types": [
    {"name": "属于", "domain": "部件", "range": "系统"},
    {"name": "表现为", "domain": "故障模式", "range": "征兆"},
    {"name": "导致", "domain": "故障模式", "range": "故障模式"},
    {"name": "处置措施为", "domain": "故障模式", "range": "维修动作"}
  ],
  "event_types": ["故障发生", "故障发现", "诊断分析", "维修处置", "验证复查"]
}
```

### 4.4 置信度评分策略

置信度评分建议综合以下因子加权计算：

- 抽取模型自身输出的概率/置信度信号；
- 与已有知识图谱中同类实体/关系的匹配一致性；
- 来源可信度（如已发布标准 > 专家录入 > 一般历史文档）；
- 多来源交叉验证情况（同一知识点被多个独立来源提及，置信度提升）。

---

## 5. 本体与知识图谱模块详细设计（M03）

### 5.1 子组件划分

| 子组件 | 职责 |
|---|---|
| OntologyManager | 本体定义管理（核心层+领域扩展层） |
| OntologyEditor | 本体可视化编辑工具后端服务 |
| GraphInstantiationEngine | 将结构化知识条目实例化为图谱节点/边 |
| GraphQualityEvaluator | 图谱质量评估（完整性/一致性/准确性指标计算） |
| CrossDomainLinker | 跨领域知识关联（共性部件/故障模式类比） |

### 5.2 本体核心类定义（概念模型）

```
Class: Equipment（装备）
  - equipment_id, name, model, domain, hierarchy_level

Class: Component（部件）
  - component_id, name, parent_equipment_id, component_type

Class: FailureMode（故障模式）
  - failure_mode_id, name, mechanism_description, severity_level

Class: Symptom（征兆）
  - symptom_id, name, measurable_parameter, detection_method

Class: DiagnosisMethod（诊断方法）
  - method_id, name, applicable_failure_modes, principle_description

Class: HealthState（健康状态）
  - state_id, name, threshold_definition

Class: RULModel（寿命预测模型）
  - model_id, name, applicable_component_type, input_parameters, model_type

Class: MaintenanceStrategy（维修策略）
  - strategy_id, name, applicable_failure_modes, action_description

Relationships:
  Component --belongsTo--> Equipment
  FailureMode --occursIn--> Component
  FailureMode --manifestsAs--> Symptom
  Symptom --detectedBy--> DiagnosisMethod
  FailureMode --leadsTo--> FailureMode  (故障传播)
  FailureMode --resolvedBy--> MaintenanceStrategy
  Component --appliesModel--> RULModel
```

### 5.3 图实例化流程

```
输入：已审核通过的结构化知识条目

Step1: 根据知识条目的entity/relation标注，映射至OntologyManager中定义的类与关系
Step2: 实体消歧（Entity Resolution）：
   查询图数据库中是否已存在同名/同义实体
   IF 存在: 复用已有节点，更新属性/置信度
   ELSE: 创建新节点
Step3: 关系写入：创建/更新对应的边，携带来源、置信度、时间等属性
Step4: CrossDomainLinker 执行跨领域关联规则匹配
   （如同一部件类型在不同领域中的故障模式关联提示）
Step5: GraphQualityEvaluator 增量评估本次写入对图谱完整性/一致性的影响
Step6: 写入完成，更新知识条目状态为"已入图谱"
```

### 5.4 图数据库Schema设计（逻辑设计，具体DDL依选型工具确定）

| 节点标签 | 主要属性 |
|---|---|
| Equipment | id, name, model, domain, level |
| Component | id, name, type, parent_id |
| FailureMode | id, name, mechanism, severity, confidence |
| Symptom | id, name, parameter, detection_method |
| DiagnosisMethod | id, name, principle |
| MaintenanceStrategy | id, name, description |
| RULModel | id, name, applicable_type, parameters |

| 关系类型 | 起点→终点 | 关键属性 |
|---|---|---|
| BELONGS_TO | Component→Equipment | —— |
| OCCURS_IN | FailureMode→Component | confidence, source |
| MANIFESTS_AS | FailureMode→Symptom | confidence |
| LEADS_TO | FailureMode→FailureMode | probability, source |
| RESOLVED_BY | FailureMode→MaintenanceStrategy | effectiveness_rating |
| DETECTED_BY | Symptom→DiagnosisMethod | —— |
| APPLIES_MODEL | Component→RULModel | —— |

---

## 6. 知识存储模块详细设计（M04）

### 6.1 关系型数据库表结构设计（核心表）

**表：knowledge_item（知识条目主表）**

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | varchar(32) | 主键，知识条目ID |
| domain | varchar(20) | 领域（energy/transportation/aerospace/general） |
| type | varchar(20) | 知识类型（case/rule/standard/literature/expertise） |
| title | varchar(255) | 标题 |
| content_summary | text | 内容摘要 |
| content_ref | varchar(255) | 原文引用（对象存储路径） |
| classification_level | varchar(10) | 密级 |
| confidence | decimal(3,2) | 置信度 |
| status | varchar(20) | 生命周期状态 |
| version | int | 版本号 |
| owner_id | varchar(32) | 责任专家ID |
| source_project_id | varchar(32) | 来源项目ID |
| created_time | datetime | 创建时间 |
| updated_time | datetime | 更新时间 |

**表：knowledge_version_history（版本历史表）**

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | varchar(32) | 主键 |
| knowledge_id | varchar(32) | 关联知识条目ID |
| version | int | 版本号 |
| content_snapshot | text | 该版本内容快照 |
| change_type | varchar(20) | 变更类型（create/update/deprecate） |
| operator_id | varchar(32) | 操作人 |
| operate_time | datetime | 操作时间 |

**表：review_workflow（审核流程表）**

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | varchar(32) | 主键 |
| knowledge_id | varchar(32) | 关联知识条目ID |
| current_stage | varchar(20) | 当前审核阶段 |
| reviewer_id | varchar(32) | 当前审核人 |
| review_result | varchar(20) | 审核结果（approved/rejected/pending） |
| review_comment | text | 审核意见 |
| update_time | datetime | 更新时间 |

**表：user_permission（用户权限表）**

| 字段名 | 类型 | 说明 |
|---|---|---|
| user_id | varchar(32) | 用户ID |
| role | varchar(20) | 角色（expert/engineer/admin/manager） |
| domain_scope | varchar(100) | 可访问领域范围 |
| max_classification_level | varchar(10) | 可访问最高密级 |

### 6.2 向量数据库设计要点

- 每个知识条目（或分块Chunk）生成对应Embedding向量，存储时携带元数据（knowledge_id、domain、classification_level）便于检索时联合过滤；
- 建议采用"知识条目粒度+分块粒度"双重索引策略：条目级向量用于粗粒度召回，分块级向量用于精确定位具体段落。

### 6.3 数据一致性设计

- 知识条目在关系库、图数据库、向量库中的记录通过统一的 `knowledge_id` 关联；
- 采用**最终一致性**模型：知识条目状态变更（如失效/归档）通过事件驱动方式（发布领域事件）异步同步至图库与向量库索引状态，避免分布式事务带来的性能损耗；
- 定期执行一致性校验任务，检测并修复跨存储的数据不一致。

---

## 7. RAG检索增强模块详细设计（M05）

### 7.1 子组件划分

| 子组件 | 职责 |
|---|---|
| QueryUnderstanding | 查询意图识别与改写 |
| PermissionFilterBuilder | 依据用户权限生成检索过滤条件 |
| VectorRetriever | 向量语义检索 |
| GraphRetriever | 图谱关系检索 |
| StructuredRetriever | 结构化规则/参数检索 |
| ResultReranker | 多路召回结果融合重排序 |
| ContextBuilder | 构建带来源标注的生成上下文 |
| AnswerGenerator | 调用大模型生成最终回答 |
| CitationTagger | 回答引用溯源标注 |

### 7.2 详细处理时序

```
1. 用户输入问题 → QueryUnderstanding
   - 意图分类（案例查询/规则查询/标准解读/通用问答）
   - 查询改写（补全领域术语、消解指代）

2. PermissionFilterBuilder 依据 SecurityContext(user)
   生成过滤条件：{domain ⊆ user.domain_scope, classification_level ≤ user.max_level}

3. 并行调用：
   VectorRetriever.search(query_embedding, filter, top_k=20)
   GraphRetriever.search(query_entities, relation_patterns, filter, max_hop=3)
   StructuredRetriever.search(query_keywords, filter)

4. ResultReranker：
   - 对三路结果去重、归一化打分
   - 融合排序，取Top N（建议N=5~8）

5. ContextBuilder：
   - 将Top N结果拼装为带来源标记的Prompt上下文
   - 控制总Token数不超过模型上下文窗口限制

6. AnswerGenerator：
   - 调用大模型推理服务生成回答
   - 若命中知识不足，明确提示"知识库暂无充分依据"，避免模型自由发挥编造

7. CitationTagger：
   - 将回答中引用内容与来源知识条目ID关联，前端支持点击溯源

8. 返回：{answer, citations[], confidence_hint}
```

### 7.3 关键设计约束

- 当检索结果为空或相关度低于阈值时，系统须明确告知用户"未检索到充分依据"，**不得由大模型在无知识依据情况下直接生成专业结论**，尤其针对安全关键问题；
- 检索与生成的全过程日志需完整留存，支持问答质量抽样评估与追溯。

---

## 8. Agent智能体模块详细设计（M06）

### 8.1 Agent架构组成

```
AgentController（任务入口）
   → TaskPlanner（任务规划：将用户任务分解为子步骤）
   → ToolRegistry（工具注册中心）
        - GraphQueryTool
        - StructuredQueryTool
        - RAGRetrievalTool
        - CalculationTool
        - ExternalPHMAlgorithmTool
   → ExecutionEngine（按规划逐步执行，必要时调用工具）
   → ReflectionModule（步骤结果校验与再规划）
   → HumanConfirmationGate（安全关键节点人工确认）
   → ResultAssembler（结果汇总与呈现）
```

### 8.2 典型Agent工作流示例：故障诊断辅助Agent

```
输入：故障现象描述（自然语言）

Step1: TaskPlanner 规划子任务：
   [1]提取关键征兆特征 → [2]检索历史相似案例(RAGRetrievalTool)
   → [3]图谱查询关联故障模式(GraphQueryTool)
   → [4]结构化查询适用诊断规则(StructuredQueryTool)
   → [5]生成根因假设排序 → [6]生成处置建议

Step2: ExecutionEngine 依次执行工具调用，收集中间结果

Step3: ReflectionModule 校验：
   - 若各来源结果冲突（如不同案例给出不同根因），
     标记冲突并在最终结果中并列呈现，不强行给出单一结论

Step4: HumanConfirmationGate：
   - 对于涉及安全关键装备（如航空发动机）的诊断建议，
     强制标注"AI辅助建议，须专家复核确认"，不作为最终结论直接输出

Step5: ResultAssembler 汇总输出：
   {可能根因排序, 支持依据(案例/规则引用), 建议处置措施, 置信度提示, 免责说明}
```

### 8.3 Agent执行轨迹记录设计

每次Agent执行须记录完整轨迹，用于可解释性展示与审计：

```json
{
  "trace_id": "string",
  "task_input": "用户输入",
  "steps": [
    {"step": 1, "action": "工具调用/推理", "tool": "...", "input": "...", "output": "...", "timestamp": "..."}
  ],
  "final_result": "...",
  "human_confirmation_required": true,
  "confirmation_status": "pending/confirmed/rejected"
}
```

---

## 9. 领域微调模块详细设计（M07）

### 9.1 子组件划分

| 子组件 | 职责 |
|---|---|
| TrainingDataBuilder | 基于知识库构建微调训练语料（指令-回答对） |
| FineTuningPipeline | 微调训练流程编排（LoRA等参数高效微调） |
| ModelEvaluator | 微调模型效果评估（离线测试集评估） |
| ModelRegistry | 模型版本管理与灰度发布 |

### 9.2 训练数据构建流程

```
Step1: 从已审核发布的知识条目中，按领域/任务类型抽取样本
Step2: 基于模板+人工/半自动方式构建指令-回答对
   （如：{"instruction": "某型号轴承出现异响，可能的故障原因是什么？",
          "output": "结合历史案例及诊断规则的标准回答..."}）
Step3: 数据质量校验（去重、敏感信息脱敏、样本均衡性检查）
Step4: 划分训练集/验证集/测试集
```

### 9.3 微调与评估流程

```
Step1: FineTuningPipeline 基于基础模型 + 训练集执行LoRA微调
Step2: ModelEvaluator 在验证集/测试集上评估：
   - 领域问答准确率（人工抽样评估+自动化指标）
   - 与基础模型/RAG-only方案的对比效果
Step3: 若效果达标，ModelRegistry 注册新模型版本，进入灰度发布
Step4: 灰度期间对比线上反馈数据，确认无明显负面影响后全量切换
```

---

## 10. 知识问答与检索应用模块详细设计（M08）

### 10.1 前端交互设计要点

- 问答界面支持多轮对话、历史会话管理；
- 回答内容中的引用来源以可点击标签形式呈现，点击后弹出原文片段及跳转链接；
- 提供"有帮助/无帮助"反馈按钮及文字纠错入口，反馈数据写入 `feedback` 表供运营分析。

### 10.2 检索页面设计要点

- 支持关键词、领域、装备型号、时间范围、知识类型多维度筛选组件；
- 检索结果列表展示知识摘要、置信度、来源、密级标识；
- 支持"相似案例"侧栏推荐（基于向量相似度）。

---

## 11. 知识图谱可视化模块详细设计（M09）

- 采用力导向图/层次图相结合的可视化方案，支持节点点击展开、关系路径高亮；
- 提供"故障传播链路"专项可视化视图，突出展示 `LEADS_TO` 关系链条；
- 支持按领域/装备类型进行子图过滤展示，避免全图渲染性能问题（建议单次渲染节点数控制在合理阈值内，超出则提供逐层展开交互）。

---

## 12. 知识运营与治理模块详细设计（M10）

### 12.1 知识审核工作流设计

```
状态机：草稿(Draft) → 待审(Pending) → [审核通过]发布(Published)
                                    → [审核驳回]草稿(Draft，附驳回意见)
        发布(Published) → [复核到期/标准变更触发]待复核(Under Review)
        发布(Published) → [人工标记失效]失效(Deprecated) → 归档(Archived)
```

- 支持多级审核配置（如：一线专家初审 + 领域首席专家终审，视知识密级/重要程度动态配置审核链）；
- 审核环节需展示AI抽取置信度、冲突检测结果，辅助审核人决策。

### 12.2 知识质量评估规则引擎设计

| 评估维度 | 评估规则示例 |
|---|---|
| 时效性 | 知识条目超过设定有效期未复核，标记"待复核" |
| 完整性 | 关键字段缺失（如故障模式缺少处置措施关联）标记"待完善" |
| 一致性 | 与图谱中其他知识存在逻辑冲突，标记"待仲裁" |
| 使用度 | 长期未被检索命中的条目纳入定期抽查复核范围 |

### 12.3 知识运营看板设计要点

- 知识资产统计（总量、领域分布、类型分布、增长趋势）；
- 使用效果统计（问答调用量、检索热词、满意度趋势）；
- 专家贡献度排行（贡献数量、审核通过率、被引用次数）。

---

## 13. 系统管理模块详细设计（M11）

### 13.1 权限管理设计

- 角色定义：专家（expert）、工程师（engineer）、管理员（admin）、管理层（manager）；
- 权限维度：功能权限（可执行操作）+ 领域权限（可访问业务领域）+ 密级权限（可访问最高密级）；
- 权限变更需记录审计日志，重要权限调整（如密级权限提升）建议纳入审批流程。

### 13.2 日志审计设计

| 日志类型 | 记录内容 |
|---|---|
| 操作日志 | 用户登录、知识增删改、审核操作、权限变更 |
| 问答日志 | 问题内容、检索命中知识、生成回答、反馈结果 |
| 系统日志 | 服务调用链路、异常堆栈、性能指标 |

日志需支持按时间、用户、操作类型多维度检索，满足安全审计与合规检查要求。

### 13.3 监控告警设计

- 监控指标：服务可用性、接口响应时延、GPU资源利用率、存储容量水位、异常错误率；
- 告警阈值可配置，支持多渠道告警通知（邮件/企业IM等，视公司实际使用工具对接）。

---

## 14. 异常处理与容错设计

| 异常场景 | 处理策略 |
|---|---|
| 文档解析失败 | 记录失败原因，写入死信队列，通知数据接入负责人 |
| 大模型推理服务超时/不可用 | 触发降级策略：优先返回检索结果（不生成），提示"生成服务暂不可用" |
| 检索结果为空 | 明确提示用户，避免大模型无依据生成 |
| 图数据库/向量库写入失败 | 重试机制（指数退避），超过重试次数进入人工处理队列 |
| 知识冲突无法自动仲裁 | 强制进入人工仲裁流程，冲突双方知识条目均标记"待仲裁"状态，暂不参与检索召回 |
| 权限校验失败 | 统一返回403，记录尝试访问日志供安全审计 |

---

## 15. 关键业务流程时序设计

### 15.1 知识入库全流程时序（简化）

```
[数据接入层] --采集--> [消息队列]
[消息队列] --消费--> [知识加工层：解析/抽取/清洗/融合]
[知识加工层] --写入(Pending)--> [知识存储层：待审核知识库]
[知识运营模块] --分配审核任务--> [责任专家]
[责任专家] --审核确认--> [知识运营模块]
[知识运营模块] --状态更新为Published--> [知识存储层]
[知识存储层] --触发实例化--> [本体与知识图谱模块：图实例化]
[知识存储层] --触发向量化--> [向量数据库：Embedding写入]
[知识运营模块] --通知--> [订阅该领域的相关用户（可选）]
```

### 15.2 智能问答请求全流程时序（简化）

```
[用户] --提问--> [应用层：问答界面]
[应用层] --请求--> [RAG检索增强模块]
[RAG模块] --权限过滤+混合检索--> [知识服务层]
[知识服务层] --查询--> [知识存储层：图库/向量库/结构化库]
[知识服务层] --返回检索结果--> [RAG模块]
[RAG模块] --构建上下文+调用--> [大模型推理服务]
[大模型推理服务] --生成回答--> [RAG模块]
[RAG模块] --标注引用来源--> [应用层]
[应用层] --展示回答+引用--> [用户]
[用户] --反馈(可选)--> [知识运营模块：反馈记录]
```

---

*本文档为详细设计初版，各模块具体类设计、字段定义将在开发阶段随技术选型细化，重大变更须同步更新本文档并履行评审流程。*
