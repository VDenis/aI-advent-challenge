from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from .security import SandboxViolation, assert_allowed, normalize_path

server = FastMCP("filesystem-sandbox")
sandbox_root: Path | None = None


def configure_sandbox_root(raw_root: str) -> Path:
    """
    Initialize the single sandbox root.

    The directory is created if it does not exist. All subsequent operations
    are confined to this root.
    """
    global sandbox_root
    root = normalize_path(raw_root)
    if root.exists() and not root.is_dir():
        raise SandboxViolation(f"Корневой путь должен быть директорией: {root}")
    root.mkdir(parents=True, exist_ok=True)
    sandbox_root = root
    return root


def require_sandbox_root() -> Path:
    if sandbox_root is None:
        raise SandboxViolation("Корневой каталог песочницы не настроен. Перезапустите с путём.")
    return sandbox_root


def _relative_to_root(path: Path) -> str:
    root = require_sandbox_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def resolve_path(path_str: Optional[str]) -> Path:
    """
    Resolve an incoming path within the configured sandbox root.

    - Relative paths are joined to the sandbox root.
    - Absolute paths are allowed only if they remain inside the sandbox root.
    - Empty/None/".": refer to the sandbox root itself.
    """
    root = require_sandbox_root()

    if not path_str or path_str.strip() in {".", "/"}:
        candidate = root
    else:
        cleaned = path_str.strip()
        user_path = Path(cleaned)
        if user_path.is_absolute():
            candidate = normalize_path(cleaned)
        else:
            candidate = normalize_path(str(root / user_path))

    assert_allowed(candidate, [root])
    return candidate


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
    """Return the configured sandbox root (single-item list)."""
    root = require_sandbox_root()
    return [str(root)]


@server.tool()
async def read_text_file(path: str, head: Optional[int] = None, tail: Optional[int] = None) -> dict:
    """
    Read a UTF-8 text file with optional head/tail limits (by lines).
    If both head and tail are provided, head takes precedence.
    """
    target = resolve_path(path)
    if not target.exists():
        raise SandboxViolation(f"Файл не найден: {target}")
    if target.is_dir():
        raise SandboxViolation(f"Нельзя читать директорию как файл: {target}")

    content = _read_file_lines(target, head, tail)
    return {"path": str(target), "relative_path": _relative_to_root(target), "content": content}


@server.tool()
async def read_multiple_files(paths: List[str]) -> list[dict]:
    """
    Read multiple files; partial failures are returned per-path without aborting.
    """
    results: list[dict] = []
    for path in paths:
        try:
            entry = await read_text_file(path)
            results.append(
                {"path": entry["path"], "relative_path": entry["relative_path"], "content": entry["content"]}
            )
        except Exception as exc:
            results.append({"path": str(path), "error": str(exc)})
    return results


@server.tool()
async def write_file(path: str, content: str) -> dict:
    """Create or overwrite a file with UTF-8 content."""
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_dir():
        raise SandboxViolation(f"Нельзя перезаписать директорию: {target}")
    with target.open("w", encoding="utf-8") as f:
        f.write(content)
    return {"path": str(target), "relative_path": _relative_to_root(target), "status": "ok"}


@server.tool()
async def create_directory(path: str) -> dict:
    """mkdir -p equivalent; succeeds if already exists."""
    target = resolve_path(path)
    if target.exists() and target.is_file():
        raise SandboxViolation(f"Файл с таким именем уже существует: {target}")
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target), "relative_path": _relative_to_root(target), "status": "ok"}


@server.tool()
async def list_directory(path: str = ".") -> dict:
    """List files and folders within the sandbox root."""
    target = resolve_path(path)
    if not target.exists():
        raise SandboxViolation(f"Путь не найден: {target}")
    if not target.is_dir():
        raise SandboxViolation(f"Это не директория: {target}")

    entries: list[dict] = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        entries.append(
            {
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "path": str(child),
                "relative_path": _relative_to_root(child),
            }
        )
    return {"path": str(target), "relative_path": _relative_to_root(target), "entries": entries}


@server.tool()
async def get_file_info(path: str) -> dict:
    """Return basic file metadata."""
    target = resolve_path(path)
    if not target.exists():
        raise SandboxViolation(f"Путь не найден: {target}")

    stats = target.stat()
    info = {
        "path": str(target),
        "relative_path": _relative_to_root(target),
        "is_dir": target.is_dir(),
        "size": stats.st_size,
        "modified": datetime.fromtimestamp(stats.st_mtime).isoformat(),
        "permissions": oct(stats.st_mode & 0o777),
    }
    return info


# TODO: integrate MCP Roots protocol once it is exposed in the Python SDK.


def main() -> None:
    parser = argparse.ArgumentParser(description="Filesystem sandbox MCP server (stdio).")
    parser.add_argument("root", help="Directory to sandbox all operations.")
    args = parser.parse_args()

    configure_sandbox_root(args.root)
    server.run("stdio")


if __name__ == "__main__":
    main()

