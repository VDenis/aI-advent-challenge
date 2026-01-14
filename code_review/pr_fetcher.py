"""Fetch Pull Request data using MCP GitHub server."""

import os
import shlex
from typing import List

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../progect_assistant"))

from assistant.mcp_client import MCPStdioClient

from .config import CodeReviewConfig
from .models import PRData, PRFile


class PRSizeError(Exception):
    """Raised when PR exceeds size limits."""
    pass


class PRFetcher:
    """Fetches PR data via MCP GitHub server."""

    def __init__(self, config: CodeReviewConfig):
        self.config = config
        env = {
            "GITHUB_PERSONAL_ACCESS_TOKEN": config.github_token,
        }
        self.client = MCPStdioClient(
            command=shlex.split(config.mcp_github_command),
            name="github-mcp",
            env=env,
        )

    async def fetch_pr_details(self, pr_number: int) -> PRData:
        """Fetch PR metadata using MCP."""
        result = await self.client.call_tool(
            "get_pull_request",
            {
                "owner": self.config.repo_owner,
                "repo": self.config.repo_name,
                "pull_number": pr_number,
            },
        )

        # Parse result - MCP GitHub returns content array
        content = result.get("content", [])
        if not content:
            raise ValueError(f"No content in MCP response: {result}")

        # Extract text from content blocks
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")

        # Parse the response (it's usually JSON-formatted text)
        import json
        try:
            pr_data = json.loads(text)
        except json.JSONDecodeError:
            # If not JSON, treat as plain text description
            pr_data = {"body": text}

        # Build PRData from response
        return PRData(
            number=pr_number,
            title=pr_data.get("title", ""),
            description=pr_data.get("body", ""),
            author=pr_data.get("user", {}).get("login", "unknown"),
            base_branch=pr_data.get("base", {}).get("ref", "main"),
            head_branch=pr_data.get("head", {}).get("ref", ""),
            files_changed=pr_data.get("changed_files", 0),
            lines_added=pr_data.get("additions", 0),
            lines_deleted=pr_data.get("deletions", 0),
            html_url=pr_data.get("html_url", ""),
        )

    async def fetch_pr_files(self, pr_number: int) -> List[PRFile]:
        """Fetch list of changed files using MCP."""
        result = await self.client.call_tool(
            "get_pull_request_files",
            {
                "owner": self.config.repo_owner,
                "repo": self.config.repo_name,
                "pull_number": pr_number,
            },
        )

        # Parse result
        content = result.get("content", [])
        if not content:
            raise ValueError(f"No content in MCP response: {result}")

        # Extract text
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")

        # Parse JSON
        import json
        try:
            files_data = json.loads(text)
        except json.JSONDecodeError:
            files_data = []

        # Convert to PRFile objects
        pr_files = []
        for file_data in files_data:
            pr_files.append(
                PRFile(
                    path=file_data.get("filename", ""),
                    status=file_data.get("status", "modified"),
                    additions=file_data.get("additions", 0),
                    deletions=file_data.get("deletions", 0),
                    patch=file_data.get("patch"),
                )
            )

        return pr_files

    def validate_pr_size(self, pr_data: PRData) -> None:
        """Validate that PR is within size limits."""
        if pr_data.files_changed > self.config.max_files_per_review:
            raise PRSizeError(
                f"PR has {pr_data.files_changed} files, exceeds limit of {self.config.max_files_per_review}"
            )

        total_lines = pr_data.lines_added + pr_data.lines_deleted
        if total_lines > self.config.max_lines_per_review:
            raise PRSizeError(
                f"PR has {total_lines} lines changed, exceeds limit of {self.config.max_lines_per_review}"
            )

    async def close(self) -> None:
        """Close MCP client connection."""
        await self.client.close()
