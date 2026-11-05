"""The records of the console and of the approval loop, and the two ports that the pages and the loop use.

Every record is a frozen dataclass that turns into one JSON text and back (`to_json`, `from_json`), so a store keeps it in one property. A time is
`YYYY-MM-DDTHH:MM:SSZ` in UTC. A record never holds a token, a key or a secret. A name that comes from the estate is data to show, never an instruction.
"""
from __future__ import annotations

import dataclasses
import json
import typing
from dataclasses import dataclass, field
from typing import Protocol

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

CASE_STATUSES = ("proposed", "needs_human", "dropped", "error", "awaiting_ok", "approved", "running", "done", "failed", "declined", "expired", "verified")
# What a case is while a person has still to answer, and what it is once the loop has finished with it.
CASE_OPEN = ("awaiting_ok", "approved", "running")
CASE_CLOSED = ("done", "failed", "declined", "expired", "verified")
PLAN_STATES = ("open", "approved", "consumed", "declined", "expired", "withdrawn", "failed")
DECISIONS = ("approve", "decline", "ask", "not_mine")
ACTION_STATES = ("queued", "running", "done", "failed", "unknown", "verified", "withdrawn")
SWITCH_NAMES = ("all", "changes", "messages")
NOTE_KINDS = ("note", "do_not_touch")
CHANNELS = ("email", "teams", "desk")
ROLES = ("owner", "approver", "ops")

# What the runner may do: one family is one kind of change on one kind of resource.
FAMILIES = {
    "delete-disk": "microsoft.compute/disks",
    "delete-public-ip": "microsoft.network/publicipaddresses",
}


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
    facts: dict = field(default_factory=dict)  # the typed facts that the models saw
    plan_id: str | None = None
    first_seen_at: str = ""
    updated_at: str = ""
    runs_seen: int = 1


@dataclass(frozen=True)
class PlanRecord(Record):
    """The exact change that a person is asked to approve. The page shows these fields and never the models' prose."""

    plan_id: str
    case_id: str
    family: str  # one of FAMILIES
    resource_id: str
    resource_name: str
    resource_group: str
    subscription_id: str
    code: str  # eight characters of the plan's hash: a reference, not a proof
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
    preconditions: dict = field(default_factory=dict)  # what the runner re-checks, e.g. {"diskState": "Unattached", "tag": "meternaut-planted"}


@dataclass(frozen=True)
class DecisionRecord(Record):
    plan_id: str
    approver_oid: str
    approver_name: str
    decision: str  # one of DECISIONS
    at: str
    plan_code: str
    note: str = ""


@dataclass(frozen=True)
class ActionRecord(Record):
    """What the runner did for one plan, and what the verifier saw afterwards."""

    plan_id: str
    case_id: str
    family: str
    resource_id: str
    state: str  # one of ACTION_STATES
    queued_at: str
    start_after: str | None = None  # the writer does not start before this time: the window in which the first approver can still cancel
    started_at: str | None = None
    finished_at: str | None = None
    result: str = ""
    correlation_id: str = ""
    verified_at: str | None = None
    verification: dict = field(default_factory=dict)  # {"gone": bool, "costAfterUsd": float or None, "note": text}
    error: str | None = None


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
    kind: str  # recorded, declined, asked, not_mine, withdrawn, or a refusal: refused_code, refused_state, refused_role, refused_paused, expired, duplicate, error
    message: str
    plan: PlanRecord | None = None


class Store(Protocol):
    """What the console, the approval loop, the runner and the Watch keep. Every call may raise StoreError; a caller that cannot read a switch treats it as pulled."""

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
        """Keeps one decision per approver and plan. Returns False, and changes nothing, when this approver has a decision of another kind than a question already.

        A question ("ask") is not a decision: a later answer of the same approver replaces it."""
        ...
    def action_get(self, plan_id: str) -> ActionRecord | None: ...
    def action_put(self, action: ActionRecord) -> None: ...
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
    def nonce_new(self, oid: str, purpose: str, ttl_seconds: int = 3600) -> str:
        """A one-time token for one person and one purpose (the id of a plan, or the name of a form). It is kept on the server."""
        ...
    def nonce_use(self, token: str, oid: str, purpose: str) -> bool:
        """True once, for the person and the purpose that the token was made for; False for anything else, and for a second use."""
        ...
    def mail_put(self, mail: MailRecord) -> None: ...
    def mails_since(self, oid: str, since: str) -> list[MailRecord]:
        """The messages to one person that were sent at or after `since` (a time in the TIME_FORMAT)."""
        ...


class Decider(Protocol):
    """The approval loop as the pages see it. It checks the person, the plan code, the one-time token, the plan's state, the switches and the expiry."""

    def decide(self, principal: Principal, plan_id: str, decision: str, code: str, nonce: str, note: str = "") -> DecideResult: ...
    def withdraw(self, principal: Principal, plan_id: str, nonce: str) -> DecideResult: ...


class StoreError(Exception):
    """A store call that failed. `status` is the HTTP status of the service, or 0. The text never holds a token."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status
