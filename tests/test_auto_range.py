from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from clockify_automation.auto_range import (
    LOOKBACK_DAYS,
    MAX_RANGE_DAYS,
    NoRecentEntriesError,
    find_last_entry_date,
    resolve_automatic_range,
)

TZ = ZoneInfo("America/Mexico_City")
WORKSPACE = "ws-1"
PROJECT = "proj-1"
TAG = "tag-1"
USER = "user-1"


def _settings() -> Any:
    return SimpleNamespace(
        clockify_api_key="ck",
        clockify_workspace_id=WORKSPACE,
        clockify_project_id=PROJECT,
        clockify_tag_id=TAG,
        clockify_user_id=USER,
        timezone_name="America/Mexico_City",
        timezone=TZ,
    )


def _list_route() -> str:
    return f"https://api.clockify.me/api/v1/workspaces/{WORKSPACE}/user/{USER}/time-entries"


def _entry(
    entry_id: str,
    day: date,
    *,
    hour: int = 9,
    project_id: str = PROJECT,
    tag_ids: list[str] | None = None,
    description: str = "PROJ-1 — work",
) -> dict[str, Any]:
    start_local = datetime.combine(day, datetime.min.time().replace(hour=hour), tzinfo=TZ)
    return {
        "id": entry_id,
        "description": description,
        "projectId": project_id,
        "tagIds": [TAG] if tag_ids is None else tag_ids,
        "timeInterval": {
            "start": start_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (start_local.astimezone(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }


# ---------------------------------------------------------------------------
# find_last_entry_date
# ---------------------------------------------------------------------------


@respx.mock
def test_finds_latest_day_among_entries() -> None:
    entries = [
        _entry("e1", date(2026, 8, 24)),
        _entry("e3", date(2026, 8, 27)),
        _entry("e2", date(2026, 8, 25)),
    ]
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=entries))

    assert find_last_entry_date(_settings(), date(2026, 8, 31)) == date(2026, 8, 27)


@respx.mock
def test_entry_in_another_project_counts_as_covered() -> None:
    entries = [
        _entry("e1", date(2026, 8, 27)),
        _entry(
            "e2",
            date(2026, 8, 29),
            project_id="some-other-project",
            tag_ids=[],
            description="Daily standup",
        ),
    ]
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=entries))

    assert find_last_entry_date(_settings(), date(2026, 8, 31)) == date(2026, 8, 29)


@respx.mock
def test_entry_day_uses_configured_timezone() -> None:
    # 2026-08-28T03:00:00Z is 2026-08-27 21:00 in America/Mexico_City.
    entry = {
        "id": "e1",
        "description": "PROJ-1",
        "projectId": PROJECT,
        "tagIds": [TAG],
        "timeInterval": {"start": "2026-08-28T03:00:00Z", "end": "2026-08-28T04:00:00Z"},
    }
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[entry]))

    assert find_last_entry_date(_settings(), date(2026, 8, 31)) == date(2026, 8, 27)


@respx.mock
def test_entry_without_start_is_ignored() -> None:
    entries = [
        _entry("e1", date(2026, 8, 27)),
        {"id": "e2", "description": "x", "projectId": PROJECT, "tagIds": [TAG], "timeInterval": {}},
    ]
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=entries))

    assert find_last_entry_date(_settings(), date(2026, 8, 31)) == date(2026, 8, 27)


@respx.mock
def test_lookback_window_spans_lookback_days_back_to_today() -> None:
    route = respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[]))

    find_last_entry_date(_settings(), date(2026, 8, 31))

    params = route.calls.last.request.url.params
    # 21-day window ending today: 2026-08-11 .. 2026-08-31, 00:00 local = 06:00Z.
    assert params["start"] == "2026-08-11T06:00:00Z"
    assert params["end"] == "2026-09-01T05:59:59Z"


@respx.mock
def test_no_entries_returns_none() -> None:
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[]))

    assert find_last_entry_date(_settings(), date(2026, 8, 31)) is None


# ---------------------------------------------------------------------------
# resolve_automatic_range
# ---------------------------------------------------------------------------


@respx.mock
def test_range_starts_the_day_after_the_last_entry() -> None:
    respx.get(_list_route()).mock(
        return_value=httpx.Response(200, json=[_entry("e1", date(2026, 8, 27))])
    )

    result = resolve_automatic_range(_settings(), date(2026, 8, 31))

    assert result is not None
    assert result.last_entry_date == date(2026, 8, 27)
    assert result.from_date == date(2026, 8, 28)
    assert result.to_date == date(2026, 8, 31)


@respx.mock
def test_oldest_resolvable_entry_yields_exactly_the_max_range() -> None:
    """The oldest day the window can surface must not exceed the 20-day cap."""
    today = date(2026, 8, 31)
    oldest = today - timedelta(days=LOOKBACK_DAYS - 1)
    assert oldest == date(2026, 8, 11)
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[_entry("e1", oldest)]))

    result = resolve_automatic_range(_settings(), today)

    assert result is not None
    assert result.from_date == date(2026, 8, 12)
    assert result.to_date == today
    assert (result.to_date - result.from_date).days + 1 == MAX_RANGE_DAYS


@respx.mock
def test_already_up_to_date_returns_none() -> None:
    respx.get(_list_route()).mock(
        return_value=httpx.Response(200, json=[_entry("e1", date(2026, 8, 31))])
    )

    assert resolve_automatic_range(_settings(), date(2026, 8, 31)) is None


@respx.mock
def test_entry_in_the_future_returns_none() -> None:
    respx.get(_list_route()).mock(
        return_value=httpx.Response(200, json=[_entry("e1", date(2026, 9, 2))])
    )

    assert resolve_automatic_range(_settings(), date(2026, 8, 31)) is None


@respx.mock
def test_empty_window_raises_and_mentions_from_flag() -> None:
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(NoRecentEntriesError) as exc:
        resolve_automatic_range(_settings(), date(2026, 8, 31))

    message = str(exc.value)
    assert f"last {LOOKBACK_DAYS} days" in message
    assert "--from" in message


@respx.mock
def test_user_id_is_resolved_when_not_configured() -> None:
    settings = _settings()
    settings.clockify_user_id = None
    me = respx.get("https://api.clockify.me/api/v1/user").mock(
        return_value=httpx.Response(200, json={"id": USER})
    )
    respx.get(_list_route()).mock(
        return_value=httpx.Response(200, json=[_entry("e1", date(2026, 8, 27))])
    )

    result = resolve_automatic_range(settings, date(2026, 8, 31))

    assert me.call_count == 1
    assert result is not None and result.from_date == date(2026, 8, 28)
