from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from typing import Any, Dict, List, Optional


class MCPStdioClient:
    """Минимальный JSON-RPC клиент поверх stdio процесса."""

    def __init__(
        self,
        command: List[str],
        name: str,
        env: Optional[Dict[str, str]] = None,
        startup_timeout: float = 15.0,
        response_timeout: float = 25.0,
    ) -> None:
        self.command = command
        self.name = name
        self.env = env or {}
        self.startup_timeout = startup_timeout
        self.response_timeout = response_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._initialized = False
        self._stderr_task: asyncio.Task | None = None

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
        if self._proc.stderr:
            self._stderr_task = asyncio.create_task(self._drain_stderr())

        await self._initialize()

    async def _drain_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    return
        except asyncio.CancelledError:  # pragma: no cover
            return

    async def _initialize(self) -> None:
        if self._initialized:
            return
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "websearch-tui", "version": "0.1.0"},
            },
        }
        self._next_id += 1
        await self._send_request(request, expect_result=True)
        self._initialized = True

    async def _send_request(self, payload: Dict[str, Any], expect_result: bool = True) -> Dict[str, Any]:
        await self._ensure_started()
        assert self._proc and self._proc.stdin and self._proc.stdout

        data = json.dumps(payload, ensure_ascii=False) + "\n"
        self._proc.stdin.write(data.encode())
        await self._proc.stdin.drain()

        if not expect_result:
            return {}

        deadline = time.monotonic() + self.response_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{self.name}: не дождались ответа {payload.get('method')}")

            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=remaining)
            if not line:
                raise RuntimeError(f"{self.name}: процесс завершился до ответа")
            text = line.decode(errors="ignore").strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                # пропускаем мусор
                continue
            if message.get("id") == payload.get("id"):
                if "error" in message:
                    raise RuntimeError(f"{self.name}: {message['error']}")
                return message.get("result", message)
            # игнорируем уведомления/другие ответы

    async def list_tools(self) -> List[Dict[str, Any]]:
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/list",
        }
        self._next_id += 1
        result = await self._send_request(request)
        return result.get("tools", []) if isinstance(result, dict) else []

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

    async def close(self) -> None:
        if not self._proc:
            return
        try:
            if self._proc.stdin and not self._proc.stdin.is_closing():
                try:
                    # Попробуем завершить по-протокольно
                    shutdown_payload = {
                        "jsonrpc": "2.0",
                        "id": self._next_id,
                        "method": "shutdown",
                    }
                    self._next_id += 1
                    data = json.dumps(shutdown_payload) + "\n"
                    self._proc.stdin.write(data.encode())
                    await self._proc.stdin.drain()
                except Exception:
                    pass
                self._proc.stdin.close()
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except Exception:
            if self._proc.returncode is None:
                self._proc.kill()
        if self._stderr_task:
            self._stderr_task.cancel()
            with contextlib.suppress(Exception):
                await self._stderr_task
