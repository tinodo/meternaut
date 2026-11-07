#!/usr/bin/env python3
"""Deletes what Meternaut does not use any more, in the project's own resource group and nowhere else (standard library only).

    python tools/retire-old.py show --subscription S --resource-group G
    python tools/retire-old.py run  --subscription S --resource-group G [--summary <file>]

It is the action `retire-old` of the Hub workflow. On 2026-11-07 the owner ordered the old leftovers of two parts of Meternaut removed, because a tool that finds waste
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
   6. the event hub ai-usage                 in the namespace evhns-meternaut-<digest> (the namespace and its hub cases-control are not touched)
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

show   Read only. Says for each item of the list whether it is there, and whether a soft-deleted model account of that name is left.
run    Deletes, as above. Only a GitHub Actions run may do that (AGENTS.md rule 18). Exit 0 when everything on the list is gone, 1 when something could not be deleted or read (nothing
       after it is touched, and the second run goes on from there), 2 when it refuses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

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
ACCOUNT = ("Microsoft.CognitiveServices/accounts", "2025-06-01")
IDENTITY = ("Microsoft.ManagedIdentity/userAssignedIdentities", "2023-01-31")

USAGE_HUBS = ("ai-usage", "pii-usage", "usage-control")
USAGE_PLAN = "plan-meternaut-usage"
USAGE_IDENTITY = "id-meternaut-usage"


class Problem(Exception):
    """Something a person can fix or must know; printed without a trace."""


class Refused(Problem):
    """The tool was not allowed to start: nothing was read or changed."""


def digest(subscription: str, group: str) -> str:
    """Eight hex characters that depend on the subscription and the group only: the same as tools/environment-params.py makes."""
    return hashlib.sha256(f"{subscription}/{group}".lower().encode("utf-8")).hexdigest()[:8]


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


def command_show(args, azure: Azure, out) -> int:
    out(f"What is still there in resource group {args.resource_group}, of what Meternaut does not use any more (read only):")
    for item in items(args.subscription, args.resource_group):
        document = azure.read(item)
        out(f"  {item.what} {item.name}: {'still there' if document is not None else 'was not there'}")
        if item.kind == "model-account":
            for location in azure.soft_deleted(args.resource_group, item.name):
                out(f"  the soft-deleted old model account {item.name} ({location}): still there, and a run purges it")
    return 0


def command_run(args, azure: Azure, environ, out) -> int:
    if environ.get("GITHUB_ACTIONS") != "true":
        raise Refused("this command deletes, and only a GitHub Actions run may do that (AGENTS.md rule 18)")
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
    list_left_behind(azure, args.subscription, group, identities, out)
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
        code = command_show(args, azure, say) if args.command == "show" else command_run(args, azure, environ, say)
    except Refused as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        code = 1
    if args.command == "run" and getattr(args, "summary", None):
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write("### What Meternaut does not use any more, and was deleted\n\n```\n" + "\n".join(lines) + "\n```\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
