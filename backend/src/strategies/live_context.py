from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.models import Instrument
from src.data import repository
from src.core.strategy_run_logger import StrategyRunLogger
from src.strategies.base import DataContext
from src.strategies.snapshot_bars import merge_snapshot_close_into_daily, quote_mark_price

_TZ = ZoneInfo(settings.timezone)


class LiveDataContext(DataContext):
    """Reads market data from the local PostgreSQL database.

    When ``snapshot_close`` is True, the 14:00 mark-price overlay is applied only in
    memory inside ``get_bars`` — it is never written to ``ohlcv_bars``.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        snapshot_close: bool = False,
        quote_prices: dict[str, float] | None = None,
        run_logger: StrategyRunLogger | None = None,
    ):
        self._session = session
        self._snapshot_close = snapshot_close
        self._quote_prices: dict[str, float] = quote_prices or {}
        self._run_logger = run_logger
        self._tz = _TZ

    @property
    def sql_session(self) -> AsyncSession:
        """Read-only Postgres session for fundamentals / HA cache queries."""
        return self._session

    async def log_step(self, message: str, *, level: str = "info", **details) -> None:
        if self._run_logger is not None:
            await self._run_logger.step(message, level=level, **details)

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
        df = await repository.get_bars(self._session, instrument_id, timeframe, limit)
        if not self._snapshot_close or timeframe != "1d" or df.empty:
            return df
        price = self._quote_prices.get(symbol)
        if price is None:
            quote = await self.get_latest_quote(symbol)
            price = quote_mark_price(quote)
        if price is None:
            return df
        return merge_snapshot_close_into_daily(
            df,
            mark_price=price,
            as_of=datetime.now(timezone.utc),
            tz=_TZ,
        )

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        from src.data.providers.schwab import SchwabProvider
        provider = SchwabProvider()
        return await provider.get_option_chain(underlying, expiry)

    async def get_latest_quote(self, symbol: str) -> dict:
        from src.data.providers.yfinance_provider import YFinanceProvider

        provider = YFinanceProvider()
        return await provider.get_latest_quote(symbol)
