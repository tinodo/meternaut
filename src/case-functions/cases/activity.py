"""What an investigation looked at, kept as one compact record for the page "What the AI looked at" (docs/proposals/23-what-the-ai-looked-at.md).

Made from what the run knows: the toolbox's log and handles, the kinds in the cost lines that the Watch read, the Investigator's phrases and each finding. The AI's text is cleaned of ids and of the
names that the tools showed; no name, tag, id or amount is kept (the cost lines only order the kinds). The one thing kept of a resource is the hash of its id, when a picture of it was read (`profiled`):
it says that the resource was looked at, so that the next runs look at others first (docs/proposals/25-beats.md). A fault here is one line in the log, and the investigation goes on.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Mapping

from . import agents, roles
from .brief import without_ids
from .memory_store import stamp
from .models import INVESTIGATION_ENDS, INVESTIGATION_TOUCHES, KEPT_INVESTIGATIONS, InvestigationRecord
from .store import MAX_DATA
from .toolbox import type_of_id, type_word

if TYPE_CHECKING:
    from .beats import Result
    from .detectors import Context
    from .investigate import Finding, Investigation

LOG = logging.getLogger("meternaut.activity")
MAX_KIND = 80  # a kind of resource that is longer than this is left out
MAX_KINDS = 20  # the kinds of each list that a record keeps
MAX_FINDINGS = 16  # the findings that a record keeps when it has beats: those of all of them can be more than a row of the store takes, and `more` counts the rest
LOOKED_DAYS = 21  # a resource whose picture a run of these days read, and a kind that its tools touched, count as looked at: the seeds of a beat and the last beat go to what no run of these days looked at first
MAX_PROFILED = 300  # the hashes of the pictures that a record keeps: a run at the budgets of today reads about 160, and 300 are about 4,500 characters of a row of 30,000
BEAT_PHRASES = 3  # what a beat said that it examined, at most as many phrases as this
NAME = re.compile(r"\w+(?:[.-]\w+)*")  # a word that may be a resource's name: a full stop or a dash ends it unless a letter follows
MAX_DOUBTS, DOUBT, NOTE = 2, 120, 160  # objections of the second AI that a record keeps, and the longest of one of them and of a note of code
# What each tool does to the kinds that it names or whose handles it is given (the letters of INVESTIGATION_TOUCHES: a profile measures and describes). The other tools show a list and touch no kind: a test fails for one that is in neither.
VERBS = {"list_resources": "l", "cost_lines": "l", "cost_history": "l", "cost_meters": "l", "measure": "m", "metric_summary": "m", "describe": "d", "children": "d", "data_volume": "d",
         "data_readers": "d", "data_writers": "d", "metric_split": "s", "neighbors": "d", "profile": "md", "changes": "d"}
LEFT = ("unknown", "unproven", "repeated", "guarded", "recent", "capped", "small")  # why resources of a finding left it (investigate.Finding)


def _fit(text: str, size: int) -> str:
    """The start of `text` whose JSON form (ASCII, as Record.to_json writes it) is at most `size` characters."""
    used = 0
    for index, char in enumerate(text):
        used += len(json.dumps(char)) - 2
        if used > size:
            return text[:index]
    return text


def plain(text: object, size: int, names: frozenset[str] = frozenset()) -> str:
    """Text of the AI for a record: cleaned, with no id and none of `names` (what the tools showed), and at most `size` characters of JSON."""
    text = without_ids(roles.clean_text(text, 4 * size))
    if names:
        text = NAME.sub(lambda word: "(name removed)" if word[0].lower() in names else word[0], text)
    return _fit(text, size)


def known(toolbox: object, costs: Mapping[str, float]) -> set[str]:
    """The kinds of resource that the run knows the estate has: those of the handles that the tools showed and of the cost lines."""
    kinds = {type_word(r.resource_type) for r in getattr(toolbox, "handles", {}).values()}
    return {kind for kind in kinds if kind and len(kind) <= MAX_KIND} | set(costs)


def touched(toolbox: object, exist: set[str]) -> dict[str, str]:
    """The kinds among `exist` that the tools touched, with the letters of what was done. A failed call touched nothing. A tool that gives a picture of resources says in its log entry which of them its answer
    held data of (`read`: handle -> the letters of what), and only those are credited, and only for those letters; for any other tool every handle that it was given is."""
    handles = getattr(toolbox, "handles", {})
    found: dict[str, set[str]] = {}
    for call in getattr(toolbox, "log", []):
        arguments = call.get("arguments") if isinstance(call, dict) and call.get("ok") else None
        verb = VERBS.get(call.get("name")) if isinstance(arguments, dict) else None
        if verb is None:
            continue
        read = call.get("read") if isinstance(call.get("read"), dict) else None
        asked = arguments.get("handles") if isinstance(arguments.get("handles"), list) else [arguments.get("handle")]
        credit = [(type_word(arguments.get("type")), verb)]
        credit += [(type_word(getattr(handles.get(h), "resource_type", None)), verb if read is None else "".join(letter for letter in verb if letter in str(read.get(h) or ""))) for h in asked if isinstance(h, str)]
        for kind, letters in credit:
            if kind in exist and letters:
                found.setdefault(kind, set()).update(letters)
    return {kind: "".join(letter for letter in INVESTIGATION_TOUCHES if letter in verbs) for kind, verbs in sorted(found.items())}


def costs_by_kind(contexts: Mapping[str, "Context"]) -> tuple[dict[str, float], int]:
    """The 30-day cost that the run read in US dollars, by kind of resource (a credit and a line of no kind are left out), and in how many subscriptions it was read. It only orders the kinds."""
    by_kind: dict[str, float] = {}
    read = 0
    for context in contexts.values():
        if context.costs is None or context.currency not in ("USD", None):
            continue
        read += 1
        for resource_id, amount in context.costs.items():
            kind = type_of_id(resource_id) if resource_id else None
            if kind and len(kind) <= MAX_KIND:
                by_kind[kind] = by_kind.get(kind, 0.0) + amount
    return {kind: amount for kind, amount in by_kind.items() if amount > 0}, read


def end_of_run(held: bool, answer: object, ran: bool) -> str:
    """How one run of the Investigator ended (models.INVESTIGATION_ENDS): held by the harness, out of time, of tokens or of calls (also with no answer to read), answered, or failed."""
    if held:
        return "refused"
    if getattr(answer, "out_of_time", False):
        return "time"
    if getattr(answer, "out_of_tokens", False):
        return "tokens"
    refused = any(isinstance(call, dict) and call.get("refused") for call in getattr(answer, "calls", ()))
    return "calls" if refused else "answered" if ran else "failed"


def end_of(out: "Investigation") -> str:
    """How the Investigator's work ended. One run: as end_of_run says. Beats: held when the harness held it, else the first of time, tokens and calls that a beat ran out of, else answered, or failed
    when no beat answered."""
    if not out.beats:
        return end_of_run(out.held, out.answer, out.ran)
    ends = {beat.end for beat in out.beats}
    return "refused" if out.held else next((word for word in ("time", "tokens", "calls") if word in ends), "answered" if out.ran else "failed")


def stop_of(harness: object) -> str:
    """The code that the harness gave for refusing or stopping a run, or empty."""
    return next((record.reason for record in getattr(harness, "records", []) if record.outcome in ("refused", "stopped")), "")


def earlier(store: object, now: dt.datetime) -> tuple[frozenset[str], frozenset[str]]:
    """What the runs of the last LOOKED_DAYS days looked at, from their records: the hashes of the resources whose picture was read, and the kinds that their tools touched. Nothing when the store
    cannot be read: the seeds are then the dearest first, as they always were."""
    since = stamp(now - dt.timedelta(days=LOOKED_DAYS))
    try:
        found = [record for record in store.investigations_recent(KEPT_INVESTIGATIONS) if record.at >= since]  # type: ignore[attr-defined]
        return frozenset(word for record in found for word in record.profiled), frozenset(kind for record in found for kind, _ in record.kinds)
    except Exception as error:  # noqa: BLE001 (a store that cannot be read changes the order of the seeds and nothing else)
        LOG.warning("the earlier investigations could not be read (%s)", type(error).__name__)
        return frozenset(), frozenset()


def coverage(toolbox: object) -> tuple[int, int, int]:
    """The counts of a run, for its History line and its note: the resources whose picture it read, those of them that the runs of the last days had not looked at, and all that those runs and this
    one looked at."""
    now, before = getattr(toolbox, "looked_at", frozenset)(), getattr(toolbox, "window", frozenset())
    return len(now), len(now - before), len(now | before)


def looked_note(now: int, new: int, total: int) -> str:
    """The note of a run (counts of `coverage`): how many resources it looked at, how many of them for the first time in LOOKED_DAYS days and, when the runs before it looked at others, how many
    those runs and this one looked at in all."""
    days = f"{LOOKED_DAYS} days"
    first = ("This run looked at no resources" if not now else f"This run looked at 1 resource, {'for' if new else 'not for'} the first time in {days}" if now == 1
             else f"This run looked at {now} resources, {'all' if new == now else 'none' if not new else new} of them for the first time in {days}")
    return f"{first}." + (f" In {days} Meternaut has looked at {total} resource{'' if total == 1 else 's'}." if total > now else "")


def entry_of(finding: "Finding", names: frozenset[str]) -> dict:
    """One finding as the record keeps it; a dropped one says how many resources the AI listed."""
    kept = finding.reason is None
    verdict = finding.verdict
    entry = {"n": finding.number, "basis": finding.basis, "proposal": finding.proposal, "sure": finding.confidence if finding.basis else None,
             "resources": len(finding.items) if kept else finding.claimed, "says": plain(finding.summary, agents.MAX_SUMMARY, names),
             "verdict": verdict.verdict if verdict else "", "doubts": [plain(o, DOUBT, names) for o in (verdict.objections if verdict else ())[:MAX_DOUBTS]], "kept": kept,
             "left": {name: count for name in LEFT if (count := getattr(finding, name))}, "fates": dict(finding.fates),
             "note": plain(finding.note or ("" if finding.basis else finding.reason), NOTE, names)}
    return {key: value for key, value in entry.items() if value not in ("", [], {}, None)}


def beat_of(result: "Result", names: frozenset[str]) -> dict:
    """One beat as the record keeps it: counts, words and kinds, what it said that it examined (cleaned of ids and names), and no amount."""
    beat = result.beat
    return {"n": beat.number, "kinds": [kind for kind in beat.kinds if len(kind) <= MAX_KIND][:MAX_KINDS], "billing": beat.billing, "more": beat.rest, "calls": result.calls, "max_calls": result.max_calls,
            "tokens": result.tokens, "seconds": result.seconds, "end": result.end if result.end in INVESTIGATION_ENDS else "failed", "seeded": result.seeded, "looked": result.looked,
            "found": result.found, "says": [plain(p, agents.MAX_EXAMINED_TEXT, names) for p in result.examined[:BEAT_PHRASES]]}


def fit(record: InvestigationRecord) -> InvestigationRecord:
    """The record with as many findings as a row of the store can take (a record that is too large is not kept at all): the last ones go, and `more` says how many."""
    while len(record.to_json()) > MAX_DATA and record.findings:
        record = replace(record, findings=record.findings[:-1], more=record.more + 1)
    return record


def record_of(s: object, out: "Investigation", contexts: Mapping[str, "Context"], *, trigger: str, at: str, seconds: int) -> InvestigationRecord:
    """The record of an investigation that was tried. The trigger is `timer`, or `request` for any other. The kinds are in the order of their cost lines, the dearest first."""
    st, harness = s.settings, getattr(s, "harness", None)
    names = frozenset(r.name.lower() for r in getattr(out.toolbox, "handles", {}).values() if len(r.name) >= 4)
    costs, costed = costs_by_kind(contexts)
    exist = known(out.toolbox, costs)
    done = touched(out.toolbox, exist)
    end = end_of(out)
    order = sorted(exist, key=lambda kind: (-costs.get(kind, 0.0), kind))
    parts = [beat_of(r, names) for r in out.beats] if any(not r.beat.open for r in out.beats) else []
    return fit(InvestigationRecord(
        run_id=s.history.run_id, at=at, trigger="timer" if trigger == "timer" else "request" if trigger else "", investigator=st.foundry_model_investigator,
        skeptic=st.foundry_model_skeptic, calls=out.tool_calls, max_calls=sum(p["max_calls"] for p in parts) if parts else harness.budget.tool_calls if harness is not None else st.investigate_max_calls,
        tokens=out.tokens, seconds=seconds, max_seconds=int(st.investigate_max_seconds), end=end, answered=out.ran or bool(out.findings), stop=stop_of(harness) if end == "refused" else "",
        note=plain(out.note, NOTE, names), examined=tuple(plain(p, agents.MAX_EXAMINED_TEXT, names) for p in out.examined[: agents.MAX_EXAMINED]),
        findings=tuple(entry_of(f, names) | ({"beat": f.beat} if parts else {}) for f in out.findings[:MAX_FINDINGS]), known=len(exist), looked=len(done),
        kinds=tuple([kind, done[kind]] for kind in order if kind in done)[:MAX_KINDS], unread=tuple(kind for kind in order if kind not in done)[:MAX_KINDS], subs=len(st.subscriptions),
        subs_costed=costed, beats=tuple(parts), more=max(0, len(out.findings) - MAX_FINDINGS), profiled=tuple(sorted(getattr(out.toolbox, "looked_at", frozenset)()))[:MAX_PROFILED]))


def keep(s: object, out: "Investigation", contexts: Mapping[str, "Context"], *, trigger: str, opened: object) -> None:
    """Keeps the record of an investigation that was tried (not one that is off, or has no store), begun at `opened`. It never raises: a fault is one line in the log with its kind and never its text."""
    extras = getattr(s, "extras", None)
    if out.off or extras is None:
        return
    try:
        seconds = out.seconds or int((s.clock() - opened).total_seconds())  # a run that failed before its end has no seconds of its own
        extras.store.investigation_put(record_of(s, out, contexts, trigger=trigger, at=stamp(opened), seconds=seconds))
    except Exception as error:  # noqa: BLE001 (nothing that goes wrong here may stop the Watch)
        LOG.warning("the record of the investigation could not be kept (%s)", type(error).__name__)
