"""Tests of tools/hub-local.py, the runner that runs the Hub workflow's own steps on the owner's machine.

No network and no subscription: the az session is a fake in memory, git is the real git in repositories that these tests make for themselves (under local/test-scratch, which git ignores), and
bash is Git's bash when the machine has one (the tests that need it are skipped otherwise). Nothing here reads or writes the owner's configuration."""
import argparse
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("hub_local", ROOT / "tools" / "hub-local.py")
hub = importlib.util.module_from_spec(SPEC)
sys.modules["hub_local"] = hub
SPEC.loader.exec_module(hub)
SOURCE = (ROOT / "tools" / "hub-local.py").read_text(encoding="utf-8")
REAL_WORKFLOW = hub.load_workflow(ROOT / ".github" / "workflows" / "deploy-hub.yml")
SCRATCH_BASE = ROOT / "local" / "test-scratch"

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
TENANT = "66666666-7777-8888-9999-000000000000"
PREVIOUS = "99999999-8888-7777-6666-555555555555"
FAKE_VALUES = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION, "AZURE_TENANT_ID": TENANT, "AZURE_CLIENT_ID": "", "ENV_RESOURCE_GROUP": "rg-of-the-project",
               "ENV_LOCATION": "examplelocation", "ENV_VNET_PREFIX": "10.0.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.0.0.0/27", "ENV_DNS_SERVERS": "10.0.0.4", "ENV_OWNER": "someone@example.com",
               "ENV_BUDGET_AMOUNT": "25", "ENV_ALERT_EMAILS": "someone@example.com", "CONSOLE_APP_CLIENT_ID": "", "CONSOLE_PEOPLE": '[{"name": "Someone"}]', "CONSOLE_HOST_NAME": "",
               "MAIL_SENDER": ""}
CONFIG_TEXT = "# fake values\n" + "".join(f"{name}={value}\n" for name, value in FAKE_VALUES.items())


def find_bash():
    try:
        return hub.find_bash()
    except hub.HubLocalError:
        return None


BASH = find_bash()


def git_available() -> bool:
    return hub.run_git(["--version"], ROOT)[0] == 0


def scratch():
    SCRATCH_BASE.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=SCRATCH_BASE, ignore_cleanup_errors=True)


def git(*args, cwd):
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(path: Path, ignore_local: bool = True) -> Path:
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)
    git("config", "user.name", "Test", cwd=path)
    (path / ".gitignore").write_text("/local/\n" if ignore_local else "# nothing ignored\n", encoding="utf-8")
    (path / "tracked.txt").write_text("x\n", encoding="utf-8")
    git("add", "-A", cwd=path)
    git("commit", "-q", "-m", "first", cwd=path)
    return path


TEMPLATE: dict = {}


def copy_repo(target: Path) -> Path:
    """A repository like make_repo's, copied from one that is made once for all the tests: git is slow to start on some machines."""
    if "path" not in TEMPLATE:
        SCRATCH_BASE.mkdir(parents=True, exist_ok=True)
        TEMPLATE["holder"] = Path(tempfile.mkdtemp(dir=SCRATCH_BASE, prefix="template-"))
        TEMPLATE["path"] = make_repo(TEMPLATE["holder"] / "repo")
    shutil.copytree(TEMPLATE["path"], target)
    return target


def tearDownModule():
    if "holder" in TEMPLATE:
        hub.remove_tree(TEMPLATE["holder"])


def make_args(action="what-if", **flags):
    args = argparse.Namespace(action=action, minutes=None, public_ai_gateway_requested=False, plant_public_ip=False, yes=False, allow_dirty=False, dry_run=False, workflow=None, init=False,
                              from_github=False)
    args.__dict__.update(flags)
    return args


def plan_for(workflow, action, values=None, **flags):
    args = make_args(action, **flags)
    values = FAKE_VALUES if values is None else values
    ctx = hub.Context(inputs=hub.input_values(workflow, args), variables=values, secrets=values, runner_temp="C:/x/rt/1", planning=True,
                      step_ids={step.id: step.index for step in workflow.steps if step.id},
                      github={"run_number": 288, "run_id": 1, "actor": hub.LOCAL_ACTOR, "ref": hub.LOCAL_REF, "ref_name": "main", "sha": "a" * 40, "event_name": "workflow_dispatch",
                              "run_attempt": 1, "workspace": "C:/x"})
    return hub.build_plan(workflow, ctx, [], []), ctx


def kinds(plan):
    return sorted(entry.replacement.kind for entry in plan.entries if entry.replacement and entry.verdict is not False)


class TheRealWorkflowIsPlanned(unittest.TestCase):
    """The parser and the planner against the real .github/workflows/deploy-hub.yml, whatever it holds now: only what the format and the rules guarantee is asserted."""

    def test_the_file_is_read_whole_with_its_actions_and_inputs(self):
        self.assertGreater(len(REAL_WORKFLOW.steps), 50)
        for action in ("what-if", "model-side", "base", "foundry", "cases", "cases-run", "operator", "aigateway"):
            self.assertIn(action, REAL_WORKFLOW.actions)
        self.assertEqual(REAL_WORKFLOW.actions[0], "what-if")
        for name in ("action", "minutes", "public_ai_gateway_requested", "plant_public_ip"):
            self.assertIn(name, REAL_WORKFLOW.inputs)
        self.assertIs(REAL_WORKFLOW.inputs["public_ai_gateway_requested"].default, False)
        self.assertEqual(REAL_WORKFLOW.inputs["minutes"].default, "20")
        self.assertEqual(REAL_WORKFLOW.job_condition, f"github.actor == '{hub.LOCAL_ACTOR}' && github.ref == '{hub.LOCAL_REF}'")
        self.assertEqual([step.unknown_keys for step in REAL_WORKFLOW.steps if step.unknown_keys], [], "a step key that this tool does not read would be ignored")

    def test_every_run_script_is_kept_whole_and_none_holds_an_expression(self):
        scripts = [step for step in REAL_WORKFLOW.steps if step.run is not None]
        self.assertGreater(len(scripts), 50)
        for step in scripts:
            self.assertTrue(step.run.strip(), step.name)
            self.assertNotIn("${{", step.run, step.name)
            self.assertNotIn("\r", step.run, "the workflow's CRLF line ends (git on Windows) are not in a script")

    def test_every_action_has_a_plan_that_resolves_without_an_unknown_expression(self):
        for action in REAL_WORKFLOW.actions:
            with self.subTest(action=action):
                plan, _ = plan_for(REAL_WORKFLOW, action, public_ai_gateway_requested=True)
                self.assertEqual(plan.problems, [])
                running = [entry for entry in plan.entries if entry.verdict is not False]
                self.assertGreaterEqual(len(running), 6, "the common steps and the steps of the action")
                self.assertLess(len(running), len(REAL_WORKFLOW.steps) - 10, "most steps belong to other actions")

    def test_every_step_runs_for_some_action_so_the_expressions_of_all_of_them_were_checked(self):
        seen = set()
        for action in REAL_WORKFLOW.actions:
            plan, _ = plan_for(REAL_WORKFLOW, action, public_ai_gateway_requested=True)
            seen |= {entry.step.index for entry in plan.entries if entry.verdict is not False}
        self.assertEqual(sorted(set(range(len(REAL_WORKFLOW.steps))) - seen), [], "a step that no action runs is never checked")

    def test_always_and_outcome_conditions_evaluate(self):
        plan, _ = plan_for(REAL_WORKFLOW, "cases")
        cleanup = [entry for entry in plan.entries if entry.replacement and entry.replacement.kind == "cases-publish-cleanup"]
        self.assertEqual(len(cleanup), 1)
        self.assertIs(cleanup[0].verdict, True, "always() and steps.<publish>.outcome != 'skipped': the publish step is in the plan, so its outcome is not skipped")
        plan, _ = plan_for(REAL_WORKFLOW, "what-if")
        cleanup = [entry for entry in plan.entries if entry.replacement and entry.replacement.kind == "cases-publish-cleanup"]
        self.assertEqual(cleanup, [], "for what-if the publish step is skipped, and so is its clean-up")
        last = plan.entries[-1]
        self.assertIs(last.verdict, True, "the closing step has always(): it runs whatever came before")

    def test_a_condition_that_reads_what_an_earlier_step_makes_is_decided_when_the_run_reaches_it(self):
        plan, _ = plan_for(REAL_WORKFLOW, "cases")
        maybe = [entry for entry in plan.entries if entry.verdict is hub.UNKNOWN]
        self.assertTrue(maybe, "a step reads steps.<id>.outputs: its condition is not known before the run")
        for entry in maybe:
            self.assertIn("steps.", entry.step.condition)

    def test_the_cases_action_replaces_the_publish_through_the_operator_and_nothing_else_needs_a_token(self):
        plan, _ = plan_for(REAL_WORKFLOW, "cases")
        self.assertEqual([k for k in kinds(plan) if k.startswith("cases")], ["cases-pack", "cases-publish", "cases-publish-cleanup"])
        for action in REAL_WORKFLOW.actions:
            plan, _ = plan_for(REAL_WORKFLOW, action, public_ai_gateway_requested=True)
            self.assertEqual(plan.problems, [], action)
            for entry in plan.entries:
                if entry.verdict is not False and entry.step.run and any(marker in entry.step.run for marker in hub.OIDC_MARKERS):
                    self.assertIsNotNone(entry.replacement, f"{action}: {entry.step.name} asks for a token and has to have a replacement")

    def test_the_probe_goes_on_without_the_token_and_says_so(self):
        plan, _ = plan_for(REAL_WORKFLOW, "operator-probe")
        self.assertIn("no-token", kinds(plan))

    def test_the_checkout_the_python_set_up_and_every_sign_in_are_replaced(self):
        plan, _ = plan_for(REAL_WORKFLOW, "foundry")
        found = kinds(plan)
        self.assertEqual(found.count("checkout"), 1)
        self.assertEqual(found.count("python"), 1)
        self.assertGreaterEqual(found.count("az-session"), 2, "the first sign-in and the ones that renew it")

    def test_an_input_that_the_workflow_does_not_have_is_an_error(self):
        text = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("inputs.minutes", "inputs.nothere", 1)
        workflow = hub.parse_workflow(text)
        plan, _ = plan_for(workflow, "page-latency")
        self.assertTrue(any("inputs.nothere" in problem for problem in plan.problems), plan.problems)

    def test_a_variable_that_the_configuration_does_not_define_stops_the_plan_before_anything_runs(self):
        values = {name: value for name, value in FAKE_VALUES.items() if name != "ENV_LOCATION"}
        plan, _ = plan_for(REAL_WORKFLOW, "what-if", values=values)
        self.assertTrue(any("vars.ENV_LOCATION is not defined" in problem for problem in plan.problems), plan.problems)

    def test_a_step_that_needs_a_token_and_has_no_replacement_stops_the_plan(self):
        text = textwrap.dedent("""\
            name: x
            on:
              workflow_dispatch:
                inputs:
                  action:
                    type: choice
                    options:
                      - what-if
            jobs:
              hub:
                steps:
                  - name: Asks for a token
                    run: |
                      curl --config - "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=x"
                  - name: Uses another action
                    uses: someone/else@0123456789012345678901234567890123456789
                  - name: Expression in a script
                    run: echo "${{ inputs.action }}"
            """)
        plan, _ = plan_for(hub.parse_workflow(text), "what-if")
        self.assertEqual(len(plan.problems), 3, plan.problems)
        self.assertIn("OpenID Connect token", plan.problems[0])
        self.assertIn("someone/else", plan.problems[1])
        self.assertIn("${{", plan.problems[2])

    def test_a_job_condition_that_is_not_true_for_a_local_run_stops_the_plan(self):
        text = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("github.actor == 'tinodo'", "github.actor == 'somebody'", 1)
        plan, _ = plan_for(hub.parse_workflow(text), "what-if")
        self.assertTrue(any("condition of the job" in problem for problem in plan.problems), plan.problems)

    def test_the_workflow_text_does_not_depend_on_its_line_ends(self):
        text = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8")
        as_lf, as_crlf = text.replace("\r\n", "\n"), text.replace("\r\n", "\n").replace("\n", "\r\n")
        one, two = hub.parse_workflow(as_lf), hub.parse_workflow(as_crlf)
        self.assertEqual([step.run for step in one.steps], [step.run for step in two.steps])
        self.assertEqual([step.condition for step in one.steps], [step.condition for step in two.steps])


class TheYamlReader(unittest.TestCase):
    def parse(self, text):
        return hub.parse_yaml(textwrap.dedent(text))

    def test_mappings_sequences_scalars_and_comments(self):
        tree = self.parse("""\
            # a comment
            a: one
            b: 'it''s'   # a trailing comment
            c: "x \\"quoted\\" y"
            d:
              - first
              - key: value
                other: thing
              -
                nested: here
            e:   # a comment after a key
              f: g
            """)
        self.assertEqual(tree["a"], "one")
        self.assertEqual(tree["b"], "it's")
        self.assertEqual(tree["c"], 'x "quoted" y')
        self.assertEqual(tree["d"][0], "first")
        self.assertEqual(dict(tree["d"][1]), {"key": "value", "other": "thing"})
        self.assertEqual(dict(tree["d"][2]), {"nested": "here"})
        self.assertEqual(dict(tree["e"]), {"f": "g"})

    def test_a_plain_value_keeps_its_quotes_colons_and_braces_but_not_a_trailing_comment(self):
        tree = self.parse("""\
            if: inputs.action == 'what-if' && steps.x.outputs.y != 'true'
            run: az group show --query "{name:name, location:location}" --output table
            uses: actions/checkout@abc # v7
            """)
        self.assertEqual(tree["if"], "inputs.action == 'what-if' && steps.x.outputs.y != 'true'")
        self.assertEqual(tree["run"], 'az group show --query "{name:name, location:location}" --output table')
        self.assertEqual(tree["uses"], "actions/checkout@abc")

    def test_a_literal_block_keeps_its_lines_its_blank_lines_and_its_comments(self):
        tree = self.parse("""\
            run: |
              # a bash comment stays
              echo one

                indented more
              echo two
            next: |-
              no final newline
            keep: |+
              kept

            last: end
            """)
        self.assertEqual(tree["run"], "# a bash comment stays\necho one\n\n  indented more\necho two\n")
        self.assertEqual(tree["next"], "no final newline")
        self.assertEqual(tree["keep"], "kept\n\n")
        self.assertEqual(tree["last"], "end")

    def test_what_is_not_read_is_an_error_with_a_line_number(self):
        for text, fragment in (("a: [1, 2]\n", "line 1"), ("a: {b: c}\n", "line 1"), ("a: >\n  folded\n", "folded"), ("a: &anchor x\n", "line 1"), ("a: *alias\n", "line 1"),
                               ("a: !tag x\n", "line 1"), ("a: 'open\n", "closing quote"), ('a: "open\n', "closing quote"), ("a: b\na: c\n", "twice"),
                               ("a:\n\tb: c\n", "tab"), ("a: b\n  c: d\n", "unexpected indentation"), ("just text\n", "key: value"), ('a: "x" y\n', "follows the closing quote"),
                               ('a: "\\q"\n', "escape")):
            with self.subTest(text=text), self.assertRaises(hub.WorkflowFormatError) as caught:
                hub.parse_yaml(text)
            self.assertIn(fragment, str(caught.exception))

    def test_a_workflow_with_another_default_shell_or_two_jobs_or_a_step_with_both_run_and_uses_is_refused(self):
        base = "on:\n  workflow_dispatch:\n    inputs:\n      action:\n        type: choice\n        options:\n          - a\n"
        for text, fragment in ((base + "defaults:\n  run:\n    shell: pwsh\njobs:\n  j:\n    steps:\n      - run: x\n", "only bash"),
                               (base + "jobs:\n  j:\n    steps:\n      - run: x\n  k:\n    steps:\n      - run: y\n", "exactly one job"),
                               (base + "jobs:\n  j:\n    steps:\n      - run: x\n        uses: y/z@1\n", "either run or uses"),
                               (base + "jobs:\n  j:\n    steps:\n      - name: no body\n", "either run or uses"),
                               (base + "jobs:\n  j:\n    steps:\n      - id: a\n        run: x\n      - id: a\n        run: y\n", "used twice"),
                               ("jobs:\n  j:\n    steps:\n      - run: x\n", "inputs")):
            with self.subTest(fragment=fragment), self.assertRaises(hub.WorkflowFormatError) as caught:
                hub.parse_workflow(text)
            self.assertIn(fragment, str(caught.exception))


class Expressions(unittest.TestCase):
    def context(self, planning=False, **inputs):
        ctx = hub.Context(inputs={"action": "cases", "minutes": "20", "flag": False, **inputs}, variables={"V": "vee"}, secrets={"S": "ess"}, runner_temp="C:/rt",
                          step_ids={"a": 0, "b": 1, "c": 2}, planning=planning, github={"run_number": 288, "run_id": 5, "actor": "tinodo", "ref": "refs/heads/main", "sha": "abc"})
        ctx.current_index = 2
        ctx.steps["a"] = hub.StepState("success", {"x": "one"})
        ctx.steps["b"] = hub.StepState("skipped", {})
        return ctx

    def check(self, text, expected, **kwargs):
        ctx = self.context(**kwargs)
        self.assertEqual(hub.evaluate(hub.parse_expression(text), ctx), expected, text)

    def test_the_operators_and_their_precedence(self):
        for text, expected in (("true && false", False), ("true || false", True), ("false || false", False), ("!false", True), ("!!true", True), ("true || false && false", True),
                               ("(true || false) && false", False), ("!true == false", True), ("1 == 1", True), ("1 != 2", True), ("'a' == 'a'", True), ("'a' != 'a'", False),
                               ("null == ''", True), ("null == 0", True), ("true == 1", True), ("'abc' == 1", False), ("'1' == 1", True), ("'' == 0", True)):
            self.check(text, expected)

    def test_strings_are_compared_without_regard_to_case_as_the_workflow_runner_does(self):
        self.check("'What-If' == 'what-if'", True)
        self.check("inputs.action == 'CASES'", True)
        self.check("inputs.action != 'cases'", False)

    def test_and_and_or_give_the_value_of_the_operand_that_decides_as_github_does(self):
        self.check("'' || 'fallback'", "fallback")
        self.check("'first' || 'second'", "first")
        self.check("'first' && 'second'", "second")
        self.check("'' && 'second'", "")
        self.check("0 || steps.a.outputs.x", "one")

    def test_the_contexts_that_a_condition_may_read(self):
        self.check("inputs.action == 'cases' && steps.a.outputs.x == 'one'", True)
        self.check("steps.b.outcome == 'skipped'", True)
        self.check("steps.a.outcome != 'skipped'", True)
        self.check("steps.a.outputs.missing == ''", True)
        self.check("vars.V == 'vee' && secrets.S == 'ess'", True)
        self.check("github.run_number == 288", True)
        self.check("runner.temp == 'C:/rt'", True)
        self.check("job.status == 'success'", True)
        self.check("always()", True)
        self.check("success()", True)
        self.check("failure()", False)
        self.check("cancelled()", False)

    def test_the_status_functions_follow_the_state_of_the_job(self):
        ctx = self.context()
        ctx.job_status = "failure"
        for text, expected in (("success()", False), ("failure()", True), ("always()", True), ("cancelled()", False)):
            self.assertIs(hub.evaluate(hub.parse_expression(text), ctx), expected, text)
        ctx.job_status, ctx.cancelled = "cancelled", True
        self.assertIs(hub.evaluate(hub.parse_expression("cancelled()"), ctx), True)
        self.assertIs(hub.condition_result("inputs.action == 'cases'", ctx), False, "the implicit success() of a step without a status function")
        self.assertIs(hub.condition_result("always() && inputs.action == 'cases'", ctx), True)
        self.assertIs(hub.condition_result(None, ctx), False)

    def test_a_function_that_is_not_known_is_refused(self):
        for text in ("contains('abc', 'a')", "startsWith('abc', 'a')", "format('{0}', 'x')", "fromJSON('1')", "toJSON(inputs)", "hashFiles('x')", "join(x, 'y')", "evil()", "always(1)",
                     "github.event.x()", "success"):
            with self.subTest(text=text), self.assertRaises(hub.ExprError):
                hub.evaluate(hub.parse_expression(text), self.context())

    def test_hostile_and_odd_inputs_are_refused_without_running_anything(self):
        marker = ROOT / "local" / "test-scratch" / "hostile-marker"
        marker.unlink(missing_ok=True)
        for text in ("__import__('os').system('echo x')", "'a' + 'b'", "inputs.action[0]", "inputs['action']", "steps.a.outputs.x.y", "steps.a", "steps.nothere.outputs.x", "steps.c.outputs.x",
                     "env.A.B", "github.event.inputs.action", "needs.a.result", "matrix.os", "secrets", "vars.NOPE", "inputs.nope", "runner.os", "job.nope", "1 < 2", "a && ",
                     "(true", "true)", "&& true", "'unterminated", "", "   ", "!", "true true", "$(touch x)", "`echo x`", "inputs.action; rm -rf /", "x" * (hub.MAX_EXPRESSION_LENGTH + 1),
                     "(" * 500 + "true" + ")" * 500, "!" * 500 + "true", "1e3", "0x10", "-1"):
            with self.subTest(text=text[:40]), self.assertRaises(hub.ExprError):
                hub.evaluate(hub.parse_expression(text), self.context())
        self.assertFalse(marker.exists())

    def test_the_source_never_hands_text_to_the_interpreter(self):
        for word in (r"\beval\s*\(", r"\bexec\s*\(", r"__import__", r"\bos\.system\b", r"shell\s*=\s*True", r"\bcompile\s*\(", r"literal_eval", r"importlib\.import_module"):
            code = re.sub(r"re\.compile\(", "re_compile(", SOURCE)
            self.assertIsNone(re.search(word, code), word)

    def test_a_value_that_holds_an_expression_is_text_and_is_never_read_again(self):
        ctx = self.context()
        ctx.steps["a"] = hub.StepState("success", {"x": "${{ secrets.S }} and ${{ steps.zzz.outputs.q }}"})
        self.assertEqual(hub.interpolate("got ${{ steps.a.outputs.x }}", ctx), "got ${{ secrets.S }} and ${{ steps.zzz.outputs.q }}")

    def test_interpolation_formats_values_as_github_does(self):
        ctx = self.context(flag=True)
        self.assertEqual(hub.interpolate("r${{ github.run_number }}-${{ inputs.flag }}-${{ null }}|${{ true }}|${{ 'x' }}|${{ 1 }}", ctx), "r288-true-|true|x|1")
        self.assertEqual(hub.interpolate("no expression", ctx), "no expression")
        self.assertEqual(hub.interpolate("${{ inputs.action }}/${{ vars.V }}", ctx), "cases/vee")

    def test_a_problem_in_an_interpolation_is_collected_and_the_text_is_kept(self):
        problems = []
        text = hub.interpolate("a ${{ vars.NOPE }} b ${{ inputs.action }}", self.context(), problems, "where")
        self.assertEqual(text, "a ${{ vars.NOPE }} b cases")
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("where: vars.NOPE is not defined in hub-local.env"))

    def test_what_a_dry_run_cannot_know_yet_stays_unknown_and_the_logic_works_with_it(self):
        ctx = self.context(planning=True)
        ctx.steps["a"] = hub.StepState(hub.UNKNOWN, hub.UNKNOWN)

        def value(text):
            return hub.evaluate(hub.parse_expression(text), ctx)
        self.assertIs(value("steps.a.outputs.x"), hub.UNKNOWN)
        self.assertIs(value("steps.a.outputs.x == 'x'"), hub.UNKNOWN)
        self.assertIs(value("!(steps.a.outputs.x == 'x')"), hub.UNKNOWN)
        self.assertIs(value("false && steps.a.outputs.x == 'x'"), False)
        self.assertIs(value("steps.a.outputs.x == 'x' && false"), False)
        self.assertIs(value("true && steps.a.outputs.x == 'x'"), hub.UNKNOWN)
        self.assertIs(value("true || steps.a.outputs.x == 'x'"), True)
        self.assertIs(value("steps.a.outputs.x == 'x' || true"), True)
        self.assertIs(value("false || steps.a.outputs.x == 'x'"), hub.UNKNOWN)
        self.assertIs(hub.condition_result("steps.a.outputs.x == 'x'", ctx), hub.UNKNOWN)
        self.assertIs(hub.condition_result("inputs.action == 'what-if' && steps.a.outputs.x == 'x'", ctx), False)

    def test_a_reference_that_a_short_circuit_would_skip_is_still_checked_in_a_plan(self):
        ctx = self.context(planning=True)
        with self.assertRaises(hub.ExprError):
            hub.condition_result("false && steps.nothere.outputs.x == 'x'", ctx)

    def test_a_step_that_is_skipped_has_no_outputs_and_a_step_not_yet_run_is_unknown_only_in_a_plan(self):
        ctx = self.context()
        ctx.steps.clear()
        ctx.current_index = 2
        self.assertEqual(hub.evaluate(hub.parse_expression("steps.a.outputs.x"), ctx), "")
        ctx.planning = True
        self.assertIs(hub.evaluate(hub.parse_expression("steps.a.outputs.x"), ctx), hub.UNKNOWN)


class CommandFilesAndOutput(unittest.TestCase):
    def test_name_value_lines_and_blocks(self):
        text = "a=1\nb=two words\nc=x=y\n\nmulti<<EOF\nline one\n\nline three\nEOF\nlast=end\n"
        self.assertEqual(hub.parse_command_file(text), {"a": "1", "b": "two words", "c": "x=y", "multi": "line one\n\nline three", "last": "end"})

    def test_line_ends_of_windows_and_an_empty_file(self):
        self.assertEqual(hub.parse_command_file("a=1\r\nb<<X\r\nl1\r\nX\r\n"), {"a": "1", "b": "l1"})
        self.assertEqual(hub.parse_command_file(""), {})

    def test_an_equals_sign_before_the_heredoc_marker_is_a_plain_value(self):
        self.assertEqual(hub.parse_command_file("a=b<<c\n"), {"a": "b<<c"})

    def test_a_line_that_is_not_valid_is_an_error(self):
        for text in ("no separator\n", "=value\n", "name<<\n", "<<EOF\nx\nEOF\n", "a<<EOF\nnever closed\n"):
            with self.subTest(text=text), self.assertRaises(hub.HubLocalError):
                hub.parse_command_file(text)

    def test_the_last_write_of_a_name_wins(self):
        self.assertEqual(hub.parse_command_file("a=1\na=2\n"), {"a": "2"})


class TheConsole(unittest.TestCase):
    def console(self):
        self.out = io.StringIO()
        return hub.Console(self.out)

    def test_workflow_commands_are_translated_and_a_masked_value_never_shows(self):
        console = self.console()
        for line in ("::add-mask::topsecret", "plain line with topsecret inside", "::error::bad thing topsecret", "::warning file=a.sh,line=3::careful", "::notice::fyi", "::debug::hidden",
                     "::group::A group", "inside", "::endgroup::", "::unknown-command::x", "::add-mask::"):
            console.step_line(line)
        self.assertEqual(self.out.getvalue().splitlines(),
                         ["plain line with *** inside", "ERROR: bad thing ***", "WARNING: careful", "NOTE: fyi", "-- A group", "inside", "::unknown-command::x"])
        self.assertEqual((console.errors, console.warnings), (1, 1))

    def test_a_short_value_is_not_masked_and_the_longest_goes_first(self):
        console = self.console()
        console.add_mask("ab")
        console.add_mask("secret")
        console.add_mask("secret-longer")
        console.emit("ab secret-longer secret")
        self.assertEqual(self.out.getvalue().strip(), "ab *** ***")

    def test_a_character_that_the_console_cannot_show_does_not_stop_the_run(self):
        class Narrow(io.StringIO):
            def write(self, text):
                text.encode("ascii")
                return super().write(text)
        console = hub.Console(Narrow())
        console.emit("caf\u00e9 \u2014 done")


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The machine: a fake az session, small workflows, repositories made for the test
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
FAKE_AZ_SCRIPT = '''import os, sys
with open(os.environ["FAKE_AZ_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("FAKE_AZ_EXIT", "0")))
'''


class FakeAz:
    """An az session in memory (the CLI's default subscription and what is asked of it), and a script that stands in for az in the steps of a run."""

    def __init__(self, folder: Path, user_type="user", tenant=TENANT, set_fails=False, show_fails=False, rest=None):
        self.default = PREVIOUS
        self.user_type, self.tenant, self.set_fails, self.show_fails = user_type, tenant, set_fails, show_fails
        self.rest = dict(rest or {})
        self.calls: list = []
        self.shows = 0
        self.drift_after = None
        script = folder / "fake_az.py"
        script.write_text(FAKE_AZ_SCRIPT, encoding="utf-8", newline="\n")
        self.argv = [sys.executable, str(script)]
        self.step_log = folder / "step_az_calls.txt"
        self.step_log.write_text("", encoding="utf-8")

    def environment(self):
        return dict(os.environ, FAKE_AZ_LOG=str(self.step_log))

    def run(self, args, timeout=300):
        self.calls.append(list(args))
        if args[:2] == ["account", "show"]:
            self.shows += 1
            if self.show_fails:
                return 1, "", "ERROR: Please run 'az login' to setup account.\n"
            if self.drift_after is not None and self.shows > self.drift_after:
                self.default = PREVIOUS
            return 0, json.dumps({"id": self.default, "name": "Previous Default" if self.default == PREVIOUS else "Pilot", "tenant": self.tenant, "user": "owner@example.com",
                                  "type": self.user_type}), ""
        if args[:2] == ["account", "set"]:
            if self.set_fails and args[3] == SUBSCRIPTION:
                return 1, "", "ERROR: the subscription could not be set\n"
            self.default = args[3]
            return 0, "", ""
        if args[:1] == ["rest"]:
            joined = " ".join(args)
            for fragment, answer in self.rest.items():
                if fragment in joined:
                    return answer
            return 0, "Enabled\n", ""
        return 0, "", ""

    def set_calls(self):
        return [call[3] for call in self.calls if call[:2] == ["account", "set"]]

    def step_calls(self):
        return [line for line in self.step_log.read_text(encoding="utf-8").splitlines() if line]


MINI_HEAD = """\
name: Mini
on:
  workflow_dispatch:
    inputs:
      action:
        description: "a choice"
        type: choice
        required: true
        default: what-if
        options:
          - what-if
          - plant
          - aigateway
      minutes:
        type: string
        default: "20"
      public_ai_gateway_requested:
        type: boolean
        default: false
      plant_public_ip:
        type: boolean
        default: false
defaults:
  run:
    shell: bash
jobs:
  hub:
    name: Mini (${{ inputs.action }})
    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    timeout-minutes: 150
    env:
      ACTION: ${{ inputs.action }}
      ENV_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      ENV_RESOURCE_GROUP: ${{ vars.ENV_RESOURCE_GROUP }}
      PLANTED_ID: r${{ github.run_number }}
    steps:
"""
PIN = "0" * 40
CHECKOUT = f"""\
      - name: Check out the repository
        uses: actions/checkout@{PIN} # v7
        with:
          persist-credentials: false
"""
LOGIN = f"""\
      - name: Sign in to Azure
        uses: azure/login@{PIN}
        with:
          client-id: ${{{{ secrets.AZURE_CLIENT_ID }}}}
          tenant-id: ${{{{ secrets.AZURE_TENANT_ID }}}}
          subscription-id: ${{{{ secrets.AZURE_SUBSCRIPTION_ID }}}}
"""


def python_step(version=None):
    version = version or f"{sys.version_info[0]}.{sys.version_info[1]}"
    return f"""\
      - name: Set up Python
        uses: actions/setup-python@{PIN}
        with:
          python-version: "{version}"
"""


def block(name, run, id=None, cond=None, env=None, timeout=None):
    out = [f"      - name: {name}"]
    if id:
        out.append(f"        id: {id}")
    if cond:
        out.append(f"        if: {cond}")
    if timeout:
        out.append(f"        timeout-minutes: {timeout}")
    if env:
        out.append("        env:")
        out += [f"          {key}: {value}" for key, value in env.items()]
    out.append("        run: |")
    out += [("          " + line) if line else "" for line in textwrap.dedent(run).strip("\n").split("\n")]
    return "\n".join(out) + "\n"


def mini(*blocks):
    return MINI_HEAD + "".join(blocks)


HELLO = block("Say hello", 'echo "hello from a step"')
ALWAYS = block("Closing", 'echo "closing, the job is $JOB_STATUS"', cond="always()", env={"JOB_STATUS": "${{ job.status }}"})


class RunnerCase(unittest.TestCase):
    """A repository of its own with a local/ folder (git ignores it), a fake az, and a small workflow."""

    def setUp(self):
        if not git_available():
            self.skipTest("no git on this machine")
        self.tmp = scratch()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = copy_repo(self.base / "repo")
        self.local = self.root / "local"
        self.local.mkdir()
        (self.local / hub.CONFIG_NAME).write_text(CONFIG_TEXT, encoding="utf-8")
        (self.local / hub.STATE_NAME).write_text('{"lastRun": 287}', encoding="utf-8")
        self.az = FakeAz(self.base)
        self.workflow_path = self.base / "wf.yml"
        self.write_workflow(mini(CHECKOUT, python_step(), LOGIN, HELLO, ALWAYS))
        self.sleeps: list = []

    def write_workflow(self, text, newline="\n"):
        self.workflow_path.write_text(text, encoding="utf-8", newline=newline)

    def deps(self, **extra):
        values = dict(root=self.root, az=lambda: self.az, bash=lambda: BASH, sleep=self.sleeps.append)
        values.update(extra)
        return hub.Deps(**values)

    def go(self, *argv, deps=None, environ=None):
        env = dict(os.environ, FAKE_AZ_LOG=str(self.az.step_log))
        env.pop(hub.LOCAL_OVERRIDE, None)
        env.update(environ or {})
        out = io.StringIO()
        code = hub.main([*argv, "--workflow", str(self.workflow_path)], environ=env, out=out, deps=deps or self.deps())
        return code, out.getvalue()

    def records(self, suffix=".md"):
        folder = self.local / "records"
        return sorted(folder.glob(f"hub-local-*{suffix}")) if folder.exists() else []

    def state(self):
        return json.loads((self.local / hub.STATE_NAME).read_text(encoding="utf-8"))["lastRun"]


@unittest.skipIf(BASH is None, "no Git bash on this machine")
class TheRuns(RunnerCase):
    def test_small_steps_run_in_gits_bash_and_pass_outputs_environment_and_summary_on(self):
        self.write_workflow(mini(CHECKOUT, python_step(), LOGIN, block("Make", """
            echo "alpha=one" >> "$GITHUB_OUTPUT"
            {
              echo "multi<<EOF"
              echo "line1"
              echo "line2"
              echo "EOF"
            } >> "$GITHUB_OUTPUT"
            echo "FROM_ENV=hello" >> "$GITHUB_ENV"
            echo "### made by the first step" >> "$GITHUB_STEP_SUMMARY"
            """, id="first"), block("Read", """
            echo "got=$GOT from_env=$FROM_ENV id=$PLANTED_ID"
            echo "multi=$MULTI"
            """, env={"GOT": "${{ steps.first.outputs.alpha }}", "MULTI": "${{ steps.first.outputs.multi }}"}), ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        self.assertIn("got=one from_env=hello id=r288", text)
        self.assertIn("multi=line1\nline2", text)
        self.assertIn("closing, the job is success", text)
        self.assertIn("Hub (local) what-if: PASSED in", text.strip().splitlines()[-1])
        self.assertIn("### made by the first step", text)
        self.assertEqual(self.az.default, PREVIOUS, "the CLI's default subscription is put back")
        self.assertEqual(self.az.set_calls(), [SUBSCRIPTION, PREVIOUS])
        self.assertEqual(self.state(), 287, "a read-only action does not use up a run number")

    def test_a_failed_step_stops_the_run_the_steps_that_always_run_still_run_and_the_default_is_put_back(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Fails", 'echo "about to fail"\nexit 3'), block("Later", 'echo "this must not print"'), ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertIn("about to fail", text)
        self.assertIn("exit code 3", text)
        self.assertNotIn("this must not print", text)
        self.assertIn("closing, the job is failure", text)
        self.assertIn("FAILED in", text.strip().splitlines()[-1])
        self.assertEqual(self.az.default, PREVIOUS)
        self.assertEqual(self.az.calls[-1], ["account", "set", "--subscription", PREVIOUS], "the restore is the last thing that is done with az")

    def test_a_failure_of_the_runner_inside_a_step_still_puts_the_default_back(self):
        with mock.patch.object(hub.Hub, "read_files", side_effect=RuntimeError("boom")):
            code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertIn("the runner failed in this step", text)
        self.assertEqual(self.az.default, PREVIOUS)
        self.assertFalse((self.local / hub.LOCK_NAME).exists())

    def test_ctrl_c_in_a_step_ends_it_runs_the_steps_that_always_run_and_puts_the_default_back(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Slow", "# slow-step-marker\nsleep 60"), block("Later", 'echo "this must not print"'), ALWAYS))
        real = hub.run_process

        def interrupted(argv, env, cwd, console, timeout):
            if "slow-step-marker" in Path(argv[-1]).read_text(encoding="utf-8"):
                raise KeyboardInterrupt
            return real(argv, env, cwd, console, timeout)
        with mock.patch.object(hub, "run_process", interrupted):
            code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertIn("interrupted (Ctrl+C)", text)
        self.assertIn("closing, the job is cancelled", text)
        self.assertNotIn("this must not print", text)
        self.assertEqual(self.az.default, PREVIOUS)
        self.assertFalse((self.local / hub.LOCK_NAME).exists())

    def test_a_second_ctrl_c_ends_the_run_at_once_and_the_default_is_still_put_back(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Slow", "# slow-step-marker\nsleep 60"), ALWAYS))
        real = hub.run_process

        def interrupted(argv, env, cwd, console, timeout):
            if "closing" in Path(argv[-1]).read_text(encoding="utf-8") or "slow-step-marker" in Path(argv[-1]).read_text(encoding="utf-8"):
                raise KeyboardInterrupt
            return real(argv, env, cwd, console, timeout)
        with mock.patch.object(hub, "run_process", interrupted):
            code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertEqual(self.az.default, PREVIOUS)
        self.assertFalse((self.local / hub.LOCK_NAME).exists())

    def test_a_step_is_stopped_with_everything_it_started_when_its_timeout_is_over(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Too slow", "sleep 120", timeout="0.05"), ALWAYS))
        began = time.monotonic()
        code, text = self.go("what-if")
        self.assertLess(time.monotonic() - began, 60)
        self.assertEqual(code, 1, text)
        self.assertIn("the step was stopped after 0.05 minutes", text)
        self.assertIn("closing, the job is failure", text)

    def test_the_environment_of_a_step_is_the_one_of_a_run_of_the_hub(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Environment", """
            for name in GITHUB_ACTIONS METERNAUT_HUB_LOCAL GITHUB_ACTOR GITHUB_REF GITHUB_RUN_NUMBER MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL PYTHONUTF8 PYTHONUNBUFFERED ACTION ENV_RESOURCE_GROUP; do
              echo "$name=${!name}"
            done
            echo "sha_set=$([ -n "$GITHUB_SHA" ] && echo yes)"
            oidc_name="ACTIONS_ID_TOKEN_REQUEST_""URL"
            echo "run_id_is_a_number=$([[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]] && echo yes)"
            echo "temp=$RUNNER_TEMP"
            echo "output_file_in_temp=$([[ "$GITHUB_OUTPUT" == "$RUNNER_TEMP"/* ]] && echo yes)"
            echo "gh_token=${GH_TOKEN-unset} github_token=${GITHUB_TOKEN-unset} oidc=${!oidc_name-unset}"
            echo "python3=$(python3 -c 'import sys; print(sys.version_info[0])')"
            echo "converted=$(python3 -c 'import sys; print(sys.argv[1])' /subscriptions/abc/resourceGroups/x)"
            echo "az=$(az account show --query id --output tsv)"
            echo "type_az=$(type -t az)"
            """), ALWAYS))
        code, text = self.go("what-if", environ={"GH_TOKEN": "gh-secret-token", "GITHUB_TOKEN": "gh-secret-token-2", "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/token"})
        self.assertEqual(code, 0, text)
        for expected in ("GITHUB_ACTIONS=true", "METERNAUT_HUB_LOCAL=1", "GITHUB_ACTOR=tinodo", "GITHUB_REF=refs/heads/main", "GITHUB_RUN_NUMBER=288", "MSYS_NO_PATHCONV=1", "MSYS2_ARG_CONV_EXCL=*",
                         "PYTHONUTF8=1", "PYTHONUNBUFFERED=1", "ACTION=what-if", "ENV_RESOURCE_GROUP=rg-of-the-project", "sha_set=yes", "run_id_is_a_number=yes", "output_file_in_temp=yes",
                         "gh_token=unset github_token=unset oidc=unset", f"python3={sys.version_info[0]}", "converted=/subscriptions/abc/resourceGroups/x", "type_az=file"):
            self.assertIn(expected, text)
        self.assertRegex(text, r"temp=[A-Za-z]:/|temp=/", "the temp folder is written with forward slashes")
        self.assertNotIn("\\", re.search(r"temp=(\S+)", text).group(1))
        self.assertIn(self.az.step_calls()[0], "account show --query id --output tsv", "az in a step is the shim, which reached the stand-in for the CLI")

    def test_the_line_ends_of_the_workflow_never_reach_bash(self):
        script = block("Multi line constructs", """
            for word in one two; do
              if [ "$word" = two ]; then
                echo "constructs work: $word"
              fi
            done
            """)
        self.write_workflow(mini(CHECKOUT, LOGIN, script, ALWAYS), newline="\r\n")
        self.assertIn(b"\r\n", self.workflow_path.read_bytes())
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        self.assertIn("constructs work: two", text)

    def test_the_unit_tests_of_the_first_step_are_not_repeated_and_the_commit_is_said(self):
        head = hub.run_git(["rev-parse", "HEAD"], self.root)[1].strip()
        self.write_workflow(mini(CHECKOUT, block("Checks", """
            python3 -m unittest discover -s tools/tests
              python3 -m unittest discover -s src/case-functions/tests
            echo "the other lines run"
            """), LOGIN, ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        self.assertEqual(text.count("the unit tests are not repeated: they were run on this machine"), 1)
        self.assertIn(f"commit {head[:12]}, working tree clean", text)
        self.assertIn("the other lines run", text)
        self.assertNotIn("Ran ", text)
        self.assertIn("the unit tests of the first step are not repeated", self.records()[0].read_text(encoding="utf-8"))

    def test_a_write_action_uses_up_a_run_number_and_names_what_it_plants_with_it(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Plant", 'echo "planting planted-disk-$PLANTED_ID"', cond="inputs.action == 'plant'"), ALWAYS))
        code, text = self.go("plant", "--yes")
        self.assertEqual(code, 0, text)
        self.assertIn("planting planted-disk-r288", text)
        self.assertEqual(self.state(), 288)
        code, text = self.go("plant", "--yes")
        self.assertIn("planting planted-disk-r289", text)
        self.assertEqual(self.state(), 289)
        code, text = self.go("what-if")
        self.assertEqual(self.state(), 289)
        self.assertNotIn("planting", text)

    def test_the_record_and_the_log_are_written_and_the_run_leaves_nothing_behind(self):
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        (record,), (log,) = self.records(), self.records(".log")
        body = record.read_text(encoding="utf-8")
        head = hub.run_git(["rev-parse", "HEAD"], self.root)[1].strip()
        for expected in ("# Hub (local): what-if", "PASSED in", head, "working tree: clean", "restored: the CLI's default subscription was put back", "| 1 | success |", "## Steps",
                         "run number 288 (not used up: a read-only action)"):
            self.assertIn(expected, body)
        self.assertNotIn(SUBSCRIPTION, body + log.read_text(encoding="utf-8"), "the subscription is a secret of the Hub: it is masked in the log and the record")
        self.assertIn("hello from a step", log.read_text(encoding="utf-8"))
        self.assertFalse((self.local / hub.LOCK_NAME).exists())
        self.assertEqual(list((self.local / hub.TEMP_NAME).glob("*")) if (self.local / hub.TEMP_NAME).exists() else [], [], "the run's temp folder is deleted")

    def test_a_dirty_tree_is_run_for_a_read_only_action_and_the_record_says_so(self):
        (self.root / "untracked.txt").write_text("not committed\n", encoding="utf-8")
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        self.assertIn("working tree NOT clean (1 paths", text)
        self.assertIn("NOT clean (1 paths)", self.records()[0].read_text(encoding="utf-8"))
        code, text = self.go("plant", "--yes", "--allow-dirty")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.state(), 288)

    def test_a_python_other_than_the_one_the_step_asks_for_stops_the_run(self):
        self.write_workflow(mini(CHECKOUT, python_step("2.7"), LOGIN, HELLO, ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertIn("asks for Python 2.7", text)
        self.assertNotIn("hello from a step", text)
        self.assertEqual(self.az.default, PREVIOUS)

    def test_the_sign_in_replacement_stops_the_run_when_the_default_subscription_changed_under_it(self):
        self.az.drift_after = 2
        code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertIn("not the pilot's subscription any more", text)
        self.assertNotIn("hello from a step", text)
        self.assertEqual(self.az.default, PREVIOUS)

    def test_a_skipped_step_gives_an_empty_output_and_the_outcome_skipped(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Plant", 'echo "x=planted" >> "$GITHUB_OUTPUT"', id="plant", cond="inputs.action == 'plant'"),
                                 block("Report", 'echo "x=[$X] outcome=$OUTCOME"', env={"X": "${{ steps.plant.outputs.x }}", "OUTCOME": "${{ steps.plant.outcome }}"}), ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        self.assertIn("x=[] outcome=skipped", text)

    def test_a_step_that_writes_a_line_that_is_not_valid_to_its_output_file_fails(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Bad output", 'echo "no separator here" >> "$GITHUB_OUTPUT"'), ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 1, text)
        self.assertIn("is not valid", text)

    def test_what_a_step_prints_in_utf8_reaches_the_log_whole(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, block("Unicode", 'echo "caf\u00e9 \u2014 \u20ac"\npython3 -c "print(\'caf\\u00e9 \\u2014 \\u20ac\')"'), ALWAYS))
        code, text = self.go("what-if")
        self.assertEqual(code, 0, text)
        log = self.records(".log")[0].read_text(encoding="utf-8")
        self.assertEqual(log.count("caf\u00e9 \u2014 \u20ac"), 2, "bash and a native Python both print UTF-8")


class TheGuards(RunnerCase):
    def never_az(self):
        def refuse():
            raise AssertionError("az must not be asked for")
        return self.deps(az=refuse, bash=refuse)

    def test_an_action_that_changes_azure_needs_yes_and_without_it_the_plan_is_printed_and_nothing_runs(self):
        code, text = self.go("plant", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("the action plant changes Azure: it needs --yes", text)
        self.assertIn("The steps:", text)
        self.assertIn("Refused, so this was a dry run", text)
        self.assertEqual(self.state(), 287)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.local / hub.TEMP_NAME).exists())

    def test_a_dry_run_needs_no_az_session_and_changes_nothing(self):
        for action in ("what-if", "plant"):
            code, text = self.go(action, "--dry-run", "--yes", deps=self.never_az())
            self.assertEqual(code, 0, text)
            self.assertIn("dry run, nothing was run", text)
            self.assertIn("The steps:", text)
        self.assertEqual(self.state(), 287)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.local / hub.LOCK_NAME).exists())

    def test_a_dry_run_says_when_a_real_run_would_be_refused(self):
        (self.root / "untracked.txt").write_text("x\n", encoding="utf-8")
        code, text = self.go("plant", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 0, text)
        self.assertIn("a real run would be refused", text)
        self.assertIn("needs --yes", text)
        self.assertIn("working tree is not clean", text)

    def test_a_dirty_tree_refuses_an_action_that_changes_azure_unless_allow_dirty_is_given(self):
        (self.root / "untracked.txt").write_text("x\n", encoding="utf-8")
        code, text = self.go("plant", "--yes", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("the working tree is not clean (1 paths)", text)
        (self.root / "untracked.txt").unlink()
        (self.root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        code, text = self.go("plant", "--yes", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("not clean", text)

    def test_the_ai_gateway_needs_the_owners_written_request_as_in_the_workflow(self):
        code, text = self.go("aigateway", "--yes", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("the action aigateway needs --public-ai-gateway-requested", text)
        code, text = self.go("aigateway", "--yes", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 0, text)
        self.assertIn("a real run would be refused", text)
        code, text = self.go("aigateway", "--yes", "--public-ai-gateway-requested", "--dry-run", deps=self.never_az())
        self.assertNotIn("a real run would be refused", text)

    def test_an_action_that_the_workflow_does_not_have_is_refused(self):
        code, text = self.go("destroy-everything", "--yes", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("is not an action of the workflow. It has: what-if, plant, aigateway", text)

    def test_a_configuration_file_that_git_tracks_is_refused(self):
        git("add", "-f", "local/hub-local.env", cwd=self.root)
        git("commit", "-q", "-m", "tracked by mistake", cwd=self.root)
        code, text = self.go("what-if", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("is tracked by git", text)

    def test_a_configuration_file_that_git_does_not_ignore_is_refused(self):
        (self.root / ".gitignore").write_text("# nothing\n", encoding="utf-8")
        code, text = self.go("what-if", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("is not ignored by git", text)

    def test_a_missing_configuration_or_run_counter_is_refused_with_the_way_out(self):
        (self.local / hub.STATE_NAME).unlink()
        code, text = self.go("what-if", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("--init", text)
        (self.local / hub.CONFIG_NAME).unlink()
        code, text = self.go("what-if", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("does not exist", text)

    def test_a_broken_run_counter_is_refused(self):
        for content in ("not json", "[]", '{"lastRun": "x"}', '{"lastRun": -1}', '{"lastRun": true}', "{}"):
            (self.local / hub.STATE_NAME).write_text(content, encoding="utf-8")
            code, text = self.go("what-if", "--dry-run", deps=self.never_az())
            self.assertEqual(code, 2, content)
            self.assertIn("not a valid state file", text)

    def test_a_configuration_that_misses_a_value_or_names_two_subscriptions_is_refused(self):
        (self.local / hub.CONFIG_NAME).write_text(CONFIG_TEXT.replace("ENV_LOCATION=examplelocation", "ENV_LOCATION="), encoding="utf-8")
        code, text = self.go("what-if", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("ENV_LOCATION has no value", text)
        (self.local / hub.CONFIG_NAME).write_text(CONFIG_TEXT.replace(f"AZURE_SUBSCRIPTION_ID={SUBSCRIPTION}", f"AZURE_SUBSCRIPTION_ID={PREVIOUS}"), encoding="utf-8")
        code, text = self.go("what-if", "--dry-run", deps=self.never_az())
        self.assertEqual(code, 2, text)
        self.assertIn("are not the same subscription", text)

    def test_one_run_at_a_time(self):
        lock = self.local / hub.LOCK_NAME
        lock.write_text(json.dumps({"pid": os.getpid(), "action": "base", "started": "2026-11-08T10:00:00Z"}), encoding="utf-8")
        code, text = self.go("what-if")
        self.assertEqual(code, 2, text)
        self.assertIn("another run holds the lock", text)
        self.assertIn("action base", text)
        self.assertEqual(self.az.calls, [])
        self.assertTrue(lock.exists(), "the lock of the other run is not touched")

    @unittest.skipIf(BASH is None, "no Git bash on this machine")
    def test_the_lock_of_a_run_that_is_gone_is_taken_over_and_the_default_it_had_changed_is_put_back_first(self):
        lock = self.local / hub.LOCK_NAME
        lock.write_text(json.dumps({"pid": 4000001, "action": "base", "started": "2026-11-08T10:00:00Z", "previousDefault": "12121212-1212-1212-1212-121212121212"}), encoding="utf-8")
        code, text = self.go("what-if", deps=self.deps(pid_alive=lambda pid: False))
        self.assertEqual(code, 0, text)
        self.assertIn("an earlier run (process 4000001, action base", text)
        self.assertEqual(self.az.set_calls()[0], "12121212-1212-1212-1212-121212121212", "put back before this run reads the default that it has to restore")
        self.assertEqual(self.az.calls[1][:2], ["account", "show"])
        self.assertFalse(lock.exists())
        lock.write_text("garbage", encoding="utf-8")
        code, text = self.go("what-if", deps=self.deps(pid_alive=lambda pid: False))
        self.assertEqual(code, 0, text)
        self.assertFalse(lock.exists())

    def test_a_session_that_is_not_a_persons_is_refused_and_nothing_is_set(self):
        self.az.user_type = "servicePrincipal"
        code, text = self.go("what-if")
        self.assertEqual(code, 2, text)
        self.assertIn("not a person", text)
        self.assertEqual(self.az.set_calls(), [])
        self.assertFalse((self.local / hub.LOCK_NAME).exists())

    def test_no_az_session_is_refused_and_the_tool_never_signs_in(self):
        self.az.show_fails = True
        code, text = self.go("what-if")
        self.assertEqual(code, 2, text)
        self.assertIn("there is no az session on this machine", text)
        self.assertIn("this tool never signs in", text)
        self.assertEqual([call[0] for call in self.az.calls], ["account"])
        self.assertEqual(self.az.set_calls(), [])

    def test_a_tenant_that_is_not_the_configured_one_is_refused_and_the_default_is_put_back(self):
        self.az.tenant = "00000000-0000-0000-0000-00000000dead"
        code, text = self.go("what-if")
        self.assertEqual(code, 2, text)
        self.assertIn("another tenant than AZURE_TENANT_ID", text)
        self.assertEqual(self.az.default, PREVIOUS)

    def test_a_subscription_that_cannot_be_set_is_refused_and_the_default_is_still_put_back(self):
        self.az.set_fails = True
        code, text = self.go("what-if")
        self.assertEqual(code, 2, text)
        self.assertIn("az account set --subscription failed", text)
        self.assertEqual(self.az.default, PREVIOUS)

    def test_a_machine_without_gits_bash_is_refused(self):
        def missing():
            raise hub.HubLocalError("Git's bash was not found (looked for x)")
        code, text = self.go("what-if", deps=self.deps(bash=missing))
        self.assertEqual(code, 2, text)
        self.assertIn("Git's bash was not found", text)
        self.assertEqual(self.az.calls, [])

    def test_the_command_line_is_checked(self):
        for argv in (["--from-github"], ["what-if", "--from-github"], ["--init", "what-if"], []):
            with self.subTest(argv=argv), mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as caught:
                hub.main(argv, environ={}, out=io.StringIO(), deps=self.deps())
            self.assertEqual(caught.exception.code, 2)


class TheCasesPublish(RunnerCase):
    """The action cases publishes the app from this machine: the package is built by the repository's script and published with az, through the app's public deployment site."""

    PUBLISH = block("Publish the cases to the function app from inside the network, in the Operator", '# --script operator/publish.sh\necho "never run"', id="publish_cases",
                    env={"FUNCTION_APP": "func-cases-test", "CASES_APP_PLAN": "Flex"})
    PACK = block("Pack the cases app's sources for the Operator", 'FUNCTION_APP_SOURCES_ONLY=1 bash tools/build-function-app.sh case-functions cases x y\necho "never run"')
    CLEANUP = block("Delete any container group of the publish that is left", 'python3 tools/operator-run.py cleanup --prefix op-publish-\necho "never run"',
                    cond="always() && steps.publish_cases.outcome != 'skipped'")

    def setUp(self):
        super().setUp()
        self.write_workflow(mini(CHECKOUT, LOGIN, self.PACK, self.PUBLISH, self.CLEANUP, ALWAYS))
        self.processes: list = []

    def fake_process(self, build_ok=True, publish_codes=(0,)):
        codes = list(publish_codes)

        def fake(argv, env, cwd, console, timeout):
            if str(argv[-1]).endswith("cases-build.sh"):
                entry = {"argv": list(argv), "env": dict(env), "timeout": timeout, "script": Path(argv[-1]).read_text(encoding="utf-8")}
                self.processes.append(entry)
                if build_ok:
                    (Path(argv[-1]).parent.parent / "cases.zip").write_bytes(b"PK")
                return (0 if build_ok else 1), False
            if "config-zip" in argv:
                self.processes.append({"argv": list(argv), "env": dict(env), "timeout": timeout})
                console.step_line("publishing to the deployment site")
                return (codes.pop(0) if codes else 0), False
            return 0, False
        return fake

    def run_cases(self, **kwargs):
        with mock.patch.object(hub, "run_process", self.fake_process(**kwargs)):
            return self.go("what-if")

    def test_the_package_is_built_by_the_repositorys_script_and_published_with_the_owners_session(self):
        code, text = self.run_cases()
        self.assertEqual(code, 0, text)
        site = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-of-the-project/providers/Microsoft.Web/sites/func-cases-test?api-version=2024-04-01"
        self.assertIn(["rest", "--method", "get", "--url", site, "--query", "properties.publicNetworkAccess", "--output", "tsv"], self.az.calls)
        build, publish = self.processes
        self.assertEqual(build["argv"][1:4], ["--noprofile", "--norc", "-eo"])
        self.assertNotIn("MSYS_NO_PATHCONV", build["env"], "the build script of the function app tests for a leading slash and hands paths to a native Python: Git's path conversion stays on for it")
        self.assertNotIn("MSYS2_ARG_CONV_EXCL", build["env"])
        self.assertIn("bash tools/build-function-app.sh case-functions cases ", build["script"])
        for path in re.findall(r"cases ('?/\S+'?) ('?/\S+'?)\n", build["script"])[0]:
            self.assertTrue(path.strip("'").startswith("/"), "absolute paths in the form of Git's bash: the script treats anything else as relative")
        self.assertEqual(publish["argv"][:len(self.az.argv)], self.az.argv)
        arguments = publish["argv"][len(self.az.argv):]
        self.assertEqual(arguments[:8], ["functionapp", "deployment", "source", "config-zip", "--subscription", SUBSCRIPTION, "--resource-group", "rg-of-the-project"])
        self.assertEqual(arguments[8:10], ["--name", "func-cases-test"])
        self.assertEqual(arguments[arguments.index("--build-remote"):arguments.index("--build-remote") + 2], ["--build-remote", "false"])
        self.assertIn("the package is published to func-cases-test (attempt 1 of 3), from this machine, through the app's public deployment site", text)
        self.assertIn("replaced: not needed: the publish step that follows builds the package", text)
        self.assertIn("replaced: not needed: the publish made no container group", text)
        self.assertNotIn("never run", text)
        record = self.records()[0].read_text(encoding="utf-8")
        self.assertIn("published from this machine through the app's public deployment site", record)
        self.assertEqual(self.az.default, PREVIOUS)

    def test_the_publish_is_tried_three_times_a_minute_apart(self):
        code, text = self.run_cases(publish_codes=(1, 1, 0))
        self.assertEqual(code, 0, text)
        self.assertEqual(self.sleeps, [60, 60])
        self.assertIn("attempt 3 of 3", text)
        code, text = self.run_cases(publish_codes=(1, 1, 1))
        self.assertEqual(code, 1, text)
        self.assertIn("the code could not be published to func-cases-test", text)
        self.assertEqual(self.sleeps, [60, 60, 60, 60])

    def test_an_app_that_takes_no_public_traffic_cannot_be_published_to_from_here_and_nothing_is_built(self):
        self.az.rest = {"properties.publicNetworkAccess": (0, "Disabled\n", "")}
        code, text = self.run_cases()
        self.assertEqual(code, 1, text)
        self.assertIn("takes no public traffic", text)
        self.assertIn("needs a GitHub OpenID Connect token", text)
        self.assertEqual(self.processes, [])

    def test_a_public_access_that_is_not_set_counts_as_enabled(self):
        for answer in ("None\n", "\n", "Enabled\n", "enabled\n"):
            self.az.rest = {"properties.publicNetworkAccess": (0, answer, "")}
            self.processes.clear()
            code, text = self.run_cases()
            self.assertEqual(code, 0, answer + text)

    def test_an_app_that_cannot_be_read_stops_before_anything_is_built(self):
        self.az.rest = {"publicNetworkAccess": (1, "", "ERROR: (AuthorizationFailed) no right")}
        code, text = self.run_cases()
        self.assertEqual(code, 1, text)
        self.assertIn("the cases app could not be read", text)
        self.assertEqual(self.processes, [])

    def test_a_package_that_cannot_be_built_is_never_published(self):
        code, text = self.run_cases(build_ok=False)
        self.assertEqual(code, 1, text)
        self.assertIn("the package could not be built", text)
        self.assertIn("Nothing was published", text)
        self.assertEqual(len(self.processes), 1)

    def test_a_name_that_is_not_a_name_is_refused(self):
        self.write_workflow(mini(CHECKOUT, LOGIN, self.PUBLISH.replace("func-cases-test", "bad name; rm -rf"), ALWAYS))
        code, text = self.run_cases()
        self.assertEqual(code, 1, text)
        self.assertIn("is not a name", text)
        self.assertEqual(self.processes, [])


class TheLocalFolder(unittest.TestCase):
    def setUp(self):
        if not git_available():
            self.skipTest("no git on this machine")
        self.tmp = scratch()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_a_worktree_finds_the_local_folder_of_the_main_working_tree(self):
        main = copy_repo(self.base / "main")
        worktree = self.base / "wt"
        git("worktree", "add", "-q", str(worktree), "-b", "feature", cwd=main)
        (worktree / "sub").mkdir()
        for cwd in (main, worktree, worktree / "sub"):
            found = hub.resolve_local_dir({}, cwd)
            self.assertEqual(found.name, "local")
            self.assertTrue(found.parent.samefile(main), f"{found} from {cwd}")

    def test_the_environment_variable_names_another_folder_and_a_blank_one_is_ignored(self):
        main = copy_repo(self.base / "main")
        elsewhere = self.base / "elsewhere"
        self.assertEqual(hub.resolve_local_dir({hub.LOCAL_OVERRIDE: str(elsewhere)}, main), elsewhere.resolve())
        self.assertTrue(hub.resolve_local_dir({hub.LOCAL_OVERRIDE: "   "}, main).parent.samefile(main))
        self.assertTrue(hub.resolve_local_dir({hub.LOCAL_OVERRIDE: ""}, main).parent.samefile(main))

    def test_an_old_git_that_does_not_know_the_absolute_option_is_asked_again_and_a_relative_answer_is_made_absolute(self):
        calls = []

        def old_git(args, cwd):
            calls.append(list(args))
            return (129, "", "unknown option") if "--path-format=absolute" in args else (0, ".git\n", "")
        found = hub.resolve_local_dir({}, self.base, old_git)
        self.assertEqual(found, self.base.resolve() / "local")
        self.assertEqual(len(calls), 2)

    def test_git_that_cannot_say_is_a_refusal_that_names_the_way_out(self):
        for answer in ((128, "", "fatal: not a git repository"), (0, "", "")):
            with self.assertRaises(hub.HubLocalError) as caught:
                hub.resolve_local_dir({}, self.base, lambda args, cwd, answer=answer: answer)
            self.assertIn(hub.LOCAL_OVERRIDE, str(caught.exception))

    def test_a_git_directory_that_is_not_a_dot_git_folder_is_refused(self):
        with self.assertRaises(hub.HubLocalError) as caught:
            hub.resolve_local_dir({}, self.base, lambda args, cwd: (0, str(self.base / "repo.git") + "\n", ""))
        self.assertIn(hub.LOCAL_OVERRIDE, str(caught.exception))

    def test_a_run_from_a_worktree_uses_the_configuration_of_the_main_tree_and_not_a_local_folder_of_its_own(self):
        main = copy_repo(self.base / "main")
        (main / "local").mkdir()
        (main / "local" / hub.CONFIG_NAME).write_text(CONFIG_TEXT, encoding="utf-8")
        (main / "local" / hub.STATE_NAME).write_text('{"lastRun": 287}', encoding="utf-8")
        worktree = self.base / "wt"
        git("worktree", "add", "-q", str(worktree), "-b", "feature", cwd=main)
        (worktree / "local").mkdir()
        (worktree / "local" / hub.CONFIG_NAME).write_text("ONLY_THIS=1\n", encoding="utf-8")
        (worktree / "local" / hub.STATE_NAME).write_text('{"lastRun": 5}', encoding="utf-8")
        workflow = self.base / "wf.yml"
        workflow.write_text(mini(CHECKOUT, HELLO), encoding="utf-8", newline="\n")

        def refuse():
            raise AssertionError("a dry run needs no az session")
        out = io.StringIO()
        code = hub.main(["what-if", "--dry-run", "--workflow", str(workflow)], environ={}, out=out, deps=hub.Deps(root=worktree, az=refuse, bash=refuse))
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn(f"{len(FAKE_VALUES)} names", out.getvalue())
        self.assertIn("run number     288", out.getvalue())
        shown = re.search(r"local folder   (.+)", out.getvalue()).group(1).strip()
        self.assertTrue(Path(shown).samefile(main / "local"), shown)

    def test_the_lock_and_the_records_live_next_to_the_configuration_of_the_main_tree(self):
        if BASH is None:
            self.skipTest("no Git bash on this machine")
        main = copy_repo(self.base / "main")
        (main / "local").mkdir()
        (main / "local" / hub.CONFIG_NAME).write_text(CONFIG_TEXT, encoding="utf-8")
        (main / "local" / hub.STATE_NAME).write_text('{"lastRun": 287}', encoding="utf-8")
        worktree = self.base / "wt"
        git("worktree", "add", "-q", str(worktree), "-b", "feature", cwd=main)
        workflow = self.base / "wf.yml"
        workflow.write_text(mini(CHECKOUT, LOGIN, HELLO), encoding="utf-8", newline="\n")
        az = FakeAz(self.base)
        out = io.StringIO()
        code = hub.main(["what-if", "--workflow", str(workflow)], environ=dict(os.environ, FAKE_AZ_LOG=str(az.step_log)), out=out,
                        deps=hub.Deps(root=worktree, az=lambda: az, bash=lambda: BASH, sleep=lambda seconds: None))
        self.assertEqual(code, 0, out.getvalue())
        self.assertTrue(list((main / "local" / "records").glob("hub-local-what-if-*.md")))
        self.assertFalse((worktree / "local" / "records").exists(), "nothing is written to the worktree's own local/ folder")
        self.assertFalse((main / "local" / hub.LOCK_NAME).exists())


class TheInit(unittest.TestCase):
    class FakeGh:
        def __init__(self, variables=None, runs=None, code=0):
            self.variables, self.runs, self.code, self.calls = variables if variables is not None else [], runs if runs is not None else [], code, []

        def __call__(self, args, cwd):
            self.calls.append(list(args))
            if self.code:
                return self.code, "", "gh: not logged in"
            return 0, json.dumps(self.variables if args[:2] == ["variable", "list"] else self.runs), ""

    def setUp(self):
        if not git_available():
            self.skipTest("no git on this machine")
        self.tmp = scratch()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "local-folder"

    def init(self, *argv, gh=None, environ=None):
        out = io.StringIO()
        code = hub.main(["--init", *argv], environ=environ if environ is not None else {hub.LOCAL_OVERRIDE: str(self.folder)}, out=out, deps=hub.Deps(root=ROOT, gh=gh or self.FakeGh()))
        return code, out.getvalue()

    def test_the_template_holds_the_names_with_empty_values_and_the_counter_starts_above_what_the_hub_reached(self):
        gh = self.FakeGh()
        code, text = self.init(gh=gh)
        self.assertEqual(code, 0, text)
        self.assertEqual(gh.calls, [], "GitHub is read only when the owner passes --from-github")
        lines = [line for line in (self.folder / hub.CONFIG_NAME).read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
        self.assertEqual([line.split("=")[0] for line in lines], list(hub.TEMPLATE_NAMES))
        self.assertTrue(all(line.endswith("=") for line in lines), "no value is written without --from-github")
        self.assertEqual(json.loads((self.folder / hub.STATE_NAME).read_text(encoding="utf-8")), {"lastRun": hub.FIRST_RUN_NUMBER - 1})
        self.assertGreaterEqual(hub.FIRST_RUN_NUMBER, 1000)

    def test_what_exists_is_kept_and_never_overwritten(self):
        self.init()
        (self.folder / hub.CONFIG_NAME).write_text("MINE=1\n", encoding="utf-8")
        (self.folder / hub.STATE_NAME).write_text('{"lastRun": 287}', encoding="utf-8")
        code, text = self.init()
        self.assertEqual(code, 0, text)
        self.assertIn("kept:", text)
        self.assertEqual((self.folder / hub.CONFIG_NAME).read_text(encoding="utf-8"), "MINE=1\n")
        self.assertEqual((self.folder / hub.STATE_NAME).read_text(encoding="utf-8"), '{"lastRun": 287}')

    def test_from_github_reads_the_variables_and_the_newest_run_once_and_never_the_secrets(self):
        gh = self.FakeGh(variables=[{"name": "ENV_LOCATION", "value": "somewhere"}, {"name": "ENV_OWNER", "value": "me@example.com"}, {"name": "SOME_OTHER", "value": "ignored"}],
                         runs=[{"number": 301}])
        code, text = self.init("--from-github", gh=gh)
        self.assertEqual(code, 0, text)
        self.assertEqual(gh.calls, [["variable", "list", "--json", "name,value"], ["run", "list", "--workflow", "deploy-hub.yml", "--limit", "1", "--json", "number"]])
        values = hub.parse_env_file((self.folder / hub.CONFIG_NAME).read_text(encoding="utf-8"))
        self.assertEqual(values["ENV_LOCATION"], "somewhere")
        self.assertEqual(values["ENV_OWNER"], "me@example.com")
        self.assertNotIn("SOME_OTHER", values)
        for secret in hub.SECRET_NAMES:
            self.assertEqual(values[secret], "", "GitHub never shows a secret: it is filled in by hand")
        self.assertIn("fill in:", text)
        self.assertIn("AZURE_TENANT_ID", text.split("fill in:")[1])
        self.assertNotIn("somewhere", text, "values are never printed")

    def test_a_newest_run_below_the_start_is_the_number_that_github_reached(self):
        self.init("--from-github", gh=self.FakeGh(runs=[{"number": 301}]))
        self.assertEqual(json.loads((self.folder / hub.STATE_NAME).read_text(encoding="utf-8")), {"lastRun": 301}, "the counter is seeded from GitHub: the next run is 302")

    def test_a_newest_run_above_the_start_wins(self):
        self.init("--from-github", gh=self.FakeGh(runs=[{"number": 4000}]))
        self.assertEqual(json.loads((self.folder / hub.STATE_NAME).read_text(encoding="utf-8")), {"lastRun": 4000})

    def test_a_workflow_that_has_no_run_yet_keeps_the_start(self):
        self.init("--from-github", gh=self.FakeGh(runs=[]))
        self.assertEqual(json.loads((self.folder / hub.STATE_NAME).read_text(encoding="utf-8")), {"lastRun": hub.FIRST_RUN_NUMBER - 1})

    def test_from_github_when_both_files_exist_asks_github_nothing(self):
        self.init()
        gh = self.FakeGh(variables=[{"name": "ENV_LOCATION", "value": "x"}], runs=[{"number": 5000}])
        code, text = self.init("--from-github", gh=gh)
        self.assertEqual(code, 0, text)
        self.assertEqual(gh.calls, [])

    def test_a_failing_gh_is_a_refusal_and_nothing_is_made(self):
        code, text = self.init("--from-github", gh=self.FakeGh(code=1))
        self.assertEqual(code, 2, text)
        self.assertIn("gh variable list failed", text)
        self.assertFalse((self.folder / hub.CONFIG_NAME).exists())
        self.assertFalse((self.folder / hub.STATE_NAME).exists())

    def test_a_folder_that_git_does_not_ignore_gets_no_file(self):
        repo = make_repo(Path(self.tmp.name) / "repo", ignore_local=False)
        code, text = self.init(environ={hub.LOCAL_OVERRIDE: str(repo / "local")})
        self.assertEqual(code, 2, text)
        self.assertIn("is not ignored by git", text)
        self.assertFalse((repo / "local" / hub.CONFIG_NAME).exists())


class TheShims(unittest.TestCase):
    def setUp(self):
        self.tmp = scratch()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.az = FakeAz(self.base)

    def bash(self, script, shim_names=("az", "python3")):
        shim = self.base / "shim"
        shim.mkdir(exist_ok=True)
        texts = {"az": hub.az_shim(self.az.argv), "python3": hub.python_shim(sys.executable)}
        for name in shim_names:
            (shim / name).write_text(texts[name], encoding="utf-8", newline="\n")
        (self.base / "t.sh").write_text(script, encoding="utf-8", newline="\n")
        env = dict(os.environ, PATH=shim.as_posix() + os.pathsep + os.environ["PATH"], FAKE_AZ_LOG=str(self.az.step_log), MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
        return subprocess.run([BASH, "--noprofile", "--norc", "-eo", "pipefail", (self.base / "t.sh").as_posix()], capture_output=True, text=True, env=env, encoding="utf-8")

    @unittest.skipIf(BASH is None, "no Git bash on this machine")
    def test_the_az_shim_reaches_the_cli_with_every_argument_whole_and_refuses_what_changes_the_session(self):
        done = self.bash('az rest --url "https://x/y?a=1&b=2" --query \'{a: name, b: "x&y", c: `||`}\'\naz account set --subscription x || echo "set refused: $?"\n'
                         'az login || echo "login refused: $?"\naz account show --query id\n')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.az.step_calls(), ['rest --url https://x/y?a=1&b=2 --query {a: name, b: "x&y", c: `||`}', "account show --query id"])
        self.assertIn("set refused: 97", done.stdout)
        self.assertIn("login refused: 97", done.stdout)
        self.assertIn("az account set is not run by a step of the Hub", done.stderr)

    @unittest.skipIf(BASH is None, "no Git bash on this machine")
    def test_python3_is_the_python_that_runs_the_tool_and_not_the_alias_of_the_store(self):
        done = self.bash('python3 -c "import sys; print(sys.version_info[0], sys.executable)"')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.split()[0], str(sys.version_info[0]))
        self.assertEqual(os.path.normcase(done.stdout.split(" ", 1)[1].strip()), os.path.normcase(sys.executable))

    def test_the_hook_makes_az_in_a_subprocess_the_clis_own_python_and_refuses_what_changes_the_session(self):
        hook = self.base / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(hub.sitecustomize_text(), encoding="utf-8", newline="\n")
        code = textwrap.dedent("""
            import subprocess
            r = subprocess.run(["az", "rest", "--url", "https://x/y?a=1&b=2", "--query", '{b: "x&y"}'], capture_output=True, text=True)
            print("rc", r.returncode)
            for command in (["az", "login"], ["az.cmd", "account", "set", "--subscription", "x"], ["az", "config", "set", "a=b"], ["az", "logout"]):
                r = subprocess.run(command, capture_output=True, text=True)
                print(command[1], r.returncode, r.stderr.strip())
            """)
        env = dict(os.environ, PYTHONPATH=str(hook), HUB_LOCAL_AZ=json.dumps(self.az.argv), FAKE_AZ_LOG=str(self.az.step_log))
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], "rc 0")
        for line, command in zip(lines[1:5], ("login", "account", "config", "logout")):
            self.assertTrue(line.startswith(f"{command} 97 ERROR: az "), line)
        self.assertEqual(self.az.step_calls(), ['rest --url https://x/y?a=1&b=2 --query {b: "x&y"}'], "only the allowed call reached the stand-in for the CLI")

    def test_without_the_variable_the_hook_changes_nothing(self):
        hook = self.base / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(hub.sitecustomize_text(), encoding="utf-8", newline="\n")
        env = {key: value for key, value in os.environ.items() if key != "HUB_LOCAL_AZ"}
        env["PYTHONPATH"] = str(hook)
        done = subprocess.run([sys.executable, "-c", "import subprocess; print(subprocess.Popen.__init__.__module__)"], capture_output=True, text=True, env=env)
        self.assertEqual(done.stdout.strip(), "subprocess")

    def test_the_session_commands_that_are_refused_are_the_ones_that_change_the_owners_session(self):
        for words in (["login"], ["logout"], ["account", "set", "--subscription", "x"], ["account", "clear"], ["configure"], ["config", "set", "a=b"], ["config", "unset", "a"]):
            self.assertIsNotNone(hub.refused_session_command(words), words)
        for words in (["account", "show"], ["account", "list"], ["rest", "--method", "get"], ["config", "get"], ["bicep", "build"], ["login-extra"], ["deployment", "group", "what-if"]):
            self.assertIsNone(hub.refused_session_command(words), words)

    @unittest.skipUnless(os.name == "nt", "the form of Git's bash for a Windows path")
    def test_a_windows_path_is_given_in_the_form_that_gits_bash_uses(self):
        self.assertEqual(hub.posix_absolute(Path("C:/Users/someone/repo/local/rt/1/cases.zip")), "/c/Users/someone/repo/local/rt/1/cases.zip")
        self.assertEqual(hub.posix(Path("C:\\Users\\someone\\x")), "C:/Users/someone/x")

    @unittest.skipIf(BASH is None, "no Git bash on this machine")
    def test_the_bash_that_is_found_is_the_one_of_git_and_not_the_launcher_of_wsl(self):
        self.assertTrue(hub.is_git_bash(BASH))
        self.assertFalse(hub.is_git_bash(sys.executable), "a program that is not bash is not accepted")

    @unittest.skipUnless(os.name == "nt" and Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe").exists(), "the Windows install of the Azure CLI")
    def test_the_azure_cli_is_found_as_its_own_python_and_not_as_az_cmd(self):
        argv = hub.AzCli.find().argv
        self.assertTrue(argv[0].lower().endswith("python.exe"))
        self.assertEqual(argv[1:], ["-IBm", "azure.cli"])


class TheSmallParts(unittest.TestCase):
    def setUp(self):
        self.tmp = scratch()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_the_configuration_file_format(self):
        text = "# comment\n\nA=1\n  B = two words  \nC=\"quoted\"\nD='single'\nE=[{\"k\": \"v\"}]\nF=a=b\nG=\"half\nH=\"x\" and \"y\"\r\n"
        self.assertEqual(hub.parse_env_file(text), {"A": "1", "B": "two words", "C": "quoted", "D": "single", "E": '[{"k": "v"}]', "F": "a=b", "G": '"half', "H": '"x" and "y"'})
        for bad, fragment in (("A=1\nA=2\n", "twice"), ("no equals\n", "NAME=VALUE"), ("1A=x\n", "NAME=VALUE"), ("=x\n", "NAME=VALUE")):
            with self.subTest(bad=bad), self.assertRaises(hub.HubLocalError) as caught:
                hub.parse_env_file(bad)
            self.assertIn(fragment, str(caught.exception))

    def test_the_two_names_of_the_subscription_are_one_value(self):
        values, notes, problems = hub.reconcile_config({**FAKE_VALUES, "AZURE_SUBSCRIPTION_ID": ""})
        self.assertEqual((values["AZURE_SUBSCRIPTION_ID"], problems), (SUBSCRIPTION, []))
        self.assertTrue(notes)
        values, notes, problems = hub.reconcile_config({**FAKE_VALUES, "ENV_SUBSCRIPTION_ID": ""})
        self.assertEqual((values["ENV_SUBSCRIPTION_ID"], problems), (SUBSCRIPTION, []))
        _, _, problems = hub.reconcile_config({**FAKE_VALUES, "AZURE_SUBSCRIPTION_ID": PREVIOUS})
        self.assertTrue(any("not the same subscription" in problem for problem in problems))
        _, _, problems = hub.reconcile_config({**FAKE_VALUES, "AZURE_TENANT_ID": "not an id", "ENV_RESOURCE_GROUP": ""})
        self.assertTrue(any("AZURE_TENANT_ID is not an id" in problem for problem in problems))
        self.assertTrue(any("ENV_RESOURCE_GROUP has no value" in problem for problem in problems))

    def test_the_run_counter_is_saved_whole(self):
        hub.save_state(self.base, {"lastRun": 41})
        self.assertEqual(hub.load_state(self.base), {"lastRun": 41})
        self.assertFalse(list(self.base.glob("*.new")))

    def test_the_lock_is_taken_once_and_given_back(self):
        path = self.base / hub.LOCK_NAME
        first, second = hub.Lock(path, {"pid": os.getpid()}), hub.Lock(path, {"pid": os.getpid()})
        self.assertIsNone(first.acquire())
        with self.assertRaises(hub.HubLocalError):
            second.acquire()
        first.update(previousDefault="x")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["previousDefault"], "x")
        first.release()
        self.assertFalse(path.exists())
        first.release()
        self.assertIsNone(second.acquire())
        second.release()

    def test_a_process_that_is_gone_is_not_alive_and_this_one_is(self):
        self.assertTrue(hub.process_alive(os.getpid()))
        for pid in (0, -1, None, "12", 4000001):
            self.assertFalse(hub.process_alive(pid), pid)
        done = subprocess.Popen([sys.executable, "-c", "pass"])
        done.wait()
        self.assertFalse(hub.process_alive(done.pid))

    def test_a_folder_with_a_read_only_file_is_deleted(self):
        folder = self.base / "tree"
        (folder / "sub").mkdir(parents=True)
        target = folder / "sub" / "readonly.txt"
        target.write_text("x", encoding="utf-8")
        os.chmod(target, 0o444)
        self.assertTrue(hub.remove_tree(folder))
        self.assertFalse(folder.exists())


@unittest.skipIf(BASH is None, "no Git bash on this machine")
class TheProcessRunner(unittest.TestCase):
    """run_process: live output, a timeout that ends everything, a silent command that is said to be running, and Ctrl+C with time to clean up."""

    def setUp(self):
        self.tmp = scratch()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.out = io.StringIO()
        self.console = hub.Console(self.out)

    def run_script(self, text, timeout=60, console=None):
        script = self.base / "s.sh"
        script.write_text(text, encoding="utf-8", newline="\n")
        return hub.run_process([BASH, "--noprofile", "--norc", "-eo", "pipefail", script.as_posix()], dict(os.environ), self.base, console or self.console, timeout)

    def test_the_output_is_streamed_and_the_exit_code_is_given(self):
        code, timed_out = self.run_script('echo "one"\necho "two" >&2\nexit 7\n')
        self.assertEqual((code, timed_out), (7, False))
        self.assertEqual(sorted(self.out.getvalue().split()), ["one", "two"])

    def test_what_a_command_leaves_running_when_it_ends_is_ended_with_it(self):
        marker = self.base / "late.txt"
        code, timed_out = self.run_script(f'( sleep 4; echo late > "{marker.as_posix()}" ) &\necho started\n')
        self.assertEqual((code, timed_out), (0, False))
        time.sleep(6)
        self.assertFalse(marker.exists(), "the background process of the step was ended with the step")

    def test_a_command_that_is_silent_for_a_while_is_said_to_be_still_running(self):
        with mock.patch.object(hub, "HEARTBEAT_SECONDS", 1):
            code, _ = self.run_script("sleep 4\necho done\n")
        self.assertEqual(code, 0)
        self.assertIn("... still running after", self.out.getvalue())
        self.assertIn("done", self.out.getvalue())

    def test_ctrl_c_gives_the_command_time_to_clean_up_and_then_ends_it(self):
        class Interrupting(hub.Console):
            """Stands in for a Ctrl+C that arrives in the main thread, on the second look of the wait loop at the console."""
            looks = 0

            @property
            def last_output(self):
                Interrupting.looks += 1
                if Interrupting.looks == 6:
                    raise KeyboardInterrupt
                return time.monotonic()

            @last_output.setter
            def last_output(self, value):
                pass
        out = io.StringIO()
        console = Interrupting(out)
        with mock.patch.object(hub, "INTERRUPT_GRACE_SECONDS", 30), self.assertRaises(KeyboardInterrupt):
            self.run_script('echo working\nsleep 3\necho "cleaned up after the interrupt"\n', console=console)
        self.assertIn("cleaned up after the interrupt", out.getvalue(), "the command ran on to its own end: a tool that deletes what it made has its time")

    def test_ctrl_c_ends_a_command_that_does_not_stop_when_the_grace_is_over(self):
        class Interrupting(hub.Console):
            looks = 0

            @property
            def last_output(self):
                Interrupting.looks += 1
                if Interrupting.looks == 6:
                    raise KeyboardInterrupt
                return time.monotonic()

            @last_output.setter
            def last_output(self, value):
                pass
        began = time.monotonic()
        with mock.patch.object(hub, "INTERRUPT_GRACE_SECONDS", 2), self.assertRaises(KeyboardInterrupt):
            self.run_script("sleep 100\n", console=Interrupting(io.StringIO()))
        self.assertLess(time.monotonic() - began, 30)


class NothingReachesGitHubButTheOptionalInitRead(unittest.TestCase):
    code = re.sub(r"(?m)^\s*#.*$", "", re.sub(r'""".*?"""', "", SOURCE, flags=re.S))

    def test_the_source_has_no_network_code(self):
        for word in (r"\burllib\b", r"http\.client", r"\bhttplib\b", r"\bsocket\b", r"\brequests\b", r"\bcurl\b", r"\bwget\b", r"api\.github\.com", r"ftplib", r"smtplib"):
            self.assertIsNone(re.search(word, self.code), word)

    def test_gh_is_called_in_one_place_and_only_by_init(self):
        self.assertEqual(re.findall(r'\["gh",', self.code), ['["gh",'])
        self.assertEqual(len(re.findall(r"\bdeps\.gh\(", self.code)), 2)
        init = self.code[self.code.index("def do_init"):self.code.index("def build_parser")]
        self.assertEqual(len(re.findall(r"\bdeps\.gh\(", init)), 2, "both reads are in do_init, behind --from-github")
        self.assertIn("if args.from_github", init)

    def test_git_is_only_read(self):
        used = set(re.findall(r'(?:git|self\.deps\.git|deps\.git)\(\["([a-z-]+)"', self.code))
        self.assertEqual(used, {"rev-parse", "status", "ls-files", "check-ignore"})
        for word in ("push", "fetch", "pull", "clone", "commit", "checkout", "reset", "worktree", "remote", "merge", "rebase", "stash"):
            self.assertIsNone(re.search(rf'git\(\["{word}"', self.code), word)

    def test_what_the_runner_itself_asks_of_az_is_the_session_and_one_read(self):
        used = set(re.findall(r'self\.az\.run\(\["([a-z-]+)", "([a-z-]+)"', self.code))
        self.assertEqual(used, {("account", "show"), ("account", "set"), ("rest", "--method")})

    def test_the_header_says_plainly_that_the_local_hub_is_the_hub(self):
        header = " ".join(SOURCE.split('"""')[1].split())
        self.assertIn("THE HUB IS THIS TOOL NOW", header)
        self.assertIn("GITHUB_ACTIONS=true and METERNAUT_HUB_LOCAL=1", header)
        self.assertIn("not a way round a guard", header)
        self.assertIn("MAIN working tree", header)
        self.assertIn("METERNAUT_LOCAL", header)

    def test_the_tool_runs_from_its_own_folder_and_names_nothing_of_the_estate(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "hub-local.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--public-ai-gateway-requested", done.stdout)
        for pattern in (r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r"\.onmicrosoft\.com", r"\b10\.\d+\.\d+\.\d+\b"):
            self.assertIsNone(re.search(pattern, SOURCE), pattern)


if __name__ == "__main__":
    unittest.main()
