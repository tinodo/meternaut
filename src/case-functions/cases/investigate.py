"""The investigation: two agents in Microsoft Foundry look for waste in the estate, and code checks every word of theirs against what the tools showed.

The Investigator reads the estate through the read-only tools of toolbox.py (handles instead of names, typed numbers instead of text) and ends with one JSON
object of findings. Nothing in it is believed before code has checked it:

- a handle that no tool showed is dropped, and so is a measurement whose total is not a number that the tools returned;
- a finding that claims no usage keeps only the resources whose cited measurements are nil in every total that the tools recorded for them;
- the cost of the resources is added up by code from the cost lines, and the agent never supplies a figure;
- the guards of guards.py hold every resource, and a resource with a guard on leaves the finding;
- a second agent, the Skeptic, then tries to break the findings that are left, and decide.py gives each resource its status.

A resource whose finding cites no measurement that matched the tools is never proposed, whatever the agents say: a person has to judge it. The same holds for a
resource that the Skeptic was not shown, for a finding that it gave no verdict (or two verdicts) for, and for a finding whose confidence is not a number from 0 to 1.

Each resource of a finding that is left becomes one case, so that the History, the page of the case and the letters show it like any other case. Nothing here changes
Azure: no plan of a change is made for a case that this module opens (approvals.create refuses it), and the advise plan that asks a person whether it is worth acting on
changes nothing in Azure.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Mapping

from . import agents, decide, guards, learning, roles, wiring
from .approvals import is_fixture
from .arm import scopes_of
from .detectors import Context, Lead
from .foundry import SOFT_TIME_SHARE, FoundryError
from .guards import Guards
from .harness import HarnessRefused
from .http import HttpError
from .memory_store import parse, stamp
from .models import ADVISE, CaseRecord, StoreError
from .ownership import NOT_COMPLETE, NOT_IN_WINDOW, NOT_VISIBLE, UNAVAILABLE, OwnerReader, owner_hints
from .roles import DetectiveAnswer, RoleError, SkepticAnswer, clean_text
from .toolbox import SUBSCRIPTION_SECONDS, Resource, Toolbox

if TYPE_CHECKING:
    from .run import Services

DETECTOR = "investigation"
MAX_CASES = 60  # the cases that one run opens
MAX_ENTRIES = 720  # the entries of metric_evidence that are read: a handful for each of the handles that a finding may hold
MAX_FACT_METRICS = 12  # the measurements that a case keeps
MAX_TOTALS = 20  # the totals of one measurement that are read: the toolbox records at most as many
SKEPTIC_METRICS = 6  # the measurements of one resource that the Skeptic sees, at most
SKEPTIC_PROPERTIES = 8  # the properties of one resource that the Skeptic sees
SKEPTIC_CHARS = 30000  # the size of the Skeptic's input
RESERVE_SECONDS = 120.0  # what the Investigator leaves of its time for the checks and the Skeptic, at most
LOG = logging.getLogger("meternaut.investigate")

# What code lets through of what the tools showed, once more: a metric name, a resource type as Azure names one, a word, and the key path of a property. Each is
# used with fullmatch, so that nothing can follow the last character (not even a line break).
METRIC_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/%()-]{0,98}")
RESOURCE_TYPE = re.compile(r"[a-z0-9.]{1,60}(?:/[a-z0-9._-]{1,50}){1,4}")
WORD = re.compile(r"[A-Za-z0-9_.-]{1,32}")
PROPERTY_PATH = re.compile(r"[A-Za-z][A-Za-z0-9.]{0,100}")

# The rows that the Skeptic is given, from the richest to the poorest: how many measurements of a resource, which fields of a measurement, and whether the SKU and the
# properties of the resource are shown. The richest level whose input fits SKEPTIC_CHARS is the one that is used.
FULL = ("total", "max", "average", "days", "daysWithData", "unit")
SHORT = ("total", "days", "daysWithData")
LEAST = ("total",)
DETAIL = ((SKEPTIC_METRICS, FULL, True, True), (SKEPTIC_METRICS, FULL, True, False), (4, SHORT, True, False), (3, SHORT, False, False), (2, LEAST, False, False),
          (1, LEAST, False, False))

NO_VERDICT = "no verdict for this finding"
NOT_SHOWN = "this resource was not shown to the Skeptic"


@dataclass
class Item:
    """One resource of a finding, on its way to a case."""

    handle: str
    lead: Lead
    metrics: dict[str, float]  # the entries of the finding that matched the tools: metric name -> the total that the tools returned
    shown: bool = False  # the Skeptic was given a row for the resource


@dataclass
class Finding:
    """One finding of the Investigator and what code did to it. `reason` is set when the whole finding was dropped."""

    number: int
    basis: str = ""
    proposal: str = ""
    confidence: float = 0.0
    summary: str = ""
    note: str | None = None  # what code says about the finding, for a person: its confidence was not a number from 0 to 1
    claimed: int = 0  # the distinct handles that the answer listed
    handles: list[str] = field(default_factory=list)  # the handles that the tools showed, in the finding's order
    cited: dict[str, dict[str, float]] = field(default_factory=dict)
    listed: dict[str, set[str]] = field(default_factory=dict)  # the measurements that the agent cited for each handle, whether or not they matched the tools
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
    """What the investigation came to. `ran` is true when the Investigator gave an answer that could be read, even one with no finding. `off` is true when it was
    not meant to run (it is switched off, or the app has no Foundry project); a run that was meant to and did not has `ran` and `off` false."""

    ran: bool = False
    off: bool = False
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
    unmeasured: int = 0
    owners: object = None  # the OwnerReader of the run: one for all its cases, so that the reads of the Activity Log share one budget
    # True when the harness did not let the agents run (a pulled switch, a lock that does not hold, a stored definition that differs) or stopped a run: the run of the Watch then opens no new
    # case from the investigation, and the planted waste, the approvals and the messages go on (cases/harness.py).
    held: bool = False

    @property
    def state(self) -> str:
        """`ran`, `held`, `off` or `failed`: what the end of the run says of the investigation."""
        return "ran" if self.ran else "held" if self.held else "off" if self.off else "failed"


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
    if 0 <= confidence <= 1:
        finding.confidence = round(float(confidence), 2)
    else:  # a model that writes 85 for a percentage must not pass the gate of 0.7: the finding stays, with a confidence that cannot propose, and a person is told
        finding.note = f"the Investigator gave a confidence of {confidence:g}, which is not a number from 0 to 1, so it counts as 0 and a person has to judge this finding"
    finding.summary = clean_text(raw.get("summary"), agents.MAX_SUMMARY)
    handles = list(dict.fromkeys(h for h in listed if isinstance(h, str)))
    finding.claimed = len(handles)
    return finding, handles[: agents.MAX_HANDLES], raw.get("metric_evidence")


def parse_verdicts(text: object, count: int) -> dict[int, SkepticAnswer]:
    """The Skeptic's verdicts by the index of the finding. Raises RoleError when the answer is not one JSON object with a list of verdicts.

    A verdict that is not valid is left out, and the finding that it was for stays without a verdict. So does a finding whose index the answer holds twice, whatever
    the two entries say: an answer that contradicts itself, or repeats itself, decides nothing, and the finding goes to a person."""
    data = _object(text)
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        raise RoleError("the answer holds no list of verdicts")
    found: dict[int, SkepticAnswer | None] = {}
    for entry in verdicts:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
            continue
        verdict = _word(entry.get("verdict"), roles.VERDICTS)
        if index in found or verdict is None:
            found[index] = None
            continue
        objections = entry.get("objections", [])
        kept = tuple(clean_text(o, roles.MAX_OBJECTION) for o in (objections if isinstance(objections, list) else [])[: roles.MAX_OBJECTIONS]
                     if isinstance(o, str) and o.strip())
        found[index] = SkepticAnswer(verdict, kept, clean_text(entry.get("summary"), agents.MAX_VERDICT_SUMMARY))
    return {index: answer for index, answer in found.items() if answer is not None}


# -- what the tools showed ---------------------------------------------------------------------------------------------------------------------------

def _block(evidence: Mapping[str, dict], handle: str) -> dict:
    block = evidence.get(handle)
    return block if isinstance(block, dict) else {}


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _word_of(value: object) -> str | None:
    return value if isinstance(value, str) and WORD.fullmatch(value) else None


def _totals(aggregate: dict) -> list[float | int | None]:
    """Every total that the tools recorded for one measurement, in order, None for one that is not a number. When the evidence holds no list of totals, it is the one
    total that it holds. No total is left out: a claim of no usage is checked against every one."""
    totals = aggregate.get("totals")
    if isinstance(totals, (list, tuple)) and totals:
        return [_number(total) for total in totals]
    return [_number(aggregate.get("total"))]


def _aggregates(evidence: Mapping[str, dict], handle: str) -> dict[str, dict]:
    """The measurements that the tools showed for one handle: metric name -> its total, maximum and average (a number, or None when the measurement was absent),
    the days that it covers and the days that had data, its unit, and every total that was recorded for it."""
    metrics = _block(evidence, handle).get("metrics")
    shown: dict[str, dict] = {}
    for name, aggregate in (metrics.items() if isinstance(metrics, dict) else []):
        if isinstance(name, str) and isinstance(aggregate, dict):
            shown[name] = {"total": _number(aggregate.get("total")), "max": _number(aggregate.get("max")), "average": _number(aggregate.get("average")),
                           "days": _count(aggregate.get("days")), "daysWithData": _count(aggregate.get("days_with_data")), "unit": _word_of(aggregate.get("unit")),
                           "totals": _totals(aggregate)}
    return shown


def _metrics(evidence: Mapping[str, dict], handle: str) -> dict[str, float | int | None]:
    """The total of each measurement that the tools showed for one handle, None when the measurement was absent."""
    return {name: aggregate["total"] for name, aggregate in _aggregates(evidence, handle).items()}


def _properties(evidence: Mapping[str, dict], handle: str) -> dict[str, bool | int | float | str]:
    """The typed properties that the tools showed for one handle: a flag, a number or a word under a plain key path."""
    properties = _block(evidence, handle).get("properties")
    shown: dict[str, bool | int | float | str] = {}
    for path, value in sorted((p, v) for p, v in (properties.items() if isinstance(properties, dict) else []) if isinstance(p, str)):
        if isinstance(path, str) and PROPERTY_PATH.fullmatch(path) and (isinstance(value, bool) or _number(value) is not None or _word_of(value)):
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
    if getattr(resource, "part_of", None) is not None:
        return None  # a part of a resource is billed with the resource: it has no cost of its own, and that is not a cost of nil
    if context is not None and context.costs is not None and context.currency == "USD":
        return round(context.costs.get(resource.resource_id.lower(), 0.0), 2)
    return None


def _verify(finding: Finding, handles: list[str], entries: object, toolbox: Toolbox, taken: set[str]) -> None:
    """Keeps of a finding what the tools showed. `taken` holds the handles of the findings before it: a resource belongs to one finding only.

    An entry of metric_evidence counts when its total is one of the totals that the tools recorded for that handle and metric; the number that is kept is the tools'.
    A claim of no usage is proved by such an entry only when every total that was recorded for the metric is nil: a short measurement that shows nil does not cancel
    a longer one that showed something. A resource with a cited measurement that shows something, or with none that proves it, leaves a finding of no usage."""
    known: list[str] = []
    for handle in handles:
        if handle not in toolbox.handles:
            finding.unknown += 1
        elif handle in taken:
            finding.repeated += 1
        else:
            known.append(handle)
    cited: dict[str, dict[str, float]] = {handle: {} for handle in known}
    contradicted: set[str] = set()
    recorded = {handle: _aggregates(toolbox.evidence, handle) for handle in known}
    for entry in (entries if isinstance(entries, list) else [])[:MAX_ENTRIES]:
        if not isinstance(entry, dict) or not isinstance(entry.get("handle"), str) or entry["handle"] not in cited or not isinstance(entry.get("metric"), str):
            continue
        finding.listed.setdefault(entry["handle"], set()).add(entry["metric"])
        handle, said = entry["handle"], _number(entry.get("total"))
        shown = recorded[handle].get(entry["metric"])
        if said is None or shown is None:
            continue
        total = next((t for t in shown["totals"] if t is not None and math.isclose(said, t, rel_tol=1e-6, abs_tol=0.0)), None)
        if total is None:
            continue  # an entry that is not a number of the tools is thrown away, and an absent measurement proves nothing
        if finding.basis == "no-usage":
            numbers = [t for t in shown["totals"] if t is not None]
            if any(t != 0 for t in numbers):
                contradicted.add(handle)
                continue
            if len(numbers) != len(shown["totals"]):
                continue  # a measurement that was absent at some time proves nothing
        if len(cited[handle]) < MAX_FACT_METRICS:
            cited[handle][entry["metric"]] = total
    if finding.basis == "no-usage":
        kept = [handle for handle in known if cited[handle] and handle not in contradicted]
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

def _nonzero(aggregate: dict) -> bool:
    """A measurement with a total that is not nil among the totals that the tools recorded for it: what can contradict a claim of no usage."""
    return any(total != 0 for total in aggregate["totals"] if total is not None)


def _measurement(name: str, aggregate: dict, cited: bool, fields: tuple[str, ...]) -> dict:
    """One measurement of a row: its name, whether the agent cited it, the fields of `fields` that the tools had (the total always, a null when it was absent), and
    the totals that were recorded for it when there are several (at most MAX_TOTALS are shown)."""
    row: dict = {"metric": name, "cited": cited}
    for key in fields:
        if aggregate[key] is not None or key == "total":
            row[key] = aggregate[key]
    if len(aggregate["totals"]) > 1:
        row["totals"] = aggregate["totals"][:MAX_TOTALS]
    return row


def _row(item: Item, toolbox: Toolbox, count: int, fields: tuple[str, ...], sku: bool, properties: bool) -> dict:
    """The evidence row of one resource: its handle, its type as Azure names it, its cost, and at most `count` of the measurements that the tools showed for it,
    those with a total that is not nil first (what may contradict the claim), then the cited ones, then the others by name. A SKU and typed properties are added
    when `sku` and `properties` say so. No name, no tag, no text of the estate."""
    shown = _aggregates(toolbox.evidence, item.handle)
    names = sorted((n for n in shown if METRIC_NAME.fullmatch(n)), key=lambda n: (not _nonzero(shown[n]), n not in item.metrics, n))[:count]
    block = _block(toolbox.evidence, item.handle)
    kind = block["type"] if isinstance(block.get("type"), str) else toolbox.handles[item.handle].resource_type
    row: dict = {"handle": item.handle, "type": kind if len(kind) <= 120 and RESOURCE_TYPE.fullmatch(kind) else "other", "costUsd30d": item.lead.cost_usd_30d,
                 "metrics": [_measurement(n, shown[n], n in item.metrics, fields) for n in names]}
    if sku and _word_of(block.get("sku")):
        row["sku"] = block["sku"]
    typed = _properties(toolbox.evidence, item.handle) if properties else {}
    if typed:
        row["properties"] = typed
    if item.lead.advisor_saving_usd is not None:
        row["advisorSavingUsdMonth"] = item.lead.advisor_saving_usd
    return row


def _skeptic_input(findings: list[Finding], toolbox: Toolbox) -> tuple[str, set[str]]:
    """The input of the Skeptic and the handles of the resources that it shows. It shows every resource that will be a case, with the richest rows that fit
    SKEPTIC_CHARS. When even the poorest rows do not fit, the cheapest resources are left out, and the case of a resource that was not shown needs a person."""
    items = [item for finding in findings for item in finding.items]
    left_out: set[str] = set()

    def build(level: tuple) -> str:
        count, fields, sku, properties = level
        listed = []
        for index, f in enumerate(findings):
            rows = [_row(item, toolbox, count, fields, sku, properties) for item in f.items if item.handle not in left_out]
            listed.append({"index": index, "basis": f.basis, "proposal": f.proposal, "confidence": f.confidence, "summary": f.summary, "resources": len(f.items),
                           "costUsd30d": f.covered_usd, "evidence": rows, "evidenceShown": len(rows)})
        return agents.skeptic_input(listed)

    for level in DETAIL:
        text = build(level)
        if len(text) <= SKEPTIC_CHARS:
            return text, {item.handle for item in items}
    for item in sorted(items, key=lambda i: (i.lead.cost_usd_30d or 0.0, i.handle)):
        left_out.add(item.handle)
        text = build(DETAIL[-1])
        if len(text) <= SKEPTIC_CHARS:
            break
    return text, {item.handle for item in items} - left_out


# -- the cases ---------------------------------------------------------------------------------------------------------------------------------------

def _lead(resource: Resource, facts: dict, cost: float | None, advisor: float | None) -> Lead:
    return Lead(detector=DETECTOR, resource_id=resource.resource_id, resource_type=resource.resource_type, name=resource.name, resource_group=resource.resource_group,
                subscription_id=resource.subscription_id.lower(), location=resource.location, tags=dict(resource.tags), managed_by=resource.managed_by, facts=facts,
                advisor_saving_usd=advisor, cost_usd_30d=cost)


def _facts(finding: Finding, metrics: dict[str, float], cost: float | None, recorded: Mapping[str, dict] | None = None, listed: int | None = None) -> dict:
    """The typed digest of a case: what the finding rests on, and no name. `recorded` is what the tools showed for the resource (its unit and the days of each measurement)
    and `listed` how many measurements the agent cited for it: a person reads "code re-checked 5 of 6 numbers" from them."""
    facts: dict = {"basis": finding.basis, "proposal": finding.proposal, "metrics": dict(metrics), "costUsd30d": cost, "finding": finding.number}
    shown = recorded or {}
    units = {name: shown[name]["unit"] for name in metrics if name in shown and shown[name].get("unit")}
    days = {name: shown[name]["days"] for name in metrics if name in shown and shown[name].get("days")}
    if units:
        facts["metricUnits"] = units
    if days:
        facts["metricDays"] = days
    if listed is not None and listed >= len(metrics):
        facts["citedMetrics"] = listed
    return facts


def _figure(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _why(s: "Services", error: Exception) -> str:
    """Why a call of the Agent Service failed, in at most 200 characters: the fixed words of the route when the model of the agent goes through a connection and the answer is about that route
    (FoundryError.route), and the text of the error as it always was in every other case."""
    return clean_text(s.redact(getattr(error, "route", "") or error), 200)


def _own_words(note: Callable[[str], None], error: Exception) -> None:
    """The fixed words of a route say what to check. The words of the Agent Service as they came (redacted and cut by the client) say what it found: when there are fixed words, those are kept in
    a note of their own too, so that a cause that the fixed words did not name right can still be read."""
    if getattr(error, "route", ""):
        note(f"the words of the Agent Service: {error}")


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
    finally:
        harness = getattr(s, "harness", None)
        if harness is not None:
            harness.close()  # the line of every agent run, and the brake for a run that misbehaved (cases/harness.py)


def _investigate(s: "Services", contexts: Mapping[str, Context], notes: list[str], toolbox: Toolbox | None, out: Investigation) -> Investigation:
    h, st = s.history, s.settings
    if not st.investigate:
        out.off, out.note = True, "it is switched off"
        return out
    if not st.foundry_endpoint or s.foundry is None:
        out.off, out.note = True, "no Foundry endpoint is set"
        return out

    def note(text: str) -> None:
        text = clean_text(s.redact(text), 300)
        notes.append(text)
        h.emit("run.note", note=text)

    began = s.monotonic()
    budget = max(1.0, float(st.investigate_max_seconds))
    deadline = began + budget
    s.client.deadline = deadline
    if toolbox is None:
        toolbox = Toolbox(s.arm, st.subscriptions, s.clock(), [])
        # One call may take at most an eighth of the investigation's time, or the default, for reading the subscriptions, so that a call over a large estate cannot use the time that the
        # Investigator needs for its answer and the Skeptic for its verdicts.
        toolbox.read_seconds = min(SUBSCRIPTION_SECONDS, max(5.0, budget / 8))
    try:
        # The harness (cases/harness.py) stands between the run and the agents: it holds the code and the stored definitions against the lock, reads the switches, and makes the agent only from
        # a definition that equals the lock. Without a harness (a test that plays the agents) the client makes the agents as it always did.
        spec_i, spec_s = agents.investigator(st, toolbox.specs), agents.skeptic(st)
        harness = getattr(s, "harness", None)
        if harness is None:
            investigator_ref = s.foundry.ensure_agent(spec_i)
            skeptic_ref = s.foundry.ensure_agent(spec_s)
        else:
            investigator_ref = harness.ensure(spec_i)
            skeptic_ref = harness.ensure(spec_s)
    except FoundryError as error:
        _own_words(note, error)
        out.held = isinstance(error, HarnessRefused)
        out.note = f"the agents could not be made ready ({_why(s, error)})"
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
    run_seconds = max(1.0, budget - reserve)
    started = s.monotonic()
    max_calls = harness.budget.tool_calls if harness is not None else st.investigate_max_calls
    try:
        if harness is None:
            answer = s.foundry.run(investigator_ref, agents.investigator_input(max_calls), toolbox.call, max_calls=max_calls, max_seconds=run_seconds)
        else:
            answer = harness.run(investigator_ref, spec_i, agents.investigator_input(max_calls), toolbox.call, max_calls=max_calls, max_seconds=run_seconds)
    except FoundryError as error:
        partial = getattr(error, "partial", None)  # what the run had come to: the calls that it made and the tokens that it used
        out.tool_calls = len(_made(partial.calls)) if partial is not None else len(toolbox.log)
        out.tokens = partial.input_tokens + partial.output_tokens if partial is not None else 0
        flush_notes()
        _own_words(note, error)
        out.held = isinstance(error, HarnessRefused)
        out.note = f"the investigator gave no answer ({_why(s, error)})"
        finished(False, note=out.note)
        return out
    made = _made(answer.calls)
    refused = len(answer.calls) - len(made)
    out.tool_calls, out.tokens = len(made), answer.input_tokens + answer.output_tokens
    failed_calls = sum(1 for call in made if isinstance(call, dict) and call.get("ok") is False)
    out_of_time = answer.out_of_time
    investigator_step = step("investigator", st.foundry_model_investigator, started, True, (answer.input_tokens, answer.output_tokens),
                             f"{out.tool_calls} tool call{'' if out.tool_calls == 1 else 's'}" + (f", {failed_calls} failed" if failed_calls else "")
                             + (f", {refused} refused after the {'time' if out_of_time else 'budget'}" if refused else ""))
    if refused:
        spent = (f"its time for tool calls ({int(SOFT_TIME_SHARE * run_seconds)} seconds) was used up" if out_of_time
                 else f"its budget of {st.investigate_max_calls} was used up")
        note(f"the investigator asked for {refused} more tool call{'' if refused == 1 else 's'} after {spent}, and was refused")
    flush_notes()
    try:
        raw_findings, examined = parse_answer(answer.text)
    except RoleError as error:
        if harness is not None:
            harness.guard_failed(spec_i.name, "unreadable")
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
            if finding.unknown and harness is not None:
                harness.guard_failed(spec_i.name, "unknown-handle")  # an answer that cites a handle that no tool returned is a failure of the run, and a third failure trips the brake
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
            facts = _facts(finding, finding.cited[handle], costs[handle], _aggregates(toolbox.evidence, handle), len(finding.listed[handle]) if handle in finding.listed else None)
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

    # 3. The Skeptic tries to break the findings that are left, in one run. It is shown every resource that will be a case, as far as its input allows.
    skeptic_step: dict | None = None
    unjudged = hidden = 0  # the findings that got no verdict, and the resources that the Skeptic was not shown
    if survivors:
        started = s.monotonic()
        left = deadline - started
        if left <= 1.0:
            skeptic_step = step("skeptic", st.foundry_model_skeptic, started, False, None, "no time was left for the Skeptic")
        else:
            tokens: tuple[int, int] | None = None
            try:
                skeptic_text, shown_handles = _skeptic_input(survivors, toolbox)
                for finding in survivors:
                    for item in finding.items:
                        item.shown = item.handle in shown_handles
                hidden = sum(1 for finding in survivors for item in finding.items if not item.shown)
                if harness is None:
                    judged = s.foundry.run(skeptic_ref, skeptic_text, None, max_calls=0, max_seconds=left)
                else:
                    judged = harness.run(skeptic_ref, spec_s, skeptic_text, None, max_calls=0, max_seconds=left)
                tokens = (judged.input_tokens, judged.output_tokens)
                out.tokens += judged.input_tokens + judged.output_tokens
                try:
                    verdicts = parse_verdicts(judged.text, len(survivors))
                except RoleError:
                    if harness is not None:
                        harness.guard_failed(spec_s.name, "unreadable")
                    raise
                for index, verdict in verdicts.items():
                    survivors[index].verdict = verdict
                unjudged = len(survivors) - len(verdicts)
                skeptic_step = step("skeptic", st.foundry_model_skeptic, started, True, tokens, None)
            except (FoundryError, RoleError) as error:
                partial = getattr(error, "partial", None)
                if tokens is None and partial is not None:
                    tokens = (partial.input_tokens, partial.output_tokens)
                    out.tokens += partial.input_tokens + partial.output_tokens
                skeptic_step = step("skeptic", st.foundry_model_skeptic, started, False, tokens, _why(s, error))
                _own_words(note, error)
                hidden = 0  # the run did not judge anything, and its note says why
                if isinstance(error, HarnessRefused):
                    # The harness stopped the Skeptic after the Investigator had run (a switch pulled or a brake tripped in between): the investigation is held like one that was refused at the
                    # start, so that no case is opened from findings that nobody judged, and only the planted waste goes on (cases/run.py).
                    out.ran, out.held = False, True
                    out.note = f"the Skeptic was not let run ({_why(s, error)}), so no case was opened from this investigation"
                    flush_notes()
                    finished(False, note=out.note)
                    return out
            flush_notes()
        if not skeptic_step["ok"] or unjudged:
            reason = skeptic_step["note"] if not skeptic_step["ok"] else f"no verdict for {unjudged} of {len(survivors)} findings"
            note(f"the Skeptic could not judge every finding ({reason}); a finding without a verdict needs a person")
        if hidden:
            note(f"{hidden} resource{'' if hidden == 1 else 's'} of the findings {'was' if hidden == 1 else 'were'} not shown to the Skeptic, whose input is limited to "
                 f"{SKEPTIC_CHARS} characters, so a person has to judge {'it' if hidden == 1 else 'them'}")

    # 4. One line for each finding, then one case for each resource that is left.
    for finding in findings:
        h.emit("investigation.finding", finding=finding.number, basis=finding.basis or None, proposal=finding.proposal or None, confidence=finding.confidence,
               claimed=finding.claimed, handles=len(finding.items), unknown=finding.unknown, unproven=finding.unproven, repeated=finding.repeated,
               judgedLately=finding.recent, guarded=finding.guarded, capped=finding.capped, unmeasured=sum(1 for item in finding.items if not item.metrics),
               shown=sum(1 for item in finding.items if item.shown), coveredCostUsd30d=finding.covered_usd,
               verdict=finding.verdict.verdict if finding.verdict else None, kept=finding.reason is None, reason=finding.reason, note=finding.note, summary=finding.summary)
    models = {"investigator": st.foundry_model_investigator, "skeptic": st.foundry_model_skeptic}
    number = 0
    for finding in survivors:
        for item in finding.items:
            number += 1
            steps = tuple(x for x in (investigator_step, _skeptic_step_of(skeptic_step, finding, item)) if x is not None)
            _open_case(s, out, finding, item, models, steps, f"{h.run_id[:8]}-i{number}")
    out.kept = len(survivors)
    out.dropped_findings = len(raw_findings) - len(survivors)
    if out.guarded:
        note(f"the investigation held back {out.guarded} resource{'' if out.guarded == 1 else 's'} with a guard: " + ", ".join(f"{n} {name}" for name, n in sorted(held.items())))
    capped = sum(f.capped for f in findings)
    if capped:
        note(f"{capped} resource{'' if capped == 1 else 's'} of the findings {'is' if capped == 1 else 'are'} not listed as cases: a run opens at most {MAX_CASES}")
    for finding in survivors:
        if finding.note:
            note(f"finding {finding.number}: {finding.note}")
    if out.unmeasured:
        note(f"{out.unmeasured} resource{'' if out.unmeasured == 1 else 's'} of the findings {'has' if out.unmeasured == 1 else 'have'} no measurement that backs the "
             f"finding, so a person has to judge {'it' if out.unmeasured == 1 else 'them'}")
    finished(True, examined=examined, findingsKept=out.kept, findingsDropped=out.dropped_findings, cases=out.cases, guarded=out.guarded)
    note(f"the investigation made {out.tool_calls} tool call{'' if out.tool_calls == 1 else 's'}, kept {out.kept} of {len(raw_findings)} finding"
         f"{'' if len(raw_findings) == 1 else 's'} and opened {out.cases} case{'' if out.cases == 1 else 's'}")
    return out


def _skeptic_step_of(shared: dict | None, finding: Finding, item: Item) -> dict | None:
    """The step of the Skeptic as the case of one resource records it. The run of the Skeptic is the same for every case, but it did not judge this resource when it
    was not shown it, or when its finding has no verdict: the step is then not ok, so that the page says so and the recheck takes the resource up again at once."""
    if shared is None or not shared["ok"]:
        return shared
    if not item.shown:
        return {**shared, "ok": False, "note": NOT_SHOWN}
    if finding.verdict is None:
        return {**shared, "ok": False, "note": NO_VERDICT}
    return dict(shared)


def _owner_of(s: "Services", out: Investigation, lead: Lead) -> dict:
    """What the brief says about whose a resource is: a tag that conventionally names an owner, and who made and last changed it (ownership.py). It is shown to people and
    never goes to a model. A word that says why a read gave nothing (not visible, not in the window) is not a person: it is left out, so that the page says only what it knows."""
    reader = out.owners
    try:
        if reader is None:
            reader = out.owners = OwnerReader(s.arm, s.clock())
        hint = reader.hints(lead.resource_id, lead.tags)
        # A read that was refused, that failed or that was not made (the reads of the run were used up) answers nothing: the page must then say that the lookup was not made, and not that
        # the resource has no owner.
        looked_up = hint.get("lastChangedBy") not in (UNAVAILABLE, NOT_VISIBLE)
    except Exception as error:  # noqa: BLE001 (the owner line is a convenience: a lookup that fails never costs a case)
        LOG.warning("investigate: the owner of a resource could not be looked up (%s)", type(error).__name__)
        hint, looked_up = owner_hints(lead.tags, None, False, lead.resource_id, UNAVAILABLE), False
    sentinels = {NOT_COMPLETE, NOT_IN_WINDOW, NOT_VISIBLE, UNAVAILABLE}

    def real(value: object) -> str:
        return value if isinstance(value, str) and value not in sentinels else ""

    tags = hint.get("tags") if isinstance(hint.get("tags"), dict) else {}
    name = next((tag for tag in ("owner", "contact", "team", "manager", "createdby") if tags.get(tag)), "")
    return {"tagOwner": tags.get(name, ""), "tagName": name, "createdBy": real(hint.get("createdBy")), "createdAt": real(hint.get("createdAt")),
            "changedBy": real(hint.get("lastChangedBy")), "changedAt": real(hint.get("lastChangedAt")), "lookedUp": looked_up}


def _open_case(s: "Services", out: Investigation, finding: Finding, item: Item, models: dict, steps: tuple[dict, ...], case_id: str) -> None:
    """The case of one resource: decide.py gives it its status, the History gets its result, and the store keeps it when there is a store. The verdict of the Skeptic
    counts only for a resource that it was shown, and the case is never proposed without a measurement that code confirmed."""
    h = s.history
    lead = item.lead
    detective = DetectiveAnswer(finding.proposal, finding.confidence, finding.summary)
    judged = finding.verdict if item.shown else None
    outcome = decide.decide(lead, Guards({}), detective, judged, backed=bool(item.metrics), notes=(finding.note,) if finding.note else ())
    # What past requests like this showed may hold a proposal back for a person, and never makes a finding stronger (cases/learning.py). The case is always an advise plan's: no change is made for it.
    outcome, held = learning.hold(s.extras.store if s.extras is not None else None, learning.type_word(lead.resource_type), ADVISE, detective.confidence, outcome)
    learned = {"skeptic": judged.verdict if judged is not None else "none", **({"held": "history"} if held else {})}
    if not item.metrics:
        out.unmeasured += 1
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
            runs_seen=(old.runs_seen + 1) if old else 1, owner=_owner_of(s, out, lead), learned=learned)
        ex.store.case_put(record)
        if outcome.status in ("proposed", "needs_human"):
            plan = ex.approvals.plan_for(record, lead, ex.approvers())  # a plan of a change is made for none of these cases: the advise plan asks a person whether it is worth acting on
            if plan is not None:
                record = learning.remember(ex.store, record, plan)  # how past requests like this were answered: the one line of the brief
                h.emit("plan.created", planId=plan.plan_id, caseKey=record.case_id, family=plan.family, approvers=len(plan.approvers))
                ex.on_plan(plan, ex.store.case_get(record.case_id) or record)
    except (StoreError, ValueError) as error:
        h.emit("run.note", note=clean_text(s.redact(f"the case could not be kept in the store: {error}"), 300))
