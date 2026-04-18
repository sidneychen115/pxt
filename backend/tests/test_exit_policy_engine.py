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


async def test_take_profit_pct_close():
    # Buy at t1 open=100. TP=15% → tp=115.
    # t2: close=116 >= 115 → TP queued. t3: fill at open=117.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),   # t1: buy at 100; close=101 < 115 → hold
        (101, 120, 100, 116),  # t2: close=116 >= 115 → TP queued
        (117, 120, 116, 118),  # t3: fill at open=117
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(take_profit_pct=0.15),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(117.0)


async def test_take_profit_abs_close():
    # Buy 10 shares at 100 = $1000. TP abs=$200 → tp=100+200/10=120.
    # t2: close=121 >= 120 → TP queued. t3: fill at open=122.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (101, 125, 100, 121),
        (122, 125, 120, 123),
    ])

    class _BuyFixedQtyStrategy2(BaseStrategy):
        name = "_test_fixed_qty2"
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
        exit_policy=ExitPolicy(take_profit_abs=200.0),
    )
    metrics = await engine.run(_BuyFixedQtyStrategy2(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(122.0)


async def test_take_profit_ohlc():
    # Buy at t1 open=100. TP=15% → tp=115. t2: high=116 >= 115 → fill at 115 exactly.
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 102, 99, 101),   # t1: buy at 100
        (101, 116, 100, 112),  # t2: high=116 >= 115 → fill at 115
        (112, 113, 111, 112),  # t3: not reached
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(take_profit_pct=0.15, price_check_mode="ohlc"),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(115.0)


async def test_trailing_stop_immediate():
    # trailing_stop_pct=0.05, no activation threshold → active from entry.
    # Buy at t1 open=100. peak starts at 100.
    # t1: close=110 → peak=110, trail=104.5; close=110 > 104.5 → hold
    # t2: close=108 → peak still 110, trail=104.5; close=108 > 104.5 → hold
    # t3: close=104 → close=104 < 104.5 → TS queued; fill at t4 open=103
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 111, 99, 110),   # t1: buy at 100; peak=110
        (110, 112, 107, 108),  # t2: peak=110, trail=104.5; hold
        (108, 109, 103, 104),  # t3: close=104 < 104.5 → TS queued
        (103, 104, 102, 103),  # t4: fill at open=103
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(trailing_stop_pct=0.05),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(103.0)


async def test_trailing_stop_ohlc():
    # trailing_stop_pct=0.05, ohlc mode. peak updates on bar high.
    # Buy at t1 open=100.
    # t1: high=115 → peak=115, trail=109.25; low=110 > 109.25 → hold
    # t2: high=116 → peak=116, trail=110.2; low=108 < 110.2 → TS at 110.2
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 115, 110, 113),  # t1: buy at 100; peak=115, trail=109.25; low=110 > 109.25 → hold
        (113, 116, 108, 111),  # t2: peak=116, trail=110.2; low=108 < 110.2 → TS at 110.2
        (108, 109, 107, 108),
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(trailing_stop_pct=0.05, price_check_mode="ohlc"),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(116 * 0.95)  # 110.2


async def test_trailing_stop_with_activate():
    # trailing_stop_pct=0.05, trailing_activate_pct=0.10 → activates when price >= 110.
    # Buy at t1 open=100.
    # t1: close=105 < 110 → not active, peak=105
    # t2: close=112 >= 110 → active, peak=112, trail=106.4; close=112 > 106.4 → hold
    # t3: close=106 < 106.4 → TS queued; fill at t4 open=105
    bars = make_bars([
        (100, 101, 99, 100),
        (100, 106, 99, 105),   # t1: buy at 100; peak=105 < 110 → not active
        (105, 113, 104, 112),  # t2: peak=112 >= 110 → active; trail=106.4; hold
        (112, 113, 105, 106),  # t3: close=106 < 106.4 → TS queued
        (105, 106, 104, 105),  # t4: fill at open=105
    ])
    engine = BacktestEngine(
        initial_capital=10_000,
        exit_policy=ExitPolicy(trailing_stop_pct=0.05, trailing_activate_pct=0.10),
    )
    metrics = await engine.run(_BuyOnceStrategy(), ["AAPL"], {}, {"AAPL": {"1d": bars}}, "1d")
    trade = metrics.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == pytest.approx(105.0)
