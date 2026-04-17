from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Send prompt, return text response."""
