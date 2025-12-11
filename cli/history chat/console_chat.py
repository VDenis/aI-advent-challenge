"""Console chat client for GigaChat.

Run:
    python "cli/history chat/console_chat.py"

Required in `.env`:
- GIGA_CLIENT_BASIC=base64(client_id:client_secret)
Optional: GIGA_API_BASE_URL, GIGA_VERIFY_SSL, GIGA_MODEL_NAME, etc.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Literal, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Settings, load_settings
from services.gigachat_client import GigaChatClient, GigaChatClientConfig
from services.token_counter import count_message_tokens, count_tokens


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MessageRole = Literal["user", "assistant", "system", "summary"]

SUMMARY_PROMPT = (
    "Ты — ассистент, который кратко суммирует предыдущий диалог. "
    "Сделай сжатое, но полезное резюме для сохранения контекста."
)


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

    def __init__(self, settings: Settings):
        self.settings = settings
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
        self.stats = SessionStats()
        self.user_message_count = 0

        if self.settings.system_prompt:
            self._append_system(self.settings.system_prompt)

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
            await self.client.close()

    def _append_system(self, content: str) -> None:
        tokens = count_tokens(content)
        self.history.append(Message(role="system", content=content, tokens=tokens))

    async def _handle_command(self, command: str) -> bool:
        if command == "/exit":
            return True
        if command == "/clear":
            self.history = []
            self.user_message_count = 0
            if self.settings.system_prompt:
                self._append_system(self.settings.system_prompt)
            print("Context cleared.")
            return False
        if command == "/stats":
            self._print_stats()
            return False
        if command == "/history":
            self._print_history()
            return False
        print("Unknown command. Available: /exit /clear /stats /history")
        return False

    def _print_help(self) -> None:
        print("Commands: /exit, /stats, /clear, /history")

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

    async def _handle_user_message(self, text: str) -> None:
        user_msg = Message(role="user", content=text, tokens=count_tokens(text))
        self.history.append(user_msg)
        self.user_message_count += 1

        try:
            reply, input_tokens, output_tokens = await self._send_chat()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send message")
            print(f"Error: {exc}")
            return

        assistant_msg = Message(role="assistant", content=reply, tokens=output_tokens)
        self.history.append(assistant_msg)
        self.stats.total_input_tokens += input_tokens
        self.stats.total_output_tokens += output_tokens

        print(f"GigaChat: {reply}")
        print(
            f"Tokens: input={input_tokens}, output={output_tokens}. "
            f"Session totals — input: {self.stats.total_input_tokens}, output: {self.stats.total_output_tokens}"
        )

        await self._maybe_compress_history()

    def _build_api_messages(self, extra_messages: Optional[Iterable[Message]] = None) -> List[Dict[str, str]]:
        messages: List[Message] = list(self.history)
        if extra_messages:
            messages.extend(extra_messages)
        return [m.to_api_dict() for m in messages]

    async def _send_chat(self) -> Tuple[str, int, int]:
        api_messages = self._build_api_messages()
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

    def _oldest_pair_indices(self, pair_count: int) -> List[int]:
        indices = [idx for idx, msg in enumerate(self.history) if msg.role in {"user", "assistant"}]
        if len(indices) < pair_count * 2:
            return []
        return indices[: pair_count * 2]

    async def _compress_pairs(self, indices: List[int]) -> None:
        messages_to_summarize = [self.history[i] for i in indices]
        summary_prompt_msg = Message(role="system", content=SUMMARY_PROMPT, tokens=count_tokens(SUMMARY_PROMPT))
        api_messages = [summary_prompt_msg.to_api_dict()] + [m.to_api_dict() for m in messages_to_summarize]

        estimated_input = count_message_tokens(api_messages)
        summary_text, raw_response = await self.client.chat(api_messages, temperature=0.2)
        usage = raw_response.get("usage", {}) if isinstance(raw_response, dict) else {}

        input_tokens = int(usage.get("prompt_tokens", 0) or estimated_input)
        output_tokens = int(usage.get("completion_tokens", 0) or count_tokens(summary_text))

        self.stats.total_input_tokens += input_tokens
        self.stats.total_output_tokens += output_tokens

        # Build new history without the summarized messages, inserting the summary at the earliest index.
        keep_history: List[Message] = []
        earliest_index = min(indices)
        summary_message = Message(role="summary", content=summary_text, tokens=output_tokens)
        for idx, msg in enumerate(self.history):
            if idx == earliest_index:
                keep_history.append(summary_message)
            if idx in indices:
                continue
            keep_history.append(msg)

        self.history = keep_history
        logger.info("History compressed. Summary tokens=%d", output_tokens)


async def main() -> None:
    settings = load_settings()
    app = ConsoleChatApp(settings)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
