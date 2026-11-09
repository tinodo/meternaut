"""tools/hubguard.py: the one test that the tools which change Azure use to know that a run of the Hub started them.

Only the proof file of a run of tools/hub-local.py counts: one that is alive, found in the repository's own local folder and started when its lock says. A proof that is missing, stale, somebody
else's or in another folder is refused, and so is everything that a GitHub runner sets (GITHUB_ACTIONS=true and the rest): any process can set it, and since 2026-11-08 a GitHub run changes nothing
in Azure (AGENTS.md rule 18). A refusal says nothing of what counts as a run: only a person who asks at a terminal is told. The tools that use it are held to it here; the tools that run inside the
Operator's container are held to what they keep."""
import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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


class OnlyTheProofFileCounts(unittest.TestCase):
    """Since 2026-11-08 no GitHub run changes Azure (AGENTS.md rule 18), so no GitHub runner is left to start these tools. What a runner sets proves nothing, and any process can set it."""

    A_GITHUB_RUNNER = {**hubenv.RUNNER, "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "a-bearer-of-the-tests", "GITHUB_RUN_NUMBER": "288", "GITHUB_ACTOR": "someone", "GITHUB_SHA": "0" * 40,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW": "Hub", "GITHUB_EVENT_NAME": "workflow_dispatch", "RUNNER_OS": "Linux", "RUNNER_TEMP": "/home/runner/work/_temp", "CI": "true"}

    def test_the_whole_environment_of_a_github_runner_is_refused_and_so_is_each_part_of_it(self):
        for environ in (hubenv.RUNNER, self.A_GITHUB_RUNNER):
            self.assertFalse(hg.started_by_the_hub(environ))
            self.assertEqual(hg.refusal(environ), hg.REFUSAL)
            self.assertIn("METERNAUT_HUB_PROOF is not set", hg.what_is_missing(environ))
        for name in self.A_GITHUB_RUNNER:
            with self.subTest(name):
                self.assertFalse(hg.started_by_the_hub({name: self.A_GITHUB_RUNNER[name]}), "alone")
                self.assertFalse(hg.started_by_the_hub({key: value for key, value in self.A_GITHUB_RUNNER.items() if key != name}), "all the others")

    def test_every_set_of_the_four_variables_that_the_helper_used_to_ask_for_is_refused(self):
        names = tuple(hubenv.RUNNER)
        for size in range(len(names) + 1):
            for chosen in itertools.combinations(names, size):
                self.assertFalse(hg.started_by_the_hub({name: hubenv.RUNNER[name] for name in chosen}), chosen)

    def test_github_actions_true_alone_is_refused_and_the_long_text_for_a_person_says_why(self):
        why = hg.what_is_missing({"GITHUB_ACTIONS": "true"})
        self.assertFalse(hg.started_by_the_hub({"GITHUB_ACTIONS": "true"}))
        self.assertIn("METERNAUT_HUB_PROOF is not set", why)
        self.assertIn("only the proof file of a run of tools/hub-local.py counts", why)
        self.assertIn("GITHUB_ACTIONS=true and what else a GitHub runner sets are no proof", why)
        self.assertIn("AGENTS.md rule 18", why)

    def test_the_value_of_github_actions_makes_no_difference_to_anything(self):
        for value in ("true", "false", "True", "1", "yes", ""):
            with self.subTest(value):
                self.assertEqual(hg.what_is_missing({"GITHUB_ACTIONS": value}), hg.what_is_missing({}))

    def test_nothing_at_all_is_refused_in_plain_words(self):
        self.assertEqual(hg.what_is_missing({}), "METERNAUT_HUB_PROOF is not set: only the proof file of a run of tools/hub-local.py counts. GITHUB_ACTIONS=true and what else a GitHub runner sets are no proof: "
                                                 "any process can set them, and a GitHub run changes nothing in Azure since 2026-11-08 (AGENTS.md rule 18)")

    def test_a_refusal_says_only_that_the_call_was_not_started_by_a_run_of_the_hub_and_nothing_that_could_be_copied(self):
        stale = self.stale_proof_environment()
        for environ in ({}, {"GITHUB_ACTIONS": "true"}, hubenv.RUNNER, self.A_GITHUB_RUNNER, {"METERNAUT_HUB_PROOF": "somewhere"}, stale):
            self.assertEqual(hg.refusal(environ), hg.REFUSAL, environ)
        self.assertEqual(hg.REFUSAL, "this call was not started by a run of the Hub")
        self.assertIsNone(NOTHING_TO_COPY.search(hg.REFUSAL), hg.REFUSAL)
        self.assertEqual(hg.refusal(hubenv.inside()), "")
        self.assertIn("METERNAUT_HUB_PROOF", hg.what_is_missing({"GITHUB_ACTIONS": "true"}), "the long text exists, for a person who asks")

    def stale_proof_environment(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return hubenv.proof_environment(folder.name, pid=hubenv.dead_pid())

    def test_the_helper_has_no_other_way_in_than_the_proof_file_and_reads_nothing_that_a_runner_sets(self):
        source = text("tools/hubguard.py")
        code = "\n".join(line for line in re.sub(r'""".*?"""', "", source, flags=re.S).splitlines() if not line.strip().startswith("#"))
        self.assertFalse(hasattr(hg, "RUNNER_VARIABLES"), "the list of the variables of a runner is gone")
        for word in ("RUNNER_VARIABLES", "GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL", 'get("GITHUB_ACTIONS")', "GITHUB_ACTIONS\") =="):
            self.assertNotIn(word, code, word)
        self.assertEqual(sorted(re.findall(r"env\.get\(([A-Z_]+)\)", code)), ["LOCAL_VARIABLE", "PROOF_VARIABLE"], "the variables that the test reads are the one that names the proof file and the one that names the local folder")
        docstring = source.split('"""')[1]
        self.assertIn("The proof file is the only way in", docstring)
        self.assertIn("AGENTS.md rule 18", docstring)
        self.assertIn("It can call az itself, read the proof file of a run that is alive and use it, or make a proof of its own", " ".join(docstring.split()))

    def test_the_premise_of_the_one_way_in_is_the_rule_of_the_repository_and_the_workflow_is_not_the_one_that_gives_a_runner_a_proof(self):
        rule = " ".join(text("AGENTS.md").split())
        self.assertIn("a GitHub workflow run changes nothing in Azure any more", rule, "if rule 18 changes, so does this guard: the tools would have to know a GitHub runner again")
        self.assertNotIn("hub-proof", text(".github/workflows/deploy-hub.yml"), "the workflow makes no proof: only tools/hub-local.py does")
        self.assertNotIn("METERNAUT_HUB_PROOF", text(".github/workflows/deploy-hub.yml"))


class TheProofOfARunOfTheLocalHub(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def environment(self, proof, **extra):
        return {"METERNAUT_HUB_PROOF": str(proof), "METERNAUT_LOCAL": str(self.folder), **extra}

    def why(self, proof, alive=None, **injected):
        if alive is not None:
            injected["alive"] = alive
        return hg.what_is_missing(self.environment(proof), **injected)

    def test_the_proof_of_a_run_that_is_alive_passes_with_no_other_variable(self):
        proof = hubenv.make_proof(self.folder)
        self.assertEqual(self.why(proof), "")
        self.assertTrue(hg.started_by_the_hub(self.environment(proof)))
        self.assertEqual(hg.what_is_missing(self.environment(proof, GITHUB_ACTIONS="true")), "", "with the variable that the local Hub also sets")

    def test_a_missing_file_is_refused_and_so_is_one_that_a_run_deleted_at_its_end(self):
        proof = hubenv.make_proof(self.folder)
        proof.unlink()
        self.assertIn("names no file that is there", self.why(proof))
        self.assertIn("a run of the Hub deletes its proof when it ends", self.why(proof))
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
        self.assertIn("no run lock hub-local.lock is in the repository's own local folder: no run of the Hub is going on", self.why(proof))
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

    def test_a_file_that_is_not_the_proof_file_of_a_run_in_the_rt_folder_of_the_local_folder_is_refused(self):
        proof = hubenv.make_proof(self.folder)
        other = proof.with_name("something-else")
        other.write_text("a-token-of-the-tests", encoding="utf-8", newline="")
        elsewhere = self.folder / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "hub-proof").write_text("a-token-of-the-tests", encoding="utf-8", newline="")
        deeper = self.folder / "rt" / "1762000000" / "deeper"
        deeper.mkdir()
        (deeper / "hub-proof").write_text("a-token-of-the-tests", encoding="utf-8", newline="")
        for path in (other, elsewhere / "hub-proof", proof.parent, self.folder, deeper / "hub-proof"):
            self.assertIn("is not the proof file of a run in the repository's own local folder", self.why(path), str(path))

    def test_a_hostile_folder_with_its_own_proof_and_its_own_lock_is_refused_whatever_sits_next_to_it(self):
        own = self.folder / "own-local"
        hostile = self.folder / "hostile-local"
        real = hubenv.make_proof(own, run="1762000002", token="the-token-of-the-real-run")
        forged = hubenv.make_proof(hostile, run="1", token="a-token-that-the-forger-made")
        environ = {"METERNAUT_HUB_PROOF": str(forged), "METERNAUT_LOCAL": str(own)}
        self.assertIn("is not the proof file of a run in the repository's own local folder", hg.what_is_missing(environ))
        self.assertFalse(hg.started_by_the_hub(environ))
        self.assertEqual(hg.what_is_missing({"METERNAUT_HUB_PROOF": str(real), "METERNAUT_LOCAL": str(own)}), "", "the proof of the real run in the own folder is the one that counts")
        (own / "hub-local.lock").unlink()
        self.assertIn("no run lock", hg.what_is_missing({"METERNAUT_HUB_PROOF": str(real), "METERNAUT_LOCAL": str(own)}), "the lock is the own folder's: the forged one next to the forged proof is not read")
        self.assertIn("is not the proof file of a run in the repository's own local folder", hg.what_is_missing(environ), "and the forged proof is still refused, whichever lock there is")

    def test_the_local_folder_is_found_from_the_repository_and_not_from_the_path_that_the_caller_names(self):
        main = self.folder / "main"
        (main / "local").mkdir(parents=True)
        (main / ".git").mkdir()
        real = hubenv.make_proof(main / "local", run="1762000002", token="the-token-of-the-real-run")
        forged = hubenv.make_proof(self.folder / "hostile-local", run="1", token="a-token-that-the-forger-made")
        asked = []

        def git(args, cwd):
            asked.append((list(args), Path(cwd)))
            return 0, str(main / ".git") + "\n", ""
        self.assertEqual(hg.what_is_missing({"METERNAUT_HUB_PROOF": str(real)}, git=git), "")
        self.assertIn("is not the proof file of a run in the repository's own local folder", hg.what_is_missing({"METERNAUT_HUB_PROOF": str(forged)}, git=git))
        self.assertEqual({cwd for _, cwd in asked}, {Path(hg.__file__).resolve().parent}, "git is asked from the folder of the tool, whatever the caller's folder is")
        no_git = lambda args, cwd: (128, "", "fatal: not a git repository")
        self.assertIn("the repository's own local folder cannot be found", hg.what_is_missing({"METERNAUT_HUB_PROOF": str(real)}, git=no_git))

    def test_a_proof_whose_process_started_at_another_time_than_the_lock_says_is_refused_because_its_number_was_used_again(self):
        mine = hg.process_started(os.getpid())
        proof = hubenv.make_proof(self.folder, start="a-start-that-this-process-never-had")
        self.assertIn("did not start when the lock says", self.why(proof))
        self.assertIn("its number was used again", self.why(proof))
        self.assertEqual(self.why(proof, started=lambda pid: "a-start-that-this-process-never-had"), "", "what the platform says now is the caller's to give: it is asked about the pid of the lock")
        self.assertIn("did not start when the lock says", self.why(hubenv.make_proof(self.folder, start="one"), started=lambda pid: "another"))
        if mine != hg.UNKNOWN:
            self.assertEqual(self.why(hubenv.make_proof(self.folder, start=mine)), "", "the start that the platform gives for this process is the one that counts")

    def test_a_start_that_is_not_known_makes_the_check_no_weaker_than_the_one_that_asks_only_whether_the_number_is_alive(self):
        proof = hubenv.make_proof(self.folder, start=hg.UNKNOWN)
        self.assertEqual(self.why(proof), "", "the lock does not know when its process started")
        proof = hubenv.make_proof(self.folder, start="a-start")
        self.assertEqual(self.why(proof, started=lambda pid: hg.UNKNOWN), "", "the platform does not say now")
        held = json.loads((self.folder / "hub-local.lock").read_text(encoding="utf-8"))
        del held["processStart"]
        (self.folder / "hub-local.lock").write_text(json.dumps(held), encoding="utf-8")
        self.assertEqual(self.why(proof), "", "a lock of an older run, which holds no start")
        self.assertIn("is not alive", self.why(proof, alive=lambda pid: False), "a number that is not alive is refused whatever the start says")

    def test_a_proof_that_is_not_valid_is_not_rescued_by_github_actions_true_or_by_a_whole_runner(self):
        proof = hubenv.make_proof(self.folder, pid=hubenv.dead_pid())
        for extra in ({"GITHUB_ACTIONS": "true"}, OnlyTheProofFileCounts.A_GITHUB_RUNNER):
            why = hg.what_is_missing(self.environment(proof, **extra))
            self.assertIn("this proof is stale", why)

    def test_a_proof_that_is_valid_is_not_spoiled_by_the_environment_of_a_runner_whether_it_is_partial_or_whole(self):
        proof = hubenv.make_proof(self.folder)
        for extra in ({"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1"}, hubenv.RUNNER, OnlyTheProofFileCounts.A_GITHUB_RUNNER):
            self.assertEqual(hg.what_is_missing(self.environment(proof, **extra)), "")


class TheProcessTest(unittest.TestCase):
    def test_this_process_is_alive_and_nonsense_and_a_process_that_has_ended_are_not(self):
        self.assertTrue(hg.process_alive(os.getpid()))
        for pid in (None, 0, -1, True, False, "5", 1.0):
            self.assertFalse(hg.process_alive(pid), repr(pid))
        self.assertFalse(hg.process_alive(hubenv.dead_pid()))

    def test_the_hub_runner_uses_the_same_test_the_same_names_and_the_same_way_to_find_the_local_folder(self):
        spec_hub = importlib.util.spec_from_file_location("hub_local_of_the_hubguard_tests", ROOT / "tools" / "hub-local.py")
        module = importlib.util.module_from_spec(spec_hub)
        sys.modules["hub_local_of_the_hubguard_tests"] = module
        self.addCleanup(sys.modules.pop, "hub_local_of_the_hubguard_tests", None)
        spec_hub.loader.exec_module(module)
        self.assertEqual((module.LOCK_NAME, module.TEMP_NAME, module.guard.PROOF_VARIABLE, module.guard.PROOF_NAME), (hg.LOCK_NAME, hg.TEMP_NAME, hg.PROOF_VARIABLE, hg.PROOF_NAME))
        self.assertIs(module.process_alive, module.guard.process_alive)
        self.assertEqual(module.LOCAL_OVERRIDE, hg.LOCAL_VARIABLE)
        self.assertIs(module.run_git, module.guard.run_git)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(module.resolve_local_dir({hg.LOCAL_VARIABLE: folder}, Path(folder)), hg.local_folder({hg.LOCAL_VARIABLE: folder}), "the same folder, found by the same function")
        self.assertEqual(module.resolve_local_dir({}, ROOT), hg.local_folder({}, ROOT))


class TheStartOfAProcess(unittest.TestCase):
    def test_a_process_has_one_start_and_a_process_that_started_later_has_another(self):
        mine = hg.process_started(os.getpid())
        if mine == hg.UNKNOWN:
            self.skipTest("this platform does not say when a process started")
        self.assertEqual(mine, hg.process_started(os.getpid()))
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            theirs = hg.process_started(child.pid)
        finally:
            child.kill()
            child.wait()
        self.assertNotIn(theirs, (hg.UNKNOWN, mine))

    def test_a_number_that_means_nothing_or_that_no_process_has_is_unknown(self):
        for pid in (None, 0, -1, True, "5", 1.5, [1]):
            self.assertEqual(hg.process_started(pid), hg.UNKNOWN, repr(pid))
        self.assertEqual(hg.process_started(hubenv.dead_pid()), hg.UNKNOWN)

    def test_what_the_platform_cannot_say_is_unknown_and_never_an_error(self):
        if os.name == "nt":
            with mock.patch.object(hg, "started_on_windows", side_effect=OSError("denied")):
                self.assertEqual(hg.process_started(os.getpid()), hg.UNKNOWN)
        else:
            with mock.patch.object(hg, "started_by_ps", side_effect=OSError("no ps")), mock.patch.object(hg.sys, "platform", "darwin"):
                self.assertEqual(hg.process_started(os.getpid()), hg.UNKNOWN)

    def test_the_start_that_linux_gives_is_read_from_the_stat_line_with_the_boot_id_and_a_name_with_brackets_does_not_move_it(self):
        line = "4242 (my (odd) name) S 1 4242 4242 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 1 0 987654 12345678 1234 18446744073709551615 1 1 0 0 0 0 0 0 0 0 0 0 17 3 0 0 0 0 0"
        self.assertEqual(hg.linux_start(line, "a-boot-id\n"), "a-boot-id:987654")
        self.assertNotEqual(hg.linux_start(line, "another-boot-id"), hg.linux_start(line, "a-boot-id"), "the same number after a reboot is another start")
        for bad in ("", "4242 (x) S 1", "no bracket here"):
            with self.assertRaises((ValueError, IndexError)):
                hg.linux_start(bad, "a-boot-id")

    def test_the_start_that_ps_gives_is_its_text_in_one_line_and_what_it_cannot_say_is_unknown(self):
        said = types.SimpleNamespace(returncode=0, stdout="Mon Nov  9 01:48:22 2026\n")
        with mock.patch.object(hg.subprocess, "run", return_value=said) as called:
            self.assertEqual(hg.started_by_ps(4242), "Mon Nov 9 01:48:22 2026")
        self.assertEqual(called.call_args.args[0], ["ps", "-o", "lstart=", "-p", "4242"])
        for answer in (types.SimpleNamespace(returncode=1, stdout=""), types.SimpleNamespace(returncode=0, stdout="  \n")):
            with mock.patch.object(hg.subprocess, "run", return_value=answer):
                self.assertEqual(hg.started_by_ps(4242), hg.UNKNOWN)


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


class TheLocalFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_the_variable_names_the_folder_and_a_blank_one_names_none(self):
        elsewhere = self.base / "elsewhere"
        self.assertEqual(hg.local_folder({"METERNAUT_LOCAL": str(elsewhere)}), elsewhere.resolve())
        said = []
        git = lambda args, cwd: said.append(args) or (0, str(self.base / ".git") + "\n", "")
        for blank in ("", "   "):
            self.assertEqual(hg.local_folder({"METERNAUT_LOCAL": blank}, self.base, git), self.base / "local")
        self.assertEqual(len(said), 2, "a blank variable is no variable: git is asked")

    def test_git_says_where_the_main_working_tree_is_from_the_folder_of_the_tool_unless_another_is_given(self):
        asked = []

        def git(args, cwd):
            asked.append((list(args), Path(cwd)))
            return 0, str(self.base / "main" / ".git") + "\n", ""
        self.assertEqual(hg.local_folder({}, None, git), self.base / "main" / "local")
        self.assertEqual(asked, [(["rev-parse", "--path-format=absolute", "--git-common-dir"], Path(hg.__file__).resolve().parent)])
        asked.clear()
        hg.local_folder({}, self.base, git)
        self.assertEqual(asked[0][1], self.base)

    def test_an_old_git_is_asked_again_a_relative_answer_is_made_absolute_and_what_is_no_dot_git_folder_or_unsaid_is_refused(self):
        calls = []

        def old_git(args, cwd):
            calls.append(list(args))
            return (129, "", "unknown option") if "--path-format=absolute" in args else (0, ".git\n", "")
        self.assertEqual(hg.local_folder({}, self.base, old_git), self.base.resolve() / "local")
        self.assertEqual(len(calls), 2)
        for answer in ((128, "", "fatal: not a git repository"), (0, "", ""), (0, str(self.base / "repo.git") + "\n", "")):
            with self.assertRaises(hg.NoLocalFolder) as caught:
                hg.local_folder({}, self.base, lambda args, cwd, answer=answer: answer)
            self.assertIn("METERNAUT_LOCAL", str(caught.exception))

    def test_git_is_only_read_here(self):
        source = text("tools/hubguard.py")
        asked = set(re.findall(r'git\(\["([a-z-]+)"', source))
        self.assertEqual(asked, {"rev-parse"})


class TheCommandLine(unittest.TestCase):
    def run_it(self, env):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "hubguard.py")], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout.strip(), done.stderr

    def environment(self, **extra):
        return {**hubenv.outside(os.environ), **extra}

    def test_it_says_yes_for_a_proof_and_to_anything_that_is_no_terminal_only_that_the_call_was_not_started_by_a_run_of_the_hub_whatever_a_runner_sets(self):
        code, out, err = self.run_it(self.environment(**hubenv.inside()))
        self.assertEqual((code, out, err), (0, "yes: a run of the Hub started this process", ""), "the real proof that the tests make for this process, which is alive")
        for environ in ({}, {"GITHUB_ACTIONS": "true"}, hubenv.RUNNER, OnlyTheProofFileCounts.A_GITHUB_RUNNER):
            code, out, err = self.run_it(self.environment(**environ))
            self.assertEqual((code, out, err), (2, "no: this call was not started by a run of the Hub", ""), "a pipe is no terminal: nothing of what is missing")
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.run_it(self.environment(**hubenv.proof_environment(folder)))
            self.assertEqual((code, out), (0, "yes: a run of the Hub started this process"), "the process that holds the lock is this one, and it is alive")
            code, out, _ = self.run_it(self.environment(**hubenv.proof_environment(folder, pid=hubenv.dead_pid())))
            self.assertEqual((code, out), (2, "no: this call was not started by a run of the Hub"))
            code, out, _ = self.run_it(self.environment(**hubenv.proof_environment(folder), **hubenv.RUNNER))
            self.assertEqual((code, out), (0, "yes: a run of the Hub started this process"), "a proof that is valid counts on a machine that is itself a runner")

    def test_the_main_function_tells_a_person_what_is_missing_and_anything_else_only_the_refusal(self):
        out = io.StringIO()
        self.assertEqual(hg.main(environ={}, out=out), 2)
        self.assertEqual(out.getvalue().strip(), "no: this call was not started by a run of the Hub")
        out = io.StringIO()
        self.assertEqual(hg.main(environ=hubenv.RUNNER, out=out), 2)
        self.assertEqual(out.getvalue().strip(), "no: this call was not started by a run of the Hub", "not a person: a runner's environment gets the refusal and nothing else")
        out = io.StringIO()
        self.assertEqual(hg.main(environ=hubenv.RUNNER, out=out, person=True), 2)
        self.assertTrue(out.getvalue().startswith("no: METERNAUT_HUB_PROOF is not set: only the proof file of a run of tools/hub-local.py counts."), out.getvalue())
        self.assertIn("GITHUB_ACTIONS=true and what else a GitHub runner sets are no proof", out.getvalue())
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
                for word in ("METERNAUT_HUB_PROOF", "GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN", "hub-proof"):
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
