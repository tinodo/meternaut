"""A candidate of the Investigator's instructions, replayed against a temporary agent and never against the production one: `--candidate` and `--effort` of tools/foundry-evals.py, the files of
evaluation/candidates/ and the Hub inputs evals_candidate and evals_effort (docs/proposals/11, "Trying a change of the instructions before it is made").

A fake of the Foundry project answers every call (tools/tests/test_aisec_tools.py): no model, no Foundry project and no Azure is called. The texts, the names and the numbers are invented, except the
first candidate of the repository, which is read as it is.
"""
import ast
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import test_aisec_tools as aisec
import test_aisec_workflow as flow

helpers, evals, redteam, ROOT, APP = aisec.helpers, aisec.evals, aisec.redteam, aisec.ROOT, aisec.APP
FOLDER = ROOT / "evaluation" / "candidates"
FIRST = "others-research"
ADDED = ("A smaller number of units is only one way to save on something that comes in tiers, sizes or numbers of units. Before you answer for one resource, and within your budget of calls, look for the "
         "others: read what the documentation was read to say about its other tiers or sizes, price each one that can be priced with the tool for alternatives, and state each in others "
         "with what it gives up and whether it can be altered in place. Say in examined when you looked and found none.")
PRODUCTION = "meternaut-investigator"
IDLE = "idle-disk-1"
NAME = re.compile(r"meternaut-candidate-[0-9]{12}-[0-9a-f]{4}")


class Staged(aisec.Project):
    """The project when a candidate is replayed: the agents that are made are kept under their names and a read or a delete of one is answered. `delete` is the status that a delete answers (and the agent
    stays when it is not 200), `make` is what the creation of an agent answers instead of making it, `lost` makes it and answers nothing, and `answer_with` is called instead of a response."""

    def __init__(self, lock, *, delete=200, delete_raises=False, make=None, lost=False, answer_with=None, **options):
        super().__init__(lock, **options)
        self.delete, self.delete_raises, self.make, self.lost, self.answer_with, self.references = delete, delete_raises, make, lost, answer_with, []

    def __call__(self, method, path, body):
        route = path.split("?")[0]
        if route.startswith("/agents/meternaut-candidate-"):
            name = route.split("/")[2]
            self.methods.append((method, route))
            if method == "DELETE":
                if self.delete_raises:
                    raise helpers.Problem("no token could be had for the project: the sign-in did not give one")
                if self.delete == 200:
                    self.agents.pop(name, None)
                return self.delete, {}
            return (200, {"name": name}) if name in self.agents else (404, None)
        if method == "POST" and route == "/agents" and (self.make is not None or self.lost):
            self.methods.append((method, route))
            if self.lost:
                self.agents[body["name"]] = body
                return 0, None
            return self.make
        if method == "POST" and route == "/openai/v1/responses":
            self.references.append(body["agent_reference"])
            if self.answer_with is not None:
                return self.answer_with()
        return super().__call__(method, path, body)


def go(project, *argv, spend=None, env=aisec.ACTIONS):
    client = aisec.evals_client(project)
    clock = aisec.FakeTime()
    code, out, err = aisec.run(evals.main, ["run", "--endpoint", aisec.ENDPOINT, *argv], env, client=client, spend=spend or helpers.Spend(aisec.LIMITS), sleep=clock.sleep, clock=clock)
    return code, out, err, client


@contextlib.contextmanager
def candidate_file(content, name="a-trial"):
    """A candidate of this name whose file holds `content` (text or bytes): the lookup of the tool is answered with that file."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"{name}.txt"
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        with mock.patch.object(evals, "find_candidate", lambda asked: path):
            yield name


def instructions_of(project):
    return project.production["versions"]["latest"]["definition"]["instructions"]


def made_by(client):
    return [body for method, path, body in client.log if method == "POST" and path.split("?")[0] == "/agents"]


def written_by(client):
    return [(method, path.split("?")[0], body) for method, path, body in client.log if method != "GET"]


def sha12(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def scanner():
    """`banned_in` of src/case-functions/tests/test_investigate.py, which holds the instructions of the agents to rule 30, taken from the file with its word lists: the same scan, and none of the app's tests."""
    path = APP / "tests" / "test_investigate.py"
    wanted = {"RESOURCE_WORDS", "MEASUREMENT_WORDS", "STATE_WORDS", "THRESHOLD_WORDS", "THRESHOLD_SHAPES", "banned_in"}
    nodes = [node for node in ast.parse(path.read_text(encoding="utf-8")).body
             if (isinstance(node, ast.FunctionDef) and node.name in wanted) or (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted)]
    found = {node.name if isinstance(node, ast.FunctionDef) else node.targets[0].id for node in nodes}
    assert found == wanted, f"the scan of the instructions is no longer where this test looks for it: {sorted(wanted - found)}"
    space = {"re": re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), space)
    return space["banned_in"]


def difference(before, after):
    """The one stretch in which two texts differ: where it starts, what the first has there and what the second has there."""
    start = len(os.path.commonprefix([before, after]))
    end = len(os.path.commonprefix([before[start:][::-1], after[start:][::-1]]))
    return start, before[start:len(before) - end], after[start:len(after) - end]


# -- the files -------------------------------------------------------------------------------------------------------------------------------------

class TheCandidateFiles(unittest.TestCase):
    PRODUCTION_TEXT = (ROOT / "evaluation" / "investigator-instructions.txt").read_text(encoding="utf-8")

    def test_the_folder_holds_files_that_the_name_of_a_candidate_reaches_and_no_other(self):
        names = sorted(path.name for path in FOLDER.iterdir())
        self.assertIn(f"{FIRST}.txt", names)
        for name in names:
            self.assertRegex(name, r"^[a-z0-9][a-z0-9-]{0,49}\.txt$", f"{name}: only a file that --candidate can name travels to the Operator")

    def test_every_candidate_is_text_that_the_tool_accepts_and_is_not_the_production_text(self):
        for path in FOLDER.iterdir():
            with self.subTest(candidate=path.stem):
                text = evals.read_candidate(path.stem)
                self.assertTrue(0 < len(text) <= 20_000)
                self.assertNotEqual(text.strip(), self.PRODUCTION_TEXT.strip(), "a candidate that is the production text compares nothing")

    def test_every_candidate_passes_the_scan_that_holds_the_instructions_to_rule_30_and_names_no_tool(self):
        banned_in = scanner()
        tools = sorted(evals.PARAMETERS)
        for path in FOLDER.iterdir():
            text = path.read_text(encoding="utf-8")
            with self.subTest(candidate=path.stem):
                self.assertEqual(banned_in(text), [], "it names no kind of resource, no measurement, no state and no threshold")
                for tool in tools:
                    self.assertNotRegex(text, rf"\b{re.escape(tool)}\b", "the instructions do not tell the agent which tool to use for what")

    def test_the_scan_has_teeth_and_lets_the_production_text_through(self):
        banned_in = scanner()
        self.assertEqual(banned_in(self.PRODUCTION_TEXT), [])
        self.assertIn("bastion", banned_in(self.PRODUCTION_TEXT + " Look at the bastion host."))
        self.assertIn("at least", banned_in(self.PRODUCTION_TEXT + " Keep it when it carries at least a little."))
        self.assertTrue(banned_in(self.PRODUCTION_TEXT + " Use 5% of it."))

    def test_the_first_candidate_is_the_production_text_with_one_paragraph_in_item_4_right_after_a_price_shows_neither(self):
        text = (FOLDER / f"{FIRST}.txt").read_text(encoding="utf-8")
        start, removed, added = difference(self.PRODUCTION_TEXT, text)
        self.assertEqual((removed, added), ("", ADDED + " "), "nothing is taken away, and what is added is the one paragraph")
        self.assertTrue(self.PRODUCTION_TEXT[:start].endswith("a price shows neither. "), "right after the sentence that ends there")
        self.assertTrue(self.PRODUCTION_TEXT[:start].rsplit("\n", 1)[-1].startswith("4. Waste is one of these"), "in item 4")
        self.assertEqual(text, self.PRODUCTION_TEXT[:start] + ADDED + " " + self.PRODUCTION_TEXT[start:])

    def test_the_difference_is_found_where_it_is_and_a_text_that_changed_elsewhere_is_not_the_first_candidate(self):
        self.assertEqual(difference("abc def", "abc XYZ def"), (4, "", "XYZ "))
        self.assertEqual(difference("abc def", "abc def"), (7, "", ""))
        self.assertEqual(difference("abc def", "abd def")[1:], ("c", "d"))
        start, removed, added = difference(self.PRODUCTION_TEXT, (FOLDER / f"{FIRST}.txt").read_text(encoding="utf-8").replace("Quiet resources", "Quiet things"))
        self.assertNotEqual((removed, added), ("", ADDED + " "), "an accidental change elsewhere is seen")


# -- the tool --------------------------------------------------------------------------------------------------------------------------------------

class TheCandidateReplay(unittest.TestCase):
    def setUp(self):
        self.lock = aisec.lockfile.load(APP / "cases" / "agents.lock.json")

    def project(self, **options):
        return Staged(self.lock, only=[IDLE], **options)

    def test_a_replay_with_no_candidate_makes_no_agent_and_says_what_it_always_said(self):
        project = self.project()
        code, out, err, client = go(project, "--only", IDLE)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual([(m, r) for m, r, _ in written_by(client) if r.startswith("/agents")], [], "no agent is made or deleted")
        self.assertIn("against version 7 of the Investigator; judge none", out)
        self.assertNotIn("candidate", out)
        self.assertEqual({reference["name"] for reference in project.references}, {PRODUCTION})
        self.assertTrue(project.evals[0]["name"].startswith("meternaut-investigator-safety-"))

    def test_a_candidate_is_a_temporary_agent_with_the_production_definition_and_the_instructions_of_the_file_and_is_deleted_at_the_end(self):
        project = self.project(agent_changes={"temperature": 1.0, "top_p": 1.0})
        production = project.production["versions"]["latest"]["definition"]
        text = instructions_of(project) + " One more sentence of the candidate."
        with candidate_file(text) as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        self.assertEqual((code, err), (0, ""), out)
        agents = made_by(client)
        self.assertEqual(len(agents), 1)
        agent = agents[0]
        self.assertRegex(agent["name"], NAME)
        self.assertNotEqual(agent["name"], PRODUCTION)
        definition = agent["definition"]
        self.assertEqual(definition["instructions"], text)
        for key in ("kind", "model", "tools"):
            self.assertEqual(definition[key], production[key], f"{key}: the same as the production agent's")
        self.assertEqual(set(definition), {"kind", "model", "instructions", "tools"}, "what the lock pins, and not the defaults that the service added")
        self.assertTrue(definition["tools"] and all(tool["type"] == "function" for tool in definition["tools"]), "the function tools of the production agent")
        self.assertTrue(all(isinstance(value, str) for value in agent["metadata"].values()))
        self.assertLessEqual(len(agent["description"]), 512)
        self.assertEqual(project.agents, {}, "the agent was deleted")
        self.assertEqual(project.references, [{"type": "agent_reference", "name": agent["name"], "version": "1"}] * 2, "both responses of the row are the candidate's")
        self.assertIn(f"candidate: made the temporary agent {agent['name']} (version 1)", out)
        self.assertIn(f"candidate: the temporary agent {agent['name']} was deleted and is gone", out)
        self.assertEqual(project.conversations, set())

    def test_the_replay_is_graded_and_counted_exactly_as_the_production_one(self):
        production_project, production_spend = self.project(), helpers.Spend(aisec.LIMITS)
        code, production_out, _, _ = go(production_project, "--only", IDLE, spend=production_spend)
        project, spend = self.project(), helpers.Spend(aisec.LIMITS)
        with candidate_file(instructions_of(project) + " More.") as name:
            code, out, _, _ = go(project, "--only", IDLE, "--candidate", name, spend=spend)
        self.assertEqual(code, 0, out)
        self.assertEqual((spend.rows, spend.model_calls, spend.tokens), (production_spend.rows, production_spend.model_calls, production_spend.tokens))
        grades = [line for line in out.splitlines() if line.startswith(("PASS", "FAIL", "UNKNOWN"))]
        self.assertEqual(grades, [line for line in production_out.splitlines() if line.startswith(("PASS", "FAIL", "UNKNOWN"))], "the same thresholds, the same words")
        self.assertTrue(project.evals[0]["name"].startswith("meternaut-candidate-a-trial-safety-"), "a person who reads Build, Evaluations can tell it from a run of the production agent")

    def test_the_effort_alone_makes_a_candidate_with_the_production_instructions_named_for_the_effort(self):
        for effort in ("low", "medium", "high"):
            with self.subTest(effort=effort):
                project = self.project()
                code, out, err, client = go(project, "--only", IDLE, "--effort", effort)
                self.assertEqual((code, err), (0, ""), out)
                definition = made_by(client)[0]["definition"]
                self.assertEqual(definition["reasoning"], {"effort": effort})
                self.assertEqual(definition["instructions"], instructions_of(project), "the instructions are the production ones")
                self.assertEqual(project.agents, {})
                self.assertRegex(out.splitlines()[0], rf"^run: candidate effort-{effort} \(")
                self.assertIn(f"against candidate effort-{effort}; judge none", out)

    def test_the_effort_and_a_file_together_and_an_effort_that_keeps_what_else_the_production_reasoning_holds(self):
        project = self.project(agent_changes={"reasoning": {"summary": "auto"}})
        with candidate_file(instructions_of(project) + " More.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name, "--effort", "low")
        self.assertEqual((code, err), (0, ""), out)
        definition = made_by(client)[0]["definition"]
        self.assertEqual(definition["reasoning"], {"summary": "auto", "effort": "low"})
        self.assertTrue(definition["instructions"].endswith(" More."))
        self.assertIn("against candidate a-trial; judge none", out)
        self.assertEqual(project.production["versions"]["latest"]["definition"]["reasoning"], {"summary": "auto"}, "the production definition is not changed in place")

    def test_a_candidate_without_an_effort_leaves_the_reasoning_of_the_production_agent_as_it_is(self):
        project = self.project(agent_changes={"reasoning": {"summary": "auto"}})
        with candidate_file(instructions_of(project) + " More.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        self.assertEqual(made_by(client)[0]["definition"]["reasoning"], {"summary": "auto"})

    def test_the_production_agent_is_never_written_whatever_is_asked(self):
        for label, asked in (("file", lambda name: ["--candidate", name]), ("effort", lambda name: ["--effort", "high"]), ("both", lambda name: ["--candidate", name, "--effort", "low"])):
            with self.subTest(asked=label):
                project = self.project()
                with candidate_file(instructions_of(project) + " More.") as name:
                    code, out, err, client = go(project, "--only", IDLE, *asked(name))
                self.assertEqual(code, 0, out + err)
                temporary = made_by(client)[0]["name"]
                for method, route, body in written_by(client):
                    if route.startswith("/agents"):
                        self.assertIn((method, route), (("POST", "/agents"), ("DELETE", f"/agents/{temporary}")), "a write of an agent goes to the name of the temporary agent")
                    if route == "/openai/v1/responses":
                        self.assertEqual(body["agent_reference"]["name"], temporary)
                    self.assertNotIn(PRODUCTION, json.dumps([route, body]), f"{method} {route}: nothing that the tool writes carries the name of the production agent")
                self.assertEqual({reference["name"] for reference in project.references}, {temporary})

    def test_the_stored_investigator_must_still_be_the_locked_one_and_a_candidate_does_not_change_that(self):
        project = self.project(agent_changes={"model": "gpt-5.5"})
        with candidate_file("Another text.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        self.assertEqual(code, 1)
        self.assertIn("is not what the lock says", err)
        self.assertEqual(written_by(client), [], "nothing was sent: no agent, no conversation, no response")

    # -- what is deleted, and when -----------------------------------------------------------------------------------------------------------------

    def test_the_temporary_agent_is_deleted_after_a_replay_that_fails_and_the_error_is_still_said(self):
        project = self.project(answer_with=lambda: (500, {"error": {"code": "server_error"}}))
        with candidate_file("A text.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        self.assertEqual(code, 1)
        self.assertIn("a response of the agent could not be had (500 server_error)", err)
        self.assertEqual((project.agents, project.conversations), ({}, set()))
        self.assertIn("was deleted and is gone", out)

    def test_the_temporary_agent_is_deleted_when_the_spend_cap_stops_the_replay(self):
        project = self.project()
        with candidate_file("A text.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name, spend=helpers.Spend({**aisec.LIMITS, "maxModelCalls": 1}))
        self.assertEqual(code, 1)
        self.assertIn("STOPPED the spend cap holds", out)
        self.assertEqual((project.agents, project.conversations), ({}, set()))
        self.assertIn("was deleted and is gone", out)

    def test_the_temporary_agent_is_deleted_when_the_run_is_interrupted(self):
        def interrupt():
            raise KeyboardInterrupt

        project = self.project(answer_with=interrupt)
        client, clock, out = aisec.evals_client(project), aisec.FakeTime(), io.StringIO()
        with candidate_file("A text.") as name, contextlib.redirect_stdout(out), mock.patch.dict(os.environ, aisec.ACTIONS), self.assertRaises(KeyboardInterrupt):
            evals.main(["run", "--endpoint", aisec.ENDPOINT, "--only", IDLE, "--candidate", name], client=client, spend=helpers.Spend(aisec.LIMITS), sleep=clock.sleep, clock=clock)
        self.assertEqual((project.agents, project.conversations), ({}, set()))
        self.assertIn("was deleted and is gone", out.getvalue())

    def test_a_temporary_agent_that_cannot_be_deleted_is_said_with_its_name_the_result_is_not_hidden_and_the_run_fails(self):
        project = self.project(delete=403)
        with candidate_file("A text.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        (left,) = project.agents
        self.assertRegex(left, NAME)
        self.assertEqual(code, 1, "a person has to delete it")
        self.assertIn(f"candidate: the temporary agent {left} was NOT deleted: delete it by hand in the portal under Build, Agents", out)
        self.assertRegex(out, r"(?m)^PASS groundedRate ", "what the replay found is printed all the same")
        self.assertRegex(out, rf"(?m)^WARNING the temporary agent {left} is still in the project: delete it by hand")
        self.assertLess(out.index("was NOT deleted"), out.index("WARNING the temporary agent"), "it is said when the block ends and again at the end of the result, where a person reads")
        self.assertGreater(out.index("WARNING the temporary agent"), out.index("PASS groundedRate "))

    def test_a_delete_that_cannot_even_be_asked_for_is_said_as_not_deleted_and_hides_nothing(self):
        project = self.project(delete_raises=True)
        with candidate_file("A text.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        (left,) = project.agents
        self.assertEqual((code, err), (1, ""), "the sign-in that failed at the end does not stop the report")
        self.assertIn(f"candidate: the temporary agent {left} was NOT deleted: delete it by hand in the portal under Build, Agents", out)
        self.assertRegex(out, r"(?m)^PASS groundedRate ")
        self.assertRegex(out, rf"(?m)^WARNING the temporary agent {left} is still in the project")

    def together(self, project, *argv):
        """The whole text of a run, standard output and standard error in one stream as the log of the Operator has them, and what main returned ('interrupted' for a run that was stopped by hand, 'raised' for one
        that an unexpected error ended)."""
        client, clock, text = aisec.evals_client(project), aisec.FakeTime(), io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(text), mock.patch.dict(os.environ, aisec.ACTIONS):
            try:
                code = evals.main(["run", "--endpoint", aisec.ENDPOINT, "--only", IDLE, *argv], client=client, spend=helpers.Spend(aisec.LIMITS), sleep=clock.sleep, clock=clock)
            except KeyboardInterrupt:
                code = "interrupted"
            except RuntimeError:
                code = "raised"
        return code, [line for line in text.getvalue().splitlines() if line.strip()]

    def test_the_last_line_of_every_run_that_leaves_an_agent_behind_is_the_warning_that_names_it_the_paths_of_an_error_too(self):
        def fails():
            return 500, {"error": {"code": "server_error"}}

        def interrupts():
            raise KeyboardInterrupt

        def raises():
            raise RuntimeError("an error that nobody expected")

        for label, options, expected in (("the replay ends", {}, 1), ("the replay fails", {"answer_with": fails}, 1), ("the run is stopped by hand", {"answer_with": interrupts}, "interrupted"),
                                         ("the replay raises an error", {"answer_with": raises}, "raised"), ("the answer to the creation is lost", {"lost": True}, 1)):
            with self.subTest(path=label):
                project = self.project(delete=403, **options)
                with candidate_file("A text.") as name:
                    code, lines = self.together(project, "--candidate", name)
                (left,) = project.agents
                self.assertEqual(code, expected)
                self.assertEqual(lines[-1], f"WARNING the temporary agent {left} is still in the project: delete it by hand in the portal under Build, Agents")
                self.assertEqual(sum(line.startswith("WARNING") for line in lines), 1, "once, and nothing comes after it")
                self.assertEqual(sum(f"candidate: the temporary agent {left} was NOT deleted" in line for line in lines), 1, "it is said when the block ends, and the warning says it again at the end")
                if label == "the replay fails":
                    self.assertTrue(any(line.startswith("error: a response of the agent could not be had (500 server_error)") for line in lines[:-1]), "the error comes first and the warning after it")

    def test_a_run_that_deleted_its_agent_ends_with_no_warning_and_a_second_run_does_not_repeat_the_warning_of_the_first(self):
        with candidate_file("A text.") as name:
            code, lines = self.together(self.project(delete=403), "--candidate", name)
            self.assertTrue(lines[-1].startswith("WARNING"))
            code, lines = self.together(self.project(), "--candidate", name)
        self.assertEqual(code, 0)
        self.assertFalse(any(line.startswith("WARNING") for line in lines), "the agent that the first run left is not the second run's")
        self.assertTrue(lines[-1].startswith("run: ") and "calls to the project in all" in lines[-1])

    def test_an_agent_that_was_made_when_the_answer_was_lost_is_deleted_too_and_a_refusal_leaves_nothing_to_delete(self):
        project = self.project(lost=True)
        with candidate_file("A text.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        self.assertEqual(code, 1)
        self.assertIn("the temporary agent could not be made (0 )", err)
        self.assertEqual(project.agents, {}, "the creation was answered with nothing and the agent was there: it is deleted")
        self.assertNotIn("NOT deleted", out)
        self.assertEqual(project.references, [], "no response was asked of an agent that was not made")
        refusing = self.project(make=(403, {"error": {"code": "AuthorizationFailed"}}))
        with candidate_file("A text.") as name:
            code, out, err, client = go(refusing, "--only", IDLE, "--candidate", name)
        self.assertEqual(code, 1)
        self.assertIn("the temporary agent could not be made (403 AuthorizationFailed)", err)
        self.assertNotIn("temporary agent meternaut", out, "nothing is said of an agent that was never made")
        self.assertEqual((refusing.agents, refusing.references), ({}, []))

    # -- what is refused before any call is made to a model ----------------------------------------------------------------------------------------

    def refused(self, *argv, fragment, calls=0):
        project = self.project()
        code, out, err, client = go(project, "--only", IDLE, *argv)
        self.assertEqual(code, 2, (argv, out, err))
        self.assertIn(fragment, err, argv)
        self.assertEqual(len(client.calls), calls, f"{argv}: the calls that were made")
        self.assertEqual((written_by(client), project.references), ([], []), "nothing was written and no model was called")
        self.assertEqual(out, "")

    def test_a_name_that_is_not_the_name_of_a_candidate_is_refused_before_any_call(self):
        for bad in ("", "-x", "--judge", "A", "Others", "a_b", "a.b", "a/b", "a\\b", "a b", "a,b", "a;b", "$(id)", "a" * 51, "\u043ethers", "\uff41bc", "a\u2010b", "k\u212a", "a\nb", "\u0131x"):
            with self.subTest(name=bad):
                self.refused(f"--candidate={bad}", fragment="--candidate names a file of evaluation/candidates")

    def test_the_longest_name_and_the_shortest_are_accepted_by_the_pattern_and_then_found_missing(self):
        for good in ("a", "0", "a-", "others-research-2", "a" * 50):
            with self.subTest(name=good):
                self.refused("--candidate", good, fragment=f"there is no candidate {good}")

    def test_a_name_of_51_characters_is_refused_in_plain_words_that_give_the_limit_and_one_of_50_is_taken_as_far_as_the_file(self):
        self.refused("--candidate", "a" * 51, fragment="lower-case letters, digits and hyphens, starting with a letter or a digit, at most 50 characters")
        self.refused("--candidate", "a" * 50, fragment=f"there is no candidate {'a' * 50}")

    def test_a_file_that_is_not_there_is_refused_before_any_call_and_the_name_of_a_file_of_another_folder_cannot_be_given(self):
        self.refused("--candidate", "no-such-candidate", fragment="there is no candidate no-such-candidate")
        self.refused("--candidate", "../investigator-instructions", fragment="--candidate names a file of evaluation/candidates")

    def test_a_file_that_is_empty_too_long_or_not_text_is_refused_before_any_call(self):
        for label, content, fragment in (("empty", b"", "is empty"), ("white space", b" \n\t\r\n", "is empty"), ("too long", b"a " * 10_001, "is longer than 20000 characters"),
                                         ("one more than the limit", b"a" * 20_001, "is longer than 20000 characters"),
                                         ("not UTF-8", b"caf\xe9 is latin-1", "is not UTF-8 text"), ("a lone byte", b"\xff\xfe", "is not UTF-8 text"),
                                         ("a NUL", b"text\x00more", "holds a character that is not plain text"), ("a byte order mark", "\ufeffhello".encode("utf-8"), "holds a character that is not plain text"),
                                         ("a zero width space", "he\u200bllo".encode("utf-8"), "holds a character that is not plain text"),
                                         ("a right-to-left override", "he\u202ello".encode("utf-8"), "holds a character that is not plain text"),
                                         ("a bell", b"he\x07llo", "holds a character that is not plain text")):
            with self.subTest(file=label), candidate_file(content) as name:
                self.refused("--candidate", name, fragment=fragment)

    def test_text_of_exactly_20000_characters_with_tabs_new_lines_and_letters_of_other_languages_is_accepted(self):
        for text in ("a" * 20_000, "line one\n\tline two\r\nline three \u00e9\u00fc \u2014 \u65e5\u672c"):
            with self.subTest(length=len(text)), candidate_file(text) as name:
                project = self.project()
                code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(made_by(client)[0]["definition"]["instructions"], text.replace("\r\n", "\n"))

    def test_the_production_instructions_are_refused_as_a_candidate_because_there_is_nothing_to_compare_and_so_are_they_with_white_space_at_the_ends(self):
        project = self.project()
        production = instructions_of(project)
        for label, text in (("as they are", production), ("with a new line at the end", production + "\n"), ("with windows line ends", production.replace("\n", "\r\n")), ("with spaces round them", f"  {production} \n")):
            with self.subTest(text=label), candidate_file(text) as name:
                project = self.project()
                code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
                self.assertEqual(code, 2)
                self.assertIn("holds the production instructions: there is nothing to compare", err)
                self.assertEqual((written_by(client), project.references, out), ([], [], ""), "only the production agent was read")
        with candidate_file(production) as name:
            project = self.project()
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name, "--effort", "high")
            self.assertEqual(code, 0, out + err)
            self.assertIn("reasoning effort high", out.splitlines()[0], "with an effort there is something to compare")

    def test_a_candidate_and_an_effort_go_with_the_command_run_alone(self):
        for command in ("probe", "rule"):
            for extra in (["--candidate", FIRST], ["--effort", "high"], ["--candidate", FIRST, "--effort", "low"], ["--candidate="]):
                with self.subTest(command=command, extra=extra):
                    project = self.project()
                    client = aisec.evals_client(project)
                    code, out, err = aisec.run(evals.main, [command, "--endpoint", aisec.ENDPOINT, *extra], aisec.ACTIONS, client=client)
                    self.assertEqual((code, client.calls, out), (2, [], ""))
                    self.assertIn("--candidate and --effort go with the command run alone", err)

    def test_an_effort_that_is_not_low_medium_or_high_is_refused_by_the_parser_before_any_call(self):
        for bad in ("none", "extreme", "LOW", "", "low,high"):
            with self.subTest(effort=bad), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                evals.main(["run", "--endpoint", aisec.ENDPOINT, "--effort", bad], client=aisec.evals_client(self.project()))

    # -- the words at the top and at the end --------------------------------------------------------------------------------------------------------

    def test_the_top_of_the_result_says_which_candidate_with_the_hash_and_the_length_of_its_instructions_and_which_baseline(self):
        project = self.project()
        text = instructions_of(project) + " One more sentence of the candidate."
        with candidate_file(text) as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        lines = out.splitlines()
        self.assertEqual(lines[0], f"run: candidate a-trial (instructions sha256 {sha12(text)}, {len(text)} characters) against baseline version 7")
        self.assertRegex(lines[1], r"^candidate: made the temporary agent meternaut-candidate-", "the label comes before anything that is made")
        self.assertIn(f"fixtures replayed (only: {IDLE}) against candidate a-trial; judge none", out)
        self.assertNotIn("against version", out)
        self.assertNotIn("of the Investigator", out)

    def test_the_label_names_the_effort_and_says_when_the_instructions_are_the_production_ones(self):
        project = self.project()
        with candidate_file(instructions_of(project) + " More.") as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name, "--effort", "medium")
        self.assertRegex(out.splitlines()[0], r"^run: candidate a-trial \(instructions sha256 [0-9a-f]{12}, \d+ characters, reasoning effort medium\) against baseline version 7$")
        code, out, err, client = go(self.project(), "--only", IDLE, "--effort", "high")
        production = instructions_of(self.project())
        self.assertEqual(out.splitlines()[0], f"run: candidate effort-high (instructions sha256 {sha12(production)}, {len(production)} characters, the production text, reasoning effort high) against baseline version 7")

    def test_a_label_is_one_line_of_plain_words_for_a_name_of_any_length_that_is_allowed(self):
        project = self.project()
        with candidate_file(instructions_of(project) + " More.", name="a" * 50) as name:
            code, out, err, client = go(project, "--only", IDLE, "--candidate", name)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.splitlines()[0].count("\n"), 0)
        self.assertLessEqual(len(out.splitlines()[0]), 220, "helpers.say cuts a longer line")
        self.assertTrue(project.evals[0]["name"].startswith("meternaut-candidate-" + "a" * 30 + "-safety-"), "the name of an evaluation is short enough for the project")

    def test_the_lookup_takes_the_file_that_travelled_with_the_tool_before_the_file_of_the_repository(self):
        with tempfile.TemporaryDirectory() as volume, tempfile.TemporaryDirectory() as repository:
            (Path(repository) / "candidates").mkdir()
            (Path(volume) / "candidate-a-trial.txt").write_text("from the volume", encoding="utf-8")
            (Path(repository) / "candidates" / "a-trial.txt").write_text("from the repository", encoding="utf-8")
            (Path(repository) / "candidates" / "only-here.txt").write_text("only in the repository", encoding="utf-8")
            with mock.patch.object(helpers, "HERE", Path(volume)), mock.patch.object(helpers, "EVALUATION", Path(repository)):
                self.assertEqual(evals.read_candidate("a-trial"), "from the volume")
                self.assertEqual(evals.read_candidate("only-here"), "only in the repository")
                with self.assertRaises(helpers.Problem):
                    evals.read_candidate("neither")


# -- what the tools share ----------------------------------------------------------------------------------------------------------------------------

class TheTemporaryAgentsOfTheTools(unittest.TestCase):
    def test_only_a_name_that_starts_with_a_temporary_prefix_and_is_plain_is_ever_made_or_deleted(self):
        class Silent:
            log = []

            def request(self, *arguments, **options):
                self.log.append(arguments)
                return 404, None

        client = Silent()
        for bad in (PRODUCTION, "meternaut-skeptic", "meternaut-scholar", "other", "", "meternaut-candidate-", "meternaut-candidate-x/../meternaut-investigator", "meternaut-candidate-X",
                    "meternaut-redteam-copy-" + "a" * 50, "meternaut-candidate-a b", "meternaut-candidate-a-", None, 7):
            with self.subTest(name=bad):
                self.assertFalse(helpers.delete_agent(client, bad), "it deletes nothing")
                with self.assertRaises(helpers.Problem):
                    helpers.make_agent(client, bad, {"kind": "prompt"}, "x", {})
        self.assertEqual(client.log, [], "the name is checked before any call")
        self.assertTrue(helpers.delete_agent(client, "meternaut-candidate-202611211433-ab12"))
        self.assertEqual(client.log, [("DELETE", "/agents/meternaut-candidate-202611211433-ab12?api-version=v1"), ("GET", "/agents/meternaut-candidate-202611211433-ab12?api-version=v1")])

    def test_a_temporary_name_says_what_it_is_the_minute_and_a_token_that_does_not_repeat(self):
        import datetime as dt

        now = dt.datetime(2026, 11, 21, 14, 33, tzinfo=dt.timezone.utc)
        self.assertEqual(helpers.temporary_name("meternaut-candidate-", now, "ab12"), "meternaut-candidate-202611211433-ab12")
        names = {helpers.temporary_name("meternaut-candidate-", now) for _ in range(40)}
        self.assertGreater(len(names), 30, "a token of its own for each")
        for name in names:
            self.assertRegex(name, NAME)

    def test_the_two_prefixes_are_the_ones_that_the_tools_use_and_no_prefix_is_the_start_of_another(self):
        self.assertEqual(set(helpers.TEMPORARY), {redteam.COPY_PREFIX, evals.CANDIDATE_PREFIX})
        for prefix in helpers.TEMPORARY:
            self.assertFalse(PRODUCTION.startswith(prefix) or prefix.startswith(PRODUCTION))
        self.assertFalse(redteam.COPY_PREFIX.startswith(evals.CANDIDATE_PREFIX) or evals.CANDIDATE_PREFIX.startswith(redteam.COPY_PREFIX))

    def test_the_red_team_makes_and_deletes_its_copy_with_the_same_code_and_keeps_its_own_rules(self):
        import datetime as dt

        self.assertEqual(redteam.copy_name(dt.datetime(2026, 11, 21, 14, 33, tzinfo=dt.timezone.utc), "ab12"), "meternaut-redteam-copy-202611211433-ab12")
        project = Staged(aisec.lockfile.load(APP / "cases" / "agents.lock.json"))
        client = aisec.evals_client(project)
        with self.assertRaises(helpers.Problem):
            redteam.make_copy(client, "meternaut-candidate-202611211433-ab12", {"kind": "prompt", "model": "m", "instructions": "x"})
        with self.assertRaises(helpers.Problem):
            redteam.make_copy(client, "meternaut-redteam-copy-x", {"kind": "prompt", "model": "m", "instructions": "x", "tools": []})
        self.assertFalse(redteam.delete_copy(client, "meternaut-candidate-202611211433-ab12"), "the red team deletes its own copies alone")
        self.assertEqual(client.log, [])
        self.assertEqual(redteam.make_copy(client, "meternaut-redteam-copy-202611211433-ab12", {"kind": "prompt", "model": "m", "instructions": "x"}), "1")
        self.assertTrue(redteam.delete_copy(client, "meternaut-redteam-copy-202611211433-ab12"))


# -- the Hub -----------------------------------------------------------------------------------------------------------------------------------------

def started(**changes):
    """The step that runs the evaluations, run with bash against a stand-in for python3: its return, and the arguments that it gave to tools/operator-run.py."""
    done, lines, _ = flow.run_script(flow.EVALS, {"python3": flow.PYTHON}, {**flow.ENV, "EVALS_COMMAND": "run", "EVALS_JUDGE": "none", **changes})
    return done, [line[len("arg:"):] for line in lines if line.startswith("arg:")]


@unittest.skipUnless(flow.PASTED and flow.BASH, "the steps of the AI security are not in the workflow, or there is no bash on this machine")
class TheHubInputsOfACandidate(unittest.TestCase):
    TAIL = f"--endpoint {flow.ENDPOINT} --judge none --wait-seconds 900"
    NAME_MESSAGE = ("::error::The input evals_candidate is the name of a file of evaluation/candidates, without .txt: lower-case letters, digits and hyphens, starting with a letter or a digit, "
                    "at most 50 characters. Nothing was changed.")

    def block(self, name):
        return re.search(rf"(?ms)^      {name}:\n(.*?)(?=^      \w|^\w)", flow.WORKFLOW).group(1)

    def test_evals_candidate_is_an_optional_string_for_the_command_run_and_every_other_action_ignores_it(self):
        block = self.block("evals_candidate")
        for line in ("        type: string\n", "        required: false\n", '        default: ""\n'):
            self.assertIn(line, block)
        self.assertNotIn("options:", block, "the name is free text, so the step checks it")
        for words in ("Only with foundry-evals and evals_command run", "evaluation/candidates/NAME.txt", "lower-case letters, digits and hyphens", "at most 50 characters", "a temporary agent",
                      "deletes it at the end, whatever happened", "never written", "nothing is promoted", "Empty replays the production Investigator", "Every other action ignores it."):
            self.assertIn(words, block)
        self.assertIn("EVALS_CANDIDATE: ${{ inputs.evals_candidate }}", flow.step(flow.EVALS), "the value reaches the script through the environment, never through an expression in the script")
        self.assertEqual(flow.WORKFLOW.count("inputs.evals_candidate"), 1)

    def test_the_description_says_that_a_candidate_run_is_never_the_test_of_a_release_which_runs_with_this_input_empty(self):
        block = self.block("evals_candidate")
        for words in ("A candidate run is never the test of a release", "rule 40", "runs this action with this input empty", "exits 0 with the same PASS lines"):
            self.assertIn(words, block)
        self.assertLess(block.index("A candidate run is never the test of a release"), block.index("Empty replays the production Investigator"))

    def test_evals_effort_is_a_choice_with_the_safe_default_and_every_other_action_ignores_it(self):
        block = self.block("evals_effort")
        for line in ("        type: choice\n", "        required: false\n", "        default: none\n"):
            self.assertIn(line, block)
        self.assertEqual(re.findall(r"^          - (\S+)$", block, re.M), ["none", "low", "medium", "high"])
        for words in ("Only with foundry-evals and evals_command run", "reasoning effort", "temporary", "never changes the production Investigator", "Every other action ignores it."):
            self.assertIn(words, block)
        self.assertIn("EVALS_EFFORT: ${{ inputs.evals_effort }}", flow.step(flow.EVALS))
        self.assertEqual(flow.WORKFLOW.count("inputs.evals_effort"), 1)

    def test_the_two_inputs_follow_evals_only_and_come_before_the_red_team(self):
        inputs = re.findall(r"^      ([a-z_]+):$", flow.WORKFLOW[flow.WORKFLOW.index("    inputs:\n"):flow.WORKFLOW.index("\npermissions:\n")], re.M)
        self.assertEqual(inputs[inputs.index("evals_only"):inputs.index("evals_only") + 3], ["evals_only", "evals_candidate", "evals_effort"])
        self.assertLess(inputs.index("evals_effort"), inputs.index("redteam_mode"))

    def test_a_replay_with_no_candidate_is_started_as_it_was_and_carries_no_file_of_the_candidates(self):
        done, args = started()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(next(a for a in args if a.startswith("TOOL_ARGS=")), f"TOOL_ARGS=run {self.TAIL}")
        parsed = flow.operator_run().build_parser().parse_args(args[1:])
        self.assertEqual([pair for pair in parsed.secret_file if "candidate" in pair], [])

    def test_a_candidate_reaches_the_tool_as_an_argument_and_its_one_file_travels_in_the_request(self):
        done, args = started(EVALS_CANDIDATE=FIRST)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(next(a for a in args if a.startswith("TOOL_ARGS=")), f"TOOL_ARGS=run {self.TAIL} --candidate {FIRST}")
        parsed = flow.operator_run().build_parser().parse_args(args[1:])
        self.assertEqual([pair for pair in parsed.secret_file if "candidate" in pair], [f"candidate-{FIRST}.txt=evaluation/candidates/{FIRST}.txt"], "only that file, and under the name that the tool looks for")
        self.assertRegex(next(a for a in args if a.startswith("TOOL_ARGS=")), r"^TOOL_ARGS=[A-Za-z0-9 ./:_=-]{1,600}$")

    def test_the_candidate_and_the_effort_come_before_the_ids_of_the_cases_so_that_the_ids_stay_last(self):
        done, args = started(EVALS_CANDIDATE=FIRST, EVALS_EFFORT="high", EVALS_ONLY="idle-disk-1,idle-addresses")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(next(a for a in args if a.startswith("TOOL_ARGS=")), f"TOOL_ARGS=run {self.TAIL} --candidate {FIRST} --effort high --only idle-disk-1 idle-addresses")

    def test_the_tool_reads_the_arguments_that_the_step_gives_it_and_replays_the_two_cases_against_the_first_candidate(self):
        done, args = started(EVALS_CANDIDATE=FIRST, EVALS_EFFORT="high", EVALS_ONLY="idle-disk-1,idle-addresses")
        words = next(a for a in args if a.startswith("TOOL_ARGS="))[len("TOOL_ARGS="):].split(" ")
        project = Staged(aisec.lockfile.load(APP / "cases" / "agents.lock.json"), only=["idle-disk-1", "idle-addresses"])
        client, clock = aisec.evals_client(project), aisec.FakeTime()
        code, out, err = aisec.run(evals.main, words, aisec.ACTIONS, client=client, spend=helpers.Spend(aisec.LIMITS), sleep=clock.sleep, clock=clock)
        self.assertEqual((code, err), (0, ""), out)
        (agent,) = made_by(client)
        self.assertEqual(agent["definition"]["instructions"], (FOLDER / f"{FIRST}.txt").read_text(encoding="utf-8"))
        self.assertEqual(agent["definition"]["reasoning"], {"effort": "high"})
        self.assertEqual(project.agents, {})
        self.assertIn("run: 2 of ", out)
        self.assertIn(f"against candidate {FIRST}; judge none", out)

    def test_the_effort_reaches_the_tool_and_the_effort_none_is_no_option_at_all(self):
        for effort, tail in (("", ""), ("none", ""), ("low", " --effort low"), ("medium", " --effort medium"), ("high", " --effort high")):
            with self.subTest(effort=effort):
                done, args = started(EVALS_EFFORT=effort)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(next(a for a in args if a.startswith("TOOL_ARGS=")), f"TOOL_ARGS=run {self.TAIL}{tail}")
                parsed = flow.operator_run().build_parser().parse_args(args[1:])
                self.assertEqual([pair for pair in parsed.secret_file if "candidate" in pair], [], "an effort alone sends no file")

    def test_a_name_that_is_not_the_name_of_a_candidate_is_refused_before_anything_is_started_and_is_never_printed_back(self):
        sneaky = ("-x", "--judge", "--judge,connection", "a,b", "a/b", "a\\b", "a.b", "../x", "a b", "$(id)", "`id`", "a;b", "A", "Others-research", "a_b", "a" * 51, "\u043ethers-research",
                  "others\u2010research", "\uff41bc", "k\u212a", "\u0131x", "a\nb", "a\n::add-mask::x", "x\r", "-", "--", "a--judge ")
        for bad in sneaky:
            with self.subTest(name=bad):
                done, args = started(EVALS_CANDIDATE=bad)
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn(self.NAME_MESSAGE, done.stdout)
                self.assertEqual(args, [], "nothing was started")
                self.assertNotIn("::add-mask::x", done.stdout.replace(self.NAME_MESSAGE, ""), "a value is never printed back")

    def test_a_name_that_the_pattern_allows_but_that_has_no_file_in_this_commit_is_refused_with_its_own_words(self):
        for good in ("a", "0a", "a-", "others-research-2", "a" * 50):
            with self.subTest(name=good):
                done, args = started(EVALS_CANDIDATE=good)
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn(f"::error::There is no file evaluation/candidates/{good}.txt in this commit. Nothing was changed.", done.stdout)
                self.assertEqual(args, [])

    def test_the_longest_name_gives_a_file_name_that_operator_run_takes_and_one_more_character_is_what_it_refuses(self):
        tool = flow.operator_run()
        done, args = started(EVALS_CANDIDATE=FIRST)
        parsed = tool.build_parser().parse_args(args[1:])
        pair = next(p for p in parsed.secret_file if p.startswith(f"candidate-{FIRST}.txt="))
        path = pair.split("=", 1)[1]
        for length, taken in ((50, True), (51, False)):
            name = f"candidate-{'a' * length}.txt"
            parsed.secret_file = [f"{name}={path}" if p == pair else p for p in parsed.secret_file]
            pair = f"{name}={path}"
            with self.subTest(length=length):
                if taken:
                    self.assertIn(name, tool.read_files(parsed), "a name of the longest length that the step lets through is a file name that the request takes")
                else:
                    with self.assertRaises(tool.Problem):
                        tool.read_files(parsed)

    def test_the_limit_of_the_name_is_the_same_in_the_step_the_tool_and_the_check_of_the_file_name_of_operator_run(self):
        tool = flow.operator_run()
        longest = int(re.search(r"\{0,(\d+)\}", tool.FILE_NAME.pattern).group(1)) + 1 - len("candidate-") - len(".txt")
        in_the_step = int(re.search(r"\{0,(\d+)\}\$ \]\]", flow.step(flow.EVALS)).group(1)) + 1
        in_the_tool = int(re.search(r"\{0,(\d+)\}", evals.CANDIDATE_NAME.pattern).group(1)) + 1
        self.assertEqual((in_the_step, in_the_tool, 50), (longest, longest, longest), "the name, with candidate- before it and .txt after it, fits the longest name of a file that operator-run takes")

    def test_the_notes_of_the_summary_say_what_is_true_of_a_candidate_run_and_the_note_of_a_failure_keeps_the_words_of_main(self):
        failed, ended = re.findall(r'(?m)^ +foundry-evals\) echo "(.*)" ;;$', flow.WORKFLOW)
        for note in (failed, ended):
            self.assertIn("evals_candidate", note)
            self.assertIn("temporary agent", note)
            self.assertIn("WARNING", note, "the last line of a run that could not delete the agent says so, and the note says where to look")
        self.assertTrue(failed.startswith("The evaluations stopped or failed."))
        self.assertIn("(nothing was run: run \\`agents-ready\\` first, which makes the version from the lock)", failed, "the words that rule 40 added are kept, and the sentence about the candidate is added to them")
        self.assertIn("The production Investigator was never written.", failed)
        self.assertIn("or the last line that the tool printed is a WARNING that names it", failed)
        self.assertIn("through the Investigator, or, with the input evals_candidate, through a temporary agent", ended)
        self.assertIn("a WARNING that names it is the last line that the tool prints when it was not", ended)
        self.assertIn("A run with a candidate is never the test of a release", ended)
        self.assertIn("with evals_candidate empty", ended)
        self.assertTrue(ended.endswith("The production agents were not changed."))
        self.assertNotIn("The agents were not changed.", ended, "a candidate run makes a temporary agent, so the note says which agents were not changed")

    def test_an_effort_that_is_not_none_low_medium_or_high_is_refused_before_anything_is_started(self):
        for bad in ("extreme", "LOW", "low;x", "--judge", "low high", "$(id)"):
            with self.subTest(effort=bad):
                done, args = started(EVALS_EFFORT=bad)
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("::error::The input evals_effort is none, low, medium or high. Nothing was changed.", done.stdout)
                self.assertEqual(args, [])

    def test_the_other_commands_ignore_both_inputs(self):
        for command in ("probe", "rule", "rule-apply"):
            with self.subTest(command=command):
                done, args = started(EVALS_COMMAND=command, EVALS_CANDIDATE="whatever it is; it is ignored", EVALS_EFFORT="whatever")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue(all("candidate" not in a and "effort" not in a and "whatever" not in a for a in args), args)

    def test_the_request_that_the_operator_receives_grows_by_the_one_file_and_stays_under_the_cap(self):
        tool = flow.operator_run()
        sizes = {}
        for label, changes in (("production", {}), ("candidate", {"EVALS_CANDIDATE": FIRST, "EVALS_EFFORT": "high", "EVALS_ONLY": "idle-disk-1"})):
            done, args = started(**changes)
            parsed = tool.build_parser().parse_args(args[1:])
            sizes[label] = {name: len(content.replace(b"\r\n", b"\n")) for name, content in tool.read_files(parsed).items()}
        self.assertEqual(set(sizes["candidate"]) - set(sizes["production"]), {f"candidate-{FIRST}.txt"})
        self.assertEqual(set(sizes["production"]) - set(sizes["candidate"]), set())
        self.assertEqual(sizes["candidate"][f"candidate-{FIRST}.txt"], len((FOLDER / f"{FIRST}.txt").read_text(encoding="utf-8").encode("utf-8")))
        self.assertLess(sum(sizes["candidate"].values()), tool.MAX_FILE_BYTES, "the request of a replay of a candidate fits the cap, measured with the line ends of the repository")
        self.assertLessEqual(sum(sizes["candidate"].values()) - sum(sizes["production"].values()), 20_000, "a candidate is at most 20,000 characters")

    def test_the_tool_finds_the_file_of_the_candidate_in_the_flat_folder_of_its_secret_volume_and_reads_nothing_else_of_the_candidates(self):
        tool = flow.operator_run()
        code = textwrap.dedent("""
            import importlib.util, sys
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("tool", Path.cwd() / "foundry-evals.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            helpers = sys.modules["aisec_helpers"]
            class Stop:
                calls = []
                def request(self, method, path, body=None, **options):
                    raise helpers.Problem("STOP: the candidate was found and accepted: the first call to the project is " + method + " " + path.split("?")[0], 1)
            print("code", module.main(sys.argv[1:] + ["--endpoint", "%s"], client=Stop()))
        """ % flow.ENDPOINT)
        done, args = started(EVALS_CANDIDATE=FIRST)
        parsed = tool.build_parser().parse_args(args[1:])
        with tempfile.TemporaryDirectory() as folder:
            for pair in parsed.secret_file:
                file_name, path = pair.split("=", 1)
                shutil.copyfile(ROOT / path, Path(folder) / file_name)
            self.assertFalse((Path(folder) / "candidates").exists(), "the volume is flat")
            env = {**os.environ, "GITHUB_ACTIONS": "true"}
            found = subprocess.run([sys.executable, "-c", code, "run", "--candidate", FIRST], cwd=folder, capture_output=True, text=True, env=env)
            self.assertIn("STOP: the candidate was found and accepted: the first call to the project is GET /agents/meternaut-investigator", found.stdout + found.stderr, found.stdout + found.stderr)
            (Path(folder) / f"candidate-{FIRST}.txt").unlink()
            missing = subprocess.run([sys.executable, "-c", code, "run", "--candidate", FIRST], cwd=folder, capture_output=True, text=True, env=env)
            self.assertIn(f"there is no candidate {FIRST}", missing.stdout + missing.stderr)
            self.assertNotIn("STOP", missing.stdout + missing.stderr, "no call was made")


class TheRecordOfTheCandidates(unittest.TestCase):
    """What proposal 11 says to the person who promotes a candidate: the order, what a candidate run is not, and the limit of the rows."""

    PROPOSAL = (ROOT / "docs" / "proposals" / "11-agent-harness-and-evaluation.md").read_text(encoding="utf-8")
    SECTION = re.search(r"(?ms)^## Trying a change of the instructions before it is made.*?(?=^## )", PROPOSAL).group(0)

    def test_the_order_of_a_promotion_is_the_order_of_rule_40_after_one_commit_that_changes_the_instructions_and_the_lock(self):
        item = self.SECTION[self.SECTION.index("5. When the candidate passes the test of the held-out rows"):]
        places = [item.index(words) for words in ("`INVESTIGATOR_INSTRUCTIONS` and the lock in one commit", "the order of rule 40", "`cases`", "`agents-ready`", "`foundry-evals` with no candidate", "a real run that a person starts")]
        self.assertEqual(places, sorted(places))
        self.assertLess(self.SECTION.index("1. Write the candidate"), self.SECTION.index("3. Start the Hub action `foundry-evals`"), "the candidate is written, and replayed, before anything of the release")
        self.assertLess(self.SECTION.index("3. Start the Hub action `foundry-evals`"), self.SECTION.index("5. When the candidate passes the test of the held-out rows"))

    def test_it_says_that_a_candidate_run_is_not_the_test_of_a_release_and_that_the_candidate_file_is_rewritten_or_dropped_after_a_promotion(self):
        for words in ("**A candidate run is not the test of a release.**", "with `evals_candidate` empty", "exits 0 with the same PASS lines", "It must never be taken for the test of a release",
                      "**After a promotion the candidate file is rewritten or dropped.**", "Any edit of the instructions makes that test fail", "also rewrites the candidate file against the new production text, or drops it"):
            self.assertIn(words, self.SECTION)

    def test_it_says_plainly_that_the_held_out_set_is_small_and_names_its_four_rows_and_that_only_the_replay_tool_promotes_nothing(self):
        # Until the four held-out rows were written (2026-11-22) this said that there is none: that sentence is false now, and what is true is the limit of four rows of three kinds, which it says as plainly.
        self.assertIn("The held-out set is small. Four rows of three kinds that no candidate was tuned on decide a release together with the rest", self.SECTION)
        self.assertIn("a better score on them alone is weak evidence", self.SECTION)
        self.assertNotIn("There is no held-out set", self.SECTION)
        item = self.SECTION[self.SECTION.index("**The held-out rows.**"):]
        for words in ("`heldout-firewall`, `heldout-appgw-mincap`, `heldout-sql-vcores` and `heldout-sql-busy`", "**no candidate was tuned on them**", "**What they do not prove:**", "No replay has used these rows yet."):
            self.assertIn(words, item)
        # The rule as it goes into rule 41, word for word, and the conditions that make it applicable (a run passes when no miss line is printed for the row, and how often each side is replayed): a rule that says
        # "no worse" and "better" and cannot be applied was the finding of the review of 2026-11-22.
        self.assertIn("A candidate is judged on the story rows that it was written against and on four held-out rows of other kinds (`heldout-*` in evaluation/cases.jsonl, written on 2026-11-22 from Learn and the price list and not tuned on): "
                      "it is promoted only when, replayed twice, it passes each held-out row as often as production does and one row more often, and the older rows still pass. "
                      "A held-out row stops being held out when a candidate is changed because of its result.", item)
        for words in ("passes a run when the replay prints no `miss:` line for it", "The busy database passes when its answer has no deletion and no lowered setting", "a way is not judged by code",
                      "at least twice with the candidate and at least twice with production", "(i) for each row the candidate passes in at least as many of its runs as production does in its own",
                      "(ii) for at least one row it passes in more", "(iii) the older rows still pass once with the candidate", "reading a held-out result and then editing the candidate is changing it because of that result",
                      "About 0.45 US dollar a row", "so it takes two days", "so a replay for a release names its rows with `evals_only`"):
            self.assertIn(words, item)
        for words in ("one run each", "no worse on them than production", "better on at least one", "expects no proposal"):
            self.assertNotIn(words, item, "the rule that nobody could apply, which the review of 2026-11-22 found: no run count, no meaning of worse and better")
        self.assertIn("A replay tool may suggest, test and measure. It never promotes.", self.SECTION)
        self.assertIn("**Nothing is promoted by the replay tool.** No replay tool writes the production agent, the lock or the instructions, or decides a release", self.SECTION)
        self.assertNotIn("A tool may suggest", self.SECTION, "agents-lock writes the lock and the instructions, and agents-ready makes versions: it is the replay tool that promotes nothing")

    def test_the_size_of_the_first_candidate_that_the_proposal_gives_is_the_size_of_the_file(self):
        text = (FOLDER / f"{FIRST}.txt").read_text(encoding="utf-8")
        self.assertIn(f"the first candidate is {len(text):,} characters", self.SECTION)
        self.assertIn(f"{len(text.encode('utf-8')):,} bytes for the first candidate", self.SECTION)
        self.assertNotIn("free or shared", self.SECTION, "the paragraph no longer names a kind of offer")


if __name__ == "__main__":
    unittest.main()
