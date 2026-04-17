from dataclasses import dataclass, field
import numpy as np
import pandas as pd


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    quantity: float
    entry_time: object
    entry_price: float
    exit_time: object = None
    exit_price: float = None
    exit_reason: str = "end_of_backtest"
    entry_signal: dict = field(default_factory=dict)
    exit_signal: dict = field(default_factory=dict)

    @property
    def pnl(self) -> float | None:
        if self.exit_price is None:
            return None
        multiplier = 1 if self.direction == "buy" else -1
        return multiplier * (self.exit_price - self.entry_price) * self.quantity

    @property
    def pnl_pct(self) -> float | None:
        if self.exit_price is None or self.entry_price == 0:
            return None
        multiplier = 1 if self.direction == "buy" else -1
        return multiplier * (self.exit_price - self.entry_price) / self.entry_price

    @property
    def hold_days(self) -> float | None:
        if self.exit_time is None:
            return None
        return (self.exit_time - self.entry_time).days


@dataclass
class BacktestMetrics:
    initial_capital: float
    final_equity: float
    trades: list[TradeRecord]
    equity_curve: pd.Series  # index=datetime, values=equity

    @property
    def total_return(self) -> float:
        return (self.final_equity - self.initial_capital) / self.initial_capital

    @property
    def annualized_return(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        days = (self.equity_curve.index[-1] - self.equity_curve.index[0]).days
        if days <= 0:
            return 0.0
        return (1 + self.total_return) ** (365 / days) - 1

    @property
    def sharpe_ratio(self) -> float:
        daily = self.equity_curve.pct_change().dropna()
        if daily.std() == 0:
            return 0.0
        return float(daily.mean() / daily.std() * np.sqrt(252))

    @property
    def max_drawdown(self) -> float:
        rolling_max = self.equity_curve.cummax()
        drawdown = (self.equity_curve - rolling_max) / rolling_max
        return float(drawdown.min())

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.pnl is not None]
        if not closed:
            return 0.0
        winners = sum(1 for t in closed if t.pnl > 0)
        return winners / len(closed)

    @property
    def profit_factor(self) -> float:
        closed = [t for t in self.trades if t.pnl is not None]
        gross_profit = sum(t.pnl for t in closed if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in closed if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def avg_hold_days(self) -> float:
        days = [t.hold_days for t in self.trades if t.hold_days is not None]
        return sum(days) / len(days) if days else 0.0
