from __future__ import annotations

from typing import Dict, List, TypedDict


class ChunkSpan(TypedDict):
    """Fragment of a source document."""

    start_char: int
    end_char: int
    text: str


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[ChunkSpan]:
    """
    Split text into overlapping chunks using a sliding window (character-based).

    Empty or very short chunks (<50 chars) are skipped.
    """
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap to advance the window")

    spans: List[ChunkSpan] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        piece = text[start:end]
        if len(piece) >= 50:
            spans.append({"start_char": start, "end_char": end, "text": piece})
        start += chunk_size - overlap

    return spans

