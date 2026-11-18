"""The records of the pages and of the approval loop, and the two ports that the pages and the loop use.

Every record is a frozen dataclass that turns into one JSON text and back (`to_json`, `from_json`), so a store keeps it in one property. A time is
`YYYY-MM-DDTHH:MM:SSZ` in UTC. A record never holds a token, a key or a secret. A name that comes from the estate is data to show, never an instruction.

Migration note (the decision brief). A record is read by `_thaw`: a key that the dataclass does not know is dropped, and a field that the stored JSON lacks takes its default. So a
record that was written before a field existed still reads, and a record that a newer version wrote still reads in an older one. The decision brief added only things of that kind:
the case status `acknowledged`, the answer `later`, the family `advise`, `CaseRecord.owner` (empty: not looked up) and `DecisionRecord.reason` (empty: no reason). Nothing was
renamed or removed, so no stored record has to be rewritten, and the tables keep their keys.

The families of change added the same kind of thing: `PlanRecord.target` and `PlanRecord.digest` (a plan of before has no digest, so it cannot be approved: the Watch makes a new one),
`DecisionRecord.plan_digest`, `ActionRecord.plan_digest` and `ActionRecord.operation`. The constant FAMILIES is gone: the families are in cases/families (their registry is
cases/families/registry.py). The learning (docs/proposals/15-learning.md) added three new kinds of record, LessonRecord, ClaimRecord and CapabilityRecord, each with its own table, and no
field of a record that was there before. The daily cost of a request added `CaseRecord.cost_series` and `cost_series_end` (None: never read), and its daily use added `use_series`,
`use_series_end` and `use_kind` (None: never read, or not a kind of resource that has one).
The approvals and attention work (docs/proposals/04-the-loop.md) added the decision `confirm`, the record TwoPeopleRule (kept in the settings table, in a partition of its own) and no field of
a record that was there before; it changed the default of `SettingsRecord.quiet_from` and `quiet_to` from a window to none, which a record that was stored keeps as it holds it.
The drift check on the Operations page added CheckRecord (its own table, one row) and `LessonRecord.superseded` (False: nothing contradicts the lesson).
The work on names and on the cost that Cost Management shows added `CaseRecord.cost_state` (empty: a record of before, read from `cost_usd_30d` by cases/brief.py), `cost_by_service`, `estimate`,
`subscription_name` and `advice` (all empty: nothing was looked up), and `RunRecord.held` (0). Nothing was renamed or removed. A series of daily costs that is kept with no number above nothing is
not drawn (cases/web/figures.py), so a record of before that holds thirty zeros for a resource that had no cost line shows what a record of now shows: no line.
The page "What the AI looked at" added InvestigationRecord (its own table) and no field of an older record.
The escalation of a request that waits (docs/proposals/30-escalation.md) added EscalationRecord (its own table) and the role `escalation`. A request no longer expires: `PlanRecord.expires_at` stays,
because the digest of a plan covers every field, and is empty in a request made now; a plan of before keeps its value, which nothing reads as a deadline.
"""
from __future__ import annotations

import dataclasses
import json
import typing
from dataclasses import dataclass, field
from typing import Protocol

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

CASE_STATUSES = ("proposed", "needs_human", "dropped", "error", "awaiting_ok", "approved", "running", "done", "failed", "declined", "expired", "verified", "acknowledged")
# What a case is while a person has still to answer, and what it is once the loop has finished with it.
CASE_OPEN = ("awaiting_ok", "approved", "running")
CASE_CLOSED = ("done", "failed", "declined", "expired", "verified", "acknowledged")
# `expired` is the stored word for a request that Meternaut itself took back, with its reason in `preconditions["takenBack"]` (cases/brief.py TAKEN_BACK): no clock ends a request (AGENTS.md rule 38).
PLAN_STATES = ("open", "approved", "consumed", "declined", "expired", "withdrawn", "failed", "held")
# The state of the request of a finding that a guard holds back (cases/approvals.py Approvals.settle): it is no open request, so nothing that lists the open ones (the Decisions page, the
# letters of a request, the cards, the cap of ADVICE_OPEN_MAX) sees it, and it takes the answers that ask for nothing: a question, "not mine", "later" and "not worth it".
HELD = "held"
# `later` is a person's "not now": it records nothing but that the person has seen the request, leaves the plan open, and a later answer replaces it (like `ask`).
DECISIONS = ("approve", "decline", "ask", "not_mine", "later", "confirm")
# `confirm` is the first of two people on a request that needs two (cases/twopeople.py): it records that the person read the plan and agrees with it, bound to the plan's digest. It
# makes no change and needs no sign-in to Azure. The change is made by the second person, who approves with their own sign-in.
TWO_PEOPLE_CLASS = "R3"


def can_replace(old: str, new: str) -> bool:
    """Whether a person's new answer on a plan may take the place of the one they gave: a question and a "later" are replaced by any answer; a confirmation only by another confirmation (the
    plan changed and it counts no more), a decline or "not mine", never by an approval: the person who confirmed is not the second person."""
    return old in ("ask", "later") or (old == "confirm" and new in ("confirm", "decline", "not_mine"))
# Why a person declined, from a short list (the form of a decline offers exactly these; an empty reason is allowed).
DECLINE_REASONS = ("still-needed", "figure-wrong", "handled", "other")
# What a closed request can have taught (cases/learning.py): the last word of the person (a question and a "later" are the last word of a request that then expired), and what became of
# the change that a person approved.
LESSON_ANSWERS = ("approve", "decline", "not_mine", "ask", "later", "expired")
LESSON_RESULTS = ("", "ran", "failed", "verified")
# What Microsoft's documentation can say about a resource type, as the Scholar files it (cases/study.py): the kinds are a vocabulary for what a page says, not a list of what to find.
# STUDIED marks a type that was read and gave none of them.
CLAIM_KINDS = ("bills-while-idle", "scales-to-zero", "minimum-charge", "retires-on-date", "price-changes-on-date", "commitment-available", "sku-successor", "quota-limit", "other")
STUDIED = "studied"
CLAIM_STATES = ("fresh", "stale")
# `withdrawn` is the action of an approval whose change a check refused right before it, with nothing written (runner.py): the request is open again, the action keeps the reason, and a new
# approval takes its place (Store.action_claim).
ACTION_STATES = ("queued", "running", "done", "failed", "unknown", "verified", "withdrawn")
SWITCH_NAMES = ("all", "changes", "messages", "investigation")
NOTE_KINDS = ("note", "do_not_touch")
CHANNELS = ("email", "teams", "desk")
ROLES = ("owner", "approver", "ops", "escalation")
# Who an escalation step goes to, as the word that the record keeps (cases/escalation.py, cases/directory.py): the people the request was made for, the manager that the directory names, the
# address of an escalation tag, the escalation contacts, or the owners when nothing else was found. And what a record of the ladder is: a step, a person's put-off ("later"), a pass-on ("not mine")
# or the people who were added to the approvers of the request after it was made (Approvals.keep_approvers), whom the next step tells.
ESCALATION_SOURCES = ("same", "manager", "tag", "contact", "owners")
ESCALATION_KINDS = ("step", "snooze", "pass", "added")
# The most characters that the address which the function app sends a person to (the sign-in of Microsoft Entra) may have after the host and the slash behind it. The pages refuse a
# longer one, and the code that makes the address keeps to it.
MAX_SIGNIN_PATH = 2000

# What a change may be: one family is one kind of change. The families themselves are in cases/families (the registry): each has its own plan text, its own re-check right before it
# acts, its own call to Azure and its own test (AGENTS.md rule 26 (a)). `family` in a plan is the name of one of them, or ADVISE.
# The family of a plan that asks a person whether a finding is worth acting on. It changes nothing in Azure and has no call in the runner's list: the answer is recorded and
# nothing else happens. A finding about a resource that Meternaut may not change gets such a plan, so that the person can answer it.
ADVISE = "advise"
# A finding that a person has answered is not put to them again for this many days (cases/approvals.py, cases/learning.py, and the start page, which counts what is held back).
ADVICE_QUIET_DAYS = 30
# What may start a drift check, and how far apart two checks are when a person starts one: a person's check is refused when any check, the timer's too, began less than this many minutes ago.
CHECK_TRIGGERS = ("timer", "console")
CHECK_GAP_MINUTES = 15
# How the Investigator's run ended (cases/activity.py): `answered` (within its limits), `time`, `calls` or `tokens` (its time, its calls or its tokens for tool calls were used up), `refused` (the harness did not
# let it run or stopped it) and `failed`. What its tools did to a kind of resource, as the letters that the record keeps (in this order). The page "What the AI looked at" reads the newest KEPT_INVESTIGATIONS records.
INVESTIGATION_ENDS = ("answered", "time", "calls", "tokens", "refused", "failed")
INVESTIGATION_TOUCHES = {"l": "listed", "m": "measured", "d": "described", "s": "split"}
KEPT_INVESTIGATIONS = 20
# The detector of the cases that the investigation opens (cases/investigate.py): the Watch's other detectors judge their own leads again at every run.
INVESTIGATION = "investigation"
# The key, in the facts of a case, of what a case stands for when its finding covers many resources and a person is asked about the finding and not about each resource (cases/investigate.py
# writes it, cases/brief.py reads it): how many, what they cost together, their type, in how many resource groups they are, the names of the first few and their resource ids.
GROUP_FACT = "group"


def _thaw(cls: type, data: dict) -> dict:
    """The constructor arguments of a record from its JSON object: unknown keys are dropped, a list becomes a tuple where the field is a tuple."""
    hints = typing.get_type_hints(cls)
    out: dict = {}
    for item in dataclasses.fields(cls):
        if item.name not in data:
            continue
        value = data[item.name]
        if isinstance(value, list) and str(hints[item.name]).startswith(("tuple", "typing.Tuple")):
            value = tuple(value)
        out[item.name] = value
    return out


class Record:
    """The JSON form of a record."""

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), separators=(",", ":"), sort_keys=True, ensure_ascii=True)  # type: ignore[call-overload]

    @classmethod
    def from_json(cls, text: str):
        return cls(**_thaw(cls, json.loads(text)))


@dataclass(frozen=True)
class RunRecord(Record):
    run_id: str
    trigger: str
    started_at: str
    finished_at: str | None = None
    ok: bool = True
    leads: int = 0
    cases: int = 0
    proposed: int = 0
    needs_human: int = 0
    dropped: int = 0
    errors: int = 0
    tokens: int = 0
    seconds: int = 0
    notes: tuple[str, ...] = ()
    reason: str | None = None
    investigated: bool = False  # the investigation ran in this run: the daily timer waits INVESTIGATE_EVERY_DAYS after the last such run (cases/run.py)
    held: int = 0  # the findings that were held back in this run because they say nothing about what to look at (cases/upkeep.py): no request was made for them


@dataclass(frozen=True)
class CaseRecord(Record):
    """One resource that Meternaut looked at. The id is derived from the resource, so a later run updates the same case."""

    case_id: str
    resource_id: str
    resource_name: str
    resource_type: str
    resource_group: str
    subscription_id: str
    detector: str
    run_id: str
    status: str
    recommendation: str | None = None
    confidence: float | None = None
    saving_usd_month: float | None = None
    cost_usd_30d: float | None = None
    summary: str = ""
    objections: tuple[str, ...] = ()
    guards: tuple[str, ...] = ()
    models: dict = field(default_factory=dict)  # {"detective": name, "skeptic": name or None}
    steps: tuple[dict, ...] = ()  # one dict per step: step, model, promptTokens, completionTokens, ms, ok, note
    facts: dict = field(default_factory=dict)  # the typed facts that the models saw; for a person to read and never for a model it can also hold `change` (what the finding would change and what code worked out from the bill lines), `group` (many resources) and `advisor`
    plan_id: str | None = None
    first_seen_at: str = ""
    updated_at: str = ""
    runs_seen: int = 1
    # Who the resource probably belongs to, as plain facts that code read from the estate (the tags and the Activity Log), for a person to read and never for a model:
    # {"tagOwner": the value of an owner tag, "tagName": the name of that tag, "createdBy": who made the resource, "createdAt": when (a time or a date),
    #  "changedBy": who changed it last, "changedAt": when, "lookedUp": True once the tags and the Activity Log were read, even when they held nothing}.
    # A key that is not known is left out. The text is from the estate: pages and letters show it escaped, and nothing trusts it. An empty dict means "not looked up".
    owner: dict = field(default_factory=dict)
    # What the lessons and the capability profile said when the case was found, as typed words and numbers, for a person to read and never for a model (cases/learning.py):
    # {"skeptic": the second AI's verdict, "past": {"n", "approved", "ratio", "boomerangs"}: how past requests like this were answered, "held": "history" when what past requests
    # showed held a proposal back, "access": a word of cases/capability.py when what the identity cannot see changes what can be said}. A key that is not known is left out.
    learned: dict = field(default_factory=dict)
    # The cost of each of the last 30 closed days (US dollars, the oldest first, 0.0 for a day with no cost line, the last on `cost_series_end`: YYYY-MM-DD, UTC), summed for a case of a group,
    # while a request about the case is open (cases/run.py, read_cost_series). None: never read, or could not be, or Azure has no cost line at all for what the case is about (a series of nothing but
    # zeros is never kept: `cost_series_end` then says on which day that was read, so that the next Watch of the same day does not ask again).
    cost_series: list[float] | None = None
    cost_series_end: str | None = None
    # The use of the resource on each of the last 30 closed days, for the second chart of the card of its request: one number a day, the oldest first, in the unit of the kind that `use_kind`
    # names (cases/usage.py: a percentage, bytes or a count), None for a day that Azure Monitor has no value for (a gap, never a zero), the last on `use_series_end` (YYYY-MM-DD, UTC). It is
    # kept while a request about the case is open, only for a case of one resource of a type that the table of cases/usage.py has, and only when at least 20 of the 30 days have a value
    # (cases/run.py, read_use_series). `use_kind` is a key of that table, a constant of the code and never text from the estate or from a model. None: never read, or could not be.
    use_series: list[float | None] | None = None
    use_series_end: str | None = None
    use_kind: str | None = None
    # How the 30-day cost of the finding was read (cases/costs.py: lines, none, failed or currency). Empty in a record of before the state existed: cases/brief.py reads such a record from
    # `cost_usd_30d` (a number above nothing is lines, 0.0 is none for a resource and unread for a subscription or a resource group, which an earlier version looked up by its own id).
    cost_state: str = ""
    # What the cost of a finding about a whole subscription or resource group is made of: its largest services and the rest, as cases/costs.py parts_of makes them. Empty for every other finding.
    cost_by_service: dict = field(default_factory=dict)
    # An estimate at list price of what a managed disk costs a month, for a finding that Azure has no cost line for ({"usdMonth", "tier", "table"}: cases/estimate.py). It is never a cost: it is kept
    # apart from `cost_usd_30d`, so that nothing counts it, learns from it or checks a saving against it. Empty for every other finding.
    estimate: dict = field(default_factory=dict)
    # The display name of the subscription of the resource, read once from Azure Resource Manager when the finding was made ("" when it could not be read): a person reads a name before an id.
    subscription_name: str = ""
    # Azure Advisor's own words for a finding that is an Advisor recommendation ({"problem", "solution"}: its short description, cut to one line). Text that Advisor wrote and never text for a model;
    # the title of the request and the line that says what to look at are made from it. Empty for every other finding.
    advice: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PlanRecord(Record):
    """The exact change that a person is asked to approve. The page shows these fields and never the models' prose."""

    plan_id: str
    case_id: str
    family: str  # the name of a family of cases/families, or ADVISE
    resource_id: str
    resource_name: str
    resource_group: str
    subscription_id: str
    code: str  # the first eight characters of the digest: a reference, not a proof
    title: str  # a verb, an object and a place
    what_changes: str
    saving_usd_month: float | None
    waiting_costs_usd_day: float | None
    could_go_wrong: str
    undo: str
    evidence_level: str
    approvers: tuple[str, ...]  # directory object ids
    created_at: str
    expires_at: str
    state: str = "open"
    approval_class: str = "R2"
    preconditions: dict = field(default_factory=dict)  # what the re-check right before the change looks at, e.g. {"diskState": "Unattached", "tag": "meternaut-planted"}
    target: dict = field(default_factory=dict)  # the typed parameters of the change as the plan states them, e.g. {"vmSize": "Standard_B1s", "fromVmSize": "Standard_B2s"}; empty for a delete
    # SHA-256 over every other field of the plan but state and code (cases/families/digest.py), 64 hexadecimal characters. The sign-in binds it and the runner compares it before it acts:
    # empty only in a plan that was made before the digest existed, which cannot be approved.
    digest: str = ""
    # When the wait of the request began, when that is before the request was made: a request that stands for another one keeps the oldest start (cases/approvals.py supersede). Not in the digest.
    waiting_since: str = ""
    # What the requests that this one stands for cost while they waited, in dollars (each at its own figure, for its own days, up to the day that this one was made). The cost of waiting adds what this one
    # has cost since it was made. Not in the digest.
    waited_usd: float = 0.0


def started(plan: PlanRecord) -> str:
    """When the wait of a request began: the start that it carries from the request that it stands for, else the time that it was made."""
    return plan.waiting_since or plan.created_at


@dataclass(frozen=True)
class DecisionRecord(Record):
    plan_id: str
    approver_oid: str
    approver_name: str
    decision: str  # one of DECISIONS
    at: str
    plan_code: str
    note: str = ""
    reason: str = ""  # one of DECLINE_REASONS, or empty: only a decline has one
    plan_digest: str = ""  # the digest of the plan that an approval was made for (an approval of a change records it; the other answers leave it empty)


@dataclass(frozen=True)
class ActionRecord(Record):
    """What happened to the change of one plan, and what the verifier saw afterwards."""

    plan_id: str
    case_id: str
    family: str
    resource_id: str
    state: str  # one of ACTION_STATES
    queued_at: str
    start_after: str | None = None  # kept for records of the earlier design, which waited for this time; a change now starts at the approver's sign-in
    started_at: str | None = None
    finished_at: str | None = None
    result: str = ""
    correlation_id: str = ""
    verified_at: str | None = None
    verification: dict = field(default_factory=dict)  # {"gone": bool, "costAfterUsd": float or None, "note": text}, and for a change that is not a delete {"now": what a read showed}; "noChange": True when nothing was written
    error: str | None = None
    step_up: bool = False  # Azure asked for an extra sign-in check: the action waits in the queue for it, and a second ask is final
    plan_digest: str = ""  # the digest of the plan that this action carries out (empty in an action of before the digest existed)
    # A write that Azure accepted and is still carrying out (the state is then `running`): {"pending": True, "acceptedAt": time, "via": the header that gave its address, or "none"}. The timer
    # reads the resource later and settles it. Empty for every other action.
    operation: dict = field(default_factory=dict)

    @property
    def no_change(self) -> bool:
        """The action made no change: when Meternaut looked, the resource was in the state that the plan wants (or was gone already), so nothing was written. The runner marks it with
        `noChange` in the check. Such an action is not checked by cost lines later and is never shown with a saving: this approval did not make it."""
        return isinstance(self.verification, dict) and self.verification.get("noChange") is True


@dataclass(frozen=True)
class SwitchRecord(Record):
    name: str  # one of SWITCH_NAMES
    paused: bool = False
    by: str = ""
    at: str = ""
    reason: str = ""


@dataclass(frozen=True)
class SettingsRecord(Record):
    oid: str
    channel: str = "email"
    language: str = "en"
    timezone: str = "Europe/Amsterdam"  # the zone of the times that the pages show and of the quiet hours; a zone that is empty or that this machine does not know is UTC (cases/quiet.py)
    working_days: tuple[int, ...] = (1, 2, 3, 4, 5)  # 1 is Monday
    # The quiet hours: nothing is sent to the person from `quiet_from` until `quiet_to`, by the clock of `timezone` (the window may cross midnight). Both empty: none, the default. A record that
    # a person saved before the quiet hours were applied holds the window that the page showed then (18:00 to 08:00): it applies now, as the page says.
    quiet_from: str = ""
    quiet_to: str = ""
    desk_day: int = 2
    weekly_budget: int = 3
    paused_until: str | None = None
    mutes: tuple[str, ...] = ()
    updated_at: str = ""


@dataclass(frozen=True)
class TwoPeopleRule(Record):
    """When a change needs two people instead of one (cases/twopeople.py). Off when it names no amount and no family: that is the default. A plan that the rule covers when it is made is of the
    approval class R3 for the rest of its life, whatever the rule says later. `by` and `at` are who changed the rule last, and when."""

    min_usd_month: float | None = None  # a change whose saving is at least this many US dollars a month needs two people; None: no amount
    families: tuple[str, ...] = ()  # the families of change that always need two people
    by: str = ""
    at: str = ""

    @property
    def on(self) -> bool:
        return self.min_usd_month is not None or bool(self.families)


@dataclass(frozen=True)
class NoteRecord(Record):
    note_id: str
    oid: str
    kind: str  # one of NOTE_KINDS
    text: str
    scope_resource_id: str | None = None
    understood_as: str = ""
    source: str = "the owner"
    created_at: str = ""
    expires_at: str = ""
    uses: int = 0


@dataclass(frozen=True)
class MailRecord(Record):
    """One message that Meternaut sent (or tried to send), kept so that the weekly budget and the repeats can be counted."""

    mail_id: str
    oid: str
    kind: str  # first_contact, approval, notice, verified, unsure, digest
    subject: str
    sent_at: str
    status: str  # sent, held, refused, failed
    plan_id: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class EscalationRecord(Record):
    """One record of the ladder of a request that waits (cases/escalation.py): a step, made once, or a person's put-off. A step keeps who was told by which source, the words of what could not
    be looked up, and what became of the message. Names are text from the directory: cut and cleaned, shown escaped, never trusted."""

    plan_id: str
    kind: str  # one of ESCALATION_KINDS
    number: int  # the step (1, 2, ...) or the put-off (1, 2, 3)
    at: str  # when it was made
    source: str = ""  # one of ESCALATION_SOURCES (a step only)
    who: tuple[str, ...] = ()  # object ids of the people that a step goes to; the person who put it off
    names: tuple[str, ...] = ()
    delivered: tuple[str, ...] = ()  # of `who`, those whose message the mailer accepted
    channel: str = "email"
    outcome: str = "due"  # due, held, failed or sent
    notes: tuple[str, ...] = ()  # words of cases/directory.py NOTES: what could not be looked up on the way
    detail: str = ""  # why a message is held or failed, in plain words
    tries: int = 0
    last_try: str = ""


def escalated_to(records: typing.Iterable[EscalationRecord], oid: str) -> bool:
    """Whether a step of the ladder of a request was delivered to this person (cases/escalation.py): a message that was sent, not one that was only meant for them."""
    return any(r.kind == "step" and oid.lower() in {o.lower() for o in r.delivered} for r in records)


def may_answer(principal: "Principal", plan: PlanRecord, ladder: typing.Callable[[], typing.Iterable[EscalationRecord]] = lambda: ()) -> bool:
    """The one rule of who may answer a request, for the decider and the pages. A person who is named on it may, with the role approver, or the role owner when it is advice, which changes nothing in
    Azure. Advice may also be answered by a person that a step of its ladder was delivered to (`ladder` is read only when nothing else lets the person answer), whatever their role on the list: the
    contacts, the owners, the people that the ladder came to last. Every answer of advice is theirs (worth acting on, not worth it, not mine, a question, decide later) and none of a change, which
    only a named approver makes, with their own sign-in to Azure (AGENTS.md rule 29)."""
    named = principal.oid.lower() in {a.lower() for a in plan.approvers}
    return (named and (principal.has("approver") or (plan.family == ADVISE and principal.has("owner")))) or (plan.family == ADVISE and escalated_to(ladder(), principal.oid))


@dataclass(frozen=True)
class LessonRecord(Record):
    """What one closed request taught (docs/proposals/15-learning.md): typed values only, never a name and never a text of a person or of an estate. One lesson for each plan."""

    lesson_id: str  # the id of the plan
    resource_type: str  # as Azure names it, in lower case, or "other"
    family: str  # one of FAMILIES, or ADVISE
    detector: str = ""
    basis: str = ""  # the basis of an investigation's finding (a word of a closed list), or empty
    proposal: str = ""  # delete, change or investigate, or empty
    signals: dict = field(default_factory=dict)  # a closed set of keys, each with a bucket: {"cost": "10-100", "usage": "none", ...}
    confidence: float | None = None  # what the first AI said, as it said it
    skeptic: str = ""  # agree, disagree, unsure, or none when the second AI gave no verdict
    answer: str = "expired"  # one of LESSON_ANSWERS
    reason: str = ""  # one of DECLINE_REASONS, or empty: only a decline has one
    opened_at: str = ""
    closed_at: str = ""
    result: str = ""  # one of LESSON_RESULTS: what became of the change when the person approved one
    predicted_usd_month: float | None = None
    measured_usd_month: float | None = None  # what the cost lines showed some days after a change, when they could be read
    measured_at: str = ""
    boomerang: bool = False  # the change was undone within weeks (the Activity Log shows the resource made again)
    boomerang_checked_at: str = ""
    updated_at: str = ""
    superseded: bool = False  # a later answer about the same resource and family contradicts this one, so it no longer counts for the calibration (learning.superseded_ids)


@dataclass(frozen=True)
class CheckRecord(Record):
    """The latest drift check of the app (cases/drift.py): when it started, what started it (the timer, or a person on the Operations page), whether it has reported, and one row for each control:
    {"control", "layer", "state", "detail"}. Only the latest is kept: the telemetry holds a line for every control of every check."""

    started_at: str
    trigger: str = "timer"  # one of CHECK_TRIGGERS
    by: str = ""  # the name of the person who started it on the Operations page
    finished_at: str = ""  # empty while it runs, and for ever when it did not report
    tripped: bool = False  # the check pulled the switch investigation
    results: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ClaimRecord(Record):
    """One statement of Microsoft's documentation about a resource type, with the page and a quote that code found on that page. `kind` is STUDIED for the mark that the Scholar looked and
    the documentation gave nothing of the closed kinds: it keeps the same type from being studied again at once."""

    claim_id: str
    resource_type: str
    kind: str  # one of CLAIM_KINDS, or STUDIED
    url: str = ""
    quote: str = ""  # at most 200 characters, copied from the page
    read_at: str = ""
    expires_at: str = ""
    checked_at: str = ""
    state: str = "fresh"  # one of CLAIM_STATES
    recipe: str = "refetch-and-match"  # how it is checked again: the page is fetched again and the quote must still be on it


@dataclass(frozen=True)
class CapabilityRecord(Record):
    """What the app's identity could see in one run, as words of a closed list (cases/capability.py). It holds no id, no name and no address of an estate."""

    run_id: str
    at: str
    subscriptions: int = 0
    cost: str = "unknown"  # visible, not visible with this access, unavailable or unknown
    billing: str = "unknown"  # the billing accounts of the identity: the same four words
    agreement: str = "unknown"  # what the billing accounts say: enterprise, customer, pay-as-you-go, partner, other, mixed (they differ) or unknown
    hint: str = "unknown"  # what the quota ids of the subscriptions suggest, when the billing accounts say nothing: pay-as-you-go, enterprise-or-customer, partner, other, mixed or unknown
    reservations: str = "unknown"
    savings_plans: str = "unknown"
    price_sheet: str = "unknown"


@dataclass(frozen=True)
class InvestigationRecord(Record):
    """What one investigation looked at and came to (made by cases/activity.py, shown by the page "What the AI looked at"): closed words, numbers, the AI's sentences cleaned of ids, and kinds of
    resource; no name, tag or id of a resource. A run from before it has none, which is not a record of nothing."""

    run_id: str
    at: str  # when the investigation began
    trigger: str = ""  # `timer`, or `request` (a person or a tool asked for the run)
    investigator: str = ""  # the two models
    skeptic: str = ""
    calls: int = 0  # tool calls made, and allowed
    max_calls: int = 0
    tokens: int = 0
    seconds: int = 0
    max_seconds: int = 0
    end: str = "failed"  # one of INVESTIGATION_ENDS
    answered: bool = False  # the Investigator's answer could be read
    stop: str = ""  # the code of cases/harness.py that refused or stopped the run
    note: str = ""  # what the run said of itself when it ended in no answer
    examined: tuple[str, ...] = ()  # the Investigator's own phrases about what it looked at
    # One dict for each finding: n, basis, proposal, sure, resources, says, verdict, doubts, kept, left (resources left out, by reason), fates (by what became of them) and note (of code).
    findings: tuple[dict, ...] = ()
    # The kinds of resource that the run knows the estate has (known), those that the tools touched (looked) and, dearest first by the cost lines (no amount is kept), the first of the touched ones
    # ([kind, what the tools did to it]) and of the others (unread).
    known: int = 0
    looked: int = 0
    kinds: tuple[list, ...] = ()
    unread: tuple[str, ...] = ()
    subs: int = 0  # the subscriptions of the run, and those whose cost was read in dollars (which the order rests on)
    subs_costed: int = 0
    # When the estate was looked at in beats (cases/beats.py), one dict for each: n, kinds (the words of its focus), billing (the lines of the bill that no resource owns were in it), more (kinds that the last one holds
    # beyond those named), calls, max_calls, tokens, seconds, end (one of INVESTIGATION_ENDS), seeded (the resources whose picture code read), looked (how many of its kinds its tools read), found (findings that it wrote)
    # and says (what it said that it examined). Counts and words, no amount. `more` counts the findings that the record had no room for.
    beats: tuple[dict, ...] = ()
    more: int = 0


@dataclass(frozen=True)
class Principal:
    """The signed-in person, from the headers that the platform's sign-in adds. It is never read from a form or a link."""

    oid: str
    name: str
    roles: tuple[str, ...] = ()

    def has(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class DecideResult:
    ok: bool
    # Answers: declined, asked, not_mine, later, confirmed (the first of two people: the plan stays open for the second) and acknowledged (an advise plan answered with "worth acting on":
    # nothing changes in Azure). What a sign-in to Azure led to:
    # ran, ran_unconfirmed, running (Azure accepted the change and is still making it: the timer reads the resource later), unchanged (nothing had to be changed: the resource was as the plan
    # wants when the runner looked, and nothing was written), stopped (a check right before the change refused it and nothing was written: the request is open again, except when the request
    # itself is not what was approved, which closes it), azure_refused, failed, signin_failed, and step_up_failed
    # (the extra sign-in check that Azure asked for was not completed: the request is closed). step_up: Azure asked for an extra sign-in check, and `location` is where the person goes.
    # Refusals: refused_code, refused_state, refused_role, refused_paused, expired, duplicate, error.
    kind: str
    message: str
    plan: PlanRecord | None = None
    location: str = field(default="", repr=False)  # only for step_up: the sign-in of Microsoft Entra, to which the person is sent again (it holds the claims request)


@dataclass(frozen=True)
class Begun:
    """What starting an approval gives: the address that the person is sent to (to sign in to Azure), or the refusal to show. Never both."""

    location: str = ""
    refusal: DecideResult | None = None


READY, REFUSED, UNKNOWN = "ready", "refused", "unknown"


@dataclass(frozen=True)
class Readiness:
    """What a look at a resource, made now, says about a change that waits for an approval (cases/precheck.py): `ready` (none of the checks that the runner makes right before the change would
    refuse it), `refused` (one would, and `why` says which, in plain words, as the end of a sentence that starts "Meternaut will not change this disk now:") or `unknown` (the look could not be made,
    and `why` stays empty). The look is advice for a page: the runner makes the same checks again right before it acts, with the approver's own token."""

    state: str
    why: str = ""


class Store(Protocol):
    """What the pages, the approval loop, the change and the Watch keep. Every call may raise StoreError; a caller that cannot read a switch treats it as pulled."""

    def runs_recent(self, limit: int = 20) -> list[RunRecord]: ...
    def run_put(self, run: RunRecord) -> None: ...
    def cases_recent(self, limit: int = 100, status: str | None = None) -> list[CaseRecord]: ...
    def case_get(self, case_id: str) -> CaseRecord | None: ...
    def case_put(self, case: CaseRecord) -> None: ...
    def case_update(self, case_id: str, change: typing.Callable[[CaseRecord], CaseRecord | None]) -> bool:
        """Changes a case that another step may be changing at the same moment (an approval, the runner, the Watch's own reads): `change` is given the case as it is stored and returns the
        new record, or None to leave the case as it is. The new record is kept only when nobody has changed the case since it was read; when somebody has, `change` is given the newer record
        and its result is kept instead, so that what the other step wrote is never written over. Returns False when the case is gone or when `change` returned None."""
        ...
    def plans_open(self) -> list[PlanRecord]: ...
    def plans_held(self) -> list[PlanRecord]:
        """The requests of the findings that a guard holds back (the state HELD), newest first. plans_recent leaves them out: they never end by the clock, and a bulk of them would crowd the newest plans."""
        ...
    def plans_recent(self, limit: int = 50) -> list[PlanRecord]: ...
    def plans_expired(self) -> list[PlanRecord]: ...
    def plan_get(self, plan_id: str) -> PlanRecord | None: ...
    def plan_put(self, plan: PlanRecord) -> None: ...
    def decisions_of_plan(self, plan_id: str) -> list[DecisionRecord]: ...
    def decisions_by(self, oid: str, limit: int = 100) -> list[DecisionRecord]: ...
    def decision_put(self, decision: DecisionRecord) -> bool:
        """Keeps one decision per approver and plan. Returns False, and changes nothing, when this approver has a decision of another kind than a question or a "later" already, and
        than a confirmation that this answer may replace (can_replace).

        A question ("ask") and a "later" are not decisions: a later answer of the same approver replaces them."""
        ...
    def decision_release(self, plan_id: str, oid: str) -> None:
        """Removes the approval of a person on a plan whose change was refused before anything was written (runner.py), so that the approval is as if it had not been given and the person can
        approve again. Only an approval goes: any other answer of the person stays, and so does a confirmation (the first of two people)."""
        ...
    def action_get(self, plan_id: str) -> ActionRecord | None: ...
    def action_put(self, action: ActionRecord) -> None: ...
    def action_claim(self, action: ActionRecord) -> bool:
        """Stores the first action of a plan and returns True; returns False, and changes nothing, when the plan has an action already, unless that action was withdrawn (a change that was
        refused before anything was written, and whose request is open again): the new action then takes its place, and only one of two approvers who claim at the same moment gets True.

        Of several approvers who answer at the same moment, only one gets True: that one makes the change."""
        ...
    def action_release(self, plan_id: str) -> None:
        """Removes the action of a plan that was claimed and has not started, so that a new try can claim it. An action that has started or finished stays."""
        ...
    def actions_recent(self, limit: int = 50) -> list[ActionRecord]: ...
    def switch_get(self, name: str) -> SwitchRecord: ...
    def switch_put(self, switch: SwitchRecord) -> None: ...
    def switches(self) -> list[SwitchRecord]: ...
    def settings_get(self, oid: str) -> SettingsRecord: ...
    def settings_put(self, settings: SettingsRecord) -> None: ...
    def settings_delete(self, oid: str) -> None: ...
    def rule_get(self) -> TwoPeopleRule:
        """When a change needs two people: the rule that was saved, or the one that is off."""
        ...
    def rule_put(self, rule: TwoPeopleRule) -> None: ...
    def notes_of(self, oid: str) -> list[NoteRecord]: ...
    def note_put(self, note: NoteRecord) -> None: ...
    def note_delete(self, oid: str, note_id: str) -> None: ...
    def do_not_touch(self) -> set[str]:
        """Lower-case resource ids that carry a do-not-touch mark that has not expired."""
        ...
    def nonce_new(self, oid: str, purpose: str, ttl_seconds: int = 3600, data: str = "") -> str:
        """A one-time token for one person and one purpose (the id of a plan, or the name of a form). It is kept on the server, with `data` (text, never a token)."""
        ...
    def nonce_peek(self, token: str, oid: str, purpose: str) -> str | None:
        """The `data` that nonce_take would give, without using the token up."""
        ...
    def nonce_take(self, token: str, oid: str, purpose: str) -> str | None:
        """The `data` that was kept with the token, once: for the person and the purpose that the token was made for, before it expired. None for anything else, and for a second use."""
        ...
    def nonce_use(self, token: str, oid: str, purpose: str) -> bool:
        """True once, for the person and the purpose that the token was made for; False for anything else, and for a second use."""
        ...
    def mail_put(self, mail: MailRecord) -> None: ...
    def mails_since(self, oid: str, since: str) -> list[MailRecord]:
        """The messages to one person that were sent at or after `since` (a time in the TIME_FORMAT)."""
        ...
    def escalation_claim(self, record: EscalationRecord) -> bool:
        """Keeps a step or a put-off only when none with that number is kept yet, and says whether it did: a step is made once, whoever asks."""
        ...
    def escalation_put(self, record: EscalationRecord) -> None: ...
    def escalations_of(self, plan_id: str) -> list[EscalationRecord]: ...
    def cursor_get(self) -> str:
        """The key of the request that the last round of the ladder ended with (cases/escalation.py `_window`), or an empty text: the next round goes on with the request after it."""
        ...
    def cursor_put(self, key: str) -> None: ...
    def lesson_put(self, lesson: LessonRecord) -> None: ...
    def lessons_of(self, resource_type: str, limit: int = 500) -> list[LessonRecord]:
        """The lessons of one resource type (any family), at most `limit`."""
        ...
    def lessons_recent(self, limit: int = 300) -> list[LessonRecord]: ...
    def check_latest(self) -> CheckRecord | None: ...
    def check_put(self, check: CheckRecord) -> None:
        """Keeps the latest drift check: the one that a check writes when it has reported (or, for a check that does not report, the claim that began it)."""
        ...
    def check_claim(self, check: CheckRecord, after: str) -> bool:
        """Keeps `check` as the latest drift check only when the latest is still the one that began at `after` (empty: there is none), and returns whether it did. Of two people who start a
        check at the same moment, only one gets True."""
        ...
    def claim_put(self, claim: ClaimRecord) -> None: ...
    def claims_of(self, resource_type: str) -> list[ClaimRecord]: ...
    def claims_recent(self, limit: int = 500) -> list[ClaimRecord]: ...
    def profile_put(self, profile: CapabilityRecord) -> None: ...
    def profile_latest(self) -> CapabilityRecord | None: ...
    def investigation_put(self, record: InvestigationRecord) -> None: ...  # keeps only the newest KEPT_INVESTIGATIONS
    def investigations_recent(self, limit: int = KEPT_INVESTIGATIONS) -> list[InvestigationRecord]: ...


class Decider(Protocol):
    """The approval loop as the pages see it, for the answers that change nothing in Azure: decline, ask a question, not mine, later, and the answer of an advise plan
    ("worth acting on", sent as approve). It checks the person, the plan code, the one-time token, the plan's state, the switches and the expiry. The approval of a change is
    not decided here: it is made at the person's sign-in to Azure."""

    def decide(self, principal: Principal, plan_id: str, decision: str, code: str, nonce: str, note: str = "", reason: str = "") -> DecideResult: ...


class Delegate(Protocol):
    """An approval, in its steps. `begin` checks the form and gives the address of the sign-in to Azure; `finish` takes the person back from that sign-in, records the
    approval and makes the change with the person's own token. When Azure asks for an extra sign-in check, `finish` answers with the kind step_up and the address of
    the sign-in once more, and the next `finish` makes the change. Meternaut holds no right of its own to change Azure."""

    def begin(self, principal: Principal, plan_id: str, code: str, nonce: str, note: str = "", hint: str = "") -> Begun: ...
    def finish(self, principal: Principal, query: dict[str, str]) -> DecideResult: ...


class Checker(Protocol):
    """The look that a page takes at the resource of a change before it offers Approve (cases/precheck.py): the checks that the runner would make right before the change, made now with the
    app's own reader, which holds no right to write. It never raises, it changes nothing, and what it says is advice: the runner checks again when it acts."""

    def check(self, plan: PlanRecord) -> Readiness: ...


class StoreError(Exception):
    """A store call that failed. `status` is the HTTP status of the service, or 0. The text never holds a token."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status
