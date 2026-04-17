from openai import AsyncOpenAI
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def model_name(self) -> str:
        return "gpt-4o-mini"

    async def complete(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        if not response.choices:
            raise ValueError("OpenAI returned no choices")
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI returned no text content")
        return content
