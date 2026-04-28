from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from clockyfy_automation.allocator import (
    AllocationResult,
    Ticket,
    _allocations_for_n,
    allocate,
    allocate_day,
    working_days,
)

TZ = ZoneInfo("America/Mexico_City")


def _ticks(*keys: str) -> list[Ticket]:
    return [Ticket(key=k, summary=f"summary-of-{k}") for k in keys]


# ---------------------------------------------------------------------------
# working_days
# ---------------------------------------------------------------------------


def test_working_days_skips_weekends() -> None:
    days = working_days(date(2026, 4, 24), date(2026, 4, 27))  # Fri-Mon
    assert days == [date(2026, 4, 24), date(2026, 4, 27)]


def test_working_days_skips_holidays() -> None:
    holidays = {date(2026, 5, 1)}  # Friday
    days = working_days(date(2026, 4, 30), date(2026, 5, 4), holidays)  # Thu-Mon
    assert days == [date(2026, 4, 30), date(2026, 5, 4)]


def test_working_days_inclusive_range_full_week() -> None:
    days = working_days(date(2026, 4, 20), date(2026, 4, 26))  # Mon-Sun
    assert days == [
        date(2026, 4, 20),
        date(2026, 4, 21),
        date(2026, 4, 22),
        date(2026, 4, 23),
        date(2026, 4, 24),
    ]


def test_working_days_full_week_of_holidays_returns_empty() -> None:
    holidays = {
        date(2026, 4, 20),
        date(2026, 4, 21),
        date(2026, 4, 22),
        date(2026, 4, 23),
        date(2026, 4, 24),
    }
    assert working_days(date(2026, 4, 20), date(2026, 4, 26), holidays) == []


def test_working_days_inverted_range_empty() -> None:
    assert working_days(date(2026, 4, 30), date(2026, 4, 20)) == []


# ---------------------------------------------------------------------------
# _allocations_for_n
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, [8]),
        (2, [4, 4]),
        (3, [3, 3, 2]),
        (4, [2, 2, 2, 2]),
        (5, [2, 2, 2, 1, 1]),
        (6, [2, 2, 1, 1, 1, 1]),
        (7, [2, 1, 1, 1, 1, 1, 1]),
        (8, [1, 1, 1, 1, 1, 1, 1, 1]),
        (9, [1, 1, 1, 1, 1, 1, 1, 1]),
        (10, [1, 1, 1, 1, 1, 1, 1, 1]),
    ],
)
def test_allocations_for_n(n: int, expected: list[int]) -> None:
    assert _allocations_for_n(n) == expected
    if n <= 8:
        assert sum(expected) == 8


# ---------------------------------------------------------------------------
# allocate_day
# ---------------------------------------------------------------------------


def test_allocate_day_n4_equal_blocks() -> None:
    day = date(2026, 4, 21)
    blocks, skipped = allocate_day(_ticks("A-1", "A-2", "B-1", "C-1"), day, TZ)
    assert skipped == []
    assert [b.ticket_key for b in blocks] == ["A-1", "A-2", "B-1", "C-1"]
    expected_starts = [9, 11, 13, 15]
    expected_ends = [11, 13, 15, 17]
    for b, sh, eh in zip(blocks, expected_starts, expected_ends, strict=True):
        assert b.start == datetime(2026, 4, 21, sh, 0, tzinfo=TZ)
        assert b.end == datetime(2026, 4, 21, eh, 0, tzinfo=TZ)
    assert sum((b.end - b.start).total_seconds() for b in blocks) == 8 * 3600


def test_allocate_day_n3_gives_3_3_2() -> None:
    day = date(2026, 4, 21)
    blocks, skipped = allocate_day(_ticks("A-1", "B-1", "C-1"), day, TZ)
    assert skipped == []
    durations = [int((b.end - b.start).total_seconds() // 3600) for b in blocks]
    assert durations == [3, 3, 2]
    # Contiguous and ends at 17:00
    for b1, b2 in pairwise(blocks):
        assert b1.end == b2.start
    assert blocks[0].start.time().isoformat() == "09:00:00"
    assert blocks[-1].end.time().isoformat() == "17:00:00"


def test_allocate_day_n7_gives_first_2h_then_ones() -> None:
    day = date(2026, 4, 21)
    blocks, skipped = allocate_day(
        _ticks("A-1", "B-1", "C-1", "D-1", "E-1", "F-1", "G-1"), day, TZ
    )
    assert skipped == []
    durations = [int((b.end - b.start).total_seconds() // 3600) for b in blocks]
    assert durations == [2, 1, 1, 1, 1, 1, 1]


def test_allocate_day_unsorted_input_alphabetized_in_output() -> None:
    day = date(2026, 4, 21)
    blocks, _ = allocate_day(_ticks("C-1", "A-1", "B-1"), day, TZ)
    assert [b.ticket_key for b in blocks] == ["A-1", "B-1", "C-1"]


def test_allocate_day_n8_one_hour_each() -> None:
    day = date(2026, 4, 21)
    blocks, skipped = allocate_day(
        _ticks(*[f"K-{i}" for i in range(1, 9)]), day, TZ
    )
    assert skipped == []
    assert all((b.end - b.start) == timedelta(hours=1) for b in blocks)
    assert blocks[-1].end.time().isoformat() == "17:00:00"


def test_allocate_day_n10_skips_last_two_alphabetically() -> None:
    day = date(2026, 4, 21)
    keys = [f"K-{i:02d}" for i in range(1, 11)]
    blocks, skipped = allocate_day(_ticks(*keys), day, TZ)
    assert [b.ticket_key for b in blocks] == keys[:8]
    assert skipped == keys[8:]
    assert sum((b.end - b.start).total_seconds() for b in blocks) == 8 * 3600


def test_allocate_day_empty_returns_empty() -> None:
    assert allocate_day([], date(2026, 4, 21), TZ) == ([], [])


def test_allocate_day_blocks_are_tz_aware() -> None:
    blocks, _ = allocate_day(_ticks("A-1"), date(2026, 4, 21), TZ)
    assert blocks[0].start.tzinfo is not None
    assert blocks[0].end.tzinfo is not None
    assert str(blocks[0].start.tzinfo) == "America/Mexico_City"


# ---------------------------------------------------------------------------
# allocate (full)
# ---------------------------------------------------------------------------


def test_allocate_skips_weekends_and_holidays() -> None:
    holidays = {date(2026, 5, 1)}
    day_to_tickets = {
        date(2026, 4, 24): _ticks("A-1"),  # Fri
        date(2026, 5, 1): _ticks("A-1"),  # Fri holiday
        date(2026, 5, 4): _ticks("A-1"),  # Mon
    }
    result = allocate(date(2026, 4, 24), date(2026, 5, 4), holidays, day_to_tickets, TZ)
    block_dates = {b.start.date() for b in result.blocks}
    assert block_dates == {date(2026, 4, 24), date(2026, 5, 4)}
    assert date(2026, 5, 1) not in block_dates


def test_allocate_records_empty_days_for_working_days_with_no_tickets() -> None:
    day_to_tickets = {date(2026, 4, 20): _ticks("A-1")}  # Mon only
    result = allocate(date(2026, 4, 20), date(2026, 4, 22), set(), day_to_tickets, TZ)
    assert result.empty_days == [date(2026, 4, 21), date(2026, 4, 22)]


def test_allocate_records_skipped_per_day() -> None:
    keys = [f"K-{i:02d}" for i in range(1, 11)]
    day_to_tickets = {date(2026, 4, 20): _ticks(*keys)}
    result = allocate(date(2026, 4, 20), date(2026, 4, 20), set(), day_to_tickets, TZ)
    assert result.skipped == {date(2026, 4, 20): keys[8:]}


def test_allocate_is_deterministic() -> None:
    day_to_tickets = {
        date(2026, 4, 20): _ticks("A-1", "B-1", "C-1"),
        date(2026, 4, 21): _ticks("X-9", "M-2", "B-1"),
    }
    r1 = allocate(date(2026, 4, 20), date(2026, 4, 21), set(), day_to_tickets, TZ)
    r2 = allocate(date(2026, 4, 20), date(2026, 4, 21), set(), day_to_tickets, TZ)
    assert [asdict(b) for b in r1.blocks] == [asdict(b) for b in r2.blocks]
    assert r1.empty_days == r2.empty_days
    assert r1.skipped == r2.skipped


def test_allocate_total_hours_per_non_empty_day_is_8() -> None:
    day_to_tickets = {
        date(2026, 4, 20): _ticks("A-1"),
        date(2026, 4, 21): _ticks("A-1", "B-1", "C-1"),
        date(2026, 4, 22): _ticks(*[f"K-{i:02d}" for i in range(1, 6)]),
    }
    result = allocate(date(2026, 4, 20), date(2026, 4, 22), set(), day_to_tickets, TZ)
    by_day: dict[date, float] = {}
    for b in result.blocks:
        by_day[b.start.date()] = by_day.get(b.start.date(), 0.0) + (
            b.end - b.start
        ).total_seconds() / 3600
    for d, hours in by_day.items():
        assert hours == 8, (d, hours)


def test_allocate_returns_empty_result_when_no_working_days() -> None:
    holidays = {
        date(2026, 4, 20),
        date(2026, 4, 21),
        date(2026, 4, 22),
        date(2026, 4, 23),
        date(2026, 4, 24),
    }
    day_to_tickets = {d: _ticks("A-1") for d in holidays}
    result = allocate(date(2026, 4, 20), date(2026, 4, 26), holidays, day_to_tickets, TZ)
    assert result == AllocationResult()
