"""The tool that applies the AI Gateway's gateway-wide policies, deletes its built-in key when the service lets it be deleted, and reads the gateway back (tools/aigateway-prep.py).

Azure is a stand-in that answers `az rest` from a dictionary of documents and keeps every request, so no test calls Azure."""
import contextlib
import copy
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("aigateway_prep", ROOT / "tools" / "aigateway-prep.py")
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
_hubenv_spec = importlib.util.spec_from_file_location("hubenv", Path(__file__).with_name("hubenv.py"))
hubenv = importlib.util.module_from_spec(_hubenv_spec)
_hubenv_spec.loader.exec_module(hubenv)

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
GATEWAY = "aigw-meternaut-0123abcd"
ACCOUNT = "aif-meternaut-agents-0123abcd"
OPERATOR = "id-meternaut-operator"
GATEWAY_PRINCIPAL = "aaaaaaaa-0000-0000-0000-000000000001"
OPERATOR_PRINCIPAL = "bbbbbbbb-0000-0000-0000-000000000002"
PROJECT_PRINCIPAL = "cccccccc-0000-0000-0000-000000000003"
OTHER_PRINCIPAL = "dddddddd-0000-0000-0000-000000000004"
CASES_PRINCIPAL = "eeeeeeee-0000-0000-0000-000000000005"
SECRET = "THE-VALUE-OF-A-KEY-THAT-NOTHING-MAY-PRINT"
MODELS = json.loads((ROOT / "environment" / "models.json").read_text(encoding="utf-8"))
POLICIES = json.loads((ROOT / "environment" / "aigateway" / "policies.json").read_text(encoding="utf-8"))
NOT_FOUND = "ERROR: (ResourceNotFound) The Resource was not found."
BASE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
GATEWAY_ID = f"{BASE}/providers/Microsoft.ApiManagement/aigateways/{GATEWAY}"
WORKSPACE = f"{GATEWAY_ID}/workspaces/default"
ACCOUNT_ID = f"{BASE}/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}"
SUBNET_ID = f"{BASE}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-aigw"
IDENTITY_ID = f"{BASE}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{OPERATOR}"
GATEWAY_ROLES = f"{GATEWAY_ID}/providers/Microsoft.Authorization/roleAssignments"
ACCOUNT_ROLES = f"{ACCOUNT_ID}/providers/Microsoft.Authorization/roleAssignments"
KEYS = f"{GATEWAY_ID}/apiKeys"
ARGUMENTS = ["--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--gateway", GATEWAY]


def assignment(role, principal, scope):
    return {"name": "x", "properties": {"roleDefinitionId": f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{role}", "principalId": principal, "scope": scope}}


def world(policies=None, keys=("master",)):
    """What Azure holds after a deploy of the template and a run of the action, as the service answers it."""
    models = []
    aliases = []
    for model in MODELS:
        resource = model["name"].replace(".", "-")
        models.append({"name": resource, "properties": {
            "displayName": model["name"], "providerKind": "Foundry", "supportedEndpoints": ["/openai/v1/chat/completions", "/openai/v1/responses"],
            "deployment": {"resourceId": f"{ACCOUNT_ID}/deployments/{model['name']}", "modelName": model["name"], "modelVersion": model["version"]},
            "policies": [{"type": "contentSafety", "hateSeverity": "Medium", "violenceSeverity": "Medium", "sexualSeverity": "Medium", "selfHarmSeverity": "Medium", "scope": "resource"}]}})
        aliases.append({"name": model["name"], "properties": {
            "aliasName": model["name"], "backendModels": [{"resourceId": f"{WORKSPACE}/modelProviders/foundry/models/{resource}", "priority": 0, "weight": 1}]}})
    return {
        GATEWAY_ID: {"name": GATEWAY, "identity": {"type": "SystemAssigned", "principalId": GATEWAY_PRINCIPAL}, "sku": {"name": "Standard"},
                     "properties": {"provisioningState": "Succeeded", "publicNetworkAccess": "Enabled", "backend": {"subnet": {"id": SUBNET_ID}},
                                    "frontend": {"defaultHostname": f"{GATEWAY}.swedencentral.ai.gateway.azure.com"}}},
        WORKSPACE: {"name": "default", "properties": {"policies": copy.deepcopy(POLICIES if policies is None else policies)}},
        f"{WORKSPACE}/modelProviders": {"value": [{"name": "foundry", "properties": {
            "kind": "Foundry", "foundry": {"endpoint": f"https://{ACCOUNT}.cognitiveservices.azure.com/", "resourceIds": [ACCOUNT_ID],
                                           "authentication": {"kind": "ManagedIdentity", "managedIdentity": {"resource": "https://cognitiveservices.azure.com/"}}}}}]},
        f"{WORKSPACE}/modelProviders/foundry/models": {"value": models},
        f"{WORKSPACE}/aliases": {"value": aliases},
        KEYS: {"value": [{"name": key, "properties": {"description": "Built-in all-access subscription", "value": SECRET, "primaryKey": SECRET}} for key in keys]},
        SUBNET_ID: {"properties": {"delegations": [{"properties": {"serviceName": "Microsoft.App/environments"}}], "routeTable": {"id": f"{BASE}/providers/Microsoft.Network/routeTables/rt"}}},
        IDENTITY_ID: {"properties": {"principalId": OPERATOR_PRINCIPAL}},
        GATEWAY_ROLES: {"value": [assignment(prep.MODELS_USER, OPERATOR_PRINCIPAL, GATEWAY_ID)]},
        ACCOUNT_ROLES: {"value": [assignment(prep.FOUNDRY_USER, GATEWAY_PRINCIPAL, ACCOUNT_ID)]},
    }


class Azure:
    """An Azure Resource Manager that answers `az rest` from a dictionary of documents (the keys are paths), keeps every request, and can be told what to answer instead for one request."""

    def __init__(self, documents=None):
        self.documents = {path.lower(): document for path, document in (world() if documents is None else documents).items()}
        self.calls = []
        self.failures = {}
        self.sleeps = []

    def fail(self, method, path, error, code=1):
        self.failures[(method, path.lower())] = (code, error)

    def doc(self, path):
        return self.documents[path.lower()]

    def __call__(self, arguments):
        assert arguments[0] == "rest", arguments
        method = arguments[arguments.index("--method") + 1]
        url = arguments[arguments.index("--url") + 1]
        body = json.loads(arguments[arguments.index("--body") + 1]) if "--body" in arguments else None
        path = url[len(prep.ARM):].split("?")[0]
        self.calls.append((method, path, url, body))
        failure = self.failures.get((method, path.lower()))
        if failure:
            code, error = failure
            if isinstance(error, BaseException):
                raise error
            return code, "", error
        key = path.lower()
        if method == "get":
            return (0, json.dumps(self.documents[key]), "") if key in self.documents else (1, "", NOT_FOUND)
        if method == "patch":
            self.documents[key]["properties"].update(body["properties"])
            return 0, json.dumps(self.documents[key]), ""
        if method == "delete":
            parent, name = path.rsplit("/", 1)
            self.documents[parent.lower()]["value"] = [item for item in self.documents[parent.lower()]["value"] if item["name"] != name]
            return 0, "", ""
        raise AssertionError(method)

    def writes(self):
        return [call for call in self.calls if call[0] != "get"]


def run(argv, azure, summary=None, actions=True, extra=None):
    out, err = io.StringIO(), io.StringIO()
    with hubenv.patched(actions, extra), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = prep.main([*argv, *(["--summary", str(summary)] if summary else [])], az=azure, sleep=azure.sleeps.append)
    return code, out.getvalue(), err.getvalue()


def policy_file(directory, policies=None):
    path = Path(directory) / "policies.json"
    path.write_text(json.dumps(POLICIES if policies is None else policies), encoding="utf-8")
    return path


class Merge(unittest.TestCase):
    def test_a_policy_that_is_not_there_is_added_and_one_that_is_there_is_updated_in_place_and_keeps_what_else_it_holds(self):
        current = [{"type": "tokenLimit", "count": 1000, "period": "minute", "counterKey": ["identity"], "scope": "workspace", "id": "kept", "spent": 7},
                   {"type": "costLimit", "id": "meternaut-day", "amount": 20.0, "period": "day", "counterKey": ["identity"], "scope": "workspace", "counted": 3.5}]
        merged, changes = prep.merge(current, POLICIES)
        self.assertEqual([p["type"] for p in merged], ["tokenLimit", "costLimit", "requestRateLimit", "costLimit"])
        self.assertEqual((merged[0]["count"], merged[0]["id"], merged[0]["spent"]), (50000, "kept", 7), "updated in place: the id and the other fields stay")
        self.assertEqual((merged[1]["amount"], merged[1]["counted"]), (5, 3.5), "a cost limit keeps what it has counted")
        self.assertEqual(merged[2]["callsPerPeriod"], 60)
        self.assertEqual(merged[3]["id"], "meternaut-month")
        self.assertEqual(changes, ["updates tokenLimit (count 1000 to 50000)", "adds requestRateLimit", "updates costLimit meternaut-day (amount 20 to 5)", "adds costLimit meternaut-month"])

    def test_a_cost_limit_is_found_by_its_id_and_a_policy_of_another_type_is_left_as_it_is(self):
        current = [{"type": "costLimit", "id": "default", "amount": 1, "period": "day", "counterKey": ["identity"], "scope": "workspace"},
                   {"type": "ipFilter", "action": "Allow", "cidrRanges": ["10.0.0.0/8"]}, "not even an object"]
        merged, changes = prep.merge(current, POLICIES)
        self.assertEqual(merged[:3], current, "another id of the same type, another type, and anything else are never changed")
        self.assertEqual([p["id"] for p in merged if isinstance(p, dict) and p.get("type") == "costLimit"], ["default", "meternaut-day", "meternaut-month"])
        self.assertEqual(len(changes), 4)

    def test_numbers_are_compared_as_numbers_so_that_a_policy_that_is_there_is_not_written_again(self):
        current = copy.deepcopy(POLICIES)
        current[2]["amount"] = 5.0
        current[3]["amount"] = 25.0
        current[0]["scope"] = "workspace"
        extra = {**current[0], "extra": "kept"}
        merged, changes = prep.merge([extra, *current[1:]], POLICIES)
        self.assertEqual((merged, changes), ([extra, *current[1:]], []))
        self.assertTrue(prep.holds({"amount": 5.0, "x": 1}, {"amount": 5}))
        self.assertFalse(prep.holds({"amount": True}, {"amount": 1}), "a switch is not a number")
        self.assertFalse(prep.holds({"counterKey": ["ipAddress"]}, {"counterKey": ["identity"]}))
        self.assertFalse(prep.holds({}, {"amount": 5}))

    def test_the_lines_that_describe_a_policy_hold_names_and_numbers_only(self):
        for policy, expected in ((POLICIES[0], "tokenLimit: 50000 tokens a minute for each caller (workspace)"),
                                 (POLICIES[1], "requestRateLimit: 60 calls in 60 seconds for each caller (workspace)"),
                                 (POLICIES[2], "costLimit meternaut-day: 5 US dollars a day for each caller (workspace)"),
                                 ({"type": "ipFilter", "cidrRanges": ["203.0.113.0/24"]}, "ipFilter: a policy of this type is there (not managed here)"),
                                 ({"type": "tokenLimit", "count": "SECRET", "period": "mi nute!", "scope": "work space"}, "tokenLimit: ? tokens a mi?nute? for each caller (work?space)")):
            self.assertEqual(prep.describe_policy(policy), expected)


class Policies(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.file = policy_file(self.directory.name)

    def command(self, azure, **kwargs):
        return run(["policies", *ARGUMENTS, "--file", str(self.file)], azure, **kwargs)

    def test_it_refuses_to_run_anywhere_but_in_a_run_of_the_workflow_and_asks_azure_nothing(self):
        azure = Azure()
        code, out, err = self.command(azure, actions=False)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("this command writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)", err)
        self.assertEqual(azure.calls, [])

    def test_a_process_that_only_says_that_github_actions_is_true_is_refused_and_the_refusal_names_what_is_missing(self):
        azure = Azure()
        code, out, err = self.command(azure, actions=False, extra={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, out), (2, ""))
        self.assertIn("GITHUB_ACTIONS=true alone is no proof", err)
        self.assertIn("METERNAUT_HUB_PROOF", err)
        self.assertEqual(azure.calls, [])

    def test_the_proof_of_a_run_of_tools_hub_local_that_is_alive_is_enough_and_a_stale_one_is_not(self):
        with tempfile.TemporaryDirectory() as folder:
            azure = Azure(world(policies=[]))
            code, _, err = self.command(azure, actions=False, extra={"METERNAUT_HUB_PROOF": str(hubenv.make_proof(folder))})
            self.assertEqual(code, 0, err)
            azure = Azure()
            code, out, err = self.command(azure, actions=False, extra={"METERNAUT_HUB_PROOF": str(hubenv.make_proof(folder, pid=hubenv.dead_pid()))})
            self.assertEqual((code, out), (2, ""))
            self.assertIn("is not alive: this proof is stale", err)
            self.assertEqual(azure.calls, [])

    def test_an_empty_workspace_gets_the_four_policies_in_one_patch_that_holds_nothing_else_and_they_are_read_back(self):
        azure = Azure(world(policies=[]))
        code, out, err = self.command(azure)
        self.assertEqual((code, err), (0, ""), out)
        patches = [call for call in azure.calls if call[0] == "patch"]
        self.assertEqual(len(patches), 1)
        method, path, url, body = patches[0]
        self.assertEqual(path, WORKSPACE)
        self.assertTrue(url.endswith("?api-version=2025-09-01-preview"), url)
        self.assertEqual(body, {"properties": {"policies": POLICIES}}, "the policies and nothing else of the workspace")
        self.assertEqual(azure.writes(), [patches[0]], "no other write: no key, no model, no role")
        for line in ("note: The merge adds tokenLimit", "note: The merge adds costLimit meternaut-month", "ok: The merged policies were written to the workspace (one PATCH)",
                     "ok: Read back: tokenLimit: 50000 tokens a minute for each caller (workspace)", "ok: Read back: requestRateLimit: 60 calls in 60 seconds for each caller (workspace)",
                     "ok: Read back: costLimit meternaut-day: 5 US dollars a day for each caller (workspace)", "ok: Read back: costLimit meternaut-month: 25 US dollars a month for each caller (workspace)"):
            self.assertIn(line, out)
        self.assertEqual(azure.calls[0][1], GATEWAY_ID, "the gateway is read first")
        self.assertEqual(azure.calls[1][1], WORKSPACE)

    def test_a_workspace_that_holds_them_already_is_not_written_again(self):
        azure = Azure()
        code, out, err = self.command(azure)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(azure.writes(), [])
        self.assertIn("ok: The gateway-wide policies are as environment/aigateway/policies.json says: nothing to change", out)

    def test_what_a_person_added_in_the_portal_stays_and_an_updated_policy_keeps_its_counted_spend(self):
        current = [{"type": "ipFilter", "action": "Allow", "cidrRanges": ["203.0.113.0/24"], "scope": "workspace"},
                   {"type": "costLimit", "id": "default", "amount": 3, "period": "week", "counterKey": ["identity"], "scope": "workspace"},
                   {**POLICIES[2], "amount": 20, "counted": 4.25}]
        azure = Azure(world(policies=current))
        code, out, err = self.command(azure)
        self.assertEqual((code, err), (0, ""), out)
        body = [call for call in azure.calls if call[0] == "patch"][0][3]["properties"]["policies"]
        self.assertEqual(body[:2], current[:2], "the filter and the other cost limit are untouched")
        self.assertEqual((body[2]["amount"], body[2]["counted"]), (5, 4.25))
        self.assertEqual([p["type"] for p in body], ["ipFilter", "costLimit", "costLimit", "tokenLimit", "requestRateLimit", "costLimit"])
        self.assertIn("note: The merge updates costLimit meternaut-day (amount 20 to 5)", out)

    def test_a_refusal_of_the_service_is_said_with_its_first_line_and_with_what_to_do_and_nothing_else_is_written(self):
        azure = Azure(world(policies=[]))
        azure.fail("patch", WORKSPACE, "ERROR: Bad Request({\"error\":{\"code\":\"InvalidPolicy\",\"message\":\"Only one costLimit policy is allowed.\"}})\nsecond line that is not printed")
        code, out, err = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("FAILED: The service refused the policies: ERROR: Bad Request", out)
        self.assertIn("Only one costLimit policy is allowed.", out)
        self.assertNotIn("second line that is not printed", out)
        self.assertIn("If it refuses a second cost limit", out)
        self.assertIn("AGENTS.md rule 15 (g)", out)
        self.assertEqual(len(azure.writes()), 1, "one attempt, and no retry")
        self.assertIn("thing(s) are not as they should be. The run fails; nothing is repaired from here.", err)

    def test_a_refusal_of_the_deploy_identity_a_slow_az_and_an_answer_that_is_not_usable_fail_the_run_and_say_which(self):
        for error, expected in (("ERROR: (AuthorizationFailed) The client does not have authorization to perform action", "Azure does not allow the deploy identity this request"),
                                ("ERROR: Forbidden({})", "Azure does not allow the deploy identity this request"),
                                ("ERROR: (InternalServerError) try again later", "Azure gave no usable answer"),
                                (prep.Stuck("az did not answer within 120 seconds (PATCH /subscriptions/x)"), "az did not answer within 120 seconds")):
            with self.subTest(error=str(error)[:40]):
                azure = Azure(world(policies=[]))
                azure.fail("patch", WORKSPACE, error)
                code, out, err = self.command(azure)
                self.assertEqual(code, 1)
                self.assertIn(expected, out)

    def test_a_gateway_that_is_not_ready_a_workspace_that_is_not_there_and_a_gateway_that_is_not_there_stop_before_anything_is_written(self):
        azure = Azure()
        azure.doc(GATEWAY_ID)["properties"]["provisioningState"] = "Updating"
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("The gateway is in the state Updating and not Succeeded: nothing was changed", out)
        self.assertEqual(azure.writes(), [])
        azure = Azure()
        del azure.documents[WORKSPACE.lower()]
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("The gateway's default workspace is not there", out)
        azure = Azure({})
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn(f"The gateway {GATEWAY} is not there: nothing was changed", out)
        self.assertEqual(azure.writes(), [])

    def test_a_write_that_does_not_show_in_the_read_back_fails_after_six_reads_and_five_waits(self):
        azure = Azure(world(policies=[]))
        original = azure.__call__

        def patch_that_changes_nothing(arguments):
            if arguments[arguments.index("--method") + 1] == "patch":
                return 0, "{}", ""
            return original(arguments)

        out, err = io.StringIO(), io.StringIO()
        with hubenv.patched(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = prep.main(["policies", *ARGUMENTS, "--file", str(self.file)], az=patch_that_changes_nothing, sleep=azure.sleeps.append)
        self.assertEqual(code, 1)
        self.assertEqual(azure.sleeps, [prep.READ_BACK_SECONDS] * 5)
        self.assertIn("Read back (check 6 of 6): not there yet or different: tokenLimit, requestRateLimit, costLimit meternaut-day, costLimit meternaut-month", out.getvalue())
        self.assertIn("FAILED: After the write the workspace does not hold: tokenLimit", out.getvalue())

    def test_a_policy_that_differs_after_the_write_is_named(self):
        azure = Azure(world(policies=[]))
        original = azure.__call__

        def patch_with_another_amount(arguments):
            if arguments[arguments.index("--method") + 1] == "patch":
                body = json.loads(arguments[arguments.index("--body") + 1])
                body["properties"]["policies"][2]["amount"] = 50
                azure.documents[WORKSPACE.lower()]["properties"].update(body["properties"])
                return 0, "{}", ""
            return original(arguments)

        out = io.StringIO()
        with hubenv.patched(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = prep.main(["policies", *ARGUMENTS, "--file", str(self.file)], az=patch_with_another_amount, sleep=lambda seconds: None)
        self.assertEqual(code, 1)
        self.assertIn("different: costLimit meternaut-day", out.getvalue())

    def test_the_lines_go_to_the_summary_too_and_a_file_that_is_not_a_list_of_managed_policies_is_refused(self):
        summary = Path(self.directory.name) / "summary.md"
        azure = Azure(world(policies=[]))
        code, out, _ = self.command(azure, summary=summary)
        self.assertEqual(code, 0)
        text = summary.read_text(encoding="utf-8")
        self.assertIn("### The gateway-wide policies of the AI Gateway", text)
        self.assertIn("ok: Read back: costLimit meternaut-month: 25 US dollars a month", text)
        for content in ("[", "{}", "[]", json.dumps([{"type": "ipFilter", "action": "Allow"}])):
            policy_file(self.directory.name).write_text(content, encoding="utf-8")
            azure = Azure()
            code, out, err = self.command(azure)
            self.assertEqual((code, out), (2, ""), content)
            self.assertIn("is not a", err)
            self.assertEqual(azure.calls, [], "nothing is asked before the file is accepted")

    def test_a_wrong_name_is_refused_before_azure_is_asked(self):
        for arguments in (["--subscription", "x", "--resource-group", GROUP, "--gateway", GATEWAY], ["--subscription", SUBSCRIPTION, "--resource-group", "../x", "--gateway", GATEWAY],
                          ["--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--gateway", "Aigw/../x"]):
            azure = Azure()
            code, out, err = run(["policies", *arguments, "--file", str(self.file)], azure)
            self.assertEqual((code, out), (2, ""), arguments)
            self.assertIn("--subscription is a subscription id", err)
            self.assertEqual(azure.calls, [])


class RemoveKey(unittest.TestCase):
    def command(self, azure, **kwargs):
        return run(["remove-key", *ARGUMENTS], azure, **kwargs)

    def test_it_refuses_to_run_anywhere_but_in_a_run_of_the_workflow_and_asks_azure_nothing(self):
        azure = Azure()
        code, out, err = self.command(azure, actions=False)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("only a GitHub Actions run may do that", err)
        self.assertEqual(azure.calls, [])

    def test_a_gateway_without_the_key_has_nothing_to_delete_and_nothing_is_written(self):
        azure = Azure(world(keys=()))
        code, out, err = self.command(azure)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("note: The API keys of the gateway, by name: none", out)
        self.assertIn("ok: The built-in key master is not there: nothing to delete", out)
        self.assertEqual(azure.writes(), [])

    def test_the_key_is_read_then_deleted_once_by_its_name_and_read_again_and_no_value_is_printed_or_written_anywhere(self):
        azure = Azure()
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            code, out, err = self.command(azure, summary=summary)
            written = summary.read_text(encoding="utf-8")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([call[:2] for call in azure.calls], [("get", KEYS), ("delete", f"{KEYS}/master"), ("get", KEYS)], "read first, delete, read back")
        self.assertTrue(azure.calls[1][2].endswith("?api-version=2025-09-01-preview"))
        self.assertIn("note: The API keys of the gateway, by name: master", out)
        self.assertIn("ok: Read back: the built-in key master is deleted", out)
        for text in (out, err, written, " ".join(call[2] for call in azure.calls)):
            self.assertNotIn(SECRET, text, "the value of a key is never printed, and the tool never asks for one")
        self.assertEqual(azure.sleeps, [])

    def test_a_key_with_another_name_is_never_deleted_and_is_said(self):
        azure = Azure(world(keys=("master", "mine")))
        code, out, _ = self.command(azure)
        self.assertEqual(code, 0)
        self.assertEqual([call[:2] for call in azure.writes()], [("delete", f"{KEYS}/master")])
        self.assertIn("note: The API keys of the gateway, by name: master, mine", out)
        self.assertIn("The key(s) mine are not the built-in key and are not deleted here", out)

    def test_a_refusal_of_the_service_is_a_finding_that_says_the_key_path_exists_and_is_unused_and_not_a_failure(self):
        for error in ("ERROR: Bad Request({\"error\":{\"code\":\"BadRequest\",\"message\":\"The built-in key cannot be deleted.\"}})", "ERROR: (Conflict) The key is in use.",
                      "ERROR: Method Not Allowed", "ERROR: (PreconditionFailed) the key is protected", "ERROR: the request failed with status 405", "ERROR: the key is built-in"):
            with self.subTest(error=error[:50]):
                azure = Azure()
                azure.fail("delete", f"{KEYS}/master", error)
                with tempfile.TemporaryDirectory() as directory:
                    summary = Path(directory) / "summary.md"
                    code, out, err = self.command(azure, summary=summary)
                    written = summary.read_text(encoding="utf-8")
                self.assertEqual((code, err), (0, ""), out)
                self.assertIn("FINDING: The service refuses to delete the built-in key master:", out)
                self.assertIn("The key path exists and is unused", out)
                self.assertIn("is not a failure", out)
                self.assertNotIn("FAILED", out)
                self.assertIn("FINDING:", written)
                self.assertEqual(len(azure.writes()), 1, "one attempt, and no retry")
                self.assertNotIn(SECRET, out + written)

    def test_what_is_not_a_refusal_fails_the_run_because_nothing_is_known_about_the_services_answer(self):
        for error, expected in (("ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.ApiManagement/aigateways/apiKeys/delete'", "Azure does not allow the deploy identity"),
                                ("ERROR: Forbidden({\"error\": \"not allowed here\"})", "Azure does not allow the deploy identity"),
                                ("ERROR: Unauthorized", "Azure does not allow the deploy identity"),
                                ("ERROR: (InternalServerError) An error occurred", "Azure gave no usable answer"),
                                ("ERROR: (TooManyRequests) Too many requests", "Azure gave no usable answer"),
                                ("ERROR: something that nobody has seen before", "Azure gave no usable answer"),
                                (prep.Stuck("az did not answer within 120 seconds (DELETE /x)"), "az did not answer within 120 seconds")):
            with self.subTest(error=str(error)[:50]):
                azure = Azure()
                azure.fail("delete", f"{KEYS}/master", error)
                code, out, err = self.command(azure)
                self.assertEqual(code, 1, out)
                self.assertIn(expected, out)
                self.assertNotIn("FINDING", out, "a failure is not a finding")

    def test_a_delete_that_the_service_accepts_and_that_does_not_show_is_a_finding_after_six_reads_and_five_waits(self):
        azure = Azure()
        original = azure.__call__

        def delete_that_deletes_nothing(arguments):
            if arguments[arguments.index("--method") + 1] == "delete":
                return 0, "", ""
            return original(arguments)

        out = io.StringIO()
        with hubenv.patched(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = prep.main(["remove-key", *ARGUMENTS], az=delete_that_deletes_nothing, sleep=azure.sleeps.append)
        self.assertEqual(code, 0)
        self.assertEqual(azure.sleeps, [prep.READ_BACK_SECONDS] * 5)
        self.assertIn("Read back (check 6 of 6): the key master is still listed", out.getvalue())
        self.assertIn("FINDING: The service accepted the delete of the built-in key master and still lists it", out.getvalue())

    def test_a_key_that_is_gone_when_the_delete_arrives_is_gone(self):
        azure = Azure()

        def raced(arguments):
            if arguments[arguments.index("--method") + 1] == "delete":
                azure.documents[KEYS.lower()]["value"] = []
                return 1, "", NOT_FOUND
            return azure(arguments)

        out = io.StringIO()
        with hubenv.patched(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = prep.main(["remove-key", *ARGUMENTS], az=raced, sleep=lambda seconds: None)
        self.assertEqual(code, 0)
        self.assertIn("note: The service says that the key master is not there any more", out.getvalue())
        self.assertIn("ok: Read back: the built-in key master is deleted", out.getvalue())

    def test_a_gateway_that_is_not_there_fails_and_writes_nothing(self):
        azure = Azure({})
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn(f"The gateway {GATEWAY} is not there, so its keys cannot be read", out)
        self.assertEqual(azure.writes(), [])


class ReadBack(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.models = Path(self.directory.name) / "models.json"
        self.models.write_text(json.dumps(MODELS), encoding="utf-8")
        self.policies = policy_file(self.directory.name)

    def command(self, azure, *extra, **kwargs):
        return run(["read-back", *ARGUMENTS, "--vnet", "vnet-meternaut", "--subnet", "snet-aigw", "--foundry-account", ACCOUNT, "--operator-identity", OPERATOR,
                    "--models", str(self.models), "--policies", str(self.policies), *extra], azure, **kwargs)

    def test_a_gateway_that_is_as_its_template_says_passes_and_the_lines_say_what_was_read(self):
        azure = Azure()
        code, out, err = self.command(azure)
        self.assertEqual((code, err), (0, ""), out)
        for line in ("ok: The gateway is in the state Succeeded", "ok: The backend subnet of the gateway is snet-aigw", "ok: The gateway has a system-assigned identity",
                     "ok: The service reports the gateway's host name", f"ok: The subnet snet-aigw is delegated to Microsoft.App/environments and to nothing else",
                     "note: The subnet carries a route table: yes", "note: The model providers of the gateway, by name: foundry",
                     f"ok: The provider foundry: kind Foundry, the Foundry resource {ACCOUNT}, called with the gateway's managed identity and no key",
                     "ok: The model gpt-6-luna: deployment gpt-6-luna version 2026-09-22, content safety Medium for the four categories",
                     "ok: The model gpt-6-1-sol: deployment gpt-6.1-sol version 2026-09-29, content safety Medium for the four categories",
                     "ok: The alias gpt-6-luna points to the model gpt-6-luna, and to nothing else", "ok: The alias gpt-6.1-sol points to the model gpt-6-1-sol, and to nothing else",
                     "ok: The policy tokenLimit: 50000 tokens a minute for each caller (workspace)", "ok: The policy requestRateLimit: 60 calls in 60 seconds for each caller (workspace)",
                     "ok: The policy costLimit meternaut-day: 5 US dollars a day for each caller (workspace)", "ok: The policy costLimit meternaut-month: 25 US dollars a month for each caller (workspace)",
                     "ok: The Operator's identity holds AI Gateway Models User on the gateway", "note: No principal of the Foundry project was given",
                     f"ok: The gateway's identity holds Foundry User on the Foundry resource {ACCOUNT}",
                     "note: The API keys of the gateway, by name: master. The service makes the built-in key master; it is unused"):
            self.assertIn(line, out)
        self.assertEqual(azure.writes(), [], "only reads")
        self.assertNotRegex(out, r"(?m)^FAILED")

    def test_public_network_access_is_printed_as_the_service_reports_it_and_is_never_judged(self):
        for reported in ("Enabled", "Disabled", None):
            azure = Azure()
            azure.doc(GATEWAY_ID)["properties"]["publicNetworkAccess"] = reported
            code, out, err = self.command(azure)
            self.assertEqual((code, err), (0, ""), reported)
            self.assertIn(f"note: The service reports publicNetworkAccess {reported if reported else 'None'}. The frontend is public whatever that says: the service has no private endpoint and no private frontend", out)
            self.assertIn("docs/proposals/08-ai-gateway.md", out)

    def test_everything_that_is_read_is_a_get_of_the_places_below_and_the_versions_that_the_template_uses(self):
        azure = Azure()
        self.command(azure)
        paths = {call[1] for call in azure.calls}
        self.assertEqual(paths, {GATEWAY_ID, WORKSPACE, f"{WORKSPACE}/modelProviders", f"{WORKSPACE}/modelProviders/foundry/models", f"{WORKSPACE}/aliases", KEYS, SUBNET_ID,
                                 IDENTITY_ID, GATEWAY_ROLES, ACCOUNT_ROLES})
        self.assertEqual({call[0] for call in azure.calls}, {"get"})

        def expected_version(path):
            for marker, version in (("/Microsoft.Network/", "2025-05-01"), ("/Microsoft.ManagedIdentity/", "2023-01-31"), ("/Microsoft.Authorization/", "2022-04-01")):
                if marker in path:
                    return version
            return "2025-09-01-preview"

        for method, path, url, _ in azure.calls:
            self.assertEqual(re.search(r"api-version=([^&]+)", url).group(1), expected_version(path), path)
        roles = [call[2] for call in azure.calls if call[1] in (GATEWAY_ROLES, ACCOUNT_ROLES)]
        self.assertEqual(len(roles), 2)
        for url in roles:
            self.assertTrue(url.endswith("&%24filter=atScope()"), url)

    def mutations(self):
        """What can be wrong, as a change to the world, and the words that the failure has to hold."""

        def models(change):
            return lambda azure: change(azure.doc(f"{WORKSPACE}/modelProviders/foundry/models")["value"])

        def provider(azure):
            return azure.doc(f"{WORKSPACE}/modelProviders")["value"][0]["properties"]

        return {
            "the gateway is still updating": (lambda a: a.doc(GATEWAY_ID)["properties"].update(provisioningState="Updating"), "The gateway is in the state Updating and not Succeeded"),
            "the subnet is not the one of the template": (lambda a: a.doc(GATEWAY_ID)["properties"]["backend"]["subnet"].update(id=SUBNET_ID.replace("snet-aigw", "snet-other")),
                                                           "The backend subnet of the gateway is not snet-aigw (the service reports snet-other)"),
            "no backend subnet": (lambda a: a.doc(GATEWAY_ID)["properties"].pop("backend"), "The backend subnet of the gateway is not snet-aigw (the service reports nothing)"),
            "no identity": (lambda a: a.doc(GATEWAY_ID).pop("identity"), "The gateway has no system-assigned identity"),
            "a user-assigned identity only": (lambda a: a.doc(GATEWAY_ID).update(identity={"type": "UserAssigned", "principalId": GATEWAY_PRINCIPAL}), "The gateway has no system-assigned identity"),
            "no host name": (lambda a: a.doc(GATEWAY_ID)["properties"].pop("frontend"), "The service does not report a host name under .ai.gateway.azure.com"),
            "the subnet lost its delegation": (lambda a: a.doc(SUBNET_ID)["properties"].update(delegations=[]), "is not delegated to Microsoft.App/environments alone (delegations: none)"),
            "the subnet has a second delegation": (lambda a: a.doc(SUBNET_ID)["properties"]["delegations"].append({"properties": {"serviceName": "Microsoft.Web/serverFarms"}}),
                                                   "is not delegated to Microsoft.App/environments alone"),
            "no provider": (lambda a: a.doc(f"{WORKSPACE}/modelProviders").update(value=[]), "The provider foundry is not there"),
            "the provider is not of kind Foundry": (lambda a: provider(a).update(kind="OpenAI"), "The provider foundry differs from its template (kind OpenAI"),
            "the provider does not use the managed identity": (lambda a: provider(a)["foundry"]["authentication"].update(kind="ApiKey"), "authentication ApiKey"),
            "the provider points to another resource": (lambda a: provider(a)["foundry"].update(resourceIds=[ACCOUNT_ID.replace(ACCOUNT, "aif-other")]), "not among them"),
            "a model is missing": (models(lambda m: m.pop()), "The model gpt-5-5 is not there"),
            "a model has another version": (models(lambda m: m[0]["properties"]["deployment"].update(modelVersion="2000-01-01")), "The model gpt-6-luna differs from its template: the model and its version"),
            "a model points to another deployment": (models(lambda m: m[0]["properties"]["deployment"].update(resourceId=ACCOUNT_ID + "/deployments/other")), "the deployment that it points to"),
            "a model has another API format": (models(lambda m: m[1]["properties"].update(apiFormat="OpenAIResponses")), "the API format"),
            "a model does not list the chat completions endpoint": (models(lambda m: m[0]["properties"].update(supportedEndpoints=["/openai/v1/responses"])), "the chat completions endpoint"),
            "a model lists no endpoint at all": (models(lambda m: m[1]["properties"].pop("supportedEndpoints")), "the chat completions endpoint"),
            "content safety is at High for one category": (models(lambda m: m[0]["properties"]["policies"][0].update(hateSeverity="High")), "content safety at Medium for the four categories"),
            "content safety is missing": (models(lambda m: m[0]["properties"].update(policies=[])), "content safety at Medium for the four categories"),
            "content safety is there twice": (models(lambda m: m[0]["properties"]["policies"].append(copy.deepcopy(m[0]["properties"]["policies"][0]))), "content safety at Medium"),
            "an alias is missing": (lambda a: a.doc(f"{WORKSPACE}/aliases")["value"].pop(0), "The alias gpt-6-luna is not there"),
            "an alias points to the wrong model": (lambda a: a.doc(f"{WORKSPACE}/aliases")["value"][0]["properties"]["backendModels"][0].update(resourceId=f"{WORKSPACE}/modelProviders/foundry/models/other"),
                                                   "The alias gpt-6-luna differs from its template (it has 1 target(s))"),
            "an alias has two targets": (lambda a: a.doc(f"{WORKSPACE}/aliases")["value"][0]["properties"]["backendModels"].append({"resourceId": "x"}), "(it has 2 target(s))"),
            "the token limit is another number": (lambda a: a.doc(WORKSPACE)["properties"]["policies"][0].update(count=99999), "The policy tokenLimit differs from environment/aigateway/policies.json: it holds tokenLimit: 99999 tokens a minute"),
            "the token limit is missing": (lambda a: a.doc(WORKSPACE)["properties"]["policies"].pop(0), "The policy tokenLimit is not there"),
            "a cost limit is another number": (lambda a: a.doc(WORKSPACE)["properties"]["policies"][3].update(amount=250), "The policy costLimit meternaut-month differs"),
            "a cost limit counts for everyone together": (lambda a: a.doc(WORKSPACE)["properties"]["policies"][2].update(counterKey=[]), "The policy costLimit meternaut-day differs"),
            "no policy at all": (lambda a: a.doc(WORKSPACE)["properties"].pop("policies"), "The policy requestRateLimit is not there"),
            "the Operator has no role": (lambda a: a.doc(GATEWAY_ROLES).update(value=[]), "The Operator's identity does not hold AI Gateway Models User on the gateway"),
            "the Operator has the role for another gateway": (lambda a: a.doc(GATEWAY_ROLES).update(value=[assignment(prep.MODELS_USER, OPERATOR_PRINCIPAL, GATEWAY_ID + "-other")]),
                                                              "The Operator's identity does not hold AI Gateway Models User on the gateway"),
            "the Operator has another role": (lambda a: a.doc(GATEWAY_ROLES).update(value=[assignment(prep.FOUNDRY_USER, OPERATOR_PRINCIPAL, GATEWAY_ID)]), "The Operator's identity does not hold AI Gateway Models User"),
            "the Operator's identity is not there": (lambda a: a.documents.pop(IDENTITY_ID.lower()), f"The Operator's identity {OPERATOR} is not there"),
            "the gateway has no role on the Foundry resource": (lambda a: a.doc(ACCOUNT_ROLES).update(value=[]), f"The gateway's identity does not hold Foundry User on the Foundry resource {ACCOUNT}"),
            "another principal has the Foundry role": (lambda a: a.doc(ACCOUNT_ROLES).update(value=[assignment(prep.FOUNDRY_USER, OTHER_PRINCIPAL, ACCOUNT_ID)]), "The gateway's identity does not hold Foundry User"),
            "an API key that the template does not make": (lambda a: a.doc(KEYS)["value"].append({"name": "mine", "properties": {"value": SECRET}}), "API keys exist that the template does not make: mine"),
            "the gateway is not there": (lambda a: a.documents.pop(GATEWAY_ID.lower()), f"The gateway {GATEWAY} is not there"),
            "the workspace is not there": (lambda a: a.documents.pop(WORKSPACE.lower()), "The default workspace is not there"),
        }

    def test_each_thing_that_differs_from_the_template_fails_the_run_and_says_what(self):
        for what, (change, expected) in self.mutations().items():
            with self.subTest(what):
                azure = Azure()
                change(azure)
                code, out, err = self.command(azure)
                self.assertEqual(code, 1, out)
                failures = [line for line in out.splitlines() if line.startswith("FAILED: ")]
                self.assertTrue(any(expected in line for line in failures), f"{expected!r} is in none of {failures}")
                self.assertIn("thing(s) are not as they should be. The run fails; nothing is repaired from here.", err)
                self.assertNotIn(SECRET, out + err)

    def test_the_built_in_key_that_the_service_would_not_delete_is_a_note_and_any_other_key_is_a_failure(self):
        azure = Azure(world(keys=("master",)))
        self.assertEqual(self.command(azure)[0], 0)
        azure = Azure(world(keys=()))
        code, out, _ = self.command(azure)
        self.assertEqual(code, 0)
        self.assertIn("ok: The gateway has no API key", out)
        azure = Azure(world(keys=("master", "other", "another")))
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("FAILED: API keys exist that the template does not make: another, other. No key is used by this project (AGENTS.md rule 23)", out)
        self.assertNotIn(SECRET, out)

    def test_the_project_principal_is_checked_when_it_is_given_and_what_else_is_held_is_only_a_note(self):
        azure = Azure()
        code, out, _ = self.command(azure, "--project-principal", PROJECT_PRINCIPAL)
        self.assertEqual(code, 1)
        self.assertIn("FAILED: The Foundry project's identity does not hold AI Gateway Models User on the gateway", out)
        azure = Azure()
        azure.doc(GATEWAY_ROLES)["value"].append(assignment(prep.MODELS_USER, PROJECT_PRINCIPAL.upper(), GATEWAY_ID.upper()))
        azure.doc(GATEWAY_ROLES)["value"].append(assignment("caad7a21-134e-43f4-a550-c5ffc17e051c", OTHER_PRINCIPAL, GATEWAY_ID))
        azure.doc(GATEWAY_ROLES)["value"].append(assignment("8e3af657-a8ff-443c-a75c-2fe8c4bcb635", OTHER_PRINCIPAL, BASE))
        code, out, _ = self.command(azure, "--project-principal", PROJECT_PRINCIPAL)
        self.assertEqual(code, 0, out)
        self.assertIn("ok: The Foundry project's identity holds AI Gateway Models User on the gateway", out)
        self.assertIn(f"note: AI Gateway User is also held on the gateway by the principal {OTHER_PRINCIPAL}", out)
        self.assertNotIn("8e3af657", out, "a role of no concern to the gateway's data actions is not listed")

    def test_the_cases_apps_principal_is_required_when_it_is_given_and_is_a_note_when_it_is_not(self):
        # The Detective and the Skeptic call the gateway with the cases app's own identity, so the role of that identity is read back like the Operator's.
        azure = Azure()
        code, out, _ = self.command(azure)
        self.assertEqual(code, 0, out)
        self.assertIn("note: No principal of the cases app was given: the app has no identity of its own before the action cases has made it", out)
        azure = Azure()
        code, out, _ = self.command(azure, "--cases-principal", CASES_PRINCIPAL)
        self.assertEqual(code, 1)
        self.assertIn("FAILED: The cases app's identity does not hold AI Gateway Models User on the gateway, so the Detective and the Skeptic cannot call the models", out)
        self.assertNotIn("No principal of the cases app was given", out)
        azure = Azure()
        azure.doc(GATEWAY_ROLES)["value"].append(assignment(prep.MODELS_USER, CASES_PRINCIPAL.upper(), GATEWAY_ID.upper()))
        code, out, _ = self.command(azure, "--cases-principal", CASES_PRINCIPAL)
        self.assertEqual(code, 0, out)
        self.assertIn("ok: The cases app's identity holds AI Gateway Models User on the gateway", out)
        self.assertNotIn("is also held on the gateway by the principal", out, "the three callers that are expected are not listed as others")
        self.assertEqual(azure.writes(), [], "only reads")

    def test_the_cases_apps_role_on_another_scope_or_another_role_is_not_the_role_that_is_asked_for(self):
        for role, scope in ((prep.FOUNDRY_USER, GATEWAY_ID), ("caad7a21-134e-43f4-a550-c5ffc17e051c", GATEWAY_ID), (prep.MODELS_USER, BASE), (prep.MODELS_USER, ACCOUNT_ID)):
            azure = Azure()
            azure.doc(GATEWAY_ROLES)["value"].append(assignment(role, CASES_PRINCIPAL, scope))
            code, out, _ = self.command(azure, "--cases-principal", CASES_PRINCIPAL)
            self.assertEqual(code, 1, (role, scope))
            self.assertIn("FAILED: The cases app's identity does not hold AI Gateway Models User on the gateway", out)

    def test_what_else_is_held_is_only_a_note_also_when_the_cases_principal_is_given(self):
        azure = Azure()
        azure.doc(GATEWAY_ROLES)["value"].append(assignment(prep.MODELS_USER, CASES_PRINCIPAL, GATEWAY_ID))
        azure.doc(GATEWAY_ROLES)["value"].append(assignment(prep.MODELS_USER, OTHER_PRINCIPAL, GATEWAY_ID))
        code, out, _ = self.command(azure, "--cases-principal", CASES_PRINCIPAL, "--project-principal", PROJECT_PRINCIPAL)
        self.assertEqual(code, 1, "the project's role is missing, and that fails")
        self.assertIn(f"note: AI Gateway Models User is also held on the gateway by the principal {OTHER_PRINCIPAL}", out)
        self.assertNotIn(f"also held on the gateway by the principal {CASES_PRINCIPAL}", out)

    def test_what_else_the_gateway_holds_is_listed_and_does_not_fail_the_run(self):
        azure = Azure()
        azure.doc(f"{WORKSPACE}/modelProviders")["value"].append({"name": "second", "properties": {"kind": "OpenAI"}})
        azure.doc(f"{WORKSPACE}/modelProviders/foundry/models")["value"].append({"name": "extra-model", "properties": {}})
        azure.doc(f"{WORKSPACE}/aliases")["value"].append({"name": "extra.alias", "properties": {}})
        azure.doc(WORKSPACE)["properties"]["policies"].append({"type": "ipFilter", "action": "Allow", "cidrRanges": ["203.0.113.0/24"], "scope": "workspace"})
        code, out, _ = self.command(azure)
        self.assertEqual(code, 0, out)
        self.assertIn("note: The model providers of the gateway, by name: foundry, second", out)
        self.assertIn("note: The provider also holds the model extra-model", out)
        self.assertIn("note: The gateway also holds the alias extra.alias", out)
        self.assertIn("note: The workspace also holds a policy: ipFilter: a policy of this type is there (not managed here)", out)
        self.assertNotIn("203.0.113.0", out, "a range is not printed")

    def test_a_slow_az_stops_the_read_back_where_it_is_and_the_rest_is_not_asked(self):
        azure = Azure()
        azure.fail("get", f"{WORKSPACE}/aliases", prep.Stuck("az did not answer within 120 seconds (GET /x)"))
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("The aliases could not be read: az did not answer within 120 seconds (GET /x). The read-back stops here: nothing after it was read", out)
        asked = [call[1] for call in azure.calls]
        self.assertIn(f"{WORKSPACE}/aliases", asked)
        self.assertNotIn(KEYS, asked)
        self.assertNotIn(GATEWAY_ROLES, asked)

    def test_a_read_that_azure_refuses_or_cannot_answer_is_a_failure_that_says_so(self):
        for error, expected in (("ERROR: (AuthorizationFailed) no", "The role assignments at the gateway could not be read, Azure does not allow it"),
                                ("ERROR: (InternalServerError) later", "The role assignments at the gateway could not be read: ERROR: (InternalServerError) later")):
            azure = Azure()
            azure.fail("get", GATEWAY_ROLES, error)
            code, out, _ = self.command(azure)
            self.assertEqual(code, 1)
            self.assertIn(expected, out)

    def test_a_list_is_read_to_its_end_and_only_at_addresses_of_azure_resource_manager(self):
        azure = Azure()
        first = {"value": [azure.doc(f"{WORKSPACE}/aliases")["value"][0]], "nextLink": prep.ARM + "/page-two"}
        second = {"value": azure.doc(f"{WORKSPACE}/aliases")["value"][1:]}
        azure.documents[f"{WORKSPACE}/aliases".lower()] = first
        azure.documents["/page-two"] = second
        code, out, _ = self.command(azure)
        self.assertEqual(code, 0, out)
        self.assertIn("ok: The alias gpt-6.1-sol points to the model gpt-6-1-sol", out)
        self.assertIn("ok: The alias gpt-5.5 points to the model gpt-5-5", out)
        azure = Azure()
        azure.doc(f"{WORKSPACE}/aliases")["nextLink"] = "https://example.invalid/page-two"
        code, out, _ = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("goes on at an address that is not of Azure Resource Manager, and that is not followed", out)
        self.assertFalse(any("example.invalid" in call[2] for call in azure.calls), "the address was not asked")

    def test_nothing_that_an_answer_holds_is_printed_but_names_states_and_numbers(self):
        azure = Azure()
        azure.doc(GATEWAY_ID)["properties"]["publicNetworkAccess"] = "Enabled\nSECRET=" + SECRET
        azure.doc(GATEWAY_ID)["sku"] = {"name": "Standard", "secret": SECRET}
        provider = azure.doc(f"{WORKSPACE}/modelProviders")["value"][0]["properties"]
        provider["foundry"]["authentication"]["apiKey"] = SECRET
        provider["foundry"]["endpoint"] = f"https://{ACCOUNT}.cognitiveservices.azure.com/?key={SECRET}"
        azure.doc(WORKSPACE)["properties"]["policies"].append({"type": "cors", "allowedOrigins": [SECRET], "token": SECRET})
        azure.doc(f"{WORKSPACE}/modelProviders/foundry/models")["value"][0]["properties"]["description"] = SECRET
        code, out, err = self.command(azure)
        self.assertEqual(code, 0, out)
        self.assertNotIn(SECRET, out + err)
        self.assertIn("note: The service reports publicNetworkAccess an unexpected value.", out, "a state that is not one of the known words is not echoed")
        azure.doc(GATEWAY_ID)["properties"]["provisioningState"] = SECRET
        code, out, err = self.command(azure)
        self.assertEqual(code, 1)
        self.assertIn("The gateway is in the state an unexpected value and not Succeeded", out)
        self.assertNotIn(SECRET, out + err)

    def test_the_lines_go_to_the_summary_and_the_arguments_are_checked_before_azure_is_asked(self):
        azure = Azure()
        summary = Path(self.directory.name) / "summary.md"
        self.assertEqual(self.command(azure, summary=summary)[0], 0)
        self.assertIn("### The AI Gateway, read back from Azure", summary.read_text(encoding="utf-8"))
        azure = Azure()
        code, out, err = self.command(azure, "--project-principal", "not-an-object-id")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--project-principal is an object id", err)
        self.assertEqual(azure.calls, [])
        azure = Azure()
        code, out, err = self.command(azure, "--cases-principal", "not-an-object-id")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--cases-principal is an object id", err)
        self.assertNotIn("not-an-object-id", err)
        self.assertEqual(azure.calls, [])
        azure = Azure()
        code, out, err = run(["read-back", *ARGUMENTS, "--vnet", "../x", "--subnet", "snet-aigw", "--foundry-account", ACCOUNT, "--operator-identity", OPERATOR,
                              "--models", str(self.models), "--policies", str(self.policies)], azure)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--vnet is a resource name", err)
        self.assertEqual(azure.calls, [])

    def test_a_file_that_cannot_be_read_is_refused_before_azure_is_asked(self):
        self.models.write_text("[", encoding="utf-8")
        azure = Azure()
        code, out, err = self.command(azure)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("is not a readable JSON list of models", err)
        self.assertEqual(azure.calls, [])
        self.models.write_text(json.dumps(MODELS), encoding="utf-8")
        self.policies.write_text("[]", encoding="utf-8")
        code, out, err = self.command(azure)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("is not a list of policies of the types", err)
        self.assertEqual(azure.calls, [])


class TheTemplateAndTheToolAgree(unittest.TestCase):
    """The tool reads back what the template makes: the words that both name are the same, so a change of one is a failing test until the other follows."""

    TEMPLATE = (ROOT / "environment" / "aigateway" / "main.bicep").read_text(encoding="utf-8")
    SUBNET_TEMPLATE = (ROOT / "environment" / "aigateway" / "subnet.bicep").read_text(encoding="utf-8")

    def test_the_names_the_versions_and_the_roles_are_the_templates(self):
        self.assertEqual(set(re.findall(r"Microsoft\.ApiManagement/aigateways[^'@]*@([^']+)'", self.TEMPLATE)), {prep.API})
        self.assertIn(f"var providerName = '{prep.PROVIDER}'", self.TEMPLATE)
        self.assertIn(f"var contentSafetySeverity = '{prep.SEVERITY}'", self.TEMPLATE)
        self.assertIn(f"var foundryUserRoleId = '{prep.FOUNDRY_USER}'", self.TEMPLATE)
        self.assertIn(f"var aiGatewayModelsUserRoleId = '{prep.MODELS_USER}'", self.TEMPLATE)
        self.assertIn(f"serviceName: '{prep.SUBNET_DELEGATION}'", self.SUBNET_TEMPLATE, "the subnet is made, and delegated, by the template of the subnet: the gateway's template only names it")
        self.assertNotIn("serviceName:", self.TEMPLATE)
        for category in prep.CATEGORIES:
            self.assertIn(f"{category}: contentSafetySeverity", self.TEMPLATE)
        self.assertEqual(prep.AI_GATEWAY_ROLES[prep.MODELS_USER], "AI Gateway Models User")
        self.assertEqual(sorted(prep.AI_GATEWAY_ROLES.values()), ["AI Gateway Models User", "AI Gateway Tools User", "AI Gateway User"])

    def test_the_tool_uses_the_standard_library_alone_and_has_no_other_way_to_reach_azure_than_az_rest(self):
        source = (ROOT / "tools" / "aigateway-prep.py").read_text(encoding="utf-8")
        imports = set(re.findall(r"(?m)^(?:import|from) (\w+)", source))
        self.assertLessEqual(imports, {"argparse", "importlib", "json", "os", "re", "subprocess", "sys", "time", "pathlib", "typing", "__future__"}, "importlib loads tools/hubguard.py from the tool's own folder")
        self.assertEqual(re.findall(r'subprocess\.run\(\[([^\]]*)\]', source), ['os.environ.get("AZ", "az"), *arguments'])
        for word in ("urllib", "http.client", "socket", "listKeys", "listSecrets"):
            self.assertNotIn(word, source, word)
        self.assertEqual(source.count('"rest", "--method"'), 2, "one request that may write, and the read of the next page of a list")
        self.assertEqual(len(re.findall(r'(?m)^def (?:only_in_actions)', source)), 1)
        self.assertEqual(len(re.findall(r"\bonly_in_actions\(\)", source)), 3, "defined once and called by the two commands that write")


if __name__ == "__main__":
    unittest.main()
