"""What Azure's public price list says about the prices of one service in one region, read for the tool that shows alternatives (price_alternatives in cases/toolbox.py).

The one call is a GET of the list with no token (http.PRICE_CALL). Its address is made from typed words only: a service, a region, a product and the currency, each a word of the platform that
passed a check before it got here, and never a name, a tag or an id of an estate. What comes back is read into typed numbers and short words: a text of the list is kept only when it is no longer than
a word of the platform, and the tool shows it through the same check as every other word of a meter. Only pay-as-you-go prices are read, in US dollars, and a price that has several steps is marked so
and is never taken for the price of the whole quantity. A price that holds in every region the list writes with the region Global or with no region: both are Global here. A read has a cap of pages, of
lines, of the length of a page and of time (a try of a page takes at most ATTEMPT seconds and never more than the time that is left), and says when a cap or a failure ended it. Standard library only: the
client is the one of the Watch.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Callable, Sequence
from urllib.parse import quote, urlsplit

from .http import PRICES_HOST, PRICES_PATH, Client, HttpError

API_VERSION = "2023-01-01-preview"
CURRENCY = "USD"
GLOBAL = "Global"  # how the list names the region of a price that holds in every region (it also writes such a price with no region: see _keep)
MAX_PAGES = 5  # pages of one read; the list gives 1,000 lines a page
MAX_LINES = 6000  # prices that one read keeps
MAX_HELD = 20000  # prices that the reads of one run keep in all
MAX_TEXT = 100  # characters of a text of the list that are kept: a longer one is no word of the platform
MAX_PAGE_LENGTH = 3_000_000  # the longest answer for a page that is read, as it comes: a page of 1,000 lines is about 600,000 long
ATTEMPT = 8.0  # seconds that one try of one page may take
SECONDS = 24.0  # what one read may take in all (a call of the toolbox may take 45)
PAUSE = 5.0  # the longest that a list that says to wait is waited for
USER_AGENT = "Meternaut-Watch/1 (reads the public price list)"
WORDS = re.compile(r"[A-Za-z0-9.&()/:+-]+(?: [A-Za-z0-9.&()/:+-]+){0,9}")
REGION = re.compile(r"[a-z0-9]{1,24}")


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


def read(client: Client, service: str, region: str, product: str | None, monotonic: Callable[[], float] = time.monotonic, seconds: float = SECONDS) -> Book:
    """The prices of a service in a region, and of one product of it when there is one, read a page at a time up to the caps and never for longer than `seconds`: a try takes at most ATTEMPT seconds
    (the timeout of one socket operation, so a host that sends one byte at a time can take longer: the time is checked between pages) and at most the time that is left, a host that gives no answer is
    tried once, and a second try (for a list that is busy or fails) is made only when the time that is left holds it. The transport reads at most MAX_PAGE_LENGTH + 1 of a page, so a page cannot fill
    the memory, and a longer one is refused with the code word TooLarge. Raises HttpError when the first page cannot be read: a call that failed, an answer that is not the list, a page that is too large
    or a next page somewhere else. A failure after a page that was read ends the read there: the book holds what was read, is not complete and has the failure. A price that the list gives twice with
    two values is left out, and so is a price of nothing: it is no price of any alternative."""
    found: dict = {}
    url: str | None = address(service, region, product)
    regions = frozenset((GLOBAL,) if region == GLOBAL else (region, GLOBAL))
    stop, pages, error = monotonic() + seconds, 0, None
    while url and pages < MAX_PAGES and len(found) < MAX_LINES:
        left = stop - monotonic()
        if left < 1.0:
            break
        try:
            response = client.request("GET", url, headers={"User-Agent": USER_AGENT}, timeout=min(ATTEMPT, left), retries=1 if left >= 2 * ATTEMPT + PAUSE else 0, retry_after_max=PAUSE,
                                      retry_network=False, limit=MAX_PAGE_LENGTH + 1)
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
