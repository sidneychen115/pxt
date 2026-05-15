from datetime import date, datetime, timezone

from src.strategies.ha_cache.calendar import (
    current_week_start,
    last_completed_week_end,
    previous_calendar_month,
)


def test_wednesday_week_boundaries_mon_fri():
    # 2025-03-12 Wed CT — in-progress week Mon 3/10–Fri 3/14; prior week ends Fri 3/7
    as_of = datetime(2025, 3, 12, 20, 0, tzinfo=timezone.utc)
    assert current_week_start(as_of) == date(2025, 3, 10)
    assert last_completed_week_end(as_of) == date(2025, 3, 7)


def test_saturday_uses_last_friday_as_completed_week():
    as_of = datetime(2025, 3, 15, 15, 0, tzinfo=timezone.utc)  # Sat CT
    assert last_completed_week_end(as_of) == date(2025, 3, 14)
    assert current_week_start(as_of) == date(2025, 3, 10)


def test_previous_month():
    assert previous_calendar_month(2025, 3) == (2025, 2)
    assert previous_calendar_month(2025, 1) == (2024, 12)
