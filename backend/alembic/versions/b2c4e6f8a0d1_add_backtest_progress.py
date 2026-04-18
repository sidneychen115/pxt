"""add_backtest_progress

Revision ID: b2c4e6f8a0d1
Revises: 7a1f7c8c5357
Create Date: 2026-04-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c4e6f8a0d1'
down_revision: Union[str, None] = '7a1f7c8c5357'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('backtests', sa.Column('progress_phase', sa.String(length=32), nullable=True))
    op.add_column('backtests', sa.Column('progress_message', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('backtests', 'progress_message')
    op.drop_column('backtests', 'progress_phase')
