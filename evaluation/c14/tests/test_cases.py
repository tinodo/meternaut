import json
import shutil
import tempfile
import unittest
from pathlib import Path

from harness.cases import PackError, copied_from_cases, load_pack, pack_hashes, shared_run

TEMPLATE = Path(__file__).resolve().parents[1] / "pack-template"


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c14-pack-"))
        self.pack = self.tmp / "pack"
        shutil.copytree(TEMPLATE, self.pack)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def edit(self, name: str, change):
        path = self.pack / name
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_the_template_loads(self):
        pack = load_pack(self.pack)
        self.assertEqual(len(pack.snapshot), 5)
        self.assertEqual(sum(c.kind == "waste" for c in pack.cases), 6)
        self.assertEqual(sum(c.kind == "decoy" for c in pack.cases), 3)
        self.assertEqual(set(pack.key), {c.id for c in pack.cases})

    def test_a_snapshot_smaller_than_the_stated_minimum_is_refused(self):
        (self.pack / "snapshot" / "prism-backup-retention.json").unlink()
        with self.assertRaises(PackError) as raised:
            load_pack(self.pack)
        self.assertIn("at least 5", str(raised.exception))
        self.edit("params.json", lambda params: params.update({"snapshot_claims_min": 4}))
        self.assertEqual(len(load_pack(self.pack).snapshot), 4)

    def test_a_case_that_quotes_the_source_is_not_unseen(self):
        def change(cases):
            cases[0]["facts"]["notes"] = "Keep more replicas than the load needs only for a window."
        self.edit("cases.json", change)
        with self.assertRaises(PackError) as raised:
            load_pack(self.pack)
        self.assertIn("not unseen", str(raised.exception))

    def test_the_kind_and_the_key_must_agree(self):
        self.edit("key.json", lambda key: key["case-d1"].update({"waste": True, "monthly_waste_eur": 5}))
        with self.assertRaises(PackError) as raised:
            load_pack(self.pack)
        self.assertIn("disagree", str(raised.exception))

    def test_a_waste_case_needs_an_amount(self):
        self.edit("key.json", lambda key: key["case-w1"].pop("monthly_waste_eur"))
        with self.assertRaises(PackError):
            load_pack(self.pack)

    def test_the_counts_must_match_the_params(self):
        self.edit("params.json", lambda params: params.update({"waste_cases": 7}))
        with self.assertRaises(PackError) as raised:
            load_pack(self.pack)
        self.assertIn("params say 7", str(raised.exception))

    def test_a_missing_param_is_named(self):
        self.edit("params.json", lambda params: params.pop("max_model_calls"))
        with self.assertRaises(PackError) as raised:
            load_pack(self.pack)
        self.assertIn("max_model_calls", str(raised.exception))

    def test_a_missing_file_is_named(self):
        (self.pack / "cases.json").unlink()
        with self.assertRaises(PackError) as raised:
            load_pack(self.pack)
        self.assertIn("cases.json: missing", str(raised.exception))

    def test_the_hashes_change_when_a_file_changes(self):
        before = pack_hashes(load_pack(self.pack))
        self.edit("key.json", lambda key: key["case-w1"].update({"monthly_waste_eur": 1.0}))
        after = pack_hashes(load_pack(self.pack))
        self.assertNotEqual(before["key"], after["key"])
        self.assertEqual(before["cases"], after["cases"])


class SharedRunTests(unittest.TestCase):
    def test_finds_a_shared_run_of_words(self):
        source = "A replica that has served no query for a month costs the same as a busy one."
        self.assertEqual(shared_run("it costs the same as a busy one", source), "costs the same as a busy")
        self.assertIsNone(shared_run("a busy index costs less", source))


class GivingAwayTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_pack(TEMPLATE)

    def gives_away(self, text):
        return copied_from_cases(text, self.pack.cases, self.pack.key)

    def test_a_clean_claim_gives_nothing_away(self):
        self.assertIsNone(self.gives_away("Each replica is billed per hour whether or not it serves a query."))

    def test_a_run_of_five_words_from_a_case_is_given_away(self):
        self.assertIn("case-w2", self.gives_away("It is used by the help centre of a software team."))

    def test_a_case_id_or_a_name_from_the_facts_is_given_away(self):
        self.assertIn("case-w1", self.gives_away("Think of case-w1 here."))
        self.assertIn("shop-search", self.gives_away("An index such as Shop-Search keeps replicas."))
        self.assertIsNone(self.gives_away("An index such as shop-searching is a different word."))

    def test_the_amount_of_the_key_is_given_away_in_either_form(self):
        self.assertIn("1168", self.gives_away("It wastes 1168 EUR."))
        self.assertIn("1,168", self.gives_away("It wastes 1,168 EUR."))
        self.assertIn("1168.00", self.gives_away("It wastes 1168.00 EUR."))
        self.assertIn("1,168.00", self.gives_away("It wastes 1,168.00 EUR."))
        self.assertIsNone(self.gives_away("It wastes 11680 EUR."))

    def test_a_fractional_amount_is_given_away_in_each_way_of_writing_it(self):
        from harness.cases import _amount_forms
        self.assertEqual(set(_amount_forms(1234.5)), {"1234.5", "1234.50", "1,234.50", "1,234.5"})
        self.assertEqual(set(_amount_forms(730.0)), {"730", "730.00"})


if __name__ == "__main__":
    unittest.main()
