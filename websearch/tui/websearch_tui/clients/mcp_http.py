from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Iterable, List

import httpx


class MCPHttpClient:
    """Минимальный HTTP JSON-RPC клиент MCP (initialize + tools/list + tools/call)."""

    def __init__(
        self,
        base_urls: Iterable[str],
        name: str,
        timeout: float = 20.0,
    ) -> None:
        self.base_urls = [u.rstrip("/") for u in base_urls]
        self.name = name
        self.timeout = timeout
        self._next_id = 1
        self._initialized = False
        self._session_id: str | None = None
        # Streamable HTTP MCP требует Accept с поддержкой SSE (text/event-stream)
        self._client = httpx.AsyncClient(timeout=self.timeout)
        self._lock = asyncio.Lock()

    @staticmethod
    def _parse_sse_payload(raw: str) -> Dict[str, Any]:
        """Простой разбор text/event-stream с JSON-RPC ответами."""
        events: List[str] = []
        current: List[str] = []

        for line in raw.splitlines():
            if line.startswith("data:"):
                current.append(line[len("data:"):].strip())
            elif line.strip() == "":
                if current:
                    joined = "\n".join(current).strip()
                    if joined:
                        events.append(joined)
                    current = []
        if current:
            joined = "\n".join(current).strip()
            if joined:
                events.append(joined)

        if not events:
            raise RuntimeError("Empty SSE response from MCP server")

        for event in reversed(events):
            try:
                return json.loads(event)
            except Exception:
                continue
        raise RuntimeError("Failed to parse SSE JSON payload from MCP server")

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        for base in self.base_urls:
            try:
                headers = {
                    "Accept": "application/json, text/event-stream",
                    "Mcp-Protocol-Version": "2024-11-05",
                }
                if self._session_id:
                    headers["Mcp-Session-Id"] = self._session_id

                response = await self._client.post(base, json=payload, headers=headers)
                response.raise_for_status()

                # Захватываем session-id, если сервер его вернул
                session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
                if session_id:
                    self._session_id = session_id

                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    data = self._parse_sse_payload(response.text)
                else:
                    data = response.json()
                if "error" in data:
                    raise RuntimeError(f"{self.name}: {data['error']}")
                return data
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{base}: {exc}")
                continue
        raise RuntimeError(f"{self.name}: all connection attempts failed: {'; '.join(errors)}")

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            req_id = self._next_id
            self._next_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "websearch-tui", "version": "0.1.0"},
                },
            }
            await self._post(payload)
            self._initialized = True

    async def list_tools(self) -> List[Dict[str, Any]]:
        await self._ensure_initialized()
        req_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": req_id, "method": "tools/list"}
        data = await self._post(payload)
        result = data.get("result", data)
        return result.get("tools", []) if isinstance(result, dict) else []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_initialized()
        req_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        data = await self._post(payload)
        result = data.get("result", data)
        if isinstance(result, dict):
            return result
        return {"content": result}

    async def close(self) -> None:
        await self._client.aclose()
