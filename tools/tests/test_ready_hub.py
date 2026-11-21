"""The action agents-ready of the Hub (docs/proposals/11-agent-harness-and-evaluation.md, "The order of a release"): the stored version of each of the three agents made from the lock before the replay and
the real run. It reuses the machinery of cases-run and study-run (the Operator, the generic container script, the tool tools/cases-check.py with a command of its own). What these tests pin: that the action is
offered once, in the order of a release, that it runs only after the Operator is found and the app lists its functions, that it runs the same container script and the same two files with its own command, that its
group is cleaned up by its own prefix, that nothing is run from the runner but a read, that the description and the summaries say what it does and what it does not prove, and that the replay names it. The scripts
are not run: no test calls Azure or GitHub."""
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


wl = load("tools/workflow-lint.py", "workflow_lint_of_the_ready_hub_tests")
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-hub.yml"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")

FIND = "Find the Operator, which runs the check from inside the network"
LISTING = "Before the agents are made ready, the cases app lists its functions"
READY = "Make the agents ready from the lock and read what the app said"
CLEANUP = "Delete any container group of the agents-ready run that is left"
STUDY_CLEANUP = "Delete any container group of the Study run that is left"
WATCH = "Start one Watch and read its History"
CI = "The checks of CI have passed for this commit"
NEXT = "run foundry-evals on this version, then cases-run"


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


def description():
    return re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)


class TheActionIsOfferedInTheOrderOfARelease(unittest.TestCase):
    def test_it_is_offered_once_between_cases_and_cases_run_so_that_the_list_reads_in_the_order_of_a_release(self):
        found = options()
        self.assertEqual(found.count("agents-ready"), 1)
        self.assertEqual(found[found.index("cases"):found.index("cases") + 3], ["cases", "agents-ready", "cases-run"])

    def test_the_description_says_what_it_runs_what_it_prints_what_comes_next_and_that_it_changes_nothing(self):
        sentence = description().split(" agents-ready: ")[1].split(" cases-run: ")[0]
        for words in ("the three agents (the Investigator, the Skeptic and the Scholar) from the lock, before any run, through the harness that every run uses",
                      "the Operator puts the control message of the job ready in the control queue and reads the lines of that request from the telemetry, both from inside the network",
                      "the same container script and the same tool as cases-run", "It needs operator and cases first", "counts and plain words only", "its name, its version",
                      "the first 12 hex digits of the lock's digest of its definition", "made or existing", "the reason word and what to check", "no line arrived in 10 minutes",
                      f"it says what comes next: {NEXT}", "The order of a release is cases, agents-ready, foundry-evals on the exact version, cases-run",
                      "It calls no model, reads nothing of the estate and changes nothing in it", "a version that exists is not a promoted one, because a run uses the latest version of each agent"):
            self.assertIn(words, sentence, words)
        self.assertNotIn('"', sentence, "the description is one quoted value on one line")
        self.assertIn(" cases-run: start one Watch through the control queue", description(), "the sentence of cases-run is where it was")

    def test_the_description_of_cases_names_the_order_of_a_release_and_the_one_of_the_replay_names_the_action(self):
        cases = description().split(" cases: ")[1].split(" agents-ready: ")[0].rstrip()
        self.assertTrue(cases.endswith("For a release, the next action is agents-ready, then foundry-evals on that version, then cases-run."), cases[-200:])
        replay = description().split(" foundry-evals: ")[1].split(" foundry-redteam: ")[0]
        self.assertIn("it needs operator, aigateway, foundry and cases first, and after a release agents-ready, because it refuses a stored Investigator that is not what the lock says and runs nothing then", replay)

    def test_the_replay_tools_say_to_run_it_when_the_stored_version_is_not_the_lock_s(self):
        for tool, agent in (("foundry-evals.py", "Investigator"), ("study-evals.py", "Scholar")):
            source = (ROOT / "tools" / tool).read_text(encoding="utf-8")
            self.assertIn(f'the stored {agent} is not what the lock says (', source)
            self.assertIn("): nothing was run. Run the Hub action agents-ready first: it makes the version from the lock and calls no model", source, tool)
        self.assertIn(NEXT, (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8"), "what the step prints is what the description promises")


class TheStepsRunInTheOperatorAfterTheFunctionsAreListed(unittest.TestCase):
    def test_the_steps_come_in_the_order_the_operator_is_found_the_functions_are_listed_the_agents_are_made_and_the_group_is_cleaned_up(self):
        order = [names().index(name) for name in (FIND, LISTING, READY, CLEANUP)]
        self.assertEqual(order, sorted(order))
        self.assertLess(names().index("Work out the settings"), order[0], "after the settings, whose outputs the steps use")
        self.assertLess(order[-1], names().index("What was done"))
        self.assertLess(names().index(STUDY_CLEANUP), order[1], "the steps of the Watch and of the Study are where they were, and these follow them")
        self.assertIn("if: inputs.action == 'cases-run' || inputs.action == 'page-latency' || inputs.action == 'teams-test' || inputs.action == 'study-run' || inputs.action == 'agents-ready'\n", step(FIND))
        self.assertIn("if: inputs.action == 'agents-ready'\n", step(LISTING))
        self.assertIn("if: inputs.action == 'agents-ready'\n", step(READY))
        self.assertIn("id: ready\n", step(READY))
        self.assertIn("if: always() && steps.ready.outcome != 'skipped'\n", step(CLEANUP), "the second line behind the tool's own delete runs when the run was cancelled too, and only when the step started")
        self.assertIn("if: inputs.action == 'cases-run'\n", step(WATCH), "the step of the Watch is not shared: its pins hold")

    def test_no_other_step_runs_for_the_action_and_the_gate_of_ci_runs_for_every_action(self):
        runs_for_it = [title for title, body in blocks() if "inputs.action == 'agents-ready'" in body.split("        run: |")[0]]
        self.assertEqual(runs_for_it, [FIND, LISTING, READY])
        self.assertNotIn("        if:", step(CI).split("        env:")[0], "the same gate as every action: the Hub does not run until CI has passed for this commit")
        self.assertNotIn("agents-ready", step(CI))

    def test_the_listing_is_a_read_from_the_runner(self):
        script = code_of(LISTING)
        self.assertIn('python3 tools/cases-check.py functions --site "$site" --minutes 5', script)
        self.assertIn("SITE_NAME: ${{ steps.params.outputs.cases_function_app_name }}", step(LISTING))
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")

    def test_the_step_runs_the_generic_container_script_and_the_two_files_of_the_watch_with_a_command_of_its_own(self):
        block, script = step(READY), code_of(READY)
        self.assertIn('python3 tools/operator-run.py run --resource-group "$ENV_RESOURCE_GROUP" --name "op-ready-$GITHUB_RUN_ID"', script)
        for word in ('--subnet-id "$OPERATOR_SUBNET_ID"', '--identity-id "$OPERATOR_IDENTITY_ID"', '--image "$OPERATOR_IMAGE"', "--script operator/run-tool.sh", '"${dns[@]}"', '--summary "$GITHUB_STEP_SUMMARY"',
                     '--env "GITHUB_ACTIONS=true"', '--env "OPERATOR_CLIENT_ID=$OPERATOR_CLIENT_ID"', '--env "OPERATOR_SUBSCRIPTION=$ENV_SUBSCRIPTION_ID"',
                     "for server in ${ENV_DNS_SERVERS//,/ }; do dns+=(--dns-server \"$server\"); done"):
            self.assertIn(word, script, word)
        self.assertEqual(re.findall(r'--secret-file "([^"=]+)=tools/([^"]+)"', script), [("cases-check.py", "cases-check.py"), ("check-helpers.py", "check-helpers.py")], "the files of the Watch's step, and no new one")
        self.assertEqual(len(re.findall(r"--secret-file", script)), 2)
        self.assertIn('--env "TOOL_NAME=cases-check"', script)
        args = re.search(r'TOOL_ARGS=([^"]+)"', script).group(1)
        self.assertEqual(args, "ready --storage-account $STORAGE_ACCOUNT --insights $insights --minutes 10")
        self.assertNotIn("--counts-only", args, "the command ready has one mode only, and it is the one for a public log")
        env = dict(re.findall(r"(?m)^          (\w+): (.+)$", block.split("        env:\n")[1].split("        run: |")[0]))
        self.assertEqual(env, {"STORAGE_ACCOUNT": "${{ steps.params.outputs.storage_account_name }}", "INSIGHTS_NAME": "${{ steps.params.outputs.appinsights_name }}",
                               "OPERATOR_IDENTITY_ID": "${{ steps.operator.outputs.identity_id }}", "OPERATOR_CLIENT_ID": "${{ steps.operator.outputs.client_id }}",
                               "OPERATOR_SUBNET_ID": "${{ steps.operator.outputs.subnet_id }}"})
        for word in ("--secure-env", "--allow-tag", "get-access-token", "listSecrets", "az account", "--auth-mode", "secrets."):
            self.assertNotIn(word, block, word)

    def test_the_times_are_ordered_the_tool_waits_less_than_the_group_lives_and_the_group_less_than_the_step(self):
        script, block = code_of(READY), step(READY)
        waits = int(re.search(r"--minutes (\d+)", re.search(r'TOOL_ARGS=([^"]+)"', script).group(1)).group(1))
        seconds = int(re.search(r"--timeout-seconds (\d+)", script).group(1))
        minutes = int(re.search(r"(?m)^        timeout-minutes: (\d+)$", block).group(1))
        self.assertEqual((waits, seconds, minutes), (10, 900, 25))
        self.assertLess(waits * 60, seconds)
        self.assertLess(seconds, minutes * 60)

    def test_the_arguments_fit_the_strict_pattern_of_the_container_script_and_the_tool_has_the_command(self):
        runner = (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")
        pattern = re.search(r"argument_characters='([^']+)'", runner).group(1)
        command_word = re.search(r"command_word='([^']+)'", runner).group(1)
        args = re.search(r'TOOL_ARGS=([^"]+)"', code_of(READY)).group(1).replace("$STORAGE_ACCOUNT", "stmeternautfn0a1b2c3d").replace("$insights", "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-x/providers/Microsoft.Insights/components/appi-x")
        self.assertNotIn("$", args)
        self.assertRegex(args, pattern)
        self.assertLessEqual(len(args), 600)
        self.assertRegex(args.split()[0], command_word)
        tool = (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8")
        self.assertIn('commands.add_parser("ready"', tool)
        for loaded in re.findall(r'with_name\("([^"]+)"\)', tool):
            self.assertIn(loaded, ("check-helpers.py",), "everything that the tool loads from its own folder is sent")

    def test_the_runner_starts_nothing_and_reads_no_telemetry_it_lists_the_functions_and_the_operator_does_the_rest(self):
        code = "\n".join(line for title in (LISTING, READY, CLEANUP) for line in code_of(title).splitlines())
        self.assertNotRegex(code, r"python3 tools/(check-helpers|cases-check)\.py (run|study|ready)\b", "no command of a check tool that sends a message runs on the runner")
        for word in ("storage.azure.com", "/messages?", "servicebus.windows.net", "queue.core.windows.net", "az monitor", "api.applicationinsights.io"):
            self.assertNotIn(word, code, word)

    def test_the_cleanup_deletes_only_the_groups_of_this_action_through_the_tool_and_it_cannot_take_a_group_of_another_check(self):
        script = code_of(CLEANUP)
        self.assertIn('python3 tools/operator-run.py cleanup --resource-group "$ENV_RESOURCE_GROUP" --prefix op-ready- --older-than-minutes 0', script)
        self.assertIn("::warning::", script)
        self.assertNotIn("delete", script.replace("deletes", ""), "the tool deletes, not a command of the step")
        self.assertIn('--name "op-ready-$GITHUB_RUN_ID"', code_of(READY), "the prefix of the cleanup is the start of the name that the step gives its group")
        others = re.findall(r'--name "(op-[a-z]+-)\$GITHUB_RUN_ID"', WORKFLOW)
        self.assertEqual(others.count("op-ready-"), 1)
        for other in set(others) - {"op-ready-"}:
            self.assertFalse(other.startswith("op-ready-") or "op-ready-".startswith(other), f"neither cleanup can take the groups of the other: {other}")

    def test_the_lint_of_the_hub_passes_with_the_new_steps(self):
        self.assertEqual(wl.lint_file(WORKFLOW_PATH), [])


class TheSummariesSayWhatWasDoneAndWhatIsNotProved(unittest.TestCase):
    def test_the_summaries_say_where_the_work_was_done_what_to_check_and_what_a_version_that_exists_is_not(self):
        block = step("What was done")
        failed, finished = re.findall(r"(?m)^\s+agents-ready\) echo \"(.*?)\" ;;$", block)
        for words in ("A container group named \\`op-ready-$GITHUB_RUN_ID\\` may have been made, and the last step of the run deletes it if the tool could not.",
                      "this runner put nothing in the queue and read no telemetry.", "\\`operator\\` has to be run first", "the app does not know the job", "run \\`cases\\`",
                      "\\`switch\\` means that a switch stops the agents", "\\`lock-differs\\` means that the definition that the app's code and settings give is not the one in the lock, so nothing was made from it",
                      "\\`definition\\` means that the stored definition differs from the lock (\\`agents-drift\\` says which control)", "\\`service\\` means that the Foundry project gave no answer or refused",
                      "Nothing in the estate was changed", "Running \\`agents-ready\\` again is safe."):
            self.assertIn(words, failed, words)
        for words in ("The Operator, from inside the network, put the control message of the job ready in the queue and read the telemetry, with its own identity and no key; this runner put nothing in the queue",
                      "That proves that the versions are stored and equal the lock, and nothing about how they answer", "a version that exists is not a promoted one, because a run uses the latest version of each agent and nothing splits the traffic",
                      "The job called no model, read nothing of the estate and changed nothing in it.", "What comes next is \\`foundry-evals\\` on this version, and then \\`cases-run\\`.",
                      "A rollback is the old definition put back in the lock and this action run again, which makes a new version with the old definition; a real run that already used a bad version cannot be taken back."):
            self.assertIn(words, finished, words)
        self.assertEqual(len(re.findall(r"(?m)^\s+agents-ready\) echo ", block)), 2)
        cases = re.findall(r"(?m)^\s+cases\) echo \"(.*?)\" ;;$", block)[1]
        self.assertTrue(cases.endswith("The stored versions of the three agents are made from the lock by the action \\`agents-ready\\`, which a release runs next, before \\`foundry-evals\\` and \\`cases-run\\`."), cases[-200:])
        evals = re.findall(r"(?m)^\s+foundry-evals\) echo \"(.*?)\" ;;$", block)[0]
        self.assertIn("a stored Investigator that is not what the lock says (nothing was run: run \\`agents-ready\\` first, which makes the version from the lock)", evals)


if __name__ == "__main__":
    unittest.main()
