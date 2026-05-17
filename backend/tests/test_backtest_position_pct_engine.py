import pandas as pd
import pytest

from src.backtesting.engine import BacktestEngine
from src.strategies.base import BaseStrategy, TradeSignal


class _BuyOnceStrategy(BaseStrategy):
    id = "test_buy_once_pct"
    name = "Buy Once"

    async def generate_signals(self, symbols, parameters, ctx, portfolio=None):
        return [TradeSignal(symbols[0], "buy", "market")]


@pytest.mark.asyncio
async def test_position_pct_controls_buy_size():
    idx = pd.date_range("2023-01-02", periods=5, freq="B", tz="UTC")
    price = 100.0
    df = pd.DataFrame(
        {
            "open": [price] * 5,
            "high": [price] * 5,
            "low": [price] * 5,
            "close": [price] * 5,
            "volume": [1000] * 5,
        },
        index=idx,
    )
    data = {"SPY": {"1d": df}}
    engine = BacktestEngine(initial_capital=10_000, position_pct=0.25)
    metrics = await engine.run(_BuyOnceStrategy(), ["SPY"], {}, data, "1d")
    assert len(metrics.trades) == 1
    assert metrics.trades[0].quantity == pytest.approx(25.0)
    assert metrics.trades[0].entry_price == pytest.approx(100.0)
