from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.routers.strategy_serialize import strategy_to_dict
from src.api.routers.user_strategy_serialize import user_strategy_to_dict
from src.core.database import get_session
from src.core.models import Strategy, User, UserStrategy
from src.scheduler.run_schedule import is_cron_frequency, is_interval_frequency
from src.scheduler.timeframe_interval import KNOWN_TIMEFRAMES, min_interval_minutes
from src.strategies.registry import REGISTRY, discover_strategies

router = APIRouter()


class UserStrategyCreate(BaseModel):
    strategy_id: str


class UserStrategyUpdate(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    run_frequency: str | None = None
    parameters: dict | None = None
    is_active: bool | None = None
    max_symbols: int | None = None


def _validate_updates(updates: dict, current: UserStrategy) -> dict:
    if "run_frequency" in updates and updates["run_frequency"] is not None:
        rf = updates["run_frequency"].strip()
        if not (is_interval_frequency(rf) or is_cron_frequency(rf)):
            raise HTTPException(
                400,
                "run_frequency must be an interval like '1440m' or a 5-field cron.",
            )
        updates["run_frequency"] = rf
    if "timeframes" in updates and updates["timeframes"] is not None:
        tfs = updates["timeframes"]
        if not tfs:
            raise HTTPException(400, "timeframes must include at least one period.")
        unknown = [tf for tf in tfs if tf not in KNOWN_TIMEFRAMES]
        if unknown:
            raise HTTPException(400, f"Unknown timeframe(s): {', '.join(unknown)}")
        if "run_frequency" not in updates and not is_cron_frequency(current.run_frequency or ""):
            updates["run_frequency"] = f"{min_interval_minutes(list(tfs))}m"
    if "symbols" in updates:
        max_sym = updates.get("max_symbols", current.max_symbols)
        if len(updates["symbols"]) > max_sym:
            raise HTTPException(400, f"Exceeds max_symbols limit of {max_sym}.")
    return updates


async def _get_pool(session: AsyncSession, strategy_id: str) -> Strategy:
    result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
    pool = result.scalar_one_or_none()
    if not pool:
        raise HTTPException(404, f"Strategy '{strategy_id}' not in pool.")
    return pool


@router.get("/pool")
async def list_pool(session: AsyncSession = Depends(get_session)):
    discover_strategies()
    result = await session.execute(select(Strategy).order_by(Strategy.name))
    return [strategy_to_dict(s) for s in result.scalars().all()]


@router.get("/")
async def list_my_strategies(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(UserStrategy, Strategy)
        .join(Strategy, UserStrategy.strategy_id == Strategy.id)
        .where(UserStrategy.user_id == user.id)
        .order_by(Strategy.name)
    )
    return [user_strategy_to_dict(us, pool) for us, pool in result.all()]


@router.post("/")
async def add_strategy(
    body: UserStrategyCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    discover_strategies()
    if body.strategy_id not in REGISTRY:
        raise HTTPException(400, f"Strategy '{body.strategy_id}' is not registered in code.")
    pool = await _get_pool(session, body.strategy_id)
    existing = await session.execute(
        select(UserStrategy).where(
            UserStrategy.user_id == user.id,
            UserStrategy.strategy_id == body.strategy_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Strategy already in your list.")
    cls = REGISTRY[body.strategy_id]
    us = UserStrategy(
        user_id=user.id,
        strategy_id=body.strategy_id,
        symbols=list(pool.symbols or cls.default_symbols),
        timeframes=list(pool.timeframes or cls.default_timeframes),
        run_frequency=pool.run_frequency or cls.default_frequency,
        parameters=dict(pool.parameters or cls.default_parameters),
        is_active=False,
        max_symbols=pool.max_symbols,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(us)
    await session.commit()
    await session.refresh(us)
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler and us.is_active:
        await scheduler.reload_user_strategy(user.id, body.strategy_id)
    return user_strategy_to_dict(us, pool)


@router.put("/{row_id}")
async def update_my_strategy(
    row_id: int,
    body: UserStrategyUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No fields to update.")
    result = await session.execute(
        select(UserStrategy, Strategy)
        .join(Strategy, UserStrategy.strategy_id == Strategy.id)
        .where(UserStrategy.id == row_id, UserStrategy.user_id == user.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "User strategy not found.")
    us, pool = row
    updates = _validate_updates(updates, us)
    updates["updated_at"] = datetime.now(timezone.utc)
    for k, v in updates.items():
        setattr(us, k, v)
    await session.commit()
    await session.refresh(us)
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        await scheduler.reload_user_strategy(user.id, us.strategy_id)
    return user_strategy_to_dict(us, pool)


@router.delete("/{row_id}")
async def remove_my_strategy(
    row_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(UserStrategy).where(
            UserStrategy.id == row_id, UserStrategy.user_id == user.id
        )
    )
    us = result.scalar_one_or_none()
    if not us:
        raise HTTPException(404, "User strategy not found.")
    if us.is_active:
        raise HTTPException(
            400,
            "Cannot remove an active strategy. Set is_active to false first.",
        )
    strategy_id = us.strategy_id
    await session.execute(delete(UserStrategy).where(UserStrategy.id == row_id))
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        await scheduler.reload_user_strategy(user.id, strategy_id)
    return {"ok": True}
