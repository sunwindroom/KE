"""add finetune task and registered model tables

Revision ID: 006_finetune
Revises: 005_conflict_snapshot
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "006_finetune"
down_revision = "005_conflict_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 不手动 enum.create(...)：op.create_table() 会在建表时自动创建该枚举类型；
    # 手动再创建一次会导致 "type already exists" 报错。
    finetune_stage_enum = sa.Enum("SFT", "DPO", "RLHF", name="finetune_stage_enum")
    finetune_status_enum = sa.Enum("queued", "running", "completed", "failed", name="finetune_status_enum")
    registered_model_status_enum = sa.Enum(
        "registered", "staging", "production", "retired", name="registered_model_status_enum"
    )

    op.create_table(
        "finetune_task",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("base_model", sa.String(100), nullable=False),
        sa.Column("stage", finetune_stage_enum, nullable=False, server_default="SFT"),
        sa.Column("domain", sa.String(20), nullable=True),
        sa.Column("dataset_id", sa.String(32), nullable=True),
        sa.Column("submitter_id", sa.String(32), nullable=False),
        sa.Column("status", finetune_status_enum, nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_finetune_task_submitter_id", "finetune_task", ["submitter_id"])

    op.create_table(
        "registered_model",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("base_model", sa.String(100), nullable=True),
        sa.Column("source_task_id", sa.String(32), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="v1"),
        sa.Column("stage", sa.String(20), nullable=True),
        sa.Column("status", registered_model_status_enum, nullable=False, server_default="registered"),
        sa.Column("submitter_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("registered_model")
    op.drop_index("ix_finetune_task_submitter_id", table_name="finetune_task")
    op.drop_table("finetune_task")
    bind = op.get_bind()
    sa.Enum(name="registered_model_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="finetune_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="finetune_stage_enum").drop(bind, checkfirst=True)
