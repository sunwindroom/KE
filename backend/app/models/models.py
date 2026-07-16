from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidate"

    id = Column(String(32), primary_key=True)
    source_type = Column(SAEnum("document", "database", "expert_input", "external_standard", name="source_type_enum"), nullable=False)
    domain = Column(SAEnum("energy", "transportation", "aerospace", "general", name="domain_enum"), nullable=False)
    raw_content = Column(Text, nullable=True)
    attachments = Column(Text, nullable=True)
    source_name = Column(String(255), nullable=True)
    project_id = Column(String(32), nullable=True)
    classification_level = Column(String(20), nullable=False, default="internal")
    submitter_id = Column(String(32), nullable=False)
    status = Column(SAEnum("pending", "processing", "processed", "failed", name="candidate_status_enum"), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_item"

    id = Column(String(32), primary_key=True)
    domain = Column(SAEnum("energy", "transportation", "aerospace", "general", name="domain_enum_item"), nullable=False)
    type = Column(SAEnum("case", "rule", "standard", "literature", "expertise", name="knowledge_type_enum"), nullable=False)
    title = Column(String(255), nullable=False)
    content_summary = Column(Text, nullable=True)
    content_ref = Column(String(255), nullable=True)
    classification_level = Column(String(20), nullable=False, default="internal")
    confidence = Column(Numeric(3, 2), nullable=True)
    status = Column(
        SAEnum("draft", "pending", "published", "deprecated", "archived", name="knowledge_status_enum"),
        nullable=False,
        default="draft",
    )
    version = Column(Integer, nullable=False, default=1)
    owner_id = Column(String(32), nullable=True)
    source_project_id = Column(String(32), nullable=True)
    source_candidate_id = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class KnowledgeVersionHistory(Base):
    __tablename__ = "knowledge_version_history"

    id = Column(String(32), primary_key=True)
    knowledge_id = Column(String(32), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_snapshot = Column(Text, nullable=True)
    change_type = Column(SAEnum("create", "update", "deprecate", name="change_type_enum"), nullable=False)
    operator_id = Column(String(32), nullable=False)
    operated_at = Column(DateTime, nullable=False, default=datetime.now)


class KnowledgeConflict(Base):
    __tablename__ = "knowledge_conflict"

    id = Column(String(32), primary_key=True)
    knowledge_id_a = Column(String(32), nullable=False, index=True)
    knowledge_id_b = Column(String(32), nullable=False, index=True)
    domain = Column(String(20), nullable=True)
    conflict_type = Column(String(30), nullable=False, default="similar_title")
    description = Column(Text, nullable=True)
    similarity = Column(Numeric(4, 3), nullable=True)
    status = Column(
        SAEnum("pending", "resolved", name="knowledge_conflict_status_enum"),
        nullable=False,
        default="pending",
    )
    resolver_id = Column(String(32), nullable=True)
    resolution = Column(String(20), nullable=True)
    resolution_comment = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class KnowledgeSnapshot(Base):
    __tablename__ = "knowledge_snapshot"

    id = Column(String(32), primary_key=True)
    name = Column(String(255), nullable=False)
    comment = Column(Text, nullable=True)
    total_knowledge_count = Column(Integer, nullable=False, default=0)
    by_domain_json = Column(Text, nullable=True)
    by_status_json = Column(Text, nullable=True)
    creator_id = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class ReviewWorkflow(Base):
    __tablename__ = "review_workflow"

    id = Column(String(32), primary_key=True)
    knowledge_id = Column(String(32), nullable=False, index=True)
    review_type = Column(String(20), nullable=False, default="initial")
    current_stage = Column(String(20), nullable=False, default="pending")
    reviewer_id = Column(String(32), nullable=True)
    review_result = Column(SAEnum("approved", "rejected", "pending", "escalated", name="review_result_enum"), nullable=False, default="pending")
    review_comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)


class UserPermission(Base):
    __tablename__ = "user_permission"

    user_id = Column(String(32), primary_key=True)
    user_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SAEnum("expert", "engineer", "admin", "manager", name="role_enum"), nullable=False, default="engineer")
    domain_scope = Column(String(100), nullable=False, default="energy,transportation,aerospace,general")
    max_classification_level = Column(String(20), nullable=False, default="internal")
    status = Column(SAEnum("active", "disabled", name="user_status_enum"), nullable=False, default="active")
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class AgentTask(Base):
    __tablename__ = "agent_task"

    id = Column(String(32), primary_key=True)
    agent_type = Column(String(50), nullable=False)
    input_data = Column(Text, nullable=True)
    domain = Column(String(20), nullable=True)
    submitter_id = Column(String(32), nullable=False)
    status = Column(
        SAEnum("running", "completed", "failed", "waiting_confirmation", "confirmed", "rejected", name="agent_status_enum"),
        nullable=False,
        default="running",
    )
    trace = Column(Text, nullable=True)
    final_result = Column(Text, nullable=True)
    human_confirmation_required = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class OntologyChangeRequest(Base):
    __tablename__ = "ontology_change_request"

    id = Column(String(32), primary_key=True)
    domain = Column(String(20), nullable=False)
    change_description = Column(Text, nullable=False)
    classes_json = Column(Text, nullable=True)
    relations_json = Column(Text, nullable=True)
    submitter_id = Column(String(32), nullable=False)
    status = Column(
        SAEnum("pending", "approved", "rejected", name="ontology_change_status_enum"),
        nullable=False,
        default="pending",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class OntologyVersion(Base):
    __tablename__ = "ontology_version"

    id = Column(String(32), primary_key=True)
    version = Column(String(20), nullable=False, unique=True)
    comment = Column(Text, nullable=True)
    publisher_id = Column(String(32), nullable=False)
    published_at = Column(DateTime, nullable=False, default=datetime.now)


class RagIndexJob(Base):
    __tablename__ = "rag_index_job"

    id = Column(String(32), primary_key=True)
    domain = Column(String(20), nullable=True)
    embedding_model = Column(String(50), nullable=False, default="bge-m3")
    status = Column(
        SAEnum("building", "completed", "failed", name="rag_index_status_enum"),
        nullable=False,
        default="building",
    )
    items_indexed = Column(Integer, nullable=False, default=0)
    chunks_indexed = Column(Integer, nullable=False, default=0)
    used_real_embedding = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class RagQueryLog(Base):
    __tablename__ = "rag_query_log"

    id = Column(String(32), primary_key=True)
    query = Column(Text, nullable=False)
    domain = Column(String(20), nullable=True)
    hit_count = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False, default=0)
    used_real_embedding = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class QaSession(Base):
    __tablename__ = "qa_session"

    id = Column(String(32), primary_key=True)
    user_id = Column(String(32), nullable=False, index=True)
    domain = Column(String(20), nullable=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class QaMessage(Base):
    __tablename__ = "qa_message"

    id = Column(String(32), primary_key=True)
    session_id = Column(String(32), nullable=False, index=True)
    role = Column(SAEnum("user", "assistant", name="qa_message_role_enum"), nullable=False)
    content = Column(Text, nullable=False)
    citations_json = Column(Text, nullable=True)
    confidence_hint = Column(String(10), nullable=True)
    helpful = Column(Integer, nullable=True)
    feedback_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class ExtractionTask(Base):
    __tablename__ = "extraction_task"

    id = Column(String(32), primary_key=True)
    candidate_id = Column(String(32), nullable=True, index=True)
    domain = Column(String(20), nullable=True)
    submitter_id = Column(String(32), nullable=False)
    status = Column(
        SAEnum("processing", "completed", "failed", name="extraction_task_status_enum"),
        nullable=False,
        default="processing",
    )
    used_real_llm = Column(Integer, nullable=False, default=0)
    entities_extracted = Column(Integer, nullable=False, default=0)
    relations_extracted = Column(Integer, nullable=False, default=0)
    knowledge_item_id = Column(String(32), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class ExtractionItem(Base):
    __tablename__ = "extraction_item"

    id = Column(String(32), primary_key=True)
    task_id = Column(String(32), nullable=False, index=True)
    candidate_id = Column(String(32), nullable=True, index=True)
    domain = Column(String(20), nullable=True)
    kind = Column(SAEnum("entity", "relation", name="extraction_item_kind_enum"), nullable=False)
    payload_json = Column(Text, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False, default=0.5)
    has_conflict = Column(Integer, nullable=False, default=0)
    status = Column(
        SAEnum("pending", "approved", "rejected", name="extraction_item_status_enum"),
        nullable=False,
        default="pending",
    )
    reviewer_id = Column(String(32), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(32), primary_key=True)
    user_id = Column(String(32), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(32), nullable=True)
    detail = Column(Text, nullable=True)
    classification_level = Column(String(20), nullable=True)
    request_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class FinetuneTask(Base):
    __tablename__ = "finetune_task"

    id = Column(String(32), primary_key=True)
    base_model = Column(String(100), nullable=False)
    stage = Column(SAEnum("SFT", "DPO", "RLHF", name="finetune_stage_enum"), nullable=False, default="SFT")
    domain = Column(String(20), nullable=True)
    dataset_id = Column(String(32), nullable=True)
    submitter_id = Column(String(32), nullable=False)
    status = Column(
        SAEnum("queued", "running", "completed", "failed", name="finetune_status_enum"),
        nullable=False,
        default="queued",
    )
    progress = Column(Integer, nullable=False, default=0)
    metrics_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class RegisteredModel(Base):
    __tablename__ = "registered_model"

    id = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    base_model = Column(String(100), nullable=True)
    source_task_id = Column(String(32), nullable=True)
    version = Column(String(20), nullable=False, default="v1")
    stage = Column(String(20), nullable=True)
    status = Column(
        SAEnum("registered", "staging", "production", "retired", name="registered_model_status_enum"),
        nullable=False,
        default="registered",
    )
    submitter_id = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

class SystemConfig(Base):
    """系统运行时配置项：管理员通过“系统设置”界面维护的、覆盖 .env 默认值的键值对。

    - category: 配置分组（llm / embedding / storage_minio / graph_neo4j / vector_milvus /
      cache_redis / mq_rabbitmq / security / cors / upload / rate_limit / app）。
    - key: 对应 app.config.Settings 中的字段名，保持完全一致，便于启动时按同名属性覆盖。
    - value: 明文配置以原始字符串存储；is_secret=True 的值经 Fernet 加密后存储，
      永远不会在接口中明文返回（读取时只返回掩码）。
    - updated_by / updated_at: 审计用，便于追溯“谁在什么时候改了生产配置”。
    """

    __tablename__ = "system_config"

    id = Column(String(64), primary_key=True)  # 固定为 f"{category}.{key}"，天然唯一
    category = Column(String(50), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=True)
    is_secret = Column(Integer, nullable=False, default=0)  # 0/1，跨方言兼容优于 Boolean
    updated_by = Column(String(32), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
