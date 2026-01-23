"""Configuration module - loads settings from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env file from project root
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)


@dataclass
class Config:
    """Application configuration."""

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))

    # LLM Engine: "ollama" or "llamacpp"
    llm_engine: Literal["ollama", "llamacpp"] = field(
        default_factory=lambda: os.getenv("LLM_ENGINE", "ollama")  # type: ignore
    )

    # Ollama settings
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma2:2b"))

    # llama.cpp settings
    llamacpp_model_path: str = field(
        default_factory=lambda: os.getenv("LLAMACPP_MODEL_PATH", "")
    )
    llamacpp_cli_path: str = field(
        default_factory=lambda: os.getenv("LLAMACPP_CLI_PATH", "llama-cli")
    )
    llamacpp_n_ctx: int = field(
        default_factory=lambda: int(os.getenv("LLAMACPP_N_CTX", "4096"))
    )
    llamacpp_n_predict: int = field(
        default_factory=lambda: int(os.getenv("LLAMACPP_N_PREDICT", "512"))
    )

    # Dialog history settings
    max_history_messages: int = field(
        default_factory=lambda: int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
    )
    max_response_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_RESPONSE_TOKENS", "400"))
    )

    # LLM generation parameters (optimized for gemma2:2b real estate assistant)
    llm_temperature: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.4"))
    )
    llm_top_p: float = field(
        default_factory=lambda: float(os.getenv("LLM_TOP_P", "0.9"))
    )
    llm_top_k: int = field(
        default_factory=lambda: int(os.getenv("LLM_TOP_K", "40"))
    )
    llm_repeat_penalty: float = field(
        default_factory=lambda: float(os.getenv("LLM_REPEAT_PENALTY", "1.10"))
    )

    # Database
    db_path: str = field(
        default_factory=lambda: os.getenv(
            "DB_PATH", str(Path(__file__).parent / "data" / "history.db")
        )
    )

    # Logging
    log_path: str = field(
        default_factory=lambda: os.getenv(
            "LOG_PATH", str(Path(__file__).parent / "logs" / "bot.log")
        )
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Timeouts
    llm_timeout: int = field(
        default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "120"))
    )
    llm_retries: int = field(default_factory=lambda: int(os.getenv("LLM_RETRIES", "2")))

    # System prompt
    system_prompt: str = field(
        default_factory=lambda: os.getenv(
            "SYSTEM_PROMPT",
            "Ты — помощник по недвижимости. Отвечай кратко и по делу. "
            "Не выдумывай цены, ставки и законы. Если не знаешь — скажи прямо.",
        )
    )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")

        if self.llm_engine not in ("ollama", "llamacpp"):
            errors.append(f"LLM_ENGINE must be 'ollama' or 'llamacpp', got '{self.llm_engine}'")

        if self.llm_engine == "llamacpp" and not self.llamacpp_model_path:
            errors.append("LLAMACPP_MODEL_PATH is required when LLM_ENGINE=llamacpp")

        return errors


def get_config() -> Config:
    """Get configuration instance."""
    return Config()
