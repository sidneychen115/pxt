"""Heikin-Ashi and OHLC resampling helpers for strategies."""

from __future__ import annotations

import pandas as pd


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

    o = ohlc["open"].astype(float)
    h = ohlc["high"].astype(float)
    l = ohlc["low"].astype(float)
    c = ohlc["close"].astype(float)

    ha_close = (o + h + l + c) / 4.0
    ha_open = pd.Series(index=ohlc.index, dtype=float)
    ha_high = pd.Series(index=ohlc.index, dtype=float)
    ha_low = pd.Series(index=ohlc.index, dtype=float)

    ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2.0
    ha_high.iloc[0] = max(h.iloc[0], ha_open.iloc[0], ha_close.iloc[0])
    ha_low.iloc[0] = min(l.iloc[0], ha_open.iloc[0], ha_close.iloc[0])

    for i in range(1, len(ohlc)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0
        ha_high.iloc[i] = max(h.iloc[i], ha_open.iloc[i], ha_close.iloc[i])
        ha_low.iloc[i] = min(l.iloc[i], ha_open.iloc[i], ha_close.iloc[i])

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


def resample_to_weekly_friday(daily: pd.DataFrame) -> pd.DataFrame:
    """Week ending Friday (common US equity convention); partial week as last row."""
    if daily.empty:
        return daily.copy()
    agg = _agg_ohlc()
    if "volume" in daily.columns:
        agg["volume"] = "sum"
    out = daily.sort_index().resample("W-FRI").agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"], how="any")
