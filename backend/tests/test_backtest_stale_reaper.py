from datetime import datetime, timedelta, timezone

import pytest

from src.api.backtest_stale_reaper import queued_stale_after, stale_after


def test_stale_after_defaults():
    assert stale_after().total_seconds() == 1800
    assert queued_stale_after().total_seconds() == 86400


def test_queued_stale_much_longer_than_running():
    assert queued_stale_after() > stale_after() * 10
