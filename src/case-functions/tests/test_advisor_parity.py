"""Every cost recommendation of Azure Advisor is a finding of Meternaut with Advisor's own figure (cases/advisor.py, docs/proposals/22-advisor-first-class.md).

No test calls Azure. The recommendations are invented, in the shapes that Advisor gave for a real estate when they were read (keys and counts only): 18 virtual machine
reservations, 4 savings plans, 6 Cosmos DB reservations and 3 disks, in two subscriptions. The fakes are those of the other tests of the Watch.
"""
import datetime as dt
import hashlib
import json
import unittest
from dataclasses import replace
from unittest import mock

from support import NOW, SUBSCRIPTION, disk_row
from test_estate_watch import Tenant, of_type, sub_id, watch
from test_run_loop import GROUP, PLANTED, Moving, loop_for
from test_web_support import MAYA, TINO, Console, make_case, make_decision, make_plan

from cases import advisor, brief as brief_mod, cards, detectors, investigate, letters
from cases.detectors import ADVISOR
from cases.models import ADVISE
from cases.people import Person

SUB_B = sub_id(5)
VM, SAVINGS_PLAN, COSMOS, DISKS = "84b1a508-0000-4000-8000-000000000001", "89515250-0000-4000-8000-000000000002", "a205074f-0000-4000-8000-000000000003", "48eda464-0000-4000-8000-000000000004"
SOLUTION = {VM: "Buy virtual machine reserved instances to save money over pay-as-you-go costs", SAVINGS_PLAN: "Consider a Compute Savings Plan to save money over pay-as-you-go costs",
            COSMOS: "Buy Azure Cosmos DB reserved capacity to save money", DISKS: "Delete unattached managed disks to reduce costs"}
CATEGORY = {VM: "Reservations", SAVINGS_PLAN: "SavingsPlan", COSMOS: "Reservations", DISKS: "IdleResources"}


def rec(type_id: str, sub: str, n: int, annual: float | None = None, resource: str | None = None, **extended) -> dict:
    """One invented recommendation in the shape of the real ones: its name is a hash, a reservation is about the subscription, a disk about the disk (and names no currency)."""
    annual = 300.0 + 25 * n if annual is None else annual
    props = {"recommendationSubCategory": CATEGORY[type_id], "annualSavingsAmount": str(annual), "savingsAmount": str(round(annual / 12)), "recommendationOfferingId": f"offer-{n}"}
    if type_id == DISKS:
        props.update({"armRegionName": "swedencentral", "productName": "Standard HDD Managed Disks"})
    else:
        props.update({"savingsCurrency": "USD", "scope": "Single", "subId": sub, "term": "P1Y" if n % 2 else "P3Y", "lookbackPeriod": ("7", "30", "60")[n // 2 % 3]})
        if type_id == SAVINGS_PLAN:
            props.update({"sku": "Compute_Savings_Plan", "commitment": "0.098", "lookbackPeriod": "30"})
        elif type_id == COSMOS:
            props.update({"sku": "Cosmos_DB_100_RUs", "displaySKU": "100 RU/s", "qty": "6", "displayQty": "6", "region": "All", "displayRegion": "All", "reservedResourceType": "cosmosdb"})
        else:
            big = n % 3 == 0
            props.update({"sku": "Standard_D2als_v6" if big else "Standard_D2s_v6", "displaySKU": "x", "qty": "2" if big else "1", "displayQty": "x", "region": "swedencentral",
                          "location": "swedencentral", "reservedResourceType": "virtualmachines", "targetResourceCount": "1", "vmSize": "x"})
    props.update(extended)
    about = resource or f"/subscriptions/{sub}"
    return {"id": f"{about}/providers/Microsoft.Advisor/recommendations/{n}", "name": hashlib.sha256(f"{type_id}{sub}{n}".encode()).hexdigest(), "type": "Microsoft.Advisor/recommendations",
            "properties": {"category": "Cost", "impact": "Medium" if type_id == DISKS else "High", "impactedField": "microsoft.compute/disks" if type_id == DISKS else "microsoft.subscriptions/subscriptions",
                           "impactedValue": "disk-one" if type_id == DISKS else "whatever the subscription is called", "lastUpdated": "2026-11-16T08:00:00Z", "recommendationTypeId": type_id,
                           "resourceMetadata": {"resourceId": about}, "shortDescription": {"problem": f"Problem sentence of {CATEGORY[type_id]} that Advisor wrote", "solution": SOLUTION[type_id]},
                           "extendedProperties": props}}


def disk_id(name: str, sub: str = SUBSCRIPTION) -> str:
    return f"/subscriptions/{sub}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/{name}"


def the_list() -> tuple[dict, float]:
    """The invented list, by subscription, and what Advisor's figures add up to a year: 14 + 4 virtual machine reservations, 2 + 2 savings plans, 6 for Cosmos DB, 3 disks."""
    mine = [rec(VM, SUBSCRIPTION, n) for n in range(14)] + [rec(SAVINGS_PLAN, SUBSCRIPTION, n) for n in range(2)] + [rec(COSMOS, SUBSCRIPTION, n) for n in range(6)]
    mine += [rec(DISKS, SUBSCRIPTION, n, annual=18.42, resource=disk_id(f"disk-{n}")) for n in range(3)]
    theirs = [rec(VM, SUB_B, n) for n in range(4)] + [rec(SAVINGS_PLAN, SUB_B, n) for n in range(2)]
    every = mine + theirs
    return {SUBSCRIPTION: mine, SUB_B: theirs}, sum(float(r["properties"]["extendedProperties"]["annualSavingsAmount"]) for r in every)


def estate(advisor_of=None) -> Tenant:
    tenant = Tenant([SUBSCRIPTION, SUB_B])
    tenant.advisor_of, _ = (advisor_of, 0) if advisor_of is not None else the_list()
    tenant.costs_of[SUBSCRIPTION], tenant.costs_of[SUB_B] = [(12.0, disk_id("x"))], [(12.0, disk_id("x", SUB_B))]  # a cost line gives the currency of the subscription: dollars
    return tenant


class Watched:
    """A Watch of the estate with the loop (the store, the people, the approvals), as the daily timer runs it."""

    def __init__(self, tenant: Tenant | None = None) -> None:
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store
        self.tenant = tenant or estate()

    def run(self, **options):
        self.summary, self.events, self.messages = watch(self.tenant, clock=self.clock, extras=self.extras, **options)
        return self

    def cases(self, detector: str = ADVISOR):
        return [case for case in self.store.cases_recent() if case.detector == detector]

    def case(self, kind: str, sub: str = SUBSCRIPTION):
        (found,) = [case for case in self.cases() if case.subscription_id == sub and case.facts["advisor"]["type"] == kind]
        return found


def month(case) -> float:
    return brief_mod.scenario_saving(case) or 0.0


class TheLeads(unittest.TestCase):
    def test_every_recommendation_has_a_lead_of_its_own_that_the_recommendation_itself_names(self):
        lists, _ = the_list()
        leads = [detectors.advisor_lead(r, SUBSCRIPTION) for r in lists[SUBSCRIPTION]]
        self.assertEqual(len({lead.lead_id for lead in leads}), len(leads), "two recommendations about one subscription are two leads")
        again = [detectors.advisor_lead(r, SUBSCRIPTION) for r in lists[SUBSCRIPTION]]
        self.assertEqual([lead.lead_id for lead in again], [lead.lead_id for lead in leads], "and the same recommendation is the same lead at every Watch")

    def test_a_lead_keeps_every_number_and_word_of_the_recommendation_as_typed_values_and_advisors_sentences_in_none_of_them(self):
        lead = detectors.advisor_lead(rec(VM, SUBSCRIPTION, 3, annual=1200.0), SUBSCRIPTION)
        self.assertEqual(lead.advisor, {"type": VM, "sub": "Reservations", "sku": "Standard_D2als_v6", "qty": 2, "region": "swedencentral", "term": "P1Y", "annual": 1200.0,
                                        "currency": "USD", "lookback": 30, "scope": "Single"})
        self.assertEqual((lead.advisor_saving_usd, lead.facts["impact"], lead.facts["recommendationType"]), (100.0, "high", VM))
        self.assertNotIn("Advisor wrote", json.dumps([lead.facts, lead.advisor]))
        self.assertIn("Advisor wrote", lead.advice["problem"])

    def test_no_currency_and_not_dollars_give_the_lead_no_figure_in_dollars(self):
        eur = detectors.advisor_lead(rec(VM, SUBSCRIPTION, 1, savingsCurrency="EUR"), SUBSCRIPTION)
        disk = detectors.advisor_lead(rec(DISKS, SUBSCRIPTION, 1, annual=18.42, resource=disk_id("d")), SUBSCRIPTION)
        self.assertEqual((eur.advisor_saving_usd, eur.advisor["currency"], disk.advisor_saving_usd, disk.advisor["currency"]), (None, "EUR", None, ""))

    def test_the_leads_of_one_subscription_are_not_folded_by_the_ranking(self):
        lists, _ = the_list()
        leads = [detectors.advisor_lead(r, SUBSCRIPTION) for r in lists[SUBSCRIPTION]]
        ranked = detectors.rank(leads, {SUBSCRIPTION: detectors.Context(currency="USD", costs={})})
        self.assertEqual(len(ranked), len(leads))


class TheCasesOfTheWatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.watched = Watched().run()
        cls.lists, cls.annual = the_list()

    def test_the_thirty_one_recommendations_are_eight_cases_one_for_each_subscription_type_and_sub_category_and_one_for_each_disk(self):
        cases = self.watched.cases()
        self.assertEqual(len(cases), 8)
        self.assertEqual(sorted((c.subscription_id == SUBSCRIPTION, c.facts["advisor"]["type"], c.facts["advisor"]["n"]) for c in cases),
                         sorted([(True, VM, 14), (True, SAVINGS_PLAN, 2), (True, COSMOS, 6), (False, VM, 4), (False, SAVINGS_PLAN, 2)] + [(True, DISKS, 1)] * 3))
        self.assertEqual({c.status for c in cases}, {"needs_human"})
        self.assertEqual(sum(c.facts["advisor"]["n"] for c in cases), 31, "none lost and none counted twice")

    def test_the_figures_add_up_to_what_advisor_says_a_year_divided_by_twelve_for_each_recommendation(self):
        stated = sum(month(case) for case in self.watched.cases())
        self.assertAlmostEqual(stated, self.annual / 12, delta=0.01 * 8)
        plans = [plan for plan in self.store_plans() if plan.family == ADVISE]
        self.assertAlmostEqual(sum(plan.saving_usd_month for plan in plans), self.annual / 12, delta=0.01 * 8)

    def store_plans(self):
        return self.watched.store.plans_open()

    def test_each_case_has_one_request_and_the_requests_of_one_subscription_do_not_hold_each_other_back(self):
        plans = self.store_plans()
        self.assertEqual(len(plans), 8)
        self.assertEqual({plan.case_id for plan in plans}, {case.case_id for case in self.watched.cases()})
        self.assertEqual(len(of_type(self.watched.events, "plan.created")), 8)

    def test_a_group_keeps_at_most_twelve_rows_and_says_how_many_more_and_what_they_add_up_to(self):
        digest = self.watched.case(VM).facts["advisor"]
        every = sorted((float(r["properties"]["extendedProperties"]["annualSavingsAmount"]) for r in self.lists[SUBSCRIPTION] if r["properties"]["recommendationTypeId"] == VM), reverse=True)
        self.assertEqual((len(digest["rows"]), digest["more"]), (12, 2))
        self.assertEqual([row[4] for row in digest["rows"]], every[:12], "the largest first")
        self.assertAlmostEqual(digest["moreUsd"], sum(every[12:]))
        self.assertAlmostEqual(digest["usd"], sum(every))
        self.assertEqual({row[5] for row in digest["rows"]}, {"USD"})

    def test_a_row_says_the_sku_the_quantity_the_region_the_term_the_saving_a_year_the_look_back_and_the_scope(self):
        (row,) = [r for r in self.watched.case(SAVINGS_PLAN, SUB_B).facts["advisor"]["rows"] if r[3] == "P3Y"]
        self.assertEqual([row[0], row[3], row[5], row[6], row[7]], ["Compute_Savings_Plan", "P3Y", "USD", 30, "Single"])

    def test_the_impact_that_advisor_gives_is_kept_as_a_typed_fact(self):
        self.assertEqual(self.watched.case(VM).facts["impact"], "high")
        self.assertEqual({c.facts["impact"] for c in self.watched.cases() if c.facts["advisor"]["type"] == DISKS}, {"medium"})

    def test_the_figure_is_a_scenario_that_says_it_is_advisors_own_and_that_the_rows_can_be_alternatives(self):
        case = self.watched.case(VM)
        plan = next(p for p in self.store_plans() if p.case_id == case.case_id)
        said = brief_mod.build_brief(case, plan, now=NOW)
        self.assertEqual((said.saving.level, round(said.saving.monthly, 2)), ("Scenario", month(case)))
        self.assertIn("Azure Advisor", said.saving.basis)
        self.assertIn("alternatives", said.saving.basis)

    def test_the_history_says_each_case_with_its_figure_and_that_nothing_was_judged_by_a_model(self):
        results = [e for e in of_type(self.watched.events, "case.result") if e["detector"] == ADVISOR]
        self.assertEqual(len(results), 8)
        self.assertAlmostEqual(sum(e["monthlySavingUsd"] for e in results), self.annual / 12, delta=0.01 * 8)
        self.assertEqual(self.watched.tenant.chat_calls(), [], "Advisor's own claims are not judged by the models")
        self.assertEqual(len(of_type(self.watched.events, "lead.found")), 31)
        self.assertEqual((self.watched.summary.leads, self.watched.summary.cases, self.watched.summary.needs_human), (31, 8, 8))


class OnePerRecommendationAndNoneDroppedSilently(unittest.TestCase):
    def test_a_recommendation_in_another_currency_is_counted_and_not_added_and_the_history_says_so(self):
        lists, annual = the_list()
        lists[SUB_B][0] = rec(VM, SUB_B, 0, annual=999.0, savingsCurrency="EUR")
        watched = Watched(estate(lists)).run()
        case = watched.case(VM, SUB_B)
        digest = case.facts["advisor"]
        self.assertEqual((digest["n"], digest["added"], digest["skipped"], digest["currencies"]), (4, 3, 1, ["EUR"]))
        self.assertAlmostEqual(digest["usd"], sum(float(r["properties"]["extendedProperties"]["annualSavingsAmount"]) for r in lists[SUB_B][1:4]))
        self.assertTrue(any(r[5] == "EUR" and r[4] == 999.0 for r in digest["rows"]), "its row is there, with its own figure and currency")
        self.assertTrue(any("not added" in e["note"] and "EUR" in e["note"] for e in of_type(watched.events, "run.note")))
        self.assertAlmostEqual(sum(month(c) for c in watched.cases()), (annual - 300.0) / 12, delta=0.1)

    def test_a_disk_that_names_no_currency_is_read_in_dollars_only_when_the_cost_lines_of_the_subscription_are(self):
        dollars = Watched().run()
        self.assertEqual([c.facts["advisor"]["skipped"] for c in dollars.cases() if c.facts["advisor"]["type"] == DISKS], [0, 0, 0])
        euros = estate()
        euros.currency = "EUR"
        other = Watched(euros).run()
        disks = [c for c in other.cases() if c.facts["advisor"]["type"] == DISKS]
        self.assertEqual(([c.facts["advisor"]["skipped"] for c in disks], [month(c) for c in disks]), ([1, 1, 1], [0.0, 0.0, 0.0]))
        self.assertEqual(len(other.store.plans_open()), 8, "a recommendation without a figure in dollars is still a request")

    def test_a_recommendation_that_says_neither_a_problem_nor_a_solution_still_makes_a_request_with_words_of_code(self):
        lists, _ = the_list()
        bare = rec(VM, SUB_B, 9)
        bare["properties"]["shortDescription"] = {}
        watched = Watched(estate({SUBSCRIPTION: [], SUB_B: [bare]})).run()
        (case,) = watched.cases()
        self.assertTrue(brief_mod.advice_of(case), "it has words")
        self.assertEqual(len(watched.store.plans_open()), 1)

    def test_no_guard_of_the_ai_cases_holds_an_advisor_case_back_a_small_figure_ten_open_questions_or_the_investigation(self):
        watched = Watched()
        for n in range(10):  # the ten open requests that the AIs did not settle are the whole of ADVICE_OPEN_MAX
            watched.store.plan_put(make_plan(plan_id=f"open{n}", case_id=f"kopen{n}", family=ADVISE, resource_id=disk_id(f"other-{n}"), state="open", approvers=(TINO,),
                                             preconditions={"family": ADVISE, "caseStatus": "needs_human"}, expires_at="2026-11-30T00:00:00Z"))
        ran = investigate.Investigation(ran=True)
        with mock.patch.object(investigate, "investigate", return_value=ran):
            watched.run()
        self.assertEqual(len([p for p in watched.store.plans_open() if p.case_id.startswith("k") and not p.case_id.startswith("kopen")]), 8)
        self.assertFalse([e for e in of_type(watched.events, "case.held")])

    def test_the_next_watch_makes_no_second_request_for_a_request_that_is_open_and_keeps_the_cases_up_to_date(self):
        watched = Watched().run()
        first = {plan.plan_id for plan in watched.store.plans_open()}
        lists, _ = the_list()
        lists[SUBSCRIPTION].append(rec(VM, SUBSCRIPTION, 40, annual=5000.0))
        watched.tenant.advisor_of = lists
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual({plan.plan_id for plan in watched.store.plans_open()}, first)
        self.assertEqual(len(watched.cases()), 8)
        self.assertEqual(watched.case(VM).facts["advisor"]["n"], 15)
        self.assertEqual(watched.case(VM).runs_seen, 2)
        self.assertEqual((watched.summary.cases, of_type(watched.events, "case.result")), (0, []), "a request that waits is not announced again, and the Watch does not count it as made")

    def test_what_a_person_declined_is_not_asked_again_for_a_month_and_the_other_requests_of_the_subscription_stay(self):
        watched = Watched().run()
        case = watched.case(COSMOS)
        plan = next(p for p in watched.store.plans_open() if p.case_id == case.case_id)
        watched.store.plan_put(replace(plan, state="declined"))
        watched.store.case_put(replace(case, status="declined", updated_at="2026-11-04T12:00:00Z"))
        watched.clock.advance(days=3)
        watched.run()
        self.assertEqual(watched.case(COSMOS).status, "declined", "a person's answer is not undone by a Watch")
        self.assertEqual(len(watched.store.plans_open()), 7)
        watched.clock.advance(days=31)
        watched.run()
        self.assertEqual((watched.case(COSMOS).status, len([p for p in watched.store.plans_open() if p.case_id == case.case_id])), ("needs_human", 1))


class TheDiskAndTheDetectorThatFoundItAreOneCase(unittest.TestCase):
    def estate(self, planted: bool):
        lists, _ = the_list()
        tenant = estate(lists)
        row = (disk_row("planted-disk-1", GROUP, tags=PLANTED, timeCreated="2026-01-02T10:00:00+00:00") if planted else
               disk_row("disk-0", "rg-app", tags={"owner": "someone"}, timeCreated="2026-01-02T10:00:00+00:00"))
        lists[SUBSCRIPTION][-3] = rec(DISKS, SUBSCRIPTION, 0, annual=18.42, resource=row["id"])  # the first of the three disks is the one that the older check found too
        tenant.graph["orphan-managed-disk"] = [row]
        return tenant

    def test_a_disk_that_the_older_check_found_too_is_one_case_with_both_sources_and_one_request(self):
        watched = Watched(self.estate(planted=False)).run()
        disks = [c for c in watched.store.cases_recent() if c.resource_id.lower().endswith("/disks/disk-0")]
        self.assertEqual(len(disks), 1, "never two cases for one disk")
        self.assertEqual(disks[0].facts["advisor"]["also"], ["orphan-managed-disk"])
        self.assertEqual(len([p for p in watched.store.plans_open() if p.resource_id.lower().endswith("/disks/disk-0")]), 1)
        self.assertEqual([c for c in watched.store.cases_recent() if c.detector == "orphan-managed-disk"], [])

    def test_waste_that_meternaut_planted_keeps_its_own_case_and_its_own_plan_and_carries_what_advisor_says(self):
        tenant = self.estate(planted=True)
        watched = Watched(tenant).run()
        (case,) = [c for c in watched.store.cases_recent() if c.detector == "orphan-managed-disk"]
        self.assertEqual((case.facts["advisor"]["n"], case.models != {}), (1, True))
        self.assertEqual(len([c for c in watched.store.cases_recent() if c.resource_id.lower() == case.resource_id.lower()]), 1)
        self.assertEqual([p.family for p in watched.store.plans_open() if p.resource_id.lower() == case.resource_id.lower()], ["delete-disk"])
        for prompt in tenant.prompts():
            self.assertNotIn("Advisor", prompt)
            self.assertNotIn("Standard HDD", prompt)

    def test_the_page_names_both_sources_of_the_one_case(self):
        watched = Watched(self.estate(planted=False)).run()
        (case,) = [c for c in watched.store.cases_recent() if c.resource_id.lower().endswith("/disks/disk-0")]
        plan = next(p for p in watched.store.plans_open() if p.case_id == case.case_id)
        reply = Console(store=watched.store).get(f"/ok/{plan.plan_id}")
        content = reply.content
        self.assertEqual(reply.table("advisor").headers, ["What", "Where", "Saves a year"], "a disk has no term, look-back or scope: those columns are left out")
        self.assertIn("Advisor's list", content)
        self.assertIn("Also found by Meternaut", content)
        self.assertIn("Not attached to any virtual machine", content)

    def test_an_older_case_that_asks_to_delete_keeps_its_own_guards_and_gets_no_words_of_advisor_and_the_history_says_what_was_held(self):
        disk = disk_id("disk-0")
        lists = {SUBSCRIPTION: [rec(DISKS, SUBSCRIPTION, 0, annual=18.42, resource=disk)], SUB_B: []}
        watched = Watched(estate(lists))
        mate = make_case(case_id=f"k{detectors.ident('orphan-managed-disk', disk)}", detector="orphan-managed-disk", status="needs_human", recommendation="delete", resource_id=disk,
                         resource_type="microsoft.compute/disks", resource_name="disk-0", resource_group="rg-app", subscription_id=SUBSCRIPTION, facts={"diskState": "unattached"}, advice={})
        watched.store.case_put(mate)
        watched.run()
        found = watched.store.case_get(mate.case_id)
        self.assertEqual((found.advice, found.detector, found.facts["advisor"]["n"]), ({}, "orphan-managed-disk", 1), "Advisor's figure is on its case, and its words are not")
        self.assertEqual([p for p in watched.store.plans_open() if p.resource_id.lower() == disk.lower()], [], "nobody looked up who changed the disk: a deletion is not asked on that")
        (held,) = [e for e in of_type(watched.events, "case.held") if e["caseId"] == mate.case_id]
        self.assertEqual(held["reason"], "held back: not checked who changed it")
        self.assertEqual(watched.summary.held, 1)


class AnEarlierVersionsRequestForAWholeSubscriptionIsClosed(unittest.TestCase):
    """The first version asked once for a whole subscription, with one figure for all of its recommendations. The requests for each kind replace it, unless a person has answered it."""

    def old(self, watched):
        about = f"/subscriptions/{SUBSCRIPTION}"
        watched.store.case_put(make_case(case_id="kold", detector="advisor-cost", status="needs_human", resource_id=about, resource_type="microsoft.subscriptions/subscriptions",
                                         resource_name="", resource_group="", subscription_id=SUBSCRIPTION, plan_id="pold", facts={"category": "cost", "impact": "high"},
                                         advice={"problem": "Buy reservations", "solution": "Buy reservations"}))
        watched.store.plan_put(make_plan(plan_id="pold", case_id="kold", family=ADVISE, resource_id=about, state="open", approvers=(TINO,),
                                         preconditions={"family": ADVISE, "caseStatus": "needs_human"}, expires_at="2026-11-30T00:00:00Z"))

    def test_the_request_that_nobody_answered_is_closed_with_its_reason_and_its_case_ends_and_the_new_requests_stay(self):
        watched = Watched()
        self.old(watched)
        watched.run()
        closed, ended = watched.store.plan_get("pold"), watched.store.case_get("kold")
        self.assertEqual((closed.state, closed.preconditions["takenBack"], ended.status), ("expired", "advisor", "expired"))
        self.assertEqual(len(watched.store.plans_open()), 8)
        self.assertIn(brief_mod.TAKEN_BACK["advisor"], brief_mod.build_brief(ended, closed, now=NOW).outcome.lines)
        self.assertTrue(any("earlier request" in e["note"] and "closed" in e["note"] for e in of_type(watched.events, "run.note")))

    def test_a_request_that_a_person_put_off_stays_open_and_theirs(self):
        watched = Watched()
        self.old(watched)
        watched.store.decision_put(make_decision(plan_id="pold", approver_oid=TINO, decision="later"))
        watched.run()
        self.assertEqual((watched.store.plan_get("pold").state, watched.store.case_get("kold").status), ("open", "needs_human"))

    def test_nothing_is_closed_when_advisor_has_no_recommendation_now_to_replace_it(self):
        watched = Watched(estate({SUBSCRIPTION: [], SUB_B: [rec(VM, SUB_B, 0)]}))
        self.old(watched)
        watched.run()
        self.assertEqual((watched.store.plan_get("pold").state, watched.store.case_get("kold").status), ("open", "needs_human"))


class WhatThePageTheLetterAndTheCardSay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.watched = Watched().run()
        cls.case = cls.watched.case(VM)
        cls.plan = next(plan for plan in cls.watched.store.plans_open() if plan.case_id == cls.case.case_id)
        cls.year = brief_mod.usd_text(cls.case.facts["advisor"]["usd"])
        cls.page = Console(store=cls.watched.store).get(f"/ok/{cls.plan.plan_id}")

    def test_the_page_shows_the_sum_twelve_rows_and_the_rest_with_their_sum_at_the_level_scenario(self):
        reply = self.page
        self.assertEqual((reply.status, reply.problems), (200, []))
        table = reply.table("advisor")
        self.assertEqual((table.headers, len(table.rows)), (brief_mod.ADVISOR_COLUMNS, 12))
        first = table.rows[0]
        self.assertEqual((first["What"], first["Where"], first["For how long"], first["Applies to"]), ("Standard_D2s_v6 × 1", "swedencentral", "1 year", "one subscription"))
        self.assertRegex(first["Saves a year"], r"^\$[0-9,]+\.00$")
        self.assertRegex(first["Looked back"], r"^[0-9]+ days$")
        self.assertIn(f"Its figures add up to {self.year} a year", reply.content)
        self.assertIn(f"and 2 more, {brief_mod.usd_text(self.case.facts['advisor']['moreUsd'])} a year", reply.content)
        self.assertIn("Saves, Scenario", reply.content)
        self.assertIn("the rows can be alternatives or overlap, so buying saves less than the sum", reply.content)

    def test_the_page_says_the_order_of_work_that_nothing_was_checked_and_that_meternaut_does_not_buy(self):
        content = self.page.content
        for words in (brief_mod.ADVISOR_FIRST, brief_mod.ADVISOR_FIRST_RISK, "Meternaut does not buy it", brief_mod.ADVISOR_RISK):
            self.assertIn(words, content)
        self.assertNotIn("Why the AIs think so", content)
        self.assertIn("How sure Meternaut is", content)

    def test_the_details_say_that_no_ai_looked_at_it_and_claim_no_text_or_fact_of_an_ai(self):
        content = self.page.content
        self.assertIn("No AI looked at this finding", content)
        self.assertIn("The typed facts that Meternaut recorded", content)
        for text in ("What the AIs wrote, in full", "The typed facts that the AIs saw", "The second AI was not asked"):
            self.assertNotIn(text, content)

    def test_the_page_names_nothing_of_the_estate_that_other_requests_do_not_name(self):
        content = self.page.content
        self.assertIn("Problem sentence of Reservations that Advisor wrote", content, "Advisor's own words, escaped, for a person")
        for text in (SUB_B, "offer-", "whatever the subscription is called"):
            self.assertNotIn(text, content)

    def test_the_decisions_page_has_a_row_for_each_subscription_and_type_and_one_row_for_the_three_disks(self):
        content = Console(store=self.watched.store).get("/").content
        self.assertGreaterEqual(content.count("Problem sentence of Reservations"), 5, "the two virtual machine groups, Cosmos DB, and the two savings plans: a row each")
        self.assertIn("Show 3", content, "the three disks are one row that opens")

    def test_the_letter_and_the_card_carry_the_sum_and_the_order_of_work_in_a_line(self):
        person = Person(TINO, "Tino", ("owner", "approver"), "tino@example.com")
        letter = letters.approval_letter(self.plan, self.case, person, "https://meternaut.example", NOW)
        self.assertIn(brief_mod.ADVISOR_SHORT, letter.text)
        self.assertIn("Advisor's list", letter.text)
        self.assertIn(f"${round(self.case.facts['advisor']['usd']):,}", letter.text)
        built = brief_mod.build_brief(self.case, self.plan, now=NOW, may_answer=True)
        card = json.dumps(cards.decision_card(built, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", contacts=())))
        self.assertIn("Order of work", card)
        self.assertIn("Advisor's list", card)
