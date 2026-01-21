# Chat Ollama Telegram Bot

Telegram-бот с локальной языковой моделью. Генерация ответов происходит полностью офлайн через Ollama или llama.cpp.

## Возможности

- 🤖 Локальная генерация через Ollama (по умолчанию) или llama.cpp
- 💬 История диалога (SQLite) с ограничением по количеству сообщений
- 🔄 Переключение между моделями на лету
- ⚡ Асинхронная архитектура (aiogram 3.x + asyncio)
- 📊 Логирование в файл

## Требования

- Python 3.11+
- [Ollama](https://ollama.com/) (для режима ollama) или [llama.cpp](https://github.com/ggerganov/llama.cpp) (для режима llamacpp)
- Telegram Bot Token (от [@BotFather](https://t.me/BotFather))

## Быстрый старт

### 1. Установка Ollama

#### macOS
```bash
brew install ollama
```

#### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### Windows
Скачайте установщик с [ollama.com/download](https://ollama.com/download)

### 2. Скачивание модели

```bash
# Запустите Ollama (если не запущен как сервис)
ollama serve

# В другом терминале скачайте модель
ollama pull llama3.2

# Проверьте, что модель работает
ollama run llama3.2 "Привет!"
```

Другие рекомендуемые модели:
- `mistral` — быстрая, хорошее качество
- `gemma2` — от Google, компактная
- `phi3` — от Microsoft, очень быстрая
- `qwen2` — от Alibaba, хорошо знает русский

### 3. Создание Telegram бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям, выберите имя и username
4. Скопируйте токен (вида `123456789:ABCdefGHI...`)

### 4. Установка зависимостей

```bash
cd chat_ollama_tg
pip install -r requirements.txt
```

### 5. Настройка

```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Отредактируйте .env
nano .env  # или любой текстовый редактор
```

Минимальная настройка:
```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
OLLAMA_MODEL=llama3.2
```

### 6. Запуск

```bash
# Из директории проекта (родительской для chat_ollama_tg)
python -m chat_ollama_tg

# Или из директории chat_ollama_tg
cd chat_ollama_tg
python -m chat_ollama_tg
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и инструкция |
| `/help` | Справка по командам |
| `/reset` | Очистить историю диалога |
| `/model` | Показать текущую модель и движок |
| `/setmodel <имя>` | Сменить модель |

## Конфигурация

### Переменные окружения (.env)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TELEGRAM_BOT_TOKEN` | — | **Обязательно.** Токен бота |
| `LLM_ENGINE` | `ollama` | Движок: `ollama` или `llamacpp` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL Ollama API |
| `OLLAMA_MODEL` | `llama3.2` | Модель по умолчанию |
| `LLAMACPP_MODEL_PATH` | — | Путь к GGUF модели |
| `LLAMACPP_CLI_PATH` | `llama-cli` | Путь к llama-cli |
| `MAX_HISTORY_MESSAGES` | `20` | Лимит истории |
| `MAX_RESPONSE_TOKENS` | `1024` | Макс. токенов в ответе |
| `LLM_TIMEOUT` | `120` | Таймаут генерации (сек) |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

## Использование llama.cpp

Если предпочитаете llama.cpp вместо Ollama:

### 1. Установка llama.cpp

```bash
# macOS/Linux
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
make -j

# Или через Homebrew (macOS)
brew install llama.cpp
```

### 2. Скачивание модели GGUF

Скачайте модель с [Hugging Face](https://huggingface.co/models?search=gguf), например:
- [Llama-3.2-3B-Instruct-GGUF](https://huggingface.co/lmstudio-community/Llama-3.2-3B-Instruct-GGUF)
- [Mistral-7B-Instruct-v0.3-GGUF](https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.3-GGUF)

### 3. Настройка .env

```env
LLM_ENGINE=llamacpp
LLAMACPP_MODEL_PATH=/path/to/model.gguf
LLAMACPP_CLI_PATH=/path/to/llama.cpp/llama-cli
LLAMACPP_N_CTX=4096
LLAMACPP_N_PREDICT=512
```

## Структура проекта

```
chat_ollama_tg/
├── __init__.py          # Версия пакета
├── __main__.py          # Точка входа
├── config.py            # Загрузка конфигурации
├── requirements.txt     # Зависимости
├── .env.example         # Пример конфигурации
├── pytest.ini           # Настройки pytest
├── bot/
│   ├── __init__.py
│   └── handlers.py      # Обработчики команд Telegram
├── llm/
│   ├── __init__.py
│   ├── base.py          # Базовый класс адаптера
│   ├── ollama.py        # Адаптер Ollama
│   ├── llamacpp.py      # Адаптер llama.cpp
│   └── factory.py       # Фабрика адаптеров
├── storage/
│   ├── __init__.py
│   └── sqlite_storage.py # SQLite хранилище истории
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_storage.py  # Тесты хранилища
│   └── test_llm.py      # Тесты LLM адаптеров
├── logs/                # Логи (создаётся автоматически)
└── data/                # База данных (создаётся автоматически)
```

## Запуск тестов

```bash
cd chat_ollama_tg
pip install -r requirements.txt
pytest -v
```

## Пример диалога

```
Пользователь: /start

Бот: 👋 Привет! Я бот-ассистент с локальной языковой моделью.
     Я работаю на базе Ollama/llama.cpp и могу отвечать на ваши
     вопросы полностью офлайн (генерация происходит локально).
     ...

Пользователь: Что такое Python?

Бот: Python — это высокоуровневый язык программирования общего
     назначения с динамической типизацией. Он известен своим
     простым и читаемым синтаксисом, что делает его отличным
     выбором как для начинающих, так и для опытных разработчиков.
     ...

Пользователь: /model

Бот: 🤖 Информация о модели:
     • Движок: ollama
     • Модель: llama3.2

     📋 Доступные модели:
       • llama3.2
       • mistral
       • gemma2

Пользователь: /setmodel mistral

Бот: ✅ Модель изменена на mistral

Пользователь: /reset

Бот: 🗑 История очищена (5 сообщений удалено). Начнём сначала!
```

## Важные примечания

### Офлайн vs Онлайн

- **Генерация текста** происходит **локально** — модель работает на вашем компьютере
- **Telegram API** требует **интернет** — для получения и отправки сообщений нужна связь с серверами Telegram

Это означает:
- Ваши диалоги не отправляются на сторонние LLM-сервисы (OpenAI, Anthropic и т.д.)
- Но Telegram видит все сообщения (как и в любом Telegram-боте)
- Для полной приватности используйте self-hosted альтернативы Telegram

### Производительность

- Первый запрос может быть медленным (загрузка модели в память)
- Скорость зависит от: размера модели, количества RAM/VRAM, CPU/GPU
- Рекомендации:
  - Для слабых машин: `phi3`, `gemma2:2b`
  - Для средних: `llama3.2:3b`, `mistral:7b`
  - Для мощных с GPU: `llama3.2:8b`, `qwen2:72b`

### Ограничения

- Telegram ограничивает длину сообщения (4096 символов) — длинные ответы автоматически разбиваются
- История хранит только последние N сообщений (настраивается)
- При перезапуске бота история сохраняется (SQLite)

## Устранение неполадок

### "Ollama не запущен"

```bash
# Проверьте статус
curl http://localhost:11434/api/tags

# Запустите Ollama
ollama serve
```

### "Модель не найдена"

```bash
# Скачайте модель
ollama pull llama3.2

# Проверьте список моделей
ollama list
```

### "Таймаут генерации"

Увеличьте таймаут в `.env`:
```env
LLM_TIMEOUT=300
```

Или используйте более быструю модель:
```env
OLLAMA_MODEL=phi3
```

### Логи

Логи записываются в `chat_ollama_tg/logs/bot.log`:
```bash
tail -f chat_ollama_tg/logs/bot.log
```

## Лицензия

MIT
