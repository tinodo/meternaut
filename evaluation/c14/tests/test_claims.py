import json
import unittest
from pathlib import Path

from harness.claims import (ClaimError, normalise, parse_claim, quote_hash, render_for_prompt, verify_receipts)

TEMPLATE = Path(__file__).resolve().parents[1] / "pack-template"
SNAPSHOT = TEMPLATE / "snapshot" / "prism-snapshot-storage.json"


def claim_data() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


class ParseClaimTests(unittest.TestCase):
    def test_a_template_claim_parses(self):
        claim = parse_claim(claim_data())
        self.assertEqual(claim.id, "prism-snapshot-storage")
        self.assertEqual(claim.mechanism, ("stock",))
        self.assertIn("[prism-snapshot-storage]", render_for_prompt(claim))

    def test_every_problem_is_listed(self):
        data = claim_data()
        data["id"] = "X"
        data["mechanism"] = ["magic"]
        data["level"] = "bill-observed"
        data["receipts"] = []
        with self.assertRaises(ClaimError) as raised:
            parse_claim(data)
        joined = " ".join(raised.exception.problems)
        for word in ("id:", "mechanism:", "level:", "receipts:"):
            self.assertIn(word, joined)

    def test_a_claim_without_a_receipt_is_a_rumour(self):
        data = claim_data()
        del data["receipts"]
        with self.assertRaises(ClaimError):
            parse_claim(data)

    def test_a_bad_hash_or_link_is_refused(self):
        data = claim_data()
        data["receipts"][0]["quote_sha256"] = "abc"
        data["receipts"][0]["url"] = "http://insecure.example/page"
        with self.assertRaises(ClaimError) as raised:
            parse_claim(data)
        self.assertEqual(len(raised.exception.problems), 2)

    def test_not_an_object(self):
        with self.assertRaises(ClaimError):
            parse_claim([])


class QuoteTests(unittest.TestCase):
    def test_rewrapping_and_typographic_quotes_do_not_matter(self):
        self.assertEqual(normalise("It\u2019s  billed\nper hour"), "It's billed per hour")
        self.assertEqual(quote_hash("It\u2019s billed per hour"), quote_hash("It's  billed\nper hour"))

    def test_a_changed_word_changes_the_hash(self):
        self.assertNotEqual(quote_hash("billed per hour"), quote_hash("billed per day"))

    def test_verify_receipts(self):
        claim = parse_claim(claim_data())
        url = claim.receipts[0].url
        page = "Intro. A snapshot of an index is billed per gigabyte\nfor each month it is kept. Outro."
        self.assertEqual(verify_receipts(claim, {url: page}), [])
        self.assertIn("not on the page", verify_receipts(claim, {url: "Something else."})[0])
        self.assertIn("not available", verify_receipts(claim, {})[0])

    def test_a_hash_that_does_not_match_the_quote_is_found(self):
        data = claim_data()
        data["receipts"][0]["quote_sha256"] = "0" * 64
        claim = parse_claim(data)
        page = "A snapshot of an index is billed per gigabyte for each month it is kept."
        problems = verify_receipts(claim, {claim.receipts[0].url: page})
        self.assertEqual(len(problems), 1)
        self.assertIn("hash", problems[0])


if __name__ == "__main__":
    unittest.main()
