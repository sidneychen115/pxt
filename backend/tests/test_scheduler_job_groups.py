from types import SimpleNamespace

from src.scheduler.job_groups import (
    group_active_user_strategies,
    job_id_for_group,
    signals_for_user_symbols,
)


def _us(**kwargs):
    defaults = dict(
        strategy_id="ha",
        run_frequency="0 16 * * 1-5",
        symbols=["SPY"],
        timeframes=["1d"],
        parameters={},
        is_active=True,
        user_id=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_merge_same_schedule_different_symbols():
    rows = [
        _us(user_id=1, symbols=["SPY", "QQQ"]),
        _us(user_id=2, symbols=["AAPL"]),
    ]
    groups = group_active_user_strategies(rows)
    assert len(groups) == 1
    assert set(groups[0].merged_symbols) == {"SPY", "QQQ", "AAPL"}
    assert len(groups[0].members) == 2


def test_split_different_run_frequency():
    rows = [
        _us(user_id=1, run_frequency="0 16 * * 1-5"),
        _us(user_id=2, run_frequency="0 17 * * 1-5"),
    ]
    assert len(group_active_user_strategies(rows)) == 2


def test_split_different_parameters():
    rows = [
        _us(user_id=1, parameters={"x": 1}),
        _us(user_id=2, parameters={"x": 2}),
    ]
    assert len(group_active_user_strategies(rows)) == 2


def test_inactive_excluded():
    rows = [_us(user_id=1), _us(user_id=2, is_active=False)]
    groups = group_active_user_strategies(rows)
    assert len(groups) == 1
    assert len(groups[0].members) == 1


def test_job_id_stable():
    rows = [_us(user_id=1), _us(user_id=2, symbols=["AAPL"])]
    g = group_active_user_strategies(rows)[0]
    assert job_id_for_group(g) == job_id_for_group(g)


def test_signals_for_user_symbols():
    sig = SimpleNamespace(symbol="SPY", direction="buy")
    other = SimpleNamespace(symbol="QQQ", direction="buy")
    assert signals_for_user_symbols([sig, other], ["SPY"]) == [sig]
