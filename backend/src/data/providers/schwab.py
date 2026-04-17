import asyncio
from datetime import date, datetime, timezone
from functools import partial
import pandas as pd
import schwab
from schwab.client import Client
from src.core.config import settings
from src.data.providers.base import DataProvider

# Schwab frequency mappings
_FREQ_MAP = {
    "1m":  (Client.PriceHistory.FrequencyType.MINUTE, 1),
    "5m":  (Client.PriceHistory.FrequencyType.MINUTE, 5),
    "15m": (Client.PriceHistory.FrequencyType.MINUTE, 15),
    "30m": (Client.PriceHistory.FrequencyType.MINUTE, 30),
    "1h":  (Client.PriceHistory.FrequencyType.MINUTE, 60),
    "1d":  (Client.PriceHistory.FrequencyType.DAILY, 1),
    "1wk": (Client.PriceHistory.FrequencyType.WEEKLY, 1),
    "1mo": (Client.PriceHistory.FrequencyType.MONTHLY, 1),
}


class SchwabProvider(DataProvider):
    def __init__(self):
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = schwab.auth.client_from_token_file(
                settings.schwab_token_path,
                settings.schwab_api_key,
                settings.schwab_app_secret,
            )
        return self._client

    @staticmethod
    def authenticate() -> None:
        """One-time browser-based OAuth flow. Run once to create the token file."""
        schwab.auth.easy_client(
            settings.schwab_api_key,
            settings.schwab_app_secret,
            "https://127.0.0.1",
            settings.schwab_token_path,
        )

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        client = self._get_client()
        if timeframe not in _FREQ_MAP:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Valid: {list(_FREQ_MAP)}")
        freq_type, freq = _FREQ_MAP[timeframe]
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                client.get_price_history,
                symbol,
                frequency_type=freq_type,
                frequency=freq,
                start_datetime=start,
                end_datetime=end,
                need_extended_hours_data=False,
            ),
        )
        resp.raise_for_status()
        data = resp.json()
        candles = data.get("candles", [])
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "source"])
        df = pd.DataFrame(candles)
        df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
        df = df.set_index("datetime")
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df["vwap"] = None
        df["source"] = "schwab"
        return df

    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        client = self._get_client()
        loop = asyncio.get_running_loop()
        kwargs: dict = {"symbol": underlying}
        if expiry:
            kwargs["from_date"] = expiry
            kwargs["to_date"] = expiry
        resp = await loop.run_in_executor(None, partial(client.get_option_chain, **kwargs))
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for exp_date, strikes in {**data.get("callExpDateMap", {}), **data.get("putExpDateMap", {})}.items():
            exp = exp_date.split(":")[0]
            for strike_str, options in strikes.items():
                for opt in options:
                    rows.append({
                        "symbol": opt["symbol"],
                        "underlying": underlying,
                        "expiry": exp,
                        "strike": float(strike_str),
                        "option_type": "call" if opt["putCall"] == "CALL" else "put",
                        "bid": opt.get("bid"),
                        "ask": opt.get("ask"),
                        "last": opt.get("last"),
                        "volume": opt.get("totalVolume"),
                        "open_interest": opt.get("openInterest"),
                        "iv": opt.get("volatility"),
                        "delta": opt.get("delta"),
                        "gamma": opt.get("gamma"),
                        "theta": opt.get("theta"),
                        "vega": opt.get("vega"),
                        "source": "schwab",
                    })
        return pd.DataFrame(rows)

    async def get_latest_quote(self, symbol: str) -> dict:
        client = self._get_client()
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, partial(client.get_quote, symbol))
        resp.raise_for_status()
        data = resp.json().get(symbol, {})
        quote = data.get("quote", {})
        return {
            "symbol": symbol,
            "bid": quote.get("bidPrice"),
            "ask": quote.get("askPrice"),
            "last": quote.get("lastPrice"),
            "volume": quote.get("totalVolume"),
            "timestamp": (
                datetime.fromtimestamp(quote["quoteTime"] / 1000, tz=timezone.utc)
                if quote.get("quoteTime")
                else datetime.now(timezone.utc)
            ),
            "source": "schwab",
        }
