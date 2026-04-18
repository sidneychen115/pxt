"""seed_ma_crossover

Revision ID: 7a1f7c8c5357
Revises: 3af5a19a14c9
Create Date: 2026-04-18 00:13:33.817409

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1f7c8c5357'
down_revision: Union[str, None] = '3af5a19a14c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        ) VALUES (
            'ma_crossover',
            'Moving Average Crossover',
            'EMA crossover strategy: buy on golden cross, sell on death cross.',
            false,
            ARRAY['SPY'],
            ARRAY['1d'],
            '0 16 * * 1-5',
            '{"fast": 10, "slow": 30}'::jsonb,
            50,
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE id = 'ma_crossover';")
