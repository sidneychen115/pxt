"""Global strategy pool catalog (read-only). Per-user config: /api/me/strategies."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routers.strategy_serialize import strategy_to_dict
from src.core.database import get_session
from src.core.models import Strategy

router = APIRouter()


@router.get("/")
async def list_strategies(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).order_by(Strategy.name))
    return [strategy_to_dict(s) for s in result.scalars().all()]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found.")
    return strategy_to_dict(s)
