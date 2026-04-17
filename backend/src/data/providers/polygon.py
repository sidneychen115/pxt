from datetime import date, datetime
import pandas as pd
from src.data.providers.base import DataProvider


class PolygonProvider(DataProvider):
    """Paid provider stub. Implement when Polygon API key is available."""

    async def get_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        raise NotImplementedError("Polygon provider not yet implemented")

    async def get_option_chain(self, underlying: str, expiry: date | None = None) -> pd.DataFrame:
        raise NotImplementedError("Polygon provider not yet implemented")

    async def get_latest_quote(self, symbol: str) -> dict:
        raise NotImplementedError("Polygon provider not yet implemented")
