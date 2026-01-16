# Developer Assistant

Локальный ассистент с регистрацией инструментов, безопасным исполнением, RAG-поиском и MCP-совместимым git контекстом. Работает как CLI, веб-приложение и MCP сервер.

## Быстрый старт
1. Установка (из корня репо):
   ```bash
   pip install -e .
   ```
2. CLI:
   ```bash
   python -m progect_assistant.main
   ```
3. MCP сервер ассистента:
   ```bash
   python -m progect_assistant.mcp_server
   # конфиг: progect_assistant/mcp_config.json, PROJECT_ROOT берётся из окружения (по умолчанию cwd)
   ```
4. Веб-UI:
   ```bash
   python -m progect_assistant.web_server
   # OLLAMA_BASE_URL/OLLAMA_MODEL и HF_MODEL/HF_API_KEY настраиваются через env
   ```
5. Git MCP отдельно: `python -m progect_assistant.git_mcp_server`.

Полезные переменные окружения:
- `PROJECT_ROOT` (по умолчанию текущая директория)
- `ASSISTANT_CACHE_PATH` (по умолчанию `progect_assistant/.cache/rag_index.json`)
- `ASSISTANT_LOG_PATH` (по умолчанию `progect_assistant/logs/assistant.log`)
- `MCP_CONFIG_PATH` (по умолчанию `progect_assistant/mcp_config.json`)
- `GIT_MCP_COMMAND` (fallback для запуска git MCP из JSON)
- `GITHUB_TOKEN` (токен для GitHub Issues)
- `GITHUB_OWNER`/`GITHUB_REPO` или `GITHUB_REPOSITORY` (репозиторий для Issues)
- `GITHUB_API_BASE` (по умолчанию `https://api.github.com`)
- `GITHUB_DEFAULT_LABELS` (labels по умолчанию через запятую)

## Структура
- `progect_assistant/main.py` — CLI вход.
- `progect_assistant/assistant/app.py` — сборка логгера, реестра, рантайма.
- `assistant/core/` — цикл, реестр инструментов, executor.
- `assistant/tools/` — встроенные инструменты (RAG, git, file) + support.
- `assistant/rag/` — чанкинг, векторный поиск, индекс.
- `assistant/mcp/` — MCP клиент, конфиг резолвер, git adapter.
- `assistant/help.py` — поведение `/help`.
- Документация: `progect_assistant/docs/architecture.md`.

## MCP клиенты/конфиги
- Шаблоны для Claude/Codex: `progect_assistant/claude_desktop_config.json`, `progect_assistant/codex_mcp_config.json` (обнови `PROJECT_ROOT` под свою машину).
- Общий конфиг серверов: `progect_assistant/mcp_config.json` (assistant, git, support). Git MCP можно запустить вручную:
  ```bash
  GIT_MCP_PROJECT_ROOT=/path/to/repo python -m progect_assistant.git_mcp_server
  ```

## Команды (CLI)
- `/index` — собрать/обновить RAG индекс.
- `/help <topic>` — подсказки по setup/style/архитектуре с цитатами.
- `/tool <name> <json>` — вызвать инструмент напрямую.
- `/mcp list` и `/mcp call <tool> <json>` — операции MCP.
- `/exit` — выход.

## RAG источники по умолчанию
- `README.md`, `docs/**`, конфиги (`*.yaml`, `*.toml`, `*.json`, `.editorconfig`, etc.), другие markdown/text файлы.

## Notes
- Git инструменты идут через MCP-адаптер, его можно заменить на реальный MCP клиент.
- Ассистент не придумывает детали проекта: если нет источников — говорит об этом.

## GitHub Issues
Создание Issue доступно через `POST /api/github/create-issue` (в `progect_assistant/web_server.py`).
Payload строится из `user_query` и `assistant_answer`, при необходимости можно добавить `rag_context`,
`labels`, `findings` или `metadata`. Для MCP есть инструмент `create_github_issue`
в `progect_assistant/mcp_server.py` (использует `GITHUB_TOKEN` и `GITHUB_OWNER`/`GITHUB_REPO` или
`GITHUB_REPOSITORY` из окружения).
