import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import Strategy
from src.data.providers.yfinance_provider import YFinanceProvider
from src.data import repository

logger = logging.getLogger(__name__)

# Default historical backfill depth per timeframe
BACKFILL_DAYS: dict[str, int] = {
    "1m": 7, "5m": 60, "15m": 60, "30m": 60,
    "1h": 730, "4h": 730, "1d": 730, "1wk": 1825, "1mo": 3650,
}


class DataCollector:
    def __init__(self):
        self._yfinance = YFinanceProvider()

    async def build_collection_plan(self) -> dict[str, set[str]]:
        """Scan active strategies and return {symbol: {timeframes}} merged plan."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active.is_(True))
            )
            strategies = result.scalars().all()
        plan: dict[str, set[str]] = {}
        for s in strategies:
            for sym in s.symbols:
                plan.setdefault(sym, set()).update(s.timeframes)
        return plan

    async def sync_symbol_timeframe(
        self, symbol: str, timeframe: str
    ) -> None:
        """Fetch missing bars for one symbol+timeframe and upsert into DB."""
        async with async_session_factory() as session:
            inst = await repository.upsert_instrument(session, symbol, "stock")
            latest = await repository.get_latest_bar_time(session, inst.id, timeframe)
            now = datetime.now(timezone.utc)
            if latest:
                start = latest + timedelta(minutes=1)
            else:
                days = BACKFILL_DAYS.get(timeframe, 730)
                start = now - timedelta(days=days)
            if start >= now:
                return
            days_back = (now - start).days + 1
            provider = self._yfinance
            try:
                df = await provider.get_bars(symbol, timeframe, start, now)
                if not df.empty:
                    await repository.save_bars(session, inst.id, timeframe, df)
                    await session.commit()
                    logger.info("Synced %s %s: %d bars", symbol, timeframe, len(df))
            except Exception as e:
                logger.error("Failed to sync %s %s: %s", symbol, timeframe, e)

    async def run_full_sync(self) -> None:
        """Sync all symbols+timeframes from the collection plan, with batching."""
        plan = await self.build_collection_plan()
        tasks = [
            self.sync_symbol_timeframe(sym, tf)
            for sym, timeframes in plan.items()
            for tf in timeframes
        ]
        batch_size = settings.data_batch_size
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            await asyncio.gather(*batch)
            if i + batch_size < len(tasks):
                await asyncio.sleep(settings.data_batch_delay)
