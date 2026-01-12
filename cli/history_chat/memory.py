from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 3


def iso_now() -> str:
    """Return timezone-aware ISO timestamp."""
    return datetime.now(tz=timezone.utc).astimezone().isoformat()


def _parse_iso_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


@dataclass
class SessionRecord:
    session_id: str
    created_at: str
    updated_at: str
    model_name: Optional[str] = None
    api_base_url: Optional[str] = None
    first_user_message: str = ""
    title: str = ""
    summary: str = ""
    user_turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    is_active: bool = False
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["SessionRecord"]:
        try:
            return cls(
                session_id=str(data["session_id"]),
                created_at=str(data["created_at"]),
                updated_at=str(data.get("updated_at", data["created_at"])),
                model_name=data.get("model_name"),
                api_base_url=data.get("api_base_url"),
                first_user_message=data.get("first_user_message", ""),
                title=data.get("title", data.get("first_user_message", "")),
                summary=data.get("summary", ""),
                user_turns=int(data.get("user_turns", 0) or 0),
                total_input_tokens=int(data.get("total_input_tokens", 0) or 0),
                total_output_tokens=int(data.get("total_output_tokens", 0) or 0),
                is_active=bool(data.get("is_active", False)),
                messages=list(data.get("messages", [])) if isinstance(data.get("messages", []), list) else [],
            )
        except Exception:
            return None


@dataclass
class MemoryStore:
    schema_version: int = SCHEMA_VERSION
    sessions: List[SessionRecord] = field(default_factory=list)
    active_session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "sessions": [s.to_dict() for s in self.sessions],
        }
        if self.active_session_id:
            payload["active_session_id"] = self.active_session_id
        return payload


def load_memory(path: Path, *, logger: Optional[logging.Logger] = None) -> MemoryStore:
    """
    Load memory file. If missing or invalid, return empty store and keep file untouched.
    """
    if not path.exists():
        return MemoryStore()

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.warning("Cannot read memory file %s: %s", path, exc)
        return MemoryStore()

    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.warning("Memory file %s is not valid JSON: %s", path, exc)
        return MemoryStore()

    if not isinstance(data, dict):
        if logger:
            logger.warning("Memory file %s has unexpected structure, starting fresh.", path)
        return MemoryStore()

    schema_version = data.get("schema_version")
    if schema_version not in {None, 2, SCHEMA_VERSION}:
        if logger:
            logger.warning(
                "Unknown memory schema version %s (expected %s). Ignoring file.",
                schema_version,
                SCHEMA_VERSION,
            )
        return MemoryStore()

    sessions_payload = data.get("sessions")
    if isinstance(sessions_payload, list):
        sessions = [s for item in sessions_payload if (s := SessionRecord.from_dict(item))]
        return MemoryStore(
            schema_version=SCHEMA_VERSION,
            sessions=sessions,
            active_session_id=data.get("active_session_id"),
        )

    # Fallback: legacy single-session structure with a summary field.
    if "summary" in data:
        summary_text = str(data.get("summary") or "").strip()
        if summary_text:
            session = SessionRecord(
                session_id=data.get("session_id") or data.get("id") or "legacy",
                created_at=data.get("updated_at") or iso_now(),
                updated_at=data.get("updated_at") or iso_now(),
                model_name=data.get("model_name"),
                api_base_url=data.get("api_base_url"),
                first_user_message=data.get("first_user_message", ""),
                title=data.get("title", data.get("first_user_message", "")),
                summary=summary_text,
                user_turns=int(data.get("user_turns", 0) or 0),
                total_input_tokens=int(data.get("total_input_tokens", 0) or 0),
                total_output_tokens=int(data.get("total_output_tokens", 0) or 0),
                is_active=False,
            )
            if logger:
                logger.info("Migrated legacy memory file %s into a single session.", path)
            return MemoryStore(schema_version=SCHEMA_VERSION, sessions=[session])

    if logger:
        logger.warning("Memory file %s is incompatible. Starting with empty memory.", path)
    return MemoryStore()


def save_memory(store: MemoryStore, path: Path, *, backup: bool = True, logger: Optional[logging.Logger] = None) -> None:
    """
    Atomically persist the memory store using write-then-replace with optional backup.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(store.to_dict(), fh, ensure_ascii=False, indent=2)

        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            try:
                shutil.copy2(path, backup_path)
            except Exception as exc:  # noqa: BLE001
                if logger:
                    logger.warning("Failed to write backup %s: %s", backup_path, exc)

        os.replace(tmp_path, path)
    finally:
        # If replace failed, ensure temporary file is removed.
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def upsert_session(store: MemoryStore, session: SessionRecord) -> MemoryStore:
    store.sessions = [s for s in store.sessions if s.session_id != session.session_id]
    store.sessions.append(session)
    return store


def delete_session(store: MemoryStore, session_id: str) -> MemoryStore:
    store.sessions = [s for s in store.sessions if s.session_id != session_id]
    if store.active_session_id == session_id:
        store.active_session_id = None
    return store


def sorted_sessions(store: MemoryStore) -> List[SessionRecord]:
    return sorted(
        store.sessions,
        key=lambda s: _parse_iso_dt(s.updated_at or s.created_at),
        reverse=True,
    )


def recent_sessions(store: MemoryStore, limit: int) -> List[SessionRecord]:
    return sorted_sessions(store)[:limit]


def find_session(store: MemoryStore, session_id: str) -> Optional[SessionRecord]:
    for session in store.sessions:
        if session.session_id == session_id:
            return session
    return None

