from __future__ import annotations

import argparse
import json
import os
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from mcp.server.fastmcp import FastMCP

from .security import SandboxViolation, assert_allowed, normalize_path

server = FastMCP("filesystem-sandbox")
allowed_roots: list[Path] = []


def set_allowed_roots(raw_roots: Iterable[str]) -> None:
    """Initialize allowed roots from CLI args."""
    global allowed_roots
    normalized = [normalize_path(path) for path in raw_roots]
    if not normalized:
        raise SandboxViolation("At least one --allow path is required.")
    allowed_roots = normalized


def ensure_allowed(path_str: str) -> Path:
    """Normalize and validate a user-supplied path."""
    path = normalize_path(path_str)
    assert_allowed(path, allowed_roots)
    return path


def require_allowed_roots() -> None:
    if not allowed_roots:
        raise SandboxViolation("Access denied: server has no allowed directories configured.")


def _read_file_lines(path: Path, head: Optional[int], tail: Optional[int]) -> str:
    if head is not None and head < 0:
        raise SandboxViolation("head must be non-negative.")
    if tail is not None and tail < 0:
        raise SandboxViolation("tail must be non-negative.")

    if head is not None and tail is not None:
        # Prefer head if both are provided to avoid ambiguity.
        tail = None

    if head is not None:
        lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx >= head:
                    break
                lines.append(line)
        return "".join(lines)

    if tail is not None:
        buffer: deque[str] = deque(maxlen=tail)
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                buffer.append(line)
        return "".join(buffer)

    with path.open("r", encoding="utf-8", errors="replace") as f:
        return f.read()


@server.tool()
async def list_allowed_directories() -> list[str]:
    """Return the current allowlist."""
    require_allowed_roots()
    return [str(p) for p in allowed_roots]


@server.tool()
async def read_text_file(path: str, head: Optional[int] = None, tail: Optional[int] = None) -> dict:
    """
    Read a UTF-8 text file with optional head/tail limits (by lines).
    If both head and tail are provided, head takes precedence.
    """
    require_allowed_roots()
    target = ensure_allowed(path)
    if not target.exists():
        raise SandboxViolation(f"File not found: {target}")
    if target.is_dir():
        raise SandboxViolation(f"Cannot read directory as file: {target}")

    content = _read_file_lines(target, head, tail)
    return {"path": str(target), "content": content}


@server.tool()
async def read_multiple_files(paths: List[str]) -> list[dict]:
    """
    Read multiple files; partial failures are returned per-path without aborting.
    """
    results: list[dict] = []
    for path in paths:
        try:
            entry = await read_text_file(path)
            results.append({"path": entry["path"], "content": entry["content"]})
        except Exception as exc:
            results.append({"path": str(path), "error": str(exc)})
    return results


@server.tool()
async def write_file(path: str, content: str) -> dict:
    """Create or overwrite a file with UTF-8 content."""
    require_allowed_roots()
    target = ensure_allowed(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        f.write(content)
    return {"path": str(target), "status": "ok"}


@server.tool()
async def create_directory(path: str) -> dict:
    """mkdir -p equivalent; succeeds if already exists."""
    require_allowed_roots()
    target = ensure_allowed(path)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target), "status": "ok"}


@server.tool()
async def list_directory(path: str) -> dict:
    """List directory entries with simple [DIR]/[FILE] prefixes."""
    require_allowed_roots()
    target = ensure_allowed(path)
    if not target.exists():
        raise SandboxViolation(f"Path not found: {target}")
    if not target.is_dir():
        raise SandboxViolation(f"Not a directory: {target}")

    entries: list[str] = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        prefix = "[DIR]" if child.is_dir() else "[FILE]"
        entries.append(f"{prefix} {child.name}")
    return {"path": str(target), "entries": entries}


@server.tool()
async def move_file(source: str, destination: str) -> dict:
    """Move/rename a file or directory; destination must not exist."""
    require_allowed_roots()
    src_path = ensure_allowed(source)
    dst_path = ensure_allowed(destination)

    if not src_path.exists():
        raise SandboxViolation(f"Source not found: {src_path}")
    if dst_path.exists():
        raise SandboxViolation(f"Destination already exists: {dst_path}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dst_path)
    return {"status": "ok", "source": str(src_path), "destination": str(dst_path)}


def _matches_exclude(path: Path, patterns: list[str]) -> bool:
    return any(path.match(pat) for pat in patterns)


@server.tool()
async def search_files(path: str, pattern: str, excludePatterns: Optional[List[str]] = None) -> dict:
    """
    Search for files whose relative path matches a case-insensitive regex.
    excludePatterns uses glob semantics applied to full paths.
    """
    require_allowed_roots()
    base = ensure_allowed(path)
    if not base.is_dir():
        raise SandboxViolation(f"Search root must be a directory: {base}")

    regex = re.compile(pattern, re.IGNORECASE)
    exclude = excludePatterns or []
    matches: list[str] = []

    for root, dirs, files in os.walk(base, followlinks=False):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not _matches_exclude(root_path / d, exclude)]
        for name in files:
            candidate = root_path / name
            if _matches_exclude(candidate, exclude):
                continue
            resolved = candidate.resolve(strict=False)
            try:
                assert_allowed(resolved, allowed_roots)
                rel = resolved.relative_to(base)
            except SandboxViolation:
                # Skip anything that would escape via symlink.
                continue
            except ValueError:
                # Symlink into another allowed root: ignore for this search base.
                continue
            if regex.search(str(rel)):
                matches.append(str(resolved))

    return {"path": str(base), "matches": matches}


@server.tool()
async def get_file_info(path: str) -> dict:
    """Return basic file metadata."""
    require_allowed_roots()
    target = ensure_allowed(path)
    if not target.exists():
        raise SandboxViolation(f"Path not found: {target}")

    stats = target.stat()
    info = {
        "path": str(target),
        "is_dir": target.is_dir(),
        "size": stats.st_size,
        "modified": datetime.fromtimestamp(stats.st_mtime).isoformat(),
        "permissions": oct(stats.st_mode & 0o777),
    }
    return info


# TODO: integrate MCP Roots protocol once it is exposed in the Python SDK.


def main() -> None:
    parser = argparse.ArgumentParser(description="Filesystem sandbox MCP server (stdio).")
    parser.add_argument(
        "--allow",
        action="append",
        dest="allowed",
        required=True,
        help="Absolute directory to allow (repeatable).",
    )
    args = parser.parse_args()

    set_allowed_roots(args.allowed)
    server.run("stdio")


if __name__ == "__main__":
    main()

