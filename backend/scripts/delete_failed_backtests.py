"""One-off maintenance: remove rows where backtests.status = 'failed' and dependent rows."""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from src.core.database import async_session_factory
from src.core.models import Backtest, BacktestEquityCurve, BacktestTrade


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(Backtest.id).where(Backtest.status == "failed"))
        ids = list(result.scalars().all())
        if not ids:
            print("No failed backtests to delete.")
            return
        await session.execute(delete(BacktestTrade).where(BacktestTrade.backtest_id.in_(ids)))
        await session.execute(delete(BacktestEquityCurve).where(BacktestEquityCurve.backtest_id.in_(ids)))
        await session.execute(delete(Backtest).where(Backtest.id.in_(ids)))
        await session.commit()
        print(f"Deleted {len(ids)} failed backtest(s), ids: {ids}")


if __name__ == "__main__":
    asyncio.run(main())
