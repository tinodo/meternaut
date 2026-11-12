"""A whole Watch about a subscription, the words of Azure Advisor, and what a page, a card and a letter say about them.

A fake of Azure (tests/support.py) stands in for it, with Cost Management by service, by day and the read of a subscription. Everything in it is INVENTED: the names, the services, the
amounts, the ids. (A disk that Azure has no cost line for is in test_no_cost_line.py, and a finding that says nothing in test_held_back.py.)
"""
import datetime as dt
import json
import re
import unittest

from support import NOW, RG, SUBSCRIPTION, FakeEstate
from test_run_loop import OID, Moving, loop_for, watch
from test_web_support import NOW as WEB_NOW
from test_web_support import Console, make_advice, make_case

from cases import cards, detectors, letters
from cases.brief import build_brief
from cases.costs import analysis_url
from cases.people import Person
from cases.web import figures

DEV = "contoso-dev"
LAST = dt.date(2026, 11, 3)  # the last closed day of a Watch at support.NOW
BASE = "https://meternaut.example"
PROBLEM = "The subscription has no budget that warns somebody"
SOLUTION = "Create a budget with an alert for this subscription"


def advisor_item(**changes) -> dict:
    """An Azure Advisor cost recommendation whose impacted resource is the subscription itself: Advisor puts the id of the subscription in impactedValue."""
    properties = {"category": "Cost", "impact": "Medium", "impactedField": "Microsoft.Subscriptions/subscriptions", "impactedValue": SUBSCRIPTION,
                  "recommendationTypeId": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "shortDescription": {"problem": PROBLEM, "solution": SOLUTION},
                  "resourceMetadata": {"resourceId": f"/subscriptions/{SUBSCRIPTION}"}}
    properties.update(changes)
    return {"id": f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations/r1", "name": "r1", "properties": properties}


def a_subscription_with_a_bill() -> FakeEstate:
    """A subscription that Cost Management shows a bill for: three services in two groups, and a plan of Microsoft Defender for Cloud that has no resource and no group."""
    estate = FakeEstate()
    estate.advisor = [advisor_item()]
    estate.subscription_name = DEV
    estate.scope_rows = [(88.10, "Virtual Network", "rg-net"), (41.25, "Microsoft Defender for Cloud", ""), (19.60, "Azure Cognitive Search", "rg-app")]
    estate.scope_days = [(LAST - dt.timedelta(days=n), 4.0 + n, "rg-net") for n in range(0, 10)] + [(LAST, 1.5, "")]
    return estate


def the_case(extras, detector: str):
    (case,) = [c for c in extras.store.cases_recent() if c.detector == detector]
    return case


class TheFindingAboutASubscription(unittest.TestCase):
    """The request that read "Review the resource <id>" with a flat line at zero: the id of the subscription, the plan of Defender that has no group, and an Advisor recommendation."""

    @classmethod
    def setUpClass(cls):
        cls.clock = Moving()
        cls.extras = loop_for(cls.clock)
        cls.estate = a_subscription_with_a_bill()
        cls.summary, cls.events, _ = watch(cls.estate, cls.extras, cls.clock)
        cls.case = the_case(cls.extras, "advisor-cost")
        (cls.plan,) = cls.extras.store.plans_open()
        cls.brief = build_brief(cls.case, cls.plan, now=NOW, may_answer=True)

    def test_the_name_of_the_subscription_is_read_once_and_kept_and_it_is_the_name_of_the_finding(self):
        reads = [c for c in self.estate.calls if c["method"] == "GET" and c["path"] == f"/subscriptions/{SUBSCRIPTION}"]
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["url"], f"https://management.azure.com/subscriptions/{SUBSCRIPTION}?api-version=2022-12-01")
        self.assertEqual((self.case.subscription_name, self.case.resource_name), (DEV, DEV))
        self.assertNotIn(SUBSCRIPTION, self.case.resource_name)

    def test_the_cost_is_every_line_of_the_subscription_also_the_plan_that_has_no_group_and_it_is_made_of_its_services(self):
        self.assertEqual((self.case.cost_state, self.case.cost_usd_30d), ("lines", 148.95))
        self.assertEqual(self.case.cost_by_service, {"services": [["Virtual Network", 88.1], ["Microsoft Defender for Cloud", 41.25], ["Azure Cognitive Search", 19.6]], "more": 0, "moreUsd": 0.0})
        queries = [c["body"] for c in self.estate.calls if "costmanagement" in c["path"].lower() and c["body"]["dataset"]["granularity"] == "None"]
        by_service = [q for q in queries if [g["name"] for g in q["dataset"].get("grouping", [])] == ["ServiceName"]]
        self.assertEqual(len(by_service), 1, "one query by service for the subscription, however many findings it has")
        self.assertNotIn("filter", by_service[0]["dataset"])

    def test_the_title_and_what_to_look_at_are_advisors_own_words_and_never_the_id(self):
        self.assertEqual(self.case.advice, {"problem": PROBLEM, "solution": SOLUTION})
        self.assertEqual(self.brief.headline, f"{PROBLEM}: subscription {DEV}")
        look = next(fact for fact in self.brief.facts if fact.label == "What to look at")
        self.assertEqual((look.value, look.source, self.brief.facts[0]), (SOLUTION, "Azure Advisor", look))
        for text in (self.brief.headline, self.brief.where.name, self.plan.title, *(fact.value for fact in self.brief.facts)):
            self.assertNotIn(SUBSCRIPTION, text)
            self.assertNotIn("Review the resource", text)

    def test_the_daily_cost_is_the_sum_of_every_line_of_each_day_and_is_read_for_the_whole_subscription(self):
        self.assertEqual((self.case.cost_series_end, len(self.case.cost_series)), (LAST.isoformat(), 30))
        self.assertEqual((self.case.cost_series[29], self.case.cost_series[28], self.case.cost_series[20]), (5.5, 5.0, 13.0))
        self.assertEqual(round(sum(self.case.cost_series), 2), 4.0 * 10 + 45 + 1.5)
        days = [c["body"] for c in self.estate.calls if "costmanagement" in c["path"].lower() and c["body"]["dataset"]["granularity"] == "Daily"]
        self.assertEqual(len(days), 1)
        self.assertEqual(("grouping" in days[0]["dataset"], "filter" in days[0]["dataset"]), (False, False))

    def test_the_figure_is_the_whole_bill_and_says_so_and_says_what_it_is_made_of_and_no_total_counts_it(self):
        figure = figures.figure_for([self.brief], [figures.cost_of(self.brief, self.case)])
        self.assertEqual((figure.state, figure.label, figure.monthly, figure.whole), ("cost", "Costs, saving not measured", 148.95, True))
        self.assertEqual(figure.note, "All the cost lines of the subscription in the last 30 days. What a change would save was not worked out.")
        self.assertEqual(figure.made_of, "Made of: Virtual Network $88.10, Microsoft Defender for Cloud $41.25 and Azure Cognitive Search $19.60.")
        self.assertFalse(figure.counts)

    def test_the_page_shows_the_name_the_bill_by_service_a_real_chart_and_the_link_to_cost_analysis(self):
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(self.plan)
        reply = console.get(f"/ok/{self.plan.plan_id}")
        self.assertEqual(reply.status, 200)
        card = reply.main.find("section", class_="focus")
        lines = [p.text() for p in card.find_all("p") if "figsub" in p.classes()]
        self.assertEqual(lines[0], "Costs, saving not measured. $148.95 a month. All the cost lines of the subscription in the last 30 days. What a change would save was not worked out.")
        self.assertEqual(lines[1], "Made of: Virtual Network $88.10, Microsoft Defender for Cloud $41.25 and Azure Cognitive Search $19.60.")
        link = next(a for a in card.find_all("a") if a.text() == "Open in Cost analysis")
        self.assertEqual((link.attrs["href"], link.attrs["rel"]), (analysis_url(SUBSCRIPTION), "noopener"))
        self.assertIn(f"for subscription {DEV}", card.text())
        (chart,) = [n for n in card.find_all("figure") if "chart" in n.classes()]
        self.assertEqual(len(chart.find_all("path")), 2, "a line and its tint: the daily cost of every line of the subscription")
        self.assertNotIn("Review the resource", reply.content)
        self.assertEqual(reply.headings(1), [f"{PROBLEM}: subscription {DEV}"])
        self.assertIn(f"Subscription {DEV}.", reply.main.text())
        outside = reply.main.text().replace(reply.main.find("details").text(), "")
        self.assertNotIn(SUBSCRIPTION, outside, "the id of the subscription is in the details and nowhere else")

    def test_the_decisions_page_does_not_count_the_bill_of_a_whole_subscription_as_money_that_a_change_could_save(self):
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(self.plan)
        reply = console.get("/")
        text = reply.main.text()
        self.assertIn("Nothing is under review.", text, "the bill is not what a change could save, so it is no cost under review")
        self.assertIn("No saving is known yet.", text)
        (row,) = [li for ol in reply.main.find_all("ol", class_="items") for li in ol.children if hasattr(li, "tag")]
        self.assertIn("$148.95 a month", row.text())
        self.assertIsNone(row.find("svg", class_="bar"), "no bar compares it with what a change could save")
        self.assertNotIn("under review.", reply.main.find("div", class_="head").text())

    def test_a_letter_and_a_card_say_the_name_the_bill_and_what_it_is_made_of_and_hold_one_link_each(self):
        person = Person(OID, "Tino", ("owner", "approver"), "tino@example.com")
        letter = letters.approval_letter(self.plan, self.case, person, BASE, NOW, ())
        card = cards.decision_card(self.brief, cards.CardContext(page_url=f"{BASE}/ok/{self.plan.plan_id}"))
        card_text = " ".join(node["text"] for node in _walk(card) if isinstance(node.get("text"), str))
        for text in (letter.text, card_text):
            self.assertIn(f"subscription {DEV}", text)
            self.assertIn("Made of: Virtual Network $88.10, Microsoft Defender for Cloud $41.25 and Azure Cognitive Search $19.60.", text)
            self.assertNotIn(SUBSCRIPTION, text)
            self.assertNotIn("Review the resource", text)
            self.assertNotIn("cost-analysis", text.lower())
        self.assertEqual(len(re.findall(r'href="([^"]*)"', letter.html)), 1, "a letter has one link: the page of the request")

    def test_the_run_says_nothing_was_held_back(self):
        record = self.extras.store.runs_recent()[0]
        self.assertEqual(record.held, 0)
        self.assertEqual([e for e in self.events if e["type"] == "case.held"], [])


class AdvisorsOwnWords(unittest.TestCase):
    """The title and what to look at are what Azure Advisor wrote (properties.shortDescription: a problem and a solution), whatever the recommendation is about, never "Review the resource <id>"."""

    def words(self, short):
        return detectors.advisor_words({"shortDescription": short})

    def test_both_sentences_are_kept_one_line_each_and_one_stands_for_the_other_when_advisor_gave_only_one(self):
        self.assertEqual(self.words({"problem": "Buy a\n reservation", "solution": "Reserve\tthe machines"}), {"problem": "Buy a reservation", "solution": "Reserve the machines"})
        self.assertEqual(self.words({"problem": "Buy a reservation"}), {"problem": "Buy a reservation", "solution": "Buy a reservation"})
        self.assertEqual(self.words({"solution": "Reserve the machines"}), {"problem": "Reserve the machines", "solution": "Reserve the machines"})

    def test_no_words_are_none_and_so_is_anything_that_is_not_text(self):
        for short in ({}, {"problem": "", "solution": "  "}, {"problem": 5, "solution": None}, "text", None, ["a"]):
            with self.subTest(short=short):
                self.assertEqual(self.words(short), {})

    def test_the_words_are_cut_where_a_title_and_a_line_can_hold_them_and_a_link_in_them_is_removed(self):
        found = self.words({"problem": "p" * 400, "solution": "s" * 600})
        self.assertEqual((len(found["problem"]), len(found["solution"])), (detectors.ADVICE_PROBLEM, detectors.ADVICE_SOLUTION))
        link = self.words({"problem": "See https://evil.example now", "solution": "Go to https://evil.example/x"})
        self.assertNotIn("evil.example", json.dumps(link))

    def lead(self, **properties):
        return detectors.advisor_lead(advisor_item(**properties), SUBSCRIPTION)

    def brief_of(self, lead, **changes):
        case = make_case(case_id="kadv00001", resource_id=lead.resource_id, resource_name=lead.name, resource_type=lead.resource_type, resource_group=lead.resource_group,
                         subscription_id=SUBSCRIPTION, detector="advisor-cost", advice=lead.advice, status="needs_human", recommendation="change", saving_usd_month=0.0,
                         cost_usd_30d=0.0, **changes)
        plan = make_advice(plan_id="padv00001", case_id=case.case_id, resource_id=lead.resource_id, resource_name=lead.name, resource_group=lead.resource_group,
                           subscription_id=SUBSCRIPTION, title="")
        return build_brief(case, plan, now=WEB_NOW, may_answer=True)

    def test_a_recommendation_about_a_resource_is_titled_with_the_problem_the_name_and_the_group_and_says_what_to_look_at(self):
        lead = self.lead(impactedField="Microsoft.Compute/disks", impactedValue="idle-disk", resourceMetadata={"resourceId": f"{RG}/rg-app/providers/Microsoft.Compute/disks/idle-disk"})
        self.assertEqual((lead.name, lead.resource_group, lead.resource_type, lead.advice), ("idle-disk", "rg-app", "microsoft.compute/disks", {"problem": PROBLEM, "solution": SOLUTION}))
        brief = self.brief_of(lead)
        self.assertEqual(brief.headline, f"{PROBLEM}: idle-disk in group rg-app")
        self.assertEqual(next(f.value for f in brief.facts if f.label == "What to look at"), SOLUTION)

    def test_a_recommendation_about_a_resource_group_names_the_group_and_one_about_a_resource_that_has_only_an_id_names_the_group_only(self):
        group = self.lead(impactedField="Microsoft.Resources/resourceGroups", impactedValue="rg-demo", resourceMetadata={"resourceId": f"{RG}/rg-demo"})
        self.assertEqual(self.brief_of(group).headline, f"{PROBLEM}: resource group rg-demo")
        only_an_id = self.lead(impactedField="Microsoft.Foo/bars", impactedValue="aaaaaaaa-1111-4222-8333-444444444444",
                               resourceMetadata={"resourceId": f"{RG}/rg-app/providers/Microsoft.Foo/bars/aaaaaaaa-1111-4222-8333-444444444444"})
        self.assertEqual(self.brief_of(only_an_id).headline, f"{PROBLEM} in group rg-app")

    def test_a_recommendation_about_a_subscription_with_a_name_that_was_not_read_names_the_start_of_its_id(self):
        lead = self.lead()
        lead.name = SUBSCRIPTION  # the id that Advisor gives in impactedValue: no display name was read
        brief = self.brief_of(lead)
        self.assertEqual(brief.headline, f"{PROBLEM}: subscription {SUBSCRIPTION[:8]}")
        self.assertNotIn(SUBSCRIPTION, brief.headline)

    def test_a_recommendation_without_words_is_titled_by_what_it_is_about_and_not_by_the_words_review_the_resource(self):
        lead = self.lead(shortDescription={}, impactedField="Microsoft.Compute/disks", impactedValue="idle-disk",
                         resourceMetadata={"resourceId": f"{RG}/rg-app/providers/Microsoft.Compute/disks/idle-disk"})
        self.assertEqual(lead.advice, {})
        brief = self.brief_of(lead)
        self.assertNotIn("Review the resource", brief.headline)
        self.assertIn("idle-disk", brief.headline)


class TheRun(unittest.TestCase):
    """What the Watch says once more about a finding that was taken up."""

    def test_the_run_says_nothing_was_held_back(self):
        clock = Moving()
        extras = loop_for(clock)
        summary, events, _ = watch(a_subscription_with_a_bill(), extras, clock)
        self.assertEqual((summary.held, extras.store.runs_recent()[0].held), (0, 0))
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])
        self.assertEqual(events[-1]["heldBack"], 0)


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


if __name__ == "__main__":
    unittest.main()
