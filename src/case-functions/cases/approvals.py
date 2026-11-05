"""The approval loop: a plan is made for a case that the writer could act on, a person answers it on a page, and the answer is recorded.

Nothing here changes Azure. An approved plan waits for its start time (the window in which the first approver can still cancel), and the runner
(runner.py) is the only code that makes the change. The plan is computed by code from the lead's typed facts and never from a model's words.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass, replace
from typing import Callable

from . import switches
from .detectors import Lead
from .memory_store import parse, stamp, utc_now
from .models import (ActionRecord, CaseRecord, DecideResult, DecisionRecord, PlanRecord, Principal, Store, StoreError)
from .roles import clean_text

FAMILY_OF = {"orphan-managed-disk": "delete-disk", "orphan-public-ip": "delete-public-ip"}
# title, what the resource is called in a sentence, what cannot be undone
WORDS = {
    "delete-disk": ("Delete an unattached managed disk", "disk",
                    "A deleted disk cannot be restored and its data is lost. A new disk with the same name can be made, empty."),
    "delete-public-ip": ("Delete an unassigned public IP address", "public IP address",
                         "A deleted public IP address cannot be restored. The address is released and may not be given again; a new one can be made."),
}
RE_CHECK = ("the resource is still unattached or unassigned, still carries the tag that marks it as planted by Meternaut, is still in this resource group "
            "and has no management lock")


@dataclass(frozen=True)
class ApprovalSettings:
    writer_group: str  # the one resource group in which the writer may act
    planted_tag: str = "meternaut-planted"
    ttl_hours: int = 72
    delay_seconds: int = 120


def _planted(lead: Lead, settings: ApprovalSettings) -> bool:
    return any(key.lower() == settings.planted_tag.lower() and str(value).strip() for key, value in lead.tags.items())


def is_fixture(lead: Lead, settings: ApprovalSettings) -> bool:
    """A resource that Meternaut planted itself, in the one group where the writer may act: the one kind of resource that is not held back for being new."""
    return lead.resource_group.lower() == settings.writer_group.lower() and _planted(lead, settings)


def why_not(case: CaseRecord, lead: Lead, settings: ApprovalSettings, store: Store) -> str | None:
    """None when a plan can be made for the case; otherwise the plain reason why not."""
    if case.status != "proposed" or case.recommendation != "delete":
        return "the case is not proposed for deletion"
    if lead.detector not in FAMILY_OF:
        return "the writer has no action for this kind of resource"
    if lead.resource_group.lower() != settings.writer_group.lower():
        return "the resource is outside the one resource group in which the writer may act"
    if not _planted(lead, settings):
        return f"the resource does not carry the {settings.planted_tag} tag"
    try:
        if lead.resource_id.lower() in store.do_not_touch():
            return "a person marked the resource do-not-touch"
        if any(p.resource_id.lower() == lead.resource_id.lower() for p in store.plans_open()):
            return "a plan for this resource is open already"
    except StoreError:
        return "the store could not be read"
    return None


def build_plan(case: CaseRecord, lead: Lead, approvers: tuple[str, ...], now: dt.datetime, settings: ApprovalSettings,
               new_id: Callable[[], str] = lambda: uuid.uuid4().hex) -> PlanRecord:
    family = FAMILY_OF[lead.detector]
    title, noun, undo = WORDS[family]
    plan_id = new_id()
    expires = stamp(now + dt.timedelta(hours=settings.ttl_hours))
    saving = case.saving_usd_month if case.cost_usd_30d else None
    waiting = round(saving / 30, 2) if saving else None
    code = hashlib.sha256(f"{plan_id}|{family}|{lead.resource_id.lower()}|{expires}".encode("utf-8")).hexdigest()[:8].upper()
    objections = len(case.objections)
    return PlanRecord(
        plan_id=plan_id, case_id=case.case_id, family=family, resource_id=lead.resource_id, resource_name=clean_text(lead.name, 120),
        resource_group=clean_text(lead.resource_group, 90), subscription_id=lead.subscription_id, code=code,
        title=f"{title} in resource group {clean_text(lead.resource_group, 90)}",
        what_changes=(f"Meternaut's writer deletes the {noun} named {clean_text(lead.name, 120)} in resource group {clean_text(lead.resource_group, 90)} "
                      f"(subscription {lead.subscription_id[:8]}). It changes nothing else. Right before it deletes, it reads the resource again and stops "
                      f"unless {RE_CHECK}."),
        saving_usd_month=saving, waiting_costs_usd_day=waiting,
        could_go_wrong=("If something still uses the resource, that use stops. The writer's re-check stops the change when anything is attached or assigned. "
                        + (f"The Skeptic role raised {objections} objection{'s' if objections != 1 else ''}: they are in the notebook." if objections
                           else "The Skeptic role raised no objection.")),
        undo=undo,
        evidence_level=("Observed now: Azure Resource Graph lists the resource as unattached or unassigned and as planted by Meternaut. Judged: two AI roles "
                        "running on different models agree. Not measured yet: the saving, which cost lines confirm after the change."),
        approvers=approvers, created_at=stamp(now), expires_at=expires, state="open", approval_class="R2",
        preconditions={"family": family, "resourceType": lead.resource_type, "tag": settings.planted_tag, "resourceGroup": lead.resource_group.lower()},
    )


class Approvals:
    """The Decider that the pages call, and the rest of the loop around a plan."""

    def __init__(self, store: Store, settings: ApprovalSettings, clock: Callable[[], dt.datetime] = utc_now) -> None:
        self.store, self.settings, self.clock = store, settings, clock

    def _set_case(self, case_id: str, status: str) -> None:
        case = self.store.case_get(case_id)
        if case is not None and case.status != status:
            self.store.case_put(_with(case, status=status, updated_at=stamp(self.clock())))

    def _expire_if_due(self, plan: PlanRecord, now: dt.datetime) -> PlanRecord:
        if plan.state == "open" and now >= parse(plan.expires_at):
            plan = _plan_with(plan, state="expired")
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "expired")
        return plan

    def decide(self, principal: Principal, plan_id: str, decision: str, code: str, nonce: str, note: str = "") -> DecideResult:
        now = self.clock()
        try:
            return self._decide(principal, plan_id, decision, code, nonce, clean_text(note, 300), now)
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing is approved. Try again in a few minutes.")

    def _decide(self, principal: Principal, plan_id: str, decision: str, code: str, nonce: str, note: str, now: dt.datetime) -> DecideResult:
        if decision not in ("approve", "decline", "ask", "not_mine"):
            return DecideResult(False, "error", "That answer is not one of the answers on the page.")
        plan = self.store.plan_get(plan_id)
        if plan is None:
            return DecideResult(False, "refused_state", "This request does not exist. Nothing is approved.")
        if not principal.has("approver") or principal.oid.lower() not in plan.approvers:
            return DecideResult(False, "refused_role", "I cannot take your OK on this request.")
        plan = self._expire_if_due(plan, now)
        if plan.state == "expired":
            return DecideResult(False, "expired", f"This request expired on {plan.expires_at} UTC. Nothing has changed.", plan)
        if plan.state != "open":
            return DecideResult(False, "refused_state", f"This request is {_words(plan.state)}. Nothing more can be recorded.", plan)
        if decision == "approve" and switches.pulled(self.store, "all", "changes"):
            return DecideResult(False, "refused_paused", "Changes are paused here. Nothing has changed, and your OK cannot be recorded now.", plan)
        if (code or "").strip().upper() != plan.code:
            return DecideResult(False, "refused_code", "This plan changed. Nothing is approved. A new message will bring the new plan and code.")
        if not self.store.nonce_use(nonce, principal.oid, plan.plan_id):
            return DecideResult(False, "error", "This form is no longer valid. Open the link in the message again. Nothing is approved.", plan)
        record = DecisionRecord(plan_id=plan.plan_id, approver_oid=principal.oid, approver_name=clean_text(principal.name, 80), decision=decision,
                                at=stamp(now), plan_code=plan.code, note=note)
        if not self.store.decision_put(record):
            return DecideResult(False, "duplicate", "You answered this request already. Your answer stands.", plan)
        if decision == "ask":
            return DecideResult(True, "asked", "Your question is recorded. Nothing is approved. The request stays open.", plan)
        if decision == "decline":
            plan = _plan_with(plan, state="declined")
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "declined")
            return DecideResult(True, "declined", "Declined. Nothing has changed.", plan)
        if decision == "not_mine":
            plan = _plan_with(plan, state="withdrawn")
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "needs_human")
            return DecideResult(True, "not_mine", "Recorded: this resource is not yours. Nothing is approved.", plan)
        start = now + dt.timedelta(seconds=self.settings.delay_seconds)
        plan = _plan_with(plan, state="approved")
        self.store.plan_put(plan)
        self.store.action_put(ActionRecord(plan_id=plan.plan_id, case_id=plan.case_id, family=plan.family, resource_id=plan.resource_id, state="queued",
                                           queued_at=stamp(now), start_after=stamp(start), correlation_id=uuid.uuid4().hex))
        self._set_case(plan.case_id, "approved")
        return DecideResult(True, "recorded", f"Recorded. Nothing has changed yet. The change starts at {stamp(start)} UTC. You can cancel until then.", plan)

    def withdraw(self, principal: Principal, plan_id: str, nonce: str) -> DecideResult:
        now = self.clock()
        try:
            plan = self.store.plan_get(plan_id)
            if plan is None:
                return DecideResult(False, "refused_state", "This request does not exist.")
            if not principal.has("approver") or principal.oid.lower() not in plan.approvers:
                return DecideResult(False, "refused_role", "I cannot take your OK on this request.")
            mine = next((d for d in self.store.decisions_of_plan(plan_id) if d.approver_oid == principal.oid), None)
            action = self.store.action_get(plan_id)
            if plan.state != "approved" or mine is None or mine.decision != "approve" or action is None:
                return DecideResult(False, "refused_state", "There is no approval of yours to cancel.", plan)
            if action.state != "queued" or (action.start_after and now >= parse(action.start_after)):
                return DecideResult(False, "refused_state", "The change has started. It cannot be cancelled.", plan)
            if not self.store.nonce_use(nonce, principal.oid, plan.plan_id):
                return DecideResult(False, "error", "This form is no longer valid. Open the link in the message again.", plan)
            self.store.action_put(_action_with(action, state="withdrawn", finished_at=stamp(now), result="Withdrawn before it started. Nothing changed."))
            plan = _plan_with(plan, state="withdrawn")
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "declined")
            return DecideResult(True, "withdrawn", "Withdrawn. Your approval is cancelled and the request is closed. Nothing has changed.", plan)
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing was changed. Try again in a few minutes.")

    def expire(self) -> list[PlanRecord]:
        """Closes the open plans whose time is over. Returns them."""
        now = self.clock()
        closed = []
        for plan in self.store.plans_open():
            after = self._expire_if_due(plan, now)
            if after.state == "expired":
                closed.append(after)
        return closed

    def create(self, case: CaseRecord, lead: Lead, approvers: tuple[str, ...]) -> PlanRecord | None:
        """The plan for a case, or None when no plan can be made (why_not says why). The case moves to awaiting_ok."""
        if why_not(case, lead, self.settings, self.store) is not None or not approvers:
            return None
        plan = build_plan(case, lead, approvers, self.clock(), self.settings)
        self.store.plan_put(plan)
        self.store.case_put(_with(case, status="awaiting_ok", plan_id=plan.plan_id, updated_at=stamp(self.clock())))
        return plan


def _words(state: str) -> str:
    return {"consumed": "closed: it ran", "declined": "declined", "withdrawn": "withdrawn", "approved": "approved and waiting to start", "failed": "closed: the change failed"}.get(state, state)


def _with(case: CaseRecord, **changes) -> CaseRecord:
    return replace(case, **changes)


def _plan_with(plan: PlanRecord, **changes) -> PlanRecord:
    return replace(plan, **changes)


def _action_with(action: ActionRecord, **changes) -> ActionRecord:
    return replace(action, **changes)