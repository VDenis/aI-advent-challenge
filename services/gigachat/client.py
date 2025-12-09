"""Async client for the GigaChat API."""

import time
import uuid
from typing import Any, Dict, List, Optional

import aiohttp

from .config import GigaChatConfig


class GigaChatClient:
    """High-level client for interacting with the GigaChat API."""

    def __init__(self, config: Optional[GigaChatConfig] = None):
        self.config = config or GigaChatConfig()
        self._token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0.0}

    def _is_token_valid(self) -> bool:
        return bool(self._token_cache["access_token"]) and time.time() < float(self._token_cache["expires_at"])

    async def _fetch_token(self) -> str:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.config.basic_auth}",
        }
        data = f"scope={self.config.scope}"

        connector = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(self.config.oauth_url, headers=headers, data=data) as resp:
                js = await resp.json()
                token = js["access_token"]
                expires_at = js.get("expires_at")
                expires_in = js.get("expires_in")

                if isinstance(expires_at, (int, float)):
                    self._token_cache["expires_at"] = float(expires_at)
                elif expires_in:
                    self._token_cache["expires_at"] = time.time() + float(expires_in) - self.config.token_skew_seconds
                else:
                    # Default to 25 minutes if the response does not include expirations.
                    self._token_cache["expires_at"] = time.time() + 25 * 60

                self._token_cache["access_token"] = token
                return token

    async def get_token(self) -> str:
        """Return a valid OAuth token, refreshing it when necessary."""
        if self._is_token_valid():
            return str(self._token_cache["access_token"])
        return await self._fetch_token()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> str:
        """Send chat completion messages and return the assistant reply."""
        token = await self.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": model or self.config.model,
            "temperature": self.config.default_temperature if temperature is None else temperature,
            "stream": False,
            "messages": messages,
        }

        connector = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(self.config.chat_url, headers=headers, json=payload) as resp:
                data = await resp.json(content_type=None)

                if resp.status != 200:
                    raise RuntimeError(f"GigaChat HTTP {resp.status}: {data}")

                choices = data.get("choices")
                if not choices:
                    raise RuntimeError(f"GigaChat response missing choices: {data}")

                return choices[0]["message"]["content"]


default_client = GigaChatClient()


async def chat_gigachat(messages: List[Dict[str, str]], *, temperature: float = 0.7) -> str:
    """Convenience wrapper using the default client."""
    return await default_client.chat(messages, temperature=temperature)
