# WebSearch MCP Textual TUI

Консольное Textual-приложение, которое ищет через MCP Brave Search, делает саммари через MCP GigaChat и сохраняет результаты в файловую систему только через MCP Desktop Commander. Клиент общается с MCP по HTTP (JSON-RPC), без docker attach.

## Что внутри
- `docker-compose.yml` — сервисы `brave-search`, `desktop-commander`, `gigachat-summary` и `tui`.
- `cursor.json` — конфигурация MCP для Cursor (по-прежнему stdio-пример; для HTTP используйте прямые URL из .env).
- `tui/` — Textual TUI + клиенты MCP stdio.
- `mcp/gigachat-summary/` — MCP HTTP сервер (JSON-RPC) с tool `summarize(text, style, max_chars)` (использует GigaChat API с фолбэком).
- `output/` — папка для результатов (пишется через Desktop Commander, смонтирована в контейнер).

## Переменные окружения
Скопируйте `.env.example` в `.env` и заполните:
- `BRAVE_API_KEY` — ключ Brave Search.
- `GIGACHAT_API_KEY` — ключ GigaChat (если пусто — будет упрощённое фолбэк‑саммари).
- `GIGACHAT_API_URL`/`GIGACHAT_MODEL` — эндпоинт и модель GigaChat (по умолчанию OpenAI‑совместимый `chat/completions`).
- `PROJECT_ROOT` (по умолчанию `/workspace`) и `OUTPUT_DIR` (`/workspace/output`) — должны соответствовать точке монтирования в `desktop-commander`. Значения из старой версии (`/mnt/workspace`) автоматически нормализуются в TUI, но лучше обновить `.env`.
- `MCP_*_CONTAINER` — имена контейнеров для `docker attach` (совпадают с compose).

## Запуск
1. `cp .env.example .env` и заполните ключи/URL. `MCP_*_URL` можно указывать списком через запятую — клиент попробует последовательно (например `http://brave-search:3000,http://localhost:3001`). По умолчанию стоят адреса контейнеров, плюс код сам добавляет fallback на `localhost` (3001/3002/3003).
2. Поднимите MCP серверы: `docker compose up -d brave-search desktop-commander gigachat-summary`.
   - Для MCP HTTP обязателен путь `/mcp` в адресе. Пример: `http://brave-search:3000/mcp,http://localhost:3001/mcp`. В `docker-compose.yml` уже стоят такие значения по умолчанию, добавьте их и в свой `.env`.
   - Если запускаете TUI в контейнере, доступ к проброшенным портам на хосте есть по `host.docker.internal` (фолбэк зашит в код), поэтому можно не прописывать это вручную.
3. Запустите TUI интерактивно: `docker compose run --rm --service-ports tui` (важно именно `run`, а не `up`, иначе увидите только логи и ввод будет недоступен). После изменений пересоберите образ: `docker compose build tui`. При необходимости передайте `-e TERM=xterm-256color`.
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
