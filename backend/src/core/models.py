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
    sec_cik: Mapped[str | None] = mapped_column(String(10), nullable=True)

    bars: Mapped[list["OhlcvBar"]] = relationship(back_populates="instrument")


class HaOhlcBar(Base):
    """Heikin-Ashi OHLC for aggregated periods (calendar month/week; daily finalized optional).

    Partial in-progress periods use ``is_final=False`` with stable ``ha_open``; finalized rows use
    ``is_final=True``. ``bar_time`` is period end (UTC).
    """

    __tablename__ = "ha_ohlc_bars"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    timeframe: Mapped[str] = mapped_column(String(6), nullable=False)
    bar_time: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    ha_open: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    ha_high: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    ha_low: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    ha_close: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="computed")
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "bar_time",
            name="uq_ha_ohlc_instrument_tf_bar_time",
        ),
        Index("idx_ha_ohlc_lookup", "instrument_id", "timeframe", "bar_time"),
        Index("idx_ha_ohlc_partial", "instrument_id", "timeframe", "is_final"),
    )


class FundamentalRevenueQuarterly(Base):
    """SEC XBRL Revenue (``us-gaap:Revenues``) facts with optional YoY."""

    __tablename__ = "fundamental_revenue_quarterly"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    accession: Mapped[str] = mapped_column(String(32), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_form: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(8), nullable=True)
    calendar_frame: Mapped[str | None] = mapped_column(String(12), nullable=True)
    revenue_usd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revenue_yoy: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    __table_args__ = (
        UniqueConstraint("instrument_id", "accession", name="uq_fund_rev_inst_accn"),
        Index("idx_fund_rev_inst_filed", "instrument_id", "filing_date"),
        Index("idx_fund_rev_inst_frame", "instrument_id", "calendar_frame"),
    )


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


class HaMonthOpenCache(Base):
    """Cached monthly Heikin-Ashi open for a calendar month (stable within the month)."""

    __tablename__ = "ha_month_open_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    calendar_year: Mapped[int] = mapped_column(Integer, nullable=False)
    calendar_month: Mapped[int] = mapped_column(Integer, nullable=False)
    ha_open: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "calendar_year",
            "calendar_month",
            name="uq_ha_month_open_instrument_ym",
        ),
        Index("idx_ha_month_open_lookup", "instrument_id", "calendar_year", "calendar_month"),
    )


class HaMonthAnchorCache(Base):
    """HA open/close of the last completed calendar month — seeds current month HA open."""

    __tablename__ = "ha_month_anchor_cache"

    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    calendar_year: Mapped[int] = mapped_column(Integer, nullable=False)
    calendar_month: Mapped[int] = mapped_column(Integer, nullable=False)
    ha_open: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    ha_close: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)


class HaWeekAnchorCache(Base):
    """HA open/close of the last completed week — seeds incremental in-progress week HA."""

    __tablename__ = "ha_week_anchor_cache"

    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    week_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    ha_open: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    ha_close: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)


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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


class UserStrategy(Base):
    __tablename__ = "user_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    run_frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_symbols: Mapped[int] = mapped_column(Integer, default=50)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "strategy_id", name="uq_user_strategy"),)


class UserPosition(Base):
    __tablename__ = "user_positions"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


class PositionFill(Base):
    __tablename__ = "position_fills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id"), nullable=False
    )
    signal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("trade_signals.id", ondelete="SET NULL")
    )
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)


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
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
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
        Index("idx_signals_user", "user_id", "created_at"),
    )


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
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
    benchmark_total_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    alpha_vs_benchmark: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    llm_evaluation: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    progress_phase: Mapped[str | None] = mapped_column(String(32))
    progress_message: Mapped[str | None] = mapped_column(Text)
    progress_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    exit_policy: Mapped[dict | None] = mapped_column(JSONB)

    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="backtest")
    equity_curve: Mapped[list["BacktestEquityCurve"]] = relationship(back_populates="backtest")

    __table_args__ = (Index("idx_backtests_created_at", "created_at"),)


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


class BacktestConfigPreset(Base):
    """Saved backtest form configuration (server-side; replaces browser localStorage)."""

    __tablename__ = "backtest_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, default=datetime.utcnow)
    strategy_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("strategies.id"), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbols: Mapped[str] = mapped_column(Text, nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    exit_policy_form: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (Index("idx_backtest_presets_created_at", "created_at"),)


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
