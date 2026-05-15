"""Parallel latest-quote fetch for many symbols (live HA runs)."""

from __future__ import annotations

import asyncio
import logging

from src.strategies.snapshot_bars import quote_mark_price

logger = logging.getLogger(__name__)


async def prefetch_mark_prices(
    symbols: list[str],
    *,
    concurrency: int = 25,
) -> dict[str, float]:
    """Return symbol -> mark price for symbols with a usable quote."""
    from src.data.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, float] = {}

    async def one(sym: str) -> None:
        if not sym:
            return
        async with sem:
            try:
                quote = await provider.get_latest_quote(sym)
                price = quote_mark_price(quote)
                if price is not None:
                    out[sym] = price
            except Exception as e:
                logger.warning("quote prefetch failed for %s: %s", sym, e)

    await asyncio.gather(*(one(s) for s in symbols))
    return out
