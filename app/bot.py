import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

from gigachat_client import ask_gigachat

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Состояния для FSM
class MovieQuiz(StatesGroup):
    question_1 = State()  # Настроение и жанр
    question_2 = State()  # Длительность
    question_3 = State()  # Мозговая нагрузка
    question_4 = State()  # Интересы
    question_5 = State()  # Время выхода


# Тексты вопросов
QUESTIONS = {
    1: "🎭 Какое у тебя настроение? Что хочется посмотреть?\n\n"
       "Например: адреналин, комедию, драму, триллер, фантастику, хоррор, романтику...",
    
    2: "⏱ Сколько времени у тебя есть на просмотр?\n\n"
       "• Короткий фильм (до 90 минут)\n"
       "• Средний фильм (90-120 минут)\n"
       "• Длинный фильм (120+ минут)",
    
    3: "🧠 Какую мозговую нагрузку предпочитаешь?\n\n"
       "• Легкий фильм (расслабиться и не думать)\n"
       "• Баланс (интересный, но не сложный)\n"
       "• Умный фильм (требует внимания и размышлений)",
    
    4: "💫 Что тебе интересно в фильмах?\n\n"
       "Например: космос, отношения, спецэффекты, экшн, философия, история, детективы, приключения...",
    
    5: "📅 Какой период кино предпочитаешь?\n\n"
       "• Классика (до 1990-х)\n"
       "• Золотое время (1990-2010)\n"
       "• Новинки (2010+)"
}


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Приветствие и начало диалога"""
    await state.clear()  # Очищаем предыдущее состояние
    
    greeting = (
        "🎬 Привет! Я бот **\"Чтосмотреть\"**! 🍿\n\n"
        "Помогу тебе выбрать идеальный фильм на вечер! "
        "Отвечу на 5 вопросов о твоих предпочтениях, "
        "и я порекомендую тебе отличные варианты.\n\n"
        "Готов начать? Давай узнаем, что посмотреть! 🎥✨"
    )
    
    await message.answer(greeting, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(1)  # Небольшая пауза для естественности
    
    # Задаём первый вопрос
    await message.answer(QUESTIONS[1], parse_mode=ParseMode.MARKDOWN)
    await state.set_state(MovieQuiz.question_1)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущего опроса"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять. Используй /start чтобы начать заново!")
        return
    
    await state.clear()
    await message.answer(
        "❌ Опрос отменён. Когда захочешь подобрать фильм — пиши /start!",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(MovieQuiz.question_1)
async def process_question_1(message: Message, state: FSMContext):
    """Обработка ответа на первый вопрос"""
    await state.update_data(answer_1=message.text)
    await message.answer(QUESTIONS[2], parse_mode=ParseMode.MARKDOWN)
    await state.set_state(MovieQuiz.question_2)


@dp.message(MovieQuiz.question_2)
async def process_question_2(message: Message, state: FSMContext):
    """Обработка ответа на второй вопрос"""
    await state.update_data(answer_2=message.text)
    await message.answer(QUESTIONS[3], parse_mode=ParseMode.MARKDOWN)
    await state.set_state(MovieQuiz.question_3)


@dp.message(MovieQuiz.question_3)
async def process_question_3(message: Message, state: FSMContext):
    """Обработка ответа на третий вопрос"""
    await state.update_data(answer_3=message.text)
    await message.answer(QUESTIONS[4], parse_mode=ParseMode.MARKDOWN)
    await state.set_state(MovieQuiz.question_4)


@dp.message(MovieQuiz.question_4)
async def process_question_4(message: Message, state: FSMContext):
    """Обработка ответа на четвёртый вопрос"""
    await state.update_data(answer_4=message.text)
    await message.answer(QUESTIONS[5], parse_mode=ParseMode.MARKDOWN)
    await state.set_state(MovieQuiz.question_5)


@dp.message(MovieQuiz.question_5)
async def process_question_5(message: Message, state: FSMContext):
    """Обработка последнего ответа и формирование рекомендаций"""
    await state.update_data(answer_5=message.text)
    
    # Получаем все ответы
    data = await state.get_data()
    
    # Формируем запрос к GigaChat
    user_request = f"""
Пользователь ответил на вопросы о предпочтениях для выбора фильма:

1. Настроение и жанр: {data['answer_1']}
2. Длительность: {data['answer_2']}
3. Мозговая нагрузка: {data['answer_3']}
4. Интересы: {data['answer_4']}
5. Период кино: {data['answer_5']}

Подбери 3-4 фильма, которые идеально подойдут под эти предпочтения.
"""
    
    system_prompt = """Ты ассистент чат-бота "Чтосмотреть". Твоя задача - рекомендовать фильмы на основе предпочтений пользователя.

Правила:
1. Предложи ровно 3-4 конкретных фильма
2. Для каждого фильма укажи:
   - Название (с годом выпуска)
   - Краткое описание (2-3 предложения)
   - Почему этот фильм подходит под запрос пользователя
3. Тон: Дружелюбный, энтузиастичный, помогающий
4. Используй эмодзи для оформления
5. Используй Markdown для форматирования (жирный текст для названий фильмов)
6. Язык: Русский

Формат ответа:
🎬 **Название фильма (год)**
Краткое описание фильма...
✨ Подходит потому что...

[повторить для каждого фильма]

В конце пожелай приятного просмотра! 🍿"""
    
    await message.chat.do("typing")
    
    try:
        # Отправляем запрос в GigaChat
        response = await ask_gigachat(user_request, system_prompt=system_prompt)
        
        # Очищаем состояние
        await state.clear()
        
        # Отправляем рекомендации
        intro = "🎯 Отлично! Вот что я подобрал для тебя:\n\n"
        await message.answer(intro + response, parse_mode=ParseMode.MARKDOWN)
        
        # Предлагаем начать заново
        await asyncio.sleep(2)
        await message.answer(
            "Хочешь подобрать ещё фильм? Просто напиши /start! 🎬",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        print(f"Ошибка при получении рекомендаций: {e}")
        await state.clear()
        await message.answer(
            "❌ Произошла ошибка при формировании рекомендаций. "
            "Попробуй начать заново с помощью /start",
            parse_mode=ParseMode.MARKDOWN
        )


@dp.message(F.text)
async def handle_other_messages(message: Message):
    """Обработка сообщений вне диалога"""
    await message.answer(
        "👋 Привет! Чтобы я помог тебе выбрать фильм, используй команду /start\n\n"
        "Я задам тебе 5 вопросов и подберу идеальные варианты для просмотра! 🎬",
        parse_mode=ParseMode.MARKDOWN
    )


async def main():
    print("🚀 Бот 'Чтосмотреть' запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
