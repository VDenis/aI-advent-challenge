"""CLI utility for testing Hugging Face models locally."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.huggingface import (  # noqa: E402
    DEFAULT_MODEL_ALIAS,
    DEFAULT_MODEL_ALIASES,
    GenerationResult,
    default_client,
    resolve_model_alias,
)

COMPARISON_ALIASES = ["deepseek", "llama3", "qwen2"]


def _estimate_cost(alias: str, total_tokens: int) -> float:
    price_per_1k = default_client.config.pricing_per_1k_tokens.get(alias, 0.0)
    if price_per_1k <= 0:
        return 0.0
    return (total_tokens / 1000) * price_per_1k


async def run_single(
    prompt: str,
    model_alias: str,
    max_tokens: int,
    temperature: float,
) -> tuple[GenerationResult, float]:
    start = time.monotonic()
    result = await default_client.generate_text(
        model_alias, prompt, max_tokens=max_tokens, temperature=temperature
    )
    duration_ms = (time.monotonic() - start) * 1000
    return result, duration_ms


async def compare_three(prompt: str, max_tokens: int, temperature: float) -> None:
    rows = []
    for alias in COMPARISON_ALIASES:
        result, duration_ms = await run_single(prompt, alias, max_tokens, temperature)
        rows.append(
            {
                "alias": alias,
                "model": resolve_model_alias(alias),
                "time_ms": duration_ms,
                "tokens": result.total_tokens,
                "cost": _estimate_cost(alias, result.total_tokens),
                "text": result.text,
            }
        )

    print("\nСравнение моделей по одному запросу:\n")
    header = f"{'alias':<10}{'time_ms':>12}{'tokens':>12}{'cost(~)':>12}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['alias']:<10}{row['time_ms']:>12.1f}{row['tokens']:>12}{row['cost']:>12.4f}")
    print("\nДетальные ответы:")
    for row in rows:
        print(f"\n[{row['alias']}] {row['model']} (≈{row['tokens']} токенов, {row['time_ms']:.1f} мс)")
        print(row["text"])


async def main_async():
    parser = argparse.ArgumentParser(description="Hugging Face Inference API CLI tester.")
    parser.add_argument("prompt", help="Текстовый запрос для модели.")
    parser.add_argument(
        "--model",
        choices=list(DEFAULT_MODEL_ALIASES.keys()),
        default=DEFAULT_MODEL_ALIAS,
        help="Короткое имя модели (default: llama3).",
    )
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=default_client.config.default_max_tokens,
        help="Максимум новых токенов в ответе.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=default_client.config.default_temperature,
        help="Температура выборки (по умолчанию из конфига).",
    )
    parser.add_argument(
        "--compare_three",
        action="store_true",
        help="Последовательно сравнить deepseek, llama3 и qwen2 на одном запросе.",
    )
    args = parser.parse_args()

    try:
        if args.compare_three:
            await compare_three(args.prompt, args.max_tokens, args.temperature)
            return

        result, duration_ms = await run_single(args.prompt, args.model, args.max_tokens, args.temperature)
        est_cost = _estimate_cost(args.model, result.total_tokens)
        print(f"Модель: {args.model} → {resolve_model_alias(args.model)}")
        print(f"Время ответа: {duration_ms:.1f} мс")
        print(
            f"Токенов (примерно): {result.total_tokens} "
            f"(in: {result.input_tokens}, out: {result.output_tokens})"
        )
        print(f"Стоимость (примерно): {est_cost:.4f} за запрос")
        print("\nОтвет модели:\n")
        print(result.text)
    except Exception as exc:
        print(f"⚠️ Ошибка при обращении к Hugging Face: {exc}")


if __name__ == "__main__":
    asyncio.run(main_async())
