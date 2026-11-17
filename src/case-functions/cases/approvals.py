"""The approval loop: a plan is made for a case that a person may approve, the person answers it on a page, and the answer is recorded.

Nothing here changes Azure, and Meternaut holds no right to change Azure. An approval is made when the person signs in to Azure, and the change is made
with that person's own token (delegated.py and runner.py), so Azure checks the person's own rights. The plan is computed by code from the lead's typed
facts and never from a model's words. A finding about a resource that Meternaut may not change gets an advise plan: a person says whether it is worth acting on,
and the answer is recorded and changes nothing in Azure. A finding that a guard holds back gets one too, in the state held (`Approvals.settle`): nothing asks a person to approve it.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, replace
from typing import Callable, Sequence

from . import brief, switches, twopeople
from .decide import NO_MEASUREMENT
from .detectors import ADVISOR, Lead
from .families import digest as plan_digest
from .families import registry
from .families.azure import Azure
from .families.base import Env, Family, Stop, Unreadable
from .families.gates import ChangeScope, Gates
from .memory_store import parse, stamp, utc_now
from .models import (ADVICE_QUIET_DAYS, ADVISE, DECLINE_REASONS, GROUP_FACT, HELD, ActionRecord, CaseRecord, DecideResult, DecisionRecord, EscalationRecord, PlanRecord, Principal, Store, StoreError,
                     TwoPeopleRule)
from .roles import clean_text

# The answers that a person can give (a request that changes nothing in Azure takes all of them on the page; a change takes the sign-in for its approval). `confirm` is the first of two
# people on a change that needs two (cases/twopeople.py): it changes nothing and is taken on the page only.
ANSWERS = ("approve", "decline", "ask", "not_mine", "later", "confirm")
ADVICE_STATUSES = ("proposed", "needs_human")
# A person's time is the scarce thing: a request that gives nothing to decide with, or that comes in dozens, is noise. A finding that no measurement backs, that names no saving and that
# concerns a resource of under ADVICE_MIN_USD in 30 days is no request: it stays a case and an open question that the AIs look at again at the next investigation (cases/learning.py).
ADVICE_MIN_USD = 50.0
# What the History says about a finding that is not made into a request because it cannot say what to look at (brief.says_nothing): it stays a case, and the run counts it.
NOTHING_TO_SAY = "held back: nothing to say"
# What the History says about a finding of the investigation about a resource that an automation changed lately (an application or service identity that is not Meternaut's own): somebody else
# manages it, so no request is made, and the run counts it like the findings that say nothing (investigate.py AUTOMATION_DAYS).
MANAGED_BY_AUTOMATION = "held back: managed by an automation"
# And of one that asks to delete a resource when nobody looked up who changed it, or the look could not be made (the Watch that never looks one up is the older detectors'): an unread Activity Log
# shows nothing, and a deletion is not asked on nothing.
NOT_CHECKED = "held back: not checked who changed it"
# And of one that asks to delete a resource of the network that others do not share, when what depends on it was not checked to the end (cases/impact.py): nobody removes what was not looked at.
IMPACT_NOT_CHECKED = "held back: impact not checked"
# And of an open request that was made when a deletion could be asked on less than the rules ask for now: it is taken back when nobody has answered it.
RULES_CHANGED = "held back: Meternaut's rules changed"
HELD_BACK = {"automation": MANAGED_BY_AUTOMATION, "unchecked": NOT_CHECKED, "impact": IMPACT_NOT_CHECKED, "rules": RULES_CHANGED}  # the reason of cases/brief.py held_reason (and `rules`) -> the words of the History
# What the History says when a finding that a guard held back is held no longer (cases/upkeep.py released), and the words of each reason that it was held for.
RELEASED = "no longer held back"
LEFT_ALONE = "closed: a person marked it do-not-touch"
WAITING_FOR_PLACE = "held back: waiting for a free place"
HELD_WORDS = {**HELD_BACK, "nothing": NOTHING_TO_SAY, "waiting": WAITING_FOR_PLACE}
# A finding that a guard holds back is shown in a request of its own, in the state HELD (Approvals.settle): nothing asks a person to approve a change for it, and it takes no more than the
# answers that ask for nothing. It is no open request, so ADVICE_OPEN_MAX does not count it, no card is made for it, and the Decisions page and the letters of a request do not list it.
HELD_STATUSES = ("needs_human", "proposed")  # the statuses of the cases that wait with no request
HELD_CASES = 300  # the latest cases of each of those statuses that settle reads (the start page and cases/learning.py read the same number)
HELD_ANSWERS = 200  # the latest plans that settle looks at for the answers that people gave lately (the number that advise reads)
HELD_NEW = 50  # the most held requests that one Watch makes: a Watch that finds more makes the rest at the next one
HELD_NO_APPROVAL = "This finding is held back, so there is no request to approve. Nothing is approved."
# And no more than ADVICE_OPEN_MAX requests wait at the same time for a finding that the AIs did not settle (a finding that both AIs agree on and that code re-checked is not held by it):
# the first page of the start page. The rest wait as open questions, and a request is made for them when a place is free.
ADVICE_OPEN_MAX = 10
GROUP_CASES_READ = 200  # the latest cases that are read to find the groups whose requests are open
# The recommendations that may lead to a plan of a change (the family that matches picks among them: cases/families).
CHANGE_RECOMMENDATIONS = ("delete", "change")
PAUSED_MESSAGE = brief.PAUSED_CHANGES
PAUSED_ADVICE = brief.PAUSED_ADVICE


@dataclass(frozen=True)
class ApprovalSettings:
    change_scopes: tuple[ChangeScope, ...]  # the resource groups of Meternaut's own in which a plan is made and a change may be made: each in one subscription
    planted_tag: str = "meternaut-planted"

    @property
    def gates(self) -> Gates:
        return Gates(self.change_scopes, self.planted_tag)


def is_fixture(lead: Lead, settings: ApprovalSettings) -> bool:
    """A resource that Meternaut planted itself, in a group of its own where a change may be made (inside a scope, with the tag, on the planted list): the one kind of resource that is
    not held back for being new."""
    gates = settings.gates
    return gates.why_outside(lead.subscription_id, lead.resource_group) is None and gates.why_not_planted(lead.tags, lead.resource_type, lead.name) is None


def why_not(case: CaseRecord, lead: Lead, settings: ApprovalSettings, store: Store, family: Family | None = None) -> str | None:
    """None when a plan can be made for the case; otherwise the plain reason why not. The gates come in this order: what the case recommends, a family that matches, the scope, the
    planted tag and list, a person's do-not-touch note and an open plan."""
    if case.status != "proposed" or case.recommendation not in CHANGE_RECOMMENDATIONS:
        return "the case is not proposed for a change"
    if family is None and not registry.candidates(lead.detector, lead.resource_type, case.recommendation):
        return "Meternaut has no change for this kind of resource"
    outside = settings.gates.why_outside(lead.subscription_id, lead.resource_group)
    if outside is not None:
        return outside
    not_planted = settings.gates.why_not_planted(lead.tags, lead.resource_type, lead.name)
    if not_planted is not None:
        return not_planted
    try:
        if lead.resource_id.lower() in store.do_not_touch():
            return "a person marked the resource do-not-touch"
        if any(p.resource_id.lower() == lead.resource_id.lower() for p in store.plans_open()):
            return "a plan for this resource is open already"
    except StoreError:
        return "the store could not be read"
    return None


def why_not_ask(case: CaseRecord) -> str | None:
    """None when a finding gives a person something to decide with; otherwise the plain reason why not. Only a finding that no measurement backs (decide.NO_MEASUREMENT), that names no
    saving and whose resource cost under ADVICE_MIN_USD in 30 days is held back: the AIs could not measure anything and nothing is at stake that a person can weigh."""
    if NO_MEASUREMENT not in case.objections:
        return None
    if (case.saving_usd_month or 0) > 0 or brief.advisor_saving(case) is not None or (case.cost_usd_30d or 0) >= ADVICE_MIN_USD:
        return None
    return "no measurement backs the finding, it names no saving, and the resource cost little"


def build_plan(case: CaseRecord, lead: Lead, approvers: tuple[str, ...], now: dt.datetime, settings: ApprovalSettings,
               new_id: Callable[[], str] = lambda: uuid.uuid4().hex, family: Family | None = None, facts: dict | None = None, rule: TwoPeopleRule | None = None) -> PlanRecord:
    """The plan of a change, written by code: the family decides its text, its target and its preconditions from the lead's typed facts and the case's cost lines; the rest of the record
    is the same for every family. The rule of when a change needs two people (`rule`, off when it is None) decides the approval class. The digest is made last, over every field
    (families/digest.py). Raises ValueError when the family has no plan for this resource."""
    family = family or next(iter(registry.candidates(lead.detector, lead.resource_type, case.recommendation)), None)
    if family is None:
        raise ValueError("Meternaut has no change for this kind of resource")
    try:
        located = family.locate(lead.resource_id, settings.gates)
    except Stop as stop:
        raise ValueError(str(stop)) from stop
    planned = family.plan(case, lead, facts or {}, located, settings.gates)
    if isinstance(planned, str):
        raise ValueError(planned)
    saving = planned.saving_usd_month
    return plan_digest.sealed(PlanRecord(
        plan_id=new_id(), case_id=case.case_id, family=family.name, resource_id=lead.resource_id, resource_name=clean_text(lead.name, 120),
        resource_group=clean_text(lead.resource_group, 90), subscription_id=lead.subscription_id, code="", title=planned.title, what_changes=planned.what_changes,
        saving_usd_month=saving, waiting_costs_usd_day=round(saving / 30, 2) if saving else None, could_go_wrong=planned.could_go_wrong, undo=planned.undo,
        evidence_level=planned.evidence, approvers=approvers, created_at=stamp(now), expires_at="", state="open",
        approval_class=twopeople.CLASS if rule is not None and twopeople.applies(rule, family.name, saving) else "R2",
        preconditions=planned.preconditions, target=planned.target))


def build_advice(case: CaseRecord, approvers: tuple[str, ...], now: dt.datetime, settings: ApprovalSettings, new_id: Callable[[], str] = lambda: uuid.uuid4().hex, held: str = "") -> PlanRecord:
    """The plan that asks a person whether a finding is worth acting on. It changes nothing in Azure: the words are code's, and the figures are the case's own (what code computed from the bill lines that the
    finding names, decide.py). A finding that has no figure of its own but whose facts hold what Azure Advisor says takes Advisor's. `held` (a key of brief.HOLD_WORDS) makes it the request of a finding
    that a guard holds back: the state HELD, and the reason kept in the preconditions."""
    saving = case.saving_usd_month if (case.saving_usd_month or 0) > 0 else brief.advisor_saving(case)
    by_advisor = case.detector == ADVISOR  # Azure Advisor's own recommendation, made by code: no AI looked at it
    judged = ("Judged: no AI looked at it. It is Azure Advisor's own recommendation, and Meternaut has not checked it." if by_advisor else
              "Judged: a check by code holds it back from a request, so nobody was asked to approve anything." if held else
              "Judged: two AI reviewers agree that this looks wasted, and code checked again the numbers that the first one cited." if case.status == "proposed" else
              "Judged: the AI reviewers did not settle it, or a check by code held it back, so a person has to decide.")
    return plan_digest.sealed(PlanRecord(
        plan_id=new_id(), case_id=case.case_id, family=ADVISE, resource_id=case.resource_id, resource_name=clean_text(case.resource_name, 120),
        resource_group=clean_text(case.resource_group, 90), subscription_id=case.subscription_id, code="",
        title=brief.headline_of(ADVISE, case.resource_name, case.resource_group, case.resource_type, case.recommendation, together=brief.group_of(case), case=case),
        what_changes=brief.ADVICE_CHANGE,
        saving_usd_month=saving, waiting_costs_usd_day=round(saving / 30, 2) if saving else None, could_go_wrong=brief.acting_risk(case).text, undo=brief.ADVICE_UNDO,
        evidence_level=judged + " Not measured yet: the saving, which cost lines confirm after a change.", approvers=approvers, created_at=stamp(now), expires_at="",
        state=HELD if held else "open", approval_class="R1", preconditions={"family": ADVISE, "caseStatus": case.status, **({"source": ADVISOR} if by_advisor else {}), **({HELD: held} if held else {})}))


def about_the_same(plan: PlanRecord, case: CaseRecord) -> bool:
    """Whether a request is about what a case is about: the same resource, but for an Advisor recommendation about a whole subscription the same case (many of them are about one subscription)."""
    if case.detector == ADVISOR and brief.scope_of_case(case) == "subscription":
        return plan.case_id == case.case_id
    return plan.resource_id.lower() == case.resource_id.lower()


class Approvals:
    """The Decider that the pages call, and the rest of the loop around a plan."""

    def __init__(self, store: Store, settings: ApprovalSettings, clock: Callable[[], dt.datetime] = utc_now, reader: Azure | None = None) -> None:
        # `reader` reads a resource to write the plan of a family that needs facts from Azure (a machine's size, a disk's tier): the Watch's own reader, with a list of calls that holds
        # reads only and only the resource groups of the change scopes. Without it, only a family that needs no read makes a plan, and every other finding gets the advise plan.
        self.store, self.settings, self.clock, self.reader = store, settings, clock, reader

    def _set_case(self, case_id: str, status: str) -> None:
        case = self.store.case_get(case_id)
        if case is not None and case.status != status:
            self.store.case_put(_with(case, status=status, updated_at=stamp(self.clock())))

    def _gate(self, principal: Principal, plan_id: str, decision: str, code: str, now: dt.datetime) -> tuple[PlanRecord | None, DecideResult | None]:
        """The checks that every answer shares, in this order. Returns the plan, or the refusal. It records nothing and uses no one-time token."""
        if decision not in ANSWERS:
            return None, DecideResult(False, "error", "That answer is not one of the answers on the page.")
        plan = self.store.plan_get(plan_id)
        if plan is None:
            return None, DecideResult(False, "refused_state", "This request does not exist. Nothing is approved.")
        advice = plan.family == ADVISE
        # A change is approved by an approver. An advise plan only records an opinion, so the owner may answer it too; either way the person has to be named on the plan. The one other person who may answer
        # advice is an escalation contact, the last link of the ladder (cases/escalation.py): a request that nobody answers comes to them.
        if not ((principal.has("approver") or (advice and principal.has("owner"))) and principal.oid.lower() in {a.lower() for a in plan.approvers}) and not (advice and principal.has("escalation")):
            return None, DecideResult(False, "refused_role", "I cannot take your OK on this request.")
        if plan.state == "expired":  # the stored word for a request that Meternaut took back: no clock ends a request (AGENTS.md rule 38)
            return None, DecideResult(False, "expired", "Meternaut took this request back, so it cannot be answered. Nothing has changed.", plan)
        if plan.state not in ("open", HELD):
            return None, DecideResult(False, "refused_state", f"This request is {_words(plan.state)}. Nothing more can be recorded.", plan)
        if plan.state == HELD and decision in ("approve", "confirm"):
            return None, DecideResult(False, "refused_state", HELD_NO_APPROVAL, plan)
        if decision in ("approve", "confirm") and switches.pulled(self.store, *(("all",) if advice else ("all", "changes"))):  # no change is made for advice, so only the full stop holds it
            return None, DecideResult(False, "refused_paused", PAUSED_ADVICE if advice else PAUSED_MESSAGE, plan)
        if (code or "").strip().upper() != plan.code:
            return None, DecideResult(False, "refused_code", "This request changed. Nothing is approved. A new message will bring the new request and its code.")
        return plan, None

    def decide(self, principal: Principal, plan_id: str, decision: str, code: str, nonce: str, note: str = "", reason: str = "") -> DecideResult:
        """An answer that changes nothing in Azure: decline, a question, "not mine", "later", the confirmation that is the first of two people on a change that needs two, and the answer
        "worth acting on" of an advise plan (sent as approve). The approval of a change is made at the person's sign-in to Azure (delegated.py)."""
        now = self.clock()
        try:
            return self._decide(principal, plan_id, decision, code, nonce, clean_text(note, 300), now, reason)
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing is approved. Try again in a few minutes.")

    def _decide(self, principal: Principal, plan_id: str, decision: str, code: str, nonce: str, note: str, now: dt.datetime, reason: str = "") -> DecideResult:
        if decision == "approve":
            known = self.store.plan_get(plan_id)
            if known is None or known.family != ADVISE:
                return DecideResult(False, "error", "A change is approved on the page of its request, not here. Nothing is approved.")
        plan, refusal = self._gate(principal, plan_id, decision, code, now)
        if refusal is not None or plan is None:
            return refusal or DecideResult(False, "error", "")
        if decision == "confirm":
            return self._confirm(principal, plan, nonce, note, now)
        if not self.store.nonce_use(nonce, principal.oid, plan.plan_id):
            return DecideResult(False, "error", "This form is no longer valid. Open the link in the message again. Nothing is approved.", plan)
        record = DecisionRecord(plan_id=plan.plan_id, approver_oid=principal.oid, approver_name=clean_text(principal.name, 80), decision=decision,
                                at=stamp(now), plan_code=plan.code, note=note, reason=reason if decision == "decline" and reason in DECLINE_REASONS else "")
        if not self.store.decision_put(record):
            return DecideResult(False, "duplicate", "You answered this request already. Your answer stands.", plan)
        if decision == "ask":
            return DecideResult(True, "asked", "Recorded with your name. It approves nothing. The request stays open.", plan)
        if decision == "later":
            if plan.state == HELD:  # a held finding has no request that can be put off, and nobody to pass it on to
                return DecideResult(True, "later", "Noted. Nothing is approved. The finding stays held back, in your list.", plan)
            self._ladder(plan, "snooze", principal, now)
            return DecideResult(True, "later", "Noted. Nothing is approved. The request stays open, in your list. If nobody answers it, it goes on to the next person.", plan)
        if decision == "decline":
            plan = _plan_with(plan, state="declined", **_answered(plan, now))
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "declined")
            return DecideResult(True, "declined", "Declined. Nothing has changed.", plan)
        if decision == "approve":  # only the answer of an advise plan gets here: worth acting on, and nothing is changed in Azure
            plan = _plan_with(plan, state="consumed")
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "acknowledged")
            return DecideResult(True, "acknowledged", "Recorded: worth acting on. Nothing was changed in Azure.", plan)
        if plan.family == ADVISE and plan.state != HELD:  # nobody's answer ends a request that is passed on: it goes to the next person at once, and stays open (cases/escalation.py)
            self._ladder(plan, "pass", principal, now)
            return DecideResult(True, "not_mine", "Recorded: this is not yours. Meternaut passes the request on to the next person. Nothing is approved.", plan)
        plan = _plan_with(plan, state="withdrawn", **_answered(plan, now))
        self.store.plan_put(plan)
        self._set_case(plan.case_id, "needs_human")
        return DecideResult(True, "not_mine", "Recorded: this resource is not yours. Nothing is approved.", plan)

    def _ladder(self, plan: PlanRecord, kind: str, principal: Principal, now: dt.datetime) -> None:
        """Keeps a put-off ("later") or a pass-on ("not mine") of a person for the ladder of the request (cases/escalation.py): the ladder reads it, and the page shows it."""
        count = sum(1 for r in self.store.escalations_of(plan.plan_id) if r.kind == kind)
        self.store.escalation_claim(EscalationRecord(plan.plan_id, kind, count + 1, stamp(now), who=(principal.oid,), names=(clean_text(principal.name, 80),)))

    def _confirm(self, principal: Principal, plan: PlanRecord, nonce: str, note: str, now: dt.datetime) -> DecideResult:
        """The first of two people on a change that needs two (cases/twopeople.py): records that this person confirms this exact plan, bound to its code and its digest. It changes nothing
        in Azure and needs no sign-in to it: the change is made by a second person, who approves the plan with their own sign-in. Refused for a plan that needs one person only, for a plan
        whose digest is not the one that its fields give, for a request that fewer than two people can approve, and for a plan that somebody confirmed already."""
        if not twopeople.needs(plan):
            return DecideResult(False, "refused_state", "This request does not need a second person, so there is nothing to confirm. Nothing was recorded.", plan)
        problem = plan_digest.problem(plan, plan.digest)
        if problem:
            return DecideResult(False, "refused_code", plan_digest.refusal(problem), plan)
        found = twopeople.standing(plan, self.store.decisions_of_plan(plan.plan_id), principal.oid)
        if found.stage == "alone":
            return DecideResult(False, "refused_state", twopeople.ALONE, plan)
        if found.stage == "mine":
            return DecideResult(False, "duplicate", "You confirmed this request already. Your confirmation stands.", plan)
        if found.stage == "second":
            return DecideResult(False, "refused_state", f"{found.by} confirmed this request already. A second person approves it now, so nothing more is needed here. Nothing was recorded.", plan)
        if not self.store.nonce_use(nonce, principal.oid, plan.plan_id):
            return DecideResult(False, "error", "This form is no longer valid. Open the link in the message again. Nothing is approved.", plan)
        record = DecisionRecord(plan_id=plan.plan_id, approver_oid=principal.oid, approver_name=clean_text(principal.name, 80), decision="confirm", at=stamp(now), plan_code=plan.code,
                                note=note, plan_digest=plan.digest)
        if not self.store.decision_put(record):
            return DecideResult(False, "duplicate", "You answered this request already. Your answer stands.", plan)
        return DecideResult(True, "confirmed", "Recorded: you confirmed this request. It changes nothing. A second person has to approve it.", plan)

    def check_approve(self, principal: Principal, plan_id: str, code: str) -> tuple[PlanRecord | None, DecideResult | None]:
        """The checks before an approval is recorded, without a one-time token: the person, the plan's state and expiry, the switches and the plan code, and for a change that needs two
        people a confirmation of this exact plan by somebody else."""
        try:
            return self._second(*self._no_advice(*self._gate(principal, plan_id, "approve", code, self.clock())), principal)
        except StoreError:
            return None, DecideResult(False, "error", "I cannot reach my records right now. Nothing is approved. Try again in a few minutes.")

    def check_form(self, principal: Principal, plan_id: str, code: str, nonce: str) -> tuple[PlanRecord | None, DecideResult | None]:
        """The checks of the approve form, in the order of every other answer: the person, the plan, the switches, the plan code, for a change that needs two people the confirmation
        of somebody else, and then the one-time token."""
        try:
            plan, refusal = self._second(*self._no_advice(*self._gate(principal, plan_id, "approve", code, self.clock())), principal)
            if refusal is not None or plan is None:
                return None, refusal or DecideResult(False, "error", "")
            if not self.store.nonce_use(nonce, principal.oid, plan.plan_id):
                return None, DecideResult(False, "error", "This form is no longer valid. Open the link in the message again. Nothing is approved.", plan)
            return plan, None
        except StoreError:
            return None, DecideResult(False, "error", "I cannot reach my records right now. Nothing is approved. Try again in a few minutes.")

    def _second(self, plan: PlanRecord | None, refusal: DecideResult | None, principal: Principal) -> tuple[PlanRecord | None, DecideResult | None]:
        """A change that needs two people is approved only by a person who did not confirm it, after a confirmation of this exact plan (cases/twopeople.py)."""
        if plan is not None and refusal is None and twopeople.needs(plan):
            text = twopeople.problem(plan, self.store.decisions_of_plan(plan.plan_id), principal.oid)
            if text:
                return None, DecideResult(False, "refused_state", text, plan)
        return plan, refusal

    @staticmethod
    def _no_advice(plan: PlanRecord | None, refusal: DecideResult | None) -> tuple[PlanRecord | None, DecideResult | None]:
        """An advise plan makes no change in Azure, so there is no sign-in to Azure for it: it is answered on its page. A plan of a change has to be sealed: its digest is there and is the
        one that its fields give (cases/families/digest.py)."""
        if plan is not None and plan.family == ADVISE:
            return None, DecideResult(False, "refused_state", "This request makes no change in Azure, so there is no change to approve. Answer it on its page. Nothing is approved.", plan)
        if plan is not None and refusal is None:
            problem = plan_digest.problem(plan, plan.digest)
            if problem:
                return None, DecideResult(False, "refused_code", plan_digest.refusal(problem), plan)
        return plan, refusal

    def check_stepup(self, principal: Principal, plan_id: str, code: str, resource_id: str) -> tuple[PlanRecord | None, ActionRecord | None, DecideResult | None]:
        """The checks before the change is tried again, after the approver's extra sign-in check: the plan is approved (not open: the approval is recorded already), with this
        code and this resource, this person's approval is recorded, the action of the plan waits in the queue for that check, and the switches are not pulled.

        Returns the plan and the action, or the refusal. It records nothing and uses no one-time token: the state of the sign-in was used up when the person came back."""
        try:
            return self._stepup(principal, plan_id, code, resource_id)
        except StoreError:
            return None, None, DecideResult(False, "error", "I cannot reach my records right now. Nothing was changed.")

    def _stepup(self, principal: Principal, plan_id: str, code: str, resource_id: str) -> tuple[PlanRecord | None, ActionRecord | None, DecideResult | None]:
        plan = self.store.plan_get(plan_id)
        if plan is None:
            return _refused_stepup("refused_state", "This request does not exist. Nothing was changed.")
        if not principal.has("approver") or principal.oid.lower() not in {a.lower() for a in plan.approvers}:
            return _refused_stepup("refused_role", "I cannot take your OK on this request.")
        if plan.state != "approved":
            return _refused_stepup("refused_state", f"This request is {_words(plan.state)}. Nothing more can be recorded.", plan)
        if switches.pulled(self.store, "all", "changes"):
            return _refused_stepup("refused_paused", PAUSED_MESSAGE, plan)
        if (code or "").strip().upper() != plan.code or plan.resource_id != resource_id:
            return _refused_stepup("refused_code", "This request changed. Nothing was changed. A new message will bring the new request and its code.", plan)
        mine = principal.oid.lower()
        if not any(d.decision == "approve" and d.plan_code == plan.code and d.plan_digest == plan.digest and d.approver_oid.lower() == mine for d in self.store.decisions_of_plan(plan_id)):
            return _refused_stepup("refused_state", "Your OK on this request is not recorded. Nothing was changed.", plan)
        action = self.store.action_get(plan_id)
        if action is None or action.plan_id != plan.plan_id or action.state != "queued" or not action.step_up:
            return _refused_stepup("refused_state", "The change of this request does not wait for an extra sign-in check. Nothing was changed.", plan)
        return plan, action, None

    def close_waiting(self, plan: PlanRecord, action: ActionRecord, text: str) -> ActionRecord:
        """The approved change that waited for the approver's extra sign-in check will not be made: the action and the plan fail, and the case with them. Nothing was changed."""
        failed = replace(action, state="failed", result=text, error=text, finished_at=stamp(self.clock()))
        self.store.plan_put(_plan_with(plan, state="failed"))  # the plan first: if the next write fails, the timer still closes the action that is queued
        self.store.action_put(failed)
        self._set_case(plan.case_id, "failed")
        return failed

    def reopen(self, plan: PlanRecord, action: ActionRecord, text: str) -> ActionRecord:
        """A check right before the change refused it, and nothing was written: the approval is not used, and the request is open again, as it was before the person approved it.

        The action stays as the record of the try, withdrawn, with the reason in plain words; a new approval takes its place (`Store.action_claim`). The person's approval is taken back
        (`Store.decision_release`: a confirmation of the first of two people stays), the plan is open and the case waits for an OK again. A new approval is a new one: it goes through the form
        and the sign-in once more, with a one-time token of its own, and it is bound to the digest of the plan as the plan is then; the tokens of the try that was refused were used up, and
        a plan that changed since has another digest, which no earlier approval fits.

        The action is written first, and the plan last. If a write fails between them, the plan stays approved with a withdrawn action, which the timer finishes (`runner.tick` calls this
        again: every step is the same when it is repeated). Returns the withdrawn action."""
        withdrawn = replace(action, state="withdrawn", result=text, error=None, finished_at=stamp(self.clock()))
        self.store.action_put(withdrawn)
        for decision in self.store.decisions_of_plan(plan.plan_id):
            if decision.decision == "approve":
                self.store.decision_release(plan.plan_id, decision.approver_oid)
        self.store.plan_put(_plan_with(plan, state="open"))
        self._set_case(plan.case_id, "awaiting_ok")
        return withdrawn

    def record_approval(self, principal: Principal, plan: PlanRecord, note: str) -> tuple[DecideResult, ActionRecord | None]:
        """Records the approval of a person who has signed in to Azure, and the action that the change is made under. The change itself is made by the caller.

        The action of a plan is claimed first, and once: of two approvers who answer at the same moment (or one person in two windows) only one records
        an approval and makes the change, and the other records nothing. A change that needs two people is refused here once more unless a confirmation of this exact plan by somebody
        else is recorded: the one place where the approval is written does not rely on the checks before it."""
        now = self.clock()
        claimed = False
        problem = plan_digest.problem(plan, plan.digest)
        if problem:
            return DecideResult(False, "refused_code", plan_digest.refusal(problem), plan), None
        try:
            if switches.pulled(self.store, "all", "changes"):
                return DecideResult(False, "refused_paused", PAUSED_MESSAGE, plan), None  # the switch can be pulled while the person signs in
            action = ActionRecord(plan_id=plan.plan_id, case_id=plan.case_id, family=plan.family, resource_id=plan.resource_id, state="queued",
                                  queued_at=stamp(now), correlation_id=uuid.uuid4().hex, plan_digest=plan.digest)
            if not self.store.action_claim(action):
                return DecideResult(False, "refused_state", "This request is being approved at this moment, by you in another window or by somebody else. "
                                                            "Nothing was changed by this answer.", plan), None
            claimed = True
            if twopeople.needs(plan):
                # The last look, after the claim: the confirmation of somebody else must be there for this exact plan right now (a person may have withdrawn theirs while this one signed in).
                text = twopeople.problem(plan, self.store.decisions_of_plan(plan.plan_id), principal.oid)
                if text:
                    self.store.action_release(plan.plan_id)
                    return DecideResult(False, "refused_state", text, plan), None
            record = DecisionRecord(plan_id=plan.plan_id, approver_oid=principal.oid, approver_name=clean_text(principal.name, 80), decision="approve",
                                    at=stamp(now), plan_code=plan.code, note=clean_text(note, 300), plan_digest=plan.digest)
            if not self.store.decision_put(record):
                self.store.action_release(plan.plan_id)  # this person's earlier answer stands; the claim must not block another approver
                return DecideResult(False, "duplicate", "You answered this request already. Your answer stands. Nothing has changed.", plan), None
            plan = _plan_with(plan, state="approved")
            self.store.plan_put(plan)
            self._set_case(plan.case_id, "approved")
            return DecideResult(True, "recorded", "Recorded.", plan), action
        except StoreError:
            if claimed:
                try:
                    self.store.action_release(plan.plan_id)  # a claim that no change follows must not block the next try
                except StoreError:
                    pass
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing was changed. Try again in a few minutes.", plan), None

    def supersede(self) -> list[PlanRecord]:
        """Takes back, with the reason `group` (stored as expired, ending now), the open advice requests of the resources that an open group request stands for, other than the group's own, and the
        request of a group that a fresher request of a group stands for (the group changed its first resource): the first version asked about each resource on its own, and the group asks once. A plan
        of a change and an answered plan are never touched. Returns the plans that it took back."""
        try:
            open_plans = [plan for plan in self.store.plans_open() if plan.family == ADVISE and plan.state == "open"]
            waiting = {plan.case_id for plan in open_plans}
            groups: set[str] = set()
            covered: set[str] = set()
            members_of: dict[str, set[str]] = {}
            for case in self.store.cases_recent(GROUP_CASES_READ):
                together = case.facts.get(GROUP_FACT) if isinstance(case.facts, dict) else None
                if isinstance(together, dict):
                    groups.add(case.case_id)
                    members = together.get("members")
                    if case.case_id in waiting and isinstance(members, list):
                        covered.update(f"k{member}" for member in members if isinstance(member, str))
                        members_of[case.case_id] = {f"k{member}" for member in members if isinstance(member, str)}
            closed = []
            for plan in open_plans:
                fresher = any(other.plan_id != plan.plan_id and other.created_at > plan.created_at and len(members_of.get(plan.case_id, set()) & members_of.get(other.case_id, set())) * 2 > len(members_of.get(plan.case_id, set()))
                              for other in open_plans)  # a later request of a group that shares most of its members: the finding changed its first resource, and the fresher request stands for it now
                if (plan.case_id in covered and plan.case_id not in groups) or fresher:
                    plan = self.store.plan_get(plan.plan_id)  # read again: a person may have answered it since the list was read
                    if plan is None or plan.state != "open" or self.store.decisions_of_plan(plan.plan_id):
                        continue  # a person who put it off or asked about it has answered it
                    plan = _plan_with(plan, state="expired", expires_at=stamp(self.clock()), preconditions={**(plan.preconditions or {}), "takenBack": "group"})  # the field keeps the time of the end
                    self.store.plan_put(plan)
                    self._set_case(plan.case_id, "expired")
                    closed.append(plan)
            return closed
        except StoreError:
            return []

    def _own_group(self, case: CaseRecord) -> bool:
        """Whether the case is about something in a group of Meternaut's own where a change may be made: the waste that it planted lives there, and the rules about asking to delete leave it alone."""
        return self.settings.gates.why_outside(case.subscription_id, case.resource_group) is None

    def held_why(self, case: CaseRecord) -> str:
        """Why no request is made for a case (cases/brief.py held_reason), whichever detector or AI made it, or "" when none is held. The one place that every path to an advise plan passes."""
        return "" if self._own_group(case) else brief.held_reason(case, self.clock())

    def hold_back_empty(self) -> list[tuple[PlanRecord, CaseRecord]]:
        """Takes back the open advice requests of the findings that cannot say what to look at (brief.says_nothing), that the rules of today hold back (held_why) or that were made when a deletion
        could be asked on less than they ask for now (brief.made_under_old_rules), when nobody has answered them: no request is made for such a finding, and one that was made before is closed, as
        expired and ending now, like the requests that supersede() takes back, and the plan keeps why (`preconditions["takenBack"]`, written with its end: the page, the letter and the card say so in
        words, and a case that is judged again cannot lose it). The case is not touched: it keeps its status (a finding that no person has seen). A request that a person put off or asked about is
        theirs and stays, and so is a change that is running or done. Returns the plans that it closed, each with its case."""
        try:
            closed: list[tuple[PlanRecord, CaseRecord]] = []
            for plan in [p for p in self.store.plans_open() if p.family == ADVISE and p.state == "open"]:
                case = self.store.case_get(plan.case_id)
                why = "" if case is None else self.held_why(case) or ("rules" if not self._own_group(case) and brief.made_under_old_rules(case, plan) else "")
                if case is None or not (why or brief.says_nothing(case)):
                    continue
                fresh = self.store.plan_get(plan.plan_id)  # read again: a person may have answered it since the list was read
                if fresh is None or fresh.state != "open" or self.store.decisions_of_plan(fresh.plan_id):
                    continue
                fresh = _plan_with(fresh, state="expired", expires_at=stamp(self.clock()), preconditions={**(fresh.preconditions or {}), "takenBack": why or "nothing"})
                self.store.plan_put(fresh)
                closed.append((fresh, case))
            return closed
        except StoreError:
            return []

    def _guard(self, case: CaseRecord) -> str:
        """The reason (a key of brief.HOLD_WORDS) that a guard holds a finding back now, or "" when none does: a rule of brief.held_reason, or a finding that cannot say what to look at."""
        return self.held_why(case) or ("nothing" if brief.says_nothing(case) else "")

    def settle(self, approvers: tuple[str, ...]) -> list[tuple[PlanRecord, CaseRecord | None]]:
        """Keeps the request of each finding that a guard holds back (state HELD, brief.held_of): a person sees the finding with its figure, why no request was made, what the guard needs and who may
        know, and may ask, say that it is not theirs, put it off or say that it is not worth it. It asks for no approval and changes nothing in Azure. A held request is made for a finding that waits
        with no request (status needs_human or proposed, and no request open for it, nobody has answered it lately, nobody marked it do-not-touch, and what is at stake is worth a person's time,
        approvals.why_not_ask): when a guard holds it back (brief.held_reason, nothing to say), or when its request was taken back because the rules changed. At most HELD_NEW are made at a time, and none
        when nobody can answer.

        A held request is closed when its finding is not one that waits any more (a person answered it, it was dropped, or a request or a change was made), when a request is open for the resource, when a
        person marked the resource do-not-touch (`left-alone`), or when the finding was judged again, no guard holds it back now and nobody is to be asked (little is at stake, or a person answered it
        lately). When the finding was judged again and no guard holds it back, but no request exists for it (the places for requests are full), the request stays, with the reason `waiting`, until a real
        request exists: the finding is then asked about as any other, by the normal path, and the held one ends. A guard that ends by itself (an automation that stopped changing the resource) does not
        close it: only a judgment does, with the facts of that day. A reason that changed is kept, and so is the figure of the case. Returns the requests that it closed, each with its case; it makes no
        History line (cases/upkeep.py does, and counts none of them as held back)."""
        try:
            now = self.clock()
            open_plans = self.store.plans_open()
            silenced = {key.lower() for key in self.store.do_not_touch()}
            quiet = now - dt.timedelta(days=ADVICE_QUIET_DAYS)
            answered = [p for p in self.store.plans_recent(HELD_ANSWERS) if p.family == ADVISE and p.state in ("declined", "consumed", "withdrawn") and parse(p.created_at) >= quiet]
            held: dict[str, PlanRecord] = {}
            for plan in self.store.plans_held():  # newest first
                if plan.case_id in held:
                    self._release(plan, now, "released")  # a second request for one case (two Watches at once made it): the newest stays
                else:
                    held[plan.case_id] = plan
            released: list[tuple[PlanRecord, CaseRecord | None]] = []
            for case_id, plan in held.items():
                case = self.store.case_get(case_id)
                how = ""  # why the request ends, when it does
                if case is None or case.status not in HELD_STATUSES or any(about_the_same(open_plan, case) for open_plan in open_plans):
                    how = "released"
                elif case.resource_id.lower() in silenced:
                    how = "left-alone"
                else:
                    why = self._guard(case)
                    if not why and case.updated_at > plan.created_at:
                        # Judged again, and nothing holds it back now: the normal path asks about it, and the request ends when there is a real one. Until then it stays shown (the places for requests may be full),
                        # unless nobody is to be asked: little is at stake, or a person answered it lately.
                        why = "" if why_not_ask(case) is not None or any(about_the_same(p, case) for p in answered) else "waiting"
                        how = "" if why else "released"
                    if not how:
                        self._refresh(plan.plan_id, case, why)
                        if case.plan_id != plan.plan_id:
                            self.store.case_update(case.case_id, lambda kept, plan_id=plan.plan_id: _with(kept, plan_id=plan_id))
                if how:
                    fresh = self._release(plan, now, how)
                    if fresh is not None:
                        released.append((fresh, case))
            if not approvers:
                return released
            made = 0
            for status in HELD_STATUSES:
                for case in self.store.cases_recent(HELD_CASES, status):
                    if made >= HELD_NEW:
                        return released
                    if (case.case_id in held or case.resource_id.lower() in silenced or any(about_the_same(p, case) for p in (*open_plans, *answered, *held.values()))
                            or why_not_ask(case) is not None):
                        continue
                    why = self._guard(case)
                    if not why and case.plan_id:
                        before = self.store.plan_get(case.plan_id)
                        why = "rules" if brief.taken_back(before) == "rules" else ""
                    if not why:
                        continue
                    plan = build_advice(case, approvers, now, self.settings, held=why)
                    self.store.plan_put(plan)
                    self.store.case_update(case.case_id, lambda kept, plan_id=plan.plan_id: _with(kept, plan_id=plan_id))
                    held[case.case_id] = plan
                    made += 1
            return released
        except StoreError:
            return []

    def _release(self, plan: PlanRecord, now: dt.datetime, how: str) -> PlanRecord | None:
        """Closes a held request, as expired and ending now, with the reason that it ends (`how`: released, when nothing holds the finding back any more or it does not wait any more, or left-alone, when
        a person marked the resource do-not-touch). It is read again first: a person may have answered it since the list was read, and an answer is never taken back. Returns the plan that it closed, or None."""
        fresh = self.store.plan_get(plan.plan_id)
        if fresh is None or fresh.state != HELD:
            return None
        fresh = _plan_with(fresh, state="expired", expires_at=stamp(now), preconditions={**(fresh.preconditions or {}), "takenBack": how})
        self.store.plan_put(fresh)
        return fresh

    def _refresh(self, plan_id: str, case: CaseRecord, why: str) -> None:
        """Gives a held request that is still held what the case says now: the reason when it changed, and the figure (the page and the letter read the figure of the request, which the Watch
        judged earlier). It is read again first, and written only while it is still held: an answer that came in since is not undone."""
        fresh = self.store.plan_get(plan_id)
        if fresh is None or fresh.state != HELD:
            return
        saving = case.saving_usd_month if (case.saving_usd_month or 0) > 0 else brief.advisor_saving(case)
        changes: dict = {name: value for name, value in (("saving_usd_month", saving), ("waiting_costs_usd_day", round(saving / 30, 2) if saving else None)) if getattr(fresh, name) != value}
        if why and why != (fresh.preconditions or {}).get(HELD):
            changes["preconditions"] = {**(fresh.preconditions or {}), HELD: why}
        if changes:
            self.store.plan_put(_plan_with(fresh, **changes))

    def create(self, case: CaseRecord, lead: Lead, approvers: tuple[str, ...]) -> PlanRecord | None:
        """The plan for a case, or None when no plan can be made (why_not says why). The case moves to awaiting_ok.

        The model's recommendation only chooses among the families that match the resource (cases/families). Each of them that passes the gates reads what its plan needs from Azure with
        the reader (when it needs to) and writes the plan itself, in code; the first that has a plan wins. A family that cannot read, or finds the resource not as a plan needs it, makes none,
        and the finding gets the advise plan instead."""
        if not approvers:
            return None
        rule = self.store.rule_get()  # a store that cannot be read makes no plan now: the Watch tries again at its next run
        for family in registry.candidates(lead.detector, lead.resource_type, case.recommendation):
            if why_not(case, lead, self.settings, self.store, family) is not None:
                continue
            facts = self._facts(family, lead)
            if facts is None:
                continue
            try:
                plan = build_plan(case, lead, approvers, self.clock(), self.settings, family=family, facts=facts, rule=rule)
            except ValueError:
                continue
            self.store.plan_put(plan)
            self.store.case_put(_with(case, status="awaiting_ok", plan_id=plan.plan_id, updated_at=stamp(self.clock())))
            return plan
        return None

    def _facts(self, family: Family, lead: Lead) -> dict | None:
        """What the family reads to write its plan, or None when it cannot: there is no reader here, or Azure shows the resource as no plan of the family can use."""
        if not family.needs_reads(lead):
            return {}
        if self.reader is None:
            return None
        try:
            located = family.locate(lead.resource_id, self.settings.gates)
            return family.facts(Env(self.reader, self.settings.gates, self.store.do_not_touch, self.clock), lead, located)
        except (Stop, Unreadable):
            return None

    def advise(self, case: CaseRecord, approvers: tuple[str, ...]) -> PlanRecord | None:
        """The advise plan for a finding that a person has to look at and that Meternaut may not change: it makes no change in Azure, and the person's answer is recorded.

        None when the case is not a finding for a person (its status is not proposed or needs_human), when nobody can answer, when a person marked the resource do-not-touch,
        when a plan for the resource is open already (the case is linked to it when it is the case's own), or when a person answered an advise plan for the resource lately.
        None also when the finding is not worth a request (why_not_ask), when it cannot say what to look at (brief.says_nothing: NOTHING_TO_SAY, which the caller says in the History and counts),
        or when it needs a person only because the AIs did not settle it and ADVICE_OPEN_MAX requests wait already:
        the case is then an open question, and nothing is made for it until a place is free.
        The status of the case is left as it is while the plan is open: it still says what the AIs came to."""
        if case.status not in ADVICE_STATUSES or not approvers:
            return None
        try:
            if case.resource_id.lower() in self.store.do_not_touch():
                return None
            open_plans = self.store.plans_open()
            for plan in open_plans:
                if about_the_same(plan, case):
                    if plan.state == "open" and plan.case_id == case.case_id and case.plan_id != plan.plan_id:
                        self.store.case_put(_with(case, plan_id=plan.plan_id))
                    return None
            if why_not_ask(case) is not None or brief.says_nothing(case) or self.held_why(case):
                return None
            if places_full(case, open_plans):
                return None
            now = self.clock()
            quiet = now - dt.timedelta(days=ADVICE_QUIET_DAYS)
            for plan in self.store.plans_recent(200):
                if about_the_same(plan, case) and plan.family == ADVISE and plan.state in ("declined", "consumed", "withdrawn") and parse(plan.created_at) >= quiet:
                    return None
            plan = build_advice(case, approvers, now, self.settings)
            self.store.plan_put(plan)
            self.store.case_put(_with(case, plan_id=plan.plan_id, updated_at=stamp(now)))
            return plan
        except StoreError:
            return None

    def plan_for(self, case: CaseRecord, lead: Lead, approvers: tuple[str, ...]) -> PlanRecord | None:
        """The plan for a case that a person has to look at: the plan of a change when Meternaut may make one for it, else the advise plan."""
        if case.status == "proposed":
            plan = self.create(case, lead, approvers)
            if plan is not None:
                return plan
        return self.advise(case, approvers)


def places_full(case: CaseRecord, open_plans: Sequence[PlanRecord]) -> bool:
    """Whether no place is free for a request about this finding: ADVICE_OPEN_MAX requests wait already for findings that the AIs did not settle. Azure Advisor's own recommendations are neither held
    by the cap nor counted by it: they are claims with a figure, and the cap is for the findings that the AIs did not settle."""
    return case.status == "needs_human" and case.detector != ADVISOR and sum(
        1 for plan in open_plans if plan.family == ADVISE and plan.state == "open" and (plan.preconditions or {}).get("caseStatus") == "needs_human"
        and (plan.preconditions or {}).get("source") != ADVISOR) >= ADVICE_OPEN_MAX


def _answered(plan: PlanRecord, now: dt.datetime) -> dict:
    """What a held request keeps of an answer that closes it (declined, or "not mine"): the time of the answer in `created_at`, so that the quiet days of the finding count from the answer, as they do
    for a request that is answered within the days that it is open, and not from the day that the held request was made (it can be weeks old)."""
    return {"created_at": stamp(now)} if plan.state == HELD else {}


def _words(state: str) -> str:
    return {"consumed": "closed: it ran", "declined": "declined", "withdrawn": "withdrawn", "approved": "approved: its change is being made",
            "failed": "closed: the change failed", "expired": "taken back by Meternaut"}.get(state, state)


def _refused_stepup(kind: str, message: str, plan: PlanRecord | None = None) -> tuple[None, None, DecideResult]:
    return None, None, DecideResult(False, kind, message, plan)


def _with(case: CaseRecord, **changes) -> CaseRecord:
    return replace(case, **changes)


def _plan_with(plan: PlanRecord, **changes) -> PlanRecord:
    return replace(plan, **changes)