from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.core.models import User


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    x_user_id: int | None = Header(None, alias="X-User-Id"),
) -> User:
    if x_user_id is None:
        raise HTTPException(401, "Missing X-User-Id header.")
    result = await session.execute(select(User).where(User.id == x_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Invalid user.")
    return user
