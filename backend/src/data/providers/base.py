from abc import ABC, abstractmethod
from datetime import date, datetime
import pandas as pd


class DataProvider(ABC):
    """
    All providers return DataFrames with these standardised columns:
    - bars: index=DatetimeIndex(UTC), columns=[open, high, low, close, volume, vwap, source]
    - option_chain: columns=[symbol, underlying, expiry, strike, option_type,
                              bid, ask, last, volume, open_interest,
                              iv, delta, gamma, theta, vega]
    - quote: dict with keys [symbol, bid, ask, last, volume, timestamp, source]
    """

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV bars. timeframe: '1m','5m','15m','30m','1h','4h','1d','1wk','1mo'"""

    @abstractmethod
    async def get_option_chain(
        self,
        underlying: str,
        expiry: date | None = None,
    ) -> pd.DataFrame:
        """Return current option chain snapshot."""

    @abstractmethod
    async def get_latest_quote(self, symbol: str) -> dict:
        """Return latest bid/ask/last quote."""


# Timeframe mapping: internal → yfinance interval strings
YFINANCE_INTERVALS: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",   # yfinance has no 4h; caller must resample
    "1d": "1d",
    "1wk": "1wk",
    "1mo": "1mo",
}
