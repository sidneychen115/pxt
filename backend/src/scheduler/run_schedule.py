"""Parse strategy run_frequency into APScheduler triggers (cron or interval)."""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

_INTERVAL_RE = re.compile(r"^(\d+)m$", re.IGNORECASE)
# Five cron fields: minute hour dom month dow
_CRON_RE = re.compile(
    r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$"
)


def is_interval_frequency(run_frequency: str) -> bool:
    return bool(_INTERVAL_RE.match((run_frequency or "").strip()))


def is_cron_frequency(run_frequency: str) -> bool:
    return bool(_CRON_RE.match((run_frequency or "").strip()))


def schedule_mode(run_frequency: str) -> str:
    """``cron`` | ``interval`` for API / UI."""
    if is_cron_frequency(run_frequency):
        return "cron"
    return "interval"


def build_trigger(run_frequency: str, tz: ZoneInfo) -> BaseTrigger:
    freq = (run_frequency or "1440m").strip()
    m = _INTERVAL_RE.match(freq)
    if m:
        return IntervalTrigger(minutes=int(m.group(1)), timezone=tz)
    if is_cron_frequency(freq):
        return CronTrigger.from_crontab(freq, timezone=tz)
    # Fallback: daily interval
    return IntervalTrigger(minutes=1440, timezone=tz)


def build_cron_frequency(
    hour: int,
    minute: int,
    *,
    days: str = "mon-fri",
) -> str:
    """Build a 5-field cron string in server timezone (America/Chicago)."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("hour must be 0-23 and minute 0-59")
    return f"{minute} {hour} * * {days}"


def parse_cron_frequency(run_frequency: str) -> dict | None:
    """Return {hour, minute, days} when run_frequency is cron; else None."""
    m = _CRON_RE.match((run_frequency or "").strip())
    if not m:
        return None
    minute_s, hour_s, _dom, _month, dow = m.groups()
    try:
        minute = int(minute_s)
        hour = int(hour_s)
    except ValueError:
        return None
    return {"hour": hour, "minute": minute, "days": dow}
