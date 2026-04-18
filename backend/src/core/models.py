from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    ARRAY, BigInteger, Boolean, CheckConstraint, Date, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP as TIMESTAMPTZ
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base

# Use timezone-aware TIMESTAMP for all datetime columns
TIMESTAMPTZ = TIMESTAMPTZ(timezone=True)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # stock, etf, crypto
    exchange: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    name: Mapped[str | None] = mapped_column(String(100))

    bars: Mapped[list["OhlcvBar"]] = relationship(back_populates="instrument")


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    underlying: Mapped[str] = mapped_column(String(20), ForeignKey("instruments.symbol"), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # call, put
    multiplier: Mapped[int] = mapped_column(Integer, default=100)

    __table_args__ = (
        Index("idx_options_underlying", "underlying", "expiry", "strike"),
    )


class OhlcvBar(Base):
    __tablename__ = "ohlcv_bars"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    bar_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="bars")

    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "bar_time"),
        Index("idx_bars", "instrument_id", "timeframe", "bar_time"),
    )


class OptionChainSnapshot(Base):
    __tablename__ = "option_chain_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    option_id: Mapped[int] = mapped_column(Integer, ForeignKey("options.id"), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    last: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column(Integer)
    open_interest: Mapped[int | None] = mapped_column(Integer)
    iv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("idx_chain", "option_id", "snapshot_time"),
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    run_frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    max_symbols: Mapped[int] = mapped_column(Integer, default=50)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


class TradeSignalRecord(Base):
    __tablename__ = "trade_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(50), ForeignKey("strategies.id"), nullable=False)
    stock_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("instruments.id"))
    option_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("options.id"))
    signal_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    reasoning: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "(stock_id IS NOT NULL AND option_id IS NULL) OR "
            "(stock_id IS NULL AND option_id IS NOT NULL)",
            name="ck_signal_instrument",
        ),
        Index("idx_signals_strategy", "strategy_id", "created_at"),
        Index("idx_signals_status", "status", "created_at"),
    )


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(50), ForeignKey("strategies.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="running")
    total_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    annualized_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    total_trades: Mapped[int | None] = mapped_column(Integer)
    avg_hold_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    llm_evaluation: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    progress_phase: Mapped[str | None] = mapped_column(String(32))
    progress_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    exit_policy: Mapped[dict | None] = mapped_column(JSONB)

    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="backtest")
    equity_curve: Mapped[list["BacktestEquityCurve"]] = relationship(back_populates="backtest")


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    backtest_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("backtests.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    hold_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    exit_reason: Mapped[str | None] = mapped_column(String(50))
    entry_signal: Mapped[dict | None] = mapped_column(JSONB)
    exit_signal: Mapped[dict | None] = mapped_column(JSONB)

    backtest: Mapped["Backtest"] = relationship(back_populates="trades")

    __table_args__ = (
        Index("idx_bt_trades", "backtest_id", "entry_time"),
    )


class BacktestEquityCurve(Base):
    __tablename__ = "backtest_equity_curve"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    backtest_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("backtests.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    backtest: Mapped["Backtest"] = relationship(back_populates="equity_curve")

    __table_args__ = (
        Index("idx_bt_equity", "backtest_id", "ts"),
    )


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_system_events", "event_type", "created_at"),
    )
