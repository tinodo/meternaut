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

FOUNDRY_SETTINGS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"identity list"*"--subscription"*) printf '%s' "$FAKE_IDENTITY" ;;
  *"identity list"*)
    if [ "$FAKE_CASES" = "FAIL" ]; then echo "ERROR: (AuthorizationFailed) the client does not have authorization" >&2; exit 1; fi
    printf '%s' "$FAKE_CASES" ;;
  *"/loggers?"*) printf '%s' "$FAKE_LOGGERS" ;;
  *"/projects/"*)
    if [ "$FAKE_PROJECT" = "found" ]; then echo meternaut; else echo "$FAKE_PROJECT" >&2; exit 1; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

FOUNDRY_SETTINGS_PYTHON3 = """#!/bin/bash
if [ "$2" = "build" ]; then
  echo "build preview=$([[ " $* " == *" --preview "* ]] && echo yes || echo no) cases_principal=[${CASES_PRINCIPAL_ID-unset}] foundry_project=${ENV_FOUNDRY_PROJECT_EXISTS-unset}" >> "$FAKE_LOG"
  printf 'gateway_subscription=sub1\\ngateway_resource_group=rg1\\nidentity_name=id-meternaut-gateway\\ncases_identity_name=id-meternaut-cases\\nfoundry_account_name=aif-meternaut-agents-abc123\\nfoundry_project_name=meternaut\\n'
else
  echo "check $*" >> "$FAKE_LOG"
fi
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class WorkOutTheFoundrySettings(unittest.TestCase):
    """The lookups that the step 'Work out the settings' makes for the Foundry resource: the identity that gets a role on the project, and whether the project is there."""

    def run_step(self, project="found", cases=CASES_PRINCIPAL, identity=f"{PRINCIPAL}\t{CLIENT}"):
        return run_step_script("Work out the settings", {"az": FOUNDRY_SETTINGS_AZ, "python3": FOUNDRY_SETTINGS_PYTHON3},
                               {"FAKE_IDENTITY": identity, "FAKE_CASES": cases, "FAKE_PROJECT": project, "FAKE_LOGGERS": "appinsights-logger\n",
                                "ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project",
                                "GATEWAY_RESOURCE_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg1/providers/Microsoft.ApiManagement/service/apim1"})

    def builds(self, lines):
        return [line for line in lines if line.startswith("build ")]

    def test_the_identity_and_the_project_are_there_so_the_file_gets_the_identity_and_the_cases_app_gets_the_address(self):
        done, lines, _ = self.run_step()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), ["build preview=yes cases_principal=[unset] foundry_project=unset",
                                              f"build preview=no cases_principal=[{CASES_PRINCIPAL}] foundry_project=true"])
        self.assertIn("az rest --method get --url https://management.azure.com/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project/providers/Microsoft.CognitiveServices"
                      "/accounts/aif-meternaut-agents-abc123/projects/meternaut?api-version=2026-09-01 --query name --output tsv", lines)
        self.assertIn("az identity list --resource-group rg-of-the-project --query [?name=='id-meternaut-cases'].principalId | [0] --output tsv", lines)
        self.assertIn("The cases app's identity exists; its principal id goes into the Foundry file.", done.stdout)
        self.assertIn("The Foundry project is in Azure: true.", done.stdout)

    def test_an_object_id_in_capitals_is_passed_on_as_it_is(self):
        done, lines, _ = self.run_step(cases=CASES_PRINCIPAL.upper())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines)[1], f"build preview=no cases_principal=[{CASES_PRINCIPAL.upper()}] foundry_project=true")

    def test_a_project_that_is_not_there_gives_false_however_the_service_says_so_and_the_final_build_still_follows(self):
        for answer in ("ERROR: (ResourceNotFound) The Resource 'Microsoft.CognitiveServices/accounts/x/projects/meternaut' was not found.",
                       'ERROR: Not Found({"error":{"code":"NotFound"}})', "ERROR: the request failed with status 404"):
            done, lines, _ = self.run_step(project=answer)
            self.assertEqual(done.returncode, 0, (answer, done.stderr))
            self.assertEqual(self.builds(lines)[1], f"build preview=no cases_principal=[{CASES_PRINCIPAL}] foundry_project=false", answer)
            self.assertIn("The Foundry project is in Azure: false.", done.stdout)

    def test_an_answer_that_is_not_not_found_stops_the_run_before_the_final_build_even_when_it_holds_the_digits_404_inside_an_object_id(self):
        for answer in ("ERROR: (AuthorizationFailed) The client '40404040-4040-4040-4040-404040404040' with object id 'a404b404-0000-0000-0000-000000000404' does not have authorization",
                       "ERROR: (InternalServerError) try again later", "ERROR: the request timed out"):
            done, lines, _ = self.run_step(project=answer)
            self.assertNotEqual(done.returncode, 0, answer)
            self.assertIn("meternaut could not be read", done.stderr + done.stdout, answer)
            self.assertEqual(self.builds(lines), ["build preview=yes cases_principal=[unset] foundry_project=unset"], "a wrong guess would switch the investigation off or on")
            self.assertEqual([line for line in lines if line.startswith("check ")], [], "the run stopped before the files were checked")

    def test_a_cases_identity_that_is_not_there_gives_an_empty_object_id_and_the_run_goes_on(self):
        for answer in ("", "None", "not-a-guid"):
            done, lines, _ = self.run_step(cases=answer)
            self.assertEqual(done.returncode, 0, (answer, done.stderr))
            self.assertEqual(self.builds(lines)[1], "build preview=no cases_principal=[] foundry_project=true", answer)
            self.assertIn("The cases app's identity does not exist yet (the action cases makes it); the Foundry file holds a placeholder.", done.stdout)

    def test_a_lookup_of_the_cases_identity_that_fails_stops_the_run_instead_of_counting_as_not_there(self):
        done, lines, _ = self.run_step(cases="FAIL")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("AuthorizationFailed", done.stderr)
        self.assertEqual(self.builds(lines), ["build preview=yes cases_principal=[unset] foundry_project=unset"], "no file was made with a placeholder for an identity that may be there")

    def test_without_the_gateway_identity_neither_lookup_is_made_and_only_the_preview_is_built(self):
        for identity in ("", "None"):
            done, lines, _ = self.run_step(identity=identity)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(self.builds(lines), ["build preview=yes cases_principal=[unset] foundry_project=unset"], identity)
            self.assertEqual([line for line in lines if line.startswith("az ")],
                             ["az identity list --subscription sub1 --resource-group rg1 --query [?name=='id-meternaut-gateway'] | [0].[principalId, clientId] --output tsv"], identity)

    def test_the_lookups_only_read(self):
        done, lines, _ = self.run_step()
        self.assertEqual(done.returncode, 0, done.stderr)
        for call in (line for line in lines if line.startswith("az ")):
            for word in (" put ", " post ", " patch ", " delete ", " create ", " role ", "listKeys", "listSecrets", "--yes"):
                self.assertNotIn(word, call + " ", call)


FOUNDRY_PRECHECK_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) printf '%s' "$FAKE_COMPONENT" ;;
  *"identity list"*) printf '%s' "$FAKE_CASES" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheFoundryResourceBuildsOnWhatIsThere(unittest.TestCase):
    """The check before the deploy of the Foundry resource: the component for the traces, the cases identity, and a file that carries the identity's object id."""

    TITLE = "The usage recording and the cases identity are there, which the Foundry resource builds on"

    def run_step(self, component="appi-meternaut", cases=CASES_PRINCIPAL, parameter_file=None):
        parameter_file = f'{{"casesPrincipalId": {{"value": "{CASES_PRINCIPAL}"}}}}' if parameter_file is None else parameter_file
        return run_step_script(self.TITLE, {"az": FOUNDRY_PRECHECK_AZ},
                               {"FAKE_COMPONENT": component, "FAKE_CASES": cases, "ENV_RESOURCE_GROUP": "rg-of-the-project", "INSIGHTS_NAME": "appi-meternaut",
                                "CASES_IDENTITY": "id-meternaut-cases"},
                               files={"foundry.parameters.json": parameter_file})

    def test_everything_is_there_and_the_file_carries_the_object_id_so_the_step_passes(self):
        done, lines, _ = self.run_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(lines, ["az resource list --resource-group rg-of-the-project --resource-type Microsoft.Insights/components --query [?name=='appi-meternaut'].name | [0] --output tsv",
                                 "az identity list --resource-group rg-of-the-project --query [?name=='id-meternaut-cases'].principalId | [0] --output tsv"])
        self.assertIn("the parameter file carries the identity's object id", done.stdout)

    def test_the_object_id_is_found_in_the_file_whatever_its_case(self):
        done, _, _ = self.run_step(cases=CASES_PRINCIPAL.upper())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_component_that_is_not_there_stops_the_step_and_says_to_run_the_recording_first(self):
        for answer in ("", "None"):
            done, lines, _ = self.run_step(component=answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("Run recording first", done.stdout)
            self.assertEqual(len(lines), 1, "the identity is not asked for when the first thing is missing")

    def test_an_identity_that_is_not_there_stops_the_step_and_says_to_run_cases_first(self):
        for answer in ("", "None", "ERROR: no such group"):
            done, _, _ = self.run_step(cases=answer)
            self.assertEqual(done.returncode, 1, answer)
            self.assertIn("Run cases first", done.stdout)

    def test_a_file_without_the_object_id_stops_the_step_and_nothing_is_deployed(self):
        for parameter_file in ('{"casesPrincipalId": {"value": "00000000-0000-0000-0000-000000000000"}}', "{}", ""):
            done, _, _ = self.run_step(parameter_file=parameter_file)
            self.assertEqual(done.returncode, 1, parameter_file)
            self.assertIn("does not carry the object id of id-meternaut-cases", done.stdout)
            self.assertIn("Nothing was deployed.", done.stdout)

    def test_the_check_only_reads(self):
        done, lines, _ = self.run_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for call in lines:
            self.assertRegex(call, r"^az (resource|identity) list ")
            for word in (" create ", " delete ", " update ", " role ", " rest "):
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
