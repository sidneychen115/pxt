import httpx
from src.llm.providers.base import BaseLLMProvider
from src.core.config import settings


class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str = "llama3"):
        self._model = model
        self._base_url = settings.ollama_base_url

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["response"]
