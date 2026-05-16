from datetime import date, datetime, timezone
import pandas as pd
from src.strategies.base import DataContext


class BacktestDataContext(DataContext):
    """
    Injects pre-loaded historical data sliced at current_time.
    By default prevents look-ahead: strategy only sees bars with bar_time < current_time.
    With ``inclusive_end=True`` (same-bar-close fill mode), bars with index <= current_time
    are visible so the signal can use the decision bar's OHLC.
    """

    def __init__(
        self,
        data: dict[str, dict[str, pd.DataFrame]],  # {symbol: {timeframe: df}}
        current_time: datetime,
        inclusive_end: bool = False,
    ):
        self._data = data
        self._current_time = current_time
        self._inclusive_end = inclusive_end

    def advance(self, new_time: datetime) -> None:
        self._current_time = new_time

    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        df = self._data.get(symbol, {}).get(timeframe)
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if self._inclusive_end:
            past = df[df.index <= self._current_time]
        else:
            past = df[df.index < self._current_time]
        return past.tail(limit)

    async def get_option_chain(self, underlying, expiry=None) -> pd.DataFrame:
        return pd.DataFrame()  # Historical option chain not available from free sources

    async def get_latest_quote(self, symbol: str) -> dict:
        df = await self.get_bars(symbol, "1d", limit=1)
        if df.empty:
            return {}
        return {"symbol": symbol, "last": float(df["close"].iloc[-1])}

    async def decision_time(self) -> datetime:
        t = self._current_time
        if t.tzinfo is None:
            return t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
