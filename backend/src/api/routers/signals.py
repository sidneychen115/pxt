from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routers.signal_serialize import signal_detail_to_dict, signal_to_dict
from src.core.database import get_session
from src.core.models import Instrument, Option, TradeSignalRecord

router = APIRouter()


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


@router.get("/")
async def list_signals(
    strategy_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    query = _signals_select().order_by(desc(TradeSignalRecord.created_at))
    if strategy_id:
        query = query.where(TradeSignalRecord.strategy_id == strategy_id)
    if status:
        query = query.where(TradeSignalRecord.status == status)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    return [
        signal_to_dict(row[0], stock_symbol=row.stock_symbol, option_symbol=row.option_symbol)
        for row in result.all()
    ]


@router.get("/{signal_id}")
async def get_signal(signal_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        _signals_select().where(TradeSignalRecord.id == signal_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Signal not found.")
    return signal_detail_to_dict(
        row[0], stock_symbol=row.stock_symbol, option_symbol=row.option_symbol
    )
