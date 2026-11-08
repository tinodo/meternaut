"""The Teams bot's action in the deploy workflow (.github/workflows/deploy-hub.yml).

The bot's messaging endpoint is public by necessity (docs/proposals/13-teams-and-outlook.md), and the owner's rule is "NO PUBLIC ENDPOINTS UNLESS SPECIFICALLY REQUESTED" (AGENTS.md rule 15 (c)). So the action `teams`,
the only one that deploys it, stops at a guard before the tests and before any sign-in unless the workflow input `public_teams_bot_requested` is set (only when the owner has asked in writing) and the repository
variable `TEAMS_BOT_ENABLED` is True. The block of the action is written in a file that the builder of the Teams channel left for the orchestrator, because the workflow belongs to the infrastructure builder; until
that block is in the workflow these tests skip themselves, and from then on they hold the action to it. HUB_WORKFLOW_FILE names another copy of the workflow to check (the builder tried the block on a copy). No test calls Azure."""
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
WORKFLOW_FILE = Path(os.environ.get("HUB_WORKFLOW_FILE") or ROOT / ".github" / "workflows" / "deploy-hub.yml")
WORKFLOW = WORKFLOW_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
OPTIONS = re.findall(r"- (\S+)", re.search(r"options:\n((?:          - .+\n)+)", WORKFLOW).group(1))
ACTIVE = "teams" in OPTIONS
GUARD = "Refuse the Teams bot unless the owner asked for a public endpoint in writing and the switch is on"
CASES_GUARD = "The function subnet is free for the cases app, which runs on Flex Consumption"
ONLY_WHEN_TEAMS = "        if: inputs.action == 'teams'\n"
SKIP = "the action teams has not been added to the Hub workflow yet"


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


def named(name):
    (block,) = [block for step, block in steps() if step == name]
    return block


def script_of(block):
    return block.split("        run: |\n")[1]


def commands_of(block):
    """The lines of the script that are not comments."""
    return "\n".join(line for line in script_of(block).splitlines() if not line.lstrip().startswith("#"))


def teams_steps():
    """The steps that run for the action teams alone, in order, the guard first."""
    return [(name, block) for name, block in steps() if ONLY_WHEN_TEAMS in block]


@unittest.skipUnless(ACTIVE, SKIP)
class TheInput(unittest.TestCase):
    def test_it_is_a_boolean_that_is_off_unless_somebody_sets_it(self):
        inputs = WORKFLOW.split("    inputs:\n")[1].split("\npermissions:")[0]
        block = re.search(r"(?ms)^      public_teams_bot_requested:\n(.*?)(?=^      \w|\Z)", inputs)
        self.assertIsNotNone(block, "the input is there")
        self.assertRegex(block.group(1), r"(?m)^        type: boolean$")
        self.assertRegex(block.group(1), r"(?m)^        required: false$")
        self.assertRegex(block.group(1), r"(?m)^        default: false$", "the default is off: a click on Run workflow never asks for a public bot")
        self.assertEqual(len(re.findall(r"(?m)^      public_teams_bot_requested:$", inputs)), 1)
        description = re.search(r'(?m)^        description: "(Only with teams: set it only when the owner has asked in writing for a public Teams bot\..*)"$', block.group(1))
        self.assertIsNotNone(description)
        for words in ("messaging endpoint is public by necessity", "stops at its first step, before it signs in to Azure, unless this is set and the repository variable TEAMS_BOT_ENABLED is True",
                      "what-if and every other action ignore it"):
            self.assertIn(words, description.group(1), words)

    def test_the_description_of_the_action_says_that_teams_is_refused_without_it(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        teams = description.split(" teams: ")[1]
        self.assertTrue(teams.startswith("the Teams bot (docs/proposals/13-teams-and-outlook.md), refused at its first step unless the input public_teams_bot_requested is set, which only the owner's "
                                         "written request for a public endpoint allows"), teams[:200])
        for words in ("TEAMS_BOT_ENABLED is True", "tools/build-teams-bot.sh", "tools/teams-check.py", "Microsoft.BotService registered once by a person", "a Teams administrator uploads the package by hand"):
            self.assertIn(words, teams, words)

    def test_only_the_guard_reads_the_input_and_the_variable(self):
        self.assertEqual([name for name, block in steps() if "inputs.public_teams_bot_requested" in block], [GUARD])
        self.assertEqual([name for name, block in steps() if "vars.TEAMS_BOT_ENABLED" in block], [GUARD])


@unittest.skipUnless(ACTIVE, SKIP)
class TheGuardStep(unittest.TestCase):
    def test_it_comes_right_after_the_checkout_and_before_the_set_up_the_tests_and_every_sign_in(self):
        names = [name for name, _ in steps()]
        self.assertEqual(names.index(GUARD), names.index("Check out the repository") + 1)
        self.assertLess(names.index(GUARD), names.index("Set up Python 3.13, the runtime of the function app"))
        self.assertLess(names.index(GUARD), names.index("The tools and the templates pass their checks"))
        self.assertLess(names.index(GUARD), names.index("Sign in to Azure"))
        self.assertNotIn("uses:", named(GUARD), "it runs a shell and nothing else: no action is downloaded for it")

    def test_it_runs_for_the_action_teams_alone(self):
        block = named(GUARD)
        self.assertIn(ONLY_WHEN_TEAMS, block)
        for other in OPTIONS:
            if other != "teams":
                self.assertNotIn(f"'{other}'", re.search(r"(?m)^        if: (.+)$", block).group(1), other)
        self.assertNotIn("continue-on-error", block)

    def test_the_input_and_the_switch_reach_the_shell_through_the_environment_and_never_through_the_script(self):
        block = named(GUARD)
        self.assertIn("          PUBLIC_TEAMS_BOT_REQUESTED: ${{ inputs.public_teams_bot_requested }}\n", block)
        self.assertIn("          TEAMS_BOT_ENABLED: ${{ vars.TEAMS_BOT_ENABLED }}\n", block)
        script = script_of(block)
        self.assertNotIn("${{", script, "no expression inside the script (tools/workflow-lint.py)")
        self.assertIn('if [ "$PUBLIC_TEAMS_BOT_REQUESTED" != true ]; then', script, "only the word true lets the action go on")
        self.assertIn('if [ "$TEAMS_BOT_ENABLED" != true ] && [ "$TEAMS_BOT_ENABLED" != True ]; then', script)
        self.assertEqual(script.count("exit 1"), 2)
        self.assertEqual(len(re.findall(r"\baz\b|gh |curl", commands_of(block))), 0, "the guard calls nothing")

    def test_each_error_says_in_plain_words_what_happened_why_and_who_may_lift_it(self):
        script = script_of(named(GUARD))
        for words in ("::error::This run does not deploy the Teams bot: its messaging endpoint is public, and nothing public is made unless the owner has asked for it in writing.",
                      "Set the input public_teams_bot_requested only when he has.",
                      "::error::This run does not deploy the Teams bot: the repository variable TEAMS_BOT_ENABLED is not True. It is the switch of the bot, and it stays False until the owner says so.",
                      "Nothing was changed."):
            self.assertIn(words, script, words)

    def test_the_comment_names_the_rule_and_the_record(self):
        comment = " ".join(line.strip()[2:] for line in named(GUARD).splitlines() if line.strip().startswith("# "))
        for words in ("docs/proposals/13-teams-and-outlook.md", "AGENTS.md rule 15 (c)", "before any sign-in"):
            self.assertIn(words, comment, words)


@unittest.skipUnless(ACTIVE and BASH is not None, SKIP if not ACTIVE else "no bash on this machine")
class TheGuardRuns(unittest.TestCase):
    """The shell of the guard, run with bash with stand-ins first on the PATH for the commands that it must not call."""

    def run_guard(self, requested, switch):
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
            script.write_text(textwrap.dedent(script_of(named(GUARD))), encoding="utf-8", newline="\n")
            env = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": log.as_posix()}
            for name, value in (("PUBLIC_TEAMS_BOT_REQUESTED", requested), ("TEAMS_BOT_ENABLED", switch)):
                env.pop(name, None)
                if value is not None:
                    env[name] = value
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            return done, log.read_text(encoding="utf-8").splitlines()

    def test_without_the_input_or_with_anything_but_true_the_action_stops_with_the_plain_error_and_calls_nothing(self):
        for value in (None, "", "false", "False", "TRUE", "yes", "1", "true ", " true", "truee"):
            with self.subTest(input=value):
                done, calls = self.run_guard(value, "True")
                self.assertEqual(done.returncode, 1, (value, done.stdout, done.stderr))
                said = done.stdout + done.stderr
                self.assertIn("::error::This run does not deploy the Teams bot: its messaging endpoint is public", said)
                self.assertIn("Set the input public_teams_bot_requested only when he has. Nothing was changed.", said)
                self.assertNotIn("the owner has asked in writing for a public Teams bot.", said, "it does not say that the owner asked")
                self.assertEqual(calls, [], "nothing was called")

    def test_with_the_input_but_a_switch_that_is_not_true_the_action_stops_with_the_plain_error_and_calls_nothing(self):
        for value in (None, "", "false", "False", "FALSE", "TRUE", "yes", "1", "true ", " True", "Truee"):
            with self.subTest(switch=value):
                done, calls = self.run_guard("true", value)
                self.assertEqual(done.returncode, 1, (value, done.stdout, done.stderr))
                said = done.stdout + done.stderr
                self.assertIn("the repository variable TEAMS_BOT_ENABLED is not True. It is the switch of the bot, and it stays False until the owner says so. Nothing was changed.", said)
                self.assertEqual(calls, [])

    def test_with_both_set_the_guard_says_so_and_lets_the_run_go_on_and_still_calls_nothing(self):
        for switch in ("true", "True"):
            with self.subTest(switch=switch):
                done, calls = self.run_guard("true", switch)
                self.assertEqual(done.returncode, 0, (done.stdout, done.stderr))
                self.assertIn("The input public_teams_bot_requested is set and TEAMS_BOT_ENABLED is True: the owner has asked in writing for a public Teams bot.", done.stdout)
                self.assertEqual(calls, [])


@unittest.skipUnless(ACTIVE, SKIP)
class TheAction(unittest.TestCase):
    def test_every_step_of_the_action_comes_after_the_guard_and_the_guard_is_the_first_of_them(self):
        names = [name for name, _ in steps()]
        mine = [name for name, _ in teams_steps()]
        self.assertEqual(mine[0], GUARD)
        self.assertEqual(len(mine), 9, "the guard and the eight steps of the action: settings, reads, deploy, build, sign-in, publish, sign-in, read-back and door")
        for name in mine[1:]:
            self.assertGreater(names.index(name), names.index("Sign in to Azure"), name)

    def test_the_settings_are_made_from_the_cases_file_and_checked_against_the_compiled_template(self):
        script = commands_of(named("Work out the Teams bot's settings"))
        self.assertIn('python3 tools/teams-params.py --cases-params "$RUNNER_TEMP/cases.parameters.json" --out "$RUNNER_TEMP/teams.parameters.json" >> "$GITHUB_OUTPUT"', script)
        self.assertIn('python3 tools/environment-params.py check --params "$RUNNER_TEMP/teams.parameters.json" --template "$RUNNER_TEMP/teams.json" --label teams', script)
        checks = named("The tools and the templates pass their checks")
        self.assertIn("environment/aigateway/subnet.bicep environment/teams/main.bicep; do", checks, "the template is built and linted with the others")
        self.assertIn('az bicep build --file environment/teams/main.bicep --outfile "$RUNNER_TEMP/teams.json"', checks)

    def test_the_reads_before_the_deploy_change_nothing_and_name_what_to_run_first(self):
        block = named("The base, the function subnet and the resource provider of the Azure Bot Service are there, which the Teams bot builds on")
        script = commands_of(block)
        self.assertNotRegex(script, r"\baz (?:rest --method (?!get)|resource (?:create|delete)|deployment|role)")
        for words in ("Run base first", "run model-side first", "Microsoft.App/environments", "Microsoft.BotService", "A person does that once"):
            self.assertIn(words, script, words)
        self.assertEqual(script.count("az provider register"), 2, "the workflow only says the command: it does not run it (the lines are the messages)")
        self.assertNotRegex(re.sub(r'echo "[^\n]*', "", script), r"az provider register", "and no line runs it")

    def test_it_is_deployed_through_the_one_deploy_tool_with_the_teams_template_and_nothing_else(self):
        script = commands_of(named("Deploy the Teams bot"))
        self.assertIn("python3 tools/az-deploy.py create", script)
        self.assertIn("--template environment/teams/main.bicep --parameters \"$RUNNER_TEMP/teams.parameters.json\"", script)
        self.assertIn('--name "teams-$GITHUB_RUN_ID" --output botClientId', script)
        self.assertIn("id: teams\n", named("Deploy the Teams bot"))
        self.assertIn('echo "bot_client_id=$client" >> "$GITHUB_OUTPUT"', script)

    def test_the_package_is_the_one_that_the_build_script_makes_and_the_publish_is_said_to_be_unproved(self):
        self.assertIn('bash tools/build-teams-bot.sh "$RUNNER_TEMP/teams-bot" "$RUNNER_TEMP/teams-bot.zip"', commands_of(named("Build the Teams bot's package")))
        block = named("Publish the code to the Teams bot's function app")
        script = commands_of(block)
        self.assertIn('az functionapp deployment source config-zip --resource-group "$ENV_RESOURCE_GROUP" --name "$BOT_APP" --src "$RUNNER_TEMP/teams-bot.zip" --build-remote false', script)
        self.assertIn("has NOT been run for this app", script_of(block))
        self.assertIn("timeout-minutes: 25", block)

    def test_the_read_back_and_the_door_are_the_check_tool_and_name_the_identity_of_the_template(self):
        script = commands_of(named("Read the Teams bot back from Azure and knock at its door with no token"))
        self.assertIn("python3 tools/teams-check.py read-back", script)
        self.assertIn("python3 tools/teams-check.py door --host \"$host\"", script)
        self.assertIn("--identity id-meternaut-teams-bot", script)
        template = (ROOT / "environment" / "teams" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn("name: 'id-${workload}-teams-bot'", template)
        self.assertIn("param workload string = 'meternaut'", template)

    def test_each_sign_in_is_the_pinned_one_of_the_other_actions_and_a_new_one_follows_every_long_step(self):
        logins = [block for name, block in teams_steps() if "azure/login@" in block]
        self.assertEqual(len(logins), 2)
        pinned = re.search(r"uses: (azure/login@[0-9a-f]{40}) # v3\.1\.0", named("Sign in to Azure")).group(1)
        for block in logins:
            self.assertIn(f"uses: {pinned} # v3.1.0", block)
            self.assertIn("client-id: ${{ secrets.AZURE_CLIENT_ID }}", block)
        names = [name for name, _ in teams_steps()]
        self.assertEqual([n.split(" ")[0] for n in names[5:8]], ["Sign", "Publish", "Sign"], "a fresh credential before the publish and before the read-back")

    def test_no_step_of_the_action_deletes_anything_or_reads_a_secret(self):
        for name, block in teams_steps():
            script = commands_of(block) if "        run: |\n" in block else ""
            self.assertNotRegex(script, r"\bdelete\b|\bpurge\b|--no-wait|list-keys|listKeys|regenerate|az keyvault", name)
            self.assertEqual(len(re.findall(r"secrets\.", re.sub(r"(?s)with:.*", "", block))), 0, f"{name}: a secret reaches a script only through a sign-in")

    def test_the_cases_guard_lets_the_bots_app_share_the_function_subnet(self):
        block = named(CASES_GUARD)
        self.assertIn('[[ "${name,,}" == func-meternaut-teams-* ]]; then continue; fi', script_of(block))
        self.assertIn("The one exception is the Teams bot's app (func-meternaut-teams-<digest>, docs/proposals/13-teams-and-outlook.md)", block)
        names = re.search(r"func-meternaut-teams-", (ROOT / "tools" / "teams-params.py").read_text(encoding="utf-8"))
        self.assertIsNotNone(names, "the name that the bot's app gets is the one that the guard lets through")

    def test_what_was_done_tells_the_two_outcomes_and_names_the_bots_client_id(self):
        block = named("What was done")
        self.assertIn("          TEAMS_BOT_CLIENT_ID: ${{ steps.teams.outputs.bot_client_id }}\n", block)
        self.assertIn("          TEAMS_BOT_APP: ${{ steps.teams_params.outputs.teams_bot_app_name }}\n", block)
        arms = re.findall(r"(?m)^                teams\) echo \"(.*)\" ;;$", block)
        self.assertEqual(len(arms), 2, "one for a run that did not finish and one for a run that did")
        self.assertIn("nothing is repaired from here, and the endpoint answers every caller until a person looks at it", arms[0])
        self.assertIn("This run does not prove that a card reaches a person", arms[1])
        self.assertIn("python tools/teams-package.py build --bot-id", arms[1])
        self.assertNotIn("${{", "".join(arms))

    def test_no_other_action_uses_what_the_teams_steps_make(self):
        users = [name for name, block in steps() if re.search(r"steps\.teams(?:_params)?\.outputs", block)]
        self.assertEqual(sorted(users), sorted([name for name, block in teams_steps() if "steps.teams_params" in block] + ["What was done"]))
        for name, block in steps():
            if name not in dict(teams_steps()) and name != "What was done":
                self.assertNotIn("teams.parameters.json", block, name)


if __name__ == "__main__":
    unittest.main()
