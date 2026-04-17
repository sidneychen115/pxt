from abc import ABC, abstractmethod
from src.core.models import TradeSignalRecord


class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, signal: TradeSignalRecord, instrument_symbol: str) -> bool:
        """Send notification. Returns True on success."""
