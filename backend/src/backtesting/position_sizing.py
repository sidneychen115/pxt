"""Backtest position sizing from ``parameters.backtest_position_pct``."""

from __future__ import annotations

DEFAULT_BACKTEST_POSITION_PCT = 0.1


def parse_backtest_position_pct(parameters: dict | None) -> float:
    """Fraction of available cash to deploy per buy (0–1). Default 10%."""
    raw = (parameters or {}).get("backtest_position_pct", DEFAULT_BACKTEST_POSITION_PCT)
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        pct = DEFAULT_BACKTEST_POSITION_PCT
    if pct > 1.0 and pct <= 100.0:
        pct = pct / 100.0
    return max(0.0, min(1.0, pct))


def buy_quantity_for_signal(
    *,
    cash: float,
    fill_price: float,
    position_pct: float,
    signal_quantity: float | None,
) -> float:
    """Shares/units to buy: cap by ``position_pct`` of cash; optional strategy qty is an upper bound."""
    if fill_price <= 0 or cash <= 0 or position_pct <= 0:
        return 0.0
    budget = cash * position_pct
    cap_qty = budget / fill_price
    if signal_quantity is not None:
        qty = min(float(signal_quantity), cap_qty)
    else:
        qty = cap_qty
    if signal_quantity is None:
        return float(max(1, int(qty)))
    return max(0.0, qty)
