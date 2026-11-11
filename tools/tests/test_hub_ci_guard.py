"""The Hub does not repeat the tests (AGENTS.md rule 35: the owner's minutes of GitHub Actions are limited).

Every run of the Hub used to start by running both complete unit-test suites: about five of its eight minutes on average. CI (checks.yml) runs them once, when a commit is pushed to main, and the Hub now asks GitHub,
read only and with its own token, whether that run passed for exactly its commit, and stops when it did not, whatever its action is. The step's script is run here with bash and a stand-in for `gh`; nothing is called."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workflow_scripts_of_the_hub_ci_guard_tests", ROOT / "tools" / "tests" / "test_workflow_scripts.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)

HUB = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
TITLE = "The checks of CI have passed for this commit"
MASKS = "Mask the identifiers of the estate in this run's log"
VALUES = "Refuse a value that the Hub does not know"
COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
# What a call looks like: the caller's own commit and repository are what GitHub puts in GITHUB_SHA and GITHUB_REPOSITORY; the code's own are what the `job` context gives.
CALLER = {"GITHUB_SHA": "0f0e0d0c0b0a09080706050403020100ffeeddcc", "GITHUB_REPOSITORY": "owner/deploy-repository"}
CALL = (f"gh api repos/owner/repository/actions/workflows/checks.yml/runs?head_sha={COMMIT}&event=push&branch=main&status=success&per_page=1 --jq .total_count")
GH = """#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
if [ "$FAKE_GH" = FAIL ]; then echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; fi
printf '%s\\n' "$FAKE_GH"
"""


def steps_of(text):
    return re.split(r"(?m)^      - ", text.split("    steps:\n", 1)[1])[1:]


def names_of(text):
    return [re.match(r"name: (.+)\n", block).group(1) for block in steps_of(text)]


def guard_block():
    (block,) = [b for b in steps_of(HUB) if b.startswith(f"name: {TITLE}\n")]
    return block


def code_of(block):
    return "\n".join(line for line in block.split("run:", 1)[1].splitlines() if not line.strip().startswith("#"))


class TheHubDoesNotRepeatTheTests(unittest.TestCase):
    def test_no_step_of_the_hub_runs_a_unit_test_the_workflow_lint_or_the_lint_of_bicep(self):
        for block in steps_of(HUB):
            if "run:" not in block:
                continue
            script = code_of(block)
            for word in ("unittest", "workflow-lint", "bicep lint", "check-docs", "cardlint", "--selftest"):
                self.assertNotIn(word, script, f"{word}: CI runs it once, for the commit that is pushed to main, and the Hub reads that it did ({block.splitlines()[0]})")

    def test_the_step_is_the_fourth_of_the_job_after_the_refusal_of_the_public_gateway_the_masks_and_the_check_of_the_values_and_before_the_checkout_and_every_sign_in(self):
        names = names_of(HUB)
        self.assertEqual(names[:4], ["Refuse the AI Gateway unless the owner asked for a public one in writing", MASKS, VALUES, TITLE])
        self.assertLess(names.index(TITLE), names.index("Check out the repository"), "it needs no checkout, so a commit that CI has not passed costs the seconds of this step and nothing else")
        self.assertLess(names.index(TITLE), names.index("Sign in to Azure"))

    def test_it_is_asked_of_every_action_the_ones_that_only_read_included(self):
        block = guard_block()
        self.assertNotIn("\n        if:", block, "no condition: what-if, drift-check and the checks of the apps are held to the same guard as a deploy")
        self.assertNotIn("continue-on-error", block)
        self.assertEqual(block.splitlines()[1], "        env:")
        self.assertIn("GH_TOKEN: ${{ github.token }}", block, "the run's own token, with the permissions of this workflow")

    def test_the_commit_and_the_repository_are_the_codes_own_and_never_the_callers_because_the_github_context_of_a_called_run_is_the_callers(self):
        block = guard_block()
        self.assertIn("          HUB_SOURCE_REPOSITORY: ${{ job.workflow_repository }}\n", block)
        self.assertIn("          HUB_SOURCE_SHA: ${{ job.workflow_sha }}\n", block)
        script = code_of(block)
        for caller in ("GITHUB_SHA", "GITHUB_REPOSITORY", "github.sha", "github.repository"):
            self.assertNotIn(caller, script, f"{caller} is the deploy repository's when the Hub is called")
        checkout = [b for b in steps_of(HUB) if b.startswith("name: Check out the repository\n")][0]
        self.assertIn("          repository: ${{ job.workflow_repository }}\n          ref: ${{ job.workflow_sha }}\n", checkout, "the commit that CI passed for is the commit that is checked out")

    def test_the_workflow_may_read_the_runs_of_actions_and_write_nothing_but_the_token_of_its_sign_in(self):
        lines = HUB.split("\njobs:\n", 1)[0].splitlines()
        start = lines.index("permissions:")
        values = {}
        for line in lines[start + 1:]:
            if line.strip() and not line.startswith(" "):
                break
            found = re.match(r"^  ([a-z-]+): (read|write|none)\s*$", line)
            if found:
                values[found.group(1)] = found.group(2)
        self.assertEqual(values, {"contents": "read", "actions": "read", "id-token": "write"})

    def test_the_step_only_reads_and_starts_nothing(self):
        script = code_of(guard_block())
        self.assertEqual(script.count("gh api"), 1)
        for word in ("--method", "-X ", "--field", "--raw-field", "--input", "gh workflow", "gh run", "gh pr", "gh issue", "gh release", "git push", "git fetch", "git pull", "curl"):
            self.assertNotIn(word, script, word)
        self.assertNotIn("${{", script, "no expression inside a script (tools/workflow-lint.py)")

    def test_what_it_asks_is_the_runs_of_checks_yml_for_exactly_this_commit_started_by_a_push_to_main_and_successful(self):
        script = code_of(guard_block())
        for word in ("actions/workflows/checks.yml/runs", "head_sha=$HUB_SOURCE_SHA", "event=push", "branch=main", "status=success", "--jq '.total_count'", "$HUB_SOURCE_REPOSITORY"):
            self.assertIn(word, script, word)
        self.assertTrue((ROOT / ".github" / "workflows" / "checks.yml").is_file(), "the workflow that the step looks for")
        checks = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8")
        self.assertRegex(checks, r"(?m)^on:\n  pull_request:\n  push:\n    branches: \[main\]\n", "a push to main starts it: that is the run that the Hub asks for")


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheStepRunWithBash(unittest.TestCase):
    def run_guard(self, answer="1", **env):
        return ws.run_step_script(TITLE, {"gh": GH}, {**CALLER, "HUB_SOURCE_SHA": COMMIT, "HUB_SOURCE_REPOSITORY": "owner/repository", "FAKE_GH": answer, **env})

    def test_a_call_asks_about_the_code_and_never_about_the_caller(self):
        done, lines, _ = self.run_guard("1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(lines, [CALL])
        for caller in CALLER.values():
            self.assertNotIn(caller, "\n".join(lines) + done.stdout + done.stderr)

    def test_a_successful_run_for_this_commit_lets_the_job_go_on_after_one_read(self):
        for answer in ("1", "2"):
            with self.subTest(answer=answer):
                done, lines, _ = self.run_guard(answer)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(lines, [CALL])
                self.assertIn(f"The checks of CI (checks.yml) have passed for commit {COMMIT}", done.stdout)

    def test_no_such_run_stops_the_job_with_the_plain_message_and_says_that_nothing_was_changed(self):
        done, lines, _ = self.run_guard("0")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(lines, [CALL])
        text = done.stdout + done.stderr
        self.assertIn("The checks have not passed for this commit: push it and let CI finish, then run the Hub again.", text)
        self.assertIn(COMMIT, text)
        self.assertIn("a push to main started", text)
        self.assertIn("Nothing was changed.", text)

    def test_an_answer_that_is_not_a_number_is_no_pass(self):
        for answer in ("", "null", "true", "one", "1 2", "-1"):
            with self.subTest(answer=answer):
                done, _, _ = self.run_guard(answer)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("The checks have not passed for this commit", done.stdout + done.stderr)

    def test_a_read_that_fails_stops_the_job_and_says_what_github_said_and_which_permission_the_workflow_needs(self):
        done, lines, _ = self.run_guard("FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(lines, [CALL])
        text = done.stdout + done.stderr
        self.assertIn("GitHub did not say whether the checks of CI passed", text)
        self.assertIn("Resource not accessible by integration (HTTP 403)", text)
        self.assertIn("actions: read", text)
        self.assertIn("Nothing was changed.", text)

    def test_a_commit_that_is_not_a_commit_id_is_refused_before_anything_is_asked(self):
        for sha in ("main", "", COMMIT[:39], COMMIT.upper(), COMMIT + "0", "../../runs"):
            with self.subTest(sha=sha):
                done, lines, _ = self.run_guard("1", HUB_SOURCE_SHA=sha)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertEqual(lines, [], "no call is made with what is not a commit id")
                self.assertIn("is not a git commit id", done.stdout + done.stderr)

    def test_a_repository_that_is_not_owner_slash_name_is_refused_before_anything_is_asked(self):
        for repository in ("", "owner", "owner/", "/name", "owner/name/extra", "../../x", "owner/na me", "owner/name?x=1", "owner/name;rm"):
            with self.subTest(repository=repository):
                done, lines, _ = self.run_guard("1", HUB_SOURCE_REPOSITORY=repository)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertEqual(lines, [], "no call is made with what is not a repository name")
                self.assertIn("not a name of the form owner/repository", done.stdout + done.stderr)
                self.assertIn("Nothing was changed.", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
