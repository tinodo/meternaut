import datetime as dt
import re
import unittest
from dataclasses import replace
from unittest import mock

from support import APP_ROOT
from test_web_support import (MAYA, NOW, OPS, OWNER, SUB, TINO, VM, XSS, Console, FailingStore, at, make_action, make_advice, make_advice_case, make_case, make_decision, make_plan,
                              snapshot)

from cases.models import GROUP_FACT, SettingsRecord, StoreError
from cases.web import core, figures, history

VM_ID = VM

NAV_ALL = ["Decisions", "History", "Settings", "Operations"]
HEADLINE = "Delete the unattached disk planted-disk-1 in group meternaut-test-rg"
TITLE = "Delete the unattached disk planted-disk-1"  # the headline of a request page: without its place, which the line under it says


def opens(reply) -> str:
    """The line under the title of a request page: what it is, where, when it was found and until when it is open."""
    return reply.main.find("div", class_="head").find("p").text()


def seeded() -> Console:
    console = Console()
    console.seed()
    return console


def lane(reply, anchor: str):
    """The section of one lane of the page of the decisions: "ready" (changes) or "look" (findings)."""
    (section,) = [s for s in reply.main.find_all("section") if s.attrs.get("aria-labelledby") == anchor]
    return section


def decisions(reply, anchor: str) -> list[str]:
    """Where the buttons of a lane go, in the order of the page: the decision in focus first, then the rows."""
    return [a.attrs["href"] for a in lane(reply, anchor).find_all("a") if a.attrs["href"].startswith("/ok/")]


def rows(reply, anchor: str) -> list:
    """The rows of a lane under the decision in focus."""
    return [li for ol in lane(reply, anchor).find_all("ol", class_="items") for li in ol.children if hasattr(li, "tag")]


def spans(node) -> list[str]:
    """The text of each span that is a direct child of a node: the parts of a figure, of a row of recent decisions."""
    return [child.text() for child in node.children if hasattr(child, "tag") and child.tag == "span"]


def chips(node) -> list[str]:
    return [span.text() for span in node.find_all("span") if "chip" in span.classes()]


def storage(console: Console, count: int, cost=lambda n: 3.0 + n, saving=lambda n: None) -> None:
    """`count` findings of the investigation about one storage account each, in a resource group each, with a request for each."""
    for n in range(count):
        rid = f"/subscriptions/{SUB}/resourceGroups/rg-{n}/providers/Microsoft.Storage/storageAccounts/st{n}"
        console.store.case_put(make_advice_case(case_id=f"case5{n:03d}", resource_id=rid, resource_name=f"st{n}", resource_type="microsoft.storage/storageaccounts",
                                                resource_group=f"rg-{n}", saving_usd_month=saving(n), cost_usd_30d=cost(n), plan_id=f"plan5{n:03d}"))
        console.store.plan_put(make_advice(plan_id=f"plan5{n:03d}", case_id=f"case5{n:03d}", resource_id=rid, resource_name=f"st{n}", resource_group=f"rg-{n}",
                                           saving_usd_month=saving(n), title=f"Look at the storage account st{n} in group rg-{n}"))


def endpoints(console: Console) -> None:
    """One finding that stands for 50 private endpoints in 8 resource groups, and the one request about all of them."""
    rid = f"/subscriptions/{SUB}/resourceGroups/rg-pe/providers/Microsoft.Network/privateEndpoints/pe-1"
    group = {"count": 50, "groups": 8, "type": "microsoft.network/privateendpoints", "names": ["pe-2", "pe-3", "pe-4", "pe-5"], "costUsd30d": 358.11}
    console.store.case_put(make_advice_case(case_id="case6000", resource_id=rid, resource_name="pe-1", resource_type="microsoft.network/privateendpoints", resource_group="rg-pe",
                                            saving_usd_month=None, cost_usd_30d=358.11, plan_id="plan6000", facts={"basis": "idle", GROUP_FACT: group}))
    console.store.plan_put(make_advice(plan_id="plan6000", case_id="case6000", resource_id=rid, resource_name="pe-1", resource_group="rg-pe", saving_usd_month=None,
                                       title="Look at 50 private endpoints"))


def busy() -> Console:
    """A console whose page of the decisions has every part: a decision in focus, rows, a row that opens for three requests, one that stands for fifty resources, a finding with no
    cost, a request that was put off, a finding that is held back and a decision that was made."""
    console = seeded()
    more_plans(console, 2, saving=lambda n: 30.0, seen=lambda n: (-3, -10)[n])
    console.store.case_put(make_advice_case())
    console.store.plan_put(make_advice())
    storage(console, 3)
    endpoints(console)
    console.store.case_put(make_advice_case(case_id="case7000", resource_id=f"{VM}-none", resource_name="law-x", resource_type="microsoft.operationalinsights/workspaces",
                                            saving_usd_month=None, cost_usd_30d=None, plan_id="plan7000"))
    console.store.plan_put(make_advice(plan_id="plan7000", case_id="case7000", resource_id=f"{VM}-none", resource_name="law-x", saving_usd_month=None))
    console.store.decision_put(make_decision(plan_id="plan7000", decision="later"))
    console.store.case_put(make_advice_case(case_id="case3000", resource_id=f"{VM_ID}-held", resource_name="held-1", plan_id=None))
    console.store.plan_put(make_plan(plan_id="plan2000", case_id="case2000", resource_name="gone-0", state="declined"))
    console.store.decision_put(make_decision(plan_id="plan2000", decision="decline", at=at(hours=-1)))
    return console


def more_plans(console: Console, count: int, *, saving=lambda n: 1.0 + n, seen=lambda n: -3) -> None:
    """`count` more open requests, each for a disk of its own."""
    for n in range(count):
        console.store.case_put(make_case(case_id=f"case1{n:03d}", resource_name=f"disk-{n}", saving_usd_month=saving(n), first_seen_at=at(days=seen(n)), plan_id=f"plan1{n:03d}"))
        console.store.plan_put(make_plan(plan_id=f"plan1{n:03d}", case_id=f"case1{n:03d}", resource_name=f"disk-{n}", saving_usd_month=saving(n)))


class TheDecisionsPage(unittest.TestCase):
    def test_it_is_a_summary_two_lanes_and_the_last_decisions_and_nothing_else(self):
        reply = seeded().get("/")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Decisions"])
        self.assertEqual(reply.headings(2), ["Ready to decide", "Recently decided"])
        self.assertEqual(reply.root.find("main").classes(), ["wide"])
        self.assertEqual(reply.root.find_all("table"), [], "no table: a table is only in a row that opens")
        self.assertEqual(reply.forms(), [])
        self.assertEqual(reply.problems, [])

    def test_the_decision_with_the_most_at_stake_is_in_focus_with_its_figure_a_year_and_a_month_and_what_it_is_based_on(self):
        reply = seeded().get("/")
        focus = reply.main.find("article", class_="focus")
        self.assertEqual(focus.find("h3").text(), "Delete the unattached disk planted-disk-1")
        self.assertEqual(focus.find("p", class_="fig save").text(), "$86 a year")
        self.assertEqual(focus.find("p", class_="figsub").text(), "Saves, Expected. $7.17 a month. Based on the cost lines of the last 30 days.")
        self.assertEqual([dt.text() for dt in focus.find_all("dt")], ["What changes", "Why", "Checked", "Undo"])
        self.assertEqual(chips(focus), ["Medium risk", "High confidence"])
        button = focus.find("a")
        self.assertEqual((button.attrs["class"], button.attrs["href"], button.text()), ("btn primary", "/ok/plan0001", "Review and decide: Delete the unattached disk planted-disk-1"))
        self.assertEqual(rows(reply, "ready"), [], "the one decision is in focus and not again in a row")
        self.assertEqual(reply.main.find("figure", class_="chart").find("p", class_="m").text(), f"{figures.READ_LATER} The chart fills in then.", "no series of daily costs is stored yet")

    def test_a_row_has_its_rank_its_figure_a_year_and_a_month_its_risk_and_one_button(self):
        console = seeded()
        more_plans(console, 2, saving=lambda n: 30.0, seen=lambda n: (-3, -10)[n])
        reply = console.get("/")
        first, last = rows(reply, "ready")
        self.assertEqual((first.find("span", class_="rank").text(), last.find("span", class_="rank").text()), ("2", "3"))
        self.assertEqual(first.find("span", class_="t").text(), "Delete the unattached disk disk-0")
        self.assertEqual(spans(first.find("span", class_="impact save")), ["Saves, Expected", "$360 a year", "$30.00 a month"])
        self.assertEqual(spans(last.find("span", class_="impact save")), ["Saves, Expected", "$86 a year", "$7.17 a month"])
        self.assertEqual(chips(first), ["Medium risk", "High confidence"])
        self.assertEqual([(a.attrs["class"], a.attrs["href"], a.text()) for a in first.find_all("a")], [("btn sm primary", "/ok/plan1000", "Review: Delete the unattached disk disk-0")])
        self.assertIn("Managed disk · resource group meternaut-test-rg · found 3 days ago", first.text())
        self.assertIn("Based on the cost lines of the last 30 days.", first.text())

    def test_the_decisions_are_ranked_by_what_is_at_stake_then_by_how_long_they_waited_and_the_order_can_be_asked_for(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        more_plans(console, 2, saving=lambda n: (5.0, 50.0)[n], seen=lambda n: (-20, -3)[n])
        for sort, order in (("impact", ["/ok/plan1001", "/ok/plan0001", "/ok/plan1000"]), ("age", ["/ok/plan1000", "/ok/plan1001", "/ok/plan0001"]),
                            ("risk", ["/ok/plan1001", "/ok/plan0001", "/ok/plan1000"]), ("nonsense", ["/ok/plan1001", "/ok/plan0001", "/ok/plan1000"])):
            with self.subTest(sort=sort):
                reply = console.get("/", query={"sort": sort})
                self.assertEqual(decisions(reply, "ready"), order)
                self.assertEqual(decisions(reply, "look"), ["/ok/plan0002"], "the finding of the machine is a lane of its own")
        links = {a.text(): a for a in console.get("/").main.find("div", class_="seg").find_all("a")}
        self.assertEqual(list(links), ["Impact", "Age", "Risk"])
        self.assertEqual([name for name, a in links.items() if "aria-current" in a.attrs], ["Impact"])
        self.assertEqual(links["Age"].attrs["href"], "/?sort=age")
        self.assertEqual([name for name, a in {a.text(): a for a in console.get("/", query={"sort": "age"}).main.find("div", class_="seg").find_all("a")}.items()
                          if "aria-current" in a.attrs], ["Age"])
        self.assertIsNone(seeded().get("/").main.find("div", class_="seg"), "one decision needs no order")

    def test_a_request_that_the_person_put_off_goes_to_the_end_of_its_lane_and_says_so(self):
        console = seeded()
        more_plans(console, 1, saving=lambda n: 1.0)
        console.store.decision_put(make_decision(plan_id="plan0001", decision="later"))
        reply = console.get("/")
        self.assertEqual(decisions(reply, "ready"), ["/ok/plan1000", "/ok/plan0001"])
        (row,) = rows(reply, "ready")
        self.assertEqual(chips(row), ["Medium risk", "High confidence", "You chose to decide later"])
        self.assertNotIn("You chose to decide later", chips(lane(reply, "ready").find("article")))

    def test_a_request_of_advice_says_that_its_saving_is_a_scenario_when_azure_advisor_is_the_only_basis(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        (row,) = rows(console.get("/"), "look")
        self.assertEqual(spans(row.find("span", class_="impact save")), ["Saves, Scenario", "$1,440 a year", "$120.00 a month"])
        self.assertIn("Based on Azure Advisor's own estimate: no cost line of this resource backs it.", row.text())
        self.assertEqual(row.find("span", class_="t").text(), "Consider changing the virtual machine oversized-vm-1")

    def test_what_a_finding_costs_is_shown_when_nothing_says_what_a_change_would_save_and_nothing_is_ever_no_figure(self):
        console = Console()
        for n, cost in enumerate((3.0, 0.0, None)):
            rid = f"/subscriptions/{SUB}/resourceGroups/rg-{n}/providers/Microsoft.Compute/disks/d{n}"
            console.store.case_put(make_advice_case(case_id=f"case8{n:03d}", resource_id=rid, resource_name=f"d{n}", resource_type="microsoft.compute/disks", resource_group=f"rg-{n}",
                                                    saving_usd_month=None, cost_usd_30d=cost, plan_id=f"plan8{n:03d}", recommendation=f"r{n}"))
            console.store.plan_put(make_advice(plan_id=f"plan8{n:03d}", case_id=f"case8{n:03d}", resource_id=rid, resource_name=f"d{n}", resource_group=f"rg-{n}", saving_usd_month=None))
        reply = console.get("/")
        found = {row.find("span", class_="t").text(): spans(row.find("span", class_="impact cost") or row.find("span", class_="impact none")) for row in rows(reply, "look")}
        self.assertEqual(found, {"Review the disk d0": ["Costs, saving not measured", "$36 a year", "$3.00 a month"],
                                 "Review the disk d1": ["Cost not visible", "—", "No cost line in the last 30 days."],
                                 "Review the disk d2": ["Cost not visible", "—", "No cost line was read yet."]})
        self.assertNotIn("No figure", reply.content)

    def test_money_is_in_dollars_a_year_is_twelve_months_and_nothing_is_called_saved_before_cost_management_measured_it(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        content = console.get("/").content
        self.assertIn("Money is in US dollars, and a year is twelve times the month.", content)
        self.assertNotRegex(content, r"\bsaved\b|\bUSD\b|€|£|No figure|Talk to a person")

    def test_a_person_who_is_not_named_sees_nothing_to_answer_and_a_plan_that_is_not_open_or_has_expired_is_not_listed(self):
        console = seeded()
        for who in (MAYA, OWNER, OPS):
            with self.subTest(who=who):
                reply = console.get("/", oid=who)
                self.assertIn("Nothing waits for you.", reply.content)
                self.assertEqual(reply.main.find_all("section"), [])
        for changes in (dict(state="approved"), dict(state="declined"), dict(state="expired"), dict(expires_at=at(minutes=-1)), dict(expires_at="not a time")):
            with self.subTest(changes=changes):
                console.store.plan_put(make_plan(**changes))
                self.assertIn("Nothing waits for you.", console.get("/").content)

    def test_when_nothing_waits_one_sentence_says_so_and_when_the_next_search_is(self):
        console = Console()
        self.assertIn("Nothing waits for you. The next search is tomorrow at 06:30.", console.get("/").content)
        console.now = NOW.replace(hour=4)
        self.assertIn("Nothing waits for you. The next search is at 06:30.", console.get("/").content)
        self.assertIn("Nothing was decided yet.", console.get("/").content)

    def test_the_time_of_the_next_search_is_the_one_of_the_daily_timer(self):
        source = (APP_ROOT / "function_app.py").read_text(encoding="utf-8")
        second, minute, hour, *_ = re.search(r'TIMER_SCHEDULE = "([^"]+)"', source).group(1).split()
        self.assertEqual((second, core.WATCH_AT), ("0", (int(hour), int(minute))), "the page says when the timer of function_app.py runs, in UTC")

    def test_twelve_rows_of_a_lane_are_shown_and_all_of_them_on_request(self):
        console = seeded()
        more_plans(console, 13)
        reply = console.get("/")
        self.assertEqual(len(decisions(reply, "ready")), 12, "the decision in focus and eleven rows")
        self.assertIn("2 more wait. Show all.", reply.content)
        self.assertIn("/?sort=impact&all=1", reply.links())
        everything = console.get("/", query={"all": "1"})
        self.assertEqual(len(decisions(everything, "ready")), 14)
        self.assertNotIn("more wait", everything.content)

    def test_findings_of_one_kind_about_one_resource_each_are_one_row_that_opens_with_a_request_for_each(self):
        console = Console()
        storage(console, 3)
        reply = console.get("/")
        (row,) = rows(reply, "look")
        group = row.find("details")
        self.assertEqual(group.classes(), ["grp"])
        summary = group.find("summary")
        self.assertEqual(summary.find("span", class_="t").text(), "3 storage accounts in 3 resource groups")
        self.assertEqual(spans(summary.find("span", class_="impact cost")), ["Costs, saving not measured", "$144 a year", "$12.00 a month"])
        self.assertEqual(reply.table("members-plan5002").rows, [{"Resource": "st2", "Resource group": "rg-2", "A month": "$5.00", "Request": "Review: st2"},
                                                               {"Resource": "st1", "Resource group": "rg-1", "A month": "$4.00", "Request": "Review: st1"},
                                                               {"Resource": "st0", "Resource group": "rg-0", "A month": "$3.00", "Request": "Review: st0"}])
        self.assertEqual([a.attrs["href"] for a in group.find_all("a")], ["/ok/plan5002", "/ok/plan5001", "/ok/plan5000"], "a request for each: nothing answers three at once")
        self.assertNotIn("Review all", reply.content)

    def test_findings_of_one_kind_that_all_have_a_saving_are_one_row_with_the_sum_and_the_weakest_level_and_no_confidence_chip(self):
        console = Console()
        storage(console, 2, saving=lambda n: 10.0 + n)
        (row,) = rows(console.get("/"), "look")
        self.assertEqual(spans(row.find("span", class_="impact save")), ["Saves, Scenario", "$252 a year", "$21.00 a month"])
        self.assertIn("Based on the figures of each, added up.", row.text())
        self.assertEqual(chips(row), ["Low risk"])

    def test_findings_of_another_kind_a_single_finding_and_a_change_are_not_consolidated(self):
        console = seeded()
        storage(console, 1)
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        more_plans(console, 2)
        reply = console.get("/")
        self.assertEqual(len(rows(reply, "look")), 2)
        self.assertEqual(reply.main.find_all("details", class_="grp"), [])
        self.assertEqual(len(decisions(reply, "ready")), 3, "each change is a decision of its own")

    def test_a_finding_that_stands_for_many_resources_is_one_row_with_one_request_for_all_of_them(self):
        console = Console()
        endpoints(console)
        reply = console.get("/")
        (row,) = rows(reply, "look")
        self.assertEqual(row.find("span", class_="t").text(), "50 private endpoints in 8 resource groups")
        self.assertEqual(spans(row.find("span", class_="impact cost")), ["Costs, saving not measured", "$4,297 a year", "$358.11 a month"])
        self.assertEqual([(a.text(), a.attrs["href"]) for a in row.find_all("a")], [("Review all 50", "/ok/plan6000")])
        self.assertEqual([r["Resource"] for r in reply.table("members-plan6000").rows], ["pe-1", "pe-2", "pe-3", "pe-4", "pe-5"])
        self.assertIn("45 more. All 50 are in 8 resource groups.", row.text())
        self.assertEqual(row.find("svg", class_="sp none").attrs["aria-label"], f"No daily costs yet: {figures.WHEN_JUDGED}", "a finding of an earlier search kept no ids: its series is read after it is judged again")
        case = console.store.case_get("case6000")
        console.store.case_put(replace(case, facts={**case.facts, GROUP_FACT: {**case.facts[GROUP_FACT], "resourceIds": ["/subscriptions/x/resourcegroups/g/providers/p.q/t/n"]}}))
        (row,) = rows(console.get("/"), "look")
        self.assertEqual(row.find("svg", class_="sp none").attrs["aria-label"], f"No daily costs yet: {figures.READ_LATER}")

    def test_the_summary_adds_up_what_is_known_what_is_under_review_and_what_cost_management_measured(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        storage(console, 3)
        reply = console.get("/")
        tiles = {tile.find("p", class_="k").text(): (tile.find("p", class_="v").text(), tile.find("p", class_="n").text(), "good" in tile.classes())
                 for tile in reply.main.find("ul", class_="kpis").find_all("li")}
        self.assertEqual(tiles, {"Ready to save": ("$1,526 a year", "2 decisions · Scenario, Expected. The basis is in each row.", True),
                                 "Cost under review": ("$144 a year", "1 decision · saving not measured. Cost Management, 30 days.", False),
                                 "Saving measured": ("—", "Nothing measured yet. Cost lines arrive 8 to 72 hours after a change.", False)})
        self.assertIn("3 decisions. $1,526 a year is ready to save, and $144 a year more is under review.", reply.content)
        console.store.plan_put(make_plan(plan_id="plan0009", case_id="case0009", state="consumed"))
        console.store.action_put(make_action(plan_id="plan0009", case_id="case0009", state="verified", verified_at=at(hours=-1), verification={"gone": True, "costBeforeUsd30d": 30.0, "costAfterUsd": 0.0}))
        measured = console.get("/").main.find("ul", class_="kpis").find_all("li")[2]
        self.assertEqual((measured.find("p", class_="v").text(), measured.find("p", class_="n").text()), ("$360 a year", "$30.00 a month, confirmed by Cost Management after 1 change."))

    def test_a_decision_in_focus_has_a_chart_of_its_cost_and_a_row_a_small_one_from_the_series_that_the_watch_stored(self):
        console = seeded()
        more_plans(console, 1, saving=lambda n: 1.0)
        for case_id, series in (("case0001", [4.0] * 29 + [4.67]), ("case1000", [0.0] * 15 + [1.0] * 15)):
            console.store.case_put(replace(console.store.case_get(case_id), cost_series=series, cost_series_end="2026-11-04"))
        reply = console.get("/")
        focus = reply.main.find("article", class_="focus")
        chart = focus.find("figure", class_="chart")
        self.assertEqual(chart.find("figcaption").text(), "Cost per day last 30 days, yesterday $4.67")
        self.assertEqual(chart.find("svg").attrs["aria-label"], "Cost per day for the last 30 days: from $4.00 to $4.67 a day, $4.67 on the last day.")
        (row,) = rows(reply, "ready")
        self.assertEqual(row.find("svg", class_="sp").attrs["aria-label"], "Cost per day, last 30 days: from $0.00 to $1.00 a day, $1.00 on the last day.")
        self.assertNotIn("No daily costs yet", reply.content)

    def test_a_series_that_is_not_what_it_should_be_is_no_chart_and_says_that_the_next_search_reads_it(self):
        console = seeded()
        for series in ([4.0], [-1.0] * 30, "not a list", [float("nan")] * 30):
            with self.subTest(series=str(series)[:20]):
                console.store.case_put(replace(console.store.case_get("case0001"), cost_series=series))
                content = console.get("/").content
                self.assertIn("no daily costs yet", content)
                self.assertIn("The next search reads them. The chart fills in then.", content)

    def test_a_row_that_opens_has_the_sum_of_the_series_of_its_requests_and_none_when_one_is_missing(self):
        console = Console()
        storage(console, 2)
        for n in range(2):
            console.store.case_put(replace(console.store.case_get(f"case5{n:03d}"), cost_series=[1.0 + n] * 30, cost_series_end="2026-11-04"))
        (row,) = rows(console.get("/"), "look")
        self.assertEqual(row.find("svg", class_="sp").attrs["aria-label"], "Cost per day, last 30 days: flat at about $3.00 a day.")
        console.store.case_put(replace(console.store.case_get("case5001"), cost_series=None))
        (row,) = rows(console.get("/"), "look")
        self.assertIn("No daily costs yet", row.text())

    def test_what_comes_from_the_estate_or_from_a_model_is_escaped_in_a_title_a_row_and_a_table(self):
        console = Console()
        storage(console, 2)
        console.store.case_put(make_advice_case(case_id="case9000", resource_name=XSS, plan_id="plan9000"))
        console.store.plan_put(make_advice(plan_id="plan9000", case_id="case9000", resource_name=XSS, title=f"Look at the virtual machine {XSS} in group team-apps-rg", saving_usd_month=None))
        console.store.case_put(make_advice_case(case_id="case9001", resource_name=XSS, resource_group=XSS, plan_id="plan9001", summary=XSS))
        console.store.plan_put(make_advice(plan_id="plan9001", case_id="case9001", resource_name=XSS, resource_group=XSS, title=f"Look at the virtual machine {XSS} in group {XSS}", approvers=(TINO,)))
        reply = console.get("/")
        self.assertEqual(reply.problems, [])
        for gone in ("<script", "<img", "onerror=alert(2)>"):
            self.assertNotIn(gone, reply.text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", reply.text)

    def held(self, console: Console, count: int, **changes) -> None:
        """`count` findings of the investigation that need a person and that no request waits for."""
        for n in range(count):
            fields = dict(case_id=f"case3{n:03d}", resource_id=f"{VM_ID}-{n}", resource_name=f"endpoint-{n}", plan_id=None)
            fields.update(changes)
            console.store.case_put(make_advice_case(**fields))

    def test_findings_that_no_request_waits_for_are_counted_in_one_sentence_so_that_nothing_is_dropped_silently(self):
        console = seeded()
        self.assertNotIn("Held back", console.get("/").content, "none is held")
        self.held(console, 3)
        reply = console.get("/")
        self.assertIn("Held back: 3 findings", reply.content)
        self.assertIn("No measurement backs them yet, or the places for requests are full. The AIs look at them again at the next investigation.", reply.content)
        self.assertEqual(len(decisions(reply, "ready")), 1, "they are not rows: nobody has to decide them")
        self.held(console, 1, case_id="case3900", resource_id=f"{VM_ID}-x", resource_name="endpoint-x")
        self.assertIn("Held back: 4 findings", console.get("/").content)

    def test_one_finding_is_said_in_the_singular_and_the_sentence_is_there_when_nothing_waits(self):
        console = Console()
        self.held(console, 1)
        content = console.get("/").content
        self.assertIn("Nothing waits for you. The next search is tomorrow at 06:30.", content)
        self.assertIn("Held back: 1 finding No measurement backs it yet, or the places for requests are full. The AIs look at it again at the next investigation.", content)

    def test_a_finding_with_a_request_an_answered_one_a_finding_of_another_detector_and_one_that_is_over_are_not_held(self):
        console = seeded()
        self.held(console, 1, case_id="case3001", status="expired")
        self.held(console, 1, case_id="case3002", resource_id=f"{VM_ID}-b", detector="orphan-managed-disk")
        self.held(console, 1, case_id="case3003", resource_id=f"{VM_ID}-c", plan_id="plan3003")
        console.store.plan_put(make_advice(plan_id="plan3003", case_id="case3003", resource_id=f"{VM_ID}-c"))
        self.assertNotIn("Held back", console.get("/").content)
        self.held(console, 1, case_id="case3004", resource_id=f"{VM_ID}-d")
        console.store.plan_put(make_advice(plan_id="plan3004", case_id="case3004", resource_id=f"{VM_ID}-d", state="declined", created_at=at(days=-2)))
        self.assertNotIn("Held back", console.get("/").content, "a person answered it lately: nobody is to be asked again")

    def test_a_store_that_cannot_be_read_says_nothing_of_the_held_findings_and_the_page_is_there(self):
        console = Console(store=FailingStore(fail={"cases_recent"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/")
        self.assertEqual(reply.status, 200)
        self.assertNotIn("Held back", reply.content)
        self.assertIn("Ready to decide", reply.headings(2))

    def test_the_last_five_decisions_are_one_line_each_newest_first(self):
        console = seeded()
        for n in range(7):
            console.store.plan_put(make_plan(plan_id=f"plan2{n:03d}", case_id=f"case2{n:03d}", resource_name=f"gone-{n}", state="declined"))
            console.store.decision_put(make_decision(plan_id=f"plan2{n:03d}", decision="decline", at=at(hours=-n - 1)))
        reply = console.get("/")
        listing = [spans(li) for li in reply.main.find("ul", class_="recent").find_all("li")]
        self.assertEqual(listing, [["Declined", f"Delete the unattached disk gone-{n} in group meternaut-test-rg: Declined", "Tino, Thu 5 Nov"] for n in range(5)])

    def test_an_advice_that_nobody_answered_is_no_row_of_recently_decided_and_a_change_that_nobody_answered_is(self):
        console = seeded()
        for n in range(6):
            console.store.case_put(make_advice_case(case_id=f"case4{n:03d}", resource_id=f"{VM_ID}-e{n}", resource_name=f"endpoint-e{n}", plan_id=f"plan4{n:03d}"))
            console.store.plan_put(make_advice(plan_id=f"plan4{n:03d}", case_id=f"case4{n:03d}", resource_id=f"{VM_ID}-e{n}", state="expired", created_at=at(days=-6), expires_at=at(days=-1)))
        console.store.plan_put(make_plan(plan_id="plan0005", case_id="case0005", state="expired", created_at=at(days=-6), expires_at=at(days=-2)))
        listing = [li.text() for li in console.get("/").main.find("ul", class_="recent").find_all("li")]
        self.assertEqual(len(listing), 1, "six advices that expired are not rows, and the change that expired is")
        self.assertIn("Expired", listing[0])
        self.assertNotIn("oversized-vm-1", listing[0])

    def test_what_moved_to_the_page_of_the_platform_team_is_not_on_the_start_page(self):
        reply = seeded().get("/")
        for gone in ("What Meternaut can change in Azure", "State of each switch", "The kill switch", "Latest runs", "Latest cases", "Needs a person"):
            self.assertNotIn(gone, reply.content)
        for table in ("switches", "latest-runs", "latest-cases", "needs-ok"):
            self.assertFalse(reply.has_table(table))

    def test_a_part_that_cannot_be_read_says_so_and_the_rest_of_the_page_is_there(self):
        for failing, notice, kept in (("plans_open", "I cannot read the open requests now.", "Recently decided"), ("plans_recent", "I cannot read the recent decisions now.", "Ready to decide")):
            with self.subTest(failing=failing):
                console = Console(store=FailingStore(fail={failing}, clock=lambda: NOW))
                console.seed()
                reply = console.get("/")
                self.assertEqual(reply.status, 200)
                self.assertIn(notice, reply.content)
                self.assertIn(kept, reply.content)
                self.assertEqual(reply.problems, [])

    def test_the_page_only_shows_and_changes_nothing(self):
        console = seeded()
        before = snapshot(console.store)
        console.get("/")
        console.get("/", query={"all": "1"})
        console.get("/", query={"sort": "age"})
        self.assertEqual(snapshot(console.store), before)


class TheNavigation(unittest.TestCase):
    def names(self, who, path="/"):
        reply = seeded().get(path, oid=who)
        return [a.text() for a in reply.root.find("nav").find_all("a")]

    def test_each_person_sees_the_pages_that_the_role_allows(self):
        self.assertEqual(self.names(TINO), NAV_ALL)
        self.assertEqual(self.names(MAYA), NAV_ALL[:3])
        self.assertEqual(self.names(OWNER), NAV_ALL[:3])
        self.assertEqual(self.names(OPS), NAV_ALL, "the role ops sees Operations")

    def test_the_page_that_is_open_is_marked(self):
        console = seeded()
        for path, name in (("/", "Decisions"), ("/history", "History"), ("/me/decisions", "History"), ("/me/activity", "History"), ("/me/settings", "Settings"),
                           ("/me/notes", "Settings"), ("/ops", "Operations"), ("/ops/runs", "Operations"), ("/ops/permissions", "Operations"), ("/ops/pause", "Operations")):
            with self.subTest(path=path):
                reply = console.get(path)
                current = [a.text() for a in reply.root.find("nav").find_all("a") if a.attrs.get("aria-current") == "page"]
                self.assertEqual(current, [name])

    def test_the_header_names_the_person_and_the_roles(self):
        self.assertIn("Signed in as Maya. Roles: approver.", seeded().get("/", oid=MAYA).content)


class TheBriefOfACase(unittest.TestCase):
    """The page of a case, `/why/<case>`: the same decision brief as the page of its request."""

    def setUp(self):
        self.console = seeded()
        self.reply = self.console.get("/why/case0001")

    def test_it_is_the_brief_of_the_case_with_its_form_for_a_person_who_may_answer(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), [TITLE])
        self.assertEqual(self.reply.headings(2)[:5], ["If you approve", "What was measured", "Why the AIs think so", "Whose is it", "Your answer"])
        self.assertEqual([f.action for f in self.reply.forms()], ["/ok/plan0001"])

    def test_a_person_who_is_not_named_reads_the_brief_and_cannot_answer_and_sees_nobody_elses_decisions(self):
        self.console.store.decision_put(make_decision(decision="ask", note="TINO-PRIVATE-QUESTION"))
        reply = self.console.get("/why/case0001", oid=OWNER)
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), [TITLE])
        self.assertEqual(reply.forms(), [])
        self.assertIn("Only the people who are named for this request can answer it.", reply.content)
        self.assertNotIn("TINO-PRIVATE-QUESTION", reply.text)

    def test_a_case_without_a_request_has_no_form_and_says_that_no_request_is_open(self):
        console = Console()
        console.seed(plan=False)
        reply = console.get("/why/case0001")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Consider deleting the disk planted-disk-1"])
        self.assertEqual(reply.forms(), [])
        self.assertNotIn("Your answer", reply.headings(2))
        self.assertIn("No request is open for this finding. Nothing changes in Azure.", reply.content)
        self.assertIn("Whose is it", reply.headings(2))

    def test_the_guards_that_fired_are_a_fact_and_are_explained_in_the_details(self):
        self.assertIn("Locks and keep tags", self.reply.measured())
        self.assertIn("No guard fired.", self.reply.content)
        self.console.store.case_put(make_case(guards=("locked", "keep-tag", "too-new", "managed-group", "unverified", "something-else"), status="needs_human", plan_id=None))
        reply = self.console.get("/why/case0001")
        self.assertIn("Held back by", reply.measured())
        self.assertIn("A management lock covers the resource.", reply.measured()["Held back by"][0])
        self.assertIn("How sure: Low.", reply.content)
        (disclosure,) = reply.main.find_all("details")
        self.assertIn("A management lock covers the resource.", disclosure.text())
        self.assertIn("A guard could not be read, so it counts as on.", disclosure.text())
        self.assertIn("no model can lift it", disclosure.text())

    def test_the_second_ai_that_was_not_asked_or_has_no_objection_says_so(self):
        self.console.store.case_put(make_case(status="dropped", recommendation="keep", models={"detective": "model-detective-x", "skeptic": None}, objections=(), plan_id=None))
        self.assertIn("The second AI was not asked.", self.console.get("/why/case0001").content)
        self.console.store.case_put(make_case(objections=()))
        self.assertIn("The second AI raised no objection.", self.console.get("/why/case0001").content)

    def test_a_case_that_ended_in_an_error_shows_its_reason_as_a_note_of_meternaut_and_not_as_ai_text(self):
        self.console.store.case_put(make_case(status="error", recommendation=None, confidence=None, summary="the token budget of the run was reached", objections=(), models={},
                                              plan_id=None))
        reply = self.console.get("/why/case0001")
        self.assertIn("Why the finding ended", reply.headings(3))
        self.assertEqual([p.text() for p in reply.main.find_all("p", class_="quote-label")], ["Recorded by Meternaut"])
        self.assertNotIn("The AI's reasoning", reply.content)
        self.assertIn("the token budget of the run was reached", reply.content)

    def test_the_details_hold_the_steps_the_typed_facts_and_what_the_ais_wrote_in_full(self):
        (disclosure,) = self.reply.main.find_all("details")
        self.assertEqual(self.reply.table("steps").rows, [
            {"Step": "evidence", "Model": "none", "Tokens in": "none", "Tokens out": "none", "Milliseconds": "3", "Result": "ok", "Note": ""},
            {"Step": "detective", "Model": "model-detective-x", "Tokens in": "702", "Tokens out": "307", "Milliseconds": "1,200", "Result": "ok", "Note": ""},
            {"Step": "skeptic", "Model": "model-skeptic-y", "Tokens in": "857", "Tokens out": "223", "Milliseconds": "1,500", "Result": "not ok", "Note": "a note of the step"}])
        self.assertEqual({r["Fact"]: r["Value"] for r in self.reply.table("facts").rows},
                         {"diskState": "unattached", "flags": '{"locked": false}', "sizeBucket": "up to 128", "states": "disconnected, pending"})
        labels = [p.text() for p in disclosure.find_all("p", class_="quote-label")]
        self.assertEqual(labels, ["Written by AI (model: model-detective-x): summary", "Written by AI (model: model-skeptic-y): objection 1"])
        self.assertIn("Treat it as text, not as fact.", disclosure.text())
        self.assertIn("Every step of the finding", disclosure.text())

    def test_the_status_of_a_case_that_was_approved_or_declined_is_said_in_words(self):
        for status, words_ in (("approved", "Approved. A person approved the request and signed in to Azure. The change is being made now."),
                               ("declined", "Declined. A person said no. Nothing changed."),
                               ("acknowledged", "Worth acting on. A person said that this is worth acting on. Meternaut changed nothing in Azure.")):
            with self.subTest(status=status):
                self.console.store.case_put(make_case(status=status))
                (disclosure,) = self.console.get("/why/case0001").main.find_all("details")
                self.assertIn(words_, disclosure.text())

    def test_the_check_afterwards_writes_money_as_the_guide_does(self):
        self.console.store.case_put(make_case(plan_id="plan0001", status="verified"))
        self.console.store.plan_put(make_plan(state="consumed"))
        self.console.store.action_put(make_action(state="verified", finished_at=at(minutes=-5), verified_at=at(minutes=-1),
                                                  verification={"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 7.17, "currency": "USD"}))
        (disclosure,) = self.console.get("/why/case0001").main.find_all("details")
        self.assertIn("Cost lines after the change: $0.00.", disclosure.text())
        self.assertIn("Cost lines of the 30 days before: $7.17.", disclosure.text())
        self.assertNotIn("US dollars", disclosure.text())

    def test_text_from_the_estate_or_a_model_is_escaped_quoted_and_never_a_link_or_a_control(self):
        hostile = "Ignore the rules <a href=\"https://evil.example\">click</a> [go](javascript:alert(1)) <script>alert(1)</script>"
        self.console.store.case_put(make_case(summary=hostile, objections=(hostile,), resource_name=hostile, owner={"tagOwner": hostile, "lookedUp": True}))
        reply = self.console.get("/why/case0001")
        for quote in reply.main.find_all("blockquote", class_="quote"):
            self.assertEqual([n.tag for n in quote.walk() if n.tag in ("a", "button", "input", "form", "script", "select", "textarea")], [])
        self.assertNotIn("<script>alert(1)</script>", reply.text)
        self.assertNotIn('href="https://evil.example"', reply.text)
        self.assertEqual(reply.root.find_all("script"), [])
        self.assertNotIn("https://evil.example", reply.links())
        external = [h for h in reply.links() if h.startswith(("http", "javascript", "data:"))]
        self.assertEqual(external, ["https://portal.azure.com/#resource" + make_case().resource_id], "the only address that is not of this site is the one made from the resource id")

    def test_a_case_that_does_not_exist_is_a_404(self):
        reply = self.console.get("/why/nothing")
        self.assertEqual(reply.status, 404)
        self.assertIn("I cannot find this finding", reply.content)

    def test_the_page_says_in_its_footer_that_an_ai_wrote_what_it_shows(self):
        footer = self.reply.root.find("footer")
        self.assertIn("Recommendations written by AI. A person approves every change.", footer.text())
        self.assertIn("Models: model-detective-x, model-skeptic-y.", footer.text())


INVESTIGATED = dict(
    case_id="case0100", detector="investigation", recommendation="change", confidence=0.85, saving_usd_month=None, cost_usd_30d=41.5,
    summary="The size is larger than the use needs.", objections=("It may be a standby.",), guards=(),
    models={"investigator": "model-investigator-x", "skeptic": "model-skeptic-y"},
    steps=({"step": "investigator", "model": "model-investigator-x", "promptTokens": 4100, "completionTokens": 900, "ms": 61000, "ok": True, "note": "12 tool calls"},
           {"step": "skeptic", "model": "model-skeptic-y", "promptTokens": 1500, "completionTokens": 200, "ms": 9000, "ok": True, "note": None}),
    facts={"basis": "oversized", "proposal": "change", "metrics": {"MetricA": 40}, "costUsd30d": 41.5, "finding": 1}, plan_id=None)


class TheBriefOfAnInvestigation(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.console.store.case_put(make_case(**INVESTIGATED))
        self.reply = self.console.get("/why/case0100")

    def test_it_says_what_the_investigation_found_in_the_words_of_its_basis_and_what_the_tools_measured(self):
        self.assertEqual(self.reply.status, 200)
        facts = {name: value for name, (value, _) in self.reply.measured().items()}
        self.assertEqual(list(facts)[:3], ["Cost, last 30 days", "MetricA", "What the investigation found"])
        self.assertTrue(facts["MetricA"].startswith("40 in the period measured"), facts["MetricA"])
        self.assertTrue(facts["What the investigation found"].startswith("Larger than its use needs"))
        self.assertIn("Azure Monitor", self.reply.measured()["MetricA"][1])

    def test_the_headline_says_consider_changing_and_the_page_says_how_sure_it_is(self):
        self.assertEqual(self.reply.headings(1), ["Consider changing the disk planted-disk-1"])
        self.assertIn("How sure: ", self.reply.content)

    def test_the_two_agents_words_are_in_labelled_boxes_and_in_full_in_the_details(self):
        labels = [p.text() for p in self.reply.main.find_all("p", class_="quote-label")]
        self.assertEqual(labels[:2], ["The AI's reasoning (not checked by code)", "The second AI's doubt"])
        self.assertIn("Written by AI (model: model-investigator-x): summary", labels)
        self.assertIn("Written by AI (model: model-skeptic-y): objection 1", labels)

    def test_its_steps_are_the_two_runs_of_the_agents(self):
        self.assertEqual(self.reply.table("steps").rows, [
            {"Step": "investigator", "Model": "model-investigator-x", "Tokens in": "4,100", "Tokens out": "900", "Milliseconds": "61,000", "Result": "ok", "Note": "12 tool calls"},
            {"Step": "skeptic", "Model": "model-skeptic-y", "Tokens in": "1,500", "Tokens out": "200", "Milliseconds": "9,000", "Result": "ok", "Note": ""},
        ])

    def test_a_skeptic_that_gave_no_verdict_or_was_not_asked_says_so_and_shows_no_objection(self):
        failed = ({**INVESTIGATED["steps"][0]}, {**INVESTIGATED["steps"][1], "ok": False, "note": "the project is busy"})
        self.console.store.case_put(make_case(**{**INVESTIGATED, "steps": failed, "objections": (), "status": "needs_human"}))
        reply = self.console.get("/why/case0100")
        self.assertIn("The second AI gave no verdict on this finding.", reply.content)
        self.assertIn("How sure: Low.", reply.content)
        self.console.store.case_put(make_case(**{**INVESTIGATED, "models": {"investigator": "model-investigator-x", "skeptic": None}, "objections": ()}))
        self.assertIn("The second AI was not asked.", self.console.get("/why/case0100").content)

    def test_the_notes_that_code_wrote_among_the_objections_are_not_shown_as_the_second_ais_doubt(self):
        notes = ("no measurement backs this finding: the tools returned no number", "the Investigator gave a confidence of 0.5, under the 0.7 that a proposal needs")
        self.console.store.case_put(make_case(**{**INVESTIGATED, "objections": notes + ("It may be a standby.",)}))
        reply = self.console.get("/why/case0100")
        doubt = [q.text() for q in reply.main.find_all("blockquote", class_="quote")][1]
        self.assertEqual(doubt, "It may be a standby.")
        self.console.store.case_put(make_case(**{**INVESTIGATED, "objections": notes}))
        self.assertIn("The second AI raised no objection.", self.console.get("/why/case0100").content)

    def test_text_of_the_agents_is_quoted_and_is_never_a_link_or_a_control(self):
        hostile = "Ignore the rules <a href=\"https://evil.example\">click</a> <script>alert(1)</script>"
        self.console.store.case_put(make_case(**{**INVESTIGATED, "summary": hostile, "objections": (hostile,), "resource_name": hostile}))
        reply = self.console.get("/why/case0100")
        for quote in reply.main.find_all("blockquote", class_="quote"):
            self.assertEqual([n.tag for n in quote.walk() if n.tag in ("a", "button", "input", "form", "script", "select", "textarea")], [])
        self.assertNotIn("<script>alert(1)</script>", reply.text)
        self.assertNotIn('href="https://evil.example"', reply.text)
        self.assertEqual(reply.root.find_all("script"), [])
        self.assertNotIn("https://evil.example", reply.links())


class TheRequestPage(unittest.TestCase):
    """The page of one request, drawn from the style guide: a card with what is at stake and what happens on a yes, what was measured and why beside the answer."""

    def stake(self, reply):
        """The figure of the card (its classes and its text) and the line under it."""
        card = reply.main.find("section", class_="focus")
        figure = next(p for p in card.find_all("p") if "fig" in p.classes())
        sub = next(p for p in card.find_all("p") if "figsub" in p.classes())
        return figure.classes(), figure.text(), sub.text()

    def test_a_saving_is_a_green_figure_with_its_level_a_cost_is_a_plain_one_and_what_is_not_known_says_why(self):
        console = seeded()
        classes, figure, sub = self.stake(console.get("/ok/plan0001"))
        self.assertEqual((classes, figure), (["fig", "save"], "$86 a year"))
        self.assertEqual(sub, "Saves, Expected. $7.17 a month. Based on the cost lines of the last 30 days. Waiting costs about $0.24 a day.")
        storage(console, 1, cost=lambda n: 358.11)
        classes, figure, sub = self.stake(console.get("/ok/plan5000"))
        self.assertEqual((classes, figure), (["fig"], "$4,297 a year"))
        self.assertEqual(sub, "Costs, saving not measured. $358.11 a month. The most that a change could save: what it would save was not worked out.")
        storage(console, 1, cost=lambda n: None)
        classes, figure, sub = self.stake(console.get("/ok/plan5000"))
        self.assertEqual((classes, figure, sub), (["fig"], "—", "Cost not visible. No cost line was read yet."))
        storage(console, 1, cost=lambda n: 0.0)
        self.assertEqual(self.stake(console.get("/ok/plan5000"))[2], "Cost not visible. No cost line in the last 30 days.")

    def test_a_reason_of_the_findings_own_takes_the_place_of_the_general_one(self):
        console = seeded()
        console.store.plan_put(make_plan(family="change-disk-tier", saving_usd_month=None, waiting_costs_usd_day=None))
        console.store.case_put(replace(console.store.case_get("case0001"), saving_usd_month=None, cost_usd_30d=80.0))
        sub = self.stake(console.get("/ok/plan0001"))[2]
        self.assertEqual(sub, "Costs, saving not measured. $80.00 a month. The price of a disk depends on its size and its type, and Meternaut does not read the price list, so it claims no figure "
                              "for this change.")
        storage(console, 1, cost=lambda n: 80.0)
        self.assertNotIn("price list", self.stake(console.get("/ok/plan5000"))[2], "the general reason is the line of the figure, not a sentence of its own")

    def test_the_card_draws_the_stored_daily_cost_and_a_request_without_one_says_why(self):
        console = seeded()
        self.assertIn("The next search reads them. The chart fills in then.", console.get("/ok/plan0001").content)
        console.store.case_put(replace(console.store.case_get("case0001"), cost_series=[1.0, 2.0, 3.0] + [4.0] * 27, cost_series_end="2026-11-04"))
        reply = console.get("/ok/plan0001")
        (chart,) = [n for n in reply.main.find_all("figure") if "chart" in n.classes()]
        self.assertEqual(chart.find("figcaption").text(), "Cost per day last 30 days, yesterday $4.00")
        self.assertIn("Cost per day for the last 30 days", chart.find("svg").attrs["aria-label"])
        self.assertNotIn("The chart fills in then.", reply.content)

    def test_a_request_for_many_resources_is_titled_by_their_number_and_says_when_its_chart_is_read(self):
        console = seeded()
        endpoints(console)
        reply = console.get("/ok/plan6000")
        self.assertEqual(reply.headings(1), ["50 private endpoints in 8 resource groups"])
        self.assertEqual(self.stake(reply)[1], "$4,297 a year")
        self.assertIn("They are read when the AIs judge this finding again. The chart fills in then.", reply.content)

    def test_the_answer_stands_beside_what_was_measured_and_a_page_that_takes_no_answer_has_one_column(self):
        reply = seeded().get("/ok/plan0001")
        (cols,) = reply.main.find_all("div", class_="cols")
        self.assertEqual([child.tag for child in cols.children if hasattr(child, "tag")], ["div", "section"])
        (panel,) = [s for s in cols.find_all("section") if s.classes() == ["panel"]]
        self.assertEqual(panel.find("h2").text(), "Your answer")
        self.assertEqual(len(panel.find_all("form")), 1)
        closed = seeded()
        closed.store.plan_put(make_plan(state="declined"))
        reply = closed.get("/ok/plan0001")
        self.assertEqual(len(reply.main.find_all("div", class_="cols solo")), 1)
        self.assertEqual(reply.main.find_all("section", class_="panel"), [])

    def test_a_person_who_may_not_answer_is_told_so_in_the_place_of_the_answer(self):
        reply = seeded().get("/why/case0001", oid=OWNER)
        self.assertEqual(reply.status, 200)
        panel = reply.main.find("section", class_="panel")
        self.assertEqual(panel.text(), "Your answer Only the people who are named for this request can answer it.")
        self.assertEqual(reply.forms(), [])

    def test_the_way_back_is_a_link_to_the_decisions_and_a_case_without_a_request_names_what_it_would_change(self):
        reply = seeded().get("/ok/plan0001")
        self.assertEqual([a.text() for a in reply.main.find_all("a") if a.attrs.get("href") == "/"], ["Back to the decisions"])
        console = Console()
        console.seed(plan=False)
        info = console.get("/why/case0001")
        self.assertEqual(info.headings(2)[0], "What changes")
        self.assertEqual(list(info.facts()), ["What changes"])
        self.assertEqual(info.facts()["What changes"], "No request is open for this finding. Nothing changes in Azure.")

    def test_advice_says_what_an_answer_does_and_has_a_chip_that_it_changes_nothing(self):
        console = seeded()
        storage(console, 1, cost=lambda n: 80.0)
        reply = console.get("/ok/plan5000")
        self.assertEqual(reply.headings(2)[0], "If you answer")
        self.assertIn("Changes nothing in Azure", reply.main.find("p", class_="chips").text())
        self.assertEqual([text for _, _, text in reply.forms()[0].buttons], ["Worth acting on", "Not worth it", "This is not mine", "Ask or tell", "Decide later"])


class TheHistory(unittest.TestCase):
    """"What happened": a feed of the last 30 days, a line for each thing, grouped by day, newest first."""

    def setUp(self):
        self.console = seeded()
        store = self.console.store
        store.plan_put(make_plan(state="declined"))
        store.decision_put(make_decision(decision="decline", reason="handled", at=at(days=-1)))
        store.case_put(make_case(case_id="case0004", first_seen_at=at(days=-1), resource_name="b", plan_id="plan0004"))
        store.plan_put(make_plan(plan_id="plan0004", case_id="case0004", state="consumed", created_at=at(days=-4), expires_at=at(days=-1)))
        store.decision_put(make_decision(plan_id="plan0004", at=at(days=-3, hours=-1)))
        store.action_put(make_action(plan_id="plan0004", case_id="case0004", state="verified", finished_at=at(days=-3), verified_at=at(days=-1, hours=-2),
                                     result="Deleted. Azure no longer lists the resource.", verification={"gone": True, "note": "Cost lines show no cost."}))
        store.plan_put(make_plan(plan_id="plan0005", case_id="case0005", state="expired", created_at=at(days=-6), expires_at=at(days=-2)))
        store.case_put(make_advice_case())
        store.plan_put(make_advice(state="consumed", created_at=at(days=-2)))
        store.decision_put(make_decision(plan_id="plan0002", decision="approve", at=at(days=-2, hours=-1)))
        self.reply = self.console.get("/history")

    def feed(self, reply):
        """The lines of each day, newest day first: for each line the chip, the main part and the quiet part (empty when the line has none)."""
        lists = [[tuple((spans(li) + ["", ""])[:3]) for li in ul.find_all("li")] for ul in reply.main.find_all("ul", class_="recent")]
        return dict(zip(reply.headings(2), lists))

    def test_it_is_a_feed_grouped_by_day_newest_first(self):
        self.assertEqual(self.reply.headings(1), ["What happened"])
        self.assertEqual(self.reply.headings(2), ["Wed 4 Nov", "Tue 3 Nov", "Mon 2 Nov"])
        self.assertEqual(self.reply.root.find_all("table"), [], "no run table and no case table: they are on the Operations page")

    def test_each_line_is_a_chip_a_title_and_one_quiet_part_that_says_who_why_or_what_came_of_it(self):
        feed = self.feed(self.reply)
        self.assertEqual(feed["Wed 4 Nov"], [
            ("Declined", TITLE, "Tino · reason: it is already handled"),
            ("Search", "1 new finding", ""),
            ("Checked", TITLE, "Cost lines show no cost.")])
        self.assertEqual(feed["Tue 3 Nov"], [("Expired", TITLE, "Nobody answered in time."),
                                              ("Worth acting on", "Consider changing the virtual machine oversized-vm-1", "Tino")])
        self.assertIn(("Change made", TITLE, "Deleted. Azure no longer lists the resource."), feed["Mon 2 Nov"])
        self.assertIn(("Approved", TITLE, "Tino"), feed["Mon 2 Nov"])

    def test_a_chip_is_a_word_and_a_shape_and_every_kind_of_line_has_one(self):
        for chip_ in self.reply.main.find_all("span", class_="chip") + self.reply.main.find_all("span", class_="chip low") + self.reply.main.find_all("span", class_="chip info"):
            self.assertEqual(len(chip_.find_all("svg")), 1, "a shape beside the word")
            self.assertEqual(chip_.find("svg").attrs.get("aria-hidden"), "true")
        self.assertEqual(set(history.DECISIONS) - set(history.KINDS), set())
        self.assertTrue(all(label and kind in ("", "low", "mid", "high", "info") and shape in figures.SHAPES for label, kind, shape in history.KINDS.values()))

    def test_three_tiles_count_the_decisions_the_changes_and_the_findings_and_no_money(self):
        (tiles,) = self.reply.main.find_all("ul", class_="kpis")
        self.assertEqual(tiles.attrs["aria-label"], "The last 30 days")
        found = [(li.find("p", class_="k").text(), li.find("p", class_="v").text(), li.find("p", class_="n").text()) for li in tiles.find_all("li")]
        self.assertEqual(found, [("Decisions", "3", "Answers on the requests that you may answer, in the last 30 days."),
                                 ("Changes made", "1", "Made in Azure on those requests, with the approver's own rights."),
                                 ("New findings", "3", "Found by the search in the last 30 days.")])
        self.assertNotIn("$", tiles.text(), "Meternaut is not a cost report (rule 25): the tiles count things and add up no money")

    def tiles_of(self, reply):
        (tiles,) = reply.main.find_all("ul", class_="kpis")
        return {li.find("p", class_="k").text(): (li.find("p", class_="v").text(), li.find("p", class_="n").text()) for li in tiles.find_all("li")}

    def test_a_count_that_rests_on_a_read_that_failed_is_a_dash_and_the_others_are_still_counted(self):
        exact = self.tiles_of(self.reply)
        for failing, dashed in (("plans_recent", {"Decisions", "Changes made"}), ("actions_recent", {"Changes made"}), ("decisions_of_plan", {"Decisions"}),
                                ("cases_recent", {"New findings"})):
            with self.subTest(failing=failing), mock.patch.object(self.console.store, failing, side_effect=StoreError("the store is down", 503)):
                reply = self.console.get("/history")
                self.assertEqual(reply.status, 200)
                self.assertIn("cannot be read", reply.content)
                for name, tile in self.tiles_of(reply).items():
                    self.assertEqual(tile, ("—", "Cannot be read now.") if name in dashed else exact[name], name)

    def test_a_count_that_the_page_reads_only_in_part_is_at_least_that_many_and_says_so(self):
        exact = self.tiles_of(self.reply)
        store = self.console.store
        for n in range(history.PLANS_READ + 5):
            store.plan_put(make_plan(plan_id=f"plan7{n:03d}", case_id=f"case7{n:03d}", state="consumed", created_at=at(days=-1, minutes=-n), expires_at=at(days=1)))
            store.decision_put(make_decision(plan_id=f"plan7{n:03d}", at=at(days=-1, minutes=-n)))
        tiles = self.tiles_of(self.console.get("/history"))
        for name in ("Decisions", "Changes made"):
            self.assertRegex(tiles[name][0], r"^\d+\+$", name)
            self.assertEqual(tiles[name][1], "At least this many: the page reads only the latest records.")
        self.assertEqual(tiles["New findings"], exact["New findings"], "the findings are read in full")

    def test_a_store_that_holds_more_plans_than_the_page_asks_for_makes_the_counts_at_least_and_so_do_more_findings(self):
        store = self.console.store
        for n in range(history.PLANS_ASKED):
            store.plan_put(make_plan(plan_id=f"plan8{n:03d}", case_id=f"case8{n:03d}", state="declined", approvers=("someone-else",), created_at=at(days=-1, minutes=-n)))
        tiles = self.tiles_of(self.console.get("/history"))
        self.assertRegex(tiles["Decisions"][0], r"^\d+\+$")
        for n in range(history.CASES_ASKED):
            store.case_put(make_case(case_id=f"case9{n:04d}", first_seen_at=at(days=-2), updated_at=at(minutes=-n - 1), plan_id=None))
        self.assertRegex(self.tiles_of(self.console.get("/history"))["New findings"][0], r"^\d+\+$")

    def test_a_history_with_nothing_in_it_has_no_tiles(self):
        reply = Console().get("/history")
        self.assertEqual(reply.main.find_all("ul", class_="kpis"), [])
        self.assertIn("Nothing has happened in the last 30 days.", reply.content)

    def test_the_count_of_the_advice_that_nobody_answered_is_not_cut_and_does_not_take_the_places_of_the_other_plans(self):
        store = self.console.store
        for n in range(49):
            store.case_put(make_advice_case(case_id=f"case6{n:03d}", resource_id=f"{VM_ID}-k{n}", resource_name=f"endpoint-k{n}", plan_id=f"plan6{n:03d}"))
            store.plan_put(make_advice(plan_id=f"plan6{n:03d}", case_id=f"case6{n:03d}", resource_id=f"{VM_ID}-k{n}", state="expired", created_at=at(days=-1, hours=-1), expires_at=at(days=-1)))
        feed = self.feed(self.console.get("/history"))
        self.assertIn(("Closed", "49 requests to look at a finding", "Closed with no answer."), feed["Wed 4 Nov"])
        self.assertIn(("Declined", TITLE, "Tino · reason: it is already handled"), feed["Wed 4 Nov"], "the decisions of the other plans are still there")

    def test_a_line_that_names_a_request_links_to_its_page(self):
        self.assertIn("/ok/plan0001", self.reply.links())
        self.assertIn("/ok/plan0002", self.reply.links())

    def test_advice_that_nobody_answered_is_one_line_for_each_day_and_a_change_that_nobody_answered_is_a_line_of_its_own(self):
        store = self.console.store
        for n in range(3):
            store.case_put(make_advice_case(case_id=f"case5{n:03d}", resource_id=f"{VM_ID}-h{n}", resource_name=f"endpoint-h{n}", plan_id=f"plan5{n:03d}"))
            store.plan_put(make_advice(plan_id=f"plan5{n:03d}", case_id=f"case5{n:03d}", resource_id=f"{VM_ID}-h{n}", state="expired", created_at=at(days=-3), expires_at=at(days=-1, hours=-n)))
        feed = self.feed(self.console.get("/history"))
        self.assertEqual(feed["Tue 3 Nov"][0], ("Expired", TITLE, "Nobody answered in time."), "the change that expired is a line of its own")
        self.assertIn(("Closed", "3 requests to look at a finding", "Closed with no answer."), feed["Wed 4 Nov"])
        self.assertFalse([line for lines in feed.values() for line in lines if line[0] == "Expired" and line[1].startswith("Consider")], feed)

    def test_the_old_addresses_of_my_decisions_and_what_i_did_here_answer_with_the_same_page(self):
        for path in ("/me/decisions", "/me/activity"):
            with self.subTest(path=path):
                reply = self.console.get(path)
                self.assertEqual((reply.status, reply.headings(1)), (200, ["What happened"]))
                self.assertEqual(self.feed(reply), self.feed(self.reply))

    def test_a_person_who_is_not_named_sees_the_number_of_findings_and_none_of_the_decisions(self):
        reply = self.console.get("/history", oid=MAYA)
        lines = [line for lines_ in self.feed(reply).values() for line in lines_]
        self.assertTrue(lines)
        for chip_, what, quiet in lines:
            self.assertEqual(chip_, "Search")
            self.assertRegex(what, r"^\d+ new findings?$")
            self.assertEqual(quiet, "")
        (tiles,) = reply.main.find_all("ul", class_="kpis")
        self.assertEqual([li.find("p", class_="v").text() for li in tiles.find_all("li")][:2], ["0", "0"])

    def test_an_empty_history_says_so(self):
        reply = Console().get("/history")
        self.assertIn("Nothing has happened in the last 30 days.", reply.content)

    def test_what_is_older_than_30_days_is_not_in_the_feed(self):
        console = Console()
        console.store.plan_put(make_plan(created_at=at(days=-40), expires_at=at(days=-37)))
        console.store.decision_put(make_decision(at=at(days=-38), decision="decline"))
        console.store.case_put(make_case(first_seen_at=at(days=-35)))
        self.assertIn("Nothing has happened in the last 30 days.", console.get("/history").content)

    def test_the_page_is_not_a_cost_report(self):
        for gone in ("cost report", "Cost, last 30 days", "per month in total", "Total"):
            self.assertNotIn(gone, self.reply.content)

    def test_a_store_that_cannot_be_read_is_said_plainly(self):
        console = Console(store=FailingStore(fail={"plans_recent"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/history")
        self.assertEqual(reply.status, 200)
        self.assertIn("The history cannot be read", reply.content)


class Times(unittest.TestCase):
    def setUp(self):
        self.console = seeded()

    def zone(self, name, offset_hours, label):
        return mock.patch.object(core, "zone_of", return_value=dt.timezone(dt.timedelta(hours=offset_hours), label))

    def test_a_time_is_shown_in_utc_and_in_the_persons_zone_with_its_name(self):
        with self.zone("America/New_York", -5, "EST"):
            reply = self.console.get("/ok/plan0001")
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (03:00 EST)", reply.content)

    def test_a_zone_on_another_day_names_the_day(self):
        self.console.store.plan_put(make_plan(expires_at="2026-11-08T20:30:00Z"))
        with self.zone("Asia/Tokyo", 9, "JST"):
            reply = self.console.get("/ok/plan0001")
        self.assertIn("Sun 8 Nov 2026 20:30 UTC (Mon 9 Nov 2026 05:30 JST)", reply.content)

    def test_utc_and_a_zone_that_is_not_known_show_utc_alone(self):
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="UTC"))
        reply = self.console.get("/ok/plan0001")
        self.assertTrue(opens(reply).endswith("open until Sun 8 Nov 2026 08:00 UTC"), opens(reply))
        self.assertNotIn("UTC (", reply.content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="Mars/Olympus_Mons"))
        self.assertTrue(opens(self.console.get("/ok/plan0001")).endswith("open until Sun 8 Nov 2026 08:00 UTC"))
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="../../etc/passwd"))
        self.assertTrue(opens(self.console.get("/ok/plan0001")).endswith("open until Sun 8 Nov 2026 08:00 UTC"))

    def test_a_person_whose_settings_cannot_be_read_still_gets_the_page_in_utc(self):
        console = Console(store=FailingStore(fail={"settings_get"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/ok/plan0001")
        self.assertEqual(reply.status, 200)
        self.assertTrue(opens(reply).endswith("open until Sun 8 Nov 2026 08:00 UTC"), opens(reply))

    def test_a_time_that_is_not_a_time_is_shown_as_it_is_stored_and_escaped(self):
        self.console.store.plan_put(make_plan(expires_at="<b>soon</b>"))
        reply = self.console.get("/ok/plan0001")
        self.assertEqual(reply.status, 200)
        self.assertNotIn("<b>soon</b>", reply.text)
        self.assertNotIn("<b>", reply.text)

    def test_the_time_zone_database_of_the_machine_is_used_when_it_has_the_zone(self):
        try:
            import zoneinfo
            zoneinfo.ZoneInfo("Europe/Amsterdam")
        except Exception:  # noqa: BLE001
            self.skipTest("this machine has no time zone database")
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (09:00 CET)", self.console.get("/ok/plan0001").content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="America/New_York"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (03:00 EST)", self.console.get("/ok/plan0001").content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="Australia/Sydney"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (19:00 AEDT)", self.console.get("/ok/plan0001").content)

    def test_without_a_time_zone_database_a_short_list_of_names_is_accepted_and_times_stay_in_utc(self):
        core.zone_index.cache_clear()
        try:
            with mock.patch.object(core.zoneinfo, "available_timezones", return_value=set()), mock.patch.object(core.zoneinfo, "ZoneInfo", side_effect=KeyError("no database")):
                self.assertEqual(core.canonical_zone("europe/amsterdam"), "Europe/Amsterdam")
                self.assertEqual(core.canonical_zone("UTC"), "UTC")
                self.assertIsNone(core.canonical_zone("Mars/Olympus_Mons"))
                self.assertIsNone(core.canonical_zone("Europe"))
                self.assertIsNone(core.zone_of("Europe/Amsterdam"))
                self.assertTrue(opens(self.console.get("/ok/plan0001")).endswith("open until Sun 8 Nov 2026 08:00 UTC"))
        finally:
            core.zone_index.cache_clear()

    def test_the_names_are_taken_from_the_database_with_its_spelling(self):
        core.zone_index.cache_clear()
        with mock.patch.object(core.zoneinfo, "available_timezones", return_value={"Europe/Amsterdam", "UTC"}):
            try:
                self.assertEqual(core.canonical_zone("EUROPE/amsterdam"), "Europe/Amsterdam")
                self.assertIsNone(core.canonical_zone("Europe/Berlin"))
            finally:
                core.zone_index.cache_clear()


if __name__ == "__main__":
    unittest.main()
