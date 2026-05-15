"""HA month open and week anchor cache tables"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "l3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ha_month_open_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("calendar_year", sa.Integer(), nullable=False),
        sa.Column("calendar_month", sa.Integer(), nullable=False),
        sa.Column("ha_open", sa.Numeric(16, 6), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "calendar_year",
            "calendar_month",
            name="uq_ha_month_open_instrument_ym",
        ),
    )
    op.create_index(
        "idx_ha_month_open_lookup",
        "ha_month_open_cache",
        ["instrument_id", "calendar_year", "calendar_month"],
    )

    op.create_table(
        "ha_week_anchor_cache",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("week_end_date", sa.Date(), nullable=False),
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
    op.drop_table("ha_week_anchor_cache")
    op.drop_index("idx_ha_month_open_lookup", table_name="ha_month_open_cache")
    op.drop_table("ha_month_open_cache")
