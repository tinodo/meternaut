"""The family advise, end to end: a finding that Meternaut may not change gets a request that a person answers.

The answer is recorded with the person's name and changes nothing in Azure. These tests run the real approvals over the store of memory, the real sign-in to Azure and the real
runner over a fake Azure, and the real pages, and they pin that no path from an advise plan reaches Azure. Everything in them is invented.
"""
import datetime as dt
import json
import re
import unittest
from dataclasses import replace

from support import APP_ROOT  # noqa: F401

from cases import brief
from cases.approvals import ADVICE_MIN_USD, ADVICE_OPEN_MAX, ADVICE_QUIET_DAYS, ANSWERS, Approvals, ApprovalSettings, why_not_ask
from cases.decide import NO_MEASUREMENT
from cases.delegated import Delegation, SigninSettings
from cases.detectors import Lead
from cases.families import registry
from cases.families.calls import KINDS
from cases.families.gates import ChangeScope
from cases.families.words import SHOWN
from cases.http import Client
from cases.learning import OpenQuestions
from cases.memory_store import MemoryStore, parse, stamp
from cases.models import (ADVISE, CASE_CLOSED, CASE_STATUSES, DECISIONS, DECLINE_REASONS, ActionRecord, CaseRecord, DecisionRecord, NoteRecord, Principal,
                          SwitchRecord)
from cases.runner import RunnerServices, change_calls, execute, tick
from cases.web import words
from test_runner import FakeAzure
from test_web_support import (MAYA, NOW, OPS, OWNER, STRANGER, SUB, TINO, VM, Console, FailingStore, make_advice_case, make_run)

CHANGE_GROUP = "meternaut-sc-rg"
SCOPES = (ChangeScope(SUB, CHANGE_GROUP),)
SETTINGS = ApprovalSettings(change_scopes=SCOPES, ttl_hours=72)
SIGNIN = SigninSettings("cccccccc-1111-4222-8333-444444444444", "dddddddd-1111-4222-8333-444444444444", "eeeeeeee-1111-4222-8333-444444444444", "console.example.test")
BOTH = Principal(TINO, "Tino", ("owner", "approver", "ops"))
APPROVER = Principal(MAYA, "Maya", ("approver",))
OWNER_ONLY = Principal(OWNER, "Olga", ("owner",))
OPS_ONLY = Principal(OPS, "Otto", ("ops",))
NAMED = (TINO, MAYA, OWNER)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += dt.timedelta(**kwargs)


def lead_of(case: CaseRecord) -> Lead:
    return Lead(detector=case.detector, resource_id=case.resource_id, resource_type=case.resource_type, name=case.resource_name, resource_group=case.resource_group,
                subscription_id=case.subscription_id, location="swedencentral", tags={}, managed_by="", facts={}, age_days=0)


def planted_disk(name="planted-disk-1") -> Lead:
    kind = "microsoft.compute/disks"
    return Lead(detector="orphan-managed-disk", resource_id=f"/subscriptions/{SUB}/resourceGroups/{CHANGE_GROUP}/providers/{kind}/{name}", resource_type=kind, name=name,
                resource_group=CHANGE_GROUP, subscription_id=SUB, location="swedencentral", tags={"meternaut-planted": "demo"}, managed_by="", facts={"diskState": "unattached"},
                age_days=0)


def case_of(item: Lead, **changes) -> CaseRecord:
    base = dict(case_id="k" + item.lead_id, resource_id=item.resource_id, resource_name=item.name, resource_type=item.resource_type, resource_group=item.resource_group,
                subscription_id=item.subscription_id, detector=item.detector, run_id="r1", status="proposed", recommendation="delete", confidence=0.9, summary="the model said so",
                updated_at=stamp(NOW), first_seen_at=stamp(NOW))
    base.update(changes)
    return CaseRecord(**base)


class Base(unittest.TestCase):
    """A finding about a virtual machine that needs a person, and the advise plan that asks the three people named in NAMED."""

    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.approvals = Approvals(self.store, SETTINGS, self.clock)
        self.case = make_advice_case(plan_id=None, updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(self.case)
        self.plan = self.approvals.advise(self.case, NAMED)
        self.assertIsNotNone(self.plan)

    def token(self, who, plan=None):
        return self.store.nonce_new(who.oid, (plan or self.plan).plan_id)

    def answer(self, who, decision, *, code=None, nonce=None, note="", reason="", plan=None):
        plan = plan or self.plan
        return self.approvals.decide(who, plan.plan_id, decision, plan.code if code is None else code, self.token(who, plan) if nonce is None else nonce, note, reason)

    def case_now(self):
        return self.store.case_get(self.case.case_id)

    def plan_now(self):
        return self.store.plan_get(self.plan.plan_id)

    def decisions(self):
        return self.store.decisions_of_plan(self.plan.plan_id)

    def pause(self, name):
        self.store.switch_put(SwitchRecord(name=name, paused=True))

    def change_plan(self):
        item = planted_disk()
        case = case_of(item)
        self.store.case_put(case)
        plan = self.approvals.create(case, item, NAMED)
        self.assertIsNotNone(plan)
        return plan


class TheVocabulary(unittest.TestCase):
    def test_the_new_status_and_the_new_answer_are_in_the_lists_that_the_records_are_checked_against(self):
        self.assertIn("acknowledged", CASE_STATUSES)
        self.assertIn("acknowledged", CASE_CLOSED)
        self.assertIn("later", DECISIONS)
        self.assertEqual(ANSWERS, ("approve", "decline", "ask", "not_mine", "later", "confirm"))
        self.assertEqual(set(ANSWERS), set(DECISIONS))
        self.assertEqual(ADVISE, "advise")

    def test_the_form_offers_exactly_the_reasons_that_a_decline_may_give(self):
        self.assertEqual({value for value, _ in words.DECLINE_REASON}, set(DECLINE_REASONS) | {""})
        self.assertEqual(set(brief.REASON_WORDS), set(DECLINE_REASONS))

    def test_advise_is_not_a_family_of_a_change(self):
        for known in (set(registry.names()), set(SHOWN), {kind.collection for kind in KINDS}, {kind.type for kind in KINDS}):
            self.assertNotIn(ADVISE, known)
        self.assertIsNone(registry.get(ADVISE))

    def test_every_answer_has_a_name_on_the_page_and_in_the_history(self):
        for decision in DECISIONS:
            self.assertIn(decision, words.DECISION)
        for kind in ("change", "advice"):
            self.assertEqual(set(words.ANSWER_LABEL[kind]), set(ANSWERS) - ({"confirm"} if kind == "advice" else set()), "advice changes nothing, so it has no second person")


class MakingTheAdvice(Base):
    def test_a_finding_that_needs_a_person_gets_one_open_plan_that_changes_nothing(self):
        plan = self.plan
        self.assertEqual((plan.family, plan.state, plan.approval_class, plan.approvers), (ADVISE, "open", "R1", NAMED))
        self.assertEqual(plan.preconditions, {"family": ADVISE, "caseStatus": "needs_human"})
        self.assertRegex(plan.code, r"^[0-9A-F]{8}$")
        self.assertEqual(parse(plan.expires_at) - parse(plan.created_at), dt.timedelta(hours=72))
        self.assertEqual((plan.what_changes, plan.could_go_wrong, plan.undo), (brief.ADVICE_CHANGE, brief.ADVICE_RISK, brief.ADVICE_UNDO))
        self.assertIn("Nothing changes in Azure", plan.what_changes)
        self.assertEqual((plan.resource_id, plan.resource_name, plan.resource_group, plan.case_id), (VM, "oversized-vm-1", "team-apps-rg", self.case.case_id))
        self.assertEqual(self.store.plan_get(plan.plan_id), plan)
        self.assertEqual(self.store.plans_open(), [plan])
        self.assertIsNone(self.store.action_get(plan.plan_id))

    def test_the_case_is_linked_to_the_plan_and_keeps_the_status_that_the_review_gave_it(self):
        case = self.case_now()
        self.assertEqual((case.plan_id, case.status), (self.plan.plan_id, "needs_human"))

    def test_the_figures_of_the_plan_are_the_cases_own_and_a_case_without_a_saving_has_none(self):
        self.assertEqual((self.plan.saving_usd_month, self.plan.waiting_costs_usd_day), (120.0, 4.0))
        for saving in (None, 0, -5.0):
            with self.subTest(saving=saving):
                store = MemoryStore(clock=self.clock)
                case = replace(self.case, saving_usd_month=saving)
                plan = Approvals(store, SETTINGS, self.clock).advise(case, NAMED)
                self.assertEqual((plan.saving_usd_month, plan.waiting_costs_usd_day), (None, None))

    def test_a_case_without_a_figure_of_its_own_takes_the_one_that_code_worked_out_for_the_data_that_nothing_reads_and_a_figure_of_its_own_stays(self):
        digest = {"days": 30, "billableGb": 100.0, "unreadGb": 60.0, "share": 0.6, "savingUsd": 48.0, "costUsd30d": 80.0, "runsRecorded": True, "more": 0, "unknown": 0,
                  "kinds": [{"kind": "Syslog", "gb": 60.0, "share": 0.6, "runs": 0}]}
        for own, found, expected in ((None, digest, (48.0, 1.6)), (0, digest, (48.0, 1.6)), (-5.0, digest, (48.0, 1.6)), (120.0, digest, (120.0, 4.0)),
                                     (None, {**digest, "savingUsd": 90.0}, (None, None)), (None, {**digest, "savingUsd": 0}, (None, None)), (None, {**digest, "savingUsd": "48"}, (None, None)),
                                     (None, {"missing": "volume"}, (None, None)), (None, "text", (None, None))):
            with self.subTest(saving=own, digest=found):
                store = MemoryStore(clock=self.clock)
                case = replace(self.case, saving_usd_month=own, cost_usd_30d=80.0, facts={"unread": found})
                plan = Approvals(store, SETTINGS, self.clock).advise(case, NAMED)
                self.assertEqual((plan.saving_usd_month, plan.waiting_costs_usd_day), expected)

    def test_a_case_that_the_ais_agreed_on_says_so_and_one_that_needs_a_person_says_that(self):
        self.assertTrue(self.plan.evidence_level.startswith("Judged: the AI reviewers did not settle it"))
        store = MemoryStore(clock=self.clock)
        proposed = replace(self.case, status="proposed")
        plan = Approvals(store, SETTINGS, self.clock).advise(proposed, NAMED)
        self.assertEqual(plan.preconditions["caseStatus"], "proposed")
        self.assertTrue(plan.evidence_level.startswith("Judged: two AI reviewers agree"))

    def test_only_a_case_that_a_person_has_to_look_at_gets_advice(self):
        for status in CASE_STATUSES:
            if status in ("proposed", "needs_human"):
                continue
            with self.subTest(status):
                store = MemoryStore(clock=self.clock)
                self.assertIsNone(Approvals(store, SETTINGS, self.clock).advise(replace(self.case, status=status), NAMED))
                self.assertEqual(store.plans, {})

    def test_nobody_to_ask_means_no_plan(self):
        store = MemoryStore(clock=self.clock)
        self.assertIsNone(Approvals(store, SETTINGS, self.clock).advise(self.case, ()))
        self.assertEqual(store.plans, {})

    def test_a_resource_that_a_person_marked_do_not_touch_gets_no_advice(self):
        store = MemoryStore(clock=self.clock)
        store.note_put(NoteRecord(note_id="n", oid=TINO, kind="do_not_touch", text="keep", scope_resource_id=VM, expires_at="2099-01-01T00:00:00Z"))
        self.assertIsNone(Approvals(store, SETTINGS, self.clock).advise(self.case, NAMED))

    def test_an_open_plan_for_the_resource_stops_a_second_one_and_links_the_case_that_it_belongs_to(self):
        self.assertIsNone(self.approvals.advise(self.case, NAMED), "the same finding again while the request is open")
        other = replace(self.case, case_id="case0003")
        self.assertIsNone(self.approvals.advise(other, NAMED), "a finding of another case for the same resource")
        self.assertEqual(len(self.store.plans), 1)
        self.store.case_put(replace(self.case, plan_id=None))
        self.assertIsNone(self.approvals.advise(replace(self.case, plan_id=None), NAMED))
        self.assertEqual(self.case_now().plan_id, self.plan.plan_id, "the case is linked to its own open plan again")

    def test_a_finding_that_a_person_answered_lately_is_not_put_to_them_again_for_thirty_days(self):
        self.assertEqual(ADVICE_QUIET_DAYS, 30)
        for decision, state in (("approve", "consumed"), ("decline", "declined"), ("not_mine", "withdrawn")):
            with self.subTest(decision):
                self.setUp()
                self.assertTrue(self.answer(BOTH, decision).ok)
                self.assertEqual(self.plan_now().state, state)
                self.clock.advance(days=ADVICE_QUIET_DAYS - 1)
                self.assertIsNone(self.approvals.advise(self.case, NAMED), "29 days after the answer")
                self.clock.advance(days=2)
                again = self.approvals.advise(self.case, NAMED)
                self.assertIsNotNone(again, "31 days after the answer")
                self.assertNotEqual(again.plan_id, self.plan.plan_id)

    def test_a_request_that_nobody_answered_is_made_again_at_once(self):
        self.clock.advance(hours=73)
        self.assertEqual(len(self.approvals.expire()), 1)
        again = self.approvals.advise(self.case, NAMED)
        self.assertIsNotNone(again)
        self.assertNotEqual(again.plan_id, self.plan.plan_id)
        self.assertEqual(again.state, "open")

    def test_a_store_that_cannot_be_read_means_no_plan_and_no_error(self):
        for name in ("do_not_touch", "plans_open", "plans_recent"):
            with self.subTest(name):
                broken = FailingStore(fail=(name,), clock=self.clock)
                self.assertIsNone(Approvals(broken, SETTINGS, self.clock).advise(self.case, NAMED))


class TheWorthOfARequest(unittest.TestCase):
    """A finding that gives a person nothing to decide with is no request, and no more than ADVICE_OPEN_MAX findings that the AIs did not settle wait at the same time. What is not
    asked stays a case and an open question that the AIs look at again."""

    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.approvals = Approvals(self.store, SETTINGS, self.clock)

    def finding(self, n=0, **changes) -> CaseRecord:
        """The finding of the live Watch that flooded the page: nothing measured, no saving, a resource of a few dollars."""
        base = dict(case_id=f"case-w{n}", resource_id=f"{VM}-{n}", resource_name=f"endpoint-{n}", saving_usd_month=None, cost_usd_30d=7.17, objections=(NO_MEASUREMENT,),
                    plan_id=None, confidence=0.55)
        base.update(changes)
        return make_advice_case(**base)

    def settled_not(self, count: int, **changes) -> None:
        for n in range(count):
            self.assertIsNotNone(self.approvals.advise(self.finding(n, cost_usd_30d=80.0, objections=("It may be in use.",), **changes), NAMED))

    def open_advice(self):
        return [p for p in self.store.plans.values() if p.family == ADVISE and p.state == "open"]

    def test_the_limits_are_the_ones_that_the_start_page_and_the_owner_know(self):
        self.assertEqual((ADVICE_MIN_USD, ADVICE_OPEN_MAX), (50.0, 10))

    def test_a_finding_that_nothing_backs_with_no_saving_and_a_cheap_resource_gets_no_request_and_stays_an_open_question(self):
        case = self.finding()
        self.assertIn("no measurement backs the finding", why_not_ask(case))
        self.store.case_put(case)
        self.assertIsNone(self.approvals.advise(case, NAMED))
        self.assertEqual(self.store.plans, {})
        kept = self.store.case_get(case.case_id)
        self.assertEqual((kept.status, kept.plan_id), ("needs_human", None))
        self.assertTrue(OpenQuestions(self.store, NOW).is_open(kept), "the Investigator is given it again by recall_open_questions")

    def test_a_saving_or_a_costly_resource_or_a_measurement_makes_it_a_request(self):
        for name, changes in (("a saving", dict(saving_usd_month=5.0)), ("a resource that cost enough", dict(cost_usd_30d=ADVICE_MIN_USD)),
                              ("a measurement behind it", dict(objections=("It may be in use.",))), ("a finding that both AIs agree on", dict(status="proposed", objections=()))):
            with self.subTest(name):
                self.setUp()
                case = self.finding(**changes)
                self.assertIsNone(why_not_ask(case))
                self.assertIsNotNone(self.approvals.advise(case, NAMED))

    def test_the_edges_of_the_worth_are_exact(self):
        for name, changes in (("just under the cost", dict(cost_usd_30d=ADVICE_MIN_USD - 0.01)), ("no cost known", dict(cost_usd_30d=None)), ("a saving of nothing", dict(saving_usd_month=0)),
                              ("a negative saving", dict(saving_usd_month=-3.0))):
            with self.subTest(name):
                self.assertIsNotNone(why_not_ask(self.finding(**changes)))

    def test_a_figure_that_code_worked_out_for_the_data_that_a_workspace_takes_in_and_nothing_reads_is_something_to_decide_with_even_for_a_cheap_resource(self):
        digest = {"days": 30, "billableGb": 100.0, "unreadGb": 60.0, "share": 0.6, "savingUsd": 12.0, "costUsd30d": 20.0, "runsRecorded": True, "more": 0, "unknown": 0,
                  "kinds": [{"kind": "Syslog", "gb": 60.0, "share": 0.6, "runs": 0}]}
        case = self.finding(cost_usd_30d=20.0, facts={"unread": digest})
        self.assertIsNone(why_not_ask(case))
        self.assertIsNotNone(self.approvals.advise(case, NAMED))
        for name, found in (("no figure", {"missing": "volume"}), ("a figure above the cost", {**digest, "savingUsd": 25.0}), ("a figure of nothing", {**digest, "savingUsd": 0})):
            with self.subTest(name):
                self.assertIsNotNone(why_not_ask(self.finding(cost_usd_30d=20.0, facts={"unread": found})))

    def test_plan_for_holds_the_same_finding_back(self):
        case = self.finding()
        self.assertIsNone(self.approvals.plan_for(case, lead_of(case), NAMED))
        self.assertEqual(self.store.plans, {})

    def test_no_more_requests_wait_for_findings_that_the_ais_did_not_settle_than_the_places(self):
        self.settled_not(ADVICE_OPEN_MAX)
        late = self.finding(99, cost_usd_30d=80.0, objections=("It may be in use.",))
        self.assertIsNone(self.approvals.advise(late, NAMED))
        self.assertEqual(len(self.open_advice()), ADVICE_OPEN_MAX)
        self.assertTrue(OpenQuestions(self.store, NOW).is_open(late), "it waits as an open question for a free place")

    def test_a_place_is_free_when_a_request_is_answered_or_over(self):
        self.settled_not(ADVICE_OPEN_MAX)
        for n, state in enumerate(("declined", "expired")):
            with self.subTest(state):
                late = self.finding(90 + n, cost_usd_30d=80.0, objections=("It may be in use.",))
                self.assertIsNone(self.approvals.advise(late, NAMED), "no place is free")
                self.store.plan_put(replace(self.open_advice()[0], state=state))
                self.assertIsNotNone(self.approvals.advise(late, NAMED))
                self.assertEqual(len(self.open_advice()), ADVICE_OPEN_MAX)

    def test_a_finding_that_both_ais_agree_on_is_not_held_by_the_places(self):
        self.settled_not(ADVICE_OPEN_MAX)
        agreed = self.finding(98, status="proposed", cost_usd_30d=80.0, objections=(), confidence=0.9)
        self.assertIsNotNone(self.approvals.advise(agreed, NAMED))
        self.assertEqual(len(self.open_advice()), ADVICE_OPEN_MAX + 1)

    def test_the_requests_for_findings_that_both_ais_agree_on_take_no_place_from_the_ones_that_nobody_settled(self):
        for n in range(ADVICE_OPEN_MAX + 2):
            self.assertIsNotNone(self.approvals.advise(self.finding(n, status="proposed", cost_usd_30d=80.0, objections=(), confidence=0.9), NAMED))
        self.assertEqual(len(self.open_advice()), ADVICE_OPEN_MAX + 2)
        for n in range(100, 100 + ADVICE_OPEN_MAX):
            self.assertIsNotNone(self.approvals.advise(self.finding(n, cost_usd_30d=80.0, objections=("It may be in use.",)), NAMED), "a place is free for the unsettled ones")
        self.assertIsNone(self.approvals.advise(self.finding(199, cost_usd_30d=80.0, objections=("It may be in use.",)), NAMED), "now the places of the unsettled ones are full")

    def test_the_plans_of_a_change_do_not_take_a_place(self):
        item = planted_disk()
        case = case_of(item)
        self.store.case_put(case)
        self.assertIsNotNone(self.approvals.create(case, item, NAMED))
        self.settled_not(ADVICE_OPEN_MAX - 1)
        self.assertIsNotNone(self.approvals.advise(self.finding(97, cost_usd_30d=80.0, objections=("It may be in use.",)), NAMED))

    def test_a_store_that_cannot_be_read_still_means_no_plan_and_no_error(self):
        broken = FailingStore(fail=("plans_open",), clock=self.clock)
        self.assertIsNone(Approvals(broken, SETTINGS, self.clock).advise(self.finding(cost_usd_30d=80.0), NAMED))


class ThePlanOfAFinding(Base):
    """plan_for: the plan of a change when Meternaut may make one, else the advise plan."""

    def test_a_proposed_planted_disk_in_the_change_group_gets_the_plan_of_a_change(self):
        item = planted_disk()
        case = case_of(item)
        self.store.case_put(case)
        plan = self.approvals.plan_for(case, item, NAMED)
        self.assertEqual((plan.family, plan.approval_class), ("delete-disk", "R2"))
        self.assertEqual(self.store.case_get(case.case_id).status, "awaiting_ok")

    def test_a_proposed_finding_that_meternaut_may_not_change_gets_advice(self):
        case = replace(self.case, case_id="case0005", resource_id=VM.replace("oversized-vm-1", "oversized-vm-2"), resource_name="oversized-vm-2", status="proposed", plan_id=None)
        plan = self.approvals.plan_for(case, lead_of(case), NAMED)
        self.assertEqual((plan.family, plan.preconditions["caseStatus"]), (ADVISE, "proposed"))

    def test_a_planted_disk_that_needs_a_person_gets_advice_and_not_a_change(self):
        item = planted_disk("planted-disk-2")
        case = case_of(item, status="needs_human", recommendation="change")
        self.store.case_put(case)
        plan = self.approvals.plan_for(case, item, NAMED)
        self.assertEqual(plan.family, ADVISE)

    def test_a_planted_disk_that_a_person_marked_do_not_touch_gets_nothing(self):
        item = planted_disk("planted-disk-3")
        case = case_of(item)
        self.store.note_put(NoteRecord(note_id="n", oid=TINO, kind="do_not_touch", text="keep", scope_resource_id=item.resource_id, expires_at="2099-01-01T00:00:00Z"))
        self.assertIsNone(self.approvals.plan_for(case, item, NAMED))

    def test_a_case_that_is_dropped_gets_nothing(self):
        case = replace(self.case, case_id="case0009", resource_id=VM + "-b", status="dropped")
        self.assertIsNone(self.approvals.plan_for(case, lead_of(case), NAMED))


class TheGate(Base):
    def test_a_person_named_on_the_plan_with_the_role_owner_or_the_role_approver_may_answer(self):
        for who in (BOTH, APPROVER, OWNER_ONLY):
            with self.subTest(who.name):
                result = self.answer(who, "ask", note="a question")
                self.assertEqual((result.ok, result.kind), (True, "asked"))
        self.assertEqual(sorted(d.approver_oid for d in self.decisions()), sorted(NAMED))

    def test_a_person_who_is_not_named_on_the_plan_may_not_answer_whatever_the_role(self):
        for who in (Principal(STRANGER, "Stan", ("owner", "approver", "ops")), Principal(STRANGER, "Stan", ("owner",))):
            with self.subTest(who.roles):
                result = self.answer(who, "approve")
                self.assertEqual((result.ok, result.kind), (False, "refused_role"))
        self.assertEqual(self.decisions(), [])

    def test_a_person_who_is_named_but_has_neither_role_may_not_answer(self):
        self.store.plan_put(replace(self.plan, approvers=NAMED + (OPS,)))
        result = self.answer(OPS_ONLY, "ask", note="x")
        self.assertEqual((result.ok, result.kind), (False, "refused_role"))
        self.assertEqual(self.decisions(), [])

    def test_the_name_on_the_plan_is_compared_without_regard_to_case(self):
        shouting = Principal(TINO.upper(), "Tino", ("owner",))
        result = self.answer(shouting, "ask", note="x")
        self.assertEqual((result.ok, result.kind), (True, "asked"))

    def test_an_owner_does_not_answer_a_change_and_cannot_approve_one(self):
        change = self.change_plan()
        for decision in ("decline", "ask", "later", "not_mine"):
            with self.subTest(decision):
                result = self.answer(OWNER_ONLY, decision, plan=change, note="x")
                self.assertEqual((result.ok, result.kind), (False, "refused_role"))
        self.assertEqual(self.approvals.check_approve(OWNER_ONLY, change.plan_id, change.code)[1].kind, "refused_role")
        self.assertEqual(self.approvals.check_form(OWNER_ONLY, change.plan_id, change.code, self.token(OWNER_ONLY, change))[1].kind, "refused_role")
        self.assertEqual(self.store.decisions_of_plan(change.plan_id), [])
        self.assertEqual(self.answer(APPROVER, "decline", plan=change).kind, "declined", "an approver answers a change as before")

    def test_a_plan_that_does_not_exist_is_refused_and_records_nothing(self):
        result = self.approvals.decide(BOTH, "nothing-here", "ask", "ABCD1234", self.token(BOTH), "x")
        self.assertEqual((result.ok, result.kind), (False, "refused_state"))
        self.assertEqual(self.store.decisions, {})

    def test_a_wrong_code_is_refused_before_the_token_is_used(self):
        token = self.token(BOTH)
        result = self.answer(BOTH, "approve", code="00000000", nonce=token)
        self.assertEqual((result.ok, result.kind), (False, "refused_code"))
        self.assertEqual(self.decisions(), [])
        self.assertTrue(self.store.nonce_use(token, TINO, self.plan.plan_id), "the token of the form is still good")

    def test_the_code_is_compared_without_regard_to_case_or_spaces_around_it(self):
        self.assertTrue(self.answer(BOTH, "ask", code=f" {self.plan.code.lower()} ", note="x").ok)

    def test_an_answer_that_is_not_on_the_form_is_refused(self):
        for decision in ("", "yes", "APPROVE", "delete", "reply"):
            with self.subTest(decision):
                result = self.answer(BOTH, decision)
                self.assertEqual((result.ok, result.kind), (False, "error"))
        self.assertEqual(self.decisions(), [])

    def test_a_closed_plan_takes_no_more_answers(self):
        self.assertTrue(self.answer(BOTH, "decline").ok)
        for decision in ANSWERS:
            with self.subTest(decision):
                result = self.answer(APPROVER, decision, note="x")
                self.assertEqual((result.ok, result.kind), (False, "refused_state"))
                self.assertIn("declined", result.message)
        self.assertEqual([d.approver_oid for d in self.decisions()], [TINO])


class TheAnswers(Base):
    def test_worth_acting_on_closes_the_plan_acknowledges_the_case_and_changes_nothing_in_azure(self):
        result = self.answer(BOTH, "approve", note="Plan it for the next sprint.")
        self.assertEqual((result.ok, result.kind), (True, "acknowledged"))
        self.assertIn("Nothing was changed in Azure", result.message)
        self.assertEqual((self.plan_now().state, self.case_now().status), ("consumed", "acknowledged"))
        (decision,) = self.decisions()
        self.assertEqual((decision.approver_oid, decision.approver_name, decision.decision, decision.plan_code, decision.note, decision.reason, decision.at),
                         (TINO, "Tino", "approve", self.plan.code, "Plan it for the next sprint.", "", stamp(NOW)))
        self.assertEqual((self.store.actions, self.store.mails), ({}, []))

    def test_not_worth_it_closes_the_plan_declines_the_case_and_keeps_the_reason(self):
        for reason in DECLINE_REASONS:
            with self.subTest(reason):
                self.setUp()
                result = self.answer(APPROVER, "decline", reason=reason)
                self.assertEqual((result.ok, result.kind), (True, "declined"))
                self.assertEqual((self.plan_now().state, self.case_now().status), ("declined", "declined"))
                self.assertEqual([(d.decision, d.reason) for d in self.decisions()], [("decline", reason)])

    def test_a_reason_that_is_not_on_the_list_is_not_kept_and_only_a_decline_has_a_reason(self):
        self.assertTrue(self.answer(BOTH, "decline", reason="because I say so").ok)
        self.assertEqual(self.decisions()[0].reason, "")
        self.setUp()
        self.assertTrue(self.answer(BOTH, "ask", reason="other", note="x").ok)
        self.assertEqual(self.decisions()[0].reason, "")

    def test_this_is_not_mine_withdraws_the_plan_and_sends_the_case_back_to_a_person(self):
        result = self.answer(OWNER_ONLY, "not_mine")
        self.assertEqual((result.ok, result.kind), (True, "not_mine"))
        self.assertEqual((self.plan_now().state, self.case_now().status), ("withdrawn", "needs_human"))
        self.assertEqual([(d.decision, d.approver_oid) for d in self.decisions()], [("not_mine", OWNER)])

    def test_ask_or_tell_records_the_words_and_leaves_the_request_open(self):
        result = self.answer(BOTH, "ask", note="Is the monthly batch job still running on it?")
        self.assertEqual((result.ok, result.kind), (True, "asked"))
        self.assertIn("approves nothing", result.message)
        self.assertEqual((self.plan_now().state, self.case_now().status), ("open", "needs_human"))
        self.assertEqual([(d.decision, d.note) for d in self.decisions()], [("ask", "Is the monthly batch job still running on it?")])

    def test_decide_later_is_recorded_and_leaves_the_request_open(self):
        result = self.answer(BOTH, "later")
        self.assertEqual((result.ok, result.kind), (True, "later"))
        self.assertEqual((self.plan_now().state, self.case_now().status), ("open", "needs_human"))
        self.assertEqual([d.decision for d in self.decisions()], ["later"])

    def test_the_words_that_a_person_wrote_are_stored_as_one_short_line_and_shown_without_a_link(self):
        hostile = "see https://evil.example/x?a=1 now\n\nand [click](javascript:alert(1)) \x1b[31m" + "x" * 500
        self.assertTrue(self.answer(BOTH, "ask", note=hostile).ok)
        note = self.decisions()[0].note
        self.assertLessEqual(len(note), 300)
        for bad in ("https://", "\n", "\x1b"):
            self.assertNotIn(bad, note)
        self.assertNotIn("](", brief.plain(note), "a renderer that uses plain() cannot make a link of it")

    def test_a_question_and_a_later_are_replaced_by_the_next_answer_of_the_same_person(self):
        self.assertTrue(self.answer(BOTH, "ask", note="first").ok)
        self.assertTrue(self.answer(BOTH, "later").ok)
        self.assertEqual([d.decision for d in self.decisions()], ["later"])
        self.assertTrue(self.answer(BOTH, "ask", note="second").ok)
        self.assertEqual([(d.decision, d.note) for d in self.decisions()], [("ask", "second")])
        self.assertTrue(self.answer(BOTH, "decline", reason="handled").ok)
        self.assertEqual([(d.decision, d.reason) for d in self.decisions()], [("decline", "handled")])

    def test_each_person_has_an_answer_of_their_own(self):
        self.assertTrue(self.answer(BOTH, "later").ok)
        self.assertTrue(self.answer(APPROVER, "ask", note="mine").ok)
        self.assertEqual(sorted((d.approver_oid, d.decision) for d in self.decisions()), sorted([(TINO, "later"), (MAYA, "ask")]))

    def test_a_second_answer_of_the_same_person_after_a_final_one_follows_the_duplicate_rule(self):
        # The final answer is stored but the plan is still open: the write that closes the plan did not happen, so the person tries again.
        self.store.decision_put(DecisionRecord(plan_id=self.plan.plan_id, approver_oid=TINO, approver_name="Tino", decision="decline", at=stamp(NOW), plan_code=self.plan.code,
                                               reason="handled"))
        for decision in ANSWERS:
            with self.subTest(decision):
                result = self.answer(BOTH, decision, note="x")
                if decision == "confirm":  # advice changes nothing, so it has no second person: the answer is refused for that, whoever gave an answer before
                    self.assertEqual((result.ok, result.kind), (False, "refused_state"))
                    continue
                self.assertEqual((result.ok, result.kind), (False, "duplicate"))
                self.assertIn("Your answer stands", result.message)
        self.assertEqual([(d.decision, d.reason) for d in self.decisions()], [("decline", "handled")])
        self.assertTrue(self.answer(APPROVER, "approve").ok, "another named person is not blocked by it")

    def test_the_token_of_a_form_works_once(self):
        token = self.token(BOTH)
        self.assertTrue(self.answer(BOTH, "ask", nonce=token, note="x").ok)
        again = self.answer(BOTH, "ask", nonce=token, note="y")
        self.assertEqual((again.ok, again.kind), (False, "error"))
        self.assertIn("no longer valid", again.message)
        self.assertEqual([d.note for d in self.decisions()], ["x"])

    def test_a_token_of_another_person_or_another_plan_does_not_work(self):
        for label, token in (("another person", self.token(APPROVER)), ("another plan", self.token(BOTH, replace(self.plan, plan_id="plan-other")))):
            with self.subTest(label):
                result = self.answer(BOTH, "ask", nonce=token, note="x")
                self.assertEqual((result.ok, result.kind), (False, "error"))
        self.assertEqual(self.decisions(), [])

    def test_a_store_that_fails_is_an_error_that_records_nothing(self):
        broken = FailingStore(fail=("decision_put",), clock=self.clock)
        broken.plans, broken.cases = self.store.plans, self.store.cases
        approvals = Approvals(broken, SETTINGS, self.clock)
        result = approvals.decide(BOTH, self.plan.plan_id, "approve", self.plan.code, broken.nonce_new(TINO, self.plan.plan_id), "")
        self.assertEqual((result.ok, result.kind), (False, "error"))
        self.assertEqual((self.plan_now().state, self.case_now().status), ("open", "needs_human"))


class TheExpiry(Base):
    def test_a_request_that_nobody_answered_closes_as_expired_with_no_record_no_action_and_no_letter(self):
        self.clock.advance(hours=73)
        closed = self.approvals.expire()
        self.assertEqual([p.plan_id for p in closed], [self.plan.plan_id])
        self.assertEqual((self.plan_now().state, self.case_now().status), ("expired", "expired"))
        self.assertEqual((self.decisions(), self.store.actions, self.store.mails), ([], {}, []))
        self.assertEqual(self.approvals.expire(), [], "it closes once")

    def test_a_request_is_open_until_its_time_is_over(self):
        self.clock.advance(hours=71)
        self.assertEqual(self.approvals.expire(), [])
        self.assertEqual(self.plan_now().state, "open")
        self.assertTrue(self.answer(BOTH, "later").ok)

    def test_an_answer_that_comes_after_the_time_is_refused_and_closes_the_request(self):
        self.clock.advance(hours=73)
        for decision in ANSWERS:
            with self.subTest(decision):
                result = self.answer(BOTH, decision, note="x")
                self.assertEqual((result.ok, result.kind), (False, "expired"))
        self.assertEqual((self.plan_now().state, self.case_now().status, self.decisions()), ("expired", "expired", []))

    def test_a_request_that_was_asked_about_still_expires_and_keeps_the_question(self):
        self.assertTrue(self.answer(BOTH, "ask", note="a question").ok)
        self.clock.advance(hours=73)
        self.assertEqual(len(self.approvals.expire()), 1)
        self.assertEqual([d.decision for d in self.decisions()], ["ask"])
        self.assertEqual(self.plan_now().state, "expired")

    def test_nothing_that_closes_a_plan_can_send_a_letter(self):
        text = (APP_ROOT / "cases" / "approvals.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^\s*(from|import) .*\b(mail|letters|notify)\b")


class ThePause(Base):
    def test_the_full_stop_refuses_the_answer_worth_acting_on_and_records_nothing(self):
        self.pause("all")
        token = self.token(BOTH)
        result = self.answer(BOTH, "approve", nonce=token)
        self.assertEqual((result.ok, result.kind, result.message), (False, "refused_paused", brief.PAUSED_ADVICE))
        self.assertEqual((self.plan_now().state, self.case_now().status, self.decisions()), ("open", "needs_human", []))
        self.assertTrue(self.store.nonce_use(token, TINO, self.plan.plan_id), "the token was not used up")

    def test_every_other_answer_is_still_taken_while_everything_is_paused(self):
        for decision in ("ask", "later", "not_mine", "decline"):
            with self.subTest(decision):
                self.setUp()
                self.pause("all")
                result = self.answer(BOTH, decision, note="x")
                self.assertTrue(result.ok, result)
                self.assertEqual([d.decision for d in self.decisions()], [decision])

    def test_the_pause_of_changes_and_the_pause_of_messages_do_not_stop_advice(self):
        for name in ("changes", "messages"):
            with self.subTest(name):
                self.setUp()
                self.pause(name)
                result = self.answer(BOTH, "approve")
                self.assertEqual((result.ok, result.kind), (True, "acknowledged"))

    def test_a_change_is_stopped_by_the_pause_of_changes_and_by_the_full_stop(self):
        change = self.change_plan()
        for name in ("changes", "all"):
            with self.subTest(name):
                self.store.switch_put(SwitchRecord(name="changes", paused=False))
                self.store.switch_put(SwitchRecord(name="all", paused=False))
                self.pause(name)
                refusal = self.approvals.check_approve(BOTH, change.plan_id, change.code)[1]
                self.assertEqual((refusal.ok, refusal.kind), (False, "refused_paused"))

    def test_a_released_switch_lets_the_answer_through_again(self):
        self.pause("all")
        self.assertEqual(self.answer(BOTH, "approve").kind, "refused_paused")
        self.store.switch_put(SwitchRecord(name="all", paused=False))
        self.assertEqual(self.answer(BOTH, "approve").kind, "acknowledged")


class AdviceNeverReachesAzure(Base):
    """The sign-in to Azure, the runner and the timer, given an advise plan: each refuses or does nothing, and the fake Azure sees no call."""

    def setUp(self):
        super().setUp()
        self.azure = FakeAzure()
        self.redeemed = []

    def redeem(self, code, verifier, claims=""):
        self.redeemed.append(code)
        raise AssertionError("an advise plan never asks Microsoft Entra for a token")

    def services(self):
        client = Client(change_calls(SCOPES), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        return RunnerServices(self.store, client, lambda resource: "token-of-the-person", SETTINGS, clock=self.clock, sleep=lambda s: None)

    def delegation(self):
        return Delegation(self.store, self.approvals, SIGNIN, self.redeem, lambda token: self.services())

    def test_the_sign_in_is_refused_for_an_advise_plan_for_every_person_who_may_answer_it(self):
        for who in (BOTH, APPROVER, OWNER_ONLY):
            with self.subTest(who.name):
                token = self.token(who)
                begun = self.delegation().begin(who, self.plan.plan_id, self.plan.code, token)
                self.assertEqual((begun.location, begun.refusal.kind), ("", "refused_state"))
                self.assertIn("nothing to sign in to", begun.refusal.message)
                self.assertTrue(self.store.nonce_use(token, who.oid, self.plan.plan_id), "the form's token is not used up by the refusal")
        self.assertEqual((self.azure.calls, self.redeemed), ([], []))
        self.assertEqual([n for n in self.store.nonces.values() if n[1] == "arm-signin"], [], "no state of a sign-in was made")
        self.assertEqual((self.plan_now().state, self.decisions(), self.store.actions), ("open", [], {}))

    def test_a_sign_in_state_that_was_forged_for_an_advise_plan_is_refused_on_the_way_back(self):
        data = json.dumps({"plan": self.plan.plan_id, "code": self.plan.code, "resource": self.plan.resource_id, "verifier": "v" * 43, "nonce": "n" * 22, "note": ""})
        state = self.store.nonce_new(TINO, "arm-signin", 600, data)
        result = self.delegation().finish(BOTH, {"code": "C" * 40, "state": state})
        self.assertEqual((result.ok, result.kind), (False, "refused_state"))
        self.assertEqual((self.azure.calls, self.redeemed), ([], []))
        self.assertEqual((self.plan_now().state, self.case_now().status, self.decisions(), self.store.actions), ("open", "needs_human", [], {}))

    def test_the_checks_before_an_approval_refuse_an_advise_plan(self):
        plan, refusal = self.approvals.check_approve(BOTH, self.plan.plan_id, self.plan.code)
        self.assertEqual((plan, refusal.kind), (None, "refused_state"))
        plan, refusal = self.approvals.check_form(BOTH, self.plan.plan_id, self.plan.code, self.token(BOTH))
        self.assertEqual((plan, refusal.kind), (None, "refused_state"))
        self.assertEqual(self.approvals.check_stepup(BOTH, self.plan.plan_id, self.plan.code, self.plan.resource_id)[2].kind, "refused_state")

    def test_an_action_that_somebody_made_for_an_advise_plan_is_not_executed(self):
        action = ActionRecord(plan_id=self.plan.plan_id, case_id=self.plan.case_id, family=ADVISE, resource_id=VM, state="queued", queued_at=stamp(NOW))
        self.store.action_put(action)
        done = execute(self.services(), action, approved_digest=self.plan.digest)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertIn("does not make", done.action.result)
        self.assertEqual(self.azure.calls, [])
        self.assertEqual(self.plan_now().state, "open")

    def test_the_timer_closes_an_advise_plan_without_a_call(self):
        self.clock.advance(hours=73)
        result = tick(self.services())
        self.assertEqual([p.plan_id for p in result.expired], [self.plan.plan_id])
        self.assertEqual((result.finished, result.verified, self.azure.calls), ([], [], []))

    def test_the_list_of_calls_of_a_change_holds_no_way_to_delete_or_to_replace_a_virtual_machine_and_no_family_of_advice(self):
        url = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{CHANGE_GROUP}/providers/Microsoft.Compute/virtualMachines/oversized-vm-1"
        for method, pattern in change_calls(SCOPES):
            if method in ("DELETE", "PUT"):
                self.assertIsNone(pattern.match(url), (method, pattern.pattern))
        self.assertNotIn(ADVISE, {kind.collection for kind in KINDS})
        self.assertIsNone(registry.get(ADVISE), "nothing of a change is made for an advise plan: the registry has no family of that name")

    def test_the_modules_that_make_a_change_do_not_know_the_family(self):
        for name in ("delegated.py", "runner.py"):
            text = (APP_ROOT / "cases" / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)advis", name)


class TheWholeWay(unittest.TestCase):
    """From a finding to the answer on the page, over the real approvals and the real sign-in, with a fake Azure that has to stay unused."""

    def setUp(self):
        self.console = Console()
        self.store = self.console.store
        self.clock = lambda: self.console.now
        self.approvals = Approvals(self.store, SETTINGS, self.clock)
        self.azure = FakeAzure()
        self.redeemed = []

        def redeem(code, verifier, claims=""):
            self.redeemed.append(code)
            raise AssertionError("an advise plan never asks Microsoft Entra for a token")

        def run(token):
            client = Client(change_calls(SCOPES), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
            return RunnerServices(self.store, client, lambda resource: token, SETTINGS, clock=self.clock, sleep=lambda s: None)

        self.console.use(self.approvals)
        self.console.use_delegate(Delegation(self.store, self.approvals, SIGNIN, redeem, run))
        self.store.run_put(make_run())
        self.case = make_advice_case(plan_id=None)
        self.store.case_put(self.case)
        self.plan = self.approvals.plan_for(self.case, lead_of(self.case), (TINO, OWNER))
        self.path = f"/ok/{self.plan.plan_id}"

    def assert_azure_untouched(self):
        self.assertEqual((self.azure.calls, self.redeemed, self.store.actions), ([], [], {}))

    def test_the_page_of_the_request_has_the_five_answers_in_one_form(self):
        page = self.console.get(self.path)
        self.assertEqual(page.status, 200)
        forms = [f for f in page.forms() if f.action == self.path]
        self.assertEqual(len(forms), 1)
        self.assertEqual([label for _, _, label in forms[0].buttons], ["Worth acting on", "Not worth it", "This is not mine", "Ask or tell", "Decide later"])
        self.assertEqual(sorted(forms[0].fields), ["code", "nonce", "note", "reason"])
        self.assertEqual(forms[0].fields["code"], self.plan.code)

    def test_worth_acting_on_is_recorded_and_the_page_then_has_no_form(self):
        form = self.console.get(self.path).form(self.path)
        reply = self.console.submit(form, "Worth acting on", note="Please plan it for the next sprint.")
        self.assertEqual(reply.status, 200)
        self.assertIn("Recorded: worth acting on", reply.headings())
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, self.store.case_get(self.case.case_id).status), ("consumed", "acknowledged"))
        (decision,) = self.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual((decision.approver_oid, decision.approver_name, decision.decision, decision.note), (TINO, "Tino", "approve", "Please plan it for the next sprint."))
        self.assert_azure_untouched()
        again = self.console.get(self.path)
        self.assertEqual(again.status, 200)
        self.assertEqual([f for f in again.forms() if f.action == self.path], [])
        history = self.console.get("/history")
        lines = [tuple(c.text() for c in li.children if hasattr(c, "tag") and c.tag == "span") for ul in history.main.find_all("ul", class_="recent") for li in ul.find_all("li")]
        self.assertTrue(any(line[:1] == ("Worth acting on",) and line[2:] == ("Tino",) for line in lines), lines)

    def test_a_second_answer_with_the_old_form_changes_nothing(self):
        form = self.console.get(self.path).form(self.path)
        self.assertEqual(self.console.submit(form, "Worth acting on").status, 200)
        second = self.console.submit(form, "Not worth it")
        self.assertEqual(second.status, 409)
        self.assertEqual([d.decision for d in self.store.decisions_of_plan(self.plan.plan_id)], ["approve"])
        self.assert_azure_untouched()

    def test_not_worth_it_with_a_reason_closes_the_request(self):
        form = self.console.get(self.path).form(self.path)
        reply = self.console.submit(form, "Not worth it", reason="figure-wrong")
        self.assertEqual(reply.status, 200)
        self.assertIn("Recorded: not worth it", reply.headings())
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, self.store.case_get(self.case.case_id).status), ("declined", "declined"))
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id)[0].reason, "figure-wrong")
        self.assertIn("the figure is wrong", self.console.get("/history").content)
        self.assert_azure_untouched()

    def test_ask_or_tell_needs_words_and_leaves_the_request_open(self):
        form = self.console.get(self.path).form(self.path)
        empty = self.console.submit(form, "Ask or tell", note="")
        self.assertEqual(empty.status, 400)
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
        reply = self.console.submit(form, "Ask or tell", note="Does the batch job still need it?")
        self.assertEqual(reply.status, 200)
        self.assertIn("Recorded: your words", reply.headings())
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
        self.assertIn("Does the batch job still need it?", self.console.get(self.path).content, "the person sees their own question again")
        self.assert_azure_untouched()

    def test_an_owner_who_is_named_answers_the_request_and_an_owner_does_not_see_a_change(self):
        reply = self.console.get(self.path, oid=OWNER)
        self.assertEqual(reply.status, 200)
        form = reply.form(self.path)
        self.assertEqual(self.console.submit(form, "Decide later", oid=OWNER).status, 200)
        self.assertEqual([(d.approver_oid, d.decision) for d in self.store.decisions_of_plan(self.plan.plan_id)], [(OWNER, "later")])
        item = planted_disk()
        case = case_of(item)
        self.store.case_put(case)
        change = self.approvals.create(case, item, (TINO, OWNER))
        self.assertEqual(self.console.get(f"/ok/{change.plan_id}", oid=OWNER).status, 403)
        self.assertEqual(self.console.get(f"/ok/{change.plan_id}", oid=TINO).status, 200)

    def test_a_person_who_is_not_named_on_the_request_does_not_see_it(self):
        self.assertEqual(self.console.get(self.path, oid=MAYA).status, 403)
        self.assertEqual(self.console.get(self.path, oid=STRANGER).status, 403)

    def test_the_full_stop_leaves_out_the_approving_answer_and_refuses_it_when_it_is_sent_anyway(self):
        form = self.console.get(self.path).form(self.path)
        self.store.switch_put(SwitchRecord(name="all", paused=True))
        paused = self.console.get(self.path)
        labels = [label for f in paused.forms() if f.action == self.path for _, _, label in f.buttons]
        self.assertEqual(labels, ["Not worth it", "This is not mine", "Ask or tell", "Decide later"])
        self.assertIn("Meternaut is paused", paused.content)
        reply = self.console.submit(form, "Worth acting on")
        self.assertEqual(reply.status, 409)
        self.assertIn("Meternaut is paused", reply.headings())
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
        self.assert_azure_untouched()

    def test_the_pause_of_changes_does_not_leave_out_the_answer_of_advice(self):
        self.store.switch_put(SwitchRecord(name="changes", paused=True))
        labels = [label for f in self.console.get(self.path).forms() if f.action == self.path for _, _, label in f.buttons]
        self.assertIn("Worth acting on", labels)

    def test_a_request_whose_time_is_over_says_so_and_takes_no_answer(self):
        form = self.console.get(self.path).form(self.path)
        self.console.now = self.console.now + dt.timedelta(hours=73)
        reply = self.console.submit(form, "Worth acting on")
        self.assertEqual(reply.status, 410)
        self.assertIn("This request expired", reply.headings())
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, self.store.decisions_of_plan(self.plan.plan_id)), ("expired", []))
        self.assert_azure_untouched()
        self.assertEqual([f for f in self.console.get(self.path).forms() if f.action == self.path], [])

    def test_the_old_addresses_of_the_question_and_of_not_mine_take_the_same_answers(self):
        form = self.console.get(self.path).form(self.path)
        data = dict(form.fields, note="a question")
        self.assertEqual(self.console.post(f"{self.path}/ask", data).status, 200)
        self.assertEqual([d.decision for d in self.store.decisions_of_plan(self.plan.plan_id)], ["ask"])
        fresh = self.console.get(self.path).form(self.path)
        self.assertEqual(self.console.post(f"{self.path}/not-mine", dict(fresh.fields)).status, 200)
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "withdrawn")
        self.assert_azure_untouched()


class OldRecordsStayReadable(unittest.TestCase):
    """The migration note of models.py: a record that was written before the decision brief reads, and one with a key that is not known reads too."""

    def test_a_case_that_was_written_before_the_owner_field_reads_with_an_empty_owner(self):
        old = json.loads(make_advice_case().to_json())
        del old["owner"]
        case = CaseRecord.from_json(json.dumps(old))
        self.assertEqual((case.owner, case.resource_name, case.status), ({}, "oversized-vm-1", "needs_human"))

    def test_a_decision_that_was_written_before_the_reason_field_reads_with_no_reason(self):
        old = json.loads(DecisionRecord(plan_id="p", approver_oid=TINO, approver_name="T", decision="decline", at=stamp(NOW), plan_code="ABCD1234", reason="handled").to_json())
        del old["reason"]
        decision = DecisionRecord.from_json(json.dumps(old))
        self.assertEqual((decision.reason, decision.decision), ("", "decline"))

    def test_a_key_that_a_newer_version_wrote_is_dropped_and_not_an_error(self):
        for record in (make_advice_case(), DecisionRecord(plan_id="p", approver_oid=TINO, approver_name="T", decision="later", at=stamp(NOW), plan_code="ABCD1234")):
            with self.subTest(type(record).__name__):
                data = json.loads(record.to_json())
                data["aFieldOfTheFuture"] = {"x": 1}
                self.assertEqual(type(record).from_json(json.dumps(data)), record)

    def test_the_owner_lines_of_a_case_survive_a_round_trip(self):
        owner = {"tagOwner": "Team Apps", "createdBy": "someone@example.com", "createdAt": "2026-09-30T08:00:00Z", "lookedUp": True}
        case = make_advice_case(owner=owner)
        self.assertEqual(CaseRecord.from_json(case.to_json()).owner, owner)


if __name__ == "__main__":
    unittest.main()
