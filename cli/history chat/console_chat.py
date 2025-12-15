"""Console chat client for GigaChat.

Run:
    python "cli/history chat/console_chat.py"

Required in `.env`:
- GIGA_CLIENT_BASIC=base64(client_id:client_secret)
Optional: GIGA_API_BASE_URL, GIGA_VERIFY_SSL, GIGA_MODEL_NAME, etc.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Settings, load_settings
from services.gigachat_client import GigaChatClient, GigaChatClientConfig
from services.token_counter import count_message_tokens, count_tokens
from memory import (
    MemoryStore,
    SessionRecord,
    iso_now,
    load_memory,
    recent_sessions,
    save_memory,
    upsert_session,
    delete_session,
    find_session,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MessageRole = Literal["user", "assistant", "system", "summary"]

SUMMARY_PROMPT = (
    "Ты — ассистент, который кратко суммирует предыдущий диалог. "
    "Сделай сжатое, но полезное резюме для сохранения контекста. "
    "Пиши простым текстом без эмодзи и специальных символов, используй только буквы, цифры и базовую пунктуацию."
)
SUMMARY_CONTEXT_PREFIX = "Предыдущий диалог (резюме): "
MAX_TITLE_LENGTH = 100


@dataclass
class Message:
    """Message stored in local history."""

    role: MessageRole
    content: str
    tokens: int

    def to_api_dict(self) -> Dict[str, str]:
        """
        Convert to API-compatible dict.

        "summary" is treated as "system" so the summary is preserved as context.
        """
        mapped_role = "system" if self.role in {"system", "summary"} else self.role
        return {"role": mapped_role, "content": self.content}

    def to_dict(self) -> Dict[str, object]:
        return {"role": self.role, "content": self.content, "tokens": self.tokens}

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Message":
        role = data.get("role", "user")
        content = str(data.get("content", ""))
        tokens = int(data.get("tokens", 0) or count_tokens(content))
        return cls(role=role, content=content, tokens=tokens)


@dataclass
class SessionStats:
    """Token statistics for the session."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def input_cost(self, price_per_1k: float) -> float:
        return (self.total_input_tokens / 1000) * price_per_1k

    def output_cost(self, price_per_1k: float) -> float:
        return (self.total_output_tokens / 1000) * price_per_1k


class ConsoleChatApp:
    """Interactive console chat with history, summarization, and stats."""

    def __init__(self, settings: Settings, *, log_prompts: bool = False):
        self.settings = settings
        self.log_prompts = log_prompts
        self.memory_file = settings.memory_file
        self.session_list_limit = settings.session_list_limit
        client_config = GigaChatClientConfig(
            basic_auth=settings.basic_auth,
            chat_url=settings.chat_url,
            oauth_url=settings.oauth_url,
            model=settings.model,
            verify_ssl=settings.verify_ssl,
            request_timeout=settings.request_timeout,
        )
        self.client = GigaChatClient(client_config)
        self.history: List[Message] = []
        self.full_log: List[Message] = []
        self.stats = SessionStats()
        self.user_message_count = 0
        self.session_summary_text = ""
        self.summary_injected = False

        self.memory_store: MemoryStore = load_memory(self.memory_file, logger=logger)
        self.session: SessionRecord = self._select_or_create_session()

        self._reset_runtime_state()

    def _select_or_create_session(self, *, prefer_session_id: Optional[str] = None) -> SessionRecord:
        recent = recent_sessions(self.memory_store, self.session_list_limit)
        if prefer_session_id:
            preferred = find_session(self.memory_store, prefer_session_id)
            if preferred:
                dedup = [preferred] + [s for s in recent if s.session_id != preferred.session_id]
                recent = dedup[: self.session_list_limit]

        if recent:
            print("Найденные сессии (0 — новая):")
            self._print_recent_sessions(recent)
            choice = self._prompt_session_choice(len(recent))
            session = self._new_session() if choice == 0 else recent[choice - 1]
        else:
            print("Сохранённых сессий нет — начинаем новую.")
            session = self._new_session()

        self._apply_session_state(session)
        return session

    def _apply_session_state(self, session: SessionRecord) -> None:
        self.session = session
        self.session_summary_text = (session.summary or "").strip()
        self.user_message_count = session.user_turns
        self.stats.total_input_tokens = session.total_input_tokens
        self.stats.total_output_tokens = session.total_output_tokens
        self.summary_injected = False
        self.full_log = [Message.from_dict(m) for m in session.messages] if session.messages else []
        self.history = list(self.full_log)

    def _new_session(self) -> SessionRecord:
        now = iso_now()
        return SessionRecord(
            session_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            model_name=self.settings.model,
            api_base_url=self.settings.base_url,
            first_user_message="",
            title="",
            summary="",
            user_turns=0,
            total_input_tokens=0,
            total_output_tokens=0,
            is_active=True,
        )

    def _reset_runtime_state(self) -> None:
        self.history = list(self.full_log)
        self.summary_injected = False
        # Keep full_log intact; it reflects persisted history.
        if self.settings.system_prompt:
            self._append_system(self.settings.system_prompt)
        self._inject_saved_summary()

    def _inject_saved_summary(self) -> None:
        if not self.session_summary_text or self.summary_injected:
            return
        content = f"{SUMMARY_CONTEXT_PREFIX}{self.session_summary_text}"
        self.history.append(Message(role="system", content=content, tokens=count_tokens(content)))
        self.summary_injected = True

    def _print_recent_sessions(self, sessions: List[SessionRecord]) -> None:
        for idx, session in enumerate(sessions, start=1):
            title = session.title or session.first_user_message or "(нет заголовка)"
            title = self._truncate_title(title)
            ts = session.updated_at or session.created_at
            print(f"{idx}. {ts} — {title}")
        print("0. Новая сессия")

    def _prompt_session_choice(self, max_index: int) -> int:
        while True:
            try:
                raw = input(f"Выбор [0-{max_index}]: ").strip() or "0"
                choice = int(raw)
                if 0 <= choice <= max_index:
                    return choice
            except ValueError:
                pass
            print("Введите число из списка.")

    def _truncate_title(self, text: str, max_len: int = MAX_TITLE_LENGTH) -> str:
        text = text.strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"

    async def run(self) -> None:
        """Start the REPL loop."""
        self._print_help()
        try:
            while True:
                try:
                    user_input = await asyncio.to_thread(input, "You: ")
                except (EOFError, KeyboardInterrupt):
                    break
                text = user_input.strip()
                if not text:
                    continue
                if text.startswith("/"):
                    should_exit = await self._handle_command(text)
                    if should_exit:
                        break
                    continue
                await self._handle_user_message(text)
        finally:
            self._save_session_summary()
            await self.client.close()

    def _append_system(self, content: str) -> None:
        tokens = count_tokens(content)
        self.history.append(Message(role="system", content=content, tokens=tokens))

    async def _handle_command(self, command: str) -> bool:
        if command == "/exit":
            self._save_session_summary()
            return True
        if command == "/clear":
            self.history = []
            self.user_message_count = 0
            self.session_summary_text = ""
            self.session.summary = ""
            self.summary_injected = False
            self._reset_runtime_state()
            print("Context cleared.")
            self._save_session_summary()
            return False
        if command == "/stats":
            self._print_stats()
            return False
        if command == "/history":
            self._print_history()
            return False
        if command == "/compress":
            await self._manual_compress()
            return False
        if command == "/save":
            self._save_session_summary()
            print("Session saved.")
            return False
        if command == "/memory":
            self._print_memory_info()
            return False
        if command == "/forget":
            self._forget_current_session()
            self._save_session_summary()
            print("Текущая сессия удалена, создана новая.")
            return False
        if command == "/load":
            current_id = self.session.session_id
            self._save_session_summary()
            self._reload_memory_from_disk()
            self.session = self._select_or_create_session(prefer_session_id=current_id)
            self._reset_runtime_state()
            print("Память перечитана.")
            return False
        print("Unknown command. Available: /exit /clear /stats /history /save /memory /forget /load")
        return False

    def _print_help(self) -> None:
        print("Commands: /exit, /stats, /clear, /history, /compress, /save, /memory, /forget, /load")

    def _print_stats(self) -> None:
        total_cost = self.stats.input_cost(self.settings.price_input_per_1k) + self.stats.output_cost(
            self.settings.price_output_per_1k
        )
        print(
            f"Tokens — input: {self.stats.total_input_tokens}, output: {self.stats.total_output_tokens}. "
            f"Est. cost: {total_cost:.6f}"
        )

    def _print_history(self) -> None:
        if not self.history:
            print("History is empty.")
            return
        print("History:")
        for idx, msg in enumerate(self.history, start=1):
            label = f"{msg.role}"
            if msg.role == "summary":
                label = "summary (compressed)"
            print(f"{idx}. {label} [{msg.tokens} tkn]: {msg.content}")

    def _current_summary_text(self) -> str:
        parts: List[str] = []
        if self.session_summary_text:
            base = self.session_summary_text.strip()
            if base:
                parts.append(base)
        for msg in self.history:
            if msg.role != "summary":
                continue
            content = msg.content.strip()
            if content and content not in parts:
                parts.append(content)
        return "\n\n".join(parts).strip()

    def _update_first_user_message(self, text: str) -> None:
        if not self.session.first_user_message:
            self.session.first_user_message = text
        if not self.session.title:
            self.session.title = self._truncate_title(text)

    def _snapshot_session_for_save(self) -> SessionRecord:
        self.session_summary_text = self._current_summary_text()
        self.session.summary = self.session_summary_text
        self.session.user_turns = self.user_message_count
        self.session.total_input_tokens = self.stats.total_input_tokens
        self.session.total_output_tokens = self.stats.total_output_tokens
        self.session.model_name = self.settings.model
        self.session.api_base_url = self.settings.base_url
        self.session.updated_at = iso_now()
        self.session.messages = [m.to_dict() for m in self.full_log]
        return self.session

    def _save_session_summary(self) -> None:
        record = self._snapshot_session_for_save()
        upsert_session(self.memory_store, record)
        self.memory_store.active_session_id = record.session_id
        try:
            save_memory(self.memory_store, self.memory_file, logger=logger)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to save memory to %s", self.memory_file)
            print(f"Не удалось сохранить память: {exc}")

    def _print_memory_info(self) -> None:
        summary_len = len(self._current_summary_text())
        print(
            f"Memory file: {self.memory_file}\n"
            f"Session: {self.session.session_id}\n"
            f"Updated: {self.session.updated_at}\n"
            f"Summary chars: {summary_len}\n"
            f"User turns: {self.user_message_count}"
        )

    def _log_payload(self, api_messages: List[Dict[str, str]], *, context: str, extra: Optional[Dict[str, object]] = None) -> None:
        if not self.log_prompts:
            return
        payload = {"messages": api_messages}
        if extra:
            payload.update(extra)
        logger.info("GigaChat payload (%s): %s", context, payload)

    def _reload_memory_from_disk(self) -> None:
        self.memory_store = load_memory(self.memory_file, logger=logger)

    def _forget_current_session(self) -> None:
        delete_session(self.memory_store, self.session.session_id)
        self.session = self._new_session()
        self._apply_session_state(self.session)
        self._reset_runtime_state()
        self.full_log = []

    async def _handle_user_message(self, text: str) -> None:
        user_msg = Message(role="user", content=text, tokens=count_tokens(text))
        self.history.append(user_msg)
        self.full_log.append(user_msg)
        self.user_message_count += 1
        self._update_first_user_message(text)

        try:
            reply, input_tokens, output_tokens = await self._send_chat()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send message")
            print(f"Error: {exc}")
            return

        assistant_msg = Message(role="assistant", content=reply, tokens=output_tokens)
        self.history.append(assistant_msg)
        self.full_log.append(assistant_msg)
        self.stats.total_input_tokens += input_tokens
        self.stats.total_output_tokens += output_tokens

        print(f"GigaChat: {reply}")
        print(
            f"Tokens: input={input_tokens}, output={output_tokens}. "
            f"Session totals — input: {self.stats.total_input_tokens}, output: {self.stats.total_output_tokens}"
        )

        await self._maybe_compress_history()
        self._save_session_summary()

    def _build_api_messages(self, extra_messages: Optional[Iterable[Message]] = None) -> List[Dict[str, str]]:
        messages: List[Message] = list(self.history)
        if extra_messages:
            messages.extend(extra_messages)
        return [m.to_api_dict() for m in messages]

    async def _send_chat(self) -> Tuple[str, int, int]:
        api_messages = self._build_api_messages()
        self._log_payload(api_messages, context="chat")
        estimated_input_tokens = count_message_tokens(api_messages)
        reply, raw_response = await self.client.chat(api_messages)
        usage = raw_response.get("usage", {}) if isinstance(raw_response, dict) else {}

        input_tokens = int(usage.get("prompt_tokens", 0) or estimated_input_tokens)
        output_tokens = int(usage.get("completion_tokens", 0) or count_tokens(reply))
        return reply, input_tokens, output_tokens

    async def _maybe_compress_history(self) -> None:
        if self.user_message_count == 0:
            return
        if self.user_message_count % self.settings.summary_every != 0:
            return

        pair_indices = self._oldest_pair_indices(self.settings.summary_pair_batch)
        if not pair_indices:
            return

        logger.info("Compressing %d message pairs into a summary", self.settings.summary_pair_batch)
        await self._compress_pairs(pair_indices)

    async def _manual_compress(self) -> None:
        pair_indices = self._all_user_assistant_indices()
        if not pair_indices:
            print("Нет сообщений для сжатия.")
            return
        await self._compress_pairs(pair_indices)
        self._save_session_summary()
        print("История сжата вручную.")

    def _all_user_assistant_indices(self) -> List[int]:
        return [idx for idx, msg in enumerate(self.history) if msg.role in {"user", "assistant"}]

    def _oldest_pair_indices(self, pair_count: int) -> List[int]:
        indices = [idx for idx, msg in enumerate(self.history) if msg.role in {"user", "assistant"}]
        if len(indices) < pair_count * 2:
            return []
        return indices[: pair_count * 2]

    async def _compress_pairs(self, indices: List[int]) -> None:
        messages_to_summarize = [self.history[i] for i in indices]
        summary_prompt_msg = Message(role="system", content=SUMMARY_PROMPT, tokens=count_tokens(SUMMARY_PROMPT))
        api_messages = [summary_prompt_msg.to_api_dict()] + [m.to_api_dict() for m in messages_to_summarize]
        self._log_payload(api_messages, context="summarize", extra={"temperature": 0.2})

        estimated_input = count_message_tokens(api_messages)
        summary_text, raw_response = await self.client.chat(api_messages, temperature=0.2)
        usage = raw_response.get("usage", {}) if isinstance(raw_response, dict) else {}

        input_tokens = int(usage.get("prompt_tokens", 0) or estimated_input)
        output_tokens = int(usage.get("completion_tokens", 0) or count_tokens(summary_text))

        self.stats.total_input_tokens += input_tokens
        self.stats.total_output_tokens += output_tokens

        # Build new history without the summarized messages, inserting the summary at the earliest index.
        summary_message = Message(role="summary", content=summary_text, tokens=output_tokens)
        system_messages = [m for m in self.history if m.role == "system"]
        keep_history: List[Message] = system_messages + [summary_message]

        # Replace runtime history and persisted full_log with the compressed view
        self.history = keep_history
        self.full_log = list(keep_history)
        logger.info("History compressed. Summary tokens=%d", output_tokens)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GigaChat REPL with session memory.")
    parser.add_argument(
        "--memory-file",
        type=Path,
        help="Path to JSON file for session summaries (defaults to CHAT_MEMORY_FILE or ./.chat_memory.json).",
    )
    parser.add_argument(
        "--session-list-limit",
        type=int,
        help="How many recent sessions to show on startup (default 5).",
    )
    parser.add_argument(
        "-log",
        "--log",
        dest="log_prompts",
        action="store_true",
        help="Log request payloads (prompts) sent to GigaChat.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = load_settings(memory_file=args.memory_file, session_list_limit=args.session_list_limit)
    app = ConsoleChatApp(settings, log_prompts=args.log_prompts)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
