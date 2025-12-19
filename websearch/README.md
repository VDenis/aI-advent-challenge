# WebSearch MCP Textual TUI

Консольное Textual-приложение, которое ищет через MCP Brave Search, делает саммари через MCP GigaChat и сохраняет результаты в файловую систему только через MCP Desktop Commander.

## Что внутри
- `docker-compose.yml` — сервисы `brave-search`, `desktop-commander`, `gigachat-summary` и `tui`.
- `cursor.json` — конфигурация MCP для Cursor (stdio через `docker run`).
- `tui/` — Textual TUI + клиенты MCP stdio.
- `mcp/gigachat-summary/` — MCP сервер с tool `summarize(text, style, max_chars)` (использует GigaChat API с фолбэком).
- `output/` — папка для результатов (пишется через Desktop Commander, смонтирована в контейнер).

## Переменные окружения
Скопируйте `.env.example` в `.env` и заполните:
- `BRAVE_API_KEY` — ключ Brave Search.
- `GIGACHAT_API_KEY` — ключ GigaChat (если пусто — будет упрощённое фолбэк‑саммари).
- `GIGACHAT_API_URL`/`GIGACHAT_MODEL` — эндпоинт и модель GigaChat (по умолчанию OpenAI‑совместимый `chat/completions`).
- `PROJECT_ROOT` (по умолчанию `/mnt/workspace`) и `OUTPUT_DIR` (`/mnt/workspace/output`) — должны соответствовать точке монтирования в `desktop-commander`.
- `MCP_*_CONTAINER` — имена контейнеров для `docker attach` (совпадают с compose).

## Запуск
1. `cp .env.example .env` и заполните ключи.
2. `docker compose up --build brave-search desktop-commander gigachat-summary` — запустить MCP серверы (stdin открыт для stdio).
3. В отдельном терминале: `docker compose run --rm tui` — запустить Textual TUI (русский интерфейс).
   - Клавиши: `Enter` — поиск, `s` — саммари, `w` — сохранить, `q` — выход.
4. Итоговые файлы попадают в `websearch/output/` на хосте через Desktop Commander.

## Предположения по GigaChat API
Используется OpenAI‑совместимый REST `chat/completions`:
```http
POST $GIGACHAT_API_URL
Authorization: Bearer $GIGACHAT_API_KEY
Content-Type: application/json
{
  "model": "GigaChat",
  "messages": [{"role": "system", ...}, {"role": "user", ...}],
  "temperature": 0.2,
  "max_tokens": ~max_chars/2
}
```
Если запрос не удался или ключ не задан — возвращается обрезанный фолбэк без выхода наружу.

## Почему `cursor.json`
Файл `websearch/cursor.json` добавляет три MCP сервера для Cursor через stdio (`docker run -i`). Пути/имена совпадают с docker‑compose и можно править при необходимости.
