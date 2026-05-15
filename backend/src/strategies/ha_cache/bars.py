"""Mon–Fri daily bar filters (America/Chicago)."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("America/Chicago")


def mon_fri_bars(daily: pd.DataFrame) -> pd.DataFrame:
    """Keep Mon–Fri session rows (America/Chicago)."""
    if daily is None or daily.empty:
        return daily
    d = daily.sort_index()
    idx = pd.DatetimeIndex(d.index)
    if idx.tz is not None:
        mask = idx.tz_convert(_TZ).weekday < 5
    else:
        mask = idx.weekday < 5
    return d.loc[mask]


def session_dates(index: pd.DatetimeIndex) -> pd.Series:
    if index.tz is not None:
        return pd.Series(index.tz_convert(_TZ).date, index=index)
    return pd.Series(index.date, index=index)


def daily_through(daily: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    """Bars on or before ``as_of`` (CT session date)."""
    if daily.empty:
        return daily
    d = mon_fri_bars(daily)
    cutoff = as_of.astimezone(_TZ).date() if as_of.tzinfo else as_of.date()
    dates = session_dates(pd.DatetimeIndex(d.index))
    return d.loc[dates <= cutoff]


def daily_in_range(daily: pd.DataFrame, start: date, end_inclusive: date) -> pd.DataFrame:
    if daily.empty:
        return daily
    d = mon_fri_bars(daily)
    dates = session_dates(pd.DatetimeIndex(d.index))
    return d.loc[(dates >= start) & (dates <= end_inclusive)]
