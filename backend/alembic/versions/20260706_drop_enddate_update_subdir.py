"""drop enddate and update_subdir from tasks

Revision ID: 20260706_drop_enddate_update_subdir
Revises: 20260706_drop_sort_index_startfid
Create Date: 2026-07-06 13:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = '20260706_drop_enddate_update_subdir'
down_revision = '20260706_drop_sort_index_startfid'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('tasks', 'enddate')
    op.drop_column('tasks', 'update_subdir')


def downgrade() -> None:
    op.add_column('tasks', sa.Column('update_subdir', sa.String(length=255), nullable=True))
    op.add_column('tasks', sa.Column('enddate', sa.String(length=32), nullable=True))