"""MCP integration helpers (client, config resolution, git adapter)."""

from .client import MCPStdioClient, run_async
from .config import load_mcp_config, resolve_mcp_entry
from .git_adapter import GitMCPAdapter, GitStatus, close_all_clients

__all__ = [
    "MCPStdioClient",
    "run_async",
    "load_mcp_config",
    "resolve_mcp_entry",
    "GitMCPAdapter",
    "GitStatus",
    "close_all_clients",
]
