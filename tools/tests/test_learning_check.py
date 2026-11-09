"""The learning check (tools/learning-check.py): the rows and the thresholds that it accepts, the replay in time order with the app's own calibration and hold, the numbers on small sets that are
worked out by hand, the verdicts at the edge of each threshold, the report and the exit codes, and the rule that a hold never makes a finding stronger.

The sets here are small and invented (AGENTS.md rule 17). The replay set of evaluation/learning-cases.jsonl is tested in test_learning_check_set.py.
"""
import ast
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "case-functions"
sys.path.insert(0, str(APP))

spec = importlib.util.spec_from_file_location("learning_check", ROOT / "tools" / "learning-check.py")
check = importlib.util.module_from_spec(spec)
sys.modules["learning_check"] = check
spec.loader.exec_module(check)

from cases import decide, learning, models  # noqa: E402
from cases.families import registry  # noqa: E402

DISKS = "microsoft.compute/disks"
PLANS = "microsoft.web/serverfarms"


def row(ident, stated, answer, opened, closed, reason="", kind=DISKS, family="advise"):
    return {"id": ident, "type": kind, "family": family, "stated": stated, "answer": answer, "reason": reason, "opened": opened, "closed": closed}


def text_of(rows):
    return "\n".join(json.dumps(item) for item in rows) + "\n"


def thresholds(**changed):
    rules = {"labelledMin": {"min": 5, "why": "w"}, "brierImprovementMin": {"min": 0.02, "why": "w"}, "decoysHeldShareMin": {"min": 0.5, "why": "w"}, "goodHeldShareMax": {"max": 1.0, "why": "w"},
             "coldStartIdentical": {"equals": True, "why": "w"}}
    rules.update(changed)
    return {"date": "2026-11-09", "thresholds": rules, "notMeasured": ["the first thing that is not measured", "the second thing"]}


def worked_set():
    """Five requests teach, five are graded. Of the five that teach one was approved (the others were declined as wrong), so what 0.9 supports is 0.2; the graded five all state 0.9, are judged
    on one day (none of them has closed by then) and are three wrong (F) and two right (T)."""
    teach = [row("e1", 0.9, "approve", 1, 2), row("e2", 0.9, "decline", 2, 3, "still-needed"), row("e3", 0.9, "decline", 3, 4, "still-needed"), row("e4", 0.9, "decline", 4, 5, "figure-wrong"),
             row("e5", 0.9, "decline", 5, 6, "still-needed")]
    graded = [row("g1", 0.9, "decline", 10, 30, "figure-wrong"), row("g2", 0.9, "approve", 10, 30), row("g3", 0.9, "decline", 10, 30, "still-needed"),
              row("g4", 0.9, "decline", 10, 30, "still-needed"), row("g5", 0.9, "approve", 10, 30)]
    return teach + graded


class TheReplaySet(unittest.TestCase):
    def test_a_well_formed_row_is_kept_with_or_without_a_note(self):
        good = row("a-1", 0.8, "approve", 1, 4)
        self.assertEqual(check.parse_rows(text_of([good, {**row("a-2", 0.5, "expired", 2, 9), "note": "a sentence for people"}])), [good, {**row("a-2", 0.5, "expired", 2, 9), "note": "a sentence for people"}])
        self.assertEqual(check.parse_rows("\n" + text_of([good]) + "\n\n"), [good], "blank lines are skipped")

    def test_a_row_that_is_not_well_formed_is_refused_by_name_with_exit_code_2(self):
        good = row("a-1", 0.8, "approve", 1, 4)
        wrong = [
            ({**good, "colour": "red"}, "unknown: colour"), ({k: v for k, v in good.items() if k != "stated"}, "missing: stated"), ({**good, "id": "A 1"}, "id"), ({**good, "type": "other"}, "type"),
            ({**good, "type": "disks"}, "type"), ({**good, "type": "Microsoft.Compute/Disks"}, "type"), ({**good, "family": "delete-everything"}, "family"), ({**good, "stated": 1.2}, "stated"),
            ({**good, "stated": True}, "stated"), ({**good, "stated": "0.9"}, "stated"), ({**good, "stated": -0.1}, "stated"), ({**good, "answer": "yes"}, "answer"),
            ({**good, "reason": "still-needed"}, "reason"), ({**row("a-1", 0.8, "decline", 1, 4), "reason": "because"}, "reason"), ({**good, "opened": 1.5}, "whole numbers"),
            ({**good, "closed": True}, "whole numbers"), ({**good, "closed": 1}, "closes after it opens"), ({**good, "opened": 4}, "closes after it opens"),
            ({**good, "closed": check.MAX_DAY + 1}, "closes after it opens"), ({**good, "note": "x" * 241}, "note"), ({**good, "note": 5}, "note"),
        ]
        for bad, words in wrong:
            with self.subTest(bad=bad), self.assertRaises(check.Problem) as raised:
                check.parse_rows(text_of([bad]))
            self.assertIn(words, str(raised.exception))
            self.assertEqual(raised.exception.code, 2)
        for text, words in (("{not json}\n", "line 1"), ("[1, 2]\n", "line 1"), ("", "no request"), ("\n\n", "no request"), (text_of([good, good]), "same id")):
            with self.subTest(text=text), self.assertRaises(check.Problem) as raised:
                check.parse_rows(text)
            self.assertIn(words, str(raised.exception))
        with self.assertRaises(check.Problem):
            check.parse_rows(text_of([row(f"r-{n}", 0.8, "approve", 1, 2) for n in range(check.MAX_ROWS + 1)]))

    def test_a_decline_may_have_no_reason_and_every_reason_of_the_app_is_accepted(self):
        rows = [row("d-0", 0.8, "decline", 1, 2)] + [row(f"d-{n}", 0.8, "decline", 1, 2, reason) for n, reason in enumerate(models.DECLINE_REASONS, 1)]
        self.assertEqual(len(check.parse_rows(text_of(rows))), 1 + len(models.DECLINE_REASONS))
        every = (*registry.names(), models.ADVISE)
        self.assertEqual(len(check.parse_rows(text_of([row(f"f-{n}", 0.8, "approve", 1, 2, family=family) for n, family in enumerate(every)]))), len(every))


class TheThresholdsFile(unittest.TestCase):
    def document(self, **changed):
        document = {"writtenBefore": "the first run: 2026-11-09. The order was ...", "thresholds": thresholds()["thresholds"], "notMeasured": ["a", "b"]}
        document.update(changed)
        return json.dumps(document)

    def test_a_good_file_gives_the_date_the_thresholds_and_what_is_not_measured(self):
        found = check.parse_thresholds(self.document())
        self.assertEqual(found["date"], "2026-11-09")
        self.assertEqual(found["notMeasured"], ["a", "b"])
        self.assertEqual(sorted(found["thresholds"]), sorted(check.RULES))

    def test_the_real_file_is_one_that_the_tool_reads(self):
        found = check.parse_thresholds((ROOT / "evaluation" / "learning-thresholds.json").read_text(encoding="utf-8"))
        self.assertEqual(found["date"], "2026-11-09")
        self.assertGreaterEqual(len(found["notMeasured"]), 4)

    def test_a_file_with_a_missing_unknown_or_ill_shaped_threshold_is_refused_so_that_nothing_passes_for_lack_of_a_rule(self):
        base = thresholds()["thresholds"]
        for name in base:
            with self.subTest(missing=name), self.assertRaises(check.Problem):
                check.parse_thresholds(self.document(thresholds={k: v for k, v in base.items() if k != name}))
        shapes = [{**base, "extra": {"min": 1, "why": "w"}}, {**base, "labelledMin": {"max": 5, "why": "w"}}, {**base, "labelledMin": {"min": -1, "why": "w"}},
                  {**base, "labelledMin": {"min": True, "why": "w"}}, {**base, "labelledMin": {"min": "5", "why": "w"}}, {**base, "labelledMin": {"min": 5}}, {**base, "labelledMin": {"min": 5, "why": ""}},
                  {**base, "coldStartIdentical": {"equals": False, "why": "w"}}, {**base, "coldStartIdentical": {"min": 1, "why": "w"}}, {**base, "goodHeldShareMax": 0.25}]
        for shape in shapes:
            with self.subTest(shape=shape), self.assertRaises(check.Problem):
                check.parse_thresholds(self.document(thresholds=shape))
        for bad in ("{}", "[]", "not json", self.document(writtenBefore="before the run"), self.document(writtenBefore=5), self.document(notMeasured=[]), self.document(notMeasured=["a", ""]),
                    self.document(notMeasured="a"), json.dumps({"writtenBefore": "2026-11-09", "notMeasured": ["a"]})):
            with self.subTest(bad=bad), self.assertRaises(check.Problem) as raised:
                check.parse_thresholds(bad)
            self.assertEqual(raised.exception.code, 2)


class TheReplay(unittest.TestCase):
    def test_frozen_memory_proposes_at_the_gate_of_the_app_and_above_it(self):
        self.assertEqual(decide.PROPOSE_CONFIDENCE, 0.7)
        judged = check.replay([row("a", 0.69, "approve", 1, 2), row("b", 0.7, "approve", 1, 2), row("c", 0.71, "approve", 1, 2), row("d", 1.0, "approve", 1, 2), row("e", 0.0, "approve", 1, 2)])
        self.assertEqual({item.row["id"]: item.frozen for item in judged}, {"a": "needs_human", "b": "proposed", "c": "proposed", "d": "proposed", "e": "needs_human"})

    def test_a_lesson_is_known_only_on_a_day_after_its_request_closed(self):
        teach = [row("t1", 0.9, "approve", 1, 2), row("t2", 0.9, "decline", 2, 3, "still-needed"), row("t3", 0.9, "decline", 3, 4, "still-needed"), row("t4", 0.9, "decline", 4, 5, "figure-wrong"),
                 row("t5", 0.9, "decline", 5, 6, "still-needed")]
        asked = [row("same-day", 0.9, "approve", 6, 20), row("next-day", 0.9, "approve", 7, 20)]
        by_id = {item.row["id"]: item for item in check.replay(teach + asked)}
        self.assertIsNone(by_id["same-day"].calibrated, "the fifth lesson closes on day 6: on that day only four are known, which is too few to say anything")
        self.assertEqual(by_id["same-day"].updated, "proposed")
        self.assertEqual((by_id["next-day"].calibrated.rate, by_id["next-day"].calibrated.cases), (0.2, 5))
        self.assertEqual(by_id["next-day"].updated, "needs_human", "from day 7 the five lessons are in the store, and 0.9 is approved in 1 of 5")

    def test_a_request_never_teaches_a_judgement_that_came_before_its_close_and_never_its_own(self):
        lone = check.replay([row("only", 0.95, "decline", 1, 2, "still-needed")])
        self.assertEqual((lone[0].calibrated, lone[0].updated), (None, "proposed"))
        later = [row(f"x{n}", 0.9, "decline", 1, 50, "still-needed") for n in range(8)] + [row("y", 0.9, "approve", 10, 11)]
        self.assertIsNone({item.row["id"]: item for item in check.replay(later)}["y"].calibrated, "eight requests are open on day 10: none of them has taught anything yet")

    def test_the_lessons_of_another_type_or_another_family_do_not_count(self):
        teach = [row(f"t{n}", 0.9, "decline", n, n + 1, "still-needed") for n in range(1, 7)]
        other_type = [{**item, "id": "p" + item["id"], "type": PLANS} for item in teach]
        other_family = [{**item, "id": "f" + item["id"], "family": "delete-disk"} for item in teach]
        asked = {item.row["id"]: item for item in check.replay(other_type + other_family + [row("q", 0.9, "approve", 20, 21)])}
        self.assertIsNone(asked["q"].calibrated)
        self.assertEqual(asked["q"].updated, "proposed")
        held = {item.row["id"]: item for item in check.replay(teach + [row("q", 0.9, "approve", 20, 21)])}
        self.assertEqual(held["q"].updated, "needs_human")

    def test_the_order_of_the_file_does_not_matter_and_an_id_breaks_a_tie(self):
        rows = worked_set()
        forward = [(item.row["id"], item.frozen, item.updated, item.calibrated) for item in check.replay(rows)]
        backward = [(item.row["id"], item.frozen, item.updated, item.calibrated) for item in check.replay(list(reversed(rows)))]
        self.assertEqual(forward, backward)
        self.assertEqual([item[0] for item in forward], ["e1", "e2", "e3", "e4", "e5", "g1", "g2", "g3", "g4", "g5"])

    def test_what_the_replay_calls_is_the_hold_of_the_app_and_nothing_else_decides(self):
        rows = worked_set()
        with mock.patch.object(check.learning, "hold", wraps=learning.hold) as spy:
            judged = check.replay(rows)
        self.assertEqual(spy.call_count, len(rows))
        for call, item in zip(spy.call_args_list, judged):
            store, kind, family, stated, outcome = call.args
            self.assertEqual((kind, family, stated, outcome.status), (item.row["type"], item.row["family"], item.row["stated"], item.frozen))
            self.assertEqual(type(store).__name__, "MemoryStore")
        for item in judged:
            held = learning.holds(item.row["stated"], item.calibrated)
            self.assertEqual(item.updated, "needs_human" if held and item.frozen == "proposed" else item.frozen)

    def test_the_label_of_a_row_is_the_apps_own_one(self):
        cases = [("approve", "", True), ("decline", "still-needed", False), ("decline", "figure-wrong", False), ("decline", "handled", None), ("decline", "other", None), ("decline", "", None),
                 ("not_mine", "", None), ("expired", "", None), ("ask", "", None), ("later", "", None)]
        for n, (answer, reason, label) in enumerate(cases):
            with self.subTest(answer=answer, reason=reason):
                self.assertIs(check.replay([row(f"l{n}", 0.8, answer, 1, 2, reason)])[0].label, label)


class TheNumbers(unittest.TestCase):
    def test_a_set_that_is_worked_out_by_hand(self):
        judged = check.replay(worked_set())
        numbers = check.measure(judged)
        self.assertEqual((numbers.rows, numbers.graded, numbers.labelled), (10, 5, 5))
        self.assertEqual([item.row["id"] for item in check.graded_part(judged)], ["g1", "g2", "g3", "g4", "g5"], "the later half is graded")
        # frozen: 0.9 against 3 wrong (0.81 each) and 2 right (0.01 each); updated: 0.2 against them (0.04 each, 0.64 each)
        self.assertAlmostEqual(numbers.brier_frozen, (3 * 0.81 + 2 * 0.01) / 5)
        self.assertAlmostEqual(numbers.brier_updated, (3 * 0.04 + 2 * 0.64) / 5)
        self.assertEqual((numbers.decoys, numbers.decoys_held, numbers.good, numbers.good_held), (3, 3, 2, 2))
        self.assertEqual((numbers.cold, numbers.cold_same, numbers.stronger), (5, 5, 0), "the five that taught were judged with fewer than five lessons: decided as frozen memory decides")

    def test_what_says_nothing_is_not_graded_and_a_finding_below_the_gate_is_neither_a_decoy_nor_a_good_proposal(self):
        teach = [row(f"t{n}", 0.9, "decline", n, n + 1, "still-needed") for n in range(1, 7)]
        graded = [row("u1", 0.9, "expired", 20, 40), row("u2", 0.9, "decline", 20, 40, "handled"), row("u3", 0.9, "not_mine", 20, 40), row("lo", 0.5, "decline", 20, 40, "still-needed"),
                  row("w", 0.9, "decline", 20, 40, "still-needed"), row("a", 0.9, "approve", 20, 40)]
        numbers = check.measure(check.replay(teach + graded))
        self.assertEqual((numbers.rows, numbers.graded, numbers.labelled), (12, 6, 3), "of the six graded only lo, w and a say whether the finding was right")
        self.assertEqual((numbers.decoys, numbers.decoys_held, numbers.good, numbers.good_held), (1, 1, 1, 1), "lo is below the gate: frozen memory does not propose it")
        self.assertEqual((numbers.cold, numbers.cold_same), (6, 6), "the six that taught were judged with fewer than five lessons known")
        # lo: 0.5 on both sides (nothing is known of its band); w: 0.9 against a wrong finding, and 0 supported; a: 0.9 against a right one, and 0 supported (a good proposal that was held)
        self.assertAlmostEqual(numbers.brier_frozen, (0.5 ** 2 + 0.9 ** 2 + 0.1 ** 2) / 3)
        self.assertAlmostEqual(numbers.brier_updated, (0.5 ** 2 + 0.0 + 1.0) / 3, msg="holding a good proposal costs calibration: a check that only counted the decoys would not see it")

    def test_learning_never_raises_a_confidence_a_type_that_is_approved_more_often_than_the_ai_said_is_left_as_it_is(self):
        teach = [row(f"t{n}", 0.75, "approve", n, n + 1) for n in range(1, 6)]
        graded = [row("g1", 0.75, "approve", 10, 30), row("g2", 0.75, "approve", 10, 30), row("g3", 0.75, "approve", 10, 30), row("g4", 0.75, "decline", 10, 30, "still-needed"),
                  row("g5", 0.75, "decline", 10, 30, "figure-wrong")]
        judged = check.replay(teach + graded)
        numbers = check.measure(judged)
        self.assertEqual({item.calibrated.rate for item in check.graded_part(judged)}, {1.0}, "what the lessons support is higher than what the AI said")
        self.assertEqual({item.forecast for item in check.graded_part(judged)}, {0.75}, "and the confidence that decides stays the one that the AI stated")
        self.assertAlmostEqual(numbers.brier_updated, numbers.brier_frozen)
        self.assertAlmostEqual(numbers.brier_frozen, (3 * 0.25 ** 2 + 2 * 0.75 ** 2) / 5)
        self.assertEqual((numbers.decoys, numbers.decoys_held, numbers.good, numbers.good_held, numbers.stronger), (2, 0, 3, 0, 0), "nothing is held, and nothing is made stronger")

    def test_no_graded_request_that_says_anything_gives_no_figure_at_all(self):
        numbers = check.measure(check.replay([row("a", 0.9, "expired", 1, 2), row("b", 0.9, "ask", 3, 4)]))
        self.assertEqual((numbers.labelled, numbers.brier_frozen, numbers.brier_updated, numbers.decoys, numbers.good), (0, None, None, 0, 0))


class TheVerdicts(unittest.TestCase):
    EDGE = check.Numbers(rows=60, graded=30, labelled=20, brier_frozen=0.30, brier_updated=0.28, decoys=10, decoys_held=5, good=8, good_held=2, cold=3, cold_same=3, stronger=0)
    RULES = {"labelledMin": {"min": 20}, "brierImprovementMin": {"min": 0.02}, "decoysHeldShareMin": {"min": 0.5}, "goodHeldShareMax": {"max": 0.25}, "coldStartIdentical": {"equals": True}}

    def judge(self, **changed):
        return {verdict.name: verdict for verdict in check.verdicts(replace(self.EDGE, **changed), self.RULES)}

    def test_every_threshold_holds_exactly_at_its_edge(self):
        found = self.judge()
        self.assertEqual(sorted(found), sorted(check.RULES))
        self.assertTrue(all(verdict.passed for verdict in found.values()), [v.words for v in found.values() if not v.passed])

    def test_every_threshold_is_missed_by_a_hair(self):
        for name, changed in {"labelledMin": {"labelled": 19}, "brierImprovementMin": {"brier_updated": 0.2801}, "decoysHeldShareMin": {"decoys_held": 4},
                              "goodHeldShareMax": {"good_held": 3}, "coldStartIdentical": {"cold_same": 2}}.items():
            with self.subTest(name=name):
                found = self.judge(**changed)
                self.assertFalse(found[name].passed, found[name].words)
                self.assertTrue(all(verdict.passed for other, verdict in found.items() if other != name), "the others are not touched")

    def test_a_number_that_cannot_be_had_is_a_threshold_that_is_missed_and_says_so(self):
        for name, changed in {"brierImprovementMin": {"labelled": 0, "brier_frozen": None, "brier_updated": None}, "decoysHeldShareMin": {"decoys": 0, "decoys_held": 0},
                              "goodHeldShareMax": {"good": 0, "good_held": 0}, "coldStartIdentical": {"cold": 0, "cold_same": 0}}.items():
            with self.subTest(name=name):
                found = self.judge(**changed)
                self.assertFalse(found[name].passed)
                self.assertIn("not measured", found[name].words)

    def test_a_worse_calibration_is_a_negative_improvement_and_misses(self):
        found = self.judge(brier_updated=0.35)
        self.assertFalse(found["brierImprovementMin"].passed)
        self.assertIn("better by -0.050", found["brierImprovementMin"].words)


class TheReport(unittest.TestCase):
    def test_a_replay_that_holds_every_threshold_exits_0_and_prints_the_numbers_the_table_and_what_is_not_measured(self):
        lines, code = check.run(worked_set(), thresholds())
        text = "\n".join(lines)
        self.assertEqual(code, 0, text)
        self.assertEqual([line[:4] for line in lines if line[:4] in ("PASS", "FAIL")], ["PASS"] * 6)
        for words in ("10 invented closed requests of 1 type in learning-cases.jsonl", "the later half, 5 requests from day 10", "written on 2026-11-09",
                      "0.490 with frozen memory and 0.280 with updated memory, better by 0.210",
                      "holds back 3 of the 3 proposals that people declined as wrong", "5 of the 5 proposals with too few outcomes", "microsoft.compute/disks", "not measured: the first thing that is not measured",
                      "not measured: the second thing", "result: on these invented requests and these thresholds updated memory beats frozen memory"):
            self.assertIn(words, text)
        self.assertNotIn("withdrawn", text)

    def test_a_missed_threshold_exits_1_and_the_claim_of_learning_is_withdrawn_by_name(self):
        lines, code = check.run(worked_set(), thresholds(goodHeldShareMax={"max": 0.25, "why": "w"}, labelledMin={"min": 6, "why": "w"}))
        self.assertEqual(code, 1)
        self.assertIn("result: the claim of learning is withdrawn (missed: labelledMin, goodHeldShareMax); docs/proposals/15-learning.md and the README say so", lines[-1])
        self.assertEqual([line[:4] for line in lines if line[:4] in ("PASS", "FAIL")].count("FAIL"), 2)

    def test_the_report_is_the_same_every_time_and_holds_no_path(self):
        first, second = check.run(worked_set(), thresholds())[0], check.run(list(reversed(worked_set())), thresholds())[0]
        self.assertEqual(first, second)
        text = "\n".join(first)
        for part in ("\\", "C:", "/Users/", "tinodo"):
            self.assertNotIn(part, text)

    def test_a_hold_that_makes_a_finding_stronger_fails_the_check_whatever_the_numbers_say(self):
        def stronger(store, kind, family, stated, outcome):
            return replace(outcome, status="proposed"), False

        with mock.patch.object(check.learning, "hold", stronger):
            numbers = check.measure(check.replay([row("low", 0.5, "approve", 1, 2)] + worked_set()))
            lines, code = check.run([row("low", 0.5, "approve", 1, 2)] + worked_set(), thresholds())
        self.assertEqual(numbers.stronger, 1)
        self.assertEqual(code, 1)
        self.assertTrue(any(line.startswith("FAIL  rule: no hold made a finding stronger (1 of 11 requests)") for line in lines), lines)
        self.assertIn("missed: ", lines[-1])
        self.assertIn("neverStronger", lines[-1])


class TheTool(unittest.TestCase):
    def run_main(self, files, *args):
        """The tool with the files that it reads served from a dictionary by name, so that no file is made."""
        def served(path):
            if path.name in files:
                return files[path.name]
            raise check.Problem(f"{path.name} cannot be read")

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(check, "read", served), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main(list(args))
        return code, out.getvalue(), err.getvalue()

    GOOD = {"c.jsonl": text_of(worked_set()), "t.json": json.dumps({"writtenBefore": "2026-11-09", "thresholds": thresholds()["thresholds"], "notMeasured": ["a thing"]})}

    def test_read_says_plainly_when_a_file_is_not_there_and_does_not_echo_its_path(self):
        with self.assertRaises(check.Problem) as raised:
            check.read(Path("no-such-folder") / "no-such-replay-set.jsonl")
        self.assertEqual((str(raised.exception), raised.exception.code), ("no-such-replay-set.jsonl cannot be read", 2))

    def test_the_report_goes_to_the_output_and_its_code_is_the_exit_code_of_the_tool(self):
        code, out, err = self.run_main(self.GOOD, "--cases", "c.jsonl", "--thresholds", "t.json")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("10 invented closed requests of 1 type in c.jsonl", out)
        self.assertIn("thresholds: t.json, written on 2026-11-09", out)
        self.assertTrue(out.rstrip().endswith("what is listed above as not measured is not claimed"))
        code, out, err = self.run_main({**self.GOOD, "t.json": self.GOOD["t.json"].replace('"min": 5', '"min": 6', 1)}, "--cases", "c.jsonl", "--thresholds", "t.json")
        self.assertEqual((code, err), (1, ""))
        self.assertIn("the claim of learning is withdrawn (missed: labelledMin)", out)

    def test_a_file_that_is_missing_or_not_well_formed_is_exit_2_with_a_plain_message_and_no_report(self):
        for files, args, words in ((self.GOOD, ("--cases", "none.jsonl", "--thresholds", "t.json"), "none.jsonl cannot be read"), (self.GOOD, ("--cases", "c.jsonl", "--thresholds", "none.json"), "none.json cannot be read"),
                                   ({**self.GOOD, "c.jsonl": "{nope}\n"}, ("--cases", "c.jsonl", "--thresholds", "t.json"), "line 1 of the replay set is not JSON"),
                                   ({**self.GOOD, "t.json": "{}"}, ("--cases", "c.jsonl", "--thresholds", "t.json"), "the thresholds file holds no `thresholds` object")):
            with self.subTest(words=words):
                code, out, err = self.run_main(files, *args)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(err.strip(), f"error: {words}")

    def test_the_defaults_are_the_files_of_evaluation(self):
        self.assertEqual((check.CASES, check.THRESHOLDS), (ROOT / "evaluation" / "learning-cases.jsonl", ROOT / "evaluation" / "learning-thresholds.json"))
        seen = []

        def stop(path):
            seen.append(path.name)
            raise check.Problem("stop")

        with mock.patch.object(check, "read", stop), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check.main([]), 2)
        self.assertEqual(seen, ["learning-cases.jsonl"])

    def test_the_tool_is_standard_library_and_the_app_and_never_the_network_or_a_model(self):
        tree = ast.parse((ROOT / "tools" / "learning-check.py").read_text(encoding="utf-8"))
        library, app = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                library |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "cases" or node.module.startswith("cases."):
                    app |= {f"{node.module}.{alias.name}" for alias in node.names}
                else:
                    library.add(node.module.split(".")[0])
        self.assertEqual(library, {"__future__", "argparse", "datetime", "json", "re", "sys", "dataclasses", "pathlib"})
        self.assertEqual(app, {"cases.decide", "cases.learning", "cases.models", "cases.memory_store.MemoryStore", "cases.memory_store.stamp", "cases.families.registry"},
                         "the decision, the lessons, the names of the families and the records of the app and its store in memory: no gateway, no Foundry, no agent")

    def test_the_tool_names_the_files_that_it_reads_and_the_exit_codes_in_its_help(self):
        doc = check.__doc__
        for words in ("evaluation/learning-cases.jsonl", "evaluation/learning-thresholds.json", "written before this tool, the replay set and the first run", "exits 0", "1 when one is missed",
                      "2 when a file cannot be read", "never calls a model", "AGENTS.md rule 14 (c)"):
            self.assertIn(words, doc)


if __name__ == "__main__":
    unittest.main()
