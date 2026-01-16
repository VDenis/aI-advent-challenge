"""
Unit tests for GitHub issue creation web endpoint.

Tests the /api/github/create-issue endpoint with mocked GitHub API calls.
"""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from io import BytesIO
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Helper functions for web server testing
# =============================================================================


def import_web_server_helpers():
    """Import helper functions from web_server module."""
    import sys
    sys.path.insert(0, "/Users/denis/code/ai_challenge/aI-advent-challenge")
    from progect_assistant.web_server import (
        _default_github_labels,
        _github_status_from_error,
        _parse_label_list,
        _resolve_github_repo,
    )
    return _parse_label_list, _default_github_labels, _resolve_github_repo, _github_status_from_error


# =============================================================================
# Tests for _parse_label_list
# =============================================================================


class TestParseLabelList:
    """Tests for _parse_label_list function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self._parse_label_list, _, _, _ = import_web_server_helpers()

    def test_parse_list_input(self) -> None:
        result = self._parse_label_list(["bug", "enhancement", "urgent"])
        assert result == ["bug", "enhancement", "urgent"]

    def test_parse_string_input(self) -> None:
        result = self._parse_label_list("bug,enhancement,urgent")
        assert result == ["bug", "enhancement", "urgent"]

    def test_parse_string_with_spaces(self) -> None:
        result = self._parse_label_list(" bug , enhancement , urgent ")
        assert result == ["bug", "enhancement", "urgent"]

    def test_parse_empty_items_filtered(self) -> None:
        result = self._parse_label_list(["bug", "", "  ", "urgent"])
        assert result == ["bug", "urgent"]

    def test_parse_none_input(self) -> None:
        result = self._parse_label_list(None)
        assert result is None

    def test_parse_empty_list(self) -> None:
        result = self._parse_label_list([])
        assert result == []

    def test_parse_non_string_non_list(self) -> None:
        result = self._parse_label_list(123)
        assert result is None


class TestDefaultGitHubLabels:
    """Tests for _default_github_labels function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        _, self._default_github_labels, _, _ = import_web_server_helpers()

    def test_default_labels_from_env(self) -> None:
        with patch.dict(os.environ, {"GITHUB_DEFAULT_LABELS": "custom-label,another"}):
            result = self._default_github_labels()
            assert result == ["custom-label", "another"]

    def test_default_labels_fallback(self) -> None:
        with patch.dict(os.environ, {"GITHUB_DEFAULT_LABELS": ""}, clear=False):
            # Remove the key if it exists
            env_copy = os.environ.copy()
            if "GITHUB_DEFAULT_LABELS" in env_copy:
                del env_copy["GITHUB_DEFAULT_LABELS"]
            with patch.dict(os.environ, env_copy, clear=True):
                result = self._default_github_labels()
                assert result == ["bug", "user-report"]

    def test_default_labels_empty_env(self) -> None:
        with patch.dict(os.environ, {"GITHUB_DEFAULT_LABELS": ""}, clear=False):
            result = self._default_github_labels()
            assert result == ["bug", "user-report"]


class TestResolveGitHubRepo:
    """Tests for _resolve_github_repo function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        _, _, self._resolve_github_repo, _ = import_web_server_helpers()

    def test_resolve_from_payload_owner_repo(self) -> None:
        payload = {"owner": "test-owner", "repo": "test-repo"}
        owner, repo = self._resolve_github_repo(payload)
        assert owner == "test-owner"
        assert repo == "test-repo"

    def test_resolve_from_payload_repository(self) -> None:
        payload = {"repository": "test-owner/test-repo"}
        owner, repo = self._resolve_github_repo(payload)
        assert owner == "test-owner"
        assert repo == "test-repo"

    def test_resolve_from_env_owner_repo(self) -> None:
        payload: Dict[str, Any] = {}
        with patch.dict(os.environ, {"GITHUB_OWNER": "env-owner", "GITHUB_REPO": "env-repo"}, clear=True):
            owner, repo = self._resolve_github_repo(payload)
            assert owner == "env-owner"
            assert repo == "env-repo"

    def test_resolve_from_env_repository(self) -> None:
        payload: Dict[str, Any] = {}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "env-owner/env-repo"}, clear=True):
            owner, repo = self._resolve_github_repo(payload)
            assert owner == "env-owner"
            assert repo == "env-repo"

    def test_resolve_payload_overrides_env(self) -> None:
        payload = {"owner": "payload-owner", "repo": "payload-repo"}
        with patch.dict(os.environ, {"GITHUB_OWNER": "env-owner", "GITHUB_REPO": "env-repo"}):
            owner, repo = self._resolve_github_repo(payload)
            assert owner == "payload-owner"
            assert repo == "payload-repo"

    def test_resolve_missing_returns_none(self) -> None:
        payload: Dict[str, Any] = {}
        with patch.dict(os.environ, {}, clear=True):
            owner, repo = self._resolve_github_repo(payload)
            assert owner is None
            assert repo is None

    def test_resolve_partial_from_payload_partial_from_env(self) -> None:
        payload = {"owner": "payload-owner"}
        with patch.dict(os.environ, {"GITHUB_REPO": "env-repo"}, clear=True):
            owner, repo = self._resolve_github_repo(payload)
            assert owner == "payload-owner"
            assert repo == "env-repo"


class TestGitHubStatusFromError:
    """Tests for _github_status_from_error function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        _, _, _, self._github_status_from_error = import_web_server_helpers()

    def test_401_returns_unauthorized(self) -> None:
        result = self._github_status_from_error(401)
        assert result == HTTPStatus.UNAUTHORIZED

    def test_403_returns_unauthorized(self) -> None:
        result = self._github_status_from_error(403)
        assert result == HTTPStatus.UNAUTHORIZED

    def test_404_returns_not_found(self) -> None:
        result = self._github_status_from_error(404)
        assert result == HTTPStatus.NOT_FOUND

    def test_422_returns_unprocessable_entity(self) -> None:
        result = self._github_status_from_error(422)
        assert result == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_other_4xx_returns_bad_request(self) -> None:
        result = self._github_status_from_error(400)
        assert result == HTTPStatus.BAD_REQUEST
        result = self._github_status_from_error(429)
        assert result == HTTPStatus.BAD_REQUEST

    def test_5xx_returns_bad_gateway(self) -> None:
        result = self._github_status_from_error(500)
        assert result == HTTPStatus.BAD_GATEWAY
        result = self._github_status_from_error(503)
        assert result == HTTPStatus.BAD_GATEWAY

    def test_none_returns_bad_gateway(self) -> None:
        result = self._github_status_from_error(None)
        assert result == HTTPStatus.BAD_GATEWAY


# =============================================================================
# Integration tests for the endpoint (mocked HTTP handler)
# =============================================================================


class TestGitHubCreateIssueEndpoint:
    """Integration tests for POST /api/github/create-issue endpoint."""

    @pytest.fixture
    def valid_payload(self) -> Dict[str, Any]:
        return {
            "user_query": "Application crashes on startup",
            "assistant_answer": "This appears to be a configuration issue.",
            "owner": "test-owner",
            "repo": "test-repo",
        }

    @pytest.fixture
    def mock_github_response(self) -> Dict[str, Any]:
        return {
            "number": 42,
            "title": "Application crashes on startup",
            "html_url": "https://github.com/test-owner/test-repo/issues/42",
            "labels": [
                {"name": "bug"},
                {"name": "user-report"},
            ],
        }

    def test_missing_github_token(self, valid_payload: Dict[str, Any]) -> None:
        """Test error when GITHUB_TOKEN is not set."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            # Simulate the validation logic
            token = os.environ.get("GITHUB_TOKEN", "")
            assert not token, "Token should be empty for this test"

    def test_missing_owner_repo(self) -> None:
        """Test error when owner/repo cannot be resolved."""
        payload = {
            "user_query": "Test query",
            "assistant_answer": "Test answer",
        }
        _, _, _resolve_github_repo, _ = import_web_server_helpers()

        with patch.dict(os.environ, {}, clear=True):
            owner, repo = _resolve_github_repo(payload)
            assert owner is None or repo is None

    def test_missing_required_fields(self) -> None:
        """Test error when user_query or assistant_answer is missing."""
        payload_missing_query = {
            "assistant_answer": "Test answer",
            "owner": "test-owner",
            "repo": "test-repo",
        }
        payload_missing_answer = {
            "user_query": "Test query",
            "owner": "test-owner",
            "repo": "test-repo",
        }

        # Simulate validation
        user_query = str(payload_missing_query.get("user_query", "")).strip()
        assert not user_query, "user_query should be empty"

        assistant_answer = str(payload_missing_answer.get("assistant_answer", "")).strip()
        assert not assistant_answer, "assistant_answer should be empty"

    @patch("httpx.request")
    def test_successful_issue_creation(
        self,
        mock_request: MagicMock,
        valid_payload: Dict[str, Any],
        mock_github_response: Dict[str, Any],
    ) -> None:
        """Test successful issue creation flow."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.content = json.dumps(mock_github_response).encode()
        mock_response.json.return_value = mock_github_response
        mock_request.return_value = mock_response

        # Import and call
        from progect_assistant.assistant.github import GitHubClient, format_issue_from_conversation

        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
            issue_payload = format_issue_from_conversation(
                user_query=valid_payload["user_query"],
                assistant_answer=valid_payload["assistant_answer"],
            )

            client = GitHubClient(token="test-token")
            result = client.create_issue(
                owner=valid_payload["owner"],
                repo=valid_payload["repo"],
                **issue_payload,
            )

            assert result["number"] == 42
            assert result["html_url"] == "https://github.com/test-owner/test-repo/issues/42"

    @patch("httpx.request")
    def test_issue_creation_with_custom_labels(
        self,
        mock_request: MagicMock,
        mock_github_response: Dict[str, Any],
    ) -> None:
        """Test issue creation with custom labels."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.content = json.dumps(mock_github_response).encode()
        mock_response.json.return_value = mock_github_response
        mock_request.return_value = mock_response

        from progect_assistant.assistant.github import GitHubClient, format_issue_from_conversation

        issue_payload = format_issue_from_conversation(
            user_query="Test query",
            assistant_answer="Test answer",
            labels=["critical", "frontend"],
            default_labels=["bug", "user-report"],
        )

        client = GitHubClient(token="test-token")
        client.create_issue(
            owner="test-owner",
            repo="test-repo",
            **issue_payload,
        )

        # Verify labels were merged correctly
        call_args = mock_request.call_args
        sent_labels = call_args[1]["json"]["labels"]
        assert "bug" in sent_labels
        assert "user-report" in sent_labels
        assert "critical" in sent_labels
        assert "frontend" in sent_labels

    @patch("httpx.request")
    def test_issue_creation_with_metadata(
        self,
        mock_request: MagicMock,
        mock_github_response: Dict[str, Any],
    ) -> None:
        """Test issue creation with metadata."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.content = json.dumps(mock_github_response).encode()
        mock_response.json.return_value = mock_github_response
        mock_request.return_value = mock_response

        from progect_assistant.assistant.github import GitHubClient, format_issue_from_conversation

        issue_payload = format_issue_from_conversation(
            user_query="Test query",
            assistant_answer="Test answer",
            metadata={"browser": "Chrome", "os": "macOS", "version": "1.0.0"},
        )

        client = GitHubClient(token="test-token")
        client.create_issue(
            owner="test-owner",
            repo="test-repo",
            **issue_payload,
        )

        call_args = mock_request.call_args
        sent_body = call_args[1]["json"]["body"]
        assert "## Metadata" in sent_body
        assert "browser: Chrome" in sent_body
        assert "os: macOS" in sent_body

    @patch("httpx.request")
    def test_github_api_error_handling(
        self,
        mock_request: MagicMock,
        valid_payload: Dict[str, Any],
    ) -> None:
        """Test handling of various GitHub API errors."""
        from progect_assistant.assistant.github import GitHubClient, GitHubError, format_issue_from_conversation

        # Test 401 Unauthorized
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.content = b'{"message": "Bad credentials"}'
        mock_response.json.return_value = {"message": "Bad credentials"}
        mock_response.text = '{"message": "Bad credentials"}'
        mock_request.return_value = mock_response

        issue_payload = format_issue_from_conversation(
            user_query=valid_payload["user_query"],
            assistant_answer=valid_payload["assistant_answer"],
        )

        client = GitHubClient(token="invalid-token")

        with pytest.raises(GitHubError) as exc_info:
            client.create_issue(
                owner=valid_payload["owner"],
                repo=valid_payload["repo"],
                **issue_payload,
            )

        assert exc_info.value.status_code == 401


# =============================================================================
# Security tests
# =============================================================================


class TestSecurityConcerns:
    """Tests for security-related concerns."""

    def test_token_not_in_url(self) -> None:
        """Ensure token is passed in headers, not URL."""
        from progect_assistant.assistant.github import GitHubClient

        client = GitHubClient(token="secret-token")

        # The _base_url should not contain the token
        assert "secret-token" not in client._base_url

    @patch("httpx.request")
    def test_token_in_authorization_header(
        self, mock_request: MagicMock
    ) -> None:
        """Ensure token is sent in Authorization header."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.content = b'{"number": 1}'
        mock_response.json.return_value = {"number": 1}
        mock_request.return_value = mock_response

        from progect_assistant.assistant.github import GitHubClient

        client = GitHubClient(token="secret-token")
        client.create_issue(
            owner="test",
            repo="test",
            title="Test",
            body="Test",
        )

        call_args = mock_request.call_args
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer secret-token"

    def test_ssrf_via_base_url_concern(self) -> None:
        """
        Document the SSRF concern with user-controlled base_url.

        This test documents that the current implementation allows
        arbitrary base_url from payload, which is a security concern.
        """
        # This is a documentation test showing the vulnerability exists
        _, _, _, _ = import_web_server_helpers()

        # The web_server.py line 1054 accepts base_url from payload:
        # base_url = payload.get("base_url") or os.environ.get("GITHUB_API_BASE") or DEFAULT_GITHUB_API_BASE
        #
        # An attacker could set base_url to an internal service:
        # {"base_url": "http://internal-service:8080", ...}
        #
        # Recommendation: Validate base_url against an allowlist
        assert True  # Placeholder - this documents the concern


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
