"""ha_month_week_band: default cron 14:00 America/Chicago"""

from typing import Sequence, Union

from alembic import op

revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET run_frequency = '0 14 * * mon-fri',
            updated_at = now()
        WHERE id = 'ha_month_week_band'
          AND run_frequency IN ('0 16 * * 1-5', '1440m');
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET run_frequency = '0 16 * * 1-5',
            updated_at = now()
        WHERE id = 'ha_month_week_band';
    """)
