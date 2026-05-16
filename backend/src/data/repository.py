from datetime import datetime
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models import Instrument, OhlcvBar


async def upsert_instrument(session: AsyncSession, symbol: str, type_: str, **kwargs) -> Instrument:
    updates = {k: v for k, v in kwargs.items() if v is not None}
    updates["type"] = type_
    stmt = (
        insert(Instrument)
        .values(symbol=symbol, type=type_, **kwargs)
        .on_conflict_do_update(index_elements=["symbol"], set_=updates)
        .returning(Instrument)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def save_bars(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
    df: pd.DataFrame,
) -> int:
    """Insert bars, skip duplicates. Returns count of new rows inserted."""
    if df.empty:
        return 0
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        return 0
    rows = [
        {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "bar_time": idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
            "vwap": float(row["vwap"]) if pd.notna(row.get("vwap")) else None,
            "source": row["source"],
        }
        for idx, row in df.iterrows()
    ]
    stmt = insert(OhlcvBar).values(rows).on_conflict_do_nothing()
    result = await session.execute(stmt)
    return result.rowcount


async def get_bars(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
    limit: int = 200,
    end_before: datetime | None = None,
) -> pd.DataFrame:
    query = (
        select(OhlcvBar)
        .where(OhlcvBar.instrument_id == instrument_id, OhlcvBar.timeframe == timeframe)
    )
    if end_before:
        query = query.where(OhlcvBar.bar_time < end_before)
    query = query.order_by(OhlcvBar.bar_time.desc()).limit(limit)
    result = await session.execute(query)
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap"])
    df = pd.DataFrame([
        {"bar_time": b.bar_time, "open": float(b.open), "high": float(b.high),
         "low": float(b.low), "close": float(b.close),
         "volume": b.volume, "vwap": float(b.vwap) if b.vwap is not None else None}
        for b in bars
    ]).set_index("bar_time").sort_index()
    return df


async def get_bars_range(
    session: AsyncSession,
    instrument_id: int,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Return all bars for instrument between start and end (inclusive)."""
    result = await session.execute(
        select(OhlcvBar)
        .where(
            OhlcvBar.instrument_id == instrument_id,
            OhlcvBar.timeframe == timeframe,
            OhlcvBar.bar_time >= start,
            OhlcvBar.bar_time <= end,
        )
        .order_by(OhlcvBar.bar_time)
    )
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap"])
    return pd.DataFrame([
        {"bar_time": b.bar_time, "open": float(b.open), "high": float(b.high),
         "low": float(b.low), "close": float(b.close),
         "volume": b.volume, "vwap": float(b.vwap) if b.vwap is not None else None}
        for b in bars
    ]).set_index("bar_time").sort_index()


_OHLC_EMPTY_COLS = ["open", "high", "low", "close", "volume", "vwap"]


async def get_bars_range_for_symbols(
    session: AsyncSession,
    symbols: list[str],
    timeframe: str,
    start: datetime,
    end: datetime,
) -> dict[str, pd.DataFrame]:
    """Load OHLC for many tickers in one round-trip (JOIN instruments).

    Every symbol in ``symbols`` appears in the result: missing series map to an empty DataFrame
    with the standard columns.
    """
    if not symbols:
        return {}
    uniq = list(dict.fromkeys(symbols))
    template = pd.DataFrame(columns=_OHLC_EMPTY_COLS)
    out: dict[str, pd.DataFrame] = {s: template.copy() for s in uniq}
    buf: dict[str, list[dict]] = {s: [] for s in uniq}

    result = await session.execute(
        select(OhlcvBar, Instrument.symbol)
        .join(Instrument, OhlcvBar.instrument_id == Instrument.id)
        .where(
            Instrument.symbol.in_(uniq),
            OhlcvBar.timeframe == timeframe,
            OhlcvBar.bar_time >= start,
            OhlcvBar.bar_time <= end,
        )
        .order_by(Instrument.symbol, OhlcvBar.bar_time)
    )
    for bar, sym in result.all():
        buf[sym].append({
            "bar_time": bar.bar_time,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": bar.volume,
            "vwap": float(bar.vwap) if bar.vwap is not None else None,
        })
    for s in uniq:
        rows = buf[s]
        if rows:
            out[s] = pd.DataFrame(rows).set_index("bar_time").sort_index()
    return out


async def get_latest_bar_time(
    session: AsyncSession, instrument_id: int, timeframe: str
) -> datetime | None:
    result = await session.execute(
        select(OhlcvBar.bar_time)
        .where(OhlcvBar.instrument_id == instrument_id, OhlcvBar.timeframe == timeframe)
        .order_by(OhlcvBar.bar_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
