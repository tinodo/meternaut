"""The investigation: two agents in Microsoft Foundry look for waste in the estate, and code checks every word of theirs against what the tools showed.

The Investigator reads the estate through the read-only tools of toolbox.py (handles instead of names, typed numbers instead of text) and ends with one JSON
object of findings. Nothing in it is believed before code has checked it:

- a handle that no tool showed is dropped, and so is a measurement whose total is not a number that the tools returned;
- a finding that claims no usage keeps only the resources whose cited measurements are nil in every total that the tools recorded for them;
- the cost of the resources is added up by code from the cost lines, and the agent never supplies a figure;
- the change that a finding states (its action, the meters that it would shrink and what remains of them) is checked against the meters and the numbers that the tools showed, and the saving
  is computed by code from the bill lines (cases/pricing.py);
- the settings that the change proposes to lower (`set`) and the other ways that it names to save on the same resource (`others`) are checked entry by entry against what the tools showed, and each
  other way is priced from the bill like the change (cases/proposals.py): an entry that fails is dropped and counted, and the finding stays;
- the guards of guards.py hold every resource, and a resource with a guard on leaves the finding;
- a second agent, the Skeptic, then tries to break the findings that are left, and decide.py gives each resource its status.

A resource whose finding cites no measurement that matched the tools is never proposed, whatever the agents say: a person has to judge it. The same holds for a
resource that the Skeptic was not shown, for a finding that it gave no verdict (or two verdicts) for, and for a finding whose confidence is not a number from 0 to 1.

Each resource of a finding that is left becomes one case, so that the History, the page of the case and the letters show it like any other case. The exception is a finding that asks
for a look (the proposal investigate) and has more than GROUP_MIN resources left after the checks of code: it is one case, which belongs to its dearest resource, and so one question to a
person, because nobody can use dozens of look-alike requests. The case keeps which resources it stands for. A case of a group that was judged lately stands for a later finding only when most of
that finding's resources (COVER_PERCENT) are ones that it stands for already; the resources of the finding that it stands for are not asked about again, and the others are a group of their own.
A resource that a person marked do-not-touch is never one of a group. Nothing here changes Azure: no plan of a change is made for a case that this module opens (approvals.create refuses it),
and the advise plan that asks a person whether it is worth acting on changes nothing in Azure.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Callable, Mapping

from . import activity, agents, beats, capability, decide, guards, impact, learning, pricing, proposals, roles, upkeep, wiring
from . import costs as cost_words
from . import estimate as estimates
from .approvals import is_fixture
from .arm import scopes_of
from .brief import MEASURED_DAYS, HELD_SHARED, HELD_UNPROVEN, IMPACT_VERDICTS, NOT_ASKED, about_use, says_nothing, shared, why_not_ask
from .detectors import Context, Lead
from .foundry import SOFT_TIME_SHARE, FoundryError
from .guards import Guards
from .harness import HarnessRefused
from .http import HttpError
from .memory_store import parse, stamp
from .models import ADVISE, AUTOMATED, GROUP_FACT, CaseRecord, StoreError
from .ownership import NOT_COMPLETE, NOT_IN_WINDOW, NOT_VISIBLE, UNAVAILABLE, OwnerReader, owner_hints
from .roles import DetectiveAnswer, RoleError, SkepticAnswer, clean_text
from .toolbox import MAX_CALLS, OWNER_READS, OWNER_SECONDS, SUBSCRIPTION_SECONDS, WARM_SECONDS, Resource, Toolbox, meter_word

if TYPE_CHECKING:
    from .run import Services

DETECTOR = "investigation"
MAX_CASES = 60  # the cases that one run opens
GROUP_MIN = 5  # a finding to investigate that has more resources than this left after the checks of code is one case, and one question to a person, not one for each resource
COVER_PERCENT = 80  # of each hundred resources of a later finding, how many a group case that was judged lately has to stand for already, for that case to stand for the finding too
GROUP_CASES_READ = 200  # the latest cases that are read once for a run, to find the groups
RECHECK_SLACK = dt.timedelta(hours=1)  # a case saved minutes after a run began is checked again by the run that begins RECHECK_DAYS later (run.TIMER_SLACK)
MAX_GROUP_NAMES = 12  # the names of the other resources that the case of such a finding keeps, for the page of a person
MAX_GROUP_IDS = 200  # the resource ids that the case of a group keeps, for its daily cost (run.read_cost_series)
MEMBER = re.compile(r"[0-9a-f]{12}")  # the short id of a resource that the case of a group keeps (Lead.lead_id)
MAX_ENTRIES = 720  # the entries of metric_evidence that are read: a handful for each of the handles that a finding may hold
MAX_FACT_METRICS = 12  # the measurements that a case keeps
NEAR_TOTAL = 0.05  # how close to a total of the tools, as a fraction of it, a cited number is counted as near (only a count: no number is accepted for it)
MAX_TOTALS = 20  # the totals of one measurement that are read: the toolbox records at most as many
SKEPTIC_METRICS = 6  # the measurements of one resource that the Skeptic sees, at most
SKEPTIC_PROPERTIES = 8  # the properties of one resource that the Skeptic sees
SKEPTIC_CHARS = 30000  # the size of the Skeptic's input
EXAMINED_KEPT = 24  # the phrases of examined that the investigation keeps from all its beats
SKEPTIC_CALLS = 4  # the calls of the Skeptic that findings are shared among when they do not fit in one input: a finding that gets none is left to a person
RICH_ROWS = 1  # the findings of one call of the Skeptic are the most that all keep the rows of this level of DETAIL, the second richest
RESERVE_SECONDS = 120.0  # what the Investigator leaves of its time for the checks and the Skeptic, at most
MAX_IMPACTS = 6  # the resources of one run whose impact is checked: each check takes about a dozen reads. A resource beyond this keeps the digest of its earlier case, and the cases with the oldest digest or none go first
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
    earlier: CaseRecord | None = None  # the case that an earlier Watch opened for the resource, when there is one
    marked: bool = False  # a person marked the resource do-not-touch


@dataclass
class Finding:
    """One finding of the Investigator and what code did to it. `reason` is set when the whole finding was dropped."""

    number: int
    basis: str = ""
    proposal: str = ""
    confidence: float = 0.0
    summary: str = ""
    note: str | None = None  # what code says about the finding, for a person: its confidence was not a number from 0 to 1, or it asked to delete and code turned that into a look
    asked: str = ""  # the proposal that the Investigator gave, when code turned it into a look (it asked to delete)
    claimed: int = 0  # the distinct handles that the answer listed
    handles: list[str] = field(default_factory=list)  # the handles that the tools showed, in the finding's order
    cited: dict[str, dict[str, float]] = field(default_factory=dict)
    listed: dict[str, set[str]] = field(default_factory=dict)  # the measurements that the agent cited for each handle, whether or not they matched the tools
    items: list[Item] = field(default_factory=list)
    unknown: int = 0
    unproven: int = 0
    repeated: int = 0
    surpassed: int = 0  # the resources that a later finding, which was surer of them, took from this one
    # Why the claims of the finding were not confirmed, as counts (the diagnosis of a run, from the History alone): the resources that it lists and gave no measurement for, and the measurements
    # that it cites for a resource that no tool measured, for a metric that no tool returned for the resource, or with a total that none of the tools' totals equals; and, for a claim of no usage,
    # the cited measurements that match the tools and still prove nothing: one that shows use, and one of too few days or with gaps.
    no_entry: int = 0
    not_measured: int = 0
    metric_unknown: int = 0
    differs: Counter = field(default_factory=Counter)  # the cited totals that equal none of the totals of the tools, by what the cited number is (_differs); `total_differs` is their sum
    shows_use: int = 0
    too_brief: int = 0
    recent: int = 0
    guarded: int = 0
    capped: int = 0
    small: int = 0  # the resources of a finding that together costs less than CASE_MIN_USD in the last 30 days: too small to ask a person for, so the finding opens no case (counted, never shown with a cost)
    seen: set[str] = field(default_factory=set)  # the short ids of every resource that the finding names and that the tools showed, whatever became of it
    stood: list[CaseRecord] = field(default_factory=list)  # the cases of a group, judged lately, that a resource of the finding is the first of: what the finding may be covered by
    silenced: int = 0  # the resources that a person marked do-not-touch and that the case of the group leaves out
    reason: str | None = None
    verdict: SkepticAnswer | None = None
    covered_usd: float | None = None
    change: pricing.Change | None = None  # the change that the Investigator stated, read strictly (cases/pricing.py); None when it stated none
    priced: pricing.Priced | None = None  # what code made of it for the resources that are left: the figure of each, or why it has none
    ways: proposals.Checked | None = None  # what code kept of the settings and the other ways that the change proposes, and what it dropped (cases/proposals.py)
    fates: dict[str, int] = field(default_factory=dict)  # its resources by what became of them: request, person, dropped, or why the request was held back (cases/activity.py)
    beat: int = 1  # the beat of the investigation whose session wrote it (cases/beats.py)

    @property
    def total_differs(self) -> int:
        return sum(self.differs.values())


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
    impact_reader: object = None  # the impact.Reader of the run: one for all its cases, with the OwnerReader above, so that the reads of the impact checks share one budget
    impacts: int = 0  # the resources whose impact was checked in this run (MAX_IMPACTS)
    impact_due: set[str] | None = None  # the lead ids whose impact this run checks, the oldest or no digest first (_impact_due); None: any, up to MAX_IMPACTS
    profile: object = None  # the CapabilityRecord of the run (cases/capability.py): what the identity can see of the agreement and of the commitments
    # True when the harness did not let the agents run (a pulled switch, a lock that does not hold, a stored definition that differs) or stopped a run: the run of the Watch then opens no new
    # case from the investigation, and the planted waste, the approvals and the messages go on (cases/harness.py).
    held: bool = False
    said_nothing: int = 0  # the cases whose request was not made because the finding cannot say what to look at (cases/upkeep.py): the Watch counts them with the findings that it held back
    held_back: dict[str, int] = field(default_factory=dict)  # the cases whose request was not made by the rules of cases/brief.py held_reason (unchecked, impact), by reason: counted with the findings that were held back
    not_asked: dict[str, int] = field(default_factory=dict)  # the cases that no request was made for by the rules of asking (approvals.py why_not_ask), by reason: the end note of the investigation counts them
    # What the record of the run is made from (cases/activity.py).
    toolbox: object = None
    answer: object = None
    examined: list[str] = field(default_factory=list)
    findings: list = field(default_factory=list)
    beats: list = field(default_factory=list)  # what each beat came to (cases/beats.py Result): the record of the run keeps them

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
    finding.change = pricing.parse(raw.get("change"))
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


def _quiet(aggregate: dict) -> bool:
    """A measured zero: every total that was recorded for the measurement is a number and nil, and a value was read on at least MEASURED_DAYS days of its window. Missing data is not zero: no
    data, a read that failed, a metric that the type does not offer and a few days of values are none of this."""
    days = aggregate["daysWithData"]
    return all(total is not None and total == 0 for total in aggregate["totals"]) and days is not None and days >= MEASURED_DAYS


def _zero_only(cited: Mapping, recorded: Mapping[str, dict]) -> bool:
    """Whether the measurements that a finding cited for one resource show that nothing used it: one of them is a measured zero (_quiet) and none of them shows anything. A measured zero does not
    outweigh a measurement of the same resource that shows use, whatever the basis of the finding is."""
    shown = [aggregate for name, aggregate in recorded.items() if name in cited]
    return any(_quiet(aggregate) for aggregate in shown) and not any(_nonzero(aggregate) for aggregate in shown)


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


def _cost_state(resource: Resource, context: Context | None, cost: float | None) -> str:
    """How the cost of a resource was read (cases/costs.py): lines, none (the cost lines were read and have none for it: not a cost of nothing), failed (those of its subscription could not be
    read), currency (they are not in US dollars) or "" (nothing says: a part of a resource, which is billed with the resource, has no line of its own)."""
    if cost is not None:
        return cost_words.LINES if cost > 0 else cost_words.NONE
    if getattr(resource, "part_of", None) is not None or context is None:
        return ""
    if context.costs is None:
        return cost_words.FAILED if context.cost_error else ""
    return cost_words.CURRENCY if context.costs and context.currency != "USD" else cost_words.NONE


def _estimate(toolbox: Toolbox, resource: Resource, state: str) -> dict:
    """The estimate at list price (cases/estimate.py) of a managed disk that Azure has no cost line for, and nothing for any other resource or any other state: it stands for no cost line."""
    if state != cost_words.NONE or resource.resource_type != estimates.DISK_TYPE:
        return {}
    sku, properties = toolbox.known_of(resource.handle)
    return estimates.disk_estimate(sku, properties.get(estimates.SIZE_PROPERTY))


def _subscription_name(s: "Services", subscription: str) -> str:
    """The display name of a subscription (Arm.subscription_name), which a person reads before an id. It is a convenience: a read that fails costs no case, and the pages then show the id."""
    try:
        return s.arm.subscription_name(subscription)
    except Exception:  # noqa: BLE001 (a name that cannot be read is no reason to lose a case)
        return ""


def _metric_of(recorded: dict[str, dict], name: str) -> str | None:
    """The metric of the evidence of a resource that a name of the agent stands for: the same name, or the same name in another case or with spaces round it (the same metric written another way),
    and only when one metric of the resource has that name; None when the tools returned no metric of that name for the resource."""
    if name in recorded:
        return name
    folded = name.strip().casefold()
    same = [known for known in recorded if known.strip().casefold() == folded]
    return same[0] if len(same) == 1 else None


def _outranks(finding: Finding, earlier: "Finding | None") -> bool:
    """A later finding takes a resource from an earlier one only when it is surer of it (its confidence is higher); with the same confidence the earlier keeps it."""
    return earlier is not None and earlier is not finding and finding.confidence > earlier.confidence


def _differs(said: float | int | None, shown: dict) -> str:
    """What a cited total is that equals none of the totals of the tools, for the diagnosis of a run: `none` (not a number), `zero`, `stat` (the maximum, the average or the days with data that the
    tools recorded for the measurement), `near` (within NEAR_TOTAL of a total) or `far`, in that order. It decides nothing: the entry is thrown away whichever it is."""
    if said is None:
        return "none"
    if said == 0:
        return "zero"
    if any(stat is not None and math.isclose(said, stat, rel_tol=1e-6, abs_tol=0.0) for stat in (shown["max"], shown["average"], shown["daysWithData"])):
        return "stat"
    return "near" if any(t is not None and abs(said - t) <= NEAR_TOTAL * abs(t) for t in shown["totals"]) else "far"


def _verify(finding: Finding, handles: list[str], entries: object, toolbox: Toolbox, taken: set[str], holders: "dict[str, Finding] | None" = None) -> None:
    """Keeps of a finding what the tools showed. `taken` holds the handles of the findings before it: a resource belongs to one finding only, the surer one of two (`holders` says which
    finding has each handle; the earlier keeps it when they are as sure).

    An entry of metric_evidence counts when its total is one of the totals that the tools recorded for that handle and metric; the number that is kept is the tools'.
    A claim of no usage is proved by such an entry only when every total that was recorded for the metric is nil and a value was read on at least MEASURED_DAYS days (_quiet): a short
    measurement that shows nil does not cancel a longer one that showed something, and no data, a failed read or a few days prove nothing. A resource with a cited measurement that shows
    something, or with none that proves it, leaves a finding of no usage."""
    known: list[str] = []
    for handle in handles:
        if handle not in toolbox.handles:
            finding.unknown += 1
        elif handle in taken and not _outranks(finding, (holders or {}).get(handle)):
            finding.repeated += 1
        else:
            known.append(handle)
    cited: dict[str, dict[str, float]] = {handle: {} for handle in known}
    contradicted: set[str] = set()
    recorded = {handle: _aggregates(toolbox.evidence, handle) for handle in known}
    for entry in (entries if isinstance(entries, list) else [])[:MAX_ENTRIES]:
        if not isinstance(entry, dict) or not isinstance(entry.get("handle"), str) or entry["handle"] not in cited or not isinstance(entry.get("metric"), str):
            continue
        handle = entry["handle"]
        metric = _metric_of(recorded[handle], entry["metric"])  # the name as the tools gave it: the same name, or the same name in another case, and nothing else
        finding.listed.setdefault(handle, set()).add(metric or entry["metric"])
        said = _number(entry.get("total"))
        shown = recorded[handle].get(metric) if metric is not None else None
        if shown is None:
            if recorded[handle]:
                finding.metric_unknown += 1  # the resource was measured, and no tool returned a metric of this name for it
            else:
                finding.not_measured += 1  # no tool measured the resource at all
            continue
        total = None if said is None else next((t for t in shown["totals"] if t is not None and math.isclose(said, t, rel_tol=1e-6, abs_tol=0.0)), None)
        if total is None:
            finding.differs[_differs(said, shown)] += 1  # not a number, or one that none of the totals that the tools returned for the metric equals
            continue  # an entry that is not a number of the tools is thrown away, and an absent measurement proves nothing
        if finding.basis == "no-usage":
            numbers = [t for t in shown["totals"] if t is not None]
            if any(t != 0 for t in numbers):
                finding.shows_use += 1
                contradicted.add(handle)
                continue
            if not _quiet(shown):
                finding.too_brief += 1
                continue  # a measurement that was absent at some time, or that has values on too few days, proves nothing
        if len(cited[handle]) < MAX_FACT_METRICS:
            cited[handle][metric] = total
    finding.no_entry = sum(1 for handle in known if handle not in finding.listed)  # the resources that the finding lists and that it gave no measurement for
    if finding.basis == "no-usage":
        kept = [handle for handle in known if cited[handle] and handle not in contradicted]
        finding.unproven = len(known) - len(kept)
        known = kept
    finding.handles = known
    finding.cited = {handle: cited[handle] for handle in known}
    taken.update(known)
    for handle in known:
        earlier = (holders or {}).get(handle)
        if earlier is not None and earlier is not finding and handle in earlier.handles:
            earlier.handles = [kept for kept in earlier.handles if kept != handle]  # the surer finding has it now: the earlier gives it up, and is dropped when it has none left
            earlier.cited.pop(handle, None)
            earlier.surpassed += 1
            if not earlier.handles and earlier.reason is None:
                earlier.reason = _why_none(earlier)
        if holders is not None:
            holders[handle] = finding
    if not known:
        finding.reason = _why_none(finding)


def _why_none(finding: Finding) -> str:
    parts = [f"{n} {what}" for n, what in ((finding.unknown, "that no tool showed"), (finding.unproven, "without a cited measurement that matches the tools and shows no usage on enough days"),
                                          (finding.repeated, "that an earlier finding has"), (finding.surpassed, "that a later finding, which is surer of them, has")) if n]
    return "no resource of it is left: " + (", ".join(parts) if parts else "it lists none that the tools showed")


def _hold_delete(finding: Finding, toolbox: Toolbox) -> None:
    """A finding is to delete only when every resource of it has a measured zero among the measurements that it cited (_quiet) and none is a resource that others share (cases/brief.py SHARED):
    any other that asks to delete asks for a look, and says so in its note. Missing data is not zero, and a resource that others share is not deleted on a measurement alone."""
    if finding.proposal != "delete" or not finding.handles:
        return
    others = any(shared(toolbox.handles[handle].resource_type) for handle in finding.handles)
    proved = all(_zero_only(finding.cited[handle], _aggregates(toolbox.evidence, handle)) for handle in finding.handles)
    if proved and not others:
        return
    finding.asked, finding.proposal = finding.proposal, "investigate"
    said = HELD_SHARED if others else HELD_UNPROVEN
    finding.note = f"{said}; {finding.note}" if finding.note else said


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


def _earlier(s: "Services", lead: Lead) -> CaseRecord | None:
    """The case that an earlier Watch opened for the resource of a lead: None when there is no store, when nothing was opened, or when the store cannot be read."""
    ex = s.extras
    if ex is None:
        return None
    try:
        return ex.store.case_get(f"k{lead.lead_id}")
    except StoreError:
        return None


def _recent(s: "Services", old: CaseRecord | None, facts: dict | None, open_questions: "learning.OpenQuestions | None" = None) -> bool:
    """Whether the earlier case of a resource (None: there is none) keeps the resource from being taken up again now: see _judged_lately. `facts` None: the evidence is not compared."""
    ex = s.extras
    if ex is None or old is None or old.status in ("error", "failed") or not old.updated_at or any(isinstance(x, dict) and x.get("ok") is False for x in old.steps):
        return False
    if s.clock() - parse(old.updated_at) >= dt.timedelta(days=ex.settings.recheck_days) - RECHECK_SLACK:
        return False
    if old.status in ("proposed", "needs_human", "dropped"):
        if open_questions is not None and open_questions.is_open(old):
            return False
        return facts is None or _signature(old.facts if isinstance(old.facts, dict) else {}) == _signature(facts)
    return True


def _judged_lately(s: "Services", lead: Lead, facts: dict, open_questions: "learning.OpenQuestions | None" = None) -> bool:
    """A resource whose case was updated within the days of RECHECK_DAYS is not taken up again unless its evidence changed. A case that ended in an error, or
    whose steps did not all work, is taken up again at once. A case that a person has answered, or that the loop has taken on, is left alone for the whole time.

    An open question (learning.OpenQuestions: a case that needs a person or is proposed, with no request to a person open or with a first AI that was not sure enough, that nobody
    answered lately and that is not marked do-not-touch) is taken up again at once when the Investigator cites it again, whether its evidence changed or not: it comes back with the tools
    until it is decision-ready or dropped, and a case that older code left with no request gets its request."""
    return _recent(s, _earlier(s, lead), facts, open_questions)


def _stands_for_a_group(case: CaseRecord | None) -> bool:
    """Whether an earlier case stands for the group of resources of a finding (cases opened by this module with a group in their facts)."""
    return case is not None and isinstance(case.facts, dict) and isinstance(case.facts.get(GROUP_FACT), dict)


def _members_of(case: CaseRecord) -> set[str]:
    """The short ids of the resources that the case of a group stands for, as the case keeps them: only the resource that it belongs to when it keeps none (a case that a run made before it did)."""
    found = case.facts.get(GROUP_FACT) if isinstance(case.facts, dict) else None
    listed = found.get("members") if isinstance(found, dict) else None
    ids = {item for item in listed if isinstance(item, str) and MEMBER.fullmatch(item)} if isinstance(listed, list) else set()
    return ids or {case.case_id[1:]}


def _alike(later: set[str], stored: set[str]) -> bool:
    """Whether most of `later` (COVER_PERCENT of them) is in `stored`: a group that stands for most of what a finding names stands for the finding."""
    return bool(later) and len(later & stored) * 100 >= COVER_PERCENT * len(later)


def _marked(s: "Services") -> set[str] | None:
    """The ids, in lower case, of the resources that a person marked do-not-touch; None when the store cannot be read: the investigation does not run then."""
    if s.extras is None:
        return set()
    try:
        return {key.lower() for key in s.extras.store.do_not_touch()}
    except StoreError as error:
        LOG.warning("investigate: the do-not-touch marks could not be read: %s", s.redact(str(error)))
        return None


def _groups_lately(s: "Services") -> list[CaseRecord]:
    """The cases of groups among the latest cases, read once for a run."""
    if s.extras is None:
        return []
    try:
        return [case for case in s.extras.store.cases_recent(GROUP_CASES_READ) if _stands_for_a_group(case)]
    except StoreError:
        return []


def _settle(finding: Finding, marked: set[str]) -> int:
    """What the cases of groups that were judged lately, and the marks of people, make of the resources that a finding to investigate has left. Returns the places of the cap of cases that this frees.

    A case of a group that a resource of the finding is the first of stands for the whole finding when most of the finding's resources are ones that it stands for (`_alike`): nothing of the finding
    is taken up again. When it stands for few of them, the resources that it does stand for are left out, since they were asked about, and the others go on: they are a group of their own, or
    cases of their own when they are few. A finding that is one case (see _group_of) leaves out the resources that a person marked do-not-touch, and says how many; a finding with fewer
    resources has a case for each of them as ever, and approvals.advise makes no request for one that is marked."""
    if finding.proposal != "investigate":
        return 0
    freed = 0
    if finding.stood:
        stored = set().union(*(_members_of(case) for case in finding.stood))
        if _alike(finding.seen, stored):
            freed = len(finding.items)
            finding.recent += freed + finding.capped
            finding.items, finding.capped = [], 0
            return freed
        left = [item for item in finding.items if item.lead.lead_id not in stored]
        freed = len(finding.items) - len(left)
        finding.recent += freed
        finding.items = left
    open_items = []
    for item in finding.items:
        item.marked = item.lead.resource_id.lower() in marked
        if not item.marked:
            open_items.append(item)
    if GROUP_MIN < len(open_items) < len(finding.items):
        finding.silenced = len(finding.items) - len(open_items)
        freed += finding.silenced
        finding.items = open_items
    return freed


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


def _skeptic_text(findings: list[Finding], toolbox: Toolbox, level: tuple, left_out: set[str] | frozenset[str] = frozenset()) -> str:
    """The input of the Skeptic for these findings at one level of DETAIL, without the resources of `left_out`."""
    count, fields, sku, properties = level
    listed = []
    for index, f in enumerate(findings):
        rows = [_row(item, toolbox, count, fields, sku, properties) for item in f.items if item.handle not in left_out]
        said = {"index": index, "basis": f.basis, "proposal": f.proposal, "confidence": f.confidence, "summary": f.summary, "resources": len(f.items),
                "costUsd30d": f.covered_usd, "evidence": rows, "evidenceShown": len(rows)}
        kept = {item.handle for item in f.items}
        model = pricing.view(f.change, f.priced, getattr(toolbox, "meters", {}), meter_word, count, left_out | (set(f.handles) - kept)) if f.priced is not None else None
        if model and model["effects"]:
            said["change"] = model  # the model of the saving, for the Skeptic to judge: the lines that it rests on and what remains of them, never the words of the AI for a person
        said.update(proposals.view((item.handle, item.lead.facts) for item in f.items if item.handle not in left_out))  # the settings and the other ways that code kept, as typed data
        listed.append(said)
    return agents.skeptic_input(listed)


def _skeptic_input(findings: list[Finding], toolbox: Toolbox) -> tuple[str, set[str]]:
    """The input of the Skeptic and the handles of the resources that it shows. It shows every resource that will be a case, with the richest rows that fit
    SKEPTIC_CHARS. When even the poorest rows do not fit, the cheapest resources are left out, and the case of a resource that was not shown needs a person."""
    items = [item for finding in findings for item in finding.items]
    left_out: set[str] = set()
    for level in DETAIL:
        text = _skeptic_text(findings, toolbox, level)
        if len(text) <= SKEPTIC_CHARS:
            return text, {item.handle for item in items}
    for item in sorted(items, key=lambda i: (i.lead.cost_usd_30d or 0.0, i.handle)):
        left_out.add(item.handle)
        text = _skeptic_text(findings, toolbox, DETAIL[-1], left_out)
        if len(text) <= SKEPTIC_CHARS:
            break
    return text, {item.handle for item in items} - left_out


def _batches(findings: list[Finding], toolbox: Toolbox) -> list[tuple[list[Finding], str, set[str]]]:
    """The findings in the groups that the Skeptic judges one call each, with the input of each and the handles that it shows. A finding joins the group before it while all of them keep the rows of level
    RICH_ROWS of DETAIL within SKEPTIC_CHARS, so that the Skeptic is not given poorer rows for being given more findings; a finding that does not fit alone is cut as it always was (_skeptic_input)."""
    groups: list[list[Finding]] = []
    for finding in findings:
        if groups and len(_skeptic_text(groups[-1] + [finding], toolbox, DETAIL[RICH_ROWS])) <= SKEPTIC_CHARS:
            groups[-1].append(finding)
        else:
            groups.append([finding])
    return [(group, *_skeptic_input(group, toolbox)) for group in groups]


# -- the cases ---------------------------------------------------------------------------------------------------------------------------------------

def _lead(resource: Resource, facts: dict, cost: float | None, advisor: float | None, state: str = "", estimate: dict | None = None) -> Lead:
    return Lead(detector=DETECTOR, resource_id=resource.resource_id, resource_type=resource.resource_type, name=resource.name, resource_group=resource.resource_group,
                subscription_id=resource.subscription_id.lower(), location=resource.location, tags=dict(resource.tags), managed_by=resource.managed_by, facts=facts,
                advisor_saving_usd=advisor, cost_usd_30d=cost, cost_state=state, estimate=dict(estimate or {}))


def _facts(finding: Finding, metrics: dict[str, float], cost: float | None, recorded: Mapping[str, dict] | None = None, listed: int | None = None) -> dict:
    """The typed digest of a case: what the finding rests on, and no name. `recorded` is what the tools showed for the resource (its unit and the days of each measurement)
    and `listed` how many measurements the agent cited for it: a person reads "code re-checked 5 of 6 numbers" from them."""
    facts: dict = {"basis": finding.basis, "proposal": finding.proposal, "metrics": dict(metrics), "costUsd30d": cost, "finding": finding.number}
    shown = recorded or {}
    units = {name: shown[name]["unit"] for name in metrics if name in shown and shown[name].get("unit")}
    days = {name: shown[name]["days"] for name in metrics if name in shown and shown[name].get("days")}
    seen = {name: shown[name]["daysWithData"] for name in metrics if name in shown and shown[name].get("daysWithData") is not None}
    if units:
        facts["metricUnits"] = units
    if days:
        facts["metricDays"] = days
    if seen:
        facts["metricDaysWithData"] = seen  # the days of the window that had a value: a measured zero needs MEASURED_DAYS of them (brief.measured_zero)
    if finding.asked:
        facts["asked"] = finding.asked
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
    opened = s.clock()
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
        activity.keep(s, out, contexts, trigger=getattr(s, "trigger", ""), opened=opened)  # never raises


def _investigate(s: "Services", contexts: Mapping[str, Context], notes: list[str], toolbox: Toolbox | None, out: Investigation) -> Investigation:
    h, st = s.history, s.settings
    if not st.investigate:
        out.off, out.note = True, "it is switched off"
        return out
    if not st.foundry_endpoint or s.foundry is None:
        out.off, out.note = True, "no Foundry endpoint is set"
        return out
    marked = _marked(s)  # read before the agents run, so that nothing is spent when it cannot be: the marks decide which resources a group stands for
    if marked is None:
        out.note = "the marks of people, who asked that a resource is left alone, could not be read"
        return out

    def note(text: str) -> None:
        text = clean_text(s.redact(text), 300)
        notes.append(text)
        h.emit("run.note", note=text)

    began = s.monotonic()
    budget = max(1.0, float(st.investigate_max_seconds))
    deadline = began + budget
    s.client.deadline = deadline
    # The parts of the estate that the Investigator looks at one after the other, dearest first (cases/beats.py). When no cost is known to rank by, or INVESTIGATE_BEATS is 1 (the way back), one open
    # beat is the whole estate, as one session always looked at it. What the runs of the last days looked at (their records) decides which resources the seeds start from and which kinds the last beat names.
    remembered = activity.earlier(s.extras.store, s.clock()) if s.extras is not None else (frozenset(), frozenset(), frozenset())  # None: the records could not be read
    looked, touched, unrecorded = remembered or (frozenset(), frozenset(), frozenset())
    assumed = dict.fromkeys(unrecorded, beats.SEED_RESOURCES)  # the runs from before the hashes seeded the dearest SEED_RESOURCES of the kinds of their beats: code's reads take them as looked at, in the kinds that the records without a hash touched, beside the hashes
    plan = (beats.plan(*beats.spend(contexts), st.investigate_beats, touched) if st.investigate_beats > 1 else []) or [beats.Beat()]
    focused = not plan[0].open
    built_here = toolbox is None
    if toolbox is None:
        toolbox = Toolbox(s.arm, st.subscriptions, s.clock(), [])
        toolbox.memory = s.extras.store if s.extras is not None else None  # what the tools that recall read: the lessons, the claims and the open questions of the store of the loop
        # One call may take at most an eighth of the investigation's time, or the default, for reading the subscriptions, so that a call over a large estate cannot use the time that the
        # Investigator needs for its answer and the Skeptic for its verdicts.
        toolbox.read_seconds = min(SUBSCRIPTION_SECONDS, max(5.0, budget / 8))
        # The Activity Logs that the tools read (age and last change of a resource) are kept where the reads for the cases keep them, so that nothing is read twice, and they have a budget of their own, so
        # that an agent that asks for many cannot use up the reads that the cases need for who changed a resource. The budget is that of one beat for each beat.
        out.owners = out.owners or OwnerReader(s.arm, s.clock())
        toolbox.owners = out.owners.sharing(max_reads=OWNER_READS * len(plan), seconds=OWNER_SECONDS * len(plan))
    toolbox.window, toolbox.backfill = looked, assumed
    toolbox.emit = h.emit  # a line of the History for each try that reaches the price list (events.PRICE_KINDS)
    out.toolbox = toolbox
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
    if built_here:
        # What the identity can see of the agreement and the commitments: read once for the run, only when the agents will run, kept for the run, and shown by `commitments` and by the brief
        # of a finding about a commitment.
        toolbox.profile = capability.keep(s.extras.store if s.extras is not None else None,
                                          capability.probe(s.arm, st.subscriptions, st.quota_ids, contexts, h.run_id, s.clock()))
    out.profile = getattr(toolbox, "profile", None)
    h.emit("investigation.started", investigator=investigator_ref, skeptic=skeptic_ref, modelInvestigator=st.foundry_model_investigator,
           modelSkeptic=st.foundry_model_skeptic, maxCalls=len(plan) * st.investigate_beat_calls if focused else st.investigate_max_calls, maxSeconds=int(budget),
           **({"beats": len(plan)} if focused else {}))
    if remembered is None:
        note(activity.UNREADABLE)
    # The price book is filled before the first question: the list is read for the products of the dearest meters that it does not hold fresh, with no model call and no call of a tool of the run
    # (Toolbox.warm_prices), in at most an eighth of the investigation's time, like a call of a tool, and in no more than WARM_SECONDS. It never fails the run, and it has no effect when the store has
    # no book.
    warm = getattr(toolbox, "warm_prices", None)
    if warm is not None:
        try:
            warmed_up = warm(min(WARM_SECONDS, budget / 8))
        except Exception as error:  # noqa: BLE001 (a warm-up never fails the run)
            note(f"the price book could not be warmed ({type(error).__name__})")
        else:
            if warmed_up is not None:
                note(f"the price book: {warmed_up[0]} products read from the price list, {warmed_up[1]} already in the book, {warmed_up[2]} not read")

    def finished(ok: bool, **fields: object) -> None:
        out.seconds = int(s.monotonic() - began)
        counts = activity.coverage(toolbox)
        if any(counts):
            if remembered is not None:  # what is new is only said against a memory that was read
                note(activity.looked_note(*counts, assumed))
                notes.insert(0, notes.pop())  # first, so that the cap on the notes that a run keeps never takes it
            fields.update(zip(("profiled", "firstTime", "inWindow"), counts[:1] if remembered is None or assumed else counts))
        h.emit("investigation.finished", ok=ok, toolCalls=out.tool_calls, tokens=out.tokens, seconds=out.seconds, **({"beats": len(out.beats)} if focused else {}), **fields)

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

    # 1. The Investigator reads the estate with the tools, one beat after another (cases/beats.py): each beat is a session of its own, in a budget of calls, seconds and tokens of its own, on this one toolbox, so
    # that nothing that a beat read is read again. It is given what code read of its dearest resources and what the beats before it concluded. A beat that fails is a note and the others go on; the harness
    # refusing any of them holds the whole investigation.
    reserve = min(RESERVE_SECONDS, budget / 4)
    beats_deadline = deadline - reserve
    max_calls = harness.budget.tool_calls if harness is not None else st.investigate_max_calls
    findings: list[Finding] = []
    out.findings = findings
    taken: set[str] = set()
    holders: dict[str, Finding] = {}  # the finding that has each resource of `taken`: a later finding that is surer takes it
    beat_steps: dict[int, dict] = {}
    raw_total, last_note = 0, ""

    def close(result: beats.Result, ok: bool, at: float, log_before: int) -> None:
        result.seconds = result.seconds or int(s.monotonic() - at)
        result.looked = beats.looked(toolbox, result.beat, log_before)
        out.beats.append(result)
        if focused:
            h.emit("investigation.beat", beat=result.beat.number, of=result.beat.of, kinds=len(result.beat.kinds), billing=result.beat.billing, seeded=result.seeded, looked=result.looked,
                   toolCalls=result.calls, tokens=result.tokens, seconds=result.seconds, end=result.end, ok=ok, findings=result.found, **({"salvaged": True} if result.salvaged else {}))

    # The time of a tool call is taken from the toolbox's own clock, so that the lines of the calls read no clock of the run.
    tool_clock = getattr(toolbox, "monotonic", time.monotonic)

    def say_call(beat: beats.Beat, number: list[int], by: str, fields: dict) -> None:
        number[0] += 1
        try:
            h.emit("investigation.call", beat=beat.number, n=number[0], by=by, **fields)
        except Exception:  # noqa: BLE001 (a line of the History never costs the agent its answer)
            LOG.warning("a line of a tool call could not be written")

    def recorded(beat: beats.Beat, by: str, number: list[int]) -> Callable[[str, dict], str]:
        """The handler of the tool calls of a beat: the toolbox's own, and one line of the History for each call that it runs (cases/beats.call_fields), `by` code for the reads that code makes for a
        beat and `agent` for the calls of the Investigator."""
        def handler(name: str, arguments: dict) -> str:
            began = tool_clock()
            # The picture that code reads for a beat has a time of its own, so that a resource with very many measurements cannot take the time of the beat: what does not finish is unread and named.
            capped = by == "code" and name == "profile" and hasattr(toolbox, "budget_seconds")
            # The list prices that code reads are a trial of the toolbox: what it leaves behind never costs the call of the Investigator for the same prices its own read (Toolbox.trial).
            trying = by == "code" and name == "price_alternatives" and hasattr(toolbox, "trial")
            # The listings that code reads for a beat start from what no run of the last days looked at; the Investigator's own listing is the dearest first, as it always was (Toolbox.rotate).
            rotating = by == "code" and name == "list_resources" and hasattr(toolbox, "rotate")
            if capped:
                kept_budget = toolbox.budget_seconds
                toolbox.budget_seconds = min(kept_budget, beats.SEED_PICTURE_SECONDS)
            if trying:
                toolbox.trial = True
            if rotating:
                toolbox.rotate = True
            try:
                text = toolbox.call(name, arguments)
            finally:
                if capped:
                    toolbox.budget_seconds = kept_budget
                if trying:
                    toolbox.trial = False
                if rotating:
                    toolbox.rotate = False
            try:
                fields = beats.call_fields(name, arguments, text, tool_clock() - began)
                saved = toolbox.log[-1].get("saved") if toolbox.log and isinstance(toolbox.log[-1], dict) else None
                if fields and isinstance(saved, (int, float)) and not isinstance(saved, bool) and saved > 0:
                    fields["savedSeconds"] = round(float(saved), 1)  # a picture that was kept: the seconds that its read took, which this call did not spend
            except Exception:  # noqa: BLE001 (the same: nothing that the line needs may fail a call)
                fields = {}
            if fields:
                say_call(beat, number, by, fields)
            return text
        return handler

    def say_refused(beat: beats.Beat, number: list[int], run: object) -> None:
        """A line for each of the first calls that the agent asked for after its budget was used up, and was refused: what it still wanted is what a person reading the History looks for."""
        asked = [call for call in getattr(run, "calls", ()) if isinstance(call, dict) and call.get("refused")]
        for call in asked[: beats.REFUSED_LINES]:
            say_call(beat, number, "agent", beats.call_fields(call.get("name"), call.get("arguments"), None, 0.0, refused=True))

    def warmed(beat: beats.Beat, number: list[int]) -> Callable[[object], object] | None:
        """The read ahead that the toolbox makes of the resources of a beat's kinds, all at the same time, and one line of the History for it when it read something (cases/beats.seed)."""
        preload = getattr(toolbox, "preload", None)
        if preload is None:
            return None

        def warm(kinds: object) -> object:
            began = tool_clock()
            read = preload(kinds)
            if read:
                say_call(beat, number, "code", {"tool": beats.PRELOAD, "handles": 0, "ok": True, "chars": 0, "seconds": round(max(0.0, tool_clock() - began), 1)})
            return read
        return warm

    seeds: list[float] = []  # the seconds that the reads of each beat took: what the next beat is expected to need before the model starts

    def not_started(rest: list[beats.Beat], end: str, why: str) -> None:
        """The beats that the investigation has no time or no tokens left for are in the record, with their kinds and no number, so that what was not looked at is said and not only missing."""
        note(f"{why} after {len(out.beats)} of {len(plan)} beats, so the kinds of the others were not looked at")
        for left in rest:
            close(beats.Result(left, end=end), False, s.monotonic(), len(toolbox.log))

    for position, beat in enumerate(plan):
        at = s.monotonic()
        # A beat starts only when it can afford its own reads and its allowance for the model: the reads of the beats before it took what they took, and one that is not read yet is estimated.
        needs = max(beats.MIN_SECONDS, (sum(seeds) / len(seeds) if seeds else beats.SEED_ESTIMATE_SECONDS) + beats.times(st.investigate_beat_seconds)[1])
        if out.beats and beats_deadline - at < needs:
            not_started(plan[position:], "time", "the time of the investigation was used up")
            break
        if out.beats and focused and st.investigate_total_tokens - out.tokens < beats.MIN_TOKENS:
            not_started(plan[position:], "tokens", f"the tokens of the investigation ({st.investigate_total_tokens}) were used up")
            break
        calls, cap = (st.investigate_beat_calls, min(st.investigate_beat_tokens, st.investigate_total_tokens - out.tokens)) if focused else (max_calls, None)
        result = beats.Result(beat, max_calls=calls)
        log_before = len(toolbox.log)
        number = [0]  # the tool calls of this beat that have a line in the History: the reads that code makes for it first, then the calls of its session
        if focused:
            # Each beat has an allowance of calls of its own on the shared toolbox, whatever the beats before it used: the reads that code makes for it and the calls of its session (the toolbox allows MAX_CALLS and what is added).
            toolbox.extra_calls = max(toolbox.extra_calls, log_before + beats.SEED_CALLS + calls - MAX_CALLS)
        seeded = beats.seed(recorded(beat, "code", number), beat, warmed(beat, number)) if focused else None
        calls_from = len(toolbox.log) if focused or out.beats else 0  # the calls of the beat's own session are the ones after the reads that code made for it
        if seeded is not None:
            result.seeded = len(seeded.handles)
            seeded.seen = getattr(toolbox, "seen_in", lambda kinds: 0)(beat.kinds)
            if seeded.failed:
                note(f"beat {beat.number}: {seeded.failed} of the reads that code makes for its start could not be read in full")
        if focused:
            seeds.append(s.monotonic() - at)
        if beats.empty(beat, seeded):
            # What code listed holds no resource of the kinds of this beat: there is nothing to look at, so no session is run and no token is spent. The next beats are told that its kinds were not judged.
            result.end, result.note = beats.EMPTY, "no resource of its kinds was listed, so the Investigator was not asked"
            last_note = last_note or result.note
            note(f"beat {beat.number}: {result.note}")
            close(result, True, at, log_before)
            continue
        # The model and its tool calls have the seconds of the setting, whatever the reads of the beat took, inside what is left of the time of the investigation: its tool calls are refused after half of them
        # and it has a minute more to write its answer (beats.times).
        allowed = max(1.0, min(st.investigate_beat_seconds, beats_deadline - s.monotonic())) if focused else 0.0
        soft_seconds, seconds = beats.times(allowed) if focused else (None, min(beats.OPEN_SECONDS, max(1.0, budget - reserve)))
        if focused and allowed < beats.STEP_SECONDS:
            # What is left after the reads that code made does not pay for one step of the model: the model is not asked, and the beat fails at no cost in tokens.
            result.end, result.note = "time", f"no time was left for the model after the reads that code made for the beat"
            last_note = result.note
            note(f"beat {beat.number}: {result.note}; the other beats go on")
            close(result, False, at, log_before)
            continue
        what = beats.beat_input(beat, calls, seeded, beats.carry(out.beats))
        who = f"beat {beat.number}: " if focused else ""
        handler = recorded(beat, "agent", number)
        if harness is not None and out.beats:
            harness.again(spec_i)  # each beat is a run of its own: its own tokens, its own refusals and its own line
        # A beat that is cut off is asked once more, with no tool, to write its answer, when at least beats.SALVAGE_MIN_LEFT seconds are left in the time of the beats.
        timing = {"soft_seconds": soft_seconds, "salvage": lambda: beats.SALVAGE_SECONDS if beats_deadline - s.monotonic() >= beats.SALVAGE_MIN_LEFT else 0.0} if focused else {}
        try:
            if harness is None:
                answer = s.foundry.run(investigator_ref, what, handler, max_calls=calls, max_seconds=seconds, **({"max_tokens": cap} if cap else {}), **timing)
            else:
                answer = harness.run(investigator_ref, spec_i, what, handler, max_calls=calls, max_seconds=seconds, **({"max_tokens": cap} if cap else {}), **timing)
        except FoundryError as error:
            partial = getattr(error, "partial", None)  # what the run had come to: the calls that it made and the tokens that it used
            say_refused(beat, number, partial)
            if getattr(partial, "salvage_failed", ""):
                note(f"{who}the last request for the answer of {'beat ' + str(beat.number) if focused else 'the investigator'} failed: {clean_text(partial.salvage_failed, 40)}")
            result.calls = len(_made(partial.calls)) if partial is not None else len(toolbox.log) - calls_from
            result.tokens = partial.input_tokens + partial.output_tokens if partial is not None else 0
            out.answer, out.tool_calls, out.tokens = partial, out.tool_calls + result.calls, out.tokens + result.tokens
            flush_notes()
            _own_words(note, error)
            result.end = activity.end_of_run(isinstance(error, HarnessRefused), partial, False)
            result.note = last_note = f"the investigator gave no answer ({_why(s, error)})"
            close(result, False, at, log_before)
            if isinstance(error, HarnessRefused):
                out.ran, out.held, out.note = False, True, result.note  # whatever the beats before it found is held with it: nobody judged it
                finished(False, note=out.note)
                return out
            if focused:
                note(f"{who}{result.note}; the other beats go on")
            continue
        made = _made(answer.calls)
        refused = len(answer.calls) - len(made)
        say_refused(beat, number, answer)
        out.answer = answer
        result.calls, result.tokens = len(made), answer.input_tokens + answer.output_tokens
        out.tool_calls, out.tokens = out.tool_calls + result.calls, out.tokens + result.tokens
        failed_calls = sum(1 for call in made if isinstance(call, dict) and call.get("ok") is False)
        out_of_time, out_of_tokens = answer.out_of_time, getattr(answer, "out_of_tokens", False)
        beat_steps[beat.number] = step("investigator", st.foundry_model_investigator, at, True, (answer.input_tokens, answer.output_tokens),
                                       (f"beat {beat.number} of {beat.of}, " if focused else "") + f"{result.calls} tool call{'' if result.calls == 1 else 's'}" + (f", {failed_calls} failed" if failed_calls else "")
                                       + (f", {refused} refused after the {'time' if out_of_time else 'tokens' if out_of_tokens else 'budget'}" if refused else ""))
        result.seconds = beat_steps[beat.number]["ms"] // 1000
        if refused:
            spent = (f"its time for tool calls ({int(soft_seconds if soft_seconds is not None else SOFT_TIME_SHARE * seconds)} seconds) was used up" if out_of_time
                     else f"its tokens for tool calls ({cap}) were used up" if out_of_tokens else f"its budget of {calls if focused else st.investigate_max_calls} was used up")
            note(f"{who}the investigator asked for {refused} more tool call{'' if refused == 1 else 's'} after {spent}, and was refused")
        flush_notes()
        try:
            raw_findings, examined = parse_answer(answer.text)
        except RoleError as error:
            if harness is not None:
                harness.guard_failed(spec_i.name, "unreadable")
            result.end = "failed"
            result.note = last_note = f"the investigator gave no answer that could be read ({clean_text(error, 200)})"
            close(result, False, at, log_before)
            if focused:
                note(f"{who}{result.note}; the other beats go on")
            continue
        out.ran = True
        out.examined += examined
        raw_total += len(raw_findings)
        result.end, result.examined, result.found = activity.end_of_run(False, answer, True), examined, min(len(raw_findings), agents.MAX_FINDINGS)
        result.salvaged = bool(getattr(answer, "salvaged", False))
        if result.salvaged:
            note(f"{who}the investigator was cut off by its {result.end if result.end in ('time', 'tokens', 'calls') else 'limit'} and gave its answer when it was asked once more")
        if len(raw_findings) > agents.MAX_FINDINGS:
            note(f"{who}the investigator gave {len(raw_findings)} findings; the first {agents.MAX_FINDINGS} were taken")

        # 2. Code checks the findings against what the tools showed.
        for raw in raw_findings[: agents.MAX_FINDINGS]:
            finding, handles, entries = parse_finding(len(findings) + 1, raw)
            finding.beat = beat.number
            if finding.reason is None:
                _verify(finding, handles, entries, toolbox, taken, holders)
                _hold_delete(finding, toolbox)
                if finding.unknown and harness is not None:
                    harness.guard_failed(spec_i.name, "unknown-handle")  # an answer that cites a handle that no tool returned is a failure of the run, and a third failure trips the brake
                if finding.reason is None:
                    result.lines.append({"basis": finding.basis, "proposal": finding.proposal, "handles": finding.handles[: beats.CARRY_ITEMS]})
            findings.append(finding)
        close(result, True, at, log_before)
    if not out.ran:
        out.note = last_note  # no beat gave an answer that code could read
        finished(False, note=out.note)
        return out
    out.examined = out.examined[:EXAMINED_KEPT]

    # 2. Then the recheck and the guards hold every resource of the findings of all the beats.
    locks: dict[str, list[str] | None] = {}
    room = MAX_CASES
    held: dict[str, int] = {}
    open_questions = learning.OpenQuestions(s.extras.store, s.clock()) if s.extras is not None else None  # read once, when the first old case is looked at
    groups = _groups_lately(s)
    for finding in findings:
        if finding.reason is not None:
            continue
        costs = {handle: _cost(toolbox.handles[handle], contexts.get(toolbox.handles[handle].subscription_id.lower())) for handle in finding.handles}
        states = {handle: _cost_state(toolbox.handles[handle], contexts.get(toolbox.handles[handle].subscription_id.lower()), costs[handle]) for handle in finding.handles}
        blocked = {h: "currency" for h, state in states.items() if state == cost_words.CURRENCY}
        finding.priced = pricing.price(finding.change, finding.handles, toolbox, costs, blocked, meter_word)
        finding.ways = proposals.check(finding.change, finding.proposal, finding.handles, toolbox.evidence,
                                       lambda option: pricing.price(option, finding.handles, toolbox, costs, blocked, meter_word))
        for handle in sorted(finding.handles, key=lambda handle: -(costs[handle] or 0.0)):
            resource = toolbox.handles[handle]
            facts = _facts(finding, finding.cited[handle], costs[handle], _aggregates(toolbox.evidence, handle), len(finding.listed[handle]) if handle in finding.listed else None)
            advisor, state = _advisor(toolbox.evidence, handle), states[handle]
            stated = pricing.digest(finding.change, finding.priced, handle, advisor)
            if stated is not None:
                facts[pricing.KEY] = stated  # the change that the finding states, with the figure that code computed from the bill lines or the word that says why there is none
            if handle in finding.ways.ways:
                facts[proposals.KEY] = finding.ways.ways[handle]  # the settings and the other ways that code kept for this resource
            lead = _lead(resource, facts, costs[handle], advisor, state, _estimate(toolbox, resource, state))
            finding.seen.add(lead.lead_id)
            old = _earlier(s, lead)
            if old is not None and old.status == "expired" and any(lead.lead_id in _members_of(group) and group.case_id != old.case_id and _recent(s, group, None) for group in groups):
                old = None  # its request was closed (or nobody answered) and a group stands for it: it goes back into the group
            if _recent(s, old, facts, open_questions):
                finding.recent += 1
                if finding.proposal == "investigate" and _stands_for_a_group(old):
                    finding.stood.append(old)  # the case of a group, judged lately: the question to a person is open or was answered. Whether it stands for this finding is settled below
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
                    finding.items.append(Item(handle, lead, finding.cited[handle], earlier=old))
                    room -= 1
        if finding.proposal == "investigate":
            for old in groups:
                if _members_of(old) & finding.seen and old.case_id[1:] not in finding.seen and all(old.case_id != known.case_id for known in finding.stood) and _recent(s, old, None, open_questions):
                    finding.stood.append(old)  # a group that stands for resources of this finding although the resource that it belongs to is not one of them
        room += _settle(finding, marked)
        if (st.case_min_usd > 0 and finding.items and all(states[item.handle] == cost_words.LINES and item.lead.cost_usd_30d is not None for item in finding.items)
                and sum(item.lead.cost_usd_30d for item in finding.items) < st.case_min_usd):  # type: ignore[misc]
            # A finding whose resources that are left together cost less than the floor is too small to ask a person for: no case, and a count. A resource of which the cost is not known, or none, makes the
            # finding not small, and a finding at the floor or over it keeps every resource however small it is alone (twenty small things that are idle are 73 dollars, which is not small).
            room += len(finding.items)
            finding.small += len(finding.items)
            finding.items = []
        known = [i.lead.cost_usd_30d for i in finding.items if i.lead.cost_usd_30d is not None]
        finding.covered_usd = round(sum(known), 2) if known else None
        if not finding.items:
            parts = [f"{n} {what}" for n, what in ((finding.guarded, "held back by a guard"), (finding.recent, "judged lately"), (finding.small, "too small to open a case"),
                                                  (finding.capped, "beyond the cap of cases for one run")) if n]
            finding.reason = "no resource of it is left: " + ", ".join(parts)
    survivors = [f for f in findings if f.reason is None]

    # 3. The Skeptic tries to break the findings that are left. It is shown every resource that will be a case, as far as its input allows: the findings that do not fit in one input go to it in as many calls
    # as they take (SKEPTIC_CALLS at most, inside the time that is left), each with the richest rows that fit, and a finding that gets no call is left to a person.
    skeptic_steps: dict[int, dict] = {}  # the step of the Skeptic's run that had a finding, by the number of the finding
    unjudged = hidden = 0  # the findings that got no verdict, and the resources that the Skeptic was not shown
    if survivors:
        batches = _batches(survivors, toolbox)
        for position, (group_, skeptic_text, shown_handles) in enumerate(batches):
            started = s.monotonic()
            left = deadline - started
            if position >= SKEPTIC_CALLS or left <= 1.0:
                no_call = step("skeptic", st.foundry_model_skeptic, started, False, None, "no time was left for the Skeptic" if left <= 1.0 else "no call of the Skeptic was left for this finding")
                skeptic_steps.update({finding.number: no_call for finding in group_})
                continue
            if position and harness is not None:
                harness.again(spec_s)  # each call of the Skeptic is a run of its own
            tokens: tuple[int, int] | None = None
            batch_hidden = 0
            try:
                for finding in group_:
                    for item in finding.items:
                        item.shown = item.handle in shown_handles
                batch_hidden = sum(1 for finding in group_ for item in finding.items if not item.shown)
                if harness is None:
                    judged = s.foundry.run(skeptic_ref, skeptic_text, None, max_calls=0, max_seconds=left)
                else:
                    judged = harness.run(skeptic_ref, spec_s, skeptic_text, None, max_calls=0, max_seconds=left)
                tokens = (judged.input_tokens, judged.output_tokens)
                out.tokens += judged.input_tokens + judged.output_tokens
                try:
                    verdicts = parse_verdicts(judged.text, len(group_))
                except RoleError:
                    if harness is not None:
                        harness.guard_failed(spec_s.name, "unreadable")
                    raise
                for index, verdict in verdicts.items():
                    group_[index].verdict = verdict
                unjudged += len(group_) - len(verdicts)
                hidden += batch_hidden
                made_step = step("skeptic", st.foundry_model_skeptic, started, True, tokens, None)
            except (FoundryError, RoleError) as error:
                partial = getattr(error, "partial", None)
                if tokens is None and partial is not None:
                    tokens = (partial.input_tokens, partial.output_tokens)
                    out.tokens += partial.input_tokens + partial.output_tokens
                made_step = step("skeptic", st.foundry_model_skeptic, started, False, tokens, _why(s, error))
                _own_words(note, error)  # the run did not judge anything, and its note says why
                if isinstance(error, HarnessRefused):
                    # The harness stopped the Skeptic after the Investigator had run (a switch pulled or a brake tripped in between): the investigation is held like one that was refused at the
                    # start, so that no case is opened from findings that nobody judged, and only the planted waste goes on (cases/run.py).
                    out.ran, out.held = False, True
                    out.note = f"the Skeptic was not let run ({_why(s, error)}), so no case was opened from this investigation"
                    flush_notes()
                    finished(False, note=out.note)
                    return out
            skeptic_steps.update({finding.number: made_step for finding in group_})
            flush_notes()
        failed_steps = [made for made in skeptic_steps.values() if not made["ok"]]
        if failed_steps or unjudged:
            reason = failed_steps[0]["note"] if failed_steps else f"no verdict for {unjudged} of {len(survivors)} findings"
            note(f"the Skeptic could not judge every finding ({reason}); a finding without a verdict needs a person")
        if hidden:
            note(f"{hidden} resource{'' if hidden == 1 else 's'} of the findings {'was' if hidden == 1 else 'were'} not shown to the Skeptic, whose input is limited to "
                 f"{SKEPTIC_CHARS} characters, so a person has to judge {'it' if hidden == 1 else 'them'}")

    # 4. One line for each finding, then one case for each resource that is left.
    for finding in findings:
        saved = [point for item in finding.items if (point := pricing.point(item.lead.facts, item.lead.cost_usd_30d)) is not None]
        h.emit("investigation.finding", finding=finding.number, basis=finding.basis or None, proposal=finding.proposal or None, confidence=finding.confidence,
               claimed=finding.claimed, handles=len(finding.items), unknown=finding.unknown, unproven=finding.unproven, repeated=finding.repeated,
               noEntry=finding.no_entry, totalDiffers=finding.total_differs, diffNone=finding.differs["none"], diffNear=finding.differs["near"], diffStat=finding.differs["stat"],
               diffZero=finding.differs["zero"], diffFar=finding.differs["far"], metricUnknown=finding.metric_unknown, notMeasured=finding.not_measured, showsUse=finding.shows_use,
               tooBrief=finding.too_brief,
               judgedLately=finding.recent, guarded=finding.guarded, capped=finding.capped, tooSmall=finding.small, unmeasured=sum(1 for item in finding.items if not item.metrics),
               shown=sum(1 for item in finding.items if item.shown), coveredCostUsd30d=finding.covered_usd, change=finding.change.action if finding.change else None,
               pricedHandles=len(saved), savingUsdMonth=_figure(sum(saved)) if saved else None,
               verdict=finding.verdict.verdict if finding.verdict else None, kept=finding.reason is None, reason=finding.reason, note=finding.note, summary=finding.summary,
               **({"beat": finding.beat} if focused else {}))
    models = {"investigator": st.foundry_model_investigator, "skeptic": st.foundry_model_skeptic}
    out.impact_due = _impact_due(survivors)
    number = 0
    for finding in survivors:
        group = _group_of(finding)
        for item in (group[:1] if group else finding.items):
            number += 1
            steps = tuple(x for x in (beat_steps.get(finding.beat), _skeptic_step_of(skeptic_steps.get(finding.number), finding, item)) if x is not None)
            _open_case(s, out, finding, item, models, steps, f"{h.run_id[:8]}-i{number}", **({"group": group} if group else {}))
        if group:
            left_out = f"; {finding.silenced} more that a person marked do-not-touch {'is' if finding.silenced == 1 else 'are'} left out" if finding.silenced else ""
            note(f"finding {finding.number}: its {len(group)} resources are one case and one question to a person, which belong to the dearest of them{left_out}")
    out.kept = len(survivors)
    out.dropped_findings = raw_total - len(survivors)
    if out.guarded:
        note(f"the investigation held back {out.guarded} resource{'' if out.guarded == 1 else 's'} with a guard: " + ", ".join(f"{n} {name}" for name, n in sorted(held.items())))
    capped = sum(f.capped for f in findings)
    small, small_findings = sum(f.small for f in findings), sum(1 for f in findings if f.small)
    if small:
        note(f"{small_findings} finding{'' if small_findings == 1 else 's'} whose resources together cost less than the floor of the setting CASE_MIN_USD open{'s' if small_findings == 1 else ''} no case "
             f"({small} resource{'' if small == 1 else 's'} in all)")
    if capped:
        note(f"{capped} resource{'' if capped == 1 else 's'} of the findings {'is' if capped == 1 else 'are'} not listed as cases: a run opens at most {MAX_CASES}")
    for finding in survivors:
        if finding.note:
            note(f"finding {finding.number}: {finding.note}")
        if finding.ways is not None and (told := proposals.note_of(finding.ways)):
            note(f"finding {finding.number}: {told}")
    if out.unmeasured:
        note(f"{out.unmeasured} resource{'' if out.unmeasured == 1 else 's'} of the findings {'has' if out.unmeasured == 1 else 'have'} no measurement that backs the "
             f"finding, so a person has to judge {'it' if out.unmeasured == 1 else 'them'}")
    finished(True, examined=out.examined, findingsKept=out.kept, findingsDropped=out.dropped_findings, cases=out.cases, guarded=out.guarded)
    note(f"the investigation made {out.tool_calls} tool call{'' if out.tool_calls == 1 else 's'}, kept {out.kept} of {raw_total} finding"
         f"{'' if raw_total == 1 else 's'} and opened {out.cases} case{'' if out.cases == 1 else 's'}")
    for why, words in NOT_ASKED.items():  # one sentence for each reason, so that none is cut: a note keeps 300 characters
        if (count := out.not_asked.get(why)):
            note(f"no request was made for {count} case{'' if count == 1 else 's'} because {words.format(their='its' if count == 1 else 'their')}")
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


def _own_ids(s: "Services") -> set[str]:
    """The identities of Meternaut itself: the app's own and the two of the sign-in of the approvers. A write by one of them is not an automation of somebody else."""
    ex, settings = getattr(s, "extras", None), getattr(s, "settings", None)
    return {text.lower() for text in (getattr(settings, "client_id", ""), getattr(getattr(ex, "settings", None), "signin_client_id", ""),
                                      getattr(getattr(ex, "settings", None), "signin_assertion_client_id", "")) if text}


def _owner_of(s: "Services", out: Investigation, lead: Lead) -> dict:
    """What the brief says about whose a resource is: a tag that conventionally names an owner, and who made and last changed it (ownership.py), and when an application or service identity last
    wrote to it (`automatedAt`, from every write of the Activity Log and not only the newest: a person's edit yesterday does not hide an automation's write three days ago; cases/brief.py
    automation_note warns on it). It is shown to people and never goes to a model. A word that says why a read gave nothing (not visible, not in the window) is not a person: it is
    left out, so that the page says only what it knows."""
    reader = out.owners
    writes = None
    try:
        if reader is None:
            reader = out.owners = OwnerReader(s.arm, s.clock())
        hint = reader.hints(lead.resource_id, lead.tags)
        writes = reader.writes(lead.resource_id)
        # A read that was refused, that failed or that was not made (the reads of the run were used up) answers nothing: the page must then say that the lookup was not made, and not that
        # the resource has no owner.
        looked_up = hint.get("lastChangedBy") not in (UNAVAILABLE, NOT_VISIBLE)
    except Exception as error:  # noqa: BLE001 (the owner line is a convenience: a lookup that fails never costs a case)
        LOG.warning("investigate: the owner of a resource could not be looked up (%s)", type(error).__name__)
        hint, looked_up = owner_hints(lead.tags, None, False, lead.resource_id, UNAVAILABLE), False
    sentinels = {NOT_COMPLETE, NOT_IN_WINDOW, NOT_VISIBLE, UNAVAILABLE}

    def real(value: object) -> str:
        return value if isinstance(value, str) and value not in sentinels else ""

    own = _own_ids(s)
    automated = max((when for when, caller in writes or [] if "@" not in caller and caller.lower() not in own), default=None)
    tags = hint.get("tags") if isinstance(hint.get("tags"), dict) else {}
    name = next((tag for tag in ("owner", "contact", "team", "manager", "createdby") if tags.get(tag)), "")
    return {"tagOwner": tags.get(name, ""), "tagName": name, "createdBy": real(hint.get("createdBy")), "createdAt": real(hint.get("createdAt")),
            "changedBy": real(hint.get("lastChangedBy")), "changedAt": real(hint.get("lastChangedAt")), "lookedUp": looked_up, "automatedAt": stamp(automated) if automated else ""}


def _impact_of(s: "Services", out: Investigation, lead: Lead) -> dict | None:
    """The digest of the impact check of one resource (cases/impact.py), made with the reads of the run: one reader and one budget for all its cases. It is made for a resource whose type has a
    check that this run has room for (`_impact_due`), at most MAX_IMPACTS times in a run, and it reads with the reader identity of the app and nothing else (the module says whose rights). Its
    notes go to the notes of the run."""
    if out.impacts >= MAX_IMPACTS or (out.impact_due is not None and lead.lead_id not in out.impact_due):
        return None
    out.impacts += 1
    if out.impact_reader is None:
        out.impact_reader = impact.Reader(s.arm, s.settings.subscriptions, s.clock(), owners=out.owners, own=_own_ids(s))
    found = impact.analyse(out.impact_reader, lead.resource_id, lead.resource_type)
    for text in out.impact_reader.notes:
        s.history.emit("run.note", note=clean_text(s.redact(text), 300))
    out.impact_reader.notes.clear()
    return found


def _kept_impact(old: CaseRecord | None) -> dict | None:
    """The digest that the earlier case of a resource kept, for a case that this run did not check again: it says when it was read, and a page shows that date."""
    found = old.facts.get(impact.KEY) if old is not None and isinstance(old.facts, dict) else None
    return found if isinstance(found, dict) and found.get("verdict") in IMPACT_VERDICTS else None


def _impact_due(survivors: list[Finding]) -> set[str]:
    """The resources whose impact this run checks, at most MAX_IMPACTS: of the cases that ask for a check, those with no digest first and then the oldest digest, so that nothing is starved (the
    order of the findings decides between equals). The others keep their earlier digest (`_kept_impact`)."""
    asking = [item for finding in survivors if finding.proposal != "keep" and not _group_of(finding)
              for item in finding.items if impact.has_check(item.lead.resource_type) and about_use(item.lead.facts, finding.proposal)]

    def read(item: Item) -> str:
        found = _kept_impact(item.earlier)
        return str(found.get("readAt") or "") if found is not None else ""

    return {item.lead.lead_id for item in sorted(asking, key=read)[:MAX_IMPACTS]}


def _group_of(finding: Finding) -> list[Item] | None:
    """The resources of a finding that is one case, with the one that the case belongs to first, or None when each resource of the finding is a case.

    Only a finding that asks for a look (investigate) is one case, and only when it has more than GROUP_MIN resources left after the checks of code, not counting those that a person marked
    do-not-touch (_settle leaves those out of a finding that is one case): a delete and a change need a decision for each resource, and a handful of requests can each be read. The case belongs to
    the resource that an earlier Watch made it for, when that case stands for most of these resources (so that a Watch that finds the same group again does not make another case and another
    request when the costs have moved), or else to the dearest resource, and the first of them when the cost is the same."""
    if finding.proposal != "investigate" or sum(1 for item in finding.items if not item.marked) <= GROUP_MIN:
        return None
    ids = {item.lead.lead_id for item in finding.items}
    stands = (item for item in finding.items if _stands_for_a_group(item.earlier) and _alike(ids, _members_of(item.earlier)))
    first = next(stands, finding.items[0])  # the items are in the order of their cost, the dearest first
    return [first] + [item for item in finding.items if item is not first]


def _together(members: list[Item], capped: int = 0, silenced: int = 0) -> dict:
    """What the case of a group keeps of it, as typed numbers and cleaned names (cases/brief.py shows it): how many resources, what they cost together (None when no cost line was read for any
    of them), their type ("other" when they differ), in how many resource groups they are, the names of the first of the others, how many more of the finding the cap of cases left out, how
    many a person marked do-not-touch, the short ids of the resources that it stands for (a later Watch compares a finding with them: _settle) and their lower-case resource ids, at most
    MAX_GROUP_IDS (the daily cost of the group is the sum of theirs: run.read_cost_series). The names are text of the estate: cut
    and cleaned here, and cleaned again where they are shown."""
    leads = [member.lead for member in members]
    known = [lead.cost_usd_30d for lead in leads if lead.cost_usd_30d is not None]
    types = {(lead.resource_type or "").lower() for lead in leads}
    kind = next(iter(types)) if len(types) == 1 else "other"
    names = [clean_text(lead.name, 60) for lead in leads[1 : 1 + MAX_GROUP_NAMES]]
    return {"count": len(leads), "costUsd30d": _figure(sum(known)) if known else None, "type": kind if len(kind) <= 120 and RESOURCE_TYPE.fullmatch(kind) else "other",
            "groups": len({(lead.subscription_id.lower(), (lead.resource_group or "").lower()) for lead in leads}), "names": [name for name in names if name],
            "capped": capped, "silenced": silenced, "members": sorted(lead.lead_id for lead in leads),
            "resourceIds": sorted(lead.resource_id.lower() for lead in leads)[:MAX_GROUP_IDS]}


def _together_state(members: list[Item], cost: float | None) -> str:
    """How the cost of a group was read (cases/costs.py): lines when the lines of its resources add up to something, none when they were read for every one of them and none has a line, failed or
    currency when that is why a resource of it has no figure and the rest add up to nothing, and "" when nothing says."""
    if cost is None:
        return ""
    if cost > 0:
        return cost_words.LINES
    states = {member.lead.cost_state for member in members}
    if states == {cost_words.NONE}:
        return cost_words.NONE
    return next((word for word in (cost_words.FAILED, cost_words.CURRENCY) if word in states), "")


def _open_case(s: "Services", out: Investigation, finding: Finding, item: Item, models: dict, steps: tuple[dict, ...], case_id: str, group: list[Item] | None = None) -> None:
    """The case of one resource: decide.py gives it its status, the History gets its result, and the store keeps it when there is a store. The verdict of the Skeptic
    counts only for a resource that it was shown, and the case is never proposed without a measurement that code confirmed.

    The case of a group (`group`: its resources, `item` the one that the case belongs to) is judged as that resource is, with the verdict of the finding, and is the case of that resource in
    the store: its cost is what all of them cost, its facts say how many they are, and the History has the one line, with the size of the group. The resources of the group that no
    measurement backs are counted one by one."""
    h = s.history
    lead = item.lead
    if group:
        together = _together(group, finding.capped, finding.silenced)
        kept = {k: v for k, v in lead.facts.items() if k not in (pricing.KEY, proposals.KEY)}  # the figure and the proposals of one resource are not those of the group
        combined = pricing.combine([member.lead.facts.get(pricing.KEY) for member in group], len(group))
        kept.update({pricing.KEY: combined} if combined is not None else {})  # the digest of the group is made from the digests of its resources
        lead = replace(lead, cost_usd_30d=together["costUsd30d"], cost_state=_together_state(group, together["costUsd30d"]), estimate={},
                       facts={**kept, "costUsd30d": together["costUsd30d"], GROUP_FACT: together})
    detective = DetectiveAnswer(finding.proposal, finding.confidence, finding.summary)
    judged = finding.verdict if item.shown else None
    outcome = decide.decide(lead, Guards({}), detective, judged, backed=bool(item.metrics), notes=(finding.note,) if finding.note else ())
    # What past requests like this showed may hold a proposal back for a person, and never makes a finding stronger (cases/learning.py). It does so only when LEARNING_HOLD is on: the first run of
    # tools/learning-check.py missed its thresholds (docs/proposals/15-learning.md). The case is always an advise plan's: no change is made for it.
    store = s.extras.store if s.extras is not None and s.settings.learning_hold else None
    outcome, held = learning.hold(store, learning.type_word(lead.resource_type), ADVISE, detective.confidence, outcome)
    learned = {"skeptic": judged.verdict if judged is not None else "none", **({"held": "history"} if held else {})}
    access = capability.access_code(out.profile, finding.basis)
    if access:
        learned["access"] = access  # what the identity cannot see of the commitments, as the one sentence that the brief of a finding about a commitment carries
    out.unmeasured += sum(1 for member in (group or [item]) if not member.metrics)
    h.emit("case.result", caseId=case_id, leadId=lead.lead_id, detector=DETECTOR, resourceName=clean_text(lead.name, 120), resourceType=clean_text(lead.resource_type, 120),
           resourceGroup=clean_text(lead.resource_group, 90), costUsd30d=lead.cost_usd_30d, status=outcome.status, recommendation=outcome.recommendation,
           confidence=outcome.confidence, monthlySavingUsd=_figure(outcome.monthly_saving_usd), summary=outcome.summary, objections=list(outcome.objections),
           guards=outcome.guards, **({"groupSize": len(group)} if group else {}))
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
    lead = replace(lead, subscription_name=_subscription_name(s, lead.subscription_id))
    now = stamp(s.clock())
    try:
        old = ex.store.case_get(f"k{lead.lead_id}")
        past = old.learned.get("past") if old is not None and isinstance(old.learned, dict) else None
        if past and "past" not in learned:
            learned["past"] = past  # a case judged again while its request is still open keeps the line of the past that the request was made with (no second request writes it)
        owner = _owner_of(s, out, lead) if outcome.status in ("proposed", "needs_human") else {}  # a case that is dropped is never shown to anybody: it takes no lookup of the Activity Log, whose reads are few
        # The impact of a resource that is proposed for removal: a fresh check when this run has room (_impact_due), else the digest of the earlier case, with its own date.
        checked = outcome.status in ("proposed", "needs_human") and not group and impact.has_check(lead.resource_type) and about_use(lead.facts, outcome.recommendation)
        found = (_impact_of(s, out, lead) or _kept_impact(old)) if checked else None
        if found is not None:
            lead = replace(lead, facts={**lead.facts, impact.KEY: found})
        saving = _figure(outcome.monthly_saving_usd)
        if not saving and outcome.status != "dropped" and (asked := ex.approvals.asked_saving(old)):
            saving = asked  # judged again with no price while a request that was asked with one is open: the case keeps what the person was shown, the figure and the price (its level and basis)
            if pricing.saved(old.facts) is not None:
                lead = replace(lead, facts={**lead.facts, pricing.KEY: old.facts[pricing.KEY], **({proposals.KEY: old.facts[proposals.KEY]} if proposals.KEY in old.facts and proposals.KEY not in lead.facts and not group else {})})
        record = CaseRecord(
            case_id=f"k{lead.lead_id}", resource_id=lead.resource_id, resource_name=clean_text(lead.name, 120), resource_type=clean_text(lead.resource_type, 120),
            resource_group=clean_text(lead.resource_group, 90), subscription_id=lead.subscription_id, detector=DETECTOR, run_id=h.run_id, status=outcome.status,
            recommendation=outcome.recommendation, confidence=outcome.confidence, saving_usd_month=saving,
            summary=clean_text(outcome.summary, 600), objections=tuple(clean_text(o, 300) for o in outcome.objections), guards=tuple(outcome.guards),
            models=dict(models), steps=steps, facts=lead.facts, first_seen_at=old.first_seen_at if old and old.first_seen_at else now, updated_at=now,
            runs_seen=(old.runs_seen + 1) if old else 1, owner=owner, learned=learned,
            subscription_name=lead.subscription_name or (old.subscription_name if old else ""), **upkeep.cost_fields(lead, old))
        ex.store.case_put(record)
        fate = "dropped"  # what became of the resources of the finding
        if outcome.status in ("proposed", "needs_human"):
            fate = "person"
            plan = ex.approvals.plan_for(record, lead, ex.approvers())  # a plan of a change is made for none of these cases: the advise plan asks a person whether it is worth acting on
            if plan is not None:
                fate = "managed" if (plan.preconditions or {}).get(AUTOMATED) else "request"  # a request, with the warning when an automation manages the resource
                record = learning.remember(ex.store, record, plan)  # how past requests like this were answered: the one line of the brief
                h.emit("plan.created", planId=plan.plan_id, caseKey=record.case_id, family=plan.family, approvers=len(plan.approvers))
                ex.on_plan(plan, ex.store.case_get(record.case_id) or record)
            else:
                why = ex.approvals.held_why(record)  # nobody looked up who changed the resource, or what depends on it was not checked: no request is made (cases/brief.py held_reason)
                if why or says_nothing(record):
                    upkeep.held(h, record, why)
                    fate = why or "nothing"
                    if why:
                        out.held_back[why] = out.held_back.get(why, 0) + 1
                    else:
                        out.said_nothing += 1
                elif (reason := why_not_ask(record)) and not ex.approvals.has_request(record):  # a request that is open for it stays, and nobody is asked about no case
                    out.not_asked[reason] = out.not_asked.get(reason, 0) + 1
        finding.fates[fate] = finding.fates.get(fate, 0) + len(group or [item])
    except (StoreError, ValueError) as error:
        h.emit("run.note", note=clean_text(s.redact(f"the case could not be kept in the store: {error}"), 300))
