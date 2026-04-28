from __future__ import annotations

import httpx
import respx

from clockyfy_automation.jira.client import (
    _request_with_retry,
    fetch_issue,
    make_jira_client,
    search_candidate_issues,
)

SEARCH_URL = "https://example.atlassian.net/rest/api/3/search/jql"
ISSUE_URL_RE = r"https://example\.atlassian\.net/rest/api/3/issue/[A-Z]+-\d+"


@respx.mock
def test_retry_after_429_then_succeeds() -> None:
    sleeps: list[float] = []

    route = respx.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"issues": [], "isLast": True}),
        ]
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        resp = _request_with_retry(
            client,
            "GET",
            "/rest/api/3/search/jql",
            params={"jql": "x"},
            sleep=lambda s: sleeps.append(s),
        )

    assert resp.status_code == 200
    assert route.call_count == 2
    assert sleeps == [0.0]


@respx.mock
def test_retry_500_then_succeeds() -> None:
    sleeps: list[float] = []

    respx.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"issues": [], "isLast": True}),
        ]
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        resp = _request_with_retry(
            client,
            "GET",
            "/rest/api/3/search/jql",
            params={},
            sleep=lambda s: sleeps.append(s),
        )

    assert resp.status_code == 200
    assert len(sleeps) == 1


@respx.mock
def test_search_paginates_with_next_page_token() -> None:
    page1 = {
        "issues": [{"key": "A-1"}, {"key": "A-2"}],
        "nextPageToken": "tok-2",
        "isLast": False,
    }
    page2 = {
        "issues": [{"key": "A-3"}],
        "isLast": True,
    }

    route = respx.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        keys = [i["key"] for i in search_candidate_issues(client, "x", page_size=2)]

    assert keys == ["A-1", "A-2", "A-3"]
    assert route.call_count == 2
    second_request = route.calls[1].request
    assert "nextPageToken=tok-2" in str(second_request.url)


@respx.mock
def test_search_stops_when_is_last_true() -> None:
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"issues": [], "isLast": True})
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        keys = list(search_candidate_issues(client, "x"))

    assert keys == []


@respx.mock
def test_fetch_issue_requests_changelog_expand() -> None:
    route = respx.get(url__regex=ISSUE_URL_RE).mock(
        return_value=httpx.Response(
            200,
            json={
                "key": "PROJ-1",
                "fields": {"summary": "x", "created": "2026-04-20T08:00:00.000+0000"},
                "changelog": {"histories": []},
            },
        )
    )

    with make_jira_client("https://example.atlassian.net", "u@e.com", "t") as client:
        issue = fetch_issue(client, "PROJ-1")

    assert issue["key"] == "PROJ-1"
    assert "changelog" in issue
    request_url = str(route.calls.last.request.url)
    assert "expand=changelog" in request_url
    assert "fields=" in request_url
