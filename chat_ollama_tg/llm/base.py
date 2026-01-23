"""Base class for LLM adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class Message:
    """Chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """Base exception for LLM errors."""

    pass


class LLMConnectionError(LLMError):
    """Connection to LLM service failed."""

    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""

    pass


class LLMModelNotFoundError(LLMError):
    """Requested model not found."""

    pass


class BaseLLMAdapter(ABC):
    """Base class for LLM adapters."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return the name of the LLM engine."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the current model name."""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            messages: List of chat messages (system, user, assistant)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            top_p: Nucleus sampling threshold
            top_k: Top-k sampling parameter
            repeat_penalty: Repetition penalty

        Returns:
            Generated text response

        Raises:
            LLMConnectionError: If connection to LLM service fails
            LLMTimeoutError: If request times out
            LLMModelNotFoundError: If model is not available
        """
        pass

    @abstractmethod
    async def set_model(self, model_name: str) -> None:
        """
        Change the current model.

        Args:
            model_name: Name of the model to use

        Raises:
            LLMModelNotFoundError: If model is not available
        """
        pass

    @abstractmethod
    async def list_models(self) -> list[str]:
        """
        List available models.

        Returns:
            List of available model names
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the LLM service is available.

        Returns:
            True if service is healthy, False otherwise
        """
        pass

    async def close(self) -> None:
        """Clean up resources."""
        pass
