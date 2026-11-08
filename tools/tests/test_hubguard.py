"""tools/hubguard.py: the one test that the tools which change Azure from the runner use to know that a run of the Hub started them.

GITHUB_ACTIONS=true alone is refused. A real GitHub runner (its own variables) passes, and so does the proof of a run of tools/hub-local.py that is alive; a proof that is missing, stale or
somebody else's is refused, and the refusal says what is missing. The tools that use it are held to it here; the tools that run inside the Operator's container are held to what they keep."""
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
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
        for name in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL", "METERNAUT_HUB_PROOF"):
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
                why = hg.what_is_missing(hubenv.inside({"GITHUB_ACTIONS": value}))
                self.assertIn("GITHUB_ACTIONS is not true and METERNAUT_HUB_PROOF is not set", why)

    def test_nothing_at_all_is_refused_in_plain_words(self):
        self.assertEqual(hg.what_is_missing({}), "GITHUB_ACTIONS is not true and METERNAUT_HUB_PROOF is not set: neither a GitHub runner nor a run of tools/hub-local.py started this")

    def test_the_runner_variables_are_the_ones_of_the_hub_workflow_and_its_job_may_ask_for_a_token(self):
        workflow = text(".github/workflows/deploy-hub.yml")
        self.assertRegex(workflow, r"(?m)^permissions:\n(?:  .*\n)*?  id-token: write\n", "every step of the Hub's job has the address of the token request, which hubguard.py asks for")
        self.assertEqual(hg.RUNNER_VARIABLES, ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL"))


class TheProofOfARunOfTheLocalHub(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def why(self, proof, alive=None):
        kwargs = {} if alive is None else {"alive": alive}
        return hg.what_is_missing({"METERNAUT_HUB_PROOF": str(proof)}, **kwargs)

    def test_the_proof_of_a_run_that_is_alive_passes_with_no_other_variable(self):
        proof = hubenv.make_proof(self.folder)
        self.assertEqual(self.why(proof), "")
        self.assertTrue(hg.started_by_the_hub({"METERNAUT_HUB_PROOF": str(proof)}))
        self.assertEqual(hg.what_is_missing({"GITHUB_ACTIONS": "true", "METERNAUT_HUB_PROOF": str(proof)}), "", "with the variable that the local Hub also sets")

    def test_a_missing_file_is_refused_and_so_is_one_that_a_run_deleted_at_its_end(self):
        proof = hubenv.make_proof(self.folder)
        proof.unlink()
        self.assertIn("names no file that is there (a run of the Hub deletes its proof when it ends)", self.why(proof))
        self.assertIn("names no file that is there", self.why(self.folder / "nothing-here"))
        self.assertIn("names no file that is there", self.why("bad\0name"))

    def test_a_proof_whose_run_is_not_alive_is_stale(self):
        proof = hubenv.make_proof(self.folder, pid=hubenv.dead_pid())
        why = self.why(proof)
        self.assertIn("is not alive: this proof is stale", why)
        self.assertIn("hub-local.lock", why)
        self.assertEqual(self.why(proof, alive=lambda pid: True), "", "what counts as alive is the caller's to give: it is asked about the pid of the lock")

    def test_a_lock_that_is_not_there_or_is_not_a_lock_is_refused(self):
        proof = hubenv.make_proof(self.folder, lock=False)
        self.assertIn("no run lock hub-local.lock is next to the folder rt: no run of the Hub is going on there", self.why(proof))
        for content in ("garbage", "[]", "42", "null", ""):
            (self.folder / "hub-local.lock").write_text(content, encoding="utf-8")
            self.assertIn("no run lock", self.why(proof), content)

    def test_a_pid_that_is_not_a_number_does_not_pass(self):
        proof = hubenv.make_proof(self.folder)
        for pid in (None, True, "1", 0, -5, 1.5, [1]):
            held = json.loads((self.folder / "hub-local.lock").read_text(encoding="utf-8"))
            held["pid"] = pid
            (self.folder / "hub-local.lock").write_text(json.dumps(held), encoding="utf-8")
            self.assertIn("is not alive", self.why(proof), pid)

    def test_a_proof_of_another_run_than_the_one_that_holds_the_lock_is_refused(self):
        first = hubenv.make_proof(self.folder, run="1762000001", token="the-token-of-the-first-run")
        second = hubenv.make_proof(self.folder, run="1762000002", token="the-token-of-the-second-run")
        self.assertEqual(self.why(second), "")
        self.assertEqual(self.why(first), "the proof is not the proof of the run that holds the lock")

    def test_a_file_that_does_not_hold_the_token_of_the_run_is_refused(self):
        proof = hubenv.make_proof(self.folder)
        for content in ("another-token", "", "a-token-of-the-tests\n", "A-TOKEN-OF-THE-TESTS"):
            proof.write_text(content, encoding="utf-8", newline="")
            self.assertIn("does not hold the token of the run that holds the lock", self.why(proof), repr(content))
        proof.write_text("a-token-of-the-tests", encoding="utf-8", newline="")
        self.assertEqual(self.why(proof), "")

    def test_the_lock_holds_the_digest_and_a_lock_that_holds_the_token_itself_is_not_taken_for_it(self):
        proof = hubenv.make_proof(self.folder)
        held = json.loads((self.folder / "hub-local.lock").read_text(encoding="utf-8"))
        self.assertEqual(held["proof"], hashlib.sha256(b"a-token-of-the-tests").hexdigest())
        self.assertEqual(hg.digest_of("a-token-of-the-tests"), held["proof"])
        held["proof"] = "a-token-of-the-tests"
        (self.folder / "hub-local.lock").write_text(json.dumps(held), encoding="utf-8")
        self.assertIn("does not hold the token", self.why(proof))
        del held["proof"]
        (self.folder / "hub-local.lock").write_text(json.dumps(held), encoding="utf-8")
        self.assertIn("does not hold the token", self.why(proof), "a lock that has dropped the digest (the run is ending) proves nothing")

    def test_a_file_that_is_not_the_proof_file_of_a_run_in_an_rt_folder_is_refused(self):
        proof = hubenv.make_proof(self.folder)
        other = proof.with_name("something-else")
        other.write_text("a-token-of-the-tests", encoding="utf-8", newline="")
        elsewhere = self.folder / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "hub-proof").write_text("a-token-of-the-tests", encoding="utf-8", newline="")
        for path in (other, elsewhere / "hub-proof", proof.parent, self.folder):
            self.assertIn("does not name the proof file of a run of tools/hub-local.py", self.why(path), str(path))

    def test_a_proof_that_is_not_valid_is_not_rescued_by_github_actions_true(self):
        proof = hubenv.make_proof(self.folder, pid=hubenv.dead_pid())
        why = hg.what_is_missing({"GITHUB_ACTIONS": "true", "METERNAUT_HUB_PROOF": str(proof)})
        self.assertIn("this proof is stale", why)

    def test_a_proof_that_is_valid_is_not_spoiled_by_a_partial_runner_environment(self):
        proof = hubenv.make_proof(self.folder)
        self.assertEqual(hg.what_is_missing({"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1", "METERNAUT_HUB_PROOF": str(proof)}), "")


class TheProcessTest(unittest.TestCase):
    def test_this_process_is_alive_and_nonsense_and_a_process_that_has_ended_are_not(self):
        self.assertTrue(hg.process_alive(os.getpid()))
        for pid in (None, 0, -1, True, False, "5", 1.0):
            self.assertFalse(hg.process_alive(pid), repr(pid))
        self.assertFalse(hg.process_alive(hubenv.dead_pid()))

    def test_the_hub_runner_uses_the_same_test_and_the_same_names(self):
        spec_hub = importlib.util.spec_from_file_location("hub_local_of_the_hubguard_tests", ROOT / "tools" / "hub-local.py")
        module = importlib.util.module_from_spec(spec_hub)
        sys.modules["hub_local_of_the_hubguard_tests"] = module
        self.addCleanup(sys.modules.pop, "hub_local_of_the_hubguard_tests", None)
        spec_hub.loader.exec_module(module)
        self.assertEqual((module.LOCK_NAME, module.TEMP_NAME, module.guard.PROOF_VARIABLE, module.guard.PROOF_NAME), (hg.LOCK_NAME, hg.TEMP_NAME, hg.PROOF_VARIABLE, hg.PROOF_NAME))
        self.assertIs(module.process_alive, module.guard.process_alive)


class TheScopeOfAStrayCall(unittest.TestCase):
    PROJECT = {"ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "ENV_RESOURCE_GROUP": "rg-of-the-project"}

    def test_the_projects_own_subscription_and_group_pass_and_any_other_is_refused_without_being_printed_back(self):
        sub, group = self.PROJECT["ENV_SUBSCRIPTION_ID"], self.PROJECT["ENV_RESOURCE_GROUP"]
        self.assertEqual(hg.other_scope(sub, group, self.PROJECT), "")
        self.assertEqual(hg.other_scope(sub.upper(), group, self.PROJECT), "", "a subscription id has no case")
        for subscription, resource_group in (("99999999-2222-3333-4444-555555555555", group), (sub, "rg-another"), (sub, group.upper()), ("", group), (sub, ""), (None, None)):
            why = hg.other_scope(subscription, resource_group, self.PROJECT)
            self.assertIn("is not the project's own (ENV_SUBSCRIPTION_ID and ENV_RESOURCE_GROUP): this command names no other group", why)
            for given in (subscription, resource_group):
                if given:
                    self.assertNotIn(given, why)

    def test_settings_that_are_not_both_set_refuse_everything(self):
        for environ in ({}, {"ENV_SUBSCRIPTION_ID": "x"}, {"ENV_RESOURCE_GROUP": "x"}, {"ENV_SUBSCRIPTION_ID": "", "ENV_RESOURCE_GROUP": "x"}):
            self.assertIn("are not both set", hg.other_scope("x", "x", environ), environ)


class TheCommandLine(unittest.TestCase):
    def run_it(self, env):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "hubguard.py")], capture_output=True, text=True, env=env)
        return done.returncode, done.stdout.strip(), done.stderr

    def environment(self, **extra):
        return {**hubenv.outside(os.environ), **extra}

    def test_it_says_yes_for_a_runner_and_no_with_the_reason_for_anything_else(self):
        code, out, err = self.run_it(self.environment(**hubenv.inside()))
        self.assertEqual((code, out, err), (0, "yes: a run of the Hub started this process", ""))
        code, out, err = self.run_it(self.environment(GITHUB_ACTIONS="true"))
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("no: GITHUB_ACTIONS=true alone is no proof"), out)
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.run_it(self.environment(METERNAUT_HUB_PROOF=str(hubenv.make_proof(folder))))
            self.assertEqual((code, out), (0, "yes: a run of the Hub started this process"), "the process that holds the lock is this one, and it is alive")

    def test_the_main_function_prints_the_answer_to_the_stream_it_is_given(self):
        out = io.StringIO()
        self.assertEqual(hg.main(environ={}, out=out), 2)
        self.assertTrue(out.getvalue().startswith("no: GITHUB_ACTIONS is not true"))
        out = io.StringIO()
        self.assertEqual(hg.main(environ=hubenv.inside(), out=out), 0)
        self.assertEqual(out.getvalue().strip(), "yes: a run of the Hub started this process")


class TheToolsThatUseIt(unittest.TestCase):
    def test_the_five_tools_that_change_azure_from_the_runner_ask_the_helper_and_no_longer_trust_github_actions_alone(self):
        for name in RUNNER_SIDE:
            source = text(f"tools/{name}")
            with self.subTest(name):
                self.assertIn('Path(__file__).with_name("hubguard.py")', source, "the helper is loaded from the tool's own folder, as the other shared helpers are")
                self.assertIn("guard.what_is_missing(", source)
                self.assertNotRegex(source, r'GITHUB_ACTIONS"\) !?= ?"true"|GITHUB_ACTIONS"\) != "true"', "the old test is gone")
                self.assertNotIn("os.environ.get(\"GITHUB_ACTIONS\")", source)
                self.assertNotIn("environ.get(\"GITHUB_ACTIONS\")", source)

    def test_the_helper_is_standard_library_only_and_keeps_the_names_that_the_local_hub_uses(self):
        source = text("tools/hubguard.py")
        imports = set(re.findall(r"(?m)^(?:import|from) (\w+)", source))
        self.assertLessEqual(imports, set(sys.stdlib_module_names))
        self.assertEqual(hg.PROOF_VARIABLE, "METERNAUT_HUB_PROOF")
        self.assertEqual((hg.LOCK_NAME, hg.TEMP_NAME, hg.PROOF_NAME), ("hub-local.lock", "rt", "hub-proof"))

    def test_the_tools_that_run_in_the_operators_container_keep_the_old_test_because_the_container_has_no_run_lock_to_compare_with(self):
        # The workflow gives the container GITHUB_ACTIONS=true and the client id of the identity, and nothing of the run: no lock, no proof file, no run id. These tools reach only what the container's own
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
