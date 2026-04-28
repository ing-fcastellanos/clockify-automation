from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)


_BASE_URL = "https://api.clockify.me"
_DEFAULT_PAGE_SIZE = 200
_MAX_RETRIES = 4
_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 30.0


def make_clockify_client(api_key: str, timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        base_url=_BASE_URL,
        timeout=timeout,
        headers={
            "X-Api-Key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )


def _request_with_retry(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
    sleep: callable = time.sleep,  # type: ignore[valid-type]
) -> httpx.Response:
    backoff = _BASE_BACKOFF_SECONDS
    last_response: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES):
        response = client.request(method, path, params=params, json=json)
        last_response = response
        logger.info("clockify %s %s -> %s", method, path, response.status_code)

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
            logger.info("clockify retry in %.2fs (attempt %d)", wait, attempt + 1)
            sleep(wait)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
            continue
        return response

    assert last_response is not None
    return last_response


def resolve_user_id(client: httpx.Client) -> str:
    response = _request_with_retry(client, "GET", "/api/v1/user")
    response.raise_for_status()
    return response.json()["id"]


def list_user_entries(
    client: httpx.Client,
    workspace_id: str,
    user_id: str,
    start_iso_utc: str,
    end_iso_utc: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    page = 1
    while True:
        params = {
            "start": start_iso_utc,
            "end": end_iso_utc,
            "page": page,
            "page-size": page_size,
        }
        response = _request_with_retry(
            client,
            "GET",
            f"/api/v1/workspaces/{workspace_id}/user/{user_id}/time-entries",
            params=params,
        )
        response.raise_for_status()
        entries = response.json()
        if not entries:
            return
        yield from entries
        if len(entries) < page_size:
            return
        page += 1


def create_time_entry(
    client: httpx.Client, workspace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    response = _request_with_retry(
        client, "POST", f"/api/v1/workspaces/{workspace_id}/time-entries", json=payload
    )
    response.raise_for_status()
    return response.json()


def delete_time_entry(client: httpx.Client, workspace_id: str, entry_id: str) -> None:
    response = _request_with_retry(
        client, "DELETE", f"/api/v1/workspaces/{workspace_id}/time-entries/{entry_id}"
    )
    response.raise_for_status()
