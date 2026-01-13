from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from mcp.server.fastmcp import FastMCP

from progect_assistant.assistant.git_mcp import GitMCPAdapter
from progect_assistant.assistant.help import build_help_response
from progect_assistant.assistant.rag import RagIndexer, RagSearch

PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())
CACHE_PATH = os.environ.get(
    "ASSISTANT_CACHE_PATH",
    str(Path("progect_assistant") / ".cache" / "rag_index.json"),
)

mcp = FastMCP("developer-assistant")


def _rag_search() -> RagSearch:
    indexer = RagIndexer(PROJECT_ROOT, CACHE_PATH)
    index = indexer.load_or_build()
    return RagSearch(index)


@mcp.tool()
async def rag_search(query: str, top_k: int = 5) -> Dict:
    """Search project docs/configs using RAG and return citations."""
    searcher = _rag_search()
    results = []
    for score, chunk in searcher.search(query, top_k=top_k):
        results.append(
            {
                "score": round(score, 4),
                "path": chunk.path,
                "section": chunk.section,
                "snippet": chunk.text[:300],
            }
        )
    return {"query": query, "results": results}


@mcp.tool()
async def index_rag() -> Dict:
    """Build or refresh the RAG index."""
    RagIndexer(PROJECT_ROOT, CACHE_PATH).build_index()
    return {"status": "ok"}


@mcp.tool()
async def help(topic: str) -> Dict:
    """Answer project questions with citations via RAG + git context."""
    searcher = _rag_search()
    git = await GitMCPAdapter(PROJECT_ROOT).status_async()
    return build_help_response(topic, searcher, {"branch": git.branch})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
