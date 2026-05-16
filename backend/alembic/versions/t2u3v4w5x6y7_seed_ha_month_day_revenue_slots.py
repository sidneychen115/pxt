"""seed ha_month_day_revenue_slots strategy row"""

from typing import Sequence, Union

from alembic import op

revision: str = "t2u3v4w5x6y7"
down_revision: Union[str, None] = "r0s1t2u3v4w5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'ha_month_day_revenue_slots',
            'HA Month/Day + SEC Revenue YoY (ranked slots)',
            'Monthly and daily Heikin-Ashi filters with SEC quarterly revenue YoY ranking; '
            'concurrent long count capped by portfolio_size (default 20); monthly exit '
            'when month HA closes below its open; live fills use mark-price snapshot at run time.',
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
    op.execute("DELETE FROM strategies WHERE id = 'ha_month_day_revenue_slots';")
