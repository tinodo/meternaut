"""The shared parts of the pages: the request and the response, what a page needs from the rest of the app, and the helpers for text, times and money.

The standard library only. A page is built from `Safe` text: a value is escaped when it is put into a page, and only text that this package built
is `Safe`. Nothing here reads a person from a form or a link: the person comes from the headers that the platform's sign-in adds.
"""
from __future__ import annotations

import datetime as dt
import html
import math
import re
import zoneinfo
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlsplit

from ..brief import visible
from ..models import TIME_FORMAT, Decider, Delegate, Principal, Store
from ..people import People

MAX_BODY = 16 * 1024
MAX_FIELDS = 60
MAX_NOTE = 300
MAX_REASON = 200
FORM_TYPE = "application/x-www-form-urlencoded"
FORM_SECONDS = 6 * 3600
ID = r"[A-Za-z0-9_.-]{1,80}"
# When the Watch looks every day, in UTC (hour and minute): the daily timer of function_app.py, "0 30 5 * * *". A test holds the two together.
WATCH_AT = (5, 30)

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Characters that hide text or change its order on the screen.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\u2066\u2067\u2068\u2069\u061c\ufeff"), None)


@dataclass(frozen=True)
class Request:
    """One request, read once. `headers` has lower-case names. `problem` is empty, `too_large` (the body is over 16 KB) or `bad_form`."""

    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    form: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    problem: str = ""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8")


@dataclass(frozen=True)
class Services:
    """What the pages need from the rest of the app.

    `host` is the public host name (for the address that a page names). `acts_on` says in plain words the one change that the code makes, with the approver's own
    token. `delegate` takes an approval through the person's sign-in to Azure. `models` are the names of the AI models, for the AI line. `base` is the path in
    front of the console, when the platform adds one (for example `/api`): links carry it and incoming paths lose it.
    """

    store: Store
    decider: Decider
    delegate: Delegate
    people: People
    now: Callable[[], dt.datetime]
    host: str
    acts_on: str
    models: tuple[str, ...] = ()
    base: str = ""


class Safe(str):
    """HTML that this package built. Every dynamic part of it was escaped when it was put in."""

    __slots__ = ()


def esc(value: object) -> Safe:
    """The value as escaped HTML text (and attribute text). `Safe` text passes through; everything else is stripped of the characters that hide text or change its order
    (brief.visible) and escaped: the one place where every page puts text of the estate, of a person or of a model."""
    if isinstance(value, Safe):
        return value
    return Safe(html.escape(visible(value), quote=True))


def fmt(template: str, **values: object) -> Safe:
    """Fills the named places of a trusted HTML template. Each value is escaped unless it is `Safe`."""
    return Safe(template.format(**{name: esc(value) for name, value in values.items()}))


def join(parts: Iterable[object], separator: str = "") -> Safe:
    return Safe(separator.join(esc(part) for part in parts))


def clean_line(value: object) -> str:
    """One line of plain text: control characters become spaces, characters that hide or reorder text are dropped, runs of spaces become one."""
    text = "" if value is None else str(value)
    return " ".join(_CONTROLS.sub(" ", text).translate(_INVISIBLE).split())


def _pairs(text: str) -> dict[str, str]:
    """Names and values of a query or a form. A name that comes more than once (check boxes) has its values joined with commas."""
    found: dict[str, list[str]] = {}
    for name, value in parse_qsl(text, keep_blank_values=True, max_num_fields=MAX_FIELDS):
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", name):
            found.setdefault(name, []).append(clean_line(value))
    return {name: ",".join(values) for name, values in found.items()}


def parse_request(method: str, url: str, headers: Mapping[str, str] | None, body: bytes | str | None) -> Request:
    """Reads a request. It never raises: a body over 16 KB or a form that cannot be read is marked in `problem` and the page refuses it."""
    parts = urlsplit(str(url or "/"))
    lowered = {str(name).lower(): str(value) for name, value in (headers or {}).items()}
    raw = body.encode("utf-8") if isinstance(body, str) else bytes(body or b"")
    problem, query, form = "", {}, {}
    try:
        query = _pairs(parts.query)
    except ValueError:
        problem = "bad_form"
    if len(raw) > MAX_BODY:
        return Request(str(method).upper(), parts.path or "/", query, lowered, {}, b"", "too_large")
    if raw and lowered.get("content-type", "").split(";")[0].strip().lower() == FORM_TYPE:
        try:
            form = _pairs(raw.decode("utf-8", "replace"))
        except ValueError:
            problem = "bad_form"
    return Request(str(method).upper(), parts.path or "/", query, lowered, form, raw, problem)


# -- times ---------------------------------------------------------------------------------------------------------------------------------------

def utc(moment: dt.datetime) -> dt.datetime:
    return moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)


def stamp(moment: dt.datetime) -> str:
    return utc(moment).strftime(TIME_FORMAT)


def parse_time(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return utc(value)
    try:
        return dt.datetime.strptime(str(value), TIME_FORMAT).replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


ZONE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{0,40}(?:/[A-Za-z0-9_+-]{1,40}){0,2}")
# What is accepted as a time zone when the machine has no time zone database.
FALLBACK_ZONES = ("UTC", "Europe/Amsterdam", "Europe/Berlin", "Europe/Brussels", "Europe/Dublin", "Europe/Lisbon", "Europe/London", "Europe/Madrid",
                  "Europe/Paris", "Europe/Rome", "Europe/Stockholm", "Europe/Warsaw", "America/New_York", "America/Chicago", "America/Denver",
                  "America/Los_Angeles", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney")


@lru_cache(maxsize=1)
def zone_index() -> dict[str, str]:
    """Lower-case name to the name as the time zone database spells it."""
    try:
        names = set(zoneinfo.available_timezones())
    except Exception:  # noqa: BLE001 (a machine with no time zone database)
        names = set()
    return {name.lower(): name for name in (names or set(FALLBACK_ZONES))}


def canonical_zone(name: object) -> str | None:
    """The spelling of a time zone name that is known here, or None."""
    text = clean_line(name)
    return zone_index().get(text.lower()) if ZONE_NAME.fullmatch(text) else None


def zone_of(name: object) -> dt.tzinfo | None:
    """The time zone of a stored name, or None when this machine does not know it: a time is then shown in UTC only."""
    text = clean_line(name)
    if text.upper() == "UTC":
        return dt.timezone.utc
    if not ZONE_NAME.fullmatch(text):
        return None
    try:
        return zoneinfo.ZoneInfo(text)
    except Exception:  # noqa: BLE001 (not known, not readable or a directory)
        return None


def short_date(moment: dt.datetime) -> str:
    return f"{DAYS[moment.weekday()][:3]} {moment.day} {MONTHS[moment.month - 1]} {moment.year}"


def time_text(moment: dt.datetime, zone: dt.tzinfo | None) -> str:
    """`Thu 5 Nov 2026 09:00 UTC (10:00 CET)`. The second part appears when the person's time zone is known and is not UTC."""
    moment = utc(moment)
    text = f"{short_date(moment)} {moment:%H:%M} UTC"
    if zone is None:
        return text
    local = moment.astimezone(zone)
    if local.utcoffset() == dt.timedelta(0) and (local.tzname() or "") in ("UTC", "GMT"):
        return text
    label = local.tzname() or str(getattr(zone, "key", "local time"))
    day = f"{short_date(local)} " if local.date() != moment.date() else ""
    return f"{text} ({day}{local:%H:%M} {label})"


def usd(value: object) -> str:
    """Money as the records hold it: US dollars."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "not known"
    return f"{value:,.2f} US dollars"


def number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return ""
    return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"


def link_part(value: str) -> str:
    """One piece of a path, made safe for an address."""
    return quote(value, safe="")


@dataclass
class Ctx:
    """One request as a page sees it: who signed in, what time it is, and the helpers that depend on both."""

    request: Request
    services: Services
    principal: Principal | None
    now: dt.datetime
    _zone: object = field(default=None, init=False, repr=False)
    _zone_read: bool = field(default=False, init=False, repr=False)

    @property
    def store(self) -> Store:
        return self.services.store

    def url(self, path: str) -> str:
        return f"{self.services.base.rstrip('/')}{path}"

    def zone(self) -> dt.tzinfo | None:
        """The signed-in person's time zone as stored in their settings, or None."""
        if not self._zone_read:
            self._zone_read = True
            try:
                self._zone = zone_of(self.store.settings_get(self.principal.oid).timezone) if self.principal else None
            except Exception:  # noqa: BLE001 (a page is shown in UTC when the settings cannot be read)
                self._zone = None
        return self._zone  # type: ignore[return-value]

    def when(self, value: object, empty: str = "not set") -> Safe:
        """A time as `<time>` text: UTC, and the person's own time zone where it is known."""
        moment = parse_time(value)
        if moment is None:
            return esc(clean_line(value) or empty)
        return fmt('<time datetime="{iso}">{text}</time>', iso=stamp(moment), text=time_text(moment, self.zone()))

    def day(self, value: object, empty: str = "not set") -> Safe:
        """A day as `<time>` text in the person's own time zone, where it is known (else in UTC): `Thu 5 Nov`."""
        moment = parse_time(value)
        if moment is None:
            return esc(clean_line(value) or empty)
        zone = self.zone()
        shown = moment.astimezone(zone) if zone is not None else moment
        return fmt('<time datetime="{iso}">{text}</time>', iso=stamp(moment), text=f"{DAYS[shown.weekday()][:3]} {shown.day} {MONTHS[shown.month - 1]}")

    def day_key(self, value: object) -> str:
        """The calendar day of a time in the person's own time zone, as YYYY-MM-DD, for grouping a list by day. Empty for a time that cannot be read."""
        moment = parse_time(value)
        if moment is None:
            return ""
        zone = self.zone()
        return (moment.astimezone(zone) if zone is not None else moment).date().isoformat()

    def next_search(self) -> str:
        """When the Watch looks next, as a person reads it: `at 06:30` in the person's own time zone, `tomorrow at 06:30` when that is the next day there."""
        now = utc(self.now)
        at = now.replace(hour=WATCH_AT[0], minute=WATCH_AT[1], second=0, microsecond=0)
        if at <= now:
            at += dt.timedelta(days=1)
        zone = self.zone()
        if zone is None or zone is dt.timezone.utc:
            return f"at {at:%H:%M} UTC" if at.date() == now.date() else f"tomorrow at {at:%H:%M} UTC"
        local = at.astimezone(zone)
        return f"at {local:%H:%M}" if local.date() == now.astimezone(zone).date() else f"tomorrow at {local:%H:%M}"

    def nonce(self, purpose: str, seconds: int = FORM_SECONDS) -> str:
        """A one-time token for a form: for this person and this purpose only."""
        return self.store.nonce_new(self.principal.oid, purpose, seconds)  # type: ignore[union-attr]
