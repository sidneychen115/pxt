"""Monthly + daily Heikin-Ashi gates without fundamentals (slot portfolio)."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.core.models import Instrument
from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.heikin_ashi import heikin_ashi, resample_to_monthly
from src.strategies.indicators import Indicators
from src.strategies.snapshot_bars import quote_mark_price

_MIN_DAILY_FOR_MONTHLY_HA = 1500


async def _instrument_ids(session: AsyncSession, symbols: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for sym in symbols:
        r = await session.execute(select(Instrument.id).where(Instrument.symbol == sym))
        i = r.scalar_one_or_none()
        if i is not None:
            out[sym] = i
    return out


def _daily_ha_cross_above_regular_sma(daily: pd.DataFrame, period: int) -> bool:
    """True on the last bar if HA close crosses above SMA(period) of regular closes."""
    if len(daily) < period + 1:
        return False
    hx = heikin_ashi(daily)
    if hx.empty or len(hx) < 2:
        return False
    sma = Indicators.sma(daily, period)
    ha_c = hx["ha_close"]
    prev_ha = float(ha_c.iloc[-2])
    curr_ha = float(ha_c.iloc[-1])
    prev_sma = sma.iloc[-2]
    curr_sma = sma.iloc[-1]
    if pd.isna(prev_sma) or pd.isna(curr_sma):
        return False
    return prev_ha < float(prev_sma) and curr_ha > float(curr_sma)


def _month_ha_close_open(daily_snap: pd.DataFrame) -> tuple[float, float] | None:
    monthly = resample_to_monthly(daily_snap)
    if monthly.empty or len(monthly) < 2:
        return None
    hx = heikin_ashi(monthly)
    if hx.empty:
        return None
    return float(hx["ha_close"].iloc[-1]), float(hx["ha_open"].iloc[-1])


class HaMonthDayHaCrossSmaSlotsStrategy(BaseStrategy):
    """Up to *portfolio_size* names; monthly exit; HA crosses SMA(period) without fundamentals."""

    # Historical id kept for DB / presets compatibility (filename uses generic ha_cross_sma).
    id = "ha_month_day_ma7_slots"
    name = "HA Month/Day + HA cross SMA (slots, no fundamentals)"
    description = (
        "Long when month HA close > month HA open (from monthly HA chained on visible daily bars) and "
        "daily HA close crosses above SMA(sma_period) of regular closes on the signal bar "
        "(previous bar: HA close strictly below SMA; current bar: HA close above SMA). "
        "sma_period defaults to 7 and is configurable in parameters. "
        "No SEC revenue YoY filtering or ranking; eligible buys preserve universe symbol order. "
        "Exits longs when month HA close drops below that month HA open. "
        "Concurrent long count is capped by portfolio_size (default 20)."
    )
    default_symbols = ["SPY"]
    default_timeframes = ["1d"]
    default_frequency = "0 14 * * mon-fri"
    default_parameters = {
        "timeframe": "1d",
        "portfolio_size": 20,
        "sma_period": 7,
        "backtest_fill_mode": "same_close",
        "snapshot_close_at_run": True,
        "account_equity": 100_000.0,
    }
    backtest_fill_mode = "same_close"

    def _params(self, parameters: dict) -> dict:
        return {**self.default_parameters, **parameters}

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        p = self._params(parameters)
        tf = str(p.get("timeframe", "1d"))
        sma_n = max(1, int(p.get("sma_period", 7)))
        daily_limit = max(_MIN_DAILY_FOR_MONTHLY_HA, sma_n + 30)
        cap_raw = int(p.get("portfolio_size", 20))
        cap = max(1, cap_raw)

        if not symbols:
            return []

        if portfolio is None or portfolio.equity is None or float(portfolio.equity) <= 0:
            await ctx.log_step(f"{self.id}: skip — need portfolio snapshot with equity")
            return []

        equity = float(portfolio.equity)
        raw_pos = dict(portfolio.positions or {})
        holdings = {k: float(v) for k, v in raw_pos.items() if float(v) > 0}

        marks: dict[str, float] = {}
        for sym in symbols:
            quote = await ctx.get_latest_quote(sym)
            px = quote_mark_price(quote)
            if px is None:
                bars1 = await ctx.get_bars(sym, tf, limit=2)
                if not bars1.empty:
                    px = float(bars1["close"].iloc[-1])
            if px is not None and px > 0:
                marks[sym] = px

        async with async_session_factory() as session:
            id_map = await _instrument_ids(session, symbols)

            eligible_ordered: list[str] = []

            for sym in symbols:
                tid = id_map.get(sym)
                if tid is None:
                    continue

                daily = await ctx.get_bars(sym, tf, limit=daily_limit)
                if daily.empty or len(daily) < sma_n + 1:
                    continue

                mc_mo = _month_ha_close_open(daily)
                if mc_mo is None:
                    continue
                month_close, month_open = mc_mo

                tech_buy = month_close > month_open and _daily_ha_cross_above_regular_sma(
                    daily, sma_n
                )

                if tech_buy:
                    eligible_ordered.append(sym)

            signals: list[TradeSignal] = []

            sell_syms = [s for s in list(holdings.keys()) if s in id_map and s in symbols]

            for sym in list(sell_syms):
                daily = await ctx.get_bars(sym, tf, limit=daily_limit)
                tid = id_map.get(sym)
                if tid is None or daily.empty:
                    continue
                mc_mo = _month_ha_close_open(daily)
                if mc_mo is None:
                    continue
                month_close, month_open = mc_mo
                if month_close < month_open:
                    qty = holdings.get(sym)
                    if qty and qty > 0:
                        signals.append(
                            TradeSignal(
                                symbol=sym,
                                direction="sell",
                                order_type="market",
                                quantity=float(qty),
                                reasoning=(
                                    "month_ha_close_below_open "
                                    f"m_close={month_close:.4f}<m_open={month_open:.4f}"
                                ),
                                confidence=1.0,
                            )
                        )

            planned_holdings = {
                k: v for k, v in holdings.items() if k not in {s.symbol for s in signals if s.direction == "sell"}
            }

            sell_proceeds = 0.0
            has_sells = False
            for sig in signals:
                if sig.direction == "sell":
                    has_sells = True
                    sell_proceeds += float(sig.quantity or 0) * marks.get(sig.symbol, 0.0)

            slots_free = max(0, cap - len(planned_holdings))
            if slots_free <= 0:
                return signals

            already = set(planned_holdings.keys())
            buy_list: list[str] = []
            for sym in eligible_ordered:
                if sym in already:
                    continue
                buy_list.append(sym)
                if len(buy_list) >= slots_free:
                    break

            if not buy_list:
                return signals

            held_mv_kept = 0.0
            for sym, qty in planned_holdings.items():
                px = marks.get(sym, 0.0)
                if px > 0:
                    held_mv_kept += qty * px
            cash_proxy = max(0.0, equity - held_mv_kept)

            if has_sells and sell_proceeds > 1.0:
                alloc_each = sell_proceeds / len(buy_list)
            elif cash_proxy > 1.0:
                alloc_each = cash_proxy / len(buy_list)
            else:
                await ctx.log_step(
                    f"{self.id}: skip buys — no deployable cash (proxy)",
                    cash_proxy=cash_proxy,
                    sell_proceeds=sell_proceeds,
                )
                return signals

            for sym in buy_list:
                px = marks.get(sym)
                if px is None or px <= 0:
                    continue
                qty = max(0.0, alloc_each / px)
                if qty <= 0:
                    continue
                signals.append(
                    TradeSignal(
                        symbol=sym,
                        direction="buy",
                        order_type="market",
                        quantity=qty,
                        reasoning=(
                            f"month_ha_bull ha_cross_sma{sma_n} slot alloc~{alloc_each:.0f} px={px:.4f}"
                        ),
                        confidence=1.0,
                    )
                )

        ordered = [s for s in signals if s.direction == "sell"] + [
            s for s in signals if s.direction == "buy"
        ]
        return ordered
