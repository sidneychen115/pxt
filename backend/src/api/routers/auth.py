from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_session
from src.core.models import User

router = APIRouter()


@router.get("/users")
async def list_users(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).order_by(User.username))
    return [{"id": u.id, "username": u.username} for u in result.scalars().all()]


@router.get("/session")
async def get_session_user(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username}
