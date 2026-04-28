## ADDED Requirements

### Requirement: Authenticate against JIRA Cloud with email + API token

The system SHALL authenticate against the JIRA Cloud REST API using HTTP Basic authentication, encoding the user's email and API token (`email:token`) in the `Authorization` header. Credentials SHALL be read from the environment variables `JIRA_EMAIL` and `JIRA_API_TOKEN`. The base URL SHALL come from `JIRA_BASE_URL`. The system SHALL never log, print, or otherwise expose the API token, including in error messages.

#### Scenario: Successful authentication

- **WHEN** the user runs `clockyfy-sync` with valid `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_BASE_URL` env vars
- **THEN** the system performs JIRA requests with `Authorization: Basic <base64(email:token)>`
- **AND** the API token does not appear in any log output or error message

#### Scenario: Missing credentials

- **WHEN** the user runs `clockyfy-sync` and `JIRA_API_TOKEN` is unset or empty
- **THEN** the system aborts with a clear error message naming the missing variable
- **AND** no HTTP request is made

#### Scenario: Authentication failure from server

- **WHEN** JIRA responds with HTTP 401 or 403 to the search request
- **THEN** the system aborts with a message indicating credential rejection
- **AND** the response body is logged but the token value is redacted

### Requirement: Search candidate issues by JQL for a date range

The system SHALL query the JIRA REST API search endpoint with the JQL `assignee was currentUser() AND status was "In Progress" DURING ("<from>", "<to>")` to retrieve all candidate issues for the given date range. The system SHALL paginate through all result pages until the response set is exhausted. For each returned issue the system SHALL fetch at minimum `key`, `summary`, and the full changelog.

#### Scenario: Issues span multiple pages

- **WHEN** the JQL query returns more issues than fit in a single page
- **THEN** the system follows pagination and retrieves all issues across all pages
- **AND** the final candidate set contains every matching issue exactly once

#### Scenario: No matching issues in range

- **WHEN** the JQL query returns zero issues
- **THEN** the system continues without error and reports "no candidate tickets in range"

#### Scenario: JIRA returns 429 Too Many Requests

- **WHEN** a search or changelog request returns HTTP 429
- **THEN** the system honors the `Retry-After` header (or applies exponential backoff with jitter when absent) before retrying
- **AND** the request succeeds on retry once the rate limit window has elapsed

### Requirement: Reconstruct intervals from issue changelog

For each candidate issue the system SHALL parse the changelog entries for `assignee` and `status` fields to produce a sorted timeline of state transitions. From this timeline the system SHALL emit a list of disjoint intervals `[start, end]` during which the issue was simultaneously assigned to the current user AND in status `"In Progress"`. The system SHALL handle issues that enter and exit this combined state multiple times by emitting multiple intervals. Open-ended intervals (the issue is still in the active state at query time) SHALL have their `end` set to "now" in the configured timezone.

#### Scenario: Single continuous interval

- **WHEN** an issue was assigned to the user and moved to "In Progress" once, and is still in that state
- **THEN** a single interval is emitted from the transition timestamp to "now"

#### Scenario: Issue cycled through In Progress twice

- **WHEN** an issue went In Progress → Done → In Progress with the user as assignee throughout
- **THEN** two disjoint intervals are emitted, one per active period

#### Scenario: Assignee changed during In Progress

- **WHEN** an issue was In Progress with the user as assignee, then reassigned to another user, then reassigned back to the user
- **THEN** two disjoint intervals are emitted covering only the periods when both conditions held

#### Scenario: Issue never had user as assignee

- **WHEN** the changelog shows the issue was In Progress but never assigned to the current user
- **THEN** zero intervals are emitted for that issue

### Requirement: Map intervals to active days in the configured timezone

Given the reconstructed intervals for an issue, the system SHALL produce the set of calendar days on which that issue was active. A day is considered active for an issue if any of the issue's intervals intersects any moment of that day in the timezone configured by `TIMEZONE` (default `America/Mexico_City`). All day-boundary arithmetic SHALL use `zoneinfo` and never naive UTC.

#### Scenario: Interval ends just before midnight local time

- **WHEN** an interval ends at 23:59 local time on Monday
- **THEN** Monday is marked active and Tuesday is not

#### Scenario: Interval crosses midnight local time

- **WHEN** an interval starts at 22:00 local Monday and ends at 02:00 local Tuesday
- **THEN** both Monday and Tuesday are marked active

#### Scenario: Interval spans multiple full days

- **WHEN** an interval starts on Monday 10:00 local and ends on Friday 14:00 local
- **THEN** Monday, Tuesday, Wednesday, Thursday, and Friday are all marked active

### Requirement: Output a normalized day-to-tickets map

The JIRA source SHALL produce, for the requested date range, a data structure mapping each calendar day to the sorted list of issue keys active on that day, where each entry includes at minimum the issue key and the issue summary (or `None` if the summary is unavailable). This output SHALL be the sole interface between the JIRA source and the time allocator; the allocator SHALL NOT make any HTTP calls of its own.

#### Scenario: Allocator-ready output structure

- **WHEN** the JIRA source completes for a given range
- **THEN** the returned structure contains keys for every day in the range (or only days with activity, per implementation choice — but consistently)
- **AND** each ticket entry exposes `key` and `summary` fields suitable for the time allocator
