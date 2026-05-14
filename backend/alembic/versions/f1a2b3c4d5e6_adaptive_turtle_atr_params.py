"""merge ATR sizing parameters into adaptive_turtle strategy row

Revision ID: f1a2b3c4d5e6
Revises: d4e5f7a9c0b2
Create Date: 2026-04-18

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d4e5f7a9c0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET
            parameters = parameters || '{"atr_period": 20, "dollar_risk_pct": 0.01}'::jsonb,
            description = 'Donchian breakout with optional SPY trend filter and ATR-based position sizing. Buy on N-day high breakout when benchmark is above its MA; sell on M-day low breakdown. Add SPY to symbols when using the filter.'
        WHERE id = 'adaptive_turtle';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET
            parameters = parameters - 'atr_period' - 'dollar_risk_pct',
            description = 'Donchian breakout with optional SPY trend filter. Buy on N-day high breakout when benchmark is above its MA; sell on M-day low breakdown. Add SPY to symbols when using the filter.'
        WHERE id = 'adaptive_turtle';
    """)
