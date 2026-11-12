"""The Azure side of the Teams cards (docs/proposals/19-teams-cards-through-power-automate.md): the template of the subnet and the enterprise policy (environment/powerplatform/main.bicep), the queue and its setting in the
cases template, the files that the builder makes for them (tools/environment-params.py --powerplatform) and the checks of CI that compile and test them.

The resource types of the templates are pinned with the others' in test_environment_template.py (AGENTS.md rule 19), and what a template may read in test_deploy_scope.py. Nothing here calls Azure: the compile test
runs the Bicep compiler of the Azure CLI when it is on the machine, and says so when it is not."""
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from ipaddress import ip_network
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = "environment/powerplatform/main.bicep"
spec = importlib.util.spec_from_file_location("environment_params_of_the_powerplatform_template_tests", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def resources(source):
    """Symbolic name -> (type, body) of every top-level resource of a Bicep file, loops and conditions included."""
    found = {}
    pattern = r"^resource (\w+) '([^'@]+)@[^']+' (?:existing )?= (?:\[for [^\n]*\n)?\{?\n?(.*?)^(?:\}|\}\])\n"
    for match in re.finditer(pattern, source, re.M | re.S):
        found[match.group(1)] = (match.group(2), match.group(3))
    return found


SOURCE = text(PATH)
CODE = re.sub(r"(?<!:)//.*", "", SOURCE)
CASES = text("environment/cases/main.bicep")
CASES_CODE = re.sub(r"(?<!:)//.*", "", CASES)
SETTINGS = {
    "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "ENV_RESOURCE_GROUP": "rg-example", "ENV_LOCATION": "swedencentral", "ENV_VNET_PREFIX": "10.53.0.0/24",
    "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27", "ENV_DNS_SERVERS": "10.20.0.4", "ENV_OWNER": "owner@example.com", "ENV_BUDGET_AMOUNT": "25", "ENV_ALERT_EMAILS": "owner@example.com",
    "ENV_BUDGET_START": "2026-11-01", "CASES_SYSTEM_PRINCIPAL_ID": "12345678-dddd-eeee-ffff-123456789012", "ENV_FOUNDRY_PROJECT_EXISTS": "true",
    "FOUNDRY_PROJECT_PRINCIPAL_ID": "12345678-eeee-ffff-1111-123456789012", "OPERATOR_PRINCIPAL_ID": "12345678-aaaa-bbbb-cccc-123456789012",
    "AIGATEWAY_HOST": "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com",
}


def build(env, powerplatform=True, full=True):
    """The builder as the workflow runs it: the exit code, what it printed (as a dict), what it said and the files that it wrote."""
    with tempfile.TemporaryDirectory() as tmp:
        arguments = ["build", "--models", str(ROOT / "environment" / "models.json"), "--out-dir", str(Path(tmp) / "out")]
        if full:
            arguments += ["--aigateway-policies", str(ROOT / "environment" / "aigateway" / "policies.json"), "--governance", str(ROOT / "environment" / "aigateway" / "contracts.json")]
        if powerplatform:
            arguments += ["--powerplatform"]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ep.main(arguments, environ=env)
        files = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(tmp) / "out").glob("*.json"))} if (Path(tmp) / "out").exists() else {}
    return code, dict(line.split("=", 1) for line in out.getvalue().splitlines() if "=" in line), err.getvalue(), files


def values(files, name):
    return {k: v["value"] for k, v in files[name]["parameters"].items()}


class TheTemplate(unittest.TestCase):
    def setUp(self):
        self.found = resources(SOURCE)

    def test_it_reads_the_network_and_makes_the_group_the_subnet_and_the_policy_and_nothing_else(self):
        self.assertEqual({name: kind for name, (kind, _) in self.found.items()}, {
            "vnet": "Microsoft.Network/virtualNetworks",
            "powerPlatformNsg": "Microsoft.Network/networkSecurityGroups",
            "powerPlatformSubnet": "Microsoft.Network/virtualNetworks/subnets",
            "enterprisePolicy": "Microsoft.PowerPlatform/enterprisePolicies",
        })
        self.assertRegex(SOURCE, r"(?m)^resource vnet 'Microsoft\.Network/virtualNetworks@2025-05-01' existing = \{$", "the network is only read: the model side makes it")
        self.assertNotIn("#disable", CODE)

    def test_it_makes_no_role_no_endpoint_no_dns_object_no_route_no_peering_and_reads_nothing_at_deployment_time(self):
        for word in ("Microsoft.Authorization", "roleAssignments", "privateEndpoints", "privateDnsZones", "privateDnsZoneGroups", "virtualNetworkLinks", "routeTable", "virtualNetworkPeerings", "listKeys", "listSecrets",
                     "Microsoft.Web", "Microsoft.Storage", "Microsoft.BotService", "Microsoft.ApiManagement", "principalId", "publicIPAddresses"):
            self.assertNotIn(word, CODE, f"{word}: the landing zone provides the DNS and the routes (rule 19), a person gives the roles, and the queue is the cases template's")
        self.assertIsNone(re.search(r"\b(?:reference|list[A-Z]\w*)\(", CODE))

    def test_the_subnet_is_made_once_is_delegated_to_the_policy_holds_nothing_else_and_has_a_group_with_no_rule_and_no_default_outbound_access(self):
        subnet, group = self.found["powerPlatformSubnet"][1], self.found["powerPlatformNsg"][1]
        self.assertTrue(subnet.startswith("if (!powerPlatformSubnetExists) {"), "made only while it is not there: rule 27, the route table of the landing zone")
        for word in ("parent: vnet", "name: powerPlatformSubnetName", "addressPrefix: powerPlatformSubnetPrefix", "id: powerPlatformNsg.id", "defaultOutboundAccess: false"):
            self.assertIn(word, subnet, word)
        self.assertEqual(re.findall(r"serviceName: '([^']+)'", subnet), ["Microsoft.PowerPlatform/enterprisePolicies"], "one delegation: the subnet holds nothing else")
        self.assertIn("var powerPlatformSubnetName = 'snet-powerplatform'", CODE)
        self.assertIn("securityRules: []", group)
        self.assertIn("name: 'nsg-${workload}-powerplatform'", group)
        self.assertNotIn("if (", group, "the group is written every time, as the others are")

    def test_the_policy_is_a_network_injection_policy_of_the_geography_sweden_with_one_network_and_made_once(self):
        policy = self.found["enterprisePolicy"][1]
        self.assertTrue(policy.startswith("if (!enterprisePolicyExists) {"), "a policy that an environment is linked to is read only: a second write is refused")
        for word in ("name: enterprisePolicyName", "location: enterprisePolicyGeography", "kind: 'NetworkInjection'", "id: vnet.id", "name: powerPlatformSubnetName"):
            self.assertIn(word, policy, word)
        self.assertEqual(policy.count("virtualNetworks"), 1)
        self.assertEqual(len(re.findall(r"id: vnet\.id", policy)), 1, "one virtual network: the geography Sweden has one Azure region")
        self.assertIn("var enterprisePolicyGeography = 'sweden'", CODE)
        self.assertIn("var enterprisePolicyName = 'ep-${workload}-netinjection'", CODE)
        self.assertIn("Microsoft.PowerPlatform/enterprisePolicies@2020-10-30-preview", CODE)
        self.assertRegex(policy, r"(?m)^  dependsOn: \[\n    powerPlatformSubnet\n  \]$", "the subnet is there before the policy names it")

    def test_the_region_is_the_one_azure_region_of_the_geography_and_the_parameters_are_the_ones_of_the_other_subnet_templates(self):
        self.assertRegex(CODE, r"(?m)^@allowed\(\[\n  'swedencentral'\n\]\)\nparam location string = 'swedencentral'$")
        self.assertEqual(re.findall(r"(?m)^param (\w+) ", CODE), ["location", "workload", "owner", "powerPlatformSubnetPrefix", "powerPlatformSubnetExists", "enterprisePolicyExists"])
        for pattern in (r"(?m)^@minLength\(9\)\n@maxLength\(18\)\nparam powerPlatformSubnetPrefix string$", r"(?m)^param powerPlatformSubnetExists bool = false$", r"(?m)^param enterprisePolicyExists bool = false$",
                        r"(?m)^param workload string = 'meternaut'$", r"(?m)^@minLength\(1\)\nparam owner string$"):
            self.assertRegex(CODE, pattern)
        self.assertIn("var virtualNetworkName = 'vnet-${workload}'", CODE)
        self.assertIn("name: 'vnet-${workload}'", text("environment/main.bicep"), "the virtual network that the model side makes")

    def test_it_gives_the_workflow_the_names_and_nothing_else(self):
        self.assertEqual(re.findall(r"(?m)^output (\w+) ", CODE), ["subnetName", "enterprisePolicyName", "enterprisePolicyId"])

    def test_the_header_says_what_it_makes_why_it_is_made_once_where_the_names_come_from_and_who_gives_the_roles(self):
        header = re.sub(r"\s*\n//\s*", " ", SOURCE.split("targetScope", 1)[0])
        for words in ("No bot, no app registration, no public endpoint and no key.", "the owner's own reference repository tinodo/secure-request-classifier (MIT",
                      "The policy's location is the Power Platform geography `sweden`, not an Azure region", "The geography Sweden has one Azure region, swedencentral",
                      "(1) The policy's location is", "The subnet is made once and then left alone (powerPlatformSubnetExists)", "(AGENTS.md rule 27)", "waits until the table is on the subnet, before anybody links an environment",
                      "The policy is made once too (enterprisePolicyExists)", "Power Platform refuses every write to a policy that an environment is linked to (EnterprisePolicyUpdateNotAllowed)",
                      "The range cannot be changed once the subnet is delegated", "and for the range a request to Microsoft support", "a /28 is the least", "a /26 is what a production environment needs",
                      "Left out on purpose (AGENTS.md rule 19)", "No role assignment: the Power Platform administrator needs Reader on the policy to link it, which a person gives",
                      "2020-10-30-preview", "which Microsoft's own PowerShell module (microsoft/PowerPlatform-EnterprisePolicies) writes",
                      "Deployed only by the workflow .github/workflows/deploy-hub.yml (AGENTS.md rule 18)."):
            self.assertIn(words, header, words)

    def test_the_template_compiles_and_makes_what_it_says(self):
        python = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")
        az = [str(python), "-IBm", "azure.cli"] if python.exists() else ([shutil.which("az")] if shutil.which("az") else None)
        bicep = Path.home() / ".azure" / "bin" / ("bicep.exe" if python.exists() else "bicep")
        if az is None or not bicep.exists():
            self.skipTest("no Azure CLI with Bicep on this machine: the checks of CI compile every template")
        done = subprocess.run([*az, "bicep", "build", "--file", str(ROOT / PATH), "--stdout"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        compiled = json.loads(done.stdout)
        rows = compiled["resources"].values() if isinstance(compiled["resources"], dict) else compiled["resources"]
        self.assertEqual({r["type"]: r.get("condition") for r in rows}, {
            "Microsoft.Network/networkSecurityGroups": None,
            "Microsoft.Network/virtualNetworks/subnets": "[not(parameters('powerPlatformSubnetExists'))]",
            "Microsoft.PowerPlatform/enterprisePolicies": "[not(parameters('enterprisePolicyExists'))]"})
        self.assertEqual({r["type"]: r["apiVersion"] for r in rows}["Microsoft.PowerPlatform/enterprisePolicies"], "2020-10-30-preview")
        self.assertEqual(set(compiled["parameters"]), {"location", "workload", "owner", "powerPlatformSubnetPrefix", "powerPlatformSubnetExists", "enterprisePolicyExists"})
        self.assertEqual(compiled["parameters"]["location"]["allowedValues"], ["swedencentral"])
        self.assertEqual(set(compiled["outputs"]), {"subnetName", "enterprisePolicyName", "enterprisePolicyId"})
        # The parameter file that the builder writes fits this very template.
        code, _, err, files = build(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(ep.check_against(files["powerplatform.parameters.json"], compiled, "powerplatform"), [])


class TheQueue(unittest.TestCase):
    def test_the_cases_template_makes_the_queue_of_the_cards_next_to_the_control_queue_and_tells_the_app_its_name(self):
        found = resources(CASES)
        self.assertEqual(found["cardsQueue"][0], "Microsoft.Storage/storageAccounts/queueServices/queues")
        self.assertIn("var cardsQueueName = 'teams-cards'", CASES_CODE)
        self.assertIn("parent: queueService", found["cardsQueue"][1])
        self.assertIn("name: cardsQueueName", found["cardsQueue"][1])
        self.assertNotIn("properties", found["cardsQueue"][1], "a plain queue: the app sets the time to live of each message")
        self.assertIn("{ name: 'TEAMS_CARDS_QUEUE', value: cardsQueueName }", CASES_CODE)
        self.assertEqual(CASES_CODE.count("TEAMS_CARDS_QUEUE"), 1)

    def test_the_cases_template_makes_the_queue_that_the_flow_writes_after_a_post_and_the_app_reads_it_through_the_host_connection(self):
        found = resources(CASES)
        self.assertEqual(found["postedQueue"][0], "Microsoft.Storage/storageAccounts/queueServices/queues")
        self.assertIn("var postedQueueName = 'teams-posted'", CASES_CODE)
        self.assertIn("parent: queueService", found["postedQueue"][1])
        self.assertIn("name: postedQueueName", found["postedQueue"][1])
        self.assertNotIn("properties", found["postedQueue"][1], "a plain queue")
        self.assertIn("{ name: 'TEAMS_POSTED_QUEUE', value: postedQueueName }", CASES_CODE)
        self.assertEqual(CASES_CODE.count("TEAMS_POSTED_QUEUE"), 1)
        self.assertIn("postedQueue", " ".join(re.findall(r"(?m)^  dependsOn: \[\n(.*?)^  \]", CASES, re.S | re.M)), "the trigger reads it, so the app starts after it exists, as for the control queue")
        for name, (kind, role_body) in found.items():
            if kind == "Microsoft.Authorization/roleAssignments":
                self.assertNotIn("postedQueue", role_body, f"{name}: the app reads it with the role that it holds on the account, and the flow's person is given the right to write by hand")

    def test_the_apps_identity_can_send_to_it_through_the_role_that_it_holds_on_the_account_and_no_role_was_added_for_the_queue(self):
        found = resources(CASES)
        self.assertIn("Microsoft.Authorization/roleAssignments", found["functionUsesQueues"][0])
        body = found["functionUsesQueues"][1]
        self.assertIn("scope: storage", body, "the whole account: every queue of it, this one too")
        self.assertIn("storageQueueDataContributorRoleId", body)
        self.assertIn("var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'", CASES_CODE, "Storage Queue Data Contributor, which can add a message")
        for name, (kind, role_body) in found.items():
            if kind == "Microsoft.Authorization/roleAssignments":
                self.assertNotIn("cardsQueue", role_body, f"{name}: the queue's reader is a person's connection, and the role is given by hand")

    def test_the_storage_account_stays_private_and_keyless_so_the_queue_is_reached_only_through_the_private_endpoint(self):
        base = re.sub(r"//.*", "", text("environment/base/main.bicep"))
        self.assertIn("publicNetworkAccess: 'Disabled'", base)
        self.assertIn("allowSharedKeyAccess: false", base)
        self.assertIn("'queue'", base, "the queue endpoint is one of the three private endpoints of the account")

    def test_the_app_is_told_no_more_than_the_name_and_the_queue_does_not_wake_it(self):
        self.assertNotIn("cardsQueue", " ".join(re.findall(r"(?m)^  dependsOn: \[\n(.*?)^  \]", CASES, re.S | re.M)), "the app only sends to it: no start-up depends on it")


class TheBuilder(unittest.TestCase):
    def test_with_the_flag_it_writes_the_file_and_the_lines_and_without_it_nothing_of_the_output_changes(self):
        code, out, err, files = build(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(values(files, "powerplatform.parameters.json"), {"location": "swedencentral", "owner": "owner@example.com", "powerPlatformSubnetPrefix": "10.53.0.96/27",
                                                                           "powerPlatformSubnetExists": False, "enterprisePolicyExists": False})
        self.assertEqual({k: v for k, v in out.items() if k.startswith("powerplatform_") or k == "cards_queue_name"}, {
            "powerplatform_subnet_name": "snet-powerplatform", "powerplatform_subnet_prefix": "10.53.0.96/27", "powerplatform_policy_name": "ep-meternaut-netinjection",
            "powerplatform_geography": "sweden", "powerplatform_files": "true", "powerplatform_reason": "", "cards_queue_name": "teams-cards"})
        plain_code, plain_out, _, plain_files = build(SETTINGS, powerplatform=False)
        self.assertEqual(plain_code, 0)
        self.assertNotIn("powerplatform.parameters.json", plain_files)
        self.assertEqual({k: v for k, v in out.items() if not (k.startswith("powerplatform_") or k == "cards_queue_name")}, plain_out)
        self.assertEqual({k: v for k, v in files.items() if k != "powerplatform.parameters.json"}, plain_files, "every other file is what it was")

    def test_the_subnet_is_the_last_free_slash_27_beside_the_five_other_subnets_with_or_without_the_gateways_files(self):
        for full in (True, False):
            code, out, _, files = build(SETTINGS, full=full)
            self.assertEqual(code, 0)
            mine = ip_network(out["powerplatform_subnet_prefix"])
            others = [ip_network(SETTINGS["ENV_PE_SUBNET_PREFIX"]), ip_network(out["function_subnet_prefix"]), ip_network(out["web_subnet_prefix"]), ip_network(out["ops_subnet_prefix"]), ip_network("10.53.0.128/26")]
            self.assertEqual(mine.prefixlen, 27)
            self.assertTrue(mine.subnet_of(ip_network(SETTINGS["ENV_VNET_PREFIX"])))
            self.assertFalse([o for o in others if mine.overlaps(o)], f"full={full}: it must not overlap the gateway's subnet even when the gateway's files are not asked for")
            self.assertEqual(str(mine), "10.53.0.96/27")

    def test_what_the_workflow_found_in_azure_goes_into_the_file_and_a_wrong_flag_is_refused(self):
        code, _, _, files = build({**SETTINGS, "ENV_PP_SUBNET_EXISTS": "true", "ENV_PP_POLICY_EXISTS": "TRUE"})
        self.assertEqual(code, 0)
        file = values(files, "powerplatform.parameters.json")
        self.assertEqual((file["powerPlatformSubnetExists"], file["enterprisePolicyExists"]), (True, True))
        code, _, err, files = build({**SETTINGS, "ENV_PP_POLICY_EXISTS": "maybe"})
        self.assertEqual(code, 2)
        self.assertIn("ENV_PP_POLICY_EXISTS is true or false", err)

    def test_another_region_gets_no_file_and_a_reason_and_a_network_with_no_room_gets_no_range_invented(self):
        code, out, err, files = build({**SETTINGS, "ENV_LOCATION": "westeurope"})
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("powerplatform.parameters.json", files)
        self.assertEqual((out["powerplatform_files"], out["powerplatform_subnet_prefix"]), ("false", ""))
        self.assertIn("has one Azure region, swedencentral", out["powerplatform_reason"])
        code, out, err, files = build({**SETTINGS, "ENV_VNET_PREFIX": "10.53.0.0/25"})
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("powerplatform.parameters.json", files)
        self.assertEqual((out["powerplatform_files"], out["powerplatform_subnet_prefix"]), ("false", ""))
        self.assertIn("no free /27", out["powerplatform_reason"])
        self.assertIn("the owner decides", out["powerplatform_reason"])
        self.assertIn("a /28 is the least", out["powerplatform_reason"])

    def test_the_size_is_one_value_that_a_person_changes_before_the_first_deploy(self):
        self.assertEqual(ep.POWERPLATFORM_SUBNET_LENGTH, 27)
        self.assertGreaterEqual(2 ** (32 - ep.POWERPLATFORM_SUBNET_LENGTH) - 5, 11, "a /28 is the least: 6 to 10 addresses and the five that Azure keeps")
        net = ip_network("10.53.0.0/24")
        taken = (ip_network("10.53.0.0/27"), ip_network("10.53.0.32/27"), ip_network("10.53.0.64/27"), ip_network("10.53.0.96/27"), ip_network("10.53.0.128/26"), ip_network("10.53.0.192/26"))
        self.assertIsNone(ep.powerplatform_subnet(net, taken))
        self.assertEqual(str(ep.powerplatform_subnet(net, taken[:3] + taken[4:])), "10.53.0.96/27")
        self.assertIsNone(ep.powerplatform_subnet(ip_network("10.53.0.0/28"), ()), "a network smaller than the subnet has none")

    def test_the_builders_names_are_the_templates(self):
        self.assertIn("var powerPlatformSubnetName = 'snet-powerplatform'", CODE)
        self.assertEqual(ep.POWERPLATFORM_SUBNET_NAME, "snet-powerplatform")
        self.assertIn("var enterprisePolicyName = 'ep-${workload}-netinjection'", CODE)
        self.assertEqual(ep.POWERPLATFORM_POLICY_NAME, "ep-meternaut-netinjection")
        self.assertIn(f"var enterprisePolicyGeography = '{ep.POWERPLATFORM_GEOGRAPHY}'", CODE)
        self.assertIn(f"'{ep.POWERPLATFORM_AZURE_REGION}'", CODE)
        self.assertIn(f"var cardsQueueName = '{ep.CARDS_QUEUE_NAME}'", CASES_CODE)

    def test_the_documentation_of_the_builder_says_what_the_flag_does(self):
        source = text("tools/environment-params.py")
        for words in ("[--powerplatform]", "is asked for with --powerplatform, and nothing else of the output changes without it", "powerplatform.parameters.json     for environment/powerplatform/main.bicep",
                      "ENV_PP_SUBNET_EXISTS and ENV_PP_POLICY_EXISTS", "no range is invented"):
            self.assertIn(words, source, words)


class TheChecksOfCi(unittest.TestCase):
    CHECKS = text(".github/workflows/checks.yml")

    def test_ci_compiles_and_lints_the_template_and_tests_the_parameter_file_against_it(self):
        self.assertIn("environment/governance/main.bicep environment/powerplatform/main.bicep infra/budgets/*.bicep; do", self.CHECKS)
        self.assertIn("--governance environment/aigateway/contracts.json --powerplatform > /dev/null", self.CHECKS)
        self.assertIn('az bicep build --file environment/powerplatform/main.bicep --outfile "$out/powerplatform.json"', self.CHECKS)
        self.assertIn('python tools/environment-params.py check --params "$out/powerplatform.parameters.json" --template "$out/powerplatform.json" --label powerplatform', self.CHECKS)

    def test_the_template_is_listed_where_the_scope_test_lists_the_templates(self):
        self.assertIn('"environment/powerplatform/main.bicep"', text("tools/tests/test_deploy_scope.py"))
        self.assertIn('"environment/powerplatform/main.bicep": {', text("tools/tests/test_environment_template.py"))


if __name__ == "__main__":
    unittest.main()
