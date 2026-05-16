"""seed ha_month_day_ma7_slots strategy row (HA cross SMA; filename generic)."""

from typing import Sequence, Union

from alembic import op

revision: str = "x8y9z0a1b2c4"
down_revision: Union[str, None] = "w6x7y8z9a0b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'ha_month_day_ma7_slots',
            'HA Month/Day + HA cross SMA (slots, no fundamentals)',
            'Monthly HA bullish (close > open) plus daily HA close crossing above SMA of regular closes '
            '(sma_period sets length, default 7; prior bar strictly below SMA, signal bar above); '
            'no SEC fundamentals; '
            'monthly exit when month HA closes below its open; universe order for fills; '
            'portfolio_size caps concurrent longs (default 20).',
            false,
            ARRAY['SPY'],
            ARRAY['1d'],
            '0 14 * * mon-fri',
            '{"timeframe": "1d", "portfolio_size": 20, "sma_period": 7, '
            '"backtest_fill_mode": "same_close", "snapshot_close_at_run": true, '
            '"account_equity": 100000}'::jsonb,
            200,
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'ha_month_day_ma7_slots';")
