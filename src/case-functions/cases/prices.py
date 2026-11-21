"""What Azure's public price list says about the prices of one service in one region, read for the tool that shows alternatives (price_alternatives in cases/toolbox.py).

The one call is a GET of the list with no token (http.PRICE_CALL). Its address is made from typed words only: a service, a region, a product and the currency, each a word of the platform that
passed a check before it got here, and never a name, a tag or an id of an estate. What comes back is read into typed numbers and short words: a text of the list is kept only when it is no longer than
a word of the platform, and the tool shows it through the same check as every other word of a meter. Only pay-as-you-go prices are read, in US dollars, and a price that has several steps is marked so
and is never taken for the price of the whole quantity. A price that holds in every region the list writes with the region Global or with no region: both are Global here. A read has a cap of pages, of
lines, of the length of a page and of time (a try of a page takes at most ATTEMPT seconds and never more than the time that is left), and says when a cap or a failure ended it. The list
limits the requests of one address (it says so in its headers: ten in a window of 60 seconds was what it showed), so a read waits once for as long as the list asks when a call can afford it, and
the Hold of a run keeps what it asked for that was not waited for. What a read of the whole list gave can be kept by the store (the book: pack and unpack make its text). Standard library only: the
client is the one of the Watch.
"""
from __future__ import annotations

import base64
import json
import math
import re
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable, Sequence
from urllib.parse import quote, urlsplit

from .http import PRICES_HOST, PRICES_PATH, RETRY_STATUSES, Client, HttpError, Response

API_VERSION = "2023-01-01-preview"
CURRENCY = "USD"
GLOBAL = "Global"  # how the list names the region of a price that holds in every region (it also writes such a price with no region: see _keep)
MAX_PAGES = 5  # pages of one read; the list gives 1,000 lines a page
MAX_LINES = 6000  # prices that one read keeps
MAX_HELD = 20000  # prices that the reads of one run keep in all
MAX_TEXT = 100  # characters of a text of the list that are kept: a longer one is no word of the platform
MAX_PAGE_LENGTH = 3_000_000  # the longest answer for a page that is read, as it comes: a page of 1,000 lines is about 600,000 long
ATTEMPT = 8.0  # seconds that one try of one page may take
SECONDS = 24.0  # what one read may take in all, not counting a wait that the list asked for (a call of the toolbox may take 45)
WAIT = 20.0  # the longest wait that a call takes when the list asks for one: the 24 seconds of a read and one such wait are 44, which fit in the 45 of a call. The list asked for 60 in the one answer that was read: a call does not wait so long
MAX_UNPACKED = 4_000_000  # the most that a copy of the book may unpack to, in characters: 6,000 lines are about 600,000
FRESH_DAYS = 10  # a copy of a read in the price book answers like a read of the list while it is younger than this. The investigation runs every INVESTIGATE_EVERY_DAYS (7: cases/config.py), so a copy of 3 days is always stale at the next run and every run would pay for the warm-up; a list price changes rarely, and the limit of the list is for the reads that cannot be spared
STALE_DAYS = 45  # when the list cannot be read, a copy younger than this is shown with its age: a list price that may have moved since, and never what the bill paid (that is `rate_ratio`, from the bill)
MAX_ASKED = 86_400.0  # the longest wait that a list can be taken to ask for, a day: a Retry-After that is no number, is not finite, is below nothing or is above this asks for nothing that a run can take or hold, and is read as no wait asked
USER_AGENT = "Meternaut-Watch/1 (reads the public price list)"
WORDS = re.compile(r"[A-Za-z0-9.&()/:+-]+(?: [A-Za-z0-9.&()/:+-]+){0,9}")
REGION = re.compile(r"[a-z0-9]{1,24}")


@dataclass
class Hold:
    """What a run has learned of the limit of the list, kept for one run by whoever holds the run's state (the toolbox): `until` is the time, on the clock of the reads, before which the list is not asked
    again because it asked to wait and the wait was not taken, and `paused` the addresses (the first page of a read) that a wait was taken for: a read waits once for an address and never twice."""

    until: float = 0.0
    paused: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Line:
    """One price of the list: the service, the product, the SKU and the meter as the list names them, the unit of measure, the price of one unit in US dollars, the region as the list names it, and how many
    price steps the meter has (1 for one price: the price is then that of every unit)."""

    service: str
    product: str
    sku: str
    meter: str
    unit: str
    usd: float
    region: str  # `Global` for a price that holds in every region
    tiers: int


@dataclass(frozen=True)
class Book:
    lines: tuple[Line, ...]
    complete: bool  # False when a cap of pages, of lines or of time, or a failure, ended the read
    error: HttpError | None = None  # the failure that ended the read after a page that was read: the lines are those of the pages before it
    source: str = "list"  # `list` for a read of the price list, `book` for a copy that the store kept of an earlier read
    age: int | None = None  # for a copy: how many whole days old it is

    @property
    def aged(self) -> int | None:
        """How many whole days old a copy of the book is when it is at least a day old, which is what the owner is told of a price that may have moved since; None for a read of the list (it has no age) and
        for a copy of today."""
        return self.age if self.age is not None and self.age >= 1 else None


def region_of(word: object) -> str | None:
    """The region as the list names it: the lower-case word that Azure gives, and `Global` for the word global."""
    return (GLOBAL if word == "global" else word) if isinstance(word, str) and REGION.fullmatch(word) else None


def address(service: str, region: str, product: str | None) -> str:
    """The address of the first page: the prices of a service that hold in a region or in every region (the list writes the region of such a price as Global or leaves it empty), and of one product
    of it when there is one."""
    for word in (service, product or "x"):
        if not WORDS.fullmatch(word):
            raise ValueError("a word that is not made of letters, digits and the marks of a platform name")
    if not REGION.fullmatch(region) and region != GLOBAL:
        raise ValueError("a region that is not a region word")
    everywhere = f"armRegionName eq '{GLOBAL}' or armRegionName eq ''"
    condition = f"serviceName eq '{service}' and priceType eq 'Consumption' and (" + (everywhere if region == GLOBAL else f"armRegionName eq '{region}' or {everywhere}") + ")"
    if product:
        condition += f" and productName eq '{product}'"
    return f"https://{PRICES_HOST}{PRICES_PATH}?api-version={API_VERSION}&currencyCode='{CURRENCY}'&$filter={quote(condition, safe='')}"


def _bad(what: str, code: str = "") -> HttpError:
    return HttpError(200, f"the price list {what}", code=code)


def _next(link: object) -> str:
    """The next page, as the list gives it (it writes the port 443 into the address): on the host and the path of the list and no other, and made again without the port."""
    try:
        parts = urlsplit(str(link))
        port = parts.port
    except ValueError:
        raise _bad("gave a next page that the app does not follow") from None
    if parts.scheme != "https" or "@" in parts.netloc or parts.hostname != PRICES_HOST or port not in (None, 443) or parts.path != PRICES_PATH:
        raise _bad("gave a next page that the app does not follow")
    return f"https://{PRICES_HOST}{PRICES_PATH}?{parts.query}"


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _keep(found: dict, item: object, service: str, regions: frozenset) -> None:
    """One line of a page: kept when it is a pay-as-you-go price in dollars of the service that was asked for, in a region that was asked for (a line with no region holds in every region), with
    words of the length of a platform's, as the price of its first step and the steps that it has. The filter of the address is the list's to keep; a line of another service or region is not priced."""
    if not isinstance(item, dict) or item.get("type") != "Consumption" or item.get("currencyCode") != CURRENCY or item.get("serviceName") != service:
        return
    region = item.get("armRegionName")
    texts = (*(item.get(name) for name in ("productName", "skuName", "meterName", "unitOfMeasure")), GLOBAL if region == "" else region)
    price, tier = _number(item.get("retailPrice")), _number(item.get("tierMinimumUnits"))
    if price is not None and tier is not None and all(isinstance(text, str) and 0 < len(text) <= MAX_TEXT for text in texts) and texts[4] in regions:
        found.setdefault(texts, {}).setdefault(tier, set()).add(price)


def _seconds(wait: float) -> str:
    seconds = math.ceil(wait)
    return f"{seconds} second{'' if seconds == 1 else 's'}"


def _asked(failure: HttpError) -> float | None:
    """The wait that a 429 asks for, in seconds, or None when it asks for none. A number that is not finite (inf, nan: the comparison is false for both), below nothing or above MAX_ASKED is read as no wait
    asked, so that it is never slept for, never held for and never said."""
    wait = failure.retry_after if failure.status == 429 else None
    return float(wait) if isinstance(wait, (int, float)) and 0 <= wait <= MAX_ASKED else None


def _said(failure: HttpError, asked: float | None) -> HttpError:
    """A failure of a try as the run says it: a 429 says what the list asked for (`asked`: _asked), with the code 429 when the body has no code word of its own, and never the address or a header; any
    other failure is as the client made it."""
    if failure.status != 429:
        return failure
    words = f"asked to wait {_seconds(asked)} (429)" if asked is not None else "answered 429 and gave no time to wait"
    return HttpError(429, f"the price list {words}", asked, code=failure.code or "429")


def read(client: Client, service: str, region: str, product: str | None, monotonic: Callable[[], float] = time.monotonic, seconds: float = SECONDS, hold: Hold | None = None,
         room: float = WAIT, tell: Callable[[int, float, float | None], None] | None = None, gap: float = 0.0) -> Book:
    """The prices of a service in a region, and of one product of it when there is one, read a page at a time up to the caps and never for longer than `seconds`: a try takes at most ATTEMPT seconds
    (the timeout of one socket operation, so a host that sends one byte at a time can take longer: the time is checked between pages) and at most the time that is left, a host that gives no answer is
    tried once, and a second try of a page (for a list that is busy or fails) is made only when the time that is left holds it. A list that answers 429 with the seconds to wait is waited for once, when
    that is at most `room` (the longest wait that the caller can afford: WAIT for a call of the toolbox): the wait is not a part of `seconds`, and a read waits once for its address in a run, whatever
    its pages say (`hold.paused`). A wait that is not taken ends the read, says what the list asked for, and holds the list for that time in `hold`: no read of the run goes to it before. `tell` is
    given the status (0 for no answer), the seconds and the wait that the list asked for, of each try that reaches the list. `gap` is the least pause between two requests of the read, a second try
    and the next page, whatever the list asked or did not ask (the warm-up keeps the pace that the list showed). The transport reads at most MAX_PAGE_LENGTH + 1 of a page, so a page
    cannot fill the memory, and a longer one is refused with the code word TooLarge. Raises HttpError when the first page cannot be read: a call that failed, an answer that is not the list, a page
    that is too large or a next page somewhere else. A failure after a page that was read ends the read there: the book holds what was read, is not complete and has the failure. A price that the list
    gives twice with two values is left out, and so is a price of nothing: it is no price of any alternative."""
    found: dict = {}
    first = url = address(service, region, product)
    hold = Hold() if hold is None else hold
    regions = frozenset((GLOBAL,) if region == GLOBAL else (region, GLOBAL))
    stop, pages, error = monotonic() + seconds, 0, None

    def get(page: str, now: float) -> Response:
        nonlocal stop
        tried = False
        while True:
            if not tried and hold.until > now:
                raise HttpError(429, f"the price list asked to wait, and {_seconds(hold.until - now)} of it are left (429)", hold.until - now, code="429")
            try:
                response = client.request("GET", page, headers={"User-Agent": USER_AGENT}, timeout=min(ATTEMPT, stop - now), retries=0, retry_network=False, limit=MAX_PAGE_LENGTH + 1)
            except HttpError as failure:
                asked = _asked(failure)
                if tell:
                    tell(failure.status, monotonic() - now, asked)
                pause = max(gap, asked if asked is not None else 1.0 + client.jitter())
                left = stop - monotonic() - (0.0 if asked is not None else pause)
                if tried or failure.status not in RETRY_STATUSES or first in hold.paused or left < 1.0 or (asked is not None and asked > room):
                    if asked is not None:
                        hold.until = max(hold.until, monotonic() + asked)
                    raise _said(failure, asked) from None
                client.sleep(pause)
                if asked is not None:
                    stop += pause
                    hold.paused.add(first)
                tried, now = True, monotonic()
                continue
            if tell:
                tell(response.status, monotonic() - now, None)
            return response

    while url and pages < MAX_PAGES and len(found) < MAX_LINES:
        now = monotonic()
        pause = gap if pages else 0.0
        if stop - now - pause < 1.0:
            break
        if pause:
            client.sleep(pause)
            now = monotonic()
        try:
            response = get(url, now)
            if len(response.body) > MAX_PAGE_LENGTH:
                raise _bad("gave a page that is too large to read", "TooLarge")
            data = response.json()
            items = data.get("Items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise _bad("gave an answer that the app does not understand")
            following = _next(data["NextPageLink"]) if data.get("NextPageLink") else None
        except HttpError as failure:
            if not pages:
                raise
            error = failure
            break
        for item in items:
            _keep(found, item, service, regions)
        pages += 1
        url = following
    lines = tuple(Line(service, *texts[:4], price, texts[4], len(steps)) for texts, steps in found.items() if 0 in steps and len(steps[0]) == 1 and (price := next(iter(steps[0]))) > 0)
    return Book(lines[:MAX_LINES], url is None and len(lines) <= MAX_LINES, error)


def pack(lines: Sequence[Line]) -> str:
    """The lines of a read as the text that the book keeps: the compact JSON of what differs from line to line (the service is the key of the copy), deflated and written in base64. A product of some
    dozens of lines is some hundreds of characters, and the store keeps a record of 30,000 characters at most."""
    rows = [[line.product, line.sku, line.meter, line.unit, line.usd, line.region, line.tiers] for line in lines]
    return base64.b64encode(zlib.compress(json.dumps(rows, separators=(",", ":")).encode("utf-8"), 9)).decode("ascii")


def _valid(line: Line) -> bool:
    return (all(isinstance(word, str) and 0 < len(word) <= MAX_TEXT for word in (line.product, line.sku, line.meter, line.unit)) and isinstance(line.region, str)
            and (REGION.fullmatch(line.region) is not None or line.region == GLOBAL) and (_number(line.usd) or 0) > 0 and type(line.tiers) is int and line.tiers > 0)


def unpack(service: str, text: str, count: int) -> tuple[Line, ...] | None:
    """The lines that `pack` made `text` of, for `service`: None for a text that is not that (not base64, not deflate or too large when unpacked, not JSON, a row that is not a line of the list, a price that
    is no price, or another number of lines than `count`), so that a broken record is no copy."""
    try:
        undone = zlib.decompressobj()
        raw = undone.decompress(base64.b64decode(text, validate=True), MAX_UNPACKED)
        lines = tuple(Line(service, *row) for row in json.loads(raw)) if not undone.unconsumed_tail else ()
    except (ValueError, TypeError, zlib.error):
        return None
    return lines if len(lines) == count and all(map(_valid, lines)) else None


def match(lines: Sequence[Line], product: str, meter: str, unit: str, region: str) -> tuple[Line | None, str]:
    """The line that the words of a meter of the bill name: the same product, meter and unit, the line of the region itself when there is one and else the one that holds in every region. `found`;
    `none` when no line has the words; `several` when the lines that have them do not agree on the price (the SKUs of one meter share its price, and that is no disagreement)."""
    same = [line for line in lines if line.product == product and line.meter == meter and line.unit == unit]
    own = [line for line in same if line.region == region] or [line for line in same if line.region == GLOBAL]
    if not own:
        return None, "none"
    return (None, "several") if len({line.usd for line in own}) > 1 else (min(own, key=lambda line: line.sku), "found")


def layout(names: Sequence[str], rows: list[list]) -> tuple[dict, list[str], list[list]]:
    """The rows of a table as the tools lay it out: a column that every row has with one value, when there are several rows, is given once in `same`; a column that no row has is left out; and a null at
    the end of a row is left off. The first column is always a column."""
    same = {name: rows[0][place] for place, name in enumerate(names) if place and len(rows) > 1 and rows[0][place] is not None and all(row[place] == rows[0][place] for row in rows)}
    kept = [place for place, name in enumerate(names) if not place or (name not in same and any(row[place] is not None for row in rows))]
    table = []
    for row in rows:
        values = [row[place] for place in kept]
        while len(values) > 1 and values[-1] is None:
            values.pop()
        table.append(values)
    return same, [names[place] for place in kept], table
