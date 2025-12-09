"""Handlers for the real estate Telegram bot."""

from typing import Dict, List, Literal, TypedDict

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services.gigachat import chat_gigachat

EXPERT_PROMPT = """Ты — эксперт по подбору квартир в новостройках и на вторичном рынке. Твоя задача — помогать пользователю найти оптимальную квартиру под его запрос: бюджет, количество комнат, район, транспортная доступность, инфраструктура, сроки сдачи и т.п. Всегда сначала уточняй критерии, если их не хватает для осознанной рекомендации. Объясняй свои рекомендации простым понятным языком, без канцелярита. Давай структурированные ответы: краткий вывод, затем список подходящих вариантов с короткими комментариями, плюсы и минусы для каждого."""

FRIEND_PROMPT = """Ты — дружелюбный, но при этом разумный друг, который помогает выбрать квартиру. Общайся неформально, как хороший знакомый: можно использовать разговорные формулировки, но без грубостей и токсичности. Твоя задача — помочь человеку разобраться, подходит ли квартира под его образ жизни, привычки, бюджет и планы на будущее. Поддерживай, снимай лишнюю тревогу, но не скрывай очевидные минусы вариантов. Отвечая, сначала коротко отзеркали запрос («ты ищешь ...»), затем давай рекомендации и мягко подталкивай к уточняющим вопросам, если чего-то не хватает."""

CRITIC_PROMPT = """Ты — строгий и требовательный критик при выборе квартиры. Твоя задача — искать слабые места в каждом варианте: завышенная цена, неудачная планировка, проблемы с локацией, риски по срокам сдачи, слабая инфраструктура, шум, транспорт и т.д. Будь прямолинейным, но не оскорбительным: критикуй варианты, а не пользователя. Каждый раз, когда пользователь предлагает вариант или критерий, сначала перечисляй возможные риски и недостатки, затем давай взвешенный вывод: «если для тебя Х не критично — вариант можно рассматривать / лучше поискать альтернативу». Не соглашайся автоматически, всегда проверяй, не есть ли за запросом скрытые проблемы (переплата, завышенные ожидания, недооценка района и т.п.)."""

DEFAULT_PROMPT = """Ты — умный помощник для поиска и анализа информации о квартирах и недвижимости, но также можешь отвечать на общие вопросы. По умолчанию общайся нейтрально и вежливо, структурируй ответы и по возможности уточняй цель пользователя, если запрос выглядит неполным или расплывчатым. Если пользователь начинает обсуждать покупку или аренду квартиры, автоматически переходи к поведению эксперта по подбору квартир: уточняй критерии, помогай формулировать запрос и объясняй плюсы и минусы решений. Если пользователь просит дружеский совет или «покритикуй мой вариант», можешь адаптировать стиль под более дружелюбный или критичный, но сохраняй рациональность и пользу."""


class ConversationState(TypedDict):
    mode: Literal["expert", "friend", "critic", "default"]
    history: List[Dict[str, str]]


PROMPTS: Dict[str, str] = {
    "expert": EXPERT_PROMPT,
    "friend": FRIEND_PROMPT,
    "critic": CRITIC_PROMPT,
    "default": DEFAULT_PROMPT,
}

states: Dict[int, ConversationState] = {}
KEYWORDS = ["квартира", "flat", "цена", "площадь", "район", "этаж"]


async def get_state(user_id: int) -> ConversationState:
    return states.get(user_id, {"mode": "default", "history": []})


async def set_state(user_id: int, **kwargs) -> None:
    current = await get_state(user_id)
    states[user_id] = {**current, **kwargs}


def build_mode_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🏗 Эксперт", callback_data="mode:expert"),
            InlineKeyboardButton(text="🤝 Друг", callback_data="mode:friend"),
        ],
        [
            InlineKeyboardButton(text="🧭 Критик", callback_data="mode:critic"),
            InlineKeyboardButton(text="⚖️ По умолчанию", callback_data="mode:default"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def apply_mode(message: Message, user_id: int, mode: str, source: str) -> None:
    await set_state(user_id, mode=mode)
    note = {
        "expert": "Режим эксперта: уточняю критерии и подбираю варианты.",
        "friend": "Режим друга: общаюсь неформально и поддерживаю.",
        "critic": "Режим критика: ищу слабые места и риски.",
        "default": "Нейтральный режим: отвечаю вежливо и структурно.",
    }.get(mode, "Режим обновлён.")
    await message.answer(f"Режим переключён на *{mode}* ({source}).\n{note}")


async def cmd_start(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    await set_state(user_id, mode="default", history=[])
    intro = (
        "👋 Привет! Я помогаю подобрать и оценить варианты квартир. "
        "Выбери стиль ответа или просто напиши запрос.\n\n"
        "Команды: /mode_expert /mode_friend /mode_critic /mode_default /reset\n"
        "Кнопки ниже переключают режим. История хранится пока бот запущен."
    )
    await message.answer(intro, reply_markup=build_mode_keyboard())


async def cmd_reset(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    states[user_id] = {"mode": "default", "history": []}
    await message.answer("История очищена, режим сброшен на *default*.")


async def cmd_mode_expert(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    await apply_mode(message, user_id, "expert", "команда")


async def cmd_mode_friend(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    await apply_mode(message, user_id, "friend", "команда")


async def cmd_mode_critic(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    await apply_mode(message, user_id, "critic", "команда")


async def cmd_mode_default(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    await apply_mode(message, user_id, "default", "команда")


async def on_mode_click(callback: CallbackQuery):
    user_id = callback.from_user.id if callback.from_user else 0
    mode = callback.data.split(":", maxsplit=1)[1]
    await set_state(user_id, mode=mode)
    try:
        await callback.message.edit_reply_markup(reply_markup=build_mode_keyboard())
    except TelegramBadRequest:
        # Сообщение уже имеет такую же разметку — игнорируем
        pass
    await callback.answer(f"Режим {mode} активирован.")


def trim_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return history[-20:]


async def handle_message(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    text = message.text or ""
    lower_text = text.lower()

    state = await get_state(user_id)
    mode = state["mode"]

    if mode == "default" and any(word in lower_text for word in KEYWORDS):
        mode = "expert"
        await set_state(user_id, mode=mode)
        await message.answer("Вижу, речь о квартирах — переключаюсь в режим *expert*.")

    await message.chat.do("typing")

    messages = [{"role": "system", "content": PROMPTS.get(mode, DEFAULT_PROMPT)}]
    messages.extend(state["history"][-18:])
    messages.append({"role": "user", "content": text})

    try:
        reply = await chat_gigachat(messages)
        new_history = trim_history(
            state["history"] + [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        )
        await set_state(user_id, history=new_history)
        await message.answer(reply)
    except Exception as exc:
        await message.answer("⚠️ Не удалось получить ответ от модели. Попробуй ещё раз.")
        print(f"GigaChat error: {exc}")


def register_handlers(dp: Dispatcher) -> None:
    """Attach handlers to the dispatcher."""
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_reset, Command("reset"))
    dp.message.register(cmd_mode_expert, Command("mode_expert"))
    dp.message.register(cmd_mode_friend, Command("mode_friend"))
    dp.message.register(cmd_mode_critic, Command("mode_critic"))
    dp.message.register(cmd_mode_default, Command("mode_default"))
    dp.callback_query.register(on_mode_click, F.data.startswith("mode:"))
    dp.message.register(handle_message, F.text)
