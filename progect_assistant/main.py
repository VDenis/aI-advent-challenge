import logging
import os
from pathlib import Path

from progect_assistant.assistant.runtime import AgentRuntime, RuntimeConfig
from progect_assistant.assistant.tools import ToolRegistry
from progect_assistant.assistant.tooling import (
    GitDiffTool,
    GitStatusTool,
    RagSearchTool,
    ReadFileSnippetTool,
)


def setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("assistant")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def build_registry(cache_path: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RagSearchTool(cache_path))
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())
    registry.register(ReadFileSnippetTool())
    return registry


def main() -> None:
    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    cache_path = os.environ.get(
        "ASSISTANT_CACHE_PATH",
        str(Path("progect_assistant") / ".cache" / "rag_index.json"),
    )
    log_path = os.environ.get(
        "ASSISTANT_LOG_PATH",
        str(Path("progect_assistant") / "logs" / "assistant.log"),
    )
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(log_path)
    registry = build_registry(cache_path)
    runtime = AgentRuntime(RuntimeConfig(project_root=project_root, cache_path=cache_path), registry, logger)
    runtime.run()


if __name__ == "__main__":
    main()
