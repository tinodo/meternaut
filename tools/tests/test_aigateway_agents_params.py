"""The switch of the agents' route through the AI Gateway (AGENTS_VIA_AI_GATEWAY in tools/environment-params.py): while it is False nothing differs, and when it is True the three actions get what they need.

Step 2 of docs/proposals/08-ai-gateway.md. The parameter builder is run in this process with fixed inputs that this file holds itself (no file of the repository is an input of the pins of
"nothing differs"), so that a change of a model version or of a limit cannot break them. No test calls Azure."""
import hashlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("environment_params_of_the_agents_route", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

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
    "GATEWAY_APPINSIGHTS_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg-gateway/providers/microsoft.insights/components/example-insights",
    "RECORDING_READER_IDS": "12345678-1234-1234-1234-123456789012",
    "CASES_SYSTEM_PRINCIPAL_ID": "12345678-dddd-eeee-ffff-123456789012",
    "ENV_FOUNDRY_PROJECT_EXISTS": "true",
    "FOUNDRY_PROJECT_PRINCIPAL_ID": "12345678-eeee-ffff-1111-123456789012",
    "CONSOLE_HOST_NAME": "console.example.com",
}
MODELS = [
    {"name": "gpt-6-luna", "version": "2026-09-22", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 20, "retirementDate": "2028-03-11"},
    {"name": "gpt-6.1-sol", "version": "2026-09-29", "sku": "DataZoneStandard", "capacity": 20, "agentCapacity": 50, "retirementDate": "2028-03-11"},
]
LIMITS = [
    {"type": "tokenLimit", "count": 50000, "period": "minute", "counterKey": ["identity"], "scope": "workspace"},
    {"type": "requestRateLimit", "callsPerPeriod": 60, "periodSeconds": 60, "counterKey": ["identity"], "scope": "workspace"},
    {"type": "costLimit", "id": "meternaut-day", "amount": 5, "period": "day", "counterKey": ["identity"], "scope": "workspace"},
    {"type": "costLimit", "id": "meternaut-month", "amount": 25, "period": "month", "counterKey": ["identity"], "scope": "workspace"},
]
HOST = "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com"
PROJECT_PRINCIPAL = SETTINGS["FOUNDRY_PROJECT_PRINCIPAL_ID"]

# What the builder wrote for exactly these inputs on main before this change (the files byte for byte, and what it printed). While the switch is False the hashes are what they were.
# The hashes of the files are of their LF form: the builder writes with the platform's line ending (CRLF on Windows, LF on the runner), and build() below reads the files with LF.
# Re-recorded on purpose, by the changes that undo what Meternaut added to the owner's API Management instance (2026-11-07). First change: cases.parameters.json lost gatewayUrl,
# gatewayProductSubscriptionId, modelDetective and modelSkeptic (the Detective and the Skeptic call the models of the Foundry project directly, and the app reads no key; the template's defaults apply to
# the two models), and the output lost the line gateway_url. Second change (the retirement of the actions that made objects on the instance): environment.parameters.json and recording.parameters.json lost
# gatewayPrincipalId (no role is made for a gateway identity any more), the four files logger, eventhub-loggers, kit and contract are not written at all, and the output lost the lines gateway_subscription,
# gateway_resource_group, gateway_name, identity_name and principal_known. Every other file is what it was. Third change (the Watch reads every subscription that its identity can read, 2026-11-07):
# cases.parameters.json gained scopeAllSubscriptions (true); every other file and the output are what they were.
GOLDEN = {
    "aigateway-policies.json": "e6d99d1633ab16afc3410e50dbdcb7e290f0e125f4283b4b19f63a8eebb8395c",
    "aigateway-subnet.parameters.json": "a2a16b02fd7a1d54d8949ad89796d4ea89d6bf1907db1f5b621205699a5a0196",
    "aigateway.parameters.json": "77593485df872804654eae54c91724ac5fd0a50b4afd33a625bf59d3a542d0a5",
    "cases.parameters.json": "de1effc78bc153e5e7ce88d242b9d8904700ecf2a656bd0d7df7b370454a6cdf",
    "environment.parameters.json": "f96d09a1eab2372a668e50d5a1ecee07faf2d7b70cacd3986ac4868b45379bed",
    "foundry.parameters.json": "ed5e8a14727de3595a0ab4bc5b0fcc4979c7d35b088536fce62f80651e59e99d",
    "operator.parameters.json": "78972401f11e209ef6bbdbba2c7cab95921b372e1dc570765d953aa01b2b2f90",
    "planted.parameters.json": "62ecf7282a7bf4c968db91a3943ba20a99dc7ac04fcabb7816aadf6f68f9759c",
    "recording.parameters.json": "1151a3f2462d5cd97d2f2d7be9839c8fdd4a9f6c84a7fd38c0b356cb35cc2064",
}
GOLDEN_OUTPUT = "e61ff4a4b1cae124c45659f163fdf20988ca4e526d89bf93206fd3f93c462f67"

FOUNDRY = (ROOT / "environment" / "foundry" / "main.bicep").read_text(encoding="utf-8")
CASES = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
CASES_CONFIG = (ROOT / "src" / "case-functions" / "cases" / "config.py").read_text(encoding="utf-8")


def build(env, models=None, preview=False, switch=False, full=True):
    """Runs the builder like the workflow does, with the AI Gateway's limits (full), and returns the exit code, what it printed, what it said and the files as bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, content in (("models.json", json.dumps(MODELS if models is None else models)), ("limits.json", json.dumps(LIMITS))):
            (tmp / name).write_text(content, encoding="utf-8")
        arguments = ["build", "--models", str(tmp / "models.json"), "--out-dir", str(tmp / "out"), *(["--preview"] if preview else [])]
        if full:
            arguments += ["--aigateway-policies", str(tmp / "limits.json")]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ep, "AGENTS_VIA_AI_GATEWAY", switch), redirect_stdout(out), redirect_stderr(err):
            code = ep.main(arguments, environ=env)
        # The builder writes the files with the platform's line ending (CRLF on Windows, LF on the runner): they are read with LF, so that the hashes are the same everywhere.
        files = {p.name: p.read_bytes().replace(b"\r\n", b"\n") for p in sorted((tmp / "out").glob("*.json"))} if (tmp / "out").exists() else {}
    return code, out.getvalue(), err.getvalue(), files


def values(files, name):
    return {k: v["value"] for k, v in json.loads(files[name])["parameters"].items()}


def outputs(out):
    return dict(line.split("=", 1) for line in out.splitlines())


def declared(text):
    return {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(r"^param (\w+) (\w+)(?: = (.+))?$", text, re.M)}


class TheSwitchIsOffAndNothingDiffers(unittest.TestCase):
    def test_the_switch_is_a_constant_of_the_builder_and_it_is_false(self):
        self.assertIs(ep.AGENTS_VIA_AI_GATEWAY, False, "a later change, after the owner's yes and after aigateway and aigateway-check have passed on the real estate, flips this one value")
        source = (ROOT / "tools" / "environment-params.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^AGENTS_VIA_AI_GATEWAY = (True|False)$", source)), 1, "one constant, one line")
        self.assertIn("AGENTS_VIA_AI_GATEWAY = False\n", source)

    def test_every_file_and_the_whole_output_are_what_they_were_byte_for_byte(self):
        code, out, err, files = build(SETTINGS)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual({name: hashlib.sha256(content).hexdigest() for name, content in files.items()}, GOLDEN)
        self.assertEqual(hashlib.sha256(out.encode("utf-8")).hexdigest(), GOLDEN_OUTPUT, "the key=value lines that the workflow reads are the same too")

    def test_what_the_switch_is_for_is_not_even_read_while_it_is_off(self):
        # A host name, a bad one, the name of the action: none of it changes a byte or is refused while the switch is False.
        for extra in ({"AIGATEWAY_HOST": HOST}, {"AIGATEWAY_HOST": "https://evil.example/x"}, {"ACTION": "foundry"}, {"ACTION": "foundry", "AIGATEWAY_HOST": ""}, {"ACTION": "aigateway"}):
            with self.subTest(extra=extra):
                code, out, err, files = build({**SETTINGS, **extra})
                self.assertEqual((code, err), (0, ""))
                self.assertEqual({name: hashlib.sha256(content).hexdigest() for name, content in files.items()}, GOLDEN)
                self.assertEqual(hashlib.sha256(out.encode("utf-8")).hexdigest(), GOLDEN_OUTPUT)
        without = {key: value for key, value in SETTINGS.items() if key != "FOUNDRY_PROJECT_PRINCIPAL_ID"}
        code, _, err, files = build({**without, "ACTION": "aigateway"})
        self.assertEqual((code, err), (0, ""), "no identity of the project is asked for while the switch is off")
        self.assertEqual(values(files, "aigateway.parameters.json")["foundryProjectPrincipalId"], "")

    def test_the_new_parameters_of_the_template_are_empty_so_that_a_file_that_does_not_carry_them_asks_for_nothing(self):
        params = declared(FOUNDRY)
        self.assertEqual(params["aiGatewayHost"], ("string", "''"))
        self.assertEqual(params["aiGatewayModels"], ("array", "[]"))
        self.assertEqual(params["aiGatewayConnectionName"], ("string", f"'{ep.AIGATEWAY_CONNECTION_NAME}'"))
        _, _, _, files = build(SETTINGS)
        given = values(files, "foundry.parameters.json")
        self.assertFalse({"aiGatewayHost", "aiGatewayModels", "aiGatewayConnectionName"} & set(given))
        self.assertEqual(set(given), {"location", "accountName", "projectName", "guardrailName", "models", "casesSystemPrincipalId", "owner"}, "the file of the Foundry resource is what it was")
        cases = values(files, "cases.parameters.json")
        self.assertFalse({"foundryModelInvestigator", "foundryModelSkeptic"} & set(cases), "the template's own defaults, the plain deployment names, apply")

    def test_no_output_is_added_while_it_is_off(self):
        _, out, _, _ = build(SETTINGS)
        self.assertFalse([key for key in outputs(out) if "ai_gateway" in key or key == "aigateway_connection_name"])
        self.assertEqual(len(out.splitlines()), 37)

    def test_a_switch_that_is_not_true_or_false_is_refused_by_name(self):
        for bad in ("False", "no", 0, 1, None, "true"):
            with self.subTest(bad=bad):
                code, out, err, files = build(SETTINGS, switch=bad)
                self.assertEqual((code, out, files), (2, "", {}))
                self.assertIn("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True or False", err)


class TheSwitchIsOn(unittest.TestCase):
    def on(self, **changes):
        env = {**SETTINGS, "ACTION": "foundry", "AIGATEWAY_HOST": HOST, **changes}
        env = {key: value for key, value in env.items() if value is not None}
        return build(env, switch=True)

    def test_the_foundry_file_asks_for_the_connection_with_the_host_and_the_aliases_and_the_rest_of_it_is_what_it_was(self):
        code, out, err, files = self.on()
        self.assertEqual((code, err), (0, ""))
        given = values(files, "foundry.parameters.json")
        self.assertEqual(given["aiGatewayHost"], HOST)
        self.assertEqual(given["aiGatewayModels"], [{"name": "gpt-6-luna", "version": "2026-09-22"}, {"name": "gpt-6.1-sol", "version": "2026-09-29"}], "the aliases are the deployments' names, with their versions")
        self.assertEqual({key: value for key, value in given.items() if not key.startswith("aiGateway")},
                         values(build(SETTINGS)[3], "foundry.parameters.json"), "everything else in the file is what it was")
        self.assertNotIn("aiGatewayConnectionName", given, "the name is the template's own default")
        self.assertEqual({k: hashlib.sha256(v).hexdigest() for k, v in files.items() if k not in ("foundry.parameters.json", "cases.parameters.json")},
                         {k: v for k, v in GOLDEN.items() if k not in ("foundry.parameters.json", "cases.parameters.json")}, "no other file differs")

    def test_the_cases_file_names_the_models_through_the_connection_and_nothing_else_of_it_differs(self):
        code, out, err, files = self.on()
        self.assertEqual((code, err), (0, ""))
        cases = values(files, "cases.parameters.json")
        self.assertEqual((cases["foundryModelInvestigator"], cases["foundryModelSkeptic"]), ("aigateway/gpt-6.1-sol", "aigateway/gpt-6-luna"))
        plain = values(build(SETTINGS)[3], "cases.parameters.json")
        self.assertEqual({k: v for k, v in cases.items() if not k.startswith("foundryModel")}, plain)
        self.assertNotEqual(cases["foundryModelInvestigator"].lower(), cases["foundryModelSkeptic"].lower(), "the Skeptic is another model than the Investigator")
        self.assertNotIn("modelDetective", cases, "the older Detective and the Skeptic call the deployments of the project directly, with the template's default names")

    def test_the_workflow_is_told_that_it_is_on_and_the_name_of_the_connection_and_nothing_else_is_added(self):
        _, out, _, _ = self.on()
        printed = outputs(out)
        self.assertEqual((printed["agents_via_ai_gateway"], printed["aigateway_connection_name"]), ("true", "aigateway"))
        _, off, _, _ = build(SETTINGS)
        self.assertEqual({k: v for k, v in printed.items() if k not in ("agents_via_ai_gateway", "aigateway_connection_name")}, outputs(off))
        self.assertNotIn(HOST, out, "the host name is not printed")

    def test_the_host_is_lower_cased_and_trimmed_and_must_be_under_the_services_domain(self):
        code, _, err, files = self.on(AIGATEWAY_HOST=f"  {HOST.upper()} ")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(values(files, "foundry.parameters.json")["aiGatewayHost"], HOST)
        code, _, err, files = self.on(AIGATEWAY_HOST=f"{HOST}\n")
        self.assertEqual((code, err), (0, ""), "white space around it is trimmed")
        for bad in ("evil.example.com", f"{HOST}.evil.example.com", f"https://{HOST}", f"{HOST}/default", f"{HOST}:443", ".ai.gateway.azure.com", "ai.gateway.azure.com",
                    f"a b.{HOST}", "x" * 250 + ".ai.gateway.azure.com", "-x.ai.gateway.azure.com", "x_y.ai.gateway.azure.com"):
            with self.subTest(bad=bad[:40]):
                code, out, err, files = self.on(AIGATEWAY_HOST=bad)
                self.assertEqual((code, out, files), (2, "", {}))
                self.assertIn("AIGATEWAY_HOST is the host name that the service reports for the AI Gateway, under .ai.gateway.azure.com", err)
                if bad not in "under .ai.gateway.azure.com":
                    self.assertNotIn(bad, err, "the value is not echoed")

    def test_the_action_that_makes_the_connection_is_refused_without_a_host_and_says_what_to_do(self):
        for missing in (None, "", "   "):
            with self.subTest(missing=missing):
                code, out, err, files = self.on(AIGATEWAY_HOST=missing)
                self.assertEqual((code, out, files), (2, "", {}))
                self.assertIn("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True and the AI Gateway cannot be named", err)
                self.assertIn("Run the action aigateway first", err)
                self.assertIn("or set the constant back to False", err)

    def test_the_action_that_gives_the_projects_identity_its_role_is_refused_without_the_identity(self):
        for missing in (None, "", " "):
            with self.subTest(missing=missing):
                code, out, err, files = self.on(ACTION="aigateway", AIGATEWAY_HOST=None, FOUNDRY_PROJECT_PRINCIPAL_ID=missing)
                self.assertEqual((code, out, files), (2, "", {}))
                self.assertIn("is True and FOUNDRY_PROJECT_PRINCIPAL_ID is not set", err)
                self.assertIn("Run the action foundry first", err)
        code, _, err, files = self.on(ACTION="aigateway", AIGATEWAY_HOST=None, FOUNDRY_PROJECT_PRINCIPAL_ID=PROJECT_PRINCIPAL.upper())
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(values(files, "aigateway.parameters.json")["foundryProjectPrincipalId"], PROJECT_PRINCIPAL.lower(), "the template gives it AI Gateway Models User on the gateway")

    def test_a_preview_and_every_action_that_needs_neither_go_on_without_them(self):
        for action, preview in (("foundry", True), ("aigateway", True), ("what-if", False), ("cases", False), ("recording", False), ("operator", False), ("model-side", False), ("", False)):
            with self.subTest(action=action, preview=preview):
                env = {**SETTINGS, "ACTION": action}
                env.pop("FOUNDRY_PROJECT_PRINCIPAL_ID")
                code, out, err, files = build(env, preview=preview, switch=True)
                self.assertEqual((code, err), (0, ""))
                self.assertFalse({"aiGatewayHost", "aiGatewayModels"} & set(values(files, "foundry.parameters.json")), "no host, so no connection is asked for")
                self.assertEqual(values(files, "cases.parameters.json")["foundryModelInvestigator"], "aigateway/gpt-6.1-sol")
                self.assertEqual(outputs(out)["agents_via_ai_gateway"], "true", "the workflow reads that the switch is on from the first, preview, run")

    def test_an_object_id_that_is_not_one_is_still_refused_and_never_echoed(self):
        code, out, err, files = self.on(ACTION="aigateway", FOUNDRY_PROJECT_PRINCIPAL_ID="not-a-guid-secret")
        self.assertEqual((code, files), (2, {}))
        self.assertIn("FOUNDRY_PROJECT_PRINCIPAL_ID", err)
        self.assertNotIn("secret", err)

    def test_the_models_of_the_agents_have_to_be_deployed_so_that_every_name_is_an_alias_of_the_gateway(self):
        others = [dict(m, name=name) for m, name in zip(MODELS, ("alpha", "beta"))]
        code, out, err, files = build({**SETTINGS, "ACTION": "foundry", "AIGATEWAY_HOST": HOST}, models=others, switch=True, full=False)
        self.assertEqual((code, out, files), (2, "", {}))
        self.assertIn("the models of the agents (gpt-6.1-sol, gpt-6-luna) are not in environment/models.json: there is no alias to name", err)
        code, _, _, _ = build({**SETTINGS, "ACTION": "foundry", "AIGATEWAY_HOST": HOST}, models=others, switch=False, full=False)
        self.assertEqual(code, 0, "while the switch is off the names of the models do not matter here")

    def test_nothing_secret_is_in_the_files_of_the_switch(self):
        _, _, _, files = self.on()
        for name in ("foundry.parameters.json", "cases.parameters.json"):
            text = files[name].decode("utf-8").lower()
            for word in ("secret", "password", "connectionstring", "token", "apikey", "sas"):
                self.assertNotIn(word, text, f"{word} in {name}")
        self.assertNotIn('"key"', files["foundry.parameters.json"].decode("utf-8").lower(), "no key: the connection uses the project's identity")

    def test_the_aliases_of_the_connection_the_aliases_of_the_gateway_and_the_names_of_the_app_are_the_same_strings(self):
        _, out, _, files = self.on()
        aliases = outputs(out)["aigateway_aliases"].split()
        self.assertEqual([m["name"] for m in values(files, "foundry.parameters.json")["aiGatewayModels"]], aliases)
        cases = values(files, "cases.parameters.json")
        for name in (cases["foundryModelInvestigator"], cases["foundryModelSkeptic"]):
            connection, alias = name.split("/")
            self.assertEqual(connection, ep.AIGATEWAY_CONNECTION_NAME)
            self.assertIn(alias, aliases)
            self.assertRegex(name, r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", "what the app accepts (cases/config.py)")

    def test_the_files_fit_the_templates_names_and_types(self):
        _, _, _, files = self.on()
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, text in (("foundry.parameters.json", FOUNDRY), ("cases.parameters.json", CASES)):
            params = declared(text)
            given = json.loads(files[name])["parameters"]
            self.assertTrue(set(given) <= set(params), set(given) - set(params))
            self.assertTrue({k for k, (_, default) in params.items() if default is None} <= set(given))
            for key, wrapped in given.items():
                self.assertIsInstance(wrapped["value"], types[params[key][0]], key)


class TheThreeNamesAreOneName(unittest.TestCase):
    def test_the_connection_name_of_the_builder_is_the_default_of_the_template(self):
        self.assertEqual(ep.AIGATEWAY_CONNECTION_NAME, "aigateway")
        self.assertIn(f"param aiGatewayConnectionName string = '{ep.AIGATEWAY_CONNECTION_NAME}'", FOUNDRY)

    def test_the_two_models_of_the_agents_are_the_defaults_of_the_cases_template_and_of_the_app_and_are_deployed(self):
        template = dict(re.findall(r"^param (foundryModelInvestigator|foundryModelSkeptic) string = '([^']+)'$", CASES, re.M))
        self.assertEqual(template, ep.AGENT_MODELS)
        self.assertEqual(re.search(r'(?m)^DEFAULT_MODEL_INVESTIGATOR = "([^"]+)"$', CASES_CONFIG).group(1), ep.AGENT_MODELS["foundryModelInvestigator"])
        self.assertEqual(re.search(r'(?m)^DEFAULT_MODEL_SKEPTIC = "([^"]+)"$', CASES_CONFIG).group(1), ep.AGENT_MODELS["foundryModelSkeptic"])
        deployed = {m["name"] for m in json.loads((ROOT / "environment" / "models.json").read_text(encoding="utf-8"))}
        self.assertTrue(set(ep.AGENT_MODELS.values()) <= deployed, "an alias exists for each of them (environment/aigateway/main.bicep makes one for each model of models.json)")

    def test_the_host_pattern_is_the_one_that_the_workflow_and_the_check_ask_for(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8")
        shell = r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.ai\.gateway\.azure\.com$"
        self.assertIn(shell, workflow)
        for host in (HOST, "a.ai.gateway.azure.com"):
            self.assertTrue(ep.AIGATEWAY_HOST.match(host), host)
            self.assertTrue(re.match(shell, host), host)
        for host in ("evil.example.com", ".ai.gateway.azure.com", "Aigw.ai.gateway.azure.com", f"{HOST}/default"):
            self.assertFalse(ep.AIGATEWAY_HOST.match(host), host)
            self.assertFalse(re.match(shell, host), host)


if __name__ == "__main__":
    unittest.main()
