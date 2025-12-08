import aiohttp
import os
import time
import uuid
from typing import List, Dict, Any

GIGA_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

TOKEN_CACHE: Dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def _is_token_valid() -> bool:
    return bool(TOKEN_CACHE["access_token"]) and time.time() < float(TOKEN_CACHE["expires_at"])


async def get_giga_token() -> str:
    if _is_token_valid():
        return str(TOKEN_CACHE["access_token"])

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {os.getenv('GIGA_CLIENT_BASIC')}",
    }
    data = "scope=GIGACHAT_API_PERS"

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.post(GIGA_OAUTH_URL, headers=headers, data=data) as resp:
            js = await resp.json()
            token = js["access_token"]
            expires_at = js.get("expires_at")
            expires_in = js.get("expires_in")

            if isinstance(expires_at, (int, float)):
                TOKEN_CACHE["expires_at"] = float(expires_at)
            elif expires_in:
                TOKEN_CACHE["expires_at"] = time.time() + float(expires_in) - 30
            else:
                TOKEN_CACHE["expires_at"] = time.time() + 25 * 60

            TOKEN_CACHE["access_token"] = token
            return token


async def chat_gigachat(messages: List[Dict[str, str]], *, temperature: float = 0.7) -> str:
    """
    Отправляет список сообщений (chat completions) в GigaChat.
    messages: [{'role': 'system'|'user'|'assistant', 'content': '...'}, ...]
    temperature: "температура" выборки модели, по умолчанию 0.7
    """
    token = await get_giga_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": "GigaChat",
        "temperature": temperature,
        "stream": False,
        "messages": messages,
    }

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.post(GIGA_CHAT_URL, headers=headers, json=payload) as resp:
            data = await resp.json(content_type=None)

            if resp.status != 200:
                raise RuntimeError(f"GigaChat HTTP {resp.status}: {data}")

            choices = data.get("choices")
            if not choices:
                raise RuntimeError(f"GigaChat response missing choices: {data}")

            return choices[0]["message"]["content"]