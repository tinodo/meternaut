"""The guard of the AI Gateway in the deploy workflow (.github/workflows/deploy-hub.yml).

The AI Gateway's front door is public and cannot be made private (docs/proposals/08-ai-gateway.md), and the owner's rule is "NO PUBLIC ENDPOINTS UNLESS SPECIFICALLY REQUESTED" (AGENTS.md rule 15 (c)).
So the action `aigateway`, the only one that deploys it, stops at the first step of the job unless the workflow input `public_ai_gateway_requested` is set, which is done only when the owner has
asked in writing for a public AI Gateway. The checks of the gateway (`aigateway-check`), the preview (`what-if`) and every other action are not touched. No test calls Azure."""
import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
GUARD = "Refuse the AI Gateway unless the owner asked for a public one in writing"


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def steps():
    """Every step of the job, as (name, text)."""
    return [(re.match(r"name: (.+)", block).group(1), block) for block in re.split(r"(?m)^      - ", WORKFLOW)[1:]]


def guard():
    (block,) = [block for name, block in steps() if name == GUARD]
    return block


class TheInput(unittest.TestCase):
    def test_it_is_a_boolean_that_is_off_unless_somebody_sets_it(self):
        inputs = WORKFLOW.split("    inputs:\n")[1].split("\npermissions:")[0]
        block = re.search(r"(?ms)^      public_ai_gateway_requested:\n(.*?)(?=^      \w|\Z)", inputs)
        self.assertIsNotNone(block, "the input is there")
        self.assertRegex(block.group(1), r"(?m)^        type: boolean$")
        self.assertRegex(block.group(1), r"(?m)^        required: false$")
        self.assertRegex(block.group(1), r"(?m)^        default: false$", "the default is off: a click on Run workflow never asks for a public AI Gateway")
        self.assertEqual(len(re.findall(r"(?m)^      public_ai_gateway_requested:$", inputs)), 1)
        description = re.search(r'(?m)^        description: "(Only with aigateway: set it only when the owner has asked in writing for a public AI Gateway\..*)"$', block.group(1))
        self.assertIsNotNone(description)
        for words in ("front door is public and cannot be made private", "stops at its first step, before it signs in to Azure, unless this is set",
                      "aigateway-check, what-if and every other action ignore it"):
            self.assertIn(words, description.group(1), words)

    def test_the_description_of_the_action_says_that_aigateway_is_refused_without_it(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        gateway = description.split(" aigateway: ")[1].split(" aigateway-check: ")[0]
        self.assertTrue(gateway.startswith("refused at its first step unless the input public_ai_gateway_requested is set, which only the owner's written request for a public AI Gateway allows "), gateway[:160])
        self.assertIn("(its frontend is public and cannot be made private)", gateway)

    def test_only_the_guard_reads_the_input(self):
        self.assertEqual(WORKFLOW.count("public_ai_gateway_requested"), 7, "the header, the action's description, the input, the same input of a call, the guard's environment and the guard's two texts: nothing else mentions it")
        users = [name for name, block in steps() if "inputs.public_ai_gateway_requested" in block]
        self.assertEqual(users, [GUARD])


class TheGuardStep(unittest.TestCase):
    def test_it_is_the_first_step_of_the_job_that_can_stop_a_run_so_that_nothing_is_checked_out_read_or_signed_in_to_before_it(self):
        names = [name for name, _ in steps()]
        self.assertEqual(names[0], GUARD)
        self.assertEqual(names.index("Check out the repository"), 4, "after the refusal of the public gateway, the masks, the check of the values and the read of the checks of CI, which need no checkout")
        self.assertLess(names.index(GUARD), names.index("Sign in to Azure"))
        self.assertNotIn("uses:", guard(), "it runs a shell and nothing else: no action is downloaded for it")

    def test_it_runs_for_the_action_aigateway_alone(self):
        self.assertIn("        if: inputs.action == 'aigateway'\n", guard())
        for other in re.findall(r"- (\S+)", re.search(r"options:\n((?:          - .+\n)+)", WORKFLOW).group(1)):
            if other != "aigateway":
                self.assertNotIn(f"'{other}'", re.search(r"(?m)^        if: (.+)$", guard()).group(1), other)
        self.assertNotIn("continue-on-error", guard())

    def test_the_input_reaches_the_shell_through_the_environment_and_never_through_the_script(self):
        block = guard()
        self.assertIn("          PUBLIC_AI_GATEWAY_REQUESTED: ${{ inputs.public_ai_gateway_requested }}\n", block)
        script = block.split("        run: |\n")[1]
        self.assertNotIn("${{", script, "no expression inside the script (tools/workflow-lint.py)")
        self.assertIn('if [ "$PUBLIC_AI_GATEWAY_REQUESTED" != true ]; then', script, "only the word true lets the action go on")
        self.assertIn("exit 1", script)
        self.assertEqual(len(re.findall(r"\baz\b|gh |curl", "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#")))), 0, "the guard calls nothing")

    def test_the_error_says_in_plain_words_what_happened_why_and_who_may_lift_it(self):
        script = guard().split("        run: |\n")[1]
        for words in ("::error::This run does not deploy the AI Gateway: its front door is public and cannot be made private, and nothing public is made unless the owner has asked for it in writing.",
                      "Set the input public_ai_gateway_requested only when he has.", "Nothing was changed."):
            self.assertIn(words, script, words)

    def test_the_guard_comment_names_the_rule_and_the_record(self):
        comment = " ".join(line.strip()[2:] for line in guard().splitlines() if line.strip().startswith("# "))
        for words in ("docs/proposals/08-ai-gateway.md", "AGENTS.md rule 15 (c)", "first step of the job"):
            self.assertIn(words, comment, words)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheGuardRuns(unittest.TestCase):
    """The shell of the guard, run with bash with stand-ins first on the PATH for the commands that it must not call."""

    def run_guard(self, value):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            log = tmp / "calls.txt"
            log.write_text("", encoding="utf-8")
            for command in ("az", "gh", "curl", "python3", "git"):
                path = bin_dir / command
                path.write_text('#!/bin/bash\necho "$0 $*" >> "$FAKE_LOG"\nexit 9\n', encoding="utf-8", newline="\n")
                path.chmod(path.stat().st_mode | stat.S_IEXEC)
            script = tmp / "guard.sh"
            script.write_text(textwrap.dedent(guard().split("        run: |\n")[1]), encoding="utf-8", newline="\n")
            env = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": log.as_posix()}
            env.pop("PUBLIC_AI_GATEWAY_REQUESTED", None)
            if value is not None:
                env["PUBLIC_AI_GATEWAY_REQUESTED"] = value
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            return done, log.read_text(encoding="utf-8").splitlines()

    def test_without_the_input_or_with_anything_but_true_the_action_stops_with_the_plain_error_and_calls_nothing(self):
        for value in (None, "", "false", "False", "TRUE", "yes", "1", "true ", " true", "truee"):
            with self.subTest(value=value):
                done, calls = self.run_guard(value)
                self.assertEqual(done.returncode, 1, (value, done.stdout, done.stderr))
                said = done.stdout + done.stderr
                self.assertIn("::error::This run does not deploy the AI Gateway: its front door is public and cannot be made private", said)
                self.assertNotIn("The AI Gateway is not deployed", said, "the gateway was deployed on 2026-11-07: the error says what this run does, not what exists")
                self.assertIn("Set the input public_ai_gateway_requested only when he has. Nothing was changed.", said)
                self.assertNotIn("The input public_ai_gateway_requested is set", said, "it does not say that the owner asked")
                self.assertEqual(calls, [], "nothing is called: no Azure, no GitHub, no download")

    def test_with_the_input_set_the_action_goes_on_and_says_why(self):
        done, calls = self.run_guard("true")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("The input public_ai_gateway_requested is set: the owner has asked in writing for a public AI Gateway.", done.stdout)
        self.assertNotIn("::error::", done.stdout + done.stderr)
        self.assertEqual(calls, [])


class TheRulesSayIt(unittest.TestCase):
    def test_agents_md_says_that_the_input_is_set_only_on_the_owners_written_request(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        (rule,) = [line for line in agents.splitlines()
                   if line.startswith("    - **(c) Every model call of Meternaut goes through the AI Gateway, the governance hub of the Citadel design, with no direct path, not even for a test, unless the owner makes a written exception**")]
        for words in ("\"NO PUBLIC ENDPOINTS UNLESS SPECIFICALLY REQUESTED\"", "the action `aigateway`, the only one that deploys the AI Gateway, stops at its first step unless the workflow input `public_ai_gateway_requested` is set",
                      "which is done only when the owner has asked in writing for a public AI Gateway"):
            self.assertIn(words, rule, words)

    def test_the_decision_record_says_it_too(self):
        record = (ROOT / "docs" / "proposals" / "08-ai-gateway.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        for words in ("public_ai_gateway_requested", "only when the owner has asked in writing for a public AI Gateway", "the action `aigateway` stops at its first step"):
            self.assertIn(words, record, words)


if __name__ == "__main__":
    unittest.main()
