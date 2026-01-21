"""Tests for SQLite storage."""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path

from chat_ollama_tg.storage import SQLiteStorage


@pytest_asyncio.fixture
async def storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        storage = SQLiteStorage(db_path=db_path, max_messages=5)
        await storage.init()
        yield storage
        await storage.close()


@pytest.mark.asyncio
async def test_add_and_get_message(storage: SQLiteStorage):
    """Test adding and retrieving messages."""
    chat_id = 12345

    # Add messages
    await storage.add_message(chat_id, "user", "Hello!")
    await storage.add_message(chat_id, "assistant", "Hi there!")

    # Get history
    history = await storage.get_history(chat_id)

    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "Hello!"
    assert history[1].role == "assistant"
    assert history[1].content == "Hi there!"


@pytest.mark.asyncio
async def test_clear_history(storage: SQLiteStorage):
    """Test clearing chat history."""
    chat_id = 12345

    # Add messages
    await storage.add_message(chat_id, "user", "Message 1")
    await storage.add_message(chat_id, "user", "Message 2")
    await storage.add_message(chat_id, "assistant", "Response")

    # Clear history
    count = await storage.clear_history(chat_id)

    assert count == 3

    # Verify empty
    history = await storage.get_history(chat_id)
    assert len(history) == 0


@pytest.mark.asyncio
async def test_history_limit(storage: SQLiteStorage):
    """Test that history is limited to max_messages."""
    chat_id = 12345

    # Add more messages than the limit (max_messages=5)
    for i in range(10):
        await storage.add_message(chat_id, "user", f"Message {i}")

    # Get history
    history = await storage.get_history(chat_id)

    # Should only have last 5 messages
    assert len(history) == 5

    # Check it's the latest messages
    assert history[0].content == "Message 5"
    assert history[-1].content == "Message 9"


@pytest.mark.asyncio
async def test_multiple_chats(storage: SQLiteStorage):
    """Test history is separate per chat."""
    chat_id_1 = 111
    chat_id_2 = 222

    # Add messages to different chats
    await storage.add_message(chat_id_1, "user", "Chat 1 message")
    await storage.add_message(chat_id_2, "user", "Chat 2 message")

    # Get histories
    history_1 = await storage.get_history(chat_id_1)
    history_2 = await storage.get_history(chat_id_2)

    assert len(history_1) == 1
    assert len(history_2) == 1
    assert history_1[0].content == "Chat 1 message"
    assert history_2[0].content == "Chat 2 message"


@pytest.mark.asyncio
async def test_set_and_get_model(storage: SQLiteStorage):
    """Test setting and getting model preference."""
    chat_id = 12345

    # Initially no model set
    model = await storage.get_chat_model(chat_id)
    assert model is None

    # Set model
    await storage.set_chat_model(chat_id, "mistral")

    # Get model
    model = await storage.get_chat_model(chat_id)
    assert model == "mistral"

    # Change model
    await storage.set_chat_model(chat_id, "llama3.2")
    model = await storage.get_chat_model(chat_id)
    assert model == "llama3.2"
