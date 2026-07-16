"""seed default admin user

Revision ID: 001_seed
Revises: 
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

from app.core.security import get_password_hash

revision = "001_seed"
down_revision = "000_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    admin_hash = get_password_hash("admin123")
    op.execute(
        sa.text(
            "INSERT INTO user_permission (user_id, user_name, password_hash, role, domain_scope, max_classification_level, status) "
            "VALUES (:uid, :uname, :phash, CAST(:role AS role_enum), :dscope, :mcl, CAST(:status AS user_status_enum)) "
            "ON CONFLICT (user_id) DO NOTHING"
        ).bindparams(
            uid="admin",
            uname="系统管理员",
            phash=admin_hash,
            role="admin",
            dscope="energy,transportation,aerospace,general",
            mcl="secret",
            status="active",
        )
    )

    expert_hash = get_password_hash("expert123")
    op.execute(
        sa.text(
            "INSERT INTO user_permission (user_id, user_name, password_hash, role, domain_scope, max_classification_level, status) "
            "VALUES (:uid, :uname, :phash, CAST(:role AS role_enum), :dscope, :mcl, CAST(:status AS user_status_enum)) "
            "ON CONFLICT (user_id) DO NOTHING"
        ).bindparams(
            uid="expert001",
            uname="张专家",
            phash=expert_hash,
            role="expert",
            dscope="energy,aerospace",
            mcl="confidential",
            status="active",
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM user_permission WHERE user_id IN ('admin', 'expert001')"))