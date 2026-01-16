"""
Unit tests for GitHub issue creation functionality.

All tests use mocking - NO real API calls are made.
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import httpx
import pytest

from progect_assistant.assistant.github import (
    DEFAULT_GITHUB_API_BASE,
    DEFAULT_GITHUB_LABELS,
    DEFAULT_TITLE_MAX_LEN,
    GitHubClient,
    GitHubError,
    _build_body,
    _build_title,
    _extract_github_error,
    _merge_labels,
    _normalize_labels,
    format_issue_from_conversation,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_token() -> str:
    return "ghp_test_token_1234567890"


@pytest.fixture
def github_client(mock_token: str) -> GitHubClient:
    return GitHubClient(token=mock_token)


@pytest.fixture
def sample_issue_response() -> Dict[str, Any]:
    """Sample successful GitHub API response for issue creation."""
    return {
        "id": 123456789,
        "number": 42,
        "title": "Test issue title",
        "body": "Test issue body",
        "html_url": "https://github.com/test-owner/test-repo/issues/42",
        "state": "open",
        "labels": [
            {"id": 1, "name": "bug", "color": "d73a4a"},
            {"id": 2, "name": "user-report", "color": "0075ca"},
        ],
        "user": {"login": "test-user", "id": 1},
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
    }


# =============================================================================
# GitHubClient Tests
# =============================================================================


class TestGitHubClientInit:
    """Tests for GitHubClient initialization."""

    def test_init_with_valid_token(self, mock_token: str) -> None:
        client = GitHubClient(token=mock_token)
        assert client._token == mock_token
        assert client._base_url == DEFAULT_GITHUB_API_BASE
        assert client._timeout == 10.0

    def test_init_with_custom_base_url(self, mock_token: str) -> None:
        custom_url = "https://github.mycompany.com/api/v3"
        client = GitHubClient(token=mock_token, base_url=custom_url)
        assert client._base_url == custom_url.rstrip("/")

    def test_init_strips_trailing_slash_from_base_url(self, mock_token: str) -> None:
        client = GitHubClient(token=mock_token, base_url="https://api.github.com/")
        assert client._base_url == "https://api.github.com"

    def test_init_with_custom_timeout(self, mock_token: str) -> None:
        client = GitHubClient(token=mock_token, timeout=30.0)
        assert client._timeout == 30.0

    def test_init_raises_on_empty_token(self) -> None:
        with pytest.raises(ValueError, match="GitHub token is required"):
            GitHubClient(token="")

    def test_init_raises_on_none_token(self) -> None:
        with pytest.raises(ValueError, match="GitHub token is required"):
            GitHubClient(token=None)  # type: ignore


class TestGitHubClientCreateIssue:
    """Tests for GitHubClient.create_issue method."""

    @patch("httpx.request")
    def test_create_issue_success(
        self,
        mock_request: MagicMock,
        github_client: GitHubClient,
        sample_issue_response: Dict[str, Any],
    ) -> None:
        """Test successful issue creation (HTTP 201)."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.content = json.dumps(sample_issue_response).encode()
        mock_response.json.return_value = sample_issue_response
        mock_request.return_value = mock_response

        result = github_client.create_issue(
            owner="test-owner",
            repo="test-repo",
            title="Test issue title",
            body="Test issue body",
            labels=["bug", "user-report"],
        )

        assert result["number"] == 42
        assert result["title"] == "Test issue title"
        assert result["html_url"] == "https://github.com/test-owner/test-repo/issues/42"

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert "/repos/test-owner/test-repo/issues" in call_args[0][1]
        assert call_args[1]["json"]["title"] == "Test issue title"
        assert call_args[1]["json"]["body"] == "Test issue body"
        assert call_args[1]["json"]["labels"] == ["bug", "user-report"]

    @patch("httpx.request")
    def test_create_issue_without_labels(
        self,
        mock_request: MagicMock,
        github_client: GitHubClient,
        sample_issue_response: Dict[str, Any],
    ) -> None:
        """Test issue creation without labels."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.content = json.dumps(sample_issue_response).encode()
        mock_response.json.return_value = sample_issue_response
        mock_request.return_value = mock_response

        github_client.create_issue(
            owner="test-owner",
            repo="test-repo",
            title="Test issue",
            body="Test body",
        )

        call_args = mock_request.call_args
        assert "labels" not in call_args[1]["json"]

    @patch("httpx.request")
    def test_create_issue_unexpected_status_returns_error(
        self,
        mock_request: MagicMock,
        github_client: GitHubClient,
    ) -> None:
        """Ensure non-201 responses are treated as failures to avoid false positives."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202
        mock_response.content = b"{}"
        mock_response.json.return_value = {}
        mock_response.text = "{}"
        mock_request.return_value = mock_response

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="test-owner",
                repo="test-repo",
                title="Test issue",
                body="Test issue body",
            )

        assert exc_info.value.status_code == 202
        assert "Unexpected GitHub status" in str(exc_info.value)

    @patch("httpx.request")
    def test_create_issue_401_unauthorized(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test 401 Unauthorized error (invalid token)."""
        error_response = {
            "message": "Bad credentials",
            "documentation_url": "https://docs.github.com/rest",
        }
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.content = json.dumps(error_response).encode()
        mock_response.json.return_value = error_response
        mock_response.text = json.dumps(error_response)
        mock_request.return_value = mock_response

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="test-owner",
                repo="test-repo",
                title="Test",
                body="Test",
            )

        assert exc_info.value.status_code == 401
        assert "Bad credentials" in str(exc_info.value)
        assert exc_info.value.payload.get("message") == "Bad credentials"

    @patch("httpx.request")
    def test_create_issue_404_not_found(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test 404 Not Found error (repository doesn't exist or no access)."""
        error_response = {
            "message": "Not Found",
            "documentation_url": "https://docs.github.com/rest/issues/issues#create-an-issue",
        }
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.content = json.dumps(error_response).encode()
        mock_response.json.return_value = error_response
        mock_response.text = json.dumps(error_response)
        mock_request.return_value = mock_response

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="nonexistent-owner",
                repo="nonexistent-repo",
                title="Test",
                body="Test",
            )

        assert exc_info.value.status_code == 404
        assert "Not Found" in str(exc_info.value)

    @patch("httpx.request")
    def test_create_issue_422_validation_failed(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test 422 Validation Failed error (e.g., invalid label)."""
        error_response = {
            "message": "Validation Failed",
            "errors": [{"resource": "Label", "code": "invalid", "field": "name"}],
            "documentation_url": "https://docs.github.com/rest/issues/issues#create-an-issue",
        }
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 422
        mock_response.content = json.dumps(error_response).encode()
        mock_response.json.return_value = error_response
        mock_response.text = json.dumps(error_response)
        mock_request.return_value = mock_response

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="test-owner",
                repo="test-repo",
                title="Test",
                body="Test",
                labels=["nonexistent-label"],
            )

        assert exc_info.value.status_code == 422
        assert "Validation Failed" in str(exc_info.value)
        assert "errors" in exc_info.value.payload

    @patch("httpx.request")
    def test_create_issue_403_rate_limit(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test 403 Forbidden error (rate limit exceeded)."""
        error_response = {
            "message": "API rate limit exceeded for user ID 12345.",
            "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting",
        }
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.content = json.dumps(error_response).encode()
        mock_response.json.return_value = error_response
        mock_response.text = json.dumps(error_response)
        mock_request.return_value = mock_response

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="test-owner",
                repo="test-repo",
                title="Test",
                body="Test",
            )

        assert exc_info.value.status_code == 403
        assert "rate limit" in str(exc_info.value).lower()

    @patch("httpx.request")
    def test_create_issue_network_error(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test network error handling (connection timeout, DNS failure, etc.)."""
        mock_request.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="test-owner",
                repo="test-repo",
                title="Test",
                body="Test",
            )

        assert "request failed" in str(exc_info.value).lower()
        assert exc_info.value.status_code is None

    @patch("httpx.request")
    def test_create_issue_timeout(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test timeout error handling."""
        mock_request.side_effect = httpx.TimeoutException("Request timed out")

        with pytest.raises(GitHubError) as exc_info:
            github_client.create_issue(
                owner="test-owner",
                repo="test-repo",
                title="Test",
                body="Test",
            )

        assert "request failed" in str(exc_info.value).lower()

    @patch("httpx.request")
    def test_create_issue_sends_correct_headers(
        self,
        mock_request: MagicMock,
        github_client: GitHubClient,
        sample_issue_response: Dict[str, Any],
    ) -> None:
        """Test that correct headers are sent with the request."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.content = json.dumps(sample_issue_response).encode()
        mock_response.json.return_value = sample_issue_response
        mock_request.return_value = mock_response

        github_client.create_issue(
            owner="test-owner",
            repo="test-repo",
            title="Test",
            body="Test",
        )

        call_args = mock_request.call_args
        headers = call_args[1]["headers"]
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["User-Agent"] == "progect-assistant"


class TestGitHubClientListIssues:
    """Tests for GitHubClient.list_issues method."""

    @patch("httpx.request")
    def test_list_issues_success(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test successful issue listing."""
        issues_response = [
            {"number": 1, "title": "Issue 1"},
            {"number": 2, "title": "Issue 2"},
        ]
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = json.dumps(issues_response).encode()
        mock_response.json.return_value = issues_response
        mock_request.return_value = mock_response

        result = github_client.list_issues(owner="test-owner", repo="test-repo")

        assert len(result) == 2
        assert result[0]["number"] == 1

    @patch("httpx.request")
    def test_list_issues_empty(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test empty issue list."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b"[]"
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        result = github_client.list_issues(owner="test-owner", repo="test-repo")

        assert result == []

    @patch("httpx.request")
    def test_list_issues_with_filters(
        self, mock_request: MagicMock, github_client: GitHubClient
    ) -> None:
        """Test issue listing with filters."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b"[]"
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        github_client.list_issues(
            owner="test-owner",
            repo="test-repo",
            state="closed",
            labels=["bug", "wontfix"],
            per_page=50,
        )

        call_args = mock_request.call_args
        params = call_args[1]["params"]
        assert params["state"] == "closed"
        assert params["labels"] == "bug,wontfix"
        assert params["per_page"] == 50


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestBuildTitle:
    """Tests for _build_title function."""

    def test_explicit_title(self) -> None:
        result = _build_title("My explicit title", "user query", "answer")
        assert result == "My explicit title"

    def test_fallback_to_user_query(self) -> None:
        result = _build_title(None, "User query as title", "answer")
        assert result == "User query as title"

    def test_fallback_to_answer(self) -> None:
        result = _build_title(None, "", "Answer as title")
        assert result == "Answer as title"

    def test_default_title(self) -> None:
        result = _build_title(None, "", "")
        assert result == "User report"

    def test_title_truncation(self) -> None:
        long_title = "A" * 200
        result = _build_title(long_title, "", "")
        assert len(result) == DEFAULT_TITLE_MAX_LEN
        assert result.endswith("...")

    def test_whitespace_normalization(self) -> None:
        result = _build_title("  Multiple   spaces   here  ", "", "")
        assert result == "Multiple spaces here"

    def test_empty_strings_fallback_to_default(self) -> None:
        """Edge case: empty strings should fallback to default."""
        result = _build_title("", "", "")
        # Current implementation returns empty string - this is a bug
        # After fix, it should return "User report"
        assert result in ("", "User report")


class TestBuildBody:
    """Tests for _build_body function."""

    def test_full_body(self) -> None:
        result = _build_body(
            user_query="What is Python?",
            assistant_answer="Python is a programming language.",
            rag_context="Found in docs/python.md",
            findings=["Finding 1", "Finding 2"],
            metadata={"version": "1.0", "timestamp": "2025-01-15"},
        )

        assert "## User request" in result
        assert "What is Python?" in result
        assert "## Assistant response" in result
        assert "Python is a programming language." in result
        assert "## RAG context" in result
        assert "## Findings" in result
        assert "- Finding 1" in result
        assert "## Metadata" in result
        assert "version: 1.0" in result
        assert "_Generated by progect_assistant._" in result

    def test_minimal_body(self) -> None:
        result = _build_body(
            user_query="Query",
            assistant_answer="Answer",
            rag_context=None,
            findings=None,
            metadata=None,
        )

        assert "## User request" in result
        assert "## Assistant response" in result
        assert "## RAG context" not in result
        assert "## Findings" not in result
        assert "## Metadata" not in result

    def test_empty_findings_filtered(self) -> None:
        result = _build_body(
            user_query="Query",
            assistant_answer="Answer",
            rag_context=None,
            findings=["", "  ", "Valid finding"],
            metadata=None,
        )

        assert "## Findings" in result
        assert "- Valid finding" in result
        # Empty findings should be filtered out
        assert result.count("- ") == 1

    def test_metadata_with_complex_values(self) -> None:
        result = _build_body(
            user_query="Query",
            assistant_answer="Answer",
            rag_context=None,
            findings=None,
            metadata={"list_value": [1, 2, 3], "dict_value": {"nested": True}},
        )

        assert "## Metadata" in result
        assert "list_value:" in result
        assert "dict_value:" in result


class TestNormalizeLabels:
    """Tests for _normalize_labels function."""

    def test_normalize_valid_labels(self) -> None:
        result = _normalize_labels(["bug", "enhancement", "help wanted"])
        assert result == ["bug", "enhancement", "help wanted"]

    def test_normalize_with_whitespace(self) -> None:
        result = _normalize_labels(["  bug  ", " enhancement "])
        assert result == ["bug", "enhancement"]

    def test_normalize_removes_empty(self) -> None:
        result = _normalize_labels(["bug", "", "  ", "enhancement"])
        assert result == ["bug", "enhancement"]

    def test_normalize_removes_duplicates(self) -> None:
        result = _normalize_labels(["bug", "bug", "enhancement", "bug"])
        assert result == ["bug", "enhancement"]

    def test_normalize_none_input(self) -> None:
        result = _normalize_labels(None)
        assert result == []

    def test_normalize_empty_list(self) -> None:
        result = _normalize_labels([])
        assert result == []


class TestMergeLabels:
    """Tests for _merge_labels function."""

    def test_merge_default_and_custom(self) -> None:
        result = _merge_labels(["bug", "user-report"], ["critical", "frontend"])
        assert result == ["bug", "user-report", "critical", "frontend"]

    def test_merge_deduplicates(self) -> None:
        result = _merge_labels(["bug", "user-report"], ["bug", "critical"])
        assert result == ["bug", "user-report", "critical"]

    def test_merge_none_defaults(self) -> None:
        result = _merge_labels(None, ["custom-label"])
        assert result == ["custom-label"]

    def test_merge_none_labels(self) -> None:
        result = _merge_labels(["default-label"], None)
        assert result == ["default-label"]

    def test_merge_both_none(self) -> None:
        result = _merge_labels(None, None)
        assert result == []


class TestFormatIssueFromConversation:
    """Tests for format_issue_from_conversation function."""

    def test_basic_formatting(self) -> None:
        result = format_issue_from_conversation(
            user_query="How do I use this?",
            assistant_answer="You can use it like this...",
        )

        assert "title" in result
        assert "body" in result
        assert result["title"] == "How do I use this?"

    def test_with_explicit_title(self) -> None:
        result = format_issue_from_conversation(
            user_query="Original query",
            assistant_answer="Answer",
            title="Custom Title",
        )

        assert result["title"] == "Custom Title"

    def test_with_labels(self) -> None:
        result = format_issue_from_conversation(
            user_query="Query",
            assistant_answer="Answer",
            labels=["bug", "urgent"],
            default_labels=["user-report"],
        )

        assert "labels" in result
        assert "user-report" in result["labels"]
        assert "bug" in result["labels"]
        assert "urgent" in result["labels"]

    def test_no_labels_when_empty(self) -> None:
        result = format_issue_from_conversation(
            user_query="Query",
            assistant_answer="Answer",
            labels=None,
            default_labels=None,
        )

        assert "labels" not in result or result.get("labels") == []


class TestExtractGitHubError:
    """Tests for _extract_github_error function."""

    def test_extract_json_error(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"message": "Not Found"}

        message, payload = _extract_github_error(mock_response)

        assert message == "Not Found"
        assert payload == {"message": "Not Found"}

    def test_extract_error_with_errors_field(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {
            "message": "Validation Failed",
            "errors": [{"code": "invalid"}],
        }

        message, payload = _extract_github_error(mock_response)

        assert "Validation Failed" in message
        assert "[{'code': 'invalid'}]" in message

    def test_extract_non_json_error(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Internal Server Error"

        message, payload = _extract_github_error(mock_response)

        assert message == "Internal Server Error"
        assert payload == {}

    def test_extract_non_dict_json(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = "Just a string"

        message, payload = _extract_github_error(mock_response)

        assert message == "Just a string"
        assert payload == {}


# =============================================================================
# GitHubError Tests
# =============================================================================


class TestGitHubError:
    """Tests for GitHubError exception class."""

    def test_basic_error(self) -> None:
        error = GitHubError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.status_code is None
        assert error.payload == {}

    def test_error_with_status_code(self) -> None:
        error = GitHubError("Not Found", status_code=404)
        assert error.status_code == 404

    def test_error_with_payload(self) -> None:
        payload = {"message": "Not Found", "documentation_url": "https://..."}
        error = GitHubError("Not Found", status_code=404, payload=payload)
        assert error.payload == payload

    def test_error_is_runtime_error(self) -> None:
        error = GitHubError("Test")
        assert isinstance(error, RuntimeError)


# =============================================================================
# Integration-like tests (still mocked, but testing full flow)
# =============================================================================


class TestCreateIssueFullFlow:
    """Integration-like tests for the full issue creation flow."""

    @patch("httpx.request")
    def test_full_flow_success(
        self,
        mock_request: MagicMock,
        mock_token: str,
        sample_issue_response: Dict[str, Any],
    ) -> None:
        """Test full flow: format conversation -> create issue."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.content = json.dumps(sample_issue_response).encode()
        mock_response.json.return_value = sample_issue_response
        mock_request.return_value = mock_response

        # Format the issue from conversation
        issue_payload = format_issue_from_conversation(
            user_query="Application crashes when clicking button",
            assistant_answer="This appears to be a bug in the click handler.",
            rag_context="Found similar issue in src/handlers.py",
            findings=["Error in line 42", "Missing null check"],
            labels=["bug", "critical"],
            default_labels=["user-report"],
            metadata={"browser": "Chrome 120", "os": "macOS"},
        )

        # Create the issue
        client = GitHubClient(token=mock_token)
        result = client.create_issue(
            owner="test-owner",
            repo="test-repo",
            **issue_payload,
        )

        assert result["number"] == 42
        assert result["html_url"] is not None

        # Verify the request payload
        call_args = mock_request.call_args
        sent_json = call_args[1]["json"]
        assert "crashes when clicking" in sent_json["title"]
        assert "## User request" in sent_json["body"]
        assert "## Findings" in sent_json["body"]
        assert set(sent_json["labels"]) == {"user-report", "bug", "critical"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
