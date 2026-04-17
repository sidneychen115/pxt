from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the actual model identifier string."""

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Send prompt, return text response."""
