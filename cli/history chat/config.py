"""Shared configuration for the GigaChat console client.

Values are loaded from `.env` via python-dotenv. Required variables:
- GIGA_CLIENT_BASIC: base64-encoded `client_id:client_secret`.
Optional:
- GIGA_API_BASE_URL: base URL for GigaChat API (defaults to production).
- GIGA_VERIFY_SSL: set to `false`/`0` to disable SSL verification (not recommended).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from dotenv import load_dotenv


load_dotenv()


DEFAULT_BASE_URL = "https://gigachat.devices.sberbank.ru"
DEFAULT_CHAT_PATH = "/api/v1/chat/completions"
DEFAULT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_MODEL = "GigaChat"
DEFAULT_REQUEST_TIMEOUT = 60.0

# Conversation handling defaults.
SUMMARY_EVERY_USER_MESSAGES = 5
SUMMARY_PAIR_BATCH = 5

# Pricing hooks (per 1k tokens). Values can be adjusted later.
PRICE_INPUT_PER_1K = 0.0
PRICE_OUTPUT_PER_1K = 0.0

# Optional system prompt to keep at the top of history.
DEFAULT_SYSTEM_PROMPT: Optional[str] = None

# Session memory defaults.
DEFAULT_MEMORY_FILE = Path(__file__).resolve().parents[2] / ".chat_memory.json"
DEFAULT_SESSION_LIST_LIMIT = 5


def _bool_from_env(value: str, *, default: bool = True) -> bool:
    if value == "":
        return default
    return value.lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the console chat client."""

    base_url: str
    chat_url: str
    oauth_url: str
    model: str
    basic_auth: str
    verify_ssl: bool
    request_timeout: float
    summary_every: int
    summary_pair_batch: int
    price_input_per_1k: float
    price_output_per_1k: float
    system_prompt: Optional[str] = None
    memory_file: Path = DEFAULT_MEMORY_FILE
    session_list_limit: int = DEFAULT_SESSION_LIST_LIMIT


def load_settings(*, memory_file: Optional[Path] = None, session_list_limit: Optional[int] = None) -> Settings:
    """Load settings from environment with sensible defaults."""
    base_url = os.getenv("GIGA_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    chat_url = os.getenv(
        "GIGA_CHAT_URL",
        urljoin(base_url + "/", DEFAULT_CHAT_PATH.lstrip("/")),
    )
    oauth_url = os.getenv("GIGA_OAUTH_URL", DEFAULT_OAUTH_URL)
    basic_auth = os.getenv("GIGA_CLIENT_BASIC", "")
    if not basic_auth:
        raise RuntimeError("GIGA_CLIENT_BASIC is required but not set in .env")

    verify_ssl = _bool_from_env(os.getenv("GIGA_VERIFY_SSL", ""), default=True)
    memory_file_path = Path(
        memory_file
        or os.getenv("CHAT_MEMORY_FILE")
        or DEFAULT_MEMORY_FILE
    ).expanduser().resolve()
    list_limit = session_list_limit or int(os.getenv("CHAT_MEMORY_LIST_LIMIT", DEFAULT_SESSION_LIST_LIMIT))

    return Settings(
        base_url=base_url,
        chat_url=chat_url,
        oauth_url=oauth_url,
        model=os.getenv("GIGA_MODEL_NAME", DEFAULT_MODEL),
        basic_auth=basic_auth,
        verify_ssl=verify_ssl,
        request_timeout=float(os.getenv("GIGA_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)),
        summary_every=int(os.getenv("GIGA_SUMMARY_EVERY", SUMMARY_EVERY_USER_MESSAGES)),
        summary_pair_batch=int(os.getenv("GIGA_SUMMARY_BATCH", SUMMARY_PAIR_BATCH)),
        price_input_per_1k=float(os.getenv("PRICE_INPUT_PER_1K", PRICE_INPUT_PER_1K)),
        price_output_per_1k=float(os.getenv("PRICE_OUTPUT_PER_1K", PRICE_OUTPUT_PER_1K)),
        system_prompt=os.getenv("GIGA_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT) or None,
        memory_file=memory_file_path,
        session_list_limit=list_limit,
    )
