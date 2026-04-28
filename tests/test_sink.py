from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from clockify_automation.allocator import Block
from clockify_automation.clockify.sink import (
    ConflictError,
    apply_blocks,
    block_to_payload,
    format_description,
    to_utc_iso8601_z,
)

TZ = ZoneInfo("America/Mexico_City")
WORKSPACE = "ws-1"
PROJECT = "proj-1"
TAG = "tag-1"
USER = "user-1"


# ---------------------------------------------------------------------------
# Pure helpers (tasks 5.7, 5.8)
# ---------------------------------------------------------------------------


def test_format_description_with_summary() -> None:
    assert format_description("PROJ-123", "Fix login bug") == "PROJ-123 — Fix login bug"


def test_format_description_no_summary() -> None:
    assert format_description("PROJ-123", None) == "PROJ-123"
    assert format_description("PROJ-123", "") == "PROJ-123"


def test_format_description_truncates_long_summary() -> None:
    long_summary = "x" * 1000
    out = format_description("PROJ-1", long_summary)
    assert out.startswith("PROJ-1 — ")
    assert out.endswith("…")
    assert len(out) <= 500


def test_to_utc_iso8601_z_converts_local_to_utc() -> None:
    local = datetime(2026, 4, 21, 9, 0, tzinfo=TZ)
    assert to_utc_iso8601_z(local) == "2026-04-21T15:00:00Z"


def test_to_utc_iso8601_z_rejects_naive() -> None:
    with pytest.raises(ValueError):
        to_utc_iso8601_z(datetime(2026, 4, 21, 9, 0))


def test_block_to_payload_shape() -> None:
    block = Block(
        ticket_key="PROJ-1",
        summary="Do the thing",
        start=datetime(2026, 4, 21, 9, 0, tzinfo=TZ),
        end=datetime(2026, 4, 21, 11, 0, tzinfo=TZ),
    )
    payload = block_to_payload(block, PROJECT, TAG)
    assert payload == {
        "start": "2026-04-21T15:00:00Z",
        "end": "2026-04-21T17:00:00Z",
        "description": "PROJ-1 — Do the thing",
        "projectId": PROJECT,
        "tagIds": [TAG],
    }


# ---------------------------------------------------------------------------
# apply_blocks integration (task 5.10) using respx
# ---------------------------------------------------------------------------


def _settings() -> Any:
    """Build a Settings-like stub. Avoids requiring full env."""
    from types import SimpleNamespace

    s = SimpleNamespace(
        clockify_api_key="ck",
        clockify_workspace_id=WORKSPACE,
        clockify_project_id=PROJECT,
        clockify_tag_id=TAG,
        clockify_user_id=USER,
        timezone_name="America/Mexico_City",
        timezone=TZ,
    )
    return s


def _block(key: str, day: date, start_h: int, end_h: int, summary: str = "x") -> Block:
    return Block(
        ticket_key=key,
        summary=summary,
        start=datetime.combine(day, datetime.min.time().replace(hour=start_h), tzinfo=TZ),
        end=datetime.combine(day, datetime.min.time().replace(hour=end_h), tzinfo=TZ),
    )


def _existing_owned_entry(entry_id: str, day: date, description: str = "PROJ-9 — old") -> dict:
    start_local = datetime.combine(day, datetime.min.time().replace(hour=9), tzinfo=TZ)
    end_local = datetime.combine(day, datetime.min.time().replace(hour=17), tzinfo=TZ)

    return {
        "id": entry_id,
        "description": description,
        "projectId": PROJECT,
        "tagIds": [TAG],
        "timeInterval": {
            "start": start_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }


def _existing_manual_entry(entry_id: str, day: date) -> dict:
    start_local = datetime.combine(day, datetime.min.time().replace(hour=14), tzinfo=TZ)
    end_local = datetime.combine(day, datetime.min.time().replace(hour=15), tzinfo=TZ)

    return {
        "id": entry_id,
        "description": "Reunión semanal",
        "projectId": PROJECT,
        "tagIds": [TAG],
        "timeInterval": {
            "start": start_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }


def _list_route() -> str:
    return f"https://api.clockify.me/api/v1/workspaces/{WORKSPACE}/user/{USER}/time-entries"


def _create_route() -> str:
    return f"https://api.clockify.me/api/v1/workspaces/{WORKSPACE}/time-entries"


def _delete_route(entry_id: str) -> str:
    return f"https://api.clockify.me/api/v1/workspaces/{WORKSPACE}/time-entries/{entry_id}"


@respx.mock
def test_dry_run_makes_no_writes() -> None:
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[]))
    create_mock = respx.post(_create_route()).mock(return_value=httpx.Response(201))
    delete_mock = respx.delete(url__regex=r".*time-entries/.*").mock(
        return_value=httpx.Response(204)
    )

    blocks = [_block("PROJ-1", date(2026, 4, 21), 9, 17)]
    report = apply_blocks(
        _settings(),
        blocks,
        "dry_run",
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
    )
    assert create_mock.call_count == 0
    assert delete_mock.call_count == 0
    assert len(report.planned) == 1
    assert report.created == []


@respx.mock
def test_error_mode_aborts_on_conflict() -> None:
    existing = [_existing_owned_entry("e1", date(2026, 4, 21))]
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=existing))
    create_mock = respx.post(_create_route()).mock(return_value=httpx.Response(201))

    blocks = [_block("PROJ-1", date(2026, 4, 21), 9, 17)]
    with pytest.raises(ConflictError, match="already exist"):
        apply_blocks(
            _settings(),
            blocks,
            "error",
            from_date=date(2026, 4, 21),
            to_date=date(2026, 4, 21),
        )
    assert create_mock.call_count == 0


@respx.mock
def test_error_mode_proceeds_when_no_conflict() -> None:
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[]))
    create_mock = respx.post(_create_route()).mock(
        return_value=httpx.Response(201, json={"id": "new-1"})
    )

    blocks = [_block("PROJ-1", date(2026, 4, 21), 9, 17)]
    report = apply_blocks(
        _settings(),
        blocks,
        "error",
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
    )
    assert create_mock.call_count == 1
    assert len(report.created) == 1


@respx.mock
def test_force_mode_deletes_owned_then_creates_and_preserves_manual() -> None:
    owned = _existing_owned_entry("e1", date(2026, 4, 21))
    manual = _existing_manual_entry("e2", date(2026, 4, 21))

    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[owned, manual]))
    create_mock = respx.post(_create_route()).mock(
        return_value=httpx.Response(201, json={"id": "new-1"})
    )
    delete_owned = respx.delete(_delete_route("e1")).mock(return_value=httpx.Response(204))
    delete_manual = respx.delete(_delete_route("e2")).mock(return_value=httpx.Response(204))

    blocks = [_block("PROJ-1", date(2026, 4, 21), 9, 17)]
    report = apply_blocks(
        _settings(),
        blocks,
        "force",
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
    )
    assert delete_owned.call_count == 1
    assert delete_manual.call_count == 0
    assert create_mock.call_count == 1
    assert len(report.deleted) == 1
    assert report.deleted[0]["id"] == "e1"


@respx.mock
def test_skip_mode_skips_conflicting_days_and_processes_others() -> None:
    owned = _existing_owned_entry("e1", date(2026, 4, 21))  # only Tuesday
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[owned]))
    create_mock = respx.post(_create_route()).mock(
        return_value=httpx.Response(201, json={"id": "new"})
    )

    blocks = [
        _block("PROJ-A", date(2026, 4, 20), 9, 17),  # Mon (no conflict)
        _block("PROJ-B", date(2026, 4, 21), 9, 17),  # Tue (conflicts)
        _block("PROJ-C", date(2026, 4, 22), 9, 17),  # Wed (no conflict)
    ]
    report = apply_blocks(
        _settings(),
        blocks,
        "skip",
        from_date=date(2026, 4, 20),
        to_date=date(2026, 4, 22),
    )
    assert create_mock.call_count == 2
    assert report.skipped_days == [date(2026, 4, 21)]


@respx.mock
def test_create_payload_has_correct_utc_and_required_fields() -> None:
    respx.get(_list_route()).mock(return_value=httpx.Response(200, json=[]))
    create_mock = respx.post(_create_route()).mock(
        return_value=httpx.Response(201, json={"id": "new"})
    )

    blocks = [_block("PROJ-1", date(2026, 4, 21), 9, 11, summary="Fix it")]
    apply_blocks(
        _settings(),
        blocks,
        "error",
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
    )
    sent = create_mock.calls.last.request
    import json as _json

    body = _json.loads(sent.content)
    assert body == {
        "start": "2026-04-21T15:00:00Z",
        "end": "2026-04-21T17:00:00Z",
        "description": "PROJ-1 — Fix it",
        "projectId": PROJECT,
        "tagIds": [TAG],
    }
