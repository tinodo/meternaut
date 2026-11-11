"""A finding about point-to-site gateways that carry more scale units than anybody uses: what code works out from what the tools recorded (cases/gateways.py), what the decision brief says of
it (cases/brief.py), and the page, the letter and the card that render it. Every name, id and number in it is INVENTED.

The Investigator finds such gateways with its generic tools and tells nothing of them to code: these tests run the real investigation with a fake Foundry and a fake toolbox (the harness of
test_investigate) and read what it keeps. Many gateways are one case and one request, as every finding about many resources is.
"""
import json
import re
import unittest
from dataclasses import replace

import support  # noqa: F401  (it puts the app on the path)
from test_investigate import FakeFoundry, FakeToolbox, Harness, answer, entry, finding, resource
from test_letters import BASE, CONTACTS, MOST_WORDS, PERSON, word_count
from test_unread import page_of, walk_blocks
from test_web_support import NOW as WEB_NOW

from cases import approvals, brief, cards, gateways, letters
from cases.models import ADVISE, GROUP_FACT, CaseRecord
from cases.web import figures

TYPE = "microsoft.network/p2svpngateways"
METRIC = "P2SConnectionCount"
HOSTILE = "<script>alert(1)</script>\n[click](https://evil.example/x) \u202eevil " + "n" * 100


def record(units=12, peak=0, days=14, **more) -> dict:
    """What the tools recorded for one gateway: its scale units among the properties that they showed, and the connection count that they measured (a total, the highest value and the days)."""
    reading = {"total": 0 if peak == 0 else peak * days, "max": peak, "average": 0 if peak == 0 else float(peak), "days": 30, "days_with_data": days, "unit": "Count",
               "totals": [0 if peak == 0 else peak * days]}
    block = {"type": TYPE, "properties": {"vpnGatewayScaleUnit": units}, "metrics": {METRIC: reading}}
    block.update(more)
    return block


def estate(units, peaks=None, days=14, per_unit=6.0, **changes):
    """Gateways r1, r2, ... with the scale units given, in three resource groups, costing `per_unit` a month for each scale unit, and the evidence of each."""
    peaks = peaks or [0] * len(units)
    resources = [resource(n, resource_type=TYPE, name=f"gw-{n:02d}", resource_group=f"rg-{n % 3:02d}", cost_usd_30d=round(count * per_unit, 2), **changes) for n, count in enumerate(units, 1)]
    evidence = {f"r{n}": record(count, peak, days) for n, (count, peak) in enumerate(zip(units, peaks), 1)}
    return resources, evidence


def raw_of(count, basis="no-usage", proposal="investigate", cited=0, **changes):
    handles = [f"r{n}" for n in range(1, count + 1)]
    return finding(handles=handles, basis=basis, proposal=proposal, confidence=0.8, summary="Nobody connected to these gateways in the window.",
                   evidence=[entry(handle, METRIC, cited) for handle in handles], **changes)


def watch(resources, evidence, raw=None) -> Harness:
    h = Harness(FakeFoundry(answer(raw if raw is not None else raw_of(len(resources)))), FakeToolbox(resources, evidence), with_store=True)
    h.go()
    return h


def case_and_plan(h) -> tuple[CaseRecord, object]:
    (case,) = h.store.cases_recent()
    (plan,) = h.store.plans_open()
    return case, plan


UNITS = [12, 12, 12, 12, 12, 12, 40]  # 112 scale units, 672 US dollars a month, and nobody connected


class TheAnalysis(unittest.TestCase):
    def test_a_gateway_that_nobody_used_is_counted_with_the_smallest_size_and_the_share_of_its_cost_that_goes(self):
        digest = gateways.analyse(record(units=12, peak=0, days=14), 72.0)
        self.assertEqual(digest, {"gateways": 1, "counted": 1, "units": 12, "target": 1, "peak": 0, "days": 14, "quiet": 1, "limit": 10000, "costUsd30d": 72.0, "savingUsd": 66.0})

    def test_a_gateway_that_was_used_keeps_the_smallest_size_that_carries_the_most_connections_that_it_saw(self):
        for peak, target in ((1, 1), (500, 1), (501, 4), (1000, 4), (1001, 7), (5001, 11), (10001, 12)):
            with self.subTest(peak=peak):
                digest = gateways.analyse(record(units=12, peak=peak), 120.0)
                self.assertEqual((digest["counted"], digest["target"], digest["peak"], digest["quiet"]), (1, target, peak, 0))
                self.assertEqual(digest.get("savingUsd", 0.0), round(120.0 * (12 - target) / 12, 2))
        self.assertEqual(gateways.analyse(record(units=12, peak=200000), 120.0)["target"], 12, "more connections than any size carries: nothing is taken away")

    def test_a_gateway_at_the_smallest_size_has_nothing_to_take_away_and_no_figure(self):
        digest = gateways.analyse(record(units=1), 6.0)
        self.assertEqual((digest["counted"], digest["target"], digest["quiet"]), (1, 1, 1))
        self.assertNotIn("savingUsd", digest)

    def test_a_gateway_whose_record_lacks_the_scale_units_or_the_connections_is_not_counted_and_is_never_one_with_none(self):
        no_units = record()
        del no_units["properties"]
        no_metric = record()
        del no_metric["metrics"]
        absent = record(days=0)
        absent["metrics"][METRIC].update(total=None, max=None, average=None, days_with_data=0)
        for label, block in (("no units", no_units), ("no metric", no_metric), ("no day with a value", absent), ("not a record", None), ("a list", [1]), ("empty", {}),
                             ("units as text", record(units="12")), ("units of nothing", record(units=0)), ("too many units", record(units=201)), ("units as a flag", record(units=True)),
                             ("a negative peak", record(peak=-1))):
            with self.subTest(label):
                digest = gateways.analyse(block, 72.0)
                self.assertEqual((digest["gateways"], digest["counted"], digest["units"], digest["quiet"]), (1, 0, 0, 0))
                self.assertNotIn("costUsd30d", digest)

    def test_a_total_of_nothing_with_a_day_that_had_a_value_is_nobody_and_no_total_is_not(self):
        only_total = record()
        only_total["metrics"][METRIC]["max"] = None
        self.assertEqual(gateways.analyse(only_total, None)["peak"], 0)
        only_total["metrics"][METRIC]["total"] = 4
        self.assertEqual(gateways.analyse(only_total, None)["counted"], 0, "a total above nothing without a highest value says nothing of the peak")

    def test_a_cost_that_is_not_there_or_is_nothing_makes_no_figure(self):
        for cost in (None, 0, 0.0, -5.0, float("nan"), float("inf")):
            with self.subTest(cost=cost):
                digest = gateways.analyse(record(), cost)
                self.assertEqual((digest["counted"], "costUsd30d" in digest, "savingUsd" in digest), (1, False, False))

    def test_many_gateways_are_a_digest_made_from_the_digests_of_each(self):
        parts = [gateways.analyse(record(units=12, peak=0, days=14), 72.0), gateways.analyse(record(units=40, peak=700, days=9), 240.0), gateways.analyse({}, 50.0)]
        digest = gateways.combine(parts)
        self.assertEqual(digest, {"gateways": 3, "counted": 2, "units": 52, "target": 5, "peak": 700, "days": 9, "quiet": 1, "costUsd30d": 312.0, "savingUsd": round(66.0 + 240.0 * 36 / 40, 2)})
        self.assertNotIn("limit", digest, "what one size carries is said of one gateway")
        self.assertEqual(gateways.combine([parts[0]])["limit"], 10000)

    def test_a_digest_of_nothing_is_none_and_what_is_not_a_digest_is_left_out(self):
        self.assertIsNone(gateways.combine([]))
        self.assertIsNone(gateways.combine([None, "x", 4]))
        self.assertEqual(gateways.combine([None, gateways.analyse(record(), 6.0)])["gateways"], 1)


class WhatTheInvestigationKeeps(unittest.TestCase):
    def setUp(self):
        resources, evidence = estate(UNITS)
        self.h = watch(resources, evidence)
        self.case, self.plan = case_and_plan(self.h)

    def test_seven_gateways_are_one_case_and_one_request_that_changes_nothing_in_azure(self):
        self.assertEqual((self.h.result.cases, len(self.h.store.cases_recent()), len(self.h.store.plans_open())), (1, 1, 1))
        self.assertEqual((self.case.resource_name, self.case.recommendation, self.case.status, self.case.cost_usd_30d), ("gw-07", "investigate", "needs_human", 672.0), "the dearest, with what all cost")
        self.assertEqual((self.plan.family, self.plan.case_id), (ADVISE, self.case.case_id))
        self.assertEqual(self.case.facts[GROUP_FACT]["count"], 7)

    def test_the_facts_of_the_case_hold_the_digest_of_the_group_as_numbers_and_nothing_of_the_estate(self):
        digest = self.case.facts[gateways.KEY]
        self.assertEqual(digest, {"gateways": 7, "counted": 7, "units": 112, "target": 7, "peak": 0, "days": 14, "quiet": 7, "costUsd30d": 672.0, "savingUsd": 630.0})
        self.assertTrue(all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in digest.values()))
        self.assertEqual(sorted(self.case.facts), sorted(["basis", "citedMetrics", "costUsd30d", "finding", "metricDays", "metricUnits", "metrics", "proposal", GROUP_FACT, gateways.KEY]))
        json.dumps(self.case.facts)

    def test_the_advise_plan_takes_the_figure_of_the_digest_and_code_wrote_its_words(self):
        self.assertEqual((self.plan.saving_usd_month, self.plan.waiting_costs_usd_day), (630.0, 21.0))
        self.assertEqual(self.plan.title, "Look at 7 point-to-site gateways in 3 groups, the first is gw-07")
        self.assertEqual((self.plan.what_changes, self.plan.undo), (brief.ADVICE_CHANGE, brief.ADVICE_UNDO))
        self.assertIsNone(approvals.why_not_ask(self.case))

    def test_the_case_has_no_figure_of_its_own_as_no_change_has(self):
        self.assertIsNone(self.case.saving_usd_month)

    def test_a_finding_of_five_gateways_or_fewer_is_one_case_for_each_with_the_digest_of_one(self):
        resources, evidence = estate([12, 20, 5], peaks=[0, 0, 0])
        h = watch(resources, evidence, raw_of(3, proposal="change"))
        cases = sorted(h.store.cases_recent(), key=lambda case: case.resource_name)
        self.assertEqual([case.resource_name for case in cases], ["gw-01", "gw-02", "gw-03"])
        self.assertEqual([case.facts[gateways.KEY]["units"] for case in cases], [12, 20, 5])
        self.assertTrue(all(case.facts[gateways.KEY]["gateways"] == 1 and GROUP_FACT not in case.facts for case in cases))
        self.assertEqual(len(h.store.plans_open()), 3)

    def test_a_change_to_many_gateways_is_not_one_case_as_before_and_each_has_its_own_digest(self):
        resources, evidence = estate(UNITS)
        h = watch(resources, evidence, raw_of(7, proposal="change"))
        self.assertEqual(len(h.store.cases_recent()), 7)
        self.assertTrue(all(case.facts[gateways.KEY]["gateways"] == 1 for case in h.store.cases_recent()))

    def test_resources_of_other_kinds_get_no_digest_and_a_group_of_mixed_kinds_has_none(self):
        resources, evidence = estate(UNITS)
        resources[0] = resource(1, resource_type="microsoft.example/things", name="thing-01", resource_group="rg-01", cost_usd_30d=72.0)
        evidence["r1"] = record()
        case, _ = case_and_plan(watch(resources, evidence))
        self.assertEqual(case.facts[GROUP_FACT]["type"], "other")
        self.assertNotIn(gateways.KEY, case.facts)
        thing = resource(1, resource_type="microsoft.example/things")
        case, _ = case_and_plan(watch([thing], {"r1": record()}, raw_of(1, proposal="change")))
        self.assertNotIn(gateways.KEY, case.facts)

    def test_the_gateways_that_the_record_cannot_count_are_counted_as_such_and_the_figure_is_of_the_others(self):
        resources, evidence = estate(UNITS)
        del evidence["r2"]["properties"]
        evidence["r3"]["metrics"] = {}
        case, plan = case_and_plan(watch(resources, evidence, raw_of(7, basis="other")))
        digest = case.facts[gateways.KEY]
        self.assertEqual((digest["gateways"], digest["counted"], digest["units"], digest["target"]), (7, 5, 88, 5))
        self.assertEqual(plan.saving_usd_month, round(4 * 72.0 * 11 / 12 + 240.0 * 39 / 40, 2))


class WhatTheBriefSays(unittest.TestCase):
    def setUp(self):
        resources, evidence = estate(UNITS)
        self.case, self.plan = case_and_plan(watch(resources, evidence))
        self.b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)

    def test_what_these_gateways_are_what_was_found_and_what_would_change_are_in_plain_words(self):
        found = self.b.gateways
        self.assertTrue(found.what.startswith("A point-to-site gateway is the gateway that a virtual hub runs for its User VPN setting"))
        self.assertIn("Azure runs it inside the hub, which Microsoft manages, so what a person sets and sees is one number on the hub: its scale units.", found.what)
        self.assertIn("Azure charges for each unit by the hour whether anybody is connected or not", found.what)
        self.assertIn("easy to forget", found.what)
        self.assertEqual(found.sentence, "Nobody was connected to any of the 7 gateways in the days that Azure Monitor has a value for (at least 14 for each). "
                                         "They have 112 scale units together. The smallest size that still carries what each saw is 7 together, which is 105 fewer.")
        self.assertEqual((found.counted, found.gateways, found.fewer, found.note, found.caveat), (7, 7, 105, "", ""))

    def test_the_figure_is_a_scenario_with_its_basis_and_the_headline_counts_the_gateways(self):
        self.assertEqual(self.b.headline, "Look at 7 point-to-site gateways in 3 groups, the first is gw-07")
        self.assertEqual((self.b.saving.monthly, self.b.saving.level), (630.0, "Scenario"))
        self.assertEqual(self.b.saving.basis, "the cost of the gateways in the last 30 days, scaled by the share of their scale units that would be taken away (the price list was not read, so it is an estimate)")
        self.assertEqual((self.b.kind, self.b.family, self.b.cost), ("advice", ADVISE, 672.0))

    def test_the_rows_of_evidence_say_the_units_and_the_connections_before_the_examples(self):
        self.assertEqual([(fact.label, fact.value) for fact in self.b.facts],
                         [("Covers", "7 point-to-site gateways in 3 resource groups"), ("Together they cost", "$672.00 in the last 30 days"), ("Scale units", "112 in all, on 7 gateways"),
                          ("Most connections at one time", "0 in the last 14 days with a value"), ("Examples", "gw-07, gw-01, gw-02, gw-03, gw-04, gw-05 and 1 more")])
        self.assertEqual({fact.source for fact in self.b.facts[2:4]}, {brief.RESOURCE_GRAPH, brief.MONITOR})

    def test_the_choices_are_scale_down_with_the_exact_steps_or_keep_and_say_why(self):
        down, keep = self.b.options
        self.assertTrue(down.what.startswith("Scale the gateways down by 105 scale units in all, each to the smallest size that carries the most connections that it saw. "))
        for step in ("open the virtual hub, go to its Point to site page, set Gateway scale units to the smaller number and confirm",
                     "az network p2s-vpn-gateway update --name <gateway> --resource-group <resource group> --scale-unit <scale units>",
                     "plan for downtime when scale units change", "a hub update can take up to 30 minutes"):
            self.assertIn(step, down.what)
        self.assertIn("users who are connected may be disconnected while it changes", down.risk)
        self.assertTrue(keep.what.startswith("Keep the gateways as they are, and say why in your answer"))
        self.assertEqual(keep.risk, "the scale units keep billing by the hour, used or not.")
        self.assertEqual(self.b.change, brief.ADVICE_CHANGE)

    def test_a_case_with_no_request_has_the_figure_and_the_rows_and_no_choices(self):
        b = brief.build_brief(self.case, None, now=WEB_NOW)
        self.assertEqual((b.kind, b.saving.monthly, b.saving.level, b.options), ("info", 630.0, "Scenario", ()))
        self.assertIsNotNone(b.gateways)

    def test_one_gateway_with_connections_says_the_most_and_what_its_units_carry(self):
        resources, evidence = estate([12], peaks=[700], per_unit=10.0)
        case, plan = case_and_plan(watch(resources, evidence, raw_of(1, basis="low-usage", proposal="change", cited=700 * 14)))
        b = brief.build_brief(case, plan, now=WEB_NOW)
        self.assertEqual(b.gateways.sentence, "The most connections at one time on the gateway was 700 in the 14 days that Azure Monitor has a value for. "
                                              "It has 12 scale units, which carry up to 10,000 connections at one time. The smallest size that still carries what it saw is 4, which is 8 fewer.")
        self.assertEqual((b.saving.monthly, b.headline), (80.0, "Consider changing the point-to-site gateway gw-01 in group rg-01"))
        self.assertEqual([(fact.label, fact.value) for fact in b.facts[:3]],
                         [("Cost, last 30 days", "$120.00"), ("Scale units", "12 in all"), ("Most connections at one time", "700 in the last 14 days with a value")])

    def test_some_gateways_with_connections_say_how_many_had_none(self):
        resources, evidence = estate(UNITS, peaks=[0, 0, 0, 40, 0, 0, 0])
        case, plan = case_and_plan(watch(resources, evidence, raw_of(7, basis="low-usage", cited=0)))
        found = brief.build_brief(case, plan, now=WEB_NOW).gateways
        self.assertTrue(found.sentence.startswith("The most connections at one time on any of the 7 gateways was 40 in the days that Azure Monitor has a value for (at least 14 for each). "
                                                  "Nobody was connected to 6 of them. "), found.sentence)

    def test_gateways_that_are_at_the_smallest_size_already_have_one_choice_and_no_figure(self):
        resources, evidence = estate([1] * 7)
        case, plan = case_and_plan(watch(resources, evidence))
        b = brief.build_brief(case, plan, now=WEB_NOW)
        self.assertEqual(b.gateways.fewer, 0)
        self.assertIn("Each is at the smallest size that carries what it saw already.", b.gateways.sentence)
        self.assertEqual(len(b.options), 1)
        self.assertTrue(b.options[0].what.startswith("Leave the gateways as they are"))
        self.assertIsNone(b.saving.monthly)


class WhenTheRecordIsNotEnough(unittest.TestCase):
    def test_gateways_that_cannot_be_counted_say_so_and_no_figure_is_made(self):
        resources, evidence = estate(UNITS)
        for block in evidence.values():
            del block["properties"]
        case, plan = case_and_plan(watch(resources, evidence))
        b = brief.build_brief(case, plan, now=WEB_NOW)
        self.assertEqual((b.gateways.counted, b.gateways.gateways), (0, 7))
        self.assertEqual(b.gateways.sentence, "Meternaut could not say how many scale units these gateways have or whether anybody connected, because the tools did not record both.")
        self.assertEqual(b.gateways.caveat, "Not counted: 7 gateways.")
        self.assertIsNone(b.saving.monthly)
        self.assertTrue(b.saving.specific)
        self.assertEqual(b.saving.why_none, "The scale units or the connections of these gateways were not recorded, so no figure can be worked out for scaling them down.")
        self.assertTrue(b.options[0].what.startswith("Look at the connections of the gateways first. In the Azure portal, open Monitor, then Metrics, choose the gateway and the metric P2S Connection Count"))
        self.assertIn("az network p2s-vpn-gateway list shows the gateways and their scale units", b.options[0].what)
        self.assertEqual([fact.label for fact in b.facts][:2], ["Covers", "Together they cost"])
        self.assertNotIn("Scale units", [fact.label for fact in b.facts])

    def test_gateways_that_were_not_all_counted_say_how_many_and_the_figure_is_of_the_others(self):
        resources, evidence = estate(UNITS)
        del evidence["r1"]["properties"]
        del evidence["r2"]["metrics"]
        case, plan = case_and_plan(watch(resources, evidence, raw_of(7, basis="other")))
        found = brief.build_brief(case, plan, now=WEB_NOW).gateways
        self.assertEqual(found.note, "2 gateways of the 7 are not counted: the tools did not record the scale units or the connections.")
        self.assertEqual(found.caveat, "Not counted: 2 of 7 gateways.")
        self.assertIn("any of the 5 gateways", found.sentence)

    def test_a_digest_that_is_not_as_it_should_be_shows_nothing_and_never_something_else(self):
        resources, evidence = estate(UNITS)
        case, plan = case_and_plan(watch(resources, evidence))
        good = dict(case.facts[gateways.KEY])
        for label, changes in (("more counted than there are", {"counted": 8}), ("no gateway", {"gateways": 0}), ("a flag for a count", {"counted": True}), ("a text", {"units": "112"}),
                               ("a target above the units", {"target": 113}), ("a target below the gateways", {"target": 1}), ("a negative peak", {"peak": -1}), ("no days", {"days": 0}),
                               ("more nobody than gateways", {"quiet": 8}), ("too many gateways", {"gateways": 10 ** 6, "counted": 7})):
            with self.subTest(label):
                broken = replace(case, facts={**case.facts, gateways.KEY: {**good, **changes}})
                self.assertIsNone(brief.gateways_of(broken))
                self.assertEqual(brief.build_brief(broken, plan, now=WEB_NOW).gateways, None)
        self.assertIsNone(brief.gateways_of(replace(case, facts={**case.facts, gateways.KEY: "x"})))
        self.assertIsNone(brief.gateways_of(None))
        self.assertIsNone(brief.gateways_saving(replace(case, facts={**case.facts, gateways.KEY: {**good, "savingUsd": 10 ** 6}})), "a figure above the cost of the resources is not believed")
        self.assertIsNone(brief.gateways_saving(replace(case, facts={**case.facts, gateways.KEY: {**good, "savingUsd": -1.0}})))


class WhatAPersonSees(unittest.TestCase):
    def setUp(self):
        resources, evidence = estate(UNITS)
        self.case, self.plan = case_and_plan(watch(resources, evidence))
        self.reply, self.text = page_of(self.case, self.plan)
        self.b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)

    def test_the_page_has_the_figure_the_rows_what_the_gateways_are_what_was_found_and_the_choices_in_this_order(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), [figures.title_of(self.b)[1]])
        self.assertEqual(figures.title_of(self.b)[1], "7 point-to-site gateways in 3 resource groups")
        self.assertEqual(self.reply.headings(2), ["If you answer", "What was measured", "What you could do", "Why the AIs think so", "Whose is it", "Your answer"])
        self.assertIn("The gateways", self.reply.headings(3))
        order = [self.text.index(part) for part in ("Saves, Scenario. $630.00 a month.", "112 in all, on 7 gateways", "A point-to-site gateway is the gateway that a virtual hub runs",
                                                    "Nobody was connected to any of the 7 gateways", "What you could do", "Keep the gateways as they are")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(self.reply.problems, [])

    def test_the_choices_are_a_list_with_what_each_puts_at_risk_and_the_page_asks_nothing(self):
        (choices,) = self.reply.main.find_all("ol")
        parts = [li.text() for li in choices.find_all("li")]
        self.assertEqual(len(parts), 2)
        for part in parts:
            self.assertEqual(part.count("At risk:"), 1, part)
        self.assertIn("az network p2s-vpn-gateway update --name <gateway>", parts[0])
        self.assertNotIn("?", self.text)
        self.assertTrue(self.text[self.text.index("What you could do"):].split("Why the AIs think so")[0].rstrip().endswith("Nothing changes in Azure when you answer."))

    def test_the_words_of_money_on_the_page_are_those_of_the_style_guide(self):
        content = self.reply.content
        self.assertNotRegex(content, r"\b(?:saved|savings|save)\b")
        self.assertEqual(re.findall(r"\bSaves\b[^.]*", content), ["Saves, Scenario"])
        self.assertNotRegex(content, r"[\u20ac\u00a3]|\bEUR\b|\bUSD\b")

    def test_the_decision_letter_says_what_was_found_and_the_choices_in_a_line_and_stays_within_the_words_of_a_letter(self):
        letter = letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS)
        text = letter.text
        self.assertEqual(text.splitlines()[0], figures.title_of(self.b)[1], "the title of the page")
        self.assertIn("$7,560 a year\nSaves, Scenario. $630.00 a month.", text)
        self.assertIn("Nobody was connected to any of the 7 gateways in the days that Azure Monitor has a value for (at least 14 for each).", text)
        self.assertIn(brief.GATEWAYS_SHORT, text)
        self.assertIn("If you answer: Nothing changes in Azure. Your answer is recorded with your name.", text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["approval"])
        self.assertTrue(text.isascii())
        self.assertEqual(len(re.findall(r'href="', letter.html)), 1)
        for gone in ("?", "!", "saved", "\u2013", "\u2014"):
            self.assertNotIn(gone, text.lower())

    def test_the_card_has_the_sentence_and_the_choices_in_one_line_and_passes_the_check_of_cards(self):
        card = cards.decision_card(self.b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24))
        texts = {block["id"]: block["text"] for block in walk_blocks(card)}
        self.assertTrue(texts["gateways"].startswith("**Gateways.** Nobody was connected to any of the 7 gateways"))
        self.assertEqual(texts["options"], brief.GATEWAYS_SHORT)
        self.assertEqual((texts["value"], texts["saving-word"]), ("$7,560 a year", "Saves, Scenario. $630.00 a month."))
        self.assertNotIn("gateways-caveat", texts)

    def test_what_could_not_be_counted_is_in_a_few_words_on_the_letter_and_the_card_and_in_a_sentence_on_the_page(self):
        resources, evidence = estate(UNITS)
        del evidence["r1"]["properties"]
        case, plan = case_and_plan(watch(resources, evidence))
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertIn("Not counted: 1 of 7 gateways.", letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS).text)
        texts = {block["id"]: block["text"] for block in walk_blocks(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}", nonce="n" * 24)))}
        self.assertEqual(texts["gateways-caveat"], "Not counted: 1 of 7 gateways.")
        self.assertIn("1 gateway of the 7 is not counted: the tools did not record the scale units or the connections.", page_of(case, plan)[1])


class WhatAnEstateCannotDo(unittest.TestCase):
    def test_a_name_that_is_text_from_the_estate_never_reaches_the_digest_or_the_words_of_code(self):
        resources, evidence = estate(UNITS)
        resources = [replace(item, name=HOSTILE if n == 7 else item.name, resource_group=HOSTILE if n == 6 else item.resource_group) for n, item in enumerate(resources, 1)]
        case, plan = case_and_plan(watch(resources, evidence))
        digest = case.facts[gateways.KEY]
        self.assertTrue(all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in digest.values()), "numbers only")
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        said = " ".join([b.gateways.what, b.gateways.sentence, b.gateways.note, b.gateways.caveat, *(f"{option.what} {option.risk}" for option in b.options)])
        for text in ("script", "evil", "gw-07", "gw-06"):
            self.assertNotIn(text, said)
        letter = letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS)
        self.assertNotIn("<script>", letter.html)
        self.assertNotIn("](", letter.text)

    def test_the_digest_is_worked_out_from_what_the_tools_recorded_and_not_from_what_the_agent_cited(self):
        resources, evidence = estate(UNITS)
        case, _ = case_and_plan(watch(resources, evidence, raw_of(7, cited=0)))
        quiet = case.facts[gateways.KEY]
        resources, evidence = estate(UNITS, peaks=[0, 0, 0, 0, 0, 0, 900])
        case, _ = case_and_plan(watch(resources, evidence, raw_of(7, basis="other", cited=0)))
        self.assertEqual((quiet["peak"], case.facts[gateways.KEY]["peak"]), (0, 900), "the agent cited nothing about the connections of the last, and the digest has them all the same")


if __name__ == "__main__":
    unittest.main()
