"""Entry point for the Telegram bot."""

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .bot import setup_handlers
from .config import get_config
from .llm import create_llm_adapter
from .storage import SQLiteStorage


def setup_logging(log_path: str, log_level: str) -> None:
    """Setup logging configuration."""
    # Ensure log directory exists
    log_dir = Path(log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)


async def main() -> None:
    """Main entry point."""
    # Load configuration
    config = get_config()

    # Setup logging
    setup_logging(config.log_path, config.log_level)
    logger = logging.getLogger(__name__)

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("Starting Chat Ollama Telegram Bot")
    logger.info(f"LLM Engine: {config.llm_engine}")
    if config.llm_engine == "ollama":
        logger.info(f"Ollama URL: {config.ollama_base_url}")
        logger.info(f"Ollama Model: {config.ollama_model}")
    else:
        logger.info(f"llama.cpp Model: {config.llamacpp_model_path}")
    logger.info("=" * 50)

    # Initialize storage
    storage = SQLiteStorage(
        db_path=config.db_path,
        max_messages=config.max_history_messages,
    )
    await storage.init()
    logger.info("Storage initialized")

    # Initialize LLM adapter
    llm = create_llm_adapter(config)
    logger.info(f"LLM adapter created: {llm.engine_name}/{llm.model_name}")

    # Check LLM health
    if await llm.health_check():
        logger.info("LLM health check passed")
    else:
        logger.warning(
            "LLM health check failed! "
            "Make sure Ollama is running (ollama serve) or llama.cpp is configured correctly."
        )

    # Initialize bot
    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Initialize dispatcher
    dp = Dispatcher()

    # Setup handlers
    setup_handlers(dp, llm, storage, config)

    try:
        # Get bot info
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username}")

        # Start polling
        logger.info("Starting long polling...")
        await dp.start_polling(bot)

    except Exception as e:
        logger.exception(f"Bot error: {e}")
        raise

    finally:
        # Cleanup
        logger.info("Shutting down...")
        await llm.close()
        await storage.close()
        await bot.session.close()
        logger.info("Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
