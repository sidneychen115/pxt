import pandas as pd
import pytest
from datetime import datetime, timezone

from src.backtesting.metrics import BacktestMetrics, TradeRecord
from src.backtesting.benchmark import enrich_metrics_with_benchmark


def test_enrich_alpha_vs_spy():
    idx = pd.date_range("2023-01-01", periods=5, freq="B", tz=timezone.utc)
    equity = pd.Series([100_000.0, 101_000.0, 102_000.0, 103_000.0, 110_000.0], index=idx)
    trade = TradeRecord(
        symbol="SPY",
        direction="buy",
        quantity=1.0,
        entry_time=idx[0],
        entry_price=100.0,
        exit_time=idx[-1],
        exit_price=110.0,
    )
    m = BacktestMetrics(
        initial_capital=100_000.0,
        final_equity=110_000.0,
        trades=[trade],
        equity_curve=equity,
    )
    spy = pd.DataFrame(
        {
            "open": [400.0, 400.5, 401.0, 401.5, 402.0],
            "high": [401.0, 401.5, 402.0, 402.5, 403.0],
            "low": [399.0, 399.5, 400.0, 400.5, 401.0],
            "close": [400.0, 400.0, 400.0, 400.0, 404.0],
            "volume": [1e7] * 5,
        },
        index=idx,
    )
    data = {"SPY": {"1d": spy}}
    out = enrich_metrics_with_benchmark(m, data, benchmark_symbol="SPY", timeframe="1d")
    assert out.benchmark_total_return == pytest.approx(404.0 / 400.0 - 1.0)
    assert out.alpha_vs_benchmark == pytest.approx(m.total_return - out.benchmark_total_return)
