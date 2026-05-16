"""Rename BRK.B to BRK-B and fix symbol references across tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v4w5x6y8z9a2"
down_revision: Union[str, None] = "u3v4w5x6y7z8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "BRK.B"
_NEW = "BRK-B"


def _merge_instrument_row(conn, *, keep_id: int, drop_id: int) -> None:
    """Repoint FKs from duplicate instrument ``drop_id`` to canonical ``keep_id``.

    When both rows have conflicting children (same unique keys), rows on ``drop_id`` are deleted.
    """
    params = {"keep_id": keep_id, "drop_id": drop_id}

    conn.execute(
        sa.text(
            """DELETE FROM ha_ohlc_bars AS d USING ha_ohlc_bars AS k
WHERE d.instrument_id = :drop_id
  AND k.instrument_id = :keep_id
  AND k.timeframe = d.timeframe
  AND k.bar_time = d.bar_time"""
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE ha_ohlc_bars SET instrument_id = :keep_id WHERE instrument_id = :drop_id"
        ),
        params,
    )

    conn.execute(
        sa.text(
            """DELETE FROM fundamental_revenue_quarterly AS d
USING fundamental_revenue_quarterly AS k
WHERE d.instrument_id = :drop_id
  AND k.instrument_id = :keep_id
  AND k.accession = d.accession"""
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE fundamental_revenue_quarterly SET instrument_id = :keep_id "
            "WHERE instrument_id = :drop_id"
        ),
        params,
    )

    conn.execute(
        sa.text(
            """DELETE FROM ohlcv_bars AS d USING ohlcv_bars AS k
WHERE d.instrument_id = :drop_id
  AND k.instrument_id = :keep_id
  AND k.timeframe = d.timeframe
  AND k.bar_time = d.bar_time"""
        ),
        params,
    )
    conn.execute(
        sa.text("UPDATE ohlcv_bars SET instrument_id = :keep_id WHERE instrument_id = :drop_id"),
        params,
    )

    conn.execute(
        sa.text(
            """DELETE FROM ha_month_open_cache AS d USING ha_month_open_cache AS k
WHERE d.instrument_id = :drop_id
  AND k.instrument_id = :keep_id
  AND k.calendar_year = d.calendar_year
  AND k.calendar_month = d.calendar_month"""
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE ha_month_open_cache SET instrument_id = :keep_id WHERE instrument_id = :drop_id"
        ),
        params,
    )

    conn.execute(
        sa.text(
            """DELETE FROM ha_month_anchor_cache WHERE instrument_id = :keep_id
  AND EXISTS (
    SELECT 1 FROM ha_month_anchor_cache d WHERE d.instrument_id = :drop_id
  )"""
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE ha_month_anchor_cache SET instrument_id = :keep_id WHERE instrument_id = :drop_id"
        ),
        params,
    )

    conn.execute(
        sa.text(
            """DELETE FROM ha_week_anchor_cache WHERE instrument_id = :keep_id
  AND EXISTS (
    SELECT 1 FROM ha_week_anchor_cache d WHERE d.instrument_id = :drop_id
  )"""
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE ha_week_anchor_cache SET instrument_id = :keep_id WHERE instrument_id = :drop_id"
        ),
        params,
    )

    conn.execute(
        sa.text(
            """DELETE FROM user_positions AS k USING user_positions AS d
WHERE k.instrument_id = :keep_id
  AND d.instrument_id = :drop_id
  AND k.user_id = d.user_id"""
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE user_positions SET instrument_id = :keep_id WHERE instrument_id = :drop_id"
        ),
        params,
    )

    conn.execute(
        sa.text("UPDATE position_fills SET instrument_id = :keep_id WHERE instrument_id = :drop_id"),
        params,
    )
    conn.execute(
        sa.text("UPDATE trade_signals SET stock_id = :keep_id WHERE stock_id = :drop_id"),
        params,
    )


def upgrade() -> None:
    conn = op.get_bind()
    row_old = conn.execute(
        sa.text("SELECT id FROM instruments WHERE symbol = :o"),
        {"o": _OLD},
    ).fetchone()
    row_new = conn.execute(
        sa.text("SELECT id FROM instruments WHERE symbol = :n"),
        {"n": _NEW},
    ).fetchone()

    op.drop_constraint("options_underlying_fkey", "options", type_="foreignkey")

    conn.execute(
        sa.text("UPDATE options SET underlying = :n WHERE underlying = :o"),
        {"n": _NEW, "o": _OLD},
    )

    old_id = row_old[0] if row_old else None
    new_id = row_new[0] if row_new else None

    if old_id is not None and new_id is not None and old_id != new_id:
        _merge_instrument_row(conn, keep_id=new_id, drop_id=old_id)
        conn.execute(sa.text("DELETE FROM instruments WHERE id = :did"), {"did": old_id})
    elif old_id is not None and new_id is None:
        conn.execute(
            sa.text("UPDATE instruments SET symbol = :n WHERE symbol = :o"),
            {"n": _NEW, "o": _OLD},
        )

    op.create_foreign_key(
        "options_underlying_fkey",
        "options",
        "instruments",
        ["underlying"],
        ["symbol"],
    )

    conn.execute(
        sa.text(
            "UPDATE strategies SET symbols = array_replace(symbols, :o, :n) WHERE :o = ANY (symbols)"
        ),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text(
            "UPDATE user_strategies SET symbols = array_replace(symbols, :o, :n) "
            "WHERE :o = ANY (symbols)"
        ),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text(
            "UPDATE backtests SET symbols = array_replace(symbols, :o, :n) WHERE :o = ANY (symbols)"
        ),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text("UPDATE backtest_trades SET symbol = :n WHERE symbol = :o"),
        {"n": _NEW, "o": _OLD},
    )
    conn.execute(
        sa.text("UPDATE backtest_presets SET symbols = REPLACE(symbols, :o, :n) WHERE symbols LIKE :pat"),
        {"o": _OLD, "n": _NEW, "pat": "%" + _OLD + "%"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    row_new = conn.execute(
        sa.text("SELECT id FROM instruments WHERE symbol = :n"),
        {"n": _NEW},
    ).fetchone()
    if not row_new:
        return

    op.drop_constraint("options_underlying_fkey", "options", type_="foreignkey")

    conn.execute(
        sa.text("UPDATE options SET underlying = :o WHERE underlying = :n"),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text("UPDATE instruments SET symbol = :o WHERE symbol = :n"),
        {"o": _OLD, "n": _NEW},
    )

    op.create_foreign_key(
        "options_underlying_fkey",
        "options",
        "instruments",
        ["underlying"],
        ["symbol"],
    )

    conn.execute(
        sa.text(
            "UPDATE strategies SET symbols = array_replace(symbols, :n, :o) WHERE :n = ANY (symbols)"
        ),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text(
            "UPDATE user_strategies SET symbols = array_replace(symbols, :n, :o) "
            "WHERE :n = ANY (symbols)"
        ),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text(
            "UPDATE backtests SET symbols = array_replace(symbols, :n, :o) WHERE :n = ANY (symbols)"
        ),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text("UPDATE backtest_trades SET symbol = :o WHERE symbol = :n"),
        {"o": _OLD, "n": _NEW},
    )
    conn.execute(
        sa.text("UPDATE backtest_presets SET symbols = REPLACE(symbols, :n, :o) WHERE symbols LIKE :pat"),
        {"o": _OLD, "n": _NEW, "pat": "%" + _NEW + "%"},
    )
