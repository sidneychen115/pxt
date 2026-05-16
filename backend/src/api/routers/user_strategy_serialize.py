from __future__ import annotations

from src.core.models import Strategy, UserStrategy
from src.api.routers.strategy_serialize import registry_default_parameters
from src.scheduler.run_schedule import parse_cron_frequency, schedule_mode
from src.scheduler.timeframe_interval import anchor_timeframe, min_interval_minutes


def user_strategy_to_dict(us: UserStrategy, pool: Strategy) -> dict:
    cron = parse_cron_frequency(us.run_frequency or "")
    return {
        "row_id": us.id,
        "id": us.strategy_id,
        "user_id": us.user_id,
        "name": pool.name,
        "description": pool.description,
        "is_active": us.is_active,
        "symbols": us.symbols,
        "timeframes": us.timeframes,
        "run_frequency": us.run_frequency,
        "schedule_mode": schedule_mode(us.run_frequency or ""),
        "cron_schedule": cron,
        "run_interval_minutes": min_interval_minutes(list(us.timeframes or [])),
        "run_anchor_timeframe": anchor_timeframe(list(us.timeframes or [])),
        "parameters": us.parameters or {},
        "default_parameters": registry_default_parameters(us.strategy_id),
        "max_symbols": us.max_symbols,
        "updated_at": us.updated_at.isoformat() if us.updated_at else None,
    }
