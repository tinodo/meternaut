import importlib.util
import io
import ipaddress
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "environment-params.py"
spec = importlib.util.spec_from_file_location("environment_params", TOOL)
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

MODELS = ROOT / "environment" / "models.json"
CONTRACT_FILE = ROOT / "environment" / "contract.json"
POLICY_FILE = ROOT / "environment" / "gateway" / "contract-policy.xml"
BICEP = (ROOT / "environment" / "main.bicep").read_text(encoding="utf-8")
LOGGER = (ROOT / "environment" / "gateway" / "logger.bicep").read_text(encoding="utf-8")
CONTRACT_BICEP = (ROOT / "environment" / "gateway" / "contract.bicep").read_text(encoding="utf-8")
SETTINGS = {
    "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555",
    "ENV_RESOURCE_GROUP": "rg-example",
    "ENV_LOCATION": "swedencentral",
    "ENV_VNET_PREFIX": "10.53.0.0/24",
    "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27",
    "ENV_DNS_SERVERS": "10.20.0.4",
    "ENV_OWNER": "owner@example.com",
    "ENV_BUDGET_AMOUNT": "25",
    "ENV_ALERT_EMAILS": "owner@example.com",
    "ENV_BUDGET_START": "2026-11-01",
    "GATEWAY_RESOURCE_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg-gateway/providers/Microsoft.ApiManagement/service/example-apim",
    "GATEWAY_APPINSIGHTS_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg-gateway/providers/microsoft.insights/components/example-insights",
    "GATEWAY_PRINCIPAL_ID": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
}
READER = "12345678-1234-1234-1234-123456789012"
RECORDING = (ROOT / "environment" / "recording" / "main.bicep").read_text(encoding="utf-8")


def run(env, *extra, models=MODELS):
    with tempfile.TemporaryDirectory() as tmp:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ep.main(["build", "--models", str(models), "--out-dir", tmp, *extra], environ=env)
        files = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in Path(tmp).glob("*.json")}
    return code, out.getvalue(), err.getvalue(), files


def values(document):
    return {k: v["value"] for k, v in document["parameters"].items()}


def bicep_params(text):
    declared = {}
    for match in re.finditer(r"^param (\w+) (\w+)( = .+)?$", text, re.M):
        declared[match.group(1)] = (match.group(2), match.group(3) is not None)
    return declared


class Build(unittest.TestCase):
    def test_good_settings_give_four_files_and_the_outputs(self):
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(set(files), {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json", "recording.parameters.json", "foundry.parameters.json", "operator.parameters.json", "planted.parameters.json",
                                      "cases.parameters.json"})
        env = values(files["environment.parameters.json"])
        self.assertEqual(env["vnetAddressPrefix"], "10.53.0.0/24")
        self.assertEqual(env["peSubnetPrefix"], "10.53.0.0/27")
        self.assertEqual(env["dnsServers"], ["10.20.0.4"])
        self.assertEqual(env["gatewayPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(env["budgetStartDate"], "2026-11-01")
        self.assertEqual([m["name"] for m in env["models"]], [m["name"] for m in json.loads(MODELS.read_text())])
        lines = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual(lines["account_name"], env["accountName"])
        self.assertEqual(lines["private_endpoint"], "pe-" + env["accountName"])
        self.assertEqual(lines["endpoint"], f"https://{env['accountName']}.cognitiveservices.azure.com")
        self.assertEqual(lines["gateway_name"], "example-apim")
        self.assertEqual(lines["gateway_resource_group"], "rg-gateway")
        self.assertEqual(lines["principal_known"], "true")

    def test_the_account_name_is_a_valid_host_name_and_the_same_on_every_run(self):
        names = {values(run(SETTINGS)[3]["environment.parameters.json"])["accountName"] for _ in range(3)}
        self.assertEqual(len(names), 1)
        name = names.pop()
        self.assertRegex(name, r"^aif-meternaut-[0-9a-f]{8}$")

    def test_the_name_differs_per_subscription_and_group_and_ignores_case(self):
        base = ep.account_name(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-a")
        self.assertNotEqual(base, ep.account_name(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-b"))
        self.assertNotEqual(base, ep.account_name("99999999-2222-3333-4444-555555555555", "rg-a"))
        self.assertEqual(base, ep.account_name(SETTINGS["ENV_SUBSCRIPTION_ID"].upper(), "RG-A"))

    def test_the_environment_file_matches_the_parameters_of_the_template(self):
        declared = bicep_params(BICEP)
        given = run(SETTINGS)[3]["environment.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)
        self.assertEqual(bicep_params(BICEP)["restoreAccount"], ("bool", True))
        self.assertNotIn("restoreAccount", given)

    def test_the_logger_file_matches_the_logger_template(self):
        declared = bicep_params(LOGGER)
        given = run(SETTINGS)[3]["logger.parameters.json"]["parameters"]
        self.assertEqual(set(given), set(declared))
        self.assertEqual(values(run(SETTINGS)[3]["logger.parameters.json"]), {
            "apimName": "example-apim", "appInsightsName": "example-insights", "appInsightsResourceGroup": "rg-gateway"})

    def test_the_names_the_workflow_removes_are_the_ones_the_template_gives(self):
        lines = dict(line.split("=", 1) for line in run(SETTINGS)[1].splitlines())
        self.assertIn("name: 'pe-${accountName}'", BICEP)
        self.assertIn("param workload string = 'meternaut'", BICEP)
        self.assertIn("name: 'vnet-${workload}'", BICEP)
        self.assertIn("name: 'nsg-${workload}-pe'", BICEP)
        self.assertEqual((lines["vnet_name"], lines["nsg_name"]), ("vnet-meternaut", "nsg-meternaut-pe"))

    def test_the_budget_keeps_the_start_date_it_was_given(self):
        self.assertNotIn("utcNow", BICEP)
        self.assertIn("startDate: budgetStartDate", BICEP)
        again = run({**SETTINGS, "ENV_BUDGET_START": "2027-02-01"})[3]["environment.parameters.json"]
        self.assertEqual(values(again)["budgetStartDate"], "2027-02-01")


class Recording(unittest.TestCase):
    """The parameter file of the usage recording, and the names that it gives to services whose names are host names."""

    def files(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual((code, err), (0, ""))
        return files, dict(line.split("=", 1) for line in out.splitlines())

    def test_the_file_matches_the_parameters_of_the_template(self):
        declared = bicep_params(RECORDING)
        files, _ = self.files(RECORDING_READER_IDS=READER)
        given = files["recording.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)

    def test_the_gateway_and_the_readers_reach_the_template_and_the_workflow_does_not(self):
        files, outputs = self.files(RECORDING_READER_IDS=f"{READER.upper()}")
        recording = values(files["recording.parameters.json"])
        self.assertEqual(recording["gatewayPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(recording["gatewayAppInsightsSubscriptionId"], "66666666-7777-8888-9999-000000000000")
        self.assertEqual((recording["gatewayAppInsightsResourceGroup"], recording["gatewayAppInsightsName"]), ("rg-gateway", "example-insights"))
        self.assertNotIn("workflowPrincipalId", recording, "no template gives the workflow's identity a role on an event hub: the Operator sends the control events")
        self.assertEqual(recording["dataReaderPrincipalIds"], [READER])
        self.assertEqual(recording["functionAppName"], outputs["function_app_name"])
        for old in ("logicAppName", "dataContributorPrincipalIds"):
            self.assertNotIn(old, recording)
        self.assertEqual((recording["location"], recording["owner"]), ("swedencentral", "owner@example.com"))

    def test_no_reader_is_a_valid_choice_and_the_workflow_is_never_one(self):
        files, _ = self.files()
        self.assertEqual(values(files["recording.parameters.json"])["dataReaderPrincipalIds"], [])
        files, _ = self.files(RECORDING_READER_IDS="  ")
        self.assertEqual(values(files["recording.parameters.json"])["dataReaderPrincipalIds"], [])

    def test_the_names_are_host_names_inside_their_limits_and_the_same_on_every_run(self):
        _, first = self.files()
        _, second = self.files()
        for key, pattern, longest in (("storage_account_name", r"^[a-z0-9]{3,24}$", 24), ("event_hub_namespace", r"^[A-Za-z][A-Za-z0-9-]{4,49}$", 50),
                                      ("cosmos_account_name", r"^[a-z0-9][a-z0-9-]{2,43}$", 44), ("function_app_name", r"^[A-Za-z0-9][A-Za-z0-9-]{1,59}$", 60)):
            self.assertRegex(first[key], pattern, key)
            self.assertLessEqual(len(first[key]), longest, key)
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(len({first[k] for k in ("storage_account_name", "event_hub_namespace", "cosmos_account_name", "function_app_name")}), 4)
        self.assertNotIn("logic_app_name", first)

    def test_the_names_differ_per_subscription_and_group_and_ignore_case(self):
        base = ep.recording_names(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-a")
        self.assertNotEqual(base, ep.recording_names(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-b"))
        self.assertNotEqual(base, ep.recording_names("99999999-2222-3333-4444-555555555555", "rg-a"))
        self.assertEqual(base, ep.recording_names(SETTINGS["ENV_SUBSCRIPTION_ID"].upper(), "RG-A"))
        self.assertTrue(ep.account_name(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-a").endswith(base["function_app_name"][-8:]))

    def test_the_key_based_version_is_removed_by_the_four_names_it_had_and_by_no_other(self):
        _, outputs = self.files()
        token = ep.digest(SETTINGS["ENV_SUBSCRIPTION_ID"], SETTINGS["ENV_RESOURCE_GROUP"])
        legacy = {key: value for key, value in outputs.items() if key.startswith("legacy_")}
        # The names that the first version was deployed with (they are in the changelog): the first storage account is not the new one.
        self.assertEqual(legacy, {"legacy_logic_app_name": f"logic-meternaut-usage-{token}", "legacy_plan_name": "asp-meternaut-usage",
                                  "legacy_connection_name": "azuremonitorlogs", "legacy_storage_account_name": f"stmeternaut{token}"})
        self.assertNotEqual(legacy["legacy_storage_account_name"], outputs["storage_account_name"])
        self.assertNotIn(legacy["legacy_logic_app_name"], RECORDING)
        self.assertNotIn(legacy["legacy_plan_name"], RECORDING)
        self.assertNotIn("azuremonitorlogs", RECORDING)

    def test_the_function_app_has_a_subnet_of_its_own_beside_the_endpoint_subnet(self):
        files, outputs = self.files()
        env = values(files["environment.parameters.json"])
        self.assertEqual((env["peSubnetPrefix"], env["funcSubnetPrefix"]), ("10.53.0.0/27", "10.53.0.32/27"))
        self.assertEqual(outputs["function_subnet_prefix"], "10.53.0.32/27")
        # whichever /27 the endpoints use, the function app gets another one
        files, _ = self.files(ENV_PE_SUBNET_PREFIX="10.53.0.32/27")
        self.assertEqual(values(files["environment.parameters.json"])["funcSubnetPrefix"], "10.53.0.0/27")
        # no room: a /28 network cannot hold a /27
        code, out, err, files = run({**SETTINGS, "ENV_VNET_PREFIX": "10.53.0.0/28", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/28"})
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("ENV_VNET_PREFIX", err)

    def test_the_model_side_file_says_whether_the_virtual_network_is_there_already_and_says_no_when_nobody_has_looked(self):
        self.assertIs(values(self.files()[0]["environment.parameters.json"])["networkExists"], False)
        for given, expected in (("", False), ("false", False), ("true", True), (" TRUE ", True)):
            files, _ = self.files(ENV_NETWORK_EXISTS=given)
            self.assertIs(values(files["environment.parameters.json"])["networkExists"], expected, given)
        for refused in ("yes", "1"):
            code, out, err, files = run({**SETTINGS, "ENV_NETWORK_EXISTS": refused})
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("ENV_NETWORK_EXISTS is true or false", err)

    def test_the_basic_plan_of_the_first_cases_has_a_third_subnet_that_overlaps_neither_of_the_other_two(self):
        files, outputs = self.files()
        env = values(files["environment.parameters.json"])
        self.assertEqual(env["webSubnetPrefix"], "10.53.0.224/27", "the last /27: the first subnet of the Basic plan took the first free one and was replaced")
        self.assertEqual(outputs["web_subnet_prefix"], "10.53.0.224/27")
        taken = [ipaddress.ip_network(env[name]) for name in ("peSubnetPrefix", "funcSubnetPrefix")]
        self.assertFalse(any(ipaddress.ip_network(env["webSubnetPrefix"]).overlaps(other) for other in taken))
        # whichever /27 the other two use, the plan gets the last free one
        files, _ = self.files(ENV_PE_SUBNET_PREFIX="10.53.0.64/27")
        env = values(files["environment.parameters.json"])
        self.assertEqual((env["funcSubnetPrefix"], env["webSubnetPrefix"]), ("10.53.0.0/27", "10.53.0.224/27"))
        files, _ = self.files(ENV_PE_SUBNET_PREFIX="10.53.0.224/27")
        env = values(files["environment.parameters.json"])
        self.assertEqual((env["funcSubnetPrefix"], env["webSubnetPrefix"]), ("10.53.0.0/27", "10.53.0.192/27"))
        # a /26 holds two /27: no room for a third
        code, out, err, files = run({**SETTINGS, "ENV_VNET_PREFIX": "10.53.0.0/26", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27"})
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("Basic plan", err)

    def test_the_endpoint_subnet_holds_the_nine_private_endpoints(self):
        # nine endpoints (the usage recording's five, the model account's, the Foundry resource's and one for each of the two function apps) and the five addresses that Azure keeps: a /29 has
        # eight addresses and cannot hold them, and a /28 has sixteen
        code, out, err, files = run({**SETTINGS, "ENV_PE_SUBNET_PREFIX": "10.53.0.0/29"})
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("ENV_PE_SUBNET_PREFIX", err)
        self.assertIn("at least a /28", err)
        self.assertIn("each of the two function apps one", err)
        self.assertEqual(run({**SETTINGS, "ENV_PE_SUBNET_PREFIX": "10.53.0.0/28"})[0], 0)

    def test_the_private_endpoints_and_their_zones_are_the_ones_the_template_makes(self):
        _, outputs = self.files()
        pairs = [pair.split(":") for pair in outputs["recording_endpoints"].split(",")]
        self.assertEqual(len(pairs), 6)
        storage, cosmos, hubs, app = outputs["storage_account_name"], outputs["cosmos_account_name"], outputs["event_hub_namespace"], outputs["function_app_name"]
        self.assertEqual(pairs, [[f"pe-{storage}-blob", "privatelink.blob.core.windows.net"], [f"pe-{storage}-queue", "privatelink.queue.core.windows.net"],
                                 [f"pe-{storage}-table", "privatelink.table.core.windows.net"], [f"pe-{cosmos}", "privatelink.documents.azure.com"],
                                 [f"pe-{hubs}", "privatelink.servicebus.windows.net"], [f"pe-{app}", "privatelink.azurewebsites.net"]])
        for line in ("name: 'pe-${storageAccountName}-${service}'", "name: 'pe-${cosmosAccountName}'", "name: 'pe-${eventHubNamespaceName}'", "name: 'pe-${functionAppName}'"):
            self.assertIn(line, RECORDING)
        self.assertEqual(outputs["appinsights_name"], "appi-meternaut")
        self.assertNotIn("usage_identity_name", outputs, "the usage app's own system-assigned identity has no name, and the workflow does not look for the user-assigned one that it replaced")
        self.assertNotIn("id-${workload}-usage", RECORDING, "the template no longer makes the identity that the app's own system-assigned one replaced")
        self.assertIn("name: 'appi-${workload}'", RECORDING)

    def test_the_readers_must_be_object_ids(self):
        for changes in ({"RECORDING_READER_IDS": "not-an-id"}, {"RECORDING_READER_IDS": f"{READER},"},
                        {"RECORDING_READER_IDS": f"{READER},{READER.upper()}"}, {"RECORDING_READER_IDS": ",".join([READER[:-1] + str(i) for i in range(6)])}):
            code, out, err, files = run({**SETTINGS, **changes})
            self.assertEqual((code, out, files), (2, "", {}), changes)
            self.assertIn("RECORDING_", err)
            self.assertNotIn("not-an-id", err)

    def test_the_identity_of_the_workflow_is_no_setting_of_the_builder_and_no_file_carries_it(self):
        # It used to get the right to send to the control hub of each of the two apps (the parameter workflowPrincipalId of both templates); the Operator sends the control events now, and the workflow
        # reads its own object id only to find and delete the assignment that it held (the steps that retire it).
        self.assertNotIn("RECORDING_DEPLOYER_ID", SETTINGS)
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("RECORDING_DEPLOYER_ID", TOOL.read_text(encoding="utf-8"))
        for name, document in files.items():
            self.assertNotIn("workflowPrincipalId", document["parameters"], name)
        code, out, err, files = run({**SETTINGS, "RECORDING_DEPLOYER_ID": "me"})
        self.assertEqual((code, err), (0, ""), "a leftover setting is not read, so a wrong value cannot stop a run")
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "contract.json"
            contract.write_text(CONTRACT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            code, out, err, files = run(SETTINGS, "--contract", str(contract), "--contract-policy", str(POLICY_FILE))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("cases.parameters.json", files)
        for name, document in files.items():
            self.assertNotIn("workflowPrincipalId", document["parameters"], name)


class KitSettings(unittest.TestCase):
    """The choices made for the Citadel gateway-upgrade module are held here, with the reason for each."""

    def setUp(self):
        self.kit = values(run(SETTINGS)[3]["kit.parameters.json"])

    def test_no_prompt_and_no_answer_is_logged(self):
        llm = self.kit["azureMonitorLogSettings"]["largeLanguageModel"]
        self.assertEqual((llm["requests"]["messages"], llm["responses"]["messages"]), ("none", "none"))
        for side in ("frontend", "backend"):
            for direction in ("request", "response"):
                self.assertEqual(self.kit["azureMonitorLogSettings"][side][direction]["body"]["bytes"], 0)
        self.assertEqual(self.kit["appInsightsLogSettings"]["body"]["bytes"], 0)

    def test_the_personal_data_flag_stays_on_because_a_fragment_needs_it(self):
        # the module creates the ai-foundry-compatibility fragment only with this flag, and the inference APIs include it
        self.assertTrue(self.kit["enablePIIAnonymization"])

    def test_the_named_values_are_never_empty_and_name_the_account(self):
        endpoint = values(run(SETTINGS)[3]["environment.parameters.json"])["accountName"]
        for key in ("aiLanguageServiceUrl", "contentSafetyServiceUrl"):
            self.assertEqual(self.kit[key], f"https://{endpoint}.cognitiveservices.azure.com/")

    def test_only_the_two_inference_apis_are_deployed(self):
        self.assertTrue(self.kit["updateUniversalLLMApi"] and self.kit["updateAzureOpenAIApi"])
        for key in ("updateUnifiedAiApi", "updateReleaseVersionApi", "updateOpenAIRealtimeApi",
                    "updateRedisCache", "enableRedisCache", "updateEmbeddingsBackend", "enableEmbeddingsBackend"):
            self.assertIs(self.kit[key], False, key)

    def test_the_unified_api_is_not_deployed_but_its_fragments_are_because_the_two_apis_include_one(self):
        # The service refused the policies of both inference APIs, in a real run, because set-response-headers did not exist:
        # the module creates it only with enableUnifiedAiApi, and both policies include it.
        self.assertIs(self.kit["updateUnifiedAiApi"], False)
        self.assertIs(self.kit["enableUnifiedAiApi"], True)

    def test_callers_use_the_contracts_key_and_no_second_azure_monitor_logger_is_made(self):
        self.assertIs(self.kit["enableJwtAuth"], False)
        self.assertIs(self.kit["deployAzureMonitorLogger"], False)
        self.assertNotIn("logAnalyticsWorkspaceResourceId", self.kit)

    def test_the_service_level_logging_is_replaced_on_purpose(self):
        self.assertIs(self.kit["updateAppInsightsDiagnostics"], True)

    def test_the_backend_holds_exactly_the_models_that_are_deployed(self):
        (backend,) = self.kit["llmBackendConfig"]
        deployed = values(run(SETTINGS)[3]["environment.parameters.json"])["models"]
        self.assertEqual([(m["name"], m["modelVersion"], m["sku"], m["capacity"]) for m in backend["supportedModels"]],
                         [(m["name"], m["version"], m["sku"], m["capacity"]) for m in deployed])
        self.assertEqual((backend["backendType"], backend["authType"]), ("ai-foundry", "managed-identity"))
        self.assertTrue(backend["endpoint"].startswith("https://aif-meternaut-") and backend["endpoint"].endswith(".cognitiveservices.azure.com/"))

    def test_the_gateway_identity_is_the_one_the_template_grants_a_role(self):
        self.assertEqual(self.kit["managedIdentityName"], ep.IDENTITY_NAME)
        self.assertEqual(self.kit["apimServiceName"], "example-apim")

    def test_nothing_secret_is_in_the_file(self):
        text = json.dumps(run(SETTINGS)[3]["kit.parameters.json"]).lower()
        for word in ("key", "secret", "password", "connectionstring"):
            self.assertNotIn(word, text.replace("subscriptionkey", ""), word)


class Preview(unittest.TestCase):
    def test_a_run_before_the_identity_exists_needs_the_preview_flag(self):
        env = {**SETTINGS, "GATEWAY_PRINCIPAL_ID": ""}
        code, out, err, files = run(env)
        self.assertEqual(code, 2)
        self.assertIn("GATEWAY_PRINCIPAL_ID", err)
        self.assertEqual(files, {})
        code, out, err, files = run(env, "--preview")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("principal_known=false", out)
        self.assertEqual(values(files["environment.parameters.json"])["gatewayPrincipalId"], ep.PLACEHOLDER)

    def test_the_usage_recording_reads_the_placeholder_as_no_gateway_identity(self):
        # The recording makes the two roles of the gateway identity only for an identity that is known (the owner ordered the undo of what Meternaut added to his API Management
        # instance on 2026-11-07, so the identity may be gone): the template compares with the same all-zero id that the builder writes while the identity is not known.
        code, out, err, files = run({**SETTINGS, "GATEWAY_PRINCIPAL_ID": ""}, "--preview")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(values(files["recording.parameters.json"])["gatewayPrincipalId"], ep.PLACEHOLDER)
        template = (TOOL.parents[1] / "environment" / "recording" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn(f"var noGatewayIdentity = '{ep.PLACEHOLDER}'", template)
        self.assertEqual(ep.PLACEHOLDER, "00000000-0000-0000-0000-000000000000")


class EventHubLoggers(unittest.TestCase):
    """The file for the two Event Hub loggers, and the choice that makes the module create the two fragments that use them."""

    CLIENT = "BBBBBBBB-1111-2222-3333-CCCCCCCCCCCC"

    def test_without_the_identitys_client_id_no_file_is_written(self):
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("eventhub-loggers.parameters.json", files)

    def test_with_it_the_file_names_the_namespace_the_two_hubs_and_the_identity(self):
        code, out, err, files = run({**SETTINGS, "GATEWAY_CLIENT_ID": self.CLIENT})
        self.assertEqual((code, err), (0, ""))
        lines = dict(line.split("=", 1) for line in out.splitlines())
        loggers = values(files["eventhub-loggers.parameters.json"])
        self.assertEqual(loggers, {
            "apimName": "example-apim",
            "eventHubHost": lines["event_hub_namespace"] + ".servicebus.windows.net",
            "usageHubName": "ai-usage",
            "piiHubName": "pii-usage",
            "identityClientId": self.CLIENT.lower(),
        })

    def test_the_preview_uses_a_placeholder_and_says_nothing_secret(self):
        code, out, err, files = run({**SETTINGS, "GATEWAY_PRINCIPAL_ID": ""}, "--preview")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(values(files["eventhub-loggers.parameters.json"])["identityClientId"], ep.PLACEHOLDER)

    def test_the_file_matches_the_parameters_of_the_template_and_the_hubs_are_the_ones_the_recording_makes(self):
        template = (ROOT / "environment" / "gateway" / "eventhub-loggers.bicep").read_text(encoding="utf-8")
        declared = bicep_params(template)
        files = run({**SETTINGS, "GATEWAY_CLIENT_ID": self.CLIENT})[3]
        given = files["eventhub-loggers.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        self.assertTrue({name for name, (_, has_default) in declared.items() if not has_default} <= set(given))
        self.assertIn("var usageHubName = 'ai-usage'", RECORDING)
        self.assertIn("var piiHubName = 'pii-usage'", RECORDING)
        self.assertEqual((values(files["eventhub-loggers.parameters.json"])["usageHubName"], values(files["eventhub-loggers.parameters.json"])["piiHubName"]), ("ai-usage", "pii-usage"))
        self.assertEqual(values(files["eventhub-loggers.parameters.json"])["eventHubHost"], values(files["recording.parameters.json"])["eventHubNamespaceName"] + ".servicebus.windows.net")

    def test_a_client_id_that_is_not_one_is_refused(self):
        for bad in ("me", "1234", "{" + self.CLIENT + "}"):
            code, out, err, files = run({**SETTINGS, "GATEWAY_CLIENT_ID": bad})
            self.assertEqual((code, out, files), (2, "", {}), bad)
            self.assertIn("GATEWAY_CLIENT_ID", err)

    def test_the_fragments_are_off_unless_the_workflow_found_both_loggers(self):
        self.assertIs(values(run(SETTINGS)[3]["kit.parameters.json"])["deployUsageRecordingFragments"], False)
        self.assertIs(values(run({**SETTINGS, "RECORDING_FRAGMENTS": "false"})[3]["kit.parameters.json"])["deployUsageRecordingFragments"], False)
        self.assertIs(values(run({**SETTINGS, "RECORDING_FRAGMENTS": "TRUE"})[3]["kit.parameters.json"])["deployUsageRecordingFragments"], True)

    def test_anything_but_true_or_false_is_refused(self):
        for bad in ("yes", "1", "truee"):
            code, out, err, files = run({**SETTINGS, "RECORDING_FRAGMENTS": bad})
            self.assertEqual((code, out, files), (2, "", {}), bad)
            self.assertIn("RECORDING_FRAGMENTS", err)


class Refusals(unittest.TestCase):
    def refused(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual(code, 2, changes)
        self.assertEqual(files, {}, "nothing is written for a bad setting")
        self.assertEqual(out, "")
        return err

    def test_a_missing_setting_is_named(self):
        for name in SETTINGS:
            if name == "GATEWAY_PRINCIPAL_ID":
                continue
            env = {k: v for k, v in SETTINGS.items() if k != name}
            code, _, err, _ = run(env)
            self.assertEqual(code, 2, name)
            self.assertIn(name, err)
            self.assertEqual(run({**env, name: "   "})[0], 2, name)

    def test_bad_ids_names_and_labels(self):
        self.refused(ENV_SUBSCRIPTION_ID="not-a-guid")
        self.refused(GATEWAY_PRINCIPAL_ID="1234")
        for bad in ("rg name", "rg/x", "rg;x", "-", "a" * 91, "rg.", "$(x)"):
            self.refused(ENV_RESOURCE_GROUP=bad)
        for bad in ("Sweden Central", "sweden_central", "x", "https://x"):
            self.refused(ENV_LOCATION=bad)
        for bad in ('o"wner', "o<wner", "a" * 65, "o;wner", "o\nwner"):
            self.refused(ENV_OWNER=bad)

    def test_the_gateway_ids_must_have_the_shape_of_the_right_resource(self):
        for bad in ("", "/subscriptions/x", SETTINGS["GATEWAY_APPINSIGHTS_ID"], SETTINGS["GATEWAY_RESOURCE_ID"] + "/apis/x",
                    SETTINGS["GATEWAY_RESOURCE_ID"].replace("service/example-apim", "service/bad name")):
            self.refused(GATEWAY_RESOURCE_ID=bad)
        for bad in ("", SETTINGS["GATEWAY_RESOURCE_ID"], SETTINGS["GATEWAY_APPINSIGHTS_ID"].replace("66666666", "77777777")):
            self.refused(GATEWAY_APPINSIGHTS_ID=bad)

    def test_address_ranges_must_be_private_ipv4_and_nested(self):
        for bad in ("10.53.0.1/24", "10.53.0.0", "192.168.0.0/24", "8.8.8.0/24", "10.53.0.0/29", "10.53.0.0/8", "fd00::/64", "10.53.0.0/33", "x"):
            self.refused(ENV_VNET_PREFIX=bad, ENV_PE_SUBNET_PREFIX="10.53.0.0/29")
        for bad in ("10.54.0.0/28", "10.53.0.0/23", "10.53.0.0/30", "10.53.0.1/28", ""):
            self.refused(ENV_PE_SUBNET_PREFIX=bad)

    def test_dns_servers_must_be_private_ipv4_addresses(self):
        for bad in ("8.8.8.8", "10.20.0.4,8.8.8.8", "dns.example.com", "fd00::1", "10.20.0.4,,10.20.0.5", "1,2,3,4,5"):
            self.refused(ENV_DNS_SERVERS=bad)
        document = run({**SETTINGS, "ENV_DNS_SERVERS": "10.20.0.4, 10.20.0.5"})[3]["environment.parameters.json"]
        self.assertEqual(values(document)["dnsServers"], ["10.20.0.4", "10.20.0.5"])

    def test_budget_and_mail_addresses(self):
        for bad in ("0", "-5", "10001", "many", "1.5", ""):
            self.refused(ENV_BUDGET_AMOUNT=bad)
        for bad in ("not-a-mail", "a@b", "a@b.c", "a b@example.com", "a@example.com,", "a@example.com;b@example.com", "a@x.com," * 6 + "a@x.com"):
            self.refused(ENV_ALERT_EMAILS=bad)

    def test_the_budget_start_is_the_first_day_of_a_month(self):
        for bad in ("2026-11-02", "2026-13-01", "2026-00-01", "26-11-01", "2026-11-1", "2026-11-01T00:00:00Z", "tomorrow", "1899-01-01"):
            self.refused(ENV_BUDGET_START=bad)

    def test_the_messages_name_the_setting_and_never_echo_a_value(self):
        err = self.refused(ENV_OWNER='o"wner<secret>')
        self.assertIn("ENV_OWNER", err)
        self.assertNotIn("secret", err)


class Models(unittest.TestCase):
    def write(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "models.json"
        path.write_text(text, encoding="utf-8")
        return path

    def refused(self, models):
        code, _, err, files = run(SETTINGS, models=self.write(json.dumps(models)))
        self.assertEqual((code, files), (2, {}), models)
        return err

    def good(self, **changes):
        return {"name": "gpt-6-luna", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 20, "retirementDate": "2028-03-11", **changes}

    def test_the_models_of_the_repository_are_valid(self):
        self.assertEqual(run(SETTINGS)[0], 0)

    def test_bad_models_are_refused(self):
        for bad in ([], "x", [1], [{"name": "x"}], [self.good(name="Has Space")], [self.good(name="gpt;x")], [self.good(version="latest")],
                    [self.good(sku="Standard")], [self.good(capacity=0)], [self.good(capacity=True)], [self.good(capacity="20")],
                    [self.good(agentCapacity=0)], [self.good(agentCapacity=1001)], [self.good(agentCapacity=True)], [self.good(agentCapacity="20")], [self.good(agentCapacity=2.5)],
                    [{k: v for k, v in self.good().items() if k != "agentCapacity"}],
                    [self.good(retirementDate="soon")], [self.good(), self.good()], [self.good(extra=1)], [self.good(name=f"m{i}") for i in range(9)]):
            self.refused(bad)

    def test_a_file_that_is_not_json_is_refused(self):
        code, _, err, _ = run(SETTINGS, models=self.write("{"))
        self.assertEqual(code, 2)


class Contract(unittest.TestCase):
    """The contract of environment/contract.json and its policy: what reaches the gateway is what the contract says."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def contract(self, **changes):
        return {**json.loads(CONTRACT_FILE.read_text(encoding="utf-8")), **changes}

    def build(self, contract=None, policy=None, models=MODELS):
        contract_path = self.write("contract.json", json.dumps(self.contract() if contract is None else contract))
        policy_path = self.write("policy.xml", POLICY_FILE.read_text(encoding="utf-8") if policy is None else policy)
        return run(SETTINGS, "--contract", str(contract_path), "--contract-policy", str(policy_path), models=models)

    def refused(self, contract=None, policy=None, **kw):
        code, out, err, files = self.build(contract, policy, **kw)
        self.assertEqual((code, out, files), (2, "", {}), (contract, policy))
        return err

    def test_the_contract_of_the_repository_gives_a_fifth_file_that_fits_its_template(self):
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(set(files), {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json", "recording.parameters.json", "foundry.parameters.json", "operator.parameters.json",
                                      "contract.parameters.json", "cases.parameters.json", "planted.parameters.json"})
        given = files["contract.parameters.json"]["parameters"]
        declared = bicep_params(CONTRACT_BICEP)
        self.assertEqual(set(given), set(declared))
        self.assertTrue(all(not has_default for _, has_default in declared.values()), "every setting of the contract is given, none is left to a default")
        types = {"string": str, "array": list}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)
        lines = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual((lines["contract_name"], lines["contract_subscription"]), ("meternaut-agents", "meternaut-agents-sub-01"))
        self.assertEqual(lines["contract_apis"], "universal-llm-api,azure-openai-api")
        self.assertEqual(values(files["contract.parameters.json"])["apimName"], "example-apim")

    def test_without_a_contract_there_is_no_contract_file(self):
        self.assertNotIn("contract.parameters.json", run(SETTINGS)[3])

    def test_the_policy_carries_the_contracts_models_and_limits_and_counts_for_each_subscription(self):
        contract = self.contract()
        policy = values(self.build()[3]["contract.parameters.json"])["policyXml"]
        self.assertNotIn("@@", policy)
        inbound = ET.fromstring(policy).find("inbound")
        (models,) = [v for v in inbound.findall("set-variable") if v.get("name") == "allowedModels"]
        self.assertEqual(models.get("value"), ",".join(contract["allowedModels"]))
        (limit,) = inbound.findall("llm-token-limit")
        self.assertEqual(limit.get("tokens-per-minute"), str(contract["tokensPerMinute"]))
        self.assertEqual(limit.get("token-quota"), str(contract["tokenQuotaPerMonth"]))
        self.assertEqual((limit.get("token-quota-period"), limit.get("estimate-prompt-tokens")), ("Monthly", "false"))
        self.assertEqual(limit.get("counter-key"), "@(context.Subscription.Id)")
        self.assertIn("set-llm-requested-model", [f.get("fragment-id") for f in inbound.findall("include-fragment")])

    def test_a_contract_that_names_a_model_that_is_not_deployed_is_refused(self):
        for models in (["gpt-9"], [], ["gpt-6-luna", "gpt-6-luna"], "gpt-6-luna", [1], [["gpt-6-luna"]], ["gpt-6-luna", "gpt-6.1-sol", "x"]):
            self.refused(self.contract(allowedModels=models))

    def test_the_token_rate_may_not_be_more_than_the_smallest_deployment_can_serve(self):
        self.assertEqual(self.build(self.contract(tokensPerMinute=20000))[0], 0)
        self.assertIn("20000", self.refused(self.contract(tokensPerMinute=20001)))
        models = [{"name": "big", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 20, "retirementDate": "2028-03-11"},
                  {"name": "also-big", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 20, "retirementDate": "2028-03-11"},
                  {"name": "small", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 5, "agentCapacity": 5, "retirementDate": "2028-03-11"}]
        path = self.write("models.json", json.dumps(models))
        self.assertIn("5000", self.refused(self.contract(allowedModels=["big", "small"], tokensPerMinute=10000), models=path))
        self.assertEqual(self.build(self.contract(allowedModels=["big", "also-big"], tokensPerMinute=10000), models=path)[0], 0)

    def test_numbers_names_and_apis_are_checked(self):
        for changes in ({"tokensPerMinute": 0}, {"tokensPerMinute": True}, {"tokensPerMinute": "10000"}, {"tokensPerMinute": 10.5},
                        {"tokenQuotaPerMonth": 9999}, {"tokenQuotaPerMonth": 1_000_000_001}, {"tokenQuotaPerMonth": None},
                        {"name": "Meternaut"}, {"name": "ab"}, {"name": "-ab"}, {"name": "a" * 61}, {"name": "a b"}, {"name": "x;y"}, {"name": "ab-"},
                        {"description": ""}, {"description": "a\nb"}, {"description": "x" * 401}, {"description": 5},
                        {"apis": []}, {"apis": ["unified-ai-api"]}, {"apis": ["universal-llm-api", "universal-llm-api"]},
                        {"apis": "universal-llm-api"}, {"apis": [["x"]]}):
            self.refused(self.contract(**changes))
        self.refused({**self.contract(), "key": "x"})
        missing = self.contract()
        del missing["name"]
        self.refused(missing)
        self.assertEqual(self.build(self.contract(apis=["universal-llm-api"], tokenQuotaPerMonth=10000))[0], 0)

    def test_a_policy_template_that_lost_a_rule_is_refused(self):
        template = POLICY_FILE.read_text(encoding="utf-8")
        for broken in (template.replace("@@TOKEN_QUOTA@@", "1000"),
                       template.replace("@@ALLOWED_MODELS@@", "@@ALLOWED_MODELS@@,@@ALLOWED_MODELS@@"),
                       template.replace('counter-key="@(context.Subscription.Id)"', 'counter-key="shared"'),
                       template.replace('<include-fragment fragment-id="set-llm-requested-model" />', ""),
                       template.replace('name="allowedModels"', 'name="allowed"'),
                       template.replace('token-quota-period="Monthly"', 'token-quota-period="Daily"'),
                       template.replace('estimate-prompt-tokens="false"', 'estimate-prompt-tokens="true"'),
                       template.replace("<inbound>", '<inbound><llm-token-limit counter-key="x" tokens-per-minute="1" />'),
                       template.replace("<inbound>", "<inbound>@@EXTRA@@"),
                       # a rule the template does not have, nested or not, in any section
                       template.replace("</inbound>", '<choose><when condition="@(true)"><set-variable name="allowedModels" value="" /></when></choose></inbound>'),
                       template.replace("</inbound>", '<return-response><set-status code="200" /></return-response></inbound>'),
                       template.replace("</inbound>", '<set-variable name="allowedModels" value="" /></inbound>'),
                       template.replace("</inbound>", '<set-header name="x" exists-action="override"><value>1</value></set-header></inbound>'),
                       template.replace("</outbound>", '<set-variable name="allowedModels" value="" /></outbound>'),
                       template.replace("</backend>", '<set-variable name="allowedModels" value="" /></backend>'),
                       template.replace("</on-error>", '<llm-token-limit counter-key="x" tokens-per-minute="1" /></on-error>'),
                       template.replace("<base />", '<base><set-variable name="allowedModels" value="" /></base>', 1),
                       template.replace('<include-fragment fragment-id="set-llm-requested-model" />', '<include-fragment fragment-id="set-llm-requested-model" /><include-fragment fragment-id="ai-usage" />'),
                       template.replace('<set-variable name="enableResponseHeaders" value="@(true)" />', '<set-variable name="enableResponseHeaders" value="@(true)" /><set-variable name="other" value="1" />'),
                       template.replace('<set-variable name="enableResponseHeaders" value="@(true)" />', '<set-variable name="enableResponseHeaders" value="@(false)" />'),
                       template.replace("<llm-token-limit ", '<llm-token-limit retry-after-variable-name="x" '),
                       # the same rules in another order
                       template.replace('<set-variable name="enableResponseHeaders" value="@(true)" />', "").replace("<base />", '<base /><set-variable name="enableResponseHeaders" value="@(true)" />', 1),
                       template.replace("<inbound>", "<inbound><backend />"),
                       template.replace("</policies>", ""),
                       "<policies><backend /></policies>",
                       ""):
            self.refused(policy=broken)

    def test_the_two_files_go_together_and_must_be_readable(self):
        for extra in (("--contract", str(CONTRACT_FILE)), ("--contract-policy", str(POLICY_FILE))):
            code, _, err, files = run(SETTINGS, *extra)
            self.assertEqual((code, files), (2, {}))
            self.assertIn("go together", err)
        missing = str(self.tmp / "missing")
        self.assertEqual(run(SETTINGS, "--contract", missing, "--contract-policy", str(POLICY_FILE))[0], 2)
        self.assertEqual(run(SETTINGS, "--contract", str(CONTRACT_FILE), "--contract-policy", missing)[0], 2)
        self.assertEqual(run(SETTINGS, "--contract", str(self.write("c.json", "{")), "--contract-policy", str(POLICY_FILE))[0], 2)


class FirstCases(unittest.TestCase):
    """The parameter file of the first cases app (environment/cases/main.bicep): it names what the usage recording made, and nothing of a gateway or a contract."""

    CASES = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")

    def build(self, **changes):
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "contract.json"
            contract.write_text(CONTRACT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            code, out, err, files = run({**SETTINGS, **changes}, "--contract", str(contract), "--contract-policy", str(POLICY_FILE))
        self.assertEqual((code, err), (0, ""))
        return files, dict(line.split("=", 1) for line in out.splitlines())

    def test_the_file_fits_the_template_and_every_setting_has_a_value_of_the_right_type(self):
        files, _ = self.build()
        declared = bicep_params(self.CASES)
        given = files["cases.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)

    def test_it_names_the_storage_and_the_namespace_that_the_recording_has_and_no_workflow_principal(self):
        files, lines = self.build()
        cases, recording = values(files["cases.parameters.json"]), values(files["recording.parameters.json"])
        self.assertEqual(cases["storageAccountName"], recording["storageAccountName"])
        self.assertEqual(cases["eventHubNamespaceName"], recording["eventHubNamespaceName"])
        self.assertNotIn("workflowPrincipalId", cases)
        self.assertNotIn("workflowPrincipalId", recording)
        self.assertEqual(cases["location"], recording["location"])
        self.assertRegex(cases["functionAppName"], r"^func-meternaut-cases-[0-9a-f]{8}$")
        self.assertEqual(lines["cases_function_app_name"], cases["functionAppName"])
        self.assertNotEqual(cases["functionAppName"], recording["functionAppName"])
        self.assertLessEqual(len(cases["functionAppName"]), 60)

    def test_the_plans_subnet_is_the_same_in_the_cases_file_and_in_the_model_side_file(self):
        files, lines = self.build()
        cases, environment = values(files["cases.parameters.json"]), values(files["environment.parameters.json"])
        self.assertEqual(cases["webSubnetPrefix"], environment["webSubnetPrefix"])
        self.assertEqual(lines["web_subnet_prefix"], cases["webSubnetPrefix"])
        self.assertNotEqual(cases["webSubnetPrefix"], environment["funcSubnetPrefix"], "the usage recording's subnet is delegated to Flex Consumption")

    def test_the_file_says_whether_the_integration_subnet_is_there_already_and_says_no_when_nobody_has_looked(self):
        # the subnet is made once: a template that makes it again takes away the route table that the landing zone's network manager put on it
        self.assertIs(values(self.build()[0]["cases.parameters.json"])["webSubnetExists"], False)
        for given, expected in (("", False), ("false", False), ("FALSE", False), ("true", True), (" True ", True)):
            self.assertIs(values(self.build(ENV_WEB_SUBNET_EXISTS=given)[0]["cases.parameters.json"])["webSubnetExists"], expected, given)
        for refused in ("yes", "1", "exists"):
            with tempfile.TemporaryDirectory() as tmp:
                contract = Path(tmp) / "contract.json"
                contract.write_text(CONTRACT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
                code, out, err, files = run({**SETTINGS, "ENV_WEB_SUBNET_EXISTS": refused}, "--contract", str(contract), "--contract-policy", str(POLICY_FILE))
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("ENV_WEB_SUBNET_EXISTS is true or false", err)
        self.assertIn("param webSubnetExists bool = false", self.CASES)

    def test_it_reads_the_pilot_subscription_and_names_no_gateway_and_no_contract_and_no_key(self):
        files, lines = self.build()
        cases = values(files["cases.parameters.json"])
        self.assertEqual(cases["scopeSubscriptions"], SETTINGS["ENV_SUBSCRIPTION_ID"])
        self.assertFalse([name for name in cases if "gateway" in name.lower() or "product" in name.lower() or "contract" in name.lower()], "the app reads no key, so the file names no gateway")
        self.assertNotIn("gatewayUrl", cases)
        self.assertNotIn("gatewayProductSubscriptionId", cases)
        self.assertNotIn("gateway_url", lines, "no step of the workflow knocks at the gateway's address any more")
        self.assertNotIn("azure-api.net", json.dumps(files["cases.parameters.json"]))
        self.assertNotIn("/subscriptions/meternaut-agents-sub-01", json.dumps(files["cases.parameters.json"]))

    def test_the_two_older_roles_are_given_two_different_deployments_of_the_agents_resource_by_the_defaults_of_the_template(self):
        # The Detective and the Skeptic call the model deployments of the agents' own Foundry resource (environment/foundry/main.bicep deploys environment/models.json), so the names that the
        # template defaults to are deployments of that resource and they differ: the file leaves them out and the template's defaults are what the app is given.
        cases = values(self.build()[0]["cases.parameters.json"])
        self.assertNotIn("modelDetective", cases)
        self.assertNotIn("modelSkeptic", cases)
        models = dict(re.findall(r"^param (modelDetective|modelSkeptic) string = '([^']+)'$", self.CASES, re.M))
        self.assertEqual(sorted(models), ["modelDetective", "modelSkeptic"])
        self.assertNotEqual(models["modelDetective"], models["modelSkeptic"], "the Skeptic is another model than the Detective, so that it is more independent")
        deployed = {m["name"] for m in json.loads(MODELS.read_text(encoding="utf-8"))}
        self.assertTrue(set(models.values()) <= deployed, "the Detective and the Skeptic call deployments that the Foundry resource of the agents has")
        self.assertEqual(models["modelDetective"], json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))["allowedModels"][0], "as they were while the contract named them")
        self.assertEqual(models["modelSkeptic"], json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))["allowedModels"][1])

    def test_a_contract_with_one_model_is_refused_because_the_skeptic_has_to_be_another_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
            contract["allowedModels"] = contract["allowedModels"][:1]
            path = Path(tmp) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            code, out, err, files = run(SETTINGS, "--contract", str(path), "--contract-policy", str(POLICY_FILE))
        self.assertEqual(code, 2)
        self.assertIn("at least two models", err)
        self.assertEqual(out, "")

    def test_the_hub_and_the_one_identity_are_the_ones_the_template_makes(self):
        _, lines = self.build()
        self.assertIn("var controlHubName = '" + lines["cases_hub_name"] + "'", self.CASES)
        self.assertIn("name: 'id-${workload}-console-auth'", self.CASES, "the one user-assigned identity of the template: the console's sign-in")
        self.assertNotIn("id-${workload}-cases", self.CASES, "the user-assigned identity that the app's system-assigned one replaced is not made any more")
        self.assertNotIn("cases_identity_name", lines)

    def test_the_cases_file_does_not_depend_on_the_contract_and_is_the_same_with_or_without_it(self):
        # The contract is the API Management side, which Meternaut is leaving: the first cases are deployed without it.
        without = run(SETTINGS)
        self.assertEqual(without[0], 0)
        with_contract = self.build()[0]["cases.parameters.json"]
        self.assertEqual(without[3]["cases.parameters.json"], with_contract)
        self.assertNotIn("contract.parameters.json", without[3], "the contract's own file is still made only when the contract is asked for")
        self.assertNotIn("contract_subscription", dict(line.split("=", 1) for line in without[1].splitlines()))
        self.assertEqual(self.build()[1]["contract_subscription"], "meternaut-agents-sub-01", "the contract action keeps its output")

    def test_the_cases_file_is_written_with_no_gateway_identity_at_all_in_a_preview_and_it_names_the_foundry_project_when_the_workflow_found_it(self):
        settings = {k: v for k, v in SETTINGS.items() if k not in ("GATEWAY_PRINCIPAL_ID", "GATEWAY_CLIENT_ID", "RECORDING_FRAGMENTS")}
        code, out, err, files = run({**settings, "ENV_FOUNDRY_PROJECT_EXISTS": "true"}, "--preview")
        self.assertEqual((code, err), (0, ""))
        cases = values(files["cases.parameters.json"])
        lines = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual(cases["foundryProjectEndpoint"], lines["foundry_project_endpoint"])
        self.assertTrue(cases["foundryProjectEndpoint"].endswith(".services.ai.azure.com/api/projects/meternaut"))

    PEOPLE = '[{"oid": "AAAAAAAA-1111-4222-8333-444444444444", "name": "Tino", "roles": ["owner", "approver", "ops"], "mail": "tino@example.com"}]'
    APP = "11111111-2222-3333-4444-555555555555"

    def test_without_the_console_variables_the_sign_in_is_not_set_up_and_nobody_is_listed(self):
        files, _ = self.build()
        cases = values(files["cases.parameters.json"])
        self.assertEqual((cases["consoleAppClientId"], cases["consolePeople"], cases["consoleUserObjectIds"], cases["mailSender"]), ("", "[]", [], ""))

    def test_the_people_and_the_app_registration_become_the_settings_of_the_console_and_of_the_sign_in(self):
        files, _ = self.build(CONSOLE_APP_CLIENT_ID=self.APP.upper(), CONSOLE_PEOPLE=self.PEOPLE, MAIL_SENDER="meternaut-ai@example.onmicrosoft.com")
        cases = values(files["cases.parameters.json"])
        self.assertEqual(cases["consoleAppClientId"], self.APP)
        self.assertEqual(cases["consoleUserObjectIds"], ["aaaaaaaa-1111-4222-8333-444444444444"])
        people = json.loads(cases["consolePeople"])
        self.assertEqual(people[0]["oid"], "aaaaaaaa-1111-4222-8333-444444444444", "the object id is lower-case, because the sign-in sends it that way")
        self.assertEqual(people[0]["roles"], ["owner", "approver", "ops"])
        self.assertEqual(cases["mailSender"], "meternaut-ai@example.onmicrosoft.com")

    def test_a_console_that_would_let_nobody_in_or_that_has_bad_people_is_refused(self):
        bad = {
            "an app registration without people": {"CONSOLE_APP_CLIENT_ID": self.APP},
            "an app registration that is not a client id": {"CONSOLE_APP_CLIENT_ID": "nope", "CONSOLE_PEOPLE": self.PEOPLE},
            "people that are not JSON": {"CONSOLE_PEOPLE": "not json"},
            "people that are not a list": {"CONSOLE_PEOPLE": "{}"},
            "a person without an object id": {"CONSOLE_PEOPLE": '[{"name": "A", "roles": ["owner"]}]'},
            "a person with a role that does not exist": {"CONSOLE_PEOPLE": '[{"oid": "aaaaaaaa-1111-4222-8333-444444444444", "name": "A", "roles": ["admin"]}]'},
            "a person without roles": {"CONSOLE_PEOPLE": '[{"oid": "aaaaaaaa-1111-4222-8333-444444444444", "name": "A", "roles": []}]'},
            "a person with a bad address": {"CONSOLE_PEOPLE": '[{"oid": "aaaaaaaa-1111-4222-8333-444444444444", "name": "A", "roles": ["owner"], "mail": "x"}]'},
            "the same person twice": {"CONSOLE_PEOPLE": '[{"oid": "aaaaaaaa-1111-4222-8333-444444444444", "name": "A", "roles": ["owner"]}, {"oid": "AAAAAAAA-1111-4222-8333-444444444444", "name": "B", "roles": ["owner"]}]'},
            "a sender that is not an address": {"MAIL_SENDER": "nobody"},
        }
        for label, change in bad.items():
            with self.subTest(label):
                with tempfile.TemporaryDirectory() as tmp:
                    contract = Path(tmp) / "contract.json"
                    contract.write_text(CONTRACT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
                    code, out, err, _ = run({**SETTINGS, **change}, "--contract", str(contract), "--contract-policy", str(POLICY_FILE))
                self.assertEqual(code, 2, err)
                self.assertEqual(out, "")

    def test_the_planting_has_a_name_that_the_run_chooses_and_a_public_address_only_when_asked(self):
        files, _ = self.build()
        planted = values(files["planted.parameters.json"])
        self.assertEqual((planted["plantedId"], planted["plantPublicIp"]), ("demo", False))
        files, _ = self.build(PLANTED_ID="r42", PLANT_PUBLIC_IP="TRUE")
        planted = values(files["planted.parameters.json"])
        self.assertEqual((planted["plantedId"], planted["plantPublicIp"]), ("r42", True))
        self.assertEqual(planted["location"], values(files["recording.parameters.json"])["location"])
        for bad in ({"PLANTED_ID": "Has Space"}, {"PLANTED_ID": "x" * 13}, {"PLANT_PUBLIC_IP": "maybe"}):
            with self.subTest(bad):
                self.assertEqual(run({**SETTINGS, **bad})[0], 2)

    def test_the_planted_file_fits_its_template(self):
        files, _ = self.build()
        template = (ROOT / "environment" / "cases" / "planted.bicep").read_text(encoding="utf-8")
        declared = bicep_params(template)
        given = files["planted.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        self.assertTrue({name for name, (_, has_default) in declared.items() if not has_default} <= set(given))

    def test_the_token_allowance_of_the_contract_covers_a_month_of_runs_and_stays_under_the_standing_limit(self):
        contract = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(contract["tokenQuotaPerMonth"], 2_000_000)
        # AGENTS.md rule 15(g): at most 25 EUR of model calls in total. Even if every token of the month were an output token of the
        # dearer model (DataZone Standard, the price snapshot's figure), the allowance would stay under that limit.
        snapshot = json.loads((ROOT / "docs" / "design" / "cost" / "prices-snapshot.json").read_text(encoding="utf-8"))
        dearest = max(m["prices"]["EUR"] for m in snapshot["meters"]
                      if m.get("product") == "Azure OpenAI GPT6" and re.fullmatch(r"6(\.1)?-sol ShortCo Opt Std DZ", m.get("sku", "")))
        self.assertGreater(dearest, 5, "the price was found")
        self.assertLess(contract["tokenQuotaPerMonth"] / 1_000_000 * dearest, 25)


class Foundry(unittest.TestCase):
    """The parameter file of the Foundry resource of the agents (environment/foundry/main.bicep), the names it carries, and what the cases file takes from it."""

    FOUNDRY = (ROOT / "environment" / "foundry" / "main.bicep").read_text(encoding="utf-8")
    CASES = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
    RETIRED_PRINCIPAL = "ABCDEFAB-1234-5678-9ABC-DEF012345678"

    def files(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual((code, err), (0, ""))
        return files, dict(line.split("=", 1) for line in out.splitlines())

    def cases_file(self, **changes):
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "contract.json"
            contract.write_text(CONTRACT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            code, out, err, files = run({**SETTINGS, **changes}, "--contract", str(contract), "--contract-policy", str(POLICY_FILE))
        return code, out, err, files

    def test_the_file_fits_the_template_and_every_setting_has_a_value_of_the_right_type(self):
        files, _ = self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL)
        declared = bicep_params(self.FOUNDRY)
        given = files["foundry.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)
        self.assertNotIn("restoreAccount", given, "the deploy sets it only after the platform says that a soft-deleted resource of the name is there")

    def test_the_names_are_a_host_name_inside_its_limit_the_same_on_every_run_and_not_the_model_accounts(self):
        files, outputs = self.files()
        again = self.files()[1]
        token = ep.digest(SETTINGS["ENV_SUBSCRIPTION_ID"], SETTINGS["ENV_RESOURCE_GROUP"])
        account = outputs["foundry_account_name"]
        self.assertEqual(account, f"aif-meternaut-agents-{token}")
        self.assertRegex(account, r"^[A-Za-z0-9][A-Za-z0-9-]{1,63}$")
        self.assertEqual({k: v for k, v in outputs.items() if k.startswith("foundry_")}, {k: v for k, v in again.items() if k.startswith("foundry_")})
        self.assertNotEqual(account, outputs["account_name"], "the model account was made with allowProjectManagement false and can never hold a project")
        self.assertNotIn(outputs["account_name"], account)
        self.assertEqual((outputs["foundry_project_name"], outputs["foundry_guardrail_name"]), ("meternaut", "meternaut-agents"))
        self.assertEqual(outputs["foundry_private_endpoint"], f"pe-{account}")
        self.assertEqual(outputs["foundry_project_endpoint"], f"https://{account}.services.ai.azure.com/api/projects/meternaut")
        foundry = values(files["foundry.parameters.json"])
        self.assertEqual((foundry["accountName"], foundry["projectName"], foundry["guardrailName"]), (account, "meternaut", "meternaut-agents"))
        self.assertEqual((foundry["location"], foundry["owner"]), ("swedencentral", "owner@example.com"))

    def test_the_names_differ_per_subscription_and_group_and_ignore_case(self):
        base = ep.foundry_names(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-a")
        self.assertNotEqual(base["foundry_account_name"], ep.foundry_names(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-b")["foundry_account_name"])
        self.assertNotEqual(base["foundry_account_name"], ep.foundry_names("99999999-2222-3333-4444-555555555555", "rg-a")["foundry_account_name"])
        self.assertEqual(base, ep.foundry_names(SETTINGS["ENV_SUBSCRIPTION_ID"].upper(), "RG-A"))

    def test_the_names_of_the_file_are_the_defaults_of_the_template_and_the_endpoint_has_the_form_that_the_template_returns(self):
        self.assertIn("param projectName string = 'meternaut'", self.FOUNDRY)
        self.assertIn("param guardrailName string = 'meternaut-agents'", self.FOUNDRY)
        self.assertIn("name: 'pe-${accountName}'", self.FOUNDRY)
        self.assertIn("output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'", self.FOUNDRY)
        outputs = self.files()[1]
        self.assertTrue(outputs["foundry_project_endpoint"].startswith(f"https://{outputs['foundry_account_name']}.services.ai.azure.com/api/projects/"))
        self.assertEqual(outputs["foundry_project_endpoint"].rsplit("/", 1)[1], outputs["foundry_project_name"])

    def test_the_models_are_the_ones_of_models_json_with_the_capacity_that_the_agents_have_and_nothing_else(self):
        files, _ = self.files()
        deployed = values(files["foundry.parameters.json"])["models"]
        listed = json.loads(MODELS.read_text(encoding="utf-8"))
        wanted = [{"name": m["name"], "version": m["version"], "sku": m["sku"], "capacity": m["agentCapacity"]} for m in listed]
        self.assertEqual(deployed, wanted)
        self.assertEqual([m["name"] for m in values(files["environment.parameters.json"])["models"]], [m["name"] for m in deployed], "the same models as the model side")
        self.assertEqual(values(files["environment.parameters.json"])["models"], [{k: m[k] for k in ("name", "version", "sku", "capacity")} for m in listed],
                         "the model side keeps its own capacity")
        for model in deployed:
            self.assertEqual(set(model), {"name", "version", "sku", "capacity"}, "no retirement date and no agentCapacity reaches the template")

    def test_the_capacity_of_the_agents_may_differ_from_the_one_of_the_model_side_and_each_side_gets_its_own(self):
        models = [{"name": "alpha", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 70, "retirementDate": "2028-03-11"},
                  {"name": "beta", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 30, "agentCapacity": 10, "retirementDate": "2028-03-11"}]
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "models.json"
        path.write_text(json.dumps(models), encoding="utf-8")
        code, _, _, files = run(SETTINGS, models=path)
        self.assertEqual(code, 0)
        self.assertEqual([m["capacity"] for m in values(files["foundry.parameters.json"])["models"]], [70, 10])
        self.assertEqual([m["capacity"] for m in values(files["environment.parameters.json"])["models"]], [20, 30])

    SYSTEM_PRINCIPAL = "12345678-DDDD-EEEE-FFFF-123456789012"

    def test_the_system_assigned_identity_of_the_cases_app_reaches_the_file_and_without_it_a_placeholder_says_so_and_nothing_else_is_asked_of_it(self):
        files, outputs = self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL)
        self.assertEqual(values(files["foundry.parameters.json"])["casesSystemPrincipalId"], self.SYSTEM_PRINCIPAL.lower())
        self.assertEqual(outputs["cases_system_principal_known"], "true")
        for empty in ("", "   "):
            files, outputs = self.files(CASES_SYSTEM_PRINCIPAL_ID=empty)
            self.assertEqual(values(files["foundry.parameters.json"])["casesSystemPrincipalId"], ep.PLACEHOLDER)
            self.assertEqual(outputs["cases_system_principal_known"], "false", "the workflow refuses to deploy the Foundry resource then")
        files, outputs = self.files()
        self.assertEqual((values(files["foundry.parameters.json"])["casesSystemPrincipalId"], outputs["cases_system_principal_known"]), (ep.PLACEHOLDER, "false"),
                         "nobody looked: the file holds a placeholder, and no role is ever given to it because the workflow refuses to deploy")
        self.assertEqual(run({**SETTINGS, "GATEWAY_PRINCIPAL_ID": ""}, "--preview")[0], 0, "a preview needs no cases identity")

    def test_a_system_assigned_identity_that_is_not_an_object_id_is_refused_without_echoing_it(self):
        for bad in ("me", "1234", "{" + self.SYSTEM_PRINCIPAL + "}", self.SYSTEM_PRINCIPAL + "0", "not-a-guid-but-with-secret"):
            code, out, err, files = run({**SETTINGS, "CASES_SYSTEM_PRINCIPAL_ID": bad})
            self.assertEqual((code, out, files), (2, "", {}), bad)
            self.assertIn("CASES_SYSTEM_PRINCIPAL_ID", err)
            self.assertNotIn("secret", err)
            if len(bad) > 8:
                self.assertNotIn(bad, err)

    def test_the_user_assigned_identity_of_the_cases_app_is_not_read_any_more_and_reaches_no_file(self):
        files, outputs = self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL, CASES_PRINCIPAL_ID=self.RETIRED_PRINCIPAL)
        self.assertNotIn("casesPrincipalId", values(files["foundry.parameters.json"]))
        self.assertNotIn("cases_principal_known", outputs)
        self.assertNotIn(self.RETIRED_PRINCIPAL.lower(), json.dumps(files).lower())
        code, out, err, files = run({**SETTINGS, "CASES_PRINCIPAL_ID": "not-a-guid"})
        self.assertEqual((code, err), (0, ""), "a setting that nothing reads is not checked either")

    def test_the_template_takes_the_system_assigned_identity_as_its_one_required_identity_parameter_of_guid_length(self):
        self.assertRegex(self.FOUNDRY, r"(?m)^@minLength\(36\)\n@maxLength\(36\)\nparam casesSystemPrincipalId string$")
        self.assertNotIn("casesPrincipalId", self.FOUNDRY, "the user-assigned identity is gone from the template")

    def test_the_cases_app_is_given_the_project_endpoint_only_when_the_workflow_found_the_project(self):
        for given in ("", "false", " FALSE "):
            code, out, err, files = self.cases_file(ENV_FOUNDRY_PROJECT_EXISTS=given)
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(values(files["cases.parameters.json"])["foundryProjectEndpoint"], "", given)
        self.assertEqual(values(self.cases_file()[3]["cases.parameters.json"])["foundryProjectEndpoint"], "", "nobody looked: the investigation stays off")
        for given in ("true", " True "):
            code, out, err, files = self.cases_file(ENV_FOUNDRY_PROJECT_EXISTS=given)
            self.assertEqual((code, err), (0, ""))
            lines = dict(line.split("=", 1) for line in out.splitlines())
            self.assertEqual(values(files["cases.parameters.json"])["foundryProjectEndpoint"], lines["foundry_project_endpoint"], given)
        for refused in ("yes", "1", "exists"):
            code, out, err, files = self.cases_file(ENV_FOUNDRY_PROJECT_EXISTS=refused)
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("ENV_FOUNDRY_PROJECT_EXISTS is true or false", err)

    def test_the_cases_template_takes_the_endpoint_off_by_default_and_names_two_deployed_models_that_differ(self):
        self.assertIn("param foundryProjectEndpoint string = ''", self.CASES)
        models = dict(re.findall(r"^param (foundryModelInvestigator|foundryModelSkeptic) string = '([^']+)'$", self.CASES, re.M))
        self.assertEqual(sorted(models), ["foundryModelInvestigator", "foundryModelSkeptic"])
        self.assertNotEqual(models["foundryModelInvestigator"], models["foundryModelSkeptic"])
        deployed = {m["name"] for m in json.loads(MODELS.read_text(encoding="utf-8"))}
        self.assertTrue(set(models.values()) <= deployed, "the agents use deployments that the Foundry resource has")

    def test_nothing_secret_is_in_the_file(self):
        text = json.dumps(self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL)[0]["foundry.parameters.json"]).lower()
        for word in ("key", "secret", "password", "connectionstring", "token"):
            self.assertNotIn(word, text, word)


class Operator(unittest.TestCase):
    """The parameter file of the Operator (environment/operator/main.bicep): the subnet of its container groups is the last free /27 and is made once."""

    OPERATOR = (ROOT / "environment" / "operator" / "main.bicep").read_text(encoding="utf-8")

    def files(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual((code, err), (0, ""))
        return files, dict(line.split("=", 1) for line in out.splitlines())

    def test_the_file_fits_the_template_and_every_setting_has_a_value_of_the_right_type(self):
        files, _ = self.files()
        declared = bicep_params(self.OPERATOR)
        given = files["operator.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)
        operator = values(files["operator.parameters.json"])
        self.assertEqual(set(operator), {"location", "owner", "opsSubnetPrefix", "opsSubnetExists", "eventHubNamespaceName"},
                         "a range, a flag, the name of a namespace and two tags: nothing else, and nothing secret")
        self.assertEqual((operator["location"], operator["owner"]), ("swedencentral", "owner@example.com"))

    def test_the_namespace_is_the_one_that_the_usage_recording_and_the_first_cases_use(self):
        files, outputs = self.files()
        operator = values(files["operator.parameters.json"])["eventHubNamespaceName"]
        self.assertEqual(operator, values(files["recording.parameters.json"])["eventHubNamespaceName"], "the Operator reads the namespace that the usage recording makes")
        self.assertEqual(operator, outputs["event_hub_namespace"])
        self.assertRegex(operator, r"^evhns-meternaut-[0-9a-f]{8}$")
        self.assertIn("param eventHubNamespaceName string", self.OPERATOR)

    def test_the_subnet_is_the_last_free_27_and_overlaps_none_of_the_other_three(self):
        files, outputs = self.files()
        env, operator = values(files["environment.parameters.json"]), values(files["operator.parameters.json"])
        self.assertEqual(operator["opsSubnetPrefix"], "10.53.0.192/27")
        self.assertEqual(outputs["ops_subnet_prefix"], "10.53.0.192/27")
        taken = [ipaddress.ip_network(env[name]) for name in ("peSubnetPrefix", "funcSubnetPrefix", "webSubnetPrefix")]
        self.assertFalse(any(ipaddress.ip_network(operator["opsSubnetPrefix"]).overlaps(other) for other in taken))
        self.assertTrue(ipaddress.ip_network(operator["opsSubnetPrefix"]).subnet_of(ipaddress.ip_network(env["vnetAddressPrefix"])))
        # whichever /27 the endpoints use, the Operator gets the last /27 that the other three leave
        for endpoints, expected in (("10.53.0.192/27", ("10.53.0.0/27", "10.53.0.224/27", "10.53.0.160/27")),
                                    ("10.53.0.224/27", ("10.53.0.0/27", "10.53.0.192/27", "10.53.0.160/27"))):
            files, _ = self.files(ENV_PE_SUBNET_PREFIX=endpoints)
            env = values(files["environment.parameters.json"])
            self.assertEqual((env["funcSubnetPrefix"], env["webSubnetPrefix"], values(files["operator.parameters.json"])["opsSubnetPrefix"]), expected, endpoints)

    def test_a_network_with_four_27_gives_one_to_each_and_a_network_without_a_free_one_is_refused_by_name(self):
        files, _ = self.files(ENV_VNET_PREFIX="10.53.0.0/25")
        env = values(files["environment.parameters.json"])
        self.assertEqual((env["peSubnetPrefix"], env["funcSubnetPrefix"], env["webSubnetPrefix"], values(files["operator.parameters.json"])["opsSubnetPrefix"]),
                         ("10.53.0.0/27", "10.53.0.32/27", "10.53.0.96/27", "10.53.0.64/27"))
        # an endpoint subnet of a /26 takes two of the four
        code, out, err, files = run({**SETTINGS, "ENV_VNET_PREFIX": "10.53.0.0/25", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/26"})
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("Operator", err)
        self.assertIn("ENV_VNET_PREFIX", err)
        # the function that picks it refuses a network that is smaller than a /27, and says so as a problem and not as a traceback
        small = ipaddress.ip_network("10.53.0.0/28")
        with self.assertRaises(ep.Problem):
            ep.ops_subnet(small, small, small, small)

    def test_the_file_says_whether_the_subnet_is_there_already_and_says_no_when_nobody_has_looked(self):
        # the subnet is made once: a template that makes it again takes away the route table that the landing zone's network manager put on it
        self.assertIs(values(self.files()[0]["operator.parameters.json"])["opsSubnetExists"], False)
        for given, expected in (("", False), ("false", False), ("FALSE", False), ("true", True), (" True ", True)):
            files, _ = self.files(ENV_OPS_SUBNET_EXISTS=given)
            self.assertIs(values(files["operator.parameters.json"])["opsSubnetExists"], expected, given)
        for refused in ("yes", "1", "exists"):
            code, out, err, files = run({**SETTINGS, "ENV_OPS_SUBNET_EXISTS": refused})
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("ENV_OPS_SUBNET_EXISTS is true or false", err)
        self.assertIn("param opsSubnetExists bool = false", self.OPERATOR)

    def test_the_names_the_workflow_reads_are_the_ones_the_template_makes(self):
        _, outputs = self.files()
        self.assertEqual((outputs["operator_identity_name"], outputs["operator_subnet_name"]), ("id-meternaut-operator", "snet-ops"))
        self.assertIn("param workload string = 'meternaut'", self.OPERATOR)
        self.assertIn("name: 'id-${workload}-operator'", self.OPERATOR)
        self.assertIn("var opsSubnetName = 'snet-ops'", self.OPERATOR)


class AiGateway(unittest.TestCase):
    """The parameter files and the policy file of the AI Gateway (environment/aigateway/subnet.bicep, environment/aigateway/main.bicep, environment/aigateway/policies.json): written only when --aigateway-policies
    asks for them.

    The subnet is the last free /26 (a /27 when no /26 is free), made once like the Operator's, in a template and a file of its own because the action makes it first and waits for the landing zone's route table
    on it before it makes the gateway (test_aigateway_subnet_first.py), and the policies are held to the models and to the owner's standing limit."""

    TEMPLATE = (ROOT / "environment" / "aigateway" / "main.bicep").read_text(encoding="utf-8")
    SUBNET_TEMPLATE = (ROOT / "environment" / "aigateway" / "subnet.bicep").read_text(encoding="utf-8")
    POLICIES = ROOT / "environment" / "aigateway" / "policies.json"
    AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    def files(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes}, "--aigateway-policies", str(self.POLICIES))
        self.assertEqual((code, err), (0, ""))
        return files, dict(line.split("=", 1) for line in out.splitlines())

    def with_policies(self, document, **changes):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.json"
            path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
            return run({**SETTINGS, **changes}, "--aigateway-policies", str(path))

    def policies(self):
        return json.loads(self.POLICIES.read_text(encoding="utf-8"))

    def test_nothing_of_the_gateway_is_written_or_printed_unless_the_option_asks_for_it(self):
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertFalse([name for name in files if "aigateway" in name], "the other actions are not touched by the gateway")
        self.assertNotIn("aigateway", out)

    def test_the_three_files_are_written_and_the_outputs_name_what_the_workflow_reads(self):
        files, outputs = self.files()
        mine = {"aigateway-subnet.parameters.json", "aigateway.parameters.json", "aigateway-policies.json"}
        self.assertTrue(mine <= set(files))
        self.assertEqual(set(files) - mine,
                         {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json", "recording.parameters.json", "foundry.parameters.json", "operator.parameters.json", "planted.parameters.json",
                          "cases.parameters.json"})
        self.assertEqual({key: value for key, value in outputs.items() if key.startswith("aigateway_")},
                         {"aigateway_name": outputs["aigateway_name"], "aigateway_subnet_name": "snet-aigw", "aigateway_subnet_prefix": "10.53.0.128/26",
                          "aigateway_aliases": "gpt-6-luna gpt-6.1-sol", "aigateway_files": "true"})
        self.assertEqual(files["aigateway-policies.json"], self.policies(), "the policies go to the gateway as they are in the repository")

    def test_each_file_fits_its_template_and_every_setting_has_a_value_of_the_right_type(self):
        files, _ = self.files()
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, template in (("aigateway.parameters.json", self.TEMPLATE), ("aigateway-subnet.parameters.json", self.SUBNET_TEMPLATE)):
            declared = bicep_params(template)
            given = files[name]["parameters"]
            self.assertTrue(set(given) <= set(declared), (name, set(given) - set(declared)))
            required = {setting for setting, (_, has_default) in declared.items() if not has_default}
            self.assertTrue(required <= set(given), (name, required - set(given)))
            for setting, wrapped in given.items():
                self.assertIsInstance(wrapped["value"], types[declared[setting][0]], (name, setting))
        gateway = values(files["aigateway.parameters.json"])
        self.assertEqual(set(gateway), {"location", "owner", "gatewayName", "foundryAccountName", "models", "foundryProjectPrincipalId"},
                         "names, a flag and the models: nothing secret, nothing of the subnet, and the telemetry stays at the template's default, which is off")
        subnet = values(files["aigateway-subnet.parameters.json"])
        self.assertEqual(set(subnet), {"location", "owner", "aigwSubnetPrefix", "aigwSubnetExists"},
                         "the range and whether it is there already; the workload is left to the template's default, as the file of the gateway leaves it")
        self.assertEqual((subnet["location"], subnet["owner"]), (gateway["location"], gateway["owner"]), "the subnet is in the gateway's region and has the gateway's owner")
        self.assertEqual(bicep_params(self.TEMPLATE)["telemetryEnabled"], ("bool", True))
        self.assertIn("param telemetryEnabled bool = false", self.TEMPLATE)
        self.assertEqual(bicep_params(self.TEMPLATE)["foundryProjectPrincipalId"], ("string", True))
        for moved in ("aigwSubnetPrefix", "aigwSubnetExists"):
            self.assertNotIn(moved, bicep_params(self.TEMPLATE), "the gateway's template no longer takes the subnet's settings")

    def test_the_name_is_stable_inside_the_services_limit_and_made_from_the_digest(self):
        names = {values(self.files()[0]["aigateway.parameters.json"])["gatewayName"] for _ in range(3)}
        self.assertEqual(len(names), 1)
        name = names.pop()
        self.assertRegex(name, r"^aigw-meternaut-[0-9a-f]{8}$")
        self.assertLessEqual(len(name), 24, "the service's limit")
        self.assertRegex(name, ep.AIGATEWAY_NAME.pattern)
        self.assertEqual(name, ep.aigateway_name(SETTINGS["ENV_SUBSCRIPTION_ID"], SETTINGS["ENV_RESOURCE_GROUP"]))
        self.assertEqual(name.rsplit("-", 1)[1], ep.digest(SETTINGS["ENV_SUBSCRIPTION_ID"], SETTINGS["ENV_RESOURCE_GROUP"]), "the same digest as every other name of the environment")
        self.assertNotEqual(name, ep.aigateway_name(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-other"))

    def test_the_model_account_is_the_one_the_foundry_file_makes_and_the_models_are_the_deployed_ones(self):
        files, outputs = self.files()
        gateway = values(files["aigateway.parameters.json"])
        foundry = values(files["foundry.parameters.json"])
        self.assertEqual(gateway["foundryAccountName"], foundry["accountName"], "the gateway calls the Foundry resource of the agents, not the model account of the gateway")
        self.assertEqual(gateway["foundryAccountName"], outputs["foundry_account_name"])
        self.assertEqual(gateway["models"], [{"name": m["name"], "version": m["version"]} for m in foundry["models"]], "the agents' deployments, in their order")
        self.assertEqual(outputs["aigateway_aliases"].split(), [m["name"] for m in gateway["models"]], "the alias is the name of the deployment, as the check and the agents send it")
        self.assertEqual((gateway["location"], gateway["owner"]), ("swedencentral", "owner@example.com"))

    def test_the_subnet_is_the_last_free_26_and_overlaps_none_of_the_other_four(self):
        files, outputs = self.files()
        env, operator, gateway = values(files["environment.parameters.json"]), values(files["operator.parameters.json"]), values(files["aigateway-subnet.parameters.json"])
        self.assertEqual(gateway["aigwSubnetPrefix"], "10.53.0.128/26")
        self.assertEqual(outputs["aigateway_subnet_prefix"], "10.53.0.128/26")
        mine = ipaddress.ip_network(gateway["aigwSubnetPrefix"])
        taken = [ipaddress.ip_network(env[name]) for name in ("peSubnetPrefix", "funcSubnetPrefix", "webSubnetPrefix")] + [ipaddress.ip_network(operator["opsSubnetPrefix"])]
        self.assertFalse(any(mine.overlaps(other) for other in taken))
        self.assertTrue(mine.subnet_of(ipaddress.ip_network(env["vnetAddressPrefix"])))
        self.assertGreaterEqual(mine.num_addresses, 32, "the service wants a /27 at least")
        # none of the other subnets moves: the picks of the four earlier subnets are the ones that they had before the gateway
        self.assertEqual((env["peSubnetPrefix"], env["funcSubnetPrefix"], env["webSubnetPrefix"], operator["opsSubnetPrefix"]),
                         ("10.53.0.0/27", "10.53.0.32/27", "10.53.0.224/27", "10.53.0.192/27"))

    def test_the_picker_prefers_a_26_takes_the_last_free_block_and_falls_back_to_a_27_and_to_none(self):
        net = ipaddress.ip_network
        four = tuple(net(prefix) for prefix in ("10.53.0.0/27", "10.53.0.32/27", "10.53.0.224/27", "10.53.0.192/27"))
        self.assertEqual(ep.aigw_subnet(net("10.53.0.0/24"), four), net("10.53.0.128/26"))
        self.assertEqual(ep.aigw_subnet(net("10.53.0.0/24"), four + (net("10.53.0.128/26"),)), net("10.53.0.64/26"), "the last free /26 that is left")
        self.assertEqual(ep.aigw_subnet(net("10.53.0.0/23"), four), net("10.53.1.192/26"), "the last /26 of a larger network, not the first")
        # no /26 free, a /27 free: the last one
        self.assertEqual(ep.aigw_subnet(net("10.53.0.0/24"), four + (net("10.53.0.64/26"), net("10.53.0.128/27"))), net("10.53.0.160/27"))
        # nothing free: no range, and no error, because the gateway is an optional service
        self.assertIsNone(ep.aigw_subnet(net("10.53.0.0/24"), four + (net("10.53.0.64/26"), net("10.53.0.128/26"))))
        self.assertIsNone(ep.aigw_subnet(net("10.53.0.0/27"), (net("10.53.0.0/28"),)))
        self.assertEqual(ep.AIGATEWAY_SUBNET_LENGTHS, (26, 27), "a /26 when the network can spare one, never smaller than a /27")

    def test_a_network_without_a_free_range_gets_no_file_and_no_error_and_the_other_files_stay_as_they_are(self):
        # a /25 holds four /27, and the four earlier subnets take them
        code, out, err, files = run({**SETTINGS, "ENV_VNET_PREFIX": "10.53.0.0/25"}, "--aigateway-policies", str(self.POLICIES))
        self.assertEqual((code, err), (0, ""))
        outputs = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual((outputs["aigateway_files"], outputs["aigateway_subnet_prefix"]), ("false", ""))
        self.assertFalse([name for name in files if "aigateway" in name])
        without = run({**SETTINGS, "ENV_VNET_PREFIX": "10.53.0.0/25"})[3]
        self.assertEqual(files, without, "every other file is the same with and without the gateway")

    def test_the_file_says_whether_the_subnet_is_there_already_and_says_no_when_nobody_has_looked(self):
        # the subnet is made once: a template that makes it again takes away the route table that the landing zone's network manager put on it
        self.assertIs(values(self.files()[0]["aigateway-subnet.parameters.json"])["aigwSubnetExists"], False)
        for given, expected in (("", False), ("false", False), ("FALSE", False), ("true", True), (" True ", True)):
            files, _ = self.files(ENV_AIGW_SUBNET_EXISTS=given)
            self.assertIs(values(files["aigateway-subnet.parameters.json"])["aigwSubnetExists"], expected, given)
            self.assertNotIn("aigwSubnetExists", values(files["aigateway.parameters.json"]), "the gateway's file does not carry it: the subnet is made, or left alone, before the gateway's template runs")
        for refused in ("yes", "1", "exists"):
            code, out, err, files = run({**SETTINGS, "ENV_AIGW_SUBNET_EXISTS": refused}, "--aigateway-policies", str(self.POLICIES))
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("ENV_AIGW_SUBNET_EXISTS is true or false", err)
        self.assertIn("param aigwSubnetExists bool = false", self.SUBNET_TEMPLATE)

    def test_the_principal_of_the_foundry_project_is_empty_until_step_two_gives_it_and_is_checked_as_an_object_id(self):
        self.assertEqual(values(self.files()[0]["aigateway.parameters.json"])["foundryProjectPrincipalId"], "", "the template works without it")
        files, _ = self.files(FOUNDRY_PROJECT_PRINCIPAL_ID="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")
        self.assertEqual(values(files["aigateway.parameters.json"])["foundryProjectPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        for refused in ("not-a-guid", "12345678-1234-1234-1234-12345678901", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee,aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"):
            code, out, err, files = run({**SETTINGS, "FOUNDRY_PROJECT_PRINCIPAL_ID": refused}, "--aigateway-policies", str(self.POLICIES))
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("FOUNDRY_PROJECT_PRINCIPAL_ID", err)
            self.assertNotIn(refused, err, "a value that is not an object id is not echoed")

    def test_two_models_whose_resource_names_would_be_the_same_are_refused_and_so_is_a_name_the_service_cannot_take(self):
        base = json.loads(MODELS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            for names, expected in ((("gpt-6.1-sol", "gpt-6-1-sol"), "no two are the same"), (("gpt-6.1-sol", "ab"), "3 to 63")):
                models = [{**base[0], "name": names[0]}, {**base[1], "name": names[1]}]
                path = Path(tmp) / "models.json"
                path.write_text(json.dumps(models), encoding="utf-8")
                code, out, err, files = run(SETTINGS, "--aigateway-policies", str(self.POLICIES), models=path)
                self.assertEqual((code, out, files), (2, "", {}), names)
                self.assertIn(expected, err)

    def test_the_policy_file_of_the_repository_holds_the_three_kinds_with_the_numbers_of_the_plan(self):
        policies = self.policies()
        by_kind = {}
        for policy in policies:
            by_kind.setdefault(policy["type"], []).append(policy)
        self.assertEqual(sorted(by_kind), ["costLimit", "requestRateLimit", "tokenLimit"], "no ipFilter or cors policy: the file has no values for them, and the Foundry Agent Service has no address range to allow")
        for policy in policies:
            self.assertEqual((policy["counterKey"], policy["scope"]), (["identity"], "workspace"), "each caller has its own counter, across all models")
        (token,) = by_kind["tokenLimit"]
        agent_rates = [m["agentCapacity"] * 1000 for m in json.loads(MODELS.read_text(encoding="utf-8"))]
        self.assertEqual((token["period"], token["count"]), ("minute", max(agent_rates)), "a minute's tokens of the deployment that the Investigator uses, the largest of the agents'")
        self.assertEqual({(c["period"], c["amount"]) for c in by_kind["costLimit"]}, {("day", 5), ("month", 25)}, "the owner's standing limit: 5 a day and 25 in total")
        self.assertEqual(len({c["id"] for c in by_kind["costLimit"]}), 2, "each cost limit keeps its own stable id")

    def test_the_numbers_of_the_standing_limit_in_the_builder_are_the_ones_of_agents_md(self):
        rule = re.search(r"\*\*\(g\) Standing limits\*\*.*", self.AGENTS).group(0)
        total, daily = re.search(r"at most (\d+) EUR in total and (\d+) EUR a day", rule).groups()
        self.assertEqual(ep.AIGATEWAY_COST_CEILING_USD, {"hour": int(daily), "day": int(daily), "week": int(total), "month": int(total), "year": int(total)})

    def test_a_policy_file_that_breaks_the_plan_is_refused_by_name_and_nothing_is_written(self):
        good = self.policies()

        def changed(index, **changes):
            document = json.loads(json.dumps(good))
            document[index].update(changes)
            return document

        def without(key, index):
            document = json.loads(json.dumps(good))
            del document[index][key]
            return document

        cases = {
            "an ipFilter policy, which has no values here": ([*good, {"type": "ipFilter", "action": "Allow", "cidrRanges": ["10.0.0.0/8"]}], "a gateway-wide policy is one of"),
            "a key that nothing here has seen": (changed(0, payloadCapture=False), "a tokenLimit policy has exactly"),
            "a missing key": (without("scope", 1), "a requestRateLimit policy has exactly"),
            "a counter for all callers together": (changed(0, counterKey=[]), 'counterKey of a tokenLimit policy is ["identity"]'),
            "a counter for the address": (changed(1, counterKey=["ipAddress"]), 'counterKey of a requestRateLimit policy is ["identity"]'),
            "a scope that is one model": (changed(2, scope="resource"), "scope of a costLimit policy is workspace"),
            "a token period that is not offered": (changed(0, period="week"), "period of the token limit is one of"),
            "a token limit above the deployments' rate": (changed(0, count=50001), "count of the token limit is a whole number from 1 to 50000"),
            "a token limit of nothing": (changed(0, count=0), "count of the token limit"),
            "a token count that is a text": (changed(0, count="50000"), "count of the token limit"),
            "a token count that is a switch": (changed(0, count=True), "count of the token limit"),
            "a rate of nothing": (changed(1, callsPerPeriod=0), "request rate limit is callsPerPeriod from 1 to 1000"),
            "a rate window of a day": (changed(1, periodSeconds=86400), "request rate limit is callsPerPeriod from 1 to 1000"),
            "a daily cost above the daily limit": (changed(2, amount=5.01), "cost limit for a day is a number above 0 and at most 5"),
            "a monthly cost above the total": (changed(3, amount=26), "cost limit for a month is a number above 0 and at most 25"),
            "a cost of nothing": (changed(3, amount=0), "above 0"),
            "a cost that is a text": (changed(3, amount="25"), "above 0"),
            "a cost that is a switch": (changed(3, amount=True), "above 0"),
            "a cost period that is not offered": (changed(3, period="fortnight"), "own period"),
            "two cost limits of the same period": (changed(3, period="day", amount=4), "own period"),
            "two cost limits with the same id": (changed(3, id="meternaut-day"), "own stable id"),
            "an id that starts with a hyphen": (changed(3, id="-month"), "own stable id"),
            "an id that ends with a hyphen": (changed(3, id="month-"), "own stable id"),
            "an id with a space": (changed(3, id="the month"), "own stable id"),
            "a second token limit": ([*good, changed(0, count=1000)[0]], "one tokenLimit policy at most"),
            "no cost limit at all": (good[:2], "costLimit is missing"),
            "no token limit": (good[1:], "tokenLimit is missing"),
            "no request rate limit": ([good[0], *good[2:]], "requestRateLimit is missing"),
            "an empty list": ([], "a list of 1 to 8 policies"),
            "an object and not a list": ({"type": "tokenLimit"}, "a list of 1 to 8 policies"),
            "text that is not JSON": ("[", "not a readable JSON list"),
            "a policy that is a text": (["tokenLimit"], "a gateway-wide policy is one of"),
        }
        for what, (document, expected) in cases.items():
            code, out, err, files = self.with_policies(document)
            self.assertEqual((code, out, files), (2, "", {}), what)
            self.assertIn(expected, err, what)

    def test_a_policy_file_that_is_not_there_is_refused_and_a_larger_agent_capacity_raises_the_ceiling_of_the_token_limit(self):
        code, out, err, files = run(SETTINGS, "--aigateway-policies", str(ROOT / "environment" / "aigateway" / "no-such-file.json"))
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("not a readable JSON list of policies", err)
        base = json.loads(MODELS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(json.dumps([{**base[0]}, {**base[1], "agentCapacity": 80}]), encoding="utf-8")
            policies = self.policies()
            policies[0]["count"] = 80000
            policy_path = Path(tmp) / "policies.json"
            policy_path.write_text(json.dumps(policies), encoding="utf-8")
            code, out, err, files = run(SETTINGS, "--aigateway-policies", str(policy_path), models=path)
            self.assertEqual((code, err), (0, ""), "the ceiling follows models.json")
            self.assertEqual(files["aigateway-policies.json"][0]["count"], 80000)

    def test_nothing_secret_is_in_any_of_the_three_files(self):
        files, _ = self.files(FOUNDRY_PROJECT_PRINCIPAL_ID="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        text = json.dumps([files["aigateway-subnet.parameters.json"], files["aigateway.parameters.json"], files["aigateway-policies.json"]]).lower()
        for word in ("secret", "password", "connectionstring", "apikey", "api-key", "instrumentationkey", "bearer"):
            self.assertNotIn(word, text, word)

    def test_the_names_the_workflow_reads_are_the_ones_the_template_makes(self):
        _, outputs = self.files()
        self.assertEqual(outputs["aigateway_subnet_name"], "snet-aigw")
        for template in (self.TEMPLATE, self.SUBNET_TEMPLATE):
            self.assertIn("var aigwSubnetName = 'snet-aigw'", template, "the subnet's template makes it, and the gateway's names it")
            self.assertIn("param workload string = 'meternaut'", template)
            self.assertIn("var virtualNetworkName = 'vnet-${workload}'", template)
        self.assertIn("var operatorIdentityName = 'id-${workload}-operator'", self.TEMPLATE)
        self.assertIn("name: 'id-${workload}-operator'", Operator.OPERATOR, "the identity that the gateway's template reads is the one that the Operator's makes")
        self.assertIn("name: 'vnet-${workload}'", BICEP, "the virtual network that the model side makes")


class PublicNetworkAccessOfTheApps(unittest.TestCase):
    """What each function app takes from the public internet is one value each (docs/proposals/07-private-by-default.md, phase 1): written to its parameter file every time, so that the property is never
    left unset, which would let the first private endpoint switch public access off by itself."""

    RECORDING_TEMPLATE = (ROOT / "environment" / "recording" / "main.bicep").read_text(encoding="utf-8")
    CASES_TEMPLATE = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")

    def build(self, **changes):
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "contract.json"
            contract.write_text(CONTRACT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            return run({**SETTINGS, **changes}, "--contract", str(contract), "--contract-policy", str(POLICY_FILE))

    def test_the_usage_app_is_closed_and_the_cases_app_is_open_until_the_people_have_a_path_and_the_values_reach_their_parameter_files(self):
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((ep.USAGE_APP_PUBLIC_NETWORK_ACCESS, ep.CASES_APP_PUBLIC_NETWORK_ACCESS), ("Disabled", "Enabled"),
                         "the usage app has no page for people and its code is published through its private endpoint, so it is closed; the cases app serves the console and stays open until the people who "
                         "approve have a network path to it (the owner's decision): that is the one value and the one test to change then")
        self.assertEqual(values(files["recording.parameters.json"])["usageAppPublicNetworkAccess"], "Disabled")
        self.assertEqual(values(files["cases.parameters.json"])["casesAppPublicNetworkAccess"], "Enabled")
        for name, document in files.items():
            if name not in ("recording.parameters.json", "cases.parameters.json"):
                self.assertFalse({"usageAppPublicNetworkAccess", "casesAppPublicNetworkAccess"} & set(document["parameters"]), f"{name}: the value reaches the file of its own app only")

    def test_closing_an_app_is_one_value_and_it_reaches_only_that_app(self):
        # A closed cases app needs the console's host name on the platform's Application Gateway: without it the build is refused (the next test), so the host name is given here.
        for usage, cases in (("Disabled", "Enabled"), ("Enabled", "Disabled"), ("Disabled", "Disabled"), ("Enabled", "Enabled")):
            with mock.patch.object(ep, "USAGE_APP_PUBLIC_NETWORK_ACCESS", usage), mock.patch.object(ep, "CASES_APP_PUBLIC_NETWORK_ACCESS", cases):
                code, _, err, files = self.build(CONSOLE_HOST_NAME="console.example.com")
            self.assertEqual((code, err), (0, ""), (usage, cases))
            self.assertEqual(values(files["recording.parameters.json"])["usageAppPublicNetworkAccess"], usage, (usage, cases))
            self.assertEqual(values(files["cases.parameters.json"])["casesAppPublicNetworkAccess"], cases, (usage, cases))

    def test_a_value_that_is_not_enabled_or_disabled_is_refused_by_name_because_the_property_must_always_be_written(self):
        for constant in ("USAGE_APP_PUBLIC_NETWORK_ACCESS", "CASES_APP_PUBLIC_NETWORK_ACCESS"):
            for bad in ("", "enabled", "Allow", "SecuredByPerimeter"):
                with mock.patch.object(ep, constant, bad):
                    code, out, err, files = self.build()
                self.assertEqual((code, out, files), (2, "", {}), (constant, bad))
                self.assertIn(f"{constant} (in tools/environment-params.py) is Enabled or Disabled", err)

    def test_each_template_takes_the_value_with_the_same_two_choices_and_the_default_that_the_files_carry(self):
        for source, name in ((self.RECORDING_TEMPLATE, "usageAppPublicNetworkAccess"), (self.CASES_TEMPLATE, "casesAppPublicNetworkAccess")):
            self.assertRegex(source, rf"(?m)^@allowed\(\[\n  'Enabled'\n  'Disabled'\n\]\)\nparam {name} string = 'Enabled'$", name)
            self.assertEqual(bicep_params(source)[name], ("string", True), "it has a default: a file that leaves it out still gives the property a value")
            self.assertIn(f"    publicNetworkAccess: {name}\n", source, "the app takes the parameter, and nothing else gives the property a value")
        self.assertEqual(ep.PUBLIC_NETWORK_ACCESS, ("Enabled", "Disabled"))

    def test_the_endpoint_of_each_app_is_in_the_list_that_its_action_waits_for_with_the_zone_of_app_service_and_the_name_that_its_template_gives_it(self):
        # The first `recording` after the usage app's endpoint was made failed at the publish: a Flex Consumption deployment ends with a call from the deployment site to the app's own host name,
        # and while the central zone had no record of the new endpoint that name did not resolve ("Reset all workers endpoint responded with Name or service not known"). A list without the
        # app's endpoint lets the workflow publish too early, so it is pinned here for both apps.
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        lines = dict(line.split("=", 1) for line in out.splitlines())
        usage, cases = values(files["recording.parameters.json"])["functionAppName"], values(files["cases.parameters.json"])["functionAppName"]
        waited = lines["recording_endpoints"].split(",")
        self.assertEqual(len(waited), 6, "the five endpoints of the services and the usage app's own")
        self.assertIn(f"pe-{usage}:privatelink.azurewebsites.net", waited)
        self.assertEqual(lines["cases_endpoints"], f"pe-{cases}:privatelink.azurewebsites.net", "the cases app has one endpoint, and its action waits for it")
        self.assertEqual(ep.APP_ENDPOINT_ZONE, "privatelink.azurewebsites.net", "the central zone of App Service: the names of the app and of its deployment site")
        self.assertNotIn(cases, lines["recording_endpoints"], "each action waits for the endpoints that it makes")
        self.assertNotIn(usage, lines["cases_endpoints"])
        for name, source in ((usage, self.RECORDING_TEMPLATE), (cases, self.CASES_TEMPLATE)):
            self.assertIn("name: 'pe-${functionAppName}'", source, "the name that the workflow looks for is the name that the template gives the endpoint")
            self.assertIn("'sites'", source)
    TEMPLATE = {"parameters": {"a": {"type": "string"}, "b": {"type": "int", "defaultValue": 1}, "c": {"type": "array", "defaultValue": []}, "d": {"type": "bool", "defaultValue": True}}}

    def doc(self, **given):
        return {"parameters": {k: {"value": v} for k, v in given.items()}}

    def test_a_fitting_file_has_no_problems(self):
        self.assertEqual(ep.check_against(self.doc(a="x", b=2, c=[], d=False), self.TEMPLATE, "t"), [])

    def test_an_unknown_name_a_wrong_type_and_a_missing_required_one_are_found(self):
        problems = ep.check_against(self.doc(z=1), self.TEMPLATE, "t")
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("z is not a parameter" in p for p in problems))
        self.assertTrue(any("a has no default" in p for p in problems))
        self.assertTrue(ep.check_against(self.doc(a=1), self.TEMPLATE, "t"))
        self.assertTrue(ep.check_against(self.doc(a="x", b=True), self.TEMPLATE, "t"))
        self.assertTrue(ep.check_against(self.doc(a="x", c={}), self.TEMPLATE, "t"))


if __name__ == "__main__":
    unittest.main()
