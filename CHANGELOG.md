# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
