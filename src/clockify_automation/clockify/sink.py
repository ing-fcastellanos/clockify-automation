from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

from clockify_automation.allocator import Block
from clockify_automation.clockify.client import (
    create_time_entry,
    delete_time_entry,
    list_user_entries,
    make_clockify_client,
    resolve_user_id,
)
from clockify_automation.clockify.dedupe import partition_entries
from clockify_automation.config import Settings

Mode = Literal["error", "force", "skip", "dry_run"]

_MAX_DESCRIPTION_LEN = 500


@dataclass(frozen=True)
class SinkReport:
    created: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[dict[str, Any]] = field(default_factory=list)
    skipped_days: list[date] = field(default_factory=list)
    planned: list[dict[str, Any]] = field(default_factory=list)


class ConflictError(RuntimeError):
    pass


def format_description(ticket_key: str, summary: str | None) -> str:
    if not summary:
        return ticket_key
    full = f"{ticket_key} — {summary}"
    if len(full) <= _MAX_DESCRIPTION_LEN:
        return full
    prefix = f"{ticket_key} — "
    available = _MAX_DESCRIPTION_LEN - len(prefix) - 1
    truncated_summary = summary[:available].rstrip()
    return f"{prefix}{truncated_summary}…"


def to_utc_iso8601_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed; expected tz-aware")
    utc = dt.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def block_to_payload(block: Block, project_id: str, tag_id: str) -> dict[str, Any]:
    return {
        "start": to_utc_iso8601_z(block.start),
        "end": to_utc_iso8601_z(block.end),
        "description": format_description(block.ticket_key, block.summary),
        "projectId": project_id,
        "tagIds": [tag_id],
    }


def _entry_local_date(entry: dict[str, Any], tz_name: str) -> date | None:
    interval = entry.get("timeInterval") or {}
    start = interval.get("start")
    if not start:
        return None
    from zoneinfo import ZoneInfo

    parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo(tz_name)).date()


def apply_blocks(
    settings: Settings,
    blocks: list[Block],
    mode: Mode,
    *,
    from_date: date,
    to_date: date,
) -> SinkReport:
    range_start = datetime.combine(from_date, datetime.min.time(), tzinfo=settings.timezone)
    range_end = datetime.combine(
        to_date, datetime.max.time().replace(microsecond=0), tzinfo=settings.timezone
    )
    start_iso = to_utc_iso8601_z(range_start)
    end_iso = to_utc_iso8601_z(range_end)

    planned_payloads = [
        block_to_payload(b, settings.clockify_project_id, settings.clockify_tag_id)
        for b in blocks
    ]

    with make_clockify_client(settings.clockify_api_key) as client:
        user_id = settings.clockify_user_id or resolve_user_id(client)

        existing = list(
            list_user_entries(
                client,
                settings.clockify_workspace_id,
                user_id,
                start_iso,
                end_iso,
            )
        )
        owned, _ = partition_entries(
            existing, settings.clockify_project_id, settings.clockify_tag_id
        )

        if mode == "dry_run":
            return SinkReport(planned=planned_payloads, created=[], deleted=[], skipped_days=[])

        if mode == "error":
            if owned:
                raise ConflictError(
                    f"{len(owned)} automation-owned time entries already exist between "
                    f"{from_date.isoformat()} and {to_date.isoformat()}. "
                    f"Re-run with --force to replace them or --skip to leave their days alone."
                )
            return _create_all(client, settings, planned_payloads)

        if mode == "force":
            for entry in owned:
                delete_time_entry(client, settings.clockify_workspace_id, entry["id"])
            report = _create_all(client, settings, planned_payloads)
            return SinkReport(
                created=report.created,
                deleted=owned,
                skipped_days=[],
                planned=planned_payloads,
            )

        if mode == "skip":
            owned_days = {
                d for entry in owned if (d := _entry_local_date(entry, settings.timezone_name))
            }
            filtered_payloads = [
                payload
                for payload, block in zip(planned_payloads, blocks, strict=True)
                if block.start.date() not in owned_days
            ]
            report = _create_all(client, settings, filtered_payloads)
            return SinkReport(
                created=report.created,
                deleted=[],
                skipped_days=sorted(owned_days),
                planned=planned_payloads,
            )

        raise ValueError(f"unknown mode: {mode!r}")


def _create_all(
    client: Any, settings: Settings, payloads: list[dict[str, Any]]
) -> SinkReport:
    created: list[dict[str, Any]] = []
    for payload in payloads:
        result = create_time_entry(client, settings.clockify_workspace_id, payload)
        created.append(result)
    return SinkReport(created=created, deleted=[], skipped_days=[], planned=payloads)
