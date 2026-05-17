import asyncio
import time

import pytest

from src.backtesting.thread_runner import run_coroutine_in_worker_thread, threadsafe_progress_callback


@pytest.mark.asyncio
async def test_worker_thread_keeps_main_loop_responsive():
    async def heavy() -> str:
        time.sleep(0.25)
        return "ok"

    ticked = False

    async def ticker() -> None:
        nonlocal ticked
        await asyncio.sleep(0.05)
        ticked = True

    task = asyncio.create_task(run_coroutine_in_worker_thread(heavy()))
    await ticker()
    assert ticked, "main event loop was blocked during backtest-style work"
    assert await task == "ok"


@pytest.mark.asyncio
async def test_threadsafe_progress_runs_on_main_loop():
    main_loop = asyncio.get_running_loop()
    seen: list[tuple[int, int]] = []

    async def record(done: int, total: int) -> None:
        seen.append((done, total))

    wrapped = threadsafe_progress_callback(main_loop, record)

    async def worker() -> None:
        await wrapped(1, 10)
        await wrapped(10, 10)

    await run_coroutine_in_worker_thread(worker())
    assert seen == [(1, 10), (10, 10)]
