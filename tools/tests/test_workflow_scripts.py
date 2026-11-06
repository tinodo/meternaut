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


AZ = """#!/bin/bash
case "$*" in
  *"identity list"*) printf '%s' "$FAKE_IDENTITY" ;;
  *"rest "*) printf '%s' "$FAKE_LOGGERS" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

PYTHON3 = """#!/bin/bash
if [ "$2" = "build" ]; then
  echo "build principal=${GATEWAY_PRINCIPAL_ID-unset} client=${GATEWAY_CLIENT_ID-unset} fragments=${RECORDING_FRAGMENTS-unset} preview=$([[ " $* " == *" --preview "* ]] && echo yes || echo no)" >> "$FAKE_LOG"
  printf 'gateway_subscription=sub1\\ngateway_resource_group=rg1\\nidentity_name=id-meternaut-gateway\\n'
else
  echo "check $*" >> "$FAKE_LOG"
fi
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class WorkOutTheSettings(unittest.TestCase):
    """The shell of the step that decides what the later steps ask for, run against stand-ins for the Azure CLI and the parameter builder."""

    def run_step(self, identity, loggers):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            for name, body in (("az", AZ), ("python3", PYTHON3)):
                path = bin_dir / name
                path.write_text(body, encoding="utf-8", newline="\n")
                path.chmod(path.stat().st_mode | stat.S_IEXEC)
            script = tmp / "step.sh"
            script.write_text(step_script("Work out the settings"), encoding="utf-8", newline="\n")
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            (tmp / "out.txt").write_text("", encoding="utf-8")
            env = {**os.environ,
                   "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}",
                   "FAKE_IDENTITY": identity, "FAKE_LOGGERS": loggers, "FAKE_LOG": log.as_posix(),
                   "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(), "RUNNER_TEMP": tmp.as_posix(),
                   "GATEWAY_RESOURCE_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg1/providers/Microsoft.ApiManagement/service/apim1"}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            return done, log.read_text(encoding="utf-8").splitlines(), (tmp / "out.txt").read_text(encoding="utf-8")

    def builds(self, lines):
        return [line for line in lines if line.startswith("build ")]

    def test_the_identity_on_one_line_and_both_loggers_present_turns_the_fragments_on(self):
        done, lines, out = self.run_step(f"{PRINCIPAL}\t{CLIENT}", "appinsights-logger\nusage-eventhub-logger\npii-usage-eventhub-logger\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), ["build principal=unset client=unset fragments=unset preview=yes",
                                              f"build principal={PRINCIPAL} client={CLIENT} fragments=true preview=no"])
        self.assertIn("gateway_subscription=sub1", out)

    def test_the_identity_on_two_lines_is_read_the_same_way(self):
        done, lines, _ = self.run_step(f"{PRINCIPAL}\n{CLIENT}", "appinsights-logger\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines)[1], f"build principal={PRINCIPAL} client={CLIENT} fragments=false preview=no")

    def test_one_logger_is_not_enough(self):
        for loggers in ("usage-eventhub-logger\n", "pii-usage-eventhub-logger\n", "", "usage-eventhub-logger-2\npii-usage-eventhub-logger\n"):
            done, lines, _ = self.run_step(f"{PRINCIPAL}\t{CLIENT}", loggers)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("fragments=false", self.builds(lines)[1], loggers)

    def test_without_the_identity_only_the_preview_is_built(self):
        for identity in ("", "None", PRINCIPAL):
            done, lines, _ = self.run_step(identity, "usage-eventhub-logger\npii-usage-eventhub-logger\n")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(self.builds(lines), ["build principal=unset client=unset fragments=unset preview=yes"], identity)
            self.assertIn("does not exist yet", done.stdout)

    def test_every_parameter_file_is_checked_against_its_template(self):
        done, lines, _ = self.run_step(f"{PRINCIPAL}\t{CLIENT}", "")
        checks = [line for line in lines if line.startswith("check ")]
        labels = [re.search(r"--label (\S+)", line).group(1) for line in checks]
        self.assertEqual(labels, ["environment", "logger", "eventhub-loggers", "kit", "recording", "foundry", "contract", "cases", "planted"])


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

FOUNDRY_SETTINGS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"identity list"*"--subscription"*) printf '%s' "$FAKE_IDENTITY" ;;
  *"/loggers?"*) printf '%s' "$FAKE_LOGGERS" ;;
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
  echo "build preview=$([[ " $* " == *" --preview "* ]] && echo yes || echo no) foundry_project=${ENV_FOUNDRY_PROJECT_EXISTS-unset} cases_system=[${CASES_SYSTEM_PRINCIPAL_ID-unset}]" >> "$FAKE_LOG"
  printf 'gateway_subscription=sub1\\ngateway_resource_group=rg1\\nidentity_name=id-meternaut-gateway\\ncases_function_app_name=func-meternaut-cases-abc123\\nfoundry_account_name=aif-meternaut-agents-abc123\\nfoundry_project_name=meternaut\\n'
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
    PREVIEW = "build preview=yes foundry_project=unset cases_system=[unset]"
    HOSTILE = "ERROR: (AuthorizationFailed) The client '40404040-4040-4040-4040-404040404040' with object id 'a404b404-0000-0000-0000-000000000404' does not have authorization"

    def run_step(self, action="what-if", project="found", identity=f"{PRINCIPAL}\t{CLIENT}", system=SYSTEM_PRINCIPAL):
        return run_step_script("Work out the settings", {"az": FOUNDRY_SETTINGS_AZ, "python3": FOUNDRY_SETTINGS_PYTHON3},
                               {"ACTION": action, "FAKE_IDENTITY": identity, "FAKE_PROJECT": project, "FAKE_LOGGERS": "appinsights-logger\n",
                                "FAKE_SYSTEM": system, "FAKE_SYSTEM_ERROR": self.HOSTILE,
                                "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project",
                                "GATEWAY_RESOURCE_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg1/providers/Microsoft.ApiManagement/service/apim1"})

    def builds(self, lines):
        return [line for line in lines if line.startswith("build ")]

    def final(self, project="false", system=""):
        return f"build preview=no foundry_project={project} cases_system=[{system}]"

    def user_assigned_lookups(self, lines):
        return [line for line in lines if line.startswith("az identity list") and "--subscription" not in line]

    def test_what_if_looks_for_the_identity_of_the_app_and_for_the_project_with_the_version_that_the_model_account_uses(self):
        done, lines, _ = self.run_step("what-if")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), [self.PREVIEW, self.final("true", SYSTEM_PRINCIPAL)])
        self.assertIn(self.PROJECT_CALL, lines, "existence does not need the newest version")
        self.assertIn(self.SITE_CALL, lines, "the system-assigned identity is read from the app, and the version is the one that the other reads of the app use")
        self.assertEqual(self.user_assigned_lookups(lines), [], "the user-assigned identity that the app used before is not looked for")
        self.assertIn("The cases app's system-assigned identity exists; its principal id goes into the Foundry file.", done.stdout)
        self.assertIn("The Foundry project is in Azure: true.", done.stdout)

    def test_foundry_needs_the_identity_and_never_looks_for_the_project(self):
        done, lines, _ = self.run_step("foundry", project="ERROR: (AuthorizationFailed) a read that would stop the run if it were made")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), [self.PREVIEW, self.final("false", SYSTEM_PRINCIPAL)])
        self.assertIn(self.SITE_CALL, lines)
        self.assertEqual([line for line in lines if "/projects/" in line], [])
        self.assertEqual(self.user_assigned_lookups(lines), [])
        self.assertIn("The action foundry does not use the Foundry project, so it is not looked for.", done.stdout)

    def test_cases_needs_the_project_and_never_looks_for_the_identity(self):
        done, lines, _ = self.run_step("cases", system="FAIL")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), [self.PREVIEW, self.final("true", "")])
        self.assertIn(self.PROJECT_CALL, lines)
        self.assertEqual([line for line in lines if "Microsoft.Web/sites" in line], [], "the cases app is not given a role on the project by this action")
        self.assertEqual(self.user_assigned_lookups(lines), [])
        self.assertIn("The Foundry project is in Azure: true.", done.stdout)

    def test_every_other_action_looks_for_none_of_them_so_a_refused_read_cannot_stop_it(self):
        for action in ("loop-check", "recording"):
            with self.subTest(action=action):
                done, lines, _ = self.run_step(action, project=self.HOSTILE, system="FAIL")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(self.builds(lines), [self.PREVIEW, self.final()])
                self.assertEqual([line for line in lines if "/projects/" in line or "Microsoft.Web/sites" in line], [])
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
        self.assertEqual(self.builds(lines)[1], self.final("false", SYSTEM_PRINCIPAL))
        self.assertIn("The Foundry project is in Azure: false.", done.stdout)
        self.assertEqual([line for line in lines if line.startswith("check ")][-1].split("--label ")[1], "planted", "the files were checked as always")

    def test_an_app_without_a_system_assigned_identity_gives_an_empty_value_and_the_run_goes_on(self):
        # "none yet": the app is not there (not found), or it is there and has no such identity (the CLI prints None for a null, and an empty string for nothing)
        for action in ("foundry", "what-if"):
            for answer in ("ABSENT", "None", "", "not-a-guid"):
                with self.subTest(action=action, answer=answer):
                    done, lines, _ = self.run_step(action, system=answer)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(self.builds(lines)[1], self.final("true" if action == "what-if" else "false", ""))
                    self.assertIn("The cases app has no system-assigned identity yet (the action cases makes the app with it); the Foundry file holds a placeholder.", done.stdout)
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

    def test_without_the_gateway_identity_no_lookup_is_made_and_only_the_preview_is_built(self):
        for action, identity in (("what-if", ""), ("cases", "None")):
            with self.subTest(action=action):
                done, lines, _ = self.run_step(action, identity=identity)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(self.builds(lines), [self.PREVIEW])
                self.assertEqual([line for line in lines if line.startswith("az ")],
                                 ["az identity list --subscription sub1 --resource-group rg1 --query [?name=='id-meternaut-gateway'] | [0].[principalId, clientId] --output tsv"])

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

    TITLE = "The usage recording and the cases app's identity are there, which the Foundry resource builds on"
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

    def test_a_component_that_is_not_there_stops_the_step_and_says_to_run_the_recording_first(self):
        for answer in ("", "None"):
            done, lines, _ = self.run_step(component=answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("Run recording first", done.stdout)
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
            env = {**os.environ, "JOB_STATUS": status, "ACCOUNT_NAME": "aif-meternaut-abc", "CONTRACT_NAME": "meternaut-pilot", "FOUNDRY_ACCOUNT": "aif-meternaut-agents-abc", "FOUNDRY_PROJECT": "meternaut",
                   "FOUNDRY_ENDPOINT": "https://aif-meternaut-agents-abc.services.ai.azure.com/api/projects/meternaut", "ENV_RESOURCE_GROUP": "rg-of-the-project",
                   "GITHUB_STEP_SUMMARY": summary.as_posix()}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            text = summary.read_text(encoding="utf-8")
        return done, actions, dict(re.findall(r"(?ms)^### Hub: ([a-z-]+), \w+\n(.*?)(?=^### Hub: |\Z)", text))

    def test_every_action_has_words_for_a_run_that_finished_and_for_one_that_did_not_and_the_shell_says_nothing_of_its_own(self):
        for status in ("success", "failure"):
            with self.subTest(status=status):
                done, actions, sections = self.run_all(status)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stderr, "", "a backtick that is not escaped inside the quotes runs a command in bash, which says 'command not found' and leaves the name out")
                self.assertEqual(sorted(sections), sorted(actions))
                for action, body in sections.items():
                    self.assertGreater(len(body.strip()), 60, (status, action))

    def test_the_name_of_the_retired_identity_is_printed_in_the_summary_of_the_cases(self):
        done, _, sections = self.run_all("success")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("The retired identity of the first loop, `id-meternaut-runner`, is removed when it is still there and nothing holds it.", sections["cases"])

    def test_the_watch_changes_no_resource_of_the_estate_and_with_the_investigation_on_it_uses_its_own_foundry_project_and_calls_the_models_of_that_resource_directly(self):
        _, _, finished = self.run_all("success")
        _, _, failed = self.run_all("failure")
        self.assertIn("No resource of the estate was changed; with the investigation on, the Watch also created its agents and conversations in its own Foundry project.", finished["cases-run"])
        self.assertIn("Calls that go through the gateway are counted there; with the investigation on, the agents in the Foundry project call the models of that resource directly, not through the gateway.",
                      finished["cases-run"])
        self.assertIn("It changes no resource of the estate; with the investigation on it may also have created agents and conversations in its own Foundry project before it stopped.", failed["cases-run"])
        for body in (finished["cases-run"], failed["cases-run"]):
            for old in ("It only reads Azure, so nothing was changed", "tokens that went through the gateway", "Nothing in Azure was changed"):
                self.assertNotIn(old, body, old)


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

    def run_script(self, python_version, arguments=("usage-functions", "usage")):
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
        self.assertEqual(copied, ["function_app.py", "host.json", "requirements.txt", "usage"], "the app's files; the stand-in pip makes no target directory")
        (install,) = calls
        for flag in ("-m pip install", "--require-hashes", "--only-binary=:all:", "--platform manylinux2014_x86_64", "--platform manylinux_2_28_x86_64",
                     "--implementation cp", "--python-version 3.13", "--no-compile", "/.python_packages/lib/site-packages", "src/usage-functions/requirements.txt"):
            self.assertIn(flag, install)
        for word in ("--index-url", "--extra-index-url", "--trusted-host", "--no-deps"):
            self.assertNotIn(word, install, word)

    def test_the_cases_app_is_built_from_its_own_lock(self):
        done, calls, copied = self.run_script("3.13.0", arguments=("case-functions", "cases"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(copied, ["cases", "function_app.py", "host.json", "requirements.txt"])
        (install,) = calls
        self.assertIn("src/case-functions/requirements.txt", install)
        self.assertNotIn("usage-functions", install)

    def test_names_that_leave_the_src_folder_or_the_plain_form_are_refused_before_anything_is_built(self):
        for arguments in (("../tools", "usage"), ("usage-functions", "usage/../x"), ("Usage-Functions", "usage"), ("usage-functions", "Usage"), ("", "usage")):
            done, calls, copied = self.run_script("3.13.0", arguments=arguments)
            self.assertNotEqual(done.returncode, 0, arguments)
            self.assertEqual((calls, copied), ([], []), arguments)


if __name__ == "__main__":
    unittest.main()
