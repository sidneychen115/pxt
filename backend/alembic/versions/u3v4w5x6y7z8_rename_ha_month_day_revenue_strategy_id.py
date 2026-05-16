"""Rename strategy id ha_month_day_revenue_top20 -> ha_month_day_revenue_slots

Revision ID: u3v4w5x6y7z8
Revises: t2u3v4w5x6y7
"""

from typing import Sequence, Union

from alembic import op

revision: str = "u3v4w5x6y7z8"
down_revision: Union[str, None] = "t2u3v4w5x6y7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        )
        SELECT
            'ha_month_day_revenue_slots',
            'HA Month/Day + SEC Revenue YoY (ranked slots)',
            'Monthly and daily Heikin-Ashi filters with SEC quarterly revenue YoY ranking; '
            'concurrent long count capped by portfolio_size (default 20); monthly exit '
            'when month HA closes below its open; live fills use mark-price snapshot at run time.',
            is_active,
            symbols,
            timeframes,
            run_frequency,
            parameters,
            max_symbols,
            now()
        FROM strategies
        WHERE id = 'ha_month_day_revenue_top20'
          AND NOT EXISTS (
              SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_slots'
          );
    """)
    op.execute("""
        UPDATE user_strategies SET strategy_id = 'ha_month_day_revenue_slots'
        WHERE strategy_id = 'ha_month_day_revenue_top20'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_slots');
    """)
    op.execute("""
        UPDATE trade_signals SET strategy_id = 'ha_month_day_revenue_slots'
        WHERE strategy_id = 'ha_month_day_revenue_top20'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_slots');
    """)
    op.execute("""
        UPDATE backtests SET strategy_id = 'ha_month_day_revenue_slots'
        WHERE strategy_id = 'ha_month_day_revenue_top20'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_slots');
    """)
    op.execute("""
        UPDATE backtest_presets SET strategy_id = 'ha_month_day_revenue_slots'
        WHERE strategy_id = 'ha_month_day_revenue_top20'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_slots');
    """)
    op.execute(
        "DELETE FROM strategies WHERE id = 'ha_month_day_revenue_top20';"
    )


def downgrade() -> None:
    op.execute("""
        INSERT INTO strategies (
            id, name, description, is_active,
            symbols, timeframes, run_frequency,
            parameters, max_symbols, updated_at
        )
        SELECT
            'ha_month_day_revenue_top20',
            name,
            description,
            is_active,
            symbols,
            timeframes,
            run_frequency,
            parameters,
            max_symbols,
            now()
        FROM strategies
        WHERE id = 'ha_month_day_revenue_slots'
          AND NOT EXISTS (
              SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_top20'
          );
    """)
    op.execute("""
        UPDATE user_strategies SET strategy_id = 'ha_month_day_revenue_top20'
        WHERE strategy_id = 'ha_month_day_revenue_slots'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_top20');
    """)
    op.execute("""
        UPDATE trade_signals SET strategy_id = 'ha_month_day_revenue_top20'
        WHERE strategy_id = 'ha_month_day_revenue_slots'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_top20');
    """)
    op.execute("""
        UPDATE backtests SET strategy_id = 'ha_month_day_revenue_top20'
        WHERE strategy_id = 'ha_month_day_revenue_slots'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_top20');
    """)
    op.execute("""
        UPDATE backtest_presets SET strategy_id = 'ha_month_day_revenue_top20'
        WHERE strategy_id = 'ha_month_day_revenue_slots'
          AND EXISTS (SELECT 1 FROM strategies WHERE id = 'ha_month_day_revenue_top20');
    """)
    op.execute("DELETE FROM strategies WHERE id = 'ha_month_day_revenue_slots';")
