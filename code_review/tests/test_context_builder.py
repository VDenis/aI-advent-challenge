"""Tests for ContextBuilder."""

from code_review.config import CodeReviewConfig
from code_review.context_builder import ContextBuilder
from code_review.models import PRData, PRFile


def test_estimate_tokens():
    """Test token estimation."""
    config = CodeReviewConfig(
        project_root="/tmp",
        github_repo="owner/repo",
        github_token="test",
        gigachat_credentials="test",
    )
    builder = ContextBuilder(config)

    # Roughly 4 chars per token
    text = "a" * 400
    tokens = builder._estimate_tokens(text)
    assert tokens == 100


def test_truncate_to_budget():
    """Test text truncation."""
    config = CodeReviewConfig(
        project_root="/tmp",
        github_repo="owner/repo",
        github_token="test",
        gigachat_credentials="test",
    )
    builder = ContextBuilder(config)

    # Text that exceeds budget
    text = "a" * 1000
    truncated = builder._truncate_to_budget(text, token_budget=50)

    # Should be truncated to ~200 chars (50 tokens * 4 chars/token)
    assert len(truncated) < len(text)
    assert "(truncated)" in truncated


def test_extract_key_terms():
    """Test key term extraction from PR."""
    config = CodeReviewConfig(
        project_root="/tmp",
        github_repo="owner/repo",
        github_token="test",
        gigachat_credentials="test",
    )
    builder = ContextBuilder(config)

    pr_data = PRData(
        number=1,
        title="Add user authentication",
        description="Implements JWT auth",
        author="test",
        base_branch="main",
        head_branch="feature/auth",
        files_changed=2,
        lines_added=50,
        lines_deleted=10,
        html_url="https://example.com",
    )

    pr_files = [
        PRFile(
            path="src/auth/jwt.py",
            status="added",
            additions=40,
            deletions=0,
            patch="@@ ... @@\n+def verify_token():\n+    pass",
        ),
        PRFile(
            path="tests/test_auth.py",
            status="added",
            additions=10,
            deletions=0,
            patch="",
        ),
    ]

    terms = builder._extract_key_terms(pr_data, pr_files)

    # Should contain title, description, file paths, and function names
    assert "authentication" in terms.lower()
    assert "jwt" in terms.lower()
    assert "auth" in terms.lower()
    assert "verify_token" in terms


def test_build_diff_context():
    """Test diff context building."""
    config = CodeReviewConfig(
        project_root="/tmp",
        github_repo="owner/repo",
        github_token="test",
        gigachat_credentials="test",
    )
    builder = ContextBuilder(config)

    pr_files = [
        PRFile(
            path="src/main.py",
            status="modified",
            additions=5,
            deletions=2,
            patch="@@ -1,5 +1,8 @@\n-old\n+new",
        )
    ]

    diff_text = builder._build_diff_context(pr_files)

    assert "src/main.py" in diff_text
    assert "modified" in diff_text
    assert "+5" in diff_text
    assert "@@ -1,5 +1,8 @@" in diff_text
