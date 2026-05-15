from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.scheduler.run_schedule import (
    build_cron_frequency,
    build_trigger,
    is_cron_frequency,
    is_interval_frequency,
    parse_cron_frequency,
    schedule_mode,
)

TZ = ZoneInfo("America/Chicago")


def test_interval_frequency():
    assert is_interval_frequency("1440m")
    assert schedule_mode("1440m") == "interval"
    t = build_trigger("1440m", TZ)
    assert isinstance(t, IntervalTrigger)


def test_cron_frequency():
    assert is_cron_frequency("0 14 * * mon-fri")
    assert schedule_mode("0 14 * * mon-fri") == "cron"
    t = build_trigger("0 14 * * mon-fri", TZ)
    assert isinstance(t, CronTrigger)


def test_build_and_parse_cron():
    freq = build_cron_frequency(14, 0, days="mon-fri")
    assert freq == "0 14 * * mon-fri"
    parsed = parse_cron_frequency(freq)
    assert parsed == {"hour": 14, "minute": 0, "days": "mon-fri"}
