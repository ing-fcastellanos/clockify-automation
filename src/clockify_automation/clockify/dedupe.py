from __future__ import annotations

import re
from typing import Any

AUTOMATION_DESCRIPTION_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+( — .*)?$")


def is_automation_owned(
    entry: dict[str, Any],
    project_id: str,
    tag_id: str,
    description_re: re.Pattern[str] = AUTOMATION_DESCRIPTION_RE,
) -> bool:
    if entry.get("projectId") != project_id:
        return False
    tag_ids = entry.get("tagIds") or []
    if tag_id not in tag_ids:
        return False
    description = entry.get("description") or ""
    return bool(description_re.match(description))


def partition_entries(
    entries: list[dict[str, Any]],
    project_id: str,
    tag_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    owned: list[dict[str, Any]] = []
    untouched: list[dict[str, Any]] = []
    for entry in entries:
        if is_automation_owned(entry, project_id, tag_id):
            owned.append(entry)
        else:
            untouched.append(entry)
    return owned, untouched
