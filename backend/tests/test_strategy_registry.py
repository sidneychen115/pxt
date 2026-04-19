from src.strategies.registry import discover_strategies, REGISTRY, get_strategy


def test_discover_finds_ma_crossover():
    REGISTRY.clear()
    discover_strategies()
    assert "ma_crossover" in REGISTRY
    assert "adaptive_turtle" in REGISTRY


def test_get_strategy_returns_instance():
    discover_strategies()
    strategy = get_strategy("ma_crossover")
    assert hasattr(strategy, "generate_signals")


def test_get_strategy_unknown_raises():
    import pytest
    discover_strategies()
    with pytest.raises(KeyError):
        get_strategy("nonexistent_strategy_xyz")
