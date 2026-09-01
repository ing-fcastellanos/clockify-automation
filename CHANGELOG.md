# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--automatic` / `-a`: derive the sync range from Clockify instead of passing
  dates. Finds the last day with any user time entry (searching 21 days back)
  and syncs from the day after it through today, inclusive. Any entry counts as
  a covered day regardless of project, tag, or description, so manual time
  tracking is never overwritten or doubled.
- Quiet exits for scheduled runs: exit 0 when Clockify is already current or the
  derived range holds no working days; exit 1 with a message pointing at
  `--from` when the 21-day window is empty.

### Changed

- `--from` and `--to` are now required only when `--automatic` is not used, and
  are rejected when it is. `--automatic` is also mutually exclusive with
  `--force` and `--skip`.
- A run that produces no entries to write now exits 0 with "Nothing to write."
  before contacting Clockify, including when `--yes` is given.

## [0.1.0] - 2026-04-28

### Added

- Initial release.
- Sync JIRA tickets that were "In Progress" within a date range into Clockify time entries.
- CLI `clockify-sync` with `--from` / `--to` date range, plus `--dry-run`, `--force`, `--skip` modes.
- Short flags for every option: `-F`, `-t`, `-d`, `-f`, `-s`, `-v`, `-y`, `-H`.
- Interactive confirmation prompt before writing to Clockify, with `--yes` / `-y` to skip.
- 8h-per-working-day allocation across active tickets, capped at 8 tickets per day.
- Holiday-awareness via `holidays.yaml`.
- Idempotent sync via project + tag + description matching for conflict detection.
- Configuration via `.env` (see `.env.example`) using `pydantic-settings`.

[Unreleased]: https://github.com/ing-fcastellanos/clockify-automation/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ing-fcastellanos/clockify-automation/releases/tag/v0.1.0
