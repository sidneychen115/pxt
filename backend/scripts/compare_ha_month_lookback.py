#!/usr/bin/env python3
"""Compare monthly HA open for a target month under different daily lookback windows.

Example:
  cd backend && uv run python scripts/compare_ha_month_lookback.py --symbol SPY --year 2026 --month 5
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from src.strategies.heikin_ashi import heikin_ashi, resample_to_monthly

TZ = ZoneInfo("America/Chicago")


def fetch_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    df = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close"]].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    return df.dropna(subset=["open", "close"])


def month_ha_open_from_daily(daily: pd.DataFrame, year: int, month: int) -> float | None:
    monthly = resample_to_monthly(daily)
    if monthly.empty:
        return None
    ha = heikin_ashi(monthly)
    # Match target calendar month (month-end index in CT)
    for ts, row in ha.iterrows():
        local = pd.Timestamp(ts).tz_convert(TZ)
        if local.year == year and local.month == month:
            return float(row["ha_open"])
    return None


def lookback_start(target: date, months: int) -> date:
    y, m = target.year, target.month - months
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--year", type=int, default=2026)
    p.add_argument("--month", type=int, default=5)
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today UTC)")
    args = p.parse_args()

    if args.as_of:
        as_of = date.fromisoformat(args.as_of)
    else:
        as_of = datetime.now(timezone.utc).astimezone(TZ).date()

    target = date(args.year, args.month, 1)
    windows = [12, 24, 36, 60, 120]

    # Full available from yfinance (~ decades) as reference
    full_start = date(1993, 1, 1)
    full_daily = fetch_daily(args.symbol, full_start, as_of)
    full_val = month_ha_open_from_daily(full_daily, args.year, args.month)

    print(f"Symbol: {args.symbol}")
    print(f"Target: {args.year}-{args.month:02d} monthly HA open (as_of {as_of}, America/Chicago)")
    print(f"Reference (max history ~{len(full_daily)} daily bars): {full_val!r}")
    print()
    print(f"{'Lookback months':>16}  {'Start date':>12}  {'Daily bars':>10}  {'HA open':>14}  {'Δ vs full':>12}")

    for months in windows:
        start = lookback_start(target, months)
        daily = fetch_daily(args.symbol, start, as_of)
        val = month_ha_open_from_daily(daily, args.year, args.month)
        delta = (val - full_val) if val is not None and full_val is not None else None
        delta_s = f"{delta:+.6f}" if delta is not None else "n/a"
        val_s = f"{val:.6f}" if val is not None else "n/a"
        print(f"{months:>16}  {start!s:>12}  {len(daily):>10}  {val_s:>14}  {delta_s:>12}")


if __name__ == "__main__":
    main()
