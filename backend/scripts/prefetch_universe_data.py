#!/usr/bin/env python3
"""Prefetch HA OHLC (month/week) and SEC quarterly revenue into the shared Postgres DB."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from sqlalchemy import select

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import Instrument
from src.data.prefetch_universe import default_daily_end_date_yesterday, prefetch_instrument_data

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def parse_optional_iso_date(raw: str | None, *, opt_name: str) -> date | None:
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip()
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise SystemExit(
            f"Invalid date for --{opt_name}: {raw!r} (expected YYYY-MM-DD)"
        ) from e


def symbols_from_lines(text: str) -> list[str]:
    """Split comma- and/or whitespace-separated tickers ; ``#`` starts until-EOL comments."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for tok in re.split(r"[\s,]+", line):
            u = tok.strip().upper()
            if u:
                out.append(u)
    return out


def load_symbols_from_file(path: Path | str) -> list[str]:
    p = Path(path)
    return symbols_from_lines(p.read_text(encoding="utf-8"))


async def gather_symbols(
    include_db: bool, file_symbols: list[str], cli_symbols: Iterable[str]
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    async with async_session_factory() as session:
        if include_db:
            rows = (
                (
                    await session.execute(
                        select(Instrument.symbol).order_by(Instrument.symbol)
                    )
                )
                .scalars()
                .all()
            )
            for sym in rows:
                u = str(sym).upper()
                if u not in seen:
                    seen.add(u)
                    out.append(u)
        for s in [*file_symbols, *cli_symbols]:
            u = str(s).strip().upper()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


async def run_main(args: argparse.Namespace) -> None:
    start_d_opt = parse_optional_iso_date(args.start, opt_name="start")
    end_d_opt = parse_optional_iso_date(args.end, opt_name="end")

    effective_end = end_d_opt or default_daily_end_date_yesterday()

    file_syms: list[str] = []
    if args.symbols_file:
        file_syms = load_symbols_from_file(args.symbols_file)

    symbols = await gather_symbols(args.include_db, file_syms, args.symbols)
    if not symbols:
        print("No symbols to process.")
        return
    logging.info(
        "%d symbol(s); daily [%s … %s] (calendar; end defaults yesterday if omitted)%s",
        len(symbols),
        start_d_opt or f"computed from ~{args.yfinance_years} yr before end",
        effective_end,
        "; daily_source=Yahoo (--yf-daily-only)" if args.yf_daily_only else "",
    )

    ha_month = not args.no_ha_month
    ha_week = not args.no_ha_week

    range_end_bound = end_d_opt or default_daily_end_date_yesterday()
    if start_d_opt is not None and start_d_opt > range_end_bound:
        raise SystemExit(
            f"--start {start_d_opt.isoformat()} cannot be after effective end "
            f"{range_end_bound.isoformat()}"
        )
    if args.yf_daily_only and args.no_yfinance_fill:
        raise SystemExit(
            "--yf-daily-only cannot be combined with --no-yfinance-fill "
            "(Yahoo OHLC pulls are disabled while force mode requires them)."
        )
    if args.yf_daily_only and ha_month is False and ha_week is False:
        raise SystemExit(
            "--yf-daily-only is meaningless without monthly or weekly HA "
            "(omit both --no-ha-month/--no-ha-week or drop --yf-daily-only)."
        )

    async with async_session_factory() as session:
        for sym in symbols:
            try:
                rep = await prefetch_instrument_data(
                    session,
                    sym,
                    instrument_type=args.type,
                    daily_start_day=start_d_opt,
                    daily_end_day=end_d_opt,
                    yfinance_history_years=args.yfinance_years,
                    ha_month=ha_month,
                    ha_week=ha_week,
                    fundamentals=not args.no_fundamentals,
                    fill_ohlc_if_missing=not args.no_yfinance_fill,
                    force_yfinance_daily=args.yf_daily_only,
                )
                await session.commit()
                logging.info("%s -> %s", sym, rep)
            except Exception as e:
                await session.rollback()
                logging.error("%s FAILED: %s", sym, e)


def parse_args() -> argparse.Namespace:
    yesterday = default_daily_end_date_yesterday()

    epilog = f"""\
Daily OHLC bar ``bar_time`` is stored at **midnight calendar session date** in ``{settings.timezone}``
(and serialized in API ISO with that offset). Intraday series remain anchored in UTC epochs.

  --end   When omitted: yesterday in app timezone ({settings.timezone}); e.g. {yesterday.isoformat()}
          below was generated when --help ran; each real prefetch run recomputes 'yesterday'.

  --start When omitted: end − (365 × --yfinance-years) calendar days before the effective --end.

Symbol list files: comma and/or ASCII whitespace separators; '#' starts a comment to EOL.
You may combine -S/--symbols-file, --symbols, and --include-db; order is DB list first (if enabled),
then file tokens, then CLI tickers — duplicates stripped. Long options need two dashes: --symbols-file
"""
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    p.add_argument(
        "--symbols",
        nargs="*",
        default=[],
        help="Tickers (optional if -S/--symbols-file or --include-db provides names)",
    )
    p.add_argument(
        "-S",
        "--symbols-file",
        metavar="PATH",
        dest="symbols_file",
        help="Lines of comma/space-separated tickers (# comments stripped)",
    )
    p.add_argument(
        "--include-db",
        action="store_true",
        help="Also prefetch every ticker already stored in instruments",
    )
    p.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        default=None,
        help="Inclusive first calendar date for daily (and HA) window",
    )
    p.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "Inclusive last calendar date for daily (and HA) window; "
            "default: yesterday in settings.timezone"
        ),
    )
    p.add_argument("--no-ha-month", action="store_true", help="Skip monthly HA")
    p.add_argument("--no-ha-week", action="store_true", help="Skip weekly HA")
    p.add_argument("--no-fundamentals", action="store_true", help="Skip SEC revenue")
    p.add_argument(
        "--no-yfinance-fill",
        action="store_true",
        help="Do not fetch missing OHLC from yfinance for sparse histories",
    )
    p.add_argument(
        "--yf-daily-only",
        action="store_true",
        dest="yf_daily_only",
        help=(
            "Always download the window's 1d bars from Yahoo; compute HA strictly from "
            "that Yahoo slice (still INSERT-missing-only into OHLC via save_bars; "
            "does not DELETE or UPDATE conflicting DB candles)"
        ),
    )
    p.add_argument(
        "--yfinance-years",
        type=int,
        default=12,
        metavar="N",
        help="When --start is omitted: look back N×365 calendar days before --end/end default",
    )
    p.add_argument(
        "--type",
        default="stock",
        help='Instrument ``type`` for new rows (default "stock")',
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
