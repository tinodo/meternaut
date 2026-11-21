"""The actions agents-drift, foundry-evals, foundry-redteam and agent365-check of the deploy workflow (.github/workflows/deploy-hub.yml): what runs for each, in what order, what the Operator is given,
and that the arguments are the ones that tools/operator-run.py and operator/run-tool.sh accept, with the files that each tool needs in its flat secret volume.

The step blocks of these actions are pasted into the workflow at integration (the infrastructure builder owns that file), so every test here is skipped until the first of them is there and runs
from then on. The shell of each step is run with bash against stand-ins first on the PATH: the Azure CLI (for the step that finds the Operator) and python3 (which the steps call for
tools/operator-run.py and which records its arguments). No test calls Azure."""
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
ACCOUNT = "aif-meternaut-agents-0123abcd"
GATEWAY_HOST = "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com"
OPERATOR_CLIENT = "99999999-8888-7777-6666-555555555555"
IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"
ENDPOINT = f"https://{ACCOUNT}.services.ai.azure.com/api/projects/meternaut"
IMAGE = "mcr.microsoft.com/azure-cli@sha256:" + "0" * 64

FIND = "Find the Operator, which runs the AI security checks from inside the network"
HOST = "Read the host name of the AI Gateway from the service, for the drift check"
DRIFT = "Run the drift check of the agents in the Operator"
EVALS = "Run the evaluations of the Investigator in the Operator"
REDTEAM = "Run the red team on a synthetic copy of the Investigator in the Operator"
AGENT365 = "Check Agent 365 and Microsoft Entra Agent ID in the Operator"
CLEANUP = "Delete any container group of the AI security checks that is left"
ORDER = [FIND, HOST, DRIFT, EVALS, REDTEAM, AGENT365, CLEANUP, "What was done"]
ACTIONS = {DRIFT: "agents-drift", EVALS: "foundry-evals", REDTEAM: "foundry-redteam", AGENT365: "agent365-check"}
PASTED = f"      - name: {FIND}\n" in WORKFLOW
NOT_YET = "the step blocks of the AI security are not in the workflow yet: they are pasted at integration"


def find_bash():
    for candidate in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def step(name):
    block = re.search(rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", WORKFLOW)
    assert block, name
    return block.group(0)


def script_of(name):
    run = re.search(r"(?ms)^        run: \|\n(.*)", step(name))
    assert run, name
    return textwrap.dedent(run.group(1))


def run_script(name, stand_ins, env):
    """The `run:` script of a step, run with bash as the runner does. Returns the process, the lines that the stand-ins logged and the text that the step added to its output file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for command, body in stand_ins.items():
            path = bin_dir / command
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        script = tmp / "step.sh"
        script.write_text(script_of(name), encoding="utf-8", newline="\n")
        log = tmp / "log.txt"
        log.write_text("", encoding="utf-8")
        (tmp / "out.txt").write_text("", encoding="utf-8")
        full = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": log.as_posix(), "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(),
                "GITHUB_STEP_SUMMARY": (tmp / "summary.md").as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env}
        done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=full, cwd=ROOT)
        return done, log.read_text(encoding="utf-8").splitlines(), (tmp / "out.txt").read_text(encoding="utf-8")


PYTHON = '#!/bin/bash\n{ echo "python3"; printf \'arg:%s\\n\' "$@"; } >> "$FAKE_LOG"\nexit "${FAKE_EXIT:-0}"\n'

ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "GITHUB_RUN_ID": "12345", "ACTION": "agents-drift", "FOUNDRY_ENDPOINT": ENDPOINT, "FOUNDRY_ACCOUNT": ACCOUNT,
       "GATEWAY_HOST": GATEWAY_HOST, "GATEWAY_NAME": "aigw-meternaut-0123abcd", "OPERATOR_IDENTITY_ID": IDENTITY, "OPERATOR_CLIENT_ID": OPERATOR_CLIENT, "OPERATOR_SUBNET_ID": SUBNET,
       "OPERATOR_IMAGE": IMAGE, "ENV_DNS_SERVERS": "10.20.0.4,10.20.0.5", "EVALS_COMMAND": "probe", "EVALS_JUDGE": "none", "EVALS_ONLY": "", "REDTEAM_MODE": "auto"}

FIND_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) printf '%s' "$FAKE_IDENTITY" ;;
  *"/userAssignedIdentities/"*) printf '%s' "$FAKE_CLIENT" ;;
  *"/subnets/snet-ops"*)
    case "$FAKE_SUBNET" in
      ok) echo snet-ops ;;
      absent) echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops' was not found." >&2; exit 1 ;;
      *) echo "$FAKE_SUBNET" >&2; exit 1 ;;
    esac ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""


def operator_run():
    spec = importlib.util.spec_from_file_location("operator_run_of_the_aisec_tests", ROOT / "tools" / "operator-run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(PASTED, NOT_YET)
class TheActionsAreOfferedAndTheStepsFollowTheOrder(unittest.TestCase):
    def test_the_four_actions_are_the_last_of_the_options_and_the_description_says_what_each_does(self):
        options = re.search(r"(?ms)^      action:\n(.*?)^      \w", WORKFLOW).group(1)
        listed = re.findall(r"^          - (\S+)$", options, re.M)
        self.assertEqual(listed[-4:], ["agents-drift", "foundry-evals", "foundry-redteam", "agent365-check"], "the four actions of the agents' checks are the last of the options")
        self.assertIn("aigateway-check", listed[:-4])
        description = re.search(r'(?m)^        description: "(what-if: .*)"$', options).group(1)
        for action in ("agents-drift", "foundry-evals", "foundry-redteam", "agent365-check"):
            self.assertIn(f" {action}: ", description, action)
        self.assertIn("never the production agent", description)

    def test_the_three_inputs_are_choices_with_the_safe_default(self):
        for name, default, options in (("evals_command", "probe", ["probe", "run", "rule", "rule-apply"]), ("evals_judge", "none", ["none", "connection", "auto"]),
                                       ("redteam_mode", "auto", ["auto", "cloud", "dataset"])):
            block = re.search(rf"(?ms)^      {name}:\n(.*?)(?=^      \w|^\w)", WORKFLOW).group(1)
            self.assertIn("        type: choice\n", block, name)
            self.assertIn("        required: false\n", block, name)
            self.assertIn(f"        default: {default}\n", block, name)
            self.assertEqual(re.findall(r"^          - (\S+)$", block, re.M), options, name)
            self.assertIn("Every other action ignores it.", block, name)

    def test_the_input_evals_only_is_an_optional_string_that_names_cases_for_the_command_run_and_every_other_action_ignores_it(self):
        block = re.search(r"(?ms)^      evals_only:\n(.*?)(?=^      \w|^\w)", WORKFLOW).group(1)
        for line in ("        type: string\n", "        required: false\n", '        default: ""\n'):
            self.assertIn(line, block)
        self.assertNotIn("options:", block, "the ids are free text, so the step checks them (a choice would hold only the ids that the workflow lists, and the set of cases is the file's)")
        for words in ("Only with foundry-evals and evals_command run", "separated by commas", "letters, digits and hyphens", "at most 80 characters", "Every other action ignores it."):
            self.assertIn(words, block)
        self.assertIn("EVALS_ONLY: ${{ inputs.evals_only }}", step(EVALS), "the value reaches the script through the environment, never through an expression in the script")
        self.assertEqual(WORKFLOW.count("inputs.evals_only"), 1)

    def test_the_steps_come_in_the_order_of_the_checks_and_before_the_summary(self):
        names = re.findall(r"(?m)^      - name: (.*)$", WORKFLOW)
        positions = [names.index(name) for name in ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(positions[-1], len(names) - 1, "the summary is the last step")
        self.assertLess(names.index("Delete any container group of the AI Gateway check that is left"), positions[0])

    def test_each_step_runs_for_its_own_action_alone_and_the_cleanup_for_the_four(self):
        for name, action in ACTIONS.items():
            self.assertRegex(step(name), rf"(?m)^        if: inputs\.action == '{action}'$", name)
        self.assertRegex(step(HOST), r"(?m)^        if: inputs\.action == 'agents-drift'$")
        for name in (FIND, CLEANUP):
            block = step(name)
            for action in ACTIONS.values():
                self.assertIn(f"inputs.action == '{action}'", block, (name, action))
        self.assertIn("steps.aisec_operator.outcome != 'skipped'", step(CLEANUP))
        self.assertIn("always()", step(CLEANUP))

    def test_no_expression_of_the_workflow_is_written_into_a_script(self):
        for name in ORDER[:-1]:
            self.assertNotIn("${{", script_of(name), name)


@unittest.skipUnless(PASTED, NOT_YET)
@unittest.skipIf(BASH is None, "no bash on this machine")
class TheOperatorIsFoundAndTheToolsAreStartedInIt(unittest.TestCase):
    def find(self, **changes):
        env = {**ENV, "FAKE_IDENTITY": IDENTITY, "FAKE_CLIENT": OPERATOR_CLIENT, "FAKE_SUBNET": "ok", **changes}
        return run_script(FIND, {"az": FIND_AZ}, env)

    def test_the_operator_is_found_by_its_name_and_only_reads_are_made(self):
        done, lines, out = self.find()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(out.splitlines(), [f"identity_id={IDENTITY}", f"client_id={OPERATOR_CLIENT}", f"subnet_id={SUBNET}"])
        self.assertTrue(all(line.startswith("az resource list") or "--method get" in line for line in lines))

    def test_an_operator_that_is_not_there_says_that_operator_is_run_first_and_changes_nothing(self):
        done, _, out = self.find(FAKE_IDENTITY="", FAKE_CLIENT="")
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The identity id-meternaut-operator is not there. The action agents-drift runs its tool in the Operator, so run operator first. Nothing was changed.", done.stdout)
        self.assertEqual(out, "")
        done, _, _ = self.find(FAKE_SUBNET="absent")
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The subnet snet-ops is not there.", done.stdout)
        done, _, _ = self.find(FAKE_SUBNET="ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later.")
        self.assertEqual(done.returncode, 1, "a message that holds the digits 404 inside an id is not 'not found'")
        self.assertIn("::error::The subnet snet-ops could not be read", done.stdout)

    def test_the_host_of_the_gateway_is_read_from_the_service_and_must_be_under_its_domain(self):
        az = '#!/bin/bash\necho "az $*" >> "$FAKE_LOG"\nif [ "$FAKE_FAIL" = "yes" ]; then echo "$FAKE_ANSWER" >&2; exit 1; fi\nprintf \'%s\' "$FAKE_ANSWER"\n'
        done, lines, out = run_script(HOST, {"az": az}, {**ENV, "FAKE_ANSWER": GATEWAY_HOST, "FAKE_FAIL": "no"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(out, f"host={GATEWAY_HOST}\n")
        self.assertEqual(len(lines), 1)
        self.assertIn("Microsoft.ApiManagement/aigateways/aigw-meternaut-0123abcd?api-version=2025-09-01-preview --query properties.frontend.defaultHostname", lines[0])
        for bad in ("", "None", "evil.example.com", f"{GATEWAY_HOST}.evil.example.com", f"https://{GATEWAY_HOST}"):
            done, _, out = run_script(HOST, {"az": az}, {**ENV, "FAKE_ANSWER": bad, "FAKE_FAIL": "no"})
            self.assertEqual(done.returncode, 1, bad)
            self.assertEqual(out, "")

    def cases(self):
        yield DRIFT, {}
        for command in ("probe", "run", "rule", "rule-apply"):
            for judge in ("none", "connection", "auto"):
                yield EVALS, {"EVALS_COMMAND": command, "EVALS_JUDGE": judge}
        yield EVALS, {"EVALS_COMMAND": "run", "EVALS_JUDGE": "none", "EVALS_ONLY": "idle-disk-1,idle-bastion-with-four-units"}
        for mode in ("auto", "cloud", "dataset"):
            yield REDTEAM, {"REDTEAM_MODE": mode}
        yield AGENT365, {}

    def started(self, name, **changes):
        done, lines, _ = run_script(name, {"python3": PYTHON}, {**ENV, **changes})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return [line[len("arg:"):] for line in lines if line.startswith("arg:")]

    def test_each_tool_is_started_with_arguments_that_operator_run_and_the_script_of_the_container_accept(self):
        tool = operator_run()
        run_tool = (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")
        self.assertIn("[A-Za-z0-9 ./:_=-]", run_tool)
        for name, changes in self.cases():
            with self.subTest(step=name, **changes):
                args = self.started(name, **changes)
                self.assertEqual(args[:2], ["tools/operator-run.py", "run"])
                parsed = tool.build_parser().parse_args(args[1:])
                plain, secure, servers = tool.check_options(parsed)
                files = tool.read_files(parsed)
                env = dict(plain)
                self.assertEqual(secure, [], "no secret goes into the container as an environment variable")
                self.assertEqual(env["TOOL_NAME"], ACTIONS[name])
                self.assertEqual(env["GITHUB_ACTIONS"], "true")
                self.assertRegex(env["TOOL_ARGS"], r"^[A-Za-z0-9 ./:_=-]{1,600}$")
                self.assertRegex(env["TOOL_ARGS"].split(" ")[0], r"^[a-z][a-z-]{0,19}$")
                self.assertEqual(parsed.name, "op-aisec-12345")
                self.assertEqual(servers, ["10.20.0.4", "10.20.0.5"])
                self.assertEqual(parsed.script, "operator/run-tool.sh")
                self.assertEqual(parsed.image, IMAGE)
                self.assertIn(f"{ACTIONS[name]}.py", files)
                self.assertIn("aisec-helpers.py", files)

    def test_the_arguments_carry_the_choice_of_the_input_and_nothing_else_of_the_run(self):
        text = next(a for a in self.started(EVALS, EVALS_COMMAND="run", EVALS_JUDGE="auto") if a.startswith("TOOL_ARGS="))
        self.assertEqual(text, f"TOOL_ARGS=run --endpoint {ENDPOINT} --judge auto --wait-seconds 900")
        self.assertIn(f"TOOL_ARGS=rule --endpoint {ENDPOINT} --apply", self.started(EVALS, EVALS_COMMAND="rule-apply"))
        self.assertIn(f"TOOL_ARGS=run --endpoint {ENDPOINT} --mode dataset --wait-seconds 900", self.started(REDTEAM, REDTEAM_MODE="dataset"))
        self.assertIn(f"TOOL_ARGS=run --endpoint {ENDPOINT} --gateway-host {GATEWAY_HOST}", self.started(DRIFT))
        done, _, _ = run_script(EVALS, {"python3": PYTHON}, {**ENV, "EVALS_COMMAND": "delete-everything"})
        self.assertEqual(done.returncode, 1, "a command that is not one of the four is refused before anything is started")
        self.assertIn("::error::evals_command is probe, run, rule or rule-apply. Nothing was changed.", done.stdout)

    def test_the_ids_of_evals_only_reach_the_tool_as_words_of_its_arguments_and_no_comma_reaches_the_container(self):
        run_tool = (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")
        self.assertNotIn(",", re.search(r"argument_characters='\^\[(.*?)\]\+\$'", run_tool).group(1), "the script of the container takes no comma in the arguments, so the step turns the commas into spaces")
        text = next(a for a in self.started(EVALS, EVALS_COMMAND="run", EVALS_JUDGE="none", EVALS_ONLY="idle-disk-1,idle-bastion-with-four-units") if a.startswith("TOOL_ARGS="))
        self.assertEqual(text, f"TOOL_ARGS=run --endpoint {ENDPOINT} --judge none --wait-seconds 900 --only idle-disk-1 idle-bastion-with-four-units")
        self.assertRegex(text, r"^TOOL_ARGS=[A-Za-z0-9 ./:_=-]+$")
        one = next(a for a in self.started(EVALS, EVALS_COMMAND="run", EVALS_JUDGE="connection", EVALS_ONLY="idle-disk-1") if a.startswith("TOOL_ARGS="))
        self.assertEqual(one, f"TOOL_ARGS=run --endpoint {ENDPOINT} --judge connection --wait-seconds 900 --only idle-disk-1")
        plain = next(a for a in self.started(EVALS, EVALS_COMMAND="run", EVALS_JUDGE="none", EVALS_ONLY="") if a.startswith("TOOL_ARGS="))
        self.assertNotIn("--only", plain, "an empty input is every case")

    def test_a_value_of_evals_only_that_is_not_ids_is_refused_before_anything_is_started_and_the_other_commands_ignore_it(self):
        message = "::error::The input evals_only is the ids of invented cases, separated by commas: letters, digits and hyphens, and every id starts and ends with a letter or a digit, at most 80 characters. Nothing was changed."
        for bad in ("idle disk-1", "idle-disk-1;x", "$(id)", "`id`", "idle-disk-1,,idle-addresses", ",idle-disk-1", "idle-disk-1,", ",", "a" * 81, "idle_disk", "idle/disk", "idle.disk",
                    "--judge", "x,--judge,connection", "idle-disk-1,--judge,connection", "-a", "a,-b", "-", "a,-", "a-,b", "a,b-", "--lock,x", "a,--wait-seconds,5", "a,--only"):
            with self.subTest(bad=bad):
                done, lines, _ = run_script(EVALS, {"python3": PYTHON}, {**ENV, "EVALS_COMMAND": "run", "EVALS_ONLY": bad})
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn(message, done.stdout)
                self.assertEqual([line for line in lines if line.startswith("arg:")], [], "nothing was started")
        for good in ("a", "idle-disk-1,idle-addresses", "a" * 80, "A1-b2,C3", "a-b", "a1,b2-c3-d4"):
            with self.subTest(good=good):
                text = next(a for a in self.started(EVALS, EVALS_COMMAND="run", EVALS_ONLY=good) if a.startswith("TOOL_ARGS="))
                self.assertTrue(text.endswith(" --only " + good.replace(",", " ")), text)
        for command in ("probe", "rule", "rule-apply"):
            with self.subTest(command=command):
                args = self.started(EVALS, EVALS_COMMAND=command, EVALS_ONLY="whatever it is; it is ignored")
                self.assertTrue(all("--only" not in a and "whatever" not in a for a in args))

    def test_no_value_of_evals_only_can_set_another_option_of_the_tool_through_the_words_that_it_becomes(self):
        for sneaky in ("idle-disk-1,--judge,connection", "--judge,connection", "idle-disk-1,--lock,x", "idle-disk-1,--wait-seconds,1", "idle-disk-1,--summary,x"):
            with self.subTest(sneaky=sneaky):
                done, lines, _ = run_script(EVALS, {"python3": PYTHON}, {**ENV, "EVALS_COMMAND": "run", "EVALS_JUDGE": "none", "EVALS_ONLY": sneaky})
                self.assertEqual((done.returncode, [line for line in lines if line.startswith("arg:")]), (1, []), "the step stops before the container is started")

    def test_the_grader_of_the_settings_runs_in_the_flat_folder_of_the_secret_volume_where_the_toolbox_is_not(self):
        tool = operator_run()
        code = textwrap.dedent("""
            import importlib.util, json, sys
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("tool", Path.cwd() / "foundry-evals.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            rows = {row["id"]: row for row in (json.loads(line) for line in Path("cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
            answer = sys.stdin.read()
            change = {"action": "reduce", "effects": [{"handle": "r1", "meters": ["m2"], "remains": {"form": "quantity", "from": 1440, "to": 0}}], "how": "Take the extra units away.",
                      "set": [{"handle": "r1", "property": "scaleUnits", "from": 4, "to": 2}]}
            story = json.dumps({"findings": [{"handles": ["r1"], "basis": "oversized", "proposal": "change", "metric_evidence": [], "change": change, "confidence": 0.8, "summary": "x"}], "examined": []})

            def lowered(to):
                lowering = {**change, "set": [{"handle": "r1", "property": "scaleUnits", "from": 4, "to": to}]}
                return json.dumps({"findings": [{"handles": ["r1"], "basis": "oversized", "proposal": "change", "metric_evidence": [], "change": lowering, "confidence": 0.8, "summary": "x"}], "examined": []})
            print(json.dumps({"light": module.grade(rows["lightly-used-bastion-with-four-units"], answer), "busy": module.grade(rows["busy-bastion-with-four-units"], answer),
                              "story": module.grade(rows["bastion-four-units-full-story"], story).get("priced"), "toolbox": hasattr(sys.modules.get("cases_flat.toolbox"), "__file__"),
                              "floor": [module.grade(rows["bastion-four-units-floor-in-docs"], lowered(to)).get("set_found") for to in (1, 2, 3)]}))
        """)
        change = {"action": "reduce", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "ratio", "on": "scaleUnits", "from": 4, "to": 2}}], "how": "Fewer units.",
                  "set": [{"handle": "r1", "property": "scaleUnits", "from": 4, "to": 2}], "others": [{"title": "Use a smaller tier", "gives_up": "Fewer features.", "in_place": False, "change": {
                      "action": "switch", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "assumed", "low": 0.2, "high": 0.4}}]}}]}
        answer = json.dumps({"findings": [{"handles": ["r1"], "basis": "oversized", "proposal": "change", "metric_evidence": [], "change": change, "confidence": 0.8, "summary": "x"}], "examined": []})
        parsed = tool.build_parser().parse_args(self.started(EVALS, EVALS_COMMAND="run", EVALS_JUDGE="none")[1:])
        with tempfile.TemporaryDirectory() as tmp:
            for pair in parsed.secret_file:
                file_name, path = pair.split("=", 1)
                shutil.copyfile(ROOT / path, Path(tmp) / file_name)
            self.assertFalse((Path(tmp) / "toolbox.py").exists(), "the volume does not hold the toolbox: it is 230 KB and reads half of the app")
            done = subprocess.run([sys.executable, "-c", code], cwd=tmp, input=answer, capture_output=True, text=True, env={**os.environ, "GITHUB_ACTIONS": "true"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        found = json.loads(done.stdout.splitlines()[-1])
        self.assertEqual((found["light"]["set_found"], found["light"]["settings"], found["light"]["ways"], found["light"]["decoys"]), (1.0, 1, 1, 0))
        self.assertEqual((found["busy"]["settings"], found["busy"]["decoys"]), (1, 1), "the same answer on the host that is in use is a decoy")
        self.assertEqual(found["story"], {"set": {"low": 201.6, "high": 201.6}, "others": []}, "the price of the change is the app's own pricing.py over the meters of the row, with no toolbox in the folder")
        self.assertFalse(found["toolbox"], "what stands in for the toolbox is made by the tool and is no file")
        self.assertEqual(found["floor"], [0.0, 1.0, 1.0], "the floor of the row of the documentation is held in the flat folder too: 1 is below it, 2 and 3 are not")

    def test_the_two_that_spend_are_given_their_caps_and_the_container_outlives_the_cap_on_seconds(self):
        tool = operator_run()
        limits = json.loads((ROOT / "evaluation" / "limits.json").read_text(encoding="utf-8"))
        for name, needed in ((EVALS, {"cases.jsonl"}), (REDTEAM, {"investigator-instructions.txt", "redteam-prompts.jsonl"})):
            parsed = tool.build_parser().parse_args(self.started(name, EVALS_COMMAND="run", REDTEAM_MODE="auto")[1:])
            names = {pair.split("=", 1)[0] for pair in parsed.secret_file}
            self.assertLessEqual({"limits.json", "thresholds.json", "agents.lock.json"} | needed, names, name)
            self.assertGreater(parsed.timeout_seconds, limits["maxSeconds"], "the container outlives the tool's own cap, so that the tool says why it stopped")
            self.assertLessEqual(parsed.timeout_seconds, 3600)

    def test_each_tool_finds_every_file_that_it_needs_in_the_flat_folder_of_its_secret_volume(self):
        tool = operator_run()
        code = textwrap.dedent("""
            import importlib.util, sys
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("tool", Path.cwd() / (sys.argv[1] + ".py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            helpers = sys.modules["aisec_helpers"]
            class Stop:
                calls = []
                def request(self, method, path, body=None, **options):
                    raise helpers.Problem("STOP: every file was found, and this is the first call to the project: " + method + " " + path.split("?")[0], 1)
            print("code", module.main(sys.argv[2:] + ["--endpoint", "%s"], client=Stop()))
        """ % ENDPOINT)
        wanted = {DRIFT: ["run"], EVALS: ["run", "--judge", "none"], REDTEAM: ["run", "--mode", "auto"]}
        for name, extra in wanted.items():
            with self.subTest(tool=ACTIONS[name]):
                parsed = tool.build_parser().parse_args(self.started(name, EVALS_COMMAND="run", REDTEAM_MODE="auto")[1:])
                with tempfile.TemporaryDirectory() as tmp:
                    for pair in parsed.secret_file:
                        file_name, path = pair.split("=", 1)
                        shutil.copyfile(ROOT / path, Path(tmp) / file_name)
                    done = subprocess.run([sys.executable, "-c", code, ACTIONS[name], *extra], cwd=tmp, capture_output=True, text=True, env={**os.environ, "GITHUB_ACTIONS": "true"})
                self.assertIn("every file was found", done.stdout + done.stderr, done.stdout + done.stderr)

    def test_a_cleanup_that_fails_is_a_warning_and_never_an_error_and_it_deletes_the_groups_of_these_checks_alone(self):
        done, lines, _ = run_script(CLEANUP, {"python3": PYTHON}, ENV)
        self.assertEqual(done.returncode, 0)
        self.assertEqual([line[len("arg:"):] for line in lines if line.startswith("arg:")], ["tools/operator-run.py", "cleanup", "--resource-group", GROUP, "--prefix", "op-aisec-", "--older-than-minutes", "0"])
        done, _, _ = run_script(CLEANUP, {"python3": PYTHON}, {**ENV, "FAKE_EXIT": "1"})
        self.assertEqual(done.returncode, 0, "a cleanup that fails does not fail a run that passed")
        self.assertIn(f"::warning::A container group whose name starts with op-aisec- may be left in resource group {GROUP}.", done.stdout)


if __name__ == "__main__":
    unittest.main()
