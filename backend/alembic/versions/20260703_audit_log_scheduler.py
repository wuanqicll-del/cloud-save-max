"""add audit_log_scheduler_settings table

Revision ID: 20260703_audit_log_scheduler
Revises: 20260702_task_templates
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260703_audit_log_scheduler"
down_revision = "20260702_task_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "audit_log_scheduler_settings" not in inspector.get_table_names():
        op.create_table(
            "audit_log_scheduler_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("crontab", sa.String(64), nullable=False, server_default="0 3 * * *"),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
            sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("audit_log_scheduler_settings")
