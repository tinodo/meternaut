import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("access_requirements", ROOT / "tools" / "access-requirements.py")
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)

http_spec = importlib.util.spec_from_file_location("cases_http_for_access_test", ROOT / "src" / "case-functions" / "cases" / "http.py")
cases_http = importlib.util.module_from_spec(http_spec)
sys.modules["cases_http_for_access_test"] = cases_http
http_spec.loader.exec_module(cases_http)

PROJECT = "11111111-2222-3333-4444-555555555555"
SECOND = "99999999-8888-7777-6666-555555555555"
GATEWAY_SUB = "66666666-7777-8888-9999-000000000000"
WORKSPACE_SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
APIM = f"/subscriptions/{GATEWAY_SUB}/resourceGroups/rg-gateway/providers/Microsoft.ApiManagement/service/example-apim"
GATEWAY_GROUP = f"/subscriptions/{GATEWAY_SUB}/resourceGroups/rg-gateway"
INSIGHTS = f"/subscriptions/{GATEWAY_SUB}/resourceGroups/rg-gateway/providers/microsoft.insights/components/example-insights"
WORKSPACE_GROUP = f"/subscriptions/{WORKSPACE_SUB}/resourceGroups/rg-central"
WORKSPACE = f"{WORKSPACE_GROUP}/providers/Microsoft.OperationalInsights/workspaces/example-workspace"
PROJECT_GROUP = f"/subscriptions/{PROJECT}/resourceGroups/rg-project"
PRODUCT = f"{APIM}/subscriptions/meternaut-agents-sub-01"
ESTATE = f"/subscriptions/{PROJECT}"
MANAGEMENT_GROUP = "/providers/Microsoft.Management/managementGroups/landing-zones"
PLACES = ["--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway", APIM, "--gateway-insights", INSIGHTS]
KEY_READER_ID = "00000000-0000-0000-0000-0000000000a1"
USAGE_READER_ID = "00000000-0000-0000-0000-0000000000a2"
WASTE_REMOVER_ID = "00000000-0000-0000-0000-0000000000a3"
WRITER = "Meternaut waste remover"

MANIFEST = ar.load_manifest()
BUILTIN = {name: spec["id"] for name, spec in MANIFEST["roles"].items() if spec["kind"] == "builtin"}


def definition(name, role_id, group, **changes):
    spec = MANIFEST["roles"][name]
    value = {"name": role_id, "roleName": name, "assignableScopes": [group],
             "permissions": [{"actions": list(spec["actions"]), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


class FakeAz:
    """Answers the Azure CLI commands of the tool from a small model of a tenant, and remembers every command."""

    def __init__(self, granted=True):
        self.identities = {"id-meternaut-cases": "case-principal", "id-meternaut-usage": "usage-principal", "id-meternaut-runner": "runner-principal"}
        self.roles = {}
        self.assignments = []
        self.calls = []
        self.definition_files = []
        self.user = "operator@example.com"
        self.assign_errors = []
        if granted:
            self.roles["Meternaut gateway key reader"] = definition("Meternaut gateway key reader", KEY_READER_ID, GATEWAY_GROUP)
            self.roles["Meternaut usage reader"] = definition("Meternaut usage reader", USAGE_READER_ID, WORKSPACE_GROUP)
            self.roles[WRITER] = definition(WRITER, WASTE_REMOVER_ID, PROJECT_GROUP)
            self.grant("case-principal", BUILTIN["Reader"], ESTATE)
            self.grant("case-principal", BUILTIN["Cost Management Reader"], ESTATE)
            self.grant("case-principal", KEY_READER_ID, PRODUCT)
            self.grant("usage-principal", BUILTIN["Monitoring Reader"], INSIGHTS)
            self.grant("usage-principal", USAGE_READER_ID, WORKSPACE)
            self.grant("runner-principal", WASTE_REMOVER_ID, PROJECT_GROUP)

    def grant(self, principal, role_id, scope):
        self.assignments.append({"principal": principal, "role_id": role_id, "scope": scope})

    def writes(self):
        return [c for c in self.calls if c[:3] in (["role", "assignment", "create"], ["role", "definition", "create"])]

    def __call__(self, args):
        self.calls.append(list(args))
        a = list(args)
        option = lambda name: a[a.index(name) + 1]  # noqa: E731
        if a[:2] == ["account", "show"]:
            return 0, self.user + "\n", ""
        if a[:2] == ["identity", "show"]:
            name = option("--name")
            if name in self.identities:
                return 0, self.identities[name] + "\n", ""
            return 3, "", f"ERROR: (ResourceNotFound) The Resource 'Microsoft.ManagedIdentity/userAssignedIdentities/{name}' was not found."
        if a[:3] == ["role", "definition", "list"]:
            sub = option("--subscription")
            found = [d for d in self.roles.values() if d["roleName"] == option("--name") and any(s.lower().startswith(f"/subscriptions/{sub}/".lower()) for s in d["assignableScopes"])]
            return 0, json.dumps(found), ""
        if a[:3] == ["role", "definition", "create"]:
            path = option("--role-definition")
            content = json.loads(Path(path).read_text(encoding="utf-8"))
            self.definition_files.append((path, content))
            role_id = f"00000000-0000-0000-0000-00000000b{len(self.roles) + 1:03d}"
            self.roles[content["Name"]] = {"name": role_id, "roleName": content["Name"], "assignableScopes": content["AssignableScopes"],
                                           "permissions": [{"actions": content["Actions"], "notActions": content["NotActions"], "dataActions": content["DataActions"],
                                                            "notDataActions": content["NotDataActions"]}]}
            return 0, json.dumps(self.roles[content["Name"]]), ""
        if a[:3] == ["role", "assignment", "create"]:
            if self.assign_errors:
                return 1, "", self.assign_errors.pop(0)
            principal, role, scope = option("--assignee-object-id"), option("--role"), option("--scope")
            if any(x["principal"] == principal and x["role_id"] == role and x["scope"] == scope for x in self.assignments):
                return 1, "", "ERROR: (RoleAssignmentExists) The role assignment already exists."
            self.grant(principal, role, scope)
            return 0, json.dumps({"name": f"assignment-{len(self.assignments)}"}), ""
        if a[0] == "rest":
            url = option("--url")
            if "/roleAssignments?" in url:
                scope = url[len(ar.ARM):url.index("/providers/Microsoft.Authorization/roleAssignments")]
                principal = re.search(r"principalId eq '([^']+)'", url).group(1)
                value = []
                for x in self.assignments:
                    here, there = scope.lower(), x["scope"].lower()
                    if x["principal"] == principal and (there.startswith(here) or here.startswith(there + "/") or there.startswith(ar.MANAGEMENT_PREFIX)):
                        value.append({"properties": {"roleDefinitionId": f"/providers/Microsoft.Authorization/roleDefinitions/{x['role_id']}", "scope": x["scope"],
                                                     "principalId": principal}})
                return 0, json.dumps({"value": value}), ""
            if url.startswith(f"{ar.ARM}{INSIGHTS}?"):
                return 0, json.dumps({"properties": {"WorkspaceResourceId": WORKSPACE}}), ""
        return 1, "", f"unexpected command {a[:3]}"


def run(argv, fake, env=None, answers=("yes",), asked=None):
    lines, errors, sleeps = [], io.StringIO(), []
    answers = list(answers)

    def ask(prompt):
        if asked is not None:
            asked.append(prompt)
        return answers.pop(0) if answers else None

    with contextlib.redirect_stderr(errors):
        code = ar.main(argv, az=ar.Az(fake), env={} if env is None else env, out=lines.append, sleep=sleeps.append, ask=ask)
    return code, "\n".join(lines), errors.getvalue(), sleeps


class TheFile(unittest.TestCase):
    WRITER_ACTIONS = ["Microsoft.Compute/disks/delete", "Microsoft.Network/publicIPAddresses/delete"]

    def test_it_loads_and_every_reference_resolves(self):
        self.assertEqual([g["id"] for g in MANIFEST["grants"]], ["R1", "R2", "R3", "R4", "R5", "W1"])
        for grant in MANIFEST["grants"]:
            self.assertIn(grant["identity"], MANIFEST["identities"])
            self.assertIn(grant["place"], MANIFEST["places"])
            self.assertIn(grant["role"], MANIFEST["roles"])

    def test_the_built_in_roles_are_the_ones_that_azure_has_and_all_of_them_only_read(self):
        self.assertEqual(BUILTIN, {"Reader": "acdd72a7-3385-48ef-bd42-f606fba81ae7", "Cost Management Reader": "72fafb9e-0641-4937-9268-a91bfd8191a3",
                                   "Monitoring Reader": "43d0d8ad-25c7-4714-9337-8ba259a9fe05"})

    def test_a_custom_role_can_only_read_except_the_one_writer_and_the_one_key_read_has_a_name_that_a_test_knows(self):
        for name, spec in MANIFEST["roles"].items():
            if spec["kind"] != "custom":
                continue
            for action in spec["actions"]:
                self.assertNotIn("*", action, name)
                if spec.get("writes"):
                    self.assertTrue(action.endswith("/read") or action in self.WRITER_ACTIONS, f"{name}: {action}")
                else:
                    self.assertTrue(action.endswith("/read") or action == "Microsoft.ApiManagement/service/subscriptions/listSecrets/action", f"{name}: {action}")
            if not spec.get("writes"):
                self.assertFalse(any(re.search(r"write|delete", a, re.I) for a in spec["actions"]), name)

    def test_one_custom_role_changes_azure_it_only_deletes_two_kinds_of_resource_and_is_held_by_one_identity_in_one_group(self):
        writers = [name for name, spec in MANIFEST["roles"].items() if spec.get("writes")]
        self.assertEqual(writers, [WRITER], "another role that changes Azure is a decision for a person, and for this test")
        spec = MANIFEST["roles"][WRITER]
        self.assertEqual(sorted(a for a in spec["actions"] if not a.endswith("/read")), sorted(self.WRITER_ACTIONS))
        self.assertEqual(spec["definedIn"], "projectGroup")
        held = [(g["id"], g["identity"], g["place"]) for g in MANIFEST["grants"] if g["role"] == WRITER]
        self.assertEqual(held, [("W1", "runner", "projectGroup")])
        self.assertEqual(MANIFEST["identities"]["runner"], {"name": "id-meternaut-runner", "madeBy": "cases"})
        for grant in MANIFEST["grants"]:
            if grant["identity"] == "runner":
                self.assertEqual(grant["role"], WRITER, "the writer's identity holds its one role and no other")

    def test_a_role_that_changes_azure_can_only_be_defined_in_the_project_group(self):
        broken = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8"))
        broken["roles"][WRITER]["definedIn"] = "workspaceGroup"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ar.Problem) as raised:
                ar.load_manifest(path)
            self.assertIn("project's own group", str(raised.exception))

    def test_the_hand_steps_page_has_every_custom_role_and_every_action_of_it(self):
        text = (ROOT / "environment" / "BOOTSTRAP.md").read_text(encoding="utf-8")
        for name, spec in MANIFEST["roles"].items():
            self.assertIn(name, text)
            if spec["kind"] == "custom":
                for action in spec["actions"]:
                    self.assertIn(action, text, f"{name}: {action} is in the file but not on the hand steps page")

    def test_a_file_with_a_missing_reference_is_refused(self):
        broken = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8"))
        broken["grants"][0]["role"] = "Owner"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ar.Problem):
                ar.load_manifest(path)


class TheTable(unittest.TestCase):
    def test_one_row_for_each_requirement(self):
        rows = ar.markdown(MANIFEST).splitlines()
        self.assertEqual(len(rows), 2 + len(MANIFEST["grants"]))
        self.assertTrue(rows[0].startswith("| # | Identity | Role | Where | What it is for |"))
        self.assertIn("Meternaut gateway key reader (custom role)", rows[4])

    def test_the_proposal_shows_exactly_this_table(self):
        text = (ROOT / "docs" / "proposals" / "03-access-and-onboarding.md").read_text(encoding="utf-8")
        match = re.search(r"<!-- access-requirements:start -->\n(.*?)\n<!-- access-requirements:end -->", text, re.S)
        self.assertIsNotNone(match, "the proposal has no marked table")
        self.assertEqual(match.group(1), ar.markdown(MANIFEST), "run: python tools/access-requirements.py markdown, and paste it between the markers")

    def test_the_command_prints_it(self):
        code, out, _, _ = run(["markdown"], FakeAz())
        self.assertEqual((code, out), (0, ar.markdown(MANIFEST)))

    def test_the_role_that_changes_azure_is_marked_in_the_table(self):
        rows = [r for r in ar.markdown(MANIFEST).splitlines() if r.startswith("| W1 ")]
        self.assertEqual(len(rows), 1)
        self.assertIn(f"{WRITER} (custom role, changes Azure)", rows[0])
        self.assertEqual(sum("changes Azure" in r for r in ar.markdown(MANIFEST).splitlines()), 1)


class TheCallsOfTheApp(unittest.TestCase):
    NAMES = {
        "resource-graph-query": lambda m, p: m == "POST" and "ResourceGraph" in p,
        "cost-management-query": lambda m, p: m == "POST" and "CostManagement" in p,
        "advisor-read": lambda m, p: m == "GET" and "Advisor" in p,
        "locks-read": lambda m, p: m == "GET" and "Authorization" in p and "locks" in p,
        "gateway-key-read": lambda m, p: m == "POST" and "listSecrets" in p,
        "gateway-chat": lambda m, p: m == "POST" and "chat/completions" in p,
    }
    NO_AZURE_ROLE = {"gateway-chat"}

    def test_every_call_that_the_app_may_make_is_a_requirement_or_needs_no_azure_role(self):
        allowed = cases_http.allowed_calls("example-apim.azure-api.net", f"{PRODUCT}/listSecrets")
        names = []
        for method, pattern in allowed:
            found = [n for n, test in self.NAMES.items() if test(method, pattern.pattern)]
            self.assertEqual(len(found), 1, f"{method} {pattern.pattern}: the app makes a call that the access requirements do not know. Add it to environment/access-requirements.json")
            names.append(found[0])
        listed = {c for g in MANIFEST["grants"] for c in g.get("calls", [])}
        self.assertEqual(sorted(set(names) - self.NO_AZURE_ROLE), sorted(listed), "the calls of the app and the calls in the requirements differ")
        self.assertEqual(len(names), len(set(names)))

    def test_only_the_cases_identity_has_calls_listed(self):
        for grant in MANIFEST["grants"]:
            self.assertEqual(bool(grant.get("calls")), grant["identity"] == "cases", grant["id"])


class TheCallsOfTheRunner(unittest.TestCase):
    ACTIONS = (
        (lambda m, p: m == "GET" and "Microsoft.Compute/disks/" in p, "Microsoft.Compute/disks/read"),
        (lambda m, p: m == "DELETE" and "Microsoft.Compute/disks/" in p, "Microsoft.Compute/disks/delete"),
        (lambda m, p: m == "GET" and "Microsoft.Network/publicIPAddresses/" in p, "Microsoft.Network/publicIPAddresses/read"),
        (lambda m, p: m == "DELETE" and "Microsoft.Network/publicIPAddresses/" in p, "Microsoft.Network/publicIPAddresses/delete"),
        (lambda m, p: m == "GET" and "Microsoft.Authorization/locks" in p, "Microsoft.Authorization/locks/read"),
    )

    def test_the_calls_that_the_runner_may_make_and_the_actions_of_its_role_are_the_same_list(self):
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import runner
        finally:
            sys.path.remove(app)
        wanted = []
        for method, pattern in runner.runner_calls(PROJECT, "rg-project"):
            text = pattern.pattern.replace("\\", "")
            found = [action for test, action in self.ACTIONS if test(method, text)]
            self.assertEqual(len(found), 1, f"{method} {text}: the runner makes a call that the access requirements do not know. Add it to environment/access-requirements.json")
            wanted.append(found[0])
        self.assertEqual(len(wanted), len(set(wanted)))
        self.assertEqual(sorted(wanted), sorted(MANIFEST["roles"][WRITER]["actions"]), "the calls of the runner and the actions of its role differ")


class Check(unittest.TestCase):
    def test_everything_granted_is_present_and_nothing_is_written(self):
        fake = FakeAz()
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual(code, 0)
        self.assertIn("6 of 6 present.", out)
        self.assertIn("signed in as operator@example.com", out)
        self.assertEqual(fake.writes(), [])

    def test_a_second_subscription_that_has_no_grant_is_missing(self):
        code, out, _, _ = run(["check", *PLACES, "--estate", ESTATE, "--estate", f"/subscriptions/{SECOND}", "--only", "R1,R2"], FakeAz())
        self.assertEqual(code, 1)
        self.assertEqual(len(re.findall(r"MISSING", out)), 2)
        self.assertIn(f"Reader  at /subscriptions/{SECOND}", out)
        self.assertIn("2 of 4 present.", out)

    def test_a_grant_at_a_management_group_counts_for_the_subscriptions_below_it(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if a["scope"] != ESTATE]
        fake.grant("case-principal", BUILTIN["Reader"], MANAGEMENT_GROUP)
        fake.grant("case-principal", BUILTIN["Cost Management Reader"], MANAGEMENT_GROUP)
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual((code, "6 of 6 present." in out), (0, True))

    def test_a_grant_on_something_below_the_place_does_not_count(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if not (a["scope"] == ESTATE and a["role_id"] == BUILTIN["Reader"])]
        fake.grant("case-principal", BUILTIN["Reader"], f"{ESTATE}/resourceGroups/rg-one")
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual((code, "MISSING" in out), (1, True))

    def test_a_grant_to_another_identity_does_not_count(self):
        fake = FakeAz()
        fake.assignments = [dict(a, principal="somebody-else") if a["scope"] == ESTATE else a for a in fake.assignments]
        code, out, _, _ = run(["check", *PLACES, "--only", "R1,R2"], fake)
        self.assertEqual((code, out.count("MISSING")), (1, 2))

    def test_a_custom_role_that_can_do_more_than_the_file_says_is_reported(self):
        fake = FakeAz()
        fake.roles["Meternaut gateway key reader"]["permissions"][0]["actions"].append("Microsoft.ApiManagement/service/write")
        code, out, _, _ = run(["check", *PLACES, "--only", "R3"], fake)
        self.assertEqual(code, 1)
        self.assertIn("role differs", out)
        self.assertIn("Microsoft.ApiManagement/service/write", out)

    def test_a_custom_role_that_can_be_assigned_in_more_places_than_the_file_says_is_reported(self):
        fake = FakeAz()
        fake.roles["Meternaut gateway key reader"]["assignableScopes"].append(f"/subscriptions/{GATEWAY_SUB}")
        code, out, _, _ = run(["check", *PLACES, "--only", "R3"], fake)
        self.assertEqual((code, "role differs" in out), (1, True))

    def test_a_custom_role_that_does_not_exist_is_missing(self):
        fake = FakeAz()
        del fake.roles["Meternaut gateway key reader"]
        code, out, _, _ = run(["check", *PLACES, "--only", "R3"], fake)
        self.assertEqual(code, 1)
        self.assertIn("MISSING", out)
        self.assertIn("the custom role does not exist yet", out)

    def test_an_identity_that_does_not_exist_yet_says_which_action_makes_it(self):
        fake = FakeAz()
        del fake.identities["id-meternaut-cases"]
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual(code, 1)
        self.assertIn("cannot yet", out)
        self.assertIn("the Hub action cases makes it", out)

    def test_an_identity_that_cannot_be_read_stops_the_check_with_the_reason(self):
        fake = FakeAz()

        def denied(args):
            if list(args)[:2] == ["identity", "show"]:
                return 1, "", "ERROR: (AuthorizationFailed) The client does not have authorization to perform action"
            return fake(args)

        code, out, err, _ = run(["check", *PLACES, "--only", "R1"], denied)
        self.assertEqual(code, 1)
        self.assertIn("could not be read", err)

    def test_the_workspace_is_read_from_the_gateways_component_when_it_is_not_given(self):
        fake = FakeAz()
        run(["check", *PLACES, "--only", "R5"], fake)
        self.assertTrue(any(c[0] == "rest" and f"{INSIGHTS}?api-version={ar.INSIGHTS_API}" in c[c.index("--url") + 1] for c in fake.calls))
        fake = FakeAz()
        run(["check", *PLACES, "--workspace", WORKSPACE, "--only", "R5"], fake)
        self.assertFalse(any(c[0] == "rest" and INSIGHTS in c[c.index("--url") + 1] and "roleAssignments" not in c[c.index("--url") + 1] for c in fake.calls))

    def test_the_settings_of_the_workflow_are_read_from_the_environment(self):
        env = {"ENV_SUBSCRIPTION_ID": PROJECT, "ENV_RESOURCE_GROUP": "rg-project", "GATEWAY_RESOURCE_ID": APIM, "GATEWAY_APPINSIGHTS_ID": INSIGHTS,
               "ACCESS_ESTATE_SCOPES": f"{ESTATE}, /subscriptions/{SECOND}"}
        code, out, _, _ = run(["check", "--only", "R1"], FakeAz(), env=env)
        self.assertEqual((code, "1 of 2 present." in out), (1, True))

    def test_without_an_estate_the_project_subscription_is_the_estate(self):
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], FakeAz())
        self.assertIn(f"at {ESTATE}", out)

    def test_a_missing_or_wrong_place_is_named(self):
        for argv, word in ((["check", "--project-subscription", PROJECT, "--project-group", "rg-project", "--only", "R3"], "--gateway"),
                           (["check", "--only", "R1"], "--project-subscription"),
                           (["check", *PLACES, "--estate", "not-a-scope"], "--estate"),
                           (["check", *PLACES, "--gateway", "/subscriptions/x"], "--gateway"),
                           (["check", *PLACES, "--only", "R9"], "R9")):
            code, _, err, _ = run(argv, FakeAz())
            self.assertEqual(code, 1, argv)
            self.assertIn(word, err)

    def test_the_azure_command_is_az_or_the_variable(self):
        with mock.patch.dict(os.environ, {"AZ": ""}, clear=False), mock.patch("shutil.which", return_value="/usr/bin/az"):
            self.assertEqual(ar.az_command(), ["/usr/bin/az"])
        with mock.patch.dict(os.environ, {"AZ": '"/opt/az dir/python" -IBm azure.cli'}, clear=False):
            self.assertEqual(ar.az_command(), ["/opt/az dir/python", "-IBm", "azure.cli"])


class Grant(unittest.TestCase):
    EMPTY = dict(granted=False)

    def test_a_dry_run_says_what_it_would_do_and_does_nothing(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES], fake)
        self.assertEqual(code, 0)
        self.assertIn("This was a dry run", out)
        self.assertIn("9 change(s) would be made, and nothing else", out)
        self.assertEqual(fake.writes(), [])
        self.assertIn("az role assignment create --assignee-object-id case-principal", out)
        self.assertIn("az role assignment create --assignee-object-id runner-principal", out)

    def test_apply_makes_the_missing_custom_roles_first_and_then_every_assignment_and_checks_again(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        writes = fake.writes()
        kinds = [c[:3] for c in writes]
        self.assertEqual(kinds.count(["role", "definition", "create"]), 3)
        self.assertEqual(kinds.count(["role", "assignment", "create"]), 6)
        custom_ids = {r["name"] for r in fake.roles.values()}
        for name in ("Meternaut gateway key reader", "Meternaut usage reader", WRITER):
            role_id = fake.roles[name]["name"]
            define = next(i for i, c in enumerate(writes) if c[:3] == ["role", "definition", "create"] and name in str(fake.definition_files))
            assign = next(i for i, c in enumerate(writes) if c[:3] == ["role", "assignment", "create"] and c[c.index("--role") + 1] == role_id)
            self.assertLess(define, assign, "a custom role is made before it is assigned")
        self.assertEqual(len(custom_ids), 3)
        self.assertTrue(out.rstrip().endswith("6 of 6 present."))
        self.assertIn("Checking again:", out)

    def test_the_writer_role_is_made_in_the_project_group_and_given_to_the_runner_there_only(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes", "--only", "W1"], fake)
        self.assertEqual(code, 0, out)
        ((path, content),) = fake.definition_files
        spec = MANIFEST["roles"][WRITER]
        self.assertEqual(content, {"Name": WRITER, "IsCustom": True, "Description": spec["description"], "Actions": spec["actions"],
                                   "NotActions": [], "DataActions": [], "NotDataActions": [], "AssignableScopes": [PROJECT_GROUP]})
        define = [c for c in fake.writes() if c[:3] == ["role", "definition", "create"]][0]
        self.assertEqual(define[define.index("--subscription") + 1], PROJECT)
        assigns = [c for c in fake.writes() if c[:3] == ["role", "assignment", "create"]]
        self.assertEqual(len(assigns), 1)
        assign = assigns[0]
        self.assertEqual((assign[assign.index("--assignee-object-id") + 1], assign[assign.index("--scope") + 1]), ("runner-principal", PROJECT_GROUP))
        self.assertTrue(out.rstrip().endswith("1 of 1 present."))

    def test_the_definition_that_is_made_holds_exactly_what_the_file_says_and_the_file_is_removed_after(self):
        fake = FakeAz(**self.EMPTY)
        run(["grant", *PLACES, "--apply", "--yes", "--only", "R3"], fake)
        ((path, content),) = fake.definition_files
        spec = MANIFEST["roles"]["Meternaut gateway key reader"]
        self.assertEqual(content, {"Name": "Meternaut gateway key reader", "IsCustom": True, "Description": spec["description"], "Actions": spec["actions"],
                                   "NotActions": [], "DataActions": [], "NotDataActions": [], "AssignableScopes": [GATEWAY_GROUP]})
        self.assertFalse(os.path.exists(path))
        define = [c for c in fake.writes() if c[:3] == ["role", "definition", "create"]][0]
        self.assertEqual(define[define.index("--subscription") + 1], GATEWAY_SUB)

    def test_every_role_that_is_assigned_is_one_of_the_file(self):
        fake = FakeAz(**self.EMPTY)
        run(["grant", *PLACES, "--apply", "--yes"], fake)
        known = set(BUILTIN.values()) | {r["name"] for r in fake.roles.values()}
        for call in fake.writes():
            if call[:3] == ["role", "assignment", "create"]:
                self.assertIn(call[call.index("--role") + 1], known)
                self.assertEqual(call[call.index("--assignee-principal-type") + 1], "ServicePrincipal")

    def test_a_second_apply_has_nothing_to_do(self):
        fake = FakeAz(**self.EMPTY)
        run(["grant", *PLACES, "--apply", "--yes"], fake)
        before = len(fake.writes())
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual((code, len(fake.writes()), "Nothing to grant." in out), (0, before, True))

    def test_only_what_is_missing_is_made(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if not (a["scope"] == ESTATE and a["role_id"] == BUILTIN["Reader"])]
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "create"]])
        write = fake.writes()[0]
        self.assertEqual((write[write.index("--role") + 1], write[write.index("--scope") + 1]), (BUILTIN["Reader"], ESTATE))

    def test_a_second_estate_gets_its_two_roles(self):
        fake = FakeAz()
        code, out, _, _ = run(["grant", *PLACES, "--estate", ESTATE, "--estate", f"/subscriptions/{SECOND}", "--only", "R1,R2", "--apply", "--yes"], fake)
        self.assertEqual(code, 0)
        scopes = [(c[c.index("--role") + 1], c[c.index("--scope") + 1]) for c in fake.writes()]
        self.assertEqual(sorted(scopes), sorted([(BUILTIN["Reader"], f"/subscriptions/{SECOND}"), (BUILTIN["Cost Management Reader"], f"/subscriptions/{SECOND}")]))

    def test_a_custom_role_that_differs_is_never_changed(self):
        fake = FakeAz()
        fake.roles["Meternaut gateway key reader"]["permissions"][0]["actions"].append("Microsoft.ApiManagement/service/write")
        fake.assignments = [a for a in fake.assignments if a["scope"] != PRODUCT]
        code, out, _, _ = run(["grant", *PLACES, "--only", "R3", "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertEqual(fake.writes(), [])
        self.assertIn("Nothing can be granted until", out)
        self.assertIn("role differs", out)

    def test_an_identity_that_does_not_exist_yet_blocks_its_grants_only(self):
        fake = FakeAz(**self.EMPTY)
        del fake.identities["id-meternaut-usage"]
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("cannot yet", out)
        assigned = [c for c in fake.writes() if c[:3] == ["role", "assignment", "create"]]
        self.assertEqual(len(assigned), 4)
        self.assertTrue(all(c[c.index("--assignee-object-id") + 1] in ("case-principal", "runner-principal") for c in assigned))

    def test_a_pipeline_may_not_apply_but_a_dry_run_is_allowed(self):
        fake = FakeAz(**self.EMPTY)
        code, _, err, _ = run(["grant", *PLACES, "--apply", "--yes"], fake, env={})
        self.assertEqual(code, 0, "outside a pipeline it applies")
        fake = FakeAz(**self.EMPTY)
        code, _, err, _ = run(["grant", *PLACES, "--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 1)
        self.assertIn("never a pipeline", err)
        self.assertEqual(fake.calls, [], "it refused before it read or wrote anything")
        code, out, _, _ = run(["grant", *PLACES], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])

    def test_it_asks_first_unless_it_is_told_not_to(self):
        fake, asked = FakeAz(**self.EMPTY), []
        code, out, _, _ = run(["grant", *PLACES, "--apply"], fake, answers=("yes",), asked=asked)
        self.assertEqual(code, 0)
        self.assertIn("operator@example.com", asked[0])
        fake = FakeAz(**self.EMPTY)
        code, _, err, _ = run(["grant", *PLACES, "--apply"], fake, answers=("no",))
        self.assertEqual((code, fake.writes()), (1, []))
        self.assertIn("nothing was changed", err)
        fake = FakeAz(**self.EMPTY)
        code, _, err, _ = run(["grant", *PLACES, "--apply"], fake, answers=())
        self.assertEqual((code, fake.writes()), (1, []))
        self.assertIn("needs --yes", err)

    def test_an_assignment_that_is_there_already_is_not_an_error(self):
        fake = FakeAz(**self.EMPTY)
        fake.assign_errors = ["ERROR: (RoleAssignmentExists) The role assignment already exists."]
        code, out, _, _ = run(["grant", *PLACES, "--only", "R1", "--apply", "--yes"], fake)
        self.assertIn("was there already", out)

    def test_a_role_that_azure_does_not_know_yet_is_tried_again_after_a_pause(self):
        fake = FakeAz(**self.EMPTY)
        fake.assign_errors = ["ERROR: (RoleDefinitionDoesNotExist) The specified role definition with ID does not exist."] * 2
        code, out, _, sleeps = run(["grant", *PLACES, "--only", "R3", "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(sleeps, [15, 15])

    def test_any_other_failure_stops_at_once_and_says_which_step(self):
        fake = FakeAz(**self.EMPTY)
        fake.assign_errors = ["ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Authorization/roleAssignments/write'"]
        code, out, err, _ = run(["grant", *PLACES, "--only", "R1,R2", "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("Reader at", err)
        self.assertEqual(len([c for c in fake.calls if c[:3] == ["role", "assignment", "create"]]), 1, "it did not go on to the next")


if __name__ == "__main__":
    unittest.main()
