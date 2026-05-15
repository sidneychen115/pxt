"""Heikin-Ashi and OHLC resampling helpers for strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd


def heikin_ashi_single_bar(
    open_: float,
    high: float,
    low: float,
    close: float,
    prev_ha_open: float,
    prev_ha_close: float,
) -> tuple[float, float, float, float]:
    """HA for one bar given prior bar HA open/close."""
    ha_close = (open_ + high + low + close) / 4.0
    ha_open = (prev_ha_open + prev_ha_close) / 2.0
    ha_high = max(high, ha_open, ha_close)
    ha_low = min(low, ha_open, ha_close)
    return ha_open, ha_high, ha_low, ha_close


def heikin_ashi(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Compute Heikin-Ashi OHLC on a regular OHLC DataFrame (sorted index).

    First bar: HA_Open = (O + C) / 2. Subsequent HA_Open = (HA_O_prev + HA_C_prev) / 2.
    """
    if ohlc.empty:
        return pd.DataFrame(
            columns=["ha_open", "ha_high", "ha_low", "ha_close"]
        ).reindex(ohlc.index)
    need = {"open", "high", "low", "close"}
    miss = need - set(ohlc.columns)
    if miss:
        raise ValueError(f"heikin_ashi: missing columns {sorted(miss)}")

    o = ohlc["open"].astype(float).to_numpy()
    h = ohlc["high"].astype(float).to_numpy()
    l = ohlc["low"].astype(float).to_numpy()
    c = ohlc["close"].astype(float).to_numpy()
    n = len(o)

    ha_close = (o + h + l + c) / 4.0
    ha_open = np.empty(n, dtype=float)
    ha_high = np.empty(n, dtype=float)
    ha_low = np.empty(n, dtype=float)

    ha_open[0] = (o[0] + c[0]) / 2.0
    ha_high[0] = max(h[0], ha_open[0], ha_close[0])
    ha_low[0] = min(l[0], ha_open[0], ha_close[0])

    for i in range(1, n):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
        ha_high[i] = max(h[i], ha_open[i], ha_close[i])
        ha_low[i] = min(l[i], ha_open[i], ha_close[i])

    return pd.DataFrame(
        {"ha_open": ha_open, "ha_high": ha_high, "ha_low": ha_low, "ha_close": ha_close},
        index=ohlc.index,
    )


def _agg_ohlc() -> dict[str, str]:
    d: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    return d


def resample_to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Calendar month-end buckets (partial current month as last row)."""
    if daily.empty:
        return daily.copy()
    agg = _agg_ohlc()
    if "volume" in daily.columns:
        agg["volume"] = "sum"
    out = daily.sort_index().resample("ME").agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"], how="any")


def resample_to_weekly_mon_fri(daily: pd.DataFrame) -> pd.DataFrame:
    """Mon–Fri trading week ending Friday (America/Chicago weekdays only); partial week OK."""
    if daily.empty:
        return daily.copy()
    d = daily.sort_index()
    idx = pd.DatetimeIndex(d.index)
    if idx.tz is not None:
        weekday_mask = idx.tz_convert("America/Chicago").weekday < 5
    else:
        weekday_mask = idx.weekday < 5
    d = d.loc[weekday_mask]
    if d.empty:
        return d.copy()
    agg = _agg_ohlc()
    if "volume" in daily.columns:
        agg["volume"] = "sum"
    out = d.resample("W-FRI").agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"], how="any")


def resample_to_weekly_friday(daily: pd.DataFrame) -> pd.DataFrame:
    """Alias for :func:`resample_to_weekly_mon_fri` (Mon–Fri week, label Friday)."""
    return resample_to_weekly_mon_fri(daily)
