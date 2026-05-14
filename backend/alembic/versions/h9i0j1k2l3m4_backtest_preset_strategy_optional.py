"""backtest_presets.strategy_id nullable (presets no longer bind a strategy)

Revision ID: h9i0j1k2l3m4
Revises: g7h8i9j0k1l2
Create Date: 2026-04-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h9i0j1k2l3m4"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "backtest_presets",
        "strategy_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE backtest_presets AS p
        SET strategy_id = (SELECT s.id FROM strategies AS s ORDER BY s.id LIMIT 1)
        WHERE p.strategy_id IS NULL
          AND EXISTS (SELECT 1 FROM strategies LIMIT 1)
        """
    )
    op.execute("DELETE FROM backtest_presets WHERE strategy_id IS NULL")
    op.alter_column(
        "backtest_presets",
        "strategy_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
