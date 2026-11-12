"""What a Watch keeps right on the findings that wait for a person (cases/upkeep.py), the fields that the records gained, and the name of a subscription in the words of a plan.

A request is given what the Watch learned since it was made (the name of the subscription, Advisor's own words, the cost), only while it is open; a read that failed never takes a figure from a
request that has one; and an old record reads as it always did. Everything is invented.
"""
import json
import unittest
from types import SimpleNamespace

from support import SUBSCRIPTION
from test_web_support import make_advice, make_advice_case, make_case, make_run

from cases import costs, upkeep
from cases.detectors import Lead
from cases.families.base import subscription_words
from cases.memory_store import MemoryStore
from cases.models import CaseRecord, RunRecord, StoreError

SUBSCRIPTION_ID = f"/subscriptions/{SUBSCRIPTION}"
PARTS = costs.parts_of({"Virtual Network": 88.1, "Microsoft Defender for Cloud": 41.25, "Azure Cognitive Search": 19.6, "Storage": 2.0})
WORDS = {"problem": "Buy a reservation", "solution": "Reserve the machines that run all month"}
ESTIMATE = {"usdMonth": 1.54, "tier": "S4", "table": "2026-11-12"}


def lead_for(**changes) -> Lead:
    base = dict(detector="advisor-cost", resource_id=SUBSCRIPTION_ID, resource_type="microsoft.subscriptions/subscriptions", name="contoso-dev", resource_group="",
                subscription_id=SUBSCRIPTION, location="", tags={}, managed_by="", facts={})
    base.update(changes)
    return Lead(**base)


def earlier_version(lead: Lead, **changes):
    """A case as an earlier version kept it for the lead: named by its id, no words of Advisor, no state of the cost and a flat zero."""
    base = dict(case_id=f"k{lead.lead_id}", resource_id=lead.resource_id, resource_name=SUBSCRIPTION, resource_type=lead.resource_type, resource_group="", subscription_id=SUBSCRIPTION,
                detector=lead.detector, status="needs_human", saving_usd_month=0.0, cost_usd_30d=0.0, plan_id="pplan01")
    base.update(changes)
    return make_advice_case(**base)


class Kept(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.lead = lead_for()

    def keep(self, case=None, plan_state="open", **plan_changes):
        case = case or earlier_version(self.lead)
        self.store.case_put(case)
        self.store.plan_put(make_advice(plan_id=case.plan_id, case_id=case.case_id, state=plan_state, **plan_changes))
        return case

    def now(self, case):
        return self.store.case_get(case.case_id)


class WhatACaseKeepsOfTheCost(unittest.TestCase):
    def test_what_the_lead_says_is_what_the_case_keeps(self):
        lead = lead_for(cost_usd_30d=12.5, cost_state="lines", cost_by_service=PARTS)
        self.assertEqual(upkeep.cost_fields(lead, None), {"cost_usd_30d": 12.5, "cost_state": "lines", "cost_by_service": PARTS, "estimate": {}})
        none = lead_for(cost_usd_30d=0.0, cost_state="none", estimate=ESTIMATE)
        self.assertEqual(upkeep.cost_fields(none, None), {"cost_usd_30d": 0.0, "cost_state": "none", "cost_by_service": {}, "estimate": ESTIMATE})

    def test_a_read_that_failed_this_time_never_takes_the_figure_from_a_case_that_has_one(self):
        failed = lead_for(cost_state="failed")
        old = make_case(cost_usd_30d=7.17, cost_state="lines")
        self.assertEqual(upkeep.cost_fields(failed, old), {"cost_usd_30d": 7.17, "cost_state": "lines", "cost_by_service": {}, "estimate": {}})

    def test_a_read_that_failed_on_a_case_that_never_had_a_figure_says_that_it_failed(self):
        failed = lead_for(cost_state="failed")
        for old in (None, make_case(cost_usd_30d=None, cost_state="")):
            with self.subTest(old=old is not None):
                self.assertEqual(upkeep.cost_fields(failed, old), {"cost_usd_30d": None, "cost_state": "failed", "cost_by_service": {}, "estimate": {}})


class WhatAnOpenRequestIsGiven(Kept):
    def test_it_gets_the_name_of_the_subscription_the_words_of_advisor_and_its_cost_and_the_flat_zero_of_an_earlier_version_is_gone(self):
        case = self.keep()
        lead = lead_for(subscription_name="contoso-dev", advice=WORDS, cost_usd_30d=151.35, cost_state="lines", cost_by_service=PARTS)
        self.assertEqual(upkeep.refresh(self.store, [lead]), 1)
        now = self.now(case)
        self.assertEqual((now.subscription_name, now.advice, now.cost_state, now.cost_usd_30d, now.cost_by_service), ("contoso-dev", WORDS, "lines", 151.35, PARTS))
        self.assertEqual(now.resource_name, SUBSCRIPTION, "nothing else of the case is touched")
        self.assertEqual(upkeep.refresh(self.store, [lead]), 0, "it holds what the lead says: nothing changes the second time")

    def test_a_request_that_is_answered_or_approved_is_not_touched_and_neither_is_one_that_no_lead_is_about(self):
        lead = lead_for(subscription_name="contoso-dev", cost_usd_30d=151.35, cost_state="lines")
        case = self.keep(plan_state="approved")
        self.assertEqual(upkeep.refresh(self.store, [lead]), 0)
        self.assertEqual(self.now(case), case, "the cost that a change is checked against is never moved once a person has approved it")
        other = self.keep(earlier_version(lead_for(resource_id=f"{SUBSCRIPTION_ID}/resourceGroups/rg-other", name="rg-other"), plan_id="pplan02"))
        self.assertEqual(upkeep.refresh(self.store, [lead]), 0)
        self.assertEqual(self.now(other), other)

    def test_a_read_that_failed_marks_a_case_that_never_had_a_figure_and_leaves_one_that_has_a_figure(self):
        failed = lead_for(cost_state="failed")
        never = self.keep(earlier_version(self.lead, cost_usd_30d=None))
        self.assertEqual(upkeep.refresh(self.store, [failed]), 1)
        self.assertEqual((self.now(never).cost_state, self.now(never).cost_usd_30d), ("failed", None))
        self.assertEqual(upkeep.refresh(self.store, [failed]), 0)
        had = self.keep(earlier_version(self.lead, cost_usd_30d=9.0, cost_state="lines"))
        self.assertEqual(upkeep.refresh(self.store, [failed]), 0)
        self.assertEqual(self.now(had), had)

    def test_no_cost_line_is_kept_as_it_is_whether_the_number_is_zero_or_none_and_its_estimate_follows_the_lead(self):
        lead = lead_for(resource_id=f"{SUBSCRIPTION_ID}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/idle", resource_type="microsoft.compute/disks", name="idle", cost_usd_30d=0.0,
                        cost_state="none", estimate=ESTIMATE)
        for number in (0.0, None):
            with self.subTest(number=number):
                case = self.keep(earlier_version(lead, resource_type="microsoft.compute/disks", cost_usd_30d=number, cost_state="none"))
                self.assertEqual(upkeep.refresh(self.store, [lead]), 1, "the estimate is new")
                self.assertEqual((self.now(case).cost_usd_30d, self.now(case).estimate), (number, ESTIMATE), "the number stays as it was: none and 0.0 say the same")
                self.assertEqual(upkeep.refresh(self.store, [lead]), 0)
        lines = lead_for(resource_id=lead.resource_id, resource_type="microsoft.compute/disks", name="idle", cost_usd_30d=3.0, cost_state="lines")
        self.assertEqual(upkeep.refresh(self.store, [lines]), 1)
        self.assertEqual((self.now(case).cost_state, self.now(case).cost_usd_30d, self.now(case).estimate), ("lines", 3.0, {}), "a disk that has a line has no estimate")

    def test_a_cost_that_is_not_in_dollars_is_kept_without_a_figure(self):
        case = self.keep(earlier_version(self.lead, cost_usd_30d=0.0))
        self.assertEqual(upkeep.refresh(self.store, [lead_for(cost_usd_30d=None, cost_state="currency")]), 1)
        self.assertEqual((self.now(case).cost_state, self.now(case).cost_usd_30d), ("currency", None))

    def test_a_store_that_fails_costs_nothing_and_says_nothing(self):
        class Broken(MemoryStore):
            def plans_open(self):
                raise StoreError("no table")

        self.assertEqual(upkeep.refresh(Broken(), [lead_for(subscription_name="contoso-dev")]), 0)

        class Stubborn(MemoryStore):
            def case_update(self, case_id, change):
                raise StoreError("a record is larger than a table property may be")

        stubborn = Stubborn()
        case = earlier_version(self.lead)
        stubborn.case_put(case)
        stubborn.plan_put(make_advice(plan_id=case.plan_id, case_id=case.case_id))
        self.assertEqual(upkeep.refresh(stubborn, [lead_for(subscription_name="contoso-dev")]), 0)


class TheRecords(unittest.TestCase):
    def test_a_case_with_the_new_fields_survives_a_round_trip_and_the_json_holds_them(self):
        case = make_case(subscription_name="contoso-dev", advice=WORDS, cost_state="lines", cost_by_service=PARTS, estimate={})
        self.assertEqual(CaseRecord.from_json(case.to_json()), case)
        data = json.loads(case.to_json())
        self.assertEqual((data["subscription_name"], data["advice"], data["cost_state"], data["cost_by_service"]), ("contoso-dev", WORDS, "lines", PARTS))
        disk = make_case(cost_usd_30d=0.0, cost_state="none", estimate=ESTIMATE)
        self.assertEqual(CaseRecord.from_json(disk.to_json()).estimate, ESTIMATE)

    def test_a_case_that_was_kept_before_the_fields_existed_reads_with_nothing_in_them(self):
        old = json.loads(make_case().to_json())
        for name in ("subscription_name", "advice", "cost_state", "cost_by_service", "estimate"):
            del old[name]
        got = CaseRecord.from_json(json.dumps(old))
        self.assertEqual((got.subscription_name, got.advice, got.cost_state, got.cost_by_service, got.estimate), ("", {}, "", {}, {}))
        self.assertEqual(got, make_case())

    def test_a_run_counts_what_it_held_back_and_an_old_run_counted_none(self):
        run = make_run(held=2)
        self.assertEqual(RunRecord.from_json(run.to_json()).held, 2)
        old = json.loads(make_run().to_json())
        del old["held"]
        self.assertEqual(RunRecord.from_json(json.dumps(old)), make_run())
        self.assertEqual(make_run().held, 0)


class TheSubscriptionInTheWordsOfAPlan(unittest.TestCase):
    def test_a_plan_names_the_subscription_by_its_display_name_and_by_the_start_of_its_id_when_that_was_not_read(self):
        named = SimpleNamespace(subscription_name="contoso-dev", subscription_id=SUBSCRIPTION)
        unnamed = SimpleNamespace(subscription_name="", subscription_id=SUBSCRIPTION)
        self.assertEqual((subscription_words(named), subscription_words(unnamed)), ("contoso-dev", "11111111"))
        self.assertEqual(subscription_words(SimpleNamespace(subscription_id=SUBSCRIPTION)), "11111111", "a lead of an earlier kind has no name at all")

    def test_a_name_is_one_clean_line_of_at_most_eighty_characters(self):
        hostile = SimpleNamespace(subscription_name="line one\nline two\x1b[31m" + "x" * 200, subscription_id=SUBSCRIPTION)
        said = subscription_words(hostile)
        self.assertLessEqual(len(said), 80)
        self.assertNotRegex(said, r"[\x00-\x1f]")


if __name__ == "__main__":
    unittest.main()
