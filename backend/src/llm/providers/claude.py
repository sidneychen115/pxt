import anthropic
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class ClaudeProvider(BaseLLMProvider):
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def model_name(self) -> str:
        return "claude-sonnet-4-6"

    async def complete(self, prompt: str) -> str:
        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        if not message.content:
            raise ValueError("Claude returned empty content")
        block = message.content[0]
        if not isinstance(block, anthropic.types.TextBlock):
            raise ValueError(f"Unexpected content block type: {type(block)}")
        return block.text
