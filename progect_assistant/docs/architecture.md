# Developer Assistant architecture

This package is organized so Claude/Codex can quickly find responsibilities without digging through large files.

## Entry points
- `progect_assistant/main.py` — CLI that loads `AppConfig.from_env()` and starts the runtime.
- `progect_assistant/mcp_server.py` — exposes RAG + help over MCP (for Claude/Codex).
- `progect_assistant/support_mcp_server.py` — exposes support tools over MCP.
- `progect_assistant/web_server.py` — local web UI + MCP process manager.

## Package map
- `assistant/app.py` — wiring for logger, tool registry, runtime config (`AppConfig`, `create_runtime`).
- `assistant/core/` — runtime loop (`runtime.py`), tool registry/context (`registry.py`), safe executor (`executor.py`).
- `assistant/tools/builtin.py` — RAG search, git status/diff, safe file read.
- `assistant/tools/support.py` — FAQ/ticket tools and helpers.
- `assistant/rag/index.py` — chunking, index persistence, cosine search (`RagIndexer`, `RagSearch`).
- `assistant/mcp/` — stdio MCP client, config resolver, git MCP adapter (falls back to local git).
- `assistant/help.py` — `/help` behavior that combines RAG with git branch context.
- `assistant/llm.py` — HTTP client for OpenAI-compatible inference used by the web UI.

## Runtime flow
1) `main.py` loads env/config -> `create_runtime` -> `AgentRuntime.run()` dialog loop.
2) Commands `/index`, `/help`, `/tool`, `/mcp` are routed in `core/runtime.py`.
3) Tools run through `ToolExecutor` with logging/truncation safeguards.
4) Git context comes from `GitMCPAdapter` (MCP server if configured, otherwise local git).

## Defaults and storage
- `PROJECT_ROOT` defaults to `os.getcwd()`.
- RAG cache: `ASSISTANT_CACHE_PATH` -> `progect_assistant/.cache/rag_index.json`.
- Logs: `ASSISTANT_LOG_PATH` -> `progect_assistant/logs/assistant.log`.
- MCP config: `MCP_CONFIG_PATH` -> `progect_assistant/mcp_config.json`.
