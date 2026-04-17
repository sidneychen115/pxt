from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session
from src.core.models import SystemEvent

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/events")
async def list_events(
    level: str | None = None,
    event_type: str | None = None,
    limit: int = Query(100, le=500),
    session: AsyncSession = Depends(get_session),
):
    query = select(SystemEvent).order_by(desc(SystemEvent.created_at)).limit(limit)
    if level:
        query = query.where(SystemEvent.level == level)
    if event_type:
        query = query.where(SystemEvent.event_type == event_type)
    result = await session.execute(query)
    events = result.scalars().all()
    return [
        {"id": e.id, "event_type": e.event_type, "level": e.level,
         "message": e.message, "details": e.details, "created_at": e.created_at}
        for e in events
    ]
