"""Benchmark buy-and-hold vs strategy equity curve (e.g. alpha over SPY)."""

from __future__ import annotations

from src.backtesting.metrics import BacktestMetrics


def enrich_metrics_with_benchmark(
    metrics: BacktestMetrics,
    data: dict,
    *,
    benchmark_symbol: str = "SPY",
    timeframe: str = "1d",
) -> BacktestMetrics:
    """
    Align benchmark closes to the strategy equity curve index and set
    ``benchmark_total_return`` and ``alpha_vs_benchmark``.
    """
    sym_data = data.get(benchmark_symbol, {}).get(timeframe)
    if sym_data is None or getattr(sym_data, "empty", True):
        return metrics
    eq = metrics.equity_curve
    if eq is None or eq.empty:
        return metrics
    start, end = eq.index[0], eq.index[-1]
    bench = sym_data[(sym_data.index >= start) & (sym_data.index <= end)]
    if len(bench) < 2:
        return metrics
    c0 = float(bench["close"].iloc[0])
    c1 = float(bench["close"].iloc[-1])
    if c0 <= 0:
        return metrics
    bh = c1 / c0 - 1.0
    alpha = metrics.total_return - bh
    return BacktestMetrics(
        initial_capital=metrics.initial_capital,
        final_equity=metrics.final_equity,
        trades=metrics.trades,
        equity_curve=metrics.equity_curve,
        benchmark_total_return=bh,
        alpha_vs_benchmark=alpha,
    )
