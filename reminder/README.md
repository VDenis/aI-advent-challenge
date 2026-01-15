# Reminder MCP stack

Два сервиса в Docker: MCP SSE сервер-планировщик и консольный Textual агент. Все команды — из `reminder/`.

## Требования
- Docker + Docker Compose, Make.
- GigaChat креды опциональны (LLM-саммари можно отключить `--no-llm`).

## Быстрый старт (3 шага)
1. Env: `cp .env.example .env` (переменные `MCP_MESSAGES_URL`, `MCP_SSE_URL`, опционально `GIGACHAT_*`).
2. Сервер: `make up` — поднимает MCP SSE на `:8000`, хранение в `./data/tasks.json`.
3. Клиент: `make run-client` — Textual TUI (`a` добавить, `r` обновить, `q` выйти). Остановить всё: `make down`.

## Добавление задач
- В клиенте нажмите `a`, введите текст и дату/время в ISO-8601 со смещением (например `2025-12-17T18:30:00+03:00`), затем `Сохранить`.
- Задачи автоматически сортируются, просроченные выделяются в сводке. SSE-подписка обновляет список; при недоступности SSE используйте `r`.
- Режим без LLM: `make run-client` можно заменить на `docker compose run --rm console poetry run python -m console_agent.app --no-llm`.

## Пример `data/tasks.json`
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "text": "Позвонить клиенту",
    "remind_at": "2025-12-17T18:30:00+03:00",
    "status": "pending",
    "created_at": "2025-12-16T12:00:00Z"
  }
]
```

## Структура
- `mcp_scheduler_server/` — FastAPI MCP SSE сервер (`/messages`, `/sse`), атомарное хранение в `data/tasks.json`.
- `console_agent/` — Textual TUI, подключение к MCP по SSE, резюме через GigaChat (или детерминированный fallback).
- `docker-compose.yml` — сервисы `mcp` и `console`, общий `.env`.
- `Makefile` — `make up`, `make run-client`, `make down`.

## Примечания
- Логи и данные задач лежат в `./data`; не коммить содержимое.
- Если не нужны GigaChat вызовы, оставьте токены пустыми и используйте `--no-llm` (клавиша `a` и прочая функциональность продолжат работать).

