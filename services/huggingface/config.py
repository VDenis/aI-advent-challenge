"""Configuration and constants for the Hugging Face Inference API client."""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

# Mapping of short names to full model ids in Hugging Face Hub.
DEFAULT_MODEL_ALIASES: Dict[str, str] = {
    "deepseek": "deepseek-ai/DeepSeek-V3.2:novita",
    "llama3": "meta-llama/Meta-Llama-3-8B-Instruct",
    "qwen2": "Gensyn/Qwen2.5-1.5B-Instruct:featherless-ai",
}

# Simple pricing map: cost per 1000 tokens (input + output).
# Values are placeholders; adjust to real pricing if needed.
DEFAULT_PRICING_PER_1K: Dict[str, float] = {
    "deepseek": 0.0,
    "llama3": 0.0,
    "qwen2": 0.0,
}

DEFAULT_MODEL_ALIAS: str = "llama3"


@dataclass
class HuggingFaceConfig:
    """Runtime configuration for Hugging Face Inference API client."""

    # OpenAI-compatible endpoint for Hugging Face Inference API (OpenAI-style)
    base_url: str = "https://router.huggingface.co/v1"
    token: str = os.getenv("HF_TOKEN", "")
    request_timeout: float = 60.0
    default_max_tokens: int = 512
    default_temperature: float = 0.7
    average_chars_per_token: float = 4.0
    model_aliases: Dict[str, str] = field(default_factory=lambda: DEFAULT_MODEL_ALIASES.copy())
    pricing_per_1k_tokens: Dict[str, float] = field(default_factory=lambda: DEFAULT_PRICING_PER_1K.copy())


def resolve_model_alias(name: str, aliases: Optional[Dict[str, str]] = None) -> str:
    """Return a full model id for a given alias or full name."""
    if not name:
        return (aliases or DEFAULT_MODEL_ALIASES).get(DEFAULT_MODEL_ALIAS, DEFAULT_MODEL_ALIASES[DEFAULT_MODEL_ALIAS])
    lookup = {k.lower(): v for k, v in (aliases or DEFAULT_MODEL_ALIASES).items()}
    key = name.lower()
    return lookup.get(key, name)
