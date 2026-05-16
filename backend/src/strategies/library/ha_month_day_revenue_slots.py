"""Monthly + daily Heikin-Ashi gates with SEC revenue YoY ranking (slot portfolio)."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.core.models import Instrument
from src.data.fundamental_repository import get_latest_quarterly_revenue_as_of
from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.heikin_ashi import heikin_ashi, resample_to_monthly
from src.strategies.indicators import Indicators
from src.strategies.snapshot_bars import quote_mark_price

# Monthly HA needs a deep enough daily chain; short tails distort HA vs operational pipelines.
_MIN_DAILY_FOR_MONTHLY_HA = 1500


async def _instrument_ids(session: AsyncSession, symbols: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for sym in symbols:
        r = await session.execute(select(Instrument.id).where(Instrument.symbol == sym))
        i = r.scalar_one_or_none()
        if i is not None:
            out[sym] = i
    return out


def _daily_ha_close_last(daily: pd.DataFrame) -> float | None:
    if daily.empty:
        return None
    hx = heikin_ashi(daily)
    if hx.empty:
        return None
    return float(hx["ha_close"].iloc[-1])


def _regular_sma_last(daily: pd.DataFrame, period: int) -> float | None:
    if len(daily) < period:
        return None
    s = Indicators.sma(daily, period)
    v = s.iloc[-1]
    if pd.isna(v):
        return None
    return float(v)


def _month_ha_close_open(daily_snap: pd.DataFrame) -> tuple[float, float] | None:
    """(month_ha_close, month_ha_open) for the in-progress calendar month using only visible daily bars.

    Chains HA from the start of ``daily_snap`` so simulation matches causal history (live DB anchors are not used).

    Returns ``None`` unless there is at least one **prior** calendar month row before the current month bucket.
    Otherwise the HA series has only one bar and ``ha_open`` degenerates to ``(month_O + partial_month_C)/2``,
    which is not a stable monthly regime gate — callers should skip trading for that symbol/month.
    """
    monthly = resample_to_monthly(daily_snap)
    if monthly.empty or len(monthly) < 2:
        return None
    hx = heikin_ashi(monthly)
    if hx.empty:
        return None
    return float(hx["ha_close"].iloc[-1]), float(hx["ha_open"].iloc[-1])


class HaMonthDayRevenueSlotsStrategy(BaseStrategy):
    """Up to *portfolio_size* names (parameter); monthly exit only; buys ranked by revenue YoY."""

    id = "ha_month_day_revenue_slots"
    name = "HA Month/Day + SEC Revenue YoY (ranked slots)"
    description = (
        "Long when month HA close > month HA open (from monthly HA chained on visible daily bars) and "
        "day HA close > SMA(7) on regular closes; exits longs when month HA close drops "
        "below that open. In backtests, the server preloads daily data before your start date "
        "(default 24 months via parameters.backtest_warmup_months) so monthly HA matches a longer "
        "history chain; simulation and metrics still start on your chosen start_date. "
        "Monthly HA requires at least one completed prior calendar month in visible bars "
        "(no trades on the first month-only tail). Fills empty slots from the universe sorted by "
        "latest SEC Revenues YoY "
        "(point-in-time by filing_date). Concurrent long count is capped by portfolio_size "
        "(default 20, configurable)."
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
        sma_n = int(p.get("sma_period", 7))
        daily_limit = max(_MIN_DAILY_FOR_MONTHLY_HA, sma_n + 30)
        cap_raw = int(p.get("portfolio_size", 20))
        cap = max(1, cap_raw)

        if not symbols:
            return []

        if portfolio is None or portfolio.equity is None or float(portfolio.equity) <= 0:
            await ctx.log_step(
                f"{self.id}: skip — need portfolio snapshot with equity"
            )
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

        as_of_dt = await ctx.decision_time()

        async with async_session_factory() as session:
            id_map = await _instrument_ids(session, symbols)

            eligible_ranked: list[tuple[str, float]] = []

            for sym in symbols:
                tid = id_map.get(sym)
                if tid is None:
                    continue

                daily = await ctx.get_bars(sym, tf, limit=daily_limit)
                if daily.empty or len(daily) < sma_n:
                    continue

                mc_mo = _month_ha_close_open(daily)
                if mc_mo is None:
                    continue
                month_close, month_open = mc_mo

                sma_v = _regular_sma_last(daily, sma_n)
                if sma_v is None:
                    continue
                dh_close = _daily_ha_close_last(daily)
                if dh_close is None:
                    continue

                tech_buy = month_close > month_open and dh_close > sma_v

                row = await get_latest_quarterly_revenue_as_of(session, tid, as_of_dt)
                if row is None or row.revenue_yoy is None:
                    continue

                yoy = float(row.revenue_yoy)

                if tech_buy:
                    eligible_ranked.append((sym, yoy))

            eligible_ranked.sort(key=lambda x: x[1], reverse=True)
            ranked_symbols = [s for s, _ in eligible_ranked]

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
            for sym in ranked_symbols:
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
                yoy_ex = next((y for s, y in eligible_ranked if s == sym), 0.0)
                signals.append(
                    TradeSignal(
                        symbol=sym,
                        direction="buy",
                        order_type="market",
                        quantity=qty,
                        reasoning=f"rank yoy fill slot alloc~{alloc_each:.0f} px={px:.4f}",
                        confidence=min(1.0, max(0.5, 0.5 + min(yoy_ex, 2.0) * 0.15)),
                    )
                )

        ordered = [s for s in signals if s.direction == "sell"] + [
            s for s in signals if s.direction == "buy"
        ]
        return ordered
