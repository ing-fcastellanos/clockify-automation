from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

import httpx

from clockify_automation.config import Settings
from clockify_automation.jira.client import (
    _request_with_retry,
    fetch_issue,
    make_jira_client,
    search_candidate_issues,
)
from clockify_automation.jira.timeline import (
    intervals_to_active_days,
    reconstruct_intervals,
)


@dataclass(frozen=True)
class Ticket:
    key: str
    summary: str | None


def _build_jql(from_date: date, to_date: date) -> str:
    return (
        'assignee was currentUser() AND status was "In Progress" '
        f'DURING ("{from_date.isoformat()}", "{to_date.isoformat()}")'
    )


def _resolve_account_id(client: httpx.Client) -> str:
    response = _request_with_retry(client, "GET", "/rest/api/3/myself")
    response.raise_for_status()
    data = response.json()
    return cast(str, data["accountId"])


def fetch_active_tickets_by_day(
    settings: Settings,
    from_date: date,
    to_date: date,
    *,
    now: datetime | None = None,
) -> dict[date, list[Ticket]]:
    if now is None:
        now = datetime.now(tz=settings.timezone)

    with make_jira_client(
        settings.jira_base_url, settings.jira_email, settings.jira_api_token
    ) as client:
        account_id = _resolve_account_id(client)
        jql = _build_jql(from_date, to_date)
        per_day: dict[date, list[Ticket]] = defaultdict(list)
        seen_per_day: dict[date, set[str]] = defaultdict(set)
        for issue_stub in search_candidate_issues(client, jql, fields=["summary"]):
            full_issue = fetch_issue(client, issue_stub["key"])
            ticket = _ticket_from_issue(full_issue)
            intervals = reconstruct_intervals(full_issue, account_id, now)
            active_days = intervals_to_active_days(intervals, settings.timezone)
            for d in active_days:
                if d < from_date or d > to_date:
                    continue
                if ticket.key in seen_per_day[d]:
                    continue
                seen_per_day[d].add(ticket.key)
                per_day[d].append(ticket)

    return {d: sorted(tickets, key=lambda t: t.key) for d, tickets in per_day.items()}


def _ticket_from_issue(issue: dict[str, Any]) -> Ticket:
    fields = issue.get("fields", {}) or {}
    summary = fields.get("summary")
    return Ticket(key=issue["key"], summary=summary)
