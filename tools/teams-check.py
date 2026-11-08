#!/usr/bin/env python3
"""Reads the Teams bot back from Azure and knocks at its door (standard library only).

    python tools/teams-check.py read-back --subscription S --resource-group G --app A --bot B --identity I [--wait-seconds N] [--summary FILE] [--timeout SECONDS]
    python tools/teams-check.py door --host H [--tries N] [--interval SECONDS] [--timeout SECONDS]

The bot (docs/proposals/13-teams-and-outlook.md, environment/teams/main.bicep) is the one public endpoint of the project, so both checks are written to fail loudly.

read-back  A deployment that says Succeeded does not say that the resource came out as the template wrote it: tenant policies with the effect Modify rewrite a resource while it is made, and a Modify
           policy does not refuse anything (AGENTS.md rule 19). So the run fails for each thing that differs. It reads:
             - the identity of the bot: there, with a client id and a principal id, and holding no role assignment anywhere in the resource group (its token is for the Bot Connector alone);
             - the Azure Bot resource: kind azurebot, the free tier F0, app type UserAssignedMSI, the app id the client id of that identity, its resource id, its own tenant, local authentication off, and the
               endpoint the one route of the app (https://<default host name of the app>/api/messages);
             - its Teams channel: there, and not disabled;
             - the function app: a function app that is Running, https only, with its own system-assigned identity and the bot's, integrated with the function subnet snet-func, and no deployment password
               (basic publishing credentials off), TLS 1.2 at the least; whether the inbound side is open or narrowed to the service tag AzureBotService is said, and is no failure either way;
             - its functions: exactly teams-messages and teams-offer (no function of the cases app is in this app). With --wait-seconds the list is read again every 15 seconds until it is right, because a
               site that has just been given its code needs a minute or two to list it.
           Only GET requests of Azure Resource Manager through `az rest`. Nothing of the data plane is called, no setting is read (the list of settings is a POST) and no key is listed.
door       Knocks at the public endpoint from here, with no token: a POST with no token and a POST with a token that is not one must be refused with 401 and an empty body, a GET of the route must not be
           answered with a page (404 or 405), and the host's admin endpoint must refuse a caller with no key. A request that gets no answer or an answer of 5xx, or 429, is tried again (a Flex Consumption
           app that has scaled to zero needs a start), up to --tries times, --interval seconds apart. Nothing secret is sent or printed. This is the proof that the endpoint fails closed.

Exit 0 when every line is ok, 1 when any line fails or cannot be read.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

ARM = "https://management.azure.com"
BOT_API = "2022-09-15"
SITE_API = "2024-04-01"
IDENTITY_API = "2023-01-31"
ROLE_API = "2022-04-01"
NOT_FOUND = re.compile(r"NotFound|ResourceNotFound|\b404\b", re.I)
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HOST = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FUNCTION_SUBNET = "snet-func"
FUNCTIONS = ("teams-messages", "teams-offer")
TIMEOUT_SECONDS = 120
LIST_SECONDS = 15

Runner = Callable[[list[str]], "tuple[int, str, str]"]


class Gone(Exception):
    """Azure says that the resource is not there."""


class Unreadable(Exception):
    """Azure gave no usable answer. The text is the first line of its error, which holds no token."""


class Stuck(Exception):
    """`az` did not answer in time. The rest is not read: a second read would wait just as long."""


def run_az(arguments: list[str], timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    try:
        done = subprocess.run([os.environ.get("AZ", "az"), *arguments], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Stuck(f"az did not answer within {timeout} seconds")
    return done.returncode, done.stdout, done.stderr


def get(az: Runner, path: str, api: str, query: str = "") -> dict:
    code, out, err = az(["rest", "--method", "get", "--url", f"{ARM}{path}?api-version={api}{query}", "--output", "json"])
    if code != 0:
        if NOT_FOUND.search(err):
            raise Gone()
        raise Unreadable((err.strip().splitlines() or ["no answer"])[0][:300])
    try:
        document = json.loads(out)
    except ValueError:
        raise Unreadable("the answer is not JSON")
    if not isinstance(document, dict):
        raise Unreadable("the answer is not an object")
    return document


def same(a: object, b: object) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower()


def read_back(az: Runner, subscription: str, group: str, app: str, bot: str, identity: str, wait_seconds: int = 0,
              sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> list[tuple[bool, str]]:
    """One (ok, text) per thing that was read. A thing that cannot be read is a failure too."""
    found: list[tuple[bool, str]] = []
    halted: list[str] = []
    base = f"/subscriptions/{subscription}/resourceGroups/{group}/providers"

    def say(ok: bool, text: str) -> None:
        found.append((ok, text))

    def fetch(label: str, path: str, api: str, query: str = "") -> dict | None:
        if halted:
            return None
        try:
            return get(az, path, api, query)
        except Gone:
            say(False, f"{label} is not there")
        except Unreadable as e:
            say(False, f"{label} could not be read: {e}")
        except Stuck as e:
            halted.append(str(e))
            say(False, f"{label} could not be read: {e}. The read-back stops here: nothing after it was read")
        return None

    who = fetch(f"The identity {identity}", f"{base}/Microsoft.ManagedIdentity/userAssignedIdentities/{identity}", IDENTITY_API)
    identity_id = f"{base}/Microsoft.ManagedIdentity/userAssignedIdentities/{identity}"
    client = principal = tenant = ""
    if who is not None:
        properties = who.get("properties") or {}
        client, principal, tenant = str(properties.get("clientId") or ""), str(properties.get("principalId") or ""), str(properties.get("tenantId") or "")
        ok = bool(GUID.match(client) and GUID.match(principal))
        say(ok, f"The identity {identity} is there, with a client id (the bot's app id) and a principal id" if ok else f"The identity {identity} has no client id or no principal id")

    if principal and GUID.match(principal):
        query = "&$filter=" + urllib.parse.quote(f"principalId eq '{principal}'", safe="'")
        granted = fetch("The role assignments of the bot's identity", f"{base}/Microsoft.Authorization/roleAssignments", ROLE_API, query)
        if granted is not None:
            held = [a for a in granted.get("value") or [] if isinstance(a, dict)]
            say(not held, "The bot's identity holds no role assignment in the resource group" if not held
                else f"The bot's identity holds {len(held)} role assignment(s): it is for the token of the Bot Connector alone and holds none")

    site = fetch(f"The function app {app}", f"{base}/Microsoft.Web/sites/{app}", SITE_API)
    host = ""
    if site is not None:
        properties = site.get("properties") or {}
        identities = site.get("identity") or {}
        users = {k.lower() for k in (identities.get("userAssignedIdentities") or {})}
        host = str(properties.get("defaultHostName") or "")
        for label, ok in (("it is a function app", "functionapp" in str(site.get("kind") or "")),
                          ("it is Running", properties.get("state") == "Running"),
                          ("it takes https only", properties.get("httpsOnly") is True),
                          ("it has an identity of its own (system-assigned)", "SystemAssigned" in str(identities.get("type") or "") and bool(identities.get("principalId"))),
                          ("it has the bot's identity (user-assigned)", identity_id.lower() in users),
                          (f"it runs in the function subnet {FUNCTION_SUBNET}", str(properties.get("virtualNetworkSubnetId") or "").lower().endswith(f"/subnets/{FUNCTION_SUBNET}")),
                          ("it reports its default host name", bool(host))):
            say(ok, f"The function app {app}: {label}" if ok else f"The function app {app} differs from its template: {label} is not so")

    if bot:
        document = fetch(f"The Azure Bot resource {bot}", f"{base}/Microsoft.BotService/botServices/{bot}", BOT_API)
        if document is not None:
            properties = document.get("properties") or {}
            wanted = f"https://{host}/api/messages" if host else ""
            for label, ok in (("its kind is azurebot", document.get("kind") == "azurebot"),
                              ("it is the free tier F0", (document.get("sku") or {}).get("name") == "F0"),
                              ("its app type is UserAssignedMSI", properties.get("msaAppType") == "UserAssignedMSI"),
                              ("its app id is the client id of the bot's identity", bool(client) and same(properties.get("msaAppId"), client)),
                              ("its identity is the bot's identity", same(properties.get("msaAppMSIResourceId"), identity_id)),
                              ("its tenant is the tenant of the bot's identity", bool(tenant) and same(properties.get("msaAppTenantId"), tenant)),
                              ("local authentication is off (disableLocalAuth)", properties.get("disableLocalAuth") is True),
                              ("its endpoint is the one route of the app", bool(wanted) and same(properties.get("endpoint"), wanted))):
                say(ok, f"The Azure Bot resource {bot}: {label}" if ok else f"The Azure Bot resource {bot} differs from its template: {label} is not so")
        channel = fetch("The Teams channel of the bot", f"{base}/Microsoft.BotService/botServices/{bot}/channels/MsTeamsChannel", BOT_API)
        if channel is not None:
            properties = channel.get("properties") or {}
            inner = properties.get("properties") if isinstance(properties.get("properties"), dict) else {}
            ok = properties.get("channelName") == "MsTeamsChannel" and properties.get("provisioningState", "Succeeded") == "Succeeded" and inner.get("isEnabled", True) is not False
            say(ok, "The Teams channel of the bot is there and is not disabled" if ok else "The Teams channel of the bot is not MsTeamsChannel, is not Succeeded or is disabled")

    config = fetch(f"The configuration of the function app {app}", f"{base}/Microsoft.Web/sites/{app}/config/web", SITE_API)
    if config is not None:
        properties = config.get("properties") or {}
        say(properties.get("minTlsVersion") == "1.2", "The function app takes TLS 1.2 at the least" if properties.get("minTlsVersion") == "1.2" else "The function app does not require TLS 1.2")
        rules = [r for r in properties.get("ipSecurityRestrictions") or [] if isinstance(r, dict) and r.get("action") == "Allow" and r.get("ipAddress") != "Any"]
        tags = sorted({str(r.get("ipAddress")) for r in rules})
        if properties.get("ipSecurityRestrictionsDefaultAction") == "Deny":
            say(True, "Inbound: only " + (", ".join(tags) or "nothing") + " (the rest is denied), on top of the check of the token that the app makes on every call")
        else:
            say(True, "Inbound: open to the internet, as designed: the check of the token that the app makes on every call is the protection (restrictInboundToBotService is off)")
    scm = fetch("The deployment password policy", f"{base}/Microsoft.Web/sites/{app}/basicPublishingCredentialsPolicies/scm", SITE_API)
    if scm is not None:
        ok = (scm.get("properties") or {}).get("allow") is False
        say(ok, "The deployment endpoint takes no password (basic publishing credentials are off)" if ok else "The deployment endpoint takes a password: basic publishing credentials are on")

    deadline = clock() + max(0, wait_seconds)
    while True:
        listed = fetch(f"The functions of {app}", f"{base}/Microsoft.Web/sites/{app}/functions", SITE_API)
        if listed is None:
            break
        names = sorted(str(f.get("name") or "").split("/")[-1] for f in listed.get("value") or [] if isinstance(f, dict))
        if names == sorted(FUNCTIONS) or clock() >= deadline:
            ok = names == sorted(FUNCTIONS)
            say(ok, f"The app lists exactly its two functions: {', '.join(names)}" if ok else f"The app lists {', '.join(names) or 'no function'}, and not exactly {', '.join(FUNCTIONS)}")
            break
        sleep(LIST_SECONDS)
    return found


# -- the door --------------------------------------------------------------------------------------------------------------------------------------

class NoAnswer(Exception):
    """The request got no answer: the name did not resolve, the connection failed or it took too long."""


def knock(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple[int, int]:
    """(status, length of the first kilobyte of the body). An answer of any status is an answer."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https, an address that is built here)
            return response.status, len(response.read(1024))
    except urllib.error.HTTPError as e:
        return e.code, len(e.read(1024))
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        raise NoAnswer(type(e).__name__) from e


# (what, method, path, headers, body, the statuses that are the right answer, whether the body has to be empty)
DOOR = (
    ("a POST with no token", "POST", "/api/messages", {"Content-Type": "application/json"}, b"{}", (401,), True),
    ("a POST with a token that is not one", "POST", "/api/messages", {"Content-Type": "application/json", "Authorization": "Bearer not.a.token"}, b"{}", (401,), True),
    ("a GET of the route", "GET", "/api/messages", {}, None, (404, 405), False),
    ("the host's admin endpoint with no key", "GET", "/admin/host/status", {}, None, (401, 403, 404), False),
)


def door(host: str, tries: int = 12, interval: float = 15, timeout: float = 30, transport=knock, sleep: Callable[[float], None] = time.sleep) -> list[tuple[bool, str]]:
    found: list[tuple[bool, str]] = []
    for what, method, path, headers, body, wanted, empty in DOOR:
        verdict = ""
        for attempt in range(1, tries + 1):
            try:
                status, length = transport(method, f"https://{host}{path}", dict(headers), body, timeout)
            except NoAnswer as e:
                verdict = f"got no answer ({e}) at try {attempt} of {tries}"
            else:
                if status >= 500 or status == 429:
                    verdict = f"was answered with {status} at try {attempt} of {tries}"
                elif status in wanted and (length == 0 or not empty):
                    found.append((True, f"{what}: refused with {status}" + (" and an empty body" if empty else "")))
                    verdict = ""
                    break
                else:
                    found.append((False, f"{what}: was answered with {status}" + (f" and {length}+ bytes of body" if empty and status in wanted else "")
                                  + f", and the right answer is {' or '.join(map(str, wanted))}" + (" with an empty body" if empty else "")))
                    verdict = ""
                    break
            if attempt < tries:
                sleep(interval)
        if verdict:
            found.append((False, f"{what}: {verdict}; the app did not answer as a closed door does"))
    return found


# -- the command line ------------------------------------------------------------------------------------------------------------------------------

def report(findings: list[tuple[bool, str]], title: str, detail: str, summary: str | None, out=print) -> int:
    lines = [f"{'ok' if ok else 'FAILED'}: {text}" for ok, text in findings]
    out("\n".join(lines))
    failed = [text for ok, text in findings if not ok]
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"### {title}\n\n{detail}\n\n```\n" + "\n".join(lines) + "\n```\n")
    if failed:
        print(f"{len(failed)} thing(s) are not as they should be. The run fails; nothing is repaired from here.", file=sys.stderr)
        return 1
    return 0


def main(argv=None, az: Runner | None = None, transport=knock, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    back = commands.add_parser("read-back", help="read the Teams bot back from Azure and fail unless it is as its template says")
    for name in ("subscription", "resource-group", "app", "bot", "identity"):
        back.add_argument(f"--{name}", required=True)
    back.add_argument("--wait-seconds", type=int, default=0, help="read the list of functions again every 15 seconds for this long, until it is right")
    back.add_argument("--summary", help="a file to append the lines to as Markdown (the step summary of a workflow run)")
    back.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS, help=f"seconds that one read of Azure may take (default {TIMEOUT_SECONDS})")
    knocking = commands.add_parser("door", help="knock at the public endpoint with no token and fail unless it is refused")
    knocking.add_argument("--host", required=True, help="the default host name of the function app")
    knocking.add_argument("--tries", type=int, default=12)
    knocking.add_argument("--interval", type=float, default=15)
    knocking.add_argument("--timeout", type=float, default=30)
    knocking.add_argument("--summary")
    args = parser.parse_args(argv)
    if args.command == "read-back":
        if not GUID.match(args.subscription) or not all(NAME.match(v) for v in (args.resource_group, args.app, args.bot, args.identity)):
            parser.error("--subscription is a GUID, and --resource-group, --app, --bot and --identity are plain names")
        if args.timeout < 1 or args.wait_seconds < 0:
            parser.error("--timeout is a number of seconds, one or more, and --wait-seconds is not negative")
        runner = az or (lambda arguments: run_az(arguments, args.timeout))
        findings = read_back(runner, args.subscription, args.resource_group, args.app, args.bot, args.identity, args.wait_seconds, sleep, clock)
        return report(findings, "The Teams bot, read back from Azure", f"Function app `{args.app}`, bot `{args.bot}`.", args.summary)
    if not HOST.match(args.host.lower()) or args.tries < 1 or args.interval < 0 or args.timeout <= 0:
        parser.error("--host is a host name, --tries is one or more, --interval is not negative and --timeout is a number of seconds")
    findings = door(args.host.lower(), args.tries, args.interval, args.timeout, transport, sleep)
    return report(findings, "The door of the Teams bot", f"Host `{args.host.lower()}`: requests with no token.", args.summary)


if __name__ == "__main__":
    sys.exit(main())
