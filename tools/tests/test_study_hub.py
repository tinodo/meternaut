"""The Study switched on through the Hub (docs/proposals/15-learning.md): the variable STUDY of the environment hub and the action study-run of .github/workflows/deploy-hub.yml, which reuses the machinery of cases-run
(the Operator, the generic container script, the tool tools/cases-check.py). What these tests pin: that the switch is a variable and no secret, that the action is offered once and runs only after the Operator is found and
the app lists its functions, that it runs the same container script and the same two files as cases-run with a command of its own, that its group is cleaned up by its own prefix, that nothing is run from the runner but a
read, and that the summary says what happened. The scripts are not run: no test calls Azure or GitHub."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(file_name, label):
    spec = importlib.util.spec_from_file_location(label, ROOT / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


wl = load("tools/workflow-lint.py", "workflow_lint_of_the_study_hub_tests")
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-hub.yml"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
BOOTSTRAP = (ROOT / "environment" / "BOOTSTRAP.md").read_text(encoding="utf-8").replace("\r\n", "\n")

FIND = "Find the Operator, which runs the check from inside the network"
LISTING = "Before the Study is started, the cases app lists its functions"
STUDY = "Start one Study and read its History"
CLEANUP = "Delete any container group of the Study run that is left"
WATCH = "Start one Watch and read its History"
WATCH_CLEANUP = "Delete any container group of the checks that is left"
CI = "The checks of CI have passed for this commit"


def blocks():
    return re.findall(r"(?ms)^      - name: (.+?)\n(.*?)(?=^      - |\Z)", WORKFLOW)


def names():
    return [title for title, _ in blocks()]


def step(name):
    (text,) = [body for title, body in blocks() if title == name]
    return text


def code_of(name):
    run = step(name).split("        run: |\n", 1)[1]
    return "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))


def options():
    return re.findall(r"(?m)^          - (\S+)$", re.search(r"(?ms)^      action:\n(.*?)^      \w", WORKFLOW).group(1))


class TheSwitchIsAVariableOfTheEnvironment(unittest.TestCase):
    def test_the_job_reads_it_from_the_variables_and_it_is_no_identifier_of_the_estate(self):
        job_env = re.search(r"(?ms)^    env:\n(.*?)^    steps:", WORKFLOW).group(1)
        self.assertEqual(job_env.count("      STUDY: ${{ vars.STUDY }}\n"), 1)
        self.assertNotIn("secrets.STUDY", WORKFLOW, "a switch is plain configuration: GitHub masks a secret in the public log, and a word that is on or off needs no mask")
        self.assertNotIn("STUDY", wl.ESTATE_SECRETS)
        self.assertNotIn("STUDY", wl.NEVER_VARIABLES)
        self.assertEqual(wl.lint_file(WORKFLOW_PATH), [], "the lint of the Hub passes with the variable and the new steps")

    def test_the_bootstrap_page_lists_it_among_the_variables_and_says_how_to_switch_the_study_on_and_off(self):
        variables = BOOTSTRAP.split("Its **variables** are plain configuration", 1)[1].split("The repository's list of allowed actions", 1)[0]
        self.assertIn("`STUDY`", variables)
        for words in ("`STUDY` is a **variable**", "Set the variable `STUDY` to `on`", "Run `cases`", "`study-run`", "set `STUDY` to `off` and run `cases`"):
            self.assertIn(words, BOOTSTRAP, words)


class TheActionIsOfferedOnceAndRunsInTheOperatorAfterTheFunctionsAreListed(unittest.TestCase):
    def test_it_is_offered_once_right_after_cases_run(self):
        found = options()
        self.assertEqual(found.count("study-run"), 1)
        self.assertEqual(found[found.index("cases-run") + 1], "study-run")

    def test_the_description_says_what_it_runs_what_it_prints_and_that_it_changes_nothing(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        sentence = description.split(" study-run: ")[1].split(" page-latency: ")[0]
        for words in ("the Operator puts the control message of the job study in it", "from inside the network", "the same container script and the same tool as cases-run", "it needs operator first",
                      "the variable STUDY of the environment hub is on and cases has been run", "counts and plain words only", "the pages read", "the claims kept and thrown away",
                      "in the app's own words only", "STUDY is off, the Scholar was not made, no page could be read, or no line arrived",
                      "It changes nothing in the estate"):
            self.assertIn(words, sentence, words)
        self.assertNotIn('"', sentence, "the description is one quoted value on one line")
        self.assertIn(" cases-run: start one Watch through the control queue", description, "the sentence of cases-run is where it was")

    def test_the_steps_come_in_the_order_the_operator_is_found_the_functions_are_listed_the_study_runs_and_its_group_is_cleaned_up(self):
        order = [names().index(name) for name in (FIND, LISTING, STUDY, CLEANUP)]
        self.assertEqual(order, sorted(order))
        self.assertLess(names().index("Work out the settings"), order[0], "after the settings, whose outputs the steps use")
        self.assertLess(order[-1], names().index("What was done"))
        self.assertLess(names().index(WATCH_CLEANUP), order[1], "the steps of the Watch are where they were, and the Study's follow them")
        self.assertIn("if: inputs.action == 'cases-run' || inputs.action == 'page-latency' || inputs.action == 'teams-test' || inputs.action == 'study-run'\n", step(FIND))
        self.assertIn("if: inputs.action == 'study-run'\n", step(LISTING))
        self.assertIn("if: inputs.action == 'study-run'\n", step(STUDY))
        self.assertIn("id: study\n", step(STUDY))
        self.assertIn("if: always() && steps.study.outcome != 'skipped'\n", step(CLEANUP), "the second line behind the tool's own delete runs when the run was cancelled too, and only when the step started")
        self.assertIn("if: inputs.action == 'cases-run'\n", step(WATCH), "the step of the Watch is not shared: its pins hold")

    def test_no_other_step_runs_for_the_action_and_the_gate_of_ci_runs_for_every_action(self):
        runs_for_it = [title for title, body in blocks() if "inputs.action == 'study-run'" in body.split("        run: |")[0]]
        self.assertEqual(runs_for_it, [FIND, LISTING, STUDY])
        self.assertNotIn("        if:", step(CI).split("        env:")[0], "the same gate as every action: the Hub does not run until CI has passed for this commit")
        self.assertNotIn("study-run", step(CI))

    def test_the_listing_is_a_read_from_the_runner_and_it_waits_for_the_function_of_the_study(self):
        script = code_of(LISTING)
        self.assertIn('python3 tools/cases-check.py functions --site "$site" --minutes 5', script)
        self.assertIn("SITE_NAME: ${{ steps.params.outputs.cases_function_app_name }}", step(LISTING))
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        self.assertIn("study-weekly", (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8"), "the tool waits for the function of the Study as one of the app's functions")

    def test_the_study_runs_the_generic_container_script_and_the_two_files_of_the_watch_with_a_command_of_its_own(self):
        block, script = step(STUDY), code_of(STUDY)
        self.assertIn('python3 tools/operator-run.py run --resource-group "$ENV_RESOURCE_GROUP" --name "op-study-$GITHUB_RUN_ID"', script)
        for word in ('--subnet-id "$OPERATOR_SUBNET_ID"', '--identity-id "$OPERATOR_IDENTITY_ID"', '--image "$OPERATOR_IMAGE"', "--script operator/run-tool.sh", '"${dns[@]}"', '--summary "$GITHUB_STEP_SUMMARY"',
                     '--env "GITHUB_ACTIONS=true"', '--env "OPERATOR_CLIENT_ID=$OPERATOR_CLIENT_ID"', '--env "OPERATOR_SUBSCRIPTION=$ENV_SUBSCRIPTION_ID"',
                     "for server in ${ENV_DNS_SERVERS//,/ }; do dns+=(--dns-server \"$server\"); done"):
            self.assertIn(word, script, word)
        self.assertEqual(re.findall(r'--secret-file "([^"=]+)=tools/([^"]+)"', script), [("cases-check.py", "cases-check.py"), ("check-helpers.py", "check-helpers.py")], "the files of the Watch's step, and no new one")
        self.assertEqual(len(re.findall(r"--secret-file", script)), 2)
        self.assertIn('--env "TOOL_NAME=cases-check"', script)
        args = re.search(r'TOOL_ARGS=([^"]+)"', script).group(1)
        self.assertEqual(args, "study --storage-account $STORAGE_ACCOUNT --insights $insights --minutes 20")
        self.assertNotIn("--counts-only", args, "the command study has one mode only, and it is the one for a public log")
        env = dict(re.findall(r"(?m)^          (\w+): (.+)$", block.split("        env:\n")[1].split("        run: |")[0]))
        self.assertEqual(env, {"STORAGE_ACCOUNT": "${{ steps.params.outputs.storage_account_name }}", "INSIGHTS_NAME": "${{ steps.params.outputs.appinsights_name }}",
                               "OPERATOR_IDENTITY_ID": "${{ steps.operator.outputs.identity_id }}", "OPERATOR_CLIENT_ID": "${{ steps.operator.outputs.client_id }}",
                               "OPERATOR_SUBNET_ID": "${{ steps.operator.outputs.subnet_id }}"})
        for word in ("--secure-env", "--allow-tag", "get-access-token", "listSecrets", "az account", "--auth-mode", "secrets."):
            self.assertNotIn(word, block, word)

    def test_the_times_are_ordered_the_tool_waits_less_than_the_group_lives_and_the_group_less_than_the_step(self):
        script, block = code_of(STUDY), step(STUDY)
        waits = int(re.search(r"--minutes (\d+)", re.search(r'TOOL_ARGS=([^"]+)"', script).group(1)).group(1))
        seconds = int(re.search(r"--timeout-seconds (\d+)", script).group(1))
        minutes = int(re.search(r"(?m)^        timeout-minutes: (\d+)$", block).group(1))
        self.assertEqual((waits, seconds, minutes), (20, 1800, 40))
        self.assertLess(waits * 60, seconds)
        self.assertLess(seconds, minutes * 60)

    def test_the_arguments_fit_the_strict_pattern_of_the_container_script_and_the_tool_has_the_command(self):
        pattern = re.search(r"argument_characters='([^']+)'", (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")).group(1)
        command_word = re.search(r"command_word='([^']+)'", (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")).group(1)
        args = re.search(r'TOOL_ARGS=([^"]+)"', code_of(STUDY)).group(1).replace("$STORAGE_ACCOUNT", "stmeternautfn0a1b2c3d").replace("$insights", "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-x/providers/Microsoft.Insights/components/appi-x")
        self.assertNotIn("$", args)
        self.assertRegex(args, pattern)
        self.assertLessEqual(len(args), 600)
        self.assertRegex(args.split()[0], command_word)
        tool = (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8")
        self.assertIn('commands.add_parser("study"', tool)
        for loaded in re.findall(r'with_name\("([^"]+)"\)', tool):
            self.assertIn(loaded, ("check-helpers.py",), "everything that the tool loads from its own folder is sent")
        size = sum((ROOT / "tools" / name).stat().st_size for name in ("cases-check.py", "check-helpers.py")) + (ROOT / "operator" / "run-tool.sh").stat().st_size
        self.assertLess(size, 300_000, "far below the 400,000 bytes that the probe found a secret volume takes whole")

    def test_the_runner_starts_nothing_and_reads_no_telemetry_for_the_study_it_lists_the_functions_and_the_operator_does_the_rest(self):
        code = "\n".join(line for title in (LISTING, STUDY, CLEANUP) for line in code_of(title).splitlines())
        self.assertNotRegex(code, r"python3 tools/(check-helpers|cases-check)\.py (run|study)\b", "no command of a check tool that sends a message runs on the runner")
        for word in ("storage.azure.com", "/messages?", "servicebus.windows.net", "queue.core.windows.net", "az monitor", "api.applicationinsights.io"):
            self.assertNotIn(word, code, word)

    def test_the_cleanup_deletes_only_the_groups_of_the_study_through_the_tool_and_it_cannot_take_a_group_of_another_check(self):
        script = code_of(CLEANUP)
        self.assertIn('python3 tools/operator-run.py cleanup --resource-group "$ENV_RESOURCE_GROUP" --prefix op-study- --older-than-minutes 0', script)
        self.assertIn("::warning::", script)
        self.assertNotIn("delete", script.replace("deletes", ""), "the tool deletes, not a command of the step")
        self.assertIn('--name "op-study-$GITHUB_RUN_ID"', code_of(STUDY), "the prefix of the cleanup is the start of the name that the step gives its group")
        others = re.findall(r'--name "(op-[a-z]+-)\$GITHUB_RUN_ID"', WORKFLOW)
        self.assertEqual(others.count("op-study-"), 1)
        for other in set(others) - {"op-study-"}:
            self.assertFalse(other.startswith("op-study-") or "op-study-".startswith(other), f"neither cleanup can take the groups of the other: {other}")

    def test_the_summaries_say_where_the_work_was_done_what_to_check_and_what_the_study_does_not_do(self):
        block = step("What was done")
        failed, finished = re.findall(r"(?m)^\s+study-run\) echo \"(.*?)\" ;;$", block)
        for words in ("A container group named \\`op-study-$GITHUB_RUN_ID\\` may have been made, and the last step of the run deletes it if the tool could not.",
                      "this runner put nothing in the queue and read no telemetry.", "\\`operator\\` has to be run first", "without \\`study-weekly\\`", "run \\`cases\\`",
                      "\\`STUDY is off in the app\\` means that the variable STUDY of the environment hub is not on, or that \\`cases\\` has not been run since it was set.",
                      "\\`The Scholar was not made\\` means that the Foundry project refused the agent or that its stored definition is not the one in the lock (\\`agents-drift\\` says which).",
                      "\\`No page could be read\\` with every call of the page reader unavailable means that the app's network may not let the app's subnet reach learn.microsoft.com",
                      "on port 443 (the landing zone's firewall, or its DNS): Meternaut opens nothing itself, and the platform team decides.", "The Study changes no resource of the estate", "Running \\`study-run\\` again is safe."):
            self.assertIn(words, failed, words)
        for words in ("The Operator, from inside the network, put the control message of the job study in the queue and read the telemetry, with its own identity and no key; this runner put nothing in the queue",
                      "as counts and plain words with every identifier masked", "it is context for the Investigator and moves no finding, no figure and no proposal", "no resource of the estate was changed",
                      "The timer \\`study-weekly\\` runs it every Monday while the variable STUDY of the environment hub is on"):
            self.assertIn(words, finished, words)
        self.assertEqual(len(re.findall(r"(?m)^\s+study-run\) echo ", block)), 2)
        cases = re.findall(r"(?m)^\s+cases\) echo \"(.*?)\" ;;$", block)[1]
        self.assertIn("is switched by the variable STUDY of the environment hub, which was \\`${STUDY:-not set}\\` in this run and is off unless it says on; the action \\`study-run\\` runs it once.", cases)


if __name__ == "__main__":
    unittest.main()
