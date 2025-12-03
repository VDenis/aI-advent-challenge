import asyncio
import os
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from gigachat_client import ask_gigachat

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище настроек пользователей: {user_id: "text" или "json"}
user_settings = {}

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_settings[message.from_user.id] = "text"  # По умолчанию текстовый режим
    await message.answer(
        "🤖 Привет! Напиши мне сообщение, я спрошу GigaChat и пришлю ответ.\n\n"
        "📝 Используй /format для выбора формата ответа (текст или JSON)."
    )

@dp.message(Command("format"))
async def cmd_format(message: Message):
    user_id = message.from_user.id
    current_format = user_settings.get(user_id, "text")
    
    # Переключаем режим
    new_format = "json" if current_format == "text" else "text"
    user_settings[user_id] = new_format
    
    format_emoji = "📝" if new_format == "text" else "🔧"
    format_name = "Текст с форматированием" if new_format == "text" else "JSON"
    
    await message.answer(
        f"{format_emoji} Формат ответа изменён на: **{format_name}**\n\n"
        f"Текущий режим: `{new_format}`",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(F.text)
async def handle_message(message: Message):
    await message.chat.do("typing")
    try:
        user_id = message.from_user.id
        response_format = user_settings.get(user_id, "text")
        
        # Получаем полный ответ от GigaChat
        full_response = await ask_gigachat(message.text, return_full=True)
        
        if response_format == "json":
            # Отправляем JSON
            json_str = json.dumps(full_response, ensure_ascii=False, indent=2)
            await message.answer(f"```json\n{json_str}\n```", parse_mode=ParseMode.MARKDOWN)
        else:
            # Отправляем текст с форматированием (Markdown)
            answer_text = full_response["choices"][0]["message"]["content"]
            await message.answer(answer_text, parse_mode=ParseMode.MARKDOWN)
            
    except Exception as e:
        print(f"Ошибка: {e}")  # в консоль для отладки
        await message.answer("❌ Произошла ошибка при обращении к GigaChat. Попробуй ещё раз позже.")

async def main():
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
