import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.backtest_stale_reaper import run_backtest_stale_reaper
from src.core.leader_lock import api_background_leader
from src.api.routers import (
    auth,
    strategies,
    signals,
    backtests,
    backtest_presets,
    system,
    me_strategies,
    me_positions,
)
from src.api.websocket import ws_manager
from src.scheduler.runner import StrategyScheduler

_scheduler: StrategyScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    stale_task: asyncio.Task | None = None
    async with api_background_leader() as is_leader:
        if is_leader:
            _scheduler = StrategyScheduler()
            await _scheduler.start()
            app.state.scheduler = _scheduler
            stale_task = asyncio.create_task(run_backtest_stale_reaper())
        else:
            app.state.scheduler = None
        try:
            yield
        finally:
            if stale_task is not None:
                stale_task.cancel()
                with suppress(asyncio.CancelledError):
                    await stale_task
            if is_leader and _scheduler is not None:
                await _scheduler.stop()


app = FastAPI(title="PXT Trading System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(me_strategies.router, prefix="/api/me/strategies", tags=["me-strategies"])
app.include_router(me_positions.router, prefix="/api/me/positions", tags=["me-positions"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
app.include_router(backtest_presets.router, prefix="/api/backtest-presets", tags=["backtest-presets"])
app.include_router(system.router, prefix="/api/system", tags=["system"])


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
