from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WORK_DAY_HOURS = 8
DAY_MAX_TICKETS = WORK_DAY_HOURS  # one block per ticket, minimum 1h
DEFAULT_DAY_START = time(9, 0)
DEFAULT_DAY_END = time(17, 0)
DEFAULT_WORK_DAYS = frozenset({0, 1, 2, 3, 4})  # Mon-Fri (Python weekday())


@dataclass(frozen=True)
class Ticket:
    key: str
    summary: str | None = None


@dataclass(frozen=True)
class Block:
    ticket_key: str
    summary: str | None
    start: datetime
    end: datetime


@dataclass(frozen=True)
class AllocationResult:
    blocks: list[Block] = field(default_factory=list)
    empty_days: list[date] = field(default_factory=list)
    skipped: dict[date, list[str]] = field(default_factory=dict)


def working_days(
    from_date: date,
    to_date: date,
    holidays: Iterable[date] = (),
    work_days: Iterable[int] = DEFAULT_WORK_DAYS,
) -> list[date]:
    holidays_set = set(holidays)
    work_set = set(work_days)
    if from_date > to_date:
        return []
    out: list[date] = []
    d = from_date
    one_day = timedelta(days=1)
    while d <= to_date:
        if d.weekday() in work_set and d not in holidays_set:
            out.append(d)
        d = d + one_day
    return out


def _allocations_for_n(n: int) -> list[int]:
    if n <= 0:
        return []
    if n >= WORK_DAY_HOURS:
        return [1] * WORK_DAY_HOURS
    base = WORK_DAY_HOURS // n
    remainder = WORK_DAY_HOURS - base * n
    return [base + 1] * remainder + [base] * (n - remainder)


def allocate_day(
    active_tickets: list[Ticket],
    day: date,
    tz: ZoneInfo,
    day_start: time = DEFAULT_DAY_START,
    day_end: time = DEFAULT_DAY_END,
) -> tuple[list[Block], list[str]]:
    if not active_tickets:
        return [], []

    sorted_tickets = sorted(active_tickets, key=lambda t: t.key)
    if len(sorted_tickets) > DAY_MAX_TICKETS:
        used = sorted_tickets[:DAY_MAX_TICKETS]
        skipped = [t.key for t in sorted_tickets[DAY_MAX_TICKETS:]]
    else:
        used = sorted_tickets
        skipped = []

    hours_per = _allocations_for_n(len(used))

    blocks: list[Block] = []
    cursor = datetime.combine(day, day_start, tzinfo=tz)
    for ticket, hours in zip(used, hours_per, strict=True):
        end = cursor + timedelta(hours=hours)
        blocks.append(
            Block(
                ticket_key=ticket.key,
                summary=ticket.summary,
                start=cursor,
                end=end,
            )
        )
        cursor = end

    expected_end = datetime.combine(day, day_end, tzinfo=tz)
    assert cursor == expected_end, (
        f"allocator drift on {day}: ended at {cursor}, expected {expected_end}"
    )
    return blocks, skipped


def allocate(
    from_date: date,
    to_date: date,
    holidays: Iterable[date],
    day_to_tickets: Mapping[date, list[Ticket]],
    tz: ZoneInfo,
    day_start: time = DEFAULT_DAY_START,
    day_end: time = DEFAULT_DAY_END,
    work_days: Iterable[int] = DEFAULT_WORK_DAYS,
) -> AllocationResult:
    days = working_days(from_date, to_date, holidays, work_days)

    blocks: list[Block] = []
    empty: list[date] = []
    skipped: dict[date, list[str]] = {}

    for d in days:
        tickets = day_to_tickets.get(d, [])
        if not tickets:
            empty.append(d)
            continue
        day_blocks, day_skipped = allocate_day(tickets, d, tz, day_start, day_end)
        blocks.extend(day_blocks)
        if day_skipped:
            skipped[d] = day_skipped

    return AllocationResult(blocks=blocks, empty_days=empty, skipped=skipped)
