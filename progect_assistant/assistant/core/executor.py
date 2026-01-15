import json
import logging
import time
from typing import Any, Dict

from .registry import ToolContext, ToolRegistry


class ToolExecutionError(Exception):
    pass


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, logger: logging.Logger) -> None:
        self._registry = registry
        self._logger = logger

    def execute(self, name: str, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        tool = self._registry.get(name)
        if not tool:
            raise ToolExecutionError(f"Unknown tool: {name}")

        start = time.time()
        self._logger.info("tool_start %s %s", name, json.dumps(params, ensure_ascii=True))
        try:
            result = tool.execute(params, context)
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("tool_error %s", name)
            raise ToolExecutionError(str(exc)) from exc
        finally:
            elapsed_ms = int((time.time() - start) * 1000)
            self._logger.info("tool_end %s %dms", name, elapsed_ms)

        if "output" in result:
            output = result["output"]
            if isinstance(output, str) and len(output) > context.max_output_chars:
                result["output"] = output[: context.max_output_chars] + "\n...output truncated..."

        return result
