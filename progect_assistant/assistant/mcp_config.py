import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _default_config_path(project_root: str) -> Path:
    return Path(project_root) / "progect_assistant" / "mcp_config.json"


def load_mcp_config(project_root: str) -> Dict[str, Any]:
    raw_path = os.environ.get("MCP_CONFIG_PATH")
    config_path = Path(raw_path) if raw_path else _default_config_path(project_root)
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def resolve_mcp_entry(
    project_root: str, name: str, fallback_command: Optional[str] = None
) -> Dict[str, Any]:
    config = load_mcp_config(project_root)
    entry = config.get(name, {}) if isinstance(config, dict) else {}
    command = entry.get("command") or fallback_command or ""
    env = entry.get("env", {}) if isinstance(entry, dict) else {}

    resolved_env: Dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(value, str):
            resolved_env[key] = str(value)
            continue
        resolved_env[key] = value.replace("${PROJECT_ROOT}", project_root)
    return {"command": command, "env": resolved_env}
