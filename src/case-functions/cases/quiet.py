"""Quiet hours: a window of the day in which nothing is sent to a person.

A person sets two times (`SettingsRecord.quiet_from` and `quiet_to`, as HH:MM) and a time zone. From the first until the second, by the clock of that zone, Meternaut sends the person
nothing on its own: no letter and no Teams card. What was due waits, and is sent when the window ends (the timer offers it again; the letters and the cards that wait are not lost and are
never sent twice, because a letter that was sent is never sent again). There is no way around it: nothing that Meternaut sends is urgent (AGENTS.md rule 13), so no letter, whatever its kind,
and no request, however long it has waited, is sent inside a person's quiet hours.

Without both times there is no window (the default). The window may cross midnight (22:00 to 07:00): the start is inside it and the end is not. Two equal times are no window. The zone is the one
of the person's settings; a zone that is empty, or that this machine does not know, is UTC. Nothing here reads a clock, a store or the network: the caller passes the settings and the time.
"""
from __future__ import annotations

import datetime as dt
import re
import zoneinfo

from .models import SettingsRecord

HOURS = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
WAITING = "Quiet hours: this waits until they end, and is sent then."  # what the record of a letter that was held for them says: the timer looks for exactly this text


def zone_for(name: object) -> dt.tzinfo:
    """The time zone of a stored name: UTC for no name, for UTC and for a name that this machine does not know."""
    text = str(name or "").strip()
    if not text or text.upper() == "UTC":
        return dt.timezone.utc
    try:
        return zoneinfo.ZoneInfo(text)
    except Exception:  # noqa: BLE001 (not known, not readable or a directory: a person's own word is never a reason to fail)
        return dt.timezone.utc


def window(settings: SettingsRecord) -> tuple[dt.time, dt.time] | None:
    """The window as two times of the day, or None: no time, only one, a time that is not HH:MM, or the same time twice."""
    start, end = (settings.quiet_from or "").strip(), (settings.quiet_to or "").strip()
    if not (HOURS.fullmatch(start) and HOURS.fullmatch(end)) or start == end:
        return None
    return dt.time.fromisoformat(start), dt.time.fromisoformat(end)


def _local(now: dt.datetime, settings: SettingsRecord) -> dt.datetime:
    moment = now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now
    return moment.astimezone(zone_for(settings.timezone))


def inside(settings: SettingsRecord, now: dt.datetime) -> bool:
    """Whether `now` is inside the person's quiet hours: the wall clock of the person's zone is at or after the start and before the end (or, for a window across midnight, at or after the
    start or before the end)."""
    found = window(settings)
    if found is None:
        return False
    start, end = found
    clock = _local(now, settings).time()
    return start <= clock < end if start < end else (clock >= start or clock < end)


def last_end(settings: SettingsRecord, now: dt.datetime) -> dt.datetime | None:
    """The latest time, not after `now`, at which the person's quiet hours ended (in UTC); None when there is no window or `now` is inside it. A card that waited for the end of the hours has its
    first twenty minutes counted from here, so that the letter does not overtake it."""
    found = window(settings)
    if found is None or inside(settings, now):
        return None
    local = _local(now, settings)
    end = dt.datetime.combine(local.date(), found[1], tzinfo=local.tzinfo)
    if end > local:
        end = dt.datetime.combine(local.date() - dt.timedelta(days=1), found[1], tzinfo=local.tzinfo)
    return end.astimezone(dt.timezone.utc)
