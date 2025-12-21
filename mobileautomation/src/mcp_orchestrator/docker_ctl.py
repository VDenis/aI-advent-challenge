from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List
import os

from .types import CommandResult

LOGGER = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = Path(os.getenv("COMPOSE_FILE_PATH", PROJECT_ROOT / "docker-compose.yml")).resolve()
COMPOSE_CMD = os.getenv("DOCKER_COMPOSE_CMD", "docker compose")


def _compose_base_cmd() -> List[str]:
    base = COMPOSE_CMD.strip().split()
    return [*base, "-f", str(COMPOSE_FILE)]


def _run_compose(args: List[str]) -> CommandResult:
    cmd = _compose_base_cmd() + args
    LOGGER.debug("Running compose command: %s", " ".join(cmd))
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=cmd,
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def env_up() -> CommandResult:
    """Start the Android emulator environment."""
    return _run_compose(["up", "-d"])


def env_down() -> CommandResult:
    """Stop and remove the Android emulator environment."""
    return _run_compose(["down"])


def env_status() -> CommandResult:
    """Show current docker-compose service status."""
    return _run_compose(["ps"])

