import importlib.util
import io
import ipaddress
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "environment-params.py"
spec = importlib.util.spec_from_file_location("environment_params", TOOL)
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

MODELS = ROOT / "environment" / "models.json"
BICEP = (ROOT / "environment" / "main.bicep").read_text(encoding="utf-8")
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
}
READER = "12345678-1234-1234-1234-123456789012"
# The settings of the retired actions that touched the owner's API Management instance (the owner ordered the undo of what Meternaut had added to it, 2026-11-07), and of the usage recording that
# copied the calls through it (removed the same day, with the old model account): nothing reads them any more.
RETIRED_SETTINGS = {
    "GATEWAY_RESOURCE_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg-gateway/providers/Microsoft.ApiManagement/service/example-apim",
    "GATEWAY_APPINSIGHTS_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg-gateway/providers/microsoft.insights/components/example-insights",
    "GATEWAY_PRINCIPAL_ID": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
    "GATEWAY_CLIENT_ID": "BBBBBBBB-1111-2222-3333-CCCCCCCCCCCC",
    "RECORDING_FRAGMENTS": "true",
    "RECORDING_READER_IDS": READER,
}
BASE = (ROOT / "environment" / "base" / "main.bicep").read_text(encoding="utf-8")


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
    def test_good_settings_give_six_files_and_the_outputs(self):
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(set(files), {"environment.parameters.json", "base.parameters.json", "foundry.parameters.json", "operator.parameters.json", "planted.parameters.json",
                                      "cases.parameters.json"})
        env = values(files["environment.parameters.json"])
        self.assertEqual(env["vnetAddressPrefix"], "10.53.0.0/24")
        self.assertEqual(env["peSubnetPrefix"], "10.53.0.0/27")
        self.assertEqual(env["dnsServers"], ["10.20.0.4"])
        self.assertNotIn("gatewayPrincipalId", env, "the model side makes no role for any gateway identity")
        self.assertEqual(env["budgetStartDate"], "2026-11-01")
        self.assertFalse({"models", "accountName"} & set(env), "the model side makes the network and the budget: the old model account was removed on 2026-11-07, and the models are those of the Foundry resource")
        self.assertEqual(set(env), {"location", "vnetAddressPrefix", "networkExists", "peSubnetPrefix", "funcSubnetPrefix", "webSubnetPrefix", "dnsServers", "owner", "budgetAmount", "alertEmails",
                                    "budgetStartDate"})
        lines = dict(line.split("=", 1) for line in out.splitlines())
        for retired in ("account_name", "private_endpoint", "endpoint", "gateway_name", "gateway_subscription", "gateway_resource_group", "identity_name", "principal_known"):
            self.assertNotIn(retired, lines, retired)

    def test_the_old_model_account_has_no_name_in_the_builder_and_the_foundry_resource_is_another_account(self):
        # tools/retire-old.py names the old account by the same digest, to delete it (a test there holds the two together); nothing in the builder makes or names it.
        text = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("def account_name", text)
        self.assertNotIn("aif-meternaut-{", text.replace("aif-meternaut-agents-{", ""))
        self.assertNotIn("restoreAccount", text)

    def test_the_environment_file_matches_the_parameters_of_the_template(self):
        declared = bicep_params(BICEP)
        given = run(SETTINGS)[3]["environment.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)
        for retired in ("restoreAccount", "models", "accountName", "gatewayPrincipalId"):
            self.assertNotIn(retired, declared, f"{retired}: it served the old model account, which the template does not make any more")

    def test_nothing_of_the_owners_api_management_instance_reaches_a_file_or_an_output(self):
        # The owner ordered the undo of what Meternaut had added to his instance (2026-11-07): the builder makes no file for it, names no object of it and reads no setting that names it.
        code, out, err, files = run({**SETTINGS, **RETIRED_SETTINGS})
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(files, run(SETTINGS)[3], "a leftover setting of the retired actions changes no file")
        self.assertEqual(out, run(SETTINGS)[1], "and no output")
        for name in ("logger.parameters.json", "eventhub-loggers.parameters.json", "kit.parameters.json", "contract.parameters.json"):
            self.assertNotIn(name, files, name)
        text = (out + json.dumps(files)).lower()
        for word in ("example-apim", "apim", "microsoft.apimanagement/service", "contract", "usage-eventhub-logger"):
            self.assertNotIn(word, text, word)
        self.assertNotIn("GATEWAY_RESOURCE_ID", TOOL.read_text(encoding="utf-8"), "the instance's resource id is not a setting of the builder any more")

    def test_the_options_of_the_retired_contract_are_gone(self):
        for option in ("--contract", "--contract-policy"):
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit) as stopped:
                ep.main(["build", "--models", str(MODELS), "--out-dir", ".", option, "x"], environ=SETTINGS)
            self.assertEqual(stopped.exception.code, 2, option)
            self.assertIn("unrecognized arguments", err.getvalue(), option)

    def test_the_names_the_workflow_removes_are_the_ones_the_template_gives(self):
        lines = dict(line.split("=", 1) for line in run(SETTINGS)[1].splitlines())
        self.assertNotIn("pe-${accountName}", BICEP, "the old model account's private endpoint is not made any more: the action retire-old deletes what is left of it")
        self.assertIn("param workload string = 'meternaut'", BICEP)
        self.assertIn("name: 'vnet-${workload}'", BICEP)
        self.assertIn("name: 'nsg-${workload}-pe'", BICEP)
        self.assertEqual((lines["vnet_name"], lines["nsg_name"]), ("vnet-meternaut", "nsg-meternaut-pe"))

    def test_the_budget_keeps_the_start_date_it_was_given(self):
        self.assertNotIn("utcNow", BICEP)
        self.assertIn("startDate: budgetStartDate", BICEP)
        again = run({**SETTINGS, "ENV_BUDGET_START": "2027-02-01"})[3]["environment.parameters.json"]
        self.assertEqual(values(again)["budgetStartDate"], "2027-02-01")


class Base(unittest.TestCase):
    """The parameter file of the base (environment/base/main.bicep: the workspace, Application Insights and the storage account), and the name that it gives to the service whose name is a host name."""

    def files(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual((code, err), (0, ""))
        return files, dict(line.split("=", 1) for line in out.splitlines())

    def test_the_file_matches_the_parameters_of_the_template(self):
        declared = bicep_params(BASE)
        files, _ = self.files()
        given = files["base.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= set(given), required - set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)

    def test_the_file_holds_the_storage_name_the_region_and_the_owner_and_nothing_of_the_usage_recording_or_the_event_hubs_namespace(self):
        files, outputs = self.files()
        base = values(files["base.parameters.json"])
        self.assertEqual(set(base), {"location", "owner", "storageAccountName"} | ({"otlpIngestion"} if ep.GATEWAY_TELEMETRY else set()),
                         "the gateway's telemetry is the one thing that the base was given after the usage recording went (docs/proposals/10-ai-security-and-governance.md)")
        self.assertEqual((base["location"], base["owner"]), ("swedencentral", "owner@example.com"))
        self.assertEqual(base["storageAccountName"], outputs["storage_account_name"])
        self.assertNotIn("eventHubNamespaceName", bicep_params(BASE), "the base makes no Event Hubs namespace: the control message goes through a queue in the storage account")
        self.assertFalse({"event_hub_namespace", "cases_hub_name"} & set(outputs), "no output names an Event Hubs namespace or a control hub")
        for old in ("functionAppName", "cosmosAccountName", "dataReaderPrincipalIds", "gatewayAppInsightsName", "gatewayAppInsightsResourceGroup", "gatewayAppInsightsSubscriptionId",
                    "usageAppPublicNetworkAccess", "gatewayPrincipalId", "workflowPrincipalId", "logicAppName", "dataContributorPrincipalIds"):
            self.assertNotIn(old, base, old)
            self.assertNotIn(old, bicep_params(BASE), f"{old}: the template does not take it")
        self.assertFalse({"cosmos_account_name", "function_app_name", "recording_endpoints"} & set(outputs), "no output names the Cosmos DB account or the usage app")

    def test_a_leftover_setting_of_the_usage_recording_is_not_read_and_not_checked(self):
        # RECORDING_READER_IDS named the people who read the usage store; GATEWAY_APPINSIGHTS_ID the old gateway's Application Insights, which the copy jobs read. Nothing reads them any more.
        plain = run(SETTINGS)
        for leftover in ({"RECORDING_READER_IDS": READER}, {"RECORDING_READER_IDS": "not-an-id"}, {"GATEWAY_APPINSIGHTS_ID": RETIRED_SETTINGS["GATEWAY_APPINSIGHTS_ID"]},
                         {"GATEWAY_APPINSIGHTS_ID": "not-an-id"}):
            code, out, err, files = run({**SETTINGS, **leftover})
            self.assertEqual((code, err), (0, ""), leftover)
            self.assertEqual((out, files), (plain[1], plain[3]), f"{leftover}: nothing changes")
        text = TOOL.read_text(encoding="utf-8")
        for name in ("RECORDING_READER_IDS", "GATEWAY_APPINSIGHTS_ID", "GATEWAY_RESOURCE_ID"):
            self.assertNotIn(f'"{name}"', text, f"{name} is not a setting of the builder any more")

    def test_the_names_are_host_names_inside_their_limits_and_the_same_on_every_run(self):
        _, first = self.files()
        _, second = self.files()
        for key, pattern, longest in (("storage_account_name", r"^[a-z0-9]{3,24}$", 24), ("cases_function_app_name", r"^[A-Za-z0-9][A-Za-z0-9-]{1,59}$", 60)):
            self.assertRegex(first[key], pattern, key)
            self.assertLessEqual(len(first[key]), longest, key)
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(len({first[k] for k in ("storage_account_name", "cases_function_app_name")}), 2)
        self.assertNotIn("logic_app_name", first)

    def test_the_names_differ_per_subscription_and_group_and_ignore_case(self):
        base = ep.base_names(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-a")
        self.assertNotEqual(base, ep.base_names(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-b"))
        self.assertNotEqual(base, ep.base_names("99999999-2222-3333-4444-555555555555", "rg-a"))
        self.assertEqual(base, ep.base_names(SETTINGS["ENV_SUBSCRIPTION_ID"].upper(), "RG-A"))
        self.assertTrue(base["storage_account_name"].endswith(ep.digest(SETTINGS["ENV_SUBSCRIPTION_ID"], "rg-a")))

    def test_the_old_key_based_version_and_its_four_names_are_gone_from_the_builder(self):
        _, outputs = self.files()
        self.assertEqual([key for key in outputs if key.startswith("legacy_")], [], "the workflow removed the key-based Logic App version by its four names until 2026-11-07; the action retire-old does not need them")
        text = TOOL.read_text(encoding="utf-8")
        for old in ("logic-meternaut-usage", "asp-meternaut-usage", "azuremonitorlogs"):
            self.assertNotIn(old, text, old)

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

    def test_the_endpoint_subnet_holds_the_five_private_endpoints(self):
        # five endpoints (the base's three, the Foundry resource's and the cases app's) and the five addresses that Azure keeps: a /29 has eight addresses and cannot hold them, and a /28 has sixteen
        code, out, err, files = run({**SETTINGS, "ENV_PE_SUBNET_PREFIX": "10.53.0.0/29"})
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("ENV_PE_SUBNET_PREFIX", err)
        self.assertIn("at least a /28", err)
        self.assertIn("the base has three private endpoints (the storage account's)", err)
        self.assertIn("the Foundry resource one and the cases app one", err)
        self.assertEqual(run({**SETTINGS, "ENV_PE_SUBNET_PREFIX": "10.53.0.0/28"})[0], 0)

    def test_the_private_endpoints_and_their_zones_are_the_ones_the_template_makes(self):
        _, outputs = self.files()
        pairs = [pair.split(":") for pair in outputs["base_endpoints"].split(",")]
        self.assertEqual(len(pairs), 3)
        storage = outputs["storage_account_name"]
        self.assertEqual(pairs, [[f"pe-{storage}-blob", "privatelink.blob.core.windows.net"], [f"pe-{storage}-queue", "privatelink.queue.core.windows.net"],
                                 [f"pe-{storage}-table", "privatelink.table.core.windows.net"]])
        self.assertIn("name: 'pe-${storageAccountName}-${service}'", BASE)
        self.assertNotIn("privateEndpoints", BASE.replace("storageEndpoints 'Microsoft.Network/privateEndpoints", ""), "the base makes the storage account's three endpoints and no other")
        self.assertNotIn("servicebus", " ".join(outputs["base_endpoints"].split(",")), "no endpoint for an Event Hubs namespace")
        self.assertEqual(outputs["appinsights_name"], "appi-meternaut")
        for gone in ("pe-${cosmosAccountName}", "pe-${functionAppName}", "id-${workload}-usage", "pe-${eventHubNamespaceName}"):
            self.assertNotIn(gone, BASE, f"{gone}: the usage recording's pieces and the namespace's endpoint are not made any more")
        self.assertIn("name: 'appi-${workload}'", BASE)

    def test_the_identity_of_the_workflow_is_no_setting_of_the_builder_and_no_file_carries_it(self):
        # It used to get the right to send to the control hub of each of the two apps (the parameter workflowPrincipalId of both templates); the Operator puts the control message in the queue now, and the
        # workflow reads its own object id from its token only to look at the condition of its right to assign roles before it makes the AI Gateway.
        self.assertNotIn("RECORDING_DEPLOYER_ID", SETTINGS)
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("RECORDING_DEPLOYER_ID", TOOL.read_text(encoding="utf-8"))
        for name, document in files.items():
            self.assertNotIn("workflowPrincipalId", document["parameters"], name)
        code, out, err, files = run({**SETTINGS, "RECORDING_DEPLOYER_ID": "me"})
        self.assertEqual((code, err), (0, ""), "a leftover setting is not read, so a wrong value cannot stop a run")
        for name, document in files.items():
            self.assertNotIn("workflowPrincipalId", document["parameters"], name)


class Preview(unittest.TestCase):
    """The flag --preview is for the facts that are not known yet (the AI Gateway's host name and its project's identity): there is no gateway identity to wait for any more."""

    def test_the_flag_changes_no_file_and_no_output_while_the_agents_do_not_go_through_the_ai_gateway(self):
        # The way back (the constant set to False): the constant is True in the repository, so the test sets it.
        with mock.patch.object(ep, "AGENTS_VIA_AI_GATEWAY", False):
            plain, preview = run(SETTINGS), run(SETTINGS, "--preview")
        self.assertEqual((plain[0], plain[2]), (0, ""))
        self.assertEqual(preview[0:3], plain[0:3])
        self.assertEqual(preview[3], plain[3])

    def test_the_flag_changes_nothing_with_the_agents_route_on_while_no_action_needs_the_host_or_the_identity(self):
        # With no ACTION nothing asks for the host or for the project's identity, so a preview and a plain run are the same with the constant True too (the actions that do ask are in
        # test_aigateway_agents_params.py).
        self.assertIs(ep.AGENTS_VIA_AI_GATEWAY, True)
        plain, preview = run(SETTINGS), run(SETTINGS, "--preview")
        self.assertEqual((plain[0], plain[2]), (0, ""))
        self.assertEqual(preview[0:3], plain[0:3])
        self.assertEqual(preview[3], plain[3])

    def test_no_gateway_identity_is_needed_by_any_run_and_the_base_makes_no_role_for_one(self):
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""), "no setting names a gateway identity, and a run needs none")
        base = (TOOL.parents[1] / "environment" / "base" / "main.bicep").read_text(encoding="utf-8")
        self.assertNotIn("gatewayPrincipalId", base)
        self.assertNotIn("noGatewayIdentity", base)
        self.assertNotIn("gatewaySends", base)
        self.assertNotIn("eventHubsDataSenderRoleId", base, "the base's template gives no role to send to an event hub")
        self.assertEqual(ep.PLACEHOLDER, "00000000-0000-0000-0000-000000000000", "the all-zero id is still what the Foundry file holds until the cases app has an identity")


class Refusals(unittest.TestCase):
    def refused(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual(code, 2, changes)
        self.assertEqual(files, {}, "nothing is written for a bad setting")
        self.assertEqual(out, "")
        return err

    def test_a_missing_setting_is_named(self):
        for name in SETTINGS:
            env = {k: v for k, v in SETTINGS.items() if k != name}
            code, _, err, _ = run(env)
            self.assertEqual(code, 2, name)
            self.assertIn(name, err)
            self.assertEqual(run({**env, name: "   "})[0], 2, name)

    def test_bad_ids_names_and_labels(self):
        self.refused(ENV_SUBSCRIPTION_ID="not-a-guid")
        for bad in ("rg name", "rg/x", "rg;x", "-", "a" * 91, "rg.", "$(x)"):
            self.refused(ENV_RESOURCE_GROUP=bad)
        for bad in ("Sweden Central", "sweden_central", "x", "https://x"):
            self.refused(ENV_LOCATION=bad)
        for bad in ('o"wner', "o<wner", "a" * 65, "o;wner", "o\nwner"):
            self.refused(ENV_OWNER=bad)

    def test_a_leftover_application_insights_id_of_the_old_gateway_is_not_read_even_when_it_is_malformed(self):
        # It was the only id of the gateway's side that the builder read: the usage recording's copy jobs read that component. The recording was removed on 2026-11-07, and the setting went with it.
        plain = run(SETTINGS)
        for bad in ("", "/subscriptions/x", RETIRED_SETTINGS["GATEWAY_RESOURCE_ID"], RETIRED_SETTINGS["GATEWAY_APPINSIGHTS_ID"] + "/x"):
            code, out, err, files = run({**SETTINGS, "GATEWAY_APPINSIGHTS_ID": bad})
            self.assertEqual((code, err, out, files), (0, "", plain[1], plain[3]), bad)

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


class FirstCases(unittest.TestCase):
    """The parameter file of the first cases app (environment/cases/main.bicep): it names what the base made, and nothing of the owner's API Management instance."""

    CASES = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")

    def build(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
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

    def test_it_names_the_storage_account_that_the_base_has_and_no_namespace_and_no_workflow_principal(self):
        files, lines = self.build()
        cases, base = values(files["cases.parameters.json"]), values(files["base.parameters.json"])
        self.assertEqual(cases["storageAccountName"], base["storageAccountName"])
        self.assertNotIn("eventHubNamespaceName", cases)
        self.assertNotIn("eventHubNamespaceName", bicep_params(self.CASES))
        self.assertNotIn("workflowPrincipalId", cases)
        self.assertNotIn("workflowPrincipalId", base)
        self.assertEqual(cases["location"], base["location"])
        self.assertRegex(cases["functionAppName"], r"^func-meternaut-cases-[0-9a-f]{8}$")
        self.assertEqual(lines["cases_function_app_name"], cases["functionAppName"])
        self.assertLessEqual(len(cases["functionAppName"]), 60)

    def test_the_plans_subnet_is_the_same_in_the_cases_file_and_in_the_model_side_file(self):
        files, lines = self.build()
        cases, environment = values(files["cases.parameters.json"]), values(files["environment.parameters.json"])
        self.assertEqual(cases["webSubnetPrefix"], environment["webSubnetPrefix"])
        self.assertEqual(lines["web_subnet_prefix"], cases["webSubnetPrefix"])
        self.assertNotEqual(cases["webSubnetPrefix"], environment["funcSubnetPrefix"], "the function subnet is delegated to Flex Consumption: the Basic plan has a subnet of its own")

    def test_the_file_says_whether_the_integration_subnet_is_there_already_and_says_no_when_nobody_has_looked(self):
        # the subnet is made once: a template that makes it again takes away the route table that the landing zone's network manager put on it
        self.assertIs(values(self.build()[0]["cases.parameters.json"])["webSubnetExists"], False)
        for given, expected in (("", False), ("false", False), ("FALSE", False), ("true", True), (" True ", True)):
            self.assertIs(values(self.build(ENV_WEB_SUBNET_EXISTS=given)[0]["cases.parameters.json"])["webSubnetExists"], expected, given)
        for refused in ("yes", "1", "exists"):
            code, out, err, files = run({**SETTINGS, "ENV_WEB_SUBNET_EXISTS": refused})
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("ENV_WEB_SUBNET_EXISTS is true or false", err)
        self.assertIn("param webSubnetExists bool = false", self.CASES)

    def test_it_reads_the_pilot_subscription_and_names_nothing_of_the_api_management_instance_and_no_key(self):
        files, lines = self.build()
        cases = values(files["cases.parameters.json"])
        self.assertEqual(cases["scopeSubscriptions"], SETTINGS["ENV_SUBSCRIPTION_ID"])
        self.assertEqual([name for name in cases if "gateway" in name.lower() or "product" in name.lower() or "contract" in name.lower()], ["aiGatewayHost"],
                         "the app reads no key, so the file names no gateway of API Management: the one gateway that it names is the AI Gateway's host")
        self.assertNotIn("gatewayUrl", cases)
        self.assertNotIn("gatewayProductSubscriptionId", cases)
        self.assertNotIn("gateway_url", lines, "no step of the workflow knocks at the gateway's address any more")
        self.assertNotIn("azure-api.net", json.dumps(files["cases.parameters.json"]))

    def test_the_cases_file_names_the_ai_gateway_that_every_model_call_goes_through(self):
        # With the host that the workflow read from the service, the file carries it; in a preview and a what-if, where the gateway may not be in Azure yet, a placeholder that is no gateway.
        host = "aigw-meternaut-0123abcd.swedencentral-01.ai.gateway.azure.com"
        for extra in ((), ("--preview",)):
            code, out, err, files = run({**SETTINGS, "AIGATEWAY_HOST": host, "ACTION": "cases"}, *extra)
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(values(files["cases.parameters.json"])["aiGatewayHost"], host, extra)
            self.assertNotIn(host, out, "the host name is not printed")
        for action, extra in (("", ()), ("what-if", ()), ("cases", ("--preview",)), ("base", ())):
            code, out, err, files = run({**SETTINGS, "ACTION": action}, *extra)
            self.assertEqual((code, err), (0, ""), action)
            self.assertEqual(values(files["cases.parameters.json"])["aiGatewayHost"], ep.PLACEHOLDER_AIGATEWAY_HOST, f"{action!r}: the placeholder, because the gateway is not named")
        # With the agents' route on, the actions foundry and aigateway are refused without the host and without the project's identity (test_aigateway_agents_params.py); with the constant
        # False, which is the way back, they go on without them.
        for action in ("foundry", "aigateway"):
            with mock.patch.object(ep, "AGENTS_VIA_AI_GATEWAY", False):
                code, out, err, files = run({**SETTINGS, "ACTION": action})
            self.assertEqual((code, err), (0, ""), action)
            self.assertEqual(values(files["cases.parameters.json"])["aiGatewayHost"], ep.PLACEHOLDER_AIGATEWAY_HOST, f"{action!r}: the placeholder, because the gateway is not named")
        self.assertRegex(ep.PLACEHOLDER_AIGATEWAY_HOST, ep.AIGATEWAY_HOST.pattern, "the placeholder is a valid host name, so that the file fits the template's checks")
        self.assertIn("placeholder", ep.PLACEHOLDER_AIGATEWAY_HOST)
        declared = bicep_params(self.CASES)
        self.assertEqual(declared["aiGatewayHost"], ("string", False), "required by the template: no default, so that no file can leave it out")

    def test_the_action_cases_is_refused_without_the_host_of_the_gateway_and_says_what_to_do(self):
        for missing in (None, "", "   "):
            env = {**SETTINGS, "ACTION": "cases"}
            if missing is not None:
                env["AIGATEWAY_HOST"] = missing
            code, out, err, files = run(env)
            self.assertEqual((code, out, files), (2, "", {}), repr(missing))
            self.assertIn("the AI Gateway cannot be named: AIGATEWAY_HOST", err)
            self.assertIn("every model call of the cases app goes through the gateway", err)
            self.assertIn("Run the action aigateway first", err)

    def test_a_host_that_is_set_is_checked_whatever_the_action_is_and_is_never_echoed(self):
        host = "aigw-meternaut-0123abcd.swedencentral-01.ai.gateway.azure.com"
        for action in ("cases", "what-if", "foundry", "aigateway", ""):
            for bad in ("evil.example.com", f"{host}.evil.example.com", f"https://{host}", f"{host}/default", f"{host}:443", ".ai.gateway.azure.com", "x_y.ai.gateway.azure.com"):
                with self.subTest(action=action, bad=bad[:30]):
                    code, out, err, files = run({**SETTINGS, "ACTION": action, "AIGATEWAY_HOST": bad})
                    self.assertEqual((code, out, files), (2, "", {}))
                    self.assertIn("AIGATEWAY_HOST is the host name that the service reports for the AI Gateway, under .ai.gateway.azure.com", err)
                    self.assertNotIn("evil", err)
        code, _, err, files = run({**SETTINGS, "ACTION": "cases", "AIGATEWAY_HOST": f"  {host.upper()} "})
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(values(files["cases.parameters.json"])["aiGatewayHost"], host, "trimmed and in lower case")

    def test_the_host_of_the_gateway_reaches_the_cases_file_alone_while_the_agents_switch_is_off(self):
        # The way back: with the constant False the Foundry file carries no connection (the constant is True in the repository, so the test sets it).
        host = "aigw-meternaut-0123abcd.swedencentral-01.ai.gateway.azure.com"
        with mock.patch.object(ep, "AGENTS_VIA_AI_GATEWAY", False):
            files, _ = self.build(AIGATEWAY_HOST=host, ACTION="foundry")
        self.assertFalse({"aiGatewayHost", "aiGatewayModels"} & set(values(files["foundry.parameters.json"])), "no connection of the Foundry project to the gateway while the switch is off")
        for name, document in files.items():
            if name != "cases.parameters.json":
                self.assertNotIn(host, json.dumps(document), name)

    def test_the_host_of_the_gateway_reaches_the_foundry_file_and_the_cases_file_while_the_agents_switch_is_on(self):
        host = "aigw-meternaut-0123abcd.swedencentral-01.ai.gateway.azure.com"
        self.assertIs(ep.AGENTS_VIA_AI_GATEWAY, True)
        files, _ = self.build(AIGATEWAY_HOST=host, ACTION="foundry")
        foundry = values(files["foundry.parameters.json"])
        self.assertEqual(foundry["aiGatewayHost"], host, "the connection of the Foundry project to the gateway is asked for")
        self.assertEqual([m["name"] for m in foundry["aiGatewayModels"]], [m["name"] for m in json.loads(MODELS.read_text(encoding="utf-8"))])
        cases = values(files["cases.parameters.json"])
        self.assertEqual(cases["aiGatewayHost"], host)
        self.assertEqual((cases["foundryModelInvestigator"], cases["foundryModelSkeptic"]), tuple(f"{ep.AIGATEWAY_CONNECTION_NAME}/{name}" for name in ep.AGENT_MODELS.values()))
        for name, document in files.items():
            if name not in ("foundry.parameters.json", "cases.parameters.json"):
                self.assertNotIn(host, json.dumps(document), name)

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
        self.assertEqual(models, {"modelDetective": "gpt-6-luna", "modelSkeptic": "gpt-6.1-sol"},
                         "the judges keep the two GPT-6 models that worked through the gateway; the Investigator of the agents is another model, gpt-5.5, because the GPT-6 models refuse function tools on Chat Completions")

    def test_the_queue_and_the_one_identity_are_the_ones_the_template_makes(self):
        _, lines = self.build()
        self.assertIn("var controlQueueName = '" + lines["cases_queue_name"] + "'", self.CASES)
        self.assertIn("name: 'id-${workload}-console-auth'", self.CASES, "the one user-assigned identity of the template: the function app's sign-in")
        self.assertNotIn("id-${workload}-cases", self.CASES, "the user-assigned identity that the app's system-assigned one replaced is not made any more")
        self.assertNotIn("cases_identity_name", lines)

    def test_the_cases_file_depends_on_nothing_of_the_api_management_instance_and_is_the_same_whatever_a_leftover_setting_says(self):
        # The contract and the gateway were the API Management side, which Meternaut has left: the first cases are deployed without it, and a setting of the retired actions changes nothing.
        plain = run(SETTINGS)
        self.assertEqual(plain[0], 0)
        leftover = run({**SETTINGS, **RETIRED_SETTINGS, "GATEWAY_PRINCIPAL_ID": "not-a-guid", "GATEWAY_CLIENT_ID": "x", "RECORDING_FRAGMENTS": "maybe"})
        self.assertEqual((leftover[0], leftover[2]), (0, ""))
        self.assertEqual(plain[3]["cases.parameters.json"], leftover[3]["cases.parameters.json"])
        self.assertNotIn("contract_subscription", dict(line.split("=", 1) for line in plain[1].splitlines()))

    def test_the_cases_file_names_the_foundry_project_when_the_workflow_found_it_and_a_preview_changes_nothing_of_it(self):
        for extra in ((), ("--preview",)):
            code, out, err, files = run({**SETTINGS, "ENV_FOUNDRY_PROJECT_EXISTS": "true"}, *extra)
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
                code, out, err, _ = run({**SETTINGS, **change})
                self.assertEqual(code, 2, err)
                self.assertEqual(out, "")

    def test_the_planting_has_a_name_that_the_run_chooses_and_a_public_address_and_a_machine_only_when_asked(self):
        files, _ = self.build()
        planted = values(files["planted.parameters.json"])
        self.assertEqual((planted["plantedId"], planted["plantPublicIp"], planted["plantVm"]), ("demo", False, False))
        self.assertEqual(planted["plantedVmSize"], ep.PLANTED_VM_SIZE)
        self.assertEqual(ep.PLANTED_VM_SIZE, "Standard_B4als_v2", "a size of the pilot's subscription that has a smaller one in its series, so that resize-vm has a step to take (Standard_B2als_v2)")
        files, _ = self.build(PLANTED_ID="r42", PLANT_PUBLIC_IP="TRUE")
        planted = values(files["planted.parameters.json"])
        self.assertEqual((planted["plantedId"], planted["plantPublicIp"], planted["plantVm"]), ("r42", True, False))
        self.assertEqual(planted["location"], values(files["base.parameters.json"])["location"])
        files, _ = self.build(PLANTED_ID="r43", PLANT_VM="True")
        planted = values(files["planted.parameters.json"])
        self.assertEqual((planted["plantedId"], planted["plantPublicIp"], planted["plantVm"]), ("r43", False, True))
        for bad in ({"PLANTED_ID": "Has Space"}, {"PLANTED_ID": "x" * 13}, {"PLANT_PUBLIC_IP": "maybe"}, {"PLANT_VM": "maybe"}, {"PLANT_VM": "1"}):
            with self.subTest(bad):
                self.assertEqual(run({**SETTINGS, **bad})[0], 2)

    def test_the_planted_file_fits_its_template(self):
        files, _ = self.build()
        template = (ROOT / "environment" / "cases" / "planted.bicep").read_text(encoding="utf-8")
        declared = bicep_params(template)
        given = files["planted.parameters.json"]["parameters"]
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        self.assertTrue({name for name, (_, has_default) in declared.items() if not has_default} <= set(given))


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
        return run({**SETTINGS, **changes})

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

    def test_the_names_are_a_host_name_inside_its_limit_the_same_on_every_run_and_not_the_old_model_account(self):
        files, outputs = self.files()
        again = self.files()[1]
        token = ep.digest(SETTINGS["ENV_SUBSCRIPTION_ID"], SETTINGS["ENV_RESOURCE_GROUP"])
        account = outputs["foundry_account_name"]
        self.assertEqual(account, f"aif-meternaut-agents-{token}")
        self.assertRegex(account, r"^[A-Za-z0-9][A-Za-z0-9-]{1,63}$")
        self.assertEqual({k: v for k, v in outputs.items() if k.startswith("foundry_")}, {k: v for k, v in again.items() if k.startswith("foundry_")})
        self.assertNotEqual(account, f"aif-meternaut-{token}", "the old model account was made with allowProjectManagement false and could never hold a project: the action retire-old deletes it")
        self.assertNotIn("account_name", outputs, "the builder names no model account but this one")
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
        self.assertNotIn("models", values(files["environment.parameters.json"]), "the model side makes no model deployments: the old model account was removed on 2026-11-07")
        for model in deployed:
            self.assertEqual(set(model), {"name", "version", "sku", "capacity"}, "no retirement date and no agentCapacity reaches the template")

    def test_the_capacity_of_the_agents_is_the_one_that_the_foundry_file_gets(self):
        models = [{"name": "gpt-5.5", "version": "2026-04-24", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 70, "retirementDate": "2027-10-26"},
                  {"name": "gpt-6.1-sol", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 30, "agentCapacity": 10, "retirementDate": "2028-03-11"}]
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "models.json"
        path.write_text(json.dumps(models), encoding="utf-8")
        code, _, _, files = run(SETTINGS, models=path)
        self.assertEqual(code, 0)
        self.assertEqual([m["capacity"] for m in values(files["foundry.parameters.json"])["models"]], [70, 10])

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
        self.assertEqual(run({**SETTINGS, "CASES_SYSTEM_PRINCIPAL_ID": ""}, "--preview")[0], 0, "a preview needs no cases identity")

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

    OPERATOR_PRINCIPAL = "ABCDEF01-2345-6789-ABCD-EF0123456789"

    def test_the_identity_of_the_operator_reaches_the_foundry_file_when_it_is_given_and_the_file_is_what_it_was_when_it_is_not(self):
        # The template gives that identity Foundry User on the project (docs/proposals/11-agent-harness-and-evaluation.md); the parameter is optional so that the Foundry resource still deploys on an estate with no Operator.
        with_it, _ = self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL, OPERATOR_PRINCIPAL_ID=self.OPERATOR_PRINCIPAL)
        self.assertEqual(values(with_it["foundry.parameters.json"])["operatorPrincipalId"], self.OPERATOR_PRINCIPAL.lower())
        declared = bicep_params(self.FOUNDRY)
        self.assertEqual(declared["operatorPrincipalId"], ("string", True), "the template has a default: empty, and then no role")
        self.assertTrue(set(with_it["foundry.parameters.json"]["parameters"]) <= set(declared))
        without, _ = self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL)
        self.assertNotIn("operatorPrincipalId", without["foundry.parameters.json"]["parameters"], "not given: no parameter, so the template's default holds")
        for empty in ("", "   "):
            files, _ = self.files(CASES_SYSTEM_PRINCIPAL_ID=self.SYSTEM_PRINCIPAL, OPERATOR_PRINCIPAL_ID=empty)
            self.assertEqual(files, without, repr(empty))
        self.assertEqual({k: v for k, v in with_it["foundry.parameters.json"]["parameters"].items() if k != "operatorPrincipalId"}, without["foundry.parameters.json"]["parameters"])
        for name in without:
            if name != "foundry.parameters.json":
                self.assertEqual(with_it[name], without[name], f"{name}: only the Foundry file asks for the role")

    def test_an_identity_of_the_operator_that_is_not_an_object_id_is_refused_without_echoing_it(self):
        for bad in ("me", "1234", "{" + self.OPERATOR_PRINCIPAL + "}", self.OPERATOR_PRINCIPAL + "0", "not-a-guid-but-with-secret"):
            for extra in ((), ("--preview",)):
                with self.subTest(bad=bad, extra=extra):
                    code, out, err, files = run({**SETTINGS, "OPERATOR_PRINCIPAL_ID": bad}, *extra)
                    self.assertEqual((code, out, files), (2, "", {}))
                    self.assertIn("OPERATOR_PRINCIPAL_ID is the object id of the", err)
                    self.assertNotIn("secret", err)
                    if len(bad) > 8:
                        self.assertNotIn(bad, err)

    def test_the_template_takes_the_identity_of_the_operator_as_an_optional_parameter_of_at_most_guid_length_and_the_builder_documents_it(self):
        self.assertRegex(self.FOUNDRY, r"(?m)^@maxLength\(36\)\nparam operatorPrincipalId string = ''$")
        self.assertIn("OPERATOR_PRINCIPAL_ID (optional, may be empty)", TOOL.read_text(encoding="utf-8"), "the docstring of the builder names the setting")

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
        self.assertEqual(set(operator), {"location", "owner", "opsSubnetPrefix", "opsSubnetExists", "storageAccountName"},
                         "a range, a flag, the name of the storage account and two tags: nothing else, and nothing secret")
        self.assertEqual((operator["location"], operator["owner"]), ("swedencentral", "owner@example.com"))

    def test_the_storage_account_is_the_one_that_the_base_and_the_first_cases_use(self):
        files, outputs = self.files()
        operator = values(files["operator.parameters.json"])["storageAccountName"]
        self.assertEqual(operator, values(files["base.parameters.json"])["storageAccountName"], "the Operator reads the queue in the storage account that the base makes")
        self.assertEqual(operator, values(files["cases.parameters.json"])["storageAccountName"])
        self.assertEqual(operator, outputs["storage_account_name"])
        self.assertRegex(operator, r"^stmeternautfn[0-9a-f]{8}$")
        self.assertIn("param storageAccountName string", self.OPERATOR)
        self.assertNotIn("eventHubNamespaceName", self.OPERATOR)

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
        # What the option asks for are the three files and the aigateway_* outputs of step 1. The agents' route (the constant True in the repository) prints its own two lines, which are the next test's.
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertFalse([name for name in files if "aigateway" in name], "the other actions are not touched by the gateway")
        printed = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual([key for key in printed if "aigateway" in key or "ai_gateway" in key], ["agents_via_ai_gateway", "aigateway_connection_name"], "the two lines of the agents' route and nothing of the gateway's files")
        with mock.patch.object(ep, "AGENTS_VIA_AI_GATEWAY", False):
            code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("aigateway", out, "with the agents' route off (the way back) nothing of the gateway is printed")

    def test_the_three_files_are_written_and_the_outputs_name_what_the_workflow_reads(self):
        files, outputs = self.files()
        mine = {"aigateway-subnet.parameters.json", "aigateway.parameters.json", "aigateway-policies.json"}
        self.assertTrue(mine <= set(files))
        self.assertEqual(set(files) - mine,
                         {"environment.parameters.json", "base.parameters.json", "foundry.parameters.json", "operator.parameters.json", "planted.parameters.json",
                          "cases.parameters.json"})
        self.assertEqual({key: value for key, value in outputs.items() if key.startswith("aigateway_")},
                         {"aigateway_name": outputs["aigateway_name"], "aigateway_subnet_name": "snet-aigw", "aigateway_subnet_prefix": "10.53.0.128/26",
                          "aigateway_aliases": "gpt-6-luna gpt-6.1-sol gpt-5.5", "aigateway_files": "true", "aigateway_connection_name": "aigateway"})
        self.assertEqual(outputs["agents_via_ai_gateway"], "true", "the agents' route is on in the repository")
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
        self.assertEqual(set(gateway), {"location", "owner", "gatewayName", "foundryAccountName", "models", "foundryProjectPrincipalId", "casesPrincipalId"},
                         "names, a flag and the models: nothing secret, nothing of the subnet, and the telemetry stays at the template's default, which is off")
        subnet = values(files["aigateway-subnet.parameters.json"])
        self.assertEqual(set(subnet), {"location", "owner", "aigwSubnetPrefix", "aigwSubnetExists"},
                         "the range and whether it is there already; the workload is left to the template's default, as the file of the gateway leaves it")
        self.assertEqual((subnet["location"], subnet["owner"]), (gateway["location"], gateway["owner"]), "the subnet is in the gateway's region and has the gateway's owner")
        self.assertNotIn("telemetryEnabled", bicep_params(self.TEMPLATE), "the exporter moved to environment/aigateway/telemetry.bicep (the action gateway-telemetry)")
        self.assertEqual(bicep_params(self.TEMPLATE)["foundryProjectPrincipalId"], ("string", True))
        self.assertEqual(bicep_params(self.TEMPLATE)["casesPrincipalId"], ("string", True), "empty means none: the app has no identity before the action cases has made it")
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

    def test_the_principal_of_the_cases_app_is_the_one_that_the_workflow_reads_from_the_app_and_is_empty_when_the_app_has_no_identity_yet(self):
        # The same object id that the Foundry file gets (CASES_SYSTEM_PRINCIPAL_ID): the Detective and the Skeptic call the gateway with that identity, so it gets AI Gateway Models User on it.
        files, _ = self.files()
        self.assertEqual(values(files["aigateway.parameters.json"])["casesPrincipalId"], "", "no identity yet: the gateway is made without the role, and the next run gives it")
        files, _ = self.files(CASES_SYSTEM_PRINCIPAL_ID="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")
        self.assertEqual(values(files["aigateway.parameters.json"])["casesPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(values(files["foundry.parameters.json"])["casesSystemPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "the one id serves both files")
        for action in ("aigateway", "what-if", "cases", ""):
            # with the agents' route on the action aigateway also needs the Foundry project's identity (test_aigateway_agents_params.py)
            files, _ = self.files(CASES_SYSTEM_PRINCIPAL_ID="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", ACTION=action, AIGATEWAY_HOST="aigw-x.swedencentral-01.ai.gateway.azure.com",
                                  FOUNDRY_PROJECT_PRINCIPAL_ID="bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
            self.assertEqual(values(files["aigateway.parameters.json"])["casesPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", action)
        for refused in ("not-a-guid", "12345678-1234-1234-1234-12345678901"):
            code, out, err, files = run({**SETTINGS, "CASES_SYSTEM_PRINCIPAL_ID": refused}, "--aigateway-policies", str(self.POLICIES))
            self.assertEqual((code, out, files), (2, "", {}), refused)
            self.assertIn("CASES_SYSTEM_PRINCIPAL_ID", err)
            self.assertNotIn(refused, err, "a value that is not an object id is not echoed")

    def test_two_models_whose_resource_names_would_be_the_same_are_refused_and_so_is_a_name_the_service_cannot_take(self):
        # The rule of the gateway's names (step 1). With the agents' route on, a list that lacks the two models of the agents is refused first, with a message of its own (test_aigateway_agents_params.py),
        # so the constant is False here.
        base = json.loads(MODELS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ep, "AGENTS_VIA_AI_GATEWAY", False):
            for names, expected in ((("gpt-6.1-sol", "gpt-6-1-sol"), "no two are the same"), (("gpt-6.1-sol", "ab"), "3 to 63")):
                models = [{**base[0], "name": names[0]}, {**base[1], "name": names[1]}, base[2]]
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
            path.write_text(json.dumps([{**base[0]}, {**base[1]}, {**base[2], "agentCapacity": 80}]), encoding="utf-8")
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
    """What the cases app takes from the public internet is one value (docs/proposals/07-private-by-default.md, phase 1): written to its parameter file every time, so that the property is never
    left unset, which would let the first private endpoint switch public access off by itself. (The usage app, which had a value of its own and was closed, was removed on 2026-11-07.)"""

    CASES_TEMPLATE = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")

    def build(self, **changes):
        return run({**SETTINGS, **changes})

    def test_the_cases_app_is_open_until_the_people_have_a_path_and_the_value_reaches_its_parameter_file_only(self):
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(ep.CASES_APP_PUBLIC_NETWORK_ACCESS, "Enabled",
                         "the cases app serves the web page and stays open until the owner closes it (he reaches the private network, and flips this one value himself, in a change of its own, when he can "
                         "reach the private address): that is the one value and the one test to change then")
        self.assertFalse(hasattr(ep, "USAGE_APP_PUBLIC_NETWORK_ACCESS"), "the usage app was removed on 2026-11-07, and its constant with it")
        self.assertEqual(values(files["cases.parameters.json"])["casesAppPublicNetworkAccess"], "Enabled")
        for name, document in files.items():
            if name != "cases.parameters.json":
                self.assertFalse({"usageAppPublicNetworkAccess", "casesAppPublicNetworkAccess"} & set(document["parameters"]), f"{name}: the value reaches the file of its own app only")

    def test_closing_the_app_is_one_value_and_it_reaches_only_that_app(self):
        # A closed cases app builds with a host name on the platform's Application Gateway and, since the owner decided against the gateway (2026-11-07), without one: then the check of its front door runs
        # in the Operator (tools/tests/test_console_gateway.py has the output and the steps).
        for cases in ("Disabled", "Enabled"):
            for named in ("", "console.example.com"):
                with mock.patch.object(ep, "CASES_APP_PUBLIC_NETWORK_ACCESS", cases):
                    code, _, err, files = self.build(CONSOLE_HOST_NAME=named)
                self.assertEqual((code, err), (0, ""), (cases, named))
                self.assertEqual(values(files["cases.parameters.json"])["casesAppPublicNetworkAccess"], cases, (cases, named))

    def test_a_value_that_is_not_enabled_or_disabled_is_refused_by_name_because_the_property_must_always_be_written(self):
        for constant in ("CASES_APP_PUBLIC_NETWORK_ACCESS",):
            for bad in ("", "enabled", "Allow", "SecuredByPerimeter"):
                with mock.patch.object(ep, constant, bad):
                    code, out, err, files = self.build()
                self.assertEqual((code, out, files), (2, "", {}), (constant, bad))
                self.assertIn(f"{constant} (in tools/environment-params.py) is Enabled or Disabled", err)

    def test_the_template_takes_the_value_with_the_same_two_choices_and_the_default_that_the_file_carries(self):
        for source, name in ((self.CASES_TEMPLATE, "casesAppPublicNetworkAccess"),):
            self.assertRegex(source, rf"(?m)^@allowed\(\[\n  'Enabled'\n  'Disabled'\n\]\)\nparam {name} string = 'Enabled'$", name)
            self.assertEqual(bicep_params(source)[name], ("string", True), "it has a default: a file that leaves it out still gives the property a value")
            self.assertIn(f"    publicNetworkAccess: {name}\n", source, "the app takes the parameter, and nothing else gives the property a value")
        self.assertEqual(ep.PUBLIC_NETWORK_ACCESS, ("Enabled", "Disabled"))

    def test_the_endpoint_of_the_app_is_in_the_list_that_its_action_waits_for_with_the_zone_of_app_service_and_the_name_that_its_template_gives_it(self):
        # The first publish after an app's endpoint was made failed: a deployment ends with a call from the deployment site to the app's own host name, and while the central zone had no record of
        # the new endpoint that name did not resolve ("Reset all workers endpoint responded with Name or service not known"). A list without the app's endpoint lets the workflow publish too early.
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        lines = dict(line.split("=", 1) for line in out.splitlines())
        cases = values(files["cases.parameters.json"])["functionAppName"]
        self.assertEqual(lines["cases_endpoints"], f"pe-{cases}:privatelink.azurewebsites.net", "the cases app has one endpoint, and its action waits for it")
        self.assertEqual(ep.APP_ENDPOINT_ZONE, "privatelink.azurewebsites.net", "the central zone of App Service: the names of the app and of its deployment site")
        self.assertNotIn(cases, lines["base_endpoints"], "each action waits for the endpoints that it makes: the base makes none of an app's")
        self.assertIn("name: 'pe-${functionAppName}'", self.CASES_TEMPLATE, "the name that the workflow looks for is the name that the template gives the endpoint")
        self.assertIn("'sites'", self.CASES_TEMPLATE)
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


class ThePlanOfTheCasesApp(unittest.TestCase):
    """The web page's app runs on Flex Consumption or on a Basic plan, from one constant (docs/proposals/07-private-by-default.md, "The web page on Flex Consumption"): both values build valid files, the
    two differ in nothing but the plan, and the way back to Basic is the one value, on the owner's word."""

    CASES_TEMPLATE = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")

    def build(self, plan=None, **changes):
        if plan is None:
            return run({**SETTINGS, **changes})
        with mock.patch.object(ep, "CASES_APP_PLAN", plan):
            return run({**SETTINGS, **changes})

    def test_the_constant_is_flex_and_is_one_line_among_the_constants_near_the_top_of_the_builder(self):
        self.assertEqual(ep.CASES_APP_PLAN, "Flex", "the owner ordered Flex Consumption on 2026-11-07 and again on 2026-11-08, after the measurement of the platform's hold (docs/proposals/07-private-by-default.md): the constant goes back to Basic only on his word, and then this is the one value and the one test to change")
        self.assertEqual(ep.CASES_APP_PLANS, ("Flex", "Basic"))
        source = TOOL.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'(?m)^CASES_APP_PLAN = "(Flex|Basic)"$', source), ["Flex"], "one constant, one line")
        self.assertLess(source.index('\nCASES_APP_PLAN = "Flex"\n'), source.index("\ndef "), "near the top, with the other constants")

    def test_both_values_build_valid_parameter_files_that_the_template_takes(self):
        declared = bicep_params(self.CASES_TEMPLATE)
        for plan in ("Flex", "Basic"):
            with self.subTest(plan=plan):
                code, out, err, files = self.build(plan)
                self.assertEqual((code, err), (0, ""))
                given = values(files["cases.parameters.json"])
                self.assertEqual(given["casesAppPlan"], plan)
                self.assertFalse(set(given) - set(declared), f"{plan}: a setting that the template does not take")
                self.assertFalse({name for name, (_, has_default) in declared.items() if not has_default} - set(given), f"{plan}: a setting that the template needs and the file does not give")
                self.assertEqual(declared["casesAppPlan"], ("string", True))
        self.assertIn("param casesAppPlan string = 'Flex'\n", self.CASES_TEMPLATE, "the template's default is the constant's")
        self.assertRegex(self.CASES_TEMPLATE, r"@allowed\(\[\n  'Flex'\n  'Basic'\n\]\)\nparam casesAppPlan")

    def test_the_two_values_differ_in_the_plan_alone_and_nothing_else_changes_when_the_plan_changes(self):
        results = {plan: self.build(plan) for plan in ("Flex", "Basic")}
        for plan, (code, out, err, files) in results.items():
            self.assertEqual((code, err), (0, ""), plan)
        flex_files, basic_files = results["Flex"][3], results["Basic"][3]
        self.assertEqual(set(flex_files), set(basic_files))
        for name in flex_files:
            if name != "cases.parameters.json":
                self.assertEqual(flex_files[name], basic_files[name], f"{name}: the plan reaches the file of the cases app only")
        flex, basic = values(flex_files["cases.parameters.json"]), values(basic_files["cases.parameters.json"])
        self.assertEqual({k: v for k, v in flex.items() if k != "casesAppPlan"}, {k: v for k, v in basic.items() if k != "casesAppPlan"},
                         "the subnet's range, the identities, the settings, the people and the public access are the same: the app moves and nothing else does")
        self.assertEqual(flex["webSubnetPrefix"], basic["webSubnetPrefix"], "the Basic plan's subnet range is always given, whichever plan the app is on, so that a move between the two needs nothing else")
        lines = {plan: dict(line.split("=", 1) for line in results[plan][1].splitlines()) for plan in results}
        plan_keys = {"cases_app_plan", "cases_plan_name", "cases_plan_tier", "cases_other_plan_name", "cases_other_plan_tier", "cases_subnet_name"}
        for key in set(lines["Flex"]) - plan_keys:
            self.assertEqual(lines["Flex"][key], lines["Basic"][key], key)
        self.assertEqual(set(lines["Flex"]), set(lines["Basic"]))

    def test_the_plan_and_the_subnet_of_each_kind_and_the_plan_that_the_action_removes_are_named_by_the_builder(self):
        expected = {"Flex": {"cases_app_plan": "Flex", "cases_plan_name": "plan-meternaut-cases", "cases_plan_tier": "FlexConsumption", "cases_other_plan_name": "plan-meternaut-cases-basic",
                             "cases_other_plan_tier": "Basic", "cases_subnet_name": "snet-func", "function_subnet_name": "snet-func"},
                    "Basic": {"cases_app_plan": "Basic", "cases_plan_name": "plan-meternaut-cases-basic", "cases_plan_tier": "Basic", "cases_other_plan_name": "plan-meternaut-cases",
                              "cases_other_plan_tier": "FlexConsumption", "cases_subnet_name": "snet-cases", "function_subnet_name": "snet-func"}}
        for plan, want in expected.items():
            with self.subTest(plan=plan):
                _, out, _, _ = self.build(plan)
                lines = dict(line.split("=", 1) for line in out.splitlines())
                self.assertEqual({key: lines[key] for key in want}, want)
        self.assertEqual(ep.CASES_PLAN_NAMES["Flex"], "plan-meternaut-cases")
        self.assertIn("name: isFlex ? 'plan-${workload}-cases' : 'plan-${workload}-cases-basic'", self.CASES_TEMPLATE, "the names that the workflow removes a plan by are the template's")

    def test_a_value_that_is_not_flex_or_basic_is_refused_by_name_before_anything_is_written(self):
        for bad in ("flex", "basic", "FlexConsumption", "Premium", "", None, True, 1):
            with self.subTest(bad=bad), mock.patch.object(ep, "CASES_APP_PLAN", bad):
                code, out, err, files = run(SETTINGS)
                self.assertEqual((code, out, files), (2, "", {}), repr(bad))
                self.assertIn("CASES_APP_PLAN (in tools/environment-params.py) is Flex or Basic", err)


class WhatTheWatchReads(unittest.TestCase):
    """The Watch reads every subscription that its identity can read (the owner's order of 2026-11-07: watch the entire estate). The parameter builder says so through one named constant, and the
    template takes it with the default false, so that a file that leaves it out keeps what the app did before: it reads only the subscription of scopeSubscriptions."""

    CASES_TEMPLATE = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
    CONFIG = (ROOT / "src" / "case-functions" / "cases" / "config.py").read_text(encoding="utf-8")

    def build(self, **changes):
        return run({**SETTINGS, **changes})

    def test_the_constant_is_true_and_is_one_line_among_the_constants_near_the_top_of_the_builder(self):
        self.assertIs(ep.SCOPE_ALL_SUBSCRIPTIONS, True, "the owner wants the entire estate: this is the one value, and the one test, to change to read only the subscription of this estate")
        source = TOOL.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^SCOPE_ALL_SUBSCRIPTIONS = (True|False)$", source), ["True"], "one constant, one line")
        self.assertLess(source.index("\nSCOPE_ALL_SUBSCRIPTIONS = True\n"), source.index("\ndef "), "near the top, with the other constants")

    def test_the_value_reaches_the_file_of_the_cases_app_only_and_the_subscription_stays_as_the_fallback(self):
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        cases = values(files["cases.parameters.json"])
        self.assertIs(cases["scopeAllSubscriptions"], True)
        self.assertEqual(cases["scopeSubscriptions"], SETTINGS["ENV_SUBSCRIPTION_ID"], "the explicit list stays: it is what the Watch reads when the list of its identity cannot be had")
        for name, document in files.items():
            if name != "cases.parameters.json":
                self.assertNotIn("scopeAllSubscriptions", document.get("parameters", {}), name)
        self.assertNotIn("scope", "".join(line.split("=", 1)[0] for line in out.splitlines()), "no output of the workflow carries it")

    def test_the_other_value_is_written_too_so_that_a_deploy_of_cases_sets_the_setting_either_way(self):
        with mock.patch.object(ep, "SCOPE_ALL_SUBSCRIPTIONS", False):
            code, _, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        self.assertIs(values(files["cases.parameters.json"])["scopeAllSubscriptions"], False)

    def test_a_value_that_is_not_true_or_false_is_refused_by_name(self):
        for bad in ("True", "true", "yes", 1, 0, None, ""):
            with mock.patch.object(ep, "SCOPE_ALL_SUBSCRIPTIONS", bad):
                code, out, err, files = self.build()
            self.assertEqual((code, out, files), (2, "", {}), repr(bad))
            self.assertIn("SCOPE_ALL_SUBSCRIPTIONS (in tools/environment-params.py) is True or False", err)

    def test_the_template_takes_a_bool_with_the_default_false_and_gives_it_to_the_app_as_the_setting_that_the_code_reads(self):
        self.assertEqual(bicep_params(self.CASES_TEMPLATE)["scopeAllSubscriptions"], ("bool", True))
        self.assertIn("\nparam scopeAllSubscriptions bool = false\n", self.CASES_TEMPLATE, "a file that leaves it out keeps the old behaviour")
        self.assertIn("        { name: 'SCOPE_ALL_SUBSCRIPTIONS', value: scopeAllSubscriptions ? 'true' : 'false' }\n", self.CASES_TEMPLATE)
        self.assertIn('\nSCOPE_ALL_SUBSCRIPTIONS = "SCOPE_ALL_SUBSCRIPTIONS"\n', self.CONFIG)
        self.assertIn("        { name: 'SCOPE_SUBSCRIPTIONS', value: scopeSubscriptions }\n", self.CASES_TEMPLATE, "the explicit list is still set: it is the fallback")

    def test_the_template_grants_nothing_for_it_because_a_person_gives_the_read_only_roles_outside_it(self):
        # AGENTS.md rule 18: the roles of the app's identity at a subscription or at a management group are given by a person; the deployment workflow's identity has no right there and must not get one.
        self.assertIn("\ntargetScope = 'resourceGroup'\n", self.CASES_TEMPLATE)
        self.assertNotIn("managementGroups", self.CASES_TEMPLATE)
        self.assertNotIn("Microsoft.Management", self.CASES_TEMPLATE)
        for role, name in (("acdd72a7-3385-48ef-bd42-f606fba81ae7", "Reader"), ("72fafb9e-0641-4937-9268-a91bfd8191a3", "Cost Management Reader")):
            self.assertNotIn(role, self.CASES_TEMPLATE, f"{name} is given by a person")


if __name__ == "__main__":
    unittest.main()
