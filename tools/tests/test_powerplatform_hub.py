"""The Hub's action powerplatform (docs/proposals/19-teams-cards-through-power-automate.md) and the preview of the AI security's policy that skips itself when the deploy identity cannot write one.

The action makes the Azure side of the Teams cards: the subnet snet-powerplatform and the enterprise policy ep-meternaut-netinjection (environment/powerplatform/main.bicep). What these tests pin: that it is offered
and described, that its nine steps run for it alone, in the order that keeps the landing zone's route table on the subnet and the log of a public repository free of an identifier, that each step stops where it has to and
says what a person does, that nothing but the one deploy writes, that no new secret or variable is read, and that the summary and the documents say what is true. The preview of the AI security's templates, which failed
the whole `what-if` while the deploy identity held no role that can write a policy assignment, is tested here as well. The scripts of the steps are run with bash and stand-ins for the commands that they call: no test
calls Azure, GitHub or Power Platform."""
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(file_name, label, register=False):
    spec = importlib.util.spec_from_file_location(label, ROOT / file_name)
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


ws = load("tools/tests/test_workflow_scripts.py", "workflow_scripts_of_the_powerplatform_hub_tests")
ep = load("tools/environment-params.py", "environment_params_of_the_powerplatform_hub_tests")
pp = load("tools/powerplatform.py", "powerplatform_of_the_powerplatform_hub_tests", register=True)
wl = load("tools/workflow-lint.py", "workflow_lint_of_the_powerplatform_hub_tests")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


WORKFLOW = ws.WORKFLOW
TEMPLATE = read("environment/powerplatform/main.bicep")
BASH = ws.BASH

GUARD = "The resource provider Microsoft.PowerPlatform is registered and the virtual network is there, which the subnet and the enterprise policy of Power Platform need"
EXISTS = "Find out whether the subnet of Power Platform and its enterprise policy are there already"
SETTINGS = "Work out the settings of the subnet and the enterprise policy of Power Platform"
PREVIEW = "What the subnet and the enterprise policy of Power Platform would change"
DEPLOY = "Deploy the subnet and the enterprise policy of Power Platform"
WAIT = "Wait until the landing zone has put its route table on the subnet of Power Platform"
LOGIN = ("Sign in to Azure again for the read-back of the subnet and the enterprise policy of Power Platform, because the deploy and the wait for the route table can take up to 30 minutes and the first "
         "sign-in's credential lasts five minutes")
READ_BACK = "Read the subnet and the enterprise policy of Power Platform back from Azure"
HAND_STEPS = "The steps that a person does by hand for the Teams cards"
CHAIN = [GUARD, EXISTS, SETTINGS, PREVIEW, DEPLOY, WAIT, LOGIN, READ_BACK, HAND_STEPS]
AISEC_PREVIEW = "What the AI security's templates would change"

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-of-the-project"
SCOPE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
VNET = f"{SCOPE}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut"
TABLE = f"{SCOPE}/providers/Microsoft.Network/routeTables/rt-landing-zone"
NSG = f"{SCOPE}/providers/Microsoft.Network/networkSecurityGroups/nsg-meternaut-powerplatform"
DEPLOYER = "5a1c0de0-0000-4000-8000-0000000000de"
RESOURCE_POLICY_CONTRIBUTOR = "36243c78-bf99-498c-9df9-86d9f8d28608"
OWNER_ROLE = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
CONTRIBUTOR_ROLE = "b24988ac-6180-42a0-ab88-20f7382dd24c"
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SLEEP = 'sleep() { echo "sleep $*" >> "$FAKE_LOG"; }\n'
BASE_ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "GITHUB_RUN_ID": "12345", "ACTION": "powerplatform"}
SKIP_BASH = unittest.skipIf(BASH is None, "no bash on this machine")


def blocks():
    """Every step of the workflow, in order, with its name and its text."""
    return re.findall(r"(?ms)^      - name: (.+?)\n(.*?)(?=^      - |\Z)", WORKFLOW)


def step(name):
    (text,) = [body for title, body in blocks() if title == name]
    return text


def code_of(name):
    """The script of a step without its comment lines."""
    run = step(name).split("        run: |\n", 1)[1]
    return "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))


def run(name, stand_ins, **env):
    return ws.run_step_script(name, stand_ins, {**BASE_ENV, **env}, prelude=SLEEP)


def said(done):
    return done.stdout + done.stderr


class TheActionIsOfferedAndDescribed(unittest.TestCase):
    def test_it_is_offered_between_loop_check_and_operator_and_the_four_checks_of_the_agents_are_still_the_last_options(self):
        options = re.findall(r"(?m)^          - (\S+)$", re.search(r"(?ms)^      action:\n(.*?)^      \w", WORKFLOW).group(1))
        self.assertEqual(options[options.index("loop-check") + 1:options.index("loop-check") + 3], ["powerplatform", "operator"])
        self.assertEqual(options.count("powerplatform"), 1)
        self.assertEqual(options[-4:], ["agents-drift", "foundry-evals", "foundry-redteam", "agent365-check"])

    def test_the_description_says_what_it_makes_what_it_does_not_and_what_it_needs_first(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        sentence = description.split(" powerplatform: ")[1].split(" foundry: ")[0]
        for words in ("the Azure side of the Teams cards (docs/proposals/19-teams-cards-through-power-automate.md)", "the subnet snet-powerplatform, which is delegated to Microsoft.PowerPlatform/enterprisePolicies",
                      "the enterprise policy ep-meternaut-netinjection (kind NetworkInjection, the Power Platform geography Sweden, whose one Azure region is swedencentral)",
                      "It makes no role, private endpoint, private DNS object, link or peering, and it links no environment", "tools/powerplatform.py, a tool that never runs in a pipeline",
                      "unless the resource provider Microsoft.PowerPlatform is registered (a person registers it once)", "a free /27 for the subnet (no range is invented: the owner decides what else will do)",
                      "makes each only while it is not there (AGENTS.md rule 27; Power Platform refuses every write to a policy that an environment is linked to)",
                      "waits up to 20 minutes for the landing zone's route table on the subnet (no environment is linked before the table is there)", "prints the hand steps with placeholders only, because the log of this repository is public",
                      "It needs model-side first and is run after cases, which makes the queue teams-cards."):
            self.assertIn(words, sentence, words)
        self.assertNotIn('"', sentence, "the description is one quoted value on one line")


class TheStepsFollowTheOrderThatKeepsTheRouteTableOnTheSubnet(unittest.TestCase):
    def names(self):
        return [title for title, _ in blocks()]

    def test_the_steps_that_run_for_powerplatform_are_these_nine_in_this_order_and_follow_one_another_before_the_summary(self):
        ran = [title for title, body in blocks() if re.search(r"(?m)^        if: inputs\.action == 'powerplatform'$", body)]
        self.assertEqual(ran, CHAIN)
        names = self.names()
        positions = [names.index(name) for name in CHAIN]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(CHAIN))), "no step of another action is in between")
        self.assertEqual(names[positions[-1] + 1], "What was done", "the summary is the step after the last: the hand steps are printed before it")
        self.assertEqual(len(re.findall(r"inputs\.action == 'powerplatform'", WORKFLOW)), 9, "and no other step names the action: the shared steps are the same for every action")

    def test_the_shared_steps_are_not_changed_for_the_action_so_that_every_other_action_gets_the_files_and_reads_that_it_got_before(self):
        settings = step("Work out the settings")
        self.assertNotIn("--powerplatform", settings)
        self.assertNotIn("ENV_PP_", settings)
        network = step("Find out what of the network is there already")
        self.assertNotIn("powerplatform", network, "the read of the policy needs a provider that may not be registered, so no other action looks for it")
        compiled = code_of("The templates compile, for the check of their parameter files")
        self.assertNotIn("powerplatform", compiled)

    def test_the_guard_comes_first_then_the_reads_then_the_settings_then_the_preview_then_the_one_deploy_then_the_wait_then_the_sign_in_and_the_read_back(self):
        names = self.names()
        for earlier, later in zip(CHAIN, CHAIN[1:]):
            self.assertLess(names.index(earlier), names.index(later), f"{earlier!r} before {later!r}")
        self.assertEqual(WORKFLOW.count("--template environment/powerplatform/main.bicep"), 2, "the preview and the deploy, nothing else")
        self.assertEqual(code_of(DEPLOY).count("az-deploy.py create"), 1)
        self.assertEqual(code_of(PREVIEW).count("az-deploy.py what-if"), 1)
        self.assertNotIn("az-deploy.py create", code_of(PREVIEW))
        self.assertNotIn("az-deploy.py what-if", code_of(DEPLOY))

    def test_the_sign_in_before_the_read_back_is_the_same_pinned_action_with_the_same_three_secrets_as_every_other(self):
        block = step(LOGIN)
        self.assertRegex(block, r"uses: azure/login@[0-9a-f]{40} # v3\.1\.0\n")
        for line in ("client-id: ${{ secrets.AZURE_CLIENT_ID }}", "tenant-id: ${{ secrets.AZURE_TENANT_ID }}", "subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}", "if: inputs.action == 'powerplatform'"):
            self.assertIn(line, block, line)
        self.assertEqual(len(set(re.findall(r"uses: azure/login@([0-9a-f]{40})", WORKFLOW))), 1, "one pin of the action for every sign-in")
        names = self.names()
        self.assertEqual(names[names.index(WAIT) + 1], LOGIN, "the sign-in follows the wait at once")
        self.assertEqual(names[names.index(LOGIN) + 1], READ_BACK)

    def test_the_step_that_waits_has_the_timeout_of_the_wait_of_the_ai_gateway(self):
        self.assertIn("        timeout-minutes: 25\n", step(WAIT))
        self.assertIn("        timeout-minutes: 20\n", step(READ_BACK))

    def test_the_wait_is_not_before_the_deploy_because_the_table_is_put_on_a_subnet_that_is_there(self):
        names = self.names()
        self.assertLess(names.index(DEPLOY), names.index(WAIT))


class NothingNewIsReadAndNothingIsWrittenButTheDeploy(unittest.TestCase):
    def test_no_step_of_the_action_reads_a_secret_that_the_others_do_not_or_a_variable_and_only_the_sign_in_names_a_secret(self):
        for name in CHAIN:
            block = step(name)
            if name == LOGIN:
                self.assertEqual(sorted(re.findall(r"secrets\.([A-Z_]+)", block)), ["AZURE_CLIENT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID"])
            else:
                self.assertNotIn("secrets.", block, name)
            self.assertNotIn("vars.", block, name)
        self.assertEqual(set(re.findall(r"\bsecrets\.([A-Za-z_]+)", "\n".join(line for line in WORKFLOW.splitlines() if not line.lstrip().startswith("#")))), wl.ESTATE_SECRETS)

    def test_no_step_writes_in_azure_but_the_one_deploy_and_none_gives_a_role_registers_a_provider_or_reads_a_key(self):
        for name in CHAIN:
            script = code_of(name) if name != LOGIN else ""
            self.assertNotRegex(script, r"--method (put|patch|post|delete)", name)
            for word in ("az role", "az group", "az network", "az resource", "listKeys", "listSecrets", "--yes", "az provider register"):
                if word == "az provider register":
                    for line in script.splitlines():
                        if word in line:
                            self.assertIn("::error::", line, "only an error message that tells a person what to run names the command")
                else:
                    self.assertNotIn(word, script, f"{name}: {word}")
        self.assertEqual(re.findall(r"python3 tools/(\S+) (\w+)", code_of(DEPLOY)), [("az-deploy.py", "create")])

    def test_the_script_of_no_step_holds_an_expression_of_the_workflow_and_each_value_reaches_it_through_env(self):
        for name in CHAIN:
            run_text = step(name).split("        run: |\n", 1)[1] if "        run: |\n" in step(name) else ""
            self.assertNotIn("${{", run_text, name)

    def test_no_line_prints_an_identifier_a_range_or_a_name_that_ends_in_the_masked_digest(self):
        for name in CHAIN:
            if name == LOGIN:
                continue
            for line in code_of(name).splitlines():
                stripped = line.strip()
                if not re.match(r"(echo|printf|tee|cat)\b", stripped):
                    continue
                for variable in ("prefix", "network_group", "table", "policy_network", "DEPLOYER_ID", "ENV_SUBSCRIPTION_ID", "ENV_VNET_PREFIX", "STORAGE_ACCOUNT", "system_id"):
                    if variable == "prefix" and "${prefix##*/}" in stripped:
                        continue
                    if variable == "table" and "${table##*/}" in stripped:
                        continue
                    self.assertNotRegex(stripped, rf"\${{?{variable}\b(?!##)", f"{name}: {stripped}")

    def test_the_route_table_and_the_policys_system_id_are_never_printed_whole(self):
        self.assertIn("The landing zone added the route table ${table##*/} to the subnet $SUBNET_NAME.", code_of(WAIT))
        self.assertIn("length(properties.systemId)", code_of(READ_BACK))
        self.assertNotRegex(code_of(READ_BACK), r"properties\.systemId'|properties\.systemId\"|--query properties\.systemId")


class TheNamesAreTheOnesOfTheBuilderTheTemplateAndTheTool(unittest.TestCase):
    def test_the_names_that_the_steps_use_are_the_builders_constants_and_the_templates_and_the_tools(self):
        self.assertEqual(ep.POWERPLATFORM_SUBNET_NAME, "snet-powerplatform")
        self.assertEqual(ep.POWERPLATFORM_POLICY_NAME, "ep-meternaut-netinjection")
        self.assertEqual(pp.DEFAULT_POLICY_NAME, ep.POWERPLATFORM_POLICY_NAME)
        self.assertIn(f"var powerPlatformSubnetName = '{ep.POWERPLATFORM_SUBNET_NAME}'", TEMPLATE)
        self.assertIn("var enterprisePolicyName = 'ep-${workload}-netinjection'", TEMPLATE)
        self.assertIn("param workload string = 'meternaut'", TEMPLATE)
        self.assertIn("name: 'nsg-${workload}-powerplatform'", TEMPLATE)
        exists = code_of(EXISTS)
        self.assertIn(f"/subnets/{ep.POWERPLATFORM_SUBNET_NAME}\" 2025-05-01", exists)
        self.assertIn(f"/enterprisePolicies/{ep.POWERPLATFORM_POLICY_NAME}\" 2020-10-30-preview", exists)
        self.assertIn("check \"The network security group of the subnet\" nsg-meternaut-powerplatform", code_of(READ_BACK))
        self.assertIn(f"Microsoft.PowerPlatform/enterprisePolicies@{pp.POLICY_API}", TEMPLATE)
        self.assertEqual(pp.POLICY_API, "2020-10-30-preview")
        self.assertIn(f"Microsoft.Network/virtualNetworks/subnets@{pp.SUBNET_API}", TEMPLATE)
        self.assertEqual(pp.SUBNET_API, "2025-05-01")
        self.assertEqual(pp.DELEGATION, "Microsoft.PowerPlatform/enterprisePolicies")
        self.assertIn("Microsoft.PowerPlatform/enterprisePolicies", code_of(READ_BACK))

    def test_the_step_that_works_out_the_settings_passes_the_two_flags_and_the_folder_of_its_own_to_the_builder(self):
        block = step(SETTINGS)
        self.assertIn("ENV_PP_SUBNET_EXISTS: ${{ steps.powerplatform_exists.outputs.pp_subnet_exists }}", block)
        self.assertIn("ENV_PP_POLICY_EXISTS: ${{ steps.powerplatform_exists.outputs.pp_policy_exists }}", block)
        self.assertIn("ENV_BUDGET_START: ${{ steps.budget.outputs.start }}", block)
        self.assertIn('--out-dir "$RUNNER_TEMP/powerplatform" --powerplatform)', block, "a folder of its own: the files of the other actions are what they were")
        self.assertIn("id: powerplatform\n", block)
        self.assertIn("id: powerplatform_exists\n", step(EXISTS))

    def test_the_builders_outputs_that_the_later_steps_read_are_the_ones_that_the_builder_writes(self):
        settings = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "ENV_LOCATION": "swedencentral", "ENV_VNET_PREFIX": "10.53.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27",
                    "ENV_DNS_SERVERS": "10.20.0.4", "ENV_OWNER": "owner@example.com", "ENV_BUDGET_AMOUNT": "25", "ENV_BUDGET_START": "2026-11-01", "ENV_ALERT_EMAILS": "owner@example.com"}
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = ep.main(["build", "--models", str(ROOT / "environment" / "models.json"), "--out-dir", str(Path(tmp) / "powerplatform"), "--powerplatform"], environ=settings)
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "powerplatform" / "powerplatform.parameters.json").exists(), "the step reads the file from a folder of its own")
        outputs = dict(line.split("=", 1) for line in out.getvalue().splitlines() if "=" in line)
        for name in ("powerplatform_subnet_name", "powerplatform_policy_name", "powerplatform_geography", "powerplatform_files", "powerplatform_reason", "cards_queue_name", "powerplatform_subnet_prefix"):
            self.assertIn(name, outputs, name)
        self.assertEqual(outputs["powerplatform_files"], "true")
        taken = re.compile(re.search(r"grep -E '(.+?)' <<< \"\$outputs\"", code_of(SETTINGS)).group(1))
        for name, value in outputs.items():
            wanted = name.startswith("powerplatform_") and name != "powerplatform_subnet_prefix" or name == "cards_queue_name"
            self.assertEqual(taken.match(f"{name}={value}") is not None, wanted, f"{name}: the range is not copied to the outputs of the step, and the names that the later steps read are")


GUARD_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"provider show --namespace Microsoft.PowerPlatform --query registrationState"*)
    if [ "$FAKE_PROVIDER" = FAIL ]; then echo "ERROR: (AuthorizationFailed) denied" >&2; exit 1; fi
    printf '%s' "$FAKE_PROVIDER" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""


@SKIP_BASH
class TheGuardStopsBeforeAnythingIsChanged(unittest.TestCase):
    def go(self, **env):
        return run(GUARD, {"az": GUARD_AZ}, **{"NETWORK_EXISTS": "true", "FAKE_PROVIDER": "Registered", **env})

    def test_a_registered_provider_and_a_network_go_on(self):
        done, lines, _ = self.go()
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("The resource provider Microsoft.PowerPlatform is registered.", done.stdout)
        self.assertIn("The virtual network is there.", done.stdout)
        self.assertEqual(lines, ["az provider show --namespace Microsoft.PowerPlatform --query registrationState --output tsv"], "one read and nothing else")

    def test_a_provider_that_is_not_registered_stops_with_the_command_that_a_person_runs_and_says_that_nothing_was_changed(self):
        for state in ("NotRegistered", "Registering", ""):
            with self.subTest(state=state):
                done, _, _ = self.go(FAKE_PROVIDER=state)
                self.assertEqual(done.returncode, 1)
                self.assertIn(f"::error::The resource provider Microsoft.PowerPlatform is {state or 'not registered'} in the subscription", said(done))
                self.assertIn("a person who may (Contributor or Owner on the subscription) registers it once, with their own sign-in: az provider register --namespace Microsoft.PowerPlatform", said(done))
                self.assertIn("environment/BOOTSTRAP.md, the section on the Teams cards", said(done))
                self.assertIn("Nothing was changed.", said(done))

    def test_a_read_that_fails_stops_the_run(self):
        done, _, _ = self.go(FAKE_PROVIDER="FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertIn("The registration of the resource provider Microsoft.PowerPlatform could not be read", said(done))

    def test_a_network_that_is_not_there_stops_the_run_and_names_the_action_that_makes_it(self):
        done, _, _ = self.go(NETWORK_EXISTS="false")
        self.assertEqual(done.returncode, 1)
        self.assertIn("The virtual network is not there. Run model-side first: the subnet goes into it. Nothing was changed.", said(done))


EXISTS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"/subnets/snet-powerplatform?api-version=2025-05-01"*) answer="$FAKE_SUBNET"; name=snet-powerplatform ;;
  *"/enterprisePolicies/ep-meternaut-netinjection?api-version=2020-10-30-preview"*) answer="$FAKE_POLICY"; name=ep-meternaut-netinjection ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
case "$answer" in
  there) printf '%s' "$name" ;;
  absent) echo "ERROR: (ResourceNotFound) The Resource '$name' under resource group 'rg' was not found." >&2; exit 1 ;;
  *) echo "$answer" >&2; exit 1 ;;
esac
"""


@SKIP_BASH
class TheReadsSayWhetherTheSubnetAndThePolicyAreThere(unittest.TestCase):
    def go(self, **env):
        return run(EXISTS, {"az": EXISTS_AZ}, **{"VNET_NAME": "vnet-meternaut", "FAKE_SUBNET": "there", "FAKE_POLICY": "there", **env})

    def test_what_is_there_is_true_and_what_is_not_is_false_and_nothing_else_is_printed(self):
        for subnet, policy in (("there", "there"), ("there", "absent"), ("absent", "there"), ("absent", "absent")):
            with self.subTest(subnet=subnet, policy=policy):
                done, lines, out = self.go(FAKE_SUBNET=subnet, FAKE_POLICY=policy)
                self.assertEqual(done.returncode, 0, said(done))
                flags = {"there": "true", "absent": "false"}
                self.assertEqual(out.splitlines(), [f"pp_subnet_exists={flags[subnet]}", f"pp_policy_exists={flags[policy]}"])
                self.assertEqual(len(lines), 2)
                self.assertFalse(GUID.search(done.stdout), "no identifier is printed")
                self.assertIn(f"The subnet snet-powerplatform is there: {flags[subnet]}. The enterprise policy ep-meternaut-netinjection is there: {flags[policy]}.", done.stdout)

    def test_the_two_reads_use_the_api_versions_of_the_template_and_only_get(self):
        _, lines, _ = self.go()
        self.assertEqual(len(lines), 2)
        self.assertIn(f"https://management.azure.com{VNET}/subnets/snet-powerplatform?api-version=2025-05-01", lines[0])
        self.assertIn(f"https://management.azure.com{SCOPE}/providers/Microsoft.PowerPlatform/enterprisePolicies/ep-meternaut-netinjection?api-version=2020-10-30-preview", lines[1])
        for line in lines:
            self.assertIn("rest --method get", line)
            self.assertIn("--query name --output tsv", line)

    def test_a_read_that_is_refused_stops_the_run_and_is_not_taken_for_a_missing_resource(self):
        for broken in ("FAKE_SUBNET", "FAKE_POLICY"):
            with self.subTest(read=broken):
                done, _, out = self.go(**{broken: "(AuthorizationFailed) The client does not have authorization to perform action"})
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("could not be read", said(done))
                self.assertNotIn("pp_policy_exists", out)


SETTINGS_PY = """#!/bin/bash
echo "python3 $* [subnet=$ENV_PP_SUBNET_EXISTS policy=$ENV_PP_POLICY_EXISTS budget=$ENV_BUDGET_START]" >> "$FAKE_LOG"
case "$*" in
  *"tools/environment-params.py build "*)
    printf '%s\\n' "storage_account_name=stexample" "powerplatform_subnet_name=snet-powerplatform" "powerplatform_subnet_prefix=$FAKE_PREFIX" "powerplatform_policy_name=ep-meternaut-netinjection" \\
      "powerplatform_geography=sweden" "powerplatform_files=$FAKE_FILES" "powerplatform_reason=$FAKE_REASON" "cards_queue_name=teams-cards" ;;
esac
"""
SETTINGS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
"""


@SKIP_BASH
class TheSettingsStepStopsWhenThereIsNoRangeAndInventsNone(unittest.TestCase):
    def go(self, **env):
        return run(SETTINGS, {"python3": SETTINGS_PY, "az": SETTINGS_AZ},
                   **{"ENV_BUDGET_START": "2026-11-01", "ENV_PP_SUBNET_EXISTS": "true", "ENV_PP_POLICY_EXISTS": "false", "FAKE_FILES": "true", "FAKE_PREFIX": "10.99.0.96/27", "FAKE_REASON": "", **env})

    def test_with_a_range_it_builds_in_a_folder_of_its_own_compiles_and_checks_the_file_and_prints_the_length_of_the_range_alone(self):
        done, lines, out = self.go()
        self.assertEqual(done.returncode, 0, said(done))
        build, compile_, check = lines
        self.assertIn("python3 tools/environment-params.py build --models environment/models.json", build)
        self.assertRegex(build, r"--out-dir \S+/?powerplatform --powerplatform \[subnet=true policy=false budget=2026-11-01\]$")
        self.assertRegex(compile_, r"^az bicep build --file environment/powerplatform/main\.bicep --outfile \S+powerplatform\.json$")
        self.assertRegex(check, r"^python3 tools/environment-params\.py check --params \S+/powerplatform/powerplatform\.parameters\.json --template \S+powerplatform\.json --label powerplatform")
        self.assertIn("The subnet of Power Platform is a /27, the last free block of that size in the virtual network; no other subnet is touched.", done.stdout)
        self.assertNotIn("10.99.0", said(done), "the range is not printed: the log is public")
        outputs = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual(sorted(outputs), ["cards_queue_name", "powerplatform_files", "powerplatform_geography", "powerplatform_policy_name", "powerplatform_reason", "powerplatform_subnet_name"])
        self.assertEqual((outputs["powerplatform_files"], outputs["powerplatform_policy_name"], outputs["powerplatform_subnet_name"], outputs["powerplatform_geography"]), ("true", "ep-meternaut-netinjection", "snet-powerplatform", "sweden"))

    def test_the_two_flags_that_the_read_found_reach_the_builder_as_they_are(self):
        _, lines, _ = self.go(ENV_PP_SUBNET_EXISTS="false", ENV_PP_POLICY_EXISTS="true")
        self.assertIn("[subnet=false policy=true budget=2026-11-01]", lines[0])

    def test_with_no_range_it_stops_before_anything_is_compiled_checked_or_changed_and_gives_the_reason_of_the_builder(self):
        reason = "the virtual network has no free /27 beside its other subnets, and no range is invented: the owner decides whether a smaller subnet (a /28 is the least), a larger virtual network or another place will do"
        done, lines, out = self.go(FAKE_FILES="false", FAKE_PREFIX="", FAKE_REASON=reason)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"::error::The subnet of Power Platform is not made: {reason}. Nothing was changed. The owner decides what else will do", said(done))
        self.assertIn("no range is invented here", said(done))
        self.assertEqual(len(lines), 1, "only the builder ran: no compile, no check")
        self.assertIn("powerplatform_files=false", out)

    def test_a_builder_that_says_nothing_still_stops_the_run_with_a_message(self):
        done, _, _ = self.go(FAKE_FILES="", FAKE_REASON="")
        self.assertEqual(done.returncode, 1)
        self.assertIn("The subnet of Power Platform is not made", said(done))


PREVIEW_PY = """#!/bin/bash
echo "python3 $*" >> "$FAKE_LOG"
case "$*" in
  *"az-deploy.py create"*) printf '%s' "$FAKE_NAME" ;;
esac
if [ -n "$FAKE_FAIL" ]; then echo "ERROR: the deployment failed" >&2; exit 1; fi
"""


@SKIP_BASH
class ThePreviewAndTheDeploy(unittest.TestCase):
    def test_the_preview_is_one_what_if_of_the_template_with_the_file_of_the_settings_step(self):
        done, lines, _ = run(PREVIEW, {"python3": PREVIEW_PY})
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], rf"^python3 tools/az-deploy\.py what-if --subscription {SUBSCRIPTION} --resource-group {GROUP} --template environment/powerplatform/main\.bicep --parameters \S+/powerplatform/powerplatform\.parameters\.json$")

    def test_the_deploy_is_one_create_with_the_template_the_file_and_the_name_of_the_run_and_asks_for_the_name_of_the_policy(self):
        done, lines, _ = run(DEPLOY, {"python3": PREVIEW_PY}, EXPECTED_POLICY="ep-meternaut-netinjection", FAKE_NAME="ep-meternaut-netinjection")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(len(lines), 1)
        for words in (f"tools/az-deploy.py create --subscription {SUBSCRIPTION} --resource-group {GROUP}", "--template environment/powerplatform/main.bicep", "/powerplatform/powerplatform.parameters.json",
                      "--name powerplatform-12345", "--output enterprisePolicyName"):
            self.assertIn(words, lines[0], words)
        self.assertIn(f"The subnet snet-powerplatform and the enterprise policy ep-meternaut-netinjection are in resource group {GROUP}; each was made only when it was not there.", done.stdout)

    def test_a_deployment_that_names_another_policy_fails_its_step_and_a_failed_deployment_stops_the_run(self):
        done, _, _ = run(DEPLOY, {"python3": PREVIEW_PY}, EXPECTED_POLICY="ep-meternaut-netinjection", FAKE_NAME="ep-another-name")
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The deployment returned the enterprise policy ep-another-name, not ep-meternaut-netinjection", said(done))
        done, _, _ = run(DEPLOY, {"python3": PREVIEW_PY}, EXPECTED_POLICY="ep-meternaut-netinjection", FAKE_NAME="ep-meternaut-netinjection", FAKE_FAIL="1")
        self.assertNotEqual(done.returncode, 0)


WAIT_AZ = """#!/bin/bash
case "$*" in
  *"/subnets/snet-pe?"*) printf '%s' "$FAKE_PE_TABLE" ;;
  *"/subnets/snet-powerplatform?"*)
    n=$(cat "$FAKE_DIR/count" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$FAKE_DIR/count"
    echo "read snet-powerplatform $n" >> "$FAKE_LOG"
    if [ "$n" -ge "$FAKE_AFTER" ]; then printf '%s' "$FAKE_TABLE"; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""


@SKIP_BASH
class TheWaitIsForTheTableThatTheLandingZonePutsOnTheSubnet(unittest.TestCase):
    ENV = {"VNET_NAME": "vnet-meternaut", "SUBNET_NAME": "snet-powerplatform", "FAKE_PE_TABLE": TABLE, "FAKE_TABLE": TABLE, "FAKE_AFTER": "1"}

    def go(self, **changes):
        return run(WAIT, {"az": WAIT_AZ}, **{**self.ENV, **changes})

    def test_a_table_that_comes_on_the_third_look_is_waited_for_with_half_a_minute_between_the_looks_and_said_by_its_name_alone(self):
        done, lines, _ = self.go(FAKE_AFTER="3")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(lines, ["read snet-powerplatform 1", "sleep 30", "read snet-powerplatform 2", "sleep 30", "read snet-powerplatform 3"])
        self.assertIn("The landing zone added the route table rt-landing-zone to the subnet snet-powerplatform.", done.stdout)
        self.assertNotIn(SUBSCRIPTION, said(done))

    def test_a_table_that_never_comes_fails_after_twenty_minutes_and_says_that_the_subnet_and_the_policy_are_made_and_that_no_environment_is_to_be_linked(self):
        done, lines, _ = self.go(FAKE_AFTER="100000")
        self.assertEqual(done.returncode, 1)
        self.assertEqual((lines.count("sleep 30"), len([line for line in lines if line.startswith("read ")])), (39, 40), "40 looks half a minute apart: twenty minutes")
        self.assertIn("::error::The landing zone's network manager has put a route table on snet-pe and has not put one on snet-powerplatform in 20 minutes. The subnet and the enterprise policy are made, "
                      "and no environment is to be linked before the table is on the subnet. Nothing else was changed: run powerplatform again later, which repeats only what is missing and waits again.", said(done))

    def test_a_landing_zone_that_puts_no_table_on_the_network_is_not_waited_for(self):
        done, lines, _ = self.go(FAKE_PE_TABLE="")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(lines, [])
        self.assertIn("The endpoint subnet carries no route table, so the landing zone puts none on this network: there is nothing to wait for.", done.stdout)

    def test_a_table_that_is_there_already_is_found_at_the_first_look_which_is_how_a_second_run_goes(self):
        done, lines, _ = self.go()
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(lines, ["read snet-powerplatform 1"])


READ_BACK_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
url=""; query=""
while [ $# -gt 0 ]; do
  case "$1" in
    --url) url="$2"; shift ;;
    --query) query="$2"; shift ;;
  esac
  shift
done
case "$url" in
  *"/subnets/snet-powerplatform?"*) key=subnet ;;
  *"/enterprisePolicies/ep-meternaut-netinjection?"*) key=policy ;;
  *) echo "unexpected url: $url" >&2; exit 9 ;;
esac
case "$key:$query" in
  "subnet:properties.provisioningState") printf '%s' "${FAKE_STATE-Succeeded}" ;;
  "subnet:properties.delegations[].properties.serviceName") printf '%b' "${FAKE_DELEGATIONS-Microsoft.PowerPlatform/enterprisePolicies}" ;;
  "subnet:properties.networkSecurityGroup.id") printf '%s' "${FAKE_NSG-$FAKE_NSG_ID}" ;;
  "subnet:properties.defaultOutboundAccess") printf '%s' "${FAKE_OUTBOUND-False}" ;;
  "subnet:properties.addressPrefix") printf '%s' "${FAKE_PREFIX-10.99.0.96/27}" ;;
  "subnet:properties.routeTable.id") printf '%s' "${FAKE_TABLE-$FAKE_TABLE_ID}" ;;
  "policy:kind") printf '%s' "${FAKE_KIND-NetworkInjection}" ;;
  "policy:location") printf '%s' "${FAKE_LOCATION-sweden}" ;;
  "policy:length(properties.networkInjection.virtualNetworks)") printf '%s' "${FAKE_NETWORKS-1}" ;;
  "policy:properties.networkInjection.virtualNetworks[0].id") printf '%s' "${FAKE_POLICY_NETWORK-$FAKE_VNET_ID}" ;;
  "policy:properties.networkInjection.virtualNetworks[0].subnet.name") printf '%s' "${FAKE_POLICY_SUBNET-snet-powerplatform}" ;;
  "policy:length(properties.systemId)") if [ "$FAKE_SYSTEM_ID_LENGTH" = FAIL ]; then echo "ERROR: In function length(), invalid type for value: None" >&2; exit 1; fi; printf '%s' "${FAKE_SYSTEM_ID_LENGTH-36}" ;;
  *) echo "unexpected query: $key $query" >&2; exit 9 ;;
esac
"""


@SKIP_BASH
class TheReadBackFailsUnlessTheSubnetAndThePolicyAreAsTheTemplateWroteThem(unittest.TestCase):
    ENV = {"VNET_NAME": "vnet-meternaut", "SUBNET_NAME": "snet-powerplatform", "POLICY_NAME": "ep-meternaut-netinjection", "GEOGRAPHY": "sweden", "FAKE_NSG_ID": NSG, "FAKE_TABLE_ID": TABLE, "FAKE_VNET_ID": VNET}

    def go(self, **changes):
        return run(READ_BACK, {"az": READ_BACK_AZ}, **{**self.ENV, **changes})

    def test_what_the_template_wrote_passes_and_the_lines_hold_names_and_the_length_of_the_range_and_no_identifier(self):
        done, lines, _ = self.go()
        self.assertEqual(done.returncode, 0, said(done))
        for words in ("The state of the subnet snet-powerplatform: Succeeded.", "The delegation of the subnet: Microsoft.PowerPlatform/enterprisePolicies.", "The network security group of the subnet: nsg-meternaut-powerplatform.",
                      "The default outbound access of the subnet: false.", "The subnet is a /27.", "The landing zone's route table rt-landing-zone is on the subnet.",
                      "The kind of the enterprise policy ep-meternaut-netinjection: NetworkInjection.", "The location of the enterprise policy: sweden.", "The number of virtual networks of the enterprise policy: 1.",
                      "The virtual network of the enterprise policy: vnet-meternaut.", "The subnet of the enterprise policy: snet-powerplatform.", "The enterprise policy has a system id, which the link needs.",
                      "The subnet snet-powerplatform and the enterprise policy ep-meternaut-netinjection are in Azure as the template wrote them. No environment is linked: a Power Platform administrator does that."):
            self.assertIn(words, done.stdout, words)
        self.assertNotIn(SUBSCRIPTION, said(done))
        self.assertNotIn("10.99.0", said(done))
        self.assertFalse(GUID.search(said(done)))
        for call in lines:
            self.assertIn("rest --method get", call)
        self.assertIn("--query length(properties.systemId)", "\n".join(lines), "only the length of the system id is read")

    def test_each_difference_fails_the_run_and_the_line_says_which(self):
        cases = (("FAKE_STATE", "Updating", "The state of the subnet snet-powerplatform: expected Succeeded, read Updating."),
                 ("FAKE_DELEGATIONS", "", "The delegation of the subnet: expected Microsoft.PowerPlatform/enterprisePolicies, read nothing."),
                 ("FAKE_DELEGATIONS", "Microsoft.PowerPlatform/enterprisePolicies\\nMicrosoft.Web/serverFarms", "The delegation of the subnet: expected Microsoft.PowerPlatform/enterprisePolicies"),
                 ("FAKE_NSG", "", "The network security group of the subnet: expected nsg-meternaut-powerplatform, read nothing."),
                 ("FAKE_NSG", f"{SCOPE}/providers/Microsoft.Network/networkSecurityGroups/nsg-another", "read nsg-another."),
                 ("FAKE_OUTBOUND", "True", "The default outbound access of the subnet: expected false, read true."),
                 ("FAKE_PREFIX", "10.99.0.96/29", "The subnet is smaller than a /28"), ("FAKE_PREFIX", "", "The subnet is smaller than a /28 or has no address range that could be read"),
                 ("FAKE_KIND", "Other", "The kind of the enterprise policy ep-meternaut-netinjection: expected NetworkInjection, read Other."),
                 ("FAKE_LOCATION", "swedencentral", "The location of the enterprise policy: expected sweden, read swedencentral."),
                 ("FAKE_NETWORKS", "2", "The number of virtual networks of the enterprise policy: expected 1, read 2."),
                 ("FAKE_POLICY_NETWORK", f"{SCOPE}/providers/Microsoft.Network/virtualNetworks/vnet-another", "The virtual network of the enterprise policy: expected vnet-meternaut, read vnet-another."),
                 ("FAKE_POLICY_SUBNET", "snet-another", "The subnet of the enterprise policy: expected snet-powerplatform, read snet-another."),
                 ("FAKE_SYSTEM_ID_LENGTH", "0", "The enterprise policy has no system id yet"))
        for variable, value, words in cases:
            with self.subTest(variable=variable, value=value):
                done, _, _ = self.go(**{variable: value})
                self.assertEqual(done.returncode, 1, said(done))
                self.assertIn(words, said(done))
                self.assertIn("Nothing is repaired from here", said(done))

    def test_a_policy_with_no_system_id_at_all_is_a_read_that_fails_and_says_so(self):
        done, _, _ = self.go(FAKE_SYSTEM_ID_LENGTH="FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertIn("could not be read", said(done))

    def test_a_subnet_without_a_route_table_is_said_and_is_not_a_failure_because_the_wait_before_this_step_dealt_with_it(self):
        done, _, _ = self.go(FAKE_TABLE="")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("The subnet carries no route table", done.stdout)

    def test_a_subnet_that_does_not_report_its_default_outbound_access_is_said_and_only_an_explicit_true_fails(self):
        done, _, _ = self.go(FAKE_OUTBOUND="")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("The subnet does not report its default outbound access (the template sets it to false).", done.stdout)
        done, _, _ = self.go(FAKE_OUTBOUND="false")
        self.assertEqual(done.returncode, 0, said(done))

    def test_the_geography_is_compared_in_lower_case_and_a_larger_range_is_enough(self):
        done, _, _ = self.go(FAKE_LOCATION="Sweden", FAKE_PREFIX="10.99.0.64/26")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("The subnet is a /26.", done.stdout)


REAL_PYTHON = '#!/bin/bash\nexec "' + Path(sys.executable).as_posix() + '" "$@"\n'


@SKIP_BASH
class TheHandStepsArePrintedWithPlaceholdersOnly(unittest.TestCase):
    def test_the_tool_prints_its_steps_with_the_resource_group_and_nothing_else_of_the_estate_and_to_the_log_and_the_summary(self):
        done, lines, _ = run(HAND_STEPS, {"python3": REAL_PYTHON}, ENV_RESOURCE_GROUP="rg-example")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("### The steps that a person does by hand for the Teams cards", done.stdout)
        self.assertIn("The steps that a person does by hand, in order (docs/proposals/19-teams-cards-through-power-automate.md).", done.stdout)
        for placeholder in ("<subscription id>", "<storage account>", "<environment name>", "--resource-group rg-example", "python tools/powerplatform.py create-environment", "python tools/powerplatform.py link"):
            self.assertIn(placeholder, done.stdout, placeholder)
        self.assertFalse(GUID.search(done.stdout), "no identifier is printed: the log of a public repository is public")
        self.assertNotIn(SUBSCRIPTION, done.stdout)
        script = code_of(HAND_STEPS)
        self.assertIn('python3 tools/powerplatform.py steps --resource-group "$ENV_RESOURCE_GROUP"', script)
        self.assertIn('tee -a "$GITHUB_STEP_SUMMARY"', script)
        for word in ("--subscription", "--storage-account", "--person", "--environment"):
            self.assertNotIn(word, script, f"{word}: the tool is given the resource group, which is plain configuration, and nothing else")

    def test_steps_is_the_one_command_of_the_tool_that_runs_in_a_pipeline(self):
        done = subprocess.run([sys.executable, "tools/powerplatform.py", "status"], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "GITHUB_ACTIONS": "true"})
        self.assertNotEqual(done.returncode, 0, "every other command is refused in a pipeline")
        done = subprocess.run([sys.executable, "tools/powerplatform.py", "steps"], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "GITHUB_ACTIONS": "true"})
        self.assertEqual(done.returncode, 0, done.stderr)


@SKIP_BASH
class TheSummaryAndTheDocumentsSayWhatIsTrue(unittest.TestCase):
    def summary(self, status):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            summary.write_text("", encoding="utf-8")
            script = Path(tmp) / "step.sh"
            script.write_text(ws.step_script("What was done"), encoding="utf-8", newline="\n")
            env = {**os.environ, "ACTION": "powerplatform", "JOB_STATUS": status, "ENV_RESOURCE_GROUP": GROUP, "GITHUB_STEP_SUMMARY": summary.as_posix()}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stderr, "", "a backtick that is not escaped inside the quotes runs a command in bash")
            return summary.read_text(encoding="utf-8")

    def test_a_run_that_finished_says_what_is_in_azure_that_nothing_is_linked_and_that_the_steps_are_above(self):
        text = self.summary("success")
        for words in ("### Hub: powerplatform, success", f"in resource group `{GROUP}` and was read back from Azure", "the subnet `snet-powerplatform` is Succeeded, delegated to Microsoft.PowerPlatform/enterprisePolicies and to nothing else",
                      "the enterprise policy `ep-meternaut-netinjection` is of kind NetworkInjection, in the Power Platform geography Sweden", "Each was made only when it was not there",
                      "No role, private endpoint, private DNS object, link or peering was made, and no environment is linked.", "The steps that a person does by hand are above, with placeholders, because this log is public",
                      "The queue `teams-cards` is made by `cases`.", "Nothing was run in Power Platform or in Teams."):
            self.assertIn(words, text, words)
        self.assertFalse(GUID.search(text))

    def test_a_run_that_did_not_finish_says_what_may_exist_where_each_stop_means_and_that_running_it_again_is_safe(self):
        text = self.summary("failure")
        for words in ("**The run did not finish.**", "Part of the Azure side of the Teams cards may exist now", "the subnet `snet-powerplatform` with its network security group, and the enterprise policy `ep-meternaut-netinjection`",
                      "the resource provider Microsoft.PowerPlatform (a person who may registers it once", "the virtual network (run `model-side`)", "which the builder does not invent: the owner decides what else will do",
                      "a policy that an environment is linked to cannot be written again", "no environment is to be linked before the table is on the subnet", "nothing is repaired from here",
                      "Running `powerplatform` again is safe."):
            self.assertIn(words, text, words)

    def test_bootstrap_has_the_section_with_the_four_hand_steps_the_order_and_the_way_back(self):
        bootstrap = read("environment/BOOTSTRAP.md")
        section = bootstrap.split("## Added on 2026-11-11 for the Teams cards (built, not deployed)\n", 1)[1].split("\n## After it", 1)[0]
        for words in ("| T1 |", "| T2 |", "| T3 |", "| T4 |", "az provider register --subscription $devSub --namespace Microsoft.PowerPlatform", "Storage Queue Data Message Processor", "--role 'Reader'",
                      "ep-meternaut-netinjection", "**The order.**", "`cases` runs once more", "**Going back.**", "no action deletes what `powerplatform` makes", "rule 19", "rule 27", "refuses every command but `steps` in a pipeline",
                      "The action `what-if` does not list this template"):
            self.assertIn(words, section, words)
        self.assertLess(section.index("T1"), section.index("**The order.**"))
        self.assertIn("(#added-on-2026-11-11-for-the-teams-cards-built-not-deployed)", bootstrap)
        self.assertNotIn("TEAMS_BOT_ENABLED", bootstrap)

    def test_the_changelog_has_one_bullet_in_the_top_entry_after_the_one_that_removed_the_bot_and_it_says_what_is_not_proved(self):
        changelog = read("CHANGELOG.md")
        top = changelog.split("\n## ", 2)[1]
        self.assertTrue(top.startswith("The repository is public"), top[:80])
        bullets = [b for b in re.split(r"(?m)^- ", top) if b.startswith("**The Azure and Power Platform side of those cards, and the Hub action `powerplatform`, built the same day.**")]
        self.assertEqual(len(bullets), 1)
        bullet = bullets[0]
        for words in ("environment/powerplatform/main.bicep", "the enterprise policy `ep-meternaut-netinjection`", "`TEAMS_CARDS_QUEUE`", "it takes no new secret or variable", "waits up to 20 minutes for the landing zone's route table",
                      "prints the hand steps with placeholders only", "**Also fixed:** the preview of the AI security's templates in `what-if` failed", "no role was given", "**Not proved:**", "the solution was never imported"):
            self.assertIn(words, bullet, words)
        self.assertLess(top.index("the Teams bot was removed, on the owner's order"), top.index("The Azure and Power Platform side of those cards"))

    def test_the_proposals_link_each_other_and_the_readme_has_one_row_for_this_one(self):
        thirteen = read("docs/proposals/13-teams-and-outlook.md")
        self.assertEqual(thirteen.count("](19-teams-cards-through-power-automate.md)"), 3)
        self.assertNotIn("`19-teams-cards-through-power-automate.md`", thirteen)
        nineteen = read("docs/proposals/19-teams-cards-through-power-automate.md")
        for words in ("Start the action `powerplatform`.", "the virtual network is there (`model-side`)", "waits for the landing zone's route table to appear on the subnet (20 minutes at most)", "signs in again and reads both back",
                      "The Hub action `powerplatform` ends by printing them with placeholders only", "gives each message a time to live of 24 hours"):
            self.assertIn(words, nineteen, words)
        readme = read("README.md")
        self.assertEqual(readme.count("(docs/proposals/19-teams-cards-through-power-automate.md)"), 1)

    def test_the_rule_about_the_tools_that_refuse_a_pipeline_names_the_tool_of_power_platform(self):
        rule = [line for line in read("AGENTS.md").splitlines() if line.startswith("24. ")][0]
        self.assertIn("[`tools/powerplatform.py`](tools/powerplatform.py)", rule)
        self.assertIn("its command `steps`, which only prints text, is the one that a pipeline may run", rule)
        self.assertIn("deletes nothing", rule)


AISEC_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*"Microsoft.OperationalInsights/workspaces"*) printf '%s' "$FAKE_WORKSPACE" ;;
  *"resource list"*"Microsoft.CognitiveServices/accounts"*) printf '%s' "$FAKE_FOUNDRY" ;;
  *"role assignment list"*) if [ "$FAKE_ROLES" = "FAIL" ]; then echo "ERROR: (AuthorizationFailed) denied" >&2; exit 1; fi; printf '%b' "$FAKE_ROLES" ;;
  *"rest --method get"*) ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
AISEC_PY = """#!/bin/bash
echo "python3 $*" >> "$FAKE_LOG"
"""


@SKIP_BASH
class ThePreviewOfThePolicySkipsItselfWhenTheDeployIdentityCannotWriteOne(unittest.TestCase):
    ROLE_DEFINITIONS = f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions"

    def go(self, **changes):
        env = {"DEPLOYER_ID": DEPLOYER, "FOUNDRY_ACCOUNT": "aif-meternaut-agents-abc", "GATEWAY_NAME": "aigw-meternaut-abc", "INSIGHTS_NAME": "appi-meternaut", "ACTION": "what-if",
               "FAKE_WORKSPACE": "log-meternaut", "FAKE_FOUNDRY": "aif-meternaut-agents-abc", "FAKE_ROLES": f"{SCOPE}\\t{self.ROLE_DEFINITIONS}/{RESOURCE_POLICY_CONTRIBUTOR}\\n", **changes}
        return run(AISEC_PREVIEW, {"az": AISEC_AZ, "python3": AISEC_PY}, **env)

    def governance_previews(self, lines):
        return [line for line in lines if "az-deploy.py what-if" in line and "environment/governance/main.bicep" in line]

    SKIPPED = "The policy preview is skipped: the deploy identity holds no role that can write a policy assignment (Resource Policy Contributor, or Owner)"

    def test_a_deploy_identity_that_holds_the_role_gets_the_preview_as_before_and_the_look_is_one_read_of_its_roles_on_the_group(self):
        done, lines, _ = self.go()
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(len(self.governance_previews(lines)), 1)
        self.assertNotIn("skipped", said(done))
        role_call = next(line for line in lines if "role assignment list" in line)
        self.assertIn(f"--assignee-object-id {DEPLOYER}", role_call)
        self.assertIn(f"--scope {SCOPE}", role_call)
        self.assertIn("--include-inherited", role_call)
        self.assertIn("::group::The telemetry exporter of the AI Gateway", done.stdout, "the rest of the preview runs")

    def test_owner_or_resource_policy_contributor_at_the_group_or_above_it_is_enough_and_contributor_alone_is_not(self):
        sub = f"/subscriptions/{SUBSCRIPTION}"
        for scope, role, ok in ((SCOPE, RESOURCE_POLICY_CONTRIBUTOR, True), (SCOPE, OWNER_ROLE, True), (sub, OWNER_ROLE, True), (sub, RESOURCE_POLICY_CONTRIBUTOR, True),
                                ("/providers/Microsoft.Management/managementGroups/mg-of-the-estate", OWNER_ROLE, True), ("/", OWNER_ROLE, True),
                                (SCOPE, CONTRIBUTOR_ROLE, False), (SCOPE + "/providers/Microsoft.Storage/storageAccounts/x", OWNER_ROLE, False), ("/subscriptions/another", OWNER_ROLE, False), (SCOPE + "x", OWNER_ROLE, False)):
            with self.subTest(scope=scope, role=role):
                done, lines, _ = self.go(FAKE_ROLES=f"{scope}\\t{self.ROLE_DEFINITIONS}/{role}\\n")
                self.assertEqual(done.returncode, 0, said(done))
                self.assertEqual(len(self.governance_previews(lines)), 1 if ok else 0)
                self.assertEqual(self.SKIPPED in done.stdout, not ok)

    def test_without_the_right_the_policy_preview_is_skipped_with_one_plain_line_the_rest_of_the_what_if_runs_and_nothing_is_an_error(self):
        done, lines, _ = self.go(FAKE_ROLES=f"{SCOPE}\\t{self.ROLE_DEFINITIONS}/{CONTRIBUTOR_ROLE}\\n")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertEqual(self.governance_previews(lines), [])
        self.assertEqual(done.stdout.count(self.SKIPPED), 1, "one line")
        line = next(line for line in done.stdout.splitlines() if self.SKIPPED in line)
        for words in ("and Azure refuses the preview of a template that writes one.", "The action governance stops for the same reason until a person gives the role once (environment/BOOTSTRAP.md, the section on the AI security, step G1)."):
            self.assertIn(words, line)
        self.assertNotIn("::error::", said(done))
        self.assertNotIn("::warning::", said(done))
        self.assertIn("::group::The telemetry exporter of the AI Gateway", done.stdout)
        self.assertIn("The telemetry exporter cannot be previewed yet", done.stdout, "the second group ran: the gateway is not there in this stand-in")
        self.assertEqual(done.stdout.count("::group::"), done.stdout.count("::endgroup::"))

    def test_a_right_that_cannot_be_looked_at_skips_the_preview_with_a_warning_and_the_reason_and_the_step_still_passes(self):
        for changes, reason in (({"FAKE_ROLES": "FAIL"}, "its role assignments could not be read: ERROR: (AuthorizationFailed) denied"), ({"DEPLOYER_ID": ""}, "the object id of the deploy identity was not read from its token"),
                                ({"DEPLOYER_ID": "not-an-id"}, "the object id of the deploy identity was not read from its token")):
            with self.subTest(reason=reason):
                done, lines, _ = self.go(**changes)
                self.assertEqual(done.returncode, 0, said(done))
                self.assertEqual(self.governance_previews(lines), [])
                self.assertIn(f"::warning::The policy preview is skipped: the right of the deploy identity to write a policy assignment could not be looked at ({reason}).", said(done))
                self.assertNotIn("::error::", said(done))
                self.assertIn("::group::The telemetry exporter of the AI Gateway", done.stdout)

    def test_a_workspace_or_a_foundry_resource_that_is_not_there_is_said_first_and_the_roles_are_not_even_listed(self):
        for changes in ({"FAKE_WORKSPACE": ""}, {"FAKE_FOUNDRY": "None"}):
            with self.subTest(changes=changes):
                done, lines, _ = self.go(**changes)
                self.assertEqual(done.returncode, 0, said(done))
                self.assertIn("The AI security cannot be previewed yet: it reads the base's workspace and the Foundry resource of the agents, and the actions base and foundry make them.", done.stdout)
                self.assertFalse([line for line in lines if "role assignment" in line])
                self.assertEqual(self.governance_previews(lines), [])

    def test_the_step_only_reads_and_gives_no_role(self):
        done, lines, _ = self.go(FAKE_ROLES="")
        for call in lines:
            for word in (" put ", " post ", " patch ", " delete ", " create ", "--yes"):
                self.assertNotIn(word, call + " ", call)
        script = code_of(AISEC_PREVIEW)
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        self.assertNotIn("az role assignment create", script)

    def test_the_step_takes_the_object_id_from_the_step_that_reads_it_and_prints_it_nowhere(self):
        block = step(AISEC_PREVIEW)
        self.assertIn("DEPLOYER_ID: ${{ steps.me.outputs.oid }}", block)
        for line in code_of(AISEC_PREVIEW).splitlines():
            if re.match(r"\s*(echo|printf)\b", line):
                self.assertNotIn("DEPLOYER_ID", line, line)
        done, _, _ = self.go(FAKE_ROLES="FAIL")
        self.assertNotIn(DEPLOYER, said(done))


if __name__ == "__main__":
    unittest.main()
