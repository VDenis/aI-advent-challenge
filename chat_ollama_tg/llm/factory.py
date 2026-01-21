"""Factory for creating LLM adapters."""

from ..config import Config
from .base import BaseLLMAdapter
from .llamacpp import LlamaCppAdapter
from .ollama import OllamaAdapter


def create_llm_adapter(config: Config) -> BaseLLMAdapter:
    """
    Create an LLM adapter based on configuration.

    Args:
        config: Application configuration

    Returns:
        LLM adapter instance

    Raises:
        ValueError: If unknown engine specified
    """
    if config.llm_engine == "ollama":
        return OllamaAdapter(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            timeout=config.llm_timeout,
            retries=config.llm_retries,
        )
    elif config.llm_engine == "llamacpp":
        return LlamaCppAdapter(
            model_path=config.llamacpp_model_path,
            cli_path=config.llamacpp_cli_path,
            n_ctx=config.llamacpp_n_ctx,
            n_predict=config.llamacpp_n_predict,
            timeout=config.llm_timeout,
            retries=config.llm_retries,
        )
    else:
        raise ValueError(f"Unknown LLM engine: {config.llm_engine}")
