"""backtest_presets table

Revision ID: d4e5f7a9c0b2
Revises: c3d5e7f9b1a2
Create Date: 2026-04-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "d4e5f7a9c0b2"
down_revision: Union[str, None] = "c3d5e7f9b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtest_presets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("symbols", sa.Text(), nullable=False),
        sa.Column("initial_capital", sa.Numeric(16, 2), nullable=False),
        sa.Column("parameters", JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("exit_policy_form", JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_backtest_presets_created_at", "backtest_presets", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_backtest_presets_created_at", table_name="backtest_presets")
    op.drop_table("backtest_presets")
