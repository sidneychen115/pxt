"""seed_pivot_supertrend

Revision ID: 86894cd676cb
Revises: e47ea07f0ffe
Create Date: 2026-04-17 22:09:04.784503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86894cd676cb'
down_revision: Union[str, None] = 'e47ea07f0ffe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'pivot_supertrend',
            'Pivot Point SuperTrend',
            'SuperTrend built on pivot-point center line. Buys on bullish trend flip, sells on bearish trend flip.',
            false,
            ARRAY['SPY','QQQ','AAPL','TSLA','NVDA'],
            ARRAY['1d'],
            '0 16 * * 1-5',
            '{"pivot_period": 2, "atr_factor": 3.0, "atr_period": 10}'::jsonb,
            50,
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'pivot_supertrend';")
