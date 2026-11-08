"""The template of the Teams bot (environment/teams/main.bicep) and the app that it makes: what is public and why, that nothing holds a key, that the bot's identity holds no role, and that the
settings of the app are the ones that cases/teams.py reads. The template is read as text, so no test needs Azure or the Bicep tool."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "case-functions"))

from cases import teams  # noqa: E402

TEMPLATE = ROOT / "environment" / "teams" / "main.bicep"
ROLES = {
    "b7e6dc6d-f1e8-4753-8033-0f276bb0955b": "Storage Blob Data Owner",
    "974c5e8b-45b9-4653-ba55-5f855dd0fb88": "Storage Queue Data Contributor",
    "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3": "Storage Table Data Contributor",
    "3913510d-42f4-4e42-8a64-420c390055eb": "Monitoring Metrics Publisher",
}
GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def source() -> str:
    return TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n")


def code() -> str:
    return re.sub(r"//.*", "", source())


def resource(name: str) -> str:
    """The text of one top-level resource of the template."""
    found = re.search(rf"^resource {name} '[^']+' (?:existing )?= (?:\[for [^\n]*?: )?\{{\n(.*?)^\}}\]?$", source(), re.M | re.S)
    assert found, f"no resource {name}"
    return found.group(1)


def app_settings() -> dict[str, str]:
    block = re.search(r"appSettings: \[\n(.*?)^      \]", source(), re.M | re.S)
    assert block
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"\{ name: '([A-Za-z0-9_]+)', value: (.+?) \}$", block.group(1), re.M)}


def parameter(name: str) -> str:
    found = re.search(rf"^param {name} (\w+)(?: = (.+))?$", source(), re.M)
    assert found, f"no parameter {name}"
    return (found.group(2) or "").strip()


class TheParameters(unittest.TestCase):
    def test_the_defaults_are_the_cheap_and_the_narrow_ones(self):
        self.assertEqual(parameter("maximumInstanceCount"), "2")
        self.assertEqual(parameter("alwaysReadyInstances"), "0", "the app scales to zero: an instance that is kept warm is billed all month")
        self.assertEqual(parameter("instanceMemoryMB"), "512", "the smallest instance: the bot does a few table calls and one signature check for a call")
        self.assertEqual(parameter("restrictInboundToBotService"), "false", "not proved for Teams: off until a tap on a card has shown that Teams still gets through")
        self.assertEqual(parameter("planTtlHours"), "72", "the same time as the cases app's requests")

    def test_the_memory_of_an_instance_is_one_of_the_three_that_the_plan_has(self):
        allowed = re.search(r"@allowed\(\[\n(.*?)\]\)\nparam instanceMemoryMB", source(), re.S)
        self.assertEqual(sorted(int(n) for n in re.findall(r"\d+", allowed.group(1))), [512, 2048, 4096])

    def test_what_the_workflow_passes_is_what_the_template_takes(self):
        # tools/teams-params.py writes these, and the template has no other parameter without a default.
        without_default = {m.group(1) for m in re.finditer(r"^param (\w+) \w+$", source(), re.M)}
        written = {"owner", "storageAccountName", "botAppName", "botName", "consoleHost", "consolePeople"}
        self.assertEqual(without_default, written)


class TheBotResource(unittest.TestCase):
    def test_it_is_the_azure_bot_of_the_free_tier_with_the_identity_of_the_bot_and_no_key(self):
        body = resource("bot")
        for line in ("kind: 'azurebot'", "name: 'F0'", "msaAppType: 'UserAssignedMSI'", "msaAppMSIResourceId: botIdentity.id", "msaAppId: botIdentity.properties.clientId",
                     "msaAppTenantId: tenant().tenantId", "disableLocalAuth: true", "publicNetworkAccess: 'Enabled'", "location: 'global'"):
            self.assertIn(line, body, line)
        self.assertIn("endpoint: 'https://${botApp.properties.defaultHostName}/api/messages'", body, "Teams is told to call the one route of the app")
        self.assertNotIn("MultiTenant", code(), "a multi-tenant bot cannot be made any more, and the app type is not a secret")
        self.assertNotIn("SingleTenant", code(), "one app type, and one way to get the token for the Connector: the platform's identity endpoint (cases/connector.py)")

    def test_the_teams_channel_is_made_with_its_name_only_and_the_terms_are_accepted_by_a_person(self):
        body = resource("teamsChannel")
        self.assertIn("parent: bot", body)
        self.assertIn("name: 'MsTeamsChannel'", body)
        self.assertIn("channelName: 'MsTeamsChannel'", body)
        self.assertNotIn("acceptedTerms", body)
        self.assertNotIn("enableCalling: true", body, "the bot makes no call")

    def test_the_identity_of_the_bot_holds_no_role_and_no_other_resource_uses_its_principal(self):
        self.assertNotIn("botIdentity.properties.principalId", re.sub(r"^output .*$", "", code(), flags=re.M), "no role assignment names the bot's own identity")
        for name in re.findall(r"^resource (\w+) 'Microsoft\.Authorization/roleAssignments@", source(), re.M):
            self.assertNotIn("botIdentity", resource(name), name)


class TheApp(unittest.TestCase):
    def test_it_is_a_flex_consumption_app_with_two_identities_and_a_public_front_door(self):
        plan, app = resource("plan"), resource("botApp")
        self.assertIn("name: 'FC1'", plan)
        self.assertIn("tier: 'FlexConsumption'", plan)
        self.assertIn("type: 'SystemAssigned, UserAssigned'", app)
        self.assertIn("'${botIdentity.id}': {}", app)
        for line in ("httpsOnly: true", "publicNetworkAccess: 'Enabled'", "minTlsVersion: '1.2'", "runtime: {\n        name: 'python'", "version: '3.13'",
                     "type: 'SystemAssignedIdentity'", "kind: 'functionapp,linux'"):
            self.assertIn(line, app, line)

    def test_it_runs_in_the_function_subnet_that_the_model_side_made_and_makes_no_network_object(self):
        app = resource("botApp")
        self.assertIn("virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, functionSubnetName)", app)
        self.assertIn("var functionSubnetName = 'snet-func'", code())
        self.assertIn("var virtualNetworkName = 'vnet-${workload}'", code())
        self.assertNotIn("Microsoft.Network/virtualNetworks@", code(), "a subnet is made once and then left alone: this template reads it by its name and never makes or changes it")
        for word in ("privateEndpoints", "privateDnsZones", "subnets@", "routeTables", "networkSecurityGroups"):
            self.assertNotIn(word, code(), word)

    def test_the_host_storage_and_the_code_package_use_the_identity_and_nothing_in_it_is_a_key(self):
        app = resource("botApp")
        settings = app_settings()
        self.assertEqual(settings["AzureWebJobsStorage__credential"], "'managedidentity'")
        for name in ("AzureWebJobsStorage__blobServiceUri", "AzureWebJobsStorage__queueServiceUri", "AzureWebJobsStorage__tableServiceUri"):
            self.assertIn(name, settings)
        self.assertNotIn("AzureWebJobsStorage", set(settings), "a connection string is a key")
        self.assertNotIn("AZURE_CLIENT_ID", settings, "the app's token for the tables is the system-assigned identity's: a client id here would make it the bot's")
        self.assertEqual(settings["APPLICATIONINSIGHTS_AUTHENTICATION_STRING"], "'Authorization=AAD'")
        self.assertIn("authentication: {\n            type: 'SystemAssignedIdentity'", app)
        body = code()
        for word in ("listKeys", "listSecrets", "primaryKey", "secondaryKey", "accountKey", "AccountKey", "SharedAccessSignature", "sasToken", "clientSecret", "password", "msaAppPassword"):
            self.assertNotIn(word, body, word)
        self.assertEqual(re.findall(r"connectionString|ConnectionString", body), ["ConnectionString"], "only the telemetry's connection string, which names the component and authenticates nothing")

    def test_the_deployment_endpoint_takes_no_password(self):
        body = resource("noBasicAuthForDeployment")
        self.assertIn("parent: botApp", body)
        self.assertIn("name: 'scm'", body)
        self.assertIn("allow: false", body)

    def test_the_settings_are_the_ones_that_the_bot_reads(self):
        settings = app_settings()
        for name in (teams.APP_ID, teams.TENANT_ID, "STORE_ACCOUNT_NAME", "CHANGE_SCOPES", "CONSOLE_HOST", "CONSOLE_PEOPLE", "PLAN_TTL_HOURS"):
            self.assertIn(name, settings, name)
        self.assertEqual(settings[teams.APP_ID], "botIdentity.properties.clientId", "the app id of the bot is the client id of its identity: the audience of every token that Teams sends")
        self.assertEqual(settings[teams.TENANT_ID], "tenant().tenantId")
        self.assertEqual(settings["CONSOLE_HOST"], "consoleHost")
        # With real values in the place of the expressions the bot's own loader takes them, which is the whole of what the app is told.
        env = {teams.APP_ID: "0f6a4c2e-7b1d-4e35-9a58-3c2d1b0e9f47", teams.TENANT_ID: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "STORE_ACCOUNT_NAME": "stexample",
               "CHANGE_SCOPES": "11111111-2222-3333-4444-555555555555/rg-example", "CONSOLE_HOST": "meternaut.example.com", "PLAN_TTL_HOURS": "72"}
        loaded = teams.load(env)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.loop.console_host, "meternaut.example.com")

    def test_the_two_functions_of_the_app_are_the_only_public_surface(self):
        entry = (ROOT / "src" / "case-functions" / "teams_function_app.py").read_text(encoding="utf-8")
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', entry)), ["teams-messages", "teams-offer"])
        self.assertEqual(entry.count("@app.route("), 1)
        self.assertIn('route="api/messages", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS', entry)
        self.assertNotIn("AuthLevel.FUNCTION", entry, "a function key is a secret")


class TheRoles(unittest.TestCase):
    def test_the_app_holds_the_four_roles_of_an_identity_based_host_and_the_tables_and_nothing_else(self):
        used = set(re.findall(rf"var \w+RoleId = '({GUID})'", code()))
        self.assertEqual(used, set(ROLES), "no role that writes anywhere but the shared storage account and the telemetry, and none that reads the estate")
        assignments = re.findall(r"^resource (\w+) 'Microsoft\.Authorization/roleAssignments@", source(), re.M)
        self.assertGreaterEqual(len(assignments), 5)
        for name in assignments:
            body = resource(name)
            self.assertIn("principalId: botApp.identity.principalId", body, "the roles are the system-assigned identity's")
            self.assertIn("principalType: 'ServicePrincipal'", body)
            self.assertNotRegex(body, r"scope: resourceGroup\(\)|scope: subscription\(\)|scope: tenant\(\)", "each role is on one resource, never on the group")

    def test_the_template_makes_no_subscription_or_group_scope_assignment_and_no_custom_role(self):
        self.assertNotIn("roleDefinitions@", code(), "no custom role")
        self.assertIn("targetScope = 'resourceGroup'", code())


class TheInboundRestriction(unittest.TestCase):
    def test_the_narrowing_is_a_service_tag_rule_with_deny_for_the_rest_and_only_when_it_is_asked_for(self):
        app = resource("botApp")
        self.assertIn("ipSecurityRestrictionsDefaultAction: restrictInboundToBotService ? 'Deny' : 'Allow'", app)
        rule = re.search(r"ipSecurityRestrictions: restrictInboundToBotService \? \[\n(.*?)\n      \] : \[\]", app, re.S)
        self.assertIsNotNone(rule, "an empty list when it is off")
        for line in ("action: 'Allow'", "tag: 'ServiceTag'", "ipAddress: 'AzureBotService'", "priority: 100"):
            self.assertIn(line, rule.group(1), line)
        self.assertEqual(rule.group(1).count("name:"), 1, "one rule, nothing for an address")

    def test_the_deployment_endpoint_stays_open_to_the_workflow_that_publishes_through_it(self):
        app = resource("botApp")
        self.assertIn("scmIpSecurityRestrictionsUseMain: false", app)
        self.assertIn("scmIpSecurityRestrictionsDefaultAction: 'Allow'", app)

    def test_the_header_says_that_it_is_not_proved_for_teams_and_where_the_facts_were_read(self):
        flat = re.sub(r"\n// ?", " ", source())
        for phrase in ("not proved for Teams", "AzureBotService", "allow-listing inbound addresses is not supported", "read 2026-11-08"):
            self.assertIn(phrase, flat, phrase)


class TheSwitchAndTheGuard(unittest.TestCase):
    def test_the_header_says_that_only_the_owners_written_request_deploys_it(self):
        flat = re.sub(r"\n// ?", " ", source())
        for phrase in ("public_teams_bot_requested", "TEAMS_BOT_ENABLED", "AGENTS.md rule 15 (c)", "the action `teams`"):
            self.assertIn(phrase, flat, phrase)

    def test_the_outputs_are_what_the_package_tool_and_the_hub_read(self):
        outputs = set(re.findall(r"^output (\w+) ", source(), re.M))
        self.assertTrue({"botAppName", "botClientId", "messagingEndpoint", "botName"} <= outputs, outputs)


if __name__ == "__main__":
    unittest.main()
