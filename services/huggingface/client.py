"""Async client for Hugging Face Inference API using the openai client."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from .config import HuggingFaceConfig, resolve_model_alias

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Container for generation output and simple metrics."""

    model: str
    text: str
    raw_response: Any
    status: int
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class HuggingFaceClient:
    """High-level async client for Hugging Face text generation."""

    def __init__(self, config: Optional[HuggingFaceConfig] = None):
        self.config = config or HuggingFaceConfig()
        self.client = AsyncOpenAI(base_url=self.config.base_url, api_key=self.config.token)

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text) / self.config.average_chars_per_token))

    def _extract_text_and_tokens(self, data: Any) -> tuple[str, int]:
        """Handle typical Inference API responses."""
        text = ""
        output_tokens = 0

        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                text = str(first.get("generated_text") or first.get("generated_text_tokenized") or "")
                output_tokens = int(first.get("generated_token_count", 0) or 0)
            else:
                text = str(first)
        elif isinstance(data, dict):
            if "generated_text" in data:
                text = str(data.get("generated_text", ""))
                output_tokens = int(data.get("generated_token_count", 0) or 0)
            elif "choices" in data:
                choices = data.get("choices") or []
                if choices:
                    text = str(choices[0].get("text") or choices[0].get("message", {}).get("content", ""))
                    usage = data.get("usage") or {}
                    output_tokens = int(usage.get("completion_tokens", 0) or 0)
            elif "error" in data:
                raise RuntimeError(f"HuggingFace error: {data.get('error')}")
            else:
                text = str(data)
        else:
            text = str(data)

        if not text:
            raise RuntimeError(f"HuggingFace response missing generated text: {data}")

        return text, output_tokens

    async def generate_text(
        self,
        model: str,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        """Call Hugging Face Inference endpoint and return generated text."""
        if not self.config.token:
            raise RuntimeError("HF_TOKEN is not configured")

        full_model = resolve_model_alias(model, self.config.model_aliases)

        params: Dict[str, Any] = {
            "max_tokens": max_tokens if max_tokens is not None else self.config.default_max_tokens,
            "temperature": temperature if temperature is not None else self.config.default_temperature,
        }
        params.update(kwargs)

        start_time = time.monotonic()

        try:
            response = await self.client.chat.completions.create(
                model=full_model,
                messages=[{"role": "user", "content": prompt}],
                **params,
            )
        except Exception as exc:
            raise RuntimeError(f"HuggingFace request failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start_time) * 1000

        choice = response.choices[0] if response.choices else None
        message_content = choice.message.content if choice and choice.message else ""
        text = message_content or ""

        usage = response.usage or {}
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        if not text:
            text, output_tokens = self._extract_text_and_tokens(response.model_dump())

        if input_tokens <= 0:
            input_tokens = self._estimate_tokens(prompt)
        if output_tokens <= 0:
            output_tokens = self._estimate_tokens(text)

        logger.debug(
            "HuggingFace response: model=%s time_ms=%.2f tokens_in=%s tokens_out=%s",
            full_model,
            elapsed_ms,
            input_tokens,
            output_tokens,
        )

        return GenerationResult(
            model=full_model,
            text=text,
            raw_response=response.model_dump(),
            status=200,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


default_client = HuggingFaceClient()


async def generate_text(
    model: str,
    prompt: str,
    *,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> GenerationResult:
    """Convenience wrapper using the default client."""
    return await default_client.generate_text(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
