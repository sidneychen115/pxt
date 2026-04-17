from openai import AsyncOpenAI
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return response.choices[0].message.content
