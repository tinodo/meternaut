#!/usr/bin/env python3
"""The sign-in of the Meternaut console: one Microsoft Entra app registration that has no secret (standard library only).

    python tools/entra-setup.py check --tenant-id <id> --host <host name of the console> --identity-principal-id <id> [--assign <object id>]...
    python tools/entra-setup.py apply --tenant-id <id> --host <host name of the console> --identity-principal-id <id> [--assign <object id>]... [--apply] [--yes]

The console is a set of web pages of the first cases' function app. A person gets in only after a Microsoft Entra sign-in that the platform does (App
Service authentication), before any page code runs. That sign-in needs an app registration. This one has no client secret and no certificate (AGENTS.md
rule 23): its only credential is a federated identity credential that trusts one user-assigned managed identity of the function app
(https://learn.microsoft.com/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret-preview). Only people
who are assigned to the app can sign in, and the app asks for the one delegated Microsoft Graph permission User.Read.

A person who may make app registrations, assign people to an enterprise application and consent for the whole tenant (an Application Administrator and
a Privileged Role Administrator, or a Global Administrator) runs this tool with their own sign-in to the Azure CLI. It never runs in a pipeline
(AGENTS.md rules 18 and 24): the deployment workflow's identity holds no right in Microsoft Entra and must not get one. The tool makes only the calls of
CALLS below and removes nothing.

check   Read only. For each item: present, MISSING, DIFFERS or why not. Exit 0 when every item is in order, exit 1 otherwise.
apply   A dry run: prints what is there and what it would make. With --apply it makes what is missing, each only once, and checks again. It stops before it
        changes anything when the app holds a secret or a certificate, or is not for this tenant only: a person removes or fixes that.

The items, in order:
  1  The app registration "Meternaut console": this tenant only, one redirect address (https://<host>/.auth/login/aad/callback), ID tokens on (the platform
     signs in with the hybrid flow), the one permission User.Read, and no secret and no certificate.
  2  Its enterprise application (service principal), with "assignment required" on: nobody gets in who is not assigned.
  3  The federated identity credential: issuer https://login.microsoftonline.com/<tenant id>/v2.0, subject the object id of the identity, audience
     api://AzureADTokenExchange.
  4  One assignment for each --assign object id (the people who may sign in).
  5  The consent of the tenant's administrator for User.Read, so that nobody is asked to consent at the first sign-in.

At the end it prints the client id of the app registration: that is the repository variable CONSOLE_APP_CLIENT_ID, which the template reads (a client id is
an identifier, not a secret). The Azure CLI is `az`, or the command in the variable AZ (for example "C:\\path\\python.exe" -IBm azure.cli).
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Mapping

GRAPH = "https://graph.microsoft.com"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
USER_READ = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
APP_NAME = "Meternaut console"
CREDENTIAL_NAME = "meternaut-console-auth"
AUDIENCE = "api://AzureADTokenExchange"
THIS_TENANT_ONLY = "AzureADMyOrg"
NO_ROLE = "00000000-0000-0000-0000-000000000000"
READY_TRIES = 8
READY_SECONDS = 5

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
HOST = re.compile(r"(?=.{4,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
OBJECT = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
# (method, the address after /v1.0/ without its query): everything that this tool may send to Microsoft Graph.
CALLS = (
    ("GET", re.compile(r"applications")), ("POST", re.compile(r"applications")), ("PATCH", re.compile(rf"applications/{OBJECT}")),
    ("GET", re.compile(rf"applications/{OBJECT}/federatedIdentityCredentials")), ("POST", re.compile(rf"applications/{OBJECT}/federatedIdentityCredentials")),
    ("GET", re.compile(r"servicePrincipals")), ("POST", re.compile(r"servicePrincipals")), ("PATCH", re.compile(rf"servicePrincipals/{OBJECT}")),
    ("GET", re.compile(rf"servicePrincipals/{OBJECT}/appRoleAssignedTo")), ("POST", re.compile(rf"servicePrincipals/{OBJECT}/appRoleAssignedTo")),
    ("GET", re.compile(r"oauth2PermissionGrants")), ("POST", re.compile(r"oauth2PermissionGrants")),
)
NOT_READY = re.compile(r"valid application object|does not exist|not found|replicat", re.I)
TOKEN_SHAPES = (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}"), re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"))
HIDDEN = "[token hidden]"
LABELS = {"present": "present", "missing": "MISSING", "differs": "DIFFERS", "unreadable": "UNREADABLE"}

Http = Callable[[str, str, Mapping[str, str], "bytes | None"], "tuple[int, Mapping[str, str], bytes]"]


class Problem(Exception):
    """Something the person who runs the tool can fix or must know; printed without a trace."""


# ---- the Azure CLI and its token -----------------------------------------------------------------------------------------------------------------

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


def first_line(text: str) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0][:300] if lines else "no message"


class Hider:
    """Takes every token that was handed out, and everything that looks like one, out of a text before it is shown."""

    def __init__(self) -> None:
        self.secrets: set[str] = set()

    def add(self, secret: str) -> None:
        if len(secret) >= 8:
            self.secrets.add(secret)

    def __call__(self, text: object) -> str:
        shown = str(text)
        for secret in sorted(self.secrets, key=len, reverse=True):
            shown = shown.replace(secret, HIDDEN)
        for shape in TOKEN_SHAPES:
            shown = shape.sub(HIDDEN, shown)
        return shown


class Tokens:
    """The access token of the signed-in person's Azure CLI for Microsoft Graph in one tenant, asked for once and kept in memory only."""

    def __init__(self, runner: Callable[[list[str]], tuple[int, str, str]], tenant: str, hide: Hider) -> None:
        self.runner, self.tenant, self.hide, self.token = runner, tenant, hide, None

    def __call__(self) -> str:
        if self.token is None:
            code, out, err = self.runner(["account", "get-access-token", "--resource", GRAPH, "--tenant", self.tenant, "--query", "accessToken", "-o", "tsv"])
            token = out.strip()
            if code != 0 or not token:
                raise Problem(f"the Azure CLI gave no token for Microsoft Graph in this tenant: {first_line(err)}")
            self.hide.add(token)
            self.token = token
        return self.token


# ---- Microsoft Graph -----------------------------------------------------------------------------------------------------------------------------

def default_http(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (the address is built from the one host above)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        raise Problem(f"no answer from {urllib.parse.urlsplit(url).netloc} ({type(e).__name__})") from e


def error_of(raw: bytes) -> tuple[str, str]:
    """The code and the message of an error body, the message on one line."""
    text = raw.decode("utf-8", "replace")
    try:
        document = json.loads(text)
    except ValueError:
        return "", " ".join(text.split())
    error = document.get("error") if isinstance(document, dict) else None
    if isinstance(error, dict):
        return str(error.get("code") or ""), " ".join(str(error.get("message") or "").split())
    return "", " ".join(text.split())


def wait_of(headers: Mapping[str, str]) -> float:
    given = next((v for k, v in headers.items() if k.lower() == "retry-after"), "5")
    try:
        return min(60.0, max(1.0, float(given)))
    except ValueError:
        return 5.0


class Failed(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(": ".join(part for part in (f"{status} {code}".strip(), message[:300]) if part))
        self.status, self.code, self.message = status, code, message


class Graph:
    """Calls to Microsoft Graph with the signed-in person's token. Only the calls of CALLS can be sent."""

    def __init__(self, token: Tokens, transport: Http = default_http, sleep: Callable[[float], None] = time.sleep) -> None:
        self.token, self.transport, self.sleep = token, transport, sleep

    def send(self, method: str, path: str, body: dict | None = None) -> dict:
        route = path.split("?", 1)[0]
        if not any(m == method and p.fullmatch(route) for m, p in CALLS):
            raise Problem(f"{method} {route} is not one of the calls that this tool sends")
        headers = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        url = f"{GRAPH}/v1.0/{path}"
        for attempt in (1, 2):
            status, answer, raw = self.transport(method, url, headers, data)
            if status in (429, 503) and attempt == 1:
                self.sleep(wait_of(answer))
                continue
            break
        if 200 <= status < 300:
            if not raw.strip():
                return {}
            try:
                document = json.loads(raw.decode("utf-8"))
            except ValueError as e:
                raise Problem(f"{method} {route}: Microsoft Graph answered with something that is not JSON") from e
            return document if isinstance(document, dict) else {}
        code, message = error_of(raw)
        raise Failed(status, code, message)

    def pages(self, path: str) -> list[dict]:
        found: list[dict] = []
        for _ in range(20):
            document = self.send("GET", path)
            found += [v for v in document.get("value") or [] if isinstance(v, dict)]
            path = document.get("@odata.nextLink") or ""
            if not path:
                return found
            path = path.removeprefix(f"{GRAPH}/v1.0/")
        raise Problem("a list has more than 20 pages")

    def make(self, path: str, body: dict) -> dict:
        """A POST that is tried again for a while when Microsoft Entra does not yet know what an earlier call made."""
        for attempt in range(1, READY_TRIES + 1):
            try:
                return self.send("POST", path, body)
            except Failed as e:
                if attempt < READY_TRIES and (e.status == 404 or (e.status == 400 and NOT_READY.search(e.message))):
                    self.sleep(READY_SECONDS)
                    continue
                raise
        raise AssertionError("unreachable")


# ---- the inputs ----------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    tenant: str
    host: str
    principal_id: str
    people: tuple[str, ...]

    @property
    def callback(self) -> str:
        return f"https://{self.host}/.auth/login/aad/callback"

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/v2.0"


def read_config(args: argparse.Namespace) -> Config:
    tenant = args.tenant_id
    if not tenant or not GUID.fullmatch(tenant):
        raise Problem("--tenant-id is required: the id of the tenant (a GUID)")
    host = (args.host or "").lower()
    if not host or not HOST.fullmatch(host):
        raise Problem("--host is required: the host name of the console, for example func-name.azurewebsites.net")
    principal = args.identity_principal_id
    if not principal or not GUID.fullmatch(principal):
        raise Problem("--identity-principal-id is required: the object (principal) id of the identity of the sign-in (a GUID)")
    people: list[str] = []
    for value in args.assign or []:
        for one in (x.strip() for x in value.split(",") if x.strip()):
            if not GUID.fullmatch(one):
                raise Problem(f"--assign {one} is not an object id (a GUID)")
            if one.lower() not in people:
                people.append(one.lower())
    return Config(tenant.lower(), host, principal.lower(), tuple(people))


# ---- reading what is there -----------------------------------------------------------------------------------------------------------------------

@dataclass
class Item:
    label: str
    state: str
    detail: str = ""
    blocking: bool = False


@dataclass
class State:
    app: dict | None = None
    principal: dict | None = None
    credential: dict | None = None
    assigned: set[str] = field(default_factory=set)
    graph_principal: str | None = None
    consent: bool = False
    app_fixable: list[str] = field(default_factory=list)
    app_blocking: list[str] = field(default_factory=list)


def app_problems(app: dict, cfg: Config) -> tuple[list[str], list[str]]:
    """(what the tool can change, what only a person can change) about an app registration that is there."""
    fixable, blocking = [], []
    if app.get("signInAudience") != THIS_TENANT_ONLY:
        blocking.append(f"it signs in {app.get('signInAudience') or 'nobody'}, and it must be this tenant only ({THIS_TENANT_ONLY})")
    if app.get("passwordCredentials") or app.get("keyCredentials"):
        blocking.append("it holds a secret or a certificate: remove it in the portal, the sign-in has none (AGENTS.md rule 23)")
    web = app.get("web") or {}
    if [u.lower() for u in web.get("redirectUris") or []] != [cfg.callback.lower()]:
        fixable.append(f"the redirect addresses are {', '.join(web.get('redirectUris') or []) or 'none'}, they must be {cfg.callback} only")
    if not (web.get("implicitGrantSettings") or {}).get("enableIdTokenIssuance"):
        fixable.append("ID token issuance is off")
    held = {(str(r.get("resourceAppId", "")).lower(), str(a.get("id", "")).lower(), a.get("type")) for r in app.get("requiredResourceAccess") or []
            for a in r.get("resourceAccess") or []}
    if held != {(GRAPH_APP_ID, USER_READ, "Scope")}:
        fixable.append("it must ask for the delegated permission User.Read of Microsoft Graph and for nothing else")
    return fixable, blocking


def credential_of(graph: Graph, app: dict, cfg: Config) -> dict | None:
    found = graph.pages(f"applications/{app['id']}/federatedIdentityCredentials")
    for credential in found:
        if (credential.get("issuer") == cfg.issuer and str(credential.get("subject", "")).lower() == cfg.principal_id
                and AUDIENCE in (credential.get("audiences") or [])):
            return credential
    return None


def lookup(path: str, field_name: str, value: str, select: str) -> str:
    """A list address that asks for the objects whose field has one value (the query is encoded: a space may not be in an address)."""
    expression = urllib.parse.quote(f"{field_name} eq '{value}'", safe="")
    return f"{path}?$filter={expression}&$select={select}"


def examine(graph: Graph, cfg: Config) -> tuple[list[Item], State]:
    state = State()
    apps = graph.pages(lookup("applications", "displayName", APP_NAME, "id,appId,displayName,signInAudience,web,requiredResourceAccess,passwordCredentials,keyCredentials"))
    if len(apps) > 1:
        raise Problem(f"{len(apps)} app registrations are called {APP_NAME}: remove the ones that are not Meternaut's, then run this again")
    items: list[Item] = []
    state.app = apps[0] if apps else None
    if state.app is None:
        items.append(Item(f"App registration {APP_NAME}", "missing", "this tenant only, no secret, no certificate, one redirect address, ID tokens on, User.Read"))
    else:
        state.app_fixable, state.app_blocking = app_problems(state.app, cfg)
        problems = state.app_blocking + state.app_fixable
        items.append(Item(f"App registration {APP_NAME} (client id {state.app['appId']})", "differs" if problems else "present", "; ".join(problems),
                          blocking=bool(state.app_blocking)))
        found = graph.pages(lookup("servicePrincipals", "appId", state.app["appId"], "id,appId,appRoleAssignmentRequired"))
        state.principal = found[0] if found else None
    if state.principal is None:
        items.append(Item("Enterprise application, assignment required", "missing", "made with the app registration"))
    elif state.principal.get("appRoleAssignmentRequired") is not True:
        items.append(Item("Enterprise application, assignment required", "differs", "assignment is not required: anybody in the tenant could sign in"))
    else:
        items.append(Item("Enterprise application, assignment required", "present"))
    if state.app is not None:
        state.credential = credential_of(graph, state.app, cfg)
    items.append(Item("Federated identity credential for the identity of the sign-in", "present" if state.credential else "missing",
                      "" if state.credential else f"issuer {cfg.issuer}, subject {cfg.principal_id}, audience {AUDIENCE}"))
    if state.principal is not None:
        state.assigned = {str(a.get("principalId", "")).lower() for a in graph.pages(f"servicePrincipals/{state.principal['id']}/appRoleAssignedTo")}
    for person in cfg.people:
        items.append(Item(f"Assignment of {person}", "present" if person in state.assigned else "missing"))
    graph_found = graph.pages(lookup("servicePrincipals", "appId", GRAPH_APP_ID, "id"))
    state.graph_principal = graph_found[0]["id"] if graph_found else None
    if state.principal is not None and state.graph_principal:
        grants = graph.pages(lookup("oauth2PermissionGrants", "clientId", state.principal["id"], "id,consentType,resourceId,scope"))
        state.consent = any(g.get("consentType") == "AllPrincipals" and str(g.get("resourceId", "")).lower() == state.graph_principal.lower()
                            and "User.Read" in str(g.get("scope", "")).split() for g in grants)
    items.append(Item("Consent of the administrator for User.Read", "present" if state.consent else "missing"))
    return items, state


def describe(item: Item) -> str:
    line = f"  {LABELS[item.state]:<11}{item.label}"
    return line + (f"\n             {item.detail}" if item.detail else "")


def report(items: list[Item], state: State, out: Callable[[str], None]) -> bool:
    for item in items:
        out(describe(item))
    done = sum(1 for i in items if i.state == "present")
    out(f"{done} of {len(items)} in order.")
    if state.app:
        out(f"Client id of the app registration (the repository variable CONSOLE_APP_CLIENT_ID): {state.app['appId']}")
    return done == len(items)


# ---- making what is missing ----------------------------------------------------------------------------------------------------------------------

def app_body(cfg: Config) -> dict:
    return {"displayName": APP_NAME, "signInAudience": THIS_TENANT_ONLY,
            "web": {"redirectUris": [cfg.callback], "implicitGrantSettings": {"enableIdTokenIssuance": True, "enableAccessTokenIssuance": False}},
            "requiredResourceAccess": [{"resourceAppId": GRAPH_APP_ID, "resourceAccess": [{"id": USER_READ, "type": "Scope"}]}]}


def app_changes(cfg: Config) -> dict:
    body = app_body(cfg)
    return {key: body[key] for key in ("web", "requiredResourceAccess")}


def plan(items: list[Item], state: State, cfg: Config) -> list[str]:
    steps = []
    if state.app is None:
        steps.append(f"POST applications: make the app registration {APP_NAME} (this tenant only, redirect address {cfg.callback}, ID tokens on, User.Read, no secret)")
    elif state.app_fixable:
        steps.append(f"PATCH applications/{state.app['id']}: " + "; ".join(state.app_fixable))
    if state.principal is None:
        steps.append("POST servicePrincipals: make its enterprise application, assignment required")
    elif state.principal.get("appRoleAssignmentRequired") is not True:
        steps.append(f"PATCH servicePrincipals/{state.principal['id']}: assignment required")
    if state.credential is None:
        steps.append(f"POST applications/<the app>/federatedIdentityCredentials: subject {cfg.principal_id}, issuer {cfg.issuer}, audience {AUDIENCE}")
    steps += [f"POST servicePrincipals/<the enterprise application>/appRoleAssignedTo: {person}" for person in cfg.people if person not in state.assigned]
    if not state.consent:
        steps.append("POST oauth2PermissionGrants: the administrator's consent for User.Read, for all users")
    return steps


def apply_steps(graph: Graph, cfg: Config, state: State, out: Callable[[str], None]) -> None:
    app = state.app
    if app is None:
        app = graph.make("applications", app_body(cfg))
        out(f"  made the app registration {APP_NAME} (client id {app['appId']})")
    elif state.app_fixable:
        graph.send("PATCH", f"applications/{app['id']}", app_changes(cfg))
        out(f"  changed the app registration: {'; '.join(state.app_fixable)}")
    principal = state.principal
    if principal is None:
        principal = graph.make("servicePrincipals", {"appId": app["appId"], "appRoleAssignmentRequired": True})
        out("  made the enterprise application, assignment required")
    elif principal.get("appRoleAssignmentRequired") is not True:
        graph.send("PATCH", f"servicePrincipals/{principal['id']}", {"appRoleAssignmentRequired": True})
        out("  switched assignment required on")
    if state.credential is None:
        graph.make(f"applications/{app['id']}/federatedIdentityCredentials",
                   {"name": CREDENTIAL_NAME, "issuer": cfg.issuer, "subject": cfg.principal_id, "audiences": [AUDIENCE],
                    "description": "Lets the user-assigned identity of the console's function app sign in as this app, with no secret."})
        out("  made the federated identity credential")
    for person in cfg.people:
        if person not in state.assigned:
            graph.make(f"servicePrincipals/{principal['id']}/appRoleAssignedTo", {"principalId": person, "resourceId": principal["id"], "appRoleId": NO_ROLE})
            out(f"  assigned {person}")
    if not state.consent:
        if not state.graph_principal:
            raise Problem("the enterprise application of Microsoft Graph is not in this tenant")
        graph.make("oauth2PermissionGrants", {"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": state.graph_principal, "scope": "User.Read"})
        out("  gave the administrator's consent for User.Read")


# ---- the commands --------------------------------------------------------------------------------------------------------------------------------

def command_check(graph: Graph, cfg: Config, out: Callable[[str], None]) -> int:
    out(f"The sign-in of the Meternaut console, in tenant {cfg.tenant}:")
    items, state = examine(graph, cfg)
    return 0 if report(items, state, out) else 1


def command_apply(args: argparse.Namespace, graph: Graph, cfg: Config, out: Callable[[str], None], ask: Callable[[str], "str | None"], env: Mapping[str, str]) -> int:
    if args.apply and env.get("GITHUB_ACTIONS") == "true":
        raise Problem("a person who may administer Microsoft Entra runs this, never a pipeline: the workflow's identity must not hold that right (AGENTS.md rules 18 and 24)")
    out(f"The sign-in of the Meternaut console, in tenant {cfg.tenant}:")
    items, state = examine(graph, cfg)
    for item in items:
        out(describe(item))
    if any(i.blocking for i in items):
        out("Nothing can be changed until the lines above that say DIFFERS with a secret, a certificate or another audience are settled by a person.")
        return 1
    steps = plan(items, state, cfg)
    if not steps:
        out("Nothing to make.")
        if state.app:
            out(f"Client id of the app registration (the repository variable CONSOLE_APP_CLIENT_ID): {state.app['appId']}")
        return 0
    out(f"{len(steps)} change(s) would be made, and nothing else:")
    for step in steps:
        out(f"  {step}")
    if not args.apply:
        out("This was a dry run. Run again with --apply to make them.")
        return 1
    if not args.yes:
        answer = ask(f"Make these {len(steps)} change(s) in tenant {cfg.tenant}? Type yes: ")
        if answer is None:
            raise Problem("--apply needs --yes when there is no terminal to ask in")
        if answer.strip().lower() != "yes":
            raise Problem("nothing was changed")
    apply_steps(graph, cfg, state, out)
    out("Checking again:")
    items, state = examine(graph, cfg)
    return 0 if report(items, state, out) else 1


def main(argv: list[str] | None = None, runner: Callable[[list[str]], tuple[int, str, str]] = run_az, transport: Http = default_http,
         sleep: Callable[[float], None] = time.sleep, out: Callable[[str], None] = print, ask: Callable[[str], "str | None"] | None = None,
         env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    ask = ask or (lambda prompt: input(prompt) if sys.stdin.isatty() else None)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "read only: which items are in order"), ("apply", "dry run; with --apply, make what is missing")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--tenant-id")
        sub.add_argument("--host", help="the host name of the console, for example func-name.azurewebsites.net")
        sub.add_argument("--identity-principal-id", help="the object id of the user-assigned identity that signs in as the app")
        sub.add_argument("--assign", action="append", help="the object id of a person who may sign in; repeat it or separate with commas")
        if name == "apply":
            sub.add_argument("--apply", action="store_true", help="make the changes (the default is a dry run)")
            sub.add_argument("--yes", action="store_true", help="do not ask first")
    args = parser.parse_args(argv)
    hide = Hider()
    try:
        cfg = read_config(args)
        graph = Graph(Tokens(runner, cfg.tenant, hide), transport, sleep)
        if args.command == "check":
            return command_check(graph, cfg, out)
        return command_apply(args, graph, cfg, out, ask, env)
    except Failed as e:
        print(hide(f"error: Microsoft Graph refused: {e}"), file=sys.stderr)
        return 1
    except Problem as e:
        print(hide(f"error: {e}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
