#!/usr/bin/env python3
"""The access that Meternaut needs outside its own resource group, and the installer that reads it (standard library only).

    python tools/access-requirements.py markdown [--retired | --tenant]
    python tools/access-requirements.py check [places] [--only R1,R4]
    python tools/access-requirements.py grant [places] [--only R1,R4] [--apply] [--yes]
    python tools/access-requirements.py retire [places] [--only W1,W2] [--apply] [--yes]

Meternaut holds no write right: every grant in the file only reads, and a change to Azure is made with the token of the person who approved it
(docs/proposals/03-access-and-onboarding.md). The deployment workflow's identity may change only the project's own resource group and must not get a
right anywhere else (AGENTS.md rule 18). The function app that the workflow makes (the first cases) runs as an identity that
still needs reads in other places: the subscriptions that the Watch reads. Only a person who may assign roles there can
give them. The file environment/access-requirements.json says which role of which identity at which place, and which grants an earlier version made and
must now be removed. This tool reads that file and the signed-in person's view of Azure.

An identity of the file is what a function app runs as, and its grants are held by its holders: the system-assigned identity of the app, which the tool
finds by reading the app in the project's resource group (--cases-site gives the name of the app), and, while an app is moved from
a user-assigned identity to its system-assigned one, the user-assigned identity too, which the tool finds by its name in the project's group. Every holder
is checked and receives every grant of its identity, so that the app is never without access. An app that does not exist yet, or has no
system-assigned identity yet, is reported like an identity that does not exist yet: "cannot yet".

markdown  Prints the table of the requirements, as docs/proposals/03-access-and-onboarding.md shows it; with --retired, the table of the retired grants; with --tenant, the table of the
          reads at the tenant or at a billing scope (the file's "tenantReads", which a person gives and this tool does not check), as docs/proposals/15-learning.md shows it.
          Reads no Azure.
check     Read only. For each requirement and each holder: present, missing, or why it cannot be present yet (the identity or the app does not exist, the
          app has no system-assigned identity, the custom role does not exist or differs from the file). Exit 0 when every requirement is present. A
          grant at a higher place (a management group) counts.
grant     A dry run: prints what is missing and the exact commands that would make it. With --apply it runs them, with the rights of the person
          who is signed in to the Azure CLI, and checks again. It grants only what the file lists, never changes a custom role that already exists
          (it reports the difference) and refuses to run in GitHub Actions: no pipeline may hold these rights.
retire    Removes what the file lists under "retired". It reads first: for each retired item it looks for (a) the identity, by name, in the project's
          group (it is reported and never deleted: a person removes the old user-assigned identities after this tool has taken away their grants, and the
          deployment workflow or the owner removes the retired runner identity; the deployment identity's own retired role, W8, names an identity that
          is in the bootstrap group and says "lookup": false, so it is not looked for), (b) the assignments of the retired custom
          role at that place and below it, whoever holds them (an identity that was deleted leaves its assignment, which the portal shows as "Identity
          not found"), and (c) the custom role itself. A dry run prints the exact commands. With --apply it runs them, with the rights of the person
          who is signed in to the Azure CLI: the assignments of that role at that place first, then the role, and only when no assignment of it
          remains. A role that can also be assigned outside the place (outside the resource group where it was defined) is left alone. For the custom role of the usage app (W10) the place is the
          central workspace and the role was defined in the resource group that holds it, so the assignments are listed in that group and below it: Azure refuses to delete a role while any assignment of it
          remains. It changes nothing else, a second run finds nothing to retire,
          and it refuses --apply in GitHub Actions like grant. Exit 0 when nothing is left to retire, 1 when something is (also after a dry run).
          An item with replacedBy is the grant of an identity that an app no longer runs as. Its role is still wanted by the grant that replaces it, so
          only the assignments that this one identity holds at that place and below it are looked for and removed, never another holder's and never the
          role. They are removed only while the replacing grant is present for every holder of its identity (read like check does, so the option that
          names the app is needed); until then the line says 'kept', so that the app is never left without access. An assignment of the identity above the
          place is reported as 'left alone'. An item with roleStays (W9) is the grant of a built-in role that nothing needs any more: the same, with nothing that replaces it,
          for the user-assigned identity that the item names and, when it has alsoHeldBy, for the system-assigned identity of the app that --usage-site names (read from the app, and never changed).
          The tool finds the assignments by the object id of the identity, so it must run while the identity exists:
          Azure keeps the assignments of a deleted identity, shows them as "Identity not found", and the tool cannot tell whose they were. So run it for W9 before the Hub action retire-old deletes the usage app.

The places come from options or from the settings that the workflow uses: --project-subscription (ENV_SUBSCRIPTION_ID) and --project-group
(ENV_RESOURCE_GROUP), where the identities and the apps are; --cases-site (ACCESS_CASES_SITE), the name of the cases app in that group (func-meternaut-cases-*;
it is needed only by the requirements of that app), and --usage-site (ACCESS_USAGE_SITE), the name of the usage app that the Hub action retire-old deletes (func-meternaut-usage-*;
it is needed only by the retired item W9, which names the app's system-assigned identity); --gateway (ACCESS_GATEWAY_ID), the API Management instance, whose resource group is where the retired
custom roles were defined (the items W7 and W8); --gateway-insights (ACCESS_GATEWAY_INSIGHTS_ID), the old gateway's Application Insights component (the items W9 and W10); --estate (ACCESS_ESTATE_SCOPES, comma
separated; default: the project subscription), what the Watch reads: a subscription, or a management group such as the tenant root management group above the subscriptions to watch (the app then reads every subscription that its identity can read; a grant at the group counts for everything below it); --workspace (ACCESS_WORKSPACE_ID; default: the workspace of the gateway's component), whose resource group is where the retired custom role of the usage app was defined (the item W10).
These settings are the ones of the person's own session: they are not the repository secrets of the deployment workflow, which reads none of them.
The Azure CLI is `az`, or the command in the variable AZ (for example "C:\\path\\python.exe" -IBm azure.cli).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "environment" / "access-requirements.json"

GUID =  r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
NAME = r"[A-Za-z0-9._()-]{1,90}"
GROUP_PATH = rf"/subscriptions/{GUID}/resourceGroups/{NAME}"
SUBSCRIPTION = re.compile(rf"^/subscriptions/{GUID}$", re.I)
MANAGEMENT_GROUP = re.compile(r"^/providers/Microsoft\.Management/managementGroups/[A-Za-z0-9._()-]{1,90}$", re.I)
RESOURCE_GROUP = re.compile(rf"^{GROUP_PATH}$", re.I)
APIM = re.compile(rf"^({GROUP_PATH})/providers/Microsoft\.ApiManagement/service/[A-Za-z0-9-]{{1,50}}$", re.I)
INSIGHTS = re.compile(rf"^{GROUP_PATH}/providers/Microsoft\.Insights/components/[A-Za-z0-9._()-]{{1,260}}$", re.I)
WORKSPACE = re.compile(rf"^({GROUP_PATH})/providers/Microsoft\.OperationalInsights/workspaces/[A-Za-z0-9-]{{4,63}}$", re.I)
SIMPLE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
GUID_ONLY = re.compile(rf"^{GUID}$")
MANAGEMENT_PREFIX = "/providers/microsoft.management/managementgroups/"

ARM = "https://management.azure.com"
ASSIGNMENTS_API = "2022-04-01"
INSIGHTS_API = "2020-02-02"
SITE_API = "2024-04-01"
SITE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,58}[A-Za-z0-9]$")
# The option that names a function app, and the setting that names it when the option is not given.
SITE_OPTIONS = {"--cases-site": "ACCESS_CASES_SITE", "--usage-site": "ACCESS_USAGE_SITE"}
NOT_FOUND = re.compile(r"ResourceNotFound|could not be found|was not found|not found", re.I)
STATES = {"present": "present", "missing": "MISSING", "role-missing": "MISSING", "no-identity": "cannot yet", "role-differs": "role differs"}
UNFIXABLE = ("no-identity", "role-differs")


class Problem(Exception):
    """Something the person who runs the tool can fix or must know; printed without a trace."""


# ---- the Azure CLI -------------------------------------------------------------------------------------------------------------------------------

def az_command() -> list[str]:
    """`az`, or the command in the variable AZ (it may hold a path with spaces in quotes, and arguments)."""
    value = os.environ.get("AZ", "").strip()
    if not value:
        return [shutil.which("az") or "az"]
    parts = shlex.split(value, posix=(os.name != "nt"))
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]


def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([*az_command(), *args, "--only-show-errors"], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class Az:
    def __init__(self, runner=run_az) -> None:
        self.runner = runner

    def run(self, *args: str) -> tuple[int, str, str]:
        return self.runner(list(args))

    def json(self, *args: str):
        code, out, err = self.run(*args)
        if code != 0:
            raise Problem(f"az {' '.join(args[:3])} failed: {first_line(err)}")
        return json.loads(out) if out.strip() else None


def first_line(text: str) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0][:300] if lines else "no message"


@contextlib.contextmanager
def json_file(document):
    """The definition goes to the Azure CLI as a file: on Windows the CLI's own wrapper mangles quotes in an argument."""
    handle, path = tempfile.mkstemp(suffix=".json", prefix="role-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(document, f)
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


# ---- the file ------------------------------------------------------------------------------------------------------------------------------------

def looked_up(item: dict) -> bool:
    """False for a retired custom role whose holder is not looked up by name in the project's group: the deployment identity lives in the bootstrap group, so a
    lookup there would say that it does not exist. The role is removed whole, whoever holds it, so nothing is said about an identity that was not read."""
    return bool(item["identity"].get("lookup", True))


def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["version"] == 1
        for key in ("identities", "places", "roles", "grants"):
            assert manifest[key]
        user_assigned: list[str] = []
        site_options: list[str] = []
        for key, identity in manifest["identities"].items():
            assert identity["madeBy"] and identity["app"] and identity["appName"], f"{key}: an identity names its app and the Hub action that makes it"
            holders = identity["holders"]
            assert isinstance(holders, list) and holders, f"{key}: an identity has holders"
            assert [h["kind"] for h in holders].count("system") <= 1, f"{key}: an app has one system-assigned identity"
            for holder in holders:
                assert holder["kind"] in ("system", "user"), f"{key}: a holder is 'system' or 'user'"
                if holder["kind"] == "system":
                    assert holder["siteOption"] in SITE_OPTIONS, f"{key}: siteOption is one of {', '.join(SITE_OPTIONS)}"
                    site_options.append(holder["siteOption"])
                else:
                    assert SIMPLE_NAME.match(str(holder.get("name", ""))), f"{key}: a user-assigned holder has a name"
                    user_assigned.append(holder["name"])
        assert len(site_options) == len(set(site_options)), "an option names one app"
        assert len(user_assigned) == len(set(user_assigned)), "a user-assigned identity is a holder once"
        ids = [g["id"] for g in manifest["grants"]]
        assert len(ids) == len(set(ids)), "an id is used twice"
        for grant in manifest["grants"]:
            assert grant["identity"] in manifest["identities"] and grant["role"] in manifest["roles"] and grant["place"] in manifest["places"], grant["id"]
            assert grant["why"]
        for name, role in manifest["roles"].items():
            assert role["kind"] in ("builtin", "custom"), name
            if role["kind"] == "builtin":
                assert GUID_ONLY.match(role["id"]), name
            else:
                assert role["definedIn"] in ("gatewayGroup", "workspaceGroup", "projectGroup") and role["actions"] and role["description"], name
                assert not role.get("writes"), f"{name}: Meternaut holds no write right, so no role may be one that changes Azure"
        assert isinstance(manifest.get("retired", []), list), "retired is a list"
        used = set(ids)
        current = set(user_assigned)
        grants = {g["id"]: g for g in manifest["grants"]}
        assert isinstance(manifest.get("tenantReads", []), list), "tenantReads is a list"
        tenant_ids: set[str] = set()
        for item in manifest.get("tenantReads", []):
            assert item["id"] not in used and item["id"] not in tenant_ids, f"{item['id']}: an id is used once"
            tenant_ids.add(item["id"])
            assert item["identity"] in manifest["identities"] and item["read"] and item["why"], item["id"]
            assert isinstance(item["calls"], list) and item["calls"] and all(isinstance(c, str) and c for c in item["calls"]), f"{item['id']}: calls is a list of names"
            assert isinstance(item["roles"], list) and item["roles"] and all(isinstance(r, str) and r for r in item["roles"]), f"{item['id']}: roles is a list of texts"
        used |= tenant_ids
        for item in manifest.get("retired", []):
            assert item["id"] not in used, f"{item['id']}: the id of a retired item is not the id of a grant, and is used once"
            used.add(item["id"])
            assert isinstance(item["identity"], dict) and SIMPLE_NAME.match(str(item["identity"].get("name", ""))), f"{item['id']}: the identity is an object with a name"
            assert isinstance(item["identity"].get("lookup", True), bool), f"{item['id']}: lookup is true or false"
            assert item["identity"]["name"] not in current, f"{item['id']}: a retired identity is not an identity of the file"
            assert item["place"] in manifest["places"] and item["why"], item["id"]
            if "replacedBy" in item:
                assert looked_up(item), f"{item['id']}: the grant of an identity that is not looked up is not one that a grant replaces"
                assert "roleStays" not in item and "alsoHeldBy" not in item, f"{item['id']}: replacedBy and roleStays are two kinds of item"
                replacing = grants.get(item["replacedBy"])
                assert replacing, f"{item['id']}: replacedBy is the id of a grant of the file"
                assert (item["role"], item["place"]) == (replacing["role"], replacing["place"]), (
                    f"{item['id']}: the role and the place of a retired grant are those of the grant that replaces it, {item['replacedBy']}")
            elif "roleStays" in item:
                assert item["roleStays"] is True and looked_up(item), f"{item['id']}: roleStays is true, and its identity is looked up"
                spec = manifest["roles"].get(item["role"])
                assert spec and spec["kind"] == "builtin", f"{item['id']}: roleStays is for a built-in role of the file, which stays"
                also = item.get("alsoHeldBy")
                if also is not None:
                    assert isinstance(also, dict) and also.get("app") and also.get("appName") and also.get("siteOption") in SITE_OPTIONS, (
                        f"{item['id']}: alsoHeldBy names the app, its name and the option that gives its name ({', '.join(SITE_OPTIONS)})")
            else:
                assert "alsoHeldBy" not in item, f"{item['id']}: alsoHeldBy belongs to an item with roleStays"
                assert item["role"] and item["role"] not in manifest["roles"], f"{item['id']}: a retired role is not a role of the file"
    except (OSError, ValueError, KeyError, AssertionError, TypeError) as e:
        raise Problem(f"{path} is not a valid list of access requirements ({e})") from e
    return manifest


def selected(manifest: dict, only: str | None) -> list[dict]:
    if not only:
        return manifest["grants"]
    wanted = [x.strip() for x in only.split(",") if x.strip()]
    known = {g["id"]: g for g in manifest["grants"]}
    unknown = [x for x in wanted if x not in known]
    if unknown:
        raise Problem(f"--only names {', '.join(unknown)}; the requirements are {', '.join(known)}")
    return [known[x] for x in wanted]


def holder_text(identity: dict, holder: dict) -> str:
    """How a holder is named in the table of the proposal."""
    if holder["kind"] == "system":
        return f"the system-assigned identity of {identity['app']} (`{identity['appName']}`)"
    return f"the user-assigned identity `{holder['name']}`"


def markdown(manifest: dict) -> str:
    """The table of the requirements, for the proposal."""
    rows = ["| # | Identity | Role | Where | What it is for |", "|---|---|---|---|---|"]
    for g in manifest["grants"]:
        custom = " (custom role)" if manifest["roles"][g["role"]]["kind"] == "custom" else ""
        identity = manifest["identities"][g["identity"]]
        holders = " and ".join(holder_text(identity, h) for h in identity["holders"])
        rows.append(f"| {g['id']} | {holders[0].upper() + holders[1:]} | {g['role']}{custom} | {manifest['places'][g['place']]} | {g['why']} |")
    return "\n".join(rows)


def markdown_tenant(manifest: dict) -> str:
    """The table of the reads that no Azure role at a subscription or a management group gives: they are at the tenant or at a billing scope, which a person gives in the Billing area of the
    portal or at the tenant scope of Reservations and of Savings plans, for the proposal. This tool neither checks nor gives them."""
    rows = ["| # | Read | Who can give it | What it is for |", "|---|---|---|---|"]
    for item in manifest.get("tenantReads", []):
        rows.append(f"| {item['id']} | {item['read']} | {' '.join(item['roles'])} | {item['why']} |")
    return "\n".join(rows)


def markdown_retired(manifest: dict) -> str:
    """The table of what an earlier version granted and is to be removed, for the proposal."""
    rows = ["| # | Identity | Role | Where | Why it is retired |", "|---|---|---|---|---|"]
    for r in manifest.get("retired", []):
        custom = "" if r["role"] in manifest["roles"] and manifest["roles"][r["role"]]["kind"] == "builtin" else " (custom role)"
        also = r.get("alsoHeldBy")
        who = f"`{r['identity']['name']}`" + (f" and the system-assigned identity of {also['app']} (`{also['appName']}`)" if also else "")
        rows.append(f"| {r['id']} | {who} | {r['role']}{custom} | {manifest['places'][r['place']]} | {r['why']} |")
    return "\n".join(rows)


# ---- the places ----------------------------------------------------------------------------------------------------------------------------------

class Places:
    def __init__(self, project_subscription=None, project_group=None, estate=None, gateway=None, gateway_insights=None, workspace=None, sites=None) -> None:
        self.project_subscription, self.project_group, self.estate = project_subscription, project_group, list(estate or [])
        self.gateway, self.gateway_insights, self.workspace = gateway, gateway_insights, workspace
        self.sites = dict(sites or {})


def checked(value, pattern, option: str, what: str):
    if value and not pattern.match(value):
        raise Problem(f"{option} is {what}")
    return value


def read_places(args, env) -> Places:
    pick = lambda option, name: getattr(args, option, None) or env.get(name) or None  # noqa: E731
    estate = list(args.estate or []) or [x.strip() for x in (env.get("ACCESS_ESTATE_SCOPES") or "").split(",") if x.strip()]
    places = Places(
        project_subscription=checked(pick("project_subscription", "ENV_SUBSCRIPTION_ID"), GUID_ONLY, "--project-subscription", "a subscription id"),
        project_group=checked(pick("project_group", "ENV_RESOURCE_GROUP"), re.compile(rf"^{NAME}$"), "--project-group", "a resource group name"),
        estate=estate,
        gateway=checked(pick("gateway", "ACCESS_GATEWAY_ID"), APIM, "--gateway", "the resource id of the API Management instance"),
        gateway_insights=checked(pick("gateway_insights", "ACCESS_GATEWAY_INSIGHTS_ID"), INSIGHTS, "--gateway-insights",
                                 "the resource id of the gateway's Application Insights component"),
        workspace=checked(pick("workspace", "ACCESS_WORKSPACE_ID"), WORKSPACE, "--workspace", "the resource id of the central Log Analytics workspace"),
        sites={option: checked(pick(option[2:].replace("-", "_"), setting), SITE_NAME, option, "the name of a function app: letters, digits and hyphens")
               for option, setting in SITE_OPTIONS.items()},
    )
    for scope in places.estate:
        if not any(p.match(scope) for p in (SUBSCRIPTION, MANAGEMENT_GROUP, RESOURCE_GROUP)):
            raise Problem(f"--estate holds {scope}: a subscription, a management group or a resource group, as a resource id")
    if not places.estate and places.project_subscription:
        places.estate = [f"/subscriptions/{places.project_subscription}"]
    return places


def need(value, option: str, what: str):
    if not value:
        raise Problem(f"{option} is not set: it is {what}")
    return value


def workspace_of(az: Az, places: Places) -> str:
    """The central workspace: given, or the one that the gateway's component writes to."""
    if not places.workspace:
        insights = need(places.gateway_insights, "--workspace or --gateway-insights", "the central workspace, or the component that writes to it")
        found = az.json("rest", "--method", "get", "--url", f"{ARM}{insights}?api-version={INSIGHTS_API}", "--output", "json")
        value = ((found or {}).get("properties") or {}).get("WorkspaceResourceId")
        if not isinstance(value, str) or not WORKSPACE.match(value):
            raise Problem("the gateway's component names no workspace: give --workspace")
        places.workspace = value
    return places.workspace


def scopes_for(place: str, places: Places, az: Az) -> list[str]:
    if place == "estate":
        return need(places.estate, "--estate or --project-subscription", "what the Watch reads")
    if place == "gatewayGroup":
        return [APIM.match(need(places.gateway, "--gateway", "the resource id of the API Management instance")).group(1)]
    if place == "gatewayInsights":
        return [need(places.gateway_insights, "--gateway-insights", "the resource id of the gateway's Application Insights component")]
    if place == "centralWorkspace":
        return [workspace_of(az, places)]
    if place == "projectGroup":
        return [project_group_scope(places)]
    raise Problem(f"unknown place {place}")


def project_group_scope(places: Places) -> str:
    return (f"/subscriptions/{need(places.project_subscription, '--project-subscription', 'the subscription of the project')}"
            f"/resourceGroups/{need(places.project_group, '--project-group', 'the resource group of the project')}")


def definition_group(where: str, places: Places, az: Az) -> str:
    """The resource group in which a custom role is defined: its one assignable scope."""
    if where == "gatewayGroup":
        return APIM.match(need(places.gateway, "--gateway", "the resource id of the API Management instance")).group(1)
    if where == "projectGroup":
        return project_group_scope(places)
    return WORKSPACE.match(workspace_of(az, places)).group(1)


def subscription_of(scope: str) -> str:
    return scope.split("/")[2]


# ---- what is granted -----------------------------------------------------------------------------------------------------------------------------

class Item:
    """One requirement of one holder at one scope, and where it stands."""

    def __init__(self, grant: dict, scope: str, state: str, principal: str | None = None, role_id: str | None = None, detail: str = "", holder: str = "") -> None:
        self.grant, self.scope, self.state, self.principal, self.role_id, self.detail, self.holder = grant, scope, state, principal, role_id, detail, holder


def principal_of(az: Az, places: Places, name: str) -> str | None:
    code, out, err = az.run("identity", "show", "--subscription", need(places.project_subscription, "--project-subscription", "the subscription of the project"),
                            "--resource-group", need(places.project_group, "--project-group", "the resource group of the project"), "--name", name,
                            "--query", "principalId", "--output", "tsv")
    if code == 0 and out.strip():
        return out.strip()
    if code != 0 and not NOT_FOUND.search(err or ""):
        raise Problem(f"the identity {name} could not be read: {first_line(err)}")
    return None


def system_principal_of(az: Az, group: str, site: str) -> tuple[str | None, str]:
    """(the object id of the app's system-assigned identity, or None and what is missing). The app is read, never changed."""
    code, out, err = az.run("rest", "--method", "get", "--url", f"{ARM}{group}/providers/Microsoft.Web/sites/{site}?api-version={SITE_API}", "--output", "json")
    if code != 0:
        if NOT_FOUND.search(err or ""):
            return None, "does not exist yet"
        raise Problem(f"the app {site} could not be read: {first_line(err)}")
    try:
        identity = (json.loads(out) or {}).get("identity") or {}
    except ValueError as e:
        raise Problem(f"the app {site} could not be read: the answer is not JSON") from e
    principal = identity.get("principalId")
    if "systemassigned" in str(identity.get("type", "")).lower() and isinstance(principal, str) and principal.strip():
        return principal.strip(), ""
    return None, "has no system-assigned identity yet"


def holder_principal(az: Az, places: Places, identity: dict, holder: dict) -> tuple[str | None, str, str]:
    """(object id or None, how the holder is named in a report, what is missing when there is no object id)."""
    if holder["kind"] == "user":
        name = holder["name"]
        return principal_of(az, places, name), name, f"{name} does not exist yet: the Hub action {identity['madeBy']} makes it"
    group = project_group_scope(places)
    option = holder["siteOption"]
    site = need(places.sites.get(option), option, f"the name of {identity['app']} ({identity['appName']}), whose system-assigned identity holds these grants")
    principal, why = system_principal_of(az, group, site)
    return principal, f"{site} (system-assigned)", f"{site} {why}: the Hub action {identity['madeBy']} makes it"


def definition_problems(definition: dict, spec: dict, expected_scope: str) -> list[str]:
    permissions = (definition.get("permissions") or [{}])[0]
    wanted = {"actions": spec["actions"], "notActions": [], "dataActions": [], "notDataActions": []}
    problems = []
    for key, expected in wanted.items():
        have = sorted(x.lower() for x in permissions.get(key) or [])
        if have != sorted(x.lower() for x in expected):
            problems.append(f"{key} are {', '.join(permissions.get(key) or []) or 'none'}, the file says {', '.join(expected) or 'none'}")
    if sorted(s.lower() for s in definition.get("assignableScopes") or []) != [expected_scope.lower()]:
        problems.append(f"it can be assigned at {', '.join(definition.get('assignableScopes') or [])}, the file says {expected_scope}")
    return problems


def custom_roles_named(az: Az, subscription: str, name: str) -> list[dict]:
    """The custom roles of that name that the subscription can see (a role that is assignable in one of its resource groups is among them)."""
    return az.json("role", "definition", "list", "--subscription", subscription, "--name", name, "--custom-role-only", "true") or []


def role_state(az: Az, name: str, spec: dict, places: Places) -> tuple[str | None, str, str]:
    """(role id or None, 'ok' | 'role-missing' | 'role-differs', detail)."""
    if spec["kind"] == "builtin":
        return spec["id"], "ok", ""
    group = definition_group(spec["definedIn"], places, az)
    found = custom_roles_named(az, subscription_of(group), name)
    if not found:
        return None, "role-missing", "the custom role does not exist yet; grant makes it first"
    if len(found) > 1:
        raise Problem(f"two custom roles are called {name}")
    problems = definition_problems(found[0], spec, group)
    return found[0]["name"], ("role-differs" if problems else "ok"), "; ".join(problems)


def all_pages(az: Az, url: str) -> list[dict]:
    """Every item of a list that Azure returns in pages."""
    found: list[dict] = []
    while url:
        page = az.json("rest", "--method", "get", "--url", url, "--output", "json") or {}
        found += [v for v in page.get("value") or [] if isinstance(v, dict)]
        url = page.get("nextLink")
    return found


def assignments(az: Az, principal: str, scope: str) -> list[dict]:
    """The principal's assignments at, above and below the scope (the list for a scope with this filter returns all three)."""
    return all_pages(az, f"{ARM}{scope}/providers/Microsoft.Authorization/roleAssignments?api-version={ASSIGNMENTS_API}&$filter=principalId eq '{principal}'")


def covers(assigned_scope: str, target: str) -> bool:
    """True when an assignment at assigned_scope applies at target: the same place, a place above it, or a management group (which is above any other place)."""
    a, t = assigned_scope.rstrip("/").lower(), target.rstrip("/").lower()
    return a == t or t.startswith(a + "/") or (a.startswith(MANAGEMENT_PREFIX) and not t.startswith(MANAGEMENT_PREFIX))


def examine(az: Az, manifest: dict, places: Places, only: str | None = None) -> list[Item]:
    items: list[Item] = []
    principals: dict[tuple[str, int], tuple[str | None, str, str]] = {}
    roles: dict[str, tuple] = {}
    listed: dict[tuple[str, str], list[dict]] = {}
    for grant in selected(manifest, only):
        identity = manifest["identities"][grant["identity"]]
        for index, holder in enumerate(identity["holders"]):
            if (grant["identity"], index) not in principals:
                principals[(grant["identity"], index)] = holder_principal(az, places, identity, holder)
            principal, label, missing = principals[(grant["identity"], index)]
            for scope in scopes_for(grant["place"], places, az):
                if principal is None:
                    items.append(Item(grant, scope, "no-identity", detail=missing, holder=label))
                    continue
                name = grant["role"]
                if name not in roles:
                    roles[name] = role_state(az, name, manifest["roles"][name], places)
                role_id, hint, detail = roles[name]
                if hint == "role-missing":
                    items.append(Item(grant, scope, "role-missing", principal, None, detail, label))
                    continue
                if hint == "role-differs":
                    items.append(Item(grant, scope, "role-differs", principal, role_id, detail, label))
                    continue
                if (principal, scope) not in listed:
                    listed[(principal, scope)] = assignments(az, principal, scope)
                held = any(str(a.get("properties", {}).get("roleDefinitionId", "")).rsplit("/", 1)[-1].lower() == role_id.lower()
                           and covers(str(a["properties"].get("scope", "")), scope) for a in listed[(principal, scope)])
                items.append(Item(grant, scope, "present" if held else "missing", principal, role_id, holder=label))
    return items


def describe(item: Item, manifest: dict) -> str:
    line = f"  {STATES[item.state]:<13}{item.grant['id']}  {item.holder}  {item.grant['role']}  at {item.scope}"
    return line + (f"\n               {item.detail}" if item.detail else "")


def report(items: list[Item], manifest: dict, out) -> bool:
    for item in items:
        out(describe(item, manifest))
    done = sum(1 for i in items if i.state == "present")
    out(f"{done} of {len(items)} present.")
    return done == len(items)


# ---- making what is missing ----------------------------------------------------------------------------------------------------------------------

class Step:
    def __init__(self, kind: str, role: str, scope: str, principal: str | None = None, role_id: str | None = None) -> None:
        self.kind, self.role, self.scope, self.principal, self.role_id = kind, role, scope, principal, role_id


def build_definition(manifest: dict, name: str, places: Places, az: Az) -> dict:
    spec = manifest["roles"][name]
    return {"Name": name, "IsCustom": True, "Description": spec["description"], "Actions": list(spec["actions"]), "NotActions": [], "DataActions": [],
            "NotDataActions": [], "AssignableScopes": [definition_group(spec["definedIn"], places, az)]}


def plan_for(items: list[Item]) -> list[Step]:
    steps, defined = [], set()
    for item in items:
        if item.state == "role-missing":
            if item.grant["role"] not in defined:
                defined.add(item.grant["role"])
                steps.append(Step("define", item.grant["role"], item.scope))
            steps.append(Step("assign", item.grant["role"], item.scope, item.principal))
        elif item.state == "missing":
            steps.append(Step("assign", item.grant["role"], item.scope, item.principal, item.role_id))
    return steps


def show_step(step: Step, manifest: dict, places: Places, az: Az) -> str:
    if step.kind == "define":
        definition = build_definition(manifest, step.role, places, az)
        return (f"az role definition create --subscription {subscription_of(definition['AssignableScopes'][0])} --role-definition <the definition of {step.role}: "
                f"{', '.join(definition['Actions'])}; assignable only in {definition['AssignableScopes'][0]}>")
    role = step.role_id or step.role
    return (f"az role assignment create --assignee-object-id {step.principal} --assignee-principal-type ServicePrincipal --role \"{role}\" "
            f"--scope {step.scope}   # {step.role}")


def apply_steps(az: Az, steps: list[Step], manifest: dict, places: Places, out, sleep=time.sleep) -> None:
    made: dict[str, str] = {}
    for step in steps:
        if step.kind == "define":
            with json_file(build_definition(manifest, step.role, places, az)) as path:
                created = az.json("role", "definition", "create", "--subscription", subscription_of(definition_group(manifest["roles"][step.role]["definedIn"], places, az)),
                                  "--role-definition", path)
            made[step.role] = created["name"]
            out(f"  made the custom role {step.role} ({created['name']}), assignable only in {created['assignableScopes'][0]}")
            continue
        role = step.role_id or made.get(step.role) or step.role
        for attempt in range(1, 9):
            code, text, err = az.run("role", "assignment", "create", "--assignee-object-id", step.principal, "--assignee-principal-type", "ServicePrincipal",
                                     "--role", role, "--scope", step.scope, "--output", "json")
            if code == 0:
                out(f"  assigned {step.role} at {step.scope} (assignment {json.loads(text)['name']})")
                break
            if re.search(r"already exists", err or "", re.I):
                out(f"  {step.role} at {step.scope} was there already")
                break
            if attempt < 8 and re.search(r"RoleDefinitionDoesNotExist|role definition .* does not exist|Cannot find role", err or "", re.I):
                sleep(15)
                continue
            raise Problem(f"{step.role} at {step.scope} could not be assigned: {first_line(err)}")


def signed_in(az: Az) -> str:
    code, out, err = az.run("account", "show", "--query", "user.name", "--output", "tsv")
    if code != 0 or not out.strip():
        raise Problem("nobody is signed in to the Azure CLI")
    return out.strip()


# ---- what an earlier version granted ---------------------------------------------------------------------------------------------------------------

LEFT_STATES = {"there": "still there", "gone": "gone", "left-alone": "left alone", "kept": "kept"}
ASSIGNMENT_TAIL = re.compile(rf"/providers/Microsoft\.Authorization/roleAssignments/{GUID}$", re.I)
NOT_THERE = re.compile(r"could not be found|was not found|does not exist|ResourceNotFound|RoleAssignmentNotFound", re.I)
STILL_ASSIGNED = re.compile(r"RoleDefinitionHasAssignments|existing role assignments", re.I)


class Left:
    """One retired item at one scope, and what is still there of it. holder says whose assignments these are, for an item that names an identity ('' means the identity of the item);
    listed_at is where the assignments of a custom role were listed, when that is not the place itself (the resource group where the role was defined)."""

    def __init__(self, item: dict, scope: str, state: str, role_id: str | None = None, assigned: list[dict] | None = None, detail: str = "",
                 holder: str = "", listed_at: str = "") -> None:
        self.item, self.scope, self.state, self.role_id, self.assigned, self.detail = item, scope, state, role_id, assigned or [], detail
        self.holder, self.listed_at = holder, listed_at


class Removal:
    """One command that removes something of a retired item: an assignment (target is its id) or the custom role (target is its id)."""

    def __init__(self, kind: str, role: str, scope: str, target: str) -> None:
        self.kind, self.role, self.scope, self.target = kind, role, scope, target


def selected_retired(manifest: dict, only: str | None) -> list[dict]:
    retired = manifest.get("retired") or []
    if not only:
        return retired
    wanted = [x.strip() for x in only.split(",") if x.strip()]
    known = {r["id"]: r for r in retired}
    unknown = [x for x in wanted if x not in known]
    if unknown:
        raise Problem(f"--only names {', '.join(unknown)}; the retired items are {', '.join(known) or 'none'}")
    return [known[x] for x in wanted]


def inside(scope: str, place: str) -> bool:
    """True when scope is the place or something below it."""
    s, p = scope.rstrip("/").lower(), place.rstrip("/").lower()
    return s == p or s.startswith(p + "/")


def of_one_identity(item: dict) -> bool:
    """A retired item with replacedBy is a grant of an identity that an app no longer runs as; one with roleStays is a grant of a built-in role that nothing needs any more.
    The role is kept in both: by the grant that replaces it, or because it is built in. So only the assignments that the identities of the item hold are removed:
    never another holder's, and never the role."""
    return "replacedBy" in item or bool(item.get("roleStays"))


def defined_in(place: str, scope: str) -> str:
    """Where a retired custom role of this place was made assignable: the place itself, or, for the central workspace, the resource group that holds it."""
    return WORKSPACE.match(scope).group(1) if place == "centralWorkspace" and WORKSPACE.match(scope) else scope


def recognised(assignment: dict, scope: str, role_id: str) -> dict:
    """The assignment, when its id is that of a role assignment at or below the scope: nothing else is ever passed to a delete."""
    given = assignment.get("id")
    if not (isinstance(given, str) and inside(given, scope) and ASSIGNMENT_TAIL.search(given)):
        raise Problem(f"Azure listed an assignment of the role {role_id} with an id that this tool does not recognise: {str(given)[:200]}")
    return assignment


def role_of(assignment: dict) -> str:
    return str((assignment.get("properties") or {}).get("roleDefinitionId", "")).rsplit("/", 1)[-1].lower()


def scope_of(assignment: dict) -> str:
    return str((assignment.get("properties") or {}).get("scope", ""))


def assignments_of_role(az: Az, scope: str, role_id: str) -> list[dict]:
    """The assignments of one role at the scope and below it, whoever holds them. Azure keeps the assignment of an identity that was deleted, and the
    portal shows it as 'Identity not found', so this lists by role and never by identity."""
    return [recognised(assignment, scope, role_id)
            for assignment in all_pages(az, f"{ARM}{scope}/providers/Microsoft.Authorization/roleAssignments?api-version={ASSIGNMENTS_API}")
            if role_of(assignment) == role_id.lower() and inside(scope_of(assignment), scope)]


def replacement_problems(az: Az, manifest: dict, places: Places, item: dict, scope: str) -> list[str]:
    """Why the grant that replaces a retired one is not yet in place at this scope for every holder of its identity. Reads like check does."""
    problems = []
    for found in examine(az, manifest, places, item["replacedBy"]):
        if found.scope.rstrip("/").lower() == scope.rstrip("/").lower() and found.state != "present":
            why = f": {found.detail}" if found.detail else ""
            problems.append(f"{item['replacedBy']} is not present for {found.holder} at {scope} ({STATES[found.state]}{why})")
    return problems


def find_held(az: Az, manifest: dict, places: Places, item: dict, scope: str, principal: str | None, holder: str = "") -> Left:
    """What a retired identity still holds of one grant at one place: its own assignments of the role and nobody else's. Reads only."""
    name = holder or item["identity"]["name"]
    role_id, _, _ = role_state(az, item["role"], manifest["roles"][item["role"]], places)
    if role_id is None or principal is None:
        return Left(item, scope, "gone", holder=holder)
    held = [a for a in assignments(az, principal, scope) if role_of(a) == role_id.lower()]
    here = [a for a in held if inside(scope_of(a), scope)]
    outside = sorted({scope_of(a) for a in held if not inside(scope_of(a), scope)})
    note = f"{name} also holds it at {', '.join(outside)}, outside this place: nothing is removed there" if outside else ""
    if not here:
        return Left(item, scope, "left-alone" if outside else "gone", role_id, detail=note, holder=holder)
    problems = replacement_problems(az, manifest, places, item, scope) if "replacedBy" in item else []
    if problems:
        why = "; ".join(problems) + f". The {len(here)} assignment(s) of {name} stay until it is, so that the app is not left without access"
        return Left(item, scope, "kept", role_id, here, why + (f". {note}" if note else ""), holder=holder)
    return Left(item, scope, "there", role_id, [recognised(a, scope, role_id) for a in here], note, holder=holder)


def find_held_by_the_app(az: Az, manifest: dict, places: Places, item: dict, scope: str) -> Left:
    """The same for the system-assigned identity of the app that the item names (alsoHeldBy): the app is read in the project's group and never changed."""
    also = item["alsoHeldBy"]
    option = also["siteOption"]
    site = need(places.sites.get(option), option, f"the name of {also['app']} ({also['appName']}), whose system-assigned identity also holds this grant")
    principal, why = system_principal_of(az, project_group_scope(places), site)
    holder = f"{site} (system-assigned)"
    left = find_held(az, manifest, places, item, scope, principal, holder)
    if principal is None:
        left.detail = (f"{site} {why}, so nothing can be traced to its identity by name: Azure keeps the assignments of a deleted identity, shows them as 'Identity not found', "
                       "and this tool cannot tell whose they were. It removes the grants of an identity while the identity exists")
    return left


def find_retired(az: Az, manifest: dict, places: Places, only: str | None = None) -> tuple[list[Left], dict[str, str | None]]:
    """What is still there of each retired item: reads only. Also the object id of each retired identity that still exists."""
    left: list[Left] = []
    identities: dict[str, str | None] = {}
    named: dict[tuple[str, str], list[dict]] = {}
    for item in selected_retired(manifest, only):
        name = item["identity"]["name"]
        if looked_up(item) and name not in identities:
            identities[name] = principal_of(az, places, name)
        for scope in scopes_for(item["place"], places, az):
            if of_one_identity(item):
                left.append(find_held(az, manifest, places, item, scope, identities[name]))
                if "alsoHeldBy" in item:
                    left.append(find_held_by_the_app(az, manifest, places, item, scope))
                continue
            key = (subscription_of(scope), item["role"])
            if key not in named:
                named[key] = custom_roles_named(az, key[0], item["role"])
            if not named[key]:
                left.append(Left(item, scope, "gone"))
                continue
            if len(named[key]) > 1:
                raise Problem(f"two custom roles are called {item['role']}")
            role = named[key][0]
            home = defined_in(item["place"], scope)
            outside = [s for s in role.get("assignableScopes") or [] if not inside(s, home)]
            if outside:
                left.append(Left(item, scope, "left-alone", role["name"],
                                 detail=f"the custom role can also be assigned at {', '.join(outside)}, outside this place: it is not what was granted here, so nothing of it is touched"))
                continue
            left.append(Left(item, scope, "there", role["name"], assignments_of_role(az, home, role["name"]), listed_at=home if home != scope else ""))
    return left, identities


def describe_left(left: Left, identities: dict[str, str | None]) -> str:
    item = left.item
    name = left.holder or item["identity"]["name"]
    lines = [f"  {LEFT_STATES[left.state]:<13}{item['id']}  {name}  {item['role']}  at {left.scope}"]
    if left.detail:
        lines.append(f"               {left.detail}")
    if left.state == "there" and of_one_identity(item):
        lines.append(f"               {name} holds {len(left.assigned)} assignment(s) of {item['role']} at or below this place:")
        for assignment in left.assigned:
            lines.append(f"                 {assignment['id']}")
    elif left.state == "there":
        where = f"at or below {left.listed_at} (the resource group where the role was defined)" if left.listed_at else "at or below this place"
        lines.append(f"               the custom role exists ({left.role_id}); {len(left.assigned)} assignment(s) of it {where}" + (":" if left.assigned else ""))
        for assignment in left.assigned:
            holder = str((assignment.get("properties") or {}).get("principalId", ""))
            if not looked_up(item):
                who = f"{holder} ({name}, or another identity: every assignment of the role at this place is removed, whoever holds it)"
            else:
                who = name if holder and holder.lower() == (identities.get(name) or "").lower() else (
                    f"{holder} (an identity that is not {name}, or one that was deleted: the portal shows that as 'Identity not found')")
            lines.append(f"                 {assignment['id']}  held by {who}")
    return "\n".join(lines)


def identity_notes(identities: dict[str, str | None], places: Places, of_one: dict[str, str] | None = None) -> list[str]:
    """What to say about each user-assigned identity that an item names. of_one maps the name of an identity whose grant stays with the role to who removes the identity."""
    of_one = of_one or {}
    notes = []
    for name, principal in identities.items():
        if principal:
            remover = of_one[name] if name in of_one else "the deployment workflow or the owner removes it"
            notes.append(f"  note         {name} still exists in {project_group_scope(places)} (object id {principal}). This tool never deletes an identity: "
                         f"{remover}.")
        else:
            notes.append(f"  note         {name} does not exist in {project_group_scope(places)}." + (
                " Nothing can be traced to it by name any more: Azure keeps the assignments of a deleted identity, and the portal shows them as 'Identity not found'. "
                "This tool cannot tell whose they were, so it leaves them. It removes the grants of an identity while the identity exists: run retire before the identity is deleted."
                if name in of_one else ""))
    return notes


def retire_plan(found: list[Left]) -> list[Removal]:
    steps = [Removal("unassign", left.item["role"], left.scope, a["id"]) for left in found if left.state == "there" for a in left.assigned]
    defined: set[str] = set()
    for left in found:
        if left.state == "there" and not of_one_identity(left.item) and left.role_id not in defined:
            defined.add(left.role_id)
            steps.append(Removal("undefine", left.item["role"], left.scope, left.role_id))
    return steps


def show_removal(step: Removal) -> str:
    if step.kind == "unassign":
        return f"az role assignment delete --ids {step.target}   # {step.role} at {step.scope}"
    return (f"az role definition delete --subscription {subscription_of(step.scope)} --name {step.target}   "
            f"# the custom role {step.role}, only when no assignment of it remains")


def apply_retirement(az: Az, found: list[Left], out, sleep=time.sleep) -> None:
    for left in found:
        if left.state != "there":
            continue
        for assignment in left.assigned:
            code, _, err = az.run("role", "assignment", "delete", "--ids", assignment["id"])
            if code == 0:
                out(f"  removed the assignment {assignment['id']}")
            elif NOT_THERE.search(err or ""):
                out(f"  the assignment {assignment['id']} was gone already")
            else:
                raise Problem(f"the assignment {assignment['id']} of {left.item['role']} could not be removed: {first_line(err)}")
    handled: set[str] = set()
    for left in found:
        if left.state != "there" or of_one_identity(left.item) or left.role_id in handled:
            continue
        handled.add(left.role_id)
        remaining = [a for other in found if other.state == "there" and other.role_id == left.role_id
                     for a in assignments_of_role(az, other.listed_at or other.scope, left.role_id)]
        if remaining:
            out(f"  kept the custom role {left.item['role']}: {len(remaining)} assignment(s) of it remain")
            continue
        for attempt in range(1, 9):
            code, _, err = az.run("role", "definition", "delete", "--subscription", subscription_of(left.scope), "--name", left.role_id)
            if code == 0:
                out(f"  removed the custom role {left.item['role']} ({left.role_id})")
                break
            if NOT_THERE.search(err or ""):
                out(f"  the custom role {left.item['role']} was gone already")
                break
            if attempt < 8 and STILL_ASSIGNED.search(err or ""):
                sleep(15)
                continue
            raise Problem(f"the custom role {left.item['role']} could not be removed: {first_line(err)}")


def show_retired(found: list[Left], identities: dict[str, str | None], places: Places, out) -> None:
    for left in found:
        out(describe_left(left, identities))
    after = "after this tool has taken away its grants (environment/BOOTSTRAP.md)"
    removers = {left.item["identity"]["name"]: (f"{left.item['identityRemovedBy']} removes it, {after}" if left.item.get("identityRemovedBy") else f"a person removes it, with `az identity delete`, {after}")
                for left in found if of_one_identity(left.item)}
    for note in identity_notes(identities, places, removers):
        out(note)


def report_retired(found: list[Left], identities: dict[str, str | None], places: Places, out) -> bool:
    show_retired(found, identities, places, out)
    done = sum(1 for left in found if left.state == "gone")
    out(f"{done} of {len(found)} gone.")
    return done == len(found)


# ---- the commands --------------------------------------------------------------------------------------------------------------------------------

def command_check(args, az: Az, manifest: dict, places: Places, out) -> int:
    out(f"Access that Meternaut needs outside its own resource group (signed in as {signed_in(az)}):")
    return 0 if report(examine(az, manifest, places, args.only), manifest, out) else 1


def command_grant(args, az: Az, manifest: dict, places: Places, out, sleep, ask, env) -> int:
    if args.apply and env.get("GITHUB_ACTIONS") == "true":
        raise Problem("a person with the right to assign roles runs this, never a pipeline: the workflow's identity must not hold that right (AGENTS.md rule 18)")
    who = signed_in(az)
    out(f"Signed in as {who}.")
    items = examine(az, manifest, places, args.only)
    steps = plan_for(items)
    blocked = [i for i in items if i.state in UNFIXABLE]
    for item in items:
        out(describe(item, manifest))
    if not steps:
        out("Nothing to grant." if not blocked else "Nothing can be granted until the lines above that say 'cannot yet' or 'role differs' are settled.")
        return 1 if blocked else 0
    out(f"{len(steps)} change(s) would be made, and nothing else:")
    for step in steps:
        out(f"  {show_step(step, manifest, places, az)}")
    if not args.apply:
        out("This was a dry run. Run again with --apply to make them.")
        return 1 if blocked else 0
    if not args.yes:
        answer = ask(f"Make these {len(steps)} change(s) as {who}? Type yes: ")
        if answer is None:
            raise Problem("--apply needs --yes when there is no terminal to ask in")
        if answer.strip().lower() != "yes":
            raise Problem("nothing was changed")
    apply_steps(az, steps, manifest, places, out, sleep)
    out("Checking again:")
    return 0 if report(examine(az, manifest, places, args.only), manifest, out) else 1


def command_retire(args, az: Az, manifest: dict, places: Places, out, sleep, ask, env) -> int:
    if args.apply and env.get("GITHUB_ACTIONS") == "true":
        raise Problem("a person with the right to assign roles runs this, never a pipeline: the workflow's identity must not hold that right (AGENTS.md rule 18)")
    who = signed_in(az)
    out(f"Signed in as {who}.")
    found, identities = find_retired(az, manifest, places, args.only)
    show_retired(found, identities, places, out)
    steps = retire_plan(found)
    blocked = [left for left in found if left.state in ("left-alone", "kept")]
    if not steps:
        stuck = " or ".join(f"'{LEFT_STATES[state]}'" for state in ("left-alone", "kept") if any(left.state == state for left in blocked))
        out("Nothing to retire." if not blocked else f"Nothing can be retired until the lines above that say {stuck} are settled.")
        return 1 if blocked else 0
    out(f"{len(steps)} change(s) would be made, and nothing else:")
    for step in steps:
        out(f"  {show_removal(step)}")
    if not args.apply:
        out("This was a dry run. Run again with --apply to make them.")
        return 1
    if not args.yes:
        answer = ask(f"Make these {len(steps)} change(s) as {who}? Type yes: ")
        if answer is None:
            raise Problem("--apply needs --yes when there is no terminal to ask in")
        if answer.strip().lower() != "yes":
            raise Problem("nothing was changed")
    apply_retirement(az, found, out, sleep)
    out("Checking again:")
    found, identities = find_retired(az, manifest, places, args.only)
    return 0 if report_retired(found, identities, places, out) else 1


def main(argv=None, az: Az | None = None, env=None, out=print, sleep=time.sleep, ask=None) -> int:
    env = os.environ if env is None else env
    ask = ask or (lambda prompt: input(prompt) if sys.stdin.isatty() else None)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    table = commands.add_parser("markdown", help="print the table of the requirements")
    table.add_argument("--retired", action="store_true", help="print the table of the retired grants instead")
    table.add_argument("--tenant", action="store_true", help="print the table of the reads at the tenant or a billing scope instead (a person gives them; this tool does not check them)")
    for name, text in (("check", "read only: which requirements are present"), ("grant", "dry run; with --apply, make what is missing"),
                       ("retire", "dry run; with --apply, remove what an earlier version granted (the list retired)")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--only", help="comma separated ids, for example R1,R4 (retire: W1,W2)")
        sub.add_argument("--project-subscription")
        sub.add_argument("--project-group")
        sub.add_argument("--cases-site", help="the name of the cases app in the project's group, func-meternaut-cases-... (setting ACCESS_CASES_SITE)")
        sub.add_argument("--usage-site", help="the name of the usage app in the project's group, func-meternaut-usage-... (setting ACCESS_USAGE_SITE)")
        sub.add_argument("--estate", action="append", help="a subscription, management group or resource group id; repeat for more")
        sub.add_argument("--gateway")
        sub.add_argument("--gateway-insights")
        sub.add_argument("--workspace")
        if name != "check":
            sub.add_argument("--apply", action="store_true", help="make the changes (the default is a dry run)")
            sub.add_argument("--yes", action="store_true", help="do not ask first")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest()
        if args.command == "markdown":
            out(markdown_retired(manifest) if args.retired else markdown_tenant(manifest) if args.tenant else markdown(manifest))
            return 0
        az = az or Az()
        places = read_places(args, env)
        if args.command == "check":
            return command_check(args, az, manifest, places, out)
        if args.command == "retire":
            return command_retire(args, az, manifest, places, out, sleep, ask, env)
        return command_grant(args, az, manifest, places, out, sleep, ask, env)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
