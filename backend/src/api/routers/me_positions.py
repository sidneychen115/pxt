from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_session
from src.core.models import Instrument, User, UserPosition
from src.data.repository import upsert_instrument
from src.positions.repository import latest_close_prices, record_position_fill
from src.positions.service import position_summary_from_rows

router = APIRouter()


class ManualFillBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)
    fill_price: float = Field(..., gt=0)
    side: str = Field(default="buy", pattern="^(buy|sell)$")


async def _position_rows(session: AsyncSession, user_id: int):
    result = await session.execute(
        select(UserPosition, Instrument)
        .join(Instrument, UserPosition.instrument_id == Instrument.id)
        .where(UserPosition.user_id == user_id, UserPosition.quantity > 0)
    )
    rows = result.all()
    marks = await latest_close_prices(session, [up.instrument_id for up, _ in rows])
    summary_rows: list[tuple[Decimal, Decimal, Decimal | None]] = []
    items = []
    for up, inst in rows:
        mark = marks.get(up.instrument_id)
        summary_rows.append((up.quantity, up.avg_cost, mark))
        px = mark if mark is not None else up.avg_cost
        items.append({
            "symbol": inst.symbol,
            "quantity": float(up.quantity),
            "avg_cost": float(up.avg_cost),
            "mark_price": float(mark) if mark is not None else None,
            "market_value": float(up.quantity * px),
            "updated_at": up.updated_at.isoformat() if up.updated_at else None,
        })
    return items, summary_rows


@router.get("/summary")
async def positions_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _, summary_rows = await _position_rows(session, user.id)
    return position_summary_from_rows(summary_rows)


@router.get("/")
async def list_positions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    items, _ = await _position_rows(session, user.id)
    return items


@router.post("/fills")
async def create_manual_fill(
    body: ManualFillBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "Symbol is required.")
    inst = await upsert_instrument(session, symbol, "stock")
    qty = Decimal(str(body.quantity))
    price = Decimal(str(body.fill_price))
    try:
        new_qty, new_avg = await record_position_fill(
            session,
            user_id=user.id,
            instrument_id=inst.id,
            side=body.side,
            quantity=qty,
            fill_price=price,
            signal_id=None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await session.commit()
    return {
        "ok": True,
        "symbol": symbol,
        "quantity": float(new_qty),
        "avg_cost": float(new_avg),
    }
