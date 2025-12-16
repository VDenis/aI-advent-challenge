from __future__ import annotations

from pathlib import Path
from typing import Iterable


class SandboxViolation(PermissionError):
    """Raised when a requested path is outside the configured sandbox."""


def normalize_path(user_path: str) -> Path:
    """
    Convert an incoming user path to an absolute, canonical Path.

    Expands ~, resolves symlinks when possible, and never requires the
    target to already exist (strict=False) so that creation operations
    can still be validated against the sandbox.
    """
    if not user_path:
        raise SandboxViolation("Доступ запрещен: путь не может быть пустым.")

    path = Path(user_path).expanduser()
    try:
        return path.resolve(strict=False)
    except Exception as exc:  # pragma: no cover - unlikely on supported OSes
        raise SandboxViolation(f"Не удалось разобрать путь '{user_path}': {exc}") from exc


def assert_allowed(path: Path, allowed_roots: Iterable[Path]) -> None:
    """Ensure the path is within at least one allowed root (inclusive)."""
    roots = list(allowed_roots)
    if not roots:
        raise SandboxViolation("Доступ запрещен: разрешенные каталоги не настроены.")

    for root in roots:
        if path == root or path.is_relative_to(root):
            return

    allowed_str = ", ".join(str(r) for r in roots)
    raise SandboxViolation(f"Доступ запрещен: путь '{path}' вне разрешенных каталогов [{allowed_str}].")


def safe_join(root: Path, user_path: str) -> Path:
    """
    Safely join a root with a user-supplied path and verify sandboxing.

    This is helpful when the API accepts a relative path intended to be
    anchored to a specific allowed directory.
    """
    root_resolved = root.resolve(strict=False)
    candidate = (root_resolved / user_path).resolve(strict=False)
    assert_allowed(candidate, [root_resolved])
    return candidate

