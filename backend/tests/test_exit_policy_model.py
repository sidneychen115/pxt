import pytest
from src.backtesting.exit_policy import ExitPolicy


def test_stop_loss_mutual_exclusion():
    with pytest.raises(ValueError, match="stop_loss"):
        ExitPolicy(stop_loss_pct=0.05, stop_loss_abs=500.0)


def test_take_profit_mutual_exclusion():
    with pytest.raises(ValueError, match="take_profit"):
        ExitPolicy(take_profit_pct=0.15, take_profit_abs=2000.0)


def test_trailing_activate_requires_trailing_stop():
    with pytest.raises(ValueError, match="trailing_stop_pct"):
        ExitPolicy(trailing_activate_pct=0.05)


def test_all_none_is_valid():
    policy = ExitPolicy()
    assert policy.stop_loss_pct is None
    assert policy.trailing_stop_pct is None
    assert policy.price_check_mode == "close"


def test_valid_combined_policy():
    policy = ExitPolicy(
        stop_loss_pct=0.05,
        take_profit_pct=0.15,
        trailing_stop_pct=0.03,
        price_check_mode="ohlc",
    )
    assert policy.stop_loss_pct == 0.05
    assert policy.take_profit_pct == 0.15
    assert policy.trailing_stop_pct == 0.03
    assert policy.price_check_mode == "ohlc"


def test_trailing_with_activation_valid():
    policy = ExitPolicy(trailing_stop_pct=0.05, trailing_activate_pct=0.10)
    assert policy.trailing_activate_pct == 0.10


def test_stop_loss_pct_must_be_positive():
    with pytest.raises(ValueError):
        ExitPolicy(stop_loss_pct=-0.05)


def test_stop_loss_pct_zero_invalid():
    with pytest.raises(ValueError):
        ExitPolicy(stop_loss_pct=0.0)


def test_take_profit_pct_must_be_positive():
    with pytest.raises(ValueError):
        ExitPolicy(take_profit_pct=-0.10)


def test_stop_loss_abs_must_be_positive():
    with pytest.raises(ValueError):
        ExitPolicy(stop_loss_abs=-100.0)
