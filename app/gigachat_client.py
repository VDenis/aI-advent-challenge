import aiohttp
import os
import uuid

GIGA_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

async def get_giga_token():
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {os.getenv('GIGA_CLIENT_BASIC')}",
    }
    data = "scope=GIGACHAT_API_PERS"

    async with aiohttp.ClientSession() as session:
        async with session.post(GIGA_OAUTH_URL, headers=headers, data=data) as resp:
            js = await resp.json()
            return js["access_token"]

async def ask_gigachat(user_text: str, system_prompt: str = None, return_full: bool = False):
    """
    Отправляет запрос в GigaChat API.
    
    Args:
        user_text: Текст запроса пользователя
        system_prompt: Системный промпт (если None, используется базовый)
        return_full: Если True, возвращает полный JSON ответ,
                     если False, возвращает только текст ответа
    
    Returns:
        dict или str в зависимости от параметра return_full
    """
    token = await get_giga_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    if system_prompt is None:
        system_prompt = "Ты дружелюбный Telegram-бот, отвечай кратко и по делу. Используй Markdown для форматирования текста (жирный **текст**, курсив *текст*, код `код`)."
    
    payload = {
        "model": "GigaChat",
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(GIGA_CHAT_URL, headers=headers, json=payload) as resp:
            js = await resp.json()
            if return_full:
                return js
            else:
                return js["choices"][0]["message"]["content"]