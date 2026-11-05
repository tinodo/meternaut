#!/usr/bin/env python3
"""The access that Meternaut needs outside its own resource group, and the installer that reads it (standard library only).

    python tools/access-requirements.py markdown
    python tools/access-requirements.py check [places] [--only R1,R3]
    python tools/access-requirements.py grant [places] [--only R1,R3] [--apply] [--yes]

The deployment workflow's identity may change only the project's own resource group and must not get a right anywhere else (AGENTS.md rule 18).
The identities that the workflow makes (one for the usage recording, one for the first cases) still need rights in other places: the subscriptions
that the Watch reads, the gateway, the central workspace. Only a person who may assign roles there can give them. The file
environment/access-requirements.json says which role of which identity at which place. This tool reads that file and the signed-in person's view
of Azure.

markdown  Prints the table of the requirements, as docs/proposals/03-access-and-onboarding.md shows it. Reads no Azure.
check     Read only. For each requirement: present, missing, or why it cannot be present yet (the identity does not exist, the custom role does not
          exist or differs from the file). Exit 0 when every requirement is present. A grant at a higher place (a management group) counts.
grant     A dry run: prints what is missing and the exact commands that would make it. With --apply it runs them, with the rights of the person
          who is signed in to the Azure CLI, and checks again. It grants only what the file lists, never changes a custom role that already exists
          (it reports the difference) and refuses to run in GitHub Actions: no pipeline may hold these rights.

The places come from options or from the settings that the workflow uses: --project-subscription (ENV_SUBSCRIPTION_ID) and --project-group
(ENV_RESOURCE_GROUP), where the identities are; --gateway (GATEWAY_RESOURCE_ID), the API Management instance; --gateway-insights
(GATEWAY_APPINSIGHTS_ID); --estate (ACCESS_ESTATE_SCOPES, comma separated; default: the project subscription), what the Watch reads;
--workspace (ACCESS_WORKSPACE_ID; default: the workspace of the gateway's component); --product-subscription (default: from environment/contract.json).
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
CONTRACT = ROOT / "environment" / "contract.json"

GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
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

def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["version"] == 1
        for key in ("identities", "places", "roles", "grants"):
            assert manifest[key]
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
                if role.get("writes"):
                    assert role["definedIn"] == "projectGroup", f"{name}: a role that writes is defined in the project's own group and nowhere else"
    except (OSError, ValueError, KeyError, AssertionError) as e:
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


def markdown(manifest: dict) -> str:
    """The table of the requirements, for the proposal."""
    rows = ["| # | Identity | Role | Where | What it is for |", "|---|---|---|---|---|"]
    for g in manifest["grants"]:
        role = manifest["roles"][g["role"]]
        custom = (" (custom role, changes Azure)" if role.get("writes") else " (custom role)") if role["kind"] == "custom" else ""
        rows.append(f"| {g['id']} | `{manifest['identities'][g['identity']]['name']}` | {g['role']}{custom} | {manifest['places'][g['place']]} | {g['why']} |")
    return "\n".join(rows)


# ---- the places ----------------------------------------------------------------------------------------------------------------------------------

class Places:
    def __init__(self, project_subscription=None, project_group=None, estate=None, gateway=None, gateway_insights=None, workspace=None,
                 product_subscription=None) -> None:
        self.project_subscription, self.project_group, self.estate = project_subscription, project_group, list(estate or [])
        self.gateway, self.gateway_insights, self.workspace, self.product_subscription = gateway, gateway_insights, workspace, product_subscription


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
        gateway=checked(pick("gateway", "GATEWAY_RESOURCE_ID"), APIM, "--gateway", "the resource id of the API Management instance"),
        gateway_insights=checked(pick("gateway_insights", "GATEWAY_APPINSIGHTS_ID"), INSIGHTS, "--gateway-insights",
                                 "the resource id of the gateway's Application Insights component"),
        workspace=checked(pick("workspace", "ACCESS_WORKSPACE_ID"), WORKSPACE, "--workspace", "the resource id of the central Log Analytics workspace"),
        product_subscription=checked(args.product_subscription, SIMPLE_NAME, "--product-subscription", "the name of one subscription of the gateway"),
    )
    for scope in places.estate:
        if not any(p.match(scope) for p in (SUBSCRIPTION, MANAGEMENT_GROUP, RESOURCE_GROUP)):
            raise Problem(f"--estate holds {scope}: a subscription, a management group or a resource group, as a resource id")
    if not places.estate and places.project_subscription:
        places.estate = [f"/subscriptions/{places.project_subscription}"]
    if not places.product_subscription:
        try:
            places.product_subscription = f"{json.loads(CONTRACT.read_text(encoding='utf-8'))['name']}-sub-01"
        except (OSError, ValueError, KeyError):
            places.product_subscription = None
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
    if place == "gatewayProductSubscription":
        gateway = need(places.gateway, "--gateway", "the resource id of the API Management instance")
        return [f"{gateway}/subscriptions/{need(places.product_subscription, '--product-subscription', 'the gateway subscription of the access product')}"]
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
    """One requirement at one scope, and where it stands."""

    def __init__(self, grant: dict, scope: str, state: str, principal: str | None = None, role_id: str | None = None, detail: str = "") -> None:
        self.grant, self.scope, self.state, self.principal, self.role_id, self.detail = grant, scope, state, principal, role_id, detail


def principal_of(az: Az, places: Places, name: str) -> str | None:
    code, out, err = az.run("identity", "show", "--subscription", need(places.project_subscription, "--project-subscription", "the subscription of the project"),
                            "--resource-group", need(places.project_group, "--project-group", "the resource group of the project"), "--name", name,
                            "--query", "principalId", "--output", "tsv")
    if code == 0 and out.strip():
        return out.strip()
    if code != 0 and not re.search(r"ResourceNotFound|could not be found|was not found|not found", err or "", re.I):
        raise Problem(f"the identity {name} could not be read: {first_line(err)}")
    return None


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


def role_state(az: Az, name: str, spec: dict, places: Places) -> tuple[str | None, str, str]:
    """(role id or None, 'ok' | 'role-missing' | 'role-differs', detail)."""
    if spec["kind"] == "builtin":
        return spec["id"], "ok", ""
    group = definition_group(spec["definedIn"], places, az)
    found = az.json("role", "definition", "list", "--subscription", subscription_of(group), "--name", name, "--custom-role-only", "true") or []
    if not found:
        return None, "role-missing", "the custom role does not exist yet; grant makes it first"
    if len(found) > 1:
        raise Problem(f"two custom roles are called {name}")
    problems = definition_problems(found[0], spec, group)
    return found[0]["name"], ("role-differs" if problems else "ok"), "; ".join(problems)


def assignments(az: Az, principal: str, scope: str) -> list[dict]:
    """The principal's assignments at, above and below the scope (the list for a scope with this filter returns all three)."""
    url = f"{ARM}{scope}/providers/Microsoft.Authorization/roleAssignments?api-version={ASSIGNMENTS_API}&$filter=principalId eq '{principal}'"
    found: list[dict] = []
    while url:
        page = az.json("rest", "--method", "get", "--url", url, "--output", "json") or {}
        found += [v for v in page.get("value") or [] if isinstance(v, dict)]
        url = page.get("nextLink")
    return found


def covers(assigned_scope: str, target: str) -> bool:
    """True when an assignment at assigned_scope applies at target: the same place, a place above it, or a management group (which is above any other place)."""
    a, t = assigned_scope.rstrip("/").lower(), target.rstrip("/").lower()
    return a == t or t.startswith(a + "/") or (a.startswith(MANAGEMENT_PREFIX) and not t.startswith(MANAGEMENT_PREFIX))


def examine(az: Az, manifest: dict, places: Places, only: str | None = None) -> list[Item]:
    items: list[Item] = []
    principals: dict[str, str | None] = {}
    roles: dict[str, tuple] = {}
    listed: dict[tuple[str, str], list[dict]] = {}
    for grant in selected(manifest, only):
        identity = manifest["identities"][grant["identity"]]
        if identity["name"] not in principals:
            principals[identity["name"]] = principal_of(az, places, identity["name"])
        principal = principals[identity["name"]]
        for scope in scopes_for(grant["place"], places, az):
            if principal is None:
                items.append(Item(grant, scope, "no-identity", detail=f"{identity['name']} does not exist yet: the Hub action {identity['madeBy']} makes it"))
                continue
            name = grant["role"]
            if name not in roles:
                roles[name] = role_state(az, name, manifest["roles"][name], places)
            role_id, hint, detail = roles[name]
            if hint == "role-missing":
                items.append(Item(grant, scope, "role-missing", principal, None, detail))
                continue
            if hint == "role-differs":
                items.append(Item(grant, scope, "role-differs", principal, role_id, detail))
                continue
            if (principal, scope) not in listed:
                listed[(principal, scope)] = assignments(az, principal, scope)
            held = any(str(a.get("properties", {}).get("roleDefinitionId", "")).rsplit("/", 1)[-1].lower() == role_id.lower()
                       and covers(str(a["properties"].get("scope", "")), scope) for a in listed[(principal, scope)])
            items.append(Item(grant, scope, "present" if held else "missing", principal, role_id))
    return items


def describe(item: Item, manifest: dict) -> str:
    line = f"  {STATES[item.state]:<13}{item.grant['id']}  {manifest['identities'][item.grant['identity']]['name']}  {item.grant['role']}  at {item.scope}"
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


def main(argv=None, az: Az | None = None, env=None, out=print, sleep=time.sleep, ask=None) -> int:
    env = os.environ if env is None else env
    ask = ask or (lambda prompt: input(prompt) if sys.stdin.isatty() else None)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("markdown", help="print the table of the requirements")
    for name, text in (("check", "read only: which requirements are present"), ("grant", "dry run; with --apply, make what is missing")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--only", help="comma separated requirement ids, for example R1,R3")
        sub.add_argument("--project-subscription")
        sub.add_argument("--project-group")
        sub.add_argument("--estate", action="append", help="a subscription, management group or resource group id; repeat for more")
        sub.add_argument("--gateway")
        sub.add_argument("--gateway-insights")
        sub.add_argument("--workspace")
        sub.add_argument("--product-subscription")
        if name == "grant":
            sub.add_argument("--apply", action="store_true", help="make the changes (the default is a dry run)")
            sub.add_argument("--yes", action="store_true", help="do not ask first")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest()
        if args.command == "markdown":
            out(markdown(manifest))
            return 0
        az = az or Az()
        places = read_places(args, env)
        if args.command == "check":
            return command_check(args, az, manifest, places, out)
        return command_grant(args, az, manifest, places, out, sleep, ask, env)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
