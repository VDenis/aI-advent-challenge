"""Configuration for AI Code Review system."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CodeReviewConfig:
    """Configuration for AI code review system."""

    # Project settings
    project_root: str
    github_repo: str  # Format: "owner/repo"

    # Authentication
    github_token: str
    gigachat_credentials: str

    # PR constraints
    max_files_per_review: int = 30
    max_lines_per_review: int = 2000

    # RAG settings
    rag_cache_path: str = ".cache/rag_index.json"

    # Token budget for GigaChat (8k context limit)
    review_context_limit: int = 6000  # tokens
    pr_metadata_tokens: int = 500
    rag_context_tokens: int = 2500
    diff_context_tokens: int = 3000

    # MCP settings
    mcp_github_command: str = "npx -y @modelcontextprotocol/server-github"

    @classmethod
    def from_env(cls) -> "CodeReviewConfig":
        """Create configuration from environment variables."""
        project_root = os.getenv("PROJECT_ROOT", os.getcwd())
        github_repo = os.getenv("GITHUB_REPO")
        if not github_repo:
            # Try to construct from REPO_OWNER and REPO_NAME
            owner = os.getenv("REPO_OWNER", "")
            name = os.getenv("REPO_NAME", "")
            if owner and name:
                github_repo = f"{owner}/{name}"
            else:
                raise ValueError("GITHUB_REPO or (REPO_OWNER + REPO_NAME) environment variable required")

        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable required")

        gigachat_credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not gigachat_credentials:
            raise ValueError("GIGACHAT_CREDENTIALS environment variable required")

        return cls(
            project_root=project_root,
            github_repo=github_repo,
            github_token=github_token,
            gigachat_credentials=gigachat_credentials,
            rag_cache_path=os.path.join(project_root, ".cache/rag_index.json"),
        )

    @property
    def repo_owner(self) -> str:
        """Extract owner from github_repo."""
        return self.github_repo.split("/")[0]

    @property
    def repo_name(self) -> str:
        """Extract repo name from github_repo."""
        return self.github_repo.split("/")[1]
