"""ATR position sizing helpers for Adaptive Turtle."""

import pytest

from src.strategies.library.adaptive_turtle import compute_atr_position_size


def test_compute_atr_position_size_basic():
    # equity 100k, risk 1%, ATR $2 → 500 shares; cap by cash if needed
    q = compute_atr_position_size(
        equity=100_000.0,
        cash=100_000.0,
        last_close=100.0,
        atr=2.0,
        dollar_risk_pct=0.01,
    )
    assert q == 500.0


def test_compute_atr_position_size_capped_by_cash():
    q = compute_atr_position_size(
        equity=100_000.0,
        cash=5_000.0,
        last_close=100.0,
        atr=1.0,
        dollar_risk_pct=0.01,
    )
    # risk wants 1000 shares; cash allows only 50
    assert q == 50.0


def test_compute_atr_position_size_invalid_returns_none():
    assert compute_atr_position_size(100_000, 100_000, 100.0, float("nan"), 0.01) is None
    assert compute_atr_position_size(100_000, 100_000, 100.0, -1.0, 0.01) is None
    assert compute_atr_position_size(100_000, 100_000, 100.0, 2.0, 0.0) is None
    assert compute_atr_position_size(100_000, 100_000, 100.0, 2.0, 1.5) is None


@pytest.mark.asyncio
async def test_adaptive_turtle_buy_includes_quantity_when_atr_ok():
    import pandas as pd

    from src.strategies.base import PortfolioSnapshot
    from src.strategies.library.adaptive_turtle import AdaptiveTurtleStrategy
    from src.backtesting.data_context import BacktestDataContext

    idx = pd.date_range("2023-01-02", periods=260, freq="B", tz="UTC")
    n = len(idx)
    close = pd.Series(range(100, 100 + n), dtype=float, index=idx)
    df = pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )
    data = {"SPY": {"1d": df}, "QQQ": {"1d": df}}
    ctx = BacktestDataContext(data, idx[200])
    strat = AdaptiveTurtleStrategy()
    portfolio = PortfolioSnapshot(cash=100_000.0, initial_capital=100_000.0, equity=100_000.0)
    sigs = await strat.generate_signals(
        ["QQQ"],
        {
            "fast_period": 5,
            "slow_period": 3,
            "benchmark_symbol": "SPY",
            "benchmark_ma_period": 20,
            "atr_period": 14,
            "dollar_risk_pct": 0.01,
        },
        ctx,
        portfolio=portfolio,
    )
    buys = [s for s in sigs if s.direction == "buy"]
    assert buys
    assert buys[0].quantity is not None
    assert buys[0].quantity >= 1


@pytest.mark.asyncio
async def test_dollar_risk_zero_uses_no_explicit_quantity():
    import pandas as pd

    from src.strategies.base import PortfolioSnapshot
    from src.strategies.library.adaptive_turtle import AdaptiveTurtleStrategy
    from src.backtesting.data_context import BacktestDataContext

    idx = pd.date_range("2023-01-02", periods=260, freq="B", tz="UTC")
    n = len(idx)
    close = pd.Series(range(100, 100 + n), dtype=float, index=idx)
    df = pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )
    data = {"SPY": {"1d": df}, "QQQ": {"1d": df}}
    ctx = BacktestDataContext(data, idx[200])
    strat = AdaptiveTurtleStrategy()
    portfolio = PortfolioSnapshot(cash=100_000.0, initial_capital=100_000.0, equity=100_000.0)
    sigs = await strat.generate_signals(
        ["QQQ"],
        {
            "fast_period": 5,
            "slow_period": 3,
            "benchmark_symbol": "SPY",
            "benchmark_ma_period": 20,
            "dollar_risk_pct": 0,
        },
        ctx,
        portfolio=portfolio,
    )
    buys = [s for s in sigs if s.direction == "buy"]
    assert buys
    assert buys[0].quantity is None
