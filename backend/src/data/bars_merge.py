"""Merge DB-cached OHLC with yfinance gaps; detect full cache hits to skip network."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta

import pandas as pd

from src.core.app_timezone import app_zone, equity_daily_session_calendar_date

_DAILY_LIKE_TF = frozenset({"1d", "1wk", "1mo"})
# Weekends/holidays: first stored daily bar may be several calendar days after warmup start.
_DAILY_HEAD_SLACK_DAYS = 7
_MEMORY_CACHE_MAX = 512


def _bar_session_date(bar_time) -> date:
    if hasattr(bar_time, "to_pydatetime"):
        bar_time = bar_time.to_pydatetime()
    return equity_daily_session_calendar_date(bar_time)


def required_first_session_date(start: datetime, timeframe: str) -> date:
    """First trading session that must appear in cached bars."""
    return _bar_session_date(start)


def required_last_session_date(end: datetime, timeframe: str) -> date:
    """Last trading session that must appear in cached bars.

    Intraday backtests pass ``fetch_end`` as midnight at the start of the day *after*
    ``end_date`` (exclusive). The last required session is therefore ``end_date``, not
    that midnight instant (which would always look like a missing tail vs RTH bars).
    """
    if timeframe in _DAILY_LIKE_TF:
        return _bar_session_date(end)
    z = app_zone()
    aware = end if end.tzinfo is not None else end.replace(tzinfo=z)
    local = aware.astimezone(z)
    if (
        local.hour == 0
        and local.minute == 0
        and local.second == 0
        and local.microsecond == 0
    ):
        return local.date() - timedelta(days=1)
    return local.date()


def yfinance_gap_needed(
    cached: pd.DataFrame,
    start: datetime,
    end: datetime,
    timeframe: str,
) -> tuple[bool, bool]:
    """Return ``(needs_head_fetch, needs_tail_fetch)`` for [start, end]."""
    if cached.empty:
        return True, True
    req_start = required_first_session_date(start, timeframe)
    req_end = required_last_session_date(end, timeframe)
    first_sess = _bar_session_date(cached.index[0])
    last_sess = _bar_session_date(cached.index[-1])
    if timeframe in _DAILY_LIKE_TF:
        needs_head = first_sess > req_start and (first_sess - req_start).days > _DAILY_HEAD_SLACK_DAYS
    else:
        needs_head = first_sess > req_start
    needs_tail = last_sess < req_end
    return needs_head, needs_tail


def db_bars_cover_range(
    cached: pd.DataFrame,
    start: datetime,
    end: datetime,
    timeframe: str,
) -> bool:
    """True when ``cached`` already spans [start, end] (no yfinance head/tail needed)."""
    needs_head, needs_tail = yfinance_gap_needed(cached, start, end, timeframe)
    return not needs_head and not needs_tail


class BacktestOhlcMemoryCache:
    """Process-local cache of merged OHLC for identical backtest fetch windows."""

    def __init__(self, max_entries: int = _MEMORY_CACHE_MAX) -> None:
        self._max = max(1, max_entries)
        self._store: OrderedDict[tuple[str, str, str, str], pd.DataFrame] = OrderedDict()

    @staticmethod
    def key(sym: str, timeframe: str, start: datetime, end: datetime) -> tuple[str, str, str, str]:
        return (
            sym.strip().upper(),
            timeframe,
            pd.Timestamp(start).isoformat(),
            pd.Timestamp(end).isoformat(),
        )

    def get(self, sym: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame | None:
        k = self.key(sym, timeframe, start, end)
        hit = self._store.get(k)
        if hit is None:
            return None
        self._store.move_to_end(k)
        return hit.copy()

    def put(self, sym: str, timeframe: str, start: datetime, end: datetime, df: pd.DataFrame) -> None:
        if df.empty:
            return
        k = self.key(sym, timeframe, start, end)
        self._store[k] = df.copy()
        self._store.move_to_end(k)
        while len(self._store) > self._max:
            self._store.popitem(last=False)


_backtest_ohlc_memory_cache = BacktestOhlcMemoryCache()


def get_backtest_ohlc_memory_cache() -> BacktestOhlcMemoryCache:
    return _backtest_ohlc_memory_cache
