"""Модуль для хранения истории разговоров."""

import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Message:
    """Сообщение в истории."""

    role: str  # "user" или "assistant"
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Conversation:
    """Разговор (сессия)."""

    id: str
    title: str
    messages: list[Message]
    created_at: str
    updated_at: str

    @classmethod
    def create_new(cls, title: str = "Новый разговор") -> "Conversation":
        """Создаёт новый разговор."""
        now = datetime.now().isoformat()
        conv_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return cls(
            id=conv_id,
            title=title,
            messages=[],
            created_at=now,
            updated_at=now,
        )

    def add_message(self, role: str, content: str) -> None:
        """Добавляет сообщение в разговор."""
        self.messages.append(Message(role=role, content=content))
        self.updated_at = datetime.now().isoformat()

    def get_messages_for_api(self, max_messages: int = 50) -> list[dict]:
        """Возвращает сообщения в формате для API."""
        messages = self.messages[-max_messages:] if max_messages else self.messages
        return [{"role": m.role, "content": m.content} for m in messages]

    def auto_title(self) -> None:
        """Автоматически генерирует заголовок из первого сообщения."""
        if self.messages and self.title == "Новый разговор":
            first_msg = self.messages[0].content
            self.title = first_msg[:50] + "..." if len(first_msg) > 50 else first_msg


class HistoryManager:
    """Менеджер истории разговоров."""

    def __init__(self, history_dir: Optional[Path] = None):
        self.history_dir = history_dir or (Path(__file__).parent / ".history")
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.current_conversation: Optional[Conversation] = None

    def _get_conversation_path(self, conv_id: str) -> Path:
        """Возвращает путь к файлу разговора."""
        return self.history_dir / f"{conv_id}.json"

    def _get_index_path(self) -> Path:
        """Возвращает путь к индексу разговоров."""
        return self.history_dir / "index.json"

    def save_conversation(self, conversation: Conversation) -> None:
        """Сохраняет разговор в файл."""
        path = self._get_conversation_path(conversation.id)

        data = {
            "id": conversation.id,
            "title": conversation.title,
            "messages": [asdict(m) for m in conversation.messages],
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self._update_index(conversation)

    def _update_index(self, conversation: Conversation) -> None:
        """Обновляет индекс разговоров."""
        index_path = self._get_index_path()

        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = {"conversations": []}

        # Обновляем или добавляем запись
        existing = next((c for c in index["conversations"] if c["id"] == conversation.id), None)

        entry = {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "message_count": len(conversation.messages),
        }

        if existing:
            index["conversations"] = [entry if c["id"] == conversation.id else c for c in index["conversations"]]
        else:
            index["conversations"].insert(0, entry)

        # Сортируем по дате обновления
        index["conversations"].sort(key=lambda x: x["updated_at"], reverse=True)

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def load_conversation(self, conv_id: str) -> Optional[Conversation]:
        """Загружает разговор из файла."""
        path = self._get_conversation_path(conv_id)

        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = [Message(**m) for m in data["messages"]]

        return Conversation(
            id=data["id"],
            title=data["title"],
            messages=messages,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def list_conversations(self, limit: int = 10) -> list[dict]:
        """Возвращает список последних разговоров."""
        index_path = self._get_index_path()

        if not index_path.exists():
            return []

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        return index["conversations"][:limit]

    def get_latest_conversation(self) -> Optional[Conversation]:
        """Возвращает последний разговор."""
        conversations = self.list_conversations(limit=1)
        if conversations:
            return self.load_conversation(conversations[0]["id"])
        return None

    def start_new_conversation(self, title: str = "Новый разговор") -> Conversation:
        """Начинает новый разговор."""
        self.current_conversation = Conversation.create_new(title)
        return self.current_conversation

    def continue_conversation(self, conv_id: Optional[str] = None) -> Optional[Conversation]:
        """Продолжает существующий разговор."""
        if conv_id:
            self.current_conversation = self.load_conversation(conv_id)
        else:
            self.current_conversation = self.get_latest_conversation()

        return self.current_conversation

    def delete_conversation(self, conv_id: str) -> bool:
        """Удаляет разговор."""
        path = self._get_conversation_path(conv_id)

        if path.exists():
            path.unlink()

            # Обновляем индекс
            index_path = self._get_index_path()
            if index_path.exists():
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)

                index["conversations"] = [c for c in index["conversations"] if c["id"] != conv_id]

                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(index, f, ensure_ascii=False, indent=2)

            return True

        return False

    def clear_all_history(self) -> None:
        """Очищает всю историю."""
        for file in self.history_dir.glob("*.json"):
            file.unlink()
        self.current_conversation = None
