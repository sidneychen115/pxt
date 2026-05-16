"""seed_chan_bi_fractal_mvp"""

from typing import Sequence, Union

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "z9a0b1c2d4e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'chan_bi_fractal_mvp',
            'Chan MVP: fractal confirm (daily OHLC)',
            'Daily OHLC: K-line inclusion merge, strict fractals; buy on confirmed bottom (optional SMA filter), '
            'sell on confirmed top. Coarse Chan MVP for backtests.',
            false,
            ARRAY['SPY'],
            ARRAY['1d'],
            '0 16 * * 1-5',
            '{"timeframe": "1d", "sma_period": 20, "use_sma_filter": true, "bar_limit": 240}'::jsonb,
            100,
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'chan_bi_fractal_mvp';")
