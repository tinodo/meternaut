import unittest

from harness.cases import Case, KeyEntry
from harness.scoring import (RunSummary, decide, extract_json_object, parse_answer, score_case, summarise_run)

WASTE = Case("w", "waste", "t", {})
DECOY = Case("d", "decoy", "t", {})
KEY = KeyEntry(True, 1000.0, None, ("replica",))
PARAMS = {"updated_found_min": 5, "updated_priced_min": 4, "updated_runs_required": 2, "baseline_found_max": 2}


def answer(waste=True, amount=1000.0, explanation="Each replica bills per hour", action="Reduce replicas"):
    import json
    return parse_answer(json.dumps({"waste": waste, "monthly_waste_eur": amount, "price_basis": "bill",
                                    "claim_ids": ["c1"], "explanation": explanation, "action": action}))


def summary(found, priced, false_positives=0):
    return RunSummary(found, priced, false_positives, 0, 6, 3)


class ExtractTests(unittest.TestCase):
    def test_finds_an_object_in_prose_and_fences(self):
        self.assertEqual(extract_json_object('Sure.\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_braces_inside_strings_do_not_confuse_it(self):
        self.assertEqual(extract_json_object('{"a": "x } y", "b": {"c": 2}}'), {"a": "x } y", "b": {"c": 2}})

    def test_none_when_there_is_no_object(self):
        self.assertIsNone(extract_json_object("no json here"))
        self.assertIsNone(extract_json_object("{broken"))

    def test_parse_answer_needs_a_boolean_waste(self):
        self.assertIsNone(parse_answer('{"waste": "yes"}'))
        parsed = parse_answer('{"waste": false, "monthly_waste_eur": null}')
        self.assertFalse(parsed.waste)
        self.assertIsNone(parsed.monthly_waste_eur)


class ScoreCaseTests(unittest.TestCase):
    def test_found_and_priced(self):
        score = score_case(WASTE, KEY, answer(amount=1040.0), 10)
        self.assertTrue(score.found and score.priced)

    def test_found_but_priced_outside_the_tolerance(self):
        score = score_case(WASTE, KEY, answer(amount=1500.0), 10)
        self.assertTrue(score.found)
        self.assertFalse(score.priced)

    def test_a_missing_cause_term_is_not_a_find(self):
        score = score_case(WASTE, KEY, answer(explanation="It looks idle", action="Delete it"), 10)
        self.assertTrue(score.flagged)
        self.assertFalse(score.found)

    def test_no_cause_terms_in_the_key_means_flagged_is_found(self):
        score = score_case(WASTE, KeyEntry(True, 1000.0, None, ()), answer(explanation="idle"), 10)
        self.assertTrue(score.found)

    def test_waste_not_flagged(self):
        score = score_case(WASTE, KEY, answer(waste=False, amount=None), 10)
        self.assertFalse(score.found)

    def test_the_keys_own_tolerance_wins(self):
        tight = KeyEntry(True, 1000.0, 1.0, ("replica",))
        self.assertFalse(score_case(WASTE, tight, answer(amount=1040.0), 10).priced)

    def test_a_flagged_decoy_is_a_false_positive(self):
        self.assertTrue(score_case(DECOY, KeyEntry(False, None, None, ()), answer(), 10).false_positive)
        self.assertFalse(score_case(DECOY, KeyEntry(False, None, None, ()), answer(waste=False, amount=None), 10).false_positive)

    def test_an_unreadable_answer_counts_as_unanswered(self):
        score = score_case(WASTE, KEY, None, 10)
        self.assertFalse(score.answered or score.found)
        self.assertEqual(summarise_run([score]).unanswered, 1)


class DecideTests(unittest.TestCase):
    def runs(self, frozen=(0, 0, 0), control=(0, 0, 0), updated=((6, 6), (6, 5), (5, 4)), fp=0, ufp=0):
        return {
            "frozen": [summary(f, 0, fp) for f in frozen],
            "control": [summary(c, 0) for c in control],
            "updated": [summary(f, p, ufp) for f, p in updated],
        }

    def decide(self, runs, **kw):
        base = {"quote_ok": True, "review_ok": True, "within_cap": True, "answers_ok": True}
        base.update(kw)
        return decide(runs, PARAMS, **base)

    def test_everything_holds(self):
        verdict = self.decide(self.runs())
        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["failed"], [])

    def test_a_frozen_memory_that_already_finds_the_cases_means_no_headroom(self):
        verdict = self.decide(self.runs(frozen=(4, 5, 4)))
        self.assertIn("baselines_below_the_bar", verdict["failed"])
        self.assertTrue(verdict["no_headroom"])

    def test_one_good_updated_run_is_not_enough(self):
        verdict = self.decide(self.runs(updated=((6, 6), (3, 3), (2, 1))))
        self.assertIn("updated_finds_and_prices", verdict["failed"])
        self.assertFalse(verdict["no_headroom"])

    def test_priced_matters_as_well_as_found(self):
        verdict = self.decide(self.runs(updated=((6, 2), (6, 3), (6, 1))))
        self.assertIn("updated_finds_and_prices", verdict["failed"])

    def test_a_control_above_the_bar_is_judged_by_the_same_rule_as_frozen(self):
        verdict = self.decide(self.runs(control=(3, 3, 4)))
        self.assertIn("baselines_below_the_bar", verdict["failed"])
        self.assertTrue(verdict["no_headroom"])

    def test_a_control_that_finds_a_little_more_than_frozen_still_passes(self):
        self.assertTrue(self.decide(self.runs(control=(2, 1, 2)))["passed"])

    def test_the_baselines_are_judged_by_their_median_not_one_noisy_run(self):
        self.assertTrue(self.decide(self.runs(frozen=(0, 4, 0), control=(1, 0, 3)))["passed"])

    def test_one_flagged_decoy_in_the_updated_arm_fails(self):
        verdict = self.decide(self.runs(ufp=1))
        self.assertIn("decoys_quiet", verdict["failed"])

    def test_a_decoy_flagged_by_a_baseline_is_reported_but_not_counted(self):
        verdict = self.decide(self.runs(fp=1))
        self.assertTrue(verdict["passed"])
        self.assertIn("frozen 3", verdict["checks"]["decoys_quiet"]["detail"])

    def test_a_quote_off_the_page_or_no_review_fails(self):
        self.assertIn("quote_on_page", self.decide(self.runs(), quote_ok=False)["failed"])
        self.assertIn("review_recorded", self.decide(self.runs(), review_ok=False)["failed"])

    def test_an_unknown_cost_leaves_the_verdict_pending(self):
        verdict = self.decide(self.runs(), within_cap=None)
        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["pending"])
        self.assertEqual(verdict["failed"], [])

    def test_a_cost_over_the_cap_fails(self):
        self.assertIn("within_cap", self.decide(self.runs(), within_cap=False)["failed"])

    def test_a_pass_waits_for_a_person_to_read_the_updated_answers(self):
        verdict = self.decide(self.runs(), answers_ok=None)
        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["pending"])
        self.assertEqual(verdict["failed"], [])
        self.assertIsNone(verdict["checks"]["answers_read"]["ok"])

    def test_an_answer_that_does_not_rest_on_the_claim_fails(self):
        verdict = self.decide(self.runs(), answers_ok=False)
        self.assertIn("answers_read", verdict["failed"])
        self.assertFalse(verdict["passed"])


if __name__ == "__main__":
    unittest.main()
