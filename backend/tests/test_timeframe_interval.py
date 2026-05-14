import pytest

from src.scheduler.timeframe_interval import anchor_timeframe, min_interval_minutes, timeframe_minutes


def test_min_interval_picks_smallest_bar():
    assert min_interval_minutes(["1d", "5m"]) == 5


def test_anchor_timeframe():
    assert anchor_timeframe(["1d", "5m", "15m"]) == "5m"


def test_unknown_timeframe_defaults_to_daily_minutes():
    assert timeframe_minutes("unknown") == 1440


@pytest.mark.parametrize(
    "tfs,expected",
    [
        ([], 1440),
        (["1h"], 60),
    ],
)
def test_min_interval_edges(tfs, expected):
    assert min_interval_minutes(tfs) == expected
