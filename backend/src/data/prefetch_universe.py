"""Load HA OHLC bars and SEC fundamentals into shared DB (live + backtests)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.app_timezone import app_zone, daily_bar_timestamp_for_session_date
from src.core.models import Instrument
from src.data import repository as bar_repo
from src.data.fundamental_repository import insert_revenue_quarterly_ignore_conflicts
from src.data.ha_ohlc_compute import (
    compute_monthly_ha_rows_from_daily,
    compute_weekly_ha_rows_from_daily,
)
from src.data.ha_ohlc_repository import upsert_ha_bars
from src.data.providers.yfinance_provider import YFinanceProvider
from src.data.sec_edgar import (
    fetch_company_facts,
    parse_revenues_quarterly_usd,
    resolve_cik_for_ticker,
    revenue_rows_for_database,
)

logger = logging.getLogger(__name__)


def default_daily_end_date_yesterday(*, tz: str | None = None) -> date:
    """Calendar date of yesterday in the app timezone (default ``settings.timezone``)."""
    z = ZoneInfo(tz or settings.timezone)
    return (datetime.now(z) - timedelta(days=1)).date()


def _session_daily_bounds(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    """Inclusive ``bar_time`` range for anchored daily caches (Chicago session midnight)."""
    lo = daily_bar_timestamp_for_session_date(start_day)
    hi = daily_bar_timestamp_for_session_date(end_day)
    return lo, hi


def _max_calendar_gap_days_between_bars(df: pd.DataFrame) -> int:
    """Longest gap in **calendar days** between consecutive normalized daily bar timestamps.

    Weekends produce gaps of roughly 3 (Fri → Mon). Missing blocks of calendar **months/years**
    dominate and should exceed `GAP_CALENDAR_DAYS_YFIN_MERGE_THRESHOLD` so yfinance merges.
    """
    if df is None or df.empty:
        return 0
    if len(df) < 2:
        return 0
    ds = sorted({pd.Timestamp(ts).astimezone(app_zone()).date() for ts in df.index.unique()})
    return max(int((ds[i] - ds[i - 1]).days) for i in range(1, len(ds)))


# Beyond normal weekend/long-weekend clustering; suspicious for liquid US equities in range.
GAP_CALENDAR_DAYS_YFIN_MERGE_THRESHOLD = 21


def _daily_frame_repository_shape(df: pd.DataFrame) -> pd.DataFrame:
    """Columns/order compatible with HA compute + ``save_bars`` / ``get_bars_range`` outputs."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap"])
    d = df.copy()
    d = d.dropna(subset=["open", "high", "low", "close"])
    if "vwap" not in d.columns:
        d["vwap"] = None
    if "volume" not in d.columns:
        d["volume"] = 0
    cols = ["open", "high", "low", "close", "volume", "vwap"]
    missing = set(cols) - set(d.columns)
    if missing:
        raise ValueError(f"Daily frame missing columns: {sorted(missing)}")
    out = d[cols].copy()
    return out.sort_index()


async def _ensure_daily_history(
    session: AsyncSession,
    symbol: str,
    instrument_id: int,
    *,
    start_day: date,
    end_day: date,
    fill_if_sparse: bool = True,
    sparse_below: int = 120,
    force_yfinance_daily: bool = False,
) -> pd.DataFrame:
    """Return daily OHLC ascending inside ``[start_day, end_day]`` (calendar inclusive).

    Hybrid mode (``force_yfinance_daily=False``, default):
        merges from yfinance when the DB slice is sparse (**< sparse_below bars**) **or** when the
        longest **calendar** gap between consecutive bars is **≥**
        ``GAP_CALENDAR_DAYS_YFIN_MERGE_THRESHOLD`` (weekends ~3 days).

    Yahoo-only HA input (``force_yfinance_daily=True``):
        always downloads this window from yfinance (requires ``fill_if_sparse=True``); **HA is
        computed from that Yahoo slice**, not merged with unrelated DB candles.
        Rows are passed to ``save_bars`` (``ON CONFLICT DO NOTHING`` — existing differing-source
        days in DB remain unless you purge them separately).

    yfinance ``end`` is exclusive; ``end_day + 1`` is requested so the last session fits.
    """
    lo, hi = _session_daily_bounds(start_day, end_day)
    db_df = await bar_repo.get_bars_range(session, instrument_id, "1d", lo, hi)

    async def fetch_yfinance_slice() -> tuple[pd.DataFrame, pd.DataFrame | None]:
        yf_end = daily_bar_timestamp_for_session_date(end_day + timedelta(days=1))
        prov = YFinanceProvider()
        try:
            fetched = await prov.get_bars(symbol, "1d", lo, yf_end)
        except Exception as e:
            logger.warning("yfinance fetch failed for %s: %s", symbol, e)
            return pd.DataFrame(), None
        if fetched is None or fetched.empty:
            return pd.DataFrame(), None
        d_labels = pd.Series(
            [pd.Timestamp(x).astimezone(app_zone()).date() for x in fetched.index],
            index=fetched.index,
        )
        sl = fetched.loc[(d_labels >= start_day) & (d_labels <= end_day)].copy()
        if sl.empty:
            return pd.DataFrame(), None
        for_save = sl.copy()
        for_save["source"] = "yfinance"
        return sl, for_save

    if force_yfinance_daily:
        if not fill_if_sparse:
            raise ValueError(
                "force_yfinance_daily requires OHLC fills enabled "
                "(incompatible with fill_if_sparse=False / --no-yfinance-fill)"
            )
        plain, batch = await fetch_yfinance_slice()
        if batch is not None and not batch.empty:
            await bar_repo.save_bars(session, instrument_id, "1d", batch)
            await session.flush()
        if not plain.empty:
            cut = plain.drop(columns=["source"], errors="ignore")
            return _daily_frame_repository_shape(cut)
        logger.warning(
            "yfinance-only: empty Yahoo slice %s [%s,%s]; falling back to DB",
            symbol,
            start_day,
            end_day,
        )
        return db_df

    if not fill_if_sparse:
        return db_df

    df = db_df

    if df.empty or len(df) < sparse_below:
        needs_yfinance = True
    else:
        needs_yfinance = (
            _max_calendar_gap_days_between_bars(df)
            >= GAP_CALENDAR_DAYS_YFIN_MERGE_THRESHOLD
        )
    if not needs_yfinance:
        return df
    _, batch = await fetch_yfinance_slice()
    if batch is None or batch.empty:
        return df
    await bar_repo.save_bars(session, instrument_id, "1d", batch)
    await session.flush()
    return await bar_repo.get_bars_range(session, instrument_id, "1d", lo, hi)


async def prefetch_instrument_data(
    session: AsyncSession,
    symbol: str,
    *,
    instrument_type: str = "stock",
    daily_start_day: date | None = None,
    daily_end_day: date | None = None,
    yfinance_history_years: int = 12,
    as_of_for_ha: datetime | None = None,
    ha_month: bool = True,
    ha_week: bool = True,
    fundamentals: bool = True,
    fill_ohlc_if_missing: bool = True,
    force_yfinance_daily: bool = False,
) -> dict[str, object]:
    """Upsert HA month/week bars and SEC quarterly revenue (+YoY).

    Daily history is clipped to **[daily_start_day, daily_end_day]** (calendar-inclusive).
    If ``daily_end_day`` is omitted, it defaults to yesterday in ``settings.timezone``.
    If ``daily_start_day`` is omitted, it defaults to ``daily_end_day - yfinance_history_years``
    (~365 × years calendar days).

    ``as_of_for_ha`` affects partial vs finalized month/week flags; defaults to closing instant of
    ``daily_end_day`` in ``settings.timezone``.

    ``force_yfinance_daily``: use Yahoo-only daily slice for HA in this window (see
    :func:`_ensure_daily_history`).

    Persists ``instruments.sec_cik`` when the ticker resolves in SEC ticker JSON.
    """
    end_d = daily_end_day if daily_end_day is not None else default_daily_end_date_yesterday()
    if daily_start_day is not None:
        start_d = daily_start_day
    else:
        start_d = end_d - timedelta(days=365 * yfinance_history_years)
    if start_d > end_d:
        raise ValueError(f"Invalid range: daily_start_day {start_d} after daily_end_day {end_d}")

    z = ZoneInfo(settings.timezone)
    as_of = as_of_for_ha or datetime.combine(end_d, time(23, 59, 59), tzinfo=z)

    inst = await bar_repo.upsert_instrument(session, symbol, instrument_type)
    instrument_id = inst.id
    summary: dict[str, object] = {
        "symbol": symbol,
        "instrument_id": instrument_id,
        "daily_start_day": start_d,
        "daily_end_day": end_d,
        "daily_source": "yfinance" if force_yfinance_daily else "hybrid_db_first",
    }

    cik_digits = resolve_cik_for_ticker(symbol)
    if cik_digits:
        await session.execute(
            update(Instrument)
            .where(Instrument.id == instrument_id)
            .values(sec_cik=cik_digits)
        )

    mo_rows = wo_rows = 0
    if ha_month or ha_week:
        daily = await _ensure_daily_history(
            session,
            symbol,
            instrument_id,
            start_day=start_d,
            end_day=end_d,
            fill_if_sparse=fill_ohlc_if_missing,
            force_yfinance_daily=force_yfinance_daily,
        )
        summary["daily_bars"] = len(daily)
        if ha_month:
            rows = compute_monthly_ha_rows_from_daily(
                daily, instrument_id, as_of=as_of
            )
            await upsert_ha_bars(session, rows)
            mo_rows = len(rows)
        if ha_week:
            rows_w = compute_weekly_ha_rows_from_daily(
                daily, instrument_id, as_of=as_of
            )
            await upsert_ha_bars(session, rows_w)
            wo_rows = len(rows_w)
    summary["ha_month_rows"] = mo_rows
    summary["ha_week_rows"] = wo_rows

    fund_rows = 0
    if fundamentals and cik_digits:
        blob = fetch_company_facts(cik_digits)
        if blob:
            raw = parse_revenues_quarterly_usd(blob)
            db_rows = revenue_rows_for_database(instrument_id, raw)
            await insert_revenue_quarterly_ignore_conflicts(session, db_rows)
            fund_rows = len(db_rows)
        else:
            summary["fundamentals_error"] = "companyfacts empty or 404"
    elif fundamentals and not cik_digits:
        summary["fundamentals_error"] = "no SEC CIK for ticker"
    summary["fundamental_rows"] = fund_rows

    return summary
