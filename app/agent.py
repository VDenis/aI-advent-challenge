from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

# Prefer the standalone package; fall back to community shim if missing.
try:  # pragma: no cover - import shim
    from langchain_gigachat import GigaChat  # type: ignore
except ImportError:  # pragma: no cover - fallback path
    from langchain_community.chat_models.gigachat import GigaChat

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SYSTEM_PROMPT = (
    "You are a helpful assistant. If the user asks about weather, "
    "use the weather tools. Do not invent values if a tool was not called. "
    "Use latitude=55.75 and longitude=37.62 for Moscow unless the user gives other coordinates."
)


@dataclass
class ToolLog:
    name: str
    args: Dict[str, Any]
    result_preview: str


def build_llm() -> GigaChat:
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        raise RuntimeError("GIGACHAT_CREDENTIALS is required (see .env.example)")

    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    verify_ssl_env = os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "false").lower()
    verify_ssl = verify_ssl_env not in {"false", "0", "no"}

    # Streaming off by default for stable tool-calling.
    return GigaChat(
        credentials=credentials,
        scope=scope,
        verify_ssl_certs=verify_ssl,
        streaming=False,
    )


def _schema_field_to_type(field_schema: Dict[str, Any]) -> Any:
    t = field_schema.get("type")
    if t == "number":
        return float
    if t == "integer":
        return int
    if t == "boolean":
        return bool
    if t == "array":
        return list
    if t == "object":
        return dict
    return str


def _build_args_model(schema: Dict[str, Any]) -> type[BaseModel]:
    props: Dict[str, Any] = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    fields: Dict[str, tuple[Any, Any]] = {}
    for name, prop in props.items():
        py_type = _schema_field_to_type(prop)
        default = ... if name in required else prop.get("default", None)
        fields[name] = (py_type, default)
    return create_model(schema.get("title", "Args"), **fields)  # type: ignore


async def _session_call_tool(session: ClientSession, name: str, args: Dict[str, Any]) -> Any:
    result = await session.call_tool(name, arguments=args)
    if getattr(result, "is_error", False):
        return {"error": getattr(result, "message", "tool call failed")}
    parts: List[str] = []
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(str(content))
    return "\n".join(parts) if parts else result


async def load_tools(
    server_command: Optional[List[str]] = None,
) -> tuple[ClientSession, List[Any], List[Dict[str, Any]], Any]:
    """Start the MCP weather server over stdio and return tools plus cleanup callback."""
    cmd = server_command or ["python", "-m", "weather_mcp.server"]
    if not cmd:
        raise ValueError("server_command must not be empty")
    server_params = StdioServerParameters(
        command=cmd[0],
        args=cmd[1:],
    )

    stdio_ctx = stdio_client(server_params)
    stdio_transport = await stdio_ctx.__aenter__()
    read, write = stdio_transport
    session_ctx = ClientSession(read, write)
    session = await session_ctx.__aenter__()
    try:
        await session.initialize()
        tools_resp = await session.list_tools()
        tools: List[Any] = []
        tool_specs: List[Dict[str, Any]] = []
        for tool in tools_resp.tools:
            schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {}) or {}
            args_model = _build_args_model(schema)

            async def _tool_fn(**model_args: Any) -> Any:
                return await _session_call_tool(session, tool.name, model_args)

            tools.append(
                StructuredTool.from_function(
                    coroutine=_tool_fn,
                    name=tool.name,
                    description=tool.description or "",
                    args_schema=args_model,
                )
            )
            tool_specs.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "schema": schema,
                }
            )

        async def _cleanup() -> None:
            await session_ctx.__aexit__(None, None, None)
            await stdio_ctx.__aexit__(None, None, None)

        return session, tools, tool_specs, _cleanup
    except Exception:
        await session_ctx.__aexit__(None, None, None)
        await stdio_ctx.__aexit__(None, None, None)
        raise


async def _invoke_tool(tool: Any, args: Dict[str, Any]) -> Any:
    if hasattr(tool, "ainvoke"):
        return await tool.ainvoke(args)
    if callable(tool):
        maybe = tool(args)
        if asyncio.iscoroutine(maybe):
            return await maybe
        return maybe
    raise RuntimeError("Tool object is not callable")


def _tool_call_fields(tool_call: Any) -> tuple[str, Dict[str, Any], str]:
    name = getattr(tool_call, "name", None) or getattr(tool_call, "function", None)
    call_id = getattr(tool_call, "id", None) or getattr(tool_call, "tool_call_id", None)
    args = getattr(tool_call, "args", None) or getattr(tool_call, "arguments", None)
    if args is None and isinstance(tool_call, dict):
        name = name or tool_call.get("name")
        call_id = call_id or tool_call.get("id") or tool_call.get("tool_call_id")
        args = tool_call.get("args") or tool_call.get("arguments")
    return str(name), args or {}, str(call_id or name)


async def run_agent(
    user_query: str,
    server_command: Optional[List[str]] = None,
) -> tuple[str, List[ToolLog]]:
    """Main loop: model -> tool_calls -> ToolMessage -> model."""
    load_dotenv()
    llm = build_llm()

    session, tools, tool_specs, cleanup = await load_tools(server_command)
    tool_registry = {tool.name: tool for tool in tools}

    use_native_tools = True
    try:
        llm_with_tools = llm.bind_tools(tools)
    except NotImplementedError:
        use_native_tools = False

    messages: List[Any] = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_query)]
    logs: List[ToolLog] = []

    try:
        while True:
            if use_native_tools:
                ai_message: AIMessage = await llm_with_tools.ainvoke(messages)
                messages.append(ai_message)
                tool_calls = ai_message.tool_calls or []
                if not tool_calls:
                    final = ai_message.content or ""
                    return final, logs

                for tool_call in tool_calls:
                    name, args, call_id = _tool_call_fields(tool_call)
                    tool = tool_registry.get(name)
                    if tool is None:
                        result: Any = {"error": f"Tool '{name}' not found"}
                    else:
                        try:
                            result = await _invoke_tool(tool, args)
                        except Exception as exc:  # pragma: no cover - defensive
                            result = {"error": str(exc)}

                    preview = result if isinstance(result, str) else json.dumps(
                        result, ensure_ascii=False
                    )
                    logs.append(ToolLog(name=name, args=args, result_preview=preview[:500]))

                    messages.append(
                        ToolMessage(
                            content=preview,
                            tool_call_id=call_id,
                        )
                    )
            else:
                # Fallback: ask the model to return JSON with tool_calls or final answer.
                tool_spec_json = json.dumps(tool_specs, ensure_ascii=False)
                fallback_prompt = (
                    SYSTEM_PROMPT
                    + "\nYou can call tools by returning JSON: "
                    + '{"tool_calls":[{"name": "...", "arguments": {...}}]} '
                    + 'or return {"final": "..."}.\n'
                    + f"Available tools: {tool_spec_json}"
                )
                ai_message: AIMessage = await llm.ainvoke(
                    [SystemMessage(content=fallback_prompt)] + messages[1:]
                )
                messages.append(ai_message)
                content = ai_message.content or ""
                calls: List[Dict[str, Any]] = []
                try:
                    parsed = json.loads(content)
                    calls = parsed.get("tool_calls", [])
                    final_answer = parsed.get("final")
                except Exception:
                    calls = []
                    final_answer = None

                if not calls:
                    final = final_answer or content
                    return final, logs

                for idx, call in enumerate(calls):
                    name = call.get("name")
                    args = call.get("arguments") or call.get("args") or {}
                    call_id = f"fallback-{idx}-{name}"
                    tool = tool_registry.get(name)
                    if tool is None:
                        result: Any = {"error": f"Tool '{name}' not found"}
                    else:
                        try:
                            result = await _invoke_tool(tool, args)
                        except Exception as exc:  # pragma: no cover - defensive
                            result = {"error": str(exc)}

                    preview = result if isinstance(result, str) else json.dumps(
                        result, ensure_ascii=False
                    )
                    logs.append(ToolLog(name=name or "unknown", args=args, result_preview=preview[:500]))

                    messages.append(
                        HumanMessage(
                            content=f"[tool:{name}] {preview}"
                        )
                    )
    finally:
        await cleanup()
