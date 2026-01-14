"""Data models for AI Code Review system."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PRData:
    """Pull Request metadata."""
    number: int
    title: str
    description: str
    author: str
    base_branch: str
    head_branch: str
    files_changed: int
    lines_added: int
    lines_deleted: int
    html_url: str


@dataclass
class PRFile:
    """Changed file details in a PR."""
    path: str
    status: str  # "added", "modified", "deleted", "renamed"
    additions: int
    deletions: int
    patch: Optional[str] = None  # Unified diff patch


@dataclass
class ReviewContext:
    """Full context for generating a code review."""
    pr_data: PRData
    pr_files: List[PRFile]
    relevant_docs: str  # RAG context from documentation
    existing_patterns: str  # RAG context from similar code
    token_count: int  # Estimated token count for LLM


@dataclass
class Issue:
    """Individual code review issue."""
    severity: str  # "blocking" or "non-blocking"
    file: str
    line: Optional[int]
    description: str
    suggestion: str


@dataclass
class ReviewResult:
    """Structured code review output."""
    summary: str
    blocking_issues: List[Issue] = field(default_factory=list)
    non_blocking_issues: List[Issue] = field(default_factory=list)
    tests_assessment: str = ""
    risks: List[str] = field(default_factory=list)
    suggested_improvements: List[str] = field(default_factory=list)
