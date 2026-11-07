#!/usr/bin/env python3
"""The helpers of the check tools that run in the Operator (standard library only): tools/cases-check.py loads this file from its own folder.

It calls the Azure CLI, which the workflow has signed in. The tokens that the CLI hands out are used and never printed. What it holds:

  * the object id of the identity that the CLI is signed in as, read from the claims of its own token (the workflow's identity may not read the directory): the Hub workflow
    uses it to find the deploy identity's own role assignment on the control hub of the cases, which the action cases retires (no template gives that identity a role there any
    more, because the Operator sends the control events);
  * one event to a control hub, with the identity that the CLI is signed in as: in the Hub workflow that is the Operator's identity, which holds Azure Event Hubs Data Sender on
    that hub, and the tool runs inside the network, because the namespace takes no public traffic. Only a GitHub Actions run may send the event (AGENTS.md rule 18);
  * the telemetry of the app, read the way --query-via says:
      arm         The default. The query goes to Azure Resource Manager (POST <component>/query). Learn says that such a query cannot use an Azure
                  Monitor private link, so it works only while the component accepts queries from public networks.
      data-plane  The query goes to https://api.applicationinsights.io/v1/apps/<Application ID>/query with a Microsoft Entra token for that resource.
                  It is the way in for a component that is private, so it is run from inside the network (docs/proposals/07-private-by-default.md),
                  where that name resolves to the private endpoint. The identity needs the Reader or the Monitoring Reader role on the component, or
                  above it. The Application ID is read once through Resource Manager, a read of the control plane that works while the component is
                  private, and it is read before the event is sent: a component that cannot be read stops the run first.

It began as the checker of the usage recording, which was removed on 2026-11-07; what the checker of the cases needs of it stayed.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

SITE_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.Web/sites/[A-Za-z0-9-]{2,60}$", re.I)
INSIGHTS_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.Insights/components/[A-Za-z0-9._()-]{1,260}$", re.I)
NAMESPACE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{4,49}$")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SITE_API = "2024-04-01"
QUERY_API = "2018-04-20"
COMPONENT_API = "2020-02-02"
DATA_PLANE = "https://api.applicationinsights.io"
QUERY_VIA = ("arm", "data-plane")
QUERY_VIA_HELP = ("how the telemetry is read: arm (the default) asks Azure Resource Manager, which needs a component that accepts queries from public networks; "
                  "data-plane asks https://api.applicationinsights.io with a Microsoft Entra token, which is for a component that is private and is run from inside the network")
DATA_PLANE_REFUSALS = {
    401: "the token was not accepted by the Application Insights API",
    403: ("the identity probably has no Reader or Monitoring Reader role on the component or above it (a new role takes minutes to apply), "
          "or the component refuses queries from this network"),
}


class Problem(Exception):
    """Something the owner can fix or must know; printed without a trace."""


def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *args], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer like any other. The request is not repeated at the address it names, because that would carry the bearer token along."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def post_http(url: str, headers: dict, body: bytes) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with OPENER.open(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Azure:
    def __init__(self, runner=run_az, post=post_http, sleep=time.sleep, clock=time.monotonic):
        self.runner, self.post, self.sleep, self.clock = runner, post, sleep, clock
        self.query_via = "arm"
        self.app_ids: dict[str, str] = {}

    def rest(self, method: str, url: str, body: dict | None = None):
        args = ["rest", "--method", method, "--url", url, "--only-show-errors", "--output", "json"]
        if body is not None:
            args += ["--body", json.dumps(body)]
        code, out, err = self.runner(args)
        if code != 0:
            first = (err or "").strip().splitlines()[:1]
            raise Problem(f"{method} {url.split('?')[0].rsplit('/', 1)[-1]} failed: {first[0][:300] if first else 'no message'}")
        return json.loads(out) if out.strip() else None

    def token(self, resource: str) -> str:
        code, out, err = self.runner(["account", "get-access-token", "--resource", resource, "--query", "accessToken", "--output", "tsv", "--only-show-errors"])
        if code != 0 or not out.strip():
            first = (err or "").strip().splitlines()[:1]
            raise Problem(f"no token for {resource}: {first[0][:200] if first else 'no message'}")
        return out.strip()

    def app_id(self, insights: str) -> str:
        """The Application ID of a component, read once through Resource Manager: a read of the control plane, which works while the component is private."""
        key = insights.lower()
        if key not in self.app_ids:
            answer = self.rest("get", f"https://management.azure.com{insights}?api-version={COMPONENT_API}")
            properties = answer.get("properties") if isinstance(answer, dict) else None
            found = properties.get("AppId") if isinstance(properties, dict) else None
            if not isinstance(found, str) or not GUID.fullmatch(found):
                raise Problem("Resource Manager gives the component no Application ID (properties.AppId): is --insights an Application Insights component?")
            self.app_ids[key] = found.lower()
        return self.app_ids[key]


def object_id(token: str) -> str:
    """The `oid` claim of a token. The claims are not secret to the holder, but nothing else of the token is read or kept."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        oid = claims["oid"]
    except (IndexError, ValueError, KeyError, TypeError):
        raise Problem("the token of the signed-in identity has no object id")
    if not isinstance(oid, str) or not GUID.match(oid):
        raise Problem("the token of the signed-in identity has no object id")
    return oid.lower()


def check_site(site: str) -> str:
    if not SITE_ID.match(site):
        raise Problem("--site is the resource id of the function app (a Microsoft.Web/sites resource)")
    return site


def check_insights(insights: str) -> str:
    if not INSIGHTS_ID.match(insights):
        raise Problem("--insights is the resource id of the function app's Application Insights component")
    return insights


def namespace_host(namespace: str) -> str:
    name = namespace.strip().lower().removesuffix(".servicebus.windows.net")
    if not NAMESPACE.match(name):
        raise Problem("--namespace is the name of the Event Hubs namespace")
    return f"{name}.servicebus.windows.net"


def items(answer) -> list[dict]:
    if isinstance(answer, dict):
        answer = answer.get("value", [])
    return [item for item in (answer or []) if isinstance(item, dict)]


def function_names(azure: Azure, site: str) -> list[str]:
    found = items(azure.rest("get", f"https://management.azure.com{site}/functions?api-version={SITE_API}"))
    names = []
    for item in found:
        name = (item.get("properties") or {}).get("name") or str(item.get("name", "")).rsplit("/", 1)[-1]
        if name:
            names.append(name)
    return sorted(names)


def send_control_event(azure: Azure, namespace: str, job: str, request_id: str, hub: str) -> None:
    """One event to a control hub, with the workflow's own token (Event Hubs accepts Microsoft Entra tokens for its REST send)."""
    url = f"https://{namespace_host(namespace)}/{hub}/messages?timeout=60&api-version=2014-01"
    headers = {"Authorization": f"Bearer {azure.token('https://eventhubs.azure.net')}", "Content-Type": "application/atom+xml;type=entry;charset=utf-8"}
    body = json.dumps({"job": job, "requestId": request_id}, separators=(",", ":")).encode("utf-8")
    status, answer = azure.post(url, headers, body)
    if status not in (200, 201):
        text = answer.decode("utf-8", "replace").strip().splitlines()[:1] if isinstance(answer, bytes) else []
        raise Problem(f"sending the control event answered {status}: {text[0][:200] if text else 'no message'}")


def said(answer, token: str, limit: int = 160) -> str:
    """The first line of what a service answered, for a message: one short line, without control characters, and without the token should the service echo it."""
    text = answer.decode("utf-8", "replace") if isinstance(answer, (bytes, bytearray)) else str(answer or "")
    try:
        error = json.loads(text).get("error")
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str):
            text = message
    except (ValueError, AttributeError):
        pass
    if token:
        text = text.replace(token, "[token hidden]")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = re.sub(r"[\x00-\x1f\x7f]+", " ", lines[0]) if lines else ""
    return first if len(first) <= limit else first[: limit - 3] + "..."


def checked_answer(answer) -> dict:
    """The answer of the data plane as a document, or a Problem when it is not a query result. A result has the shape of the one that Resource Manager gives: tables, each with rows."""
    try:
        document = json.loads(answer.decode("utf-8") if isinstance(answer, (bytes, bytearray)) else answer)
    except (ValueError, TypeError):
        raise Problem("the data-plane answer is not JSON")
    tables = document.get("tables") if isinstance(document, dict) else None
    first = tables[0] if isinstance(tables, list) and tables else {}
    rows = first.get("rows", []) if isinstance(first, dict) else None
    if not isinstance(tables, list) or not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        raise Problem("the data-plane answer is not a query result (a list of tables whose rows are lists)")
    return document


def data_plane_query(azure: Azure, insights: str, kql: str) -> dict:
    """One query through the data plane of Application Insights, with a Microsoft Entra token for that resource. Every failure is a Problem, so the loops that wait for the telemetry wait through it."""
    app_id = azure.app_id(insights)
    token = azure.token(DATA_PLANE)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    body = json.dumps({"query": kql}, separators=(",", ":")).encode("utf-8")
    try:
        status, answer = azure.post(f"{DATA_PLANE}/v1/apps/{app_id}/query", headers, body)
    except (OSError, http.client.HTTPException) as e:
        reason = f"{type(e).__name__}: {e}"
        raise Problem(f"the data-plane query could not be sent: {said(reason, token)}")
    if status != 200:
        cause = DATA_PLANE_REFUSALS.get(status)
        detail = said(answer, token)
        raise Problem(f"the data-plane query answered {status}" + (f" ({cause})" if cause else "") + (f": {detail}" if detail else ""))
    return checked_answer(answer)


def query_telemetry(azure: Azure, insights: str, kql: str) -> list[list]:
    """The rows of the first table of the answer to one query, asked the way azure.query_via says: through Resource Manager (the default) or through the data plane."""
    if azure.query_via == "data-plane":
        answer = data_plane_query(azure, insights, kql)
    else:
        answer = azure.rest("post", f"https://management.azure.com{insights}/query?api-version={QUERY_API}", body={"query": kql})
    tables = (answer or {}).get("tables") or []
    return list(tables[0].get("rows") or []) if tables else []


def add_query_via(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query-via", choices=QUERY_VIA, default="arm", help=QUERY_VIA_HELP)


def choose_query_path(azure: Azure, via: str, insights: str) -> None:
    """Sets how this run reads the telemetry. For the data plane the Application ID is read first, so that a component that cannot be read stops the run before an event is sent."""
    if via not in QUERY_VIA:
        raise Problem(f"--query-via is one of {', '.join(QUERY_VIA)}")
    azure.query_via = via
    if via == "data-plane":
        azure.app_id(insights)
        print("The telemetry is read through the data plane of Application Insights (api.applicationinsights.io).", flush=True)


def problem_lines(azure: Azure, insights: str) -> list[str]:
    """The last warnings, errors and exceptions of the function app, to say why no result arrived."""
    lines = []
    queries = (
        ("traces", "traces | where timestamp > ago(1h) and severityLevel >= 2 | project timestamp, message | top 8 by timestamp desc"),
        ("exceptions", "exceptions | where timestamp > ago(1h) | project timestamp, type, outerMessage | top 8 by timestamp desc"),
    )
    for label, kql in queries:
        try:
            for row in query_telemetry(azure, insights, kql):
                lines.append(f"  {label} {' | '.join(str(c).strip().splitlines()[0][:240] if str(c).strip() else '' for c in row)}")
        except Problem as e:
            lines.append(f"  {label}: could not be read ({e})")
    return lines or ["  nothing: the function app wrote no warning and no exception in the last hour"]


def only_in_actions() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise Problem("this command starts a job that writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)")


def command_whoami(args, azure: Azure) -> int:
    print(object_id(azure.token("https://management.azure.com")))
    return 0
