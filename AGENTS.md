# Памятка для Codex и других агентов

## Быстрый контекст
- `weather_mcp`: FastMCP сервер с инструментами `get_current_weather` и `get_hourly_forecast` (Open-Meteo).
- `weather_mcp_cli`: LangChain агент на GigaChat, подключается к MCP по stdio.
- `progect_assistant`: локальный Developer Assistant (CLI, веб, MCP) с RAG и git инструментами; шаблоны клиентских конфигов в `progect_assistant/claude_desktop_config.json` и `progect_assistant/codex_mcp_config.json`.
- `cli/`: дополнительные консольные клиенты (GigaChat, HF/OpenAI) + тест `cli/tests/test_hf_llama3_openai.py`.
- `bots/`: Telegram-боты; `code_review/`: конфиг для AI code review; прочие папки (`rag_search`, `reminder`, `services`) — вспомогательные демо/утилиты.

## Установка и окружение
- Python 3.10+. Базово: `pip install -e .` в корне.
- Для CLI/ботов: `pip install -r cli/requirements.txt` и при необходимости `pip install -r bots/requirements.txt`.
- Создай `.env` из `env.example` (GIGACHAT_*, HF_TOKEN/HF_BOT_TOKEN, GIGA_* и др.).
- MCP шаблон для ассистента/гита/саппорта: `progect_assistant/mcp_config.json` (использует `PROJECT_ROOT`).

## Полезные команды
- MCP сервер погоды: `python -m weather_mcp.server`.
- Погодный агент: `python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"`.
- Ассистент CLI: `python -m progect_assistant.main`; как MCP сервер: `python -m progect_assistant.mcp_server`; веб-UI: `python -m progect_assistant.web_server`.
- Git MCP отдельно: `python -m progect_assistant.git_mcp_server`.

## Тесты и проверки
- `pytest cli/tests` (понадобятся токены HF/OpenAI).
- Быстрая ручная проверка: прогон погодного агента, чтобы увидеть вызов `get_current_weather`.

## Стиль и ограничения
- Python 3.10+, сохраняй типы и асинхронные паттерны в существующих модулях.
- Не трогай/не коммить `venv*/`, `venvmcp*/`, `.cache/`, `.env`, `progect_assistant/logs/` и другие артефакты окружения.
- Документацию держим краткой на русском, в Markdown.
