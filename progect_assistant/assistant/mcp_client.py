import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional


class MCPStdioClient:
    """Minimal JSON-RPC MCP client over stdio."""

    def __init__(
        self,
        command: List[str],
        name: str,
        env: Optional[Dict[str, str]] = None,
        startup_timeout: float = 15.0,
        response_timeout: float = 25.0,
    ) -> None:
        self.command = self._normalize_command(command)
        self.name = name
        self.env = env or {}
        self.startup_timeout = startup_timeout
        self.response_timeout = response_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._initialized = False

    @staticmethod
    def _normalize_command(command: List[str]) -> List[str]:
        if not command:
            return command
        if command[0] == "python":
            return [sys.executable, *command[1:]]
        return command

    async def _ensure_started(self) -> None:
        if self._proc and self._proc.returncode is None:
            return

        env = os.environ.copy()
        env.update(self.env)

        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._initialized = False
        await self._initialize()

    async def _initialize(self) -> None:
        if self._initialized:
            return
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "progect-assistant", "version": "0.1.0"},
            },
        }
        self._next_id += 1
        await self._send_request(request, expect_result=True)
        self._initialized = True

    async def _send_request(self, payload: Dict[str, Any], expect_result: bool = True) -> Dict[str, Any]:
        await self._ensure_started()
        assert self._proc and self._proc.stdin and self._proc.stdout

        data = json.dumps(payload, ensure_ascii=True) + "\n"
        self._proc.stdin.write(data.encode())
        await self._proc.stdin.drain()

        if not expect_result:
            return {}

        deadline = time.monotonic() + self.response_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{self.name}: no response from {payload.get('method')}")

            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=remaining)
            if not line:
                raise RuntimeError(f"{self.name}: process exited before response")
            text = line.decode(errors="ignore").strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if message.get("id") == payload.get("id"):
                if "error" in message:
                    raise RuntimeError(f"{self.name}: {message['error']}")
                return message.get("result", message)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        self._next_id += 1
        result = await self._send_request(request)
        if isinstance(result, dict):
            return result
        return {"content": result}

    async def list_tools(self) -> List[Dict[str, Any]]:
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/list",
            "params": {},
        }
        self._next_id += 1
        result = await self._send_request(request)
        return result.get("tools", []) if isinstance(result, dict) else []

    async def close(self) -> None:
        if not self._proc:
            return
        if self._proc.stdin and not self._proc.stdin.is_closing():
            self._proc.stdin.close()
        await self._proc.wait()


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)
