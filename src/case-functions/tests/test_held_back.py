"""A finding that cannot say what to look at is not sent to a person: it is held back, kept in the History with the reason "held back: nothing to say", and counted.

A request that an earlier version made for such a finding, and that nobody has answered, is taken back. A request that a person answered, put off or asked about stays theirs. A fake of Azure
(tests/support.py) answers; everything in it is invented.
"""
import unittest
from dataclasses import replace

from support import SUBSCRIPTION, NOW
from test_names_and_cost import DEV, PROBLEM, a_subscription_with_a_bill, advisor_item, the_case
from test_run_loop import GROUP, OID, Moving, loop_for, watch
from test_web_support import make_advice, make_advice_case, make_decision, page_of, priced_facts

from cases import brief, learning
from cases.advisor import ADVICE_NONE
from cases.approvals import ASKED_UNDER, ASKING_RULES, NOTHING_TO_SAY, RULES_CHANGED, UNCONFIRMED, UNMEASURED, why_not_ask
from cases.decide import NO_MEASUREMENT

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
    """The request that read "Review the resource <id>": Azure Advisor's recommendation about a subscription, with none of Advisor's words, no figure, no product and no term. It has nothing to say,
    so no request is made."""

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
        self.assertEqual(self.extras.store.plan_get(self.case.plan_id).state, "held", "it is shown in a request of its own that nobody is asked to approve (cases/approvals.py settle)")

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

    def test_it_is_not_said_again_at_the_next_watch_so_it_is_not_counted_twice(self):
        self.clock.advance(hours=3)
        same = a_subscription_with_a_bill()
        same.advisor = [advisor_item(shortDescription={})]
        again, events, _ = watch(same, self.extras, self.clock)
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
        clock.advance(days=8)  # the finding is asked about again after the days that the loop waits
        estate = a_subscription_with_a_bill()
        second, events, _ = watch(estate, extras, clock)
        (plan,) = extras.store.plans_open()
        self.assertEqual((second.held, offered), (0, [plan.plan_id]))
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])
        self.assertTrue(plan.title.startswith(PROBLEM))


TYPED = {"annualSavingsAmount": "240", "savingsCurrency": "USD", "sku": "Standard_D2s_v6", "term": "P1Y", "lookbackPeriod": "30", "region": "swedencentral", "qty": "1", "scope": "Single",
         "recommendationSubCategory": "Reservations"}


class AnAdvisorRecommendationWithNoWordsButWithAFigureIsNotHeldBack(unittest.TestCase):
    """Azure Advisor's recommendation about a subscription, with none of Advisor's words but with a figure, a product and a term. It is Advisor's own claim, and its figure and rows say what to look at,
    so no rule that holds back a finding that says nothing (brief.says_nothing) holds it back: the request is made, in words of code (docs/proposals/22-advisor-first-class.md)."""

    @classmethod
    def setUpClass(cls):
        cls.clock = Moving()
        cls.offered: list = []
        cls.extras = loop_for(cls.clock, on_plan=lambda plan, case: cls.offered.append(plan.plan_id))
        cls.estate = a_subscription_with_a_bill()
        cls.estate.advisor = [advisor_item(shortDescription={}, extendedProperties=TYPED)]
        cls.summary, cls.events, _ = watch(cls.estate, cls.extras, cls.clock)
        cls.case = the_case(cls.extras, "advisor-cost")

    def test_a_request_is_made_and_the_person_is_asked(self):
        (plan,) = self.extras.store.plans_open()
        self.assertEqual((self.offered, self.case.plan_id), ([plan.plan_id], plan.plan_id))

    def test_it_is_titled_by_what_it_is_about_in_words_of_code_and_never_by_the_words_review_the_resource(self):
        (plan,) = self.extras.store.plans_open()
        self.assertEqual(plan.title, f"{ADVICE_NONE['problem']}: subscription {DEV}")
        self.assertNotIn("Review the resource", plan.title)
        self.assertNotIn(SUBSCRIPTION, plan.title)

    def test_nothing_is_held_back_and_nothing_is_counted_as_held(self):
        self.assertEqual([e for e in self.events if e["type"] == "case.held"], [])
        self.assertEqual((self.summary.held, self.extras.store.runs_recent()[0].held, self.events[-1]["heldBack"]), (0, 0, 0))

    def test_the_case_is_kept_with_its_name_and_its_bill(self):
        self.assertEqual((self.case.subscription_name, self.case.resource_name, self.case.cost_state, self.case.cost_usd_30d), (DEV, DEV, "lines", 148.95))

    def test_the_run_ends_well_with_the_one_case(self):
        self.assertTrue(self.summary.ok)
        self.assertEqual((self.summary.cases, self.summary.needs_human), (1, 1))

    def test_the_next_watch_asks_nobody_again_for_a_request_that_is_open(self):
        (first,) = self.extras.store.plans_open()
        self.clock.advance(hours=3)
        same = a_subscription_with_a_bill()
        same.advisor = [advisor_item(shortDescription={}, extendedProperties=TYPED)]
        again, events, _ = watch(same, self.extras, self.clock)
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])


class WhatSaysNothing(unittest.TestCase):
    def test_a_subscription_or_a_resource_group_without_words_says_nothing(self):
        self.assertTrue(brief.says_nothing(finding()))
        self.assertTrue(brief.says_nothing(finding(resource_id=GROUP_ID, resource_name="rg-demo", resource_type="microsoft.resources/resourcegroups")))

    def test_the_words_of_advisor_are_enough_to_say_what_to_look_at(self):
        words = {"problem": "Buy a reservation", "solution": "Reserve the machines that run all month"}
        self.assertFalse(brief.says_nothing(finding(advice=words)))
        self.assertFalse(brief.says_nothing(finding(advice=words, resource_id=GROUP_ID, resource_name="rg-demo")))

    def test_the_recommendations_of_advisor_are_enough_only_when_they_hold_a_figure_a_product_or_a_term(self):
        empty = ["", None, "", "", None, "", None, ""]
        said = {"type": "t", "sub": "Reservations", "n": 1, "added": 1, "skipped": 0, "currencies": [], "usd": 120.0, "low": 120.0, "high": 120.0, "alt": "", "more": 0,
                "rows": [["Standard_D2s_v6", 1, "swedencentral", "P1Y", 120.0, "USD", 30, "Single"]]}
        self.assertFalse(brief.says_nothing(finding(facts={"category": "cost", "advisor": said})))
        nothing = {**said, "usd": 0.0, "low": 0.0, "high": 0.0, "rows": [empty]}
        self.assertTrue(brief.says_nothing(finding(facts={"category": "cost", "advisor": nothing})), "no figure, no product and no term: the old held-back behaviour")
        self.assertFalse(brief.says_nothing(finding(facts={"category": "cost", "advisor": {**nothing, "usd": 5.0}})), "a figure is something to say")
        self.assertFalse(brief.says_nothing(finding(facts={"category": "cost", "advisor": {**nothing, "rows": [["Standard_D2s_v6"] + empty[1:]]}})), "a product is something to say")
        self.assertFalse(brief.says_nothing(finding(facts={"category": "cost", "advisor": {**nothing, "rows": [empty[:3] + ["P1Y"] + empty[4:]]}})), "a term is something to say")
        self.assertTrue(brief.says_nothing(finding(facts={"category": "cost", "advisor": {**said, "rows": []}})), "a digest that is not as it should be says nothing")

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


def unpriced(**changes):
    """A finding of the investigation about an AI services account that costs a great deal, with no saving that code priced: what an earlier Watch asked a person about on one number."""
    base = dict(case_id="kunpriced1", detector="investigation", status="needs_human", recommendation="investigate", confidence=0.4, saving_usd_month=None, cost_usd_30d=848.0, objections=(),
                resource_id=f"{GROUP_ID}/providers/Microsoft.CognitiveServices/accounts/contoso-ai", resource_name="contoso-ai", resource_type="microsoft.cognitiveservices/accounts",
                resource_group="rg-demo", subscription_id=SUBSCRIPTION, plan_id="punpriced1", owner={"lookedUp": True, "automatedAt": ""}, advice={},
                facts={"basis": "other", "proposal": "investigate", "metrics": {"Requests": 2929}})
    base.update(changes)
    return make_advice_case(**base)


class AnOpenRequestForAFindingThatNoSavingBacksIsTakenBack(unittest.TestCase):
    """A finding of the investigation is asked about only when code priced a saving for it (approvals.UNPRICED). A request that an earlier Watch made for one that has none is taken back at the next
    Watch with the reason `rules`: once, in words, in the History, and never when a person answered it."""

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store
        self.case = unpriced()
        self.plan = request_for(self.case, title="Check whether the account contoso-ai in group rg-demo is still used", resource_name="contoso-ai", resource_group="rg-demo",
                                created_at="2026-11-01T09:00:00Z", expires_at="")
        self.store.case_put(self.case)
        self.store.plan_put(self.plan)

    def watch(self):
        from support import FakeEstate
        return watch(FakeEstate(), self.extras, self.clock)

    def test_the_request_that_nobody_answered_is_taken_back_with_the_reason_rules_said_in_the_history_and_counted_once(self):
        summary, events, _ = self.watch()
        plan = self.store.plan_get(self.plan.plan_id)
        self.assertEqual((plan.state, plan.preconditions["takenBack"], plan.expires_at, self.store.plans_open()), ("expired", "rules", "2026-11-04T12:00:00Z", []))
        (held,) = [e for e in events if e["type"] == "case.held"]
        self.assertEqual((held["caseId"], held["detector"], held["resourceType"], held["reason"]), (self.case.case_id, "investigation", "microsoft.cognitiveservices/accounts", RULES_CHANGED))
        self.assertEqual((summary.held, self.store.runs_recent()[0].held), (1, 1))
        self.assertIn(f"1 finding {RULES_CHANGED}", [e["note"] for e in events if e["type"] == "run.note"])
        self.assertEqual(self.store.case_get(self.case.case_id).status, "needs_human", "the finding stays what it was: an open question that the Investigator gets again")
        self.clock.advance(hours=3)
        again, events, _ = self.watch()
        self.assertEqual((again.held, [e for e in events if e["type"] == "case.held"], self.store.plan_get(self.plan.plan_id)), (0, [], plan), "a second Watch takes back nothing more")

    def test_the_page_says_taken_back_and_why_and_nothing_was_changed_in_azure(self):
        self.watch()
        after, kept = self.store.plan_get(self.plan.plan_id), self.store.case_get(self.case.case_id)
        shown = brief.build_brief(kept, after, now=NOW)
        self.assertEqual((shown.outcome.state, shown.outcome.title), ("expired", "Taken back"))
        self.assertEqual(shown.outcome.lines, (brief.TAKEN_BACK["rules"], "Nothing was changed in Azure."))
        self.assertEqual(brief.taken_back(after), "rules")
        _, text = page_of(kept, after)
        self.assertIn("Taken back", text)
        self.assertIn("Meternaut took this request back because its rules changed. It asked about this resource on less evidence than its rules ask for now.", text)
        self.assertIn("Nothing was changed in Azure.", text)

    def test_a_finding_that_no_saving_backs_gets_no_held_request_either_and_is_not_asked_about_again(self):
        self.watch()
        self.assertEqual((self.store.plans_open(), self.store.plans_held()), ([], []))
        self.clock.advance(days=8)
        self.watch()
        self.assertEqual((self.store.plans_open(), self.store.plans_held()), ([], []))

    def test_a_request_that_a_person_answered_in_any_way_is_never_taken_back(self):
        for decision, state in (("approve", "consumed"), ("decline", "declined"), ("ask", "open"), ("later", "open"), ("not_mine", "open")):
            with self.subTest(decision):
                self.setUp()
                self.store.decision_put(make_decision(plan_id=self.plan.plan_id, approver_oid=OID, decision=decision))
                if state != "open":
                    self.store.plan_put(replace(self.plan, state=state))
                summary, events, _ = self.watch()
                self.assertEqual((self.store.plan_get(self.plan.plan_id).state, summary.held, [e for e in events if e["type"] == "case.held"]), (state, 0, []))

    def test_what_is_not_an_open_request_for_this_kind_of_finding_is_never_taken_back(self):
        advisor = finding(advice={"problem": "Buy a reservation", "solution": "Reserve the machines that run all month"})
        rule_based = unpriced(case_id="krule1", detector="orphan-private-endpoint", plan_id="prule1", objections=(), cost_usd_30d=80.0)
        for label, case, plan in (("a change that is open", self.case, request_for(self.case, family="delete-disk", preconditions={"family": "delete-disk"}, plan_id=self.plan.plan_id)),
                                  ("a recommendation of Advisor", advisor, request_for(advisor, title="Buy a reservation: subscription")),
                                  ("a finding of a rule-based detector", rule_based, request_for(rule_based, title="Check whether the resource contoso-ai is still used")),
                                  ("a held request", self.case, request_for(self.case, plan_id=self.plan.plan_id, state="held", preconditions={"family": "advise", "held": "nothing"}))):
            with self.subTest(label):
                self.setUp()
                self.store.case_put(case)
                self.store.plan_put(plan)
                summary, events, _ = self.watch()
                self.assertEqual((self.store.plan_get(plan.plan_id).state, [e for e in events if e["type"] == "case.held" and e["caseId"] == case.case_id]), (plan.state, []))

    def test_a_request_for_a_finding_that_code_priced_stays_open(self):
        self.store.case_put(replace(self.case, saving_usd_month=120.0))
        summary, events, _ = self.watch()
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, summary.held, [e for e in events if e["type"] == "case.held"]), ("open", 0, []))

    def test_a_request_about_something_in_a_group_of_meternauts_own_is_left_alone_and_the_same_request_outside_it_is_taken_back(self):
        mine = unpriced(case_id="kmine1", plan_id="pmine1", resource_group=GROUP, resource_name="contoso-mine")
        self.store.case_put(mine)
        self.store.plan_put(request_for(mine, title=f"Check whether the account contoso-mine in group {GROUP} is still used", created_at="2026-11-01T09:00:00Z", expires_at=""))
        summary, events, _ = self.watch()
        self.assertEqual((self.store.plan_get("pmine1").state, [e for e in events if e["type"] == "case.held" and e["caseId"] == mine.case_id]), ("open", []))
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, summary.held), ("expired", 1))

    def test_a_request_that_the_old_clock_closed_and_that_comes_back_is_taken_back_in_the_same_watch_and_never_chased(self):
        closed = request_for(self.case, state="expired", created_at="2026-10-26T12:00:00Z", expires_at="2026-10-29T12:00:00Z")
        self.store.plan_put(closed)
        self.store.case_put(replace(self.case, status="expired"))
        summary, events, _ = self.watch()
        plan = self.store.plan_get(self.plan.plan_id)
        self.assertEqual(len([e for e in events if e["type"] == "plan.revived"]), 1, "it came back: nobody had answered it, and no clock closes a request")
        self.assertEqual((plan.state, plan.preconditions["takenBack"], self.store.plans_open(), summary.held), ("expired", "rules", [], 1))
        self.assertEqual(self.store.case_get(self.case.case_id).status, "needs_human")


def unasked(reason, **changes):
    """A finding of the investigation that code priced a saving for and that an earlier Watch asked a person about on less than the rules ask for now: nothing was measured of the resource (`unmeasured`), or
    its saving is a switch to another price of the list that the second AI did not agree to (`unconfirmed`)."""
    own = {UNMEASURED: dict(objections=(NO_MEASUREMENT,), facts={"basis": "other", "proposal": "change", "metrics": {}}),
           UNCONFIRMED: dict(objections=("It may not be possible.",), facts=priced_facts("alternative", metrics={"Traffic": 5}), learned={"skeptic": "disagree"})}[reason]
    return unpriced(**{"case_id": f"k{reason}", "plan_id": f"p{reason}", "recommendation": "change", "saving_usd_month": 40.0, "cost_usd_30d": 200.0, **own, **changes})


class AnOpenRequestForAFindingThatNothingMeasuredOrThatNobodyConfirmedIsTakenBack(unittest.TestCase):
    """A finding of the investigation is asked about only when something was measured of the resource's use (approvals.UNMEASURED) and, for a switch to another price of the list, when the second AI
    agreed (UNCONFIRMED). A request that an earlier Watch made without that has no ASKED_UNDER, and is taken back at the next Watch with the reason `rules`: once, in words, in the History, and never when a
    person answered it. A request that was made under today's rules is never taken back for them, whatever a later judgment of its finding says."""

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store

    def made(self, reason, asked_under=False, **changes):
        """The finding for `reason` and its open request, as the Watch before these rules made it (no ASKED_UNDER), or as today's rules make it."""
        case = unasked(reason, **changes)
        pre = {"family": "advise", "caseStatus": "needs_human", **({ASKED_UNDER: ASKING_RULES} if asked_under else {})}
        plan = request_for(case, title="Check whether the account contoso-ai in group rg-demo is still used", resource_name="contoso-ai", resource_group="rg-demo", saving_usd_month=case.saving_usd_month,
                           created_at="2026-11-01T09:00:00Z", expires_at="", preconditions=pre)
        self.store.case_put(case)
        self.store.plan_put(plan)
        return case, plan

    def watch(self):
        from support import FakeEstate
        return watch(FakeEstate(), self.extras, self.clock)

    def each(self):
        for reason in (UNMEASURED, UNCONFIRMED):
            with self.subTest(reason):
                self.setUp()
                yield reason

    def test_the_request_that_nobody_answered_is_taken_back_with_the_reason_rules_said_in_the_history_counted_and_asked_about_no_more(self):
        for reason in self.each():
            case, plan = self.made(reason)
            self.assertEqual(why_not_ask(case), reason)
            summary, events, _ = self.watch()
            taken = self.store.plan_get(plan.plan_id)
            self.assertEqual((taken.state, taken.preconditions["takenBack"], taken.expires_at, self.store.plans_open(), self.store.plans_held()), ("expired", "rules", "2026-11-04T12:00:00Z", [], []))
            (held,) = [e for e in events if e["type"] == "case.held"]
            self.assertEqual((held["caseId"], held["detector"], held["reason"]), (case.case_id, "investigation", RULES_CHANGED))
            self.assertEqual((summary.held, self.store.runs_recent()[0].held), (1, 1))
            self.assertIn(f"1 finding {RULES_CHANGED}", [e["note"] for e in events if e["type"] == "run.note"])
            kept = self.store.case_get(case.case_id)
            self.assertEqual(kept.status, "needs_human", "the finding stays what it was")
            self.assertTrue(learning.OpenQuestions(self.store, NOW).is_open(kept), "the Investigator is given it again, with the reason")
            self.assertEqual([row.why for row in learning.OpenQuestions(self.store, NOW).rows()], [reason])
            self.clock.advance(hours=3)
            again, events, _ = self.watch()
            self.assertEqual((again.held, [e for e in events if e["type"] == "case.held"], self.store.plan_get(plan.plan_id), self.store.plans_held()), (0, [], taken, []), "a second Watch takes back nothing more")
            self.clock.advance(days=8)
            self.watch()
            self.assertEqual((self.store.plans_open(), self.store.plans_held()), ([], []), "and nobody is asked about it again")

    def test_the_page_says_taken_back_and_why_and_nothing_was_changed_in_azure(self):
        for reason in self.each():
            case, plan = self.made(reason)
            self.watch()
            after, kept = self.store.plan_get(plan.plan_id), self.store.case_get(case.case_id)
            shown = brief.build_brief(kept, after, now=NOW)
            self.assertEqual((shown.outcome.state, shown.outcome.title, shown.outcome.lines), ("expired", "Taken back", (brief.TAKEN_BACK["rules"], "Nothing was changed in Azure.")))
            _, text = page_of(kept, after)
            self.assertIn("Taken back", text)
            self.assertIn("Meternaut took this request back because its rules changed.", text)

    def test_a_request_that_was_made_under_todays_rules_is_never_taken_back_when_its_finding_is_judged_again_without_a_measurement_or_with_another_verdict(self):
        for reason in self.each():
            case, plan = self.made(reason, asked_under=True)
            self.assertEqual(why_not_ask(case), reason, "the finding as it is judged now would not be asked about")
            summary, events, _ = self.watch()
            self.assertEqual((self.store.plan_get(plan.plan_id).state, summary.held, [e for e in events if e["type"] == "case.held"]), ("open", 0, []))
            self.clock.advance(days=8)
            self.watch()
            self.assertEqual(self.store.plan_get(plan.plan_id).state, "open")

    def test_a_request_that_a_person_answered_in_any_way_is_never_taken_back(self):
        for reason in self.each():
            for decision, state in (("approve", "consumed"), ("decline", "declined"), ("ask", "open"), ("later", "open"), ("not_mine", "open")):
                with self.subTest(reason=reason, decision=decision):
                    self.setUp()
                    _, plan = self.made(reason)
                    self.store.decision_put(make_decision(plan_id=plan.plan_id, approver_oid=OID, decision=decision))
                    if state != "open":
                        self.store.plan_put(replace(plan, state=state))
                    summary, events, _ = self.watch()
                    self.assertEqual((self.store.plan_get(plan.plan_id).state, summary.held, [e for e in events if e["type"] == "case.held"]), (state, 0, []))

    def test_what_is_not_an_open_request_for_this_kind_of_finding_is_never_taken_back(self):
        for reason in self.each():
            case, plan = self.made(reason)
            advisor = unasked(reason, case_id="kadvisor", plan_id="padvisor", detector="advisor-cost", resource_id=SUBSCRIPTION_ID, resource_name=SUBSCRIPTION, resource_group="",
                              resource_type="microsoft.subscriptions/subscriptions", advice={"problem": "Buy a reservation", "solution": "Reserve the machines that run all month"})
            rule_based = unasked(reason, case_id="krule", plan_id="prule", detector="orphan-private-endpoint")
            for label, other, request in (("a change that is open", case, request_for(case, family="delete-disk", preconditions={"family": "delete-disk"}, plan_id=plan.plan_id)),
                                          ("a recommendation of Advisor", advisor, request_for(advisor, title="Buy a reservation: subscription")),
                                          ("a finding of a rule-based detector", rule_based, request_for(rule_based, title="Check whether the resource contoso-ai is still used")),
                                          ("a held request", case, request_for(case, plan_id=plan.plan_id, state="held", preconditions={"family": "advise", "held": "nothing"}))):
                with self.subTest(reason=reason, case=label):
                    self.setUp()
                    self.store.case_put(other)
                    self.store.plan_put(request)
                    summary, events, _ = self.watch()
                    self.assertEqual((self.store.plan_get(request.plan_id).state, [e for e in events if e["type"] == "case.held" and e["caseId"] == other.case_id]), (request.state, []))

    def test_a_request_for_a_finding_that_was_measured_and_confirmed_stays_open_whenever_it_was_made(self):
        measured = {UNMEASURED: dict(objections=()), UNCONFIRMED: dict(learned={"skeptic": "agree"}, confidence=0.9)}
        for reason in self.each():
            _, plan = self.made(reason, **measured[reason])
            summary, events, _ = self.watch()
            self.assertEqual((self.store.plan_get(plan.plan_id).state, summary.held, [e for e in events if e["type"] == "case.held"]), ("open", 0, []))

    def test_a_switch_that_the_second_ai_agreed_to_is_taken_back_when_the_first_was_not_sure_and_stays_when_it_was(self):
        for confidence, state in ((0.45, "expired"), (0.69, "expired"), (None, "expired"), (0.7, "open")):
            with self.subTest(confidence=confidence):
                self.setUp()
                case, plan = self.made(UNCONFIRMED, learned={"skeptic": "agree"}, confidence=confidence)
                self.assertEqual(why_not_ask(case), None if state == "open" else UNCONFIRMED)
                summary, events, _ = self.watch()
                self.assertEqual((self.store.plan_get(plan.plan_id).state, summary.held), (state, int(state == "expired")))

    def test_a_request_about_something_in_a_group_of_meternauts_own_is_left_alone_and_the_same_request_outside_it_is_taken_back(self):
        for reason in self.each():
            _, outside = self.made(reason)
            mine = unasked(reason, case_id="kmine", plan_id="pmine", resource_group=GROUP, resource_name="contoso-mine")
            self.store.case_put(mine)
            self.store.plan_put(request_for(mine, title=f"Check whether the account contoso-mine in group {GROUP} is still used", saving_usd_month=40.0, created_at="2026-11-01T09:00:00Z", expires_at=""))
            summary, events, _ = self.watch()
            self.assertEqual((self.store.plan_get("pmine").state, [e for e in events if e["type"] == "case.held" and e["caseId"] == mine.case_id]), ("open", []))
            self.assertEqual((self.store.plan_get(outside.plan_id).state, summary.held), ("expired", 1))

    def test_a_request_that_the_old_clock_closed_and_that_comes_back_is_taken_back_in_the_same_watch(self):
        for reason in self.each():
            case, _ = self.made(reason)
            self.store.plan_put(request_for(case, plan_id=f"p{reason}", state="expired", saving_usd_month=40.0, created_at="2026-10-26T12:00:00Z", expires_at="2026-10-29T12:00:00Z"))
            self.store.case_put(replace(case, status="expired"))
            summary, events, _ = self.watch()
            plan = self.store.plan_get(f"p{reason}")
            self.assertEqual(len([e for e in events if e["type"] == "plan.revived"]), 1, "it came back: nobody had answered it, and no clock closes a request")
            self.assertEqual((plan.state, plan.preconditions["takenBack"], self.store.plans_open(), summary.held), ("expired", "rules", [], 1))


if __name__ == "__main__":
    unittest.main()
