"""Telegram bot handlers."""

import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..llm.base import BaseLLMAdapter, LLMError, Message as LLMMessage
from ..storage import SQLiteStorage

if TYPE_CHECKING:
    from ..config import Config

logger = logging.getLogger(__name__)

# Create router for handlers
router = Router()

# Global references (set by setup_handlers)
_llm: BaseLLMAdapter | None = None
_storage: SQLiteStorage | None = None
_config: "Config | None" = None

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long message into chunks."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    # Try to split on newlines first
    lines = text.split("\n")

    for line in lines:
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + "\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            # If single line is too long, split by words
            if len(line) > max_length:
                words = line.split(" ")
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= max_length:
                        current_chunk += word + " "
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.rstrip())
                        current_chunk = word + " "
            else:
                current_chunk = line + "\n"

    if current_chunk:
        chunks.append(current_chunk.rstrip())

    return chunks


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    welcome_text = """👋 Привет! Я бот-ассистент с локальной языковой моделью.

Я работаю на базе Ollama/llama.cpp и могу отвечать на ваши вопросы полностью офлайн (генерация происходит локально).

📝 **Как пользоваться:**
Просто напишите мне сообщение, и я отвечу!

⚙️ **Команды:**
/help — справка по командам
/reset — очистить историю диалога
/model — показать текущую модель
/setmodel <имя> — сменить модель

💡 Примечание: хотя генерация ответов происходит локально, для работы Telegram-бота нужен интернет."""

    await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    help_text = """📖 **Справка по командам:**

/start — приветствие и краткая инструкция
/help — эта справка
/reset — очистить историю диалога (начать заново)
/model — показать текущую модель и движок
/setmodel <имя> — сменить модель

**Для Ollama:** имя модели, например: `llama3.2`, `mistral`, `gemma2`
**Для llama.cpp:** путь к GGUF файлу

📊 **Ограничения:**
• История хранит последние {max_messages} сообщений
• Максимальная длина ответа: {max_tokens} токенов

🔧 **Движок:** {engine}
🤖 **Модель:** {model}"""

    if _config and _llm:
        help_text = help_text.format(
            max_messages=_config.max_history_messages,
            max_tokens=_config.max_response_tokens,
            engine=_llm.engine_name,
            model=_llm.model_name,
        )

    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    """Handle /reset command - clear dialog history."""
    if not _storage:
        await message.answer("❌ Хранилище не инициализировано")
        return

    chat_id = message.chat.id
    count = await _storage.clear_history(chat_id)

    await message.answer(f"🗑 История очищена ({count} сообщений удалено). Начнём сначала!")


@router.message(Command("model"))
async def cmd_model(message: Message) -> None:
    """Handle /model command - show current model."""
    if not _llm:
        await message.answer("❌ LLM не инициализирован")
        return

    # Check if chat has a custom model
    custom_model = None
    if _storage:
        custom_model = await _storage.get_chat_model(message.chat.id)

    model_info = f"""🤖 **Информация о модели:**

• Движок: `{_llm.engine_name}`
• Модель: `{_llm.model_name}`"""

    if custom_model:
        model_info += f"\n• Выбранная модель для чата: `{custom_model}`"

    # Try to list available models
    try:
        models = await _llm.list_models()
        if models:
            models_list = "\n".join(f"  • `{m}`" for m in models[:10])
            model_info += f"\n\n📋 **Доступные модели:**\n{models_list}"
            if len(models) > 10:
                model_info += f"\n  ... и ещё {len(models) - 10}"
    except Exception as e:
        logger.warning(f"Error listing models: {e}")

    await message.answer(model_info, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("setmodel"))
async def cmd_setmodel(message: Message) -> None:
    """Handle /setmodel command - change model."""
    if not _llm or not _storage:
        await message.answer("❌ LLM или хранилище не инициализированы")
        return

    # Extract model name from command
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "❌ Укажите имя модели.\n"
                f"Пример: `/setmodel llama3.2`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        model_name = parts[1].strip()
    else:
        await message.answer("❌ Укажите имя модели")
        return

    # Show typing indicator
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)  # type: ignore

    try:
        await _llm.set_model(model_name)
        await _storage.set_chat_model(message.chat.id, model_name)
        await message.answer(f"✅ Модель изменена на `{model_name}`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error setting model: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message()
async def handle_message(message: Message) -> None:
    """Handle regular text messages."""
    if not message.text:
        return

    if not _llm or not _storage or not _config:
        await message.answer("❌ Бот не полностью инициализирован. Попробуйте позже.")
        return

    chat_id = message.chat.id
    user_text = message.text

    logger.info(f"Message from chat {chat_id}: {user_text[:50]}...")

    # Show typing indicator
    bot = message.bot
    if bot:
        await bot.send_chat_action(chat_id, ChatAction.TYPING)

    try:
        # Save user message to history
        await _storage.add_message(chat_id, "user", user_text)

        # Get chat history
        history = await _storage.get_history(chat_id)

        # Build messages for LLM
        messages = [LLMMessage(role="system", content=_config.system_prompt)]
        messages.extend(history)

        logger.debug(f"Sending {len(messages)} messages to LLM")

        # Generate response
        response = await _llm.generate(
            messages=messages,
            max_tokens=_config.max_response_tokens,
        )

        # Save assistant response to history
        await _storage.add_message(chat_id, "assistant", response)

        # Split and send response
        chunks = split_message(response)
        for chunk in chunks:
            await message.answer(chunk)

        logger.info(f"Response sent to chat {chat_id}: {len(response)} chars")

    except LLMError as e:
        logger.error(f"LLM error for chat {chat_id}: {e}")
        await message.answer(f"❌ Ошибка генерации: {e}")

    except Exception as e:
        logger.exception(f"Unexpected error for chat {chat_id}")
        await message.answer("❌ Произошла непредвиденная ошибка. Попробуйте позже.")


def setup_handlers(
    dp: Dispatcher,
    llm: BaseLLMAdapter,
    storage: SQLiteStorage,
    config: "Config",
) -> None:
    """
    Setup bot handlers.

    Args:
        dp: Aiogram dispatcher
        llm: LLM adapter instance
        storage: Storage instance
        config: Application config
    """
    global _llm, _storage, _config

    _llm = llm
    _storage = storage
    _config = config

    dp.include_router(router)
    logger.info("Handlers registered")
