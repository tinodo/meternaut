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
  alternative    a switch of one billed meter to a price of the same service that the tool for alternatives showed for it, in the same unit: what remains is the alternative's list price over what the bill
                 pays for a unit now, with the rate that the bill pays against list carried over and, for the other end of a range, at list prices alone (Scenario). The digest keeps the plain name of
                 each end (`now`, `to`), and a switch whose alternative cannot be named in plain words is not priced

A ratio on a property is right only when the meter follows that property, which code cannot know: a meter that bills the units above those that are included is not halved when the units are. The
quantity of a meter is what the bill measures, so it is checked against the meter itself. The quantity of an alternative is the same quantity at the same monthly rate as the cost that it replaces, so the
share that remains is one number for every rate: the price of the alternative per unit over the list price of the meter's own line, like for like (the rate that the bill pays against list is carried over),
and over what the bill paid per unit over the window for the other end of the range (list prices alone); both must save, and a meter whose own list price the tool did not find is not priced. The price must be
one that the tool showed in this run for that meter, in its unit, one price for the whole quantity, and above nothing.

A meter that no tool showed, that belongs to another resource or to a whole type, or that gives no rate (a read of under 7 days, or fewer than 3 days of cost) is not counted; a bill line is counted
once in a finding; what could not be checked is said, and no figure is made of it. The point that a case keeps is the low end. The digest is numbers and closed words, which the brief reads again.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Collection, Iterable, Mapping, NamedTuple, Sequence

from .costs import money
from .meters import FEWEST, MONTH, WEEK, Meter, Rates, rates, shape
from .proposals import label
from .roles import MAX_CITED_NAME, clean_text

KEY = "change"  # the key of the facts of a case
ACTIONS = ("remove", "reduce", "switch", "schedule", "commit", "none")
FORMS = ("none", "quantity", "ratio", "share_of_days", "assumed", "alternative")
ALLOWED = {"remove": ("none",), "reduce": ("quantity", "ratio", "assumed"), "schedule": ("share_of_days", "quantity", "assumed"), "switch": ("alternative", "assumed"), "commit": ("assumed",)}
SHOWN = ("none", "quantity", "ratio", "share_of_days", "assumed", "alternative", "mixed")  # the forms that a digest may have: mixed is a sum of resources whose rules differ
MAX_EFFECTS, MAX_METERS, MAX_HOW = 60, 40, 300
UNEVEN = 1.0  # a meter whose daily cost spreads by more than its mean is uneven: a rate worked out from it is a rough guide (a statistic about the bill, not a rule about what is waste)
MATERIAL = 0.1  # an uneven meter makes a figure rough only when it carries at least this share of what the figure rests on
ALIKE = 0.05  # two rates that differ by no more than this share of the larger are the same one
DIFFER = 0.25  # two rates that differ by more than this share of the larger are far apart: the figure is then a Scenario whatever its form, because the bill alone does not say what it will be
EXPECTED, SCENARIO = "Expected", "Scenario"
METER = re.compile(r"m[0-9]{1,4}")
NAME = re.compile(rf"[A-Za-z][A-Za-z0-9 ._/-]{{0,{MAX_CITED_NAME - 1}}}")  # the name of a property or a measurement as a tool returned it: a plain word, which a sentence may hold
UNIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._/,-]{0,23}")  # the unit of a meter as Cost Management words it ("1 Hour", "100 GB/Month"): plain characters, which a sentence may hold
PLAIN = re.compile(r"[A-Za-z0-9]+(?: [A-Za-z0-9]+){0,5}")  # a word of an alternative that the Skeptic is shown, beside the check of the tools: letters, digits and single spaces, at most 6 words and 40 characters
WHY = {
    "none": "No saving was worked out, because the AI did not say which charges on the bill the change would shrink.",
    "lines": f"No saving was worked out. The charges that the AI named were not found for this resource, or they have less than {FEWEST} days of cost to work from.",
    "remains": "No saving was worked out, because the AI did not say what would remain of those charges in a form that Meternaut can check.",
    "currency": "No saving was worked out, because the cost is not in US dollars.",
    "nothing": f"No saving was worked out, because the charges that the AI named cost nothing in the last {WEEK} days.",
    "credit": "No saving was worked out, because what the resource gets back on its bill is as much as the charges that the AI named cost.",
    "alternative": "No saving was worked out. Meternaut did not find the alternative that the AI named as a price for this charge in this run, or its price changes with the quantity, or Meternaut cannot name it in plain words.",
    "units": "No saving was worked out, because the units differ, so the alternative cannot be priced against this charge.",
    "listed": "No saving was worked out, because Meternaut does not know the list price of the current meter, so it cannot compare the alternative with it like for like.",
    "dearer": "No saving was worked out, because the alternative costs as much as this charge or more, both at what the bill pays and at list prices.",
    "quantity": "No saving was worked out, because this charge has no cost per unit to price the alternative by.",
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
    """The figure of one resource: US dollars a month (low and high), what the meters that it rests on cost a month at the higher of their rates (`bill`), at the rate of the last 7 days (`week`) and at
    the mean since their first day (`since`, None when no read can say it), and at a typical day (`steady`, only when that is the lowest of the rates), how many there are and what remains of them, how
    many days ago the youngest that began inside the window began (`life`) and how many are uneven."""

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
    steady: float | None
    alts: tuple = ()  # for a switch, what the Skeptic is shown of the alternative: the meter, the words of the price, its list price, the rate that the bill pays against list and the shares that remain
    after: float | None = None  # for a switch, what the same use costs a month on the alternative at the rate of `low`: the lowest rate of each meter times the larger share that remains

    @property
    def level(self) -> str:
        return EXPECTED if self.form == "none" and _firm(self.digest()) else SCENARIO

    @property
    def base(self) -> float:
        return min(self.week, self.week if self.since is None else self.since, self.week if self.steady is None else self.steady)

    def digest(self, advisor: float | None = None) -> dict:
        out: dict = {"lowUsd": self.low, "highUsd": self.high, "billUsd": self.bill, "weekUsd": self.week, "lines": self.lines, "resources": 1, "form": self.form, **self.said}
        if self.away is not None and self.form == "assumed":
            out["away"] = list(self.away)
        for key, value in (("sinceUsd", self.since), ("steadyUsd", self.steady), ("life", self.life), ("uneven", self.uneven or None), ("skipped", self.skipped or None),
                           ("switched", (len(self.alts) or None) if self.form == "mixed" else None), ("afterUsd", self.after), ("advisorUsd", advisor)):
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
        offer = said.get("price")
        return (form, 0.0, 0.0, {"offer": offer}) if isinstance(offer, str) else "alternative"
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
    """One effect of a resource: what remains (the form, the smallest and the largest share, the numbers that the AI stated), what its meters cost a month at the rate of the last 7 days (`week`), at the
    mean since their first day (`since`, None when no read can say it) and at a typical day (`steady`, the week for a meter with too few days to have one), the meters that count, how many were not
    counted, how many days ago the youngest that began inside the window began (`life`) and how many are uneven."""

    form: str
    least: float
    most: float
    said: dict
    week: float
    since: float | None
    steady: float
    names: tuple[str, ...]
    skipped: int
    life: int | None
    uneven: int
    alts: tuple = ()

    @property
    def low(self) -> float:
        return min(self.week, self.week if self.since is None else self.since, self.steady)

    @property
    def high(self) -> float:
        return self.week if self.since is None else max(self.week, self.since)


class Market(NamedTuple):
    """What the run showed of the price list (the registers `prices`, `retail` and `offers` of cases/toolbox.py): the lines by price handle, the list price of the line of each meter, and the price
    handles that were shown for each meter. Read, never written."""

    prices: Mapping
    retail: Mapping
    offers: Mapping


def _name(text: object, word: Callable[[object], str | None] | None) -> str:
    """A word of a price as a person reads it: the text when it is plain (_plain) and passes the check of the tools, else nothing. Without that check no word is kept."""
    return text if word is not None and _plain(text, word) == text else ""


def _switch(effect: Effect, offer: str, used: Sequence[tuple[str, Rates, Meter]], market: Market, word: Callable[[object], str | None] | None) -> tuple[float, float, dict, tuple] | str:
    """The smallest and the largest share of what the meter costs that remains after a switch to the price `offer`, the numbers and the plain names of both ends that go into the digest and what the
    Skeptic is shown, or the word of WHY. The same quantity at the same monthly rate as the cost that it replaces is the cost per unit that the bill paid over the window (`paid`) against the alternative's
    price: the share is one number for every rate. Like for like, the alternative costs its list price over the list price of the meter's own line (`retail`: the rate that the bill pays against list is
    carried over, whether it is above 1 or below); at list prices alone it costs its list price over `paid`. Both ends must save: a share of 1 or more at either is no saving, and a meter whose own list
    price is not known is not priced. A request must name its target: the meter name of the alternative's line, or else its SKU, that is plain and is not the name that the bill already has; a switch
    whose alternative cannot be named is not priced."""
    if len(effect.meters) != 1:
        return "remains"
    name, _, meter = used[0]
    held = market.offers.get(name)
    line = market.prices.get(offer) if isinstance(held, (set, frozenset, list, tuple)) and offer in held else None
    usd, unit, service, tiers = (getattr(line, key, None) for key in ("usd", "unit", "service", "tiers"))
    if _number(usd) is None or usd <= 0 or tiers != 1 or len(meter.words) != 6 or service != meter.words[0]:
        return "alternative"
    if unit != meter.words[5]:
        return "units"
    retail = _number(market.retail.get(name))
    if retail is None or retail <= 0:
        return "listed"
    if not (_number(meter.quantity) and meter.quantity > 0 and meter.usd > 0):
        return "quantity"
    paid = meter.usd / meter.quantity
    shares = (usd / retail, usd / paid)
    least, most = min(shares), max(shares)
    if most >= 1:
        return "dearer"
    words = tuple(getattr(line, key, "") for key in ("product", "sku", "meter"))
    target = next((text for text in (words[2], words[1]) if _name(text, word) and text != meter.words[2]), "")
    if not target:
        return "alternative"
    ratio = round(paid / retail, 4)
    named = {"to": target, **({"now": meter.words[2]} if _name(meter.words[2], word) else {})}
    return least, most, {"offer": offer, "list": usd, "ratio": ratio, **named}, ({"meter": name, "words": words, "list": usd, "ratio": ratio, "remains": (least, most)},)


def _part(effect: Effect, action: str, block: Mapping, registry: Mapping, seen: set, word: Callable[[object], str | None] | None, market: Market) -> Part | str:
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
    alts: tuple = ()
    if form == "alternative":  # a switch is priced for one meter, from a price that the tool showed for it
        switched = _switch(effect, said["offer"], used, market, word)
        if isinstance(switched, str):
            return switched
        least, most, said, alts = switched
    if form == "quantity":  # a quantity is the quantity of one meter, in its own unit, and is the one that the tool showed for it
        if len(effect.meters) != 1 or not math.isclose(said["from"], used[0][2].quantity, rel_tol=1e-5, abs_tol=0.0):  # the tool shows a quantity with six significant digits
            return "remains"
        unit = (used[0][2].words or ("",))[-1]
        said = {**said, **({"unit": unit} if word is not None and word(unit) == unit and UNIT.fullmatch(unit) else {})}  # the unit passes the check of the tools, and is short
    since = math.fsum(got.week if got.since is None else got.since for _, got, _ in used) if any(got.since is not None for _, got, _ in used) else None
    total = math.fsum(got.high for _, got, _ in used)
    return Part(form, least, most, said, math.fsum(got.week for _, got, _ in used), since, math.fsum(got.week if got.steady is None else got.steady for _, got, _ in used),
                tuple(name for name, _, _ in used), skipped, min((got.life for _, got, _ in used if got.began), default=None),
                sum(1 for _, got, _ in used if got.cv is not None and got.cv > UNEVEN and got.high >= MATERIAL * total), alts)


def _own(meters: Iterable[Meter]) -> tuple[float, float] | None:
    """What a resource costs a month at the lower and at the higher of its two rates, from every meter of it that a tool showed (a bill line once). A meter that cost less than nothing in its window is a
    credit: it takes off what it gave back in the window, scaled to a month, and never its rate of the last days, which a single day of it would make a hundred and fifty a month."""
    seen: set = set()
    week, since = [], []
    for meter in meters:
        if meter.words in seen or _number(meter.usd) is None:
            continue
        got = None if meter.usd < 0 else rates(meter)
        if meter.usd < 0 or got is not None:
            seen.add(meter.words)
            week.append(meter.usd * MONTH / meter.days if got is None else got.week)
            since.append(week[-1] if got is None or got.since is None else got.since)
    return (min(math.fsum(week), math.fsum(since)), max(math.fsum(week), math.fsum(since))) if week else None


def _rule(part: Part) -> tuple:
    """What makes the rule of a part the one of another: for a switch the price that it goes to (the rate of the bill that was carried over differs from one meter to the next), else the form and the
    shares."""
    if part.form == "alternative":
        return part.form, part.said.get("offer"), part.said.get("list")
    return part.form, part.least, part.most, tuple(sorted(part.said.items()))


def _row(handle: str, parts: list[Part], cost: float | None, failed: int, own: tuple[float, float] | None) -> Row | str:
    low = math.fsum(part.low * (1 - part.most) for part in parts)
    high = math.fsum(part.high * (1 - part.least) for part in parts)
    week = math.fsum(part.week for part in parts)
    since = math.fsum(part.week if part.since is None else part.since for part in parts) if any(part.since is not None for part in parts) else None
    steady = math.fsum(part.steady for part in parts)
    life = min((part.life for part in parts if part.life is not None), default=None)
    if high <= 0 or math.fsum(part.low for part in parts) <= 0:
        return "nothing"
    if own is not None:  # never above what the resource costs a month on the same rates
        capped = max(0.0, min(low, own[0])), min(high, own[1])
        if capped[1] <= 0 or capped[0] <= 0 < low:
            return "credit"
        low, high = capped
    if cost is not None:  # its own 30 days bound a rate only as far as the days of life allow: a meter of 4 days has a rate of 7.5 times what the 30 days show
        reach = cost * MONTH / min(WEEK, life or WEEK)
        low, high = min(low, reach), min(high, reach)
        if high <= 0:
            return "nothing"
    alike = len({_rule(part) for part in parts}) == 1
    form = parts[0].form if alike else "mixed"
    said = {key: value for key, value in parts[0].said.items() if not (form == "alternative" and key in ("ratio", "now", "to") and len({part.said.get(key) for part in parts}) > 1)} if alike else {}
    away = (round(1 - max(part.most for part in parts), 4), round(1 - min(part.least for part in parts), 4)) if alike else None
    return Row(handle, round(low, 2), round(high, 2), round(math.fsum(part.high for part in parts), 2), sum(len(part.names) for part in parts), form, said, away,
               failed + sum(part.skipped for part in parts), tuple(name for part in parts for name in part.names), round(week, 2), None if since is None else round(since, 2), life,
               sum(part.uneven for part in parts), round(steady, 2) if steady < min(week, week if since is None else since) - 0.005 else None, tuple(alt for part in parts for alt in part.alts),
               round(math.fsum(part.low * part.most for part in parts), 2) if alike and form == "alternative" else None)


def _held(toolbox: object, name: str) -> Mapping:
    found = getattr(toolbox, name, None)
    return found if isinstance(found, Mapping) else {}


def _plain(text: object, word: Callable[[object], str | None]) -> str:
    """A word of an alternative as the Skeptic is shown it: the text when it passes the check of the tools and is made of letters, digits and single spaces, in at most 6 words and 40 characters
    (a sentence in Title Case passes the check of the tools and is not a name), else `other`."""
    return text if isinstance(text, str) and len(text) <= 40 and PLAIN.fullmatch(text) and word(text) == text else "other"


def price(change: Change | None, handles: Collection[str], toolbox: object, costs: Mapping[str, float | None], blocked: Mapping[str, str] | None = None,
          word: Callable[[object], str | None] | None = None) -> Priced:
    """The rows of a change for the resources `handles` of a finding. `toolbox` holds the meters (`meters`) and the evidence of the run, and the prices of the list that the tool for alternatives showed
    (`prices`, `retail`, `offers`), `costs` the 30-day cost of each resource (None when it was not read), `blocked` the resources that have no figure from outside, by the word of WHY (a cost that is not
    in US dollars), and `word` the check that the tools make of a word of a meter (none: a unit is not kept, and no switch is priced, because its alternative cannot be named)."""
    out = Priced(change.action if change is not None else "")
    if change is None:
        return out
    registry, evidence = _held(toolbox, "meters"), _held(toolbox, "evidence")
    market = Market(_held(toolbox, "prices"), _held(toolbox, "retail"), _held(toolbox, "offers"))
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
            got = _part(effect, change.action, block if isinstance(block, Mapping) else {}, registry, seen, word, market)
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


def _switched(price: Mapping) -> int:
    """How many bill lines of a digest rest on an alternative."""
    if price.get("form") == "alternative":
        return _whole(price.get("lines")) or 0
    held = _whole(price.get("switched"))
    return held if held is not None and held > 0 else 0


def combine(digests: Sequence[object], members: int) -> dict | None:
    """The `change` of the case of a group from those of its resources: the sums of the figures, and the rule only when it is the same for all of them (for a switch: the same price, whatever rate of
    the bill each carried over, which is kept when it is the same). A figure that is a sum of rules says how many of its bill lines rest on an alternative. None when there is none."""
    kept = [item for item in digests if isinstance(item, Mapping)]
    if not kept:
        return None
    out: dict = {"action": kept[0].get("action"), **({"how": how} if (how := next((item["how"] for item in kept if item.get("how")), "")) else {})}
    prices = [item["price"] for item in kept if isinstance(item.get("price"), Mapping)]
    if not prices:
        return {**out, "missing": next((item["missing"] for item in kept if item.get("missing") in WHY), "none")}
    keys = ("form", "from", "on", "unit", "days", "span", "away", "offer", "list") + (() if prices[0].get("form") == "alternative" else ("to",))  # the `to` of a switch is a name, which one price can have twice
    alike = len({tuple(str(price.get(key)) for key in keys) for price in prices}) == 1
    rated = all("weekUsd" in price for price in prices)  # a digest made before the rates has none, and a sum of such digests has none either
    total = {key: round(math.fsum(price.get(key) or 0 for price in prices), 2) for key in ("lowUsd", "highUsd", "billUsd", *(("weekUsd",) if rated else ()))}
    if rated and any("sinceUsd" in price for price in prices):
        total["sinceUsd"] = round(math.fsum(price.get("sinceUsd", price["weekUsd"]) for price in prices), 2)
    if rated and any("steadyUsd" in price for price in prices):
        total["steadyUsd"] = round(math.fsum(price.get("steadyUsd", min(price["weekUsd"], price.get("sinceUsd", price["weekUsd"]))) for price in prices), 2)
    if alike and all("afterUsd" in price for price in prices):  # a digest made before it has none, and a sum with one of those has none either
        total["afterUsd"] = round(math.fsum(price["afterUsd"] for price in prices), 2)
    lives, uneven = [price["life"] for price in prices if "life" in price], sum(price.get("uneven") or 0 for price in prices)
    price = {**total, "lines": sum(price.get("lines") or 0 for price in prices), "resources": len(prices), "members": members,
             **({key: prices[0][key] for key in keys if key in prices[0]} if alike else {"form": "mixed"}), **({"life": min(lives)} if rated and lives else {}), **({"uneven": uneven} if uneven else {})}
    for key in ("ratio", "now", "to"):  # what each resource carries of its own is kept only when it is the same for all
        if alike and key in prices[0] and len({str(item.get(key)) for item in prices}) == 1:
            price[key] = prices[0][key]
    if price["form"] == "mixed" and (switched := sum(_switched(item) for item in prices)):
        price["switched"] = switched
    skipped = sum(price.get("skipped") or 0 for price in prices)
    return {**out, "price": {**price, **({"skipped": skipped} if skipped else {})}}


def _change(facts: object) -> Mapping:
    found = facts.get(KEY) if isinstance(facts, Mapping) else None
    return found if isinstance(found, Mapping) else {}


class Saved(NamedTuple):
    low: float
    high: float
    level: str
    basis: str  # the sentences that say what the figure rests on, from closed words and numbers: no text of the estate
    bill: float  # what the bill lines that the figure rests on cost: a month at the lower of their two rates, or in the last 30 days for a figure made before the rates
    lines: int
    per: str = f"in the last {MONTH} days"  # the period of `bill`


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _firm(found: Mapping) -> bool:
    """Whether a figure follows from the bill alone: no line that is uneven, and the rates that the digest holds within DIFFER of each other. A digest made before the rates holds none, and does."""
    held = [number for key in ("weekUsd", "sinceUsd", "steadyUsd") if (number := _number(found.get(key))) is not None]
    return not _whole(found.get("uneven")) and (not held or min(held) >= (1 - DIFFER) * max(held))


def _when(found: Mapping) -> str:
    """Which days the figure counts, as the start of a sentence, from the numbers of the digest. A digest made before the rates counts the last 30 days."""
    week, since, steady, life = _number(found.get("weekUsd")), _number(found.get("sinceUsd")), _number(found.get("steadyUsd")), _whole(found.get("life"))
    if week is None:
        return f"Over the last {MONTH} days"
    if steady is not None and steady < (1 - ALIKE) * (week if since is None else min(week, since)):
        return "Counting a typical day,"
    if since is not None and abs(week - since) > ALIKE * max(week, since):
        return f"Counting the lower of the last {WEEK} days and " + ("the time since it began," if life else f"the last {MONTH} days,")
    return f"Since it began {life} days ago," if life and life < WEEK and (_whole(found.get("resources")) or 1) == 1 else f"Over the last {WEEK} days"


def _read(value: object) -> str:
    """A name of a digest as it is read again: plain letters, digits and single spaces, in at most 40 characters, else nothing."""
    return value if isinstance(value, str) and len(value) <= 40 and PLAIN.fullmatch(value) else ""


def _shown(value: float) -> float:
    """A figure as `money` shows it: whole dollars from 100 up, cents below."""
    amount = round(value, 2)
    return float(math.floor(amount + 0.5)) if amount >= 100 else amount


def billed(value: float, unit: object = None) -> str:
    """A quantity as a person says it: "1,440 hours" for the unit "1 Hour", "1,440 units of 100 GB/Month" for any other plain unit, and the bare number when the digest keeps none."""
    number = f"{value:,.10g}"
    if not (isinstance(unit, str) and UNIT.fullmatch(unit)):
        return number
    one = re.fullmatch(r"1 ([A-Za-z]+)", unit)
    return f"{number} {one.group(1).lower()}{'' if value == 1 else 's'}" if one else f"{number} units of {unit}"


def window(found: Mapping) -> str:
    """The days that the quantity of a meter covers: those since it began, when it began inside the window, else the last 30."""
    life = _whole(found.get("life"))
    return f"the {life} days since it began" if life else f"the last {MONTH} days"


def _gone(share: float) -> str:
    return "all of it" if share >= 1 else f"{round(100 * share)} percent of it"


def _basis(found: Mapping, form: str, low: float, high: float, base: float) -> str:
    """What a figure rests on, as whole sentences: what the resource paid over the days that the figure counts (`base`), what the bill shows and what the change would do to it, which number is the bill's
    (Meternaut checked it) and which is the AI's choice (it did not), the range when there is one, and what the figure leaves out. A switch names both ends when the digest holds their names."""
    many, members = _whole(found.get("resources")) or 1, _whole(found.get("members"))
    uneven = _whole(found.get("uneven"))
    who = f"{many} of the {members} resources" if members and members > many else ("this resource" if many == 1 else f"these {many} resources")  # how many of the resources are priced comes first: a card cuts the end of the text
    when = _when(found)
    start, target, days, span, away, on, unit = (found.get(key) for key in ("from", "to", "days", "span", "away", "on", "unit"))
    numbers = _number(start) is not None and _number(target) is not None
    to, now, ratio = _read(target) if form == "alternative" else "", _read(found.get("now")), _number(found.get("ratio"))
    paid = f"{when}{',' if who[0].isdigit() and not when.endswith(',') else ''} {who} paid about {money(base)}{' a month' if _number(found.get('weekUsd')) is not None else ''} for " + (
        "what the change would remove" if form == "none" else now or "what would be switched" if form == "alternative" else "what the change would shrink") + "."
    if form == "quantity":
        text = paid + (f" The bill shows {billed(start, unit)} of it in {window(found)}. The change would lower that to {billed(target, unit)}, which takes away {_gone(1 - target / start)}. "
                       f"The old quantity, {billed(start)}, is the bill's own, and Meternaut checked it. The new quantity, {billed(target)}, is the AI's choice, and Meternaut did not check it."
                       if numbers else " The AI proposes a lower quantity, and Meternaut did not check it.")
    elif form == "ratio":
        name = label(on) if isinstance(on, str) and len(on) <= 24 and NAME.fullmatch(on) else ""
        what = name or "the number"
        text = paid + (f" The change would lower {what} from {start:g} to {target:g}, which takes away {_gone(1 - target / start)}. The old number, {start:g}, is what the tools read{' for ' + name if name else ''}, "
                       f"and Meternaut checked it. The new number, {target:g}, is the AI's choice, and Meternaut did not check it. Meternaut also did not check that the charge falls in step with {what}."
                       if numbers else " The AI proposes a change, and Meternaut did not check it.")
    elif form == "share_of_days":
        text = paid + (f" The AI says it is needed {days} days of every {span}, so the change would turn it off on {span - days} of every {span} days, which takes away {_gone(1 - days / span)}. "
                       "Those days are the AI's own, and Meternaut did not check them." if _whole(days) and _whole(span) else " The AI says it is needed only on some days, and Meternaut did not check that.")
    elif form == "assumed":
        pair = [round(share * 100) for share in away] if isinstance(away, list) and len(away) == 2 and all(_number(share) is not None for share in away) else []
        said = f"{pair[0]}" + (f" to {pair[1]}" if pair[1] != pair[0] else "") + " percent" if pair else "a share"
        text = paid + f" The AI assumes that {said} of that would go away. That is the AI's own assumption, and Meternaut did not check it."
    elif form == "alternative":
        after, goal = _number(found.get("afterUsd")), to or "another price of the same service"
        pct = round(ratio * 100) if ratio is not None and 0 < ratio < 1e9 else 0
        listed = bool(pct) and abs(ratio - 1) < 0.005
        # What remains is said only when it adds up: a credit on the resource, or resources whose rates differ, make the saving something other than what is paid less what remains. It is then the
        # difference of the two amounts that the sentence shows, so that its three amounts add up to the dollar (or the cent) as printed, and the saving is the figure that the page states above it.
        left = round(_shown(base) - _shown(low), 2)
        cost = f"would cost about {money(left)} a month for the same use, so it " if after is not None and abs(base - after - low) < 0.02 and 0 < left == _shown(left) else ""
        text = paid + f" {'At list prices, a' if listed else 'A'} switch to {goal} {cost}would save about {money(low)} a month."
        if not listed:
            text += " " + (f"Your bill pays about {pct} percent of the list price" + (f" of {now}" if now else "") + f". Meternaut prices {to or 'it'} both at its list price and at {pct} percent of it."
                           if pct else f"Meternaut prices {to or 'it'} both at list prices and at the same share of the list prices that your bill pays.")
        text += " Meternaut did not check whether " + ("this resource can be switched to it, or whether it has what this resource needs." if many == 1
                                                      else "these resources can be switched to it, or whether it has what they need.")
    elif form == "mixed":
        text = paid + " Each part of it has its own rule for what would remain. Part of it rests on the AI's own proposals, and Meternaut did not check them."
        text += " Meternaut did not check whether the resources can be switched to the alternatives, or whether those have what the resources need." if (_whole(found.get("switched")) or 0) > 0 else ""
    else:
        text = paid + " That comes from your bill." + ("" if _firm(found) or uneven else f" The cost of {who} has changed over the days that the figure counts, so the figure is less certain.")
    if high > low:
        text += f" The saving could be anywhere from {money(low)} to {money(high)} a month, and Meternaut counts the low end."
    if uneven:
        text += f" {_count(uneven, 'charge')} {'is' if uneven == 1 else 'are'} uneven from day to day{', so the figure is less certain' if form == 'none' else ''}."
    skipped = _whole(found.get("skipped"))
    if skipped:
        text += f" Meternaut could not count {_count(skipped, 'more thing')} that the AI named."
    advisor = _number(found.get("advisorUsd"))
    if advisor is not None and advisor > 0:
        text += f" Azure Advisor's {money(advisor)} is not added."
    return text


def saved(facts: object, cost: float | None = None) -> Saved | None:
    """The figure that a case keeps, read again: None when there is none or when a number is not as it should be (a high above what the bill lines cost on their higher rate, or above what the finding
    cost in 30 days allows for the days of life of its youngest line, a low of nothing, a form that is not one). The level follows from the form and from whether the rates agree, never from a word of
    the digest: Expected only when the figure follows from the bill alone."""
    found = _change(facts).get("price")
    if not isinstance(found, Mapping):
        return None
    low, high, bill = (_number(found.get(key)) for key in ("lowUsd", "highUsd", "billUsd"))
    form, life = found.get("form"), found.get("life")
    if low is None or high is None or bill is None or form not in SHOWN or not 0 < low <= high <= bill + 0.005:
        return None
    rated = "weekUsd" in found
    bases = [_number(found.get(key)) for key in ("weekUsd", "sinceUsd", "steadyUsd") if key in found]
    if rated and (any(base is None or base <= 0 for base in bases) or ("life" in found and (_whole(life) is None or not FEWEST <= life <= MONTH))):
        return None
    if cost is not None and high > (cost * MONTH / min(WEEK, life or WEEK) if rated else cost) + 0.005:
        return None
    base = round(min(bases) if rated else bill, 2)
    return Saved(round(low, 2), round(high, 2), EXPECTED if form == "none" and _firm(found) else SCENARIO, _basis(found, str(form), low, high, base), base, _whole(found.get("lines")) or 0,
                 "a month" if rated else f"in the last {MONTH} days")


def ends(facts: object) -> tuple[str, str]:
    """The plain names of the two ends of a switch that a case keeps, read again: what the bill pays now and what it would switch to, each "" when the digest holds no such name (a digest made before the
    names, a figure that is not a switch, or a word that is not plain). Never text of the estate: the platform's words, which passed the check of the tools when the figure was made."""
    found = _change(facts).get("price")
    return (_read(found.get("now")), _read(found.get("to"))) if isinstance(found, Mapping) and found.get("form") == "alternative" else ("", "")


def one_price(facts: object) -> bool:
    """Whether the figure of a switch that a case keeps is one alternative (named or not), and not a mix of rules: only then is it a switch to one other price."""
    found = _change(facts).get("price")
    return isinstance(found, Mapping) and found.get("form") == "alternative"


def point(facts: object, cost: float | None = None) -> float | None:
    """The figure that a case counts: the low end of what code computed from the bill lines."""
    found = saved(facts, cost)
    return found.low if found is not None else None


def stated(facts: object) -> bool:
    """Whether the facts of a case hold the change that a finding states, priced or not: the case then says what it is worth now, its own price or why it has none."""
    return bool(_change(facts))


def action_of(facts: object) -> str:
    """The action of the change that a finding states in typed form (one of ACTIONS), or "" when it states none."""
    word = _change(facts).get("action")
    return word if isinstance(word, str) and word in ACTIONS else ""


def is_switch(facts: object) -> bool:
    """Whether the change that a finding states is a switch to another price of the list: its action is `switch` (priced from an alternative that the tool showed, or from a share that the AI assumes:
    nothing in the bill checks either), or its figure is a sum of rules that holds an alternative (the group of a mixed change)."""
    price = _change(facts).get("price")
    return action_of(facts) == "switch" or (isinstance(price, Mapping) and _switched(price) > 0)


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
                          "since": None if got.since is None else round(got.since, 2), "steady": None if got.steady is None else round(got.steady, 2), "life": got.life,
                          "cv": None if got.cv is None else round(got.cv, 3)})
        more = {"remains": [round(1 - row.away[1], 4), round(1 - row.away[0], 4)]} if row.form == "assumed" and row.away is not None else {}
        if row.form == "quantity":  # the share is the window's: say when the meter's last week is not the window's mean
            got = rates(registry[row.meters[0]])
            more["moved"] = got.since is not None and abs(got.week - got.since) > DIFFER * max(got.week, got.since)
        said = {key: (word(value) or "other" if key == "unit" else value) for key, value in row.said.items()} if row.form != "alternative" else {}  # the unit of a meter is a word of the platform, shown through the check of the tools
        if row.alts:  # a switch: the words of the price (through the same check), its list price, the rate of the bill against list and the shares that remain
            more["alternatives"] = [{"meter": alt["meter"], "words": [_plain(text, word) for text in alt["words"]], "list": alt["list"], "ratio": alt["ratio"],
                                     "remains": [round(alt["remains"][0], 4), round(alt["remains"][1], 4)]} for alt in row.alts]
        effects.append({"handle": handle, "form": row.form, "usd": round(row.base, 2), "week": row.week, "since": row.since, "lines": lines, **said, **more})
    return {"action": change.action, "effects": effects}
