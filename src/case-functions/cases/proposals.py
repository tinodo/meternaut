"""What a finding proposes to be done to a resource, as data that code checked: the settings to change, and the other ways to save on the same resource.

The Investigator states them in the key `change` of its answer (`set` and `others`, cases/agents.py). `check` keeps an entry only after comparing it with what the tools showed in the same run, and
cases/investigate.py puts the kept ones in the facts of the case under KEY, in the plain shape below. The family `change-setting` (cases/families/setting.py) makes a `set` when a person approves it,
with that person's own token (AGENTS.md rule 29), and the pages, cards and letters say both in words. The readers and the builders here decide nothing about Azure: standard library only, and no
call to Azure. A reader never raises: what is not in the shape is left out.

The shape, under facts[KEY]:
  {"set":    [{"path": "<a key path exactly as the tools returned it>", "from": <its value as the tools returned it>, "to": <the value to set>}],            at most MAX_SETTINGS
   "others": [{"title": "<plain words>", "givesUp": "<plain words>", "action": "<an action of cases/pricing.py>", "inPlace": <true, false or absent>,
               "lowUsd": <a number>, "highUsd": <a number>, "estimate": <true or absent>}]}                                                               at most MAX_OTHERS
An estimate is a way whose saving rests on a share that the AI states and nothing checks (the form `assumed`): the pages say so. `countlike` is the one gate on which property may be lowered.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, NamedTuple, Sequence

from . import pricing
from .pricing import NAME, _number
from .roles import clean_text

KEY = "ways"  # not "proposal": the facts of a case already hold the word of the finding's proposal under that key
MAX_SETTINGS, MAX_OTHERS = 3, 3
MAX_TITLE, MAX_GIVES_UP = 80, 240
TITLE = re.compile(rf"(?!.*[0-9]{{3}})[A-Za-z0-9][A-Za-z0-9 ,()'+-]{{0,{MAX_TITLE - 1}}}")  # a title: plain words, a few marks, no stop inside it and no run of three digits (an amount)
WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")  # the words of a camel case key
KEPT_WORDS = ("retention", "retain", "retained", "keep", "kept", "ttl", "backup", "snapshot", "history", "version", "restore", "archive", "purg", "recover", "revision", "checkpoint", "softdelete", "delete",
              "logfile")  # found anywhere in a path, in any case and inside another word too, one of these says that the number decides how much is kept: a lower number deletes. The list is not complete, as no list of words is: the confirm page, the undo sentence and the approver's reading are the other guards
# Why an entry was dropped, in the words of the notes of a run: by the kind of entry, then the rule.
WHY = {
    "set": {"action": "the finding is not a reduction", "shape": "not an entry of the form", "handle": "a resource that is not the finding's", "name": "not a plain property name",
            "shown": "a property that no tool showed", "number": "a value that is not one plain number", "count": "a property that is not a count or a size", "period": "a period, not a count or a size",
            "kept": "a setting that decides how much is kept, which a lower number deletes",
            "from": "an old value that no tool showed", "to": "a new value that is not a smaller number of the same kind", "duplicate": "a property listed twice",
            "ratio": "numbers that differ from the change's own", "limit": "over the limit",
            "lowest": "a new value below {}, the lowest that Microsoft's reference page gives for the setting",
            "highest": "a new value above {}, the highest that Microsoft's reference page gives for the setting"},
    "other": {"group": "a finding of several resources", "shape": "not an entry of the form", "title": "a title that is not plain words", "action": "no action that code can read",
              "duplicate": "a repeat of the change or of a way", "limit": "over the limit"},
}
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
    "not-a-count": "Meternaut only lowers a count of units, and this setting is not one.",
    "approvers": "Nobody who may approve this change is known for the resource.",
    "unsettled": "The AI reviewers did not agree on this finding, so a person decides first whether it is worth a change.",
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
    """Another way to save on the same resource, which a person may take instead. `in_place` says whether Azure changes the resource where it is (True), or only by making it again (False).
    `estimate` is True when its saving rests on a share that the AI states and nothing checks."""

    title: str
    gives_up: str
    action: str
    in_place: bool | None
    low: float | None
    high: float | None
    estimate: bool = False


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
                         _money(item.get("lowUsd")), _money(item.get("highUsd")), item.get("estimate") is True))
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


# -- what code keeps of an answer -------------------------------------------------------------------------------------------------------------------

class Checked(NamedTuple):
    """What code made of the settings and the other ways that an answer proposed: for each handle the entry of facts[KEY] that was kept, how many entries were dropped for each (kind, rule) of WHY,
    and how many settings and other ways the answer listed."""

    ways: dict
    dropped: Counter
    said: tuple[int, int]


def _same(one: float, other: float) -> bool:
    return math.isclose(one, other, rel_tol=1e-6, abs_tol=0.0)


def _refusal(path: object) -> str:
    """Why the last key of a property path is no count, as a word of WHY, or "": the path must be a plain name of plain ASCII (pricing.NAME, which also bounds its length), and its last key must rank in
    the toolbox's own order as a count or a size (COUNT_LIKE) or be a `numberOf...` key. The length of a list that the toolbox makes up (`<plural>Count`) is not a count, a number of days,
    hours or another period is a period of time and not a count of what the resource holds, and a path that contains one of KEPT_WORDS anywhere, in any case and inside another word too (a retention, a
    backup, a snapshot, a time to live, what to keep, a history, a version, a restore or a recovery point, an archive, a purge, a revision, a checkpoint, a soft delete, a log file: `retentionCount`,
    `keepcount`, `numberOfDaysToKeep`, `recoveryPointCount`) decides how much is kept, which a lower number deletes: each has a reason of its own. A name that merely contains one of the words is refused
    too (`maxThrottleCount` holds `ttl`): the safe side of a gate that decides what may be deleted. The list is not complete, as no list of words is."""
    from .toolbox import COUNT_LIKE, _rank  # imported here: the toolbox reaches the brief and the words of the families (through the lessons), and they import this module, so a top-level import would be circular
    leaf = path.rsplit(".", 1)[-1] if isinstance(path, str) and NAME.fullmatch(path) else ""
    if not leaf or _rank(leaf) not in COUNT_LIKE or re.search(r"[^s]sCount$", leaf):
        return "count"
    if re.search(r"(?i)(?:day|hour|minute|second|week|month|year)s$", leaf):
        return "period"
    return "kept" if any(word in path.lower() for word in KEPT_WORDS) else ""


def countlike(path: str) -> bool:
    """Whether the last key of a property path names a count or a size of what a resource holds (a count, units, replicas, cores, a size, a bandwidth, a capacity: the toolbox's own ranking of a key,
    COUNT_LIKE, or a `numberOf...` key), the only kind of property that a setting may lower. A period (a retention in days, a `numberOf...` key that ends in days, hours or another period), a version, a
    state, a flag, the length of a list that the toolbox makes up (`<plural>Count`) and a setting that decides how much is kept (a path that contains a retention, backup, snapshot, ttl, keep, kept, history,
    version, restore, archive, purge, recover, revision, checkpoint, delete or log file word anywhere in it, even inside another word) are not.
    The last key decides the rank, the whole path is read for the words of what is kept, and only a plain ASCII path is one: the function is pure and answers False for
    anything that is not a path (it never raises). The dotted path is the one that the tools showed, so the family that makes a change can apply the same gate when it plans."""
    return not _refusal(path)


def _ratios(change: pricing.Change) -> dict:
    """The pairs of numbers that the change states as a ratio on a property, by (handle, property): a setting of that property has to be the same change."""
    found: dict = {}
    for effect in change.effects:
        said, on = effect.remains, effect.remains.get("on")
        pair = (_number(said.get("from")), _number(said.get("to")))
        if said.get("form") == "ratio" and isinstance(on, str) and None not in pair:
            found.setdefault((effect.handle, on), []).append(pair)
    return found


def _setting(item: object, handles: Sequence[str], evidence: Mapping, ratios: Mapping) -> tuple[str, dict] | str:
    """The handle and the entry of one setting, or the rule that it fails: a resource of the finding, a property that a tool showed under that name with one plain number and that is a count or a size
    (`countlike`), the old value that the tool showed, a new value that is smaller and of the same kind (whole where the old one is whole), inside the range that the tools showed for the property
    (`limits` of the evidence: the lowest and highest number that Microsoft's reference page gives, cases/ranges.py; outside it the rule is `lowest 2` or `highest 50`, with the page's number, and
    with no range shown nothing changes) and, where the change states a ratio on the property, that ratio's numbers."""
    if not isinstance(item, Mapping):
        return "shape"
    handle, name = item.get("handle"), item.get("property")
    if not isinstance(handle, str) or handle not in handles:
        return "handle"
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return "name"
    block = evidence.get(handle)
    held = block.get("properties") if isinstance(block, Mapping) else None
    if not isinstance(held, Mapping) or name not in held:
        return "shown"
    now = _number(held[name])
    if now is None:
        return "number"
    if why := _refusal(name):
        return why
    start, to = _number(item.get("from")), _number(item.get("to"))
    if start is None or not _same(start, now):
        return "from"
    if to is None or not 0 <= to < now or (now == int(now) and to != int(to)):
        return "to"
    if (beyond := pricing.outside(block, name, to)) is not None:
        return f"{beyond[0]} {beyond[1]}"
    if any(not (_same(one, now) and _same(other, to)) for one, other in ratios.get((handle, name), ())):
        return "ratio"
    return handle, {"path": name, "from": held[name], "to": int(to) if now == int(now) else to}


def _title(value: object) -> str:
    """A title as it is kept: one line of plain words, at most MAX_TITLE characters, with no link, markup or amount of money in it; empty when it is not that."""
    text = " ".join(value[:4 * MAX_TITLE].split()).rstrip(".") if isinstance(value, str) else ""
    return text if TITLE.fullmatch(text) and clean_text(text, MAX_TITLE) == text else ""


def _other(item: object, taken: list, titles: set) -> tuple[dict, pricing.Change] | str:
    """The entry (without its figures) and the change of one other way, or the rule that it fails: a title in plain words, a change with an action that code can read, and not the same as the
    change that the finding states or as a way that was kept before it."""
    if not isinstance(item, Mapping):
        return "shape"
    title = _title(item.get("title"))
    if not title:
        return "title"
    option = pricing.parse(item.get("change"))
    if option is None or option.action == "none":
        return "action"
    if (option.action, option.effects) in taken or title.casefold() in titles:
        return "duplicate"
    gives_up, place = item.get("gives_up"), item.get("in_place")
    return {"title": title, "givesUp": clean_text(gives_up, MAX_GIVES_UP) if isinstance(gives_up, str) else "", "action": option.action,
            **({"inPlace": place} if isinstance(place, bool) else {})}, option


def check(change: pricing.Change | None, proposal: str, handles: Sequence[str], evidence: Mapping, price: Callable[[pricing.Change], pricing.Priced]) -> Checked:
    """What code keeps of the settings and the other ways that the change of a finding states. `proposal` is the finding's, `handles` the resources that it covers, `evidence` what the tools showed
    for each handle (Toolbox.evidence) and `price` the price of a change from the bill (cases/pricing.py price, for those handles). An entry that fails a rule is dropped by itself and counted, and
    the finding is never dropped for it. Settings are kept only for a finding that proposes a change by the action reduce, and other ways only for a finding of one resource. A way that cannot be
    priced is kept with no figure, and no way ever becomes a setting."""
    dropped: Counter = Counter()
    ways: dict[str, dict] = {}
    if change is None:
        return Checked(ways, dropped, (0, 0))
    ratios, seen = _ratios(change), set()
    for item in change.settings:
        found = _setting(item, handles, evidence, ratios) if proposal == "change" and change.action == "reduce" else "action"
        if not isinstance(found, str):
            found = "duplicate" if (found[0], found[1]["path"]) in seen else "limit" if len(seen) >= MAX_SETTINGS else found
        if isinstance(found, str):
            dropped["set", found] += 1
        else:
            seen.add((found[0], found[1]["path"]))
            ways.setdefault(found[0], {}).setdefault("set", []).append(found[1])
    if change.others and len(handles) != 1:
        dropped["other", "group"] += len(change.others)
    elif change.others:
        kept: list[dict] = []
        taken, titles = [(change.action, change.effects)], set()
        for item in change.others:
            found = _other(item, taken, titles)
            if isinstance(found, str) or len(kept) >= MAX_OTHERS:
                dropped["other", found if isinstance(found, str) else "limit"] += 1
                continue
            entry, option = found
            row = price(option).rows.get(handles[0])
            if row is not None:
                entry |= {"lowUsd": row.low, "highUsd": row.high, **({"estimate": True} if row.form in ("assumed", "mixed") else {})}  # these forms rest on a share that only the AI states
            kept.append(entry)
            taken.append((option.action, option.effects))
            titles.add(entry["title"].casefold())
        if kept:
            ways.setdefault(handles[0], {})["others"] = kept
    return Checked(ways, dropped, (len(change.settings), len(change.others)))


def reason(kind: str, why: str) -> str:
    """The words for the rule that dropped an entry (a word of WHY[kind]): the two rules of the documented range carry the number that the page gives, as `lowest 2` or `highest 50`, and say it."""
    word, _, number = why.partition(" ")
    return WHY[kind][word].format(shown(int(number))) if number.lstrip("-").isdigit() else WHY[kind][why]


def note_of(checked: Checked) -> str:
    """The sentence for the notes of a run about the entries that code dropped (how many of those that the answer listed, and why), or "" when it dropped none."""
    parts = []
    for place, (kind, noun) in enumerate((("set", "setting"), ("other", "other way"))):
        gone = {why: count for (what, why), count in checked.dropped.items() if what == kind}
        if gone:
            parts.append(f"{sum(gone.values())} of {checked.said[place]} {noun}{'' if checked.said[place] == 1 else 's'} ({', '.join(f'{reason(kind, why)}: {count}' for why, count in gone.items())})")
    return "code dropped " + " and ".join(parts) if parts else ""


def view(items: Iterable[tuple[str, object]]) -> dict:
    """What the Skeptic is shown of the proposals of a finding, from the facts of the cases of its resources (`items`: a handle and the facts of its case): the settings, each with its handle, the
    property as the tools showed it and the value now and after, and the other ways, each with its title, what it gives up (the Investigator's words), the action, whether Azure changes the resource
    where it is, what code priced it at a month and whether that is an estimate. A key is there only when it has entries."""
    lowered, ways = [], []
    for handle, facts in items:
        lowered += [{"handle": handle, "property": item.path, "from": item.now, "to": item.to} for item in settings(facts)]
        ways += [{key: value for key, value in (("title", way.title), ("givesUp", way.gives_up), ("action", way.action), ("inPlace", way.in_place), ("lowUsd", way.low), ("highUsd", way.high),
                                                ("estimate", way.estimate or None)) if value is not None} for way in others(facts)]
    return {**({"set": lowered} if lowered else {}), **({"others": ways} if ways else {})}
