"""The parameter builder of the AI security (tools/environment-params.py --governance): the access list of the gateway (environment/aigateway/contracts.json) checked against the models, the policies and the
templates, the files for the governance and the telemetry templates, and the release that the action cases records (BUILD_COMMIT and PACKAGE_SHA256). Run in this process with fixed inputs; no test calls Azure."""
import copy
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
spec = importlib.util.spec_from_file_location("environment_params_of_the_governance", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

SETTINGS = {
    "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "ENV_RESOURCE_GROUP": "rg-example", "ENV_LOCATION": "swedencentral", "ENV_VNET_PREFIX": "10.53.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27",
    "ENV_DNS_SERVERS": "10.20.0.4", "ENV_OWNER": "owner@example.com", "ENV_BUDGET_AMOUNT": "25", "ENV_ALERT_EMAILS": "owner@example.com,second@example.com", "ENV_BUDGET_START": "2026-11-01",
    "CASES_SYSTEM_PRINCIPAL_ID": "12345678-dddd-eeee-ffff-123456789012", "FOUNDRY_PROJECT_PRINCIPAL_ID": "12345678-eeee-ffff-1111-123456789012", "OPERATOR_PRINCIPAL_ID": "12345678-aaaa-bbbb-cccc-123456789012",
    "AIGATEWAY_HOST": "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com", "ENV_FOUNDRY_DIAGNOSTICS_EXIST": "true", "GUARDRAIL_INITIATIVE_AVAILABLE": "true", "ACTION": "governance",
}
MODELS = ROOT / "environment" / "models.json"
POLICIES = ROOT / "environment" / "aigateway" / "policies.json"
CONTRACTS = ROOT / "environment" / "aigateway" / "contracts.json"
GOVERNANCE = (ROOT / "environment" / "governance" / "main.bicep").read_text(encoding="utf-8")
TELEMETRY = (ROOT / "environment" / "aigateway" / "telemetry.bicep").read_text(encoding="utf-8")
GATEWAY = (ROOT / "environment" / "aigateway" / "main.bicep").read_text(encoding="utf-8")
CASES = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")


def params_of(source):
    return {m.group(1): (m.group(2), m.group(3) is not None) for m in re.finditer(r"(?m)^param (\w+) (\w+)( = .+)?$", source)}


def build(env=None, contracts=CONTRACTS, extra=(), constants=None):
    env = SETTINGS if env is None else env
    constants = constants or {}
    with tempfile.TemporaryDirectory() as tmp:
        out, err = io.StringIO(), io.StringIO()
        patches = [mock.patch.object(ep, name, value) for name, value in constants.items()]
        for patch in patches:
            patch.start()
        try:
            arguments = ["build", "--models", str(MODELS), "--out-dir", tmp, "--aigateway-policies", str(POLICIES), *extra]
            if contracts is not None:
                arguments += ["--governance", str(contracts)]
            with redirect_stdout(out), redirect_stderr(err):
                code = ep.main(arguments, environ=env)
        finally:
            for patch in patches:
                patch.stop()
        files = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in Path(tmp).glob("*.json")}
    outputs = dict(line.split("=", 1) for line in out.getvalue().splitlines())
    return code, outputs, err.getvalue(), files


def values(document):
    return {k: v["value"] for k, v in document["parameters"].items()}


class TheAccessListIsHonest(unittest.TestCase):
    def read(self, change=None):
        document = json.loads(CONTRACTS.read_text(encoding="utf-8"))
        if change:
            change(document)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contracts.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            models = ep.read_models(MODELS)
            return ep.read_contracts(path, models, ep.read_aigateway_policies(POLICIES, models))

    def refused(self, change, words):
        with self.assertRaises(ep.Problem) as stopped:
            self.read(change)
        self.assertIn(words, str(stopped.exception))

    def test_the_file_of_the_repository_is_accepted_and_names_the_three_identities_that_hold_the_role(self):
        document = self.read()
        self.assertEqual({e["identity"] for e in document["contracts"]}, set(ep.CONTRACT_IDENTITIES))
        self.assertEqual([e["id"] for e in document["contracts"]], ["AC1", "AC2", "AC3"])

    def test_every_alias_is_a_model_every_limit_is_a_policy_and_every_policy_is_named(self):
        self.refused(lambda d: d["contracts"][0]["aliases"].append("gpt-9"), "gpt-9 is not a model of environment/models.json")
        self.refused(lambda d: d["contracts"][0]["limits"].pop(), "the limits of the entry are the policies")
        self.refused(lambda d: d["contracts"][1]["limits"].append({"type": "costLimit", "id": "meternaut-week"}), "the limits of the entry are the policies")
        self.refused(lambda d: d["contracts"][2]["limits"][3].update(id="meternaut-day"), "the limits of the entry are the policies")
        self.refused(lambda d: d["contracts"][0]["limits"].append({"type": "tokenLimit"}), "the limits of the entry are the policies")

    def test_one_entry_for_each_identity_and_a_caller_name_that_is_safe_to_print(self):
        self.refused(lambda d: d["contracts"][1].update(identity="cases"), "no two entries share one")
        self.refused(lambda d: d["contracts"][1].update(identity="somebody"), "the identity is one of")
        self.refused(lambda d: d["contracts"].pop(), "has an entry for each identity")
        for bad in ("It's a name", 'a "quote"', "x\ny", "a;b", ""):
            with self.subTest(bad=bad):
                self.refused(lambda d, b=bad: d["contracts"][0].update(caller=b), "the caller has its own short name")
        self.refused(lambda d: d["contracts"][1].update(caller=d["contracts"][0]["caller"]), "the caller has its own short name")

    def test_the_review_comes_from_an_event_and_never_from_a_date_or_a_period(self):
        for bad in ("Every 6 months a person looks at it", "A review on 2027-01-15", "Reviewed monthly", "Quarterly review", "every 30 days"):
            with self.subTest(bad=bad):
                self.refused(lambda d, b=bad: d["contracts"][0].update(reviewTrigger=b + " and more words to be long enough"), "never from a date or a period")

    def test_the_shape_the_role_and_the_text_fields_are_checked(self):
        self.refused(lambda d: d.update(version=2), "version 1")
        self.refused(lambda d: d["gatewayRole"].update(id="00000000-0000-0000-0000-000000000000"), "AI Gateway Models User")
        self.refused(lambda d: d["contracts"][0].pop("owner"), "has exactly")
        self.refused(lambda d: d["contracts"][0].update(extra="x"), "has exactly")
        self.refused(lambda d: d["contracts"][0].update(purpose="short"), "purpose is a sentence or two")
        self.refused(lambda d: d.pop("about"), "has exactly")
        self.refused(lambda d: d["identities"].pop("operator"), "the identities of the access list are")
        self.refused(lambda d: d["contracts"][0].update(aliases=[]), "aliases is a list")

    def test_the_role_of_the_file_is_the_one_that_the_template_gives_to_each_identity(self):
        document = json.loads(CONTRACTS.read_text(encoding="utf-8"))
        self.assertEqual(document["gatewayRole"]["id"], ep.GATEWAY_MODELS_USER_ROLE)
        self.assertIn(f"var aiGatewayModelsUserRoleId = '{ep.GATEWAY_MODELS_USER_ROLE}'", GATEWAY)
        for resource in ("operatorCallsTheModels", "projectCallsTheModels", "casesCallsTheModels"):
            self.assertIn(f"resource {resource} ", GATEWAY)
        self.assertEqual(GATEWAY.count("roleDefinitions', aiGatewayModelsUserRoleId"), len(document["contracts"]), "one assignment of the role for each entry of the list")

    def test_every_entry_says_who_owns_it_what_it_may_send_and_what_makes_a_person_look_at_it_again_and_holds_no_key(self):
        document = json.loads(CONTRACTS.read_text(encoding="utf-8"))
        for entry in document["contracts"]:
            for field in ("purpose", "owner", "dataClass", "reviewTrigger"):
                self.assertTrue(entry[field].strip(), (entry["id"], field))
            self.assertRegex(entry["dataClass"], r"(?i)no name|no text|typed|fixed", "typed facts only: no text that somebody wrote in the estate (AGENTS.md rule 26 (d))")
        self.assertNotRegex(json.dumps(document), r"(?i)\"(api[-_]?key|secret|password)\"")
        self.assertIn("No entry holds a key or a connection string", document["about"])


class TheFilesOfTheGovernanceAndTheTelemetry(unittest.TestCase):
    def test_a_build_with_the_access_list_writes_the_two_files_and_says_what_it_made(self):
        code, outputs, err, files = build()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("governance.parameters.json", files)
        self.assertIn("gateway-telemetry.parameters.json", files)
        self.assertEqual(outputs["governance_files"], "true")
        self.assertEqual(outputs["governance_callers"], "3")
        self.assertEqual(outputs["governance_callers_missing"], "")
        self.assertEqual((outputs["governance_approved_models_effect"], outputs["governance_model_eligibility_effect"]), ("Audit", "Audit"))
        self.assertEqual(outputs["governance_guardrail_initiative"], "true")

    def test_a_build_without_it_writes_neither_file_and_adds_no_line(self):
        code, outputs, err, files = build(contracts=None)
        self.assertEqual((code, err), (0, ""))
        self.assertFalse({"governance.parameters.json", "gateway-telemetry.parameters.json"} & set(files))
        self.assertFalse([k for k in outputs if k.startswith("governance_")])

    def test_the_governance_file_fits_its_template_and_holds_what_the_workflow_reads_and_nothing_secret(self):
        _, _, _, files = build()
        given = files["governance.parameters.json"]["parameters"]
        declared = params_of(GOVERNANCE)
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))
        self.assertTrue({k for k, (_, has_default) in declared.items() if not has_default} <= set(given))
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in given.items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)
        values_ = values(files["governance.parameters.json"])
        self.assertEqual(values_["alertEmails"], ["owner@example.com", "second@example.com"])
        self.assertEqual(values_["approvedModelAssetIds"], [f"azureml://registries/azure-openai/models/{m['name']}/" for m in ep.read_models(MODELS)], "a slash at the end matches every version of that model and no other")
        self.assertEqual((values_["tokenLimitPerMinute"], values_["requestLimitPerMinute"]), (50000, 60), "from environment/aigateway/policies.json")
        self.assertEqual([c["name"] for c in values_["callers"]], ["Judges of the cases app", "Agents in Foundry", "The check of the Operator"])
        self.assertEqual(values_["callers"][0], {"name": "Judges of the cases app", "objectId": SETTINGS["CASES_SYSTEM_PRINCIPAL_ID"], "aliases": ["gpt-6-luna", "gpt-6.1-sol"]})
        self.assertEqual((values_["approvedModelsEffect"], values_["modelEligibilityEffect"]), ("Audit", "Audit"))
        self.assertEqual((values_["auditCustomerManagedKeys"], values_["landingZoneDiagnostics"], values_["guardrailInitiative"]), (False, True, True))
        self.assertNotIn("workload", values_)

    def test_the_telemetry_file_fits_its_template_and_names_the_gateway_by_the_name_of_the_other_actions(self):
        _, outputs, _, files = build()
        given = files["gateway-telemetry.parameters.json"]["parameters"]
        declared = params_of(TELEMETRY)
        self.assertTrue(set(given) <= set(declared))
        self.assertTrue({k for k, (_, has_default) in declared.items() if not has_default} <= set(given))
        self.assertEqual(values(files["gateway-telemetry.parameters.json"]), {"gatewayName": outputs["aigateway_name"]})
        self.assertEqual(values(files["gateway-telemetry.parameters.json"])["gatewayName"], values(files["aigateway.parameters.json"])["gatewayName"])

    def test_the_two_switches_and_the_flags_of_the_tenant_decide_the_optional_policies(self):
        for preview_switch, available, expected in ((True, "true", True), (True, "false", False), (False, "true", False), (True, "", False)):
            with self.subTest(switch=preview_switch, available=available):
                _, outputs, _, files = build(env={**SETTINGS, "GUARDRAIL_INITIATIVE_AVAILABLE": available}, constants={"GUARDRAIL_INITIATIVE_PREVIEW": preview_switch})
                self.assertEqual(values(files["governance.parameters.json"])["guardrailInitiative"], expected)
                self.assertEqual(outputs["governance_guardrail_initiative"], "true" if expected else "false")
        _, _, _, files = build(constants={"AUDIT_CUSTOMER_MANAGED_KEYS": True})
        self.assertIs(values(files["governance.parameters.json"])["auditCustomerManagedKeys"], True)
        _, _, _, files = build(env={**SETTINGS, "ENV_FOUNDRY_DIAGNOSTICS_EXIST": "false"})
        self.assertIs(values(files["governance.parameters.json"])["landingZoneDiagnostics"], False)
        code, _, err, _ = build(env={**SETTINGS, "ENV_FOUNDRY_DIAGNOSTICS_EXIST": "maybe"})
        self.assertEqual(code, 2)
        self.assertIn("ENV_FOUNDRY_DIAGNOSTICS_EXIST is true or false", err)

    def test_the_effects_are_audit_or_deny_and_nothing_else(self):
        _, _, _, files = build(constants={"APPROVED_MODELS_EFFECT": "Deny"})
        self.assertEqual(values(files["governance.parameters.json"])["approvedModelsEffect"], "Deny")
        for bad in ("Disabled", "Modify", "audit", None):
            with self.subTest(bad=bad):
                code, _, err, files = build(constants={"MODEL_ELIGIBILITY_EFFECT": bad})
                self.assertEqual((code, files), (2, {}))
                self.assertIn("MODEL_ELIGIBILITY_EFFECT (in tools/environment-params.py) is Audit or Deny", err)
        for name in ("GUARDRAIL_INITIATIVE_PREVIEW", "AUDIT_CUSTOMER_MANAGED_KEYS"):
            code, _, err, _ = build(constants={name: "yes"})
            self.assertEqual(code, 2, name)
            self.assertIn(f"{name} (in tools/environment-params.py) is True or False", err)

    def test_the_constants_of_the_repository_are_the_ones_the_design_gave(self):
        self.assertEqual((ep.APPROVED_MODELS_EFFECT, ep.MODEL_ELIGIBILITY_EFFECT), ("Audit", "Audit"), "audit first: the owner changes the line to Deny after a clean run")
        self.assertIs(ep.GUARDRAIL_INITIATIVE_PREVIEW, True)
        self.assertIs(ep.AUDIT_CUSTOMER_MANAGED_KEYS, False, "the owner has not decided on customer-managed keys")
        source = (ROOT / "tools" / "environment-params.py").read_text(encoding="utf-8")
        for name in ("APPROVED_MODELS_EFFECT", "MODEL_ELIGIBILITY_EFFECT", "GUARDRAIL_INITIATIVE_PREVIEW", "AUDIT_CUSTOMER_MANAGED_KEYS", "GATEWAY_TELEMETRY"):
            self.assertEqual(len(re.findall(rf"(?m)^{name} = ", source)), 1, f"{name}: one constant, one line")


class TheIdentitiesOfTheAccessList(unittest.TestCase):
    def without(self, *names):
        return {k: v for k, v in SETTINGS.items() if k not in names}

    def test_the_action_governance_is_refused_without_an_identity_and_says_which_action_makes_it(self):
        for name, maker in (("CASES_SYSTEM_PRINCIPAL_ID", "cases"), ("FOUNDRY_PROJECT_PRINCIPAL_ID", "foundry"), ("OPERATOR_PRINCIPAL_ID", "operator")):
            with self.subTest(missing=name):
                code, _, err, files = build(env=self.without(name))
                self.assertEqual((code, files), (2, {}))
                self.assertIn("needs the object id of every identity on it", err)
                self.assertIn(f"{maker} (the ", err)
        code, _, err, _ = build(env=self.without("CASES_SYSTEM_PRINCIPAL_ID", "OPERATOR_PRINCIPAL_ID"))
        self.assertEqual(code, 2)
        self.assertIn("cases (the ", err)
        self.assertIn("operator (the ", err)

    def test_a_preview_and_every_other_action_go_on_with_the_identities_that_are_known(self):
        for extra, action in (((), "what-if"), (("--preview",), "governance"), ((), "gateway-telemetry"), ((), "drift-check")):
            with self.subTest(action=action, extra=extra):
                env = {**self.without("OPERATOR_PRINCIPAL_ID", "CASES_SYSTEM_PRINCIPAL_ID"), "ACTION": action}
                code, outputs, err, files = build(env=env, extra=extra)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(outputs["governance_callers"], "1")
                self.assertEqual(outputs["governance_callers_missing"], "cases,operator")
                self.assertEqual([c["name"] for c in values(files["governance.parameters.json"])["callers"]], ["Agents in Foundry"])

    def test_an_object_id_that_is_not_one_is_refused_and_never_echoed(self):
        code, _, err, files = build(env={**SETTINGS, "OPERATOR_PRINCIPAL_ID": "not-a-guid-40404040"})
        self.assertEqual((code, files), (2, {}))
        self.assertIn("OPERATOR_PRINCIPAL_ID is the object id of the", err)
        self.assertNotIn("40404040", err)

    def test_the_object_ids_are_written_in_lower_case_as_the_oid_claim_of_a_token_is(self):
        _, _, _, files = build(env={**SETTINGS, "CASES_SYSTEM_PRINCIPAL_ID": SETTINGS["CASES_SYSTEM_PRINCIPAL_ID"].upper()})
        self.assertEqual(values(files["governance.parameters.json"])["callers"][0]["objectId"], SETTINGS["CASES_SYSTEM_PRINCIPAL_ID"])

    def test_the_options_go_together_and_a_file_that_is_not_readable_is_refused(self):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(out), redirect_stderr(err):
            code = ep.main(["build", "--models", str(MODELS), "--out-dir", tmp, "--governance", str(CONTRACTS)], environ=SETTINGS)
        self.assertEqual(code, 2)
        self.assertIn("--governance goes with --aigateway-policies", err.getvalue())
        code, _, err, _ = build(contracts=ROOT / "environment" / "aigateway" / "nowhere.json")
        self.assertEqual(code, 2)
        self.assertIn("is not a readable JSON document", err)


class ThePerMinuteLimitsOfTheNearLimitRule(unittest.TestCase):
    def test_the_limits_are_read_from_the_policies_and_a_period_that_the_rule_cannot_read_is_refused(self):
        policies = ep.read_aigateway_policies(POLICIES, ep.read_models(MODELS))
        self.assertEqual(ep.per_minute_limits(policies), (50000, 60))
        hourly = copy.deepcopy(policies)
        next(p for p in hourly if p["type"] == "tokenLimit").update(period="hour", count=3000000)
        with self.assertRaises(ep.Problem) as stopped:
            ep.per_minute_limits(hourly)
        self.assertIn("per minute", str(stopped.exception))
        slow = copy.deepcopy(policies)
        next(p for p in slow if p["type"] == "requestRateLimit").update(periodSeconds=3600, callsPerPeriod=100)
        with self.assertRaises(ep.Problem):
            ep.per_minute_limits(slow)


class TheReleaseThatTheActionCasesRecords(unittest.TestCase):
    COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
    DIGEST = "0123456789abcdef" * 4

    def test_the_commit_and_the_digest_go_into_the_cases_file_only_when_the_workflow_sets_them(self):
        _, _, _, files = build(env={**SETTINGS, "BUILD_COMMIT": self.COMMIT, "PACKAGE_SHA256": self.DIGEST.upper()}, contracts=None)
        cases = values(files["cases.parameters.json"])
        self.assertEqual((cases["buildCommit"], cases["packageSha256"]), (self.COMMIT, self.DIGEST), "in lower case")
        _, _, _, files = build(contracts=None)
        self.assertFalse({"buildCommit", "packageSha256"} & set(values(files["cases.parameters.json"])))
        _, _, _, files = build(env={**SETTINGS, "BUILD_COMMIT": self.COMMIT}, contracts=None)
        self.assertEqual({"buildCommit"} & set(values(files["cases.parameters.json"])), {"buildCommit"})
        self.assertNotIn("packageSha256", values(files["cases.parameters.json"]))

    def test_a_value_that_is_not_a_commit_or_a_digest_is_refused_and_never_echoed(self):
        for name, bad in (("BUILD_COMMIT", "main"), ("BUILD_COMMIT", "g" * 40), ("BUILD_COMMIT", self.COMMIT[:39]), ("PACKAGE_SHA256", "abc"), ("PACKAGE_SHA256", "x" * 64)):
            with self.subTest(name=name, bad=bad[:10]):
                code, _, err, files = build(env={**SETTINGS, name: bad}, contracts=None)
                self.assertEqual((code, files), (2, {}))
                self.assertIn(name, err)
                self.assertNotIn(bad, err)

    def test_the_template_takes_them_as_the_two_app_settings_writes_them_only_when_given_and_leaves_the_tags_to_the_workflow(self):
        declared = params_of(CASES)
        self.assertEqual((declared["buildCommit"], declared["packageSha256"]), (("string", True), ("string", True)), "empty means none: a deploy that does not carry them writes none")
        self.assertRegex(CASES, r"(?m)^@maxLength\(64\)\nparam packageSha256 string = ''$")
        for word in ("BUILD_COMMIT", "PACKAGE_SHA256", "buildSettings", "concat(empty(buildCommit) ? [] : [", "empty(packageSha256) ? [] : ["):
            self.assertIn(word, CASES, word)
        code = re.sub(r"(?m)^\s*//.*$", "", CASES)
        self.assertNotIn("meternaut-build-commit", code, "the tags say which release has been published, and the workflow writes them after the publish: a deploy that is followed by a publish that fails must not say otherwise")
        self.assertNotIn("buildTags", code)

    def test_the_cases_file_still_fits_its_template(self):
        _, _, _, files = build(env={**SETTINGS, "BUILD_COMMIT": self.COMMIT, "PACKAGE_SHA256": self.DIGEST}, contracts=None)
        given = files["cases.parameters.json"]["parameters"]
        declared = params_of(CASES)
        self.assertTrue(set(given) <= set(declared), set(given) - set(declared))


if __name__ == "__main__":
    unittest.main()
