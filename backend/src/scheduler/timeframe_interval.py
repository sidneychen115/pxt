"""Map K-line periods to scheduler intervals (live strategy runs)."""

from __future__ import annotations

# Minutes between runs when this is the smallest selected timeframe.
TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1wk": 10080,
    "1mo": 43200,
}

KNOWN_TIMEFRAMES = frozenset(TIMEFRAME_MINUTES.keys())


def timeframe_minutes(tf: str) -> int:
    """Return bar length in minutes; unknown values default to daily."""
    return TIMEFRAME_MINUTES.get(tf, 1440)


def min_interval_minutes(timeframes: list[str]) -> int:
    """Smallest bar length in minutes among selected timeframes (highest run frequency)."""
    if not timeframes:
        return 1440
    return max(1, min(timeframe_minutes(tf) for tf in timeframes))


def anchor_timeframe(timeframes: list[str]) -> str:
    """The timeframe that sets the minimum interval (for display)."""
    if not timeframes:
        return "1d"
    best_tf = timeframes[0]
    best_m = timeframe_minutes(best_tf)
    for tf in timeframes[1:]:
        m = timeframe_minutes(tf)
        if m < best_m:
            best_m = m
            best_tf = tf
    return best_tf
