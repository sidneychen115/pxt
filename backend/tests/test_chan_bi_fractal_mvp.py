import pandas as pd
import pytest

from src.strategies.base import DataContext
from src.strategies.library.chan_bi_fractal_mvp import ChanBiFractalMvpStrategy


class MockDataContext(DataContext):
    def __init__(self, df: pd.DataFrame, *, decision_ts=None):
        self._df = df
        self._decision_ts = decision_ts
        if self._decision_ts is None and not df.empty:
            self._decision_ts = df.index[-1]

    async def decision_time(self):
        ts = self._decision_ts
        if ts is None:
            return await super().decision_time()
        return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

    async def get_bars(self, symbol, timeframe, limit=200):
        return self._df.tail(limit).copy()

    async def get_option_chain(self, underlying, expiry=None):
        return pd.DataFrame()

    async def get_latest_quote(self, symbol):
        return {}


def _trending_bars_with_bottom_confirm(n_prefix: int = 27) -> pd.DataFrame:
    rows = []
    for i in range(n_prefix):
        o = 100.0 + i * 0.05
        h = o + 1.0
        lo = o - 1.0
        c = o
        rows.append((o, h, lo, c))
    rows.append((100.0, 101.0, 99.0, 100.0))
    rows.append((100.0, 100.0, 98.0, 99.0))
    rows.append((100.0, 102.0, 99.0, 101.0))
    o, h, lo, c = zip(*rows, strict=True)
    return pd.DataFrame(
        {
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": [1000] * len(rows),
        },
        index=pd.date_range("2023-01-01", periods=len(rows), freq="B"),
    )


@pytest.fixture
def strategy():
    return ChanBiFractalMvpStrategy()


async def test_chan_mvp_buy_without_sma(strategy):
    ctx = MockDataContext(_trending_bars_with_bottom_confirm())
    signals = await strategy.generate_signals(
        ["SPY"], {"use_sma_filter": False, "bar_limit": 300}, ctx
    )
    assert len(signals) == 1
    assert signals[0].direction == "buy"
    assert signals[0].symbol == "SPY"


async def test_chan_mvp_no_signal_when_flat(strategy):
    df = pd.DataFrame(
        {
            "open": [100.0] * 40,
            "high": [101.0] * 40,
            "low": [99.0] * 40,
            "close": [100.0] * 40,
            "volume": [1] * 40,
        },
        index=pd.date_range("2023-01-01", periods=40, freq="B"),
    )
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(["SPY"], {"use_sma_filter": False}, ctx)
    assert signals == []


async def test_chan_mvp_1h_uses_hourly_bars(strategy):
    df = _trending_bars_with_bottom_confirm()
    df.index = pd.date_range("2023-01-01", periods=len(df), freq="h", tz="UTC")
    ctx = MockDataContext(df)
    signals = await strategy.generate_signals(
        ["SPY"],
        {"timeframe": "1h", "use_sma_filter": False, "bar_limit": 300},
        ctx,
    )
    assert len(signals) == 1
    assert signals[0].direction == "buy"


async def test_chan_mvp_caches_fractal_per_bar_rounds(strategy, monkeypatch):
    """Same simulated bar + multiple generate_signals calls should not recompute merge/fractals."""
    calls = {"n": 0}
    import src.strategies.library.chan_bi_fractal_mvp as stratmod
    from src.strategies.chan_structure import mvp_fractal_signal_at_last_bar as real_mvp

    def counting_mvp(*args, **kwargs):
        calls["n"] += 1
        return real_mvp(*args, **kwargs)

    monkeypatch.setattr(stratmod, "mvp_chan_signal_at_last_bar", counting_mvp)

    df = _trending_bars_with_bottom_confirm()
    ts = df.index[-1]
    ctx = MockDataContext(df, decision_ts=ts)
    p = {"use_sma_filter": False, "bar_limit": 300}
    await strategy.generate_signals(["SPY"], p, ctx)
    await strategy.generate_signals(["SPY"], p, ctx)
    assert calls["n"] == 1
