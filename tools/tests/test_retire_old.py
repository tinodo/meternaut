"""The actions `retire-old` and `retire-event-hubs`: tools/retire-old.py, run against a model of Azure, and the steps of the Hub workflow that run it.

`retire-old` deletes what Meternaut does not use any more (the usage recording and the old model account) in the project's own resource group, by exact names, and nothing else.
`retire-event-hubs` deletes the Event Hubs namespace that carried the control event, its private endpoint and its checkpoint container, the same way, once the control queue that replaces it is there.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("retire_old", ROOT / "tools" / "retire-old.py")
ro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ro)
params_spec = importlib.util.spec_from_file_location("environment_params_for_retire_test", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(params_spec)
params_spec.loader.exec_module(ep)

SUB = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
TOKEN = ro.digest(SUB, GROUP)
BASE = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
NAMESPACE = f"{BASE}/Microsoft.EventHub/namespaces/evhns-meternaut-{TOKEN}"
SUBNET = f"{BASE}/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-func"
WEB_SUBNET = f"{BASE}/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-cases"
CASES_SITE = f"{BASE}/Microsoft.Web/sites/func-meternaut-cases-{TOKEN}"
USAGE_PRINCIPAL = "aaaaaaaa-0000-4000-8000-000000000001"
IDENTITY_PRINCIPAL = "bbbbbbbb-0000-4000-8000-000000000002"
ENVIRONMENT = {"GITHUB_ACTIONS": "true", "ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP}

# The whole list, in this order: (what it is, its exact name, the id of the resource, the API version it is read and deleted with).
THE_LIST = [
    ("the usage function app", f"func-meternaut-usage-{TOKEN}", f"{BASE}/Microsoft.Web/sites/func-meternaut-usage-{TOKEN}", "2024-04-01"),
    ("the usage app's plan", "plan-meternaut-usage", f"{BASE}/Microsoft.Web/serverfarms/plan-meternaut-usage", "2024-04-01"),
    ("the usage app's private endpoint", f"pe-func-meternaut-usage-{TOKEN}", f"{BASE}/Microsoft.Network/privateEndpoints/pe-func-meternaut-usage-{TOKEN}", "2025-05-01"),
    ("the Cosmos DB account", f"cosmos-meternaut-{TOKEN}", f"{BASE}/Microsoft.DocumentDB/databaseAccounts/cosmos-meternaut-{TOKEN}", "2024-11-15"),
    ("the Cosmos DB account's private endpoint", f"pe-cosmos-meternaut-{TOKEN}", f"{BASE}/Microsoft.Network/privateEndpoints/pe-cosmos-meternaut-{TOKEN}", "2025-05-01"),
    ("the event hub", "ai-usage", f"{NAMESPACE}/eventhubs/ai-usage", "2024-01-01"),
    ("the event hub", "pii-usage", f"{NAMESPACE}/eventhubs/pii-usage", "2024-01-01"),
    ("the event hub", "usage-control", f"{NAMESPACE}/eventhubs/usage-control", "2024-01-01"),
    ("the old model account's private endpoint", f"pe-aif-meternaut-{TOKEN}", f"{BASE}/Microsoft.Network/privateEndpoints/pe-aif-meternaut-{TOKEN}", "2025-05-01"),
    ("the old model account", f"aif-meternaut-{TOKEN}", f"{BASE}/Microsoft.CognitiveServices/accounts/aif-meternaut-{TOKEN}", "2025-06-01"),
    ("the identity of the usage app", "id-meternaut-usage", f"{BASE}/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-usage", "2023-01-31"),
]

# What stays, in the same group: the base, the cases app and the network. Nothing of this may ever be touched by the list `old`. The Event Hubs namespace with its private endpoint and its checkpoint container
# is on the other list, `event-hubs` (the action retire-event-hubs): the list `old` never touches it.
WHAT_STAYS = [
    f"{BASE}/Microsoft.EventHub/namespaces/evhns-meternaut-{TOKEN}",
    f"{NAMESPACE}/eventhubs/cases-control",
    f"{BASE}/Microsoft.Storage/storageAccounts/stmeternautfn{TOKEN}",
    f"{BASE}/Microsoft.Storage/storageAccounts/stmeternautfn{TOKEN}/blobServices/default/containers/azure-webjobs-eventhub",
    f"{BASE}/Microsoft.Storage/storageAccounts/stmeternautfn{TOKEN}/queueServices/default/queues/cases-control",
    f"{BASE}/Microsoft.Network/privateEndpoints/pe-stmeternautfn{TOKEN}-blob",
    f"{BASE}/Microsoft.Network/privateEndpoints/pe-evhns-meternaut-{TOKEN}",
    f"{BASE}/Microsoft.OperationalInsights/workspaces/log-meternaut",
    f"{BASE}/Microsoft.Insights/components/appi-meternaut",
    f"{BASE}/Microsoft.Network/virtualNetworks/vnet-meternaut",
    f"{BASE}/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-func",
    f"{BASE}/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-pe",
    f"{BASE}/Microsoft.Web/sites/func-meternaut-cases-{TOKEN}",
    f"{BASE}/Microsoft.CognitiveServices/accounts/aif-meternaut-agents-{TOKEN}",
]

# The list `event-hubs`, in this order: (what it is, its exact name, the id of the resource, the API version it is read and deleted with), and the control queue that has to be there before anything is deleted.
STORAGE_ACCOUNT = f"stmeternautfn{TOKEN}"
CONTROL_QUEUE = f"{BASE}/Microsoft.Storage/storageAccounts/{STORAGE_ACCOUNT}/queueServices/default/queues/cases-control"
THE_EVENT_HUBS_LIST = [
    ("the Event Hubs namespace's private endpoint", f"pe-evhns-meternaut-{TOKEN}", f"{BASE}/Microsoft.Network/privateEndpoints/pe-evhns-meternaut-{TOKEN}", "2025-05-01"),
    ("the Event Hubs namespace", f"evhns-meternaut-{TOKEN}", NAMESPACE, "2024-01-01"),
    ("the container of the namespace's checkpoints", "azure-webjobs-eventhub",
     f"{BASE}/Microsoft.Storage/storageAccounts/{STORAGE_ACCOUNT}/blobServices/default/containers/azure-webjobs-eventhub", "2023-05-01"),
]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def time(self) -> float:
        return self.now


class FakeAzure:
    """A model of the project's resource group: what is there, what a read and a delete say, the soft-deleted accounts, the role assignments, the function subnet and the apps on it."""

    def __init__(self, present=True, stays=True) -> None:
        self.resources: dict[str, dict] = {}
        self.deleted_accounts: list[dict] = []
        self.assignments: list[dict] = []
        self.calls: list[list[str]] = []
        self.visible_after_delete: dict[str, int] = {}
        self.read_errors: dict[str, str] = {}
        self.delete_errors: dict[str, str] = {}
        self.purge_error: str | None = None
        self.list_deleted_error: str | None = None
        self.stuck_after_purge = False
        self.hidden: dict[str, int] = {}
        self.delegations = ["Microsoft.App/environments"]
        self.links: list[dict] = []
        self.integration: dict[str, str] = {}
        self.plan_of: dict[str, str] = {}
        self.ghosts: dict[str, int] = {}
        self.rest_errors: dict[str, str] = {}
        self.rest_urls: list[tuple[str, str]] = []
        self.page_size = 0
        if present:
            for _, _, resource_id, _ in THE_LIST:
                self.resources[resource_id.lower()] = {"id": resource_id}
            self.resources[THE_LIST[0][2].lower()]["identity"] = {"type": "SystemAssigned", "principalId": USAGE_PRINCIPAL}
            self.resources[THE_LIST[-1][2].lower()]["properties"] = {"principalId": IDENTITY_PRINCIPAL}
            self.integration[THE_LIST[0][2].lower()] = SUBNET
            self.plan_of[THE_LIST[0][2].lower()] = THE_LIST[1][2]
        if stays:
            for resource_id in WHAT_STAYS:
                self.resources[resource_id.lower()] = {"id": resource_id}
            self.integration[CASES_SITE.lower()] = WEB_SUBNET
            self.plan_of[CASES_SITE.lower()] = f"{BASE}/Microsoft.Web/serverfarms/plan-meternaut-cases-basic"

    def add_app(self, name: str, subnet: str | None = None, plan: str = "plan-elsewhere") -> str:
        site = f"{BASE}/Microsoft.Web/sites/{name}"
        self.resources[site.lower()] = {"id": site}
        if subnet:
            self.integration[site.lower()] = subnet
        self.plan_of[site.lower()] = f"{BASE}/Microsoft.Web/serverfarms/{plan}"
        return site

    def ids(self) -> set[str]:
        return set(self.resources)

    def add_event_hubs(self, queue: bool = True) -> None:
        """The namespace, its private endpoint and its checkpoint container are there, and so is the control queue that replaces the namespace (unless `queue` is False)."""
        for _, _, resource_id, _ in THE_EVENT_HUBS_LIST:
            self.resources[resource_id.lower()] = {"id": resource_id}
        if queue:
            self.resources[CONTROL_QUEUE.lower()] = {"id": CONTROL_QUEUE}

    def writes(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] in (["resource", "delete"],) or c[:3] == ["cognitiveservices", "account", "purge"] or c[:3] == ["role", "assignment", "delete"]]

    def option(self, args: list[str], name: str) -> str:
        return args[args.index(name) + 1]

    def sites_page(self, url: str):
        skip = int(re.search(r"skiptoken=(\d+)", url).group(1)) if "skiptoken=" in url else 0
        keys = [k for k in self.resources if "/microsoft.web/sites/" in k and "/slots/" not in k]
        keys += [k for k, left in self.ghosts.items() if left > 0 and k not in self.resources]
        if skip == 0:
            self.ghosts = {k: left - 1 for k, left in self.ghosts.items() if left > 1}
        size = self.page_size or len(keys) or 1
        value = []
        for key in keys[skip:skip + size]:
            site_id = self.resources.get(key, {}).get("id", key)
            value.append({"id": site_id, "name": site_id.rsplit("/", 1)[-1],
                          "properties": {"virtualNetworkSubnetId": self.integration.get(key), "serverFarmId": self.plan_of.get(key)}})
        body = {"value": value}
        if skip + size < len(keys):
            body["nextLink"] = f"{url.split('&$skiptoken')[0]}&$skiptoken={skip + size}"
        return 0, json.dumps(body), ""

    def __call__(self, args):
        self.calls.append(list(args))
        a = list(args)
        if a[:2] == ["resource", "show"]:
            resource_id = self.option(a, "--ids")
            if resource_id in self.read_errors:
                return 1, "", self.read_errors[resource_id]
            key = resource_id.lower()
            if key in self.hidden:
                self.hidden[key] -= 1
                if self.hidden[key] <= 0:
                    del self.hidden[key]
                    self.resources.pop(key, None)
                return (0, json.dumps({"id": resource_id}), "") if key in self.resources or self.hidden.get(key) else (3, "", self.not_found(resource_id))
            if key in self.resources:
                return 0, json.dumps(self.resources[key]), ""
            return 3, "", self.not_found(resource_id)
        if a[:2] == ["resource", "delete"]:
            resource_id = self.option(a, "--ids")
            if resource_id in self.delete_errors:
                return 1, "", self.delete_errors[resource_id]
            key = resource_id.lower()
            if key not in self.resources:
                return 3, "", self.not_found(resource_id)
            if "/microsoft.cognitiveservices/accounts/" in key:
                name = resource_id.rsplit("/", 1)[-1]
                self.deleted_accounts.append({"id": f"/subscriptions/{SUB}/providers/Microsoft.CognitiveServices/locations/swedencentral/resourceGroups/{GROUP}/deletedAccounts/{name}",
                                              "name": name, "location": "Sweden Central"})
            delay = self.visible_after_delete.get(key, 0)
            if delay:
                self.hidden[key] = delay
            else:
                del self.resources[key]
                for child in [k for k in self.resources if k.startswith(key + "/")]:
                    del self.resources[child]
            return 0, "", ""
        if a[:4] == ["cognitiveservices", "account", "list-deleted", "--output"]:
            if self.list_deleted_error:
                return 1, "", self.list_deleted_error
            return 0, json.dumps(self.deleted_accounts), ""
        if a[:3] == ["cognitiveservices", "account", "purge"]:
            if self.purge_error:
                return 1, "", self.purge_error
            name = self.option(a, "--name")
            location = self.option(a, "--location")
            group = self.option(a, "--resource-group")
            found = [d for d in self.deleted_accounts if d["name"] == name and f"/locations/{location}/resourceGroups/{group}/" in d["id"]]
            if not found:
                return 3, "", f"(ResourceNotFound) The deleted account {name} was not found."
            if not self.stuck_after_purge:
                self.deleted_accounts.remove(found[0])
            return 0, "", ""
        if a[0] == "rest":
            url = self.option(a, "--url")
            self.rest_urls.append((self.option(a, "--method"), url))
            for part, error in self.rest_errors.items():
                if part in url:
                    return 1, "", error
            if "/providers/Microsoft.Web/sites?" in url:
                return self.sites_page(url)
            if "/queueServices/default/queues/" in url:
                path = url[len(ro.ARM):url.index("?")]
                if path.lower() not in self.resources:
                    return 3, "", self.not_found(path)
                return 0, json.dumps({"id": path, "name": path.rsplit("/", 1)[-1]}), ""
            if "/subnets/" in url and "roleAssignments" not in url:
                path = url[len(ro.ARM):url.index("?")]
                if path.lower() not in self.resources:
                    return 3, "", self.not_found(path)
                body = {"id": path, "name": path.rsplit("/", 1)[-1],
                        "properties": {"delegations": [{"properties": {"serviceName": name}} for name in self.delegations], "serviceAssociationLinks": self.links}}
                return 0, json.dumps(body), ""
            principal = re.search(r"principalId eq '([^']+)'", url)
            scope = url[len(ro.ARM):url.index("/providers/Microsoft.Authorization/roleAssignments")]
            value = [{"id": x["id"], "properties": {"scope": x["scope"], "principalId": x["principal"]}} for x in self.assignments
                     if principal and x["principal"] == principal.group(1) and (x["scope"].lower().startswith(scope.lower()) or scope.lower().startswith(x["scope"].lower()))]
            return 0, json.dumps({"value": value}), ""
        return 1, "", f"unexpected command {a[:3]}"

    @staticmethod
    def not_found(resource_id: str) -> str:
        return f"ERROR: (ResourceNotFound) The Resource '{resource_id.split('/providers/')[-1]}' under resource group '{GROUP}' was not found. For more details please go to https://aka.ms/ARMResourceNotFoundFix"


def go(argv, fake, environ=None, clock=None):
    clock = clock or Clock()
    lines, errors = [], io.StringIO()
    with contextlib.redirect_stderr(errors):
        code = ro.main(argv, runner=fake, environ=dict(ENVIRONMENT) if environ is None else environ, sleep=clock.sleep, clock=clock.time, out=lines.append)
    return code, "\n".join(lines), errors.getvalue(), clock


RUN = ["run", "--subscription", SUB, "--resource-group", GROUP]
SHOW = ["show", "--subscription", SUB, "--resource-group", GROUP]


class TheList(unittest.TestCase):
    def test_the_list_is_exactly_this_and_in_this_order(self):
        got = [(i.what, i.name, i.id, i.api_version) for i in ro.items(SUB, GROUP)]
        self.assertEqual(got, THE_LIST)

    def test_every_id_is_in_the_project_group_and_nowhere_else(self):
        for item in ro.items(SUB, GROUP):
            self.assertTrue(item.id.startswith(f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/"), item.id)
        for other_group in ("rg-other", "rg-example2"):
            self.assertFalse([i for i in ro.items(SUB, other_group) if f"/resourceGroups/{GROUP}/" in i.id])

    def test_the_namespace_and_its_hub_for_the_cases_are_not_on_the_list_old_they_have_a_list_of_their_own(self):
        ids = {i.id.lower() for i in ro.items(SUB, GROUP)}
        self.assertNotIn(f"{BASE}/Microsoft.EventHub/namespaces/evhns-meternaut-{TOKEN}".lower(), ids)
        self.assertFalse([i for i in ids if "cases-control" in i])
        self.assertEqual([i.name for i in ro.items(SUB, GROUP) if i.what == "the event hub"], ["ai-usage", "pii-usage", "usage-control"])

    def test_nothing_that_stays_is_on_the_list(self):
        ids = {i.id.lower() for i in ro.items(SUB, GROUP)}
        for stays in WHAT_STAYS:
            self.assertNotIn(stays.lower(), ids)
        self.assertFalse([i for i in ids if "/subnets/" in i or "virtualnetworks/vnet" in i or "storageaccounts" in i or "workspaces" in i or "components/appi" in i])

    def test_the_names_are_the_ones_that_the_parameter_builder_makes_and_the_templates_made(self):
        self.assertEqual(ro.digest(SUB, GROUP), ep.digest(SUB, GROUP))
        self.assertEqual(ro.digest(SUB.upper(), GROUP.upper()), ep.digest(SUB.upper(), GROUP.upper()))
        self.assertEqual(ep.base_names(SUB, GROUP), {"storage_account_name": STORAGE_ACCOUNT}, "the builder makes the storage account's name, which holds the checkpoint container and the control queue, and no namespace")
        self.assertEqual(ep.cases_names(SUB, GROUP)["cases_function_app_name"], f"func-meternaut-cases-{TOKEN}")
        self.assertNotEqual(ep.foundry_names(SUB, GROUP)["foundry_account_name"], f"aif-meternaut-{TOKEN}", "the Foundry resource of the agents is not the old model account")

    def test_the_hub_names_and_the_plan_are_the_ones_that_the_templates_made(self):
        recording = subprocess_text("git", "show", "383b968:environment/recording/main.bicep")
        if recording is None:
            self.skipTest("the history is not available")
        for hub in ro.USAGE_HUBS:
            self.assertIn(f"var {'usageHubName' if hub == 'ai-usage' else 'piiHubName' if hub == 'pii-usage' else 'controlHubName'} = '{hub}'", recording)
        self.assertIn("name: 'plan-${workload}-usage'", recording)
        self.assertIn("name: 'pe-${cosmosAccountName}'", recording)
        self.assertIn("name: 'pe-${functionAppName}'", recording)


def subprocess_text(*command):
    import subprocess
    try:
        done = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


class TheRefusal(unittest.TestCase):
    def refused(self, argv, environ=None):
        fake = FakeAzure()
        code, out, err, _ = go(argv, fake, environ)
        self.assertEqual(code, 2, err)
        self.assertEqual(fake.calls, [], "nothing is read or changed when it refuses")
        self.assertEqual(out, "")
        return err

    def test_another_resource_group_is_refused_before_anything_is_read(self):
        err = self.refused(["run", "--subscription", SUB, "--resource-group", "rg-other"])
        self.assertIn("is not the one of the workflow's setting ENV_RESOURCE_GROUP", err)
        self.refused(["show", "--subscription", SUB, "--resource-group", "rg-other"])

    def test_a_group_that_differs_only_in_case_is_another_group(self):
        self.refused(["run", "--subscription", SUB, "--resource-group", GROUP.upper()])

    def test_another_subscription_is_refused(self):
        err = self.refused(["run", "--subscription", "99999999-8888-7777-6666-555555555555", "--resource-group", GROUP])
        self.assertIn("ENV_SUBSCRIPTION_ID", err)

    def test_a_workflow_without_its_settings_refuses(self):
        self.refused(RUN, {"GITHUB_ACTIONS": "true"})
        self.refused(RUN, {"GITHUB_ACTIONS": "true", "ENV_RESOURCE_GROUP": "", "ENV_SUBSCRIPTION_ID": ""})

    def test_a_group_name_that_is_not_one_is_refused(self):
        for bad in ("rg/../other", "rg example", "", "a" * 91):
            self.refused(["run", "--subscription", SUB, "--resource-group", bad], {**ENVIRONMENT, "ENV_RESOURCE_GROUP": bad})

    def test_a_subscription_that_is_not_an_id_is_refused(self):
        self.refused(["run", "--subscription", "not-an-id", "--resource-group", GROUP], {**ENVIRONMENT, "ENV_SUBSCRIPTION_ID": "not-an-id"})

    def test_only_a_github_actions_run_may_delete(self):
        fake = FakeAzure()
        code, _, err, _ = go(RUN, fake, {"ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP})
        self.assertEqual(code, 2)
        self.assertIn("only a GitHub Actions run may do that", err)
        self.assertEqual(fake.calls, [])

    def test_show_reads_without_a_run_of_the_workflow(self):
        fake = FakeAzure()
        code, _, _, _ = go(SHOW, fake, {"ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP})
        self.assertEqual(code, 0)
        self.assertEqual(fake.writes(), [])

    def test_the_command_takes_no_input_but_the_group_and_the_subscription(self):
        for extra in (["--name", "x"], ["--resource", "x"], ["--everything"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                ro.main([*RUN, *extra], runner=FakeAzure(), environ=dict(ENVIRONMENT), out=lambda text: None)


class Run(unittest.TestCase):
    def test_it_reads_each_one_first_deletes_it_when_it_is_there_reads_back_and_says_one_line_each(self):
        fake = FakeAzure()
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], f"Deleting what Meternaut does not use any more, in resource group {GROUP} and nowhere else:")
        item_lines = [x for x in lines if x.startswith("  the ") and ": " in x]
        self.assertEqual(len(item_lines), len(THE_LIST))
        for (what, name, _, _), line in zip(THE_LIST, item_lines):
            self.assertTrue(line.startswith(f"  {what} {name}: deleted"), line)
        self.assertIn("11 deleted, 0 were not there.", out)
        self.assertEqual(fake.ids() & {i[2].lower() for i in THE_LIST}, set(), "everything on the list is gone")

    def test_it_deletes_in_the_order_of_the_list_and_reads_before_every_delete_and_after(self):
        fake = FakeAzure()
        go(RUN, fake)
        deletes = [c[c.index("--ids") + 1] for c in fake.calls if c[:2] == ["resource", "delete"]]
        self.assertEqual(deletes, [i[2] for i in THE_LIST])
        for resource_id in deletes:
            position = [n for n, c in enumerate(fake.calls) if c[:2] == ["resource", "delete"] and c[c.index("--ids") + 1] == resource_id][0]
            reads = [n for n, c in enumerate(fake.calls) if c[:2] == ["resource", "show"] and c[c.index("--ids") + 1] == resource_id]
            self.assertTrue([n for n in reads if n < position], f"{resource_id} was read before it was deleted")
            self.assertTrue([n for n in reads if n > position], f"{resource_id} was read again after it was deleted")

    def test_it_uses_the_api_version_of_each_type_and_nothing_but_a_delete_of_these_ids(self):
        fake = FakeAzure()
        go(RUN, fake)
        versions = {i[2]: i[3] for i in THE_LIST}
        for call in fake.calls:
            if call[:2] in (["resource", "show"], ["resource", "delete"]):
                self.assertEqual(call[call.index("--api-version") + 1], versions[call[call.index("--ids") + 1]])
        self.assertEqual({tuple(c[:3]) for c in fake.writes()}, {("resource", "delete", "--ids"), ("cognitiveservices", "account", "purge")})

    def test_what_stays_is_never_read_or_deleted(self):
        fake = FakeAzure()
        before = {k for k in fake.ids() if k in {s.lower() for s in WHAT_STAYS}}
        go(RUN, fake)
        self.assertEqual({k for k in fake.ids() if k in {s.lower() for s in WHAT_STAYS}}, before)
        touched = {c[c.index("--ids") + 1].lower() for c in fake.calls if "--ids" in c}
        self.assertEqual(touched, {i[2].lower() for i in THE_LIST})

    def test_the_old_model_account_is_deleted_and_then_purged_so_that_its_name_and_quota_are_free(self):
        fake = FakeAzure()
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        account = f"aif-meternaut-{TOKEN}"
        delete_at = [n for n, c in enumerate(fake.calls) if c[:2] == ["resource", "delete"] and c[c.index("--ids") + 1].endswith(f"/accounts/{account}")][0]
        purge_at = [n for n, c in enumerate(fake.calls) if c[:3] == ["cognitiveservices", "account", "purge"]][0]
        self.assertLess(delete_at, purge_at)
        purge = fake.calls[purge_at]
        self.assertEqual(purge[3:], ["--location", "swedencentral", "--resource-group", GROUP, "--name", account])
        self.assertEqual(fake.deleted_accounts, [], "nothing soft-deleted is left")
        line = [x for x in out.splitlines() if f"the old model account {account}:" in x][0]
        self.assertIn("deleted, and the soft-deleted account was purged (swedencentral), so its name and its quota are free", line)

    def test_a_soft_deleted_account_of_an_earlier_run_is_purged_though_the_account_is_not_there(self):
        fake = FakeAzure(present=False)
        name = f"aif-meternaut-{TOKEN}"
        fake.deleted_accounts.append({"id": f"/subscriptions/{SUB}/providers/Microsoft.CognitiveServices/locations/swedencentral/resourceGroups/{GROUP}/deletedAccounts/{name}", "name": name})
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.deleted_accounts, [])
        self.assertIn(f"the old model account {name}: was not there, and the soft-deleted account was purged (swedencentral)", out)

    def test_a_soft_deleted_account_of_another_group_or_name_is_not_purged(self):
        fake = FakeAzure(present=False)
        other_group = {"id": f"/subscriptions/{SUB}/providers/Microsoft.CognitiveServices/locations/swedencentral/resourceGroups/rg-other/deletedAccounts/aif-meternaut-{TOKEN}", "name": f"aif-meternaut-{TOKEN}"}
        other_name = {"id": f"/subscriptions/{SUB}/providers/Microsoft.CognitiveServices/locations/swedencentral/resourceGroups/{GROUP}/deletedAccounts/aif-meternaut-agents-{TOKEN}", "name": f"aif-meternaut-agents-{TOKEN}"}
        fake.deleted_accounts += [other_group, other_name]
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.deleted_accounts, [other_group, other_name])
        self.assertEqual([c for c in fake.calls if c[:3] == ["cognitiveservices", "account", "purge"]], [])
        self.assertIn("no soft-deleted account of that name is left to purge", out)

    def test_a_second_run_finds_nothing_and_says_so_for_every_line(self):
        fake = FakeAzure()
        go(RUN, fake)
        fake.calls.clear()
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.writes(), [], "a second run deletes nothing")
        item_lines = [x for x in out.splitlines() if x.startswith("  the ") and ": " in x]
        self.assertEqual(len(item_lines), 11)
        for line in item_lines:
            self.assertIn(": was not there", line)
        self.assertIn("0 deleted, 11 were not there.", out)

    def test_an_estate_that_never_had_them_is_fine(self):
        fake = FakeAzure(present=False)
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.writes(), [])
        self.assertIn("0 deleted, 11 were not there.", out)

    def test_a_part_of_the_list_that_is_there_is_deleted_and_the_rest_is_not_there(self):
        fake = FakeAzure(present=False)
        for item in (THE_LIST[3], THE_LIST[7]):
            fake.resources[item[2].lower()] = {"id": item[2]}
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn("2 deleted, 9 were not there.", out)
        self.assertIn(f"the Cosmos DB account cosmos-meternaut-{TOKEN}: deleted", out)
        self.assertIn("the event hub usage-control: deleted", out)
        self.assertIn("the event hub ai-usage: was not there", out)

    def test_it_waits_until_a_resource_is_gone(self):
        fake = FakeAzure()
        cosmos = THE_LIST[3][2].lower()
        fake.visible_after_delete[cosmos] = 4
        code, out, _, clock = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn(f"the Cosmos DB account cosmos-meternaut-{TOKEN}: deleted", out)
        self.assertEqual(clock.sleeps, [ro.POLL_SECONDS] * 3)
        self.assertEqual(sum(1 for c in fake.calls if c[:2] == ["resource", "show"] and c[c.index("--ids") + 1].lower() == cosmos), 1 + 4)

    def test_a_resource_that_does_not_go_stops_the_run_and_nothing_after_it_is_touched(self):
        fake = FakeAzure()
        fake.visible_after_delete[THE_LIST[3][2].lower()] = 10 ** 6
        code, out, err, clock = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn(f"the Cosmos DB account cosmos-meternaut-{TOKEN} is still there 15 minutes after the delete was accepted", err)
        self.assertIn("Nothing after it was touched: run the action again", err)
        self.assertGreaterEqual(clock.now, ro.WAIT_SECONDS)
        for _, _, resource_id, _ in THE_LIST[4:]:
            self.assertIn(resource_id.lower(), fake.ids(), "what comes after is still there")
        self.assertNotIn(f"the Cosmos DB account cosmos-meternaut-{TOKEN}: deleted", out, "no line says that it was deleted: it was not seen to be gone")

    def test_a_refused_delete_stops_at_once_with_the_first_line_of_the_answer(self):
        fake = FakeAzure()
        fake.delete_errors[THE_LIST[1][2]] = "ERROR: (ScopeLocked) The scope cannot perform delete operation because following scope(s) are locked.\nsecond line"
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("the usage app's plan plan-meternaut-usage could not be deleted: ERROR: (ScopeLocked)", err)
        self.assertNotIn("second line", err)
        self.assertIn(THE_LIST[2][2].lower(), fake.ids())
        self.assertFalse([c for c in fake.calls if c[:2] == ["resource", "delete"] and c[c.index("--ids") + 1] == THE_LIST[2][2]])

    def test_a_read_that_fails_for_another_reason_than_not_found_stops_before_that_resource_is_deleted(self):
        fake = FakeAzure()
        fake.read_errors[THE_LIST[0][2]] = "ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Web/sites/read'."
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("could not be read: ERROR: (AuthorizationFailed)", err)
        self.assertEqual(fake.writes(), [])

    def test_a_missing_resource_group_is_an_error_and_not_a_line_that_says_was_not_there(self):
        fake = FakeAzure(present=False, stays=False)
        fake.read_errors[THE_LIST[0][2]] = f"ERROR: (ResourceGroupNotFound) Resource group '{GROUP}' could not be found."
        code, _, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("the resource group is not there", err)

    def test_a_purge_that_azure_refuses_ends_with_the_one_command_for_a_person(self):
        fake = FakeAzure()
        fake.purge_error = "ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts/delete'."
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn(f"az cognitiveservices account purge --location swedencentral --resource-group {GROUP} --name aif-meternaut-{TOKEN}", err)
        self.assertIn(f"the soft-deleted account aif-meternaut-{TOKEN} could not be purged", err)
        self.assertIn(THE_LIST[-1][2].lower(), fake.ids(), "the identity after the account is not touched when the purge stops the run")

    def test_a_purge_that_does_not_show_in_the_list_in_time_stops_the_run(self):
        fake = FakeAzure()
        fake.stuck_after_purge = True
        code, _, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("is still listed 15 minutes after the purge was accepted", err)

    def test_the_summary_file_gets_the_lines(self):
        fake = FakeAzure()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            code, out, _, _ = go([*RUN, "--summary", str(path)], fake)
            text = path.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("### What Meternaut does not use any more, and was deleted\n\n```\n"))
        self.assertIn("11 deleted, 0 were not there.", text)

    def test_the_summary_is_written_when_the_run_stops_too(self):
        fake = FakeAzure()
        fake.delete_errors[THE_LIST[2][2]] = "ERROR: (ScopeLocked) locked"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            code, _, _, _ = go([*RUN, "--summary", str(path)], fake)
            text = path.read_text(encoding="utf-8")
        self.assertEqual(code, 1)
        self.assertIn("the usage function app func-meternaut-usage-", text)


class Leftovers(unittest.TestCase):
    """A deleted identity leaves its role assignments behind. They are listed, and never deleted."""

    def give(self, fake, principal, scope, role="00000000-0000-0000-0000-00000000000b"):
        fake.assignments.append({"id": f"{scope}/providers/Microsoft.Authorization/roleAssignments/{len(fake.assignments) + 1:08d}-0000-4000-8000-000000000000",
                                 "principal": principal, "scope": scope, "role": role})

    def test_the_assignments_of_the_deleted_identities_in_the_group_are_listed_and_not_deleted(self):
        fake = FakeAzure()
        storage = f"{BASE}/Microsoft.Storage/storageAccounts/stmeternautfn{TOKEN}"
        insights = f"{BASE}/Microsoft.Insights/components/appi-meternaut"
        self.give(fake, USAGE_PRINCIPAL, storage)
        self.give(fake, USAGE_PRINCIPAL, insights)
        self.give(fake, IDENTITY_PRINCIPAL, f"/subscriptions/{SUB}/resourceGroups/{GROUP}")
        self.give(fake, USAGE_PRINCIPAL, f"/subscriptions/{SUB}/resourceGroups/rg-other")
        self.give(fake, "cccccccc-0000-4000-8000-000000000003", storage)
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn("3 role assignment(s) of the deleted identities of the usage app are left at or below the resource group", out)
        self.assertIn("None was deleted", out)
        self.assertEqual(out.count("roleAssignments/"), 3)
        self.assertNotIn("rg-other", out)
        self.assertNotIn("cccccccc", out)
        self.assertEqual(len(fake.assignments), 5, "no role assignment was deleted")
        self.assertEqual([c for c in fake.calls if c[:2] == ["role", "assignment"]], [])

    def test_nothing_left_is_said_so(self):
        fake = FakeAzure()
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn("No role assignment of the usage app's identities is left in the resource group.", out)

    def test_the_object_ids_are_read_before_the_identities_are_deleted(self):
        fake = FakeAzure()
        go(RUN, fake)
        first_delete = next(n for n, c in enumerate(fake.calls) if c[:2] == ["resource", "delete"])
        reads = [c for c in fake.calls[:first_delete + 1] if c[:2] == ["resource", "show"]]
        self.assertEqual(reads[0][reads[0].index("--ids") + 1], THE_LIST[0][2], "the usage app is read first, and its identity's object id is taken from that read")

    def test_when_the_identities_were_not_there_it_has_nothing_to_look_for(self):
        fake = FakeAzure(present=False)
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn("No identity of the usage app was found, so there is no role assignment of it to look for.", out)

    def test_the_principal_is_taken_from_the_identity_of_the_app_and_from_the_properties_of_the_user_assigned_identity(self):
        items = ro.items(SUB, GROUP)
        self.assertEqual(ro.principal_of(items[0], {"identity": {"principalId": USAGE_PRINCIPAL.upper()}}), USAGE_PRINCIPAL)
        self.assertEqual(ro.principal_of(items[-1], {"properties": {"principalId": IDENTITY_PRINCIPAL}}), IDENTITY_PRINCIPAL)
        self.assertIsNone(ro.principal_of(items[0], {"identity": {"principalId": "not-an-id"}}))
        self.assertIsNone(ro.principal_of(items[1], {"identity": {"principalId": USAGE_PRINCIPAL}}), "no other resource of the list holds an identity that is looked for")
        self.assertIsNone(ro.principal_of(items[0], None))


class Show(unittest.TestCase):
    def test_it_says_what_is_still_there_and_changes_nothing(self):
        fake = FakeAzure()
        fake.deleted_accounts.append({"id": f"/subscriptions/{SUB}/providers/Microsoft.CognitiveServices/locations/swedencentral/resourceGroups/{GROUP}/deletedAccounts/aif-meternaut-{TOKEN}"})
        code, out, _, _ = go(SHOW, fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.writes(), [])
        self.assertEqual(len([x for x in out.splitlines() if x.endswith(": still there")]), 11)
        self.assertIn("the soft-deleted old model account", out)

    def test_it_says_was_not_there_for_what_is_gone(self):
        fake = FakeAzure(present=False)
        code, out, _, _ = go(SHOW, fake)
        self.assertEqual(code, 0)
        self.assertEqual(len([x for x in out.splitlines() if x.endswith(": was not there")]), 11)

    def test_it_says_which_apps_are_integrated_with_the_function_subnet_and_changes_nothing(self):
        fake = FakeAzure()
        code, out, _, _ = go(SHOW, fake)
        self.assertEqual(code, 0)
        self.assertIn(f"  the function subnet snet-func (delegated to Microsoft.App/environments): apps integrated with it: func-meternaut-usage-{TOKEN} (plan plan-meternaut-usage)", out)
        self.assertEqual(fake.writes(), [])
        go(RUN, fake)
        code, out, _, _ = go(SHOW, fake)
        self.assertIn("apps integrated with it: none", out)

    def test_a_subnet_that_is_not_there_is_said_and_is_no_error(self):
        fake = FakeAzure(present=False, stays=False)
        code, out, _, _ = go(SHOW, fake)
        self.assertEqual(code, 0)
        self.assertIn("  the function subnet snet-func: is not there (the action model-side makes it)", out)


class TheFunctionSubnet(unittest.TestCase):
    """The action cases, on Flex Consumption, refuses to deploy while another app holds snet-func: the run reads it after the deletes and says that it is free."""

    FREE = "The function subnet snet-func is free: no app is integrated with it, so the action cases can use it."

    def test_after_the_deletes_it_reads_the_subnet_and_the_apps_and_says_that_snet_func_is_free(self):
        fake = FakeAzure()
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("11 deleted, 0 were not there."), out.index("The function subnet snet-func is delegated to Microsoft.App/environments."))
        self.assertIn("The subnet carries no service association link.", out)
        self.assertIn(self.FREE, out)
        last_delete = max(n for n, c in enumerate(fake.calls) if c[:2] == ["resource", "delete"])
        subnet_reads = [n for n, c in enumerate(fake.calls) if c[0] == "rest" and "/subnets/snet-func?api-version=2025-05-01" in c[c.index("--url") + 1]]
        app_reads = [n for n, c in enumerate(fake.calls) if c[0] == "rest" and "/providers/Microsoft.Web/sites?api-version=2024-04-01" in c[c.index("--url") + 1]]
        self.assertTrue(subnet_reads and app_reads)
        self.assertGreater(min(subnet_reads), last_delete, "the subnet is read back after the last delete")
        self.assertGreater(min(app_reads), last_delete, "the apps are listed after the last delete")
        self.assertNotIn(THE_LIST[0][2].lower(), fake.ids())

    def test_the_cases_app_on_the_subnet_is_what_is_meant_and_is_said_so(self):
        fake = FakeAzure()
        fake.integration[CASES_SITE.lower()] = SUBNET
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn(f"The function subnet snet-func is free for the cases app: only the cases app func-meternaut-cases-{TOKEN} is integrated with it, as intended.", out)
        self.assertNotIn(self.FREE, out)

    def test_the_teams_bots_app_on_the_subnet_is_allowed_is_said_so_and_is_never_deleted(self):
        fake = FakeAzure()
        bot = fake.add_app(f"func-meternaut-teams-{TOKEN}", SUBNET, "plan-meternaut-teams")
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertIn(f"The function subnet snet-func is free for the cases app: only the Teams bot's app func-meternaut-teams-{TOKEN} is integrated with it, as intended.", out)
        self.assertNotIn(self.FREE, out)
        self.assertIn(bot.lower(), fake.ids(), "an app that is not on the list is never deleted")

    def test_the_cases_app_and_the_teams_bots_app_on_the_subnet_are_both_named(self):
        fake = FakeAzure()
        fake.integration[CASES_SITE.lower()] = SUBNET
        fake.add_app(f"func-meternaut-teams-{TOKEN}", SUBNET, "plan-meternaut-teams")
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertIn(f"only the cases app func-meternaut-cases-{TOKEN} and the Teams bot's app func-meternaut-teams-{TOKEN} are integrated with it, as intended.", out)

    def test_an_app_that_only_looks_like_the_teams_bots_app_still_holds_the_subnet(self):
        fake = FakeAzure()
        fake.add_app("func-meternaut-teams-00000000", SUBNET, "plan-elsewhere")
        fake.add_app(f"func-meternaut-teams-{TOKEN}-copy", SUBNET, "plan-elsewhere")
        code, _, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("is still taken by func-meternaut-teams-00000000 (plan plan-elsewhere), func-meternaut-teams-" + TOKEN + "-copy (plan plan-elsewhere)", err)

    def test_another_app_on_the_subnet_fails_the_run_after_fifteen_minutes_and_names_the_app_and_its_plan(self):
        fake = FakeAzure()
        elsewhere = fake.add_app("func-elsewhere", SUBNET, "plan-elsewhere")
        code, out, err, clock = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("the function subnet snet-func is still taken by func-elsewhere (plan plan-elsewhere), 15 minutes after the deletes", err)
        self.assertIn("The action cases needs it for itself", err)
        self.assertNotIn("is free", out)
        self.assertGreaterEqual(clock.now, ro.WAIT_SECONDS)
        self.assertIn(elsewhere.lower(), fake.ids(), "an app that is not on the list is never deleted")
        self.assertEqual({c[c.index("--ids") + 1] for c in fake.calls if c[:2] == ["resource", "delete"]}, {i[2] for i in THE_LIST})

    def test_the_usage_app_that_is_still_listed_for_a_while_after_it_is_gone_is_waited_for(self):
        fake = FakeAzure()
        fake.ghosts[THE_LIST[0][2].lower()] = 3
        code, out, _, clock = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertEqual(clock.sleeps, [ro.POLL_SECONDS] * 3)
        self.assertIn(self.FREE, out)

    def test_the_usage_app_that_stays_in_the_list_fails_the_run_and_is_named(self):
        fake = FakeAzure()
        fake.ghosts[THE_LIST[0][2].lower()] = 10 ** 6
        code, _, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn(f"is still taken by func-meternaut-usage-{TOKEN} (plan plan-meternaut-usage)", err)

    def test_a_subnet_that_is_not_there_is_said_and_is_no_error_and_no_app_is_listed(self):
        fake = FakeAzure()
        del fake.resources[SUBNET.lower()]
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertIn("The function subnet snet-func is not there, so no app is integrated with it. The action model-side makes it, and the action cases needs it.", out)
        self.assertEqual([u for _, u in fake.rest_urls if "/providers/Microsoft.Web/sites?" in u], [])

    def test_the_platforms_links_on_the_subnet_are_said_as_information_and_do_not_fail_the_run(self):
        fake = FakeAzure()
        fake.links = [{"name": "legionservicelink", "properties": {"linkedResourceType": "Microsoft.App/environments", "link": THE_LIST[1][2]}}]
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn(f"The platform's links on the subnet (service association links), as read: legionservicelink (Microsoft.App/environments, {THE_LIST[1][2]}).", out)
        self.assertIn("A link can stay for a while after its app is gone: it does not stop the action cases, which looks at the apps.", out)
        self.assertIn(self.FREE, out)

    def test_a_subnet_that_is_delegated_to_something_else_is_said_and_the_run_does_not_judge_it(self):
        fake = FakeAzure()
        fake.delegations = ["Microsoft.Web/serverFarms"]
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn("The function subnet snet-func is delegated to Microsoft.Web/serverFarms.", out)

    def test_an_app_on_another_subnet_or_none_or_on_a_subnet_of_another_network_does_not_hold_it(self):
        fake = FakeAzure()
        fake.add_app("func-on-the-web-subnet", WEB_SUBNET)
        fake.add_app("func-with-no-integration", None)
        fake.add_app("func-on-another-network", SUBNET.replace("vnet-meternaut", "vnet-other"))
        code, out, _, _ = go(RUN, fake)
        self.assertEqual(code, 0)
        self.assertIn(self.FREE, out)

    def test_the_ids_are_compared_without_regard_to_case(self):
        fake = FakeAzure()
        fake.add_app("func-elsewhere", SUBNET.replace("resourceGroups", "resourcegroups").replace("subnets", "SUBNETS").upper())
        code, _, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("is still taken by func-elsewhere", err)

    def test_the_apps_are_listed_page_by_page(self):
        fake = FakeAzure()
        fake.page_size = 1
        fake.add_app("func-elsewhere", SUBNET)
        code, _, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("is still taken by func-elsewhere", err)
        self.assertGreaterEqual(len([u for _, u in fake.rest_urls if "/providers/Microsoft.Web/sites?" in u and "skiptoken=1" in u]), 1, "the second page was read")

    def test_only_gets_are_made_and_only_of_the_subnet_the_apps_and_the_assignments_in_the_project_group(self):
        fake = FakeAzure()
        go(RUN, fake)
        self.assertEqual({method for method, _ in fake.rest_urls}, {"get"})
        kinds = {"subnet" if "/subnets/" in url else "apps" if "/providers/Microsoft.Web/sites?" in url else "assignments" if "roleAssignments" in url else url for _, url in fake.rest_urls}
        self.assertEqual(kinds, {"subnet", "apps", "assignments"})
        for _, url in fake.rest_urls:
            self.assertIn(f"/subscriptions/{SUB}/resourceGroups/{GROUP}/", url)

    def test_a_subnet_that_cannot_be_read_fails_the_run_and_the_leftover_assignments_are_still_looked_for(self):
        fake = FakeAzure()
        fake.rest_errors["/subnets/snet-func"] = "ERROR: (AuthorizationFailed) The client does not have authorization to perform action 'Microsoft.Network/virtualNetworks/subnets/read'."
        code, out, err, _ = go(RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("the function subnet snet-func could not be read: ERROR: (AuthorizationFailed)", err)
        self.assertIn("No role assignment of the usage app's identities is left in the resource group.", out)
        self.assertEqual(fake.ids() & {i[2].lower() for i in THE_LIST}, set(), "everything on the list was deleted before the subnet was read")

    def test_the_summary_file_says_that_snet_func_is_free(self):
        fake = FakeAzure()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            code, _, _, _ = go([*RUN, "--summary", str(path)], fake)
            text = path.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn(self.FREE, text)

    def test_the_names_are_the_ones_of_the_template_and_the_parameter_builder(self):
        template = (ROOT / "environment" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn("param workload string = 'meternaut'", template)
        self.assertIn(f"name: 'vnet-${{workload}}'", template)
        self.assertEqual(ro.NETWORK, "vnet-meternaut")
        self.assertIn(f"name: '{ro.FUNCTION_SUBNET}'", template)
        self.assertEqual(ro.FUNCTION_SUBNET, ep.CASES_SUBNET_NAMES["Flex"], "the subnet that the Flex Consumption app of the cases uses")
        self.assertEqual(ro.subnet_id(SUB, GROUP), SUBNET)


WORKFLOW = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8")


def step(title: str) -> str:
    start = WORKFLOW.index(f"      - name: {title}\n")
    end = WORKFLOW.find("\n      - name: ", start + 1)
    return WORKFLOW[start:end if end != -1 else len(WORKFLOW)]


class TheHubAction(unittest.TestCase):
    def options(self):
        block = WORKFLOW[WORKFLOW.index("        options:\n"):WORKFLOW.index("      public_ai_gateway_requested:")]
        return re.findall(r"^          - (\S+)$", block, re.M)

    def test_the_action_is_offered_and_the_old_names_are_not(self):
        options = self.options()
        self.assertIn("retire-old", options)
        self.assertIn("base", options)
        self.assertNotIn("recording", options)
        self.assertNotIn("recording-check", options)

    def test_its_description_says_in_plain_words_what_it_deletes_and_that_it_takes_no_input(self):
        text = WORKFLOW[WORKFLOW.index("description: \"what-if"):WORKFLOW.index("type: choice")]
        for words in ("retire-old: delete what Meternaut does not use any more, in the project's resource group and nowhere else, and nothing else",
                      "the usage function app, its plan and its private endpoint, the Cosmos DB account and its private endpoint, and the event hubs ai-usage, pii-usage and usage-control",
                      "the old model account (its private endpoint, and then the account itself, which it purges so that its name and its quota are free)",
                      "and the identity id-meternaut-usage", "it reads each one first, deletes it when it is there, reads back until it is gone",
                      "says on one line for each one whether it was deleted or was not there", "it takes no input, needs no other action first and is safe to run twice",
                      "base: the parts that the other actions build on, which are a Log Analytics workspace, an Application Insights component and a storage account, with the storage account's private endpoints and without any key"):
            self.assertIn(words, text)

    def test_no_new_input_is_added_for_it(self):
        inputs = re.findall(r"^      ([a-z_]+):$", WORKFLOW[WORKFLOW.index("    inputs:\n"):WORKFLOW.index("permissions:")], re.M)
        self.assertEqual(inputs, ["action", "minutes", "public_ai_gateway_requested", "public_teams_bot_requested", "plant_public_ip", "evals_command", "evals_judge", "redteam_mode"], "minutes is the input of page-latency; the last three are the inputs of the checks of the agents: retire-old has none")
        self.assertNotIn("inputs.minutes", step("Delete what Meternaut does not use any more, in the project's resource group"))

    def test_one_step_runs_the_tool_with_the_workflows_own_group_and_subscription_and_nothing_else(self):
        block = step("Delete what Meternaut does not use any more, in the project's resource group")
        self.assertIn("if: inputs.action == 'retire-old'", block)
        calls = re.findall(r"python3 tools/retire-old\.py (.*)", block)
        self.assertEqual(calls, ['run --subscription "$ENV_SUBSCRIPTION_ID" --resource-group "$ENV_RESOURCE_GROUP" --summary "$GITHUB_STEP_SUMMARY"'])
        self.assertNotIn("az ", re.sub(r"#.*", "", block), "the step calls the tool and no az command of its own")
        self.assertNotIn("inputs.", block.replace("if: inputs.action == 'retire-old'", ""))
        self.assertIn("timeout-minutes: 60", block)

    def test_it_needs_no_other_action_first_and_nothing_else_runs_for_it_but_the_common_steps_and_a_fresh_sign_in(self):
        steps = re.split(r"\n(?=      - name: )", WORKFLOW)
        only = [s.splitlines()[0].strip()[8:] for s in steps if re.search(r"if: [^\n]*inputs\.action == 'retire-old'", s)]
        self.assertEqual(only, ["Sign in to Azure again for the retirement, because the first sign-in's credential lasts five minutes",
                                "Delete what Meternaut does not use any more, in the project's resource group"])

    def test_what_if_shows_what_it_would_delete_and_deletes_nothing(self):
        block = step("What the model side, the base, the Foundry resource, the first cases, the Operator and the AI Gateway's templates would change")
        self.assertIn('python3 tools/retire-old.py show --subscription "$ENV_SUBSCRIPTION_ID" --resource-group "$ENV_RESOURCE_GROUP"', block)
        self.assertIn('python3 tools/retire-old.py show --list event-hubs --subscription "$ENV_SUBSCRIPTION_ID" --resource-group "$ENV_RESOURCE_GROUP"', block)
        self.assertNotIn("retire-old.py run", block)

    def test_the_tool_is_run_only_by_these_four_steps(self):
        self.assertEqual(len(re.findall(r"python3 tools/retire-old\.py run", WORKFLOW)), 2, "retire-old and retire-event-hubs")
        self.assertEqual(len(re.findall(r"python3 tools/retire-old\.py show", WORKFLOW)), 2, "the preview of each")

    def test_the_summary_says_what_was_done_and_what_stays(self):
        text = WORKFLOW[WORKFLOW.index("retire-old) echo \"What Meternaut does not use any more was deleted"):]
        text = text[:text.index(";;")]
        for words in ("and nothing else", "The Event Hubs namespace (the action \\`retire-event-hubs\\` deletes it), the storage account, the workspace, Application Insights and every subnet were not touched",
                      "Running \\`retire-old\\` again is safe: it finds nothing.",
                      "The function subnet \\`snet-func\\` was read back after the deletes: it is free (no app but the cases app and the Teams bot's app is integrated with it), so the action \\`cases\\` can put the web page's app on it if the app is on Flex Consumption"):
            self.assertIn(words, text)

    def test_the_stopped_summary_says_what_to_do_when_another_app_holds_the_function_subnet(self):
        text = WORKFLOW[WORKFLOW.index("retire-old) echo \"The run stopped before it had deleted everything"):]
        text = text[:text.index(";;")]
        for words in ("the lines stop at the function subnet \\`snet-func\\`, another app still holds it", "the line names that app and its plan", "a person deletes that app or moves it to another subnet"):
            self.assertIn(words, text)

    def test_the_description_says_that_it_reads_back_that_the_function_subnet_is_free(self):
        text = WORKFLOW[WORKFLOW.index("description: \"what-if"):WORKFLOW.index("type: choice")]
        self.assertIn("and then reads back that the function subnet snet-func is free (no app but the cases app and the Teams bot's app is integrated with it), which the action cases needs only while the web page's app is on Flex Consumption", text)

    def test_the_old_settings_are_read_by_nothing(self):
        for name in ("GATEWAY_RESOURCE_ID", "GATEWAY_APPINSIGHTS_ID", "RECORDING_READER_IDS"):
            self.assertNotIn(name, WORKFLOW)


EVENT_HUBS_RUN = ["run", "--list", "event-hubs", "--subscription", SUB, "--resource-group", GROUP]
EVENT_HUBS_SHOW = ["show", "--list", "event-hubs", "--subscription", SUB, "--resource-group", GROUP]
STAYS_WHEN_THE_NAMESPACE_GOES = [stays for stays in WHAT_STAYS if "evhns" not in stays and "azure-webjobs-eventhub" not in stays]


def estate(queue: bool = True, event_hubs: bool = True) -> FakeAzure:
    """The project's group as it is after cases-run: the base, the cases app and the network, the control queue (unless `queue` is False), and the Event Hubs namespace with its private endpoint, its hub and its checkpoint container."""
    fake = FakeAzure(present=False, stays=True)
    if not event_hubs:
        for resource_id in [r[2] for r in THE_EVENT_HUBS_LIST] + [f"{NAMESPACE}/eventhubs/cases-control"]:
            del fake.resources[resource_id.lower()]
    if not queue:
        del fake.resources[CONTROL_QUEUE.lower()]
    return fake


class TheEventHubsList(unittest.TestCase):
    def test_the_list_is_exactly_this_and_in_this_order(self):
        got = [(i.what, i.name, i.id, i.api_version) for i in ro.event_hub_items(SUB, GROUP)]
        self.assertEqual(got, THE_EVENT_HUBS_LIST)

    def test_the_private_endpoint_goes_first_then_the_namespace_then_the_checkpoints(self):
        self.assertEqual([i.name for i in ro.event_hub_items(SUB, GROUP)], [f"pe-evhns-meternaut-{TOKEN}", f"evhns-meternaut-{TOKEN}", "azure-webjobs-eventhub"])

    def test_every_id_is_in_the_project_group_and_nowhere_else(self):
        for item in ro.event_hub_items(SUB, GROUP):
            self.assertTrue(item.id.startswith(f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/"), item.id)
        for other_group in ("rg-other", "rg-example2"):
            self.assertFalse([i for i in ro.event_hub_items(SUB, other_group) if f"/resourceGroups/{GROUP}/" in i.id])

    def test_nothing_that_stays_is_on_the_list_and_the_two_lists_share_nothing(self):
        ids = {i.id.lower() for i in ro.event_hub_items(SUB, GROUP)}
        for stays in STAYS_WHEN_THE_NAMESPACE_GOES:
            self.assertNotIn(stays.lower(), ids)
        self.assertFalse(ids & {i.id.lower() for i in ro.items(SUB, GROUP)})
        self.assertFalse([i for i in ids if "/subnets/" in i or "virtualnetworks/vnet" in i or "workspaces" in i or "components/appi" in i or "/queues/" in i or "/sites/" in i])

    def test_the_names_are_the_ones_that_the_parameter_builder_made_and_the_template_made_before_this_change(self):
        self.assertEqual(ro.digest(SUB, GROUP), ep.digest(SUB, GROUP))
        self.assertEqual(ep.base_names(SUB, GROUP)["storage_account_name"], STORAGE_ACCOUNT, "the account that holds the checkpoint container and the control queue")
        base = subprocess_text("git", "show", "476ae26:environment/base/main.bicep")
        params = subprocess_text("git", "show", "476ae26:tools/environment-params.py")
        if base is None or params is None:
            self.skipTest("the history is not available")
        self.assertIn('"event_hub_namespace": f"evhns-meternaut-{token}"', params)
        self.assertIn("resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01'", base)
        self.assertIn("name: 'pe-${eventHubNamespaceName}'", base)
        self.assertIn("'azure-webjobs-eventhub'", base)

    def test_no_template_makes_any_of_it_any_more(self):
        for path in ("environment/base/main.bicep", "environment/cases/main.bicep", "environment/operator/main.bicep"):
            text = (ROOT / path).read_text(encoding="utf-8")
            for word in ("Microsoft.EventHub", "azure-webjobs-eventhub", "eventHubNamespaceName"):
                self.assertNotIn(word, text, f"{path} still names {word}")

    def test_the_queue_that_the_guard_reads_is_the_one_that_the_cases_template_makes(self):
        self.assertEqual(ro.CONTROL_QUEUE, "cases-control")
        self.assertIn(f"var controlQueueName = '{ro.CONTROL_QUEUE}'", (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8"))
        self.assertEqual(ro.control_queue_url(SUB, GROUP), f"{ro.ARM}{CONTROL_QUEUE}?api-version=2023-05-01")


class RunEventHubs(unittest.TestCase):
    def test_it_reads_each_one_first_deletes_it_in_order_reads_back_and_says_one_line_each(self):
        fake = estate()
        code, out, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 0, err)
        deletes = [c for c in fake.calls if c[:2] == ["resource", "delete"]]
        self.assertEqual([fake.option(c, "--ids") for c in deletes], [r[2] for r in THE_EVENT_HUBS_LIST])
        self.assertEqual([fake.option(c, "--api-version") for c in deletes], [r[3] for r in THE_EVENT_HUBS_LIST])
        lines = [line for line in out.splitlines() if line.startswith("  ")]
        self.assertEqual(lines, [f"  {what} {name}: deleted" for what, name, _, _ in THE_EVENT_HUBS_LIST])
        self.assertIn("3 deleted, 0 were not there.", out)
        for _, _, resource_id, _ in THE_EVENT_HUBS_LIST:
            shows = [i for i, c in enumerate(fake.calls) if c[:2] == ["resource", "show"] and fake.option(c, "--ids") == resource_id]
            delete = next(i for i, c in enumerate(fake.calls) if c[:2] == ["resource", "delete"] and fake.option(c, "--ids") == resource_id)
            self.assertTrue(any(i < delete for i in shows) and any(i > delete for i in shows), f"{resource_id} is read before its delete and again after it")

    def test_only_these_three_go_with_the_hub_of_the_namespace_and_everything_else_stays(self):
        fake = estate()
        before = fake.ids()
        code, _, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertEqual(before - fake.ids(), {r[2].lower() for r in THE_EVENT_HUBS_LIST} | {f"{NAMESPACE}/eventhubs/cases-control".lower()}, "the hub goes with its namespace")
        for stays in STAYS_WHEN_THE_NAMESPACE_GOES:
            self.assertIn(stays.lower(), fake.ids())
        self.assertIn(CONTROL_QUEUE.lower(), fake.ids(), "the queue that replaces the namespace is never touched")
        self.assertEqual(fake.writes(), [c for c in fake.calls if c[:2] == ["resource", "delete"]], "no write but the three deletes: no purge, no role assignment")

    def test_the_control_queue_is_read_before_anything_is_deleted(self):
        fake = estate()
        go(EVENT_HUBS_RUN, fake)
        queue_read = next(i for i, c in enumerate(fake.calls) if c[0] == "rest" and "/queues/cases-control" in fake.option(c, "--url"))
        first_delete = next(i for i, c in enumerate(fake.calls) if c[:2] == ["resource", "delete"])
        self.assertLess(queue_read, first_delete)
        self.assertEqual({m for m, _ in fake.rest_urls}, {"get"})

    def test_without_the_control_queue_nothing_is_deleted_and_the_run_says_why(self):
        fake = estate(queue=False)
        code, out, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 1)
        self.assertEqual(fake.writes(), [])
        self.assertIn("the control queue cases-control is not in the base's storage account", err)
        self.assertIn("Run the action cases, then the action cases-run", err)
        self.assertNotIn("deleted", out)
        self.assertTrue(all(i.lower() in fake.ids() for i in [r[2] for r in THE_EVENT_HUBS_LIST]))

    def test_an_estate_that_never_had_a_namespace_passes_even_without_the_queue(self):
        for queue in (True, False):
            fake = estate(queue=queue, event_hubs=False)
            code, out, err, _ = go(EVENT_HUBS_RUN, fake)
            self.assertEqual(code, 0, err)
            self.assertEqual(fake.writes(), [])
            lines = [line for line in out.splitlines() if line.startswith("  ")]
            self.assertEqual(lines, [f"  {what} {name}: was not there" for what, name, _, _ in THE_EVENT_HUBS_LIST])
            self.assertIn("0 deleted, 3 were not there.", out)

    def test_a_second_run_finds_nothing_and_says_so_for_every_line(self):
        fake = estate()
        self.assertEqual(go(EVENT_HUBS_RUN, fake)[0], 0)
        writes_before = len(fake.writes())
        code, out, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(fake.writes()), writes_before, "the second run writes nothing")
        self.assertIn("0 deleted, 3 were not there.", out)

    def test_a_part_of_the_list_that_is_there_is_deleted_and_the_rest_is_not_there(self):
        fake = estate()
        del fake.resources[THE_EVENT_HUBS_LIST[0][2].lower()]
        del fake.resources[THE_EVENT_HUBS_LIST[2][2].lower()]
        code, out, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertEqual([line for line in out.splitlines() if line.startswith("  ")],
                         [f"  {THE_EVENT_HUBS_LIST[0][0]} {THE_EVENT_HUBS_LIST[0][1]}: was not there", f"  {THE_EVENT_HUBS_LIST[1][0]} {THE_EVENT_HUBS_LIST[1][1]}: deleted",
                          f"  {THE_EVENT_HUBS_LIST[2][0]} {THE_EVENT_HUBS_LIST[2][1]}: was not there"])

    def test_it_waits_until_a_resource_is_gone(self):
        fake = estate()
        fake.visible_after_delete[NAMESPACE.lower()] = 4
        code, out, err, clock = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 0, err)
        self.assertTrue(clock.sleeps)
        self.assertIn("3 deleted", out)

    def test_a_namespace_that_does_not_go_stops_the_run_and_the_container_is_not_touched(self):
        fake = estate()
        fake.visible_after_delete[NAMESPACE.lower()] = 10_000
        code, out, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn(f"the Event Hubs namespace evhns-meternaut-{TOKEN} is still there 15 minutes after the delete was accepted", err)
        self.assertIn("Nothing after it was touched", err)
        self.assertEqual([fake.option(c, "--ids") for c in fake.calls if c[:2] == ["resource", "delete"]], [THE_EVENT_HUBS_LIST[0][2], NAMESPACE])
        self.assertIn(THE_EVENT_HUBS_LIST[2][2].lower(), fake.ids())

    def test_a_refused_delete_stops_at_once_with_the_first_line_of_the_answer(self):
        fake = estate()
        fake.delete_errors[NAMESPACE] = "ERROR: (ScopeLocked) The scope has a lock that prevents this delete.\nmore lines\nand more"
        code, _, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("could not be deleted: ERROR: (ScopeLocked) The scope has a lock that prevents this delete.", err)
        self.assertNotIn("more lines", err)
        self.assertIn(THE_EVENT_HUBS_LIST[2][2].lower(), fake.ids(), "nothing after the refused delete is touched")

    def test_a_read_that_fails_for_another_reason_than_not_found_stops_before_anything_is_deleted(self):
        fake = estate()
        fake.read_errors[THE_EVENT_HUBS_LIST[0][2]] = "ERROR: (TooManyRequests) Slow down."
        code, _, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("could not be read: ERROR: (TooManyRequests) Slow down.", err)
        self.assertEqual(fake.writes(), [])

    def test_a_queue_that_cannot_be_read_stops_the_run_and_nothing_is_deleted(self):
        fake = estate()
        fake.rest_errors["/queues/cases-control"] = "ERROR: (AuthorizationFailed) The client does not have authorization."
        code, _, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("the control queue cases-control could not be read", err)
        self.assertEqual(fake.writes(), [])

    def test_a_missing_resource_group_is_an_error_and_not_a_line_that_says_was_not_there(self):
        fake = estate()
        fake.read_errors[THE_EVENT_HUBS_LIST[0][2]] = f"ERROR: (ResourceGroupNotFound) Resource group '{GROUP}' could not be found."
        code, out, err, _ = go(EVENT_HUBS_RUN, fake)
        self.assertEqual(code, 1)
        self.assertIn("the resource group is not there", err)
        self.assertNotIn("was not there", out)

    def test_the_summary_file_gets_the_lines_under_its_own_title(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = Path(folder) / "summary.md"
            code, out, err, _ = go([*EVENT_HUBS_RUN, "--summary", str(summary)], estate())
            self.assertEqual(code, 0, err)
            text = summary.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("### The Event Hubs namespace that carried the control event, and was deleted\n"))
        for line in out.splitlines():
            self.assertIn(line, text)

    def test_the_summary_is_written_when_the_run_stops_too(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = Path(folder) / "summary.md"
            code, _, err, _ = go([*EVENT_HUBS_RUN, "--summary", str(summary)], estate(queue=False))
            self.assertEqual(code, 1, err)
            self.assertIn("Deleting the Event Hubs namespace", summary.read_text(encoding="utf-8"))

    def test_the_other_list_is_what_it_was_and_never_reads_the_queue_or_the_container(self):
        fake = estate()
        go(RUN, fake)
        for call in fake.calls:
            text = " ".join(call)
            self.assertNotIn("/queues/", text)
            self.assertNotIn("azure-webjobs-eventhub", text)


class RefusalsOfTheEventHubsList(unittest.TestCase):
    def refused(self, argv, environ=None):
        fake = estate()
        code, out, err, _ = go(argv, fake, environ)
        self.assertEqual(code, 2, err)
        self.assertEqual(fake.calls, [], "nothing is read or changed when it refuses")
        self.assertEqual(out, "")
        return err

    def test_another_resource_group_or_subscription_is_refused_before_anything_is_read(self):
        self.assertIn("ENV_RESOURCE_GROUP", self.refused(["run", "--list", "event-hubs", "--subscription", SUB, "--resource-group", "rg-other"]))
        self.refused(["show", "--list", "event-hubs", "--subscription", SUB, "--resource-group", "rg-other"])
        self.assertIn("ENV_SUBSCRIPTION_ID", self.refused(["run", "--list", "event-hubs", "--subscription", "99999999-8888-7777-6666-555555555555", "--resource-group", GROUP]))

    def test_only_a_github_actions_run_may_delete(self):
        err = self.refused(EVENT_HUBS_RUN, {"ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP})
        self.assertIn("only a GitHub Actions run may do that", err)

    def test_a_list_that_is_not_one_is_refused_by_the_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ro.main(["run", "--list", "everything", "--subscription", SUB, "--resource-group", GROUP], runner=FakeAzure(), environ=dict(ENVIRONMENT), out=lambda text: None)

    def test_the_command_takes_no_input_but_the_list_the_group_and_the_subscription(self):
        for extra in (["--name", "x"], ["--namespace", "x"], ["--queue", "x"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                ro.main([*EVENT_HUBS_RUN, *extra], runner=FakeAzure(), environ=dict(ENVIRONMENT), out=lambda text: None)


class ShowEventHubs(unittest.TestCase):
    def test_it_says_what_is_still_there_and_whether_the_queue_is_there_and_changes_nothing(self):
        fake = estate()
        code, out, err, _ = go(EVENT_HUBS_SHOW, fake, {"ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP})
        self.assertEqual(code, 0, err)
        self.assertEqual(fake.writes(), [])
        self.assertEqual({m for m, _ in fake.rest_urls}, {"get"})
        for what, name, _, _ in THE_EVENT_HUBS_LIST:
            self.assertIn(f"  {what} {name}: still there", out)
        self.assertIn("the control queue cases-control, which replaces the namespace: is there", out)

    def test_it_says_was_not_there_for_what_is_gone_and_when_the_queue_is_not_there(self):
        fake = estate(queue=False, event_hubs=False)
        code, out, err, _ = go(EVENT_HUBS_SHOW, fake)
        self.assertEqual(code, 0, err)
        for what, name, _, _ in THE_EVENT_HUBS_LIST:
            self.assertIn(f"  {what} {name}: was not there", out)
        self.assertIn("is not there (the action cases makes it, and nothing of the list is deleted while it is not there)", out)

    def test_the_old_list_is_still_the_default_of_show(self):
        fake = estate()
        code, out, err, _ = go(SHOW, fake)
        self.assertEqual(code, 0, err)
        self.assertIn("what Meternaut does not use any more", out)
        self.assertNotIn("Event Hubs namespace's private endpoint", out)


class TheEventHubsAction(unittest.TestCase):
    TITLE = "Delete the Event Hubs namespace that carried the control event, its private endpoint and its checkpoint container, in the project's resource group"
    LOGIN = "Sign in to Azure again for the retirement of the Event Hubs namespace, because the first sign-in's credential lasts five minutes"

    def test_the_action_is_offered_after_retire_old_and_before_the_rest(self):
        block = WORKFLOW[WORKFLOW.index("        options:\n"):WORKFLOW.index("      public_ai_gateway_requested:")]
        options = re.findall(r"^          - (\S+)$", block, re.M)
        self.assertEqual(options[options.index("retire-old") + 1], "retire-event-hubs")

    def test_its_description_says_in_plain_words_what_it_deletes_and_when_to_run_it(self):
        text = WORKFLOW[WORKFLOW.index("description: \"what-if"):WORKFLOW.index("type: choice")]
        for words in ("retire-event-hubs: delete the Event Hubs namespace that carried the control event of the cases app before the control message moved to a Storage queue, and its private endpoint, in the project's resource group and nowhere else",
                      "the private endpoint, then the namespace (which takes its hub cases-control and that hub's consumer group with it), then the container azure-webjobs-eventhub in the storage account, which held the namespace's checkpoints",
                      "run it only after the action cases-run has proved the queue path, because it removes the old channel",
                      "it refuses to delete anything while the control queue cases-control is not there, takes no input and is safe to run twice, and on an estate that never had a namespace it finds nothing and passes"):
            self.assertIn(words, text)

    def test_one_step_runs_the_tool_with_the_list_and_the_workflows_own_group_and_subscription_and_nothing_else(self):
        block = step(self.TITLE)
        self.assertIn("if: inputs.action == 'retire-event-hubs'", block)
        calls = re.findall(r"python3 tools/retire-old\.py (.*)", block)
        self.assertEqual(calls, ['run --list event-hubs --subscription "$ENV_SUBSCRIPTION_ID" --resource-group "$ENV_RESOURCE_GROUP" --summary "$GITHUB_STEP_SUMMARY"'])
        self.assertNotIn("az ", re.sub(r"#.*", "", block), "the step calls the tool and no az command of its own")
        self.assertNotIn("inputs.", block.replace("if: inputs.action == 'retire-event-hubs'", ""))
        self.assertIn("timeout-minutes: 60", block)

    def test_nothing_else_runs_for_it_but_the_common_steps_and_a_fresh_sign_in(self):
        steps = re.split(r"\n(?=      - name: )", WORKFLOW)
        only = [s.splitlines()[0].strip()[8:] for s in steps if re.search(r"if: [^\n]*inputs\.action == 'retire-event-hubs'", s)]
        self.assertEqual(only, [self.LOGIN, self.TITLE])

    def test_it_is_a_separate_action_that_no_other_action_runs_or_needs(self):
        self.assertNotRegex(step("Delete what Meternaut does not use any more, in the project's resource group"), r"--list")
        for title in ("Deploy the base", "Deploy the first cases", "Deploy the Operator, its identity and the subnet of its container groups"):
            self.assertNotIn("retire-old.py", step(title), "no deploy deletes the namespace: it has an action of its own, run after cases-run")

    def test_the_summaries_say_what_was_done_and_what_to_do_when_it_stopped(self):
        done = WORKFLOW[WORKFLOW.index("retire-event-hubs) echo \"The Event Hubs namespace that carried the control event was deleted"):]
        done = done[:done.index(";;")]
        for words in ("its private endpoint, the namespace (with its hub \\`cases-control\\` and that hub's consumer group, and whatever else was in it), and the container \\`azure-webjobs-eventhub\\`",
                      "each was read back until it was gone", "which this action reads before it deletes anything and does not touch",
                      "Running \\`retire-event-hubs\\` again is safe: it finds nothing."):
            self.assertIn(words, done)
        stopped = WORKFLOW[WORKFLOW.index("retire-event-hubs) echo \"The run stopped before it had deleted everything"):]
        stopped = stopped[:stopped.index(";;")]
        for words in ("the control queue \\`cases-control\\` is not there, so nothing was deleted: run \\`cases\\` and then \\`cases-run\\` first", "Running \\`retire-event-hubs\\` again is safe"):
            self.assertIn(words, stopped)

    def test_what_if_and_the_actions_own_prechecks_do_not_read_the_namespace(self):
        text = re.sub(r"^\s*#.*$", "", WORKFLOW, flags=re.M)
        for forbidden in ("Microsoft.EventHub", "servicebus.windows.net", "EVENT_HUB_NAMESPACE", "event_hub_namespace", "eventHubNamespaceName"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
