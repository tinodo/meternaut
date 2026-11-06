#!/usr/bin/env python3
"""Reads the Foundry resource of the agents back from Azure and fails unless it is as its template says (standard library only).

    python tools/foundry-check.py read-back --subscription S --resource-group G --account A --project P --guardrail R \
        --private-endpoint PE --endpoint URL --models environment/models.json [--summary FILE]

A deployment that says Succeeded does not say that the resource came out as the template wrote it: tenant policies with the effect Modify rewrite a
resource while it is made, and a Modify policy does not refuse anything (AGENTS.md rule 19). So what the design rests on is read back, and the run fails
for each thing that differs:

  - the Foundry resource: public network access Disabled, local authentication off (disableLocalAuth), project management on (allowProjectManagement,
    which cannot be switched on later), and an identity of its own;
  - its private endpoint: made, and approved;
  - its project: there, with an identity of its own, and an endpoint that is the one that the cases app is given;
  - its model deployments: every model of environment/models.json, with its version, its deployment type and its capacity, and the guardrail;
  - the guardrail: there, with the Prompt Shields that the agents need, blocking;
  - the connection of the project to Application Insights: there, and with an identity and no key.

It only reads: GET requests of Azure Resource Manager through `az rest`. No key is listed and nothing of the data plane is called (the resource has no public
endpoint, and the runner is not in the network). It prints names and states, never a value that is a secret, and writes the same lines to --summary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

API = "2026-09-01"
NETWORK_API = "2025-05-01"
ARM = "https://management.azure.com"
NOT_FOUND = re.compile(r"NotFound|ResourceNotFound|\b404\b", re.I)
# A connection that sends traces with an identity. The portal calls it "Project managed identity"; the template writes ProjectManagedIdentity.
ENTRA_AUTH_TYPES = ("ProjectManagedIdentity", "AAD", "ManagedIdentity")
# What the guardrail must hold: (name, source) of a Prompt Shield, each blocking.
SHIELDS = (("Jailbreak", "Prompt"), ("Indirect Attack", "Prompt"), ("Indirect Attack", "PostToolCall"))

Runner = Callable[[list[str]], tuple[int, str, str]]


class Gone(Exception):
    """Azure says that the resource is not there."""


class Unreadable(Exception):
    """Azure gave no usable answer. The text is the first line of its error, which holds no token."""


def run_az(arguments: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *arguments], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def get(az: Runner, path: str, api: str) -> dict:
    code, out, err = az(["rest", "--method", "get", "--url", f"{ARM}{path}?api-version={api}", "--output", "json"])
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


def read_models(path: Path) -> list[dict]:
    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit(f"error: {path} is not a readable JSON list of models")
    if not isinstance(models, list) or not models or any(not isinstance(m, dict) or not {"name", "version", "sku", "capacity"} <= set(m) for m in models):
        raise SystemExit(f"error: {path} is not a list of models with name, version, sku and capacity")
    return models


def read_back(az: Runner, subscription: str, group: str, account: str, project: str, guardrail: str, private_endpoint: str, endpoint: str,
              models: list[dict]) -> list[tuple[bool, str]]:
    """One (ok, text) per thing that was read. A thing that cannot be read is a failure too."""
    found: list[tuple[bool, str]] = []
    base = f"/subscriptions/{subscription}/resourceGroups/{group}/providers"
    resource = f"{base}/Microsoft.CognitiveServices/accounts/{account}"

    def say(ok: bool, text: str) -> None:
        found.append((ok, text))

    def fetch(label: str, path: str, api: str = API) -> dict | None:
        try:
            return get(az, path, api)
        except Gone:
            say(False, f"{label} is not there")
        except Unreadable as e:
            say(False, f"{label} could not be read: {e}")
        return None

    document = fetch(f"The Foundry resource {account}", resource)
    if document is not None:
        properties = document.get("properties") or {}
        identity = document.get("identity") or {}
        for label, ok in (("public network access is Disabled", properties.get("publicNetworkAccess") == "Disabled"),
                          ("local authentication is off (disableLocalAuth)", properties.get("disableLocalAuth") is True),
                          ("project management is on (allowProjectManagement)", properties.get("allowProjectManagement") is True),
                          ("it has an identity of its own", bool(identity.get("principalId"))),
                          ("its kind is AIServices", document.get("kind") == "AIServices")):
            say(ok, f"The Foundry resource: {label}" if ok else f"The Foundry resource differs from its template: {label} is not so")

    document = fetch(f"The private endpoint {private_endpoint}", f"{base}/Microsoft.Network/privateEndpoints/{private_endpoint}", NETWORK_API)
    if document is not None:
        properties = document.get("properties") or {}
        states = [((c.get("properties") or {}).get("privateLinkServiceConnectionState") or {}).get("status")
                  for c in (properties.get("privateLinkServiceConnections") or []) + (properties.get("manualPrivateLinkServiceConnections") or [])]
        say(properties.get("provisioningState") == "Succeeded" and states == ["Approved"], f"The private endpoint {private_endpoint}: "
            + ("made and approved" if properties.get("provisioningState") == "Succeeded" and states == ["Approved"] else f"is not made and approved (state {properties.get('provisioningState')}, connections {states})"))

    document = fetch(f"The project {project}", f"{resource}/projects/{project}")
    if document is not None:
        say(bool((document.get("identity") or {}).get("principalId")), f"The project {project}: " + ("there, with an identity of its own"
            if (document.get("identity") or {}).get("principalId") else "has no identity of its own"))
        given = ((document.get("properties") or {}).get("endpoints") or {}).get("AI Foundry API")
        if given is not None:
            same = str(given).rstrip("/").lower() == endpoint.rstrip("/").lower()
            say(same, "The project endpoint is the one that the cases app is given" if same else f"The project endpoint that Azure reports ({given}) is not the one that the cases app is given ({endpoint})")

    document = fetch("The model deployments", f"{resource}/deployments")
    if document is not None:
        deployed = {d.get("name"): d for d in document.get("value") or [] if isinstance(d, dict)}
        for model in models:
            d = deployed.get(model["name"])
            if d is None:
                say(False, f"The deployment {model['name']} is not there")
                continue
            made = (d.get("properties") or {}).get("model") or {}
            problems = [word for word, ok in (("model", made.get("name") == model["name"]), ("version", made.get("version") == model["version"]),
                                                ("deployment type", (d.get("sku") or {}).get("name") == model["sku"]),
                                                ("capacity", (d.get("sku") or {}).get("capacity") == model["capacity"]),
                                                ("guardrail", (d.get("properties") or {}).get("raiPolicyName") == guardrail)) if not ok]
            say(not problems, f"The deployment {model['name']}: " + (f"{model['version']}, {model['sku']}, {model['capacity']} thousand tokens a minute, guardrail {guardrail}"
                                                                    if not problems else f"differs from environment/models.json or its template: {', '.join(problems)}"))

    document = fetch(f"The guardrail {guardrail}", f"{resource}/raiPolicies/{guardrail}")
    if document is not None:
        filters = (document.get("properties") or {}).get("contentFilters") or []
        for name, source in SHIELDS:
            ok = any(isinstance(f, dict) and f.get("name") == name and f.get("source") == source and f.get("enabled") is True and f.get("blocking") is True for f in filters)
            say(ok, f"The guardrail blocks {name} at {source}" if ok else f"The guardrail does not block {name} at {source}")

    document = fetch(f"The connections of the project {project}", f"{resource}/projects/{project}/connections")
    if document is not None:
        traces = [c for c in document.get("value") or [] if isinstance(c, dict) and (c.get("properties") or {}).get("category") == "AppInsights"]
        kinds = [(c.get("properties") or {}).get("authType") for c in traces]
        ok = len(traces) == 1 and kinds[0] in ENTRA_AUTH_TYPES
        say(ok, "The project sends its traces to Application Insights with its identity" if ok else f"The project's connection to Application Insights is missing or is not made with an identity (found {len(traces)}, authentication {kinds})")
    return found


def main(argv=None, az: Runner = run_az) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("read-back", help="read the Foundry resource back and fail unless it is as its template says")
    for name in ("subscription", "resource-group", "account", "project", "guardrail", "private-endpoint", "endpoint", "models"):
        check.add_argument(f"--{name}", required=True)
    check.add_argument("--summary", help="a file to append the lines to as Markdown (the step summary of a workflow run)")
    args = parser.parse_args(argv)
    findings = read_back(az, args.subscription, args.resource_group, args.account, args.project, args.guardrail, args.private_endpoint, args.endpoint,
                         read_models(Path(args.models)))
    lines = [f"{'ok' if ok else 'FAILED'}: {text}" for ok, text in findings]
    print("\n".join(lines))
    failed = [text for ok, text in findings if not ok]
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(f"### The Foundry resource, read back from Azure\n\nProject endpoint: `{args.endpoint}`\n\n```\n" + "\n".join(lines) + "\n```\n")
    if failed:
        print(f"{len(failed)} thing(s) differ from what the template says. The run fails; nothing is repaired from here.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
