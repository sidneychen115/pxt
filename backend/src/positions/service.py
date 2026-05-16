from decimal import Decimal
from typing import Any


def apply_fill(
    current: tuple[Decimal, Decimal] | None,
    side: str,
    quantity: Decimal,
    fill_price: Decimal,
) -> tuple[Decimal, Decimal]:
    if quantity <= 0 or fill_price <= 0:
        raise ValueError("quantity and fill_price must be positive")
    if side == "buy":
        if current is None:
            return quantity, fill_price
        q0, a0 = current
        new_q = q0 + quantity
        new_avg = (q0 * a0 + quantity * fill_price) / new_q
        return new_q, new_avg
    if side == "sell":
        if current is None:
            raise ValueError("no position to sell")
        q0, a0 = current
        if quantity > q0:
            raise ValueError("sell quantity exceeds position")
        return q0 - quantity, a0
    raise ValueError(f"invalid side: {side}")


def filter_signals_for_positions(
    signals: list[Any],
    positions_by_symbol: dict[str, Decimal],
) -> list[Any]:
    out = []
    for sig in signals:
        sym = sig.symbol if hasattr(sig, "symbol") else sig["symbol"]
        direction = sig.direction if hasattr(sig, "direction") else sig["direction"]
        qty = positions_by_symbol.get(sym, Decimal(0))
        if direction == "buy" and qty > 0:
            continue
        if direction == "sell" and qty <= 0:
            continue
        out.append(sig)
    return out


def position_summary_from_rows(rows: list[tuple[Decimal, Decimal, Decimal | None]]) -> dict:
    open_symbols = sum(1 for q, _, _ in rows if q > 0)
    total_shares = sum(q for q, _, _ in rows if q > 0)
    value = Decimal(0)
    for q, avg, mark in rows:
        if q <= 0:
            continue
        px = mark if mark is not None else avg
        value += q * px
    return {
        "open_symbols": open_symbols,
        "total_shares": float(total_shares),
        "position_value": float(value),
    }
