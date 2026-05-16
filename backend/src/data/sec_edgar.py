"""SEC EDGAR lightweight client (tickers→CIK, company facts, Revenues XBRL)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache

from src.core.config import settings

_TICKERS_JSON = "https://www.sec.gov/files/company_tickers.json"


def _request_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": settings.sec_edgar_user_agent})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


@lru_cache(maxsize=1)
def _ticker_to_cik_map() -> dict[str, str]:
    """Uppercase ticker → zero-padded 10-digit CIK string."""
    raw = _request_json(_TICKERS_JSON)
    out: dict[str, str] = {}
    for entry in raw.values():
        t = str(entry.get("ticker", "")).upper()
        cik = str(entry.get("cik_str", "")).zfill(10)
        if t and cik:
            out[t] = cik
    return out


def resolve_cik_for_ticker(ticker: str) -> str | None:
    """Return CIK ``000XXXXXXX`` or None if unknown (non-US listings)."""
    return _ticker_to_cik_map().get(ticker.strip().upper())


def fetch_company_facts(cik_no_prefix: str) -> dict | None:
    """``cik_no_prefix`` digits only or 10-digit with leading zeros."""
    cik = cik_no_prefix.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        return _request_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


_CY_Q_RE = re.compile(r"^CY(20\d{2})Q([1-4])$")


def is_calendar_quarter_frame(frame: str | None) -> bool:
    return bool(frame and _CY_Q_RE.match(frame))


def prior_year_calendar_frame(frame: str) -> str | None:
    m = _CY_Q_RE.match(frame)
    if not m:
        return None
    return f"CY{int(m.group(1)) - 1}Q{m.group(2)}"


@dataclass(frozen=True)
class RawRevenueFact:
    accession: str
    period_end: date
    filing_date: date
    report_form: str
    fiscal_period: str | None
    calendar_frame: str | None
    revenue_usd: int


def parse_revenues_quarterly_usd(facts_blob: dict) -> list[RawRevenueFact]:
    """Extract ``us-gaap:Revenues`` USD quarterly facts with XBRL calendar ``CYnnnnQq``."""
    out: list[RawRevenueFact] = []
    try:
        usgaap = facts_blob["facts"]["us-gaap"]
    except KeyError:
        return out
    revenues = usgaap.get("Revenues")
    if not revenues:
        return out
    units = revenues.get("units") or {}
    items = units.get("USD") or []
    for x in items:
        form = x.get("form") or ""
        if form not in ("10-Q", "10-K"):
            continue
        frame = x.get("frame")
        if not is_calendar_quarter_frame(frame):
            continue
        accn = x.get("accn")
        end = x.get("end")
        filed = x.get("filed")
        val = x.get("val")
        if not accn or not end or not filed or val is None:
            continue
        out.append(
            RawRevenueFact(
                accession=str(accn),
                period_end=date.fromisoformat(str(end)),
                filing_date=date.fromisoformat(str(filed)),
                report_form=form,
                fiscal_period=x.get("fp"),
                calendar_frame=frame if isinstance(frame, str) else None,
                revenue_usd=int(round(float(val))),
            )
        )
    return out


def revenue_rows_for_database(
    instrument_id: int,
    facts: list[RawRevenueFact],
) -> list[dict]:
    """Chronological PIT-lite YoY vs prior-calendar-quarter frame latest known before filing."""
    if not facts:
        return []

    chronological = sorted(facts, key=lambda r: (r.filing_date, r.accession))
    latest_by_frame: dict[str, tuple[int, date]] = {}
    now_iso = datetime.now(timezone.utc)
    rows: list[dict] = []

    for r in chronological:
        frame = r.calendar_frame
        assert frame is not None
        py = prior_year_calendar_frame(frame)
        prev_snap = latest_by_frame.get(py) if py else None
        revenue_yoy = None
        if prev_snap is not None and prev_snap[0] != 0:
            revenue_yoy = round((r.revenue_usd - prev_snap[0]) / prev_snap[0], 10)

        rows.append(
            {
                "instrument_id": instrument_id,
                "accession": r.accession,
                "period_end": r.period_end,
                "filing_date": r.filing_date,
                "report_form": r.report_form,
                "fiscal_period": r.fiscal_period,
                "calendar_frame": r.calendar_frame,
                "revenue_usd": r.revenue_usd,
                "revenue_yoy": revenue_yoy,
                "created_at": now_iso,
            }
        )

        cur_snap = latest_by_frame.get(frame)
        if cur_snap is None or r.filing_date >= cur_snap[1]:
            latest_by_frame[frame] = (r.revenue_usd, r.filing_date)

    return rows
