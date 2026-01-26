# gigachat-mcp-weather (монорепо демо‑проектов)

Монорепо с несколькими MCP/LLM демо: погодный сервер + агент на GigaChat, локальный Developer Assistant (CLI/web/MCP), AI code review, RAG примеры, веб/мобильная автоматизация, боты и офлайн-анализатор данных с Ollama.

## Состав монорепо
- `weather_mcp` + `weather_mcp_cli` — FastMCP сервер погоды (Open-Meteo) и LangChain агент на GigaChat.
- `progect_assistant/` — локальный Developer Assistant (CLI, web, MCP) с RAG и git инструментами. Шаблоны клиентов для Claude/Codex в `progect_assistant/claude_desktop_config.json` и `progect_assistant/codex_mcp_config.json`.
- `eyes_ollama/` — офлайн CLI-анализатор проектов и данных с Ollama LLM: анализ кода, git-истории, зависимостей + вопросы на естественном языке.
- `code_review/` — AI code review для GitHub PR (GigaChat + MCP GitHub).
- `rag_search/` — локальный RAG на FAISS + Ollama.
- `websearch/` — Textual TUI, который ищет через MCP Brave и суммаризирует через GigaChat MCP.
- `reminder/` — MCP SSE планировщик + Textual клиент в Docker.
- `mobileautomation/` — MCP orchestrator для Android эмулятора/ADB в Docker.
- `bots/` — Telegram/CLI демо, включая YouTube RAG бот (`bots/youtalk`).
- Памятки для агентов: `CLAUDE.md` и `AGENTS.md`.

## Быстрый старт: погода (GigaChat + MCP)
1. Python 3.10+ и окружение:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -e .
   cp env.example .env  # заполни GIGACHAT_* для GigaChat
   ```
2. Подними MCP сервер погоды:
   ```bash
   python -m weather_mcp.server
   ```
3. Запусти агента (auto tool-calling по stdio):
   ```bash
   python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"
   # или entrypoints: weather-mcp-server / gigachat-weather-agent
   ```
   В выводе должны быть логи `get_current_weather` и финальный ответ из данных инструмента.

## Быстрый старт: Developer Assistant
1. Установи зависимости (из корня): `pip install -e .`
2. CLI: `python -m progect_assistant.main`
3. MCP сервер: `python -m progect_assistant.mcp_server` (использует `progect_assistant/mcp_config.json`, переменная `PROJECT_ROOT` по умолчанию = текущая папка).
4. Web UI: `python -m progect_assistant.web_server` (порт 8088 по умолчанию).
5. Git MCP отдельно: `python -m progect_assistant.git_mcp_server`.

## Быстрый старт: eyes_ollama (анализатор проекта с Ollama)
1. Убедись, что Ollama запущена: `ollama serve`
2. Сканируй и анализируй проект:
   ```bash
   python eyes_ollama/project_scanner.py scan .
   python eyes_ollama/project_scanner.py ask . "какой модуль самый большой?"
   python eyes_ollama/project_scanner.py ask . "какие файлы чаще меняются?"
   python eyes_ollama/project_scanner.py chat .
   ```

## Acceptance (погодное демо)
- Запусти `python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"`
- Убедись, что агент сам вызвал `get_current_weather` (и при необходимости `get_hourly_forecast`) и ответ опирается на результаты инструмента.
