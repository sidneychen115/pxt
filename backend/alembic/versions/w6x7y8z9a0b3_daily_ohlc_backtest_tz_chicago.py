"""Normalize daily-like OHLC and backtest session timestamps to app-timezone session midnight.

Assumes existing rows used **UTC midnight** for session calendar dates (pre-revision behavior).
``TIMEZONE`` env (default ``America/Chicago``, same as ``settings.timezone``) must match the zone
used in application config. Do not run twice on already-migrated rows.
"""

import os
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w6x7y8z9a0b3"
down_revision: Union[str, None] = "v4w5x6y8z9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TF = "'1d', '1wk', '1mo'"


def _app_tz_sql() -> str:
    raw = os.environ.get("TIMEZONE", "America/Chicago")
    if not re.fullmatch(r"[A-Za-z0-9_/+\-]+", raw):
        raise ValueError(f"Invalid TIMEZONE for SQL: {raw!r}")
    return raw.replace("'", "''")


def upgrade() -> None:
    z = _app_tz_sql()
    # One statement per op.execute: asyncpg cannot run multiple commands in one prepared statement.
    op.execute(
        sa.text(
            f"""
            UPDATE ohlcv_bars
            SET bar_time = (((bar_time AT TIME ZONE 'UTC')::date) AT TIME ZONE '{z}')
            WHERE timeframe IN ({_TF})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE backtest_trades
            SET entry_time = (((entry_time AT TIME ZONE 'UTC')::date) AT TIME ZONE '{z}')
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE backtest_trades
            SET exit_time = (((exit_time AT TIME ZONE 'UTC')::date) AT TIME ZONE '{z}')
            WHERE exit_time IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    z = _app_tz_sql()
    op.execute(
        sa.text(
            f"""
            UPDATE ohlcv_bars
            SET bar_time = (((bar_time AT TIME ZONE '{z}')::date) AT TIME ZONE 'UTC')
            WHERE timeframe IN ({_TF})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE backtest_trades
            SET entry_time = (((entry_time AT TIME ZONE '{z}')::date) AT TIME ZONE 'UTC')
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE backtest_trades
            SET exit_time = (((exit_time AT TIME ZONE '{z}')::date) AT TIME ZONE 'UTC')
            WHERE exit_time IS NOT NULL
            """
        )
    )
