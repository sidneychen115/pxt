"""Build HA OHLC rows for ``ha_ohlc_bars`` from daily OHLC (month/week)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.core.config import settings
from src.strategies.ha_cache.calendar import current_calendar_month, last_completed_week_end
from src.strategies.ha_cache.lookback import friday_week_end_from_label
from src.strategies.heikin_ashi import heikin_ashi, resample_to_monthly, resample_to_weekly_mon_fri

_TZ = ZoneInfo(settings.timezone)

HA_TF_MONTH = "1mo"
HA_TF_WEEK = "1wk"


def _utc_ts(ts: pd.Timestamp) -> datetime:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.to_pydatetime().astimezone(timezone.utc)


def week_row_is_final(week_friday: date, as_of: datetime) -> bool:
    """Final if the week's Friday is on or before the last fully completed Fri before ``as_of``."""
    lf = last_completed_week_end(as_of)
    return week_friday <= lf


def compute_monthly_ha_rows_from_daily(
    daily: pd.DataFrame,
    instrument_id: int,
    *,
    as_of: datetime | None = None,
    source: str = "computed",
) -> list[dict]:
    """Return rows for :func:`~src.data.ha_ohlc_repository.upsert_ha_bars`."""
    as_of = as_of or datetime.now(timezone.utc)
    now_dt = datetime.now(timezone.utc)
    if daily.empty:
        return []
    monthly = resample_to_monthly(daily)
    if monthly.empty:
        return []
    ha = heikin_ashi(monthly)
    cy, cm = current_calendar_month(as_of)
    out: list[dict] = []
    for ts, row in ha.iterrows():
        local = pd.Timestamp(ts)
        if local.tzinfo is None:
            local = local.tz_localize("UTC").tz_convert(_TZ)
        else:
            local = local.tz_convert(_TZ)
        is_final = not (local.year == cy and local.month == cm)
        bt = _utc_ts(ts)
        out.append(
            {
                "instrument_id": instrument_id,
                "timeframe": HA_TF_MONTH,
                "bar_time": bt,
                "ha_open": float(row["ha_open"]),
                "ha_high": float(row["ha_high"]),
                "ha_low": float(row["ha_low"]),
                "ha_close": float(row["ha_close"]),
                "is_final": is_final,
                "source": source,
                "computed_at": now_dt,
            }
        )
    return out


def compute_weekly_ha_rows_from_daily(
    daily: pd.DataFrame,
    instrument_id: int,
    *,
    as_of: datetime | None = None,
    source: str = "computed",
) -> list[dict]:
    """Mon–Fri weeks (Fri labels); partial when week Friday is still in progress."""
    as_of = as_of or datetime.now(timezone.utc)
    now_dt = datetime.now(timezone.utc)
    if daily.empty:
        return []
    weekly = resample_to_weekly_mon_fri(daily)
    if weekly.empty:
        return []
    ha = heikin_ashi(weekly)
    out: list[dict] = []
    for ts, row in ha.iterrows():
        fri = friday_week_end_from_label(ts)
        is_final = week_row_is_final(fri, as_of)
        bt = _utc_ts(ts)
        out.append(
            {
                "instrument_id": instrument_id,
                "timeframe": HA_TF_WEEK,
                "bar_time": bt,
                "ha_open": float(row["ha_open"]),
                "ha_high": float(row["ha_high"]),
                "ha_low": float(row["ha_low"]),
                "ha_close": float(row["ha_close"]),
                "is_final": is_final,
                "source": source,
                "computed_at": now_dt,
            }
        )
    return out
