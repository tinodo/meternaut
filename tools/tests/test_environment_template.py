import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Everything each template may create. AGENTS.md rule 19: in a landing zone no private DNS zone, no link to one and no
# zone group (a policy registers the endpoint's name), no peering or route by hand (the network manager does it), and
# no second API Management instance (the gateway objects go into the existing one by the kit's module).
ALLOWED = {
    "environment/main.bicep": {
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.CognitiveServices/accounts",
        "Microsoft.CognitiveServices/accounts/deployments",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Authorization/roleAssignments",
    },
    "environment/gateway/identity.bicep": {"Microsoft.ManagedIdentity/userAssignedIdentities"},
    "environment/gateway/logger.bicep": {"Microsoft.ApiManagement/service", "Microsoft.Insights/components", "Microsoft.ApiManagement/service/loggers"},
    "environment/gateway/eventhub-loggers.bicep": {"Microsoft.ApiManagement/service", "Microsoft.ApiManagement/service/loggers"},
    "environment/gateway/contract.bicep": {
        "Microsoft.ApiManagement/service",
        "Microsoft.ApiManagement/service/products",
        "Microsoft.ApiManagement/service/products/apis",
        "Microsoft.ApiManagement/service/products/policies",
        "Microsoft.ApiManagement/service/subscriptions",
    },
    "infra/budgets/rg-budget.bicep": {"Microsoft.Consumption/budgets"},
    "environment/recording/main.bicep": {
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Network/virtualNetworks/subnets",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.OperationalInsights/workspaces",
        "Microsoft.Insights/components",
        "Microsoft.Storage/storageAccounts",
        "Microsoft.Storage/storageAccounts/blobServices",
        "Microsoft.Storage/storageAccounts/blobServices/containers",
        "Microsoft.EventHub/namespaces",
        "Microsoft.EventHub/namespaces/eventhubs",
        "Microsoft.EventHub/namespaces/eventhubs/consumergroups",
        "Microsoft.Authorization/roleAssignments",
        "Microsoft.DocumentDB/databaseAccounts",
        "Microsoft.DocumentDB/databaseAccounts/sqlDatabases",
        "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers",
        "Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments",
        "Microsoft.Web/serverfarms",
        "Microsoft.Web/sites",
        "Microsoft.Web/sites/basicPublishingCredentialsPolicies",
    },
}


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def resources(source):
    """Symbolic name -> (type, body) of every top-level resource of a Bicep file, loops included."""
    found = {}
    pattern = r"^resource (\w+) '([^'@]+)@[^']+' (?:existing )?= (?:\[for [^\n]*\n)?\{?\n?(.*?)^(?:\}|\}\])\n"
    for match in re.finditer(pattern, source, re.M | re.S):
        found[match.group(1)] = (match.group(2), match.group(3))
    return found


def depends_on(body):
    match = re.search(r"^  dependsOn: \[\n(.*?)^  \]", body, re.M | re.S)
    return set(re.findall(r"\w+", match.group(1))) if match else set()


class Templates(unittest.TestCase):
    def test_only_the_resource_types_of_the_design_are_declared(self):
        for path, allowed in ALLOWED.items():
            declared = {m.group(1) for m in re.finditer(r"^resource \w+ '([^'@]+)@", text(path), re.M)}
            self.assertEqual(declared, allowed, path)

    def test_the_model_side_declares_no_gateway_object_and_no_dns(self):
        source = re.sub(r"//.*", "", text("environment/main.bicep"))
        for word in ("Microsoft.ApiManagement", "privateDnsZones", "virtualNetworkPeerings", "routeTables", "privateDnsZoneGroups"):
            self.assertNotIn(word, source, word)

    def test_the_model_side_has_the_resources_and_the_order_that_a_real_deploy_needed(self):
        found = resources(text("environment/main.bicep"))
        self.assertEqual(set(found), {"nsg", "funcNsg", "vnet", "account", "modelDeployment", "privateEndpoint", "gatewayMayCallTheModels"})
        # the private endpoint after every model deployment, the role assignment after the private endpoint
        self.assertIn("modelDeployment", depends_on(found["privateEndpoint"][1]))
        self.assertIn("privateEndpoint", depends_on(found["gatewayMayCallTheModels"][1]))

    def test_nothing_else_is_written_to_the_account_beside_the_private_endpoint(self):
        # The endpoint's connection is written to the account with an If-Match. Any other write to the account at the same
        # time makes it fail with IfMatchPreconditionFailed: a role assignment did, in an earlier deploy.
        found = resources(text("environment/main.bicep"))
        before = depends_on(found["privateEndpoint"][1])
        beside = []
        for name, (_, body) in found.items():
            if name != "privateEndpoint" and re.search(r"^  (parent|scope): account$", body, re.M):
                if name not in before and "privateEndpoint" not in depends_on(body):
                    beside.append(name)
        self.assertEqual(beside, [], f"{beside} would be written to the account while the private endpoint is")

    def test_the_account_is_private_and_has_no_keys(self):
        source = text("environment/main.bicep")
        self.assertIn("publicNetworkAccess: 'Disabled'", source)
        self.assertIn("disableLocalAuth: true", source)
        self.assertIn("versionUpgradeOption: 'NoAutoUpgrade'", source)

    def test_the_gateway_may_run_completions_and_nothing_more_on_the_account(self):
        source = text("environment/main.bicep")
        self.assertIn("var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'", source)
        self.assertEqual(len(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", source)), 1)
        self.assertIn("principalType: 'ServicePrincipal'", source)

    def test_the_logger_has_the_name_the_module_expects(self):
        self.assertIn("name: 'appinsights-logger'", text("environment/gateway/logger.bicep"))

    def test_the_logger_template_makes_the_one_logger_of_the_module_and_no_event_hub_logger(self):
        source = text("environment/gateway/logger.bicep")
        self.assertEqual(set(resources(source)), {"apim", "appInsights", "logger"})
        self.assertNotIn("azureEventHub", re.sub(r"//.*", "", source))

    def test_the_kit_patch_makes_the_two_usage_recording_fragments_conditional_and_lets_the_workflow_choose(self):
        patch = text("environment/kit-patches/no-usage-recording-fragments.patch")
        self.assertEqual(re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", patch), [("bicep/infra/apim-gateway-upgrade/main.bicep",) * 2, ("bicep/infra/modules/apim/policy-fragments.bicep",) * 2])
        first, second = re.split(r"(?m)^diff --git ", patch)[1:]
        # the module's own template: one parameter, off unless somebody asks, passed on to the fragments module; nothing removed
        self.assertEqual([line for line in first.splitlines() if line.startswith("-") and not line.startswith("---")], [])
        added = [line[1:] for line in first.splitlines() if line.startswith("+") and not line.startswith("+++")]
        self.assertIn("param deployUsageRecordingFragments bool = false", added)
        self.assertIn("    deployUsageRecordingFragments: deployUsageRecordingFragments", added)
        self.assertEqual(len([line for line in added if not line.startswith("//") and line.strip()]), 3, "the parameter with its description, and the argument")
        # the fragments module: the two resources and their two outputs wait for that parameter
        added = [line[1:] for line in second.splitlines() if line.startswith("+") and not line.startswith("+++")]
        removed = [line[1:] for line in second.splitlines() if line.startswith("-") and not line.startswith("---")]
        self.assertIn("param deployUsageRecordingFragments bool = false", added)  # off unless somebody asks
        self.assertEqual(sorted(line.split()[1] for line in removed if line.startswith("resource")), ["aiUsagePolicyFragment", "piiStateSavingPolicyFragment"])
        self.assertEqual(sorted(line.split()[1] for line in removed if line.startswith("output")), ["aiUsagePolicyFragmentName", "piiStateSavingPolicyFragmentName"])
        self.assertEqual(len(removed), 4, "nothing else of the kit's file is touched")
        for line in added:
            if line.startswith("resource"):
                self.assertIn("deployUsageRecordingFragments", line)

    def test_the_event_hub_loggers_are_the_two_the_fragments_name_and_use_the_identity_not_a_key(self):
        source = text("environment/gateway/eventhub-loggers.bicep")
        code = re.sub(r"//.*", "", source)
        self.assertEqual(set(resources(source)), {"apim", "usageLogger", "piiLogger"})
        self.assertIn("name: 'usage-eventhub-logger'", code)
        self.assertIn("name: 'pii-usage-eventhub-logger'", code)
        self.assertEqual(code.count("loggerType: 'azureEventHub'"), 2)
        self.assertEqual(code.count("identityClientId: identityClientId"), 2)
        for word in ("connectionString", "sharedAccessKey", "SharedAccessKey", "listKeys", "@secure"):
            self.assertNotIn(word, code, word)
        self.assertNotIn("Microsoft.EventHub", code)  # it only names the namespace; the recording makes it

    def test_the_fragments_that_the_loggers_serve_are_the_ones_the_patch_makes_conditional(self):
        source = text("environment/gateway/eventhub-loggers.bicep")
        patch = text("environment/kit-patches/no-usage-recording-fragments.patch")
        self.assertIn("ai-usage", source)
        self.assertIn("pii-state-saving", source)
        for name in ("aiUsagePolicyFragment", "piiStateSavingPolicyFragment"):
            self.assertIn(name, patch)

    def test_no_policy_of_ours_includes_the_fragments_that_the_kit_patch_leaves_out(self):
        policy = text("environment/gateway/contract-policy.xml")
        for fragment in ("ai-usage", "pii-state-saving"):
            self.assertNotIn(f'fragment-id="{fragment}"', policy)

    def test_the_kit_patches_are_these_three_and_no_others(self):
        found = sorted(p.name for p in (ROOT / "environment" / "kit-patches").glob("*"))
        self.assertEqual(found, ["contract-required.patch", "llm-log-messages-none.patch", "no-usage-recording-fragments.patch"])

    def test_the_llm_log_patch_leaves_the_messages_out_when_the_setting_is_none_and_touches_nothing_else(self):
        patch = text("environment/kit-patches/llm-log-messages-none.patch")
        self.assertEqual(re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", patch), [("bicep/infra/modules/apim/inference-api.bicep",) * 2])
        removed = [line[1:].strip() for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]
        added = [line[1:].strip() for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
        self.assertEqual(removed, ["requests: {", "responses: {"])
        self.assertEqual(added, [
            "requests: azureMonitorLogSettings.largeLanguageModel.requests.messages == 'none' ? null : {",
            "responses: azureMonitorLogSettings.largeLanguageModel.responses.messages == 'none' ? null : {"])

    def test_the_contract_required_patch_adds_one_guard_to_each_of_the_two_inference_api_policies(self):
        patch = text("environment/kit-patches/contract-required.patch")
        self.assertEqual(
            re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", patch),
            [(f"bicep/infra/modules/apim/policies/{name}",) * 2 for name in ("universal-llm-api-policy-v2.xml", "azure-open-ai-api-policy.xml")])
        self.assertEqual([line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")], [], "nothing of the kit's policies is removed")
        hunks = re.split(r"(?m)^diff --git .*$", patch)[1:]
        self.assertEqual(len(hunks), 2)
        self.assertEqual(hunks[0].split("@@", 2)[2], hunks[1].split("@@", 2)[2], "the same guard in both policies")
        guard = hunks[0]
        for needle in ('condition="@(context.Product == null)"', '<set-status code="403" reason="Forbidden" />', '"code":"contract_required"', "<return-response>"):
            self.assertIn(needle, guard)
        added = [line for line in guard.splitlines() if line.startswith("+") and not line.startswith("+++")]
        self.assertEqual(len([line for line in added if "<set-variable" in line or "<forward-request" in line or "<include-fragment" in line]), 0)

    def test_the_gateway_identity_template_makes_only_the_identity(self):
        self.assertIn("param identityName string = 'id-meternaut-gateway'", text("environment/gateway/identity.bicep"))

    def test_the_contract_is_a_published_product_that_needs_a_key_and_has_one_subscription(self):
        source = text("environment/gateway/contract.bicep")
        for line in ("subscriptionRequired: true", "approvalRequired: true", "subscriptionsLimit: 1", "state: 'published'", "format: 'rawxml'", "scope: product.id"):
            self.assertIn(line, source)
        found = resources(source)
        self.assertEqual(set(found), {"apim", "product", "productApis", "productPolicy", "consumerSubscription"})
        # the links before the policy, the policy before the subscription: a key never works before its rules are in place
        self.assertIn("productApis", depends_on(found["productPolicy"][1]))
        self.assertIn("productPolicy", depends_on(found["consumerSubscription"][1]))

    def test_the_contract_hands_out_no_key_and_deletes_nothing(self):
        source = re.sub(r"//.*", "", text("environment/gateway/contract.bicep"))
        self.assertEqual(re.findall(r"^output (\w+)", source, re.M), ["productName", "subscriptionName"])
        for word in ("listSecrets", "primaryKey", "secondaryKey", "@secure", "Delete", "delete"):
            self.assertNotIn(word, source, word)

    def test_the_contract_takes_every_rule_from_a_parameter(self):
        source = text("environment/gateway/contract.bicep")
        for name in ("apimName", "contractName", "subscriptionName", "contractDescription", "apiNames", "policyXml"):
            self.assertRegex(source, rf"(?m)^param {name} (string|array)$")
        self.assertNotIn("loadTextContent", source)


class Recording(unittest.TestCase):
    """The usage recording: what it may create, how each caller reaches it, and what it costs while it stands."""

    def setUp(self):
        self.source = text("environment/recording/main.bicep")
        self.code = re.sub(r"//.*", "", self.source)

    def test_it_makes_no_dns_no_peering_no_route_and_no_gateway_object(self):
        for word in ("Microsoft.ApiManagement", "privateDnsZones", "virtualNetworkPeerings", "routeTables", "privateDnsZoneGroups"):
            self.assertNotIn(word, self.code, word)

    def test_nothing_is_public_but_event_hubs_and_the_function_apps_own_endpoint_and_none_has_a_key(self):
        # Storage and Cosmos DB have no public endpoint; Event Hubs keeps one on purpose (the gateway sends to it, the workflow sends one control
        # event to it; the function app uses a private endpoint, so that it can be switched off later); the function app has the platform's
        # endpoint, which it needs for its deployment and which serves no function (no HTTP trigger).
        self.assertEqual(self.code.count("publicNetworkAccess: 'Disabled'"), 2)  # storage, cosmos
        self.assertEqual(self.code.count("publicNetworkAccess: 'Enabled'"), 2)  # event hubs, the function app
        found = resources(self.source)
        self.assertIn("publicNetworkAccess: 'Disabled'", found["storage"][1])
        self.assertIn("publicNetworkAccess: 'Disabled'", found["cosmos"][1])
        self.assertIn("publicNetworkAccess: 'Enabled'", found["eventHubs"][1])
        self.assertIn("allowSharedKeyAccess: false", found["storage"][1])
        self.assertIn("defaultToOAuthAuthentication: true", found["storage"][1])
        self.assertIn("disableLocalAuth: true", found["cosmos"][1])
        self.assertIn("disableLocalAuth: true", found["eventHubs"][1])
        self.assertIn("DisableLocalAuth: true", found["insights"][1])  # Application Insights takes telemetry only with Entra ID
        self.assertIn("disableLocalAuth: true", found["workspace"][1])
        self.assertIn("allowBlobPublicAccess: false", self.code)
        self.assertEqual(self.code.count("minimumTlsVersion"), 2)  # storage, event hubs
        self.assertIn("minTlsVersion: '1.2'", self.code)  # the function app's site
        self.assertIn("minimalTlsVersion: 'Tls12'", self.code)  # cosmos
        self.assertEqual(self.code.count("allow: false"), 1)  # the deployment endpoint takes no password; FTP does not exist on a Flex Consumption app
        self.assertNotIn("ftpsState", self.code)
        self.assertIn("httpsOnly: true", self.code)
        for word in ("allowSharedKeyAccess: true", "disableLocalAuth: false", "DisableLocalAuth: false"):
            self.assertNotIn(word, self.code, word)

    def test_cosmos_db_is_serverless_and_no_container_has_a_throughput_of_its_own(self):
        self.assertIn("name: 'EnableServerless'", self.code)
        for word in ("throughput", "autoscaleSettings", "maxThroughput", "enableFreeTier", "enableMultipleWriteLocations", "backupPolicy"):
            self.assertNotIn(word, self.code, word)

    def test_the_containers_are_the_ones_the_functions_name(self):
        containers = re.findall(r"\{ name: '([a-z-]+)', partitionKey: '(/\w+)' \}", self.code)
        self.assertEqual(sorted(name for name, _ in containers), ["agent-usage-container", "ai-usage-container", "llm-usage-container", "mcp-usage-container",
                                                                 "model-pricing", "pii-usage-container", "streaming-export-config"])
        settings = dict(re.findall(r"\{ name: '(COSMOS_CONTAINER_\w+)', value: '([a-z-]+)' \}", self.code))
        self.assertEqual(len(settings), 6)
        self.assertTrue(set(settings.values()) <= {name for name, _ in containers})
        self.assertEqual(settings["COSMOS_CONTAINER_LLM_USAGE"], "llm-usage-container")
        self.assertEqual(settings["COSMOS_CONTAINER_CONFIG"], "streaming-export-config")

    def test_the_roles_are_the_ones_that_each_caller_needs_and_nothing_wider(self):
        guids = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.code))
        self.assertEqual(guids, {
            "2b629674-e913-4c01-ae53-ef4638d8f975",  # Azure Event Hubs Data Sender
            "a638d3c7-ab3a-418d-83e6-5f17a39d4fde",  # Azure Event Hubs Data Receiver
            "b7e6dc6d-f1e8-4753-8033-0f276bb0955b",  # Storage Blob Data Owner
            "974c5e8b-45b9-4653-ba55-5f855dd0fb88",  # Storage Queue Data Contributor
            "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3",  # Storage Table Data Contributor
            "3913510d-42f4-4e42-8a64-420c390055eb",  # Monitoring Metrics Publisher
            "00000000-0000-0000-0000-000000000001",  # Cosmos DB built-in Data Reader
            "00000000-0000-0000-0000-000000000002",  # Cosmos DB built-in Data Contributor
        })
        found = resources(self.source)
        assignments = {name: body for name, (kind, body) in found.items() if kind == "Microsoft.Authorization/roleAssignments"}
        self.assertEqual(sorted(assignments), ["functionOwnsBlobs", "functionPublishesTelemetry", "functionReceivesControl", "functionReceivesPii", "functionReceivesUsage",
                                               "functionUsesQueues", "functionUsesTables", "gatewaySendsPii", "gatewaySendsUsage", "workflowSendsControl"])
        for name, body in assignments.items():
            self.assertIn("principalType: 'ServicePrincipal'", body, name)
            # on the one resource, never on the group, the subscription or the whole namespace
            self.assertRegex(body, r"(?m)^  scope: (usageHub|piiHub|controlHub|storage|insights)$", name)
        data_roles = sorted(n for n, (k, _) in found.items() if k == "Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments")
        self.assertEqual(data_roles, ["functionWritesUsage", "readersOfTheData"])
        self.assertIn("cosmosDataContributorRoleId", found["functionWritesUsage"][1])
        self.assertIn("principalId: usageIdentity.properties.principalId", found["functionWritesUsage"][1])
        self.assertIn("cosmosDataReaderRoleId", found["readersOfTheData"][1])

    def test_nothing_relies_on_an_opt_out_of_the_tenants_policies(self):
        for word in ("SecurityControl", "optOut", "Ignore"):
            self.assertNotIn(word, self.code, word)
        self.assertNotIn("tags: union(", self.code)

    def test_the_gateway_and_the_workflow_only_send_and_the_function_app_only_receives_each_on_the_hub_it_uses(self):
        found = resources(self.source)
        for name, hub, principal in (("gatewaySendsUsage", "usageHub", "gatewayPrincipalId"), ("gatewaySendsPii", "piiHub", "gatewayPrincipalId"),
                                     ("workflowSendsControl", "controlHub", "workflowPrincipalId")):
            body = found[name][1]
            self.assertIn("eventHubsDataSenderRoleId", body, name)
            self.assertIn(f"scope: {hub}", body, name)
            self.assertIn(f"principalId: {principal}", body, name)
        for name, hub in (("functionReceivesUsage", "usageHub"), ("functionReceivesPii", "piiHub"), ("functionReceivesControl", "controlHub")):
            body = found[name][1]
            self.assertIn("eventHubsDataReceiverRoleId", body, name)
            self.assertIn(f"scope: {hub}", body, name)
            self.assertIn("principalId: usageIdentity.properties.principalId", body, name)

    def test_the_applications_insights_of_the_gateway_is_a_parameter_because_it_is_in_another_subscription(self):
        for name in ("gatewayAppInsightsSubscriptionId", "gatewayAppInsightsResourceGroup", "gatewayAppInsightsName"):
            self.assertRegex(self.code, rf"(?m)^param {name} string$")
        self.assertIn("{ name: 'GATEWAY_APPINSIGHTS_ID', value: resourceId(gatewayAppInsightsSubscriptionId, gatewayAppInsightsResourceGroup, 'Microsoft.Insights/components', gatewayAppInsightsName) }", self.code)

    def test_the_function_app_runs_on_flex_consumption_in_a_subnet_of_its_own_with_a_ceiling_and_an_identity_for_everything(self):
        found = resources(self.source)
        self.assertIn("name: 'FC1'", found["plan"][1])
        self.assertIn("tier: 'FlexConsumption'", found["plan"][1])
        self.assertIn("reserved: true", found["plan"][1])
        body = found["functionApp"][1]
        self.assertIn("kind: 'functionapp,linux'", body)
        self.assertIn("type: 'UserAssigned'", body)
        self.assertNotIn("SystemAssigned", body)
        self.assertIn("maximumInstanceCount: 10", body)  # the price has a ceiling
        self.assertNotIn("alwaysReady", body)  # nothing runs while nothing is to do
        self.assertIn("virtualNetworkSubnetId: functionSubnet.id", body)
        self.assertRegex(body, r"(?s)runtime: \{\s+name: 'python'\s+version: '3\.13'")
        # the package and the host storage are reached with the identity, and so are the event hubs and the telemetry
        self.assertIn("type: 'UserAssignedIdentity'", body)
        self.assertIn("userAssignedIdentityResourceId: usageIdentity.id", body)
        for setting in ("AzureWebJobsStorage__credential", "AzureWebJobsStorage__clientId", "EventHubConnection__credential", "EventHubConnection__clientId",
                        "EventHubConnection__fullyQualifiedNamespace", "APPLICATIONINSIGHTS_AUTHENTICATION_STRING", "AZURE_CLIENT_ID"):
            self.assertIn(f"name: '{setting}'", body, setting)
        # what a Flex Consumption app must not have, and what would be a key
        for setting in ("'AzureWebJobsStorage'", "AzureWebJobsDashboard", "FUNCTIONS_WORKER_RUNTIME", "FUNCTIONS_EXTENSION_VERSION", "WEBSITE_CONTENT", "WEBSITE_RUN_FROM_PACKAGE",
                        "StorageAccountConnectionString", "basicPublishingCredentialsPolicies"):
            self.assertNotIn(setting, body, setting)

    def test_the_function_app_reaches_every_service_through_a_private_endpoint_and_the_subnets_are_the_two_of_the_model_side(self):
        found = resources(self.source)
        self.assertEqual(sorted(n for n, (k, _) in found.items() if k == "Microsoft.Network/privateEndpoints"), ["cosmosEndpoint", "eventHubsEndpoint", "storageEndpoints"])
        self.assertIn("var storageServices = [\n  'blob'\n  'queue'\n  'table'\n]", self.code)
        self.assertIn("groupIds: [\n            'Sql'\n          ]", found["cosmosEndpoint"][1])
        self.assertIn("groupIds: [\n            'namespace'\n          ]", found["eventHubsEndpoint"][1])
        for name in ("storageEndpoints", "cosmosEndpoint", "eventHubsEndpoint"):
            self.assertIn("id: privateEndpointSubnet.id", found[name][1], name)
        self.assertIn("var privateEndpointSubnetName = 'snet-pe'", self.code)
        self.assertIn("var functionSubnetName = 'snet-func'", self.code)
        model_side = text("environment/main.bicep")
        self.assertIn("name: 'snet-pe'", model_side)
        self.assertIn("name: 'snet-func'", model_side)
        self.assertIn("serviceName: 'Microsoft.App/environments'", model_side)  # the subnet of a Flex Consumption app is delegated to it

    def test_a_service_is_not_changed_while_its_private_endpoint_is_written_to_it(self):
        # The endpoint's connection is written to the service with an If-Match; a change of the service at the same time made an earlier deploy
        # fail with IfMatchPreconditionFailed. So: the endpoint after the last other write to its service, the roles after the endpoint.
        found = resources(self.source)
        self.assertIn("deploymentContainer", depends_on(found["storageEndpoints"][1]))
        self.assertIn("usageContainers", depends_on(found["cosmosEndpoint"][1]))
        self.assertEqual(depends_on(found["eventHubsEndpoint"][1]), {"usageConsumerGroup", "piiConsumerGroup", "controlConsumerGroup"})
        for name in ("gatewaySendsUsage", "gatewaySendsPii", "workflowSendsControl", "functionReceivesUsage", "functionReceivesPii", "functionReceivesControl"):
            self.assertIn("eventHubsEndpoint", depends_on(found[name][1]), name)
        for name in ("functionOwnsBlobs", "functionUsesQueues", "functionUsesTables"):
            self.assertIn("storageEndpoints", depends_on(found[name][1]), name)
        self.assertIn("cosmosEndpoint", depends_on(found["functionWritesUsage"][1]))
        self.assertIn("functionWritesUsage", depends_on(found["readersOfTheData"][1]))
        self.assertRegex(self.source, r"@batchSize\(1\)\nresource storageEndpoints ")  # one endpoint after the other on the same account

    def test_event_hubs_has_no_auto_inflate_so_its_price_has_a_ceiling(self):
        found = resources(self.source)
        self.assertIn("isAutoInflateEnabled: false", found["eventHubs"][1])
        self.assertIn("capacity: 1", found["eventHubs"][1])

    def test_the_workspace_has_a_daily_cap(self):
        self.assertIn("dailyQuotaGb", self.code)

    def test_no_output_carries_a_key_or_a_connection_string(self):
        outputs = [line for line in self.code.splitlines() if line.startswith("output ")]
        self.assertEqual(len(outputs), 9)
        for line in outputs:
            for word in ("listKeys", "listConnectionStrings", "ConnectionString", "AccountKey", "primaryKey"):
                self.assertNotIn(word, line, line)

    def test_no_key_is_read_or_written_anywhere(self):
        for word in ("listKeys", "listConnectionStrings", "listSecrets", "listAccountSas", "listServiceSas", "AccountKey", "SharedAccessKey", "primaryKey", "@secure",
                     "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING"):
            self.assertNotIn(word, self.code, word)
        # the one connection string of the template is the telemetry's: it names the component and holds no secret that ingestion accepts (local authentication is off)
        self.assertEqual(self.code.count("ConnectionString"), 1)
        self.assertIn("{ name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }", self.code)

    def test_the_order_that_the_services_need_is_in_the_template(self):
        found = resources(self.source)
        self.assertEqual(depends_on(found["functionApp"][1]), {"functionReceivesUsage", "functionReceivesPii", "functionReceivesControl", "functionOwnsBlobs", "functionUsesQueues",
                                                               "functionUsesTables", "functionPublishesTelemetry", "functionWritesUsage"},
                         "the roles before the first start of the app: it reads its storage and its event hubs with them")
        self.assertIn("deploymentContainer", depends_on(found["storageEndpoints"][1]))

    def test_the_event_hubs_and_their_consumer_groups_are_the_ones_the_functions_name(self):
        self.assertIn("var usageHubName = 'ai-usage'", self.code)
        self.assertIn("var piiHubName = 'pii-usage'", self.code)
        self.assertIn("var controlHubName = 'usage-control'", self.code)
        for group in ("aiUsageIngestion", "piiUsageIngestion", "usageControl"):
            self.assertIn(f"name: '{group}'", self.code)
        self.assertIn("{ name: 'EVENTHUB_USAGE_NAME', value: usageHubName }", self.code)
        self.assertIn("{ name: 'EVENTHUB_PII_NAME', value: piiHubName }", self.code)
        self.assertIn("{ name: 'EVENTHUB_CONTROL_NAME', value: controlHubName }", self.code)

    def test_every_setting_that_the_functions_read_is_set_by_the_template(self):
        config = ROOT / "src" / "usage-functions" / "usage" / "config.py"
        self.assertTrue(config.exists(), "the function app's settings are in src/usage-functions/usage/config.py")
        read = set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', config.read_text(encoding="utf-8"), re.M))
        self.assertGreaterEqual(len(read), 10)
        found = resources(self.source)
        given = set(re.findall(r"\{ name: '([A-Za-z0-9_]+)', value: ", found["functionApp"][1]))
        self.assertEqual(sorted(read - given), [], "the template does not set what the code requires")
        self.assertEqual(sorted(name for name in given - read if name.isupper() and "__" not in name and not name.startswith(("APPLICATIONINSIGHTS", "EVENTHUB_"))), [],
                         "the template sets a setting that the code never reads")


class Workflow(unittest.TestCase):
    """Structure of the deploy workflow that its lint does not see: what may write, and when."""

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]

    def test_the_kit_is_pinned_to_the_same_commit_in_the_deploy_workflow_and_in_the_checks(self):
        refs = []
        for path in (".github/workflows/deploy-hub.yml", ".github/workflows/checks.yml"):
            match = re.search(r"repository: Azure-Samples/ai-hub-gateway-solution-accelerator\n\s+ref: ([0-9a-f]{40})\n", text(path))
            self.assertIsNotNone(match, path)
            refs.append(match.group(1))
        self.assertEqual(refs[0], refs[1])

    def test_every_step_that_writes_to_azure_names_the_actions_it_runs_in_and_never_what_if(self):
        writers = 0
        for block in self.steps:
            if "az-deploy.py create" in block or "gateway-prep.py attach-identity" in block:
                writers += 1
                condition = re.search(r"(?m)^        if: (.+)$", block)
                self.assertIsNotNone(condition, block[:80])
                self.assertNotIn("'what-if'", condition.group(1))
                self.assertNotIn("always()", condition.group(1))
        self.assertGreaterEqual(writers, 5)

    def test_the_conditions_name_only_actions_that_the_workflow_offers(self):
        options = re.search(r"options:\n((?:          - .+\n)+)", self.text)
        self.assertIsNotNone(options)
        offered = set(re.findall(r"- (\S+)", options.group(1)))
        used = set(re.findall(r"inputs\.action == '([a-z-]+)'", self.text))
        self.assertTrue(used <= offered, used - offered)
        self.assertTrue(offered <= used, f"an action with no step of its own: {offered - used}")

    def test_the_workflow_makes_no_resource_group_no_role_and_no_dns(self):
        for word in ("az group delete", "az group create", "az role assignment", "az role definition", "privateDnsZones", "az network private-dns"):
            self.assertNotIn(word, self.text, word)

    def contract_steps(self):
        return [block for block in self.steps if "inputs.action == 'contract'" in block]

    def test_the_key_of_the_contract_is_read_masked_and_handed_to_one_command_only(self):
        (block,) = [b for b in self.steps if "listSecrets" in b]
        self.assertTrue(block.startswith("name: Test the gateway with the contract's key"))
        self.assertEqual(len(re.findall(r"listSecrets", self.text)), 1)
        self.assertLess(block.index("listSecrets"), block.index('echo "::add-mask::$key"'))
        self.assertLess(block.index('echo "::add-mask::$key"'), block.index("tools/environment-smoke.py"))
        self.assertIn('GATEWAY_SMOKE_KEY="$key" python3 tools/environment-smoke.py', block)
        # nothing keeps the key: not a secret, an output, the environment file, the summary or a file of the run
        self.assertNotRegex(block, r"(?m)^\s*export ")
        for word in ("GITHUB_ENV", "GITHUB_OUTPUT", "gh secret", "--debug", "set -x", "az account get-access-token"):
            self.assertNotIn(word, block, word)
        for line in block.splitlines():
            if "$key" in line and "add-mask" not in line and "GATEWAY_SMOKE_KEY" not in line and "key=$(" not in line:
                self.fail(f"the key is used somewhere else: {line.strip()}")
        for other in self.steps:
            if other is not block:
                self.assertNotIn("$key", other)

    def test_every_kit_patch_is_checked_and_applied_before_anything_reads_the_kit(self):
        for path in (".github/workflows/deploy-hub.yml", ".github/workflows/checks.yml"):
            source = text(path)
            loop = "for patch in environment/kit-patches/*.patch; do"
            check = 'git -C kit apply --check "../$patch"'
            apply_ = 'git -C kit apply "../$patch"'
            self.assertEqual(source.count(loop), 1, path)
            self.assertEqual(source.count(apply_), 1, path)
            self.assertLess(source.index(loop), source.index(check), path)
            self.assertLess(source.index(check), source.index(apply_), path)
            self.assertLess(source.index(apply_), source.index("kit/bicep/infra/apim-gateway-upgrade/main.bicep"), path)

    def test_the_two_model_apis_are_read_back_after_the_module_has_been_applied(self):
        (block,) = [b for b in self.steps if b.startswith("name: The two model APIs refuse a call that is not made with a contract's key")]
        self.assertIn("if: inputs.action == 'gateway'", block)
        self.assertIn("--method get", block)
        self.assertNotRegex(block, r"--method (put|patch|post|delete)")
        for api in ("universal-llm-api", "azure-openai-api"):
            self.assertIn(api, block)
        self.assertIn("contract_required", block)
        names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]
        self.assertLess(names.index("Add the Citadel module's objects to the gateway"), names.index("The two model APIs refuse a call that is not made with a contract's key"))

    def test_the_contract_is_added_only_after_the_gateway_has_the_apis_it_grants(self):
        first, second = [b for b in self.steps if b.startswith("name: What the first contract would change")], self.contract_steps()
        self.assertEqual(len(first), 1)
        self.assertIn("inputs.action == 'what-if' || inputs.action == 'contract'", first[0])
        self.assertIn("run gateway first", first[0].lower().replace("::error::", ""))
        names = [re.match(r"name: (.+)", b).group(1) for b in second]
        self.assertEqual(names[:3], ["What the first contract would change in the gateway", "Add the first contract to the gateway", "Test the gateway with the contract's key"])
        order = [self.text.index(f"- name: {n}") for n in names[:3]]
        self.assertEqual(order, sorted(order))

    def test_the_limit_check_is_opt_in_and_reaches_the_script_only_through_the_environment(self):
        self.assertRegex(self.text, r"(?s)check_limits:\n\s+description: .+?\n\s+type: boolean\n\s+required: false\n\s+default: false")
        (block,) = [b for b in self.steps if "CHECK_LIMITS" in b]
        self.assertIn("CHECK_LIMITS: ${{ inputs.check_limits }}", block)
        self.assertNotIn("${{ inputs.check_limits }}", block.split("run:")[1])

    def names(self):
        return [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def test_every_step_that_publishes_or_starts_a_job_names_the_actions_it_runs_in_and_never_what_if(self):
        found = 0
        for block in self.steps:
            if "az functionapp deployment source config-zip" in block or "recording-check.py run" in block:
                found += 1
                condition = re.search(r"(?m)^        if: (.+)$", block)
                self.assertIsNotNone(condition, block[:80])
                self.assertNotIn("what-if", condition.group(1))
                self.assertNotIn("always()", condition.group(1))
        self.assertEqual(found, 2)

    def test_the_recording_is_made_ready_deployed_published_and_listed_in_that_order_and_for_its_action_only(self):
        order = ["Remove the key-based Logic App version of the usage recording, when it is still there", "Deploy the usage recording",
                 "Wait until the landing zone has registered the usage recording's private endpoints in the central zones",
                 "Sign in to Azure again for the publish, because the first sign-in's credential lasts five minutes",
                 "Build the function app's package", "Publish the usage functions to the function app", "The function app lists its six functions"]
        names = self.names()
        positions = [names.index(name) for name in order]
        self.assertEqual(positions, sorted(positions))
        for name in order:
            self.assertIn("if: inputs.action == 'recording'", self.steps[names.index(name)])
        deploy = self.steps[names.index("Deploy the usage recording")]
        self.assertIn("--template environment/recording/main.bicep", deploy)
        self.assertIn('--parameters "$RUNNER_TEMP/recording.parameters.json"', deploy)
        self.assertIn("--output functionAppId", deploy)
        self.assertEqual(self.text.count("--template environment/recording/main.bicep"), 2, "the preview and the deploy, nothing else")

    def test_the_key_based_version_is_removed_by_its_four_names_and_nothing_else_is_deleted_anywhere(self):
        (block,) = [b for b in self.steps if b.startswith("name: Remove the key-based Logic App version")]
        for variable, output in (("LEGACY_LOGIC_APP", "legacy_logic_app_name"), ("LEGACY_PLAN", "legacy_plan_name"),
                                 ("LEGACY_CONNECTION", "legacy_connection_name"), ("LEGACY_STORAGE", "legacy_storage_account_name")):
            self.assertIn(f"{variable}: ${{{{ steps.params.outputs.{output} }}}}", block)
            self.assertIn(f"[?name=='${variable}']", block)
        self.assertEqual(re.findall(r'az resource delete --ids "\$(\w+)"', block), ["site", "plan", "connection", "storage"])
        self.assertEqual(self.text.count("az resource delete"), 4)
        self.assertEqual(len(re.findall(r"(?m)^\s*az \S+(?: \S+)* delete\b", self.text)), 4, "no other delete, of any kind")
        self.assertNotIn("--yes", block)
        for kind in ("Microsoft.Web/sites", "Microsoft.Web/serverfarms", "Microsoft.Web/connections", "Microsoft.Storage/storageAccounts"):
            self.assertIn(f"--resource-type {kind}", block)

    def test_the_function_app_is_given_its_code_only_after_the_landing_zone_has_registered_every_endpoint(self):
        (block,) = [b for b in self.steps if b.startswith("name: Wait until the landing zone has registered the usage recording's private endpoints")]
        self.assertIn("RECORDING_ENDPOINTS: ${{ steps.params.outputs.recording_endpoints }}", block)
        self.assertIn("az network private-endpoint dns-zone-group list", block)
        self.assertIn("exit 1", block)
        self.assertNotIn("--method", block)
        self.assertNotRegex(block, r"az \S+ (create|delete|update|set)\b")

    def test_nothing_in_the_workflow_reads_a_key_but_the_contracts_and_nothing_writes_one(self):
        for word in ("listKeys", "listConnectionStrings", "AccountKey", "SharedAccessKey", "primaryMasterKey", "az storage account keys", "--auth-mode key",
                     "az cosmosdb keys", "az eventhubs namespace authorization-rule", "az functionapp keys", "--connection-string", "az webapp deployment list-publishing"):
            self.assertNotIn(word, self.text, word)
        self.assertEqual(self.text.count("listSecrets"), 1, "the contract's own subscription key, read for one test and masked: AGENTS.md rule 23 names it")

    def test_the_recording_signs_in_again_before_it_publishes_because_the_first_credential_lasts_five_minutes(self):
        names = self.names()
        again = "Sign in to Azure again for the publish, because the first sign-in's credential lasts five minutes"
        block = self.steps[names.index(again)]
        self.assertIn("if: inputs.action == 'recording'", block)
        self.assertIn("uses: azure/login@", block)
        self.assertEqual(self.text.count("uses: azure/login@"), 2)
        self.assertLess(names.index("Deploy the usage recording"), names.index(again))
        self.assertLess(names.index(again), names.index("Publish the usage functions to the function app"))

    def test_the_package_is_built_by_the_script_that_the_checks_use_and_published_with_the_identity_and_no_password(self):
        (build,) = [b for b in self.steps if b.startswith("name: Build the function app's package")]
        self.assertIn('bash tools/build-usage-functions.sh "$RUNNER_TEMP/usage-functions" "$RUNNER_TEMP/usage-functions.zip"', build)
        (publish,) = [b for b in self.steps if b.startswith("name: Publish the usage functions to the function app")]
        self.assertIn("az functionapp deployment source config-zip", publish)
        self.assertIn('--src "$RUNNER_TEMP/usage-functions.zip"', publish)
        self.assertIn("--build-remote false", publish)
        self.assertIn("FUNCTION_APP: ${{ steps.params.outputs.function_app_name }}", publish)
        self.assertNotIn("environment/", publish + build)
        for word in ("az webapp deploy", "publishing-credentials", "--user", "--password", "kit/"):
            self.assertNotIn(word, publish + build, word)
        self.assertIn("for attempt in 1 2 3", publish)
        self.assertEqual(text(".github/workflows/checks.yml").count("bash tools/build-usage-functions.sh"), 1, "the checks build the same package, so a missing wheel is found before a deploy")

    def test_the_copy_job_is_started_only_by_its_own_action(self):
        (block,) = [b for b in self.steps if "recording-check.py run" in b]
        self.assertIn("if: inputs.action == 'recording-check'", block)
        self.assertNotIn("listSecrets", block)

    def test_the_identity_of_the_workflow_is_read_after_the_sign_in_and_before_the_settings(self):
        names = self.names()
        self.assertLess(names.index("Sign in to Azure"), names.index("Read the object id of the signed-in identity"))
        self.assertLess(names.index("Read the object id of the signed-in identity"), names.index("Work out the settings"))
        (block,) = [b for b in self.steps if b.startswith("name: Work out the settings\n")]
        self.assertIn("RECORDING_DEPLOYER_ID: ${{ steps.me.outputs.oid }}", block)
        (block,) = [b for b in self.steps if b.startswith("name: Work out the settings with the identity's principal")]
        self.assertIn("RECORDING_DEPLOYER_ID: ${{ steps.me.outputs.oid }}", block)

    def test_the_recording_needs_the_gateway_identity_to_exist(self):
        (block,) = [b for b in self.steps if b.startswith("name: Find the gateway identity")]
        self.assertIn("inputs.action == 'recording'", block)

    def test_the_event_hub_loggers_are_added_only_by_gateway_prepare_and_only_when_the_namespace_exists(self):
        names = self.names()
        title = "Add the two Event Hub loggers, when the usage recording's Event Hubs namespace exists"
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}")]
        self.assertIn("if: inputs.action == 'gateway-prepare'", block)
        self.assertIn("--resource-type Microsoft.EventHub/namespaces", block)
        self.assertLess(block.index("exit 0"), block.index("az-deploy.py create"), "without the namespace nothing is written")
        self.assertIn("--template environment/gateway/eventhub-loggers.bicep", block)
        self.assertIn('--parameters "$RUNNER_TEMP/eventhub-loggers.parameters.json"', block)
        self.assertLess(names.index("Add the Application Insights logger that the module expects"), names.index(title))
        self.assertLess(names.index(title), names.index("Wait until the gateway has finished updating"))
        self.assertEqual(self.text.count("--template environment/gateway/eventhub-loggers.bicep"), 2, "the preview and the deploy, nothing else")

    def test_the_fragments_are_asked_for_only_when_both_loggers_are_in_the_instance(self):
        (block,) = [b for b in self.steps if b.startswith("name: Work out the settings\n")]
        self.assertIn("fragments=false", block)
        self.assertIn("grep -Fxq usage-eventhub-logger", block)
        self.assertIn("grep -Fxq pii-usage-eventhub-logger", block)
        self.assertIn('RECORDING_FRAGMENTS="$fragments"', block)
        self.assertLess(block.index("fragments=false"), block.index('RECORDING_FRAGMENTS="$fragments"'))
        self.assertIn("--method get", block)
        self.assertNotRegex(block, r"--method (put|patch|post|delete)")


if __name__ == "__main__":
    unittest.main()
