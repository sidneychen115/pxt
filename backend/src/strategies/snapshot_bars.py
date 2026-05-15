"""Merge a live market price into daily OHLC as the session close (scheduled runs)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd


def quote_mark_price(quote: dict) -> float | None:
    """Best-effort last trade; mid if needed."""
    last = quote.get("last")
    if last is not None and pd.notna(last):
        return float(last)
    bid, ask = quote.get("bid"), quote.get("ask")
    if bid is not None and ask is not None and pd.notna(bid) and pd.notna(ask):
        return (float(bid) + float(ask)) / 2.0
    return None


def _bar_session_date(ts: pd.Timestamp, tz: ZoneInfo) -> date:
    if ts.tzinfo is None:
        return ts.date()
    return ts.tz_convert(tz).date()


def merge_snapshot_close_into_daily(
    daily: pd.DataFrame,
    *,
    mark_price: float,
    as_of: datetime,
    tz: ZoneInfo,
) -> pd.DataFrame:
    """Update or append today's daily bar using ``mark_price`` as close (and H/L bounds)."""
    if daily.empty:
        idx = pd.Timestamp(as_of.astimezone(tz).date(), tz=tz)
        row = {
            "open": mark_price,
            "high": mark_price,
            "low": mark_price,
            "close": mark_price,
            "volume": 0.0,
        }
        return pd.DataFrame([row], index=[idx])

    out = daily.sort_index().copy()
    session_day = as_of.astimezone(tz).date()
    price = float(mark_price)

    last_ts = out.index[-1]
    last_day = _bar_session_date(pd.Timestamp(last_ts), tz)

    if last_day == session_day:
        h = float(out["high"].iloc[-1])
        l = float(out["low"].iloc[-1])
        out.iloc[-1, out.columns.get_loc("close")] = price
        out.iloc[-1, out.columns.get_loc("high")] = max(h, price)
        out.iloc[-1, out.columns.get_loc("low")] = min(l, price)
        return out

    prev_close = float(out["close"].iloc[-1])
    open_px = prev_close
    idx = pd.Timestamp(session_day, tz=tz)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC")
    new_row = {
        "open": open_px,
        "high": max(open_px, price),
        "low": min(open_px, price),
        "close": price,
    }
    if "volume" in out.columns:
        new_row["volume"] = 0.0
    if "vwap" in out.columns:
        new_row["vwap"] = None
    return pd.concat([out, pd.DataFrame([new_row], index=[idx])]).sort_index()
