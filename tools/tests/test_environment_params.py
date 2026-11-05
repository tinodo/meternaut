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
    "RECORDING_DEPLOYER_ID": "99999999-8888-7777-6666-555555555555",
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
        self.assertEqual(set(files), {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json", "recording.parameters.json", "planted.parameters.json"})
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

    def test_the_gateway_the_workflow_and_the_readers_reach_the_template(self):
        files, outputs = self.files(RECORDING_READER_IDS=f"{READER.upper()}")
        recording = values(files["recording.parameters.json"])
        self.assertEqual(recording["gatewayPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(recording["gatewayAppInsightsSubscriptionId"], "66666666-7777-8888-9999-000000000000")
        self.assertEqual((recording["gatewayAppInsightsResourceGroup"], recording["gatewayAppInsightsName"]), ("rg-gateway", "example-insights"))
        self.assertEqual(recording["workflowPrincipalId"], SETTINGS["RECORDING_DEPLOYER_ID"])
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

    def test_the_endpoint_subnet_holds_the_six_private_endpoints(self):
        # six endpoints and the five addresses that Azure keeps: a /29 has eight addresses and cannot hold them
        code, out, err, files = run({**SETTINGS, "ENV_PE_SUBNET_PREFIX": "10.53.0.0/29"})
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("ENV_PE_SUBNET_PREFIX", err)
        self.assertIn("at least a /28", err)
        self.assertEqual(run({**SETTINGS, "ENV_PE_SUBNET_PREFIX": "10.53.0.0/28"})[0], 0)

    def test_the_private_endpoints_and_their_zones_are_the_ones_the_template_makes(self):
        _, outputs = self.files()
        pairs = [pair.split(":") for pair in outputs["recording_endpoints"].split(",")]
        self.assertEqual(len(pairs), 5)
        storage, cosmos, hubs = outputs["storage_account_name"], outputs["cosmos_account_name"], outputs["event_hub_namespace"]
        self.assertEqual(pairs, [[f"pe-{storage}-blob", "privatelink.blob.core.windows.net"], [f"pe-{storage}-queue", "privatelink.queue.core.windows.net"],
                                 [f"pe-{storage}-table", "privatelink.table.core.windows.net"], [f"pe-{cosmos}", "privatelink.documents.azure.com"],
                                 [f"pe-{hubs}", "privatelink.servicebus.windows.net"]])
        for line in ("name: 'pe-${storageAccountName}-${service}'", "name: 'pe-${cosmosAccountName}'", "name: 'pe-${eventHubNamespaceName}'"):
            self.assertIn(line, RECORDING)
        self.assertEqual((outputs["usage_identity_name"], outputs["appinsights_name"]), ("id-meternaut-usage", "appi-meternaut"))
        self.assertIn("name: 'id-${workload}-usage'", RECORDING)
        self.assertIn("name: 'appi-${workload}'", RECORDING)

    def test_the_deployer_and_the_readers_must_be_object_ids(self):
        for changes in ({"RECORDING_DEPLOYER_ID": "me"}, {"RECORDING_READER_IDS": "not-an-id"}, {"RECORDING_READER_IDS": f"{READER},"},
                        {"RECORDING_READER_IDS": f"{READER},{READER.upper()}"}, {"RECORDING_READER_IDS": ",".join([READER[:-1] + str(i) for i in range(6)])}):
            code, out, err, files = run({**SETTINGS, **changes})
            self.assertEqual((code, out, files), (2, "", {}), changes)
            self.assertIn("RECORDING_", err)
            self.assertNotIn("not-an-id", err)


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
        return {"name": "gpt-6-luna", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "retirementDate": "2028-03-11", **changes}

    def test_the_models_of_the_repository_are_valid(self):
        self.assertEqual(run(SETTINGS)[0], 0)

    def test_bad_models_are_refused(self):
        for bad in ([], "x", [1], [{"name": "x"}], [self.good(name="Has Space")], [self.good(name="gpt;x")], [self.good(version="latest")],
                    [self.good(sku="Standard")], [self.good(capacity=0)], [self.good(capacity=True)], [self.good(capacity="20")],
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
        self.assertEqual(set(files), {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json", "recording.parameters.json", "contract.parameters.json", "cases.parameters.json",
                                      "planted.parameters.json"})
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
        models = [{"name": "big", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "retirementDate": "2028-03-11"},
                  {"name": "also-big", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "retirementDate": "2028-03-11"},
                  {"name": "small", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 5, "retirementDate": "2028-03-11"}]
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
    """The parameter file of the first cases app (environment/cases/main.bicep): it names what the usage recording made, and the contract's key."""

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

    def test_it_names_the_storage_the_namespace_and_the_workflow_that_the_recording_has(self):
        files, lines = self.build()
        cases, recording = values(files["cases.parameters.json"]), values(files["recording.parameters.json"])
        self.assertEqual(cases["storageAccountName"], recording["storageAccountName"])
        self.assertEqual(cases["eventHubNamespaceName"], recording["eventHubNamespaceName"])
        self.assertEqual(cases["workflowPrincipalId"], recording["workflowPrincipalId"])
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

    def test_it_reads_the_pilot_subscription_and_the_gateway_with_the_contracts_key(self):
        files, lines = self.build()
        cases = values(files["cases.parameters.json"])
        self.assertEqual(cases["scopeSubscriptions"], SETTINGS["ENV_SUBSCRIPTION_ID"])
        self.assertEqual(cases["gatewayUrl"], "https://example-apim.azure-api.net")
        self.assertEqual(lines["gateway_url"], cases["gatewayUrl"])
        self.assertEqual(cases["gatewayProductSubscriptionId"], SETTINGS["GATEWAY_RESOURCE_ID"] + "/subscriptions/meternaut-agents-sub-01")
        contract = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(cases["modelDetective"], contract["allowedModels"][0])
        self.assertEqual(cases["modelSkeptic"], contract["allowedModels"][1], "the Skeptic is another model than the Detective, so that it is more independent")
        self.assertNotEqual(cases["modelDetective"], cases["modelSkeptic"])

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

    def test_the_hub_and_the_identity_are_the_ones_the_template_makes(self):
        _, lines = self.build()
        self.assertIn("var controlHubName = '" + lines["cases_hub_name"] + "'", self.CASES)
        self.assertIn("name: 'id-${workload}-cases'", self.CASES)
        self.assertEqual(lines["cases_identity_name"], "id-meternaut-cases")

    def test_without_a_contract_there_is_no_cases_file(self):
        self.assertNotIn("cases.parameters.json", run(SETTINGS)[3])

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


class CheckAgainst(unittest.TestCase):
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
