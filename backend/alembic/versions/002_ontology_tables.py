"""add ontology change request and version tables

Revision ID: 002_ontology
Revises: 001_seed
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "002_ontology"
down_revision = "001_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 不手动 enum.create(...)：op.create_table() 会在建表时自动创建该枚举类型；
    # 手动再创建一次会导致 "type already exists" 报错（downgrade() 中仍需手动 drop）。
    ontology_change_status_enum = sa.Enum("pending", "approved", "rejected", name="ontology_change_status_enum")

    op.create_table(
        "ontology_change_request",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("domain", sa.String(20), nullable=False),
        sa.Column("change_description", sa.Text, nullable=False),
        sa.Column("classes_json", sa.Text, nullable=True),
        sa.Column("relations_json", sa.Text, nullable=True),
        sa.Column("submitter_id", sa.String(32), nullable=False),
        sa.Column("status", ontology_change_status_enum, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "ontology_version",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("version", sa.String(20), nullable=False, unique=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("publisher_id", sa.String(32), nullable=False),
        sa.Column("published_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ontology_version")
    op.drop_table("ontology_change_request")
    sa.Enum(name="ontology_change_status_enum").drop(op.get_bind(), checkfirst=True)
