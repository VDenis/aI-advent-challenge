"""MCP server exposing support service tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

try:
    # Prefer standalone fastmcp package; fall back to mcp bundled version if missing.
    from fastmcp import FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

from progect_assistant.assistant.core import ToolContext
from progect_assistant.assistant.tools import (
    CreateTicketTool,
    FindSimilarTicketsTool,
    GetTicketTool,
    GetUserContextTool,
    SearchFAQTool,
    SearchTicketsTool,
    UpdateTicketTool,
)

PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())
CACHE_PATH = os.environ.get(
    "ASSISTANT_CACHE_PATH",
    str(Path("progect_assistant") / ".cache" / "rag_index.json"),
)

mcp = FastMCP("support-assistant")


def _execute_tool(tool, params: Dict) -> Dict:
    """Helper to execute a tool with proper context."""
    context = ToolContext(project_root=PROJECT_ROOT, request_id="mcp")
    return tool.execute(params, context)


@mcp.tool()
async def search_faq(query: str, top_k: int = 3) -> Dict:
    """Search FAQ entries for answers to common questions."""
    tool = SearchFAQTool()
    return _execute_tool(tool, {"query": query, "top_k": top_k})


@mcp.tool()
async def get_ticket(ticket_id: str) -> Dict:
    """Get detailed information about a support ticket."""
    tool = GetTicketTool()
    return _execute_tool(tool, {"ticket_id": ticket_id})


@mcp.tool()
async def create_ticket(
    user_id: str,
    subject: str,
    description: str,
    priority: str = "medium",
    tags: Optional[List[str]] = None,
) -> Dict:
    """Create a new support ticket."""
    tool = CreateTicketTool()
    params = {
        "user_id": user_id,
        "subject": subject,
        "description": description,
        "priority": priority,
        "tags": tags or [],
    }
    return _execute_tool(tool, params)


@mcp.tool()
async def update_ticket(
    ticket_id: str,
    status: Optional[str] = None,
    comment: Optional[str] = None,
    comment_author: str = "support",
    resolution: Optional[str] = None,
) -> Dict:
    """Update ticket status or add a comment."""
    tool = UpdateTicketTool()
    params = {
        "ticket_id": ticket_id,
        "status": status,
        "comment": comment,
        "comment_author": comment_author,
        "resolution": resolution,
    }
    return _execute_tool(tool, params)


@mcp.tool()
async def search_tickets(
    query: str = "",
    status: Optional[str] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
) -> Dict:
    """Search support tickets by text, status, or tags."""
    tool = SearchTicketsTool()
    params = {
        "query": query,
        "status": status,
        "tags": tags or [],
        "user_id": user_id,
    }
    return _execute_tool(tool, params)


@mcp.tool()
async def get_user_context(user_id: str) -> Dict:
    """Retrieve user profile and their support ticket history."""
    tool = GetUserContextTool()
    return _execute_tool(tool, {"user_id": user_id})


@mcp.tool()
async def find_similar_tickets(description: str, top_k: int = 5) -> Dict:
    """Find similar resolved tickets that might help solve current issue."""
    tool = FindSimilarTicketsTool()
    return _execute_tool(tool, {"description": description, "top_k": top_k})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
