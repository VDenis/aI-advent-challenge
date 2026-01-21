"""Ollama LLM adapter."""

import asyncio
import logging
from typing import Any

import httpx

from .base import (
    BaseLLMAdapter,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMTimeoutError,
    Message,
)

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseLLMAdapter):
    """Adapter for Ollama local LLM service."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: int = 120,
        retries: int = 2,
    ):
        """
        Initialize Ollama adapter.

        Args:
            base_url: Ollama API base URL
            model: Default model name
            timeout: Request timeout in seconds
            retries: Number of retries on failure
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._retries = retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
            )
        return self._client

    @property
    def engine_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Generate response using Ollama /api/chat endpoint."""
        client = await self._get_client()

        # Convert messages to Ollama format
        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        payload = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        last_error: Exception | None = None

        for attempt in range(self._retries + 1):
            try:
                logger.debug(f"Ollama request attempt {attempt + 1}/{self._retries + 1}")

                response = await client.post("/api/chat", json=payload)

                if response.status_code == 404:
                    raise LLMModelNotFoundError(
                        f"Model '{self._model}' not found. "
                        f"Pull it with: ollama pull {self._model}"
                    )

                response.raise_for_status()
                data = response.json()

                content = data.get("message", {}).get("content", "")
                if not content:
                    logger.warning(f"Empty response from Ollama: {data}")
                    content = "Не удалось получить ответ от модели."

                return content

            except httpx.ConnectError as e:
                last_error = LLMConnectionError(
                    f"Не удалось подключиться к Ollama ({self._base_url}). "
                    "Убедитесь, что Ollama запущен: ollama serve"
                )
                logger.warning(f"Connection error: {e}")

            except httpx.TimeoutException as e:
                last_error = LLMTimeoutError(
                    f"Таймаут запроса к Ollama ({self._timeout}s). "
                    "Попробуйте использовать более быструю модель или увеличить таймаут."
                )
                logger.warning(f"Timeout error: {e}")

            except httpx.HTTPStatusError as e:
                last_error = LLMConnectionError(f"HTTP error from Ollama: {e.response.status_code}")
                logger.warning(f"HTTP error: {e}")

            except Exception as e:
                last_error = LLMConnectionError(f"Unexpected error: {e}")
                logger.exception("Unexpected error in Ollama request")

            if attempt < self._retries:
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

        raise last_error or LLMConnectionError("Unknown error")

    async def set_model(self, model_name: str) -> None:
        """Change the current model."""
        # Check if model exists by trying to get its info
        client = await self._get_client()

        try:
            response = await client.post("/api/show", json={"name": model_name})

            if response.status_code == 404:
                # Try to list available models
                models = await self.list_models()
                raise LLMModelNotFoundError(
                    f"Модель '{model_name}' не найдена. "
                    f"Доступные модели: {', '.join(models) if models else 'нет'}. "
                    f"Скачайте модель: ollama pull {model_name}"
                )

            response.raise_for_status()
            self._model = model_name
            logger.info(f"Model changed to: {model_name}")

        except httpx.ConnectError:
            raise LLMConnectionError(
                f"Не удалось подключиться к Ollama ({self._base_url}). "
                "Убедитесь, что Ollama запущен."
            )

    async def list_models(self) -> list[str]:
        """List available models in Ollama."""
        client = await self._get_client()

        try:
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models = [m["name"] for m in data.get("models", [])]
            return models

        except httpx.ConnectError:
            raise LLMConnectionError(
                f"Не удалось подключиться к Ollama ({self._base_url}). "
                "Убедитесь, что Ollama запущен."
            )
        except Exception as e:
            logger.exception("Error listing models")
            return []

    async def health_check(self) -> bool:
        """Check if Ollama is running."""
        client = await self._get_client()

        try:
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
