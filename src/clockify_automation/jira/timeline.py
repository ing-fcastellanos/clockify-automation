from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IN_PROGRESS_STATUS = "In Progress"


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


def _parse_jira_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _initial_value(
    histories: list[dict[str, Any]],
    field: str,
    current_value: str | None,
    value_attr: str,
) -> str | None:
    for h in histories:
        for item in h.get("items", []):
            if item.get("field") == field:
                value = item.get(value_attr)
                return value if value is None else str(value)
    return current_value


def reconstruct_intervals(
    issue: dict[str, Any],
    user_account_id: str,
    now: datetime,
    in_progress_status: str = IN_PROGRESS_STATUS,
) -> list[Interval]:
    fields = issue.get("fields", {}) or {}
    changelog = issue.get("changelog", {}) or {}
    histories = sorted(
        list(changelog.get("histories", []) or []),
        key=lambda h: _parse_jira_ts(h["created"]),
    )

    current_assignee = ((fields.get("assignee") or {}) or {}).get("accountId")
    current_status = ((fields.get("status") or {}) or {}).get("name")

    state_assignee = _initial_value(histories, "assignee", current_assignee, "from")
    state_status = _initial_value(histories, "status", current_status, "fromString")

    issue_created_raw = fields.get("created")
    issue_created_ts = _parse_jira_ts(issue_created_raw) if issue_created_raw else None

    intervals: list[Interval] = []
    interval_start: datetime | None = None

    def is_active() -> bool:
        return state_assignee == user_account_id and state_status == in_progress_status

    if is_active() and issue_created_ts is not None:
        interval_start = issue_created_ts

    for history in histories:
        ts = _parse_jira_ts(history["created"])
        was_active = is_active()
        for item in history.get("items", []):
            field = item.get("field")
            if field == "assignee":
                state_assignee = item.get("to")
            elif field == "status":
                state_status = item.get("toString")
        now_active = is_active()
        if was_active and not now_active:
            assert interval_start is not None
            intervals.append(Interval(start=interval_start, end=ts))
            interval_start = None
        elif not was_active and now_active:
            interval_start = ts

    if is_active() and interval_start is not None:
        intervals.append(Interval(start=interval_start, end=now))

    return intervals


def intervals_to_active_days(intervals: list[Interval], tz: ZoneInfo) -> set[date]:
    days: set[date] = set()
    one_day = timedelta(days=1)
    for iv in intervals:
        start_local = iv.start.astimezone(tz)
        end_local = iv.end.astimezone(tz)
        d = start_local.date()
        last = end_local.date()
        while d <= last:
            days.add(d)
            d = d + one_day
    return days
