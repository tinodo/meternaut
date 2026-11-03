import importlib.util
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "az-deploy.py"
spec = importlib.util.spec_from_file_location("az_deploy", TOOL)
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)

BASE = ["--subscription", "sub", "--resource-group", "rg", "--template", "t.bicep", "--parameters", "p.json"]


class Runner:
    def __init__(self, *results):
        self.results, self.commands = list(results), []

    def __call__(self, parts):
        self.commands.append(parts)
        return self.results.pop(0)


def run(argv, runner, actions=True):
    out, err, naps = io.StringIO(), io.StringIO(), []
    env = {"GITHUB_ACTIONS": "true"} if actions else {}
    with mock.patch.dict(os.environ, env, clear=False), redirect_stdout(out), redirect_stderr(err):
        if not actions:
            os.environ.pop("GITHUB_ACTIONS", None)
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

    def test_create_refuses_outside_github_actions_and_without_a_name(self):
        runner = Runner()
        self.assertEqual(run(["create", *BASE, "--name", "n"], runner, actions=False)[0], 2)
        self.assertEqual(run(["create", *BASE], runner)[0], 2)
        self.assertEqual(runner.commands, [])


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
