from datetime import date

import pytest

from src.backtesting.intraday_limits import (
    INTRADAY_YFINANCE_MAX_DAYS,
    YFINANCE_MAX_DAYS_5M_30M,
    cap_intraday_warmup_months,
    default_warmup_months,
    intraday_fetch_span_days,
    intraday_yfinance_earliest_date,
    no_data_fetched_hint,
    parse_warmup_months,
    resolve_intraday_fetch_start_date,
    yfinance_max_days,
)


def test_parse_warmup_defaults_by_timeframe():
    assert parse_warmup_months({}, timeframe="1h") == 6
    assert parse_warmup_months({}, timeframe="15m") == 0
    assert parse_warmup_months({}, timeframe="1d") == 24
    assert default_warmup_months("15m") == 0


def test_yfinance_max_days_by_timeframe():
    assert yfinance_max_days("15m") == YFINANCE_MAX_DAYS_5M_30M
    assert yfinance_max_days("1h") == INTRADAY_YFINANCE_MAX_DAYS


def test_cap_reduces_24m_warmup_for_two_year_window():
    start = date(2024, 1, 1)
    end = date(2025, 12, 31)
    effective, reduced = cap_intraday_warmup_months(start, end, 24, timeframe="1h")
    assert reduced
    assert intraday_fetch_span_days(start, end, effective) <= INTRADAY_YFINANCE_MAX_DAYS


def test_cap_reduces_6m_warmup_for_15m_may_window():
    start = date(2026, 5, 1)
    end = date(2026, 5, 10)
    effective, reduced = cap_intraday_warmup_months(start, end, 6, timeframe="15m")
    assert reduced
    assert effective <= 1
    assert intraday_fetch_span_days(start, end, effective) <= YFINANCE_MAX_DAYS_5M_30M


def test_short_window_keeps_requested_warmup_for_1h():
    start = date(2025, 1, 1)
    end = date(2025, 6, 30)
    effective, reduced = cap_intraday_warmup_months(start, end, 6, timeframe="1h")
    assert effective == 6
    assert not reduced


def test_2023_backtest_rejected_for_1h():
    as_of = date(2026, 5, 16)
    with pytest.raises(ValueError, match="outside that window"):
        resolve_intraday_fetch_start_date(
            date(2023, 1, 1),
            date(2023, 1, 20),
            6,
            "1h",
            as_of=as_of,
        )


def test_recent_backtest_clips_warmup_to_yahoo_window():
    as_of = date(2026, 5, 16)
    earliest = intraday_yfinance_earliest_date(timeframe="1h", as_of=as_of)
    fetch_start, warning = resolve_intraday_fetch_start_date(
        date(2025, 4, 1),
        date(2025, 5, 1),
        12,
        "1h",
        as_of=as_of,
    )
    assert fetch_start == earliest
    assert warning is not None


def test_15m_usable_earliest_insets_rolling_edge():
    as_of = date(2026, 5, 16)
    earliest = intraday_yfinance_earliest_date(timeframe="15m", as_of=as_of)
    assert earliest == date(2026, 3, 18)
    with pytest.raises(ValueError, match="unreliable when start_date is before"):
        resolve_intraday_fetch_start_date(
            date(2026, 5, 1),
            date(2026, 5, 10),
            6,
            "15m",
            as_of=as_of,
        )


def test_no_data_hint_mentions_warmup_for_15m():
    hint = no_data_fetched_hint("15m", as_of=date(2026, 5, 16))
    assert "60" in hint
    assert "backtest_warmup_months" in hint
