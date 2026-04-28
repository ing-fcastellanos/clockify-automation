## ADDED Requirements

### Requirement: Authenticate against Clockify with API key

The system SHALL authenticate against the Clockify v1 REST API using the `X-Api-Key` header. The API key SHALL be read from the environment variable `CLOCKIFY_API_KEY`. The workspace, project, and tag IDs SHALL be read from `CLOCKIFY_WORKSPACE_ID`, `CLOCKIFY_PROJECT_ID`, and `CLOCKIFY_TAG_ID` respectively. The system SHALL never log, print, or otherwise expose the API key. If `CLOCKIFY_USER_ID` is not provided, the system SHALL resolve it at runtime via the `/api/v1/user` endpoint and use it for all subsequent listing and deletion calls.

#### Scenario: Successful authentication

- **WHEN** the user runs `clockify-sync` with valid Clockify env vars
- **THEN** every Clockify request includes `X-Api-Key: <key>`
- **AND** the API key never appears in log output

#### Scenario: Missing required env var

- **WHEN** `CLOCKIFY_PROJECT_ID` is unset
- **THEN** the system aborts with a clear error naming the missing variable
- **AND** no Clockify request is made

#### Scenario: User ID auto-resolution

- **WHEN** `CLOCKIFY_USER_ID` is unset and the user runs the sync
- **THEN** the system calls `/api/v1/user` once to resolve the user ID
- **AND** uses that ID for the rest of the run

### Requirement: Identify automation-owned entries by project, tag, and description

An existing Clockify time entry SHALL be considered owned by this automation if and only if all three of the following hold: (a) its `projectId` equals the configured `CLOCKIFY_PROJECT_ID`, (b) the configured `CLOCKIFY_TAG_ID` is present in its `tagIds` list, and (c) its `description` matches the regular expression `^[A-Z][A-Z0-9_]+-\d+( — .*)?$`. Entries that fail any of these criteria SHALL never be deleted, modified, or counted as conflicts.

#### Scenario: Manual entry with prose description in same project

- **WHEN** the user has an entry in the configured project with description "Reunión semanal" and the configured tag
- **THEN** that entry is NOT considered automation-owned
- **AND** is left untouched by all run modes

#### Scenario: Automation-owned entry

- **WHEN** an entry has the configured projectId, includes the configured tagId, and description "PROJ-123 — Fix the thing"
- **THEN** that entry is considered automation-owned

#### Scenario: Entry in different project

- **WHEN** an entry has description "PROJ-123 — Fix the thing" but its projectId does not match
- **THEN** that entry is NOT considered automation-owned

### Requirement: Default mode aborts when prior automation entries exist in range

When the user runs the sync without `--force`, `--skip`, or `--dry-run`, and the system finds at least one automation-owned entry within the requested date range, the system SHALL abort before creating any new entries. The error message SHALL list (a) how many automation-owned entries were found, (b) the date range, and (c) suggest the `--force` and `--skip` alternatives.

#### Scenario: Conflict detected, default mode

- **WHEN** the range contains 5 automation-owned entries and the user runs without flags
- **THEN** no new entries are created
- **AND** the error message names the count, the range, and suggests `--force` or `--skip`

#### Scenario: No conflict, default mode proceeds

- **WHEN** the range contains zero automation-owned entries
- **THEN** the system creates new entries normally

### Requirement: Force mode replaces automation-owned entries

When the user passes `--force`, the system SHALL delete every automation-owned entry within the requested date range before creating any new entries. Manual entries SHALL never be deleted. If deletion of a specific entry fails, the system SHALL abort and report the failure without creating any new entries.

#### Scenario: Force mode replaces existing automation entries

- **WHEN** the user runs with `--force` and the range has 3 automation-owned entries
- **THEN** those 3 entries are deleted first
- **AND** new entries are created based on the current JIRA + allocator output

#### Scenario: Force mode preserves manual entries

- **WHEN** the range has 2 automation-owned entries and 1 manual entry
- **THEN** with `--force`, the 2 automation entries are deleted but the manual entry is preserved

### Requirement: Skip mode leaves days with prior automation entries untouched

When the user passes `--skip`, the system SHALL leave intact every day in the range that already contains at least one automation-owned entry, creating no new entries for those days. Days that have no automation-owned entries SHALL be processed normally.

#### Scenario: Some days already have entries

- **WHEN** the range is Mon–Fri and Mon, Tue already have automation-owned entries
- **THEN** with `--skip`, Mon and Tue are left untouched and Wed, Thu, Fri are processed normally

### Requirement: Dry-run mode performs no writes

When the user passes `--dry-run`, the system SHALL NOT call any Clockify endpoint that creates, updates, or deletes data. It MAY call read endpoints to detect conflicts. It SHALL print, for each planned time entry, the date, start time, end time, ticket key, and description that would be sent.

#### Scenario: Dry-run prints plan without writes

- **WHEN** the user runs with `--dry-run`
- **THEN** no `POST /time-entries` or `DELETE /time-entries/{id}` request is made
- **AND** the planned entries are printed to stdout in a human-readable format

### Requirement: Create time entries with correct payload

For each block produced by the time allocator, the system SHALL create a Clockify time entry by POST to `/api/v1/workspaces/{workspaceId}/time-entries` with `start` and `end` as ISO 8601 UTC timestamps (converted from the configured local timezone), `description` set to `"<TICKET-KEY> — <summary>"` (or just `<TICKET-KEY>` when summary is unavailable), `projectId` set to the configured project ID, and `tagIds` containing exactly the configured tag ID.

#### Scenario: Standard entry creation

- **WHEN** the allocator produces a block (PROJ-123, 2026-04-21 09:00 local, 2026-04-21 11:00 local) with summary "Fix login bug"
- **THEN** a POST is made with start in UTC, end in UTC, description "PROJ-123 — Fix login bug", projectId, and tagIds matching configuration

#### Scenario: Missing summary

- **WHEN** a block's ticket has no summary
- **THEN** the description is just the ticket key (no em-dash, no trailing space)

#### Scenario: Very long summary

- **WHEN** a ticket summary exceeds 500 characters
- **THEN** the description is truncated to 500 characters with a trailing `…` while preserving the `<KEY> — ` prefix

### Requirement: Convert local timestamps to UTC for Clockify payload

All `start` and `end` values sent to Clockify SHALL be in UTC, formatted as ISO 8601 with the `Z` suffix. Conversion SHALL use `zoneinfo` based on the configured `TIMEZONE` (default `America/Mexico_City`) and SHALL never use a naive UTC conversion.

#### Scenario: Mexico City local time conversion

- **WHEN** a block is 2026-04-21 09:00 local in `America/Mexico_City` (UTC-6)
- **THEN** the payload `start` is `2026-04-21T15:00:00Z`
