from __future__ import annotations

import asyncio
import json
import os
import shlex
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from dotenv import load_dotenv
from progect_assistant.assistant.github import (
    DEFAULT_GITHUB_API_BASE,
    DEFAULT_GITHUB_LABELS,
    GitHubClient,
    GitHubError,
    format_issue_from_conversation,
)
from progect_assistant.assistant.llm import LLMError, openai_chat_completion
from progect_assistant.assistant.mcp import (
    MCPStdioClient,
    load_mcp_config,
    resolve_mcp_entry,
    run_async,
)
from progect_assistant.assistant.rag import RagIndexer, RagSearch
# New Code RAG (hybrid search + AST chunking)
from progect_assistant.assistant.rag import CodeRAG, RetrievalResult


PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())
WEB_ROOT = Path(PROJECT_ROOT) / "progect_assistant" / "web"

# Load environment from .env if present (helps when running web server directly)
load_dotenv(dotenv_path=Path(PROJECT_ROOT) / ".env", override=False)

DEFAULT_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "openai/gpt-oss-20b:groq")
DEFAULT_HF_BASE_URL = os.environ.get("HF_BASE_URL", "https://router.huggingface.co/v1")
DEFAULT_HF_MODEL = os.environ.get("HF_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
DEFAULT_HOST = os.environ.get("ASSISTANT_WEB_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ASSISTANT_WEB_PORT", "8088"))
DEFAULT_RAG_CACHE_PATH = os.environ.get(
    "ASSISTANT_CACHE_PATH",
    str(Path("progect_assistant") / ".cache" / "rag_index.json"),
)

RAG_SYSTEM_PROMPT = (
    "You must answer only using the information in CONTEXT. "
    "If the answer is not in CONTEXT, say you couldn't find it in the provided context."
)
_RAG_LOCK = threading.Lock()
_RAG_INDEXER = RagIndexer(PROJECT_ROOT, DEFAULT_RAG_CACHE_PATH)
_RAG_INDEX = None
_RAG_STATUS: Dict[str, Any] = {
    "state": "idle",
    "total_files": 0,
    "processed_files": 0,
    "current_file": "",
    "chunks": 0,
    "error": "",
}
_RAG_THREAD: Optional[threading.Thread] = None

# ============================================================================
# NEW CODE RAG (Hybrid Search + AST Chunking)
# ============================================================================
_CODE_RAG_LOCK = threading.Lock()
_CODE_RAG: Optional[CodeRAG] = None
_CODE_RAG_STATUS: Dict[str, Any] = {
    "state": "idle",
    "total_files": 0,
    "processed_files": 0,
    "current_file": "",
    "chunks": 0,
    "error": "",
    "embedding_progress": 0,
}
_CODE_RAG_THREAD: Optional[threading.Thread] = None

# Environment variable to enable new Code RAG (default: True)
USE_CODE_RAG = os.environ.get("USE_CODE_RAG", "true").lower() in ("true", "1", "yes")
CODE_RAG_EMBEDDING_PROVIDER = os.environ.get("CODE_RAG_EMBEDDING_PROVIDER", "ollama")
CODE_RAG_EMBEDDING_MODEL = os.environ.get("CODE_RAG_EMBEDDING_MODEL", "nomic-embed-text")
CODE_RAG_USE_RERANKER = os.environ.get("CODE_RAG_USE_RERANKER", "false").lower() in ("true", "1", "yes")


def _get_code_rag() -> Optional[CodeRAG]:
    """Get or create Code RAG instance."""
    global _CODE_RAG
    if not USE_CODE_RAG:
        return None

    with _CODE_RAG_LOCK:
        if _CODE_RAG is None:
            try:
                _CODE_RAG = CodeRAG(
                    project_root=Path(PROJECT_ROOT),
                    embedding_provider=CODE_RAG_EMBEDDING_PROVIDER,
                    embedding_model=CODE_RAG_EMBEDDING_MODEL,
                    use_reranker=CODE_RAG_USE_RERANKER,
                )
                # Try to load existing index
                if _CODE_RAG.index_path.exists():
                    _ = _CODE_RAG.retriever  # This triggers loading
                    print(f"✓ Code RAG loaded ({len(_CODE_RAG.retriever.chunks)} chunks)")
            except Exception as e:
                print(f"✗ Code RAG init failed: {e}")
                _CODE_RAG = None
        return _CODE_RAG


def _get_code_rag_status() -> Dict[str, Any]:
    """Get Code RAG indexing status."""
    with _CODE_RAG_LOCK:
        status = dict(_CODE_RAG_STATUS)
        rag = _CODE_RAG
        if rag and rag.retriever.chunks:
            status["chunks"] = len(rag.retriever.chunks)
            status["files"] = len(set(c.file_path for c in rag.retriever.chunks.values()))
        return status


def _set_code_rag_status(**updates: Any) -> None:
    """Update Code RAG status."""
    with _CODE_RAG_LOCK:
        _CODE_RAG_STATUS.update(updates)


def _code_rag_progress_callback(current_file: str, processed: int, total: int) -> None:
    """Progress callback for Code RAG indexing."""
    _set_code_rag_status(
        current_file=current_file,
        processed_files=processed,
        total_files=total,
    )


def _run_code_rag_indexing() -> None:
    """Run Code RAG indexing in background thread."""
    global _CODE_RAG
    try:
        _set_code_rag_status(state="running", error="", chunks=0)

        rag = CodeRAG(
            project_root=Path(PROJECT_ROOT),
            embedding_provider=CODE_RAG_EMBEDDING_PROVIDER,
            embedding_model=CODE_RAG_EMBEDDING_MODEL,
            use_reranker=CODE_RAG_USE_RERANKER,
        )

        count = rag.build_index(progress_callback=_code_rag_progress_callback)

        with _CODE_RAG_LOCK:
            _CODE_RAG = rag

        _set_code_rag_status(state="done", chunks=count, current_file="")
        print(f"✓ Code RAG indexed {count} chunks")

    except Exception as e:
        _set_code_rag_status(state="error", error=str(e), current_file="")
        print(f"✗ Code RAG indexing failed: {e}")


def _start_code_rag_indexing() -> Dict[str, Any]:
    """Start Code RAG indexing in background."""
    global _CODE_RAG_THREAD
    with _CODE_RAG_LOCK:
        if _CODE_RAG_THREAD and _CODE_RAG_THREAD.is_alive():
            return dict(_CODE_RAG_STATUS)

        _CODE_RAG_STATUS.update({
            "state": "running",
            "total_files": 0,
            "processed_files": 0,
            "current_file": "",
            "chunks": 0,
            "error": "",
        })

        _CODE_RAG_THREAD = threading.Thread(target=_run_code_rag_indexing, daemon=True)
        _CODE_RAG_THREAD.start()
        return dict(_CODE_RAG_STATUS)


def _build_code_rag_context(query: str, top_k: int = 10) -> str:
    """Build context using new Code RAG with hybrid search."""
    rag = _get_code_rag()
    if not rag or not rag.retriever.chunks:
        return ""

    try:
        results = rag.search(query, top_k=top_k, rerank=CODE_RAG_USE_RERANKER)
        if not results:
            return ""

        return rag.get_context(results, query=query, max_tokens=8000)
    except Exception as e:
        print(f"Code RAG search error: {e}")
        return ""


class MCPProcessManager:
    """Manages persistent MCP server processes."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def start_all(self):
        """Start all configured MCP servers at web server startup."""
        entries = _available_mcp_entries()
        for name in entries.keys():
            await self.start_server(name)

    async def start_server(self, name: str):
        """Start a single MCP server as persistent process."""
        try:
            entry = resolve_mcp_entry(self.project_root, name)
            command = entry.get("command", "")

            if not command:
                async with self.lock:
                    self.servers[name] = {
                        "client": None,
                        "status": "error",
                        "error": "No command configured",
                        "tools_count": 0,
                        "last_check": time.time(),
                    }
                return

            env = {"PROJECT_ROOT": self.project_root, **entry.get("env", {})}
            client = MCPStdioClient(command=shlex.split(command), name=f"{name}-mcp", env=env)

            # Test connection
            tools = await client.list_tools()

            async with self.lock:
                self.servers[name] = {
                    "client": client,
                    "status": "connected",
                    "error": None,
                    "tools_count": len(tools),
                    "last_check": time.time(),
                }

            print(f"✓ MCP server '{name}' started ({len(tools)} tools)")

        except Exception as e:
            print(f"✗ MCP server '{name}' failed to start: {e}")
            async with self.lock:
                self.servers[name] = {
                    "client": None,
                    "status": "error",
                    "error": str(e),
                    "tools_count": 0,
                    "last_check": time.time(),
                }

    async def stop_server(self, name: str):
        """Stop a single MCP server."""
        async with self.lock:
            instance = self.servers.get(name)
            if instance and instance.get("client"):
                try:
                    await instance["client"].close()
                    print(f"✓ MCP server '{name}' stopped")
                except Exception as e:
                    print(f"✗ Error stopping MCP server '{name}': {e}")
                finally:
                    self.servers[name]["client"] = None
                    self.servers[name]["status"] = "disconnected"

    async def stop_all(self):
        """Stop all running servers (at shutdown)."""
        for name in list(self.servers.keys()):
            await self.stop_server(name)

    async def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all servers (connected/disconnected/error)."""
        async with self.lock:
            status = {}
            for name, instance in self.servers.items():
                status[name] = {
                    "status": instance.get("status", "unknown"),
                    "error": instance.get("error"),
                    "tools_count": instance.get("tools_count", 0),
                    "last_check": instance.get("last_check", 0),
                }
            return status

    async def list_all_tools(self) -> List[Dict[str, Any]]:
        """List tools from all connected servers."""
        tools = []

        async with self.lock:
            servers_snapshot = dict(self.servers)

        for name, instance in servers_snapshot.items():
            if instance["status"] != "connected" or not instance.get("client"):
                continue

            try:
                client = instance["client"]
                server_tools = await client.list_tools()
                for tool in server_tools:
                    raw_name = tool.get("name", "")
                    tools.append({
                        **tool,
                        "name": f"{name}::{raw_name}",
                        "raw_name": raw_name,
                        "server": name,
                    })
            except Exception as e:
                # Mark as error if tool listing fails
                async with self.lock:
                    if name in self.servers:
                        self.servers[name]["status"] = "error"
                        self.servers[name]["error"] = f"Failed to list tools: {e}"
                print(f"✗ MCP server '{name}' error: {e}")

        return tools


# Global MCP manager instance
_mcp_manager: Optional[MCPProcessManager] = None


def get_mcp_manager() -> MCPProcessManager:
    """Get or create the global MCP process manager."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPProcessManager(PROJECT_ROOT)
    return _mcp_manager


def _get_rag_index():
    global _RAG_INDEX
    with _RAG_LOCK:
        if _RAG_INDEX is None:
            _RAG_INDEX = _RAG_INDEXER.load_or_build()
        return _RAG_INDEX


def _get_rag_status() -> Dict[str, Any]:
    with _RAG_LOCK:
        return dict(_RAG_STATUS)


def _set_rag_status(**updates: Any) -> None:
    with _RAG_LOCK:
        _RAG_STATUS.update(updates)


def _rag_progress_update(payload: Dict[str, Any]) -> None:
    event = payload.get("event")
    if event == "start":
        _set_rag_status(
            state="running",
            total_files=int(payload.get("total", 0)),
            processed_files=0,
            current_file="",
            chunks=0,
            error="",
        )
        return
    if event == "file":
        _set_rag_status(
            processed_files=int(payload.get("index", 0)),
            total_files=int(payload.get("total", 0)),
            current_file=str(payload.get("path", "")),
        )
        return
    if event == "done":
        _set_rag_status(
            state="done",
            total_files=int(payload.get("total", 0)),
            processed_files=int(payload.get("total", 0)),
            chunks=int(payload.get("chunks", 0)),
            current_file="",
        )


def _run_rag_indexing() -> None:
    global _RAG_INDEX
    try:
        _set_rag_status(state="running", error="")
        index = _RAG_INDEXER.build_index(progress_cb=_rag_progress_update, verbose=False)
        with _RAG_LOCK:
            _RAG_INDEX = index
    except Exception as exc:
        _set_rag_status(state="error", error=str(exc), current_file="")


def _start_rag_indexing() -> Dict[str, Any]:
    global _RAG_THREAD
    with _RAG_LOCK:
        if _RAG_THREAD and _RAG_THREAD.is_alive():
            return dict(_RAG_STATUS)
        _RAG_STATUS.update(
            {
                "state": "running",
                "total_files": 0,
                "processed_files": 0,
                "current_file": "",
                "chunks": 0,
                "error": "",
            }
        )
        _RAG_THREAD = threading.Thread(target=_run_rag_indexing, daemon=True)
        _RAG_THREAD.start()
        return dict(_RAG_STATUS)


def _extract_last_user_message(messages: List[Dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _build_rag_context(query: str, top_k: int) -> str:
    """Build RAG context - uses Code RAG if available, falls back to legacy."""
    if not query:
        return ""

    # Try new Code RAG first (hybrid search)
    if USE_CODE_RAG:
        code_rag_context = _build_code_rag_context(query, top_k=top_k)
        if code_rag_context:
            return code_rag_context

    # Fallback to legacy TF-IDF RAG
    index = _get_rag_index()
    searcher = RagSearch(index)
    results = searcher.search(query, top_k=top_k)
    if not results:
        return ""
    sections = []
    for _score, chunk in results:
        snippet = chunk.text.strip()
        if not snippet:
            continue
        sections.append(f"[{chunk.path} | {chunk.section}]\n{snippet}")
    return "\n\n".join(sections)


def _inject_rag_context(messages: List[Dict[str, Any]], context: str) -> List[Dict[str, Any]]:
    if not context:
        return [{"role": "system", "content": RAG_SYSTEM_PROMPT}, *messages]

    new_messages: List[Dict[str, Any]] = []
    last_user_idx = None
    for idx, message in enumerate(messages):
        if message.get("role") == "user":
            last_user_idx = idx

    for idx, message in enumerate(messages):
        if idx == last_user_idx:
            content = str(message.get("content", ""))
            new_content = f"{content}\n\nCONTEXT:\n{context}"
            new_messages.append({**message, "content": new_content})
        else:
            new_messages.append(message)

    if last_user_idx is None:
        new_messages.append({"role": "user", "content": f"CONTEXT:\n{context}"})

    return [{"role": "system", "content": RAG_SYSTEM_PROMPT}, *new_messages]


def _find_create_issue_tools(mcp_tools: List[Dict[str, Any]]) -> List[str]:
    """Return fully qualified names for GitHub issue tools."""
    issue_tools: List[str] = []
    for tool in mcp_tools:
        raw_name = tool.get("raw_name") or tool.get("name") or ""
        qualified = tool.get("name") or raw_name
        if "create_github_issue" in raw_name or "create_github_issue" in qualified:
            issue_tools.append(str(qualified))
    return issue_tools


def _inject_mcp_guidance(messages: List[Dict[str, Any]], mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prepend guidance so the model knows how to use MCP tools for GitHub tasks."""
    issue_tools = _find_create_issue_tools(mcp_tools)
    if not issue_tools:
        return messages

    tools_text = ", ".join(issue_tools)
    guidance = (
        "You can call MCP tools to take real actions. "
        "When the user asks to create a task/issue, call the GitHub issue tool "
        f"({tools_text}) with user_query (original ask) and assistant_answer (your summary). "
        "Always return the created issue number and URL to the user."
    )
    return [{"role": "system", "content": guidance}, *messages]


def _mask_api_key(key: str) -> str:
    """Mask API key for display, showing only first 3 and last 4 chars."""
    if not key or len(key) < 8:
        return ""
    return f"{key[:3]}{'*' * 8}{key[-4:]}"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    data = handler.rfile.read(length).decode("utf-8")
    if not data:
        return {}
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {}


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


def _resolve_github_repo(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    owner = payload.get("owner")
    repo = payload.get("repo")
    repository = payload.get("repository") or os.environ.get("GITHUB_REPOSITORY", "")
    if repository and (not owner or not repo):
        if "/" in repository:
            repo_owner, repo_name = repository.split("/", 1)
            owner = owner or repo_owner
            repo = repo or repo_name

    owner = owner or os.environ.get("GITHUB_OWNER")
    repo = repo or os.environ.get("GITHUB_REPO")

    return (str(owner) if owner else None), (str(repo) if repo else None)


def _github_status_from_error(status_code: Optional[int]) -> HTTPStatus:
    if status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        return HTTPStatus.UNAUTHORIZED
    if status_code == HTTPStatus.NOT_FOUND:
        return HTTPStatus.NOT_FOUND
    if status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
        return HTTPStatus.UNPROCESSABLE_ENTITY
    if status_code is not None and 400 <= status_code < 500:
        return HTTPStatus.BAD_REQUEST
    return HTTPStatus.BAD_GATEWAY


def _available_mcp_entries() -> Dict[str, Dict[str, Any]]:
    config = load_mcp_config(PROJECT_ROOT)
    entries: Dict[str, Dict[str, Any]] = {}
    if isinstance(config, dict):
        for name in config.keys():
            entry = resolve_mcp_entry(PROJECT_ROOT, name)
            if entry.get("command"):
                entries[name] = entry
    if not entries:
        fallback_command = os.environ.get("GIT_MCP_COMMAND", "")
        if fallback_command:
            entries["git"] = resolve_mcp_entry(PROJECT_ROOT, "git", fallback_command=fallback_command)
    return entries


def _load_mcp_client(server: str) -> Optional[MCPStdioClient]:
    fallback = os.environ.get("GIT_MCP_COMMAND", "") if server == "git" else ""
    entry = resolve_mcp_entry(PROJECT_ROOT, server, fallback_command=fallback)
    command = entry.get("command", "")
    if not command:
        return None
    env = {"PROJECT_ROOT": PROJECT_ROOT, **entry.get("env", {})}
    return MCPStdioClient(command=shlex.split(command), name=f"{server}-mcp", env=env)


def _split_tool_name(name: str, server: Optional[str], servers: List[str]) -> tuple[str, str]:
    if "::" in name:
        server_name, tool_name = name.split("::", 1)
        return server_name, tool_name
    if server:
        return server, name
    if len(servers) == 1:
        return servers[0], name
    if "git" in servers:
        return "git", name
    return (servers[0] if servers else ""), name


async def _list_mcp_tools_async() -> List[Dict[str, Any]]:
    entries = _available_mcp_entries()
    tools: List[Dict[str, Any]] = []
    for server, _entry in entries.items():
        client = _load_mcp_client(server)
        if not client:
            continue
        try:
            for tool in await client.list_tools():
                raw_name = tool.get("name", "")
                qualified_name = f"{server}::{raw_name}" if raw_name else ""
                tools.append(
                    {
                        **tool,
                        "name": qualified_name,
                        "raw_name": raw_name,
                        "server": server,
                    }
                )
        finally:
            await client.close()
    return tools


def _list_mcp_tools() -> List[Dict[str, Any]]:
    return run_async(_list_mcp_tools_async())


async def _call_mcp_tool_async(
    name: str, arguments: Dict[str, Any], server: Optional[str] = None
) -> Dict[str, Any]:
    entries = _available_mcp_entries()
    servers = list(entries.keys())
    server_name, tool_name = _split_tool_name(name, server, servers)
    if not server_name:
        return {"error": "No MCP servers are configured.", "success": False}
    client = _load_mcp_client(server_name)
    if not client:
        return {"error": f"MCP server '{server_name}' is not configured.", "success": False}
    try:
        result = await client.call_tool(tool_name, arguments)
        # Check if result contains an error from MCP server
        if isinstance(result, dict) and result.get("error"):
            print(f"✗ MCP tool '{name}' returned error: {result.get('error')}")
            result["success"] = False
            return result
        # Mark successful calls explicitly
        if isinstance(result, dict):
            result["success"] = True
        return result
    except Exception as e:
        print(f"✗ MCP tool '{name}' call failed: {e}")
        return {"error": str(e), "success": False}
    finally:
        await client.close()


def _call_mcp_tool(name: str, arguments: Dict[str, Any], server: Optional[str] = None) -> Dict[str, Any]:
    return run_async(_call_mcp_tool_async(name, arguments, server=server))


def _format_openai_tools(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted = []
    for tool in mcp_tools:
        server = tool.get("server")
        description = tool.get("description", "")
        if server:
            description = f"[{server}] {description}" if description else f"[{server}]"
        formatted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": description,
                    "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
                },
            }
        )
    return formatted


def _extract_issue_results(tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collect GitHub issue results from MCP tool responses."""
    issues: List[Dict[str, Any]] = []
    for entry in tool_results:
        name = str(entry.get("name", ""))
        result = entry.get("result")
        if "create_github_issue" not in name:
            continue
        if not isinstance(result, dict):
            issues.append({"name": name, "success": False, "error": "No issue details returned"})
            continue
        success = result.get("success", True)
        issue = {
            "name": name,
            "success": bool(success),
            "number": result.get("number"),
            "title": result.get("title"),
            "url": result.get("url") or result.get("html_url"),
            "labels": result.get("labels") if isinstance(result.get("labels"), list) else [],
        }
        if not success:
            issue["error"] = result.get("error") or "Issue creation failed"
        issues.append(issue)
    return issues


def _extract_openai_message(data: Dict[str, Any]) -> Dict[str, Any]:
    choices = data.get("choices", []) if isinstance(data, dict) else []
    if not choices:
        return {"role": "assistant", "content": ""}
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if isinstance(message, dict):
        return message
    return {"role": "assistant", "content": ""}


def _run_openai_with_mcp(
    *,
    base_url: str,
    api_key: Optional[str],
    model: str,
    messages: List[Dict[str, Any]],
    mcp_tools: List[Dict[str, Any]],
) -> Dict[str, Any]:
    tools = _format_openai_tools(mcp_tools)
    first = openai_chat_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    message = _extract_openai_message(first)
    tool_calls = message.get("tool_calls") or []
    if not tool_calls and message.get("function_call"):
        tool_calls = [{"id": "call-1", "type": "function", "function": message["function_call"]}]

    if not tool_calls:
        return {"message": message, "tool_calls": [], "tool_results": []}

    tool_results = []
    tool_messages = []
    for call in tool_calls:
        function = call.get("function", {})
        name = function.get("name", "")
        raw_args = function.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            args = {}
        result = _call_mcp_tool(name, args)
        tool_results.append({"name": name, "result": result})
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(result, ensure_ascii=True),
            }
        )

    follow_up = openai_chat_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=[*messages, message, *tool_messages],
    )
    follow_up_message = _extract_openai_message(follow_up)
    issues = _extract_issue_results(tool_results)
    return {
        "message": follow_up_message,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "issues": issues,
    }


class AssistantWebHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/config":
            hf_key = os.environ.get("HF_API_KEY", "")
            ollama_key = os.environ.get("OLLAMA_API_KEY", "")

            # Get Code RAG stats
            code_rag_stats = {"enabled": False, "chunks": 0}
            if USE_CODE_RAG:
                rag = _get_code_rag()
                code_rag_stats = {
                    "enabled": True,
                    "provider": CODE_RAG_EMBEDDING_PROVIDER,
                    "model": CODE_RAG_EMBEDDING_MODEL,
                    "reranker": CODE_RAG_USE_RERANKER,
                    "chunks": len(rag.retriever.chunks) if rag and rag.retriever.chunks else 0,
                    "ready": bool(rag and rag.retriever.chunks),
                }

            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "ollama": {
                        "base_url": DEFAULT_OLLAMA_BASE_URL,
                        "model": DEFAULT_OLLAMA_MODEL,
                        "api_key_masked": _mask_api_key(ollama_key),
                        "has_api_key": bool(ollama_key),
                    },
                    "huggingface": {
                        "base_url": DEFAULT_HF_BASE_URL,
                        "model": DEFAULT_HF_MODEL,
                        "api_key_masked": _mask_api_key(hf_key),
                        "has_api_key": bool(hf_key),
                    },
                    "code_rag": code_rag_stats,
                },
            )
            return

        if self.path == "/api/rag/status":
            _json_response(self, HTTPStatus.OK, {"status": _get_rag_status()})
            return

        # New Code RAG status endpoint
        if self.path == "/api/code-rag/status":
            status = _get_code_rag_status()
            rag = _get_code_rag()
            if rag:
                status["stats"] = rag.get_stats()
                status["enabled"] = True
                status["provider"] = CODE_RAG_EMBEDDING_PROVIDER
                status["model"] = CODE_RAG_EMBEDDING_MODEL
                status["reranker"] = CODE_RAG_USE_RERANKER
            else:
                status["enabled"] = USE_CODE_RAG
                status["stats"] = {"status": "not_initialized"}
            _json_response(self, HTTPStatus.OK, {"status": status})
            return

        # Code RAG search endpoint (for testing)
        if self.path.startswith("/api/code-rag/search"):
            query = self._query_param("q") or ""
            top_k = int(self._query_param("top_k") or "10")
            if not query:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Query parameter 'q' required"})
                return

            rag = _get_code_rag()
            if not rag:
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Code RAG not available"})
                return

            try:
                results = rag.search(query, top_k=top_k)
                response_results = []
                for r in results:
                    response_results.append({
                        "file_path": r.chunk.file_path,
                        "name": r.chunk.name,
                        "chunk_type": r.chunk.chunk_type,
                        "start_line": r.chunk.start_line,
                        "end_line": r.chunk.end_line,
                        "score": r.final_score,
                        "dense_score": r.dense_score,
                        "sparse_score": r.sparse_score,
                        "text_preview": r.chunk.text[:200] + "..." if len(r.chunk.text) > 200 else r.chunk.text,
                    })
                _json_response(self, HTTPStatus.OK, {"query": query, "results": response_results})
            except Exception as e:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})
            return

        if self.path.startswith("/api/ollama/models"):
            base_url = self._query_param("base_url") or DEFAULT_OLLAMA_BASE_URL
            models = _fetch_ollama_models(base_url)
            _json_response(self, HTTPStatus.OK, {"models": models})
            return

        if self.path == "/api/mcp/tools":
            manager = get_mcp_manager()
            # Ensure servers are started even if startup hook was skipped.
            if not manager.servers:
                run_async(manager.start_all())
            tools = run_async(manager.list_all_tools())
            status = run_async(manager.get_status())

            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "tools": tools,
                    "servers": list(status.keys()),
                    "status": status,
                },
            )
            return

        if self.path == "/api/mcp/status":
            manager = get_mcp_manager()
            status = run_async(manager.get_status())
            _json_response(self, HTTPStatus.OK, {"servers": status})
            return

        # Support API endpoints
        if self.path == "/api/support/tickets":
            tickets_data = _load_support_tickets(PROJECT_ROOT)
            _json_response(self, HTTPStatus.OK, tickets_data)
            return

        if self.path.startswith("/api/support/ticket/"):
            ticket_id = self.path.split("/")[-1]
            ticket_data = _get_support_ticket(PROJECT_ROOT, ticket_id)
            _json_response(self, HTTPStatus.OK, ticket_data)
            return

        if self.path == "/api/support/faq":
            faq_data = _load_support_faq(PROJECT_ROOT)
            _json_response(self, HTTPStatus.OK, faq_data)
            return

        if self.path in ("/", "/index.html"):
            path = WEB_ROOT / "index.html"
            self._send_static(path, "text/html; charset=utf-8")
            return

        if self.path == "/app.js":
            self._send_static(WEB_ROOT / "app.js", "application/javascript; charset=utf-8")
            return

        if self.path == "/styles.css":
            self._send_static(WEB_ROOT / "styles.css", "text/css; charset=utf-8")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        if self.path == "/api/rag/index":
            status = _start_rag_indexing()
            _json_response(self, HTTPStatus.OK, {"status": status})
            return

        # New Code RAG indexing endpoint
        if self.path == "/api/code-rag/index":
            if not USE_CODE_RAG:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Code RAG is disabled. Set USE_CODE_RAG=true"})
                return
            status = _start_code_rag_indexing()
            _json_response(self, HTTPStatus.OK, {"status": status})
            return

        if self.path == "/api/mcp/restart":
            payload = _read_json(self)
            server_name = payload.get("server")

            if not server_name:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Server name required"})
                return

            manager = get_mcp_manager()

            async def restart_server():
                await manager.stop_server(server_name)
                await manager.start_server(server_name)

            run_async(restart_server())
            _json_response(self, HTTPStatus.OK, {"status": "restarted", "server": server_name})
            return

        if self.path == "/api/mcp/call":
            payload = _read_json(self)
            name = payload.get("name", "")
            arguments = payload.get("arguments") or {}
            server = payload.get("server")
            if not name:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Tool name is required."})
                return
            result = _call_mcp_tool(name, arguments, server=server)
            _json_response(self, HTTPStatus.OK, {"result": result})
            return

        if self.path == "/api/chat":
            payload = _read_json(self)
            provider = payload.get("provider", "huggingface")
            model = payload.get("model") or (DEFAULT_OLLAMA_MODEL if provider == "ollama" else DEFAULT_HF_MODEL)
            messages = payload.get("messages") or []
            if not messages and payload.get("message"):
                messages = [{"role": "user", "content": payload["message"]}]
            if not isinstance(messages, list):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "messages must be a list"})
                return
            use_mcp = bool(payload.get("use_mcp"))
            use_rag = bool(payload.get("use_rag"))
            rag_top_k = int(payload.get("rag_top_k", 5))
            is_gpt_oss = "gpt-oss" in str(model).lower()
            rag_context = ""

            if is_gpt_oss:
                use_rag = True
                use_mcp = False

            if use_rag:
                query = _extract_last_user_message(messages)
                rag_context = _build_rag_context(query, rag_top_k)
                messages = _inject_rag_context(messages, rag_context)

            try:
                if provider == "ollama":
                    base_url = payload.get("base_url") or DEFAULT_OLLAMA_BASE_URL
                    api_key = payload.get("api_key") or os.environ.get("OLLAMA_API_KEY")
                    if use_mcp:
                        mcp_tools = _list_mcp_tools()
                        messages_with_guidance = _inject_mcp_guidance(messages, mcp_tools)
                        response = _run_openai_with_mcp(
                            base_url=base_url,
                            api_key=api_key,
                            model=model,
                            messages=messages_with_guidance,
                            mcp_tools=mcp_tools,
                        )
                        response["rag_context"] = rag_context
                        _json_response(self, HTTPStatus.OK, response)
                        return
                    data = openai_chat_completion(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                    )
                    message = _extract_openai_message(data)
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {"message": message, "rag_context": rag_context},
                    )
                    return

                if provider == "huggingface":
                    base_url = payload.get("base_url") or DEFAULT_HF_BASE_URL
                    api_key = payload.get("api_key") or os.environ.get("HF_API_KEY", "")
                    if not api_key:
                        _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "HF_API_KEY is required."})
                        return
                    if use_mcp:
                        mcp_tools = _list_mcp_tools()
                        messages_with_guidance = _inject_mcp_guidance(messages, mcp_tools)
                        response = _run_openai_with_mcp(
                            base_url=base_url,
                            api_key=api_key,
                            model=model,
                            messages=messages_with_guidance,
                            mcp_tools=mcp_tools,
                        )
                        response["rag_context"] = rag_context
                        _json_response(self, HTTPStatus.OK, response)
                        return
                    data = openai_chat_completion(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                    )
                    message = _extract_openai_message(data)
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {"message": message, "rag_context": rag_context},
                    )
                    return

                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"Unknown provider: {provider}"})
            except LLMError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if self.path == "/api/github/create-issue":
            payload = _read_json(self)
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "GITHUB_TOKEN is required."})
                return

            owner, repo = _resolve_github_repo(payload)
            if not owner or not repo:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "GitHub owner/repo is required."})
                return

            user_query = str(payload.get("user_query", "")).strip()
            assistant_answer = str(payload.get("assistant_answer", "")).strip()
            if not user_query or not assistant_answer:
                _json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "user_query and assistant_answer are required."},
                )
                return

            labels = _parse_label_list(payload.get("labels"))
            default_labels = _default_github_labels()
            findings = payload.get("findings")
            if not isinstance(findings, list):
                findings = None
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None

            issue_payload = format_issue_from_conversation(
                user_query=user_query,
                assistant_answer=assistant_answer,
                rag_context=payload.get("rag_context"),
                findings=findings,
                title=payload.get("title"),
                labels=labels,
                default_labels=default_labels,
                metadata=metadata,
            )

            base_url = payload.get("base_url") or os.environ.get("GITHUB_API_BASE") or DEFAULT_GITHUB_API_BASE
            client = GitHubClient(token=token, base_url=base_url)
            try:
                issue = client.create_issue(owner=owner, repo=repo, **issue_payload)
            except GitHubError as exc:
                status = _github_status_from_error(exc.status_code)
                _json_response(self, status, {"error": str(exc), "details": exc.payload})
                return

            result = {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "url": issue.get("html_url"),
                "labels": [
                    label.get("name")
                    for label in issue.get("labels", [])
                    if isinstance(label, dict) and label.get("name")
                ],
            }
            _json_response(self, HTTPStatus.OK, {"issue": result})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_static(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _query_param(self, name: str) -> Optional[str]:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        values = query.get(name, [])
        if not values:
            return None
        return unquote(values[0])


def _fetch_ollama_models(base_url: str) -> List[str]:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    url = normalized + "/api/tags"
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    data = response.json()
    models = []
    for item in data.get("models", []):
        name = item.get("name")
        if name:
            models.append(str(name))
    return models


def _load_support_tickets(project_root: str) -> Dict[str, Any]:
    """Load tickets from support directory."""
    path = Path(project_root) / "progect_assistant" / "support" / "tickets.json"
    if not path.exists():
        return {"tickets": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {"tickets": []}


def _get_support_ticket(project_root: str, ticket_id: str) -> Dict[str, Any]:
    """Get single ticket by ID."""
    data = _load_support_tickets(project_root)
    for ticket in data.get("tickets", []):
        if ticket.get("ticket_id") == ticket_id:
            return {"ticket": ticket}
    return {"error": "Ticket not found"}


def _load_support_faq(project_root: str) -> Dict[str, Any]:
    """Load FAQ from support directory."""
    path = Path(project_root) / "progect_assistant" / "support" / "faq.json"
    if not path.exists():
        return {"faqs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {"faqs": []}


def main() -> None:
    # Initialize and start MCP manager
    manager = get_mcp_manager()

    # Start MCP servers using shared event loop (thread-safe)
    run_async(manager.start_all())

    # Start web server
    server = ThreadingHTTPServer((DEFAULT_HOST, DEFAULT_PORT), AssistantWebHandler)
    print(f"Assistant Web UI running on http://{DEFAULT_HOST}:{DEFAULT_PORT}")

    try:
        server.serve_forever()
    finally:
        # Cleanup on shutdown
        print("\nShutting down MCP servers...")
        run_async(manager.stop_all())


if __name__ == "__main__":
    main()
