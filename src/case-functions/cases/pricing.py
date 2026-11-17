"""What a finding's change would save, worked out by code from the bill and from nothing that an AI wrote as an amount (rules 26 (d) and 30).

The Investigator states a change in typed form (the key `change` of a finding): an action and, for each resource that it covers, the meters that the change would shrink (the handles that
cost_meters gave for that resource, cases/meters.py) and what remains of them. The saving of a resource is the cost of those meters in the last 30 closed days times the share that goes away,
as a low and a high, never above what the resource cost. How much remains is one of a few forms that code can check against what the tools showed in the same run:

  none           everything that the meters bill goes away: a figure that follows from the bill alone (Expected)
  ratio          a count or a size goes from a number that a tool returned for the resource to a number that the AI proposes (Scenario)
  share_of_days  the resource is needed on some days of every so many, which the AI states (Scenario)
  assumed        a share that the AI assumes, as a low and a high, always said to be the AI's own (Scenario)
  alternative    a switch to something else, priced from a public price list: refused until that exists

A meter that no tool showed, that belongs to another resource or to a whole type, or that was not read over 30 days is not counted; a bill line is counted once in a finding; what could not be
checked is said, and no figure is made of it. The point that a case keeps is the low end. The digest is numbers and closed words, which the brief reads again.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Collection, Mapping, NamedTuple, Sequence

from .meters import Meter, shape
from .roles import clean_text

KEY = "change"  # the key of the facts of a case
ACTIONS = ("remove", "reduce", "switch", "schedule", "commit", "none")
FORMS = ("none", "ratio", "share_of_days", "assumed", "alternative")
ALLOWED = {"remove": ("none",), "reduce": ("ratio", "assumed"), "schedule": ("share_of_days", "assumed"), "switch": ("alternative", "assumed"), "commit": ("assumed",)}
SHOWN = ("none", "ratio", "share_of_days", "assumed", "mixed")  # the forms that a digest may have: mixed is a sum of resources whose rules differ
MAX_EFFECTS, MAX_METERS, MAX_HOW = 60, 40, 300
WINDOW = 30  # the closed days that a figure a month rests on
EXPECTED, SCENARIO = "Expected", "Scenario"
METER = re.compile(r"m[0-9]{1,4}")
WHY = {
    "none": "No saving was worked out: the AI did not name the bill lines that a change would shrink.",
    "lines": "No saving was worked out: the bill lines that the AI named were not found for this resource over the last 30 days.",
    "remains": "No saving was worked out: what would remain of the bill lines was not stated in a form that code can check.",
    "currency": "No saving was worked out: the cost is not in US dollars.",
    "nothing": "No saving was worked out: the bill lines that the AI named cost nothing in the last 30 days.",
    "later": "No saving was worked out: a switch to an alternative is not available yet.",
}


@dataclass(frozen=True)
class Effect:
    handle: str
    meters: tuple[str, ...]
    remains: dict


@dataclass(frozen=True)
class Change:
    action: str
    effects: tuple[Effect, ...]
    how: str  # the AI's words for a person, cleaned: never an input of a model


class Row(NamedTuple):
    """The figure of one resource: US dollars a month (low and high), the cost of the meters that it rests on, how many there are and what remains of them."""

    handle: str
    low: float
    high: float
    bill: float
    lines: int
    form: str
    said: dict
    away: tuple[float, float] | None  # the smallest and the largest share that goes away, when one rule says it
    skipped: int
    meters: tuple[str, ...]

    @property
    def level(self) -> str:
        return EXPECTED if self.form == "none" else SCENARIO

    def digest(self, advisor: float | None = None) -> dict:
        out: dict = {"lowUsd": self.low, "highUsd": self.high, "billUsd": self.bill, "lines": self.lines, "resources": 1, "form": self.form, **self.said}
        if self.away is not None and self.form == "assumed":
            out["away"] = list(self.away)
        if self.skipped:
            out["skipped"] = self.skipped
        if advisor is not None:
            out["advisorUsd"] = advisor
        return out


@dataclass
class Priced:
    """What code made of a change: a row for each resource that has a figure, the word of WHY for each that has none, and how many effects named a resource that is not the finding's."""

    action: str
    rows: dict[str, Row] = field(default_factory=dict)
    why: dict[str, str] = field(default_factory=dict)
    ignored: int = 0


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def _whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse(raw: object) -> Change | None:
    """The change that an answer states, read strictly. None when the answer states none; a block that cannot be read is a change of the action none, which the finding says."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return Change("none", (), "")
    action = raw.get("action").strip().lower() if isinstance(raw.get("action"), str) else ""
    items = raw.get("effects") if action in ACTIONS and action != "none" and isinstance(raw.get("effects"), list) else []
    effects = []
    for item in items[:MAX_EFFECTS]:
        if isinstance(item, dict) and isinstance(item.get("handle"), str):
            named = item.get("meters") if isinstance(item.get("meters"), list) else []
            effects.append(Effect(item["handle"], tuple(dict.fromkeys(m for m in named[:MAX_METERS] if isinstance(m, str))), item["remains"] if isinstance(item.get("remains"), dict) else {}))
    return Change(action if action in ACTIONS else "none", tuple(effects), clean_text(raw.get("how"), MAX_HOW))


def _cited(block: Mapping, name: object, said: float) -> bool:
    """Whether a number is one that the tools returned for the resource under this name: a property, or the total, the highest value, the average or any recorded total of a measurement."""
    if not isinstance(name, str):
        return False
    properties, measured = block.get("properties"), block.get("metrics")
    found = [properties.get(name)] if isinstance(properties, Mapping) else []
    aggregate = measured.get(name) if isinstance(measured, Mapping) else None
    if isinstance(aggregate, Mapping):
        totals = aggregate.get("totals")
        found += [aggregate.get(key) for key in ("total", "max", "average")] + (list(totals) if isinstance(totals, (list, tuple)) else [])
    return any(number is not None and math.isclose(said, number, rel_tol=1e-6, abs_tol=0.0) for number in map(_number, found))


def _remains(said: Mapping, action: str, block: Mapping) -> tuple[str, float, float, dict] | str:
    """(the form, the smallest and the largest share that remains, the numbers that the AI stated) or the word of WHY."""
    form = said.get("form")
    if form not in FORMS or form not in ALLOWED.get(action, ()):
        return "remains"
    if form == "none":
        return form, 0.0, 0.0, {}
    if form == "alternative":
        return "later"
    if form == "ratio":
        start, target = _number(said.get("from")), _number(said.get("to"))
        if start is None or target is None or not 0 <= target < start or not _cited(block, said.get("on"), start):
            return "remains"
        return form, target / start, target / start, {"from": start, "to": target}
    if form == "share_of_days":
        days, span = _whole(said.get("days")), _whole(said.get("of"))
        if days is None or span is None or not 1 <= days < span <= 31:
            return "remains"
        return form, days / span, days / span, {"days": days, "span": span}
    low, high = _number(said.get("low")), _number(said.get("high"))
    return (form, low, high, {}) if low is not None and high is not None and 0 <= low <= high <= 1 else "remains"


def _part(effect: Effect, action: str, block: Mapping, registry: Mapping, seen: set) -> tuple | str:
    """One effect: (form, smallest share that remains, largest, stated numbers, cost of its meters, the meters that count, how many were not counted), or the word of WHY."""
    found = _remains(effect.remains, action, block)
    if isinstance(found, str):
        return found
    used: list[tuple[str, float]] = []
    skipped = 0
    for name in effect.meters:
        meter = registry.get(name) if METER.fullmatch(name) else None
        if not isinstance(meter, Meter) or meter.scope != effect.handle or meter.days != WINDOW or _number(meter.usd) is None:
            skipped += 1
        elif (meter.scope, meter.words) not in seen and meter.usd > 0:
            seen.add((meter.scope, meter.words))  # a bill line counts once, however many calls showed it
            used.append((name, meter.usd))
    if not effect.meters:
        return "none"
    if not used:
        return "lines" if skipped else "nothing"
    return (*found, math.fsum(usd for _, usd in used), tuple(name for name, _ in used), skipped)


def _row(handle: str, parts: list[tuple], cost: float | None, failed: int) -> Row | str:
    low = math.fsum(part[4] * (1 - part[2]) for part in parts)
    high = math.fsum(part[4] * (1 - part[1]) for part in parts)
    bill = math.fsum(part[4] for part in parts)
    if cost is not None:
        low, high = min(low, cost), min(high, cost)
    if high <= 0:
        return "nothing"
    alike = len({(part[0], part[1], part[2], tuple(sorted(part[3].items()))) for part in parts}) == 1
    form = parts[0][0] if alike else "mixed"
    away = (round(1 - parts[0][2], 4), round(1 - parts[0][1], 4)) if alike else None
    return Row(handle, round(low, 2), round(high, 2), round(bill, 2), sum(len(part[5]) for part in parts), form, parts[0][3] if alike else {}, away,
               failed + sum(part[6] for part in parts), tuple(name for part in parts for name in part[5]))


def price(change: Change | None, handles: Collection[str], toolbox: object, costs: Mapping[str, float | None], blocked: Mapping[str, str] | None = None) -> Priced:
    """The rows of a change for the resources `handles` of a finding. `toolbox` holds the meters (`meters`) and the evidence of the run, `costs` the 30-day cost of each resource (None when it was not
    read) and `blocked` the resources that have no figure from outside, by the word of WHY (a cost that is not in US dollars)."""
    out = Priced(change.action if change is not None else "")
    if change is None:
        return out
    registry, evidence = getattr(toolbox, "meters", None), getattr(toolbox, "evidence", None)
    registry, evidence = registry if isinstance(registry, Mapping) else {}, evidence if isinstance(evidence, Mapping) else {}
    seen: set = set()
    parts: dict[str, list[tuple]] = {}
    failed: dict[str, list[str]] = {}
    for effect in change.effects:
        if effect.handle not in handles:
            out.ignored += 1
        elif blocked and effect.handle in blocked:
            failed.setdefault(effect.handle, []).append(blocked[effect.handle])
        else:
            block = evidence.get(effect.handle)
            got = _part(effect, change.action, block if isinstance(block, Mapping) else {}, registry, seen)
            if isinstance(got, str):
                failed.setdefault(effect.handle, []).append(got)
            else:
                parts.setdefault(effect.handle, []).append(got)
    for handle in dict.fromkeys([*parts, *failed]):
        row = _row(handle, parts[handle], costs.get(handle), len(failed.get(handle, ()))) if handle in parts else failed[handle][0]
        if isinstance(row, str):
            out.why[handle] = row
        else:
            out.rows[handle] = row
    return out


# -- what a case keeps ------------------------------------------------------------------------------------------------------------------------------

def digest(change: Change | None, priced: Priced, handle: str, advisor: float | None = None) -> dict | None:
    """The `change` of the facts of the case of one resource: the action, the AI's words for a person, and either the typed figure or the word that says why there is none."""
    if change is None:
        return None
    out: dict = {"action": change.action, **({"how": change.how} if change.how else {})}
    row = priced.rows.get(handle)
    if row is not None:
        out["price"] = row.digest(advisor)
    else:
        out["missing"] = priced.why.get(handle) or "none"
    return out


def combine(digests: Sequence[object], members: int) -> dict | None:
    """The `change` of the case of a group from those of its resources: the sums of the figures, and the rule only when it is the same for all of them. None when there is none."""
    kept = [item for item in digests if isinstance(item, Mapping)]
    if not kept:
        return None
    out: dict = {"action": kept[0].get("action"), **({"how": how} if (how := next((item["how"] for item in kept if item.get("how")), "")) else {})}
    prices = [item["price"] for item in kept if isinstance(item.get("price"), Mapping)]
    if not prices:
        return {**out, "missing": next((item["missing"] for item in kept if item.get("missing") in WHY), "none")}
    keys = ("form", "from", "to", "days", "span", "away")
    alike = len({tuple(str(price.get(key)) for key in keys) for price in prices}) == 1
    total = {key: round(math.fsum(price.get(key) or 0 for price in prices), 2) for key in ("lowUsd", "highUsd", "billUsd")}
    price = {**total, "lines": sum(price.get("lines") or 0 for price in prices), "resources": len(prices), "members": members,
             **({key: prices[0][key] for key in keys if key in prices[0]} if alike else {"form": "mixed"})}
    skipped = sum(price.get("skipped") or 0 for price in prices)
    return {**out, "price": {**price, **({"skipped": skipped} if skipped else {})}}


def _change(facts: object) -> Mapping:
    found = facts.get(KEY) if isinstance(facts, Mapping) else None
    return found if isinstance(found, Mapping) else {}


class Saved(NamedTuple):
    low: float
    high: float
    level: str
    basis: str  # a phrase for "Based on ...", from closed words and numbers: no text of the estate
    bill: float  # what the bill lines that the figure rests on cost in the last 30 days
    lines: int


def _usd(value: float) -> str:
    return f"${value:,.2f}"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _basis(found: Mapping, form: str, low: float, high: float) -> str:
    lines, many = _whole(found.get("lines")) or 1, _whole(found.get("resources")) or 1
    text = f"the {_count(lines, 'bill line')} of {_count(many, 'resource')} that the change would {'remove' if form == 'none' else 'shrink'}, over the last {WINDOW} days"
    start, target, days, span, away = (found.get(key) for key in ("from", "to", "days", "span", "away"))
    if form == "ratio":
        text += (f", scaled by the change from {start:g} to {target:g}" if _number(start) is not None and _number(target) is not None else ", scaled by the change that the AI proposed")
        text += ": the target is the AI's proposal"
    elif form == "share_of_days":
        text += f", scaled to {days} days of every {span}: the AI's proposal" if _whole(days) and _whole(span) else ", scaled to the days that it is needed: the AI's proposal"
    elif form == "assumed":
        pair = [round(share * 100) for share in away] if isinstance(away, list) and len(away) == 2 and all(_number(share) is not None for share in away) else []
        text += (f", of which {pair[0]}" + (f" to {pair[1]}" if pair[1] != pair[0] else "") + " percent would go away" if pair else ", of which a share would go away")
        text += ": the AI's own assumption, not checked by code"
    elif form == "mixed":
        text += ", each by its own rule, added up; part of it rests on the AI's own proposals"
    if high > low:
        text += f"; it saves between {_usd(low)} and {_usd(high)} a month, and the figure shown is the lowest"
    members = _whole(found.get("members"))
    if members and members > many:
        text += f"; {many} of {members} resources are priced"
    skipped = _whole(found.get("skipped"))
    if skipped:
        text += f"; {_count(skipped, 'thing')} that it named could not be checked and {'is' if skipped == 1 else 'are'} not counted"
    advisor = _number(found.get("advisorUsd"))
    if advisor is not None and advisor > 0:
        text += f"; Azure Advisor's own estimate for it is {_usd(advisor)} a month, and the two are not added"
    return text


def saved(facts: object, cost: float | None = None) -> Saved | None:
    """The figure that a case keeps, read again: None when there is none or when a number is not as it should be (a high above the cost of the bill lines or of the finding, a low of nothing,
    a form that is not one). The level follows from the form, never from a word of the digest."""
    found = _change(facts).get("price")
    if not isinstance(found, Mapping):
        return None
    low, high, bill = (_number(found.get(key)) for key in ("lowUsd", "highUsd", "billUsd"))
    form = found.get("form")
    if low is None or high is None or bill is None or form not in SHOWN or not 0 < low <= high <= bill + 0.005 or (cost is not None and high > cost + 0.005):
        return None
    return Saved(round(low, 2), round(high, 2), EXPECTED if form == "none" else SCENARIO, _basis(found, str(form), low, high), round(bill, 2), _whole(found.get("lines")) or 0)


def point(facts: object, cost: float | None = None) -> float | None:
    """The figure that a case counts: the low end of what code computed from the bill lines."""
    found = saved(facts, cost)
    return found.low if found is not None else None


def missing(facts: object) -> str:
    """The plain sentence that says why a finding that states a change has no figure, or "" when it has none to explain."""
    word = _change(facts).get("missing")
    return WHY.get(word, "") if isinstance(word, str) else ""


def refused(facts: object) -> bool:
    """Whether the finding stated a change and code could not price it (the AI not naming any bill line is no such change)."""
    word = _change(facts).get("missing")
    return isinstance(word, str) and word in WHY and word != "none"


# -- what the second AI is shown ----------------------------------------------------------------------------------------------------------------------

def view(change: Change | None, priced: Priced, registry: Mapping, word: Callable[[object], str | None], limit: int, skip: Collection[str]) -> dict | None:
    """The change in typed form for the Skeptic: for each resource its rule, the cost of the bill lines that it rests on, and at most `limit` of them with their words (as the tools show them:
    `word` is the check of the tools), their cost and how steady it was; or the word that says why it has no figure. Not the AI's words for a person."""
    if change is None:
        return None
    effects: list[dict] = []
    for handle in dict.fromkeys(effect.handle for effect in change.effects):
        row = priced.rows.get(handle)
        if handle in skip or (row is None and handle not in priced.why):
            continue
        if row is None:
            effects.append({"handle": handle, "unpriced": priced.why[handle]})
            continue
        lines = []
        for name in row.meters[:limit]:
            meter = registry[name]
            numbers = shape(meter, meter.start + dt.timedelta(days=meter.days))
            lines.append({"meter": name, "words": [word(text) or "other" for text in meter.words], "usd": round(meter.usd, 2), "days": numbers["days"],
                          "cv": None if numbers["cv"] is None else round(numbers["cv"], 3)})
        more = {"remains": [round(1 - row.away[1], 4), round(1 - row.away[0], 4)]} if row.form == "assumed" and row.away is not None else {}
        effects.append({"handle": handle, "form": row.form, "usd": row.bill, "lines": lines, **row.said, **more})
    return {"action": change.action, "effects": effects}
