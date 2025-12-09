"""Run one of the available Telegram bots."""

import argparse
import asyncio
from typing import Callable

from bots.hf_demo.bot import create_bot as create_hf_demo_bot
from bots.literary.bot import create_bot as create_literary_bot
from bots.real_estate.bot import create_bot as create_real_estate_bot


async def _run(create_fn: Callable[[], tuple]):
    bot, dp = create_fn()
    await dp.start_polling(bot)


def main():
    parser = argparse.ArgumentParser(description="Run Telegram bots in this project.")
    parser.add_argument(
        "--bot",
        choices=["real_estate", "literary", "hf_demo"],
        default="real_estate",
        help="Which bot to run (default: real_estate).",
    )
    args = parser.parse_args()

    runner: Callable[[], tuple]
    if args.bot == "real_estate":
        runner = create_real_estate_bot
    elif args.bot == "literary":
        runner = create_literary_bot
    else:
        runner = create_hf_demo_bot
    asyncio.run(_run(runner))


if __name__ == "__main__":
    main()
