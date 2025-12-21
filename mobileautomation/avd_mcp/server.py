from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="avd-control")


def _default_emulator_path() -> Path:
    env_path = os.getenv("ANDROID_EMULATOR")
    if env_path:
        return Path(env_path)
    return Path.home() / "Library" / "Android" / "sdk" / "emulator" / "emulator"


def _default_avd_name() -> str:
    return os.getenv("AVD_NAME", "Wear_OS_Small_Round")


def _default_extra_args() -> str:
    return os.getenv(
        "AVD_EXTRA_ARGS",
        "-no-window -gpu swiftshader_indirect -noaudio -no-snapshot",
    )


@mcp.tool()
def start_avd(
    avd_name: Optional[str] = None,
    port: int = 5554,
    extra_args: Optional[str] = None,
) -> str:
    """Start a local Android AVD headless. Returns PID and log path."""
    emulator_bin = _default_emulator_path()
    if not emulator_bin.exists():
        return f"emulator binary not found at {emulator_bin}"

    name = avd_name or _default_avd_name()
    args = extra_args or _default_extra_args()
    log_path = Path(f"/tmp/avd_{name.replace(' ', '_')}_{port}.log")

    cmd = [
        str(emulator_bin),
        "-avd",
        name,
        "-port",
        str(port),
        *args.split(),
    ]

    log_file = log_path.open("w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:  # noqa: BLE001
        log_file.close()
        return f"failed to start emulator: {exc}"

    return f"started AVD '{name}' on port {port}, pid={proc.pid}, log={log_path}"


@mcp.tool()
def stop_avd(port: int = 5554) -> str:
    """Stop an AVD by port using adb emu kill."""
    serial = f"emulator-{port}"
    adb_bin = os.getenv("ADB_PATH", "adb")
    result = subprocess.run(
        [adb_bin, "-s", serial, "emu", "kill"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return f"failed to stop {serial}: {result.stderr.strip() or result.stdout.strip()}"
    return f"stopped {serial}"


@mcp.tool()
def adb(
    cmd: List[str],
    serial: Optional[str] = None,
) -> str:
    """Run an adb command. Example: cmd=["shell", "getprop"]."""
    adb_bin = os.getenv("ADB_PATH", "adb")
    args = [adb_bin]
    if serial:
        args.extend(["-s", serial])
    args.extend(cmd)

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return f"adb failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
    return result.stdout.strip() or "ok"


if __name__ == "__main__":
    mcp.run()

