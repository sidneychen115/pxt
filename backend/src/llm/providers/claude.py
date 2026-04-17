import anthropic
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class ClaudeProvider(BaseLLMProvider):
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, prompt: str) -> str:
        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
