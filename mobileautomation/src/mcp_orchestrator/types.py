from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class CommandResult:
    """Represents the outcome of a subprocess call."""

    command: List[str]
    stdout: str
    stderr: str
    returncode: int

    def as_summary(self) -> str:
        """Human-friendly summary that includes exit code and stderr if present."""
        parts = [
            f"cmd={' '.join(self.command)}",
            f"exit={self.returncode}",
        ]
        if self.stdout.strip():
            parts.append(f"stdout={self.stdout.strip()}")
        if self.stderr.strip():
            parts.append(f"stderr={self.stderr.strip()}")
        return " | ".join(parts)


