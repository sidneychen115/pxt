"""Tests for GET /api/backtests/{id}/ohlc."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pandas as pd
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.core.database import get_session
from src.core.models import Backtest, BacktestTrade, Strategy


@pytest.fixture
async def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed_strategy_and_backtest(session, *, status: str = "completed") -> Backtest:
    st = Strategy(
        id="test_strat_ohlc_api",
        name="Ohlc Test Strat",
        description=None,
        is_active=True,
        symbols=["SPY"],
        timeframes=["1d"],
        run_frequency="daily",
        parameters={},
        max_symbols=50,
    )
    session.add(st)
    bt = Backtest(
        strategy_id=st.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 10),
        symbols=["SPY", "QQQ"],
        initial_capital=Decimal("100000.00"),
        parameters={"timeframe": "1d"},
        status=status,
    )
    session.add(bt)
    await session.flush()
    await session.refresh(bt)
    return bt


async def test_backtest_ohlc_404(client: AsyncClient):
    r = await client.get("/api/backtests/999999001/ohlc?symbol=SPY")
    assert r.status_code == 404


async def test_backtest_ohlc_bad_symbol(client: AsyncClient, session):
    bt = await _seed_strategy_and_backtest(session)
    r = await client.get(f"/api/backtests/{bt.id}/ohlc?symbol=INVALID")
    assert r.status_code == 400
    assert "not part" in r.json()["detail"].lower()


async def test_backtest_ohlc_not_completed(client: AsyncClient, session):
    bt = await _seed_strategy_and_backtest(session, status="running")
    r = await client.get(f"/api/backtests/{bt.id}/ohlc?symbol=SPY")
    assert r.status_code == 409


async def test_backtest_ohlc_completed_returns_bars(client: AsyncClient, session):
    bt = await _seed_strategy_and_backtest(session, status="completed")
    idx = pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [float(i) for i in range(8)],
            "high": [float(i) + 0.5 for i in range(8)],
            "low": [float(i) - 0.1 for i in range(8)],
            "close": [float(i) + 0.1 for i in range(8)],
        },
        index=idx,
    )
    session.add(
        BacktestTrade(
            backtest_id=bt.id,
            symbol="SPY",
            direction="buy",
            quantity=Decimal("1"),
            entry_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            entry_price=Decimal("10"),
            exit_time=datetime(2024, 1, 5, tzinfo=timezone.utc),
            exit_price=Decimal("11"),
            pnl=Decimal("1"),
            pnl_pct=Decimal("0.1"),
            hold_days=Decimal("3"),
            exit_reason="signal",
        )
    )
    await session.flush()

    with patch("src.api.routers.backtests._fetch_with_cache", new_callable=AsyncMock) as m:
        m.return_value = df
        r = await client.get(f"/api/backtests/{bt.id}/ohlc?symbol=SPY&max_points=4000")

    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "SPY"
    assert body["timeframe"] == "1d"
    assert len(body["bars"]) == 8
    assert body["bars"][0]["time"] == "2024-01-01"
    assert body["bars"][0]["open"] == 0.0
    m.assert_awaited_once()


async def test_backtest_ohlc_subsample_keeps_trade_bars(client: AsyncClient, session):
    bt = await _seed_strategy_and_backtest(session, status="completed")
    n = 500
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.0] * n,
            "high": [1.5] * n,
            "low": [0.9] * n,
            "close": [1.1] * n,
        },
        index=idx,
    )
    entry_ts = idx[10].to_pydatetime()
    exit_ts = idx[400].to_pydatetime()
    session.add(
        BacktestTrade(
            backtest_id=bt.id,
            symbol="SPY",
            direction="buy",
            quantity=Decimal("1"),
            entry_time=entry_ts,
            entry_price=Decimal("1"),
            exit_time=exit_ts,
            exit_price=Decimal("2"),
            pnl=Decimal("1"),
            pnl_pct=Decimal("1"),
            hold_days=Decimal("1"),
            exit_reason="signal",
        )
    )
    await session.flush()

    with patch("src.api.routers.backtests._fetch_with_cache", new_callable=AsyncMock) as m:
        m.return_value = df
        r = await client.get(f"/api/backtests/{bt.id}/ohlc?symbol=SPY&max_points=200")

    assert r.status_code == 200
    times = {b["time"] for b in r.json()["bars"]}
    assert "2024-01-11" in times  # idx[10]
    assert "2025-02-04" in times  # idx[400]
