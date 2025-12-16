"""gigachat-mcp-cli: консольный чат с GigaChat и инструментами MCP FS."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.gigachat_client import GigaChatClient, GigaChatClientConfig


load_dotenv()


DEFAULT_SYSTEM_PROMPT = """
Ты работаешь в консольном клиенте. У тебя есть инструменты файловой системы,
подключённые через MCP (описаны ниже). Когда для ответа нужно действие с файлами,
верни строго JSON в одной строке вида {"tool":"имя","arguments":{...}} без текста.
Если достаточно объяснения, отвечай кратко по-русски. Для опасных действий
(перезапись/удаление/перемещение) сначала уточни у пользователя.

Важно: инструменты принимают параметр path (а не filename). При создании файла
или директории всегда указывай path. Если пользователь не задал путь, спроси
его, не придумывай путь сам.
""".strip()


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def split_env_list(value: str) -> List[str]:
    return [part for part in value.split(os.pathsep) if part] if value else []


def build_mcp_args(root: str, override: str | None) -> List[str]:
    if override:
        return shlex.split(override)
    return ["-m", "mcp_filesystem_sandbox.server", root]


@dataclass
class Settings:
    basic_auth: str
    chat_url: str
    oauth_url: str
    model: str
    temperature: float
    scope: str
    verify_ssl: bool
    request_timeout: float
    root: str
    mcp_command: str
    mcp_args: List[str]
    system_prompt: str
    max_tool_loops: int = 3


def load_settings() -> Settings:
    parser = argparse.ArgumentParser(description="gigachat-mcp-cli")
    parser.add_argument("--root", help="Корень файловой песочницы MCP (по умолчанию ./mcp_fs_root)")
    parser.add_argument("--system-prompt", help="Кастомный system prompt для GigaChat")
    parser.add_argument("--model", default=os.getenv("GIGA_MODEL_NAME", "GigaChat"))
    parser.add_argument("--temperature", type=float, default=float(os.getenv("GIGA_TEMPERATURE", "0.7")))
    parser.add_argument("--chat-url", default=os.getenv("GIGA_CHAT_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"))
    parser.add_argument("--oauth-url", default=os.getenv("GIGA_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"))
    parser.add_argument("--scope", default=os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS"))
    parser.add_argument("--verify-ssl", action="store_true", default=env_bool("GIGA_VERIFY_SSL", True))
    parser.add_argument("--request-timeout", type=float, default=float(os.getenv("GIGA_REQUEST_TIMEOUT", "60")))
    parser.add_argument("--mcp-command", default=os.getenv("MCP_SERVER_CMD", "python"), help="Команда для запуска MCP сервера")
    parser.add_argument("--mcp-args", default=os.getenv("MCP_SERVER_ARGS"), help="Аргументы для сервера (перекрывают --allow)")
    parser.add_argument("--max-tool-loops", type=int, default=int(os.getenv("MCP_MAX_TOOL_LOOPS", "3")))

    args = parser.parse_args()

    root_arg = args.root or os.getenv("MCP_FS_ROOT")
    if not root_arg:
        # Значение по умолчанию: поддиректория в корне проекта, преобразуется в абсолютный путь.
        root_arg = str((ROOT_DIR / "mcp_fs_root").resolve())
    root_arg = str(Path(root_arg).expanduser().resolve(strict=False))

    mcp_args = build_mcp_args(root_arg, args.mcp_args) if root_arg else shlex.split(args.mcp_args)
    basic_auth = os.getenv("GIGA_CLIENT_BASIC", "")
    if not basic_auth:
        raise SystemExit("Не задан GIGA_CLIENT_BASIC (base64(client_id:client_secret)).")

    system_prompt = args.system_prompt or DEFAULT_SYSTEM_PROMPT

    return Settings(
        basic_auth=basic_auth,
        chat_url=args.chat_url,
        oauth_url=args.oauth_url,
        model=args.model,
        temperature=args.temperature,
        scope=args.scope,
        verify_ssl=args.verify_ssl,
        request_timeout=args.request_timeout,
        root=str(root_arg) if root_arg else "",
        mcp_command=args.mcp_command,
        mcp_args=mcp_args,
        system_prompt=system_prompt,
        max_tool_loops=max(1, args.max_tool_loops),
    )


def tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", ""))


def tool_description(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("description", "") or "")
    return str(getattr(tool, "description", "") or "")


def format_tools(tools: Iterable[Any]) -> str:
    lines = ["Доступные инструменты файловой системы (MCP):"]
    for tool in tools:
        name = tool_name(tool)
        desc = tool_description(tool)
        if name:
            lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        inner = cleaned[3:-3].strip()
        if inner.startswith("json"):
            inner = inner[4:].strip()
        return inner
    return cleaned


def parse_tool_request(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    payload = strip_code_fence(text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("tool") or data.get("name")
    if not name:
        return None
    args = data.get("arguments") or data.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"value": args}
    if not isinstance(args, dict):
        return None
    return str(name), args


async def call_tool(session: ClientSession, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = await session.call_tool(tool, arguments)
        is_error = bool(getattr(result, "isError", False))
        return {"ok": not is_error, "result": result, "is_error": is_error}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _render_content_block(block: Any) -> str:
    if isinstance(block, dict):
        if block.get("type") == "text":
            return str(block.get("text", ""))
        return json.dumps(block, ensure_ascii=False, default=str)
    text = getattr(block, "text", None)
    if text is not None:
        return str(text)
    return str(block)


def serialize_tool_result(result_obj: Any) -> Dict[str, Any]:
    if result_obj is None:
        return {"is_error": False, "content": [], "structured": None}
    is_error = bool(getattr(result_obj, "isError", False))
    content = getattr(result_obj, "content", None)
    structured = None
    # mcp/client returns "structured" per spec; fastmcp may expose "structuredContent"
    if hasattr(result_obj, "structured"):
        structured = getattr(result_obj, "structured")
    elif hasattr(result_obj, "structuredContent"):
        structured = getattr(result_obj, "structuredContent")
    elif isinstance(result_obj, dict):
        structured = result_obj
    rendered = []
    try:
        for entry in content or []:
            rendered.append(_render_content_block(entry))
    except Exception:
        rendered = [str(content)]
    return {"is_error": is_error, "content": rendered, "structured": structured}


async def ask_gigachat(client: GigaChatClient, messages: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
    reply, meta = await client.chat(messages)
    return reply, meta


def compose_system_prompt(base_prompt: str, tools: Iterable[Any]) -> str:
    tools_block = format_tools(tools)
    return textwrap.dedent(f"{base_prompt}\n\n{tools_block}\nОтвечай в рамках этих инструментов.")


async def chat_loop(settings: Settings) -> None:
    client_config = GigaChatClientConfig(
        basic_auth=settings.basic_auth,
        chat_url=settings.chat_url,
        oauth_url=settings.oauth_url,
        model=settings.model,
        verify_ssl=settings.verify_ssl,
        request_timeout=settings.request_timeout,
        scope=settings.scope,
        temperature=settings.temperature,
    )
    giga = GigaChatClient(client_config)

    server_params = StdioServerParameters(
        command=settings.mcp_command,
        args=settings.mcp_args,
    )

    print(f"Запускаю MCP сервер: {settings.mcp_command} {' '.join(settings.mcp_args)}")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            tools_response = await mcp.list_tools()
            tools = (
                tools_response.tools
                if hasattr(tools_response, "tools")
                else tools_response.get("tools", tools_response)
                if isinstance(tools_response, dict)
                else tools_response
            )
            system_prompt = compose_system_prompt(settings.system_prompt, tools)
            messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

            print("Доступные инструменты MCP:")
            print(format_tools(tools))
            print("Команды: :exit для выхода, :tools чтобы обновить список, :clear чтобы сбросить контекст.")

            while True:
                try:
                    user_text = await asyncio.to_thread(input, "you> ")
                except (EOFError, KeyboardInterrupt):
                    break
                user_text = user_text.strip()
                if not user_text:
                    continue
                if user_text.startswith(":"):
                    cmd = user_text[1:].strip().lower()
                    if cmd in {"exit", "quit"}:
                        break
                    if cmd == "tools":
                        tools_response = await mcp.list_tools()
                        tools = (
                            tools_response.tools
                            if hasattr(tools_response, "tools")
                            else tools_response.get("tools", tools_response)
                            if isinstance(tools_response, dict)
                            else tools_response
                        )
                        print(format_tools(tools))
                        continue
                    if cmd == "clear":
                        messages = [{"role": "system", "content": system_prompt}]
                        print("Контекст очищен.")
                        continue
                    print("Неизвестная команда. Доступно: :exit, :tools, :clear")
                    continue

                messages.append({"role": "user", "content": user_text})
                reply_text, _ = await ask_gigachat(giga, messages)
                tool_attempts = 0

                while True:
                    maybe_tool = parse_tool_request(reply_text)
                    if not maybe_tool or tool_attempts >= settings.max_tool_loops:
                        print(f"assistant> {reply_text}")
                        messages.append({"role": "assistant", "content": reply_text})
                        break

                    tool_attempts += 1
                    tool_name, tool_args = maybe_tool
                    print(f"[tool] {tool_name} {tool_args}")
                    tool_result = await call_tool(mcp, tool_name, tool_args)
                    serialized = serialize_tool_result(tool_result.get("result"))
                    tool_result_text = json.dumps(
                        {"ok": tool_result.get("ok"), **serialized, "raw": None},
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                    messages.append({"role": "assistant", "content": json.dumps({"tool": tool_name, "arguments": tool_args}, ensure_ascii=False)})
                    messages.append({"role": "assistant", "content": f"Результат инструмента {tool_name}:\n{tool_result_text}"})
                    reply_text, _ = await ask_gigachat(giga, messages)

    await giga.close()


def main() -> None:
    settings = load_settings()
    asyncio.run(chat_loop(settings))


if __name__ == "__main__":
    main()

