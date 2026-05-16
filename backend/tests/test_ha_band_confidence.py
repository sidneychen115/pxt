"""HA band strategy: confidence from breakout excess (scheme 1)."""

from src.strategies.library.ha_month_week_band import HaMonthOpenWeeklyCloseBandStrategy


def test_confidence_at_band_edge_is_floor():
    bench, w_close = 100.0, 101.0
    delta = 1.0
    upper, lower = bench + delta, bench - delta
    conf, excess = HaMonthOpenWeeklyCloseBandStrategy._confidence_from_breakout(
        bench, w_close, upper, lower, delta, "buy", floor=0.5, cap=1.0, excess_scale=0.25
    )
    assert excess == 0.0
    assert conf == 0.5


def test_confidence_scales_with_excess_capped():
    bench, delta = 100.0, 2.0
    upper = bench + delta
    w_close = upper + 4.0  # 2× band above upper
    conf, excess = HaMonthOpenWeeklyCloseBandStrategy._confidence_from_breakout(
        bench, w_close, upper, bench - delta, delta, "buy", floor=0.5, cap=1.0, excess_scale=0.25
    )
    assert excess == 2.0
    assert conf == 1.0


def test_zero_band_uses_benchmark_relative_excess():
    bench, w_close = 100.0, 102.0
    delta = 0.0
    upper, lower = bench, bench
    conf, excess = HaMonthOpenWeeklyCloseBandStrategy._confidence_from_breakout(
        bench, w_close, upper, lower, delta, "buy", floor=0.5, cap=1.0, excess_scale=0.25
    )
    assert excess == 0.02
    assert conf == 0.505


def test_detect_band_cross_up_through_upper():
    assert (
        HaMonthOpenWeeklyCloseBandStrategy._detect_band_cross(
            100.0, 100.0, 102.0, 100.0, 0.01, 0.0
        )
        == "buy"
    )


def test_detect_band_cross_down_through_lower():
    assert (
        HaMonthOpenWeeklyCloseBandStrategy._detect_band_cross(
            100.0, 100.0, 98.0, 100.0, 0.01, 0.0
        )
        == "sell"
    )


def test_detect_no_cross_when_still_above_upper():
    assert (
        HaMonthOpenWeeklyCloseBandStrategy._detect_band_cross(
            103.0, 100.0, 104.0, 100.0, 0.01, 0.0
        )
        is None
    )


def test_detect_no_cross_when_still_below_lower():
    assert (
        HaMonthOpenWeeklyCloseBandStrategy._detect_band_cross(
            97.0, 100.0, 96.0, 100.0, 0.01, 0.0
        )
        is None
    )


def test_signal_from_cross_includes_strength_in_reasoning():
    strat = HaMonthOpenWeeklyCloseBandStrategy()
    # prev inside band, curr above upper (1% band on bench 100 → upper 101)
    sig = strat._signal_from_cross(
        "SPY", 100.0, 100.5, 100.0, 103.0, 0.01, 0.0, "2026-05-15"
    )
    assert sig is not None
    assert sig.direction == "buy"
    assert "crossed up through upper" in sig.reasoning
    assert 0.5 <= sig.confidence <= 1.0
    assert "excess=" in sig.reasoning
    assert "strength=" in sig.reasoning
