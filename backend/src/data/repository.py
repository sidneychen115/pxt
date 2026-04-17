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
