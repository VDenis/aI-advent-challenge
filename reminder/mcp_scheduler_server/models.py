from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, validator


def _parse_dt(value: str) -> datetime:
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception as exc:  # pragma: no cover - user input validation
        raise ValueError("remind_at must be ISO-8601 with timezone offset") from exc


class Task(BaseModel):
    id: str
    text: str
    remind_at: str
    status: Literal["pending", "done"] = "pending"
    created_at: str

    @validator("remind_at", "created_at")
    def ensure_iso(cls, v: str) -> str:
        _parse_dt(v)
        return v


class TaskCreate(BaseModel):
    text: str = Field(..., min_length=1)
    remind_at: str

    @validator("remind_at")
    def parse_date(cls, v: str) -> str:
        _parse_dt(v)
        return v


class TaskIdRequest(BaseModel):
    id: str


class MessageRequest(BaseModel):
    tool: Literal["task_add", "task_list", "task_done", "task_delete"]
    arguments: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    type: Literal["result", "error"]
    content: Any
