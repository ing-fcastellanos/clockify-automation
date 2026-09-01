## ADDED Requirements

### Requirement: List all user entries in a window without ownership filtering

The system SHALL provide a way to list every Clockify time entry belonging to the
user within an arbitrary date window, without filtering by project, tag, or
description, and SHALL expose the mapping from an entry to its local calendar day
in the configured timezone as a reusable operation.

This unfiltered listing SHALL be distinct from automation-ownership detection:
the ownership filter continues to govern conflict detection, deletion, and
skipping, and is unaffected by this requirement.

#### Scenario: Unfiltered listing includes foreign entries

- **WHEN** the window contains an entry in a project other than `CLOCKIFY_PROJECT_ID`
- **THEN** the unfiltered listing includes it
- **AND** the automation-owned partition still excludes it

#### Scenario: Local day of an entry

- **WHEN** an entry's `timeInterval.start` is `2026-08-28T03:00:00Z` and `TIMEZONE` is `America/Mexico_City`
- **THEN** its local day is 2026-08-27

#### Scenario: Entry without a start timestamp

- **WHEN** an entry has no `timeInterval.start`
- **THEN** it has no local day and is ignored by callers that group entries by day
