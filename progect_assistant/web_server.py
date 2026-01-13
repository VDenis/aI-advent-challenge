from __future__ import annotations

import json
import os
import shlex
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from progect_assistant.assistant.llm import LLMError, openai_chat_completion
from progect_assistant.assistant.mcp_client import MCPStdioClient, run_async
from progect_assistant.assistant.mcp_config import load_mcp_config, resolve_mcp_entry


PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())
WEB_ROOT = Path(PROJECT_ROOT) / "progect_assistant" / "web"

DEFAULT_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "openai/gpt-oss-20b:groq")
DEFAULT_HF_BASE_URL = os.environ.get("HF_BASE_URL", "https://router.huggingface.co/v1")
DEFAULT_HF_MODEL = os.environ.get("HF_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
DEFAULT_HOST = os.environ.get("ASSISTANT_WEB_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ASSISTANT_WEB_PORT", "8088"))


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
        return {"error": "No MCP servers are configured."}
    client = _load_mcp_client(server_name)
    if not client:
        return {"error": f"MCP server '{server_name}' is not configured."}
    try:
        result = await client.call_tool(tool_name, arguments)
        return result
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
    return {"message": follow_up_message, "tool_calls": tool_calls, "tool_results": tool_results}


class AssistantWebHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/config":
            hf_key = os.environ.get("HF_API_KEY", "")
            ollama_key = os.environ.get("OLLAMA_API_KEY", "")

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
                },
            )
            return

        if self.path.startswith("/api/ollama/models"):
            base_url = self._query_param("base_url") or DEFAULT_OLLAMA_BASE_URL
            models = _fetch_ollama_models(base_url)
            _json_response(self, HTTPStatus.OK, {"models": models})
            return

        if self.path == "/api/mcp/tools":
            _json_response(
                self,
                HTTPStatus.OK,
                {"tools": _list_mcp_tools(), "servers": list(_available_mcp_entries().keys())},
            )
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
            provider = payload.get("provider", "ollama")
            model = payload.get("model") or (DEFAULT_OLLAMA_MODEL if provider == "ollama" else DEFAULT_HF_MODEL)
            messages = payload.get("messages") or []
            if not messages and payload.get("message"):
                messages = [{"role": "user", "content": payload["message"]}]
            if not isinstance(messages, list):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "messages must be a list"})
                return
            use_mcp = bool(payload.get("use_mcp"))

            try:
                if provider == "ollama":
                    base_url = payload.get("base_url") or DEFAULT_OLLAMA_BASE_URL
                    api_key = payload.get("api_key") or os.environ.get("OLLAMA_API_KEY")
                    if use_mcp:
                        mcp_tools = _list_mcp_tools()
                        response = _run_openai_with_mcp(
                            base_url=base_url,
                            api_key=api_key,
                            model=model,
                            messages=messages,
                            mcp_tools=mcp_tools,
                        )
                        _json_response(self, HTTPStatus.OK, response)
                        return
                    data = openai_chat_completion(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                    )
                    message = _extract_openai_message(data)
                    _json_response(self, HTTPStatus.OK, {"message": message})
                    return

                if provider == "huggingface":
                    base_url = payload.get("base_url") or DEFAULT_HF_BASE_URL
                    api_key = payload.get("api_key") or os.environ.get("HF_API_KEY", "")
                    if not api_key:
                        _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "HF_API_KEY is required."})
                        return
                    if use_mcp:
                        mcp_tools = _list_mcp_tools()
                        response = _run_openai_with_mcp(
                            base_url=base_url,
                            api_key=api_key,
                            model=model,
                            messages=messages,
                            mcp_tools=mcp_tools,
                        )
                        _json_response(self, HTTPStatus.OK, response)
                        return
                    data = openai_chat_completion(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                    )
                    message = _extract_openai_message(data)
                    _json_response(self, HTTPStatus.OK, {"message": message})
                    return

                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"Unknown provider: {provider}"})
            except LLMError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
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


def main() -> None:
    server = ThreadingHTTPServer((DEFAULT_HOST, DEFAULT_PORT), AssistantWebHandler)
    print(f"Assistant Web UI running on http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
