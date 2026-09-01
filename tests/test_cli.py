from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import typer
from typer.testing import CliRunner

from clockify_automation import cli
from clockify_automation.allocator import AllocationResult, Block
from clockify_automation.auto_range import AutomaticRange, NoRecentEntriesError
from clockify_automation.sync import Plan

TZ = ZoneInfo("America/Mexico_City")

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    application = typer.Typer()
    application.command()(cli._main)
    return application


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    settings = SimpleNamespace(
        clockify_api_key="ck",
        clockify_workspace_id="ws-1",
        clockify_project_id="proj-1",
        clockify_tag_id="tag-1",
        clockify_user_id="user-1",
        timezone_name="America/Mexico_City",
        timezone=TZ,
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    return settings


def _plan_with_blocks(from_date: date, to_date: date, mode: str) -> Plan:
    from datetime import datetime

    block = Block(
        ticket_key="PROJ-1",
        summary="Do the thing",
        start=datetime.combine(from_date, datetime.min.time().replace(hour=9), tzinfo=TZ),
        end=datetime.combine(from_date, datetime.min.time().replace(hour=17), tzinfo=TZ),
    )
    return Plan(
        allocation=AllocationResult(blocks=[block]),
        mode=mode,  # type: ignore[arg-type]
        from_date=from_date,
        to_date=to_date,
    )


def _empty_plan(from_date: date, to_date: date, mode: str) -> Plan:
    return Plan(
        allocation=AllocationResult(blocks=[]),
        mode=mode,  # type: ignore[arg-type]
        from_date=from_date,
        to_date=to_date,
    )


# ---------------------------------------------------------------------------
# Flag contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [["--from", "2026-08-01"], ["--to", "2026-08-31"]],
)
def test_automatic_rejects_explicit_dates(app: typer.Typer, extra: list[str]) -> None:
    result = runner.invoke(app, ["--automatic", *extra])
    assert result.exit_code != 0
    assert "--automatic cannot be combined with --from or --to" in result.output


@pytest.mark.parametrize("extra", ["--force", "--skip"])
def test_automatic_rejects_force_and_skip(app: typer.Typer, extra: str) -> None:
    result = runner.invoke(app, ["--automatic", extra])
    assert result.exit_code != 0
    assert "--automatic cannot be combined with --force or --skip" in result.output


def test_dates_required_without_automatic(app: typer.Typer) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "--automatic" in result.output


def test_partial_range_without_automatic_is_rejected(app: typer.Typer) -> None:
    result = runner.invoke(app, ["--from", "2026-08-01"])
    assert result.exit_code != 0
    assert "--from and --to are required" in result.output


def test_manual_range_still_works(app: typer.Typer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "plan",
        lambda *a, **k: _plan_with_blocks(date(2026, 8, 3), date(2026, 8, 3), "dry_run"),
    )
    monkeypatch.setattr(
        cli,
        "apply",
        lambda settings, p: cli.RunReport(
            allocation=p.allocation,
            sink=SimpleNamespace(created=[], deleted=[], skipped_days=[], planned=[{}]),
            mode=p.mode,
            from_date=p.from_date,
            to_date=p.to_date,
        ),
    )
    result = runner.invoke(app, ["--from", "2026-08-03", "--to", "2026-08-03", "--dry-run"])
    assert result.exit_code == 0
    assert "2026-08-03" in result.output


# ---------------------------------------------------------------------------
# Automatic mode behavior
# ---------------------------------------------------------------------------


def test_automatic_derives_and_reports_range(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "resolve_automatic_range",
        lambda settings: AutomaticRange(
            last_entry_date=date(2026, 8, 27),
            from_date=date(2026, 8, 28),
            to_date=date(2026, 8, 31),
        ),
    )
    captured: dict[str, Any] = {}

    def fake_plan(settings: Any, from_date: date, to_date: date, mode: str, **kw: Any) -> Plan:
        captured["range"] = (from_date, to_date)
        captured["mode"] = mode
        return _plan_with_blocks(from_date, to_date, mode)

    monkeypatch.setattr(cli, "plan", fake_plan)
    monkeypatch.setattr(
        cli,
        "apply",
        lambda settings, p: cli.RunReport(
            allocation=p.allocation,
            sink=SimpleNamespace(created=[], deleted=[], skipped_days=[], planned=[{}]),
            mode=p.mode,
            from_date=p.from_date,
            to_date=p.to_date,
        ),
    )

    result = runner.invoke(app, ["--automatic", "--dry-run"])

    assert result.exit_code == 0
    assert captured["range"] == (date(2026, 8, 28), date(2026, 8, 31))
    assert captured["mode"] == "dry_run"
    assert "Last day with Clockify entries: 2026-08-27" in result.output
    assert "2026-08-28" in result.output


def test_automatic_uses_default_conflict_mode(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "resolve_automatic_range",
        lambda settings: AutomaticRange(
            last_entry_date=date(2026, 8, 27),
            from_date=date(2026, 8, 28),
            to_date=date(2026, 8, 31),
        ),
    )
    captured: dict[str, Any] = {}

    def fake_plan(settings: Any, from_date: date, to_date: date, mode: str, **kw: Any) -> Plan:
        captured["mode"] = mode
        return _plan_with_blocks(from_date, to_date, mode)

    monkeypatch.setattr(cli, "plan", fake_plan)
    monkeypatch.setattr(
        cli,
        "apply",
        lambda settings, p: cli.RunReport(
            allocation=p.allocation,
            sink=SimpleNamespace(created=[{"id": "x"}], deleted=[], skipped_days=[], planned=[{}]),
            mode=p.mode,
            from_date=p.from_date,
            to_date=p.to_date,
        ),
    )

    result = runner.invoke(app, ["--automatic", "--yes"])

    assert result.exit_code == 0
    assert captured["mode"] == "error"


def test_automatic_up_to_date_exits_zero_without_planning(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "resolve_automatic_range", lambda settings: None)

    def boom(*a: Any, **k: Any) -> Plan:
        raise AssertionError("plan() must not run when Clockify is up to date")

    monkeypatch.setattr(cli, "plan", boom)

    result = runner.invoke(app, ["--automatic"])

    assert result.exit_code == 0
    assert "up to date" in result.output


def test_automatic_without_recent_entries_exits_one(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_no_entries(settings: Any) -> AutomaticRange:
        raise NoRecentEntriesError("No Clockify entries found in the last 21 days. Use --from.")

    monkeypatch.setattr(cli, "resolve_automatic_range", raise_no_entries)

    def boom(*a: Any, **k: Any) -> Plan:
        raise AssertionError("plan() must not run without a derived range")

    monkeypatch.setattr(cli, "plan", boom)

    result = runner.invoke(app, ["--automatic"])

    assert result.exit_code == 1
    assert "No Clockify entries found" in result.output


def test_automatic_range_without_working_days_exits_zero(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "resolve_automatic_range",
        lambda settings: AutomaticRange(
            last_entry_date=date(2026, 8, 28),
            from_date=date(2026, 8, 29),
            to_date=date(2026, 8, 30),
        ),
    )
    monkeypatch.setattr(
        cli, "plan", lambda *a, **k: _empty_plan(date(2026, 8, 29), date(2026, 8, 30), "error")
    )

    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("apply() must not run with an empty allocation")

    monkeypatch.setattr(cli, "apply", boom)

    result = runner.invoke(app, ["--automatic", "--yes"])

    assert result.exit_code == 0
    assert "Nothing to write" in result.output
