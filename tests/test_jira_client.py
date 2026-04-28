from __future__ import annotations

import httpx
import respx

from clockyfy_automation.jira.client import (
    _request_with_retry,
    make_jira_client,
    search_candidate_issues,
)


@respx.mock
def test_retry_after_429_then_succeeds() -> None:
    sleeps: list[float] = []

    route = respx.get("https://example.atlassian.net/rest/api/3/search").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"issues": [], "total": 0}),
        ]
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        resp = _request_with_retry(
            client,
            "GET",
            "/rest/api/3/search",
            params={"jql": "x"},
            sleep=lambda s: sleeps.append(s),
        )

    assert resp.status_code == 200
    assert route.call_count == 2
    assert sleeps == [0.0]


@respx.mock
def test_retry_500_then_succeeds() -> None:
    sleeps: list[float] = []

    respx.get("https://example.atlassian.net/rest/api/3/search").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"issues": [], "total": 0}),
        ]
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        resp = _request_with_retry(
            client,
            "GET",
            "/rest/api/3/search",
            params={},
            sleep=lambda s: sleeps.append(s),
        )

    assert resp.status_code == 200
    assert len(sleeps) == 1


@respx.mock
def test_search_paginates_until_total_reached() -> None:
    page1 = {
        "issues": [{"key": "A-1"}, {"key": "A-2"}],
        "total": 3,
        "startAt": 0,
        "maxResults": 2,
    }
    page2 = {
        "issues": [{"key": "A-3"}],
        "total": 3,
        "startAt": 2,
        "maxResults": 2,
    }

    route = respx.get("https://example.atlassian.net/rest/api/3/search").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        keys = [i["key"] for i in search_candidate_issues(client, "x", page_size=2)]

    assert keys == ["A-1", "A-2", "A-3"]
    assert route.call_count == 2


@respx.mock
def test_search_stops_on_empty_page() -> None:
    respx.get("https://example.atlassian.net/rest/api/3/search").mock(
        return_value=httpx.Response(200, json={"issues": [], "total": 0})
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        keys = list(search_candidate_issues(client, "x"))

    assert keys == []
