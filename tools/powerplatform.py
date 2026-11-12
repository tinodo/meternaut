#!/usr/bin/env python3
"""The Power Platform side of the Teams cards: look at the environments, make one, make it a Managed Environment, link the project's enterprise policy to it, and unlink it (standard library only).

    python tools/powerplatform.py status [--environment <name or id>] [--subscription <id> --resource-group <name>] [--policy-name <name>]
    python tools/powerplatform.py create-environment --name <display name> [--sku Developer|Sandbox] [--domain-name <name>] [--apply] [--yes]
    python tools/powerplatform.py managed --environment <name or id> [--apply] [--yes]
    python tools/powerplatform.py link --environment <name or id> --subscription <id> --resource-group <name> [--policy-name <name>] [--apply] [--yes]
    python tools/powerplatform.py unlink --environment <name or id> --subscription <id> --resource-group <name> [--policy-name <name>] [--apply] [--yes]
    python tools/powerplatform.py steps [--subscription <id>] [--resource-group <name>] [--storage-account <name>] [--environment <name>] [--person <object id>]
    python tools/powerplatform.py connections --environment <name or id> [--apply] [--yes]
    python tools/powerplatform.py flow --environment <name or id> --storage-account <name> [--queue <name>] [--posted-queue <name>] [--apply] [--yes]
    python tools/powerplatform.py flow-runs --environment <name or id> [--last <1 to 20>]
    python tools/powerplatform.py test-card --environment <name or id> --storage-account <name> --to <mail address> [--queue <name>] [--apply] [--yes]
    python tools/powerplatform.py test-close --environment <name or id> --to <mail address> [--apply] [--yes]

Why. Teams cards reach people through a Power Automate flow that reads the Storage queue `teams-cards` over Power Platform virtual network support: the flow's Azure Queues connector runs in a subnet of the
project's own virtual network (environment/powerplatform/main.bicep), so the storage account needs no public endpoint, and no key and no app registration is involved (docs/proposals/19-teams-cards-through-power-automate.md).
The Azure side is made by the Hub. What the Hub cannot make is in Power Platform, which is not Azure Resource Manager and has its own control plane (the Business Application Platform, BAP): the environment, its
Managed Environment setting, and the link between it and the enterprise policy. This tool makes those, with the sign-in of the person who runs it and nothing else.

How it signs in, and what it will not do. It asks the Azure CLI of the person who runs it for a token (`az account get-access-token`, for https://service.powerapps.com/ and for Azure Resource Manager) and keeps it in
memory. No credential is stored, read from a file or taken from the command line, and a token is taken out of everything that is printed. The person needs the Power Platform Administrator role in Microsoft Entra,
and Reader on the enterprise policy (docs/proposals/19-teams-cards-through-power-automate.md: the command that gives it). It never runs in a pipeline (AGENTS.md rules 18 and 24: its output names environments and policies of the
estate, which a log must not hold, and the deploy identity holds no right in Power Platform), and it sends only the calls of CALLS below: a read of Azure Resource Manager is the only thing it does to Azure, and it
changes nothing there. It deletes nothing, except the one test flow that `test-card` or `test-close` made a moment before.

status               Read only. Without --environment, the environments that the signed-in person sees (name, region, type, Managed Environment, state, linked policy). With one, what it takes to
                     link it: its region, type, Managed Environment setting and linked policy, the project's policy in Azure (kind, geography, virtual network, subnet, delegation), and whether they are linked.
create-environment   A dry run. With --apply, makes the environment (location sweden, Dataverse, euro, English) and waits until it is Ready (the BAP call and body are the ones of the reference repository
                     tinodo/secure-request-classifier, MIT, scripts/New-PowerPlatformEnvironment.ps1). An environment of that name that exists is left alone. The Developer plan: Learn, 2026-11-11, says that from
                     15 November 2026 an unmanaged developer environment cannot be made and that every developer environment has to be a Managed Environment, which needs a premium licence of the person
                     who runs flows in it, so `managed` follows at once.
managed              A dry run. With --apply, turns Managed Environments on (the body that Learn gives: protectionLevel Standard and no extended settings), which virtual network support requires.
link                 Checks first, and stops at the first check that fails: the environment exists, is in the geography Sweden, is a type that supports virtual network support (not a trial, not Dataverse for
                     Teams), is a Managed Environment and is not linked to another policy; the policy can be read (otherwise the Reader role is missing), is a NetworkInjection policy for the same geography with one
                     virtual network, and its subnet is delegated to Microsoft.PowerPlatform/enterprisePolicies and has room. A dry run, unless --apply: it then asks for a yes (or takes --yes), links, waits for the
                     operation and reads the environment again.
unlink               The same, the other way: only the project's own policy is unlinked, the person confirms, and the environment is read again.
steps                Prints, in order, every step that a person does by hand, with the commands: the Hub actions, the roles, the Teams admin center setting for the Workflows app, the environment, the link, the import of the solution, the two connections, the three environment
                     variables, turning the flow on, and the first card. It sends nothing. The import is left to the maker portal: the Dataverse call for it (ImportSolutionAsync) takes the
                     connection references and the values of the environment variables as a collection of entities that the Web API reference does not show an example of, so it is not written here.
connections          For a person whom the maker portal refuses (a guest of the tenant: new Dataverse environments refuse guests, and the admin center does not take a guest at all), and for anyone who would rather not click. A dry run says
                     which of the two connections of the flow (Azure Queues with Microsoft Entra ID, and Microsoft Teams) are connected, made and not signed in, or not made. With --apply it makes the ones that are not
                     made, with the signed-in person's own token, and prints the address at which the person signs in to each (the platform's own consent page: the person ticks a box and allows). The addresses are good for
                     about 15 minutes. It stores nothing, and the connections belong to the person.
flow                 With the two connections connected: a dry run, or, with --apply, makes the flow `Meternaut cards` from the definition of the unpacked solution (the one that tools/powerplatform-pack.py packs) with the
                     address of the queue of the cards, its name and the name of the queue of the posted cards, started; a flow of that name that is there is updated, never made twice, and two of that name are left alone. It is not a
                     solution: it is one of the person's own flows.
flow-runs            Read only: the last runs of that flow and, for a failed one, the actions that failed. The code of a failed run says which: CardNotPosted, PostedMessageNotWritten, CardNotUpdated or MessageCannotBeRead.
test-card            A dry run, or, with --apply, makes a flow with a button that puts one test card on the queue, runs it once, says where the card is, and deletes that flow (the only thing the tool ever deletes, and only
                     the one it made a moment before). The signed-in person needs Storage Queue Data Message Sender on the queue while it runs: without it the queue answers `AuthorizationPermissionMismatch` and the tool says so.
test-close           The same for the step that replaces a card: the test flow posts a test card as the Flow bot with the step of the flow `Meternaut cards`, waits ten seconds and replaces it with a card that has no button, with
                     that flow's own step and fields. No queue is involved: only the Microsoft Teams connection is needed. It proves the names of the fields of the step, which no document shows.

On 2026-11-11 the commands status, create-environment, managed, link, connections, flow, flow-runs and test-card ran against the owner's tenant, and a card reached a Teams chat. test-close, the queue of the posted
cards and the step that replaces a card were added later and have not run there yet. The calls follow the owner's reference repository
(scripts/Set-PowerPlatformSubnetInjection.ps1, New-PowerPlatformEnvironment.ps1 and Resolve-PowerPlatformEnvironment.ps1), Microsoft's own module (microsoft/PowerPlatform-EnterprisePolicies,
Source/Common/EnvironmentOperations.ps1) and the calls that the maker portal makes. The tests run it against a fake of those calls and of nothing else. Enabling or disabling the delegation can leave
connections unstable for up to 30 minutes (Learn): the tool says so before it links.
"""
from __future__ import annotations

import argparse
import copy
import http.client
import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

BAP = "https://api.bap.microsoft.com"
BAP_AUDIENCE = "https://service.powerapps.com/"
POWERAPPS = "https://api.powerapps.com"  # the connections of an environment; it takes the same token as the BAP
FLOW = "https://api.flow.microsoft.com"  # the flows of an environment
FLOW_AUDIENCE = "https://service.flow.microsoft.com/"
ARM = "https://management.azure.com"
ARM_AUDIENCE = "https://management.azure.com/"
ENVIRONMENTS_API = "2021-04-01"   # list, read, create and the governance configuration of an environment (the reference's calls)
LINK_API = "2019-10-01"           # link and unlink of an enterprise policy (Microsoft's module: EnvironmentOperations.ps1)
POLICY_API = "2020-10-30-preview"  # the version of the enterprise policy that environment/powerplatform/main.bicep writes
SUBNET_API = "2025-05-01"
APPS_API = "2016-11-01"           # connections and flows (the version that the maker portal itself calls, 2026-11-11)
# The project's own, as environment/powerplatform/main.bicep and tools/environment-params.py make them (a test holds the three together).
DEFAULT_POLICY_NAME = "ep-meternaut-netinjection"
GEOGRAPHY = "sweden"
AZURE_REGION = "swedencentral"
DELEGATION = "Microsoft.PowerPlatform/enterprisePolicies"
QUEUE_NAME = "teams-cards"
POSTED_QUEUE_NAME = "teams-posted"
FLOW_NAME = "Meternaut cards"
TEST_FLOW_NAME = "Meternaut test card (made by tools/powerplatform.py, deleted at once)"
# The two connectors of the flow: (api name, what it is called, the connection parameter set of Microsoft Entra ID sign-in or None).
CONNECTORS = (("shared_azurequeues", "Azure Queues (Microsoft Entra ID Integrated)", "tokenBasedAuth", "Premium"), ("shared_teams", "Microsoft Teams", None, "Standard"))
ENDPOINT_PARAMETER = "Storage queue endpoint (mtnaut_StorageQueueEndpoint)"  # the three values of the flow, named as the packed solution names its environment variables
QUEUE_PARAMETER = "Queue name (mtnaut_QueueName)"
POSTED_PARAMETER = "Posted queue name (mtnaut_PostedQueueName)"
POST_ACTION, UPDATE_ACTION = "Post_card_in_a_chat_or_channel", "Update_an_adaptive_card_in_a_chat_or_channel"  # the two Teams steps of the flow, which test-close copies
STORAGE_ACCOUNT_RE = re.compile(r"^[a-z0-9]{3,24}$")
QUEUE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
MAIL_RE = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,}$")
CONSENT_RETURN = "https://example.com/"  # where the browser lands after the person allows a connection: nothing is passed to it (seen on 2026-11-11), and IANA owns it
SKUS_CREATED = ("Developer", "Sandbox")
# The types of environment that virtual network support covers (Learn, "Supported environments"): not Trial, not Microsoft Dataverse for Teams.
SKUS_SUPPORTED = ("Production", "Default", "Sandbox", "Developer")
CURRENCY = "EUR"
LANGUAGE = 1033
# Least usable addresses: a /28 is 16, and Azure keeps five of every subnet. An environment that is not production needs 6 to 10 (Learn, "Estimating subnet size for Power Platform environments").
LEAST_USABLE = 11
WAIT_SECONDS = 1800
# Role ids from Learn (built-in roles for Storage and for general use), read 2026-11-11.
ROLE_MESSAGE_PROCESSOR = "Storage Queue Data Message Processor"
ROLE_MESSAGE_SENDER = "Storage Queue Data Message Sender"

GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
GUID_RE = re.compile(rf"^{GUID}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,62}$")
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
RESOURCE_GROUP_RE = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
POLICY_RE = re.compile(r"^[A-Za-z0-9._-]{1,90}$")
BAP_PATH = r"/providers/Microsoft\.BusinessAppPlatform"
# The platform names the operation of a 202 on its regional host (unitedstates.api.bap.microsoft.com, seen on 2026-11-11), which is the same service and takes the same token: https, at most one label in front, no user, no port.
BAP_HOST_RE = re.compile(r"^(?:[a-z0-9-]+\.)?api\.bap\.microsoft\.com$")
APPS_QUERY = rf"api-version={APPS_API}&\$filter=environment%20eq%20%27{GUID}%27"
CONNECTION = rf"{re.escape(POWERAPPS)}/providers/Microsoft\.PowerApps/apis/shared_(?:azurequeues|teams)/connections/[0-9a-f]{{32}}"
FLOWS = rf"{re.escape(FLOW)}/providers/Microsoft\.ProcessSimple/environments/{GUID}/flows"
# (method, a pattern of the whole address): everything that this tool may send. Azure Resource Manager is only ever read.
CALLS = (
    ("GET", re.compile(rf"^{re.escape(BAP)}{BAP_PATH}/(?:scopes/admin/)?environments(?:\?[^#]*)?$")),
    ("GET", re.compile(rf"^{re.escape(BAP)}{BAP_PATH}/(?:scopes/admin/)?environments/{GUID}(?:\?[^#]*)?$")),
    ("POST", re.compile(rf"^{re.escape(BAP)}{BAP_PATH}/environments\?api-version={ENVIRONMENTS_API}$")),
    ("POST", re.compile(rf"^{re.escape(BAP)}{BAP_PATH}/environments/{GUID}/governanceConfiguration\?api-version={ENVIRONMENTS_API}$")),
    ("POST", re.compile(rf"^{re.escape(BAP)}{BAP_PATH}/environments/{GUID}/enterprisePolicies/NetworkInjection/(?:link|unlink)\?api-version={LINK_API}$")),
    ("GET", re.compile(rf"^https://(?:[a-z0-9-]+\.)?api\.bap\.microsoft\.com{BAP_PATH}/[^#]*$")),   # the operation that a 202 names: on the host of the platform or on its regional host
    ("GET", re.compile(rf"^{re.escape(POWERAPPS)}/providers/Microsoft\.PowerApps/connections\?{APPS_QUERY}$")),
    ("GET", re.compile(rf"^{CONNECTION}\?{APPS_QUERY}$")),
    ("PUT", re.compile(rf"^{CONNECTION}\?{APPS_QUERY}$")),
    ("POST", re.compile(rf"^{CONNECTION}/getConsentLink\?{APPS_QUERY}$")),
    ("GET", re.compile(rf"^{FLOWS}\?api-version={APPS_API}$")),
    ("POST", re.compile(rf"^{FLOWS}\?api-version={APPS_API}$")),
    ("PATCH", re.compile(rf"^{FLOWS}/{GUID}\?api-version={APPS_API}$")),
    ("DELETE", re.compile(rf"^{FLOWS}/{GUID}\?api-version={APPS_API}$")),   # only the test flow that `test-card` made a moment before
    ("POST", re.compile(rf"^{FLOWS}/{GUID}/triggers/manual/run\?api-version={APPS_API}$")),
    ("GET", re.compile(rf"^{FLOWS}/{GUID}/runs\?api-version={APPS_API}$")),
    ("GET", re.compile(rf"^{FLOWS}/{GUID}/runs/[0-9A-Za-z]+\?api-version={APPS_API}&\$expand=properties/actions$")),
    ("GET", re.compile(rf"^{re.escape(ARM)}/subscriptions/{GUID}/resourceGroups/[A-Za-z0-9._()-]+/providers/Microsoft\.PowerPlatform/enterprisePolicies/[A-Za-z0-9._-]+\?api-version={POLICY_API}$")),
    ("GET", re.compile(rf"^{re.escape(ARM)}/subscriptions/{GUID}/resourceGroups/[A-Za-z0-9._()-]+/providers/Microsoft\.Network/virtualNetworks/[A-Za-z0-9._-]+/subnets/[A-Za-z0-9._-]+\?api-version={SUBNET_API}$")),
)
TOKEN_SHAPES = (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}"), re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"))
HIDDEN = "[token hidden]"

Http = Callable[[str, str, Mapping[str, str], "bytes | None"], "tuple[int, Mapping[str, str], bytes]"]


def on_bap_host(url: str) -> bool:
    """Whether an address is on the host of the Business Application Platform or on its regional host, over https, and nowhere else: the token goes nowhere else."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and bool(BAP_HOST_RE.match(parts.netloc))


def audience_of(url: str) -> str | None:
    """The audience of the token that an address takes, or None when the address is not one of the four hosts that this tool talks to (https only)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        return None
    if on_bap_host(url) or parts.netloc == urllib.parse.urlsplit(POWERAPPS).netloc:
        return BAP_AUDIENCE
    if parts.netloc == urllib.parse.urlsplit(FLOW).netloc:
        return FLOW_AUDIENCE
    if parts.netloc == urllib.parse.urlsplit(ARM).netloc:
        return ARM_AUDIENCE
    return None


class Problem(Exception):
    """Something the person who runs the tool can fix or must know; printed without a trace."""


# ---- the Azure CLI and its tokens ---------------------------------------------------------------------------------------------------------------

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
    """The access token of the signed-in person's Azure CLI for one audience, asked for once and kept in memory only."""

    def __init__(self, runner: Callable[[list[str]], tuple[int, str, str]], hide: Hider) -> None:
        self.runner, self.hide, self.tokens = runner, hide, {}

    def __call__(self, audience: str) -> str:
        if audience not in self.tokens:
            code, out, err = self.runner(["account", "get-access-token", "--resource", audience, "--query", "accessToken", "--output", "tsv"])
            token = out.strip()
            if code != 0 or not token:
                raise Problem(f"the Azure CLI gave no token for {audience}: {first_line(err)}. Sign in with `az login` as the person who administers Power Platform")
            self.hide.add(token)
            self.tokens[audience] = token
        return self.tokens[audience]


# ---- the calls -----------------------------------------------------------------------------------------------------------------------------------

def default_http(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (the address is one of the two hosts above)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        raise Problem(f"no answer from {urllib.parse.urlsplit(url).netloc} ({type(e).__name__})") from e


@dataclass(frozen=True)
class Answer:
    status: int
    headers: Mapping[str, str]
    body: object  # the parsed JSON, or None when there is none
    text: str

    def header(self, name: str) -> str:
        return next((v for k, v in self.headers.items() if k.lower() == name.lower()), "")


def message_of(answer: Answer) -> str:
    """What an error answer says, on one line: the code and the message of a BAP or Azure Resource Manager error."""
    body = answer.body
    if isinstance(body, dict):
        error = body.get("error") if isinstance(body.get("error"), dict) else body
        code = str(error.get("code") or "")
        message = " ".join(str(error.get("message") or "").split())
        if code or message:
            return f"{code}: {message}".strip(": ")[:400]
    return " ".join((answer.text or "").split())[:400] or f"HTTP {answer.status}"


class Client:
    """Calls to Power Platform and to Azure Resource Manager with the signed-in person's token. Only the calls of CALLS can be sent."""

    def __init__(self, tokens: Tokens, transport: Http = default_http, sleep: Callable[[float], None] = time.sleep) -> None:
        self.tokens, self.transport, self.sleep = tokens, transport, sleep

    def send(self, method: str, url: str, body: dict | None = None) -> Answer:
        host = urllib.parse.urlsplit(url).netloc
        audience = audience_of(url)
        if url.split("?", 1)[0].count("://") != 1 or audience is None:
            raise Problem(f"{host or url} is not a host that this tool talks to: the token goes nowhere else")
        if not any(m == method and p.match(url) for m, p in CALLS):
            raise Problem(f"{method} {url.split('?', 1)[0]} is not one of the calls that this tool sends")
        headers = {"Authorization": f"Bearer {self.tokens(audience)}", "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        for attempt in (1, 2):
            status, answer_headers, raw = self.transport(method, url, headers, data)
            if status in (429, 503) and attempt == 1:
                self.sleep(retry_after(answer_headers, 5))
                continue
            break
        text = raw.decode("utf-8", "replace")
        try:
            parsed = json.loads(text) if text.strip() else None
        except ValueError:
            parsed = None
        return Answer(status, answer_headers, parsed, text)


def retry_after(headers: Mapping[str, str], default: float) -> float:
    given = next((v for k, v in headers.items() if k.lower() == "retry-after"), "")
    try:
        return min(60.0, max(1.0, float(given)))
    except ValueError:
        return default


def pick(node: object, *keys: str) -> object:
    """A value of nested JSON, with the names of the keys matched without regard to case (the service writes VNets, and a script reads vNets)."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        found = next((v for k, v in node.items() if k.lower() == key.lower()), None)
        node = found
    return node


# ---- environments --------------------------------------------------------------------------------------------------------------------------------

def list_environments(client: Client) -> tuple[list[dict], bool]:
    """The environments that the signed-in person sees, and whether they are all of the tenant's (the admin scope) or only the person's own (the maker scope, when the admin scope refuses)."""
    expand = urllib.parse.quote("properties.enterprisePolicies", safe=".")
    query = f"api-version={ENVIRONMENTS_API}&$expand={expand}"
    for admin, scope in ((True, "scopes/admin/"), (False, "")):
        answer = client.send("GET", f"{BAP}/providers/Microsoft.BusinessAppPlatform/{scope}environments?{query}")
        if answer.status == 200 and isinstance(answer.body, dict):
            return [e for e in answer.body.get("value") or [] if isinstance(e, dict)], admin
        if answer.status not in (401, 403) or not admin:
            raise Problem(f"the list of environments was refused: {message_of(answer)}")
    raise AssertionError("unreachable")


def read_environment(client: Client, environment_id: str) -> dict:
    expand = urllib.parse.quote("properties.enterprisePolicies", safe=".")
    last = None
    for scope in ("scopes/admin/", ""):
        answer = client.send("GET", f"{BAP}/providers/Microsoft.BusinessAppPlatform/{scope}environments/{environment_id}?api-version={ENVIRONMENTS_API}&$expand={expand}")
        if answer.status == 200 and isinstance(answer.body, dict):
            return answer.body
        last = answer
        if answer.status not in (401, 403, 404):
            break
    raise Problem(f"the environment could not be read: {message_of(last) if last else 'no answer'}")


def resolve_environment(client: Client, reference: str) -> dict:
    """The environment that a name or an id stands for, read in full. A name that two environments have is refused: the tool changes nothing on a guess."""
    if GUID_RE.match(reference):
        return read_environment(client, reference)
    found, _ = list_environments(client)
    matches = [e for e in found if str((e.get("properties") or {}).get("displayName", "")).lower() == reference.lower()]
    if not matches:
        raise Problem(f"no environment is named {reference!r} for this sign-in (`status` lists the ones that it sees)")
    if len(matches) > 1:
        raise Problem(f"{len(matches)} environments are named {reference!r}: give the id of the one that is meant (`status` shows the ids)")
    return read_environment(client, str(matches[0].get("name")))


def facts(environment: dict) -> dict[str, object]:
    """What the tool reads of an environment, in one place."""
    properties = environment.get("properties") or {}
    metadata = properties.get("linkedEnvironmentMetadata") or {}
    linked = pick(properties, "enterprisePolicies", "vnets")
    return {
        "id": str(environment.get("name") or ""),
        "name": str(properties.get("displayName") or ""),
        "location": str(environment.get("location") or ""),
        "region": str(properties.get("azureRegion") or ""),
        "sku": str(properties.get("environmentSku") or ""),
        "managed": str(pick(properties, "governanceConfiguration", "protectionLevel") or "Basic"),
        "state": str(properties.get("provisioningState") or ""),
        "management": str(pick(properties, "states", "management", "id") or ""),
        "instance": str(metadata.get("instanceUrl") or ""),
        "tenant": str(properties.get("tenantId") or ""),
        "policy": str(pick(linked, "id") or ""),
        "link_status": str(pick(linked, "linkStatus") or ""),
    }


def short(policy_id: str) -> str:
    return policy_id.rstrip("/").rsplit("/", 1)[-1] if policy_id else ""


def policy_id_of(subscription: str, group: str, name: str) -> str:
    return f"/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.PowerPlatform/enterprisePolicies/{name}"


def same(a: str, b: str) -> bool:
    return a.strip("/").lower() == b.strip("/").lower()


# ---- the project's policy in Azure ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    id: str
    kind: str
    geography: str
    system_id: str
    networks: tuple[tuple[str, str], ...]  # (virtual network id, subnet name)


def read_policy(client: Client, subscription: str, group: str, name: str) -> Policy:
    answer = client.send("GET", f"{ARM}{policy_id_of(subscription, group, name)}?api-version={POLICY_API}")
    if answer.status in (401, 403):
        raise Problem(f"the policy {name} cannot be read with this sign-in ({message_of(answer)}). The person who links needs Reader on it, which a person who may give roles gives: "
                      f"az role assignment create --assignee-object-id <object id of the person> --assignee-principal-type User --role Reader --scope {policy_id_of(subscription, group, name)}")
    if answer.status == 404:
        raise Problem(f"the policy {name} is not in resource group {group} of that subscription: the Hub action powerplatform makes it")
    if answer.status != 200 or not isinstance(answer.body, dict):
        raise Problem(f"the policy {name} could not be read: {message_of(answer)}")
    body = answer.body
    properties = body.get("properties") or {}
    networks = tuple((str(n.get("id") or ""), str(pick(n, "subnet", "name") or "")) for n in (pick(properties, "networkInjection", "virtualNetworks") or []) if isinstance(n, dict))
    return Policy(str(body.get("id") or ""), str(body.get("kind") or ""), str(body.get("location") or ""), str(properties.get("systemId") or ""), networks)


def read_subnet(client: Client, network_id: str, subnet: str) -> dict:
    match = re.match(rf"^/subscriptions/({GUID})/resourceGroups/([A-Za-z0-9._()-]+)/providers/Microsoft\.Network/virtualNetworks/([A-Za-z0-9._-]+)$", network_id, re.I)
    if not match or not re.match(r"^[A-Za-z0-9._-]+$", subnet):
        raise Problem("the policy names a virtual network that is not an Azure resource id of this tool's kind")
    answer = client.send("GET", f"{ARM}/subscriptions/{match.group(1)}/resourceGroups/{match.group(2)}/providers/Microsoft.Network/virtualNetworks/{match.group(3)}/subnets/{subnet}?api-version={SUBNET_API}")
    if answer.status != 200 or not isinstance(answer.body, dict):
        raise Problem(f"the subnet {subnet} could not be read: {message_of(answer)}")
    return answer.body


def usable_addresses(prefix: str) -> int:
    """The addresses of a subnet that a workload can use: Azure keeps five."""
    match = re.match(r"^\d{1,3}(?:\.\d{1,3}){3}/(\d{1,2})$", prefix)
    return (2 ** (32 - int(match.group(1)))) - 5 if match and int(match.group(1)) <= 32 else 0


# ---- the output ----------------------------------------------------------------------------------------------------------------------------------

def table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return ["  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows]


def linked_text(f: dict[str, object], mine: str) -> str:
    policy = str(f["policy"])
    if not policy:
        return "none"
    return f"{short(policy)}{' (this project)' if mine and same(policy, mine) else ''}{' [' + str(f['link_status']) + ']' if f['link_status'] else ''}"


def command_status(args: argparse.Namespace, client: Client, out: Callable[[str], None]) -> int:
    mine = policy_id_of(args.subscription, args.resource_group, args.policy_name) if args.subscription and args.resource_group else ""
    found, admin = list_environments(client)
    out(f"{len(found)} environment(s) that this sign-in sees ({'every environment of the tenant' if admin else 'only its own: the sign-in is not a Power Platform administrator'}):")
    rows = [["name", "region", "type", "managed", "state", "linked policy"]]
    for environment in sorted(found, key=lambda e: str((e.get("properties") or {}).get("displayName", "")).lower()):
        f = facts(environment)
        rows.append([str(f["name"]), f"{f['location']} ({f['region'] or '?'})", str(f["sku"]), str(f["managed"]), str(f["state"]), linked_text(f, mine)])
    for line in table(rows):
        out(line)
    if not args.environment:
        return 0
    f = facts(resolve_environment(client, args.environment))
    out("")
    out(f"The environment {f['name']} (id {f['id']}):")
    out(f"  region: {f['location']} ({f['region'] or 'not reported'}); type: {f['sku']}; Managed Environment: {f['managed']}; state: {f['state']}, {f['management'] or 'no management state'}")
    out(f"  linked enterprise policy: {linked_text(f, mine)}")
    if not (args.subscription and args.resource_group):
        out("  Give --subscription and --resource-group to read the project's policy in Azure and to say whether it is the one that is linked.")
        return 0
    try:
        policy = read_policy(client, args.subscription, args.resource_group, args.policy_name)
    except Problem as e:
        out(f"  the project's policy {args.policy_name}: {e}")
        return 1
    out(f"  the project's policy {args.policy_name}: kind {policy.kind}, geography {policy.geography}, {len(policy.networks)} virtual network(s)")
    for network, subnet in policy.networks:
        try:
            read = read_subnet(client, network, subnet)
        except Problem as e:
            out(f"    subnet {subnet}: {e}")
            continue
        properties = read.get("properties") or {}
        delegations = sorted({str(pick(d, "properties", "serviceName") or "") for d in properties.get("delegations") or []})
        out(f"    subnet {subnet}: {properties.get('addressPrefix', 'no range')}, delegated to {', '.join(delegations) or 'nothing'}")
    linked = bool(f["policy"]) and same(str(f["policy"]), mine)
    out(f"  linked to the project's policy: {'YES' if linked else 'NO'}" + ("" if linked or not f["policy"] else f" (it is linked to {short(str(f['policy']))})"))
    return 0


# ---- waiting for an operation --------------------------------------------------------------------------------------------------------------------

def wait_for_operation(client: Client, url: str, label: str, out: Callable[[str], None], timeout: float, clock: Callable[[], float]) -> dict:
    """Polls the operation that a 202 named, until it ends. The address has to be on the BAP host or its regional host: the token goes nowhere else."""
    if not on_bap_host(url):
        raise Problem(f"the operation of {label} is at {urllib.parse.urlsplit(url).netloc or url}, which is not the Business Application Platform: it is not followed")
    deadline = clock() + timeout
    last = ""
    while clock() < deadline:
        answer = client.send("GET", url)
        if answer.status not in (200, 202) or not isinstance(answer.body, dict):
            raise Problem(f"{label}: the operation could not be read: {message_of(answer)}")
        state = str(pick(answer.body, "state", "id") or "")
        if state != last:
            out(f"  {label}: {state or 'no state'}")
            last = state
        if state == "Succeeded":
            return answer.body
        if state == "Failed":
            error = pick(answer.body, "error")
            detail = " ".join(str(pick(error, "message") or "").split()) if error else ""
            raise Problem(f"{label} failed: {detail or 'no detail was returned'}")
        client.sleep(retry_after(answer.headers, 15))
    raise Problem(f"{label} did not end in {int(timeout // 60)} minutes: look at its history in the Power Platform admin center before anything is run again")


def confirm(args: argparse.Namespace, prompt: str, ask: Callable[[str], "str | None"]) -> None:
    if args.yes:
        return
    answer = ask(prompt + " Type yes: ")
    if answer is None:
        raise Problem("--apply needs --yes when there is no terminal to ask in")
    if answer.strip().lower() != "yes":
        raise Problem("nothing was changed")


# ---- create-environment --------------------------------------------------------------------------------------------------------------------------

def domain_of(name: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", name.lower())).strip("-")[:32]


def creation_body(args: argparse.Namespace) -> dict:
    return {
        "location": args.region,
        "properties": {
            "displayName": args.name,
            "description": "Made by tools/powerplatform.py for the Meternaut Teams cards.",
            "environmentSku": args.sku,
            "databaseType": "CommonDataService",
            "linkedEnvironmentMetadata": {"baseLanguage": LANGUAGE, "currency": {"code": CURRENCY}, "domainName": args.domain_name or domain_of(args.name)},
        },
    }


def wait_until_ready(client: Client, environment_id: str, out: Callable[[str], None], timeout: float, clock: Callable[[], float]) -> dict:
    deadline = clock() + timeout
    last = ""
    while clock() < deadline:
        f = facts(read_environment(client, environment_id))
        shown = f"{f['state'] or 'no state'}, {f['management'] or 'no management state'}, {'Dataverse is there' if f['instance'] else 'no Dataverse yet'}"
        if shown != last:
            out(f"  {shown}")
            last = shown
        if f["state"] == "Failed":
            raise Problem(f"the environment {f['name']} reached the state Failed: look at its history in the Power Platform admin center")
        if f["state"] == "Succeeded" and f["management"] == "Ready" and f["instance"]:
            return f
        client.sleep(15)
    raise Problem(f"the environment was not Ready in {int(timeout // 60)} minutes: look at it in the Power Platform admin center before anything is run again")


def command_create(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"], clock: Callable[[], float]) -> int:
    found, _ = list_environments(client)
    same_name = [facts(e) for e in found if str((e.get("properties") or {}).get("displayName", "")).lower() == args.name.lower()]
    if same_name:
        f = same_name[0]
        out(f"An environment named {args.name} exists already (type {f['sku']}, {f['location']}, Managed Environment {f['managed']}). Nothing is made.")
        if len(same_name) > 1:
            out(f"  {len(same_name)} environments have that name: the other commands then need the id.")
        return 0
    body = creation_body(args)
    out(f"Would make the environment {args.name}: type {args.sku}, location {args.region}, Dataverse, {CURRENCY}, language {LANGUAGE}, domain {body['properties']['linkedEnvironmentMetadata']['domainName']}.")
    if args.sku == "Developer":
        out("  The Developer plan (Learn, read 2026-11-11): only the owner of the environment may use it, it is for development and test, and from 15 November 2026 an unmanaged developer environment can not be made: "
            "run `managed` straight after, and note that a Managed Environment needs a premium licence for the person who runs flows in it.")
    if not args.apply:
        out("This was a dry run. Run again with --apply to make it.")
        return 0
    confirm(args, f"Make the environment {args.name}?", ask)
    answer = client.send("POST", f"{BAP}/providers/Microsoft.BusinessAppPlatform/environments?api-version={ENVIRONMENTS_API}", body)
    if answer.status not in (200, 201, 202):
        raise Problem(f"the environment was not made: {message_of(answer)}")
    if answer.status == 202:
        location = answer.header("location") or answer.header("operation-location")
        if not location:
            raise Problem("the request was accepted and named no operation to follow: look at the Power Platform admin center before it is run again")
        operation = wait_for_operation(client, location, "making the environment", out, WAIT_SECONDS, clock)
        path = str(pick(operation, "links", "environment", "path") or "")
        environment_id = path.rstrip("/").rsplit("/", 1)[-1]
    else:
        environment_id = str((answer.body or {}).get("name") or "") if isinstance(answer.body, dict) else ""
    if not GUID_RE.match(environment_id):
        raise Problem("the operation ended and did not name the environment: find it with `status`")
    f = wait_until_ready(client, environment_id, out, WAIT_SECONDS, clock)
    out(f"The environment {f['name']} is Ready (id {f['id']}, type {f['sku']}, Managed Environment {f['managed']}).")
    out("Next: `managed` (virtual network support needs it), then `link`.")
    return 0


# ---- managed -------------------------------------------------------------------------------------------------------------------------------------

def command_managed(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"]) -> int:
    f = facts(resolve_environment(client, args.environment))
    out(f"The environment {f['name']} (id {f['id']}): type {f['sku']}, Managed Environment {f['managed']}.")
    if f["managed"] == "Standard":
        out("It is a Managed Environment already. Nothing is changed.")
        return 0
    if f["sku"] not in SKUS_SUPPORTED:
        raise Problem(f"a {f['sku'] or 'type unknown'} environment does not support virtual network support (Learn: Production, Default, Sandbox and Developer do), so it is not made a Managed Environment for that")
    out("Would turn Managed Environments on (protectionLevel Standard, no extended settings). Its use rights are not in the Developer plan: whoever runs a flow in it needs a premium licence "
        "(https://learn.microsoft.com/power-platform/admin/managed-environment-licensing).")
    if not args.apply:
        out("This was a dry run. Run again with --apply to turn it on.")
        return 0
    confirm(args, f"Make {f['name']} a Managed Environment?", ask)
    body = {"protectionLevel": "Standard", "settings": {"extendedSettings": {}}}
    answer = client.send("POST", f"{BAP}/providers/Microsoft.BusinessAppPlatform/environments/{f['id']}/governanceConfiguration?api-version={ENVIRONMENTS_API}", body)
    if answer.status not in (200, 201, 202, 204):
        raise Problem(f"Managed Environments was not turned on: {message_of(answer)}")
    after = facts(read_environment(client, str(f["id"])))
    out(f"Read again: Managed Environment {after['managed']}.")
    return 0 if after["managed"] == "Standard" else 1


# ---- link and unlink -----------------------------------------------------------------------------------------------------------------------------

def checks_for_link(client: Client, f: dict[str, object], args: argparse.Namespace, out: Callable[[str], None]) -> Policy:
    """Every check before the link; the first that fails stops it, with what to do. Returns the policy."""
    mine = policy_id_of(args.subscription, args.resource_group, args.policy_name)

    def ok(text: str) -> None:
        out(f"  ok  {text}")

    if f["location"].lower() != GEOGRAPHY:
        raise Problem(f"the environment is in {f['location'] or 'an unknown location'}, and the project's policy is for the geography {GEOGRAPHY}: only an environment of that geography can be linked")
    if f["region"] and f["region"].lower() != AZURE_REGION:
        raise Problem(f"the environment runs in {f['region']}, and the subnet is in {AZURE_REGION}: they have to be in the same region")
    ok(f"the environment is in the geography {GEOGRAPHY} ({f['region'] or 'region not reported'})")
    if f["sku"] not in SKUS_SUPPORTED:
        raise Problem(f"a {f['sku'] or 'type unknown'} environment does not support virtual network support (Learn: Production, Default, Sandbox and Developer do; not Trial, not Dataverse for Teams)")
    ok(f"the environment type {f['sku']} supports it")
    if f["managed"] != "Standard":
        raise Problem("the environment is not a Managed Environment, which virtual network support requires: run `managed` first")
    ok("the environment is a Managed Environment")
    if f["state"] != "Succeeded" or f["management"] not in ("Ready", ""):
        raise Problem(f"the environment is not ready ({f['state']}, {f['management']}): wait for it")
    policy = read_policy(client, args.subscription, args.resource_group, args.policy_name)
    ok(f"the policy {args.policy_name} can be read with this sign-in")
    if policy.kind != "NetworkInjection":
        raise Problem(f"the policy is of the kind {policy.kind or 'unknown'}, not NetworkInjection")
    if policy.geography.lower() != GEOGRAPHY:
        raise Problem(f"the policy is for the geography {policy.geography or 'unknown'}, not {GEOGRAPHY}")
    if len(policy.networks) != 1:
        raise Problem(f"the policy names {len(policy.networks)} virtual networks: the geography {GEOGRAPHY} has one Azure region, so it names one")
    if not policy.system_id:
        raise Problem("the policy has no systemId yet: it is still being made, run this again in a minute")
    ok("the policy is a NetworkInjection policy of the geography Sweden with one virtual network and a systemId")
    network, subnet = policy.networks[0]
    properties = read_subnet(client, network, subnet).get("properties") or {}
    delegations = [str(pick(d, "properties", "serviceName") or "") for d in properties.get("delegations") or []]
    if delegations != [DELEGATION]:
        raise Problem(f"the subnet {subnet} is delegated to {', '.join(delegations) or 'nothing'}, and has to be delegated to {DELEGATION} and to nothing else")
    if usable_addresses(str(properties.get("addressPrefix") or "")) < LEAST_USABLE:
        raise Problem(f"the subnet {subnet} has the range {properties.get('addressPrefix')}, which leaves fewer than {LEAST_USABLE} addresses: an environment that is not production needs 6 to 10 and Azure keeps five")
    ok(f"the subnet {subnet} ({properties.get('addressPrefix')}) is delegated to {DELEGATION}, and has room")
    return policy


def command_link(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"], clock: Callable[[], float], unlink: bool = False) -> int:
    mine = policy_id_of(args.subscription, args.resource_group, args.policy_name)
    f = facts(resolve_environment(client, args.environment))
    verb = "unlink" if unlink else "link"
    out(f"The environment {f['name']} (id {f['id']}), the project's policy {args.policy_name}:")
    if unlink:
        if not f["policy"]:
            out("  The environment is not linked to a policy. Nothing is changed.")
            return 0
        if not same(str(f["policy"]), mine):
            raise Problem(f"the environment is linked to {short(str(f['policy']))}, which is not the project's policy {args.policy_name}: this tool unlinks only its own")
        policy = read_policy(client, args.subscription, args.resource_group, args.policy_name)
        if not policy.system_id:
            raise Problem("the policy has no systemId: it cannot be named in the unlink")
        out("  ok  the environment is linked to the project's policy")
    else:
        if f["policy"] and same(str(f["policy"]), mine):
            out(f"  The environment is linked to the project's policy already{' [' + str(f['link_status']) + ']' if f['link_status'] else ''}. Nothing is changed.")
            return 0
        if f["policy"]:
            raise Problem(f"the environment is linked to {short(str(f['policy']))}: this tool does not swap a policy. Unlink it first, with the tool that linked it")
        out("  ok  the environment is not linked to any policy")
        policy = checks_for_link(client, f, args, out)
    out(f"Would {verb} the environment {'from' if unlink else 'to'} the policy: POST .../environments/<id>/enterprisePolicies/NetworkInjection/{verb} with the policy's systemId. Enabling or disabling the delegation "
        "can make connections unstable for up to 30 minutes (Learn, 'Set up virtual network support for Power Platform').")
    if not args.apply:
        out("This was a dry run. Run again with --apply to do it.")
        return 0
    confirm(args, f"{verb.capitalize()} {f['name']}?", ask)
    answer = client.send("POST", f"{BAP}/providers/Microsoft.BusinessAppPlatform/environments/{f['id']}/enterprisePolicies/NetworkInjection/{verb}?api-version={LINK_API}", {"SystemId": policy.system_id})
    if answer.status not in (200, 201, 202):
        raise Problem(f"the {verb} did not start: {message_of(answer)}")
    location = answer.header("operation-location")
    if location:
        try:
            wait_for_operation(client, location, f"the {verb}", out, WAIT_SECONDS, clock)
        except Problem as problem:
            raise Problem(f"{str(problem).rstrip('.')}. The {verb} itself was accepted: run `status`, which says what the environment shows now") from problem
    else:
        out(f"  the {verb} was accepted with no operation to follow (HTTP {answer.status})")
    after = facts(read_environment(client, str(f["id"])))
    linked = bool(after["policy"]) and same(str(after["policy"]), mine)
    if unlink:
        out("Read again: " + ("the environment is still linked." if linked else "the environment is not linked."))
        return 1 if linked else 0
    out("Read again: " + (f"the environment is linked to {args.policy_name}{' [' + str(after['link_status']) + ']' if after['link_status'] else ''}." if linked
                          else "the environment does not report the policy yet. It can take a few minutes to show: run `status` again, and look at the environment's History in the Power Platform admin center."))
    if linked:
        out("Connections can be unstable for up to 30 minutes. Next: import the solution (`steps`).")
    return 0 if linked else 1


# ---- the connections and the flow, by the platform's own API ---------------------------------------------------------------------------------------

# The maker portal refuses a person who is a guest of the tenant ("You are not permitted to make flows in this environment"): every new Dataverse environment refuses guests (Learn, "Control guest access to
# Microsoft Power Platform environments"), and the owner of the project is a guest (B2B) of the lab tenant that holds the subscription. The same calls that the portal makes are open to such a person, and this is
# how the two connections and the flow were made on 2026-11-11. Nothing is stored: the person's own token, the person's own connections, and the flow is the person's.

def apps_query(environment_id: str) -> str:
    return f"api-version={APPS_API}&$filter=" + urllib.parse.quote(f"environment eq '{environment_id}'", safe="")


def connection_url(api: str, name: str, environment_id: str, tail: str = "") -> str:
    return f"{POWERAPPS}/providers/Microsoft.PowerApps/apis/{api}/connections/{name}{tail}?{apps_query(environment_id)}"


def flows_url(environment_id: str, tail: str = "") -> str:
    return f"{FLOW}/providers/Microsoft.ProcessSimple/environments/{environment_id}/flows{tail}?api-version={APPS_API}"


def list_connections(client: Client, environment_id: str) -> list[dict]:
    answer = client.send("GET", f"{POWERAPPS}/providers/Microsoft.PowerApps/connections?{apps_query(environment_id)}")
    if answer.status != 200 or not isinstance(answer.body, dict):
        raise Problem(f"the connections could not be read: {message_of(answer)}")
    return [c for c in answer.body.get("value") or [] if isinstance(c, dict)]


def connector_of(connection: dict) -> str:
    return str(pick(connection, "properties", "apiId") or "").rstrip("/").rsplit("/", 1)[-1]


def connection_status(connection: dict) -> str:
    statuses = pick(connection, "properties", "statuses")
    first = statuses[0] if isinstance(statuses, list) and statuses and isinstance(statuses[0], dict) else {}
    return str(first.get("status") or "")


def connected_names(client: Client, environment_id: str, wanted: tuple[str, ...]) -> dict[str, str]:
    """The name of a connection that is signed in, for each connector that is wanted, or a Problem that says which one is not and what to run."""
    existing = list_connections(client, environment_id)
    names: dict[str, str] = {}
    for api in wanted:
        found = next((c for c in existing if connector_of(c) == api and connection_status(c) == "Connected"), None)
        label = next(label for a, label, _, _ in CONNECTORS if a == api)
        if found is None:
            raise Problem(f"the signed-in person has no connected connection for {label} in this environment: run `connections --apply` and open its sign-in address first")
        names[api] = str(found.get("name"))
    return names


def command_connections(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"]) -> int:
    f = facts(resolve_environment(client, args.environment))
    out(f"The environment {f['name']} (id {f['id']}): the connections of the signed-in person for the flow {FLOW_NAME}.")
    existing = list_connections(client, str(f["id"]))
    todo: list[tuple[str, str, str, str | None]] = []
    for api, label, parameter_set, _ in CONNECTORS:
        mine = [c for c in existing if connector_of(c) == api]
        if any(connection_status(c) == "Connected" for c in mine):
            out(f"  ok  {label}: connected")
            continue
        waiting = mine[0] if mine else None
        out(f"  --  {label}: " + ("made, and not signed in" if waiting else "not made"))
        todo.append((api, label, str(waiting.get("name")) if waiting else "", parameter_set))
    if not todo:
        out("Both are connected. Next: `flow --storage-account <name> --apply`.")
        return 0
    if not args.apply:
        out("This was a dry run. Run again with --apply to make what is not made and to get the address at which the person signs in.")
        return 0
    confirm(args, "Make the connections that are missing and get their sign-in addresses?", ask)
    environment = {"id": f"/providers/Microsoft.PowerApps/environments/{f['id']}", "name": f["id"]}
    for api, label, name, parameter_set in todo:
        if not name:
            name = secrets.token_hex(16)
            properties: dict = {"environment": environment}
            properties["connectionParametersSet" if parameter_set else "connectionParameters"] = {"name": parameter_set, "values": {}} if parameter_set else {}
            made = client.send("PUT", connection_url(api, name, str(f["id"])), {"properties": properties})
            if made.status not in (200, 201):
                raise Problem(f"the connection of {label} was not made: {message_of(made)}")
            out(f"  made the connection of {label}")
        answer = client.send("POST", connection_url(api, name, str(f["id"]), "/getConsentLink"), {"redirectUrl": CONSENT_RETURN})
        link = str(pick(answer.body, "consentLink") or "") if answer.status == 200 else ""
        if not link.startswith("https://"):
            raise Problem(f"no sign-in address was given for {label}: {message_of(answer)}")
        out(f"  Sign in for {label}: open this address in a browser, choose your own account, tick 'I have verified this request and trust the source' and click 'Allow access':")
        out(f"    {link}")
    out(f"The addresses are good for about 15 minutes. If your sign-in name has #EXT# in it (you are a guest of the tenant), and the sign-in page for Azure Queues has /common/ in its web address, put the tenant id "
        f"{f['tenant'] or '<tenant id>'} in its place and press Enter before you choose your account: otherwise the connection is made with your home tenant's token, which the queue (in this tenant) refuses. "
        "Then run `connections` again: it says connected.")
    return 0


def flow_definition() -> dict:
    """The definition of the flow, from the unpacked solution through the packer (tools/powerplatform-pack.py reads the files: this tool reads none), so that there is one flow and not two."""
    spec = importlib.util.spec_from_file_location("powerplatform_pack_of_the_tool", Path(__file__).with_name("powerplatform-pack.py"))
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    try:
        parts = pack.collect(pack.DEFAULT_SOURCE)
    except pack.Problem as problem:
        raise Problem(str(problem)) from problem
    flows = [name for name in parts if name.startswith("Workflows/") and name.endswith(".json")]
    if len(flows) != 1:
        raise Problem(f"the unpacked solution has {len(flows)} flows, and this tool makes the one")
    return json.loads(parts[flows[0]])["properties"]["definition"]


def flow_body(account: str, queue: str, names: Mapping[str, str], posted: str = POSTED_QUEUE_NAME) -> dict:
    definition = flow_definition()
    for key, value in ((ENDPOINT_PARAMETER, f"https://{account}.queue.core.windows.net/"), (QUEUE_PARAMETER, queue), (POSTED_PARAMETER, posted)):
        if key not in definition.get("parameters", {}):
            raise Problem(f"the flow of the solution has no parameter {key!r}: the tool and the solution have drifted apart")
        definition["parameters"][key]["defaultValue"] = value
    references = {api: {"connectionName": names[api], "source": "Embedded", "id": f"/providers/Microsoft.PowerApps/apis/{api}", "tier": tier} for api, _, _, tier in CONNECTORS}
    return {"properties": {"displayName": FLOW_NAME, "definition": definition, "state": "Started", "connectionReferences": references}}


def find_flows(client: Client, environment_id: str, display_name: str) -> list[dict]:
    answer = client.send("GET", flows_url(environment_id))
    if answer.status != 200 or not isinstance(answer.body, dict):
        raise Problem(f"the flows could not be read: {message_of(answer)}")
    return [x for x in answer.body.get("value") or [] if isinstance(x, dict) and str(pick(x, "properties", "displayName") or "") == display_name]


def command_flow(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"]) -> int:
    f = facts(resolve_environment(client, args.environment))
    names = connected_names(client, str(f["id"]), tuple(api for api, _, _, _ in CONNECTORS))
    body = flow_body(args.storage_account, args.queue, names, args.posted_queue)
    found = find_flows(client, str(f["id"]), FLOW_NAME)
    if len(found) > 1:
        raise Problem(f"{len(found)} flows in this environment are named {FLOW_NAME!r}: this tool changes none of them on a guess")
    out(f"The environment {f['name']} (id {f['id']}): both connections are connected.")
    out(f"Would {'update the definition and the connections of' if found else 'make'} the flow {FLOW_NAME}, started: it reads the queue {args.queue} of the storage account {args.storage_account} once a minute, posts each message as a Teams card "
        f"(or replaces a card with it), and tells the app which message each card is by a message on the queue {args.posted_queue}.")
    if not args.apply:
        out("This was a dry run. Run again with --apply to do it.")
        return 0
    confirm(args, f"{'Update' if found else 'Make'} the flow {FLOW_NAME}?", ask)
    if found:
        answer = client.send("PATCH", flows_url(str(f["id"]), "/" + str(found[0].get("name"))), body)
    else:
        answer = client.send("POST", flows_url(str(f["id"])), body)
    if answer.status not in (200, 201):
        raise Problem(f"the flow was not {'updated' if found else 'made'}: {message_of(answer)}")
    state = str(pick(answer.body, "properties", "state") or "no state")
    suspended = str(pick(answer.body, "properties", "flowSuspensionReason") or "None")
    out(f"The flow {FLOW_NAME} is {'updated' if found else 'made'}: {state}" + ("" if suspended == "None" else f", suspended: {suspended}") + ".")
    out("Next: `test-card` puts one card on the queue, and `flow-runs` shows what the flow did with it.")
    return 0 if suspended == "None" and state == "Started" else 1


def command_flow_runs(args: argparse.Namespace, client: Client, out: Callable[[str], None]) -> int:
    f = facts(resolve_environment(client, args.environment))
    found = find_flows(client, str(f["id"]), FLOW_NAME)
    if not found:
        raise Problem(f"no flow named {FLOW_NAME!r} in this environment for this sign-in: run `flow` first")
    name = str(found[0].get("name"))
    out(f"The flow {FLOW_NAME} in {f['name']}: {pick(found[0], 'properties', 'state') or 'no state'}.")
    answer = client.send("GET", flows_url(str(f["id"]), f"/{name}/runs"))
    if answer.status != 200 or not isinstance(answer.body, dict):
        raise Problem(f"the runs could not be read: {message_of(answer)}")
    runs = sorted((r for r in answer.body.get("value") or [] if isinstance(r, dict)), key=lambda r: str(pick(r, "properties", "startTime") or ""), reverse=True)[: args.last]
    if not runs:
        out("It has not run yet: a run starts when a message is on the queue.")
        return 0
    failed = 0
    for run in runs:
        status = str(pick(run, "properties", "status") or "")
        out(f"  {pick(run, 'properties', 'startTime') or 'no time'}  {status}  {pick(run, 'properties', 'code') or ''}".rstrip())
        if status == "Failed":
            failed += 1
            detail = client.send("GET", f"{FLOW}/providers/Microsoft.ProcessSimple/environments/{f['id']}/flows/{name}/runs/{run.get('name')}?api-version={APPS_API}&$expand=properties/actions")
            actions = pick(detail.body, "properties", "actions") if detail.status == 200 else None
            for action, result in (actions or {}).items() if isinstance(actions, dict) else ():
                if isinstance(result, dict) and result.get("status") == "Failed":
                    out(f"      {action}: {result.get('code') or 'no code'}")
    return 1 if failed else 0


def test_flow_body(account: str, queue: str, to: str, queue_connection: str, card_id: str) -> dict:
    message = {"v": 1, "id": card_id, "to": to, "title": "Meternaut test card",
               "card": {"type": "AdaptiveCard", "version": "1.4", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "body": [{"type": "TextBlock", "text": "Meternaut test card", "weight": "Bolder", "size": "Large"},
                                 {"type": "TextBlock", "wrap": True, "text": "This card went through the private queue and the flow Meternaut cards, which runs in the project's own network."}]}}
    put = {"runAfter": {}, "type": "OpenApiConnection", "inputs": {
        "host": {"connectionName": "shared_azurequeues", "operationId": "PutMessage_V2", "apiId": "/providers/Microsoft.PowerApps/apis/shared_azurequeues"},
        "parameters": {"storageAccountName": f"https://{account}.queue.core.windows.net/", "queueName": queue, "message": json.dumps(message)},
        "authentication": "@parameters('$authentication')"}}
    definition = {"$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#", "contentVersion": "1.0.0.0",
                  "parameters": {"$connections": {"defaultValue": {}, "type": "Object"}, "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                  "triggers": {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": {}, "required": []}}}},
                  "actions": {"Put_a_message_on_a_queue_(V2)": put}}
    references = {"shared_azurequeues": {"connectionName": queue_connection, "source": "Embedded", "id": "/providers/Microsoft.PowerApps/apis/shared_azurequeues", "tier": "Premium"}}
    return {"properties": {"displayName": TEST_FLOW_NAME, "definition": definition, "state": "Started", "connectionReferences": references}}


def action_of(definition: dict, name: str) -> dict:
    """The action of that name in the definition, in a condition too: test-close copies the two Teams steps of the flow, so that what it proves is what the flow does."""
    todo = [definition["actions"]]
    while todo:
        actions = todo.pop()
        if name in actions:
            return copy.deepcopy(actions[name])
        for action in actions.values():
            todo += [action.get("actions", {}), action.get("else", {}).get("actions", {})]
    raise Problem(f"the flow of the solution has no action {name!r}: the tool and the solution have drifted apart")


def test_close_flow_body(to: str, teams_connection: str) -> dict:
    def card(text: str) -> str:
        return json.dumps({"type": "AdaptiveCard", "version": "1.4", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "body": [{"type": "TextBlock", "text": text, "wrap": True}]})
    real = flow_definition()
    post, update = action_of(real, POST_ACTION), action_of(real, UPDATE_ACTION)
    post["runAfter"], update["runAfter"] = {}, {"Wait_ten_seconds": ["Succeeded"]}
    post["inputs"]["parameters"].update({"body/recipient": to, "body/messageBody": card("Meternaut test card: in ten seconds this card is replaced by one that has no button.")})
    update["inputs"]["parameters"].update({"body/recipient": to, "body/messageId": f"@body('{POST_ACTION}')?['id']", "body/messageBody": card("Decided: Declined by the test, just now. Nothing more to do.")})
    wait = {"runAfter": {POST_ACTION: ["Succeeded"]}, "type": "Wait", "inputs": {"interval": {"count": 10, "unit": "Second"}}}
    definition = {"$schema": real["$schema"], "contentVersion": real["contentVersion"], "parameters": {"$connections": {"defaultValue": {}, "type": "Object"}, "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                  "triggers": {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": {}, "required": []}}}},
                  "actions": {POST_ACTION: post, "Wait_ten_seconds": wait, UPDATE_ACTION: update}}
    references = {"shared_teams": {"connectionName": teams_connection, "source": "Embedded", "id": "/providers/Microsoft.PowerApps/apis/shared_teams", "tier": "Standard"}}
    return {"properties": {"displayName": TEST_FLOW_NAME, "definition": definition, "state": "Started", "connectionReferences": references}}


def command_test_card(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"], clock: Callable[[], float]) -> int:
    f = facts(resolve_environment(client, args.environment))
    names = connected_names(client, str(f["id"]), ("shared_azurequeues",))
    out(f"The environment {f['name']} (id {f['id']}): the queue connection is connected.")
    out(f"Would make a flow with a button, run it once and delete it: it puts one card for {args.to} on the queue {args.queue}, which the flow {FLOW_NAME} then posts in Teams. "
        f"The signed-in person needs {ROLE_MESSAGE_SENDER} on the queue for that, for as long as the test lasts.")
    if not args.apply:
        out("This was a dry run. Run again with --apply to do it.")
        return 0
    confirm(args, "Put a test card on the queue?", ask)
    body = test_flow_body(args.storage_account, args.queue, args.to, names["shared_azurequeues"], "test-" + secrets.token_hex(4))
    return run_test_flow(client, f, body, out, clock, f"The card is on the queue {args.queue}. The flow {FLOW_NAME} picks it up within a minute: look at your chat with Workflows in Teams (in the tenant's organisation, when you are a guest), or run `flow-runs`.",
                         f" Forbidden here is the queue's own answer that the signed-in person has no {ROLE_MESSAGE_SENDER} on it yet (a role takes up to 10 minutes to apply).", "Forbidden")


def command_test_close(args: argparse.Namespace, client: Client, out: Callable[[str], None], ask: Callable[[str], "str | None"], clock: Callable[[], float]) -> int:
    f = facts(resolve_environment(client, args.environment))
    names = connected_names(client, str(f["id"]), ("shared_teams",))
    out(f"The environment {f['name']} (id {f['id']}): the Teams connection is connected.")
    out(f"Would make a flow with a button, run it once and delete it: it posts a test card for {args.to} as the Flow bot, waits ten seconds and replaces it with a card that has no button, with the two steps of the flow {FLOW_NAME}. "
        "No queue is used.")
    if not args.apply:
        out("This was a dry run. Run again with --apply to do it.")
        return 0
    confirm(args, "Post a test card and replace it?", ask)
    return run_test_flow(client, f, test_close_flow_body(args.to, names["shared_teams"]), out, clock,
                         "The card was posted and replaced. Look at your chat with Workflows in Teams (in the tenant's organisation, when you are a guest): the card must say 'Decided: Declined by the test' and have no button. "
                         "If it still shows the first text, the step took the call and did not replace the card: say so.", " The step that failed names the field that Teams did not take: check it against the flow.")


def run_test_flow(client: Client, f: dict[str, object], body: dict, out: Callable[[str], None], clock: Callable[[], float], success: str, hint: str, hint_when: str = "") -> int:
    """Makes the test flow, runs it once, says how it went (`hint` is added to a failure, when an action failed with the code `hint_when` if one is named) and deletes it, whatever came of it."""
    made = client.send("POST", flows_url(str(f["id"])), body)
    if made.status not in (200, 201) or not GUID_RE.match(str(pick(made.body, "name") or "")):
        raise Problem(f"the test flow was not made: {message_of(made)}")
    flow_id = str(pick(made.body, "name"))
    result = 1
    try:
        started = client.send("POST", flows_url(str(f["id"]), f"/{flow_id}/triggers/manual/run"), {})
        if started.status not in (200, 202):
            raise Problem(f"the test flow did not start: {message_of(started)}")
        deadline = clock() + 120
        status, latest = "", None
        while clock() < deadline:
            client.sleep(5)
            runs = client.send("GET", flows_url(str(f["id"]), f"/{flow_id}/runs"))
            listed = [r for r in (runs.body or {}).get("value") or [] if isinstance(r, dict)] if runs.status == 200 and isinstance(runs.body, dict) else []
            latest = max(listed, key=lambda r: str(pick(r, "properties", "startTime") or ""), default=None)
            status = str(pick(latest, "properties", "status") or "") if latest else ""
            if status in ("Succeeded", "Failed", "Cancelled"):
                break
        if status == "Succeeded":
            out(success)
            result = 0
        elif status == "Failed" and latest:
            detail = client.send("GET", f"{FLOW}/providers/Microsoft.ProcessSimple/environments/{f['id']}/flows/{flow_id}/runs/{latest.get('name')}?api-version={APPS_API}&$expand=properties/actions")
            actions = pick(detail.body, "properties", "actions") if detail.status == 200 else None
            codes = [str(r.get("code")) for r in actions.values() if isinstance(r, dict) and r.get("status") == "Failed"] if isinstance(actions, dict) else []
            out(f"The test flow failed: {', '.join(codes) or 'no code'}." + (hint if not hint_when or hint_when in codes else ""))
        else:
            out(f"The test flow did not end in two minutes (last state: {status or 'none'}).")
    finally:
        removed = client.send("DELETE", flows_url(str(f["id"]), f"/{flow_id}"))
        out("The test flow is deleted." if removed.status in (200, 204) else f"The test flow {flow_id} could not be deleted ({message_of(removed)}): delete it in the maker portal or with the flow API.")
    return result


# ---- the steps that a person does ----------------------------------------------------------------------------------------------------------------

def steps_text(args: argparse.Namespace) -> list[str]:
    subscription = args.subscription or "<subscription id>"
    group = args.resource_group or "<resource group>"
    account = args.storage_account or "<storage account>"
    environment = args.environment or "<environment name>"
    person = args.person or "<object id of the person whose connection reads the queue>"
    queue = f"/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Storage/storageAccounts/{account}/queueServices/default/queues/{QUEUE_NAME}"
    posted = queue.removesuffix(QUEUE_NAME) + POSTED_QUEUE_NAME
    policy = policy_id_of(subscription, group, DEFAULT_POLICY_NAME)
    return [
        "The steps that a person does by hand, in order (docs/proposals/19-teams-cards-through-power-automate.md). Nothing here was run: it is the plan that the Hub and this tool follow.",
        "",
        "Before anything runs:",
        "  1. Decide the size of the subnet snet-powerplatform (POWERPLATFORM_SUBNET_LENGTH in tools/environment-params.py: /27 by default, /28 is the least, /26 for a Production environment). It cannot change once an environment is linked.",
        "",
        "In the Hub (the Actions tab, the workflow Hub, which runs in the environment hub):",
        "  2. Start the action cases once more: it makes the queues teams-cards and teams-posted next to cases-control and gives the app its settings TEAMS_CARDS_QUEUE and TEAMS_POSTED_QUEUE; the app's new code, which writes the cards, keeps the answer of the flow and replaces a card when its request ends, goes out in the same run.",
        "  3. Start the action powerplatform: the subnet snet-powerplatform and the enterprise policy. It stops before it changes anything, and says why, unless the resource provider is registered, the virtual network is there and the parameter builder found room for the subnet. "
        "It waits up to 20 minutes for the landing zone's route table on the subnet and reads both back. The deploy identity cannot register a provider: check once, and register it if it is not:",
        "       az provider show --namespace Microsoft.PowerPlatform --query registrationState",
        "       az provider register --namespace Microsoft.PowerPlatform",
        "",
        "In Azure, by a person (the deploy identity gives roles to service principals only):",
        "  4. Give the person whose Azure Queues connection the flow will use a data role on each of the two queues, and nothing wider. A role takes up to ten minutes to apply:",
        f"       az role assignment create --assignee-object-id {person} --assignee-principal-type User --role \"{ROLE_MESSAGE_PROCESSOR}\" --scope {queue}",
        f"       az role assignment create --assignee-object-id {person} --assignee-principal-type User --role \"{ROLE_MESSAGE_SENDER}\" --scope {posted}",
        f"     (The person's own object id: az ad signed-in-user show --query id --output tsv, run by that person. The account's name: az storage account list --resource-group {group} --query \"[].name\" --output tsv.",
        f"      The first role is for the queue of the cards: peek, retrieve and delete is what the trigger and the delete need. The second is for the queue of the posted cards: the flow writes one message to it for each card that it posted, and the app reads it with its own role on the account. For the test flow of step 14 add the role \"{ROLE_MESSAGE_SENDER}\" on the first queue too, and take it away again after.)",
        "  5. If the person who links the environment does not read the policy already, give that person Reader on it:",
        f"       az role assignment create --assignee-object-id <object id of the Power Platform administrator> --assignee-principal-type User --role Reader --scope {policy}",
        "",
        "In Teams, by a Teams administrator (a setting of the Teams admin center that this tool cannot read):",
        "  6. Check that the app 'Workflows' (formerly Power Automate) is allowed: https://admin.teams.microsoft.com/policies/manage-apps, find Workflows, its status must be Allowed. The action that posts a card needs it (Learn: the Microsoft Teams connector, known issues and limitations).",
        "",
        "In Power Platform (this tool, with the Power Platform administrator's own `az login`; each command is a dry run until --apply):",
        f"  7. python tools/powerplatform.py create-environment --name {environment} --sku Developer --apply     (an environment of that name is left alone: skip this step when it exists)",
        "     From 15 November 2026 a new developer environment has to be a Managed Environment (Learn). This tool makes the environment first and turns Managed Environments on second: if the first call is refused, "
        "make the environment in the Power Platform admin center with Managed Environments on, and go on with step 9.",
        f"  8. python tools/powerplatform.py managed --environment {environment} --apply                     (virtual network support needs a Managed Environment)",
        f"  9. python tools/powerplatform.py link --environment {environment} --subscription {subscription} --resource-group {group} --apply",
        "     Wait: connections can be unstable for up to 30 minutes after a link or an unlink.",
        f" 10. python tools/powerplatform.py status --environment {environment} --subscription {subscription} --resource-group {group}     (the answer must be: linked to the project's policy: YES)",
        "",
        "In the maker portal (https://make.powerapps.com), as the person of step 4 (who made the environment, or is an administrator of it), in the environment of step 7 (the import by the Dataverse API is not written: see this tool's help):",
        " 11. python tools/powerplatform-pack.py makes powerplatform/out/meternaut-cards.zip. Solutions, Import solution, Browse, that zip, Next.",
        " 12. The import asks for the two connections and the three values. Make each connection there, or from the actions of the flow in its designer, and not first under Data, Connections to pick afterwards (that can leave a second connection reference for the same connector):",
        "       - the Azure Queues connection: sign in with Microsoft Entra ID (the authentication type 'Microsoft Entra ID Integrated'), not with an access key; it belongs to you and is not shareable;",
        "       - the Microsoft Teams connection: sign in;",
        f"       - Storage queue endpoint: https://{account}.queue.core.windows.net/   (the whole address, with https and the closing slash);",
        f"       - Queue name: {QUEUE_NAME}",
        f"       - Posted queue name: {POSTED_QUEUE_NAME}",
        " 13. Import. Open the solution, open the flow 'Meternaut cards', save it and turn it on: it arrives switched off, and saving does not turn it on. It is untested in Power Platform: if the designer marks an action, that is the first thing to read.",
        " 14. The first card, before the app sends one: a second flow in the same environment, with a manual trigger and one action 'Put a message on a queue (V2)', the same connection, the same endpoint, the queue "
        f"{QUEUE_NAME} and, as the message, the JSON text {{\"v\":1,\"id\":\"test-1\",\"to\":\"<your mail address>\",\"title\":\"Test\",\"card\":{{\"type\":\"AdaptiveCard\",\"version\":\"1.4\",\"body\":[{{\"type\":\"TextBlock\",\"text\":\"Test card\"}}]}}}}. "
        "Run it. The card should be in your chat with the Workflows app within a few minutes, and the queue empty. Delete the test flow and take the Sender role away.",
        "",
        "When the maker portal says 'You are not permitted to make flows in this environment' (you are a guest of the tenant, and new Dataverse environments refuse guests), make steps 11 to 14 with this tool instead, as the same person:",
        f" 15. python tools/powerplatform.py connections --environment {environment} --apply     (open each address that it prints, choose your own account, tick the box, click Allow access; for a guest, put the tenant id in place of /common/ in the Azure Queues sign-in page's address)",
        f" 16. python tools/powerplatform.py flow --environment {environment} --storage-account {account} --apply",
        f" 17. python tools/powerplatform.py test-card --environment {environment} --storage-account {account} --to <your mail address> --apply     (needs {ROLE_MESSAGE_SENDER} on the queue while it runs; take it away after)",
        f"     python tools/powerplatform.py test-close --environment {environment} --to <your mail address> --apply     (posts a card and replaces it ten seconds later: it proves the step that closes a card, with no queue and no role)",
        f" 18. python tools/powerplatform.py flow-runs --environment {environment}     (what the flow did with each card)",
        "",
        "After a new version of the solution: an import replaces the flow, and the replacement arrives switched off with no connection chosen. Pick the two connections again (they are kept, with no new sign-in), save, and turn it on, as in steps 12 and 13.",
        "If the first runs after the link are slow and fail once with a 404 from the connector's host, wait out the 30 minutes and run again before looking for another cause.",
        "If a step fails: the flow's own run history says which action failed and why; `status` says what is linked; the Power Platform admin center shows the environment's History.",
    ]


def command_steps(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    for line in steps_text(args):
        out(line)
    return 0


# ---- the command line ----------------------------------------------------------------------------------------------------------------------------

def ask_on_terminal(prompt: str) -> "str | None":
    """The answer of a person at a terminal, or None when there is nobody to ask (no terminal, or one that is closed)."""
    if not sys.stdin.isatty():
        return None
    try:
        return input(prompt)
    except EOFError:
        return None


def main(argv: list[str] | None = None, runner: Callable[[list[str]], tuple[int, str, str]] = run_az, transport: Http = default_http, sleep: Callable[[float], None] = time.sleep,
         out: Callable[[str], None] = print, ask: Callable[[str], "str | None"] | None = None, env: Mapping[str, str] | None = None, clock: Callable[[], float] = time.monotonic) -> int:
    env = os.environ if env is None else env
    ask = ask or ask_on_terminal
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def common(sub: argparse.ArgumentParser, environment_required: bool, project: bool, changes: bool) -> None:
        sub.add_argument("--environment", default=env.get("PP_ENVIRONMENT"), required=environment_required and not env.get("PP_ENVIRONMENT"), help="the display name or the id of the environment (the variable PP_ENVIRONMENT)")
        sub.add_argument("--subscription", default=env.get("ENV_SUBSCRIPTION_ID"), help="the project's subscription id (the variable ENV_SUBSCRIPTION_ID of the Hub)")
        sub.add_argument("--resource-group", default=env.get("ENV_RESOURCE_GROUP"), help="the project's resource group (the variable ENV_RESOURCE_GROUP of the Hub)")
        sub.add_argument("--policy-name", default=DEFAULT_POLICY_NAME, help="the project's enterprise policy; the default is the one that environment/powerplatform/main.bicep makes")
        if changes:
            sub.add_argument("--apply", action="store_true", help="make the change (the default is a dry run)")
            sub.add_argument("--yes", action="store_true", help="do not ask first")

    status = commands.add_parser("status", help="read only: the environments, and for one of them whether the project's policy is linked")
    common(status, False, True, False)
    create = commands.add_parser("create-environment", help="a dry run; with --apply, make the environment and wait until it is Ready")
    create.add_argument("--name", required=True, help="the display name of the environment")
    create.add_argument("--region", default=GEOGRAPHY, choices=[GEOGRAPHY], help="the Power Platform geography (Sweden is the only one that the project's policy is made for)")
    create.add_argument("--sku", default="Developer", choices=SKUS_CREATED, help="the type of the environment")
    create.add_argument("--domain-name", help="the Dataverse domain name; the default is made from the name")
    create.add_argument("--apply", action="store_true", help="make the environment (the default is a dry run)")
    create.add_argument("--yes", action="store_true", help="do not ask first")
    managed = commands.add_parser("managed", help="a dry run; with --apply, turn Managed Environments on")
    common(managed, True, False, True)
    for name, text in (("link", "checks, then a dry run; with --apply, link the project's policy to the environment"), ("unlink", "a dry run; with --apply, unlink the project's policy from the environment")):
        sub = commands.add_parser(name, help=text)
        common(sub, True, True, True)
    steps = commands.add_parser("steps", help="print the steps that a person does by hand")
    steps.add_argument("--subscription")
    steps.add_argument("--resource-group")
    steps.add_argument("--storage-account")
    steps.add_argument("--environment")
    steps.add_argument("--person", help="the object id of the person whose connection reads the queue")
    connections = commands.add_parser("connections", help="the two connections of the flow: what is made and connected, and the address at which the person signs in")
    common(connections, True, False, True)
    flow = commands.add_parser("flow", help="a dry run; with --apply, make or update the flow Meternaut cards from the definition of the packed solution")
    common(flow, True, False, True)
    flow.add_argument("--storage-account", required=True, help="the name of the storage account that holds the queue (the output of `az storage account list` in the project's resource group)")
    flow.add_argument("--queue", default=QUEUE_NAME, help="the queue that the cards are put on")
    flow.add_argument("--posted-queue", default=POSTED_QUEUE_NAME, help="the queue that the flow writes to after it posted a card")
    flow_runs = commands.add_parser("flow-runs", help="read only: the last runs of the flow and, for a failed one, the actions that failed")
    common(flow_runs, True, False, False)
    flow_runs.add_argument("--last", type=int, default=5, help="how many runs (1 to 20)")
    test_card = commands.add_parser("test-card", help="a dry run; with --apply, put one test card on the queue by a flow that is made, run once and deleted")
    common(test_card, True, False, True)
    test_card.add_argument("--storage-account", required=True, help="the name of the storage account that holds the queue")
    test_card.add_argument("--queue", default=QUEUE_NAME, help="the queue that the cards are put on")
    test_card.add_argument("--to", required=True, help="the mail address of the person whose chat with Workflows gets the card")
    test_close = commands.add_parser("test-close", help="a dry run; with --apply, post a test card and replace it ten seconds later by a flow that is made, run once and deleted")
    common(test_close, True, False, True)
    test_close.add_argument("--to", required=True, help="the mail address of the person whose chat with Workflows gets the card")
    args = parser.parse_args(argv)
    hide = Hider()
    try:
        if args.command == "steps":
            return command_steps(args, out)
        if env.get("GITHUB_ACTIONS") == "true":
            raise Problem("a person who administers Power Platform runs this, never a pipeline: its output names environments and policies of the estate, and the deploy identity holds no right in Power Platform (AGENTS.md rules 18 and 24)")
        for field, pattern, text in (("subscription", GUID_RE, "a subscription id"), ("resource_group", RESOURCE_GROUP_RE, "a resource group name"), ("policy_name", POLICY_RE, "the name of an enterprise policy"),
                                     ("storage_account", STORAGE_ACCOUNT_RE, "a storage account name (3 to 24 lower case letters and digits)"), ("queue", QUEUE_RE, "a queue name (3 to 63 lower case letters, digits and hyphens)"),
                                     ("posted_queue", QUEUE_RE, "a queue name (3 to 63 lower case letters, digits and hyphens)"), ("to", MAIL_RE, "a mail address")):
            value = getattr(args, field, None)
            if value is not None and not pattern.match(value):
                raise Problem(f"--{field.replace('_', '-')} is {text}")
        if getattr(args, "last", None) is not None and not 1 <= args.last <= 20:
            raise Problem("--last is a number from 1 to 20")
        if getattr(args, "name", None) is not None and not NAME_RE.match(args.name):
            raise Problem("--name is 2 to 63 letters, digits, spaces, dots, underscores and hyphens, and starts with a letter or a digit")
        if getattr(args, "domain_name", None) is not None and not DOMAIN_RE.match(args.domain_name):
            raise Problem("--domain-name is lower case letters, digits and hyphens")
        client = Client(Tokens(runner, hide), transport, sleep)
        if args.command == "status":
            return command_status(args, client, out)
        if args.command == "create-environment":
            return command_create(args, client, out, ask, clock)
        if args.command == "connections":
            return command_connections(args, client, out, ask)
        if args.command == "flow":
            return command_flow(args, client, out, ask)
        if args.command == "flow-runs":
            return command_flow_runs(args, client, out)
        if args.command == "test-card":
            return command_test_card(args, client, out, ask, clock)
        if args.command == "test-close":
            return command_test_close(args, client, out, ask, clock)
        if args.command in ("link", "unlink") and not (args.subscription and args.resource_group):
            raise Problem("--subscription and --resource-group name where the project's policy is (the variables ENV_SUBSCRIPTION_ID and ENV_RESOURCE_GROUP of the Hub)")
        if args.command == "managed":
            return command_managed(args, client, out, ask)
        return command_link(args, client, out, ask, clock, unlink=args.command == "unlink")
    except Problem as e:
        print(hide(f"error: {e}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
