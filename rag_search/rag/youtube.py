from __future__ import annotations

import logging
import os
import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url: str) -> str | None:
    """
    Extracts the video ID from a YouTube URL.
    Supports regular URLs, shortened URLs (youtu.be), and simple IDs.
    """
    # Simply return if it looks like an ID (11 chars)
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url

    parsed = urlparse(url)
    
    # https://youtu.be/VIDEO_ID
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip("/")
    
    # https://www.youtube.com/watch?v=VIDEO_ID
    if parsed.netloc in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            return qs.get("v", [None])[0]
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/")[2]
        if parsed.path.startswith("/v/"):
            return parsed.path.split("/")[2]

    return None


def get_transcript(video_id: str, languages: list[str] | None = None) -> str:
    """
    Fetches the transcript for a video ID.
    Tries languages in order.
    Returns the concatenated text.
    """
    if languages is None:
        # Prefer Russian, then English
        languages = ["ru", "en"]

    try:
        logging.info("Fetching transcript for video %s (langs=%s)", video_id, languages)
        
        # Instantiate API and fetch
        api = YouTubeTranscriptApi()
        transcript_obj = api.fetch(video_id, languages=languages)
        
        # Access snippets
        # Note: transcript_obj.snippets is a list of FetchedTranscriptSnippet objects
        full_text = " ".join(item.text for item in transcript_obj.snippets)
        
        # Simple cleanup: multiple spaces/newlines
        full_text = re.sub(r"\s+", " ", full_text).strip()
        
        return full_text
    
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch transcript: {exc}")



def save_transcript(video_id: str, text: str, output_dir: str) -> str:
    """
    Saves the transcript to a file in output_dir.
    Returns the file path.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{video_id}.txt"
    path = os.path.join(output_dir, filename)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    
    return path
