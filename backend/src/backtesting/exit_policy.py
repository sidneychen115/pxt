from __future__ import annotations
from pydantic import BaseModel, model_validator, field_validator
from typing import Literal


class ExitPolicy(BaseModel):
    stop_loss_pct: float | None = None
    stop_loss_abs: float | None = None
    take_profit_pct: float | None = None
    take_profit_abs: float | None = None
    trailing_stop_pct: float | None = None
    trailing_activate_pct: float | None = None
    price_check_mode: Literal["close", "ohlc"] = "close"

    @field_validator("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "trailing_activate_pct", mode="after")
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

    @model_validator(mode="after")
    def _validate(self) -> ExitPolicy:
        if self.stop_loss_pct is not None and self.stop_loss_abs is not None:
            raise ValueError("Specify stop_loss_pct or stop_loss_abs, not both")
        if self.take_profit_pct is not None and self.take_profit_abs is not None:
            raise ValueError("Specify take_profit_pct or take_profit_abs, not both")
        if self.trailing_activate_pct is not None and self.trailing_stop_pct is None:
            raise ValueError("trailing_activate_pct requires trailing_stop_pct")
        return self
