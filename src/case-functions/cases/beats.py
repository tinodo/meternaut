"""The beats of an investigation (docs/proposals/25-beats.md): the estate is looked at in parts, the dearest first, each part in a short session of the Investigator that starts from
pictures that code has already read. A single long session starves: its model reads everything said so far again at every step, so it costs the square of its steps, and it ends where its
budget ends, whatever is left. Here code chooses the parts from what the kinds of resource cost, reads the picture of the dearest resources of each part, and tells each part what the parts
before it concluded.

Everything is made from the bill, by dollars, and from what the tools showed. No kind of resource, no measurement and no rule of what is waste is written in this file: a kind comes in as a
word that the cost lines gave, and goes out as the same word.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from itertools import zip_longest
from types import SimpleNamespace
from typing import Callable, Mapping, Sequence

from . import activity
from .detectors import Context

FLOOR_PERCENT = 95  # the dearest kinds that together make this share of the cost of the last 30 days have a beat of their own; the cheaper ones are left to the last beat
BEAT_KINDS = 3  # the most kinds of one beat, of one service when they belong together
CATCH_ALL_KINDS = 8  # the kinds that the last beat names when it holds what the others did not
SEED_RESOURCES = 5  # the resources whose picture code reads for a beat before the Investigator starts (cases/dossier.py takes five at most)
SEED_CALLS = SEED_RESOURCES + 1  # the reads that this takes at most: a listing for each kind that is seeded, and one picture
MIN_SECONDS = 45  # a beat does not start with less time than this, and not with fewer tokens than MIN_TOKENS
MIN_TOKENS = 30_000
CARRY_CHARS = 3000  # what a beat is told of the beats before it, at most
CARRY_ITEMS = 6
BILLING = "billing-only"  # stands in the ranking for the lines of the bill that no resource owns; it has no slash, so it is never a kind


@dataclass(frozen=True)
class Beat:
    """One part of the estate: its kinds of resource, as the cost lines name them, dearest first. `billing` says that the lines of the bill that no resource owns belong to it, and `rest` how
    many more kinds the last beat holds than it names. A beat with no kind and no billing is open: the whole estate, as one session looks at it."""

    number: int = 1
    kinds: tuple[str, ...] = ()
    billing: bool = False
    rest: int = 0
    of: int = 1

    @property
    def open(self) -> bool:
        return not self.kinds and not self.billing


def spend(contexts: Mapping[str, Context]) -> tuple[dict[str, float], float]:
    """What the Watch read of the cost lines, in US dollars: the cost of each kind of resource, and the cost of the lines that no resource owns. A subscription whose cost was not read in dollars counts for nothing."""
    kinds, _ = activity.costs_by_kind(contexts)
    return kinds, sum(max(0.0, c.costs.get("", 0.0)) for c in contexts.values() if c.costs is not None and c.currency in ("USD", None))


def _service(kind: str) -> str:
    return kind.partition("/")[0]


def plan(costs: Mapping[str, float], unowned: float, limit: int) -> list[Beat]:
    """The beats, at most `limit`, from the dearest kinds down to FLOOR_PERCENT of the cost. A beat opens with the dearest kind that no beat has and takes the dearer-first kinds of the same
    service after it, BEAT_KINDS at most; the lines that no resource owns are ranked like a kind and make a beat of their own. What is left, the kinds below the floor and those that do not
    fit in `limit` beats, is the last beat, which names the dearest CATCH_ALL_KINDS of them. Nothing is known to cost anything: no beat, and the caller makes one open beat."""
    ranked = sorted([(usd, kind) for kind, usd in costs.items() if usd > 0] + ([(unowned, BILLING)] if unowned > 0 else []), key=lambda entry: (-entry[0], entry[1]))
    total = sum(usd for usd, _ in ranked)
    if limit < 1 or total <= 0:
        return []
    cut, running = len(ranked), 0.0
    for index, (usd, _) in enumerate(ranked):
        if running * 100 >= FLOOR_PERCENT * total:
            cut = index
            break
        running += usd
    order = [kind for _, kind in ranked]
    named, left = order[:cut], order[cut:]
    groups: list[list[str]] = []
    while named:
        group = [named.pop(0)]
        if group[0] != BILLING:
            for kind in [k for k in named if k != BILLING and _service(k) == _service(group[0])][: BEAT_KINDS - 1]:
                group.append(kind)
                named.remove(kind)
        groups.append(group)
    fits = not left and len(groups) <= limit
    chosen = groups if fits else groups[: limit - 1]
    placed = {kind for group in chosen for kind in group}
    rest = [] if fits else [kind for kind in order if kind not in placed]
    beats = [Beat(number, tuple(k for k in group if k != BILLING), BILLING in group) for number, group in enumerate(chosen, 1)]
    if rest:
        kinds = [k for k in rest if k != BILLING]
        beats.append(Beat(len(beats) + 1, tuple(kinds[:CATCH_ALL_KINDS]), BILLING in rest, max(0, len(kinds) - CATCH_ALL_KINDS)))
    return [replace(beat, of=len(beats)) for beat in beats]


@dataclass
class Seed:
    """What code read for a beat before the Investigator started: how many resources each kind has, the handles of the dearest ones, their picture (the answer of the tool `profile`) and how many reads gave no answer."""

    counts: dict[str, int] = field(default_factory=dict)
    handles: list[str] = field(default_factory=list)
    pictures: dict | None = None
    failed: int = 0


def _said(text: object) -> dict:
    try:
        found = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return {}
    return found if isinstance(found, dict) and found and "error" not in found else {}


def seed(call: Callable[[str, dict], str], beat: Beat) -> Seed:
    """Reads, with the tools that the Investigator has and through the same toolbox, the dearest resources of the beat's kinds, one of each kind first, then the next dearest of each, SEED_RESOURCES in all,
    and the picture of those. It costs no model tokens, and what it shows is registered as evidence like any answer of a tool."""
    found, lists = Seed(), []
    for kind in beat.kinds[:SEED_RESOURCES]:
        listing = _said(call("list_resources", {"type": kind, "order_by": "cost", "limit": SEED_RESOURCES, "offset": None}))
        if not listing:
            found.failed += 1
            continue
        total = listing.get("total")
        if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
            found.counts[kind] = total
        rows = listing.get("rows") if isinstance(listing.get("rows"), list) else []
        lists.append([row[0] for row in rows if isinstance(row, list) and row and isinstance(row[0], str)])
    found.handles = [handle for rank in zip_longest(*lists) for handle in rank if handle][:SEED_RESOURCES]
    if found.handles:
        found.pictures = _said(call("profile", {"handles": found.handles, "days": None, "grain": None})) or None
        if found.pictures is None:
            found.failed += 1
    return found


@dataclass
class Result:
    """What one beat came to: its numbers and how it ended (a word of models.INVESTIGATION_ENDS), the pictures that code read for it, how many of its kinds its tools touched, what the
    Investigator said that it examined (cleaned) and a typed line for each finding that it wrote: the basis, the proposal and the handles that the tools showed."""

    beat: Beat
    calls: int = 0
    max_calls: int = 0
    tokens: int = 0
    seconds: int = 0
    end: str = "failed"
    seeded: int = 0
    looked: int = 0
    found: int = 0
    note: str = ""
    examined: list[str] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)


def looked(toolbox: object, beat: Beat, start: int) -> int:
    """How many of the beat's kinds the tools touched in the calls of the log from `start` on."""
    part = SimpleNamespace(handles=getattr(toolbox, "handles", {}), log=list(getattr(toolbox, "log", []))[start:])
    return len(activity.touched(part, set(beat.kinds)))


def carry(results: Sequence[Result]) -> list[dict]:
    """What a beat is told of the beats before it, as typed lines that fit in CARRY_CHARS: for each, its kinds and, when it gave an answer, the basis, the proposal and the handles of its findings and what
    it said that it examined; when it gave none, only that it did not conclude. The oldest phrases go first when it is too long."""
    lines = [{"beat": r.beat.number, "kinds": list(r.beat.kinds), **({"billingOnly": True} if r.beat.billing else {}),
              **({"findings": r.lines[:CARRY_ITEMS], "examined": r.examined[:CARRY_ITEMS]} if r.end != "failed" else {"concluded": False})} for r in results]
    while len(json.dumps(lines, separators=(",", ":"))) > CARRY_CHARS:
        for key in ("examined", "findings"):
            line = next((line for line in lines if line.get(key)), None)
            if line is not None:
                line[key] = line[key][:-1]
                break
        else:
            break
    return lines


def beat_input(beat: Beat, calls: int, seeded: Seed | None, earlier: Sequence[dict]) -> str:
    """What the Investigator is given for a beat: the budget of tool calls, the beat (its number, how many there are, its kinds), how many resources each kind has, the pictures that code read, and what the
    beats before it concluded. An open beat is given the budget alone, as one session always was."""
    where: dict = {"number": beat.number, "of": beat.of, "focus": list(beat.kinds)}
    if beat.billing:
        where["billingOnly"] = True
    if beat.rest:
        where["moreKinds"] = beat.rest
    body: dict = {"budget": {"toolCalls": calls}}
    if not beat.open:
        body["beat"] = where
    if seeded is not None and seeded.counts:
        body["counts"] = seeded.counts
    if seeded is not None and seeded.pictures:
        body["pictures"] = seeded.pictures
    if earlier:
        body["earlier"] = list(earlier)
    return json.dumps(body, sort_keys=True, separators=(",", ":"))
