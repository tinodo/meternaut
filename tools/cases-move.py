#!/usr/bin/env python3
"""Clears what is in the way of the deploy of the cases app, from the state that Azure shows now and not from what an earlier run did (standard library only).

    python tools/cases-move.py run --subscription S --resource-group G --app NAME --wanted-kind Flex|Basic --wanted-tier TIER --other-plan NAME --other-tier TIER \
                                   --template environment/cases/main.bicep --parameters FILE [--summary FILE]

It is a step of the action `cases` of the Hub workflow, before its deploy. The cases app cannot move between a Flex Consumption plan and a Basic plan, so when the constant CASES_APP_PLAN
(tools/environment-params.py) asks for the other kind, the app is deleted and the deploy makes it again, with the same name. A run that stops half way (the platform's front end answers a
delete with a gateway time-out; a deploy is refused) leaves part of that done, and the next run must work whatever the earlier one did. So each thing below is read as it is now, deleted when it is
in the way, and read again until it is gone, with one line each, and a thing that is not there is no error:

  1. the app, when it runs on the plan of the other kind (by its exact name; a plan that is neither of the two kinds stops the run, and nothing is deleted);
  2. the plan of the other kind (by its exact name, and only while its tier is that kind's): an idle plan bills for nothing, so it does not stay when the app has gone;
  3. the private endpoint pe-<app>, when its connection is Disconnected or the app that it points at is not there: Azure refuses to change such an endpoint ("it can not be updated since it's in
     disconnected state. Please delete it and create a new one"), and the deploy writes the endpoint every time;
  4. the role assignments that the deploy is about to write: the template names each after the app's id, so Azure refuses to change the identity of one that exists (RoleAssignmentUpdateNotPermitted),
     and an app that is made again has a new identity. Their ids are read from a preview of the deployment (what-if, resource ids only), so no list of them is kept here and a change of the template
     changes the list. One is deleted when it exists and is not the app's own: the app is not there, or its identity is another one. The app's own are kept.

Every call of Azure that gets a gateway time-out, a bad gateway, a service that is not available or too many requests (502, 503, 504, 429) is made again, up to five times, a quarter of a minute apart.
A delete that still gets only such answers is not taken for failed: the thing is read again, and a delete that went through is a delete. A refusal of any other kind stops the run with Azure's own text.
A preview that cannot be read is said, and the run goes on: the deploy that follows says whether an assignment was in the way.

The tool deletes only what is named above, in the project's own resource group: the app and the endpoint by the name that it is given, the plan by the name that it is given, and a role assignment only when
its id is in that group and in the preview. It refuses unless the group is the ENV_RESOURCE_GROUP of the workflow, and unless a GitHub Actions run starts it (AGENTS.md rule 18). Exit code 0 when everything is
clear, 1 when something could not be read or deleted (the next run starts from what is left), 2 when it refuses.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
NAME = re.compile(r"^[A-Za-z0-9-]{2,60}$")
NOT_FOUND = re.compile(r"ResourceNotFound|ParentResourceNotFound|NotFound|Not Found|could not be found|was not found|does not exist|\b404\b", re.I)
GROUP_NOT_FOUND = re.compile(r"ResourceGroupNotFound|resource group .* could not be found", re.I)
# What a second try clears: the answers of the platform's front end when a back end is slow or busy.
TRANSIENT = re.compile(r"Gateway Timeout|GatewayTimeout|Bad Gateway|BadGateway|Service Unavailable|ServiceUnavailable|TooManyRequests|Too Many Requests|RequestTimeout|ServiceBusy|(?<![\w.:+-])(?:429|502|503|504)(?![\w.])", re.I)
ARM = "https://management.azure.com"
SITE_API = "2024-04-01"
PLAN_API = "2024-04-01"
ENDPOINT_API = "2025-05-01"
ASSIGNMENT_API = "2022-04-01"
ASSIGNMENT_PATH = "/providers/microsoft.authorization/roleassignments/"
TRIES = 5
PAUSE = 15
WAIT_SECONDS = 300
POLL_SECONDS = 15
HOST_NAME_SECONDS = 90
# The built-in roles that the template gives the app, for the lines of the log only; any other role is shown by its id.
ROLE_NAMES = {
    "a638d3c7-ab3a-418d-83e6-5f17a39d4fde": "Azure Event Hubs Data Receiver",
    "b7e6dc6d-f1e8-4753-8033-0f276bb0955b": "Storage Blob Data Owner",
    "974c5e8b-45b9-4653-ba55-5f855dd0fb88": "Storage Queue Data Contributor",
    "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3": "Storage Table Data Contributor",
    "3913510d-42f4-4e42-8a64-420c390055eb": "Monitoring Metrics Publisher",
}


class Problem(Exception):
    """Something a person can fix or must know; printed without a trace."""


class Refused(Problem):
    """The tool was not allowed to start: nothing was read or changed."""


def first_line(text: str) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0][:300] if lines else "no message"


def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *args, "--only-show-errors"], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class Azure:
    def __init__(self, runner=run_az, sleep=time.sleep, clock=time.monotonic, out=print) -> None:
        self.runner, self.sleep, self.clock, self.out = runner, sleep, clock, out

    def call(self, args: list[str], what: str) -> tuple[int, str, str]:
        """One call of az, made again while Azure answers with something that a second try clears (TRIES tries at the most)."""
        for attempt in range(1, TRIES + 1):
            code, out, err = self.runner(args)
            if code == 0 or attempt == TRIES or not TRANSIENT.search(err or ""):
                return code, out, err
            self.out(f"::warning::{what}: Azure answered with a transient error ({first_line(err)}); trying again in {PAUSE} seconds (attempt {attempt} of {TRIES}).")
            self.sleep(PAUSE)
        raise AssertionError("unreachable")

    def get(self, resource_id: str, api: str, what: str) -> dict | None:
        """The resource as Azure shows it, or None when it is not there. Any other answer (a refusal, a missing group, a throttle that did not clear) stops the run."""
        code, out, err = self.call(["rest", "--method", "get", "--url", f"{ARM}{resource_id}?api-version={api}", "--output", "json"], what)
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

    def remove(self, resource_id: str, api: str, what: str) -> None:
        """Deletes the resource and reads it again until it is gone. 'Not found' on the delete is a delete that went through earlier; so is a delete that only got transient answers, when the read says so."""
        code, _, err = self.call(["rest", "--method", "delete", "--url", f"{ARM}{resource_id}?api-version={api}"], what)
        accepted = True
        if code != 0 and not NOT_FOUND.search(err or ""):
            if not TRANSIENT.search(err or ""):
                raise Problem(f"{what} could not be deleted: {first_line(err)}")
            accepted = False
            self.out(f"::warning::{what}: the delete got only transient answers ({first_line(err)}) in {TRIES} tries. It may have gone through, so it is read again.")
        deadline = self.clock() + WAIT_SECONDS
        while self.get(resource_id, api, what) is not None:
            if self.clock() >= deadline:
                raise Problem(f"{what} is still there {WAIT_SECONDS // 60} minutes after the delete was " + ("accepted" if accepted else "tried, and Azure answered with a transient error every time")
                              + ". Run the action again: it reads what is left and repeats only that")
            self.sleep(POLL_SECONDS)

    def assignments_of_the_deploy(self, args, group: str) -> list[str] | None:
        """The ids of the role assignments that the deploy is about to write, from a preview of it with resource ids only. None when the preview cannot be read."""
        parts = ["deployment", "group", "what-if", "--subscription", args.subscription, "--resource-group", args.resource_group, "--template-file", args.template,
                 "--parameters", f"@{args.parameters}", "--result-format", "ResourceIdOnly", "--no-pretty-print", "--output", "json"]
        code, out, err = self.call(parts, "the preview of the deployment")
        if code != 0:
            self.out(f"::warning::The preview of the deployment could not be read ({first_line(err)}), so the role assignments that it would write are not known and none was looked for.")
            return None
        try:
            document = json.loads(out)
        except ValueError:
            document = None
        changes = document.get("changes") if isinstance(document, dict) else None
        if changes is None and isinstance(document, dict):
            changes = (document.get("properties") or {}).get("changes")
        if not isinstance(changes, list):
            self.out("::warning::The preview of the deployment has no list of changes, so the role assignments that it would write are not known and none was looked for.")
            return None
        ids: list[str] = []
        for change in changes:
            resource_id = str((change or {}).get("resourceId") or "") if isinstance(change, dict) else ""
            if ASSIGNMENT_PATH in resource_id.lower() and resource_id.lower().startswith(group.lower() + "/") and resource_id.lower() not in {i.lower() for i in ids}:
                ids.append(resource_id)
        return ids


def connection_states(endpoint: dict) -> list[str]:
    properties = endpoint.get("properties") or {}
    found = []
    for key in ("privateLinkServiceConnections", "manualPrivateLinkServiceConnections"):
        for connection in properties.get(key) or []:
            state = ((connection or {}).get("properties") or {}).get("privateLinkServiceConnectionState") or {}
            if state.get("status"):
                found.append(str(state["status"]))
    return found


def target_of(endpoint: dict) -> str:
    properties = endpoint.get("properties") or {}
    for key in ("privateLinkServiceConnections", "manualPrivateLinkServiceConnections"):
        for connection in properties.get(key) or []:
            target = ((connection or {}).get("properties") or {}).get("privateLinkServiceId")
            if target:
                return str(target)
    return ""


def principal_of(site: dict | None) -> str:
    value = ((site or {}).get("identity") or {}).get("principalId")
    return value.lower() if isinstance(value, str) and GUID.match(value) else ""


def describe(assignment: dict) -> str:
    properties = assignment.get("properties") or {}
    role = str(properties.get("roleDefinitionId") or "").rsplit("/", 1)[-1].lower()
    where = "/".join(str(properties.get("scope") or "").rstrip("/").rsplit("/", 2)[-2:])
    return f"{ROLE_NAMES.get(role, 'role ' + (role or 'unknown'))} on {where or 'an unknown scope'}"


def clear_the_app(azure: Azure, args, group: str, out) -> tuple[bool, bool]:
    """Items 1 and 2. Whether the app was deleted in this run, and whether the plan of the other kind was."""
    site_id = f"{group}/providers/Microsoft.Web/sites/{args.app}"
    site = azure.get(site_id, SITE_API, f"the cases app {args.app}")
    app_deleted, plan_deleted = False, False
    if site is None:
        out(f"  the cases app {args.app}: was not there")
    else:
        plan_id = str((site.get("properties") or {}).get("serverFarmId") or "")
        plan = azure.get(plan_id, PLAN_API, "the plan of the cases app") if plan_id else None
        if plan is None:
            raise Problem(f"the plan of the cases app {args.app} could not be read ({plan_id or 'the app names none'}): nothing was deleted")
        tier, plan_name = str((plan.get("sku") or {}).get("tier") or ""), plan_id.rsplit("/", 1)[-1]
        if tier.lower() == args.wanted_tier.lower():
            out(f"  the cases app {args.app}: runs on the plan {plan_name}, a {tier} plan, which is the kind that CASES_APP_PLAN asks for ({args.wanted_kind}): kept")
        elif tier.lower() == args.other_tier.lower() and plan_name.lower() == args.other_plan.lower():
            azure.remove(site_id, SITE_API, f"the cases app {args.app}")
            app_deleted = True
            out(f"  the cases app {args.app}: deleted (it ran on the plan {plan_name}, a {tier} plan, and CASES_APP_PLAN asks for {args.wanted_kind})")
        else:
            raise Problem(f"The cases app runs on the plan {plan_name}, whose tier is {tier}. CASES_APP_PLAN asks for {args.wanted_kind} ({args.wanted_tier}), and the plan of the other kind is "
                          f"{args.other_plan} ({args.other_tier}): this is neither, so nothing was removed. A person looks at the app and its plan; a plan that this workflow does not know is never deleted")
    other_id = f"{group}/providers/Microsoft.Web/serverfarms/{args.other_plan}"
    plan = azure.get(other_id, PLAN_API, f"the plan {args.other_plan}")
    if plan is None:
        out(f"  the plan {args.other_plan}: was not there")
    else:
        tier = str((plan.get("sku") or {}).get("tier") or "")
        if tier.lower() != args.other_tier.lower():
            raise Problem(f"The plan {args.other_plan} is a {tier} plan and the other kind is {args.other_tier}: it is not deleted. A person looks at it; a plan that this workflow does not know is never deleted")
        azure.remove(other_id, PLAN_API, f"the plan {args.other_plan}")
        plan_deleted = True
        out(f"  the plan {args.other_plan}: deleted (a {tier} plan, and the cases app is not on it)")
    return app_deleted, plan_deleted


def clear_the_endpoint(azure: Azure, args, group: str, out) -> bool:
    """Item 3. True when the endpoint was deleted."""
    name = f"pe-{args.app}"
    endpoint_id = f"{group}/providers/Microsoft.Network/privateEndpoints/{name}"
    endpoint = azure.get(endpoint_id, ENDPOINT_API, f"the private endpoint {name}")
    if endpoint is None:
        out(f"  the private endpoint {name}: was not there")
        return False
    states = connection_states(endpoint)
    target = target_of(endpoint)
    why = ""
    if any(state.lower() == "disconnected" for state in states):
        why = "its connection is Disconnected"
    elif target and azure.get(target, SITE_API, "the app that the private endpoint points at") is None:
        why = "the app that it points at is not there"
    if not why:
        shown = ", ".join(states) if states else "not readable from Azure's answer, so it is taken for connected"
        out(f"  the private endpoint {name}: kept (its connection is {shown}, and the app that it points at is there)")
        return False
    azure.remove(endpoint_id, ENDPOINT_API, f"the private endpoint {name}")
    out(f"  the private endpoint {name}: deleted ({why}); the deploy makes it again")
    return True


def clear_the_assignments(azure: Azure, args, group: str, out) -> int:
    """Item 4. The number of assignments deleted."""
    principal = principal_of(azure.get(f"{group}/providers/Microsoft.Web/sites/{args.app}", SITE_API, f"the cases app {args.app}"))
    ids = azure.assignments_of_the_deploy(args, group)
    if ids is None:
        out("  the role assignments that the deploy will write: could not be listed (see the warning above)")
        return 0
    absent, kept, deleted = 0, 0, 0
    for assignment_id in ids:
        assignment = azure.get(assignment_id, ASSIGNMENT_API, f"the role assignment {assignment_id.rsplit('/', 1)[-1]}")
        if assignment is None:
            absent += 1
            continue
        held_by = str((assignment.get("properties") or {}).get("principalId") or "").lower()
        label = f"role assignment {assignment_id.rsplit('/', 1)[-1]} ({describe(assignment)})"
        if principal and held_by == principal:
            kept += 1
            out(f"  {label}: kept (it is the app's own)")
            continue
        try:
            azure.remove(assignment_id, ASSIGNMENT_API, label)
        except Problem as e:
            raise Problem(f"{e}. The deploy is refused for an assignment that exists for another identity, so a person deletes it with their own sign-in, on the owner's written word, "
                          "and runs the action again (environment/BOOTSTRAP.md)") from e
        deleted += 1
        out(f"  {label}: deleted (it was for the identity {held_by or 'unknown'}; the app's is {principal or 'not there'})")
    out(f"  the role assignments that the deploy will write: {len(ids)} listed, {absent} were not there, {kept} are the app's own and were kept, {deleted} were deleted")
    return deleted


NEW_IDENTITY = ("### The cases app is made again, with a new identity\n\n"
                "What was in the way of the deploy was deleted (the lines of this step say what). The app that the deploy makes has **a new system-assigned identity**, so what a person gave the old one "
                "outside the project's group has to be given again: Reader and Cost Management Reader (`tools/access-requirements.py check`, then `grant --apply`), and the right to send letters "
                "(`tools/exchange-setup.py`), both described in environment/BOOTSTRAP.md. Run `foundry` after this run, which gives the new identity its role on the Foundry project, and `aigateway` "
                "(on the owner's written word, as for its first run), which gives it AI Gateway Models User on the gateway: a new role takes up to ten minutes to apply. "
                "Until then a run of the Watch ends with an authorization error.\n")


def command_run(args, azure: Azure, environ, out, sleep) -> int:
    if environ.get("GITHUB_ACTIONS") != "true":
        raise Refused("this command deletes, and only a GitHub Actions run may do that (AGENTS.md rule 18)")
    group = f"/subscriptions/{args.subscription}/resourceGroups/{args.resource_group}"
    out(f"Clearing what is in the way of the deploy of the cases app {args.app}, on the {args.wanted_kind} plan, in resource group {args.resource_group}:")
    app_deleted, plan_deleted = clear_the_app(azure, args, group, out)
    endpoint_deleted = clear_the_endpoint(azure, args, group, out)
    assignments_deleted = clear_the_assignments(azure, args, group, out)
    if app_deleted:
        out(f"The host name of the app is let go a little after the app: waiting {HOST_NAME_SECONDS} seconds, because a new app of the same name may be refused for a minute.")
        sleep(HOST_NAME_SECONDS)
    if args.summary and (app_deleted or plan_deleted or endpoint_deleted or assignments_deleted):
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(NEW_IDENTITY)
    out("Clear.")
    return 0


def refuse_unless_the_workflows_own(args, environ) -> None:
    """The subscription and the group are the workflow's own settings, and nothing else: the tool can be pointed at no other group."""
    if not GUID.match(args.subscription or ""):
        raise Refused("--subscription is a subscription id")
    if not GROUP.match(args.resource_group or ""):
        raise Refused("--resource-group is a resource group name")
    for option, value in (("--app", args.app), ("--other-plan", args.other_plan)):
        if not NAME.match(value or ""):
            raise Refused(f"{option} is a resource name")
    if args.resource_group != (environ.get("ENV_RESOURCE_GROUP") or ""):
        raise Refused("the resource group is not the one of the workflow's setting ENV_RESOURCE_GROUP: this tool touches the project's own resource group and no other. Nothing was read or changed")
    if args.subscription.lower() != (environ.get("ENV_SUBSCRIPTION_ID") or "").lower():
        raise Refused("the subscription is not the one of the workflow's setting ENV_SUBSCRIPTION_ID. Nothing was read or changed")


def main(argv=None, runner=run_az, environ=None, sleep=time.sleep, clock=time.monotonic, out=print) -> int:
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="clear what is in the way of the deploy of the cases app")
    run.add_argument("--subscription", required=True)
    run.add_argument("--resource-group", required=True)
    run.add_argument("--app", required=True, help="the cases app's name (its private endpoint is pe-<name>)")
    run.add_argument("--wanted-kind", required=True, choices=["Flex", "Basic"])
    run.add_argument("--wanted-tier", required=True, help="the tier of the plan that is asked for (FlexConsumption or Basic)")
    run.add_argument("--other-plan", required=True, help="the name of the plan of the other kind")
    run.add_argument("--other-tier", required=True, help="the tier of the plan of the other kind")
    run.add_argument("--template", required=True, help="the template that the deploy uses")
    run.add_argument("--parameters", required=True, help="the parameter file that the deploy uses")
    run.add_argument("--summary", help="a file that the step summary of the run is appended to")
    args = parser.parse_args(argv)
    try:
        refuse_unless_the_workflows_own(args, environ)
        return command_run(args, Azure(runner, sleep, clock, out), environ, out, sleep)
    except Refused as e:
        out(f"::error::{e}")
        return 2
    except Problem as e:
        out(f"::error::{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
