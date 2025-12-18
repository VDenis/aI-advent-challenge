import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

import fcntl

from .models import Task

DEFAULT_DATA_PATH = Path(os.getenv("TASKS_FILE", Path(__file__).resolve().parent.parent / "data" / "tasks.json"))
LOCK_PATH = DEFAULT_DATA_PATH.with_suffix(".lock")


def ensure_data_files() -> None:
    DEFAULT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_DATA_PATH.exists():
        _write_raw([])


@contextmanager
def locked() -> Iterable[None]:
    ensure_data_files()
    lock_file = LOCK_PATH.open("w+")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _read_raw() -> List[Task]:
    if not DEFAULT_DATA_PATH.exists():
        return []
    raw = DEFAULT_DATA_PATH.read_text()
    if not raw.strip():
        return []
    items = json.loads(raw)
    return [Task(**item) for item in items]


def _write_raw(tasks: List[Task]) -> None:
    temp_path = DEFAULT_DATA_PATH.with_suffix(".tmp")
    data = [task.dict() for task in tasks]
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(temp_path, DEFAULT_DATA_PATH)


def read_tasks() -> List[Task]:
    with locked():
        return _read_raw()


def write_tasks(tasks: List[Task]) -> None:
    with locked():
        _write_raw(tasks)


def create_task(text: str, remind_at: str) -> Task:
    now_iso = datetime.now(timezone.utc).isoformat()
    new_task = Task(
        id=str(uuid.uuid4()),
        text=text,
        remind_at=remind_at,
        status="pending",
        created_at=now_iso,
    )
    with locked():
        tasks = _read_raw()
        tasks.append(new_task)
        _write_raw(tasks)
    return new_task


def set_task_status(task_id: str, status: str) -> Task:
    with locked():
        tasks = _read_raw()
        for idx, task in enumerate(tasks):
            if task.id == task_id:
                tasks[idx] = Task(**{**task.dict(), "status": status})
                _write_raw(tasks)
                return tasks[idx]
    raise KeyError(task_id)


def delete_task(task_id: str) -> None:
    with locked():
        tasks = _read_raw()
        updated = [task for task in tasks if task.id != task_id]
        _write_raw(updated)


def list_tasks() -> List[Task]:
    return read_tasks()
