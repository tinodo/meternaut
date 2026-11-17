"""Owner hints: what the human brief may say about who is behind a resource. It is data to show to the person who reads a case, and it never goes to a model.

Two sources, and neither is a text that a model reads: the tags of the resource, limited to a closed set of tag names that conventionally say who owns something (and each value cut and
cleaned), and the Activity Log (Learn, "Activity Logs - List", `Microsoft.Insights/eventtypes/management/values`: the last 90 days, newest first), which says who made the last change.

What a hint does NOT say, and the caller of the Activity Log is personal data (an e-mail address or the object id of an application): keep it with the case, and out of logs and prompts.
* `createdBy` and `createdAt` are the caller and the time of the newest event that says that the resource itself was created: a write of the resource whose status code is 201 (Created), inside
  the window (the log keeps 90 days). A resource that is older has no creation in it, and a later update (status code 200) is a change and never a creation; so a resource that was made before
  the window names no creator, however often it was changed since. A window that was not read to its end names none either, unless it shows a creation.
* `lastChangedBy` and `lastChangedAt` are the newest successful write or delete that the log shows for the resource or for a part of it. A start or a stop is not one.
* A tag is a claim of whoever set it: it may be wrong or old.

The function that the orchestrator calls is `OwnerReader.hints`, once for each case that is opened (investigate.py::_open_case, before the case record is made); the pure functions are what a
test reads.
"""
from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata
from typing import Callable, Mapping

from .arm import Arm
from .http import HttpError, Refused
from .identity import IdentityError

OWNER_TAGS = ("owner", "contact", "team", "costcenter", "project", "environment", "createdby", "manager")  # the closed set, in the order that they are shown in
MAX_TAGS = 6  # the values of the tags that a hint holds
MAX_VALUE = 80  # the characters of the value of a tag
MAX_CALLER = 120  # the characters of the caller of an event
WINDOW_DAYS = 90  # what the Activity Log keeps
CHANGES = ("write", "delete")  # the last part of the name of an operation that changes a resource
NOT_IN_WINDOW = "not in the last 90 days"
NOT_VISIBLE = "not visible with this access"
UNAVAILABLE = "unavailable"
NOT_COMPLETE = "not read in full"
NOT_RECORDED = "not-recorded"  # what the history of a resource says of what no source says: unknown, never none
OLDER = f"over-{WINDOW_DAYS}"  # what it says of a resource that a log that was read to its end does not show in its window
RECENT_DAYS = 14
KINDS = ("person", "application", "managed-identity", "unknown")  # the kinds of identity that a change has, as words and never as the identity
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
RESOURCE = re.compile(r"/subscriptions/([0-9a-fA-F-]{36})/resourceGroups/[^/]+/providers/(.+)", re.I)
READ_ERRORS = (HttpError, Refused, IdentityError)


def clean(value: object, limit: int) -> str | None:
    """A text for a person to read: without control and format characters, whitespace squeezed to single spaces, cut to `limit` characters. None when nothing is left."""
    if not isinstance(value, str):
        return None
    text = " ".join("".join(" " if character.isspace() else character for character in value if not unicodedata.category(character).startswith("C") or character.isspace()).split())
    return text[:limit].rstrip() or None


def tag_hints(tags: Mapping | None) -> dict[str, str]:
    """The tags of a resource that conventionally say who owns it: a tag whose name is one of OWNER_TAGS (without regard to case, and to a dash, an underscore or a space in it), at most
    MAX_TAGS of them in the order of OWNER_TAGS, each value cleaned and cut to MAX_VALUE characters. A tag with no value, or a value that is not a text, is left out."""
    if not isinstance(tags, Mapping):
        return {}
    found: dict[str, str] = {}
    for name, value in tags.items():
        key = re.sub(r"[-_ ]", "", name).lower() if isinstance(name, str) else ""
        text = clean(value, MAX_VALUE)
        if key in OWNER_TAGS and text is not None and key not in found:
            found[key] = text
    return dict(list({key: found[key] for key in OWNER_TAGS if key in found}.items())[:MAX_TAGS])


def moment(value: object) -> dt.datetime | None:
    """The time of an event of the Activity Log (2026-11-05T10:11:12.3456789Z), to the second, in UTC."""
    if not isinstance(value, str) or STAMP.match(value) is None:
        return None
    try:
        return dt.datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _stamp(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _value(item: object, key: str) -> str:
    """The `value` of a field of an event that Azure gives as {value, localizedValue}."""
    field = item.get(key) if isinstance(item, Mapping) else None
    return str(field.get("value") or "") if isinstance(field, Mapping) else ""


def own_type(resource_id: str) -> str | None:
    """The type of a resource as the names of its operations have it (microsoft.compute/virtualmachines), in lower case, from its id."""
    found = RESOURCE.fullmatch(resource_id)
    if found is None:
        return None
    parts = [part for part in found.group(2).split("/") if part]
    return "/".join([parts[0], *parts[1::2]]).lower() if len(parts) >= 3 and len(parts) % 2 == 1 else None


def _writes(events: list[dict]) -> list[tuple[dt.datetime, str, dict]]:
    """The successful writes and deletes in a list of events of the Activity Log, with their time, their caller (cleaned) and the event, the newest first."""
    found = []
    for event in events:
        verb = _value(event, "operationName").lower().rpartition("/")[2]
        when, caller = moment(event.get("eventTimestamp")), clean(event.get("caller"), MAX_CALLER)
        if _value(event, "status").lower() != "succeeded" or verb not in CHANGES or when is None or caller is None:
            continue
        found.append((when, caller, event))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def changes(events: list[dict]) -> list[tuple[dt.datetime, str]]:
    """The successful writes and deletes in a list of events of the Activity Log, for the resource or a part of it: the time and the caller (cleaned), the newest first. A start, a stop, a
    read of keys and an event with no caller or no time are not changes."""
    return [(when, caller) for when, caller, _ in _writes(events)]


def _creations(events: list[dict], resource_id: str) -> list[tuple[dt.datetime, str, dict]]:
    own = own_type(resource_id)
    found = []
    for event in events:
        prefix, _, verb = _value(event, "operationName").lower().rpartition("/")
        when, caller = moment(event.get("eventTimestamp")), clean(event.get("caller"), MAX_CALLER)
        if (verb != "write" or prefix != own or _value(event, "status").lower() not in ("accepted", "succeeded") or not _value(event, "subStatus").lower().startswith("created")
                or when is None or caller is None):
            continue
        found.append((when, caller, event))
    found.sort(key=lambda item: item[0])
    return found


def creations(events: list[dict], resource_id: str) -> list[tuple[dt.datetime, str]]:
    """The events that say that the resource itself was created: a write of the resource that Azure accepted or that succeeded and whose status code is 201 (Created), with a caller and a
    time, the oldest first. A write that updated it (200) is not one: the log keeps 90 days, so the oldest write that it shows is the creation only when the log says so."""
    return [(when, caller) for when, caller, _ in _creations(events, resource_id)]


def identity_kind(event: Mapping) -> str:
    """The kind of identity that made an event of the Activity Log, as one of the words of KINDS and never the identity itself: a sign-in name has an @ (a person); a token of an application has the claim
    idtyp app, and one that a managed identity got also has the claim xms_mirid; anything else is unknown."""
    caller = event.get("caller") if isinstance(event.get("caller"), str) else ""
    claims = {str(key).rsplit("/", 1)[-1].lower(): value for key, value in (event.get("claims") if isinstance(event.get("claims"), Mapping) else {}).items()}
    return "person" if "@" in caller else "managed-identity" if "xms_mirid" in claims else "application" if claims.get("idtyp") == "app" else "unknown"


def _when(value: object) -> dt.datetime | None:
    """A time that Resource Graph gives, to the second or to the day, in UTC."""
    if isinstance(value, str) and (found := moment(value)) is not None:
        return found
    try:
        return dt.datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc) if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value) else None
    except ValueError:
        return None


def _kind_of(value: object) -> str:
    """The word for the createdByType and lastModifiedByType of systemData (User, Application, ManagedIdentity, Key): NOT_RECORDED when there is none, `unknown` for any other."""
    return NOT_RECORDED if not isinstance(value, str) or not value else {"user": "person", "application": "application", "managedidentity": "managed-identity"}.get(value.lower(), "unknown")


def history(now: dt.datetime, system: object, made: object, events: list[dict] | None, complete: bool, resource_id: str) -> dict:
    """The age and the recent history of one resource, as numbers and words only: `age_days`, `created_by` (the kind of identity), `changed_days`, `changed_by` and `written_14d`. The sources are the
    `systemData` that Resource Graph gives for some types (the kinds of identity, never the identity), a creation time among the properties, and the Activity Log (`events`, None when it was not read;
    it keeps WINDOW_DAYS days). What no source says is NOT_RECORDED, and a log that was read to its end and shows nothing in its window says that the resource is older than it (OLDER). Nothing of it is
    a verdict: a young resource is not forgotten, and says so."""
    moment_now = now.astimezone(dt.timezone.utc) if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    sd = system if isinstance(system, Mapping) else {}

    def old(when: dt.datetime) -> int:
        return max(0, (moment_now - when).days)

    read = events is not None
    writes = _writes(events or [])
    made_at, by = _when(sd.get("createdAt")), _kind_of(sd.get("createdByType"))
    if made_at is None:
        made_at, by = _when(made), NOT_RECORDED
    if made_at is None and read and (born := _creations(events or [], resource_id)):
        made_at, by = born[-1][0], identity_kind(born[-1][2])
    modified = _when(sd.get("lastModifiedAt"))
    latest = [item for item in ((writes[0][0], identity_kind(writes[0][2])) if writes else None, (modified, _kind_of(sd.get("lastModifiedByType"))) if modified else None) if item]
    last = max(latest, key=lambda item: item[0], default=None)
    seen = [stamp for event in events or [] if (stamp := moment(event.get("eventTimestamp"))) is not None]
    covered = read and (complete or bool(seen) and min(seen) <= moment_now - dt.timedelta(days=RECENT_DAYS))
    recent = last is not None and old(last[0]) <= RECENT_DAYS
    return {"age_days": old(made_at) if made_at else OLDER if read and complete else NOT_RECORDED, "created_by": by if made_at else NOT_RECORDED,
            "changed_days": old(last[0]) if last else OLDER if read and complete else NOT_RECORDED, "changed_by": last[1] if last else NOT_RECORDED,
            "written_14d": True if recent else False if covered or (modified is not None and not recent) else NOT_RECORDED}


def owner_hints(tags: Mapping | None, events: list[dict] | None, complete: bool, resource_id: str, word: str | None = None) -> dict:
    """The hint for one resource: its tags (tag_hints) and who made it and who changed it last. `events` are the events of the Activity Log of the resource, and `complete` says whether all of
    them were read; `word` says why there are none to look at (NOT_VISIBLE or UNAVAILABLE), when that is so."""
    hint: dict = {"tags": tag_hints(tags), "createdBy": None, "createdAt": None, "lastChangedBy": None, "lastChangedAt": None, "windowDays": WINDOW_DAYS, "complete": bool(complete and word is None)}
    if word is not None or events is None:
        for key in ("createdBy", "createdAt", "lastChangedBy", "lastChangedAt"):
            hint[key] = word or UNAVAILABLE
        return hint
    found = changes(events)
    if found:
        hint["lastChangedAt"], hint["lastChangedBy"] = _stamp(found[0][0]), found[0][1]
    else:
        hint["lastChangedAt"] = hint["lastChangedBy"] = NOT_IN_WINDOW
    made = creations(events, resource_id)
    if made:
        hint["createdAt"], hint["createdBy"] = _stamp(made[-1][0]), made[-1][1]  # the newest: a resource that was removed and made again was made by the last one
    else:
        hint["createdAt"] = hint["createdBy"] = NOT_IN_WINDOW if complete else NOT_COMPLETE
    return hint


class OwnerReader:
    """Reads the hints of the resources of one run: the Activity Log of each resource, once, within a count of reads and a time that the whole run shares."""

    def __init__(self, arm: Arm, now: dt.datetime, *, days: int = WINDOW_DAYS, max_pages: int = 3, max_reads: int = 30, seconds: float = 40.0,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.arm, self.now, self.days, self.max_pages, self.max_reads, self.seconds, self.monotonic = arm, now, min(days, WINDOW_DAYS), max_pages, max_reads, seconds, monotonic
        self.began: float | None = None
        self.reads = 0
        self.notes: list[str] = []
        self.shared = False  # a reader that shares what it keeps with another does not keep the answer of a read that its own budget did not allow
        self._kept: dict[str, tuple[list[dict] | None, bool, str | None]] = {}

    def _events(self, resource_id: str) -> tuple[list[dict] | None, bool, str | None]:
        key = resource_id.lower()
        if key not in self._kept:
            spent = self.shared and (self.reads >= self.max_reads or (self.began is not None and self.monotonic() - self.began >= self.seconds))
            found = self._read(resource_id)
            if spent:
                return found
            self._kept[key] = found
        return self._kept[key]

    def log(self, resource_id: str) -> tuple[list[dict] | None, bool]:
        """The events of the Activity Log of the resource as Azure gave them (None when the log was not read) and whether every page was read."""
        events, complete, _ = self._events(resource_id)
        return events, events is not None and complete

    def sharing(self, *, max_reads: int, seconds: float) -> "OwnerReader":
        """A reader with a budget of its own that keeps what it reads where this one keeps it, so that nothing is read twice and the reads of one do not use up the budget of the other."""
        other = OwnerReader(self.arm, self.now, days=self.days, max_pages=self.max_pages, max_reads=max_reads, seconds=seconds, monotonic=self.monotonic)
        other._kept, other.shared = self._kept, True
        return other

    def writes(self, resource_id: str) -> list[tuple[dt.datetime, str]] | None:
        """Every successful write and delete of the resource that the Activity Log shows (see `changes`), newest first, and None when the log was not read: an unread log shows nothing."""
        events, _, _ = self._events(resource_id)
        return None if events is None else changes(events)

    def complete(self, resource_id: str) -> bool:
        """Whether every page of the Activity Log of the resource was read: False when only part of the 90 days was read (`writes` then shows only the newest writes) and when none was."""
        events, complete, _ = self._events(resource_id)
        return events is not None and complete

    def _read(self, resource_id: str) -> tuple[list[dict] | None, bool, str | None]:
        found = RESOURCE.fullmatch(resource_id)
        if found is None:
            return None, False, UNAVAILABLE
        if self.began is None:
            self.began = self.monotonic()
        if self.reads >= self.max_reads or self.monotonic() - self.began >= self.seconds:
            self.notes.append("the Activity Log of some resources was not read: the reads of one run for owner hints were used up")
            return None, False, UNAVAILABLE
        self.reads += 1
        moment_now = self.now if self.now.tzinfo else self.now.replace(tzinfo=dt.timezone.utc)
        try:
            events, complete = self.arm.activity_events(found.group(1).lower(), moment_now - dt.timedelta(days=self.days), moment_now, resource_id=resource_id, max_pages=self.max_pages)
        except READ_ERRORS as error:
            self.notes.append(f"the Activity Log of a resource could not be read ({str(error)[:160]})")
            return None, False, NOT_VISIBLE if getattr(error, "status", None) in (401, 403) else UNAVAILABLE
        return events, complete, None

    def hints(self, resource_id: str, tags: Mapping | None = None) -> dict:
        """The hint of one resource (see owner_hints). It never raises for a read that fails: the fields then say why they are empty."""
        events, complete, word = self._events(resource_id)
        return owner_hints(tags, events, complete, resource_id, word)
