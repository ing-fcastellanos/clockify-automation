## 1. Project bootstrap

- [x] 1.1 Initialize `pyproject.toml` with `uv init`, target Python 3.11+, declare deps: `httpx`, `typer`, `pydantic`, `pydantic-settings`, `python-dotenv`, `pyyaml`. Dev deps: `pytest`, `pytest-cov`, `freezegun`, `respx` (httpx mocking), `ruff`.
- [x] 1.2 Create the source layout `src/clockify_automation/{__init__,__main__,cli,config,sync,allocator}.py` plus `jira/` and `clockify/` packages, each with `__init__.py`.
- [x] 1.3 Create `.env.example` listing every env var: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `CLOCKIFY_API_KEY`, `CLOCKIFY_WORKSPACE_ID`, `CLOCKIFY_PROJECT_ID`, `CLOCKIFY_TAG_ID`, `CLOCKIFY_USER_ID` (optional), `TIMEZONE` (default `America/Mexico_City`).
- [x] 1.4 Create `.gitignore` ignoring `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `dist/`, `*.egg-info/`.
- [x] 1.5 Create `holidays.yaml` at repo root, committed, populated with Mexico 2026 federal holidays as illustrative examples and explanatory comments.
- [x] 1.6 Create `README.md` with: prerequisites, install (`uv sync`), env setup, basic usage (`uv run clockify-sync --from ... --to ...`), and "moving to GitHub Actions" placeholder section.
- [x] 1.7 Configure `ruff` (lint + format) in `pyproject.toml` with sensible defaults; add `pytest` config pointing to `tests/`.

## 2. Configuration layer

- [x] 2.1 In `config.py`, define a `Settings` pydantic-settings class that reads all env vars, validates required ones are non-empty, loads `.env` via `python-dotenv` only when `CI` env is unset, and exposes a single `load_settings()` factory.
- [x] 2.2 Add `holidays.py` (or function in `config.py`) that loads `holidays.yaml`, parses each date as ISO `YYYY-MM-DD`, and returns a `frozenset[date]`. Raise a clear error if the file is missing or malformed.
- [x] 2.3 Add a small `tests/test_config.py` covering: missing required env raises, optional `CLOCKIFY_USER_ID` defaults to `None`, holidays file parses correctly, malformed holidays file raises with a clear message.

## 3. JIRA source — client and changelog timeline

- [x] 3.1 In `jira/client.py`, build an `httpx.Client` factory with Basic auth (`email:token` base64), a sane timeout, and a custom logger that redacts `Authorization` headers.
- [x] 3.2 Implement `search_candidate_issues(client, jql, fields)` that paginates `/rest/api/3/search` until exhausted, requesting `expand=changelog` and the needed fields (`summary`).
- [x] 3.3 Implement an exponential-backoff-with-jitter retry wrapper that honors `Retry-After` on 429 and retries on 5xx. Cover with a `respx` test for one success-after-429 case.
- [x] 3.4 In `jira/timeline.py`, implement `reconstruct_intervals(issue, current_user_account_id, now_local) -> list[Interval]`: merge changelog `assignee` and `status` events into a sorted timeline, walk it carrying `(assignee, status)` state, emit disjoint intervals where both conditions hold. Open intervals get `end = now_local`.
- [x] 3.5 In `jira/timeline.py`, implement `intervals_to_active_days(intervals, tz) -> set[date]`: for each interval, iterate the days in local tz between `start.date()` and `end.date()`, return the union.
- [x] 3.6 In `jira/__init__.py`, expose `fetch_active_tickets_by_day(settings, from_date, to_date) -> dict[date, list[Ticket]]` orchestrating: build JQL, search, reconstruct intervals per issue, map to days, group by day with tickets sorted alphabetically by key. Each `Ticket` carries `key` and optional `summary`.
- [x] 3.7 Add `tests/test_timeline.py` covering: single continuous interval, two disjoint intervals (In Progress→Done→In Progress), reassignment in the middle, never-assigned-to-user, interval crossing midnight, interval spanning multiple days, open interval (still in progress at "now").

## 4. Time allocator — pure logic

- [x] 4.1 In `allocator.py`, define dataclasses `Ticket(key: str, summary: str | None)`, `Block(ticket_key: str, summary: str | None, start: datetime, end: datetime)`, and `AllocationResult(blocks: list[Block], empty_days: list[date], skipped: dict[date, list[str]])`.
- [x] 4.2 Implement `working_days(from_date, to_date, holidays, work_days={MON..FRI}) -> list[date]` that yields ordered working days in range, excluding weekends and holiday dates.
- [x] 4.3 Implement `allocate_day(active_tickets: list[Ticket], day: date, tz, day_start=time(9,0), day_end=time(17,0)) -> tuple[list[Block], list[str]]`: applies `base = 8 // N`, `remainder = 8 - base*N`, sorts tickets alphabetically, returns blocks and the skipped keys when N > 8.
- [x] 4.4 Implement `allocate(range, holidays, day_to_tickets, tz) -> AllocationResult` that combines the above and produces the full result.
- [x] 4.5 Add `tests/test_allocator.py` covering: working-day filtering with weekends, with holidays mid-range, with full-week holiday range; per-day allocations for N=1, 2, 3, 4, 5, 6, 7, 8; N=0 produces empty_days entry; N=9, 10 trigger `skipped`; alphabetical ordering verified; block start/end times exactly contiguous; total hours per day = 8 in all non-empty cases; tz-aware datetimes are produced; determinism (same input twice = identical bytes).

## 5. Clockify sink — client, dedupe, sink

- [x] 5.1 In `clockify/client.py`, build an `httpx.Client` with `X-Api-Key` header from `CLOCKIFY_API_KEY`, redaction in logger. Add `resolve_user_id(client)` calling `/api/v1/user` if `CLOCKIFY_USER_ID` is unset.
- [x] 5.2 Implement `list_user_entries(client, workspace_id, user_id, start, end)`: paginated GET of `/api/v1/workspaces/{ws}/user/{user_id}/time-entries` filtering to the rangeand returning all entries.
- [x] 5.3 Implement `create_time_entry(client, workspace_id, payload)` and `delete_time_entry(client, workspace_id, entry_id)` with the documented payload shape.
- [x] 5.4 In `clockify/dedupe.py`, implement `is_automation_owned(entry, project_id, tag_id, regex=re.compile(r"^[A-Z][A-Z0-9_]+-\d+( — .*)?$")) -> bool` checking projectId + tagIds membership + description regex.
- [x] 5.5 Implement `partition_entries(entries, project_id, tag_id) -> tuple[list, list]` returning `(automation_owned, untouched)`.
- [x] 5.6 In `clockify/__init__.py`, build `apply_blocks(settings, blocks: list[Block], mode: Literal["error","force","skip","dry_run"]) -> SinkReport`: pre-fetch existing entries, run dedupe, branch by mode, perform deletes (force) or filter blocks (skip), then create entries. On any single failure during force-deletion, abort before creating.
- [x] 5.7 Implement description formatting helper that builds `"<KEY> — <summary>"` (or just `<KEY>` when summary is missing) and truncates to 500 chars with `…`.
- [x] 5.8 Implement local-to-UTC conversion helper using `zoneinfo` and ISO 8601 `Z` formatting; assert it is never called with naive datetimes.
- [x] 5.9 Add `tests/test_dedupe.py` covering: automation-owned vs. manual entries (matrix of project/tag/description matches), partition_entries returns disjoint sets, regex accepts `PROJ-123`, `PROJ-123 — Fix the thing`, rejects `Reunión semanal`, rejects `proj-123` (lower case).
- [x] 5.10 Add `tests/test_sink.py` (using `respx`) covering: error mode aborts with conflict message, force mode deletes-then-creates, force mode preserves manual entries, skip mode skips conflicting days but processes others, dry-run makes no POST/DELETE calls but does GET, payload has correct UTC timestamps and required fields.

## 6. Orchestration and CLI

- [x] 6.1 In `sync.py`, implement `run(settings, from_date, to_date, mode) -> RunReport` that: fetches day-to-tickets from JIRA, calls allocator, calls Clockify sink, aggregates a report (entries created, days skipped, tickets skipped per day, deleted entries when force).
- [x] 6.2 In `cli.py`, define a `typer` app with one command accepting `--from` and `--to` (ISO dates, required), mutually exclusive `--force` / `--skip`, plus `--dry-run`. Include `--verbose` flag toggling DEBUG logs.
- [x] 6.3 Configure `__main__.py` to invoke the typer app; add a `[project.scripts]` entry in `pyproject.toml` named `clockify-sync`.
- [x] 6.4 Implement structured logging (Python `logging`) with default INFO; verbose flag promotes to DEBUG without ever emitting tokens or keys.
- [x] 6.5 Print a final human-readable summary at end of run: blocks created, days with skipped tickets (with names), empty days, total hours.

## 7. Test consolidation and smoke run

- [x] 7.1 Run the full pytest suite, fix any failures, confirm coverage of allocator and timeline above 90%.
- [x] 7.2 Smoke test end-to-end against a real-but-narrow date range (e.g., last 2 days) with `--dry-run` and real credentials, validate the printed plan matches expectations.
- [x] 7.3 Run end-to-end without `--dry-run` for the same range; verify entries appear in Clockify with correct times, descriptions, project, and tag.
- [x] 7.4 Re-run the same range without flags to confirm the default-mode abort behavior; then re-run with `--force` to confirm replacement.

## 8. Documentation and CI prep

- [x] 8.1 Update `README.md` with: troubleshooting (missing env, 401 from JIRA, rate limits), idempotency semantics, holidays maintenance, timezone notes.
- [x] 8.2 Document the GitHub Actions migration path in README: which envs become repo secrets vs. variables, suggested workflow trigger (manual `workflow_dispatch` with from/to inputs). Do NOT add the workflow file in this milestone.
- [x] 8.3 Add a short `CONTRIBUTING.md`-style note (or section in README) on running tests (`uv run pytest`) and lint (`uv run ruff check`).
