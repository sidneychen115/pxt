"""Aggregate daily bars into one week or month OHLC bar."""

from __future__ import annotations

import pandas as pd


def aggregate_ohlc(daily: pd.DataFrame) -> tuple[float, float, float, float] | None:
    if daily is None or daily.empty:
        return None
    d = daily.sort_index()
    return (
        float(d["open"].iloc[0]),
        float(d["high"].max()),
        float(d["low"].min()),
        float(d["close"].iloc[-1]),
    )
