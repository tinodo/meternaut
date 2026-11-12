"""A finding that cannot say what to look at is not sent to a person: it is held back, kept in the History with the reason "held back: nothing to say", and counted.

A request that an earlier version made for such a finding, and that nobody has answered, is taken back. A request that a person answered, put off or asked about stays theirs. A fake of Azure
(tests/support.py) answers; everything in it is invented.
"""
import unittest

from support import SUBSCRIPTION, NOW
from test_names_and_cost import DEV, PROBLEM, a_subscription_with_a_bill, advisor_item, the_case
from test_run_loop import OID, Moving, loop_for, watch
from test_web_support import make_advice, make_advice_case, make_decision

from cases import brief, learning
from cases.approvals import NOTHING_TO_SAY

SUBSCRIPTION_ID = f"/subscriptions/{SUBSCRIPTION}"
GROUP_ID = f"{SUBSCRIPTION_ID}/resourceGroups/rg-demo"


def finding(**changes):
    """A case as an earlier version kept it for a subscription: named by its id, with no words of Advisor and a flat zero for a cost."""
    base = dict(case_id="kold00001", resource_id=SUBSCRIPTION_ID, resource_name=SUBSCRIPTION, resource_type="microsoft.subscriptions/subscriptions", resource_group="",
                subscription_id=SUBSCRIPTION, detector="advisor-cost", status="needs_human", recommendation="change", saving_usd_month=0.0, cost_usd_30d=0.0, plan_id="pold00001",
                facts={"category": "cost", "impact": "medium", "recommendationType": "none"})
    base.update(changes)
    return make_advice_case(**base)


def request_for(case, **changes):
    base = dict(plan_id=case.plan_id, case_id=case.case_id, resource_id=case.resource_id, resource_name=case.resource_name, resource_group=case.resource_group,
                subscription_id=case.subscription_id, title=f"Review the resource {case.resource_name}", saving_usd_month=None, waiting_costs_usd_day=None, approvers=(OID,))
    base.update(changes)
    return make_advice(**base)


class AFindingThatSaysNothingIsHeldBack(unittest.TestCase):
    """The request that read "Review the resource <id>": Azure Advisor's recommendation about a subscription, with none of Advisor's words. It has nothing to say, so no request is made."""

    @classmethod
    def setUpClass(cls):
        cls.clock = Moving()
        cls.offered: list = []
        cls.extras = loop_for(cls.clock, on_plan=lambda plan, case: cls.offered.append(plan.plan_id))
        cls.estate = a_subscription_with_a_bill()
        cls.estate.advisor = [advisor_item(shortDescription={})]
        cls.summary, cls.events, _ = watch(cls.estate, cls.extras, cls.clock)
        cls.case = the_case(cls.extras, "advisor-cost")

    def test_no_request_is_made_and_nobody_is_asked(self):
        self.assertEqual((self.extras.store.plans_open(), self.offered), ([], []))
        self.assertFalse(self.case.plan_id)

    def test_the_finding_stays_in_the_history_with_the_reason_and_its_name(self):
        (held,) = [e for e in self.events if e["type"] == "case.held"]
        self.assertEqual((held["caseId"], held["detector"], held["resourceType"], held["resourceName"]), (self.case.case_id, "advisor-cost", "microsoft.subscriptions/subscriptions", DEV))
        self.assertEqual(held["reason"], "held back: nothing to say")
        self.assertEqual(held["reason"], NOTHING_TO_SAY)
        self.assertNotIn(SUBSCRIPTION, str(held), "the history says the name, not the id")

    def test_the_case_is_kept_with_its_name_and_its_bill_so_nothing_is_lost(self):
        self.assertEqual((self.case.subscription_name, self.case.resource_name, self.case.cost_state, self.case.cost_usd_30d), (DEV, DEV, "lines", 148.95))

    def test_it_is_counted_in_the_run_and_said_in_a_note_and_in_the_end_of_the_run(self):
        self.assertEqual(self.summary.held, 1)
        record = self.extras.store.runs_recent()[0]
        self.assertEqual(record.held, 1)
        self.assertIn("1 finding held back: nothing to say", record.notes)
        finished = self.events[-1]
        self.assertEqual((finished["type"], finished["heldBack"]), ("run.finished", 1))

    def test_the_run_still_ends_well_and_the_other_findings_are_taken_up(self):
        self.assertTrue(self.summary.ok)
        self.assertEqual(self.summary.cases, 1)

    def test_it_is_not_judged_again_at_the_next_watch_so_it_is_not_counted_twice(self):
        self.clock.advance(hours=3)
        again, events, _ = watch(a_subscription_with_a_bill(), self.extras, self.clock)
        self.assertEqual(again.held, 0)
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])


class AFindingThatGetsItsWordsIsAskedAbout(unittest.TestCase):
    def test_the_same_finding_with_the_words_of_advisor_gets_its_request_and_is_not_held_back(self):
        clock = Moving()
        offered: list = []
        extras = loop_for(clock, on_plan=lambda plan, case: offered.append(plan.plan_id))
        estate = a_subscription_with_a_bill()
        estate.advisor = [advisor_item(shortDescription={})]
        first, _, _ = watch(estate, extras, clock)
        self.assertEqual((first.held, extras.store.plans_open()), (1, []))
        clock.advance(days=8)  # the finding is judged again after the days that the loop waits
        estate = a_subscription_with_a_bill()
        second, events, _ = watch(estate, extras, clock)
        (plan,) = extras.store.plans_open()
        self.assertEqual((second.held, offered), (0, [plan.plan_id]))
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])
        self.assertTrue(plan.title.startswith(PROBLEM))


class WhatSaysNothing(unittest.TestCase):
    def test_a_subscription_or_a_resource_group_without_words_says_nothing(self):
        self.assertTrue(brief.says_nothing(finding()))
        self.assertTrue(brief.says_nothing(finding(resource_id=GROUP_ID, resource_name="rg-demo", resource_type="microsoft.resources/resourcegroups")))

    def test_the_words_of_advisor_are_enough_to_say_what_to_look_at(self):
        words = {"problem": "Buy a reservation", "solution": "Reserve the machines that run all month"}
        self.assertFalse(brief.says_nothing(finding(advice=words)))
        self.assertFalse(brief.says_nothing(finding(advice=words, resource_id=GROUP_ID, resource_name="rg-demo")))

    def test_a_resource_that_has_a_name_says_what_it_is_and_one_that_is_only_an_id_of_a_kind_without_words_does_not(self):
        named = finding(resource_id=f"{GROUP_ID}/providers/Microsoft.Foo/bars/my-bar", resource_name="my-bar", resource_type="microsoft.foo/bars", resource_group="rg-demo")
        self.assertFalse(brief.says_nothing(named))
        only_an_id = finding(resource_id=f"{GROUP_ID}/providers/Microsoft.Foo/bars/a", resource_name="aaaaaaaa-1111-4222-8333-444444444444", resource_type="microsoft.foo/bars",
                             resource_group="rg-demo")
        self.assertTrue(brief.says_nothing(only_an_id))
        a_path = finding(resource_id=f"{GROUP_ID}/providers/Microsoft.Foo/bars/a", resource_name="/subscriptions/x/y", resource_type="microsoft.foo/bars", resource_group="rg-demo")
        self.assertTrue(brief.says_nothing(a_path))

    def test_a_resource_of_a_kind_that_has_words_says_something_even_when_its_name_is_an_id(self):
        disk = finding(resource_id=f"{GROUP_ID}/providers/Microsoft.Compute/disks/d", resource_name="aaaaaaaa-1111-4222-8333-444444444444", resource_type="microsoft.compute/disks",
                       resource_group="rg-demo")
        self.assertFalse(brief.says_nothing(disk))

    def test_no_case_says_nothing(self):
        self.assertFalse(brief.says_nothing(None))


class AnOpenRequestThatSaysNothingIsTakenBack(unittest.TestCase):
    """A request that an earlier version made, titled "Review the resource <id>": the Watch takes it back when nobody has answered it, and a person who has is left alone."""

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store
        self.case = finding()
        self.plan = request_for(self.case, expires_at="2026-11-07T09:00:00Z")
        self.store.case_put(self.case)
        self.store.plan_put(self.plan)

    def watch(self):
        from support import FakeEstate
        return watch(FakeEstate(), self.extras, self.clock)

    def test_the_request_that_nobody_answered_is_closed_at_once_and_said_in_the_history_and_counted(self):
        summary, events, _ = self.watch()
        plan = self.store.plan_get(self.plan.plan_id)
        self.assertEqual((plan.state, self.store.plans_open()), ("expired", []))
        self.assertEqual(plan.expires_at, "2026-11-04T12:00:00Z", "it ends now, not at the time that was set for it")
        (held,) = [e for e in events if e["type"] == "case.held"]
        self.assertEqual((held["caseId"], held["reason"]), (self.case.case_id, "held back: nothing to say"))
        self.assertEqual(summary.held, 1)
        self.assertEqual(self.store.runs_recent()[0].held, 1)
        self.assertIn("1 finding held back: nothing to say", [e["note"] for e in events if e["type"] == "run.note"])

    def test_the_case_keeps_its_place_in_the_history(self):
        self.watch()
        self.assertEqual(self.store.case_get(self.case.case_id).status, "needs_human")

    def test_it_is_no_lesson_that_nobody_answered(self):
        self.watch()
        self.clock.advance(days=4)
        learning.sync(self.store, self.clock())
        self.assertEqual(self.store.lessons_recent(), [], "a request that was taken back was never unanswered: nobody was asked")

    def test_a_request_that_a_person_answered_or_put_off_stays_open(self):
        self.store.decision_put(make_decision(plan_id=self.plan.plan_id, approver_oid=OID, decision="later"))
        summary, events, _ = self.watch()
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, summary.held), ("open", 0))
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])

    def test_a_request_that_has_something_to_say_stays_open(self):
        said = finding(advice={"problem": "Buy a reservation", "solution": "Reserve the machines that run all month"})
        self.store.case_put(said)
        summary, _, _ = self.watch()
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, summary.held), ("open", 0))

    def test_a_request_of_a_change_is_never_taken_back(self):
        self.store.plan_put(request_for(self.case, family="delete-disk", preconditions={"family": "delete-disk"}))
        summary, _, _ = self.watch()
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, summary.held), ("open", 0))

    def test_the_time_of_a_second_watch_finds_nothing_more_to_take_back(self):
        self.watch()
        self.clock.advance(hours=3)
        summary, events, _ = self.watch()
        self.assertEqual((summary.held, [e for e in events if e["type"] == "case.held"]), (0, []))


if __name__ == "__main__":
    unittest.main()
