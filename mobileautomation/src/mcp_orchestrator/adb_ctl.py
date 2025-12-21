from __future__ import annotations

import base64
import logging
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from .types import CommandResult

LOGGER = logging.getLogger(__name__)


def _adb_base_cmd(serial: Optional[str]) -> List[str]:
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    return cmd


def _run_adb(args: List[str], serial: Optional[str] = None) -> CommandResult:
    cmd = _adb_base_cmd(serial) + args
    LOGGER.debug("Running adb command: %s", " ".join(cmd))
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


def adb_connect(host: str = "127.0.0.1", port: int = 5555) -> CommandResult:
    """Connect to an ADB endpoint."""
    target = f"{host}:{port}"
    return _run_adb(["connect", target])


def list_devices() -> List[str]:
    """List connected ADB devices (serials only)."""
    result = _run_adb(["devices"])
    if result.returncode != 0:
        LOGGER.warning("adb devices failed: %s", result.as_summary())
        return []
    devices: List[str] = []
    for line in result.stdout.splitlines():
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def wait_boot_completed(serial: Optional[str] = None, timeout_sec: int = 300) -> bool:
    """Wait until the device reports boot completed."""
    deadline = time.time() + timeout_sec
    props = ["sys.boot_completed", "dev.bootcomplete"]

    while time.time() < deadline:
        for prop in props:
            result = _run_adb(["shell", "getprop", prop], serial=serial)
            if result.returncode == 0 and result.stdout.strip() == "1":
                return True
        time.sleep(5)
    return False


def install_apk(apk_path: str, serial: Optional[str] = None) -> CommandResult:
    """Install an APK on the device."""
    path = Path(apk_path)
    if not path.exists():
        return CommandResult(
            command=[],
            stdout="",
            stderr=f"APK not found at {apk_path}",
            returncode=1,
        )
    return _run_adb(["install", "-r", str(path)], serial=serial)


def launch_app(
    package: str,
    activity: Optional[str] = None,
    serial: Optional[str] = None,
) -> CommandResult:
    """Launch an app either by explicit activity or via monkey."""
    if activity:
        component = f"{package}/{activity}"
        args = ["shell", "am", "start", "-n", component]
    else:
        args = ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]
    return _run_adb(args, serial=serial)


def capture_screenshot(serial: Optional[str] = None, output_path: Optional[str] = None) -> str:
    """Capture a screenshot via adb and save it locally."""
    target = Path(output_path) if output_path else Path.cwd() / f"adb_screenshot_{int(time.time())}.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    result = _run_adb(
        ["exec-out", "sh", "-c", "screencap -p | base64"],
        serial=serial,
    )
    if result.returncode != 0:
        return result.as_summary()

    try:
        data = base64.b64decode(result.stdout)
        target.write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to decode/write screenshot: %s", exc)
        return f"failed to write screenshot: {exc}"

    return f"saved screenshot to {target} (bytes={len(data)})"

