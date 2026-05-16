"""Position mark-to-market for live strategy sizing."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.positions.repository import load_positions_by_symbol


async def holdings_qty_and_mv(
    session: AsyncSession,
    user_id: int,
    marks: dict[str, float],
) -> tuple[dict[str, float], float]:
    """Return long-only ``{symbol: qty}`` and equity using ``marks`` (last/mid fallback)."""
    raw = await load_positions_by_symbol(session, user_id)
    out: dict[str, float] = {}
    total = 0.0
    for sym, qty in raw.items():
        qf = float(qty)
        if qf <= 0:
            continue
        px = marks.get(sym)
        if px is None or px <= 0:
            continue
        out[sym] = qf
        total += qf * px
    return out, total
