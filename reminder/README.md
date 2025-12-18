# Reminder MCP stack

Два сервиса в Docker: MCP SSE сервер-планировщик и консольный Textual агент. Все пути и команды запускаются из папки `reminder/`.

## Быстрый старт (3 шага)
- Скопируйте переменные: `cp .env.example .env` и заполните GigaChat креды (или оставьте пустыми и используйте `--no-llm`).
- Поднимите сервер: `make up` (стартует `mcp` на `:8000`, том `./data/tasks.json`).
- Запустите клиента: `make run-client` (Textual TUI; клавиши `a` — добавить задачу, `r` — обновить, `q` — выйти). Остановить всё: `make down`.

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
