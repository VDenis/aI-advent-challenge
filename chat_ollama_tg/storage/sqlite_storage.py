"""SQLite storage for dialog history."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import aiosqlite

from ..llm.base import Message

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """SQLite-based storage for chat history."""

    def __init__(self, db_path: str, max_messages: int = 20):
        """
        Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file
            max_messages: Maximum messages to keep per chat
        """
        self._db_path = db_path
        self._max_messages = max_messages
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Initialize database and create tables."""
        # Ensure directory exists
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)

        # Enable foreign keys
        await self._db.execute("PRAGMA foreign_keys = ON")

        # Create tables
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                model TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
            )
        """)

        # Index for faster queries
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id
            ON messages(chat_id, created_at DESC)
        """)

        await self._db.commit()
        logger.info(f"Database initialized at {self._db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def _ensure_chat(self, chat_id: int) -> None:
        """Ensure chat exists in database."""
        if not self._db:
            raise RuntimeError("Database not initialized")

        await self._db.execute(
            "INSERT OR IGNORE INTO chats (chat_id) VALUES (?)",
            (chat_id,),
        )

    async def add_message(
        self,
        chat_id: int,
        role: Literal["system", "user", "assistant"],
        content: str,
    ) -> None:
        """
        Add a message to chat history.

        Args:
            chat_id: Telegram chat ID
            role: Message role
            content: Message content
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        await self._ensure_chat(chat_id)

        await self._db.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )

        # Update chat timestamp
        await self._db.execute(
            "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
            (datetime.now(timezone.utc).isoformat(), chat_id),
        )

        await self._db.commit()

        # Prune old messages if needed
        await self._prune_messages(chat_id)

    async def _prune_messages(self, chat_id: int) -> None:
        """Remove old messages beyond max_messages limit."""
        if not self._db:
            return

        # Count messages
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0

        if count > self._max_messages:
            # Delete oldest messages, keeping max_messages
            # Use id for ordering as it's auto-incrementing and more reliable than timestamp
            await self._db.execute("""
                DELETE FROM messages
                WHERE chat_id = ? AND id NOT IN (
                    SELECT id FROM messages
                    WHERE chat_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
            """, (chat_id, chat_id, self._max_messages))
            await self._db.commit()
            logger.debug(f"Pruned messages for chat {chat_id}: {count} -> {self._max_messages}")

    async def get_history(self, chat_id: int, limit: int | None = None) -> list[Message]:
        """
        Get chat history.

        Args:
            chat_id: Telegram chat ID
            limit: Max messages to return (default: max_messages)

        Returns:
            List of messages, oldest first
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        limit = limit or self._max_messages

        cursor = await self._db.execute("""
            SELECT role, content FROM (
                SELECT role, content, id
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
        """, (chat_id, limit))

        rows = await cursor.fetchall()

        return [Message(role=row[0], content=row[1]) for row in rows]

    async def clear_history(self, chat_id: int) -> int:
        """
        Clear chat history.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Number of messages deleted
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0

        await self._db.execute(
            "DELETE FROM messages WHERE chat_id = ?",
            (chat_id,),
        )
        await self._db.commit()

        logger.info(f"Cleared {count} messages for chat {chat_id}")
        return count

    async def get_chat_model(self, chat_id: int) -> str | None:
        """Get the model preference for a chat."""
        if not self._db:
            raise RuntimeError("Database not initialized")

        cursor = await self._db.execute(
            "SELECT model FROM chats WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()

        return row[0] if row else None

    async def set_chat_model(self, chat_id: int, model: str) -> None:
        """Set the model preference for a chat."""
        if not self._db:
            raise RuntimeError("Database not initialized")

        await self._ensure_chat(chat_id)

        await self._db.execute(
            "UPDATE chats SET model = ?, updated_at = ? WHERE chat_id = ?",
            (model, datetime.now(timezone.utc).isoformat(), chat_id),
        )
        await self._db.commit()

        logger.info(f"Set model for chat {chat_id}: {model}")

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        if not self._db:
            raise RuntimeError("Database not initialized")

        stats = {}

        cursor = await self._db.execute("SELECT COUNT(*) FROM chats")
        row = await cursor.fetchone()
        stats["total_chats"] = row[0] if row else 0

        cursor = await self._db.execute("SELECT COUNT(*) FROM messages")
        row = await cursor.fetchone()
        stats["total_messages"] = row[0] if row else 0

        return stats
