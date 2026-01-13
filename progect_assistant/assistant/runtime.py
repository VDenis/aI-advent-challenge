import json
import logging
import os
import shlex
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from .executor import ToolExecutionError, ToolExecutor
from .git_mcp import close_all_clients
from .mcp_client import MCPStdioClient, run_async
from .mcp_config import resolve_mcp_entry
from .help import build_help_response, help_menu
from .rag import RagIndexer, RagSearch
from .tools import ToolContext, ToolRegistry


@dataclass
class RuntimeConfig:
    project_root: str
    cache_path: str


class AgentRuntime:
    def __init__(self, config: RuntimeConfig, registry: ToolRegistry, logger: logging.Logger) -> None:
        self._config = config
        self._registry = registry
        self._logger = logger
        self._executor = ToolExecutor(registry, logger)
        self._rag_indexer = RagIndexer(config.project_root, config.cache_path)
        self._rag_index = None

    def run(self) -> None:
        print("Developer Assistant ready. Type /help for commands.")
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                close_all_clients()
                print("\nBye.")
                return

            if not user_input:
                continue
            if user_input == "/exit":
                close_all_clients()
                print("Bye.")
                return
            if user_input.startswith("/help"):
                self._handle_help(user_input)
                continue
            if user_input.startswith("/index"):
                self._handle_index()
                continue
            if user_input.startswith("/tool"):
                self._handle_tool(user_input)
                continue
            if user_input.startswith("/mcp"):
                self._handle_mcp(user_input)
                continue

            print("Unknown command. Type /help for options.")

    def _handle_index(self) -> None:
        self._rag_index = self._rag_indexer.build_index()
        print("RAG index built.")

    def _handle_help(self, user_input: str) -> None:
        parts = user_input.split(maxsplit=1)
        if len(parts) == 1:
            print(help_menu())
            return

        topic = parts[1]
        if self._rag_index is None:
            self._rag_index = self._rag_indexer.load_or_build()
        rag_search = RagSearch(self._rag_index)
        git_status = self._execute_tool("git_status", {})
        response = build_help_response(topic, rag_search, git_status)
        print(response["summary"])
        print(response["details"])

    def _handle_tool(self, user_input: str) -> None:
        parts = user_input.split(maxsplit=2)
        if len(parts) < 3:
            print("Usage: /tool <name> <json>")
            return
        name = parts[1]
        raw_params = parts[2]
        try:
            params = json.loads(raw_params)
        except json.JSONDecodeError:
            print("Invalid JSON parameters.")
            return
        result = self._execute_tool(name, params)
        print(json.dumps(result, ensure_ascii=True, indent=2))

    def _handle_mcp(self, user_input: str) -> None:
        parts = user_input.split(maxsplit=3)
        if len(parts) < 2:
            print("Usage: /mcp <list|call> [tool] [json]")
            return

        command = parts[1]
        entry = resolve_mcp_entry(
            self._config.project_root,
            "git",
            fallback_command=os.environ.get("GIT_MCP_COMMAND", ""),
        )
        mcp_command = entry.get("command", "")
        mcp_env = entry.get("env", {})
        if not mcp_command:
            print("MCP git command is not set. Configure progect_assistant/mcp_config.json.")
            return

        client = MCPStdioClient(
            command=shlex.split(mcp_command),
            name="git-mcp",
            env={"GIT_MCP_PROJECT_ROOT": self._config.project_root, **mcp_env},
        )
        if command == "list":
            tools = run_async(client.list_tools())
            run_async(client.close())
            print(json.dumps({"tools": tools}, ensure_ascii=True, indent=2))
            return

        if command == "call":
            if len(parts) < 4:
                print("Usage: /mcp call <tool> <json>")
                return
            tool_name = parts[2]
            try:
                params = json.loads(parts[3])
            except json.JSONDecodeError:
                print("Invalid JSON parameters.")
                return
            result = run_async(client.call_tool(tool_name, params))
            run_async(client.close())
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return

        print("Usage: /mcp <list|call> [tool] [json]")

    def _execute_tool(self, name: str, params: Dict[str, str]) -> Dict[str, str]:
        context = ToolContext(
            project_root=self._config.project_root,
            request_id=str(uuid.uuid4()),
        )
        try:
            return self._executor.execute(name, params, context)
        except ToolExecutionError as exc:
            return {"error": str(exc)}
