"""The data that a workspace takes in and nothing reads (cases/unread.py): the analysis of what the tools recorded, its way into the facts of a case and the figure of its plan, and what a person
sees of it on the page, in the letters and on the card. Every name, id and number in it is INVENTED.

The first class holds the analysis alone. The others run the real investigation with a fake Foundry: first over a record of the shape that the tools keep (the harness of test_investigate),
then over the real tools and a fake estate (deep_estate), so that the shape that the tools record is the shape that the analysis reads.
"""
import dataclasses
import json
import math
import re
import unittest

import support  # noqa: F401  (it puts the app on the path)
from deep_estate import MACHINE, RULES, WORKSPACE as WORKSPACE_TYPE, WS, deep
from test_investigate import FakeFoundry, FakeToolbox, Harness, Moving, answer, entry, finding, resource
from test_letters import BASE, CONTACTS, MOST_WORDS, PERSON, word_count
from test_toolbox import ask, row, toolbox
from test_web_support import NOW as WEB_NOW, Console

from cases import agents, brief, cards, deeper, letters, unread
from cases.approvals import ADVICE_MIN_USD, why_not_ask
from cases.decide import NO_MEASUREMENT
from cases.foundry import AgentRun
from cases.models import ADVISE, CaseRecord

HOSTILE_TABLE = "<script>alert(1)</script>\"'><img src=x onerror=alert(2)> " + "long" * 60
OPTION_WORDS = ("diagnostic setting", "data collection rule", "transformation", "Basic or Auxiliary plan")


def measured(total, days=30, unit="GB"):
    """A measurement as the toolbox keeps it in its evidence."""
    return {"total": total, "max": None, "average": None, "days": days, "days_with_data": 1 if total is not None else 0, "unit": unit, "totals": [total]}


def record(volumes, readers=None, runs=None, **more) -> dict:
    """The evidence of a workspace: `volumes` the billable GB of each kind, `readers` and `runs` what reads it (None for a count that is not known). The whole volume that the read of the volume
    reported is what the kinds add up to, unless a test says another with `volume=`: the tools record it with the rows, and a share is over it."""
    metrics = {f"Billable GB {kind}": measured(gb) for kind, gb in volumes.items()}
    metrics.update({f"Readers {kind}": measured(count, unit=None) for kind, count in (readers or {}).items()})
    metrics.update({f"Runs {kind}": measured(count, unit=None) for kind, count in (runs or {}).items()})
    more.setdefault("volume", {"billable_gb": round(sum(volumes.values()), 3), "days": 30, "tables": len(volumes)})
    return {"type": unread.WORKSPACE, "metrics": metrics, **more}


# Five kinds of data: four that nothing reads and one that a rule and some people read. 118.4 GB in all, of which 88.4 GB are read by nothing: 74.66 percent.
VOLUMES = {"AzureDiagnostics": 40.2, "ContainerLogV2": 22.0, "t1": 13.7, "Syslog": 12.5, "Perf": 30.0}
READERS = {"AzureDiagnostics": 0, "ContainerLogV2": 0, "t1": 0, "Syslog": 0, "Perf": 3}
RUNS = {"AzureDiagnostics": 0, "ContainerLogV2": 0, "t1": 0, "Syslog": 0, "Perf": 5}
COST = 95.9
SAVING = 71.6  # 95.9 times 88.4 over 118.4, to the cent


def evidence_of(**changes) -> dict:
    return record(VOLUMES, READERS, RUNS, volume={"billable_gb": 118.4, "days": 30, "tables": 5}, **changes)


class TheAnalysis(unittest.TestCase):
    def test_what_nothing_reads_is_the_kinds_with_a_reader_count_of_nothing_and_the_figure_is_the_cost_in_proportion_to_their_volume(self):
        found = unread.analyse(evidence_of(), COST, {"t1": "AppLog_CL"})
        self.assertEqual({key: found[key] for key in ("days", "billableGb", "unreadGb", "share", "runsRecorded", "more", "unknown", "costUsd30d", "savingUsd")},
                         {"days": 30, "billableGb": 118.4, "unreadGb": 88.4, "share": 0.7466, "runsRecorded": True, "more": 0, "unknown": 0, "costUsd30d": 95.9, "savingUsd": SAVING})
        self.assertEqual([(k["kind"], k["gb"], k["share"], k["runs"]) for k in found["kinds"]],
                         [("AzureDiagnostics", 40.2, 0.3395, 0), ("ContainerLogV2", 22.0, 0.1858, 0), ("t1", 13.7, 0.1157, 0), ("Syslog", 12.5, 0.1056, 0)], "the largest first; Perf is read")
        self.assertEqual(found["kinds"][2]["name"], "AppLog_CL", "a handle of the run is given the name of its table")
        self.assertNotIn("name", found["kinds"][0])
        json.dumps(found)

    def test_the_figure_is_rounded_to_the_cent_and_is_never_above_the_cost(self):
        found = unread.analyse(record({"A": 2.0, "B": 1.0}, {"A": 0, "B": 4}), 95.9)
        self.assertEqual((found["share"], found["savingUsd"]), (0.6667, 63.93))
        everything = unread.analyse(record({"A": 2.0, "B": 1.0}, {"A": 0, "B": 0}), 33.33)
        self.assertEqual((everything["share"], everything["savingUsd"]), (1.0, 33.33), "all of it is the whole cost and not a cent more")
        for cost in (0.01, 0.37, 33.33, 95.9, 1234.56, 99999.99):
            for part in (0.001, 0.3333333, 0.5, 0.999999, 1.0):
                with self.subTest(cost=cost, part=part):
                    found = unread.analyse(record({"A": part * 100, "B": (1 - part) * 100 + 1e-9}, {"A": 0, "B": 1}), cost)
                    self.assertLessEqual(found.get("savingUsd", 0), cost)

    def test_rows_that_add_up_to_more_than_the_whole_volume_that_the_tool_reported_are_not_of_one_read_and_make_no_figure(self):
        found = unread.analyse(record({"A": 100.0}, {"A": 0}, volume={"billable_gb": 10.0, "days": 30, "tables": 1}), 50.0)
        self.assertEqual(found, {"missing": "volume"}, "neither the rows nor the whole volume is believed")
        rounded = unread.analyse(record({"A": 1.0005, "B": 1.0005}, {"A": 0, "B": 0}, volume={"billable_gb": 2.0, "days": 30, "tables": 2}), 50.0)
        self.assertEqual((rounded["share"], rounded["unreadGb"], rounded["billableGb"], rounded["savingUsd"]), (1.0, 2.0, 2.0, 50.0), "rows that were rounded up a little are the whole volume, not more")

    def test_the_whole_volume_that_the_tool_reported_is_what_the_share_is_over_and_the_tail_of_small_kinds_that_the_record_does_not_list_is_in_it(self):
        listed = record({"A": 60.0, "B": 20.0}, {"A": 0, "B": 5})
        found = unread.analyse({**listed, "volume": {"billable_gb": 200.0, "days": 30, "tables": 40}}, 100.0)
        self.assertEqual((found["billableGb"], found["share"], found["savingUsd"]), (200.0, 0.3, 30.0), "the tail of small kinds that the record does not list is in the whole")

    def test_without_a_whole_volume_for_the_days_of_the_rows_there_is_no_figure_and_the_whole_is_never_the_sum_of_the_rows_that_happen_to_be_there(self):
        listed = record({"A": 60.0, "B": 20.0}, {"A": 0, "B": 5})
        for label, volume in (("none", None), ("empty", {}), ("text", "text"), ("not a number", {"billable_gb": "many", "days": 30}), ("not finite", {"billable_gb": math.nan, "days": 30}),
                              ("no days", {"billable_gb": 200.0}), ("no days either", {"billable_gb": 200.0, "days": 0}), ("negative", {"billable_gb": -1.0, "days": 30}),
                              ("other days than the rows", {"billable_gb": 200.0, "days": 7, "tables": 40})):
            with self.subTest(label):
                self.assertEqual(unread.analyse({**listed, "volume": volume}, 100.0), {"missing": "volume"})
        without = dict(listed)
        del without["volume"]
        self.assertEqual(unread.analyse(without, 100.0), {"missing": "volume"})
        self.assertEqual(unread.analyse({**listed, "volume": {"billable_gb": 0, "days": 30, "tables": 2}}, 100.0), {"missing": "volume"}, "rows that a whole of nothing does not hold")

    def test_a_volume_that_was_read_again_for_other_days_is_the_last_read_as_a_whole_and_the_rows_of_the_first_read_do_not_stay_in_it(self):
        """The tools keep the first tables of every read of the volume: the second read replaces the rows of the tables that it names and leaves the others of the first read where they were."""
        block = record({"A": 120.0, "B": 80.0, "C": 60.0, "D": 20.0, "E": 10.0, "F": 5.0}, {"A": 0, "B": 0, "C": 4, "D": 0, "E": 0, "F": 0}, {kind: 0 for kind in "ABCDEF"},
                       volume={"billable_gb": 300.0, "days": 30, "tables": 6})
        before = unread.analyse(block, 100.0)
        self.assertEqual((before["days"], before["billableGb"], before["unreadGb"], before["share"]), (30, 300.0, 235.0, 0.7833))
        for kind, gb in (("A", 28.0), ("B", 19.0), ("C", 14.0), ("D", 5.0)):
            block["metrics"][f"Billable GB {kind}"] = measured(gb, days=7)
        block["volume"] = {"billable_gb": 70.0, "days": 7, "tables": 6}
        found = unread.analyse(block, 100.0)
        self.assertEqual((found["days"], found["billableGb"], found["unreadGb"], found["share"], found["savingUsd"]), (7, 70.0, 52.0, 0.7429, 74.29))
        self.assertEqual([k["kind"] for k in found["kinds"]], ["A", "B", "D"], "E and F are rows of the first read: of other days, so they are left out and are not taken for all there is")
        self.assertEqual(found["unknown"], 0)
        # The two reads the other way round: the read of 7 days came first and left a row of a table that the read of 30 days that followed does not name.
        block = record({"A": 120.0, "B": 80.0}, {"A": 0, "B": 0, "G": 0}, {"A": 0, "B": 0, "G": 0}, volume={"billable_gb": 300.0, "days": 30, "tables": 6})
        block["metrics"]["Billable GB G"] = measured(40.0, days=7)
        again = unread.analyse(block, 100.0)
        self.assertEqual(([k["kind"] for k in again["kinds"]], again["billableGb"], again["share"]), (["A", "B"], 300.0, 0.6667), "G is a row of 7 days, and the whole is that of 30")

    def test_a_reader_count_that_is_not_a_number_is_unknown_and_never_none(self):
        found = unread.analyse(record({"A": 10.0, "B": 10.0}, {"A": None, "B": 0}, {"A": 0, "B": 0}), 20.0)
        self.assertEqual([k["kind"] for k in found["kinds"]], ["B"])
        self.assertEqual((found["unknown"], found["share"], found["savingUsd"]), (1, 0.5, 10.0), "the kind that could not be checked is in the whole and not in what nothing reads")
        self.assertEqual(unread.analyse(record({"A": 10.0}, {"A": None}, {"A": 0}), 20.0), {"missing": "readers"}, "a run that was counted does not make up for a rule that was not read")
        self.assertIsNone(unread.analyse(record({"A": 10.0}), 20.0), "nothing asked what reads it: the finding is about something else, and there is no claim to check")

    def test_a_kind_that_people_ran_a_query_on_or_that_a_rule_names_is_read(self):
        found = unread.analyse(record({"A": 10.0, "B": 10.0, "C": 10.0}, {"A": 0, "B": 0, "C": 1}, {"A": 2, "B": 0, "C": 0}), 30.0)
        self.assertEqual([k["kind"] for k in found["kinds"]], ["B"])
        self.assertIsNone(unread.analyse(record({"A": 10.0}, {"A": 0}, {"A": 2}), 30.0), "everything is read: there is nothing to say")

    def test_the_record_of_the_runs_is_optional_and_the_digest_says_when_it_is_missing(self):
        found = unread.analyse(record({"A": 10.0, "B": 10.0}, {"A": 0, "B": 0}, {"A": 0}), 20.0)
        self.assertEqual([(k["kind"], k["runs"]) for k in found["kinds"]], [("A", 0), ("B", None)])
        self.assertFalse(found["runsRecorded"])
        self.assertTrue(unread.analyse(record({"A": 10.0}, {"A": 0}, {"A": 0}), 20.0)["runsRecorded"])

    def test_without_the_volume_the_digest_says_that_it_is_missing_and_a_record_without_data_says_nothing(self):
        self.assertEqual(unread.analyse(record({}, {"A": 0}, {"A": 0}), 20.0), {"missing": "volume"})
        for nothing in (None, {}, [], "text", {"metrics": None}, {"metrics": {"Percentage CPU": measured(3.0, unit="Percent")}}, record({"A": 0.0}, {"A": 0})):
            with self.subTest(block=nothing):
                self.assertIsNone(unread.analyse(nothing, 20.0))

    def test_kinds_that_cover_other_days_than_the_volume_that_was_read_are_left_out(self):
        block = record({"A": 10.0, "B": 10.0}, {"A": 0, "B": 0}, volume={"billable_gb": 20.0, "days": 30, "tables": 2})
        block["metrics"]["Billable GB B"]["days"] = 7
        found = unread.analyse(block, 20.0)
        self.assertEqual(([k["kind"] for k in found["kinds"]], found["days"], found["billableGb"], found["share"]), (["A"], 30, 20.0, 0.5))

    def test_a_cost_that_is_not_known_or_not_above_nothing_makes_no_figure_and_the_rows_stay(self):
        for cost in (None, 0.0, -3.0, math.nan):
            with self.subTest(cost=cost):
                found = unread.analyse(evidence_of(), cost)
                self.assertEqual(found["share"], 0.7466)
                self.assertNotIn("savingUsd", found)
                self.assertNotIn("costUsd30d", found)

    def test_six_kinds_are_listed_and_the_rest_are_counted(self):
        kinds = {f"K{n}": float(n) for n in range(1, 10)}
        found = unread.analyse(record(kinds, {kind: 0 for kind in kinds}, {kind: 0 for kind in kinds}), 45.0)
        self.assertEqual([k["kind"] for k in found["kinds"]], ["K9", "K8", "K7", "K6", "K5", "K4"])
        self.assertEqual((found["more"], found["share"], found["savingUsd"]), (3, 1.0, 45.0), "the figure is for all of them, not for the six")

    def test_the_kinds_of_the_writers_are_kept_when_they_look_like_resource_types_and_never_invented(self):
        block = evidence_of(writers={"AzureDiagnostics": ["microsoft.keyvault/vaults", "Key Vault", HOSTILE_TABLE, 5, "microsoft.storage/storageaccounts", "a/b", "x/y"], "Syslog": "text"})
        by_kind = {k["kind"]: k for k in unread.analyse(block, COST)["kinds"]}
        self.assertEqual(by_kind["AzureDiagnostics"]["writers"], ["microsoft.keyvault/vaults", "microsoft.storage/storageaccounts", "a/b"])
        self.assertNotIn("writers", by_kind["Syslog"])
        self.assertNotIn("writers", by_kind["ContainerLogV2"])

    def test_a_name_that_is_not_text_or_is_the_label_again_is_not_kept_and_a_long_one_is_cut(self):
        names = {"t1": "x" * 500, "Syslog": "Syslog", "ContainerLogV2": 5, "AzureDiagnostics": ""}
        by_kind = {k["kind"]: k for k in unread.analyse(evidence_of(), COST, names)["kinds"]}
        self.assertEqual(len(by_kind["t1"]["name"]), unread.MAX_LABEL)
        for kind in ("Syslog", "ContainerLogV2", "AzureDiagnostics"):
            self.assertNotIn("name", by_kind[kind])

    def test_a_record_that_the_tools_would_never_make_makes_no_error_and_no_wrong_number(self):
        metrics = {"Billable GB A": measured(True), "Billable GB B": measured(-5.0), "Billable GB C": measured(math.inf), "Billable GB D": measured("12"), "Billable GB ": measured(9.0),
                   "Billable GB " + "x" * 500: measured(9.0), "Readers A": measured(0), "Readers D": "text", 5: measured(1.0), "Billable GB E": measured(10.0), "Readers E": measured(False)}
        for found in (unread.analyse({"metrics": metrics}, COST), unread.analyse({"metrics": metrics, "volume": {"billable_gb": "many", "days": None}, "writers": [1]}, COST)):
            self.assertEqual(found, {"missing": "volume"}, "no whole volume that is a number")
        self.assertEqual(unread.analyse({"metrics": metrics, "volume": {"billable_gb": 10.0, "days": 30}, "writers": [1]}, COST), {"missing": "readers"})

    def test_it_is_a_pure_function_of_the_record_and_leaves_it_as_it_was(self):
        block = evidence_of()
        before = json.dumps(block, sort_keys=True)
        first = unread.analyse(block, COST, {"t1": "AppLog_CL"})
        self.assertEqual(unread.analyse(block, COST, {"t1": "AppLog_CL"}), first)
        self.assertEqual(json.dumps(block, sort_keys=True), before)


def workspace_toolbox(evidence=None, names=None, **changes):
    """A fake toolbox that has shown one workspace, as the evidence of its tools holds it, and what its table handles stand for."""
    shown = resource(1, resource_type=unread.WORKSPACE, name="ws-demo", resource_group="rg-demo", cost_usd_30d=COST, **changes)
    box = FakeToolbox([shown], {"r1": evidence if evidence is not None else evidence_of()})
    box.table_names = lambda handle: dict(names if names is not None else {"t1": "AppLog_CL"})
    return box


def cited(*kinds, total=0.0) -> list:
    """The measurements that the Investigator copies from what the tools returned for some kinds of data: the volume, the readers and the runs."""
    return [item for kind in kinds for item in (entry("r1", f"Billable GB {kind}", VOLUMES[kind]), entry("r1", f"Readers {kind}", total), entry("r1", f"Runs {kind}", total))]


def finding_about_the_workspace(**changes):
    values = dict(handles=["r1"], basis="other", proposal="change", confidence=0.85, summary="This workspace stores data that nothing reads.", evidence=cited("AzureDiagnostics", "ContainerLogV2"))
    values.update(changes)
    return finding(**values)


def run_investigation(toolbox_, found=None):
    h = Harness(FakeFoundry(answer(found or finding_about_the_workspace())), toolbox_, with_store=True)
    h.go()
    return h


def case_and_plan(h) -> tuple[CaseRecord, object]:
    (case,) = h.store.cases_recent()
    (plan,) = h.store.plans_open()
    return case, plan


def page_of(case, plan) -> tuple[object, str]:
    console = Console()
    console.store.case_put(case)
    console.store.plan_put(plan)
    reply = console.get(f"/ok/{plan.plan_id}")
    return reply, reply.main.text()


def walk_blocks(card) -> list:
    """The TextBlocks of a card that have an id, at any depth (the figure and the footer are in a container or at the end, and a test reads them by id)."""
    found, stack = [], [card]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") == "TextBlock" and "id" in node:
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


class WhatTheInvestigationKeeps(unittest.TestCase):
    def setUp(self):
        self.h = run_investigation(workspace_toolbox())
        self.case, self.plan = case_and_plan(self.h)

    def test_the_facts_of_the_case_hold_the_digest_that_code_worked_out_from_everything_that_the_tools_recorded(self):
        digest = self.case.facts["unread"]
        self.assertEqual((digest["unreadGb"], digest["billableGb"], digest["savingUsd"], digest["costUsd30d"]), (88.4, 118.4, SAVING, COST))
        self.assertEqual([k["kind"] for k in digest["kinds"]], ["AzureDiagnostics", "ContainerLogV2", "t1", "Syslog"], "kinds that the Investigator did not cite are in it too")
        self.assertEqual(digest["kinds"][2]["name"], "AppLog_CL")
        self.assertEqual(sorted(self.case.facts["metrics"]), sorted(item["metric"] for item in cited("AzureDiagnostics", "ContainerLogV2")), "the cited numbers are what they were")

    def test_the_case_has_no_figure_of_its_own_and_a_change_still_has_none_in_the_history(self):
        self.assertEqual((self.case.recommendation, self.case.status, self.case.saving_usd_month), ("change", "proposed", None))
        self.assertEqual([r["monthlySavingUsd"] for r in self.h.of("case.result")], [None])

    def test_the_advise_plan_has_the_figure_and_code_wrote_its_words(self):
        plan = self.plan
        self.assertEqual((plan.family, plan.saving_usd_month, plan.waiting_costs_usd_day), (ADVISE, SAVING, round(SAVING / 30, 2)))
        self.assertEqual(plan.title, "Consider changing the Log Analytics workspace ws-demo in group rg-demo")
        self.assertEqual((plan.what_changes, plan.undo), (brief.ADVICE_CHANGE, brief.ADVICE_UNDO))

    def test_the_brief_says_scenario_and_what_the_figure_is_computed_from(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((b.saving.monthly, b.saving.level), (SAVING, "Scenario"))
        self.assertEqual(b.saving.basis, "the workspace's cost of the last 30 days times the share of its data that nothing reads, about 75 percent")
        self.assertEqual(b.headline, self.plan.title)
        self.assertEqual(b.unread.sentence, "About 75 percent of what this workspace is billed for is data that nothing reads.")
        self.assertEqual(b.unread.volume, "That is 88.4 GB of the 118.4 GB that it took in over 30 days.")
        self.assertEqual([(line.kind, line.gb, line.percent) for line in b.unread.lines],
                         [("AzureDiagnostics", "40.2 GB", "34 percent"), ("ContainerLogV2", "22 GB", "19 percent"), ("AppLog_CL", "13.7 GB", "12 percent"), ("Syslog", "12.5 GB", "11 percent")])
        for line in b.unread.lines:
            self.assertEqual(line.reads, "Read by 0 rules, 0 saved searches and 0 workbooks; 0 queries run")
        self.assertEqual((b.unread.more, b.unread.note), (0, ""))
        self.assertEqual(len(b.options), 3)
        for word in OPTION_WORDS:
            self.assertIn(word, " ".join(option.what for option in b.options))

    def test_the_two_measurements_that_were_cited_are_not_repeated_among_the_facts_when_the_rows_say_more(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW)
        self.assertEqual([fact.label for fact in b.facts], ["Cost, last 30 days", "Locks and keep tags"])

    def test_the_case_page_of_a_finding_that_has_no_request_shows_the_figure_too(self):
        b = brief.build_brief(self.case, None, now=WEB_NOW)
        self.assertEqual((b.kind, b.saving.monthly, b.saving.level), ("info", SAVING, "Scenario"))
        self.assertEqual(b.options, (), "there is no request to answer, so no choices are put")
        self.assertIsNotNone(b.unread)


class WhatAPersonSees(unittest.TestCase):
    def setUp(self):
        self.h = run_investigation(workspace_toolbox())
        self.case, self.plan = case_and_plan(self.h)
        self.reply, self.text = page_of(self.case, self.plan)

    def test_the_page_has_the_type_word_the_figure_the_rows_and_the_choices_in_this_order(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), ["Consider changing the Log Analytics workspace ws-demo"])
        self.assertEqual(self.reply.headings(2), ["If you answer", "What was measured", "What you could do", "Why the AIs think so", "Whose is it", "Your answer"])
        self.assertIn("Data that nothing reads", self.reply.headings(3))
        figure = self.text.index("Saves, Scenario. $71.60 a month.")
        method = self.text.index("About 75 percent of what this workspace is billed for is data that nothing reads. That is 88.4 GB of the 118.4 GB that it took in over 30 days.")
        rows = self.text.index("AzureDiagnostics: 40.2 GB in 30 days, 34 percent of what is billed.")
        choices = self.text.index("What you could do")
        end = self.text.index("Nothing changes in Azure when you answer.", choices)
        self.assertLess(figure, method)
        self.assertLess(method, rows)
        self.assertLess(rows, choices)
        self.assertLess(choices, end)

    def test_every_row_is_a_typed_line_and_a_table_that_is_named_by_a_handle_has_its_name(self):
        items = [li.text() for ul in self.reply.main.find_all("ul") for li in ul.find_all("li") if "of what is billed" in li.text()]
        self.assertEqual(items, ["AzureDiagnostics: 40.2 GB in 30 days, 34 percent of what is billed. Read by 0 rules, 0 saved searches and 0 workbooks; 0 queries run.",
                                 "ContainerLogV2: 22 GB in 30 days, 19 percent of what is billed. Read by 0 rules, 0 saved searches and 0 workbooks; 0 queries run.",
                                 "AppLog_CL: 13.7 GB in 30 days, 12 percent of what is billed. Read by 0 rules, 0 saved searches and 0 workbooks; 0 queries run.",
                                 "Syslog: 12.5 GB in 30 days, 11 percent of what is billed. Read by 0 rules, 0 saved searches and 0 workbooks; 0 queries run."])
        self.assertNotIn(" t1", self.text)

    def test_the_choices_are_in_the_words_of_code_each_with_what_it_puts_at_risk_and_end_in_the_one_sentence(self):
        (choices,) = self.reply.main.find_all("ol")
        parts = [li.text() for li in choices.find_all("li")]
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertEqual(part.count("At risk:"), 1, part)
        self.assertIn("Stop sending AzureDiagnostics, ContainerLogV2, AppLog_CL and 1 more at the source", parts[0])
        self.assertIn("the log categories that a diagnostic setting sends, or the data collection rule that writes it", parts[0])
        self.assertIn("alert rules, workbooks or investigations that need this data get no new data", parts[0])
        self.assertIn("a transformation in the data collection rule", parts[1])
        self.assertIn("move its table to the Basic or Auxiliary plan, if the table supports it, or keep it for less time", parts[2])
        self.assertIn("That lowers the bill by less than the figure above.", parts[2])
        self.assertTrue(self.text[self.text.index("What you could do"):].split("Why the AIs think so")[0].rstrip().endswith("Nothing changes in Azure when you answer."))

    def test_the_choices_name_no_writer_that_the_tools_did_not_show(self):
        self.assertNotIn("largest writers", self.text)
        for invented in ("Key Vault", "Kubernetes", "irtual machine"):
            self.assertNotIn(invented, self.text)

    def test_the_words_of_money_on_the_page_are_those_of_the_style_guide_and_the_page_asks_nothing(self):
        content = self.reply.content.replace("saved searches", "")  # what a workspace holds, not a money word
        self.assertNotRegex(content, r"\b(?:saved|savings|save)\b")
        self.assertEqual(re.findall(r"\bSaves\b[^.]*", content), ["Saves, Scenario"], "a saving is called one only with its level")
        self.assertNotRegex(content, r"[€£]|\bEUR\b|\bUSD\b")
        self.assertNotRegex(content.replace("US dollars", ""), r"\bdollars?\b")
        self.assertNotIn("?", self.text)

    def test_the_details_do_not_say_that_an_ai_saw_what_only_code_worked_out(self):
        facts = {row["Fact"] for row in self.reply.table("facts").rows}
        self.assertEqual(facts, {"basis", "citedMetrics", "costUsd30d", "finding", "metricDays", "metricUnits", "metrics", "proposal"})
        self.assertEqual(sorted(self.case.facts), sorted([*facts, "unread"]), "the case keeps the digest all the same")

    def test_the_page_is_well_formed_and_offers_the_answers_of_every_advice(self):
        self.assertEqual(self.reply.problems, [])
        form = self.reply.form(has_button="Worth acting on")
        self.assertTrue(form.has_button("Not worth it"))

    def test_the_weekly_letter_is_the_decision_letter_when_one_decision_waits_and_has_the_figure_the_method_the_rows_and_the_choices(self):
        letter = letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.case)], CONTACTS)
        self.assertEqual(letter.subject, "[Meternaut] 1 decision waits for you")
        text = letter.text
        self.assertIn("- Consider changing the Log Analytics workspace ws-demo: $859 a year, Scenario.", text)
        self.assertIn("About 75 percent of what this workspace is billed for is data that nothing reads.", text)
        self.assertEqual([line for line in text.splitlines() if line.startswith("- ") and ("GB" in line or "more" in line)],
                         ["- AzureDiagnostics, 40.2 GB (34 percent)", "- ContainerLogV2, 22 GB (19 percent)", "- AppLog_CL, 13.7 GB (12 percent)", "- 1 more"])
        self.assertIn("Options: stop sending it, filter it before it is stored, or use a cheaper plan. Nothing changes in Azure when you answer.", text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["digest"])
        self.assertEqual(len(re.findall(r'href="', letter.html)), 1)

    def test_the_weekly_letter_with_several_decisions_keeps_one_line_for_each_and_the_figure(self):
        other = (dataclasses.replace(self.plan, plan_id="plan-two", case_id="case-two"), dataclasses.replace(self.case, case_id="case-two", recommendation="investigate"))
        letter = letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.case), other], CONTACTS)
        self.assertEqual([line for line in letter.text.splitlines() if line.startswith("- ")],
                         ["- Consider changing the Log Analytics workspace ws-demo: $859 a year, Scenario.", "- Review the Log Analytics workspace ws-demo: $859 a year, Scenario."])
        self.assertNotIn("Options:", letter.text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["digest"])

    def test_findings_of_one_kind_are_one_line_of_the_weekly_letter_as_they_are_one_row_of_the_page(self):
        other = (dataclasses.replace(self.plan, plan_id="plan-two", case_id="case-two"), dataclasses.replace(self.case, case_id="case-two"))
        letter = letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.case), other], CONTACTS)
        self.assertEqual(letter.subject, "[Meternaut] 1 decision waits for you")
        self.assertEqual([line for line in letter.text.splitlines() if line.startswith("- ")], ["- 2 Log Analytics workspaces in 1 resource group: $1,718 a year, Scenario."])
        self.assertEqual(re.findall(r'href="([^"]*)"', letter.html), [f"{BASE}/"], "a row that holds several requests opens on the page: it has no request page of its own")
        self.assertNotIn("Options:", letter.text)

    def test_the_decision_letter_stays_within_the_words_of_a_letter_and_has_what_it_rests_on(self):
        letter = letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS)
        self.assertEqual(letter.subject, "[Meternaut] A decision waits for you")
        self.assertEqual(letter.text.splitlines()[0], "Consider changing the Log Analytics workspace ws-demo", "the title of the page")
        self.assertIn("Log Analytics workspace, resource group rg-demo", letter.text)
        self.assertIn("Low risk, High confidence, Changes nothing in Azure", letter.text)
        self.assertIn("$859 a year\nSaves, Scenario. $71.60 a month.\nMoney is in US dollars, and a year is twelve times the month.", letter.text)
        self.assertNotIn("Based on", letter.text, "the lines that follow say what the figure rests on: the method, the share and the kinds")
        self.assertIn("About 75 percent of what this workspace is billed for is data that nothing reads.", letter.text)
        self.assertIn("- AzureDiagnostics, 40.2 GB (34 percent)", letter.text)
        self.assertIn("Options: stop sending it, filter it before it is stored, or use a cheaper plan.", letter.text)
        self.assertIn("If you answer: Nothing changes in Azure. Your answer is recorded with your name.", letter.text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["approval"])
        self.assertLessEqual(sum(1 for line in letter.text.splitlines() if line.startswith("- ")), letters.MAX_KINDS + 1, "no table of five rows in a letter")
        self.assertTrue(letter.text.isascii())
        for gone in ("?", "!", "saved", "\u2013", "\u2014"):
            self.assertNotIn(gone, letter.text.lower())

    def test_the_card_has_the_rows_and_the_choices_in_one_line_and_passes_the_check_of_cards(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)
        card = cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24))
        texts = {block["id"]: block["text"] for block in walk_blocks(card)}
        self.assertIn("About 75 percent of what this workspace is billed for is data that nothing reads.", texts["unread"])
        self.assertEqual([texts[f"unread-{n}"] for n in (1, 2, 3)], ["AzureDiagnostics, 40.2 GB (34 percent)", "ContainerLogV2, 22 GB (19 percent)", "AppLog\\_CL, 13.7 GB (12 percent)"])
        self.assertEqual(texts["unread-more"], "1 more")
        self.assertIn("Options: stop sending it, filter it before it is stored, or use a cheaper plan.", texts["options"])
        self.assertEqual((texts["value"], texts["saving-word"]), ("$859 a year", "Saves, Scenario. $71.60 a month."))
        self.assertEqual(texts["price-basis"], "Based on the workspace's cost of the last 30 days times the share of its data that nothing reads, about 75 percent.")


class WhenTheRecordIsNotEnough(unittest.TestCase):
    def render(self, evidence, found=None):
        h = run_investigation(workspace_toolbox(evidence), found)
        case, plan = case_and_plan(h)
        _, text = page_of(case, plan)
        return case, plan, text, letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS)

    def test_without_the_volume_there_is_no_saving_and_the_page_the_letter_and_the_card_say_what_is_missing(self):
        case, plan, text, letter = self.render(record({}, READERS, RUNS))
        self.assertEqual(case.facts["unread"], {"missing": "volume"})
        self.assertIsNone(plan.saving_usd_month)
        why = "How much data this workspace takes in was not read, so there is no way to say how much of it nothing reads."
        self.assertIn(f"Costs, saving not measured. $95.90 a month. {why}", text)
        self.assertIn(f"$1,151 a year\nCosts, saving not measured. $95.90 a month. {why}", letter.text)
        self.assertNotIn("No figure", letter.text)
        self.assertNotIn("Data that nothing reads", text)
        self.assertNotIn("What you could do", text)
        weekly = letters.digest_letter(PERSON, BASE, WEB_NOW, [(plan, case)], CONTACTS)
        self.assertIn("- Consider changing the Log Analytics workspace ws-demo: costs $1,151 a year, saving not measured.\n", weekly.text)
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        card = cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}", nonce="n" * 24))
        texts = {block["id"]: block["text"] for block in walk_blocks(card)}
        self.assertEqual((texts["value"], texts["saving-word"], texts["price-basis"]), ("$1,151 a year", "Costs, saving not measured. $95.90 a month.", why))

    def test_a_source_of_readers_that_was_not_read_leaves_no_saving_and_says_so_and_names_no_kind_as_unread(self):
        case, plan, text, letter = self.render(record(VOLUMES, {kind: None for kind in READERS}, RUNS, volume={"billable_gb": 118.4, "days": 30, "tables": 5}))
        self.assertEqual(case.facts["unread"], {"missing": "readers"})
        self.assertIsNone(plan.saving_usd_month)
        why = ("Not everything that reads this workspace's data (its rules, saved searches, workbooks and analytics rules) could be read, so Meternaut cannot say which data nothing reads.")
        self.assertIn(f"Costs, saving not measured. $95.90 a month. {why}", text)
        self.assertIn(f"$1,151 a year\nCosts, saving not measured. $95.90 a month. {why}", letter.text)
        self.assertNotIn("No figure", letter.text)
        self.assertNotIn("What you could do", text)
        self.assertNotIn("AzureDiagnostics: ", text)

    def test_the_why_of_a_missing_figure_fits_a_card(self):
        for why in brief.UNREAD_MISSING.values():
            self.assertLessEqual(len(why), 200, "the tile of the card cuts a reason at 200 characters")

    def test_a_finding_about_a_workspace_whose_record_holds_nothing_about_data_is_as_it_was(self):
        case, plan, text, _ = self.render({"type": unread.WORKSPACE, "metrics": {"Percentage CPU": measured(3.0, unit="Percent")}},
                                          finding_about_the_workspace(evidence=[entry("r1", "Percentage CPU", 3.0)]))
        self.assertNotIn("unread", case.facts)
        self.assertIsNone(plan.saving_usd_month)
        self.assertIn("Costs, saving not measured. $95.90 a month. The most that a change could save: what it would save was not worked out.", text)
        self.assertNotIn("What you could do", text)

    def test_a_workspace_whose_volume_was_read_and_whose_readers_were_never_asked_for_is_about_something_else(self):
        case, plan, text, _ = self.render(record(VOLUMES, volume={"billable_gb": 118.4, "days": 30, "tables": 5}), finding_about_the_workspace(evidence=[entry("r1", "Billable GB Perf", 30.0)]))
        self.assertNotIn("unread", case.facts)
        self.assertIsNone(plan.saving_usd_month)
        self.assertIn("Costs, saving not measured. $95.90 a month. The most that a change could save: what it would save was not worked out.", text)
        self.assertNotIn("What you could do", text)

    def test_a_finding_about_anything_else_gets_no_digest_whatever_its_record_holds(self):
        box = FakeToolbox([resource(1, cost_usd_30d=COST)], {"r1": evidence_of()})
        h = run_investigation(box)
        (case,) = h.store.cases_recent()
        self.assertNotIn("unread", case.facts)
        self.assertIsNone(h.store.plans_open()[0].saving_usd_month)

    def test_the_figure_of_advisor_stays_when_a_finding_has_one_of_its_own_and_the_rows_are_shown_all_the_same(self):
        h = run_investigation(workspace_toolbox({**evidence_of(), "advisor": [{"savingUsdMonth": 12.5}]}))
        case, plan = case_and_plan(h)
        self.assertEqual((case.saving_usd_month, plan.saving_usd_month), (12.5, 12.5))
        b = brief.build_brief(case, plan, now=WEB_NOW)
        self.assertEqual((b.saving.monthly, b.saving.basis), (12.5, "Azure Advisor's own estimate: no cost line of this resource backs it"))
        self.assertIsNotNone(b.unread)


class WhatWasNotCounted(unittest.TestCase):
    """The page says in full what the digest could not count; the card and the letters say it in a few words (the same two caveats), and keep to their limits."""

    VARIANTS = (("the queries", {"runsRecorded": False}, "Not counted: the queries people run."),
                ("what reads other kinds", {"unknown": 3}, "Not counted: what reads 3 other kinds of data."),
                ("one other kind", {"unknown": 1}, "Not counted: what reads 1 other kind of data."),
                ("both", {"runsRecorded": False, "unknown": 3}, "Not counted: what reads 3 other kinds of data and the queries people run."))

    def setUp(self):
        self.case, self.plan = case_and_plan(run_investigation(workspace_toolbox()))

    def variant(self, **changes) -> CaseRecord:
        return dataclasses.replace(self.case, facts={**self.case.facts, "unread": {**self.case.facts["unread"], **changes}})

    def test_when_everything_was_counted_there_is_no_caveat_anywhere(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((b.unread.note, b.unread.caveat), ("", ""))
        card = json.dumps(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24)))
        self.assertNotIn("unread-caveat", card)
        self.assertNotIn("Not counted", letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS).text)

    def test_the_brief_has_the_whole_note_for_the_page_and_the_caveat_for_the_card_and_the_letters(self):
        for label, change, caveat in self.VARIANTS:
            with self.subTest(label):
                b = brief.build_brief(self.variant(**change), self.plan, now=WEB_NOW)
                self.assertEqual(b.unread.caveat, caveat)
                self.assertTrue(b.unread.note)
                self.assertLessEqual(len(b.unread.caveat), 200, "the tile of a card cuts a line at 200 characters")
        self.assertEqual(brief.build_brief(self.variant(runsRecorded=False), self.plan, now=WEB_NOW).unread.note,
                         "The queries that people run were not counted: the record of them is off or could not be read in full.")

    def test_the_page_says_the_whole_note_as_it_did(self):
        for label, change, _ in self.VARIANTS:
            with self.subTest(label):
                case = self.variant(**change)
                _, text = page_of(case, self.plan)
                self.assertIn(brief.build_brief(case, self.plan, now=WEB_NOW).unread.note, text)

    def test_the_decision_letter_carries_the_caveat_and_keeps_to_its_words_and_to_the_biggest_kind(self):
        for label, change, caveat in self.VARIANTS:
            with self.subTest(label):
                letter = letters.approval_letter(self.plan, self.variant(**change), PERSON, BASE, WEB_NOW, CONTACTS)
                self.assertIn(caveat, letter.text)
                self.assertLessEqual(word_count(letter), MOST_WORDS["approval"])
                self.assertIn("- AzureDiagnostics, 40.2 GB (34 percent)", letter.text, "the first kind is always there")
                self.assertIn("About 75 percent of what this workspace is billed for is data that nothing reads.", letter.text)
                self.assertIn("Options: stop sending it, filter it before it is stored, or use a cheaper plan.", letter.text)
                self.assertLessEqual(sum(1 for line in letter.text.splitlines() if line.startswith("- ")), letters.MAX_KINDS + 1)
                self.assertTrue(letter.text.isascii())

    def test_the_decision_letter_gives_up_the_last_kinds_and_then_the_line_that_counts_the_rest_for_the_caveat_and_never_the_caveat(self):
        lines = {label: [line for line in letters.approval_letter(self.plan, self.variant(**change), PERSON, BASE, WEB_NOW, CONTACTS).text.splitlines() if line.startswith("- ")]
                 for label, change, _ in self.VARIANTS}
        self.assertEqual([len(found) for found in lines.values()], [3, 2, 2, 1], "two kinds and the count of the rest; two kinds; two kinds; the first kind alone")
        self.assertEqual(lines["the queries"][-1], "- 2 more")
        self.assertEqual(len([line for line in letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS).text.splitlines() if line.startswith("- ")]), 4,
                         "with nothing to say the letter is as it was: three kinds and the count of the rest")

    def test_the_weekly_letter_has_room_for_all_of_it_and_carries_the_caveat_too(self):
        for label, change, caveat in self.VARIANTS:
            with self.subTest(label):
                letter = letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.variant(**change))], CONTACTS)
                self.assertIn(caveat, letter.text)
                self.assertLessEqual(word_count(letter), MOST_WORDS["digest"])
                self.assertEqual([line for line in letter.text.splitlines() if line.startswith("- ") and "GB" in line],
                                 ["- AzureDiagnostics, 40.2 GB (34 percent)", "- ContainerLogV2, 22 GB (19 percent)", "- AppLog_CL, 13.7 GB (12 percent)"])
                self.assertIn("Nothing changes in Azure when you answer.", letter.text)
        several = letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.variant(runsRecorded=False)), (dataclasses.replace(self.plan, plan_id="p2", case_id="c2"), self.case)], CONTACTS)
        self.assertNotIn("Not counted", several.text, "a letter about several decisions has a line for each and no room for the rows of one")

    def test_the_card_carries_the_caveat_after_the_kinds_and_before_the_choices_and_passes_the_check(self):
        for label, change, caveat in self.VARIANTS:
            with self.subTest(label):
                b = brief.build_brief(self.variant(**change), self.plan, now=WEB_NOW, may_answer=True)
                card = cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24))
                blocks = [block["id"] for block in card["body"] if block.get("type") == "TextBlock"]
                texts = {block["id"]: block["text"] for block in card["body"] if block.get("type") == "TextBlock"}
                self.assertEqual(texts["unread-caveat"], caveat)
                self.assertLess(blocks.index("unread-more"), blocks.index("unread-caveat"))
                self.assertLess(blocks.index("unread-caveat"), blocks.index("options"))

    def test_a_hostile_kind_changes_nothing_about_the_room_of_the_caveat(self):
        h = run_investigation(workspace_toolbox(names={"t1": HOSTILE_TABLE}))
        case, plan = case_and_plan(h)
        case = dataclasses.replace(case, facts={**case.facts, "unread": {**case.facts["unread"], "runsRecorded": False}})
        letter = letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS)
        self.assertIn("Not counted: the queries people run.", letter.text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["approval"])
        self.assertNotIn("<script>", letter.html)


class WhenTheVolumeMovesWhileTheRequestIsOpen(unittest.TestCase):
    """A Watch that judges the case again while its request is open keeps the request (approvals.advise). The figure of the request is the one that it took when it was made: what a person is shown
    is the figure of the digest that the case holds now, the same numbers as the rows."""

    MOVED = {**VOLUMES, "AzureDiagnostics": 20.0}  # 98.2 GB in all, of which 68.2 GB are read by nothing: 69 percent, and 66.60 US dollars of 95.90

    def two_watches(self, cost=COST, volume=98.2):
        clock = Moving()
        first = Harness(FakeFoundry(answer(finding_about_the_workspace())), workspace_toolbox(), with_store=True, clock=clock)
        first.go()
        self.opened = case_and_plan(first)
        clock.advance(days=1)
        moved = record(self.MOVED, READERS, RUNS, volume={"billable_gb": volume, "days": 30, "tables": 5})
        shown = resource(1, resource_type=unread.WORKSPACE, name="ws-demo", resource_group="rg-demo", cost_usd_30d=cost)
        box = FakeToolbox([shown], {"r1": moved})
        box.table_names = lambda handle: {"t1": "AppLog_CL"}
        cites = [entry("r1", "Billable GB AzureDiagnostics", 20.0), entry("r1", "Readers AzureDiagnostics", 0.0), entry("r1", "Runs AzureDiagnostics", 0.0), *cited("ContainerLogV2")]
        second = Harness(FakeFoundry(answer(finding_about_the_workspace(evidence=cites))), box, extras=first.extras, clock=clock)
        second.go()
        self.assertEqual(second.result.cases, 1, "the case is judged again: what it rests on changed")
        (case,) = second.store.cases_recent()
        (plan,) = second.store.plans_open()
        return case, plan

    def test_the_request_keeps_the_figure_that_it_was_made_with_and_what_a_person_is_shown_is_the_figure_of_the_digest(self):
        case, plan = self.two_watches()
        first_case, first_plan = self.opened
        self.assertEqual((plan.plan_id, plan.saving_usd_month, case.case_id), (first_plan.plan_id, SAVING, first_case.case_id), "the same request, with the figure of the day it was made")
        digest = case.facts["unread"]
        self.assertEqual((digest["share"], digest["unreadGb"], digest["billableGb"], digest["savingUsd"]), (0.6945, 68.2, 98.2, 66.6))
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((b.saving.monthly, b.saving.level, b.saving.waiting_per_day), (66.6, "Scenario", round(66.6 / 30, 2)))
        self.assertEqual(b.saving.basis, "the workspace's cost of the last 30 days times the share of its data that nothing reads, about 69 percent")
        self.assertEqual([(line.kind, line.gb, line.percent) for line in b.unread.lines][:2], [("ContainerLogV2", "22 GB", "22 percent"), ("AzureDiagnostics", "20 GB", "20 percent")])
        self.assertEqual(b.unread.sentence, "About 69 percent of what this workspace is billed for is data that nothing reads.")

    def test_the_page_the_letters_and_the_card_show_that_one_figure_and_never_the_old_one_under_the_name_of_another_source(self):
        case, plan = self.two_watches()
        reply, text = page_of(case, plan)
        self.assertIn("Saves, Scenario. $66.60 a month.", text)
        self.assertIn("About 69 percent of what this workspace is billed for is data that nothing reads. That is 68.2 GB of the 98.2 GB that it took in over 30 days.", text)
        self.assertIn("AzureDiagnostics: 20 GB in 30 days, 20 percent of what is billed.", text)
        for gone in ("71.60", "71.6 ", "Azure Advisor", "75 percent"):
            self.assertNotIn(gone, text)
        approval = letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS)
        weekly = letters.digest_letter(PERSON, BASE, WEB_NOW, [(plan, case)], CONTACTS)
        self.assertIn("$799 a year\nSaves, Scenario. $66.60 a month.", approval.text)
        self.assertIn("Consider changing the Log Analytics workspace ws-demo: $799 a year, Scenario.", weekly.text)
        for letter in (approval, weekly):
            self.assertIn("About 69 percent of what this workspace is billed for is data that nothing reads.", letter.text)
            self.assertNotIn("71.60", letter.text)
            self.assertNotIn("$859", letter.text)
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        text_of_card = json.dumps(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}", nonce="n" * 24)))
        self.assertIn("$799 a year", text_of_card)
        self.assertIn("Saves, Scenario. $66.60 a month.", text_of_card)
        self.assertIn("about 69 percent", text_of_card)
        self.assertNotIn("71.60", text_of_card)
        self.assertNotIn("$859", text_of_card)

    def test_a_digest_that_holds_no_figure_now_shows_none_and_says_why_and_the_old_figure_of_the_request_is_not_shown(self):
        case, plan = self.two_watches(cost=0.0)
        self.assertEqual(plan.saving_usd_month, SAVING)
        self.assertNotIn("savingUsd", case.facts["unread"])
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((b.saving.monthly, b.saving.level, b.saving.basis, b.saving.waiting_per_day), (None, "", "", None))
        self.assertEqual(b.saving.why_none, "The resource had no cost in the last 30 days.")
        _, text = page_of(case, plan)
        self.assertIn("Cost not visible. No cost line in the last 30 days.", text)
        self.assertNotIn("71.60", text)
        self.assertIn("AzureDiagnostics: 20 GB in 30 days", text, "the rows are those of the digest all the same")

    def test_the_same_numbers_on_every_render_when_nothing_moved_and_a_request_that_a_digest_has_no_hand_in_is_as_it_was(self):
        h = run_investigation(workspace_toolbox())
        case, plan = case_and_plan(h)
        self.assertEqual(brief.build_brief(case, plan, now=WEB_NOW).saving.monthly, case.facts["unread"]["savingUsd"])
        other = dataclasses.replace(case, facts={k: v for k, v in case.facts.items() if k != "unread"})
        self.assertEqual(brief.build_brief(other, plan, now=WEB_NOW).saving.monthly, SAVING, "a case with no digest shows the figure of its request, as ever")


class WhatAModelCannotDo(unittest.TestCase):
    def test_a_figure_that_the_model_writes_is_cleaned_and_the_figure_is_the_one_that_code_worked_out(self):
        liar = finding_about_the_workspace(summary="Saves $5000 a month, 4000 EUR in a year.", monthlySavingUsd=5000, savingUsd=9999, unread={"savingUsd": 9999.0, "share": 1.0})
        h = run_investigation(workspace_toolbox(), liar)
        case, plan = case_and_plan(h)
        self.assertNotRegex(case.summary, r"5000|4000")
        self.assertIn("[figure removed]", case.summary)
        self.assertEqual((plan.saving_usd_month, case.facts["unread"]["savingUsd"]), (SAVING, SAVING))
        self.assertNotIn("9999", json.dumps(case.facts))
        _, text = page_of(case, plan)
        for invented in ("5000", "4000", "9999"):
            self.assertNotIn(invented, text)

    def test_a_digest_with_a_figure_above_the_cost_is_not_a_figure(self):
        case = self.case(cost_usd_30d=10.0, facts={"unread": {**unread.analyse(evidence_of(), 10.0), "savingUsd": 10.01}})
        self.assertIsNone(brief.unread_saving(case))
        self.assertIsNone(brief.build_brief(case, None, now=WEB_NOW).saving.monthly)
        for cost in (None, 0.0):
            self.assertIsNone(brief.unread_saving(dataclasses.replace(case, cost_usd_30d=cost)))

    def test_a_request_with_no_measurement_is_asked_when_code_worked_out_a_figure_and_not_when_it_cost_little(self):
        case = self.case(cost_usd_30d=ADVICE_MIN_USD - 1, objections=(NO_MEASUREMENT,))
        self.assertIsNotNone(why_not_ask(case))
        held = dataclasses.replace(case, cost_usd_30d=30.0, facts={"unread": unread.analyse(evidence_of(), 30.0)})
        self.assertIsNone(why_not_ask(held), "the figure that code worked out is something to decide with")

    @staticmethod
    def case(**changes) -> CaseRecord:
        values = dict(case_id="c", resource_id=WS, resource_name="ws-demo", resource_type=unread.WORKSPACE, resource_group="rg-demo", subscription_id="s", detector="investigation",
                      run_id="r", status="needs_human", recommendation="change")
        values.update(changes)
        return CaseRecord(**values)


class WhatATableNameCanDo(unittest.TestCase):
    def setUp(self):
        self.h = run_investigation(workspace_toolbox(names={"t1": HOSTILE_TABLE}))
        self.case, self.plan = case_and_plan(self.h)

    def test_a_hostile_name_is_cut_in_the_brief_and_is_in_no_event_of_the_history(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW)
        line = next(line for line in b.unread.lines if line.kind.startswith("<script>"))
        self.assertLessEqual(len(line.kind), 60)
        self.assertNotIn("\n", line.kind)
        for event in self.h.events:
            self.assertNotIn("<script>", json.dumps(event))

    def test_the_page_escapes_it_and_the_letters_and_the_card_do_too(self):
        reply, _ = page_of(self.case, self.plan)
        self.assertNotIn("<script>", reply.text)
        self.assertNotIn("<img", reply.text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", reply.text)
        self.assertEqual(reply.root.find_all("script"), [])
        self.assertEqual(reply.problems, [])
        for letter in (letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.case)], CONTACTS), letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS)):
            self.assertNotIn("<script>", letter.html)
            self.assertNotIn("<img", letter.html)
            self.assertIn("&lt;script&gt;", letter.html)
            self.assertLessEqual(max(len(line) for line in letter.text.splitlines() if not line.startswith("Decide:")), 400)
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)
        card = cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24))
        self.assertNotIn("<script>", json.dumps(card))

    def test_a_name_that_looks_like_a_link_or_a_heading_is_neither_on_the_page(self):
        h = run_investigation(workspace_toolbox(names={"t1": "[click](https://evil.example/ok) https://evil.example/x\n# heading"}))
        reply, _ = page_of(*case_and_plan(h))
        self.assertFalse([link for link in reply.links() if "evil.example" in link])
        rows = " ".join(li.text() for ul in reply.main.find_all("ul") for li in ul.find_all("li") if "of what is billed" in li.text())
        self.assertIn("evil.example", rows)
        self.assertNotIn("://", rows)
        self.assertNotIn("[", rows)

    def test_a_table_of_the_customer_that_has_no_name_is_called_so_and_not_by_its_handle_alone(self):
        h = run_investigation(workspace_toolbox(names={}))
        b = brief.build_brief(*case_and_plan(h), now=WEB_NOW)
        self.assertIn("custom table t1", [line.kind for line in b.unread.lines])


class WorkspaceAgent(FakeFoundry):
    """An investigator that reads the workspace with the real tools and cites, for each kind of data that nothing names, the numbers that the tools returned. For a kind whose readers
    the tools could not count it cites the volume only, and proposes to investigate."""

    def __init__(self, *, writers=True, **options):
        super().__init__(**options)
        self.writers = writers

    def run(self, agent, user_input, handler=None, *, max_calls=20, max_seconds=None):
        if not agent.startswith(agents.INVESTIGATOR_NAME):
            return super().run(agent, user_input, handler, max_calls=max_calls, max_seconds=max_seconds)
        self.runs.append({"agent": agent, "input": user_input, "max_calls": max_calls, "max_seconds": max_seconds, "handler": handler})

        def ask(name, **arguments):
            return json.loads(handler(name, arguments))

        handle = ask("list_resources", type=WORKSPACE_TYPE)["rows"][0][0]
        volume, readers = ask("data_volume", handle=handle), ask("data_readers", handle=handle)
        nothing, unknown = [], []
        if "rows" in volume and "rows" in readers:
            gb = {line[0]: line[volume["cols"].index("gb")] for line in volume["rows"]}
            broad = sum(source.get("scanning_all", 0) for source in readers.get("sources", {}).values() if isinstance(source, dict))
            for line in readers["rows"]:
                counts = dict(zip(readers["cols"], line))
                if None in line[1:5]:
                    unknown.append(counts["table"])
                elif counts["runs"] == 0 and sum(counts[name] for name in ("rules", "saved_searches", "workbooks", "analytics_rules")) + broad == 0:
                    nothing.append(counts["table"])
        if self.writers:
            ask("data_writers", handle=handle, table="Perf")
        cites = [entry(handle, f"{name} {table}", total) for table in nothing for name, total in (("Billable GB", gb[table]), ("Readers", 0), ("Runs", 0))]
        cites += [entry(handle, f"Billable GB {table}", gb[table]) for table in unknown]
        text = answer(finding(handles=[handle], basis="other", proposal="change" if nothing else "investigate", confidence=0.85, summary="This workspace stores data that nothing reads.",
                              evidence=cites)) if cites else answer()
        calls = [{"name": "list_resources", "arguments": {}, "ok": True, "chars": 1}, {"name": "data_volume", "arguments": {}, "ok": True, "chars": 1}]
        return AgentRun(text=text, calls=calls, input_tokens=2000, output_tokens=300, responses=3)


class WithTheRealTools(unittest.TestCase):
    """The real tools over a fake estate with a workspace, and an investigator that copies the numbers from their answers: what the analysis reads is what the tools really record."""

    def setUp(self):
        self.estate = deep()
        # AppLog_CL (a table of the customer, so the handle t1) took in 3 GB, Perf 1 GB, Heartbeat 1 GB and AzureActivity 0.02 GB. A rule names Heartbeat and a saved search names AzureActivity.
        self.estate.saved = [{"properties": {"query": "AzureActivity | take 10"}}]
        self.estate.rule_rows = [row(RULES, "rule-1", properties={"scopes": [WS], "enabled": True, "criteria": {"allOf": [{"query": "Heartbeat | count"}]}})]
        self.estate.sources = [{"ResourceId": MACHINE.lower(), "Bytes": 800_000_000, "Whole": 1_000_000_000}]
        self.tools = toolbox(self.estate)

    def investigate(self, **options):
        h = Harness(WorkspaceAgent(**options), self.tools, with_store=True)
        h.go()
        return h

    def test_the_kinds_that_nothing_names_are_found_from_the_records_of_the_tools_and_the_figure_is_the_cost_in_proportion_to_them(self):
        case, plan = case_and_plan(self.investigate())
        digest = case.facts["unread"]
        self.assertEqual((digest["billableGb"], digest["unreadGb"], digest["days"], digest["unknown"], digest["more"]), (5.02, 4.0, 30, 0, 0))
        self.assertEqual([(k["kind"], k.get("name"), k["gb"], k["runs"]) for k in digest["kinds"]], [("t1", "AppLog_CL", 3.0, 0), ("Perf", None, 1.0, 0)])
        self.assertEqual((digest["costUsd30d"], digest["savingUsd"], plan.saving_usd_month), (90.0, 71.71, 71.71))
        self.assertTrue(digest["runsRecorded"])

    def test_what_the_tools_recorded_is_what_the_analysis_reads_the_volume_the_readers_the_runs_and_the_names(self):
        self.investigate()
        handle = next(h for h, found in self.tools.handles.items() if found.resource_type == unread.WORKSPACE)
        block = self.tools.evidence[handle]
        self.assertEqual(block["volume"], {"billable_gb": 5.02, "days": 30, "tables": 4})
        self.assertEqual(sorted(name for name in block["metrics"] if name.startswith("Billable GB ")), ["Billable GB AzureActivity", "Billable GB Heartbeat", "Billable GB Perf", "Billable GB t1"])
        self.assertEqual((block["metrics"]["Readers Heartbeat"]["total"], block["metrics"]["Readers t1"]["total"], block["metrics"]["Runs t1"]["total"]), (1, 0, 0))
        self.assertEqual(self.tools.table_names(handle), {"t1": "AppLog_CL"})

    def test_the_kinds_of_the_writers_that_the_tool_showed_reach_the_choices_and_nothing_else_does(self):
        case, plan = case_and_plan(self.investigate())
        by_kind = {k["kind"]: k for k in case.facts["unread"]["kinds"]}
        self.assertEqual(by_kind["Perf"]["writers"], ["microsoft.compute/virtualmachines"])
        self.assertNotIn("writers", by_kind["t1"])
        self.assertIn("On the last closed day, the largest writers of Perf were: Virtual machine.", brief.build_brief(case, plan, now=WEB_NOW).options[0].what)
        self.setUp()
        without = brief.build_brief(*case_and_plan(self.investigate(writers=False)), now=WEB_NOW)
        self.assertNotIn("largest writers", " ".join(option.what for option in without.options))

    def read(self, *calls):
        """The tools called in this order over the fake estate, and the handle of the workspace."""
        handle = ask(self.tools, "list_resources", type=WORKSPACE_TYPE)["rows"][0][0]
        for name, arguments in calls:
            ask(self.tools, name, handle=handle, **arguments)
        return handle

    def test_a_volume_that_was_read_again_for_the_last_week_is_one_whole_of_that_week_and_the_rows_that_the_month_left_behind_are_not_in_it(self):
        self.estate.usage += [{"Day": "2026-11-02T00:00:00Z", "DataType": "Perf", "BillableMB": 500.0, "FreeMB": 0.0},
                              {"Day": "2026-11-02T00:00:00Z", "DataType": "Heartbeat", "BillableMB": 100.0, "FreeMB": 0.0}]
        handle = self.read(("data_volume", {}), ("data_readers", {}))
        month = unread.analyse(self.tools.evidence[handle], 90.0)
        self.assertEqual((month["days"], month["billableGb"], month["unreadGb"], [k["kind"] for k in month["kinds"]]), (30, 5.62, 4.5, ["t1", "Perf"]))
        ask(self.tools, "data_volume", handle=handle, days=7)
        block = self.tools.evidence[handle]
        self.assertEqual(block["volume"], {"billable_gb": 0.6, "days": 7, "tables": 2})
        self.assertEqual({name: found["days"] for name, found in block["metrics"].items() if name.startswith("Billable GB ")},
                         {"Billable GB Perf": 7, "Billable GB Heartbeat": 7, "Billable GB t1": 30, "Billable GB AzureActivity": 30}, "the rows that the week does not name stay as the month left them")
        week = unread.analyse(block, 90.0)
        self.assertEqual((week["days"], week["billableGb"], week["unreadGb"], week["share"], week["savingUsd"]), (7, 0.6, 0.5, 0.8333, 75.0))
        self.assertEqual([k["kind"] for k in week["kinds"]], ["Perf"], "t1 and AzureActivity are rows of the month: no part of the week")
        self.assertNotEqual(week["share"], 1.0, "the rows that the month left are not taken for all there is")

    def test_a_record_of_the_runs_that_was_cut_leaves_the_runs_of_the_kinds_that_no_text_names_unknown_and_the_digest_and_the_page_say_so(self):
        self.estate.audit_totals = [{"Runs": 9000, "Callers": 12}]
        self.estate.audit_texts = [{"QueryText": "Heartbeat | take 5", "Runs": 5}, *({"QueryText": f"Usage | take {n}", "Runs": 1} for n in range(deeper.MAX_AUDIT_TEXTS - 1))]
        handle = self.read(("data_volume", {}), ("data_readers", {}))
        block = self.tools.evidence[handle]
        self.assertEqual(sorted(name for name in block["metrics"] if name.startswith("Runs ")), ["Runs Heartbeat"], "the kinds that no text names have no count, and so no count of nothing")
        digest = unread.analyse(block, 90.0, self.tools.table_names(handle))
        self.assertEqual([(k["kind"], k["runs"]) for k in digest["kinds"]], [("t1", None), ("Perf", None)])
        self.assertFalse(digest["runsRecorded"])
        case = WhatAModelCannotDo.case(facts={"unread": digest}, cost_usd_30d=90.0)
        b = brief.build_brief(case, None, now=WEB_NOW)
        self.assertEqual([line.reads for line in b.unread.lines], ["Read by 0 rules, 0 saved searches and 0 workbooks; queries run: not recorded"] * 2, "never '0 queries run'")
        self.assertEqual(b.unread.caveat, "Not counted: the queries people run.")
        self.assertIn("could not be read in full", b.unread.note)

    def test_a_record_of_the_runs_that_came_back_in_full_counts_them_as_it_did(self):
        self.estate.audit_totals = [{"Runs": 9000, "Callers": 12}]
        self.estate.audit_texts = [{"QueryText": "Heartbeat | take 5", "Runs": 5}, *({"QueryText": f"Usage | take {n}", "Runs": 1} for n in range(deeper.MAX_AUDIT_TEXTS - 2))]
        handle = self.read(("data_volume", {}), ("data_readers", {}))
        digest = unread.analyse(self.tools.evidence[handle], 90.0, self.tools.table_names(handle))
        self.assertEqual([(k["kind"], k["runs"]) for k in digest["kinds"]], [("t1", 0), ("Perf", 0)])
        self.assertTrue(digest["runsRecorded"])

    def test_a_workspace_whose_records_cannot_be_read_has_no_claim_to_check_and_no_case(self):
        self.estate.failures["query"] = 403
        self.assertEqual(self.investigate().store.cases_recent(), [])

    def test_a_source_of_readers_that_this_access_cannot_read_leaves_no_figure_and_no_kind_is_said_to_be_read_by_nothing(self):
        self.estate.failures["saved"] = 403
        case, plan = case_and_plan(self.investigate())
        self.assertEqual(case.facts["unread"], {"missing": "readers"})
        self.assertEqual((case.recommendation, plan.saving_usd_month), ("investigate", None))
        self.assertRegex(page_of(case, plan)[1], r"Costs, saving not measured\.|Cost not visible\.")


if __name__ == "__main__":
    unittest.main()
