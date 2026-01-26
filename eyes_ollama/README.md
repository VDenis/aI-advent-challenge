# eyes_ollama — Офлайн анализатор проектов с Ollama

CLI-утилиты для анализа кодовых баз и данных с возможностью задавать аналитические вопросы на естественном языке через локальную Ollama LLM.

## Файлы

- `project_scanner.py` — анализ кодовой базы, git-истории, зависимостей
- `analyzer.py` — анализ данных (CSV, JSON, NDJSON, логи)

## Требования

- Python 3.10+
- Ollama (`ollama serve`) для команд `ask` и `chat`
- Только стандартная библиотека Python (без внешних зависимостей)

---

## project_scanner.py — Анализ проекта

Собирает метрики исходного кода, git-истории и зависимостей.

### Быстрый старт

```bash
# 1. Запусти Ollama
ollama serve

# 2. Сканирование проекта (сохраняет project_analysis.json)
python project_scanner.py scan .

# 3. Вопросы о проекте
python project_scanner.py ask . "какой модуль самый большой?"
python project_scanner.py ask . "какие файлы чаще всего меняются?"
python project_scanner.py ask . "кто больше всех коммитит?"
python project_scanner.py ask . "какие зависимости используются?"
python project_scanner.py ask . "где больше всего TODO?"

# 4. Интерактивный чат
python project_scanner.py chat .
```

### Что собирает

| Категория | Метрики |
|-----------|---------|
| **Код** | Файлы, строки, функции, классы, импорты, сложность, TODO/FIXME |
| **Git** | Коммиты, авторы, типы изменений, часто меняющиеся файлы |
| **Зависимости** | requirements.txt, pyproject.toml, setup.py |

### Примеры вопросов

```
какой модуль самый большой?
какие файлы чаще всего меняются?
кто основной контрибьютор?
какие внешние библиотеки используются?
где больше всего TODO?
какие функции самые сложные?
сколько всего строк кода?
```

---

## analyzer.py — Анализ данных

Анализирует CSV, JSON, NDJSON, логи.

### Команды

- **schema** — структура данных, типы полей, примеры значений
- **top-errors** — частые ошибки в логах
- **funnel** — анализ воронок
- **query** — фильтрация, группировка, подсчёт
- **ask** — вопросы через Ollama
- **chat** — интерактивный режим

### Примеры

```bash
python analyzer.py schema data.csv
python analyzer.py top-errors logs.ndjson --top 15
python analyzer.py query data.csv --group-by status
python analyzer.py funnel events.json --steps "signup,activate,purchase"
python analyzer.py ask logs.ndjson "какая ошибка чаще всего?"
python analyzer.py chat data.csv --model llama3.2
```

---

## Опции вывода

- `--json` — машиночитаемый JSON вывод
- Таблицы с фиксированной шириной для консоли
