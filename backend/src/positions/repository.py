from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Instrument, OhlcvBar, PositionFill, UserPosition
from src.positions.service import apply_fill


async def load_positions_by_symbol(
    session: AsyncSession, user_id: int
) -> dict[str, Decimal]:
    result = await session.execute(
        select(Instrument.symbol, UserPosition.quantity)
        .join(Instrument, UserPosition.instrument_id == Instrument.id)
        .where(UserPosition.user_id == user_id, UserPosition.quantity > 0)
    )
    return {row.symbol: Decimal(row.quantity) for row in result.all()}


async def latest_close_prices(
    session: AsyncSession, instrument_ids: list[int]
) -> dict[int, Decimal]:
    if not instrument_ids:
        return {}
    out: dict[int, Decimal] = {}
    for iid in instrument_ids:
        result = await session.execute(
            select(OhlcvBar.close)
            .where(OhlcvBar.instrument_id == iid, OhlcvBar.timeframe == "1d")
            .order_by(OhlcvBar.bar_time.desc())
            .limit(1)
        )
        close = result.scalar_one_or_none()
        if close is not None:
            out[iid] = Decimal(close)
    return out


async def record_position_fill(
    session: AsyncSession,
    *,
    user_id: int,
    instrument_id: int,
    side: str,
    quantity: Decimal,
    fill_price: Decimal,
    signal_id: int | None = None,
) -> tuple[Decimal, Decimal]:
    """Apply fill, persist UserPosition and PositionFill. Does not commit."""
    pos_result = await session.execute(
        select(UserPosition).where(
            UserPosition.user_id == user_id,
            UserPosition.instrument_id == instrument_id,
        )
    )
    pos = pos_result.scalar_one_or_none()
    current = (pos.quantity, pos.avg_cost) if pos and pos.quantity > 0 else None
    new_qty, new_avg = apply_fill(current, side, quantity, fill_price)
    now = datetime.now(timezone.utc)
    session.add(
        PositionFill(
            user_id=user_id,
            instrument_id=instrument_id,
            signal_id=signal_id,
            side=side,
            quantity=quantity,
            fill_price=fill_price,
            filled_at=now,
        )
    )
    if pos is None:
        session.add(
            UserPosition(
                user_id=user_id,
                instrument_id=instrument_id,
                quantity=new_qty,
                avg_cost=new_avg,
                updated_at=now,
            )
        )
    else:
        pos.quantity = new_qty
        pos.avg_cost = new_avg
        pos.updated_at = now
    return new_qty, new_avg
