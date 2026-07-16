"""add rag and qa tables

Revision ID: 003_rag_qa
Revises: 002_ontology
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "003_rag_qa"
down_revision = "002_ontology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 不手动 enum.create(...)：op.create_table() 会在建表时自动创建该枚举类型。
    rag_index_status_enum = sa.Enum("building", "completed", "failed", name="rag_index_status_enum")
    qa_message_role_enum = sa.Enum("user", "assistant", name="qa_message_role_enum")

    op.create_table(
        "rag_index_job",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("embedding_model", sa.String(50), nullable=False, server_default="bge-m3"),
        sa.Column("status", rag_index_status_enum, nullable=False, server_default="building"),
        sa.Column("items_indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunks_indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_real_embedding", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "rag_query_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_real_embedding", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_query_log_created_at", "rag_query_log", ["created_at"])

    op.create_table(
        "qa_session",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_qa_session_user_id", "qa_session", ["user_id"])

    op.create_table(
        "qa_message",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("session_id", sa.String(32), nullable=False),
        sa.Column("role", qa_message_role_enum, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations_json", sa.Text, nullable=True),
        sa.Column("confidence_hint", sa.String(10), nullable=True),
        sa.Column("helpful", sa.Integer, nullable=True),
        sa.Column("feedback_comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_qa_message_session_id", "qa_message", ["session_id"])


def downgrade() -> None:
    op.drop_table("qa_message")
    op.drop_table("qa_session")
    op.drop_table("rag_query_log")
    op.drop_table("rag_index_job")
    sa.Enum(name="qa_message_role_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="rag_index_status_enum").drop(op.get_bind(), checkfirst=True)
