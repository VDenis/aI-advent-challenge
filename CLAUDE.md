# Памятка для Claude

## Контекст
- Монорепо демо: MCP сервер погоды (`weather_mcp`), LangChain агент на GigaChat (`weather_mcp_cli`), набор CLI/ботов (`cli`, `bots`), локальный Developer Assistant (`progect_assistant`), офлайн-анализатор данных (`eyes_ollama`) и персонализированный чат (`personal_chat`).
- Ассистент умеет работать как CLI, веб-UI и MCP сервер с RAG + git инструментами.
- eyes_ollama — CLI для анализа проектов (код, git, зависимости) и данных с Ollama LLM для аналитических вопросов.
- personal_chat — CLI чат с GigaChat, персонализацией через YAML-профиль, сохранением истории между сессиями, а также инструментами анализа проектов (`/scan`, `/search`, `/review`, `/metrics`).

## Подготовка окружения
- Python 3.10+. Базовые зависимости для погодного демо: `pip install -e .` из корня.
- Дополнительно при необходимости: `pip install -r cli/requirements.txt` (CLI/GigaChat/HF) и `pip install -r bots/requirements.txt` (Telegram-боты).
- Создай `.env` по `env.example` (GIGACHAT_*, HF_TOKEN/HF_BOT_TOKEN, GIGA_* и т.д.).
- Готовый шаблон для Claude Desktop в `progect_assistant/claude_desktop_config.json` — обнови `PROJECT_ROOT`, если путь другой.

## Как запускать
- MCP сервер погоды (Open-Meteo): `python -m weather_mcp.server`.
- GigaChat агент, который сам дергает MCP tools: `python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"`.
- Developer Assistant (CLI): `python -m progect_assistant.main`.
- Developer Assistant как MCP сервер: `python -m progect_assistant.mcp_server` (использует RAG + git MCP).
- Git MCP отдельно: `python -m progect_assistant.git_mcp_server`.
- Веб-UI ассистента: `python -m progect_assistant.web_server`.
- eyes_ollama (анализатор проекта): `python eyes_ollama/project_scanner.py scan .` и `python eyes_ollama/project_scanner.py ask . "вопрос"`.
- Personal Chat (персонализированный чат): `python -m personal_chat`.
  - В чате: `/scan <путь>` — сканировать проект, `/metrics` — метрики, `/search <запрос>` — поиск по файлам, `/review <файл>` — код-ревью через GigaChat.

## Тесты/проверки
- Автотестов почти нет: `pytest cli/tests/test_hf_llama3_openai.py` (нужны токены HF/OpenAI).
- Для дымовой проверки погоды запусти `python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"` — агент должен вызвать `get_current_weather`.
- Для проверки eyes_ollama: `python eyes_ollama/project_scanner.py scan . && python eyes_ollama/project_scanner.py ask . "сколько строк кода?"`.

## Примечания
- RAG индекс ассистента хранится в `progect_assistant/.cache/rag_index.json`; команда `/index` в CLI пересобирает его.
- Конфиг MCP для ассистента/гита/саппорта лежит в `progect_assistant/mcp_config.json`.
- Не коммить `.env`, логи (`progect_assistant/logs/`), `.cache/`, `venv*`, `venvmcp*`, `personal_chat/.config/`, `personal_chat/.history/`.
