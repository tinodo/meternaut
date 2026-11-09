#!/usr/bin/env python3
"""Reads the Foundry resource of the agents back from Azure and fails unless it is as its template says (standard library only).

    python tools/foundry-check.py read-back --subscription S --resource-group G --account A --project P --guardrail R \
        --private-endpoint PE --endpoint URL --models environment/models.json [--ai-gateway-host HOST --connection NAME] [--summary FILE] [--timeout SECONDS]

A deployment that says Succeeded does not say that the resource came out as the template wrote it: tenant policies with the effect Modify rewrite a
resource while it is made, and a Modify policy does not refuse anything (AGENTS.md rule 19). So what the design rests on is read back, and the run fails
for each thing that differs:

  - the Foundry resource: public network access Disabled, local authentication off (disableLocalAuth), project management on (allowProjectManagement,
    which cannot be switched on later), and an identity of its own;
  - its private endpoint: made, and approved;
  - its project: there, with an identity of its own, and an endpoint that is reported and is the one that the cases app is given;
  - its model deployments: every model of environment/models.json, with its version, its deployment type and its capacity (`agentCapacity` of the model, which is the
    capacity of this resource and not the one of the model account), and the guardrail;
  - the guardrail: there, with every filter of REQUIRED_FILTERS (the harm filters from the severity Medium, profanity, protected material and the Prompt Shields of the agents), each on and blocking;
  - the connection of the project to Application Insights: there, and with an identity and no key;
  - only with --ai-gateway-host and --connection (the switch of the agents' route through the AI Gateway is on, docs/proposals/08-ai-gateway.md, step 2): the connection of the project to the
    gateway, read with a GET of its own and held to what the template writes: the category ApiManagement, the authentication ProjectManagedIdentity (the project's own identity), the audience
    https://azure-api.net/aigateway, the target (the gateway's host with the path /default/models/openai/v1), the model not in the path, the models listed by their aliases with the versions of
    environment/models.json, not shared, and no credentials. The service does not return a secret, and nothing of its answer is printed but fixed words, the names of the models, a few plain values
    and the names (never the values) of credentials, if there were any. Whether the Agent Service can call the gateway through it is not read here: only a run of the agents shows that.

It only reads: GET requests of Azure Resource Manager through `az rest`. No key is listed and nothing of the data plane is called (the resource has no public
endpoint, and the runner is not in the network). A list is read to its end (nextLink is followed, to addresses of Azure Resource Manager only), and no read waits longer
than --timeout seconds: a stuck `az` fails the run with a message instead of holding it to the limit of the job. It prints names and states, never a value that is a
secret, and writes the same lines to --summary.
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
from urllib.parse import urlsplit

API = "2026-09-01"
NETWORK_API = "2025-05-01"
ARM = "https://management.azure.com"
NOT_FOUND = re.compile(r"NotFound|ResourceNotFound|\b404\b", re.I)
# How long one read of Azure may take, and how many pages one list may have.
TIMEOUT_SECONDS = 120
MAX_PAGES = 20
# A connection that sends traces with an identity. The portal calls it "Project managed identity"; the template writes ProjectManagedIdentity.
ENTRA_AUTH_TYPES = ("ProjectManagedIdentity", "AAD", "ManagedIdentity")
# What the guardrail must hold, one entry per content filter: (name, source, severity). Each must be in the policy, on and blocking, and where a severity is given the threshold must be that one.
# This is the one definition: tools/drift-check.py loads it, and environment/foundry/main.bicep declares exactly these filters (a test holds the two together). The names and sources are the ones that the
# audit initiative "[Preview]: Guardrail for Cognitive Services Deployments" looks for (its policies are in Azure/azure-policy, built-in-policies/policyDefinitions/Cognitive Services); it takes the severity
# Medium or High for the harm filters and the template holds Medium. The Prompt Shields that the agents need are Jailbreak and Indirect Attack at Prompt and Indirect Attack at PostToolCall (the tool
# results, which the initiative does not ask for); Indirect Attack Spotlighting at Prompt is the initiative's own.
HARM_SEVERITY = "Medium"
REQUIRED_FILTERS = (
    ("Hate", "Prompt", HARM_SEVERITY), ("Hate", "Completion", HARM_SEVERITY),
    ("Sexual", "Prompt", HARM_SEVERITY), ("Sexual", "Completion", HARM_SEVERITY),
    ("Violence", "Prompt", HARM_SEVERITY), ("Violence", "Completion", HARM_SEVERITY),
    ("Selfharm", "Prompt", HARM_SEVERITY), ("Selfharm", "Completion", HARM_SEVERITY),
    ("Profanity", "Prompt", None), ("Profanity", "Completion", None),
    ("Protected Material Code", "Completion", None), ("Protected Material Text", "Completion", None),
    ("Jailbreak", "Prompt", None), ("Indirect Attack", "Prompt", None), ("Indirect Attack Spotlighting", "Prompt", None),
    ("Indirect Attack", "PostToolCall", None),
)
# The connection to the AI Gateway (environment/foundry/main.bicep): the audience of the gateway's tokens, the base of its OpenAI route, and the host names that the service gives a gateway.
GATEWAY_AUDIENCE = "https://azure-api.net/aigateway"
GATEWAY_PATH = "/default/models/openai/v1"
GATEWAY_HOST = re.compile(r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.ai\.gateway\.azure\.com$")
CONNECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")

Runner = Callable[[list[str]], tuple[int, str, str]]


class Gone(Exception):
    """Azure says that the resource is not there."""


class Unreadable(Exception):
    """Azure gave no usable answer. The text is the first line of its error, which holds no token."""


class Stuck(Exception):
    """`az` did not answer in time. The rest is not read: a second read would wait just as long."""


def describe(arguments: list[str]) -> str:
    """Which request it was, for a message: the address without its query, or a plain word when the arguments name none."""
    if "--url" in arguments and arguments.index("--url") + 1 < len(arguments):
        return "GET " + arguments[arguments.index("--url") + 1].split("?")[0].replace(ARM, "")
    return "a request"


def run_az(arguments: list[str], timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    try:
        done = subprocess.run([os.environ.get("AZ", "az"), *arguments], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Stuck(f"az did not answer within {timeout} seconds ({describe(arguments)})")
    return done.returncode, done.stdout, done.stderr


def get_url(az: Runner, url: str) -> dict:
    code, out, err = az(["rest", "--method", "get", "--url", url, "--output", "json"])
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


def get(az: Runner, path: str, api: str) -> dict:
    return get_url(az, f"{ARM}{path}?api-version={api}")


def get_all(az: Runner, path: str, api: str) -> list:
    """Every item of a list that Azure gives in pages: nextLink is followed until there is none, to addresses of Azure Resource Manager only, and for a limited number of pages."""
    items: list = []
    document = get(az, path, api)
    pages = 1
    while True:
        items.extend(document.get("value") or [])
        link = document.get("nextLink")
        if not link:
            return items
        if pages >= MAX_PAGES:
            raise Unreadable(f"the list has more than {MAX_PAGES} pages")
        if not isinstance(link, str) or not link.startswith(ARM + "/"):
            raise Unreadable("the list goes on at an address that is not of Azure Resource Manager, and that is not followed")
        try:
            document = get_url(az, link)
        except Gone:
            raise Unreadable("a later page of the list is not there")
        pages += 1


def read_models(path: Path) -> list[dict]:
    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit(f"error: {path} is not a readable JSON list of models")
    if not isinstance(models, list) or not models or any(not isinstance(m, dict) or not {"name", "version", "sku", "capacity"} <= set(m) for m in models):
        raise SystemExit(f"error: {path} is not a list of models with name, version, sku and capacity")
    return models


def plain(value: object, limit: int = 60) -> str:
    """A value of an answer as it may be printed: letters, digits and . _ : / - only, cut, and never two colons in a row. Nothing else of an answer is ever printed."""
    text = re.sub(r"[^A-Za-z0-9._:/ -]", "?", "" if value is None else str(value)).replace("::", ": :")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def wrong_filters(filters: object) -> list[tuple[str, str, str]]:
    """The required filters that the guardrail's content filters do not hold, as (name, source, reason); none when it holds them all. Azure may return the filters of the base policy beside the guardrail's
    own, so every entry that names a filter at a source is held to it: one that is off, not blocking or at another severity is a failure even when another entry for the same filter is right."""
    entries = [f for f in filters if isinstance(f, dict)] if isinstance(filters, list) else []
    wrong = []
    for name, source, severity in REQUIRED_FILTERS:
        named = [f for f in entries if f.get("name") == name and f.get("source") == source]
        if not named:
            reason = "not in the policy"
        elif not all(f.get("enabled") is True for f in named):
            reason = "not enabled"
        elif not all(f.get("blocking") is True for f in named):
            reason = "not blocking"
        elif severity and not all(f.get("severityThreshold") == severity for f in named):
            seen = sorted({plain(f.get("severityThreshold")) or "not set" for f in named})
            reason = f"severity {' and '.join(seen)}, not {severity}"
        else:
            continue
        wrong.append((name, source, reason))
    return wrong


def blocked_in_words() -> str:
    """What REQUIRED_FILTERS makes the guardrail block, as plain words for a PASS text: the filters that share their sources and severity, each group once."""
    groups: dict[tuple[tuple[str, ...], str | None], list[str]] = {}
    for name in dict.fromkeys(n for n, _, _ in REQUIRED_FILTERS):
        rows = [(source, severity) for n, source, severity in REQUIRED_FILTERS if n == name]
        groups.setdefault((tuple(source for source, _ in rows), rows[0][1]), []).append(name)

    def listed(items: list[str]) -> str:
        return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"

    return "; ".join(f"{listed(names)} at {listed(list(sources))}" + (f" from the severity {severity}" if severity else "") for (sources, severity), names in groups.items())


def gateway_connection(document: dict, host: str, connection: str, models: list[dict]) -> list[tuple[bool, str]]:
    """One (ok, text) for each thing that the connection of the project to the AI Gateway has to be, read from the answer of Azure for it.

    The answer is held to what environment/foundry/main.bicep writes: the category ApiManagement with the project's managed identity (ProjectManagedIdentity), the audience of the gateway's tokens, the
    base of the gateway's OpenAI route on its host, the model not in the path, the models listed by their aliases (the deployments' names, with their versions), not shared, and no credentials. The
    service does not return a secret, and this does not print one: it prints fixed words, the names of the models, a few plain values and the names (never the values) of any credentials."""
    properties = document.get("properties") or {}
    metadata = properties.get("metadata") if isinstance(properties.get("metadata"), dict) else {}
    found: list[tuple[bool, str]] = []
    category, auth = properties.get("category"), properties.get("authType")
    good = category == "ApiManagement" and auth == "ProjectManagedIdentity"
    found.append((good, f"The connection {connection} to the AI Gateway is of the category ApiManagement and authenticates with the project's own identity (ProjectManagedIdentity)" if good
                  else f"The connection {connection} differs from its template: its category is {plain(category)} and its authentication {plain(auth)}, not ApiManagement and ProjectManagedIdentity"))
    audience = properties.get("audience")
    found.append((audience == GATEWAY_AUDIENCE, f"The connection's audience is {GATEWAY_AUDIENCE}, the one that the gateway asks a token for" if audience == GATEWAY_AUDIENCE
                  else f"The connection's audience is not {GATEWAY_AUDIENCE}: " + (f"the service reports {plain(audience)}" if audience else "the service reports none (it may not return the property: the portal shows it)")))
    target = properties.get("target")
    parts = urlsplit(target if isinstance(target, str) else "")
    right_host = parts.scheme == "https" and (parts.hostname or "").lower() == host.lower() and parts.port is None and not parts.username
    right_path = parts.path.rstrip("/") == GATEWAY_PATH and not parts.query and not parts.fragment
    if right_host and right_path:
        said = f"The connection's target is the gateway's host with the path {GATEWAY_PATH}"
    elif not isinstance(target, str) or not target:
        said = "The connection has no target"
    elif right_host:
        said = (f"The connection's target is on the gateway's host and its path is {plain(parts.path)}"
                + (" with a query or a fragment" if parts.query or parts.fragment else "") + f", and it has to be {GATEWAY_PATH}")
    else:
        said = f"The connection's target is not on the gateway's host (its path is {plain(parts.path)}, and it has to be {GATEWAY_PATH})"
    found.append((right_host and right_path, said))
    credentials = properties.get("credentials")
    clean = credentials is None or credentials == {}
    named = ", ".join(sorted(plain(k, 30) for k in credentials)[:5]) if isinstance(credentials, dict) else "a value that is not an object"
    found.append((clean, "The connection holds no credentials: the project's identity is the credential" if clean
                  else f"The connection holds credentials (names only: {named}). No key is used by this project (AGENTS.md rule 23)"))
    shared = properties.get("isSharedToAll")
    found.append((shared is not True, "The connection is not shared with the other projects of the resource" if shared is not True
                  else "The connection is shared with every project of the resource, and the template does not share it"))
    in_path = str(metadata.get("deploymentInPath", "")).lower()
    found.append((in_path == "false", "The model is sent in the body of the request, not in the path (deploymentInPath is false), where the gateway reads the alias" if in_path == "false"
                  else f"deploymentInPath is {plain(metadata.get('deploymentInPath')) or 'not set'}, and it has to be false: the gateway reads the alias from the body"))
    listed = metadata.get("models")
    try:
        entries = json.loads(listed) if isinstance(listed, str) else listed
    except ValueError:
        entries = None
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
        found.append((False, "The connection lists no models that can be read (metadata.models is not a list of models)"))
    else:
        by_name = {e.get("name"): ((e.get("properties") or {}).get("model") or {}) for e in entries}
        missing = [m["name"] for m in models if by_name.get(m["name"]) is None]
        wrong = [m["name"] for m in models if m["name"] in by_name and (by_name[m["name"]].get("name") != m["name"] or by_name[m["name"]].get("version") != m["version"]
                                                                        or by_name[m["name"]].get("format") != "OpenAI")]
        extra = sorted(plain(n, 40) for n in by_name if n not in {m["name"] for m in models})
        ok = not missing and not wrong and not extra and len(entries) == len(models)
        names = ", ".join(m["name"] for m in models)
        found.append((ok, f"The connection lists the models {names}: each named by its alias, with the version of environment/models.json" if ok
                      else "The connection's list of models differs from environment/models.json: " + "; ".join(
                          part for part in (f"missing {', '.join(missing)}" if missing else "", f"another model or version for {', '.join(wrong)}" if wrong else "",
                                            f"not an alias of the gateway: {', '.join(extra)}" if extra else "", "a model is listed twice" if len(entries) != len(by_name) else "") if part)))
    return found


def read_back(az: Runner, subscription: str, group: str, account: str, project: str, guardrail: str, private_endpoint: str, endpoint: str,
              models: list[dict], gateway_host: str = "", connection: str = "") -> list[tuple[bool, str]]:
    """One (ok, text) per thing that was read. A thing that cannot be read is a failure too. With a gateway host (the switch of the agents' route through the AI Gateway is on) the project's
    connection to the gateway is read back too, with a GET of its own."""
    found: list[tuple[bool, str]] = []
    halted: list[str] = []
    base = f"/subscriptions/{subscription}/resourceGroups/{group}/providers"
    resource = f"{base}/Microsoft.CognitiveServices/accounts/{account}"

    def say(ok: bool, text: str) -> None:
        found.append((ok, text))

    def fetch(label: str, path: str, api: str = API, pages: bool = False) -> dict | list | None:
        """The document at the path, or all items of the list there (pages=True). Once az has not answered in time nothing more is read."""
        if halted:
            return None
        try:
            return get_all(az, path, api) if pages else get(az, path, api)
        except Gone:
            say(False, f"{label} is not there")
        except Unreadable as e:
            say(False, f"{label} could not be read: {e}")
        except Stuck as e:
            halted.append(str(e))
            say(False, f"{label} could not be read: {e}. The read-back stops here: nothing after it was read")
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
        if not given:
            say(False, "The project does not report its endpoint (properties.endpoints['AI Foundry API']), so the address that the cases app is given cannot be checked")
        else:
            same = str(given).rstrip("/").lower() == endpoint.rstrip("/").lower()
            say(same, "The project endpoint is the one that the cases app is given" if same else f"The project endpoint that Azure reports ({given}) is not the one that the cases app is given ({endpoint})")

    items = fetch("The model deployments", f"{resource}/deployments", pages=True)
    if items is not None:
        deployed = {d.get("name"): d for d in items if isinstance(d, dict)}
        for model in models:
            d = deployed.get(model["name"])
            if d is None:
                say(False, f"The deployment {model['name']} is not there")
                continue
            made = (d.get("properties") or {}).get("model") or {}
            capacity = model.get("agentCapacity", model["capacity"])  # the resource of the agents has a capacity of its own
            problems = [word for word, ok in (("model", made.get("name") == model["name"]), ("version", made.get("version") == model["version"]),
                                                ("deployment type", (d.get("sku") or {}).get("name") == model["sku"]),
                                                ("capacity", (d.get("sku") or {}).get("capacity") == capacity),
                                                ("guardrail", (d.get("properties") or {}).get("raiPolicyName") == guardrail)) if not ok]
            say(not problems, f"The deployment {model['name']}: " + (f"{model['version']}, {model['sku']}, {capacity} thousand tokens a minute, guardrail {guardrail}"
                                                                    if not problems else f"differs from environment/models.json or its template: {', '.join(problems)}"))

    document = fetch(f"The guardrail {guardrail}", f"{resource}/raiPolicies/{guardrail}")
    if document is not None:
        wrong = {(name, source): reason for name, source, reason in wrong_filters((document.get("properties") or {}).get("contentFilters"))}
        for name, source, severity in REQUIRED_FILTERS:
            if (name, source) in wrong:
                say(False, f"The guardrail does not block {name} at {source}: {wrong[(name, source)]}")
            else:
                say(True, f"The guardrail blocks {name} at {source}" + (f" from the severity {severity}" if severity else ""))

    items = fetch(f"The connections of the project {project}", f"{resource}/projects/{project}/connections", pages=True)
    if items is not None:
        traces = [c for c in items if isinstance(c, dict) and (c.get("properties") or {}).get("category") == "AppInsights"]
        kinds = [(c.get("properties") or {}).get("authType") for c in traces]
        ok = len(traces) == 1 and kinds[0] in ENTRA_AUTH_TYPES
        say(ok, "The project sends its traces to Application Insights with its identity" if ok else f"The project's connection to Application Insights is missing or is not made with an identity (found {len(traces)}, authentication {kinds})")
    if gateway_host:
        document = fetch(f"The connection {connection} to the AI Gateway", f"{resource}/projects/{project}/connections/{connection}")
        if document is not None:
            found.extend(gateway_connection(document, gateway_host, connection, models))
    return found


def main(argv=None, az: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("read-back", help="read the Foundry resource back and fail unless it is as its template says")
    for name in ("subscription", "resource-group", "account", "project", "guardrail", "private-endpoint", "endpoint", "models"):
        check.add_argument(f"--{name}", required=True)
    check.add_argument("--summary", help="a file to append the lines to as Markdown (the step summary of a workflow run)")
    check.add_argument("--ai-gateway-host", default="", help="the host name of the AI Gateway: given, the project's connection to it is read back too (the switch of the agents' route is on); needs --connection")
    check.add_argument("--connection", default="", help="the name of the project's connection to the AI Gateway; needs --ai-gateway-host")
    check.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS, help=f"seconds that one read of Azure may take (default {TIMEOUT_SECONDS}); a read that takes longer fails the run")
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout is a number of seconds, one or more")
    if bool(args.ai_gateway_host) != bool(args.connection):
        parser.error("--ai-gateway-host and --connection go together")
    if args.ai_gateway_host and (not GATEWAY_HOST.match(args.ai_gateway_host) or not CONNECTION_NAME.match(args.connection)):
        parser.error("--ai-gateway-host is the host name that the service reports for the AI Gateway (under .ai.gateway.azure.com) and --connection the name of a connection")
    runner = az or (lambda arguments: run_az(arguments, args.timeout))
    findings = read_back(runner, args.subscription, args.resource_group, args.account, args.project, args.guardrail, args.private_endpoint, args.endpoint,
                         read_models(Path(args.models)), args.ai_gateway_host, args.connection)
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
