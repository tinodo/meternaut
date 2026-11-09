import contextlib
import hashlib
import importlib.util
import io
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
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
PRINCIPAL = "5a1c0de0-0000-4000-8000-0000000000de"
CLIENT = "11111111-2222-3333-4444-555555555555"


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def step_script(name):
    """The `run:` script of the step with this name, as the runner would write it to a file."""
    block = re.search(rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", WORKFLOW)
    assert block, name
    run = re.search(r"(?ms)^        run: \|\n(.*)", block.group(1))
    assert run, name
    return textwrap.dedent(run.group(1))


def run_step_script(name, stand_ins, env, files=None, prelude=""):
    """Run the `run:` script of a step with bash, as the runner does, with stand-ins for the commands that it calls first on the PATH.

    A command that Git's own /usr/bin has (sleep) cannot be replaced from the PATH, because Git's bash puts its folder first: give a shell function in `prelude`.
    Returns the finished process, the lines that the stand-ins logged, and the text that the step added to its output file."""
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
        script.write_text(prelude + step_script(name), encoding="utf-8", newline="\n")
        log = tmp / "log.txt"
        log.write_text("", encoding="utf-8")
        (tmp / "out.txt").write_text("", encoding="utf-8")
        full = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": log.as_posix(), "FAKE_DIR": tmp.as_posix(),
                "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(), "GITHUB_STEP_SUMMARY": (tmp / "summary.md").as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env}
        done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=full, cwd=ROOT)
        return done, log.read_text(encoding="utf-8").splitlines(), (tmp / "out.txt").read_text(encoding="utf-8")


CASES_PRINCIPAL = "7d3c1f52-3b0a-4f6e-9a55-0c1f5f2b9d11"
SYSTEM_PRINCIPAL = "3b9e2f81-6c4d-4a7e-8f10-2d5a9c7b1e44"
GATEWAY_NAME = "aigw-meternaut-abc123"
GATEWAY_HOST = "aigw-meternaut-abc123.swedencentral-01.ai.gateway.azure.com"

FOUNDRY_SETTINGS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"identity list"*|*"/loggers"*|*"Microsoft.ApiManagement/service"*) echo "the owner's API Management instance and its identity must not be looked at: $*" >&2; exit 8 ;;
  *"/providers/Microsoft.ApiManagement/aigateways/"*)
    if [ "$FAKE_GATEWAY" = "FAIL" ]; then echo "$FAKE_SYSTEM_ERROR" >&2; exit 1; fi
    if [ "$FAKE_GATEWAY" = "ABSENT" ]; then echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.ApiManagement/aigateways/aigw-meternaut-abc123' under resource group 'rg-of-the-project' was not found." >&2; exit 1; fi
    printf '%s' "$FAKE_GATEWAY" ;;
  *"/providers/Microsoft.Web/sites/"*)
    if [ "$FAKE_SYSTEM" = "FAIL" ]; then echo "$FAKE_SYSTEM_ERROR" >&2; exit 1; fi
    if [ "$FAKE_SYSTEM" = "ABSENT" ]; then echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Web/sites/func-meternaut-cases-abc123' under resource group 'rg-of-the-project' was not found." >&2; exit 1; fi
    printf '%s' "$FAKE_SYSTEM" ;;
  *"/projects/"*)
    if [ "$FAKE_PROJECT" = "found" ]; then echo meternaut; else echo "$FAKE_PROJECT" >&2; exit 1; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

FOUNDRY_SETTINGS_PYTHON3 = """#!/bin/bash
if [ "$2" = "build" ]; then
  echo "build preview=$([[ " $* " == *" --preview "* ]] && echo yes || echo no) foundry_project=${ENV_FOUNDRY_PROJECT_EXISTS-unset} cases_system=[${CASES_SYSTEM_PRINCIPAL_ID-unset}] retired=[${GATEWAY_PRINCIPAL_ID-unset}${GATEWAY_CLIENT_ID-unset}${RECORDING_FRAGMENTS-unset}] contract=$([[ " $* " == *" --contract"* ]] && echo yes || echo no) policies=$([[ " $* " == *" --aigateway-policies environment/aigateway/policies.json"* ]] && echo yes || echo no) aigw=[${AIGATEWAY_HOST-unset}]" >> "$FAKE_LOG"
  printf 'cases_function_app_name=func-meternaut-cases-abc123\\nfoundry_account_name=aif-meternaut-agents-abc123\\nfoundry_project_name=meternaut\\naigateway_name=aigw-meternaut-abc123\\nagents_via_ai_gateway=false\\n'
else
  echo "check $*" >> "$FAKE_LOG"
fi
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class WorkOutTheFoundrySettings(unittest.TestCase):
    """The lookups that the step 'Work out the settings' makes for the Foundry resource: the system-assigned identity of the cases app, which gets a role on the project and which is read from the
    app, and whether the project is there. Only the actions that use an answer look for it."""

    PROJECT_CALL = ("az rest --method get --url https://management.azure.com/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.CognitiveServices"
                    "/accounts/aif-meternaut-agents-abc123/projects/meternaut?api-version=2025-06-01 --query name --output tsv")
    SITE_CALL = ("az rest --method get --url https://management.azure.com/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.Web"
                 "/sites/func-meternaut-cases-abc123?api-version=2024-04-01 --query identity.principalId --output tsv")
    PREVIEW = "build preview=yes foundry_project=unset cases_system=[unset] retired=[unsetunsetunset] contract=no policies=yes aigw=[unset]"
    HOSTILE = "ERROR: (AuthorizationFailed) The client '40404040-4040-4040-4040-404040404040' with object id 'a404b404-0000-0000-0000-000000000404' does not have authorization"
    GATEWAY_CALL = ("az rest --method get --url https://management.azure.com/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.ApiManagement"
                    f"/aigateways/{GATEWAY_NAME}?api-version=2025-09-01-preview --query properties.frontend.defaultHostname --output tsv")

    def run_step(self, action="what-if", project="found", system=SYSTEM_PRINCIPAL, gateway=GATEWAY_HOST, **env):
        return run_step_script("Work out the settings", {"az": FOUNDRY_SETTINGS_AZ, "python3": FOUNDRY_SETTINGS_PYTHON3},
                               {"ACTION": action, "FAKE_PROJECT": project,
                                "FAKE_SYSTEM": system, "FAKE_SYSTEM_ERROR": self.HOSTILE, "FAKE_GATEWAY": gateway,
                                "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project", **env})

    def builds(self, lines):
        return [line for line in lines if line.startswith("build ")]

    def final(self, project="false", system="", host=""):
        return f"build preview=no foundry_project={project} cases_system=[{system}] retired=[unsetunsetunset] contract=no policies=yes aigw=[{host}]"

    def user_assigned_lookups(self, lines):
        return [line for line in lines if line.startswith("az identity list")]

    def test_what_if_looks_for_the_identity_of_the_app_and_for_the_project_with_the_version_that_the_model_account_uses(self):
        done, lines, _ = self.run_step("what-if")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), [self.PREVIEW, self.final("true", SYSTEM_PRINCIPAL, GATEWAY_HOST)])
        self.assertIn(self.PROJECT_CALL, lines, "existence does not need the newest version")
        self.assertIn(self.SITE_CALL, lines, "the system-assigned identity is read from the app, and the version is the one that the other reads of the app use")
        self.assertIn(self.GATEWAY_CALL, lines, "the host name of the AI Gateway is read from the service, so that the preview shows the real one")
        self.assertEqual(self.user_assigned_lookups(lines), [], "no identity is listed: the user-assigned one that the app used before is not looked for, and neither is the gateway's")
        self.assertIn("The cases app's system-assigned identity exists; its principal id goes into the Foundry file and the AI Gateway file.", done.stdout)
        self.assertIn("The Foundry project is in Azure: true.", done.stdout)

    def test_foundry_needs_the_identity_and_never_looks_for_the_project(self):
        done, lines, _ = self.run_step("foundry", project="ERROR: (AuthorizationFailed) a read that would stop the run if it were made")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), [self.PREVIEW, self.final("false", SYSTEM_PRINCIPAL)])
        self.assertIn(self.SITE_CALL, lines)
        self.assertEqual([line for line in lines if "/projects/" in line], [])
        self.assertNotIn(self.GATEWAY_CALL, lines, "while the switch of the agents is off, foundry reads nothing of the AI Gateway")
        self.assertEqual(self.user_assigned_lookups(lines), [], "foundry has no use for any identity of the gateway")
        self.assertIn("The action foundry does not use the Foundry project, so it is not looked for.", done.stdout)

    def test_cases_needs_the_project_and_the_ai_gateway_and_never_looks_for_the_identity(self):
        done, lines, _ = self.run_step("cases", system="FAIL")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), [self.PREVIEW, self.final("true", "", GATEWAY_HOST)])
        self.assertIn(self.PROJECT_CALL, lines)
        self.assertIn(self.GATEWAY_CALL, lines, "every model call goes through the AI Gateway, so the action reads its host name from the service")
        self.assertEqual([line for line in lines if "Microsoft.Web/sites" in line], [], "the cases app is not given a role on the project by this action")
        self.assertEqual(self.user_assigned_lookups(lines), [], "cases has no use for any identity of the gateway")
        self.assertIn("The Foundry project is in Azure: true.", done.stdout)
        self.assertIn(f"The service reports the host name of the AI Gateway {GATEWAY_NAME}; it goes into the cases file", done.stdout)

    def test_every_other_action_looks_for_none_of_them_so_a_refused_read_cannot_stop_it(self):
        for action in ("loop-check", "operator", "base"):
            with self.subTest(action=action):
                done, lines, _ = self.run_step(action, project=self.HOSTILE, system="FAIL", gateway="FAIL")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(self.builds(lines), [self.PREVIEW, self.final()])
                self.assertEqual([line for line in lines if "/projects/" in line or "Microsoft.Web/sites" in line or "aigateways" in line], [])
                self.assertEqual(self.user_assigned_lookups(lines), [])
                self.assertIn(f"The action {action} does not use the Foundry project, so it is not looked for.", done.stdout)

    def test_an_object_id_in_capitals_is_passed_on_as_it_is(self):
        done, lines, _ = self.run_step("foundry", system=SYSTEM_PRINCIPAL.upper())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines)[1], self.final("false", SYSTEM_PRINCIPAL.upper()))

    def test_a_project_that_is_not_there_gives_false_however_the_service_says_so_and_the_final_build_still_follows(self):
        for action, answer in (("cases", "ERROR: (ResourceNotFound) The Resource 'Microsoft.CognitiveServices/accounts/x/projects/meternaut' was not found."),
                               ("cases", "ERROR: the request failed with status 404"), ("what-if", 'ERROR: Not Found({"error":{"code":"NotFound"}})')):
            with self.subTest(action=action, answer=answer):
                done, lines, _ = self.run_step(action, project=answer)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(self.builds(lines)[1].split(" ")[2], "foundry_project=false")
                self.assertIn("The Foundry project is in Azure: false.", done.stdout)
                self.assertNotIn("::warning::", done.stdout + done.stderr, "not being there is an answer, not a failure")

    def test_for_cases_an_answer_that_is_not_not_found_stops_the_run_with_a_clear_message_even_when_it_holds_the_digits_404_inside_an_object_id(self):
        for answer in (self.HOSTILE, "ERROR: (InternalServerError) try again later", "ERROR: (NoRegisteredProviderFound) the namespace is not registered"):
            with self.subTest(answer=answer[:30]):
                done, lines, _ = self.run_step("cases", project=answer)
                self.assertNotEqual(done.returncode, 0)
                said = done.stderr + done.stdout
                self.assertIn("::error::meternaut could not be read: " + answer, said)
                self.assertIn("::error::The action cases gives the cases app the address of the Foundry project only when the project is in Azure, so it has to know, and the read of the project failed", said)
                self.assertIn("Nothing was changed: run cases again.", said)
                self.assertEqual(self.builds(lines), [self.PREVIEW], "a wrong guess would switch the investigation on or off")
                self.assertEqual([line for line in lines if line.startswith("check ")], [], "the run stopped before the files were checked")

    def test_for_what_if_an_answer_that_is_not_not_found_is_a_warning_and_counts_as_not_there(self):
        done, lines, _ = self.run_step("what-if", project=self.HOSTILE)
        self.assertEqual(done.returncode, 0, done.stderr)
        said = done.stderr + done.stdout
        self.assertIn("::warning::meternaut could not be read: " + self.HOSTILE, said)
        self.assertNotIn("::error::", said, "a preview is not stopped by a read")
        self.assertIn("::warning::The preview of the cases app assumes that the Foundry project is not in Azure, because the read of the project failed", said)
        self.assertEqual(self.builds(lines)[1], self.final("false", SYSTEM_PRINCIPAL, GATEWAY_HOST))
        self.assertIn("The Foundry project is in Azure: false.", done.stdout)
        self.assertEqual([line for line in lines if line.startswith("check ")][-1].split("--label ")[1], "planted", "the files were checked as always")

    def test_an_app_without_a_system_assigned_identity_gives_an_empty_value_and_the_run_goes_on(self):
        # "none yet": the app is not there (not found), or it is there and has no such identity (the CLI prints None for a null, and an empty string for nothing)
        for action in ("foundry", "what-if"):
            for answer in ("ABSENT", "None", "", "not-a-guid"):
                with self.subTest(action=action, answer=answer):
                    done, lines, _ = self.run_step(action, system=answer)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(self.builds(lines)[1], self.final("true", "", GATEWAY_HOST) if action == "what-if" else self.final("false", ""))
                    self.assertIn("The cases app has no system-assigned identity yet (the action cases makes the app with it); the Foundry file holds a placeholder and the AI Gateway file gives no role to the app.",
                                  done.stdout)
                    self.assertNotIn("::error::", done.stdout + done.stderr)

    def test_a_lookup_of_the_system_assigned_identity_that_fails_stops_the_run_even_when_the_error_holds_the_digits_404_inside_an_object_id(self):
        for action in ("foundry", "what-if"):
            with self.subTest(action=action):
                done, lines, _ = self.run_step(action, system="FAIL")
                self.assertNotEqual(done.returncode, 0)
                said = done.stderr + done.stdout
                self.assertIn("::error::The cases app could not be read: " + self.HOSTILE, said)
                self.assertEqual(self.builds(lines), [self.PREVIEW], "no file was made with a placeholder for an identity that may be there")
                self.assertEqual([line for line in lines if line.startswith("check ")], [])

    ACTIONS = re.findall(r"^          - (\S+)$", re.search(r"(?ms)^      action:\n(.*?)^      \w", WORKFLOW).group(1), re.M)

    def test_the_actions_of_the_workflow_are_the_ones_without_the_three_that_made_objects_on_the_instance(self):
        self.assertEqual(self.ACTIONS, ["what-if", "model-side", "base", "retire-old", "retire-event-hubs", "foundry", "cases", "cases-run", "page-latency", "plant", "loop-check", "operator", "operator-probe",
                                        "aigateway", "aigateway-check", "governance", "gateway-telemetry", "drift-check", "agents-drift", "foundry-evals", "foundry-redteam", "agent365-check", "teams"])
        for retired in ("gateway-prepare", "gateway", "contract", "recording", "recording-check"):
            self.assertNotIn(retired, self.ACTIONS)

    def test_no_action_looks_at_the_owners_api_management_instance_or_at_a_gateway_identity_and_every_action_builds_and_checks_its_files_without_a_word_of_alarm(self):
        # The owner ordered the undo of what Meternaut added to his API Management instance (2026-11-07): after it the instance has no gateway identity and no loggers of ours, and nothing here
        # looks for them. The stand-in of the Azure CLI fails any call that would: so the step has to go through for every action, with the facts that the action itself needs (cases reads the project
        # and the host name of the AI Gateway, foundry and aigateway read the identity of the cases app, what-if reads all three) and with no warning.
        for action in self.ACTIONS:
            with self.subTest(action=action):
                done, lines, _ = self.run_step(action)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                said = done.stdout + done.stderr
                self.assertNotIn("::warning::", said)
                self.assertNotIn("::error::", said)
                self.assertNotIn("gateway identity", said, "no word about an identity that does not exist")
                self.assertNotIn("placeholder", said.replace("the Foundry file holds a placeholder", ""))
                for call in (line for line in lines if line.startswith("az ")):
                    self.assertNotRegex(call, r"identity list|/loggers|ApiManagement/service|--apim", call)
                builds = self.builds(lines)
                self.assertEqual(builds[0], self.PREVIEW)
                self.assertRegex(builds[1], r"^build preview=no foundry_project=\w+ cases_system=\[[0-9a-f-]*\] retired=\[unsetunsetunset\] contract=no policies=yes aigw=\[[a-z0-9.-]*\]$",
                                 "the builder is given nothing of the retired settings")
                labels = [re.search(r"--label (\S+)", line).group(1) for line in lines if line.startswith("check ")]
                self.assertEqual(labels, ["environment", "base", "foundry", "cases", "operator", "planted"], "every file is checked against its template")

    def test_the_step_names_nothing_of_the_instance_its_identity_its_loggers_or_the_contract(self):
        # The comments of the step say that it looks at none of them; the commands do not name them.
        script = "\n".join(line for line in step_script("Work out the settings").splitlines() if not line.lstrip().startswith("#"))
        for word in ("GATEWAY_RESOURCE_ID", "GATEWAY_PRINCIPAL_ID", "GATEWAY_CLIENT_ID", "RECORDING_FRAGMENTS", "--contract", "contract_files", "identity list", "loggers", "ApiManagement/service",
                     "usage-eventhub-logger", "gateway_subscription", "gateway_resource_group", "identity_name", "--apim"):
            self.assertNotIn(word, script, word)
        self.assertNotIn("GATEWAY_APPINSIGHTS_ID", WORKFLOW, "no secret of the gateway's side is read any more: the usage recording that read the Application Insights component was removed on 2026-11-07")
        self.assertNotIn("GATEWAY_RESOURCE_ID", WORKFLOW)

    def test_the_lookups_only_read(self):
        done, lines, _ = self.run_step("what-if")
        self.assertEqual(done.returncode, 0, done.stderr)
        for call in (line for line in lines if line.startswith("az ")):
            for word in (" put ", " post ", " patch ", " delete ", " create ", " role ", "listKeys", "listSecrets", "--yes"):
                self.assertNotIn(word, call + " ", call)


FOUNDRY_PRECHECK_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) printf '%s' "$FAKE_COMPONENT" ;;
  *"/providers/Microsoft.Web/sites/"*)
    if [ "$FAKE_SITE" = "FAIL" ]; then echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Web/sites/func-meternaut-cases-abc123' was not found." >&2; exit 1; fi
    printf '%s' "$FAKE_SITE" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheFoundryResourceBuildsOnWhatIsThere(unittest.TestCase):
    """The check before the deploy of the Foundry resource: the component for the traces, the cases app with its own system-assigned identity, and a file that carries the identity's object id."""

    TITLE = "The base and the cases app's identity are there, which the Foundry resource builds on"
    SITE_CALL = ("az rest --method get --url https://management.azure.com/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.Web"
                 "/sites/func-meternaut-cases-abc123?api-version=2024-04-01 --query identity.principalId --output tsv")

    def run_step(self, component="appi-meternaut", site=CASES_PRINCIPAL, parameter_file=None):
        parameter_file = f'{{"casesSystemPrincipalId": {{"value": "{CASES_PRINCIPAL}"}}}}' if parameter_file is None else parameter_file
        return run_step_script(self.TITLE, {"az": FOUNDRY_PRECHECK_AZ},
                               {"FAKE_COMPONENT": component, "FAKE_SITE": site, "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project",
                                "INSIGHTS_NAME": "appi-meternaut", "CASES_APP": "func-meternaut-cases-abc123"},
                               files={"foundry.parameters.json": parameter_file})

    def test_everything_is_there_and_the_file_carries_the_object_id_so_the_step_passes(self):
        done, lines, _ = self.run_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(lines, ["az resource list --resource-group rg-of-the-project --resource-type Microsoft.Insights/components --query [?name=='appi-meternaut'].name | [0] --output tsv",
                                 self.SITE_CALL])
        self.assertIn("the parameter file carries the identity's object id", done.stdout)

    def test_the_object_id_is_found_in_the_file_whatever_its_case(self):
        done, _, _ = self.run_step(site=CASES_PRINCIPAL.upper())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_component_that_is_not_there_stops_the_step_and_says_to_run_the_base_first(self):
        for answer in ("", "None"):
            done, lines, _ = self.run_step(component=answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("Run base first", done.stdout)
            self.assertEqual(len(lines), 1, "the app is not asked for when the first thing is missing")

    def test_an_app_that_is_not_there_or_has_no_identity_of_its_own_stops_the_step_and_says_to_run_cases_first(self):
        for answer in ("", "None", "not-a-guid", "FAIL"):
            done, lines, _ = self.run_step(site=answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("Run cases first", done.stdout)
            self.assertEqual(lines[-1], self.SITE_CALL)
        done, _, _ = self.run_step(site="FAIL")
        self.assertIn("could not be read, or it is not in rg-of-the-project", done.stdout)
        done, _, _ = self.run_step(site="None")
        self.assertIn("has no system-assigned identity", done.stdout)

    def test_a_file_without_the_object_id_stops_the_step_and_nothing_is_deployed(self):
        for parameter_file in ('{"casesSystemPrincipalId": {"value": "00000000-0000-0000-0000-000000000000"}}', "{}", ""):
            done, _, _ = self.run_step(parameter_file=parameter_file)
            self.assertEqual(done.returncode, 1, parameter_file)
            self.assertIn("does not carry the object id of the identity of func-meternaut-cases-abc123", done.stdout)
            self.assertIn("Nothing was deployed.", done.stdout)

    def test_the_check_only_reads(self):
        done, lines, _ = self.run_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for call in lines:
            self.assertRegex(call, r"^az (resource list|rest --method get) ")
            for word in (" create ", " delete ", " update ", " role ", " put ", " post ", " patch "):
                self.assertNotIn(word, call + " ", call)


FOUNDRY_DEPLOY_PYTHON3 = """#!/bin/bash
echo "python3 $*" >> "$FAKE_LOG"
if [ "$1" = "tools/az-deploy.py" ]; then printf '%s' "$FAKE_ENDPOINT"; else exit "${FAKE_EXIT-0}"; fi
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class DeployAndReadBackTheFoundryResource(unittest.TestCase):
    """The deploy step and the read-back step of the Foundry resource, against a stand-in for python3."""

    ADDRESS = "https://aif-meternaut-agents-abc123.services.ai.azure.com/api/projects/meternaut"

    def deploy(self, answer):
        return run_step_script("Deploy the Foundry resource of the agents", {"python3": FOUNDRY_DEPLOY_PYTHON3},
                               {"FAKE_ENDPOINT": answer, "EXPECTED_ENDPOINT": self.ADDRESS, "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project",
                                "GITHUB_RUN_ID": "4242"})

    def read_back(self, exit_code):
        return run_step_script("Read the Foundry resource back", {"python3": FOUNDRY_DEPLOY_PYTHON3},
                               {"FAKE_EXIT": str(exit_code), "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project", "FOUNDRY_ACCOUNT": "aif-meternaut-agents-abc123",
                                "FOUNDRY_PROJECT": "meternaut", "FOUNDRY_GUARDRAIL": "meternaut-agents", "PRIVATE_ENDPOINT": "pe-aif-meternaut-agents-abc123", "PROJECT_ENDPOINT": self.ADDRESS})

    def test_the_template_is_deployed_with_its_file_under_a_name_of_the_run_with_the_restore_switch_and_the_address_is_asked_for(self):
        done, lines, _ = self.deploy(self.ADDRESS)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (call,) = lines
        self.assertRegex(call, r"^python3 tools/az-deploy\.py create --subscription sub-of-the-project --resource-group rg-of-the-project --template environment/foundry/main\.bicep "
                               r"--parameters \S+/foundry\.parameters\.json --name foundry-4242 --output projectEndpoint --restore-param restoreAccount$")
        self.assertIn(f"The project endpoint is {self.ADDRESS}.", done.stdout)

    def test_a_slash_at_the_end_of_the_address_does_not_matter(self):
        done, _, _ = self.deploy(self.ADDRESS + "/")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_another_address_than_the_one_the_cases_app_would_be_given_fails_the_step(self):
        for answer in ("", "https://other.services.ai.azure.com/api/projects/meternaut", self.ADDRESS + "x", self.ADDRESS.replace("/meternaut", "/other")):
            done, _, _ = self.deploy(answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("which is the address that the cases app would be given", done.stdout)

    def test_the_read_back_runs_the_tool_with_the_names_and_the_failure_of_the_tool_is_the_failure_of_the_step(self):
        done, lines, _ = self.read_back(0)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (call,) = lines
        self.assertRegex(call, r"^python3 tools/foundry-check\.py read-back --subscription sub-of-the-project --resource-group rg-of-the-project --account aif-meternaut-agents-abc123 "
                               r"--project meternaut --guardrail meternaut-agents --private-endpoint pe-aif-meternaut-agents-abc123 --endpoint " + re.escape(self.ADDRESS) +
                               r" --models environment/models\.json --summary \S+/summary\.md$")
        failed, _, _ = self.read_back(1)
        self.assertEqual(failed.returncode, 1, "a difference between the template and Azure stops the run")


FOUNDRY_WAIT_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"private-endpoint list"*) printf '%s' "$FAKE_PE" ;;
  *"dns-zone-group list"*)
    n=$(cat "$FAKE_DIR/count" 2>/dev/null || echo 0)
    n=$((n + 1))
    echo "$n" > "$FAKE_DIR/count"
    if [ "$n" -le "$FAKE_FAILING" ]; then echo "ERROR: try again" >&2; exit 1; fi
    if [ "$n" -ge "$FAKE_FROM" ]; then printf '%s' "$FAKE_ZONES"; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

FAKE_SLEEP = 'sleep() { echo "sleep $*" >> "$FAKE_LOG"; }\n'


@unittest.skipIf(BASH is None, "no bash on this machine")
class WaitForTheFoundryPrivateEndpoint(unittest.TestCase):
    """The wait for the landing zone's policy to register the Foundry resource's private endpoint: when it ends, when it fails, and that it makes no zone."""

    TITLE = "Wait until the landing zone has registered the Foundry resource's private endpoint in the central zones"
    ZONE = "/subscriptions/dddd/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/"

    def run_step(self, zones, endpoint="pe-aif-meternaut-agents-abc123", registered_from=1, failing=0):
        return run_step_script(self.TITLE, {"az": FOUNDRY_WAIT_AZ},
                               {"FAKE_PE": endpoint, "FAKE_ZONES": zones, "FAKE_FROM": str(registered_from), "FAKE_FAILING": str(failing),
                                "ENV_RESOURCE_GROUP": "rg-of-the-project", "PRIVATE_ENDPOINT": "pe-aif-meternaut-agents-abc123"}, prelude=FAKE_SLEEP)

    def checks(self, lines):
        return [line for line in lines if "dns-zone-group list" in line]

    def sleeps(self, lines):
        return [line for line in lines if line.startswith("sleep")]

    def test_a_zone_registered_at_once_ends_the_wait_and_the_two_other_zones_are_only_said(self):
        done, lines, _ = self.run_step(f"{self.ZONE}privatelink.services.ai.azure.com\n{self.ZONE}privatelink.openai.azure.com\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("has registered pe-aif-meternaut-agents-abc123 in the central private DNS zone privatelink.services.ai.azure.com", done.stdout)
        self.assertIn("It is registered in privatelink.openai.azure.com too.", done.stdout)
        self.assertIn("It is not registered in privatelink.cognitiveservices.azure.com: the cases app does not use that name.", done.stdout)
        self.assertEqual((len(self.checks(lines)), self.sleeps(lines)), (1, []))

    def test_a_zone_that_comes_later_is_waited_for_a_minute_at_a_time_and_a_check_that_fails_is_tried_again(self):
        done, lines, _ = self.run_step(f"{self.ZONE}privatelink.services.ai.azure.com\n", registered_from=4, failing=1)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Not registered yet (check 1 of 40).", done.stdout)
        self.assertEqual((len(self.checks(lines)), self.sleeps(lines)), (4, ["sleep 60"] * 3))

    def test_the_two_other_zones_alone_never_end_the_wait_and_forty_checks_fail_the_step_which_says_not_to_make_a_zone(self):
        done, lines, _ = self.run_step(f"{self.ZONE}privatelink.cognitiveservices.azure.com\n{self.ZONE}privatelink.openai.azure.com\n")
        self.assertEqual(done.returncode, 1)
        self.assertEqual((len(self.checks(lines)), self.sleeps(lines)), (40, ["sleep 60"] * 39), "no sleep after the last check")
        self.assertIn("Not registered yet (check 40 of 40).", done.stdout)
        self.assertIn("do not create a private DNS zone", done.stdout)
        self.assertIn("Do not run cases yet.", done.stdout)

    def test_a_private_endpoint_that_is_not_there_stops_the_step_at_once(self):
        for endpoint in ("", "None"):
            done, lines, _ = self.run_step("", endpoint=endpoint)
            self.assertEqual(done.returncode, 1, endpoint)
            self.assertIn("The private endpoint pe-aif-meternaut-agents-abc123 is not there.", done.stdout)
            self.assertEqual((self.checks(lines), self.sleeps(lines)), ([], []))

    def test_the_step_only_reads_and_makes_no_zone(self):
        done, lines, _ = self.run_step(f"{self.ZONE}privatelink.services.ai.azure.com\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len(lines), 2)
        for call in lines:
            self.assertRegex(call, r"^az network private-endpoint (list|dns-zone-group list) ")
            for word in ("create", "delete", "update", "private-dns", "role", "--yes"):
                self.assertNotIn(word, call, call)


APP_WAIT_AZ = """az() {
  # a function in the shell of the step and not a program on the PATH, because a wait makes hundreds of calls and a program is a process each. It asks for the zone group of the endpoint that the call
  # names (--endpoint-name). FAKE_REGISTERED is "endpoint=zone endpoint=zone@3 ...": the endpoints that the policy has registered, each in its zone, and from the check that @ names on (without it: from
  # the first). FAKE_COUNT is the number of endpoints that one check asks about, so that the number of the check can be told from the number of the call; the first FAKE_FAILING calls fail.
  local n check endpoint previous argument pair rest zone from
  echo "az $*" >> "$FAKE_LOG"
  case "$*" in
    *"dns-zone-group list"*)
      read -r n < "$FAKE_DIR/count" 2> /dev/null || n=0
      n=$((n + 1))
      echo "$n" > "$FAKE_DIR/count"
      if [ "$n" -le "${FAKE_FAILING:-0}" ]; then echo "ERROR: try again" >&2; return 1; fi
      check=$(( (n - 1) / FAKE_COUNT + 1 ))
      endpoint=""; previous=""
      for argument in "$@"; do if [ "$previous" = "--endpoint-name" ]; then endpoint=$argument; fi; previous=$argument; done
      for pair in $FAKE_REGISTERED; do
        rest=${pair#*=}; zone=${rest%%@*}; from=1
        if [[ "$rest" == *@* ]]; then from=${rest#*@}; fi
        if [ "${pair%%=*}" = "$endpoint" ] && [ "$check" -ge "$from" ]; then printf '/subscriptions/dddd/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/%s\\n' "$zone"; fi
      done ;;
    *) echo "unexpected az call: $*" >&2; return 9 ;;
  esac
}
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class WaitForTheEndpointsOfTheBaseAndTheCasesApp(unittest.TestCase):
    """The waits of the actions base and cases for the landing zone's policy to register private endpoints in its central zones before anything uses their names: the base's three (the storage account's)
    before an app starts, and the cases app's own before its code is published. A deployment of an app after its endpoint was made failed at the publish, because the
    app's own name did not resolve until the zone had its record (2026-11-06): so the cases action waits for its own endpoint. Each runs against a stand-in for az that registers the endpoints from the
    check that the test names on."""

    BASE = "Wait until the landing zone has registered the base's private endpoints in the central zones"
    CASES = "Wait until the landing zone has registered the cases app's private endpoint in the central zone"
    SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
    GROUP = "rg-of-the-project"
    ZONE_OF_THE_APPS = "privatelink.azurewebsites.net"

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("environment_params_of_the_wait_tests", ROOT / "tools" / "environment-params.py")
        cls.params = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.params)
        names = cls.params.base_names(cls.SUBSCRIPTION, cls.GROUP)
        cls.base = cls.params.base_endpoints(names)
        cls.cases = cls.params.cases_endpoints(cls.params.cases_names(cls.SUBSCRIPTION, cls.GROUP))
        cls.last_endpoint, cls.last_zone = cls.base[-1]
        cls.cases_endpoint = cls.cases[0][0]

    def run_wait(self, title, variable, pairs, registered, failing=0, two_checks=False):
        """`two_checks`: the loop runs twice and not forty times, which a test that is not about the budget uses to keep the run short (the budget is held by the forty-check tests and by the structure test)."""
        env = {variable: ",".join(f"{endpoint}:{zone}" for endpoint, zone in pairs), "ENV_RESOURCE_GROUP": self.GROUP, "FAKE_REGISTERED": " ".join(registered), "FAKE_COUNT": str(len(pairs)),
               "FAKE_FAILING": str(failing)}
        return run_step_script(title, {}, env, prelude=FAKE_SLEEP + APP_WAIT_AZ + ('seq() { printf "1\\n2\\n"; }\n' if two_checks else ""))

    def registered(self, pairs, **later):
        """Every endpoint of the list, registered in its zone from the first check, except the ones named in `later`, which come from that check on."""
        return [f"{endpoint}={zone}" + (f"@{later[endpoint]}" if endpoint in later else "") for endpoint, zone in pairs]

    def checks(self, lines):
        return [line for line in lines if "dns-zone-group list" in line]

    def named(self, lines):
        return [re.search(r"--endpoint-name (\S+)", line).group(1) for line in self.checks(lines)]

    def sleeps(self, lines):
        return [line for line in lines if line.startswith("sleep")]

    def test_the_list_of_the_base_holds_the_three_endpoints_of_the_storage_account_and_the_cases_list_holds_the_cases_app_s(self):
        self.assertEqual(len(self.base), 3, "the storage account's three (blob, queue and table), and no app's own (the usage app was removed on 2026-11-07) and none of an Event Hubs namespace, which the base does not make")
        self.assertEqual([zone for _, zone in self.base], ["privatelink.blob.core.windows.net", "privatelink.queue.core.windows.net", "privatelink.table.core.windows.net"])
        self.assertNotIn("privatelink.servicebus.windows.net", [zone for _, zone in self.base])
        self.assertNotIn(self.ZONE_OF_THE_APPS, [zone for _, zone in self.base])
        self.assertEqual(self.cases, [(self.cases_endpoint, self.ZONE_OF_THE_APPS)])

    def test_the_base_wait_ends_at_once_when_all_three_endpoints_are_registered_and_asks_about_each_one(self):
        done, lines, _ = self.run_wait(self.BASE, "BASE_ENDPOINTS", self.base, self.registered(self.base))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("The landing zone's policy has registered every private endpoint of the base in its central zone.", done.stdout)
        self.assertEqual(self.named(lines), [endpoint for endpoint, _ in self.base])
        self.assertEqual(self.sleeps(lines), [])

    def test_an_endpoint_that_is_registered_later_than_the_others_keeps_the_base_waiting_and_is_the_one_that_the_message_names(self):
        done, lines, _ = self.run_wait(self.BASE, "BASE_ENDPOINTS", self.base, self.registered(self.base, **{self.last_endpoint: 3}))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"Not registered yet: {self.last_endpoint} (check 1 of 40).", done.stdout)
        self.assertIn(f"Not registered yet: {self.last_endpoint} (check 2 of 40).", done.stdout)
        self.assertNotIn("(check 3 of 40)", done.stdout, "registered at the third check")
        self.assertEqual((len(self.checks(lines)), self.sleeps(lines)), (9, ["sleep 60"] * 2), "three checks of three endpoints, and a minute between them")

    def test_an_endpoint_that_never_gets_its_zone_group_or_gets_another_zone_fails_the_base_and_says_what_it_means(self):
        others = [pair for pair in self.base if pair[0] != self.last_endpoint]
        for label, registered in (("no zone group", self.registered(others)),
                                  ("a zone group of another zone", self.registered(others) + [f"{self.last_endpoint}=privatelink.blob.core.windows.net"]),
                                  ("a zone whose name only ends like the zone of the endpoint", self.registered(others) + [f"{self.last_endpoint}=other-{self.last_zone}"])):
            done, lines, _ = self.run_wait(self.BASE, "BASE_ENDPOINTS", self.base, registered, two_checks=True)
            self.assertEqual(done.returncode, 1, label)
            self.assertEqual((len(self.checks(lines)), len(self.sleeps(lines))), (6, 2), f"{label}: two checks of three endpoints")
            self.assertIn(f"Not registered yet: {self.last_endpoint} (check 2 of 40).", done.stdout, label)
            self.assertIn(f"::error::The landing zone's policy has not registered these private endpoints in their central zones: {self.last_endpoint}. "
                          "An app that starts now could not reach its storage by its private name.", done.stdout, label)
            self.assertIn("do not create a private DNS zone", done.stdout)

    def test_the_base_gives_up_after_forty_checks_a_minute_apart_and_no_sleep_follows_the_last(self):
        pairs = [self.base[-2], self.base[-1]]
        self.assertEqual(pairs[-1][0], self.last_endpoint, "the table's endpoint is the last of the list")
        done, lines, _ = self.run_wait(self.BASE, "BASE_ENDPOINTS", pairs, self.registered(pairs[:1]))
        self.assertEqual(done.returncode, 1)
        self.assertEqual((len(self.checks(lines)), len(self.sleeps(lines))), (80, 39), "forty checks of two endpoints, and no sleep after the last check")
        self.assertEqual(set(self.sleeps(lines)), {"sleep 60"})
        self.assertIn(f"Not registered yet: {self.last_endpoint} (check 40 of 40).", done.stdout)

    def test_the_cases_wait_ends_at_once_asks_about_the_one_endpoint_of_the_cases_app_and_says_so(self):
        done, lines, _ = self.run_wait(self.CASES, "CASES_ENDPOINTS", self.cases, self.registered(self.cases))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("The landing zone's policy has registered the private endpoint of the cases app in its central zone.", done.stdout)
        self.assertEqual((self.named(lines), self.sleeps(lines)), ([self.cases_endpoint], []))
        self.assertEqual(self.checks(lines), [f"az network private-endpoint dns-zone-group list --resource-group {self.GROUP} --endpoint-name {self.cases_endpoint} "
                                              "--query [].privateDnsZoneConfigs[].privateDnsZoneId --output tsv"])

    def test_the_cases_wait_waits_a_minute_at_a_time_until_the_zone_group_comes_and_tries_a_check_that_fails_again(self):
        done, lines, _ = self.run_wait(self.CASES, "CASES_ENDPOINTS", self.cases, self.registered(self.cases, **{self.cases_endpoint: 4}))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((len(self.checks(lines)), self.sleeps(lines)), (4, ["sleep 60"] * 3))
        self.assertIn(f"Not registered yet: {self.cases_endpoint} (check 1 of 40).", done.stdout)
        done, lines, _ = self.run_wait(self.CASES, "CASES_ENDPOINTS", self.cases, self.registered(self.cases), failing=1)
        self.assertEqual(done.returncode, 0, "a check that fails is a check that finds nothing, and the next one is made")
        self.assertEqual((len(self.checks(lines)), self.sleeps(lines)), (2, ["sleep 60"]))

    def test_the_cases_wait_fails_after_forty_checks_when_the_zone_group_never_comes_and_says_that_the_app_was_not_given_its_code(self):
        done, lines, _ = self.run_wait(self.CASES, "CASES_ENDPOINTS", self.cases, [])
        self.assertEqual(done.returncode, 1)
        self.assertEqual((len(self.checks(lines)), len(self.sleeps(lines))), (40, 39), "forty checks a minute apart, and no sleep after the last")
        self.assertEqual(set(self.sleeps(lines)), {"sleep 60"})
        self.assertIn(f"Not registered yet: {self.cases_endpoint} (check 40 of 40).", done.stdout)
        self.assertIn(f"::error::The landing zone's policy has not registered the private endpoint of the cases app in its central zone: {self.cases_endpoint}. The cases app was not given its code.", done.stdout)
        self.assertIn("do not create a private DNS zone", done.stdout)

    def test_a_zone_group_of_another_zone_or_of_a_zone_that_only_ends_like_the_zone_of_the_apps_does_not_count_for_the_cases_app(self):
        for label, registered in (("a zone group of another zone", [f"{self.cases_endpoint}=privatelink.blob.core.windows.net"]),
                                  ("a zone whose name only ends like the zone of the apps", [f"{self.cases_endpoint}=other-{self.ZONE_OF_THE_APPS}"])):
            done, lines, _ = self.run_wait(self.CASES, "CASES_ENDPOINTS", self.cases, registered, two_checks=True)
            self.assertEqual(done.returncode, 1, label)
            self.assertEqual(len(self.checks(lines)), 2, label)
            self.assertIn("The cases app was not given its code.", done.stdout, label)

    def test_the_waits_only_read_the_zone_groups_and_make_no_zone(self):
        for title, variable, pairs in ((self.BASE, "BASE_ENDPOINTS", self.base), (self.CASES, "CASES_ENDPOINTS", self.cases)):
            done, lines, _ = self.run_wait(title, variable, pairs, self.registered(pairs))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(len(lines), len(pairs))
            for call in lines:
                self.assertRegex(call, r"^az network private-endpoint dns-zone-group list ")
                for word in ("create", "delete", "update", "private-dns", "role", "--yes", "--method"):
                    self.assertNotIn(word, call, call)


OPERATOR_FIND_AZ = """#!/bin/bash
# stand-in for az: FAKE_IDENTITY_ID is what the list of the identity prints, FAKE_CLIENT what the read of the identity prints (FAIL: it fails), FAKE_SUBNET is ok, absent or throttled
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) if [ "$FAKE_IDENTITY_ID" = "FAIL" ]; then echo "ERROR: fake az: the list is refused" >&2; exit 1; fi; printf '%s' "$FAKE_IDENTITY_ID" ;;
  *"/userAssignedIdentities/"*)
    if [ "$FAKE_CLIENT" = "FAIL" ]; then echo "ERROR: fake az: the identity is not readable" >&2; exit 1; fi
    printf '%s' "$FAKE_CLIENT" ;;
  *"/subnets/snet-ops"*)
    case "$FAKE_SUBNET" in
      ok) echo snet-ops ;;
      absent) echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops' under resource group 'rg-of-the-project' was not found." >&2; exit 1 ;;
      throttled) echo "ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later." >&2; exit 1 ;;
    esac ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

OPERATOR_QUEUE_AZ = """#!/bin/bash
# stand-in for az: FAKE_QUEUE is the name that the read of the queue prints; NOTFOUND: the queue is not there; THROTTLED: the read fails for another reason
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"/queueServices/default/queues/"*)
    case "$FAKE_QUEUE" in
      NOTFOUND) echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Storage/storageAccounts/stexample/queueServices/default/queues/cases-control' under resource group 'rg-of-the-project' was not found." >&2; exit 1 ;;
      THROTTLED) echo "ERROR: (TooManyRequests) Too many requests, try again later." >&2; exit 1 ;;
      *) printf '%s\\n' "$FAKE_QUEUE" ;;
    esac ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

OPERATOR_IDENTITY = "/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
OPERATOR_SUBNET = "/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"
OPERATOR_CLIENT = "6e5f3a1c-2b7d-4c8e-9f10-3a4b5c6d7e8f"


@unittest.skipIf(BASH is None, "no bash on this machine")
class FindTheOperator(unittest.TestCase):
    """The step that finds the Operator for cases-run: what it finds, what it says when the Operator is not there, and that it only reads."""

    TITLE = "Find the Operator, which runs the check from inside the network"

    def run_step(self, identity_id=OPERATOR_IDENTITY, client=OPERATOR_CLIENT, subnet="ok", action="cases-run"):
        return run_step_script(self.TITLE, {"az": OPERATOR_FIND_AZ},
                               {"FAKE_IDENTITY_ID": identity_id, "FAKE_CLIENT": client, "FAKE_SUBNET": subnet, "ACTION": action, "ENV_SUBSCRIPTION_ID": "sub-of-the-project",
                                "ENV_RESOURCE_GROUP": "rg-of-the-project"})

    def test_the_operator_that_is_there_is_found_and_its_ids_are_the_outputs_of_the_step(self):
        for action in ("cases-run",):
            done, lines, out = self.run_step(action=action)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(lines, ["az resource list --resource-group rg-of-the-project --name id-meternaut-operator --query [0].id --output tsv",
                                     f"az rest --method get --url https://management.azure.com{OPERATOR_IDENTITY}?api-version=2023-01-31 --query properties.clientId --output tsv",
                                     f"az rest --method get --url https://management.azure.com{OPERATOR_SUBNET}?api-version=2025-05-01 --query name --output tsv"])
            self.assertEqual(out.splitlines(), [f"identity_id={OPERATOR_IDENTITY}", f"client_id={OPERATOR_CLIENT}", f"subnet_id={OPERATOR_SUBNET}"])
            self.assertIn("The Operator's identity and its subnet are there.", done.stdout)

    def test_an_identity_that_is_not_there_stops_the_step_says_to_run_operator_first_and_gives_no_output(self):
        for answer in ("", "None", "FAIL", "id-meternaut-operator", "/not/a/subscription"):
            done, lines, out = self.run_step(identity_id=answer, action="cases-run")
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("The identity id-meternaut-operator is not there. The action cases-run runs its check in the Operator, so run operator first (the order is base, cases, operator). Nothing was changed.",
                          done.stdout, answer)
            self.assertEqual((len(lines), out), (1, ""), "the identity is not read and the subnet is not asked for when the list finds nothing")

    def test_an_identity_whose_client_id_cannot_be_read_is_not_there_either(self):
        for answer in ("", "None", "FAIL", "not-a-guid", f"{OPERATOR_CLIENT} x"):
            done, lines, out = self.run_step(client=answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("The identity id-meternaut-operator is not there.", done.stdout)
            self.assertIn("run operator first", done.stdout)
            self.assertEqual((len(lines), out), (2, ""))

    def test_a_subnet_that_is_not_there_says_to_run_operator_first_and_any_other_answer_stops_the_step_with_what_it_said(self):
        done, lines, out = self.run_step(subnet="absent")
        self.assertEqual((done.returncode, out), (1, ""))
        self.assertIn("The subnet snet-ops is not there. The action cases-run runs its check in the Operator, so run operator first (the order is base, cases, operator). Nothing was changed.", done.stdout)
        self.assertEqual(len(lines), 3)
        done, lines, out = self.run_step(subnet="throttled")
        self.assertEqual((done.returncode, out), (1, ""))
        self.assertIn("The subnet snet-ops could not be read: ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later.", done.stdout,
                      "an answer that holds the digits 404 inside an id is not taken for NotFound")
        self.assertNotIn("run operator first", done.stdout)

    def test_the_step_only_reads(self):
        for subnet in ("ok", "absent", "throttled"):
            _, lines, _ = self.run_step(subnet=subnet)
            for call in lines:
                self.assertRegex(call, r"^az (resource list|rest --method get) ")
                for word in (" create ", " delete ", " update ", " role ", " put ", " post ", " patch ", " container ", " login ", "--yes"):
                    self.assertNotIn(word, call + " ", call)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheControlQueueIsThereBeforeTheOperatorIsDeployed(unittest.TestCase):
    """The step of the action operator that reads the control queue, which the Operator is given a role on, before anything is deployed."""

    TITLE = "The control queue that the Operator is given a role on is there"
    URL = ("az rest --method get --url https://management.azure.com/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.Storage/storageAccounts/stexample"
           "/queueServices/default/queues/cases-control?api-version=2023-05-01 --query name --output tsv")

    def run_step(self, queue):
        return run_step_script(self.TITLE, {"az": OPERATOR_QUEUE_AZ},
                               {"FAKE_QUEUE": queue, "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project", "STORAGE_ACCOUNT": "stexample", "CASES_QUEUE": "cases-control"})

    def test_the_queue_there_ends_the_step_well_with_one_read(self):
        done, lines, _ = self.run_step("cases-control")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(lines, [self.URL])
        self.assertIn("The control queue is there.", done.stdout)

    def test_a_queue_that_is_missing_stops_the_step_and_says_which_action_makes_it_and_that_nothing_was_changed(self):
        for queue in ("NOTFOUND", "", "None"):
            done, _, _ = self.run_step(queue)
            self.assertEqual(done.returncode, 1, queue)
            self.assertIn("The control queue cases-control is not there. Run cases first (after base): it makes the queue.", done.stdout)
            self.assertIn("The Operator is given a role on the control queue, so the actions base and cases run before operator. Nothing was changed.", done.stdout)

    def test_a_name_that_only_looks_like_the_queue_is_not_the_queue(self):
        for queue in ("cases-control-poison", "my-cases-control", "Cases-Control", "cases-control "):
            done, _, _ = self.run_step(queue)
            self.assertEqual(done.returncode, 1, queue)
            self.assertIn("The control queue cases-control is not there.", done.stdout)

    def test_a_read_that_fails_for_another_reason_than_not_found_stops_the_step_with_what_it_said(self):
        done, _, _ = self.run_step("THROTTLED")
        self.assertEqual(done.returncode, 1)
        self.assertIn("The control queue cases-control could not be read: ERROR: (TooManyRequests) Too many requests, try again later.", done.stdout)
        self.assertNotIn("Run cases first", done.stdout, "an unreadable queue is not a missing queue")

    def test_the_step_only_reads(self):
        done, lines, _ = self.run_step("cases-control")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for call in lines:
            self.assertRegex(call, r"^az rest --method get ")
            for word in (" create ", " delete ", " update ", " role ", " put ", " post ", " patch ", "--yes"):
                self.assertNotIn(word, call + " ", call)


OPERATOR_RUN_PYTHON3 = """#!/bin/bash
# stand-in for python3: one line for the program and one line, indented, for each argument; FAKE_EXIT is the exit code
{ echo "python3"; for argument in "$@"; do echo "  $argument"; done; } >> "$FAKE_LOG"
exit "${FAKE_EXIT-0}"
"""


def called(lines):
    """The calls that a stand-in python3 logged: a list of argument lists (the first argument is the tool)."""
    calls = []
    for line in lines:
        if line == "python3":
            calls.append([])
        else:
            calls[-1].append(line[2:])
    return calls


def load_operator_tool():
    spec = importlib.util.spec_from_file_location("operator_run_of_the_workflow_tests", ROOT / "tools" / "operator-run.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def load_hubenv():
    spec = importlib.util.spec_from_file_location("hubenv_of_the_workflow_tests", Path(__file__).with_name("hubenv.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hubenv = load_hubenv()


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheChecksBuildTheCallOfTheOperatorTool(unittest.TestCase):
    """The steps of cases-run, run with bash against a stand-in for python3: the call of tools/operator-run.py that the check builds, and that the tool itself accepts it."""

    SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
    GROUP = "rg-of-the-project"
    SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"
    IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
    IMAGE = "mcr.microsoft.com/azure-cli@sha256:" + "ab" * 32
    INSIGHTS = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Insights/components/appi-meternaut"
    CASES = "Start one Watch and read its History"

    def run_check(self, title, dns="10.20.0.4,10.20.0.5", exit_code=0):
        env = {"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP, "ENV_DNS_SERVERS": dns, "GITHUB_RUN_ID": "1234567890", "OPERATOR_IMAGE": self.IMAGE,
               "STORAGE_ACCOUNT": "stexample", "INSIGHTS_NAME": "appi-meternaut", "OPERATOR_IDENTITY_ID": self.IDENTITY, "OPERATOR_CLIENT_ID": CLIENT,
               "OPERATOR_SUBNET_ID": self.SUBNET, "FAKE_EXIT": str(exit_code)}
        done, lines, _ = run_step_script(title, {"python3": OPERATOR_RUN_PYTHON3}, env)
        return done, called(lines)

    def expected(self, tool, files, args, seconds, dns=("10.20.0.4", "10.20.0.5")):
        return (["tools/operator-run.py", "run", "--resource-group", self.GROUP, "--name", "op-check-1234567890", "--subnet-id", self.SUBNET, "--identity-id", self.IDENTITY,
                 "--image", self.IMAGE, "--script", "operator/run-tool.sh"]
                + [word for name in files for word in ("--secret-file", f"{name}=tools/{name}")]
                + ["--env", "GITHUB_ACTIONS=true", "--env", f"OPERATOR_CLIENT_ID={CLIENT}", "--env", f"OPERATOR_SUBSCRIPTION={self.SUBSCRIPTION}", "--env", f"TOOL_NAME={tool}", "--env", f"TOOL_ARGS={args}"]
                + [word for server in dns for word in ("--dns-server", server)]
                + ["--timeout-seconds", str(seconds), "--summary"])

    def accepted_by_the_tool(self, argv):
        tool = load_operator_tool()
        args = tool.build_parser().parse_args(argv[1:])
        plain, secure, servers = tool.check_options(args)
        with contextlib.chdir(ROOT):
            files = tool.read_files(args)
        return args, dict(plain), secure, servers, files

    def test_the_watch_is_started_by_the_tool_in_the_operator_and_both_check_files_are_in_the_volume(self):
        done, calls = self.run_check(self.CASES)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (argv,) = calls
        self.assertEqual(argv[:-1], self.expected("cases-check", ["cases-check.py", "check-helpers.py"], f"run --storage-account stexample --insights {self.INSIGHTS} --minutes 30", 2400))
        self.assertTrue(argv[-1].endswith("summary.md"), "the log of the container goes into the summary of the run")
        args, plain, secure, servers, files = self.accepted_by_the_tool(argv)
        self.assertEqual((secure, servers), ([], ["10.20.0.4", "10.20.0.5"]), "no secure value: nothing in the call is a secret")
        self.assertEqual(plain["TOOL_ARGS"], f"run --storage-account stexample --insights {self.INSIGHTS} --minutes 30")
        self.assertEqual(sorted(files), ["cases-check.py", "check-helpers.py", "run-tool.sh"], "cases-check.py loads check-helpers.py from its own folder")
        self.assertEqual(files["run-tool.sh"], (ROOT / "operator" / "run-tool.sh").read_bytes().replace(b"\r\n", b"\n"))
        self.assertEqual((args.timeout_seconds, args.name, args.cpu, args.memory), (2400, "op-check-1234567890", 1.0, 1.5))

    def test_the_landing_zone_s_dns_servers_are_given_one_flag_each_and_none_when_there_are_none(self):
        for dns, servers in (("10.20.0.4", ["10.20.0.4"]), ("10.20.0.4,10.20.0.5,10.20.0.6", ["10.20.0.4", "10.20.0.5", "10.20.0.6"]), ("", [])):
            for title in (self.CASES,):
                done, calls = self.run_check(title, dns=dns)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                argv = calls[0]
                self.assertEqual([argv[i + 1] for i, word in enumerate(argv) if word == "--dns-server"], servers, (title, dns))

    def test_a_tool_that_fails_fails_the_step_and_the_step_calls_the_tool_once(self):
        for title in (self.CASES,):
            done, calls = self.run_check(title, exit_code=1)
            self.assertEqual(done.returncode, 1, title)
            self.assertEqual(len(calls), 1, "the group is made once: a second event would start a second job")
            done, calls = self.run_check(title, exit_code=124)
            self.assertEqual(done.returncode, 124, "the exit code of the tool is the exit code of the step, a timeout included")

    def test_the_list_of_the_functions_is_still_read_from_the_runner_before_the_group_is_made(self):
        for title, tool, app in (("Before the Watch is started, the cases app lists its four functions", "cases-check", "func-meternaut-cases-0a1b2c3d"),):
            done, lines, _ = run_step_script(title, {"python3": OPERATOR_RUN_PYTHON3}, {"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP, "SITE_NAME": app})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(called(lines), [[f"tools/{tool}.py", "functions", "--site", f"/subscriptions/{self.SUBSCRIPTION}/resourceGroups/{self.GROUP}/providers/Microsoft.Web/sites/{app}", "--minutes", "5"]])

    def test_the_cleanup_asks_the_tool_for_the_groups_of_the_checks_and_a_failure_is_only_a_warning(self):
        title = "Delete any container group of the checks that is left"
        env = {"ENV_RESOURCE_GROUP": self.GROUP}
        done, lines, _ = run_step_script(title, {"python3": OPERATOR_RUN_PYTHON3}, env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(called(lines), [["tools/operator-run.py", "cleanup", "--resource-group", self.GROUP, "--prefix", "op-check-", "--older-than-minutes", "0"]])
        done, lines, _ = run_step_script(title, {"python3": OPERATOR_RUN_PYTHON3}, {**env, "FAKE_EXIT": "1"})
        self.assertEqual(done.returncode, 0, "a group that could not be deleted does not fail a run that was good")
        self.assertIn("::warning::A container group whose name starts with op-check- may be left in resource group rg-of-the-project.", done.stdout)
        tool = load_operator_tool()
        args = tool.build_parser().parse_args(called(lines)[0][1:])
        self.assertEqual((args.prefix, args.older_than_minutes, args.resource_group), ("op-check-", 0.0, self.GROUP))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with hubenv.patched(extra={"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP}):
                self.assertEqual(tool.cleanup_command(args, lambda arguments: (0, "[]", "")), 0, "the prefix is one that the tool accepts")


READ_BACK_SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
READ_BACK_GROUP = "rg-of-the-project"
READ_BACK_ACCOUNT = "stmeternautfn0a1b2c3d"

READ_BACK_AZ = """#!/bin/bash
# stand-in for az: FAKE_STATE is what the read of the storage account prints (FAIL: it fails)
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  "rest --method get --url https://management.azure.com/subscriptions/"*"/providers/Microsoft.Storage/storageAccounts/"*"?api-version=2023-05-01 --query "*" --output tsv --only-show-errors")
    if [ "$FAKE_STATE" = "FAIL" ]; then echo "ERROR: (TooManyRequests) Too many requests, try again later." >&2; exit 1; fi
    printf '%s\\n' "$FAKE_STATE" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class ReadTheStorageAccountBack(unittest.TestCase):
    """The step of the action base that reads the storage account back from Azure after the deploy and fails the run unless it is private, has no key and has its three private endpoints approved. The account
    holds the host storage of the cases app and its control queue, so it is the one resource of the base that the control message depends on."""

    TITLE = "Read the storage account back from Azure, which has no public network access and no key"
    GOOD = "Disabled false Approved,Approved,Approved"

    def run_step(self, state):
        return run_step_script(self.TITLE, {"az": READ_BACK_AZ}, {"ENV_SUBSCRIPTION_ID": READ_BACK_SUBSCRIPTION, "ENV_RESOURCE_GROUP": READ_BACK_GROUP, "STORAGE_ACCOUNT": READ_BACK_ACCOUNT, "FAKE_STATE": state})

    def test_an_account_that_is_private_has_no_key_and_has_approved_endpoints_passes_with_one_read(self):
        for state in (self.GOOD, "Disabled False Approved,Approved,Approved", "Disabled false Approved,Approved,Approved,Approved"):
            with self.subTest(state=state):
                done, lines, _ = self.run_step(state)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(len(lines), 1)
                self.assertTrue(lines[0].startswith(f"az rest --method get --url https://management.azure.com/subscriptions/{READ_BACK_SUBSCRIPTION}/resourceGroups/{READ_BACK_GROUP}"
                                                    f"/providers/Microsoft.Storage/storageAccounts/{READ_BACK_ACCOUNT}?api-version=2023-05-01 --query "), lines[0])
                self.assertIn(f"The storage account {READ_BACK_ACCOUNT}, read back from Azure: public network access is Disabled, Shared Key access is off, and its private endpoint connections are Approved.",
                              done.stdout)

    def test_the_query_asks_for_the_three_properties_and_the_step_only_reads(self):
        _, lines, _ = self.run_step(self.GOOD)
        for word in ("properties.publicNetworkAccess", "properties.allowSharedKeyAccess", "properties.privateEndpointConnections", "privateLinkServiceConnectionState.status"):
            self.assertIn(word, lines[0])
        for word in (" put ", " post ", " patch ", " delete ", "role ", "--yes"):
            self.assertNotIn(word, lines[0] + " ")

    def test_each_way_that_the_account_is_not_as_the_template_wrote_it_fails_the_run_and_says_which(self):
        for state, words in (("Enabled false Approved,Approved,Approved", ["Public network access is 'Enabled', not 'Disabled'."]),
                             ("SecuredByPerimeter false Approved,Approved,Approved", ["Public network access is 'SecuredByPerimeter', not 'Disabled'."]),
                             ("null false Approved,Approved,Approved", ["Public network access is 'null', not 'Disabled'."]),
                             ("Disabled true Approved,Approved,Approved", ["Shared Key access is not off (allowSharedKeyAccess is 'true')."]),
                             ("Disabled null Approved,Approved,Approved", ["Shared Key access is not off (allowSharedKeyAccess is 'null')."]),
                             ("Disabled false", ["The account has fewer than three private endpoint connections (blob, queue and table): ''."]),
                             ("Disabled false Approved,Approved", ["The account has fewer than three private endpoint connections (blob, queue and table): 'Approved,Approved'."]),
                             ("Disabled false Approved,Approved,Pending", ["A private endpoint connection of the account is not Approved (Approved,Approved,Pending)."]),
                             ("Disabled false Approved,Rejected,Approved", ["A private endpoint connection of the account is not Approved (Approved,Rejected,Approved)."]),
                             ("Enabled true", ["Public network access is 'Enabled', not 'Disabled'.", "Shared Key access is not off", "The account has fewer than three private endpoint connections"])):
            with self.subTest(state=state):
                done, lines, _ = self.run_step(state)
                self.assertEqual(done.returncode, 1, state)
                self.assertIn(f"::error::The storage account {READ_BACK_ACCOUNT} is not as the template wrote it:", done.stdout)
                for word in words:
                    self.assertIn(word, done.stdout)
                self.assertIn("Nothing was changed by this step.", done.stdout)
                self.assertNotIn("read back from Azure:", done.stdout)

    def test_a_read_that_fails_fails_the_run_with_what_azure_said(self):
        done, lines, _ = self.run_step("FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(len(lines), 1)
        self.assertIn("::error::The storage account could not be read: ERROR: (TooManyRequests) Too many requests, try again later.", done.stdout)


PROBE_STEP_AZ = """#!/bin/bash
# stand-in for az in the probe step: the list that finds the Operator's identity, and the read of its client id
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) printf '%s' "$FAKE_IDENTITY_ID" ;;
  *"/userAssignedIdentities/"*) printf '%s' "$FAKE_CLIENT" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

PROBE_STEP_CURL = """#!/bin/bash
# stand-in for curl, which the probe step runs once: what it was given on the command line and on standard input (the bearer of the request for the token), and the answer that
# FAKE_CURL says: ok (one line), pretty (the lines of a printed document), fail (the exit code 22 of --fail), empty (a document without the token), or the answer itself
echo "curl $*" >> "$FAKE_LOG"
echo "curl-stdin $(cat)" >> "$FAKE_LOG"
case "$FAKE_CURL" in
  ok) printf '{"count":1234,"value":"%s"}' "$FAKE_TOKEN" ;;
  pretty) printf '{\\n  "count": 3,\\n  "value": "%s"\\n}\\n' "$FAKE_TOKEN" ;;
  fail) exit 22 ;;
  empty) printf '{"count":0}' ;;
  *) printf '%s' "$FAKE_CURL" ;;
esac
"""

PROBE_STEP_PYTHON3 = """#!/bin/bash
# stand-in for python3, which the probe step runs once as the tool: the arguments, one line each; the size and the hash of each file that --secret-file names, which the step has made by now;
# and what the environment of the call holds. Nothing is printed on standard output.
{
  echo "python3"
  for argument in "$@"; do echo "  $argument"; done
  echo "token-in-env=${AZURE_FEDERATED_TOKEN-unset}"
  previous=""
  for argument in "$@"; do
    if [ "$previous" = "--secret-file" ]; then
      name=${argument%%=*}
      path=${argument#*=}
      echo "file $name $(wc -c < "$path" | tr -d ' ') $(sha256sum < "$path" | cut -d' ' -f1)"
    fi
    previous=$argument
  done
} >> "$FAKE_LOG"
exit "${FAKE_EXIT-0}"
"""


PROBE_STEP_PRELUDE = """# Git's bash on Windows finds its own curl before the folder of the stand-ins, which the PATH of the process names first: put the folder first inside the shell
if command -v cygpath > /dev/null 2>&1; then PATH="$(cygpath -u "$FAKE_DIR")/bin:$PATH"; fi
"""


def split_calls(lines):
    """The log of the stand-ins as the calls of python3 (the arguments of each) and every other line, in order."""
    calls, other = [], []
    for line in lines:
        if line == "python3":
            calls.append([])
        elif line.startswith("  ") and calls:
            calls[-1].append(line[2:])
        else:
            other.append(line)
    return calls, other


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheProbeStepAsksForTheTokenOfTheDeployIdentity(unittest.TestCase):
    """The step that runs the probe in the Operator, run with bash against stand-ins for az, curl and python3: the token of the deploy identity, which GitHub issues to the run, is asked for
    with the bearer on standard input, masked, and given to the one call of the tool through its environment and nowhere else; and the probe still runs when there is none."""

    SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
    GROUP = "rg-of-the-project"
    IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
    IMAGE = "mcr.microsoft.com/azure-cli@sha256:" + "ab" * 32
    DEPLOY_CLIENT = "aaaaaaaa-0000-4000-8000-000000000001"
    DEPLOY_TENANT = "bbbbbbbb-0000-4000-8000-000000000002"
    TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJyZXBvOmV4YW1wbGUvZXhhbXBsZSJ9.c2lnbmF0dXJlLW9mLXRoZS10ZXN0LXRva2Vu"
    BEARER = "bearer-of-the-request-0123456789"
    URL = "https://token.example.net/_apis/oidc/idtoken?api-version=2.0"
    NO_REQUEST = "the job has no token request for OpenID Connect (the id-token permission)"

    def run_probe_step(self, curl="ok", request=True, exit_code=0, **changes):
        env = {"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP, "ENV_DNS_SERVERS": "10.20.0.4,10.20.0.5", "GITHUB_RUN_ID": "1234567890", "OPERATOR_IMAGE": self.IMAGE,
               "STORAGE_ACCOUNT": "stmeternaut0a1b2c3d",
               "FOUNDRY_ACCOUNT": "aif-meternaut-agents-0a1b2c3d", "CASES_APP": "func-meternaut-cases-0a1b2c3d",
               "DEPLOY_CLIENT_ID": self.DEPLOY_CLIENT, "DEPLOY_TENANT_ID": self.DEPLOY_TENANT, "FAKE_IDENTITY_ID": self.IDENTITY, "FAKE_CLIENT": OPERATOR_CLIENT, "FAKE_CURL": curl,
               "FAKE_TOKEN": self.TOKEN, "FAKE_EXIT": str(exit_code), "ACTIONS_ID_TOKEN_REQUEST_URL": self.URL if request else "",
               "ACTIONS_ID_TOKEN_REQUEST_TOKEN": self.BEARER if request else "", **changes}
        done, lines, _ = run_step_script("Run the probe in the Operator", {"az": PROBE_STEP_AZ, "curl": PROBE_STEP_CURL, "python3": PROBE_STEP_PYTHON3}, env, prelude=PROBE_STEP_PRELUDE)
        calls, other = split_calls(lines)
        return done, calls, other

    def environment_of(self, argv):
        return dict(argv[i + 1].split("=", 1) for i, word in enumerate(argv) if word == "--env")

    def test_the_token_is_asked_for_with_the_audience_and_the_bearer_on_standard_input_and_only_the_one_call_of_the_tool_gets_it(self):
        done, calls, other = self.run_probe_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (argv,) = calls
        self.assertIn(f"curl --silent --fail --max-time 30 --config - {self.URL}&audience=api://AzureADTokenExchange", other, "the audience that the federated credential trusts")
        self.assertIn(f'curl-stdin header = "Authorization: Bearer {self.BEARER}"', other, "the bearer of the request comes on standard input")
        self.assertEqual(sum(line.startswith("curl ") for line in other), 1, "one request")
        self.assertIn(f"token-in-env={self.TOKEN}", other, "the call of the tool has the token in its environment")
        self.assertEqual(argv.count("--secure-env"), 1)
        self.assertEqual(argv[argv.index("--secure-env") + 1], "AZURE_FEDERATED_TOKEN", "named and not given: the tool takes the value from the environment")
        for where, words in (("an argument of the tool", argv), ("a line of a stand-in", [line for line in other if not line.startswith("token-in-env=")])):
            for word in words:
                self.assertNotIn(self.TOKEN, word, where)
        for word in [word for call in calls for word in call] + [line for line in other if line.startswith("curl ") or line.startswith("az ")]:
            self.assertNotIn(self.BEARER, word, "the bearer of the request is on no command line")
        self.assertNotIn("PROBE_TOKEN_NOTE", self.environment_of(argv), "there is a token, so there is nothing to explain")
        for value in self.environment_of(argv).values():
            self.assertNotIn(self.TOKEN, value, "no --env value is the token")
        self.assertIn(f"::add-mask::{self.TOKEN}", done.stdout.splitlines(), "masked at once, before the tool is called")
        self.assertNotIn(self.TOKEN, done.stdout.replace(f"::add-mask::{self.TOKEN}", ""), "and printed nowhere else")
        self.assertNotIn(self.TOKEN, done.stderr)
        self.assertNotIn(self.BEARER, done.stdout + done.stderr)
        self.assertEqual([line for line in other if line.startswith("az ")], [
            "az resource list --resource-group rg-of-the-project --name id-meternaut-operator --query [0].id --output tsv",
            f"az rest --method get --url https://management.azure.com{self.IDENTITY}?api-version=2023-01-31 --query properties.clientId --output tsv"], "the runner reads two things and signs in as nobody")

    def test_the_names_of_the_apps_their_sites_the_lock_and_the_ids_of_the_deploy_identity_are_given_to_the_probe(self):
        done, calls, other = self.run_probe_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (argv,) = calls
        cases = "func-meternaut-cases-0a1b2c3d"
        scm = f"{cases}.scm.azurewebsites.net"
        env = self.environment_of(argv)
        self.assertEqual(env["PROBE_SCM_HOSTS"], scm)
        self.assertEqual(env["PROBE_NAMES"].split()[-1:], [f"{cases}.azurewebsites.net"])
        self.assertIn("stmeternaut0a1b2c3d.queue.core.windows.net", env["PROBE_NAMES"].split(), "the name of the control queue's host: the Operator puts the control message there")
        self.assertNotIn("servicebus", env["PROBE_NAMES"], "no Event Hubs namespace is asked about any more")
        self.assertEqual(env["PROBE_PRIVATE_NAMES"], f"{env['PROBE_NAMES']} {scm}", "the app and its site must resolve to private addresses: the app has a private endpoint")
        self.assertIn(f"https://{cases}.azurewebsites.net/healthz", env["PROBE_URLS"].split())
        self.assertEqual((env["PROBE_DEPLOY_CLIENT_ID"], env["PROBE_DEPLOY_TENANT_ID"]), (self.DEPLOY_CLIENT, self.DEPLOY_TENANT))
        self.assertEqual((env["OPERATOR_CLIENT_ID"], env["OPERATOR_GROUP"], env["OPERATOR_SUBSCRIPTION"]), (OPERATOR_CLIENT, self.GROUP, self.SUBSCRIPTION))
        lock = ROOT / "src" / "case-functions" / "requirements.txt"
        content = lock.read_bytes()
        self.assertEqual(env["PROBE_LOCK_BYTES"], str(len(content)), "the size that the probe compares the file in its volume with")
        files = {line.split()[1]: line.split()[2:] for line in other if line.startswith("file ")}
        self.assertEqual(files["cases-requirements.txt"], [str(len(content)), hashlib.sha256(content).hexdigest()], "the lock is sent whole, byte for byte")
        self.assertEqual(files["size-test"][0], env["PROBE_SIZE_BYTES"], "400,000 bytes, as the first probe sent")
        self.assertIn("cases-requirements.txt=src/case-functions/requirements.txt", argv)
        self.assertEqual(argv[argv.index("--timeout-seconds") + 1], "1200")
        self.assertEqual(argv[argv.index("--name") + 1], "op-probe-1234567890")

    def test_a_job_without_the_token_request_calls_the_tool_without_a_secure_value_and_says_why_and_the_step_still_succeeds(self):
        for changes in ({"request": False}, {"ACTIONS_ID_TOKEN_REQUEST_TOKEN": ""}, {"ACTIONS_ID_TOKEN_REQUEST_URL": ""}):
            done, calls, other = self.run_probe_step(**changes)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            (argv,) = calls
            self.assertNotIn("--secure-env", argv, changes)
            self.assertEqual(self.environment_of(argv)["PROBE_TOKEN_NOTE"], self.NO_REQUEST)
            self.assertFalse([line for line in other if line.startswith("curl ")], "no request is made when the job has none")
            self.assertIn("token-in-env=", other, "the environment of the call holds an empty value, which the probe takes for no token")
            self.assertIn(f"::warning::The probe goes on without a token for the deploy identity: {self.NO_REQUEST}.", done.stdout)
            self.assertNotIn("::add-mask::", done.stdout)

    def test_a_request_that_fails_or_an_answer_without_the_token_is_said_in_a_few_words_and_never_stops_the_step(self):
        for curl, note in (("fail", "the request for the token failed (curl exit code 22)"), ("empty", "the answer to the request for the token held none"),
                           ('{"message":"nope"}', "the answer to the request for the token held none"), ("", "the answer to the request for the token held none")):
            done, calls, other = self.run_probe_step(curl=curl)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            (argv,) = calls
            self.assertNotIn("--secure-env", argv, curl)
            self.assertEqual(self.environment_of(argv)["PROBE_TOKEN_NOTE"], note, curl)
            self.assertIn(f"::warning::The probe goes on without a token for the deploy identity: {note}.", done.stdout)
            self.assertNotIn("::add-mask::", done.stdout)
            self.assertNotIn(self.BEARER, done.stdout + done.stderr)

    def test_an_answer_that_is_a_printed_document_gives_the_token_too(self):
        done, calls, other = self.run_probe_step(curl="pretty")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"token-in-env={self.TOKEN}", other)
        self.assertIn(f"::add-mask::{self.TOKEN}", done.stdout.splitlines())

    def test_a_tool_that_fails_fails_the_step_and_the_step_calls_the_tool_once(self):
        for exit_code in (1, 124):
            done, calls, _ = self.run_probe_step(exit_code=exit_code)
            self.assertEqual(done.returncode, exit_code, "the exit code of the tool is the exit code of the step")
            self.assertEqual(len(calls), 1, "the group is made once")

    def test_the_call_is_accepted_by_the_tool_the_group_holds_the_token_once_as_a_secure_value_and_the_files_stay_below_its_limit(self):
        done, calls, other = self.run_probe_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (argv,) = calls
        tool = load_operator_tool()
        args = tool.build_parser().parse_args(argv[1:])
        with mock.patch.dict(os.environ, {"AZURE_FEDERATED_TOKEN": self.TOKEN}):
            plain, secure, servers = tool.check_options(args)
        self.assertEqual(secure, [("AZURE_FEDERATED_TOKEN", self.TOKEN)])
        self.assertEqual(servers, ["10.20.0.4", "10.20.0.5"])
        self.assertEqual(sorted(name for name, _ in plain), sorted(["OPERATOR_CLIENT_ID", "OPERATOR_GROUP", "OPERATOR_SUBSCRIPTION", "PROBE_NAMES", "PROBE_PRIVATE_NAMES", "PROBE_URLS", "PROBE_SIZE_BYTES",
                                                                   "PROBE_SCM_HOSTS", "PROBE_LOCK_BYTES", "PROBE_DEPLOY_CLIENT_ID", "PROBE_DEPLOY_TENANT_ID"]))
        probe = (ROOT / "operator" / "probe.sh").read_text(encoding="utf-8")
        read = set(re.findall(r"\b(?:PROBE|OPERATOR)_[A-Z_]+\b|\bAZURE_FEDERATED_TOKEN\b", probe))
        given = {name for name, _ in plain} | {"AZURE_FEDERATED_TOKEN"}
        self.assertEqual(read - given, {"PROBE_VOLUME", "PROBE_RESOLV_CONF", "PROBE_TMP", "PROBE_TOKEN_NOTE"}, "the probe reads what the step gives it, and the hooks of its tests, and why there is no token")
        self.assertEqual(given - read, set(), "and the step gives it nothing that it does not read")
        with tempfile.TemporaryDirectory() as tmp:
            size_file = Path(tmp) / "size-test"
            size_file.write_bytes(bytes(400_000))
            args.secret_file = [f"size-test={size_file}" if pair.startswith("size-test=") else pair for pair in args.secret_file]
            with contextlib.chdir(ROOT):
                files = tool.read_files(args)
        self.assertEqual(sorted(files), ["cases-requirements.txt", "probe.sh", "size-test"])
        self.assertEqual(files["cases-requirements.txt"], (ROOT / "src" / "case-functions" / "requirements.txt").read_bytes())
        self.assertEqual(len(files["cases-requirements.txt"]), int(dict(plain)["PROBE_LOCK_BYTES"]))
        self.assertLess(sum(len(content) for content in files.values()), tool.MAX_FILE_BYTES)
        document = tool.group_document(args, files, plain, secure, servers, "2026-11-06T07:00:00Z")
        variables = document["properties"]["containers"][0]["properties"]["environmentVariables"]
        self.assertEqual([variable for variable in variables if self.TOKEN in json.dumps(variable)], [{"name": "AZURE_FEDERATED_TOKEN", "secureValue": self.TOKEN}])
        self.assertEqual(json.dumps(document).count(self.TOKEN), 1, "once in the request, as a secure value, which Azure does not show again")
        self.assertNotIn(self.TOKEN, tool.Printer([self.TOKEN]).redact(f"a line that says {self.TOKEN} in the middle"))


PUBLISH_STEP_AZ = """#!/bin/bash
# stand-in for az in the publish steps, which only read: the list that finds the Operator's identity and the read of its subnet. FAKE_IDENTITY_ID is what the list prints (FAIL: it fails), FAKE_SUBNET
# is ok, absent or throttled. The container signs in as the deploy identity, so the step reads no client id and signs in as nobody: any other call of az is an error here.
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) if [ "$FAKE_IDENTITY_ID" = "FAIL" ]; then echo "ERROR: fake az: the list is refused" >&2; exit 1; fi; printf '%s' "$FAKE_IDENTITY_ID" ;;
  *"/subnets/snet-ops"*)
    case "$FAKE_SUBNET" in
      ok) echo snet-ops ;;
      absent) echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops' under resource group 'rg-of-the-project' was not found." >&2; exit 1 ;;
      throttled) echo "ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later." >&2; exit 1 ;;
    esac ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

PUBLISH_STEP_BASH = """#!/bin/bash
# stand-in for bash in the steps that pack the sources: it logs the call (with the switch that the step set) and makes the zip, FAKE_PACKAGE_BYTES long, where the step says (the fifth argument)
echo "bash $* [sources-only=${FUNCTION_APP_SOURCES_ONLY-unset}]" >> "$FAKE_LOG"
head -c "${FAKE_PACKAGE_BYTES-1000}" /dev/zero > "$5"
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class ThePublishStepsFindTheOperatorAskForTheTokenAndStartTheContainerGroup(unittest.TestCase):
    """The step that publishes the code of the cases app from inside the network (docs/proposals/07-private-by-default.md, phase 2), run with bash against stand-ins for az, curl and python3: the Operator is
    found by its name and nothing is changed; the token of the deploy identity is asked for with the bearer on standard input, masked and given to the one call of the tool through its environment and
    nowhere else; without a token nothing is published; and the call that is built is the one that the tool itself accepts."""

    SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
    GROUP = "rg-of-the-project"
    SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"
    IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
    IMAGE = "mcr.microsoft.com/azure-cli@sha256:" + "ab" * 32
    DEPLOY_CLIENT = "aaaaaaaa-0000-4000-8000-000000000001"
    DEPLOY_TENANT = "bbbbbbbb-0000-4000-8000-000000000002"
    TOKEN = TheProbeStepAsksForTheTokenOfTheDeployIdentity.TOKEN
    BEARER = TheProbeStepAsksForTheTokenOfTheDeployIdentity.BEARER
    URL = TheProbeStepAsksForTheTokenOfTheDeployIdentity.URL
    NO_REQUEST = TheProbeStepAsksForTheTokenOfTheDeployIdentity.NO_REQUEST
    PUBLISHES = {
        "cases": {"title": "Publish the cases to the function app from inside the network, in the Operator", "app": "func-meternaut-cases-0a1b2c3d", "action": "cases",
                  "file": "cases-source.zip", "seconds": "1200"},
    }

    def run_publish(self, kind, curl="ok", request=True, identity=None, subnet="ok", exit_code=0, dns="10.20.0.4,10.20.0.5", size=1234, plan="Flex"):
        want = self.PUBLISHES[kind]
        temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (temp / want["file"]).write_bytes(b"x" * size)
        env = {"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP, "ENV_DNS_SERVERS": dns, "GITHUB_RUN_ID": "1234567890", "OPERATOR_IMAGE": self.IMAGE,
               "ACTION": want["action"], "FUNCTION_APP": want["app"], "DEPLOY_CLIENT_ID": self.DEPLOY_CLIENT, "DEPLOY_TENANT_ID": self.DEPLOY_TENANT, "CASES_APP_PLAN": plan,
               "FAKE_IDENTITY_ID": self.IDENTITY if identity is None else identity, "FAKE_SUBNET": subnet, "FAKE_CURL": curl, "FAKE_TOKEN": self.TOKEN, "FAKE_EXIT": str(exit_code),
               "RUNNER_TEMP": temp.as_posix(), "GITHUB_STEP_SUMMARY": (temp / "summary.md").as_posix(),
               "ACTIONS_ID_TOKEN_REQUEST_URL": self.URL if request else "", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": self.BEARER if request else ""}
        done, lines, _ = run_step_script(want["title"], {"az": PUBLISH_STEP_AZ, "curl": PROBE_STEP_CURL, "python3": PROBE_STEP_PYTHON3}, env, prelude=PROBE_STEP_PRELUDE)
        calls, other = split_calls(lines)
        return done, calls, other, temp

    def expected(self, kind, temp, size, dns=("10.20.0.4", "10.20.0.5"), plan="Flex"):
        want = self.PUBLISHES[kind]
        files = [f"{want['file']}={temp.as_posix()}/{want['file']}", "build-function-app.sh=tools/build-function-app.sh"]
        # the app is told the plan kind that it runs on, which decides how the container publishes
        kinds = ["--env", f"PUBLISH_KIND={kind}", "--env", f"PUBLISH_PLAN={plan}"]
        return (["tools/operator-run.py", "run", "--resource-group", self.GROUP, "--name", "op-publish-1234567890", "--subnet-id", self.SUBNET, "--identity-id", self.IDENTITY, "--image", self.IMAGE,
                 "--script", "operator/publish.sh"]
                + [word for pair in files for word in ("--secret-file", pair)]
                + kinds + ["--env", f"PUBLISH_APP={want['app']}", "--env", f"PUBLISH_RESOURCE_GROUP={self.GROUP}", "--env", f"PUBLISH_SUBSCRIPTION={self.SUBSCRIPTION}",
                    "--env", f"PUBLISH_CLIENT_ID={self.DEPLOY_CLIENT}", "--env", f"PUBLISH_TENANT_ID={self.DEPLOY_TENANT}", "--env", f"PUBLISH_FILE_BYTES={size}", "--secure-env", "AZURE_FEDERATED_TOKEN"]
                + [word for server in dns for word in ("--dns-server", server)]
                + ["--timeout-seconds", want["seconds"], "--summary", (temp / "summary.md").as_posix()])

    def environment_of(self, argv):
        return dict(argv[i + 1].split("=", 1) for i, word in enumerate(argv) if word == "--env")

    def test_each_step_builds_the_call_of_the_tool_with_the_container_script_the_files_the_ids_of_the_deploy_identity_and_the_times(self):
        for kind in self.PUBLISHES:
            done, calls, other, temp = self.run_publish(kind, size=4321)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            (argv,) = calls
            self.assertEqual(argv, self.expected(kind, temp, 4321), kind)
            files = {line.split()[1]: line.split()[2] for line in other if line.startswith("file ")}
            self.assertEqual(files, {self.PUBLISHES[kind]["file"]: "4321", "build-function-app.sh": str((ROOT / "tools" / "build-function-app.sh").stat().st_size)},
                             f"{kind}: the sources and the build script go whole, and no package: the app is built in the container")
            self.assertEqual([line for line in other if line.startswith("az ")], [
                "az resource list --resource-group rg-of-the-project --name id-meternaut-operator --query [0].id --output tsv",
                f"az rest --method get --url https://management.azure.com{self.SUBNET}?api-version=2025-05-01 --query name --output tsv"],
                "the runner reads two things and signs in as nobody: the container signs in as the deploy identity")
            self.assertEqual(sum(line.startswith("curl ") for line in other), 1, "one request, for the token")

    def test_the_call_is_accepted_by_the_tool_and_the_group_holds_the_token_once_as_a_secure_value_and_the_files_stay_within_its_cap(self):
        tool = load_operator_tool()
        for kind, size in (("cases", 210_000),):
            done, calls, other, temp = self.run_publish(kind, size=size)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            (argv,) = calls
            args = tool.build_parser().parse_args(argv[1:])
            with mock.patch.dict(os.environ, {"AZURE_FEDERATED_TOKEN": self.TOKEN}):
                plain, secure, servers = tool.check_options(args)
            self.assertEqual(secure, [("AZURE_FEDERATED_TOKEN", self.TOKEN)])
            self.assertEqual(servers, ["10.20.0.4", "10.20.0.5"])
            self.assertEqual(sorted(name for name, _ in plain), sorted(["PUBLISH_KIND", "PUBLISH_PLAN", "PUBLISH_APP", "PUBLISH_RESOURCE_GROUP", "PUBLISH_SUBSCRIPTION", "PUBLISH_CLIENT_ID", "PUBLISH_TENANT_ID",
                                                                       "PUBLISH_FILE_BYTES"]))
            with contextlib.chdir(ROOT):
                files = tool.read_files(args)
            zip_name = self.PUBLISHES[kind]["file"]
            self.assertEqual(sorted(files), sorted(["build-function-app.sh", "publish.sh", zip_name]))
            self.assertEqual(files["publish.sh"], (ROOT / "operator" / "publish.sh").read_bytes().replace(b"\r\n", b"\n"), "the container runs the script of the repository")
            self.assertEqual(len(files[zip_name]), size)
            self.assertEqual(dict(plain)["PUBLISH_FILE_BYTES"], str(size), "the size that the container compares the file in its volume with")
            self.assertLess(sum(len(content) for content in files.values()), tool.MAX_FILE_BYTES)
            document = tool.group_document(args, files, plain, secure, servers, "2026-11-06T07:00:00Z")
            variables = document["properties"]["containers"][0]["properties"]["environmentVariables"]
            self.assertEqual([variable for variable in variables if self.TOKEN in json.dumps(variable)], [{"name": "AZURE_FEDERATED_TOKEN", "secureValue": self.TOKEN}])
            self.assertEqual(json.dumps(document).count(self.TOKEN), 1, "once in the request, as a secure value, which Azure does not show again")
            self.assertNotIn(self.TOKEN, tool.Printer([self.TOKEN]).redact(f"a line that says {self.TOKEN} in the middle"))

    def test_the_tool_refuses_the_call_of_a_publish_whose_sources_are_over_the_cap_with_the_evidence_and_takes_one_that_is_exactly_at_it(self):
        tool = load_operator_tool()
        # The tool reads the script with Unix line endings, whatever the checkout has, and the secret files as they are
        fixed = len((ROOT / "operator" / "publish.sh").read_bytes().replace(b"\r\n", b"\n")) + (ROOT / "tools" / "build-function-app.sh").stat().st_size
        for kind in self.PUBLISHES:
            room = tool.MAX_FILE_BYTES - fixed
            done, calls, other, temp = self.run_publish(kind, size=room)
            (argv,) = calls
            args = tool.build_parser().parse_args(argv[1:])
            with contextlib.chdir(ROOT):
                self.assertEqual(sum(len(content) for content in tool.read_files(args).values()), tool.MAX_FILE_BYTES, f"{kind}: exactly at the cap is taken")
            done, calls, other, temp = self.run_publish(kind, size=room + 1)
            (argv,) = calls
            args = tool.build_parser().parse_args(argv[1:])
            with contextlib.chdir(ROOT), self.assertRaises(tool.Problem) as refused:
                tool.read_files(args)
            self.assertIn("more than 480000 bytes", str(refused.exception))
            self.assertIn("466104", str(refused.exception), "the evidence: the largest request that was taken")
            self.assertIn("632656", str(refused.exception), "and the one that was refused")

    def test_the_token_is_asked_for_with_the_audience_and_the_bearer_on_standard_input_masked_and_given_to_the_one_call_of_the_tool_only_through_its_environment(self):
        for kind in self.PUBLISHES:
            done, calls, other, temp = self.run_publish(kind)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            (argv,) = calls
            self.assertIn(f"curl --silent --fail --max-time 30 --config - {self.URL}&audience=api://AzureADTokenExchange", other, "the audience that the federated credential trusts")
            self.assertIn(f'curl-stdin header = "Authorization: Bearer {self.BEARER}"', other, "the bearer of the request comes on standard input")
            self.assertIn(f"token-in-env={self.TOKEN}", other, "the call of the tool has the token in its environment")
            self.assertEqual(argv.count("--secure-env"), 1)
            self.assertEqual(argv[argv.index("--secure-env") + 1], "AZURE_FEDERATED_TOKEN", "named and not given: the tool takes the value from the environment")
            for word in argv + [line for line in other if not line.startswith("token-in-env=")]:
                self.assertNotIn(self.TOKEN, word, "on no command line and in no line of a stand-in")
            for word in [word for call in calls for word in call] + [line for line in other if line.startswith(("curl ", "az "))]:
                self.assertNotIn(self.BEARER, word, "the bearer of the request is on no command line")
            for value in self.environment_of(argv).values():
                self.assertNotIn(self.TOKEN, value, "no --env value is the token")
            self.assertIn(f"::add-mask::{self.TOKEN}", done.stdout.splitlines(), "masked at once")
            self.assertNotIn(self.TOKEN, done.stdout.replace(f"::add-mask::{self.TOKEN}", ""), "and printed nowhere else")
            self.assertNotIn(self.TOKEN, done.stderr)
            self.assertNotIn(self.BEARER, done.stdout + done.stderr)
            self.assertFalse((temp / "summary.md").exists() and self.TOKEN in (temp / "summary.md").read_text(encoding="utf-8"), "not in the summary of the run")
            for path in temp.rglob("*"):
                if path.is_file() and path.name != self.PUBLISHES[kind]["file"]:
                    self.assertNotIn(self.TOKEN.encode(), path.read_bytes(), f"not in a file of the run: {path.name}")

    def test_a_token_that_is_a_printed_document_is_found_too(self):
        for kind in self.PUBLISHES:
            done, calls, other, _ = self.run_publish(kind, curl="pretty")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn(f"token-in-env={self.TOKEN}", other)

    def test_without_a_token_nothing_is_published_and_the_step_fails_and_says_why(self):
        for kind in self.PUBLISHES:
            for changes, note in (({"request": False}, self.NO_REQUEST), ({"curl": "fail"}, "the request for the token failed (curl exit code 22)"),
                                  ({"curl": "empty"}, "the answer to the request for the token held none"), ({"curl": '{"message":"nope"}'}, "the answer to the request for the token held none"),
                                  ({"curl": ""}, "the answer to the request for the token held none")):
                done, calls, other, _ = self.run_publish(kind, **changes)
                self.assertEqual(done.returncode, 1, (kind, changes, done.stdout))
                self.assertEqual(calls, [], "the tool is not called: the container would not be able to sign in, and a group that cannot publish is not made")
                self.assertIn(f"::error::Nothing was published: the container signs in as the deploy identity with a token of this run, and this run has none: {note}.", done.stdout)
                self.assertNotIn("::add-mask::", done.stdout)
                self.assertNotIn(self.BEARER, done.stdout + done.stderr)

    def test_an_operator_that_is_not_there_says_to_run_operator_first_and_the_order_stops_before_a_token_is_asked_for(self):
        for kind, want in self.PUBLISHES.items():
            first_run = ("so run operator first, and then " + want["action"] + " again (the order on an estate that has none yet is base, cases, operator, and then cases again). "
                         "The template was deployed, and the app was not given its code.")
            for answer in ("", "None", "FAIL", "id-meternaut-operator", "/not/a/subscription"):
                done, calls, other, _ = self.run_publish(kind, identity=answer)
                self.assertEqual(done.returncode, 1, (kind, answer))
                self.assertIn(f"::error::The identity id-meternaut-operator is not there. The action {want['action']} publishes its code from inside the network, in the Operator, {first_run}", done.stdout)
                self.assertEqual((calls, [line for line in other if line.startswith("curl")]), ([], []), "no token is asked for and no group is made")
            done, calls, other, _ = self.run_publish(kind, subnet="absent")
            self.assertEqual(done.returncode, 1)
            self.assertIn(f"::error::The subnet snet-ops is not there. The action {want['action']} publishes its code from inside the network, in the Operator, {first_run}", done.stdout)
            self.assertEqual((calls, [line for line in other if line.startswith("curl")]), ([], []))
            done, calls, other, _ = self.run_publish(kind, subnet="throttled")
            self.assertEqual(done.returncode, 1)
            self.assertIn("::error::The subnet snet-ops could not be read: ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later.", done.stdout,
                          "an answer that holds the digits 404 inside an id is not taken for NotFound")
            self.assertNotIn("run operator first", done.stdout)
            self.assertEqual(calls, [])

    def test_the_landing_zone_s_dns_servers_are_given_one_flag_each_and_none_when_there_are_none(self):
        for dns, servers in (("10.20.0.4", ["10.20.0.4"]), ("10.20.0.4,10.20.0.5,10.20.0.6", ["10.20.0.4", "10.20.0.5", "10.20.0.6"]), ("", [])):
            for kind in self.PUBLISHES:
                done, calls, other, _ = self.run_publish(kind, dns=dns)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                argv = calls[0]
                self.assertEqual([argv[i + 1] for i, word in enumerate(argv) if word == "--dns-server"], servers, (kind, dns))

    def test_a_tool_that_fails_fails_the_step_with_its_exit_code_and_the_group_is_made_once(self):
        for kind in self.PUBLISHES:
            for exit_code in (1, 2, 124):
                done, calls, other, _ = self.run_publish(kind, exit_code=exit_code)
                self.assertEqual(done.returncode, exit_code, (kind, "the exit code of the tool is the exit code of the step, a timeout included"))
                self.assertEqual(len(calls), 1, "one group: a second one would publish twice")

    def test_the_step_only_reads_signs_in_as_nobody_and_runs_nothing_but_the_tool_on_the_runner(self):
        for kind in self.PUBLISHES:
            for subnet in ("ok", "absent", "throttled"):
                _, calls, other, _ = self.run_publish(kind, subnet=subnet)
                for call in (line for line in other if line.startswith("az ")):
                    self.assertRegex(call, r"^az (resource list|rest --method get) ")
                    for word in (" create ", " delete ", " update ", " role ", " put ", " post ", " patch ", " container ", " login ", " functionapp ", " webapp ", " account ", "--yes"):
                        self.assertNotIn(word, call + " ", call)
            self.assertEqual(sum(line.startswith(("bash", "unzip", "zip", "pip", "python3 -m")) for line in other), 0)

    def test_the_cleanup_asks_the_tool_for_the_groups_of_the_publishes_and_a_failure_is_only_a_warning(self):
        tool = load_operator_tool()
        for title in ("Delete any container group of the publish of the cases that is left",):
            env = {"ENV_RESOURCE_GROUP": self.GROUP}
            done, lines, _ = run_step_script(title, {"python3": OPERATOR_RUN_PYTHON3}, env)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(called(lines), [["tools/operator-run.py", "cleanup", "--resource-group", self.GROUP, "--prefix", "op-publish-", "--older-than-minutes", "0"]])
            done, lines, _ = run_step_script(title, {"python3": OPERATOR_RUN_PYTHON3}, {**env, "FAKE_EXIT": "1"})
            self.assertEqual(done.returncode, 0, "a group that could not be deleted does not fail a run that was good")
            self.assertIn("::warning::A container group whose name starts with op-publish- may be left in resource group rg-of-the-project.", done.stdout)
            args = tool.build_parser().parse_args(called(lines)[0][1:])
            self.assertEqual((args.prefix, args.older_than_minutes, args.resource_group), ("op-publish-", 0.0, self.GROUP))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with hubenv.patched(extra={"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP}):
                    self.assertEqual(tool.cleanup_command(args, lambda arguments: (0, "[]", "")), 0, "the prefix is one that the tool accepts")
        done, calls, other, _ = self.run_publish("cases")
        self.assertTrue(calls[0][calls[0].index("--name") + 1].startswith("op-publish-"), "the prefix of the cleanup is the start of the name that the publish gives its group")


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheSourcesAreCheckedAgainstTheCapOfTheToolBeforeTheOperatorIsLookedFor(unittest.TestCase):
    """The step that packs the cases app's sources for the Operator (docs/proposals/07-private-by-default.md, phase 2), run with bash against a stand-in for bash that makes the zip: everything that the request
    carries, the sources, the build script and the container script, is counted on the runner against the cap of tools/operator-run.py, with a message that names the cap and its evidence."""

    STEPS = {"cases": {"title": "Pack the cases app's sources for the Operator", "arguments": "case-functions cases", "stem": "cases-source", "label": "the cases app's sources"}}

    def run_pack(self, kind, zip_bytes):
        want = self.STEPS[kind]
        with tempfile.TemporaryDirectory() as temp:
            env = {"RUNNER_TEMP": Path(temp).as_posix(), "FAKE_PACKAGE_BYTES": str(zip_bytes)}
            done, lines, _ = run_step_script(want["title"], {"bash": PUBLISH_STEP_BASH}, env, prelude=PROBE_STEP_PRELUDE)
            return done, lines, Path(temp).as_posix()

    def fixed(self):
        """The bytes that go with the sources: the build script and the container script."""
        return (ROOT / "tools" / "build-function-app.sh").stat().st_size, (ROOT / "operator" / "publish.sh").stat().st_size

    def test_each_step_zips_the_sources_with_the_script_of_the_repository_in_its_sources_only_mode_and_says_that_the_files_fit(self):
        build_bytes, script_bytes = self.fixed()
        for kind, want in self.STEPS.items():
            done, lines, temp = self.run_pack(kind, 200_000)
            self.assertEqual(done.returncode, 0, (kind, done.stdout + done.stderr))
            self.assertEqual(lines, [f"bash tools/build-function-app.sh {want['arguments']} {temp}/{want['stem']} {temp}/{want['stem']}.zip [sources-only=1]"],
                             f"{kind}: the one script that builds, in the mode that copies and zips and installs nothing")
            self.assertIn(f"The files that go to the Operator are {200_000 + build_bytes + script_bytes} bytes, of the 480000 that a container group's request may hold.", done.stdout)

    def test_the_cap_is_the_one_of_the_tool_the_boundary_is_the_same_and_files_over_it_stop_the_step_with_the_evidence(self):
        tool = load_operator_tool()
        self.assertEqual(tool.MAX_FILE_BYTES, 480_000, "the cap that the steps check is the cap of the tool")
        self.assertEqual((tool.FILES_TAKEN_BYTES, tool.FILES_REFUSED_BYTES), (466_104, 632_656), "the evidence that the message gives is the tool's")
        build_bytes, script_bytes = self.fixed()
        room = tool.MAX_FILE_BYTES - build_bytes - script_bytes
        for kind, want in self.STEPS.items():
            done, _, _ = self.run_pack(kind, room)
            self.assertEqual(done.returncode, 0, f"{kind}: exactly at the cap: the tool refuses only what is more")
            done, _, _ = self.run_pack(kind, room + 1)
            self.assertEqual(done.returncode, 1, kind)
            self.assertIn(f"::error::The files that go to the Operator are {tool.MAX_FILE_BYTES + 1} bytes ({want['label']} {room + 1}, the build script {build_bytes}, the container script {script_bytes}), more than "
                          f"the {tool.MAX_FILE_BYTES} bytes of files that a container group's request may hold: a request with {tool.FILES_TAKEN_BYTES} bytes of files was taken, and one with "
                          f"{tool.FILES_REFUSED_BYTES} was refused with an internal server error (2026-11-06). The sources have to get smaller.", done.stdout, kind)
            self.assertNotIn("The files that go to the Operator are", done.stdout.replace("::error::The files that go to the Operator are", ""), "no 'fits' line after a refusal")

    def test_the_incident_that_the_cap_is_made_from_would_have_been_stopped_here_the_finished_cases_package_with_the_script_was_refused_by_azure(self):
        tool = load_operator_tool()
        self.assertEqual(tool.FILES_REFUSED_BYTES, 614_068 + 18_588, "the finished package of the cases app and the container script, on 2026-11-06")
        done, _, _ = self.run_pack("cases", 614_068)
        self.assertEqual(done.returncode, 1, "a package of that size, which the step no longer makes, is stopped on the runner before the Operator is looked for")
        self.assertIn("The sources have to get smaller.", done.stdout)


POWERSHELLS = []


def powershells():
    """The PowerShells that the hand steps are written for and that are on this machine: every PowerShell 7 that is found, and Windows PowerShell 5.1 on Windows."""
    if POWERSHELLS:
        return POWERSHELLS
    candidates = [shutil.which("pwsh"), shutil.which("powershell")]
    if os.name == "nt":
        candidates += [r"C:\Program Files\PowerShell\7\pwsh.exe", r"C:\Program Files (x86)\PowerShell\7\pwsh.exe"]
    found = {}
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            probe = subprocess.run([candidate, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = probe.stdout.strip()
        if probe.returncode == 0 and re.fullmatch(r"\d+(\.\d+)+", version):
            found.setdefault(version, candidate)
    POWERSHELLS.extend((f"PowerShell {version}", path) for version, path in sorted(found.items(), key=lambda item: [int(part) for part in item[0].split(".")]))
    return POWERSHELLS


def run_powershell(engine, script, env, directory):
    """Run a script file with the engine as a person who saved the commands would (-File), with no profile and no prompt."""
    path = Path(directory) / "run.ps1"
    path.write_text(script, encoding="utf-8", newline="\n")
    arguments = [engine, "-NoProfile", "-NonInteractive"] + (["-ExecutionPolicy", "Bypass"] if os.name == "nt" else [])
    return subprocess.run([*arguments, "-File", str(path)], capture_output=True, text=True, env={**os.environ, **env}, cwd=str(directory), timeout=180)


def hand_step_script():
    """The commands of the hand step of environment/BOOTSTRAP.md, as a person would copy them."""
    page = (ROOT / "environment" / "BOOTSTRAP.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    section = page.split("## Changed on 2026-11-06: the Foundry resource of the agents")[1].split("\n## ")[0]
    (script,) = re.findall(r"```powershell\n(.*?)\n```", section, re.S)
    return script


HAND_SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
HAND_GROUP = "rg-hub-example"
HAND_SCOPE = f"/subscriptions/{HAND_SUBSCRIPTION}/resourceGroups/{HAND_GROUP}"
HAND_ASSIGNMENT = f"{HAND_SCOPE}/providers/Microsoft.Authorization/roleAssignments/9c1f2a64-3a8e-4f64-8d0e-5d1f0b8a7c33"
FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
CONDITION_ROLES = ["5e0bd9bd-7b93-4f28-af87-19fc36ad61bd", "2b629674-e913-4c01-ae53-ef4638d8f975", "a638d3c7-ab3a-418d-83e6-5f17a39d4fde", "b7e6dc6d-f1e8-4753-8033-0f276bb0955b",
                   "974c5e8b-45b9-4653-ba55-5f855dd0fb88", "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3", "3913510d-42f4-4e42-8a64-420c390055eb"]


def condition_of(write_ids, delete_ids=None):
    """The condition that the templates write: the roles that may be given, and the roles that may be removed."""
    delete_ids = write_ids if delete_ids is None else delete_ids
    return ("((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {"
            + ", ".join(write_ids) + "} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND "
            "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {"
            + ", ".join(delete_ids) + "} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))")


def assignment(condition=..., **changes):
    """What `az role assignment list` prints for the Role Based Access Control Administrator assignment of the deploy identity."""
    document = {"condition": condition_of(CONDITION_ROLES) if condition is ... else condition, "conditionVersion": "2.0", "createdBy": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "createdOn": "2026-11-04T13:12:11.123456+00:00", "delegatedManagedIdentityResourceId": None, "description": None, "id": HAND_ASSIGNMENT,
                "name": HAND_ASSIGNMENT.rsplit("/", 1)[1], "principalId": PRINCIPAL, "principalName": "id-meternaut-deploy", "principalType": "ServicePrincipal",
                "resourceGroup": HAND_GROUP, "roleDefinitionId": f"/subscriptions/{HAND_SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/f58310d9-a9f6-439a-9e8d-f62e7b41a168",
                "roleDefinitionName": "Role Based Access Control Administrator", "scope": HAND_SCOPE, "type": "Microsoft.Authorization/roleAssignments",
                "updatedBy": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "updatedOn": "2026-11-04T13:12:11.123456+00:00"}
    document.update(changes)
    return document


def id_lists(condition):
    return [sorted(re.split(r",\s*", ids.strip())) for ids in re.findall(r"GuidEquals\s*\{([^}]*)\}", condition)]


def shape_of(condition):
    return re.sub(r"\s+", " ", re.sub(r"GuidEquals\s*\{[^}]*\}", "GuidEquals {ids}", condition))


# A stand-in for az that keeps the assignments in a file and answers like the CLI. It refuses what the CLI would refuse: a command that does not name the subscription, a list that is
# not the one of the deploy identity at the project group, and a JSON argument whose quotes are not doubled (they would not arrive). An update changes only what the service lets
# an update change: the condition, its version and the description.
FAKE_AZ_POWERSHELL = r"""$ErrorView = 'NormalView'
$devSub = $env:FAKE_SUBSCRIPTION
$hubGroup = $env:FAKE_GROUP
$principal = $env:FAKE_PRINCIPAL
function Read-Host { param($Prompt) Write-Host ('PROMPT: ' + $Prompt); $env:FAKE_ANSWER }
function Get-Arg { param($List, $Name) $i = [array]::IndexOf(@($List), $Name); if ($i -ge 0) { @($List)[$i + 1] } }
function Save-State { param($State) $State | ConvertTo-Json -Depth 20 | Set-Content -Path $env:FAKE_STATE -Encoding UTF8 }
function Set-Failure { param($Text, $Code) [Console]::Error.WriteLine($Text); $global:LASTEXITCODE = $Code }
function az {
  Add-Content -Path $env:FAKE_LOG -Value (ConvertTo-Json -InputObject @($args | ForEach-Object { [string]$_ }) -Compress)
  $state = Get-Content -Raw -Path $env:FAKE_STATE | ConvertFrom-Json
  $kind = "$($args[0]) $($args[1]) $($args[2])"
  if ((Get-Arg $args '--subscription') -ne $env:FAKE_SUBSCRIPTION) { Set-Failure 'ERROR: fake az: the command does not name the subscription of the pilot' 3; return }
  if ($kind -eq 'role assignment list') {
    if ((Get-Arg $args '--assignee-object-id') -ne $env:FAKE_PRINCIPAL -or (Get-Arg $args '--scope') -ne ('/subscriptions/' + $env:FAKE_SUBSCRIPTION + '/resourceGroups/' + $env:FAKE_GROUP) -or (Get-Arg $args '--role') -ne 'Role Based Access Control Administrator') { Set-Failure 'ERROR: fake az: the list is not the one of the deploy identity at the project group' 3; return }
    if ($env:FAKE_LIST_FAILS -eq '1') { Set-Failure 'ERROR: (TooManyRequests) fake az: try again later' 1; return }
    $items = @($state.assignments)
    $query = Get-Arg $args '--query'
    if ($query -eq 'length(@)') { "$($items.Count)"; $global:LASTEXITCODE = 0; return }
    if ($query -eq '[0]') { if ($items.Count -gt 0) { $items[0] | ConvertTo-Json -Depth 20 } else { 'null' }; $global:LASTEXITCODE = 0; return }
    Set-Failure ('ERROR: fake az: unexpected query ' + $query) 9; return
  }
  if ($kind -eq 'role assignment update') {
    $raw = Get-Arg $args '--role-assignment'
    if ($null -eq $raw -or ($raw -replace '""', '') -match '"') { Set-Failure 'ERROR: fake az: a quote of the JSON is not doubled, so the CLI would not get the JSON as it is' 2; return }
    try { $given = ($raw -replace '""', '"') | ConvertFrom-Json } catch { Set-Failure 'ERROR: fake az: the role assignment is not valid JSON' 2; return }
    if ($env:FAKE_UPDATE_FAILS -eq '1') { Set-Failure 'ERROR: (AuthorizationFailed) fake az: the update is refused' 1; return }
    $match = @($state.assignments | Where-Object { $_.id -eq $given.id })
    if ($match.Count -ne 1) { Set-Failure 'ERROR: (RoleAssignmentNotFound) fake az: no assignment has that id' 1; return }
    $stored = $match[0]
    $stored.condition = if ($env:FAKE_STORE_CONDITION) { $env:FAKE_STORE_CONDITION } else { $given.condition }
    $stored.conditionVersion = $given.conditionVersion
    $stored.description = $given.description
    if ($env:FAKE_STORE_ID) { $stored.id = $env:FAKE_STORE_ID }
    if ($env:FAKE_UPDATE_ADDS -eq '1') { $copy = ($stored | ConvertTo-Json -Depth 20) | ConvertFrom-Json; $copy.id = $copy.id + '-second'; $state.assignments = @($state.assignments) + $copy }
    Save-State $state
    $global:LASTEXITCODE = 0
    return
  }
  Set-Failure ('ERROR: fake az: unexpected call ' + $kind) 9
}
"""


class TheFoundryUserHandStep(unittest.TestCase):
    """The commands of environment/BOOTSTRAP.md that add the Foundry User role to the condition of the deploy identity's assignment, run in every PowerShell on the machine against a stand-in for az."""

    @classmethod
    def setUpClass(cls):
        cls.engines = powershells()
        if not cls.engines:
            raise unittest.SkipTest("no PowerShell on this machine")
        first, cls.rest = hand_step_script().split("\n", 1)
        assert first.startswith("function az {"), "the first line of the commands is the az function, which the stand-in replaces"

    def run_step(self, engine, assignments, answer="yes", **flags):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "state.json").write_text(json.dumps({"assignments": assignments}), encoding="utf-8")
            (tmp / "calls.log").write_text("", encoding="utf-8")
            env = {"FAKE_STATE": str(tmp / "state.json"), "FAKE_LOG": str(tmp / "calls.log"), "FAKE_ANSWER": answer, "FAKE_SUBSCRIPTION": HAND_SUBSCRIPTION, "FAKE_GROUP": HAND_GROUP,
                   "FAKE_PRINCIPAL": PRINCIPAL, **flags}
            done = run_powershell(engine, FAKE_AZ_POWERSHELL + "\n" + self.rest, env, tmp)
            calls = [json.loads(line) for line in (tmp / "calls.log").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            left = json.loads((tmp / "state.json").read_text(encoding="utf-8-sig"))["assignments"]
        return done, calls, left

    def said(self, done):
        return re.sub(r"\s+", " ", done.stdout + " " + done.stderr)

    def kinds(self, calls):
        return [" ".join(call[:3]) for call in calls]

    def first_engine(self):
        return self.engines[0][1]

    def test_a_good_run_changes_the_condition_in_place_with_one_write_and_reads_it_back(self):
        for name, engine in self.engines:
            with self.subTest(engine=name):
                done, calls, left = self.run_step(engine, [assignment()])
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(self.kinds(calls), ["role assignment list"] * 2 + ["role assignment update"] + ["role assignment list"] * 2, "read, read, one write, read back, read back")
                for call in calls:
                    self.assertEqual(call[call.index("--subscription") + 1], HAND_SUBSCRIPTION, call)
                (update,) = [call for call in calls if call[2] == "update"]
                self.assertEqual(update[:6], ["role", "assignment", "update", "--subscription", HAND_SUBSCRIPTION, "--role-assignment"])
                self.assertEqual(update[7:], ["--output", "none"])
                sent = json.loads(update[6].replace('""', '"'))
                self.assertEqual(sent["id"], HAND_ASSIGNMENT, "the assignment that is changed is the one that was read")
                self.assertEqual(id_lists(sent["condition"]), [sorted(CONDITION_ROLES + [FOUNDRY_USER])] * 2)
                (stored,) = left
                self.assertEqual(stored["id"], HAND_ASSIGNMENT, "the assignment keeps its id")
                self.assertEqual(id_lists(stored["condition"]), [sorted(CONDITION_ROLES + [FOUNDRY_USER])] * 2, "the Foundry User role is in the list for a write and in the list for a delete")
                self.assertEqual(shape_of(stored["condition"]), shape_of(assignment()["condition"]), "nothing else of the condition changed")
                for key in ("principalId", "scope", "roleDefinitionName", "roleDefinitionId", "principalType", "conditionVersion"):
                    self.assertEqual(stored[key], assignment()[key], key)
                text = self.said(done)
                self.assertIn("PROMPT: Change the condition as shown? Type yes", text)
                self.assertIn(f"Added: {FOUNDRY_USER} (Azure AI User, named Foundry User since the rename)", text)
                self.assertIn(f"Read back: one assignment, with the same id, and both lists hold the old role ids and {FOUNDRY_USER} (Foundry User).", text)
                self.assertFalse([call for call in calls if call[2] in ("delete", "create")], "the commands never delete or make an assignment")

    def test_an_update_that_fails_stops_the_script_and_says_that_the_assignment_is_unchanged(self):
        for name, engine in self.engines:
            with self.subTest(engine=name):
                before = [assignment()]
                done, calls, left = self.run_step(engine, before, FAKE_UPDATE_FAILS="1")
                self.assertNotEqual(done.returncode, 0)
                text = self.said(done)
                self.assertIn("The update failed (exit code 1). It is one write and nothing else was done, so the assignment is unchanged.", text)
                self.assertIn("az role assignment list --subscription " + HAND_SUBSCRIPTION, text, "it says how to read the assignment")
                self.assertNotIn("Read back", text)
                self.assertEqual(self.kinds(calls), ["role assignment list"] * 2 + ["role assignment update"], "the update is the last call: nothing is made, removed or read after it")
                self.assertEqual(left, before, "the assignment is as it was")

    def test_a_read_back_that_does_not_show_what_was_written_fails_the_script(self):
        # the service takes the update and the assignment comes out other than meant: a policy that rewrites the condition, a condition that holds the role in one list only,
        # a second assignment, another id
        broken = (("the condition came back without the new role", {"FAKE_STORE_CONDITION": condition_of(CONDITION_ROLES)}, "not as meant"),
                  ("only the list for a write holds the new role", {"FAKE_STORE_CONDITION": condition_of(CONDITION_ROLES + [FOUNDRY_USER], CONDITION_ROLES)}, "not as meant"),
                  ("a second assignment appeared", {"FAKE_UPDATE_ADDS": "1"}, "assignments, not one"),
                  ("the assignment has another id", {"FAKE_STORE_ID": HAND_ASSIGNMENT + "-other"}, "not as meant"))
        for index, (label, flags, words) in enumerate(broken):
            for name, engine in (self.engines if index == 0 else self.engines[:1]):
                with self.subTest(engine=name, label=label):
                    done, calls, _ = self.run_step(engine, [assignment()], **flags)
                    self.assertNotEqual(done.returncode, 0)
                    text = self.said(done)
                    self.assertIn("Read back:", text)
                    self.assertIn(words, text)
                    self.assertNotIn("Read back: one assignment, with the same id", text)
                    self.assertEqual(self.kinds(calls).count("role assignment update"), 1)

    def test_nothing_is_written_unless_the_person_types_yes(self):
        for answer in ("no", "yes please"):
            with self.subTest(answer=answer):
                done, calls, left = self.run_step(self.first_engine(), [assignment()], answer=answer)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("Stopped. Nothing was changed.", self.said(done))
                self.assertEqual(self.kinds(calls), ["role assignment list"] * 2)
                self.assertEqual(left, [assignment()])

    def test_nothing_is_written_when_there_is_not_exactly_one_assignment(self):
        for label, assignments, count in (("none", [], "0"), ("two", [assignment(), assignment(id=HAND_ASSIGNMENT + "-2")], "2")):
            with self.subTest(label=label):
                done, calls, left = self.run_step(self.first_engine(), assignments)
                self.assertNotEqual(done.returncode, 0)
                text = self.said(done)
                self.assertIn("must have exactly one Role Based Access Control Administrator assignment on the project group, and the list says '" + count + "'. Nothing was changed.", text)
                self.assertEqual(self.kinds(calls), ["role assignment list"])
                self.assertEqual(left, assignments)

    def test_nothing_is_written_when_the_condition_is_not_the_one_of_the_templates(self):
        other_clause = condition_of(CONDITION_ROLES).replace("AND ((!(", "AND (@Resource[a:b] StringEquals 'c') AND ((!(")
        one_list = "((!(ActionMatches{'x'})) OR (@Request[a:b] ForAnyOfAnyValues:GuidEquals {" + CONDITION_ROLES[0] + "}))"
        for label, condition, words in (("the two lists differ", condition_of(CONDITION_ROLES, CONDITION_ROLES[:-1]), "two lists of the same role ids"),
                                        ("one list only", one_list, "two lists of the same role ids"),
                                        ("no condition", None, "two lists of the same role ids"),
                                        ("a clause that the templates do not write", other_clause, "differs from the templates in more than the role ids")):
            with self.subTest(label=label):
                before = [assignment(condition)]
                done, calls, left = self.run_step(self.first_engine(), before)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(words, self.said(done))
                self.assertEqual(self.kinds(calls), ["role assignment list"] * 2)
                self.assertEqual(left, before)

    def test_a_condition_that_lists_the_role_already_means_nothing_to_do(self):
        done, calls, _ = self.run_step(self.first_engine(), [assignment(condition_of(CONDITION_ROLES + [FOUNDRY_USER]))])
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The condition lists the Foundry User role already: nothing to do.", self.said(done))
        self.assertEqual(self.kinds(calls), ["role assignment list"] * 2)

    def test_a_list_that_fails_stops_the_script_before_anything_is_written(self):
        done, calls, left = self.run_step(self.first_engine(), [assignment()], FAKE_LIST_FAILS="1")
        self.assertNotEqual(done.returncode, 0)
        text = self.said(done)
        self.assertIn("The assignments could not be read (exit code 1). Nothing was changed.", text)
        self.assertEqual(self.kinds(calls), ["role assignment list"])
        self.assertEqual(left, [assignment()])


def operator_hand_step_script():
    """The commands of the hand step of the Operator in environment/BOOTSTRAP.md (the Reader role), as a person would copy them."""
    page = (ROOT / "environment" / "BOOTSTRAP.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    section = page.split("## Changed on 2026-11-06: the Operator")[1].split("\n## ")[0]
    (script,) = re.findall(r"```powershell\n(.*?)\n```", section, re.S)
    return script


READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"


class TheReaderHandStep(unittest.TestCase):
    """The commands of the Operator's section of environment/BOOTSTRAP.md that add the Reader role to the condition of the deploy identity's assignment: the same stand-in for az and the same
    harness as the hand step of the Foundry User role, so that what is tested is what a person would paste."""

    run_step = TheFoundryUserHandStep.run_step
    said = TheFoundryUserHandStep.said
    kinds = TheFoundryUserHandStep.kinds
    first_engine = TheFoundryUserHandStep.first_engine

    @classmethod
    def setUpClass(cls):
        cls.engines = powershells()
        if not cls.engines:
            raise unittest.SkipTest("no PowerShell on this machine")
        first, cls.rest = operator_hand_step_script().split("\n", 1)
        assert first.startswith("function az {"), "the first line of the commands is the az function, which the stand-in replaces"

    def test_a_good_run_changes_the_condition_in_place_with_one_write_adds_reader_to_both_lists_and_reads_it_back(self):
        done, calls, left = self.run_step(self.first_engine(), [assignment()])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.kinds(calls), ["role assignment list"] * 2 + ["role assignment update"] + ["role assignment list"] * 2, "read, read, one write, read back, read back")
        (update,) = [call for call in calls if call[2] == "update"]
        sent = json.loads(update[6].replace('""', '"'))
        self.assertEqual(sent["id"], HAND_ASSIGNMENT, "the assignment that is changed is the one that was read")
        (stored,) = left
        self.assertEqual(stored["id"], HAND_ASSIGNMENT, "the assignment keeps its id")
        self.assertEqual(id_lists(stored["condition"]), [sorted(CONDITION_ROLES + [READER])] * 2, "Reader is in the list for a write and in the list for a delete")
        self.assertEqual(shape_of(stored["condition"]), shape_of(assignment()["condition"]), "nothing else of the condition changed")
        text = self.said(done)
        self.assertIn(f"Added: {READER} (Reader)", text)
        self.assertIn(f"Read back: one assignment, with the same id, and both lists hold the old role ids and {READER} (Reader).", text)
        self.assertFalse([call for call in calls if call[2] in ("delete", "create")], "the commands never delete or make an assignment")

    def test_every_powershell_on_the_machine_runs_it_the_same_way(self):
        for name, engine in self.engines[1:]:
            with self.subTest(engine=name):
                done, calls, left = self.run_step(engine, [assignment()])
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(id_lists(left[0]["condition"]), [sorted(CONDITION_ROLES + [READER])] * 2)

    def test_an_update_that_fails_says_that_the_assignment_is_unchanged_and_nothing_is_written_without_a_yes(self):
        before = [assignment()]
        done, calls, left = self.run_step(self.first_engine(), before, FAKE_UPDATE_FAILS="1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The update failed (exit code 1). It is one write and nothing else was done, so the assignment is unchanged.", self.said(done))
        self.assertEqual((self.kinds(calls)[-1], left), ("role assignment update", before))
        done, calls, left = self.run_step(self.first_engine(), before, answer="no")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Stopped. Nothing was changed.", self.said(done))
        self.assertEqual((self.kinds(calls), left), (["role assignment list"] * 2, before))

    def test_a_condition_that_lists_reader_already_means_nothing_to_do_and_a_read_back_that_differs_fails(self):
        done, calls, _ = self.run_step(self.first_engine(), [assignment(condition_of(CONDITION_ROLES + [READER]))])
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The condition lists the Reader role already: nothing to do.", self.said(done))
        self.assertEqual(self.kinds(calls), ["role assignment list"] * 2)
        done, calls, _ = self.run_step(self.first_engine(), [assignment()], FAKE_STORE_CONDITION=condition_of(CONDITION_ROLES))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not as meant", self.said(done))


@unittest.skipUnless(os.name == "nt", "the az function of the hand step calls the Azure CLI of Windows")
class TheJsonOfTheUpdateReachesTheCli(unittest.TestCase):
    """The az function and the update command of the hand step, with a program in place of the CLI that prints the arguments that it got. The JSON must arrive as it was sent, in every PowerShell
    on the machine: Windows PowerShell 5.1 takes a backslash before a quote differently from PowerShell 7, and PowerShell 7.3 and later escape the quotes themselves."""

    @classmethod
    def setUpClass(cls):
        cls.engines = powershells()
        if not cls.engines:
            raise unittest.SkipTest("no PowerShell on this machine")
        cls.script = hand_step_script()

    def test_the_json_reaches_the_program_unchanged(self):
        first = self.script.split("\n", 1)[0]
        cli = "'C:\\Program Files\\Microsoft SDKs\\Azure\\CLI2\\python.exe' -IBm azure.cli"
        self.assertIn(cli, first)
        (update,) = [line for line in self.script.splitlines() if line.startswith("az role assignment update")]
        new = assignment(condition_of(CONDITION_ROLES + [FOUNDRY_USER]))
        for name, engine in self.engines:
            with self.subTest(engine=name), tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                (tmp / "argv.py").write_text("import json\nimport sys\n\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
                (tmp / "assignment.json").write_text(json.dumps(new), encoding="utf-8")
                program = "\n".join([f"$devSub = '{HAND_SUBSCRIPTION}'", first.replace(cli, f"'{sys.executable}' '{tmp / 'argv.py'}'"),
                                     f"$old = Get-Content -Raw -Path '{tmp / 'assignment.json'}' | ConvertFrom-Json", "$json = $old | ConvertTo-Json -Depth 20 -Compress",
                                     f"[IO.File]::WriteAllText('{tmp / 'sent.json'}', $json)", update, ""])
                done = run_powershell(engine, program, {}, tmp)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                got = json.loads(done.stdout.strip().splitlines()[-1])
                self.assertEqual(got[:6], ["role", "assignment", "update", "--subscription", HAND_SUBSCRIPTION, "--role-assignment"])
                self.assertEqual(got[7:], ["--output", "none"])
                self.assertEqual(got[6], (tmp / "sent.json").read_text(encoding="utf-8"), "the CLI gets the JSON that the script made, character for character")
                self.assertEqual(json.loads(got[6])["id"], HAND_ASSIGNMENT)


@unittest.skipIf(BASH is None, "no bash on this machine")
class WhatWasDone(unittest.TestCase):
    """The step that writes the summary of a run, run once for every action of the workflow and for a run that finished and one that did not."""

    def run_all(self, status):
        actions = re.findall(r"- (\S+)", re.search(r"options:\n((?:          - .+\n)+)", WORKFLOW).group(1))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            summary = tmp / "summary.md"
            summary.write_text("", encoding="utf-8")
            script = tmp / "all.sh"
            script.write_text("summary_of() {\n" + step_script("What was done") + "\n}\nfor ACTION in " + " ".join(actions) + "; do\n  export ACTION\n  summary_of\ndone\n", encoding="utf-8", newline="\n")
            env = {**os.environ, "JOB_STATUS": status, "FOUNDRY_ACCOUNT": "aif-meternaut-agents-abc", "FOUNDRY_PROJECT": "meternaut",
                   "FOUNDRY_ENDPOINT": "https://aif-meternaut-agents-abc.services.ai.azure.com/api/projects/meternaut", "ENV_RESOURCE_GROUP": "rg-of-the-project",
                   "GITHUB_STEP_SUMMARY": summary.as_posix()}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            text = summary.read_text(encoding="utf-8")
        return done, actions, dict(re.findall(r"(?ms)^### Hub: ([a-z0-9-]+), \w+\n(.*?)(?=^### Hub: |\Z)", text))

    def test_every_action_has_words_for_a_run_that_finished_and_for_one_that_did_not_and_the_shell_says_nothing_of_its_own(self):
        for status in ("success", "failure"):
            with self.subTest(status=status):
                done, actions, sections = self.run_all(status)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stderr, "", "a backtick that is not escaped inside the quotes runs a command in bash, which says 'command not found' and leaves the name out")
                self.assertEqual(sorted(sections), sorted(actions))
                for action, body in sections.items():
                    self.assertGreater(len(body.strip()), 60, (status, action))

    def test_no_summary_speaks_of_an_action_that_made_objects_on_the_instance_or_of_a_contract_or_a_module_or_a_logger_that_is_gone(self):
        for status in ("success", "failure"):
            with self.subTest(status=status):
                done, actions, sections = self.run_all(status)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(sorted(sections), sorted(actions))
                for action, body in sections.items():
                    for word in ("gateway-prepare", "`gateway`", "`contract`", "Citadel module", "contract", "Event Hub logger", "the key of a contract", "gateway identity"):
                        self.assertNotIn(word, body, (status, action, word))

    def test_the_name_of_the_retired_identity_is_printed_in_the_summary_of_the_cases(self):
        done, _, sections = self.run_all("success")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("The retired identity of the first loop, `id-meternaut-runner`, is removed when it is still there and nothing holds it.", sections["cases"])

    def test_the_watch_changes_no_resource_of_the_estate_and_its_two_older_roles_call_the_ai_gateway_while_the_agents_follow_the_switch_of_step_2(self):
        _, _, finished = self.run_all("success")
        _, _, failed = self.run_all("failure")
        self.assertIn("No resource of the estate was changed; with the investigation on, the Watch also created its agents and conversations in its own Foundry project.", finished["cases-run"])
        self.assertIn("The tokens that the lines above count are those of the Detective and the Skeptic, which call the AI Gateway with the app's identity and no key", finished["cases-run"])
        self.assertIn("a 403 says that the app's identity does not hold AI Gateway Models User yet: the action aigateway gives it, and a new role takes up to ten minutes to apply", finished["cases-run"])
        self.assertIn("while the agents of the investigation call their models through the project's connection and the AI Gateway when the switch of step 2 (AGENTS_VIA_AI_GATEWAY in tools/environment-params.py) "
                      "is on, and straight to the model deployments of their own Foundry project when it is off, which is the way back.", finished["cases-run"])
        self.assertNotIn("until the switch of step 2 is on", finished["cases-run"])
        self.assertNotIn("not tried before", finished["cases-run"])
        self.assertNotIn("that route was tried on 2026-11-07", finished["cases-run"], "the route of the project's chat completions is gone")
        self.assertIn("It changes no resource of the estate; with the investigation on it may also have created agents and conversations in its own Foundry project before it stopped.", failed["cases-run"])
        for body in (finished["cases-run"], failed["cases-run"]):
            for old in ("It only reads Azure, so nothing was changed", "tokens that went through the gateway", "Nothing in Azure was changed", "Calls that go through the gateway", "not through the gateway"):
                self.assertNotIn(old, body, old)
        self.assertIn("the app reads no key and needs nothing of the owner's API Management instance", finished["cases"])
        self.assertIn("The Detective and the Skeptic call the AI Gateway (every model call of Meternaut goes through it: AGENTS.md rule 15 (c)), with the app's own identity and no key", finished["cases"])
        self.assertIn("the app's identity holds AI Gateway Models User on the gateway only once the action `aigateway` has given it, which takes up to ten minutes to apply", finished["cases"])
        for body in (finished["cases"], failed["cases"]):
            self.assertNotIn("contract's key", body)
            self.assertNotIn("the gateway's subscription", body)
            self.assertNotIn("call the model deployments of the agents' own Foundry project, with the app's own identity", body)


STAND_IN_PYTHON = """#!/bin/bash
if [ "$1" = "--version" ]; then echo "Python $FAKE_PYTHON"; exit 0; fi
if [ "$1" = "-c" ]; then
  if [ "$FAKE_PYTHON" = "3.13.0" ]; then exit 0; fi
  exit 1
fi
echo "python3 $*" >> "$FAKE_LOG"
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class BuildTheFunctionPackage(unittest.TestCase):
    """tools/build-function-app.sh against a stand-in for python3: what it refuses, and the exact install that it asks for."""

    def run_script(self, python_version, arguments=("case-functions", "cases")):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            python3 = bin_dir / "python3"
            python3.write_text(STAND_IN_PYTHON, encoding="utf-8", newline="\n")
            python3.chmod(python3.stat().st_mode | stat.S_IEXEC)
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            build = tmp / "build"
            env = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_PYTHON": python_version, "FAKE_LOG": log.as_posix()}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", (ROOT / "tools" / "build-function-app.sh").as_posix(), *arguments, build.as_posix()],
                                  capture_output=True, text=True, env=env, cwd=ROOT)
            copied = sorted(p.name for p in build.iterdir()) if build.exists() else []
            return done, log.read_text(encoding="utf-8").splitlines(), copied

    def test_another_python_than_3_13_stops_it_before_anything_is_built(self):
        for version in ("3.12.3", "3.14.0", "3.11.9"):
            done, calls, copied = self.run_script(version)
            self.assertEqual(done.returncode, 1, version)
            self.assertIn("build with Python 3.13", done.stderr)
            self.assertIn(f"Python {version}", done.stderr)
            self.assertEqual((calls, copied), ([], []), "no download and no copy before the refusal")

    def test_python_3_13_installs_only_wheels_of_the_lock_for_linux_and_checks_their_hashes(self):
        done, calls, copied = self.run_script("3.13.0")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(copied, ["cases", "function_app.py", "host.json", "requirements.txt"], "the app's files; the stand-in pip makes no target directory")
        (install,) = calls
        for flag in ("-m pip install", "--require-hashes", "--only-binary=:all:", "--platform manylinux2014_x86_64", "--platform manylinux_2_28_x86_64",
                     "--implementation cp", "--python-version 3.13", "--no-compile", "/.python_packages/lib/site-packages", "src/case-functions/requirements.txt"):
            self.assertIn(flag, install)
        for word in ("--index-url", "--extra-index-url", "--trusted-host", "--no-deps"):
            self.assertNotIn(word, install, word)
        self.assertNotIn("usage-functions", install, "the app is built from its own lock")

    def test_names_that_leave_the_src_folder_or_the_plain_form_are_refused_before_anything_is_built(self):
        for arguments in (("../tools", "cases"), ("case-functions", "cases/../x"), ("Case-Functions", "cases"), ("case-functions", "Cases"), ("", "cases")):
            done, calls, copied = self.run_script("3.13.0", arguments=arguments)
            self.assertNotEqual(done.returncode, 0, arguments)
            self.assertEqual((calls, copied), ([], []), arguments)


if __name__ == "__main__":
    unittest.main()
