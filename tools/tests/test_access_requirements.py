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
# What the first version of the console left behind: the file no longer has this role, so the test makes it the way that version did.
RETIRED_ROLE = "Meternaut waste remover"
RETIRED_ROLE_ID = "00000000-0000-0000-0000-0000000000a3"
RETIRED_IDENTITY = "id-meternaut-runner"
RETIRED_ACTIONS = ["Microsoft.Compute/disks/read", "Microsoft.Compute/disks/delete", "Microsoft.Network/publicIPAddresses/read",
                   "Microsoft.Network/publicIPAddresses/delete", "Microsoft.Authorization/locks/read"]
KEY_ACTION = "Microsoft.ApiManagement/service/subscriptions/listSecrets/action"

MANIFEST = ar.load_manifest()
BUILTIN = {name: spec["id"] for name, spec in MANIFEST["roles"].items() if spec["kind"] == "builtin"}


def definition(name, role_id, group, **changes):
    spec = MANIFEST["roles"][name]
    value = {"name": role_id, "roleName": name, "assignableScopes": [group],
             "permissions": [{"actions": list(spec["actions"]), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


def retired_definition(**changes):
    value = {"name": RETIRED_ROLE_ID, "roleName": RETIRED_ROLE, "assignableScopes": [PROJECT_GROUP],
             "permissions": [{"actions": list(RETIRED_ACTIONS), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


class FakeAz:
    """Answers the Azure CLI commands of the tool from a small model of a tenant, and remembers every command."""

    def __init__(self, granted=True):
        self.identities = {"id-meternaut-cases": "case-principal", "id-meternaut-usage": "usage-principal"}
        self.roles = {}
        self.assignments = []
        self.calls = []
        self.definition_files = []
        self.user = "operator@example.com"
        self.assign_errors = []
        self.unassign_errors = []
        self.definition_errors = []
        self.stubborn = set()
        self.vanish = set()
        self.page_size = None
        self.counter = 0
        if granted:
            self.roles["Meternaut gateway key reader"] = definition("Meternaut gateway key reader", KEY_READER_ID, GATEWAY_GROUP)
            self.roles["Meternaut usage reader"] = definition("Meternaut usage reader", USAGE_READER_ID, WORKSPACE_GROUP)
            self.grant("case-principal", BUILTIN["Reader"], ESTATE)
            self.grant("case-principal", BUILTIN["Cost Management Reader"], ESTATE)
            self.grant("case-principal", KEY_READER_ID, PRODUCT)
            self.grant("usage-principal", BUILTIN["Monitoring Reader"], INSIGHTS)
            self.grant("usage-principal", USAGE_READER_ID, WORKSPACE)

    def grant(self, principal, role_id, scope):
        self.counter += 1
        self.assignments.append({"id": f"{scope}/providers/Microsoft.Authorization/roleAssignments/00000000-0000-4000-8000-{self.counter:012d}",
                                 "principal": principal, "role_id": role_id, "scope": scope})

    def leave_the_writer(self, identity=True, orphans=1, below=0):
        """What the first version of the console left: the writer's role, its assignment to the identity, the assignments of identities that were deleted
        since (Azure keeps them) and, optionally, assignments on resources in the group."""
        self.roles[RETIRED_ROLE] = retired_definition()
        if identity:
            self.identities[RETIRED_IDENTITY] = "runner-principal"
            self.grant("runner-principal", RETIRED_ROLE_ID, PROJECT_GROUP)
        for n in range(orphans):
            self.grant(f"deleted-principal-{n + 1}", RETIRED_ROLE_ID, PROJECT_GROUP)
        for n in range(below):
            self.grant("runner-principal", RETIRED_ROLE_ID, f"{PROJECT_GROUP}/providers/Microsoft.Compute/disks/planted-disk-{n + 1}")
        return self

    def writes(self):
        return [c for c in self.calls if c[:3] in (["role", "assignment", "create"], ["role", "definition", "create"], ["role", "assignment", "delete"],
                                                   ["role", "definition", "delete"])]

    def of_the_role(self, role_id=RETIRED_ROLE_ID):
        return [x for x in self.assignments if x["role_id"] == role_id]

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
        if a[:3] == ["role", "assignment", "delete"]:
            if self.unassign_errors:
                return 1, "", self.unassign_errors.pop(0)
            target = option("--ids")
            found = [x for x in self.assignments if x["id"] == target]
            if not found:
                return 1, "", f"ERROR: (ResourceNotFound) The role assignment '{target}' could not be found."
            if target in self.vanish:
                self.assignments = [x for x in self.assignments if x["id"] != target]
                return 1, "", f"ERROR: (ResourceNotFound) The role assignment '{target}' could not be found."
            if target not in self.stubborn:
                self.assignments.remove(found[0])
            return 0, "", ""
        if a[:3] == ["role", "definition", "delete"]:
            if self.definition_errors:
                return 1, "", self.definition_errors.pop(0)
            role_id = option("--name")
            if self.of_the_role(role_id):
                return 1, "", "ERROR: (RoleDefinitionHasAssignments) There are existing role assignments referencing role (code: RoleDefinitionHasAssignments)"
            name = next((n for n, d in self.roles.items() if d["name"] == role_id), None)
            if name is None:
                return 1, "", f"ERROR: (RoleDefinitionDoesNotExist) The specified role definition with ID '{role_id}' does not exist."
            del self.roles[name]
            return 0, "", ""
        if a[0] == "rest":
            url = option("--url")
            if "/roleAssignments?" in url:
                scope = url[len(ar.ARM):url.index("/providers/Microsoft.Authorization/roleAssignments")]
                filtered = re.search(r"principalId eq '([^']+)'", url)
                value = []
                for x in self.assignments:
                    here, there = scope.lower(), x["scope"].lower()
                    near = there.startswith(here) or here.startswith(there + "/") or there.startswith(ar.MANAGEMENT_PREFIX)
                    if near and (not filtered or x["principal"] == filtered.group(1)):
                        value.append({"id": x["id"], "properties": {"roleDefinitionId": f"/providers/Microsoft.Authorization/roleDefinitions/{x['role_id']}",
                                                                    "scope": x["scope"], "principalId": x["principal"]}})
                if self.page_size and not filtered:
                    start = int(re.search(r"skiptoken=(\d+)", url).group(1)) if "skiptoken=" in url else 0
                    document = {"value": value[start:start + self.page_size]}
                    if start + self.page_size < len(value):
                        document["nextLink"] = (f"{ar.ARM}{scope}/providers/Microsoft.Authorization/roleAssignments?api-version={ar.ASSIGNMENTS_API}"
                                                f"&skiptoken={start + self.page_size}")
                    return 0, json.dumps(document), ""
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
    def broken(self, change):
        """The file with one change, written to a place where the loader can read it; returns what the loader says."""
        document = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8"))
        change(document)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ar.Problem) as raised:
                ar.load_manifest(path)
        return str(raised.exception)

    def test_it_loads_and_every_reference_resolves(self):
        self.assertEqual([g["id"] for g in MANIFEST["grants"]], ["R1", "R2", "R3", "R4", "R5"])
        for grant in MANIFEST["grants"]:
            self.assertIn(grant["identity"], MANIFEST["identities"])
            self.assertIn(grant["place"], MANIFEST["places"])
            self.assertIn(grant["role"], MANIFEST["roles"])

    def test_the_built_in_roles_are_the_ones_that_azure_has_and_all_of_them_only_read(self):
        self.assertEqual(BUILTIN, {"Reader": "acdd72a7-3385-48ef-bd42-f606fba81ae7", "Cost Management Reader": "72fafb9e-0641-4937-9268-a91bfd8191a3",
                                   "Monitoring Reader": "43d0d8ad-25c7-4714-9337-8ba259a9fe05"})

    def test_meternaut_holds_no_write_right_every_custom_role_only_reads_and_the_one_key_read_has_a_name_that_a_test_knows(self):
        customs = [name for name, spec in MANIFEST["roles"].items() if spec["kind"] == "custom"]
        self.assertEqual(sorted(customs), ["Meternaut gateway key reader", "Meternaut usage reader"])
        for name in customs:
            for action in MANIFEST["roles"][name]["actions"]:
                self.assertNotIn("*", action, name)
                self.assertTrue(action.endswith("/read") or action == KEY_ACTION, f"{name}: {action}")
            self.assertFalse(any(re.search(r"write|delete", a, re.I) for a in MANIFEST["roles"][name]["actions"]), name)

    def test_nothing_in_the_file_says_that_a_role_changes_azure_and_no_identity_is_a_writer(self):
        text = (ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8")
        self.assertNotIn('"writes"', text)
        self.assertEqual(sorted(MANIFEST["identities"]), ["cases", "usage"])
        self.assertEqual(sorted(i["name"] for i in MANIFEST["identities"].values()), ["id-meternaut-cases", "id-meternaut-usage"])
        self.assertNotIn("runner", [g["identity"] for g in MANIFEST["grants"]])

    def test_a_role_that_is_marked_as_changing_azure_is_refused(self):
        said = self.broken(lambda d: d["roles"]["Meternaut usage reader"].update(writes=True))
        self.assertIn("holds no write right", said)

    def test_the_earlier_writer_is_retired_and_is_not_granted(self):
        self.assertEqual(MANIFEST["retired"], [{"id": "W1", "identity": {"name": RETIRED_IDENTITY}, "role": RETIRED_ROLE, "place": "projectGroup",
                                                "why": MANIFEST["retired"][0]["why"]}])
        self.assertTrue(MANIFEST["retired"][0]["why"])
        self.assertNotIn(RETIRED_ROLE, MANIFEST["roles"])
        self.assertNotIn(RETIRED_IDENTITY, [i["name"] for i in MANIFEST["identities"].values()])
        self.assertIn(MANIFEST["retired"][0]["place"], MANIFEST["places"])

    def test_a_retired_item_must_be_complete_and_must_not_be_a_current_grant(self):
        for change, word in (
            (lambda d: d["retired"][0].update(id="R1"), "R1"),
            (lambda d: d["retired"][0].update(role="Reader"), "not a role of the file"),
            (lambda d: d["retired"][0].update(identity={"name": "id-meternaut-cases"}), "not an identity of the file"),
            (lambda d: d["retired"][0].update(identity="id-meternaut-runner"), "an object with a name"),
            (lambda d: d["retired"][0].update(identity={}), "an object with a name"),
            (lambda d: d["retired"][0].update(place="nowhere"), "W1"),
            (lambda d: d["retired"][0].update(why=""), "W1"),
            (lambda d: d["retired"].append(dict(d["retired"][0])), "used once"),
            (lambda d: d.update(retired="W1"), "retired is a list"),
        ):
            self.assertIn(word, self.broken(change))

    def test_a_file_without_the_list_of_retired_items_is_fine_and_has_nothing_to_retire(self):
        document = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8"))
        del document["retired"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            plain = ar.load_manifest(path)
        self.assertEqual(ar.markdown_retired(plain).splitlines()[0], "| # | Identity | Role | Where | Why it is retired |")
        self.assertEqual(len(ar.markdown_retired(plain).splitlines()), 2)
        self.assertEqual(ar.selected_retired(plain, None), [])

    def test_the_hand_steps_page_has_every_custom_role_and_every_action_of_it(self):
        text = (ROOT / "environment" / "BOOTSTRAP.md").read_text(encoding="utf-8")
        for name, spec in MANIFEST["roles"].items():
            self.assertIn(name, text)
            if spec["kind"] == "custom":
                for action in spec["actions"]:
                    self.assertIn(action, text, f"{name}: {action} is in the file but not on the hand steps page")

    def test_a_file_with_a_missing_reference_is_refused(self):
        self.broken(lambda d: d["grants"][0].update(role="Owner"))


class TheTable(unittest.TestCase):
    PROPOSAL = (ROOT / "docs" / "proposals" / "03-access-and-onboarding.md")

    def test_one_row_for_each_requirement(self):
        rows = ar.markdown(MANIFEST).splitlines()
        self.assertEqual(len(rows), 2 + len(MANIFEST["grants"]))
        self.assertTrue(rows[0].startswith("| # | Identity | Role | Where | What it is for |"))
        self.assertIn("Meternaut gateway key reader (custom role)", rows[4])

    def test_the_proposal_shows_exactly_this_table(self):
        text = self.PROPOSAL.read_text(encoding="utf-8")
        match = re.search(r"<!-- access-requirements:start -->\n(.*?)\n<!-- access-requirements:end -->", text, re.S)
        self.assertIsNotNone(match, "the proposal has no marked table")
        self.assertEqual(match.group(1), ar.markdown(MANIFEST), "run: python tools/access-requirements.py markdown, and paste it between the markers")

    def test_the_command_prints_it(self):
        code, out, _, _ = run(["markdown"], FakeAz())
        self.assertEqual((code, out), (0, ar.markdown(MANIFEST)))

    def test_no_row_of_the_table_says_that_a_role_changes_azure(self):
        self.assertNotIn("changes Azure", ar.markdown(MANIFEST))
        self.assertNotIn("W1", ar.markdown(MANIFEST))

    def test_one_row_for_each_retired_item_and_the_proposal_shows_exactly_this_table_too(self):
        rows = ar.markdown_retired(MANIFEST).splitlines()
        self.assertEqual(len(rows), 2 + len(MANIFEST["retired"]))
        self.assertTrue(rows[0].startswith("| # | Identity | Role | Where | Why it is retired |"))
        self.assertTrue(rows[2].startswith(f"| W1 | `{RETIRED_IDENTITY}` | {RETIRED_ROLE} (custom role) | "))
        text = self.PROPOSAL.read_text(encoding="utf-8")
        match = re.search(r"<!-- access-retired:start -->\n(.*?)\n<!-- access-retired:end -->", text, re.S)
        self.assertIsNotNone(match, "the proposal has no marked table of the retired grants")
        self.assertEqual(match.group(1), ar.markdown_retired(MANIFEST), "run: python tools/access-requirements.py markdown --retired, and paste it between the markers")

    def test_the_command_prints_the_retired_table_with_an_option(self):
        code, out, _, _ = run(["markdown", "--retired"], FakeAz())
        self.assertEqual((code, out), (0, ar.markdown_retired(MANIFEST)))


class TheCallsOfTheApp(unittest.TestCase):
    """Every call that the app makes with the identities that it holds is a line of the file, and every call in the file is made. There are two lists of
    such calls: the Watch's (its HTTP client) and the timer's (the reads that check a change afterwards). A change is made with the token of the person
    who approved it and is no requirement of an identity of Meternaut."""

    NAMES = {
        "resource-graph-query": lambda m, p: m == "POST" and "ResourceGraph" in p,
        "cost-management-query": lambda m, p: m == "POST" and "CostManagement" in p,
        "advisor-read": lambda m, p: m == "GET" and "Advisor" in p,
        "locks-read": lambda m, p: m == "GET" and "Authorization" in p and "locks" in p,
        "metric-definitions-read": lambda m, p: m == "GET" and "Microsoft.Insights/metricDefinitions" in p,
        "metrics-read": lambda m, p: m == "GET" and "Microsoft.Insights/metrics" in p,
        "security-pricings-read": lambda m, p: m == "GET" and "Microsoft.Security/pricings" in p,
        "gateway-key-read": lambda m, p: m == "POST" and "listSecrets" in p,
        "gateway-chat": lambda m, p: m == "POST" and "chat/completions" in p,
        "disk-read": lambda m, p: m == "GET" and "Microsoft.Compute/disks" in p,
        "public-ip-read": lambda m, p: m == "GET" and "Microsoft.Network/publicIPAddresses" in p,
    }
    NO_AZURE_ROLE = {"gateway-chat"}

    @staticmethod
    def watch_calls():
        return cases_http.allowed_calls("example-apim.azure-api.net", f"{PRODUCT}/listSecrets")

    @staticmethod
    def timer_calls():
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import runner
        finally:
            sys.path.remove(app)
        return runner.read_calls(PROJECT, "rg-project")

    def names_of(self, calls, whose):
        names = []
        for method, pattern in calls:
            text = pattern.pattern.replace("\\", "")
            found = [n for n, test in self.NAMES.items() if test(method, text)]
            self.assertEqual(len(found), 1, f"{whose}: {method} {text}: the app makes a call that the access requirements do not know. Add it to environment/access-requirements.json")
            names.append(found[0])
        self.assertEqual(len(names), len(set(names)), f"{whose}: a call is on the list twice")
        return names

    @staticmethod
    def listed(*ids):
        return {c for g in MANIFEST["grants"] if not ids or g["id"] in ids for c in g.get("calls", [])}

    def test_every_call_that_the_app_may_make_is_a_requirement_or_needs_no_azure_role(self):
        names = self.names_of(self.watch_calls(), "the Watch")
        self.assertLessEqual(set(names) - self.NO_AZURE_ROLE, self.listed(), "the Watch makes a call that the requirements do not list")

    def test_every_read_that_the_timer_makes_is_a_requirement_of_the_identity_that_reads_and_is_only_a_read(self):
        calls = self.timer_calls()
        self.assertTrue(calls)
        self.assertEqual({method for method, _ in calls}, {"GET"}, "the timer's list holds no write")
        names = self.names_of(calls, "the timer")
        r1 = next(g for g in MANIFEST["grants"] if g["id"] == "R1")
        self.assertEqual((r1["identity"], r1["role"]), ("cases", "Reader"), "the timer reads with the Watch's reader, and Reader holds every read")
        self.assertLessEqual(set(names), set(r1["calls"]), "the timer makes a read that R1 does not list")
        self.assertLessEqual({"disk-read", "public-ip-read"}, set(r1["calls"]))

    def test_the_calls_in_the_file_are_the_calls_of_the_watch_and_of_the_timer_and_no_other(self):
        names = set(self.names_of(self.watch_calls(), "the Watch")) | set(self.names_of(self.timer_calls(), "the timer"))
        self.assertEqual(sorted(names - self.NO_AZURE_ROLE), sorted(self.listed()), "the calls of the app and the calls in the requirements differ")

    def test_the_watch_makes_no_write_call_with_its_own_identities(self):
        # A change to Azure is made with the token of the person who approved it, from a list of its own: this list is the one of the app's identities.
        allowed = self.watch_calls()
        self.assertEqual({method for method, _ in allowed}, {"GET", "POST"})
        for method, pattern in allowed:
            if method == "POST":
                self.assertTrue(any(word in pattern.pattern for word in ("ResourceGraph", "CostManagement", "listSecrets", "chat/completions")), pattern.pattern)

    def test_the_calls_to_the_foundry_project_need_no_line_of_this_file_and_hold_the_only_writes_of_the_list(self):
        # The agents and the conversations are written with the identity's Foundry User role on the project, which the Foundry template assigns inside the project's own group.
        endpoint = "https://example.services.ai.azure.com/api/projects/meternaut"
        base = self.watch_calls()
        calls = cases_http.allowed_calls("example-apim.azure-api.net", f"{PRODUCT}/listSecrets", endpoint)
        self.assertEqual(calls[:len(base)], base)
        extra = calls[len(base):]
        self.assertTrue(extra)
        for method, pattern in extra:
            self.assertTrue(pattern.pattern.startswith(re.escape(endpoint)), pattern.pattern)
            self.assertEqual([n for n, test in self.NAMES.items() if test(method, pattern.pattern.replace("\\", ""))], [], pattern.pattern)
        self.assertEqual({method for method, _ in extra}, {"GET", "POST", "DELETE"})
        self.assertEqual([(m, p.pattern) for m, p in calls if m == "DELETE"],
                         [("DELETE", re.escape(endpoint) + r"/openai/v1/conversations/conv_[A-Za-z0-9_-]{1,100}")], "the one delete is the app's own conversation")

    def test_only_the_cases_identity_has_calls_listed(self):
        for grant in MANIFEST["grants"]:
            self.assertEqual(bool(grant.get("calls")), grant["identity"] == "cases", grant["id"])

    def test_the_reads_of_the_investigators_tools_are_gets_and_belong_to_the_reader(self):
        # Azure Monitor metrics, their definitions and the pricing settings of Microsoft Defender for Cloud are read with Reader (*/read), not with a role of their own.
        new = {"metric-definitions-read", "metrics-read", "security-pricings-read"}
        methods = {}
        for method, pattern in self.watch_calls():
            text = pattern.pattern.replace("\\", "")
            for name in new:
                if self.NAMES[name](method, text):
                    methods[name] = method
        self.assertEqual(methods, {name: "GET" for name in new})
        r1 = next(g for g in MANIFEST["grants"] if g["id"] == "R1")
        self.assertEqual((r1["role"], new <= set(r1["calls"])), ("Reader", True))
        for grant in MANIFEST["grants"]:
            if grant["id"] != "R1":
                self.assertFalse(new & set(grant.get("calls", [])), grant["id"])

    def test_the_metric_reads_may_name_any_resource_of_the_estate_and_the_pricing_read_only_a_subscription(self):
        by_name = {}
        for method, pattern in self.watch_calls():
            text = pattern.pattern.replace("\\", "")
            for name in ("metric-definitions-read", "metrics-read", "security-pricings-read"):
                if self.NAMES[name](method, text):
                    by_name[name] = pattern
        resource = f"https://management.azure.com/subscriptions/{PROJECT}/resourceGroups/rg-app/providers/Microsoft.Storage/storageAccounts/acct/blobServices/default"
        self.assertTrue(by_name["metrics-read"].fullmatch(f"{resource}/providers/Microsoft.Insights/metrics"))
        self.assertTrue(by_name["metric-definitions-read"].fullmatch(f"{resource}/providers/microsoft.insights/metricdefinitions"))
        pricings = f"https://management.azure.com/subscriptions/{PROJECT}/providers/Microsoft.Security/pricings"
        self.assertTrue(by_name["security-pricings-read"].fullmatch(pricings))
        self.assertFalse(by_name["security-pricings-read"].fullmatch(f"https://management.azure.com/subscriptions/{PROJECT}/resourceGroups/rg/providers/Microsoft.Security/pricings"))
        self.assertFalse(by_name["metrics-read"].fullmatch(f"https://management.azure.com.evil.example/subscriptions/{PROJECT}/providers/Microsoft.Insights/metrics"))


class Check(unittest.TestCase):
    def test_everything_granted_is_present_and_nothing_is_written(self):
        fake = FakeAz()
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual(code, 0)
        self.assertIn("5 of 5 present.", out)
        self.assertIn("signed in as operator@example.com", out)
        self.assertEqual(fake.writes(), [])

    def test_check_does_not_look_for_what_is_retired(self):
        fake = FakeAz().leave_the_writer()
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual((code, "5 of 5 present." in out), (0, True))
        self.assertNotIn("W1", out)
        self.assertNotIn(RETIRED_ROLE, out)
        self.assertFalse([c for c in fake.calls if RETIRED_IDENTITY in c or RETIRED_ROLE in c])

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
        self.assertEqual((code, "5 of 5 present." in out), (0, True))

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
        self.assertIn("7 change(s) would be made, and nothing else", out)
        self.assertEqual(fake.writes(), [])
        self.assertIn("az role assignment create --assignee-object-id case-principal", out)
        self.assertIn("az role assignment create --assignee-object-id usage-principal", out)
        self.assertNotIn(RETIRED_IDENTITY, out)
        self.assertNotIn("delete", out)

    def test_apply_makes_the_missing_custom_roles_first_and_then_every_assignment_and_checks_again(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        writes = fake.writes()
        kinds = [c[:3] for c in writes]
        self.assertEqual(kinds.count(["role", "definition", "create"]), 2)
        self.assertEqual(kinds.count(["role", "assignment", "create"]), 5)
        self.assertEqual(len(kinds), 7, "nothing but makes: grant never removes")
        custom_ids = {r["name"] for r in fake.roles.values()}
        for name in ("Meternaut gateway key reader", "Meternaut usage reader"):
            role_id = fake.roles[name]["name"]
            define = next(i for i, c in enumerate(writes) if c[:3] == ["role", "definition", "create"] and name in str(fake.definition_files))
            assign = next(i for i, c in enumerate(writes) if c[:3] == ["role", "assignment", "create"] and c[c.index("--role") + 1] == role_id)
            self.assertLess(define, assign, "a custom role is made before it is assigned")
        self.assertEqual(len(custom_ids), 2)
        self.assertTrue(out.rstrip().endswith("5 of 5 present."))
        self.assertIn("Checking again:", out)

    def test_nothing_is_made_in_the_project_group_and_no_role_that_changes_anything_is_defined(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        for call in fake.writes():
            if call[:3] == ["role", "assignment", "create"]:
                self.assertFalse(call[call.index("--scope") + 1].lower().startswith(PROJECT_GROUP.lower()), call)
        for _, content in fake.definition_files:
            self.assertNotIn(PROJECT_GROUP, content["AssignableScopes"])
            self.assertTrue(all(a.endswith("/read") or a == KEY_ACTION for a in content["Actions"]), content["Name"])

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
        self.assertEqual(len(assigned), 3)
        self.assertTrue(all(c[c.index("--assignee-object-id") + 1] == "case-principal" for c in assigned))

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


class Retire(unittest.TestCase):
    """What the first version of the console left behind: the writer's role, its assignments (also those of an identity that was deleted) and its identity."""

    def left(self, **options):
        return FakeAz().leave_the_writer(**options)

    def commands(self, out):
        return [line.strip() for line in out.splitlines() if line.strip().startswith("az ")]

    def test_a_dry_run_says_what_it_would_remove_with_the_exact_commands_and_removes_nothing(self):
        fake = self.left(below=1)
        code, out, _, _ = run(["retire", *PLACES], fake)
        self.assertEqual(code, 1, "something is left to retire, and a script can tell")
        self.assertEqual(fake.writes(), [])
        self.assertIn("Signed in as operator@example.com.", out)
        self.assertIn("4 change(s) would be made, and nothing else", out)
        self.assertIn("This was a dry run", out)
        commands = self.commands(out)
        for assignment in fake.of_the_role():
            self.assertTrue(any(c.startswith(f"az role assignment delete --ids {assignment['id']}") for c in commands), assignment["id"])
        self.assertEqual(len([c for c in commands if c.startswith("az role assignment delete")]), 3)
        self.assertEqual(len([c for c in commands if c.startswith("az role definition delete")]), 1)
        self.assertTrue(commands[-1].startswith(f"az role definition delete --subscription {PROJECT} --name {RETIRED_ROLE_ID}"))
        self.assertIn("only when no assignment of it remains", commands[-1])

    def test_it_reads_first_names_what_it_found_and_lists_the_assignments_by_role_and_never_by_identity(self):
        fake = self.left(below=1)
        code, out, _, _ = run(["retire", *PLACES], fake)
        self.assertRegex(out, rf"still there +W1  {RETIRED_IDENTITY}  {RETIRED_ROLE}  at {re.escape(PROJECT_GROUP)}")
        self.assertIn(f"the custom role exists ({RETIRED_ROLE_ID}); 3 assignment(s) of it at or below this place", out)
        self.assertIn("held by id-meternaut-runner", out)
        self.assertIn("deleted-principal-1 (an identity that is not id-meternaut-runner, or one that was deleted: the portal shows that as 'Identity not found')", out)
        urls = [c[c.index("--url") + 1] for c in fake.calls if c[0] == "rest"]
        self.assertTrue(urls)
        self.assertFalse(any("principalId" in url for url in urls))
        self.assertEqual({c[c.index("--method") + 1] for c in fake.calls if c[0] == "rest"}, {"get"})

    def test_apply_reads_first_removes_the_assignments_then_the_role_and_checks_again(self):
        fake = self.left(below=1)
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 3 + [["role", "definition", "delete"]])
        self.assertEqual(fake.of_the_role(), [])
        self.assertNotIn(RETIRED_ROLE, fake.roles)
        self.assertIn("Checking again:", out)
        self.assertTrue(out.rstrip().endswith("1 of 1 gone."))
        first = next(i for i, c in enumerate(fake.calls) if c in fake.writes())
        self.assertEqual(fake.calls[0][:2], ["account", "show"])
        self.assertTrue(any(c[:3] == ["role", "definition", "list"] for c in fake.calls[:first]))
        self.assertTrue(any(c[0] == "rest" for c in fake.calls[:first]))
        removed = [c[c.index("--ids") + 1] for c in fake.writes() if c[:3] == ["role", "assignment", "delete"]]
        self.assertEqual(len(removed), len(set(removed)))
        self.assertEqual(fake.writes()[-1][fake.writes()[-1].index("--name") + 1], RETIRED_ROLE_ID)

    def test_the_assignments_of_an_identity_that_no_longer_exists_are_removed_too(self):
        fake = self.left(identity=False, orphans=2)
        code, out, _, _ = run(["retire", *PLACES], fake)
        self.assertEqual(code, 1)
        self.assertIn("2 assignment(s) of it at or below this place", out)
        self.assertIn("Identity not found", out)
        self.assertIn(f"{RETIRED_IDENTITY} does not exist in {PROJECT_GROUP}", out)
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual((fake.of_the_role(), RETIRED_ROLE in fake.roles), ([], False))

    def test_only_the_assignments_of_that_role_at_that_place_are_removed_and_nothing_else(self):
        fake = self.left(below=1)
        fake.grant("runner-principal", BUILTIN["Reader"], PROJECT_GROUP)
        fake.grant("case-principal", BUILTIN["Reader"], PROJECT_GROUP)
        fake.grant("runner-principal", USAGE_READER_ID, WORKSPACE)
        others = [dict(x) for x in fake.assignments if x["role_id"] != RETIRED_ROLE_ID]
        roles = {name: dict(role) for name, role in fake.roles.items() if name != RETIRED_ROLE}
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.assignments, others, "every other assignment of every identity is still there")
        self.assertEqual({n: r for n, r in fake.roles.items()}, roles, "every other role is still there")
        self.assertEqual(sorted({tuple(c[:3]) for c in fake.writes()}), [("role", "assignment", "delete"), ("role", "definition", "delete")])
        self.assertEqual(fake.identities, {"id-meternaut-cases": "case-principal", "id-meternaut-usage": "usage-principal", RETIRED_IDENTITY: "runner-principal"})

    def test_it_never_deletes_an_identity_and_says_who_does(self):
        fake = self.left()
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertIn(f"{RETIRED_IDENTITY} still exists in {PROJECT_GROUP} (object id runner-principal)", out)
        self.assertIn("never deletes an identity: the deployment workflow or the owner removes it", out)
        self.assertIn(RETIRED_IDENTITY, fake.identities)
        allowed = {("account", "show"), ("identity", "show"), ("role", "definition"), ("role", "assignment"), ("rest", "--method")}
        self.assertEqual({tuple(c[:2]) for c in fake.calls} - allowed, set())
        self.assertFalse([c for c in fake.calls if c[:2] == ["identity", "delete"] or c[0] == "ad"])

    def test_a_second_run_has_nothing_to_retire(self):
        fake = self.left(below=1)
        run(["retire", *PLACES, "--apply", "--yes"], fake)
        before = len(fake.writes())
        for argv in (["retire", *PLACES, "--apply", "--yes"], ["retire", *PLACES]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual((code, len(fake.writes()), "Nothing to retire." in out), (0, before, True), argv)

    def test_when_nothing_is_there_it_says_so(self):
        fake = FakeAz()
        code, out, _, _ = run(["retire", *PLACES], fake)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to retire.", out)
        self.assertRegex(out, rf"gone +W1  {RETIRED_IDENTITY}")
        self.assertEqual(fake.writes(), [])

    def test_an_identity_that_is_still_there_without_any_role_is_reported_and_there_is_nothing_to_retire(self):
        fake = FakeAz()
        fake.identities[RETIRED_IDENTITY] = "runner-principal"
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to retire.", out)
        self.assertIn("still exists", out)
        self.assertEqual(fake.writes(), [])

    def test_a_pipeline_may_not_apply_but_a_dry_run_is_allowed(self):
        fake = self.left()
        code, _, err, _ = run(["retire", *PLACES, "--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 1)
        self.assertIn("never a pipeline", err)
        self.assertEqual(fake.calls, [], "it refused before it read or wrote anything")
        code, out, _, _ = run(["retire", *PLACES], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake, env={})
        self.assertEqual(code, 0, "outside a pipeline it applies")

    def test_it_asks_first_unless_it_is_told_not_to(self):
        fake, asked = self.left(), []
        code, out, _, _ = run(["retire", *PLACES, "--apply"], fake, answers=("yes",), asked=asked)
        self.assertEqual(code, 0, out)
        self.assertIn("operator@example.com", asked[0])
        fake = self.left()
        code, _, err, _ = run(["retire", *PLACES, "--apply"], fake, answers=("no",))
        self.assertEqual((code, fake.writes()), (1, []))
        self.assertIn("nothing was changed", err)
        fake = self.left()
        code, _, err, _ = run(["retire", *PLACES, "--apply"], fake, answers=())
        self.assertEqual((code, fake.writes()), (1, []))
        self.assertIn("needs --yes", err)

    def test_the_role_is_kept_while_an_assignment_of_it_remains(self):
        fake = self.left()
        stubborn = fake.of_the_role()[0]["id"]
        fake.stubborn = {stubborn}
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"kept the custom role {RETIRED_ROLE}: 1 assignment(s) of it remain", out)
        self.assertEqual([c for c in fake.calls if c[:3] == ["role", "definition", "delete"]], [])
        self.assertIn(RETIRED_ROLE, fake.roles)
        self.assertTrue(out.rstrip().endswith("0 of 1 gone."))

    def test_a_failure_to_remove_an_assignment_stops_at_once_and_says_which(self):
        fake = self.left(orphans=2)
        fake.unassign_errors = ["ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Authorization/roleAssignments/delete'"]
        code, out, err, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("could not be removed", err)
        self.assertIn(fake.of_the_role()[0]["id"], err)
        self.assertEqual(len([c for c in fake.calls if c[:3] == ["role", "assignment", "delete"]]), 1, "it did not go on to the next")
        self.assertEqual([c for c in fake.calls if c[:3] == ["role", "definition", "delete"]], [])

    def test_an_assignment_that_is_gone_already_is_not_an_error(self):
        fake = self.left(identity=False, orphans=1)
        fake.vanish = {fake.of_the_role()[0]["id"]}
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertIn("was gone already", out)
        self.assertEqual((fake.of_the_role(), RETIRED_ROLE in fake.roles), ([], False))

    def test_a_role_that_azure_still_reports_as_assigned_is_tried_again_after_a_pause(self):
        fake = self.left()
        fake.definition_errors = ["ERROR: (RoleDefinitionHasAssignments) There are existing role assignments referencing role (code: RoleDefinitionHasAssignments)"] * 2
        code, out, _, sleeps = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(sleeps, [15, 15])
        self.assertNotIn(RETIRED_ROLE, fake.roles)

    def test_a_role_that_azure_keeps_reporting_as_assigned_ends_with_the_reason(self):
        fake = self.left()
        fake.definition_errors = ["ERROR: (RoleDefinitionHasAssignments) There are existing role assignments referencing role (code: RoleDefinitionHasAssignments)"] * 8
        code, _, err, sleeps = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual((code, len(sleeps)), (1, 7))
        self.assertIn("could not be removed", err)
        self.assertIn("RoleDefinitionHasAssignments", err)

    def test_any_other_failure_to_remove_the_role_stops_and_says_so(self):
        fake = self.left()
        fake.definition_errors = ["ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Authorization/roleDefinitions/delete'"]
        code, _, err, sleeps = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual((code, sleeps), (1, []))
        self.assertIn(f"the custom role {RETIRED_ROLE} could not be removed", err)

    def test_a_role_that_can_also_be_assigned_outside_the_place_is_left_alone(self):
        fake = self.left()
        fake.roles[RETIRED_ROLE]["assignableScopes"].append(f"/subscriptions/{PROJECT}/resourceGroups/rg-other")
        for argv in (["retire", *PLACES], ["retire", *PLACES, "--apply", "--yes"]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual(code, 1, argv)
            self.assertRegex(out, r"left alone +W1")
            self.assertIn("outside this place", out)
            self.assertIn("Nothing can be retired until the lines above that say 'left alone' are settled.", out)
        self.assertEqual(fake.writes(), [])

    def test_two_custom_roles_of_that_name_stop_it(self):
        fake = self.left()
        other = retired_definition(name="00000000-0000-0000-0000-0000000000a9")
        fake.roles["another"] = dict(other, roleName=RETIRED_ROLE)
        code, _, err, _ = run(["retire", *PLACES], fake)
        self.assertEqual(code, 1)
        self.assertIn("two custom roles are called", err)

    def test_a_list_with_a_next_page_is_read_to_the_end(self):
        fake = self.left(orphans=2, below=1)
        fake.page_size = 1
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual((fake.of_the_role(), RETIRED_ROLE in fake.roles), ([], False))
        self.assertGreater(len([c for c in fake.calls if c[0] == "rest"]), 4)

    def test_an_assignment_with_an_id_that_is_not_a_role_assignment_is_never_passed_to_a_delete(self):
        fake = self.left()
        fake.of_the_role()[0]["id"] = f"{PROJECT_GROUP}/providers/Microsoft.Compute/disks/a-disk"
        code, _, err, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("does not recognise", err)
        self.assertEqual(fake.writes(), [])

    def test_only_names_a_retired_item_and_an_unknown_one_is_refused(self):
        code, out, _, _ = run(["retire", *PLACES, "--only", "W1"], self.left())
        self.assertEqual(code, 1)
        self.assertIn("W1", out)
        code, _, err, _ = run(["retire", *PLACES, "--only", "W9"], self.left())
        self.assertEqual(code, 1)
        self.assertIn("W9", err)
        self.assertIn("W1", err)

    def test_a_missing_place_is_named(self):
        for argv, word in ((["retire"], "--project-subscription"), (["retire", "--project-subscription", PROJECT], "--project-group")):
            code, _, err, _ = run(argv, self.left())
            self.assertEqual(code, 1, argv)
            self.assertIn(word, err)

    def test_the_settings_of_the_workflow_are_read_from_the_environment(self):
        code, out, _, _ = run(["retire"], self.left(), env={"ENV_SUBSCRIPTION_ID": PROJECT, "ENV_RESOURCE_GROUP": "rg-project"})
        self.assertEqual(code, 1)
        self.assertIn(f"at {PROJECT_GROUP}", out)


if __name__ == "__main__":
    unittest.main()
