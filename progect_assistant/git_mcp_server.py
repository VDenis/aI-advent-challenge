from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(os.environ.get("GIT_MCP_PROJECT_ROOT", os.getcwd())).resolve()
MAX_DIFF_LINES = 200

mcp = FastMCP("git-mcp")


def _run_git(args: List[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _ensure_inside_root(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        raise ValueError("Path escapes project root")
    return resolved


@mcp.tool()
async def git_status() -> dict:
    """Return current git branch and changed files."""
    output = _run_git(["status", "--porcelain", "-b"])
    lines = output.strip().splitlines()
    branch = "unknown"
    changed: List[str] = []
    for line in lines:
        if line.startswith("##"):
            branch = line.replace("##", "").strip()
        else:
            parts = line.split()
            if parts:
                changed.append(parts[-1])
    return {"branch": branch, "changed_files": changed}


@mcp.tool()
async def git_diff(max_lines: int = MAX_DIFF_LINES) -> dict:
    """Return git diff with a line limit."""
    diff = _run_git(["diff", "--unified=3"])
    lines = diff.splitlines()
    limit = int(max_lines) if max_lines else MAX_DIFF_LINES
    if len(lines) > limit:
        lines = lines[:limit]
        lines.append("...diff truncated...")
    return {"output": "\n".join(lines)}


@mcp.tool()
async def read_file_snippet(path: str, start_line: int, end_line: int) -> dict:
    """Safely read a snippet from a file inside the project root."""
    target = _ensure_inside_root(PROJECT_ROOT / path)
    if not target.exists() or target.is_dir():
        raise ValueError(f"File not found: {path}")
    lines = target.read_text(encoding="utf-8", errors="ignore").splitlines(True)
    start = max(int(start_line) - 1, 0)
    end = min(int(end_line), len(lines))
    return {"output": "".join(lines[start:end])}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
