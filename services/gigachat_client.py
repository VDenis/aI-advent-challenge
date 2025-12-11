"""Async GigaChat client built on aiohttp."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import aiohttp


logger = logging.getLogger(__name__)

DEFAULT_SCOPE = "GIGACHAT_API_PERS"


@dataclass
class GigaChatClientConfig:
    """Configuration for GigaChatClient."""

    basic_auth: str
    chat_url: str
    oauth_url: str
    model: str
    request_timeout: float = 60.0
    verify_ssl: bool = True
    scope: str = DEFAULT_SCOPE
    temperature: float = 0.7
    token_skew_seconds: float = 30.0


class GigaChatClient:
    """High-level async client for the GigaChat API."""

    def __init__(self, config: GigaChatClientConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        connector = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
        self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    def _token_valid(self) -> bool:
        return bool(self._token) and time.time() < self._token_expires_at

    async def _fetch_token(self) -> str:
        logger.debug("Fetching new GigaChat OAuth token")
        payload = {"scope": self.config.scope}
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.config.basic_auth}",
        }

        session = await self._get_session()
        async with session.post(self.config.oauth_url, headers=headers, data=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"Failed to obtain token: HTTP {resp.status} {data}")

        token = str(data["access_token"])
        expires_in = float(data.get("expires_in", 0.0))
        expires_at = float(data.get("expires_at", 0.0))

        if expires_at:
            self._token_expires_at = expires_at - self.config.token_skew_seconds
        elif expires_in:
            self._token_expires_at = time.time() + expires_in - self.config.token_skew_seconds
        else:
            # Default to 25 minutes.
            self._token_expires_at = time.time() + 25 * 60

        self._token = token
        logger.debug("Token fetched, expires_at=%s", self._token_expires_at)
        return token

    async def _get_token(self) -> str:
        if self._token_valid():
            return str(self._token)

        async with self._token_lock:
            if self._token_valid():
                return str(self._token)
            return await self._fetch_token()

    async def chat(
        self,
        messages: Iterable[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Send a chat completion request.

        Args:
            messages: OpenAI-style message list.
            temperature: Optional temperature override.
            model: Optional model override.

        Returns:
            Tuple of assistant content and raw response metadata (usage if present).
        """
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model or self.config.model,
            "temperature": self.config.temperature if temperature is None else temperature,
            "stream": False,
            "messages": list(messages),
        }

        session = await self._get_session()
        async with session.post(self.config.chat_url, headers=headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise RuntimeError(f"GigaChat HTTP {resp.status}: {data}")

        choices = data.get("choices")
        if not choices:
            raise RuntimeError(f"Unexpected GigaChat response: {data}")

        message = choices[0]["message"]
        return str(message["content"]), data

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "GigaChatClient":
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
