"""Sync ha_month_day_ma7_slots display text (configurable sma_period)."""

from typing import Sequence, Union

from alembic import op

revision: str = "y9z0a1b2c3d5"
down_revision: Union[str, None] = "x8y9z0a1b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            name = 'HA Month/Day + HA cross SMA (slots, no fundamentals)',
            description = 'Monthly HA bullish (close > open) plus daily HA close crossing above SMA of regular closes '
                '(sma_period sets length, default 7; prior bar strictly below SMA, signal bar above); '
                'no SEC fundamentals; '
                'monthly exit when month HA closes below its open; universe order for fills; '
                'portfolio_size caps concurrent longs (default 20).',
            updated_at = now()
        WHERE id = 'ha_month_day_ma7_slots';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            name = 'HA Month/Day + SMA (slots, no fundamentals)',
            description = 'Monthly HA bullish (close > open) plus daily HA close above SMA on regular closes '
                '(same technical entry as revenue slots, without SEC fundamentals); '
                'monthly exit when month HA closes below its open; universe order for fills; '
                'portfolio_size caps concurrent longs (default 20).',
            updated_at = now()
        WHERE id = 'ha_month_day_ma7_slots';
    """)
