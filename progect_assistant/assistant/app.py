import logging
import os
from dataclasses import dataclass
from pathlib import Path

from progect_assistant.assistant.core import AgentRuntime, RuntimeConfig, ToolRegistry
from progect_assistant.assistant.tools import (
    CreateTicketTool,
    FindSimilarTicketsTool,
    GetTicketTool,
    GetUserContextTool,
    GitDiffTool,
    GitStatusTool,
    RagSearchTool,
    ReadFileSnippetTool,
    SearchFAQTool,
    SearchTicketsTool,
    UpdateTicketTool,
)


@dataclass
class AppConfig:
    project_root: str
    cache_path: str
    log_path: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
        cache_path = os.environ.get(
            "ASSISTANT_CACHE_PATH",
            str(Path("progect_assistant") / ".cache" / "rag_index.json"),
        )
        log_path = os.environ.get(
            "ASSISTANT_LOG_PATH",
            str(Path("progect_assistant") / "logs" / "assistant.log"),
        )
        return cls(project_root=project_root, cache_path=cache_path, log_path=log_path)


def build_logger(log_path: str) -> logging.Logger:
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

    # Support service tools
    registry.register(SearchFAQTool())
    registry.register(GetTicketTool())
    registry.register(CreateTicketTool())
    registry.register(UpdateTicketTool())
    registry.register(SearchTicketsTool())
    registry.register(GetUserContextTool())
    registry.register(FindSimilarTicketsTool())

    return registry


def create_runtime(config: AppConfig) -> AgentRuntime:
    Path(config.log_path).parent.mkdir(parents=True, exist_ok=True)
    logger = build_logger(config.log_path)
    registry = build_registry(config.cache_path)
    runtime_config = RuntimeConfig(project_root=config.project_root, cache_path=config.cache_path)
    return AgentRuntime(runtime_config, registry, logger)
