"""Every cost recommendation of Azure Advisor is a finding of Meternaut with Advisor's own figure (cases/advisor.py, docs/proposals/22-advisor-first-class.md).

No test calls Azure. The recommendations are invented, in the shapes that Advisor gave for a real estate when they were read (keys and counts only): 18 virtual machine
reservations, 4 savings plans, 6 Cosmos DB reservations and 3 disks, in two subscriptions. Advisor lists the same purchase for each term and each look-back, so the 31 are
9 decisions, and the figures here are invented to tell the variants of one decision, the decisions and the alternatives apart. The fakes are those of the other tests of the Watch.
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
from test_web_savings import rows_of
from test_web_support import MAYA, TINO, Console, make_case, make_decision, make_plan

from cases import advisor, brief as brief_mod, cards, detectors, investigate, letters
from cases.detectors import ADVISOR
from cases.models import ADVICE_OPEN_MAX, ADVISE
from cases.people import Person

SUB_B = sub_id(5)
VM, SAVINGS_PLAN, COSMOS, DISKS = "84b1a508-0000-4000-8000-000000000001", "89515250-0000-4000-8000-000000000002", "a205074f-0000-4000-8000-000000000003", "48eda464-0000-4000-8000-000000000004"
SOLUTION = {VM: "Buy virtual machine reserved instances to save money over pay-as-you-go costs", SAVINGS_PLAN: "Consider a Compute Savings Plan to save money over pay-as-you-go costs",
            COSMOS: "Buy Azure Cosmos DB reserved capacity to save money", DISKS: "Delete unattached managed disks to reduce costs"}
CATEGORY = {VM: "Reservations", SAVINGS_PLAN: "SavingsPlan", COSMOS: "Reservations", DISKS: "IdleResources"}
D2S, D2ALS = "Standard_D2s_v6", "Standard_D2als_v6"
TERMS, LOOKBACKS = ("P1Y", "P3Y"), (7, 30, 60)


def rec(type_id: str, sub: str, n: int, annual: float | None = None, resource: str | None = None, **extended) -> dict:
    """One invented recommendation in the shape of the real ones: its name is a hash, a reservation is about the subscription, a disk about the disk (and names no currency)."""
    annual = 300.0 + 25 * n if annual is None else annual
    props = {"recommendationSubCategory": CATEGORY[type_id], "annualSavingsAmount": str(annual), "savingsAmount": str(round(annual / 12)), "recommendationOfferingId": f"offer-{n}"}
    if type_id == DISKS:
        props.update({"armRegionName": "swedencentral", "productName": "Standard HDD Managed Disks"})
    else:
        props.update({"savingsCurrency": "USD", "scope": "Single", "subId": sub, "term": "P1Y", "lookbackPeriod": "30"})
        if type_id == SAVINGS_PLAN:
            props.update({"sku": "Compute_Savings_Plan", "commitment": "0.098"})
        elif type_id == COSMOS:
            props.update({"sku": "Cosmos_DB_100_RUs", "displaySKU": "100 RU/s", "qty": "6", "displayQty": "6", "region": "All", "displayRegion": "All", "reservedResourceType": "cosmosdb"})
        else:
            props.update({"sku": D2S, "displaySKU": "x", "qty": "1", "displayQty": "x", "region": "swedencentral", "location": "swedencentral", "reservedResourceType": "virtualmachines",
                          "targetResourceCount": "1", "vmSize": "x"})
    props.update(extended)
    about = resource or f"/subscriptions/{sub}"
    return {"id": f"{about}/providers/Microsoft.Advisor/recommendations/{n}", "name": hashlib.sha256(f"{type_id}{sub}{n}".encode()).hexdigest(), "type": "Microsoft.Advisor/recommendations",
            "properties": {"category": "Cost", "impact": "Medium" if type_id == DISKS else "High", "impactedField": "microsoft.compute/disks" if type_id == DISKS else "microsoft.subscriptions/subscriptions",
                           "impactedValue": "disk-one" if type_id == DISKS else "whatever the subscription is called", "lastUpdated": "2026-11-16T08:00:00Z", "recommendationTypeId": type_id,
                           "resourceMetadata": {"resourceId": about}, "shortDescription": {"problem": f"Problem sentence of {CATEGORY[type_id]} that Advisor wrote", "solution": SOLUTION[type_id]},
                           "extendedProperties": props}}


def variants(type_id: str, sub: str, base: float, first: int, lookbacks: tuple = LOOKBACKS, **extended) -> list[dict]:
    """One purchase as Advisor lists it: once for each term and each look-back, the figure growing with both. The smallest is the base times 1.07, the largest the base times 3.2 (three years, 60 days)."""
    return [rec(type_id, sub, first + i, annual=round(base * (2 if term == "P3Y" else 1) * (1 + lookback / 100), 2), term=term, lookbackPeriod=str(lookback), **extended)
            for i, (term, lookback) in enumerate((t, b) for t in TERMS for b in lookbacks)]


def disk_id(name: str, sub: str = SUBSCRIPTION) -> str:
    return f"/subscriptions/{sub}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/{name}"


def the_list() -> tuple[dict, float]:
    """The invented list, by subscription, and what all its figures add up to a year if every variant were counted (it is what the first version stated): in the first subscription two virtual
    machine decisions (two sizes) and one for Cosmos DB, 6 variants each, a savings plan of 2 and 3 disks; in the second one virtual machine decision and a savings plan. 31 recommendations, 9 decisions."""
    mine = (variants(VM, SUBSCRIPTION, 300.0, 0, sku=D2S, qty="2") + variants(VM, SUBSCRIPTION, 200.0, 10, sku=D2ALS) + variants(COSMOS, SUBSCRIPTION, 50.0, 20)
            + variants(SAVINGS_PLAN, SUBSCRIPTION, 400.0, 30, lookbacks=(30,)))
    mine += [rec(DISKS, SUBSCRIPTION, n, annual=18.42, resource=disk_id(f"disk-{n}")) for n in range(3)]
    theirs = variants(VM, SUB_B, 250.0, 0, sku=D2S) + variants(SAVINGS_PLAN, SUB_B, 450.0, 30, lookbacks=(30,))
    return {SUBSCRIPTION: mine, SUB_B: theirs}, sum(float(r["properties"]["extendedProperties"]["annualSavingsAmount"]) for r in mine + theirs)


# What an honest reading of that list counts a year: in the first subscription the reservations (321.0 + 214.0 + 53.5) beat the savings plan (520.0), which is an alternative; in the second
# the savings plan (585.0) beats the reservation (267.5); and the 3 disks (18.42 each).
COUNTED = 321.0 + 214.0 + 53.5 + 585.0 + 3 * 18.42


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

    def case(self, kind: str, sub: str = SUBSCRIPTION, sku: str | None = None):
        (found,) = [case for case in self.cases() if case.subscription_id == sub and case.facts["advisor"]["type"] == kind and (sku is None or case.facts["advisor"]["rows"][0][0] == sku)]
        return found


def month(case) -> float:
    return brief_mod.advisor_saving(case) or 0.0


class TheLeads(unittest.TestCase):
    def test_every_recommendation_has_a_lead_of_its_own_that_the_recommendation_itself_names(self):
        lists, _ = the_list()
        leads = [detectors.advisor_lead(r, SUBSCRIPTION) for r in lists[SUBSCRIPTION]]
        self.assertEqual(len({lead.lead_id for lead in leads}), len(leads), "two recommendations about one subscription are two leads")
        again = [detectors.advisor_lead(r, SUBSCRIPTION) for r in lists[SUBSCRIPTION]]
        self.assertEqual([lead.lead_id for lead in again], [lead.lead_id for lead in leads], "and the same recommendation is the same lead at every Watch")

    def test_a_lead_keeps_every_number_and_word_of_the_recommendation_as_typed_values_and_advisors_sentences_in_none_of_them(self):
        lead = detectors.advisor_lead(rec(VM, SUBSCRIPTION, 3, annual=1200.0, sku=D2ALS, qty="2"), SUBSCRIPTION)
        self.assertEqual(lead.advisor, {"type": VM, "sub": "Reservations", "sku": D2ALS, "qty": 2, "region": "swedencentral", "term": "P1Y", "annual": 1200.0,
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
        cls.lists, cls.raw = the_list()

    def decision(self, kind, sub=SUBSCRIPTION, sku=None):
        return self.watched.case(kind, sub, sku)

    def test_the_thirty_one_recommendations_are_nine_decisions_and_each_has_a_case_and_none_is_lost(self):
        cases = self.watched.cases()
        self.assertEqual(len(cases), 9)
        self.assertEqual(sorted((c.subscription_id == SUBSCRIPTION, c.facts["advisor"]["type"], c.facts["advisor"]["n"]) for c in cases),
                         sorted([(True, VM, 6), (True, VM, 6), (True, COSMOS, 6), (True, SAVINGS_PLAN, 2), (False, VM, 6), (False, SAVINGS_PLAN, 2)] + [(True, DISKS, 1)] * 3))
        self.assertEqual({c.status for c in cases}, {"needs_human"})
        self.assertEqual(sum(c.facts["advisor"]["n"] for c in cases), 31, "none lost and none counted twice")

    def test_variants_that_differ_only_by_term_and_look_back_are_one_decision_and_a_different_target_is_another(self):
        small, big = self.decision(VM, sku=D2S), self.decision(VM, sku=D2ALS)
        self.assertEqual((small.facts["advisor"]["n"], big.facts["advisor"]["n"]), (6, 6))
        self.assertEqual({(row[0], row[1], row[2]) for row in small.facts["advisor"]["rows"]}, {(D2S, 2, "swedencentral")})
        self.assertEqual({(row[3], row[6]) for row in small.facts["advisor"]["rows"]}, {(t, b) for t in TERMS for b in LOOKBACKS}, "every term and every look-back is a row")
        self.assertNotEqual(small.case_id, big.case_id)

    def test_the_figure_of_a_decision_is_its_smallest_variant_and_its_range_is_kept(self):
        said = self.decision(VM, sku=D2S).facts["advisor"]
        self.assertEqual((said["usd"], said["low"], said["high"]), (321.0, 321.0, 960.0))
        self.assertEqual([row[4] for row in said["rows"]], sorted(row[4] for row in said["rows"]), "the smallest first")
        self.assertEqual(month(self.decision(VM, sku=D2S)), round(321.0 / 12, 2))

    def test_the_commitments_of_one_subscription_that_cover_the_same_spend_are_alternatives_and_only_the_larger_is_counted(self):
        mine = [self.decision(VM, sku=D2S), self.decision(VM, sku=D2ALS), self.decision(COSMOS), self.decision(SAVINGS_PLAN)]
        self.assertEqual([case.facts["advisor"]["usd"] for case in mine], [321.0, 214.0, 53.5, 0.0], "the reservations (588.5) beat the savings plan (520)")
        self.assertEqual([case.facts["advisor"]["alt"] for case in mine], ["", "", "", "reservations"])
        self.assertEqual(self.decision(SAVINGS_PLAN).facts["advisor"]["low"], 520.0, "an alternative keeps its own figures")
        theirs = [self.decision(VM, SUB_B), self.decision(SAVINGS_PLAN, SUB_B)]
        self.assertEqual([case.facts["advisor"]["usd"] for case in theirs], [0.0, 585.0], "in the other subscription the savings plan is larger")
        self.assertEqual(theirs[0].facts["advisor"]["alt"], "savings plan")

    def test_the_disks_are_not_alternatives_of_anything_and_stay_as_they_were(self):
        disks = [c for c in self.watched.cases() if c.facts["advisor"]["type"] == DISKS]
        self.assertEqual([c.facts["advisor"]["usd"] for c in disks], [18.42] * 3)
        self.assertEqual(len({c.resource_id for c in disks}), 3)

    def test_what_every_surface_counts_is_the_same_honest_figure_and_not_the_sum_of_every_variant(self):
        self.assertAlmostEqual(sum(case.facts["advisor"]["usd"] for case in self.watched.cases()), COUNTED, places=2)
        self.assertLess(COUNTED * 5, self.raw, "the first version stated every variant: about six times too much")
        stated = sum(month(case) for case in self.watched.cases())
        self.assertAlmostEqual(stated, COUNTED / 12, delta=0.005 * 9)
        plans = [plan for plan in self.store_plans() if plan.family == ADVISE]
        self.assertAlmostEqual(sum(plan.saving_usd_month or 0.0 for plan in plans), COUNTED / 12, delta=0.005 * 9)
        results = [e for e in of_type(self.watched.events, "case.result") if e["detector"] == ADVISOR]
        self.assertAlmostEqual(sum(e["monthlySavingUsd"] or 0.0 for e in results), COUNTED / 12, delta=0.005 * 9)

    def store_plans(self):
        return self.watched.store.plans_open()

    def test_each_decision_has_one_request_and_an_alternative_has_one_too_so_that_a_person_can_decide_on_each(self):
        plans = self.store_plans()
        self.assertEqual(len(plans), 9)
        self.assertEqual({plan.case_id for plan in plans}, {case.case_id for case in self.watched.cases()})
        self.assertEqual(len(of_type(self.watched.events, "plan.created")), 9)

    def test_a_row_says_the_sku_the_quantity_the_region_the_term_the_saving_a_year_the_look_back_and_the_scope(self):
        (row,) = [r for r in self.decision(SAVINGS_PLAN, SUB_B).facts["advisor"]["rows"] if r[3] == "P3Y"]
        self.assertEqual([row[0], row[3], row[5], row[6], row[7]], ["Compute_Savings_Plan", "P3Y", "USD", 30, "Single"])

    def test_the_impact_that_advisor_gives_is_kept_as_a_typed_fact(self):
        self.assertEqual(self.decision(VM, sku=D2S).facts["impact"], "high")
        self.assertEqual({c.facts["impact"] for c in self.watched.cases() if c.facts["advisor"]["type"] == DISKS}, {"medium"})

    def test_the_figure_is_a_scenario_that_says_it_is_advisors_own_and_that_only_the_smallest_variant_is_counted(self):
        case = self.decision(VM, sku=D2S)
        plan = next(p for p in self.store_plans() if p.case_id == case.case_id)
        said = brief_mod.build_brief(case, plan, now=NOW)
        self.assertEqual((said.saving.level, round(said.saving.monthly, 2)), ("Scenario", month(case)))
        self.assertIn("smallest of its variants", said.saving.basis)
        self.assertIn("alternatives", said.saving.basis)

    def test_the_history_says_each_case_with_its_figure_and_that_nothing_was_judged_by_a_model(self):
        results = [e for e in of_type(self.watched.events, "case.result") if e["detector"] == ADVISOR]
        self.assertEqual(len(results), 9)
        self.assertEqual(self.watched.tenant.chat_calls(), [], "Advisor's own claims are not judged by the models")
        self.assertEqual(len(of_type(self.watched.events, "lead.found")), 31)
        self.assertEqual((self.watched.summary.leads, self.watched.summary.cases, self.watched.summary.needs_human), (31, 9, 9))
        self.assertEqual(sum("an alternative, none counted" in e["summary"] for e in results), 2)


class OnePerRecommendationAndNoneDroppedSilently(unittest.TestCase):
    def test_a_variant_in_another_currency_is_counted_and_not_added_and_the_history_says_so(self):
        lists, _ = the_list()
        lists[SUBSCRIPTION][12] = rec(COSMOS, SUBSCRIPTION, 20, annual=999.0, savingsCurrency="EUR", term="P1Y", lookbackPeriod="7")
        watched = Watched(estate(lists)).run()
        digest = watched.case(COSMOS).facts["advisor"]
        self.assertEqual((digest["n"], digest["added"], digest["skipped"], digest["currencies"]), (6, 5, 1, ["EUR"]))
        self.assertEqual((digest["low"], digest["usd"]), (65.0, 65.0), "the smallest variant in dollars is counted: the one in euros is not changed into dollars")
        self.assertTrue(any(r[5] == "EUR" and r[4] == 999.0 for r in digest["rows"]), "its row is there, with its own figure and currency")
        self.assertTrue(any("not added" in e["note"] and "EUR" in e["note"] for e in of_type(watched.events, "run.note")))
        self.assertAlmostEqual(sum(month(c) for c in watched.cases()), (COUNTED - 53.5 + 65.0) / 12, delta=0.05)

    def test_a_disk_that_names_no_currency_is_read_in_dollars_only_when_the_cost_lines_of_the_subscription_are(self):
        dollars = Watched().run()
        self.assertEqual([c.facts["advisor"]["skipped"] for c in dollars.cases() if c.facts["advisor"]["type"] == DISKS], [0, 0, 0])
        euros = estate()
        euros.currency = "EUR"
        other = Watched(euros).run()
        disks = [c for c in other.cases() if c.facts["advisor"]["type"] == DISKS]
        self.assertEqual(([c.facts["advisor"]["skipped"] for c in disks], [month(c) for c in disks]), ([1, 1, 1], [0.0, 0.0, 0.0]))
        self.assertEqual(len(other.store.plans_open()), 9, "a recommendation without a figure in dollars is still a request")

    def test_a_recommendation_that_says_neither_a_problem_nor_a_solution_still_makes_a_request_with_words_of_code(self):
        bare = rec(VM, SUB_B, 9)
        bare["properties"]["shortDescription"] = {}
        watched = Watched(estate({SUBSCRIPTION: [], SUB_B: [bare]})).run()
        (case,) = watched.cases()
        self.assertTrue(brief_mod.advice_of(case), "it has words")
        self.assertEqual(len(watched.store.plans_open()), 1)

    def test_no_guard_of_the_ai_cases_holds_an_advisor_case_back_a_small_figure_ten_open_questions_or_the_investigation(self):
        watched = Watched()
        for n in range(ADVICE_OPEN_MAX):  # the open requests that the AIs did not settle are the whole of ADVICE_OPEN_MAX
            watched.store.plan_put(make_plan(plan_id=f"open{n}", case_id=f"kopen{n}", family=ADVISE, resource_id=disk_id(f"other-{n}"), state="open", approvers=(TINO,),
                                             preconditions={"family": ADVISE, "caseStatus": "needs_human"}, expires_at="2026-11-30T00:00:00Z"))
        ran = investigate.Investigation(ran=True)
        with mock.patch.object(investigate, "investigate", return_value=ran):
            watched.run()
        self.assertEqual(len([p for p in watched.store.plans_open() if p.case_id.startswith("k") and not p.case_id.startswith("kopen")]), 9)
        self.assertFalse([e for e in of_type(watched.events, "case.held")])

    def test_the_next_watch_makes_no_second_request_for_a_request_that_is_open_and_keeps_the_cases_up_to_date(self):
        watched = Watched().run()
        first = {plan.plan_id for plan in watched.store.plans_open()}
        lists, _ = the_list()
        lists[SUBSCRIPTION].append(rec(VM, SUBSCRIPTION, 40, annual=100.0, sku=D2S, qty="2", term="P1Y", lookbackPeriod="90"))
        watched.tenant.advisor_of = lists
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual({plan.plan_id for plan in watched.store.plans_open()}, first)
        self.assertEqual(len(watched.cases()), 9)
        said = watched.case(VM, sku=D2S).facts["advisor"]
        self.assertEqual((said["n"], said["low"]), (7, 100.0), "a new variant is a row of the decision, and it is the smallest now")
        self.assertEqual((said["usd"], said["alt"], watched.case(SAVINGS_PLAN).facts["advisor"]["usd"]), (0.0, "savings plan", 520.0),
                         "the reservations (367.5) are now smaller than the savings plan (520): the alternative that is counted moves while the requests wait")
        self.assertEqual(watched.case(VM, sku=D2S).runs_seen, 2)
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
        self.assertEqual(len(watched.store.plans_open()), 8)
        watched.clock.advance(days=31)
        watched.run()
        self.assertEqual((watched.case(COSMOS).status, len([p for p in watched.store.plans_open() if p.case_id == case.case_id])), ("needs_human", 1))


class ADecisionThatAdvisorChangesOrDelists(unittest.TestCase):
    def test_the_quantity_that_advisor_recomputes_is_the_same_case_with_the_new_figure_and_a_decline_is_kept(self):
        watched = Watched(estate({SUBSCRIPTION: [], SUB_B: variants(VM, SUB_B, 100.0, 0, sku=D2S, qty="2")})).run()
        case = watched.case(VM, SUB_B)
        watched.store.plan_put(replace(next(p for p in watched.store.plans_open() if p.case_id == case.case_id), state="declined"))
        watched.store.case_put(replace(case, status="declined"))
        watched.tenant.advisor_of = {SUBSCRIPTION: [], SUB_B: variants(VM, SUB_B, 150.0, 0, sku=D2S, qty="3")}
        watched.clock.advance(days=1)
        watched.run()
        (again,) = watched.cases()
        self.assertEqual((again.case_id, again.status, watched.store.plans_open()), (case.case_id, "declined", []), "no second case and no second request, and the decline stands")
        self.assertEqual((again.facts["advisor"]["usd"], {row[1] for row in again.facts["advisor"]["rows"]}), (160.5, {3}), "but what Advisor says is brought up to date")
        self.assertEqual(of_type(watched.events, "plan.created"), [])

    def test_a_decision_that_advisor_does_not_list_any_more_is_closed_and_leaves_savings_found(self):
        watched = Watched().run()
        before = rows_of(Console(store=watched.store).get("/ops/savings"))["Waiting for a person"]
        lists, _ = the_list()
        lists[SUBSCRIPTION] = [r for r in lists[SUBSCRIPTION] if r["properties"]["recommendationTypeId"] != COSMOS]
        watched.tenant.advisor_of = lists
        watched.clock.advance(days=1)
        watched.run()
        (case,) = [c for c in watched.cases() if c.facts["advisor"]["type"] == COSMOS]
        plan = watched.store.plan_get(case.plan_id)
        self.assertEqual((case.status, plan.state, plan.preconditions["takenBack"]), ("expired", "expired", "delisted"))
        self.assertIn(brief_mod.TAKEN_BACK["delisted"], brief_mod.build_brief(case, plan, now=NOW).outcome.lines)
        self.assertTrue(any("closed: Advisor does not list it any more" in e["note"] for e in of_type(watched.events, "run.note")))
        after = rows_of(Console(store=watched.store).get("/ops/savings"))["Waiting for a person"]
        self.assertEqual((before["Findings"], after["Findings"], len(watched.store.plans_open())), ("9", "8", 8))
        self.assertNotEqual(before["Saving a year"], after["Saving a year"], "its figure is no longer counted")

    def test_a_decline_of_a_decision_that_is_gone_stays_and_so_does_an_answer_that_is_recorded(self):
        watched = Watched().run()
        gone = watched.case(COSMOS)
        watched.store.decision_put(make_decision(plan_id=gone.plan_id, approver_oid=TINO, decision="later"))
        lists, _ = the_list()
        lists[SUBSCRIPTION] = [r for r in lists[SUBSCRIPTION] if r["properties"]["recommendationTypeId"] != COSMOS]
        watched.tenant.advisor_of = lists
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual((watched.store.plan_get(gone.plan_id).state, watched.store.case_get(gone.case_id).status), ("open", "needs_human"))

    def test_a_subscription_whose_advisor_list_could_not_be_read_has_nothing_closed(self):
        watched = Watched().run()
        watched.tenant.broken = {("advisor", SUBSCRIPTION): 403}
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual(({c.status for c in watched.cases()}, len(watched.store.plans_open())), ({"needs_human"}, 9))
        self.assertFalse([e for e in of_type(watched.events, "run.note") if "does not list" in e["note"]])


class WhatIsOneDecisionAndWhatIsNot(unittest.TestCase):
    def cases_of(self, lists):
        return sorted((c.facts["advisor"]["n"], c.facts["advisor"]["usd"], c.facts["advisor"]["alt"]) for c in Watched(estate({SUBSCRIPTION: [], SUB_B: lists})).run().cases())

    def test_a_decision_with_one_variant_counts_that_figure(self):
        self.assertEqual(self.cases_of([rec(VM, SUB_B, 0, annual=480.0)]), [(1, 480.0, "")])

    def test_a_recommendation_that_names_no_term_or_no_look_back_is_its_own_decision_and_is_never_merged_by_a_guess(self):
        whole = variants(VM, SUB_B, 100.0, 0, lookbacks=(7,))
        no_back, no_term = rec(VM, SUB_B, 50, annual=40.0, term="P1Y", lookbackPeriod=""), rec(VM, SUB_B, 51, annual=30.0, term="")
        found = self.cases_of(whole + [no_back, no_term])
        self.assertEqual(sorted(n for n, _, _ in found), [1, 1, 2], "the two of one decision, and the two that cannot be told by their term and look-back, each alone")

    def test_look_backs_with_different_quantities_are_one_decision_and_its_figure_is_the_smallest(self):
        wanted = [("P1Y", 7, "2", 200.0), ("P1Y", 30, "3", 280.0), ("P1Y", 60, "3", 300.0), ("P3Y", 7, "2", 400.0), ("P3Y", 30, "3", 520.0), ("P3Y", 60, "3", 560.0)]
        rows = [rec(VM, SUB_B, n, annual=a, sku=D2S, qty=q, term=t, lookbackPeriod=str(b)) for n, (t, b, q, a) in enumerate(wanted)]
        (case,) = Watched(estate({SUBSCRIPTION: [], SUB_B: rows})).run().cases()
        said = case.facts["advisor"]
        self.assertEqual((said["n"], said["usd"], {row[1] for row in said["rows"]}), (6, 200.0, {2, 3}))
        self.assertIn("differ by quantity, term and look-back", brief_mod.advisor_of(case).sentence)

    def test_the_same_product_in_another_scope_is_an_alternative_and_only_the_larger_is_counted(self):
        single = variants(VM, SUB_B, 100.0, 0, lookbacks=(7,), scope="Single")
        shared = variants(VM, SUB_B, 150.0, 10, lookbacks=(7,), scope="Shared")
        self.assertEqual(self.cases_of(single + shared), [(2, 0.0, "reservations"), (2, 160.5, "")])

    def test_a_different_region_scope_type_or_sub_category_is_another_decision_and_never_merged(self):
        base = variants(VM, SUB_B, 100.0, 0, lookbacks=(7,))
        other = {"region": variants(VM, SUB_B, 100.0, 10, lookbacks=(7,), region="northeurope", location="northeurope"),
                 "scope": variants(VM, SUB_B, 100.0, 10, lookbacks=(7,), scope="Shared"),
                 "type": variants(COSMOS, SUB_B, 100.0, 10, lookbacks=(7,), sku=D2S, qty="1", region="swedencentral"),
                 "sub-category": variants(VM, SUB_B, 100.0, 10, lookbacks=(7,), recommendationSubCategory="Other")}
        for name, changed in other.items():
            with self.subTest(name):
                self.assertEqual(sorted(n for n, _, _ in self.cases_of(base + changed)), [2, 2], f"a different {name} is not a variant of the same purchase")
        self.assertEqual(sorted(n for n, _, _ in self.cases_of(base + variants(VM, SUB_B, 100.0, 10, lookbacks=(7,)))), [4], "and all the same is")

    def test_a_different_product_is_another_decision_and_both_are_counted(self):
        a, b = variants(VM, SUB_B, 100.0, 0, lookbacks=(7,), sku=D2S), variants(VM, SUB_B, 100.0, 10, lookbacks=(7,), sku=D2ALS)
        self.assertEqual(self.cases_of(a + b), [(2, 107.0, ""), (2, 107.0, "")])

    def test_a_recommendation_about_a_resource_that_overlaps_another_about_the_same_resource_counts_the_larger(self):
        disk = disk_id("disk-0", SUB_B)
        self.assertEqual(self.cases_of([rec(DISKS, SUB_B, 0, annual=20.0, resource=disk), rec(DISKS, SUB_B, 1, annual=30.0, resource=disk)]), [(2, 30.0, "")])


class TheSavingsFoundPageCountsTheHonestFigure(unittest.TestCase):
    def test_savings_found_adds_up_what_the_decisions_count_and_an_alternative_adds_nothing(self):
        watched = Watched().run()
        row = rows_of(Console(store=watched.store).get("/ops/savings"))["Waiting for a person"]
        self.assertEqual(row["Findings"], "9")
        self.assertIn("Could save about", row["Saving a year"])
        self.assertIn(f"${round(12 * sum(month(c) for c in watched.cases())):,}", row["Saving a year"])
        self.assertAlmostEqual(12 * sum(month(c) for c in watched.cases()), COUNTED, delta=0.06 * 9)
        raw = the_list()[1]
        self.assertNotIn(f"${round(raw):,}", row["Saving a year"], "not the sum of every variant")


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
        mine = [e for e in of_type(watched.events, "case.result") if e["detector"] == "orphan-managed-disk"]
        self.assertEqual(len(mine), 1, "one line of the History for it, under its own detector, and it is not the line of the Advisor step")
        self.assertNotIn("Azure Advisor", mine[0]["summary"])
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

    def test_an_older_case_is_not_rewritten_by_advisor_it_only_gets_what_advisor_says_and_keeps_its_status_its_time_and_its_words(self):
        disk = disk_id("disk-0")
        lists = {SUBSCRIPTION: [rec(DISKS, SUBSCRIPTION, 0, annual=18.42, resource=disk)], SUB_B: []}
        watched = Watched(estate(lists))
        mate = make_case(case_id=f"k{detectors.ident('orphan-managed-disk', disk)}", detector="orphan-managed-disk", status="proposed", recommendation="delete", resource_id=disk,
                         resource_type="microsoft.compute/disks", resource_name="disk-0", resource_group="rg-app", subscription_id=SUBSCRIPTION, facts={"diskState": "unattached"}, advice={},
                         updated_at="2026-11-01T00:00:00Z", runs_seen=3, models={"detective": "model-a"})
        watched.store.case_put(mate)
        watched.run()
        found = watched.store.case_get(mate.case_id)
        self.assertEqual((found.status, found.updated_at, found.runs_seen, found.advice, found.detector), ("proposed", "2026-11-01T00:00:00Z", 3, {}, "orphan-managed-disk"))
        self.assertEqual((found.facts["advisor"]["n"], found.facts["diskState"]), (1, "unattached"), "Advisor's figure is on its case, and its words are not")
        self.assertEqual([e for e in watched.events if e.get("caseId") == mate.case_id], [], "no line of the History says that Advisor made or judged it")
        self.assertEqual((watched.summary.cases, watched.store.plans_open()), (0, []), "the Advisor step made and asked about nothing")

    def test_a_disk_that_the_investigation_priced_and_advisor_lists_too_is_one_case_and_savings_found_counts_the_models_figure_once(self):
        disk = disk_id("disk-0")
        lists = {SUBSCRIPTION: [rec(DISKS, SUBSCRIPTION, 0, annual=18.42, resource=disk)], SUB_B: []}  # Advisor says 18.42 a year for it
        watched = Watched(estate(lists))
        digest = {"action": "remove", "price": {"lowUsd": 5.0, "highUsd": 5.0, "billUsd": 5.0, "lines": 1, "resources": 1, "form": "none"}}  # the investigation priced it at 5.00 a month
        mate = make_case(case_id=f"k{detectors.ident('investigation', disk)}", detector="investigation", status="needs_human", recommendation="change", resource_id=disk,
                         resource_type="microsoft.compute/disks", resource_name="disk-0", resource_group="rg-app", subscription_id=SUBSCRIPTION, saving_usd_month=5.0, cost_usd_30d=9.0,
                         facts={"basis": "oversized", "proposal": "change", "metrics": {}, "change": digest}, advice={}, updated_at="2026-11-01T00:00:00Z", runs_seen=2)
        watched.store.case_put(mate)
        watched.run()
        found = watched.store.case_get(mate.case_id)
        self.assertEqual((found.facts["change"], found.facts["advisor"]["n"]), (digest, 1), "the case holds both: the model's price and what Advisor says")
        self.assertEqual([c.case_id for c in watched.store.cases_recent() if c.resource_id.lower() == disk.lower()], [mate.case_id], "never two cases for one disk")
        self.assertGreater(brief_mod.advisor_saving(found) or 0, 0, "Advisor's own figure is still read from its digest, beside the model's")
        row = rows_of(Console(store=watched.store).get("/ops/savings"))["Waiting for a person"]
        self.assertTrue(row["Saving a year"].startswith("Could save about $60 a year ($5.00 a month)"), "twelve times the model's 5.00 and nothing of Advisor's 18.42 a year added: " + row["Saving a year"])

    def test_the_case_that_advisor_made_before_the_investigation_found_the_same_disk_leaves_savings_found_when_the_investigation_case_exists(self):
        disk = disk_id("disk-0")
        lists = {SUBSCRIPTION: [rec(DISKS, SUBSCRIPTION, 0, annual=18.42, resource=disk)], SUB_B: []}
        watched = Watched(estate(lists)).run()
        (own,) = [c for c in watched.store.cases_recent() if c.resource_id.lower() == disk.lower()]
        self.assertEqual(own.detector, "advisor-cost", "an earlier Watch made Advisor's own case, which was counted at Advisor's figure")
        digest = {"action": "remove", "price": {"lowUsd": 5.0, "highUsd": 5.0, "billUsd": 5.0, "lines": 1, "resources": 1, "form": "none"}}
        mate = make_case(case_id=f"k{detectors.ident('investigation', disk)}", detector="investigation", status="needs_human", recommendation="change", resource_id=disk,
                         resource_type="microsoft.compute/disks", resource_name="disk-0", resource_group="rg-app", subscription_id=SUBSCRIPTION, saving_usd_month=5.0, cost_usd_30d=9.0,
                         facts={"basis": "oversized", "proposal": "change", "metrics": {}, "change": digest}, advice={}, updated_at="2026-11-01T00:00:00Z", runs_seen=2)
        watched.store.case_put(mate)
        watched.clock.advance(hours=1)
        watched.run()
        live = [c for c in watched.store.cases_recent() if c.resource_id.lower() == disk.lower() and c.status in ("needs_human", "proposed")]
        self.assertEqual([c.case_id for c in live], [mate.case_id], "the disk is one case that waits for a person: Advisor's own case is closed")
        row = rows_of(Console(store=watched.store).get("/ops/savings"))["Waiting for a person"]
        self.assertTrue(row["Saving a year"].startswith("Could save about $60 a year ($5.00 a month)"), row["Saving a year"])


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
        self.assertEqual(len(watched.store.plans_open()), 9)
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
        cls.case = cls.watched.case(VM, sku=D2S)
        cls.plan = next(plan for plan in cls.watched.store.plans_open() if plan.case_id == cls.case.case_id)
        cls.year = brief_mod.usd_text(cls.case.facts["advisor"]["usd"])
        cls.page = Console(store=cls.watched.store).get(f"/ok/{cls.plan.plan_id}")

    def test_the_page_shows_the_one_decision_with_its_variants_the_smallest_counted_the_range_and_that_they_are_alternatives(self):
        reply = self.page
        self.assertEqual((reply.status, reply.problems), (200, []))
        table = reply.table("advisor")
        self.assertEqual((table.headers, len(table.rows)), (["For how long", "Saves a year", "Looked back"], 6), "what is the same in every variant is said once, in the sentence")
        self.assertEqual([(row["For how long"], row["Saves a year"], row["Looked back"]) for row in (table.rows[0], table.rows[-1])],
                         [("1 year", "$321", "7 days"), ("3 years", "$960", "60 days")], "the smallest first")
        text = reply.content.replace("&#x27;", "'")
        self.assertIn("6 variants of one purchase (Standard_D2s_v6 × 2, swedencentral, one subscription) that differ by term and look-back", text)
        self.assertIn(f"they are alternatives, and Meternaut counts the smallest: {self.year} a year", text)
        self.assertIn("The largest is $960 a year with a term of 3 years", text)
        self.assertIn(f"Azure Advisor estimates that this could save about {self.year} a year", text)
        self.assertIn(brief_mod.ADVISOR_BASIS_MANY, text)
        self.assertNotIn("add up to", text)

    def test_the_page_of_an_alternative_says_what_is_counted_instead_and_counts_nothing_for_itself(self):
        case = self.watched.case(SAVINGS_PLAN)
        plan = next(p for p in self.watched.store.plans_open() if p.case_id == case.case_id)
        text = Console(store=self.watched.store).get(f"/ok/{plan.plan_id}").content.replace("&#x27;", "'")
        self.assertIn("Advisor lists another purchase for this subscription that saves more (reservations)", text)
        self.assertIn("nothing is added for this request", text)
        self.assertNotIn("Meternaut worked out that this could save", text)
        self.assertEqual(brief_mod.build_brief(case, plan, now=NOW).saving.monthly, None)

    def test_the_page_says_the_order_of_work_that_nothing_was_checked_and_that_meternaut_does_not_buy(self):
        content = self.page.content
        for words in (brief_mod.ADVISOR_FIRST, brief_mod.ADVISOR_FIRST_RISK, "Meternaut does not buy it", brief_mod.ADVISOR_RISK):
            self.assertIn(words, content)
        self.assertNotIn("Why the AIs think so", content)
        self.assertIn("How sure it is", content)

    def test_the_details_say_that_no_ai_looked_at_it_and_claim_no_text_or_fact_of_an_ai(self):
        content = self.page.content
        self.assertIn("No AI looked at this finding", content)
        self.assertIn("The typed facts that Meternaut recorded", content)
        for text in ("What the AIs wrote, in full", "The typed facts that the AIs saw", "The second AI was not asked"):
            self.assertNotIn(text, content)

    def test_the_footer_names_no_model_and_the_weekly_summary_says_that_no_ai_looked_at_it(self):
        self.assertNotIn("Models:", self.page.content, "no model is named for a request that no model touched")
        letter = letters.digest_letter(Person(TINO, "Tino", ("owner", "approver"), "tino@example.com"), "https://meternaut.example", NOW, [(self.plan, self.case)])
        self.assertIn("No AI looked at it.", letter.text)

    def test_only_a_commitment_says_what_its_figure_rests_on_and_a_disk_says_nothing_of_rates(self):
        commitment = self.page.content.replace("&#x27;", "'")
        self.assertIn("based on your own rates and usage", commitment)
        disk = next(c for c in self.watched.cases() if c.facts["advisor"]["type"] == DISKS)
        text = Console(store=self.watched.store).get(f"/ok/{disk.plan_id}").content
        self.assertIn("Its figure is $18.42 a year", text)
        for words in ("retail", "your own rates", "rates"):
            self.assertNotIn(words, text)

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
