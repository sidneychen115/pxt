"""MVP Chan-style signals on regular daily OHLC: 分型 + 笔 + 简化中枢 (optional SMA)."""

from __future__ import annotations

from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.chan_structure import mvp_chan_signal_at_last_bar


class ChanBiFractalMvpStrategy(BaseStrategy):
    """分型 + 笔 + 中枢；买默认须站上 ZG；卖默认仅需顶分型+向上笔（可选再加破 ZD）。"""

    id = "chan_bi_fractal_mvp"
    name = "Chan MVP: 分型 + 笔 + 中枢 (daily OHLC)"
    description = (
        "Regular daily bars: inclusion merge, 分型, 笔 (min_fractal_sep), 最近 N 笔价位区间的重叠带作为简化中枢 "
        "[ZD,ZG]。买：确认底分型 + 向下笔止于该底 + 可选收盘 > ZG + 可选 SMA；"
        "卖：顶分型 + 向上笔终点；有重叠中枢时可附加收盘与 ZD 关系。最近三笔无价位重叠时买卖均退化为分型+笔（与中枢逻辑对称）。"
    )
    default_symbols = ["SPY"]
    default_timeframes = ["1d"]
    default_frequency = "0 16 * * 1-5"
    default_parameters = {
        "timeframe": "1d",
        "sma_period": 20,
        "use_sma_filter": False,
        "bar_limit": 320,
        "min_fractal_sep": 4,
        "use_bi_filter": True,
        "use_zhongshu_filter": True,
        "zhongshu_stroke_count": 3,
        "buy_close_above_zg": True,
        "sell_close_below_zd": False,
    }

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
        sma_n = int(p.get("sma_period", 20))
        use_sma = bool(p.get("use_sma_filter", False))
        limit = int(p.get("bar_limit", 320))
        limit = max(limit, sma_n + 40, 120)
        min_sep = int(p.get("min_fractal_sep", 4))
        use_bi = bool(p.get("use_bi_filter", True))
        use_zs = bool(p.get("use_zhongshu_filter", True))
        n_zs = int(p.get("zhongshu_stroke_count", 3))
        buy_zg = bool(p.get("buy_close_above_zg", True))
        sell_zd = bool(p.get("sell_close_below_zd", False))

        bar_t = await ctx.decision_time()
        if getattr(self, "_chan_mvp_bar_utc", None) != bar_t:
            self._chan_mvp_bar_utc = bar_t
            self._chan_mvp_sig_cache = {}

        signals: list[TradeSignal] = []
        for symbol in symbols:
            if not symbol:
                continue

            cache_key = (
                symbol,
                tf,
                limit,
                sma_n,
                use_sma,
                min_sep,
                use_bi,
                use_zs,
                n_zs,
                buy_zg,
                sell_zd,
            )
            hit = self._chan_mvp_sig_cache.get(cache_key)
            if hit is not None:
                direction, reasoning = hit
            else:
                df = await ctx.get_bars(symbol, tf, limit=limit)
                if df is None or df.empty or len(df) < 3:
                    self._chan_mvp_sig_cache[cache_key] = (None, "skip_short")
                    continue

                direction, reasoning = mvp_chan_signal_at_last_bar(
                    df,
                    sma_period=sma_n,
                    use_sma_filter=use_sma,
                    min_fractal_sep=min_sep,
                    use_bi_filter=use_bi,
                    use_zhongshu_filter=use_zs,
                    zhongshu_stroke_count=n_zs,
                    buy_close_above_zg=buy_zg,
                    sell_close_below_zd=sell_zd,
                )
                self._chan_mvp_sig_cache[cache_key] = (direction, reasoning)

            if direction is None:
                continue

            if direction == "buy":
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="buy",
                        order_type="market",
                        confidence=0.65,
                        reasoning=f"chan_mvp_buy:{reasoning}",
                    )
                )
            else:
                signals.append(
                    TradeSignal(
                        symbol=symbol,
                        direction="sell",
                        order_type="market",
                        confidence=0.65,
                        reasoning=f"chan_mvp_sell:{reasoning}",
                    )
                )
        return signals
