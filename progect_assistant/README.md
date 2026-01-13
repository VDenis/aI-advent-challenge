# Developer Assistant

Local developer assistant with a minimal production-ready architecture: tool registry, safe tool execution, RAG search, and MCP-compatible git context.

## Structure

- `progect_assistant/main.py` - CLI entrypoint
- `progect_assistant/assistant/runtime.py` - dialog loop and command handling
- `progect_assistant/assistant/tools.py` - tool interface + registry
- `progect_assistant/assistant/executor.py` - safe tool execution + logging
- `progect_assistant/assistant/rag.py` - chunking, vector search, index
- `progect_assistant/assistant/git_mcp.py` - MCP-compatible git adapter
- `progect_assistant/assistant/tooling.py` - concrete tools
- `progect_assistant/assistant/help.py` - /help behavior

## Run

From the repository root:

```bash
python -m progect_assistant.main
```

Optional environment variables:

- `PROJECT_ROOT` (default: current working directory)
- `ASSISTANT_CACHE_PATH` (default: `progect_assistant/.cache/rag_index.json`)
- `ASSISTANT_LOG_PATH` (default: `progect_assistant/logs/assistant.log`)
- `MCP_CONFIG_PATH` (default: `progect_assistant/mcp_config.json`)
- `GIT_MCP_COMMAND` (fallback if JSON missing)

## Web UI

Run the local web UI:

```bash
python -m progect_assistant.web_server
```

Environment variables:

- `ASSISTANT_WEB_HOST` (default: `127.0.0.1`)
- `ASSISTANT_WEB_PORT` (default: `8088`)
- `OLLAMA_BASE_URL` (default: `http://localhost:11434/v1`)
- `OLLAMA_MODEL` (default: `llama3.1`)
- `OLLAMA_API_KEY` (optional)
- `HF_MODEL` (default: `meta-llama/Meta-Llama-3.1-8B-Instruct`)
- `HF_API_KEY` (required for Hugging Face calls)

## MCP git server

MCP config lives in `progect_assistant/mcp_config.json`:

```json
{
  "git": {
    "command": "python -m progect_assistant.git_mcp_server",
    "env": {
      "GIT_MCP_PROJECT_ROOT": "${PROJECT_ROOT}"
    }
  }
}
```

## Developer Assistant as MCP server

You can expose the assistant itself as an MCP server for Claude/Codex:

```bash
python -m progect_assistant.mcp_server
```

Tools exposed:

- `rag_search`
- `index_rag`
- `help`

## MCP client configs (templates)

Templates are provided in:

- `progect_assistant/claude_desktop_config.json`
- `progect_assistant/codex_mcp_config.json`

Update `PROJECT_ROOT` to match your local path if needed.

The assistant spawns the git MCP server on demand via `GIT_MCP_COMMAND`.
You can also run it manually over stdio:

```bash
python -m progect_assistant.git_mcp_server
```

Override the project root for the MCP server:

```bash
GIT_MCP_PROJECT_ROOT=/path/to/repo python -m progect_assistant.git_mcp_server
```

## Commands

- `/index` - build or refresh the RAG index
- `/help <topic>` - answer questions about setup/style/architecture/API with citations
- `/tool <name> <json>` - call a tool directly
- `/mcp list` - list MCP tools
- `/mcp call <tool> <json>` - call MCP tool directly
- `/exit` - quit

## RAG sources

By default the assistant indexes:

- `README.md`
- `docs/**`
- Project configs (`*.yaml`, `*.toml`, `*.json`, `.editorconfig`, etc.)
- Other markdown/text docs

## Example dialogue

```
> /index
RAG index built.
> /help setup
Found 3 relevant sources for 'setup'.
Branch: main
Sources:
- README.md [Getting Started]: ...
- docs/architecture.md [Setup]: ...
- pyproject.toml [file]: ...
> /help style
Found 2 relevant sources for 'style'.
Branch: main
Sources:
- .editorconfig [file]: ...
- docs/style.md [Guidelines]: ...
```

## Notes

- The git tools are wired through an MCP-compatible adapter, so you can swap in a real MCP client without changing core runtime.
- The assistant never fabricates project details; if it cannot find sources, it tells you.
