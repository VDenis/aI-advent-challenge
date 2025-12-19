from __future__ import annotations

import os
import uuid
import base64
import binascii
import time
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

load_dotenv()

app = FastAPI()

def _normalize_api_url(raw: str | None) -> str:
    """Убеждаемся, что в URL есть путь /api/v1/chat/completions."""
    default = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    if not raw:
        return default
    raw = raw.strip()
    if raw.endswith("/chat/completions"):
        return raw
    if raw.endswith("/api/v1"):
        return raw.rstrip("/") + "/chat/completions"
    if raw.endswith("/api/v1/"):
        return raw + "chat/completions"
    if raw.endswith("/"):
        return raw + "api/v1/chat/completions"
    # если указали только домен без слеша
    if raw.count("/") < 3:
        return raw + "/api/v1/chat/completions"
    return raw


GIGACHAT_API_URL = _normalize_api_url(os.getenv("GIGACHAT_API_URL"))
GIGACHAT_AUTH_URL = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() not in {"0", "false", "no"}
REQUEST_TIMEOUT = float(os.getenv("GIGACHAT_TIMEOUT", "15"))
_CACHED_TOKEN: dict[str, Any] = {"value": None, "exp": 0.0}


def _maybe_decode_basic(raw: str) -> tuple[str, str] | None:
    """Если raw — это base64(client_id:secret), вернём пару."""
    try:
        decoded = base64.b64decode(raw, validate=True).decode()
        if ":" in decoded:
            client_id, client_secret = decoded.split(":", 1)
            if client_id and client_secret:
                return client_id, client_secret
    except (binascii.Error, UnicodeDecodeError):
        pass
    return None


def _fallback_summary(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max(0, max_chars - 3)] + "..."


async def _fetch_oauth_token(client_id: str, client_secret: str, scope: str) -> tuple[str, int]:
    """Получаем OAuth-токен GigaChat по client_credentials."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        # Требуется сервисом GigaChat для аутентификации
        "RqUID": os.getenv("GIGACHAT_RQUID", str(uuid.uuid4())),
    }
    data = {"scope": scope, "grant_type": "client_credentials"}
    timeout = httpx.Timeout(REQUEST_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, verify=VERIFY_SSL) as client:
        resp = await client.post(GIGACHAT_AUTH_URL, headers=headers, data=data)
        resp.raise_for_status()
        payload = resp.json()
    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 600)
    if not token:
        raise RuntimeError("GigaChat auth: access_token missing")
    return token, expires_in


async def _get_api_key() -> str:
    """Ключ/токен из env или client_id/secret -> OAuth (кэшируем)."""
    if _CACHED_TOKEN["value"] and _CACHED_TOKEN["exp"] > time.time() + 30:
        return str(_CACHED_TOKEN["value"])

    direct = (os.getenv("GIGACHAT_API_KEY") or os.getenv("GIGACHAT_TOKEN") or "").strip()
    if direct:
        _CACHED_TOKEN["value"] = direct
        _CACHED_TOKEN["exp"] = time.time() + 3600 * 24  # кэшируем на сутки
        return direct

    client_id = os.getenv("GIGACHAT_CLIENT_ID")
    client_secret = os.getenv("GIGACHAT_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Set GIGACHAT_API_KEY or GIGACHAT_TOKEN or client_id/secret")

    token, expires_in = await _fetch_oauth_token(client_id, client_secret, GIGACHAT_SCOPE)
    _CACHED_TOKEN["value"] = token
    _CACHED_TOKEN["exp"] = time.time() + max(60, expires_in - 30)
    return token


async def _ask_gigachat(text: str, style: str, max_chars: int) -> Dict[str, Any]:
    raw_env_key = (os.getenv("GIGACHAT_API_KEY") or os.getenv("GIGACHAT_TOKEN") or "").strip()
    basic_creds = _maybe_decode_basic(raw_env_key) if raw_env_key else None

    async def _request_with_token(token: str) -> Dict[str, Any]:
        payload = {
            "model": GIGACHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": f"Ты ассистент, делаешь краткое русскоязычное саммари. Стиль: {style}. Ограничение {max_chars} символов.",
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "max_tokens": max(128, min(2048, max_chars // 2)),
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(REQUEST_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout, verify=VERIFY_SSL) as client:
            response = await client.post(GIGACHAT_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        summary_text = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            summary_text = message.get("content") or message.get("text") or ""
        if not summary_text:
            raise RuntimeError("Empty response from GigaChat")
        return {"summary": summary_text.strip(), "source": "gigachat"}

    # 1) Пробуем прямой Bearer из env
    if raw_env_key:
        try:
            return await _request_with_token(raw_env_key)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401 or not basic_creds:
                raise
            # 401 и есть base64(id:secret) — попробуем OAuth ниже
        except Exception:
            # другая ошибка — дадим шанс OAuth/client_id
            pass

    # 2) Если есть base64(id:secret) или client_id/secret в env — берём OAuth токен и повторяем
    client_id = os.getenv("GIGACHAT_CLIENT_ID")
    client_secret = os.getenv("GIGACHAT_CLIENT_SECRET")
    if basic_creds:
        client_id, client_secret = basic_creds
    if client_id and client_secret:
        token, expires_in = await _fetch_oauth_token(client_id, client_secret, GIGACHAT_SCOPE)
        _CACHED_TOKEN["value"] = token
        _CACHED_TOKEN["exp"] = time.time() + max(60, expires_in - 30)
        return await _request_with_token(token)

    # 3) Последний шанс — кэш/другие токены (если заданы напрямую в env и не давали 401)
    api_key = await _get_api_key()
    return await _request_with_token(api_key)


async def handle_initialize(req_id: Any) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "gigachat-summary", "version": "0.1.0"},
            "capabilities": {},
        },
    }


async def handle_tools_list(req_id: Any) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": "summarize",
                    "description": "Краткое саммари текста",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "style": {"type": "string", "default": "concise"},
                            "max_chars": {"type": "integer", "default": 1200},
                        },
                        "required": ["text"],
                    },
                }
            ]
        },
    }


async def handle_tools_call(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name != "summarize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool {name}"},
        }
    text = str(arguments.get("text") or "")
    style = str(arguments.get("style") or "concise")
    max_chars = int(arguments.get("max_chars") or 1200)
    max_chars = max(200, max_chars)
    try:
        result = await _ask_gigachat(text, style, max_chars)
        result["requested_max_chars"] = max_chars
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": f"GigaChat summarize failed: {exc}",
                "data": {
                    "url": GIGACHAT_API_URL,
                },
            },
        }


@app.post("/")
@app.post("/mcp")
async def rpc_root(payload: Dict[str, Any]) -> JSONResponse:
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        resp = await handle_initialize(req_id)
    elif method == "tools/list":
        resp = await handle_tools_list(req_id)
    elif method == "tools/call":
        resp = await handle_tools_call(req_id, params)
    else:
        resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
    return JSONResponse(resp)


@app.get("/ping")
async def ping() -> Dict[str, str]:
    return {"message": "pong"}
