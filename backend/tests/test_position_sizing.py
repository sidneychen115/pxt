from src.backtesting.position_sizing import (
    buy_quantity_for_signal,
    parse_backtest_position_pct,
)


def test_parse_fraction_and_percent():
    assert parse_backtest_position_pct({}) == 0.1
    assert parse_backtest_position_pct({"backtest_position_pct": 0.25}) == 0.25
    assert parse_backtest_position_pct({"backtest_position_pct": 50}) == 0.5


def test_buy_quantity_default_uses_pct_of_cash():
    qty = buy_quantity_for_signal(
        cash=10_000,
        fill_price=100.0,
        position_pct=0.2,
        signal_quantity=None,
    )
    assert qty == 20.0


def test_buy_quantity_caps_strategy_qty():
    qty = buy_quantity_for_signal(
        cash=10_000,
        fill_price=100.0,
        position_pct=0.1,
        signal_quantity=50.0,
    )
    assert qty == 10.0
