"""Tests for backtest wall-clock duration in API summaries."""

from datetime import datetime, timedelta, timezone

from src.api.routers.backtests import _backtest_duration_seconds
from src.core.models import Backtest


def _bt(**kwargs) -> Backtest:
    base = {
        "user_id": 1,
        "strategy_id": "test",
        "start_date": datetime(2024, 1, 1).date(),
        "end_date": datetime(2024, 6, 1).date(),
        "symbols": ["SPY"],
        "initial_capital": 100_000,
        "status": "completed",
    }
    base.update(kwargs)
    return Backtest(**base)


def test_duration_completed():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    bt = _bt(created_at=t0, completed_at=t0 + timedelta(minutes=5, seconds=12), status="completed")
    assert _backtest_duration_seconds(bt) == 312.0


def test_duration_running_uses_progress_updated_at():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    bt = _bt(
        created_at=t0,
        completed_at=None,
        progress_updated_at=t0 + timedelta(seconds=90),
        status="running",
    )
    assert _backtest_duration_seconds(bt) == 90.0


def test_duration_queued_without_heartbeat_returns_none():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    bt = _bt(created_at=t0, completed_at=None, progress_updated_at=None, status="queued")
    assert _backtest_duration_seconds(bt) is None
