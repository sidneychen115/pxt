"""Tests for Chan MVP structure helpers."""

import pandas as pd
import pytest

from src.strategies.chan_structure import (
    MergedBar,
    build_strokes,
    collapse_adjacent_same_fractals,
    merge_inclusions,
    mvp_chan_signal_at_last_bar,
    mvp_fractal_signal_at_last_bar,
    raw_fractals,
    zhongshu_from_last_strokes,
)


def test_merge_inclusion_combines_two_bars():
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [105.0, 103.0],
            "low": [95.0, 96.0],
            "close": [100.0, 102.0],
            "volume": [1, 1],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="B"),
    )
    m = merge_inclusions(df)
    assert len(m) == 1
    assert m[0].high == 103.0
    assert m[0].low == 95.0
    assert m[0].orig_end == 1


def test_bottom_fractal_confirm_on_last_bar():
    rows = []
    for i in range(27):
        o = 100.0 + i * 0.05
        h = o + 1.0
        lo = o - 1.0
        c = o
        rows.append((o, h, lo, c))
    rows.append((100.0, 101.0, 99.0, 100.0))
    rows.append((100.0, 100.0, 98.0, 99.0))
    rows.append((100.0, 102.0, 99.0, 101.0))
    o, h, lo, c = zip(*rows, strict=True)
    df = pd.DataFrame(
        {
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": [1] * len(rows),
        },
        index=pd.date_range("2024-01-01", periods=len(rows), freq="B"),
    )
    direction, reason = mvp_fractal_signal_at_last_bar(
        df, sma_period=20, use_sma_filter=False
    )
    assert direction == "buy"
    assert "bottom_fractal" in reason


def test_top_fractal_sell_priority():
    """When the last bar confirms a top (rare short pattern), return sell."""
    highs = [100.0, 102.0, 101.0]
    lows = [99.0, 100.0, 99.5]
    closes = [100.0, 101.5, 100.0]
    df = pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1] * 3,
        },
        index=pd.date_range("2024-01-01", periods=3, freq="B"),
    )
    direction, _ = mvp_fractal_signal_at_last_bar(df, use_sma_filter=False)
    assert direction == "sell"


def test_build_strokes_respects_min_sep():
    merged = [MergedBar(0.0, 0.0, 0.0, 0.0, i) for i in range(5)]
    cf = [(0, "bottom"), (4, "top")]
    strokes = build_strokes(merged, cf, min_sep=4)
    assert strokes == [(0, 4, "up")]


def test_sma_filter_blocks_buy_when_below_ma():
    rows = []
    for i in range(25):
        o = 100.0 + i * 0.05
        h = o + 1.0
        lo = o - 1.0
        c = o
        rows.append((o, h, lo, c))
    rows.append((100.0, 101.0, 99.0, 100.0))
    rows.append((100.0, 100.0, 98.0, 99.0))
    rows.append((100.0, 101.0, 99.0, 99.2))
    o, h, lo, c = zip(*rows, strict=True)
    df = pd.DataFrame(
        {
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": [1] * len(rows),
        },
        index=pd.date_range("2024-01-01", periods=len(rows), freq="B"),
    )
    direction, reason = mvp_fractal_signal_at_last_bar(
        df, sma_period=20, use_sma_filter=True
    )
    assert direction is None
    assert reason == "sma_not_met"


def test_merge_requires_ohlc_columns():
    df = pd.DataFrame({"open": [1.0], "high": [1.0]})
    with pytest.raises(ValueError, match="need columns"):
        merge_inclusions(df)


def test_raw_fractals_and_collapse():
    merged = [
        MergedBar(1, 10, 8, 1, 0),
        MergedBar(1, 14, 9, 1, 1),
        MergedBar(1, 13, 9, 1, 2),
        MergedBar(1, 15, 10, 1, 3),
    ]
    rf = raw_fractals(merged)
    assert rf
    cf = collapse_adjacent_same_fractals(merged, rf)
    kinds = [k for _, k in cf]
    assert "top" in kinds or "bottom" in kinds


def test_zhongshu_from_three_overlapping_ranges():
    merged = [
        MergedBar(0, 30.0, 10.0, 20.0, 0),
        MergedBar(0, 25.0, 12.0, 18.0, 1),
        MergedBar(0, 20.0, 15.0, 17.0, 2),
    ]
    strokes = [(0, 0, "down"), (1, 1, "up"), (2, 2, "down")]
    zs = zhongshu_from_last_strokes(merged, strokes, 3)
    assert zs is not None
    zd, zg = zs
    assert zd < zg
    assert zd == 15.0
    assert zg == 20.0


def test_zhongshu_none_when_no_overlap():
    merged = [
        MergedBar(0, 10.0, 9.0, 9.5, 0),
        MergedBar(0, 50.0, 40.0, 45.0, 1),
        MergedBar(0, 20.0, 18.0, 19.0, 2),
    ]
    strokes = [(0, 0, "down"), (1, 1, "up"), (2, 2, "down")]
    assert zhongshu_from_last_strokes(merged, strokes, 3) is None


def test_mvp_chan_off_behaves_like_fractal_only():
    rows = []
    for i in range(27):
        o = 100.0 + i * 0.05
        h = o + 1.0
        lo = o - 1.0
        c = o
        rows.append((o, h, lo, c))
    rows.append((100.0, 101.0, 99.0, 100.0))
    rows.append((100.0, 100.0, 98.0, 99.0))
    rows.append((100.0, 102.0, 99.0, 101.0))
    o, h, lo, c = zip(*rows, strict=True)
    df = pd.DataFrame(
        {
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": [1] * len(rows),
        },
        index=pd.date_range("2024-01-01", periods=len(rows), freq="B"),
    )
    a, ra = mvp_fractal_signal_at_last_bar(df, use_sma_filter=False)
    b, rb = mvp_chan_signal_at_last_bar(
        df,
        use_sma_filter=False,
        use_bi_filter=False,
        use_zhongshu_filter=False,
    )
    assert a == b == "buy"
    assert "bottom" in ra and "bottom" in rb


def test_chan_buy_falls_back_when_no_three_stroke_overlap(monkeypatch):
    """Trending SPY-like windows often have no zs; buys should not block for years."""
    rows = []
    for i in range(27):
        o = 100.0 + i * 0.05
        h = o + 1.0
        lo = o - 1.0
        c = o
        rows.append((o, h, lo, c))
    rows.append((100.0, 101.0, 99.0, 100.0))
    rows.append((100.0, 100.0, 98.0, 99.0))
    rows.append((100.0, 102.0, 99.0, 101.0))
    o, h, lo, c = zip(*rows, strict=True)
    df = pd.DataFrame(
        {
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": [1] * len(rows),
        },
        index=pd.date_range("2024-01-01", periods=len(rows), freq="B"),
    )
    monkeypatch.setattr(
        "src.strategies.chan_structure.zhongshu_from_last_strokes",
        lambda *_a, **_k: None,
    )
    direction, reason = mvp_chan_signal_at_last_bar(
        df,
        use_sma_filter=False,
        use_bi_filter=False,
        use_zhongshu_filter=True,
    )
    assert direction == "buy"
    assert "no_zhongshu_overlap" in reason
