from __future__ import annotations

from typing import Any

import pytest

from clockyfy_automation.clockify.dedupe import (
    AUTOMATION_DESCRIPTION_RE,
    is_automation_owned,
    partition_entries,
)

PROJECT = "proj-1"
TAG = "tag-1"


def _entry(
    *,
    description: str = "PROJ-123",
    project_id: str = PROJECT,
    tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": "id-x",
        "description": description,
        "projectId": project_id,
        "tagIds": tag_ids if tag_ids is not None else [TAG],
    }


@pytest.mark.parametrize(
    ("description", "match"),
    [
        ("PROJ-123", True),
        ("PROJ-123 — Fix the thing", True),
        ("ABC_X-99 — anything", True),
        ("A1-12", True),  # JIRA project keys may contain digits after the first letter
        ("1AB-12", False),  # must start with a letter
        ("proj-123", False),
        ("PROJ-123 - Fix the thing", False),  # ASCII hyphen, not em-dash
        ("Reunión semanal", False),
        ("", False),
        ("PROJ-", False),
    ],
)
def test_regex_matches(description: str, match: bool) -> None:
    assert bool(AUTOMATION_DESCRIPTION_RE.match(description)) is match


def test_owned_when_all_three_match() -> None:
    assert is_automation_owned(_entry(), PROJECT, TAG) is True


def test_not_owned_when_project_id_differs() -> None:
    assert is_automation_owned(_entry(project_id="other"), PROJECT, TAG) is False


def test_not_owned_when_tag_missing() -> None:
    assert is_automation_owned(_entry(tag_ids=["other"]), PROJECT, TAG) is False
    assert is_automation_owned(_entry(tag_ids=[]), PROJECT, TAG) is False


def test_owned_when_extra_tags_present() -> None:
    assert is_automation_owned(_entry(tag_ids=[TAG, "other"]), PROJECT, TAG) is True


def test_not_owned_when_description_does_not_match() -> None:
    assert is_automation_owned(_entry(description="meeting"), PROJECT, TAG) is False


def test_partition_entries_returns_disjoint_sets() -> None:
    a = _entry(description="PROJ-1 — a")
    b = _entry(description="meeting")
    c = _entry(description="PROJ-2", project_id="other")
    d = _entry(description="PROJ-3 — c")
    owned, untouched = partition_entries([a, b, c, d], PROJECT, TAG)
    assert owned == [a, d]
    assert untouched == [b, c]
    assert set(id(e) for e in owned).isdisjoint(set(id(e) for e in untouched))
