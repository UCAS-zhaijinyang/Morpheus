"""DeepSeek Search and Fetch API client."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()


class DeepSeekSearchError(RuntimeError):
    """Raised when the DeepSeek Search or Fetch API cannot return a result."""


def _base_url() -> str:
    return os.environ.get(
        "DEEPSEEK_SEARCH_BASE_URL",
        "https://api.deepseek.com/v1",
    ).rstrip("/")


def _api_key() -> str:
    api_key = os.environ.get("DEEPSEEK_SEARCH_API_KEY")
    if not api_key:
        raise DeepSeekSearchError("DEEPSEEK_SEARCH_API_KEY is not configured")
    return api_key


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        f"{_base_url()}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise DeepSeekSearchError(
            f"DeepSeek Search request failed with HTTP {error.code}: {detail}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise DeepSeekSearchError(f"DeepSeek Search request failed: {error}") from error

    if not isinstance(body, dict):
        raise DeepSeekSearchError("DeepSeek Search returned an invalid response")
    return body


def search_web(
    query: str,
    *,
    count: int = 5,
    ori_question: str | None = None,
    localization: str | None = None,
    need_content: bool = True,
) -> list[dict[str, Any]]:
    """Search the web through DeepSeek Search API."""

    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if len(normalized_query) > 128:
        normalized_query = normalized_query[:128]

    bounded_count = max(1, min(50, int(count)))
    payload: dict[str, Any] = {
        "query": normalized_query,
        "count": bounded_count,
        "need_content": bool(need_content),
    }
    if ori_question:
        payload["ori_question"] = str(ori_question)[:128]
    if localization:
        payload["localization"] = localization

    response = _post("/tools/search", payload)
    results = response.get("results", [])
    if not isinstance(results, list):
        raise DeepSeekSearchError("DeepSeek Search response has invalid results")
    return [item for item in results if isinstance(item, dict)]


def fetch_webpage(url: str) -> dict[str, str]:
    """Fetch one webpage as Markdown through DeepSeek Fetch API."""

    normalized_url = str(url or "").strip()
    if not normalized_url.startswith(("http://", "https://")):
        raise ValueError("url must be an HTTP or HTTPS URL")

    response = _post("/tools/fetch", {"url": normalized_url})
    return {
        "title": str(response.get("title", "")),
        "content": str(response.get("content", "")),
    }


def format_search_context(results: list[dict[str, Any]], limit: int = 5) -> str:
    """Format search results for a downstream employee or tool-agent prompt."""

    rows = []
    for index, result in enumerate(results[:limit], start=1):
        summary = str(result.get("summary") or result.get("snippet", ""))[:2000]
        content = str(result.get("content", ""))[:4000]
        rows.append(
            "\n".join(
                [
                    f"[{index}] {result.get('title', '')}",
                    f"URL: {result.get('url', '')}",
                    f"Summary: {summary}",
                    f"Content: {content}",
                ]
            )
        )
    return "\n\n".join(rows) or "No search results were returned."
