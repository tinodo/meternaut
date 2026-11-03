import importlib.util
import io
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
    "GATEWAY_CLIENT_ID": "BBBBBBBB-CCCC-DDDD-EEEE-FFFFFFFFFFFF",
}


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
    def test_good_settings_give_three_files_and_the_outputs(self):
        code, out, err, files = run(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(set(files), {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json"})
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
        self.assertEqual(lines["client_id_known"], "true")

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
            "apimName": "example-apim", "appInsightsName": "example-insights", "appInsightsResourceGroup": "rg-gateway",
            "gatewayIdentityClientId": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"})

    def test_a_client_id_that_was_left_out_is_a_placeholder_and_says_so(self):
        env = {k: v for k, v in SETTINGS.items() if k != "GATEWAY_CLIENT_ID"}
        code, out, err, files = run(env)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("client_id_known=false", out)
        self.assertEqual(values(files["logger.parameters.json"])["gatewayIdentityClientId"], ep.PLACEHOLDER)
        self.assertEqual(values(run({**env, "GATEWAY_CLIENT_ID": "  "})[3]["logger.parameters.json"])["gatewayIdentityClientId"], ep.PLACEHOLDER)

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
        for key in ("updateUnifiedAiApi", "enableUnifiedAiApi", "updateReleaseVersionApi", "updateOpenAIRealtimeApi",
                    "updateRedisCache", "enableRedisCache", "updateEmbeddingsBackend", "enableEmbeddingsBackend"):
            self.assertIs(self.kit[key], False, key)

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


class Refusals(unittest.TestCase):
    def refused(self, **changes):
        code, out, err, files = run({**SETTINGS, **changes})
        self.assertEqual(code, 2, changes)
        self.assertEqual(files, {}, "nothing is written for a bad setting")
        self.assertEqual(out, "")
        return err

    def test_a_missing_setting_is_named(self):
        for name in SETTINGS:
            if name in ("GATEWAY_PRINCIPAL_ID", "GATEWAY_CLIENT_ID"):
                continue
            env = {k: v for k, v in SETTINGS.items() if k != name}
            code, _, err, _ = run(env)
            self.assertEqual(code, 2, name)
            self.assertIn(name, err)
            self.assertEqual(run({**env, name: "   "})[0], 2, name)

    def test_bad_ids_names_and_labels(self):
        self.refused(ENV_SUBSCRIPTION_ID="not-a-guid")
        self.refused(GATEWAY_PRINCIPAL_ID="1234")
        self.refused(GATEWAY_CLIENT_ID="1234")
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

    def test_the_contract_of_the_repository_gives_a_fourth_file_that_fits_its_template(self):
        code, out, err, files = self.build()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(set(files), {"environment.parameters.json", "logger.parameters.json", "kit.parameters.json", "contract.parameters.json"})
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
                  {"name": "small", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 5, "retirementDate": "2028-03-11"}]
        path = self.write("models.json", json.dumps(models))
        self.assertIn("5000", self.refused(self.contract(allowedModels=["big", "small"], tokensPerMinute=10000), models=path))
        self.assertEqual(self.build(self.contract(allowedModels=["big"], tokensPerMinute=10000), models=path)[0], 0)

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
