from __future__ import annotations

import argparse
import asyncio
from typing import List

from .agent import ToolLog, run_agent


def print_logs(logs: List[ToolLog]) -> None:
    if not logs:
        print("No tool calls were made.")
        return

    print("Tool calls:")
    for idx, log in enumerate(logs, start=1):
        print(f"{idx}. {log.name} args={log.args} -> {log.result_preview}")
    print()


async def main_async(question: str) -> None:
    answer, logs = await run_agent(question)
    print_logs(logs)
    print("Assistant:")
    print(answer)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GigaChat agent that calls MCP weather tools over stdio.",
    )
    parser.add_argument(
        "question",
        nargs="+",
        help='Question to ask, e.g. "Какая сейчас температура и ветер в Москве?"',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    question = " ".join(args.question)
    asyncio.run(main_async(question))


if __name__ == "__main__":
    main()

