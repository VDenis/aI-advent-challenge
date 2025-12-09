"""Handlers for the literary bot that demonstrates temperature changes."""

from typing import Dict, List, Optional

from aiogram import Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from services.gigachat import chat_gigachat

SYSTEM_PROMPT = "Ты креативный писатель для сериалов с большим эго."
TEMPERATURES: List[float] = [0.0, 0.7, 1.2]


async def generate_responses_with_temperatures(
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> List[str]:
    """Return responses for several temperatures for comparison."""
    base_messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        base_messages.extend(history)
    base_messages.append({"role": "user", "content": text})

    responses: List[str] = []
    for temp in TEMPERATURES:
        reply = await chat_gigachat(base_messages, temperature=temp)
        responses.append(reply)

    return responses


async def cmd_start(message: Message):
    intro = (
        "👋 Я бот, который показывает, как меняется ответ модели при разных температурах.\n"
        "Пришли текст — я верну три варианта: T=0.0, T=0.7 и T=1.2."
    )
    await message.answer(intro)


async def handle_text(message: Message):
    text = message.text or ""
    await message.chat.do("typing")

    try:
        replies = await generate_responses_with_temperatures(text)
        for temp, reply in zip(TEMPERATURES, replies):
            await message.answer(f"T={temp}:\n{reply}")
    except Exception as exc:
        await message.answer("⚠️ Не удалось получить ответ от модели. Попробуй ещё раз.")
        print(f"GigaChat error (temperature bot): {exc}")


def register_handlers(dp: Dispatcher) -> None:
    """Attach handlers to the dispatcher."""
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(handle_text, F.text)
