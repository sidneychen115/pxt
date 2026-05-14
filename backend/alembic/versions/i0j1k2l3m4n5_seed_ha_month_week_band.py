"""seed ha_month_week_band strategy row"""

from typing import Sequence, Union

from alembic import op


revision: str = "i0j1k2l3m4n5"
down_revision: Union[str, None] = "h9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'ha_month_week_band',
            'HA Month Open vs Weekly Close (band)',
            'Monthly Heikin-Ashi open (current calendar month) vs weekly HA close (W-FRI) with symmetric band; backtest fills at signal bar close.',
            false,
            ARRAY['SPY'],
            ARRAY['1d'],
            '0 16 * * 1-5',
            '{"timeframe": "1d", "band_pct": 0.0, "band_abs": 0.0, "backtest_fill_mode": "same_close"}'::jsonb,
            50,
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'ha_month_week_band';")
