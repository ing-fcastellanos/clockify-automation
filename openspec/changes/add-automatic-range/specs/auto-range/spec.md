## ADDED Requirements

### Requirement: Derive the sync range from the last day with entries in Clockify

When invoked in automatic mode, the system SHALL determine the last day `D` on
which the user has ANY time entry in Clockify, and SHALL derive the sync range as
`from_date = D + 1 day` and `to_date = today`, where `today` is the current date
resolved in the configured `TIMEZONE`.

The determination of `D` SHALL consider every time entry belonging to the user in
the configured workspace, regardless of its project, tags, or description. It
SHALL NOT apply the automation-owned filter used for conflict detection. The day
of an entry SHALL be the local date, in the configured timezone, of the start of
its `timeInterval`.

#### Scenario: Last entry is several days back

- **WHEN** today is 2026-08-31 and the user's most recent Clockify entry starts on 2026-08-27
- **THEN** the derived range is 2026-08-28 through 2026-08-31 inclusive

#### Scenario: Manual entry in an unrelated project counts as covered

- **WHEN** the user's most recent entry is a 1-hour entry in a project other than `CLOCKIFY_PROJECT_ID` on 2026-08-29
- **THEN** that entry determines `D = 2026-08-29`
- **AND** the derived range starts on 2026-08-30

#### Scenario: Entry day uses the configured timezone

- **WHEN** an entry starts at `2026-08-28T03:00:00Z` and `TIMEZONE` is `America/Mexico_City`
- **THEN** the entry counts toward 2026-08-27, not 2026-08-28

### Requirement: Bound the lookback window and cap the derived range at 20 days

The system SHALL search for `D` only within a window of 21 days ending on
`today`. Because `from_date = D + 1`, this window SHALL guarantee that the derived
range never spans more than 20 days.

If no time entry exists anywhere in that window, the system SHALL NOT sync
anything, SHALL write an error naming the window length, SHALL instruct the user
to supply `--from` and `--to` explicitly, and SHALL exit with a non-zero status.

#### Scenario: No entries in the lookback window

- **WHEN** the user has no Clockify entries in the 21 days ending today
- **THEN** no JIRA query and no Clockify write is performed
- **AND** the error message states that no entries were found in the last 21 days and instructs the user to pass `--from`
- **AND** the process exits with a non-zero status

#### Scenario: Oldest resolvable entry produces a 20-day range

- **WHEN** today is 2026-08-31 and the only entry in the window starts on 2026-08-11
- **THEN** the derived range is 2026-08-12 through 2026-08-31, spanning 20 days

### Requirement: Report a no-op instead of failing when Clockify is already current

If `D` is on or after `today`, the system SHALL perform no JIRA query and no
Clockify write, SHALL print a message naming `D`, and SHALL exit with status 0.

If the derived range contains no working days — every day in it is a weekend or
appears in the holidays file — the system SHALL print a message saying there is
nothing to write and SHALL exit with status 0.

#### Scenario: Already synced today

- **WHEN** today is 2026-08-31 and the user already has an entry on 2026-08-31
- **THEN** the system reports that Clockify is up to date through 2026-08-31
- **AND** exits with status 0 without querying JIRA

#### Scenario: Derived range covers only a weekend

- **WHEN** today is Sunday 2026-08-30 and the last entry is Friday 2026-08-28
- **THEN** the derived range 2026-08-29 through 2026-08-30 yields no working days
- **AND** the system reports nothing to write and exits with status 0

### Requirement: Automatic mode is selected by a dedicated flag with an exclusive contract

The CLI SHALL expose a boolean flag `--automatic` (short alias `-a`) that
activates automatic range derivation.

When `--automatic` is given, the system SHALL reject `--from`, `--to`, `--force`,
and `--skip` with a usage error. The system SHALL accept `--dry-run`, `--yes`,
`--verbose`, and `--holidays` alongside `--automatic`.

When `--automatic` is NOT given, the system SHALL require both `--from` and
`--to`, and SHALL emit a usage error naming `--automatic` as the alternative when
either is missing.

#### Scenario: Automatic combined with an explicit date

- **WHEN** the user runs `clockify-sync --automatic --from 2026-08-01`
- **THEN** the system exits with a usage error stating that `--automatic` cannot be combined with `--from` or `--to`

#### Scenario: Automatic combined with force

- **WHEN** the user runs `clockify-sync --automatic --force`
- **THEN** the system exits with a usage error stating that `--automatic` cannot be combined with `--force` or `--skip`

#### Scenario: Automatic combined with dry-run

- **WHEN** the user runs `clockify-sync --automatic --dry-run`
- **THEN** the range is derived from Clockify
- **AND** the plan is printed
- **AND** no Clockify write is performed

#### Scenario: Neither automatic nor a date range

- **WHEN** the user runs `clockify-sync` with no date flags
- **THEN** the system exits with a usage error requiring `--from` and `--to` or suggesting `--automatic`

### Requirement: Automatic mode uses the default conflict policy

A run in automatic mode SHALL use the default conflict mode, aborting if any
automation-owned entry is found inside the derived range, unless `--dry-run` was
requested. The system SHALL NOT delete or skip entries on the user's behalf in
automatic mode.

#### Scenario: Unexpected conflict inside the derived range

- **WHEN** automatic mode derives a range that nevertheless contains an automation-owned entry
- **THEN** the run aborts with the standard conflict error
- **AND** no entry is created or deleted

### Requirement: Report the derived range before writing

Before creating any entry, the system SHALL print the day it detected as the last
covered day and the range it derived from it, so the user can verify the
deduction. When the run is interactive, this SHALL appear before the confirmation
prompt.

#### Scenario: Derived range is shown

- **WHEN** automatic mode derives 2026-08-28 through 2026-08-31 from a last entry on 2026-08-27
- **THEN** the output names 2026-08-27 as the last day with entries
- **AND** names the derived range before any write occurs
