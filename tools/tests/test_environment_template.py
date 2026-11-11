import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The step of the Hub that previews the templates for the action what-if (the gateway templates of the owner's API Management instance were taken out of it, 2026-11-07).
PREVIEW_STEP = "What the model side, the base, the Foundry resource, the first cases, the Operator and the AI Gateway's templates would change"

# Everything each template may create. AGENTS.md rule 19: in a landing zone no private DNS zone, no link to one and no
# zone group (a policy registers the endpoint's name), no peering or route by hand (the network manager does it), and
# no API Management object of the owner's instance (2026-11-07, AGENTS.md rule 15 (c): the owner ordered the undo of what Meternaut had added, and nothing makes an object there any more).
ALLOWED = {
    "environment/main.bicep": {
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
    },
    "infra/budgets/rg-budget.bicep": {"Microsoft.Consumption/budgets"},
    "environment/base/main.bicep": {
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Network/virtualNetworks/subnets",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.OperationalInsights/workspaces",
        "Microsoft.Insights/components",
        "Microsoft.Storage/storageAccounts",
        "Microsoft.Storage/storageAccounts/blobServices",
        "Microsoft.Storage/storageAccounts/blobServices/containers",
    },
    "environment/cases/main.bicep": {
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Network/virtualNetworks/subnets",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.OperationalInsights/workspaces",
        "Microsoft.OperationalInsights/workspaces/tables",
        "Microsoft.Insights/components",
        "Microsoft.Insights/workbooks",
        "Microsoft.Storage/storageAccounts",
        "Microsoft.Storage/storageAccounts/blobServices",
        "Microsoft.Storage/storageAccounts/blobServices/containers",
        "Microsoft.Storage/storageAccounts/queueServices",
        "Microsoft.Storage/storageAccounts/queueServices/queues",
        "Microsoft.Authorization/roleAssignments",
        "Microsoft.Web/serverfarms",
        "Microsoft.Web/sites",
        "Microsoft.Web/sites/basicPublishingCredentialsPolicies",
        "Microsoft.Web/sites/config",
    },
    # The planted waste (2026-11-08, the families of change): a disk, an address when asked, and when asked a machine with its network interface and its OS disk. The machine's subnet is read and never made.
    "environment/cases/planted.bicep": {"Microsoft.Compute/disks", "Microsoft.Network/publicIPAddresses", "Microsoft.Network/networkInterfaces", "Microsoft.Compute/virtualMachines"},
    "environment/foundry/main.bicep": {
        "Microsoft.CognitiveServices/accounts",
        "Microsoft.CognitiveServices/accounts/raiPolicies",
        "Microsoft.CognitiveServices/accounts/deployments",
        "Microsoft.CognitiveServices/accounts/projects",
        "Microsoft.CognitiveServices/accounts/projects/connections",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Insights/components",
        "Microsoft.Authorization/roleAssignments",
    },
    "environment/operator/main.bicep": {
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Network/virtualNetworks/subnets",
        "Microsoft.Storage/storageAccounts",
        "Microsoft.Storage/storageAccounts/queueServices",
        "Microsoft.Storage/storageAccounts/queueServices/queues",
        "Microsoft.Authorization/roleAssignments",
    },
    "environment/aigateway/subnet.bicep": {
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Network/virtualNetworks/subnets",
    },
    "environment/aigateway/main.bicep": {
        "Microsoft.CognitiveServices/accounts",
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "Microsoft.ApiManagement/aigateways",
        "Microsoft.ApiManagement/aigateways/workspaces",
        "Microsoft.ApiManagement/aigateways/workspaces/modelProviders",
        "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models",
        "Microsoft.ApiManagement/aigateways/workspaces/aliases",
        "Microsoft.Authorization/roleAssignments",
    },
    # The gateway's telemetry exporter (the action gateway-telemetry): one exporter on the gateway's default workspace, and the project's own component, which it only reads.
    "environment/aigateway/telemetry.bicep": {
        "Microsoft.ApiManagement/aigateways",
        "Microsoft.ApiManagement/aigateways/workspaces",
        "Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters",
        "Microsoft.Insights/components",
    },
    # The AI security (docs/proposals/10-ai-security-and-governance.md, the action governance): Azure Policy at the group (Audit or Deny, no exemption), the alert rules and their action group, the workbook, the
    # retention of two tables, and a diagnostic setting only where the landing zone has not made one. The workspace, the Foundry resource and the component are only read.
    "environment/governance/main.bicep": {
        "Microsoft.OperationalInsights/workspaces",
        "Microsoft.CognitiveServices/accounts",
        "Microsoft.Authorization/policyAssignments",
        "Microsoft.Insights/diagnosticSettings",
        "Microsoft.OperationalInsights/workspaces/tables",
        "Microsoft.Insights/actionGroups",
        "Microsoft.Insights/scheduledQueryRules",
        "Microsoft.Insights/workbooks",
    },
    # Virtual network support for Power Platform (docs/proposals/19-teams-cards-through-power-automate.md): the subnet that Power Platform's connectors run in, with its group, and the enterprise policy that names it.
    # No role, no private endpoint and no DNS object; the virtual network is only read.
    "environment/powerplatform/main.bicep": {
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Network/virtualNetworks/subnets",
        "Microsoft.PowerPlatform/enterprisePolicies",
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

    def test_the_model_side_makes_the_network_and_nothing_else(self):
        found = resources(text("environment/main.bicep"))
        self.assertEqual(set(found), {"nsg", "funcNsg", "webNsg", "vnet"}, "the old model account, its deployments and its private endpoint were removed on 2026-11-07: no account, no endpoint and no role here")

    def test_the_model_side_makes_the_virtual_network_only_while_it_is_not_there_so_that_the_landing_zones_route_tables_stay(self):
        # A virtual network that is made again, with its subnets listed, loses the route tables that the landing zone's network manager put on them (AGENTS.md rule 27).
        source = text("environment/main.bicep")
        code = re.sub(r"//.*", "", source)
        found = resources(source)
        self.assertRegex(code, r"(?m)^param networkExists bool = false$")
        self.assertTrue(found["vnet"][1].startswith("if (!networkExists) {"))
        self.assertNotIn("routeTable", code, "the route tables are the landing zone's, not the template's")
        self.assertNotRegex(code, r"\bvnet\.", "nothing reads a property of a network that may not be made")

    def test_the_model_side_makes_no_model_account_no_deployment_no_private_endpoint_and_no_role_and_says_when_they_were_removed(self):
        source = text("environment/main.bicep")
        code = re.sub(r"//.*", "", source)
        for word in ("Microsoft.CognitiveServices", "privateEndpoints", "roleAssignments", "roleDefinitions", "Microsoft.Authorization", "principalId", "modelDeployment", "disableLocalAuth", "restore"):
            self.assertNotIn(word, code, word)
        self.assertEqual(len(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", code)), 0)
        flat = re.sub(r"\n//\s*", " ", source)
        self.assertIn("was removed on 2026-11-07", flat)
        self.assertIn("the action retire-old deletes it", flat)
        for subnet in ("snet-pe", "snet-func", "snet-cases"):
            self.assertIn(f"name: '{subnet}'", code, f"{subnet} stays: the apps and the private endpoints use it")
        self.assertIn("serviceName: 'Microsoft.App/environments'", code, "snet-func stays delegated to Flex Consumption, which a later try of the cases app on Flex uses")
    def test_nothing_in_the_repository_can_make_an_object_on_the_owners_api_management_instance(self):
        # The owner ordered the undo of what Meternaut had added to his instance (2026-11-07, AGENTS.md rule 15 (c)): the templates, the kit's patches and the contract that made those objects are gone,
        # and no template declares an object of an instance (the AI Gateway's own types, Microsoft.ApiManagement/aigateways, are Azure's separate service).
        for gone in ("environment/gateway", "environment/kit-patches", "environment/contract.json", "tools/gateway-prep.py", "tools/tests/test_gateway_prep.py", "tools/environment-smoke.py"):
            self.assertFalse((ROOT / gone).exists(), gone)
        templates = sorted((ROOT / "environment").rglob("*.bicep")) + sorted((ROOT / "infra").rglob("*.bicep"))
        self.assertGreaterEqual(len(templates), 9)
        for path in templates:
            code = re.sub(r"//.*", "", path.read_text(encoding="utf-8"))
            self.assertNotRegex(code, r"Microsoft\.ApiManagement/(?!aigateways)", path.as_posix())
            self.assertNotRegex(code, r"(?i)\bapim\b|listSecrets|policyFragments|azureEventHub", path.as_posix())
        for path in sorted((ROOT / "tools").glob("*.py")):
            if path.name == "access-requirements.py":
                continue  # it only reads the instance's resource id, to find the resource group of the retired custom role, and calls nothing on the instance
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"Microsoft\.ApiManagement/service", path.name)


class Base(unittest.TestCase):
    """The base (environment/base/main.bicep): the workspace, Application Insights and the storage account with its private endpoints, and nothing else."""

    def setUp(self):
        self.source = text("environment/base/main.bicep")
        self.code = re.sub(r"//.*", "", self.source)
        self.found = resources(self.source)

    def test_it_makes_no_dns_no_peering_no_route_and_no_gateway_object(self):
        for word in ("Microsoft.ApiManagement", "privateDnsZones", "virtualNetworkPeerings", "routeTables", "privateDnsZoneGroups"):
            self.assertNotIn(word, self.code, word)

    def test_it_makes_only_the_shared_services_and_their_private_endpoints_and_no_app_no_database_no_hub_no_role_and_no_identity(self):
        made = sorted(name for name in self.found if not re.search(rf"(?m)^resource {name} '[^']+' existing", self.source))
        self.assertEqual(made, ["blobService", "insights", "sharedHostContainers", "storage", "storageEndpoints", "workspace"])
        for word in ("Microsoft.Web", "Microsoft.DocumentDB", "Microsoft.Authorization", "Microsoft.ManagedIdentity", "roleAssignments", "principalId", "usage", "cosmos", "functionApp",
                     "ai-usage", "pii-usage", "usage-control", "cases-control", "eventhubs@"):
            self.assertNotIn(word, self.code, f"{word}: the usage recording was removed on 2026-11-07, and the control queue of the cases app is made by environment/cases/main.bicep")
        self.assertEqual(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.code), [], "no role, so no id of a role")

    def test_it_makes_no_event_hubs_namespace_no_private_endpoint_for_one_and_no_checkpoint_container(self):
        for word in ("Microsoft.EventHub", "eventHub", "evhns", "namespace", "servicebus", "azure-webjobs-eventhub", "checkpoint"):
            self.assertNotIn(word, self.code, f"{word}: the control message goes through a queue in the storage account, and the action retire-event-hubs deletes what was made before")
        self.assertEqual(sorted(n for n, (k, _) in self.found.items() if k == "Microsoft.Network/privateEndpoints"), ["storageEndpoints"])

    def test_nothing_is_public_and_none_has_a_key(self):
        # Storage has no public endpoint (docs/proposals/07-private-by-default.md): the cases app and the Operator reach it, and its queue, through private endpoints.
        self.assertEqual(self.code.count("publicNetworkAccess: 'Disabled'"), 1)  # storage
        self.assertEqual(self.code.count("publicNetworkAccess:"), 1, "every resource that has the property says its value")
        self.assertIn("publicNetworkAccess: 'Disabled'", self.found["storage"][1])
        self.assertNotIn("publicNetworkAccess: 'Enabled'", self.code)
        self.assertIn("allowSharedKeyAccess: false", self.found["storage"][1])
        self.assertIn("defaultToOAuthAuthentication: true", self.found["storage"][1])
        self.assertIn("DisableLocalAuth: true", self.found["insights"][1])  # Application Insights takes telemetry only with Entra ID
        self.assertIn("disableLocalAuth: true", self.found["workspace"][1])
        self.assertIn("allowBlobPublicAccess: false", self.code)
        self.assertEqual(self.code.count("minimumTlsVersion"), 1)  # storage
        for word in ("allowSharedKeyAccess: true", "disableLocalAuth: false", "DisableLocalAuth: false"):
            self.assertNotIn(word, self.code, word)

    def test_nothing_relies_on_an_opt_out_of_the_tenants_policies(self):
        for word in ("SecurityControl", "optOut", "Ignore"):
            self.assertNotIn(word, self.code, word)
        self.assertNotIn("tags: union(", self.code)

    def test_the_storage_account_is_reached_through_private_endpoints_into_the_endpoint_subnet_of_the_model_side(self):
        found = self.found
        self.assertEqual(sorted(n for n, (k, _) in found.items() if k == "Microsoft.Network/privateEndpoints"), ["storageEndpoints"])
        self.assertIn("var storageServices = [\n  'blob'\n  'queue'\n  'table'\n]", self.code, "the queue endpoint is the way in for the control queue")
        self.assertIn("id: privateEndpointSubnet.id", found["storageEndpoints"][1])
        self.assertIn("var privateEndpointSubnetName = 'snet-pe'", self.code)
        self.assertNotIn("snet-func", self.code, "the base reads the endpoint subnet only: the function subnet is the model side's, and the cases app uses it")
        self.assertIn("name: 'snet-pe'", text("environment/main.bicep"))

    def test_a_service_is_not_changed_while_its_private_endpoint_is_written_to_it(self):
        # The endpoint's connection is written to the service with an If-Match; a change of the service at the same time made an earlier deploy
        # fail with IfMatchPreconditionFailed. So: the endpoint after the last other write to its service.
        self.assertIn("sharedHostContainers", depends_on(self.found["storageEndpoints"][1]))
        self.assertRegex(self.source, r"@batchSize\(1\)\nresource storageEndpoints ")  # one endpoint after the other on the same account

    def test_the_shared_host_containers_are_the_two_that_every_functions_host_of_the_account_shares_and_no_package_container_is_made(self):
        self.assertIn("var sharedHostContainerNames = [\n  'azure-webjobs-hosts'\n  'azure-webjobs-secrets'\n]", self.code)
        self.assertIn("publicAccess: 'None'", self.found["sharedHostContainers"][1])
        for word in ("app-package", "deploymentContainer"):
            self.assertNotIn(word, self.code, f"{word}: the usage app's package container is gone with the app, and the cases app's code is pushed to the app")

    def test_the_header_says_what_the_base_is_that_nothing_public_reaches_the_storage_account_and_that_the_namespace_the_usage_recording_and_the_old_model_account_are_gone(self):
        flat = re.sub(r"\n//\s*", " ", self.source)
        for old in ("Event Hubs keeps public access on", "keeps public access on", "the deployment workflow sends one control event to it", "so that public access can be switched off later",
                    "the workflow sends to the control hub", "control events of the deployment workflow", "the gateway's two loggers can use only that endpoint too",
                    "and an Event Hubs namespace (the cases app's control hub is made in it"):
            self.assertNotIn(old, flat, old)
        for now in ("storage has public network access off and is reached through private endpoints",
                    "the Operator (environment/operator/main.bicep, which puts the control message of the check that starts a Watch in the queue) use the queue endpoint",
                    "which also holds the cases app's control queue that environment/cases/main.bicep makes",
                    "The Event Hubs namespace that the cases app's control events used to go through is not made here any more: the control message goes through a Storage queue in the storage account, "
                    "and the action retire-event-hubs deletes the namespace and its private endpoint once the queue path has been proved",
                    "the usage recording that used to live here (a function app, a Cosmos DB account and three event hubs, made for the calls of the owner's API Management instance) was removed on 2026-11-07",
                    "and so was the model account that nothing calls (the action retire-old deletes both)",
                    'Deployed only by the workflow .github/workflows/deploy-hub.yml, action "base" (AGENTS.md rule 18)'):
            self.assertIn(now, flat, now)

    def test_the_workspace_has_a_daily_cap(self):
        self.assertIn("dailyQuotaGb", self.code)

    def test_no_output_carries_a_key_or_a_connection_string(self):
        outputs = [line for line in self.code.splitlines() if line.startswith("output ")]
        self.assertEqual(re.findall(r"(?m)^output (\w+) ", self.code), ["storageAccountName", "appInsightsId"])
        self.assertEqual(len(outputs), 2)
        for line in outputs:
            for word in ("listKeys", "listConnectionStrings", "ConnectionString", "AccountKey", "primaryKey"):
                self.assertNotIn(word, line, line)

    def test_no_key_is_read_or_written_anywhere(self):
        for word in ("listKeys", "listConnectionStrings", "listSecrets", "listAccountSas", "listServiceSas", "AccountKey", "SharedAccessKey", "primaryKey", "@secure",
                     "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING", "ConnectionString"):
            self.assertNotIn(word, self.code, word)


class Workflow(unittest.TestCase):
    """Structure of the deploy workflow that its lint does not see: what may write, and when."""

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]

    def test_neither_workflow_checks_out_the_kit_or_applies_a_patch_any_more(self):
        # The Citadel kit's module and the three patches to it made the objects on the owner's API Management instance (2026-11-07, AGENTS.md rule 15 (c)): both are gone.
        for path in (".github/workflows/deploy-hub.yml", ".github/workflows/checks.yml"):
            source = text(path)
            for word in ("Azure-Samples/ai-hub-gateway-solution-accelerator", "path: kit", "kit/bicep", "kit-patches", "git -C kit", "kit.json", "kit.parameters.json", "label kit"):
                self.assertNotIn(word, source, f"{word} in {path}")

    def test_every_step_that_writes_to_azure_names_the_actions_it_runs_in_and_never_what_if(self):
        writers = 0
        for block in self.steps:
            if "az-deploy.py create" in block:
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
        used = set(re.findall(r"inputs\.action == '([a-z0-9-]+)'", self.text))
        self.assertTrue(used <= offered, used - offered)
        self.assertTrue(offered <= used, f"an action with no step of its own: {offered - used}")

    def test_the_workflow_makes_no_resource_group_no_role_and_no_dns(self):
        for word in ("az group delete", "az group create", "az role assignment create", "az role definition", "privateDnsZones", "az network private-dns"):
            self.assertNotIn(word, self.text, word)

    def test_the_roles_that_the_workflow_removes_are_only_the_one_on_the_container_that_the_flex_version_left_behind(self):
        # The incremental deployment never removes a role assignment, and the identity's condition lets it delete the roles that the templates give.
        users = [re.match(r"name: (.+)", b).group(1) for b in self.steps if "az role assignment" in b]
        # The first only reads as well: the preview of the AI security's templates lists the deploy identity's roles on the group before it previews the policy, to skip the policy when none of them can write a policy assignment
        # (Azure refuses even the preview of a template that writes one: tools/tests/test_powerplatform_hub.py pins that it only lists).
        # The last one only reads: it looks at the condition of the deploy identity's right to assign roles before the AI Gateway is made (test_aigateway_workflow.py pins that it only lists).
        # The two after it only read as well: the one before the AI security lists the deploy identity's roles on the group, to see that one of them can write a policy assignment, and the one before the
        # telemetry exporter lists the roles on the component's data collection rule, to see that the AI Gateway's identity may send there (tools/tests/test_governance_workflow.py pins that no step of the AI security writes).
        # The right to send to the control hub usage-control is not retired by a step any more: the hub is deleted by the action retire-old (tools/retire-old.py), with the rest of the usage recording.
        # The deploy identity's old right to send to the control hub cases-control was retired by a step of the action cases until the control message moved to a queue: the hub is deleted
        # now by the action retire-event-hubs, with the roles that were scoped to it, so no step looks for that assignment any more.
        self.assertEqual(users, ["What the AI security's templates would change",
                                 "Remove what the Flex Consumption version left in the storage account, when it is still there",
                                 "The network, the Foundry resource of the agents and the Operator are there, the service is offered here, and the deploy identity may give the roles of the AI Gateway",
                                 "The base, the Foundry resource and the rights that the AI security needs are there",
                                 "The AI Gateway is there, the provider is registered, the component reports its endpoints and the gateway's identity may send to them"])
        container = [b for b in self.steps if b.startswith("name: Remove what the Flex Consumption version left")][0]
        self.assertEqual(re.findall(r"az role assignment (\w+)", container), ["list", "delete"], "it lists what is assigned on the container and deletes that, and does nothing else with a role")
        self.assertIn('--scope "$container"', container)
        self.assertIn('--ids "$id"', container)
        self.assertNotIn("Retire the deploy identity's right to send", self.text)
        self.assertNotIn("Data Sender", self.text)

    def test_the_actions_that_made_objects_on_the_owners_api_management_instance_are_gone_with_their_steps_and_the_key_they_read(self):
        # The owner ordered the undo of what Meternaut added to his instance (2026-11-07, AGENTS.md rule 15 (c)): the actions gateway-prepare, gateway and contract, and every step that looked at the
        # instance, its identity or its loggers, or read the contract's key, are gone. A person removed the objects by hand.
        offered = re.findall(r"- (\S+)", re.search(r"options:\n((?:          - .+\n)+)", self.text).group(1))
        for gone in ("gateway-prepare", "gateway", "contract"):
            self.assertNotIn(gone, offered)
            self.assertNotIn(f"inputs.action == '{gone}'", self.text)
        for word in ("listSecrets", "primaryKey", "GATEWAY_SMOKE_KEY", "environment-smoke", "check_limits", "CHECK_LIMITS", "environment/gateway", "contract.json", "contract-policy", "contract_files",
                     "GATEWAY_RESOURCE_ID", "GATEWAY_PRINCIPAL_ID", "GATEWAY_CLIENT_ID", "RECORDING_FRAGMENTS", "Microsoft.ApiManagement/service", "--apim", "/loggers", "identity list", "CONTRACT_"):
            self.assertNotIn(word, self.text, word)
        self.assertNotRegex(self.text, r"(?<!ai)gateway-prep\.py", "the tool that read and changed the instance is gone (tools/aigateway-prep.py is the AI Gateway's own)")
        names = self.names()
        for old in ("Read the gateway and its Application Insights", "Make the gateway identity", "Work out the settings with the identity's principal", "Find the gateway identity",
                    "Attach the identity to the gateway, keeping what it has", "Add the Application Insights logger that the module expects", "Wait until the gateway has finished updating",
                    "The gateway is ready for the Citadel module", "What the Citadel module would change in the gateway", "Add the Citadel module's objects to the gateway", "What the gateway holds now",
                    "What the first contract would change in the gateway", "Add the first contract to the gateway", "Test the gateway with the contract's key"):
            self.assertNotIn(old, names, old)
        # no secret of the gateway's side is read any more: the owner deletes the repository secrets GATEWAY_RESOURCE_ID and GATEWAY_APPINSIGHTS_ID after the merge that retired the usage recording (2026-11-07)
        self.assertNotIn("GATEWAY_APPINSIGHTS_ID", self.text)
        self.assertNotIn("secrets.GATEWAY_", self.text)

    def test_the_settings_step_looks_for_no_identity_of_a_gateway_and_runs_the_builder_twice_the_first_time_as_a_preview(self):
        (settings,) = [b for b in self.steps if b.startswith("name: Work out the settings\n")]
        self.assertEqual(settings.count("--preview"), 1, "the first pass gives the names before the facts of the other steps are known; the final build is a plain one")
        self.assertIn('policies="--aigateway-policies environment/aigateway/policies.json"', settings)
        self.assertEqual(settings.count("tools/environment-params.py build"), 2)
        self.assertNotIn("az identity", settings)
        for label in ("environment", "base", "foundry", "cases", "operator", "planted"):
            self.assertIn(f"--label {label}\n", settings)
        for label in ("recording", "logger", "eventhub-loggers", "kit", "contract"):
            self.assertNotIn(f"--label {label}", settings)

    def names(self):
        return [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def test_every_step_that_publishes_or_starts_a_job_names_the_actions_it_runs_in_and_never_what_if(self):
        found = 0
        for block in self.steps:
            if "--script operator/publish.sh" in block or "--script operator/run-tool.sh" in block:
                found += 1
                condition = re.search(r"(?m)^        if: (.+)$", block)
                self.assertIsNotNone(condition, block[:80])
                self.assertNotIn("what-if", condition.group(1))
                self.assertNotIn("always()", condition.group(1))
        self.assertEqual(found, 10, "one publish and nine job starts, all in the Operator's container: the publish of the cases app, the check tool that sends the control event, the health check of the cases app, the measurement of the web page's answering time, the check of the web page's front door, the check of the AI Gateway, and the four checks of the AI security (the second reader of the drift of the agents, the evaluations, the red team and the Agent 365 check)")
        for block in self.steps:
            for word in ("az functionapp deployment source config-zip", "/api/zipdeploy", "az webapp deploy", "az webapp deployment"):
                self.assertNotIn(word, block, f"no step publishes from the runner: {word} is in {block[:80]!r}")

    def test_the_base_is_deployed_read_back_and_waited_for_in_that_order_and_for_its_action_only(self):
        order = ["Deploy the base", "Read the storage account back from Azure, which has no public network access and no key",
                 "Wait until the landing zone has registered the base's private endpoints in the central zones", "What the project's resource group holds now"]
        names = self.names()
        positions = [names.index(name) for name in order]
        self.assertEqual(positions, sorted(positions))
        for name in order:
            self.assertIn("if: inputs.action == 'base'", self.steps[names.index(name)], name)
        deploy = self.steps[names.index("Deploy the base")]
        self.assertIn("--template environment/base/main.bicep", deploy)
        self.assertIn('--parameters "$RUNNER_TEMP/base.parameters.json"', deploy)
        self.assertIn("--output storageAccountName", deploy)
        self.assertIn("EXPECTED_STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", deploy)
        self.assertEqual(self.text.count("--template environment/base/main.bicep"), 2, "the preview and the deploy, nothing else")
        self.assertNotIn("recording", self.text.replace("the usage recording", "").replace("The usage recording", ""), "the action recording is the action base now: no step, label or file name of the old one is left")

    def test_the_storage_account_is_read_back_after_its_deploy_in_the_base_only_and_the_step_only_reads(self):
        (block,) = [b for b in self.steps if b.startswith("name: Read the storage account back from Azure")]
        self.assertIn("if: inputs.action == 'base'", block)
        self.assertEqual(re.findall(r"az (\S+ \S+)", re.sub(r"(?m)^\s*#.*$", "", block)), ["rest --method"])
        self.assertIn("--method get", block)
        self.assertIn('providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"', block)
        self.assertIn('--url "https://management.azure.com${account}?api-version=2023-05-01"', block)
        for word in ("properties.publicNetworkAccess", "properties.allowSharedKeyAccess", "privateEndpointConnections"):
            self.assertIn(word, block)
        self.assertIn("Public network access is '$access', not 'Disabled'.", block)
        self.assertIn("Shared Key access is not off", block)
        self.assertIn("fewer than three private endpoint connections (blob, queue and table)", block)
        self.assertNotIn("Microsoft.EventHub", block)

    def test_the_deletes_of_the_workflow_are_few_and_everything_of_the_usage_recording_the_old_model_account_and_the_event_hubs_namespace_goes_through_the_one_tool_of_retire_old(self):
        self.assertEqual(self.text.count("az resource delete"), 0, "the Logic App version of the usage recording was removed by four of them: the actions retire-old and retire-event-hubs delete what is left, with a tool that is tested")
        self.assertEqual(len(re.findall(r"(?m)^.*\baz (?:\S+ )*?(?:--method )?delete\b.*$", self.text)), 5, "no other delete, of any kind, in the workflow's own steps (the app of the other plan kind, its plan, its private endpoint and the role assignments that are in the way of the deploy are deleted by the tool of the step before the deploy of the cases, which is tested against a model of Azure): two of what the Flex version left in the storage account when the app goes back to Basic (the role on its container, then the container), one that takes the app's integration with an earlier subnet away, one that removes that subnet, and one that removes the retired runner identity of the first loop")
        (block,) = [b for b in self.steps if b.startswith("name: Delete what Meternaut does not use any more, in the project's resource group")]
        self.assertEqual(re.findall(r"python3 tools/(\S+) (\w+)", block), [("retire-old.py", "run")], "the tool is the only thing that deletes in that step")
        self.assertNotRegex(re.sub(r"(?m)^\s*#.*$", "", block), r"\baz\s")
        for word in ("usage-control", "ai-usage", "pii-usage", "cosmos", "aif-meternaut", "id-meternaut-usage", "func-meternaut-usage"):
            self.assertNotIn(word, re.sub(r"(?m)^\s*#.*$", "", block), f"{word}: the names are the tool's, which is tested, and not the workflow's")
        (event_hubs,) = [b for b in self.steps if b.startswith("name: Delete the Event Hubs namespace that carried the control event")]
        self.assertEqual(re.findall(r"python3 tools/(\S+) (\w+)", event_hubs), [("retire-old.py", "run")], "the same tool, with its second list, is the only thing that deletes in that step")
        self.assertNotRegex(re.sub(r"(?m)^\s*#.*$", "", event_hubs), r"\baz\s")
        for word in ("evhns", "pe-evhns", "azure-webjobs-eventhub", "servicebus"):
            self.assertNotIn(word, re.sub(r"(?m)^\s*#.*$", "", event_hubs), f"{word}: the names are the tool's, which is tested, and not the workflow's")

    def test_the_wait_before_an_app_is_started_waits_for_the_names_of_the_bases_private_endpoints_and_only_reads(self):
        (block,) = [b for b in self.steps if b.startswith("name: Wait until the landing zone has registered the base's private endpoints")]
        self.assertIn("BASE_ENDPOINTS: ${{ steps.params.outputs.base_endpoints }}", block)
        self.assertIn("az network private-endpoint dns-zone-group list", block)
        self.assertIn("exit 1", block)
        self.assertNotIn("--method", block)
        self.assertNotRegex(block, r"az \S+ (create|delete|update|set)\b")

    def test_nothing_in_the_workflow_reads_or_writes_a_key(self):
        for word in ("listKeys", "listConnectionStrings", "AccountKey", "SharedAccessKey", "primaryMasterKey", "az storage account keys", "--auth-mode key",
                     "az cosmosdb keys", "az eventhubs namespace authorization-rule", "az functionapp keys", "--connection-string", "az webapp deployment list-publishing"):
            self.assertNotIn(word, self.text, word)
        self.assertEqual(self.text.count("listSecrets"), 0, "the contract's own subscription key was read for one test of the gateway: the action that did it is gone (AGENTS.md rule 23)")

    def test_the_retirement_signs_in_again_before_it_deletes_because_the_first_credential_lasts_five_minutes(self):
        names = self.names()
        again = "Sign in to Azure again for the retirement, because the first sign-in's credential lasts five minutes"
        block = self.steps[names.index(again)]
        self.assertIn("if: inputs.action == 'retire-old'", block)
        self.assertIn("uses: azure/login@", block)
        self.assertEqual(self.text.count("uses: azure/login@"), 12, "the first sign-in, one more before the retirement of the old things, one more before the retirement of the Event Hubs namespace, one more before the publish of the cases, one more before the health check of the cases app in the Operator and one more after it, one more before the read-back of the Foundry resource, which follows a wait of up to 40 minutes, one more before the deploy of the AI Gateway, which follows the deploy of its subnet and a wait of up to 20 minutes for the landing zone's route table, one more before the limits, the built-in key and the read-back of the AI Gateway, one before the read-back of the AI security and one before the read-back of the telemetry exporter, which follow a deploy and are each given a credential of their own, and one before the read-back of the subnet and the enterprise policy of Power Platform, which follows a deploy and a wait of up to 20 minutes for the route table")
        self.assertLess(names.index("Sign in to Azure"), names.index(again))
        self.assertEqual(names.index(again) + 1, names.index("Delete what Meternaut does not use any more, in the project's resource group"), "the sign-in is right before the deletes: the first credential is old by then")
        self.assertIn("if: inputs.action == 'retire-old'", self.steps[names.index("Delete what Meternaut does not use any more, in the project's resource group")])
        again_event_hubs = "Sign in to Azure again for the retirement of the Event Hubs namespace, because the first sign-in's credential lasts five minutes"
        self.assertIn("if: inputs.action == 'retire-event-hubs'", self.steps[names.index(again_event_hubs)])
        self.assertIn("uses: azure/login@", self.steps[names.index(again_event_hubs)])
        self.assertEqual(names.index(again_event_hubs) + 1, names.index("Delete the Event Hubs namespace that carried the control event, its private endpoint and its checkpoint container, in the project's resource group"))

    def test_the_deploy_workflow_builds_with_the_python_of_the_functions_runtime_as_the_checks_do(self):
        # A run found it: the runner's own Python was 3.12, and the app's library needs 3.13. The checks had 3.13 and could not see it.
        names = self.names()
        title = "Set up Python 3.13, the runtime of the function app"
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}")]
        pinned = re.search(r"uses: (actions/setup-python@[0-9a-f]{40})", block)
        self.assertIsNotNone(pinned, "a full commit, as the lint wants")
        self.assertIn(f"uses: {pinned.group(1)}", text(".github/workflows/checks.yml"), "the very action that the checks use")
        self.assertIn('python-version: "3.13"', block)
        self.assertLess(names.index(title), names.index("The templates compile, for the check of their parameter files"))
        self.assertLess(names.index(title), names.index("Pack the cases app's sources for the Operator"), "the app is not built with its libraries on the runner any more, but the runtime is set up before anything of an app is packed")
        self.assertRegex(text("environment/cases/main.bicep"), r"3\.13", "the runtime that the app is made for")
        self.assertIn("python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)'", text("tools/build-function-app.sh"))

    def test_the_checks_build_the_whole_package_of_the_cases_app_so_that_a_missing_wheel_is_found_before_a_deploy_and_nothing_builds_the_usage_app(self):
        checks = text(".github/workflows/checks.yml")
        self.assertIn('bash tools/build-function-app.sh case-functions cases "$RUNNER_TEMP/case-functions" "$RUNNER_TEMP/case-functions.zip"', checks, "the checks build the whole package of the cases app")
        for source in (checks, self.text, text(".github/dependabot.yml")):
            self.assertNotIn("usage-functions", source)
        self.assertFalse((ROOT / "src" / "usage-functions").exists(), "the usage app's sources were removed on 2026-11-07, with the app")

    def test_the_identity_of_the_workflow_is_read_after_the_sign_in_and_before_the_step_that_looks_at_the_condition_of_its_right_and_no_setting_takes_it_any_more(self):
        names = self.names()
        self.assertLess(names.index("Sign in to Azure"), names.index("Read the object id of the signed-in identity"))
        self.assertLess(names.index("Read the object id of the signed-in identity"), names.index("Work out the settings"))
        title = "The network, the Foundry resource of the agents and the Operator are there, the service is offered here, and the deploy identity may give the roles of the AI Gateway"
        self.assertLess(names.index("Read the object id of the signed-in identity"), names.index(title))
        self.assertIn("DEPLOYER_ID: ${{ steps.me.outputs.oid }}", self.steps[names.index(title)], "the object id is used to look at the condition of the identity's right to assign roles")
        self.assertEqual(self.text.count("steps.me.outputs.oid"), 3, "the users of the identity's object id are the step that previews the AI security's templates (it looks first whether the identity holds a role that can write a policy assignment, because Azure refuses even the preview of a template that writes one), the step that reads the condition of its right to assign roles before the AI Gateway is made, and the step that reads, before the AI security is made, that the identity holds a role that can write a policy assignment: the step that retired its old right on the control hub is gone with the hub")
        # no template gives the identity a role any more, so the parameter builder takes no setting for it
        for path in (".github/workflows/deploy-hub.yml", ".github/workflows/checks.yml", "tools/environment-params.py"):
            self.assertNotIn("RECORDING_DEPLOYER_ID", text(path), path)
        self.assertNotIn("workflowPrincipalId", text("tools/environment-params.py"))

    def test_the_base_needs_no_gateway_identity_and_no_step_of_the_workflow_looks_for_one(self):
        # The owner ordered the undo of what Meternaut added to his API Management instance (2026-11-07): after it the instance has no gateway identity of ours, and the base makes no role
        # for one (environment/base/main.bicep), so it neither looks for it nor stops when it is not there: the settings step is the same for every action (test_workflow_scripts.py runs it).
        for word in ("gateway identity", "usage recording makes no role for the gateway identity", "steps.found.outputs", "steps.identity.outputs"):
            self.assertNotIn(word, self.text, word)
        (settings,) = [b for b in self.steps if b.startswith("name: Work out the settings\n")]
        self.assertNotIn("case \"$ACTION\" in\n            what-if|gateway-prepare|gateway|recording)", settings)
        self.assertNotIn("the role assignment is shown with a placeholder", settings)
        self.assertNotIn("makes no role for the gateway identity", settings)
        self.assertNotIn('preview="--preview"', settings, "no fact of the owner's instance can be missing, so no final build is a preview")


class Cases(unittest.TestCase):
    """The first cases (environment/cases/main.bicep): what it makes, what it only uses, and who may do what with it."""

    def setUp(self):
        self.source = text("environment/cases/main.bicep")
        self.code = re.sub(r"//.*", "", self.source)
        self.found = resources(self.source)

    def test_it_makes_only_its_own_integration_subnet_that_subnets_group_and_the_apps_private_endpoint_and_no_dns_storage_account_or_namespace(self):
        for word in ("Microsoft.ApiManagement", "privateDnsZones", "virtualNetworkPeerings", "routeTables", "privateDnsZoneGroups",
                     "Microsoft.DocumentDB"):
            self.assertNotIn(word, self.code, word)
        self.assertEqual(self.code.count("Microsoft.Network/privateEndpoints"), 1, "the app's own endpoint, and no other")
        for name in ("vnet", "workspace", "insights", "storage", "blobService", "queueService", "sharedHostContainers", "privateEndpointSubnet"):
            self.assertRegex(self.source, rf"(?m)^resource {name} '[^']+' existing = ", name)
        made = sorted(name for name, (_, body) in self.found.items() if not re.search(rf"(?m)^resource {name} '[^']+' existing", self.source))
        self.assertEqual(made, ["authIdentity", "cardsQueue", "consoleSignIn", "controlQueue", "deploymentContainer", "functionApp", "functionAppEndpoint",
                                "functionOwnsHostContainers", "functionOwnsOwnPackage", "functionPublishesTelemetry", "functionUsesQueues",
                                "functionUsesTables", "historyWorkbook", "noBasicAuthForDeployment", "noBasicAuthForFtp", "plan",
                                "tracesRetention", "webNsg", "webSubnet"])
        for name in ("deploymentContainer", "functionOwnsOwnPackage"):
            self.assertTrue(self.found[name][1].startswith("if (isFlex) {"), f"{name}: only a Flex app has its own package container and the role on it")
        self.assertTrue(self.found["noBasicAuthForFtp"][1].startswith("if (!isFlex) {"), "a Flex Consumption app has no FTP endpoint")

    def test_the_plans_subnet_is_delegated_to_basic_plans_holds_nothing_else_and_is_the_one_that_the_model_side_lists_too(self):
        subnet, nsg = self.found["webSubnet"][1], self.found["webNsg"][1]
        self.assertIn("parent: vnet", subnet)
        self.assertIn("addressPrefix: webSubnetPrefix", subnet)
        self.assertIn("id: webNsg.id", subnet)
        self.assertIn("serviceName: 'Microsoft.Web/serverFarms'", subnet, "a Basic plan's integration needs it; the function subnet's delegation is Flex Consumption's")
        self.assertIn("defaultOutboundAccess: false", subnet)
        self.assertIn("securityRules: []", nsg)
        self.assertIn("var webSubnetName = 'snet-cases'", self.code)
        model_side = text("environment/main.bicep")
        self.assertIn("name: 'snet-cases'", model_side)
        self.assertNotIn("snet-web", model_side, "the first subnet lost the landing zone's route table and was replaced")
        self.assertNotIn("snet-web", self.code)
        self.assertIn("addressPrefix: webSubnetPrefix", model_side)
        self.assertIn("serviceName: 'Microsoft.Web/serverFarms'", model_side, "a run of the model-side action must not take the subnet away from the plan")
        self.assertRegex(self.code, r"(?m)^param webSubnetPrefix string$")
        self.assertRegex(model_side, r"(?m)^param webSubnetPrefix string$")

    def test_the_subnet_is_made_only_while_it_is_not_there_because_making_it_again_takes_the_landing_zones_route_table_away(self):
        # On 2026-11-05 the second deploy of this template made snet-web again; the landing zone's network manager had put a route table on it a minute after the first make,
        # the second make had none, and the app on the subnet lost its way to the landing zone's DNS and could not start.
        self.assertRegex(self.code, r"(?m)^param webSubnetExists bool = false$")
        self.assertTrue(self.found["webSubnet"][1].startswith("if (!isFlex && !webSubnetExists) {"), "the subnet is made only while it is not there, and only for a Basic app: a Flex app uses snet-func")
        self.assertNotIn("routeTable", self.code, "the route table is the landing zone's, not the template's")
        self.assertIn("virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, integrationSubnetName)", self.found["functionApp"][1],
                      "the app names the subnet by its id, which exists whether or not the template made it")
        self.assertIn("var integrationSubnetName = isFlex ? functionSubnetName : webSubnetName", self.code)
        self.assertIn("var functionSubnetName = 'snet-func'", self.code, "the Flex app uses the subnet that the model side made for the usage recording: the owner's network is small and makes no new subnet")
        self.assertNotIn("webSubnet.id", self.code)

    def test_no_key_is_read_or_written_anywhere(self):
        for word in ("listKeys", "listConnectionStrings", "listSecrets", "listAccountSas", "listServiceSas", "AccountKey", "SharedAccessKey", "primaryKey", "@secure",
                     "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING", "SecurityControl", "optOut", "allowSharedKeyAccess: true", "disableLocalAuth: false"):
            self.assertNotIn(word, self.code, word)
        self.assertEqual(self.code.count("ConnectionString"), 1, "the telemetry's connection string names the component and holds no secret that ingestion accepts")
        self.assertIn("{ name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }", self.code)
        outputs = [line for line in self.code.splitlines() if line.startswith("output ")]
        self.assertEqual(len(outputs), 8)
        for line in outputs:
            for word in ("listKeys", "ConnectionString", "AccountKey", "primaryKey"):
                self.assertNotIn(word, line, line)

    def test_the_roles_are_the_ones_that_each_caller_needs_and_nothing_wider(self):
        guids = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.code))
        self.assertEqual(guids, {
            "b7e6dc6d-f1e8-4753-8033-0f276bb0955b",  # Storage Blob Data Owner
            "974c5e8b-45b9-4653-ba55-5f855dd0fb88",  # Storage Queue Data Contributor
            "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3",  # Storage Table Data Contributor
            "3913510d-42f4-4e42-8a64-420c390055eb",  # Monitoring Metrics Publisher
        }, "no Event Hubs role here: the Operator puts the control message in the queue, in its own template, and the app's queue role covers its trigger")
        assignments = {name: body for name, (kind, body) in self.found.items() if kind == "Microsoft.Authorization/roleAssignments"}
        self.assertEqual(sorted(assignments), ["functionOwnsHostContainers", "functionOwnsOwnPackage", "functionPublishesTelemetry",
                                               "functionUsesQueues", "functionUsesTables"])
        for name, body in assignments.items():
            self.assertIn("principalType: 'ServicePrincipal'", body, name)
        scopes = {name: re.search(r"(?m)^  scope: (.+)$", body).group(1) for name, body in assignments.items()}
        self.assertEqual(scopes, {"functionOwnsHostContainers": "sharedHostContainers[i]", "functionOwnsOwnPackage": "deploymentContainer",
                                  "functionUsesQueues": "storage", "functionUsesTables": "storage",
                                  "functionPublishesTelemetry": "insights"})
        self.assertIn("storageQueueDataContributorRoleId", assignments["functionUsesQueues"], "the app's queue role is on the whole account, for its host, and covers the control queue and its poison queue")
        self.assertNotIn("controlQueue", " ".join(scopes.values()), "no role of its own for the trigger: the host's role covers it")
        self.assertNotIn("Data Receiver", self.source)
        self.assertNotIn("Data Sender", self.source.replace("The roles that the workflow's identity held on the old control hub (Azure Event Hubs Data Sender) went with the Event Hubs namespace, which the action retire-event-hubs deletes.", ""))

    def test_every_role_of_the_function_app_is_for_its_own_system_assigned_identity_and_has_the_name_that_the_first_step_gave_it(self):
        # The second step of the move to a system-assigned identity makes no new assignment on an estate where the first step has run: the names are the same. A name has to be known when
        # the deployment starts and the identity's principal id is not, so the names are seeded with the app's id (Bicep error BCP120 otherwise).
        names = {"functionOwnsHostContainers": "guid(sharedHostContainers[i].id, functionApp.id, storageBlobDataOwnerRoleId)",
                 "functionOwnsOwnPackage": "guid(deploymentContainer.id, functionApp.id, storageBlobDataOwnerRoleId)",
                 "functionUsesQueues": "guid(storage.id, functionApp.id, storageQueueDataContributorRoleId)",
                 "functionUsesTables": "guid(storage.id, functionApp.id, storageTableDataContributorRoleId)",
                 "functionPublishesTelemetry": "guid(insights.id, functionApp.id, monitoringMetricsPublisherRoleId)"}
        held = {name for name, (kind, body) in self.found.items() if "functionApp.identity.principalId" in body}
        self.assertEqual(held, set(names), "the roles of the app are for its own identity, and the workflow's is not")
        for name, expected in names.items():
            self.assertIn(f"  name: {expected}\n", self.found[name][1], name)
        self.assertEqual(len(set(names.values())), len(names), "each name is of its own")
        self.assertEqual(set(names) & depends_on(self.found["functionApp"][1]), set(), "the app does not wait for roles that wait for the app")
        for word in ("casesIdentity", "id-${workload}-cases", "id-meternaut-cases"):
            self.assertNotIn(word, self.code, f"{word}: the user-assigned identity of the Watch is gone from the template")

    def test_the_blob_role_reaches_the_two_shared_host_containers_and_a_flex_apps_own_container_and_never_the_usage_recordings_package(self):
        self.assertIn("var deploymentContainerName = 'app-package-cases'", self.code, "a Flex app keeps its package in a container of its own, a Basic app on its plan's own storage")
        self.assertEqual(self.code.count("app-package-cases"), 1)
        self.assertIn("var sharedHostContainerNames = [\n  'azure-webjobs-hosts'\n  'azure-webjobs-secrets'\n]", self.code)
        self.assertNotIn("azure-webjobs-eventhub", self.source.replace("// ", ""), "the checkpoint container of the Event Hubs trigger is not used or named any more: the action retire-event-hubs deletes it")
        self.assertNotIn("app-package-usage", self.source)
        for name, (kind, body) in self.found.items():
            if kind == "Microsoft.Authorization/roleAssignments" and "storageBlobDataOwnerRoleId" in body:
                self.assertNotRegex(body, r"(?m)^  scope: storage$", name)
        self.assertNotIn("app-package-usage", text("environment/base/main.bicep"), "the container that this app must not reach belonged to the usage app, which was removed on 2026-11-07: no template makes it any more")

    def test_the_plan_is_flex_consumption_or_basic_as_casesAppPlan_says_and_the_two_plans_have_the_names_that_the_parameter_builder_removes_them_by(self):
        # The action cases removes the plan of the other kind by its exact name, so the template and tools/environment-params.py hold the same names and tiers.
        import importlib.util
        spec = importlib.util.spec_from_file_location("environment_params", ROOT / "tools" / "environment-params.py")
        params = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(params)
        self.assertRegex(self.code, r"(?m)^@allowed\(\[\n  'Flex'\n  'Basic'\n\]\)\nparam casesAppPlan string = 'Flex'$")
        self.assertEqual(params.CASES_APP_PLANS, ("Flex", "Basic"))
        self.assertEqual(params.CASES_APP_PLAN, "Flex", "the web page is on Flex Consumption because the owner ordered it, on 2026-11-07 and again on 2026-11-08 after the measurement of the platform's hold (docs/proposals/07-private-by-default.md): it goes back to Basic only on his word")
        plan = self.found["plan"][1]
        self.assertIn("var isFlex = casesAppPlan == 'Flex'", self.code)
        self.assertIn("name: isFlex ? 'plan-${workload}-cases' : 'plan-${workload}-cases-basic'", plan)
        self.assertEqual(params.CASES_PLAN_NAMES, {"Flex": "plan-meternaut-cases", "Basic": "plan-meternaut-cases-basic"})
        self.assertIn("kind: isFlex ? 'functionapp' : 'linux'", plan)
        self.assertRegex(plan, r"sku: isFlex \? \{\n    name: 'FC1'\n    tier: 'FlexConsumption'\n  \} : \{\n    name: 'B1'\n    tier: 'Basic'\n  \}")
        self.assertEqual(params.CASES_PLAN_TIERS, {"Flex": "FlexConsumption", "Basic": "Basic"})
        self.assertIn("reserved: true", plan)
        self.assertEqual(params.CASES_SUBNET_NAMES, {"Flex": "snet-func", "Basic": "snet-cases"})
        self.assertIn("var webSubnetName = 'snet-cases'", self.code)
        self.assertIn("var functionSubnetName = 'snet-func'", self.code)

    def test_a_flex_app_has_its_own_package_container_one_instance_a_web_concurrency_of_fifty_and_no_always_ready_instance(self):
        body = self.found["functionApp"][1]
        self.assertIn("functionAppConfig: isFlex ? {", body)
        flex = body[body.index("functionAppConfig: isFlex ? {"):body.index("    } : null\n")]
        self.assertIn("value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'", flex)
        self.assertIn("type: 'blobContainer'", flex)
        self.assertRegex(flex, r"authentication: \{\n\s+type: 'SystemAssignedIdentity'\n\s+\}", "the package is read with the app's own identity: no key, no connection string")
        self.assertNotIn("userAssignedIdentityResourceId", flex)
        self.assertIn("maximumInstanceCount: 1", flex, "a run waits for models, a timer must not run twice at once, and a control message starts one run")
        self.assertRegex(flex, r"triggers: \{\n\s+http: \{\n\s+perInstanceConcurrency: 50\n\s+\}\n\s+\}",
                         "a Python app on Flex Consumption has an HTTP concurrency of one by default (Learn), and with one instance at the most the platform let one request reach the app a minute: the host log of 2026-11-08 has no two requests less than 60 seconds apart")
        self.assertIn("instanceMemoryMB: 2048", flex)
        self.assertRegex(flex, r"siteUpdateStrategy: \{\n\s+type: 'RollingUpdate'\n\s+\}",
                         "the default, Recreate, ends the executions that are in progress when a site update comes (a deployment, a tag, a setting): the Watch of 2026-11-09 06:46 UTC lost its telemetry three minutes into the drain, so nobody saw it end")
        self.assertNotIn("alwaysReady", self.code, "no always-ready instance: the app scales to zero and bills nothing while it is idle")
        self.assertRegex(flex, r"runtime: \{\n\s+name: 'python'\n\s+version: '3.13'\n\s+\}")
        self.assertEqual(self.found["deploymentContainer"][0], "Microsoft.Storage/storageAccounts/blobServices/containers")
        self.assertIn("publicAccess: 'None'", self.found["deploymentContainer"][1])
        for setting in ("linuxFxVersion", "alwaysOn", "ftpsState", "vnetRouteAllEnabled"):
            self.assertRegex(body, rf"{setting}: isFlex \? null : ", f"{setting} is not set on a Flex Consumption app")
        basic_only = self.code[self.code.index("var basicOnlyAppSettings = isFlex ? [] : ["):self.code.index("resource functionApp ")]
        for setting in ("FUNCTIONS_EXTENSION_VERSION", "FUNCTIONS_WORKER_RUNTIME", "WEBSITE_RUN_FROM_PACKAGE", "WEBSITES_CONTAINER_START_TIME_LIMIT", "SCM_DO_BUILD_DURING_DEPLOYMENT", "ENABLE_ORYX_BUILD"):
            self.assertIn(f"name: '{setting}'", basic_only, f"{setting}: a Flex Consumption app refuses it")
            self.assertEqual(self.code.count(f"name: '{setting}'"), 1, setting)
        self.assertIn("appSettings: concat(basicOnlyAppSettings, [", body)

    def test_a_basic_app_is_the_plan_of_the_web_page_with_the_plan_always_on_an_identity_for_everything_and_no_password_for_its_deployment(self):
        plan = self.found["plan"][1]
        self.assertIn("name: 'B1'", plan)
        self.assertIn("tier: 'Basic'", plan)
        self.assertIn("kind: isFlex ? 'functionapp' : 'linux'", plan)
        self.assertIn("reserved: true", plan)
        body = self.found["functionApp"][1]
        self.assertIn("kind: 'functionapp,linux'", body)
        self.assertIn("type: 'SystemAssigned, UserAssigned'", body, "the app's own identity, and the one that only presents the console's sign-in")
        self.assertEqual(re.findall(r"'\$\{(\w+)\.id\}': \{\}", body), ["authIdentity"], "the only user-assigned identity of the app")
        self.assertIn("virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, integrationSubnetName)", body)
        self.assertIn("vnetRouteAllEnabled: isFlex ? null : false", body, "only the private ranges go through the subnet, as for the Flex app that this replaced")
        self.assertIn("linuxFxVersion: isFlex ? null : 'PYTHON|3.13'", body)
        self.assertIn("alwaysOn: isFlex ? null : true", body, "timers and the control queue's trigger need an instance that is always there on a Basic plan")
        self.assertIn("ftpsState: isFlex ? null : 'Disabled'", body)
        for setting, value in (("FUNCTIONS_EXTENSION_VERSION", "~4"), ("FUNCTIONS_WORKER_RUNTIME", "python"), ("WEBSITE_RUN_FROM_PACKAGE", "1"),
                               ("WEBSITES_CONTAINER_START_TIME_LIMIT", "600"), ("SCM_DO_BUILD_DURING_DEPLOYMENT", "false"), ("ENABLE_ORYX_BUILD", "false")):
            self.assertIn(f"{{ name: '{setting}', value: '{value}' }}", self.code, setting)
        for setting in ("AzureWebJobsStorage__credential", "AzureWebJobsStorage__queueServiceUri", "APPLICATIONINSIGHTS_AUTHENTICATION_STRING"):
            self.assertIn(f"name: '{setting}'", body, setting)
        self.assertIn("{ name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }", body)
        self.assertIn("{ name: 'AzureWebJobsStorage__queueServiceUri', value: storage.properties.primaryEndpoints.queue }", body, "the trigger of the control queue reads it through the host storage connection")
        self.assertNotIn("EventHubConnection", self.code, "no connection to an Event Hubs namespace: the trigger is a queue trigger on the host storage")
        self.assertIn("{ name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'Authorization=AAD' }", body, "no client id: the app's own identity is the one that signs the telemetry")
        settings_code = re.sub(r"//.*", "", body)
        for setting in ("AzureWebJobsStorage__clientId", "AZURE_CLIENT_ID", "ClientId="):
            self.assertNotIn(setting, settings_code, f"{setting}: without a client id a connection uses the app's system-assigned identity")
        for setting in ("'AzureWebJobsStorage'", "AzureWebJobsDashboard", "WEBSITE_CONTENT", "StorageAccountConnectionString", "WEBSITE_RUN_FROM_PACKAGE_BLOB_MI_RESOURCE_ID"):
            self.assertNotIn(setting, body, setting)
        self.assertEqual(self.code.count("allow: false"), 2, "no password for the deployment site and none for FTP")
        self.assertIn("name: 'scm'", self.found["noBasicAuthForDeployment"][1])
        self.assertIn("name: 'ftp'", self.found["noBasicAuthForFtp"][1])
        self.assertIn("httpsOnly: true", self.code)
        self.assertIn("minTlsVersion: '1.2'", self.code)

    def test_the_function_app_starts_after_its_subnet_its_container_and_its_queue_and_never_waits_for_roles_that_wait_for_its_identity(self):
        self.assertEqual(depends_on(self.found["functionApp"][1]), {"webSubnet", "deploymentContainer", "controlQueue"},
                         "the roles of the app's own identity need the app, so the app cannot wait for them: the host retries until they are there")

    def test_the_control_queue_is_made_in_the_host_storage_account_and_the_app_is_told_its_name_and_reads_it_through_the_host_connection(self):
        self.assertIn("var controlQueueName = 'cases-control'", self.code)
        kind, body = self.found["controlQueue"]
        self.assertEqual(kind, "Microsoft.Storage/storageAccounts/queueServices/queues")
        self.assertIn("parent: queueService", body)
        self.assertIn("name: controlQueueName", body)
        self.assertNotIn("properties", body, "a queue with the defaults: no metadata and nothing else to hold")
        self.assertIn("resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' existing = {\n  parent: storage\n  name: 'default'\n}", self.code)
        self.assertIn("{ name: 'CASES_CONTROL_QUEUE_NAME', value: controlQueueName }", self.code)
        app = self.found["functionApp"][1]
        for setting in ("AzureWebJobsStorage__credential", "AzureWebJobsStorage__blobServiceUri", "AzureWebJobsStorage__queueServiceUri", "AzureWebJobsStorage__tableServiceUri"):
            self.assertIn(f"name: '{setting}'", app, f"{setting}: the host storage connection that the trigger uses is identity-based")
        self.assertEqual(re.findall(r"name: 'AzureWebJobsStorage[^']*'", app), ["name: 'AzureWebJobsStorage__credential'", "name: 'AzureWebJobsStorage__blobServiceUri'",
                                                                                  "name: 'AzureWebJobsStorage__queueServiceUri'", "name: 'AzureWebJobsStorage__tableServiceUri'"],
                         "no connection string, key or SAS for the host storage: the four settings of the identity-based connection, and nothing else")
        for word in ("poison", "maxDequeueCount"):
            self.assertNotIn(word, self.code, f"{word}: the host makes the poison queue itself, and the template does not name it")

    def test_the_history_is_kept_for_a_year_in_the_traces_table_and_shown_by_one_workbook(self):
        self.assertRegex(self.code, r"(?m)^param historyRetentionDays int = 365$")
        self.assertIn("name: 'AppTraces'", self.found["tracesRetention"][1])
        self.assertIn("retentionInDays: historyRetentionDays", self.found["tracesRetention"][1])
        self.assertIn("loadTextContent('history.workbook.json')", self.found["historyWorkbook"][1])
        self.assertIn("__APPINSIGHTS_ID__", self.found["historyWorkbook"][1])

    def test_the_console_signs_people_in_with_a_federated_credential_and_holds_no_secret(self):
        body = self.found["consoleSignIn"][1]
        self.assertIn("if (!empty(consoleAppClientId))", self.source, "nothing is set up, and the console refuses, until there is an app registration")
        self.assertIn("requireAuthentication: true", body)
        self.assertIn("unauthenticatedClientAction: 'RedirectToLoginPage'", body)
        self.assertIn("clientSecretSettingName: 'OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID'", body)
        self.assertIn("identities: consoleUserObjectIds", body)
        self.assertRegex(body, r"(?s)tokenStore: \{\s+enabled: false")
        self.assertIn("requireHttps: true", body)
        self.assertNotRegex(self.code, r"clientSecret\s*:", "the app registration trusts an identity: there is no client secret")
        self.assertNotIn("excludedPaths: [\n        '/ok", body)
        self.assertEqual(re.findall(r"'(/[^']*)'", re.search(r"excludedPaths: \[(.*?)\]", body, re.S).group(1)), ["/healthz"])
        self.assertNotIn("/arm", body, "the return address of the Azure sign-in is behind the platform's sign-in like every route but /healthz")
        self.assertIn("{ name: 'OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID', value: signInIsSetUp ? authIdentity.properties.clientId : '' }", self.code, "the setting that the sign-in reads is set whenever the sign-in is")

    def test_meternaut_holds_no_right_to_change_azure_so_the_app_has_its_own_identity_and_the_one_of_the_sign_in_holds_no_role(self):
        # A change runs with the token of the person who approves it: no identity of this template may write in Azure, and none is made for that.
        for name, (kind, body) in self.found.items():
            if kind == "Microsoft.Authorization/roleAssignments":
                self.assertNotIn("authIdentity", body, name)
        for word in ("runnerIdentity", "-runner", "WRITER_", "writer", "roleDefinitions@", "Microsoft.Compute", "Microsoft.Network/publicIPAddresses"):
            self.assertNotIn(word, self.code, word)
        self.assertEqual(re.findall(r"'\$\{(\w+)\.id\}': \{\}", self.found["functionApp"][1]), ["authIdentity"],
                         "the one user-assigned identity only presents the sign-in; the app's own system-assigned identity has no entry here")
        self.assertIn("type: 'SystemAssigned, UserAssigned'", self.found["functionApp"][1])
        self.assertEqual(sorted(name for name, (kind, _) in self.found.items() if kind == "Microsoft.ManagedIdentity/userAssignedIdentities"), ["authIdentity"])
        self.assertIn("{ name: 'OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID', value: signInIsSetUp ? authIdentity.properties.clientId : '' }", self.code)
        outputs = re.findall(r"(?m)^output (\w+) ", self.code)
        self.assertEqual([o for o in outputs if "dentity" in o], ["authIdentityPrincipalId", "authIdentityClientId"])
        self.assertIn("output casesSystemPrincipalId string = functionApp.identity.principalId", self.code)
        self.assertIn("casesSystemPrincipalId", outputs)

    def test_the_app_is_told_where_it_keeps_its_records_where_it_may_run_a_change_how_a_person_signs_in_to_azure_and_who_may_use_it(self):
        body = self.found["functionApp"][1]
        for setting in ("STORE_ACCOUNT_NAME", "CHANGE_SCOPES", "SIGNIN_TENANT_ID", "SIGNIN_CLIENT_ID", "CONSOLE_HOST", "CONSOLE_PEOPLE",
                        "MAIL_SENDER", "PLAN_TTL_HOURS", "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"):
            self.assertIn(f"name: '{setting}'", body, setting)
        for gone in ("WRITER_RESOURCE_GROUP", "WRITER_SUBSCRIPTION_ID", "WRITER_CLIENT_ID", "APPROVAL_DELAY_SECONDS", "approvalDelaySeconds"):
            self.assertNotIn(gone, self.source, f"{gone}: Meternaut holds no right to change Azure, and an approval has no window to cancel in")
        self.assertIn("{ name: 'STORE_ACCOUNT_NAME', value: storage.name }", self.code)
        # One list of the groups where a change may be made: exactly the one group where Meternaut plants waste of its own, and no other (the app's own gate on top of it is in the code).
        self.assertIn("{ name: 'CHANGE_SCOPES', value: '${subscription().subscriptionId}/${resourceGroup().name}' }", self.code)
        for older in ("CHANGE_RESOURCE_GROUP", "CHANGE_SUBSCRIPTION_ID"):
            self.assertNotIn(older, self.code, f"{older} is replaced by the list of the groups where a change may be made")
        # The app takes the three settings of the sign-in to Azure together or not at all (src/case-functions/cases/loop_config.py), and the Watch fails with a part of them:
        # until the console's app registration exists none is set.
        self.assertIn("var signInIsSetUp = !empty(consoleAppClientId)", self.code)
        self.assertIn("{ name: 'SIGNIN_TENANT_ID', value: signInIsSetUp ? tenant().tenantId : '' }", self.code)
        self.assertIn("{ name: 'SIGNIN_CLIENT_ID', value: consoleAppClientId }", self.code)
        self.assertIn("{ name: 'OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID', value: signInIsSetUp ? authIdentity.properties.clientId : '' }", self.code)
        self.assertEqual(self.code.count("signInIsSetUp"), 3, "the variable is used by those two settings and by nothing else")
        self.assertIn("clientId: consoleAppClientId", self.found["consoleSignIn"][1], "the app registration of the platform's sign-in is the one that an approval signs in with")

    def test_the_settings_of_the_loop_are_the_ones_the_app_reads(self):
        config = text("src/case-functions/cases/loop_config.py")
        names = set(re.findall(r'^([A-Z_]+) = "\1"$', config, re.M))
        left_to_their_defaults = {"PLANTED_TAG", "RECHECK_DAYS"}
        read_only_without_the_list = {"CHANGE_RESOURCE_GROUP", "CHANGE_SUBSCRIPTION_ID"}  # the two older settings of one group: read only when CHANGE_SCOPES is not set
        self.assertIn("CHANGE_SCOPES", names)
        for name in names - left_to_their_defaults - read_only_without_the_list:
            self.assertTrue(f"name: '{name}'" in self.code, f"the app reads {name} and the template does not set it")
        self.assertTrue("CONSOLE_PEOPLE" in self.code, "the people are read by people.py")

    def test_the_agents_of_the_foundry_resource_are_reached_with_six_settings_and_the_investigation_is_off_without_an_address(self):
        body = self.found["functionApp"][1]
        for line in ("{ name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }", "{ name: 'FOUNDRY_MODEL_INVESTIGATOR', value: foundryModelInvestigator }",
                     "{ name: 'FOUNDRY_MODEL_SKEPTIC', value: foundryModelSkeptic }", "{ name: 'INVESTIGATE', value: empty(foundryProjectEndpoint) ? 'off' : 'on' }",
                     "{ name: 'INVESTIGATE_MAX_CALLS', value: string(investigateMaxCalls) }", "{ name: 'INVESTIGATE_MAX_SECONDS', value: string(investigateMaxSeconds) }"):
            self.assertIn(line, body)
        for line in ("param foundryProjectEndpoint string = ''", "param foundryModelInvestigator string = 'gpt-5.5'", "param foundryModelSkeptic string = 'gpt-6.1-sol'",
                     "param investigateMaxCalls int = 40", "param investigateMaxSeconds int = 600"):
            self.assertRegex(self.code, rf"(?m)^{re.escape(line)}$")
        self.assertEqual(len(re.findall(r"name: '(?:FOUNDRY_\w+|INVESTIGATE\w*)'", body)), 6)
        self.assertEqual(self.code.count("foundryProjectEndpoint"), 3, "the parameter, the setting and the switch, and nothing else reads it")
        for word in ("listKeys", "apiKey", "ApiKey", "key:", "credentials"):
            self.assertNotIn(word, self.code[self.code.index("param foundryProjectEndpoint"):self.code.index("var tags")], word)
        self.assertEqual(self.code.count("Microsoft.CognitiveServices"), 0, "the role on the project is given by the template of the Foundry resource, which has to make the project first")

    def test_the_template_cannot_ask_for_more_of_the_investigation_than_the_code_accepts_and_starts_from_the_budget_that_the_code_starts_from(self):
        self.assertRegex(self.code, r"@minValue\(1\)\n@maxValue\(40\)\nparam investigateMaxCalls int = 40\n")
        self.assertRegex(self.code, r"@minValue\(30\)\n@maxValue\(600\)\nparam investigateMaxSeconds int = 600\n")
        constants = {(kind, what): value for kind, what, value in re.findall(r"(?m)^(LIMIT|DEFAULT)_INVESTIGATE_(CALLS|SECONDS) = (\d+)$",
                                                                              (ROOT / "src" / "case-functions" / "cases" / "config.py").read_text(encoding="utf-8"))}
        if not constants:
            self.skipTest("the code does not read the investigation settings yet; src/case-functions/tests/test_config.py holds the names of the template and of config.py together")
        self.assertEqual({what: value for (kind, what), value in constants.items() if kind == "LIMIT"}, {"CALLS": "40", "SECONDS": "600"},
                         "the largest value that the template takes is the largest that the code takes")
        template = dict(re.findall(r"(?m)^param (investigateMaxCalls|investigateMaxSeconds) int = (\d+)$", self.code))
        for name, what in (("investigateMaxCalls", "CALLS"), ("investigateMaxSeconds", "SECONDS")):
            if ("DEFAULT", what) in constants:
                self.assertEqual(template[name], constants[("DEFAULT", what)], f"{name}: the template and the code start from the same budget")

    def test_the_workbook_file_is_valid_json_and_only_reads_the_traces(self):
        import json
        raw = (ROOT / "environment" / "cases" / "history.workbook.json").read_text(encoding="utf-8")
        document = json.loads(raw)
        self.assertEqual(document["version"], "Notebook/1.0")
        self.assertIn("__APPINSIGHTS_ID__", raw)
        queries = re.findall(r'"query":\s*"((?:[^"\\]|\\.)*)"', raw)
        self.assertGreaterEqual(len(queries), 5)
        for query in queries:
            self.assertIn("meternaut_event", query)
            self.assertTrue(query.lstrip().startswith(("let ", "traces")), query[:40])
            for word in (".set", ".ingest", ".drop", ".create", ".alter", "externaldata"):
                self.assertNotIn(word, query, word)


class FunctionAppEndpoints(unittest.TestCase):
    """The private endpoint of the function app (the cases app and the console): in the endpoint subnet, with no DNS of its own, and written after every other write to the app. The usage app, which had
    one of the same kind, was removed on 2026-11-07."""

    TEMPLATES = ("environment/cases/main.bicep",)

    def setUp(self):
        self.sources = {path: text(path) for path in self.TEMPLATES}
        self.codes = {path: re.sub(r"//.*", "", source) for path, source in self.sources.items()}
        self.found = {path: resources(source) for path, source in self.sources.items()}

    def test_each_app_has_exactly_one_endpoint_of_the_group_sites_in_the_endpoint_subnet_named_after_the_app_and_tagged_like_the_rest(self):
        for path in self.TEMPLATES:
            found = self.found[path]
            kind, body = found["functionAppEndpoint"]
            self.assertEqual(kind, "Microsoft.Network/privateEndpoints", path)
            of_the_app = [name for name, (k, b) in found.items() if k == "Microsoft.Network/privateEndpoints" and "privateLinkServiceId: functionApp.id" in b]
            self.assertEqual(of_the_app, ["functionAppEndpoint"], f"{path}: one endpoint on the app")
            for line in ("  name: 'pe-${functionAppName}'\n", "  location: location\n", "  tags: tags\n", "      id: privateEndpointSubnet.id\n", "        name: 'sites'\n",
                         "          privateLinkServiceId: functionApp.id\n", "          groupIds: [\n            'sites'\n          ]\n"):
                self.assertIn(line, body, f"{path}: {line.strip()}")
            self.assertEqual(body.count("privateLinkServiceConnections"), 1, "one connection, to the app")
            self.assertEqual(body.count("groupIds"), 1, "and one group, `sites`: the name of the app and its deployment site share the endpoint")
            self.assertNotIn("manualPrivateLinkServiceConnections", body, "the connection is approved by the endpoint's owner, who is the owner of the app: no request to approve by hand")
            self.assertEqual(self.sources[path].count("var privateEndpointSubnetName = 'snet-pe'"), 1, path)
            self.assertRegex(self.sources[path], r"(?m)^resource privateEndpointSubnet 'Microsoft\.Network/virtualNetworks/subnets@[^']+' existing = \{\n  parent: vnet\n  name: privateEndpointSubnetName\n\}\n", path)

    def test_the_endpoint_is_written_with_the_version_of_the_other_endpoints_of_the_templates(self):
        versions = {path: set(re.findall(r"'Microsoft\.Network/privateEndpoints@([^']+)'", source)) for path, source in self.sources.items()}
        self.assertEqual(versions["environment/cases/main.bicep"], {"2025-05-01"})
        self.assertEqual(versions["environment/cases/main.bicep"], set(re.findall(r"'Microsoft\.Network/privateEndpoints@([^']+)'", text("environment/foundry/main.bicep"))),
                         "the Foundry resource's endpoint is written with the same version")
        self.assertEqual(set(re.findall(r"'Microsoft\.Network/privateEndpoints@([^']+)'", text("environment/base/main.bicep"))), {"2025-05-01"}, "and the base's")

    def test_no_dns_zone_no_link_and_no_zone_group_is_made_or_named_by_either_template_and_the_endpoints_hold_no_dns_setting(self):
        for path in self.TEMPLATES:
            self.assertNotRegex(self.codes[path], r"(?i)privateDns|virtualNetworkLinks|dnsZone|Microsoft\.Network/dns", f"{path}: the landing zone's policy registers the names of an endpoint in its central zones (AGENTS.md rule 19)")
            body = self.found[path]["functionAppEndpoint"][1]
            self.assertNotRegex(body, r"(?i)dns|zone", f"{path}: the endpoint's own body holds no DNS setting")
            self.assertNotIn("customDnsConfigs", body)

    def test_an_endpoint_is_written_after_every_other_write_to_its_app_because_the_connection_is_written_with_an_if_match(self):
        for path in self.TEMPLATES:
            found = self.found[path]
            children = {name for name, (_, body) in found.items() if re.search(r"(?m)^  (parent|scope): functionApp$", body)}
            self.assertEqual(children, {"noBasicAuthForDeployment"} | ({"noBasicAuthForFtp", "consoleSignIn"} if path.endswith("cases/main.bicep") else set()), path)
            self.assertLessEqual(children, depends_on(found["functionAppEndpoint"][1]), f"{path}: the endpoint waits for every child of the app that this template writes")
            self.assertNotIn("functionAppEndpoint", depends_on(found["functionApp"][1]), "the app is made first")
            for name in children:
                self.assertNotIn("functionAppEndpoint", depends_on(found[name][1]), name)
            others = {name for name, (_, body) in found.items() if "functionAppEndpoint" in depends_on(body)}
            self.assertEqual(others, set(), f"{path}: no other resource depends on the endpoint: it changes nothing that another resource reads, and no role is given on the app")

    def test_the_summary_of_cases_says_that_the_code_is_not_published_before_the_names_of_the_apps_endpoint_are_registered_and_what_a_stop_at_the_wait_means(self):
        workflow = text(".github/workflows/deploy-hub.yml")
        self.assertIn("and a private endpoint of its own for the console and its deployment site (the sub-resource \\`sites\\`), which the landing zone has registered in its central zone: the code is not "
                      "published before that, so that a later probe finds the names. The app's public network access is \\`$CASES_PUBLIC_ACCESS\\` (the constant "
                      "CASES_APP_PUBLIC_NETWORK_ACCESS in tools/environment-params.py).", workflow)
        self.assertIn("If they stop at the wait for the landing zone's policy, the app and its endpoint are made and the app was not given its code: the lines say that the endpoint is not registered yet.", workflow)
        for stale in ("not waited for", "nothing waits for its names", "operator-probe\\` shows whether the landing zone has registered its names"):
            self.assertNotIn(stale, workflow, "the apps' endpoints are waited for: a deployment of an app failed without the wait")

    def test_the_app_writes_its_public_access_from_a_parameter_so_that_the_value_is_never_left_to_the_platform(self):
        # Learn (Azure App Service access restrictions): a site whose publicNetworkAccess is not set has public access switched off by the first private endpoint that it gets. Writing the value
        # every time keeps the app public until the parameter says otherwise, and makes closing it one value.
        for path, name in (("environment/cases/main.bicep", "casesAppPublicNetworkAccess"),):
            self.assertRegex(self.codes[path], rf"(?m)^@allowed\(\[\n  'Enabled'\n  'Disabled'\n\]\)\nparam {name} string = 'Enabled'$", path)
            self.assertIn(f"    publicNetworkAccess: {name}\n", self.found[path]["functionApp"][1], path)
            self.assertEqual(len(re.findall(rf"\b{name}\b", self.codes[path])), 2, f"{path}: declared once and used once")


class AnAppsPrivateEndpointIsNeverAddedWithoutTheWait(unittest.TestCase):
    """What the first deploy of the usage app (removed on 2026-11-07; the finding holds for every app) found on 2026-11-06, in plain words. A Flex Consumption deployment ends with a call from the
    deployment site to the app's own host name. Right after the private endpoint of the app is made, that name is a CNAME of <app>.privatelink.azurewebsites.net, and the landing zone's central zone has no
    record of it for about ten minutes, until its policy registers the endpoint: the name does not resolve, and the last step of the deployment fails with "Deployment was successful but Reset all workers
    endpoint responded with Name or service not known". The publish step failed three times, although the package had been taken. So no template may make the private endpoint of an app unless the action that
    deploys it waits, before it publishes, until the landing zone has registered that endpoint in its central zone. A new app with an endpoint of its own has to be added to this test with its wait."""

    APPS = {
        "environment/cases/main.bicep": {
            "action": "cases", "variable": "CASES_ENDPOINTS", "output": "cases_endpoints", "deploy": "Deploy the first cases",
            "wait": "Wait until the landing zone has registered the cases app's private endpoint in the central zone",
            "login": "Sign in to Azure again for the publish of the cases, because the first sign-in's credential lasts five minutes",
            "build": "Pack the cases app's sources for the Operator", "publish": "Publish the cases to the function app from inside the network, in the Operator",
            "given": "The cases app was not given its code."},
    }

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}\n")]
        return block

    def script(self, title):
        body = self.step(title).split("        run: |\n", 1)[1]
        return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))

    def test_the_templates_that_make_the_endpoint_of_an_app_are_the_ones_whose_action_waits_for_it(self):
        makers = []
        for path in sorted((ROOT / "environment").rglob("*.bicep")):
            code = re.sub(r"//.*", "", path.read_text(encoding="utf-8").replace("\r\n", "\n"))
            if re.search(r"groupIds: \[\n\s+'sites'\n\s+\]", code):
                makers.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(makers, sorted(self.APPS), "a template that makes the private endpoint of an app is listed in this test with the step of its action that waits for the landing zone's policy to "
                                                    "register the endpoint: add the wait before adding the endpoint, or the first publish fails to resolve the app's own name")

    def test_each_of_those_actions_waits_for_the_zone_group_of_every_endpoint_in_its_list_after_its_deploy_and_before_it_publishes(self):
        for path, app in self.APPS.items():
            wait = self.step(app["wait"])
            self.assertIn(f"        if: inputs.action == '{app['action']}'\n", wait, path)
            self.assertIn(f"{app['variable']}: ${{{{ steps.params.outputs.{app['output']} }}}}", wait, "the list is the builder's, which names the zone of each endpoint")
            for word in ("az network private-endpoint dns-zone-group list", '--endpoint-name "$endpoint"', 'grep -qi "/$zone\\$" <<< "$zones"', "attempts=40", "sleep 60", "exit 1", app["given"],
                         "do not create a private DNS zone"):
                self.assertIn(word, wait, f"{path}: {word}")
            self.assertEqual(re.findall(r"\baz ([a-z-]+ [a-z-]+ [a-z-]+ [a-z-]+)", self.script(app["wait"])), ["network private-endpoint dns-zone-group list"], "it reads the zone group of the endpoint and nothing else")
            for word in ("--method", "--yes", "dns-zone-group create", "dns-zone-group delete", "az network private-dns", "az role", "az resource"):
                self.assertNotIn(word, self.script(app["wait"]), f"{path}: {word}")
            order = [self.names.index(app[key]) for key in ("deploy", "wait", "login", "build", "publish")]
            self.assertEqual(order, sorted(order), f"{path}: the deploy, the wait, a fresh sign-in (the first credential is old by the end of a wait), the build and the publish, in that order")
            for key in ("wait", "login", "build", "publish"):
                self.assertIn(f"        if: inputs.action == '{app['action']}'\n", self.step(app[key]), f"{path}: {key}")

    def test_the_comment_of_the_wait_says_what_happened_so_that_nobody_takes_the_wait_away(self):
        cases = self.step(self.APPS["environment/cases/main.bicep"]["wait"])
        for words in ("a deployment site calls its app by that name", "a later probe from the Operator finds the names", "The policy registers them about ten minutes after the endpoint is made"):
            self.assertIn(words, cases.replace("\n          # ", " "), words)


class TheCodeIsPublishedFromInsideTheNetwork(unittest.TestCase):
    """Phase 2 of docs/proposals/07-private-by-default.md, read from the text of the workflow and of the container script: the action cases publishes in a container group of the Operator, as
    the deploy identity, with the token of the run, through the app's private endpoint, and the runner publishes nothing. The steps are run with bash against stand-ins in test_workflow_scripts.py."""

    PUBLISHES = {
        "cases": {"action": "cases", "title": "Publish the cases to the function app from inside the network, in the Operator", "id": "publish_cases", "seconds": 1200, "minutes": 25,
                  "cleanup": "Delete any container group of the publish of the cases that is left", "files": ["cases-source.zip", "build-function-app.sh"]},
    }
    PROBE = "Run the probe in the Operator"

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}\n")]
        return block

    def script(self, title):
        body = self.step(title).split("        run: |\n", 1)[1]
        return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))

    def test_each_publish_finds_the_operator_then_asks_for_the_token_right_before_the_tool_and_the_tool_is_the_last_thing_it_runs(self):
        for kind, want in self.PUBLISHES.items():
            script = self.script(want["title"])
            order = ('identity_id=$(az resource list', "grep -Eq '^/subscriptions/' <<< \"$identity_id\"", 'az rest --method get --url "https://management.azure.com${subnet_id}', "dns=()", "bytes=$(wc -c",
                     "curl_status=0", 'echo "::add-mask::$token"', 'AZURE_FEDERATED_TOKEN="$token" python3 tools/operator-run.py run')
            positions = [script.index(word) for word in order]
            self.assertEqual(positions, sorted(positions), f"{kind}: everything else is ready before the token is asked for: it is valid for five minutes")
            self.assertEqual(script.count("python3 tools/operator-run.py run"), 1, "one group")
            self.assertTrue(script.rstrip().endswith('"${dns[@]}" --timeout-seconds ' + str(want["seconds"]) + ' --summary "$GITHUB_STEP_SUMMARY"'), f"{kind}: the tool is the last thing that the step runs")
            self.assertIn("this run has none", script, f"{kind}: without a token the step stops and says why, and publishes nothing")
            self.assertLess(script.index("this run has none"), script.index("python3 tools/operator-run.py run"))

    def test_the_code_that_asks_for_the_token_is_the_same_in_the_probe_and_in_the_publish_because_the_probe_has_proven_it_on_the_real_estate(self):
        def asking(title):
            found = re.search(r'(?s)if \[ -z "\$\{ACTIONS_ID_TOKEN_REQUEST_URL:-\}" \].*?\n\s*unset answer\n\s*fi', self.script(title))
            self.assertIsNotNone(found, title)
            return [line.strip() for line in found.group(0).splitlines()]

        probe = asking(self.PROBE)
        self.assertGreater(len(probe), 10)
        for want in self.PUBLISHES.values():
            self.assertEqual(asking(want["title"]), probe, want["title"])

    def test_the_token_goes_only_through_secure_env_is_written_nowhere_and_the_runner_signs_in_nowhere_in_the_step(self):
        self.assertIn("id-token: write", self.text.split("jobs:")[0], "the job may ask for the token")
        for want in self.PUBLISHES.values():
            block, script = self.step(want["title"]), self.script(want["title"])
            self.assertEqual(re.findall(r"--secure-env [A-Za-z_=]+", block), ["--secure-env AZURE_FEDERATED_TOKEN"], "one secure value, and it is named, never given")
            for value in re.findall(r'--env "[A-Z_]+=([^"]*)"', script):
                self.assertNotRegex(value, r"(?i)token", "no --env value is the token")
            for word in ("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_STATE", "GITHUB_PATH", "set -x", "xtrace", " tee ", "::set-output", "::save-state"):
                self.assertNotIn(word, block, f"{word}: the token is written nowhere")
            for word in ("az login", "azure/login", "get-access-token"):
                self.assertNotIn(word, script, f"{word}: the runner does not sign in for the publish, nor ask for another token: the container does")
            self.assertEqual(re.findall(r"secrets\.(\w+)", block), ["AZURE_CLIENT_ID", "AZURE_TENANT_ID"], "the two ids of the deploy identity, which the other steps read from the same secrets, and no other secret")
            self.assertIn("DEPLOY_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}", block)
            self.assertIn("DEPLOY_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}", block)
            self.assertIn('--image "$OPERATOR_IMAGE"', script, "the image is the one that is pinned by its digest")
            self.assertNotIn("--allow-tag", script)
            self.assertIn('--identity-id "$identity_id"', script, "the group has the Operator's identity (for the pull and for nothing that writes): the container signs in as the deploy identity")

    def test_the_group_is_given_less_time_than_the_step_and_the_comment_says_how_long_and_why(self):
        for kind, want in self.PUBLISHES.items():
            block = self.step(want["title"])
            seconds = int(re.search(r"--timeout-seconds (\d+)", block).group(1))
            minutes = int(re.search(r"(?m)^        timeout-minutes: (\d+)$", block).group(1))
            self.assertEqual((seconds, minutes), (want["seconds"], want["minutes"]), kind)
            self.assertGreaterEqual(minutes * 60 - seconds, 240, f"{kind}: the limit of the step is a second line, at least four minutes behind the limit of the group, which the tool deletes at its own")
            self.assertIn(f"The container group is given {seconds} seconds", " ".join(block.split()), f"{kind}: the comment says how long the group is given")
        self.assertLessEqual(self.PUBLISHES["cases"]["minutes"] + 40 + 30, 150, "the wait for the endpoints (40 minutes), the publish and the rest of the run stay below the 150 minutes of the job")
        self.assertIn("    timeout-minutes: 150\n", self.text)

    def test_each_cleanup_runs_always_right_after_its_publish_takes_the_groups_of_the_publishes_only_and_the_publish_has_the_id_that_it_names(self):
        for kind, want in self.PUBLISHES.items():
            publish, cleanup = self.step(want["title"]), self.step(want["cleanup"])
            self.assertIn(f"        id: {want['id']}\n", publish)
            self.assertIn(f"        if: always() && inputs.action == '{want['action']}' && steps.{want['id']}.outcome != 'skipped'\n", cleanup)
            self.assertEqual(self.names.index(want["cleanup"]), self.names.index(want["title"]) + 1, f"{kind}: right after the publish")
            self.assertIn('python3 tools/operator-run.py cleanup --resource-group "$ENV_RESOURCE_GROUP" --prefix op-publish- --older-than-minutes 0', cleanup)
            self.assertIn('--name "op-publish-$GITHUB_RUN_ID"', publish, "the prefix of the cleanup is the start of the name that the publish gives its group")
            self.assertIn("::warning::", cleanup)
            self.assertNotIn("delete", self.script(want["cleanup"]).replace("deletes", ""), "the tool deletes, not a command of the step")

    def test_the_container_script_reads_what_the_steps_give_it_and_the_files_that_the_steps_send_are_the_ones_it_looks_for_in_its_volume(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/publish.sh"))
        read = set(re.findall(r"\bPUBLISH_[A-Z_]+\b", source))
        given = set()
        for want in self.PUBLISHES.values():
            script = self.script(want["title"])
            names = set(re.findall(r'--env "(PUBLISH_[A-Z_]+)=', script))
            expected = {"PUBLISH_KIND", "PUBLISH_APP", "PUBLISH_RESOURCE_GROUP", "PUBLISH_SUBSCRIPTION", "PUBLISH_CLIENT_ID", "PUBLISH_TENANT_ID", "PUBLISH_FILE_BYTES"}
            if want["action"] == "cases":
                expected.add("PUBLISH_PLAN")  # the plan kind of the web page's app: the usage app is always Flex Consumption and says nothing
            self.assertEqual(names, expected, want["title"])
            given |= names
            sent = re.findall(r'--secret-file "([^"=]+)=', script)
            self.assertEqual(sent, want["files"], want["title"])
            for name in sent:
                self.assertIn(f"$volume/{name}", source, f"{name}: the container script looks for the file that the step sends")
        self.assertEqual(read - given, {"PUBLISH_HOLD_SECONDS", "PUBLISH_VOLUME", "PUBLISH_TMP"}, "the script reads what the steps give it, and an optional hold and the hooks of its tests")
        self.assertEqual(given - read, set(), "and the steps give it nothing that it does not read")
        self.assertIn("AZURE_FEDERATED_TOKEN", source)

    def test_the_runner_builds_no_libraries_of_the_app_and_only_zips_the_sources_with_the_script_that_the_container_builds_with(self):
        builders = [(re.match(r"name: (.+)", b).group(1), b) for b in self.steps if "tools/build-function-app.sh" in b and "--secret-file" not in b]
        self.assertEqual([name for name, _ in builders], ["Pack the cases app's sources for the Operator"],
                         "the finished package of the app is too big for a container group's request: it is not built here")
        self.assertIn('FUNCTION_APP_SOURCES_ONLY=1 bash tools/build-function-app.sh case-functions cases "$RUNNER_TEMP/cases-source" "$RUNNER_TEMP/cases-source.zip"', builders[0][1])
        for name, block in builders:
            self.assertEqual(len(re.findall(r"(?m)^\s*FUNCTION_APP_SOURCES_ONLY=1 bash tools/build-function-app\.sh ", block)), 1, f"{name}: one build, in the mode that installs nothing")
        self.assertNotIn("FUNCTION_APP_BUILD_IN_OPERATOR", self.text, "that switch is set in the container only, by the container script")
        container = re.sub(r"(?m)^\s*#.*$", "", text("operator/publish.sh"))
        self.assertIn("FUNCTION_APP_BUILD_IN_OPERATOR=1", container)
        self.assertIn("FUNCTION_APP_SOURCE_DIR=", container)
        self.assertNotIn("FUNCTION_APP_SOURCES_ONLY", container, "the container never zips sources: it builds from them")

    def test_the_summaries_say_that_the_code_is_published_from_inside_the_network_and_what_a_stop_at_that_step_means_and_the_order_on_an_estate_that_has_no_operator(self):
        for words in ("It publishes the app's code from inside the network, in a container group of the Operator that signs in as the deploy identity with a token of the run and goes through the "
                      "app's private endpoint, so on an estate that has no Operator yet it deploys and stops at the publish: the order is then base, cases, operator, and then cases again.",
                      "The action cases publishes its code through it, as the deploy identity.",
                      "If they stop at the step that publishes the code from inside the network, the app and its endpoint are made and the app was not given its code: the lines say that the Operator is not there",
                      "on an estate that has none the order is base, cases, operator, and then cases again) or what the container said.",
                      "The code was published from inside the network: a short-lived container group of the Operator signed in as the deploy identity with a token of this run, built the libraries from the "
                      "hash-locked lock file (the sources went in the request, because the finished package is too big for it) and published the finished package through the app's private endpoint: with "
                      "the Azure CLI's zip deployment command while the app is on Flex Consumption, as the usage app's was, and posted to the deployment site while it is on a Basic plan",
                      "the runner published nothing"):
            self.assertIn(words, self.text, words)
        for stale in ("goes from this runner to the public deployment site", "the app was not given its code: the lines say which endpoint is not registered yet. Running"):
            self.assertNotIn(stale, self.text, "the runner publishes nothing any more")


class Planted(unittest.TestCase):
    """The waste that Meternaut plants (environment/cases/planted.bicep): an unattached disk and, when asked, an address and a machine that nothing uses, all tagged. The names and the types are the
    planted list of the app (cases/families/gates.py): the one place that says which resources a family of change may touch."""

    def setUp(self):
        self.source = text("environment/cases/planted.bicep")
        self.code = re.sub(r"//.*", "", self.source)
        self.found = resources(self.source)

    def test_it_makes_an_unattached_disk_an_optional_unassigned_address_and_an_optional_machine_with_its_interface_and_disk_and_nothing_else(self):
        self.assertEqual(sorted(self.found), ["address", "disk", "machine", "nic", "osDisk"])
        self.assertEqual({name: kind for name, (kind, _) in self.found.items()},
                         {"disk": "Microsoft.Compute/disks", "address": "Microsoft.Network/publicIPAddresses", "nic": "Microsoft.Network/networkInterfaces", "osDisk": "Microsoft.Compute/disks",
                          "machine": "Microsoft.Compute/virtualMachines"})
        self.assertIn("if (plantPublicIp)", self.source)
        self.assertEqual(self.code.count("= if (plantVm)"), 3, "the interface, the OS disk and the machine are made together and only when asked")
        self.assertNotIn("managedBy", self.code)
        self.assertNotIn("ipConfiguration", self.found["address"][1], "the address is attached to nothing")
        self.assertNotIn("Microsoft.Authorization", self.code)
        self.assertIn("createOption: 'Empty'", self.found["disk"][1])
        self.assertIn("diskSizeGB: 4", self.found["disk"][1])
        self.assertIn("networkAccessPolicy: 'DenyAll'", self.found["disk"][1])

    def test_the_disk_is_a_premium_ssd_so_that_the_tier_family_has_a_step_to_take_and_the_os_disk_is_the_cheapest_standard_ssd(self):
        self.assertIn("name: 'Premium_LRS'", self.found["disk"][1])
        self.assertIn("name: 'StandardSSD_LRS'", self.found["osDisk"][1])
        self.assertIn("diskSizeGB: 4", self.found["osDisk"][1])

    def test_the_machine_has_no_credential_no_public_address_no_identity_and_leaves_its_disk_and_interface_when_it_is_deleted(self):
        machine = self.found["machine"][1]
        for gone in ("osProfile", "adminPassword", "adminUsername", "sshKey", "publicKeys", "identity", "secrets", "customData", "extensions"):
            self.assertNotIn(gone, self.code, gone)
        self.assertNotIn("publicIPAddress", machine)
        self.assertNotIn("publicIPAddress", self.found["nic"][1])
        self.assertIn("createOption: 'Attach'", machine)
        self.assertIn("deleteOption: 'Detach'", machine)
        self.assertEqual(machine.count("deleteOption: 'Detach'"), 2)
        self.assertIn("vmSize: plantedVmSize", machine)
        self.assertIn("privateIPAllocationMethod: 'Dynamic'", self.found["nic"][1])

    def test_the_subnet_of_the_interface_is_read_by_its_id_and_never_made_or_changed_here(self):
        self.assertNotIn("Microsoft.Network/virtualNetworks", self.code.replace("resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-${workload}', 'snet-pe')", ""))
        self.assertIn("resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-${workload}', 'snet-pe')", self.code)
        self.assertIn("param workload string = 'meternaut'", self.code, "the same name as the other templates of the model side give the virtual network")

    def test_every_resource_carries_the_tag_that_the_loop_looks_for_and_a_name_that_says_what_it_is(self):
        self.assertIn("'meternaut-planted': plantedId", self.code)
        for name in ("planted-disk-${plantedId}", "planted-ip-${plantedId}", "planted-nic-${plantedId}", "planted-osdisk-${plantedId}", "planted-vm-${plantedId}"):
            self.assertIn(f"name: '{name}'", self.code)
        self.assertEqual(self.code.count("tags: tags"), 5)

    def test_the_planted_list_of_the_app_and_the_template_say_the_same_thing(self):
        """The two gates of a change (cases/families/gates.py) are the tag and the planted list. The list holds a type and the shape of a name for each thing that this template makes, and
        nothing that it does not make, so that no family may change a resource that the planting never made."""
        import importlib
        import sys
        sys.path.insert(0, str(ROOT / "src" / "case-functions"))
        try:
            gates = importlib.import_module("cases.families.gates")
        finally:
            sys.path.pop(0)
        made = {}
        for symbol, (kind, body) in self.found.items():
            name = re.search(r"name: '([^']+)'", body).group(1).replace("${plantedId}", "r42")
            made.setdefault(kind.lower(), []).append(name)
        self.assertEqual(sorted(gates.PLANTED_NAMES), sorted(made), "the types of the list are the types that the template makes")
        for kind, names in made.items():
            for name in names:
                self.assertTrue(gates.on_planted_list(kind, name), f"{name} is made by the template and is not on the planted list")
            for other in ("planted-xx-r42", "planted-", "planted-disk-", "planted-disk-r42-extra", "disk-r42", "x" * 20):
                if other not in names:
                    self.assertFalse(gates.on_planted_list(kind, other), f"{other} must not pass for {kind}")
        # the id of a planting is 1 to 12 lower-case letters or digits (tools/environment-params.py), and the list takes every one of them
        for planted_id in ("a", "demo", "r1234", "x" * 12):
            self.assertTrue(gates.on_planted_list("microsoft.compute/virtualmachines", f"planted-vm-{planted_id}"))
        self.assertFalse(gates.on_planted_list("microsoft.compute/virtualmachines", "planted-vm-" + "x" * 13))

    def test_the_tag_and_the_group_are_the_ones_of_the_app(self):
        approvals = text("src/case-functions/cases/approvals.py")
        self.assertIn('planted_tag: str = "meternaut-planted"', approvals)
        loop = text("src/case-functions/cases/loop_config.py")
        self.assertIn('planted_tag=values[PLANTED_TAG] or "meternaut-planted"', loop)

    def test_the_size_of_the_machine_has_a_smaller_one_in_its_series_so_that_the_resize_family_has_a_step(self):
        params = text("tools/environment-params.py")
        self.assertIn('PLANTED_VM_SIZE = "Standard_B4als_v2"', params)
        self.assertIn("param plantedVmSize string = 'Standard_B4als_v2'", self.code)


class CasesWorkflow(unittest.TestCase):
    """The actions of the deploy workflow that make and start the first cases."""

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}")]
        return block

    def test_the_cases_are_made_ready_deployed_published_and_listed_in_that_order_and_for_their_action_only(self):
        order = ["The base is there, which the first cases build on",
                 "The function subnet is free for the cases app, which runs on Flex Consumption",
                 "Clear what is in the way of the deploy of the cases app (an app and a plan of the other kind, a private endpoint that is Disconnected, role assignments of an identity that is gone)",
                 "Remove what the Flex Consumption version left in the storage account, when it is still there",
                 "Let the cases app go from an integration subnet that is not the one of the template", "Deploy the first cases",
                 "Wait until the landing zone has registered the cases app's private endpoint in the central zone",
                 "Sign in to Azure again for the publish of the cases, because the first sign-in's credential lasts five minutes",
                 "Pack the cases app's sources for the Operator", "Publish the cases to the function app from inside the network, in the Operator",
                 "Delete any container group of the publish of the cases that is left",
                 "Sign in to Azure again for the health check of the cases app in the Operator, because the publish in the Operator can take a quarter of an hour and a credential lasts five minutes",
                 "Wait until the cases app answers", "Delete any container group of the health check of the cases app that is left",
                 "Sign in to Azure a fourth time for the check of the cases, because the third sign-in's credential lasts five minutes too",
                 "Say whether the integration subnet carries the route table of the landing zone's network manager",
                 "The cases app lists its four functions",
                 "Remove the first integration subnet of the cases app, snet-web, when it is still there and nothing uses it"]
        positions = [self.names.index(name) for name in order]
        self.assertEqual(positions, sorted(positions))
        second_lines = {"Delete any container group of the publish of the cases that is left": "publish_cases",
                        "Delete any container group of the health check of the cases app that is left": "health_cases"}
        for name in order:
            if name in second_lines:
                self.assertIn(f"if: always() && inputs.action == 'cases' && steps.{second_lines[name]}.outcome != 'skipped'", self.steps[self.names.index(name)], name)
            else:
                self.assertIn("if: inputs.action == 'cases'", self.steps[self.names.index(name)], name)
        deploy = self.step("Deploy the first cases")
        self.assertIn("--template environment/cases/main.bicep", deploy)
        self.assertIn('--parameters "$RUNNER_TEMP/cases.parameters.json"', deploy)
        self.assertIn("--output functionAppId", deploy)
        self.assertEqual(self.text.count("--template environment/cases/main.bicep"), 3, "the preview, the step before the deploy (which asks for a preview of the deploy, to read the role assignments that it would write) and the deploy, nothing else")

    def test_the_cases_are_published_in_the_operator_with_the_deploy_identity_and_no_password_from_sources_that_the_container_builds(self):
        pack, publish = self.step("Pack the cases app's sources for the Operator"), self.step("Publish the cases to the function app from inside the network, in the Operator")
        self.assertIn('FUNCTION_APP_SOURCES_ONLY=1 bash tools/build-function-app.sh case-functions cases "$RUNNER_TEMP/cases-source" "$RUNNER_TEMP/cases-source.zip"', pack)
        for word in ("--script operator/publish.sh", '--secret-file "cases-source.zip=$RUNNER_TEMP/cases-source.zip"', '--secret-file "build-function-app.sh=tools/build-function-app.sh"', '--env "PUBLISH_KIND=cases"',
                     '--env "PUBLISH_APP=$FUNCTION_APP"', "--secure-env AZURE_FEDERATED_TOKEN", '--name "op-publish-$GITHUB_RUN_ID"', '--image "$OPERATOR_IMAGE"', '"${dns[@]}"'):
            self.assertIn(word, publish, word)
        self.assertIn('bytes=$(wc -c < "$RUNNER_TEMP/cases-source.zip" | tr -d \' \')', publish, "the size that the container compares the file in its volume with is the size of the sources")
        self.assertIn("FUNCTION_APP: ${{ steps.params.outputs.cases_function_app_name }}", publish)
        self.assertIn('echo "::add-mask::$token"', publish, "the token is masked at once")
        self.assertLess(publish.index("::add-mask::"), publish.index("python3 tools/operator-run.py run"), "and before anything is started with it")
        self.assertIn("this run has none", publish, "no token: nothing is published, and the step says why")
        for word in ("az webapp deploy", "publishing-credentials", "--user", "--password", "config-zip", "kit/", "environment/", "zipdeploy", "--data-binary", "get-access-token", "package.zip", "case-functions.zip"):
            self.assertNotIn(word, publish + pack, word)

    def test_the_function_subnet_is_read_before_anything_is_removed_and_a_plan_that_still_holds_it_is_named_with_what_to_do(self):
        title = "The function subnet is free for the cases app, which runs on Flex Consumption"
        block = self.step(title)
        self.assertIn("if: inputs.action == 'cases' && steps.params.outputs.cases_app_plan == 'Flex'", block, "only for a Flex app: a Basic app has its own subnet")
        self.assertIn("FUNCTION_SUBNET: ${{ steps.params.outputs.function_subnet_name }}", block)
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertNotRegex(script, r"--method (put|patch|post|delete)", "it only reads")
        self.assertIn("grep -Fxq 'Microsoft.App/environments'", script, "a Flex Consumption app needs the delegation that the model side gave the function subnet")
        self.assertIn("properties.virtualNetworkSubnetId", script)
        self.assertIn("::error::The subnet $FUNCTION_SUBNET is still taken by another plan:$taken.", script)
        for words in ("the usage app", "the action retire-old removes it and its plan", "run cases again", "no other subnet is made for it", "Nothing was changed: the web page's app is still where it was."):
            self.assertIn(words, script, words)
        self.assertIn("is not there. A Flex Consumption app uses the function subnet that model-side makes, and no new subnet is made for it", script)
        self.assertIn("serviceAssociationLinks", script, "the platform's links on the subnet are said, as read")
        self.assertIn('${name,,}" = "${FUNCTION_APP,,}"', script, "the cases app itself is not another plan")
        self.assertLess(self.names.index("The base is there, which the first cases build on"), self.names.index(title))

    def test_a_flex_app_is_published_with_the_plan_kind_and_the_container_does_it_with_the_zip_deployment_command_of_the_azure_cli(self):
        publish = self.step("Publish the cases to the function app from inside the network, in the Operator")
        self.assertIn("CASES_APP_PLAN: ${{ steps.params.outputs.cases_app_plan }}", publish)
        self.assertIn('--env "PUBLISH_KIND=cases" --env "PUBLISH_PLAN=$CASES_APP_PLAN"', publish)
        script = text("operator/publish.sh")
        for line in ('plan=${PUBLISH_PLAN:-}', 'publish_flex()', 'publish_cases()', "az functionapp deployment source config-zip --resource-group \"$group\" --name \"$app\" --src \"$package_zip\" --build-remote false"):
            self.assertIn(line, script, line)

    def test_the_deploy_says_what_to_do_when_the_subnet_is_the_reason_that_a_flex_app_was_refused(self):
        deploy = self.step("Deploy the first cases")
        self.assertIn("CASES_APP_PLAN: ${{ steps.params.outputs.cases_app_plan }}", deploy)
        self.assertIn("CASES_SUBNET: ${{ steps.params.outputs.cases_subnet_name }}", deploy)
        self.assertIn('if [ "$CASES_APP_PLAN" = Flex ] && grep -Eqi \'subnet|ServiceAssociationLink|delegat|InUse\' "$RUNNER_TEMP/cases-deploy.err"; then', deploy)
        for words in ("still taken by another plan", "the usage app and its plan have to be removed first (the action retire-old does it)", "no new subnet is made", "set CASES_APP_PLAN back to Basic"):
            self.assertIn(words, deploy, words)
        self.assertIn('--output functionAppId 2> "$RUNNER_TEMP/cases-deploy.err"', deploy)

    def test_what_the_flex_version_left_in_the_storage_account_is_removed_by_name_and_nothing_else_in_the_account_is_touched(self):
        title = "Remove what the Flex Consumption version left in the storage account, when it is still there"
        block = self.step(title)
        self.assertIn("if: inputs.action == 'cases'", block)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", block)
        self.assertIn("storageAccounts/$STORAGE_ACCOUNT/blobServices/default/containers/app-package-cases", block)
        self.assertEqual(len(re.findall(r"--method delete", block)), 1, "one container goes, and nothing else")
        self.assertEqual(len(re.findall(r"az role assignment delete --ids \"\$id\"", block)), 1)
        self.assertIn('az role assignment list --scope "$container"', block, "only what is assigned on the container itself is listed")
        self.assertLess(block.index("az role assignment delete"), block.index("--method delete"), "the role goes before the container")
        self.assertIn("ContainerNotFound", block)
        self.assertIn('echo "::error::The container app-package-cases could not be read', block, "a failure that is not 'not there' stops the run")
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        for word in ("app-package-usage", "azure-webjobs", "az storage", "--account-key", "--yes", "az resource delete", "--all"):
            self.assertNotIn(word, script, word)
        self.assertLess(self.names.index("Clear what is in the way of the deploy of the cases app (an app and a plan of the other kind, a private endpoint that is Disconnected, role assignments of an identity that is gone)"), self.names.index(title))
        self.assertLess(self.names.index(title), self.names.index("Deploy the first cases"))
        self.assertIn("if: inputs.action == 'cases' && steps.params.outputs.cases_app_plan == 'Basic'", block, "a Flex app keeps its package in that container: the step runs only for a Basic app")

    def test_the_network_is_looked_for_before_the_files_are_made_and_the_answers_go_into_them(self):
        title = "Find out what of the network is there already"
        block = self.step(title)
        self.assertIn("id: network", block)
        self.assertNotIn("if:", block.split("run:")[0], "every action asks: the answer goes into the files whichever action made them")
        self.assertIn('virtualNetworks/vnet-meternaut"', block)
        self.assertIn('"$vnet/subnets/snet-cases"', block)
        self.assertIn('"https://management.azure.com${1}?api-version=2025-05-01"', block)
        self.assertIn('echo "network_exists=$network" >> "$GITHUB_OUTPUT"', block)
        self.assertIn('echo "web_subnet_exists=$subnet" >> "$GITHUB_OUTPUT"', block)
        self.assertNotRegex(block, r"--method (put|patch|post|delete)")
        self.assertIn("could not be read", block, "a failure that is not 'not found' stops the run")
        self.assertIn("return 1", block)
        (params,) = [b for b in self.steps if b.startswith("name: Work out the settings\n")]
        self.assertIn("ENV_NETWORK_EXISTS: ${{ steps.network.outputs.network_exists }}", params)
        self.assertIn("ENV_WEB_SUBNET_EXISTS: ${{ steps.network.outputs.web_subnet_exists }}", params)
        self.assertLess(self.names.index(title), self.names.index("Work out the settings"))
        template = text("environment/cases/main.bicep")
        self.assertIn("var webSubnetName = 'snet-cases'", template, "the name that the workflow reads is the template's")
        self.assertIn("var virtualNetworkName = 'vnet-${workload}'", template)
        self.assertIn("name: 'vnet-${workload}'", text("environment/main.bicep"))

    def test_the_app_is_taken_from_an_earlier_subnet_only_when_it_is_integrated_with_another_one_and_a_refusal_is_said(self):
        title = "Let the cases app go from an integration subnet that is not the one of the template"
        block = self.step(title)
        self.assertIn("if: inputs.action == 'cases'", block)
        self.assertIn("FUNCTION_APP: ${{ steps.params.outputs.cases_function_app_name }}", block)
        self.assertIn("--query properties.virtualNetworkSubnetId", block)
        self.assertIn('"${current##*/}" = "$CASES_SUBNET"', block, "an app that is on the template's subnet (snet-func for a Flex app, snet-cases for a Basic one) is left alone")
        self.assertIn("CASES_SUBNET: ${{ steps.params.outputs.cases_subnet_name }}", block)
        self.assertEqual(len(re.findall(r"--method delete", block)), 1)
        self.assertIn('${site}/networkConfig/virtualNetwork?api-version=2024-04-01', block, "the app's own integration, nothing else")
        self.assertIn("::warning::", block, "a refusal is said, and the template's own change follows")
        self.assertLess(self.names.index(title), self.names.index("Deploy the first cases"))

    def test_the_route_table_of_the_landing_zone_is_only_said_and_never_required_because_the_wait_for_the_app_is_the_gate(self):
        # The network manager took 70 seconds the first time and five minutes the second: a wait of two minutes for it stopped a run that was right. The app cannot start without the table,
        # so the wait for the app (no credential, 25 minutes) holds the run, and the start limit of the app lets the first start wait for it.
        title = "Say whether the integration subnet carries the route table of the landing zone's network manager"
        block = self.step(title)
        self.assertIn("if: inputs.action == 'cases'", block)
        self.assertIn('for name in snet-pe "$CASES_SUBNET"; do', block, "the subnet of the plan kind that is asked for")
        self.assertIn("CASES_SUBNET: ${{ steps.params.outputs.cases_subnet_name }}", block)
        self.assertIn("--query properties.routeTable.id", block)
        self.assertIn("::warning::", block)
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertNotIn("exit 1", script, "it says what the landing zone has done and never fails the run")
        self.assertNotIn("sleep", script)
        self.assertNotRegex(block, r"--method (put|patch|post|delete)")
        self.assertLess(self.names.index("Sign in to Azure a fourth time for the check of the cases, because the third sign-in's credential lasts five minutes too"),
                        self.names.index(title), "a fresh credential: the third one is old by the time the app has answered")
        self.assertLess(self.names.index(title), self.names.index("The cases app lists its four functions"))

    def test_the_wait_for_the_app_runs_in_the_operator_on_the_apps_own_name_with_no_token_of_the_deploy_identity_and_the_checks_after_it_sign_in_again(self):
        # Once the app is closed this runner cannot reach it: the health address is asked from inside the network, as the publish is (docs/proposals/07-private-by-default.md).
        again = "Sign in to Azure again for the health check of the cases app in the Operator, because the publish in the Operator can take a quarter of an hour and a credential lasts five minutes"
        fourth = "Sign in to Azure a fourth time for the check of the cases, because the third sign-in's credential lasts five minutes too"
        cleanup = "Delete any container group of the health check of the cases app that is left"
        wait = self.step("Wait until the cases app answers")
        script = "\n".join(line for line in wait.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertIn("id: health_cases\n", wait)
        self.assertIn("timeout-minutes: 35\n", wait)
        self.assertIn("FUNCTION_APP: ${{ steps.params.outputs.cases_function_app_name }}", wait)
        for word in ('--name "op-health-$GITHUB_RUN_ID"', "--script operator/run-tool.sh", '--secret-file "console-check.py=tools/console-check.py"', '--env "TOOL_NAME=console-check"',
                     '--env "TOOL_ARGS=health --host $FUNCTION_APP.azurewebsites.net --tries 60 --interval 10 --timeout 15 --private"', '--image "$OPERATOR_IMAGE"', '"${dns[@]}"',
                     "--timeout-seconds 1800", '--summary "$GITHUB_STEP_SUMMARY"', "id-meternaut-operator", "snet-ops"):
            self.assertIn(word, script, word)
        for word in ("curl", "--secure-env", "ACTIONS_ID_TOKEN", "AZURE_FEDERATED_TOKEN", "DEPLOY_CLIENT_ID", "DEPLOY_TENANT_ID", "sleep", "https://$FUNCTION_APP.azurewebsites.net/healthz", "get-access-token"):
            self.assertNotIn(word, script, f"the runner asks nothing of the app and the container gets no token of the deploy identity: {word}")
        self.assertNotRegex(script, r"--method (put|patch|post|delete)", "nothing is changed here")
        self.assertIn("exit \"$status\"", script, "the tool's own exit code stops the run")
        self.assertIn("uses: azure/login@", self.step(again))
        self.assertIn("uses: azure/login@", self.step(fourth))
        self.assertIn("if: always() && inputs.action == 'cases' && steps.health_cases.outcome != 'skipped'\n", self.step(cleanup))
        self.assertIn("--prefix op-health- --older-than-minutes 0", self.step(cleanup))
        self.assertIn("::warning::", self.step(cleanup), "a failed cleanup is a warning: the tool has deleted its group already")
        positions = [self.names.index(name) for name in ("Publish the cases to the function app from inside the network, in the Operator", again, "Wait until the cases app answers", cleanup, fourth,
                                                        "The cases app lists its four functions")]
        self.assertEqual(positions, sorted(positions))
        tries, interval, timeout, seconds, minutes = 60, 10, 15, 1800, 35
        self.assertLess(tries * (timeout + interval), seconds, "the group is given longer than the tool waits for the app")
        self.assertLess(seconds, minutes * 60, "and the step is given longer than the group, which the tool deletes at its own limit")

    def test_the_first_subnet_is_removed_by_its_name_when_nothing_holds_it_and_a_hold_is_said_and_is_no_error(self):
        title = "Remove the first integration subnet of the cases app, snet-web, when it is still there and nothing uses it"
        block = self.step(title)
        self.assertIn("if: inputs.action == 'cases'", block)
        self.assertIn("virtualNetworks/vnet-meternaut/subnets/snet-web\"", block)
        self.assertEqual(len(re.findall(r"--method delete", block)), 1)
        self.assertIn("InUseSubnetCannotBeDeleted", block)
        self.assertIn("::warning::", block, "a hold is said, and the next run tries again")
        self.assertIn("exit 1", block, "any other refusal stops the run")
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        for word in ("snet-cases", "snet-pe", "snet-func", "az network", "--yes", "az resource delete"):
            self.assertNotIn(word, script, word)
        self.assertLess(self.names.index("The cases app lists its four functions"), self.names.index(title))

    def test_the_retired_runner_identity_is_removed_by_its_name_only_when_nothing_holds_it_and_each_hold_stops_the_run(self):
        title = "Remove the retired runner identity of the first loop, when it is still there and nothing holds it"
        block = self.step(title)
        self.assertIn("if: inputs.action == 'cases'", block)
        self.assertIn("FUNCTION_APP: ${{ steps.params.outputs.cases_function_app_name }}", block)
        self.assertIn('userAssignedIdentities/id-meternaut-runner"', block)
        self.assertEqual(len(re.findall(r"--method delete", block)), 1)
        self.assertIn('az rest --method delete --url "https://management.azure.com${identity}?api-version=2023-01-31"', block, "the identity itself, nothing else")
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertIn("nothing to remove", script, "an identity that is not there is no error")
        self.assertIn("--query identity.userAssignedIdentities", script, "an app that still carries it stops the run")
        self.assertIn("providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01", script, "a role that is still assigned stops the run")
        self.assertEqual(len(re.findall(r"exit 1", script)), 3, "an unreadable identity, an app that carries it and a role that is left each stop the run")
        for word in ("az role assignment", "az identity", "az resource delete", "--yes", "az group", "snet-", "listKeys"):
            self.assertNotIn(word, script, word)
        self.assertLess(self.names.index(title), self.names.index("Start one Watch and read its History"))
        self.assertLess(self.names.index("Deploy the first cases"), self.names.index(title), "the template has stopped attaching it by then")

    def test_the_check_before_the_deploy_writes_nothing_reads_no_key_and_asks_nothing_of_the_gateway_or_the_contract(self):
        block = self.step("The base is there, which the first cases build on")
        self.assertNotIn("az-deploy.py", block)
        self.assertNotRegex(block, r"--method (put|patch|post|delete)")
        self.assertNotIn("listSecrets", block)
        self.assertNotIn("primaryKey", block)
        self.assertIn("exit 1", block)
        self.assertIn("Run base first", block)
        # The cases app reads no key and calls no model through the owner's API Management instance (2026-11-07): the step makes no call to it and needs no setting of it.
        for word in ("Run contract first", "gatewayUrl", "CONTRACT_SUBSCRIPTION", "EXPECTED_GATEWAY_URL", "GATEWAY_RESOURCE_ID", "ApiManagement", "/subscriptions?", "steps.params.outputs.gateway_url",
                     "steps.params.outputs.contract_subscription"):
            self.assertNotIn(word, block, word)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", block)
        self.assertNotIn("EVENT_HUB_NAMESPACE", block, "the first cases use the base's storage account, and their control queue is made in it: no namespace is read")
        self.assertNotIn("Microsoft.EventHub", block)

    def test_one_watch_is_started_only_by_its_own_action_and_never_reads_the_contracts_key(self):
        block = self.step("Start one Watch and read its History")
        self.assertIn("if: inputs.action == 'cases-run'", block)
        self.assertIn('--env "TOOL_NAME=cases-check"', block)
        self.assertIn("TOOL_ARGS=run --storage-account $STORAGE_ACCOUNT --insights $insights --minutes 30", block)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", block)
        self.assertNotIn("EVENT_HUB_NAMESPACE", block)
        self.assertNotIn("--namespace", block)
        self.assertIn('--summary "$GITHUB_STEP_SUMMARY"', block)
        self.assertNotIn("listSecrets", block)
        self.assertEqual(self.text.count('--env "TOOL_NAME=cases-check"'), 1)
        self.assertNotRegex(self.text, r"(?m)^\s*python3 tools/cases-check\.py run\b", "the runner starts no Watch and sends no event: the Operator runs the tool")

    def test_the_preview_of_the_cases_waits_for_the_base_instead_of_failing(self):
        block = self.step(PREVIEW_STEP)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", block)
        self.assertLess(block.index("The first cases cannot be previewed yet"), block.index("--template environment/cases/main.bicep"))

    def test_the_cases_have_their_own_words_in_the_summary_for_a_failed_and_a_finished_run(self):
        block = self.step("What was done")
        self.assertEqual(len(re.findall(r"^\s+cases\) echo ", block, re.M)), 2)
        self.assertEqual(len(re.findall(r"^\s+cases-run\) echo ", block, re.M)), 2)

    def test_the_summary_says_that_meternaut_holds_no_right_to_change_azure_and_that_a_person_s_approval_runs_the_change_with_that_person_s_permissions(self):
        block = self.step("What was done")
        (finished,) = re.findall(r"(?m)^\s+cases\) echo \"(The first cases are in resource group.*?)\" ;;$", block)
        for words in ("its identities (its own system-assigned one, which reads and stores the records and sends the letters, and \\`id-meternaut-console-auth\\`, which only presents the console's sign-in to Microsoft Entra and holds no role)",
                      "Meternaut holds no right to change Azure", "to sign in to Azure Resource Manager", "with that person's own permissions", "its Activity Log names that person",
                      "The app no longer carries the user-assigned identity that it used before, \\`id-meternaut-cases\\`. This workflow does not remove that identity: a person does, "
                      "in the order of environment/BOOTSTRAP.md (its grants outside the project's group first, with tools/access-requirements.py retire, and the identity after that)"):
            self.assertIn(words, finished)
        for words in ("three identities", "only writer", "Only the runner", "custom role", "are removed when they are still there", "go with it"):
            self.assertNotIn(words, finished)
        (planted,) = re.findall(r"(?m)^\s+plant\) echo \"(Waste of Meternaut's own.*?)\" ;;$", block)
        self.assertIn("Meternaut holds no right to delete it", planted)
        self.assertIn("because the change runs with that person's own permissions", planted)
        for word in ("writer", "Only the runner", "three identities"):
            self.assertNotIn(word, self.text, word)

    def test_the_front_door_is_knocked_at_by_its_own_action_and_after_every_cases_run_with_no_credential_and_no_write(self):
        block = self.step("Knock at the console's front door")
        self.assertIn("if: steps.params.outputs.door_in_operator != 'true' && (inputs.action == 'loop-check' || inputs.action == 'cases')", block,
                      "from the runner, except for a closed app with no host name: the next step, inside the network, checks that one")
        for word in ("CONSOLE_HOST: ${{ steps.params.outputs.console_host }}", "CONSOLE_HOST_SET: ${{ steps.params.outputs.console_host_set }}"):
            self.assertIn(word, block, "the address that is knocked at comes from the settings step: the console's host name, or the app's own name when there is none")
        self.assertNotIn("CASES_PUBLIC_ACCESS", block, "the step does not look at the app's public access any more: the condition of the step keeps the closed app for the Operator's step")
        self.assertNotIn("NOT CHECKED", block)
        self.assertNotIn("FUNCTION_APP", block)
        self.assertIn('python3 tools/console-check.py door --host "$CONSOLE_HOST" --expect "$expect" "${proxied[@]}" --summary "$GITHUB_STEP_SUMMARY"', block)
        self.assertIn("/arm/return", block, "the return address of the Azure sign-in is part of what is asked")
        script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
        self.assertNotRegex(script, r"\baz\s")
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        self.assertEqual(self.text.count("console-check.py door"), 1)

    def test_the_summary_of_cases_says_whether_the_app_has_an_identity_of_its_own_and_prints_no_object_id_because_the_summary_is_public(self):
        for title, site_variable in (("The cases app lists its four functions", "SITE_ID"),):
            block = self.step(title)
            script = "\n".join(line for line in block.split("run:")[1].splitlines() if not line.strip().startswith("#"))
            self.assertIn(f'system_principal=$(az rest --method get --url "https://management.azure.com${{{site_variable}}}?api-version=2024-04-01" --query identity.principalId --output tsv 2>/dev/null || true)', script, title)
            self.assertIn("if grep -Eq '^[0-9a-fA-F-]{36}$' <<< \"$system_principal\"; then", script, title)
            self.assertIn("printf '::add-mask::%s\\n::add-mask::%s\\n' \"$system_principal\" \"${system_principal^^}\"", script, "the object id is masked the moment it is read")
            self.assertIn("The cases app has an identity of its own, a system-assigned one: $has_identity.", script, title)
            self.assertNotIn("Identity of the cases app (object id)", script, title)
            for line in script.splitlines():
                if "echo" in line:
                    self.assertNotIn("$system_principal", line, "the object id is printed nowhere: the summary of a public repository is public")
            self.assertIn("It is the app's own system-assigned identity.", script, title)
            self.assertRegex(script, r"This workflow gives (none of them|neither)", title)
            self.assertNotRegex(script, r"--method (put|patch|post|delete)", title)
            self.assertNotIn("az identity", script, "the user-assigned identity that the app used before is not read any more")
            self.assertNotIn("USAGE_IDENTITY", block)
            self.assertNotIn("CASES_IDENTITY", block)
        self.assertIn("The application (client) id that the mailbox tool asks for cannot be read from the app, and the deployment identity may not read the directory", self.step("The cases app lists its four functions"))

    def test_the_old_user_assigned_identity_of_the_cases_app_is_neither_looked_for_nor_removed_by_the_workflow_because_retire_needs_it_and_a_person_removes_it_and_the_workflow_names_the_usage_identity_nowhere(self):
        # tools/access-requirements.py retire finds the grants of an identity by its object id: Azure keeps the grants of a deleted identity as "Identity not found", and the tool cannot tell
        # whose they were. The deployment identity cannot see the grants outside the project's group, so the workflow cannot know that they are gone: it leaves the identities alone.
        code = "\n".join(line for step in self.steps if "run:" in step for line in step.split("run:", 1)[1].splitlines()
                         if not line.strip().startswith("#") and "echo" not in line)
        for word in ("id-meternaut-cases", "id-meternaut-usage", "cases_identity_name", "usage_identity_name", "OLD_IDENTITY", "az identity delete", "az identity show"):
            self.assertNotIn(word, code, word)
        for line in code.splitlines():
            if "az identity" in line:
                self.assertIn("IDENTITY_NAME", line.upper(), f"only the gateway's identity is looked up in the identity list: {line.strip()}")
        self.assertEqual(len(re.findall(r"Microsoft\.ManagedIdentity/userAssignedIdentities", code)), 4, "the retired runner identity, which is read and removed by one path, and the Operator's own identity, which two steps "
                                                                                                     "only read, for its object id: the one that works out the settings of the AI security (it is one of the identities of the access list) and the one that works "
                                                                                                     "out the settings of the Foundry file (the role of the Operator on the project), and the one read of the list of the identities of the project's group, which "
                                                                                                     "masks their ids and changes nothing (the step 'Mask the identities that exist in the project's resource group'), and nothing else")
        self.assertEqual(len(re.findall(r'az rest --method delete --url "https://management\.azure\.com\$\{identity\}\?api-version=2023-01-31"', code)), 1, "the one that is the retired runner's")
        finished_cases = re.search(r"(?m)^\s+cases\) echo \"(The first cases are in resource group.*?)\" ;;$", self.step("What was done")).group(1)
        for words in ("The app no longer carries the user-assigned identity that it used before, \\`id-meternaut-cases\\`. This workflow does not remove that identity: a person does, "
                      "in the order of environment/BOOTSTRAP.md (its grants outside the project's group first, with tools/access-requirements.py retire, and the identity after that)",):
            self.assertIn(words, finished_cases)
        # the usage app's identity, id-meternaut-usage, is deleted by the tool of the action retire-old (tools/retire-old.py, whose tests pin the name), after a person has retired its grants
        # (tools/access-requirements.py retire --only W9,W10): the workflow says that order in the summary of the action
        retired = re.search(r"(?m)^\s+retire-old\) echo \"(What Meternaut does not use any more was deleted.*?)\" ;;$", self.step("What was done")).group(1)
        for words in ("the identity \\`id-meternaut-usage\\`", "tools/access-requirements.py retire --only W9,W10", "before this action"):
            self.assertIn(words, retired)
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        for words in ("afterwards the user-assigned identity", "it removes the user-assigned identity that the app used before"):
            self.assertNotIn(words, description, "no action promises to delete an old identity")

    def test_the_deployment_identity_never_reads_the_directory_because_it_has_no_right_to(self):
        # The application (client) id of a system-assigned identity is the application id of its service principal, which only the directory has: a person with the owner's session reads it.
        for word in ("az ad ", "az ad\n", "graph.microsoft.com", "/servicePrincipals", "az rest --method get --url \"https://graph"):
            self.assertNotIn(word, self.text, word)


class Foundry(unittest.TestCase):
    """The Foundry resource of the agents (environment/foundry/main.bicep): what it makes, how it is shut, who may do what with it, and in what order."""

    def setUp(self):
        self.source = text("environment/foundry/main.bicep")
        self.code = re.sub(r"(?m)^\s*//.*$", "", self.source)
        self.found = resources(self.source)

    def properties_of(self, source, name):
        match = re.search(rf"(?ms)^resource {name} '[^']+' = \{{\n.*?^  properties: \{{\n(.*?)^  \}}\n", source)
        self.assertIsNotNone(match, name)
        return match.group(1)

    def test_it_declares_the_resources_of_the_design_and_makes_no_dns_no_network_and_no_gateway_object(self):
        self.assertEqual(set(self.found), {"insights", "account", "guardrail", "modelDeployment", "project", "projectPublishesTraces", "tracesConnection", "aiGatewayConnection", "privateEndpoint",
                                           "casesMayUseTheAgents", "operatorMayCheckTheAgents", "projectMayRunTheEvaluationRule"})
        self.assertRegex(self.source, r"(?m)^resource insights 'Microsoft.Insights/components@2020-02-02' existing = ")
        for word in ("privateDnsZones", "privateDnsZoneGroups", "virtualNetworkLinks", "virtualNetworkPeerings", "routeTables", "Microsoft.ApiManagement",
                     "Microsoft.Network/virtualNetworks'", "networkSecurityGroups", "SecurityControl", "optOut"):
            self.assertNotIn(word, self.code, word)

    def test_the_resource_is_private_has_no_local_authentication_can_hold_projects_and_has_an_identity_of_its_own(self):
        body = self.found["account"][1]
        for line in ("kind: 'AIServices'", "name: 'S0'", "type: 'SystemAssigned'", "allowProjectManagement: true", "customSubDomainName: accountName",
                     "publicNetworkAccess: 'Disabled'", "disableLocalAuth: true", "restore: restoreAccount", "defaultAction: 'Deny'", "ipRules: []", "virtualNetworkRules: []"):
            self.assertIn(line, body)
        self.assertEqual(self.code.count("publicNetworkAccess"), 1)
        self.assertEqual(self.code.count("disableLocalAuth"), 1)
        for word in ("publicNetworkAccess: 'Enabled'", "disableLocalAuth: false", "allowProjectManagement: false", "'None'", "UserAssigned"):
            self.assertNotIn(word, self.code, word)
        self.assertRegex(self.code, r"(?m)^param restoreAccount bool = false$")
        self.assertRegex(self.code, r"(?s)@minLength\(2\)\n@maxLength\(64\)\nparam accountName string\n")

    def test_the_project_has_an_identity_of_its_own_and_its_name_is_a_parameter_with_the_default_of_the_endpoint(self):
        body = self.found["project"][1]
        self.assertIn("parent: account", body)
        self.assertIn("type: 'SystemAssigned'", body)
        self.assertIn("name: projectName", body)
        self.assertIn("location: location", body)
        self.assertRegex(self.code, r"(?m)^param projectName string = 'meternaut'$")
        self.assertNotIn("UserAssigned", body)

    def test_the_private_endpoint_goes_into_the_endpoint_subnet_of_the_model_side_and_has_no_dns_zone_group(self):
        mine = self.properties_of(self.source, "privateEndpoint")
        self.assertIn("name: 'pe-${accountName}'", self.found["privateEndpoint"][1])
        self.assertIn("groupIds: [\n            'account'\n          ]", mine)
        self.assertIn("'snet-pe'", mine)
        self.assertEqual(self.code.count("Microsoft.Network/privateEndpoints"), 1, "the one private endpoint")
        self.assertNotIn("privateDnsZoneGroups", self.code)
        self.assertIn("name: 'snet-pe'", text("environment/main.bicep"), "the subnet is the model side's")

    def test_the_order_that_a_real_deploy_needed_is_in_the_template(self):
        found = self.found
        # the project after the last deployment, the connection after the role that its identity needs, the private endpoint after every other write to the resource, the roles after it
        self.assertIn("modelDeployment", depends_on(found["project"][1]))
        self.assertIn("projectPublishesTraces", depends_on(found["tracesConnection"][1]))
        self.assertTrue({"modelDeployment", "project", "tracesConnection"} <= depends_on(found["privateEndpoint"][1]))
        self.assertIn("privateEndpoint", depends_on(found["casesMayUseTheAgents"][1]))
        self.assertIn("privateEndpoint", depends_on(found["operatorMayCheckTheAgents"][1]))
        self.assertIn("privateEndpoint", depends_on(found["projectMayRunTheEvaluationRule"][1]))
        self.assertRegex(self.source, r"@batchSize\(1\)\nresource modelDeployment ", "the resource accepts one deployment write at once")
        self.assertIn("raiPolicyName: guardrail.name", found["modelDeployment"][1], "the guardrail is made before the deployments that use it")
        # nothing else is written to the resource (or below it) at the same time as its private endpoint: each write is before it or after it, by dependsOn or by a reference
        def before(name, seen=None):
            seen = set() if seen is None else seen
            body = re.sub(r"(?m)^\s*//.*$", "", found[name][1])
            for other in found:
                if other != name and other not in seen and (other in depends_on(body) or re.search(rf"\b{other}\b", body)):
                    seen.add(other)
                    before(other, seen)
            return seen

        written = {name for name, (_, body) in found.items() if re.search(r"^  (parent|scope): (account|project)$", body, re.M)} - {"privateEndpoint"}
        beside = sorted(written - before("privateEndpoint") - {name for name in found if "privateEndpoint" in before(name)})
        self.assertEqual(beside, [], f"{beside} would be written to the resource while the private endpoint is")

    def test_the_models_are_deployed_with_the_name_version_type_and_capacity_of_the_list_and_the_guardrail_in_place_of_the_default(self):
        mine = self.found["modelDeployment"][1]
        for line in ("name: model.name", "name: model.sku", "capacity: model.capacity", "version: model.version", "versionUpgradeOption: 'NoAutoUpgrade'", "format: 'OpenAI'"):
            self.assertIn(line, mine)
        self.assertRegex(self.code, r"(?m)^param models array$")
        self.assertNotIn("Microsoft.DefaultV2", mine)

    def test_the_guardrail_is_the_default_one_with_every_filter_of_the_audit_initiative_and_the_prompt_shields_of_the_agents_all_blocking_in_one_block(self):
        body = self.found["guardrail"][1]
        self.assertIn("basePolicyName: 'Microsoft.DefaultV2'", body)
        self.assertIn("mode: 'Blocking'", body)
        filters = re.findall(r"\{ name: '([A-Za-z ]+)', source: '(\w+)', enabled: (\w+), blocking: (\w+)(?:, severityThreshold: '(\w+)')? \}", body)
        harm = ("Hate", "Sexual", "Violence", "Selfharm")
        self.assertEqual(filters, [(name, source, "true", "true", "Medium" if name in harm else "") for name, source in (
            [(name, source) for name in harm for source in ("Prompt", "Completion")]
            + [("Profanity", "Prompt"), ("Profanity", "Completion"), ("Protected Material Code", "Completion"), ("Protected Material Text", "Completion"),
               ("Jailbreak", "Prompt"), ("Indirect Attack", "Prompt"), ("Indirect Attack Spotlighting", "Prompt"), ("Indirect Attack", "PostToolCall")])])
        self.assertEqual(body.count("{ name:"), 16, "no filter in another form, and none that annotates only")
        self.assertEqual(body.count("severityThreshold:"), 8, "a severity only on the four harm categories, at both sources")
        block = re.search(r"contentFilters: \[\n(.*?)\n    \]", body, re.S).group(1)
        self.assertEqual(block.count("{ name:"), 16, "one block")
        self.assertGreaterEqual(len(re.findall(r"(?m)^    //", body)), 4, "the block has its comment: why it is there and what was not tried")
        for words in ("Guardrail for Cognitive Services Deployments", "names itself", "Not tried against the service yet", "Indirect Attack Spotlighting", "tools/foundry-check.py"):
            self.assertIn(words, body, words)
        for word in ("blocking: false", "enabled: false", "customBlocklists", "safetyProviders", "egressPolicy"):
            self.assertNotIn(word, body, word)
        self.assertRegex(self.code, r"(?m)^param guardrailName string = 'meternaut-agents'$")

    def test_the_roles_are_foundry_user_on_the_project_for_the_cases_app_the_operator_and_the_project_itself_and_one_on_the_component_and_none_on_the_group_the_account_or_the_subscription(self):
        guids = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.code))
        self.assertEqual(guids, {"53ca6127-db72-4b80-b1b0-d745d6d5456d", "3913510d-42f4-4e42-8a64-420c390055eb"})  # Foundry User, Monitoring Metrics Publisher
        assignments = {name: body for name, (kind, body) in self.found.items() if kind == "Microsoft.Authorization/roleAssignments"}
        self.assertEqual(sorted(assignments), ["casesMayUseTheAgents", "operatorMayCheckTheAgents", "projectMayRunTheEvaluationRule", "projectPublishesTraces"])
        for name, body in assignments.items():
            self.assertIn("principalType: 'ServicePrincipal'", body, name)
        self.assertEqual({name: re.search(r"(?m)^  scope: (.+)$", body).group(1) for name, body in assignments.items()},
                         {"casesMayUseTheAgents": "project", "operatorMayCheckTheAgents": "project", "projectMayRunTheEvaluationRule": "project", "projectPublishesTraces": "insights"})
        for name in ("casesMayUseTheAgents", "operatorMayCheckTheAgents", "projectMayRunTheEvaluationRule"):
            self.assertIn("roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)", assignments[name], f"{name}: Foundry User and no other role")
        # the identity of the cases app: its principal id is a parameter, so the name is known at the start
        self.assertIn("foundryUserRoleId", assignments["casesMayUseTheAgents"])
        self.assertIn("name: guid(project.id, casesSystemPrincipalId, foundryUserRoleId)", assignments["casesMayUseTheAgents"], "the name that the first step gave the role: nothing new is made")
        self.assertIn("principalId: casesSystemPrincipalId", assignments["casesMayUseTheAgents"])
        self.assertFalse(assignments["casesMayUseTheAgents"].startswith("if ("), "the role is always there: the workflow refuses to deploy while the app has no identity")
        # the Operator's identity (the tools agents-drift, foundry-evals and foundry-redteam read the project with it): only while its object id is given, so that the template still deploys with no Operator
        operator = assignments["operatorMayCheckTheAgents"]
        self.assertTrue(operator.startswith("if (!empty(operatorPrincipalId)) {"), "no role while the parameter is empty")
        self.assertIn("name: guid(project.id, operatorPrincipalId, foundryUserRoleId)", operator)
        self.assertIn("principalId: operatorPrincipalId", operator)
        self.assertRegex(self.code, r"@maxLength\(36\)\nparam operatorPrincipalId string = ''\n", "optional: empty is the default")
        # the project's own identity (the continuous evaluation rule runs as it): on the project, which is the narrower scope that Learn names; the name must not hold the principal id, which is known only after the project is made
        rule = assignments["projectMayRunTheEvaluationRule"]
        self.assertIn("principalId: project.identity.principalId", rule)
        self.assertIn("name: guid(project.id, 'the-project-itself', foundryUserRoleId)", rule)
        self.assertFalse(rule.startswith("if ("))
        self.assertIn("monitoringMetricsPublisherRoleId", assignments["projectPublishesTraces"])
        self.assertIn("principalId: project.identity.principalId", assignments["projectPublishesTraces"])
        for word in ("scope: account", "scope: resourceGroup", "scope: subscription", "subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '"):
            self.assertNotIn(word, self.code, word)
        self.assertRegex(self.code, r"@minLength\(36\)\n@maxLength\(36\)\nparam casesSystemPrincipalId string\n", "required: no default, and a guid")
        self.assertNotIn("casesPrincipalId", self.source, "the user-assigned identity of the cases app is gone: only its system-assigned identity holds the role")

    def test_the_foundry_user_role_is_the_one_that_creates_and_runs_agents_and_the_condition_of_the_deploy_identity_names_it(self):
        self.assertIn("var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'", self.source)
        page = text("environment/BOOTSTRAP.md").split("## Changed on 2026-11-06")[1]
        self.assertIn("53ca6127-db72-4b80-b1b0-d745d6d5456d", page, "the hand step adds this id to the condition, and the template gives no other role than the ones in the condition")
        self.assertIn("3913510d-42f4-4e42-8a64-420c390055eb", text("environment/BOOTSTRAP.md").split("## Added on 2026-11-04 for the usage recording")[1],
                      "Monitoring Metrics Publisher is in the condition already")

    def test_the_connection_sends_the_traces_with_the_identity_of_the_project_and_holds_no_key(self):
        body = self.found["tracesConnection"][1]
        for line in ("parent: project", "category: 'AppInsights'", "target: insights.id", "authType: 'ProjectManagedIdentity'", "isSharedToAll: false"):
            self.assertIn(line, body)
        self.assertIn("#disable-next-line BCP036\n    authType:", body, "the Bicep types do not list the value that Microsoft's own templates write")
        for word in ("credentials", "ApiKey", "apiKey", "key:", "AccountKey"):
            self.assertNotIn(word, body, word)
        self.assertIn("name: 'appi-${workload}'", body)
        self.assertIn("DisableLocalAuth: true", resources(text("environment/base/main.bicep"))["insights"][1], "the component takes telemetry only with Microsoft Entra ID")

    def test_no_key_or_secret_is_read_written_or_returned_and_the_one_connection_string_is_the_components_own_name(self):
        for word in ("listKeys", "listConnectionStrings", "listSecrets", "listAccountSas", "AccountKey", "SharedAccessKey", "primaryKey", "secondaryKey", "@secure",
                     "apiKey", "ApiKey", "instrumentationKey", "InstrumentationKey", "password", "WEBSITE_CONTENT"):
            self.assertNotIn(word, self.code, word)
        # The connection to the AI Gateway writes the property that Microsoft's sample for the project's identity writes, and it is empty: the project's identity is the credential
        # (test_aigateway_agents_template.py holds the connection itself to that).
        self.assertEqual(re.findall(r"credentials[^\n]*", self.code), ["credentials: {}"])
        lines = [line.strip() for line in self.code.splitlines() if "ConnectionString" in line]
        self.assertEqual(lines, ["ApplicationInsightsConnectionString: insights.properties.ConnectionString"],
                         "the metadata of the connection, as in Microsoft's own templates: it names the component and holds no secret that ingestion accepts")

    def test_no_output_names_a_key_and_the_outputs_are_the_ones_the_workflow_reads(self):
        outputs = re.findall(r"(?m)^output (\w+) \w+ = (.+)$", self.code)
        self.assertEqual([name for name, _ in outputs], ["projectEndpoint", "accountName", "projectName", "guardrailName", "privateEndpointName"])
        for name, value in outputs:
            for word in ("listKeys", "listSecrets", "ConnectionString", "AccountKey", "primaryKey", "key", "secret", "password", "credentials", "token"):
                self.assertNotIn(word, (name + " " + value).lower().replace("projectendpoint", ""), (name, word))
        self.assertIn("'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'", self.code)

    def test_every_type_of_the_foundry_resource_is_at_one_stable_api_version_and_the_endpoint_is_at_the_one_of_the_others(self):
        versions = set(re.findall(r"'Microsoft\.CognitiveServices/[A-Za-z/]+@([^']+)'", self.source))
        self.assertEqual(versions, {"2026-09-01"})
        self.assertEqual(re.findall(r"@[0-9-]+-preview'", self.source), [], "a preview version needs a switch with a fallback (AGENTS.md rule 11 (i)) and the Foundry resource has none")
        self.assertIn("Microsoft.Network/privateEndpoints@2025-05-01", self.source)
        self.assertIn("Microsoft.Authorization/roleAssignments@2022-04-01", self.source)

    def test_the_template_names_the_resources_that_the_other_templates_made(self):
        base = text("environment/base/main.bicep")
        self.assertIn("name: 'appi-${workload}'", base)
        self.assertIn("name: 'appi-${workload}'", self.found["insights"][1])
        self.assertIn("'vnet-${workload}', 'snet-pe'", self.found["privateEndpoint"][1])
        self.assertIn("name: 'snet-pe'", text("environment/main.bicep"))
        self.assertRegex(self.code, r"(?m)^param workload string = 'meternaut'$")

    def test_the_template_compiles(self):
        import json
        import shutil
        import subprocess

        python = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")
        az = [str(python), "-IBm", "azure.cli"] if python.exists() else ([shutil.which("az")] if shutil.which("az") else None)
        bicep = Path.home() / ".azure" / "bin" / ("bicep.exe" if python.exists() else "bicep")
        if az is None or not bicep.exists():
            self.skipTest("no Azure CLI with Bicep on this machine: the workflow and the checks compile every template")
        done = subprocess.run([*az, "bicep", "build", "--file", str(ROOT / "environment" / "foundry" / "main.bicep"), "--stdout"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        compiled = json.loads(done.stdout)
        self.assertEqual({r["type"] for r in compiled["resources"]},
                         {"Microsoft.CognitiveServices/accounts", "Microsoft.CognitiveServices/accounts/raiPolicies", "Microsoft.CognitiveServices/accounts/deployments",
                          "Microsoft.CognitiveServices/accounts/projects", "Microsoft.CognitiveServices/accounts/projects/connections", "Microsoft.Network/privateEndpoints",
                          "Microsoft.Authorization/roleAssignments"})
        self.assertEqual(set(compiled["outputs"]), {"projectEndpoint", "accountName", "projectName", "guardrailName", "privateEndpointName"})


class PageLatencyWorkflow(unittest.TestCase):
    """The action page-latency: how fast the web page answers, measured by tools/console-check.py latency in a container group of the Operator, over the app's private endpoint. It only reads."""

    FIND = "Find the Operator, which runs the check from inside the network"
    PLAN = "Say which plan the web page runs on"
    MEASURE = "Measure how fast the web page answers, from inside the network, in the Operator"
    CLEANUP = "Delete any container group of the latency measurement that is left"

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}\n")]
        return block

    def script(self, title):
        body = self.step(title).split("        run: |\n", 1)[1]
        return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))

    def test_the_action_is_one_of_the_options_with_a_minutes_input_of_20_by_default_and_a_description(self):
        options = re.search(r"(?m)^        options:\n((?:          - [a-z-]+\n)+)", self.text).group(1)
        self.assertIn("          - page-latency\n", options)
        self.assertLess(options.index("- cases-run"), options.index("- page-latency"))
        self.assertRegex(self.text, r'(?m)^      minutes:\n        description: "Only with page-latency: [^"]+"\n        type: string\n        required: false\n        default: "20"\n')
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        for words in ("page-latency: measure how fast the web page answers, by the Operator from inside the network over the app's private endpoint and with no credential",
                      "a request to /healthz every ten seconds for the minutes of the input minutes (20 at the most)", "It only reads, and it needs operator first.",
                      "docs/proposals/07-private-by-default.md (the web page on Flex Consumption)"):
            self.assertIn(words, description, words)

    def test_the_steps_find_the_operator_say_the_plan_measure_and_clean_up_in_that_order_and_for_this_action_only(self):
        positions = [self.names.index(name) for name in (self.FIND, self.PLAN, self.MEASURE, self.CLEANUP)]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(self.names.index("Work out the settings"), positions[0])
        self.assertLess(positions[-1], self.names.index("What was done"))
        self.assertIn("if: inputs.action == 'page-latency'\n", self.step(self.PLAN))
        self.assertIn("if: inputs.action == 'page-latency'\n", self.step(self.MEASURE))
        self.assertIn("if: always() && inputs.action == 'page-latency' && steps.latency.outcome != 'skipped'\n", self.step(self.CLEANUP), "the second line behind the tool's own delete")
        self.assertIn("id: latency\n", self.step(self.MEASURE))

    def test_it_reads_only_nothing_is_written_deployed_deleted_or_sent_and_no_credential_is_given_to_the_container(self):
        for title in (self.PLAN, self.MEASURE):
            script = self.script(title)
            self.assertNotRegex(script, r"--method (put|patch|post|delete)", title)
            for word in ("az deployment", "tools/az-deploy.py", "az role", "AZURE_FEDERATED_TOKEN", "--secure-env", "ACTIONS_ID_TOKEN", "az eventhubs", "tools/cases-check.py", "tools/recording-check.py"):
                self.assertNotIn(word, script, f"{title}: {word}")
        script = self.script(self.MEASURE)
        self.assertIn('--secret-file "console-check.py=tools/console-check.py"', script, "the one tool, and nothing else in the volume")
        self.assertEqual(script.count("--secret-file"), 1)
        self.assertIn('--env "TOOL_NAME=console-check" --env "TOOL_ARGS=latency --host $FUNCTION_APP.azurewebsites.net --private --minutes $MINUTES --interval 10"', script.replace(" \\\n            ", " "),
                      "over the app's private endpoint, on the app's own name, and the name has to resolve to a private address there")
        self.assertIn("--script operator/run-tool.sh", script)
        self.assertIn('--name "op-latency-$GITHUB_RUN_ID"', script, "the prefix of the cleanup is the start of this name, and of no other group's")
        self.assertIn('--timeout-seconds "$seconds" --summary "$GITHUB_STEP_SUMMARY"', script)
        self.assertIn("seconds=$((MINUTES * 60 + 300))", script, "the measurement's minutes and five more: 1500 seconds at the most, which is the Operator's 25 minutes")
        self.assertIn('"${dns[@]}"', script)
        self.assertEqual(self.step(self.CLEANUP).count("--prefix op-latency-"), 1)
        for other in ("op-check-", "op-door-", "op-health-", "op-probe-", "op-publish-", "op-aigw-"):
            self.assertNotIn(other, self.step(self.MEASURE) + self.step(self.CLEANUP), other)

    def test_the_minutes_reach_the_script_through_the_environment_and_are_checked_before_anything_runs(self):
        block = self.step(self.MEASURE)
        self.assertIn("MINUTES: ${{ inputs.minutes }}", block)
        script = self.script(self.MEASURE)
        self.assertNotIn("${{", script, "no expression inside a script (tools/workflow-lint.py)")
        self.assertIn('if ! [[ "$MINUTES" =~ ^[0-9]{1,2}$ ]] || [ "$MINUTES" -lt 1 ] || [ "$MINUTES" -gt 20 ]; then', script)
        self.assertLess(script.index('"$MINUTES" -gt 20'), script.index("python3 tools/operator-run.py run"))
        self.assertIn("timeout-minutes: 30\n", block, "the group is given at most 25 minutes, and the step a second line five minutes behind")

    def test_the_summary_of_the_run_has_the_summary_lines_of_the_tool_and_a_failed_rule_is_a_failed_run_with_words_for_what_to_do(self):
        script = self.script(self.MEASURE)
        self.assertIn('| tee "$RUNNER_TEMP/latency.log" || status=$?', script, "the exit code of the tool is kept, and the log is kept to read the summary from")
        self.assertIn("sed -n -E 's/^\\| (latency: [0-9]+ requests, p50.*|after the quiet gap: .*|verdict: .*)$/\\1/p' \"$RUNNER_TEMP/latency.log\"", script)
        self.assertIn('echo "### How fast the web page answers: $MINUTES minutes, from inside the network"', script)
        self.assertIn('exit "$status"', script)
        self.assertIn("goes to Basic only on his word, and then cases is run", script)
        tool = text("tools/console-check.py")
        for line in ("latency: {len(seconds)} requests, p50", "after the quiet gap: {len(cold)} requests", "verdict: "):
            self.assertIn(line, tool, "the lines that the step's sed picks out are the ones that the tool prints")

    def test_the_plan_is_read_and_said_so_that_the_measurement_says_what_it_measured(self):
        script = self.script(self.PLAN)
        self.assertIn("--query properties.serverFarmId", script)
        self.assertIn("--query sku.tier", script)
        self.assertIn("The cases app is not there, so there is no web page to measure. Run cases first.", script)
        self.assertIn("WANTED_KIND: ${{ steps.params.outputs.cases_app_plan }}", self.step(self.PLAN))

    def test_the_summaries_say_what_a_stall_means_and_that_nothing_was_changed(self):
        block = self.step("What was done")
        failed, finished = re.findall(r"(?m)^\s+page-latency\) echo \"(.*?)\" ;;$", block)
        for words in ("Nothing was changed: the measurement only reads.", "that the Operator is not there (run \\`operator\\` first)", "that the cases app is not there (run \\`cases\\` first)",
                      "goes to Basic only on his word, and then \\`cases\\` is run", "Running \\`page-latency\\` again is safe."):
            self.assertIn(words, failed, words)
        for words in ("asked the web page's \\`/healthz\\` over the app's private endpoint with no credential", "this runner asked nothing",
                      "The decision needs two such measurements of 20 minutes each. Nothing was changed."):
            self.assertIn(words, finished, words)


class FoundryWorkflow(unittest.TestCase):
    """The action foundry of the deploy workflow: what runs for it, in what order, and what it reads back."""

    ORDER = ["The base and the cases app's identity are there, which the Foundry resource builds on", "Deploy the Foundry resource of the agents",
             "Wait until the landing zone has registered the Foundry resource's private endpoint in the central zones",
             "Sign in to Azure again for the read-back of the Foundry resource, because the first sign-in's credential lasts five minutes", "Read the Foundry resource back"]

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}")]
        return block

    def script(self, title):
        return "\n".join(line for line in self.step(title).split("run:")[1].splitlines() if not line.strip().startswith("#"))

    def test_the_action_is_offered_between_retire_old_and_the_cases_and_is_described_in_plain_words(self):
        options = re.search(r"options:\n((?:          - .+\n)+)", self.text).group(1)
        offered = re.findall(r"- (\S+)", options)
        self.assertEqual(offered[offered.index("retire-old") + 1:offered.index("retire-old") + 4], ["retire-event-hubs", "foundry", "cases"])
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        self.assertIn(" foundry: the Foundry resource of the agents", description)
        for word in ("no key", "private endpoint", "model account cannot hold projects"):
            self.assertIn(word, description.split(" foundry: ")[1])

    def test_the_steps_run_for_the_action_alone_in_the_order_of_the_owner_before_the_cases_and_after_the_settings_are_known(self):
        positions = [self.names.index(name) for name in self.ORDER]
        self.assertEqual(positions, sorted(positions))
        for name in self.ORDER:
            self.assertIn("if: inputs.action == 'foundry'", self.step(name), name)
        self.assertLess(self.names.index("Work out the settings"), positions[0])
        self.assertLess(positions[-1], self.names.index("The base is there, which the first cases build on"))
        self.assertEqual(len(re.findall(r"inputs\.action == 'foundry'", self.text)), len(self.ORDER), "these five steps, and no other step that runs for this action")

    def test_the_deploy_makes_the_resource_from_the_template_and_the_file_restores_a_removed_one_and_checks_the_address_it_gives_the_cases_app(self):
        block = self.step("Deploy the Foundry resource of the agents")
        for word in ("--template environment/foundry/main.bicep", '--parameters "$RUNNER_TEMP/foundry.parameters.json"', '--name "foundry-$GITHUB_RUN_ID"', "--output projectEndpoint",
                     "--restore-param restoreAccount", "EXPECTED_ENDPOINT: ${{ steps.params.outputs.foundry_project_endpoint }}"):
            self.assertIn(word, block)
        self.assertIn('if [ "${endpoint%/}" != "${EXPECTED_ENDPOINT%/}" ]; then', block)
        self.assertIn("exit 1", block)
        self.assertEqual(self.text.count("--template environment/foundry/main.bicep"), 2, "the preview and the deploy, nothing else")
        self.assertEqual(self.text.count("python3 tools/az-deploy.py create"), len(re.findall(r"python3 tools/az-deploy.py create", self.text)))
        for word in ("az role", "delete", "listKeys", "listSecrets", "--auth-mode key"):
            self.assertNotIn(word, block, word)

    def test_nothing_is_deployed_without_the_component_the_cases_app_with_its_own_identity_and_a_file_that_carries_the_identity(self):
        title = self.ORDER[0]
        block = self.step(title)
        self.assertIn("INSIGHTS_NAME: ${{ steps.params.outputs.appinsights_name }}", block)
        self.assertIn("CASES_APP: ${{ steps.params.outputs.cases_function_app_name }}", block)
        self.assertNotIn("CASES_IDENTITY", block, "the user-assigned identity of the cases app is gone: its own system-assigned one is read from the app")
        self.assertNotIn("az identity", block)
        self.assertIn("Run base first", block)
        self.assertIn("Run cases first", block)
        self.assertIn('az rest --method get --url "https://management.azure.com${site}?api-version=2024-04-01" --query identity.principalId --output tsv', block)
        self.assertIn('grep -Fqi "\\"$principal\\"" "$RUNNER_TEMP/foundry.parameters.json"', block)
        script = self.script(title)
        self.assertEqual(len(re.findall(r"exit 1", script)), 4, "no component, no app, no identity of the app, and a file that does not carry it")
        self.assertNotIn("az-deploy.py", script)
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        self.assertLess(self.names.index(title), self.names.index("Deploy the Foundry resource of the agents"))

    def test_the_wait_asks_for_the_zone_of_the_project_endpoints_host_name_fails_without_it_and_creates_no_zone(self):
        title = self.ORDER[2]
        block = self.step(title)
        self.assertIn("PRIVATE_ENDPOINT: ${{ steps.params.outputs.foundry_private_endpoint }}", block)
        self.assertIn("az network private-endpoint dns-zone-group list", block)
        self.assertIn("grep -qi 'privatelink.services.ai.azure.com' <<< \"$zones\"", block)
        self.assertIn("attempts=40", block)
        script = self.script(title)
        self.assertEqual(script.rstrip().splitlines()[-1].strip(), "exit 1", "it ends in a failure when no check passed")
        self.assertIn("do not create a private DNS zone", block)
        for word in ("az network private-dns", "az network private-endpoint dns-zone-group create", "--method put", "az role", "privateDnsZones"):
            self.assertNotIn(word, block, word)
        self.assertLess(self.names.index("Deploy the Foundry resource of the agents"), self.names.index(title))

    def test_the_read_back_signs_in_again_and_runs_the_tool_with_the_names_the_settings_gave_and_the_models_of_the_repository(self):
        title = self.ORDER[4]
        block = self.step(title)
        self.assertIn("uses: azure/login@", self.step(self.ORDER[3]))
        for word in ("python3 tools/foundry-check.py read-back", '--subscription "$ENV_SUBSCRIPTION_ID"', '--resource-group "$ENV_RESOURCE_GROUP"', '--account "$FOUNDRY_ACCOUNT"',
                     '--project "$FOUNDRY_PROJECT"', '--guardrail "$FOUNDRY_GUARDRAIL"', '--private-endpoint "$PRIVATE_ENDPOINT"', '--endpoint "$PROJECT_ENDPOINT"',
                     "--models environment/models.json", '--summary "$GITHUB_STEP_SUMMARY"'):
            self.assertIn(word, block)
        for env_name, output in (("FOUNDRY_ACCOUNT", "foundry_account_name"), ("FOUNDRY_PROJECT", "foundry_project_name"), ("FOUNDRY_GUARDRAIL", "foundry_guardrail_name"),
                                 ("PRIVATE_ENDPOINT", "foundry_private_endpoint"), ("PROJECT_ENDPOINT", "foundry_project_endpoint")):
            self.assertIn(f"{env_name}: ${{{{ steps.params.outputs.{output} }}}}", block)
        self.assertEqual(self.text.count("foundry-check.py read-back"), 1)
        self.assertIn("        timeout-minutes: 20\n", block, "a step that waits for Azure has a limit of its own, besides the two minutes of each read")
        self.assertNotIn("|| true", block, "a difference stops the run")
        self.assertNotIn("continue-on-error", block)
        self.assertEqual(self.names.index(title) - self.names.index(self.ORDER[3]), 1)

    def test_the_foundry_file_is_made_checked_against_its_compiled_template_and_the_template_is_compiled_where_the_others_are(self):
        # The Hub compiles each template to a file, for the check of its parameter file; the compile-and-lint loop of the templates is CI's, run once for the commit that is pushed to main (the Hub reads that it passed).
        self.assertNotIn("az bicep lint", self.text, "the lint of the templates is CI's: the Hub does not repeat it")
        self.assertIn('az bicep build --file environment/foundry/main.bicep --outfile "$RUNNER_TEMP/foundry.json"', self.text)
        params = [b for b in self.steps if b.startswith("name: Work out the settings\n")][0]
        self.assertIn('python3 tools/environment-params.py check --params "$RUNNER_TEMP/foundry.parameters.json" --template "$RUNNER_TEMP/foundry.json" --label foundry', params)
        checks = text(".github/workflows/checks.yml")
        self.assertIn("environment/base/main.bicep environment/foundry/main.bicep environment/cases/main.bicep", checks)
        self.assertIn('az bicep build --file environment/foundry/main.bicep --outfile "$out/foundry.json"', checks)
        self.assertIn('--params "$out/foundry.parameters.json" --template "$out/foundry.json" --label foundry', checks)

    def test_the_preview_shows_the_foundry_resource_when_the_component_it_connects_to_is_there_and_says_why_not_otherwise(self):
        block = self.step(PREVIEW_STEP)
        self.assertIn("INSIGHTS_NAME: ${{ steps.params.outputs.appinsights_name }}", block)
        self.assertLess(block.index("The Foundry resource cannot be previewed yet"), block.index("--template environment/foundry/main.bicep"))
        self.assertIn("--restore-param restoreAccount", block[block.index("--template environment/foundry/main.bicep"):])
        self.assertLess(block.index("--template environment/base/main.bicep"), block.index("--template environment/foundry/main.bicep"))
        self.assertLess(block.index("--template environment/foundry/main.bicep"), block.index("--template environment/cases/main.bicep"))
        self.assertNotIn("az-deploy.py create", block)

    def test_the_cases_app_is_given_the_project_address_from_what_is_in_azure_and_the_cases_action_has_no_step_of_its_own_for_it(self):
        params = [b for b in self.steps if b.startswith("name: Work out the settings\n")][0]
        self.assertIn('project_url="/subscriptions/$ENV_SUBSCRIPTION_ID/resourceGroups/$ENV_RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$foundry_account/projects/$foundry_project"', params)
        self.assertEqual(re.findall(r'exists "\$project_url" ([0-9-]+(?: warning)?)', params), ["2025-06-01", "2025-06-01 warning"], "existence needs the version that the model account uses, not the newest")
        self.assertNotIn("2026-09-01", params)
        self.assertIn('CASES_SYSTEM_PRINCIPAL_ID="$cases_system_principal" ENV_FOUNDRY_PROJECT_EXISTS="$foundry_exists" python3 tools/environment-params.py build', params)
        self.assertNotIn("CASES_PRINCIPAL_ID", params, "the user-assigned identity of the cases app is no longer looked for")
        self.assertIn("could not be read", params, "a failure that is not 'not found' stops the run: the app is never given an address by a wrong guess")
        self.assertNotRegex(params, r"--method (put|patch|post|delete)")
        self.assertEqual(len(re.findall(r"if: .*'foundry'.*'cases'|if: .*'cases'.*'foundry'", self.text)), 0)
        self.assertIn('--parameters "$RUNNER_TEMP/cases.parameters.json"', self.step("Deploy the first cases"))

    def test_the_project_is_looked_for_only_by_the_actions_that_use_the_answer_and_a_failed_read_stops_cases_and_is_a_warning_for_what_if(self):
        params = [b for b in self.steps if b.startswith("name: Work out the settings\n")][0]
        self.assertIn("exists() {\n            local found level=\"${3:-error}\"", params, "the level of the annotation is the caller's")
        self.assertIn('echo "::${level}::${1##*/} could not be read: $found" >&2', params)
        self.assertEqual(len(re.findall(r"(?m)^\s+(what-if\|foundry\|aigateway)\)$", params)), 1, "the identity is looked for by what-if, foundry and aigateway only: the Foundry file and the AI Gateway file carry it")
        self.assertEqual(len(re.findall(r"(?m)^\s+cases\)$", params)), 1)
        self.assertEqual(len(re.findall(r"(?m)^\s+what-if\)$", params)), 1)
        self.assertEqual(len(re.findall(r'(?m)^\s+\*\) echo "The action \$ACTION does not use the Foundry project, so it is not looked for\." ;;$', params)), 1)
        self.assertEqual(params.count("az identity list"), 0, "no identity is listed: neither the gateway's nor the user-assigned one that the cases app used before")
        self.assertNotIn("cases_principal=", params.replace("cases_system_principal=", ""))
        self.assertEqual(params.count("cases_system_principal=$(az rest --method get"), 1, "the system-assigned identity is read from the app, once, and not by an action that has nothing to do with the Foundry resource")
        self.assertIn('--url "https://management.azure.com${cases_site}?api-version=2024-04-01" --query identity.principalId --output tsv', params)
        self.assertLess(params.index("what-if|foundry|aigateway)"), params.index("cases_system_principal=$(az rest"), "inside the branch that only what-if, foundry and aigateway take")
        self.assertLess(params.index("cases_system_principal=$(az rest"), re.search(r"(?m)^\s+cases\)$", params).start())
        defaults = params.index("cases_system_principal=\"\"\n            foundry_exists=false")
        self.assertLess(defaults, params.index("cases_system_principal=$(az rest"), "false is the answer for every action that does not look")
        self.assertLess(defaults, params.index("case \"$ACTION\" in"), "and the defaults are set before the first case that looks")
        self.assertEqual(params.count("case \"$ACTION\" in"), 3, "the two cases of the Foundry facts and the one of the AI Gateway's host name: no case for the identity of a gateway of the owner's API Management instance comes before them")
        self.assertIn("Nothing was changed: run cases again.", params)
        self.assertIn('echo "::warning::The preview of the cases app assumes that the Foundry project is not in Azure', params)
        self.assertNotIn("ACTION: ${{", params.split("run: |")[0], "the job's ACTION is used")
        self.assertIn("ACTION: ${{ inputs.action }}", self.text.split("    steps:")[0])

    def test_the_settings_step_reads_the_identity_of_the_operator_for_foundry_and_what_if_only_and_hands_its_object_id_to_the_final_build_on_a_line_of_its_own(self):
        # The Foundry file gives that identity the Foundry User role on the project (docs/proposals/11-agent-harness-and-evaluation.md): the tools that check the agents read the project with it.
        params = [b for b in self.steps if b.startswith("name: Work out the settings\n")][0]
        self.assertRegex(params, r'(?m)^ +operator_principal=""\n +if \[ "\$ACTION" = foundry \] \|\| \[ "\$ACTION" = what-if \]; then\n +if operator_principal=\$\(az rest --method get ')
        self.assertIn("/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator?api-version=2023-01-31\" --query properties.principalId --output tsv 2>&1); then", params)
        self.assertEqual(params.count("userAssignedIdentities/id-meternaut-operator"), 1, "read once, by the name that the AI security's step reads it by")
        self.assertEqual(len(re.findall(r"echo \"::error::The Operator's identity could not be read", params)), 1, "a read that fails stops foundry")
        self.assertEqual(len(re.findall(r"echo \"::warning::The Operator's identity could not be read", params)), 1, "and is a warning for what-if")
        self.assertEqual(params.count("OPERATOR_PRINCIPAL_ID"), 1, "one place: the export before the final build, and not inside the builder's line, which other tests hold to its words")
        self.assertRegex(params, r'(?m)^          export OPERATOR_PRINCIPAL_ID="\$operator_principal"\n')
        self.assertLess(params.index('operator_principal=""'), params.index("export OPERATOR_PRINCIPAL_ID"))
        self.assertLess(params.index("export OPERATOR_PRINCIPAL_ID"), params.rindex("python3 tools/environment-params.py build"), "the final build gets it and the preview does not")
        self.assertEqual(params.count("--preview"), 1)

    def test_the_texts_of_the_watch_say_that_it_changes_no_resource_of_the_estate_and_what_the_investigation_adds(self):
        block = self.step("Start one Watch and read its History")
        comment = " ".join(line.strip()[2:] for line in block.splitlines() if line.strip().startswith("# "))
        for words in ("The Watch changes no resource of the estate: it reads Azure and calls the AI Gateway with its own identity and no key",
                      "With the investigation on (the cases app has the address of the Foundry project",
                      "it also creates its agents and conversations in its own Foundry project, and those agents call their models through the project's connection and the AI Gateway while the switch "
                      "AGENTS_VIA_AI_GATEWAY (tools/environment-params.py, True since the owner's order of 2026-11-07) is on",
                      "With the switch set to False, the way back, they call the models of that resource directly, which AGENTS.md rule 15 (c) allows only as the owner's written exception."):
            self.assertIn(words, comment)
        self.assertNotIn("calls the model deployments of its own Foundry project directly, with its own identity", comment)
        for old in ("only reads Azure", "it only reads", "went through the gateway", "Nothing in Azure was changed"):
            self.assertNotIn(old, self.text, old)
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        self.assertIn("its Watch changes no resource of the estate (with the investigation on it also creates agents and conversations in its own Foundry project)", description)

    def test_the_summary_for_a_failed_and_a_finished_run_says_what_the_resources_hold_gives_the_endpoint_and_names_no_key(self):
        block = self.step("What was done")
        for env_name, output in (("FOUNDRY_ACCOUNT", "foundry_account_name"), ("FOUNDRY_PROJECT", "foundry_project_name"), ("FOUNDRY_ENDPOINT", "foundry_project_endpoint")):
            self.assertIn(f"{env_name}: ${{{{ steps.params.outputs.{output} }}}}", block)
        self.assertEqual(len(re.findall(r"^\s+foundry\) echo ", block, re.M)), 2)
        (failed, finished) = re.findall(r"(?m)^\s+foundry\) echo \"(.*?)\" ;;$", block)
        for words in ("\\`$FOUNDRY_ACCOUNT\\`", "\\`$FOUNDRY_PROJECT\\`", "\\`$FOUNDRY_ENDPOINT\\`", "public network access and local authentication are off", "project management is on",
                      "guardrail that blocks jailbreaks and indirect attacks", "private endpoint is approved", "traces to Application Insights with its identity",
                      "Foundry User role on the project and nothing else there", "was read back from Azure", "No key was made, read or printed"):
            self.assertIn(words, finished, words)
        self.assertIn("run \\`cases\\` only after a run of \\`foundry\\` that passed", failed)
        for text_ in (failed, finished):
            for word in ("listKeys", "listSecrets", "primaryKey", "AccountKey", "SharedAccessKey", "connection string", "password"):
                self.assertNotIn(word, text_, word)


class FoundryHandStep(unittest.TestCase):
    """The hand step of environment/BOOTSTRAP.md that adds the Foundry User role to the condition of the deploy identity: what its text says, and what its commands may do."""

    def setUp(self):
        self.section = text("environment/BOOTSTRAP.md").split("## Changed on 2026-11-06: the Foundry resource of the agents")[1].split("\n## ")[0]
        (self.script,) = re.findall(r"```powershell\n(.*?)\n```", self.section, re.S)
        self.lines = self.script.splitlines()

    def test_the_condition_is_changed_in_place_with_one_update_and_no_assignment_is_deleted_or_made(self):
        self.assertEqual(len(re.findall(r"^az role assignment update ", self.script, re.M)), 1, "one write")
        for word in ("role assignment delete", "role assignment create", "--ids", "restore", "Restore"):
            self.assertNotIn(word, self.script, word)
        self.assertEqual(sorted(set(re.findall(r"az role assignment (\w+)", self.script))), ["list", "update"])
        self.assertIn("$old.condition = $condition\n$json = $old | ConvertTo-Json -Depth 20 -Compress\n", self.script, "the assignment that was read is the one that is written, with the new condition")
        self.assertIn("az role assignment update --subscription $devSub --role-assignment ($json -replace '\"', '\"\"') --output none\n", self.script)

    def test_every_command_names_the_subscription_of_the_pilot(self):
        calls = re.findall(r"az role assignment (?:list|update)[^\n]*", self.script)
        self.assertEqual(len(calls), 3, "the text that tells the person how to read it, the list function and the update")
        for call in calls:
            self.assertIn("--subscription $devSub", call, call)
        self.assertNotIn("az account set", self.script, "the CLI's default subscription is never taken as the pilot's scope")

    def test_the_exit_code_of_every_command_is_tested_and_a_failed_update_says_that_the_assignment_is_unchanged(self):
        self.assertGreaterEqual(self.script.count("if ($LASTEXITCODE -ne 0) { throw"), 5, "the two reads, the update, and the two reads back")
        update = self.script.index("az role assignment update ")
        after = self.script[update:].split("\n", 2)[1]
        self.assertTrue(after.startswith('if ($LASTEXITCODE -ne 0) { throw "The update failed (exit code $LASTEXITCODE). It is one write and nothing else was done, so the assignment is unchanged.'), after)
        self.assertIn("Read it: $read", after, "it says how to read the assignment")

    def test_it_reads_before_it_writes_shows_the_difference_and_asks_and_reads_back_after(self):
        order = [self.script.index(word) for word in ("Get-Assignments 'length(@)'", "$old = $text | ConvertFrom-Json", "$shape = {", "Write-Host \"Role ids now:", "Read-Host 'Change the condition as shown? Type yes'",
                                                      "az role assignment update ", "$new = $text | ConvertFrom-Json", "Write-Host \"Read back:")]
        self.assertEqual(order, sorted(order))
        self.assertIn("-ne 'yes') { throw 'Stopped. Nothing was changed.' }", self.script)
        self.assertEqual(self.script.count("Read-Host"), 1)
        # the read back: one assignment, the same one, both lists equal to the ids that were meant
        for words in ("$new.id -ne $old.id", "$after.Count -ne 2", "$after[0] -ne $meant", "$after[1] -ne $meant", "\"$count\".Trim() -ne '1'"):
            self.assertIn(words, self.script)
        self.assertEqual(self.script.count("\"$count\".Trim() -ne '1'"), 2, "exactly one assignment before the write and after it")

    def test_the_json_reaches_the_cli_unchanged_in_windows_powershell_and_in_powershell_7(self):
        self.assertEqual(self.lines[0], "function az { $PSNativeCommandArgumentPassing = 'Legacy'; & 'C:\\Program Files\\Microsoft SDKs\\Azure\\CLI2\\python.exe' -IBm azure.cli @args }",
                         "PowerShell 7.3 and later escape the quotes of an argument themselves, so the function asks for the older way, which Windows PowerShell 5.1 and PowerShell 7.1 have")
        self.assertNotIn("'\\\"'", self.script, "no backslash before a quote: Windows PowerShell 5.1 does not take it")
        self.assertTrue(self.script.isascii(), "commands that are copied into a console hold plain characters only")

    def test_the_section_says_what_the_read_back_checks_including_the_endpoint_the_pages_and_the_time_limit(self):
        for words in ("the project reports an endpoint and it is the address that the cases app is given", "(a list is read to its last page)",
                      "the guardrail holds each of its sixteen filters, on and blocking", "from the severity Medium", "Jailbreak and Indirect Attack on the user input, Indirect Attack on tool results",
                      "No read waits longer than two minutes",
                      "fails the run with a message that names the request, and nothing after it is read"):
            self.assertIn(words, self.section, words)

    def test_the_text_says_one_write_in_place_what_is_read_and_checked_and_that_any_answer_but_yes_changes_nothing(self):
        for words in ("changed **in place, with one write**", "`az role assignment update`", "the assignment keeps its id", "exactly one assignment", "They test the exit code of the update",
                      "the assignment is unchanged", "read the assignment back", "with the same id", "any other answer is a dry run that changes nothing",
                      "PowerShell 7 and in Windows PowerShell 5.1", "Paste them as one block, or save them as a `.ps1` file"):
            self.assertIn(words, self.section, words)
        for old in ("delete, then create", "replaced as a whole", "two writes"):
            self.assertNotIn(old, self.section, old)
        self.assertIn("53ca6127-db72-4b80-b1b0-d745d6d5456d", self.script)


class HandSteps(unittest.TestCase):
    """environment/BOOTSTRAP.md: the page of the hand steps does not list as required what no longer exists, and says what replaced it."""

    def setUp(self):
        self.page = text("environment/BOOTSTRAP.md")
        self.template = text("environment/cases/main.bicep")
        self.change = self.page.split("## Changed on 2026-11-05: Meternaut runs a change as the person who approves it")[1].split("\n## ")[0]

    def test_the_writers_role_is_a_retired_step_and_its_removal_and_the_one_new_entra_step_are_listed(self):
        self.assertIn("1. **Retired on 2026-11-05: the writer's custom role and its one assignment. Do not make them.**", self.page)
        for command in ("python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --only W1\n",
                        "python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --only W1 --apply\n"):
            self.assertIn(command, self.change)
        for words in ("user_impersonation", "Azure Service Management", "https://<host>/arm/return", "tools/entra-setup.py", "id-meternaut-runner",
                      "no refresh token", "api://AzureADTokenExchange", "no secret, no certificate"):
            self.assertIn(words, self.change)
        for gone in ("check --only W1", "grant --only W1", "the only identity that changes Azure", "which is the only identity"):
            self.assertNotIn(gone, self.page)

    def test_the_settings_that_the_page_says_are_gone_are_gone_from_the_template_and_the_new_ones_are_in_it(self):
        for name in ("WRITER_RESOURCE_GROUP", "WRITER_SUBSCRIPTION_ID", "WRITER_CLIENT_ID", "APPROVAL_DELAY_SECONDS"):
            self.assertIn(f"`{name}`", self.change)
            self.assertNotIn(name, self.template, name)
        for name in ("CHANGE_SCOPES", "SIGNIN_TENANT_ID", "SIGNIN_CLIENT_ID"):
            self.assertIn(f"`{name}`", self.change)
            self.assertIn(f"name: '{name}'", self.template, name)
        for name in ("CHANGE_RESOURCE_GROUP", "CHANGE_SUBSCRIPTION_ID"):
            self.assertIn(f"`{name}`", self.change, "the page says that the two older settings are replaced by the list")
            self.assertNotIn(name, self.template, name)


class NoStandingRightToSend(unittest.TestCase):
    """The deploy identity holds no role on the control queue (private by default, docs/proposals/07-private-by-default.md): the Operator puts the control message there, with a role on that one queue,
    and the cases app reads it with the role on the storage account that its host needs. No identity of a gateway holds a role on a queue (2026-11-07)."""

    TEMPLATES = ("environment/cases/main.bicep",)

    def test_neither_template_names_the_workflow_s_principal_takes_a_parameter_for_it_or_declares_a_role_for_it_on_the_control_queue(self):
        for path in self.TEMPLATES:
            source = text(path)
            code = re.sub(r"//.*", "", source)
            self.assertNotIn("workflowPrincipalId", code, path)
            self.assertNotIn("workflowSendsControl", code, path)
            self.assertEqual([name for name in re.findall(r"(?m)^param (\w+) ", code) if "workflow" in name.lower() or "deployer" in name.lower()], [], path)
            found = resources(source)
            self.assertEqual(sorted(name for name, (kind, _) in found.items() if "workflow" in name.lower() or "deployer" in name.lower()), [], path)
            on_the_control_queue = sorted(name for name, (kind, body) in found.items() if kind == "Microsoft.Authorization/roleAssignments" and re.search(r"(?m)^  scope: controlQueue$", body))
            self.assertEqual(on_the_control_queue, [], f"{path}: no role on the queue itself: the app's role on the account covers its trigger, and nobody but the Operator puts a message there")
            for name, (kind, body) in found.items():
                if kind == "Microsoft.Authorization/roleAssignments":
                    principal = re.search(r"(?m)^    principalId: (.+)$", body).group(1)
                    self.assertEqual(principal, "functionApp.identity.principalId", f"{path} {name}: the principal of a role is the app's own, and no gateway has a role here any more")

    def test_the_cases_template_has_no_role_to_put_a_message_in_the_queue_because_the_operator_holds_it_in_its_own_template(self):
        code = re.sub(r"//.*", "", text("environment/cases/main.bicep"))
        for role in ("c6a89b2d-59bc-44d0-9896-0f6e12d7b80a",  # Storage Queue Data Message Sender
                     "2b629674-e913-4c01-ae53-ef4638d8f975",  # Azure Event Hubs Data Sender
                     "a638d3c7-ab3a-418d-83e6-5f17a39d4fde"):  # Azure Event Hubs Data Receiver
            self.assertNotIn(role, code)

    def test_the_role_of_the_operator_on_the_queue_is_declared_in_its_own_template_on_that_one_queue_and_the_base_and_no_gateway_has_none(self):
        source = text("environment/operator/main.bicep")
        operator = resources(source)
        body = operator["operatorPutsCasesControl"][1]
        self.assertIn("  scope: casesControlQueue\n", body, "the role is on the one queue, never on the storage account or the group")
        self.assertIn("storageQueueDataContributorRoleId", body)
        self.assertIn("    principalId: operatorIdentity.properties.principalId\n", body)
        self.assertIn("  name: guid(casesControlQueue.id, operatorIdentity.id, storageQueueDataContributorRoleId)\n", body)
        self.assertEqual(sorted(name for name, (kind, _) in operator.items() if kind == "Microsoft.Authorization/roleAssignments"), ["operatorPutsCasesControl", "operatorReadsTheGroup"])
        self.assertEqual(operator["casesControlQueue"][0], "Microsoft.Storage/storageAccounts/queueServices/queues")
        self.assertRegex(source, r"resource casesControlQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@[0-9-]+' existing = \{\n  parent: queueService\n  name: casesControlQueueName\n\}",
                         "the template only reads the queue that the cases template makes: the actions base and cases run before operator")
        self.assertIn("var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'", source)
        code = re.sub(r"//.*", "", source)
        self.assertEqual(sorted(set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", code))),
                         ["974c5e8b-45b9-4653-ba55-5f855dd0fb88", "acdd72a7-3385-48ef-bd42-f606fba81ae7"], "Reader on the group, and Storage Queue Data Contributor on the one queue: nothing else")
        self.assertNotIn("c6a89b2d-59bc-44d0-9896-0f6e12d7b80a", code, "Storage Queue Data Message Sender is not in the condition of the deploy identity's right to assign roles: it would need a hand step by the owner")
        self.assertNotIn("Microsoft.EventHub", code)
        base = resources(text("environment/base/main.bicep"))
        self.assertEqual([name for name, (kind, _) in base.items() if kind == "Microsoft.Authorization/roleAssignments"], [], "the base gives no role at all")
        cases = resources(text("environment/cases/main.bicep"))
        self.assertFalse([name for name in cases if name.startswith("gateway")], "no role for a gateway: the owner ordered the undo of what Meternaut had added to his API Management instance")

    def test_the_role_that_the_template_gives_is_in_the_condition_of_the_deploy_identitys_right_as_the_bootstrap_page_lists_it(self):
        page = text("environment/BOOTSTRAP.md")
        self.assertIn("Storage Queue Data Contributor", page)
        self.assertIn("974c5e8b-45b9-4653-ba55-5f855dd0fb88", page, "the id of the role that the Operator is given on the queue is in the condition that the bootstrap page lists")

    def test_the_parameter_files_that_the_builder_writes_carry_no_principal_for_the_workflow(self):
        builder = text("tools/environment-params.py")
        self.assertNotIn("workflowPrincipalId", builder)
        self.assertNotIn("deployer", builder.lower().replace("deployment", ""))


class RetireWorkflow(unittest.TestCase):
    """The steps of the Hub workflow that used to read the Event Hubs namespace and retire the deploy identity's old right on the control hub: the control message goes through a Storage queue now, the
    namespace is deleted by the action retire-event-hubs (tools/retire-old.py, tested in test_retire_old.py), and nothing else of the workflow reads or names it."""

    READ_BACK = "Read the storage account back from Azure, which has no public network access and no key"

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}\n")]
        return block

    def script(self, title):
        body = self.step(title).split("        run: |\n", 1)[1]
        return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))

    def test_the_step_that_retired_the_deploy_identitys_right_on_the_control_hub_is_gone_and_no_step_reads_the_namespace_or_the_hub(self):
        code = re.sub(r"(?m)^\s*#.*$", "", self.text)
        for word in ("Retire the deploy identity's right", "Data Sender", "Data Receiver", "Microsoft.EventHub", "eventhubs.azure.net", "servicebus.windows.net", "EVENT_HUB_NAMESPACE", "event_hub_namespace",
                     "CONTROL_HUB", "cases_hub_name", "eventHubNamespaceName", "casesControl"):
            self.assertNotIn(word, code, word)
        self.assertNotIn("2b629674-e913-4c01-ae53-ef4638d8f975", self.text, "the id of Azure Event Hubs Data Sender is in no step")

    def test_the_storage_account_is_read_back_after_its_deploy_in_the_base_only_and_the_step_only_reads(self):
        block, script = self.step(self.READ_BACK), self.script(self.READ_BACK)
        self.assertIn("        if: inputs.action == 'base'\n", block)
        self.assertEqual(self.text.count(self.READ_BACK), 1, "the cases action does not change the storage account")
        self.assertEqual(self.names.index(self.READ_BACK), self.names.index("Deploy the base") + 1)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", block)
        self.assertIn('az rest --method get --url "https://management.azure.com${account}?api-version=2023-05-01"', script)
        for word in ("properties.publicNetworkAccess", "properties.allowSharedKeyAccess", "privateEndpointConnections", "privateLinkServiceConnectionState.status", '"Disabled"', "Approved"):
            self.assertIn(word, script)
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        self.assertNotIn("az role", script)
        self.assertIn("exit 1", script)

    def test_no_step_that_runs_for_a_check_action_puts_a_message_in_the_queue_or_reads_the_queue_from_the_runner(self):
        # the Operator does both, with its own identity: the runner can no longer reach the storage account once the action base has deployed its template
        for action in ("cases-run",):
            for block in self.steps:
                if not self.runs_for(block, action):
                    continue
                name = re.match(r"name: (.+)", block).group(1)
                if name == "What was done" or "run:" not in block:
                    continue
                code = "\n".join(line for line in block.split("run:", 1)[1].splitlines() if not line.strip().startswith("#"))
                for word in ("Microsoft.EventHub", "eventhubs.azure.net", "servicebus.windows.net", "queue.core.windows.net", "/messages", "az eventhubs", "az event", "az storage queue"):
                    self.assertNotIn(word, code, f"{action}: the step '{name}' names {word}")
                self.assertNotRegex(code, r"tools/cases-check\.py run\b", f"{action}: {name}")

    @staticmethod
    def runs_for(block, action):
        """Whether the step runs for this action: it has no condition, or its condition is true for the action (the conditions of this workflow name an action, always() and the outcome of a step)."""
        match = re.search(r"(?m)^        if: (.+)$", block.split("run:", 1)[0] if "run:" in block else block)
        if not match:
            return True
        expression = match.group(1)
        expression = re.sub(r"inputs\.action == '([a-z0-9-]+)'", lambda m: "True" if m.group(1) == action else "False", expression)
        # Which of the two steps that knock at the front door runs is decided by an output of the settings step, not by the action: for a question about the action alone either may run.
        expression = re.sub(r"steps\.params\.outputs\.door_in_operator (==|!=) 'true'", "True", expression)
        # Which plan kind the cases app is on is decided by the constant CASES_APP_PLAN, not by the action: for a question about the action alone either may run.
        expression = re.sub(r"steps\.params\.outputs\.cases_app_plan == '(?:Flex|Basic)'", "True", expression)
        # Whether the component's OpenTelemetry ingestion is on is decided by the constant GATEWAY_TELEMETRY, not by the action: the step that reads the provider before the base turns it on runs for base alone.
        expression = re.sub(r"steps\.params\.outputs\.gateway_telemetry == 'true'", "True", expression)
        expression = re.sub(r"steps\.\w+\.outcome != 'skipped'", "True", expression).replace("always()", "True").replace("&&", " and ").replace("||", " or ")
        assert re.fullmatch(r"[\sA-Za-z()]*", expression) and set(re.findall(r"[A-Za-z]+", expression)) <= {"True", "False", "and", "or"}, expression
        return bool(eval(expression, {"__builtins__": {}}))

    def test_the_evaluator_of_the_conditions_reads_the_conditions_that_the_workflow_has(self):
        conditions = sorted(set(re.findall(r"(?m)^        if: (.+)$", self.text)))
        self.assertGreaterEqual(len(conditions), 20)
        for condition in conditions:
            block = f"name: x\n        if: {condition}\n        run: |\n          true\n"
            self.assertIsInstance(self.runs_for(block, "base"), bool, condition)
        self.assertTrue(self.runs_for("name: x\n        run: |\n          true\n", "base"))
        self.assertTrue(self.runs_for("name: x\n        if: inputs.action == 'operator' || inputs.action == 'cases-run'\n        run: |\n          true\n", "cases-run"))
        self.assertTrue(self.runs_for("name: x\n        if: inputs.action == 'cases' && steps.params.outputs.cases_app_plan == 'Basic'\n        run: |\n          true\n", "cases"))
        self.assertFalse(self.runs_for("name: x\n        if: inputs.action == 'cases' && steps.params.outputs.cases_app_plan == 'Flex'\n        run: |\n          true\n", "cases-run"))
        self.assertFalse(self.runs_for("name: x\n        if: inputs.action == 'base'\n        run: |\n          true\n", "cases-run"))

    def test_the_what_if_says_what_changes_for_the_control_message_and_that_the_namespace_is_retired_by_an_action_of_its_own(self):
        block = self.step(PREVIEW_STEP)
        for words in ("The Event Hubs namespace and its private endpoint are not in this template any more, and an incremental deployment never removes what a template stops declaring, so they are not listed below: "
                      "the action retire-event-hubs deletes them, after cases-run has proved the queue path",
                      "The usage recording that used to live in this template is not listed either: the action retire-old deletes it.",
                      "What this adds for the control message: the queue cases-control in the base's storage account, and the app's settings for it",
                      "The app's old settings for the Event Hubs namespace are not in the template any more, so the deploy takes them off the app.",
                      "What the action retire-event-hubs would delete (it is read here, and nothing is deleted; an estate that never had an Event Hubs namespace shows nothing)"):
            self.assertIn(words, block, words)
        self.assertLess(block.index("The Event Hubs namespace and its private endpoint are not in this template any more"), block.index("--template environment/base/main.bicep"))
        self.assertLess(block.index("What this adds for the control message"), block.index("--template environment/cases/main.bicep"))
        self.assertLess(block.index("--template environment/base/main.bicep"), block.index("python3 tools/retire-old.py show --list event-hubs"))
        self.assertIn("queueServices/default/queues/$CASES_QUEUE?api-version=2023-05-01", block, "the preview of the Operator looks for the queue, which the action cases makes, and says so when it is not there")
        self.assertIn("The Operator cannot be previewed yet: its role goes on the control queue $CASES_QUEUE, which the action cases makes, and it is not there (or could not be read).", block)
        self.assertNotIn("Microsoft.EventHub", block)

    def test_the_description_of_the_action_says_what_base_and_cases_do_now_in_plain_words(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        for words in ("the storage account takes no public traffic (its public network access is Disabled and its private endpoints are the only way in, so from then on only the apps and the Operator reach its queue)",
                      "and after its deploy the action reads that back from Azure",
                      "a control queue (cases-control, in the base's storage account), a longer retention of the traces and the History workbook",
                      "and it needs the base and the AI Gateway first"):
            self.assertIn(words, description, words)
        self.assertLess(description.index("base: "), description.index("the storage account takes no public traffic"))
        self.assertLess(description.index(" cases: "), description.index("a control queue (cases-control, in the base's storage account)"))
        self.assertNotIn("retires the deploy identity's old right", description, "no step retires a right on a hub any more: the hub is deleted by retire-event-hubs")
        self.assertNotIn("an Event Hubs namespace, with private endpoints", description)

    def test_the_summaries_say_what_changed_for_the_storage_account_and_the_queue_and_what_a_person_does_when_the_retirement_stops(self):
        block = self.step("What was done")
        failed, finished = re.findall(r"(?m)^\s+base\) echo \"(.*?)\" ;;$", block)
        for words in ("Once the template has been deployed the storage account takes no public traffic, so this runner can no longer reach its queue: the Operator does.",
                      "If the lines above stop at the step that reads the storage account back, Azure did not show the account as private and without a key."):
            self.assertIn(words, failed, words)
        for words in ("a storage account (public network access Disabled, no Shared Key, its private endpoint connections Approved: read back from Azure)",
                      "This runner cannot reach the queue, and the Operator puts the control message in it.",
                      "the actions \\`retire-event-hubs\\` and \\`retire-old\\` delete what is left of them."):
            self.assertIn(words, finished, words)
        for stale in ("usage-control", "the gateway's two loggers", "two usage hubs", "an Event Hubs namespace (public network access Disabled"):
            self.assertNotIn(stale, failed + finished, stale)
        failed, finished = re.findall(r"(?m)^\s+cases\) echo \"(.*?)\" ;;$", block)
        self.assertNotIn("retires the deploy identity's right to send", failed)
        self.assertIn("the function app, the control queue, the longer retention of the traces and the workbook", failed)
        self.assertIn("The deploy identity holds no role on the control queue: the Operator puts the control message there.", finished)
        self.assertIn("a trigger on the control queue", finished)
        self.assertIn("the control queue in the base's storage account", finished)


class OperatorWorkflow(unittest.TestCase):
    """The actions operator and operator-probe of the deploy workflow: what runs for each, in what order, and what the probe is given."""

    HUBS = "The control queue that the Operator is given a role on is there"
    DEPLOY = "Deploy the Operator, its identity and the subnet of its container groups"
    PROVIDER = "The resource provider of Container Instances is registered in the subscription"
    WAIT = "Wait until the landing zone has put its route table on the Operator's subnet"
    PROBE = "Run the probe in the Operator"
    CLEANUP = "Delete any container group of the probe that is left"
    ORDER = [HUBS, DEPLOY, PROVIDER, WAIT, PROBE, CLEANUP]

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}\n")]
        return block

    def script(self, title):
        body = self.step(title).split("        run: |\n", 1)[1]
        return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))

    def test_the_two_actions_are_offered_and_described_in_plain_words(self):
        offered = re.findall(r"- (\S+)", re.search(r"options:\n((?:          - .+\n)+)", self.text).group(1))
        self.assertIn("operator", offered)
        self.assertIn("operator-probe", offered)
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        self.assertIn(" operator: the Operator, the executor that works inside the virtual network", description)
        self.assertIn("two roles (Reader on the project's group, and Storage Queue Data Contributor on the control queue cases-control, which the action cases makes, so it runs after it)", description)
        self.assertNotIn("one role (Reader", description)
        self.assertNotIn("usage-control", description.split(" operator: ")[1].split(" operator-probe: ")[0], "the usage recording's control hub is gone, and so is the Operator's role on it")
        self.assertIn(" operator-probe: run operator/probe.sh once in a short-lived container group", description)
        self.assertIn("deleted at the end whatever happens", description)
        self.assertIn("It needs operator first.", description)

    def test_each_step_runs_for_its_action_alone_and_in_order_between_the_settings_and_the_summary(self):
        positions = [self.names.index(name) for name in self.ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(self.names.index("Work out the settings"), positions[0])
        self.assertLess(positions[-1], self.names.index("What was done"))
        self.assertIn("if: inputs.action == 'operator'\n", self.step(self.HUBS))
        self.assertIn("if: inputs.action == 'operator'\n", self.step(self.DEPLOY))
        self.assertIn("if: inputs.action == 'operator-probe'\n", self.step(self.PROVIDER))
        self.assertIn("if: inputs.action == 'operator' || inputs.action == 'operator-probe'\n", self.step(self.WAIT))
        self.assertIn("if: inputs.action == 'operator-probe'\n", self.step(self.PROBE))
        self.assertIn("if: always() && inputs.action == 'operator-probe' && steps.probe.outcome != 'skipped'\n", self.step(self.CLEANUP),
                      "the second line behind the tool's own delete runs when the run was cancelled too, and only when the probe step started")
        self.assertIn("id: probe\n", self.step(self.PROBE))

    def test_the_deploy_makes_the_template_with_the_parameter_file_and_asks_for_the_client_id(self):
        block = self.step(self.DEPLOY)
        for word in ("--template environment/operator/main.bicep", '--parameters "$RUNNER_TEMP/operator.parameters.json"', '--name "operator-$GITHUB_RUN_ID"', "--output identityClientId"):
            self.assertIn(word, block)
        self.assertEqual(self.text.count("--template environment/operator/main.bicep"), 2, "the preview and the deploy, nothing else")
        self.assertIn("exit 1", block)
        for word in ("az role", "delete", "listKeys", "listSecrets", "--auth-mode key"):
            self.assertNotIn(word, block, word)

    def test_the_preview_waits_for_the_network_and_the_control_queue_and_the_settings_know_whether_the_subnet_is_there(self):
        preview = self.step(PREVIEW_STEP)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", preview)
        self.assertIn("CASES_QUEUE: ${{ steps.params.outputs.cases_queue_name }}", preview)
        self.assertNotIn("EVENT_HUB_NAMESPACE", preview)
        self.assertIn('queue=$(az rest --method get --url "https://management.azure.com/subscriptions/$ENV_SUBSCRIPTION_ID/resourceGroups/$ENV_RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/'
                      '$STORAGE_ACCOUNT/queueServices/default/queues/$CASES_QUEUE?api-version=2023-05-01" --query name --output tsv 2> /dev/null || true)', preview,
                      "one read of the queue, which no failure stops: a storage account that is not there is a queue that is not there")
        self.assertIn('if [ "$NETWORK_EXISTS" != true ]; then\n', preview)
        self.assertIn('elif [ "$queue" != "$CASES_QUEUE" ]; then\n', preview)
        self.assertIn('          else\n            python3 tools/az-deploy.py what-if --subscription "$ENV_SUBSCRIPTION_ID" --resource-group "$ENV_RESOURCE_GROUP" \\\n'
                      "              --template environment/operator/main.bicep", preview, "the preview of the template only when the network and the queue are there")
        self.assertLess(preview.index("The Operator cannot be previewed yet: its role goes on the control queue $CASES_QUEUE"), preview.index("--template environment/operator/main.bicep"))
        self.assertIn('echo "::group::The Operator, in the project\'s resource group (its identity, the subnet of its container groups and its two roles)"', preview)
        self.assertIn('if [ "$network" = true ]; then ops=$(exists "$vnet/subnets/snet-ops"); else ops=false; fi', self.text)
        self.assertIn('echo "ops_subnet_exists=$ops" >> "$GITHUB_OUTPUT"', self.text)
        self.assertIn("ENV_OPS_SUBNET_EXISTS: ${{ steps.network.outputs.ops_subnet_exists }}", self.step("Work out the settings"))

    def test_the_wait_takes_the_endpoint_subnet_as_the_yardstick_waits_twenty_minutes_after_the_deploy_and_only_says_it_before_a_probe(self):
        block = self.step(self.WAIT)
        script = self.script(self.WAIT)
        self.assertIn("timeout-minutes: 25", block)
        for word in ("table_of snet-pe", "table_of snet-ops", "attempts=40", 'if [ "$ACTION" != "operator" ]; then attempts=1; fi', "sleep 30", "properties.routeTable.id", "api-version=2025-05-01"):
            self.assertIn(word, script)
        self.assertEqual(len(re.findall(r"exit 1", script)), 1, "only the action operator stops when the table does not come")
        self.assertIn("::warning::snet-ops carries no route table", script)
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")

    def test_the_provider_is_read_and_never_registered_by_the_workflow(self):
        script = self.script(self.PROVIDER)
        self.assertIn("az provider show --namespace Microsoft.ContainerInstance --query registrationState", script)
        # No line of the workflow runs `az provider register`: a message may tell a person the command (the preflights of the AI security do, when a provider is missing), and nothing else mentions it.
        for line in self.text.splitlines():
            if "az provider register" in line:
                self.assertIn("::error::", line, "only an error message that tells a person what to run names the command")
                self.assertTrue(line.strip().startswith("echo "), line.strip()[:120])
        self.assertIn("::warning::", script, "a state that cannot be read is said and does not stop the run")

    def test_the_probe_is_given_a_pinned_image_the_script_the_names_the_size_the_lock_and_a_summary_and_no_secret_but_the_token_of_the_deploy_identity(self):
        block = self.step(self.PROBE)
        script = self.script(self.PROBE)
        self.assertRegex(self.text.split("    steps:")[0], r"(?m)^      OPERATOR_IMAGE: mcr\.microsoft\.com/azure-cli@sha256:[0-9a-f]{64}$", "one pin, in the environment of the job, for every step that runs something in the Operator")
        self.assertNotIn("OPERATOR_IMAGE:", block, "the probe uses the pin of the job")
        self.assertIn('--image "$OPERATOR_IMAGE"', script)
        self.assertNotIn("--allow-tag", script, "the workflow pins by digest")
        self.assertIn("python3 tools/operator-run.py run", script)
        for word in ("--script operator/probe.sh", '--secret-file "size-test=$RUNNER_TEMP/size-test"', '--secret-file "cases-requirements.txt=$lock"', '--summary "$GITHUB_STEP_SUMMARY"', '--subnet-id "$subnet_id"',
                     '--identity-id "$identity_id"', '--name "op-probe-$GITHUB_RUN_ID"', '"${dns[@]}"', "--timeout-seconds 1200", "timeout-minutes: 25"):
            self.assertTrue(word in script or word in block, word)
        self.assertRegex(script, r'size=400000\n\s+head -c "\$size" /dev/urandom')
        self.assertIn('identity_id=$(az resource list --resource-group "$ENV_RESOURCE_GROUP" --name id-meternaut-operator --query "[0].id" --output tsv || true)', script)
        self.assertIn('client=$(az rest --method get --url "https://management.azure.com${identity_id}?api-version=2023-01-31" --query properties.clientId --output tsv || true)', script,
                      "the client id is read from the identity resource")
        for word in ("az identity", "Microsoft.ManagedIdentity"):
            self.assertNotIn(word, script, f"{word}: the workflow reads no identity with az identity and names no identity resource type outside the path that removes the retired runner identity")
        self.assertIn('--env "PROBE_SIZE_BYTES=$size"', script)
        for name in ("OPERATOR_CLIENT_ID", "OPERATOR_GROUP", "OPERATOR_SUBSCRIPTION", "PROBE_NAMES", "PROBE_PRIVATE_NAMES", "PROBE_URLS", "PROBE_SCM_HOSTS", "PROBE_LOCK_BYTES", "PROBE_DEPLOY_CLIENT_ID",
                     "PROBE_DEPLOY_TENANT_ID"):
            self.assertIn(f'--env "{name}=', script)
        for host in ("mcr.microsoft.com", "management.azure.com", "login.microsoftonline.com", "api.github.com", "codeload.github.com", "github.com", "pipelines.actions.githubusercontent.com",
                     "objects.githubusercontent.com", "pypi.org", "files.pythonhosted.org", "api.applicationinsights.io", "api.loganalytics.io"):
            self.assertIn(f"https://{host}/", script, host)
        for word in ("GITHUB_TOKEN", "get-access-token", "az account", "--auth-mode", "listKeys"):
            self.assertNotIn(word, block, word)
        self.assertEqual(re.findall(r"secrets\.(\w+)", block), ["AZURE_CLIENT_ID", "AZURE_TENANT_ID"], "the two ids of the deploy identity, which the other steps read from the same secrets, and no other secret")
        self.assertIn("DEPLOY_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}", block)
        self.assertIn("DEPLOY_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}", block)
        self.assertEqual(re.findall(r"--secure-env [A-Za-z_=]+", block), ["--secure-env AZURE_FEDERATED_TOKEN"], "one secure value, and it is named, never given: the tool takes its value from the environment")

    def test_the_token_of_the_deploy_identity_is_asked_for_right_before_the_group_is_made_masked_at_once_and_goes_nowhere_but_the_environment_of_the_one_call_of_the_tool(self):
        block, script = self.step(self.PROBE), self.script(self.PROBE)
        order = ('identity_id=$(az resource list', 'head -c "$size" /dev/urandom', "lock_bytes=$(wc -c", "curl_status=0", 'echo "::add-mask::$token"', 'AZURE_FEDERATED_TOKEN="$token" python3 tools/operator-run.py run')
        positions = [script.index(word) for word in order]
        self.assertEqual(positions, sorted(positions), "everything else is ready before the token is asked for: it is valid for five minutes")
        self.assertIn("id-token: write", self.text.split("jobs:")[0], "the job may ask for the token")
        self.assertIn('"${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=api://AzureADTokenExchange"', script, "the audience that the federated credential trusts, the one that azure/login asks for")
        self.assertRegex(script, r"printf 'header = \"Authorization: Bearer %s\"\\n' \"\$ACTIONS_ID_TOKEN_REQUEST_TOKEN\" \| curl [^\n]*--config - ", "the bearer of the request is on standard input")
        self.assertNotRegex(script, r"curl[^\n]*(?:-H |--header)", "and on no command line")
        self.assertEqual([line.strip() for line in script.splitlines() if "ACTIONS_ID_TOKEN_REQUEST_TOKEN" in line][0:1], ['if [ -z "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ] || [ -z "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]; then'])
        self.assertEqual(sum("ACTIONS_ID_TOKEN_REQUEST_TOKEN" in line for line in script.splitlines()), 2, "the bearer of the request is read twice: tested for, and sent")
        for variable in ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
            self.assertEqual(len(re.findall(rf"(?m)^[^#\n]*{variable}", self.text)), 4, f"{variable} is read in the two steps that ask for the token, each in two lines: the probe's, and the publish of the cases app")
        lines = [line.strip() for line in script.splitlines() if "$token" in line]
        self.assertEqual(lines[:3], ['if [ -z "$token" ]; then', 'echo "::add-mask::$token"', 'if [ -n "$token" ]; then'])
        self.assertEqual(len(lines), 4, "the token is tested for, masked, tested for, and handed over: nothing else mentions it")
        self.assertRegex(lines[3], r'^AZURE_FEDERATED_TOKEN="\$token" python3 tools/operator-run\.py run --resource-group ')
        self.assertEqual([line.strip() for line in script.splitlines() if "$answer" in line], ["token=$(sed -n 's/.*\"value\" *: *\"\\([^\"]*\\)\".*/\\1/p' <<< \"$answer\")"], "the answer is read once, for the token")
        self.assertIn("unset answer", script)
        self.assertLess(script.index('echo "::add-mask::$token"'), script.index('AZURE_FEDERATED_TOKEN="$token" python3'))
        self.assertEqual(re.findall(r"--secure-env [A-Za-z_=]+", script), ["--secure-env AZURE_FEDERATED_TOKEN"])
        for value in re.findall(r'--env "[A-Z_]+=([^"]*)"', script):
            self.assertNotRegex(value, r"(?i)token", "no --env value is the token")
        self.assertIn('--env "PROBE_TOKEN_NOTE=$note"', script, "without a token the probe is told why, in plain words")
        for word in ("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_STATE", "GITHUB_PATH", "set -x", "xtrace", " tee ", "::set-output", "::save-state"):
            self.assertNotIn(word, block, f"{word}: the token is written nowhere")
        for word in ("az login", "azure/login"):
            self.assertNotIn(word, script, f"{word}: the runner does not sign in again for the probe: the container does")
        self.assertRegex(script, r'secure=\(\)\n\s+note_args=\(\)\n\s+if \[ -n "\$token" \]; then\n\s+secure=\(--secure-env AZURE_FEDERATED_TOKEN\)\n\s+else\n')
        self.assertIn('"${note_args[@]}" "${secure[@]}"', script, "both lists are empty arrays when there is nothing to add, and the call stays one call")

    def test_the_lock_file_of_the_cases_app_is_sent_whole_with_its_size_and_every_file_of_the_group_stays_below_the_limit_of_the_tool(self):
        script = self.script(self.PROBE)
        self.assertIn("lock=src/case-functions/requirements.txt\n", script)
        self.assertIn("lock_bytes=$(wc -c < \"$lock\" | tr -d ' ')\n", script)
        self.assertIn('--secret-file "cases-requirements.txt=$lock"', script)
        self.assertIn('--env "PROBE_LOCK_BYTES=$lock_bytes"', script)
        self.assertIn('--requirement "$source_dir/requirements.txt"', text("tools/build-function-app.sh"), "the lock that the build script builds from is the file that the probe is sent")
        self.assertIn("requirements.txt", text("operator/probe.sh"))
        sizes = {"size-test": 400_000, "cases-requirements.txt": (ROOT / "src/case-functions/requirements.txt").stat().st_size, "probe.sh": (ROOT / "operator/probe.sh").stat().st_size}
        cap = int(re.search(r"(?m)^MAX_FILE_BYTES = ([0-9_]+)", text("tools/operator-run.py")).group(1).replace("_", ""))
        self.assertEqual(cap, 480_000)
        self.assertLessEqual(sum(sizes.values()), cap, "the cap of tools/operator-run.py for the files of one group: the probe's own request is the largest one that is known to have been taken (466,104 bytes on "
                                                       "2026-11-06), so it has to stay within the cap, or the tool would refuse the probe")
        self.assertLess(sizes["cases-requirements.txt"], 400_000, "far below the size that the probe found a secret volume takes whole")
        self.assertLess(sizes["probe.sh"], 100_000)

    def test_the_probe_is_given_the_deployment_site_of_the_cases_app_and_the_names_of_the_app_and_its_site_must_be_private(self):
        block, script = self.step(self.PROBE), self.script(self.PROBE)
        self.assertNotIn("USAGE_APP", block + script, "the usage app was removed on 2026-11-07")
        self.assertIn("CASES_APP: ${{ steps.params.outputs.cases_function_app_name }}", block)
        self.assertIn('scm_hosts="$CASES_APP.scm.azurewebsites.net"', script)
        self.assertIn('--env "PROBE_SCM_HOSTS=$scm_hosts"', script)
        self.assertIn('--env "PROBE_NAMES=$private_names"', script)
        self.assertIn('--env "PROBE_PRIVATE_NAMES=$private_names $scm_hosts"', script)
        names = re.search(r'(?m)^\s*private_names="(.+)"$', script).group(1).split()
        self.assertEqual(names[-1:], ["$CASES_APP.azurewebsites.net"], "the app has a private endpoint, so its name must resolve to a private address")
        self.assertEqual(names, ["$STORAGE_ACCOUNT.queue.core.windows.net", "$STORAGE_ACCOUNT.blob.core.windows.net", "$FOUNDRY_ACCOUNT.services.ai.azure.com", "$CASES_APP.azurewebsites.net"],
                         "the storage account's queue and blob names, the Foundry resource and the app: no namespace, no Cosmos DB account and no old model account any more")
        self.assertIn("https://$CASES_APP.azurewebsites.net/healthz", script, "the console's health address needs no sign-in")

    def test_the_digest_is_the_one_that_the_decision_record_names_and_nothing_in_the_workflow_makes_or_deletes_a_container_group_itself(self):
        digest = re.search(r"OPERATOR_IMAGE: (mcr\.microsoft\.com/azure-cli@sha256:[0-9a-f]{64})", self.text).group(1)
        self.assertIn(digest, text("docs/proposals/07-private-by-default.md"))
        self.assertEqual(len(re.findall(r"OPERATOR_IMAGE: ", self.text)), 1, "the pin is made once")
        self.assertEqual(len(re.findall(r'--image "\$OPERATOR_IMAGE"', self.text)), 11, "and used by the probe, by the check that starts a Watch, by the health check of the cases app, by the measurement of the web page's answering time, by the check of the web page's front door, by the check of the AI Gateway, by the publish and by the four checks of the AI security")
        self.assertNotIn("az container", self.text, "the tool makes, reads and deletes the group")

    def test_the_cleanup_deletes_only_groups_of_the_probe_through_the_tool_and_a_failure_is_a_warning(self):
        script = self.script(self.CLEANUP)
        self.assertIn('python3 tools/operator-run.py cleanup --resource-group "$ENV_RESOURCE_GROUP" --prefix op-probe- --older-than-minutes 0', script)
        self.assertIn("::warning::", script)
        self.assertNotIn("delete", script.replace("deletes", ""), "the tool deletes, not a command of the step")
        self.assertIn("--name \"op-probe-$GITHUB_RUN_ID\"", self.script(self.PROBE), "the prefix of the cleanup is the start of the name that the probe gives its group")

    def test_the_control_queue_is_read_before_the_deploy_and_a_missing_one_says_which_action_makes_it_and_stops_before_anything_is_changed(self):
        block, script = self.step(self.HUBS), self.script(self.HUBS)
        self.assertIn("STORAGE_ACCOUNT: ${{ steps.params.outputs.storage_account_name }}", block)
        self.assertIn("CASES_QUEUE: ${{ steps.params.outputs.cases_queue_name }}", block)
        self.assertNotIn("EVENT_HUB_NAMESPACE", block)
        for word in ('url="https://management.azure.com/subscriptions/$ENV_SUBSCRIPTION_ID/resourceGroups/$ENV_RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT/queueServices/default/queues/$CASES_QUEUE?api-version=2023-05-01"',
                     '--query name --output tsv', 'if [ "$queue" != "$CASES_QUEUE" ]', "Run cases first (after base)", "the actions base and cases run before operator", "Nothing was changed."):
            self.assertIn(word, script, word)
        self.assertNotIn("usage-control", script, "the usage recording's hub was removed on 2026-11-07")
        self.assertNotIn("Microsoft.EventHub", script)
        self.assertEqual(len(re.findall(r"exit 1", script)), 2, "a queue that is missing, and a read that fails for another reason than NotFound")
        self.assertIn("NotFound|\\b404\\b", script, "a queue that is not there is no queue, and any other answer stops the run")
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        for word in ("az-deploy", "az role", "az container", "listKeys", "listSecrets"):
            self.assertNotIn(word, script, word)

    def test_the_template_is_compiled_linted_and_its_file_is_checked_in_both_workflows(self):
        for source in (self.text, text(".github/workflows/checks.yml")):
            self.assertIn("environment/operator/main.bicep", source)
            self.assertIn('--label operator', source)
            self.assertIn('operator.json"', source)
        self.assertIn("environment/foundry/main.bicep environment/cases/main.bicep environment/operator/main.bicep", text(".github/workflows/checks.yml"), "CI compiles and lints it")
        self.assertNotIn("az bicep lint", self.text, "the Hub compiles it for the check of its file and leaves the lint to CI, which ran it for exactly this commit")

    def test_both_actions_have_a_line_in_the_summary_for_success_and_for_failure(self):
        block = self.step("What was done")
        for action in ("operator", "operator-probe"):
            self.assertEqual(len(re.findall(rf"(?m)^                {action}\) echo ", block)), 2, action)


class OperatorChecksWorkflow(unittest.TestCase):
    """The action cases-run: the control message is put in the queue, and the telemetry is read, by the check tool inside the Operator. The runner does neither. (The action recording-check, which did the same for the usage
    recording's copy jobs, was removed on 2026-11-07.)"""

    FIND = "Find the Operator, which runs the check from inside the network"
    CASES_LIST = "Before the Watch is started, the cases app lists its four functions"
    CASES = "Start one Watch and read its History"
    CLEANUP = "Delete any container group of the checks that is left"
    SAMPLE_INSIGHTS = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-meternaut-dev/providers/Microsoft.Insights/components/appi-meternaut"

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in self.steps]

    def step(self, title):
        (block,) = [b for b in self.steps if b.startswith(f"name: {title}\n")]
        return block

    def script(self, title):
        body = self.step(title).split("        run: |\n", 1)[1]
        return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))

    def test_the_action_finds_the_operator_lists_the_functions_from_the_runner_then_runs_its_check_in_the_operator_and_the_cleanup_always_runs(self):
        for action, listing, check in (("cases-run", self.CASES_LIST, self.CASES),):
            positions = [self.names.index(name) for name in (self.FIND, listing, check, self.CLEANUP)]
            self.assertEqual(positions, sorted(positions), action)
            self.assertLess(self.names.index("Work out the settings"), positions[0], "after the settings, whose outputs the steps use")
            self.assertLess(positions[-1], self.names.index("What was done"))
            self.assertIn(f"if: inputs.action == '{action}'\n", self.step(listing))
            self.assertIn(f"if: inputs.action == '{action}'\n", self.step(check))
        self.assertIn("if: inputs.action == 'cases-run' || inputs.action == 'page-latency'\n", self.step(self.FIND))
        self.assertIn("id: operator\n", self.step(self.FIND))
        self.assertIn("id: watch\n", self.step(self.CASES))
        self.assertNotIn("copy_jobs", self.text, "the copy jobs of the usage recording were removed on 2026-11-07")
        self.assertIn("if: always() && steps.watch.outcome != 'skipped'\n", self.step(self.CLEANUP),
                      "the second line behind the tool's own delete runs when the run was cancelled too, and only when the check step started")
        self.assertLess(self.names.index(self.CASES), self.names.index(self.CLEANUP), "after the check, so that it runs for it")

    def test_the_runner_puts_no_message_in_the_queue_and_reads_no_telemetry_it_only_lists_the_functions_and_the_tools_run_in_the_operator(self):
        code = "\n".join(line for block in self.steps if "run:" in block for line in block.split("run:", 1)[1].splitlines() if not line.strip().startswith("#"))
        self.assertNotRegex(code, r"tools/(check-helpers|cases-check)\.py run\b", "no `run` of a check tool on the runner")
        self.assertNotIn("recording-check", code)
        self.assertEqual(sorted(re.findall(r"python3 tools/cases-check\.py (\w+)", code)), ["functions", "functions", "whoami"], "the object id of the identity, and the list of the functions twice")
        for word in ("eventhubs.azure.net", "servicebus.windows.net", "storage.azure.com", "/messages?"):
            self.assertNotIn(word, code, f"{word}: the runner takes no token for Storage and posts nothing to a queue")
        self.assertNotRegex(code, r"https?://[^\s\"']*queue\.core\.windows\.net", "the probe is given the name of the queue to see that it resolves to a private address, and nothing is sent to it from the runner")
        self.assertEqual(self.text.count("uses: azure/login@"), 12, "the check action added no sign-in: the runner makes the container group with the credential of the first one (the twelve are the first, the two retirements', the one of cases before its publish, the two of cases around the health check in the Operator, the Foundry read-back's, the two of aigateway, one before the gateway's deploy and one before its limits, which follow the subnet's deploy and a wait for the route table: aigateway-check has none, the one before the read-back of the AI security, the one before the read-back of the telemetry exporter, and the one before the read-back of Power Platform's subnet and policy)")

    def test_the_check_runs_the_generic_script_with_its_tool_and_the_arguments_that_the_runner_used_before_and_the_times_are_ordered(self):
        expected = {self.CASES: {"tool": "cases-check", "files": ["cases-check.py", "check-helpers.py"], "args": "run --storage-account $STORAGE_ACCOUNT --insights $insights --minutes 30 --counts-only", "seconds": 2400,
                                 "minutes": 50}}
        for title, want in expected.items():
            block, script = self.step(title), self.script(title)
            self.assertIn('python3 tools/operator-run.py run --resource-group "$ENV_RESOURCE_GROUP" --name "op-check-$GITHUB_RUN_ID"', script, title)
            for word in ('--subnet-id "$OPERATOR_SUBNET_ID"', '--identity-id "$OPERATOR_IDENTITY_ID"', '--image "$OPERATOR_IMAGE"', "--script operator/run-tool.sh", '"${dns[@]}"',
                         '--summary "$GITHUB_STEP_SUMMARY"', '--env "GITHUB_ACTIONS=true"', '--env "OPERATOR_CLIENT_ID=$OPERATOR_CLIENT_ID"', '--env "OPERATOR_SUBSCRIPTION=$ENV_SUBSCRIPTION_ID"',
                         "for server in ${ENV_DNS_SERVERS//,/ }; do dns+=(--dns-server \"$server\"); done", f"--timeout-seconds {want['seconds']}"):
                self.assertIn(word, script, f"{title}: {word}")
            self.assertEqual(re.findall(r'--secret-file "([^"=]+)=tools/([^"]+)"', script), [(name, name) for name in want["files"]], title)
            self.assertEqual(len(re.findall(r"--secret-file", script)), len(want["files"]), title)
            self.assertIn(f'--env "TOOL_NAME={want["tool"]}"', script)
            self.assertIn(f'--env "TOOL_ARGS={want["args"]}"', script)
            self.assertIn(f"        timeout-minutes: {want['minutes']}\n", block)
            waits = int(re.search(r"--minutes (\d+)", want["args"]).group(1))
            self.assertLess(waits * 60, want["seconds"], f"{title}: the group is given longer than the tool waits for the telemetry")
            self.assertLess(want["seconds"], want["minutes"] * 60, f"{title}: and the step is given longer than the group, which the tool deletes at its own limit")
            for word in ("--secure-env", "--allow-tag", "get-access-token", "listSecrets", "az account", "--auth-mode", "secrets."):
                self.assertNotIn(word, block, f"{title}: {word}")

    def test_the_arguments_of_the_runner_before_the_change_are_still_the_ones_that_the_tool_takes(self):
        # cases-check.py run --storage-account --insights --minutes 30: the storage account replaces the namespace, and nothing else of the arguments changed; --counts-only (a public log) was added
        cases = text("tools/cases-check.py")
        for option in ("--storage-account", "--insights", "--minutes", "--summary", "--counts-only"):
            self.assertIn(f'run.add_argument("{option}"', cases)
        self.assertNotIn("--namespace", cases)
        self.assertNotIn("--no-send", cases, "the tool keeps its behaviour: it puts its message in the queue itself")
        self.assertNotIn("--request-id", cases)

    def test_the_environment_of_the_check_step_holds_the_names_and_the_outputs_that_it_uses_and_nothing_secret(self):
        for title in (self.CASES,):
            block = self.step(title)
            env = dict(re.findall(r"(?m)^          (\w+): (.+)$", block.split("        env:\n")[1].split("        run: |")[0]))
            self.assertEqual(env, {"STORAGE_ACCOUNT": "${{ steps.params.outputs.storage_account_name }}", "INSIGHTS_NAME": "${{ steps.params.outputs.appinsights_name }}",
                                   "OPERATOR_IDENTITY_ID": "${{ steps.operator.outputs.identity_id }}", "OPERATOR_CLIENT_ID": "${{ steps.operator.outputs.client_id }}",
                                   "OPERATOR_SUBNET_ID": "${{ steps.operator.outputs.subnet_id }}"}, title)

    def test_the_files_that_are_sent_exist_hold_what_the_tool_loads_from_its_own_folder_and_the_arguments_fit_the_script_s_strict_pattern(self):
        pattern = re.search(r"argument_characters='([^']+)'", text("operator/run-tool.sh")).group(1)
        name_pattern = re.search(r"tool_name='([^']+)'", text("operator/run-tool.sh")).group(1)
        for title in (self.CASES,):
            script = self.script(title)
            sent = re.findall(r'--secret-file "([^"=]+)=tools/([^"]+)"', script)
            for name, path in sent:
                self.assertTrue((ROOT / "tools" / path).is_file(), path)
            names = {name for name, _ in sent}
            tool = re.search(r"TOOL_NAME=([a-z-]+)", script).group(1)
            self.assertRegex(tool, name_pattern)
            self.assertIn(f"{tool}.py", names)
            for loaded in re.findall(r'with_name\("([^"]+)"\)', text(f"tools/{tool}.py")):
                self.assertIn(loaded, names, f"{tool}.py loads {loaded} from its own folder, so it goes into the secret volume too")
            args = re.search(r'TOOL_ARGS=([^"]+)"', script).group(1).replace("$STORAGE_ACCOUNT", "stmeternautfn0a1b2c3d").replace("$insights", self.SAMPLE_INSIGHTS)
            self.assertNotIn("$", args)
            self.assertRegex(args, pattern)
            self.assertLessEqual(len(args), 600)
            self.assertRegex(args.split()[0], r"^[a-z][a-z-]{0,19}$")
            size = sum((ROOT / "tools" / path).stat().st_size for _, path in sent) + (ROOT / "operator" / "run-tool.sh").stat().st_size
            self.assertLess(size, 300_000, "far below the 400,000 bytes that the probe found a secret volume takes whole")

    def test_the_container_is_told_it_is_in_a_github_actions_run_only_because_only_a_run_of_this_workflow_makes_it(self):
        # operator-run.py makes the group only for a run of the Hub (tools/hubguard.py: a GitHub runner): the container is told GITHUB_ACTIONS=true.
        self.assertIn("raise Problem(f\"this command makes and deletes resources in Azure, and only a run of the Hub may do that (AGENTS.md rule 18): {not_the_hub}\", 2)", text("tools/operator-run.py"))
        self.assertIn("not_the_hub = guard.refusal()", text("tools/operator-run.py"))
        for title in (self.CASES,):
            block = self.step(title)
            self.assertEqual(block.count('--env "GITHUB_ACTIONS=true"'), 1)
            comment = " ".join(line.strip()[2:] for line in block.splitlines() if line.strip().startswith("# "))
            self.assertIn("the container is told that it is in a GitHub Actions run, which it is", comment)
            self.assertIn("AGENTS.md rule 18", comment)

    def test_the_find_step_names_the_operator_the_way_the_probe_does_says_to_run_operator_first_and_changes_nothing(self):
        script = self.script(self.FIND)
        probe = self.script("Run the probe in the Operator")
        for line in ('identity_id=$(az resource list --resource-group "$ENV_RESOURCE_GROUP" --name id-meternaut-operator --query "[0].id" --output tsv || true)',
                     'client=$(az rest --method get --url "https://management.azure.com${identity_id}?api-version=2023-01-31" --query properties.clientId --output tsv || true)'):
            self.assertIn(line, script)
            self.assertIn(line, probe, "the same lookup as the probe's")
        self.assertIn('subnet_id="/subscriptions/$ENV_SUBSCRIPTION_ID/resourceGroups/$ENV_RESOURCE_GROUP/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"', script)
        self.assertIn('subnet_id="$scope/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"', probe)
        self.assertEqual(len(re.findall(r"exit 1", script)), 3, "an identity that is not there, a subnet that is not there, a subnet that cannot be read")
        for words in ("The identity id-meternaut-operator is not there.", "The subnet snet-ops is not there.", "so run operator first (the order is base, cases, operator). Nothing was changed.",
                      "The subnet snet-ops could not be read: $found", "NotFound|\\b404\\b"):
            self.assertIn(words, script, words)
        self.assertEqual(script.count("run operator first"), 2)
        for word in ('echo "identity_id=$identity_id"', 'echo "client_id=$client"', 'echo "subnet_id=$subnet_id"'):
            self.assertIn(word, script)
        self.assertIn('>> "$GITHUB_OUTPUT"', script)
        self.assertNotRegex(script, r"--method (put|patch|post|delete)")
        for word in ("az container", "az role", "az identity", "Microsoft.ManagedIdentity", "az login", "az-deploy", "az account", "listKeys", "listSecrets"):
            self.assertNotIn(word, script, word)

    def test_the_cleanup_deletes_only_groups_of_the_checks_through_the_tool_and_a_failure_is_a_warning_and_it_cannot_take_a_group_of_the_probe(self):
        script = self.script(self.CLEANUP)
        self.assertIn('python3 tools/operator-run.py cleanup --resource-group "$ENV_RESOURCE_GROUP" --prefix op-check- --older-than-minutes 0', script)
        self.assertIn("::warning::", script)
        self.assertNotIn("delete", script.replace("deletes", ""), "the tool deletes, not a command of the step")
        for title in (self.CASES,):
            self.assertIn('--name "op-check-$GITHUB_RUN_ID"', self.script(title), "the prefix of the cleanup is the start of the name that the check gives its group")
        self.assertIn('--name "op-probe-$GITHUB_RUN_ID"', self.script("Run the probe in the Operator"))
        self.assertFalse("op-probe-".startswith("op-check-") or "op-check-".startswith("op-probe-"), "neither cleanup can take the groups of the other")

    def test_the_action_says_in_the_description_that_it_runs_in_the_operator_and_needs_operator_first(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', self.text).group(1)
        self.assertNotIn("recording-check", description, "the action was removed on 2026-11-07, with the usage recording")
        self.assertIn("cases-run: start one Watch through the control queue (the Operator puts one message in it) and read its History from the telemetry, both by the Operator from inside the network: it needs operator first. page-latency:", description)

    def test_the_summaries_say_where_the_work_was_done_what_to_do_when_the_operator_or_its_role_is_missing_and_what_the_operator_now_holds(self):
        block = self.step("What was done")
        for action in ("cases-run",):
            failed, finished = re.findall(rf"(?m)^\s+{action}\) echo \"(.*?)\" ;;$", block)
            for words in ("The Operator put it there and read the telemetry from inside the network, in a container group named \\`op-check-$GITHUB_RUN_ID\\` that the last step of the run deletes if the tool could not.",
                          "A message that the Operator is not there means that \\`operator\\` has to be run first.", "A 401 or 403 when the message is put in the queue means that the Operator's role on the control queue is missing "
                          "(\\`operator\\` assigns it) or has not applied yet (a role takes up to ten minutes). A 404 means that the queue is not there (\\`cases\\` makes it).", f"Running \\`{action}\\` again is safe."):
                self.assertIn(words, failed, f"{action}: {words}")
            self.assertIn("The Operator, from inside the network, put the control message in the queue and read the telemetry, with its own identity and no key; this runner put nothing in the queue and read no telemetry.", finished)
        failed, finished = re.findall(r"(?m)^\s+operator\) echo \"(.*?)\" ;;$", block)
        for words in ("the Storage Queue Data Contributor role on the control queue", "If the lines above say that the control queue is not there, nothing was changed: run \\`base\\` and \\`cases\\` first.",
                      "Storage Queue Data Contributor is listed already."):
            self.assertIn(words, failed, words)
        for words in ("two roles for that identity: Reader on the group, and Storage Queue Data Contributor on the control queue \\`cases-control\\`, and nothing else.",
                      "A new role takes up to ten minutes to apply, so wait before \\`cases-run\\`", "which runs its check tool in the Operator."):
            self.assertIn(words, finished, words)


class OperatorHandStep(unittest.TestCase):
    """The hand steps of the Operator in environment/BOOTSTRAP.md: one more role in the condition of the deploy identity (Reader), and the resource provider."""

    READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"

    def setUp(self):
        self.page = text("environment/BOOTSTRAP.md")
        self.section = self.page.split("## Changed on 2026-11-06: the Operator")[1].split("\n## ")[0]
        (self.script,) = re.findall(r"```powershell\n(.*?)\n```", self.section, re.S)

    def test_the_section_follows_the_foundry_section_which_keeps_its_one_block_and_comes_before_the_last_one(self):
        foundry = self.page.index("## Changed on 2026-11-06: the Foundry resource of the agents")
        operator = self.page.index("## Changed on 2026-11-06: the Operator")
        self.assertLess(foundry, operator)
        self.assertLess(operator, self.page.index("\n## After it"))
        self.assertEqual(len(re.findall(r"```powershell", self.page.split("## Changed on 2026-11-06: the Foundry resource of the agents")[1].split("\n## ")[0])), 1)

    def test_the_role_is_the_one_that_the_template_gives_and_it_is_added_in_place_with_one_update_and_nothing_is_deleted_or_made(self):
        self.assertIn(f"var readerRoleId = '{self.READER}'", text("environment/operator/main.bicep"))
        self.assertIn(f"$reader = '{self.READER}'", self.script)
        self.assertEqual(len(re.findall(r"^az role assignment update ", self.script, re.M)), 1, "one write")
        self.assertEqual(sorted(set(re.findall(r"az role assignment (\w+)", self.script))), ["list", "update"])
        for word in ("role assignment delete", "role assignment create", "--ids", "restore", "Restore"):
            self.assertNotIn(word, self.script, word)
        for call in re.findall(r"az role assignment (?:list|update)[^\n]*", self.script):
            self.assertIn("--subscription $devSub", call, call)

    def test_it_reads_before_it_writes_shows_the_difference_asks_and_reads_back_after(self):
        order = [self.script.index(word) for word in ("Get-Assignments 'length(@)'", "$old = $text | ConvertFrom-Json", "$shape = {", "Write-Host \"Role ids now:", "Read-Host 'Change the condition as shown? Type yes'",
                                                      "az role assignment update ", "$new = $text | ConvertFrom-Json", "Write-Host \"Read back:")]
        self.assertEqual(order, sorted(order))
        self.assertIn("-ne 'yes') { throw 'Stopped. Nothing was changed.' }", self.script)
        self.assertGreaterEqual(self.script.count("if ($LASTEXITCODE -ne 0) { throw"), 5)
        self.assertTrue(self.script.isascii(), "commands that are copied into a console hold plain characters only")

    def test_the_text_says_what_the_deploy_identity_already_covers_what_it_does_not_and_the_two_hand_steps(self):
        for words in ("Microsoft.ContainerInstance/containerGroups/*", "Microsoft.Network/virtualNetworks/subnets/join/action", "Microsoft.ManagedIdentity/userAssignedIdentities/assign/action",
                      "lists eight roles and Reader is not one of them", "does not cover registering a resource provider", "**Hand step 1: a resource provider.**", "**Hand step 2: one more role in the condition",
                      "az provider register --namespace Microsoft.ContainerInstance", "the first `operator-probe` is the test", "Nothing is written until the person types `yes`"):
            self.assertIn(words, self.section, words)


if __name__ == "__main__":
    unittest.main()
