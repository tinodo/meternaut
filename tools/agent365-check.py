#!/usr/bin/env python3
"""Checks what Agent 365 and Microsoft Entra Agent ID can show of Meternaut's agents, and says what a person has to do (standard library only).

    python tools/agent365-check.py run [--name-prefix meternaut] [--account-id <resource id of the Foundry resource>]
    python tools/agent365-check.py --selftest

Reads only: Microsoft Graph (the Azure CLI's token for https://graph.microsoft.com, so what it can read depends on the signed-in identity) and, with --account-id, the Foundry resource through Azure
Resource Manager. It prints one line for each check in the report shape of the drift checks (layer L3, the layer of the Citadel blueprint that is about the management and the owners of the
agents), and then what is MANUAL: the parts that have no API that this repository may call, with the page where a person does them.

  A365-LICENSE      The tenant has the Agent 365 licence (a subscribed SKU).                                   UNKNOWN when Graph does not answer for this identity.
  A365-IDENTITIES   An agent identity exists for an agent of Meternaut, found by the name prefix.             UNKNOWN (not applicable) when none is found: Foundry prompt agents run under the project's identity.
  A365-OWNERS       Each agent identity that was found has an owner and a sponsor.                             FAIL when one has none: the sponsor is the person who answers for the agent.
  A365-LOGGING      The Foundry resource has Agent 365 logging on (a preview property of the resource).        UNKNOWN when the property is not shown.

Nothing is changed. Setting the sponsor of an agent identity needs the application permission AgentIdentity.ReadWrite.All (the delegated permission is not supported for sponsors), so it is a hand
step of the owner and no tool of this repository does it: docs/proposals/11-agent-harness-and-evaluation.md gives the call. A token is never printed, and no id, name or address of the tenant is.
The exit code is 0 when no check failed, 1 when one failed, 2 when the tool refused to run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

helpers = sys.modules.get("aisec_helpers")
if helpers is None:  # a test has loaded it already; a tool run on its own loads it from its own folder
    _spec = importlib.util.spec_from_file_location("aisec_helpers", Path(__file__).with_name("aisec-helpers.py"))
    helpers = importlib.util.module_from_spec(_spec)
    sys.modules["aisec_helpers"] = helpers
    _spec.loader.exec_module(helpers)
Problem = helpers.Problem

GRAPH = "https://graph.microsoft.com"
AGENT_365_SKU = "796a6fb4-740b-4d36-bf56-9c12ca7fa069"  # the SkuId of the Agent 365 licence (Learn, read 2026-11-08)
ACCOUNT_API = "api-version=2026-03-15-preview"  # the version of Microsoft.CognitiveServices/accounts that shows the Agent 365 properties (preview)
PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{1,30}$")
ACCOUNT_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9_-]{2,64}$")
MANUAL = (
    "MANUAL the registry of the agents: the Microsoft 365 admin center, Agents, Registry (an agent of Foundry appears there only when it is published and the tenant has Agent 365)",
    "MANUAL the agent identities and their owners and sponsors: the Microsoft Entra admin center, Agent ID, All agent identities",
    "MANUAL the policies of Agent 365 (access, data, threat protection): the Microsoft 365 admin center, Agents, Settings; Defender and Purview are the owner's decision",
    "MANUAL the sponsor of an agent identity: a person with the Agent ID Administrator role sets it; Graph POST /servicePrincipals/{id}/microsoft.graph.agentIdentity/sponsors/$ref needs AgentIdentity.ReadWrite.All",
)


def emit(items: list[tuple[str, str, str]], now: dt.datetime) -> None:
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for control, state, detail in items:
        prefix = {"PASS": "drift.pass", "FAIL": "drift.fail", "UNKNOWN": "drift.unknown"}[state]
        print(f"{prefix} {json.dumps({'control': control, 'layer': 'L3', 'state': state, 'detail': detail, 'readAt': read_at}, separators=(',', ':'))}", flush=True)


def check(graph, arm, prefix: str, account_id: str) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    status, document = graph.request("GET", "/v1.0/subscribedSkus?$select=skuId,skuPartNumber")
    if status != 200 or not isinstance(document, dict):
        found.append(("A365-LICENSE", "UNKNOWN", f"Graph did not answer for this identity (HTTP {status}): the licence cannot be read"))
    else:
        skus = [item for item in document.get("value") or [] if isinstance(item, dict)]
        has = any(str(item.get("skuId", "")).lower() == AGENT_365_SKU or "AGENT_365" in str(item.get("skuPartNumber", "")).upper() for item in skus)
        found.append(("A365-LICENSE", "PASS" if has else "UNKNOWN", "the tenant has the Agent 365 licence" if has else f"none of the {len(skus)} subscribed SKUs is Agent 365: Agent 365 is not available here, and the registry and its policies are not"))
    status, document = graph.request("GET", f"/v1.0/servicePrincipals?$filter=startswith(displayName,'{prefix}')&$select=id,displayName&$top=50")
    identities: list[str] = []
    if status == 200 and isinstance(document, dict):
        for item in document.get("value") or []:
            ident = item.get("id") if isinstance(item, dict) else None
            if isinstance(ident, str) and re.fullmatch(r"[0-9a-fA-F-]{36}", ident):
                kind, _ = graph.request("GET", f"/v1.0/servicePrincipals/{ident}/microsoft.graph.agentIdentity?$select=id")
                if kind == 200:
                    identities.append(ident)
        found.append(("A365-IDENTITIES", "PASS" if identities else "UNKNOWN", f"{len(identities)} agent identities of Meternaut's agents" if identities else
                      "no agent identity of a name with that prefix: the Foundry prompt agents run under the project's identity and have none (not applicable)"))
    else:
        found.append(("A365-IDENTITIES", "UNKNOWN", f"Graph did not answer for this identity (HTTP {status}): the agent identities cannot be listed"))
    missing = []
    for ident in identities:
        for part in ("owners", "sponsors"):
            kind, listing = graph.request("GET", f"/v1.0/servicePrincipals/{ident}/microsoft.graph.agentIdentity/{part}?$select=id&$top=1")
            if kind != 200 or not isinstance(listing, dict) or not listing.get("value"):
                missing.append(part)
    if identities:
        found.append(("A365-OWNERS", "FAIL" if missing else "PASS", f"{len(missing)} of {2 * len(identities)} owner and sponsor lists are empty or cannot be read" if missing else "every agent identity has an owner and a sponsor"))
    else:
        found.append(("A365-OWNERS", "UNKNOWN", "there is no agent identity to hold an owner and a sponsor"))
    if account_id and arm is not None:
        status, document = arm.request("GET", f"{account_id}?{ACCOUNT_API}")
        properties = document.get("properties") if isinstance(document, dict) and isinstance(document.get("properties"), dict) else {}
        flag = properties.get("a365LoggingEnabled")
        if status == 200 and isinstance(flag, bool):
            found.append(("A365-LOGGING", "PASS" if flag else "FAIL", "Agent 365 logging is on for the Foundry resource" if flag else "Agent 365 logging is off for the Foundry resource"))
        else:
            found.append(("A365-LOGGING", "UNKNOWN", f"the resource does not show a365LoggingEnabled (HTTP {status}): the property is in preview"))
    else:
        found.append(("A365-LOGGING", "UNKNOWN", "no --account-id was given, so the resource was not read"))
    return found


def selftest() -> int:
    problems: list[str] = []

    class Fake:
        def __init__(self, answers):
            self.answers, self.calls = answers, []

        def request(self, method, path, body=None, **options):
            self.calls.append(method)
            for key, value in self.answers.items():
                if key in path:
                    return value
            return 404, None

    refused = check(Fake({"subscribedSkus": (403, None), "servicePrincipals": (403, None)}), None, "meternaut", "")
    if {state for _, state, _ in refused} != {"UNKNOWN"}:
        problems.append("a Graph that refuses was not UNKNOWN everywhere")
    ident = "11111111-2222-3333-4444-555555555555"
    answers = {"subscribedSkus": (200, {"value": [{"skuId": AGENT_365_SKU, "skuPartNumber": "AGENT_365"}]}), "agentIdentity/owners": (200, {"value": []}),
               "agentIdentity/sponsors": (200, {"value": [{"id": "x"}]}), "agentIdentity?": (200, {"id": ident}), "servicePrincipals?": (200, {"value": [{"id": ident, "displayName": "meternaut-x"}]})}
    fake = Fake(answers)
    found = {control: state for control, state, _ in check(fake, None, "meternaut", "")}
    if found["A365-LICENSE"] != "PASS" or found["A365-IDENTITIES"] != "PASS" or found["A365-OWNERS"] != "FAIL":
        problems.append(f"the checks of a tenant with an agent identity without an owner came out as {found}")
    if set(fake.calls) != {"GET"}:
        problems.append("a call that is not a read was made")
    for line in problems:
        helpers.say(f"selftest FAIL: {line}")
    helpers.say("selftest: " + ("ok" if not problems else f"{len(problems)} problems"))
    return 1 if problems else 0


def main(argv=None, graph=None, arm=None, now=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    commands = parser.add_subparsers(dest="command")
    command = commands.add_parser("run")
    command.add_argument("--name-prefix", default="meternaut")
    command.add_argument("--account-id", default="")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.command != "run":
            parser.error("name the command run, or give --selftest")
        if not PREFIX.fullmatch(args.name_prefix):
            raise Problem("--name-prefix is letters, digits and hyphens", 2)
        if args.account_id and not ACCOUNT_ID.fullmatch(args.account_id):
            raise Problem("--account-id is the resource id of a Foundry resource (Microsoft.CognitiveServices/accounts)", 2)
        graph = graph or helpers.Client(GRAPH, helpers.GRAPH_RESOURCE)
        arm = arm or (helpers.Client("https://management.azure.com", "https://management.azure.com") if args.account_id else None)
        items = check(graph, arm, args.name_prefix, args.account_id)
        emit(items, now or dt.datetime.now(dt.timezone.utc))
        for line in MANUAL:
            helpers.say(line, limit=300)
        counts = {state: sum(1 for _, s, _ in items if s == state) for state in ("PASS", "FAIL", "UNKNOWN")}
        helpers.say(f"agent365-check: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['UNKNOWN']} could not be told or are not applicable")
        return 1 if counts["FAIL"] else 0
    except Problem as error:
        helpers.say(f"error: {error}", sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
