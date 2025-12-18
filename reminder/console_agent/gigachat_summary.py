import asyncio
import importlib
import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Type

import httpx
from dateutil import parser

logger = logging.getLogger(__name__)
DEBUG_LOG_PATH = "/Users/denis/code/ai_challenge/aI-advent-challenge/.cursor/debug.log"
DEBUG_LOG_PATH_CONTAINER = "/app/.cursor/debug.log"
DEBUG_SESSION_ID = "debug-session"
DEBUG_ENDPOINT = "http://127.0.0.1:7242/ingest/ec98a06e-67b1-4b48-bd2c-b7c2eaf724d4"


def _dbg_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": DEBUG_SESSION_ID,
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        # Try writing to host-mounted log file (works for local runs)
        try:
            os.makedirs(os.path.dirname(DEBUG_LOG_PATH), exist_ok=True)
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # Try writing to container path (Docker)
        try:
            os.makedirs(os.path.dirname(DEBUG_LOG_PATH_CONTAINER), exist_ok=True)
            with open(DEBUG_LOG_PATH_CONTAINER, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # Also try sending to debug server (works inside docker)
        try:
            httpx.post(
                DEBUG_ENDPOINT,
                json=payload,
                timeout=1,
            )
        except Exception:
            pass
        # Print to stdout/stderr so docker logs capture it even if file/endpoint unavailable
        try:
            print(f"[gigachat-debug] {location} {message} {json.dumps(payload.get('data', {}), ensure_ascii=False)}")
        except Exception:
            pass
    except Exception:
        pass
    # endregion


def parse_dt(value: str) -> datetime:
    return parser.isoparse(value)


def categorize_tasks(tasks: List[dict]) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    categorized = {"overdue": [], "today": [], "tomorrow": [], "later": []}
    for task in tasks:
        dt = parse_dt(task["remind_at"])
        if dt.date() < today:
            bucket = "overdue"
        elif dt.date() == today:
            bucket = "today"
        elif dt.date() == tomorrow:
            bucket = "tomorrow"
        else:
            bucket = "later"
        categorized[bucket].append(task)

    for bucket in categorized.values():
        bucket.sort(key=lambda t: parse_dt(t["remind_at"]))
    return categorized


def deterministic_summary(tasks: List[dict]) -> str:
    categorized = categorize_tasks(tasks)
    lines = []
    order = [("overdue", "Просрочено"), ("today", "Сегодня"), ("tomorrow", "Завтра"), ("later", "Позже")]
    for key, label in order:
        bucket = categorized[key]
        lines.append(f"{label}: {len(bucket)}")
        for task in bucket[:5]:
            dt = parse_dt(task["remind_at"]).isoformat()
            lines.append(f"  - {task['text']} @ {dt}")
    return "\n".join(lines)


def _load_gigachat_class() -> Optional[Type[object]]:
    """
    Пытаемся найти GigaChat в разных пакетах: официальном gigachat,
    а также в gigachain/langchain-community, чтобы не зависеть от конкретного импорта.
    """
    candidates = [
        ("gigachat", "GigaChat"),
        ("gigachain.chat_models.gigachat", "GigaChat"),
        ("langchain_community.chat_models.gigachat", "GigaChat"),
    ]
    for module_path, attr in candidates:
        try:
            module = importlib.import_module(module_path)
            clazz = getattr(module, attr)
            _dbg_log("H2", "gigachat_summary.py:_load_gigachat_class", "class_found", {"module": module_path})
            return clazz
        except Exception:
            continue
    _dbg_log("H2", "gigachat_summary.py:_load_gigachat_class", "class_not_found", {})
    return None


def _maybe_llm() -> object | None:
    gigachat_cls = _load_gigachat_class()
    if gigachat_cls is None:
        logger.warning("[gigachat] GigaChat class not found; check dependencies")
        return None

    token = os.getenv("GIGACHAT_TOKEN")
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    auth_url = os.getenv("GIGACHAT_AUTH_URL")
    model = os.getenv("GIGACHAT_MODEL")
    verify_ssl = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() == "true"

    # Клиент с токеном; client_id/client_secret библиотека не принимает, поэтому игнорируем
    if not token:
        _dbg_log("H1", "gigachat_summary.py:_maybe_llm", "missing_token", {})
        return None

    # Пробуем разные наборы параметров, т.к. сигнатуры библиотек могут отличаться.
    attempts = [
        {"credentials": token, "scope": scope, "auth_url": auth_url, "verify_ssl_certs": verify_ssl, "model": model},
        {"credentials": token, "scope": scope, "auth_url": auth_url, "verify_ssl": verify_ssl, "model": model},
        {"token": token, "scope": scope, "auth_url": auth_url, "verify": verify_ssl, "model": model},
    ]
    errors: list[Exception] = []
    for kwargs in attempts:
        # Убираем пустые значения, чтобы не сломать неожиданные сигнатуры
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        try:
            _dbg_log("H2", "gigachat_summary.py:_maybe_llm", "client_init_attempt", {"kwargs_keys": list(kwargs.keys())})
            return gigachat_cls(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            errors.append(exc)
            continue
    if errors:
        logger.error("[gigachat] failed to create client; last error: %s", errors[-1], exc_info=errors[-1])
        _dbg_log("H2", "gigachat_summary.py:_maybe_llm", "client_init_failed", {"error": str(errors[-1])})
    return None


def _chat_with_optional_context(llm: Any, prompt: str) -> Any:
    """
    Некоторые реализации GigaChat требуют контекстного менеджера (получение токена в __enter__).
    Если он есть, используем его, иначе просто вызываем .chat().
    """
    if hasattr(llm, "__enter__") and hasattr(llm, "__exit__"):
        with llm:  # type: ignore[call-arg]
            return llm.chat(prompt)  # type: ignore[attr-defined]
    return llm.chat(prompt)  # type: ignore[attr-defined]


async def _call_llm(llm: Any, prompt: str) -> str:
    # Пытаемся использовать доступные async/sync методы в порядке приоритета.
    if hasattr(llm, "ainvoke"):
        _dbg_log("H3", "gigachat_summary.py:_call_llm", "using_ainvoke", {})
        result = await llm.ainvoke(prompt)  # type: ignore[attr-defined]
        return _extract_content(result)

    if hasattr(llm, "achat"):
        _dbg_log("H3", "gigachat_summary.py:_call_llm", "using_achat", {})
        result = await llm.achat(prompt)  # type: ignore[attr-defined]
        return _extract_content(result)

    if hasattr(llm, "invoke"):
        _dbg_log("H3", "gigachat_summary.py:_call_llm", "using_invoke", {})
        result = await asyncio.to_thread(llm.invoke, prompt)  # type: ignore[attr-defined]
        return _extract_content(result)

    if hasattr(llm, "chat"):
        _dbg_log("H3", "gigachat_summary.py:_call_llm", "using_chat", {})
        result = await asyncio.to_thread(_chat_with_optional_context, llm, prompt)
        return _extract_content(result)

    raise RuntimeError("LLM client has no supported call method")


def _extract_content(result: Any) -> str:
    """
    Унифицируем извлечение текста из разных реализаций ответа GigaChat/LLM.
    """
    try:
        if hasattr(result, "content") and result.content:
            return str(result.content)

        # Структура типа ChatCompletion { choices: [ { message: { content }} ]}
        choices = getattr(result, "choices", None)
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message and getattr(message, "content", None):
                return str(message.content)

        return str(result)
    except Exception as exc:  # pragma: no cover
        _dbg_log("H3", "gigachat_summary.py:_extract_content", "extract_failed", {"error": str(exc)})
        return str(result)


async def summarize_tasks(tasks: List[dict], allow_llm: bool = True, return_meta: bool = False):
    """
    Возвращает краткое описание списка задач. Если return_meta=True,
    вернёт кортеж (summary, source) где source один из:
    - "gigachat" — запрос пошёл в LLM
    - "fallback" — использован детерминированный расчёт
    - "disabled" — LLM отключён флагом
    """

    _dbg_log(
        "H4",
        "gigachat_summary.py:summarize_tasks",
        "entry",
        {
            "allow_llm": allow_llm,
            "token_present": bool(os.getenv("GIGACHAT_TOKEN")),
            "scope": os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            "auth_url_set": bool(os.getenv("GIGACHAT_AUTH_URL")),
            "model_set": bool(os.getenv("GIGACHAT_MODEL")),
        },
    )

    if not allow_llm:
        summary = deterministic_summary(tasks)
        _dbg_log("H4", "gigachat_summary.py:summarize_tasks", "llm_disabled", {"source": "disabled"})
        return (summary, "disabled") if return_meta else summary

    llm = _maybe_llm()
    if not llm:
        _dbg_log("H4", "gigachat_summary.py:summarize_tasks", "llm_absent", {"source": "no_client"})
        raise RuntimeError("GigaChat client not available (missing token/SDK or bad init)")

    prompt = (
        "You summarize reminders grouped by time buckets: overdue, today, tomorrow, later. "
        "Be concise and include counts. Answer in Russian.\n"
        f"Tasks: {tasks}"
    )

    try:
        print("[gigachat] invoking LLM for summary...")
        summary = await _call_llm(llm, prompt)
        print("[gigachat] summary received.")
        _dbg_log("H3", "gigachat_summary.py:summarize_tasks", "llm_success", {})
        return (summary, "gigachat") if return_meta else summary
    except Exception as exc:
        logger.exception("[gigachat] failed, raising")
        _dbg_log("H3", "gigachat_summary.py:summarize_tasks", "llm_error", {"error": str(exc)})
        raise RuntimeError(f"GigaChat call failed: {exc}") from exc
