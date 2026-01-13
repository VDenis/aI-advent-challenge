from typing import Dict, List, Tuple

from .rag import RagSearch
from .tools import ToolContext


def build_help_response(
    topic: str,
    rag_search: RagSearch,
    git_status: Dict[str, str],
    max_items: int = 5,
) -> Dict[str, str]:
    hits: List[Tuple[float, str]] = []
    for score, chunk in rag_search.search(topic, top_k=max_items):
        snippet = chunk.text[:300].strip().replace("\n", " ")
        hits.append((score, f"- {chunk.path} [{chunk.section}]: {snippet}"))

    if not hits:
        return {
            "summary": "No documentation or code snippets found for this topic.",
            "details": "Try a different topic or run /index to refresh the RAG index.",
        }

    citations = "\n".join(item for _, item in hits)
    return {
        "summary": f"Found {len(hits)} relevant sources for '{topic}'.",
        "details": (
            f"Branch: {git_status.get('branch', 'unknown')}\n"
            f"Sources:\n{citations}"
        ),
    }


def help_menu() -> str:
    return (
        "Developer Assistant commands:\n"
        "- /index: build or refresh RAG index\n"
        "- /help <topic>: ask about setup, style, architecture, API\n"
        "- /tool <name> <json>: call a tool directly\n"
        "- /mcp list: list MCP tools\n"
        "- /mcp call <tool> <json>: call MCP tool directly\n"
        "- /exit: quit"
    )
