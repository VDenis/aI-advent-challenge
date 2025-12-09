"""Entry point for the literary temperature demo bot."""

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from bots.literary.handlers import register_handlers


def create_bot() -> tuple[Bot, Dispatcher]:
    """Create bot and dispatcher instances with handlers registered."""
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher()
    register_handlers(dp)
    return bot, dp


async def main() -> None:
    bot, dp = create_bot()
    print("🚀 Бот с разными температурами запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
