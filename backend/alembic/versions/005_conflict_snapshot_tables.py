"""add knowledge conflict and snapshot tables

Revision ID: 005_conflict_snapshot
Revises: 004_extraction
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "005_conflict_snapshot"
down_revision = "004_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # 不手动 enum.create(...)：op.create_table() 会在建表时自动创建该枚举类型。
    knowledge_conflict_status_enum = sa.Enum("pending", "resolved", name="knowledge_conflict_status_enum")

    op.create_table(
        "knowledge_conflict",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("knowledge_id_a", sa.String(32), nullable=False),
        sa.Column("knowledge_id_b", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("conflict_type", sa.String(30), nullable=False, server_default="similar_title"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("similarity", sa.Numeric(4, 3), nullable=True),
        sa.Column("status", knowledge_conflict_status_enum, nullable=False, server_default="pending"),
        sa.Column("resolver_id", sa.String(32), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolution_comment", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_conflict_knowledge_id_a", "knowledge_conflict", ["knowledge_id_a"])
    op.create_index("ix_knowledge_conflict_knowledge_id_b", "knowledge_conflict", ["knowledge_id_b"])

    op.create_table(
        "knowledge_snapshot",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("total_knowledge_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("by_domain_json", sa.Text, nullable=True),
        sa.Column("by_status_json", sa.Text, nullable=True),
        sa.Column("creator_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("knowledge_snapshot")
    op.drop_table("knowledge_conflict")
    sa.Enum(name="knowledge_conflict_status_enum").drop(op.get_bind(), checkfirst=True)
