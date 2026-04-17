from datetime import date
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models import Instrument
from src.data import repository
from src.strategies.base import DataContext


class LiveDataContext(DataContext):
    """Reads market data from the local PostgreSQL database."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_instrument_id(self, symbol: str) -> int | None:
        result = await self._session.execute(
            select(Instrument.id).where(Instrument.symbol == symbol)
        )
        return result.scalar_one_or_none()

    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        instrument_id = await self._get_instrument_id(symbol)
        if instrument_id is None:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return await repository.get_bars(self._session, instrument_id, timeframe, limit)

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        from src.data.providers.schwab import SchwabProvider
        provider = SchwabProvider()
        return await provider.get_option_chain(underlying, expiry)

    async def get_latest_quote(self, symbol: str) -> dict:
        from src.data.providers.schwab import SchwabProvider
        provider = SchwabProvider()
        return await provider.get_latest_quote(symbol)
