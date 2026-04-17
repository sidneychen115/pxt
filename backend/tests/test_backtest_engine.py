import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.backtesting.engine import BacktestEngine
from src.strategies.library.ma_crossover import MovingAverageCrossover


def make_trending_data(symbol="SPY", n=60, trend="up"):
    rng = np.random.default_rng(0)
    if trend == "up":
        prices = np.linspace(100, 150, n) + rng.normal(0, 1, n)
    else:
        prices = np.linspace(150, 100, n) + rng.normal(0, 1, n)
    idx = pd.date_range("2023-01-02", periods=n, freq="B", tz="UTC")
    df = pd.DataFrame({
        "open": prices * 0.99, "high": prices * 1.01,
        "low": prices * 0.98, "close": prices,
        "volume": [10000] * n,
    }, index=idx)
    return {symbol: {"1d": df}}


async def test_backtest_runs_without_error():
    engine = BacktestEngine(initial_capital=10_000)
    strategy = MovingAverageCrossover()
    data = make_trending_data("SPY", 60, "up")
    metrics = await engine.run(strategy, ["SPY"], {"fast": 5, "slow": 20}, data, "1d")
    assert metrics.initial_capital == 10_000
    assert metrics.final_equity > 0
    assert isinstance(metrics.equity_curve, pd.Series)


async def test_backtest_metrics_range():
    engine = BacktestEngine(initial_capital=10_000)
    strategy = MovingAverageCrossover()
    data = make_trending_data("SPY", 60)
    metrics = await engine.run(strategy, ["SPY"], {"fast": 5, "slow": 20}, data, "1d")
    assert -1.0 <= metrics.total_return <= 10.0
    assert 0.0 <= metrics.win_rate <= 1.0
    assert metrics.max_drawdown <= 0.0


async def test_look_ahead_prevention():
    """BacktestDataContext must not return future bars."""
    from src.backtesting.data_context import BacktestDataContext
    idx = pd.date_range("2023-01-02", periods=10, freq="B", tz="UTC")
    df = pd.DataFrame({"open": range(10), "high": range(10), "low": range(10),
                       "close": range(10), "volume": [100] * 10}, index=idx)
    data = {"SPY": {"1d": df}}
    cutoff = idx[4]  # can see bars 0-3 only
    ctx = BacktestDataContext(data, cutoff)
    result = await ctx.get_bars("SPY", "1d", limit=200)
    assert len(result) == 4
    assert all(result.index < cutoff)
