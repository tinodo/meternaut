"""What a finding proposes to be done to a resource, as data that code checked: the settings to change, and the other ways to save on the same resource.

The Investigator states them in the key `change` of its answer (`set` and `others`, cases/agents.py). cases/investigate.py keeps an entry only after code has compared it with what the tools showed in
the same run, and puts the kept ones in the facts of the case under KEY, in the plain shape below. The family `change-setting` (cases/families/setting.py) makes a `set` when a person approves it,
with that person's own token (AGENTS.md rule 29), and the pages, cards and letters say both in words. This module reads and shapes that data and decides nothing: standard library only, and no
call to Azure. A reader never raises: what is not in the shape is left out.

The shape, under facts[KEY]:
  {"set":    [{"path": "<a key path exactly as the tools returned it>", "from": <its value as the tools returned it>, "to": <the value to set>}],            at most MAX_SETTINGS
   "others": [{"title": "<plain words>", "givesUp": "<plain words>", "action": "<an action of cases/pricing.py>", "inPlace": <true, false or absent>,
               "lowUsd": <a number>, "highUsd": <a number>}]}                                                                                              at most MAX_OTHERS
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Mapping

KEY = "proposal"
MAX_SETTINGS, MAX_OTHERS = 3, 3
MAX_TITLE, MAX_GIVES_UP = 80, 240
WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")  # the words of a camel case key
# Why Meternaut cannot make a change that a finding proposes. The family `change-setting` stores one key in the preconditions of the request that it makes instead (`cannotChange`), and the pages,
# cards and letters say its sentence. The sentences are whole, plain and about this one request.
CANNOT = {
    "switch-off": "The owner has not yet allowed Meternaut to change real resources.",
    "outside": "This resource group is not on the list of places where Meternaut may make a change.",
    "locked": "A lock on the resource or on its resource group stops changes.",
    "do-not-touch": "A person marked this resource do-not-touch.",
    "unreadable": "Meternaut could not read the resource in Azure just now, so it could not check the change.",
    "mismatch": "Azure no longer shows the value that the AI saw, so the change would not be the one that was judged.",
    "busy": "Azure shows that something else is changing the resource right now.",
    "unsupported": "Meternaut can only lower a number that Azure shows as a plain value of the resource, and this is not one.",
    "no-version": "Azure lists no released version of its interface for this kind of resource, so Meternaut cannot change it safely.",
}
CANNOT_KEY = "cannotChange"


@dataclass(frozen=True)
class Setting:
    """One property of one resource and the value that it should have: `path` as the tools returned it, `now` the value they returned, `to` the value to set."""

    path: str
    now: bool | int | float | str
    to: bool | int | float | str


@dataclass(frozen=True)
class Other:
    """Another way to save on the same resource, which a person may take instead. `in_place` says whether Azure changes the resource where it is (True), or only by making it again (False)."""

    title: str
    gives_up: str
    action: str
    in_place: bool | None
    low: float | None
    high: float | None


def _scalar(value: object) -> bool | int | float | str | None:
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def _text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _money(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _entries(facts: object, name: str) -> list:
    found = facts.get(KEY) if isinstance(facts, Mapping) else None
    items = found.get(name) if isinstance(found, Mapping) else None
    return items if isinstance(items, list) else []


def settings(facts: object) -> tuple[Setting, ...]:
    """The settings that the facts of a case propose, in order: an entry without a path, a value or a new value is left out."""
    out = []
    for item in _entries(facts, "set"):
        path, now, to = (item.get("path"), _scalar(item.get("from")), _scalar(item.get("to"))) if isinstance(item, Mapping) else (None, None, None)
        if isinstance(path, str) and path and now is not None and to is not None:
            out.append(Setting(path, now, to))
    return tuple(out[:MAX_SETTINGS])


def others(facts: object) -> tuple[Other, ...]:
    """The other ways to save that the facts of a case hold, in order: an entry without a title is left out."""
    out = []
    for item in _entries(facts, "others"):
        if not isinstance(item, Mapping) or not _text(item.get("title"), MAX_TITLE):
            continue
        place = item.get("inPlace")
        out.append(Other(_text(item.get("title"), MAX_TITLE), _text(item.get("givesUp"), MAX_GIVES_UP), _text(item.get("action"), 20), place if isinstance(place, bool) else None,
                         _money(item.get("lowUsd")), _money(item.get("highUsd"))))
    return tuple(out[:MAX_OTHERS])


def cannot(preconditions: object) -> str:
    """The sentence that says why Meternaut cannot make the change of a request, from the key that the request keeps; empty when it keeps none or one that is not known."""
    key = preconditions.get(CANNOT_KEY) if isinstance(preconditions, Mapping) else None
    return CANNOT.get(key, "") if isinstance(key, str) else ""


def label(path: str) -> str:
    """A key path in words of a person: `scaleUnits` is "scale units", `sku.capacity` is "sku capacity". The words are the platform's own, in lower case."""
    return " ".join(word.lower() for part in str(path).split(".") for word in WORD.findall(part))


def shown(value: object) -> str:
    """A value as a sentence says it: 4 is "4", 1440.0 is "1,440", True is "on", a word is itself."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float) and value == int(value):
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    return str(round(value, 2)) if isinstance(value, float) else str(value)
