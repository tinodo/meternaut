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
from .toolbox import ERRORS, TOOLS, type_word

FLOOR_PERCENT = 95  # the dearest kinds that together make this share of the cost of the last 30 days have a beat of their own; the cheaper ones are left to the last beat
BEAT_KINDS = 2  # the most kinds of one beat: the dearest one that no beat has, and at most one more of the same service (it was three: the dearest things then had a third of a session)
CATCH_ALL_KINDS = 8  # the kinds that the last beat names when it holds what the others did not
SEED_RESOURCES = 5  # the resources whose picture code reads for a beat before the Investigator starts (cases/dossier.py takes five at most)
SEED_HOURLY = 3  # of those, the dearest few have their picture at the grain of the hour, which adds the peak and the 95th percentile of the finer buckets (what a thing must carry decides what it needs); the others, at the day
SEED_CALLS = SEED_RESOURCES + 2  # the reads that this takes at most: a listing for each kind that is seeded, and a picture at the hour and one at the day
MIN_SECONDS = 90  # a beat does not start with less time than this (its reads and a step of the model), and not with fewer tokens than MIN_TOKENS
SOFT_SHARE = 0.5  # the share of the seconds of a beat after which its tool calls are refused and the agent is told to write its answer (it was 0.7 for the whole run): the model and its tools have this much, and the rest is for the answer
ANSWER_SECONDS = 60  # what the agent has after that to write its answer: the hard time of a beat is its soft time and this (never more than the seconds of the beat), so that the rounds of an answer always fit
SALVAGE_SECONDS = 25  # a beat that is cut off (its hard time, its tokens, or three rounds that gave no text) is asked once more to write its answer, with no tool, and this long to do it
SALVAGE_MIN_LEFT = 40  # and only when at least this many seconds are left in the time of the beats
SEED_ESTIMATE_SECONDS = 60  # what the reads of a beat are expected to take before any beat has been read; later, what the beats before it took (on average)
SEED_PICTURE_SECONDS = 25  # the time that each picture that code reads for a beat may take (the toolbox's budget of one measurement, 60 seconds, is lowered to this for those two calls): a part that did not finish is `unread` and named, and the Investigator may read it itself
STEP_SECONDS = 30  # nor does it ask the model when less than this is left after the reads that code made for it: one step could not end inside its hard time
OPEN_SECONDS = 480  # the time that one open session has for tool calls, as it had it when the investigation had 600 seconds: the way back (INVESTIGATE_BEATS=1) is the old behaviour
MIN_TOKENS = 60_000  # nor with fewer tokens than this: one step of the model costs 13 to 20 thousand, and a beat that starts with less cannot ask and be answered inside its hard limit (harness.beat_limit)
CARRY_CHARS = 3000  # what a beat is told of the beats before it, at most
CARRY_ITEMS = 6
BILLING = "billing-only"  # stands in the ranking for the lines of the bill that no resource owns; it has no slash, so it is never a kind
PRELOAD = "preload"  # the name that the line of the History gives to the read ahead that code makes of the resources of a beat's kinds (Toolbox.preload); it is no tool of the agent
REFUSED_LINES = 8  # the tool calls that a beat asked for after its budget was used up, and that get a line each in the History; the line of the beat counts the others
BUDGET_USED_UP = "budget-used-up"  # what the client answers a call that it does not run (cases/foundry.py)
CALL_ERRORS = ERRORS + (BUDGET_USED_UP,)  # the words that a line of a tool call may give as the reason why a call has no answer: the toolbox's own, and the refusal of a budget


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
    """What code read for a beat before the Investigator started: how many resources each kind has, the handles of the dearest ones, their pictures (the answers of the tool `profile`: the dearest few at
    the grain of the hour, the others at the day) and how many reads gave no answer."""

    counts: dict[str, int] = field(default_factory=dict)
    handles: list[str] = field(default_factory=list)
    pictures: list[dict] | None = None
    failed: int = 0


def _said(text: object) -> dict:
    try:
        found = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return {}
    return found if isinstance(found, dict) and found and "error" not in found else {}


def seed(call: Callable[[str, dict], str], beat: Beat, warm: Callable[[Sequence[str]], object] | None = None) -> Seed:
    """Reads, with the tools that the Investigator has and through the same toolbox, the dearest resources of the beat's kinds, one of each kind first, then the next dearest of each, SEED_RESOURCES in all,
    and their pictures: the dearest SEED_HOURLY at the grain of the hour and the others at the day, so that two calls of `profile` with handles that the Investigator could pass itself. It costs no model
    tokens, and what it shows is registered as evidence like any answer of a tool. `warm` reads the resources of the kinds at the same time first (the toolbox's `preload`), so that the listings find
    them in its caches; a read ahead that fails leaves the listings to make their own."""
    found, lists = Seed(), []
    if warm is not None and len(beat.kinds) > 1:
        try:
            warm(beat.kinds[:SEED_RESOURCES])
        except Exception:  # noqa: BLE001 (nothing is lost by a read ahead that did not work: the listings read for themselves)
            pass
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
    for grain, handles in (("hour", found.handles[:SEED_HOURLY]), ("day", found.handles[SEED_HOURLY:])):
        if not handles:
            continue
        picture = _said(call("profile", {"handles": handles, "days": None, "grain": grain}))
        if picture:
            found.pictures = [*(found.pictures or []), picture]
        else:
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
    salvaged: bool = False
    examined: list[str] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)


def times(allowed: float) -> tuple[float, float]:
    """The soft time and the hard time of a beat that has `allowed` seconds for the model and its tool calls, on top of the reads that code made for it: its tool calls are refused after SOFT_SHARE of
    them, and it has ANSWER_SECONDS more to write its answer, never more than `allowed` in all. The seconds of the beat are the setting, whatever the reads took."""
    soft = SOFT_SHARE * allowed
    return soft, min(soft + ANSWER_SECONDS, allowed)


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


def _error_of(text: object) -> str | None:
    """None when a tool answered, else the word of the toolbox that says why not; a word that is not on its list is `other`, and an answer that is no JSON object is `failed`."""
    try:
        answer = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        return "failed"
    if "error" not in answer:
        return None
    return answer["error"] if answer["error"] in CALL_ERRORS else "other"


def call_fields(name: object, arguments: object, text: object, seconds: float, *, refused: bool = False) -> dict:
    """The fields of the History line of one tool call (`investigation.call`): words and numbers that code checks, and no text of the estate or of the agent. The tool (a name that the toolbox has, else
    `unknown`), the resource type (`resourceType`, as the lines of the cases call it: not `type`, which is the kind of the line) when the arguments hold one that has the shape of a platform type
    and never any other text of them, how many handles and metrics it asked about, whether it worked and, when it did not, the word of the toolbox that says why, the size of the answer and the
    seconds that it took. A call that was refused for a budget ran nothing: it says so and has no answer and no time."""
    asked = arguments if isinstance(arguments, dict) else {}
    handles, metrics, kind = asked.get("handles"), asked.get("metrics"), asked.get("type")
    count = len(handles) if isinstance(handles, list) else 1 if isinstance(asked.get("handle"), str) else 0
    measured = len(metrics) if isinstance(metrics, list) else 1 if isinstance(asked.get("metric"), str) else 0
    word = type_word(kind.lower()) if isinstance(kind, str) else None
    error = BUDGET_USED_UP if refused else _error_of(text)
    return {"tool": name if isinstance(name, str) and name in TOOLS else "unknown", **({"resourceType": word} if word else {}), "handles": min(count, 999), **({"metrics": min(measured, 99)} if measured else {}),
            "ok": error is None, **({"error": error} if error else {}), "chars": 0 if refused or not isinstance(text, str) else len(text), "seconds": 0.0 if refused else round(max(0.0, float(seconds)), 1)}
