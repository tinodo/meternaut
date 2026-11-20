"""A finding that a guard holds back reaches a person as a case, with its figure, why no request was made and what the guard still needs, and nobody is asked to approve anything.

The guards are right about what Meternaut may ask a person to approve; they were wrong to make the finding invisible (docs/proposals/29-held-findings.md). Each finding that a guard holds back gets
a request of its own in the state `held` (Approvals.settle). It is no open request: the Decisions page, the letters and cards of a request and the limit of open requests do not see it. Everything
in this file is invented, and no model and no Azure is called.
"""
import datetime as dt
import json
import re
import unittest
from dataclasses import replace
from types import SimpleNamespace

import support  # noqa: F401  (it puts the app on the path)
from cardsupport import MAYA as CARD_MAYA, World as CardWorld, advice_plan
from test_digest_page import desk, listed
from test_notify import ENV, OPS as ENV_OPS, TINO as ENV_TINO
from test_web_savings import PATH as SAVINGS, finding, rows_of, tiles_of
from test_web_support import MAYA, NOW, SUB, TINO, Console, make_advice, make_advice_case, make_case, make_decision, make_plan

from cases import brief, events, learning, letters, upkeep
from cases.approvals import (ADVICE_OPEN_MAX, ADVICE_QUIET_DAYS, HELD_BACK, HELD_NEW, HELD_NO_APPROVAL, HELD_WORDS, LEFT_ALONE, NOTHING_TO_SAY, RELEASED, ApprovalSettings, Approvals, why_not_ask)
from cases.families.gates import ChangeScope
from cases.memory_store import MemoryStore, stamp
from cases.models import HELD, NoteRecord, Principal

GROUP = "rg-platform"
BASE = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
BOB = Principal(TINO, "Tino", ("owner", "approver", "ops"))
NOBODY = Principal(MAYA, "Maya", ("approver",))
MEASURED = {"basis": "no-usage", "proposal": "delete", "metrics": {"MetricA": 0}, "metricDaysWithData": {"MetricA": 28}, "metricDays": {"MetricA": 30}}
REASONS = ("unchecked", "impact", "nothing", "rules")
BANNED = ("automation identity", "activity log", "console", "sign in", "sign-in", "principal", "backlog")


def days_ago(days: float) -> str:
    return stamp(NOW - dt.timedelta(days=days))


def automation(**more):
    """An application or service changed the resource two days ago: the resource is managed by an automation (it is asked about, with a warning: it is held back for no reason)."""
    base = dict(case_id="k-automation", status="needs_human", recommendation="investigate", plan_id=None,
                owner={"lookedUp": True, "automatedAt": days_ago(2), "tagOwner": "platform-team", "tagName": "owner", "changedBy": "alice@example.com", "changedAt": days_ago(1)})
    return make_advice_case(**{**base, **more})


def unchecked(**more):
    """A deletion of a disk, and nobody looked up who changed it."""
    base = dict(case_id="k-unchecked", resource_id=f"{BASE}/Microsoft.Compute/disks/disk-u", resource_name="disk-u", resource_type="microsoft.compute/disks", resource_group=GROUP,
                status="proposed", recommendation="delete", plan_id=None, owner={}, facts=MEASURED)
    return make_advice_case(**{**base, **more})


def impact(**more):
    """A deletion of a public address on a measured zero, who changed it was read, and what depends on it was not checked to the end."""
    base = dict(case_id="k-impact", resource_id=f"{BASE}/Microsoft.Network/publicIPAddresses/ip-1", resource_name="ip-1", resource_type="microsoft.network/publicipaddresses",
                resource_group=GROUP, status="proposed", recommendation="delete", plan_id=None, owner={"lookedUp": True}, facts=MEASURED)
    return make_advice_case(**{**base, **more})


def nothing(**more):
    """A recommendation of Advisor about a whole subscription, with none of Advisor's words and no figure: it cannot say what to look at."""
    base = dict(case_id="k-nothing", detector="advisor-cost", resource_id=f"/subscriptions/{SUB}", resource_name=SUB, resource_type="microsoft.subscriptions/subscriptions", resource_group="",
                status="needs_human", recommendation="change", saving_usd_month=0.0, cost_usd_30d=0.0, plan_id=None, advice={}, facts={"category": "cost", "impact": "medium"}, owner={})
    return make_advice_case(**{**base, **more})


def rules(**more):
    """A request that was made when a deletion could be asked on less than the rules ask for now (a private endpoint, which others share): it is taken back, and the finding is held."""
    base = dict(case_id="k-rules", resource_id=f"{BASE}/Microsoft.Network/privateEndpoints/pe-1", resource_name="pe-1", resource_type="microsoft.network/privateendpoints",
                resource_group=GROUP, status="needs_human", recommendation="delete", plan_id="p-rules", owner={"lookedUp": True}, facts={"basis": "other", "proposal": "delete", "metrics": {}})
    return make_advice_case(**{**base, **more})


CASES = {"unchecked": unchecked, "impact": impact, "nothing": nothing, "rules": rules}


class Lines:
    """The logger of a History: keeps each line that it was given, as the object that it holds."""

    def __init__(self) -> None:
        self.found: list[dict] = []

    def info(self, line: str) -> None:
        self.found.append(json.loads(line[len(events.EVENT_PREFIX):]))


class Base(unittest.TestCase):
    now = NOW

    def setUp(self):
        self.store = MemoryStore(lambda: self.now)
        self.approvals = Approvals(self.store, ApprovalSettings(change_scopes=()), lambda: self.now)
        self.lines = Lines()
        self.history = events.History("run1", None, lambda: self.now, lambda text: text, logger=self.lines)

    def put(self, reason: str, **more):
        case = CASES[reason](**more)
        self.store.case_put(case)
        if reason == "rules":
            self.store.plan_put(make_advice(plan_id="p-rules", case_id=case.case_id, resource_id=case.resource_id, resource_name="pe-1", resource_group=GROUP,
                                            title="Consider deleting the private endpoint pe-1 in group rg-platform", code="R1R1R1R1"))
            self.approvals.hold_back_empty()
        return case

    def settle(self, approvers=(TINO,)):
        return self.approvals.settle(approvers)

    def held_of(self, case_id: str):
        case = self.store.case_get(case_id)
        return self.store.plan_get(case.plan_id) if case is not None and case.plan_id else None

    def answer(self, plan, decision: str, who: Principal = BOB, **more):
        return self.approvals.decide(who, plan.plan_id, decision, plan.code, self.store.nonce_new(who.oid, plan.plan_id), more.get("note", ""), more.get("reason", ""))

    def judged_again(self, case, **more):
        """What the investigation does to a case that it judges again: a new record of it, with no link to a request, updated now."""
        self.now += dt.timedelta(days=1)
        self.store.case_put(replace(case, plan_id=None, updated_at=stamp(self.now), **more))


class EachReasonMakesTheFindingVisible(Base):
    def test_a_finding_of_each_reason_gets_a_request_in_the_state_held_with_its_reason(self):
        for reason in REASONS:
            with self.subTest(reason=reason):
                case = self.put(reason)
                self.assertEqual(self.approvals._guard(case) or "rules", reason)
                self.settle()
                plan = self.held_of(case.case_id)
                self.assertEqual((plan.state, plan.family, brief.held_of(plan), plan.approvers), (HELD, "advise", reason, (TINO,)))
                self.assertEqual(self.store.case_get(case.case_id).status, case.status, "the finding keeps what the AIs came to")
        self.assertEqual(self.store.plans_open(), [], "no request is open: nobody is asked to approve anything")

    def test_the_request_is_made_once_and_the_next_watch_makes_none(self):
        case = self.put("unchecked")
        self.settle()
        first = self.held_of(case.case_id)
        self.assertEqual(self.settle(), [])
        self.assertEqual([p.plan_id for p in self.store.plans_held()], [first.plan_id])

    def test_the_figure_the_level_and_the_guards_words_are_those_of_the_finding(self):
        case = self.put("unchecked")
        self.settle()
        plan = self.held_of(case.case_id)
        found = brief.build_brief(case, plan, now=self.now, may_answer=True)
        self.assertEqual((found.kind, found.state, found.saving.monthly, found.saving.level), ("advice", "held", 120.0, "Expected"))
        self.assertEqual(found.hold, brief.Hold("unchecked", *brief.HOLD_WORDS["unchecked"]))
        self.assertEqual(found.owner.text, "Meternaut has not looked up who owns this resource yet.")

    def test_a_finding_that_a_person_answered_lately_or_that_has_a_request_open_gets_none(self):
        for label, plan in (("a request is open", make_advice(plan_id="p-open", case_id="k-unchecked", resource_id=unchecked().resource_id)),
                            ("declined 3 days ago", make_advice(plan_id="p-no", case_id="k-unchecked", resource_id=unchecked().resource_id, state="declined", created_at=days_ago(3)))):
            with self.subTest(case=label):
                self.setUp()
                self.store.case_put(unchecked())
                self.store.plan_put(plan)
                self.settle()
                self.assertEqual(self.store.plans_held(), [])
        self.setUp()
        self.store.case_put(unchecked())
        self.store.plan_put(make_advice(plan_id="p-old", case_id="k-unchecked", resource_id=unchecked().resource_id, state="declined", created_at=days_ago(40)))
        self.settle()
        self.assertEqual(len(self.store.plans_held()), 1, "an answer is quiet for 30 days, and then the finding is shown again")

    def test_waste_that_meternaut_planted_in_a_group_where_it_may_change_is_never_held(self):
        group = "meternaut-test-rg"
        approvals = Approvals(self.store, ApprovalSettings(change_scopes=(ChangeScope(SUB, group),)), lambda: self.now)
        self.store.case_put(unchecked(resource_group=group))
        approvals.settle((TINO,))
        self.assertEqual(self.store.plans_held(), [])

    def test_a_finding_with_no_saving_priced_is_not_made_a_request_even_when_nothing_measured_it(self):
        quiet = unchecked(objections=("no measurement backs this finding; a person has to judge it",), saving_usd_month=None, cost_usd_30d=3.0)
        self.assertIsNotNone(why_not_ask(quiet))
        self.store.case_put(quiet)
        self.settle()
        self.assertEqual(self.store.plans_held(), [])

    def test_nobody_is_made_a_request_when_no_person_can_answer_and_at_most_so_many_are_made_at_a_time(self):
        self.put("unchecked")
        self.settle(())
        self.assertEqual(self.store.plans_held(), [])
        for number in range(HELD_NEW + 5):
            self.store.case_put(unchecked(case_id=f"k-many-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/b{number}", resource_name=f"b{number}"))
        self.settle()
        self.assertEqual(len(self.store.plans_held()), HELD_NEW)
        self.settle()
        self.assertEqual(len(self.store.plans_held()), HELD_NEW + 6, "the rest at the next Watch (and the one that was there before)")

    def test_the_limit_of_open_requests_does_not_count_a_held_one_and_a_held_one_does_not_wait_for_a_place(self):
        for number in range(ADVICE_OPEN_MAX - 1):
            case = make_advice_case(case_id=f"k-open-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/o{number}", resource_name=f"o{number}", plan_id=None, status="needs_human")
            self.store.case_put(case)
            self.assertIsNotNone(self.approvals.advise(case, (TINO,)))
        for reason in ("unchecked", "impact", "nothing"):
            self.put(reason)
        self.settle()
        self.assertEqual(len(self.store.plans_held()), 3, "the places for requests are full, and the held findings are shown all the same")
        last = make_advice_case(case_id="k-last", resource_id=f"{BASE}/Microsoft.Foo/bars/last", resource_name="last", plan_id=None, status="needs_human")
        self.store.case_put(last)
        self.assertIsNotNone(self.approvals.advise(last, (TINO,)), "the nine that are open and the three that are held make twelve plans, and the tenth place is still free")
        another = make_advice_case(case_id="k-another", resource_id=f"{BASE}/Microsoft.Foo/bars/another", resource_name="another", plan_id=None, status="needs_human")
        self.store.case_put(another)
        self.assertIsNone(self.approvals.advise(another, (TINO,)), "the limit is what it was: ADVICE_OPEN_MAX open requests for what the AIs did not settle, and a finding that is worth no more than the smallest waits")


class TheAnswersAreTheOnesThatExist(Base):
    def setUp(self):
        super().setUp()
        self.case = self.put("unchecked")
        self.settle()
        self.plan = self.held_of(self.case.case_id)

    def test_there_is_nothing_to_approve_and_nothing_is_recorded_for_it(self):
        for decision in ("approve", "confirm"):
            with self.subTest(decision=decision):
                result = self.answer(self.plan, decision)
                self.assertEqual((result.ok, result.kind, result.message), (False, "refused_state", HELD_NO_APPROVAL))
        self.assertEqual((self.store.decisions_of_plan(self.plan.plan_id), self.store.plan_get(self.plan.plan_id).state), ([], HELD))
        self.assertEqual(self.approvals.check_approve(BOB, self.plan.plan_id, self.plan.code)[1].kind, "refused_state", "no sign-in to Azure is begun for it either")

    def test_a_question_and_later_are_recorded_and_the_finding_stays_held(self):
        for decision in ("ask", "later"):
            with self.subTest(decision=decision):
                self.assertTrue(self.answer(self.plan, decision, note="who owns it?").ok)
                self.assertEqual(self.store.plan_get(self.plan.plan_id).state, HELD)
        self.assertEqual(self.store.case_get(self.case.case_id).status, self.case.status)

    def test_not_worth_it_with_a_reason_closes_the_finding_and_it_is_not_shown_again_for_a_month(self):
        result = self.answer(self.plan, "decline", reason="handled")
        self.assertEqual((result.ok, result.kind), (True, "declined"))
        (decision,) = self.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual((decision.decision, decision.reason, self.store.plan_get(self.plan.plan_id).state, self.store.case_get(self.case.case_id).status), ("decline", "handled", "declined", "declined"))
        self.settle()
        self.assertEqual([p.state for p in self.store.plans_recent(10)], ["declined"])

    def test_not_mine_withdraws_it_and_it_is_not_asked_again_for_a_month(self):
        self.assertEqual(self.answer(self.plan, "not_mine").kind, "not_mine")
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, self.store.case_get(self.case.case_id).status), ("withdrawn", "needs_human"))
        self.settle()
        self.assertEqual([p.state for p in self.store.plans_recent(10)], ["withdrawn"])

    def test_only_a_person_who_is_named_for_it_may_answer(self):
        self.assertEqual(self.answer(self.plan, "ask", NOBODY, note="x").kind, "refused_role")
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])

    def test_the_quiet_days_count_from_the_answer_and_not_from_the_day_that_the_held_request_was_made(self):
        self.store.plan_put(replace(self.plan, created_at=days_ago(40)))  # a held request is made long before a person gets to it
        self.answer(self.plan, "not_mine")
        self.assertEqual(self.store.plan_get(self.plan.plan_id).created_at, stamp(self.now))
        self.settle()
        self.assertEqual(self.store.plans_held(), [], "it is not asked again for a month")
        self.assertFalse(learning.OpenQuestions(self.store, self.now).is_open(self.store.case_get(self.case.case_id)))

    def test_an_answer_to_a_held_request_is_no_lesson_about_what_gets_approved(self):
        self.answer(self.plan, "decline", reason="handled")
        self.assertEqual((learning.sync(self.store, self.now), self.store.lessons_recent(10)), (0, []))

    def test_the_page_says_that_it_does_not_end_by_the_clock(self):
        console = held_console("unchecked")
        text = console.get("/why/k-unchecked").main.text()
        self.assertIn("It ends when nothing holds the finding back any more.", text)
        self.assertNotIn("open until", text)

    def test_the_answers_of_the_brief_have_no_approve_and_only_for_a_person_who_may_answer(self):
        mine = brief.build_brief(self.case, self.plan, now=NOW, may_answer=True)
        self.assertEqual(mine.answers, ("decline", "not_mine", "ask", "later"))
        self.assertEqual(brief.build_brief(self.case, self.plan, now=NOW, may_answer=False).answers, ())
        self.assertEqual(brief.build_brief(self.case, self.plan, now=NOW, may_answer=True, changes_paused=True).answers, ("decline", "not_mine", "ask", "later"))
        self.assertEqual(mine.outcome.state, "", "it is no closed request: it has no outcome")


class TheQuietDaysCountFromTheAnswer(Base):
    """A held request never runs out, so a person may get to it weeks after it was made: the quiet days of the finding start at the answer."""

    def held(self, reason: str):
        self.now = NOW
        self.setUp()
        case = self.put(reason)
        self.settle()
        return case, self.held_of(case.case_id)

    def test_the_normal_path_asks_nothing_the_day_after_an_answer_whatever_the_age_of_the_held_request(self):
        for age in (2, 35):
            for decision, more in (("decline", {"reason": "handled"}), ("not_mine", {})):
                with self.subTest(age=age, decision=decision):
                    case, plan = self.held("unchecked")
                    self.now += dt.timedelta(days=age)
                    self.assertTrue(self.answer(plan, decision, **more).ok)
                    self.judged_again(case, owner={"lookedUp": True})  # found again the day after, and nothing holds it back: only the quiet days do
                    self.assertIsNone(self.approvals.advise(self.store.case_get(case.case_id), (TINO,)), "no request comes back, and with it no 'Worth acting on'")
                    self.settle()
                    self.assertEqual((self.store.plans_open(), self.store.plans_held()), ([], []))

    def test_a_guard_that_still_holds_the_finding_makes_no_new_held_request_the_day_after_either(self):
        for age in (2, 35):
            for decision, more in (("decline", {"reason": "handled"}), ("not_mine", {})):
                with self.subTest(age=age, decision=decision):
                    case, plan = self.held("unchecked")
                    self.now += dt.timedelta(days=age)
                    self.assertTrue(self.answer(plan, decision, **more).ok)
                    self.judged_again(case)
                    self.settle()
                    self.assertEqual(self.store.plans_held(), [])
                    self.now += dt.timedelta(days=ADVICE_QUIET_DAYS)
                    self.settle()
                    self.assertEqual(len(self.store.plans_held()), 1, "a month after the answer the finding is shown again")


class AGuardThatEndsIsJudgedAgainByTheNormalPath(Base):
    def setUp(self):
        super().setUp()
        self.case = self.put("unchecked")
        self.settle()
        self.plan = self.held_of(self.case.case_id)
        self.ex = SimpleNamespace(approvals=self.approvals, approvers=lambda: (TINO,))

    def test_a_guard_that_is_not_read_again_does_not_close_it_by_the_clock(self):
        self.now += dt.timedelta(days=20)
        self.assertEqual(self.settle(), [])
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, HELD, "only a judgment with the facts of that day closes it")

    def test_judged_again_and_held_no_more_it_becomes_a_normal_request_and_the_held_one_is_closed_with_a_word(self):
        self.judged_again(self.case, owner={"lookedUp": True, "automatedAt": days_ago(30)})
        fresh = self.store.case_get(self.case.case_id)
        normal = self.approvals.advise(fresh, (TINO,))
        self.assertEqual((normal.state, normal.family, self.store.plans_open()), ("open", "advise", [normal]), "the normal path asks about it")
        taken = upkeep.take_back(self.ex, self.history)
        self.assertEqual(taken, {}, "it is not counted as held back")
        closed = self.store.plan_get(self.plan.plan_id)
        self.assertEqual((closed.state, closed.preconditions["takenBack"]), ("expired", "released"))
        (said,) = [line for line in self.lines.found if line["type"] == "case.released"]
        self.assertEqual((said["caseId"], said["reason"], said["was"], said["detector"]), (self.case.case_id, RELEASED, HELD_BACK["unchecked"], "investigation"))
        self.assertEqual(RELEASED, "no longer held back")
        self.assertEqual(upkeep.take_back(self.ex, self.history), {})
        self.assertEqual(len([line for line in self.lines.found if line["type"] == "case.released"]), 1, "said once")

    def test_the_history_holds_no_money_and_no_id_of_the_estate(self):
        self.judged_again(self.case, owner={"lookedUp": True})
        self.approvals.advise(self.store.case_get(self.case.case_id), (TINO,))
        upkeep.take_back(self.ex, self.history)
        (said,) = [line for line in self.lines.found if line["type"] == "case.released"]
        self.assertEqual(sorted(said), ["caseId", "detector", "reason", "requestId", "resourceName", "resourceType", "runId", "ts", "type", "v", "was"])
        text = json.dumps(said)
        for word in ("$", "usd", "saving", "cost", SUB):
            self.assertNotIn(word, text.lower())

    def test_judged_again_and_still_held_it_stays_with_the_reason_of_today_and_its_link(self):
        self.judged_again(self.case, owner={}, recommendation="delete", status="proposed", facts=MEASURED, resource_type="microsoft.compute/disks")
        self.assertEqual(self.store.case_get(self.case.case_id).plan_id, None, "a judgment writes the case again, with no link")
        self.assertEqual(self.settle(), [])
        again = self.held_of(self.case.case_id)
        self.assertEqual((again.plan_id, brief.held_of(again)), (self.plan.plan_id, "unchecked"))

    def test_a_finding_that_is_not_a_question_any_more_closes_its_request(self):
        for label, status in (("dropped", "dropped"), ("a change was planned", "awaiting_ok"), ("declined by somebody else", "declined")):
            with self.subTest(case=label):
                self.setUp()
                self.store.case_put(replace(self.case, status=status))
                (closed,) = self.settle()
                self.assertEqual((closed[0].plan_id, self.store.plan_get(self.plan.plan_id).state), (self.plan.plan_id, "expired"))

    def test_a_finding_that_is_judged_again_with_another_figure_shows_the_new_figure_and_a_reason_that_changed_is_kept(self):
        self.judged_again(self.case, saving_usd_month=60.0, cost_usd_30d=60.0)
        self.assertEqual(self.settle(), [])
        plan = self.held_of(self.case.case_id)
        self.assertEqual((plan.plan_id, plan.saving_usd_month, plan.waiting_costs_usd_day), (self.plan.plan_id, 60.0, 2.0))
        self.assertEqual(brief.build_brief(self.store.case_get(self.case.case_id), plan, now=self.now).saving.monthly, 60.0)
        self.judged_again(self.store.case_get(self.case.case_id), owner={})
        self.judged_again(self.store.case_get(self.case.case_id), recommendation="delete", facts=MEASURED, resource_type="microsoft.compute/disks")
        self.settle()
        self.assertEqual(brief.held_of(self.held_of(self.case.case_id)), "unchecked")

    def test_a_do_not_touch_mark_that_is_made_after_the_request_closes_it_with_a_word_in_the_history(self):
        self.store.note_put(NoteRecord(note_id="n1", oid=TINO, kind="do_not_touch", text="leave it", scope_resource_id=self.case.resource_id, created_at=stamp(self.now)))
        self.assertEqual(upkeep.take_back(self.ex, self.history), {}, "it is not counted as held back")
        closed = self.store.plan_get(self.plan.plan_id)
        self.assertEqual((closed.state, closed.preconditions["takenBack"], self.store.plans_held()), ("expired", "left-alone", []))
        (said,) = [line for line in self.lines.found if line["type"] == "case.released"]
        self.assertEqual((said["caseId"], said["reason"], said["was"]), (self.case.case_id, LEFT_ALONE, HELD_BACK["unchecked"]))
        self.assertEqual(LEFT_ALONE, "closed: a person marked it do-not-touch")
        self.assertEqual(upkeep.take_back(self.ex, self.history), {})
        self.assertEqual(len([line for line in self.lines.found if line["type"] == "case.released"]), 1, "said once")
        found = brief.build_brief(self.store.case_get(self.case.case_id), closed, now=self.now)
        self.assertEqual((found.outcome.state, found.outcome.title, found.outcome.lines[0]), ("expired", "Left alone", brief.TAKEN_BACK["left-alone"]))
        self.assertIsNone(learning.lesson_of(closed, self.store.case_get(self.case.case_id), [], None, self.now))

    def fill_the_places(self):
        for number in range(ADVICE_OPEN_MAX):
            case = make_advice_case(case_id=f"k-open-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/o{number}", resource_name=f"o{number}", plan_id=None, status="needs_human")
            self.store.case_put(case)
            self.assertIsNotNone(self.approvals.advise(case, (TINO,)))

    def test_when_the_guard_ends_and_no_place_is_free_the_finding_stays_held_until_a_real_request_exists(self):
        self.fill_the_places()
        self.judged_again(self.case, owner={"lookedUp": True, "automatedAt": days_ago(30)}, status="needs_human")  # only a finding that the AIs did not settle waits for a place
        self.assertIsNone(self.approvals.advise(self.store.case_get(self.case.case_id), (TINO,)), "no place is free: the normal path makes no request")
        self.assertEqual(self.settle(), [], "and the held one is not closed: the finding would have no request at all")
        waiting = self.held_of(self.case.case_id)
        self.assertEqual((waiting.plan_id, waiting.state, brief.held_of(waiting)), (self.plan.plan_id, HELD, "waiting"))
        shown = brief.build_brief(self.store.case_get(self.case.case_id), waiting, now=self.now, may_answer=True)
        self.assertEqual((shown.hold.heading, shown.answers), ("Waiting for a free place", ("decline", "not_mine", "ask", "later")))
        self.assertEqual(upkeep.take_back(self.ex, self.history), {})
        self.assertEqual([line for line in self.lines.found if line["type"] == "case.released"], [], "it stays at the next Watch too")
        self.answer(self.store.plans_open()[-1], "decline", reason="handled")  # a place is free
        self.assertIsNotNone(self.approvals.advise(self.store.case_get(self.case.case_id), (TINO,)), "the normal path asks about the finding now")
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, HELD, "the real request does not close the note by itself: the next Watch does")
        upkeep.take_back(self.ex, self.history)
        closed = self.store.plan_get(self.plan.plan_id)
        self.assertEqual((closed.state, closed.preconditions["takenBack"]), ("expired", "released"))
        (said,) = [line for line in self.lines.found if line["type"] == "case.released"]
        self.assertEqual((said["reason"], said["was"]), (RELEASED, HELD_WORDS["waiting"]))

    def test_when_the_guard_ends_and_nobody_is_to_be_asked_the_note_is_closed_and_does_not_wait(self):
        for label, change, answered in (("no saving was priced", dict(objections=("no measurement backs this finding; a person has to judge it",), saving_usd_month=None, cost_usd_30d=3.0), False),
                                         ("a person answered lately", {}, True)):
            with self.subTest(case=label):
                self.setUp()
                self.fill_the_places()
                if answered:
                    self.store.plan_put(make_advice(plan_id="p-no", case_id=self.case.case_id, resource_id=self.case.resource_id, state="declined", created_at=days_ago(3)))
                self.judged_again(self.case, owner={"lookedUp": True}, **change)
                (closed,) = self.settle()
                self.assertEqual((closed[0].plan_id, closed[0].preconditions["takenBack"]), (self.plan.plan_id, "released"))

    def test_a_stray_second_request_for_one_case_is_closed_quietly_and_two_cases_of_one_resource_get_one_request(self):
        self.store.plan_put(replace(self.plan, plan_id="p-stray", created_at=days_ago(2)))
        self.assertEqual(self.settle(), [], "it is no news: nobody saw it twice")
        self.assertEqual([p.plan_id for p in self.store.plans_held()], [self.plan.plan_id])
        self.assertEqual(self.store.plan_get("p-stray").preconditions["takenBack"], "released")
        self.store.case_put(unchecked(case_id="k-twin"))  # the same resource, found by another detector
        self.settle()
        self.assertEqual([p.plan_id for p in self.store.plans_held()], [self.plan.plan_id])

    def test_an_open_request_for_the_resource_closes_it_and_a_second_request_is_not_made_for_the_same_finding(self):
        self.store.plan_put(make_advice(plan_id="p-normal", case_id=self.case.case_id, resource_id=self.case.resource_id))
        (closed,) = self.settle()
        self.assertEqual(closed[0].plan_id, self.plan.plan_id)
        self.assertEqual([p.plan_id for p in self.store.plans_open()], ["p-normal"])

    def test_the_answer_of_a_person_is_not_taken_from_them_by_the_end_of_the_guard(self):
        self.answer(self.plan, "ask", note="who owns it?")
        self.judged_again(self.case, owner={"lookedUp": True})
        self.settle()
        self.assertEqual(len(self.store.decisions_of_plan(self.plan.plan_id)), 1, "the question stays in the record")

    def test_a_request_that_a_person_answered_since_the_list_was_read_is_not_closed_over_their_answer(self):
        self.store.case_put(replace(self.case, status="dropped"))
        self.answer(self.plan, "decline", reason="handled")
        self.assertEqual(self.settle(), [])
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "declined")

    def test_the_request_that_was_taken_back_for_the_rules_is_held_until_the_finding_is_judged_again(self):
        rule = self.put("rules")
        self.settle()
        held = self.held_of(rule.case_id)
        self.assertEqual((brief.held_of(held), self.store.plan_get("p-rules").state, self.store.plan_get("p-rules").preconditions["takenBack"]), ("rules", "expired", "rules"))
        self.assertEqual(self.settle(), [])
        self.judged_again(rule, recommendation="investigate", facts={"basis": "other", "proposal": "investigate", "asked": "delete", "metrics": {}})
        self.assertIsNotNone(self.approvals.advise(self.store.case_get(rule.case_id), (TINO,)), "judged again under the rules of today it is no deletion, and the normal path asks about it")
        self.assertEqual(len(self.settle()), 1, "and then nothing holds it back")
        self.assertEqual(self.store.plan_get(held.plan_id).preconditions["takenBack"], "released")


class TheHistoryWordsStayAsTheyAre(Base):
    def test_the_words_of_the_guards_and_the_new_word_and_the_kind_of_line(self):
        self.assertEqual(HELD_BACK, {"automation": "held back: managed by an automation", "unchecked": "held back: not checked who changed it", "impact": "held back: impact not checked",
                                     "rules": "held back: Meternaut's rules changed"})
        self.assertEqual(NOTHING_TO_SAY, "held back: nothing to say")
        self.assertIn("case.released", events.LOOP_KINDS)

    def test_a_request_that_is_taken_back_is_still_said_as_held_back_and_then_shown_as_a_held_finding(self):
        self.put("unchecked", plan_id="p-old", status="needs_human")
        self.store.plan_put(make_advice(plan_id="p-old", case_id="k-unchecked", resource_id=unchecked().resource_id, title="Check whether the virtual machine is still used"))
        ex = SimpleNamespace(approvals=self.approvals, approvers=lambda: (TINO,))
        self.assertEqual(upkeep.take_back(ex, self.history), {"held back: not checked who changed it": 1})
        (held,) = [line for line in self.lines.found if line["type"] == "case.held"]
        self.assertEqual(held["reason"], "held back: not checked who changed it")
        self.assertEqual((self.store.plan_get("p-old").state, brief.held_of(self.held_of("k-unchecked"))), ("expired", "unchecked"))
        self.assertEqual([line for line in self.lines.found if line["type"] == "case.released"], [])


class TheStoreKeepsThemApart(Base):
    def test_the_recent_plans_leave_out_the_held_ones_so_that_a_bulk_of_them_crowds_nothing_and_they_have_a_query_of_their_own(self):
        for reason in ("unchecked", "impact", "nothing"):
            self.put(reason)
        self.settle()
        self.store.plan_put(make_advice(plan_id="p-old", case_id="k-old", state="declined", created_at=days_ago(20)))
        self.assertEqual([p.plan_id for p in self.store.plans_recent(10)], ["p-old"])
        self.assertEqual(sorted(p.case_id for p in self.store.plans_held()), ["k-impact", "k-nothing", "k-unchecked"])
        self.assertEqual(self.store.plans_open(), [])


class TheLettersAndPagesLeaveOutWhatDoesNotWaitAnyMore(unittest.TestCase):
    def test_the_letter_does_not_mention_a_finding_that_was_dropped_since_its_request_was_made(self):
        console = held_console("unchecked")
        console.store.case_put(replace(console.store.case_get("k-unchecked"), status="dropped"))
        self.assertEqual(desk(console).sent, [])
        self.assertNotIn("/why/k-unchecked", console.get("/").links())


class TheWordsAreWrittenOnce(unittest.TestCase):
    def test_one_heading_one_sentence_and_one_need_for_each_reason_in_plain_words(self):
        self.assertEqual(tuple(brief.HOLD_WORDS), ("automation", *REASONS, "waiting"), "the words of the old reason stay for the held requests that were made before")
        for reason, (heading, why, needs) in brief.HOLD_WORDS.items():
            with self.subTest(reason=reason):
                self.assertTrue(heading and why and needs)
                self.assertLessEqual(len(heading), 60)
                self.assertLessEqual(why.count(". "), 1, "at most two short sentences")
                self.assertLessEqual(needs.count(". "), 1)
                for word in BANNED:
                    self.assertNotIn(word, (heading + why + needs).lower())

    def test_the_automation_sentence_says_how_long_ago_in_the_words_of_the_owner(self):
        found = brief.hold_of(replace(make_advice(), state=HELD, preconditions={"held": "automation"}), automation(), NOW)
        self.assertTrue(found.why.startswith("An automation changed this 2 days ago and would change it back"))
        for last, said in ((0, "today"), (1, "yesterday")):
            self.assertIn(f"changed this {said} and", brief.hold_of(replace(make_advice(), state=HELD, preconditions={"held": "automation"}),
                                                                    automation(owner={"automatedAt": days_ago(last)}), NOW).why)

    def test_a_request_that_is_no_held_one_has_no_hold(self):
        self.assertIsNone(brief.hold_of(make_advice(), automation(), NOW))
        self.assertIsNone(brief.hold_of(replace(make_advice(), state=HELD, preconditions={"held": "a reason that is none"}), automation(), NOW))
        self.assertIsNone(brief.hold_of(None, automation(), NOW))


def held_console(*reasons, now=NOW):
    """A console over a store in which a finding of each reason is held, with the request of each."""
    console = Console()
    approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: now)
    for reason in reasons:
        case = CASES[reason]()
        console.store.case_put(case)
        if reason == "rules":
            console.store.plan_put(make_advice(plan_id="p-rules", case_id=case.case_id, resource_id=case.resource_id, resource_name="pe-1", resource_group=GROUP,
                                               title="Consider deleting the private endpoint pe-1 in group rg-platform"))
            approvals.hold_back_empty()
    approvals.settle((TINO,))
    console.use(approvals)
    return console


class ThePageOfAHeldFinding(unittest.TestCase):
    def test_it_says_why_no_request_was_made_what_is_needed_and_who_may_know_and_offers_no_approve(self):
        console = held_console("unchecked")
        reply = console.get("/why/k-unchecked")
        self.assertEqual((reply.status, reply.problems), (200, []))
        why = brief.HOLD_WORDS["unchecked"][1]
        self.assertIn(brief.HOLD_WORDS["unchecked"][0], reply.content)
        self.assertIn(why, reply.main.text())
        self.assertIn(brief.HOLD_WORDS["unchecked"][2], reply.main.text())
        self.assertIn("Meternaut has not looked up who owns this resource yet.", reply.main.text())
        self.assertIn("Held back from a request", reply.main.find("p", class_="chips").text())
        for label in ("Worth acting on", "Approve", "Confirm this request"):
            self.assertFalse(reply.has_button(label), label)
        for label in ("Not worth it", "Ask or tell", "Decide later", "This is not mine"):
            self.assertTrue(reply.has_button(label), label)
        self.assertIn(f"{brief.ADVICE_ONLY_COUNT} {brief.ADVICE_WHO}", reply.main.text(), "a deletion is a change that Meternaut cannot make: it only lowers a count of units")
        self.assertIn("120", reply.main.text())
        self.assertIn("Held back. No request was made for the finding, and nothing changes in Azure.", reply.main.text())

    def test_the_words_of_each_reason_are_on_the_page_of_its_finding(self):
        console = held_console(*REASONS)
        for reason in REASONS:
            heading, _, needs = brief.HOLD_WORDS[reason]
            with self.subTest(reason=reason):
                reply = console.get(f"/why/k-{reason}")
                self.assertEqual(reply.status, 200)
                self.assertIn(heading, reply.content)
                self.assertIn(needs, reply.main.text())
                self.assertFalse(reply.has_button("Worth acting on"))

    def test_a_person_answers_it_on_its_page_with_the_form_that_exists(self):
        console = held_console("unchecked")
        form = console.get("/why/k-unchecked").form(has_button="Not worth it")
        reply = console.submit(form, "Not worth it", reason="handled")
        self.assertEqual(reply.status, 200)
        plan = next(p for p in console.store.plans_recent(10) if p.case_id == "k-unchecked")
        self.assertEqual((plan.state, console.store.case_get("k-unchecked").status), ("declined", "declined"))

    def test_an_approval_posted_for_it_is_refused_and_records_nothing(self):
        console = held_console("unchecked")
        plan = console.store.plans_held()[0]
        reply = console.post(f"/ok/{plan.plan_id}", {"decision": "approve", "code": plan.code, "nonce": console.store.nonce_new(TINO, plan.plan_id), "note": ""})
        self.assertEqual(reply.status, 409)
        self.assertEqual((console.store.decisions_of_plan(plan.plan_id), console.store.plan_get(plan.plan_id).state, console.store.case_get("k-unchecked").status), ([], HELD, "proposed"))

    def test_a_person_who_is_not_named_reads_it_and_cannot_answer(self):
        console = held_console("unchecked")
        reply = console.get("/why/k-unchecked", oid=MAYA)
        self.assertEqual(reply.status, 200)
        self.assertFalse(any(reply.has_button(label) for label in ("Not worth it", "Ask or tell", "Decide later", "This is not mine")))
        self.assertEqual(reply.forms(), [])

    def test_the_words_after_an_answer_say_where_the_finding_is_and_name_no_date_and_no_list_that_does_not_hold_it(self):
        where = 'You find it under "Held back" on the Decisions page, and on the page Savings found.'
        for button, fields, said in (("Ask or tell", {"note": "who owns it?"}, "Recorded with your name."), ("Decide later", {}, "Noted."),
                                     ("This is not mine", {}, "The finding is not brought up again for a month.")):
            with self.subTest(button=button):
                console = held_console("unchecked")
                reply = console.submit(console.get("/why/k-unchecked").form(has_button=button), button, **fields)
                self.assertEqual((reply.status, reply.problems), (200, []))
                text = reply.main.text()
                self.assertIn(said, text)
                if button != "This is not mine":
                    self.assertIn(where, text)
                for lie in ("open until", "stays open", "stays in your list", "right owner"):
                    self.assertNotIn(lie, text)
                self.assertNotRegex(text, r"\b20\d\d\b", "a held request never runs out by the clock: no date")

    def test_the_words_after_an_answer_to_a_request_that_is_open_are_still_those_of_a_request_that_is_open(self):
        console = Console()
        console.use(Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW))
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        reply = console.submit(console.get("/why/case0002").form(has_button="Ask or tell"), "Ask or tell", note="who owns it?")
        self.assertIn("The request stays open.", reply.main.text())
        reply = console.submit(console.get("/why/case0002").form(has_button="Decide later"), "Decide later")
        self.assertIn("The request stays in your list.", reply.main.text())


class TheDecisionsPageListsWhatIsHeldForThePerson(unittest.TestCase):
    def test_the_held_back_block_lists_each_finding_of_the_person_with_a_link_and_asks_for_nothing(self):
        console = held_console("unchecked", "impact")
        reply = console.get("/")
        self.assertIn("Held back: 2 findings", reply.content)
        self.assertEqual(reply.headings(1), ["Decisions"])
        self.assertIn("These findings are held back, so nothing is asked of you.", reply.content)
        links = [href for href in reply.links() if "/why/k-" in href]
        self.assertEqual(sorted(links), ["/why/k-impact", "/why/k-unchecked"])
        self.assertIn(brief.HOLD_WORDS["unchecked"][0], reply.content)
        self.assertNotIn("decision waits", reply.content)
        self.assertFalse(console.get("/", oid=MAYA).links().count("/why/k-unchecked"), "a person who is not named for it is not shown it")
        self.assertIn("Held back: 2 findings", console.get("/", oid=MAYA).content, "the count is everybody's, as it was")

    def test_a_held_finding_of_another_detector_is_listed_too_because_the_weekly_letter_links_to_this_page(self):
        console = held_console("nothing")
        reply = console.get("/")
        self.assertIn("Held back: 1 finding", reply.content)
        self.assertEqual([href for href in reply.links() if "/why/k-" in href], ["/why/k-nothing"])
        self.assertIn("Meternaut has nothing to say about it yet", reply.content)

    def test_a_held_finding_is_no_decision_and_no_row_of_the_page(self):
        console = held_console("unchecked")
        reply = console.get("/")
        self.assertNotIn("Ready to decide", reply.content)
        self.assertNotIn("Worth a closer look", reply.content)


class TheSavingsPageShowsThemInTheirOwnSection(unittest.TestCase):
    def setUp(self):
        self.console = held_console("unchecked", "impact", "nothing", "rules")
        self.console.store.case_put(finding("proposed"))
        self.console.store.case_put(finding("needs_human", case_id="c-advisor"))
        self.reply = self.console.get(SAVINGS)

    def test_the_section_has_one_heading_for_each_reason_and_one_line_for_each_finding(self):
        reply = self.reply
        self.assertEqual((reply.status, reply.problems), (200, []))
        headings = reply.headings(2)
        self.assertIn("Found, and held back from a request", headings)
        self.assertEqual(reply.headings(3), [brief.HOLD_WORDS[reason][0] for reason in REASONS], "a reason that no finding has is not a heading")
        for reason in REASONS:
            table = reply.table(f"held-{reason}")
            self.assertEqual(table.headers, ["Finding", "Saving or cost", "How sure", "Why no request was made", "Who may know"])
            self.assertEqual(len(table.rows), 1, reason)

    def test_each_has_the_figure_the_basis_the_evidence_and_the_guards_sentence(self):
        row = self.reply.table("held-unchecked").rows[0]
        self.assertEqual(row["Saving or cost"], f"Could save about $1,440 a year ($120 a month) {brief.BILL_BASIS}")
        self.assertIn("Confidence is medium.", row["How sure"])
        self.assertEqual(row["Why no request was made"], brief.HOLD_WORDS["unchecked"][1])
        self.assertEqual(row["Who may know"], "Meternaut has not looked up who owns this resource yet.")
        self.assertIn("/why/k-unchecked", self.reply.links())
        text = self.reply.main.text()
        for reason in REASONS:
            self.assertIn(brief.HOLD_WORDS[reason][2], text, reason)

    def test_a_finding_is_in_one_row_and_its_figure_is_counted_once(self):
        table = self.reply.table("savings")
        held = next(row for row in table.rows if row["What became of it"].startswith("Found, and held back"))
        waiting = next(row for row in table.rows if row["What became of it"].startswith("Waiting"))
        self.assertEqual((held["Findings"], waiting["Findings"]), ("4", "2"), "the four held findings are not in the row of what waits, which keeps the two ordinary ones")
        self.assertEqual(sum(int(row["Findings"]) for row in table.rows), 6)

    def test_the_tile_counts_the_held_findings_and_says_how_many_of_them_there_are(self):
        tiles = tiles_of(self.reply)
        found = tiles["Found in all"]
        self.assertEqual(found[:2], ("$3,240 a year", "It is the saving of 4 of 6 findings. The others have no saving figure. Of the 4, 2 are held back. The table says what each figure rests on."))
        self.assertEqual(found[0], "$3,240 a year", "two held findings of 120 a month, and 10 and 20 a month of the two others: each counted once")
        waiting = tiles["Waiting for a person"]
        self.assertEqual(waiting[0], "$360 a year", "what waits for a person leaves out what is held")
        self.assertEqual(list(tiles), ["Found in all", "Waiting for a person", "Saving measured"])

    def test_each_figure_says_what_it_rests_on_by_the_basis_of_its_finding(self):
        table = self.reply.table("savings")
        held = next(row for row in table.rows if row["What became of it"].startswith("Found, and held back"))
        self.assertIn(brief.BILL_BASIS, held["Saving a year"])
        waiting = next(row for row in table.rows if row["What became of it"].startswith("Waiting"))
        self.assertIn(brief.ADVISOR_BASIS, waiting["Saving a year"])
        self.assertIn(brief.BILL_BASIS, waiting["Saving a year"])

    def test_the_basis_of_a_held_finding_is_advisors_estimate_for_advisors_figure_and_the_bill_for_the_bill(self):
        console = Console()
        approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        for case in (finding("needs_human", case_id="c-bill", owner={}, detector="orphan-managed-disk", recommendation="delete", facts=MEASURED),
                     finding("needs_human", case_id="c-advisor", owner={}, recommendation="delete", facts=MEASURED, resource_id=f"{BASE}/Microsoft.Compute/disks/disk-advisor",
                             resource_name="disk-advisor", resource_group="rg-advisor")):
            console.store.case_put(case)
        approvals.settle((TINO,))
        table = console.get(SAVINGS).table("held-unchecked")
        cells = [row["Saving or cost"] for row in table.rows]
        self.assertEqual((sum(brief.BILL_BASIS in cell for cell in cells), sum(brief.ADVISOR_BASIS in cell for cell in cells)), (1, 1))

    def test_within_a_reason_what_is_at_stake_comes_first(self):
        console = Console()
        approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        for case_id, name, amount in (("c-small", "small-one", 15.0), ("c-large", "large-one", 300.0), ("c-middle", "middle-one", 90.0)):
            console.store.case_put(make_advice_case(case_id=case_id, resource_id=f"{BASE}/Microsoft.Foo/bars/{name}", resource_name=name, resource_type="microsoft.foo/bars",
                                                    resource_group=GROUP, plan_id=None, owner={}, recommendation="delete", saving_usd_month=amount, cost_usd_30d=amount, facts=MEASURED))
        approvals.settle((TINO,))
        table = console.get(SAVINGS).table("held-unchecked")
        order = [name for row in table.rows for name in ("large-one", "middle-one", "small-one") if name in row["Finding"]]
        self.assertEqual(order, ["large-one", "middle-one", "small-one"])

    def test_nothing_changes_for_a_store_that_holds_no_held_finding(self):
        console = Console()
        console.store.case_put(finding("proposed"))
        reply = console.get(SAVINGS)
        self.assertNotIn("Found, and held back from a request", reply.content)
        self.assertNotIn("Of which held back", reply.content)
        self.assertEqual(list(rows_of(reply))[:1], ["Waiting for a person"])


class TheWeeklyLetterMentionsThem(unittest.TestCase):
    def test_a_person_who_is_named_gets_one_short_block_with_the_figure_the_reason_and_what_is_needed(self):
        console = held_console("unchecked", "impact")
        graph = desk(console)
        (subject,) = graph.subjects()
        self.assertEqual(subject, "[Meternaut] 2 findings are held back from a request")
        content = graph.sent[0][1]["body"]["content"]
        lines = listed(content)
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(line.startswith("Consider deleting the disk disk-u. It could save about $1,440 a year. Meternaut cannot yet say who changed this resource") for line in lines), lines)
        self.assertTrue(all(brief.HOLD_WORDS[r][2] in " ".join(lines) for r in ("unchecked", "impact")))
        self.assertIn("These findings are held back from a request, so nothing is asked of you. Nothing changes in Azure.", content)
        self.assertEqual(content.count("https://"), 1, "one link, as every letter has")
        self.assertIn("See the held findings", content)
        for word in ("Approve", "Decline", "Worth acting on"):
            self.assertNotIn(word, content)

    def test_a_person_who_is_not_named_gets_none_and_one_who_answered_it_does_not_get_it_again(self):
        console = held_console("unchecked")
        plan = console.store.plans_held()[0]
        console.store.plan_put(replace(plan, approvers=(ENV_OPS,)))
        self.assertEqual(desk(console).sent, [], "nobody else is named")
        console.store.plan_put(replace(plan, approvers=(ENV_TINO,)))
        self.assertEqual(len(desk(console).sent), 1)
        console.store.decision_put(make_decision(plan_id=plan.plan_id, approver_oid=ENV_TINO, decision="ask", note="who owns it?"))
        self.assertEqual(desk(console).sent, [], "they have seen it")

    def test_the_block_follows_the_decisions_and_the_letter_keeps_its_number_of_lines_and_its_one_link(self):
        console = held_console("unchecked", "impact", "nothing", "rules")
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        graph = desk(console)
        self.assertEqual(graph.subjects(), ["[Meternaut] 1 decision waits for you"])
        content = graph.sent[0][1]["body"]["content"]
        lines = listed(content)
        self.assertEqual(len(lines), 1 + letters.MAX_HELD, "the decision and three of the four that are held, the largest first")
        self.assertEqual(lines[0], "Look at the virtual machine oversized-vm-1, because it may be larger than its use needs. It could save about $1,440 a year.")
        self.assertTrue(lines[1].startswith("Check whether the private endpoint pe-1 is still used. It costs $2,880 a year; nobody has worked out the saving. Meternaut's rules changed"), lines[1])
        self.assertIn("1 more is held back. It is on the page.", content)
        self.assertEqual(content.count("https://"), 1)

    def test_the_letter_is_sent_for_a_held_finding_alone_and_never_when_nothing_is_held_or_waits(self):
        self.assertIsNone(letters.digest_letter(SimpleNamespace(oid=TINO, name="Tino", mail="t@example.com", roles=("approver",)), "https://m.example", NOW, [], (), (), []))
        self.assertEqual(desk(Console()).sent, [])

    def test_a_resource_that_was_marked_do_not_touch_since_its_request_was_made_is_listed_and_written_about_no_more(self):
        console = held_console("unchecked", "impact")
        console.store.note_put(NoteRecord(note_id="n1", oid=TINO, kind="do_not_touch", text="leave it", scope_resource_id=unchecked().resource_id, created_at=stamp(NOW)))
        approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        approvals.settle((TINO,))  # the end of the next Watch
        console.use(approvals)
        self.assertEqual([plan.case_id for plan in console.store.plans_held()], ["k-impact"])
        self.assertNotIn("/why/k-unchecked", console.get("/").links())
        self.assertNotIn("disk-u", console.get(SAVINGS).main.text())
        content = desk(console).sent[0][1]["body"]["content"]
        self.assertEqual(len(listed(content)), 1)
        self.assertNotIn("disk-u", content)


class NoImmediateCardIsMadeForThem(unittest.TestCase):
    def test_a_person_who_chose_teams_gets_no_card_and_no_message_for_a_held_finding(self):
        world = CardWorld()
        world.introduce(CARD_MAYA)
        world.channel(CARD_MAYA)
        plan = advice_plan(state=HELD, preconditions={"family": "advise", "caseStatus": "needs_human", "held": "unchecked"})
        world.open_plan(plan, make_case(case_id=plan.case_id, status="needs_human", plan_id=plan.plan_id))
        self.assertEqual(world.run(), 0)
        self.assertEqual((world.queue_fake.calls, world.tries(CARD_MAYA)), ([], []))

    def test_the_same_plan_made_open_would_have_got_its_card_so_the_state_is_what_holds_it_back(self):
        world = CardWorld()
        world.introduce(CARD_MAYA)
        world.channel(CARD_MAYA)
        world.open_plan(advice_plan(), make_case(case_id="c1", status="needs_human", plan_id="p1a2b3c4d5"))
        self.assertGreater(world.run(), 0)


class TheFindingIsStillAnOpenQuestionForTheInvestigator(Base):
    def test_a_held_request_does_not_hide_the_finding_from_the_next_investigation_and_an_answer_does(self):
        case = self.put("unchecked")
        self.settle()
        questions = learning.OpenQuestions(self.store, NOW)
        self.assertTrue(questions.is_open(case), "no request waits for it: the AIs look at it again, and the normal path judges it")
        self.assertEqual([row.resource_id for row in questions.rows()], [case.resource_id])
        self.answer(self.held_of(case.case_id), "decline", reason="still-needed")
        self.assertFalse(learning.OpenQuestions(self.store, NOW).is_open(case), "a person said that it is not worth it: nobody is to be asked again for a month")

    def test_a_note_that_was_closed_because_nothing_holds_the_finding_any_more_teaches_nothing(self):
        case = self.put("unchecked")
        self.settle()
        plan = self.held_of(case.case_id)
        self.judged_again(case, owner={"lookedUp": True})
        self.approvals.advise(self.store.case_get(case.case_id), (TINO,))
        self.settle()
        closed = self.store.plan_get(plan.plan_id)
        found = brief.build_brief(self.store.case_get(case.case_id), closed, now=self.now)
        self.assertEqual((found.outcome.state, found.outcome.title), ("expired", "No longer held back"))
        self.assertEqual(found.outcome.lines, (brief.TAKEN_BACK["released"], "Nothing was changed in Azure."))
        self.assertIsNone(learning.lesson_of(closed, self.store.case_get(case.case_id), [], None, self.now))


class AFindingThatIsPricedAgainShowsOneFigure(unittest.TestCase):
    def test_the_letter_the_start_page_and_savings_found_say_what_the_case_says_after_a_new_price(self):
        console = held_console("unchecked")
        console.store.case_put(replace(console.store.case_get("k-unchecked"), saving_usd_month=400.0, cost_usd_30d=400.0))  # 120 a month when the request was made, 400 now
        approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        approvals.settle((TINO,))
        console.use(approvals)
        (plan,) = console.store.plans_held()
        self.assertEqual((plan.saving_usd_month, plan.waiting_costs_usd_day), (400.0, 13.33))
        savings = console.get(SAVINGS).table("held-unchecked").rows[0]["Saving or cost"]
        start = console.get("/").content
        letter = desk(console).sent[0][1]["body"]["content"]
        for where, text in (("Savings found", savings), ("the start page", start), ("the letter", letter)):
            self.assertIn("$4,800 a year", text, where)
            self.assertNotIn("$1,440", text, where)

    def test_a_request_that_is_held_for_another_reason_now_keeps_its_figure_too(self):
        store = MemoryStore(lambda: NOW)
        approvals = Approvals(store, ApprovalSettings(change_scopes=()), lambda: NOW)
        store.case_put(unchecked())
        approvals.settle((TINO,))
        store.case_put(replace(store.case_get("k-unchecked"), saving_usd_month=30.0))
        approvals.settle((TINO,))
        self.assertEqual([plan.saving_usd_month for plan in store.plans_held()], [30.0])


class RowKeyStore(MemoryStore):
    """A store that reads its plans as the Table store does: a query gives the first 1,000 rows that match, in the order of the row key (the id of a plan is random: no order of time), and only
    then are those sorted. A plan past the 1,000th row of a query is never seen by it."""
    PAGE = 1000

    def _rows(self, keep) -> list:
        return sorted((plan for plan in self.plans.values() if keep(plan)), key=lambda plan: plan.plan_id)[:self.PAGE]

    @staticmethod
    def _newest(rows) -> list:
        return sorted(rows, key=lambda plan: (plan.created_at, plan.plan_id), reverse=True)

    def plans_open(self):
        return self._newest(self._rows(lambda plan: plan.state in ("open", "approved")))

    def plans_held(self):
        return self._newest(self._rows(lambda plan: plan.state == HELD))

    def plans_recent(self, limit=50):
        return self._newest(self._rows(lambda plan: plan.state != HELD))[:limit]


class PastAThousandPlansNoHeldRequestIsLost(Base):
    def setUp(self):
        super().setUp()
        self.store = RowKeyStore(lambda: self.now)
        self.approvals = Approvals(self.store, ApprovalSettings(change_scopes=()), lambda: self.now)
        for number in range(1100):  # old answers about other resources, with ids that sort before the id of any request made now
            self.store.plan_put(make_advice(plan_id=f"0-{number:04d}", case_id=f"k-old-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/old{number}", resource_name=f"old{number}",
                                            state="declined", created_at=days_ago(100), expires_at=days_ago(99)))

    def test_settle_finds_the_held_request_and_makes_no_second_one_at_each_watch(self):
        case = self.put("unchecked")
        self.settle()
        (first,) = self.store.plans_held()
        for _ in range(3):
            self.assertEqual(self.settle(), [])
        self.assertEqual([plan.plan_id for plan in self.store.plans_held()], [first.plan_id])
        self.assertEqual((len(self.store.plans), self.store.case_get(case.case_id).plan_id), (1101, first.plan_id))

    def test_the_savings_page_the_start_page_and_the_letter_still_list_it(self):
        console = Console(store=self.store)
        approvals = Approvals(self.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        self.store.case_put(unchecked())
        approvals.settle((TINO,))
        console.use(approvals)
        self.assertEqual(len(console.get(SAVINGS).table("held-unchecked").rows), 1)
        self.assertEqual([href for href in console.get("/").links() if "/why/k-" in href], ["/why/k-unchecked"])
        sent = desk(console).sent
        self.assertEqual(len(sent), 1, "the letter is written")
        self.assertEqual(len(listed(sent[0][1]["body"]["content"])), 1)


class TwoCasesOfOneResourceGetOneHeldRequest(unittest.TestCase):
    def test_one_request_one_row_on_the_page_and_one_line_in_the_letter_also_when_both_are_found_in_one_pass(self):
        console = Console()
        approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        console.store.case_put(unchecked())
        console.store.case_put(unchecked(case_id="k-twin", detector="orphan-managed-disk"))  # the same resource, found by another detector
        approvals.settle((TINO,))
        approvals.settle((TINO,))
        console.use(approvals)
        self.assertEqual(len(console.store.plans_held()), 1)
        self.assertEqual(len(console.get(SAVINGS).table("held-unchecked").rows), 1)
        self.assertEqual(len([href for href in console.get("/").links() if "/why/k-" in href]), 1)
        self.assertEqual(len(listed(desk(console).sent[0][1]["body"]["content"])), 1)


class AFindingThatWaitsForAPlaceIsShownLikeTheOthers(unittest.TestCase):
    def test_its_page_the_savings_page_and_the_letter_say_that_a_place_is_awaited_and_ask_for_nothing(self):
        console = Console()
        console.store.case_put(unchecked(owner={"lookedUp": True}, plan_id="p-wait"))
        console.store.plan_put(replace(make_advice(plan_id="p-wait", case_id="k-unchecked", resource_id=unchecked().resource_id), state=HELD,
                                       preconditions={"family": "advise", "caseStatus": "needs_human", "held": "waiting"}))
        heading, why, needs = brief.HOLD_WORDS["waiting"]
        reply = console.get("/why/k-unchecked")
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertIn(heading, reply.content)
        self.assertIn(why, reply.main.text())
        self.assertIn(needs, reply.main.text())
        self.assertFalse(reply.has_button("Worth acting on"))
        self.assertEqual(len(console.get(SAVINGS).table("held-waiting").rows), 1)
        (line,) = listed(desk(console).sent[0][1]["body"]["content"])
        self.assertIn(why, line)
        self.assertIn(needs, line)


class AHeldRequestNeverEndsByTheClock(Base):
    """A request to a person never times out and never becomes invisible: a held request has no time at which it ends, whatever the time that it was stamped with."""

    def test_settle_keeps_it_and_it_stays_open_for_an_answer_a_year_after_it_was_made(self):
        case = self.put("unchecked")
        self.settle()
        plan = self.held_of(case.case_id)
        for days in (31, 400):
            with self.subTest(days=days):
                self.now = NOW + dt.timedelta(days=days)
                self.assertEqual(self.settle(), [])
                kept = self.store.plan_get(plan.plan_id)
                self.assertEqual((kept.state, self.held_of(case.case_id).plan_id), (HELD, plan.plan_id))
                found = brief.build_brief(self.store.case_get(case.case_id), kept, now=self.now, may_answer=True)
                self.assertEqual((found.state, found.answers), (HELD, ("decline", "not_mine", "ask", "later")))
        self.assertTrue(self.answer(plan, "ask", note="who owns it?").ok)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, HELD)

    def test_its_page_the_start_page_and_the_letter_still_show_it_a_year_later(self):
        console = held_console("unchecked")
        console.now = NOW + dt.timedelta(days=400)
        reply = console.get("/why/k-unchecked")
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertTrue(all(reply.has_button(label) for label in ("Not worth it", "Ask or tell", "Decide later", "This is not mine")))
        self.assertIn("Held back: 1 finding", console.get("/").content)
        (plan,) = console.store.plans_held()
        person = SimpleNamespace(oid=TINO, name="Tino", mail="t@example.com", roles=("approver",))
        self.assertIsNotNone(letters.digest_letter(person, "https://m.example", console.now, [], (), (), [(plan, console.store.case_get("k-unchecked"))]))


class TheHistoryPageDoesNotCountThemAsUnanswered(unittest.TestCase):
    def test_a_note_that_was_closed_by_meternaut_is_no_request_that_nobody_answered(self):
        console = Console()
        case = make_advice_case(status="needs_human")
        console.store.case_put(case)
        console.store.plan_put(make_advice(state="expired", expires_at=stamp(NOW - dt.timedelta(days=1)), created_at=stamp(NOW - dt.timedelta(days=4)),
                                           preconditions={"family": "advise", "held": "unchecked", "takenBack": "released"}))
        self.assertNotIn("request to look at a finding", console.get("/history").content)
        console.store.plan_put(make_advice(plan_id="p-quiet", state="expired", expires_at=stamp(NOW - dt.timedelta(days=1)), created_at=stamp(NOW - dt.timedelta(days=4))))
        self.assertIn("1 request to look at a finding", console.get("/history").content, "an ordinary request that Meternaut took back is still said")


if __name__ == "__main__":
    unittest.main()
