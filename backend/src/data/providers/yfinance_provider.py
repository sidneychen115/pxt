import asyncio
from datetime import date, datetime, timezone
from functools import partial
import pandas as pd
import yfinance as yf
from src.data.providers.base import DataProvider, YFINANCE_INTERVALS


class YFinanceProvider(DataProvider):
    """
    Runs yfinance (synchronous) in a thread pool executor.
    Limits: 1m data ≤7 days, 5m-30m ≤60 days, 1h ≤730 days, 1d+ unlimited.
    """

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        interval = YFINANCE_INTERVALS.get(timeframe, "1d")
        loop = asyncio.get_running_loop()
        intraday_intervals = {"1m", "5m", "15m", "30m", "1h"}
        fmt = "%Y-%m-%dT%H:%M:%S" if interval in intraday_intervals else "%Y-%m-%d"
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
