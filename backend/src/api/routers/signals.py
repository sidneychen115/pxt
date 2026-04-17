from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import TradeSignalRecord

router = APIRouter()


@router.get("/")
async def list_signals(
    strategy_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    query = select(TradeSignalRecord).order_by(desc(TradeSignalRecord.created_at))
    if strategy_id:
        query = query.where(TradeSignalRecord.strategy_id == strategy_id)
    if status:
        query = query.where(TradeSignalRecord.status == status)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    signals = result.scalars().all()
    return [
        {
            "id": s.id, "strategy_id": s.strategy_id,
            "stock_id": s.stock_id, "option_id": s.option_id,
            "signal_time": s.signal_time, "direction": s.direction,
            "quantity": float(s.quantity) if s.quantity else None,
            "order_type": s.order_type,
            "limit_price": float(s.limit_price) if s.limit_price else None,
            "confidence": float(s.confidence) if s.confidence else None,
            "reasoning": s.reasoning, "status": s.status,
            "created_at": s.created_at,
        }
        for s in signals
    ]


@router.get("/{signal_id}")
async def get_signal(signal_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(TradeSignalRecord).where(TradeSignalRecord.id == signal_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Signal not found.")
    return {
        "id": s.id, "strategy_id": s.strategy_id,
        "stock_id": s.stock_id, "option_id": s.option_id,
        "signal_time": s.signal_time, "direction": s.direction,
        "quantity": float(s.quantity) if s.quantity else None,
        "order_type": s.order_type,
        "limit_price": float(s.limit_price) if s.limit_price else None,
        "stop_price": float(s.stop_price) if s.stop_price else None,
        "confidence": float(s.confidence) if s.confidence else None,
        "reasoning": s.reasoning, "status": s.status,
        "metadata": s.metadata_, "created_at": s.created_at,
    }
