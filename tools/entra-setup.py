#!/usr/bin/env python3
"""The sign-in of the Meternaut function app, and the sign-in of the person who approves a change: one Microsoft Entra app registration that has no secret (standard library only).

    python tools/entra-setup.py check --tenant-id <id> --host <host name of the function app> --identity-principal-id <id> [--assign <object id>]...
    python tools/entra-setup.py apply --tenant-id <id> --host <host name of the function app> --identity-principal-id <id> [--assign <object id>]... [--apply] [--yes]

The function app of the first cases serves a set of web pages. A person gets in only after a Microsoft Entra sign-in that the platform does (App
Service authentication), before any page code runs. That sign-in needs an app registration. This one has no client secret and no certificate (AGENTS.md
rule 23): its only credential is a federated identity credential that trusts one user-assigned managed identity of the function app
(https://learn.microsoft.com/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret-preview). Only people
who are assigned to the app can sign in.

The same app registration carries a second sign-in. Meternaut holds no right to change Azure. When a person approves a plan, the function app sends the person
to Microsoft Entra to sign in to Azure Resource Manager (OAuth 2.0 authorization code flow with PKCE, the delegated scope
https://management.azure.com/user_impersonation and the OpenID Connect scopes openid and profile, no refresh token), redeems the code with the same
federated credential (the identity presents a token for api://AzureADTokenExchange as the client assertion) and makes the one change with that person's
own token, so that Azure checks the person's own rights. The app registration is a confidential client: public client flows are off
(isFallbackPublicClient is false), so a code is worth nothing without that credential. For the sign-ins the app asks for two delegated permissions:
User.Read of Microsoft Graph, and user_impersonation of Azure Service Management (resource application id 797f4846-ba00-4fd7-ba43-dac1f8f63013, permission
id 41094075-9dad-400e-a0bd-54e686782033). The OpenID Connect scopes need no permission of their own: the consent that the platform's own sign-in already uses
(User.Read) covers them. The tenant's administrator consents to both permissions for all users, once. That gives Meternaut no right of its own: it can act
only as a signed-in person. The return address of the second sign-in is https://<host>/arm/return, next to the platform's own
https://<host>/.auth/login/aad/callback.

<host> is the name that people open. While the function app takes public traffic it is the app's own name, <app>.azurewebsites.net. Once the app is closed and
the platform's Application Gateway forwards to it, it is the function app's host name on that gateway (the secret CONSOLE_HOST_NAME of the environment hub): both return
addresses name that host, because the sign-in sends a person back to the host that the person came on (docs/proposals/07-private-by-default.md). Run the tool
again with the new host before the variable is set. It only adds the addresses of the new host: the addresses of the app's own name stay, shown as a note,
until a person removes them in the portal.

A person who may make app registrations, assign people to an enterprise application and consent for the whole tenant (an Application Administrator and
a Privileged Role Administrator, or a Global Administrator) runs this tool with their own sign-in to the Azure CLI. It never runs in a pipeline
(AGENTS.md rules 18 and 24): the deployment workflow's identity holds no right in Microsoft Entra and must not get one. The tool makes only the calls of
CALLS below and removes nothing. That holds for the lists of the app registration too: a redirect address or a permission that somebody else added stays.
The tool reads the lists, sends back everything that is there together with what is missing, reads the app registration again just before it writes, and
shows what it leaves alone as a note. A person who may not consent for the whole tenant still gets everything else made: the tool says so in plain words
and prints the address that a tenant administrator opens to give the consent, https://login.microsoftonline.com/<tenant id>/adminconsent?client_id=<client id>.

check   Read only. For each item: present, MISSING, DIFFERS or why not. Exit 0 when every item is in order, exit 1 otherwise.
apply   A dry run: prints what is there and what it would make. With --apply it makes what is missing, each only once, and checks again. It adds and never
        removes anything that is there. The one thing that it turns off is public client flows, and only when they are on. It stops before it changes
        anything when the app holds a secret or a certificate, or is not for this tenant only: a person removes or fixes that.

The name. The app registration and its enterprise application are called "Meternaut": that is the name on the Microsoft sign-in screen ("Sign in to
Meternaut") and in the Microsoft Entra admin center. Until 2026-11-13 they were called "Meternaut console". The tool finds the app registration under either
name (two that it cannot tell apart stop it), and a new one is made as "Meternaut". When the one that is there has the old name, the dry run says "would
rename 'Meternaut console' to 'Meternaut'". With --apply the tool sends the display name alone (no redirect address, no credential, no permission), reads it
back, reads the enterprise application, and renames that too when its name did not follow. A second run changes nothing and says so.

The items, in order:
  1  The app registration "Meternaut": this tenant only, ID tokens on (the platform signs in with the hybrid flow), the redirect address
     https://<host>/.auth/login/aad/callback, the permission User.Read, and no secret and no certificate. A redirect address or a permission that is
     there besides the ones of this tool is not a difference: it is shown as a note under the line and left alone. An app registration that is still
     called "Meternaut console" differs in its name alone: apply renames it.
  2  The redirect address https://<host>/arm/return, where the sign-in of the person who approves returns to the function app.
  3  The delegated permission user_impersonation of Azure Service Management, asked for by the app.
  4  Public client flows off: isFallbackPublicClient of the app registration is false or not set, so that the app is a confidential client and a sign-in
     code can be redeemed only with the credential of the app. When it is true, apply sets it to false and sends nothing else of the app with it.
  5  Its enterprise application (service principal), called "Meternaut" like the app registration, with "assignment required" on: nobody gets in who is
     not assigned.
  6  The federated identity credential: issuer https://login.microsoftonline.com/<tenant id>/v2.0, subject the object id of the identity, audience
     api://AzureADTokenExchange.
  7  One assignment for each --assign object id (the people who may sign in).
  8  The consent of the tenant's administrator for User.Read, so that nobody is asked to consent at the first sign-in.
  9  The same consent for user_impersonation of Azure Service Management.

At the end it prints the client id of the app registration: that is the secret CONSOLE_APP_CLIENT_ID of the environment hub, which the template reads (a client id is
an identifier, not a credential; it is a secret there so that GitHub masks it in the public log). The Azure CLI is `az`, or the command in the variable AZ (for example "C:\\path\\python.exe" -IBm azure.cli).

The Teams cards (docs/proposals/13-teams-and-outlook.md) go through a private queue and a flow of Power Automate and need nothing in Microsoft Entra: replaced by the owner's ruling of 2026-11-13 (pending his
plain yes) for the other way to deliver them (docs/proposals/20-teams-cards-through-a-bot.md), which is off until he switches it on, and for which the sub-command teams-bot below is the one thing that this tool makes besides
the sign-in of the function app.

    python tools/entra-setup.py teams-bot --tenant-id <id> --subscription <id> --resource-group <name> [--apply] [--yes]

teams-bot  The app registration of the Teams bot: "Meternaut Teams", this tenant only, with no secret, no certificate, no API permission, no redirect address and no consent, its service principal in
           the tenant (without one Teams reports AADSTS7000229, "missing service principal in the tenant"), and ONE federated identity credential: issuer https://login.microsoftonline.com/<tenant id>/v2.0, subject
           the object (principal) id of the user-assigned identity id-meternaut-teams, which the Hub action teams made and which the tool reads with the signed-in person's own rights, audience
           api://AzureADTokenExchange. The identity and the app registration have to be in the same tenant. A wrong subject or audience is accepted when the credential is made and fails only at the first
           token exchange, so the proof is the Hub action teams-test. It is a HAND STEP of the owner's, a dry run unless --apply is given, and it refuses to run in a pipeline, even as a dry run: its output
           names the client id of the app registration, which goes to the terminal of the person alone. It makes only what is missing, so a second run changes nothing and says so, it never makes a secret or a
           certificate, it removes nothing (a stray credential, address or permission is shown and a person removes it in the portal), and after it has made anything it reads everything back: no password, no key,
           exactly one federated credential with the right values. It prints the client id and the command that stores it as the secret TEAMS_BOT_APP_ID of the environment hub.
"""
from __future__ import annotations

import argparse
import copy
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
ARM_APP_ID = "797f4846-ba00-4fd7-ba43-dac1f8f63013"
USER_IMPERSONATION = "41094075-9dad-400e-a0bd-54e686782033"
ARM_SCOPE = "user_impersonation"
ARM_PERMISSION_NAME = "user_impersonation of Azure Service Management"
# What the app registration asks for: the delegated permissions of the function app's sign-in and of the approver's sign-in to Azure Resource Manager.
WANTED_ACCESS = (
    {"resourceAppId": GRAPH_APP_ID, "resourceAccess": [{"id": USER_READ, "type": "Scope"}]},
    {"resourceAppId": ARM_APP_ID, "resourceAccess": [{"id": USER_IMPERSONATION, "type": "Scope"}]},
)
WANTED_PERMISSIONS = {(r["resourceAppId"], a["id"], a["type"]) for r in WANTED_ACCESS for a in r["resourceAccess"]}
APP_SELECT = "id,appId,displayName,signInAudience,isFallbackPublicClient,web,requiredResourceAccess,passwordCredentials,keyCredentials"
PRINCIPAL_SELECT = "id,appId,displayName,appRoleAssignmentRequired"
# The name of the app registration and of its enterprise application: the name on the Microsoft sign-in screen. The tool finds an app registration that still has the name that it had
# until 2026-11-13 and renames it; nothing new is made with that name.
APP_NAME = "Meternaut"
FORMER_APP_NAME = "Meternaut console"
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
    def arm_return(self) -> str:
        return f"https://{self.host}/arm/return"

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/v2.0"


def consent_address(tenant: str, client_id: str) -> str:
    """The address at which a tenant administrator gives the consent for what the app registration asks for (https://learn.microsoft.com/entra/identity/enterprise-apps/grant-admin-consent)."""
    return f"https://login.microsoftonline.com/{tenant}/adminconsent?client_id={client_id}"


def parse_people(values: list[str] | None) -> list[str]:
    """The object ids of --assign: each given twice or separated with commas, in lower case, each once."""
    people: list[str] = []
    for value in values or []:
        for one in (x.strip() for x in value.split(",") if x.strip()):
            if not GUID.fullmatch(one):
                raise Problem(f"--assign {one} is not an object id (a GUID)")
            if one.lower() not in people:
                people.append(one.lower())
    return people


def read_config(args: argparse.Namespace) -> Config:
    tenant = args.tenant_id
    if not tenant or not GUID.fullmatch(tenant):
        raise Problem("--tenant-id is required: the id of the tenant (a GUID)")
    host = (args.host or "").lower()
    if not host or not HOST.fullmatch(host):
        raise Problem("--host is required: the host name that people open, the function app's host name on the platform's Application Gateway or the function app's own name (for example func-name.azurewebsites.net)")
    principal = args.identity_principal_id
    if not principal or not GUID.fullmatch(principal):
        raise Problem("--identity-principal-id is required: the object (principal) id of the identity of the sign-in (a GUID)")
    return Config(tenant.lower(), host, principal.lower(), tuple(parse_people(args.assign)))


# ---- reading what is there -----------------------------------------------------------------------------------------------------------------------

@dataclass
class Item:
    label: str
    state: str
    detail: str = ""
    blocking: bool = False
    consent: bool = False
    notes: list[str] = field(default_factory=list)  # what is there besides, and left alone: shown under the line, never a difference


def plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


@dataclass
class Review:
    """What an app registration that is there lacks, and what is there besides."""
    blocking: list[str] = field(default_factory=list)  # only a person can change it
    callback: bool = True  # the redirect address of the platform's sign-in is there
    arm_return: bool = True  # the redirect address of the sign-in to Azure Resource Manager is there (it has a line of its own)
    id_token: bool = True  # ID token issuance is on
    user_read: bool = True  # the delegated permission User.Read of Microsoft Graph is asked for
    impersonation: bool = True  # the delegated permission user_impersonation of Azure Service Management is asked for (it has a line of its own)
    confidential: bool = True  # public client flows are off: isFallbackPublicClient is false or not set (it has a line of its own)
    other_addresses: list[str] = field(default_factory=list)  # redirect addresses that are not the function app's: left alone
    other_permissions: list[tuple] = field(default_factory=list)  # (resource application id, permission id, type) that this tool does not ask for: left alone

    def shown(self, cfg: Config) -> list[str]:
        """What is told on the line of the app registration: what lacks and has no line of its own."""
        lacking = []
        if not self.callback:
            lacking.append(f"the redirect address {cfg.callback} of the platform's sign-in is missing")
        if not self.id_token:
            lacking.append("ID token issuance is off")
        if not self.user_read:
            lacking.append("it does not ask for the delegated permission User.Read of Microsoft Graph")
        return lacking

    def lacking(self, cfg: Config) -> list[str]:
        """What the redirect addresses, the ID token setting and the permissions lack: one change adds it and sends back what is there."""
        more = []
        if not self.arm_return:
            more.append(f"the redirect address {cfg.arm_return} of the sign-in to Azure Resource Manager is missing")
        if not self.impersonation:
            more.append(f"it does not ask for the delegated permission {ARM_PERMISSION_NAME}")
        return self.shown(cfg) + more

    def fixable(self, cfg: Config) -> list[str]:
        """Everything that the one change of the app registration adds, switches on or switches off."""
        return self.lacking(cfg) + ([] if self.confidential else ["public client flows are on (isFallbackPublicClient is true)"])

    @property
    def web_missing(self) -> bool:
        return not (self.callback and self.arm_return and self.id_token)

    @property
    def access_missing(self) -> bool:
        return not (self.user_read and self.impersonation)

    @property
    def notes(self) -> list[str]:
        notes = []
        if self.other_addresses:
            notes.append(f"also there, and left alone because this tool removes nothing: {plural(len(self.other_addresses), 'redirect address', 'redirect addresses')} "
                         f"{', '.join(self.other_addresses)}. A person removes what nobody meant, in the portal")
        if self.other_permissions:
            named = ", ".join(f"{permission} ({kind}) of resource application {resource}" for resource, permission, kind in self.other_permissions)
            notes.append(f"also there, and left alone because this tool removes nothing: {plural(len(self.other_permissions), 'permission', 'permissions')} {named}. "
                         "A person removes what nobody meant, in the portal")
        return notes


@dataclass
class State:
    app: dict | None = None
    review: Review = field(default_factory=Review)
    old_name: str = ""  # the name that the app registration has now, when it is not the one it is to have
    principal: dict | None = None
    credential: dict | None = None
    assigned: set[str] = field(default_factory=set)
    graph_principal: str | None = None
    arm_principal: str | None = None
    consent: bool = False
    arm_consent: bool = False


def permissions_of(app: dict) -> set[tuple]:
    """(resource application id, permission id, type) of everything that the app registration asks for; the ids in lower case."""
    return {(str(r.get("resourceAppId", "")).lower(), str(a.get("id", "")).lower(), a.get("type")) for r in app.get("requiredResourceAccess") or []
            for a in r.get("resourceAccess") or []}


def review_app(app: dict, cfg: Config) -> Review:
    review = Review()
    if app.get("signInAudience") != THIS_TENANT_ONLY:
        review.blocking.append(f"it signs in {app.get('signInAudience') or 'nobody'}, and it must be this tenant only ({THIS_TENANT_ONLY})")
    if app.get("passwordCredentials") or app.get("keyCredentials"):
        review.blocking.append("it holds a secret or a certificate: remove it in the portal, the sign-in has none (AGENTS.md rule 23)")
    web = app.get("web") or {}
    addresses = [str(u) for u in web.get("redirectUris") or []]
    given = {u.lower() for u in addresses}
    review.callback = cfg.callback.lower() in given
    review.arm_return = cfg.arm_return.lower() in given
    review.other_addresses = [u for u in addresses if u.lower() not in (cfg.callback.lower(), cfg.arm_return.lower())]
    review.id_token = bool((web.get("implicitGrantSettings") or {}).get("enableIdTokenIssuance"))
    held = permissions_of(app)
    review.user_read = (GRAPH_APP_ID, USER_READ, "Scope") in held
    review.impersonation = (ARM_APP_ID, USER_IMPERSONATION, "Scope") in held
    # Only false or not set is off: any other value is treated as on, so that a value that this tool does not expect is not taken for a safe one.
    public_flows = app.get("isFallbackPublicClient")
    review.confidential = public_flows is None or public_flows is False
    review.other_permissions = sorted(held - WANTED_PERMISSIONS, key=str)
    return review


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


def consented(grants: list[dict], resource_id: str | None, scope: str) -> bool:
    """True when one grant gives the consent of the administrator, for all users, for the scope of that resource's enterprise application."""
    return bool(resource_id) and any(g.get("consentType") == "AllPrincipals" and str(g.get("resourceId", "")).lower() == resource_id.lower()
                                     and scope in str(g.get("scope", "")).split() for g in grants)


def other_name(thing: dict) -> str:
    """The name that an app registration or an enterprise application has now, when it is not the name that it is to have; empty when it is."""
    name = thing.get("displayName")
    return "" if name == APP_NAME else (str(name) if name else "(none)")


def renaming(old: str) -> str:
    return f"it is called '{old}' and is to be called '{APP_NAME}': apply renames it (the display name alone is sent)"


def read_app(graph: Graph) -> dict | None:
    """The one app registration that is Meternaut's sign-in: found under its name, or under the name that it had until 2026-11-13 (apply renames it). Two that have
    one name, or one of each name, stop the tool: it cannot tell which one is Meternaut's."""
    found: list[dict] = []
    for name in (APP_NAME, FORMER_APP_NAME):
        apps = graph.pages(lookup("applications", "displayName", name, APP_SELECT))
        if len(apps) > 1:
            raise Problem(f"{len(apps)} app registrations are called {name}: remove the ones that are not Meternaut's, then run this again")
        found += apps
    if len(found) > 1:
        raise Problem(f"one app registration is called {APP_NAME} and another {FORMER_APP_NAME}: the tool cannot tell which one is Meternaut's sign-in. "
                      "Remove the one that is not, then run this again")
    return found[0] if found else None


def read_named_app(graph: Graph, name: str, select: str) -> dict | None:
    """The one app registration of that name, or None (the Teams bot's). Two of them stop the tool: it cannot tell which one is Meternaut's."""
    apps = graph.pages(lookup("applications", "displayName", name, select))
    if len(apps) > 1:
        raise Problem(f"{len(apps)} app registrations are called {name}: remove the ones that are not Meternaut's, then run this again")
    return apps[0] if apps else None


def examine(graph: Graph, cfg: Config) -> tuple[list[Item], State]:
    state = State()
    items: list[Item] = []
    state.app = read_app(graph)
    return_label = f"Redirect address {cfg.arm_return}, where the sign-in to Azure Resource Manager of the person who approves returns to the function app"
    permission_label = f"Delegated permission {ARM_PERMISSION_NAME}, asked for by the app"
    public_label = "Public client flows off (isFallbackPublicClient false), so that a sign-in code is redeemed only with the credential of the app"
    if state.app is None:
        items.append(Item(f"App registration {APP_NAME}", "missing", "this tenant only, no secret, no certificate, the redirect address of the platform's sign-in, ID tokens on, User.Read"))
        items.append(Item(return_label, "missing", "made with the app registration"))
        items.append(Item(permission_label, "missing", "made with the app registration"))
        items.append(Item(public_label, "missing", "made with the app registration, as a confidential client"))
    else:
        state.review = review_app(state.app, cfg)
        state.old_name = other_name(state.app)
        problems = state.review.blocking + ([renaming(state.old_name)] if state.old_name else []) + state.review.shown(cfg)
        items.append(Item(f"App registration {APP_NAME} (client id {state.app['appId']})", "differs" if problems else "present", "; ".join(problems),
                          blocking=bool(state.review.blocking), notes=state.review.notes))
        items.append(Item(return_label, "present" if state.review.arm_return else "missing"))
        items.append(Item(permission_label, "present" if state.review.impersonation else "missing"))
        items.append(Item(public_label, "present" if state.review.confidential else "missing",
                          "" if state.review.confidential else "the app registration allows public client flows (isFallbackPublicClient is true), so a sign-in code could be "
                                                               "redeemed without a credential: apply switches it off"))
        found = graph.pages(lookup("servicePrincipals", "appId", state.app["appId"], PRINCIPAL_SELECT))
        state.principal = found[0] if found else None
    principal_label = f"Enterprise application {APP_NAME}, assignment required"
    if state.principal is None:
        items.append(Item(principal_label, "missing", "made with the app registration"))
    else:
        principal_problems = []
        if state.principal.get("appRoleAssignmentRequired") is not True:
            principal_problems.append("assignment is not required: anybody in the tenant could sign in")
        if other_name(state.principal):
            principal_problems.append(renaming(other_name(state.principal)))
        items.append(Item(principal_label, "differs" if principal_problems else "present", "; ".join(principal_problems)))
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
    arm_found = graph.pages(lookup("servicePrincipals", "appId", ARM_APP_ID, "id"))
    state.arm_principal = arm_found[0]["id"] if arm_found else None
    if state.principal is not None:
        grants = graph.pages(lookup("oauth2PermissionGrants", "clientId", state.principal["id"], "id,consentType,resourceId,scope"))
        state.consent = consented(grants, state.graph_principal, "User.Read")
        state.arm_consent = consented(grants, state.arm_principal, ARM_SCOPE)
    address = f"a tenant administrator can give it at {consent_address(cfg.tenant, state.app['appId'])}" if state.app else ""
    items.append(Item("Consent of the administrator for User.Read", "present" if state.consent else "missing", "" if state.consent else address, consent=True))
    if state.arm_consent:
        arm_detail = ""
    elif state.arm_principal is None and state.app:
        arm_detail = f"the enterprise application of Azure Service Management is not in this tenant yet: a tenant administrator makes it and gives the consent at {consent_address(cfg.tenant, state.app['appId'])}"
    else:
        arm_detail = address
    items.append(Item(f"Consent of the administrator for {ARM_PERMISSION_NAME}", "present" if state.arm_consent else "missing", arm_detail, consent=True))
    return items, state


def describe(item: Item) -> str:
    lines = [f"  {LABELS[item.state]:<11}{item.label}"]
    lines += [f"             {text}" for text in ([item.detail] if item.detail else []) + item.notes]
    return "\n".join(lines)


def guidance(items: list[Item], state: State, cfg: Config) -> list[str]:
    """What a tenant administrator does when a consent is not in place: open the address that gives it."""
    if state.app is None or all(i.state == "present" for i in items if i.consent):
        return []
    return [f"A tenant administrator gives the missing consent once, for the whole tenant, by opening {consent_address(cfg.tenant, state.app['appId'])}, signing in and accepting. "
            "The consent lets the function app send the person who approves to sign in to Azure Resource Manager: the change is made with that person's own rights, "
            "and Meternaut gets no right of its own. Run check again afterwards."]


def report(items: list[Item], state: State, cfg: Config, out: Callable[[str], None]) -> bool:
    for item in items:
        out(describe(item))
    done = sum(1 for i in items if i.state == "present")
    out(f"{done} of {len(items)} in order.")
    if state.app:
        out(f"Client id of the app registration (a secret of the environment hub, CONSOLE_APP_CLIENT_ID): {state.app['appId']}")
    for line in guidance(items, state, cfg):
        out(line)
    return done == len(items)


# ---- making what is missing ----------------------------------------------------------------------------------------------------------------------

def app_body(cfg: Config) -> dict:
    """The app registration as it is made when it is not there yet: a confidential client."""
    return {"displayName": APP_NAME, "signInAudience": THIS_TENANT_ONLY, "isFallbackPublicClient": False,
            "web": {"redirectUris": [cfg.callback, cfg.arm_return], "implicitGrantSettings": {"enableIdTokenIssuance": True, "enableAccessTokenIssuance": False}},
            "requiredResourceAccess": copy.deepcopy(list(WANTED_ACCESS))}


def union_addresses(there: list[str], wanted: list[str]) -> list[str]:
    """Every address that is there, in its order, and then each wanted address that is not (addresses are compared without regard to case)."""
    have = {u.lower() for u in there}
    return [*there, *[u for u in wanted if u.lower() not in have]]


def union_access(there: list[dict], wanted) -> list[dict]:
    """Per resource application id, every permission that is there, in its order, and then each wanted one that is not (compared by id and type).
    Nothing that is there is dropped, and what is passed in is not changed."""
    merged: dict[str, dict] = {}
    for resource in [*there, *wanted]:
        entry = merged.setdefault(str(resource.get("resourceAppId", "")).lower(), {**copy.deepcopy(resource), "resourceAccess": []})
        have = {(str(a.get("id", "")).lower(), a.get("type")) for a in entry["resourceAccess"]}
        for access in resource.get("resourceAccess") or []:
            key = (str(access.get("id", "")).lower(), access.get("type"))
            if key not in have:
                entry["resourceAccess"].append(copy.deepcopy(access))
                have.add(key)
    return list(merged.values())


def app_changes(app: dict, cfg: Config) -> dict:
    """What one PATCH of an app registration that is there sends: for each of the two lists that lacks something, everything that is there and what is
    missing, and nothing for a list that lacks nothing; and isFallbackPublicClient false, only when it is true. Nothing is removed and nothing else is sent."""
    review = review_app(app, cfg)
    changes: dict = {}
    if review.web_missing:
        web = app.get("web") or {}
        # A PATCH of `web` may be handled as a replacement of the whole property, so what this tool does not manage in it goes back as it was read.
        kept = {key: web[key] for key in ("homePageUrl", "logoutUrl") if web.get(key)}
        implicit = {key: value for key, value in (web.get("implicitGrantSettings") or {}).items() if value is not None}
        changes["web"] = {**kept, "redirectUris": union_addresses([str(u) for u in web.get("redirectUris") or []], [cfg.callback, cfg.arm_return]),
                          "implicitGrantSettings": {**implicit, "enableIdTokenIssuance": True}}
    if review.access_missing:
        changes["requiredResourceAccess"] = union_access(app.get("requiredResourceAccess") or [], WANTED_ACCESS)
    if not review.confidential:
        changes["isFallbackPublicClient"] = False
    return changes


def left_alone(review: Review) -> str:
    kept = []
    if review.other_addresses:
        kept.append(f"{len(review.other_addresses)} other redirect {plural(len(review.other_addresses), 'address', 'addresses')}")
    if review.other_permissions:
        kept.append(f"{len(review.other_permissions)} other {plural(len(review.other_permissions), 'permission', 'permissions')}")
    return f". Left as they were: {', '.join(kept)}" if kept else ""


def plan(items: list[Item], state: State, cfg: Config) -> list[str]:
    steps = []
    if state.app is None:
        steps.append(f"POST applications: make the app registration {APP_NAME} (this tenant only, redirect addresses {cfg.callback} and {cfg.arm_return}, ID tokens on, "
                     f"User.Read and {ARM_PERMISSION_NAME}, no secret, public client flows off)")
    else:
        if state.old_name:
            then = (f". The enterprise application is read again afterwards, and when its name has not followed it is renamed too (PATCH servicePrincipals/{state.principal['id']}, "
                    "the display name alone)" if state.principal is not None else "")
            steps.append(f"PATCH applications/{state.app['id']}: would rename '{state.old_name}' to '{APP_NAME}'. Only the display name is sent: no redirect address, "
                         f"no credential and no permission{then}")
        if state.review.fixable(cfg):
            lists = state.review.web_missing or state.review.access_missing
            steps.append(f"PATCH applications/{state.app['id']}: " + "; ".join(state.review.fixable(cfg))
                         + (". Every redirect address and permission that is there is sent back with it: nothing is removed" if lists
                            else ". Public client flows are switched off and nothing else of the app is sent"))
    if state.principal is None:
        steps.append("POST servicePrincipals: make its enterprise application, assignment required")
    else:
        if state.principal.get("appRoleAssignmentRequired") is not True:
            steps.append(f"PATCH servicePrincipals/{state.principal['id']}: assignment required")
        if other_name(state.principal) and not state.old_name:
            steps.append(f"PATCH servicePrincipals/{state.principal['id']}: would rename '{other_name(state.principal)}' to '{APP_NAME}'. Only the display name is sent")
    if state.credential is None:
        steps.append(f"POST applications/<the app>/federatedIdentityCredentials: subject {cfg.principal_id}, issuer {cfg.issuer}, audience {AUDIENCE}")
    steps += [f"POST servicePrincipals/<the enterprise application>/appRoleAssignedTo: {person}" for person in cfg.people if person not in state.assigned]
    if not state.consent:
        steps.append("POST oauth2PermissionGrants: the administrator's consent for User.Read, for all users")
    if not state.arm_consent and state.arm_principal:
        steps.append(f"POST oauth2PermissionGrants: the administrator's consent for {ARM_PERMISSION_NAME}, for all users "
                     "(a person who may not give it is told so, and gets the address that a tenant administrator opens)")
    return steps


def give_consent(graph: Graph, client_id: str, resource_id: str, scope: str, name: str, out: Callable[[str], None]) -> None:
    """The consent of the administrator for one delegated permission, for all users. A person who may not give it is told so in plain words, and the rest goes on."""
    try:
        graph.make("oauth2PermissionGrants", {"clientId": client_id, "consentType": "AllPrincipals", "resourceId": resource_id, "scope": scope})
    except Failed as e:
        if e.status != 403:
            raise
        code = re.sub(r"[^A-Za-z0-9_.-]", "", e.code)[:60]
        out(f"  could not give the administrator's consent for {name}: the signed-in person may not give consent for the whole tenant "
            f"(Microsoft Graph answered {e.status} {code}). A tenant administrator gives it, at the address below.")
        return
    out(f"  gave the administrator's consent for {name}")


def rename_app(graph: Graph, app: dict, old: str, out: Callable[[str], None]) -> None:
    """The display name of the app registration, alone, in one change; then read back until Microsoft Entra shows it (a write may take a moment to be seen)."""
    graph.send("PATCH", f"applications/{app['id']}", {"displayName": APP_NAME})
    shown = ""
    for attempt in range(1, READY_TRIES + 1):
        found = graph.pages(lookup("applications", "appId", app["appId"], "id,appId,displayName"))
        shown = str(found[0].get("displayName", "")) if found else ""
        if shown == APP_NAME:
            out(f"  renamed the app registration from '{old}' to '{APP_NAME}': the display name alone was sent, and Microsoft Graph shows the new name")
            return
        if attempt < READY_TRIES:
            graph.sleep(READY_SECONDS)
    raise Problem(f"the new name '{APP_NAME}' was sent, and Microsoft Graph still shows the app registration as '{shown}'. Nothing else was changed: run this again in a few minutes")


def follow_name(graph: Graph, app: dict, out: Callable[[str], None]) -> dict | None:
    """After the app registration was renamed: read its enterprise application, and when its name did not follow, rename it too (the display name alone)."""
    found = graph.pages(lookup("servicePrincipals", "appId", app["appId"], PRINCIPAL_SELECT))
    if not found:
        return None
    principal = found[0]
    old = other_name(principal)
    if not old:
        out(f"  the enterprise application's name followed: it is called '{APP_NAME}' too")
        return principal
    graph.send("PATCH", f"servicePrincipals/{principal['id']}", {"displayName": APP_NAME})
    out(f"  the enterprise application's name did not follow, so it was renamed too, from '{old}' to '{APP_NAME}': the display name alone was sent")
    return {**principal, "displayName": APP_NAME}


def apply_steps(graph: Graph, cfg: Config, state: State, out: Callable[[str], None]) -> None:
    app = state.app
    renamed = False
    if app is None:
        app = graph.make("applications", app_body(cfg))
        out(f"  made the app registration {APP_NAME} (client id {app['appId']})")
    elif state.old_name or state.review.fixable(cfg):
        # The person may have been asked a minute ago: what somebody else added since then must survive too, so the lists are read again right before the write.
        current = read_app(graph)
        if current is None or current.get("id") != app["id"]:
            raise Problem("the app registration changed while this ran: nothing was changed, run the tool again")
        review = review_app(current, cfg)
        if review.blocking:
            raise Problem(f"the app registration changed while this ran and now {'; '.join(review.blocking)}: nothing was changed")
        if other_name(current):
            rename_app(graph, app, other_name(current), out)
            renamed = True
        changes = app_changes(current, cfg)
        if changes:
            graph.send("PATCH", f"applications/{app['id']}", changes)
            if review.lacking(cfg):
                out(f"  changed the app registration: {'; '.join(review.lacking(cfg))}{left_alone(review)}")
            if not review.confidential:
                out("  switched public client flows off (isFallbackPublicClient was true)")
        elif not renamed:
            out("  the app registration was in order already")
    principal = state.principal
    if renamed and principal is not None:
        principal = follow_name(graph, app, out)
    if principal is None:
        principal = graph.make("servicePrincipals", {"appId": app["appId"], "appRoleAssignmentRequired": True})
        out("  made the enterprise application, assignment required")
    else:
        if principal.get("appRoleAssignmentRequired") is not True:
            graph.send("PATCH", f"servicePrincipals/{principal['id']}", {"appRoleAssignmentRequired": True})
            out("  switched assignment required on")
        if other_name(principal):
            graph.send("PATCH", f"servicePrincipals/{principal['id']}", {"displayName": APP_NAME})
            out(f"  renamed the enterprise application from '{other_name(principal)}' to '{APP_NAME}': the display name alone was sent")
    if state.credential is None:
        graph.make(f"applications/{app['id']}/federatedIdentityCredentials",
                   {"name": CREDENTIAL_NAME, "issuer": cfg.issuer, "subject": cfg.principal_id, "audiences": [AUDIENCE],
                    "description": "Lets the user-assigned identity of the function app sign in as this app, with no secret."})
        out("  made the federated identity credential")
    for person in cfg.people:
        if person not in state.assigned:
            graph.make(f"servicePrincipals/{principal['id']}/appRoleAssignedTo", {"principalId": person, "resourceId": principal["id"], "appRoleId": NO_ROLE})
            out(f"  assigned {person}")
    if not state.consent:
        if not state.graph_principal:
            raise Problem("the enterprise application of Microsoft Graph is not in this tenant")
        give_consent(graph, principal["id"], state.graph_principal, "User.Read", "User.Read", out)
    if not state.arm_consent:
        if state.arm_principal:
            give_consent(graph, principal["id"], state.arm_principal, ARM_SCOPE, ARM_PERMISSION_NAME, out)
        else:
            out(f"  could not give the administrator's consent for {ARM_PERMISSION_NAME}: its enterprise application is not in this tenant yet. "
                "A tenant administrator makes it and gives the consent, at the address below.")


# ---- the commands --------------------------------------------------------------------------------------------------------------------------------

def command_check(graph: Graph, cfg: Config, out: Callable[[str], None]) -> int:
    out(f"The sign-in of the Meternaut function app, in tenant {cfg.tenant}:")
    items, state = examine(graph, cfg)
    return 0 if report(items, state, cfg, out) else 1


def command_apply(args: argparse.Namespace, graph: Graph, cfg: Config, out: Callable[[str], None], ask: Callable[[str], "str | None"], env: Mapping[str, str]) -> int:
    if args.apply and env.get("GITHUB_ACTIONS") == "true":
        raise Problem("a person who may administer Microsoft Entra runs this, never a pipeline: the workflow's identity must not hold that right (AGENTS.md rules 18 and 24)")
    out(f"The sign-in of the Meternaut function app, in tenant {cfg.tenant}:")
    items, state = examine(graph, cfg)
    for item in items:
        out(describe(item))
    if any(i.blocking for i in items):
        out("Nothing can be changed until the lines above that say DIFFERS with a secret, a certificate or another audience are settled by a person.")
        return 1
    steps = plan(items, state, cfg)
    if not steps:
        if all(i.state == "present" for i in items):
            out("Nothing to make.")
            if state.app:
                out(f"Client id of the app registration (a secret of the environment hub, CONSOLE_APP_CLIENT_ID): {state.app['appId']}")
            return 0
        out("Nothing that this tool can make is missing.")
        for line in guidance(items, state, cfg):
            out(line)
        return 1
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
    return 0 if report(items, state, cfg, out) else 1


# ---- the Teams bot's app registration (docs/proposals/20-teams-cards-through-a-bot.md) -----------------------------------------------------------------

TEAMS_APP_NAME = "Meternaut Teams"
TEAMS_CREDENTIAL_NAME = "meternaut-teams-bot"
TEAMS_IDENTITY_NAME = "id-meternaut-teams"
TEAMS_REPOSITORY = "tinodo/meternaut"
TEAMS_APP_SELECT = APP_SELECT + ",spa,publicClient"
ARM = "https://management.azure.com"
IDENTITY_API = "2023-01-31"
GROUP_NAME = re.compile(r"[A-Za-z0-9._()-]{1,90}")
IDENTITY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
REFUSED_IN = ("GITHUB_ACTIONS", "TF_BUILD")


@dataclass(frozen=True)
class TeamsConfig:
    tenant: str
    subscription: str
    group: str
    identity: str
    repository: str

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/v2.0"

    @property
    def identity_url(self) -> str:
        return (f"{ARM}/subscriptions/{self.subscription}/resourceGroups/{self.group}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{self.identity}"
                f"?api-version={IDENTITY_API}")


@dataclass
class TeamsState:
    app: dict | None = None
    principal: dict | None = None
    credentials: list[dict] = field(default_factory=list)


def read_teams_config(args: argparse.Namespace) -> TeamsConfig:
    tenant = args.tenant_id
    if not tenant or not GUID.fullmatch(tenant):
        raise Problem("--tenant-id is required: the id of the tenant (a GUID)")
    subscription = args.subscription
    if not subscription or not GUID.fullmatch(subscription):
        raise Problem("--subscription is required: the subscription of the project (a GUID), where the identity id-meternaut-teams is")
    group = args.resource_group
    if not group or not GROUP_NAME.fullmatch(group):
        raise Problem("--resource-group is required: the project's resource group")
    if not IDENTITY_NAME.fullmatch(args.identity_name or ""):
        raise Problem("--identity-name is the name of the user-assigned identity")
    if not REPOSITORY.fullmatch(args.repository or ""):
        raise Problem("--repository is owner/name, for example tinodo/meternaut")
    return TeamsConfig(tenant.lower(), subscription.lower(), group, args.identity_name, args.repository)


def read_identity(runner: Callable[[list[str]], tuple[int, str, str]], cfg: TeamsConfig) -> str:
    """The object (principal) id of the user-assigned identity, read from Azure Resource Manager with the signed-in person's own rights. It has to be in this tenant: the app registration and the identity are
    in one tenant, or the token exchange cannot work."""
    code, text, error = runner(["rest", "--method", "get", "--url", cfg.identity_url, "--query", "{principalId: properties.principalId, tenantId: properties.tenantId}", "--output", "json"])
    if code != 0:
        if re.search(r"NotFound|ResourceNotFound|\b404\b|could not be found", error, re.I):
            raise Problem(f"the identity {cfg.identity} is not in resource group {cfg.group}: run the Hub action teams (phase 1) first, which makes it. Nothing was changed")
        raise Problem(f"the identity {cfg.identity} could not be read with your sign-in to the Azure CLI: {first_line(error)}")
    try:
        found = json.loads(text)
    except ValueError:
        found = None
    principal = found.get("principalId") if isinstance(found, dict) else None
    tenant = found.get("tenantId") if isinstance(found, dict) else None
    if not isinstance(principal, str) or not GUID.fullmatch(principal):
        raise Problem(f"Azure Resource Manager gave no object id for the identity {cfg.identity}")
    if not isinstance(tenant, str) or tenant.lower() != cfg.tenant:
        raise Problem(f"the identity {cfg.identity} is not in tenant {cfg.tenant}: the app registration and the identity have to be in the same tenant, and the federated credential would never work. Nothing was changed")
    return principal


def teams_problems(app: dict) -> tuple[list[str], list[str]]:
    """What is wrong with an app registration of that name that is there: what only a person can settle before anything is made (a secret, a certificate, another audience), and what is there besides and is left
    alone (an address, a permission, public client flows), which is a difference all the same, because this design has none of them."""
    blocking, besides = [], []
    if app.get("signInAudience") != THIS_TENANT_ONLY:
        blocking.append(f"it signs in {app.get('signInAudience') or 'nobody'}, and it must be this tenant only ({THIS_TENANT_ONLY})")
    if app.get("passwordCredentials") or app.get("keyCredentials"):
        blocking.append("it holds a secret or a certificate: remove it in the portal, the bot has none (AGENTS.md rule 23)")
    addresses = [str(u) for part in ("web", "spa", "publicClient") for u in ((app.get(part) or {}).get("redirectUris") or [])]
    if addresses:
        besides.append(f"{len(addresses)} redirect {plural(len(addresses), 'address', 'addresses')}: the bot has none, and a person removes them in the portal")
    if permissions_of(app):
        besides.append(f"{len(permissions_of(app))} API {plural(len(permissions_of(app)), 'permission', 'permissions')}: the bot has none, and a person removes them in the portal")
    if app.get("isFallbackPublicClient") not in (None, False):
        besides.append("public client flows are on: a person switches them off in the portal")
    return blocking, besides


def teams_credential_matches(credential: dict, cfg: TeamsConfig, principal_id: str) -> bool:
    """The issuer, the subject and the audience are exactly what the design says. The subject is compared as written, in the case that Azure gave: Microsoft Entra compares it with the case."""
    return credential.get("issuer") == cfg.issuer and credential.get("subject") == principal_id and (credential.get("audiences") or []) == [AUDIENCE]


def examine_teams(graph: Graph, cfg: TeamsConfig, principal_id: str) -> tuple[list[Item], TeamsState]:
    state, items = TeamsState(), []
    state.app = read_named_app(graph, TEAMS_APP_NAME, TEAMS_APP_SELECT)
    if state.app is None:
        items.append(Item(f"App registration {TEAMS_APP_NAME}", "missing", "this tenant only, no secret, no certificate, no API permission, no redirect address"))
    else:
        blocking, besides = teams_problems(state.app)
        items.append(Item(f"App registration {TEAMS_APP_NAME}", "differs" if blocking or besides else "present", "; ".join(blocking + besides), blocking=bool(blocking)))
        found = graph.pages(lookup("servicePrincipals", "appId", state.app["appId"], "id,appId"))
        state.principal = found[0] if found else None
        state.credentials = graph.pages(f"applications/{state.app['id']}/federatedIdentityCredentials")
    items.append(Item("Its service principal in this tenant (without it Teams reports AADSTS7000229)", "present" if state.principal else "missing"))
    wanted = f"issuer {cfg.issuer}, subject the object id of {cfg.identity}, audience {AUDIENCE}"
    matching = [c for c in state.credentials if teams_credential_matches(c, cfg, principal_id)]
    if state.app is None or not state.credentials:
        items.append(Item("Federated identity credential for the identity", "missing", wanted))
    elif len(state.credentials) == 1 and matching:
        items.append(Item("Federated identity credential for the identity (exactly one, with the right values)", "present"))
    elif matching:
        items.append(Item("Federated identity credential for the identity", "differs",
                          f"the right one is there, and {len(state.credentials) - 1} other federated {plural(len(state.credentials) - 1, 'credential', 'credentials')} too: the design has exactly one. "
                          "This tool removes nothing: a person removes the others in the portal (Certificates and secrets, Federated credentials)"))
    else:
        items.append(Item("Federated identity credential for the identity", "differs",
                          f"{len(state.credentials)} federated {plural(len(state.credentials), 'credential is', 'credentials are')} there and none has the right values ({wanted}). This tool removes nothing: "
                          "a person removes the stale one in the portal (Certificates and secrets, Federated credentials), and runs this again"))
    return items, state


def teams_plan(state: TeamsState, cfg: TeamsConfig, principal_id: str) -> list[str]:
    steps = []
    if state.app is None:
        steps.append(f"POST applications: make the app registration {TEAMS_APP_NAME} (this tenant only, no secret, no certificate, no API permission, no redirect address)")
    if state.principal is None:
        steps.append("POST servicePrincipals: make its service principal in this tenant")
    if not state.credentials:
        steps.append(f"POST applications/<the app>/federatedIdentityCredentials: subject the object id of {cfg.identity}, issuer {cfg.issuer}, audience {AUDIENCE}")
    return steps


def teams_apply(graph: Graph, cfg: TeamsConfig, state: TeamsState, principal_id: str, out: Callable[[str], None]) -> None:
    app = state.app
    if app is None:
        app = graph.make("applications", {"displayName": TEAMS_APP_NAME, "signInAudience": THIS_TENANT_ONLY, "isFallbackPublicClient": False,
                                          "description": "Sends the cards of Meternaut to Teams through the Bot Connector. No secret, no certificate, no permission: it is trusted by one managed identity."})
        out(f"  made the app registration {TEAMS_APP_NAME}")
    if state.principal is None:
        graph.make("servicePrincipals", {"appId": app["appId"]})
        out("  made its service principal in this tenant")
    if not state.credentials:
        graph.make(f"applications/{app['id']}/federatedIdentityCredentials",
                   {"name": TEAMS_CREDENTIAL_NAME, "issuer": cfg.issuer, "subject": principal_id, "audiences": [AUDIENCE],
                    "description": f"Lets the user-assigned identity {cfg.identity} sign in as this app, with no secret, to send Teams cards through the Bot Connector."})
        out("  made the federated identity credential")


def teams_report(items: list[Item], state: TeamsState, cfg: TeamsConfig, out: Callable[[str], None]) -> bool:
    """The lines, the client id (to this terminal alone) with the command that stores it, and whether every item is in order."""
    for item in items:
        out(describe(item))
    done = sum(1 for i in items if i.state == "present")
    out(f"{done} of {len(items)} in order.")
    if state.app:
        client = state.app["appId"]
        out(f"Client id of the app registration (shown here, on your terminal, and nowhere else): {client}")
        out("Store it as the secret TEAMS_BOT_APP_ID of the environment hub. It is an identifier of the estate, so it is a secret there and not a variable: GitHub masks a secret in the public log of the Hub")
        out("and does not mask a variable. The command (it keeps the value out of the history of your shell when it asks for it, so paste the client id when it does):")
        out(f"  gh secret set TEAMS_BOT_APP_ID --env hub --repo {cfg.repository}")
    return done == len(items)


def command_teams_bot(args: argparse.Namespace, runner: Callable[[list[str]], tuple[int, str, str]], graph: Graph, hide: Hider, out: Callable[[str], None],
                      ask: Callable[[str], "str | None"], env: Mapping[str, str]) -> int:
    if any(env.get(name) for name in REFUSED_IN):
        raise Problem("a person runs this with their own sign-in, never a pipeline: its output names the client id of the app registration, and the deploy identity must not hold a right in Microsoft Entra "
                      "(AGENTS.md rules 18 and 24)")
    cfg = read_teams_config(args)
    principal_id = read_identity(runner, cfg)
    hide.add(principal_id)
    out(f"The app registration of the Teams bot, in tenant {cfg.tenant}:")
    items, state = examine_teams(graph, cfg, principal_id)
    if any(i.blocking for i in items):
        for item in items:
            out(describe(item))
        out("Nothing can be changed until the lines above that say DIFFERS with a secret, a certificate or another audience are settled by a person.")
        return 1
    steps = teams_plan(state, cfg, principal_id)
    if not steps:
        out("Nothing to make, and nothing was changed." if all(i.state == "present" for i in items) else "Nothing that this tool can make is missing, and nothing was changed.")
        return teams_final(items, state, cfg, out)
    for item in items:
        out(describe(item))
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
    teams_apply(graph, cfg, state, principal_id, out)
    out("Reading everything back:")
    items, state = examine_teams(graph, cfg, principal_id)
    return teams_final(items, state, cfg, out)


def teams_final(items: list[Item], state: TeamsState, cfg: TeamsConfig, out: Callable[[str], None]) -> int:
    """The read-back after a change, or the report of a second run: the lines, the client id, and the proof that the app has no secret and no certificate and exactly one credential."""
    in_order = teams_report(items, state, cfg, out)
    if state.app is not None:
        out(f"Read back: {len(state.app.get('passwordCredentials') or [])} passwords, {len(state.app.get('keyCredentials') or [])} keys and {len(state.credentials)} federated "
            f"{plural(len(state.credentials), 'credential', 'credentials')} on the app registration.")
    out("Whether the federated credential really works is not known until the first token exchange: run the Hub action teams-test.")
    return 0 if in_order else 1


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
        sub.add_argument("--host", help="the host name that people open: the function app's host name on the platform's Application Gateway (the variable CONSOLE_HOST_NAME), or the function app's own name, for example func-name.azurewebsites.net")
        sub.add_argument("--identity-principal-id", help="the object id of the user-assigned identity that signs in as the app")
        sub.add_argument("--assign", action="append", help="the object id of a person who may sign in; repeat it or separate with commas")
        if name == "apply":
            sub.add_argument("--apply", action="store_true", help="make the changes (the default is a dry run)")
            sub.add_argument("--yes", action="store_true", help="do not ask first")
    teams = commands.add_parser("teams-bot", help="the app registration Meternaut Teams, its service principal and its federated credential for the identity id-meternaut-teams; dry run unless --apply")
    teams.add_argument("--tenant-id")
    teams.add_argument("--subscription", help="the subscription of the project, where the identity id-meternaut-teams is")
    teams.add_argument("--resource-group", help="the project's resource group")
    teams.add_argument("--identity-name", default=TEAMS_IDENTITY_NAME, help=f"the user-assigned identity that the Hub action teams made (default {TEAMS_IDENTITY_NAME})")
    teams.add_argument("--repository", default=TEAMS_REPOSITORY, help=f"the repository whose environment hub takes the secret, for the command that is printed (default {TEAMS_REPOSITORY})")
    teams.add_argument("--apply", action="store_true", help="make the changes (the default is a dry run)")
    teams.add_argument("--yes", action="store_true", help="do not ask first")
    args = parser.parse_args(argv)
    hide = Hider()
    try:
        if args.command == "teams-bot":
            return command_teams_bot(args, runner, Graph(Tokens(runner, args.tenant_id or "", hide), transport, sleep), hide, out, ask, env)
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
