import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from dotenv import load_dotenv

from gigachat_client import ask_gigachat

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("🤖 Привет! Напиши мне сообщение, я спрошу GigaChat и пришлю ответ.")

@dp.message(F.text)
async def handle_message(message: Message):
    await message.chat.do("typing")
    try:
        answer = await ask_gigachat(message.text)
        await message.answer(answer)
    except Exception as e:
        print(f"Ошибка: {e}")  # в консоль для отладки
        await message.answer("❌ Произошла ошибка при обращении к GigaChat. Попробуй ещё раз позже.")

async def main():
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
