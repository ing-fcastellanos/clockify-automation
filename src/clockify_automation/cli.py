from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from clockify_automation.allocator import Block
from clockify_automation.auto_range import (
    LOOKBACK_DAYS,
    NoRecentEntriesError,
    resolve_automatic_range,
)
from clockify_automation.clockify import ConflictError, Mode
from clockify_automation.config import Settings, load_settings
from clockify_automation.sync import Plan, RunReport, apply, plan


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _resolve_mode(*, force: bool, skip: bool, dry_run: bool) -> Mode:
    chosen = sum([force, skip, dry_run])
    if chosen > 1:
        raise typer.BadParameter("--force, --skip, and --dry-run are mutually exclusive")
    if dry_run:
        return "dry_run"
    if force:
        return "force"
    if skip:
        return "skip"
    return "error"


def _validate_flag_contract(
    *,
    automatic: bool,
    from_: str | None,
    to: str | None,
    force: bool,
    skip: bool,
) -> None:
    if automatic:
        if from_ is not None or to is not None:
            raise typer.BadParameter("--automatic cannot be combined with --from or --to")
        if force or skip:
            raise typer.BadParameter("--automatic cannot be combined with --force or --skip")
        return
    if from_ is None or to is None:
        raise typer.BadParameter("--from and --to are required, or use --automatic to derive them")


def _resolve_automatic_dates(settings: Settings) -> tuple[date, date]:
    """Derive the range from Clockify, or exit cleanly when there is nothing to do."""
    try:
        auto = resolve_automatic_range(settings)
    except NoRecentEntriesError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc

    if auto is None:
        today = datetime.now(tz=settings.timezone).date()
        print(f"Clockify is up to date through {today.isoformat()}. Nothing to do.")
        raise typer.Exit(code=0)

    print(
        f"Last day with Clockify entries: {auto.last_entry_date.isoformat()}. "
        f"Deriving range {auto.from_date.isoformat()} → {auto.to_date.isoformat()}."
    )
    return auto.from_date, auto.to_date


def _print_plan(p: Plan) -> float:
    print()
    print("=" * 60)
    print(f"Range: {p.from_date.isoformat()} → {p.to_date.isoformat()}")
    print(f"Mode:  {p.mode}")
    print("=" * 60)

    blocks_by_day: dict[date, list[Block]] = {}
    for b in p.allocation.blocks:
        blocks_by_day.setdefault(b.start.date(), []).append(b)

    total_hours = 0.0
    for d in sorted(blocks_by_day):
        day_blocks = blocks_by_day[d]
        day_hours = sum((b.end - b.start).total_seconds() / 3600 for b in day_blocks)
        total_hours += day_hours
        print(
            f"\n{d.isoformat()} ({d.strftime('%a')}) — {day_hours:.0f}h, "
            f"{len(day_blocks)} ticket(s)"
        )
        for b in day_blocks:
            hours = int((b.end - b.start).total_seconds() // 3600)
            label = f"{b.ticket_key}" + (f" — {b.summary}" if b.summary else "")
            print(f"  {b.start.strftime('%H:%M')}-{b.end.strftime('%H:%M')}  {hours}h  {label}")
        if d in p.allocation.skipped:
            skipped = ", ".join(p.allocation.skipped[d])
            print(f"  ! skipped (>8 tickets): {skipped}")

    if p.allocation.empty_days:
        empty = ", ".join(d.isoformat() for d in p.allocation.empty_days)
        print(f"\nWorking days with no active tickets: {empty}")

    print()
    print(f"Planned: {len(p.allocation.blocks)} entries, {total_hours:.0f}h total.")
    return total_hours


def _print_outcome(report: RunReport, total_hours: float) -> None:
    if report.sink.skipped_days:
        skipped = ", ".join(d.isoformat() for d in report.sink.skipped_days)
        print(f"Days skipped due to existing entries (--skip): {skipped}")

    if report.sink.deleted:
        print(f"Deleted {len(report.sink.deleted)} prior automation entries (--force).")

    print()
    if report.mode == "dry_run":
        print(
            f"DRY RUN. {len(report.sink.planned)} entries would be created. Total {total_hours:.0f}h."
        )
    else:
        print(f"Created {len(report.sink.created)} entries. Total {total_hours:.0f}h.")


def _main(
    from_: Annotated[
        str | None,
        typer.Option("--from", "-F", help="Start date (inclusive), YYYY-MM-DD."),
    ] = None,
    to: Annotated[
        str | None,
        typer.Option("--to", "-t", help="End date (inclusive), YYYY-MM-DD."),
    ] = None,
    automatic: Annotated[
        bool,
        typer.Option(
            "--automatic",
            "-a",
            help=(
                "Derive the range from Clockify: from the day after the last day with "
                f"any entry (searched {LOOKBACK_DAYS} days back) through today."
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-d", help="Print plan without writing to Clockify."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f", help="Delete prior automation entries in range and recreate."
        ),
    ] = False,
    skip: Annotated[
        bool,
        typer.Option("--skip", "-s", help="Skip days that already have automation entries."),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="DEBUG-level logs.")] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt before writing to Clockify."),
    ] = False,
    holidays: Annotated[
        Path,
        typer.Option("--holidays", "-H", help="Path to holidays.yaml."),
    ] = Path("holidays.yaml"),
) -> None:
    _setup_logging(verbose)
    _validate_flag_contract(automatic=automatic, from_=from_, to=to, force=force, skip=skip)
    mode = _resolve_mode(force=force, skip=skip, dry_run=dry_run)

    settings = load_settings()

    if automatic:
        from_date, to_date = _resolve_automatic_dates(settings)
    else:
        assert from_ is not None and to is not None  # guaranteed by _validate_flag_contract
        try:
            from_date = date.fromisoformat(from_)
            to_date = date.fromisoformat(to)
        except ValueError as exc:
            raise typer.BadParameter(
                f"--from and --to must be ISO dates (YYYY-MM-DD): {exc}"
            ) from exc
        if from_date > to_date:
            raise typer.BadParameter("--from must be on or before --to")

    plan_result = plan(settings, from_date, to_date, mode, holidays_path=holidays)
    total_hours = _print_plan(plan_result)

    if mode != "dry_run" and not plan_result.allocation.blocks:
        print("\nNothing to write.")
        raise typer.Exit(code=0)

    if mode != "dry_run" and not yes:
        print()
        if not typer.confirm("Apply these entries to Clockify?", default=False):
            print("Aborted. No changes were made.")
            raise typer.Exit(code=1)

    try:
        report = apply(settings, plan_result)
    except ConflictError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise typer.Exit(code=2) from exc

    _print_outcome(report, total_hours)


def app() -> None:
    # Windows consoles default to cp1252 which can't encode em-dash or arrows.
    # Reconfigure stdout/stderr to UTF-8 so summaries and descriptions print cleanly.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    typer.run(_main)
