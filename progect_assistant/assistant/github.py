from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import httpx

DEFAULT_GITHUB_API_BASE = "https://api.github.com"
DEFAULT_GITHUB_LABELS = ["bug", "user-report"]
DEFAULT_TITLE_MAX_LEN = 120


def _parse_response_content(response: httpx.Response) -> Any:
    """Parse response content safely for both success and error cases."""
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


class GitHubError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class GitHubClient:
    """Minimal GitHub API client for issue operations."""

    def __init__(self, token: str, base_url: str = DEFAULT_GITHUB_API_BASE, timeout: float = 10.0):
        if not token:
            raise ValueError("GitHub token is required")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def create_issue(
        self, *, owner: str, repo: str, title: str, body: str, labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return self._request("POST", f"/repos/{owner}/{repo}/issues", json=payload, expected_status=(201,))

    def list_issues(
        self,
        *,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[List[str]] = None,
        per_page: int = 20,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = ",".join(labels)
        data = self._request("GET", f"/repos/{owner}/{repo}/issues", params=params, expected_status=(200,))
        return data if isinstance(data, list) else []

    def _request(self, method: str, path: str, expected_status: Optional[tuple[int, ...]] = None, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "progect-assistant",
        }
        try:
            response = httpx.request(method, url, headers=headers, timeout=self._timeout, **kwargs)
        except httpx.RequestError as exc:
            raise GitHubError(f"GitHub request failed: {exc}") from exc

        status = response.status_code
        if status < 200 or status >= 300:
            message, payload = _extract_github_error(response)
            raise GitHubError(message, status_code=status, payload=payload)

        if expected_status and status not in expected_status:
            payload = _parse_response_content(response)
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            expected_str = ", ".join(str(item) for item in expected_status)
            raise GitHubError(
                f"Unexpected GitHub status {status} (expected {expected_str})",
                status_code=status,
                payload=payload,
            )

        return _parse_response_content(response)


def format_issue_from_conversation(
    *,
    user_query: str,
    assistant_answer: str,
    rag_context: Optional[str] = None,
    findings: Optional[List[str]] = None,
    title: Optional[str] = None,
    labels: Optional[List[str]] = None,
    default_labels: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create GitHub issue payload from conversation context."""

    normalized_labels = _merge_labels(default_labels, labels)
    issue_title = _build_title(title, user_query, assistant_answer)
    issue_body = _build_body(
        user_query=user_query,
        assistant_answer=assistant_answer,
        rag_context=rag_context,
        findings=findings,
        metadata=metadata,
    )
    payload: Dict[str, Any] = {"title": issue_title, "body": issue_body}
    if normalized_labels:
        payload["labels"] = normalized_labels
    return payload


def _build_title(explicit: Optional[str], user_query: str, assistant_answer: str) -> str:
    candidate = explicit or user_query or assistant_answer or "User report"
    collapsed = " ".join(str(candidate).split())
    if len(collapsed) <= DEFAULT_TITLE_MAX_LEN:
        return collapsed
    return collapsed[: DEFAULT_TITLE_MAX_LEN - 3].rstrip() + "..."


def _build_body(
    *,
    user_query: str,
    assistant_answer: str,
    rag_context: Optional[str],
    findings: Optional[List[str]],
    metadata: Optional[Dict[str, Any]],
) -> str:
    sections: List[str] = []
    if user_query:
        sections.append(f"## User request\n{user_query.strip()}")
    if assistant_answer:
        sections.append(f"## Assistant response\n{assistant_answer.strip()}")
    if findings:
        formatted_findings = "\n".join(f"- {item}" for item in findings if str(item).strip())
        if formatted_findings:
            sections.append(f"## Findings\n{formatted_findings}")
    if rag_context:
        sections.append(f"## RAG context\n{rag_context.strip()}")
    if metadata:
        metadata_lines = []
        for key, value in metadata.items():
            rendered = _format_metadata_value(value)
            metadata_lines.append(f"- {key}: {rendered}")
        if metadata_lines:
            sections.append("## Metadata\n" + "\n".join(metadata_lines))
    sections.append("_Generated by progect_assistant._")
    return "\n\n".join(sections).strip()


def _format_metadata_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _merge_labels(default_labels: Optional[List[str]], labels: Optional[List[str]]) -> List[str]:
    merged: List[str] = []
    for item in _normalize_labels(default_labels):
        if item not in merged:
            merged.append(item)
    for item in _normalize_labels(labels):
        if item not in merged:
            merged.append(item)
    return merged


def _normalize_labels(labels: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for label in labels or []:
        text = str(label).strip()
        if not text:
            continue
        if text not in normalized:
            normalized.append(text)
    return normalized


def _extract_github_error(response: httpx.Response) -> Tuple[str, Dict[str, Any]]:
    try:
        payload = response.json()
    except ValueError:
        return response.text or "GitHub API error", {}

    if not isinstance(payload, dict):
        return str(payload), {}

    message = payload.get("message") or "GitHub API error"
    errors = payload.get("errors")
    if errors:
        message = f"{message}: {errors}"
    return message, payload
