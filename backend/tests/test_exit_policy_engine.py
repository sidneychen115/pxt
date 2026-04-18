import pytest
import pandas as pd
from src.backtesting.engine import BacktestEngine
from src.backtesting.exit_policy import ExitPolicy
from src.strategies.base import BaseStrategy, TradeSignal


def make_bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Build OHLCV DataFrame. Each row is (open, high, low, close)."""
    dates = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=dates, columns=["open", "high", "low", "close"])
    df["volume"] = 1000
    return df


class _BuyOnceStrategy(BaseStrategy):
    """Buy on the first bar (0 bars visible), never sell."""
    name = "_test_buy_once"

    def __init__(self):
        self._bought = False

    async def generate_signals(self, symbols, parameters, ctx):
        sym = symbols[0]
        bars = await ctx.get_bars(sym, "1d")
        if len(bars) == 0 and not self._bought:
            self._bought = True
            return [TradeSignal(symbol=sym, direction="buy", order_type="market", reasoning="test")]
        return []


async def test_stop_loss_pct_close():
    # Buy fills at t1 open=100. SL=5% → stop at 95.
    # t2: close=93 < 95 → SL queued. t3: fill at open=92.
    bars = make_bars([
        (100, 101, 99, 100),  # t0: buy signal (0 bars visible)
        (100, 102, 99, 101),  # t1: buy fills at open=100; close=101 > 95 → hold
        (101, 102, 90, 93),   # t2: close=93 < 95 → SL queued
        (92,  92,  92, 92),   # t3: SL fills at open=92
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_pct=0.05),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    assert len(metrics.trades) == 1
    trade = metrics.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(92.0)


async def test_stop_loss_abs_close():
    # Buy 10 shares at 100 = $1000 cost. SL abs=$200 → stop at 100-200/10=80.
    # t2: close=79 < 80 → SL queued. t3: fill at open=78.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),  # t1: buy 10 shares at 100
        (101, 102, 75, 79),   # t2: close=79 < 80 → SL queued
        (78,  78,  78, 78),   # t3: fill at 78
    ])

    class _BuyFixedQtyStrategy(BaseStrategy):
        name = "_test_fixed_qty"
        def __init__(self):
            self._bought = False
        async def generate_signals(self, symbols, parameters, ctx):
            sym = symbols[0]
            bars = await ctx.get_bars(sym, "1d")
            if len(bars) == 0 and not self._bought:
                self._bought = True
                return [TradeSignal(symbol=sym, direction="buy", order_type="market", reasoning="test", quantity=10)]
            return []

    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_abs=200.0),
    )
    metrics = await engine.run(_BuyFixedQtyStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(78.0)


async def test_stop_loss_ohlc():
    # Buy at t1 open=100. SL=5% → stop=95. t2: low=90 < 95 → fill at 95 immediately.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),  # t1: buy at 100
        (101, 102, 90, 93),   # t2: low=90 < 95 → fill at 95 (stop price)
        (92,  92,  92, 92),   # t3: not reached for this trade
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(stop_loss_pct=0.05, price_check_mode="ohlc"),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(95.0)


async def test_no_policy_behavior_unchanged():
    # Without exit_policy, position holds through SL-triggering bars → end_of_backtest.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (101, 102, 90, 93),   # would trigger SL if policy existed
        (92,  92,  92, 92),
    ])
    engine = BacktestEngine(initial_capital=10_000)
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    assert metrics.trades[0].exit_reason == "end_of_backtest"
