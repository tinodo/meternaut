"""The Hub's steps of the AI security (docs/proposals/10-ai-security-and-governance.md): the actions governance, gateway-telemetry and drift-check, the preflights that stop early with the right, who gives it and
where, the release that the action cases records, and the second workflow drift.yml that can only read. The scripts of the steps are run with bash and stand-ins for the commands that they call; no test calls Azure."""
import importlib.util
import json
import os
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # CI has no PyYAML either: checks.yml parses the workflows with Ruby
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workflow_scripts_of_the_aisec_tests", ROOT / "tools" / "tests" / "test_workflow_scripts.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)

HUB = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
DRIFT = (ROOT / ".github" / "workflows" / "drift.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
CHECKS = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
SKIP_BASH = unittest.skipIf(ws.BASH is None, "no bash on this machine")

COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
DIGEST = "0123456789abcdef" * 4
ZIP = "fedcba9876543210" * 4
DEPLOYER = "5a1c0de0-0000-4000-8000-0000000000de"
GATEWAY_PRINCIPAL = "12345678-4444-5555-6666-123456789012"
RESOURCE_POLICY_CONTRIBUTOR = "36243c78-bf99-498c-9df9-86d9f8d28608"
OWNER_ROLE = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
MONITORING_METRICS_PUBLISHER = "3913510d-42f4-4e42-8a64-420c390055eb"
SETTINGS = {"ENV_SUBSCRIPTION_ID": "sub-of-the-project", "ENV_RESOURCE_GROUP": "rg-of-the-project", "ACTION": "governance"}


def steps_of(text: str) -> list[str]:
    return re.split(r"(?m)^      - ", text.split("    steps:\n", 1)[1])[1:]


def step(text: str, name: str) -> str:
    (block,) = [b for b in steps_of(text) if b.startswith(f"name: {name}\n")]
    return block


class TheActionsAreInTheHub(unittest.TestCase):
    def test_each_new_action_has_its_own_steps_and_every_step_of_them_is_named_by_its_action(self):
        for action in ("governance", "gateway-telemetry", "drift-check"):
            blocks = [b for b in steps_of(HUB) if f"inputs.action == '{action}'" in b]
            self.assertGreaterEqual(len(blocks), 1, action)
        self.assertEqual(len([b for b in steps_of(HUB) if "inputs.action == 'governance'" in b]), 5, "the settings step, the preflight, the deploy, the sign-in and the read-back")
        self.assertEqual(len([b for b in steps_of(HUB) if "inputs.action == 'drift-check'" in b]), 1)

    def test_the_governance_action_reads_before_it_deploys_and_deploys_the_two_files_of_the_builder(self):
        names = [re.match(r"name: (.+)\n", b).group(1) for b in steps_of(HUB)]
        order = ["Work out the settings of the AI security", "The base, the Foundry resource and the rights that the AI security needs are there", "Deploy the policy, the alert rules and the workbook of the AI security",
                 "Sign in to Azure again for the read-back of the AI security, because the first sign-in's credential lasts five minutes", "Read the AI security back from Azure"]
        self.assertEqual([names.index(n) for n in order], sorted(names.index(n) for n in order))
        deploy = step(HUB, order[2])
        for word in ("--template environment/governance/main.bicep", '--parameters "$RUNNER_TEMP/aisec/governance.parameters.json"', "--output actionGroupName", "ag-meternaut-ai-security"):
            self.assertIn(word, deploy, word)
        self.assertIn("if: inputs.action == 'governance'", deploy)
        telemetry = step(HUB, "Deploy the telemetry exporter of the AI Gateway")
        for word in ("--template environment/aigateway/telemetry.bicep", '--parameters "$RUNNER_TEMP/aisec/gateway-telemetry.parameters.json"', "--output exporterName", '"appinsights"'):
            self.assertIn(word, telemetry, word)

    def test_the_settings_step_of_the_ai_security_serves_the_preview_and_the_two_actions_and_leaves_the_other_settings_step_alone(self):
        block = step(HUB, "Work out the settings of the AI security")
        self.assertIn("if: inputs.action == 'what-if' || inputs.action == 'governance' || inputs.action == 'gateway-telemetry'", block)
        self.assertIn("--governance environment/aigateway/contracts.json", block)
        self.assertIn('--out-dir "$RUNNER_TEMP/aisec"', block, "a folder of its own: the files of the other actions are what they were")
        for label in ("governance", "gateway-telemetry"):
            self.assertIn(f"--label {label}", block)
        settings = step(HUB, "Work out the settings")
        self.assertNotIn("--governance", settings)

    def test_the_preview_shows_the_two_templates_when_what_they_read_is_there_and_says_what_is_missing_when_it_is_not(self):
        block = step(HUB, "What the AI security's templates would change")
        self.assertIn("if: inputs.action == 'what-if'", block)
        for word in ("environment/governance/main.bicep", "environment/aigateway/telemetry.bicep", "cannot be previewed yet", "OTLPLogsEndpoint", "the action base turns the ingestion on"):
            self.assertIn(word, block, word)

    def test_the_templates_step_compiles_both_templates_for_the_check_of_their_files_and_repeats_no_test_nor_lint(self):
        block = step(HUB, "The templates compile, for the check of their parameter files")
        for word in ("environment/aigateway/telemetry.bicep", "environment/governance/main.bicep", '--outfile "$RUNNER_TEMP/governance.json"', '--outfile "$RUNNER_TEMP/gateway-telemetry.json"'):
            self.assertIn(word, block, word)
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        for word in ("unittest", "workflow-lint", "bicep lint", "--selftest", "--stdout"):
            self.assertNotIn(word, script, f"{word}: CI ran it for exactly this commit, and the first steps of the job read that it did")

    def test_no_step_of_the_ai_security_changes_anything_but_what_it_says(self):
        for name in ("Work out the settings of the AI security", "Read the AI security back from Azure", "Read the telemetry exporter back from Azure", "Check for drift from the control plane, with reads only",
                     "The base, the Foundry resource and the rights that the AI security needs are there",
                     "The AI Gateway is there, the provider is registered, the component reports its endpoints and the gateway's identity may send to them"):
            block = step(HUB, name)
            script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
            self.assertNotRegex(script, r"--method (put|patch|post|delete)", name)
            self.assertNotRegex(script, r"\baz (role assignment (create|delete)|deployment|group deployment|resource (delete|create|tag)|policy)", name)
            self.assertNotIn("listKeys", script)

    def test_the_only_write_outside_a_deploy_is_the_merge_of_the_two_release_tags_and_it_is_after_the_publish_and_the_health_check(self):
        record = step(HUB, "Record the release that runs on the cases app, in its tags and in the summary")
        names = [re.match(r"name: (.+)\n", b).group(1) for b in steps_of(HUB)]
        publish, health = "Publish the cases to the function app from inside the network, in the Operator", "Wait until the cases app answers"
        title = "Record the release that runs on the cases app, in its tags and in the summary"
        self.assertLess(names.index(publish), names.index(health))
        self.assertLess(names.index(health), names.index(title), "the tags are written once the code is published and the app answers")
        script = "\n".join(line for line in record.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertEqual(re.findall(r"--method (\w+)", script), ["patch", "get"])
        self.assertIn("providers/Microsoft.Resources/tags/default?api-version=2021-04-01", script)
        self.assertIn('"operation":"Merge"', script, "a merge touches nothing else of the app")
        self.assertIn("if: inputs.action == 'cases'", record)


class TheDriftWorkflow(unittest.TestCase):
    def test_it_starts_by_hand_for_now_is_guarded_and_holds_no_write_and_no_deploy_identity(self):
        code = "\n".join(line for line in DRIFT.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("schedule:", code.replace("github.event_name == 'schedule'", ""), "a timer is added after the read-only identity exists (environment/BOOTSTRAP.md, step G4), in a change of its own")
        self.assertIn("on:\n  workflow_dispatch:\n", DRIFT)
        self.assertIn("    if: github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.actor == 'tinodo')\n", DRIFT)
        self.assertIn("permissions:\n  contents: read\n  id-token: write\n", DRIFT)
        self.assertIn("client-id: ${{ vars.DRIFT_CLIENT_ID }}", code)
        for word in ("--method put", "--method patch", "--method delete", "az deployment", "az role", "az group"):
            self.assertNotIn(word, code, word)
        self.assertEqual(code.count("python3 tools/drift-check.py"), 2, "the selftest and the check")
        for flag in ("--graph", "--read-subscription"):
            self.assertNotIn(flag, code, f"{flag}: the check with the role Reader on the group reads Azure Resource Manager at the group, and says UNKNOWN for the rest")

    @unittest.skipUnless(yaml, "no YAML parser on this machine: CI parses the workflows with Ruby (checks.yml)")
    def test_a_real_parser_agrees(self):
        document = yaml.safe_load(DRIFT)
        self.assertEqual(len(document["jobs"]), 1)
        self.assertEqual(list(document.get("on", document.get(True))), ["workflow_dispatch"])
        self.assertEqual(document["permissions"], {"contents": "read", "id-token": "write"})
        self.assertIn("concurrency", document)

    @SKIP_BASH
    def test_the_first_step_stops_plainly_while_the_identity_does_not_exist_and_says_who_makes_it(self):
        title = "Stop plainly when the read-only identity has not been made yet"
        script = re.search(r"(?ms)^      - name: " + re.escape(title) + r"\n(.*?)(?=^      - |\Z)", DRIFT).group(1)
        body = textwrap.dedent(re.search(r"(?ms)^        run: \|\n(.*)", script).group(1))
        for value, ok in (("", False), ("not-a-guid", False), ("12345678-aaaa-bbbb-cccc-123456789012", True)):
            with self.subTest(value=value):
                done = subprocess.run([ws.BASH, "-e", "-o", "pipefail", "-c", body], capture_output=True, text=True, env={**os.environ, "DRIFT_CLIENT_ID": value})
                self.assertEqual(done.returncode == 0, ok, done.stdout + done.stderr)
                if not ok and not value:
                    for words in ("DRIFT_CLIENT_ID is not set", "A person makes it once", "step G4", "Reader on the project's resource group", "never signs in with the deploy identity", "Nothing was read"):
                        self.assertIn(words, done.stdout + done.stderr)

    def test_the_tool_is_run_with_what_the_owner_accepted_and_this_commit_and_the_summary(self):
        run = DRIFT.split("name: Check for drift from the control plane, with reads only")[1]
        for word in ("--accepted-exemptions", "--accepted-deny", '--commit "$GITHUB_SHA"', "--app-dir src/case-functions", '--summary "$GITHUB_STEP_SUMMARY"', '"${flags[@]}"', "--access-list environment/aigateway/contracts.json"):
            self.assertIn(word, run, word)

    def test_the_checks_of_ci_guard_it_with_a_real_parser_and_build_the_two_templates_and_their_files(self):
        self.assertIn("A real YAML parser agrees that the read-only drift workflow is guarded and never uses the deploy identity", CHECKS)
        self.assertIn('guard = "github.ref == \'refs/heads/main\' && (github.event_name == \'schedule\' || github.actor == \'tinodo\')"', CHECKS)
        for word in ("environment/aigateway/telemetry.bicep", "environment/governance/main.bicep", "--governance environment/aigateway/contracts.json", "--label governance", "--label gateway-telemetry",
                     "OPERATOR_PRINCIPAL_ID:", "ENV_FOUNDRY_DIAGNOSTICS_EXIST:", "GUARDRAIL_INITIATIVE_AVAILABLE:", "python tools/drift-check.py --selftest"):
            self.assertIn(word, CHECKS, word)


@SKIP_BASH
class TheReleaseThatTheActionCasesRecords(unittest.TestCase):
    PYTHON = """#!/bin/bash
echo "python3 $*" >> "$FAKE_LOG"
if [ "$1" = "tools/source-digest.py" ]; then printf '%s\\n' "$FAKE_DIGEST"; fi
"""

    def release(self, **env):
        return ws.run_step_script("Work out which release the cases app is given, the commit and the digest of its own files", {"python3": self.PYTHON},
                                  {"HUB_SOURCE_SHA": COMMIT, "FAKE_DIGEST": DIGEST, **env})

    def test_the_commit_of_the_run_and_the_digest_of_the_apps_files_become_two_outputs(self):
        done, lines, out = self.release()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out.splitlines(), [f"build_commit={COMMIT}", f"package_sha256={DIGEST}"])
        self.assertEqual(lines, ["python3 tools/source-digest.py src/case-functions"])

    def test_a_commit_or_a_digest_that_is_not_one_stops_the_run_before_anything_is_changed(self):
        for env in ({"HUB_SOURCE_SHA": "main"}, {"HUB_SOURCE_SHA": COMMIT[:39]}, {"FAKE_DIGEST": "abc"}, {"FAKE_DIGEST": ""}):
            with self.subTest(env=env):
                done, _, out = self.release(**env)
                self.assertNotEqual(done.returncode, 0)
                self.assertEqual(out, "")
                self.assertIn("Nothing was changed.", done.stdout + done.stderr)

    def test_the_settings_step_gets_them_and_the_builder_reads_them_by_these_names(self):
        block = step(HUB, "Work out the settings")
        self.assertIn("BUILD_COMMIT: ${{ steps.release.outputs.build_commit }}", block)
        self.assertIn("PACKAGE_SHA256: ${{ steps.release.outputs.package_sha256 }}", block)
        self.assertIn("if: inputs.action == 'cases' || inputs.action == 'what-if'", step(HUB, "Work out which release the cases app is given, the commit and the digest of its own files"),
                      "the preview works the release out too: a template that is given no value writes no setting, and a preview without one would say that the app loses them")

    AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"--method patch"*) printf '%s' "$*" | sed 's/.*--body //; s/ --only-show-errors.*//' >> "$FAKE_DIR/body.txt" ;;
  *"--method get"*) printf '%s %s' "$FAKE_COMMIT_TAG" "$FAKE_DIGEST_TAG" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

    def record(self, **env):
        base = {"BUILD_COMMIT": COMMIT, "PACKAGE_SHA256": DIGEST, "ZIP_SHA256": ZIP, "SITE_ID": "/subscriptions/s/resourceGroups/g/providers/Microsoft.Web/sites/func-x",
                "FAKE_COMMIT_TAG": COMMIT, "FAKE_DIGEST_TAG": DIGEST}
        return ws.run_step_script("Record the release that runs on the cases app, in its tags and in the summary", {"az": self.AZ}, {**base, **env})

    def test_the_two_tags_are_merged_in_read_back_and_written_in_the_summary_with_the_digest_of_the_archive(self):
        done, lines, _ = self.record()
        self.assertEqual(done.returncode, 0, done.stderr)
        patch = next(line for line in lines if "--method patch" in line)
        self.assertIn("https://management.azure.com/subscriptions/s/resourceGroups/g/providers/Microsoft.Web/sites/func-x/providers/Microsoft.Resources/tags/default?api-version=2021-04-01", patch)
        body = json.loads(re.search(r"--body (\{.*\})", patch).group(1))
        self.assertEqual(body, {"operation": "Merge", "properties": {"tags": {"meternaut-build-commit": COMMIT, "meternaut-package-sha256": DIGEST}}})
        self.assertIn(f"The release is recorded: commit {COMMIT}", done.stdout)

    def test_a_tag_that_reads_back_differently_fails_the_run_and_says_that_the_record_cannot_be_trusted(self):
        for env in ({"FAKE_COMMIT_TAG": "b" * 40}, {"FAKE_DIGEST_TAG": "c" * 64}, {"FAKE_COMMIT_TAG": "null", "FAKE_DIGEST_TAG": "null"}):
            with self.subTest(env=env):
                done, _, _ = self.record(**env)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("are not the release of this run", done.stdout + done.stderr)

    def test_a_release_that_is_not_known_is_not_written(self):
        for env in ({"BUILD_COMMIT": ""}, {"PACKAGE_SHA256": "xyz"}, {"ZIP_SHA256": ""}):
            with self.subTest(env=env):
                done, lines, _ = self.record(**env)
                self.assertNotEqual(done.returncode, 0)
                self.assertEqual([line for line in lines if "--method" in line], [], "nothing is read and nothing is written")
                self.assertIn("The code was published; nothing was recorded.", done.stdout + done.stderr)

    def test_the_pack_step_records_the_sha256_of_the_archive_as_an_output(self):
        block = step(HUB, "Pack the cases app's sources for the Operator")
        self.assertIn("id: pack", block)
        self.assertIn('zip_sha256=$(sha256sum "$RUNNER_TEMP/cases-source.zip" | cut -d \' \' -f 1)', block)
        self.assertIn('echo "zip_sha256=$zip_sha256" >> "$GITHUB_OUTPUT"', block)


@SKIP_BASH
class TheBasePreflight(unittest.TestCase):
    TITLE = "The resource provider Microsoft.Monitor is registered, which the OpenTelemetry ingestion of the component needs"
    AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"provider show --namespace Microsoft.Monitor"*) if [ "$FAKE_STATE" = "FAIL" ]; then echo "ERROR: something" >&2; exit 1; fi; printf '%s' "$FAKE_STATE" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

    def run_it(self, state):
        return ws.run_step_script(self.TITLE, {"az": self.AZ}, {"FAKE_STATE": state, **SETTINGS})

    def test_it_runs_only_for_the_base_while_the_switch_is_on(self):
        self.assertIn("if: inputs.action == 'base' && steps.params.outputs.gateway_telemetry == 'true'", step(HUB, self.TITLE))
        names = [re.match(r"name: (.+)\n", b).group(1) for b in steps_of(HUB)]
        self.assertLess(names.index(self.TITLE), names.index("Deploy the base"), "before anything is changed")

    def test_a_registered_provider_goes_on(self):
        done, _, _ = self.run_it("Registered")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_any_other_state_stops_early_and_names_the_right_who_gives_it_and_where(self):
        for state in ("NotRegistered", "Registering", "Unregistered", ""):
            with self.subTest(state=state):
                done, _, _ = self.run_it(state)
                said = done.stdout + done.stderr
                self.assertEqual(done.returncode, 1)
                for words in ("Microsoft.Monitor", "A person who may register a resource provider in the subscription", "environment/BOOTSTRAP.md", "step G2", "az provider register --namespace Microsoft.Monitor",
                              "The deploy identity holds no right on the subscription", "Nothing was changed.", "GATEWAY_TELEMETRY back to False"):
                    self.assertIn(words, said, words)

    def test_a_read_that_fails_stops_the_run_too(self):
        done, _, _ = self.run_it("FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertIn("could not be read", done.stdout + done.stderr)


@SKIP_BASH
class TheGovernancePreflight(unittest.TestCase):
    TITLE = "The base, the Foundry resource and the rights that the AI security needs are there"
    AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"provider show --namespace "*)
    namespace=$(sed 's/.*--namespace \\([A-Za-z.]*\\).*/\\1/' <<< "$*")
    if [ "$namespace" = "$FAKE_MISSING_PROVIDER" ]; then printf 'NotRegistered'; else printf 'Registered'; fi ;;
  *"resource list"*"Microsoft.OperationalInsights/workspaces"*) printf '%s' "$FAKE_WORKSPACE" ;;
  *"resource list"*"Microsoft.CognitiveServices/accounts"*) printf '%s' "$FAKE_FOUNDRY" ;;
  *"role assignment list"*) if [ "$FAKE_ROLES" = "FAIL" ]; then echo "ERROR: denied" >&2; exit 1; fi; printf '%b' "$FAKE_ROLES" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
    GROUP = "/subscriptions/sub-of-the-project/resourceGroups/rg-of-the-project"

    def run_it(self, **changes):
        env = {"DEPLOYER_ID": DEPLOYER, "FOUNDRY_ACCOUNT": "aif-meternaut-agents-abc", "FAKE_MISSING_PROVIDER": "", "FAKE_WORKSPACE": "log-meternaut", "FAKE_FOUNDRY": "aif-meternaut-agents-abc",
               "FAKE_ROLES": f"{self.GROUP}\\t/subscriptions/sub-of-the-project/providers/Microsoft.Authorization/roleDefinitions/{RESOURCE_POLICY_CONTRIBUTOR}\\n", **SETTINGS, **changes}
        return ws.run_step_script(self.TITLE, {"az": self.AZ}, env)

    def test_everything_there_goes_on(self):
        done, lines, _ = self.run_it()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("The deploy identity holds a role on the group that can write a policy assignment.", done.stdout)
        role_call = next(line for line in lines if "role assignment list" in line)
        self.assertIn(f"--assignee-object-id {DEPLOYER}", role_call)
        self.assertIn(f"--scope {self.GROUP}", role_call)
        self.assertIn("--include-inherited", role_call)

    def test_owner_or_resource_policy_contributor_at_the_group_or_above_it_is_enough_and_contributor_alone_is_not(self):
        sub = "/subscriptions/sub-of-the-project"
        for scope, role, ok in ((self.GROUP, RESOURCE_POLICY_CONTRIBUTOR, True), (self.GROUP, OWNER_ROLE, True), (sub, OWNER_ROLE, True), (sub, RESOURCE_POLICY_CONTRIBUTOR, True),
                                ("/providers/Microsoft.Management/managementGroups/mg-of-the-estate", OWNER_ROLE, True), ("/", OWNER_ROLE, True),
                                (self.GROUP, "b24988ac-6180-42a0-ab88-20f7382dd24c", False), (self.GROUP + "/providers/Microsoft.Storage/storageAccounts/x", OWNER_ROLE, False),
                                ("/subscriptions/another", OWNER_ROLE, False), (self.GROUP + "x", OWNER_ROLE, False)):
            with self.subTest(scope=scope, role=role):
                done, _, _ = self.run_it(FAKE_ROLES=f"{scope}\\t{sub}/providers/Microsoft.Authorization/roleDefinitions/{role}\\n")
                self.assertEqual(done.returncode == 0, ok, done.stdout + done.stderr)

    def test_a_missing_role_stops_early_and_names_the_right_who_gives_it_and_where(self):
        done, _, _ = self.run_it(FAKE_ROLES="")
        said = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1)
        for words in ("holds no role that can write a policy assignment on the group (Resource Policy Contributor, or Owner)", "Contributor cannot", "Owner or User Access Administrator there",
                      "environment/BOOTSTRAP.md, the section on the AI security, step G1", "tools/governance-setup.py grant", "Nothing was changed."):
            self.assertIn(words, said, words)

    def test_a_resource_provider_that_is_not_registered_stops_early_with_its_own_name(self):
        for provider in ("Microsoft.Authorization", "Microsoft.Insights", "Microsoft.OperationalInsights", "Microsoft.PolicyInsights"):
            with self.subTest(provider=provider):
                done, _, _ = self.run_it(FAKE_MISSING_PROVIDER=provider)
                said = done.stdout + done.stderr
                self.assertEqual(done.returncode, 1)
                self.assertIn(f"The resource provider {provider} is NotRegistered", said)
                self.assertIn(f"az provider register --namespace {provider}", said)
                self.assertIn("step G2", said)

    def test_the_workspace_and_the_foundry_resource_have_to_be_there_and_the_message_names_the_action_that_makes_them(self):
        done, _, _ = self.run_it(FAKE_WORKSPACE="")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Run base first", done.stdout + done.stderr)
        done, _, _ = self.run_it(FAKE_FOUNDRY="None")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Run foundry first", done.stdout + done.stderr)

    def test_an_object_id_that_was_not_read_and_a_list_that_cannot_be_read_stop_the_run(self):
        done, _, _ = self.run_it(DEPLOYER_ID="")
        self.assertEqual(done.returncode, 1)
        self.assertIn("The object id of the deploy identity was not read from its token", done.stdout + done.stderr)
        done, _, _ = self.run_it(FAKE_ROLES="FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertIn("could not be read", done.stdout + done.stderr)

    def test_the_step_only_reads(self):
        done, lines, _ = self.run_it()
        for call in lines:
            for word in (" put ", " post ", " patch ", " delete ", " create ", "--yes"):
                self.assertNotIn(word, call + " ", call)


@SKIP_BASH
class TheTelemetryPreflight(unittest.TestCase):
    TITLE = "The AI Gateway is there, the provider is registered, the component reports its endpoints and the gateway's identity may send to them"
    AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"aigateways/"*)
    if [ "$FAKE_GATEWAY" = "ABSENT" ]; then echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.ApiManagement/aigateways/x' was not found." >&2; exit 1; fi
    if [ "$FAKE_GATEWAY" = "FAIL" ]; then echo "ERROR: (InternalServerError) try again" >&2; exit 1; fi
    printf '%s' "$FAKE_GATEWAY" ;;
  *"provider show --namespace Microsoft.Monitor"*) printf '%s' "$FAKE_STATE" ;;
  *"components/appi-meternaut"*) printf '%s' "$FAKE_COMPONENT" ;;
  *"role assignment list"*) if [ "$FAKE_ROLES" = "FAIL" ]; then echo "ERROR: (AuthorizationFailed) denied" >&2; exit 1; fi; printf '%b' "$FAKE_ROLES" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
    RULE = "/subscriptions/sub-of-the-project/resourceGroups/mrg-managed/providers/Microsoft.Insights/dataCollectionRules/dcr-x"
    COMPONENT = f"https://logs.example/v1/logs https://traces.example/v1/traces https://metrics.example/v1/metrics {RULE}"

    def run_it(self, **changes):
        env = {"GATEWAY_NAME": "aigw-meternaut-abc", "INSIGHTS_NAME": "appi-meternaut", "FAKE_GATEWAY": GATEWAY_PRINCIPAL, "FAKE_STATE": "Registered", "FAKE_COMPONENT": self.COMPONENT,
               "FAKE_ROLES": f"/providers/Microsoft.Authorization/roleDefinitions/{MONITORING_METRICS_PUBLISHER}\\n", **SETTINGS, "ACTION": "gateway-telemetry", **changes}
        return ws.run_step_script(self.TITLE, {"az": self.AZ}, env)

    def test_when_everything_is_in_place_it_goes_on_and_says_what_it_found(self):
        done, lines, _ = self.run_it()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("The AI Gateway's identity holds Monitoring Metrics Publisher on the data collection rule.", done.stdout)
        role_call = next(line for line in lines if "role assignment list" in line)
        self.assertIn(f"--assignee-object-id {GATEWAY_PRINCIPAL}", role_call)
        self.assertIn(f"--scope {self.RULE}", role_call)

    def test_a_gateway_that_is_not_there_stops_early_and_says_which_action_makes_it(self):
        done, _, _ = self.run_it(FAKE_GATEWAY="ABSENT")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Run aigateway first", done.stdout + done.stderr)
        done, _, _ = self.run_it(FAKE_GATEWAY="FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertIn("could not be read", done.stdout + done.stderr)
        done, _, _ = self.run_it(FAKE_GATEWAY="None")
        self.assertEqual(done.returncode, 1)
        self.assertIn("has no identity of its own", done.stdout + done.stderr)

    def test_a_provider_that_is_not_registered_stops_early_with_the_hand_step(self):
        done, _, _ = self.run_it(FAKE_STATE="NotRegistered")
        said = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1)
        for words in ("Microsoft.Monitor is NotRegistered", "step G2", "az provider register --namespace Microsoft.Monitor", "The deploy identity holds no right on the subscription", "Nothing was changed."):
            self.assertIn(words, said, words)

    def test_a_component_that_reports_no_endpoint_yet_stops_early_and_says_to_run_base_and_wait(self):
        for component in ("null null null null", "https://l.example/v1/logs null https://m.example/v1/metrics null", " "):
            with self.subTest(component=component):
                done, _, _ = self.run_it(FAKE_COMPONENT=component)
                said = done.stdout + done.stderr
                self.assertEqual(done.returncode, 1)
                for words in ("reports no OpenTelemetry endpoint yet", "turns its OpenTelemetry ingestion on", "run base, wait ten minutes, and run gateway-telemetry again", "Nothing was changed."):
                    self.assertIn(words, said, words)

    def test_a_missing_role_on_the_data_collection_rule_stops_early_and_names_the_hand_step_and_why_nothing_else_can_give_it(self):
        done, _, _ = self.run_it(FAKE_ROLES="")
        said = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1)
        for words in ("does not hold Monitoring Metrics Publisher on the data collection rule", "a resource group that the platform manages, behind a deny assignment", "the deploy identity holds no right there",
                      "step G3", "tools/governance-setup.py grant", "A role takes up to ten minutes to apply", "Nothing was changed."):
            self.assertIn(words, said, words)
        done, _, _ = self.run_it(FAKE_ROLES="/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c\\n")
        self.assertEqual(done.returncode, 1, "another role is not this one")

    def test_a_rule_that_is_not_reported_or_a_list_that_cannot_be_read_is_a_warning_and_the_read_back_after_the_deploy_says_whether_the_telemetry_arrives(self):
        done, _, _ = self.run_it(FAKE_COMPONENT="https://l.example/v1/logs https://t.example/v1/traces https://m.example/v1/metrics null")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("::warning::The component does not report its data collection rule", done.stdout)
        done, _, _ = self.run_it(FAKE_ROLES="FAIL")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("::warning::The role assignments on the data collection rule could not be read", done.stdout)

    def test_the_step_only_reads(self):
        done, lines, _ = self.run_it()
        for call in lines:
            for word in (" put ", " post ", " patch ", " delete ", " create ", "--yes"):
                self.assertNotIn(word, call + " ", call)


@SKIP_BASH
class TheSettingsStepOfTheAiSecurity(unittest.TestCase):
    TITLE = "Work out the settings of the AI security"
    AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"/providers/Microsoft.Web/sites/"*) printf '%s' "$FAKE_CASES" ;;
  *"/projects/"*) printf '%s' "$FAKE_PROJECT" ;;
  *"userAssignedIdentities/id-meternaut-operator"*) printf '%s' "$FAKE_OPERATOR" ;;
  *"diagnosticSettings"*)
    if [ "$FAKE_DIAGNOSTICS" = "FAIL" ]; then echo "ERROR: (InternalServerError) try again" >&2; exit 1; fi
    printf '%s' "$FAKE_DIAGNOSTICS" ;;
  *"policySetDefinitions/5207647b-3e83-4e28-b836-c382cb5e2a2e"*)
    if [ "$FAKE_INITIATIVE" = "ABSENT" ]; then echo "ERROR: (PolicySetDefinitionNotFound) not found" >&2; exit 1; fi
    if [ "$FAKE_INITIATIVE" = "FAIL" ]; then echo "ERROR: (InternalServerError) try again" >&2; exit 1; fi
    printf '5207647b-3e83-4e28-b836-c382cb5e2a2e' ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
    PYTHON = """#!/bin/bash
if [ "$2" = "build" ]; then
  echo "build operator=[${OPERATOR_PRINCIPAL_ID-unset}] cases=[${CASES_SYSTEM_PRINCIPAL_ID-unset}] project=[${FOUNDRY_PROJECT_PRINCIPAL_ID-unset}] diagnostics=[${ENV_FOUNDRY_DIAGNOSTICS_EXIST-unset}] initiative=[${GUARDRAIL_INITIATIVE_AVAILABLE-unset}] args=[$*]" >> "$FAKE_LOG"
  if [ "$FAKE_BUILD" = "FAIL" ]; then echo "error: the rule that watches the gateway needs the object id of every identity on it" >&2; exit 2; fi
  printf 'cases_function_app_name=func-x\\ngovernance_files=true\\ngovernance_callers=3\\ngovernance_callers_missing=\\ngateway_telemetry=true\\naigateway_name=aigw-x\\n'
else
  echo "check $*" >> "$FAKE_LOG"
fi
"""
    A, B, C = "12345678-dddd-eeee-ffff-123456789012", "12345678-eeee-ffff-1111-123456789012", "12345678-aaaa-bbbb-cccc-123456789012"

    def run_it(self, **changes):
        env = {"ENV_BUDGET_START": "2026-11-01", "FOUNDRY_ACCOUNT": "aif-meternaut-agents-abc", "FOUNDRY_PROJECT": "meternaut", "CASES_APP": "func-x", "FAKE_CASES": self.A, "FAKE_PROJECT": self.B,
               "FAKE_OPERATOR": self.C, "FAKE_DIAGNOSTICS": "1", "FAKE_INITIATIVE": "", **SETTINGS, **changes}
        return ws.run_step_script(self.TITLE, {"az": self.AZ, "python3": self.PYTHON}, env)

    def test_the_three_identities_the_landing_zones_setting_and_the_initiative_go_to_the_builder_with_the_access_list(self):
        done, lines, out = self.run_it()
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        (build,) = [line for line in lines if line.startswith("build ")]
        for word in (f"operator=[{self.C}]", f"cases=[{self.A}]", f"project=[{self.B}]", "diagnostics=[true]", "initiative=[true]", "--governance environment/aigateway/contracts.json",
                     "--aigateway-policies environment/aigateway/policies.json", '--out-dir ' ):
            self.assertIn(word, build, word)
        self.assertNotIn("--preview", build, "the files of this action are built for real: the identities are asked for, by name")
        self.assertEqual(out.splitlines(), ["governance_files=true", "governance_callers=3", "governance_callers_missing=", "gateway_telemetry=true"], "only the lines of the AI security reach the outputs")
        self.assertNotIn(self.A, done.stdout, "no object id is printed")

    def test_both_files_are_checked_against_the_templates_that_were_compiled(self):
        _, lines, _ = self.run_it()
        checks = [line for line in lines if line.startswith("check ")]
        self.assertEqual(len(checks), 2)
        self.assertRegex(checks[0], r"--params \S+/aisec/governance\.parameters\.json --template \S+/governance\.json --label governance")
        self.assertRegex(checks[1], r"--params \S+/aisec/gateway-telemetry\.parameters\.json --template \S+/gateway-telemetry\.json --label gateway-telemetry")

    def test_an_identity_that_is_not_there_or_is_not_an_object_id_is_passed_empty_and_the_builder_decides(self):
        _, lines, _ = self.run_it(FAKE_CASES="", FAKE_OPERATOR="None", FAKE_PROJECT="not-a-guid")
        (build,) = [line for line in lines if line.startswith("build ")]
        self.assertIn("operator=[]", build)
        self.assertIn("cases=[]", build)
        self.assertIn("project=[]", build)

    def test_the_builders_refusal_stops_the_run_with_its_words(self):
        done, _, out = self.run_it(FAKE_BUILD="FAIL")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("needs the object id of every identity on it", done.stdout + done.stderr)
        self.assertEqual(out, "")

    def test_a_diagnostic_setting_of_the_landing_zone_is_counted_without_the_one_of_the_template(self):
        block = step(HUB, self.TITLE)
        self.assertIn("name!='meternaut-foundry-to-workspace'", block, "a second run does not mistake the template's own setting for the landing zone's")
        for counted, expected in (("0", "false"), ("2", "true"), ("", "false"), ("1", "true")):
            with self.subTest(counted=counted):
                _, lines, _ = self.run_it(FAKE_DIAGNOSTICS=counted)
                self.assertIn(f"diagnostics=[{expected}]", next(line for line in lines if line.startswith("build ")))

    def test_the_initiative_that_the_tenant_does_not_offer_is_not_assigned_and_a_read_that_fails_is_a_warning_while_a_setting_that_cannot_be_read_stops_the_run(self):
        _, lines, _ = self.run_it(FAKE_INITIATIVE="ABSENT")
        self.assertIn("initiative=[false]", next(line for line in lines if line.startswith("build ")))
        done, lines, _ = self.run_it(FAKE_INITIATIVE="FAIL")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("::warning::The preview initiative for the guardrail could not be read", done.stdout)
        self.assertIn("initiative=[false]", next(line for line in lines if line.startswith("build ")))
        done, _, _ = self.run_it(FAKE_DIAGNOSTICS="FAIL")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The diagnostic settings of the Foundry resource could not be read", done.stdout + done.stderr)

    def test_the_step_only_reads(self):
        _, lines, _ = self.run_it()
        for call in (line for line in lines if line.startswith("az ")):
            for word in (" put ", " post ", " patch ", " delete ", " create ", "--yes"):
                self.assertNotIn(word, call + " ", call)


@SKIP_BASH
class TheDriftCheckStep(unittest.TestCase):
    TITLE = "Check for drift from the control plane, with reads only"
    PYTHON = """#!/bin/bash
echo "python3 $*" >> "$FAKE_LOG"
"""

    def run_it(self, **env):
        return ws.run_step_script(self.TITLE, {"python3": self.PYTHON}, {"HUB_SOURCE_SHA": COMMIT, "CASES_PUBLIC_ACCESS": "Enabled", **SETTINGS, "ACTION": "drift-check", **env})

    def test_the_tool_gets_the_group_the_files_this_commit_and_the_app_folder_and_no_write_and_no_directory(self):
        done, lines, _ = self.run_it()
        self.assertEqual(done.returncode, 0, done.stderr)
        (call,) = lines
        for word in ("tools/drift-check.py", "--subscription sub-of-the-project", "--resource-group rg-of-the-project", "--models environment/models.json", "--policies environment/aigateway/policies.json",
                     "--access-list environment/aigateway/contracts.json", f"--commit {COMMIT}", "--app-dir src/case-functions", "--cases-public-access Enabled", "--json ", "--summary "):
            self.assertIn(word, call, word)
        for word in ("--graph", "--read-subscription", "--accepted-exemptions", "--accepted-deny"):
            self.assertNotIn(word, call, f"{word}: not without a reason")

    def test_what_the_owner_accepted_goes_to_the_tool_only_when_it_is_set(self):
        _, lines, _ = self.run_it(DRIFT_ACCEPTED_EXEMPTIONS="Deny-Public-Endpoints/waiver", DRIFT_ACCEPTED_DENY="none")
        self.assertIn("--accepted-exemptions Deny-Public-Endpoints/waiver", lines[0])
        self.assertIn("--accepted-deny none", lines[0])

    def test_the_run_takes_the_exit_code_of_the_tool_so_that_a_failed_control_is_a_red_run(self):
        block = step(HUB, self.TITLE)
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertNotIn("|| true", script)
        self.assertNotIn("continue-on-error", block)
        self.assertIn("if: inputs.action == 'drift-check'", block)
        self.assertIn("timeout-minutes: 30", block)
        self.assertIn("the app's own daily check", block, "the step names the in-app half and says that this tool reads its lines")


class TheSummaryAndTheDescription(unittest.TestCase):
    def test_the_description_names_each_new_action_what_it_needs_first_and_that_the_check_only_reads(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', HUB).group(1)
        for words in ("governance: the policy, the alerts and the workbook of the AI security", "It needs cases, foundry and operator first.", "gateway-telemetry: the AI Gateway's telemetry exporter",
                      "It needs aigateway and base first.", "drift-check: read Azure and say, for each control of the AI security, PASS, FAIL or UNKNOWN", "It only reads (GET requests and two queries)",
                      "The workflow drift.yml runs the same tool with an identity of its own that can only read."):
            self.assertIn(words, description, words)

    def test_the_summary_of_the_new_actions_names_the_hand_steps_and_never_a_value_of_the_estate(self):
        block = step(HUB, "What was done")
        for words in ("step G1 of environment/BOOTSTRAP.md", "step G2", "step G3", "the repository variables DRIFT_ACCEPTED_EXEMPTIONS and DRIFT_ACCEPTED_DENY", "UNKNOWN is never PASS", "the e-mail holds the rule's name, a count and a link, and never a line of the telemetry"):
            self.assertIn(words, block, words)


if __name__ == "__main__":
    unittest.main()
