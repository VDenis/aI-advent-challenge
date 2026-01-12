from __future__ import annotations

from pathlib import Path

import pytest

from mcp_filesystem_sandbox.security import SandboxViolation, assert_allowed, normalize_path


def test_traversal_outside_denied(tmp_path: Path) -> None:
    allowed = [normalize_path(tmp_path)]
    target = normalize_path(tmp_path / ".." / "elsewhere" / "file.txt")
    with pytest.raises(SandboxViolation):
        assert_allowed(target, allowed)


def test_symlink_escape_denied(tmp_path: Path) -> None:
    allowed_root = normalize_path(tmp_path / "root")
    allowed_root.mkdir(parents=True, exist_ok=True)

    outside = normalize_path(tmp_path / "outside")
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "data.txt").write_text("secret", encoding="utf-8")

    sneaky = allowed_root / "link_out"
    sneaky.symlink_to(outside)

    escaped = normalize_path(sneaky / "data.txt")
    with pytest.raises(SandboxViolation):
        assert_allowed(escaped, [allowed_root])


def test_nested_directory_allowed(tmp_path: Path) -> None:
    allowed_root = normalize_path(tmp_path / "allowed")
    allowed_root.mkdir(parents=True, exist_ok=True)
    nested = normalize_path(allowed_root / "nested" / "child")
    assert_allowed(nested, [allowed_root])


def test_sibling_directory_denied(tmp_path: Path) -> None:
    base = normalize_path(tmp_path / "base")
    allowed_root = base / "allowed"
    sibling = base / "sibling"
    allowed_root.mkdir(parents=True, exist_ok=True)
    sibling.mkdir(parents=True, exist_ok=True)

    target = normalize_path(sibling / "note.txt")
    with pytest.raises(SandboxViolation):
        assert_allowed(target, [allowed_root])

