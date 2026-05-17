from src.strategies.chan_mvp_params import resolve_chan_mvp_params


def test_resolve_1h_defaults_when_only_timeframe_set():
    p = resolve_chan_mvp_params({"timeframe": "1h"})
    assert p["timeframe"] == "1h"
    assert p["bar_limit"] == 1500
    assert p["sma_period"] == 50


def test_resolve_1d_defaults():
    p = resolve_chan_mvp_params({"timeframe": "1d"})
    assert p["bar_limit"] == 320
    assert p["sma_period"] == 20


def test_user_override_bar_limit_on_1h():
    p = resolve_chan_mvp_params({"timeframe": "1h", "bar_limit": 800})
    assert p["bar_limit"] == 800


def test_resolve_15m_keeps_timeframe_and_intraday_defaults():
    p = resolve_chan_mvp_params({"timeframe": "15m"})
    assert p["timeframe"] == "15m"
    assert p["bar_limit"] == 800
    assert p["sma_period"] == 50
