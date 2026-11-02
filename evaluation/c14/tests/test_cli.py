import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

C14 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(C14))

import run  # noqa: E402
from harness import demo  # noqa: E402
from harness.client import ScriptedClient  # noqa: E402

REAL_LIMITS = {"spending_cap_eur": 50, "max_completion_tokens": 1000, "price_per_million_tokens_eur": {"input": 1.0, "output": 4.0}}


def scripted_hub(max_tokens=None):
    return ScriptedClient(demo.handler)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="c14-cli-"))
        self.work = Path(tempfile.mkdtemp(prefix="c14-cli-work-"))

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)
        shutil.rmtree(self.work, ignore_errors=True)

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = run.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def real_pack(self, **params):
        pack = self.work / "pack"
        shutil.copytree(C14 / "pack-template", pack)
        path = pack / "params.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update({**REAL_LIMITS, **params})
        path.write_text(json.dumps(data), encoding="utf-8")
        return pack

    def accept(self):
        path = self.out / "review.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update({"decision": "accepted", "reviewer": "a-person"})
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_check_describes_the_template_pack(self):
        code, out, _ = self.call("check", str(C14 / "pack-template"))
        self.assertEqual(code, 0)
        self.assertIn("6 waste cases and 3 decoys", out)

    def test_the_demo_runs_the_whole_flow_and_writes_the_report(self):
        code, out, _ = self.call("demo", "--out", str(self.out))
        self.assertEqual(code, 0, out)
        report = (self.out / "report.md").read_text(encoding="utf-8")
        self.assertIn("Every pass condition holds", report)
        results = json.loads((self.out / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["review"]["decision"], "accepted")
        self.assertIn("demo-reviewer", (self.out / "review.json").read_text(encoding="utf-8"))

    def test_the_demo_without_an_output_folder_keeps_nothing(self):
        scratch = Path(tempfile.gettempdir())
        before = {p.name for p in scratch.glob("c14-demo-*")}
        code, out, _ = self.call("demo")
        self.assertEqual(code, 0, out)
        self.assertIn("Nothing was kept", out)
        self.assertEqual({p.name for p in scratch.glob("c14-demo-*")}, before)

    def test_a_real_run_refuses_to_start_without_a_cap_prices_or_a_reply_limit(self):
        for command in ("propose", "run"):
            code, _, err = self.call(command, str(C14 / "pack-template"), "--out", str(self.out))
            for name in ("spending_cap_eur", "max_completion_tokens", "price_per_million_tokens_eur.input", "price_per_million_tokens_eur.output"):
                self.assertIn(name, str(code) + err, command)

    def test_a_cap_alone_is_not_enough(self):
        pack = self.real_pack(price_per_million_tokens_eur={"input": None, "output": None}, max_completion_tokens=None)
        code, _, err = self.call("run", str(pack), "--out", str(self.out))
        self.assertNotIn("spending_cap_eur", str(code) + err)
        self.assertIn("max_completion_tokens", str(code) + err)
        self.assertIn("price_per_million_tokens_eur.input", str(code) + err)

    def test_a_pack_that_does_not_validate_is_an_error_not_a_trace(self):
        code, _, err = self.call("check", str(self.out))
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_the_report_can_be_rendered_again(self):
        self.call("demo", "--out", str(self.out))
        (self.out / "report.md").unlink()
        code, _, _ = self.call("report", str(self.out))
        self.assertEqual(code, 0)
        self.assertTrue((self.out / "report.md").exists())

    def test_the_stop_test_ends_the_run_after_two_calls_and_counts_the_proposal(self):
        pack = self.real_pack()
        with mock.patch.object(run, "HubClient", scripted_hub):
            self.assertEqual(self.call("propose", str(pack), "--out", str(self.out))[0], 0)
            self.accept()
            code, out, _ = self.call("run", str(pack), "--out", str(self.out), "--max-calls", "2")
        self.assertEqual(code, 1, out)
        results = json.loads((self.out / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["usage"]["calls"], 3)
        self.assertIn("limit of 3 model calls", results["stopped"])
        self.assertIsNone(results["verdict"])

    def test_a_full_run_exits_non_zero_until_a_person_has_read_the_answers(self):
        pack = self.real_pack()
        with mock.patch.object(run, "HubClient", scripted_hub):
            self.call("propose", str(pack), "--out", str(self.out))
            self.accept()
            code, out, _ = self.call("run", str(pack), "--out", str(self.out))
        self.assertEqual(code, 1, out)
        self.assertIn("answers read", out)
        review = json.loads((self.out / "review.json").read_text(encoding="utf-8"))
        review.update({"answers_read_by": "a-person", "answers_rest_on_the_claim": True})
        (self.out / "review.json").write_text(json.dumps(review), encoding="utf-8")
        code, out, _ = self.call("report", str(self.out))
        self.assertEqual(code, 0, out)
        self.assertIn("Passed.", out)
        results = json.loads((self.out / "results.json").read_text(encoding="utf-8"))
        self.assertTrue(results["verdict"]["passed"])
        self.assertEqual(results["usage"]["calls"], 82)

    def test_an_answer_that_does_not_rest_on_the_claim_makes_the_report_fail(self):
        pack = self.real_pack()
        with mock.patch.object(run, "HubClient", scripted_hub):
            self.call("propose", str(pack), "--out", str(self.out))
            self.accept()
            self.call("run", str(pack), "--out", str(self.out))
        review = json.loads((self.out / "review.json").read_text(encoding="utf-8"))
        review.update({"answers_read_by": "a-person", "answers_rest_on_the_claim": False})
        (self.out / "review.json").write_text(json.dumps(review), encoding="utf-8")
        code, out, _ = self.call("report", str(self.out))
        self.assertEqual(code, 1)
        self.assertIn("answers_read", out)

    def test_a_review_changed_after_the_run_cannot_turn_the_report_into_a_pass(self):
        pack = self.real_pack()
        with mock.patch.object(run, "HubClient", scripted_hub):
            self.call("propose", str(pack), "--out", str(self.out))
            self.accept()
            self.call("run", str(pack), "--out", str(self.out))
        review = json.loads((self.out / "review.json").read_text(encoding="utf-8"))
        review.update({"answers_read_by": "a-person", "answers_rest_on_the_claim": True, "reviewer": "someone-else"})
        (self.out / "review.json").write_text(json.dumps(review), encoding="utf-8")
        code, _, err = self.call("report", str(self.out))
        self.assertEqual(code, 2)
        self.assertIn("review.json changed after the run", err)
        review["reviewer"] = "a-person"
        (self.out / "review.json").write_text(json.dumps(review), encoding="utf-8")
        self.assertEqual(self.call("report", str(self.out))[0], 0)


if __name__ == "__main__":
    unittest.main()
