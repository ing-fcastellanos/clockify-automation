## ADDED Requirements

### Requirement: Pure function with no I/O

The time allocator SHALL be implemented as a pure function (or pure class) that performs no network or file system I/O. It SHALL accept its inputs as in-memory data structures and return its outputs as in-memory data structures, enabling deterministic unit testing without mocks for HTTP, time, or file access.

#### Scenario: No external dependencies invoked

- **WHEN** the allocator is exercised in unit tests
- **THEN** no HTTP client, file reader, or system clock dependency is required
- **AND** the same input always produces the same output

### Requirement: Filter range to working days excluding weekends and holidays

Given a date range `[from, to]` (inclusive), a list of holidays, and a working-days configuration (default Monday through Friday), the allocator SHALL produce the set of working days in the range, excluding weekends and any date listed in the holidays input. The holidays input SHALL be a list of ISO-format dates (`YYYY-MM-DD`) interpreted in the configured timezone.

#### Scenario: Range crosses a weekend

- **WHEN** the range is Friday 2026-04-24 to Monday 2026-04-27 with no holidays
- **THEN** the working days are exactly `[2026-04-24, 2026-04-27]`
- **AND** Saturday and Sunday are excluded

#### Scenario: Range contains a holiday

- **WHEN** the range is `[2026-05-01, 2026-05-05]` and holidays contains `2026-05-01`
- **THEN** the working days are `[2026-05-04, 2026-05-05]` (assuming 2026-05-01 is Friday and 2026-05-02..03 are weekend)
- **AND** the holiday date is excluded

### Requirement: Allocate hours per day using base-plus-remainder algorithm

For each working day with N active tickets (1 ≤ N ≤ 8), the allocator SHALL compute `base = 8 // N` and `remainder = 8 - base * N`. With tickets sorted alphabetically by issue key, the first `remainder` tickets SHALL each receive `base + 1` whole hours and the rest SHALL each receive `base` whole hours. All allocated hours per day SHALL sum to exactly 8.

#### Scenario: N divides 8 evenly

- **WHEN** a day has 4 active tickets [A-1, A-2, B-1, C-1]
- **THEN** each ticket receives exactly 2 hours
- **AND** total is 8 hours

#### Scenario: N does not divide 8

- **WHEN** a day has 3 active tickets [A-1, B-1, C-1]
- **THEN** A-1 receives 3 hours, B-1 receives 3 hours, C-1 receives 2 hours
- **AND** total is 8 hours

#### Scenario: Many tickets in a day

- **WHEN** a day has 7 active tickets
- **THEN** the alphabetically-first ticket receives 2 hours and the remaining 6 each receive 1 hour
- **AND** total is 8 hours

### Requirement: Handle days with more than 8 tickets by skipping excess alphabetically

When a working day has N > 8 active tickets, the allocator SHALL allocate 1 hour each to the alphabetically-first 8 tickets and SHALL skip the remaining `N - 8` tickets. The skipped ticket keys SHALL be included in the allocator's output as a `skipped` collection so the orchestrator can warn the user.

#### Scenario: 10 tickets active in a single day

- **WHEN** a day has 10 active tickets [A-1..A-10]
- **THEN** A-1 through A-8 each receive 1 hour and A-9, A-10 are skipped
- **AND** the day's allocated hours sum to exactly 8
- **AND** the output reports `skipped = [A-9, A-10]` for that day

### Requirement: Handle days with zero active tickets by skipping the day

When a working day has zero active tickets, the allocator SHALL produce no entries for that day. The day SHALL be reported in an `empty_days` collection in the output so the orchestrator can warn the user.

#### Scenario: A working day has no tickets active

- **WHEN** a Tuesday in the range has no tickets active
- **THEN** no time entries are produced for that Tuesday
- **AND** that Tuesday is included in `empty_days`
- **AND** the run does not error

### Requirement: Generate contiguous one-hour blocks starting at 09:00

For each day with allocations the allocator SHALL emit time-block records `(ticket_key, start_datetime, end_datetime)` placing the first ticket's block at 09:00 local time and chaining each subsequent block end-to-end with no gaps. Each block's duration SHALL be a whole number of hours equal to that ticket's allocated hours, and the last block's end time SHALL be 17:00 local time (when 8 hours total are allocated). The configured timezone SHALL be applied to all start/end datetimes.

#### Scenario: 4 equal blocks of 2 hours

- **WHEN** a day allocates 2h each to [A-1, A-2, B-1, C-1]
- **THEN** the blocks are A-1 09:00–11:00, A-2 11:00–13:00, B-1 13:00–15:00, C-1 15:00–17:00 local time
- **AND** there are no gaps between blocks

#### Scenario: Uneven allocation [3, 3, 2]

- **WHEN** a day allocates [3, 3, 2] to [A-1, B-1, C-1]
- **THEN** the blocks are A-1 09:00–12:00, B-1 12:00–15:00, C-1 15:00–17:00 local time

### Requirement: Determinism across runs with the same input

Given identical inputs (range, holidays, day-to-tickets map, configuration), the allocator SHALL produce identical output. The ordering of blocks within a day SHALL always be alphabetical by issue key, and the assignment of the "+1 hour" extras SHALL always favor the alphabetically-earliest tickets.

#### Scenario: Same input run twice

- **WHEN** the allocator is invoked twice with the exact same inputs
- **THEN** both invocations produce byte-identical block records
