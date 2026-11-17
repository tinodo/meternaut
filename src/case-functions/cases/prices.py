"""What Azure's public price list says about the prices of one service in one region, read for the tool that shows alternatives (price_alternatives in cases/toolbox.py).

The one call is a GET of the list with no token (http.PRICE_CALL). Its address is made from typed words only: a service, a region, a product and the currency, each a word of the platform that
passed a check before it got here, and never a name, a tag or an id of an estate. What comes back is read into typed numbers and short words: a text of the list is kept only when it is no longer than
a word of the platform, and the tool shows it through the same check as every other word of a meter. Only pay-as-you-go prices are read, in US dollars, and a price that has several steps is marked so
and is never taken for the price of the whole quantity. A read has a cap of pages, of lines and of time, and says when a cap ended it. Standard library only: the client is the one of the Watch.
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
GLOBAL = "Global"  # how the list names the region of a price that holds in every region
MAX_PAGES = 5  # pages of one read; the list gives 1,000 lines a page
MAX_LINES = 6000  # prices that one read keeps
MAX_HELD = 20000  # prices that the reads of one run keep in all
MAX_TEXT = 100  # characters of a text of the list that are kept: a longer one is no word of the platform
SECONDS = 30.0  # what one read may take in all
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
    region: str
    tiers: int


@dataclass(frozen=True)
class Book:
    lines: tuple[Line, ...]
    complete: bool  # False when a cap of pages, of lines or of time ended the read


def region_of(word: object) -> str | None:
    """The region as the list names it: the lower-case word that Azure gives, and `Global` for the word global."""
    return (GLOBAL if word == "global" else word) if isinstance(word, str) and REGION.fullmatch(word) else None


def address(service: str, region: str, product: str | None) -> str:
    """The address of the first page: the prices of a service that hold in a region or in every region, and of one product of it when there is one."""
    for word in (service, product or "x"):
        if not WORDS.fullmatch(word):
            raise ValueError("a word that is not made of letters, digits and the marks of a platform name")
    if not REGION.fullmatch(region) and region != GLOBAL:
        raise ValueError("a region that is not a region word")
    condition = f"serviceName eq '{service}' and priceType eq 'Consumption' and " + (f"armRegionName eq '{GLOBAL}'" if region == GLOBAL else f"(armRegionName eq '{region}' or armRegionName eq '{GLOBAL}')")
    if product:
        condition += f" and productName eq '{product}'"
    return f"https://{PRICES_HOST}{PRICES_PATH}?api-version={API_VERSION}&currencyCode='{CURRENCY}'&$filter={quote(condition, safe='')}"


def _bad(what: str) -> HttpError:
    return HttpError(200, f"the price list {what}")


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


def _keep(found: dict, item: object) -> None:
    """One line of a page: kept when it is a pay-as-you-go price in dollars with words of the length of a platform's, as the price of its first step and the steps that it has."""
    if not isinstance(item, dict) or item.get("type") != "Consumption" or item.get("currencyCode") != CURRENCY:
        return
    texts = tuple(item.get(name) for name in ("productName", "skuName", "meterName", "unitOfMeasure", "armRegionName"))
    price, tier = _number(item.get("retailPrice")), _number(item.get("tierMinimumUnits"))
    if price is not None and tier is not None and all(isinstance(text, str) and 0 < len(text) <= MAX_TEXT for text in texts):
        found.setdefault(texts, {}).setdefault(tier, set()).add(price)


def read(client: Client, service: str, region: str, product: str | None, monotonic: Callable[[], float] = time.monotonic) -> Book:
    """The prices of a service in a region, and of one product of it when there is one, read a page at a time up to the caps. Raises HttpError when the list cannot be read: a call that failed, an
    answer that is not the list, or a next page somewhere else. A price that the list gives twice with two values is left out."""
    found: dict = {}
    url: str | None = address(service, region, product)
    stop, pages = monotonic() + SECONDS, 0
    while url and pages < MAX_PAGES and len(found) < MAX_LINES and monotonic() < stop:
        data = client.request("GET", url, headers={"User-Agent": USER_AGENT}, timeout=20, retries=1, retry_after_max=10).json()
        items = data.get("Items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise _bad("gave an answer that the app does not understand")
        for item in items:
            _keep(found, item)
        pages += 1
        url = _next(data["NextPageLink"]) if data.get("NextPageLink") else None
    lines = tuple(Line(service, *texts[:4], next(iter(steps[0])), texts[4], len(steps)) for texts, steps in found.items() if 0 in steps and len(steps[0]) == 1)
    return Book(lines[:MAX_LINES], url is None)


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
