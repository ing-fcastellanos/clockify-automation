from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)


_DEFAULT_PAGE_SIZE = 50
_MAX_RETRIES = 4
_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 30.0


def make_jira_client(base_url: str, email: str, api_token: str, timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        auth=httpx.BasicAuth(email, api_token),
        timeout=timeout,
        headers={"Accept": "application/json"},
    )


def _request_with_retry(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    sleep: callable = time.sleep,  # type: ignore[valid-type]
) -> httpx.Response:
    backoff = _BASE_BACKOFF_SECONDS
    last_response: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES):
        response = client.request(method, path, params=params)
        last_response = response
        logger.info("jira %s %s -> %s", method, path, response.status_code)

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == _MAX_RETRIES - 1:
                break
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header is not None:
                try:
                    wait = float(retry_after_header)
                except ValueError:
                    wait = backoff
            else:
                wait = backoff + random.uniform(0, backoff)
            wait = min(wait, _MAX_BACKOFF_SECONDS)
            logger.info("jira retry in %.2fs (attempt %d)", wait, attempt + 1)
            sleep(wait)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
            continue
        return response

    assert last_response is not None
    return last_response


def search_candidate_issues(
    client: httpx.Client,
    jql: str,
    fields: list[str] | None = None,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    fields_csv = ",".join(fields) if fields else "summary"
    start = 0
    while True:
        params = {
            "jql": jql,
            "fields": fields_csv,
            "expand": "changelog",
            "startAt": start,
            "maxResults": page_size,
        }
        response = _request_with_retry(client, "GET", "/rest/api/3/search", params=params)
        response.raise_for_status()
        data = response.json()
        issues = data.get("issues", [])
        yield from issues
        total = data.get("total", 0)
        start += len(issues)
        if not issues or start >= total:
            return
