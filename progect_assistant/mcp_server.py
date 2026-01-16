from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
try:
    # Prefer standalone fastmcp package; fall back to mcp bundled version if missing.
    from fastmcp import FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

from progect_assistant.assistant.github import (
    DEFAULT_GITHUB_API_BASE,
    DEFAULT_GITHUB_LABELS,
    GitHubClient,
    GitHubError,
    format_issue_from_conversation,
)
from progect_assistant.assistant.help import build_help_response
from progect_assistant.assistant.mcp import GitMCPAdapter
from progect_assistant.assistant.rag import RagIndexer, RagSearch

PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())
CACHE_PATH = os.environ.get(
    "ASSISTANT_CACHE_PATH",
    str(Path("progect_assistant") / ".cache" / "rag_index.json"),
)

# Load environment from .env if present so MCP tools have GitHub creds, etc.
load_dotenv(dotenv_path=Path(PROJECT_ROOT) / ".env", override=False)

mcp = FastMCP("developer-assistant")


def _rag_search() -> RagSearch:
    indexer = RagIndexer(PROJECT_ROOT, CACHE_PATH)
    index = indexer.load_or_build()
    return RagSearch(index)


def _parse_label_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return None


def _default_github_labels() -> List[str]:
    raw = os.environ.get("GITHUB_DEFAULT_LABELS", "").strip()
    if raw:
        parsed = _parse_label_list(raw)
        return parsed or []
    return list(DEFAULT_GITHUB_LABELS)


def _resolve_github_repo(
    owner: Optional[str], repo: Optional[str], repository: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    resolved_owner = owner
    resolved_repo = repo

    repo_env = repository or os.environ.get("GITHUB_REPOSITORY", "")
    if repo_env and (not resolved_owner or not resolved_repo):
        if "/" in repo_env:
            env_owner, env_repo = repo_env.split("/", 1)
            resolved_owner = resolved_owner or env_owner
            resolved_repo = resolved_repo or env_repo

    resolved_owner = resolved_owner or os.environ.get("GITHUB_OWNER")
    resolved_repo = resolved_repo or os.environ.get("GITHUB_REPO")

    return (str(resolved_owner) if resolved_owner else None), (str(resolved_repo) if resolved_repo else None)


def _github_base_url(value: Optional[str]) -> str:
    return (value or os.environ.get("GITHUB_API_BASE") or DEFAULT_GITHUB_API_BASE).rstrip("/")


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


@mcp.tool()
async def create_github_issue(
    user_query: str,
    assistant_answer: str,
    owner: str | None = None,
    repo: str | None = None,
    repository: str | None = None,
    title: str | None = None,
    rag_context: str | None = None,
    findings: List[str] | None = None,
    labels: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
    base_url: str | None = None,
) -> Dict[str, Any]:
    """Create a GitHub Issue using token/env-configured repo."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required.")

    resolved_owner, resolved_repo = _resolve_github_repo(owner, repo, repository)
    if not resolved_owner or not resolved_repo:
        raise RuntimeError(
            "GitHub owner/repo is required (owner/repo args or GITHUB_OWNER/GITHUB_REPO or GITHUB_REPOSITORY)."
        )

    if not user_query or not assistant_answer:
        raise RuntimeError("user_query and assistant_answer are required.")

    if findings is not None and not isinstance(findings, list):
        raise RuntimeError("findings must be a list of strings if provided.")
    if metadata is not None and not isinstance(metadata, dict):
        raise RuntimeError("metadata must be an object/dict if provided.")

    parsed_labels = _parse_label_list(labels)
    default_labels = _default_github_labels()

    issue_payload = format_issue_from_conversation(
        user_query=user_query,
        assistant_answer=assistant_answer,
        rag_context=rag_context,
        findings=findings,
        title=title,
        labels=parsed_labels,
        default_labels=default_labels,
        metadata=metadata,
    )

    client = GitHubClient(token=token, base_url=_github_base_url(base_url))
    try:
        issue = client.create_issue(owner=resolved_owner, repo=resolved_repo, **issue_payload)
    except GitHubError as exc:
        status_info = f" (status {exc.status_code})" if exc.status_code else ""
        raise RuntimeError(f"GitHub API error{status_info}: {exc}") from exc

    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "url": issue.get("html_url"),
        "labels": [
            label.get("name")
            for label in issue.get("labels", [])
            if isinstance(label, dict) and label.get("name")
        ],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
