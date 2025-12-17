# gigachat-mcp-weather

Демо-проект: MCP stdio сервер погоды (Open-Meteo, без API key) и LangChain‑агент на GigaChat, который сам вызывает MCP tools через `langchain-mcp-adapters`.

## Требования

- Python 3.10+
- Доступ к GigaChat API (`GIGACHAT_CREDENTIALS` base64(client_id:client_secret), `GIGACHAT_SCOPE`)
- Интернет‑доступ к https://api.open-meteo.com (без API key)

## Быстрый старт

1) Python 3.10+ и venv:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

2) Создай `.env` из шаблона `env.example`:

```
GIGACHAT_CREDENTIALS=base64(client_id:client_secret)
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL_CERTS=false  # true в проде, false локально/с самоподписанным
```

3) Запусти MCP сервер погоды (stdio):

```bash
python -m weather_mcp.server
```

4) Запусти CLI агента (агент сам подключится к серверу по stdio и выберет tools):

```bash
python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"
```

Альтернатива через entrypoints из `pyproject.toml`:

```bash
weather-mcp-server
gigachat-weather-agent "Какая сейчас температура и ветер в Москве?"
```

Ответ покажет:
- Логи вызовов tools (какой tool, с какими args, краткий результат).
- Финальный ответ модели.

## Что внутри

- `weather_mcp.server`: FastMCP stdio сервер с инструментами:
  - `get_current_weather(latitude, longitude, timezone?)` → текущая температура и ветер.
  - `get_hourly_forecast(latitude, longitude, hours<=168, timezone?)` → температура и влажность по часам.
  - httpx async клиент, таймауты и 2 попытки, валидация диапазонов.
  - Ошибки API возвращаются текстом в ответе tool, сервер не падает.
- `weather_mcp_cli.agent`: LangChain‑агент на GigaChat + MultiServerMCPClient. Модель умеет tool-calling (`llm.bind_tools(tools)`), цикл: `модель → tool_calls → выполнить tool → ToolMessage → модель` пока не появится финальный ответ. Стриминг отключён для устойчивого tool-calling. В system prompt добавлено правило: использовать инструменты для вопросов о погоде и не выдумывать значения. Для Москвы захардкожены координаты 55.75, 37.62.
- `weather_mcp_cli.main`: CLI. Пример: `python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"`.
- `env.example`: шаблон переменных окружения GigaChat.
- `pyproject.toml`: зависимости `fastmcp`, `mcp`, `httpx`, `langchain`, `langchain-community`, `langchain-mcp-adapters`, `python-dotenv`.
- Если tool-calling не срабатывает: убедись, что MCP сервер запущен в отдельном процессе и `.env` с GigaChat данными загружен (перезапусти CLI после изменения env).

## Пример вывода CLI

```
Tool calls:
1. get_current_weather args={'latitude': 55.75, 'longitude': 37.62} -> {"latitude": 55.75, "longitude": 37.62, "timezone": "GMT", "current": {...}}

Assistant:
В Москве сейчас около 4 °C, ветер 3 м/с. Могу показать почасовой прогноз?
```

## Acceptance checklist

- Запусти CLI агента:
  - `python -m weather_mcp_cli.main "Какая сейчас температура и ветер в Москве?"`
- В логах должно быть видно, что GigaChat сам инициировал вызов `get_current_weather` (и при необходимости `get_hourly_forecast`).
- Убедись, что ответ содержит данные из инструмента, а не придуманную погоду.
