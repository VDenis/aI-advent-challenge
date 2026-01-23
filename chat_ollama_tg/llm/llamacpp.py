"""llama.cpp LLM adapter using subprocess."""

import asyncio
import logging
import shutil
from pathlib import Path

from .base import (
    BaseLLMAdapter,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMTimeoutError,
    Message,
)

logger = logging.getLogger(__name__)


class LlamaCppAdapter(BaseLLMAdapter):
    """
    Adapter for llama.cpp using llama-cli subprocess.

    Security note: Uses asyncio.create_subprocess_exec which passes arguments
    as a list, avoiding shell injection vulnerabilities (similar to execFile).
    """

    def __init__(
        self,
        model_path: str,
        cli_path: str = "llama-cli",
        n_ctx: int = 4096,
        n_predict: int = 512,
        timeout: int = 120,
        retries: int = 2,
    ):
        """
        Initialize llama.cpp adapter.

        Args:
            model_path: Path to GGUF model file
            cli_path: Path to llama-cli executable
            n_ctx: Context size
            n_predict: Max tokens to generate
            timeout: Generation timeout in seconds
            retries: Number of retries on failure
        """
        self._model_path = model_path
        self._cli_path = cli_path
        self._n_ctx = n_ctx
        self._n_predict = n_predict
        self._timeout = timeout
        self._retries = retries

        # Validate on init
        self._validate_setup()

    def _validate_setup(self) -> None:
        """Validate llama.cpp setup."""
        # Check if llama-cli exists
        if not shutil.which(self._cli_path):
            # Check if it's a full path
            if not Path(self._cli_path).exists():
                logger.warning(
                    f"llama-cli not found at '{self._cli_path}'. "
                    "Make sure llama.cpp is installed and llama-cli is in PATH."
                )

        # Check if model file exists
        if self._model_path and not Path(self._model_path).exists():
            logger.warning(f"Model file not found: {self._model_path}")

    @property
    def engine_name(self) -> str:
        return "llamacpp"

    @property
    def model_name(self) -> str:
        return Path(self._model_path).stem if self._model_path else "none"

    def _format_prompt(self, messages: list[Message]) -> str:
        """
        Format messages into a prompt string for llama.cpp.

        Uses ChatML format which works with most models.
        """
        prompt_parts = []

        for msg in messages:
            if msg.role == "system":
                prompt_parts.append(f"<|im_start|>system\n{msg.content}<|im_end|>")
            elif msg.role == "user":
                prompt_parts.append(f"<|im_start|>user\n{msg.content}<|im_end|>")
            elif msg.role == "assistant":
                prompt_parts.append(f"<|im_start|>assistant\n{msg.content}<|im_end|>")

        # Add start of assistant response
        prompt_parts.append("<|im_start|>assistant\n")

        return "\n".join(prompt_parts)

    async def generate(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
    ) -> str:
        """Generate response using llama-cli subprocess."""
        if not Path(self._model_path).exists():
            raise LLMModelNotFoundError(f"Model file not found: {self._model_path}")

        prompt = self._format_prompt(messages)

        # Build llama-cli command as a list (safe from shell injection)
        cmd = [
            self._cli_path,
            "-m", self._model_path,
            "-c", str(self._n_ctx),
            "-n", str(min(max_tokens, self._n_predict)),
            "--temp", str(temperature),
            "--top-p", str(top_p),
            "--top-k", str(top_k),
            "--repeat-penalty", str(repeat_penalty),
            "-p", prompt,
            "--no-display-prompt",
            "-e",
        ]

        last_error: Exception | None = None

        for attempt in range(self._retries + 1):
            try:
                logger.debug(f"llama.cpp request attempt {attempt + 1}/{self._retries + 1}")
                logger.debug(f"Running command: {' '.join(cmd[:6])}...")

                # Using create_subprocess_exec (not shell) - safe from injection
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self._timeout,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise LLMTimeoutError(
                        f"Таймаут генерации ({self._timeout}s). "
                        "Попробуйте уменьшить max_tokens или использовать более быструю модель."
                    )

                if process.returncode != 0:
                    error_msg = stderr.decode("utf-8", errors="replace")
                    logger.error(f"llama-cli error: {error_msg}")

                    if "model" in error_msg.lower() and "not found" in error_msg.lower():
                        raise LLMModelNotFoundError(f"Model error: {error_msg}")

                    raise LLMConnectionError(f"llama-cli error: {error_msg}")

                output = stdout.decode("utf-8", errors="replace").strip()

                # Clean up output - remove any trailing special tokens
                for stop_token in ["<|im_end|>", "<|endoftext|>", "</s>"]:
                    if stop_token in output:
                        output = output.split(stop_token)[0]

                output = output.strip()

                if not output:
                    logger.warning("Empty response from llama.cpp")
                    output = "Не удалось получить ответ от модели."

                return output

            except (LLMTimeoutError, LLMModelNotFoundError):
                raise

            except FileNotFoundError:
                raise LLMConnectionError(
                    f"llama-cli не найден: {self._cli_path}. "
                    "Установите llama.cpp и добавьте llama-cli в PATH."
                )

            except Exception as e:
                last_error = LLMConnectionError(f"Ошибка llama.cpp: {e}")
                logger.exception("Error in llama.cpp generation")

            if attempt < self._retries:
                await asyncio.sleep(1 * (attempt + 1))

        raise last_error or LLMConnectionError("Unknown error")

    async def set_model(self, model_name: str) -> None:
        """
        Change the current model.

        For llama.cpp, model_name should be a path to a GGUF file.
        """
        model_path = Path(model_name)

        if not model_path.exists():
            raise LLMModelNotFoundError(
                f"Файл модели не найден: {model_name}. "
                "Укажите полный путь к GGUF файлу."
            )

        if not model_path.suffix.lower() == ".gguf":
            logger.warning(f"Model file doesn't have .gguf extension: {model_name}")

        self._model_path = str(model_path)
        logger.info(f"Model changed to: {model_name}")

    async def list_models(self) -> list[str]:
        """
        List available models.

        For llama.cpp, returns the current model path.
        """
        if self._model_path and Path(self._model_path).exists():
            return [self._model_path]
        return []

    async def health_check(self) -> bool:
        """Check if llama.cpp is available."""
        # Check if llama-cli exists
        if not shutil.which(self._cli_path):
            if not Path(self._cli_path).exists():
                return False

        # Check if model exists
        if not self._model_path or not Path(self._model_path).exists():
            return False

        return True
