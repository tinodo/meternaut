import contextlib
import copy
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
CASES_SITE = "func-meternaut-cases-abc123"
USAGE_SITE = "func-meternaut-usage-abc123"
SITES = ["--cases-site", CASES_SITE, "--usage-site", USAGE_SITE]
PLACES = ["--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway", APIM, "--gateway-insights", INSIGHTS, *SITES]
# The holders of the requirements while the apps are moved: the user-assigned identity that an app had, and the system-assigned identity that it gets.
OLD_CASES, OLD_USAGE = "case-principal", "usage-principal"
NEW_CASES, NEW_USAGE = "case-system-principal", "usage-system-principal"
KEY_READER = "Meternaut gateway key reader"
KEY_READER_ID = "00000000-0000-0000-0000-0000000000a1"
USAGE_READER_ID = "00000000-0000-0000-0000-0000000000a2"
# What the first environment's workflow needed in the gateway's group: the deployment identity's own role. The file no longer has it (it is retired, W8), so the test makes it the way
# the first environment did.
DEPLOYER = "Meternaut gateway deployer"
DEPLOYER_ID = "00000000-0000-0000-0000-0000000000a4"
DEPLOYER_IDENTITY = "meternaut-deploy-sc-uami"
DEPLOYER_ACTIONS = ["Microsoft.ApiManagement/service/read", "Microsoft.ApiManagement/service/write", "Microsoft.Resources/deployments/*", "Microsoft.Insights/components/read"]
# What the first cases of an earlier version needed to read a key of the gateway: the file no longer has this role (it is retired, W7), so the test makes it the way that version did.
KEY_READER_ACTIONS = ["Microsoft.ApiManagement/service/subscriptions/read", "Microsoft.ApiManagement/service/subscriptions/listSecrets/action"]
# What the first version of the console left behind: the file no longer has this role, so the test makes it the way that version did.
RETIRED_ROLE = "Meternaut waste remover"
RETIRED_ROLE_ID = "00000000-0000-0000-0000-0000000000a3"
RETIRED_IDENTITY = "id-meternaut-runner"
RETIRED_ACTIONS = ["Microsoft.Compute/disks/read", "Microsoft.Compute/disks/delete", "Microsoft.Network/publicIPAddresses/read",
                   "Microsoft.Network/publicIPAddresses/delete", "Microsoft.Authorization/locks/read"]

MANIFEST = ar.load_manifest()
BUILTIN = {name: spec["id"] for name, spec in MANIFEST["roles"].items() if spec["kind"] == "builtin"}


def file_as_it_was_before_the_usage_app_was_retired():
    """The file of the repository with what the retirement of 2026-11-07 took out put back as it was: the usage app and its identity, the custom role Meternaut usage reader, the two reads that the app
    made (R4, R5) and the retired items W5 and W6 (the grants of the user-assigned identity that the app ran as before) in place of W9 and W10. The tool's rules for a custom role, for an app with two reads
    and for a grant that replaces another are pinned against a file that has all of them, and the file in the repository has none of them any more: most of the tests run the tool against this file, and
    the class RetireTheUsageApp runs it against the real one."""
    document = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8"))
    document["identities"]["usage"] = {"app": "the usage app", "appName": "func-meternaut-usage-*", "madeBy": "recording", "holders": [{"kind": "system", "siteOption": "--usage-site"}]}
    document["roles"]["Meternaut usage reader"] = {
        "kind": "custom", "definedIn": "workspaceGroup",
        "description": "Reads one table (AppMetrics, the metrics of workspace-based Application Insights) of the central workspace, so that the usage copy job of Meternaut can read the gateway token metrics. Nothing else.",
        "actions": ["Microsoft.OperationalInsights/workspaces/read", "Microsoft.OperationalInsights/workspaces/query/read", "Microsoft.OperationalInsights/workspaces/query/AppMetrics/read"]}
    document["grants"] += [
        {"id": "R4", "identity": "usage", "role": "Monitoring Reader", "place": "gatewayInsights",
         "why": "Reads the gateway's Application Insights component, where the gateway records the token metrics of every call"},
        {"id": "R5", "identity": "usage", "role": "Meternaut usage reader", "place": "centralWorkspace",
         "why": "Reads one table (AppMetrics) of the central workspace. The component is workspace-based and the workspace asks for workspace permissions, so the role on the component alone returns no rows"}]
    replaced = [
        {"id": "W5", "identity": {"name": "id-meternaut-usage"}, "role": "Monitoring Reader", "place": "gatewayInsights", "replacedBy": "R4",
         "why": "Held by the user-assigned identity that the usage app ran as before its own system-assigned identity took over (R4). Only that identity's assignment is removed, and the role stays: R4 needs it"},
        {"id": "W6", "identity": {"name": "id-meternaut-usage"}, "role": "Meternaut usage reader", "place": "centralWorkspace", "replacedBy": "R5",
         "why": "Held by the user-assigned identity that the usage app ran as before its own system-assigned identity took over (R5). Only that identity's assignment is removed, and the custom role stays: R5 needs it"}]
    retired = [item for item in document["retired"] if item["id"] not in ("W9", "W10")]
    document["retired"] = retired[:3] + replaced + retired[3:]
    return document


def load(document):
    """The manifest that the loader makes of a document, which it reads from a file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "access-requirements.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return ar.load_manifest(path)


OLD = load(file_as_it_was_before_the_usage_app_was_retired())


def definition(name, role_id, group, **changes):
    spec = OLD["roles"][name]
    value = {"name": role_id, "roleName": name, "assignableScopes": [group],
             "permissions": [{"actions": list(spec["actions"]), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


def retired_definition(**changes):
    value = {"name": RETIRED_ROLE_ID, "roleName": RETIRED_ROLE, "assignableScopes": [PROJECT_GROUP],
             "permissions": [{"actions": list(RETIRED_ACTIONS), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


def key_reader_definition(**changes):
    value = {"name": KEY_READER_ID, "roleName": KEY_READER, "assignableScopes": [GATEWAY_GROUP],
             "permissions": [{"actions": list(KEY_READER_ACTIONS), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


def deployer_definition(**changes):
    value = {"name": DEPLOYER_ID, "roleName": DEPLOYER, "assignableScopes": [GATEWAY_GROUP],
             "permissions": [{"actions": list(DEPLOYER_ACTIONS), "notActions": [], "dataActions": [], "notDataActions": []}]}
    value.update(changes)
    return value


class FakeAz:
    """Answers the Azure CLI commands of the tool from a small model of a tenant, and remembers every command.

    granted: the custom role exists and the system-assigned identities of the two apps hold their requirements.
    old: the user-assigned identities that the apps ran as before hold the same grants still (what retire finds before it removes them)."""

    def __init__(self, granted=True, old=True):
        self.identities = {"id-meternaut-cases": OLD_CASES, "id-meternaut-usage": OLD_USAGE}
        # The apps of the project's group, and the object id of the system-assigned identity of each (None: the app has none).
        self.sites = {CASES_SITE: NEW_CASES, USAGE_SITE: NEW_USAGE}
        self.site_error = None
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
            self.roles["Meternaut usage reader"] = definition("Meternaut usage reader", USAGE_READER_ID, WORKSPACE_GROUP)
            self.give(NEW_CASES, NEW_USAGE)
            if old:
                self.give(OLD_CASES, OLD_USAGE)

    def give(self, cases, usage):
        """The requirements of the two apps, held by these two principals."""
        self.grant(cases, BUILTIN["Reader"], ESTATE)
        self.grant(cases, BUILTIN["Cost Management Reader"], ESTATE)
        self.grant(usage, BUILTIN["Monitoring Reader"], INSIGHTS)
        self.grant(usage, USAGE_READER_ID, WORKSPACE)

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

    def leave_the_key_reader(self, orphans=1, below=0):
        """What the first cases of an earlier version left in the gateway's resource group: the custom role, its assignment to the cases app's system-assigned
        identity and to the user-assigned identity that the app ran as before, on the one subscription of the access product; the assignments of identities that were
        deleted since (Azure keeps them) and, optionally, assignments on the instance itself, which is below the group too."""
        self.roles[KEY_READER] = key_reader_definition()
        self.grant(NEW_CASES, KEY_READER_ID, PRODUCT)
        self.grant(OLD_CASES, KEY_READER_ID, PRODUCT)
        for n in range(orphans):
            self.grant(f"deleted-principal-{n + 1}", KEY_READER_ID, PRODUCT)
        for n in range(below):
            self.grant("somebody-with-the-role", KEY_READER_ID, APIM)
        return self

    def leave_the_usage_app(self, orphans=1, below=1):
        """What the usage recording left for the file of the repository (W9, W10): Monitoring Reader on the old gateway's Application Insights for the usage app's system-assigned identity, for the
        user-assigned identity id-meternaut-usage and for somebody else (whose assignment stays); the custom role Meternaut usage reader, defined in the central workspace's group, held by both of the
        app's identities, by identities that were deleted since (Azure keeps them) and, optionally, by somebody on the workspace itself, which is below the group."""
        self.roles["Meternaut usage reader"] = definition("Meternaut usage reader", USAGE_READER_ID, WORKSPACE_GROUP)
        for principal in (NEW_USAGE, OLD_USAGE, "somebody-else"):
            self.grant(principal, BUILTIN["Monitoring Reader"], INSIGHTS)
        for principal in (NEW_USAGE, OLD_USAGE):
            self.grant(principal, USAGE_READER_ID, WORKSPACE)
        for n in range(orphans):
            self.grant(f"deleted-principal-{n + 1}", USAGE_READER_ID, WORKSPACE_GROUP)
        for n in range(below):
            self.grant("somebody-with-the-role", USAGE_READER_ID, WORKSPACE)
        return self

    def leave_the_deployer(self, orphans=0, below=0):
        """What the first environment left in the gateway's resource group: the deployment identity's own custom role and its assignment (the identity lives in the
        bootstrap group, so the project's group does not have it), the assignments of identities that were deleted since (Azure keeps them) and, optionally,
        assignments on the instance itself, which is below the group too."""
        self.roles[DEPLOYER] = deployer_definition()
        self.grant("deploy-principal", DEPLOYER_ID, GATEWAY_GROUP)
        for n in range(orphans):
            self.grant(f"deleted-principal-{n + 1}", DEPLOYER_ID, GATEWAY_GROUP)
        for n in range(below):
            self.grant("somebody-with-the-role", DEPLOYER_ID, APIM)
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
            site = re.fullmatch(rf"{re.escape(ar.ARM + PROJECT_GROUP)}/providers/Microsoft\.Web/sites/([A-Za-z0-9-]+)\?api-version={re.escape(ar.SITE_API)}", url)
            if site:
                if self.site_error:
                    return 1, "", self.site_error
                name = site.group(1)
                if name not in self.sites:
                    return 3, "", (f"ERROR: Not Found({{\"error\":{{\"code\":\"ResourceNotFound\",\"message\":\"The Resource 'Microsoft.Web/sites/{name}' under "
                                   f"resource group 'rg-project' was not found.\"}}}})")
                principal = self.sites[name]
                other = {f"{PROJECT_GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-console-auth": {"principalId": "auth-principal", "clientId": "c"}}
                identity = ({"type": "SystemAssigned, UserAssigned", "principalId": principal, "tenantId": "tenant", "userAssignedIdentities": other} if principal
                            else {"type": "UserAssigned", "userAssignedIdentities": other})
                return 0, json.dumps({"name": name, "type": "Microsoft.Web/sites", "identity": identity}), ""
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


def run(argv, fake, env=None, answers=("yes",), asked=None, real=False):
    """Runs the tool against the model of Azure. It reads the file as it was before the usage app was retired, unless real is true (the file of the repository)."""
    lines, errors, sleeps = [], io.StringIO(), []
    answers = list(answers)

    def ask(prompt):
        if asked is not None:
            asked.append(prompt)
        return answers.pop(0) if answers else None

    manifest = contextlib.nullcontext() if real else mock.patch.object(ar, "load_manifest", lambda path=None: OLD)
    with contextlib.redirect_stderr(errors), manifest:
        code = ar.main(argv, az=ar.Az(fake), env={} if env is None else env, out=lines.append, sleep=sleeps.append, ask=ask)
    return code, "\n".join(lines), errors.getvalue(), sleeps


class TheFile(unittest.TestCase):
    def broken(self, change, real=False):
        """The file with one change, written to a place where the loader can read it; returns what the loader says. It starts from the file as it was before the usage app was retired, which
        has what the loader's rules are about (two apps, a custom role, a grant that replaces another), unless real is true: then it starts from the file of the repository."""
        document = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8")) if real else file_as_it_was_before_the_usage_app_was_retired()
        change(document)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ar.Problem) as raised:
                ar.load_manifest(path)
        return str(raised.exception)

    def test_it_loads_and_every_reference_resolves(self):
        self.assertEqual([g["id"] for g in MANIFEST["grants"]], ["R1", "R2"], "R3, the key reader, and R4 and R5, the usage app's two reads, are retired")
        for grant in MANIFEST["grants"]:
            self.assertIn(grant["identity"], MANIFEST["identities"])
            self.assertIn(grant["place"], MANIFEST["places"])
            self.assertIn(grant["role"], MANIFEST["roles"])
        for item in MANIFEST["retired"]:
            self.assertIn(item["place"], MANIFEST["places"], item["id"])

    def test_the_built_in_roles_are_the_ones_that_azure_has_and_all_of_them_only_read(self):
        self.assertEqual(BUILTIN, {"Reader": "acdd72a7-3385-48ef-bd42-f606fba81ae7", "Cost Management Reader": "72fafb9e-0641-4937-9268-a91bfd8191a3",
                                   "Monitoring Reader": "43d0d8ad-25c7-4714-9337-8ba259a9fe05"})

    def test_meternaut_holds_no_write_right_and_reads_no_key_and_the_file_has_no_custom_role_since_the_last_one_was_retired(self):
        customs = [name for name, spec in MANIFEST["roles"].items() if spec["kind"] == "custom"]
        self.assertEqual(customs, [], "Meternaut usage reader, the last one, was retired as W10 on 2026-11-07")
        for name, spec in OLD["roles"].items():
            if spec["kind"] == "custom":
                for action in spec["actions"]:
                    self.assertNotIn("*", action, name)
                    self.assertTrue(action.endswith("/read"), f"{name}: {action}")
        text = (ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8")
        for word in ("listSecrets", "listKeys", "/action"):
            self.assertNotIn(word, text, f"{word}: since 2026-11-07 no role of the file reads a key")

    def test_the_key_reader_is_retired_with_its_grant_and_is_not_granted(self):
        self.assertNotIn(KEY_READER, MANIFEST["roles"])
        self.assertNotIn("R3", [g["id"] for g in MANIFEST["grants"]])
        self.assertNotIn(KEY_READER, [g["role"] for g in MANIFEST["grants"]])
        self.assertNotIn("gatewayProductSubscription", MANIFEST["places"], "nothing is granted on the access product any more")
        item = next(r for r in MANIFEST["retired"] if r["id"] == "W7")
        self.assertEqual((item["role"], item["place"], item["identity"]), (KEY_READER, "gatewayGroup", {"name": "id-meternaut-cases"}))
        self.assertNotIn("replacedBy", item, "it is retired whole: every assignment of the role, whoever holds it, and then the role")
        self.assertTrue(item["why"])
        self.assertIn("gatewayGroup", MANIFEST["places"])
        self.assertIn("2026-11-07", item["why"])

    def test_nothing_in_the_file_says_that_a_role_changes_azure_and_no_identity_is_a_writer(self):
        text = (ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8")
        self.assertNotIn('"writes"', text)
        self.assertEqual(sorted(MANIFEST["identities"]), ["cases"], "the usage app, the other identity, was retired on 2026-11-07")
        self.assertEqual([h for i in MANIFEST["identities"].values() for h in i["holders"] if h["kind"] == "user"], [], "no app runs as a user-assigned identity that needs a role")
        self.assertNotIn("runner", [g["identity"] for g in MANIFEST["grants"]])

    def test_an_identity_is_what_an_app_runs_as_and_its_only_holder_is_the_system_assigned_identity_of_the_app(self):
        for key, option in (("cases", "--cases-site"),):
            identity = MANIFEST["identities"][key]
            self.assertEqual(identity["holders"], [{"kind": "system", "siteOption": option}], key)
            self.assertTrue(identity["app"] and identity["madeBy"], key)
            self.assertIn("*", identity["appName"], "the name of an app is a pattern here, never a real name")
        self.assertEqual({k: i["madeBy"] for k, i in MANIFEST["identities"].items()}, {"cases": "cases"})
        self.assertEqual({k: i["madeBy"] for k, i in OLD["identities"].items()}, {"cases": "cases", "usage": "recording"}, "the file before the retirement, which the tests of the tool run against")

    def test_the_options_that_name_the_apps_are_options_of_every_command_and_have_a_setting_each(self):
        self.assertEqual(ar.SITE_OPTIONS, {"--cases-site": "ACCESS_CASES_SITE", "--usage-site": "ACCESS_USAGE_SITE"})
        for command in ("check", "grant", "retire"):
            code, out, err, _ = run([command, "--project-subscription", PROJECT, "--project-group", "rg-project", "--usage-site", "bad site name"], FakeAz())
            self.assertEqual(code, 1, command)
            self.assertIn("--usage-site is the name of a function app", err)

    def test_the_file_holds_no_identifier_of_a_real_estate(self):
        text = (ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8")
        built_in = {spec["id"] for spec in MANIFEST["roles"].values() if spec["kind"] == "builtin"}
        for found in re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I):
            self.assertIn(found, built_in, "a GUID of the file is the id of a built-in role and nothing else")

    def test_the_loader_refuses_holders_that_do_not_make_sense(self):
        def twice(document):
            for key in ("cases", "usage"):
                document["identities"][key]["holders"].append({"kind": "user", "name": "id-meternaut-shared"})

        for change, word in (
            (lambda d: d["identities"]["cases"].update(holders=[]), "has holders"),
            (lambda d: d["identities"]["cases"].update(holders=[{"kind": "system", "siteOption": "--cases-site"}, {"kind": "system", "siteOption": "--usage-site"}]), "one system-assigned"),
            (lambda d: d["identities"]["cases"].update(holders=[{"kind": "managed"}]), "'system' or 'user'"),
            (lambda d: d["identities"]["cases"].update(holders=[{"kind": "system", "siteOption": "--other-site"}]), "siteOption"),
            (lambda d: d["identities"]["cases"].update(holders=[{"kind": "system"}]), "siteOption"),
            (lambda d: d["identities"]["cases"].update(holders=[{"kind": "user"}]), "has a name"),
            (lambda d: d["identities"]["cases"].update(holders=[{"kind": "user", "name": "not a name"}]), "has a name"),
            (twice, "holder once"),
            (lambda d: d["identities"]["usage"]["holders"].__setitem__(0, {"kind": "system", "siteOption": "--cases-site"}), "names one app"),
            (lambda d: d["identities"]["cases"].pop("madeBy"), "madeBy"),
            (lambda d: d["identities"]["cases"].pop("holders"), "holders"),
            (lambda d: d["identities"]["cases"].update(app=""), "names its app"),
        ):
            self.assertIn(word, self.broken(change))

    def test_a_role_that_is_marked_as_changing_azure_is_refused(self):
        said = self.broken(lambda d: d["roles"]["Meternaut usage reader"].update(writes=True))
        self.assertIn("holds no write right", said)

    def test_the_earlier_writer_is_retired_and_is_not_granted(self):
        self.assertEqual(MANIFEST["retired"][0], {"id": "W1", "identity": {"name": RETIRED_IDENTITY}, "role": RETIRED_ROLE, "place": "projectGroup",
                                                  "why": MANIFEST["retired"][0]["why"]})
        self.assertTrue(MANIFEST["retired"][0]["why"])
        self.assertNotIn(RETIRED_ROLE, MANIFEST["roles"])
        self.assertNotIn(RETIRED_IDENTITY, [h.get("name") for i in MANIFEST["identities"].values() for h in i["holders"]])
        self.assertIn(MANIFEST["retired"][0]["place"], MANIFEST["places"])

    def test_the_grants_of_the_user_assigned_identities_are_retired_each_one_next_to_the_grant_that_replaces_it(self):
        self.assertEqual([r["id"] for r in MANIFEST["retired"]], ["W1", "W2", "W3", "W7", "W8", "W9", "W10"])
        names = {"cases": "id-meternaut-cases", "usage": "id-meternaut-usage"}
        for manifest, ids, pairs in ((MANIFEST, ["W1", "W7", "W8", "W9", "W10"], [("W2", "R1"), ("W3", "R2")]),
                                     (OLD, ["W1", "W7", "W8"], [("W2", "R1"), ("W3", "R2"), ("W5", "R4"), ("W6", "R5")])):
            grants = {g["id"]: g for g in manifest["grants"]}
            replaced = [r for r in manifest["retired"] if "replacedBy" in r]
            for item in replaced:
                replacing = grants[item["replacedBy"]]
                self.assertEqual((item["role"], item["place"]), (replacing["role"], replacing["place"]), item["id"])
                self.assertEqual(item["identity"], {"name": names[replacing["identity"]]}, item["id"])
                self.assertIn(item["role"], manifest["roles"], "the role stays: the grant that replaces it needs it")
                self.assertTrue(item["why"])
            self.assertEqual([(r["id"], r["replacedBy"]) for r in replaced], pairs, "every grant of the old identities that something replaces is retired, and none besides")
            self.assertEqual([r["id"] for r in manifest["retired"] if "replacedBy" not in r and "roleStays" not in r and r["id"] not in ("W9", "W10")], ids[:3],
                             "the three custom roles that are gone whole")

    def test_the_usage_apps_two_reads_are_retired_as_w9_and_w10_the_way_w7_and_w8_were_and_nothing_replaces_them(self):
        retired = {r["id"]: r for r in MANIFEST["retired"]}
        w9, w10 = retired["W9"], retired["W10"]
        self.assertEqual((w9["identity"], w9["role"], w9["place"], w9["roleStays"]), ({"name": "id-meternaut-usage"}, "Monitoring Reader", "gatewayInsights", True))
        self.assertEqual(w9["alsoHeldBy"], {"app": "the usage app", "appName": "func-meternaut-usage-*", "siteOption": "--usage-site"}, "the system-assigned identity of the app holds it too")
        self.assertEqual(w9["identityRemovedBy"], "the Hub action retire-old")
        self.assertEqual((w10["identity"], w10["role"], w10["place"]), ({"name": "id-meternaut-usage"}, "Meternaut usage reader", "centralWorkspace"))
        for item in (w9, w10):
            self.assertNotIn("replacedBy", item, f"{item['id']}: nothing replaces it: the app is gone")
            self.assertIn("2026-11-07", item["why"], item["id"])
            self.assertIn(item["place"], MANIFEST["places"], item["id"])
        self.assertIn("Run this before the Hub action retire-old", w9["why"], "the identity and the app are read, and the Hub action deletes both")
        self.assertIn("then the role itself", w10["why"], "the custom role is gone whole, like W7's and W8's")
        self.assertNotIn("Meternaut usage reader", MANIFEST["roles"])
        self.assertNotIn("usage", MANIFEST["identities"])
        self.assertIn("workspace", MANIFEST["places"]["centralWorkspace"], "the place is the workspace and the resource group that holds it, where the role was defined")
        self.assertNotIn("roleStays", {k for r in MANIFEST["retired"] if r["id"] != "W9" for k in r})

    def test_the_loader_refuses_the_two_new_kinds_of_retired_item_when_they_make_no_sense(self):
        for change, word in (
            (lambda d: [r for r in d["retired"] if r["id"] == "W9"][0].update(roleStays=False), "roleStays is true"),
            (lambda d: [r for r in d["retired"] if r["id"] == "W9"][0].update(role="Meternaut usage reader"), "built-in role"),
            (lambda d: [r for r in d["retired"] if r["id"] == "W9"][0].update(replacedBy="R1"), "two kinds of item"),
            (lambda d: [r for r in d["retired"] if r["id"] == "W9"][0].update(alsoHeldBy={"app": "the usage app"}), "alsoHeldBy names the app"),
            (lambda d: [r for r in d["retired"] if r["id"] == "W9"][0]["alsoHeldBy"].update(siteOption="--other-site"), "alsoHeldBy names the app"),
            (lambda d: [r for r in d["retired"] if r["id"] == "W10"][0].update(alsoHeldBy={"app": "a", "appName": "b-*", "siteOption": "--usage-site"}), "belongs to an item with roleStays"),
        ):
            self.assertIn(word, self.broken(change, real=True), word)

    def test_the_deployment_identitys_role_in_the_gateways_group_is_retired_whole_and_is_not_looked_up(self):
        self.assertNotIn(DEPLOYER, MANIFEST["roles"])
        self.assertNotIn(DEPLOYER, [g["role"] for g in MANIFEST["grants"]])
        item = next(r for r in MANIFEST["retired"] if r["id"] == "W8")
        self.assertEqual((item["role"], item["place"], item["identity"]), (DEPLOYER, "gatewayGroup", {"name": "meternaut-deploy-sc-uami", "lookup": False}))
        self.assertNotIn("replacedBy", item, "it is retired whole: every assignment of the role, whoever holds it, and then the role")
        self.assertIn("2026-11-07", item["why"])
        self.assertIn("it is not looked up", item["why"], "the deployment identity lives in the bootstrap group: a lookup in the project's group would say that it does not exist")
        self.assertEqual([r["id"] for r in MANIFEST["retired"] if r["identity"].get("lookup") is False], ["W8"], "no other item turns the lookup off")

    def test_whether_an_identity_is_looked_up_is_true_or_false_and_a_grant_that_something_replaces_is_always_looked_up(self):
        self.assertIn("lookup is true or false", self.broken(lambda d: d["retired"][-1]["identity"].update(lookup="no")))
        self.assertIn("is not one that a grant replaces", self.broken(lambda d: d["retired"][1]["identity"].update(lookup=False)))

    def test_a_retired_item_must_be_complete_and_must_not_be_a_current_grant(self):
        def as_holder(document):
            document["identities"]["cases"]["holders"].append({"kind": "user", "name": RETIRED_IDENTITY})

        for change, word in (
            (lambda d: d["retired"][0].update(id="R1"), "R1"),
            (lambda d: d["retired"][0].update(role="Reader"), "not a role of the file"),
            (as_holder, "not an identity of the file"),
            (lambda d: d["retired"][0].update(identity="id-meternaut-runner"), "an object with a name"),
            (lambda d: d["retired"][0].update(identity={}), "an object with a name"),
            (lambda d: d["retired"][0].update(place="nowhere"), "W1"),
            (lambda d: d["retired"][0].update(why=""), "W1"),
            (lambda d: d["retired"].append(dict(d["retired"][0])), "used once"),
            (lambda d: d.update(retired="W1"), "retired is a list"),
        ):
            self.assertIn(word, self.broken(change))

    def test_the_grant_of_an_identity_that_an_app_no_longer_runs_as_is_checked_against_the_grant_that_replaces_it(self):
        def holder_again(document):
            document["identities"]["cases"]["holders"].append({"kind": "user", "name": "id-meternaut-cases"})

        for change, word in (
            (lambda d: d["retired"][1].update(replacedBy="R9"), "replacedBy is the id of a grant"),
            (lambda d: d["retired"][1].update(role="Cost Management Reader"), "those of the grant that replaces it, R1"),
            (lambda d: d["retired"][1].update(place="gatewayInsights"), "those of the grant that replaces it, R1"),
            (lambda d: d["retired"][1].update(place="nowhere"), "W2"),
            (holder_again, "not an identity of the file"),
            (lambda d: d["retired"][1].update(identity={"name": "bad name"}), "an object with a name"),
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

    def test_the_estate_is_the_tenant_root_management_group_or_each_subscription_and_the_roles_of_the_reader_cover_the_list_of_subscriptions(self):
        # The owner's order of 2026-11-07: the Watch reads every subscription that its identity can read, so the grant is made once at the group above them.
        place = MANIFEST["places"]["estate"]
        for words in ("tenant root management group", "every subscription that its identity can read", "SCOPE_ALL_SUBSCRIPTIONS", "each subscription", "SCOPE_SUBSCRIPTIONS", "fallback"):
            self.assertIn(words, place)
        grants = {g["id"]: g for g in MANIFEST["grants"]}
        for grant_id in ("R1", "R2"):
            self.assertEqual(grants[grant_id]["place"], "estate", grant_id)
            self.assertIn("tenant root management group or each subscription", grants[grant_id]["why"], grant_id)
        self.assertEqual(grants["R1"]["calls"][0], "subscriptions-list", "the list of the subscriptions that the identity can read is a read of the Reader")
        self.assertEqual(grants["R1"]["role"], "Reader")
        self.assertNotIn("subscriptions-list", grants["R2"]["calls"])
        self.assertIn("tenant root management group", MANIFEST["about"])
        self.assertNotRegex(json.dumps(MANIFEST), r"/providers/Microsoft\.Management/managementGroups/[0-9a-fA-F]{8}-", "no management group of a real tenant")


class TheTable(unittest.TestCase):
    PROPOSAL = (ROOT / "docs" / "proposals" / "03-access-and-onboarding.md")

    def test_one_row_for_each_requirement(self):
        rows = ar.markdown(MANIFEST).splitlines()
        self.assertEqual(len(rows), 2 + len(MANIFEST["grants"]))
        self.assertTrue(rows[0].startswith("| # | Identity | Role | Where | What it is for |"))
        self.assertEqual([row.split(" | ")[0] for row in rows[2:]], ["| R1", "| R2"])
        self.assertNotIn("key reader", "\n".join(rows))
        self.assertNotIn("usage", "\n".join(rows), "the usage app and its two reads were retired on 2026-11-07")

    def test_a_row_names_the_holder_of_its_identity(self):
        rows = ar.markdown(MANIFEST).splitlines()[2:]
        cases = "The system-assigned identity of the cases app (`func-meternaut-cases-*`)"
        for row, number in zip(rows, ("R1", "R2")):
            self.assertTrue(row.startswith(f"| {number} | {cases} | "), row[:120])
        self.assertNotIn("user-assigned", "\n".join(rows))

    def test_the_proposal_shows_exactly_this_table(self):
        text = self.PROPOSAL.read_text(encoding="utf-8")
        match = re.search(r"<!-- access-requirements:start -->\n(.*?)\n<!-- access-requirements:end -->", text, re.S)
        self.assertIsNotNone(match, "the proposal has no marked table")
        self.assertEqual(match.group(1), ar.markdown(MANIFEST), "run: python tools/access-requirements.py markdown, and paste it between the markers")

    def test_the_command_prints_it(self):
        code, out, _, _ = run(["markdown"], FakeAz(), real=True)
        self.assertEqual((code, out), (0, ar.markdown(MANIFEST)))

    def test_no_row_of_the_table_says_that_a_role_changes_azure(self):
        self.assertNotIn("changes Azure", ar.markdown(MANIFEST))
        self.assertNotIn("W1", ar.markdown(MANIFEST))

    def test_one_row_for_each_retired_item_and_the_proposal_shows_exactly_this_table_too(self):
        rows = ar.markdown_retired(MANIFEST).splitlines()
        self.assertEqual(len(rows), 2 + len(MANIFEST["retired"]))
        self.assertTrue(rows[0].startswith("| # | Identity | Role | Where | Why it is retired |"))
        self.assertTrue(rows[2].startswith(f"| W1 | `{RETIRED_IDENTITY}` | {RETIRED_ROLE} (custom role) | "))
        self.assertTrue(rows[3].startswith("| W2 | `id-meternaut-cases` | Reader | "), "a built-in role is not a custom role")
        self.assertTrue(rows[5].startswith("| W7 | `id-meternaut-cases` | Meternaut gateway key reader (custom role) | The resource group of the owner's API Management instance"))
        self.assertTrue(rows[6].startswith(f"| W8 | `{DEPLOYER_IDENTITY}` | {DEPLOYER} (custom role) | The resource group of the owner's API Management instance"))
        self.assertTrue(rows[7].startswith("| W9 | `id-meternaut-usage` and the system-assigned identity of the usage app (`func-meternaut-usage-*`) | Monitoring Reader | "
                                           "The old gateway's Application Insights component | "), "a built-in role again, and the app's own identity is named too")
        self.assertTrue(rows[8].startswith("| W10 | `id-meternaut-usage` | Meternaut usage reader (custom role) | The central workspace that the component writes to, and the resource group that holds it | "))
        self.assertNotIn("| W4 |", "\n".join(rows), "the old grant of the key reader is folded into W7")
        self.assertNotIn("| W5 |", "\n".join(rows), "the grants of the usage app's user-assigned identity are folded into W9 and W10")
        text = self.PROPOSAL.read_text(encoding="utf-8")
        match = re.search(r"<!-- access-retired:start -->\n(.*?)\n<!-- access-retired:end -->", text, re.S)
        self.assertIsNotNone(match, "the proposal has no marked table of the retired grants")
        self.assertEqual(match.group(1), ar.markdown_retired(MANIFEST), "run: python tools/access-requirements.py markdown --retired, and paste it between the markers")

    def test_the_command_prints_the_retired_table_with_an_option(self):
        code, out, _, _ = run(["markdown", "--retired"], FakeAz(), real=True)
        self.assertEqual((code, out), (0, ar.markdown_retired(MANIFEST)))


class TheCallsOfTheApp(unittest.TestCase):
    """Every call that the app makes with the identities that it holds is a line of the file, and every call in the file is made. There are two lists of
    such calls: the Watch's (its HTTP client) and the timer's (the reads that check a change afterwards). A change is made with the token of the person
    who approved it and is no requirement of an identity of Meternaut."""

    NAMES = {
        "resource-graph-query": lambda m, p: m == "POST" and "ResourceGraph" in p,
        "cost-management-query": lambda m, p: m == "POST" and "CostManagement" in p,
        "log-analytics-query": lambda m, p: m == "POST" and p.startswith("https://api.loganalytics.azure.com/v1/workspaces/") and p.endswith("/query"),
        "advisor-read": lambda m, p: m == "GET" and "Advisor" in p,
        "locks-read": lambda m, p: m == "GET" and "Authorization" in p and "locks" in p,
        "metric-definitions-read": lambda m, p: m == "GET" and "Microsoft.Insights/metricDefinitions" in p,
        "metrics-read": lambda m, p: m == "GET" and "Microsoft.Insights/metrics" in p,
        "security-pricings-read": lambda m, p: m == "GET" and "Microsoft.Security/pricings" in p,
        "workspace-read": lambda m, p: m == "GET" and re.search(r"Microsoft\.OperationalInsights/workspaces/[^/]+$", p) is not None,
        "workspace-tables-read": lambda m, p: m == "GET" and "Microsoft.OperationalInsights/workspaces/" in p and p.endswith("/tables"),
        "saved-searches-read": lambda m, p: m == "GET" and "Microsoft.OperationalInsights/workspaces/" in p and p.endswith("/savedSearches"),
        "sentinel-rules-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.SecurityInsights/alertRules"),
        "workbooks-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Insights/workbooks"),
        "diagnostic-settings-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Insights/diagnosticSettings"),
        "deployments-read": lambda m, p: m == "GET" and "Microsoft.CognitiveServices/accounts/" in p and p.endswith("/deployments"),
        "activity-log-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Insights/eventtypes/management/values"),
        "benefit-recommendations-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.CostManagement/benefitRecommendations"),
        "reservation-recommendations-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Consumption/reservationRecommendations"),
        "disk-read": lambda m, p: m == "GET" and "Microsoft.Compute/disks" in p,
        "public-ip-read": lambda m, p: m == "GET" and "Microsoft.Network/publicIPAddresses" in p,
        # The reads that the families of change make (cases/families/calls.py): the resource that a plan is about, in the project's own group, and the sizes and the quota of a machine.
        "vm-read": lambda m, p: m == "GET" and "Microsoft.Compute/virtualMachines/" in p and not p.endswith("/vmSizes"),
        "vm-sizes-read": lambda m, p: m == "GET" and "Microsoft.Compute/virtualMachines/" in p and p.endswith("/vmSizes"),
        "snapshot-read": lambda m, p: m == "GET" and "Microsoft.Compute/snapshots" in p,
        "network-interface-read": lambda m, p: m == "GET" and "Microsoft.Network/networkInterfaces" in p,
        "nat-gateway-read": lambda m, p: m == "GET" and "Microsoft.Network/natGateways" in p,
        "load-balancer-read": lambda m, p: m == "GET" and "Microsoft.Network/loadBalancers" in p,
        "private-endpoint-read": lambda m, p: m == "GET" and "Microsoft.Network/privateEndpoints" in p,
        "compute-usage-read": lambda m, p: m == "GET" and "Microsoft.Compute/locations/" in p and p.endswith("/usages"),
        "subscriptions-list": lambda m, p: m == "GET" and p.endswith("/subscriptions"),
        "price-sheet-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Consumption/pricesheets/default"),
        "billing-accounts-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Billing/billingAccounts"),
        "reservation-orders-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.Capacity/reservationOrders"),
        "savings-plan-orders-read": lambda m, p: m == "GET" and p.endswith("/providers/Microsoft.BillingBenefits/savingsPlanOrders"),
    }
    # Every model call goes to the AI Gateway, with the app's identity: the AI Gateway Models User role that the gateway's template assigns inside the project's own group, no line of this file.
    NO_AZURE_ROLE: set = set()

    @staticmethod
    def watch_calls():
        return cases_http.allowed_calls()

    @staticmethod
    def timer_calls():
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import runner
            from cases.families.gates import ChangeScope
        finally:
            sys.path.remove(app)
        return runner.read_calls((ChangeScope(PROJECT, "rg-project"),))

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
        found = {c for g in MANIFEST["grants"] if not ids or g["id"] in ids for c in g.get("calls", [])}
        if not ids:
            found |= {c for item in MANIFEST.get("tenantReads", []) for c in item["calls"]}  # the reads at the tenant or a billing scope, which a person gives (T1 to T3)
        return found

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
        self.assertLessEqual({"disk-read", "public-ip-read", "vm-read", "vm-sizes-read", "snapshot-read", "network-interface-read", "nat-gateway-read", "load-balancer-read",
                              "private-endpoint-read", "compute-usage-read"}, set(r1["calls"]))

    def test_the_calls_in_the_file_are_the_calls_of_the_watch_and_of_the_timer_and_no_other(self):
        names = set(self.names_of(self.watch_calls(), "the Watch")) | set(self.names_of(self.timer_calls(), "the timer"))
        self.assertEqual(sorted(names - self.NO_AZURE_ROLE), sorted(self.listed()), "the calls of the app and the calls in the requirements differ")

    def test_the_watch_makes_no_write_call_with_its_own_identities(self):
        # A change to Azure is made with the token of the person who approved it, from a list of its own: this list is the one of the app's identities.
        allowed = self.watch_calls()
        self.assertEqual({method for method, _ in allowed}, {"GET", "POST"})
        for method, pattern in allowed:
            if method == "POST":
                text = pattern.pattern.replace("\\", "")
                self.assertTrue(any(word in text for word in ("ResourceGraph", "CostManagement", "https://api.loganalytics.azure.com/v1/workspaces/")), pattern.pattern)
        for method, pattern in allowed:
            for word in ("listSecrets", "listKeys", "ApiManagement", "chat/completions"):
                self.assertNotIn(word, pattern.pattern, f"{method}: the Watch's own list holds no key read, no call to the gateway and no model call")

    def test_the_calls_to_the_foundry_project_need_no_line_of_this_file_and_hold_the_only_writes_of_the_list(self):
        # The agents and the conversations are written with the identity's Foundry User role on the project, which the Foundry template assigns inside the project's own group.
        # The role covers no chat completion: the Detective and the Skeptic call the AI Gateway (every model call goes through it, AGENTS.md rule 15 (c)), and no call to the Foundry resource or project may be a chat completion.
        endpoint = "https://example.services.ai.azure.com/api/projects/meternaut"
        base = self.watch_calls()
        calls = cases_http.allowed_calls(endpoint)
        self.assertEqual(calls[:len(base)], base)
        extra = calls[len(base):]
        self.assertTrue(extra)
        for method, pattern in extra:
            self.assertTrue(pattern.pattern.startswith(re.escape(endpoint)), pattern.pattern)
            self.assertEqual([n for n, test in self.NAMES.items() if test(method, pattern.pattern.replace("\\", ""))], [], pattern.pattern)
        self.assertEqual({method for method, _ in extra}, {"GET", "POST", "DELETE"})
        self.assertEqual([(m, p.pattern) for m, p in calls if m == "DELETE"],
                         [("DELETE", re.escape(endpoint) + r"/openai/v1/conversations/conv_[A-Za-z0-9_-]{1,100}")], "the one delete is the app's own conversation")
        self.assertEqual([(m, p.pattern) for m, p in extra if "chat/completions" in p.pattern], [], "no chat completion of the Foundry resource or project is allowed")

    def test_the_one_call_to_the_ai_gateway_is_a_post_that_needs_no_line_of_this_file(self):
        # The token is for the gateway's own audience and the role is assigned by the gateway's template, inside the project's own group (AGENTS.md rule 24).
        host = "aigw-example-0123abcd.example-01.ai.gateway.azure.com"
        base = self.watch_calls()
        calls = cases_http.allowed_calls(None, host)
        self.assertEqual(calls[:len(base)], base)
        extra = calls[len(base):]
        self.assertEqual([(m, p.pattern) for m, p in extra], [("POST", re.escape(f"https://{host}/default/models/openai/v1/chat/completions"))])
        for method, pattern in extra:
            self.assertEqual([n for n, test in self.NAMES.items() if test(method, pattern.pattern.replace("\\", ""))], [], pattern.pattern)

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

    def test_the_deeper_reads_of_the_investigators_tools_are_gets_but_one_and_belong_to_the_reader_or_the_cost_management_reader(self):
        # What a workspace keeps, the deployments of an account, diagnostic settings and the Activity Log are read with Reader (*/read); the purchase recommendations are read with
        # Cost Management Reader (Microsoft.CostManagement/*/read, Microsoft.Consumption/*/read). The one POST is the query API of a workspace, which reads and writes nothing.
        reader = {"workspace-read", "workspace-tables-read", "saved-searches-read", "sentinel-rules-read", "log-analytics-query", "workbooks-read", "diagnostic-settings-read",
                  "deployments-read", "activity-log-read"}
        cost = {"benefit-recommendations-read", "reservation-recommendations-read"}
        methods = {}
        for method, pattern in self.watch_calls():
            text = pattern.pattern.replace("\\", "")
            for name in reader | cost:
                if self.NAMES[name](method, text):
                    methods[name] = method
        self.assertEqual(methods, {name: ("POST" if name == "log-analytics-query" else "GET") for name in reader | cost})
        grants = {g["id"]: g for g in MANIFEST["grants"]}
        self.assertEqual((grants["R1"]["role"], reader <= set(grants["R1"]["calls"])), ("Reader", True))
        self.assertEqual((grants["R2"]["role"], cost <= set(grants["R2"]["calls"])), ("Cost Management Reader", True))
        self.assertFalse((reader | cost) & (set(grants["R1"]["calls"]) & set(grants["R2"]["calls"])))
        self.assertFalse(cost & set(grants["R1"]["calls"]))
        self.assertFalse(reader & set(grants["R2"]["calls"]))

    def test_the_query_api_of_a_workspace_is_asked_by_the_id_of_the_workspace_only_and_on_one_host(self):
        (pattern,) = [p for m, p in self.watch_calls() if m == "POST" and self.NAMES["log-analytics-query"](m, p.pattern.replace("\\", ""))]
        guid = "0a1b2c3d-1111-2222-3333-444455556666"
        self.assertTrue(pattern.fullmatch(f"https://api.loganalytics.azure.com/v1/workspaces/{guid}/query"))
        for bad in (f"https://api.loganalytics.io/v1/workspaces/{guid}/query", f"https://api.loganalytics.azure.com.evil.example/v1/workspaces/{guid}/query",
                    f"https://api.loganalytics.azure.com/v1/workspaces/{guid}/query?x=1", "https://api.loganalytics.azure.com/v1/workspaces/DefaultWorkspace/query",
                    f"https://api.loganalytics.azure.com/v1/workspaces/{guid}/metadata", f"https://api.loganalytics.azure.com/v1/workspaces/{guid}/query/../x"):
            self.assertFalse(pattern.fullmatch(bad), bad)

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
        self.assertIn("4 of 4 present.", out)
        self.assertIn("signed in as operator@example.com", out)
        self.assertEqual(fake.writes(), [])

    def test_check_does_not_look_for_what_is_retired_and_does_not_read_the_user_assigned_identities_at_all(self):
        fake = FakeAz().leave_the_writer()
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual((code, "4 of 4 present." in out), (0, True))
        self.assertNotIn("W1", out)
        self.assertNotIn(RETIRED_ROLE, out)
        self.assertNotIn("id-meternaut", out)
        self.assertNotIn("key reader", out)
        self.assertFalse([c for c in fake.calls if RETIRED_IDENTITY in c or RETIRED_ROLE in c])
        self.assertEqual([c for c in fake.calls if c[:2] == ["identity", "show"]], [], "no app runs as a user-assigned identity that needs a role")

    def test_a_second_subscription_that_has_no_grant_is_missing(self):
        code, out, _, _ = run(["check", *PLACES, "--estate", ESTATE, "--estate", f"/subscriptions/{SECOND}", "--only", "R1,R2"], FakeAz())
        self.assertEqual(code, 1)
        self.assertEqual(len(re.findall(r"MISSING", out)), 2)
        self.assertIn(f"Reader  at /subscriptions/{SECOND}", out)
        self.assertIn("2 of 4 present.", out)

    def test_a_grant_at_a_management_group_counts_for_the_subscriptions_below_it(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if a["scope"] != ESTATE]
        fake.grant(NEW_CASES, BUILTIN["Reader"], MANAGEMENT_GROUP)
        fake.grant(NEW_CASES, BUILTIN["Cost Management Reader"], MANAGEMENT_GROUP)
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual((code, "4 of 4 present." in out), (0, True))

    def test_the_estate_may_be_a_management_group_such_as_the_tenant_root_and_only_a_grant_at_it_counts(self):
        # The Watch reads every subscription that its identity can read: a person gives R1 and R2 once, at the group above the subscriptions, and that is the one place to check.
        fake = FakeAz()
        argv = ["check", *PLACES, "--estate", MANAGEMENT_GROUP, "--only", "R1,R2"]
        code, out, _, _ = run(argv, fake)
        self.assertEqual((code, out.count("MISSING"), "0 of 2 present." in out), (1, 2, True), "the grants on the pilot subscription are below the group, and a grant below the place does not count")
        self.assertIn(f"Reader  at {MANAGEMENT_GROUP}", out)
        self.assertIn(f"Cost Management Reader  at {MANAGEMENT_GROUP}", out)
        fake.grant(NEW_CASES, BUILTIN["Reader"], MANAGEMENT_GROUP)
        fake.grant(NEW_CASES, BUILTIN["Cost Management Reader"], MANAGEMENT_GROUP)
        code, out, _, _ = run(argv, fake)
        self.assertEqual((code, "2 of 2 present." in out), (0, True))
        self.assertEqual(fake.writes(), [], "check reads and writes nothing")
        asked = [c for c in fake.calls if c[0] == "rest" and f"{ar.ARM}{MANAGEMENT_GROUP}/providers/Microsoft.Authorization/roleAssignments" in " ".join(c)]
        self.assertTrue(asked, "the assignments are read at the group")

    def test_a_management_group_is_written_in_full_and_a_name_that_is_not_one_is_refused(self):
        for bad in ("landing-zones", "/managementGroups/landing-zones", "/providers/Microsoft.Management/managementGroups/", "/providers/Microsoft.Management/managementGroups/a b"):
            code, _, err, _ = run(["check", *PLACES, "--estate", bad], FakeAz())
            self.assertEqual(code, 1, bad)
            self.assertIn("--estate holds", err)

    def test_a_grant_on_something_below_the_place_does_not_count(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if not (a["scope"] == ESTATE and a["role_id"] == BUILTIN["Reader"])]
        fake.grant(NEW_CASES, BUILTIN["Reader"], f"{ESTATE}/resourceGroups/rg-one")
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual((code, "MISSING" in out), (1, True))

    def test_a_grant_to_another_identity_does_not_count(self):
        fake = FakeAz()
        fake.assignments = [dict(a, principal="somebody-else") if a["scope"] == ESTATE else a for a in fake.assignments]
        code, out, _, _ = run(["check", *PLACES, "--only", "R1,R2"], fake)
        self.assertEqual((code, out.count("MISSING")), (1, 2))

    def test_a_grant_that_only_the_user_assigned_identity_still_holds_does_not_count(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if not (a["principal"] == NEW_CASES and a["role_id"] == BUILTIN["Reader"])]
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +R1  {CASES_SITE} \(system-assigned\)  Reader  at {re.escape(ESTATE)}")
        self.assertIn("0 of 1 present.", out)

    def test_the_system_assigned_identity_is_found_by_reading_the_app_in_the_project_group_and_nothing_is_written(self):
        fake = FakeAz()
        run(["check", *PLACES, "--only", "R1,R4"], fake)
        reads = [c for c in fake.calls if c[0] == "rest" and "Microsoft.Web/sites" in c[c.index("--url") + 1]]
        self.assertEqual([c[c.index("--url") + 1] for c in reads],
                         [f"{ar.ARM}{PROJECT_GROUP}/providers/Microsoft.Web/sites/{CASES_SITE}?api-version=2024-04-01",
                          f"{ar.ARM}{PROJECT_GROUP}/providers/Microsoft.Web/sites/{USAGE_SITE}?api-version=2024-04-01"], "each app once, however many requirements it has")
        self.assertEqual({c[c.index("--method") + 1] for c in reads}, {"get"})
        listed = " ".join(c[c.index("--url") + 1] for c in fake.calls if c[0] == "rest" and "roleAssignments" in c[c.index("--url") + 1])
        for principal in (NEW_CASES, NEW_USAGE):
            self.assertIn(f"principalId eq '{principal}'", listed)
        for principal in (OLD_CASES, OLD_USAGE):
            self.assertNotIn(principal, listed)
        self.assertEqual(fake.writes(), [])

    def test_an_app_without_a_system_assigned_identity_is_cannot_yet_and_says_which_action_makes_it(self):
        fake = FakeAz()
        fake.sites[CASES_SITE] = None
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"cannot yet +R1  {CASES_SITE} \(system-assigned\)  Reader  at {re.escape(ESTATE)}")
        self.assertIn(f"{CASES_SITE} has no system-assigned identity yet: the Hub action cases makes it", out)
        self.assertIn("0 of 1 present.", out)

    def test_an_app_that_does_not_exist_yet_is_cannot_yet_too(self):
        fake = FakeAz()
        del fake.sites[USAGE_SITE]
        code, out, _, _ = run(["check", *PLACES, "--only", "R4"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"{USAGE_SITE} does not exist yet: the Hub action recording makes it", out)
        self.assertIn("0 of 1 present.", out)

    def test_an_app_whose_identity_block_holds_no_object_id_is_without_an_identity(self):
        group = PROJECT_GROUP
        for answer in ('{"name": "x"}', '{"identity": null}', '{"identity": {"type": "None"}}', '{"identity": {"type": "UserAssigned", "principalId": "p"}}',
                       '{"identity": {"type": "SystemAssigned", "principalId": ""}}', '{"identity": {"type": "SystemAssigned"}}', "null"):
            principal, why = ar.system_principal_of(ar.Az(lambda args, answer=answer: (0, answer, "")), group, CASES_SITE)
            self.assertEqual((principal, why), (None, "has no system-assigned identity yet"), answer)
        principal, why = ar.system_principal_of(ar.Az(lambda args: (0, '{"identity": {"type": "systemassigned, userassigned", "principalId": " p1 "}}', "")), group, CASES_SITE)
        self.assertEqual((principal, why), ("p1", ""))

    def test_an_app_that_cannot_be_read_stops_the_check_with_the_reason(self):
        fake = FakeAz()
        fake.site_error = "ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Web/sites/read'"
        code, out, err, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"the app {CASES_SITE} could not be read", err)
        self.assertIn("AuthorizationFailed", err)
        fake = FakeAz()

        def not_json(args):
            if args[0] == "rest" and "Microsoft.Web/sites" in args[args.index("--url") + 1]:
                return 0, "this is not json", ""
            return fake(args)

        code, _, err, _ = run(["check", *PLACES, "--only", "R1"], not_json)
        self.assertEqual(code, 1)
        self.assertIn("the answer is not JSON", err)

    def test_the_name_of_an_app_is_needed_only_by_the_requirements_of_that_app(self):
        fake = FakeAz()
        code, out, _, _ = run(["check", "--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway-insights", INSIGHTS, "--usage-site", USAGE_SITE,
                               "--only", "R4,R5"], fake)
        self.assertEqual((code, "2 of 2 present." in out), (0, True))
        self.assertFalse([c for c in fake.calls if CASES_SITE in " ".join(c)], "the cases app is not read for the requirements of the usage app")
        code, _, err, _ = run(["check", "--project-subscription", PROJECT, "--project-group", "rg-project", "--usage-site", USAGE_SITE, "--only", "R1"], FakeAz())
        self.assertEqual(code, 1)
        self.assertIn("--cases-site is not set: it is the name of the cases app (func-meternaut-cases-*), whose system-assigned identity holds these grants", err)
        code, _, err, _ = run(["check", "--project-subscription", PROJECT, "--project-group", "rg-project", "--cases-site", CASES_SITE, "--gateway-insights", INSIGHTS,
                               "--only", "R4"], FakeAz())
        self.assertEqual(code, 1)
        self.assertIn("--usage-site is not set: it is the name of the usage app (func-meternaut-usage-*), whose system-assigned identity holds these grants", err)

    def test_the_names_of_the_apps_come_from_the_settings_of_the_workflow_too_and_an_option_wins(self):
        env = {"ACCESS_CASES_SITE": CASES_SITE, "ACCESS_USAGE_SITE": USAGE_SITE}
        code, out, _, _ = run(["check", "--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway", APIM, "--gateway-insights", INSIGHTS], FakeAz(), env=env)
        self.assertEqual((code, "4 of 4 present." in out), (0, True))
        fake = FakeAz()
        fake.sites["func-meternaut-cases-other"] = None
        code, out, _, _ = run(["check", *PLACES, "--cases-site", "func-meternaut-cases-other", "--only", "R1"], fake, env=env)
        self.assertEqual(code, 1)
        self.assertIn("func-meternaut-cases-other has no system-assigned identity yet", out)
        self.assertNotIn(f"{CASES_SITE} (system-assigned)", out)

    def test_a_custom_role_that_can_do_more_than_the_file_says_is_reported(self):
        fake = FakeAz()
        fake.roles["Meternaut usage reader"]["permissions"][0]["actions"].append("Microsoft.OperationalInsights/workspaces/write")
        code, out, _, _ = run(["check", *PLACES, "--only", "R5"], fake)
        self.assertEqual(code, 1)
        self.assertIn("role differs", out)
        self.assertIn("Microsoft.OperationalInsights/workspaces/write", out)

    def test_a_custom_role_that_can_be_assigned_in_more_places_than_the_file_says_is_reported(self):
        fake = FakeAz()
        fake.roles["Meternaut usage reader"]["assignableScopes"].append(f"/subscriptions/{WORKSPACE_SUB}")
        code, out, _, _ = run(["check", *PLACES, "--only", "R5"], fake)
        self.assertEqual((code, "role differs" in out), (1, True))

    def test_a_custom_role_that_does_not_exist_is_missing(self):
        fake = FakeAz()
        del fake.roles["Meternaut usage reader"]
        code, out, _, _ = run(["check", *PLACES, "--only", "R5"], fake)
        self.assertEqual(code, 1)
        self.assertIn("MISSING", out)
        self.assertIn("the custom role does not exist yet", out)

    def test_a_user_assigned_identity_that_is_gone_does_not_matter_to_check(self):
        fake = FakeAz()
        del fake.identities["id-meternaut-cases"]
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], fake)
        self.assertEqual((code, "1 of 1 present." in out), (0, True))

    def test_the_workspace_is_read_from_the_gateways_component_when_it_is_not_given(self):
        fake = FakeAz()
        run(["check", *PLACES, "--only", "R5"], fake)
        self.assertTrue(any(c[0] == "rest" and f"{INSIGHTS}?api-version={ar.INSIGHTS_API}" in c[c.index("--url") + 1] for c in fake.calls))
        fake = FakeAz()
        run(["check", *PLACES, "--workspace", WORKSPACE, "--only", "R5"], fake)
        self.assertFalse(any(c[0] == "rest" and INSIGHTS in c[c.index("--url") + 1] and "roleAssignments" not in c[c.index("--url") + 1] for c in fake.calls))

    def test_the_settings_of_the_workflow_are_read_from_the_environment(self):
        env = {"ENV_SUBSCRIPTION_ID": PROJECT, "ENV_RESOURCE_GROUP": "rg-project", "ACCESS_GATEWAY_ID": APIM, "ACCESS_GATEWAY_INSIGHTS_ID": INSIGHTS,
               "ACCESS_ESTATE_SCOPES": f"{ESTATE}, /subscriptions/{SECOND}", "ACCESS_CASES_SITE": CASES_SITE}
        code, out, _, _ = run(["check", "--only", "R1"], FakeAz(), env=env)
        self.assertEqual((code, "1 of 2 present." in out), (1, True))

    def test_without_an_estate_the_project_subscription_is_the_estate(self):
        code, out, _, _ = run(["check", *PLACES, "--only", "R1"], FakeAz())
        self.assertIn(f"at {ESTATE}", out)

    def test_a_missing_or_wrong_place_is_named(self):
        for argv, word in ((["retire", "--project-subscription", PROJECT, "--project-group", "rg-project", *SITES, "--only", "W7"], "--gateway"),
                           (["check", "--project-subscription", PROJECT, "--project-group", "rg-project", *SITES, "--only", "R4"], "--gateway-insights"),
                           (["check", "--only", "R1"], "--project-subscription"),
                           (["check", "--project-subscription", PROJECT, "--only", "R1"], "--project-group"),
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
        self.assertIn("5 change(s) would be made, and nothing else", out)
        self.assertEqual(fake.writes(), [])
        for principal in (NEW_CASES, NEW_USAGE):
            self.assertIn(f"az role assignment create --assignee-object-id {principal} --assignee-principal-type ServicePrincipal", out)
        for principal in (OLD_CASES, OLD_USAGE):
            self.assertNotIn(principal, out, "nothing is granted to a user-assigned identity any more")
        self.assertNotIn(RETIRED_IDENTITY, out)
        self.assertNotIn("delete", out)

    def test_apply_makes_the_missing_custom_roles_first_and_then_every_assignment_and_checks_again(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        writes = fake.writes()
        kinds = [c[:3] for c in writes]
        self.assertEqual(kinds.count(["role", "definition", "create"]), 1)
        self.assertEqual(kinds.count(["role", "assignment", "create"]), 4)
        self.assertEqual(len(kinds), 5, "nothing but makes: grant never removes")
        custom_ids = {r["name"] for r in fake.roles.values()}
        for name in ("Meternaut usage reader",):
            role_id = fake.roles[name]["name"]
            define = next(i for i, c in enumerate(writes) if c[:3] == ["role", "definition", "create"] and name in str(fake.definition_files))
            assign = next(i for i, c in enumerate(writes) if c[:3] == ["role", "assignment", "create"] and c[c.index("--role") + 1] == role_id)
            self.assertLess(define, assign, "a custom role is made before it is assigned")
        self.assertEqual(len(custom_ids), 1)
        self.assertNotIn(KEY_READER, fake.roles, "the key reader is retired and is never made again")
        self.assertTrue(out.rstrip().endswith("4 of 4 present."))
        self.assertIn("Checking again:", out)

    def test_the_system_assigned_identity_of_each_app_gets_exactly_the_requirements_of_its_app(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)

        def held(principal):
            return sorted((a["role_id"], a["scope"]) for a in fake.assignments if a["principal"] == principal)

        self.assertEqual(held(NEW_CASES), sorted([(BUILTIN["Reader"], ESTATE), (BUILTIN["Cost Management Reader"], ESTATE)]), "the cases app is granted no key")
        self.assertEqual(held(NEW_USAGE), sorted([(BUILTIN["Monitoring Reader"], INSIGHTS), (fake.roles["Meternaut usage reader"]["name"], WORKSPACE)]))
        self.assertEqual({a["principal"] for a in fake.assignments}, {NEW_CASES, NEW_USAGE})

    def test_an_app_that_has_no_system_assigned_identity_yet_blocks_only_its_own_grants(self):
        fake = FakeAz(**self.EMPTY)
        fake.sites[CASES_SITE] = None
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"{CASES_SITE} has no system-assigned identity yet: the Hub action cases makes it", out)
        self.assertIn("cannot yet", out)
        assigned = [c[c.index("--assignee-object-id") + 1] for c in fake.writes() if c[:3] == ["role", "assignment", "create"]]
        self.assertEqual(sorted(assigned), [NEW_USAGE, NEW_USAGE], "the other app is complete")

    def test_nothing_is_made_in_the_project_group_and_no_role_that_changes_anything_is_defined(self):
        fake = FakeAz(**self.EMPTY)
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        for call in fake.writes():
            if call[:3] == ["role", "assignment", "create"]:
                self.assertFalse(call[call.index("--scope") + 1].lower().startswith(PROJECT_GROUP.lower()), call)
        for _, content in fake.definition_files:
            self.assertNotIn(PROJECT_GROUP, content["AssignableScopes"])
            self.assertTrue(all(a.endswith("/read") for a in content["Actions"]), content["Name"])

    def test_the_apps_are_read_and_never_changed(self):
        fake = FakeAz(**self.EMPTY)
        run(["grant", *PLACES, "--apply", "--yes"], fake)
        sent = [c for c in fake.calls if "Microsoft.Web" in " ".join(c)]
        self.assertTrue(sent)
        self.assertEqual({tuple(c[:4]) for c in sent}, {("rest", "--method", "get", "--url")})
        self.assertFalse([c for c in fake.calls if c[:2] in (["functionapp", "identity"], ["webapp", "identity"]) or "--body" in c])

    def test_the_definition_that_is_made_holds_exactly_what_the_file_says_and_the_file_is_removed_after(self):
        fake = FakeAz(**self.EMPTY)
        run(["grant", *PLACES, "--apply", "--yes", "--only", "R5"], fake)
        ((path, content),) = fake.definition_files
        spec = OLD["roles"]["Meternaut usage reader"]
        self.assertEqual(content, {"Name": "Meternaut usage reader", "IsCustom": True, "Description": spec["description"], "Actions": spec["actions"],
                                   "NotActions": [], "DataActions": [], "NotDataActions": [], "AssignableScopes": [WORKSPACE_GROUP]})
        self.assertFalse(os.path.exists(path))
        define = [c for c in fake.writes() if c[:3] == ["role", "definition", "create"]][0]
        self.assertEqual(define[define.index("--subscription") + 1], WORKSPACE_SUB)

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
        self.assertEqual((write[write.index("--role") + 1], write[write.index("--scope") + 1], write[write.index("--assignee-object-id") + 1]), (BUILTIN["Reader"], ESTATE, NEW_CASES))

    def test_a_second_estate_gets_its_two_roles(self):
        fake = FakeAz()
        code, out, _, _ = run(["grant", *PLACES, "--estate", ESTATE, "--estate", f"/subscriptions/{SECOND}", "--only", "R1,R2", "--apply", "--yes"], fake)
        self.assertEqual(code, 0)
        made = [(c[c.index("--assignee-object-id") + 1], c[c.index("--role") + 1], c[c.index("--scope") + 1]) for c in fake.writes()]
        self.assertEqual(sorted(made), sorted([(NEW_CASES, BUILTIN["Reader"], f"/subscriptions/{SECOND}"), (NEW_CASES, BUILTIN["Cost Management Reader"], f"/subscriptions/{SECOND}")]))

    def test_a_management_group_as_the_estate_gets_its_two_roles_with_the_exact_commands_and_nothing_else(self):
        # The owner's order of 2026-11-07: the Watch reads the entire estate, so a person grants R1 and R2 once at the tenant root management group (here a group by another name).
        argv = ["grant", *PLACES, "--estate", MANAGEMENT_GROUP, "--only", "R1,R2"]
        fake = FakeAz()
        code, out, _, _ = run(argv, fake)
        self.assertEqual(code, 0)
        self.assertIn("2 change(s) would be made, and nothing else", out)
        self.assertEqual(fake.writes(), [], "a dry run writes nothing")
        for role in ("Reader", "Cost Management Reader"):
            self.assertIn(f"--assignee-object-id {NEW_CASES} --assignee-principal-type ServicePrincipal --role \"{BUILTIN[role]}\" --scope {MANAGEMENT_GROUP}   # {role}", out)
        code, out, _, _ = run([*argv, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        made = [(c[c.index("--assignee-object-id") + 1], c[c.index("--role") + 1], c[c.index("--scope") + 1]) for c in fake.writes()]
        self.assertEqual(sorted(made), sorted([(NEW_CASES, BUILTIN["Reader"], MANAGEMENT_GROUP), (NEW_CASES, BUILTIN["Cost Management Reader"], MANAGEMENT_GROUP)]))
        self.assertTrue(out.rstrip().endswith("2 of 2 present."), "it reads back at the group")
        self.assertEqual({c[:3] for c in map(tuple, fake.writes())}, {("role", "assignment", "create")}, "it only makes assignments: nothing is defined or removed")
        code, out, _, _ = run([*argv, "--apply", "--yes"], fake)
        self.assertEqual((code, "Nothing to grant." in out), (0, True), "a second run has nothing to do")

    def test_a_custom_role_that_differs_is_never_changed(self):
        fake = FakeAz()
        fake.roles["Meternaut usage reader"]["permissions"][0]["actions"].append("Microsoft.OperationalInsights/workspaces/write")
        fake.assignments = [a for a in fake.assignments if a["scope"] != WORKSPACE]
        code, out, _, _ = run(["grant", *PLACES, "--only", "R5", "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertEqual(fake.writes(), [])
        self.assertIn("Nothing can be granted until", out)
        self.assertIn("role differs", out)

    def test_an_app_that_does_not_exist_yet_blocks_its_grants_only(self):
        fake = FakeAz(**self.EMPTY)
        del fake.sites[USAGE_SITE]
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"{USAGE_SITE} does not exist yet: the Hub action recording makes it", out)
        assigned = [c for c in fake.writes() if c[:3] == ["role", "assignment", "create"]]
        self.assertEqual(len(assigned), 2)
        self.assertTrue(all(c[c.index("--assignee-object-id") + 1] == NEW_CASES for c in assigned))

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
        code, out, _, sleeps = run(["grant", *PLACES, "--only", "R5", "--apply", "--yes"], fake)
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
    """What the first version of the console left behind: the writer's role, its assignments (also those of an identity that was deleted) and its identity.
    The user-assigned identities of the two apps hold nothing here (the next class is about them), so their five items are gone."""

    def left(self, **options):
        return FakeAz(old=False).leave_the_writer(**options)

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
        code, out, _, _ = run(["retire", *PLACES, "--only", "W1"], fake)
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
        self.assertTrue(out.rstrip().endswith("7 of 7 gone."))
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
        fake.grant(OLD_CASES, BUILTIN["Reader"], PROJECT_GROUP)
        fake.grant("runner-principal", USAGE_READER_ID, WORKSPACE)
        others = [dict(x) for x in fake.assignments if x["role_id"] != RETIRED_ROLE_ID]
        roles = {name: dict(role) for name, role in fake.roles.items() if name != RETIRED_ROLE}
        code, out, _, _ = run(["retire", *PLACES, "--only", "W1", "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.assignments, others, "every other assignment of every identity is still there")
        self.assertEqual({n: r for n, r in fake.roles.items()}, roles, "every other role is still there")
        self.assertEqual(sorted({tuple(c[:3]) for c in fake.writes()}), [("role", "assignment", "delete"), ("role", "definition", "delete")])
        self.assertEqual(fake.identities, {"id-meternaut-cases": OLD_CASES, "id-meternaut-usage": OLD_USAGE, RETIRED_IDENTITY: "runner-principal"})

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
        fake = FakeAz(old=False)
        code, out, _, _ = run(["retire", *PLACES], fake)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to retire.", out)
        self.assertRegex(out, rf"gone +W1  {RETIRED_IDENTITY}")
        self.assertEqual(len(re.findall(r"^  gone +W\d", out, re.M)), 7)
        self.assertEqual(fake.writes(), [])

    def test_an_identity_that_is_still_there_without_any_role_is_reported_and_there_is_nothing_to_retire(self):
        fake = FakeAz(old=False)
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
        self.assertTrue(out.rstrip().endswith("6 of 7 gone."))

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
        env = {"ENV_SUBSCRIPTION_ID": PROJECT, "ENV_RESOURCE_GROUP": "rg-project", "ACCESS_GATEWAY_ID": APIM, "ACCESS_GATEWAY_INSIGHTS_ID": INSIGHTS}
        code, out, _, _ = run(["retire"], self.left(), env=env)
        self.assertEqual(code, 1)
        self.assertIn(f"at {PROJECT_GROUP}", out)
        self.assertIn(f"at {ESTATE}", out)
        self.assertIn(f"at {INSIGHTS}", out)
        self.assertIn(f"at {GATEWAY_GROUP}", out)
        self.assertNotIn(f"at {PRODUCT}", out, "nothing is looked for on the access product any more: the key reader is retired at the group, whole")
        self.assertIn(f"at {WORKSPACE}", out)

    def test_the_other_places_are_needed_for_the_items_that_name_them_and_not_for_the_others(self):
        code, _, err, _ = run(["retire", "--project-subscription", PROJECT, "--project-group", "rg-project"], self.left())
        self.assertEqual(code, 1)
        self.assertIn("--gateway-insights is not set", err)
        code, _, err, _ = run(["retire", "--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway-insights", INSIGHTS], self.left())
        self.assertEqual(code, 1)
        self.assertIn("--gateway is not set", err, "W7, the key reader, is retired in the resource group of the instance")
        code, out, _, _ = run(["retire", "--project-subscription", PROJECT, "--project-group", "rg-project", "--only", "W1,W2,W3"], self.left())
        self.assertEqual(code, 1, "W1 is still there")
        self.assertRegex(out, r"gone +W2")


class RetireTheOldIdentities(unittest.TestCase):
    """The apps have been flipped: they run as their system-assigned identities, which hold the requirements, and the user-assigned identities of before still hold
    theirs. Retire removes the old ones, those of the identity of each item and nobody else's, and never a role."""

    NO_SITES = ["--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway", APIM, "--gateway-insights", INSIGHTS]
    ITEMS = (("W2", "id-meternaut-cases", "Reader", ESTATE), ("W3", "id-meternaut-cases", "Cost Management Reader", ESTATE),
             ("W5", "id-meternaut-usage", "Monitoring Reader", INSIGHTS), ("W6", "id-meternaut-usage", "Meternaut usage reader", WORKSPACE))
    ONLY = "W2,W3,W5,W6"

    @staticmethod
    def old(fake):
        return [a for a in fake.assignments if a["principal"] in (OLD_CASES, OLD_USAGE)]

    @staticmethod
    def deletes(fake):
        return [c for c in fake.calls if c[:3] == ["role", "assignment", "delete"]]

    def test_a_dry_run_finds_the_assignments_of_the_old_identities_by_their_object_ids_and_removes_nothing(self):
        fake = FakeAz()
        code, out, _, _ = run(["retire", *PLACES, "--only", self.ONLY], fake)
        self.assertEqual(code, 1, "something is left to retire, and a script can tell")
        self.assertEqual(fake.writes(), [])
        self.assertIn("4 change(s) would be made, and nothing else", out)
        self.assertIn("This was a dry run", out)
        for item, identity, role, place in self.ITEMS:
            self.assertRegex(out, rf"still there +{item}  {identity}  {role}  at {re.escape(place)}")
            self.assertIn(f"{identity} holds 1 assignment(s) of {role} at or below this place:", out)
        commands = [line.strip() for line in out.splitlines() if line.strip().startswith("az ")]
        self.assertEqual(len(commands), 4)
        self.assertEqual({command.split("--ids ")[1].split()[0] for command in commands}, {a["id"] for a in self.old(fake)})
        self.assertEqual([c for c in commands if not c.startswith("az role assignment delete")], [], "no role is deleted: the system-assigned identities need them")
        lists = [c[c.index("--url") + 1] for c in fake.calls if c[0] == "rest" and "roleAssignments" in c[c.index("--url") + 1]]
        self.assertTrue(lists)
        self.assertTrue(all("principalId eq '" in url for url in lists), "every list is of one principal: never the assignments of everybody")
        self.assertEqual({c[c.index("--method") + 1] for c in fake.calls if c[0] == "rest"}, {"get"})

    def test_apply_removes_the_assignments_of_the_old_identities_and_nothing_else_and_the_apps_keep_their_access(self):
        fake = FakeAz()
        system = [dict(a) for a in fake.assignments if a["principal"] in (NEW_CASES, NEW_USAGE)]
        roles = {name: dict(role) for name, role in fake.roles.items()}
        identities = dict(fake.identities)
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 4)
        self.assertEqual(self.old(fake), [])
        self.assertEqual(fake.assignments, system, "what the system-assigned identities hold is untouched")
        self.assertEqual(fake.roles, roles, "the custom role stays")
        self.assertEqual(fake.identities, identities, "an identity is never deleted")
        self.assertIn("Checking again:", out)
        self.assertTrue(out.rstrip().endswith("7 of 7 gone."))
        self.assertIn("id-meternaut-cases still exists in", out)
        self.assertIn("never deletes an identity: a person removes it, with `az identity delete`, after this tool has taken away its grants", out)
        code, out, _, _ = run(["check", *PLACES], fake)
        self.assertEqual((code, "4 of 4 present." in out), (0, True))

    def test_the_assignments_of_anybody_else_of_the_same_roles_at_the_same_places_stay(self):
        fake = FakeAz()
        for role, scope in ((BUILTIN["Reader"], ESTATE), (BUILTIN["Cost Management Reader"], ESTATE), (BUILTIN["Monitoring Reader"], INSIGHTS), (USAGE_READER_ID, WORKSPACE)):
            fake.grant("somebody-else", role, scope)
            fake.grant("a-deleted-identity", role, scope)
        others = [dict(a) for a in fake.assignments if a["principal"] in ("somebody-else", "a-deleted-identity")]
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([a for a in fake.assignments if a["principal"] in ("somebody-else", "a-deleted-identity")], others)
        self.assertEqual(len(self.deletes(fake)), 4)

    def test_a_second_run_has_nothing_to_retire_and_needs_no_name_of_an_app(self):
        fake = FakeAz()
        run(["retire", *PLACES, "--apply", "--yes"], fake)
        before = len(fake.writes())
        for argv in (["retire", *PLACES, "--apply", "--yes"], ["retire", *PLACES], ["retire", *self.NO_SITES]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual((code, len(fake.writes()), "Nothing to retire." in out), (0, before, True), argv)

    def test_a_grant_is_kept_while_the_grant_that_replaces_it_is_not_present_for_the_system_assigned_identity(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if not (a["principal"] == NEW_CASES and a["role_id"] == BUILTIN["Reader"])]
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"kept +W2  id-meternaut-cases  Reader  at {re.escape(ESTATE)}")
        self.assertIn(f"R1 is not present for {CASES_SITE} (system-assigned) at {ESTATE} (MISSING)", out)
        self.assertIn("The 1 assignment(s) of id-meternaut-cases stay until it is, so that the app is not left without access", out)
        self.assertEqual(len(self.deletes(fake)), 3, "the other three are removed")
        self.assertEqual([(a["principal"], a["role_id"]) for a in self.old(fake)], [(OLD_CASES, BUILTIN["Reader"])])
        self.assertTrue(out.rstrip().endswith("6 of 7 gone."))
        code, out, _, _ = run(["grant", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual((code, self.old(fake)), (0, []))

    def test_an_app_that_has_no_system_assigned_identity_keeps_every_grant_of_its_old_identity_and_the_other_app_is_not_held_back(self):
        fake = FakeAz()
        fake.sites[CASES_SITE] = None
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        for item in ("W2", "W3"):
            self.assertRegex(out, rf"kept +{item}  id-meternaut-cases")
        self.assertIn(f"R1 is not present for {CASES_SITE} (system-assigned) at {ESTATE} (cannot yet: {CASES_SITE} has no system-assigned identity yet", out)
        self.assertEqual(len(self.deletes(fake)), 2)
        self.assertEqual({a["principal"] for a in self.old(fake)}, {OLD_CASES})

    def test_when_nothing_can_be_removed_because_of_the_replacements_it_says_so_and_changes_nothing(self):
        fake = FakeAz()
        fake.sites[CASES_SITE] = fake.sites[USAGE_SITE] = None
        for argv in (["retire", *PLACES, "--only", self.ONLY], ["retire", *PLACES, "--only", self.ONLY, "--apply", "--yes"]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual(code, 1, argv)
            self.assertIn("Nothing can be retired until the lines above that say 'kept' are settled.", out)
        self.assertEqual((fake.writes(), len(self.old(fake))), ([], 4))

    def test_the_replacement_is_read_like_check_reads_it_and_its_site_is_needed_when_there_is_something_to_remove(self):
        code, _, err, _ = run(["retire", *self.NO_SITES, "--only", "W2"], FakeAz())
        self.assertEqual(code, 1)
        self.assertIn("--cases-site is not set", err)
        code, _, err, _ = run(["retire", *self.NO_SITES, "--only", "W5"], FakeAz())
        self.assertEqual(code, 1)
        self.assertIn("--usage-site is not set", err)
        code, out, _, _ = run(["retire", *self.NO_SITES, "--only", self.ONLY], FakeAz(old=False))
        self.assertEqual((code, "Nothing to retire." in out), (0, True), "nothing is held, so no replacement has to be looked at")

    def test_a_grant_that_the_old_identity_holds_only_above_the_place_is_left_alone(self):
        fake = FakeAz()
        fake.assignments = [a for a in fake.assignments if not (a["principal"] == OLD_CASES and a["role_id"] == BUILTIN["Reader"])]
        fake.grant(OLD_CASES, BUILTIN["Reader"], MANAGEMENT_GROUP)
        for argv in (["retire", *PLACES, "--only", "W2"], ["retire", *PLACES, "--only", "W2", "--apply", "--yes"]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual(code, 1, argv)
            self.assertRegex(out, r"left alone +W2")
            self.assertIn(f"id-meternaut-cases also holds it at {MANAGEMENT_GROUP}, outside this place: nothing is removed there", out)
            self.assertIn("Nothing can be retired until the lines above that say 'left alone' are settled.", out)
        self.assertEqual(fake.writes(), [])

    def test_what_is_held_at_the_place_and_below_it_is_removed_and_what_is_held_above_it_is_only_reported(self):
        fake = FakeAz()
        fake.grant(OLD_CASES, BUILTIN["Reader"], MANAGEMENT_GROUP)
        fake.grant(OLD_CASES, BUILTIN["Reader"], f"{ESTATE}/resourceGroups/rg-one")
        code, out, _, _ = run(["retire", *PLACES, "--only", "W2"], fake)
        self.assertIn("id-meternaut-cases holds 2 assignment(s) of Reader at or below this place:", out)
        self.assertIn("outside this place: nothing is removed there", out)
        code, out, _, _ = run(["retire", *PLACES, "--only", "W2", "--apply", "--yes"], fake)
        self.assertEqual(code, 1, "what is held above the place is still there")
        self.assertEqual(len(self.deletes(fake)), 2)
        self.assertEqual([a["scope"] for a in fake.assignments if a["principal"] == OLD_CASES and a["role_id"] == BUILTIN["Reader"]], [MANAGEMENT_GROUP])
        self.assertRegex(out, r"left alone +W2")

    def test_an_identity_that_was_deleted_before_its_grants_cannot_be_traced_to_it_and_the_note_says_so(self):
        fake = FakeAz()
        del fake.identities["id-meternaut-cases"]
        before = [dict(a) for a in fake.assignments]
        code, out, _, _ = run(["retire", *PLACES, "--only", "W2,W3", "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertIn("Nothing to retire.", out)
        self.assertRegex(out, rf"gone +W2  id-meternaut-cases  Reader  at {re.escape(ESTATE)}")
        self.assertIn(f"id-meternaut-cases does not exist in {PROJECT_GROUP}.", out)
        self.assertIn("Azure keeps the assignments of a deleted identity, and the portal shows them as 'Identity not found'", out)
        self.assertIn("run retire before the identity is deleted", out)
        self.assertEqual((fake.writes(), fake.assignments), ([], before), "an assignment that cannot be traced to the identity is not touched")

    def test_a_custom_role_that_does_not_exist_has_no_assignment_to_retire(self):
        fake = FakeAz(old=False)
        code, out, _, _ = run(["retire", *PLACES, "--only", "W7"], fake)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"gone +W7")
        self.assertIn("Nothing to retire.", out)

    def test_a_failure_to_remove_an_assignment_of_an_old_identity_stops_at_once_and_says_which(self):
        fake = FakeAz()
        fake.unassign_errors = ["ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Authorization/roleAssignments/delete'"]
        code, out, err, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("could not be removed", err)
        self.assertIn("of Reader could not be removed", err)
        self.assertEqual(len(self.deletes(fake)), 1, "it did not go on to the next")

    def test_an_assignment_that_is_gone_already_is_not_an_error(self):
        fake = FakeAz()
        gone = next(a["id"] for a in self.old(fake) if a["principal"] == OLD_CASES and a["role_id"] == BUILTIN["Reader"])
        fake.vanish = {gone}
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertIn(f"the assignment {gone} was gone already", out)
        self.assertEqual(self.old(fake), [])

    def test_an_assignment_with_an_id_that_is_not_a_role_assignment_is_never_passed_to_a_delete(self):
        fake = FakeAz()
        victim = next(a for a in fake.assignments if a["principal"] == OLD_CASES)
        victim["id"] = f"{ESTATE}/providers/Microsoft.Compute/disks/a-disk"
        code, _, err, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("does not recognise", err)
        self.assertEqual(fake.writes(), [])

    def test_a_pipeline_may_not_apply_and_it_asks_first_like_the_other_commands(self):
        fake = FakeAz()
        code, _, err, _ = run(["retire", *PLACES, "--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, fake.calls), (1, []))
        self.assertIn("never a pipeline", err)
        asked = []
        code, out, _, _ = run(["retire", *PLACES, "--apply"], fake, answers=("no",), asked=asked)
        self.assertEqual((code, fake.writes()), (1, []))
        self.assertIn("operator@example.com", asked[0])
        self.assertIn("4 change(s)", asked[0])

    def test_nothing_but_role_assignments_of_the_retired_identities_is_ever_deleted(self):
        fake = FakeAz()
        run(["retire", *PLACES, "--apply", "--yes"], fake)
        allowed = {("account", "show"), ("identity", "show"), ("role", "definition"), ("role", "assignment"), ("rest", "--method")}
        self.assertEqual({tuple(c[:2]) for c in fake.calls} - allowed, set())
        self.assertEqual({tuple(c[:3]) for c in fake.writes()}, {("role", "assignment", "delete")})
        self.assertFalse([c for c in fake.calls if c[:2] == ["identity", "delete"] or c[0] == "ad" or c[:3] == ["role", "definition", "delete"]])


class RetireTheKeyReader(unittest.TestCase):
    """The custom role of the first cases that read one key of the owner's gateway (W7). The file no longer has the role, and retire removes it whole: every assignment of
    the role in the gateway's resource group and below it, whoever holds it, and then the role."""

    def left(self, **options):
        return FakeAz(old=False).leave_the_key_reader(**options)

    def test_a_dry_run_names_the_group_of_the_instance_lists_every_assignment_by_role_and_removes_nothing(self):
        fake = self.left(below=1)
        code, out, _, _ = run(["retire", *PLACES, "--only", "W7"], fake)
        self.assertEqual(code, 1, "something is left to retire, and a script can tell")
        self.assertEqual(fake.writes(), [])
        self.assertRegex(out, rf"still there +W7  id-meternaut-cases  {KEY_READER}  at {re.escape(GATEWAY_GROUP)}")
        self.assertIn(f"the custom role exists ({KEY_READER_ID}); 4 assignment(s) of it at or below this place", out)
        self.assertIn("5 change(s) would be made, and nothing else", out)
        self.assertIn("This was a dry run", out)
        commands = [line.strip() for line in out.splitlines() if line.strip().startswith("az ")]
        self.assertEqual(len([c for c in commands if c.startswith("az role assignment delete")]), 4)
        self.assertEqual(commands[-1].split("   #")[0], f"az role definition delete --subscription {GATEWAY_SUB} --name {KEY_READER_ID}")
        urls = [c[c.index("--url") + 1] for c in fake.calls if c[0] == "rest"]
        self.assertFalse(any("principalId" in url for url in urls), "found by the role and never by an identity: an identity that was deleted leaves its assignment")
        self.assertEqual({c[c.index("--method") + 1] for c in fake.calls if c[0] == "rest"}, {"get"})

    def test_apply_removes_every_assignment_of_the_role_whoever_holds_it_then_the_role_and_nothing_else(self):
        fake = self.left(orphans=2, below=1)
        others = [dict(a) for a in fake.assignments if a["role_id"] != KEY_READER_ID]
        roles = {name: dict(role) for name, role in fake.roles.items() if name != KEY_READER}
        code, out, _, _ = run(["retire", *PLACES, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 5 + [["role", "definition", "delete"]])
        self.assertEqual(fake.of_the_role(KEY_READER_ID), [])
        self.assertNotIn(KEY_READER, fake.roles)
        self.assertEqual(fake.assignments, others, "every other assignment of every identity is still there")
        self.assertEqual(fake.roles, roles, "every other role is still there")
        last = fake.writes()[-1]
        self.assertEqual((last[last.index("--subscription") + 1], last[last.index("--name") + 1]), (GATEWAY_SUB, KEY_READER_ID))
        self.assertIn("Checking again:", out)
        self.assertTrue(out.rstrip().endswith("7 of 7 gone."))
        self.assertEqual({tuple(c[:2]) for c in fake.calls} - {("account", "show"), ("identity", "show"), ("role", "definition"), ("role", "assignment"), ("rest", "--method")}, set())

    def test_a_second_run_has_nothing_to_retire(self):
        fake = self.left()
        run(["retire", *PLACES, "--apply", "--yes"], fake)
        before = len(fake.writes())
        for argv in (["retire", *PLACES, "--apply", "--yes"], ["retire", *PLACES, "--only", "W7"]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual((code, len(fake.writes()), "Nothing to retire." in out), (0, before, True), argv)

    def test_the_role_is_kept_while_an_assignment_of_it_remains(self):
        fake = self.left()
        stubborn = fake.of_the_role(KEY_READER_ID)[0]["id"]
        fake.stubborn = {stubborn}
        code, out, _, _ = run(["retire", *PLACES, "--only", "W7", "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"kept the custom role {KEY_READER}: 1 assignment(s) of it remain", out)
        self.assertEqual([c for c in fake.calls if c[:3] == ["role", "definition", "delete"]], [])
        self.assertIn(KEY_READER, fake.roles)

    def test_a_role_that_can_also_be_assigned_outside_the_gateways_group_is_left_alone(self):
        fake = self.left()
        fake.roles[KEY_READER]["assignableScopes"].append(f"/subscriptions/{GATEWAY_SUB}")
        for argv in (["retire", *PLACES, "--only", "W7"], ["retire", *PLACES, "--only", "W7", "--apply", "--yes"]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual(code, 1, argv)
            self.assertRegex(out, r"left alone +W7")
            self.assertIn("outside this place", out)
        self.assertEqual(fake.writes(), [])

    def test_it_is_looked_for_in_the_subscription_of_the_gateway_and_needs_no_name_of_an_app_and_no_product(self):
        fake = self.left()
        code, out, _, _ = run(["retire", "--project-subscription", PROJECT, "--project-group", "rg-project", "--gateway", APIM, "--only", "W7"], fake)
        self.assertEqual(code, 1)
        listed = [c for c in fake.calls if c[:3] == ["role", "definition", "list"]]
        self.assertEqual([c[c.index("--subscription") + 1] for c in listed], [GATEWAY_SUB])
        self.assertNotIn("--product-subscription", " ".join(" ".join(c) for c in fake.calls))
        code, _, err, _ = run(["retire", "--project-subscription", PROJECT, "--project-group", "rg-project", "--only", "W7"], self.left())
        self.assertEqual(code, 1)
        self.assertIn("--gateway is not set", err)

    def test_a_pipeline_may_not_apply_and_a_dry_run_is_allowed(self):
        fake = self.left()
        code, _, err, _ = run(["retire", *PLACES, "--only", "W7", "--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, fake.calls), (1, []))
        self.assertIn("never a pipeline", err)
        code, out, _, _ = run(["retire", *PLACES, "--only", "W7"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])


class RetireTheDeployer(unittest.TestCase):
    """The deployment identity's own custom role in the gateway's resource group (W8). The file no longer has the role, and retire removes it whole, as it does the key reader's:
    every assignment of the role in the group and below it, whoever holds it, and then the role. The identity lives in the bootstrap group, so it is not looked up."""

    ONLY = ["--only", "W8"]

    def left(self, **options):
        return FakeAz(old=False).leave_the_deployer(**options)

    def test_a_dry_run_lists_every_assignment_by_role_looks_for_no_identity_and_removes_nothing(self):
        fake = self.left(orphans=1, below=1)
        code, out, _, _ = run(["retire", *PLACES, *self.ONLY], fake)
        self.assertEqual(code, 1, "something is left to retire, and a script can tell")
        self.assertEqual(fake.writes(), [])
        self.assertRegex(out, rf"still there +W8  {DEPLOYER_IDENTITY}  {DEPLOYER}  at {re.escape(GATEWAY_GROUP)}")
        self.assertIn(f"the custom role exists ({DEPLOYER_ID}); 3 assignment(s) of it at or below this place", out)
        self.assertIn("every assignment of the role at this place is removed, whoever holds it", out)
        self.assertNotIn("Identity not found", out, "no claim about whose the assignments were: the identity was not read")
        self.assertNotIn(f"{DEPLOYER_IDENTITY} does not exist", out, "the deployment identity is in the bootstrap group: a lookup in the project's group would say that it is gone")
        self.assertEqual([c for c in fake.calls if c[:2] == ["identity", "show"]], [], "the identity is not looked up")
        self.assertIn("4 change(s) would be made, and nothing else", out)
        commands = [line.strip() for line in out.splitlines() if line.strip().startswith("az ")]
        self.assertEqual(len([c for c in commands if c.startswith("az role assignment delete")]), 3)
        self.assertEqual(commands[-1].split("   #")[0], f"az role definition delete --subscription {GATEWAY_SUB} --name {DEPLOYER_ID}")
        urls = [c[c.index("--url") + 1] for c in fake.calls if c[0] == "rest"]
        self.assertFalse(any("principalId" in url for url in urls), "found by the role and never by an identity")
        self.assertEqual({c[c.index("--method") + 1] for c in fake.calls if c[0] == "rest"}, {"get"})

    def test_it_needs_only_the_instance_and_no_project_and_no_name_of_an_app(self):
        fake = self.left()
        code, out, _, _ = run(["retire", "--gateway", APIM, *self.ONLY], fake)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, rf"still there +W8  {DEPLOYER_IDENTITY}  {DEPLOYER}  at {re.escape(GATEWAY_GROUP)}")
        code, _, err, _ = run(["retire", "--project-subscription", PROJECT, "--project-group", "rg-project", *self.ONLY], self.left())
        self.assertEqual(code, 1)
        self.assertIn("--gateway is not set", err)

    def test_apply_removes_every_assignment_of_the_role_whoever_holds_it_then_the_role_and_nothing_else(self):
        fake = self.left(orphans=2, below=1)
        others = [dict(a) for a in fake.assignments if a["role_id"] != DEPLOYER_ID]
        roles = {name: dict(role) for name, role in fake.roles.items() if name != DEPLOYER}
        code, out, _, _ = run(["retire", *PLACES, *self.ONLY, "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 4 + [["role", "definition", "delete"]])
        self.assertEqual(fake.of_the_role(DEPLOYER_ID), [])
        self.assertNotIn(DEPLOYER, fake.roles)
        self.assertEqual(fake.assignments, others, "every other assignment of every identity is still there")
        self.assertEqual(fake.roles, roles, "every other role is still there")
        last = fake.writes()[-1]
        self.assertEqual((last[last.index("--subscription") + 1], last[last.index("--name") + 1]), (GATEWAY_SUB, DEPLOYER_ID))
        self.assertIn("Checking again:", out)
        self.assertTrue(out.rstrip().endswith("1 of 1 gone."))
        self.assertEqual([c for c in fake.calls if c[:2] == ["identity", "show"] or c[:2] == ["identity", "delete"]], [], "an identity is neither looked up nor deleted")

    def test_it_goes_with_the_key_reader_in_one_run_and_each_role_is_removed_with_its_own_assignments(self):
        fake = FakeAz(old=False).leave_the_key_reader().leave_the_deployer(orphans=1)
        others = [dict(a) for a in fake.assignments if a["role_id"] not in (KEY_READER_ID, DEPLOYER_ID)]
        code, out, _, _ = run(["retire", *PLACES, "--only", "W7,W8", "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 5 + [["role", "definition", "delete"]] * 2)
        self.assertEqual((fake.of_the_role(KEY_READER_ID), fake.of_the_role(DEPLOYER_ID)), ([], []))
        self.assertTrue(DEPLOYER not in fake.roles and KEY_READER not in fake.roles)
        self.assertEqual(fake.assignments, others)
        self.assertTrue(out.rstrip().endswith("2 of 2 gone."))

    def test_a_second_run_has_nothing_to_retire(self):
        fake = self.left()
        run(["retire", *PLACES, *self.ONLY, "--apply", "--yes"], fake)
        before = len(fake.writes())
        for argv in (["retire", *PLACES, *self.ONLY, "--apply", "--yes"], ["retire", *PLACES, *self.ONLY], ["retire", *PLACES]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual((code, len(fake.writes()), "Nothing to retire." in out), (0, before, True), argv)

    def test_the_role_is_kept_while_an_assignment_of_it_remains(self):
        fake = self.left(orphans=1)
        fake.stubborn = {fake.of_the_role(DEPLOYER_ID)[0]["id"]}
        code, out, _, _ = run(["retire", *PLACES, *self.ONLY, "--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn(f"kept the custom role {DEPLOYER}: 1 assignment(s) of it remain", out)
        self.assertEqual([c for c in fake.calls if c[:3] == ["role", "definition", "delete"]], [])
        self.assertIn(DEPLOYER, fake.roles)

    def test_a_role_that_can_also_be_assigned_outside_the_gateways_group_is_left_alone(self):
        fake = self.left()
        fake.roles[DEPLOYER]["assignableScopes"].append(f"/subscriptions/{GATEWAY_SUB}")
        for argv in (["retire", *PLACES, *self.ONLY], ["retire", *PLACES, *self.ONLY, "--apply", "--yes"]):
            code, out, _, _ = run(argv, fake)
            self.assertEqual(code, 1, argv)
            self.assertRegex(out, r"left alone +W8")
            self.assertIn("outside this place", out)
        self.assertEqual(fake.writes(), [])

    def test_a_pipeline_may_not_apply_and_a_dry_run_is_allowed(self):
        fake = self.left()
        code, _, err, _ = run(["retire", *PLACES, *self.ONLY, "--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, fake.calls), (1, []))
        self.assertIn("never a pipeline", err)
        code, out, _, _ = run(["retire", *PLACES, *self.ONLY], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])

    def test_an_item_that_is_looked_up_still_says_whose_assignment_it_is_and_the_note_about_a_missing_identity_stays(self):
        fake = FakeAz(old=False).leave_the_writer(identity=False, orphans=1)
        code, out, _, _ = run(["retire", *PLACES, "--only", "W1"], fake)
        self.assertEqual(code, 1)
        self.assertIn("Identity not found", out)
        self.assertIn(f"{RETIRED_IDENTITY} does not exist in", out)
        self.assertNotIn("every assignment of the role at this place is removed, whoever holds it", out, "that wording is for an identity that is not looked up")


class RetireTheUsageApp(unittest.TestCase):
    """The usage app's two reads (W9, W10), retired on 2026-11-07 with the usage recording, against the file of the repository. W9 is the built-in role Monitoring Reader on the old gateway's
    Application Insights component, which stays because other people hold it: only the own assignments of the usage app's two identities are removed (its system-assigned identity, found by reading the
    app, and the user-assigned identity id-meternaut-usage). W10 is the custom role Meternaut usage reader, which goes whole, as W7 and W8 did: every assignment of it at the central workspace's resource
    group and below, whoever holds it, and then the role. A person runs `retire --only W9,W10` in the owner's session, before the Hub action retire-old deletes the app and its identity."""

    ONLY = ["--only", "W9,W10"]
    APP = f"{USAGE_SITE} (system-assigned)"

    def left(self, **options):
        return FakeAz(granted=False).leave_the_usage_app(**options)

    def go(self, argv, fake, **more):
        return run(["retire", *PLACES, *self.ONLY, *argv], fake, real=True, **more)

    def test_a_dry_run_names_both_identities_and_the_role_lists_what_each_holds_and_removes_nothing(self):
        fake = self.left(orphans=1, below=1)
        code, out, _, _ = self.go([], fake)
        self.assertEqual(code, 1, "something is left to retire, and a script can tell")
        self.assertEqual(fake.writes(), [])
        self.assertRegex(out, rf"still there +W9  id-meternaut-usage  Monitoring Reader  at {re.escape(INSIGHTS)}")
        self.assertRegex(out, rf"still there +W9  {re.escape(self.APP)}  Monitoring Reader  at {re.escape(INSIGHTS)}")
        self.assertRegex(out, rf"still there +W10  id-meternaut-usage  Meternaut usage reader  at {re.escape(WORKSPACE)}")
        self.assertIn("id-meternaut-usage holds 1 assignment(s) of Monitoring Reader at or below this place", out)
        self.assertIn(f"{self.APP} holds 1 assignment(s) of Monitoring Reader at or below this place", out)
        self.assertIn(f"the custom role exists ({USAGE_READER_ID}); 4 assignment(s) of it at or below {WORKSPACE_GROUP} (the resource group where the role was defined)", out)
        self.assertIn("the Hub action retire-old removes it, after this tool has taken away its grants", out, "the identity is deleted by the Hub action, never by this tool")
        self.assertIn("7 change(s) would be made, and nothing else", out)
        self.assertIn("This was a dry run", out)
        commands = [line.strip() for line in out.splitlines() if line.strip().startswith("az ")]
        self.assertEqual(len([c for c in commands if c.startswith("az role assignment delete")]), 6)
        self.assertEqual(commands[-1].split("   #")[0], f"az role definition delete --subscription {WORKSPACE_SUB} --name {USAGE_READER_ID}")
        self.assertEqual({c[c.index("--method") + 1] for c in fake.calls if c[0] == "rest"}, {"get"}, "the app is only read")
        self.assertEqual([c for c in fake.calls if c[:2] == ["identity", "delete"]], [])

    def test_apply_removes_the_own_assignments_of_the_two_identities_every_assignment_of_the_role_then_the_role_and_nothing_else(self):
        fake = self.left(orphans=2, below=1)
        somebody_else = [dict(a) for a in fake.assignments if a["principal"] == "somebody-else"]
        self.assertEqual(len(somebody_else), 1)
        code, out, _, _ = self.go(["--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 7 + [["role", "definition", "delete"]])
        self.assertEqual(fake.assignments, somebody_else, "what somebody else holds on the old component is still there: the role is built in and stays")
        self.assertEqual(fake.roles, {}, "the custom role is gone, and no built-in role is ever deleted")
        self.assertEqual([c for c in fake.calls if c[:2] in (["identity", "delete"], ["resource", "delete"])], [], "neither the identity nor the app is touched: the Hub action retire-old deletes them")
        self.assertEqual({c[c.index("--method") + 1] for c in fake.calls if c[0] == "rest"}, {"get"})
        self.assertIn("Checking again:", out)
        self.assertTrue(out.rstrip().endswith("3 of 3 gone."))

    def test_a_second_run_has_nothing_to_retire(self):
        fake = self.left()
        self.go(["--apply", "--yes"], fake)
        before = len(fake.writes())
        for argv in (["--apply", "--yes"], []):
            code, out, _, _ = self.go(argv, fake)
            self.assertEqual((code, len(fake.writes()), "Nothing to retire." in out), (0, before, True), argv)
        code, out, _, _ = run(["retire", *PLACES], fake, real=True)
        self.assertEqual((code, len(fake.writes()), "Nothing to retire." in out), (0, before, True), "the whole list of the retired items")

    def test_an_app_that_is_gone_cannot_be_traced_so_its_own_assignment_is_said_to_stay_and_the_user_assigned_identitys_is_still_removed(self):
        fake = self.left()
        del fake.sites[USAGE_SITE]
        code, out, _, _ = self.go([], fake)
        self.assertEqual(code, 1)
        self.assertIn("so nothing can be traced to its identity by name", out)
        self.assertIn("this tool cannot tell whose they were", out)
        code, out, _, _ = self.go(["--apply", "--yes"], fake)
        held = {(a["principal"], a["role_id"]) for a in fake.assignments}
        self.assertIn((NEW_USAGE, BUILTIN["Monitoring Reader"]), held, "an assignment that cannot be traced to the app stays: Azure shows it as 'Identity not found', and the role is built in")
        self.assertNotIn((OLD_USAGE, BUILTIN["Monitoring Reader"]), held, "the user-assigned identity still exists, so its own assignment is removed")
        self.assertEqual(fake.of_the_role(USAGE_READER_ID), [], "the custom role is removed whole whoever holds it, so this part does not depend on the app")
        self.assertNotIn("Meternaut usage reader", fake.roles)

    def test_the_name_of_the_usage_app_is_needed_for_w9_and_not_for_w10(self):
        places = [x for x in PLACES if x not in ("--usage-site", USAGE_SITE)]
        code, _, err, _ = run(["retire", *places, "--only", "W9"], self.left(), real=True)
        self.assertEqual(code, 1)
        self.assertIn("--usage-site", err)
        fake = self.left()
        code, out, _, _ = run(["retire", *places, "--only", "W10"], fake, real=True)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"still there +W10")
        self.assertEqual(fake.writes(), [])

    def test_the_role_is_kept_while_an_assignment_of_it_remains_and_the_built_in_reads_are_still_removed(self):
        fake = self.left()
        fake.stubborn = {fake.of_the_role(USAGE_READER_ID)[0]["id"]}
        code, out, _, _ = self.go(["--apply", "--yes"], fake)
        self.assertEqual(code, 1)
        self.assertIn("kept the custom role Meternaut usage reader: 1 assignment(s) of it remain", out)
        self.assertEqual([c for c in fake.calls if c[:3] == ["role", "definition", "delete"]], [])
        self.assertIn("Meternaut usage reader", fake.roles)
        self.assertEqual([a for a in fake.assignments if a["principal"] in (NEW_USAGE, OLD_USAGE) and a["role_id"] == BUILTIN["Monitoring Reader"]], [])

    def test_a_role_that_can_also_be_assigned_outside_the_workspaces_group_is_left_alone_and_the_built_in_reads_are_still_removed(self):
        fake = self.left()
        fake.roles["Meternaut usage reader"]["assignableScopes"].append(f"/subscriptions/{WORKSPACE_SUB}")
        code, out, _, _ = self.go([], fake)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"left alone +W10")
        self.assertIn("outside this place", out)
        before = len(fake.of_the_role(USAGE_READER_ID))
        self.go(["--apply", "--yes"], fake)
        self.assertEqual(len(fake.of_the_role(USAGE_READER_ID)), before, "nothing of a role that is not only the project's is touched")
        self.assertIn("Meternaut usage reader", fake.roles)
        self.assertEqual([a for a in fake.assignments if a["principal"] in (NEW_USAGE, OLD_USAGE) and a["role_id"] == BUILTIN["Monitoring Reader"]], [])

    def test_a_pipeline_may_not_apply_and_a_dry_run_is_allowed(self):
        fake = self.left()
        code, _, err, _ = self.go(["--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, fake.calls), (1, []))
        self.assertIn("never a pipeline", err)
        code, out, _, _ = self.go([], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])


class Offboard(unittest.TestCase):
    """The reverse of grant: exactly the assignments that grant makes, at exactly their places, and nothing else (docs/proposals/03-access-and-onboarding.md, I11)."""

    def go(self, extra, fake, **options):
        return run(["offboard", *PLACES, *extra], fake, **options)

    def held(self, fake):
        return {(x["principal"], x["role_id"], x["scope"]) for x in fake.assignments}

    def test_a_dry_run_names_every_assignment_that_grant_made_and_removes_none(self):
        fake = FakeAz(old=False)
        before = list(fake.assignments)
        code, out, _, _ = self.go([], fake)
        self.assertEqual(code, 1, "something is left to take away")
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])
        self.assertEqual(fake.assignments, before)
        self.assertEqual(len(before), 4)
        self.assertEqual(sorted(re.findall(r"az role assignment delete --ids (\S+)", out)), sorted(x["id"] for x in before))
        self.assertIn("4 assignment(s) would be removed, and nothing else", out)

    def test_apply_removes_exactly_those_and_what_grant_did_not_make_stays(self):
        fake = FakeAz(old=False)
        reader, monitoring, cost = BUILTIN["Reader"], BUILTIN["Monitoring Reader"], BUILTIN["Cost Management Reader"]
        below = f"{ESTATE}/resourceGroups/rg-below"
        others = {("somebody-else", reader, ESTATE), (NEW_CASES, reader, below), (NEW_CASES, monitoring, ESTATE), ("somebody-else", cost, MANAGEMENT_GROUP), (OLD_CASES, reader, ESTATE)}
        for principal, role, scope in others:
            fake.grant(principal, role, scope)
        code, out, _, _ = self.go(["--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.held(fake), others, "another identity's assignment of the same role (the old user-assigned identity of the app too: `retire` is for that), the same identity's assignment below the place "
                                                  "or of another role, and a management group's all stay")
        self.assertEqual(len(re.findall(r"^  removed ", out, re.M)), 4)
        self.assertEqual([c[:3] for c in fake.writes()], [["role", "assignment", "delete"]] * 4, "it deletes assignments and writes nothing else")
        self.assertIn("4 of 4 gone or not held.", out)

    def test_it_never_removes_an_identity_or_a_role(self):
        fake = FakeAz()
        roles, identities = dict(fake.roles), dict(fake.identities)
        self.go(["--apply", "--yes"], fake)
        self.assertEqual((fake.roles, fake.identities), (roles, identities))
        for call in fake.calls:
            self.assertNotEqual(call[:3], ["role", "definition", "delete"])
            self.assertNotIn(call[:2], (["identity", "delete"], ["functionapp", "delete"]))

    def test_the_same_role_held_only_at_a_place_above_is_left_alone_and_nothing_is_removed_for_it(self):
        fake = FakeAz(granted=False)
        fake.grant(NEW_CASES, BUILTIN["Cost Management Reader"], MANAGEMENT_GROUP)
        code, out, _, _ = self.go(["--only", "R2"], fake)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"left alone\s+R2\s+.*Cost Management Reader\s+at /subscriptions/")
        self.assertIn("a place above, which this tool does not take away", out)
        self.assertIn("Nothing to take away.", out)
        self.assertEqual(fake.writes(), [])

    def test_an_identity_that_does_not_exist_holds_nothing_and_the_others_are_still_offboarded(self):
        fake = FakeAz(old=False)
        fake.sites = {CASES_SITE: NEW_CASES}
        code, out, _, _ = self.go(["--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertIn("no identity", out)
        self.assertEqual(self.held(fake), {(NEW_USAGE, BUILTIN["Monitoring Reader"], INSIGHTS), (NEW_USAGE, USAGE_READER_ID, WORKSPACE)},
                         "what only a system-assigned identity holds cannot be read while its app is not there, so it stays and the line says why")

    def test_only_limits_it_to_the_grants_named(self):
        fake = FakeAz(old=False)
        code, out, _, _ = self.go(["--only", "R1", "--apply", "--yes"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual({x["principal"] for x in fake.assignments if x["role_id"] == BUILTIN["Reader"]}, set())
        self.assertEqual(len(fake.assignments), 3)
        code, _, err, _ = self.go(["--only", "R99"], FakeAz(old=False))
        self.assertEqual(code, 1)
        self.assertIn("R99", err)

    def test_a_second_run_finds_nothing_and_a_removal_that_azure_did_not_make_is_not_called_gone(self):
        again = FakeAz(old=False)
        self.go(["--apply", "--yes"], again)
        code, out, _, _ = self.go([], again)
        self.assertEqual((code, again.assignments), (0, []))
        self.assertIn("Nothing to take away.", out)
        stubborn = FakeAz(old=False)
        stubborn.stubborn = {stubborn.assignments[0]["id"]}
        code, out, _, _ = self.go(["--apply", "--yes"], stubborn)
        self.assertEqual(code, 1, "it reads again after it writes, and one assignment is still there")
        self.assertIn("still there", out.split("Checking again:")[1])
        self.assertIn("3 of 4 gone or not held.", out)

    def test_it_asks_first_and_a_pipeline_may_not_apply_but_a_dry_run_is_allowed(self):
        fake, asked = FakeAz(old=False), []
        code, out, _, _ = self.go(["--apply"], fake, answers=("yes",), asked=asked)
        self.assertEqual(code, 0)
        self.assertIn("operator@example.com", asked[0])
        fake = FakeAz(old=False)
        code, _, err, _ = self.go(["--apply"], fake, answers=("no",))
        self.assertEqual((code, fake.writes()), (1, []))
        self.assertIn("nothing was changed", err)
        code, _, err, _ = self.go(["--apply"], FakeAz(old=False), answers=())
        self.assertEqual(code, 1)
        self.assertIn("needs --yes", err)
        fake = FakeAz(old=False)
        code, _, err, _ = self.go(["--apply", "--yes"], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, fake.calls), (1, []))
        self.assertIn("never a pipeline", err)
        code, out, _, _ = self.go([], fake, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("dry run", out)
        self.assertEqual(fake.writes(), [])

    def test_the_file_of_the_repository_offboards_what_it_grants_and_the_tool_says_what_it_does_in_its_own_words(self):
        fake = FakeAz(old=False)
        fake.sites = {CASES_SITE: NEW_CASES}
        code, out, _, _ = run(["offboard", *PLACES, "--only", "R1,R2"], fake, real=True)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(re.findall(r"az role assignment delete --ids ", out)), 2)
        self.assertIn("offboard", ar.__doc__)
        self.assertIn("never removes an identity, a custom role or an assignment of anybody", re.sub(r"\s+", " ", ar.__doc__))


if __name__ == "__main__":
    unittest.main()
