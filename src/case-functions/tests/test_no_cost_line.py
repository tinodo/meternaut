"""A disk that Azure has no cost line for, and a read of cost that Azure turns away: what the app keeps and what every page, card and letter then says.

No page, card or letter may show a flat zero as if it were measured. An estimate at list price stands beside the words that say that Azure has no line, is labelled as an estimate, and is never
a cost: it is in no total, no order and no check after a change. A fake of Azure (tests/support.py) answers; everything in it is invented.
"""
import datetime as dt
import json
import re
import unittest

from support import NOW, RG, FakeEstate, disk_row
from test_run_loop import OID, Moving, loop_for, watch
from test_web_support import Console

from cases import cards, estimate, learning, letters
from cases.arm import COST_RETRIES
from cases.brief import build_brief
from cases.costs import FAILED_WORDS, NO_LINE_WORDS
from cases.families.base import per_day_check
from cases.people import Person
from cases.web import figures

BASE = "https://meternaut.example"
ESTIMATE = "Estimate at list price, not Azure's bill: about $1.54 a month for a disk of this type and size (tier S4). East US list prices of 12 November 2026."
ZERO = re.compile(r"\$\s?0(?:\.0+)?(?![\d.,])")  # "$0", "$0.00" and "$ 0": a zero as money
VM = f"{RG}/rg-app/providers/microsoft.compute/virtualmachines/some-vm"


def an_idle_disk(name: str = "idle-disk-4gb") -> dict:
    """An unattached 4 GB Standard HDD that nobody planted, in the group where Meternaut may make a change but without the tag of planted waste: it is a matter for advice."""
    return disk_row(name, "rg-meternaut", skuName="Standard_LRS", sizeGb=4, timeCreated="2026-10-01T10:00:00.0000000+00:00")


def an_estate(disks=1) -> FakeEstate:
    """An estate whose Cost Management has a line for another resource and none for the disks: the subscription has a bill, and the disks are not in it (as the owner saw)."""
    estate = FakeEstate()
    estate.graph["orphan-managed-disk"] = [an_idle_disk(f"idle-disk-{n}") for n in range(disks)]
    estate.cost_rows = [(12.5, VM)]
    return estate


def card_text(card) -> str:
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("text"), str):
                found.append(node["text"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(card)
    return " ".join(found)


class TheDiskThatAzureHasNoLineFor(unittest.TestCase):
    """The request "Delete the unattached disk ...": Azure's cost lines have the machine and nothing for the three disks, so the 0 meant "Azure has no line", not a delay."""

    @classmethod
    def setUpClass(cls):
        cls.clock = Moving()
        cls.extras = loop_for(cls.clock)
        cls.estate = an_estate()
        cls.summary, cls.events, _ = watch(cls.estate, cls.extras, cls.clock)
        (cls.case,) = cls.extras.store.cases_recent()
        (cls.plan,) = cls.extras.store.plans_open()
        cls.brief = build_brief(cls.case, cls.plan, now=NOW, may_answer=True)

    def test_the_case_keeps_that_azure_has_no_line_and_the_estimate_in_a_record_of_its_own(self):
        case = self.case
        self.assertEqual((case.cost_state, case.cost_usd_30d, case.cost_series), ("none", 0.0, None))
        self.assertEqual(case.estimate, {"usdMonth": 1.54, "tier": "S4", "table": "2026-11-12"})
        self.assertEqual((case.saving_usd_month or 0.0, self.plan.saving_usd_month or 0.0), (0.0, 0.0), "no saving is worked out from an estimate")

    def test_the_cost_lines_were_asked_for_by_resource_and_by_day_and_neither_has_the_disk(self):
        queries = [c["body"] for c in self.estate.calls if "costmanagement" in c["path"].lower()]
        self.assertEqual(sorted(q["dataset"]["granularity"] for q in queries), ["Daily", "None"])
        daily = next(q for q in queries if q["dataset"]["granularity"] == "Daily")
        self.assertEqual(daily["dataset"]["filter"]["dimensions"]["values"], [an_idle_disk("idle-disk-0")["id"].lower()])

    def test_the_brief_says_that_azure_has_no_line_and_keeps_the_estimate_apart_from_every_cost_and_saving(self):
        brief = self.brief
        self.assertEqual((brief.cost_state, brief.saving.monthly, brief.saving.why_none), ("none", None, NO_LINE_WORDS))
        self.assertEqual(brief.estimate, estimate.Estimate(1.54, "S4", "2026-11-12"))
        cost = next(fact for fact in brief.facts if fact.label == "Cost, last 30 days")
        self.assertEqual(cost.value, "Azure has no cost line for this yet")
        self.assertNotEqual(brief.cost, 1.54)
        self.assertEqual(figures.figure_for([brief], [figures.cost_of(brief, self.case)]).monthly, None)

    def test_the_figure_is_none_with_the_reason_and_the_estimate_and_it_counts_for_no_total(self):
        figure = figures.figure_for([self.brief], [figures.cost_of(self.brief, self.case)])
        self.assertEqual((figure.state, figure.label, figure.monthly, figure.read, figure.note), ("none", "Cost not visible", None, "none", NO_LINE_WORDS))
        self.assertEqual(figure.estimate, estimate.Estimate(1.54, "S4", "2026-11-12"))
        self.assertEqual(str(figures.under(figure)), f'<p class="figsub">{ESTIMATE.replace(chr(39), "&#x27;")}</p>')
        self.assertEqual(figures.series_reason(self.brief, self.case), figures.NONE_REASON)

    def test_the_page_says_that_azure_has_no_line_draws_no_line_and_labels_the_estimate(self):
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(self.plan)
        reply = console.get(f"/ok/{self.plan.plan_id}")
        self.assertEqual(reply.status, 200)
        card = reply.main.find("section", class_="focus")
        text = card.text()
        self.assertIn(NO_LINE_WORDS, text)
        self.assertIn(ESTIMATE, text)
        self.assertEqual(text.count("Estimate at list price, not Azure's bill"), 1, "said once")
        (chart,) = [n for n in card.find_all("figure") if "chart" in n.classes()]
        self.assertEqual(chart.find_all("path"), [], "no line is drawn: a line along the floor would read as a cost of nothing")
        self.assertIn(figures.NONE_REASON, chart.text())
        self.assertNotRegex(reply.main.text(), ZERO)
        self.assertNotIn("Review the resource", reply.content)

    def test_the_decisions_page_has_no_figure_for_it_and_no_money_that_an_estimate_could_be_taken_for(self):
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(self.plan)
        reply = console.get("/")
        text = reply.main.text()
        self.assertIn(NO_LINE_WORDS, text)
        self.assertNotRegex(text, ZERO)
        self.assertIn("Nothing is under review.", text, "an estimate is not a cost under review")
        self.assertIn("No saving is known yet.", text)
        self.assertEqual(re.findall(r"\$[\d,]+(?:\.\d\d)?", text), [], "no money at all: the list holds only what Cost Management or a check has measured")

    def test_a_letter_and_a_card_say_it_in_the_same_words_and_print_no_zero(self):
        person = Person(OID, "Tino", ("owner", "approver"), "tino@example.com")
        letter = letters.approval_letter(self.plan, self.case, person, BASE, NOW, ())
        card = cards.decision_card(self.brief, cards.CardContext(page_url=f"{BASE}/ok/{self.plan.plan_id}"))
        for text in (letter.text, card_text(card).replace("\\", "")):  # a card is markdown: its brackets carry a backslash
            self.assertIn(NO_LINE_WORDS, text)
            self.assertIn(ESTIMATE, text)
            self.assertNotRegex(text, ZERO)
        self.assertNotRegex(letter.html, ZERO)

    def test_the_estimate_is_in_no_measured_figure_no_total_and_nothing_that_is_learned_or_verified(self):
        record = json.loads(self.case.to_json())
        holders = [key for key, value in record.items() if "1.54" in json.dumps(value)]
        self.assertEqual(holders, ["estimate"], "the estimate is kept in one field, and in no figure")
        learned = json.dumps(learning.signals_of(self.case))
        self.assertNotIn("1.5", learned)
        self.assertNotIn("estimate", learned.lower())
        confirmed, note, saved = per_day_check(self.case.cost_usd_30d, 0.5, 2, "the disk")
        self.assertEqual((confirmed, saved), (False, None), "no saving is confirmed against an estimate: the cost lines before the change are none")
        self.assertIn("no cost lines from before the change", note)

    def test_a_second_watch_leaves_the_case_as_it_is(self):
        before = self.extras.store.cases_recent()
        self.clock.advance(hours=3)
        _, events, _ = watch(an_estate(), self.extras, self.clock)
        (after,) = self.extras.store.cases_recent()
        self.assertEqual((after.cost_state, after.cost_usd_30d, after.estimate, after.cost_series), ("none", 0.0, before[0].estimate, None))
        self.assertEqual([e for e in events if e["type"] == "case.held"], [])


class WhenAFindingHasLinesTheEstimateIsNotThere(unittest.TestCase):
    """A disk that Cost Management has a line for shows the line and never an estimate beside it."""

    def test_a_disk_with_a_cost_line_has_the_figure_and_no_estimate_and_a_disk_of_another_kind_has_none(self):
        clock = Moving()
        extras = loop_for(clock)
        estate = an_estate()
        estate.cost_rows.append((1.25, an_idle_disk("idle-disk-0")["id"].lower()))
        estate.days = [(dt.date(2026, 11, 3), an_idle_disk("idle-disk-0")["id"], 0.5), (dt.date(2026, 11, 2), an_idle_disk("idle-disk-0")["id"], 0.75)]
        watch(estate, extras, clock)
        (case,) = extras.store.cases_recent()
        self.assertEqual((case.cost_state, case.cost_usd_30d, case.estimate), ("lines", 1.25, {}))
        (plan,) = extras.store.plans_open()
        brief = build_brief(case, plan, now=NOW, may_answer=True)
        self.assertIsNone(brief.estimate)
        console = Console()
        console.store.case_put(case)
        console.store.plan_put(plan)
        text = console.get(f"/ok/{plan.plan_id}").main.text()
        self.assertNotIn("Estimate at list price", text)
        self.assertIn("$1.25", text)


class WhenCostManagementKeepsSayingTooManyRequests(unittest.TestCase):
    """Cost Management's query API limits its callers (HTTP 429 "Too many requests"). The app waits as the answer says, a few times, and then says that the cost could not be read just now."""

    @classmethod
    def setUpClass(cls):
        cls.clock = Moving()
        cls.extras = loop_for(cls.clock)
        cls.estate = an_estate()
        cls.estate.failures["costs"] = 429
        cls.estate.failures["daily"] = 429
        cls.summary, cls.events, _ = watch(cls.estate, cls.extras, cls.clock)
        (cls.case,) = cls.extras.store.cases_recent()
        (cls.plan,) = cls.extras.store.plans_open()
        cls.brief = build_brief(cls.case, cls.plan, now=NOW, may_answer=True)

    def test_the_watch_waits_as_cost_management_asks_and_repeats_a_few_times_and_still_ends_well(self):
        self.assertTrue(self.summary.ok)
        asked = [c for c in self.estate.calls if "costmanagement" in c["path"].lower() and c["body"]["dataset"]["granularity"] == "None"]
        self.assertEqual(len(asked), 1 + COST_RETRIES, "one read and its repeats, and no more")
        self.assertEqual(self.estate.sleeps[:COST_RETRIES], [1.0] * COST_RETRIES, "it waited as long as the answer said")
        self.assertEqual(self.events[-1]["type"], "run.finished")

    def test_the_run_says_that_the_cost_lines_could_not_be_read(self):
        notes = [e["note"] for e in self.events if e["type"] == "run.note"]
        self.assertTrue(any("cost lines could not be read" in note and "429" in note for note in notes), notes)

    def test_the_case_says_failed_and_keeps_no_zero_and_no_estimate(self):
        case = self.case
        self.assertEqual((case.cost_state, case.cost_usd_30d, case.cost_series, case.estimate), ("failed", None, None, {}))

    def test_the_page_says_that_the_cost_could_not_be_read_and_draws_no_line_and_no_zero(self):
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(self.plan)
        reply = console.get(f"/ok/{self.plan.plan_id}")
        card = reply.main.find("section", class_="focus")
        self.assertIn(FAILED_WORDS, card.text())
        self.assertIn("The next search reads it again.", card.text())
        self.assertNotIn("Estimate at list price", reply.main.text(), "an estimate is for a read that worked and found no line")
        (chart,) = [n for n in card.find_all("figure") if "chart" in n.classes()]
        self.assertEqual(chart.find_all("path"), [])
        self.assertNotRegex(reply.main.text(), ZERO)
        self.assertNotIn(NO_LINE_WORDS, reply.main.text(), "it is not said that Azure has no line: it was not read")

    def test_a_letter_and_a_card_say_so_too(self):
        person = Person(OID, "Tino", ("owner", "approver"), "tino@example.com")
        letter = letters.approval_letter(self.plan, self.case, person, BASE, NOW, ())
        card = cards.decision_card(self.brief, cards.CardContext(page_url=f"{BASE}/ok/{self.plan.plan_id}"))
        for text in (letter.text, card_text(card)):
            self.assertIn(FAILED_WORDS, text)
            self.assertNotRegex(text, ZERO)

    def test_the_next_watch_reads_again_and_the_case_gets_its_figure_when_azure_answers(self):
        self.clock.advance(hours=3)
        estate = an_estate()
        estate.cost_rows.append((3.5, an_idle_disk("idle-disk-0")["id"].lower()))
        watch(estate, self.extras, self.clock)
        (case,) = self.extras.store.cases_recent()
        self.assertEqual((case.cost_state, case.cost_usd_30d, case.estimate), ("lines", 3.5, {}))

    def test_a_read_that_fails_later_does_not_take_the_figure_from_a_request_that_has_one(self):
        clock = Moving()
        extras = loop_for(clock)
        estate = an_estate()
        estate.cost_rows.append((3.5, an_idle_disk("idle-disk-0")["id"].lower()))
        watch(estate, extras, clock)
        clock.advance(days=1)
        failing = an_estate()
        failing.failures["costs"] = 429
        watch(failing, extras, clock)
        (case,) = extras.store.cases_recent()
        self.assertEqual((case.cost_state, case.cost_usd_30d), ("lines", 3.5))


if __name__ == "__main__":
    unittest.main()
