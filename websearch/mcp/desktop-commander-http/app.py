from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.responses import JSONResponse

ROOT_DIR = Path(os.getenv("DESKTOP_ROOT", "/workspace")).resolve()
APP_NAME = "desktop-commander-http"
APP_VERSION = "0.1.0"

app = FastAPI()


def _ensure_within_root(path: Path) -> Path:
    path = path.resolve()
    try:
        path.relative_to(ROOT_DIR)
    except ValueError:
        raise ValueError(f"Path {path} escapes root {ROOT_DIR}")
    return path


def _resolve_path(raw: str | None) -> Path:
    if not raw or raw.strip() in {".", "/"}:
        return ROOT_DIR
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return _ensure_within_root(candidate)


def _make_error(req_id: Any, message: str, code: int = -32000, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message, "data": data or {}}}


async def handle_initialize(req_id: Any) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": APP_NAME, "version": APP_VERSION},
            "capabilities": {},
        },
    }


async def handle_tools_list(req_id: Any) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": "write_file",
                    "description": "Сохранить файл в рабочей директории",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "mode": {"type": "string", "enum": ["w", "a"], "default": "w"},
                        },
                        "required": ["path", "content"],
                    },
                },
                {
                    "name": "read_file",
                    "description": "Прочитать текстовый файл",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                        "required": ["path"],
                    },
                },
                {
                    "name": "list_directory",
                    "description": "Список файлов и папок",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                    },
                },
            ]
        },
    }


def _list_dir(path: Path) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        entries.append(
            {
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "path": str(child),
            }
        )
    return {"entries": entries, "path": str(path)}


async def handle_tools_call(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") or {}

    try:
        if name == "write_file":
            target = _resolve_path(str(args.get("path") or ""))
            mode = str(args.get("mode") or "w")
            if mode not in {"w", "a"}:
                return _make_error(req_id, f"Unsupported mode {mode}", code=-32602)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open(mode, encoding="utf-8") as f:
                f.write(str(args.get("content") or ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {"path": str(target)}}

        if name == "read_file":
            target = _resolve_path(str(args.get("path") or ""))
            if not target.exists() or target.is_dir():
                return _make_error(req_id, f"File not found: {target}", code=-32602)
            content = target.read_text(encoding="utf-8", errors="replace")
            return {"jsonrpc": "2.0", "id": req_id, "result": {"path": str(target), "content": content}}

        if name == "list_directory":
            target = _resolve_path(str(args.get("path") or "."))
            if not target.exists() or not target.is_dir():
                return _make_error(req_id, f"Directory not found: {target}", code=-32602)
            return {"jsonrpc": "2.0", "id": req_id, "result": _list_dir(target)}

        return _make_error(req_id, f"Unknown tool {name}", code=-32601)
    except Exception as exc:  # noqa: BLE001
        return _make_error(req_id, f"{exc}", code=-32000)


@app.post("/")
@app.post("/mcp")
async def rpc_root(payload: Dict[str, Any]) -> JSONResponse:
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        resp = await handle_initialize(req_id)
    elif method == "tools/list":
        resp = await handle_tools_list(req_id)
    elif method == "tools/call":
        resp = await handle_tools_call(req_id, params)
    else:
        resp = _make_error(req_id, "Method not found", code=-32601)
    return JSONResponse(resp)


@app.get("/ping")
async def ping() -> Dict[str, str]:
    return {"message": "pong", "root": str(ROOT_DIR)}
