"""The AI Gateway's subnet is made first, and the gateway after the landing zone's route table: the template of the subnet (environment/aigateway/subnet.bicep), the gateway's template that no longer
makes a network resource (environment/aigateway/main.bicep), the files of the builder (tools/environment-params.py), the order of the steps of the action aigateway in .github/workflows/deploy-hub.yml, and
what the documents say about it.

Why. The landing zone's network manager puts one managed route table on a new subnet some 70 seconds to five minutes after the subnet is made (CHANGELOG.md, 2026-11-05), and the service takes the gateway's
backend subnet when the gateway is made and treats it as read-only afterwards. So the first creation of the gateway must not race with the network manager's write to the subnet: the subnet is made alone, the
action waits until the route table is on it, signs in again, and only then makes the gateway. AGENTS.md rule 27 is the precedent: a template makes a subnet once and never undoes what the landing zone added.

The steps are run with bash against stand-ins for the commands that they call (the Azure CLI, python3 and sleep), as test_aigateway_workflow.py does, and the helpers of the other tests of the AI Gateway are
loaded by their paths. No test calls Azure."""
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(file_name, label):
    """Another test module of this folder, by its path: the stand-ins and the way to run a step are the ones that the tests of the other steps of the action use."""
    spec = importlib.util.spec_from_file_location(label, ROOT / "tools" / "tests" / file_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AW = load("test_aigateway_workflow.py", "aigateway_workflow_of_the_subnet_first_tests")
AG = load("test_aigateway_agents_workflow.py", "aigateway_agents_workflow_of_the_subnet_first_tests")
AP = load("test_aigateway_agents_params.py", "aigateway_agents_params_of_the_subnet_first_tests")
AT = load("test_aigateway_template.py", "aigateway_template_of_the_subnet_first_tests")


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


def without_comments(source):
    """The code of a Bicep file: the comments are removed, but not the two slashes of a URL."""
    return re.sub(r"(?<!:)//.*", "", source)


SUBNET_PATH = "environment/aigateway/subnet.bicep"
GATEWAY_PATH = "environment/aigateway/main.bicep"
SUBNET = text(SUBNET_PATH)
GATEWAY_TEMPLATE = text(GATEWAY_PATH)
SUBNET_CODE = without_comments(SUBNET)
GATEWAY_CODE = without_comments(GATEWAY_TEMPLATE)
WORKFLOW = AW.WORKFLOW
CHECKS = AW.CHECKS
RECORD = text("docs/proposals/08-ai-gateway.md")
BOOTSTRAP = text("environment/BOOTSTRAP.md")
CHANGELOG = text("CHANGELOG.md")
README = text("README.md")
PREVIEW = "What the model side, the usage recording, the Foundry resource, the first cases, the Operator and the AI Gateway's templates would change"
GUARD = "Refuse the AI Gateway unless the owner asked for a public one in writing"
RECORD_SECTION = "## The subnet is made first, and the gateway after the landing zone's route table\n"
BOOTSTRAP_SECTION = "## Added on 2026-11-07 for the AI Gateway"
ENTRY = "The AI Gateway's subnet is made first, and the gateway after the landing zone's route table: built, not deployed — 2026-11-07"


class TheTemplateOfTheSubnet(unittest.TestCase):
    def setUp(self):
        self.found = AT.resources(SUBNET)

    def test_it_reads_the_network_and_makes_the_security_group_and_the_subnet_and_nothing_else(self):
        self.assertEqual({name: kind for name, (kind, _) in self.found.items()}, {
            "vnet": "Microsoft.Network/virtualNetworks",
            "aigwNsg": "Microsoft.Network/networkSecurityGroups",
            "aigwSubnet": "Microsoft.Network/virtualNetworks/subnets",
        })
        self.assertRegex(SUBNET, r"(?m)^resource vnet 'Microsoft\.Network/virtualNetworks@2025-05-01' existing = \{$", "the network is only read: the model side makes it")
        self.assertEqual(set(re.findall(r"(?m)^resource \w+ 'Microsoft\.Network/[^']+@([^']+)'", SUBNET_CODE)), {"2025-05-01"}, "the version that the gateway's template used for them")
        self.assertNotIn("#disable", SUBNET_CODE, "the types of all three are known: no rule is switched off")

    def test_the_subnet_is_made_once_is_delegated_has_no_default_outbound_access_and_sits_behind_a_group_with_no_rule_of_its_own(self):
        subnet, group = self.found["aigwSubnet"][1], self.found["aigwNsg"][1]
        self.assertIn("if (!aigwSubnetExists)", subnet, "made only while it is not there (rule 27)")
        for word in ("parent: vnet", "name: aigwSubnetName", "addressPrefix: aigwSubnetPrefix", "networkSecurityGroup:", "id: aigwNsg.id", "name: 'ai-gateway'",
                     "serviceName: 'Microsoft.App/environments'", "defaultOutboundAccess: false"):
            self.assertIn(word, subnet, word)
        self.assertEqual(re.findall(r"serviceName: '([^']+)'", subnet), ["Microsoft.App/environments"], "one delegation, and nothing else lives in the subnet")
        self.assertIn("securityRules: []", group)
        self.assertIn("name: 'nsg-${workload}-aigw'", group)
        self.assertNotIn("if (", group, "the group is written every time, as it was in the gateway's template")
        self.assertNotIn("Deny", SUBNET_CODE)

    def test_the_parameters_are_the_ones_the_gateways_template_had_with_the_same_limits_and_defaults(self):
        for pattern in (r"(?m)^@minLength\(9\)\n@maxLength\(18\)\nparam aigwSubnetPrefix string$", r"(?m)^param aigwSubnetExists bool = false$", r"(?m)^param workload string = 'meternaut'$",
                        r"(?m)^@minLength\(1\)\nparam owner string$", r"(?m)^param location string = resourceGroup\(\)\.location$"):
            self.assertRegex(SUBNET_CODE, pattern)
        self.assertEqual(re.findall(r"(?m)^param (\w+) ", SUBNET_CODE), ["location", "workload", "owner", "aigwSubnetPrefix", "aigwSubnetExists"])

    def test_it_holds_no_gateway_no_role_no_key_no_route_table_no_private_endpoint_and_no_dns_object(self):
        for word in ("aigateways", "roleAssignments", "listKeys", "routeTable", "privateEndpoints", "privateDnsZone", "virtualNetworkLinks", "publicIPAddresses"):
            self.assertNotIn(word.lower(), SUBNET_CODE.lower(), f"{word}: the landing zone adds the route table (rules 19 and 27), and the gateway has a template of its own")

    def test_it_gives_the_workflow_the_name_of_the_subnet_and_nothing_else(self):
        self.assertEqual(re.findall(r"(?m)^output (\w+) ", SUBNET_CODE), ["subnetName"])
        self.assertIn("output subnetName string = aigwSubnetName", SUBNET_CODE)

    def test_the_header_says_why_it_is_a_template_of_its_own(self):
        header = re.sub(r"\s*\n//\s*", " ", SUBNET.split("targetScope", 1)[0])
        for words in ("the first of the two templates of the action aigateway", "environment/aigateway/main.bicep, which reads this subnet by its name and needs it to be there when it is deployed",
                      "some 70 seconds to five minutes after the subnet is made", "treats it as read-only afterwards",
                      "the first creation of the gateway has to happen on the subnet as the landing zone leaves it, and not while the network manager is still writing to the subnet",
                      "In one template the wait for the route table could only come after the gateway.",
                      "So the workflow deploys this template, waits until the route table is on the subnet, signs in again and only then deploys the gateway.",
                      "it is made only while it is not there (aigwSubnetExists)", "(AGENTS.md rule 27)", "deploys this template only when it is not.",
                      'Deployed only by the workflow .github/workflows/deploy-hub.yml, action "aigateway" (AGENTS.md rule 18).'):
            self.assertIn(words, header, words)

    def test_the_comment_on_the_security_group_says_what_microsofts_sample_does_and_that_none_of_its_rules_is_made(self):
        comment = re.sub(r"\s*\n//\s*", " ", SUBNET)
        for words in ("The portal's in-product text (https://ai.gateway.azure.com, read 2026-11-07) says that no rules are required.",
                      "Microsoft's lab 18 (Azure/aigateway, labs/18-private-networking) adds two allow rules (outbound 443 to Storage and to AzureKeyVault) and no deny rule, so next to the default rules, "
                      "which allow outbound traffic, they change nothing, and none is made here."):
            self.assertIn(words, comment, words)
        self.assertNotIn("belong to the older API Management gateway", SUBNET, "the two rules are in Microsoft's own sample for this service: they are not the older gateway's")
        self.assertEqual(re.findall(r"securityRules: (\[.*\])", SUBNET_CODE), ["[]"], "the group has no rule of its own")

    def test_the_names_and_the_tags_are_the_ones_of_the_gateways_template_and_the_gateway_names_the_subnet_by_the_same_two_names(self):
        tags = "var tags = {\n  workload: workload\n  component: 'ai-gateway'\n  environment: 'dev'\n  owner: owner\n  'meternaut-stage': 'ai-gateway'\n}"
        for code in (SUBNET_CODE, GATEWAY_CODE):
            self.assertIn(tags, code)
            self.assertIn("var virtualNetworkName = 'vnet-${workload}'", code)
            self.assertIn("var aigwSubnetName = 'snet-aigw'", code)
            self.assertRegex(code, r"(?m)^param workload string = 'meternaut'$")
        self.assertIn("name: 'vnet-${workload}'", text("environment/main.bicep"), "the virtual network that the model side makes")
        self.assertIn("backend: {\n      subnet: {\n        id: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, aigwSubnetName)\n      }\n    }", GATEWAY_CODE)
        self.assertIn("output subnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, aigwSubnetName)", GATEWAY_CODE)

    def test_the_gateways_template_is_the_same_but_for_the_subnet(self):
        self.assertNotRegex(GATEWAY_CODE, r"(?m)^resource (vnet|aigwNsg|aigwSubnet) ", "the network, the group and the subnet are in the subnet's template now")
        for word in ("aigwSubnetPrefix", "aigwSubnetExists", "networkSecurityGroup", "delegations", "defaultOutboundAccess", "addressPrefix"):
            self.assertNotIn(word, GATEWAY_CODE, f"{word}: it is in the subnet's template now")
        self.assertEqual(depends_on_of_the_gateway(), set(), "no dependsOn: the subnet is in Azure before this template is deployed")
        for word in ("@batchSize(1)\n#disable-next-line BCP081\nresource modelOfProvider ", "@batchSize(1)\n#disable-next-line BCP081\nresource aliasOfModel ", "resource gatewayCallsFoundry ", "resource operatorCallsTheModels ",
                     "resource projectCallsTheModels ", "resource telemetryExporter ", "output gatewayName string = gateway.name", "output gatewayHost string = gateway.properties.frontend.defaultHostname"):
            self.assertIn(word, GATEWAY_CODE, word)

    def test_the_two_templates_compile_and_the_parameters_are_where_they_should_be(self):
        python = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")
        az = [str(python), "-IBm", "azure.cli"] if python.exists() else ([shutil.which("az")] if shutil.which("az") else None)
        bicep = Path.home() / ".azure" / "bin" / ("bicep.exe" if python.exists() else "bicep")
        if az is None or not bicep.exists():
            self.skipTest("no Azure CLI with Bicep on this machine: the workflow and the checks compile every template")
        compiled = {}
        for path in (SUBNET_PATH, GATEWAY_PATH):
            done = subprocess.run([*az, "bicep", "build", "--file", str(ROOT / path), "--stdout"], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr[-600:])
            compiled[path] = json.loads(done.stdout)
        subnet, gateway = compiled[SUBNET_PATH], compiled[GATEWAY_PATH]
        resources = subnet["resources"].values() if isinstance(subnet["resources"], dict) else subnet["resources"]
        self.assertEqual({r["type"]: r.get("condition") for r in resources},
                         {"Microsoft.Network/networkSecurityGroups": None, "Microsoft.Network/virtualNetworks/subnets": "[not(parameters('aigwSubnetExists'))]"})
        self.assertEqual(set(subnet["parameters"]), {"location", "workload", "owner", "aigwSubnetPrefix", "aigwSubnetExists"})
        self.assertEqual(set(subnet["outputs"]), {"subnetName"})
        self.assertFalse({"aigwSubnetPrefix", "aigwSubnetExists"} & set(gateway["parameters"]), "the gateway's template no longer takes the settings of the subnet")
        gateway_resources = gateway["resources"].values() if isinstance(gateway["resources"], dict) else gateway["resources"]
        self.assertFalse([r["type"] for r in gateway_resources if r["type"].startswith("Microsoft.Network")], "and makes no network resource")


def depends_on_of_the_gateway():
    return AT.depends_on(AT.resources(GATEWAY_TEMPLATE)["gateway"][1])


class TheBuilderWritesAFileForEachTemplate(unittest.TestCase):
    def build(self, **changes):
        code, out, err, files = AP.build({**AP.SETTINGS, **changes})
        self.assertEqual((code, err), (0, ""))
        return files, AP.outputs(out)

    def test_it_writes_the_file_of_the_subnet_the_file_of_the_gateway_and_the_policies(self):
        files, outputs = self.build()
        self.assertEqual({name for name in files if name.startswith("aigateway")}, {"aigateway-subnet.parameters.json", "aigateway.parameters.json", "aigateway-policies.json"})
        self.assertEqual({key: value for key, value in outputs.items() if key.startswith("aigateway_")},
                         {"aigateway_name": outputs["aigateway_name"], "aigateway_subnet_name": "snet-aigw", "aigateway_subnet_prefix": "10.53.0.128/26", "aigateway_aliases": "gpt-6-luna gpt-6.1-sol",
                          "aigateway_files": "true"}, "the outputs are what they were: the action reads the same names")

    def test_the_two_parameters_of_the_subnet_moved_to_its_file_and_the_gateways_file_has_neither(self):
        files, _ = self.build()
        subnet, gateway = AP.values(files, "aigateway-subnet.parameters.json"), AP.values(files, "aigateway.parameters.json")
        self.assertEqual(set(subnet), {"location", "owner", "aigwSubnetPrefix", "aigwSubnetExists"}, "no workload: the template's default is the one of every other file of the gateway")
        self.assertEqual(set(gateway), {"location", "owner", "gatewayName", "foundryAccountName", "models", "foundryProjectPrincipalId"})
        self.assertFalse({"aigwSubnetPrefix", "aigwSubnetExists"} & set(gateway))
        self.assertEqual((subnet["aigwSubnetPrefix"], subnet["aigwSubnetExists"]), ("10.53.0.128/26", False))
        self.assertEqual((subnet["location"], subnet["owner"]), (gateway["location"], gateway["owner"]))

    def test_the_flag_that_the_network_step_reads_goes_to_the_file_of_the_subnet_alone(self):
        files, _ = self.build()
        for given, expected in (("true", True), ("false", False), ("", False)):
            changed, _ = self.build(ENV_AIGW_SUBNET_EXISTS=given)
            self.assertIs(AP.values(changed, "aigateway-subnet.parameters.json")["aigwSubnetExists"], expected, given)
            self.assertEqual(changed["aigateway.parameters.json"], files["aigateway.parameters.json"], "the gateway's file is the same byte for byte whatever the flag is")

    def test_a_network_with_no_free_range_gets_neither_file_and_the_outputs_say_so(self):
        files, outputs = self.build(ENV_VNET_PREFIX="10.53.0.0/25")
        self.assertFalse([name for name in files if name.startswith("aigateway")])
        self.assertEqual((outputs["aigateway_files"], outputs["aigateway_subnet_prefix"]), ("false", ""))

    def test_each_file_names_only_what_its_template_declares_and_gives_what_the_template_requires(self):
        files, _ = self.build()
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, source in (("aigateway-subnet.parameters.json", SUBNET), ("aigateway.parameters.json", GATEWAY_TEMPLATE)):
            declared = AP.declared(source)
            given = json.loads(files[name])["parameters"]
            self.assertLessEqual(set(given), set(declared), name)
            self.assertLessEqual({setting for setting, (_, default) in declared.items() if default is None}, set(given), name)
            for setting, wrapped in given.items():
                self.assertIsInstance(wrapped["value"], types[declared[setting][0]], (name, setting))

    def test_the_docstring_of_the_builder_lists_both_files_and_the_help_of_the_option_names_the_three(self):
        doc = flat(AP.ep.__doc__)
        self.assertIn("aigateway-subnet.parameters.json for environment/aigateway/subnet.bicep (the AI Gateway's subnet and its network security group: the action aigateway deploys it first, and waits for the "
                      "landing zone's route table on the subnet before it deploys the gateway),", doc)
        self.assertIn("aigateway.parameters.json for environment/aigateway/main.bicep (the AI Gateway: its models and aliases, and its roles; the subnet has to be there already), and", doc)
        self.assertIn("all three from --aigateway-policies", doc)
        self.assertIn("also writes aigateway-subnet.parameters.json, aigateway.parameters.json and aigateway-policies.json", text("tools/environment-params.py"))


def blocks():
    """Every step of the workflow, in order, with its name and its text."""
    return re.findall(r"(?ms)^      - name: (.+?)\n(.*?)(?=^      - |\Z)", WORKFLOW)


class TheActionMakesTheSubnetThenWaitsThenMakesTheGateway(unittest.TestCase):
    def names(self):
        return [name for name, _ in blocks()]

    def test_the_steps_that_run_for_aigateway_are_these_nine_in_this_order_after_the_guard_that_is_the_first_step_of_the_job(self):
        ran = [name for name, body in blocks() if re.search(r"(?m)^        if: inputs\.action == 'aigateway'$", body)]
        self.assertEqual(ran[0], GUARD, "the guard that stops the action unless the owner asked for a public AI Gateway in writing is the first step of the job (test_ai_gateway_guard.py)")
        self.assertEqual(self.names()[0], GUARD)
        ran = ran[1:]
        self.assertEqual(ran, [AW.READY, AW.SUBNET, AW.WAIT, AW.GATEWAY_LOGIN, AW.DEPLOY, AW.LOGIN, AW.POLICIES, AW.KEY, AW.READ_BACK])
        names = self.names()
        positions = [names.index(name) for name in ran]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(ran))), "no step of another action is in between: the nine follow one another")
        self.assertEqual([names.count(name) for name in ran], [1] * 9, "and each is there once: the wait is no longer after the gateway as well")

    def test_the_subnet_is_deployed_before_the_wait_and_the_wait_comes_before_the_deploy_of_the_gateway(self):
        names = self.names()
        self.assertLess(names.index(AW.READY), names.index(AW.SUBNET))
        self.assertLess(names.index(AW.SUBNET), names.index(AW.WAIT))
        self.assertLess(names.index(AW.WAIT), names.index(AW.DEPLOY))
        subnet, deploy = AW.code_of(AW.SUBNET), AW.code_of(AW.DEPLOY)
        self.assertEqual(subnet.count("az-deploy.py create"), 1)
        self.assertEqual(deploy.count("az-deploy.py create"), 1)
        self.assertIn("--template environment/aigateway/subnet.bicep", subnet)
        self.assertNotIn("main.bicep", subnet, "the subnet's step makes no gateway")
        self.assertIn("--template environment/aigateway/main.bicep", deploy)
        self.assertNotIn("subnet.bicep", deploy, "the gateway's step makes no subnet")
        self.assertLess(WORKFLOW.index("--template environment/aigateway/subnet.bicep --parameters"), WORKFLOW.index("--template environment/aigateway/main.bicep --parameters"),
                        "in the file too, the deploy of the subnet is above the deploy of the gateway (the preview is above both and has no --parameters on the same line)")

    def test_a_fresh_sign_in_comes_between_the_wait_and_the_gateway_and_is_the_same_action_with_the_same_inputs_as_the_other(self):
        first, second = AW.step(AW.GATEWAY_LOGIN), AW.step(AW.LOGIN)
        self.assertEqual(first.split("\n", 1)[1], second.split("\n", 1)[1], "the same pinned action and the same three inputs: only the name differs")
        self.assertRegex(first, r"uses: azure/login@[0-9a-f]{40} # v3\.1\.0\n")
        for line in ("client-id: ${{ secrets.AZURE_CLIENT_ID }}", "tenant-id: ${{ secrets.AZURE_TENANT_ID }}", "subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}", "if: inputs.action == 'aigateway'"):
            self.assertIn(line, first, line)
        names = self.names()
        self.assertEqual(names[names.index(AW.WAIT) + 1], AW.GATEWAY_LOGIN, "the sign-in follows the wait at once")
        self.assertEqual(names[names.index(AW.GATEWAY_LOGIN) + 1], AW.DEPLOY, "and the gateway's deploy follows the sign-in at once")
        self.assertIn("because the subnet's deploy and the wait for the route table can take up to 25 minutes and the first sign-in's credential lasts five minutes", AW.GATEWAY_LOGIN)
        self.assertEqual(len(set(re.findall(r"uses: azure/login@([0-9a-f]{40})", WORKFLOW))), 1, "one pin of the action for every sign-in")
        self.assertEqual(names[names.index(AW.DEPLOY) + 1], AW.LOGIN, "the sign-in for the limits, the key and the read-back is still after the gateway's deploy")

    def test_the_wait_keeps_its_logic_and_says_that_the_gateway_is_not_made_yet_and_on_a_timeout_that_it_was_not_made(self):
        block, code = AW.step(AW.WAIT), AW.code_of(AW.WAIT)
        for word in ("        timeout-minutes: 25\n", "attempts=40", "sleep 30", "reference=$(table_of snet-pe)", "table=$(table_of snet-aigw)", "api-version=2025-05-01", "--query properties.routeTable.id"):
            self.assertIn(word, block, word)
        comment = re.sub(r"\s*\n\s*#\s*", " ", block)
        self.assertIn("The gateway is not made yet: it is made on the subnet as the landing zone leaves it, and not while the network manager is still writing to the subnet, because the service takes the subnet "
                      "when the gateway is made and treats it as read-only afterwards.", comment)
        self.assertIn("::error::The landing zone's network manager has put a route table on snet-pe and has not put one on snet-aigw in 20 minutes. The gateway was not made, because it is made on the subnet as "
                      "the landing zone leaves it. Nothing else was changed: run aigateway again later, which repeats only what is missing.", code)
        self.assertNotIn("The gateway may have no way out and no DNS", block, "the old text, which said that the gateway was made")

    def test_the_subnet_step_runs_for_this_action_alone_reads_the_flag_of_the_network_step_and_changes_nothing_but_the_subnet_template(self):
        block, code = AW.step(AW.SUBNET), AW.code_of(AW.SUBNET)
        self.assertIn("        if: inputs.action == 'aigateway'\n", block)
        self.assertIn("AIGW_SUBNET_EXISTS: ${{ steps.network.outputs.aigw_subnet_exists }}", block)
        self.assertIn('if [ "$AIGW_SUBNET_EXISTS" = true ]; then', code)
        self.assertEqual(re.findall(r"python3 tools/(\S+) (\w+)", code), [("az-deploy.py", "create")])
        self.assertNotRegex(code, r"--method (put|patch|post|delete)")
        for word in ("az role", "az network", "az resource", "az group", "az rest", "listKeys", "--yes"):
            self.assertNotIn(word, code, word)
        for word in ('--parameters "$RUNNER_TEMP/aigateway-subnet.parameters.json"', '--name "aigateway-subnet-$GITHUB_RUN_ID"', "--output subnetName", 'if [ "$name" != snet-aigw ]; then'):
            self.assertIn(word, code, word)
        comment = re.sub(r"\s*\n\s*#\s*", " ", block)
        self.assertIn("The subnet is made once and never undone (AGENTS.md rule 27)", comment)

    def test_the_network_step_still_reads_whether_the_subnet_is_there_and_the_settings_step_checks_both_files(self):
        network = AW.step("Find out what of the network is there already")
        self.assertIn('echo "aigw_subnet_exists=$aigw" >> "$GITHUB_OUTPUT"', network)
        params = AW.step("Work out the settings")
        self.assertIn("ENV_AIGW_SUBNET_EXISTS: ${{ steps.network.outputs.aigw_subnet_exists }}", params)
        self.assertIn('if [ -f "$RUNNER_TEMP/aigateway.parameters.json" ]; then\n'
                      '            python3 tools/environment-params.py check --params "$RUNNER_TEMP/aigateway.parameters.json" --template "$RUNNER_TEMP/aigateway.json" --label aigateway\n'
                      '            python3 tools/environment-params.py check --params "$RUNNER_TEMP/aigateway-subnet.parameters.json" --template "$RUNNER_TEMP/aigateway-subnet.json" --label aigateway-subnet\n'
                      "          fi", params)
        self.assertIn("# The AI Gateway's two files are there only when the virtual network has a free range for its subnet", params)

    def test_both_workflows_compile_lint_and_check_the_new_template_and_its_file(self):
        for source in (WORKFLOW, CHECKS):
            self.assertIn("environment/operator/main.bicep environment/aigateway/main.bicep environment/aigateway/subnet.bicep", source)
        self.assertIn('az bicep build --file environment/aigateway/subnet.bicep --outfile "$RUNNER_TEMP/aigateway-subnet.json"', WORKFLOW)
        self.assertIn('az bicep build --file environment/aigateway/subnet.bicep --outfile "$out/aigateway-subnet.json"', CHECKS)
        self.assertIn('python tools/environment-params.py check --params "$out/aigateway-subnet.parameters.json" --template "$out/aigateway-subnet.json" --label aigateway-subnet', CHECKS)

    def test_the_description_of_the_action_says_the_order(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        gateway = description.split(" aigateway: ")[1].split(" aigateway-check: ")[0]
        for words in ("first its subnet, which is delegated to it and made only when it is not there, and, after the landing zone's route table is on that subnet, the gateway with a system-assigned identity",
                      "The gateway is made on the subnet as the landing zone leaves it, so the action makes the subnet, waits for the landing zone's route table on it (20 minutes at most: when the table does "
                      "not come the gateway is not made, and a second run repeats only what is missing), signs in again and then makes the gateway.",
                      "After the deploy the action applies the gateway-wide token, request and cost limits"):
            self.assertIn(words, gateway, words)
        self.assertLess(gateway.index("first its subnet"), gateway.index("waits for the landing zone's route table"))
        self.assertLess(gateway.index("waits for the landing zone's route table"), gateway.index("then makes the gateway"))

    def test_the_preview_shows_the_subnet_first_and_then_the_gateway_and_each_says_why_it_cannot_be_previewed(self):
        preview = AW.step(PREVIEW)
        first = preview.index("::group::The AI Gateway's subnet, in the project's resource group")
        second = preview.index("::group::The AI Gateway, in the project's resource group")
        self.assertLess(first, second)
        subnet, gateway = preview[first:second], preview[second:]
        for word in ("The AI Gateway's subnet cannot be previewed: the virtual network has no free range for it", "The AI Gateway's subnet cannot be previewed yet: it goes into the virtual network",
                     '--template environment/aigateway/subnet.bicep --parameters "$RUNNER_TEMP/aigateway-subnet.parameters.json"', 'if [ ! -f "$RUNNER_TEMP/aigateway-subnet.parameters.json" ]; then'):
            self.assertIn(word, subnet, word)
        self.assertNotIn("foundry_found", subnet, "the subnet needs neither the Foundry resource nor the Operator")
        self.assertNotIn("environment/aigateway/main.bicep", subnet)
        self.assertIn('--template environment/aigateway/main.bicep --parameters "$RUNNER_TEMP/aigateway.parameters.json"', gateway)
        self.assertNotIn("subnet.bicep", gateway)
        self.assertIn("the gateway, its models and aliases and its roles, which the action makes after the subnet above carries the landing zone's route table", gateway)
        self.assertEqual(preview.count("az-deploy.py what-if"), preview.count("--template "), "every group of the preview is one call of the tool")
        self.assertNotRegex(subnet + gateway, r"--method (put|patch|post|delete)")
        self.assertLess(preview.index("::group::The Operator, in the project's resource group"), first, "the groups of the other templates are where they were: the AI Gateway's come last")

    def test_every_other_action_still_has_the_steps_that_it_had(self):
        counts = {action: len(re.findall(rf"inputs\.action == '{action}'", WORKFLOW)) for action in ("aigateway", "aigateway-check")}
        self.assertEqual(counts, {"aigateway": 10, "aigateway-check": 4}, "the nine steps of the action and the guard before them")
        self.assertEqual(WORKFLOW.count("uses: azure/login@"), 9, "the first sign-in and eight more: the one that this change adds is one of them")


BASH = AW.BASH
TABLE = f"{AW.GROUP_SCOPE}/providers/Microsoft.Network/routeTables/rt-landing-zone"
PYTHON3 = """#!/bin/bash
echo "python3 $*" >> "$FAKE_LOG"
if [ -n "$FAKE_FAIL_ON" ] && [[ "$*" == *"$FAKE_FAIL_ON"* ]]; then echo "ERROR: the deployment failed" >&2; exit 1; fi
case "$*" in
  *"--template environment/aigateway/subnet.bicep"*) printf '%s' "${FAKE_SUBNET_NAME:-snet-aigw}" ;;
  *"--template environment/aigateway/main.bicep"*) printf '%s' "$FAKE_GATEWAY" ;;
esac
"""
AZ = """#!/bin/bash
case "$*" in
  *"/subnets/snet-pe?"*) printf '%s' "$FAKE_PE_TABLE" ;;
  *"/subnets/snet-aigw?"*)
    n=$(cat "$FAKE_DIR/count" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$FAKE_DIR/count"
    echo "read snet-aigw $n" >> "$FAKE_LOG"
    if [ "$n" -ge "$FAKE_AFTER" ]; then printf '%s' "$FAKE_AIGW_TABLE"; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
SLEEP = 'sleep() { echo "sleep $*" >> "$FAKE_LOG"; }\n'
CHAIN = [AW.SUBNET, AW.WAIT, AW.DEPLOY]


def run_steps(names, env):
    """Runs the `run:` scripts of the steps one after another, each in a process of its own as the runner does, in one folder with the same stand-ins and the same log, and stops at the first step that fails:
    a step after a failed one does not run, because none of these steps has `if: always()`. Returns what each step that ran gave (its name, its exit code and its output) and the lines that the stand-ins logged."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for command, body in {"python3": PYTHON3, "az": AZ}.items():
            path = bin_dir / command
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        for file in ("log.txt", "out.txt", "summary.md"):
            (tmp / file).write_text("", encoding="utf-8")
        full = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": (tmp / "log.txt").as_posix(), "FAKE_DIR": tmp.as_posix(),
                "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(), "GITHUB_STEP_SUMMARY": (tmp / "summary.md").as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env}
        ran = []
        for name in names:
            script = tmp / "step.sh"
            script.write_text(SLEEP + AW.script_of(name), encoding="utf-8", newline="\n")
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=full, cwd=ROOT)
            ran.append((name, done.returncode, done.stdout))
            if done.returncode != 0:
                break
        return ran, (tmp / "log.txt").read_text(encoding="utf-8").splitlines()


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheStepsRunInThatOrderAndTheGatewayIsNotMadeWhenTheTableDoesNotCome(unittest.TestCase):
    ENV = {"ENV_SUBSCRIPTION_ID": AW.SUBSCRIPTION, "ENV_RESOURCE_GROUP": AW.GROUP, "GITHUB_RUN_ID": "12345", "EXPECTED_NAME": AW.GATEWAY, "FAKE_GATEWAY": AW.GATEWAY, "AIGW_SUBNET_EXISTS": "false",
           "FAKE_PE_TABLE": TABLE, "FAKE_AIGW_TABLE": TABLE, "FAKE_AFTER": "1"}

    def run_chain(self, **changes):
        ran, lines = run_steps(CHAIN, {**self.ENV, **changes})
        return [(name, code) for name, code, _ in ran], {name: out for name, _, out in ran}, lines

    def test_a_subnet_that_is_not_there_is_made_then_waited_for_then_the_gateway_is_made_in_that_order(self):
        ran, said, lines = self.run_chain(FAKE_AFTER="3")
        self.assertEqual(ran, [(AW.SUBNET, 0), (AW.WAIT, 0), (AW.DEPLOY, 0)])
        self.assertEqual(len(lines), 7, lines)
        self.assertIn("--template environment/aigateway/subnet.bicep", lines[0])
        self.assertIn("--name aigateway-subnet-12345", lines[0])
        self.assertIn("aigateway-subnet.parameters.json", lines[0])
        self.assertEqual(lines[1:6], ["read snet-aigw 1", "sleep 30", "read snet-aigw 2", "sleep 30", "read snet-aigw 3"], "the table is read until it is there")
        self.assertIn("--template environment/aigateway/main.bicep", lines[6], "and only then is the gateway made")
        self.assertIn("--name aigateway-12345", lines[6])
        self.assertIn(f"The subnet snet-aigw is in resource group {AW.GROUP}. The gateway is made after the landing zone's route table is on it.", said[AW.SUBNET])
        self.assertIn("The landing zone added the route table rt-landing-zone to the subnet snet-aigw.", said[AW.WAIT])
        self.assertIn(f"The AI Gateway {AW.GATEWAY} is in resource group {AW.GROUP}.", said[AW.DEPLOY])

    def test_a_route_table_that_never_comes_stops_the_run_at_the_wait_and_the_gateway_is_not_made(self):
        ran, said, lines = self.run_chain(FAKE_AFTER="100000")
        self.assertEqual(ran, [(AW.SUBNET, 0), (AW.WAIT, 1)], "the gateway's step does not run")
        self.assertEqual((lines.count("sleep 30"), len([line for line in lines if line.startswith("read snet-aigw")])), (39, 40), "40 checks half a minute apart: twenty minutes")
        self.assertEqual(len([line for line in lines if line.startswith("python3")]), 1, "only the subnet was deployed")
        self.assertFalse([line for line in lines if "main.bicep" in line], "the gateway's template was never deployed")
        self.assertIn("The gateway was not made, because it is made on the subnet as the landing zone leaves it. Nothing else was changed: run aigateway again later, which repeats only what is missing.", said[AW.WAIT])

    def test_a_subnet_that_is_there_is_left_alone_and_the_wait_and_the_gateway_follow(self):
        ran, said, lines = self.run_chain(AIGW_SUBNET_EXISTS="true")
        self.assertEqual(ran, [(AW.SUBNET, 0), (AW.WAIT, 0), (AW.DEPLOY, 0)])
        self.assertIn("The subnet snet-aigw is in Azure already: it is left alone, with everything that the landing zone added to it (AGENTS.md rule 27).", said[AW.SUBNET])
        self.assertFalse([line for line in lines if "subnet.bicep" in line], "no deploy of the subnet's template")
        self.assertEqual(lines[0], "read snet-aigw 1", "the first thing that is done is the wait: it finds the table that is there")
        self.assertIn("--template environment/aigateway/main.bicep", lines[1])
        self.assertEqual(len(lines), 2, lines)

    def test_a_network_whose_landing_zone_puts_no_table_on_its_subnets_waits_for_nothing_and_still_makes_the_subnet_first(self):
        ran, said, lines = self.run_chain(FAKE_PE_TABLE="")
        self.assertEqual(ran, [(AW.SUBNET, 0), (AW.WAIT, 0), (AW.DEPLOY, 0)])
        self.assertIn("The endpoint subnet carries no route table, so the landing zone puts none on this network: there is nothing to wait for.", said[AW.WAIT])
        self.assertEqual(len(lines), 2, lines)
        self.assertIn("subnet.bicep", lines[0])
        self.assertIn("main.bicep", lines[1])

    def test_a_deploy_of_the_subnet_that_fails_stops_the_run_before_the_wait_and_the_gateway(self):
        ran, said, lines = self.run_chain(FAKE_FAIL_ON="subnet.bicep")
        self.assertEqual(ran, [(AW.SUBNET, 1)])
        self.assertEqual(len(lines), 1, lines)

    def test_a_subnet_with_another_name_stops_the_run_and_says_that_the_gateway_was_not_made(self):
        ran, said, lines = self.run_chain(FAKE_SUBNET_NAME="snet-other")
        self.assertEqual(ran, [(AW.SUBNET, 1)])
        self.assertIn("::error::The deployment made the subnet snet-other, not snet-aigw, which is the name that the gateway's template and the read-back use. The gateway was not made.", said[AW.SUBNET])
        self.assertEqual(len(lines), 1, lines)

    def test_a_gateway_that_the_deploy_does_not_name_as_expected_fails_its_step_as_before(self):
        ran, said, _ = self.run_chain(FAKE_GATEWAY="aigw-another-name")
        self.assertEqual(ran, [(AW.SUBNET, 0), (AW.WAIT, 0), (AW.DEPLOY, 1)])
        self.assertIn(f"::error::The deployment made the AI Gateway aigw-another-name, not {AW.GATEWAY}, which is the name that the later steps read back. Nothing else was changed.", said[AW.DEPLOY])

    def test_the_subnet_is_deployed_with_the_template_the_file_and_the_name_that_the_workflow_gives_it(self):
        done, lines, _, tmp = AW.run_script(AW.SUBNET, {"python3": AW.python_stand_in("snet-aigw")}, {**self.ENV})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([line[len("arg:"):] for line in lines if line.startswith("arg:")],
                         ["tools/az-deploy.py", "create", "--subscription", AW.SUBSCRIPTION, "--resource-group", AW.GROUP, "--template", "environment/aigateway/subnet.bicep",
                          "--parameters", f"{tmp}/aigateway-subnet.parameters.json", "--name", "aigateway-subnet-12345", "--output", "subnetName"])


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheSummaryAndTheDescriptionSayItInPlainWords(unittest.TestCase):
    def summary(self, status):
        env = {"ACTION": "aigateway", "JOB_STATUS": status, "ENV_RESOURCE_GROUP": AG.GROUP, "AIGATEWAY_NAME": AG.GATEWAY, "FOUNDRY_ACCOUNT": AG.ACCOUNT, "FOUNDRY_PROJECT": AG.PROJECT,
               "FOUNDRY_ENDPOINT": "https://example", "ACCOUNT_NAME": "x", "CONTRACT_NAME": "y", "GITHUB_RUN_ID": "1"}
        done, _, _, written = AG.run_step(AG.SUMMARY, {}, env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return flat(written)

    def test_a_stop_lists_what_may_exist_subnet_first_and_says_what_each_place_of_stopping_means(self):
        said = self.summary("failure")
        for words in ("Part of the AI Gateway may exist now: the subnet `snet-aigw` with its network security group (made first, and only when it was not there), and then the gateway "
                      f"`{AG.GATEWAY}` with its own identity, its provider, its models and aliases, and two roles.",
                      "If the lines stop before the subnet is made, nothing was changed:",
                      "If the subnet's deploy failed, the lines say why (for example that the range is taken) and the gateway was not made.",
                      "If the lines stop at the wait for the landing zone's route table, the subnet exists and the gateway is not made, because it is made on the subnet as the landing zone leaves it: "
                      "nothing else was done, and running `aigateway` again later leaves the subnet alone and repeats only what is missing.",
                      "If the deploy of the gateway was refused at a role, the condition does not list that role.", "If they stop at the limits, the key or the read-back, the gateway is made",
                      "the subnet cannot be changed once the gateway is made (the way back is to delete the gateway and make another)", "The frontend of the gateway is public and cannot be made private."):
            self.assertIn(words, said, words)
        places = [said.index(words) for words in ("stop before the subnet is made", "the subnet's deploy failed", "stop at the wait for the landing zone's route table", "refused at a role", "stop at the limits")]
        self.assertEqual(places, sorted(places), "in the order of the steps")
        self.assertNotIn("the gateway is made and nothing else was done", said, "the old text: the gateway is not made when the run stops at the wait")

    def test_a_success_says_that_the_gateway_was_made_after_the_subnet_and_after_the_route_table(self):
        said = self.summary("success")
        for words in ("It was made after the subnet: the action made the subnet first (or found it and left it alone), waited until the landing zone had put its route table on it, and only then made the gateway, "
                      "so the gateway was made on the subnet as the landing zone left it.", "its backend subnet is `snet-aigw` (delegated to Microsoft.App/environments, with the landing zone's route table on it "
                      "when the landing zone puts one on this network)", "THE FRONTEND OF THE GATEWAY IS PUBLIC."):
            self.assertIn(words, said, words)


class TheDocumentsSayWhatTheActionDoes(unittest.TestCase):
    def record_section(self):
        return RECORD.split(RECORD_SECTION)[1].split("\n## ")[0]

    def test_the_record_has_the_section_after_the_one_on_the_subnet_that_cannot_be_changed_and_before_step_2(self):
        headings = re.findall(r"(?m)^## (.*)$", RECORD)
        order = ["The subnet cannot be changed", "The subnet is made first, and the gateway after the landing zone's route table", "Step 2 and what is not known about it"]
        positions = [headings.index(heading) for heading in order]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(positions[1], positions[0] + 1)
        self.assertEqual(positions[2], positions[1] + 1)

    def test_the_section_says_why_the_order_and_has_a_table_of_what_each_stop_means(self):
        section = self.record_section()
        flat_section = flat(section)
        for words in ("after 70 seconds the first time and after four minutes and 36 seconds the second, for the subnet of the first cases", "the subnet is treated as fixed afterwards",
                      "Made in one deployment, the gateway would be created while the network manager is still writing to its subnet.", "(that risk is not verified here)",
                      "So the first creation of the gateway has to see the subnet as the landing zone leaves it.", "[Rule 27](../../AGENTS.md) is the precedent: a template makes a subnet once and never undoes what the landing zone added to it.",
                      "The action `aigateway` therefore uses two templates, each with a parameter file of its own.", "In one template the wait for the route table could only have come after the gateway.",
                      "**The subnet exists and the gateway is not made.** Nothing else was changed. Run `aigateway` again later: it leaves the subnet alone and repeats only what is missing",
                      "A subnet that was made and has no gateway (the run stopped at the wait) costs nothing, and the next run uses it.",
                      "a person deletes it and its network security group by hand first, and no action does it."):
            self.assertIn(words, flat_section, words)
        rows = [line.split("|")[1].strip() for line in section.splitlines() if line.startswith("| ") and not line.startswith("| Step of")]
        self.assertEqual(rows, ["Early checks", "Make the subnet", "Wait for the route table", "Sign in again", "Make the gateway", "Limits, built-in key, read-back"], "the steps of the action, in their order")

    def test_the_record_lists_both_templates_and_the_order_in_the_action(self):
        flat_record = flat(RECORD)
        for words in ("Step 1 of 2 is deployed and checked: the two templates, the workflow actions, the check tool and the numbers were used on 2026-11-07", "- **The template of the subnet** [`environment/aigateway/subnet.bicep`]",
                      "- **The template of the gateway** [`environment/aigateway/main.bicep`]", "the template names the subnet and does not make it, so the subnet has to be there when the template is deployed.",
                      "It makes the subnet (when it is not there), waits until the landing zone has put its route table on the subnet and says which one, signs in again, makes the gateway, signs in again, applies the limits",
                      "Inside `aigateway` the subnet comes first, then the wait for the landing zone's route table, then the gateway",
                      "A run that stopped at the wait for the route table has made the subnet and not the gateway: the subnet stays, costs nothing, and the next run of `aigateway` makes the gateway on it.",
                      "- The subnet is made first and alone, and the gateway only after the landing zone's route table is on it (20 minutes at most)."):
            self.assertIn(words, flat_record, words)

    def test_the_row_about_the_network_security_group_says_that_the_samples_rules_are_allow_rules_and_change_nothing(self):
        (row,) = [line for line in RECORD.splitlines() if line.startswith("| The portal needs no network security group rule for that subnet")]
        for words in ("the private networking sample (`infra/private-network.bicep`)", "The sample's two rules are Allow rules, and it has no deny rule, so beside the default rules of a network security group, "
                      "which allow outbound traffic, they change nothing: none is made here."):
            self.assertIn(words, row, words)
        self.assertNotRegex(row, r"(?i)\blabs?\b", "a live document never says that word (rule 11 (c))")

    def test_the_bootstrap_page_has_the_order_with_the_subnet_first_and_what_a_stop_at_the_wait_means(self):
        section = BOOTSTRAP.split(BOOTSTRAP_SECTION)[1].split("\n## ")[0]
        order = flat(section.split("**The order.**")[1].split("**Going back.**")[0])
        for words in ("(3) `what-if`, which now shows the subnet and then the gateway (two lists) once the Foundry resource and the Operator exist, and then `aigateway`.",
                      "Then it makes the subnet (only when it is not there: a subnet that is there is left alone, with what the landing zone added to it), waits for the landing zone's route table on the subnet "
                      "(20 minutes at most), signs in again, and only then makes the gateway, so that the gateway is made on the subnet as the landing zone leaves it.",
                      "If it stops at the wait, the subnet exists and the gateway is not made: nothing else was changed, and a later run of `aigateway` leaves the subnet alone and repeats only what is missing.",
                      "About ten minutes later, because a new role takes up to that long to apply, `aigateway-check`."):
            self.assertIn(words, order, words)
        positions = [order.index(f"`{name}`") for name in ("foundry", "cases", "operator", "aigateway")] + [order.index("`aigateway-check`")]
        self.assertEqual(positions, sorted(positions), "foundry, cases and operator, then aigateway, then aigateway-check")
        going_back = flat(section.split("**Going back.**")[1].split("**Costs.**")[0])
        self.assertIn("A run that stopped at the wait has made the subnet and no gateway: the subnet costs nothing and the next run uses it, and to make it again a person deletes it and its network security group by hand.", going_back)
        self.assertIn("No action deletes the gateway", going_back)
        self.assertIn("the templates [`environment/aigateway/subnet.bicep`](aigateway/subnet.bicep) (the subnet, made first) and [`environment/aigateway/main.bicep`](aigateway/main.bicep) (the gateway, made after "
                      "the landing zone's route table is on the subnet)", flat(section))

    def test_the_readme_lists_both_templates(self):
        (bullet,) = [line for line in README.splitlines() if line.startswith("- **An AI Gateway for the agents' model calls")]
        self.assertIn("Built: the templates [`environment/aigateway/subnet.bicep`](environment/aigateway/subnet.bicep) (its subnet, made first) and [`environment/aigateway/main.bicep`](environment/aigateway/main.bicep) "
                      "(the gateway, made after the landing zone's route table is on the subnet)", bullet)

    def test_the_rules_are_unchanged_because_nothing_in_them_became_untrue(self):
        agents = text("AGENTS.md")
        self.assertIn("27. **A template makes a subnet once, and never undoes what the landing zone added to it**", agents)
        self.assertIn("So a template makes a subnet only while it is not there (the workflow reads that from Azure and passes it, as `webSubnetExists` does) and names it by its id afterwards", agents)

    def test_the_changelog_has_the_entry_below_the_one_of_the_deployment_and_says_what_it_must(self):
        headings = re.findall(r"(?m)^## (.*)$", CHANGELOG)
        self.assertEqual(headings[3], ENTRY)
        self.assertTrue(headings[4].startswith("An AI Gateway for the agents' model calls, step 2 of 2"), "the entries of the two steps follow")
        entry = CHANGELOG.split("\n## ")[4]
        leads = ["**What was found.**", "**What changed.**", "**What was checked.**", "**Not checked.**", "**Who decides, and what a person does.**"]
        positions = [entry.index(lead) for lead in leads]
        self.assertEqual(positions, sorted(positions))
        flat_entry = flat(entry)
        for words in ("The action `aigateway` made the subnet `snet-aigw` and the gateway in one deployment, and its wait for the landing zone's route table came after the gateway was made.",
                      "70 seconds the first time and four minutes and 36 seconds the second", "treats it as read-only afterwards", "a risk that was named and is not verified here",
                      "[Rule 27](AGENTS.md) is the precedent", "Nothing here was found by a run: the action has not been run.", "**Two templates and two parameter files.**", "**The order in `aigateway`.**",
                      "Then **make the subnet**", "Then **wait** for the route table", "Then a **new sign-in**", "Then **make the gateway**", "`what-if` previews the subnet's template and then the gateway's.",
                      "That was wrong", "(seven became nine)", "(eight became nine)", "`aigateway.parameters.json` was re-recorded because two parameters moved out of it, and `aigateway-subnet.parameters.json` is new",
                      "every other golden file and the golden output are as they were", "None of it has run: no Azure change and no workflow run was made.",
                      "whether the service takes a gateway on a subnet that already carries the landing zone's route table", "Nothing that is priced is added",
                      "A run that stops at the wait leaves the subnet and no gateway, which costs nothing, and the next run uses the subnet."):
            self.assertIn(words, flat_entry, words)
        for placeholder in ("TOOLS_TOTAL", "TOOLS_NEW", "NNNN"):
            self.assertNotIn(placeholder, flat_entry, "the line about what was checked is written")
        self.assertRegex(flat_entry.split("**What was checked.**")[1].split("**Not checked.**")[0], r"\d,\d{3} tests", "and it says how many tests passed")

    def test_nothing_of_the_owners_environment_is_in_what_this_change_wrote(self):
        entry = CHANGELOG.split("\n## ")[4]
        for label, part in (("the template of the subnet", SUBNET), ("the section of the record", self.record_section()), ("the entry", entry)):
            self.assertNotRegex(part, r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", f"{label}: no id")
        for label, part in (("the section of the record", self.record_section()), ("the entry", entry)):
            self.assertNotRegex(part, r"[\w.+-]+@[\w-]+\.[\w.]+", f"{label}: no e-mail address")
            self.assertNotRegex(part, r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", f"{label}: no address of the estate")


if __name__ == "__main__":
    unittest.main()
