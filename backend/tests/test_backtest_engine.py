import pytest
import pandas as pd
import numpy as np
from src.backtesting.engine import BacktestEngine
from src.backtesting.exit_policy import ExitPolicy
from src.strategies.base import BaseStrategy, TradeSignal
from src.strategies.library.ma_crossover import MovingAverageCrossover


class _BuyThenSellStrategy(BaseStrategy):
    """First signal day: buy; thereafter: sell (for testing disable_sell_signal)."""

    id = "test_buy_then_sell"
    name = "Test Buy Then Sell"
    _bought: bool = False

    async def generate_signals(self, symbols, parameters, ctx, portfolio=None):
        sym = symbols[0]
        bars = await ctx.get_bars(sym, "1d", limit=500)
        if len(bars) < 2:
            return []
        if not self._bought:
            self._bought = True
            return [TradeSignal(sym, "buy", "market", quantity=10)]
        return [TradeSignal(sym, "sell", "market", quantity=10)]


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
    assert len(metrics.equity_curve) > 0


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


async def test_inclusive_context_includes_current_bar():
    from src.backtesting.data_context import BacktestDataContext
    idx = pd.date_range("2023-01-02", periods=10, freq="B", tz="UTC")
    df = pd.DataFrame({"open": range(10), "high": range(10), "low": range(10),
                       "close": range(10), "volume": [100] * 10}, index=idx)
    data = {"SPY": {"1d": df}}
    ctx = BacktestDataContext(data, idx[4], inclusive_end=True)
    result = await ctx.get_bars("SPY", "1d", limit=200)
    assert len(result) == 5
    assert result.index.max() == idx[4]


class _BuyWhenTwoDailyBarsStrategy(BaseStrategy):
    id = "test_buy_two_bars"
    name = "Buy when >=2 daily bars visible"

    async def generate_signals(self, symbols, parameters, ctx, portfolio=None):
        sym = symbols[0]
        bars = await ctx.get_bars(sym, "1d", limit=500)
        if len(bars) >= 2:
            return [TradeSignal(sym, "buy", "market", quantity=1)]
        return []


async def test_same_close_fills_at_signal_bar_close():
    idx = pd.date_range("2023-01-02", periods=4, freq="B", tz="UTC")
    closes = [100.0, 101.0, 102.0, 105.0]
    df = pd.DataFrame({
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * 4,
    }, index=idx)
    data = {"SPY": {"1d": df}}
    strat = _BuyWhenTwoDailyBarsStrategy()
    engine = BacktestEngine(initial_capital=10_000, fill_mode="same_close")
    metrics = await engine.run(strat, ["SPY"], {}, data, "1d")
    assert len(metrics.trades) >= 1
    t = metrics.trades[0]
    assert t.entry_price == pytest.approx(101.0)
    assert t.entry_time == idx[1]


async def test_disable_sell_signal_skips_strategy_sell():
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(disable_sell_signal=True),
    )
    strategy = _BuyThenSellStrategy()
    data = make_trending_data("SPY", 30, "up")
    metrics = await engine.run(strategy, ["SPY"], {}, data, "1d")
    assert len(metrics.trades) >= 1
    assert all(t.exit_reason != "signal" for t in metrics.trades)


async def test_sell_signal_closes_without_disable():
    engine = BacktestEngine(initial_capital=10_000, exit_policy=None)
    strategy = _BuyThenSellStrategy()
    data = make_trending_data("SPY", 30, "up")
    metrics = await engine.run(strategy, ["SPY"], {}, data, "1d")
    assert any(t.exit_reason == "signal" for t in metrics.trades)


class _DualSymbolBuyStrategy(BaseStrategy):
    """First recall round: buy SPY; second: buy QQQ. Records portfolio.cash each call."""

    id = "test_dual_buy"
    name = "Dual Buy"
    step = 0

    def __init__(self):
        self.cash_seen: list[float] = []

    async def generate_signals(self, symbols, parameters, ctx, portfolio=None):
        if portfolio is not None and portfolio.cash is not None:
            self.cash_seen.append(float(portfolio.cash))
        if self.step == 0:
            self.step = 1
            return [TradeSignal("SPY", "buy", "market", quantity=10)]
        if self.step == 1:
            self.step = 2
            return [TradeSignal("QQQ", "buy", "market", quantity=5)]
        return []


async def test_portfolio_recall_decreases_cash():
    """Second generate_signals call in same bar sees reduced cash after first fill."""
    data = make_trending_data("SPY", 40, "up")
    data["QQQ"] = make_trending_data("QQQ", 40, "up")["QQQ"]
    strat = _DualSymbolBuyStrategy()
    engine = BacktestEngine(initial_capital=100_000.0)
    await engine.run(strat, ["SPY", "QQQ"], {}, data, "1d")
    assert len(strat.cash_seen) >= 2
    assert strat.cash_seen[0] == pytest.approx(100_000.0)
    assert strat.cash_seen[1] < strat.cash_seen[0]


async def test_profit_factor_no_losers():
    """profit_factor returns None (not infinity) when no losing trades."""
    from src.backtesting.metrics import BacktestMetrics, TradeRecord
    from datetime import datetime, timezone
    trade = TradeRecord(
        symbol="SPY", direction="buy", quantity=1.0,
        entry_time=datetime(2023, 1, 2, tzinfo=timezone.utc), entry_price=100.0,
        exit_time=datetime(2023, 1, 3, tzinfo=timezone.utc), exit_price=110.0,
        exit_reason="signal",
    )
    equity = pd.Series([10000.0, 11000.0])
    metrics = BacktestMetrics(
        initial_capital=10000.0, final_equity=11000.0,
        trades=[trade], equity_curve=equity,
    )
    assert metrics.profit_factor is None  # no losing trades → None, not inf
    assert metrics.win_rate == 1.0
    assert metrics.total_return == pytest.approx(0.1)
