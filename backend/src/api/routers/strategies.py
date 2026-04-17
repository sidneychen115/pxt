from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import Strategy

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
    return [
        {
            "id": s.id, "name": s.name, "description": s.description,
            "is_active": s.is_active, "symbols": s.symbols,
            "timeframes": s.timeframes, "run_frequency": s.run_frequency,
            "parameters": s.parameters, "max_symbols": s.max_symbols,
        }
        for s in strategies
    ]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found.")
    return {"id": s.id, "name": s.name, "description": s.description,
            "is_active": s.is_active, "symbols": s.symbols,
            "timeframes": s.timeframes, "run_frequency": s.run_frequency,
            "parameters": s.parameters, "max_symbols": s.max_symbols}


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdate,
    session: AsyncSession = Depends(get_session),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update.")
    if "symbols" in updates and len(updates["symbols"]) > 50:
        raise HTTPException(400, "Exceeds max_symbols limit.")
    await session.execute(
        update(Strategy).where(Strategy.id == strategy_id).values(**updates)
    )
    await session.commit()
    from src.api.main import _scheduler
    if _scheduler:
        await _scheduler.reload_strategy(strategy_id)
    return {"ok": True}
