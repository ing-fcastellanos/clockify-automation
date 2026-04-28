from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from clockify_automation.jira.timeline import (
    Interval,
    intervals_to_active_days,
    reconstruct_intervals,
)

USER = "user-123"
OTHER = "user-999"
NOW = datetime.fromisoformat("2026-04-30T12:00:00+00:00")


def _ts(s: str) -> str:
    # Helper so tests can keep timestamps in plain ISO with offset.
    return s


def _issue(
    *,
    created: str,
    current_assignee: str | None,
    current_status: str,
    histories: list[dict],
    summary: str | None = "x",
) -> dict:
    return {
        "key": "TEST-1",
        "fields": {
            "summary": summary,
            "created": created,
            "assignee": {"accountId": current_assignee} if current_assignee else None,
            "status": {"name": current_status},
        },
        "changelog": {"histories": histories},
    }


def _history(ts: str, items: list[dict]) -> dict:
    return {"created": ts, "items": items}


def _assignee_change(from_: str | None, to: str | None) -> dict:
    return {"field": "assignee", "from": from_, "to": to}


def _status_change(from_: str, to: str) -> dict:
    return {"field": "status", "fromString": from_, "toString": to}


def test_single_continuous_interval_user_already_assigned() -> None:
    issue = _issue(
        created="2026-04-20T08:00:00+00:00",
        current_assignee=USER,
        current_status="In Progress",
        histories=[
            _history(
                "2026-04-20T10:00:00+00:00",
                [_status_change("To Do", "In Progress")],
            )
        ],
    )
    intervals = reconstruct_intervals(issue, USER, NOW)
    assert intervals == [
        Interval(
            datetime.fromisoformat("2026-04-20T10:00:00+00:00"),
            NOW,
        )
    ]


def test_two_disjoint_intervals_in_progress_done_in_progress() -> None:
    issue = _issue(
        created="2026-04-20T08:00:00+00:00",
        current_assignee=USER,
        current_status="In Progress",
        histories=[
            _history(
                "2026-04-20T10:00:00+00:00",
                [_status_change("To Do", "In Progress")],
            ),
            _history(
                "2026-04-21T15:00:00+00:00",
                [_status_change("In Progress", "Done")],
            ),
            _history(
                "2026-04-22T09:00:00+00:00",
                [_status_change("Done", "In Progress")],
            ),
        ],
    )
    intervals = reconstruct_intervals(issue, USER, NOW)
    assert len(intervals) == 2
    assert intervals[0] == Interval(
        datetime.fromisoformat("2026-04-20T10:00:00+00:00"),
        datetime.fromisoformat("2026-04-21T15:00:00+00:00"),
    )
    assert intervals[1] == Interval(
        datetime.fromisoformat("2026-04-22T09:00:00+00:00"),
        NOW,
    )


def test_reassignment_in_middle_emits_two_intervals() -> None:
    issue = _issue(
        created="2026-04-20T08:00:00+00:00",
        current_assignee=USER,
        current_status="In Progress",
        histories=[
            _history(
                "2026-04-20T10:00:00+00:00",
                [_status_change("To Do", "In Progress")],
            ),
            _history(
                "2026-04-21T12:00:00+00:00",
                [_assignee_change(USER, OTHER)],
            ),
            _history(
                "2026-04-22T08:00:00+00:00",
                [_assignee_change(OTHER, USER)],
            ),
        ],
    )
    intervals = reconstruct_intervals(issue, USER, NOW)
    assert len(intervals) == 2
    assert intervals[0] == Interval(
        datetime.fromisoformat("2026-04-20T10:00:00+00:00"),
        datetime.fromisoformat("2026-04-21T12:00:00+00:00"),
    )
    assert intervals[1] == Interval(
        datetime.fromisoformat("2026-04-22T08:00:00+00:00"),
        NOW,
    )


def test_never_assigned_to_user_emits_zero_intervals() -> None:
    issue = _issue(
        created="2026-04-20T08:00:00+00:00",
        current_assignee=OTHER,
        current_status="In Progress",
        histories=[
            _history(
                "2026-04-20T10:00:00+00:00",
                [_status_change("To Do", "In Progress")],
            ),
        ],
    )
    intervals = reconstruct_intervals(issue, USER, NOW)
    assert intervals == []


def test_simultaneous_assign_and_status_in_one_history_entry() -> None:
    # Issue created with no assignee and status To Do; then in one event the user
    # gets assigned AND status moves to In Progress. Both items in same history.
    issue = _issue(
        created="2026-04-20T08:00:00+00:00",
        current_assignee=USER,
        current_status="In Progress",
        histories=[
            _history(
                "2026-04-20T10:00:00+00:00",
                [
                    _assignee_change(None, USER),
                    _status_change("To Do", "In Progress"),
                ],
            ),
        ],
    )
    intervals = reconstruct_intervals(issue, USER, NOW)
    assert intervals == [
        Interval(
            datetime.fromisoformat("2026-04-20T10:00:00+00:00"),
            NOW,
        )
    ]


def test_open_interval_uses_now_as_end() -> None:
    issue = _issue(
        created="2026-04-20T08:00:00+00:00",
        current_assignee=USER,
        current_status="In Progress",
        histories=[
            _history(
                "2026-04-25T10:00:00+00:00",
                [_status_change("To Do", "In Progress")],
            ),
        ],
    )
    intervals = reconstruct_intervals(issue, USER, NOW)
    assert intervals[-1].end == NOW


def test_intervals_to_active_days_single_day() -> None:
    tz = ZoneInfo("America/Mexico_City")
    iv = Interval(
        datetime.fromisoformat("2026-04-20T15:00:00+00:00"),  # 09:00 local
        datetime.fromisoformat("2026-04-20T23:00:00+00:00"),  # 17:00 local
    )
    days = intervals_to_active_days([iv], tz)
    assert days == {date(2026, 4, 20)}


def test_intervals_to_active_days_crossing_midnight_local() -> None:
    tz = ZoneInfo("America/Mexico_City")
    # Mexico City is UTC-6. Start 22:00 local Mon = 04:00 UTC Tue.
    # End 02:00 local Tue = 08:00 UTC Tue.
    iv = Interval(
        datetime.fromisoformat("2026-04-21T04:00:00+00:00"),
        datetime.fromisoformat("2026-04-21T08:00:00+00:00"),
    )
    days = intervals_to_active_days([iv], tz)
    assert days == {date(2026, 4, 20), date(2026, 4, 21)}


def test_intervals_to_active_days_spans_multiple_full_days() -> None:
    tz = ZoneInfo("America/Mexico_City")
    iv = Interval(
        # 2026-04-20 10:00 local = 16:00 UTC
        datetime.fromisoformat("2026-04-20T16:00:00+00:00"),
        # 2026-04-24 14:00 local = 20:00 UTC
        datetime.fromisoformat("2026-04-24T20:00:00+00:00"),
    )
    days = intervals_to_active_days([iv], tz)
    assert days == {
        date(2026, 4, 20),
        date(2026, 4, 21),
        date(2026, 4, 22),
        date(2026, 4, 23),
        date(2026, 4, 24),
    }


def test_intervals_to_active_days_just_before_midnight_local() -> None:
    tz = ZoneInfo("America/Mexico_City")
    # 23:59 local Monday = 05:59 UTC Tuesday
    # 23:59:30 local Monday = 05:59:30 UTC Tuesday
    iv = Interval(
        datetime.fromisoformat("2026-04-21T05:00:00+00:00"),
        datetime.fromisoformat("2026-04-21T05:59:00+00:00"),
    )
    days = intervals_to_active_days([iv], tz)
    assert days == {date(2026, 4, 20)}
