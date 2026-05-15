"""ha_month_anchor_cache for incremental monthly HA"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "m4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ha_month_anchor_cache",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("calendar_year", sa.Integer(), nullable=False),
        sa.Column("calendar_month", sa.Integer(), nullable=False),
        sa.Column("ha_open", sa.Numeric(16, 6), nullable=False),
        sa.Column("ha_close", sa.Numeric(16, 6), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("instrument_id"),
    )


def downgrade() -> None:
    op.drop_table("ha_month_anchor_cache")
