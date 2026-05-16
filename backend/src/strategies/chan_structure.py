"""Chan-theory MVP helpers: inclusion merge, fractals, optional strokes on regular OHLC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.strategies.indicators import Indicators

FractalKind = Literal["top", "bottom"]


@dataclass(frozen=True)
class MergedBar:
    open: float
    high: float
    low: float
    close: float
    orig_end: int


def _ranges_overlap_inclusion(h1: float, l1: float, h2: float, l2: float) -> bool:
    """True if one bar's range contains the other's (缠论「包含」)."""
    return (h1 >= h2 and l1 <= l2) or (h2 >= h1 and l2 <= l1)


def _merge_direction(k0: MergedBar | None, a: MergedBar, b: MergedBar) -> bool:
    """Return True if merge direction is upward (高高、低高), else downward."""
    if k0 is not None:
        if a.high > k0.high:
            return True
        if a.high < k0.high:
            return False
        if a.low > k0.low:
            return True
        if a.low < k0.low:
            return False
        return a.close >= k0.close
    if b.high > a.high:
        return True
    if b.high < a.high:
        return False
    if b.low > a.low:
        return True
    if b.low < a.low:
        return False
    return b.close >= a.close


def _merge_pair(a: MergedBar, b: MergedBar, upward: bool) -> MergedBar:
    if upward:
        high = max(a.high, b.high)
        low = max(a.low, b.low)
    else:
        high = min(a.high, b.high)
        low = min(a.low, b.low)
    return MergedBar(
        open=a.open,
        high=high,
        low=low,
        close=b.close,
        orig_end=b.orig_end,
    )


def merge_inclusions(ohlc: pd.DataFrame) -> list[MergedBar]:
    """Apply sequential inclusion processing; each merged bar carries last raw iloc in ``orig_end``."""
    if ohlc.empty:
        return []
    need = {"open", "high", "low", "close"}
    if not need.issubset(ohlc.columns):
        raise ValueError(f"merge_inclusions: need columns {sorted(need)}")

    merged: list[MergedBar] = []
    for i in range(len(ohlc)):
        merged.append(
            MergedBar(
                open=float(ohlc["open"].iloc[i]),
                high=float(ohlc["high"].iloc[i]),
                low=float(ohlc["low"].iloc[i]),
                close=float(ohlc["close"].iloc[i]),
                orig_end=i,
            )
        )
        while len(merged) >= 2:
            a, b = merged[-2], merged[-1]
            if not _ranges_overlap_inclusion(a.high, a.low, b.high, b.low):
                break
            k0 = merged[-3] if len(merged) >= 3 else None
            upward = _merge_direction(k0, a, b)
            m = _merge_pair(a, b, upward)
            merged.pop()
            merged.pop()
            merged.append(m)
    return merged


def raw_fractals(merged: list[MergedBar]) -> list[tuple[int, FractalKind]]:
    """顶/底分型 on merged bars (strict inequalities). Indices are into ``merged``."""
    out: list[tuple[int, FractalKind]] = []
    n = len(merged)
    if n < 3:
        return out
    for i in range(1, n - 1):
        h_prev, h, h_next = merged[i - 1].high, merged[i].high, merged[i + 1].high
        lo_prev, lo, lo_next = merged[i - 1].low, merged[i].low, merged[i + 1].low
        if h > h_prev and h > h_next:
            out.append((i, "top"))
        elif lo < lo_prev and lo < lo_next:
            out.append((i, "bottom"))
    return out


def collapse_adjacent_same_fractals(
    merged: list[MergedBar], items: list[tuple[int, FractalKind]]
) -> list[tuple[int, FractalKind]]:
    """Merge consecutive same-type fractals, keeping the more extreme swing."""
    if not items:
        return []
    collapsed: list[tuple[int, FractalKind]] = []
    for i, k in items:
        if not collapsed:
            collapsed.append((i, k))
            continue
        pi, pk = collapsed[-1]
        if k != pk:
            collapsed.append((i, k))
            continue
        if k == "top":
            if merged[i].high >= merged[pi].high:
                collapsed[-1] = (i, k)
        else:
            if merged[i].low <= merged[pi].low:
                collapsed[-1] = (i, k)
    return collapsed


def build_strokes(
    merged: list[MergedBar],
    collapsed_fractals: list[tuple[int, FractalKind]],
    min_sep: int,
) -> list[tuple[int, int, Literal["up", "down"]]]:
    """(start_merged_idx, end_merged_idx, direction) for each valid 笔 segment between fractals."""
    if min_sep < 1:
        raise ValueError("min_sep must be >= 1")
    out: list[tuple[int, int, Literal["up", "down"]]] = []
    prev: tuple[int, FractalKind] | None = None
    for idx, typ in collapsed_fractals:
        if prev is None:
            prev = (idx, typ)
            continue
        pi, pt = prev
        if typ == pt:
            prev = (idx, typ)
            continue
        if idx - pi < min_sep:
            continue
        direction: Literal["up", "down"] = (
            "down" if pt == "top" and typ == "bottom" else "up"
        )
        out.append((pi, idx, direction))
        prev = (idx, typ)
    return out


def stroke_ohlc_range(merged: list[MergedBar], start_m: int, end_m: int) -> tuple[float, float]:
    """笔在 merged 区间内 [start_m, end_m] 的最低 low 与最高 high。"""
    if start_m > end_m:
        start_m, end_m = end_m, start_m
    seg = merged[start_m : end_m + 1]
    return min(b.low for b in seg), max(b.high for b in seg)


def zhongshu_from_last_strokes(
    merged: list[MergedBar],
    strokes: list[tuple[int, int, Literal["up", "down"]]],
    n: int = 3,
) -> tuple[float, float] | None:
    """简化中枢：最近 n 笔各自价位区间在价格轴上的交集 ``[ZD, ZG]``（存在非空重叠时）。

    非教科书完备定义，仅作结构过滤：``ZG`` 为上沿（重叠区高价端）、``ZD`` 为下沿。
    """
    if n < 2 or len(strokes) < n:
        return None
    intervals = [
        stroke_ohlc_range(merged, s, e) for s, e, _ in strokes[-n:]
    ]
    zd = max(lo for lo, _ in intervals)
    zg = min(hi for _, hi in intervals)
    if zd >= zg:
        return None
    return (zd, zg)


def _confirm_orig_pos(merged: list[MergedBar], fractal_center_m: int) -> int | None:
    """Original iloc where the分型 is confirmed (right neighbor merged bar finalized)."""
    if fractal_center_m < 1 or fractal_center_m >= len(merged) - 1:
        return None
    c = fractal_center_m + 1
    if c >= len(merged):
        return None
    return merged[c].orig_end


def mvp_chan_signal_at_last_bar(
    ohlc: pd.DataFrame,
    *,
    sma_period: int = 20,
    use_sma_filter: bool = False,
    min_fractal_sep: int = 4,
    use_bi_filter: bool = True,
    use_zhongshu_filter: bool = True,
    zhongshu_stroke_count: int = 3,
    buy_close_above_zg: bool = True,
    sell_close_below_zd: bool = False,
) -> tuple[Literal["buy", "sell"] | None, str]:
    """分型 + 可选笔/中枢过滤。

    有重叠中枢 ``[ZD,ZG]`` 时：买可要求收盘 > ZG；卖可要求收盘 < ZD（见参数）。
    最近 N 笔无价位重叠时：不阻塞整段回测，卖/买均退化为「分型 + 笔」规则（理由含 ``no_zhongshu_overlap``）。
    """
    if ohlc is None or ohlc.empty:
        return None, "empty"
    if len(ohlc) < 3:
        return None, "short_history"
    if min_fractal_sep < 1:
        return None, "bad_min_sep"
    n_zs = max(2, int(zhongshu_stroke_count))

    merged = merge_inclusions(ohlc)
    if len(merged) < 3:
        return None, "short_merged"

    rf = raw_fractals(merged)
    cf = collapse_adjacent_same_fractals(merged, rf)
    strokes = build_strokes(merged, cf, min_fractal_sep)
    zs = (
        zhongshu_from_last_strokes(merged, strokes, n_zs)
        if use_zhongshu_filter and strokes
        else None
    )

    last_i = len(ohlc) - 1
    last_close = float(ohlc["close"].iloc[-1])

    buy_center: int | None = None
    sell_center: int | None = None
    for center, kind in cf:
        cor = _confirm_orig_pos(merged, center)
        if cor != last_i:
            continue
        if kind == "top":
            sell_center = center
        else:
            buy_center = center

    def _down_bi_ends_at(ci: int) -> bool:
        return any(e == ci and d == "down" for _, e, d in strokes)

    def _up_bi_ends_at(ci: int) -> bool:
        return any(e == ci and d == "up" for _, e, d in strokes)

    sell_ok = sell_center is not None and (
        not use_bi_filter or _up_bi_ends_at(sell_center)
    )
    if sell_ok:
        if use_zhongshu_filter and zs is not None:
            zd, zg = zs
            if sell_close_below_zd:
                if last_close >= zd:
                    return None, "sell_need_below_zd"
            reason = (
                f"top_cf={sell_center};zs=({zd:.4f},{zg:.4f})"
                + (";under_zd" if sell_close_below_zd else "")
            )
            return "sell", reason
        # 启用中枢但当前三笔无重叠时，避免整段回测无法结构卖点，退化为顶分型+笔卖出
        if use_zhongshu_filter and zs is None:
            return "sell", f"top_cf={sell_center};no_zhongshu_overlap"
        return "sell", f"top_fractal_confirmed_center={sell_center}"

    if buy_center is not None:
        if use_bi_filter and not _down_bi_ends_at(buy_center):
            return None, "no_down_bi_at_bottom"
        if use_zhongshu_filter and zs is not None:
            zd, zg = zs
            if buy_close_above_zg and last_close <= zg:
                return None, "buy_need_above_zg"
            reason = f"bottom_cf={buy_center};zs=({zd:.4f},{zg:.4f})"
            if use_sma_filter:
                if len(ohlc) < sma_period:
                    return None, "sma_warmup"
                sma = Indicators.sma(ohlc, sma_period)
                sv = sma.iloc[-1]
                if pd.isna(sv) or last_close <= float(sv):
                    return None, "sma_not_met"
            return "buy", reason
        if use_zhongshu_filter and zs is None:
            reason = f"bottom_cf={buy_center};no_zhongshu_overlap"
            if use_sma_filter:
                if len(ohlc) < sma_period:
                    return None, "sma_warmup"
                sma = Indicators.sma(ohlc, sma_period)
                sv = sma.iloc[-1]
                if pd.isna(sv) or last_close <= float(sv):
                    return None, "sma_not_met"
            return "buy", reason
        if use_sma_filter:
            if len(ohlc) < sma_period:
                return None, "sma_warmup"
            sma = Indicators.sma(ohlc, sma_period)
            sv = sma.iloc[-1]
            if pd.isna(sv) or last_close <= float(sv):
                return None, "sma_not_met"
        return "buy", f"bottom_fractal_confirmed_center={buy_center}"

    return None, "no_fractal_signal"


def mvp_fractal_signal_at_last_bar(
    ohlc: pd.DataFrame,
    *,
    sma_period: int = 20,
    use_sma_filter: bool = True,
) -> tuple[Literal["buy", "sell"] | None, str]:
    """兼容旧逻辑：仅分型 + 可选 SMA（无笔/中枢）。"""
    return mvp_chan_signal_at_last_bar(
        ohlc,
        sma_period=sma_period,
        use_sma_filter=use_sma_filter,
        use_bi_filter=False,
        use_zhongshu_filter=False,
    )


__all__ = [
    "MergedBar",
    "merge_inclusions",
    "raw_fractals",
    "collapse_adjacent_same_fractals",
    "build_strokes",
    "stroke_ohlc_range",
    "zhongshu_from_last_strokes",
    "mvp_chan_signal_at_last_bar",
    "mvp_fractal_signal_at_last_bar",
]
