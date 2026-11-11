import importlib.util
import io
import re
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

try:
    import yaml
except ImportError:  # the standard library has no YAML parser; checks.yml parses the deploy workflow with Ruby on CI
    yaml = None
TOOL = Path(__file__).resolve().parents[1] / "workflow-lint.py"
spec = importlib.util.spec_from_file_location("workflow_lint", TOOL)
wl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wl)

ROOT = Path(__file__).resolve().parents[2]
SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
LOGIN = "a641126d1b8aa4d1fa005f4f92df94a3a4c4c906"

GOOD_CHECKS = f"""
name: Checks
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{SHA} # v7.0.1
        with:
          persist-credentials: false
      - name: Test
        env:
          VALUE: ${{{{ github.ref }}}}
        run: |
          echo "$VALUE"
"""

DEPLOY_ON = """on:
  workflow_dispatch:
    inputs:
      action:
        type: choice
        options:
          - what-if
          - deploy
  workflow_call:
    inputs:
      action:
        type: string
        required: true
"""

GOOD_DEPLOY = f"""
name: Hub
{DEPLOY_ON}permissions:
  contents: read
  id-token: write
concurrency:
  group: hub
jobs:
  hub:
    name: Hub ({{{{ inputs.action }}}})
    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    env:
      ACTION: ${{{{ inputs.action }}}}
    steps:
      - name: Check out
        uses: actions/checkout@{SHA} # v7.0.1
        with:
          repository: ${{{{ job.workflow_repository }}}}
          ref: ${{{{ job.workflow_sha }}}}
          persist-credentials: false
      - name: Sign in
        uses: azure/login@{LOGIN} # v3.1.0
        with:
          client-id: ${{{{ secrets.AZURE_CLIENT_ID }}}}
      - name: Work
        if: inputs.action == 'deploy'
        run: echo "$ACTION"
"""

GOOD_DRIFT = f"""
name: Drift
on:
  workflow_dispatch:
permissions:
  contents: read
  id-token: write
concurrency:
  group: drift
jobs:
  drift:
    name: Drift check
    if: github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.actor == 'tinodo')
    runs-on: ubuntu-latest
    env:
      ACTION: check
    steps:
      - name: Check out
        uses: actions/checkout@{SHA} # v7.0.1
        with:
          persist-credentials: false
      - name: Sign in
        uses: azure/login@{LOGIN} # v3.1.0
        with:
          client-id: ${{{{ vars.DRIFT_CLIENT_ID }}}}
      - name: Work
        run: echo "$ACTION"
"""


class Lint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def lint(self, text, name="checks.yml"):
        path = self.dir / name
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return wl.lint_file(path)

    def assertFinding(self, problems, fragment):
        self.assertTrue(any(fragment in p for p in problems), f"{fragment!r} not in {problems}")

    def test_the_repositorys_workflows_have_no_findings(self):
        files = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertIn("deploy-hub.yml", [f.name for f in files])
        self.assertEqual([p for f in files for p in wl.lint_file(f)], [])

    def test_good_samples_pass(self):
        self.assertEqual(self.lint(GOOD_CHECKS), [])
        self.assertEqual(self.lint(GOOD_DEPLOY, "deploy-hub.yml"), [])

    def test_an_action_must_be_pinned_to_a_full_commit(self):
        for ref in ("v4", "main", SHA[:39], SHA.upper(), SHA + "0"):
            problems = self.lint(GOOD_CHECKS.replace(SHA, ref))
            self.assertFinding(problems, "not pinned")
        self.assertFinding(self.lint(GOOD_CHECKS.replace(f"actions/checkout@{SHA}", "./local-action")), "not pinned")
        self.assertFinding(self.lint(GOOD_CHECKS.replace(f"actions/checkout@{SHA}", "docker://alpine:3")), "not pinned")

    def test_checkout_must_not_keep_the_token(self):
        self.assertFinding(self.lint(GOOD_CHECKS.replace("persist-credentials: false", "fetch-depth: 1")), "persist-credentials")
        self.assertFinding(self.lint(GOOD_CHECKS.replace("persist-credentials: false", "persist-credentials: true")), "persist-credentials")

    def test_an_expression_must_not_sit_in_a_script(self):
        block = GOOD_CHECKS.replace('echo "$VALUE"', 'echo "${{ github.event.head_commit.message }}"')
        self.assertFinding(self.lint(block), "expression inside a run script")
        inline = GOOD_CHECKS.replace("run: |\n          echo \"$VALUE\"", 'run: echo ${{ github.actor }}')
        self.assertFinding(self.lint(inline), "expression inside a run script")
        dashed = GOOD_CHECKS.replace("      - name: Test\n        env:\n          VALUE: ${{ github.ref }}\n        run: |",
                                     "      - run: |\n          echo ${{ secrets.X }}\n      - name: Test\n        env:\n          VALUE: ${{ github.ref }}\n        run: |")
        self.assertFinding(self.lint(dashed), "expression inside a run script")

    def test_an_expression_in_env_with_if_and_name_is_fine(self):
        self.assertEqual(self.lint(GOOD_DEPLOY, "deploy-hub.yml"), [])
        self.assertEqual(self.lint(GOOD_CHECKS.replace("name: Test", "name: Test ${{ github.sha }}")), [])

    def test_the_line_of_a_finding_is_reported(self):
        problems = self.lint(GOOD_CHECKS.replace('echo "$VALUE"', 'echo "${{ github.actor }}"'))
        self.assertTrue(any(p.startswith("checks.yml:") and p.split(":")[1].isdigit() for p in problems), problems)
        line = int(problems[0].split(":")[1])
        self.assertIn("${{ github.actor }}", (self.dir / "checks.yml").read_text(encoding="utf-8").splitlines()[line - 1])

    def test_permissions_are_set_and_never_write_outside_the_deploy_workflow(self):
        self.assertFinding(self.lint(GOOD_CHECKS.replace("permissions:\n  contents: read\n", "")), "no top-level `permissions:`")
        self.assertFinding(self.lint(GOOD_CHECKS.replace("contents: read", "contents: write")), "contents: write")
        self.assertFinding(self.lint(GOOD_CHECKS.replace("permissions:\n  contents: read", "permissions: write-all")), "write-all")
        self.assertFinding(self.lint(GOOD_CHECKS.replace("contents: read", "id-token: write")), "id-token: write")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("id-token: write", "contents: write"), "deploy-hub.yml"), "contents: write")

    def test_the_hub_may_read_the_runs_of_actions_to_see_that_ci_passed_and_may_not_write_them(self):
        reading = GOOD_DEPLOY.replace("  contents: read\n", "  contents: read\n  actions: read\n")
        self.assertIn("  actions: read\n", reading)
        self.assertEqual(self.lint(reading, "deploy-hub.yml"), [])
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("  contents: read\n", "  contents: read\n  actions: write\n"), "deploy-hub.yml"), "actions: write")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("  contents: read\n", "  contents: read\n  actions: write\n"), "drift.yml"), "actions: write")

    def test_risky_triggers_are_refused(self):
        for event in ("pull_request_target", "workflow_run", "issue_comment"):
            self.assertFinding(self.lint(GOOD_CHECKS.replace("  pull_request:\n", f"  {event}:\n")), event)
        self.assertFinding(self.lint(GOOD_CHECKS.replace("on:\n  pull_request:\n  push:\n    branches: [main]", "on: [push, pull_request_target]")), "pull_request_target")

    def test_only_the_two_workflows_that_may_sign_in_to_azure_do(self):
        self.assertFinding(self.lint(GOOD_CHECKS + f"      - uses: azure/login@{LOGIN}\n"), "only deploy-hub.yml and drift.yml may")
        self.assertFinding(self.lint(GOOD_CHECKS + "      - run: az login --service-principal\n"), "only deploy-hub.yml and drift.yml may")
        self.assertFinding(self.lint(GOOD_DEPLOY, "other.yml"), "only deploy-hub.yml and drift.yml may")

    def test_the_read_only_drift_workflow_passes_by_hand_and_a_timer_is_refused_until_the_constant_lets_one_through(self):
        self.assertEqual(self.lint(GOOD_DRIFT, "drift.yml"), [])
        timer = GOOD_DRIFT.replace("on:\n  workflow_dispatch:\n", "on:\n  workflow_dispatch:\n  schedule:\n    - cron: '17 3 * * *'\n")
        self.assertIn("schedule:", timer)
        self.assertFinding(self.lint(timer, "drift.yml"), "must run on `workflow_dispatch` alone")
        self.assertFinding(self.lint(timer, "drift.yml"), "read-only identity exists")
        self.assertFalse(wl.DRIFT_ON_A_TIMER, "no timer until the owner has made the read-only identity: the change that adds `schedule:` to drift.yml sets the constant in the same commit")
        with mock.patch.object(wl, "DRIFT_ON_A_TIMER", True):
            self.assertEqual(self.lint(timer, "drift.yml"), [])
            self.assertEqual(self.lint(GOOD_DRIFT, "drift.yml"), [])

    def test_the_read_only_drift_workflow_starts_by_hand_and_by_nothing_else_and_by_a_timer_only_when_the_constant_says_so(self):
        for trigger in ("on:\n  push:\n    branches: [main]\n", "on:\n  workflow_dispatch:\n  push:\n", "on:\n  schedule:\n    - cron: '17 3 * * *'\n", "on: pull_request\n"):
            with self.subTest(trigger=trigger):
                problems = self.lint(GOOD_DRIFT.replace("on:\n  workflow_dispatch:\n", trigger), "drift.yml")
                self.assertFinding(problems, "must run on `workflow_dispatch` alone")
                with mock.patch.object(wl, "DRIFT_ON_A_TIMER", True):
                    self.assertFinding(self.lint(GOOD_DRIFT.replace("on:\n  workflow_dispatch:\n", trigger), "drift.yml"), "must run on `workflow_dispatch`, and may run on a timer")
        self.assertFinding(self.lint(GOOD_DRIFT.replace("on:\n  workflow_dispatch:\n", "on:\n  workflow_dispatch:\n  workflow_run:\n"), "drift.yml"), "workflow_run")

    def test_the_read_only_drift_workflow_is_guarded_for_what_the_guard_says(self):
        guard = "    if: github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.actor == 'tinodo')\n"
        self.assertIn(guard, GOOD_DRIFT)
        for changed in ("github.ref == 'refs/heads/main'", "github.ref == 'refs/heads/main' && github.actor == 'tinodo'", "github.ref == 'refs/heads/main' || github.actor == 'tinodo'",
                        "(github.event_name == 'schedule' || github.actor == 'tinodo')", "always()", "github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.actor == 'tinodo')"):
            self.assertFinding(self.lint(GOOD_DRIFT.replace(guard, f"    if: {changed}\n"), "drift.yml"), "only on main, started by the owner or by its timer")
        self.assertFinding(self.lint(GOOD_DRIFT.replace(guard, ""), "drift.yml"), "only on main, started by the owner or by its timer")
        self.assertFinding(self.lint(GOOD_DRIFT + "  other:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n", "drift.yml"), "exactly one job")
        self.assertFinding(self.lint(GOOD_DRIFT.replace("concurrency:\n  group: drift\n", ""), "drift.yml"), "concurrency")
        self.assertFinding(self.lint(GOOD_DRIFT.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    continue-on-error: true\n"), "drift.yml"), "continue-on-error")
        self.assertFinding(self.lint(GOOD_DRIFT.replace(f"      - name: Sign in\n        uses: azure/login@{LOGIN} # v3.1.0\n        with:\n          client-id: ${{{{ vars.DRIFT_CLIENT_ID }}}}\n", ""), "drift.yml"), "does not sign in")

    def test_the_read_only_drift_workflow_never_signs_in_with_the_deploy_identity_and_never_writes(self):
        problems = self.lint(GOOD_DRIFT.replace("vars.DRIFT_CLIENT_ID", "secrets.AZURE_CLIENT_ID"), "drift.yml")
        self.assertFinding(problems, "is the deploy identity, which can change Azure")
        self.assertFinding(self.lint(GOOD_DRIFT.replace("contents: read", "contents: write"), "drift.yml"), "contents: write")
        self.assertFinding(self.lint(GOOD_DRIFT.replace("id-token: write", "id-token: write\n  pull-requests: write"), "drift.yml"), "pull-requests: write")
        self.assertEqual(self.lint(GOOD_DRIFT.replace("jobs:", "# the deploy identity is secrets.AZURE_CLIENT_ID, which this workflow never names in its code\njobs:"), "drift.yml"), [], "a comment may say so")
        self.assertFinding(self.lint(GOOD_DRIFT.replace('echo "$ACTION"', 'echo "${{ github.event.head_commit.message }}"'), "drift.yml"), "expression inside a run script")

    def test_the_deploy_workflow_starts_by_hand_and_by_a_call_and_by_nothing_else(self):
        self.assertEqual(self.lint(GOOD_DEPLOY, "deploy-hub.yml"), [])
        for trigger in ("on:\n  workflow_dispatch:\n  workflow_call:\n  push:\n    branches: [main]\n", "on: [workflow_dispatch, workflow_call, push]", "on: push", "on:\n  schedule:\n    - cron: '0 3 * * *'\n",
                        "on:\n  workflow_dispatch:\n", "on:\n  workflow_call:\n", "on: workflow_dispatch", "on:\n  workflow_dispatch:\n  workflow_call:\n  schedule:\n    - cron: '0 3 * * *'\n"):
            problems = self.lint(GOOD_DEPLOY.replace(DEPLOY_ON, trigger), "deploy-hub.yml")
            self.assertFinding(problems, "`workflow_dispatch` (by hand) and `workflow_call`")
        self.assertEqual(self.lint(GOOD_DEPLOY.replace(DEPLOY_ON, "on: [workflow_call, workflow_dispatch]\n"), "deploy-hub.yml"), [], "the order does not matter")

    def test_a_checkout_of_the_hub_is_the_workflows_own_repository_at_its_own_commit_because_a_plain_one_is_the_callers(self):
        own = "          repository: ${{ job.workflow_repository }}\n          ref: ${{ job.workflow_sha }}\n"
        self.assertIn(own, GOOD_DEPLOY)
        for what, text in {
            "no repository and no ref": GOOD_DEPLOY.replace(own, ""),
            "no ref": GOOD_DEPLOY.replace("          ref: ${{ job.workflow_sha }}\n", ""),
            "no repository": GOOD_DEPLOY.replace("          repository: ${{ job.workflow_repository }}\n", ""),
            "the caller's commit": GOOD_DEPLOY.replace("ref: ${{ job.workflow_sha }}", "ref: ${{ github.sha }}"),
            "the caller's repository": GOOD_DEPLOY.replace("repository: ${{ job.workflow_repository }}", "repository: ${{ github.repository }}"),
            "another repository": GOOD_DEPLOY.replace("repository: ${{ job.workflow_repository }}", "repository: someone/else"),
            "the repository twice": GOOD_DEPLOY.replace(own, own + "          repository: someone/else\n"),
            "the commit twice": GOOD_DEPLOY.replace(own, own + "          ref: main\n"),
            "only in a comment": GOOD_DEPLOY.replace(own, "          # repository: ${{ job.workflow_repository }}\n          # ref: ${{ job.workflow_sha }}\n"),
        }.items():
            with self.subTest(what):
                self.assertFinding(self.lint(text, "deploy-hub.yml"), "without `repository: ${{ job.workflow_repository }}` and `ref: ${{ job.workflow_sha }}`")
        # only the Hub is called, so only its checkout is held to this; the other workflows run in their own repository
        self.assertEqual(self.lint(GOOD_DRIFT, "drift.yml"), [])
        self.assertEqual(self.lint(GOOD_CHECKS), [])

    def test_the_hub_never_reads_the_callers_commit_or_repository_and_a_comment_may_say_so(self):
        for name in ("GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_WORKFLOW_SHA", "GITHUB_WORKFLOW_REF", "${{ github.sha }}", "${{ github.repository }}", "${{ github.workflow_sha }}", "${{ github.workflow_ref }}"):
            with self.subTest(name):
                in_a_script = GOOD_DEPLOY.replace('run: echo "$ACTION"', f'run: echo "{name}"')
                self.assertFinding(self.lint(in_a_script, "deploy-hub.yml"), "is the caller's when this workflow is called")
                in_the_environment = GOOD_DEPLOY.replace("      ACTION: ${{ inputs.action }}\n", f"      ACTION: ${{{{ inputs.action }}}}\n      COMMIT: {name}\n")
                self.assertFinding(self.lint(in_the_environment, "deploy-hub.yml"), "is the caller's when this workflow is called")
        for fine in ("# GITHUB_SHA is the caller's", "# ${{ github.sha }} too"):
            self.assertEqual(self.lint(GOOD_DEPLOY.replace("    steps:\n", f"    steps:\n      {fine}\n"), "deploy-hub.yml"), [], fine)
        self.assertEqual(self.lint(GOOD_DEPLOY.replace('run: echo "$ACTION"', 'run: echo "$GITHUB_RUN_ID $GITHUB_RUN_NUMBER"'), "deploy-hub.yml"), [], "the run's own numbers are the caller's and unique there: they are meant")
        # the workflows that are not called read their own commit from the plain context
        self.assertEqual(self.lint(GOOD_DRIFT.replace('run: echo "$ACTION"', 'run: echo "$GITHUB_SHA"'), "drift.yml"), [])

    def test_the_deploy_workflow_runs_only_for_the_owner_on_main_and_never_twice_at_once(self):
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("github.actor == 'tinodo' && ", ""), "deploy-hub.yml"), "only for the owner")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace(" && github.ref == 'refs/heads/main'", ""), "deploy-hub.yml"), "only for the owner")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("concurrency:\n  group: hub\n", ""), "deploy-hub.yml"), "concurrency")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    continue-on-error: true\n"), "deploy-hub.yml"), "continue-on-error")

    def test_the_guard_is_checked_for_what_it_says_not_for_the_words_in_it(self):
        # "&&" turned into "||" lets anyone on main, or the owner on any branch, through: the words are all still there
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("'tinodo' && github.ref", "'tinodo' || github.ref"), "deploy-hub.yml"), "only for the owner")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("github.ref == 'refs/heads/main'", "github.ref != 'refs/heads/main'"), "deploy-hub.yml"), "only for the owner")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("github.actor == 'tinodo'", "github.actor == 'someone'"), "deploy-hub.yml"), "only for the owner")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("github.actor == 'tinodo' && github.ref == 'refs/heads/main'", "always()"), "deploy-hub.yml"), "only for the owner")
        # the same words in a step's own condition do not make the job guarded
        moved = GOOD_DEPLOY.replace("    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'\n", "") \
                           .replace("        if: inputs.action == 'deploy'", "        if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'")
        self.assertFinding(self.lint(moved, "deploy-hub.yml"), "only for the owner")
        # quotes and a ${{ }} wrapper are the same condition
        self.assertEqual(self.lint(GOOD_DEPLOY.replace("if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'",
                                                       "if: ${{ github.actor == 'tinodo' && github.ref == 'refs/heads/main' }}"), "deploy-hub.yml"), [])

    def test_a_second_job_cannot_slip_past_the_guard(self):
        second = GOOD_DEPLOY + "  other:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
        problems = self.lint(second, "deploy-hub.yml")
        self.assertFinding(problems, "exactly one job")
        self.assertFinding(problems, "job `other` must run only for the owner")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("jobs:\n  hub:", "jobs:\n  hub:\n    needs: []") .replace("    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'\n", ""), "deploy-hub.yml"), "only for the owner")

    def test_valid_yaml_that_this_reader_does_not_follow_is_refused_not_ignored(self):
        body = "    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
        for header in ("  probe: # a comment\n", "  probe: &anchor\n", "  \"probe\":\n", "  'probe':\n", "  probe : \n", "   probe:\n", "  ? probe\n  :\n"):
            problems = self.lint(GOOD_DEPLOY + header + body, "deploy-hub.yml")
            self.assertFinding(problems, "not a plain job header")
        flow = GOOD_DEPLOY.split("jobs:")[0] + "jobs: {hub: {runs-on: ubuntu-latest, steps: []}}\n"
        self.assertFinding(self.lint(flow, "deploy-hub.yml"), "exactly one job, not 0")
        commented = GOOD_DEPLOY.replace("jobs:\n", "jobs: # all of them\n")
        self.assertFinding(self.lint(commented, "deploy-hub.yml"), "exactly one job, not 0")

    def test_a_condition_that_goes_on_is_not_the_guard(self):
        guard = "    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'\n"
        for tail in ("      || true\n", "      || github.ref == 'refs/heads/x'\n", "      # a comment, then\n      || true\n"):
            self.assertFinding(self.lint(GOOD_DEPLOY.replace(guard, guard + tail), "deploy-hub.yml"), "only for the owner")
        folded = GOOD_DEPLOY.replace(guard, "    if: >-\n      github.actor == 'tinodo' && github.ref == 'refs/heads/main'\n")
        self.assertFinding(self.lint(folded, "deploy-hub.yml"), "only for the owner")
        commented = GOOD_DEPLOY.replace(guard, guard.rstrip("\n") + "  # the owner, on main\n")
        self.assertEqual(self.lint(commented, "deploy-hub.yml"), [])

    def test_a_guard_that_is_only_text_inside_a_quoted_value_is_refused(self):
        guard = "    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'\n"
        name = "    name: Hub ({{ inputs.action }})\n"
        unguarded = GOOD_DEPLOY.replace(guard, "")
        self.assertIn(name, unguarded)
        # YAML reads each of these as one string, so the job has no `if:` at all, yet every word of the guard is still on a line of its own
        decoys = {
            "the job's name": unguarded.replace(name, '    name: "Hub\n' + guard + '    "\n'),
            "runs-on": unguarded.replace("    runs-on: ubuntu-latest\n", '    runs-on: "ubuntu-latest\n' + guard + '    "\n'),
            "a single-quoted value": unguarded.replace(name, "    name: 'Hub\n" + guard + "    '\n"),
            "a map in braces": unguarded.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    outputs: {\n" + guard + "    }\n"),
            "a list in brackets": unguarded.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    needs: [\n" + guard + "    ]\n"),
        }
        for where, text in decoys.items():
            self.assertIn(guard, text, where)
            self.assertFinding(self.lint(text, "deploy-hub.yml"), "goes on over the next lines")
            if yaml:  # where a real parser can read the file, it agrees that the job has no `if` of its own
                try:
                    job = yaml.safe_load(text)["jobs"]["hub"]
                except yaml.YAMLError:
                    continue
                self.assertNotIn("if", job, where)

    @unittest.skipUnless(yaml, "no YAML parser on this machine: CI parses the deploy workflow with Ruby (checks.yml)")
    def test_a_real_parser_agrees_that_the_deploy_workflow_is_guarded(self):
        document = yaml.safe_load((ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8"))
        jobs = document["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(next(iter(jobs.values()))["if"], wl.OWNER_GUARD)
        self.assertEqual(sorted(document.get("on", document.get(True))), ["workflow_call", "workflow_dispatch"])  # YAML 1.1 reads the key `on` as true
        self.assertIn("concurrency", document)

    def test_a_script_that_goes_on_over_several_lines_is_read_to_its_end(self):
        one_line = 'run: |\n          echo "$VALUE"'
        self.assertIn(one_line, GOOD_CHECKS)
        plain = GOOD_CHECKS.replace(one_line, "run: echo hi\n            ${{ github.event.issue.title }}")
        self.assertFinding(self.lint(plain), "expression inside a run script")
        quoted = GOOD_CHECKS.replace(one_line, 'run: "echo hi\n            ${{ github.event.issue.title }}"')
        self.assertFinding(self.lint(quoted), "goes on over the next lines")
        self.assertEqual(self.lint(GOOD_CHECKS.replace(one_line, "run: echo hi\n            echo there")), [])

    def test_quotes_that_close_on_their_line_and_quotes_inside_scripts_are_fine(self):
        values = [
            'run-name: "the owner\'s \\"quoted\\" name"',
            "run-name: 'it''s'",
            "run-name: it's plain",
            "run-name: \"x\" # it's",
            "run-name: contains(github.ref, 'x')",
            "run-name: ''",
            'run-name: ""',
            "env: {A: \"1\", B: '2', C: [x, \"y\"]}",
            "env: [a, 'b', \"c\"] # [",
        ]
        for value in values:
            self.assertEqual(self.lint(GOOD_CHECKS.replace("name: Checks\n", "name: Checks\n" + value + "\n")), [], value)
        script = GOOD_CHECKS.replace('echo "$VALUE"', "echo \"it's\" 'half\n          echo \"half\n          echo {")
        self.assertEqual(self.lint(script), [])

    def test_a_character_that_readers_do_not_agree_about_is_refused(self):
        for char in ("\u2028", "\u2029", "\x85", "\x0c", "\x00", "\x1c"):
            problems = self.lint(GOOD_CHECKS.replace("name: Checks", "name: Che" + char + "cks"))
            self.assertFinding(problems, f"U+{ord(char):04X}")
            self.assertTrue(problems[0].startswith("checks.yml:1:"), problems)

    def test_the_deploy_workflow_never_reads_a_budget_by_name_or_the_text_of_a_not_found_answer(self):
        # The Budgets API answers a missing budget with "Not Found(...)", and the first run failed on a pattern that expected
        # other words. A budget is looked for in the list of the group's budgets; only the delete addresses it by name.
        text = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if "budgets/meternaut-hub" in line:
                self.assertIn("--method delete", line, line)
        self.assertNotIn("budget.err", text)
        # a command inside a condition has its failure swallowed (set -e does not apply there): the list is read by an assignment
        self.assertIsNone(re.search(r'\[\s*"\$\(az ', text))
        self.assertGreaterEqual(text.count("value[?name=='meternaut-hub']"), 1)

    def test_a_tab_in_the_indentation_is_refused(self):
        self.assertFinding(self.lint(GOOD_CHECKS.replace("    runs-on: ubuntu-latest", "\truns-on: ubuntu-latest")), "a tab in the indentation")
        self.assertFinding(self.lint(GOOD_DEPLOY.replace("    steps:", "  \tsteps:"), "deploy-hub.yml"), "a tab in the indentation")

    def test_the_deploy_workflow_that_does_not_sign_in_is_a_finding(self):
        text = GOOD_DEPLOY.replace(f"      - name: Sign in\n        uses: azure/login@{LOGIN} # v3.1.0\n        with:\n          client-id: ${{{{ secrets.AZURE_CLIENT_ID }}}}\n", "")
        self.assertFinding(self.lint(text, "deploy-hub.yml"), "does not sign in")

    def test_main(self):
        (self.dir / "a.yml").write_text(textwrap.dedent(GOOD_CHECKS).lstrip("\n"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(wl.main(["--dir", str(self.dir)]), 0)
        self.assertIn("1 workflow(s) checked, 0 finding(s).", out.getvalue())
        (self.dir / "b.yml").write_text(textwrap.dedent(GOOD_CHECKS.replace(SHA, "v4")).lstrip("\n"), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(wl.main(["--dir", str(self.dir)]), 1)
        self.assertIn("b.yml:", out.getvalue())
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(wl.main(["--dir", empty.name]), 2)


if __name__ == "__main__":
    unittest.main()
