from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Literal
import pandas as pd


@dataclass
class PortfolioSnapshot:
    """Optional account state for backtest (live may pass None until broker integration).

    When set, ``cash`` is free cash before any new order in the current recall round;
    ``initial_capital`` is the run's starting equity.
    ``equity`` is mark-to-market account value (cash + open positions) when the backtest
    engine supplies it; use for volatility-based sizing. If None, strategies may fall back
    to ``cash``.
    """

    cash: float | None = None
    initial_capital: float | None = None
    equity: float | None = None


@dataclass
class TradeSignal:
    symbol: str
    direction: Literal["buy", "sell", "hold"]
    order_type: Literal["market", "limit", "stop"]
    quantity: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    confidence: float = 1.0          # 0.0–1.0
    reasoning: str = ""
    option_symbol: str | None = None  # set for options trades

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence!r}"
            )


class DataContext(ABC):
    """Interface for retrieving market data. Injected into strategies at runtime."""

    @abstractmethod
    async def get_bars(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        """Return DataFrame with columns [open, high, low, close, volume], DatetimeIndex."""

    @abstractmethod
    async def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> pd.DataFrame:
        """Return current option chain snapshot."""

    @abstractmethod
    async def get_latest_quote(self, symbol: str) -> dict:
        """Return latest quote dict."""

    async def log_step(self, message: str, *, level: str = "info", **details) -> None:
        """Optional live-run diagnostics; no-op unless a run logger is attached."""


class BaseStrategy(ABC):
    """
    All strategies inherit from this. Strategy code is identical for live and backtest;
    only the injected DataContext differs.
    """

    id: ClassVar[str]                          # must match strategies.id in DB
    name: ClassVar[str]
    description: ClassVar[str] = ""
    default_symbols: ClassVar[list[str]] = []
    default_timeframes: ClassVar[list[str]] = ["1d"]
    default_frequency: ClassVar[str] = "0 16 * * 1-5"   # cron: weekdays at 4pm CT
    default_parameters: ClassVar[dict] = {}

    @abstractmethod
    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        """Core strategy logic. Must not access any data beyond what ctx provides.

        In backtests, ``portfolio`` carries current cash and initial capital; the engine may
        call this multiple times per bar after each successful fill. When ``portfolio`` is
        None (e.g. live scheduling), strategies should use ``parameters`` or defaults.
        Within one call, multiple signals are tried in order; only the first executable
        fill triggers a recall with updated cash.
        """
