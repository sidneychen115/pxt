from datetime import date

import pytest

from src.backtesting.intraday_limits import (
    intraday_yfinance_usable_earliest_date,
    resolve_intraday_fetch_start_date,
)
from src.data.providers.yfinance_provider import iter_yfinance_intraday_chunks


def test_iter_chunks_splits_long_span():
    chunks = iter_yfinance_intraday_chunks(date(2026, 3, 18), date(2026, 4, 30), chunk_days=20)
    assert len(chunks) >= 2
    assert chunks[0][0] == date(2026, 3, 18)
    assert chunks[-1][1] == date(2026, 4, 30)


def test_usable_earliest_insets_15m_edge():
    as_of = date(2026, 5, 16)
    assert intraday_yfinance_usable_earliest_date(timeframe="15m", as_of=as_of) == date(2026, 3, 18)


def test_start_on_rolling_edge_rejected_for_15m():
    as_of = date(2026, 5, 16)
    with pytest.raises(ValueError, match="unreliable when start_date is before"):
        resolve_intraday_fetch_start_date(
            date(2026, 3, 17),
            date(2026, 4, 30),
            0,
            "15m",
            as_of=as_of,
        )


def test_start_after_usable_ok():
    as_of = date(2026, 5, 16)
    fetch_start, warning = resolve_intraday_fetch_start_date(
        date(2026, 3, 18),
        date(2026, 4, 30),
        0,
        "15m",
        as_of=as_of,
    )
    assert fetch_start == date(2026, 3, 18)
    assert warning is None
