"""Shared strategy JSON for list/get API responses."""

from __future__ import annotations

from src.core.models import Strategy
from src.scheduler.run_schedule import parse_cron_frequency, schedule_mode
from src.scheduler.timeframe_interval import anchor_timeframe, min_interval_minutes


def registry_default_parameters(strategy_id: str) -> dict:
    """Class-level defaults from the strategy implementation (empty if unknown)."""
    from src.strategies.registry import REGISTRY, discover_strategies

    discover_strategies()
    cls = REGISTRY.get(strategy_id)
    if cls is None:
        return {}
    return dict(getattr(cls, "default_parameters", {}) or {})


def strategy_to_dict(s: Strategy) -> dict:
    cron = parse_cron_frequency(s.run_frequency or "")
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "is_active": s.is_active,
        "symbols": s.symbols,
        "timeframes": s.timeframes,
        "run_frequency": s.run_frequency,
        "schedule_mode": schedule_mode(s.run_frequency or ""),
        "cron_schedule": cron,
        "run_interval_minutes": min_interval_minutes(list(s.timeframes or [])),
        "run_anchor_timeframe": anchor_timeframe(list(s.timeframes or [])),
        "parameters": s.parameters or {},
        "default_parameters": registry_default_parameters(s.id),
        "max_symbols": s.max_symbols,
    }
