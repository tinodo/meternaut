#!/usr/bin/env python3
"""The sender mailbox of Meternaut, and the one right to send as that mailbox only (standard library only).

    python tools/exchange-setup.py check --tenant-id <id> --domain <domain> --identity-client-id <id> --identity-principal-id <id> [--other-mailbox <address>]
    python tools/exchange-setup.py apply --tenant-id <id> --domain <domain> --identity-client-id <id> --identity-principal-id <id> [--other-mailbox <address>] [--apply]

Meternaut sends e-mail through Microsoft Graph `sendMail`, as one shared mailbox, with a managed identity. That identity gets no Microsoft Entra
permission for mail. Its only right is the Exchange Online role `Application Mail.Send` (RBAC for Applications), limited by a management scope to that
one mailbox (https://learn.microsoft.com/exchange/permissions-exo/application-rbac). Grants in Exchange and in Entra add up, so an Entra consent for a mail
permission would let the identity send as any mailbox, whatever the scope says: `check` looks for one.

A person who may administer Exchange Online runs this tool with their own sign-in to the Azure CLI. It never runs in a pipeline (AGENTS.md rules 18 and 24).
It sends Exchange nothing but the cmdlets listed in CMDLETS below, and it removes nothing.

check   Read only. For each item: present, MISSING or why not. Exit 0 when every item is in order, exit 1 otherwise.
apply   A dry run: prints what is there and the cmdlets that it would send. With --apply it sends them, each only for what is missing, and checks again.
        It stops before it changes anything when the identity holds a role assignment that it must not hold, or an Entra application permission, and says
        what to remove. The tool does not remove them: a person does.

The items, in order:
  1  The shared mailbox (Get-Mailbox, New-Mailbox). Its display name ends "(AI)": the sender name is the first AI mark of every letter.
  2  The service principal pointer in Exchange for the identity (Get-ServicePrincipal, New-ServicePrincipal).
  3  The management scope "Meternaut sender mailbox", whose filter names the one address (Get-, New- and Set-ManagementScope).
  4  The assignment of the role "Application Mail.Send" to the identity, limited to that scope (Get-, New-ManagementRoleAssignment).
  4b The identity holds no other Exchange role assignment, and none without the scope. The rows of Exchange's default role assignment policy (the self-service
     roles of a mailbox user, such as MyBaseOptions), which Exchange also lists for a service principal pointer, are the policy's and not the identity's: they
     are not counted, and nothing here removes them. Test-ServicePrincipalAuthorization (5a, 5b) says what the identity can really do.
  5a Test-ServicePrincipalAuthorization: the identity may send as the shared mailbox (InScope true).
  5b With --other-mailbox: the identity may not send as that other mailbox (InScope false). A negative proof, so give a mailbox that exists.
  6  The sign-in of the shared mailbox's user is blocked (Microsoft Graph, accountEnabled false). A user that is not there yet is "not yet visible", not a failure.
  7  The identity holds no application permission in Microsoft Entra (Microsoft Graph, appRoleAssignments).

One more cmdlet is sent, only when Exchange asks for it: Enable-OrganizationCustomization, which has no parameters. A new Exchange Online organization can refuse
to make a custom management scope ("The command you tried to run isn't currently allowed in your organization") until it has been run. It un-consolidates stored
objects so that custom roles and scopes can be made; it changes no mail flow and no policy; Exchange says it is run once per organization and cannot be run again.
When a cmdlet that creates or changes something is refused for that reason, `apply --apply` says so, sends it once (an answer that it was run before is fine) and
tries the refused cmdlet again, 12 times at most, 20 seconds apart, because Exchange can take minutes to apply it. Every other error stops the run at once.
A dry run sends nothing and says that this may be needed. `check` never sends it.
The role assignment (item 4) can be refused with "You must be assigned a delegating role assignment ..." for about an hour after that step, until Exchange has
applied the right to give the role. The tool says so and stops, without trying again for an hour: run it again later, it only creates what is missing.

It talks to Exchange as the Azure CLI's token for https://outlook.office365.com (never printed, never stored): a POST to
https://outlook.office365.com/adminapi/beta/<tenant id>/InvokeCommand. The Azure CLI is `az`, or the command in the variable AZ
(for example "C:\\path\\python.exe" -IBm azure.cli).

Two things stay with the person. The mail-flow rule that rejects mail from the mailbox to any address that is not on the list of people is not made or
checked here. And Exchange applies a new role assignment or a changed scope to live sends after 30 minutes to 2 hours: the test of item 5 bypasses that
delay, so the first real letter is sent after it (build plan, check C4).
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
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping

EXCHANGE = "https://outlook.office365.com"
GRAPH = "https://graph.microsoft.com"
ANCHOR = "SystemMailbox{bb558c35-97f1-4cb9-8ff7-d53741dc928c}"
ROLE = "Application Mail.Send"
SCOPE = "Meternaut sender mailbox"
DEFAULT_ALIAS = "meternaut-ai"
DEFAULT_DISPLAY = "Meternaut (AI)"
DEFAULT_IDENTITY = "meternaut-cases"
ENABLE = "Enable-OrganizationCustomization"
CMDLETS = frozenset({
    "Get-Mailbox", "New-Mailbox", "Get-ServicePrincipal", "New-ServicePrincipal", "Get-ManagementScope", "New-ManagementScope", "Set-ManagementScope",
    "Get-ManagementRoleAssignment", "New-ManagementRoleAssignment", "Test-ServicePrincipalAuthorization", ENABLE,
})

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
DOMAIN = re.compile(r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
ALIAS = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?")
LOCAL_PART = re.compile(r"[A-Za-z0-9._-]{1,64}")
IDENTITY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._() -]{0,79}")
# What Exchange says when a Get- finds nothing: this is "absent", every other error is a real one.
ABSENT = re.compile(r"couldn'?t be found|could not be found|was not found|can'?t be found|cannot be found|couldn'?t find object", re.I)
# What Exchange says when it will not make a custom role or scope before Enable-OrganizationCustomization has been run ("dehydrated" is its word for such an
# organization), and what it says to that cmdlet when it was run before ("has already been run", "isn't required").
CUSTOMIZATION_ASKED = re.compile(r"Enable-OrganizationCustomization|InvalidOperationInDehydratedContext", re.I)
CUSTOMIZATION_DONE = re.compile(r"already|isn.?t required|not required", re.I)
RETRY_TRIES = 12
RETRY_PAUSE = 20.0
# What Exchange says when it will not yet let the person give a role: the right to give "Application Mail.Send" comes with the role group that
# Enable-OrganizationCustomization brings, and Exchange applied it about an hour later in the pilot.
DELEGATING = re.compile(r"delegating role assignment", re.I)
DELEGATING_WAIT = ("Exchange has not applied the right to give this role yet. In the pilot it came about an hour after Enable-OrganizationCustomization. "
                   "Wait, then run this tool again: it only creates what is missing.")
ONE_TIME_STEP = ("Exchange asks for a one-time step per organization: Enable-OrganizationCustomization. It only un-consolidates stored objects so that custom roles "
                 "and scopes can be made; it changes no mail flow and no policy; Exchange says it is run once and cannot be run again.")
MAY_ASK = ("Exchange may first ask for Enable-OrganizationCustomization, once per organization. That is the one other cmdlet that this tool can send, "
           "and only when Exchange asks for it.")
TOKEN_SHAPES = (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}"), re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"))
HIDDEN = "[token hidden]"
NOT_COVERED = "Not covered by this tool: the mail-flow rule that rejects mail from the mailbox to any address that is not on the list of people."
APPLY_DELAY = ("Exchange applies a new role assignment or a changed scope to live sends after 30 minutes to 2 hours. The test above does not wait for that, "
               "so repeat the real send after that time.")

LABELS = {"present": "present", "missing": "MISSING", "differs": "DIFFERS", "fail": "FAIL", "cannot": "cannot yet", "unreadable": "UNREADABLE",
          "not_visible": "not yet visible", "not_run": "not run"}
IN_ORDER = frozenset({"present", "not_visible", "not_run"})
POLICY_KIND = "roleassignmentpolicy"  # what Exchange calls the assignee and the method of a row of its default role assignment policy, in lower case

Http = Callable[[str, str, Mapping[str, str], "bytes | None"], "tuple[int, Mapping[str, str], bytes]"]


class Problem(Exception):
    """Something the person who runs the tool can fix or must know; printed without a trace."""


class Refused(Problem):
    """A cmdlet that Exchange answered with an error. The whole message is kept: the text shown has its first 300 characters, the caller reads what Exchange asks for."""

    def __init__(self, cmdlet: str, status: int, code: str, message: str) -> None:
        super().__init__(f"{cmdlet} failed: {failure(status, code, message)}")
        self.cmdlet, self.status, self.code, self.message = cmdlet, status, code, message


# ---- the Azure CLI and its tokens ----------------------------------------------------------------------------------------------------------------

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
        return re.sub(rf"(?i)bearer\s+{re.escape(HIDDEN)}", HIDDEN, shown)


class Tokens:
    """The access token of the signed-in person's Azure CLI for one resource of one tenant, asked for once and kept in memory only."""

    def __init__(self, runner: Callable[[list[str]], tuple[int, str, str]], tenant: str, hide: Hider) -> None:
        self.runner, self.tenant, self.hide, self.cache = runner, tenant, hide, {}

    def __call__(self, resource: str) -> str:
        if resource not in self.cache:
            code, out, err = self.runner(["account", "get-access-token", "--resource", resource, "--tenant", self.tenant, "--query", "accessToken", "-o", "tsv"])
            token = out.strip()
            if code != 0 or not token:
                raise Problem(f"the Azure CLI gave no token for {resource}: {first_line(err)}")
            self.hide.add(token)
            self.cache[resource] = token
        return self.cache[resource]


# ---- Exchange and Graph --------------------------------------------------------------------------------------------------------------------------

def default_http(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 (the address is built from the two hosts above)
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
        # Exchange's own words are often in the details: the message itself can be only "Error executing cmdlet"
        parts = [str(error.get("message") or "")] + [str(d.get("message") or "") for d in (error.get("details") or []) if isinstance(d, dict)]
        return str(error.get("code") or ""), " ".join(" ".join(parts).split())
    return "", " ".join((str(document.get("message")) if isinstance(document, dict) and document.get("message") else text).split())


def wait_of(headers: Mapping[str, str]) -> float:
    given = next((v for k, v in headers.items() if k.lower() == "retry-after"), "5")
    try:
        return min(60.0, max(1.0, float(given)))
    except ValueError:
        return 5.0


def failure(status: int, code: str, message: str) -> str:
    """The status, the code and the first 300 characters of the message of a failed call."""
    return ": ".join(part for part in (f"{status} {code}".strip(), message[:300]) if part)


class Exchange:
    """Exchange Online's admin API: one cmdlet at a time, with the token of the signed-in person. Only the cmdlets of CMDLETS can be sent."""

    def __init__(self, tenant: str, domain: str, tokens: Tokens, transport: Http = default_http, sleep: Callable[[float], None] = time.sleep,
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())) -> None:
        self.tenant, self.domain, self.tokens, self.transport, self.sleep, self.new_id = tenant, domain, tokens, transport, sleep, new_id

    def call(self, cmdlet: str, parameters: dict, absent_ok: bool = False) -> list[dict]:
        """The objects that the cmdlet returned. With absent_ok, a Get- that finds nothing returns an empty list, as an empty answer or as an error does.
        An error from Exchange is a Refused, which is a Problem."""
        if cmdlet not in CMDLETS:
            raise Problem(f"{cmdlet} is not one of the cmdlets that this tool sends")
        url = f"{EXCHANGE}/adminapi/beta/{self.tenant}/InvokeCommand"
        body = json.dumps({"CmdletInput": {"CmdletName": cmdlet, "Parameters": parameters}}).encode("utf-8")
        token = self.tokens(EXCHANGE)
        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json", "X-ResponseFormat": "json",
                       "X-CmdletName": cmdlet, "client-request-id": self.new_id(), "X-AnchorMailbox": f"UPN:{ANCHOR}@{self.domain}"}
            status, answer_headers, raw = self.transport("POST", url, headers, body)
            if status in (429, 503) and attempt == 1:
                self.sleep(wait_of(answer_headers))
                continue
            break
        if status == 200:
            if not raw.strip():
                return []
            try:
                document = json.loads(raw.decode("utf-8"))
            except ValueError as e:
                raise Problem(f"{cmdlet}: Exchange answered with something that is not JSON") from e
            value = document.get("value", []) if isinstance(document, dict) else []
            return [v for v in ([value] if isinstance(value, dict) else value if isinstance(value, list) else []) if isinstance(v, dict)]
        code, message = error_of(raw)
        if absent_ok and cmdlet.startswith("Get-") and status not in (401, 403) and ABSENT.search(message):
            return []
        raise Refused(cmdlet, status, code, message)


class Graph:
    """Read-only calls to Microsoft Graph with the signed-in person's token. A call that fails gives a status and a text, never an exception for the caller."""

    def __init__(self, tokens: Tokens, transport: Http = default_http, sleep: Callable[[float], None] = time.sleep) -> None:
        self.tokens, self.transport, self.sleep = tokens, transport, sleep

    def get(self, path: str) -> tuple[int, dict, str]:
        try:
            token = self.tokens(GRAPH)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            for attempt in (1, 2):
                status, answer_headers, raw = self.transport("GET", f"{GRAPH}/v1.0/{path}", headers, None)
                if status in (429, 503) and attempt == 1:
                    self.sleep(wait_of(answer_headers))
                    continue
                break
        except Problem as e:
            return 0, {}, str(e)
        if status == 200:
            try:
                document = json.loads(raw.decode("utf-8"))
            except ValueError:
                return status, {}, "the answer is not JSON"
            return status, document if isinstance(document, dict) else {}, ""
        code, message = error_of(raw)
        return status, {}, failure(status, code, message)


# ---- the inputs ----------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    tenant: str
    domain: str
    alias: str
    display: str
    address: str
    client_id: str
    principal_id: str
    identity_name: str
    other: str | None

    @property
    def scope_filter(self) -> str:
        return f"PrimarySmtpAddress -eq '{self.address}'"


def need(value: str | None, option: str, what: str) -> str:
    if not value:
        raise Problem(f"{option} is required: {what}")
    return value


def read_config(args: argparse.Namespace) -> Config:
    tenant = need(args.tenant_id, "--tenant-id", "the id of the tenant (a GUID)")
    if not GUID.fullmatch(tenant):
        raise Problem("--tenant-id is not a GUID")
    domain = need(args.domain, "--domain", "the default domain of the tenant, for example contoso.example")
    if not DOMAIN.fullmatch(domain):
        raise Problem("--domain is not a domain name such as contoso.example")
    alias = args.alias or DEFAULT_ALIAS
    if not LOCAL_PART.fullmatch(alias) or not ALIAS.fullmatch(alias):
        raise Problem("--alias is the part of the address before the @: letters, digits, dots, hyphens and underscores, at most 64 characters")
    display = args.display_name or DEFAULT_DISPLAY
    if not 1 <= len(display) <= 80 or any(ord(ch) < 32 or ord(ch) == 127 for ch in display) or display != display.strip():
        raise Problem("--display-name is one line of at most 80 characters")
    if not display.endswith("(AI)"):
        raise Problem('--display-name ends with "(AI)": the sender name is the first mark that an AI wrote the letter (AGENTS.md rule 13)')
    client_id = need(args.identity_client_id, "--identity-client-id", "the client id of the identity (a GUID)")
    principal_id = need(args.identity_principal_id, "--identity-principal-id", "the object (principal) id of the identity (a GUID)")
    for value, option in ((client_id, "--identity-client-id"), (principal_id, "--identity-principal-id")):
        if not GUID.fullmatch(value):
            raise Problem(f"{option} is not a GUID")
    if client_id.lower() == principal_id.lower():
        raise Problem("--identity-client-id and --identity-principal-id are two different values of the identity: the client id (app id) and the object id")
    name = args.identity_name or DEFAULT_IDENTITY
    if not IDENTITY_NAME.fullmatch(name):
        raise Problem("--identity-name is a name of at most 80 characters: letters, digits, spaces and . _ - ( )")
    address = f"{alias}@{domain}".lower()
    other = args.other_mailbox
    if other:
        local, _, host = other.partition("@")
        if not LOCAL_PART.fullmatch(local) or not DOMAIN.fullmatch(host):
            raise Problem("--other-mailbox is an address such as someone@contoso.example")
        if other.lower() == address:
            raise Problem("--other-mailbox is a different mailbox than the sender mailbox")
        other = other.lower()
    return Config(tenant.lower(), domain.lower(), alias.lower(), display, address, client_id.lower(), principal_id.lower(), name, other)


# ---- reading what is there -----------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Step:
    cmdlet: str
    parameters: dict


@dataclass
class Item:
    key: str
    label: str
    state: str
    detail: str = ""
    step: Step | None = None
    blocks: bool = False  # a state that apply never goes past: a person has to remove something first


def prop(obj: Mapping, *names: str):
    lowered = {str(k).lower(): v for k, v in obj.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def name_of(value: object) -> str:
    """A name out of a property that Exchange may show as text, as a list or as an object."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = prop(value, "Name", "DisplayName") or ""
    return "" if value is None else " ".join(str(value).split())


def truth(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return True if text == "true" else False if text == "false" else None


def names_of(value: object) -> list[str]:
    """The names in a property that Exchange may show as one value or as a list."""
    return [name for name in (name_of(v) for v in (value if isinstance(value, (list, tuple)) else [value])) if name]


def of_policy(row: Mapping) -> bool:
    """Whether the row belongs to Exchange's default role assignment policy: the self-service roles of a mailbox user (MyBaseOptions and the like). Exchange shows them
    for any recipient-like object, a service principal pointer included. They are the policy's and not the identity's, they cannot be removed from here and must not
    be, and what the identity can really do is told by Test-ServicePrincipalAuthorization (items 5a and 5b). A row counts as the policy's when its assignee type is the
    policy, or when every method that it names is the policy; a row that names a direct or a group method as well stays the identity's."""
    methods = [m.lower() for m in names_of(prop(row, "AssignmentMethod"))]
    return name_of(prop(row, "RoleAssigneeType")).lower() == POLICY_KIND or (bool(methods) and all(m == POLICY_KIND for m in methods))


def own_assignments(rows: list[dict]) -> list[dict]:
    """The rows that are the identity's: a direct assignment, or one that it holds through a group. Every row of the default policy is left out."""
    return [row for row in rows if not of_policy(row)]


def is_direct(row: Mapping) -> bool:
    """Whether the identity itself is the assignee of the row, and not a group that it belongs to."""
    return name_of(prop(row, "RoleAssigneeType")).lower() == "serviceprincipal" or "direct" in [m.lower() for m in names_of(prop(row, "AssignmentMethod"))]


def held_through(row: Mapping) -> str:
    kind, who = name_of(prop(row, "RoleAssigneeType")), name_of(prop(row, "RoleAssigneeName"))
    return " ".join(part for part in (kind, f"'{who}'" if who else "") if part) or "a way that Exchange does not name"


def unwrapped(text: str) -> str:
    """A filter in one case and one spacing, without brackets around the whole of it."""
    text = " ".join(str(text).split()).lower()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for index, ch in enumerate(text):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and index < len(text) - 1:
                return text
        text = text[1:-1].strip()
    return text


def authorization(ex: Exchange, cfg: Config, resource: str) -> list[bool | None]:
    """InScope of every row of Test-ServicePrincipalAuthorization that is for the role, for one mailbox."""
    rows = ex.call("Test-ServicePrincipalAuthorization", {"Identity": cfg.principal_id, "Resource": resource})
    return [truth(prop(r, "InScope")) for r in rows if name_of(prop(r, "RoleName")).lower() == ROLE.lower()]


def examine(ex: Exchange, graph: Graph, cfg: Config) -> list[Item]:
    items: list[Item] = []
    mailbox = bool(ex.call("Get-Mailbox", {"Identity": cfg.alias}, absent_ok=True))
    items.append(Item("1", f"Shared mailbox {cfg.address}", "present" if mailbox else "missing",
                      step=None if mailbox else Step("New-Mailbox", {"Shared": True, "Name": cfg.alias, "DisplayName": cfg.display, "Alias": cfg.alias,
                                                                     "PrimarySmtpAddress": cfg.address})))
    pointer = bool(ex.call("Get-ServicePrincipal", {"Identity": cfg.principal_id}, absent_ok=True))
    items.append(Item("2", f"Service principal pointer in Exchange for {cfg.identity_name} (object id {cfg.principal_id})", "present" if pointer else "missing",
                      step=None if pointer else Step("New-ServicePrincipal", {"AppId": cfg.client_id, "ObjectId": cfg.principal_id, "DisplayName": cfg.identity_name})))

    found = ex.call("Get-ManagementScope", {"Identity": SCOPE}, absent_ok=True)
    label = f'Management scope "{SCOPE}", limited to {cfg.address}'
    if not found:
        items.append(Item("3", label, "missing", step=Step("New-ManagementScope", {"Name": SCOPE, "RecipientRestrictionFilter": cfg.scope_filter})))
    else:
        live = name_of(prop(found[0], "RecipientFilter", "RecipientRestrictionFilter"))
        if unwrapped(live) == unwrapped(cfg.scope_filter):
            items.append(Item("3", label, "present"))
        else:
            items.append(Item("3", label, "differs", f"its filter is {live or 'empty'}; it must be {cfg.scope_filter}",
                              Step("Set-ManagementScope", {"Identity": SCOPE, "RecipientRestrictionFilter": cfg.scope_filter})))

    # Nothing can be assigned to a pointer that is not there, so there is nothing to read.
    named = own_assignments(ex.call("Get-ManagementRoleAssignment", {"RoleAssignee": cfg.principal_id, "Role": ROLE}, absent_ok=True)) if pointer else []
    rows = ex.call("Get-ManagementRoleAssignment", {"RoleAssignee": cfg.principal_id}, absent_ok=True) if pointer else []
    every = own_assignments(rows)
    scoped = any((name_of(prop(a, "Role")) or ROLE).lower() == ROLE.lower() and name_of(prop(a, "CustomResourceScope")).lower() == SCOPE.lower() for a in named)
    items.append(Item("4", f'Role "{ROLE}" for the identity, limited to the scope "{SCOPE}"', "present" if scoped else "missing",
                      step=None if scoped else Step("New-ManagementRoleAssignment", {"App": cfg.principal_id, "Role": ROLE, "CustomResourceScope": SCOPE})))
    strays = [a for a in every if not (name_of(prop(a, "Role")).lower() == ROLE.lower() and name_of(prop(a, "CustomResourceScope")).lower() == SCOPE.lower())]
    items.append(stray_item(strays, len(rows) - len(every)))

    ready = mailbox and pointer and scoped
    items.append(proof_item("5a", f"The identity may send as {cfg.address}", ready, ex, cfg, cfg.address, want=True))
    if cfg.other:
        items.append(proof_item("5b", f"The identity may not send as {cfg.other}", ready, ex, cfg, cfg.other, want=False))
    else:
        items.append(Item("5b", "The identity may not send as another mailbox", "not_run", "give --other-mailbox <the address of a different mailbox> to prove it"))
    items.append(signin_item(graph, cfg, mailbox))
    items.append(consent_item(graph, cfg))
    return items


def stray_item(strays: list[dict], ignored: int = 0) -> Item:
    label = "The identity holds no other Exchange role assignment, and none without the scope"
    if not strays:
        note = (f"{ignored} row(s) of Exchange's default role assignment policy (the self-service roles of a mailbox user) are not the identity's and are not counted; "
                "items 5a and 5b show what the identity can do") if ignored else ""
        return Item("4b", label, "present", note)
    lines = ["THE IDENTITY HOLDS EXCHANGE ROLE ASSIGNMENTS THAT IT MUST NOT HOLD. Rights add up, so it can do more than send as the sender mailbox.",
             "This tool removes nothing. Remove each of these yourself (Exchange Online PowerShell), then run this tool again:"]
    for a in strays:
        assignment = name_of(prop(a, "Name", "Identity"))
        scope = name_of(prop(a, "CustomResourceScope")) or "no custom resource scope, so it covers every mailbox"
        lines.append(f"  - assignment {assignment or '(no name shown)'}: role {name_of(prop(a, 'Role')) or '?'}, {scope}")
        if not is_direct(a):
            lines.append(f"    It comes through {held_through(a)}, not directly. Do not remove the assignment (others hold it too): take the identity out of that, or ask who owns it.")
        elif assignment:
            lines.append(f"    Remove-ManagementRoleAssignment -Identity '{assignment.replace(chr(39), chr(39) * 2)}'")
    return Item("4b", label, "fail", "\n".join(lines), blocks=True)


def proof_item(key: str, label: str, ready: bool, ex: Exchange, cfg: Config, resource: str, want: bool) -> Item:
    if not ready:
        return Item(key, label, "cannot", "items 1, 2 and 4 come first")
    rows = authorization(ex, cfg, resource)
    if want:
        if any(r is True for r in rows):
            return Item(key, label, "present", f"{ROLE}: InScope true")
        if rows and all(r is False for r in rows):
            return Item(key, label, "missing", f"{ROLE}: InScope false, so the mailbox is outside the scope (the filter is {cfg.scope_filter})")
        return Item(key, label, "missing", f"the test shows no clear InScope true for {ROLE}")
    if any(r is True for r in rows):
        return Item(key, label, "fail", f"{ROLE}: InScope TRUE. The identity can send as {resource}: the scope does not hold, find out why before anything is sent")
    if rows and all(r is False for r in rows):
        return Item(key, label, "present", f"{ROLE}: InScope false")
    return Item(key, label, "fail", f"the test shows no clear InScope false for {ROLE}, so nothing is proved")


def signin_item(graph: Graph, cfg: Config, mailbox: bool) -> Item:
    label = "The sign-in of the mailbox's user is blocked"
    if not mailbox:
        return Item("6", label, "cannot", "the mailbox comes first")
    status, document, text = graph.get(f"users/{urllib.parse.quote(cfg.address, safe='@')}?$select=accountEnabled")
    if status == 404:
        return Item("6", label, "not_visible", "the user of a new shared mailbox can take a few minutes to appear: run check again later. If it stays missing, "
                                               "its sign-in name is not the address: look the user up in the Microsoft Entra admin center")
    if status != 200:
        return Item("6", label, "unreadable", f"Microsoft Graph: {text or status}")
    enabled = document.get("accountEnabled")
    if enabled is False:
        return Item("6", label, "present", "accountEnabled is false")
    if enabled is True:
        return Item("6", label, "missing", "accountEnabled is TRUE. Block the sign-in in the Microsoft Entra admin center: Users, the mailbox's user, Edit properties, "
                                          "Account enabled off. This tool does not change users")
    return Item("6", label, "unreadable", "Microsoft Graph gave no accountEnabled")


def consent_item(graph: Graph, cfg: Config) -> Item:
    label = "The identity holds no application permission in Microsoft Entra"
    status, document, text = graph.get(f"servicePrincipals/{cfg.principal_id}/appRoleAssignments")
    if status == 404:
        return Item("7", label, "unreadable", "Microsoft Entra has no service principal with this object id: check --identity-principal-id")
    if status != 200:
        return Item("7", label, "unreadable", f"Microsoft Graph: {text or status}")
    granted = [a for a in document.get("value") or [] if isinstance(a, dict)]
    if not granted:
        return Item("7", label, "present")
    lines = ["THE IDENTITY HOLDS APPLICATION PERMISSIONS IN MICROSOFT ENTRA. They add up to the Exchange role: with a mail permission among them it can send as any mailbox.",
             "This tool removes nothing. Remove the consent in Microsoft Entra (the identity's enterprise application, Permissions), then run this tool again:"]
    for a in granted[:10]:
        lines.append(f"  - {name_of(a.get('resourceDisplayName')) or 'a resource'}: app role {name_of(a.get('appRoleId')) or '?'}")
    return Item("7", label, "fail", "\n".join(lines), blocks=True)


# ---- the commands --------------------------------------------------------------------------------------------------------------------------------

def describe(item: Item) -> str:
    line = f"  {LABELS[item.state]:<16}{item.key:<4}{item.label}"
    return line + "".join(f"\n{'':<22}{text}" for text in item.detail.splitlines())


def report(items: list[Item], out: Callable[[str], None]) -> bool:
    for item in items:
        out(describe(item))
    present = sum(1 for i in items if i.state == "present")
    out(f"{present} of {len(items)} present.")
    return all(i.state in IN_ORDER for i in items)


def command_check(ex: Exchange, graph: Graph, cfg: Config, out: Callable[[str], None]) -> int:
    out(f"The sender setup for {cfg.address} in tenant {cfg.tenant}:")
    return 0 if report(examine(ex, graph, cfg), out) else 1


def asks_for_customization(error: Refused) -> bool:
    """Whether Exchange refused the cmdlet because the organization first needs Enable-OrganizationCustomization (its words are in the code or the message)."""
    return bool(CUSTOMIZATION_ASKED.search(f"{error.code} {error.message}"))


def make_ready(ex: Exchange, out: Callable[[str], None]) -> None:
    """Says why, then sends Enable-OrganizationCustomization. An answer that it was run before is fine; any other error stops the run."""
    out(f"  {ONE_TIME_STEP}")
    try:
        ex.call(ENABLE, {})
    except Refused as e:
        if not CUSTOMIZATION_DONE.search(f"{e.code} {e.message}"):
            raise
        out(f"  Exchange says that {ENABLE} was run before ({failure(e.status, e.code, e.message)}). That is fine: it is not needed again.")
        return
    out(f"  sent {ENABLE}")


def send_step(ex: Exchange, step: Step, out: Callable[[str], None], ready: bool) -> bool:
    """Sends one cmdlet that creates or changes something. When Exchange refuses it because the organization first needs Enable-OrganizationCustomization, that
    cmdlet is sent (once per run) and the refused one is tried again, RETRY_PAUSE seconds apart and RETRY_TRIES times at most, because Exchange can take minutes
    to apply it. Any other error stops the run at once. Returns whether Enable-OrganizationCustomization has been dealt with in this run."""
    try:
        ex.call(step.cmdlet, step.parameters)
    except Refused as e:
        if not asks_for_customization(e):
            if DELEGATING.search(e.message):
                raise Problem(f"{e} {DELEGATING_WAIT}") from e
            raise
        out(f"  {step.cmdlet} was refused ({failure(e.status, e.code, '')}).")
    else:
        out(f"  sent {step.cmdlet}")
        return ready
    if not ready:
        make_ready(ex, out)
    out(f"  Exchange can take minutes to apply it. {step.cmdlet} is tried again, {RETRY_TRIES} times at most, {RETRY_PAUSE:g} seconds apart.")
    for attempt in range(1, RETRY_TRIES + 1):
        ex.sleep(RETRY_PAUSE)
        try:
            ex.call(step.cmdlet, step.parameters)
        except Refused as e:
            if not asks_for_customization(e):
                if DELEGATING.search(e.message):
                    raise Problem(f"{e} {DELEGATING_WAIT}") from e
                raise
            out(f"  try {attempt} of {RETRY_TRIES}: {step.cmdlet} is still refused")
        else:
            out(f"  sent {step.cmdlet} (try {attempt} of {RETRY_TRIES})")
            return True
    raise Problem(f"{step.cmdlet} is still refused after {RETRY_TRIES} tries over {RETRY_TRIES * RETRY_PAUSE:g} seconds: Exchange has not yet applied {ENABLE}. "
                  "It can take longer. Wait, then run this tool again: it only creates what is missing.")


def command_apply(ex: Exchange, graph: Graph, cfg: Config, out: Callable[[str], None], really: bool) -> int:
    out(f"The sender setup for {cfg.address} in tenant {cfg.tenant}:")
    items = examine(ex, graph, cfg)
    ok = report(items, out)
    blocked = [i for i in items if i.blocks]
    if blocked:
        out("Nothing was changed. Fix what the lines above say, then run this tool again.")
        return 1
    steps = [i.step for i in items if i.step]
    if not steps:
        out("Nothing to create or change." if ok else "Nothing to create or change. Items that are not in order need more than this tool does: read their lines.")
        return 0 if ok else 1
    out(f"{len(steps)} cmdlet(s) {'will be' if really else 'would be'} sent to Exchange, and nothing else:")
    for step in steps:
        out(f"  {step.cmdlet} {json.dumps(step.parameters)}")
    out(MAY_ASK)
    if not really:
        out("This was a dry run. Run again with --apply to send them.")
        return 0
    ready = False
    for step in steps:
        ready = send_step(ex, step, out, ready)
    out("Checking again:")
    in_order = report(examine(ex, graph, cfg), out)
    if any(step.cmdlet in ("New-ManagementRoleAssignment", "Set-ManagementScope") for step in steps):
        out(APPLY_DELAY)
    return 0 if in_order else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "read only: which items are in order"), ("apply", "dry run; with --apply, create what is missing")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--tenant-id", help="the id of the tenant (a GUID)")
        sub.add_argument("--domain", help="the default domain of the tenant, for example contoso.example")
        sub.add_argument("--alias", help=f"the alias of the shared mailbox (default {DEFAULT_ALIAS})")
        sub.add_argument("--display-name", help=f'the name of the shared mailbox, ending "(AI)" (default "{DEFAULT_DISPLAY}")')
        sub.add_argument("--identity-client-id", help="the client id (app id) of the identity that sends")
        sub.add_argument("--identity-principal-id", help="the object (principal) id of the identity that sends")
        sub.add_argument("--identity-name", help=f"the name of the identity (default {DEFAULT_IDENTITY})")
        sub.add_argument("--other-mailbox", help="the address of a different mailbox, to prove that the identity cannot send as it")
        if name == "apply":
            sub.add_argument("--apply", action="store_true", help="send the cmdlets (the default is a dry run)")
    return parser


def main(argv=None, *, az: Callable[[list[str]], tuple[int, str, str]] = run_az, transport: Http = default_http, env: Mapping[str, str] | None = None,
         out: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep, new_id: Callable[[], str] = lambda: str(uuid.uuid4())) -> int:
    env = os.environ if env is None else env
    args = build_parser().parse_args(argv)
    hide = Hider()
    try:
        if env.get("GITHUB_ACTIONS", "").strip().lower() in ("true", "1"):
            raise Problem("a person with the right to administer Exchange Online runs this, never a pipeline (AGENTS.md rules 18 and 24)")
        cfg = read_config(args)
        tokens = Tokens(az, cfg.tenant, hide)
        say = lambda text: out(hide(text))  # noqa: E731
        ex, graph = Exchange(cfg.tenant, cfg.domain, tokens, transport, sleep, new_id), Graph(tokens, transport, sleep)
        code = command_check(ex, graph, cfg, say) if args.command == "check" else command_apply(ex, graph, cfg, say, bool(args.apply))
        say(NOT_COVERED)
        return code
    except Problem as e:
        print(f"error: {hide(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
