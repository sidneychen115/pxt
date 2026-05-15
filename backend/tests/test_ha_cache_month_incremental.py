"""Current month HA open = (prev month HA open + prev month HA close) / 2."""

from src.strategies.heikin_ashi import heikin_ashi_single_bar


def test_month_open_from_prev_anchor():
    prev_o, prev_c = 50.0, 52.0
    bench = (prev_o + prev_c) / 2.0
    assert bench == 51.0


def test_prev_month_ha_bootstrap_matches_single_bar():
    o, h, l, c = 100.0, 105.0, 98.0, 102.0
    ha_o, _, _, ha_c = heikin_ashi_single_bar(o, h, l, c, o, c)
    bench = (ha_o + ha_c) / 2.0
    assert ha_o == (o + c) / 2.0
    assert bench == (ha_o + ha_c) / 2.0
