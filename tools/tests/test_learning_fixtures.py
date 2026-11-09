"""The fixtures of the evaluations for the three tools that recall what Meternaut kept (tools/foundry-evals.py recall_answers_of), held to the answers of the real toolbox.

A fixture that answers in another shape than the real tool would test an agent against a tool that does not exist. The fixtures of a clean row are the real answers of an empty memory, to the
word; the one hostile quote of a hostile row is harsher than the real tool lets through (the real tool refuses a quote that has a link or markup), so only the shape of it is held.
"""
import datetime as dt
import json
import unittest

import test_aisec_tools as aisec

ROOT, evals = aisec.ROOT, aisec.evals  # the one copy of each tool that the other tests of the tools hold (a second load of aisec-helpers.py would make a second class of every error)

from cases import toolbox  # noqa: E402  (the app is on the path: test_aisec_tools put it there)
from cases.memory_store import MemoryStore  # noqa: E402
from cases.models import CLAIM_KINDS, ClaimRecord  # noqa: E402

NOW = dt.datetime(2026, 11, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
RECALL = ("recall_lessons", "recall_knowledge", "recall_open_questions")
ROWS = [json.loads(line) for line in (ROOT / "evaluation" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def arguments_of(name: str, kind: str) -> dict:
    return {} if name == "recall_open_questions" else {"type": kind}


def real_answer(name: str, kind: str, store: MemoryStore) -> dict:
    box = toolbox.Toolbox(None, (), NOW, [])
    box.memory = store
    return json.loads(box.call(name, arguments_of(name, kind)))


class TheFixturesAreTheShapesOfTheRealTools(unittest.TestCase):
    def test_a_clean_row_gets_the_answers_that_an_empty_memory_gives_to_the_word(self):
        clean = [row for row in ROWS if not row.get("inject")]
        self.assertGreater(len(clean), 3)
        for row in clean:
            answers = evals.answers_of(row)
            for name in RECALL:
                self.assertEqual(answers[name](arguments_of(name, row["type"])), real_answer(name, row["type"], MemoryStore(clock=lambda: NOW)), f"{row['id']}: {name}")

    def test_a_hostile_row_gives_the_documentation_one_claim_with_the_keys_of_a_real_claim_and_the_other_two_the_same_as_ever(self):
        kind = "microsoft.example/things"
        store = MemoryStore(clock=lambda: NOW)
        store.claim_put(ClaimRecord(claim_id="c1", resource_type=kind, kind=CLAIM_KINDS[0], url="https://learn.microsoft.com/en-us/azure/example/pricing",
                                    quote="A thing is billed for each hour that it exists.", read_at="2026-11-01T09:00:00Z", checked_at="2026-11-03T09:00:00Z",
                                    expires_at="2026-12-01T09:00:00Z", state="fresh"))
        real = real_answer("recall_knowledge", kind, store)
        hostile = [row for row in ROWS if row.get("inject")]
        self.assertGreater(len(hostile), 3)
        for row in hostile:
            answers = evals.answers_of(row)
            documentation = answers["recall_knowledge"](arguments_of("recall_knowledge", row["type"]))
            self.assertEqual(sorted(documentation), sorted(real), row["id"])
            (claim,) = documentation["claims"]
            self.assertEqual(sorted(claim), sorted(real["claims"][0]), row["id"])
            self.assertEqual(claim["quote"], list(row["inject"].values())[0])
            self.assertIn(claim["kind"], CLAIM_KINDS)
            for name in ("recall_lessons", "recall_open_questions"):
                self.assertEqual(answers[name](arguments_of(name, row["type"])), real_answer(name, row["type"], MemoryStore(clock=lambda: NOW)), f"{row['id']}: {name}")

    def test_the_three_tools_are_in_the_toolbox_and_the_fixtures_answer_no_tool_that_does_not_exist(self):
        names = {spec.name for spec in toolbox.SPECS}
        self.assertTrue(set(RECALL) <= names)
        self.assertEqual(set(evals.PARAMETERS) - names, set(), "the fixtures take no tool that does not exist")
        for row in ROWS:
            self.assertEqual(set(evals.answers_of(row)) - names, set(), row["id"])

    def test_the_replay_hands_the_three_answers_to_the_agent(self):
        handle, _ = evals.handler_of(ROWS[0])
        for name in RECALL:
            self.assertNotIn("error", json.loads(handle(name, arguments_of(name, ROWS[0]["type"]))), name)


if __name__ == "__main__":
    unittest.main()
