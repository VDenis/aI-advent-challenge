from __future__ import annotations

import os
import textwrap
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("gigachat-summary")

GIGACHAT_API_URL = os.getenv(
    "GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
)
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() not in {"0", "false", "no"}
REQUEST_TIMEOUT = float(os.getenv("GIGACHAT_TIMEOUT", "15"))


def _fallback_summary(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    return textwrap.shorten(cleaned, width=max_chars, placeholder="...")


async def _ask_gigachat(text: str, style: str, max_chars: int) -> Dict[str, Any]:
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key:
        return {"summary": _fallback_summary(text, max_chars), "source": "fallback"}

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
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(REQUEST_TIMEOUT)

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=VERIFY_SSL) as client:
            response = await client.post(GIGACHAT_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "summary": _fallback_summary(text, max_chars),
            "source": "fallback",
            "error": str(exc),
        }

    choices = data.get("choices") or []
    summary_text = ""
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        summary_text = message.get("content") or message.get("text") or ""

    if not summary_text:
        summary_text = _fallback_summary(text, max_chars)
    return {"summary": summary_text.strip(), "source": "gigachat"}


@mcp.tool()
async def summarize(text: str, style: str = "concise", max_chars: int = 1200) -> Dict[str, Any]:
    """Краткое саммари текста. Возвращает summary и источник (gigachat/fallback)."""
    max_chars = max(200, int(max_chars or 1200))
    result = await _ask_gigachat(text, style, max_chars)
    result["requested_max_chars"] = max_chars
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
