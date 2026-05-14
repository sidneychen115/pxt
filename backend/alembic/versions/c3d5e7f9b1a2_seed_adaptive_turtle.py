"""seed_adaptive_turtle

Revision ID: c3d5e7f9b1a2
Revises: b2c4e6f8a0d1
Create Date: 2026-04-18

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d5e7f9b1a2"
down_revision: Union[str, None] = "b2c4e6f8a0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'adaptive_turtle',
            'Adaptive Turtle (Donchian)',
            'Donchian breakout with optional SPY trend filter. Buy on N-day high breakout when benchmark is above its MA; sell on M-day low breakdown. Add SPY to symbols when using the filter.',
            false,
            ARRAY['SPY','QQQ','AAPL'],
            ARRAY['1d'],
            '0 16 * * 1-5',
            '{"fast_period": 20, "slow_period": 10, "benchmark_symbol": "SPY", "benchmark_ma_period": 200}'::jsonb,
            50,
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'adaptive_turtle';")
