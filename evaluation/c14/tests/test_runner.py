import json
import shutil
import tempfile
import unittest
from pathlib import Path

from harness import demo, runner
from harness.cases import load_pack
from harness.claims import parse_claim
from harness.client import Completion, GuardedClient, ScriptedClient
from harness.report import render_report

TEMPLATE = Path(__file__).resolve().parents[1] / "pack-template"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_pack(TEMPLATE)
        self.out = Path(tempfile.mkdtemp(prefix="c14-out-"))

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def guarded(self, handler=demo.handler, **kw):
        return GuardedClient(ScriptedClient(handler), max_calls=kw.pop("max_calls", 100), **kw)

    def review(self, decision="accepted", reviewer="a-person", claim="draft"):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        runner.write_proposal(self.out, proposal, self.pack)
        data = json.loads((self.out / "review.json").read_text(encoding="utf-8"))
        data.update({"decision": decision, "reviewer": reviewer})
        if claim != "draft":
            data["claim"] = claim
        (self.out / "review.json").write_text(json.dumps(data), encoding="utf-8")

    def test_a_proposal_carries_a_receipt_and_no_problem(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        self.assertEqual(proposal["problems"], [])
        self.assertEqual(proposal["claim"].id, demo.CLAIM_ID)
        self.assertEqual(proposal["claim"].receipts[0].url, self.pack.source.url)

    def test_a_quote_that_is_not_on_the_page_is_found_by_code(self):
        def handler(system, user):
            data = json.loads(demo.proposer_reply(self.pack.source))
            data["quote"] = "A replica is free when nobody queries it."
            return json.dumps(data)
        proposal = runner.propose_claim(self.guarded(handler), self.pack.source)
        self.assertTrue(any("not on the page" in p for p in proposal["problems"]))

    def test_a_reply_without_json_is_a_problem_not_a_crash(self):
        proposal = runner.propose_claim(self.guarded(lambda s, u: "I cannot do that."), self.pack.source)
        self.assertIsNone(proposal["claim"])
        self.assertTrue(proposal["problems"])

    def test_the_review_is_required(self):
        self.assertEqual(runner.load_review(self.out, self.pack.source)[0], "pending")
        self.review(decision="pending")
        self.assertEqual(runner.load_review(self.out, self.pack.source)[0], "pending")

    def test_a_reviewer_must_be_named(self):
        self.review(reviewer="")
        decision, claim, problems = runner.load_review(self.out, self.pack.source)
        self.assertIsNone(claim)
        self.assertTrue(problems)

    def test_a_rejected_claim_ends_the_demonstration_without_a_run(self):
        self.review(decision="rejected")
        self.assertEqual(runner.load_review(self.out, self.pack.source), ("rejected", None, []))

    def test_an_edit_that_breaks_the_quote_is_found(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        edited = proposal["claim"].to_dict()
        edited["receipts"][0]["quote"] = "Replicas are free."
        self.review(decision="edited", claim=edited)
        decision, claim, problems = runner.load_review(self.out, self.pack.source)
        self.assertEqual(decision, "edited")
        self.assertTrue(any("not on the page" in p for p in problems))

    def accepted_claim(self):
        self.review()
        return runner.load_review(self.out, self.pack.source)[1]

    def test_the_arms_pass_with_a_model_that_learns_from_the_claim(self):
        client = self.guarded()
        outcome = runner.run_arms(self.pack, self.accepted_claim(), client)
        results = runner.build_results(self.pack, self.accepted_claim(), "accepted", [], outcome, client)
        self.assertEqual(client.calls, 81)
        self.assertTrue(results["verdict"]["pending"])
        self.assertEqual(results["verdict"]["failed"], [])
        self.assertEqual([s["found"] for s in results["summaries"]["frozen"]], [0, 0, 0])
        self.assertEqual([s["found"] for s in results["summaries"]["updated"]], [6, 6, 6])
        self.assertNotEqual(outcome["memories"]["frozen"]["sha256"], outcome["memories"]["updated"]["sha256"])

    def test_a_model_that_flags_everything_fails_on_the_decoys_and_means_no_headroom(self):
        def flag_all(system, user):
            if system.startswith("You read one passage"):
                return demo.handler(system, user)
            return json.dumps({"waste": True, "monthly_waste_eur": 100, "price_basis": "guess", "claim_ids": [],
                               "explanation": "Every replica looks unneeded.", "action": "Remove replicas"})
        client = self.guarded(flag_all)
        outcome = runner.run_arms(self.pack, self.accepted_claim(), client)
        verdict = runner.build_results(self.pack, self.accepted_claim(), "accepted", [], outcome, client)["verdict"]
        self.assertIn("decoys_quiet", verdict["failed"])
        self.assertIn("baselines_below_the_bar", verdict["failed"])
        self.assertTrue(verdict["no_headroom"])

    def test_the_call_limit_stops_the_run_and_leaves_no_verdict(self):
        client = self.guarded(max_calls=20)
        accepted = self.accepted_claim()
        outcome = runner.run_arms(self.pack, accepted, client)
        results = runner.build_results(self.pack, accepted, "accepted", [], outcome, client)
        self.assertIn("limit of 20", outcome["stopped"])
        self.assertIsNone(results["verdict"])
        self.assertEqual(client.calls, 20)

    def test_the_cost_is_checked_against_the_cap_when_prices_are_known(self):
        client = self.guarded(prices=(1000.0, 1000.0), cap_eur=0.001, max_completion_tokens=10)
        outcome = runner.run_arms(self.pack, self.accepted_claim(), client)
        self.assertIn("spending cap", outcome["stopped"])
        self.assertEqual(client.calls, 0)

    def test_the_cost_is_read_from_prices_when_given(self):
        client = self.guarded(prices=(1.0, 2.0))
        outcome = runner.run_arms(self.pack, self.accepted_claim(), client)
        results = runner.build_results(self.pack, self.accepted_claim(), "accepted", [], outcome, client, answers_ok=True)
        self.assertIsNotNone(results["usage"]["cost_eur"])
        self.assertTrue(results["verdict"]["passed"])

    def test_a_run_waits_for_a_person_to_read_the_answers_and_passes_after(self):
        client = self.guarded(prices=(1.0, 2.0))
        accepted = self.accepted_claim()
        results = runner.build_results(self.pack, accepted, "accepted", [], runner.run_arms(self.pack, accepted, client), client)
        self.assertFalse(results["verdict"]["passed"])
        self.assertEqual(results["verdict"]["failed"], [])
        self.assertTrue(runner.reevaluate(results, True)["verdict"]["passed"])
        self.assertIn("answers_read", runner.reevaluate(results, False)["verdict"]["failed"])

    def test_the_reading_of_the_answers_comes_from_review_json(self):
        self.review()
        self.assertIsNone(runner.read_confirmation(self.out))
        data = json.loads((self.out / "review.json").read_text(encoding="utf-8"))
        data.update({"answers_read_by": "a-person", "answers_rest_on_the_claim": True})
        (self.out / "review.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertIs(runner.read_confirmation(self.out), True)
        data["answers_read_by"] = " "
        (self.out / "review.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(runner.read_confirmation(self.out))

    def test_a_claim_that_copies_a_case_is_refused(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        edited = proposal["claim"].to_dict()
        edited["statement"] = "The Support articles index is used by the help centre of a software team."
        self.review(decision="edited", claim=edited)
        decision, claim, problems = runner.load_review(self.out, self.pack.source, self.pack.cases, self.pack.key)
        self.assertTrue(any("gives away a case" in p for p in problems))

    def test_a_claim_that_names_a_case_or_states_its_amount_is_refused(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        for statement in ("The shop-search index pays for replicas it does not use.",
                          "An idle index wastes 1,168 EUR a month.", "An idle index wastes 1168 EUR a month."):
            edited = proposal["claim"].to_dict()
            edited["statement"] = statement
            self.review(decision="edited", claim=edited)
            problems = runner.load_review(self.out, self.pack.source, self.pack.cases, self.pack.key)[2]
            self.assertTrue(any("gives away a case" in p for p in problems), statement)

    def test_a_draft_that_gives_away_a_case_is_flagged_when_it_is_proposed(self):
        def handler(system, user):
            data = json.loads(demo.proposer_reply(self.pack.source))
            data["statement"] = "A replica of shop-search is billed per hour whether or not it serves a query."
            return json.dumps(data)
        proposal = runner.propose_claim(self.guarded(handler), self.pack.source, self.pack.cases, self.pack.key)
        self.assertTrue(any("gives away a case" in p for p in proposal["problems"]))

    def test_a_changed_claim_marked_accepted_and_an_unchanged_one_marked_edited_are_refused(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        changed = proposal["claim"].to_dict()
        changed["statement"] += " It stops when the replica is removed."
        self.review(decision="accepted", claim=changed)
        self.assertTrue(any("set decision to edited" in p for p in runner.load_review(self.out, self.pack.source)[2]))
        self.review(decision="edited", claim=proposal["claim"].to_dict())
        self.assertTrue(any("set decision to accepted" in p for p in runner.load_review(self.out, self.pack.source)[2]))

    def test_the_claim_must_not_reuse_an_id_or_share_a_mechanism_with_the_control(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        clash = proposal["claim"].to_dict()
        clash["id"] = self.pack.control.id
        self.review(decision="edited", claim=clash)
        problems = runner.load_review(self.out, self.pack.source, (), None, self.pack.snapshot, self.pack.control)[2]
        self.assertTrue(any("already used" in p for p in problems))
        related = proposal["claim"].to_dict()
        related["mechanism"] = list(self.pack.control.mechanism)
        self.review(decision="edited", claim=related)
        problems = runner.load_review(self.out, self.pack.source, (), None, self.pack.snapshot, self.pack.control)[2]
        self.assertTrue(any("share a mechanism" in p for p in problems))

    def test_the_proposal_records_what_it_used_so_that_the_run_counts_it(self):
        self.assertEqual(runner.proposal_usage(self.out), (0, 0, 0))
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        runner.write_proposal(self.out, proposal, self.pack)
        self.assertEqual(runner.proposal_usage(self.out), (1, *proposal["tokens"]))

    def test_the_fields_a_reviewer_changed_are_listed(self):
        proposal = runner.propose_claim(self.guarded(), self.pack.source)
        edited = proposal["claim"].to_dict()
        edited["statement"] = edited["statement"] + " It stops when the replica is removed."
        self.review(decision="edited", claim=edited)
        claim = runner.load_review(self.out, self.pack.source, self.pack.cases)[1]
        self.assertEqual(runner.claim_edits(self.out, claim), ["statement"])
        self.review(decision="accepted", claim=proposal["claim"].to_dict())
        self.assertEqual(runner.claim_edits(self.out, runner.load_review(self.out, self.pack.source)[1]), [])

    def test_the_control_claim_must_look_like_the_new_one(self):
        claim = self.accepted_claim()
        self.assertIsNone(runner.control_problem(claim, self.pack.control))
        long = parse_claim({**self.pack.control.to_dict(), "statement": "Exports bill. " * 40})
        self.assertIn("in the prompt", runner.control_problem(claim, long))

    def test_the_report_lists_the_updated_answers_to_read(self):
        client = self.guarded()
        accepted = self.accepted_claim()
        outcome = runner.run_arms(self.pack, accepted, client)
        results = runner.build_results(self.pack, accepted, "accepted", [], outcome, client, [])
        text = render_report(results)
        self.assertIn("## Updated answers to read", text)
        self.assertIn("| case-w1 | 1 | yes |", text)
        results["verdict"]["no_headroom"] = True
        self.assertIn("**No headroom.**", render_report(results))

    def test_an_unanswered_case_is_scored_not_skipped(self):
        def silent(system, user):
            return demo.handler(system, user) if system.startswith("You read one passage") else "no idea"
        client = self.guarded(silent)
        outcome = runner.run_arms(self.pack, self.accepted_claim(), client)
        results = runner.build_results(self.pack, self.accepted_claim(), "accepted", [], outcome, client)
        self.assertEqual(results["summaries"]["updated"][0]["unanswered"], 9)
        self.assertIn("updated_finds_and_prices", results["verdict"]["failed"])


class ClientCountTests(unittest.TestCase):
    def test_tokens_are_counted(self):
        client = GuardedClient(ScriptedClient(lambda s, u: Completion("ok", 10, 3)), max_calls=5)
        client.complete("s", "u")
        client.complete("s", "u")
        self.assertEqual((client.calls, client.prompt_tokens, client.completion_tokens), (2, 20, 6))


if __name__ == "__main__":
    unittest.main()
