"""MVP Chan-style signals on regular OHLC bars (15m / 1h / 1d): 分型 + 笔 + 简化中枢 (optional SMA)."""

from __future__ import annotations

from src.strategies.base import BaseStrategy, DataContext, PortfolioSnapshot, TradeSignal
from src.strategies.chan_mvp_params import (
    DEFAULT_CHAN_MVP_TIMEFRAME,
    chan_mvp_default_parameters,
    resolve_chan_mvp_params,
)
from src.strategies.chan_structure import mvp_chan_signal_at_last_bar


class ChanBiFractalMvpStrategy(BaseStrategy):
    """分型 + 笔 + 中枢；买默认须站上 ZG；卖默认仅需顶分型+向上笔（可选再加破 ZD）。"""

    id = "chan_bi_fractal_mvp"
    name = "Chan MVP: 分型 + 笔 + 中枢 (15m / 1h / 日线)"
    description = (
        "Regular OHLC bars (default 1h; parameters.timeframe: 15m, 1h, or 1d). "
        "Inclusion merge, 分型, 笔 (min_fractal_sep), simplified 中枢 [ZD,ZG] from overlapping strokes. "
        "Buy: confirmed bottom fractal + downward stroke ending at bottom + optional close > ZG + optional SMA; "
        "sell: top fractal + upward stroke end; optional close vs ZD. Not full Chan theory."
    )
    default_symbols = ["SPY"]
    default_timeframes = ["15m", "1h", "1d"]
    default_frequency = "60m"
    default_parameters = chan_mvp_default_parameters(DEFAULT_CHAN_MVP_TIMEFRAME)

    async def generate_signals(
        self,
        symbols: list[str],
        parameters: dict,
        ctx: DataContext,
        portfolio: PortfolioSnapshot | None = None,
    ) -> list[TradeSignal]:
        p = resolve_chan_mvp_params(parameters)
        tf = str(p["timeframe"])
        sma_n = int(p["sma_period"])
        use_sma = bool(p["use_sma_filter"])
        limit = int(p["bar_limit"])
        limit = max(limit, sma_n + 40, 120)
        min_sep = int(p["min_fractal_sep"])
        use_bi = bool(p["use_bi_filter"])
        use_zs = bool(p["use_zhongshu_filter"])
        n_zs = int(p["zhongshu_stroke_count"])
        buy_zg = bool(p["buy_close_above_zg"])
        sell_zd = bool(p["sell_close_below_zd"])

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
