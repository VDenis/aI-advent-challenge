"""Simple token counting utilities for the console client."""

from __future__ import annotations

import math
from typing import Dict, Iterable


# Heuristic: roughly 4 characters per token.
CHARS_PER_TOKEN = 4


def count_tokens(text: str) -> int:
    """Approximate token count for a text snippet."""
    if not text:
        return 0
    return max(1, int(math.ceil(len(text) / CHARS_PER_TOKEN)))


def count_message_tokens(messages: Iterable[Dict[str, str]]) -> int:
    """Approximate token count for a list of messages."""
    total = 0
    for message in messages:
        tokens = message.get("tokens")
        if isinstance(tokens, int):
            total += tokens
            continue
        total += count_tokens(message.get("content", ""))
    return total
