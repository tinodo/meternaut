"""tools/drift-check.py: the control-plane half of the drift check of Meternaut's AI security (docs/proposals/10-ai-security-and-governance.md).

The tool is run here against a fake estate that is as the repository says (the tool's own `fake_estate`, whose shapes are those that the real services answered with when the tool was read-tested against
the real estate, 2026-11-08), with one thing broken at a time. No test calls Azure."""
import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "drift-check.py"
spec = importlib.util.spec_from_file_location("drift_check", TOOL)
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

MODELS, POLICIES, ACCESS, NAMES = dc.selftest_inputs()
BASE = f"/subscriptions/{dc.SELFTEST_SUBSCRIPTION}/resourceGroups/{dc.SELFTEST_GROUP}"
ACCOUNT = f"{BASE}/providers/Microsoft.CognitiveServices/accounts/{NAMES['account']}"
GATEWAY = f"{BASE}/providers/Microsoft.ApiManagement/aigateways/{NAMES['gateway']}"
SITE = f"{BASE}/providers/Microsoft.Web/sites/{NAMES['cases_app']}"
PROJECT = f"{ACCOUNT}/projects/{NAMES['project']}"
PROJECT_ROLES = f"{PROJECT}/providers/Microsoft.Authorization/roleAssignments"
OPERATOR = dc.SELFTEST_IDS["operator"]
GOVERNANCE = (ROOT / "environment" / "governance" / "main.bicep").read_text(encoding="utf-8")
TELEMETRY = (ROOT / "environment" / "aigateway" / "telemetry.bicep").read_text(encoding="utf-8")
CASES = (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
AIGATEWAY = (ROOT / "environment" / "aigateway" / "main.bicep").read_text(encoding="utf-8")
SOURCE = TOOL.read_text(encoding="utf-8")


def world(change=None, graph_rows=None, app_rows="healthy", **options):
    estate = dc.fake_estate(MODELS, POLICIES, NAMES)
    if change:
        change(estate)
    az = dc.FakeAz(estate, graph_rows=graph_rows, app_rows=dc.healthy_rows() if app_rows == "healthy" else app_rows)
    ctx = dc.selftest_context(az, MODELS, POLICIES, ACCESS, **options)
    results, closed = dc.run_controls(ctx)
    return {r["control"]: r for r in results}, closed, az, ctx


class TheReportHasTheSharedShape(unittest.TestCase):
    def test_every_control_gives_exactly_the_five_fields_of_the_shared_report_and_its_id_is_ours(self):
        results, closed, _, ctx = world()
        for control_id, result in results.items():
            self.assertEqual(set(result), {"control", "layer", "state", "detail", "readAt"}, control_id)
            self.assertRegex(control_id, r"^I-[a-z0-9-]+$", "the ids of this half begin with I-, as the agent harness' begin with A-")
            self.assertIn(result["layer"], ("L1", "L2", "L3", "L4"))
            self.assertIn(result["state"], ("PASS", "FAIL", "UNKNOWN"))
            self.assertGreater(len(result["detail"]), 20, "a control says what it read")
            self.assertRegex(result["readAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(len(results), len(dc.CONTROLS))
        self.assertEqual(len({c for c, _, _ in dc.CONTROLS}), len(dc.CONTROLS), "no two controls share an id")
        report = dc.report_of(list(results.values()), closed, ctx)
        self.assertEqual(set(report), {"report", "readAt", "summary", "failClosed", "controls"})
        self.assertEqual(sum(report["summary"].values()), len(results))

    def test_the_four_layers_of_the_citadel_blueprint_are_all_watched(self):
        self.assertEqual({layer for _, layer, _ in dc.CONTROLS}, {"L1", "L2", "L3", "L4"})

    def test_a_healthy_estate_has_no_fail_and_says_unknown_only_for_what_this_identity_may_not_read(self):
        results, closed, _, _ = world()
        self.assertEqual([c for c, r in results.items() if r["state"] == "FAIL"], [])
        self.assertEqual(closed, set())
        self.assertEqual({c for c, r in results.items() if r["state"] == "UNKNOWN"}, {"I-defender", "I-entra-console", "I-entra-agents"})
        self.assertEqual(sum(r["state"] == "PASS" for r in results.values()), len(dc.CONTROLS) - 3)

    def test_the_selftest_of_the_tool_passes(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = dc.main(["--selftest"])
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertIn("breakages each say FAIL", out.getvalue())


class EveryBreakageIsFoundByTheControlThatWatchesIt(unittest.TestCase):
    def failing(self, control_id, change, words=(), closed=True, **options):
        results, closed_set, _, _ = world(change, **options)
        self.assertEqual(results[control_id]["state"], "FAIL", (control_id, results[control_id]["detail"]))
        for word in words:
            self.assertIn(word, results[control_id]["detail"])
        self.assertEqual(control_id in closed_set, closed, control_id)
        for other, result in results.items():
            if other != control_id and other not in ("I-inapp-results",):
                self.assertNotEqual(result["state"], "FAIL", f"{other} should not care about a break that {control_id} watches: {result['detail']}")

    def test_the_foundry_resource_taking_public_traffic_or_keys(self):
        self.failing("I-foundry-flags", lambda e: e[ACCOUNT]["properties"].update(publicNetworkAccess="Enabled"), ("public network access",))
        self.failing("I-foundry-flags", lambda e: e[ACCOUNT]["properties"].update(disableLocalAuth=False), ("local authentication",))
        self.failing("I-foundry-flags", lambda e: e[ACCOUNT]["properties"]["networkAcls"].update(ipRules=[{"value": "1.2.3.4"}]), ("address range",))

    def test_a_deployment_that_is_not_in_the_models_file_or_differs_from_it(self):
        self.failing("I-deployments", lambda e: e[f"{ACCOUNT}/deployments"]["value"].append({"name": "extra", "sku": {"name": "GlobalStandard", "capacity": 1}, "properties": {}}), ("extra",))
        self.failing("I-deployments", lambda e: e[f"{ACCOUNT}/deployments"]["value"][0]["sku"].update(capacity=999), ("capacity",))
        self.failing("I-deployments", lambda e: e[f"{ACCOUNT}/deployments"]["value"][1]["properties"].update(raiPolicyName="Microsoft.Default"), ("guardrail",))
        self.failing("I-deployments", lambda e: e[f"{ACCOUNT}/deployments"]["value"][2]["properties"]["model"].update(version="1999-01-01"), ("version",))
        self.failing("I-deployments", lambda e: e[f"{ACCOUNT}/deployments"]["value"].pop(), ("not deployed",))

    def test_a_shield_that_is_off_or_not_blocking(self):
        path = f"{ACCOUNT}/raiPolicies/{NAMES['guardrail']}"
        self.failing("I-guardrail", lambda e: e[path]["properties"]["contentFilters"].pop(), ("Indirect Attack at PostToolCall",))
        self.failing("I-guardrail", lambda e: e[path]["properties"]["contentFilters"][0].update(blocking=False), ("Jailbreak",))
        self.failing("I-guardrail", lambda e: e[path]["properties"].update(mode="Default"), ("Blocking",))

    def test_a_policy_of_the_gateway_that_is_gone_or_looser(self):
        path = f"{GATEWAY}/workspaces/default"
        self.failing("I-gateway-policies", lambda e: e[path]["properties"]["policies"].pop(0), ("is not there",))

        def looser(estate):
            token = next(p for p in estate[path]["properties"]["policies"] if p["type"] == "tokenLimit")
            token["count"] = token["count"] * 10
        self.failing("I-gateway-policies", looser, ("differs from environment/aigateway/policies.json",))

    def test_a_model_an_alias_or_a_provider_that_the_repository_does_not_list(self):
        workspace = f"{GATEWAY}/workspaces/default"
        self.failing("I-gateway-models", lambda e: e[f"{workspace}/aliases"]["value"].append({"name": "sneaky", "properties": {"backendModels": []}}), ("sneaky",))
        self.failing("I-gateway-models", lambda e: e[f"{workspace}/modelProviders"]["value"].append({"name": "other", "properties": {}}), ("another model provider",))
        self.failing("I-gateway-models", lambda e: e[f"{workspace}/modelProviders/foundry/models"]["value"][0]["properties"]["policies"][0].update(hateSeverity="High"), ("content safety",))
        self.failing("I-gateway-models", lambda e: e[f"{workspace}/modelProviders/foundry/models"]["value"].pop(), ("is not on the gateway",))

    def test_agent_365_logging_that_was_switched_off_is_a_finding_and_what_the_tenant_decides_is_never_one(self):
        self.failing("I-agent-365", lambda e: e[ACCOUNT]["properties"].update(a365LoggingEnabled=False), ("a365LoggingEnabled is false", "outside the workflow"), closed=False)
        results, closed, az, _ = world()
        self.assertEqual(results["I-agent-365"]["state"], "PASS")
        self.assertIn("portal only", results["I-agent-365"]["detail"])
        self.assertIn("Microsoft 365 admin center", results["I-agent-365"]["detail"])
        self.assertEqual([call for call in az.calls if "a365" in " ".join(call)], [], "nothing is asked of Azure by that name: the flag is a property of the Foundry resource that is read")
        for what, change in (("no setting", lambda e: [e[ACCOUNT]["properties"].pop(k) for k in ("a365LoggingEnabled", "a365Status")]), ("a status that is not Enabled", lambda e: e[ACCOUNT]["properties"].update(a365Status="Pending"))):
            with self.subTest(what=what):
                results, closed, _, _ = world(change)
                self.assertEqual(results["I-agent-365"]["state"], "UNKNOWN", results["I-agent-365"]["detail"])
                self.assertEqual(closed, set())

    def test_agent_365_is_read_at_the_generally_available_version_and_nothing_is_written_to_the_resource(self):
        self.assertRegex(SOURCE, r'FOUNDRY_API = "20\d\d-\d\d-\d\d"\n', "a version without the word preview")
        block = SOURCE.split('@control("I-agent-365", "L3")')[1].split("@control(")[0]
        self.assertIn("FOUNDRY_API", block)
        self.assertNotIn("preview", block.lower().replace("preview initiative", ""), "no preview API version in the control")
        for word in ("patch", "put", "post(", "send("):
            self.assertNotIn(word, block)

    def test_the_flag_of_agent_365_is_read_by_the_drift_check_and_set_by_no_template_here(self):
        for name in ("environment/foundry/main.bicep", "environment/governance/main.bicep", "environment/aigateway/telemetry.bicep"):
            self.assertNotIn("a365LoggingEnabled", (ROOT / name).read_text(encoding="utf-8").split("targetScope")[-1], f"{name}: the flag is read by the drift check and set by nobody here")

    def test_a_principal_on_the_gateway_that_the_access_list_does_not_name_or_a_wider_role(self):
        path = f"{GATEWAY}/providers/Microsoft.Authorization/roleAssignments"
        stranger = {"properties": {"scope": GATEWAY, "roleDefinitionId": f"/providers/Microsoft.Authorization/roleDefinitions/{dc.GATEWAY_MODELS_USER}", "principalId": dc.SELFTEST_IDS["stranger"], "principalType": "User"}}
        self.failing("I-gateway-roles", lambda e: e[path]["value"].append(stranger), ("not on the access list",))
        wider = {"properties": {"scope": GATEWAY, "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/8e3af657-a8ff-443c-a75c-2fe8c4bcb635", "principalId": dc.SELFTEST_IDS["cases"]}}
        self.failing("I-gateway-roles", lambda e: e[path]["value"].append(wider), ("only AI Gateway Models User",))
        self.failing("I-gateway-roles", lambda e: e[path]["value"].pop(0), ("does not hold AI Gateway Models User",))

    def test_inherited_assignments_above_the_gateway_are_not_the_gateways_roles(self):
        results, _, _, _ = world()
        self.assertEqual(results["I-gateway-roles"]["state"], "PASS", "the fake estate holds an Owner of the subscription, which is above the gateway and is judged by no one here")

    def test_telemetry_that_captures_a_payload_is_fail_closed_and_a_gateway_with_no_exporter_is_a_plain_fail(self):
        path = f"{GATEWAY}/workspaces/default/telemetryExporters"
        self.failing("I-telemetry", lambda e: e[path]["value"][0]["properties"].update(payloadCapture=True), ("payloadCapture",))
        self.failing("I-telemetry", lambda e: e[path]["value"][0]["properties"].pop("payloadCapture"), ("payloadCapture",))
        self.failing("I-telemetry", lambda e: e[path]["value"].clear(), ("no exporter",), closed=False)
        self.failing("I-telemetry", lambda e: e[path]["value"][0]["properties"]["openTelemetry"]["credentials"].update(headers={"api-key": "x"}), ("credential",), closed=False)

    def test_the_project_connection_that_holds_a_credential_or_points_elsewhere(self):
        path = f"{ACCOUNT}/projects/{NAMES['project']}/connections/aigateway"
        self.failing("I-connection", lambda e: e[path]["properties"].update(credentials={"key": "x"}), ("credentials",))
        self.failing("I-connection", lambda e: e[path]["properties"].update(target="https://elsewhere.example/v1"), ("target",))
        self.failing("I-connection", lambda e: e[f"{ACCOUNT}/projects/{NAMES['project']}/connections"]["value"].append({"name": "odd", "properties": {"category": "CustomKeys"}}), ("odd",))

    def test_a_policy_exemption_that_nobody_accepted(self):
        path = f"{BASE}/providers/Microsoft.Authorization/policyExemptions"
        new = {"name": "new", "properties": {"policyAssignmentId": "/providers/Microsoft.Authorization/policyAssignments/Other"}}
        self.failing("I-policy-assignments", lambda e: e[path]["value"].append(new), ("Other/new",))

    def test_our_policy_that_is_gone_audit_only_or_with_another_effect(self):
        path = f"{BASE}/providers/Microsoft.Authorization/policyAssignments"
        self.failing("I-policy-assignments", lambda e: e[path]["value"].pop(0), ("meternaut-approved-models is not on the group",))
        self.failing("I-policy-assignments", lambda e: e[path]["value"][0]["properties"].update(enforcementMode="DoNotEnforce"), ("not enforced",))
        self.failing("I-policy-assignments", lambda e: e[path]["value"][1]["properties"]["parameters"]["effect"].update(value="Disabled"), ("Disabled",))

    def test_a_deny_policy_that_became_non_compliant_and_a_resource_that_breaks_our_own_policy(self):
        row = {"Effect": "deny", "Assignment": "Some-Policy", "Reference": "ref", "Type": "microsoft.storage/storageaccounts", "Resources": 1}
        self.failing("I-policy-compliance", None, ("Some-Policy/ref/microsoft.storage/storageaccounts",), closed=True, graph_rows=[row])
        ours = {"Effect": "audit", "Assignment": "meternaut-approved-models", "Reference": "", "Type": "microsoft.cognitiveservices/accounts/deployments", "Resources": 1}
        self.failing("I-policy-compliance", None, ("meternaut-approved-models",), closed=True, graph_rows=[ours])

    def test_an_identity_of_meternaut_that_can_change_azure(self):
        path = f"{BASE}/providers/Microsoft.Authorization/roleAssignments"
        contributor = "/providers/Microsoft.Authorization/roleDefinitions/contributor"
        for who in ("cases", "foundry-project", "operator", "gateway", "account", "console"):
            with self.subTest(who=who):
                self.failing("I-role-assignments", lambda e, w=who: e[path]["value"].append({"properties": {"scope": BASE, "roleDefinitionId": contributor, "principalId": dc.SELFTEST_IDS[w]}}), ("rule 29",))

    def test_an_operator_without_foundry_user_on_the_project_is_a_plain_fail_that_says_what_the_tools_then_get(self):
        self.failing("I-operator-role", lambda e: e[PROJECT_ROLES].update(value=[a for a in e[PROJECT_ROLES]["value"] if a["properties"]["principalId"] != OPERATOR]),
                     ("does not hold the role Foundry User", "agents-drift, foundry-evals and foundry-redteam", "403 or 401", "the action foundry gives it the role"), closed=False)

    def test_an_operator_with_a_wider_foundry_role_on_the_project_or_any_foundry_role_on_the_resource_is_a_fail(self):
        for role, name in dc.WIDER_FOUNDRY_ROLES.items():
            with self.subTest(role=name):
                self.failing("I-operator-role", lambda e, r=role: e[PROJECT_ROLES]["value"].append(dc.assignment_of(PROJECT, r, OPERATOR)), (f"holds {name} on the Foundry project", "wider than Foundry User"), closed=False)
        for role in (dc.FOUNDRY_USER, *dc.WIDER_FOUNDRY_ROLES):
            with self.subTest(role=role, scope="the resource"):
                self.failing("I-operator-role", lambda e, r=role: e[PROJECT_ROLES]["value"].append(dc.assignment_of(ACCOUNT, r, OPERATOR)),
                             ("on the Foundry resource", "a role on the project alone does not"), closed=False)

    def test_a_role_that_is_not_one_of_foundry_is_wider_when_it_can_change_azure_or_holds_data_actions_of_the_resource_and_harmless_as_a_reader(self):
        def define(estate, role, permissions):
            estate[f"/subscriptions/{dc.SELFTEST_SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{role}"] = {"properties": {"permissions": permissions}}

        def add(role, permissions, scope=PROJECT):
            def change(estate):
                define(estate, role, permissions)
                estate[PROJECT_ROLES]["value"].append(dc.assignment_of(scope, role, OPERATOR))
            return change
        self.failing("I-operator-role", add("custom-writer", [{"actions": ["Microsoft.CognitiveServices/accounts/projects/write"]}]), ("which can change Azure",), closed=False)
        self.failing("I-operator-role", add("custom-caller", [{"actions": [], "dataActions": ["Microsoft.CognitiveServices/accounts/OpenAI/*"]}], ACCOUNT), ("data actions of the Foundry resource",), closed=False)
        self.failing("I-operator-role", add("custom-all", [{"actions": [], "dataActions": ["*"]}]), ("data actions of the Foundry resource",), closed=False)
        results, _, _, _ = world(add("custom-reader", [{"actions": ["*/read"], "dataActions": []}]))
        self.assertEqual(results["I-operator-role"]["state"], "PASS", "a reader adds nothing to what Foundry User reads")

    def test_the_operator_holds_foundry_user_on_the_project_and_what_others_or_the_other_roles_above_hold_is_not_its_business(self):
        results, _, az, _ = world(lambda e: e[PROJECT_ROLES]["value"].extend([
            dc.assignment_of(PROJECT, next(iter(dc.WIDER_FOUNDRY_ROLES)), dc.SELFTEST_IDS["stranger"], "User"),
            dc.assignment_of(f"/subscriptions/{dc.SELFTEST_SUBSCRIPTION}", next(iter(dc.WIDER_FOUNDRY_ROLES)), dc.SELFTEST_IDS["stranger"], "User"),
            dc.assignment_of(BASE, "acdd72a7-3385-48ef-bd42-f606fba81ae7", OPERATOR)]))
        self.assertEqual(results["I-operator-role"]["state"], "PASS", results["I-operator-role"]["detail"])
        self.assertIn("Foundry User on the Foundry project, and nothing wider", results["I-operator-role"]["detail"])
        self.assertTrue([c for c in az.calls if f"/projects/{NAMES['project']}/providers/Microsoft.Authorization/roleAssignments" in c[c.index("--url") + 1] and c[c.index("--method") + 1] == "get"],
                        "the assignments are read at the project, with a GET")

    def test_a_foundry_role_that_the_operator_holds_above_the_foundry_resource_is_wider_than_the_project_at_any_scope_and_is_not_a_missing_role(self):
        for scope in (BASE, f"/subscriptions/{dc.SELFTEST_SUBSCRIPTION}", "/providers/Microsoft.Management/managementGroups/example-root"):
            for role in (dc.FOUNDRY_USER, *dc.WIDER_FOUNDRY_ROLES):
                with self.subTest(scope=scope.rsplit("/", 1)[-1], role=role[:8]):
                    self.failing("I-operator-role", lambda e, s=scope, r=role: e[PROJECT_ROLES]["value"].append(dc.assignment_of(s, r, OPERATOR)),
                                 ("above the Foundry resource", "wider than the project"), closed=False)
        results, _, _, _ = world(lambda e: e[PROJECT_ROLES].update(value=[dc.assignment_of(BASE, dc.FOUNDRY_USER, OPERATOR)]))
        self.assertEqual(results["I-operator-role"]["state"], "FAIL")
        self.assertIn("Foundry User above the Foundry resource", results["I-operator-role"]["detail"])
        self.assertNotIn("does not hold", results["I-operator-role"]["detail"], "it holds the role, wider than designed: the tools work, and the control says what is wrong")

    def test_the_role_is_unknown_when_the_assignments_or_a_definition_cannot_be_read_and_a_missing_project_or_operator_is_said(self):
        estate = dc.fake_estate(MODELS, POLICIES, NAMES)
        az = dc.FakeAz(estate, app_rows=dc.healthy_rows())
        az.denied.add(PROJECT_ROLES.lower())
        results = {r["control"]: r for r in dc.run_controls(dc.selftest_context(az, MODELS, POLICIES, ACCESS))[0]}
        self.assertEqual(results["I-operator-role"]["state"], "UNKNOWN")
        self.assertIn("Reader at the project's group", results["I-operator-role"]["detail"])
        unreadable = lambda e: e[PROJECT_ROLES]["value"].append(dc.assignment_of(PROJECT, "00000000-0000-0000-0000-00000000dead", OPERATOR))
        results, _, _, _ = world(unreadable)
        self.assertEqual(results["I-operator-role"]["state"], "UNKNOWN", "a role that cannot be read is not known to be harmless")
        self.assertIn("could not be read", results["I-operator-role"]["detail"])
        results, _, _, _ = world(lambda e: [e.pop(PROJECT), e.pop(PROJECT_ROLES)])
        self.assertEqual((results["I-operator-role"]["state"], results["I-operator-role"]["detail"]), ("FAIL", "The Foundry project is not there."))
        results, _, _, _ = world(lambda e: e.pop(f"{BASE}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{dc.OPERATOR_IDENTITY}"))
        self.assertEqual(results["I-operator-role"]["state"], "PASS", "an Operator that is not made yet holds no role, and that is no drift")
        self.assertIn("not made yet", results["I-operator-role"]["detail"])

    def test_a_deployed_release_that_is_not_the_code_of_main(self):
        tags = lambda e: e[SITE]["tags"].update({"meternaut-build-commit": "c" * 40, "meternaut-package-sha256": "d" * 64})
        self.failing("I-release", tags, ("not the code of main", "digest"), closed=False, app_dir=str(ROOT / "src" / "case-functions"))
        self.failing("I-release", tags, ("run the action cases",), closed=False)

    def test_an_alert_rule_that_is_gone_disabled_or_tells_nobody(self):
        path = f"{BASE}/providers/Microsoft.Insights/scheduledQueryRules"
        self.failing("I-alerts", lambda e: e[path]["value"].pop(), ("is not there",), closed=False)
        self.failing("I-alerts", lambda e: e[path]["value"][0]["properties"].update(enabled=False), ("disabled",), closed=False)
        self.failing("I-alerts", lambda e: e[path]["value"][0]["properties"].update(actions={}), ("tells nobody",), closed=False)
        self.failing("I-alerts", lambda e: e[f"{BASE}/providers/Microsoft.Insights/actionGroups/{dc.ACTION_GROUP}"]["properties"].update(emailReceivers=[]), ("no e-mail receiver",), closed=False)

    def test_the_foundry_resource_without_any_diagnostic_setting(self):
        self.failing("I-diagnostics", lambda e: e[f"{ACCOUNT}/providers/Microsoft.Insights/diagnosticSettings"]["value"].clear(), ("No diagnostic setting",), closed=False)

    def test_exposure_that_the_owner_did_not_accept(self):
        storage = f"{BASE}/providers/Microsoft.Storage/storageAccounts/{NAMES['storage']}"
        self.failing("I-network", lambda e: e[storage]["properties"].update(publicNetworkAccess="Enabled"), ("storage account takes public traffic",))
        self.failing("I-network", lambda e: e[storage]["properties"].update(allowSharedKeyAccess=True), ("Shared Key",))
        self.failing("I-network", lambda e: e[SITE]["properties"].update(publicNetworkAccess="Disabled"), ("accepted value is Enabled",))
        results, _, _, _ = world(cases_public_access="Disabled", change=lambda e: e[SITE]["properties"].update(publicNetworkAccess="Disabled"))
        self.assertEqual(results["I-network"]["state"], "PASS", "the owner closes the web page: the accepted value follows the constant")

    def test_a_kind_of_resource_that_the_check_does_not_read_makes_the_network_control_unknown_and_never_pass(self):
        results, _, _, _ = world(lambda e: e[f"{BASE}/resources"]["value"].append({"type": "Microsoft.KeyVault/vaults"}))
        self.assertEqual(results["I-network"]["state"], "UNKNOWN")
        self.assertIn("microsoft.keyvault/vaults", results["I-network"]["detail"])


class ModelLifecycle(unittest.TestCase):
    def state_at(self, days_before, status="GenerallyAvailable"):
        retire = datetime.strptime(MODELS[0]["retirementDate"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = retire - timedelta(days=days_before)

        def change(estate):
            estate[f"{ACCOUNT}/models"]["value"][0]["model"]["lifecycleStatus"] = status
        results, closed, _, _ = world(change, now=now)
        return results["I-model-lifecycle"], "I-model-lifecycle" in closed

    def test_the_tiers_at_180_90_and_30_days_and_the_retired_model(self):
        # models[2] (gpt-5.5) retires earlier than models[0]: the tiers are read for whichever model retires first, so the dates are taken from it
        first = min(MODELS, key=lambda m: m["retirementDate"])
        retire = datetime.strptime(first["retirementDate"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        expected = [(400, "PASS", False), (181, "PASS", False), (180, "FAIL", False), (91, "FAIL", False), (90, "FAIL", False), (31, "FAIL", False), (30, "FAIL", True), (1, "FAIL", True), (0, "FAIL", True), (-5, "FAIL", True)]
        for days, state, closed in expected:
            with self.subTest(days=days):
                results, closed_set, _, _ = world(now=retire - timedelta(days=days))
                self.assertEqual((results["I-model-lifecycle"]["state"], "I-model-lifecycle" in closed_set), (state, closed), results["I-model-lifecycle"]["detail"])

    def test_a_model_that_the_service_calls_deprecated_is_retired_whatever_the_date_says(self):
        outcome, closed = self.state_at(400, status="Deprecated")
        self.assertEqual((outcome["state"], closed), ("FAIL", True))
        self.assertIn("is retired", outcome["detail"])

    def test_a_model_that_is_deprecating_is_a_warning_that_is_not_fail_closed(self):
        outcome, closed = self.state_at(400, status="Deprecating")
        self.assertEqual((outcome["state"], closed), ("FAIL", False))
        self.assertIn("Deprecating", outcome["detail"])

    def test_the_earlier_of_the_two_dates_wins_the_models_file_or_the_service(self):
        def earlier(estate):
            estate[f"{ACCOUNT}/models"]["value"][0]["model"]["deprecation"] = {"inference": "2026-12-01T00:00:00Z"}
        results, closed, _, _ = world(earlier)
        self.assertEqual(results["I-model-lifecycle"]["state"], "FAIL")
        self.assertIn("2026-12-01", results["I-model-lifecycle"]["detail"])
        self.assertIn("I-model-lifecycle", closed, "23 days left")


class WhatCannotBeReadIsUnknownAndNeverPass(unittest.TestCase):
    def test_a_read_that_the_identity_may_not_make_gives_unknown_with_the_right_that_would(self):
        estate = dc.fake_estate(MODELS, POLICIES, NAMES)
        az = dc.FakeAz(estate, app_rows=dc.healthy_rows())
        az.denied.add(ACCOUNT.lower())
        ctx = dc.selftest_context(az, MODELS, POLICIES, ACCESS)
        results = {r["control"]: r for r in dc.run_controls(ctx)[0]}
        self.assertEqual(results["I-foundry-flags"]["state"], "UNKNOWN")
        self.assertIn("Reader at the project's group", results["I-foundry-flags"]["detail"])
        for control_id in ("I-deployments", "I-guardrail", "I-model-lifecycle"):
            self.assertEqual(results[control_id]["state"], "UNKNOWN", control_id)
        self.assertNotIn("FAIL", {r["state"] for c, r in results.items() if c in ("I-foundry-flags", "I-deployments", "I-guardrail", "I-model-lifecycle")})

    def test_a_read_that_does_not_answer_in_time_halts_the_rest_instead_of_waiting_again(self):
        calls = []

        def stuck(arguments):
            calls.append(arguments)
            raise dc.Stuck("az did not answer within 120 seconds (GET /x)")
        ctx = dc.Context(dc.Reader(stuck), dc.SELFTEST_SUBSCRIPTION, dc.SELFTEST_GROUP, MODELS, POLICIES, ACCESS, {"now": dc.SELFTEST_NOW})
        results = {r["control"]: r for r in dc.run_controls(ctx)[0]}
        self.assertEqual(len(calls), 1, "after the first read that did not answer in time nothing more is read, and not a second read waits as long")
        self.assertNotIn("PASS", {r["state"] for r in results.values()}, "a run in which nothing could be read passes nothing")
        self.assertNotIn("FAIL", {r["state"] for r in results.values()}, "and fails nothing either: it does not know")

    def test_the_app_that_never_logged_a_result_is_unknown_and_one_that_went_silent_is_fail(self):
        results, _, _, _ = world(app_rows=[])
        self.assertEqual(results["I-heartbeat"]["state"], "UNKNOWN")
        self.assertEqual(results["I-inapp-results"]["state"], "UNKNOWN")
        old = [{"control": "A-agents", "line": "drift.pass", "timestamp": (dc.SELFTEST_NOW - timedelta(hours=27)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
        results, closed, _, _ = world(app_rows=old)
        self.assertEqual(results["I-heartbeat"]["state"], "FAIL")
        self.assertIn("27 hours ago", results["I-heartbeat"]["detail"])
        fresh = [{"control": "A-agents", "line": "drift.pass", "timestamp": (dc.SELFTEST_NOW - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
        self.assertEqual(world(app_rows=fresh)[0]["I-heartbeat"]["state"], "PASS", "26 hours is the limit")

    def test_a_failing_control_of_the_app_is_a_fail_of_the_report_and_an_unknown_one_is_not(self):
        rows = healthy_rows = [{"control": "A-agents", "line": "drift.fail", "timestamp": (dc.SELFTEST_NOW - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                               {"control": "A-tools", "line": "drift.unknown", "timestamp": (dc.SELFTEST_NOW - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
        results, closed, _, _ = world(app_rows=rows)
        self.assertEqual(results["I-inapp-results"]["state"], "FAIL")
        self.assertIn("A-agents", results["I-inapp-results"]["detail"])
        self.assertEqual(results["I-heartbeat"]["state"], "PASS", "a failing control is still a heartbeat")
        only_unknown = [r for r in rows if r["line"] == "drift.unknown"]
        self.assertEqual(world(app_rows=only_unknown)[0]["I-inapp-results"]["state"], "PASS")
        self.assertEqual(world(app_rows=only_unknown)[0]["I-heartbeat"]["state"], "UNKNOWN", "an unknown line is not a heartbeat")

    def test_no_baseline_means_unknown_with_the_list_that_the_owner_could_accept_and_none_means_none(self):
        results, _, _, _ = world(accepted_exemptions=None, accepted_deny=None)
        self.assertEqual(results["I-policy-assignments"]["state"], "UNKNOWN")
        self.assertIn("Deny-Public-Endpoints/waiver", results["I-policy-assignments"]["detail"])
        self.assertIn("DRIFT_ACCEPTED_EXEMPTIONS", results["I-policy-assignments"]["detail"])
        self.assertEqual(results["I-policy-compliance"]["state"], "UNKNOWN")
        self.assertIn("DRIFT_ACCEPTED_DENY", results["I-policy-compliance"]["detail"])
        self.assertEqual(dc.keys_of("none"), set())
        self.assertEqual(dc.keys_of("a/b, c/d"), {"a/b", "c/d"})
        results, _, _, _ = world(accepted_exemptions=set())
        self.assertEqual(results["I-policy-assignments"]["state"], "FAIL", "an empty baseline accepts no exemption")

    def test_the_two_directory_controls_are_unknown_without_graph_and_read_it_only_when_asked(self):
        results, _, az, _ = world()
        self.assertEqual({results[c]["state"] for c in ("I-entra-console", "I-entra-agents")}, {"UNKNOWN"})
        self.assertFalse([c for c in az.calls if "graph.microsoft.com" in " ".join(c)], "nothing of the directory is read unless --graph is given")
        self.assertEqual(results["I-defender"]["state"], "UNKNOWN")
        self.assertFalse([c for c in az.calls if "Microsoft.Security" in " ".join(c)], "nothing outside the project's group is read unless --read-subscription is given")

    def test_with_graph_a_secret_on_the_console_registration_and_an_agent_without_an_owner_are_found(self):
        estate = dc.fake_estate(MODELS, POLICIES, NAMES)
        calls = []

        def az(arguments):
            url = arguments[arguments.index("--url") + 1]
            calls.append(url)
            if url.startswith(dc.GRAPH):
                if "applications(" in url:
                    return 0, json.dumps({"passwordCredentials": [{"displayName": "x"}], "keyCredentials": []}), ""
                if url.split("?")[0].endswith("/owners") or url.split("?")[0].endswith("/sponsors"):
                    return 0, json.dumps({"value": []}), ""
                return 0, json.dumps({"value": [{"id": "agent-1", "displayName": f"{NAMES['account']}-meternaut-investigator-AgentIdentity"}]}), ""
            return dc.FakeAz(estate, app_rows=dc.healthy_rows())(arguments)
        ctx = dc.selftest_context(az, MODELS, POLICIES, ACCESS, graph=True, console_client_id="00000000-0000-0000-0000-000000000000")
        results = {r["control"]: r for r in dc.run_controls(ctx)[0]}
        self.assertEqual(results["I-entra-console"]["state"], "FAIL")
        self.assertIn("secret or a certificate", results["I-entra-console"]["detail"])
        self.assertEqual(results["I-entra-agents"]["state"], "FAIL")
        self.assertIn("neither an owner nor a sponsor", results["I-entra-agents"]["detail"])
        self.assertTrue([u for u in calls if u.startswith(dc.GRAPH)])
        self.assertTrue(all(" " not in u for u in calls), "an address that a request is made to holds no space: the filter is encoded")

    def test_with_read_subscription_the_defender_plan_is_read_and_a_denied_read_is_unknown(self):
        estate = dc.fake_estate(MODELS, POLICIES, NAMES)
        estate[f"/subscriptions/{dc.SELFTEST_SUBSCRIPTION}/providers/Microsoft.Security/pricings/AI"] = {"properties": {"pricingTier": "Standard"}}
        results, _, _, _ = world(lambda e: e.update({k: v for k, v in estate.items() if "Security" in k}), read_subscription=True)
        self.assertEqual(results["I-defender"]["state"], "PASS")
        self.assertIn("Sweden Central", results["I-defender"]["detail"], "the region caveat is said, and it is not a fail")
        free = {"properties": {"pricingTier": "Free"}}
        results, closed, _, _ = world(lambda e: e.update({f"/subscriptions/{dc.SELFTEST_SUBSCRIPTION}/providers/Microsoft.Security/pricings/AI": free}), read_subscription=True)
        self.assertEqual(results["I-defender"]["state"], "FAIL")
        self.assertNotIn("I-defender", closed)
        results, _, _, _ = world(read_subscription=True)
        self.assertEqual(results["I-defender"]["state"], "UNKNOWN", "the fake estate has no such plan: the control says so and does not pass")

    def test_the_release_is_unknown_when_the_app_carries_none_and_passes_when_main_changed_nothing_of_the_app(self):
        results, _, _, _ = world(lambda e: e[SITE].update(tags={}))
        self.assertEqual(results["I-release"]["state"], "UNKNOWN")
        digest = load_digest()
        def same_files(estate):
            estate[SITE]["tags"] = {"meternaut-build-commit": "e" * 40, "meternaut-package-sha256": digest}
        results, _, _, _ = world(same_files, app_dir=str(ROOT / "src" / "case-functions"))
        self.assertEqual(results["I-release"]["state"], "PASS")
        self.assertIn("main changed nothing of the app", results["I-release"]["detail"])


def load_digest():
    spec_digest = importlib.util.spec_from_file_location("source_digest_for_the_drift_tests", ROOT / "tools" / "source-digest.py")
    module = importlib.util.module_from_spec(spec_digest)
    spec_digest.loader.exec_module(module)
    return module.digest(ROOT / "src" / "case-functions")


class TheToolOnlyReads(unittest.TestCase):
    def test_every_call_of_a_run_is_a_get_or_one_of_the_two_reads_that_need_a_post(self):
        _, _, az, _ = world()
        methods = [(c[c.index("--method") + 1], c[c.index("--url") + 1].split("?")[0]) for c in az.calls]
        posts = [url for method, url in methods if method == "post"]
        self.assertEqual({m for m, _ in methods}, {"get", "post"})
        self.assertEqual(len(posts), 2)
        self.assertIn(f"{dc.ARM}/providers/Microsoft.ResourceGraph/resources", posts)
        self.assertTrue(any(url.endswith("/components/appi-meternaut/query") for url in posts))

    def test_anything_that_is_not_a_read_is_refused_before_the_call_is_made(self):
        made = []
        reader = dc.Reader(lambda arguments: made.append(arguments) or (0, "{}", ""))
        for method, url in (("put", f"{dc.ARM}/subscriptions/x"), ("delete", f"{dc.ARM}/subscriptions/x"), ("patch", f"{dc.ARM}/subscriptions/x"),
                            ("post", f"{dc.ARM}/subscriptions/x/providers/Microsoft.Authorization/roleAssignments"), ("post", f"{dc.ARM}/subscriptions/x/resourceGroups/g/providers/Microsoft.Web/sites/a/restart"),
                            ("get", "https://example.com/x"), ("post", f"{dc.GRAPH}/v1.0/applications"), ("get", "http://management.azure.com/x")):
            with self.subTest(method=method, url=url):
                with self.assertRaises(dc.Refused):
                    reader.send(method, url)
        self.assertEqual(made, [])

    def test_the_source_has_no_write_verb_and_runs_one_command_only(self):
        code = re.sub(r'""".*?"""', "", SOURCE, flags=re.S)
        code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("#"))
        for word in ("--method put", "--method patch", "--method delete", "role assignment create", "az deployment", "az group deployment", "listKeys", "listSecrets", "az login"):
            self.assertNotIn(word, code, word)
        self.assertEqual(len(re.findall(r"subprocess\.run\(", code)), 1)
        self.assertEqual(len(re.findall(r'open\(|write_text\(', code)), 2, "it writes the two files that it is asked to write (--summary, --json) and nothing else")

    def test_no_secret_word_is_in_the_code_of_the_tool(self):
        code = re.sub(r'""".*?"""', "", SOURCE, flags=re.S)
        self.assertNotRegex(code, r"(?i)instrumentationkey|accountkey|primarykey|sharedaccess")


class TheTemplatesAndTheToolAgreeOnNames(unittest.TestCase):
    def test_the_alert_rules_are_those_of_the_governance_template(self):
        rules = re.findall(r"(?m)^    name: '([a-z-]+)'$", GOVERNANCE)
        self.assertEqual(sorted(rules), sorted([*dc.ALERT_RULES, dc.ALERT_RULE_OF_ACCESS_LIST]))
        self.assertIn("name: 'alert-${workload}-ai-${rule.name}'", GOVERNANCE)

    def test_the_assignments_the_action_group_the_workbook_and_the_heartbeat_are_those_of_the_governance_template(self):
        for name in (*dc.OUR_ASSIGNMENTS, *dc.OPTIONAL_ASSIGNMENTS):
            self.assertIn(f"name: '{name}'", GOVERNANCE, name)
        self.assertIn("name: 'ag-${workload}-ai-security'", GOVERNANCE)
        self.assertEqual(dc.ACTION_GROUP, "ag-meternaut-ai-security")
        self.assertIn(f"displayName: '{dc.WORKBOOK_NAME}'", GOVERNANCE)
        self.assertIn(f"param heartbeatHours int = {dc.HEARTBEAT_HOURS}", GOVERNANCE)
        self.assertIn("name: 'log-${workload}'", GOVERNANCE)
        self.assertEqual(dc.WORKSPACE, "log-meternaut")

    def test_the_exporter_the_component_and_the_identities_are_those_of_the_templates(self):
        self.assertIn(f"param exporterName string = '{dc.EXPORTER}'", TELEMETRY)
        self.assertIn(f"param telemetryComponentName string = '{dc.COMPONENT}'", TELEMETRY)
        self.assertIn(f"resource: '{dc.MONITOR_AUDIENCE}'", TELEMETRY)
        self.assertIn("name: 'id-${workload}-console-auth'", CASES)
        self.assertEqual(dc.CONSOLE_IDENTITY, "id-meternaut-console-auth")
        self.assertIn("var operatorIdentityName = 'id-${workload}-operator'", AIGATEWAY)
        self.assertEqual(dc.OPERATOR_IDENTITY, "id-meternaut-operator")
        self.assertIn(f"var aiGatewayModelsUserRoleId = '{dc.GATEWAY_MODELS_USER}'", AIGATEWAY)

    def test_the_foundry_user_role_of_the_tool_is_the_one_that_the_template_gives_the_operator_and_no_wider_foundry_role_is_in_the_template(self):
        foundry = (ROOT / "environment" / "foundry" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn(f"var foundryUserRoleId = '{dc.FOUNDRY_USER}'", foundry)
        self.assertIn("principalId: operatorPrincipalId", foundry)
        for guid, name in dc.WIDER_FOUNDRY_ROLES.items():
            self.assertNotIn(guid, foundry, f"{name}: the template gives no wider Foundry role to anyone")

    def test_the_names_of_the_resources_are_the_ones_that_the_parameter_builder_gives(self):
        params = dc.load_sibling("environment_params_for_the_drift_names", "environment-params.py")
        _, _, _, ctx = world()
        self.assertEqual(ctx.account, params.foundry_names(dc.SELFTEST_SUBSCRIPTION, dc.SELFTEST_GROUP)["foundry_account_name"])
        self.assertEqual(ctx.gateway, params.aigateway_name(dc.SELFTEST_SUBSCRIPTION, dc.SELFTEST_GROUP))
        self.assertEqual(ctx.cases_app, params.cases_names(dc.SELFTEST_SUBSCRIPTION, dc.SELFTEST_GROUP)["cases_function_app_name"])
        self.assertEqual(ctx.storage, params.base_names(dc.SELFTEST_SUBSCRIPTION, dc.SELFTEST_GROUP)["storage_account_name"])

    def test_the_lifecycle_tiers_are_180_90_and_30_days(self):
        self.assertEqual((dc.LIFECYCLE_NOTICE_DAYS, dc.LIFECYCLE_WARNING_DAYS, dc.LIFECYCLE_CLOSED_DAYS), (180, 90, 30))


class TheCommandLine(unittest.TestCase):
    def run_main(self, *extra, estate=None, rows="healthy"):
        estate = estate or dc.fake_estate(MODELS, POLICIES, NAMES)
        az = dc.FakeAz(estate, app_rows=dc.healthy_rows() if rows == "healthy" else rows)
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(out), redirect_stderr(err):
            tmp = Path(tmp)
            arguments = ["--subscription", dc.SELFTEST_SUBSCRIPTION, "--resource-group", dc.SELFTEST_GROUP, "--models", str(ROOT / "environment" / "models.json"),
                         "--policies", str(ROOT / "environment" / "aigateway" / "policies.json"), "--access-list", str(ROOT / "environment" / "aigateway" / "contracts.json"),
                         "--accepted-exemptions", "Deny-Public-Endpoints/waiver", "--accepted-deny", "none", "--cases-public-access", "Enabled",
                         "--json", str(tmp / "report.json"), "--summary", str(tmp / "summary.md"), "--commit", dc.SELFTEST_COMMIT, *extra]
            code = dc.main(arguments, az=az, now=dc.SELFTEST_NOW)
            report = json.loads((tmp / "report.json").read_text(encoding="utf-8")) if (tmp / "report.json").exists() else None
            summary = (tmp / "summary.md").read_text(encoding="utf-8") if (tmp / "summary.md").exists() else ""
        return code, out.getvalue(), err.getvalue(), report, summary

    def test_a_clean_run_exits_0_prints_the_table_and_writes_the_json_and_the_summary(self):
        code, out, err, report, summary = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("### Drift check, control plane: 20 PASS, 0 FAIL, 3 UNKNOWN", out)
        self.assertEqual(summary, out.rstrip("\n") + "\n" if not out.endswith("\n\n") else out[:-1])
        self.assertEqual(report["summary"], {"PASS": 20, "FAIL": 0, "UNKNOWN": 3})
        self.assertEqual(report["failClosed"], [])
        self.assertEqual(len(report["controls"]), len(dc.CONTROLS))

    def test_a_fail_exits_1_and_says_whether_it_is_fail_closed(self):
        estate = dc.fake_estate(MODELS, POLICIES, NAMES)
        estate[ACCOUNT]["properties"]["publicNetworkAccess"] = "Enabled"
        code, out, err, report, _ = self.run_main(estate=estate)
        self.assertEqual(code, 1)
        self.assertIn("1 control(s) FAILED, 1 of them fail-closed (I-foundry-flags)", err)
        self.assertEqual(report["failClosed"], ["I-foundry-flags"])
        self.assertIn("Fail-closed controls that failed: I-foundry-flags", out)
        self.assertLess(out.index("| FAIL (fail-closed) | I-foundry-flags"), out.index("| UNKNOWN |"), "the failures come first")
        estate = dc.fake_estate(MODELS, POLICIES, NAMES)
        estate[f"{BASE}/providers/Microsoft.Insights/scheduledQueryRules"]["value"].pop()
        code, _, err, report, _ = self.run_main(estate=estate)
        self.assertEqual(code, 1, "a fail that is not fail-closed fails the run too")
        self.assertIn("none of them fail-closed", err)
        self.assertEqual(report["failClosed"], [])

    def test_only_runs_the_named_controls_and_an_unknown_id_is_refused(self):
        code, out, _, report, _ = self.run_main("--only", "I-foundry-flags,I-guardrail")
        self.assertEqual(code, 0)
        self.assertEqual([c["control"] for c in report["controls"]], ["I-foundry-flags", "I-guardrail"])
        code, out, err, report, _ = self.run_main("--only", "I-nope")
        self.assertEqual((code, report), (2, None))
        self.assertIn("unknown control(s): I-nope", err)

    def test_missing_settings_and_unreadable_files_are_refused_by_name(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(dc.main(["--models", "nowhere.json"]), 2)
            self.assertEqual(dc.main(["--subscription", "s", "--resource-group", "g", "--models", "nowhere.json"]), 2)
            self.assertEqual(dc.main(["--timeout", "0"]), 2)
        self.assertIn("nowhere.json is not a readable JSON file", err.getvalue())
        self.assertIn("--timeout is a number of seconds", err.getvalue())

    def test_the_report_holds_nothing_of_the_estate_but_names_and_short_ids(self):
        _, out, _, report, _ = self.run_main()
        text = out + json.dumps(report)
        self.assertNotRegex(text, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "no object id or subscription id is printed whole")
        self.assertNotIn(dc.SELFTEST_SUBSCRIPTION, text)


class TheDigestOfTheApp(unittest.TestCase):
    def test_the_digest_is_the_one_that_the_workflow_records_and_it_does_not_depend_on_the_zip(self):
        module = dc.load_sibling("source_digest_of_the_drift_test", "source-digest.py")
        first = module.digest(ROOT / "src" / "case-functions")
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, load_digest())


if __name__ == "__main__":
    unittest.main()
