"""Derive the sync range from the current state of Clockify.

Automatic mode answers "fill me in from where I left off". The last day the user
touched Clockify is the frontier; the range runs from the day after it up to
today. Clockify itself is the source of truth — a local state file would lie the
moment the user adds or deletes an entry from the web UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from clockify_automation.clockify.client import (
    list_user_entries,
    make_clockify_client,
    resolve_user_id,
)
from clockify_automation.clockify.sink import entry_local_date, to_utc_iso8601_z
from clockify_automation.config import Settings

logger = logging.getLogger(__name__)

# The derived range is `last_entry_date + 1 .. today`, so a lookback window of
# MAX_RANGE_DAYS + 1 is exactly what makes the 20-day cap unreachable. The window
# IS the guard: no separate size check is needed.
MAX_RANGE_DAYS = 20
LOOKBACK_DAYS = MAX_RANGE_DAYS + 1


@dataclass(frozen=True)
class AutomaticRange:
    last_entry_date: date
    from_date: date
    to_date: date


class NoRecentEntriesError(RuntimeError):
    pass


def find_last_entry_date(
    settings: Settings,
    today: date,
    lookback_days: int = LOOKBACK_DAYS,
) -> date | None:
    """Latest local day with ANY user entry within the lookback window.

    Deliberately unfiltered: an entry in another project, with another tag, or
    with a hand-written description still marks its day as covered. The goal is a
    calendar without holes, not automation ownership.
    """
    # lookback_days - 1: the window spans lookback_days calendar days *including*
    # today, so the oldest resolvable day yields a range of exactly MAX_RANGE_DAYS.
    window_start = datetime.combine(
        today - timedelta(days=lookback_days - 1), datetime.min.time(), tzinfo=settings.timezone
    )
    window_end = datetime.combine(
        today, datetime.max.time().replace(microsecond=0), tzinfo=settings.timezone
    )

    with make_clockify_client(settings.clockify_api_key) as client:
        user_id = settings.clockify_user_id or resolve_user_id(client)
        entries = list_user_entries(
            client,
            settings.clockify_workspace_id,
            user_id,
            to_utc_iso8601_z(window_start),
            to_utc_iso8601_z(window_end),
        )
        days = {d for entry in entries if (d := entry_local_date(entry, settings.timezone_name))}

    if not days:
        return None
    return max(days)


def resolve_automatic_range(
    settings: Settings,
    today: date | None = None,
    lookback_days: int = LOOKBACK_DAYS,
) -> AutomaticRange | None:
    """Range to sync, or None when Clockify is already current.

    Raises NoRecentEntriesError when the window holds no entry at all — the user
    has to supply --from/--to explicitly rather than have the tool guess.
    """
    if today is None:
        today = datetime.now(tz=settings.timezone).date()

    last = find_last_entry_date(settings, today, lookback_days)
    if last is None:
        raise NoRecentEntriesError(
            f"No Clockify entries found in the last {lookback_days} days "
            f"(searched {(today - timedelta(days=lookback_days - 1)).isoformat()} "
            f"through {today.isoformat()}). "
            f"Automatic mode cannot derive a range; re-run with --from and --to."
        )

    logger.debug("last day with Clockify entries: %s", last.isoformat())
    if last >= today:
        return None

    return AutomaticRange(
        last_entry_date=last,
        from_date=last + timedelta(days=1),
        to_date=today,
    )
