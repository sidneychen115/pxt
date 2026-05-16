"""HA OHLC bars (month/week partial+final), SEC fundamentals, instruments.sec_cik

Revision ID: r0s1t2u3v4w5
Revises: p7q8r9s0t1u2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r0s1t2u3v4w5"
down_revision: Union[str, None] = "p7q8r9s0t1u2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instruments",
        sa.Column("sec_cik", sa.String(length=10), nullable=True),
    )

    op.create_table(
        "ha_ohlc_bars",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(length=6), nullable=False),
        sa.Column("bar_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ha_open", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.Column("ha_high", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.Column("ha_low", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.Column("ha_close", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.Column(
            "is_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="computed"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "bar_time",
            name="uq_ha_ohlc_instrument_tf_bar_time",
        ),
    )
    op.create_index(
        "idx_ha_ohlc_lookup",
        "ha_ohlc_bars",
        ["instrument_id", "timeframe", "bar_time"],
        unique=False,
    )
    op.create_index(
        "idx_ha_ohlc_partial",
        "ha_ohlc_bars",
        ["instrument_id", "timeframe", "is_final"],
        unique=False,
    )

    op.create_table(
        "fundamental_revenue_quarterly",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("accession", sa.String(length=32), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_form", sa.String(length=10), nullable=True),
        sa.Column("fiscal_period", sa.String(length=8), nullable=True),
        sa.Column("calendar_frame", sa.String(length=12), nullable=True),
        sa.Column("revenue_usd", sa.BigInteger(), nullable=False),
        sa.Column("revenue_yoy", sa.Numeric(precision=16, scale=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "accession",
            name="uq_fund_rev_inst_accn",
        ),
    )
    op.create_index(
        "idx_fund_rev_inst_filed",
        "fundamental_revenue_quarterly",
        ["instrument_id", "filing_date"],
        unique=False,
    )
    op.create_index(
        "idx_fund_rev_inst_frame",
        "fundamental_revenue_quarterly",
        ["instrument_id", "calendar_frame"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_fund_rev_inst_frame", table_name="fundamental_revenue_quarterly")
    op.drop_index("idx_fund_rev_inst_filed", table_name="fundamental_revenue_quarterly")
    op.drop_table("fundamental_revenue_quarterly")
    op.drop_index("idx_ha_ohlc_partial", table_name="ha_ohlc_bars")
    op.drop_index("idx_ha_ohlc_lookup", table_name="ha_ohlc_bars")
    op.drop_table("ha_ohlc_bars")
    op.drop_column("instruments", "sec_cik")
