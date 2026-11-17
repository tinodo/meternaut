"""What an investigation looked at, kept as one compact record for the page "What the AI looked at" (docs/proposals/23-what-the-ai-looked-at.md).

Made from what the run knows: the toolbox's log and handles, the cost that the Watch read, the Investigator's phrases and each finding. The AI's text is cleaned of ids and of the names that
the tools showed; no name, tag or id of a resource is kept. A fault here is one line in the log, and the investigation goes on.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Iterable, Mapping

from . import agents, roles
from .brief import without_ids
from .models import INVESTIGATION_TOUCHES, InvestigationRecord
from .toolbox import type_of_id, type_word

if TYPE_CHECKING:
    from .detectors import Context
    from .investigate import Finding, Investigation

LOG = logging.getLogger("meternaut.activity")
OTHER = "other"  # the cost that is tied to no kind of resource
MAX_KIND = 80  # a kind of resource that is longer than this is `other`
MAX_KINDS = 40  # the dearest kinds of the cost that a record keeps
NAME = re.compile(r"\w+(?:[.-]\w+)*")  # a word that may be a resource's name: a full stop or a dash ends it unless a letter follows
MAX_DOUBTS, DOUBT, NOTE = 2, 120, 160  # objections of the second AI that a record keeps, and the longest of one of them and of a note of code
# What each tool does to the kinds that it names or whose handles it is given (a letter of INVESTIGATION_TOUCHES). The other tools show a list and touch no kind: a test fails for one that is in neither.
VERBS = {"list_resources": "l", "cost_lines": "l", "cost_history": "l", "measure": "m", "metric_summary": "m", "describe": "d", "children": "d", "data_volume": "d", "data_readers": "d",
         "data_writers": "d", "metric_split": "s"}
LEFT = ("unknown", "unproven", "repeated", "guarded", "recent", "capped")  # why resources of a finding left it (investigate.Finding)


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


def touched(toolbox: object, costed: Iterable[str] = ()) -> dict[str, str]:
    """The kinds that the tools touched, with the letters of what was done. A failed call touched nothing; a kind that no handle or cost line (`costed`) shows to exist is not counted."""
    handles = getattr(toolbox, "handles", {})
    exist = {type_word(r.resource_type) for r in handles.values()} | set(costed)
    found: dict[str, set[str]] = {}
    for call in getattr(toolbox, "log", []):
        arguments = call.get("arguments") if isinstance(call, dict) and call.get("ok") else None
        verb = VERBS.get(call.get("name")) if isinstance(arguments, dict) else None
        if verb is None:
            continue
        asked = arguments.get("handles") if isinstance(arguments.get("handles"), list) else [arguments.get("handle")]
        kinds = ({type_word(arguments.get("type"))} & exist) | {type_word(getattr(handles.get(h), "resource_type", None)) for h in asked if isinstance(h, str)}
        for kind in kinds - {None}:
            found.setdefault(kind, set()).add(verb)
    return {kind: "".join(letter for letter in INVESTIGATION_TOUCHES if letter in verbs) for kind, verbs in sorted(found.items())}


def costs_by_kind(contexts: Mapping[str, "Context"]) -> tuple[dict[str, float], int]:
    """The 30-day cost that the run read in US dollars, by kind (`other` for what has none; a credit is left out), and in how many subscriptions it was read."""
    by_kind: dict[str, float] = {}
    read = 0
    for context in contexts.values():
        if context.costs is None or context.currency not in ("USD", None):
            continue
        read += 1
        for resource_id, amount in context.costs.items():
            kind = type_of_id(resource_id) if resource_id else None
            kind = kind if kind and len(kind) <= MAX_KIND else OTHER
            by_kind[kind] = by_kind.get(kind, 0.0) + amount
    return {kind: amount for kind, amount in by_kind.items() if amount > 0}, read


def end_of(out: "Investigation") -> str:
    """How the Investigator's run ended (models.INVESTIGATION_ENDS): held by the harness, out of time or of calls (also with no answer to read), answered, or failed."""
    answer = out.answer
    if out.held:
        return "refused"
    if getattr(answer, "out_of_time", False):
        return "time"
    refused = any(isinstance(call, dict) and call.get("refused") for call in getattr(answer, "calls", ()))
    return "calls" if refused else "answered" if out.ran else "failed"


def stop_of(harness: object) -> str:
    """The code that the harness gave for refusing or stopping a run, or empty."""
    return next((record.reason for record in getattr(harness, "records", []) if record.outcome in ("refused", "stopped")), "")


def entry_of(finding: "Finding", names: frozenset[str]) -> dict:
    """One finding as the record keeps it; a dropped one says how many resources the AI listed."""
    kept = finding.reason is None
    verdict = finding.verdict
    entry = {"n": finding.number, "basis": finding.basis, "proposal": finding.proposal, "sure": finding.confidence if finding.basis else None,
             "resources": len(finding.items) if kept else finding.claimed, "usd": finding.covered_usd, "says": plain(finding.summary, agents.MAX_SUMMARY, names),
             "verdict": verdict.verdict if verdict else "", "doubts": [plain(o, DOUBT, names) for o in (verdict.objections if verdict else ())[:MAX_DOUBTS]], "kept": kept,
             "left": {name: count for name in LEFT if (count := getattr(finding, name))}, "fates": dict(finding.fates),
             "note": plain(finding.note or ("" if finding.basis else finding.reason), NOTE, names)}
    return {key: value for key, value in entry.items() if value not in ("", [], {}, None)}


def record_of(s: object, out: "Investigation", contexts: Mapping[str, "Context"], *, trigger: str, at: str) -> InvestigationRecord:
    """The record of an investigation that was tried. The trigger is `timer`, or `request` for any other."""
    st, harness = s.settings, getattr(s, "harness", None)
    names = frozenset(r.name.lower() for r in getattr(out.toolbox, "handles", {}).values() if len(r.name) >= 4)
    costs, costed = costs_by_kind(contexts)
    done = touched(out.toolbox, costs)
    end = end_of(out)
    dearest = sorted(costs.items(), key=lambda item: (-item[1], item[0]))[:MAX_KINDS]
    return InvestigationRecord(
        run_id=s.history.run_id, at=at, trigger="timer" if trigger == "timer" else "request" if trigger else "", investigator=st.foundry_model_investigator,
        skeptic=st.foundry_model_skeptic, calls=out.tool_calls, max_calls=harness.budget.tool_calls if harness is not None else st.investigate_max_calls, tokens=out.tokens, seconds=out.seconds,
        max_seconds=int(st.investigate_max_seconds), end=end, answered=out.ran or bool(out.findings), stop=stop_of(harness) if end == "refused" else "", note=plain(out.note, NOTE, names),
        examined=tuple(plain(p, agents.MAX_EXAMINED_TEXT, names) for p in out.examined), findings=tuple(entry_of(f, names) for f in out.findings),
        kinds=tuple([kind, round(amount, 2), done.get(kind, "")] for kind, amount in dearest), looked=len(done), cost_total=round(sum(costs.values()), 2) if costed else None,
        cost_looked=round(sum(amount for kind, amount in costs.items() if kind in done), 2), subs=len(st.subscriptions), subs_costed=costed)


def keep(s: object, out: "Investigation", contexts: Mapping[str, "Context"], *, trigger: str, at: str) -> None:
    """Keeps the record of an investigation that was tried (not one that is off, or has no store). It never raises: a fault is one line in the log with its kind and never its text."""
    extras = getattr(s, "extras", None)
    if out.off or extras is None:
        return
    try:
        extras.store.investigation_put(record_of(s, out, contexts, trigger=trigger, at=at))
    except Exception as error:  # noqa: BLE001 (nothing that goes wrong here may stop the Watch)
        LOG.warning("the record of the investigation could not be kept (%s)", type(error).__name__)
