from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ExitPolicy(BaseModel):
    """Exit rules for the backtest engine.

    **Entry vs exit (bar semantics)** — can be set independently:

    - ``entry_price_check_mode``: Intended for **opening** logic. The engine still fills entries at the
      next bar's open when the strategy emits a signal; strategies typically use **close** prices for
      signal generation. This field is stored for API/UI consistency and optional strategy use.
    - ``exit_price_check_mode``: Controls **stop / take-profit / trailing** checks on open positions:
      ``close`` = compare to bar **close** (exit often fills next bar open); ``ohlc`` = use **low/high**
      intrabar vs levels (see engine).

    Legacy JSON may contain only ``price_check_mode``; it is applied to ``exit_price_check_mode``
    when ``exit_price_check_mode`` is absent.
    """

    model_config = ConfigDict(extra="ignore")

    stop_loss_pct: float | None = None
    stop_loss_abs: float | None = None
    take_profit_pct: float | None = None
    take_profit_abs: float | None = None
    trailing_stop_pct: float | None = None
    trailing_activate_pct: float | None = None
    #: How **entries** are reasoned about (strategy-side convention); default close.
    entry_price_check_mode: Literal["close", "ohlc"] = "close"
    #: How **exits** (SL / TP / trailing) are evaluated on each bar. Default ohlc = use low/high.
    exit_price_check_mode: Literal["close", "ohlc"] = "ohlc"
    # When True, strategy SELL signals are ignored; exits only via exit rules or end of backtest.
    disable_sell_signal: bool = False

    @field_validator(
        "stop_loss_pct",
        "take_profit_pct",
        "trailing_stop_pct",
        "trailing_activate_pct",
        mode="after",
    )
    @classmethod
    def _positive_pct(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("percentage fields must be > 0")
        return v

    @field_validator("stop_loss_abs", "take_profit_abs", mode="after")
    @classmethod
    def _positive_abs(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("absolute fields must be > 0")
        return v

    @model_validator(mode="before")
    @classmethod
    def _legacy_price_check_mode(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        # Old API sent a single price_check_mode — map to exit only.
        if out.get("exit_price_check_mode") is None and out.get("price_check_mode") is not None:
            out["exit_price_check_mode"] = out["price_check_mode"]
        return out

    @model_validator(mode="after")
    def _validate(self) -> ExitPolicy:
        if self.stop_loss_pct is not None and self.stop_loss_abs is not None:
            raise ValueError("Specify stop_loss_pct or stop_loss_abs, not both")
        if self.take_profit_pct is not None and self.take_profit_abs is not None:
            raise ValueError("Specify take_profit_pct or take_profit_abs, not both")
        if self.trailing_activate_pct is not None and self.trailing_stop_pct is None:
            raise ValueError("trailing_activate_pct requires trailing_stop_pct")
        return self
