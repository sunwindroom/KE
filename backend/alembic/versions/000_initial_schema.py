"""create initial schema

Revision ID: 000_initial
Revises:
Create Date: 2026-07-09

This migration was missing from the original repository: `001_seed_admin`
inserted rows into tables that no migration ever created, so running
`alembic upgrade head` against a fresh database failed with
"relation ... does not exist". This migration creates all tables backing
app/models/models.py so the migration chain works end-to-end.
"""
from alembic import op
import sqlalchemy as sa

revision = "000_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 注意：这些 Enum 类型只在下面的 op.create_table(...) 里作为列类型使用一次。
    # PostgreSQL 方言在建表时会自动为其对应的列类型发出 CREATE TYPE（无需也不应该在
    # 这里手动再调用一次 enum.create(...)，那样会导致 "type already exists" 报错，
    # 在全新数据库上第一次执行 `alembic upgrade head` 就会失败）。
    # 每个类型在 downgrade() 里通过 sa.Enum(name=...).drop(checkfirst=True) 显式清理。
    source_type_enum = sa.Enum("document", "database", "expert_input", "external_standard", name="source_type_enum")
    domain_enum = sa.Enum("energy", "transportation", "aerospace", "general", name="domain_enum")
    domain_enum_item = sa.Enum("energy", "transportation", "aerospace", "general", name="domain_enum_item")
    candidate_status_enum = sa.Enum("pending", "processing", "processed", "failed", name="candidate_status_enum")
    knowledge_type_enum = sa.Enum("case", "rule", "standard", "literature", "expertise", name="knowledge_type_enum")
    knowledge_status_enum = sa.Enum("draft", "pending", "published", "deprecated", "archived", name="knowledge_status_enum")
    change_type_enum = sa.Enum("create", "update", "deprecate", name="change_type_enum")
    review_result_enum = sa.Enum("approved", "rejected", "pending", "escalated", name="review_result_enum")
    role_enum = sa.Enum("expert", "engineer", "admin", "manager", name="role_enum")
    user_status_enum = sa.Enum("active", "disabled", name="user_status_enum")
    agent_status_enum = sa.Enum(
        "running", "completed", "failed", "waiting_confirmation", "confirmed", "rejected", name="agent_status_enum"
    )

    op.create_table(
        "knowledge_candidate",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("domain", domain_enum, nullable=False),
        sa.Column("raw_content", sa.Text, nullable=True),
        sa.Column("attachments", sa.Text, nullable=True),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("project_id", sa.String(32), nullable=True),
        sa.Column("classification_level", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("submitter_id", sa.String(32), nullable=False),
        sa.Column("status", candidate_status_enum, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "knowledge_item",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("domain", domain_enum_item, nullable=False),
        sa.Column("type", knowledge_type_enum, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_summary", sa.Text, nullable=True),
        sa.Column("content_ref", sa.String(255), nullable=True),
        sa.Column("classification_level", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("status", knowledge_status_enum, nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("owner_id", sa.String(32), nullable=True),
        sa.Column("source_project_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "knowledge_version_history",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("knowledge_id", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content_snapshot", sa.Text, nullable=True),
        sa.Column("change_type", change_type_enum, nullable=False),
        sa.Column("operator_id", sa.String(32), nullable=False),
        sa.Column("operated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_version_history_knowledge_id", "knowledge_version_history", ["knowledge_id"])

    op.create_table(
        "review_workflow",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("knowledge_id", sa.String(32), nullable=False),
        sa.Column("review_type", sa.String(20), nullable=False, server_default="initial"),
        sa.Column("current_stage", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewer_id", sa.String(32), nullable=True),
        sa.Column("review_result", review_result_enum, nullable=False, server_default="pending"),
        sa.Column("review_comment", sa.Text, nullable=True),
        sa.Column("submitted_at", sa.DateTime, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("deadline", sa.DateTime, nullable=True),
    )
    op.create_index("ix_review_workflow_knowledge_id", "review_workflow", ["knowledge_id"])

    op.create_table(
        "user_permission",
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("user_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", role_enum, nullable=False, server_default="engineer"),
        sa.Column("domain_scope", sa.String(100), nullable=False, server_default="energy,transportation,aerospace,general"),
        sa.Column("max_classification_level", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("status", user_status_enum, nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "agent_task",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("input_data", sa.Text, nullable=True),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("submitter_id", sa.String(32), nullable=False),
        sa.Column("status", agent_status_enum, nullable=False, server_default="running"),
        sa.Column("trace", sa.Text, nullable=True),
        sa.Column("final_result", sa.Text, nullable=True),
        sa.Column("human_confirmation_required", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(32), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("classification_level", sa.String(20), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("agent_task")
    op.drop_table("user_permission")
    op.drop_table("review_workflow")
    op.drop_table("knowledge_version_history")
    op.drop_table("knowledge_item")
    op.drop_table("knowledge_candidate")

    bind = op.get_bind()
    for enum_name in (
        "source_type_enum", "domain_enum", "domain_enum_item", "candidate_status_enum", "knowledge_type_enum",
        "knowledge_status_enum", "change_type_enum", "review_result_enum", "role_enum", "user_status_enum",
        "agent_status_enum",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
