"""CRUD for saved backtest configuration presets (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_session
from src.core.models import BacktestConfigPreset, User

router = APIRouter()

MAX_PRESETS = 50


class BacktestPresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    strategy_id: str | None = None
    start_date: date
    end_date: date
    symbols: str
    initial_capital: float
    parameters: dict = Field(default_factory=dict)
    exit_policy_form: dict = Field(default_factory=dict)


class BacktestPresetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    strategy_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    symbols: str | None = None
    initial_capital: float | None = None
    parameters: dict | None = None
    exit_policy_form: dict | None = None


class BacktestPresetOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    strategy_id: str | None
    start_date: date
    end_date: date
    symbols: str
    initial_capital: float
    parameters: dict
    exit_policy_form: dict

    model_config = {"from_attributes": True}


def _row_to_out(row: BacktestConfigPreset) -> BacktestPresetOut:
    return BacktestPresetOut(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        strategy_id=row.strategy_id,
        start_date=row.start_date,
        end_date=row.end_date,
        symbols=row.symbols,
        initial_capital=float(row.initial_capital),
        parameters=row.parameters or {},
        exit_policy_form=row.exit_policy_form or {},
    )


@router.get("/", response_model=list[BacktestPresetOut])
async def list_presets(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(BacktestConfigPreset)
        .where(BacktestConfigPreset.user_id == user.id)
        .order_by(BacktestConfigPreset.created_at.desc())
    )
    rows = result.scalars().all()
    return [_row_to_out(r) for r in rows]


@router.post("/", response_model=BacktestPresetOut)
async def create_preset(
    body: BacktestPresetCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cnt = await session.scalar(
        select(func.count())
        .select_from(BacktestConfigPreset)
        .where(BacktestConfigPreset.user_id == user.id)
    )
    if cnt is not None and cnt >= MAX_PRESETS:
        raise HTTPException(400, f"最多保存 {MAX_PRESETS} 条预设，请先删除旧配置")

    sid = (body.strategy_id or "").strip() or None
    row = BacktestConfigPreset(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=body.name.strip()[:80],
        strategy_id=sid,
        start_date=body.start_date,
        end_date=body.end_date,
        symbols=body.symbols,
        initial_capital=Decimal(str(body.initial_capital)),
        parameters=body.parameters or {},
        exit_policy_form=body.exit_policy_form or {},
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(400, "无效的策略 ID") from e
    await session.refresh(row)
    return _row_to_out(row)


@router.patch("/{preset_id}", response_model=BacktestPresetOut)
async def update_preset(
    preset_id: str,
    body: BacktestPresetUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(BacktestConfigPreset).where(
            BacktestConfigPreset.id == preset_id,
            BacktestConfigPreset.user_id == user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "预设不存在")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()[:80]
    if "strategy_id" in data:
        v = data["strategy_id"]
        if v is None:
            row.strategy_id = None
        else:
            row.strategy_id = str(v).strip() or None
    if "start_date" in data and data["start_date"] is not None:
        row.start_date = data["start_date"]
    if "end_date" in data and data["end_date"] is not None:
        row.end_date = data["end_date"]
    if "symbols" in data and data["symbols"] is not None:
        row.symbols = data["symbols"]
    if "initial_capital" in data and data["initial_capital"] is not None:
        row.initial_capital = Decimal(str(data["initial_capital"]))
    if "parameters" in data and data["parameters"] is not None:
        row.parameters = data["parameters"]
    if "exit_policy_form" in data and data["exit_policy_form"] is not None:
        row.exit_policy_form = data["exit_policy_form"]

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(400, "无效的策略 ID") from e
    await session.refresh(row)
    return _row_to_out(row)


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        delete(BacktestConfigPreset).where(
            BacktestConfigPreset.id == preset_id,
            BacktestConfigPreset.user_id == user.id,
        )
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "预设不存在")
    return {"ok": True}
