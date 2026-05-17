import asyncio
from datetime import date, datetime, timedelta, timezone
from functools import partial
import pandas as pd
import yfinance as yf
from src.backtesting.intraday_limits import (
    YFINANCE_SHORT_INTRADAY_CHUNK_DAYS,
    intraday_yfinance_usable_earliest_date,
)
from src.core.app_timezone import app_zone, daily_bar_timestamp_for_session_date, session_date_from_utc_naive_daily_label
from src.data.providers.base import DataProvider, YFINANCE_INTERVALS

# Bars from Yahoo keyed by calendar day / week-end / month-end — stored at Chicago session midnight.
_DAILY_LIKE_TF = frozenset({"1d", "1wk", "1mo"})
_SHORT_INTRADAY_TF = frozenset({"1m", "5m", "15m", "30m"})


def iter_yfinance_intraday_chunks(
    start: date,
    end: date,
    *,
    chunk_days: int = YFINANCE_SHORT_INTRADAY_CHUNK_DAYS,
) -> list[tuple[date, date]]:
    """Split [start, end) into calendar chunks for Yahoo short-intraday downloads."""
    if start >= end:
        return []
    out: list[tuple[date, date]] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        out.append((cur, nxt))
        cur = nxt
    return out


class YFinanceProvider(DataProvider):
    """
    Runs yfinance (synchronous) in a thread pool executor.
    Limits: 1m data ≤7 days, 5m-30m ≤60 days, 1h ≤730 days, 1d+ unlimited.
  Short intraday ranges are downloaded in multi-day chunks (Yahoo rejects long spans).
    """

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        if timeframe in _SHORT_INTRADAY_TF:
            return await self._get_short_intraday_bars(symbol, timeframe, start, end)
        return await self._download_bars(symbol, timeframe, start, end)

    async def _get_short_intraday_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        z = start.tzinfo or app_zone()
        as_of = datetime.now(z).date()
        usable = intraday_yfinance_usable_earliest_date(timeframe=timeframe, as_of=as_of)
        start_d = max(start.date(), usable)
        end_d = end.date()
        if start_d >= end_d:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "source"])

        chunks = iter_yfinance_intraday_chunks(start_d, end_d)
        if len(chunks) <= 1:
            chunk_start = datetime.combine(start_d, datetime.min.time(), tzinfo=z)
            return await self._download_bars(symbol, timeframe, chunk_start, end)

        parts: list[pd.DataFrame] = []
        for c0, c1 in chunks:
            chunk_start = datetime.combine(c0, datetime.min.time(), tzinfo=z)
            chunk_end = datetime.combine(c1, datetime.min.time(), tzinfo=z)
            df = await self._download_bars(symbol, timeframe, chunk_start, chunk_end)
            if not df.empty:
                parts.append(df)
        if not parts:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "source"])
        out = pd.concat(parts).sort_index()
        return out[~out.index.duplicated(keep="last")]

    async def _download_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        interval = YFINANCE_INTERVALS.get(timeframe, "1d")
        loop = asyncio.get_running_loop()
        # yfinance.download expects YYYY-MM-DD for start/end (all intervals). ISO datetimes with
        # "T" or times can raise "unconverted data remains" and return empty intraday data.
        fmt = "%Y-%m-%d"
        df = await loop.run_in_executor(
            None,
            partial(
                yf.download,
                tickers=symbol,
                start=start.strftime(fmt),
                end=end.strftime(fmt),
                interval=interval,
                auto_adjust=True,
                progress=False,
            ),
        )
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "source"])
        # yfinance returns MultiIndex columns when downloading single ticker with auto_adjust
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"adj close": "close"})
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df["vwap"] = None
        df["source"] = "yfinance"
        df.index = pd.to_datetime(df.index, utc=True)
        if timeframe in _DAILY_LIKE_TF:
            sess_dates = [
                session_date_from_utc_naive_daily_label(ts.to_pydatetime()) for ts in df.index
            ]
            df.index = pd.DatetimeIndex(
                [pd.Timestamp(daily_bar_timestamp_for_session_date(sd)) for sd in sess_dates]
            )
        return df.dropna(subset=["open", "close"])

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, underlying)
        expiry_str = expiry.strftime("%Y-%m-%d") if expiry else None
        if expiry_str:
            opt = await loop.run_in_executor(None, ticker.option_chain, expiry_str)
        else:
            opt = await loop.run_in_executor(None, ticker.option_chain)
        calls = opt.calls.copy()
        calls["option_type"] = "call"
        puts = opt.puts.copy()
        puts["option_type"] = "put"
        df = pd.concat([calls, puts], ignore_index=True)
        df["underlying"] = underlying
        df["source"] = "yfinance"
        return df.rename(columns={
            "contractSymbol": "symbol",
            "lastPrice": "last",
            "impliedVolatility": "iv",
            "openInterest": "open_interest",
        })

    async def get_latest_quote(self, symbol: str) -> dict:
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
        info = await loop.run_in_executor(None, lambda: ticker.fast_info)
        bid = getattr(info, "bid", None)
        ask = getattr(info, "ask", None)
        if bid is None or ask is None:
            full_info = await loop.run_in_executor(None, lambda: ticker.info)
            if bid is None:
                bid = full_info.get("bid")
            if ask is None:
                ask = full_info.get("ask")
        return {
            "symbol": symbol,
            "last": getattr(info, "last_price", None),
            "bid": bid,
            "ask": ask,
            "volume": getattr(info, "last_volume", None),
            "timestamp": datetime.now(timezone.utc),
            "source": "yfinance",
        }
