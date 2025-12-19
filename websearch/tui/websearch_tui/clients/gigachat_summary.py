from __future__ import annotations

from typing import Dict, Iterable

from .mcp_http import MCPHttpClient


class GigaChatSummaryClient:
    def __init__(self, base_urls: Iterable[str]) -> None:
        self._client = MCPHttpClient(base_urls=base_urls, name="gigachat-summary")

    async def summarize(self, text: str, style: str = "concise", max_chars: int = 1200) -> str:
        result = await self._client.call_tool(
            "summarize",
            {"text": text, "style": style, "max_chars": max_chars},
        )
        return self._extract_text(result)

    def _extract_text(self, payload: Dict) -> str:
        # Сервер gigachat-summary возвращает {"summary": "...", ...} на верхнем уровне result
        result = payload.get("result", payload) if isinstance(payload, dict) else {}
        summary = result.get("summary")
        if summary:
            return str(summary)

        structured = result.get("structured") or result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("summary"):
            return str(structured["summary"])
        content = result.get("content", [])
        for entry in content or []:
            if isinstance(entry, dict) and entry.get("type") == "text":
                return str(entry.get("text", "")).strip()
        if isinstance(result, dict) and result.get("text"):
            return str(result["text"])
        return ""

    async def close(self) -> None:
        await self._client.close()
