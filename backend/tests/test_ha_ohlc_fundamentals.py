"""HA OHLC bars + fundamentals tables (shared cache)."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from src.core.models import FundamentalRevenueQuarterly, HaOhlcBar, Instrument
from src.data.fundamental_repository import (
    calendar_date_as_of,
    get_latest_quarterly_revenue_as_of,
    insert_revenue_quarterly_ignore_conflicts,
)
from src.data.ha_ohlc_repository import (
    get_ha_bar_at_or_before,
    get_last_finalized_ha_bar,
    get_partial_ha_bar,
    upsert_ha_bars,
)
from src.data.sec_edgar import RawRevenueFact, revenue_rows_for_database


@pytest.mark.asyncio
async def test_upsert_ha_bars(session):
    inst = Instrument(symbol="ZQTE", type="stock", currency="USD")
    session.add(inst)
    await session.flush()
    bar_time = datetime(2026, 1, 31, tzinfo=timezone.utc)
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    await upsert_ha_bars(
        session,
        [
            {
                "instrument_id": inst.id,
                "timeframe": "1mo",
                "bar_time": bar_time,
                "ha_open": 10.0,
                "ha_high": 11.0,
                "ha_low": 9.5,
                "ha_close": 10.5,
                "is_final": True,
                "source": "test",
                "computed_at": now,
            }
        ],
    )
    row = (
        (
            await session.execute(
                select(HaOhlcBar).where(
                    HaOhlcBar.instrument_id == inst.id,
                    HaOhlcBar.timeframe == "1mo",
                )
            )
        )
        .scalars()
        .one()
    )
    assert float(row.ha_close) == pytest.approx(10.5)

    await upsert_ha_bars(
        session,
        [
            {
                "instrument_id": inst.id,
                "timeframe": "1mo",
                "bar_time": bar_time,
                "ha_open": 10.0,
                "ha_high": 12.0,
                "ha_low": 9.0,
                "ha_close": 11.0,
                "is_final": False,
                "source": "test",
                "computed_at": now,
            }
        ],
    )
    row2 = (
        (
            await session.execute(
                select(HaOhlcBar).where(
                    HaOhlcBar.instrument_id == inst.id,
                    HaOhlcBar.timeframe == "1mo",
                )
            )
        )
        .scalars()
        .one()
    )
    assert float(row2.ha_close) == pytest.approx(11.0)
    assert row2.is_final is False


@pytest.mark.asyncio
async def test_insert_fundamentals_ignore_conflict(session):
    inst = Instrument(symbol="ZQTF", type="stock", currency="USD")
    session.add(inst)
    await session.flush()
    r1 = RawRevenueFact(
        accession="0000812396-26-999901",
        period_end=date(2026, 3, 31),
        filing_date=date(2026, 5, 15),
        report_form="10-Q",
        fiscal_period="Q1",
        calendar_frame="CY2026Q1",
        revenue_usd=694_133_000,
    )
    r0 = RawRevenueFact(
        accession="0000812396-25-888801",
        period_end=date(2025, 3, 31),
        filing_date=date(2025, 5, 10),
        report_form="10-Q",
        fiscal_period="Q1",
        calendar_frame="CY2025Q1",
        revenue_usd=578_573_000,
    )
    rows = revenue_rows_for_database(inst.id, [r0, r1])
    await insert_revenue_quarterly_ignore_conflicts(session, rows)
    n = (
        await session.execute(
            select(FundamentalRevenueQuarterly).where(
                FundamentalRevenueQuarterly.instrument_id == inst.id
            )
        )
    ).scalars().all()
    assert len(n) >= 2
    q1_rows = [
        x
        for x in n
        if x.calendar_frame == "CY2026Q1" and x.period_end.isoformat().startswith("2026-03-31")
    ]
    assert q1_rows
    exp_yoy = (694_133_000 - 578_573_000) / 578_573_000
    assert float(q1_rows[0].revenue_yoy) == pytest.approx(exp_yoy)


@pytest.mark.asyncio
async def test_revenue_yoy_formula(session):
    inst = Instrument(symbol="ZQTG", type="stock", currency="USD")
    session.add(inst)
    await session.flush()
    r_old = RawRevenueFact(
        accession="a1",
        period_end=date(2025, 3, 31),
        filing_date=date(2025, 5, 1),
        report_form="10-Q",
        fiscal_period="Q1",
        calendar_frame="CY2025Q1",
        revenue_usd=100,
    )
    r_new = RawRevenueFact(
        accession="a2",
        period_end=date(2026, 3, 31),
        filing_date=date(2026, 5, 1),
        report_form="10-Q",
        fiscal_period="Q1",
        calendar_frame="CY2026Q1",
        revenue_usd=119,
    )
    rows = revenue_rows_for_database(inst.id, [r_old, r_new])
    assert rows[-1]["revenue_yoy"] == pytest.approx(0.19)


@pytest.mark.asyncio
async def test_ha_query_finalized_and_partial(session):
    inst = Instrument(symbol="ZQTH", type="stock", currency="USD")
    session.add(inst)
    await session.flush()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    t_old = datetime(2025, 12, 31, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 31, tzinfo=timezone.utc)
    await upsert_ha_bars(
        session,
        [
            {
                "instrument_id": inst.id,
                "timeframe": "1mo",
                "bar_time": t_old,
                "ha_open": 1,
                "ha_high": 2,
                "ha_low": 1,
                "ha_close": 2,
                "is_final": True,
                "source": "test",
                "computed_at": now,
            },
            {
                "instrument_id": inst.id,
                "timeframe": "1mo",
                "bar_time": t_new,
                "ha_open": 3,
                "ha_high": 4,
                "ha_low": 2,
                "ha_close": 3.5,
                "is_final": False,
                "source": "test",
                "computed_at": now,
            },
        ],
    )
    finalized = await get_last_finalized_ha_bar(session, inst.id, "1mo")
    assert finalized is not None
    assert finalized.is_final is True
    assert float(finalized.ha_close) == pytest.approx(2.0)

    partial = await get_partial_ha_bar(session, inst.id, "1mo")
    assert partial is not None
    assert partial.is_final is False
    assert float(partial.ha_open) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_ha_bar_at_or_before(session):
    inst = Instrument(symbol="ZQTI", type="stock", currency="USD")
    session.add(inst)
    await session.flush()
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    t1 = datetime(2025, 10, 31, tzinfo=timezone.utc)
    t2 = datetime(2025, 11, 30, tzinfo=timezone.utc)
    await upsert_ha_bars(
        session,
        [
            {
                "instrument_id": inst.id,
                "timeframe": "1mo",
                "bar_time": t1,
                "ha_open": 10,
                "ha_high": 10,
                "ha_low": 10,
                "ha_close": 10,
                "is_final": True,
                "source": "test",
                "computed_at": now,
            },
            {
                "instrument_id": inst.id,
                "timeframe": "1mo",
                "bar_time": t2,
                "ha_open": 11,
                "ha_high": 11,
                "ha_low": 11,
                "ha_close": 11,
                "is_final": True,
                "source": "test",
                "computed_at": now,
            },
        ],
    )
    row = await get_ha_bar_at_or_before(
        session, inst.id, "1mo", datetime(2025, 11, 15, tzinfo=timezone.utc)
    )
    assert row is not None
    assert row.bar_time == t1

    row2 = await get_ha_bar_at_or_before(
        session, inst.id, "1mo", datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert row2.bar_time == t2


@pytest.mark.asyncio
async def test_latest_quarterly_revenue_as_of_pit(session):
    inst = Instrument(symbol="ZQTJ", type="stock", currency="USD")
    session.add(inst)
    await session.flush()
    now_ct = datetime.now(timezone.utc)
    await insert_revenue_quarterly_ignore_conflicts(
        session,
        [
            {
                "instrument_id": inst.id,
                "accession": "p1",
                "period_end": date(2026, 3, 31),
                "filing_date": date(2026, 5, 20),
                "report_form": "10-Q",
                "fiscal_period": "Q1",
                "calendar_frame": "CY2026Q1",
                "revenue_usd": 100,
                "revenue_yoy": 0.1,
                "created_at": now_ct,
            },
            {
                "instrument_id": inst.id,
                "accession": "p0",
                "period_end": date(2025, 12, 31),
                "filing_date": date(2026, 3, 1),
                "report_form": "10-K",
                "fiscal_period": "FY",
                "calendar_frame": "CY2025",
                "revenue_usd": 500,
                "revenue_yoy": None,
                "created_at": now_ct,
            },
        ],
    )
    as_may = await get_latest_quarterly_revenue_as_of(session, inst.id, date(2026, 5, 1))
    assert as_may is not None
    assert as_may.accession == "p0"

    as_jun = await get_latest_quarterly_revenue_as_of(session, inst.id, date(2026, 6, 1))
    assert as_jun is not None
    assert as_jun.accession == "p1"


def test_calendar_date_as_of():
    d = calendar_date_as_of(datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc))
    assert isinstance(d, date)
