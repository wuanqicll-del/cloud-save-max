"""system settings

Revision ID: 20260706_system_settings
Revises: 20260613_telegram_bot_state_and_sessions
Create Date: 2026-07-06 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260706_system_settings"
down_revision = "20260613_telegram_bot_state_and_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建系统设置表
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_system_settings_key"), "system_settings", ["key"], unique=True)
    
    # 插入默认配置
    op.execute(
        "INSERT INTO system_settings (key, value, description) VALUES "
        "('preferred_sharers', '', '优选分享者列表，多个昵称用竖线分隔'), "
        "('blocked_sharers', '', '屏蔽分享者列表，多个昵称用竖线分隔')"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_settings_key"), table_name="system_settings")
    op.drop_table("system_settings")