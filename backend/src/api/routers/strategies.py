from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import Strategy
from src.api.routers.strategy_serialize import strategy_to_dict
from src.scheduler.run_schedule import is_cron_frequency, is_interval_frequency
from src.scheduler.timeframe_interval import KNOWN_TIMEFRAMES, min_interval_minutes

router = APIRouter()


class StrategyUpdate(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    run_frequency: str | None = None
    parameters: dict | None = None
    is_active: bool | None = None
    max_symbols: int | None = None


@router.get("/")
async def list_strategies(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).order_by(Strategy.name))
    strategies = result.scalars().all()
    return [strategy_to_dict(s) for s in strategies]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found.")
    return strategy_to_dict(s)


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No fields to update.")
    if "run_frequency" in updates and updates["run_frequency"] is not None:
        rf = updates["run_frequency"].strip()
        if not (is_interval_frequency(rf) or is_cron_frequency(rf)):
            raise HTTPException(
                400,
                "run_frequency must be an interval like '1440m' or a 5-field cron "
                "(e.g. '0 14 * * mon-fri').",
            )
        updates["run_frequency"] = rf
    existing = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    current = existing.scalar_one_or_none()
    if not current:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found.")
    if "timeframes" in updates and updates["timeframes"] is not None:
        tfs = updates["timeframes"]
        if not tfs:
            raise HTTPException(400, "timeframes must include at least one period.")
        unknown = [tf for tf in tfs if tf not in KNOWN_TIMEFRAMES]
        if unknown:
            raise HTTPException(400, f"Unknown timeframe(s): {', '.join(unknown)}")
        # Interval mode only: sync run_frequency to shortest timeframe. Cron schedules are preserved.
        if "run_frequency" not in updates and not is_cron_frequency(current.run_frequency or ""):
            m = min_interval_minutes(list(tfs))
            updates["run_frequency"] = f"{m}m"
    if "symbols" in updates:
        max_sym = (
            updates["max_symbols"]
            if "max_symbols" in updates
            else current.max_symbols
        )
        if len(updates["symbols"]) > max_sym:
            raise HTTPException(
                400,
                f"Exceeds max_symbols limit of {max_sym} "
                f"({len(updates['symbols'])} provided).",
            )
    result = await session.execute(
        update(Strategy)
        .where(Strategy.id == strategy_id)
        .values(**updates)
        .returning(Strategy.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, f"Strategy '{strategy_id}' not found.")  # pragma: no cover
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        await scheduler.reload_strategy(strategy_id)
    return {"ok": True}
