from __future__ import annotations

from typing import Any, Dict, List, Optional

from .mcp_stdio import MCPStdioClient


class DesktopCommanderClient:
    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None) -> None:
        self._client = MCPStdioClient(command=command, name="desktop-commander", env=env)

    async def write_file(self, path: str, content: str, mode: str = "w") -> Dict[str, Any]:
        return await self._client.call_tool("write_file", {"path": path, "content": content, "mode": mode})

    async def read_file(self, path: str) -> Dict[str, Any]:
        return await self._client.call_tool("read_file", {"path": path})

    async def list_directory(self, path: str) -> Dict[str, Any]:
        return await self._client.call_tool("list_directory", {"path": path})

    async def close(self) -> None:
        await self._client.close()
