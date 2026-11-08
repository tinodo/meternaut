"""The AI Gateway's template (environment/aigateway/main.bicep): what it makes, what it leaves out, and what its comments say about the public frontend.

The resource types of the template are pinned with the other templates' in test_environment_template.py (AGENTS.md rule 19). The subnet that the gateway needs is not made here: its template
(environment/aigateway/subnet.bicep), and the order of the steps of the action that deploys the two, are tested in test_aigateway_subnet_first.py. The parameter and policy files that the builder
makes for them are tested in test_environment_params.py, the check tool in test_aigateway_check.py, and the other steps of the workflow action in test_aigateway_workflow.py."""
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
            "account": "Microsoft.CognitiveServices/accounts",
            "operatorIdentity": "Microsoft.ManagedIdentity/userAssignedIdentities",
            "gateway": "Microsoft.ApiManagement/aigateways",
            "workspace": "Microsoft.ApiManagement/aigateways/workspaces",
            "gatewayCallsFoundry": "Microsoft.Authorization/roleAssignments",
            "foundryProvider": "Microsoft.ApiManagement/aigateways/workspaces/modelProviders",
            "modelOfProvider": "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models",
            "aliasOfModel": "Microsoft.ApiManagement/aigateways/workspaces/aliases",
            "operatorCallsTheModels": "Microsoft.Authorization/roleAssignments",
            "projectCallsTheModels": "Microsoft.Authorization/roleAssignments",
            "casesCallsTheModels": "Microsoft.Authorization/roleAssignments",
        })
        for name in ("account", "operatorIdentity", "workspace"):
            self.assertRegex(SOURCE, rf"(?m)^resource {name} '[^']+' existing = \{{$", f"{name} is only read: another template or the service makes it")

    def test_the_frontend_is_public_the_header_says_so_and_nothing_asks_for_a_private_one(self):
        header = re.sub(r"\s*\n//\s*", " ", SOURCE.split("targetScope", 1)[0])
        self.assertIn("THE FRONTEND IS PUBLIC, AND NO TEMPLATE CAN CHANGE THAT", header)
        for word in ("Private endpoints aren't supported", "has no effect", "Microsoft Entra ID", "role assignments", "master"):
            self.assertIn(word, header, word)
        self.assertEqual(re.findall(r"publicNetworkAccess: '(\w+)'", CODE), ["Enabled"], "the only value that has an effect; the service ignores Disabled")
        for word in ("privateEndpoints", "privateLinkServiceConnections", "privateDnsZone", "virtualNetworkLinks", "ddos", "ipFilter", "apiKeys", "listKeys", "firewall", "routeTable"):
            self.assertNotIn(word.lower(), CODE.lower(), f"{word}: no private endpoint, no DNS object (rule 19), no DDoS plan, no IP filter without values, no key resource (rule 23)")

    def test_it_makes_no_network_resource_takes_no_setting_of_the_subnet_and_says_in_its_header_where_the_subnet_comes_from(self):
        for word in ("Microsoft.Network/virtualNetworks@", "Microsoft.Network/networkSecurityGroups@", "Microsoft.Network/virtualNetworks/subnets@", "networkSecurityGroup:", "delegations:", "addressPrefix"):
            self.assertNotIn(word, CODE, f"{word}: the subnet is made by environment/aigateway/subnet.bicep, before this template is deployed")
        self.assertNotRegex(CODE, r"(?m)^param aigwSubnet\w+ ", "no range and no flag of the subnet: the subnet's template takes them")
        self.assertNotIn("aigwSubnetExists", CODE)
        header = re.sub(r"\s*\n//\s*", " ", SOURCE.split("targetScope", 1)[0])
        for words in ("THE SUBNET IS NOT MADE HERE: it has to be there when this template is deployed.", "The template environment/aigateway/subnet.bicep makes it",
                      "the action aigateway deploys that one first, waits until the landing zone's network manager has put its route table on the subnet, and only then deploys this one",
                      "so that the gateway is made on the subnet as the landing zone leaves it"):
            self.assertIn(words, header, words)
        self.assertEqual(CODE.count("subnets"), 2, "the subnet is only named by its id: in the gateway's backend and in the output")

    def test_the_gateway_has_a_system_identity_and_its_backend_subnet_and_no_sku_no_key_and_no_policy(self):
        gateway = self.found["gateway"][1]
        for word in ("type: 'SystemAssigned'", "resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, aigwSubnetName)", "name: gatewayName"):
            self.assertIn(word, gateway, word)
        for word in ("sku", "policies", "apiKey", "ipFilter"):
            self.assertNotIn(word, gateway, word)
        self.assertEqual(depends_on(gateway), set(), "the subnet is not in this template: it is in Azure before the template is deployed, and the workflow waits for it")
        self.assertIn("@minLength(3)\n@maxLength(24)\nparam gatewayName string", CODE, "the service's limit")
        self.assertIn("var aigwSubnetName = 'snet-aigw'", CODE)

    def test_every_resource_of_the_service_is_at_one_api_version_and_each_has_its_own_suppression_of_the_missing_types(self):
        versions = re.findall(r"(?m)^resource \w+ 'Microsoft\.ApiManagement/aigateways[^'@]*@([^']+)'", CODE)
        self.assertEqual(versions, ["2025-09-01-preview"] * 5, "the version of the portal and of every sample of Microsoft; the service takes newer ones for the gateway only")
        self.assertEqual(len(re.findall(r"(?m)^#disable-next-line BCP081\nresource \w+ 'Microsoft\.ApiManagement/aigateways", SOURCE)), 5)
        self.assertEqual(len(re.findall(r"#disable", SOURCE)), 5, "no other rule is switched off")

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

    def test_the_cases_apps_identity_holds_ai_gateway_models_user_on_the_gateway_when_it_is_given_and_none_when_it_is_not(self):
        # Every model call of the Detective and the Skeptic goes through the gateway with the app's own identity (AGENTS.md rule 15 (c)).
        cases = self.found["casesCallsTheModels"][1]
        for word in ("if (!empty(casesPrincipalId))", "scope: gateway", "name: guid(gateway.id, casesPrincipalId, aiGatewayModelsUserRoleId)", "principalId: casesPrincipalId",
                     "principalType: 'ServicePrincipal'", "roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiGatewayModelsUserRoleId)"):
            self.assertIn(word, cases, word)
        self.assertRegex(CODE, r"(?m)^@maxLength\(36\)\nparam casesPrincipalId string = ''$", "empty means none: the app has no identity before the action cases has made it")
        self.assertEqual(len(re.findall(r"roleDefinitions', aiGatewayModelsUserRoleId", CODE)), 3, "the Operator, the Foundry project and the cases app hold the one role of the callers, and no other caller does")
        header = re.sub(r"\s*\n//\s*", " ", SOURCE.split("targetScope", 1)[0])
        for words in ("every model call of Meternaut goes through it, with no direct path", "for the cases app's identity when its principal id is given"):
            self.assertIn(words, header, words)

    def test_the_telemetry_exporter_is_not_in_this_template_any_more_and_the_gateway_template_holds_no_connection_string(self):
        # The exporter has prerequisites of its own (a registered resource provider, the component's OpenTelemetry endpoints, a role on a data collection rule that a person gives), and a missing
        # one makes the service refuse that one resource: it moved to environment/aigateway/telemetry.bicep, made by the action gateway-telemetry, so that it can never stop the gateway, its models
        # or its roles (docs/proposals/10-ai-security-and-governance.md). tools/tests/test_gateway_telemetry.py pins that template.
        for word in ("telemetryExporter", "telemetryEnabled", "telemetryComponentName", "OpenTelemetry", "payloadCapture", "Microsoft.Insights/components"):
            self.assertNotIn(word, CODE, word)
        self.assertIn("telemetry.bicep", re.sub(r"\s*\n//\s*", " ", SOURCE.split("targetScope", 1)[0]), "the header says where the exporter went")
        for word in ("connectionString", "ConnectionString", "instrumentationKey", "InstrumentationKey", "'ApplicationInsights'"):
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
            "Microsoft.ApiManagement/aigateways",
            "Microsoft.ApiManagement/aigateways/workspaces/modelProviders", "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models",
            "Microsoft.ApiManagement/aigateways/workspaces/aliases", "Microsoft.Authorization/roleAssignments"})
        self.assertEqual(set(compiled["outputs"]), {"gatewayName", "gatewayHost", "subnetId"})
        self.assertEqual({r["apiVersion"] for r in resources if r["type"].startswith("Microsoft.ApiManagement")}, {"2025-09-01-preview"})
