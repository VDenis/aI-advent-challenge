# 💬 Chat Ollama - Локальные LLM через Ollama

Набор Python-программ для работы с локальными языковыми моделями через Ollama API.

## 📦 Содержимое

- **`ollama_demo.py`** — базовая программа для одиночных запросов к LLM
- **`chat_interactive.py`** — интерактивный чат с поддержкой истории диалога

## 🚀 Быстрый старт

### 1. Установка Ollama

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
- Скачать с [ollama.com/download](https://ollama.com/download/windows)

### 2. Запуск Ollama server

```bash
# В отдельном терминале
ollama serve
```

### 3. Загрузка модели

```bash
# Рекомендуемая модель (по умолчанию)
ollama pull qwen3:4b

# Альтернативы
ollama pull llama3.2:3b   # ~2 GB
ollama pull llama3.2:1b   # ~1.3 GB (самая лёгкая)
```

### 4. Проверка работоспособности

```bash
# Healthcheck базовой программы
python ollama_demo.py --healthcheck
```

## 📖 Использование

### `ollama_demo.py` - Базовая программа

Предназначена для одиночных запросов к LLM без сохранения контекста.

**Примеры:**

```bash
# Healthcheck - проверка всех компонентов
python ollama_demo.py --healthcheck

# Простой запрос
python ollama_demo.py --prompt "Что такое Python?"

# Использование другой модели
python ollama_demo.py --prompt "Explain quantum physics" --model llama3.2:1b

# С настройкой таймаута
python ollama_demo.py --prompt "Напиши длинную историю" --timeout 300
```

**Параметры:**
- `--prompt, -p` — текст запроса к модели (обязательный)
- `--model, -m` — имя модели (по умолчанию: `qwen3:4b`)
- `--host` — адрес Ollama (по умолчанию: `http://localhost:11434`)
- `--timeout, -t` — таймаут в секундах (по умолчанию: 120)
- `--healthcheck` — полная проверка работоспособности

**Ожидаемый вывод:**
```
💬 Запрос к модели 'qwen3:4b':
Что такое Python?

⏳ Генерация ответа...

🤖 Ответ модели:
Python - это высокоуровневый интерпретируемый язык программирования...
```

---

### `chat_interactive.py` - Интерактивный чат

Полноценный диалог с LLM с сохранением истории и контекста разговора.

**Режимы работы:**

#### 🎯 Тестовый режим (предопределенный диалог)

Автоматически проводит заранее подготовленный диалог с моделью:

```bash
python chat_interactive.py --test
```

**Что делает:**
1. Задаёт 4 предопределённых вопроса
2. Получает ответы с учётом контекста
3. Показывает всю историю диалога
4. Автоматически завершается

**Ожидаемый вывод:**
```
🤖 Запуск тестового диалога...
──────────────────────────────────────────────────────────────────────

[1] Вы:
Привет! Как тебя зовут?

⏳ Ожидание ответа...

[1] AI:
Привет! Я - языковая модель Qwen, созданная компанией Alibaba Cloud...

──────────────────────────────────────────────────────────────────────

[2] Вы:
Что ты умеешь делать?
...

✅ Тестовый диалог завершён!
Всего сообщений в истории: 8
```

#### 💬 Интерактивный режим

Свободный диалог с моделью в реальном времени:

```bash
python chat_interactive.py
```

**Интерактивные команды:**
- `exit` / `quit` — выход из чата
- `clear` — очистить историю диалога
- `history` — показать всю историю разговора
- `help` — показать справку
- `Ctrl+C` — прервать и выйти

**Пример сессии:**
```
💬 Ollama Interactive Chat
══════════════════════════════════════════════════════════════════════

Команды:
  exit или quit - выход из чата
  clear - очистить историю диалога
  history - показать всю историю диалога
  help - показать это сообщение

══════════════════════════════════════════════════════════════════════

ℹ  Используется модель: qwen3:4b
ℹ  Подключено к: http://localhost:11434

Вы: Привет! Объясни, что такое рекурсия простыми словами

⏳ Генерация ответа...

AI: Рекурсия — это когда функция вызывает саму себя...

Вы: А можешь привести пример на Python?

⏳ Генерация ответа...

AI: Конечно! Вот классический пример с факториалом...

Вы: exit

Выход из чата...
ℹ  Всего сообщений: 4

До свидания! 👋
```

**Параметры:**
- `--model, -m` — имя модели (по умолчанию: `qwen3:4b`)
- `--host` — адрес Ollama (по умолчанию: `http://localhost:11434`)
- `--timeout, -t` — таймаут в секундах (по умолчанию: 120)
- `--test` — запустить тестовый режим с предопределённым диалогом

---

## 🔍 Отличия программ

| Функция | ollama_demo.py | chat_interactive.py |
|---------|----------------|---------------------|
| Одиночные запросы | ✅ | ❌ |
| Диалог с историей | ❌ | ✅ |
| Healthcheck | ✅ | ❌ |
| Интерактивный режим | ❌ | ✅ |
| Тестовый диалог | ❌ | ✅ |
| API endpoint | `/api/generate` | `/api/chat` |
| Сохранение контекста | ❌ | ✅ |

## 🛠️ Технические детали

### Зависимости
- **Python 3.7+**
- Только стандартная библиотека (urllib, json)
- Никаких внешних пакетов!

### API Endpoints

**ollama_demo.py использует:**
- `GET /` — health check
- `GET /api/tags` — список моделей
- `POST /api/generate` — генерация без контекста

**chat_interactive.py использует:**
- `GET /` — health check
- `GET /api/tags` — список моделей
- `POST /api/chat` — генерация с контекстом и историей

### Обработка ошибок

Обе программы обрабатывают:
- ❌ Ollama не запущен
- ❌ Модель не найдена
- ❌ Таймаут запроса
- ❌ Ошибки сети/JSON
- ❌ HTTP ошибки

## 📝 Коды возврата

- `0` — успешное выполнение
- `1` — ошибка (Ollama недоступен, модель не найдена, ошибка генерации)

## 🎯 Сценарии использования

### Для разовых запросов
```bash
python ollama_demo.py --prompt "Объясни алгоритм быстрой сортировки"
```

### Для диалога с контекстом
```bash
python chat_interactive.py
```

### Для автоматического тестирования
```bash
python chat_interactive.py --test
```

### Для CI/CD проверок
```bash
python ollama_demo.py --healthcheck
if [ $? -eq 0 ]; then
    echo "Ollama готов к работе"
else
    echo "Ошибка: Ollama недоступен"
    exit 1
fi
```

## 🧪 Проверка работоспособности

### Полный тест

```bash
# 1. Запустить Ollama
ollama serve &

# 2. Загрузить модель
ollama pull qwen3:4b

# 3. Проверить через CLI
ollama run qwen3:4b "Say hello"

# 4. Healthcheck базовой программы
python ollama_demo.py --healthcheck

# 5. Тестовый диалог
python chat_interactive.py --test

# 6. Одиночный запрос
python ollama_demo.py --prompt "2+2=?"
```

## 💡 Советы

1. **Первый запуск**: всегда начинайте с `--healthcheck`
2. **Медленная модель**: попробуйте `llama3.2:1b` (легче и быстрее)
3. **Длинные ответы**: увеличьте `--timeout 300`
4. **История диалога**: в интерактивном режиме используйте `history`
5. **Очистка контекста**: если модель "запуталась", используйте `clear`

## 🐛 Troubleshooting

### Ollama не запущен
```bash
# Ошибка: Connection refused
ollama serve
```

### Модель не найдена
```bash
# Ошибка: model 'qwen3:4b' not found
ollama pull qwen3:4b
```

### Таймаут
```bash
# Увеличить таймаут
python ollama_demo.py --prompt "..." --timeout 300
```

### Порт занят
```bash
# Использовать другой порт (если запустили на 11435)
python ollama_demo.py --host http://localhost:11435 --prompt "..."
```

## 📚 Дополнительно

### Интеграция в Python код

```python
from ollama_demo import OllamaClient

client = OllamaClient()
response = client.generate("qwen3:4b", "Hello!")
print(response)
```

```python
from chat_interactive import OllamaChatClient

client = OllamaChatClient()
client.add_message("user", "Привет!")
response = client.chat("qwen3:4b", "Как дела?")
print(response)
```

### Список популярных моделей

```bash
# Лёгкие (< 3GB)
ollama pull llama3.2:1b      # 1.3 GB
ollama pull llama3.2:3b      # 2 GB
ollama pull phi3:mini        # 2.3 GB
ollama pull qwen2.5:3b       # 2 GB

# Средние (3-5GB)
ollama pull qwen3:4b         # 4 GB (рекомендуется)
ollama pull mistral:7b       # 4.1 GB
ollama pull llama3.1:8b      # 4.7 GB

# Мощные (> 7GB)
ollama pull llama3.1:13b     # 7.3 GB
ollama pull mixtral:8x7b     # 26 GB
```

## 📄 Лицензия

MIT

## 🤝 Поддержка

- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Ollama Models Library](https://ollama.com/library)

---

**Автор**: Senior Python Engineer
**Дата**: 2026-01-20
