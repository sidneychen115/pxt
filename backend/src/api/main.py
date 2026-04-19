from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from src.api.websocket import ws_manager
from src.api.routers import strategies, signals, backtests, backtest_presets, system
from src.scheduler.runner import StrategyScheduler

_scheduler: StrategyScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    _scheduler = StrategyScheduler()
    await _scheduler.start()
    app.state.scheduler = _scheduler
    yield
    await _scheduler.stop()


app = FastAPI(title="PXT Trading System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
