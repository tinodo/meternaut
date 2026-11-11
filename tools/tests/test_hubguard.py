"""tools/hubguard.py: the one test that the tools which change Azure from the runner use to know that a run of the Hub started them.

GITHUB_ACTIONS=true alone is refused. A real GitHub runner (its own variables) passes. A refusal says nothing of what counts as a run: only a person who asks at a terminal is told. The tools that use it
are held to it here; the tools that run inside the Operator's container are held to what they keep."""
import importlib.util
import io
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hubguard_of_its_tests", ROOT / "tools" / "hubguard.py")
hg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hg)
_hubenv_spec = importlib.util.spec_from_file_location("hubenv", Path(__file__).with_name("hubenv.py"))
hubenv = importlib.util.module_from_spec(_hubenv_spec)
_hubenv_spec.loader.exec_module(hubenv)

RUNNER_SIDE = ("az-deploy.py", "retire-old.py", "cases-move.py", "aigateway-prep.py", "operator-run.py")
CONTAINER_SIDE = ("aigateway-check.py", "check-helpers.py", "aisec-helpers.py")
# What a refusal must not say: nothing that a process that reads it could copy.
NOTHING_TO_COPY = re.compile(r"(?i)github|meternaut|proof|actions|token|lock|\brt\b|_id\b|repository|environment|variable|file|hub-")


def text(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class TheRealRunner(unittest.TestCase):
    def test_the_variables_of_a_github_runner_are_the_proof_of_one(self):
        self.assertEqual(hg.what_is_missing(hubenv.inside()), "")
        self.assertTrue(hg.started_by_the_hub(hubenv.inside()))

    def test_github_actions_true_alone_is_refused_and_the_refusal_names_what_is_missing(self):
        why = hg.what_is_missing({"GITHUB_ACTIONS": "true"})
        self.assertFalse(hg.started_by_the_hub({"GITHUB_ACTIONS": "true"}))
        self.assertIn("GITHUB_ACTIONS=true alone is no proof", why)
        for name in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL"):
            self.assertIn(name, why)

    def test_each_variable_of_the_runner_is_needed_and_only_the_missing_ones_are_named(self):
        for name in hg.RUNNER_VARIABLES:
            with self.subTest(name):
                environ = hubenv.inside()
                del environ[name]
                why = hg.what_is_missing(environ)
                self.assertIn(f"({name} not set)", why)
                environ[name] = ""
                self.assertIn(f"({name} not set)", hg.what_is_missing(environ), "an empty value is not set")

    def test_only_the_word_true_counts_for_github_actions(self):
        for value in ("false", "True", "1", "yes", ""):
            with self.subTest(value):
                self.assertIn("GITHUB_ACTIONS is not true", hg.what_is_missing(hubenv.inside({"GITHUB_ACTIONS": value})))

    def test_nothing_at_all_is_refused_in_plain_words(self):
        self.assertEqual(hg.what_is_missing({}), "GITHUB_ACTIONS is not true: only a run of the Hub workflow on a GitHub runner started this")

    def test_a_refusal_says_only_that_the_call_was_not_started_by_a_run_of_the_hub_and_nothing_that_could_be_copied(self):
        for environ in ({}, {"GITHUB_ACTIONS": "true"}, {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1"}):
            self.assertEqual(hg.refusal(environ), hg.REFUSAL, environ)
        self.assertEqual(hg.REFUSAL, "this call was not started by a run of the Hub")
        self.assertIsNone(NOTHING_TO_COPY.search(hg.REFUSAL), hg.REFUSAL)
        self.assertEqual(hg.refusal(hubenv.inside()), "")
        self.assertIn("GITHUB_RUN_ID", hg.what_is_missing({"GITHUB_ACTIONS": "true"}), "the long text exists, for a person who asks")

    def test_the_runner_variables_are_the_ones_of_the_hub_workflow_and_its_job_may_ask_for_a_token(self):
        workflow = text(".github/workflows/deploy-hub.yml")
        self.assertRegex(workflow, r"(?m)^permissions:\n(?:  .*\n)*?  id-token: write\n", "every step of the Hub's job has the address of the token request, which hubguard.py asks for")
        self.assertEqual(hg.RUNNER_VARIABLES, ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL"))


class TheScopeOfAStrayCall(unittest.TestCase):
    PROJECT = {"ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "ENV_RESOURCE_GROUP": "rg-of-the-project"}

    def test_the_projects_own_subscription_and_group_pass_and_any_other_is_refused_without_being_printed_back(self):
        sub, group = self.PROJECT["ENV_SUBSCRIPTION_ID"], self.PROJECT["ENV_RESOURCE_GROUP"]
        self.assertEqual(hg.other_scope(sub, group, self.PROJECT), "")
        self.assertEqual(hg.other_scope(sub.upper(), group, self.PROJECT), "", "a subscription id has no case")
        for subscription, resource_group in (("99999999-2222-3333-4444-555555555555", group), (sub, "rg-another"), (sub, group.upper()), ("", group), (sub, ""), (None, None)):
            why = hg.other_scope(subscription, resource_group, self.PROJECT)
            self.assertEqual(why, "the subscription or the resource group is not the project's own: this command names no other group")
            for given in (subscription, resource_group):
                if given:
                    self.assertNotIn(given, why)
        self.assertNotIn("ENV_", why, "the settings are not named: a refusal says nothing to copy")

    def test_settings_that_are_not_both_set_refuse_everything(self):
        for environ in ({}, {"ENV_SUBSCRIPTION_ID": "x"}, {"ENV_RESOURCE_GROUP": "x"}, {"ENV_SUBSCRIPTION_ID": "", "ENV_RESOURCE_GROUP": "x"}):
            self.assertIn("are not both set for this call", hg.other_scope("x", "x", environ), environ)

    def test_an_id_is_in_the_project_when_it_names_its_subscription_and_group_and_has_no_case(self):
        sub, group = self.PROJECT["ENV_SUBSCRIPTION_ID"], self.PROJECT["ENV_RESOURCE_GROUP"]
        inside = f"/subscriptions/{sub}/resourceGroups/{group}/providers/Microsoft.Network/virtualNetworks/vnet-x/subnets/snet-x"
        self.assertTrue(hg.in_the_project(inside, self.PROJECT))
        self.assertTrue(hg.in_the_project(inside.upper(), self.PROJECT), "Azure writes the group of an id in the case that suits it")
        for other in (inside.replace(group, "rg-another"), inside.replace(sub, "99999999-2222-3333-4444-555555555555"), inside.replace(f"{group}/providers", f"{group}-more/providers"),
                      f"/subscriptions/{sub}/resourceGroups/{group}", f"/subscriptions/{sub}/resourceGroups/{group}/", "", None, "snet-x"):
            self.assertFalse(hg.in_the_project(other, self.PROJECT), other)
        self.assertFalse(hg.in_the_project(inside, {}), "no settings, no project")


class TheCommandLine(unittest.TestCase):
    def run_it(self, env):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "hubguard.py")], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout.strip(), done.stderr

    def environment(self, **extra):
        return {**hubenv.outside(os.environ), **extra}

    def test_it_says_yes_for_a_runner_and_to_anything_that_is_no_terminal_only_that_the_call_was_not_started_by_a_run_of_the_hub(self):
        code, out, err = self.run_it(self.environment(**hubenv.inside()))
        self.assertEqual((code, out, err), (0, "yes: a run of the Hub started this process", ""))
        for environ in ({}, {"GITHUB_ACTIONS": "true"}):
            code, out, err = self.run_it(self.environment(**environ))
            self.assertEqual((code, out, err), (2, "no: this call was not started by a run of the Hub", ""), "a pipe is no terminal: nothing of what is missing")

    def test_the_main_function_tells_a_person_what_is_missing_and_anything_else_only_the_refusal(self):
        out = io.StringIO()
        self.assertEqual(hg.main(environ={}, out=out), 2)
        self.assertEqual(out.getvalue().strip(), "no: this call was not started by a run of the Hub")
        out = io.StringIO()
        self.assertEqual(hg.main(environ={"GITHUB_ACTIONS": "true"}, out=out, person=True), 2)
        self.assertTrue(out.getvalue().startswith("no: GITHUB_ACTIONS=true alone is no proof"), out.getvalue())
        self.assertIn("GITHUB_REPOSITORY", out.getvalue())
        out = io.StringIO()
        self.assertEqual(hg.main(environ=hubenv.inside(), out=out, person=True), 0)
        self.assertEqual(out.getvalue().strip(), "yes: a run of the Hub started this process")


class TheToolsThatUseIt(unittest.TestCase):
    def test_the_five_tools_that_change_azure_from_the_runner_ask_the_helper_and_no_longer_trust_github_actions_alone(self):
        for name in RUNNER_SIDE:
            source = text(f"tools/{name}")
            with self.subTest(name):
                self.assertIn('Path(__file__).with_name("hubguard.py")', source, "the helper is loaded from the tool's own folder, as the other shared helpers are")
                self.assertIn("guard.refusal(", source)
                self.assertNotIn("guard.what_is_missing(", source, "a tool says only that the call was not started by a run of the Hub: what is missing is for a person at a terminal")
                self.assertIn("only a run of the Hub may do that (AGENTS.md rule 18)", source)
                self.assertNotRegex(source, r'GITHUB_ACTIONS"\) !?= ?"true"|GITHUB_ACTIONS"\) != "true"', "the old test is gone")
                self.assertNotIn("os.environ.get(\"GITHUB_ACTIONS\")", source)
                self.assertNotIn("environ.get(\"GITHUB_ACTIONS\")", source)
                for word in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN"):
                    self.assertNotIn(word, source, f"{name} does not name what counts as a run of the Hub")

    def test_all_five_name_only_the_projects_own_subscription_and_group_when_they_change_something(self):
        for name in ("az-deploy.py", "aigateway-prep.py", "operator-run.py"):
            self.assertIn("guard.other_scope(", text(f"tools/{name}"), name)
        for name in ("retire-old.py", "cases-move.py"):
            source = text(f"tools/{name}")
            self.assertIn("def refuse_unless_the_workflows_own(", source, name)
            self.assertIn('environ.get("ENV_RESOURCE_GROUP")', source, name)
            self.assertIn('environ.get("ENV_SUBSCRIPTION_ID")', source, name)
        self.assertIn("guard.in_the_project(", text("tools/operator-run.py"), "the subnet and the identity are resources of the project's group")
        prep = text("tools/aigateway-prep.py")
        self.assertEqual(len(re.findall(r"\bonly_in_the_project\(args\)", prep)), 2, "the two commands that write")

    def test_the_helper_is_standard_library_only(self):
        source = text("tools/hubguard.py")
        imports = set(re.findall(r"(?m)^(?:import|from) (\w+)", source))
        self.assertLessEqual(imports, set(sys.stdlib_module_names))

    def test_the_tools_that_run_in_the_operators_container_keep_the_old_test_because_the_container_has_no_run_id_to_compare_with(self):
        # The workflow gives the container GITHUB_ACTIONS=true and the client id of the identity, and nothing of the run: no run id. These tools reach only what the container's own
        # identity may reach, and the services behind them are private (the Foundry resource has public network access Disabled). So they are not moved, and hubguard.py is not sent to the container.
        for name in CONTAINER_SIDE:
            source = text(f"tools/{name}")
            with self.subTest(name):
                self.assertIn('os.environ.get("GITHUB_ACTIONS") != "true"', source)
                self.assertNotIn("hubguard", source)
        workflow = text(".github/workflows/deploy-hub.yml")
        in_the_container = {name for name in re.findall(r"TOOL_NAME=([a-z-]+)", workflow) if (ROOT / "tools" / f"{name}.py").is_file()}
        self.assertGreaterEqual(len(in_the_container), 4, "the workflow runs tools in the container")
        for tool in in_the_container:
            self.assertNotIn("hubguard", text(f"tools/{tool}.py"), tool)
        self.assertEqual(sorted(in_the_container & {name[:-3] for name in RUNNER_SIDE}), [], "no tool of the runner side is sent to the container")

    def test_the_guard_of_a_hand_step_that_refuses_apply_inside_a_run_is_another_guard_and_is_left_alone(self):
        for name in ("access-requirements.py", "entra-setup.py", "governance-setup.py"):
            self.assertIn('GITHUB_ACTIONS") == "true"', text(f"tools/{name}"), name)


if __name__ == "__main__":
    unittest.main()
