"""Run CPU-heavy async coroutines off the API event loop (worker thread + dedicated loop)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def run_coroutine_in_worker_thread(
    coro: Awaitable[T],
    *,
    main_loop: asyncio.AbstractEventLoop | None = None,
) -> T:
    """Execute ``coro`` in a worker thread with ``asyncio.run`` so the caller's loop stays responsive."""
    loop = main_loop or asyncio.get_running_loop()

    def _thread_main() -> T:
        return asyncio.run(coro)

    return await loop.run_in_executor(None, _thread_main)


def threadsafe_progress_callback(
    main_loop: asyncio.AbstractEventLoop,
    callback: Callable[[int, int], Awaitable[None]],
) -> Callable[[int, int], Awaitable[None]]:
    """Wrap an async progress handler so it can be awaited from a worker-thread event loop."""

    async def on_progress(done: int, total: int) -> None:
        fut = asyncio.run_coroutine_threadsafe(callback(done, total), main_loop)
        await asyncio.wrap_future(fut)

    return on_progress
