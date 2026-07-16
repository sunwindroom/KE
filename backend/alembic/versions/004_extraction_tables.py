"""add extraction pipeline tables

Revision ID: 004_extraction
Revises: 003_rag_qa
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "004_extraction"
down_revision = "003_rag_qa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # 不手动 enum.create(...)：op.create_table() 会在建表时自动创建该枚举类型。
    extraction_task_status_enum = sa.Enum("processing", "completed", "failed", name="extraction_task_status_enum")
    extraction_item_kind_enum = sa.Enum("entity", "relation", name="extraction_item_kind_enum")
    extraction_item_status_enum = sa.Enum("pending", "approved", "rejected", name="extraction_item_status_enum")

    op.create_table(
        "extraction_task",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("candidate_id", sa.String(32), nullable=True),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("submitter_id", sa.String(32), nullable=False),
        sa.Column("status", extraction_task_status_enum, nullable=False, server_default="processing"),
        sa.Column("used_real_llm", sa.Integer, nullable=False, server_default="0"),
        sa.Column("entities_extracted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("relations_extracted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("knowledge_item_id", sa.String(32), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_extraction_task_candidate_id", "extraction_task", ["candidate_id"])

    op.create_table(
        "extraction_item",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("candidate_id", sa.String(32), nullable=True),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("kind", extraction_item_kind_enum, nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("has_conflict", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", extraction_item_status_enum, nullable=False, server_default="pending"),
        sa.Column("reviewer_id", sa.String(32), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extraction_item_task_id", "extraction_item", ["task_id"])
    op.create_index("ix_extraction_item_candidate_id", "extraction_item", ["candidate_id"])

    op.add_column("knowledge_item", sa.Column("source_candidate_id", sa.String(32), nullable=True))
    op.create_index("ix_knowledge_item_source_candidate_id", "knowledge_item", ["source_candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_item_source_candidate_id", table_name="knowledge_item")
    op.drop_column("knowledge_item", "source_candidate_id")
    op.drop_table("extraction_item")
    op.drop_table("extraction_task")
    bind = op.get_bind()
    sa.Enum(name="extraction_item_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="extraction_item_kind_enum").drop(bind, checkfirst=True)
    sa.Enum(name="extraction_task_status_enum").drop(bind, checkfirst=True)
