from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.routers.signal_serialize import iso_utc, signal_detail_to_dict, signal_to_dict
from src.core.database import get_session
from src.core.models import (
    Instrument,
    Option,
    TradeSignalRecord,
    User,
)
from src.positions.repository import record_position_fill

router = APIRouter()


class SignalExecuteBody(BaseModel):
    quantity: float = Field(..., gt=0)
    fill_price: float = Field(..., gt=0)


def _parse_signal_time(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as e:
        raise HTTPException(400, "Invalid signal_time.") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _signals_select():
    return (
        select(
            TradeSignalRecord,
            Instrument.symbol.label("stock_symbol"),
            Option.symbol.label("option_symbol"),
        )
        .outerjoin(Instrument, TradeSignalRecord.stock_id == Instrument.id)
        .outerjoin(Option, TradeSignalRecord.option_id == Option.id)
    )


@router.get("/runs")
async def list_signal_runs(
    strategy_id: str | None = None,
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(
            TradeSignalRecord.strategy_id,
            TradeSignalRecord.signal_time,
            func.count().label("signal_count"),
        )
        .where(TradeSignalRecord.user_id == user.id)
        .group_by(TradeSignalRecord.strategy_id, TradeSignalRecord.signal_time)
        .order_by(desc(TradeSignalRecord.signal_time))
        .limit(limit)
    )
    if strategy_id:
        query = query.where(TradeSignalRecord.strategy_id == strategy_id)
    result = await session.execute(query)
    return [
        {
            "strategy_id": row.strategy_id,
            "signal_time": iso_utc(row.signal_time),
            "signal_count": row.signal_count,
        }
        for row in result.all()
    ]


@router.get("/")
async def list_signals(
    strategy_id: str | None = None,
    status: str | None = None,
    signal_time: str | None = Query(
        None,
        description="Exact batch timestamp from GET /signals/runs (ISO-8601 UTC).",
    ),
    limit: int = Query(50, le=500),
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = (
        _signals_select()
        .where(TradeSignalRecord.user_id == user.id)
        .order_by(desc(TradeSignalRecord.signal_time), TradeSignalRecord.id)
    )
    if strategy_id:
        query = query.where(TradeSignalRecord.strategy_id == strategy_id)
    if status:
        query = query.where(TradeSignalRecord.status == status)
    if signal_time:
        query = query.where(
            TradeSignalRecord.signal_time == _parse_signal_time(signal_time)
        )
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    return [
        signal_to_dict(row[0], stock_symbol=row.stock_symbol, option_symbol=row.option_symbol)
        for row in result.all()
    ]


@router.get("/{signal_id}")
async def get_signal(
    signal_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        _signals_select().where(
            TradeSignalRecord.id == signal_id,
            TradeSignalRecord.user_id == user.id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Signal not found.")
    return signal_detail_to_dict(
        row[0], stock_symbol=row.stock_symbol, option_symbol=row.option_symbol
    )


@router.post("/{signal_id}/execute")
async def execute_signal(
    signal_id: int,
    body: SignalExecuteBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(TradeSignalRecord).where(
            TradeSignalRecord.id == signal_id,
            TradeSignalRecord.user_id == user.id,
        )
    )
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(404, "Signal not found.")
    if signal.status == "executed":
        raise HTTPException(409, "Signal already executed.")
    if signal.status not in ("pending", "notified"):
        raise HTTPException(400, f"Cannot execute signal in status '{signal.status}'.")
    if signal.stock_id is None:
        raise HTTPException(400, "Only stock signals can be executed in Phase 1.")
    if signal.direction not in ("buy", "sell"):
        raise HTTPException(400, "Only buy/sell signals can be executed.")

    qty = Decimal(str(body.quantity))
    price = Decimal(str(body.fill_price))
    side = signal.direction

    try:
        new_qty, new_avg = await record_position_fill(
            session,
            user_id=user.id,
            instrument_id=signal.stock_id,
            side=side,
            quantity=qty,
            fill_price=price,
            signal_id=signal.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    await session.execute(
        update(TradeSignalRecord)
        .where(TradeSignalRecord.id == signal_id)
        .values(status="executed")
    )
    await session.commit()
    return {"ok": True, "quantity": float(new_qty), "avg_cost": float(new_avg)}
