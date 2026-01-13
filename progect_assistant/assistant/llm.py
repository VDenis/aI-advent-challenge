import json
from typing import Any, Dict, List, Optional

import httpx


class LLMError(RuntimeError):
    pass


def _openai_headers(api_key: Optional[str]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def openai_chat_completion(
    *,
    base_url: str,
    api_key: Optional[str],
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload: Dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
    try:
        response = httpx.post(url, json=payload, headers=_openai_headers(api_key), timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenAI-compatible request failed: {exc}") from exc
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise LLMError(f"OpenAI-compatible error: {data['error']}")
    return data


