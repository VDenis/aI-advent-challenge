from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .mcp_http import MCPHttpClient


class DesktopCommanderClient:
    def __init__(self, base_urls: Iterable[str]) -> None:
        self._client = MCPHttpClient(base_urls=base_urls, name="desktop-commander")

    async def write_file(self, path: str, content: str, mode: str = "w") -> Dict[str, Any]:
        return await self._client.call_tool("write_file", {"path": path, "content": content, "mode": mode})

    async def read_file(self, path: str) -> Dict[str, Any]:
        return await self._client.call_tool("read_file", {"path": path})

    async def list_directory(self, path: str) -> Dict[str, Any]:
        return await self._client.call_tool("list_directory", {"path": path})

    async def close(self) -> None:
        await self._client.close()
