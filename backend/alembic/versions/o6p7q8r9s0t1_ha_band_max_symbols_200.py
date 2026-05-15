"""ha_month_week_band: raise max_symbols to 200 for large watchlists"""

from typing import Sequence, Union

from alembic import op

revision: str = "o6p7q8r9s0t1"
down_revision: Union[str, None] = "n5o6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET max_symbols = 200
        WHERE id = 'ha_month_week_band';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET max_symbols = 50
        WHERE id = 'ha_month_week_band';
    """)
