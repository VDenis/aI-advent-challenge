#!/usr/bin/env python3
"""
eyes_ollama/analyzer.py — Офлайн CLI-анализатор данных с Ollama LLM.

Анализирует CSV/JSON/NDJSON/логи локально и отвечает на вопросы
на естественном языке через локальную Ollama модель.

Требования: Python 3.10+, запущенный Ollama (ollama serve).
"""

import argparse
import csv
import json
import re
import sys
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Iterator, Any

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gemma2:2b"
MAX_CONTEXT_ROWS = 100  # сколько строк данных показывать модели
MAX_SAMPLE_VALUES = 5   # примеров значений в schema


# ═══════════════════════════════════════════════════════════════════════════════
# ПАРСЕРЫ ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_format(file_path: Path) -> str:
    """Автодетект формата по расширению и содержимому."""
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        # Проверяем: массив JSON или NDJSON
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_char = f.read(1).strip()
            return "json" if first_char == "[" else "ndjson"
    if suffix in (".ndjson", ".jsonl"):
        return "ndjson"
    if suffix == ".log" or suffix == ".txt":
        return "log"
    # Пробуем угадать по содержимому
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        first_line = f.readline().strip()
        if first_line.startswith("{"):
            return "ndjson"
        if first_line.startswith("["):
            return "json"
        if "," in first_line and not re.search(r"\d{4}-\d{2}-\d{2}", first_line[:20]):
            return "csv"
    return "log"


def parse_csv(file_path: Path) -> Iterator[dict]:
    """Стриминговый парсер CSV."""
    with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield dict(row)


def parse_json(file_path: Path) -> Iterator[dict]:
    """Парсер JSON массива (загружает целиком, но выдаёт построчно)."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            yield data


def parse_ndjson(file_path: Path) -> Iterator[dict]:
    """Стриминговый парсер NDJSON/JSONL."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
            except json.JSONDecodeError:
                pass  # пропускаем битые строки


# Паттерны для парсинга логов
LOG_PATTERNS = [
    # ISO timestamp + level + message: 2024-01-15T10:30:45.123Z ERROR Something failed
    re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*Z?)\s+"
        r"(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\s+"
        r"(?P<message>.+)$",
        re.IGNORECASE
    ),
    # Syslog style: Jan 15 10:30:45 host service[pid]: message
    re.compile(
        r"^(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
        r"(?P<host>\S+)\s+(?P<service>\S+?)(?:\[(?P<pid>\d+)\])?:\s+"
        r"(?P<message>.+)$"
    ),
    # Simple: [LEVEL] message or LEVEL: message
    re.compile(
        r"^\[?(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\]?[:\s]+(?P<message>.+)$",
        re.IGNORECASE
    ),
]


def parse_log(file_path: Path) -> Iterator[dict]:
    """Парсер текстовых логов с авто-детектом формата."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip("\n\r")
            if not line:
                continue
            record = {"_raw": line, "_line": line_num}
            for pattern in LOG_PATTERNS:
                match = pattern.match(line)
                if match:
                    record.update(match.groupdict())
                    break
            yield record


def get_parser(fmt: str):
    """Возвращает парсер по формату."""
    parsers = {
        "csv": parse_csv,
        "json": parse_json,
        "ndjson": parse_ndjson,
        "log": parse_log,
    }
    return parsers.get(fmt, parse_log)


def load_data(file_path: Path, fmt: str | None = None, limit: int | None = None) -> list[dict]:
    """Загружает данные из файла с опциональным лимитом."""
    if fmt is None:
        fmt = detect_format(file_path)
    parser = get_parser(fmt)
    data = []
    for i, record in enumerate(parser(file_path)):
        data.append(record)
        if limit and i + 1 >= limit:
            break
    return data


def stream_data(file_path: Path, fmt: str | None = None) -> Iterator[dict]:
    """Стриминг данных для обработки больших файлов."""
    if fmt is None:
        fmt = detect_format(file_path)
    parser = get_parser(fmt)
    yield from parser(file_path)


# ═══════════════════════════════════════════════════════════════════════════════
# АНАЛИЗ ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_schema(data: list[dict]) -> dict:
    """Анализирует схему данных: поля, типы, примеры."""
    if not data:
        return {"fields": [], "row_count": 0}

    fields = {}
    all_keys = set()
    for record in data:
        all_keys.update(record.keys())

    for key in sorted(all_keys):
        values = [r.get(key) for r in data if r.get(key) is not None and r.get(key) != ""]
        if not values:
            fields[key] = {"type": "empty", "samples": [], "count": 0}
            continue

        # Определяем тип
        sample = values[0]
        if isinstance(sample, bool):
            dtype = "bool"
        elif isinstance(sample, int):
            dtype = "int"
        elif isinstance(sample, float):
            dtype = "float"
        elif isinstance(sample, str):
            # Пробуем распознать даты и числа в строках
            if re.match(r"^\d{4}-\d{2}-\d{2}", sample):
                dtype = "datetime"
            elif re.match(r"^-?\d+$", sample):
                dtype = "int(str)"
            elif re.match(r"^-?\d+\.\d+$", sample):
                dtype = "float(str)"
            else:
                dtype = "string"
        else:
            dtype = type(sample).__name__

        # Уникальные примеры
        unique_values = list(dict.fromkeys(str(v) for v in values))[:MAX_SAMPLE_VALUES]

        # Статистика для чисел
        stats = {}
        if dtype in ("int", "float", "int(str)", "float(str)"):
            try:
                nums = [float(v) for v in values]
                stats = {
                    "min": min(nums),
                    "max": max(nums),
                    "mean": round(mean(nums), 2),
                }
                if len(nums) > 1:
                    stats["median"] = round(median(nums), 2)
            except (ValueError, TypeError):
                pass

        # Диапазон дат
        if dtype == "datetime":
            try:
                dates = sorted(values)
                stats = {"min": dates[0], "max": dates[-1]}
            except:
                pass

        fields[key] = {
            "type": dtype,
            "samples": unique_values,
            "count": len(values),
            "unique": len(set(str(v) for v in values)),
            "stats": stats,
        }

    return {
        "fields": fields,
        "row_count": len(data),
        "columns": list(fields.keys()),
    }


def find_top_errors(
    file_path: Path,
    fmt: str | None = None,
    error_field: str | None = None,
    level_field: str = "level",
    message_field: str = "message",
    top_n: int = 10,
    error_levels: set[str] | None = None,
) -> list[dict]:
    """Находит самые частые ошибки."""
    if error_levels is None:
        error_levels = {"error", "fatal", "critical", "err", "crit"}

    error_counter = Counter()
    error_samples = {}
    total_errors = 0
    total_records = 0

    for record in stream_data(file_path, fmt):
        total_records += 1

        # Определяем, является ли запись ошибкой
        level = str(record.get(level_field, "")).lower()
        is_error = level in error_levels

        # Если нет поля level, ищем по ключевым словам в сообщении
        if not is_error and message_field in record:
            msg = str(record.get(message_field, "")).lower()
            is_error = any(kw in msg for kw in ["error", "exception", "failed", "failure"])

        if not is_error:
            continue

        total_errors += 1

        # Ключ для группировки
        if error_field and error_field in record:
            key = str(record[error_field])
        elif message_field in record:
            # Нормализуем сообщение: убираем ID, числа, UUID
            msg = str(record[message_field])
            key = re.sub(r"\b[0-9a-f]{8,}\b", "<ID>", msg, flags=re.IGNORECASE)
            key = re.sub(r"\b\d+\b", "<N>", key)
            key = key[:200]  # обрезаем длинные сообщения
        elif "_raw" in record:
            key = str(record["_raw"])[:200]
        else:
            key = str(record)[:200]

        error_counter[key] += 1
        if key not in error_samples:
            error_samples[key] = record

    results = []
    for msg, count in error_counter.most_common(top_n):
        results.append({
            "message": msg,
            "count": count,
            "percent": round(100 * count / total_errors, 1) if total_errors else 0,
            "sample": error_samples.get(msg, {}),
        })

    return {
        "top_errors": results,
        "total_errors": total_errors,
        "total_records": total_records,
        "error_rate": round(100 * total_errors / total_records, 2) if total_records else 0,
    }


def analyze_funnel(
    file_path: Path,
    steps: list[str],
    event_field: str = "event",
    user_field: str = "user_id",
    fmt: str | None = None,
) -> dict:
    """Анализ воронки: сколько пользователей прошло каждый шаг."""
    # Собираем события по пользователям
    user_events = defaultdict(set)
    event_counts = Counter()

    for record in stream_data(file_path, fmt):
        event = record.get(event_field)
        user = record.get(user_field)
        if event and user:
            user_events[user].add(event)
            event_counts[event] += 1

    # Считаем воронку
    funnel = []
    prev_count = None
    steps_set = set(steps)

    for i, step in enumerate(steps):
        # Пользователи, которые дошли до этого шага (и прошли все предыдущие)
        required_steps = set(steps[:i + 1])
        users_at_step = sum(
            1 for events in user_events.values()
            if required_steps <= events
        )

        drop_off = 0
        conversion = 100.0
        if prev_count is not None and prev_count > 0:
            drop_off = prev_count - users_at_step
            conversion = round(100 * users_at_step / prev_count, 1)

        funnel.append({
            "step": step,
            "users": users_at_step,
            "drop_off": drop_off,
            "conversion_from_prev": conversion,
            "conversion_from_start": round(100 * users_at_step / funnel[0]["users"], 1) if funnel and funnel[0]["users"] > 0 else 100.0,
        })
        prev_count = users_at_step

    return {
        "funnel": funnel,
        "total_users": len(user_events),
        "all_events": dict(event_counts.most_common(20)),
    }


def query_data(
    file_path: Path,
    fmt: str | None = None,
    filters: dict | None = None,
    group_by: str | None = None,
    count: bool = False,
    select_fields: list[str] | None = None,
    limit: int | None = None,
) -> dict:
    """Простые запросы: фильтрация, группировка, подсчёт."""
    results = []
    groups = Counter()
    total = 0
    matched = 0

    for record in stream_data(file_path, fmt):
        total += 1

        # Применяем фильтры
        if filters:
            skip = False
            for field, condition in filters.items():
                value = record.get(field, "")
                if isinstance(condition, str):
                    if condition.startswith("~"):
                        # Regex
                        if not re.search(condition[1:], str(value), re.IGNORECASE):
                            skip = True
                            break
                    elif str(value).lower() != condition.lower():
                        skip = True
                        break
                elif isinstance(condition, dict):
                    # Range: {"gte": x, "lte": y}
                    try:
                        num_val = float(value)
                        if "gte" in condition and num_val < condition["gte"]:
                            skip = True
                        if "lte" in condition and num_val > condition["lte"]:
                            skip = True
                        if "gt" in condition and num_val <= condition["gt"]:
                            skip = True
                        if "lt" in condition and num_val >= condition["lt"]:
                            skip = True
                    except (ValueError, TypeError):
                        skip = True
                    if skip:
                        break
            if skip:
                continue

        matched += 1

        if group_by:
            key = record.get(group_by, "<null>")
            groups[key] += 1
        elif not count:
            if select_fields:
                record = {k: record.get(k) for k in select_fields}
            results.append(record)
            if limit and len(results) >= limit:
                break

    if group_by:
        return {
            "groups": dict(groups.most_common()),
            "total_groups": len(groups),
            "total_matched": matched,
            "total_records": total,
        }
    elif count:
        return {
            "count": matched,
            "total_records": total,
        }
    else:
        return {
            "results": results,
            "count": len(results),
            "total_matched": matched,
            "total_records": total,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# OLLAMA ИНТЕГРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def call_ollama(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 120) -> str:
    """Вызов Ollama API."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,  # более детерминированные ответы для аналитики
            "num_predict": 2048,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response", "")
    except urllib.error.URLError as e:
        return f"[ОШИБКА] Не удалось подключиться к Ollama: {e}. Убедитесь, что ollama serve запущен."
    except Exception as e:
        return f"[ОШИБКА] {e}"


def build_analytics_prompt(
    question: str,
    schema: dict,
    sample_data: list[dict],
    stats: dict | None = None,
) -> str:
    """Строит промпт для аналитического вопроса."""

    # Форматируем схему
    schema_text = "СХЕМА ДАННЫХ:\n"
    for field, info in schema.get("fields", {}).items():
        schema_text += f"  - {field}: {info['type']}"
        if info.get("stats"):
            schema_text += f" (диапазон: {info['stats']})"
        if info.get("samples"):
            schema_text += f" примеры: {info['samples'][:3]}"
        schema_text += "\n"
    schema_text += f"Всего строк: {schema.get('row_count', '?')}\n"

    # Форматируем примеры данных
    sample_text = "\nПРИМЕРЫ ДАННЫХ (первые записи):\n"
    for i, row in enumerate(sample_data[:10], 1):
        # Компактное представление
        compact = {k: v for k, v in row.items() if v and k != "_raw"}
        sample_text += f"  {i}. {json.dumps(compact, ensure_ascii=False)[:300]}\n"

    # Дополнительная статистика если есть
    stats_text = ""
    if stats:
        stats_text = f"\nПРЕДВАРИТЕЛЬНАЯ СТАТИСТИКА:\n{json.dumps(stats, ensure_ascii=False, indent=2)}\n"

    prompt = f"""Ты — аналитик данных. Проанализируй данные и ответь на вопрос пользователя.

{schema_text}
{sample_text}
{stats_text}

ВОПРОС: {question}

Дай конкретный, структурированный ответ на основе данных. Если данных недостаточно для точного ответа, укажи это.
Используй числа и проценты где уместно. Будь кратким."""

    return prompt


def ask_analytics(
    question: str,
    file_path: Path,
    fmt: str | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Отвечает на аналитический вопрос по данным."""

    # Загружаем данные для контекста
    data = load_data(file_path, fmt, limit=MAX_CONTEXT_ROWS)
    if not data:
        return "Файл пуст или не удалось прочитать данные."

    schema = analyze_schema(data)

    # Предварительный анализ в зависимости от вопроса
    stats = None
    q_lower = question.lower()

    if any(kw in q_lower for kw in ["ошибк", "error", "fail", "exception"]):
        stats = find_top_errors(file_path, fmt)
    elif any(kw in q_lower for kw in ["воронк", "funnel", "теря", "drop", "конверс"]):
        # Пытаемся найти поля для воронки
        event_field = None
        for f in ["event", "action", "type", "event_type", "event_name"]:
            if f in schema["fields"]:
                event_field = f
                break
        if event_field:
            events = Counter()
            for row in data:
                if event_field in row:
                    events[row[event_field]] += 1
            stats = {"events_distribution": dict(events.most_common(15))}
    elif any(kw in q_lower for kw in ["групп", "group", "распредел", "по "]):
        # Ищем поле для группировки в вопросе
        for field in schema["fields"]:
            if field.lower() in q_lower:
                result = query_data(file_path, fmt, group_by=field)
                stats = result
                break

    prompt = build_analytics_prompt(question, schema, data, stats)
    return call_ollama(prompt, model)


# ═══════════════════════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ ВЫВОДА
# ═══════════════════════════════════════════════════════════════════════════════

def print_table(rows: list[dict], columns: list[str] | None = None, max_width: int = 40):
    """Печатает данные в виде таблицы."""
    if not rows:
        print("(нет данных)")
        return

    if columns is None:
        columns = list(rows[0].keys())

    # Вычисляем ширину колонок
    widths = {}
    for col in columns:
        values = [str(row.get(col, ""))[:max_width] for row in rows]
        widths[col] = max(len(col), max(len(v) for v in values))

    # Заголовок
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    separator = "-+-".join("-" * widths[col] for col in columns)

    print(header)
    print(separator)

    # Данные
    for row in rows:
        line = " | ".join(str(row.get(col, ""))[:max_width].ljust(widths[col]) for col in columns)
        print(line)


def format_output(data: Any, as_json: bool = False) -> str:
    """Форматирует вывод."""
    if as_json:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                lines.append(f"\n{key.upper()}:")
                # Таблица
                if value:
                    cols = list(value[0].keys())
                    # Фильтруем сложные вложенные поля
                    cols = [c for c in cols if not isinstance(value[0].get(c), (dict, list)) or c == "sample"]
                    for row in value:
                        row_str = " | ".join(f"{c}: {str(row.get(c, ''))[:50]}" for c in cols[:5])
                        lines.append(f"  {row_str}")
            elif isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    return str(data)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ИНТЕРФЕЙС
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_schema(args):
    """Показывает схему данных."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    data = load_data(file_path, args.format, limit=1000)
    schema = analyze_schema(data)

    if args.json:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        print(f"Файл: {file_path}")
        print(f"Формат: {args.format or detect_format(file_path)}")
        print(f"Строк (прочитано): {schema['row_count']}")
        print(f"\nПОЛЯ ({len(schema['fields'])}):")
        print("-" * 70)
        for field, info in schema["fields"].items():
            print(f"  {field}")
            print(f"    Тип: {info['type']}, Заполнено: {info['count']}, Уникальных: {info.get('unique', '?')}")
            if info.get("stats"):
                print(f"    Статистика: {info['stats']}")
            if info.get("samples"):
                print(f"    Примеры: {info['samples']}")
    return 0


def cmd_top_errors(args):
    """Показывает топ ошибок."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    result = find_top_errors(
        file_path,
        fmt=args.format,
        message_field=args.message_field,
        level_field=args.level_field,
        top_n=args.top,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"Всего записей: {result['total_records']}")
        print(f"Ошибок: {result['total_errors']} ({result['error_rate']}%)")
        print(f"\nТОП-{args.top} ОШИБОК:")
        print("=" * 70)
        for i, err in enumerate(result["top_errors"], 1):
            print(f"\n{i}. [{err['count']}x, {err['percent']}%]")
            print(f"   {err['message'][:200]}")
    return 0


def cmd_funnel(args):
    """Анализ воронки."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    steps = [s.strip() for s in args.steps.split(",")]
    result = analyze_funnel(
        file_path,
        steps=steps,
        event_field=args.event_field,
        user_field=args.user_field,
        fmt=args.format,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Всего пользователей: {result['total_users']}")
        print(f"\nВОРОНКА:")
        print("-" * 60)
        for step in result["funnel"]:
            bar = "█" * int(step["conversion_from_start"] / 5)
            print(f"  {step['step'][:25]:<25} {step['users']:>6} ({step['conversion_from_start']:>5.1f}%) {bar}")
            if step["drop_off"] > 0:
                print(f"  {'':25} ↓ -{step['drop_off']} ({100 - step['conversion_from_prev']:.1f}% потеряно)")

        print(f"\nВСЕ СОБЫТИЯ:")
        for event, count in result["all_events"].items():
            print(f"  {event}: {count}")
    return 0


def cmd_query(args):
    """Выполняет запрос."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    # Парсим фильтры
    filters = {}
    if args.filter:
        for f in args.filter:
            if "=" in f:
                key, val = f.split("=", 1)
                if val.startswith("~"):
                    filters[key] = val  # regex
                else:
                    filters[key] = val

    # Поля для выборки
    select = None
    if args.select:
        select = [s.strip() for s in args.select.split(",")]

    result = query_data(
        file_path,
        fmt=args.format,
        filters=filters,
        group_by=args.group_by,
        count=args.count,
        select_fields=select,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        if args.group_by:
            print(f"Группировка по: {args.group_by}")
            print(f"Всего групп: {result['total_groups']}")
            print(f"Matched: {result['total_matched']} / {result['total_records']}")
            print("-" * 40)
            for group, cnt in result["groups"].items():
                bar = "█" * min(50, cnt // max(1, result['total_matched'] // 50))
                print(f"  {str(group)[:30]:<30} {cnt:>6} {bar}")
        elif args.count:
            print(f"Count: {result['count']} / {result['total_records']}")
        else:
            print(f"Результатов: {result['count']} (из {result['total_matched']} matched, {result['total_records']} total)")
            if result["results"]:
                print_table(result["results"][:50])
    return 0


def cmd_ask(args):
    """Задаёт вопрос по данным через Ollama."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    question = " ".join(args.question)
    if not question:
        print("Укажите вопрос", file=sys.stderr)
        return 1

    print(f"Анализирую данные и спрашиваю {args.model}...\n")

    answer = ask_analytics(
        question,
        file_path,
        fmt=args.format,
        model=args.model,
    )

    if args.json:
        print(json.dumps({"question": question, "answer": answer}, ensure_ascii=False, indent=2))
    else:
        print("─" * 60)
        print(answer)
        print("─" * 60)
    return 0


def cmd_chat(args):
    """Интерактивный чат с вопросами по данным."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    # Предзагружаем данные
    print(f"Загружаю {file_path}...")
    data = load_data(file_path, args.format, limit=MAX_CONTEXT_ROWS)
    schema = analyze_schema(data)

    print(f"Загружено {schema['row_count']} строк, {len(schema['fields'])} полей")
    print(f"Модель: {args.model}")
    print("Введите вопрос (или 'exit' для выхода):\n")

    while True:
        try:
            question = input("❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q", "выход"):
            break

        # Специальные команды
        if question.lower() == "schema":
            print(format_output(schema))
            continue

        answer = ask_analytics(question, file_path, args.format, args.model)
        print(f"\n{answer}\n")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="analyzer",
        description="Офлайн анализатор данных с Ollama LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s schema data.csv
  %(prog)s top-errors logs.ndjson --top 20
  %(prog)s funnel events.json --steps "signup,onboarding,purchase"
  %(prog)s query data.csv --group-by status
  %(prog)s ask data.csv "какая ошибка чаще всего?"
  %(prog)s chat data.csv --model llama3.2
        """
    )

    parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # schema
    p_schema = subparsers.add_parser("schema", help="Показать схему данных")
    p_schema.add_argument("file", help="Путь к файлу данных")
    p_schema.add_argument("-f", "--format", choices=["csv", "json", "ndjson", "log"], help="Формат файла (авто)")
    p_schema.set_defaults(func=cmd_schema)

    # top-errors
    p_errors = subparsers.add_parser("top-errors", help="Топ частых ошибок")
    p_errors.add_argument("file", help="Путь к файлу данных")
    p_errors.add_argument("-f", "--format", choices=["csv", "json", "ndjson", "log"])
    p_errors.add_argument("-n", "--top", type=int, default=10, help="Количество (default: 10)")
    p_errors.add_argument("--message-field", default="message", help="Поле с сообщением")
    p_errors.add_argument("--level-field", default="level", help="Поле с уровнем")
    p_errors.set_defaults(func=cmd_top_errors)

    # funnel
    p_funnel = subparsers.add_parser("funnel", help="Анализ воронки")
    p_funnel.add_argument("file", help="Путь к файлу данных")
    p_funnel.add_argument("-f", "--format", choices=["csv", "json", "ndjson", "log"])
    p_funnel.add_argument("--steps", required=True, help="Шаги воронки через запятую")
    p_funnel.add_argument("--event-field", default="event", help="Поле события")
    p_funnel.add_argument("--user-field", default="user_id", help="Поле пользователя")
    p_funnel.set_defaults(func=cmd_funnel)

    # query
    p_query = subparsers.add_parser("query", help="Запрос к данным")
    p_query.add_argument("file", help="Путь к файлу данных")
    p_query.add_argument("-f", "--format", choices=["csv", "json", "ndjson", "log"])
    p_query.add_argument("--filter", action="append", help="Фильтр field=value (можно несколько)")
    p_query.add_argument("--group-by", help="Группировка по полю")
    p_query.add_argument("--count", action="store_true", help="Только подсчёт")
    p_query.add_argument("--select", help="Поля для вывода (через запятую)")
    p_query.add_argument("--limit", type=int, default=100, help="Лимит записей")
    p_query.set_defaults(func=cmd_query)

    # ask
    p_ask = subparsers.add_parser("ask", help="Задать вопрос по данным (Ollama)")
    p_ask.add_argument("file", help="Путь к файлу данных")
    p_ask.add_argument("question", nargs="+", help="Вопрос на естественном языке")
    p_ask.add_argument("-f", "--format", choices=["csv", "json", "ndjson", "log"])
    p_ask.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Модель Ollama (default: {DEFAULT_MODEL})")
    p_ask.set_defaults(func=cmd_ask)

    # chat
    p_chat = subparsers.add_parser("chat", help="Интерактивный чат по данным")
    p_chat.add_argument("file", help="Путь к файлу данных")
    p_chat.add_argument("-f", "--format", choices=["csv", "json", "ndjson", "log"])
    p_chat.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Модель Ollama (default: {DEFAULT_MODEL})")
    p_chat.set_defaults(func=cmd_chat)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
