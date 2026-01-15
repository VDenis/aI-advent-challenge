import abc
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass
class ToolContext:
    project_root: str
    request_id: str
    max_output_chars: int = 4000


class Tool(abc.ABC):
    name: str
    description: str
    parameters_schema: Dict[str, Any]

    @abc.abstractmethod
    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> Iterable[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)
