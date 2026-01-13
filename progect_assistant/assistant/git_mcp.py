import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

from .mcp_client import MCPStdioClient, run_async
from .mcp_config import resolve_mcp_entry


@dataclass
class GitStatus:
    branch: str
    changed_files: List[str]


class GitMCPAdapter:
    """MCP-compatible adapter for git context.

    This keeps the API stable for a real MCP client swap later.
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        entry = resolve_mcp_entry(
            project_root,
            "git",
            fallback_command=os.environ.get(
                "GIT_MCP_COMMAND",
                "python -m progect_assistant.git_mcp_server",
            ),
        )
        self._mcp_command = entry.get("command", "")
        self._mcp_env = entry.get("env", {})
        self._client_key = (self._mcp_command, self.project_root)

    _clients: Dict[tuple, MCPStdioClient] = {}

    def status(self) -> GitStatus:
        if self._mcp_command:
            data = self._call_mcp_tool("git_status", {})
            return GitStatus(
                branch=str(data.get("branch", "unknown")),
                changed_files=list(data.get("changed_files", [])),
            )
        return self._local_status()

    async def status_async(self) -> GitStatus:
        if self._mcp_command:
            data = await self._call_mcp_tool_async("git_status", {})
            return GitStatus(
                branch=str(data.get("branch", "unknown")),
                changed_files=list(data.get("changed_files", [])),
            )
        return self._local_status()

    def diff(self, max_lines: int = 200) -> str:
        if self._mcp_command:
            data = self._call_mcp_tool("git_diff", {"max_lines": max_lines})
            return str(data.get("output", ""))
        return self._local_diff(max_lines)

    async def diff_async(self, max_lines: int = 200) -> str:
        if self._mcp_command:
            data = await self._call_mcp_tool_async("git_diff", {"max_lines": max_lines})
            return str(data.get("output", ""))
        return self._local_diff(max_lines)

    def read_file_snippet(self, path: str, start_line: int, end_line: int) -> str:
        if self._mcp_command:
            data = self._call_mcp_tool(
                "read_file_snippet",
                {"path": path, "start_line": start_line, "end_line": end_line},
            )
            return str(data.get("output", ""))
        return self._local_read(path, start_line, end_line)

    async def read_file_snippet_async(self, path: str, start_line: int, end_line: int) -> str:
        if self._mcp_command:
            data = await self._call_mcp_tool_async(
                "read_file_snippet",
                {"path": path, "start_line": start_line, "end_line": end_line},
            )
            return str(data.get("output", ""))
        return self._local_read(path, start_line, end_line)

    def _local_status(self) -> GitStatus:
        result = self._run(["git", "status", "--porcelain", "-b"])
        lines = result.strip().splitlines()
        branch = "unknown"
        changed: List[str] = []
        for line in lines:
            if line.startswith("##"):
                branch = line.replace("##", "").strip()
            else:
                parts = line.split()
                if parts:
                    changed.append(parts[-1])
        return GitStatus(branch=branch, changed_files=changed)

    def _local_diff(self, max_lines: int) -> str:
        diff = self._run(["git", "diff", "--unified=3"])
        lines = diff.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("...diff truncated...")
        return "\n".join(lines)

    def _local_read(self, path: str, start_line: int, end_line: int) -> str:
        safe_path = os.path.normpath(os.path.join(self.project_root, path))
        if not safe_path.startswith(os.path.abspath(self.project_root)):
            raise ValueError("Path escapes project root")
        with open(safe_path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
        start = max(start_line - 1, 0)
        end = min(end_line, len(lines))
        return "".join(lines[start:end])

    def _call_mcp_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._mcp_command:
            raise RuntimeError("MCP command is not configured")
        client = self._ensure_client()
        result = run_async(client.call_tool(name, arguments))
        return self._unwrap_mcp_result(result)

    async def _call_mcp_tool_async(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._mcp_command:
            raise RuntimeError("MCP command is not configured")
        client = self._ensure_client()
        result = await client.call_tool(name, arguments)
        return self._unwrap_mcp_result(result)

    def _unwrap_mcp_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if "content" not in result:
            return result
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                if "json" in first:
                    return first["json"]
                if "text" in first:
                    try:
                        return json.loads(first["text"])
                    except json.JSONDecodeError:
                        return {"output": first["text"]}
        return {"output": str(content)}

    def _ensure_client(self) -> MCPStdioClient:
        client = self._clients.get(self._client_key)
        if client:
            return client
        command = shlex.split(self._mcp_command)
        client = MCPStdioClient(
            command=command,
            name="git-mcp",
            env={"GIT_MCP_PROJECT_ROOT": self.project_root, **self._mcp_env},
        )
        self._clients[self._client_key] = client
        return client

    def _run(self, args: List[str]) -> str:
        result = subprocess.run(
            args,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git command failed")
        return result.stdout


def close_all_clients() -> None:
    for client in list(GitMCPAdapter._clients.values()):
        try:
            run_async(client.close())
        except Exception:
            pass
    GitMCPAdapter._clients.clear()
