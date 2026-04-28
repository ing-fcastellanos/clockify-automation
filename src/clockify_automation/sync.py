from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from clockify_automation.allocator import AllocationResult, allocate
from clockify_automation.allocator import Ticket as AllocTicket
from clockify_automation.clockify import Mode, SinkReport, apply_blocks
from clockify_automation.config import Settings, load_holidays
from clockify_automation.jira import fetch_active_tickets_by_day


@dataclass(frozen=True)
class Plan:
    allocation: AllocationResult
    mode: Mode
    from_date: date
    to_date: date


@dataclass(frozen=True)
class RunReport:
    allocation: AllocationResult
    sink: SinkReport
    mode: Mode
    from_date: date
    to_date: date


def plan(
    settings: Settings,
    from_date: date,
    to_date: date,
    mode: Mode,
    holidays_path: Path | str = "holidays.yaml",
) -> Plan:
    holidays = load_holidays(holidays_path)

    jira_day_to_tickets = fetch_active_tickets_by_day(settings, from_date, to_date)
    alloc_input = {
        d: [AllocTicket(key=t.key, summary=t.summary) for t in tickets]
        for d, tickets in jira_day_to_tickets.items()
    }

    allocation = allocate(
        from_date,
        to_date,
        holidays,
        alloc_input,
        settings.timezone,
    )

    return Plan(allocation=allocation, mode=mode, from_date=from_date, to_date=to_date)


def apply(settings: Settings, plan: Plan) -> RunReport:
    sink_report = apply_blocks(
        settings,
        plan.allocation.blocks,
        plan.mode,
        from_date=plan.from_date,
        to_date=plan.to_date,
    )

    return RunReport(
        allocation=plan.allocation,
        sink=sink_report,
        mode=plan.mode,
        from_date=plan.from_date,
        to_date=plan.to_date,
    )


def run(
    settings: Settings,
    from_date: date,
    to_date: date,
    mode: Mode,
    holidays_path: Path | str = "holidays.yaml",
) -> RunReport:
    return apply(settings, plan(settings, from_date, to_date, mode, holidays_path))
