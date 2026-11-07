"""The actions aigateway and aigateway-check of the deploy workflow (.github/workflows/deploy-hub.yml): what runs for each, in what order, what each step reads and says, and what it refuses.

The shell of each step is run with bash against stand-ins for the commands that it calls first on the PATH: the Azure CLI, python3 (which the steps call for the tools) and sleep. No test calls Azure."""
import json
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
CHECKS = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8").replace("\r\n", "\n")

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
GATEWAY = "aigw-meternaut-0123abcd"
ACCOUNT = "aif-meternaut-agents-0123abcd"
DEPLOYER = "7f3e1d52-0000-4000-8000-0000000000aa"
OPERATOR_CLIENT = "99999999-8888-7777-6666-555555555555"
FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
MODELS_USER = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
ADMINISTRATOR = "f58310d9-a9f6-439a-9e8d-f62e7b41a168"
OLD_ROLES = ("5e0bd9bd-7b93-4f28-af87-19fc36ad61bd", "2b629674-e913-4c01-ae53-ef4638d8f975")
GROUP_SCOPE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"

READY = "The network, the Foundry resource of the agents and the Operator are there, the service is offered here, and the deploy identity may give the roles of the AI Gateway"
DEPLOY = "Deploy the AI Gateway, its subnet, its models and aliases, and its roles"
WAIT = "Wait until the landing zone has put its route table on the AI Gateway's subnet"
LOGIN = "Sign in to Azure again for the limits, the built-in key and the read-back of the AI Gateway, because the first sign-in's credential lasts five minutes"
POLICIES = "Apply the gateway-wide limits to the AI Gateway"
KEY = "Delete the built-in key of the AI Gateway when the service lets it be deleted"
READ_BACK = "Read the AI Gateway back"
FIND = "Find the Operator, which runs the AI Gateway check from inside the network"
HOST = "Read the host name of the AI Gateway from the service"
CHECK = "Run the AI Gateway check in the Operator"
CLEANUP = "Delete any container group of the AI Gateway check that is left"
APPLY = [READY, DEPLOY, WAIT, LOGIN, POLICIES, KEY, READ_BACK]
CHECKING = [FIND, HOST, CHECK, CLEANUP]


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
    """The whole block of the step with this name."""
    block = re.search(rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", WORKFLOW)
    assert block, name
    return block.group(0)


def script_of(name):
    """The `run:` script of the step, as the runner would write it to a file."""
    run = re.search(r"(?ms)^        run: \|\n(.*)", step(name))
    assert run, name
    return textwrap.dedent(run.group(1))


def code_of(name):
    """The script without its comment lines."""
    return "\n".join(line for line in script_of(name).splitlines() if not line.strip().startswith("#"))


def run_script(name, stand_ins, env, files=None, prelude=""):
    """Run the `run:` script of a step with bash, as the runner does, with stand-ins first on the PATH. Returns the process, the lines that the stand-ins logged, the text that the step added to its output
    file, and the folder that it ran in (the RUNNER_TEMP of the run, which no longer exists)."""
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
        script.write_text(prelude + script_of(name), encoding="utf-8", newline="\n")
        log = tmp / "log.txt"
        log.write_text("", encoding="utf-8")
        (tmp / "out.txt").write_text("", encoding="utf-8")
        full = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": log.as_posix(), "FAKE_DIR": tmp.as_posix(),
                "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(), "GITHUB_STEP_SUMMARY": (tmp / "summary.md").as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env}
        done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=full, cwd=ROOT)
        return done, log.read_text(encoding="utf-8").splitlines(), (tmp / "out.txt").read_text(encoding="utf-8"), tmp.as_posix()


def condition(write, delete):
    """The condition of the deploy identity's right to assign roles, as environment/BOOTSTRAP.md writes it, with the role ids of the two lists."""
    def part(kind, source, ids):
        return (f"((!(ActionMatches{{'Microsoft.Authorization/roleAssignments/{kind}'}})) OR (@{source}[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals "
                f"{{{', '.join(ids)}}} AND @{source}[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {{'ServicePrincipal'}}))")
    return f"{part('write', 'Request', write)} AND {part('delete', 'Resource', delete)}"


def assignment_line(rule=None, scope=GROUP_SCOPE, role=ADMINISTRATOR):
    return f"{scope}\t/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{role}\t{rule if rule else 'None'}\n"


READY_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*"--resource-type Microsoft.CognitiveServices/accounts"*) printf '%s' "$FAKE_FOUNDRY" ;;
  *"resource list"*"--name id-meternaut-operator"*) printf '%s' "$FAKE_OPERATOR" ;;
  *"provider show"*)
    if [ "$FAKE_REGIONS" = "FAIL" ]; then echo "ERROR: (AuthorizationFailed) the client may not read providers" >&2; exit 1; fi
    printf '%s' "$FAKE_REGIONS" ;;
  *"role assignment list"*)
    if [ "$FAKE_ASSIGNMENTS" = "FAIL" ]; then echo "ERROR: (AuthorizationFailed) the client may not read role assignments" >&2; exit 1; fi
    printf '%s' "$FAKE_ASSIGNMENTS" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

GOOD_CONDITION = condition([*OLD_ROLES, FOUNDRY_USER, MODELS_USER], [*OLD_ROLES, FOUNDRY_USER, MODELS_USER])


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheEstateIsReadyBeforeAnythingIsMade(unittest.TestCase):
    """The first step of the action aigateway only reads, and stops with a clear message, before anything is changed, for each thing that the gateway builds on and for the condition of the deploy identity."""

    def ready(self, **changes):
        env = {"NETWORK_EXISTS": "true", "FOUNDRY_ACCOUNT": ACCOUNT, "DEPLOYER_ID": DEPLOYER, "ENV_RESOURCE_GROUP": GROUP, "ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_LOCATION": "swedencentral",
               "FAKE_FOUNDRY": ACCOUNT, "FAKE_OPERATOR": "id-meternaut-operator", "FAKE_REGIONS": "East US 2\nSweden Central\n", "FAKE_ASSIGNMENTS": assignment_line(GOOD_CONDITION)}
        files = {"aigateway.parameters.json": "{}"}
        if changes.pop("no_file", False):
            files = {}
        return run_script(READY, {"az": READY_AZ}, {**env, **changes}, files)

    def assertStops(self, done, lines, message, calls=None):
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        line = next((l for l in done.stdout.splitlines() if f"::error::{message}" in l), None)
        self.assertIsNotNone(line, f"{message!r} is not among the errors: {done.stdout}")
        self.assertIn("Nothing was changed.", line)
        if calls is not None:
            self.assertEqual(len(lines), calls, lines)

    def test_a_good_estate_passes_and_only_reads(self):
        done, lines, _, _ = self.ready()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for line in (f"The virtual network, the Foundry resource {ACCOUNT} and the Operator's identity are there.", "The resource type aigateways is offered in swedencentral.",
                     "The condition of the deploy identity's right to assign roles lists Foundry User and AI Gateway Models User, for a write and for a delete."):
            self.assertIn(line, done.stdout)
        self.assertTrue(all(re.match(r"az (resource list|provider show|role assignment list) ", line) for line in lines), "three kinds of read and nothing else")
        self.assertEqual({re.match(r"az (resource list|provider show|role assignment list) ", line).group(1) for line in lines}, {"resource list", "provider show", "role assignment list"})
        for word in (" create", " delete", " update", "--method", " register"):
            self.assertFalse(any(word in line for line in lines), word)
        self.assertEqual(done.stderr, "")

    def test_no_free_range_for_the_subnet_stops_before_azure_is_asked(self):
        done, lines, _, _ = self.ready(no_file=True)
        self.assertStops(done, lines, "The virtual network has no free range for the gateway's subnet: it needs a /26, or a /27 at the least, that none of the other subnets uses.", calls=0)

    def test_a_missing_network_foundry_resource_or_operator_says_which_action_makes_it(self):
        done, lines, _, _ = self.ready(NETWORK_EXISTS="false")
        self.assertStops(done, lines, "The virtual network is not there. Run model-side first: the gateway's subnet goes into it.", calls=0)
        for found in ("", "None"):
            done, lines, _, _ = self.ready(FAKE_FOUNDRY=found)
            self.assertStops(done, lines, f"The Foundry resource {ACCOUNT} of the agents is not in {GROUP}. Run foundry first (the order is foundry and cases, then operator, then aigateway).", calls=1)
            done, lines, _, _ = self.ready(FAKE_OPERATOR=found)
            self.assertStops(done, lines, "The identity id-meternaut-operator is not there. Run operator first: it gets AI Gateway Models User on the gateway and runs the check.", calls=2)

    def test_the_service_has_to_be_offered_in_the_region_whatever_the_case_and_the_spaces_of_the_names(self):
        for location, regions in (("swedencentral", "Sweden Central"), ("swedencentral", "East US 2\nSWEDEN CENTRAL"), ("eastus2", "East US 2")):
            done, _, _, _ = self.ready(ENV_LOCATION=location, FAKE_REGIONS=regions + "\n")
            self.assertEqual(done.returncode, 0, (location, regions, done.stdout))
            self.assertIn(f"The resource type aigateways is offered in {location}.", done.stdout)
        done, lines, _, _ = self.ready(ENV_LOCATION="westeurope", FAKE_REGIONS="East US 2\nSweden Central\n")
        self.assertStops(done, lines, "The AI Gateway is not offered in westeurope; the provider lists: East US 2,Sweden Central. The preview is offered in a few regions only.")
        done, lines, _, _ = self.ready(FAKE_REGIONS="")
        self.assertStops(done, lines, "The resource provider Microsoft.ApiManagement does not list the resource type aigateways in this subscription.")

    def test_a_list_of_regions_that_cannot_be_read_is_a_warning_and_the_run_goes_on_because_the_deploy_says_it_too(self):
        done, _, _, _ = self.ready(FAKE_REGIONS="FAIL")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("::warning::The regions of the AI Gateway could not be read (ERROR: (AuthorizationFailed) the client may not read providers). If the service is not offered in swedencentral, the deploy says so.", done.stdout)
        self.assertIn("lists Foundry User and AI Gateway Models User", done.stdout, "the condition is looked at all the same")

    def test_the_condition_has_to_list_both_roles_in_both_of_its_lists_and_the_message_says_which_role_and_where_the_hand_step_is(self):
        for what, rule, role in (("Models User is in no list", condition([*OLD_ROLES, FOUNDRY_USER], [*OLD_ROLES, FOUNDRY_USER]), ("AI Gateway Models User", MODELS_USER)),
                                 ("Models User is in the list of the write alone", condition([*OLD_ROLES, FOUNDRY_USER, MODELS_USER], [*OLD_ROLES, FOUNDRY_USER]), ("AI Gateway Models User", MODELS_USER)),
                                 ("Models User is in the list of the delete alone", condition([*OLD_ROLES, FOUNDRY_USER], [*OLD_ROLES, FOUNDRY_USER, MODELS_USER]), ("AI Gateway Models User", MODELS_USER)),
                                 ("Foundry User is missing", condition([*OLD_ROLES, MODELS_USER], [*OLD_ROLES, MODELS_USER]), ("Foundry User", FOUNDRY_USER)),
                                 ("a condition with no list at all", "(true)", ("Foundry User", FOUNDRY_USER))):
            with self.subTest(what):
                done, lines, _, _ = self.ready(FAKE_ASSIGNMENTS=assignment_line(rule))
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn(f"::error::The condition of the deploy identity's right to assign roles does not list {role[0]} ({role[1]}) for a write and for a delete. The template of the AI Gateway gives that role, "
                              "and Azure would refuse it after the gateway was made. A person adds the id once, with their own sign-in, on the owner's written word (environment/BOOTSTRAP.md, the section on the AI Gateway). "
                              "Nothing was changed.", done.stdout)
        done, _, _, _ = self.ready(FAKE_ASSIGNMENTS=assignment_line(condition([MODELS_USER.upper(), FOUNDRY_USER.upper()], [MODELS_USER, FOUNDRY_USER])))
        self.assertEqual(done.returncode, 0, "the ids are compared whatever their case: " + done.stdout)

    def test_no_condition_means_any_role_may_be_given_and_no_assignment_on_the_group_is_an_error(self):
        done, _, _, _ = self.ready(FAKE_ASSIGNMENTS=assignment_line(None))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("The deploy identity's right to assign roles has no condition: it may give any role.", done.stdout)
        for what, listed in (("another role only", assignment_line(None, role="b24988ac-6180-42a0-ab88-20f7382dd24c")), ("another scope", assignment_line(GOOD_CONDITION, scope=GROUP_SCOPE + "/providers/Microsoft.EventHub/namespaces/x")),
                             ("none", "")):
            done, _, _, _ = self.ready(FAKE_ASSIGNMENTS=listed)
            self.assertEqual(done.returncode, 1, what)
            self.assertIn("::error::The deploy identity holds no assignment of Role Based Access Control Administrator on the group, so the roles of the AI Gateway cannot be given. Nothing was changed.", done.stdout, what)

    def test_an_assignment_that_cannot_be_read_and_an_object_id_that_was_not_read_stop_the_run(self):
        done, _, _, _ = self.ready(FAKE_ASSIGNMENTS="FAIL")
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The role assignments of the deploy identity on the group could not be read: ERROR: (AuthorizationFailed) the client may not read role assignments. Nothing was changed.", done.stdout)
        for given in ("", "None", "not-an-object-id"):
            done, lines, _, _ = self.ready(DEPLOYER_ID=given)
            self.assertEqual(done.returncode, 1, given)
            self.assertIn("::error::The object id of the deploy identity was not read from its token, so its right to assign roles cannot be looked at. Nothing was changed.", done.stdout)
            self.assertFalse(any("role assignment list" in line for line in lines))

    def test_the_assignments_are_listed_for_the_deploy_identity_on_the_group_alone_and_the_scope_is_compared_whatever_its_case(self):
        done, lines, _, _ = self.ready(DEPLOYER_ID=DEPLOYER.upper(), FAKE_ASSIGNMENTS=assignment_line(GOOD_CONDITION, scope=GROUP_SCOPE.upper()))
        self.assertEqual(done.returncode, 0, done.stdout)
        (call,) = [line for line in lines if "role assignment list" in line]
        self.assertIn(f"--assignee-object-id {DEPLOYER} --scope {GROUP_SCOPE} ", call, "the id is lower-cased, and the scope is the group")
        self.assertIn("--fill-principal-name false --fill-role-definition-name false", call)


def python_stand_in(print_value=None):
    body = '#!/bin/bash\n{ echo "python3"; printf \'arg:%s\\n\' "$@"; } >> "$FAKE_LOG"\n'
    if print_value:
        body += f'printf \'%s\' "{print_value}"\n'
    body += 'exit "${FAKE_EXIT:-0}"\n'
    return body


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheGatewayIsDeployedAndThenLookedAfter(unittest.TestCase):
    ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "GITHUB_RUN_ID": "12345", "GATEWAY_NAME": GATEWAY, "EXPECTED_NAME": GATEWAY}

    def arguments(self, lines):
        return [line[len("arg:"):] for line in lines if line.startswith("arg:")]

    def test_the_deploy_makes_the_template_with_the_parameter_file_and_asks_for_the_name_and_compares_it(self):
        done, lines, _, tmp = run_script(DEPLOY, {"python3": python_stand_in(GATEWAY)}, self.ENV)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.arguments(lines), ["tools/az-deploy.py", "create", "--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--template", "environment/aigateway/main.bicep",
                                                 "--parameters", f"{tmp}/aigateway.parameters.json", "--name", "aigateway-12345", "--output", "gatewayName"])
        self.assertIn(f"The AI Gateway {GATEWAY} is in resource group {GROUP}.", done.stdout)
        done, lines, _, _ = run_script(DEPLOY, {"python3": python_stand_in("aigw-another-name")}, self.ENV)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"::error::The deployment made the AI Gateway aigw-another-name, not {GATEWAY}, which is the name that the later steps read back. Nothing else was changed.", done.stdout)

    def test_the_wait_takes_the_endpoint_subnet_as_the_yardstick_and_says_which_table_the_landing_zone_added(self):
        az = """#!/bin/bash
case "$*" in
  *"/subnets/snet-pe?"*) printf '%s' "$FAKE_PE_TABLE" ;;
  *"/subnets/snet-aigw?"*)
    n=$(cat "$FAKE_DIR/count" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$FAKE_DIR/count"
    echo "read snet-aigw $n" >> "$FAKE_LOG"
    if [ "$n" -ge "$FAKE_AFTER" ]; then printf '%s' "$FAKE_AIGW_TABLE"; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
        prelude = 'sleep() { echo "sleep $*" >> "$FAKE_LOG"; }\n'
        table = f"{GROUP_SCOPE}/providers/Microsoft.Network/routeTables/rt-landing-zone"

        def wait(**changes):
            return run_script(WAIT, {"az": az}, {**self.ENV, "FAKE_PE_TABLE": table, "FAKE_AIGW_TABLE": table, "FAKE_AFTER": "1", **changes}, prelude=prelude)

        done, lines, _, _ = wait()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("The landing zone added the route table rt-landing-zone to the subnet snet-aigw.", done.stdout)
        self.assertEqual(lines, ["read snet-aigw 1"])
        done, lines, _, _ = wait(FAKE_AFTER="3")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("snet-aigw carries no route table yet (check 2 of 40).", done.stdout)
        self.assertEqual(lines, ["read snet-aigw 1", "sleep 30", "read snet-aigw 2", "sleep 30", "read snet-aigw 3"])
        for none in ("", "None"):
            done, lines, _, _ = wait(FAKE_PE_TABLE=none)
            self.assertEqual(done.returncode, 0, done.stdout)
            self.assertIn("The endpoint subnet carries no route table, so the landing zone puts none on this network: there is nothing to wait for.", done.stdout)
            self.assertEqual(lines, [], "the gateway's subnet is not even read")

    def test_a_table_that_does_not_come_in_twenty_minutes_fails_the_run_and_says_that_nothing_else_was_changed(self):
        az = """#!/bin/bash
case "$*" in
  *"/subnets/snet-pe?"*) printf '%s' "/x/routeTables/rt" ;;
  *"/subnets/snet-aigw?"*) echo "read" >> "$FAKE_LOG"; printf 'None' ;;
esac
"""
        done, lines, _, _ = run_script(WAIT, {"az": az}, self.ENV, prelude='sleep() { echo "sleep $*" >> "$FAKE_LOG"; }\n')
        self.assertEqual(done.returncode, 1)
        self.assertEqual((lines.count("read"), lines.count("sleep 30")), (40, 39), "40 checks half a minute apart: twenty minutes")
        self.assertIn("::error::The landing zone's network manager has put a route table on snet-pe and has not put one on snet-aigw in 20 minutes. The gateway may have no way out and no DNS. "
                      "Nothing else was changed: run aigateway again later, which repeats only what is missing.", done.stdout)

    def test_the_limits_the_key_and_the_read_back_are_the_tools_called_with_the_names_the_builder_gives_and_nothing_else_is_done(self):
        env = {**self.ENV, "FOUNDRY_ACCOUNT": ACCOUNT, "VNET_NAME": "vnet-meternaut", "SUBNET_NAME": "snet-aigw", "OPERATOR_IDENTITY": "id-meternaut-operator"}
        done, lines, _, tmp = run_script(POLICIES, {"python3": python_stand_in()}, env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.arguments(lines), ["tools/aigateway-prep.py", "policies", "--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--gateway", GATEWAY,
                                                 "--file", f"{tmp}/aigateway-policies.json", "--summary", f"{tmp}/summary.md"])
        done, lines, _, tmp = run_script(KEY, {"python3": python_stand_in()}, env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.arguments(lines), ["tools/aigateway-prep.py", "remove-key", "--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--gateway", GATEWAY, "--summary", f"{tmp}/summary.md"])
        done, lines, _, tmp = run_script(READ_BACK, {"python3": python_stand_in()}, env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.arguments(lines), ["tools/aigateway-prep.py", "read-back", "--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--gateway", GATEWAY, "--vnet", "vnet-meternaut",
                                                 "--subnet", "snet-aigw", "--foundry-account", ACCOUNT, "--operator-identity", "id-meternaut-operator", "--models", "environment/models.json",
                                                 "--policies", f"{tmp}/aigateway-policies.json", "--summary", f"{tmp}/summary.md"])

    def test_a_tool_that_fails_fails_its_step_and_so_the_run(self):
        env = {**self.ENV, "FOUNDRY_ACCOUNT": ACCOUNT, "VNET_NAME": "v", "SUBNET_NAME": "s", "OPERATOR_IDENTITY": "o", "FAKE_EXIT": "1"}
        for name in (POLICIES, KEY, READ_BACK):
            done, _, _, _ = run_script(name, {"python3": python_stand_in()}, env)
            self.assertEqual(done.returncode, 1, name)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheCheckRunsInTheOperator(unittest.TestCase):
    ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "GITHUB_RUN_ID": "12345", "ACTION": "aigateway-check", "GATEWAY_NAME": GATEWAY}
    IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
    SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"
    HOST = f"{GATEWAY}.swedencentral.ai.gateway.azure.com"

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

    def find(self, **changes):
        env = {**self.ENV, "FAKE_IDENTITY": self.IDENTITY, "FAKE_CLIENT": OPERATOR_CLIENT, "FAKE_SUBNET": "ok", **changes}
        return run_script(FIND, {"az": self.FIND_AZ}, env)

    def test_the_operator_is_found_by_its_name_and_the_outputs_are_the_ones_that_the_check_reads(self):
        done, lines, out, _ = self.find()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("The Operator's identity and its subnet are there.", done.stdout)
        self.assertEqual(out.splitlines(), [f"identity_id={self.IDENTITY}", f"client_id={OPERATOR_CLIENT}", f"subnet_id={self.SUBNET}"])
        self.assertTrue(all(line.startswith("az resource list") or "--method get" in line for line in lines), "only reads")

    def test_an_operator_that_is_not_there_says_that_operator_is_run_first_and_what_the_order_is(self):
        done, _, out, _ = self.find(FAKE_IDENTITY="", FAKE_CLIENT="")
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The identity id-meternaut-operator is not there. The action aigateway-check runs its check in the Operator, so run operator first (the order is foundry and cases, operator, aigateway). "
                      "Nothing was changed.", done.stdout)
        self.assertEqual(out, "")
        done, _, _, _ = self.find(FAKE_SUBNET="absent")
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The subnet snet-ops is not there. The action aigateway-check runs its check in the Operator, so run operator first (the order is foundry and cases, operator, aigateway). "
                      "Nothing was changed.", done.stdout)
        done, _, _, _ = self.find(FAKE_SUBNET="ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later.")
        self.assertEqual(done.returncode, 1, "a message that holds the digits 404 inside an id is not 'not found'")
        self.assertIn("::error::The subnet snet-ops could not be read: ERROR: (TooManyRequests)", done.stdout)

    def host(self, answer, fail=False):
        az = f"""#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
if [ "$FAKE_FAIL" = "yes" ]; then echo "$FAKE_ANSWER" >&2; exit 1; fi
printf '%s' "$FAKE_ANSWER"
"""
        return run_script(HOST, {"az": az}, {**self.ENV, "FAKE_ANSWER": answer, "FAKE_FAIL": "yes" if fail else "no"})

    def test_the_host_name_is_read_from_the_service_once_and_checked_to_be_under_the_services_domain(self):
        done, lines, out, _ = self.host(self.HOST)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(out, f"host={self.HOST}\n")
        self.assertIn(f"The service reports the host name of the gateway {GATEWAY}.", done.stdout)
        self.assertNotIn(self.HOST, done.stdout, "the host name is an output and is not printed")
        (call,) = lines
        self.assertEqual(call, f"az rest --method get --url https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ApiManagement/aigateways/{GATEWAY}"
                               "?api-version=2025-09-01-preview --query properties.frontend.defaultHostname --output tsv")
        for bad in ("", "None", "evil.example.com", f"{GATEWAY}.ai.gateway.azure.com.evil.example.com", "Aigw.ai.gateway.azure.com", ".ai.gateway.azure.com", f"{GATEWAY} .ai.gateway.azure.com",
                    f"https://{self.HOST}", f"{self.HOST}/default"):
            done, _, out, _ = self.host(bad)
            self.assertEqual(done.returncode, 1, bad)
            self.assertIn(f"::error::The service did not report a host name under .ai.gateway.azure.com for the gateway {GATEWAY} (it may be still starting). Nothing was changed.", done.stdout, bad)
            self.assertEqual(out, "", "nothing is handed on that was not accepted")

    def test_a_gateway_that_is_not_there_and_a_read_that_failed_are_told_apart(self):
        done, _, _, _ = self.host("ERROR: (ResourceNotFound) The Resource 'Microsoft.ApiManagement/aigateways/x' was not found.", fail=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"::error::The AI Gateway {GATEWAY} is not there. Run aigateway first (after foundry and operator). Nothing was changed.", done.stdout)
        done, _, _, _ = self.host("ERROR: (InternalServerError) try again later", fail=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"::error::The AI Gateway {GATEWAY} could not be read: ERROR: (InternalServerError) try again later", done.stdout)

    def run_check(self, **changes):
        env = {**self.ENV, "ALIASES": "gpt-6-luna gpt-6.1-sol", "GATEWAY_HOST": self.HOST, "OPERATOR_IDENTITY_ID": self.IDENTITY, "OPERATOR_CLIENT_ID": OPERATOR_CLIENT, "OPERATOR_SUBNET_ID": self.SUBNET,
               "OPERATOR_IMAGE": "mcr.microsoft.com/azure-cli@sha256:" + "0" * 64, "ENV_DNS_SERVERS": "10.20.0.4,10.20.0.5", **changes}
        return run_script(CHECK, {"python3": python_stand_in()}, env)

    def test_the_check_is_started_by_the_tool_with_the_tool_in_the_secret_volume_the_operators_identity_and_one_alias_flag_for_each_alias(self):
        done, lines, _, tmp = self.run_check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        arguments = [line[len("arg:"):] for line in lines if line.startswith("arg:")]
        self.assertEqual(arguments, [
            "tools/operator-run.py", "run", "--resource-group", GROUP, "--name", "op-aigw-12345", "--subnet-id", self.SUBNET, "--identity-id", self.IDENTITY,
            "--image", "mcr.microsoft.com/azure-cli@sha256:" + "0" * 64, "--script", "operator/run-tool.sh", "--secret-file", "aigateway-check.py=tools/aigateway-check.py",
            "--env", "GITHUB_ACTIONS=true", "--env", f"OPERATOR_CLIENT_ID={OPERATOR_CLIENT}", "--env", f"OPERATOR_SUBSCRIPTION={SUBSCRIPTION}", "--env", "TOOL_NAME=aigateway-check",
            "--env", f"TOOL_ARGS=run --host {self.HOST} --alias gpt-6-luna --alias gpt-6.1-sol", "--dns-server", "10.20.0.4", "--dns-server", "10.20.0.5", "--timeout-seconds", "900",
            "--summary", f"{tmp}/summary.md"])

    def test_what_the_container_is_told_is_what_the_script_of_the_container_accepts_and_no_token_goes_in(self):
        done, lines, _, _ = self.run_check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = next(line for line in lines if line.startswith("arg:TOOL_ARGS="))[len("arg:TOOL_ARGS="):]
        self.assertRegex(text, r"^[A-Za-z0-9 ./:_=-]{1,600}$", "the characters and the length that operator/run-tool.sh takes")
        self.assertRegex(text.split(" ")[0], r"^[a-z][a-z-]{0,19}$")
        run_tool = (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")
        self.assertIn("[A-Za-z0-9 ./:_=-]", run_tool)
        joined = "\n".join(lines).lower()
        for word in ("token", "secure-env", "federated", "bearer", "password"):
            self.assertNotIn(word, joined, word)

    def test_a_cleanup_that_fails_is_a_warning_and_never_an_error_and_it_deletes_the_groups_of_this_check_alone(self):
        done, lines, _, _ = run_script(CLEANUP, {"python3": python_stand_in()}, self.ENV)
        self.assertEqual(done.returncode, 0)
        self.assertEqual([line[len("arg:"):] for line in lines if line.startswith("arg:")], ["tools/operator-run.py", "cleanup", "--resource-group", GROUP, "--prefix", "op-aigw-", "--older-than-minutes", "0"])
        done, _, _, _ = run_script(CLEANUP, {"python3": python_stand_in()}, {**self.ENV, "FAKE_EXIT": "1"})
        self.assertEqual(done.returncode, 0, "a cleanup that fails does not fail a run that passed")
        self.assertIn(f"::warning::A container group whose name starts with op-aigw- may be left in resource group {GROUP}.", done.stdout)


class TheStepsAreWrittenAsTheRulesSay(unittest.TestCase):
    """The text of the steps: the order, the conditions, and the things that no step of these two actions may do."""

    def names(self):
        return re.findall(r"(?m)^      - name: (.+)$", WORKFLOW)

    def test_the_two_actions_are_offered_after_the_probe_and_described_in_plain_words(self):
        offered = re.findall(r"- (\S+)", re.search(r"options:\n((?:          - .+\n)+)", WORKFLOW).group(1))
        self.assertEqual(offered[-2:], ["aigateway", "aigateway-check"])
        self.assertEqual(offered[offered.index("operator-probe") + 1:offered.index("operator-probe") + 3], ["aigateway", "aigateway-check"])
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        gateway = description.split(" aigateway: ")[1].split(" aigateway-check: ")[0]
        for word in ("not API Management", "system-assigned identity", "with no key", "it needs foundry and operator first", "public whatever is asked", "the service has no private frontend",
                     "Microsoft Entra ID and role assignments only", "waits for the landing zone's route table", "deletes the built-in key master when the service lets it be deleted",
                     "changes nothing of the agents"):
            self.assertIn(word, gateway, word)
        checking = description.split(" aigateway-check: ")[1]
        for word in ("once without a token and once with a wrong alias", "from inside the network", "it needs aigateway and operator first", "up to ten minutes"):
            self.assertIn(word, checking, word)
        self.assertEqual(len(re.findall(r'(?m)^        description: "what-if: ', WORKFLOW)), 1, "the description stays one line")

    def test_the_steps_of_each_action_run_for_that_action_alone_in_the_order_of_the_owner_before_the_summary(self):
        names = self.names()
        for steps, action in ((APPLY, "aigateway"), (CHECKING, "aigateway-check")):
            positions = [names.index(name) for name in steps]
            self.assertEqual(positions, sorted(positions), steps)
            self.assertLess(names.index("Work out the settings"), positions[0])
            self.assertLess(positions[-1], names.index("What was done"))
            for name in steps:
                if name == CLEANUP:
                    self.assertIn("        if: always() && inputs.action == 'aigateway-check' && steps.aigw_check.outcome != 'skipped'\n", step(name))
                else:
                    self.assertIn(f"        if: inputs.action == '{action}'\n", step(name), name)
        self.assertEqual(len(re.findall(r"inputs\.action == 'aigateway'", WORKFLOW)), len(APPLY), "these steps, and no other step that runs for this action")
        self.assertEqual(len(re.findall(r"inputs\.action == 'aigateway-check'", WORKFLOW)), len(CHECKING), "the steps of the check, one condition each, and nothing else")
        self.assertIn("id: aigateway\n", step(DEPLOY))
        self.assertIn("id: aigw_operator\n", step(FIND))
        self.assertIn("id: aigw_host\n", step(HOST))
        self.assertIn("id: aigw_check\n", step(CHECK))

    def test_the_order_inside_the_action_is_check_deploy_wait_sign_in_limits_key_read_back(self):
        names = self.names()
        self.assertEqual([names.index(name) for name in APPLY], sorted(names.index(name) for name in APPLY))
        self.assertEqual(APPLY, [READY, DEPLOY, WAIT, LOGIN, POLICIES, KEY, READ_BACK])
        self.assertIn("uses: azure/login@", step(LOGIN))
        for name in (POLICIES, KEY, READ_BACK):
            self.assertGreater(names.index(name), names.index(LOGIN), "a fresh credential: the wait before them takes up to 20 minutes")
        self.assertLess(names.index(KEY), names.index(READ_BACK), "the read-back shows the end state of the keys")

    def test_the_template_is_deployed_once_and_previewed_once_and_nothing_else_makes_the_gateway(self):
        self.assertEqual(WORKFLOW.count("--template environment/aigateway/main.bicep"), 2, "the preview and the deploy, nothing else")
        deploy = code_of(DEPLOY)
        for word in ("--output gatewayName", '--name "aigateway-$GITHUB_RUN_ID"', '--parameters "$RUNNER_TEMP/aigateway.parameters.json"'):
            self.assertIn(word, deploy, word)
        self.assertEqual(WORKFLOW.count("python3 tools/aigateway-prep.py"), 3, "the limits, the key and the read-back")
        self.assertEqual(len(re.findall(r"aigateway-prep\.py (policies|remove-key|read-back)", WORKFLOW)), 3)

    def test_no_step_of_the_two_actions_makes_a_key_a_role_a_dns_object_or_a_deletion_of_its_own(self):
        scripts = [name for name in [*APPLY, *CHECKING] if name != LOGIN]
        for name in scripts:
            code = code_of(name)
            for word in ("az role assignment create", "az role assignment delete", "az role definition", "az network private-dns", "az network private-endpoint", "az keyvault", "listKeys", "listSecrets",
                         "primaryKey", "--auth-mode key", "az group delete", "az resource delete", "az provider register", "ipFilter", "az ad ", "az container", "--yes", "get-access-token"):
                self.assertNotIn(word, code, f"{word} in {name}")
            self.assertNotRegex(code, r"--method (put|patch|post|delete)", name)
        self.assertEqual([name for name in scripts if "az role assignment" in script_of(name)], [READY], "the one step that reads the deploy identity's assignments, and only reads them")
        self.assertEqual(re.findall(r"az role assignment (\w+)", code_of(READY)), ["list"])

    def test_the_comment_of_the_template_and_the_pre_check_say_that_the_frontend_is_public_and_nothing_pretends_otherwise(self):
        for name in (DEPLOY, READ_BACK):
            self.assertIn("public", step(name), name)
        self.assertNotRegex(WORKFLOW.lower(), r"private (frontend|endpoint) (of|for) the (ai )?gateway (is|was) (made|created)")
        what_was_done = step("What was done")
        self.assertIn("THE FRONTEND OF THE GATEWAY IS PUBLIC. The service has no private frontend, and its own setting for one has no effect.", what_was_done)
        self.assertIn("The frontend of the gateway is public and cannot be made private.", what_was_done)

    def test_the_check_steps_use_the_pin_of_the_operators_image_and_the_tool_and_nothing_more_in_the_secret_volume(self):
        code = code_of(CHECK)
        self.assertIn('--image "$OPERATOR_IMAGE"', code)
        self.assertEqual(re.findall(r'--secret-file "([^"]+)"', code), ["aigateway-check.py=tools/aigateway-check.py"])
        self.assertNotIn("--secure-env", code)
        self.assertIn("timeout-minutes: 25", step(CHECK))
        self.assertIn("--timeout-seconds 900", code)
        self.assertNotIn("OPERATOR_IMAGE:", step(CHECK), "the pin is the job's")
        size = (ROOT / "tools" / "aigateway-check.py").stat().st_size
        cap = int(re.search(r"(?m)^MAX_FILE_BYTES = ([0-9_]+)", (ROOT / "tools" / "operator-run.py").read_text(encoding="utf-8")).group(1).replace("_", ""))
        self.assertEqual(cap, 480_000)
        self.assertLess(size, cap // 4, "far below the limit of the secret volume")

    def test_the_network_step_looks_for_the_gateways_subnet_and_the_settings_step_gets_the_answer_and_the_policy_file(self):
        network = step("Find out what of the network is there already")
        self.assertIn('if [ "$network" = true ]; then aigw=$(exists "$vnet/subnets/snet-aigw"); else aigw=false; fi', network)
        self.assertIn('echo "aigw_subnet_exists=$aigw" >> "$GITHUB_OUTPUT"', network)
        self.assertNotRegex(network, r"--method (put|patch|post|delete)")
        params = step("Work out the settings")
        self.assertIn("ENV_AIGW_SUBNET_EXISTS: ${{ steps.network.outputs.aigw_subnet_exists }}", params)
        self.assertIn('contract_files="--contract environment/contract.json --contract-policy environment/gateway/contract-policy.xml --aigateway-policies environment/aigateway/policies.json"', params)
        self.assertIn('if [ -f "$RUNNER_TEMP/aigateway.parameters.json" ]; then', params, "the file is checked when there is one: a network with no free range has none")
        self.assertIn('--params "$RUNNER_TEMP/aigateway.parameters.json" --template "$RUNNER_TEMP/aigateway.json" --label aigateway', params)

    def test_the_template_is_compiled_linted_and_its_file_is_checked_in_both_workflows(self):
        for source in (WORKFLOW, CHECKS):
            self.assertIn("environment/aigateway/main.bicep", source)
            self.assertIn('aigateway.json"', source)
            self.assertIn("--label aigateway", source)
        self.assertIn("environment/operator/main.bicep environment/aigateway/main.bicep", WORKFLOW)
        self.assertIn("--aigateway-policies environment/aigateway/policies.json", CHECKS)

    def test_the_preview_reads_the_foundry_resource_and_the_operator_first_and_says_why_it_waits(self):
        preview = step("What the identity, the model side, the logger, the usage recording and the first cases would change")
        self.assertIn("FOUNDRY_ACCOUNT: ${{ steps.params.outputs.foundry_account_name }}", preview)
        block = preview.split("The AI Gateway, in the project's resource group")[1]
        for word in ("The AI Gateway cannot be previewed: the virtual network has no free range for its subnet", "The AI Gateway cannot be previewed yet: its subnet goes into the virtual network",
                     "The AI Gateway cannot be previewed yet: it reads the Foundry resource of the agents and the Operator's identity, and the actions foundry and operator make them.",
                     "--template environment/aigateway/main.bicep --parameters \"$RUNNER_TEMP/aigateway.parameters.json\""):
            self.assertIn(word, block, word)
        self.assertLess(block.index("cannot be previewed yet: its subnet"), block.index("--template environment/aigateway/main.bicep"))
        self.assertNotRegex(block, r"--method (put|patch|post|delete)")

    def test_both_actions_have_a_line_in_the_summary_for_success_and_for_failure(self):
        block = step("What was done")
        for action in ("aigateway", "aigateway-check"):
            self.assertEqual(len(re.findall(rf"(?m)^                {action}\) echo ", block)), 2, action)
        self.assertIn("AIGATEWAY_NAME: ${{ steps.params.outputs.aigateway_name }}", block)

    def test_the_condition_is_looked_at_by_the_object_id_that_the_run_read_from_its_own_token(self):
        self.assertIn("DEPLOYER_ID: ${{ steps.me.outputs.oid }}", step(READY))
        self.assertEqual(WORKFLOW.count("steps.me.outputs.oid"), 3, "the two steps that retire an old right, and the look at the condition of the right to assign roles")
        code = code_of(READY)
        for word in (f"foundry_user={FOUNDRY_USER}", f"models_user={MODELS_USER}", f"administrator={ADMINISTRATOR}", "--fill-principal-name false --fill-role-definition-name false"):
            self.assertIn(word, code, word)


if __name__ == "__main__":
    unittest.main()
