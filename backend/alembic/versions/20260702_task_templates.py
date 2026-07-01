"""add task_templates table

Revision ID: 20260702_task_templates
Revises: 20260706_system_settings
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260702_task_templates"
down_revision = "20260706_system_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("task_templates")
