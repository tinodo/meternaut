"""The replay set and the thresholds of the learning check, the first run as the proposal states it, and what follows from a missed threshold (docs/proposals/15-learning.md, rule 14 (c)).

The first run of tools/learning-check.py on evaluation/learning-cases.jsonl, against evaluation/learning-thresholds.json, missed two thresholds. The numbers of that run are pinned here, so that a change
of the code that decides (cases/learning.py) or of the set shows up as a failing test and the proposal is read again; and the consequence is pinned: while the check misses a threshold, the proposal and
the README say that the claim of learning is withdrawn, and the hold of the Watch is off by default.

Every row of the set is invented (AGENTS.md rule 17).
"""
import json
import re
import unittest
from collections import Counter, defaultdict

from test_learning_check import ROOT, check

from cases import config, learning

CASES = ROOT / "evaluation" / "learning-cases.jsonl"
THRESHOLDS = ROOT / "evaluation" / "learning-thresholds.json"
PROPOSAL = ROOT / "docs" / "proposals" / "15-learning.md"
README = ROOT / "README.md"


def rows():
    return check.parse_rows(CASES.read_text(encoding="utf-8"))


def rules():
    return check.parse_thresholds(THRESHOLDS.read_text(encoding="utf-8"))


def block():
    found = re.search(r"<!-- learning-check:start -->\n(.*?)\n<!-- learning-check:end -->", PROPOSAL.read_text(encoding="utf-8"), re.S)
    assert found, "the proposal has no marked block of the results of the check"
    return found.group(1)


def by_type(found):
    groups = defaultdict(list)
    for item in found:
        groups[item["type"]].append(item)
    return groups


def labelled(items, band=None):
    """(approved, wrong) among the rows that say whether the finding was right, optionally in one band of the stated confidence."""
    approved = wrong = 0
    for item in items:
        if band is not None and learning.band_of(item["stated"]) != band:
            continue
        label = learning.label_of(check.lesson_of(item))
        approved += label is True
        wrong += label is False
    return approved, wrong


class TheReplaySet(unittest.TestCase):
    def test_it_is_78_requests_of_seven_kinds_in_time_order_over_155_days_and_all_of_the_family_that_the_watch_holds(self):
        found = rows()
        self.assertEqual(len(found), 78)
        self.assertEqual(len(by_type(found)), 7)
        self.assertEqual({item["family"] for item in found}, {"advise"}, "the Watch holds only the proposals of the investigation, whose plans are all of the family advise")
        self.assertEqual([item["id"] for item in found], [item["id"] for item in sorted(found, key=lambda item: (item["opened"], item["id"]))], "the file is in the order of the replay")
        self.assertEqual((min(item["opened"] for item in found), max(item["opened"] for item in found), max(item["closed"] for item in found)), (2, 155, 163))

    def test_each_kind_has_one_note_that_says_what_it_is_made_to_show_and_the_other_rows_have_none(self):
        for kind, items in by_type(rows()).items():
            with self.subTest(kind=kind):
                self.assertEqual([item["id"] for item in items if "note" in item], [items[0]["id"]])
                self.assertEqual(len({item["id"].rsplit("-", 1)[0] for item in items}), 1, "one prefix of ids for one kind")

    def test_every_pattern_that_the_proposal_names_is_in_the_data_and_not_only_in_the_notes(self):
        groups = by_type(rows())
        disks, snaps, farms, dbs, redis, pips, stor = (groups[f"microsoft.{name}"] for name in ("compute/disks", "compute/snapshots", "web/serverfarms", "sql/servers/databases", "cache/redis",
                                                                                                "network/publicipaddresses", "storage/storageaccounts"))
        approved, wrong = labelled(disks, band=2)
        self.assertGreaterEqual(approved + wrong, 10)
        self.assertGreaterEqual(approved / (approved + wrong), 0.85, "right nine times in ten")
        first, second = labelled(snaps[:5]), labelled(snaps[5:])
        self.assertEqual((first, second), ((3, 2), (5, 0)), "an unlucky start: two declines among the first five answers, then none")
        approved, wrong = labelled(farms)
        self.assertLessEqual(approved / (approved + wrong), 0.4, "sure and mostly wrong")
        high, low = labelled(dbs, band=2), labelled(dbs, band=1)
        self.assertGreaterEqual(high[0] / sum(high), 0.8)
        self.assertLessEqual(low[0] / sum(low), 0.3, "right when the AI states 0.9 and mostly wrong when it states about 0.75")
        for items in (redis, pips):
            self.assertLess(sum(labelled(items)), learning.MIN_BAND, "too few outcomes that say whether the finding was right, in any band")
        self.assertGreaterEqual(sum(1 for item in pips if learning.label_of(check.lesson_of(item)) is None), 7, "most of the requests end with nobody deciding or with an answer that says nothing")
        early, late = labelled(stor[:6]), labelled(stor[6:])
        self.assertEqual((early, late), ((1, 5), (4, 0)), "people changed their minds: declines at first, approvals after")

    def test_a_request_closes_after_it_opens_and_an_answer_that_ended_with_nobody_deciding_takes_the_time_of_the_plan_to_expire(self):
        for item in rows():
            self.assertGreater(item["closed"], item["opened"])
            if item["answer"] in ("expired", "ask", "later"):
                self.assertEqual(item["closed"] - item["opened"], 14, item["id"])

    def test_the_rows_are_invented_and_name_no_estate_and_none_of_the_examples_that_were_left_out_on_purpose(self):
        text = CASES.read_text(encoding="utf-8").lower()
        for word in ("subscription", "tenant", "/subscriptions/", "resourcegroup", "p2s", "point-to-site", "vwan", "virtual wan", "vpn gateway", "virtual hub", "scale unit", "idle gateway",
                     "laquerylogs", "log analytics", "azure monitor logs", "never read", "never queried", "not queried", "nobody reads", "idle", "unused", "orphan", "waste", "http", "@"):
            self.assertNotIn(word, text)
        self.assertIsNone(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text), "no id of an estate")
        for item in rows():
            self.assertTrue(item["type"].startswith("microsoft."), "a type as Azure names it, and no name of a resource")

    def test_the_kinds_of_resource_are_generic_ones_and_none_is_a_kind_that_a_trap_of_the_bank_is_about_by_name(self):
        self.assertEqual(sorted(by_type(rows())), ["microsoft.cache/redis", "microsoft.compute/disks", "microsoft.compute/snapshots", "microsoft.network/publicipaddresses",
                                                  "microsoft.sql/servers/databases", "microsoft.storage/storageaccounts", "microsoft.web/serverfarms"])


class TheThresholds(unittest.TestCase):
    def test_they_were_written_first_and_say_so_and_are_the_five_that_the_proposal_shows(self):
        document = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        self.assertIn("2026-11-09", document["writtenBefore"])
        self.assertIn("then the check, then the replay set, then the first run", document["writtenBefore"])
        found = rules()
        self.assertEqual({name: next(value for key, value in rule.items() if key != "why") for name, rule in found["thresholds"].items()},
                         {"labelledMin": 20, "brierImprovementMin": 0.02, "decoysHeldShareMin": 0.5, "goodHeldShareMax": 0.25, "coldStartIdentical": True})
        for name in ("brierImprovementMin", "decoysHeldShareMin", "goodHeldShareMax"):
            self.assertIn("starting value", found["thresholds"][name]["why"], f"{name} is a starting value that was written before any measurement")
        text = block()
        for bar in ("at least 20", "better by at least 0.02", "at least 0.5", "at most 0.25"):
            self.assertIn(bar, text)

    def test_what_is_not_measured_is_listed_in_the_file_and_the_proposal_names_it(self):
        for item in rules()["notMeasured"]:
            self.assertTrue(item.strip())
        proposal = PROPOSAL.read_text(encoding="utf-8")
        for words in ("real requests", "money", "the Investigator's use of its tools", "the claims of the Study", "boomerangs"):
            self.assertIn(words, proposal)


class TheFirstRun(unittest.TestCase):
    def test_it_missed_the_calibration_and_the_good_proposals_that_it_held_back_and_nothing_else(self):
        lines, code = check.run(rows(), rules())
        self.assertEqual(code, 1)
        self.assertEqual([line[:4] for line in lines if line[:4] in ("PASS", "FAIL")], ["PASS", "FAIL", "PASS", "FAIL", "PASS", "PASS"])
        self.assertIn("the claim of learning is withdrawn (missed: brierImprovementMin, goodHeldShareMax)", lines[-1])

    def test_its_numbers_are_the_ones_that_came_out_and_that_the_proposal_states(self):
        judged = check.replay(rows())
        n = check.measure(judged)
        self.assertEqual((n.rows, n.graded, n.labelled), (78, 39, 32))
        self.assertEqual((f"{n.brier_frozen:.3f}", f"{n.brier_updated:.3f}", f"{n.brier_frozen - n.brier_updated:.3f}"), ("0.206", "0.190", "0.017"))
        self.assertEqual((n.decoys, n.decoys_held, n.good, n.good_held), (9, 7, 23, 9))
        self.assertEqual((n.cold, n.cold_same, n.stronger), (47, 47, 0))
        text = block()
        for words in (f"{n.labelled} of the {n.graded} graded", f"{n.brier_frozen:.3f} with frozen memory and {n.brier_updated:.3f} with updated memory, better by {n.brier_frozen - n.brier_updated:.3f}",
                      f"{n.decoys_held} of the {n.decoys}, {n.decoys_held / n.decoys:.2f}", f"{n.good_held} of the {n.good}, {n.good_held / n.good:.2f}", f"{n.cold_same} of the {n.cold}"):
            self.assertIn(words, text)

    def test_the_table_by_kind_of_the_proposal_is_the_one_that_the_tool_prints(self):
        printed = {}
        for line in check.table(check.replay(rows()))[1:]:
            found = re.fullmatch(r"\s+(\S+)\s+advise\s+\d+\s+\d+/\d+\s+(\d+ of \d+)\s+(\d+ of \d+)", line)
            self.assertIsNotNone(found, line)
            printed[found.group(1)] = (found.group(2), found.group(3))
        shown = {}
        for line in block().splitlines():
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells[0].startswith("microsoft."):
                shown[cells[0]] = (cells[2], cells[3])
        self.assertEqual(shown, printed)
        self.assertEqual(len(shown), 7)

    def test_the_cost_of_holding_comes_from_the_kinds_that_the_proposal_names(self):
        table = {}
        for item in check.table(check.replay(rows()))[1:]:
            kind, *_, decoys, good = re.split(r"\s{2,}", item.strip())
            table[kind] = (decoys, good)
        self.assertEqual(table["microsoft.storage/storageaccounts"], ("1 of 1", "4 of 4"), "the kind whose people changed their minds: 4 of the 9 approved proposals that were held")
        self.assertEqual(table["microsoft.compute/snapshots"][1], "2 of 5", "the kind with an unlucky start: 2 of the 9")


class TheConsequenceOfAMissedThreshold(unittest.TestCase):
    CLAIM = "the claim that learning improves proposals is withdrawn"
    PROPOSAL_CLAIM = "learning improves what Meternaut proposes is withdrawn"

    def withdrawn(self):
        return check.run(rows(), rules())[1] != 0

    def test_the_readme_and_the_proposal_say_that_the_claim_is_withdrawn_exactly_while_the_check_misses_a_threshold(self):
        for name, text, phrase in (("the README", README.read_text(encoding="utf-8"), self.CLAIM), ("the proposal", PROPOSAL.read_text(encoding="utf-8"), self.PROPOSAL_CLAIM)):
            with self.subTest(name=name):
                self.assertEqual(phrase in text, self.withdrawn(), f"{name} and the check disagree about the claim of learning")

    def test_the_hold_of_the_watch_is_off_by_default_while_the_claim_is_withdrawn_and_the_lessons_are_not_behind_the_switch(self):
        default = config.Settings.__dataclass_fields__["learning_hold"].default
        if self.withdrawn():
            self.assertIs(default, False)
        self.assertEqual(config.LEARNING_HOLD, "LEARNING_HOLD")
        self.assertIn("LEARNING_HOLD", PROPOSAL.read_text(encoding="utf-8"))
        self.assertIn("LEARNING_HOLD is on", learning.__doc__)

    def test_the_proposal_and_the_readme_are_not_longer_than_the_budget_and_are_linked(self):
        proposal = PROPOSAL.read_text(encoding="utf-8")
        self.assertLessEqual(len(proposal.split()), 2200, "docs/proposals/15-learning.md: at most 2,200 words, tables included")
        self.assertIn("(docs/proposals/15-learning.md)", README.read_text(encoding="utf-8"))
        self.assertIn("(15-learning.md#the-capability-profile)", (ROOT / "docs" / "proposals" / "03-access-and-onboarding.md").read_text(encoding="utf-8"))
        self.assertEqual(Counter(re.findall(r"^## (.+)$", proposal, re.M))["The capability profile"], 1, "the anchor that the access proposal links to")


if __name__ == "__main__":
    unittest.main()
