"""The records of the console and of the approval loop, and the two ports that the pages and the loop use.

Every record is a frozen dataclass that turns into one JSON text and back (`to_json`, `from_json`), so a store keeps it in one property. A time is
`YYYY-MM-DDTHH:MM:SSZ` in UTC. A record never holds a token, a key or a secret. A name that comes from the estate is data to show, never an instruction.

Migration note (the decision brief). A record is read by `_thaw`: a key that the dataclass does not know is dropped, and a field that the stored JSON lacks takes its default. So a
record that was written before a field existed still reads, and a record that a newer version wrote still reads in an older one. The decision brief added only things of that kind:
the case status `acknowledged`, the answer `later`, the family `advise`, `CaseRecord.owner` (empty: not looked up) and `DecisionRecord.reason` (empty: no reason). Nothing was
renamed or removed, so no stored record has to be rewritten, and the tables keep their keys.

The families of change added the same kind of thing: `PlanRecord.target` and `PlanRecord.digest` (a plan of before has no digest, so it cannot be approved: the Watch makes a new one),
`DecisionRecord.plan_digest`, `ActionRecord.plan_digest` and `ActionRecord.operation`. The constant FAMILIES is gone: the families are in cases/families (their registry is
cases/families/registry.py). The learning (docs/proposals/15-learning.md) added three new kinds of record, LessonRecord, ClaimRecord and CapabilityRecord, each with its own table, and no
field of a record that was there before. The daily cost of a request added `CaseRecord.cost_series` and `cost_series_end` (None: never read).
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
PLAN_STATES = ("open", "approved", "consumed", "declined", "expired", "withdrawn", "failed")
# `later` is a person's "not now": it records nothing but that the person has seen the request, leaves the plan open, and a later answer replaces it (like `ask`).
DECISIONS = ("approve", "decline", "ask", "not_mine", "later")
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
ACTION_STATES = ("queued", "running", "done", "failed", "unknown", "verified", "withdrawn")
SWITCH_NAMES = ("all", "changes", "messages", "investigation")
NOTE_KINDS = ("note", "do_not_touch")
CHANNELS = ("email", "teams", "desk")
ROLES = ("owner", "approver", "ops")
# The most characters that the address which the console sends a person to (the sign-in of Microsoft Entra) may have after the host and the slash behind it. The pages refuse a
# longer one, and the code that makes the address keeps to it.
MAX_SIGNIN_PATH = 2000

# What a change may be: one family is one kind of change. The families themselves are in cases/families (the registry): each has its own plan text, its own re-check right before it
# acts, its own call to Azure and its own test (AGENTS.md rule 26 (a)). `family` in a plan is the name of one of them, or ADVISE.
# The family of a plan that asks a person whether a finding is worth acting on. It changes nothing in Azure and has no call in the runner's list: the answer is recorded and
# nothing else happens. A finding about a resource that Meternaut may not change gets such a plan, so that the person can answer it.
ADVISE = "advise"
# A finding that a person has answered is not put to them again for this many days (cases/approvals.py, cases/learning.py, and the start page, which counts what is held back).
ADVICE_QUIET_DAYS = 30
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
    facts: dict = field(default_factory=dict)  # the typed facts that the models saw; for a person to read and never for a model it can also hold `unread` (a workspace) and `group` (many resources)
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
    # while a request about the case is open (cases/run.py, read_cost_series). None: never read, or could not be.
    cost_series: list[float] | None = None
    cost_series_end: str | None = None


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
    timezone: str = "Europe/Amsterdam"
    working_days: tuple[int, ...] = (1, 2, 3, 4, 5)  # 1 is Monday
    quiet_from: str = "18:00"
    quiet_to: str = "08:00"
    desk_day: int = 2
    weekly_budget: int = 3
    paused_until: str | None = None
    mutes: tuple[str, ...] = ()
    updated_at: str = ""


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
    kind: str  # first_contact, approval, notice, verified, digest
    subject: str
    sent_at: str
    status: str  # sent, held, refused, failed
    plan_id: str | None = None
    detail: str = ""


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
    # Answers: declined, asked, not_mine, later, and acknowledged (an advise plan answered with "worth acting on": nothing changes in Azure). What a sign-in to Azure led to:
    # ran, ran_unconfirmed, running (Azure accepted the change and is still making it: the timer reads the resource later), unchanged (nothing had to be changed: the resource was as the plan
    # wants when the runner looked, and nothing was written), stopped, azure_refused, failed, signin_failed, and step_up_failed
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


class Store(Protocol):
    """What the console, the approval loop, the change and the Watch keep. Every call may raise StoreError; a caller that cannot read a switch treats it as pulled."""

    def runs_recent(self, limit: int = 20) -> list[RunRecord]: ...
    def run_put(self, run: RunRecord) -> None: ...
    def cases_recent(self, limit: int = 100, status: str | None = None) -> list[CaseRecord]: ...
    def case_get(self, case_id: str) -> CaseRecord | None: ...
    def case_put(self, case: CaseRecord) -> None: ...
    def plans_open(self) -> list[PlanRecord]: ...
    def plans_recent(self, limit: int = 50) -> list[PlanRecord]: ...
    def plan_get(self, plan_id: str) -> PlanRecord | None: ...
    def plan_put(self, plan: PlanRecord) -> None: ...
    def decisions_of_plan(self, plan_id: str) -> list[DecisionRecord]: ...
    def decisions_by(self, oid: str, limit: int = 100) -> list[DecisionRecord]: ...
    def decision_put(self, decision: DecisionRecord) -> bool:
        """Keeps one decision per approver and plan. Returns False, and changes nothing, when this approver has a decision of another kind than a question or a "later" already.

        A question ("ask") and a "later" are not decisions: a later answer of the same approver replaces them."""
        ...
    def action_get(self, plan_id: str) -> ActionRecord | None: ...
    def action_put(self, action: ActionRecord) -> None: ...
    def action_claim(self, action: ActionRecord) -> bool:
        """Stores the first action of a plan and returns True; returns False, and changes nothing, when the plan has an action already.

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
    def notes_of(self, oid: str) -> list[NoteRecord]: ...
    def note_put(self, note: NoteRecord) -> None: ...
    def note_delete(self, oid: str, note_id: str) -> None: ...
    def do_not_touch(self) -> set[str]:
        """Lower-case resource ids that carry a do-not-touch mark that has not expired."""
        ...
    def nonce_new(self, oid: str, purpose: str, ttl_seconds: int = 3600, data: str = "") -> str:
        """A one-time token for one person and one purpose (the id of a plan, or the name of a form). It is kept on the server, with `data` (text, never a token)."""
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
    def lesson_put(self, lesson: LessonRecord) -> None: ...
    def lessons_of(self, resource_type: str, limit: int = 500) -> list[LessonRecord]:
        """The lessons of one resource type (any family), at most `limit`."""
        ...
    def lessons_recent(self, limit: int = 300) -> list[LessonRecord]: ...
    def claim_put(self, claim: ClaimRecord) -> None: ...
    def claims_of(self, resource_type: str) -> list[ClaimRecord]: ...
    def claims_recent(self, limit: int = 500) -> list[ClaimRecord]: ...
    def profile_put(self, profile: CapabilityRecord) -> None: ...
    def profile_latest(self) -> CapabilityRecord | None: ...


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


class StoreError(Exception):
    """A store call that failed. `status` is the HTTP status of the service, or 0. The text never holds a token."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status
