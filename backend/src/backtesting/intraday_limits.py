"""yfinance intraday history limits for backtest data fetch."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from src.core.app_timezone import app_zone

# Slightly under Yahoo's published caps (see YFinanceProvider).
YFINANCE_MAX_DAYS_1M = 7
YFINANCE_MAX_DAYS_5M_30M = 60
YFINANCE_MAX_DAYS_1H = 728

# Yahoo often rejects a single 15m request that starts exactly on the rolling 60d edge.
YFINANCE_SHORT_INTRADAY_USABLE_BUFFER_DAYS = 1
# Max calendar days per yfinance.download call for short intraday (span, not rolling window).
YFINANCE_SHORT_INTRADAY_CHUNK_DAYS = 20

# Backward-compatible alias for 1h/4h callers.
INTRADAY_YFINANCE_MAX_DAYS = YFINANCE_MAX_DAYS_1H

DEFAULT_DAILY_WARMUP_MONTHS = 24
DEFAULT_INTRADAY_WARMUP_MONTHS = 6
DEFAULT_SHORT_INTRADAY_WARMUP_MONTHS = 0

SHORT_INTRADAY_TIMEFRAMES = frozenset({"5m", "15m", "30m"})
INTRADAY_TIMEFRAMES = frozenset({"1m", *SHORT_INTRADAY_TIMEFRAMES, "1h", "4h"})


def is_intraday_timeframe(timeframe: str) -> bool:
    return timeframe in INTRADAY_TIMEFRAMES


def yfinance_max_days(timeframe: str) -> int:
    """Rolling lookback Yahoo allows for ``timeframe`` (calendar days)."""
    if timeframe == "1m":
        return YFINANCE_MAX_DAYS_1M
    if timeframe in SHORT_INTRADAY_TIMEFRAMES:
        return YFINANCE_MAX_DAYS_5M_30M
    if timeframe in ("1h", "4h"):
        return YFINANCE_MAX_DAYS_1H
    return YFINANCE_MAX_DAYS_1H


def default_warmup_months(timeframe: str) -> int:
    if not is_intraday_timeframe(timeframe):
        return DEFAULT_DAILY_WARMUP_MONTHS
    if timeframe == "1m" or timeframe in SHORT_INTRADAY_TIMEFRAMES:
        return DEFAULT_SHORT_INTRADAY_WARMUP_MONTHS
    return DEFAULT_INTRADAY_WARMUP_MONTHS


def parse_warmup_months(parameters: dict | None, *, timeframe: str) -> int:
    default = default_warmup_months(timeframe)
    try:
        months = int((parameters or {}).get("backtest_warmup_months", default))
    except (TypeError, ValueError):
        months = default
    return max(0, min(months, 120))


def intraday_fetch_span_days(start_date: date, end_date: date, warmup_months: int) -> int:
    """Calendar days from warmup fetch start through end of simulation window."""
    sim_end = end_date + timedelta(days=1)
    fetch_start = start_date - relativedelta(months=warmup_months)
    return (sim_end - fetch_start).days


def cap_intraday_warmup_months(
    start_date: date,
    end_date: date,
    warmup_months: int,
    *,
    timeframe: str,
    max_days: int | None = None,
) -> tuple[int, bool]:
    """Reduce warmup months until fetch span fits Yahoo's limit for ``timeframe``."""
    if max_days is None:
        max_days = yfinance_max_days(timeframe)
    requested = warmup_months
    while warmup_months >= 0:
        if intraday_fetch_span_days(start_date, end_date, warmup_months) <= max_days:
            return warmup_months, warmup_months < requested
        warmup_months -= 1
    return 0, requested > 0


def intraday_yfinance_usable_earliest_date(
    *,
    timeframe: str = "1h",
    as_of: date | None = None,
    max_days: int | None = None,
) -> date:
    """First start date that reliably returns bars (inset from the rolling window edge)."""
    if max_days is None:
        max_days = yfinance_max_days(timeframe)
    if timeframe in SHORT_INTRADAY_TIMEFRAMES or timeframe == "1m":
        max_days = max(1, max_days - YFINANCE_SHORT_INTRADAY_USABLE_BUFFER_DAYS)
    if as_of is None:
        as_of = datetime.now(app_zone()).date()
    return as_of - timedelta(days=max_days)


def intraday_yfinance_earliest_date(
    *,
    timeframe: str = "1h",
    as_of: date | None = None,
    max_days: int | None = None,
) -> date:
    """Earliest date shown in UI / validation (usable inset for 5m–30m)."""
    return intraday_yfinance_usable_earliest_date(
        timeframe=timeframe, as_of=as_of, max_days=max_days
    )


def resolve_intraday_fetch_start_date(
    start_date: date,
    end_date: date,
    warmup_months: int,
    timeframe: str,
    *,
    as_of: date | None = None,
) -> tuple[date, str | None]:
    """Validate rolling-window availability; optionally clip warmup fetch start to Yahoo's limit.

    Raises ``ValueError`` when the whole simulation ends before data exists.
    Returns ``(fetch_start_date, warning_or_none)``.
    """
    if not is_intraday_timeframe(timeframe):
        fetch_start = start_date - relativedelta(months=warmup_months)
        return fetch_start, None

    max_days = yfinance_max_days(timeframe)
    usable = intraday_yfinance_usable_earliest_date(
        timeframe=timeframe, as_of=as_of, max_days=max_days
    )
    fetch_start = start_date - relativedelta(months=warmup_months)

    if end_date < usable:
        as_of_s = as_of or datetime.now(app_zone()).date()
        raise ValueError(
            f"yfinance only provides {timeframe} bars for roughly the last "
            f"{max_days} days (from {as_of_s}, earliest reliable start about {usable}). "
            f"Your backtest ends on {end_date}, which is outside that window. "
            f"Use end_date on or after {usable}, or use timeframe 1d for older history."
        )

    if start_date < usable:
        raise ValueError(
            f"yfinance {timeframe} data is unreliable when start_date is before {usable} "
            f"(rolling ~{max_days}-day window from today). "
            f"Your start_date is {start_date}; use start_date on or after {usable}, "
            f"or shorten the range."
        )

    if fetch_start >= usable:
        return fetch_start, None

    warning = (
        f"yfinance {timeframe} history only reaches about {usable}; "
        f"preload clipped from {fetch_start} to {usable} "
        f"(requested backtest_warmup_months={warmup_months})."
    )
    return usable, warning


def intraday_span_error_message(
    timeframe: str,
    start_date: date,
    end_date: date,
    warmup_months: int,
    days_span: int,
    *,
    max_days: int | None = None,
) -> str:
    if max_days is None:
        max_days = yfinance_max_days(timeframe)
    sim_days = (end_date - start_date).days + 1
    return (
        f"yfinance intraday data ({timeframe}) is limited to about {max_days} days; "
        f"warmup+window span is {days_span} days "
        f"(simulation {sim_days} days, backtest_warmup_months={warmup_months}). "
        "Shorten the backtest date range or set parameters.backtest_warmup_months lower."
    )


def no_data_fetched_hint(timeframe: str, *, as_of: date | None = None) -> str:
    """Extra guidance appended when a backtest fetch returns no bars."""
    max_days = yfinance_max_days(timeframe)
    earliest = intraday_yfinance_earliest_date(timeframe=timeframe, as_of=as_of)
    if timeframe in SHORT_INTRADAY_TIMEFRAMES or timeframe == "1m":
        return (
            f" Yahoo {timeframe} is only available for roughly the last {max_days} days "
            f"(reliable start about {earliest}; the exact rolling edge often returns zero bars). "
            "Use start_date on or after that date, keep backtest_warmup_months at 0–1, "
            "or use 1h/1d for longer history."
        )
    return (
        f" Yahoo {timeframe} is only available for roughly the last {max_days} days "
        f"(about {earliest} onward). "
        "Historical ranges such as 2023 are not available—use 1d or pick recent dates."
    )
