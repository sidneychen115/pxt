"""Dedicated process: claim ``queued`` backtests and run them off the API workers."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from src.backtesting.queue import (
    claim_next_queued_backtest,
    count_running_backtests,
    refresh_queued_backtests,
)

log = logging.getLogger(__name__)


def _poll_interval_sec() -> float:
    raw = os.environ.get("BACKTEST_WORKER_POLL_SEC", "2")
    try:
        return max(0.5, float(raw))
    except ValueError:
        return 2.0


def _max_concurrent() -> int:
    raw = os.environ.get("BACKTEST_WORKER_MAX_CONCURRENT", "1")
    cap_raw = os.environ.get("BACKTEST_WORKER_MAX_CONCURRENT_CAP", "8")
    try:
        cap = max(1, int(cap_raw))
    except ValueError:
        cap = 8
    try:
        return max(1, min(cap, int(raw)))
    except ValueError:
        return 1


async def _run_one_backtest(backtest_id: int, req, sem: asyncio.Semaphore) -> None:
    from src.api.routers.backtests import _run_backtest

    async with sem:
        try:
            log.info("Running backtest id=%s strategy=%s", backtest_id, req.strategy_id)
            await _run_backtest(backtest_id, req)
        finally:
            running = await count_running_backtests()
            await refresh_queued_backtests(running_count=running)


async def run_backtest_worker_loop() -> None:
    max_jobs = _max_concurrent()
    sem = asyncio.Semaphore(max_jobs)
    active: set[asyncio.Task] = set()
    log.info(
        "Backtest worker started (poll=%.1fs, max_concurrent=%d)",
        _poll_interval_sec(),
        max_jobs,
    )

    while True:
        active = {t for t in active if not t.done()}
        running = await count_running_backtests()
        await refresh_queued_backtests(running_count=running)

        if len(active) >= max_jobs:
            await asyncio.sleep(_poll_interval_sec())
            continue

        claimed = await claim_next_queued_backtest()
        if claimed is None:
            await asyncio.sleep(_poll_interval_sec())
            continue

        backtest_id, req = claimed
        task = asyncio.create_task(_run_one_backtest(backtest_id, req, sem))
        active.add(task)
        task.add_done_callback(active.discard)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_backtest_worker_loop())
    except KeyboardInterrupt:
        log.info("Backtest worker stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
