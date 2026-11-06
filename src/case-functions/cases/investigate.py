"""The investigation: two agents in Microsoft Foundry look for waste in the estate, and code checks every word of theirs against what the tools showed.

The Investigator reads the estate through the read-only tools of toolbox.py (handles instead of names, typed numbers instead of text) and ends with one JSON
object of findings. Nothing in it is believed before code has checked it:

- a handle that no tool showed is dropped, and so is a measurement whose total is not the number that the tools returned;
- a finding that claims no usage keeps only the resources whose cited measurements are all nil in what the tools returned;
- the cost of the resources is added up by code from the cost lines, and the agent never supplies a figure;
- the guards of guards.py hold every resource, and a resource with a guard on leaves the finding;
- a second agent, the Skeptic, then tries to break the findings that are left, and decide.py gives each resource its status.

Each resource of a finding that is left becomes one case, so that the History, the notebook and the letters show it like any other case. Nothing here changes
Azure, and the plan of a change is never made here: approvals.create decides that, and it makes none for a case that this module opens.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

from . import agents, decide, guards, roles, wiring
from .approvals import is_fixture
from .arm import scopes_of
from .detectors import Context, Lead
from .foundry import FoundryError
from .guards import Guards
from .http import HttpError
from .memory_store import parse, stamp
from .models import CaseRecord, StoreError
from .roles import DetectiveAnswer, RoleError, SkepticAnswer, clean_text
from .toolbox import Resource, Toolbox

if TYPE_CHECKING:
    from .run import Services

DETECTOR = "investigation"
MAX_CASES = 60  # the cases that one run opens
MAX_ENTRIES = 720  # the entries of metric_evidence that are read: a handful for each of the handles that a finding may hold
MAX_FACT_METRICS = 12  # the measurements that a case keeps
SKEPTIC_ROWS = 8  # the resources of one finding that the Skeptic sees, dearest first
SKEPTIC_METRICS = 6  # the measurements of one resource that the Skeptic sees
SKEPTIC_PROPERTIES = 8  # the properties of one resource that the Skeptic sees
SKEPTIC_CHARS = 30000  # the size of the Skeptic's input
RESERVE_SECONDS = 120.0  # what the Investigator leaves of its time for the checks and the Skeptic, at most
LOG = logging.getLogger("meternaut.investigate")

# What code lets through of what the tools showed, once more: a metric name, a resource type as Azure names one, a word, and the key path of a property.
METRIC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/%()-]{0,98}$")
RESOURCE_TYPE = re.compile(r"^[a-z0-9.]{1,60}(?:/[a-z0-9._-]{1,50}){1,4}$")
WORD = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
PROPERTY_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9.]{0,100}$")


@dataclass
class Item:
    """One resource of a finding, on its way to a case."""

    handle: str
    lead: Lead
    metrics: dict[str, float]  # the entries of the finding that matched the tools: metric name -> the total that the tools returned


@dataclass
class Finding:
    """One finding of the Investigator and what code did to it. `reason` is set when the whole finding was dropped."""

    number: int
    basis: str = ""
    proposal: str = ""
    confidence: float = 0.0
    summary: str = ""
    claimed: int = 0  # the distinct handles that the answer listed
    handles: list[str] = field(default_factory=list)  # the handles that the tools showed, in the finding's order
    cited: dict[str, dict[str, float]] = field(default_factory=dict)
    items: list[Item] = field(default_factory=list)
    unknown: int = 0
    unproven: int = 0
    repeated: int = 0
    recent: int = 0
    guarded: int = 0
    capped: int = 0
    reason: str | None = None
    verdict: SkepticAnswer | None = None
    covered_usd: float | None = None


@dataclass
class Investigation:
    """What the investigation came to. `ran` is true when the Investigator gave an answer that could be read, even one with no finding."""

    ran: bool = False
    note: str = ""  # why it did not run
    cases: int = 0
    proposed: int = 0
    needs_human: int = 0
    dropped: int = 0
    errors: int = 0
    tokens: int = 0
    tool_calls: int = 0
    seconds: int = 0
    kept: int = 0
    dropped_findings: int = 0
    guarded: int = 0


# -- what the answers hold ---------------------------------------------------------------------------------------------------------------------------

def _number(value: object) -> float | int | None:
    """A finite number, or None for anything else: a boolean, a text, a value that is not finite or is too large to be compared."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _word(value: object, allowed: tuple[str, ...]) -> str | None:
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if text in allowed else None


def _object(text: object) -> dict:
    """The JSON object of a model's last text (roles.extract_object), and a text that is nested too deeply for the parser is no object either."""
    try:
        return roles.extract_object(text)
    except RecursionError:
        raise RoleError("the answer is nested too deeply") from None


def _made(calls: object) -> list:
    """The tool calls that were made. A call that the budget refused was never given to a tool, so it is no tool call of the run (it is `refused` in the answer's list)."""
    return [call for call in calls if not (isinstance(call, dict) and call.get("refused"))] if isinstance(calls, (list, tuple)) else []


def parse_answer(text: object) -> tuple[list, list[str]]:
    """The findings and the phrases of `examined` of the Investigator's last text. Raises RoleError when that is not one JSON object with a list of findings."""
    data = _object(text)
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise RoleError("the answer holds no list of findings")
    phrases = data.get("examined")
    examined = [clean_text(p, agents.MAX_EXAMINED_TEXT) for p in (phrases if isinstance(phrases, list) else []) if isinstance(p, str) and p.strip()]
    return findings, examined[: agents.MAX_EXAMINED]


def parse_finding(number: int, raw: object) -> tuple[Finding, list[str], object]:
    """The fields of one finding, strictly. Returns the finding (with its reason when it is dropped), the handles that it lists and its metric_evidence."""
    finding = Finding(number)
    if not isinstance(raw, dict):
        finding.reason = "it is not an object"
        return finding, [], None
    basis, proposal = _word(raw.get("basis"), agents.BASES), _word(raw.get("proposal"), agents.PROPOSALS)
    if basis is None or proposal is None:
        finding.reason = "its basis or its proposal is not on the list"
        return finding, [], None
    confidence = _number(raw.get("confidence"))
    if confidence is None:
        finding.reason = "its confidence is not a number"
        return finding, [], None
    listed = raw.get("handles")
    if not isinstance(listed, list) or not listed:
        finding.reason = "it lists no handles"
        return finding, [], None
    finding.basis, finding.proposal = basis, proposal
    finding.confidence = round(min(1.0, max(0.0, float(confidence))), 2)
    finding.summary = clean_text(raw.get("summary"), agents.MAX_SUMMARY)
    handles = list(dict.fromkeys(h for h in listed if isinstance(h, str)))
    finding.claimed = len(handles)
    return finding, handles[: agents.MAX_HANDLES], raw.get("metric_evidence")


def parse_verdicts(text: object, count: int) -> dict[int, SkepticAnswer]:
    """The Skeptic's verdicts by the index of the finding. Raises RoleError when the answer is not one JSON object with a list of verdicts.

    A verdict that is not valid, or that repeats an index, is left out, and the finding that it was for stays without a verdict."""
    data = _object(text)
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        raise RoleError("the answer holds no list of verdicts")
    found: dict[int, SkepticAnswer] = {}
    for entry in verdicts:
        if not isinstance(entry, dict):
            continue
        index, verdict = entry.get("index"), _word(entry.get("verdict"), roles.VERDICTS)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count or index in found or verdict is None:
            continue
        objections = entry.get("objections", [])
        kept = tuple(clean_text(o, roles.MAX_OBJECTION) for o in (objections if isinstance(objections, list) else [])[: roles.MAX_OBJECTIONS]
                     if isinstance(o, str) and o.strip())
        found[index] = SkepticAnswer(verdict, kept, clean_text(entry.get("summary"), agents.MAX_VERDICT_SUMMARY))
    return found


# -- what the tools showed ---------------------------------------------------------------------------------------------------------------------------

def _block(evidence: Mapping[str, dict], handle: str) -> dict:
    block = evidence.get(handle)
    return block if isinstance(block, dict) else {}


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _word_of(value: object) -> str | None:
    return value if isinstance(value, str) and WORD.match(value) else None


def _aggregates(evidence: Mapping[str, dict], handle: str) -> dict[str, dict]:
    """The measurements that the tools showed for one handle: metric name -> its total, maximum and average (a number, or None when the measurement was absent),
    the days that it covers and the days that had data, and its unit."""
    metrics = _block(evidence, handle).get("metrics")
    shown: dict[str, dict] = {}
    for name, aggregate in (metrics.items() if isinstance(metrics, dict) else []):
        if isinstance(name, str) and isinstance(aggregate, dict):
            shown[name] = {"total": _number(aggregate.get("total")), "max": _number(aggregate.get("max")), "average": _number(aggregate.get("average")),
                           "days": _count(aggregate.get("days")), "daysWithData": _count(aggregate.get("days_with_data")), "unit": _word_of(aggregate.get("unit"))}
    return shown


def _metrics(evidence: Mapping[str, dict], handle: str) -> dict[str, float | int | None]:
    """The total of each measurement that the tools showed for one handle, None when the measurement was absent."""
    return {name: aggregate["total"] for name, aggregate in _aggregates(evidence, handle).items()}


def _properties(evidence: Mapping[str, dict], handle: str) -> dict[str, bool | int | float | str]:
    """The typed properties that the tools showed for one handle: a flag, a number or a word under a plain key path."""
    properties = _block(evidence, handle).get("properties")
    shown: dict[str, bool | int | float | str] = {}
    for path, value in sorted((p, v) for p, v in (properties.items() if isinstance(properties, dict) else []) if isinstance(p, str)):
        if isinstance(path, str) and PROPERTY_PATH.match(path) and (isinstance(value, bool) or _number(value) is not None or _word_of(value)):
            shown[path] = value
    return dict(list(shown.items())[:SKEPTIC_PROPERTIES])


def _advisor(evidence: Mapping[str, dict], handle: str) -> float | None:
    """Advisor's own figure for a resource: the highest saving of the Advisor items that a tool showed for it."""
    items = _block(evidence, handle).get("advisor")
    figures = [_number(item.get("savingUsdMonth")) for item in (items if isinstance(items, list) else []) if isinstance(item, dict)]
    figures = [f for f in figures if f is not None and f >= 0]
    return round(max(figures), 2) if figures else None


def _cost(resource: Resource, context: Context | None) -> float | None:
    """The 30-day cost of a resource, from cost lines that code read. The tools' lines come first, the lines of the whole subscription second."""
    value = _number(resource.cost_usd_30d)
    if value is not None:
        return round(float(value), 2)
    if context is not None and context.costs is not None and context.currency == "USD":
        return round(context.costs.get(resource.resource_id.lower(), 0.0), 2)
    return None


def _verify(finding: Finding, handles: list[str], entries: object, toolbox: Toolbox, taken: set[str]) -> None:
    """Keeps of a finding what the tools showed. `taken` holds the handles of the findings before it: a resource belongs to one finding only."""
    known: list[str] = []
    for handle in handles:
        if handle not in toolbox.handles:
            finding.unknown += 1
        elif handle in taken:
            finding.repeated += 1
        else:
            known.append(handle)
    cited: dict[str, dict[str, float]] = {handle: {} for handle in known}
    for entry in (entries if isinstance(entries, list) else [])[:MAX_ENTRIES]:
        if not isinstance(entry, dict) or not isinstance(entry.get("handle"), str) or entry["handle"] not in cited or not isinstance(entry.get("metric"), str):
            continue
        said, shown = _number(entry.get("total")), _metrics(toolbox.evidence, entry["handle"]).get(entry["metric"])
        if said is None or shown is None or not math.isclose(said, shown, rel_tol=1e-6, abs_tol=0.0):
            continue  # an entry that is not the number of the tools is thrown away, and an absent measurement proves nothing
        if len(cited[entry["handle"]]) < MAX_FACT_METRICS:
            cited[entry["handle"]][entry["metric"]] = shown
    if finding.basis == "no-usage":
        kept = [handle for handle in known if cited[handle] and all(total == 0 for total in cited[handle].values())]
        finding.unproven = len(known) - len(kept)
        known = kept
    finding.handles = known
    finding.cited = {handle: cited[handle] for handle in known}
    taken.update(known)
    if not known:
        finding.reason = _why_none(finding)


def _why_none(finding: Finding) -> str:
    parts = [f"{n} {what}" for n, what in ((finding.unknown, "that no tool showed"), (finding.unproven, "without a cited measurement that matches the tools and shows no usage"),
                                          (finding.repeated, "that an earlier finding has")) if n]
    return "no resource of it is left: " + (", ".join(parts) if parts else "it lists none that the tools showed")


# -- the guards and the recheck ----------------------------------------------------------------------------------------------------------------------

def _guards_of(s: "Services", lead: Lead, context: Context | None, locks: dict[str, list[str] | None]) -> Guards:
    """The guards of one resource. The locks of a scope are read once for the whole investigation; a scope that cannot be read makes the resource unverified."""
    scope_locks: list[str] | None = []
    for scope in scopes_of(lead.resource_id):
        key = scope.lower()
        if key not in locks:
            try:
                locks[key] = s.arm.locks_at(lead.subscription_id, scope)
            except HttpError:
                locks[key] = None
        if locks[key] is None:
            scope_locks = None
            break
        scope_locks += locks[key]  # type: ignore[operator]
    fixture = s.extras is not None and is_fixture(lead, wiring.approval_settings(s.extras.settings))
    return guards.evaluate(lead, context if context is not None else Context(), scope_locks, fixture=fixture)


def _signature(facts: Mapping) -> tuple:
    """What a case rests on, for the recheck: its basis, its proposal and its measurements. The cost moves every day and is left out."""
    metrics = facts.get("metrics")
    return facts.get("basis"), facts.get("proposal"), tuple(sorted(metrics.items())) if isinstance(metrics, dict) else ()


def _judged_lately(s: "Services", lead: Lead, facts: dict) -> bool:
    """A resource whose case was updated within the days of RECHECK_DAYS is not taken up again unless its evidence changed. A case that ended in an error, or
    whose steps did not all work, is taken up again at once. A case that a person has answered, or that the loop has taken on, is left alone for the whole time."""
    ex = s.extras
    if ex is None:
        return False
    try:
        old = ex.store.case_get(f"k{lead.lead_id}")
    except StoreError:
        return False
    if old is None or old.status == "error" or not old.updated_at or any(isinstance(x, dict) and x.get("ok") is False for x in old.steps):
        return False
    if s.clock() - parse(old.updated_at) >= dt.timedelta(days=ex.settings.recheck_days):
        return False
    if old.status in ("proposed", "needs_human", "dropped"):
        return _signature(old.facts if isinstance(old.facts, dict) else {}) == _signature(facts)
    return True


# -- what the Skeptic is given -----------------------------------------------------------------------------------------------------------------------

def _row(item: Item, toolbox: Toolbox) -> dict:
    """The evidence row of one resource: its handle, its type as Azure names it, what the tools showed about it (measurements with the days that they cover, a SKU,
    typed properties) and its cost. No name, no tag, no text of the estate."""
    shown = _aggregates(toolbox.evidence, item.handle)
    names = sorted((n for n in shown if METRIC_NAME.match(n)), key=lambda n: (n not in item.metrics, n))[:SKEPTIC_METRICS]
    block = _block(toolbox.evidence, item.handle)
    kind = block["type"] if isinstance(block.get("type"), str) else toolbox.handles[item.handle].resource_type
    row: dict = {"handle": item.handle, "type": kind if len(kind) <= 120 and RESOURCE_TYPE.match(kind) else "other", "costUsd30d": item.lead.cost_usd_30d,
                 "metrics": [{"metric": n, "cited": n in item.metrics, **{k: v for k, v in shown[n].items() if v is not None or k == "total"}} for n in names]}
    if _word_of(block.get("sku")):
        row["sku"] = block["sku"]
    properties = _properties(toolbox.evidence, item.handle)
    if properties:
        row["properties"] = properties
    if item.lead.advisor_saving_usd is not None:
        row["advisorSavingUsdMonth"] = item.lead.advisor_saving_usd
    return row


def _skeptic_input(findings: list[Finding], toolbox: Toolbox) -> str:
    rows = [[_row(item, toolbox) for item in finding.items] for finding in findings]
    shown = SKEPTIC_ROWS
    while True:
        text = agents.skeptic_input([
            {"index": index, "basis": f.basis, "proposal": f.proposal, "confidence": f.confidence, "summary": f.summary, "resources": len(f.items),
             "costUsd30d": f.covered_usd, "evidence": rows[index][:shown], "evidenceShown": len(rows[index][:shown])} for index, f in enumerate(findings)])
        if len(text) <= SKEPTIC_CHARS or shown <= 1:
            return text
        shown = max(1, shown // 2)


# -- the cases ---------------------------------------------------------------------------------------------------------------------------------------

def _lead(resource: Resource, facts: dict, cost: float | None, advisor: float | None) -> Lead:
    return Lead(detector=DETECTOR, resource_id=resource.resource_id, resource_type=resource.resource_type, name=resource.name, resource_group=resource.resource_group,
                subscription_id=resource.subscription_id.lower(), location=resource.location, tags=dict(resource.tags), managed_by=resource.managed_by, facts=facts,
                advisor_saving_usd=advisor, cost_usd_30d=cost)


def _facts(finding: Finding, metrics: dict[str, float], cost: float | None) -> dict:
    """The typed digest of a case: what the finding rests on, and no name."""
    return {"basis": finding.basis, "proposal": finding.proposal, "metrics": dict(metrics), "costUsd30d": cost, "finding": finding.number}


def _figure(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def investigate(s: "Services", contexts: Mapping[str, Context], notes: list[str], *, toolbox: Toolbox | None = None) -> Investigation:
    """The whole investigation, with its own budget (INVESTIGATE_MAX_CALLS and INVESTIGATE_MAX_SECONDS). It never raises: when it cannot run, the result says why.

    A fault of its own, after some cases were opened, leaves the counts of those cases in the result, so that the end of the run counts the lines of the History."""
    out = Investigation()
    try:
        return _investigate(s, contexts, notes, toolbox, out)
    except Exception as error:  # noqa: BLE001 (an investigation never stops the run)
        text = clean_text(s.redact(f"{type(error).__name__}: {error}"), 300)
        LOG.warning("the investigation failed: %s", text)
        out.ran, out.note = False, f"it failed ({text})"
        return out


def _investigate(s: "Services", contexts: Mapping[str, Context], notes: list[str], toolbox: Toolbox | None, out: Investigation) -> Investigation:
    h, st = s.history, s.settings
    if not st.investigate:
        out.note = "it is switched off"
        return out
    if not st.foundry_endpoint or s.foundry is None:
        out.note = "no Foundry endpoint is set"
        return out

    def note(text: str) -> None:
        text = clean_text(s.redact(text), 300)
        notes.append(text)
        h.emit("run.note", note=text)

    began = s.monotonic()
    budget = max(1.0, float(st.investigate_max_seconds))
    deadline = began + budget
    s.client.deadline = deadline
    toolbox = toolbox if toolbox is not None else Toolbox(s.arm, st.subscriptions, s.clock(), [])
    try:
        investigator_ref = s.foundry.ensure_agent(agents.investigator(st, toolbox.specs))
        skeptic_ref = s.foundry.ensure_agent(agents.skeptic(st))
    except FoundryError as error:
        out.note = f"the agents could not be made ready ({clean_text(s.redact(error), 200)})"
        return out
    h.emit("investigation.started", investigator=investigator_ref, skeptic=skeptic_ref, modelInvestigator=st.foundry_model_investigator,
           modelSkeptic=st.foundry_model_skeptic, maxCalls=st.investigate_max_calls, maxSeconds=int(budget))

    def finished(ok: bool, **fields: object) -> None:
        out.seconds = int(s.monotonic() - began)
        h.emit("investigation.finished", ok=ok, toolCalls=out.tool_calls, tokens=out.tokens, seconds=out.seconds, **fields)

    def step(name: str, model: str, started: float, ok: bool, tokens: tuple[int, int] | None, text: str | None) -> dict:
        return {"step": name, "model": model, "promptTokens": tokens[0] if tokens else None, "completionTokens": tokens[1] if tokens else None,
                "ms": int((s.monotonic() - started) * 1000), "ok": ok, "note": text}

    shown = {"toolbox": 0, "foundry": len(s.foundry.notes) if isinstance(getattr(s.foundry, "notes", None), list) else 0}

    def flush_notes() -> None:
        """What the toolbox and the Foundry client say about problems that stopped nothing becomes a note of the run, once."""
        for key, source in (("toolbox", toolbox), ("foundry", s.foundry)):
            texts = getattr(source, "notes", None)
            if isinstance(texts, list):
                for text in texts[shown[key]:]:
                    note(text)
                shown[key] = len(texts)

    # 1. The Investigator reads the estate with the tools, inside its own budget of calls and time.
    reserve = min(RESERVE_SECONDS, budget / 4)
    started = s.monotonic()
    try:
        answer = s.foundry.run(investigator_ref, agents.investigator_input(st.investigate_max_calls), toolbox.call, max_calls=st.investigate_max_calls,
                               max_seconds=max(1.0, budget - reserve))
    except FoundryError as error:
        partial = getattr(error, "partial", None)  # what the run had come to: the calls that it made and the tokens that it used
        out.tool_calls = len(_made(partial.calls)) if partial is not None else len(toolbox.log)
        out.tokens = partial.input_tokens + partial.output_tokens if partial is not None else 0
        flush_notes()
        out.note = f"the investigator gave no answer ({clean_text(s.redact(error), 200)})"
        finished(False, note=out.note)
        return out
    made = _made(answer.calls)
    refused = len(answer.calls) - len(made)
    out.tool_calls, out.tokens = len(made), answer.input_tokens + answer.output_tokens
    failed_calls = sum(1 for call in made if isinstance(call, dict) and call.get("ok") is False)
    investigator_step = step("investigator", st.foundry_model_investigator, started, True, (answer.input_tokens, answer.output_tokens),
                             f"{out.tool_calls} tool call{'' if out.tool_calls == 1 else 's'}" + (f", {failed_calls} failed" if failed_calls else "")
                             + (f", {refused} refused after the budget" if refused else ""))
    if refused:
        note(f"the investigator asked for {refused} more tool call{'' if refused == 1 else 's'} after its budget of {st.investigate_max_calls} was used up, and was refused")
    flush_notes()
    try:
        raw_findings, examined = parse_answer(answer.text)
    except RoleError as error:
        out.note = f"the investigator gave no answer that could be read ({clean_text(error, 200)})"
        finished(False, note=out.note)
        return out
    out.ran = True
    if len(raw_findings) > agents.MAX_FINDINGS:
        note(f"the investigator gave {len(raw_findings)} findings; the first {agents.MAX_FINDINGS} were taken")

    # 2. Code checks the findings against what the tools showed, then the recheck and the guards hold every resource.
    findings: list[Finding] = []
    taken: set[str] = set()
    for number, raw in enumerate(raw_findings[: agents.MAX_FINDINGS], 1):
        finding, handles, entries = parse_finding(number, raw)
        if finding.reason is None:
            _verify(finding, handles, entries, toolbox, taken)
        findings.append(finding)
    locks: dict[str, list[str] | None] = {}
    room = MAX_CASES
    held: dict[str, int] = {}
    for finding in findings:
        if finding.reason is not None:
            continue
        costs = {handle: _cost(toolbox.handles[handle], contexts.get(toolbox.handles[handle].subscription_id.lower())) for handle in finding.handles}
        for handle in sorted(finding.handles, key=lambda handle: -(costs[handle] or 0.0)):
            resource = toolbox.handles[handle]
            facts = _facts(finding, finding.cited[handle], costs[handle])
            lead = _lead(resource, facts, costs[handle], _advisor(toolbox.evidence, handle))
            if _judged_lately(s, lead, facts):
                finding.recent += 1
            elif room <= 0:
                finding.capped += 1
            else:
                flags = _guards_of(s, lead, contexts.get(lead.subscription_id), locks)
                if flags.names:
                    finding.guarded += 1
                    out.guarded += 1
                    for name in flags.names:
                        held[name] = held.get(name, 0) + 1
                else:
                    finding.items.append(Item(handle, lead, finding.cited[handle]))
                    room -= 1
        known = [i.lead.cost_usd_30d for i in finding.items if i.lead.cost_usd_30d is not None]
        finding.covered_usd = round(sum(known), 2) if known else None
        if not finding.items:
            parts = [f"{n} {what}" for n, what in ((finding.guarded, "held back by a guard"), (finding.recent, "judged lately"),
                                                  (finding.capped, "beyond the cap of cases for one run")) if n]
            finding.reason = "no resource of it is left: " + ", ".join(parts)
    survivors = [f for f in findings if f.reason is None]

    # 3. The Skeptic tries to break the findings that are left, in one run.
    skeptic_step: dict | None = None
    if survivors:
        started = s.monotonic()
        left = deadline - started
        if left <= 1.0:
            skeptic_step = step("skeptic", st.foundry_model_skeptic, started, False, None, "no time was left for the Skeptic")
        else:
            tokens: tuple[int, int] | None = None
            try:
                judged = s.foundry.run(skeptic_ref, _skeptic_input(survivors, toolbox), None, max_calls=0, max_seconds=left)
                tokens = (judged.input_tokens, judged.output_tokens)
                out.tokens += judged.input_tokens + judged.output_tokens
                verdicts = parse_verdicts(judged.text, len(survivors))
                for index, verdict in verdicts.items():
                    survivors[index].verdict = verdict
                missing = len(survivors) - len(verdicts)
                skeptic_step = step("skeptic", st.foundry_model_skeptic, started, True, tokens,
                                    f"no verdict for {missing} of {len(survivors)} findings" if missing else None)
            except (FoundryError, RoleError) as error:
                partial = getattr(error, "partial", None)
                if tokens is None and partial is not None:
                    tokens = (partial.input_tokens, partial.output_tokens)
                    out.tokens += partial.input_tokens + partial.output_tokens
                skeptic_step = step("skeptic", st.foundry_model_skeptic, started, False, tokens, clean_text(s.redact(error), 200))
            flush_notes()
        if not skeptic_step["ok"] or skeptic_step["note"]:
            note(f"the Skeptic could not judge every finding ({skeptic_step['note']}); a finding without a verdict needs a person")

    # 4. One line for each finding, then one case for each resource that is left.
    for finding in findings:
        h.emit("investigation.finding", finding=finding.number, basis=finding.basis or None, proposal=finding.proposal or None, confidence=finding.confidence,
               claimed=finding.claimed, handles=len(finding.items), unknown=finding.unknown, unproven=finding.unproven, repeated=finding.repeated,
               judgedLately=finding.recent, guarded=finding.guarded, capped=finding.capped, coveredCostUsd30d=finding.covered_usd,
               verdict=finding.verdict.verdict if finding.verdict else None, kept=finding.reason is None, reason=finding.reason, summary=finding.summary)
    models = {"investigator": st.foundry_model_investigator, "skeptic": st.foundry_model_skeptic}
    steps = tuple(x for x in (investigator_step, skeptic_step) if x is not None)
    number = 0
    for finding in survivors:
        for item in finding.items:
            number += 1
            _open_case(s, out, finding, item, models, steps, f"{h.run_id[:8]}-i{number}")
    out.kept = len(survivors)
    out.dropped_findings = len(raw_findings) - len(survivors)
    if out.guarded:
        note(f"the investigation held back {out.guarded} resource{'' if out.guarded == 1 else 's'} with a guard: " + ", ".join(f"{n} {name}" for name, n in sorted(held.items())))
    capped = sum(f.capped for f in findings)
    if capped:
        note(f"{capped} resource{'' if capped == 1 else 's'} of the findings {'is' if capped == 1 else 'are'} not listed as cases: a run opens at most {MAX_CASES}")
    finished(True, examined=examined, findingsKept=out.kept, findingsDropped=out.dropped_findings, cases=out.cases, guarded=out.guarded)
    note(f"the investigation made {out.tool_calls} tool call{'' if out.tool_calls == 1 else 's'}, kept {out.kept} of {len(raw_findings)} finding"
         f"{'' if len(raw_findings) == 1 else 's'} and opened {out.cases} case{'' if out.cases == 1 else 's'}")
    return out


def _open_case(s: "Services", out: Investigation, finding: Finding, item: Item, models: dict, steps: tuple[dict, ...], case_id: str) -> None:
    """The case of one resource: decide.py gives it its status, the History gets its result, and the store keeps it when there is a store."""
    h = s.history
    lead = item.lead
    detective = DetectiveAnswer(finding.proposal, finding.confidence, finding.summary)
    outcome = decide.decide(lead, Guards({}), detective, finding.verdict)
    h.emit("case.result", caseId=case_id, leadId=lead.lead_id, detector=DETECTOR, resourceName=clean_text(lead.name, 120), resourceType=clean_text(lead.resource_type, 120),
           resourceGroup=clean_text(lead.resource_group, 90), costUsd30d=lead.cost_usd_30d, status=outcome.status, recommendation=outcome.recommendation,
           confidence=outcome.confidence, monthlySavingUsd=_figure(outcome.monthly_saving_usd), summary=outcome.summary, objections=list(outcome.objections),
           guards=outcome.guards)
    out.cases += 1
    if outcome.status == "proposed":
        out.proposed += 1
    elif outcome.status == "needs_human":
        out.needs_human += 1
    elif outcome.status == "dropped":
        out.dropped += 1
    else:
        out.errors += 1
    ex = s.extras
    if ex is None:
        return
    now = stamp(s.clock())
    try:
        old = ex.store.case_get(f"k{lead.lead_id}")
        record = CaseRecord(
            case_id=f"k{lead.lead_id}", resource_id=lead.resource_id, resource_name=clean_text(lead.name, 120), resource_type=clean_text(lead.resource_type, 120),
            resource_group=clean_text(lead.resource_group, 90), subscription_id=lead.subscription_id, detector=DETECTOR, run_id=h.run_id, status=outcome.status,
            recommendation=outcome.recommendation, confidence=outcome.confidence, saving_usd_month=_figure(outcome.monthly_saving_usd), cost_usd_30d=lead.cost_usd_30d,
            summary=clean_text(outcome.summary, 600), objections=tuple(clean_text(o, 300) for o in outcome.objections), guards=tuple(outcome.guards),
            models=dict(models), steps=steps, facts=lead.facts, first_seen_at=old.first_seen_at if old and old.first_seen_at else now, updated_at=now,
            runs_seen=(old.runs_seen + 1) if old else 1)
        ex.store.case_put(record)
        if outcome.status == "proposed":
            plan = ex.approvals.create(record, lead, ex.approvers())  # it makes none for a case of this detector: no change is made for a finding
            if plan is not None:
                h.emit("plan.created", planId=plan.plan_id, caseKey=record.case_id, family=plan.family, approvers=len(plan.approvers))
                ex.on_plan(plan, ex.store.case_get(record.case_id) or record)
    except (StoreError, ValueError) as error:
        h.emit("run.note", note=clean_text(s.redact(f"the case could not be kept in the store: {error}"), 300))
