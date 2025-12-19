from __future__ import annotations

from typing import Dict, List, Optional

from .mcp_stdio import MCPStdioClient


class GigaChatSummaryClient:
    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None) -> None:
        self._client = MCPStdioClient(command=command, name="gigachat-summary", env=env)

    async def summarize(self, text: str, style: str = "concise", max_chars: int = 1200) -> str:
        result = await self._client.call_tool(
            "summarize",
            {"text": text, "style": style, "max_chars": max_chars},
        )
        return self._extract_text(result)

    def _extract_text(self, payload: Dict) -> str:
        structured = payload.get("structured") or payload.get("structuredContent")
        if isinstance(structured, dict) and structured.get("summary"):
            return str(structured["summary"])
        content = payload.get("content", [])
        for entry in content or []:
            if isinstance(entry, dict) and entry.get("type") == "text":
                return str(entry.get("text", "")).strip()
        if isinstance(payload, dict) and payload.get("text"):
            return str(payload["text"])
        return ""

    async def close(self) -> None:
        await self._client.close()
