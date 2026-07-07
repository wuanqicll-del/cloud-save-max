"""remove shareurl_ban

Revision ID: 20260707_remove_shareurl_ban
Revises: 20260706_system_settings
Create Date: 2026-07-07 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260707_remove_shareurl_ban"
down_revision = "20260703_audit_log_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("shareurl_ban")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("shareurl_ban", sa.Text(), nullable=True))
