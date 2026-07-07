"""drop sort_index startfid from tasks

Revision ID: 20260706_drop_sort_index_startfid
Revises: 20260707_remove_shareurl_ban
Create Date: 2026-07-06 12:04:27.000000

"""

from alembic import op
import sqlalchemy as sa


revision = '20260706_drop_sort_index_startfid'
down_revision = '20260707_remove_shareurl_ban'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除 tasks 表的 sort_index 和 startfid 列
    op.drop_column('tasks', 'sort_index')
    op.drop_column('tasks', 'startfid')


def downgrade() -> None:
    # 回滚时重新添加列（不带默认值，允许 NULL）
    op.add_column('tasks', sa.Column('startfid', sa.String(length=128), nullable=True))
    op.add_column('tasks', sa.Column('sort_index', sa.Integer(), nullable=True))