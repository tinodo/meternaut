import re
import unittest

from test_web_support import MAYA, NOW, OPS, OWNER, SUB, STRANGER, TINO, XSS, XSS_ESCAPED, Console, FailingStore, at, make_action, make_case, make_plan, snapshot

from cases import pricing
from cases.memory_store import MemoryStore
from cases.models import CASE_STATUSES, StoreError

PATH = "/ops/savings"
AMOUNTS = {"proposed": 10.0, "needs_human": 20.0, "awaiting_ok": 30.0, "approved": 40.0, "running": 50.0, "done": 60.0, "verified": 70.0, "acknowledged": 80.0,
           "declined": 91.0, "expired": 101.0, "dropped": 111.0, "error": 121.0, "failed": 131.0}
SCENARIO = ("needs_human", "acknowledged")  # the findings whose figure is Azure Advisor's own estimate: the level Scenario
ROWS = ("Waiting for a person", "Being made", "Made, not yet confirmed", "Confirmed by Cost Management", "Worth acting on", "Declined", "Taken back", "Dropped", "Could not be finished")
EXPECTED_BASIS = "Based on the cost lines of the last 30 days."
SCENARIO_BASIS = "Based on Azure Advisor's own estimate: no cost line of this resource backs it."
NOTHING_CHANGED = "Nothing was changed, so no saving is claimed for this approval."
LOOK = "A person has to answer or look at it."
TILE_AND_ROW = '"Saving measured" counts every change that Cost Management confirmed, so it can be larger than the row "Confirmed by Cost Management".'


def finding(status: str, **more):
    """An invented finding in a status, with a saving of its own (a month): Expected, or Scenario for two of the statuses."""
    amount = AMOUNTS[status]
    base = dict(case_id=f"c-{status}", resource_id=f"/subscriptions/{SUB}/resourceGroups/rg-{status}/providers/Microsoft.Compute/disks/disk-{status}", resource_name=f"disk-{status}",
                resource_group=f"rg-{status}", status=status, saving_usd_month=amount, cost_usd_30d=amount, detector="advisor-cost" if status in SCENARIO else "orphan-managed-disk")
    return make_case(**{**base, **more})


def change(console: Console, case_id: str, plan_id: str, queued: str, state: str = "verified", **check) -> None:
    """An approved change of a finding: its plan (used) and its action, queued at `queued`, with what the check afterwards found."""
    console.store.plan_put(make_plan(plan_id=plan_id, case_id=case_id, state="consumed"))
    console.store.action_put(make_action(plan_id=plan_id, case_id=case_id, state=state, queued_at=queued, finished_at=queued, verified_at=at(hours=-1) if state == "verified" else None, verification=check))


def seeded(console: Console | None = None) -> Console:
    """One finding in each of the 13 statuses. The case that is verified expected 70 a month, and Cost Management confirmed 25 a month after the change."""
    console = console or Console()
    for status in AMOUNTS:
        console.store.case_put(finding(status, plan_id="plan-v" if status == "verified" else None))
    console.store.plan_put(make_plan(plan_id="plan-v", case_id="c-verified", state="consumed"))
    console.store.action_put(make_action(plan_id="plan-v", case_id="c-verified", state="verified", verified_at=at(hours=-1),
                                         verification={"gone": True, "costBeforeUsd30d": 25.0, "costAfterUsd": 0.0}))
    return console


def rows_of(reply) -> dict:
    """The rows of the table by the name of the group, each by the names of its columns."""
    table = reply.table("savings")
    assert table.headers == ["What became of it", "Findings", "Saving a year", "Findings with no saving figure"], table.headers
    return {next(name for name in ROWS if row["What became of it"].startswith(name)): row for row in table.rows}


def tiles_of(reply) -> dict:
    (tiles,) = reply.main.find_all("ul", class_="kpis")
    return {li.find("p", class_="k").text(): (li.find("p", class_="v").text(), li.find("p", class_="n").text(), "good" in li.classes()) for li in tiles.find_all("li")}


class OneStatusDown(MemoryStore):
    """A store that cannot read the findings of one status."""

    def __init__(self, status: str, clock) -> None:
        super().__init__(clock)
        self.down = status

    def cases_recent(self, limit: int = 100, status: str | None = None):
        if status == self.down:
            raise StoreError("the store is down", 503)
        return super().cases_recent(limit, status)


class ReadOnly(MemoryStore):
    """A store that fails the test at the first write, once it is locked."""

    locked = False

    def __getattribute__(self, name):
        if object.__getattribute__(self, "locked") and name.endswith(("_put", "_delete", "_claim", "_update", "_release", "_new", "_use", "_take")):
            raise AssertionError(f"the page wrote: {name}")
        return super().__getattribute__(name)


class TheSavingsPage(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.reply = self.console.get(PATH)

    def test_it_is_a_head_three_tiles_one_table_and_a_link_back_to_every_run_and_every_finding(self):
        reply = self.reply
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.problems, [])
        self.assertEqual(reply.headings(1), ["Savings found"])
        self.assertEqual(reply.main.find("div", class_="head").find("p").text(), "Every saving that Meternaut found, each finding counted once, by what became of it. "
                         "Money is in US dollars, and a year is twelve times the month. A saving is an estimate until Cost Management confirms it.")
        self.assertEqual(list(tiles_of(reply)), ["Found in all", "Waiting for a person", "Saving measured"], "the guide allows at most three tiles")
        self.assertEqual(len(reply.main.find("ul", class_="kpis").find_all("li")), 3)
        self.assertEqual(list(rows_of(reply)), list(ROWS), "in this order")
        self.assertEqual(reply.forms(), [])
        self.assertIn("/ops/runs", reply.links())
        self.assertEqual(reply.root.find("main").classes(), ["wide"])
        self.assertIn("You see this because your role ops or owner lets you see every saving that was found.", reply.content)

    def test_each_finding_is_counted_once_in_the_row_of_what_became_of_it(self):
        counts = {name: row["Findings"] for name, row in rows_of(self.reply).items()}
        self.assertEqual(counts, {"Waiting for a person": "3", "Being made": "2", "Made, not yet confirmed": "1", "Confirmed by Cost Management": "1", "Worth acting on": "1",
                                  "Declined": "1", "Taken back": "1", "Dropped": "1", "Could not be finished": "2"})
        self.assertEqual(sum(int(count) for count in counts.values()), len(CASE_STATUSES))
        for statuses, name in ((("proposed", "needs_human", "awaiting_ok"), "Waiting for a person"), (("approved", "running"), "Being made"), (("done",), "Made, not yet confirmed"),
                               (("verified",), "Confirmed by Cost Management"), (("acknowledged",), "Worth acting on"), (("declined",), "Declined"), (("expired",), "Taken back"),
                               (("dropped",), "Dropped"), (("error", "failed"), "Could not be finished")):
            with self.subTest(name=name):
                console = Console()
                for status in statuses:
                    console.store.case_put(finding(status))
                found = {n: row["Findings"] for n, row in rows_of(console.get(PATH)).items()}
                self.assertEqual(found, {n: str(len(statuses)) if n == name else "0" for n in ROWS}, "only its own row counts it")

    def test_the_savings_of_the_groups_that_are_found_are_added_up_with_their_basis_and_the_others_are_counted_and_not_added(self):
        rows = rows_of(self.reply)
        self.assertEqual(rows["Being made"]["Saving a year"], f"$1,080 a year Saves, Expected. $90.00 a month. {EXPECTED_BASIS}")
        self.assertEqual(rows["Made, not yet confirmed"]["Saving a year"], f"$720 a year Saves, Expected. $60.00 a month. {EXPECTED_BASIS}")
        self.assertEqual(rows["Worth acting on"]["Saving a year"], f"$960 a year Saves, Scenario. $80.00 a month. {SCENARIO_BASIS}")
        for name in ("Declined", "Taken back", "Dropped", "Could not be finished"):
            with self.subTest(name=name):
                self.assertEqual((rows[name]["Saving a year"], rows[name]["Findings with no saving figure"]), ("No saving is claimed.", "Not added up."))
                self.assertNotRegex(rows[name]["What became of it"] + rows[name]["Saving a year"], r"\$")
        self.assertIn("A person said no. Nothing changed.", rows["Declined"]["What became of it"])
        self.assertIn("Meternaut took the request back, and the request says why.", rows["Taken back"]["What became of it"])
        self.assertNotIn("nobody answered in time", self.reply.content, "nothing ends by the clock")
        self.assertIn("Cost Management reports a cost 8 to 72 hours after it happens.", rows["Made, not yet confirmed"]["What became of it"])
        self.assertIn("A person has to answer or look at it before anything changes. Nothing closes it by time: if nobody answers, it goes on to the next person.", rows["Waiting for a person"]["What became of it"])
        text = self.reply.content
        for amount in ("$1,092", "$1,212", "$1,332", "$1,452", "$1,572", "$6,660", "$10,440"):
            self.assertNotIn(amount, text, "what was declined, expired, dropped or not finished is added up nowhere")

    def test_a_finding_that_was_confirmed_shows_what_cost_management_confirmed_and_not_what_was_expected(self):
        row = rows_of(self.reply)["Confirmed by Cost Management"]
        self.assertEqual(row["Saving a year"], "$300 a year Saves, Verified. $25.00 a month. Based on the cost lines after the change, which show no cost for this resource.")
        self.assertNotIn("$840", self.reply.content, "70 a month was expected when it was proposed")
        self.assertEqual(rows_of(self.reply)["Made, not yet confirmed"]["Saving a year"].count("Verified"), 0, "the figure of a change that is done is the expected one, with its level")

    def test_a_confirmed_finding_whose_change_was_not_read_shows_its_own_figure_with_its_own_level_and_never_verified(self):
        console = Console()
        console.store.case_put(finding("verified"))
        row = rows_of(console.get(PATH))["Confirmed by Cost Management"]
        self.assertEqual((row["Findings"], row["Saving a year"]), ("1", f"$840 a year Saves, Expected. $70.00 a month. {EXPECTED_BASIS}"))
        self.assertNotIn("Verified", row["Saving a year"])
        self.assertEqual(tiles_of(console.get(PATH))["Saving measured"][0], "—", "nothing was measured that the page could read")

    def test_the_levels_of_a_group_are_apart_and_no_line_mixes_them(self):
        cell = rows_of(self.reply)["Waiting for a person"]["Saving a year"]
        self.assertEqual(cell, f"$240 a year Saves, Scenario. $20.00 a month. {SCENARIO_BASIS} $480 a year Saves, Expected. $40.00 a month. {EXPECTED_BASIS}", "the weakest level first")
        for line in re.findall(r"\$[\d,]+ a year.*?(?=\$[\d,]+ a year|$)", cell):
            self.assertEqual(len(re.findall(r"\bSaves, (?:Scenario|Expected|Verified)\b", line)), 1, line)
        for name, row in rows_of(self.reply).items():
            self.assertLessEqual(len(set(re.findall(r"Saves, (\w+)", row["Saving a year"]))), 2 if name == "Waiting for a person" else 1, name)

    def test_the_tiles_add_the_counted_groups_the_way_the_decisions_page_does_and_name_their_levels(self):
        self.assertEqual(tiles_of(self.reply), {
            "Found in all": ("$3,780 a year", "8 findings · Scenario, Expected, Verified. The basis is in the table.", True),
            "Waiting for a person": ("$720 a year", f"3 findings · Scenario, Expected. {LOOK}", True),
            "Saving measured": ("$300 a year", "$25.00 a month, confirmed by Cost Management after 1 change.", True)})

    def test_a_money_tile_says_how_many_of_the_findings_its_figure_rests_on_when_that_is_not_all_of_them(self):
        self.console.store.case_put(finding("proposed", case_id="c-cost", saving_usd_month=None, cost_usd_30d=50.0))
        self.console.store.case_put(finding("proposed", case_id="c-none", saving_usd_month=None, cost_usd_30d=None))
        reply = self.console.get(PATH)
        tiles = tiles_of(reply)
        self.assertEqual(tiles["Found in all"][:2], ("$3,780 a year", "8 of 10 findings have a saving figure · Scenario, Expected, Verified. The basis is in the table."))
        self.assertEqual(tiles["Waiting for a person"][:2], ("$720 a year", f"3 of 5 findings have a saving figure · Scenario, Expected. {LOOK}"))
        self.assertEqual(rows_of(reply)["Waiting for a person"]["Findings"], "5", "the note and the row say the same number of findings")
        self.assertEqual(sum(int(rows_of(reply)[name]["Findings"]) for name in ROWS[:5]), 10)

    def test_a_money_tile_says_how_many_findings_when_every_one_has_a_saving_figure(self):
        console = Console()
        console.store.case_put(finding("proposed"))
        tiles = tiles_of(console.get(PATH))
        self.assertEqual(tiles["Found in all"][:2], ("$120 a year", "1 finding · Expected. The basis is in the table."))
        self.assertEqual(tiles["Waiting for a person"][:2], ("$120 a year", f"1 finding · Expected. {LOOK}"))
        console.store.case_put(finding("approved"))
        tiles = tiles_of(console.get(PATH))
        self.assertEqual(tiles["Found in all"][:2], ("$600 a year", "2 findings · Expected. The basis is in the table."))
        self.assertEqual(tiles["Waiting for a person"][1], f"1 finding · Expected. {LOOK}", "only the first row")

    def test_saving_measured_adds_up_every_confirmed_change_whoever_made_it_and_is_the_tile_of_the_decisions_page_for_a_person_named_in_them(self):
        console = Console()
        console.store.case_put(finding("proposed", case_id="c-open", plan_id="plan-open"))
        console.store.plan_put(make_plan(plan_id="plan-open", case_id="c-open", saving_usd_month=10.0))  # an open request: the Decisions page has its tiles
        console.store.plan_put(make_plan(plan_id="plan0009", case_id="case0009", state="consumed"))
        console.store.action_put(make_action(plan_id="plan0009", case_id="case0009", state="verified", verified_at=at(hours=-1),
                                             verification={"gone": True, "costBeforeUsd30d": 30.0, "costAfterUsd": 0.0}))
        measured = ("$360 a year", "$30.00 a month, confirmed by Cost Management after 1 change.", True)
        for who in (TINO, OPS, OWNER):
            with self.subTest(who=who):
                self.assertEqual(tiles_of(console.get(PATH, oid=who))["Saving measured"], measured, "ops and the owner are named in no change, and see all of them")
        decisions = console.get("/", oid=TINO).main.find("ul", class_="kpis").find_all("li")[2]
        self.assertEqual((decisions.find("p", class_="k").text(), decisions.find("p", class_="v").text(), decisions.find("p", class_="n").text(), "good" in decisions.classes()),
                         ("Saving measured", *measured))
        self.assertEqual(console.get("/", oid=MAYA).main.find_all("ul", class_="kpis"), [], "a person who is named in none of the changes has no tile on the Decisions page")
        console.store.plan_put(make_plan(plan_id="plan0010", case_id="case0010", state="consumed", approvers=(MAYA,)))
        console.store.action_put(make_action(plan_id="plan0010", case_id="case0010", state="verified", verified_at=at(hours=-1),
                                             verification={"gone": True, "costBeforeUsd30d": 10.0, "costAfterUsd": 0.0}))
        self.assertEqual(tiles_of(console.get(PATH))["Saving measured"][:2], ("$480 a year", "$40.00 a month, confirmed by Cost Management after 2 changes."))
        self.assertEqual(console.get("/", oid=TINO).main.find("ul", class_="kpis").find_all("li")[2].find("p", class_="v").text(), "$360 a year", "the Decisions page counts the person's own")

    def test_a_finding_with_a_cost_and_no_saving_and_one_with_nothing_are_counted_with_the_reason_and_never_called_no_figure(self):
        self.console.store.case_put(finding("proposed", case_id="c-cost", saving_usd_month=None, cost_usd_30d=50.0))
        self.console.store.case_put(finding("proposed", case_id="c-none", saving_usd_month=None, cost_usd_30d=None))
        reply = self.console.get(PATH)
        row = rows_of(reply)["Waiting for a person"]
        self.assertEqual(row["Findings"], "5")
        self.assertEqual(row["Findings with no saving figure"], "1 finding · No cost line was read yet. 1 finding · The most that a change could save: what it would save was not worked out.")
        self.assertEqual(row["Saving a year"], rows_of(self.reply)["Waiting for a person"]["Saving a year"], "what has no saving figure adds nothing")
        self.assertEqual(rows_of(self.reply)["Waiting for a person"]["Findings with no saving figure"], "None.")
        self.assertNotRegex(reply.content, r"(?i)no figure")
        self.assertNotIn("$600", reply.content, "the cost of 50 a month is the most that a change could save, and is no saving")

    def test_a_made_finding_whose_approval_changed_nothing_claims_no_saving_and_says_so_and_a_change_that_was_made_keeps_its_figure(self):
        console = Console()
        for case_id in ("c-made", "c-nothing", "c-later"):
            console.store.case_put(finding("done", case_id=case_id))
        change(console, "c-made", "plan-made", at(hours=-3), "done", gone=True)
        change(console, "c-nothing", "plan-nothing", at(hours=-3), "done", gone=True, noChange=True, note="already gone")
        change(console, "c-later", "plan-first", at(hours=-5), "done", gone=True, noChange=True, note="already gone")
        change(console, "c-later", "plan-second", at(hours=-3), "done", gone=True)  # the newest change of this finding made one
        reply = console.get(PATH)
        row = rows_of(reply)["Made, not yet confirmed"]
        self.assertEqual(row["Findings"], "3")
        self.assertEqual(row["Saving a year"], f"$1,440 a year Saves, Expected. $120.00 a month. {EXPECTED_BASIS}", "two findings of 60 a month: the one that changed nothing adds nothing")
        self.assertEqual(row["Findings with no saving figure"], f"1 finding · {NOTHING_CHANGED}")
        self.assertEqual(tiles_of(reply)["Found in all"][:2], ("$1,440 a year", "2 of 3 findings have a saving figure · Expected. The basis is in the table."))
        self.assertEqual(tiles_of(reply)["Saving measured"][0], "—", "nothing was confirmed by Cost Management")
        self.assertNotIn("disk-", reply.text)

    def test_a_finding_shows_its_own_specific_reason_for_having_no_saving_figure_and_not_the_general_one(self):
        self.console.store.case_put(finding("needs_human", case_id="c-unpriced", saving_usd_month=None, cost_usd_30d=None, facts={"change": {"action": "remove", "missing": "lines"}}))
        row = rows_of(self.console.get(PATH))["Waiting for a person"]
        self.assertEqual((row["Findings"], row["Findings with no saving figure"]), ("4", f"1 finding · {pricing.WHY['lines']}"))

    def test_findings_that_state_a_change_are_counted_once_each_at_the_level_that_their_bill_lines_give_and_the_levels_are_never_mixed(self):
        console = Console()
        removal = {"action": "remove", "how": "Take it away.", "price": {"lowUsd": 100.0, "highUsd": 100.0, "billUsd": 100.0, "lines": 2, "resources": 1, "form": "none"}}
        assumption = {"action": "reduce", "price": {"lowUsd": 30.0, "highUsd": 60.0, "billUsd": 100.0, "lines": 2, "resources": 1, "form": "assumed", "away": [0.3, 0.6]}}
        console.store.case_put(finding("needs_human", case_id="c-removal", saving_usd_month=100.0, cost_usd_30d=100.0, facts={"change": removal}))
        console.store.case_put(finding("proposed", case_id="c-assumption", saving_usd_month=30.0, cost_usd_30d=100.0, facts={"change": assumption}))
        row = rows_of(console.get(PATH))["Waiting for a person"]
        self.assertEqual(row["Findings"], "2")
        self.assertIn("$360 a year Saves, Scenario. $30.00 a month. Based on the 2 bill lines of 1 resource that the change would shrink", row["Saving a year"])
        self.assertIn("the AI's own assumption, not checked by code", row["Saving a year"])
        self.assertIn("$1,200 a year Saves, Expected. $100.00 a month. Based on the 2 bill lines of 1 resource that the change would remove, over the last 30 days.", row["Saving a year"])
        self.assertEqual(row["Findings with no saving figure"], "None.")

    def test_two_confirmed_changes_of_one_finding_show_the_newest_in_its_row_and_are_two_changes_in_the_tile_which_the_note_says(self):
        console = Console()
        console.store.case_put(finding("verified"))
        change(console, "c-verified", "plan-old", at(days=-3), gone=True, costBeforeUsd30d=10.0, costAfterUsd=0.0)
        change(console, "c-verified", "plan-new", at(days=-1), gone=True, costBeforeUsd30d=25.0, costAfterUsd=0.0)
        reply = console.get(PATH)
        row = rows_of(reply)["Confirmed by Cost Management"]
        self.assertEqual((row["Findings"], row["Saving a year"]), ("1", "$300 a year Saves, Verified. $25.00 a month. Based on the cost lines after the change, which show no cost for this resource."))
        self.assertEqual(tiles_of(reply)["Saving measured"][:2], ("$420 a year", "$35.00 a month, confirmed by Cost Management after 2 changes."), "the tile counts every change")
        self.assertIn(TILE_AND_ROW, reply.content)

    def test_a_level_with_two_different_bases_in_one_row_says_that_the_figures_of_each_are_added_up(self):
        console = Console()
        for case_id, plan_id, check in (("c-one", "plan-one", dict(gone=True, costBeforeUsd30d=25.0, costAfterUsd=0.0)),
                                        ("c-two", "plan-two", dict(gone=True, costBeforeUsd30d=40.0, costAfterUsd=20.0, savedUsdMonth=12.5))):
            console.store.case_put(finding("verified", case_id=case_id))
            change(console, case_id, plan_id, at(days=-1), **check)
        row = rows_of(console.get(PATH))["Confirmed by Cost Management"]
        self.assertEqual((row["Findings"], row["Saving a year"]), ("2", "$450 a year Saves, Verified. $37.50 a month. Based on the figures of each, added up."))

    def test_the_link_to_every_run_and_every_finding_is_for_the_role_ops_whose_page_it_opens(self):
        for who, shown in ((TINO, True), (OPS, True), (OWNER, False)):
            with self.subTest(who=who):
                reply = self.console.get(PATH, oid=who)
                self.assertEqual(reply.status, 200)
                self.assertEqual(("/ops/runs" in reply.links(), "Every run and every finding" in reply.content), (shown, shown))
        self.assertEqual(self.console.get("/ops/runs", oid=OWNER).status, 403, "the page that the link opens refuses a person with the role owner alone")

    def test_a_group_that_has_no_finding_says_that_there_is_nothing_to_add_up(self):
        reply = Console().get(PATH)
        for name, row in rows_of(reply).items():
            self.assertEqual(row["Findings"], "0", name)
        self.assertEqual(rows_of(reply)["Being made"]["Saving a year"], "Nothing to add up.")
        self.assertEqual(tiles_of(reply), {"Found in all": ("—", "No saving is known yet.", False), "Waiting for a person": ("—", "No saving is known yet.", False),
                                           "Saving measured": ("—", "Nothing measured yet. Cost lines arrive 8 to 72 hours after a change.", False)})
        self.assertNotIn("cannot be read", reply.content)


class TheWindowsAndTheFailures(unittest.TestCase):
    def test_a_status_that_holds_a_thousand_findings_says_at_least_and_one_that_holds_fewer_does_not(self):
        console = Console()
        for n in range(1000):
            console.store.case_put(finding("dropped", case_id=f"d{n}"))
        for n in range(999):
            console.store.case_put(finding("failed", case_id=f"f{n}"))
        reply = console.get(PATH)
        rows = rows_of(reply)
        self.assertEqual((rows["Dropped"]["Findings"], rows["Could not be finished"]["Findings"]), ("At least 1,000", "999"))
        self.assertEqual(rows["Declined"]["Findings"], "0")
        self.assertIn("up to 1,000 findings of each status", reply.content)

    def test_a_counted_status_that_holds_a_thousand_findings_gives_its_savings_as_at_least_and_the_tiles_say_that_they_are_not_complete(self):
        console = seeded()
        for n in range(1000):
            console.store.case_put(finding("proposed", case_id=f"p{n}", saving_usd_month=1.0, cost_usd_30d=1.0))
        reply = console.get(PATH)
        row = rows_of(reply)["Waiting for a person"]
        self.assertEqual(row["Findings"], "At least 1,002", "a thousand of one status and one of each of the two others, read in part")
        self.assertTrue(row["Saving a year"].startswith("At least $"), row["Saving a year"])
        found = tiles_of(reply)["Found in all"]
        self.assertRegex(found[0], r"^\$[\d,]+\+ a year$")
        self.assertTrue(found[1].endswith("Not complete: there may be more."), found[1])
        self.assertEqual(tiles_of(reply)["Saving measured"][0], "$300 a year", "the confirmed changes are in a status that was read in full")
        self.assertNotIn("cannot be read", reply.content, "a window that is full is not a failure")

    def test_a_status_that_cannot_be_read_is_said_in_a_notice_in_its_row_and_in_the_tile_and_the_page_does_not_fail(self):
        for status, name in (("done", "Made, not yet confirmed"), ("dropped", "Dropped")):
            with self.subTest(status=status):
                console = Console(store=OneStatusDown(status, lambda: NOW))
                seeded(console)
                reply = console.get(PATH)
                self.assertEqual(reply.status, 200)
                self.assertIn("Part of the findings cannot be read", reply.content)
                self.assertIn("Nothing has changed.", reply.content)
                self.assertEqual(rows_of(reply)[name]["Findings"], "Cannot be read now.")
                self.assertEqual(rows_of(reply)["Being made"]["Findings"], "2", "the other groups are read")
                found = tiles_of(reply)["Found in all"]
                if status == "done":
                    self.assertEqual(rows_of(reply)[name]["Saving a year"], "Not known.")
                    self.assertRegex(found[0], r"^\$[\d,]+\+ a year$")
                    self.assertTrue(found[1].endswith("Not complete: there may be more."), found[1])
                else:
                    self.assertEqual(found[:2], ("$3,780 a year", "8 findings · Scenario, Expected, Verified. The basis is in the table."), "a status that is not added up is not in the tile")
                    self.assertEqual(rows_of(reply)["Declined"]["Findings"], "1")

    def test_a_group_of_two_statuses_that_is_read_in_part_gives_at_least_and_says_that_part_cannot_be_read(self):
        console = Console(store=OneStatusDown("awaiting_ok", lambda: NOW))
        seeded(console)
        row = rows_of(console.get(PATH))["Waiting for a person"]
        self.assertEqual(row["Findings"], "At least 2 Part of it cannot be read now.")
        self.assertTrue(row["Saving a year"].startswith("At least $"), row["Saving a year"])

    def test_in_a_row_that_is_read_in_part_the_counts_of_the_findings_with_no_saving_figure_say_at_least_too(self):
        console = Console()
        for n in range(1000):
            console.store.case_put(finding("proposed", case_id=f"p{n}", saving_usd_month=None, cost_usd_30d=None))
        row = rows_of(console.get(PATH))["Waiting for a person"]
        self.assertEqual((row["Findings"], row["Findings with no saving figure"]), ("At least 1,000", "At least 1,000 findings · No cost line was read yet."))
        part = Console(store=OneStatusDown("awaiting_ok", lambda: NOW))
        part.store.case_put(finding("proposed", case_id="c-none", saving_usd_month=None, cost_usd_30d=None))
        self.assertEqual(rows_of(part.get(PATH))["Waiting for a person"]["Findings with no saving figure"], "At least 1 finding · No cost line was read yet.")

    def test_when_nothing_can_be_read_no_number_is_given_and_the_page_still_answers(self):
        console = Console(store=FailingStore(fail={"cases_recent", "plans_recent", "actions_recent"}, clock=lambda: NOW))
        reply = console.get(PATH)
        self.assertEqual(reply.status, 200)
        self.assertIn("The findings cannot be read", reply.content)
        for name, row in rows_of(reply).items():
            self.assertEqual(row["Findings"], "Cannot be read now.", name)
        self.assertEqual({label: tile[:2] for label, tile in tiles_of(reply).items()}, {
            "Found in all": ("—", "Cannot be read now."), "Waiting for a person": ("—", "Cannot be read now."), "Saving measured": ("—", "Cannot be read now.")})
        self.assertNotRegex(reply.main.text(), r"\$\d")

    def test_when_the_changes_cannot_be_read_the_confirmed_finding_keeps_its_own_figure_with_its_own_level_and_the_tile_says_that_it_cannot_be_read(self):
        for fail in ({"plans_recent"}, {"actions_recent"}, {"plans_recent", "actions_recent"}):
            with self.subTest(fail=fail):
                console = seeded(Console(store=FailingStore(fail=fail, clock=lambda: NOW)))
                reply = console.get(PATH)
                self.assertEqual(reply.status, 200)
                self.assertIn("Part of the findings cannot be read", reply.content)
                row = rows_of(reply)["Confirmed by Cost Management"]
                self.assertEqual((row["Findings"], row["Saving a year"]), ("1", f"$840 a year Saves, Expected. $70.00 a month. {EXPECTED_BASIS}"), "its own figure, with its own level")
                self.assertNotIn("Verified", reply.content)
                self.assertEqual(tiles_of(reply)["Saving measured"][:2], ("—", "Cannot be read now."), "the same words as the other tiles use")

    def test_a_thousand_changes_or_plans_read_make_the_measured_saving_at_least_and_are_no_failure(self):
        console = seeded()
        for n in range(1000):
            console.store.plan_put(make_plan(plan_id=f"old{n}", case_id=f"old-case{n}", state="declined"))
        reply = console.get(PATH)
        self.assertEqual(tiles_of(reply)["Saving measured"][:2], ("$300+ a year", "$25.00 a month, confirmed by Cost Management after 1 change. Not complete: there may be more."))
        self.assertNotIn("cannot be read", reply.content)
        self.assertEqual(rows_of(reply)["Confirmed by Cost Management"]["Findings"], "1", "the finding is in a status that was read in full")


class WhatItShowsOfTheEstate(unittest.TestCase):
    def test_no_name_no_id_and_no_text_of_the_estate_or_of_a_model_is_on_the_page(self):
        console = Console()
        hostile = dict(resource_name=XSS, resource_group=XSS, resource_type=XSS, subscription_id=XSS, summary=XSS, objections=(XSS,), recommendation=XSS, models={"detective": XSS},
                       facts={XSS: XSS, "list": [XSS]}, run_id=XSS)
        for status in AMOUNTS:
            console.store.case_put(finding(status, case_id=f"hostile-{status}", resource_id=f"{XSS}/{status}", plan_id=None if status != "verified" else "hostile-plan", **hostile))
        seeded(console)
        console.store.plan_put(make_plan(plan_id="hostile-plan", case_id="hostile-verified", title=XSS, what_changes=XSS, resource_name=XSS, resource_group=XSS, state="consumed"))
        console.store.action_put(make_action(plan_id="hostile-plan", case_id="hostile-verified", state="verified", result=XSS, error=XSS,
                                             verification={"gone": True, "costBeforeUsd30d": 25.0, "costAfterUsd": 0.0, "note": XSS}))
        reply = console.get(PATH)
        self.assertEqual(reply.status, 200)
        text = reply.text
        for payload in (XSS, XSS_ESCAPED, "<script", "<img", "onerror"):
            self.assertNotIn(payload, text)
        for estate in ("disk-", "rg-", "c-proposed", "hostile", "plan-v", SUB, "microsoft.compute", "The disk is not attached"):
            self.assertNotIn(estate, text, estate)
        self.assertEqual(reply.problems, [])
        self.assertEqual([href for href in reply.links() if href.startswith(("http", "mailto", "javascript"))], [])
        self.assertEqual([href for href in reply.links() if "case" in href or "plan" in href or "/why/" in href or "/ok/" in href], [], "no link to a finding or a request")
        self.assertEqual(reply.root.find_all("code"), [])

    def test_it_reads_and_writes_nothing_else_and_a_post_is_not_a_route(self):
        store = ReadOnly(clock=lambda: NOW)
        console = Console(store=store)
        seeded(console)
        store.locked = True
        before = snapshot(store)
        reply = console.get(PATH)
        self.assertEqual(reply.status, 200)
        self.assertEqual(console.send("HEAD", PATH).status, 200)
        self.assertEqual(console.post(PATH, {}).status, 405)
        self.assertEqual(snapshot(store), before)
        self.assertEqual((console.decider.calls, console.delegate.begins, console.delegate.finishes), ([], [], []))

    def test_a_page_that_is_the_same_for_the_same_records(self):
        one, two = seeded().get(PATH), seeded().get(PATH)
        self.assertEqual(one.text, two.text)


class WhoMayOpenIt(unittest.TestCase):
    def setUp(self):
        self.console = seeded()

    def test_a_person_with_the_role_ops_or_owner_opens_it_and_a_person_with_neither_gets_the_refusal_of_the_permissions_page(self):
        for who, status in ((TINO, 200), (OPS, 200), (OWNER, 200), (MAYA, 403)):
            with self.subTest(who=who):
                self.assertEqual(self.console.get(PATH, oid=who).status, status)
        refused = self.console.get(PATH, oid=MAYA)
        permissions = self.console.get("/ops/permissions", oid=MAYA)
        self.assertEqual(refused.headings(1), ["You do not have the role that this page needs"])
        self.assertEqual(refused.text, permissions.text, "the same refusal as the permissions page gives, to the letter")
        self.assertIn("This page is for people with the role ops or owner.", refused.content)
        self.assertNotIn("a year", refused.main.text(), "nothing of the page is shown to a person who may not open it")

    def test_a_person_who_is_not_listed_gets_the_denied_page_and_a_request_without_a_sign_in_the_same(self):
        denied = self.console.get("/", oid=None)
        for who in (STRANGER, None):
            reply = self.console.get(PATH, oid=who)
            self.assertEqual((reply.status, reply.text), (denied.status, denied.text))
        self.assertEqual(denied.status, 403)

    def test_the_page_is_in_the_navigation_of_ops_and_owner_only_and_marked_when_it_is_open(self):
        def names(oid):
            return [a.text() for a in self.console.get("/", oid=oid).root.find("nav").find_all("a")]
        self.assertEqual(names(TINO), ["Decisions", "History", "Settings", "Operations", "Savings found", "What the AI looked at"])
        self.assertEqual(names(OPS), ["Decisions", "History", "Settings", "Operations", "Savings found", "What the AI looked at"])
        self.assertEqual(names(OWNER), ["Decisions", "History", "Settings", "Savings found", "What the AI looked at"])
        self.assertEqual(names(MAYA), ["Decisions", "History", "Settings"])
        reply = self.console.get(PATH, oid=OWNER)
        current = [a.text() for a in reply.root.find("nav").find_all("a") if a.attrs.get("aria-current") == "page"]
        self.assertEqual(current, ["Savings found"])
        self.assertEqual([a.attrs["href"] for a in reply.root.find("nav").find_all("a")][-2:], [PATH, "/ops/activity"], "it comes just before What the AI looked at")

    def test_the_operations_page_links_to_it_beside_every_run_and_every_finding(self):
        links = self.console.get("/ops", oid=OPS).links()
        self.assertEqual(links[links.index("/ops/runs") + 1], PATH)

    def test_the_router_has_the_route_for_the_roles_ops_and_owner_and_no_other(self):
        from cases.web import router, savings
        found = [(method, roles, handler) for method, pattern, handler, roles in router.ROUTES if pattern == PATH]
        self.assertEqual(found, [("GET", ("ops", "owner"), savings.savings_page)])
        self.assertIn(("GET", "/ops/savings"), {(method, pattern) for method, pattern, _, _ in router.ROUTES})
        self.assertEqual(len([1 for _, pattern, _, _ in router.ROUTES if "savings" in pattern]), 1, "a GET and nothing that writes")


class TheSavingsOfAzureAdvisor(unittest.TestCase):
    """Advisor's own recommendations are findings at the level Scenario, each counted once; a finding that Meternaut's own check or an AI made too keeps its own figure."""

    @staticmethod
    def digest(yearly: float, n: int = 3) -> dict:
        row = ["Standard_D2s_v6", 1, "swedencentral", "P1Y", round(yearly / n, 2), "USD", 60, "Single"]
        return {"type": "84b1a508-0000-4000-8000-000000000001", "sub": "Reservations", "n": n, "added": n, "skipped": 0, "currencies": [], "usd": yearly, "rows": [row] * n, "more": 0, "moreUsd": 0.0}

    def advisor_case(self, case_id: str, yearly: float, **more):
        return make_case(case_id=case_id, detector="advisor-cost", status="needs_human", saving_usd_month=None, cost_usd_30d=None, models={}, steps=(), recommendation="change", summary="",
                         objections=(), resource_id=f"/subscriptions/{SUB}", resource_type="microsoft.subscriptions/subscriptions", resource_name="", resource_group="",
                         facts={"category": "cost", "advisor": self.digest(yearly)}, advice={"problem": "Buy reservations", "solution": "Buy reservations"}, **more)

    def row(self, console: Console) -> dict:
        return rows_of(console.get(PATH))["Waiting for a person"]

    def test_the_cases_of_advisor_are_added_at_the_level_scenario_once_each_with_no_other_level_mixed_in(self):
        console = Console()
        console.store.case_put(self.advisor_case("a1", 1200.0))
        console.store.case_put(self.advisor_case("a2", 600.0))
        row = self.row(console)
        self.assertEqual(row["Findings"], "2")
        self.assertIn("Saves, Scenario", row["Saving a year"])
        self.assertIn("$1,800", row["Saving a year"], "1,200 and 600 a year, each once")
        self.assertNotIn("Expected", row["Saving a year"])
        self.assertIn("Azure Advisor's own estimate of the smallest of its variants", console.get(PATH).content.replace("&#x27;", "'"))

    def test_a_finding_that_advisor_also_names_is_counted_with_its_own_figure_and_advisors_is_not_added_to_it(self):
        console = Console()
        console.store.case_put(make_case(case_id="c-own", status="needs_human", saving_usd_month=20.0, cost_usd_30d=20.0, facts={"diskState": "unattached", "advisor": self.digest(480.0)}))
        console.store.case_put(make_case(case_id="c-none", status="needs_human", saving_usd_month=None, cost_usd_30d=None, facts={"diskState": "unattached", "advisor": self.digest(120.0)}))
        row = self.row(console)
        self.assertEqual(row["Findings"], "2")
        self.assertIn("Saves, Expected", row["Saving a year"])
        self.assertIn("$240", row["Saving a year"], "its own figure, 20 a month")
        self.assertIn("Saves, Scenario", row["Saving a year"])
        self.assertIn("$120", row["Saving a year"], "Advisor's figure for the finding that has none of its own: 10 a month")
        self.assertNotIn("$480", row["Saving a year"])
        self.assertNotIn("$840", row["Saving a year"])


if __name__ == "__main__":
    unittest.main()
