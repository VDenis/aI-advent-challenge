from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .mcp_http import MCPHttpClient
from .types import SearchResult


class BraveClient:
    def __init__(self, base_urls: Iterable[str]) -> None:
        self._client = MCPHttpClient(base_urls=base_urls, name="brave-search")

    async def search(self, query: str, count: int = 10, safesearch: str = "moderate") -> List[SearchResult]:
        result = await self._client.call_tool(
            "brave_web_search",
            {"query": query, "count": count, "safesearch": safesearch},
        )
        return self._parse_results(result)

    def _parse_results(self, payload: Dict[str, Any]) -> List[SearchResult]:
        structured = payload.get("structured") or payload.get("structuredContent") or payload.get("results")
        content = payload.get("content", [])

        candidates: List[Dict[str, Any]] = []
        if isinstance(structured, dict) and isinstance(structured.get("results"), list):
            candidates = structured["results"]
        elif isinstance(structured, list):
            candidates = structured
        elif isinstance(content, list):
            for entry in content:
                # MCP Streamable HTTP возвращает массив объектов вида {"type": "text", "text": "<json строка>"}.
                text = entry.get("text") if isinstance(entry, dict) else None
                if not text:
                    continue
                parsed = self._try_parse_json(text)
                if isinstance(parsed, list):
                    candidates.extend([r for r in parsed if isinstance(r, dict)])
                elif isinstance(parsed, dict):
                    candidates.append(parsed)

        results: List[SearchResult] = []
        for raw in candidates[:50]:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("name") or raw.get("url") or "Без названия")
            url = str(raw.get("url") or raw.get("link") or "")
            snippet = str(raw.get("snippet") or raw.get("description") or raw.get("text") or "")
            results.append(SearchResult(title=title, url=url, snippet=snippet))
        return results

    @staticmethod
    def _try_parse_json(text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    async def close(self) -> None:
        await self._client.close()
