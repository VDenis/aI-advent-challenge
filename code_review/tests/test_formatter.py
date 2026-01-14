"""Tests for ReviewFormatter."""

from code_review.formatter import ReviewFormatter
from code_review.models import Issue, ReviewResult


def test_format_review_with_blocking_issues():
    """Test formatting review with blocking issues."""
    result = ReviewResult(
        summary="This PR introduces a security vulnerability.",
        blocking_issues=[
            Issue(
                severity="blocking",
                file="api/auth.py",
                line=45,
                description="Password comparison uses == instead of constant-time comparison",
                suggestion="Use secrets.compare_digest() for constant-time comparison",
            )
        ],
        non_blocking_issues=[],
        tests_assessment="Tests are present but incomplete",
        risks=["Security risk: timing attack possible"],
        suggested_improvements=["Add more test coverage for edge cases"],
    )

    formatter = ReviewFormatter()
    markdown = formatter.format_review(result, "https://github.com/owner/repo/pull/123")

    # Check that key sections are present
    assert "# 🤖 AI Code Review" in markdown
    assert "## Summary" in markdown
    assert "## 🚨 Blocking Issues" in markdown
    assert "api/auth.py:45" in markdown
    assert "secrets.compare_digest()" in markdown
    assert "## 🧪 Tests" in markdown
    assert "## ⚠️ Risks" in markdown
    assert "## 🚀 Suggested Improvements" in markdown


def test_format_review_no_blocking_issues():
    """Test formatting review without blocking issues."""
    result = ReviewResult(
        summary="Code looks good overall.",
        blocking_issues=[],
        non_blocking_issues=[
            Issue(
                severity="non-blocking",
                file="utils.py",
                line=10,
                description="Variable name could be more descriptive",
                suggestion="Rename 'x' to 'user_count' for clarity",
            )
        ],
        tests_assessment="Good test coverage",
        risks=[],
        suggested_improvements=[],
    )

    formatter = ReviewFormatter()
    markdown = formatter.format_review(result)

    assert "## ✅ No Blocking Issues" in markdown
    assert "## 💡 Non-Blocking Issues" in markdown
    assert "utils.py:10" in markdown


def test_format_issue_with_line_number():
    """Test formatting issue with line number."""
    issue = Issue(
        severity="blocking",
        file="test.py",
        line=42,
        description="Bug here",
        suggestion="Fix it",
    )

    formatter = ReviewFormatter()
    formatted = formatter._format_issue(issue)

    assert "test.py:42" in formatted
    assert "Bug here" in formatted
    assert "Fix it" in formatted


def test_format_issue_without_line_number():
    """Test formatting issue without line number."""
    issue = Issue(
        severity="non-blocking",
        file="test.py",
        line=None,
        description="General comment",
        suggestion="Consider this",
    )

    formatter = ReviewFormatter()
    formatted = formatter._format_issue(issue)

    assert "test.py" in formatted
    assert "test.py:" not in formatted  # Should not have colon if no line number
    assert "General comment" in formatted
