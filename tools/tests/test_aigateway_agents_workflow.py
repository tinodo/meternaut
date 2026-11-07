"""The route of the agents through the AI Gateway in the deploy workflow (.github/workflows/deploy-hub.yml), step 2 of docs/proposals/08-ai-gateway.md: what the steps read and say while the switch
AGENTS_VIA_AI_GATEWAY is on, and that they read and say nothing more while it is off.

The shell of each step is run with bash against stand-ins for the commands that it calls first on the PATH: the Azure CLI and python3 (which the steps call for the parameter builder and the tools). No
test calls Azure."""
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

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
GATEWAY = "aigw-meternaut-0123abcd"
HOST = f"{GATEWAY}.swedencentral.ai.gateway.azure.com"
ACCOUNT = "aif-meternaut-agents-0123abcd"
PROJECT = "meternaut"
PROJECT_PRINCIPAL = "3b9e2f81-6c4d-4a7e-8f10-2d5a9c7b1e44"
CASES_PRINCIPAL = "7d3c1f52-3b0a-4f6e-9a55-0c1f5f2b9d11"
GATEWAY_PRINCIPAL = "5a1c0de0-0000-4000-8000-0000000000de"
GATEWAY_CLIENT = "11111111-2222-3333-4444-555555555555"
HOSTILE = "ERROR: (AuthorizationFailed) The client '40404040-4040-4040-4040-404040404040' with object id 'a404b404-0000-0000-0000-000000000404' does not have authorization"
GATEWAY_URL = (f"az rest --method get --url https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ApiManagement/aigateways/{GATEWAY}"
               "?api-version=2025-09-01-preview --query properties.frontend.defaultHostname --output tsv")
PROJECT_URL = (f"az rest --method get --url https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}"
               f"/projects/{PROJECT}?api-version=2025-06-01 --query identity.principalId --output tsv")
CONNECTION_URL = (f"az rest --method get --url https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}"
                  f"/projects/{PROJECT}/connections/aigateway?api-version=2026-09-01 --query name --output tsv")

SETTINGS = "Work out the settings"
PRECHECK = "The usage recording is there, which the first cases build on"
FOUNDRY_READ_BACK = "Read the Foundry resource back"
AIGATEWAY_READ_BACK = "Read the AI Gateway back"
SUMMARY = "What was done"


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
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


def run_step(name, stand_ins, env, files=None):
    """Runs the `run:` script of a step with bash, as the runner does, with stand-ins first on the PATH. Returns the process, the lines that the stand-ins logged, what the step wrote to its output file and
    what it wrote to its summary."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for command, body in stand_ins.items():
            path = bin_dir / command
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        for file, content in (files or {}).items():
            (tmp / file).write_text(content, encoding="utf-8", newline="\n")
        script = tmp / "step.sh"
        script.write_text(script_of(name), encoding="utf-8", newline="\n")
        for file in ("log.txt", "out.txt", "summary.md"):
            (tmp / file).write_text("", encoding="utf-8")
        full = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": (tmp / "log.txt").as_posix(), "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(),
                "GITHUB_STEP_SUMMARY": (tmp / "summary.md").as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env}
        done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=full, cwd=ROOT)
        return done, (tmp / "log.txt").read_text(encoding="utf-8").splitlines(), (tmp / "out.txt").read_text(encoding="utf-8"), (tmp / "summary.md").read_text(encoding="utf-8")


SETTINGS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"identity list"*|*"/loggers"*|*"ApiManagement/service"*) echo "the owner's API Management instance and its identity must not be looked at: $*" >&2; exit 8 ;;
  *"/aigateways/"*)
    if [ -n "$FAKE_HOST_ERROR" ]; then echo "$FAKE_HOST_ERROR" >&2; exit 1; fi
    printf '%s' "$FAKE_HOST" ;;
  *"/providers/Microsoft.Web/sites/"*) printf '%s' "$FAKE_SYSTEM" ;;
  *"/projects/"*"--query identity.principalId"*)
    if [ -n "$FAKE_PROJECT_ERROR" ]; then echo "$FAKE_PROJECT_ERROR" >&2; exit 1; fi
    printf '%s' "$FAKE_PROJECT_PRINCIPAL" ;;
  *"/projects/"*"--query name"*) echo meternaut ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

SETTINGS_PYTHON3 = """#!/bin/bash
if [ "$2" = "build" ]; then
  echo "build preview=$([[ " $* " == *" --preview "* ]] && echo yes || echo no) host=[${AIGATEWAY_HOST-unset}] project=[${FOUNDRY_PROJECT_PRINCIPAL_ID-unset}]" >> "$FAKE_LOG"
  echo "principal cases=[${CASES_SYSTEM_PRINCIPAL_ID-unset}]" >> "$FAKE_LOG"
  printf '%s\\n' "$FAKE_BUILD_OUTPUT"
else
  echo "check $*" >> "$FAKE_LOG"
fi
"""

BUILD_OFF = "\n".join([f"cases_function_app_name=func-meternaut-cases-0123abcd", f"foundry_account_name={ACCOUNT}", f"foundry_project_name={PROJECT}", f"aigateway_name={GATEWAY}"])
BUILD_ON = BUILD_OFF + "\nagents_via_ai_gateway=true\naigateway_connection_name=aigateway"


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheSettingsStepReadsWhatTheSwitchNeedsAndNothingWhileItIsOff(unittest.TestCase):
    def settings(self, action, build=BUILD_ON, **changes):
        env = {"ACTION": action, "ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "FAKE_BUILD_OUTPUT": build,
               "FAKE_HOST": HOST, "FAKE_PROJECT_PRINCIPAL": PROJECT_PRINCIPAL, "FAKE_SYSTEM": CASES_PRINCIPAL, **changes}
        return run_step(SETTINGS, {"az": SETTINGS_AZ, "python3": SETTINGS_PYTHON3}, env)

    def builds(self, lines):
        return [line for line in lines if line.startswith("build ")]

    def final_preview(self, action):
        """Only the first pass of the step is a preview: no action looks for the identity of a gateway of the owner's API Management instance any more, so the final build is a plain one for every action."""
        return "no"

    def mine(self, lines):
        return [line for line in lines if "/aigateways/" in line or "--query identity.principalId" in line and "/projects/" in line or "/connections/" in line]

    def test_while_the_switch_is_off_the_actions_that_have_nothing_to_do_with_the_gateway_read_nothing_of_it_and_the_builder_gets_it_empty(self):
        # The action foundry reads the host name only while the switch is on, and aigateway reads the project's identity only then; the other actions read neither. (cases and what-if read the host
        # whatever the switch says: they are in the next tests.)
        for action in ("foundry", "aigateway", "recording", "operator", "plant", "model-side", "cases-run", "aigateway-check"):
            with self.subTest(action=action):
                done, lines, out, _ = self.settings(action, build=BUILD_OFF)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(self.mine(lines), [])
                self.assertEqual(self.builds(lines), ["build preview=yes host=[unset] project=[unset]", f"build preview={self.final_preview(action)} host=[] project=[]"], "empty, which the builder reads as not given")
                self.assertIn("aigateway_host=\n", out)
                self.assertIn("foundry_project_principal=\n", out)
                self.assertNotIn("host name of the AI Gateway", done.stdout + done.stderr)
                self.assertNotIn("Foundry project's system-assigned identity", done.stdout + done.stderr)

    def test_the_action_cases_reads_the_host_name_of_the_gateway_whether_the_switch_is_on_or_off_and_hands_it_to_the_builder(self):
        # Every model call of the cases app goes through the AI Gateway (AGENTS.md rule 15 (c)), so the app is made only with the gateway's host name, read from the service and never made up.
        for build in (BUILD_OFF, BUILD_ON):
            with self.subTest(switch="on" if build == BUILD_ON else "off"):
                done, lines, out, _ = self.settings("cases", build=build)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual([line for line in lines if "/aigateways/" in line], [GATEWAY_URL])
                self.assertEqual(self.builds(lines)[1], f"build preview=no host=[{HOST}] project=[]", "the host goes to the builder; cases does not look for the project's identity")
                self.assertIn(f"aigateway_host={HOST}\n", out)
                self.assertIn(f"The service reports the host name of the AI Gateway {GATEWAY}; it goes into the cases file (and into the Foundry file while the switch is on).", done.stdout)
                self.assertNotIn(HOST, done.stdout + done.stderr, "the host name is an output and is not printed")
                self.assertEqual([line for line in lines if "--query identity.principalId" in line and "/projects/" in line], [])

    def test_a_gateway_that_is_not_there_stops_the_action_cases_at_once_and_nothing_is_built_after_it_whether_the_switch_is_on_or_off(self):
        for build in (BUILD_OFF, BUILD_ON):
            for answer in ("ERROR: (ResourceNotFound) The Resource 'Microsoft.ApiManagement/aigateways/x' was not found.", 'ERROR: Not Found({"error":{"code":"NotFound"}})', "ERROR: the request failed with status 404"):
                with self.subTest(switch="on" if build == BUILD_ON else "off", answer=answer[:30]):
                    done, lines, out, _ = self.settings("cases", build=build, FAKE_HOST_ERROR=answer)
                    self.assertNotEqual(done.returncode, 0)
                    said = done.stdout + done.stderr
                    self.assertIn(f"::error::The AI Gateway {GATEWAY} is not in Azure or has not reported its host name. Every model call of the cases app goes through it, so the Detective and the Skeptic have "
                                  "no route without it and the action cases does not deploy the app. Run aigateway first (the order is in environment/BOOTSTRAP.md). Nothing was changed.", said)
                    self.assertEqual(self.builds(lines), ["build preview=yes host=[unset] project=[unset]"], "the final files are not made")
                    self.assertEqual([line for line in lines if line.startswith("check ")], [])
        for answer in ("", "None", "evil.example.com", f"{HOST}.evil.example.com", f"https://{HOST}", HOST.upper(), f"{HOST}/default"):
            with self.subTest(answer=answer):
                done, lines, out, _ = self.settings("cases", build=BUILD_OFF, FAKE_HOST=answer)
                self.assertNotEqual(done.returncode, 0, answer)
                self.assertIn("is not in Azure or has not reported its host name. Every model call of the cases app goes through it", done.stdout + done.stderr)
                self.assertNotIn("aigateway_host=", out)
        done, lines, _, _ = self.settings("cases", build=BUILD_OFF, FAKE_HOST_ERROR=HOSTILE)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(f"::error::The AI Gateway {GATEWAY} could not be read: {HOSTILE}", done.stdout + done.stderr)
        self.assertNotIn("Run aigateway first", done.stdout + done.stderr, "a read that failed for another reason is no 'not found'")

    def test_what_if_previews_the_cases_app_with_a_placeholder_when_the_gateway_is_not_there_and_does_not_stop(self):
        for build in (BUILD_OFF, BUILD_ON):
            with self.subTest(switch="on" if build == BUILD_ON else "off"):
                done, lines, out, _ = self.settings("what-if", build=build, FAKE_HOST="")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(f"::warning::The preview of the cases app holds a placeholder for the host name of the AI Gateway, because the gateway {GATEWAY} is not in Azure or has not reported its host name "
                              "(run aigateway first).", done.stdout + done.stderr)
                self.assertNotIn("::error::", done.stdout + done.stderr)
                self.assertEqual(self.builds(lines)[1], "build preview=no host=[] project=[" + (PROJECT_PRINCIPAL if build == BUILD_ON else "") + "]", "no host: the builder uses its placeholder")
                done, lines, out, _ = self.settings("what-if", build=build, FAKE_HOST_ERROR=HOSTILE)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(f"::warning::The AI Gateway {GATEWAY} could not be read: {HOSTILE}", done.stdout + done.stderr)
                done, lines, out, _ = self.settings("what-if", build=build)
                self.assertEqual(self.builds(lines)[1], "build preview=no host=[" + HOST + "] project=[" + (PROJECT_PRINCIPAL if build == BUILD_ON else "") + "]", "the real host when the gateway is there")

    def test_the_cases_apps_identity_is_read_by_what_if_foundry_and_aigateway_whether_the_switch_is_on_or_off_and_by_no_other_action(self):
        # The one object id serves the Foundry file (Foundry User on the project) and the AI Gateway file (AI Gateway Models User on the gateway). An app that does not exist yet is no error: the
        # gateway is then made without the role, and the next run gives it.
        for build in (BUILD_OFF, BUILD_ON):
            for action in ("what-if", "foundry", "aigateway"):
                with self.subTest(switch="on" if build == BUILD_ON else "off", action=action):
                    done, lines, out, _ = self.settings(action, build=build)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(lines.count(f"principal cases=[{CASES_PRINCIPAL}]"), 1, "the final build is given it, and the first, preview build is not")
                    self.assertIn(f"cases_app_principal={CASES_PRINCIPAL}\n", out)
                    self.assertIn("its principal id goes into the Foundry file and the AI Gateway file.", done.stdout)
                    done, lines, out, _ = self.settings(action, build=build, FAKE_SYSTEM="")
                    self.assertEqual(done.returncode, 0, "an app with no identity yet is no error")
                    self.assertIn("cases_app_principal=\n", out)
                    self.assertIn("the Foundry file holds a placeholder and the AI Gateway file gives no role to the app.", done.stdout)
            for action in ("cases", "recording", "operator", "plant", "model-side", "cases-run"):
                with self.subTest(switch="on" if build == BUILD_ON else "off", action=action, reads="no"):
                    done, lines, out, _ = self.settings(action, build=build)
                    self.assertEqual([line for line in lines if "/providers/Microsoft.Web/sites/" in line], [], "the action does not look for the app's identity")
                    self.assertIn("cases_app_principal=\n", out)

    def test_foundry_reads_the_host_name_from_the_service_with_the_version_that_the_check_uses_and_hands_it_to_the_builder(self):
        done, lines, out, _ = self.settings("foundry")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([line for line in lines if "/aigateways/" in line], [GATEWAY_URL])
        self.assertEqual(self.builds(lines)[1], f"build preview=no host=[{HOST}] project=[]", "foundry does not look for the project's identity")
        self.assertIn(f"aigateway_host={HOST}\n", out)
        self.assertIn("foundry_project_principal=\n", out)
        self.assertIn(f"The service reports the host name of the AI Gateway {GATEWAY}; it goes into the cases file (and into the Foundry file while the switch is on).", done.stdout)
        self.assertNotIn(HOST, done.stdout + done.stderr, "the host name is an output and is not printed")
        self.assertEqual([line for line in lines if "--query identity.principalId" in line and "/projects/" in line], [], "foundry does not read the project's identity")

    def test_aigateway_reads_the_object_id_of_the_projects_identity_and_hands_it_to_the_builder_and_reads_no_gateway(self):
        done, lines, out, _ = self.settings("aigateway")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([line for line in lines if "/projects/" in line], [PROJECT_URL])
        self.assertEqual([line for line in lines if "/aigateways/" in line], [])
        self.assertEqual(self.builds(lines)[1], f"build preview=no host=[] project=[{PROJECT_PRINCIPAL}]")
        self.assertIn(f"foundry_project_principal={PROJECT_PRINCIPAL}\n", out)
        self.assertIn("The Foundry project's system-assigned identity exists; its object id goes into the AI Gateway file.", done.stdout)

    def test_what_if_reads_both_and_every_other_action_reads_neither_so_that_a_read_that_is_refused_cannot_stop_it(self):
        done, lines, out, _ = self.settings("what-if")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.builds(lines)[1], f"build preview=no host=[{HOST}] project=[{PROJECT_PRINCIPAL}]")
        for action in ("cases-run", "recording", "recording-check", "operator", "operator-probe", "plant", "loop-check", "model-side", "aigateway-check"):
            with self.subTest(action=action):
                done, lines, out, _ = self.settings(action, FAKE_HOST_ERROR=HOSTILE, FAKE_PROJECT_ERROR=HOSTILE)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual([line for line in lines if "/aigateways/" in line], [])
                self.assertEqual([line for line in lines if "--query identity.principalId" in line and "/projects/" in line], [])
                self.assertEqual(self.builds(lines)[1], f"build preview={self.final_preview(action)} host=[] project=[]")

    def test_a_gateway_that_is_not_there_stops_foundry_at_once_and_says_what_to_run_first_and_nothing_is_built_after_it(self):
        for answer in ("ERROR: (ResourceNotFound) The Resource 'Microsoft.ApiManagement/aigateways/x' was not found.", 'ERROR: Not Found({"error":{"code":"NotFound"}})', "ERROR: the request failed with status 404"):
            with self.subTest(answer=answer[:30]):
                done, lines, out, _ = self.settings("foundry", FAKE_HOST_ERROR=answer)
                self.assertNotEqual(done.returncode, 0)
                said = done.stdout + done.stderr
                self.assertIn(f"::error::The switch AGENTS_VIA_AI_GATEWAY (tools/environment-params.py) is True, and the AI Gateway {GATEWAY} is not in Azure or has not reported its host name. "
                              "Run aigateway first, or set the switch back to False. Nothing was changed.", said)
                self.assertEqual(self.builds(lines), ["build preview=yes host=[unset] project=[unset]"], "the final files are not made")
                self.assertEqual([line for line in lines if line.startswith("check ")], [])

    def test_a_host_name_that_is_not_the_services_is_no_host_name_and_stops_foundry_the_same_way(self):
        for answer in ("", "None", "evil.example.com", f"{HOST}.evil.example.com", f"https://{HOST}", HOST.upper(), f"{HOST}/default"):
            with self.subTest(answer=answer):
                done, lines, out, _ = self.settings("foundry", FAKE_HOST=answer)
                self.assertNotEqual(done.returncode, 0, answer)
                self.assertIn("is not in Azure or has not reported its host name. Run aigateway first", done.stdout + done.stderr)
                self.assertNotIn("aigateway_host=", out)

    def test_a_read_that_fails_for_another_reason_is_no_not_found_even_when_the_digits_404_are_inside_an_object_id(self):
        done, lines, _, _ = self.settings("foundry", FAKE_HOST_ERROR=HOSTILE)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(f"::error::The AI Gateway {GATEWAY} could not be read: {HOSTILE}", done.stdout + done.stderr)
        self.assertNotIn("Run aigateway first", done.stdout + done.stderr)
        done, lines, _, _ = self.settings("aigateway", FAKE_PROJECT_ERROR=HOSTILE)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(f"::error::The Foundry project could not be read: {HOSTILE}", done.stdout + done.stderr)
        self.assertNotIn("Run foundry first", done.stdout + done.stderr)

    def test_a_project_that_is_not_there_or_has_no_identity_stops_aigateway_and_says_to_run_foundry_first(self):
        for answer in ("", "None", "not-a-guid", PROJECT_PRINCIPAL + "0"):
            with self.subTest(answer=answer):
                done, lines, out, _ = self.settings("aigateway", FAKE_PROJECT_PRINCIPAL=answer)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(f"is True, and the Foundry project {PROJECT} is not in Azure or has no identity of its own, so it cannot be given AI Gateway Models User on the gateway. "
                              "Run foundry first, or set the switch back to False. Nothing was changed.", done.stdout + done.stderr)
                self.assertEqual(self.builds(lines), ["build preview=yes host=[unset] project=[unset]"])
        done, _, _, _ = self.settings("aigateway", FAKE_PROJECT_ERROR="ERROR: (ResourceNotFound) The Resource was not found.")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Run foundry first", done.stdout + done.stderr)

    def test_what_if_says_what_it_could_not_show_as_a_warning_and_goes_on_and_a_refused_read_is_a_warning_too(self):
        done, lines, out, _ = self.settings("what-if", FAKE_HOST="", FAKE_PROJECT_PRINCIPAL="")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertIn(f"::warning::The preview of the Foundry resource shows no connection to the AI Gateway, because the gateway {GATEWAY} is not in Azure or has not reported its host name (run aigateway first).", said)
        self.assertIn("::warning::The preview of the AI Gateway gives the Foundry project's identity no role, because the project is not in Azure or has no identity of its own (run foundry first).", said)
        self.assertNotIn("::error::", said)
        self.assertEqual(self.builds(lines)[1], "build preview=no host=[] project=[]")
        done, lines, out, _ = self.settings("what-if", FAKE_HOST_ERROR=HOSTILE, FAKE_PROJECT_ERROR=HOSTILE)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"::warning::The AI Gateway {GATEWAY} could not be read: {HOSTILE}", done.stdout + done.stderr)
        self.assertIn(f"::warning::The Foundry project could not be read: {HOSTILE}", done.stdout + done.stderr)
        self.assertNotIn("::error::", done.stdout + done.stderr)

    def test_the_step_only_reads_and_the_three_values_are_the_only_things_that_it_adds_to_the_answer_of_the_builder(self):
        done, lines, out, _ = self.settings("what-if")
        for call in lines:
            if call.startswith("az "):
                self.assertRegex(call, r"^az (identity list|rest --method get) ")
        code = "\n".join(line for line in script_of(SETTINGS).splitlines() if not line.strip().startswith("#"))
        self.assertNotRegex(code, r"--method (put|patch|post|delete)")
        for word in ("listKeys", "listSecrets", "az role", "az ad ", "--yes", "az resource delete"):
            self.assertNotIn(word, code, word)
        self.assertEqual(re.findall(r"(?m)^\s+echo \"(aigateway_host|foundry_project_principal|cases_app_principal)=", code), ["aigateway_host", "foundry_project_principal", "cases_app_principal"])


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheCasesActionChecksTheConnectionFirst(unittest.TestCase):
    AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) printf '%s' "found" ;;
  *"/connections/"*)
    if [ -n "$FAKE_CONNECTION_ERROR" ]; then echo "$FAKE_CONNECTION_ERROR" >&2; exit 1; fi
    echo aigateway ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
    ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "STORAGE_ACCOUNT": "stmeternautfn0123abcd", "EVENT_HUB_NAMESPACE": "evhns-meternaut-0123abcd",
           "FOUNDRY_ACCOUNT": ACCOUNT, "FOUNDRY_PROJECT": PROJECT, "CONNECTION_NAME": "aigateway"}

    def check(self, **changes):
        return run_step(PRECHECK, {"az": self.AZ}, {**self.ENV, **changes})

    def test_the_step_needs_the_recordings_storage_account_and_namespace_and_nothing_of_the_gateway_or_the_contract(self):
        done, lines, _, _ = self.check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([line for line in lines if line.startswith("az ")], [line for line in lines if line.startswith("az resource list ")])
        self.assertEqual(len(lines), 2, "one read for the storage account and one for the namespace")
        for word in ("ApiManagement", "gatewayUrl", "listSecrets", "/subscriptions/66666666", "subscriptions?"):
            self.assertFalse([line for line in lines if word in line], word)
        self.assertIn("The usage recording's storage account and namespace are there.", done.stdout)
        self.assertNotIn("contract", done.stdout.lower())
        code = "\n".join(line for line in script_of(PRECHECK).splitlines() if not line.strip().startswith("#"))
        for word in ("GATEWAY_RESOURCE_ID", "CONTRACT_SUBSCRIPTION", "EXPECTED_GATEWAY_URL", "primaryKey", "gatewayUrl"):
            self.assertNotIn(word, code, word)
        self.assertNotIn("CONTRACT_SUBSCRIPTION", step(PRECHECK))
        self.assertNotIn("steps.params.outputs.gateway_url", step(PRECHECK))

    def test_a_missing_storage_account_or_namespace_stops_the_step_and_says_to_run_recording_first(self):
        done, _, _, _ = run_step(PRECHECK, {"az": self.AZ.replace("""printf '%s' "found" """, "printf ''")}, dict(self.ENV))
        self.assertEqual(done.returncode, 1)
        self.assertIn("Run recording first: the first cases use its storage account and namespace.", done.stdout)

    def test_while_the_switch_is_off_the_step_is_what_it_was_and_does_not_look_for_the_connection(self):
        for off in ({}, {"AGENTS_VIA_AI_GATEWAY": ""}, {"AGENTS_VIA_AI_GATEWAY": "false"}):
            done, lines, _, _ = self.check(**off)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual([line for line in lines if "/connections/" in line], [])
            self.assertNotIn("connection", done.stdout)

    def test_with_the_switch_on_it_reads_the_connection_and_a_connection_that_is_there_lets_the_run_go_on(self):
        done, lines, _, _ = self.check(AGENTS_VIA_AI_GATEWAY="true")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([line for line in lines if "/connections/" in line], [CONNECTION_URL])
        self.assertIn(f"The Foundry project {PROJECT} has the connection aigateway to the AI Gateway: the app is given the model names that name it.", done.stdout)

    def test_a_connection_that_is_not_there_stops_the_run_before_anything_is_deployed_and_says_what_to_run_first(self):
        for answer in ("ERROR: (ResourceNotFound) The Resource was not found.", "ERROR: the request failed with status 404"):
            done, _, _, _ = self.check(AGENTS_VIA_AI_GATEWAY="true", FAKE_CONNECTION_ERROR=answer)
            self.assertEqual(done.returncode, 1)
            self.assertIn(f"::error::The switch AGENTS_VIA_AI_GATEWAY (tools/environment-params.py) is True, so the cases app is given model names that name the connection aigateway, and the Foundry project "
                          f"{PROJECT} has no such connection. Run aigateway and then foundry first (the order is in environment/BOOTSTRAP.md), or set the switch back to False. Nothing was deployed.", done.stdout)

    def test_a_read_that_fails_for_another_reason_is_no_not_found(self):
        done, _, _, _ = self.check(AGENTS_VIA_AI_GATEWAY="true", FAKE_CONNECTION_ERROR=HOSTILE)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"::error::The connection aigateway of the Foundry project {PROJECT} could not be read: {HOSTILE}. Nothing was deployed.", done.stdout)
        self.assertNotIn("Run aigateway and then foundry first", done.stdout)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheReadBacksAskForMoreOnlyWhileTheSwitchIsOn(unittest.TestCase):
    PYTHON3 = '#!/bin/bash\n{ echo "python3"; printf \'arg:%s\\n\' "$@"; } >> "$FAKE_LOG"\nexit "${FAKE_EXIT:-0}"\n'

    def foundry(self, **changes):
        env = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "FOUNDRY_ACCOUNT": ACCOUNT, "FOUNDRY_PROJECT": PROJECT, "FOUNDRY_GUARDRAIL": "meternaut-agents",
               "PRIVATE_ENDPOINT": f"pe-{ACCOUNT}", "PROJECT_ENDPOINT": f"https://{ACCOUNT}.services.ai.azure.com/api/projects/{PROJECT}", **changes}
        return run_step(FOUNDRY_READ_BACK, {"python3": self.PYTHON3}, env)

    def aigateway(self, **changes):
        env = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "GATEWAY_NAME": GATEWAY, "FOUNDRY_ACCOUNT": ACCOUNT, "VNET_NAME": "vnet-meternaut", "SUBNET_NAME": "snet-aigw",
               "OPERATOR_IDENTITY": "id-meternaut-operator", **changes}
        return run_step(AIGATEWAY_READ_BACK, {"python3": self.PYTHON3}, env)

    def arguments(self, lines):
        """The arguments of the tool, with the folder of the run taken out of the two paths that are in it."""
        return [re.sub(r"^.*/(summary\.md|aigateway-policies\.json)$", r"\1", line[len("arg:"):]) for line in lines if line.startswith("arg:")]

    def test_the_read_back_of_the_foundry_resource_reads_the_connection_too_with_the_host_and_the_name_and_without_them_it_is_what_it_was(self):
        done, lines, _, _ = self.foundry()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        plain = self.arguments(lines)
        self.assertEqual(plain[-2:], ["--summary", "summary.md"])
        self.assertFalse({"--ai-gateway-host", "--connection"} & set(plain))
        self.assertEqual(self.arguments(self.foundry(AIGATEWAY_HOST="", CONNECTION_NAME="aigateway")[1]), plain, "an empty host name is no host name: the call is what it was")
        done, lines, _, _ = self.foundry(AIGATEWAY_HOST=HOST, CONNECTION_NAME="aigateway")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.arguments(lines), [*plain, "--ai-gateway-host", HOST, "--connection", "aigateway"], "everything before is the call that it was")

    def test_a_tool_that_fails_fails_the_step(self):
        done, _, _, _ = self.foundry(AIGATEWAY_HOST=HOST, CONNECTION_NAME="aigateway", FAKE_EXIT="1")
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("|| true", script_of(FOUNDRY_READ_BACK))

    def test_the_read_back_of_the_gateway_asks_for_the_projects_role_only_with_the_object_id_and_otherwise_is_what_it_was(self):
        done, lines, _, _ = self.aigateway()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        plain = self.arguments(lines)
        self.assertEqual(plain[-2:], ["--summary", "summary.md"])
        self.assertNotIn("--project-principal", plain)
        self.assertEqual(self.arguments(self.aigateway(PROJECT_PRINCIPAL="")[1]), plain)
        done, lines, _, _ = self.aigateway(PROJECT_PRINCIPAL=PROJECT_PRINCIPAL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.arguments(lines), [*plain, "--project-principal", PROJECT_PRINCIPAL])
        done, _, _, _ = self.aigateway(PROJECT_PRINCIPAL=PROJECT_PRINCIPAL, FAKE_EXIT="1")
        self.assertEqual(done.returncode, 1)

    def test_the_read_back_of_the_gateway_asks_for_the_cases_apps_role_only_with_its_object_id_and_otherwise_is_what_it_was(self):
        # The judges call the gateway with the cases app's identity, so its role is read back when the app has an identity (the settings step read it from the app). Whether the switch is on or off.
        done, lines, _, _ = self.aigateway()
        plain = self.arguments(lines)
        self.assertNotIn("--cases-principal", plain)
        self.assertEqual(self.arguments(self.aigateway(CASES_PRINCIPAL="")[1]), plain, "an empty object id is none: the app has no identity yet")
        done, lines, _, _ = self.aigateway(CASES_PRINCIPAL=CASES_PRINCIPAL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.arguments(lines), [*plain, "--cases-principal", CASES_PRINCIPAL])
        done, lines, _, _ = self.aigateway(PROJECT_PRINCIPAL=PROJECT_PRINCIPAL, CASES_PRINCIPAL=CASES_PRINCIPAL)
        self.assertEqual(self.arguments(lines), [*plain, "--project-principal", PROJECT_PRINCIPAL, "--cases-principal", CASES_PRINCIPAL], "both roles are read back, each with its own flag")
        done, _, _, _ = self.aigateway(CASES_PRINCIPAL=CASES_PRINCIPAL, FAKE_EXIT="1")
        self.assertEqual(done.returncode, 1, "a read-back that fails fails the step")


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheSummaryAddsWhatTheSwitchChangesAndNothingWhileItIsOff(unittest.TestCase):
    def summary(self, action, status, on=True):
        env = {"ACTION": action, "JOB_STATUS": status, "ENV_RESOURCE_GROUP": GROUP, "AIGATEWAY_NAME": GATEWAY, "FOUNDRY_ACCOUNT": ACCOUNT, "FOUNDRY_PROJECT": PROJECT,
               "FOUNDRY_ENDPOINT": "https://example", "ACCOUNT_NAME": "x", "GITHUB_RUN_ID": "1",
               **({"AGENTS_VIA_AI_GATEWAY": "true", "CONNECTION_NAME": "aigateway"} if on else {})}
        done, _, _, text = run_step(SUMMARY, {}, env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return text

    def test_while_the_switch_is_off_the_summary_is_what_it_was(self):
        for action in ("aigateway", "foundry", "cases", "cases-run", "what-if", "aigateway-check"):
            for status in ("success", "failure"):
                self.assertNotIn("The switch of the agents' route", self.summary(action, status, on=False), (action, status))

    def test_each_changed_action_says_what_the_switch_added_for_success_and_for_failure(self):
        said = {}
        for action in ("aigateway", "foundry", "cases", "cases-run"):
            for status in ("success", "failure"):
                text = self.summary(action, status)
                self.assertEqual(text.count("**The switch of the agents' route is on.**"), 1, (action, status))
                said[(action, status)] = text
        self.assertIn("The Foundry project's identity holds AI Gateway Models User on the gateway (read back from Azure).", said[("aigateway", "success")])
        self.assertIn("The next action is `foundry`", said[("aigateway", "success")])
        self.assertIn("run `foundry` first", said[("aigateway", "failure")])
        self.assertIn("The project has the connection `aigateway` to the AI Gateway, with the project's own identity and no key.", said[("foundry", "success")])
        self.assertIn("WHETHER THE AGENT SERVICE CAN CALL THE GATEWAY THROUGH IT IS NOT KNOWN", said[("foundry", "success")])
        self.assertIn("run `aigateway` first", said[("foundry", "failure")])
        self.assertIn("the service did not take a connection of the category ApiManagement with the project's own identity for the gateway's address", said[("foundry", "failure")])
        self.assertIn("no key is built (rule 23), and the owner decides", said[("foundry", "failure")])
        self.assertIn("The cases app was given the model names `aigateway/<alias>` for the Investigator and the Skeptic", said[("cases", "success")])
        self.assertIn("The way back is the switch set to False in tools/environment-params.py, and a run of `cases`.", said[("cases", "success")])
        self.assertIn("run `aigateway` and then `foundry` first", said[("cases", "failure")])
        self.assertIn("the History says so in words", said[("cases-run", "failure")])
        self.assertIn("is not true for this run", said[("cases-run", "success")])

    def test_an_action_that_the_switch_does_not_change_gets_no_line_of_it(self):
        for action in ("what-if", "recording", "operator", "aigateway-check", "plant"):
            for status in ("success", "failure"):
                self.assertNotIn("The switch of the agents' route", self.summary(action, status), (action, status))


class TheTextsAreWrittenAsTheRulesSay(unittest.TestCase):
    def test_no_step_was_added_for_the_switch_and_the_steps_of_the_actions_are_the_ones_they_were(self):
        # aigateway has two steps more than the switch found: the subnet is made first, and the sign-in before the gateway's deploy (test_aigateway_subnet_first.py). The switch added none.
        # The tenth is the guard that stops the action at the first step of the job unless the owner asked for a public AI Gateway in writing (test_ai_gateway_guard.py).
        for action, count in (("foundry", 5), ("aigateway", 10), ("aigateway-check", 4)):
            self.assertEqual(len(re.findall(rf"inputs\.action == '{action}'", WORKFLOW)), count, action)

    def test_the_three_actions_are_described_with_the_switch_in_plain_words_and_the_description_stays_one_line(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        self.assertEqual(len(re.findall(r'(?m)^        description: "what-if: ', WORKFLOW)), 1)
        foundry = description.split(" foundry: ")[1].split(" cases: ")[0]
        self.assertIn("With the switch AGENTS_VIA_AI_GATEWAY in tools/environment-params.py on (it is off), it also makes the project's connection to the AI Gateway, with the project's own identity "
                      "and no key, and reads it back: it then needs aigateway first.", foundry)
        gateway = description.split(" aigateway: ")[1].split(" aigateway-check: ")[0]
        self.assertIn("With the switch AGENTS_VIA_AI_GATEWAY on (it is off), it also gives the Foundry project's identity AI Gateway Models User on the gateway, and needs foundry to have run.", gateway)
        cases = description.split(" cases: ")[1].split(" cases-run: ")[0]
        self.assertIn("With the switch AGENTS_VIA_AI_GATEWAY on (it is off), it gives the app the model names `aigateway/<alias>` for the agents, which name the project's connection to the AI Gateway, "
                      "and needs that connection first.", cases)

    def test_the_comments_of_the_changed_steps_say_that_the_switch_is_false_until_the_owner_says_yes_and_that_nothing_has_run(self):
        for name in (SETTINGS, PRECHECK, "Deploy the Foundry resource of the agents", FOUNDRY_READ_BACK, AIGATEWAY_READ_BACK, "Deploy the AI Gateway, its models and aliases, and its roles", SUMMARY):
            comment = re.sub(r"\s*\n\s*#\s*", " ", step(name))
            self.assertIn("AGENTS_VIA_AI_GATEWAY", comment, name)
            self.assertIn("False until the owner has said yes", comment, name)
        deploy = re.sub(r"\s*\n\s*#\s*", " ", step("Deploy the Foundry resource of the agents"))
        self.assertIn("whether the service takes that connection is not known until this runs (docs/proposals/08-ai-gateway.md, step 2)", deploy)
        self.assertIn("If it is refused, the deploy says so and the run stops there: the resource is as it was, and the owner decides. The way back is the switch set to False.", deploy)

    def test_the_settings_step_reads_the_service_with_the_version_of_the_check_and_the_environment_variables_of_the_builder_are_the_ones_it_documents(self):
        code = script_of(SETTINGS)
        self.assertIn("api-version=2025-09-01-preview", code)
        self.assertIn("AIGATEWAY_HOST=\"$aigateway_host\" FOUNDRY_PROJECT_PRINCIPAL_ID=\"$project_principal\" CASES_SYSTEM_PRINCIPAL_ID=\"$cases_system_principal\"", code)
        self.assertNotIn("GATEWAY_PRINCIPAL_ID", code)
        builder = (ROOT / "tools" / "environment-params.py").read_text(encoding="utf-8")
        for variable in ("AIGATEWAY_HOST", "FOUNDRY_PROJECT_PRINCIPAL_ID", "ACTION"):
            self.assertIn(variable, builder.split('"""\nfrom __future__')[0], f"{variable} is documented in the builder")
        self.assertIn('API = "2025-09-01-preview"', (ROOT / "tools" / "aigateway-prep.py").read_text(encoding="utf-8"), "the version of the tools is the version of the template")


if __name__ == "__main__":
    unittest.main()
