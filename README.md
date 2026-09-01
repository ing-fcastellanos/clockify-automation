# jira-clockify-sync

[![PyPI version](https://img.shields.io/pypi/v/jira-clockify-sync.svg)](https://pypi.org/project/jira-clockify-sync/)
[![Python versions](https://img.shields.io/pypi/pyversions/jira-clockify-sync.svg)](https://pypi.org/project/jira-clockify-sync/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/ing-fcastellanos/clockify-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/ing-fcastellanos/clockify-automation/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ing-fcastellanos/clockify-automation/branch/main/graph/badge.svg)](https://codecov.io/gh/ing-fcastellanos/clockify-automation)

Sync your JIRA "In Progress" activity into Clockify time entries with one
command.

Given a date range, the tool finds every JIRA ticket where you were the
assignee and the status was "In Progress" during that range, then creates
Clockify time entries spreading 8 hours per working day across those tickets.

This is heuristic time-tracking — not auditing. It exists so the calendar shows
you've been working, without manual data entry every day.

## Prerequisites

- Python 3.11 or newer (tested on 3.14)
- A JIRA Cloud account with an API token
  (https://id.atlassian.com/manage-profile/security/api-tokens)
- A Clockify account with an API key
  (https://app.clockify.me/user/settings → API)
- The IDs of the workspace, project, and tag you use in Clockify

## Install

From PyPI:

```
pip install jira-clockify-sync
```

The package installs the `clockify-sync` command on your `PATH`.

For local development (editable install with dev dependencies), see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Configure

```
cp .env.example .env
```

Edit `.env` and fill in the JIRA and Clockify values. The file is gitignored.

To find the Clockify IDs, use:

- Workspace: `GET https://api.clockify.me/api/v1/workspaces`
  with header `X-Api-Key: <your-key>`
- Projects in workspace:
  `GET https://api.clockify.me/api/v1/workspaces/{ws}/projects`
- Tags in workspace:
  `GET https://api.clockify.me/api/v1/workspaces/{ws}/tags`

## Holidays

`holidays.yaml` is committed and lists the dates excluded from the working
calendar. The file ships with Mexico federal holidays for 2026. Format is one
ISO date per line, comments allowed:

```yaml
- 2026-01-01    # Año Nuevo
- 2026-12-25    # Navidad
```

Maintain this file by hand. The tool does NOT detect holidays automatically.
Update before December each year for the upcoming year.

## Usage

```
clockify-sync --from 2026-04-20 --to 2026-04-26
```

Flags (each has a short alias):

- `--from`, `-F` — start date, ISO format (required unless `--automatic`).
- `--to`, `-t` — end date, ISO format (required unless `--automatic`).
- `--automatic`, `-a` — derive the range from Clockify instead of passing dates.
- `--dry-run`, `-d` — print the plan, do not write anything to Clockify.
- `--force`, `-f` — replace any prior automation-owned entries in the range.
- `--skip`, `-s` — skip days that already have automation-owned entries.
- `--yes`, `-y` — skip the confirmation prompt before writing.
- `--verbose`, `-v` — DEBUG-level logging.
- `--holidays`, `-H PATH` — alternate holidays file (default: `holidays.yaml`).

Before writing anything, the CLI prints the plan and asks for confirmation.
Use `-y` to skip the prompt (e.g. in CI). `--dry-run` never prompts since it
never writes.

## Automatic mode

```
clockify-sync --automatic
```

Instead of asking you for a range, `--automatic` reads it from Clockify: it
finds the last day you have **any** time entry and syncs from the day after
that through today, inclusive.

```
  Aug 24  25  26  27  28  29  30  31 (today)
  ────────────────────────────────────────────
  entries ██  ██  ██  ──  ──  ──  ──   ──
                       └───── synced ─────┘
                  last day = Aug 26
```

Two rules make this safe to run unattended:

- **Any entry counts as a covered day.** Project, tag, and description are
  ignored — unlike conflict detection, which uses the strict ownership filter
  below. A one-hour standup logged in an unrelated project marks that day as
  covered, and the tool will not add its 8 hours on top of it. The bot only
  moves forward over completely untouched days.
- **The range never exceeds 20 days.** The search looks back 21 days, which
  caps the derived range by construction. If you have no entries at all in that
  window, the command aborts and asks you to pass `--from` and `--to` yourself,
  rather than guessing at a large backfill.

Automatic mode only ever moves the frontier forward. It does not backfill holes
that sit *before* the last day with entries — use an explicit `--from`/`--to`
range for those.

Exit codes:

| Situation | Exit |
|---|---|
| Entries created | 0 |
| Clockify already current (last day is today or later) | 0 |
| Derived range has no working days (weekend, holidays) | 0 |
| No entries in the 21-day window — needs `--from` | 1 |
| Confirmation declined | 1 |
| Conflicting automation-owned entries found in range | 2 |

`--automatic` is compatible with `--dry-run`, `--yes`, `--verbose`, and
`--holidays`. It is rejected together with `--from`, `--to`, `--force`, and
`--skip`: the range is derived precisely to avoid days that already have
entries, so there should be nothing to force or skip. If a conflict does turn
up anyway, the run aborts so you find out about it.

### Scheduled runs

Because it needs no arguments and stays quiet when there is nothing to do,
automatic mode is what you want on a scheduler:

```
# Weekdays at 18:00
0 18 * * 1-5  cd /path/to/project && clockify-sync --automatic --yes
```

Note that today is included even if the workday is not over — running at 10:00
still writes the full 09:00–17:00 block for today.

## Idempotency

The tool aborts by default if it finds entries it previously created within the
requested range. This protects against accidental double-writes.

It identifies its own entries by three criteria, ALL of which must hold:

1. The entry's `projectId` equals `CLOCKIFY_PROJECT_ID`.
2. The entry's `tagIds` contains `CLOCKIFY_TAG_ID`.
3. The entry's `description` matches the regex `^[A-Z][A-Z0-9_]+-\d+( — .*)?$`
   (e.g., `PROJ-123` or `PROJ-123 — Fix login`).

Any entry failing one of these is considered hand-made and is **never**
deleted, modified, or counted as a conflict — even if it lives in the same
project on the same day.

Conflict resolution flags:

| Flag        | Behavior                                                            |
|-------------|---------------------------------------------------------------------|
| (none)      | Abort with error if conflicts are found.                            |
| `--force`   | Delete the conflicting auto-entries first, then create fresh ones.  |
| `--skip`    | Leave days with conflicts untouched, write entries for other days.  |
| `--dry-run` | Read but never write; prints the plan and any conflicts detected.   |

## Timezone

All day-boundary arithmetic uses the timezone in `TIMEZONE` (default
`America/Mexico_City`). Clockify stores entries in UTC; conversion happens at
the boundary. If you change `TIMEZONE`, re-running for prior dates with
`--force` will resync entries against the new local boundaries.

Mexico City has not observed daylight saving time since 2022, so its offset is
a constant `-06:00`.

## Troubleshooting

**`ValidationError: JIRA_API_TOKEN ...` (or any other missing env var).**
The tool refuses to start without all required env vars set. Check `.env` is
present and populated, or that the env vars are exported in your shell.
`CLOCKIFY_USER_ID` is the only optional one.

**JIRA returns 401 / 403.**
The Basic auth header uses `JIRA_EMAIL` + `JIRA_API_TOKEN`. Common causes:
- Token revoked or expired (regenerate at the API tokens page).
- Email mismatch — must be the email of the JIRA Cloud account, not an alias.
- Tenant mismatch — `JIRA_BASE_URL` must point at the right Atlassian site.

**Clockify returns 401 / 403.**
Confirm `CLOCKIFY_API_KEY` is the active one in your Clockify profile (the
"Generate" button rotates it; old keys stop working immediately).

**JIRA / Clockify returns 429 (rate limited).**
The HTTP clients retry with exponential backoff and honor `Retry-After`. If
the issue persists for a wide range, narrow `--from`/`--to` and run in chunks.

**`zoneinfo._common.ZoneInfoNotFoundError` on Windows.**
Windows has no system tzdata. The `tzdata` PyPI package is declared as a
Windows-only runtime dependency and should install automatically. Re-run
`pip install -e ".[dev]"` if you skipped it.

**Tickets that should be detected aren't appearing.**
Detection requires (a) you were the assignee at the moment the status was
`"In Progress"` and (b) those moments fall inside the requested range. If a
ticket sat in `"In Progress"` while assigned to someone else, it won't count.
Run with `--verbose` and check the JQL it issues.

**A ticket appears on a day I didn't touch it.**
By design. The "presence" definition counts a day for a ticket if its
`(assignee=you ∧ status="In Progress")` interval intersects any moment of that
day. Long-running In-Progress tickets fill the day automatically.

**More than 8 tickets active in one day.**
The first 8 alphabetically by key receive 1 hour each, and the rest are
skipped with a warning that names them. There are no fractional-hour blocks.

## Moving to GitHub Actions

The tool reads only env vars at runtime, so the same code runs unmodified
under GitHub Actions.

### Step 1 — Define repo secrets and variables

Settings → Secrets and variables → Actions:

**Secrets** (sensitive — never logged in plaintext):

- `JIRA_API_TOKEN`
- `CLOCKIFY_API_KEY`

**Variables** (non-sensitive — visible in run logs):

- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `CLOCKIFY_WORKSPACE_ID`
- `CLOCKIFY_PROJECT_ID`
- `CLOCKIFY_TAG_ID`
- `CLOCKIFY_USER_ID` (optional)
- `TIMEZONE` (optional; defaults to `America/Mexico_City`)

### Step 2 — Add a workflow

Use a `workflow_dispatch` trigger so you can fire it manually with a date
range:

```yaml
# .github/workflows/sync.yml — example, NOT yet added by this milestone
name: Clockify sync
on:
  workflow_dispatch:
    inputs:
      from: { description: 'YYYY-MM-DD', required: true }
      to:   { description: 'YYYY-MM-DD', required: true }
      mode:
        description: 'error | force | skip | dry-run'
        default: 'error'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e .
      - env:
          JIRA_BASE_URL:        ${{ vars.JIRA_BASE_URL }}
          JIRA_EMAIL:           ${{ vars.JIRA_EMAIL }}
          JIRA_API_TOKEN:       ${{ secrets.JIRA_API_TOKEN }}
          CLOCKIFY_API_KEY:     ${{ secrets.CLOCKIFY_API_KEY }}
          CLOCKIFY_WORKSPACE_ID: ${{ vars.CLOCKIFY_WORKSPACE_ID }}
          CLOCKIFY_PROJECT_ID:  ${{ vars.CLOCKIFY_PROJECT_ID }}
          CLOCKIFY_TAG_ID:      ${{ vars.CLOCKIFY_TAG_ID }}
          TIMEZONE:             ${{ vars.TIMEZONE }}
          CI:                   'true'
        run: |
          flag=""
          case "${{ inputs.mode }}" in
            force)   flag="--force" ;;
            skip)    flag="--skip" ;;
            dry-run) flag="--dry-run" ;;
          esac
          clockify-sync --from "${{ inputs.from }}" --to "${{ inputs.to }}" $flag
```

The workflow file itself is intentionally not part of the initial milestone —
add it when you're ready to migrate.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, the quality
checks the project enforces, and the release process.

Hot-path coverage targets: `allocator.py` and `jira/timeline.py` should stay
above 90%. Adding new branches without tests is a smell.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the release history.

## License

[MIT](LICENSE) © 2026 Francisco Castellanos
