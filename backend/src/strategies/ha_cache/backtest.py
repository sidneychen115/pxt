"""HA month open / week close for backtests (Mon–Fri weeks, no DB cache)."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from src.strategies.ha_cache.bars import daily_in_range, daily_through
from src.strategies.ha_cache.calendar import (
    as_of_local,
    current_week_start,
    last_completed_week_end,
)
from src.strategies.ha_cache.lookback import week_ha_open_close
from src.strategies.ha_cache.ohlc_agg import aggregate_ohlc
from src.strategies.heikin_ashi import heikin_ashi, heikin_ashi_single_bar, resample_to_monthly


def month_ha_open_backtest(daily: pd.DataFrame, as_of: datetime) -> float | None:
    """Current calendar month HA open from daily history (partial month included)."""
    hist = daily_through(daily, as_of)
    if hist.empty or len(hist) < 2:
        return None
    month_ohlc = resample_to_monthly(hist)
    if month_ohlc.empty:
        return None
    ha_m = heikin_ashi(month_ohlc)
    return float(ha_m["ha_open"].iloc[-1])


def week_ha_close_backtest(daily: pd.DataFrame, as_of: datetime) -> float | None:
    """In-progress Mon–Fri week HA close at ``as_of`` (matches live incremental logic)."""
    hist = daily_through(daily, as_of)
    if hist.empty:
        return None

    completed_friday = last_completed_week_end(as_of)
    anchor_hist = daily_in_range(hist, date(1900, 1, 1), completed_friday)
    pair = week_ha_open_close(anchor_hist, completed_friday)
    if pair is None:
        return None
    prev_o, prev_c = pair

    week_start = current_week_start(as_of)
    as_of_day = as_of_local(as_of)
    cur = daily_in_range(hist, week_start, as_of_day)
    ohlc = aggregate_ohlc(cur)
    if ohlc is None:
        return None

    *_, ha_close = heikin_ashi_single_bar(*ohlc, prev_o, prev_c)
    return ha_close
