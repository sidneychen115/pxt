"""backtest benchmark return and alpha vs benchmark

Revision ID: g7h8i9j0k1l2
Revises: f1a2b3c4d5e6
Create Date: 2026-04-18

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtests",
        sa.Column("benchmark_total_return", sa.Numeric(precision=10, scale=4), nullable=True),
    )
    op.add_column(
        "backtests",
        sa.Column("alpha_vs_benchmark", sa.Numeric(precision=10, scale=4), nullable=True),
    )
    desc = (
        "SuperTrend on pivot center line with optional SPY trend filter, ATR regime & volume gates, "
        "ATR sizing, SuperTrend stops. Add SPY for benchmark alpha. Use exit_policy for tighter loss cuts."
    )
    merge_params = {
        "timeframe": "1d",
        "benchmark_symbol": "SPY",
        "benchmark_ma_period": 200,
        "use_benchmark_long_filter": True,
        "use_atr_regime_filter": False,
        "atr_regime_period": 20,
        "min_atr_vs_ma_ratio": 0.85,
        "max_atr_vs_ma_ratio": None,
        "volume_ma_period": 20,
        "volume_confirm_mult": 0.0,
        "dollar_risk_pct": 0.0,
        "use_supertrend_stop_price": True,
    }
    # Bind JSON as text — embedding :200/:true in raw SQL is parsed as bind params by SQLAlchemy.
    op.get_bind().execute(
        sa.text(
            """
            UPDATE strategies
            SET
                description = :description,
                parameters = parameters || CAST(:merge_json AS jsonb)
            WHERE id = 'pivot_supertrend';
            """
        ),
        {"description": desc, "merge_json": json.dumps(merge_params)},
    )


def downgrade() -> None:
    op.drop_column("backtests", "alpha_vs_benchmark")
    op.drop_column("backtests", "benchmark_total_return")
