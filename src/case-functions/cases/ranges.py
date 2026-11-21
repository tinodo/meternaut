"""The documented range of the numbers of a resource type: the lowest and the highest that Microsoft's reference page of the type gives, read by code (docs/proposals/31-proposals.md).

The reference page of a resource type (Learn, `/azure/templates/<the type in lower case>`, the address that library.reference_url makes) lists the properties of the type in tables of Name,
Description and Value, and a number that has bounds says so in its Value cell: `int`, `Constraints:`, `Min value = N`, `Max value = M`. `parse` reads those cells and nothing else, for any type and
with no knowledge of any: no kind, property or number is named here. A name that two rows of a page give different bounds, or that one row bounds and another does not, has no range, because the
page does not say which object a name belongs to. `Reader` reads the page of a type once in a run, with the docs client of the app (the list of calls of the Study: GET only, no token, pages of
Microsoft's documentation only) and within the caps below, and says None for a page that it did not read, which is never the same as a type that has no range.

What this cannot do, said plainly: a page can be wrong or late, the range of the API is not the range of a SKU or a plan (a plan may take fewer), and a name that a page gives twice with two ranges
is not read at all.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Mapping

from . import library
from .http import Client

MAX_READS = 24  # pages that one run reads: a run looks at a few dozen kinds of resource at most, and the page of a kind is read once
SECONDS = 30.0  # what the reads of one run may take in all, so that a host that is slow costs a tool a read or two and then no more (a call of a tool may take 45 seconds)
ATTEMPT = 8.0  # seconds that one read may take: a page of 100 to 700 KB answers in a fraction of a second, so a read that takes longer is not going to give it
HEADER = ("name", "description", "value")  # the first row of the tables of property values
KIND = re.compile(r"[a-z0-9.]+(?:/[a-z0-9._-]{1,50}){1,4}")  # a resource type as Azure names it, in lower case: the page that is asked for is the page of one type, never an index
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
LOW = re.compile(r"Min value = (-?[0-9]{1,15})(?![0-9.,eE])")  # a whole number only: 2.5, 1,000 and 1e3 are not read as 2, 1 and 1
HIGH = re.compile(r"Max value = (-?[0-9]{1,15})(?![0-9.,eE])")


@dataclass(frozen=True)
class Range:
    """The lowest and the highest whole number that the page gives for a property. A bound that the page does not give is None."""

    lowest: int | None = None
    highest: int | None = None

    def bounds(self) -> dict[str, int]:
        return {name: value for name, value in (("lowest", self.lowest), ("highest", self.highest)) if value is not None}


class _Tables(HTMLParser):
    """The tables of a page as rows of the text of their cells, with a space for each line break or block inside a cell, so that `Min value = N<br>Max value = M` reads as it looks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.nested = False
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self.nested = self.nested or self._table is not None
            self._table = self._table if self._table is not None else []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag in library.BLOCKS and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(library.flat("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag in library.BLOCKS and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _bounds(cell: str) -> Range | None:
    """The range that the words of a Value cell give, or None when they give none that is usable: no `Min value` or `Max value` of a whole number, or a lowest above the highest."""
    low, high = (int(found.group(1)) if found else None for found in (LOW.search(cell), HIGH.search(cell)))
    return Range(low, high) if (low is not None or high is not None) and (low is None or high is None or low <= high) else None


def parse(page: str) -> dict[str, Range] | None:
    """The range of each name that the tables of property values of a page bound, as the page spells the name (the first spelling, when the spellings differ in case only). None when the page has no
    table of property values, or has a table in a table (nothing says which name a bound is for): it is not read. A name that two of its rows bound differently, or that one row bounds and another
    does not, is left out."""
    tables = _Tables()
    try:
        tables.feed(page)
        tables.close()
    except Exception:  # noqa: BLE001 (a page that the parser cannot read gives the tables up to there)
        pass
    properties = [rows for rows in tables.tables if rows and tuple(cell.lower() for cell in rows[0]) == HEADER]
    if tables.nested or not properties:
        return None
    seen: dict[str, tuple[str, set[Range | None]]] = {}
    for rows in properties:
        for row in rows[1:]:
            if len(row) >= 2 and NAME.fullmatch(row[0]):
                seen.setdefault(row[0].lower(), (row[0], set()))[1].add(_bounds(row[-1]))
    return {spelled: next(iter(variants)) for spelled, variants in seen.values() if len(variants) == 1 and None not in variants}  # type: ignore[misc]


def find(found: Mapping[str, Range], path: str) -> Range | None:
    """The range of the property that a key path of an answer names, by its last key: as the page spells it, else in the case that the platform's list gives it (the two spell a name alike but for case)."""
    leaf = path.rsplit(".", 1)[-1]
    return found.get(leaf) or next((value for name, value in found.items() if name.lower() == leaf.lower()), None)


class Reader:
    """The ranges of the numbers of the types of one run: `limits(type)` is what `parse` gives for the reference page of the type, or None when the page was not read (the address is not one that the
    Study may read, the call failed, took too long or was refused, the page is too long or is no reference page, or the caps of the run are used up). The page of a type is read once, and what the read
    gave, a failure too, is kept for the run: nothing is asked twice. It never raises."""

    def __init__(self, docs: Client, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.docs, self.monotonic = docs, monotonic
        self._found: dict[str, Mapping[str, Range] | None] = {}
        self._reads, self._spent = 0, 0.0
        self._lock = threading.Lock()

    def limits(self, resource_type: object) -> Mapping[str, Range] | None:
        if not isinstance(resource_type, str):
            return None
        with self._lock:
            if resource_type not in self._found:
                self._found[resource_type] = self._read(resource_type)
            return self._found[resource_type]

    def _read(self, resource_type: str) -> Mapping[str, Range] | None:
        url, left = library.reference_url(resource_type) if KIND.fullmatch(resource_type) else None, SECONDS - self._spent
        if url is None or self._reads >= MAX_READS or left < 1.0:
            return None
        began, self._reads = self.monotonic(), self._reads + 1
        try:
            response = self.docs.request("GET", url, headers={"User-Agent": library.USER_AGENT, "Accept": "text/html"}, timeout=min(ATTEMPT, left), retries=0, retry_network=False,
                                         limit=library.MAX_DOWNLOAD + 1)
            return None if len(response.body) > library.MAX_DOWNLOAD else parse(response.body.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 (a read that fails is a page that was not read, and it never stops a tool)
            return None
        finally:
            self._spent += self.monotonic() - began
