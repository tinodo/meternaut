"""The AI Gateway's template (environment/aigateway/main.bicep): what it makes, what it leaves out, and what its comments say about the public frontend.

The resource types of the template are pinned with the other templates' in test_environment_template.py (AGENTS.md rule 19). The parameter and policy files that the builder makes for it are
tested in test_environment_params.py, the check tool in test_aigateway_check.py, and the workflow actions in test_aigateway_workflow.py."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = "environment/aigateway/main.bicep"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def resources(source):
    """Symbolic name -> (type, body) of every top-level resource of a Bicep file, loops and conditions included."""
    found = {}
    pattern = r"^resource (\w+) '([^'@]+)@[^']+' (?:existing )?= (?:\[for [^\n]*\n)?\{?\n?(.*?)^(?:\}|\}\])\n"
    for match in re.finditer(pattern, source, re.M | re.S):
        found[match.group(1)] = (match.group(2), match.group(3))
    return found


def depends_on(body):
    match = re.search(r"^  dependsOn: \[\n(.*?)^  \]", body, re.M | re.S)
    return set(re.findall(r"\w+", match.group(1))) if match else set()


SOURCE = text(PATH)
# The comments are removed, but not the two slashes of a URL.
CODE = re.sub(r"(?<!:)//.*", "", SOURCE)

FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
MODELS_USER = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"


class Template(unittest.TestCase):
    def setUp(self):
        self.found = resources(SOURCE)

    def test_it_makes_and_reads_exactly_these_resources(self):
        self.assertEqual({name: kind for name, (kind, _) in self.found.items()}, {
            "vnet": "Microsoft.Network/virtualNetworks",
            "account": "Microsoft.CognitiveServices/accounts",
            "operatorIdentity": "Microsoft.ManagedIdentity/userAssignedIdentities",
            "aigwNsg": "Microsoft.Network/networkSecurityGroups",
            "aigwSubnet": "Microsoft.Network/virtualNetworks/subnets",
            "gateway": "Microsoft.ApiManagement/aigateways",
            "workspace": "Microsoft.ApiManagement/aigateways/workspaces",
            "gatewayCallsFoundry": "Microsoft.Authorization/roleAssignments",
            "foundryProvider": "Microsoft.ApiManagement/aigateways/workspaces/modelProviders",
            "modelOfProvider": "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models",
            "aliasOfModel": "Microsoft.ApiManagement/aigateways/workspaces/aliases",
            "operatorCallsTheModels": "Microsoft.Authorization/roleAssignments",
            "projectCallsTheModels": "Microsoft.Authorization/roleAssignments",
            "insights": "Microsoft.Insights/components",
            "telemetryExporter": "Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters",
        })
        for name in ("vnet", "account", "operatorIdentity", "workspace", "insights"):
            self.assertRegex(SOURCE, rf"(?m)^resource {name} '[^']+' existing = \{{$", f"{name} is only read: another template or the service makes it")

    def test_the_frontend_is_public_the_header_says_so_and_nothing_asks_for_a_private_one(self):
        header = re.sub(r"\s*\n//\s*", " ", SOURCE.split("targetScope", 1)[0])
        self.assertIn("THE FRONTEND IS PUBLIC, AND NO TEMPLATE CAN CHANGE THAT", header)
        for word in ("Private endpoints aren't supported", "has no effect", "Microsoft Entra ID", "role assignments", "master"):
            self.assertIn(word, header, word)
        self.assertEqual(re.findall(r"publicNetworkAccess: '(\w+)'", CODE), ["Enabled"], "the only value that has an effect; the service ignores Disabled")
        for word in ("privateEndpoints", "privateLinkServiceConnections", "privateDnsZone", "virtualNetworkLinks", "ddos", "ipFilter", "apiKeys", "listKeys", "firewall", "routeTable"):
            self.assertNotIn(word.lower(), CODE.lower(), f"{word}: no private endpoint, no DNS object (rule 19), no DDoS plan, no IP filter without values, no key resource (rule 23)")

    def test_the_subnet_is_made_once_is_delegated_and_the_security_group_has_no_rule_of_its_own(self):
        subnet = self.found["aigwSubnet"][1]
        self.assertIn("if (!aigwSubnetExists)", subnet, "made only while it is not there (rule 27)")
        for word in ("serviceName: 'Microsoft.App/environments'", "networkSecurityGroup:", "id: aigwNsg.id", "defaultOutboundAccess: false", "addressPrefix: aigwSubnetPrefix"):
            self.assertIn(word, subnet, word)
        self.assertEqual(re.findall(r"serviceName: '([^']+)'", subnet), ["Microsoft.App/environments"], "one delegation, and nothing else lives in the subnet")
        self.assertIn("securityRules: []", self.found["aigwNsg"][1])
        self.assertRegex(CODE, r"(?m)^@minLength\(9\)\n@maxLength\(18\)\nparam aigwSubnetPrefix string$", "no default: the builder chooses the range")
        self.assertRegex(CODE, r"(?m)^param aigwSubnetExists bool = false$")
        self.assertEqual(CODE.count("Microsoft.Network/virtualNetworks@"), 1, "the network is read, never made, here")

    def test_the_gateway_has_a_system_identity_and_its_backend_subnet_and_no_sku_no_key_and_no_policy(self):
        gateway = self.found["gateway"][1]
        for word in ("type: 'SystemAssigned'", "resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, aigwSubnetName)", "name: gatewayName"):
            self.assertIn(word, gateway, word)
        for word in ("sku", "policies", "apiKey", "ipFilter"):
            self.assertNotIn(word, gateway, word)
        self.assertEqual(depends_on(gateway), {"aigwSubnet"})
        self.assertIn("@minLength(3)\n@maxLength(24)\nparam gatewayName string", CODE, "the service's limit")
        self.assertIn("var aigwSubnetName = 'snet-aigw'", CODE)

    def test_every_resource_of_the_service_is_at_one_api_version_and_each_has_its_own_suppression_of_the_missing_types(self):
        versions = re.findall(r"(?m)^resource \w+ 'Microsoft\.ApiManagement/aigateways[^'@]*@([^']+)'", CODE)
        self.assertEqual(versions, ["2025-09-01-preview"] * 6, "the version of the portal and of every sample of Microsoft; the service takes newer ones for the gateway only")
        self.assertEqual(len(re.findall(r"(?m)^#disable-next-line BCP081\nresource \w+ 'Microsoft\.ApiManagement/aigateways", SOURCE)), 6)
        self.assertEqual(len(re.findall(r"#disable", SOURCE)), 6, "no other rule is switched off")

    def test_the_gateway_calls_the_foundry_resource_with_its_own_identity_through_a_provider_without_a_key(self):
        role = self.found["gatewayCallsFoundry"][1]
        for word in ("scope: account", "name: guid(account.id, gateway.id, foundryUserRoleId)", "principalId: gateway.identity.principalId", "principalType: 'ServicePrincipal'", "roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)"):
            self.assertIn(word, role, word)
        provider = self.found["foundryProvider"][1]
        for word in ("kind: 'Foundry'", "kind: 'ManagedIdentity'", "resource: 'https://cognitiveservices.azure.com/'", "resourceIds: [\n        account.id\n      ]"):
            self.assertIn(word, provider, word)
        self.assertIn("endsWith(account.properties.endpoint, '/')", provider, "the endpoint with its trailing slash, as the samples have it")
        self.assertNotIn("apiKey", provider)
        self.assertEqual(depends_on(provider), {"gatewayCallsFoundry"}, "the role first: the provider is read at once")
        self.assertIn("var providerName = 'foundry'", CODE)
        self.assertIn("name: providerName", provider)
        self.assertIn(f"var foundryUserRoleId = '{FOUNDRY_USER}'", CODE)

    def test_each_model_has_a_resource_a_content_safety_policy_at_medium_and_an_alias_with_the_deployments_name(self):
        model = self.found["modelOfProvider"][1]
        self.assertIn("name: replace(model.name, '.', '-')", model, "a resource name has no dots")
        self.assertRegex(CODE, r"(?m)^@batchSize\(1\)\n#disable-next-line BCP081\nresource modelOfProvider ", "one at a time")
        for word in ("apiFormat: 'OpenAIChatCompletions'", "modelName: model.name", "modelVersion: model.version", "resourceId('Microsoft.CognitiveServices/accounts/deployments', foundryAccountName, model.name)"):
            self.assertIn(word, model, word)
        self.assertEqual(re.findall(r"type: '(\w+)'", model), ["contentSafety"], "one policy on each model, and it is not Prompt Shields, which the gateway has not")
        for category in ("hateSeverity", "violenceSeverity", "sexualSeverity", "selfHarmSeverity"):
            self.assertEqual(len(re.findall(rf"{category}: contentSafetySeverity", model)), 1, category)
        self.assertIn("var contentSafetySeverity = 'Medium'", CODE)
        alias = self.found["aliasOfModel"][1]
        for word in ("name: model.name", "aliasName: model.name", "resourceId: modelOfProvider[index].id", "priority: 0", "weight: 1"):
            self.assertIn(word, alias, word)
        self.assertEqual(alias.count("resourceId:"), 1, "one target for each alias: no routing and no failover")
        self.assertRegex(CODE, r"(?m)^@batchSize\(1\)\n#disable-next-line BCP081\nresource aliasOfModel ", "the aliases are written one after another, like the models")
        self.assertEqual(depends_on(alias), {"modelOfProvider"}, "and only after every model is written: nothing of the gateway's configuration is written twice at once")
        comment = re.sub(r"\s*\n//\s*", " ", SOURCE)
        self.assertIn("are both the deployment's name, dots included: the specification allows dots in an alias's name (^[a-zA-Z0-9_.-]+$, where a model's name allows none)", comment,
                      "the template says why the alias resource keeps the dots and the model's does not")
        self.assertIn("'/openai/v1/chat/completions'", CODE, "the agents and the check use chat completions")

    def test_the_roles_are_the_two_of_the_plan_each_on_its_own_scope_and_never_on_the_group(self):
        ids = re.findall(r"= '([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'", CODE)
        self.assertEqual(ids, [FOUNDRY_USER, MODELS_USER], "Foundry User for the gateway, AI Gateway Models User for its callers: nothing that changes a resource")
        operator = self.found["operatorCallsTheModels"][1]
        for word in ("scope: gateway", "principalId: operatorIdentity.properties.principalId", "name: guid(gateway.id, operatorIdentity.id, aiGatewayModelsUserRoleId)", "principalType: 'ServicePrincipal'"):
            self.assertIn(word, operator, word)
        project = self.found["projectCallsTheModels"][1]
        for word in ("if (!empty(foundryProjectPrincipalId))", "scope: gateway", "principalId: foundryProjectPrincipalId", "aiGatewayModelsUserRoleId"):
            self.assertIn(word, project, word)
        for scope in re.findall(r"scope: (\S+)", CODE):
            self.assertIn(scope, ("account", "gateway"), "a role on the gateway or on the Foundry resource, never on the group or the subscription")
        self.assertIn(f"var aiGatewayModelsUserRoleId = '{MODELS_USER}'", CODE)
        self.assertRegex(CODE, r"(?m)^param foundryProjectPrincipalId string = ''$", "empty means none yet: the template works without it")

    def test_the_telemetry_is_off_by_default_sends_no_payload_and_has_no_connection_string(self):
        exporter = self.found["telemetryExporter"][1]
        self.assertIn("if (telemetryEnabled)", exporter)
        self.assertRegex(CODE, r"(?m)^param telemetryEnabled bool = false$")
        for word in ("kind: 'OpenTelemetry'", "payloadCapture: false", "resource: 'https://monitor.azure.com'", "managedIdentity:"):
            self.assertIn(word, exporter, word)
        self.assertNotIn("'ApplicationInsights'", CODE, "the kind that takes a connection string is not used (rule 23)")
        for word in ("connectionString", "ConnectionString", "instrumentationKey", "InstrumentationKey"):
            self.assertNotIn(word, CODE, word)

    def test_it_gives_the_workflow_the_name_the_host_and_the_subnet_and_nothing_else(self):
        self.assertEqual(re.findall(r"(?m)^output (\w+) ", CODE), ["gatewayName", "gatewayHost", "subnetId"])
        self.assertIn("output gatewayHost string = gateway.properties.frontend.defaultHostname", CODE, "the host name is read from the service and never constructed")

    def test_the_names_that_the_template_reads_are_the_ones_that_the_other_templates_make(self):
        self.assertIn("var virtualNetworkName = 'vnet-${workload}'", CODE)
        self.assertIn("name: 'vnet-${workload}'", text("environment/main.bicep"))
        self.assertIn("var operatorIdentityName = 'id-${workload}-operator'", CODE)
        self.assertIn("name: 'id-${workload}-operator'", text("environment/operator/main.bicep"))
        self.assertRegex(CODE, r"(?m)^param workload string = 'meternaut'$")
        foundry = text("environment/foundry/main.bicep")
        self.assertIn("param accountName string", foundry, "the name of the account is a parameter of the Foundry template, as it is of this one")
        self.assertRegex(foundry, r"name: model\.name", "the deployment is named as the model is in models.json, which is what the gateway's deployment id uses")

    def test_the_template_compiles_and_makes_what_it_says(self):
        python = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")
        az = [str(python), "-IBm", "azure.cli"] if python.exists() else ([shutil.which("az")] if shutil.which("az") else None)
        bicep = Path.home() / ".azure" / "bin" / ("bicep.exe" if python.exists() else "bicep")
        if az is None or not bicep.exists():
            self.skipTest("no Azure CLI with Bicep on this machine: the workflow and the checks compile every template")
        done = subprocess.run([*az, "bicep", "build", "--file", str(ROOT / "environment" / "aigateway" / "main.bicep"), "--stdout"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        compiled = json.loads(done.stdout)
        resources = compiled["resources"].values() if isinstance(compiled["resources"], dict) else compiled["resources"]
        self.assertEqual({r["type"] for r in resources}, {
            "Microsoft.Network/networkSecurityGroups", "Microsoft.Network/virtualNetworks/subnets", "Microsoft.ApiManagement/aigateways",
            "Microsoft.ApiManagement/aigateways/workspaces/modelProviders", "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models",
            "Microsoft.ApiManagement/aigateways/workspaces/aliases", "Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters", "Microsoft.Authorization/roleAssignments"})
        self.assertEqual(set(compiled["outputs"]), {"gatewayName", "gatewayHost", "subnetId"})
        self.assertEqual({r["apiVersion"] for r in resources if r["type"].startswith("Microsoft.ApiManagement")}, {"2025-09-01-preview"})
