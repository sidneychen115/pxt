"""Shared trade-signal JSON for API responses."""

from __future__ import annotations

from datetime import datetime

from src.core.app_timezone import api_iso
from src.core.models import TradeSignalRecord


def iso_utc(dt: datetime) -> str:
    """Serializes timestamps in ISO-8601 using ``settings.timezone`` offset (Chicago by default)."""
    r = api_iso(dt)
    return r if r else ""


def _instrument_symbol(
    signal: TradeSignalRecord,
    stock_symbol: str | None,
    option_symbol: str | None,
) -> str | None:
    if signal.stock_id is not None:
        return stock_symbol
    if signal.option_id is not None:
        return option_symbol
    return None


def signal_to_dict(
    signal: TradeSignalRecord,
    *,
    stock_symbol: str | None = None,
    option_symbol: str | None = None,
) -> dict:
    return {
        "id": signal.id,
        "strategy_id": signal.strategy_id,
        "symbol": _instrument_symbol(signal, stock_symbol, option_symbol),
        "stock_id": signal.stock_id,
        "option_id": signal.option_id,
        "signal_time": iso_utc(signal.signal_time),
        "direction": signal.direction,
        "quantity": float(signal.quantity) if signal.quantity else None,
        "order_type": signal.order_type,
        "limit_price": float(signal.limit_price) if signal.limit_price else None,
        "stop_price": float(signal.stop_price) if signal.stop_price else None,
        "confidence": float(signal.confidence) if signal.confidence else None,
        "reasoning": signal.reasoning,
        "status": signal.status,
        "created_at": iso_utc(signal.created_at),
    }


def signal_detail_to_dict(
    signal: TradeSignalRecord,
    *,
    stock_symbol: str | None = None,
    option_symbol: str | None = None,
) -> dict:
    out = signal_to_dict(
        signal, stock_symbol=stock_symbol, option_symbol=option_symbol
    )
    out["metadata"] = signal.metadata_
    return out
