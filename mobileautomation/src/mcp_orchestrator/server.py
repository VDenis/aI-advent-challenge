from __future__ import annotations

import logging
import sys
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from .adb_ctl import adb_connect as adb_connect_cmd
from .adb_ctl import install_apk as install_apk_cmd
from .adb_ctl import launch_app as launch_app_cmd
from .adb_ctl import list_devices as list_devices_cmd
from .adb_ctl import wait_boot_completed as wait_boot_completed_cmd
from .adb_ctl import capture_screenshot as capture_screenshot_cmd
from .docker_ctl import env_down as env_down_cmd
from .docker_ctl import env_status as env_status_cmd
from .docker_ctl import env_up as env_up_cmd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
LOGGER = logging.getLogger(__name__)


mcp = FastMCP(name="android-orchestrator")


@mcp.tool()
def env_up() -> str:
    """Start Android emulator docker-compose stack."""
    result = env_up_cmd()
    return result.as_summary()


@mcp.tool()
def env_down() -> str:
    """Stop Android emulator docker-compose stack."""
    result = env_down_cmd()
    return result.as_summary()


@mcp.tool()
def env_status() -> str:
    """Show docker-compose service status."""
    result = env_status_cmd()
    return result.as_summary()


@mcp.tool()
def adb_connect(host: str = "127.0.0.1", port: int = 5555) -> str:
    """Run 'adb connect host:port'."""
    result = adb_connect_cmd(host=host, port=port)
    return result.as_summary()


@mcp.tool()
def list_devices() -> List[str]:
    """List connected ADB device serials."""
    return list_devices_cmd()


@mcp.tool()
def wait_boot_completed(serial: Optional[str] = None, timeout_sec: int = 300) -> bool:
    """Wait until 'getprop sys.boot_completed' returns 1."""
    LOGGER.info("Waiting for boot completion (serial=%s, timeout=%ss)", serial, timeout_sec)
    return wait_boot_completed_cmd(serial=serial, timeout_sec=timeout_sec)


@mcp.tool()
def install_apk(apk_path: str, serial: Optional[str] = None) -> str:
    """Install an APK via 'adb install -r'."""
    result = install_apk_cmd(apk_path=apk_path, serial=serial)
    return result.as_summary()


@mcp.tool()
def launch_app(package: str, activity: Optional[str] = None, serial: Optional[str] = None) -> str:
    """Launch an app by activity or default launcher intent."""
    result = launch_app_cmd(package=package, activity=activity, serial=serial)
    return result.as_summary()


@mcp.tool()
def capture_screenshot(serial: Optional[str] = None, output_path: Optional[str] = None) -> str:
    """Take screenshot via adb; saved locally."""
    return capture_screenshot_cmd(serial=serial, output_path=output_path)


def main() -> None:
    """Entrypoint for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

