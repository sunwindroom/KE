"""add system_config table for UI-driven runtime configuration

Revision ID: 007_system_config
Revises: 006_finetune
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "007_system_config"
down_revision = "006_finetune"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("is_secret", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_by", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_system_config_category", "system_config", ["category"])


def downgrade() -> None:
    op.drop_index("ix_system_config_category", table_name="system_config")
    op.drop_table("system_config")
