"""Handlers for the Hugging Face demo bot."""

from typing import Dict

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services.huggingface import (
    DEFAULT_MODEL_ALIAS,
    DEFAULT_MODEL_ALIASES,
    GenerationResult,
    default_client,
    resolve_model_alias,
)

USER_MODELS: Dict[int, str] = {}
SUPPORTED_ALIASES = list(DEFAULT_MODEL_ALIASES.keys())


def get_user_model(user_id: int) -> str:
    return USER_MODELS.get(user_id, DEFAULT_MODEL_ALIAS)


def set_user_model(user_id: int, alias: str) -> None:
    USER_MODELS[user_id] = alias


def build_model_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{alias} → {DEFAULT_MODEL_ALIASES[alias]}", callback_data=f"model:{alias}")]
        for alias in SUPPORTED_ALIASES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def cmd_start(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    set_user_model(user_id, DEFAULT_MODEL_ALIAS)
    intro = (
        "👋 Я демо-бот для Hugging Face Inference API.\n"
        "Используй /model чтобы выбрать модель (deepseek, llama3, qwen2).\n"
        "Просто отправь текст — я отвечу выбранной моделью."
    )
    await message.answer(intro, reply_markup=build_model_keyboard())


async def cmd_model(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    current_alias = get_user_model(user_id)
    await message.answer(
        f"Текущая модель: *{current_alias}* → `{resolve_model_alias(current_alias)}`\n"
        "Выбери другую:",
        reply_markup=build_model_keyboard(),
    )


async def on_model_click(callback: CallbackQuery):
    user_id = callback.from_user.id if callback.from_user else 0
    if not callback.data:
        return
    alias = callback.data.split(":", maxsplit=1)[1]
    if alias not in SUPPORTED_ALIASES:
        await callback.answer("Неизвестная модель", show_alert=True)
        return
    set_user_model(user_id, alias)
    await callback.answer(f"Модель переключена на {alias}")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=build_model_keyboard())


async def handle_text(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    prompt = message.text or ""
    alias = get_user_model(user_id)
    await message.chat.do("typing")

    try:
        result: GenerationResult = await default_client.generate_text(alias, prompt)
        await message.answer(result.text)
    except Exception as exc:
        await message.answer("⚠️ Не удалось получить ответ от модели. Попробуй позже.")
        print(f"Hugging Face bot error: {exc}")


def register_handlers(dp: Dispatcher) -> None:
    """Attach handlers to the dispatcher."""
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_model, Command("model"))
    dp.callback_query.register(on_model_click, F.data.startswith("model:"))
    dp.message.register(handle_text, F.text)
