from typing import Any, Dict

from .git_mcp import GitMCPAdapter
from .rag import RagIndexer, RagSearch
from .tools import Tool, ToolContext


class RagSearchTool(Tool):
    name = "rag_search"
    description = "Search project documentation and configs with vector similarity."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self, cache_path: str) -> None:
        self._cache_path = cache_path

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        query = params.get("query", "")
        top_k = int(params.get("top_k", 5))
        indexer = RagIndexer(context.project_root, self._cache_path)
        index = indexer.load_or_build()
        searcher = RagSearch(index)
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


class GitStatusTool(Tool):
    name = "git_status"
    description = "Get git branch and changed files."
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        client = GitMCPAdapter(context.project_root)
        status = client.status()
        return {"branch": status.branch, "changed_files": status.changed_files}


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Get git diff with line limits."
    parameters_schema = {
        "type": "object",
        "properties": {"max_lines": {"type": "integer", "default": 200}},
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        max_lines = int(params.get("max_lines", 200))
        client = GitMCPAdapter(context.project_root)
        diff = client.diff(max_lines=max_lines)
        return {"output": diff}


class ReadFileSnippetTool(Tool):
    name = "read_file_snippet"
    description = "Safely read a file snippet."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path", "start_line", "end_line"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        path = params.get("path", "")
        start_line = int(params.get("start_line", 1))
        end_line = int(params.get("end_line", start_line))
        client = GitMCPAdapter(context.project_root)
        snippet = client.read_file_snippet(path, start_line, end_line)
        return {"output": snippet}
