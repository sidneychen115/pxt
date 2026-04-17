import importlib
import inspect
import pkgutil
from src.strategies.base import BaseStrategy

REGISTRY: dict[str, type[BaseStrategy]] = {}


def discover_strategies() -> None:
    """Auto-discover all BaseStrategy subclasses in src/strategies/library/."""
    import src.strategies.library as library_pkg
    for _, module_name, _ in pkgutil.iter_modules(library_pkg.__path__):
        module = importlib.import_module(f"src.strategies.library.{module_name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseStrategy) and obj is not BaseStrategy and hasattr(obj, "id"):
                REGISTRY[obj.id] = obj


def get_strategy(strategy_id: str) -> BaseStrategy:
    if strategy_id not in REGISTRY:
        raise KeyError(f"Strategy '{strategy_id}' not found. Available: {list(REGISTRY)}")
    return REGISTRY[strategy_id]()
