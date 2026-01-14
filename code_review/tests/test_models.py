"""Tests for data models."""

from code_review.models import Issue, PRData, PRFile, ReviewContext, ReviewResult


def test_pr_data_creation():
    """Test PRData creation."""
    pr = PRData(
        number=123,
        title="Add feature",
        description="This adds a new feature",
        author="testuser",
        base_branch="main",
        head_branch="feature/new",
        files_changed=5,
        lines_added=100,
        lines_deleted=20,
        html_url="https://github.com/owner/repo/pull/123",
    )

    assert pr.number == 123
    assert pr.title == "Add feature"
    assert pr.files_changed == 5


def test_pr_file_creation():
    """Test PRFile creation."""
    file = PRFile(
        path="src/main.py",
        status="modified",
        additions=10,
        deletions=5,
        patch="@@ -1,5 +1,10 @@\n-old line\n+new line",
    )

    assert file.path == "src/main.py"
    assert file.status == "modified"
    assert file.additions == 10


def test_issue_creation():
    """Test Issue creation."""
    issue = Issue(
        severity="blocking",
        file="test.py",
        line=42,
        description="Security issue",
        suggestion="Fix this",
    )

    assert issue.severity == "blocking"
    assert issue.line == 42


def test_review_result_defaults():
    """Test ReviewResult with default values."""
    result = ReviewResult(summary="Test")

    assert result.summary == "Test"
    assert result.blocking_issues == []
    assert result.non_blocking_issues == []
    assert result.tests_assessment == ""
    assert result.risks == []
    assert result.suggested_improvements == []


def test_review_context_creation():
    """Test ReviewContext creation."""
    pr_data = PRData(
        number=1,
        title="Test",
        description="",
        author="test",
        base_branch="main",
        head_branch="test",
        files_changed=1,
        lines_added=10,
        lines_deleted=5,
        html_url="https://example.com",
    )

    context = ReviewContext(
        pr_data=pr_data,
        pr_files=[],
        relevant_docs="Some docs",
        existing_patterns="Some patterns",
        token_count=1000,
    )

    assert context.token_count == 1000
    assert context.relevant_docs == "Some docs"
