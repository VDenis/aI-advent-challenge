"""AI-powered code reviewer using GigaChat."""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services"))

from gigachat.client import GigaChatClient
from gigachat.config import GigaChatConfig

from .config import CodeReviewConfig
from .models import Issue, ReviewContext, ReviewResult


class AIReviewer:
    """Generates code reviews using GigaChat LLM."""

    def __init__(self, config: CodeReviewConfig):
        self.config = config

        # Initialize GigaChat client
        gigachat_config = GigaChatConfig()
        gigachat_config.basic_auth = config.gigachat_credentials
        self.gigachat = GigaChatClient(gigachat_config)

        # Load system prompt template
        prompts_dir = Path(__file__).parent / "prompts"
        self.system_prompt_template = (prompts_dir / "system_prompt.txt").read_text()

    def _build_system_prompt(self, context: ReviewContext) -> str:
        """Build system prompt with RAG context."""
        project_name = self.config.github_repo

        # Avoid .format() so JSON braces in the prompt stay literal
        prompt = self.system_prompt_template
        prompt = prompt.replace("{project_name}", project_name)
        prompt = prompt.replace("{relevant_docs}", context.relevant_docs)
        prompt = prompt.replace("{existing_patterns}", context.existing_patterns)
        return prompt

    def _build_user_prompt(self, context: ReviewContext) -> str:
        """Build user prompt with PR details."""
        pr = context.pr_data

        # Build diff context
        diff_parts = []
        for pr_file in context.pr_files:
            diff_parts.append(f"\n### File: {pr_file.path}")
            diff_parts.append(f"Status: {pr_file.status}")
            diff_parts.append(f"Changes: +{pr_file.additions} -{pr_file.deletions}")

            if pr_file.patch:
                diff_parts.append("\n```diff")
                diff_parts.append(pr_file.patch)
                diff_parts.append("```")
            else:
                diff_parts.append("(No diff available)")

        diff_text = "\n".join(diff_parts)

        return f"""PULL REQUEST REVIEW REQUEST

PR #{pr.number}: {pr.title}
Author: {pr.author}
Base Branch: {pr.base_branch} ← Head Branch: {pr.head_branch}
Files Changed: {pr.files_changed} | Lines: +{pr.lines_added} -{pr.lines_deleted}

## Description
{pr.description or "(No description provided)"}

## Changes
{diff_text}

Please review this pull request following the guidelines. Return valid JSON only.
"""

    def _parse_review_response(self, response: str) -> ReviewResult:
        """Parse GigaChat response into ReviewResult."""
        # Try to extract JSON from response
        # GigaChat might wrap JSON in markdown code blocks
        json_text = response.strip()

        # Remove markdown code blocks if present
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            json_text = "\n".join(lines)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse review response as JSON: {e}\n\nResponse:\n{response}")

        # Parse issues
        blocking_issues = []
        for issue_data in data.get("blocking_issues", []):
            blocking_issues.append(
                Issue(
                    severity="blocking",
                    file=issue_data.get("file", "unknown"),
                    line=issue_data.get("line"),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", ""),
                )
            )

        non_blocking_issues = []
        for issue_data in data.get("non_blocking_issues", []):
            non_blocking_issues.append(
                Issue(
                    severity="non-blocking",
                    file=issue_data.get("file", "unknown"),
                    line=issue_data.get("line"),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", ""),
                )
            )

        return ReviewResult(
            summary=data.get("summary", "No summary provided"),
            blocking_issues=blocking_issues,
            non_blocking_issues=non_blocking_issues,
            tests_assessment=data.get("tests_assessment", ""),
            risks=data.get("risks", []),
            suggested_improvements=data.get("suggested_improvements", []),
        )

    async def review_pr(self, context: ReviewContext) -> ReviewResult:
        """Generate code review using GigaChat."""
        system_prompt = self._build_system_prompt(context)
        user_prompt = self._build_user_prompt(context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Call GigaChat
        try:
            response = await self.gigachat.chat(messages, temperature=0.3)
        except Exception as e:
            raise RuntimeError(f"GigaChat API error: {e}")

        # Parse response
        try:
            result = self._parse_review_response(response)
        except ValueError as e:
            # If parsing fails, return a generic error result
            return ReviewResult(
                summary=f"Failed to parse review response: {e}",
                blocking_issues=[],
                non_blocking_issues=[],
                tests_assessment="Review failed",
                risks=["AI review generation failed"],
                suggested_improvements=["Needs human review"],
            )

        return result
