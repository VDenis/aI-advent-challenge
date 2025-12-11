"""CLI for Llama 3 via Hugging Face Router (OpenAI-compatible) with token counting."""

import argparse
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

from openai import OpenAI

# Silence fork-related parallelism warning for tokenizers.
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from transformers import AutoTokenizer

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.huggingface.config import HuggingFaceConfig  # noqa: E402

MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
SYSTEM_PROMPT = "You are a helpful assistant."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call Llama 3 on Hugging Face Router (OpenAI API compatible) and count tokens locally."
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Входной текст (можно передать позиционно, через --text, --file или stdin).",
    )
    parser.add_argument("--text", dest="text_opt", help="Входной текст.")
    parser.add_argument(
        "--file",
        type=Path,
        help="Путь к файлу с текстом. Используется только если не указан аргумент text или --text.",
    )
    return parser.parse_args()


def read_user_text(args: argparse.Namespace) -> str:
    """Return input text from positional arg, --text, file, or stdin (exclusive)."""
    provided_sources = [
        name for name, present in [
            ("text", args.text is not None),
            ("text_opt", args.text_opt is not None),
            ("file", args.file is not None),
        ] if present
    ]
    if len(provided_sources) > 1:
        raise ValueError("Укажи только один источник текста: аргумент, --text или --file.")

    if args.file is not None:
        try:
            return args.file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Replace undecodable bytes with the standard replacement character.
            return args.file.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            raise FileNotFoundError(f"Не удалось прочитать файл {args.file}: {exc}") from exc

    if args.text is not None:
        return args.text

    if args.text_opt is not None:
        return args.text_opt

    if not sys.stdin.isatty():
        return sys.stdin.read()

    raise ValueError("Не найден входной текст. Передай аргумент, --text, --file или stdin.")


@lru_cache(maxsize=1)
def _get_tokenizer():
    return AutoTokenizer.from_pretrained(MODEL_ID)


def count_tokens_local(text: str) -> int:
    tokenizer = _get_tokenizer()
    tokens = tokenizer(text, add_special_tokens=False).input_ids
    return len(tokens)


def call_llama3_via_openai(text: str, config: Optional[HuggingFaceConfig] = None):
    cfg = config or HuggingFaceConfig()
    if not cfg.token:
        raise RuntimeError("HF_TOKEN не задан (environment или .env).")

    client = OpenAI(base_url=cfg.base_url, api_key=cfg.token)
    return client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        stream=False,
    )


def main() -> int:
    args = parse_args()

    try:
        user_text = read_user_text(args)
    except FileNotFoundError as exc:
        print(f"⚠️  Ошибка чтения файла: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"⚠️  Ошибка ввода: {exc}", file=sys.stderr)
        return 1

    try:
        local_input_tokens = count_tokens_local(user_text)
    except Exception as exc:  # pragma: no cover - безопасное оповещение
        print(f"⚠️  Не удалось посчитать токены локально: {exc}", file=sys.stderr)
        return 1

    try:
        completion = call_llama3_via_openai(user_text)
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        status_info = f" (status {status})" if status else ""
        print(f"⚠️  Запрос к Hugging Face не удался{status_info}: {exc}", file=sys.stderr)
        return 1

    choice = completion.choices[0] if completion.choices else None
    answer_text = choice.message.content if choice and choice.message else ""
    finish_reason = choice.finish_reason if choice else "unknown"

    usage = completion.usage
    api_prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    api_completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

    print(answer_text)
    print()
    print(f"local_input_tokens: {local_input_tokens}")
    print(f"api_prompt_tokens: {api_prompt_tokens}")
    print(f"api_completion_tokens: {api_completion_tokens}")
    print(f"finish_reason: {finish_reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
