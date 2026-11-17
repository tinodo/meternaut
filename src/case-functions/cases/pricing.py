"""What a finding's change would save, worked out by code from the bill and from nothing that an AI wrote as an amount (rules 26 (d) and 30).

The Investigator states a change in typed form (the key `change` of a finding): an action and, for each resource that it covers, the meters that the change would shrink (the handles that
cost_meters gave for that resource, cases/meters.py) and what remains of them. A saving is a figure a month about what is to come, so the base is what those meters cost a month NOW, from their daily
cost at two rates (cases/meters.py `rates`): the last 7 closed days, and the mean since the first day that has a cost (or over a month, for a meter that is older than the window). The low end of the
saving rests on the lower rate and the high end on the higher one, times the share that goes away, never above what the resource costs a month on the same rates. How much remains is one of a few
forms that code can check against what the tools showed in the same run:

  none           everything that the meters bill goes away: a figure that follows from the bill alone (Expected)
  quantity       how much of one billed meter is used goes from the quantity that the meter shows to a quantity that the AI proposes, in the meter's own unit (Scenario)
  ratio          a count or a size goes from a number that a tool returned for the resource to a number that the AI proposes (Scenario)
  share_of_days  the resource is needed on some days of every so many, which the AI states (Scenario)
  assumed        a share that the AI assumes, as a low and a high, always said to be the AI's own (Scenario)
  alternative    a switch to something else, priced from a public price list: refused until that exists

A ratio on a property is right only when the meter follows that property, which code cannot know: a meter that bills the units above those that are included is not halved when the units are. The
quantity of a meter is what the bill measures, so it is checked against the meter itself.

A meter that no tool showed, that belongs to another resource or to a whole type, or that gives no rate (a read of under 7 days, or fewer than 3 days of cost) is not counted; a bill line is counted
once in a finding; what could not be checked is said, and no figure is made of it. The point that a case keeps is the low end. The digest is numbers and closed words, which the brief reads again.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Collection, Iterable, Mapping, NamedTuple, Sequence

from .meters import FEWEST, MONTH, WEEK, Meter, Rates, rates, shape
from .roles import clean_text

KEY = "change"  # the key of the facts of a case
ACTIONS = ("remove", "reduce", "switch", "schedule", "commit", "none")
FORMS = ("none", "quantity", "ratio", "share_of_days", "assumed", "alternative")
ALLOWED = {"remove": ("none",), "reduce": ("quantity", "ratio", "assumed"), "schedule": ("share_of_days", "quantity", "assumed"), "switch": ("alternative", "assumed"), "commit": ("assumed",)}
SHOWN = ("none", "quantity", "ratio", "share_of_days", "assumed", "mixed")  # the forms that a digest may have: mixed is a sum of resources whose rules differ
MAX_EFFECTS, MAX_METERS, MAX_HOW = 60, 40, 300
UNEVEN = 1.0  # a meter whose daily cost spreads by more than its mean is uneven: a rate worked out from it is a rough guide (a statistic about the bill, not a rule about what is waste)
MATERIAL = 0.1  # an uneven meter makes a figure rough only when it carries at least this share of what the figure rests on
ALIKE = 0.05  # two rates that differ by no more than this share of the larger are the same one
EXPECTED, SCENARIO = "Expected", "Scenario"
METER = re.compile(r"m[0-9]{1,4}")
NAME = re.compile(r"[A-Za-z][A-Za-z0-9 ._/-]{0,63}")  # the name of a property or a measurement as a tool returned it: a plain word, which a sentence may hold
UNIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._/,-]{0,23}")  # the unit of a meter as Cost Management words it ("1 Hour", "100 GB/Month"): plain characters, which a sentence may hold
WHY = {
    "none": "No saving was worked out: the AI did not name the bill lines that a change would shrink (a bill line that no resource owns has no handle to name).",
    "lines": f"No saving was worked out: the bill lines that the AI named were not found for this resource, or they have less than {FEWEST} days of cost to give a rate.",
    "remains": "No saving was worked out: what would remain of the bill lines was not stated in a form that code can check.",
    "currency": "No saving was worked out: the cost is not in US dollars.",
    "nothing": f"No saving was worked out: the bill lines that the AI named cost nothing in the last {WEEK} days.",
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
    """The figure of one resource: US dollars a month (low and high), what the meters that it rests on cost a month at the higher of their two rates (`bill`), at the rate of the last 7 days (`week`) and at
    the mean since their first day (`since`, None when no read can say it), how many there are and what remains of them, how many days ago the youngest that began inside the window began (`life`)
    and how many are uneven."""

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
    week: float
    since: float | None
    life: int | None
    uneven: int

    @property
    def level(self) -> str:
        return EXPECTED if self.form == "none" else SCENARIO

    @property
    def base(self) -> float:
        return self.week if self.since is None else min(self.week, self.since)

    def digest(self, advisor: float | None = None) -> dict:
        out: dict = {"lowUsd": self.low, "highUsd": self.high, "billUsd": self.bill, "weekUsd": self.week, "lines": self.lines, "resources": 1, "form": self.form, **self.said}
        if self.away is not None and self.form == "assumed":
            out["away"] = list(self.away)
        for key, value in (("sinceUsd", self.since), ("life", self.life), ("uneven", self.uneven or None), ("skipped", self.skipped or None), ("advisorUsd", advisor)):
            if value is not None:
                out[key] = value
        return out


@dataclass
class Priced:
    """What code made of a change: a row for each resource that has a figure, and the word of WHY for each that has none."""

    action: str
    rows: dict[str, Row] = field(default_factory=dict)
    why: dict[str, str] = field(default_factory=dict)


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
    if form == "quantity":
        start, target = _number(said.get("from")), _number(said.get("to"))
        return (form, target / start, target / start, {"from": start, "to": target}) if start is not None and target is not None and 0 <= target < start else "remains"
    if form == "ratio":
        start, target, name = _number(said.get("from")), _number(said.get("to")), said.get("on")
        if start is None or target is None or not 0 <= target < start or not _cited(block, name, start) or not NAME.fullmatch(str(name)):
            return "remains"
        return form, target / start, target / start, {"from": start, "to": target, "on": name}
    if form == "share_of_days":
        days, span = _whole(said.get("days")), _whole(said.get("of"))
        if days is None or span is None or not 1 <= days < span <= 31:
            return "remains"
        return form, days / span, days / span, {"days": days, "span": span}
    low, high = _number(said.get("low")), _number(said.get("high"))
    return (form, low, high, {}) if low is not None and high is not None and 0 <= low <= high <= 1 else "remains"


class Part(NamedTuple):
    """One effect of a resource: what remains (the form, the smallest and the largest share, the numbers that the AI stated), what its meters cost a month at the rate of the last 7 days (`week`) and at the
    mean since their first day (`since`, None when no read can say it), the meters that count, how many were not counted, how many days ago the youngest that began inside the window began (`life`) and how
    many are uneven."""

    form: str
    least: float
    most: float
    said: dict
    week: float
    since: float | None
    names: tuple[str, ...]
    skipped: int
    life: int | None
    uneven: int

    @property
    def low(self) -> float:
        return self.week if self.since is None else min(self.week, self.since)

    @property
    def high(self) -> float:
        return self.week if self.since is None else max(self.week, self.since)


def _part(effect: Effect, action: str, block: Mapping, registry: Mapping, seen: set) -> Part | str:
    """One effect as a Part, or the word of WHY."""
    found = _remains(effect.remains, action, block)
    if isinstance(found, str):
        return found
    used: list[tuple[str, Rates, Meter]] = []
    skipped = 0
    for name in effect.meters:
        meter = registry.get(name) if METER.fullmatch(name) else None
        if not isinstance(meter, Meter) or meter.scope != effect.handle or _number(meter.usd) is None:
            skipped += 1
        elif meter.usd == 0:
            continue  # it cost nothing: that is a reason of its own, not a lack of days
        elif (got := rates(meter)) is None:
            skipped += 1
        elif (meter.scope, meter.words) not in seen and got.high > 0:
            seen.add((meter.scope, meter.words))  # a bill line counts once, however many calls showed it
            used.append((name, got, meter))
    if not effect.meters:
        return "none"
    if not used:
        return "lines" if skipped else "nothing"
    form, least, most, said = found
    if form == "quantity":  # a quantity is the quantity of one meter, in its own unit, and is the one that the tool showed for it
        if len(effect.meters) != 1 or not math.isclose(said["from"], used[0][2].quantity, rel_tol=1e-6, abs_tol=0.0):
            return "remains"
        unit = (used[0][2].words or ("",))[-1]
        said = {**said, **({"unit": unit} if UNIT.fullmatch(unit) else {})}
    since = math.fsum(got.week if got.since is None else got.since for _, got, _ in used) if any(got.since is not None for _, got, _ in used) else None
    total = math.fsum(got.high for _, got, _ in used)
    return Part(form, least, most, said, math.fsum(got.week for _, got, _ in used), since, tuple(name for name, _, _ in used), skipped,
                min((got.life for _, got, _ in used if got.began), default=None), sum(1 for _, got, _ in used if got.cv is not None and got.cv > UNEVEN and got.high >= MATERIAL * total))


def _own(meters: Iterable[Meter]) -> tuple[float, float] | None:
    """What a resource costs a month at the lower and at the higher of its two rates, from every meter of it that a tool showed (a bill line once, a credit taking its share off)."""
    seen: set = set()
    week, since = [], []
    for meter in meters:
        got = rates(meter)
        if got is not None and meter.words not in seen:
            seen.add(meter.words)
            week.append(got.week)
            since.append(got.week if got.since is None else got.since)
    return (min(math.fsum(week), math.fsum(since)), max(math.fsum(week), math.fsum(since))) if week else None


def _row(handle: str, parts: list[Part], cost: float | None, failed: int, own: tuple[float, float] | None) -> Row | str:
    low = math.fsum(part.low * (1 - part.most) for part in parts)
    high = math.fsum(part.high * (1 - part.least) for part in parts)
    week = math.fsum(part.week for part in parts)
    since = math.fsum(part.week if part.since is None else part.since for part in parts) if any(part.since is not None for part in parts) else None
    life = min((part.life for part in parts if part.life is not None), default=None)
    if own is not None:  # never above what the resource costs a month on the same rates
        low, high = max(0.0, min(low, own[0])), min(high, own[1])
    if cost is not None:  # its own 30 days bound a rate only as far as the days of life allow: a meter of 4 days has a rate of 7.5 times what the 30 days show
        reach = cost * MONTH / min(WEEK, life or WEEK)
        low, high = min(low, reach), min(high, reach)
    if high <= 0 or math.fsum(part.low for part in parts) <= 0:
        return "nothing"
    alike = len({(part.form, part.least, part.most, tuple(sorted(part.said.items()))) for part in parts}) == 1
    form = parts[0].form if alike else "mixed"
    away = (round(1 - parts[0].most, 4), round(1 - parts[0].least, 4)) if alike else None
    return Row(handle, round(low, 2), round(high, 2), round(math.fsum(part.high for part in parts), 2), sum(len(part.names) for part in parts), form, parts[0].said if alike else {}, away,
               failed + sum(part.skipped for part in parts), tuple(name for part in parts for name in part.names), round(week, 2), None if since is None else round(since, 2), life,
               sum(part.uneven for part in parts))


def price(change: Change | None, handles: Collection[str], toolbox: object, costs: Mapping[str, float | None], blocked: Mapping[str, str] | None = None) -> Priced:
    """The rows of a change for the resources `handles` of a finding. `toolbox` holds the meters (`meters`) and the evidence of the run, `costs` the 30-day cost of each resource (None when it was not
    read) and `blocked` the resources that have no figure from outside, by the word of WHY (a cost that is not in US dollars)."""
    out = Priced(change.action if change is not None else "")
    if change is None:
        return out
    registry, evidence = getattr(toolbox, "meters", None), getattr(toolbox, "evidence", None)
    registry, evidence = registry if isinstance(registry, Mapping) else {}, evidence if isinstance(evidence, Mapping) else {}
    owned: dict[str, list[Meter]] = {}
    for meter in registry.values():
        if isinstance(meter, Meter):
            owned.setdefault(meter.scope, []).append(meter)
    seen: set = set()
    parts: dict[str, list[Part]] = {}
    failed: dict[str, list[str]] = {}
    for effect in change.effects:
        if effect.handle not in handles:
            continue  # an effect for a resource that is not one of the finding's is not read
        if blocked and effect.handle in blocked:
            failed.setdefault(effect.handle, []).append(blocked[effect.handle])
        else:
            block = evidence.get(effect.handle)
            got = _part(effect, change.action, block if isinstance(block, Mapping) else {}, registry, seen)
            if isinstance(got, str):
                failed.setdefault(effect.handle, []).append(got)
            else:
                parts.setdefault(effect.handle, []).append(got)
    for handle in dict.fromkeys([*parts, *failed]):
        row = _row(handle, parts[handle], costs.get(handle), len(failed.get(handle, ())), _own(owned.get(handle, ()))) if handle in parts else failed[handle][0]
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
    keys = ("form", "from", "to", "on", "unit", "days", "span", "away")
    alike = len({tuple(str(price.get(key)) for key in keys) for price in prices}) == 1
    rated = all("weekUsd" in price for price in prices)  # a digest made before the rates has none, and a sum of such digests has none either
    total = {key: round(math.fsum(price.get(key) or 0 for price in prices), 2) for key in ("lowUsd", "highUsd", "billUsd", *(("weekUsd",) if rated else ()))}
    if rated and any("sinceUsd" in price for price in prices):
        total["sinceUsd"] = round(math.fsum(price.get("sinceUsd", price["weekUsd"]) for price in prices), 2)
    lives, uneven = [price["life"] for price in prices if "life" in price], sum(price.get("uneven") or 0 for price in prices)
    price = {**total, "lines": sum(price.get("lines") or 0 for price in prices), "resources": len(prices), "members": members,
             **({key: prices[0][key] for key in keys if key in prices[0]} if alike else {"form": "mixed"}), **({"life": min(lives)} if rated and lives else {}), **({"uneven": uneven} if uneven else {})}
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
    bill: float  # what the bill lines that the figure rests on cost: a month at the lower of their two rates, or in the last 30 days for a figure made before the rates
    lines: int
    per: str = f"in the last {MONTH} days"  # the period of `bill`


def _usd(value: float) -> str:
    return f"${value:,.2f}"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _rate(found: Mapping) -> str:
    """Which rate the figure rests on, in words, from the numbers of the digest. A digest made before the rates rests on the last 30 days."""
    week, since, life = _number(found.get("weekUsd")), _number(found.get("sinceUsd")), _whole(found.get("life"))
    if week is None:
        return f"over the last {MONTH} days"
    if since is not None and abs(week - since) > ALIKE * max(week, since):
        return f"at the lower of the {WEEK}-day rate and the " + ("rate since it began" if life else f"{MONTH}-day total")
    return f"at the rate since it began {life} days ago" if life and life < WEEK and (_whole(found.get("resources")) or 1) == 1 else f"at the rate of the last {WEEK} days"


def _basis(found: Mapping, form: str, low: float, high: float) -> str:
    lines, many, members = _whole(found.get("lines")) or 1, _whole(found.get("resources")) or 1, _whole(found.get("members"))
    whose = f"{many} of {members} resources" if members and members > many else _count(many, "resource")  # how many of the resources are priced comes first: a card cuts the end of the line
    text = f"the {_count(lines, 'bill line')} of {whose} that the change would {'remove' if form == 'none' else 'shrink'}, {_rate(found)}"
    start, target, days, span, away, on, unit = (found.get(key) for key in ("from", "to", "days", "span", "away", "on", "unit"))
    if form == "quantity":
        text += (f", scaled by the change from {start:,.10g} to {target:,.10g}" if _number(start) is not None and _number(target) is not None else ", scaled by the change in the quantity that the AI proposed")
        text += f" (unit: {unit})" if isinstance(unit, str) and UNIT.fullmatch(unit) else ""
        text += ": the AI's target"
    elif form == "ratio":
        name = f" in {on}" if isinstance(on, str) and len(on) <= 24 and NAME.fullmatch(on) else ""
        text += (f", scaled by the change{name} from {start:g} to {target:g}" if _number(start) is not None and _number(target) is not None else ", scaled by the change that the AI proposed")
        text += ": the AI's target"
    elif form == "share_of_days":
        text += f", scaled to {days} days of every {span}: the AI's proposal" if _whole(days) and _whole(span) else ", scaled to the days that it is needed: the AI's proposal"
    elif form == "assumed":
        pair = [round(share * 100) for share in away] if isinstance(away, list) and len(away) == 2 and all(_number(share) is not None for share in away) else []
        text += (f", of which {pair[0]}" + (f" to {pair[1]}" if pair[1] != pair[0] else "") + " percent would go away" if pair else ", of which a share would go away")
        text += ": the AI's own assumption, not checked by code"
    elif form == "mixed":
        text += ", each by its own rule; part rests on the AI's own proposals"
    if high > low:
        text += f"; {_usd(low)} to {_usd(high)} a month"
    uneven = _whole(found.get("uneven"))
    if uneven:
        text += f"; {_count(uneven, 'bill line')} {'is' if uneven == 1 else 'are'} uneven from day to day"
    skipped = _whole(found.get("skipped"))
    if skipped:
        text += f"; {_count(skipped, 'named thing')} not counted"
    advisor = _number(found.get("advisorUsd"))
    if advisor is not None and advisor > 0:
        text += f"; Azure Advisor's {_usd(advisor)} is not added"
    return text


def saved(facts: object, cost: float | None = None) -> Saved | None:
    """The figure that a case keeps, read again: None when there is none or when a number is not as it should be (a high above what the bill lines cost on their higher rate, or above what the finding
    cost in 30 days allows for the days of life of its youngest line, a low of nothing, a form that is not one). The level follows from the form, never from a word of the digest."""
    found = _change(facts).get("price")
    if not isinstance(found, Mapping):
        return None
    low, high, bill = (_number(found.get(key)) for key in ("lowUsd", "highUsd", "billUsd"))
    form, life = found.get("form"), found.get("life")
    if low is None or high is None or bill is None or form not in SHOWN or not 0 < low <= high <= bill + 0.005:
        return None
    rated = "weekUsd" in found
    bases = [_number(found.get(key)) for key in ("weekUsd", "sinceUsd") if key in found]
    if rated and (any(base is None or base <= 0 for base in bases) or ("life" in found and (_whole(life) is None or not FEWEST <= life <= MONTH))):
        return None
    if cost is not None and high > (cost * MONTH / min(WEEK, life or WEEK) if rated else cost) + 0.005:
        return None
    return Saved(round(low, 2), round(high, 2), EXPECTED if form == "none" else SCENARIO, _basis(found, str(form), low, high), round(min(bases) if rated else bill, 2), _whole(found.get("lines")) or 0,
                 "a month" if rated else f"in the last {MONTH} days")


def point(facts: object, cost: float | None = None) -> float | None:
    """The figure that a case counts: the low end of what code computed from the bill lines."""
    found = saved(facts, cost)
    return found.low if found is not None else None


def stated(facts: object) -> bool:
    """Whether the facts of a case hold the change that a finding states, priced or not: the case then says what it is worth now, its own price or why it has none."""
    return bool(_change(facts))


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
    """The change in typed form for the Skeptic: for each resource its rule, what the bill lines that it rests on cost a month at the lower of their two rates (`usd`) and at each of them, and at most
    `limit` of them with their words (as the tools show them: `word` is the check of the tools), what each cost in its window, what it costs a month at the rate of its last 7 days and at the mean since
    its first day (None when its read cannot say it), the days of life and how steady it was; or the word that says why it has no figure. Not the AI's words for a person."""
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
            numbers, got = shape(meter, meter.start + dt.timedelta(days=meter.days)), rates(meter)
            lines.append({"meter": name, "words": [word(text) or "other" for text in meter.words], "usd": round(meter.usd, 2), "days": numbers["days"], "week": round(got.week, 2),
                          "since": None if got.since is None else round(got.since, 2), "life": got.life, "cv": None if got.cv is None else round(got.cv, 3)})
        more = {"remains": [round(1 - row.away[1], 4), round(1 - row.away[0], 4)]} if row.form == "assumed" and row.away is not None else {}
        said = {key: (word(value) or "other" if key == "unit" else value) for key, value in row.said.items()}  # the unit of a meter is a word of the platform, shown through the check of the tools
        effects.append({"handle": handle, "form": row.form, "usd": round(row.base, 2), "week": row.week, "since": row.since, "lines": lines, **said, **more})
    return {"action": change.action, "effects": effects}
