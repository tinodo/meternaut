#!/usr/bin/env python3
"""Reads and prepares the owner's existing API Management instance for the Citadel module (standard library only).

    python tools/gateway-prep.py facts --apim <resource id> --insights <resource id> [--summary <file>]
    python tools/gateway-prep.py attach-identity --apim <resource id> --identity <resource id of a user-assigned identity>
    python tools/gateway-prep.py wait --apim <resource id> [--minutes 90]

It calls the Azure CLI (`az rest`), which the workflow has signed in. Only GitHub Actions may write (AGENTS.md rule 18): the
two writing commands refuse to run anywhere else.

facts            Read only. Prints what the instance and its Application Insights look like now, as JSON, and as a short
                 list for the run's page (--summary): the identity it has, the service-level logging setting that the
                 module replaces (so it can be put back), its loggers, and whether custom metrics may carry dimensions.
                 It fails when the instance is not in the state Succeeded, because an update in progress refuses writes.
attach-identity  Adds one user-assigned identity to the instance and keeps everything else of the identity block: a
                 system-assigned identity that is there stays, and so does every other user-assigned identity. The write is
                 conditional on the ETag that was read with the identity, so a concurrent change fails it instead of being
                 overwritten. It does nothing when the identity is attached already. Then it waits until the update has finished.
prepared         Read only. Checks that the instance is in the state Succeeded, has the identity attached and has the logger
                 appinsights-logger, which the Citadel module needs; says what is missing.
wait             Waits until the instance is in the state Succeeded; fails on Failed or Canceled and when the time is up.
                 A Developer-tier instance inside a network can take a long time for an update and has no service level.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

API = "2024-05-01"
APIM_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.ApiManagement/service/[A-Za-z0-9-]{1,50}$", re.I)
INSIGHTS_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/microsoft\.insights/components/[A-Za-z0-9._()-]{1,260}$", re.I)
IDENTITY_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.ManagedIdentity/userAssignedIdentities/[A-Za-z0-9_-]{1,128}$", re.I)
TERMINAL_BAD = {"failed", "canceled", "cancelled"}
CANON = {"systemassigned": "SystemAssigned", "userassigned": "UserAssigned"}


class Problem(Exception):
    """Something the owner can fix or must know; printed without a trace."""


def az_rest(method: str, resource: str, api: str = API, body: dict | None = None, suffix: str = "", headers: dict | None = None) -> dict:
    url = f"https://management.azure.com{resource}{suffix}?api-version={api}"
    command = [os.environ.get("AZ", "az"), "rest", "--method", method, "--url", url, "--only-show-errors", "--output", "json"]
    if headers:
        command += ["--headers", *[f"{key}={value}" for key, value in headers.items()]]
    if body is not None:
        command += ["--body", json.dumps(body)]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        first = (done.stderr or "").strip().splitlines()[:1]
        raise Problem(f"{method} {resource.rsplit('/', 2)[-2]}/{resource.rsplit('/', 1)[-1]} failed: {first[0] if first else 'no message'}")
    return json.loads(done.stdout) if done.stdout.strip() else {}


def merged_identity(current: dict | None, identity_id: str) -> tuple[dict | None, bool]:
    """The identity block that adds one user-assigned identity and keeps the rest, and whether that changes anything."""
    current = current or {}
    users = dict(current.get("userAssignedIdentities") or {})
    if identity_id.lower() in {key.lower() for key in users}:
        return None, False
    kinds = {CANON[part.strip().lower()] for part in (current.get("type") or "").split(",") if part.strip().lower() in CANON}
    kinds.add("UserAssigned")
    order = sorted(kinds, key=lambda k: (k != "SystemAssigned", k))
    return {"type": ", ".join(order), "userAssignedIdentities": {**{key: {} for key in users}, identity_id: {}}}, True


def wait_until_succeeded(read_state, minutes: float, sleep=time.sleep, clock=time.monotonic, interval: float = 30.0) -> str:
    deadline = clock() + minutes * 60
    while True:
        state = (read_state() or "").strip()
        if state.lower() == "succeeded":
            return state
        if state.lower() in TERMINAL_BAD:
            raise Problem(f"the instance is in the state {state}: nothing more is written to it until its owner has looked at it")
        if clock() >= deadline:
            raise Problem(f"the instance is still in the state {state or 'unknown'} after {minutes:g} minutes")
        print(f"The instance is in the state {state or 'unknown'}; waiting.", flush=True)
        sleep(interval)


def provisioning_state(apim: str) -> str:
    return az_rest("get", apim).get("properties", {}).get("provisioningState", "")


def only_in_actions() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise Problem("this command writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)")


def facts(apim: str, insights: str) -> tuple[dict, str]:
    service = az_rest("get", apim)
    props = service.get("properties", {})
    state = props.get("provisioningState", "")
    identity = service.get("identity") or {}
    diag = az_rest("get", apim, suffix="/diagnostics/applicationinsights").get("properties", {})
    loggers = az_rest("get", apim, suffix="/loggers").get("value", [])
    component = az_rest("get", insights, api="2020-02-02").get("properties", {})
    document = {
        "state": state,
        "sku": service.get("sku", {}),
        "virtualNetworkType": props.get("virtualNetworkType"),
        "identity": {
            "type": identity.get("type", "None"),
            "userAssigned": sorted((identity.get("userAssignedIdentities") or {}).keys()),
        },
        "serviceLevelLogging": diag,
        "loggers": sorted(item.get("name", "") for item in loggers),
        "customMetricsOptedInType": component.get("CustomMetricsOptedInType"),
    }
    dimensions = (document["customMetricsOptedInType"] or "").lower() == "withdimensions"
    lines = [
        "### The gateway before the change",
        "",
        f"- State: `{state}`; tier: `{document['sku'].get('name')}`; network mode: `{document['virtualNetworkType']}`.",
        f"- Identity: `{document['identity']['type']}`; user-assigned: {len(document['identity']['userAssigned'])}.",
        f"- Loggers: {', '.join('`' + name + '`' for name in document['loggers']) or 'none'}.",
        "- Service-level logging setting that the module replaces, complete, as the instance holds it (put these values back to undo it):",
        "",
        "```json",
        json.dumps(document["serviceLevelLogging"], indent=2),
        "```",
        "",
        f"- Custom metrics with dimensions on the Application Insights component: **{'on' if dimensions else 'off'}** (`{document['customMetricsOptedInType']}`)."
        + ("" if dimensions else " Token counts are still emitted, but cannot be split by contract or model until the owner turns on alerting on custom metric dimensions for the component; nothing here changes it."),
    ]
    if state.lower() != "succeeded":
        raise Problem(f"the instance is in the state {state or 'unknown'}: an update is in progress or failed, and it refuses writes")
    return document, "\n".join(lines) + "\n"


def attach_identity(apim: str, identity_id: str, minutes: float, tries: int = 3, sleep=None) -> None:
    """Adds the identity with one conditional write: the identity block is read together with its ETag, and the write
    carries it as If-Match, so a change made to the instance in between (another identity attached, say) fails the write
    with 412 instead of being overwritten by a stale copy. The read is then made again, up to three times."""
    for attempt in range(1, tries + 1):
        service = az_rest("get", apim)
        state = service.get("properties", {}).get("provisioningState", "")
        if state.lower() != "succeeded":
            raise Problem(f"the instance is in the state {state or 'unknown'}: an update is in progress or failed, and it refuses writes")
        body, changes = merged_identity(service.get("identity"), identity_id)
        if not changes:
            print("The identity is attached already; nothing to do.")
            return
        etag = service.get("etag")
        print(f"Adding the user-assigned identity; the identity block becomes: {body['type']}.")
        try:
            az_rest("patch", apim, body={"identity": body}, headers={"If-Match": etag} if etag else None)
        except Problem as e:
            if attempt < tries and ("PreconditionFailed" in str(e) or "412" in str(e)):
                print("The instance changed while it was being read; reading it again.")
                (sleep or time.sleep)(5)
                continue
            raise
        wait_until_succeeded(lambda: provisioning_state(apim), minutes)
        print("The update has finished.")
        return


def prepared(apim: str, identity_id: str) -> list[str]:
    """What is missing before the Citadel module may be applied: the state, the attached identity and the logger."""
    service = az_rest("get", apim)
    missing = []
    state = service.get("properties", {}).get("provisioningState", "")
    if state.lower() != "succeeded":
        missing.append(f"the instance is in the state {state or 'unknown'}, not Succeeded")
    attached = {key.lower() for key in ((service.get("identity") or {}).get("userAssignedIdentities") or {})}
    if identity_id.lower() not in attached:
        missing.append("the gateway identity is not attached to the instance")
    names = {item.get("name") for item in az_rest("get", apim, suffix="/loggers").get("value", [])}
    if "appinsights-logger" not in names:
        missing.append("the logger appinsights-logger is not on the instance")
    return missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    f = commands.add_parser("facts")
    f.add_argument("--apim", required=True)
    f.add_argument("--insights", required=True)
    f.add_argument("--summary", help="append a short list for the run's page to this file")
    a = commands.add_parser("attach-identity")
    a.add_argument("--apim", required=True)
    a.add_argument("--identity", required=True)
    a.add_argument("--minutes", type=float, default=90)
    p = commands.add_parser("prepared")
    p.add_argument("--apim", required=True)
    p.add_argument("--identity", required=True)
    w = commands.add_parser("wait")
    w.add_argument("--apim", required=True)
    w.add_argument("--minutes", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        if not APIM_ID.match(args.apim):
            raise Problem("--apim is the resource id of an API Management instance")
        if args.command == "facts":
            if not INSIGHTS_ID.match(args.insights):
                raise Problem("--insights is the resource id of an Application Insights component")
            document, summary = facts(args.apim, args.insights)
            print(json.dumps(document, indent=2))
            if args.summary:
                with open(args.summary, "a", encoding="utf-8") as handle:
                    handle.write(summary)
        elif args.command == "attach-identity":
            only_in_actions()
            if not IDENTITY_ID.match(args.identity):
                raise Problem("--identity is the resource id of a user-assigned managed identity")
            attach_identity(args.apim, args.identity, args.minutes)
        elif args.command == "prepared":
            if not IDENTITY_ID.match(args.identity):
                raise Problem("--identity is the resource id of a user-assigned managed identity")
            missing = prepared(args.apim, args.identity)
            if missing:
                raise Problem("the gateway is not ready for the Citadel module: " + "; ".join(missing) + ". Run gateway-prepare first")
            print("The gateway is ready for the Citadel module.")
        else:
            wait_until_succeeded(lambda: provisioning_state(args.apim), args.minutes)
            print("The instance is in the state Succeeded.")
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
