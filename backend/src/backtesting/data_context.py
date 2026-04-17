from datetime import date, datetime
import pandas as pd
from src.strategies.base import DataContext


class BacktestDataContext(DataContext):
    """
    Injects pre-loaded historical data sliced at current_time.
    Prevents look-ahead: strategy only sees bars with bar_time < current_time.
    Orders fill at next bar's open price (not current close).
    """

    def __init__(
        self,
        data: dict[str, dict[str, pd.DataFrame]],  # {symbol: {timeframe: df}}
        current_time: datetime,
    ):
        self._data = data
        self._current_time = current_time

    def advance(self, new_time: datetime) -> None:
        self._current_time = new_time

    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        df = self._data.get(symbol, {}).get(timeframe)
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        past = df[df.index < self._current_time]
        return past.tail(limit)

    async def get_option_chain(self, underlying, expiry=None) -> pd.DataFrame:
        return pd.DataFrame()  # Historical option chain not available from free sources

    async def get_latest_quote(self, symbol: str) -> dict:
        df = await self.get_bars(symbol, "1d", limit=1)
        if df.empty:
            return {}
        return {"symbol": symbol, "last": float(df["close"].iloc[-1])}
