#!/usr/bin/env python3
"""Deletes what Meternaut does not use any more, in the project's own resource group and nowhere else (standard library only).

    python tools/retire-old.py show [--list old|event-hubs] --subscription S --resource-group G
    python tools/retire-old.py run  [--list old|event-hubs] --subscription S --resource-group G [--summary <file>]

It is the code of two actions of the Hub workflow, each with a list of its own: `retire-old` (the list `old`, the default) and `retire-event-hubs` (the list `event-hubs`, described at the end).

The list `old`. On 2026-11-07 the owner ordered the old leftovers of two parts of Meternaut removed, because a tool that finds waste
must not carry waste of its own:

  * the old model account (an Azure AI Services account with two model deployments, and its private endpoint): since 2026-11-07 every model call goes to the models of the
    agents' own Foundry resource (environment/foundry), and nothing called the old account any more;
  * the usage recording (a function app, its plan and its private endpoint, a Cosmos DB account and its private endpoint, three event hubs): it copied the numbers of the calls
    that went through the owner's old API Management instance, which Meternaut does not use or touch any more, so nothing fed it.

What it deletes is this list, in this order, each by its exact name, and nothing else (a test pins the list):

   1. the usage function app                 func-meternaut-usage-<digest>
   2. its plan                               plan-meternaut-usage
   3. its private endpoint                   pe-func-meternaut-usage-<digest>
   4. the Cosmos DB account                  cosmos-meternaut-<digest>
   5. its private endpoint                   pe-cosmos-meternaut-<digest>
   6. the event hub ai-usage                 in the namespace evhns-meternaut-<digest> (the namespace itself is on the list `event-hubs`, not on this one)
   7. the event hub pii-usage                same namespace
   8. the event hub usage-control            same namespace
   9. the old model account's private endpoint   pe-aif-meternaut-<digest>
  10. the old model account                  aif-meternaut-<digest>: deleted, and then the soft-deleted account is purged, so that its name and its quota are free
  11. the identity of the usage app          id-meternaut-usage, when it is there as a resource

<digest> is the same eight characters that tools/environment-params.py makes from the subscription and the resource group (a test holds the two together).

For each one it reads the resource first (az resource show), deletes it when it is there (az resource delete), reads again until it is gone, and prints one line: deleted, or was not
there. Run twice, the second run finds nothing and prints "was not there" for every line (and purges a soft-deleted account of that name when an earlier run left one). It takes no input
but the subscription and the group, and it refuses unless both are the ones of the workflow's own settings (ENV_SUBSCRIPTION_ID and ENV_RESOURCE_GROUP): it can name no other group.

Role assignments of the usage app's identities: a deleted identity leaves its role assignments behind (Azure shows them as "Identity not found"). The tool reads the object ids of the
identities before it deletes them, and when it is done it lists the assignments of those ids at or below the project's resource group, so that a person can remove them. It deletes none.

The function subnet: the usage app was integrated with the subnet snet-func (virtual network vnet-meternaut), and the cases app uses that subnet too when it runs on Flex Consumption (it runs on a Basic plan, on a subnet of its own, since 2026-11-08):
the action cases then refuses to deploy while another app holds it. So after the deletes the tool reads the subnet again, lists the apps of the group that are integrated with it (the usage
app, which was just deleted, must not be one) and reads again until no app but the cases app and the Teams bot's app (docs/proposals/13-teams-and-outlook.md: it shares the subnet on purpose) is, for at most 15 minutes. It prints the platform's links on the subnet (service
association links) as information: a link can stay for a while after its app is gone, and it does not stop the action cases, whose own check looks at the apps. Then it says that
snet-func is free. When another app still holds the subnet, the run fails and names that app. A subnet that is not there is said, and is no error (the action model-side makes it).

show   Read only. Says for each item of the list whether it is there, whether a soft-deleted model account of that name is left, and which apps are integrated with snet-func.
run    Deletes, as above. Only a run of the Hub may do that (AGENTS.md rule 18; tools/hubguard.py says what counts as one). Exit 0 when everything on the list is gone and snet-func is free, 1 when something could not be
       deleted or read, or when another app holds snet-func (nothing after a failed delete is touched, and the second run goes on from there), 2 when it refuses.

The list `event-hubs` (the action `retire-event-hubs`). Until the control message of the cases app moved to a Storage queue, the cases app was started by an event in an Event Hubs
namespace, which cost 29.2 US dollars a month (the namespace, Standard, one throughput unit, and its private endpoint) for a channel that carried one small message now and then. Nothing reads the namespace any more.
A template that stops declaring a resource does not delete it, so this list does, after a run of the action `cases-run` has shown that the queue path works, by their exact names, in this order:

   1. the namespace's private endpoint       pe-evhns-meternaut-<digest>
   2. the Event Hubs namespace               evhns-meternaut-<digest>: its hub cases-control, that hub's consumer group and whatever else is in it go with it (no purge is needed for Event Hubs)
   3. the container of its checkpoints       azure-webjobs-eventhub in the base's storage account stmeternautfn<digest>, which only the Event Hubs trigger of the cases app used

It reads each one first, deletes it when it is there, reads again until it is gone, and prints one line each; a second run finds nothing and says so, and an estate that never had a namespace passes.
It refuses to delete anything while the control queue cases-control is not in the storage account (the channel that replaces the namespace), and says so. It deletes no role assignment: the roles that were on the hub
were scoped to the hub alone, so nothing is left for them to apply to. `show` with this list is read only and also says whether the control queue is there.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

guard = sys.modules.get("hubguard")
if guard is None:  # a test has loaded it already; a tool run on its own loads it from its own folder
    _spec = importlib.util.spec_from_file_location("hubguard", Path(__file__).with_name("hubguard.py"))
    guard = importlib.util.module_from_spec(_spec)
    sys.modules["hubguard"] = guard
    _spec.loader.exec_module(guard)

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
NOT_FOUND = re.compile(r"ResourceNotFound|ParentResourceNotFound|NotFound|could not be found|was not found|does not exist", re.I)
GROUP_NOT_FOUND = re.compile(r"ResourceGroupNotFound|resource group .* could not be found", re.I)
ARM = "https://management.azure.com"
ASSIGNMENTS_API = "2022-04-01"
WAIT_SECONDS = 900
POLL_SECONDS = 10

# What each item of the list is, in plain words, and the API version of its resource type.
SITE = ("Microsoft.Web/sites", "2024-04-01")
PLAN = ("Microsoft.Web/serverfarms", "2024-04-01")
ENDPOINT = ("Microsoft.Network/privateEndpoints", "2025-05-01")
COSMOS = ("Microsoft.DocumentDB/databaseAccounts", "2024-11-15")
HUB = ("Microsoft.EventHub/namespaces", "2024-01-01")
NAMESPACE = ("Microsoft.EventHub/namespaces", "2024-01-01")
ACCOUNT = ("Microsoft.CognitiveServices/accounts", "2025-06-01")
IDENTITY = ("Microsoft.ManagedIdentity/userAssignedIdentities", "2023-01-31")

USAGE_HUBS = ("ai-usage", "pii-usage", "usage-control")
USAGE_PLAN = "plan-meternaut-usage"
USAGE_IDENTITY = "id-meternaut-usage"

# The two lists: the old model account and the usage recording (`old`, the action retire-old), and the Event Hubs namespace that carried the control event (`event-hubs`, the action retire-event-hubs).
OLD_LIST = "old"
EVENT_HUBS_LIST = "event-hubs"
LISTS = (OLD_LIST, EVENT_HUBS_LIST)
# The container where the Functions host kept the checkpoints of an Event Hubs trigger, in the base's storage account, and the control queue that replaces the namespace (environment/cases/main.bicep makes it).
CHECKPOINT_CONTAINER = "azure-webjobs-eventhub"
CONTAINER_API = "2023-05-01"
CONTROL_QUEUE = "cases-control"
QUEUE_API = "2023-05-01"

# The function subnet that the usage app was integrated with and that the cases app uses while it runs on Flex Consumption.
NETWORK = "vnet-meternaut"
FUNCTION_SUBNET = "snet-func"
SUBNET_API = "2025-05-01"
SITES_API = "2024-04-01"


class Problem(Exception):
    """Something a person can fix or must know; printed without a trace."""


class Refused(Problem):
    """The tool was not allowed to start: nothing was read or changed."""


def digest(subscription: str, group: str) -> str:
    """Eight hex characters that depend on the subscription and the group only: the same as tools/environment-params.py makes."""
    return hashlib.sha256(f"{subscription}/{group}".lower().encode("utf-8")).hexdigest()[:8]


def subnet_id(subscription: str, group: str) -> str:
    return f"/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Network/virtualNetworks/{NETWORK}/subnets/{FUNCTION_SUBNET}"


class Item:
    """One thing of the list: what it is in plain words, its exact name, its resource id and the API version to read and delete it with."""

    def __init__(self, what: str, name: str, resource_id: str, api_version: str, kind: str = "resource") -> None:
        self.what, self.name, self.id, self.api_version, self.kind = what, name, resource_id, api_version, kind


def items(subscription: str, group: str) -> list[Item]:
    """The list, in the order in which it is deleted. Every id is built from the subscription and the group that were given, so no other group can be named."""
    token = digest(subscription, group)
    base = f"/subscriptions/{subscription}/resourceGroups/{group}/providers"
    namespace = f"evhns-meternaut-{token}"

    def one(what: str, kind: tuple[str, str], name: str, role: str = "resource") -> Item:
        return Item(what, name, f"{base}/{kind[0]}/{name}", kind[1], role)

    return [
        one("the usage function app", SITE, f"func-meternaut-usage-{token}", "usage-app"),
        one("the usage app's plan", PLAN, USAGE_PLAN),
        one("the usage app's private endpoint", ENDPOINT, f"pe-func-meternaut-usage-{token}"),
        one("the Cosmos DB account", COSMOS, f"cosmos-meternaut-{token}"),
        one("the Cosmos DB account's private endpoint", ENDPOINT, f"pe-cosmos-meternaut-{token}"),
        *[Item("the event hub", hub, f"{base}/{HUB[0]}/{namespace}/eventhubs/{hub}", HUB[1]) for hub in USAGE_HUBS],
        one("the old model account's private endpoint", ENDPOINT, f"pe-aif-meternaut-{token}"),
        one("the old model account", ACCOUNT, f"aif-meternaut-{token}", "model-account"),
        one("the identity of the usage app", IDENTITY, USAGE_IDENTITY, "usage-identity"),
    ]


def event_hub_items(subscription: str, group: str) -> list[Item]:
    """The list `event-hubs`, in the order in which it is deleted: the namespace's private endpoint, the namespace, and the container of its checkpoints in the base's storage account.
    Every id is built from the subscription and the group that were given, so no other group can be named."""
    token = digest(subscription, group)
    base = f"/subscriptions/{subscription}/resourceGroups/{group}/providers"
    namespace = f"evhns-meternaut-{token}"
    account = f"stmeternautfn{token}"
    return [
        Item("the Event Hubs namespace's private endpoint", f"pe-{namespace}", f"{base}/{ENDPOINT[0]}/pe-{namespace}", ENDPOINT[1]),
        Item("the Event Hubs namespace", namespace, f"{base}/{NAMESPACE[0]}/{namespace}", NAMESPACE[1]),
        Item("the container of the namespace's checkpoints", CHECKPOINT_CONTAINER,
             f"{base}/Microsoft.Storage/storageAccounts/{account}/blobServices/default/containers/{CHECKPOINT_CONTAINER}", CONTAINER_API),
    ]


def control_queue_url(subscription: str, group: str) -> str:
    """The control queue that replaces the namespace, in the base's storage account, as Azure Resource Manager addresses it."""
    account = f"stmeternautfn{digest(subscription, group)}"
    return (f"{ARM}/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Storage/storageAccounts/{account}"
            f"/queueServices/default/queues/{CONTROL_QUEUE}?api-version={QUEUE_API}")


def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *args, "--only-show-errors"], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def first_line(text: str) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0][:300] if lines else "no message"


class Azure:
    def __init__(self, runner=run_az, sleep=time.sleep, clock=time.monotonic) -> None:
        self.runner, self.sleep, self.clock = runner, sleep, clock

    def read(self, item: Item):
        """The resource as Azure shows it, or None when it is not there. Any other answer (a refusal, a throttle, a missing group) stops the run."""
        code, out, err = self.runner(["resource", "show", "--ids", item.id, "--api-version", item.api_version, "--output", "json"])
        if code == 0:
            try:
                return json.loads(out) if out.strip() else {}
            except ValueError as e:
                raise Problem(f"{item.what} {item.name} could not be read: the answer is not JSON") from e
        if GROUP_NOT_FOUND.search(err or ""):
            raise Problem(f"the resource group is not there: {first_line(err)}")
        if NOT_FOUND.search(err or ""):
            return None
        raise Problem(f"{item.what} {item.name} could not be read: {first_line(err)}")

    def delete(self, item: Item) -> None:
        code, _, err = self.runner(["resource", "delete", "--ids", item.id, "--api-version", item.api_version])
        if code != 0 and not NOT_FOUND.search(err or ""):
            raise Problem(f"{item.what} {item.name} could not be deleted: {first_line(err)}")

    def gone(self, item: Item) -> bool:
        """Reads again until the resource is gone, for at most WAIT_SECONDS."""
        deadline = self.clock() + WAIT_SECONDS
        while True:
            if self.read(item) is None:
                return True
            if self.clock() >= deadline:
                return False
            self.sleep(POLL_SECONDS)

    def soft_deleted(self, group: str, name: str) -> list[str]:
        """The locations of the soft-deleted accounts of this name that were in this group (normally none or one)."""
        code, out, err = self.runner(["cognitiveservices", "account", "list-deleted", "--output", "json"])
        if code != 0:
            raise Problem(f"the soft-deleted accounts could not be listed: {first_line(err)}")
        try:
            listed = json.loads(out) if out.strip() else []
        except ValueError as e:
            raise Problem("the soft-deleted accounts could not be listed: the answer is not JSON") from e
        pattern = re.compile(rf"/locations/([a-z0-9]+)/resourceGroups/{re.escape(group)}/deletedAccounts/{re.escape(name)}$", re.I)
        found = []
        for entry in listed if isinstance(listed, list) else []:
            match = pattern.search(str(entry.get("id", ""))) if isinstance(entry, dict) else None
            if match:
                found.append(match.group(1).lower())
        return found

    def purge(self, group: str, name: str, location: str) -> None:
        code, _, err = self.runner(["cognitiveservices", "account", "purge", "--location", location, "--resource-group", group, "--name", name])
        if code != 0 and not NOT_FOUND.search(err or ""):
            raise Problem(f"the soft-deleted account {name} could not be purged: {first_line(err)}. A person purges it with: "
                          f"az cognitiveservices account purge --location {location} --resource-group {group} --name {name}")

    def purged(self, group: str, name: str) -> bool:
        deadline = self.clock() + WAIT_SECONDS
        while True:
            if not self.soft_deleted(group, name):
                return True
            if self.clock() >= deadline:
                return False
            self.sleep(POLL_SECONDS)

    def get(self, url: str, what: str) -> dict | None:
        """One read with az rest: the answer as a dictionary, or None when Azure says that it is not there. Any other answer stops the run."""
        code, out, err = self.runner(["rest", "--method", "get", "--url", url, "--output", "json"])
        if code == 0:
            try:
                document = json.loads(out) if out.strip() else {}
            except ValueError as e:
                raise Problem(f"{what} could not be read: the answer is not JSON") from e
            return document if isinstance(document, dict) else {}
        if GROUP_NOT_FOUND.search(err or ""):
            raise Problem(f"the resource group is not there: {first_line(err)}")
        if NOT_FOUND.search(err or ""):
            return None
        raise Problem(f"{what} could not be read: {first_line(err)}")

    def function_subnet(self, subscription: str, group: str) -> dict | None:
        return self.get(f"{ARM}{subnet_id(subscription, group)}?api-version={SUBNET_API}", f"the function subnet {FUNCTION_SUBNET}")

    def control_queue(self, subscription: str, group: str) -> dict | None:
        """The control queue as Azure shows it, or None when it is not there."""
        return self.get(control_queue_url(subscription, group), f"the control queue {CONTROL_QUEUE}")

    def apps_on_the_function_subnet(self, subscription: str, group: str) -> list[tuple[str, str]]:
        """The name and the plan of every app of the group that is integrated with the function subnet, as Azure lists the apps (pages followed)."""
        wanted = subnet_id(subscription, group).lower()
        found: list[tuple[str, str]] = []
        url = f"{ARM}/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Web/sites?api-version={SITES_API}"
        while url:
            page = self.get(url, "the apps of the resource group")
            if page is None:
                raise Problem("the apps of the resource group could not be listed: Azure says that the group is not there")
            for site in page.get("value") or []:
                properties = (site.get("properties") or {}) if isinstance(site, dict) else {}
                if str(properties.get("virtualNetworkSubnetId") or "").lower() == wanted:
                    found.append((str(site.get("name", "")), str(properties.get("serverFarmId") or "").rsplit("/", 1)[-1] or "unknown plan"))
            url = page.get("nextLink")
        return found

    def assignments_of(self, scope: str, principal: str) -> list[dict]:
        """The role assignments of one object id at, above and below the scope, as Azure lists them (pages followed)."""
        found: list[dict] = []
        url = f"{ARM}{scope}/providers/Microsoft.Authorization/roleAssignments?api-version={ASSIGNMENTS_API}&$filter=principalId eq '{principal}'"
        while url:
            code, out, err = self.runner(["rest", "--method", "get", "--url", url, "--output", "json"])
            if code != 0:
                raise Problem(f"the role assignments of {principal} could not be read: {first_line(err)}")
            page = json.loads(out) if out.strip() else {}
            found += [v for v in (page.get("value") or []) if isinstance(v, dict)]
            url = page.get("nextLink")
        return found


def principal_of(item: Item, document: dict | None) -> str | None:
    """The object id of the identity that a resource of the list holds: the system-assigned identity of the usage app, or the user-assigned identity itself."""
    if not isinstance(document, dict):
        return None
    if item.kind == "usage-app":
        value = (document.get("identity") or {}).get("principalId")
    elif item.kind == "usage-identity":
        value = (document.get("properties") or {}).get("principalId")
    else:
        return None
    return value.lower() if isinstance(value, str) and GUID.match(value) else None


def refuse_unless_the_workflows_own(args, environ) -> None:
    """The subscription and the group are the workflow's own settings, and nothing else: the tool can be pointed at no other group."""
    if not GUID.match(args.subscription or ""):
        raise Refused("--subscription is a subscription id")
    if not GROUP.match(args.resource_group or ""):
        raise Refused("--resource-group is a resource group name")
    if args.resource_group != (environ.get("ENV_RESOURCE_GROUP") or ""):
        raise Refused("the resource group is not the one of the workflow's setting ENV_RESOURCE_GROUP: this tool touches the project's own resource group and no other. Nothing was read or changed")
    if args.subscription.lower() != (environ.get("ENV_SUBSCRIPTION_ID") or "").lower():
        raise Refused("the subscription is not the one of the workflow's setting ENV_SUBSCRIPTION_ID. Nothing was read or changed")


def describe_the_subnet(subnet: dict) -> tuple[str, list[str]]:
    """What the subnet is delegated to, and the platform's links on it (service association links), as Azure shows them."""
    properties = subnet.get("properties") or {}
    delegated = sorted({str((d.get("properties") or {}).get("serviceName", "")) for d in properties.get("delegations") or [] if isinstance(d, dict)} - {""})
    links = []
    for link in properties.get("serviceAssociationLinks") or []:
        if isinstance(link, dict):
            body = link.get("properties") or {}
            links.append(f"{link.get('name', 'a link')} ({body.get('linkedResourceType', 'unknown type')}, {body.get('link', 'unknown resource')})")
    return ", ".join(delegated) or "nothing", links


def show_the_function_subnet(azure: Azure, subscription: str, group: str, out) -> None:
    subnet = azure.function_subnet(subscription, group)
    if subnet is None:
        out(f"  the function subnet {FUNCTION_SUBNET}: is not there (the action model-side makes it)")
        return
    delegated, _ = describe_the_subnet(subnet)
    holders = azure.apps_on_the_function_subnet(subscription, group)
    out(f"  the function subnet {FUNCTION_SUBNET} (delegated to {delegated}): apps integrated with it: " + (", ".join(f"{name} (plan {plan})" for name, plan in holders) or "none"))


def free_the_function_subnet(azure: Azure, subscription: str, group: str, out) -> None:
    """After the deletes: no app but the cases app and the Teams bot's app may be integrated with the function subnet, so that the action cases can use it when the cases app runs on Flex Consumption. Reads until that is so."""
    cases_app = f"func-meternaut-cases-{digest(subscription, group)}"
    teams_app = f"func-meternaut-teams-{digest(subscription, group)}"
    subnet = azure.function_subnet(subscription, group)
    if subnet is None:
        out(f"The function subnet {FUNCTION_SUBNET} is not there, so no app is integrated with it. The action model-side makes it, and the action cases needs it.")
        return
    delegated, links = describe_the_subnet(subnet)
    out(f"The function subnet {FUNCTION_SUBNET} is delegated to {delegated}.")
    if links:
        out("The platform's links on the subnet (service association links), as read: " + "; ".join(links)
            + ". A link can stay for a while after its app is gone: it does not stop the action cases, which looks at the apps.")
    else:
        out("The subnet carries no service association link.")
    deadline = azure.clock() + WAIT_SECONDS
    while True:
        on_it = azure.apps_on_the_function_subnet(subscription, group)
        others = [f"{name} (plan {plan})" for name, plan in on_it if name.lower() not in (cases_app.lower(), teams_app.lower())]
        if not others:
            break
        if azure.clock() >= deadline:
            raise Problem(f"the function subnet {FUNCTION_SUBNET} is still taken by {', '.join(others)}, {WAIT_SECONDS // 60} minutes after the deletes. The action cases needs it for itself: "
                          "a person looks at that app (it has to be deleted, or moved to another subnet) and runs the action again. Nothing else was changed")
        azure.sleep(POLL_SECONDS)
    held = {name.lower() for name, _ in on_it}
    if cases_app.lower() in held and teams_app.lower() in held:
        out(f"The function subnet {FUNCTION_SUBNET} is free for the cases app: only the cases app {cases_app} and the Teams bot's app {teams_app} are integrated with it, as intended.")
    elif teams_app.lower() in held:
        out(f"The function subnet {FUNCTION_SUBNET} is free for the cases app: only the Teams bot's app {teams_app} is integrated with it, as intended.")
    elif on_it:
        out(f"The function subnet {FUNCTION_SUBNET} is free for the cases app: only the cases app {cases_app} is integrated with it, as intended.")
    else:
        out(f"The function subnet {FUNCTION_SUBNET} is free: no app is integrated with it, so the action cases can use it.")


def command_show(args, azure: Azure, out) -> int:
    out(f"What is still there in resource group {args.resource_group}, of what Meternaut does not use any more (read only):")
    for item in items(args.subscription, args.resource_group):
        document = azure.read(item)
        out(f"  {item.what} {item.name}: {'still there' if document is not None else 'was not there'}")
        if item.kind == "model-account":
            for location in azure.soft_deleted(args.resource_group, item.name):
                out(f"  the soft-deleted old model account {item.name} ({location}): still there, and a run purges it")
    show_the_function_subnet(azure, args.subscription, args.resource_group, out)
    return 0


def refuse_unless_the_hub(environ) -> None:
    not_the_hub = guard.refusal(environ)
    if not_the_hub:
        raise Refused(f"this command deletes, and only a run of the Hub may do that (AGENTS.md rule 18): {not_the_hub}")


def command_run(args, azure: Azure, environ, out) -> int:
    refuse_unless_the_hub(environ)
    group = args.resource_group
    deleted = 0
    absent = 0
    identities: dict[str, str] = {}
    out(f"Deleting what Meternaut does not use any more, in resource group {group} and nowhere else:")
    for item in items(args.subscription, group):
        document = azure.read(item)
        principal = principal_of(item, document)
        if principal:
            identities[f"{item.what} {item.name}"] = principal
        if document is None:
            absent += 1
            line = "was not there"
        else:
            azure.delete(item)
            if not azure.gone(item):
                raise Problem(f"{item.what} {item.name} is still there {WAIT_SECONDS // 60} minutes after the delete was accepted. Nothing after it was touched: run the action again")
            deleted += 1
            line = "deleted"
        if item.kind == "model-account":
            line += purge_account(azure, group, item.name, out)
        out(f"  {item.what} {item.name}: {line}")
    out(f"{deleted} deleted, {absent} were not there.")
    problems: list[str] = []
    for after in (lambda: free_the_function_subnet(azure, args.subscription, group, out),
                  lambda: list_left_behind(azure, args.subscription, group, identities, out)):
        try:
            after()
        except Problem as e:
            problems.append(str(e))
    if problems:
        raise Problem("; ".join(problems))
    return 0


def command_show_event_hubs(args, azure: Azure, out) -> int:
    out(f"What is still there in resource group {args.resource_group}, of the Event Hubs namespace that carried the control event (read only):")
    for item in event_hub_items(args.subscription, args.resource_group):
        out(f"  {item.what} {item.name}: {'still there' if azure.read(item) is not None else 'was not there'}")
    if azure.control_queue(args.subscription, args.resource_group) is None:
        out(f"  the control queue {CONTROL_QUEUE}, which replaces the namespace: is not there (the action cases makes it, and nothing of the list is deleted while it is not there)")
    else:
        out(f"  the control queue {CONTROL_QUEUE}, which replaces the namespace: is there")
    return 0


def command_run_event_hubs(args, azure: Azure, environ, out) -> int:
    refuse_unless_the_hub(environ)
    group = args.resource_group
    listed = event_hub_items(args.subscription, group)
    out(f"Deleting the Event Hubs namespace that carried the control event, and what belongs to it, in resource group {group} and nowhere else:")
    if any(azure.read(item) is not None for item in listed) and azure.control_queue(args.subscription, group) is None:
        raise Problem(f"the control queue {CONTROL_QUEUE} is not in the base's storage account, so the control message has no other way to go: nothing was deleted. "
                      "Run the action cases, then the action cases-run (it shows that the queue path works), and then this action again")
    deleted = 0
    absent = 0
    for item in listed:
        if azure.read(item) is None:
            absent += 1
            line = "was not there"
        else:
            azure.delete(item)
            if not azure.gone(item):
                raise Problem(f"{item.what} {item.name} is still there {WAIT_SECONDS // 60} minutes after the delete was accepted. Nothing after it was touched: run the action again")
            deleted += 1
            line = "deleted"
        out(f"  {item.what} {item.name}: {line}")
    out(f"{deleted} deleted, {absent} were not there.")
    return 0


def purge_account(azure: Azure, group: str, name: str, out) -> str:
    """Purges the soft-deleted account of this name, so that its name and its quota are free. What it says is added to the line of the account."""
    locations = azure.soft_deleted(group, name)
    if not locations:
        return ", and no soft-deleted account of that name is left to purge"
    for location in locations:
        azure.purge(group, name, location)
    if not azure.purged(group, name):
        raise Problem(f"the soft-deleted account {name} is still listed {WAIT_SECONDS // 60} minutes after the purge was accepted. Run the action again")
    return f", and the soft-deleted account was purged ({', '.join(locations)}), so its name and its quota are free"


def list_left_behind(azure: Azure, subscription: str, group: str, identities: dict[str, str], out) -> None:
    """The role assignments that the deleted identities of the usage app left in the project's group. Azure does not remove them with the identity. Listed, never deleted."""
    scope = f"/subscriptions/{subscription}/resourceGroups/{group}"
    if not identities:
        out("No identity of the usage app was found, so there is no role assignment of it to look for.")
        return
    left = []
    for label, principal in identities.items():
        for assignment in azure.assignments_of(scope, principal):
            where = str((assignment.get("properties") or {}).get("scope", ""))
            if where.lower() == scope.lower() or where.lower().startswith(scope.lower() + "/"):
                left.append((label, str(assignment.get("id", "")), where))
    if not left:
        out("No role assignment of the usage app's identities is left in the resource group.")
        return
    out(f"{len(left)} role assignment(s) of the deleted identities of the usage app are left at or below the resource group (Azure keeps them and shows them as 'Identity not found'). None was deleted:")
    for label, assignment_id, where in left:
        out(f"  {assignment_id}  (at {where}; the identity of {label})")
    out("A person removes them with their own sign-in: az role assignment delete --ids <the id above>.")


def main(argv=None, runner=run_az, environ=None, sleep=time.sleep, clock=time.monotonic, out=print) -> int:
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("show", "read only: what of the list is still there"), ("run", "delete the list, read each back, and say what was done")):
        command = commands.add_parser(name, help=help_text, allow_abbrev=False)
        command.add_argument("--subscription", required=True)
        command.add_argument("--resource-group", required=True)
        command.add_argument("--list", choices=LISTS, default=OLD_LIST, help="which list: old (the usage recording and the old model account, the default) or event-hubs (the Event Hubs namespace that carried the control event)")
        if name == "run":
            command.add_argument("--summary", help="a file that gets the lines of the run as a Markdown section (the step summary)")
    args = parser.parse_args(argv)
    lines: list[str] = []

    def say(text: str) -> None:
        lines.append(text)
        out(text)

    azure = Azure(runner, sleep, clock)
    try:
        refuse_unless_the_workflows_own(args, environ)
        if args.list == EVENT_HUBS_LIST:
            code = command_show_event_hubs(args, azure, say) if args.command == "show" else command_run_event_hubs(args, azure, environ, say)
        else:
            code = command_show(args, azure, say) if args.command == "show" else command_run(args, azure, environ, say)
    except Refused as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        code = 1
    if args.command == "run" and getattr(args, "summary", None):
        title = ("The Event Hubs namespace that carried the control event, and was deleted" if args.list == EVENT_HUBS_LIST
                 else "What Meternaut does not use any more, and was deleted")
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(f"### {title}\n\n```\n" + "\n".join(lines) + "\n```\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
