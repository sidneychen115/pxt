from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.app_timezone import api_iso
from src.core.database import get_session
from src.core.models import SystemEvent

router = APIRouter()


def _iso_sys_ts(dt: datetime) -> str:
    r = api_iso(dt)
    return r if r else ""


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/events")
async def list_events(
    level: str | None = None,
    event_type: str | None = None,
    summary: bool = Query(
        False,
        description=(
            "When true, omit strategy_run step rows (per-symbol logs); "
            "keep start/complete/fail and non-strategy events."
        ),
    ),
    limit: int = Query(100, le=500),
    session: AsyncSession = Depends(get_session),
):
    query = select(SystemEvent).order_by(desc(SystemEvent.created_at)).limit(limit)
    if level:
        query = query.where(SystemEvent.level == level)
    if event_type:
        query = query.where(SystemEvent.event_type == event_type)
    if summary:
        phase = SystemEvent.details["phase"].as_string()
        query = query.where(
            or_(
                SystemEvent.event_type != "strategy_run",
                phase.in_(["start", "complete", "fail"]),
            )
        )
    result = await session.execute(query)
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "level": e.level,
            "message": e.message,
            "details": e.details,
            "created_at": _iso_sys_ts(e.created_at),
        }
        for e in events
    ]
