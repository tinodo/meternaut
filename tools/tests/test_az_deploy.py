import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "az-deploy.py"
spec = importlib.util.spec_from_file_location("az_deploy", TOOL)
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)
_hubenv_spec = importlib.util.spec_from_file_location("hubenv", Path(__file__).with_name("hubenv.py"))
hubenv = importlib.util.module_from_spec(_hubenv_spec)
_hubenv_spec.loader.exec_module(hubenv)

BASE = ["--subscription", "sub", "--resource-group", "rg", "--template", "t.bicep", "--parameters", "p.json"]
PROJECT = {"ENV_SUBSCRIPTION_ID": "sub", "ENV_RESOURCE_GROUP": "rg"}


class Runner:
    def __init__(self, *results):
        self.results, self.commands = list(results), []

    def __call__(self, parts):
        self.commands.append(parts)
        return self.results.pop(0)


def run(argv, runner, actions=True, extra=None):
    """The tool, in the environment of a run of the Hub (the default) or outside one, with the project's own settings and what the caller adds."""
    out, err, naps = io.StringIO(), io.StringIO(), []
    with hubenv.patched(actions, {**PROJECT, **(extra or {})}), redirect_stdout(out), redirect_stderr(err):
        code = ad.main(argv, runner=runner, sleep=naps.append)
    return code, out.getvalue(), err.getvalue(), naps


class Commands(unittest.TestCase):
    def test_what_if_reads_and_needs_no_actions_run(self):
        runner = Runner((0, "the plan\n", ""))
        code, out, err, naps = run(["what-if", *BASE], runner, actions=False)
        self.assertEqual((code, out, err, naps), (0, "the plan\n", "", []))
        (parts,) = runner.commands
        self.assertEqual(parts[1:4], ["deployment", "group", "what-if"])
        self.assertIn("@p.json", parts)
        self.assertEqual(parts[parts.index("--result-format") + 1], "FullResourcePayloads")
        self.assertNotIn("create", parts)

    def test_a_template_without_parameters_gets_no_parameter_file(self):
        runner = Runner((0, "", ""))
        argv = ["what-if", "--subscription", "sub", "--resource-group", "rg", "--template", "t.bicep"]
        self.assertEqual(run(argv, runner)[0], 0)
        self.assertNotIn("--parameters", runner.commands[0])

    def test_create_prints_only_the_output_asked_for(self):
        runner = Runner((0, "the-value\n", "a warning\n"))
        code, out, err, _ = run(["create", *BASE, "--name", "n1", "--output", "principalId"], runner)
        self.assertEqual((code, out), (0, "the-value\n"))
        self.assertIn("a warning", err)
        parts = runner.commands[0]
        self.assertEqual(parts[parts.index("--query") + 1], "properties.outputs.principalId.value")
        self.assertEqual(parts[parts.index("--name") + 1], "n1")

    def test_create_without_an_output_prints_nothing(self):
        code, out, _, _ = run(["create", *BASE, "--name", "n1"], Runner((0, "", "")))
        self.assertEqual((code, out), (0, ""))

    def test_create_refuses_outside_a_run_of_the_hub_and_without_a_name(self):
        runner = Runner()
        code, _, err, _ = run(["create", *BASE, "--name", "n"], runner, actions=False)
        self.assertEqual(code, 2)
        self.assertIn("this command deploys, and only a GitHub Actions run may do that (AGENTS.md rule 18)", err)
        self.assertEqual(run(["create", *BASE], runner)[0], 2)
        self.assertEqual(runner.commands, [])

    def test_create_refuses_a_process_that_only_says_that_github_actions_is_true_and_names_what_is_missing(self):
        runner = Runner()
        code, _, err, _ = run(["create", *BASE, "--name", "n"], runner, actions=False, extra={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 2)
        self.assertIn("GITHUB_ACTIONS=true alone is no proof", err)
        for name in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL", "METERNAUT_HUB_PROOF"):
            self.assertIn(name, err)
        self.assertEqual(runner.commands, [])

    def test_create_goes_with_the_proof_of_a_run_of_tools_hub_local_that_is_alive_and_not_with_a_stale_one(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = Runner((0, "", ""))
            proof = hubenv.make_proof(folder)
            code, _, err, _ = run(["create", *BASE, "--name", "n"], runner, actions=False, extra={"METERNAUT_HUB_PROOF": str(proof)})
            self.assertEqual((code, err, len(runner.commands)), (0, "", 1))
            runner = Runner()
            proof = hubenv.make_proof(folder, pid=hubenv.dead_pid())
            code, _, err, _ = run(["create", *BASE, "--name", "n"], runner, actions=False, extra={"METERNAUT_HUB_PROOF": str(proof)})
            self.assertEqual(code, 2)
            self.assertIn("is not alive: this proof is stale", err)
            self.assertEqual(runner.commands, [])

    def test_create_names_no_other_subscription_or_group_than_the_projects_own(self):
        for subscription, group in (("another", "rg"), ("sub", "another"), ("sub", "RG")):
            runner = Runner()
            argv = ["create", "--subscription", subscription, "--resource-group", group, "--template", "t.bicep", "--name", "n"]
            code, _, err, _ = run(argv, runner)
            self.assertEqual(code, 2, (subscription, group))
            self.assertIn("is not the project's own (ENV_SUBSCRIPTION_ID and ENV_RESOURCE_GROUP): this command names no other group", err)
            self.assertNotIn("another", err, "the names that were given are not printed back")
            self.assertEqual(runner.commands, [])
        runner = Runner((0, "", ""))
        self.assertEqual(run(["create", "--subscription", "SUB", "--resource-group", "rg", "--template", "t.bicep", "--name", "n"], runner)[0], 0, "a subscription id is not case sensitive")
        for settings in ({"ENV_SUBSCRIPTION_ID": ""}, {"ENV_RESOURCE_GROUP": ""}):
            runner = Runner()
            code, _, err, _ = run(["create", *BASE, "--name", "n"], runner, extra=settings)
            self.assertEqual(code, 2)
            self.assertIn("the project's own settings that the workflow gives every step, are not both set", err)
            self.assertEqual(runner.commands, [])

    def test_what_if_reads_and_changes_nothing_so_it_may_name_any_group(self):
        runner = Runner((0, "the plan\n", ""))
        code, out, _, _ = run(["what-if", "--subscription", "another", "--resource-group", "another", "--template", "t.bicep"], runner, actions=False)
        self.assertEqual((code, out), (0, "the plan\n"))


class Answers(unittest.TestCase):
    def test_a_soft_deleted_account_is_restored_by_the_second_command(self):
        runner = Runner((1, "", "... FlagMustBeSetForRestore ..."), (0, "ok\n", ""))
        code, _, err, naps = run(["create", *BASE, "--name", "n", "--output", "endpoint", "--restore-param", "restoreAccount"], runner)
        self.assertEqual((code, naps), (0, []))
        self.assertNotIn("restoreAccount=true", runner.commands[0])
        self.assertIn("restoreAccount=true", runner.commands[1])
        self.assertIn("restored", err)

    def test_the_restore_is_tried_once_only(self):
        runner = Runner((1, "", "FlagMustBeSetForRestore"), (1, "", "FlagMustBeSetForRestore"))
        code, _, err, _ = run(["create", *BASE, "--name", "n", "--restore-param", "restoreAccount"], runner)
        self.assertEqual(code, 1)
        self.assertEqual(len(runner.commands), 2)

    def test_the_restore_is_not_tried_without_the_parameter(self):
        runner = Runner((1, "", "FlagMustBeSetForRestore"))
        self.assertEqual(run(["what-if", *BASE], runner)[0], 1)
        self.assertEqual(len(runner.commands), 1)

    def test_a_transient_answer_is_tried_again_after_a_minute_up_to_three_tries(self):
        runner = Runner((1, "", "IfMatchPreconditionFailed"), (1, "", "deadlock detected by _ModuleLock"), (0, "", ""))
        code, _, _, naps = run(["create", *BASE, "--name", "n"], runner)
        self.assertEqual((code, naps, len(runner.commands)), (0, [60, 60], 3))

    def test_a_third_failure_stops_with_the_services_text(self):
        runner = Runner((1, "", "ServiceBusy"), (1, "", "ServiceBusy"), (1, "", "ServiceBusy: still"))
        code, _, err, naps = run(["create", *BASE, "--name", "n"], runner)
        self.assertEqual((code, naps), (1, [60, 60]))
        self.assertIn("ServiceBusy: still", err)

    def test_anything_else_stops_at_once(self):
        runner = Runner((1, "", "InvalidTemplate: the template is wrong"))
        code, _, err, naps = run(["create", *BASE, "--name", "n"], runner)
        self.assertEqual((code, naps, len(runner.commands)), (1, [], 1))
        self.assertIn("InvalidTemplate", err)


if __name__ == "__main__":
    unittest.main()
