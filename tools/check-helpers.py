#!/usr/bin/env python3
"""The helpers of the check tools that run in the Operator (standard library only): tools/cases-check.py loads this file from its own folder.

It calls the Azure CLI, which the workflow has signed in. The tokens that the CLI hands out are used and never printed. What it holds:

  * the object id of the identity that the CLI is signed in as, read from the claims of its own token (the workflow's identity may not read the directory): the Hub workflow
    uses it to read the condition of the deploy identity's right to assign roles, before the action aigateway makes the gateway;
  * one message to a Storage queue, with the identity that the CLI is signed in as: in the Hub workflow that is the Operator's identity, which holds Storage Queue Data Contributor on that one
    queue, and the tool runs inside the network, because the storage account takes no public traffic (its queue private endpoint is the way in). The message is the JSON text of the job and the
    request id, base64-encoded, because the Functions host decodes the text of a queue message from base64 before it hands it to the app. Only a GitHub Actions run may put the message
    there (AGENTS.md rule 18);
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
STORAGE_ACCOUNT = re.compile(r"^[a-z0-9]{3,24}$")
# The name of a queue: 3 to 63 lowercase letters, digits and hyphens, beginning and ending with a letter or a digit, with no two hyphens in a row.
QUEUE_NAME = re.compile(r"^(?=.{3,63}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SITE_API = "2024-04-01"
QUERY_API = "2018-04-20"
COMPONENT_API = "2020-02-02"
DATA_PLANE = "https://api.applicationinsights.io"
# The Queue service: the token's resource is the one that Learn names for Azure Storage, and the service version is the latest one that the versioning page of Azure Storage says is deployed
# everywhere (2026-04-06 on 2026-10-29); Microsoft Entra authorization needs 2017-11-09 or later (REST API, Authorize with Microsoft Entra ID).
STORAGE_RESOURCE = "https://storage.azure.com/"
QUEUE_SERVICE_VERSION = "2026-04-06"
# A control message that nobody has taken in an hour is of no use any more (the app refuses one that is older than 15 minutes), so the queue keeps it for an hour and not for its default of seven days.
MESSAGE_TTL_SECONDS = 3600
QUERY_VIA = ("arm", "data-plane")
QUERY_VIA_HELP = ("how the telemetry is read: arm (the default) asks Azure Resource Manager, which needs a component that accepts queries from public networks; "
                  "data-plane asks https://api.applicationinsights.io with a Microsoft Entra token, which is for a component that is private and is run from inside the network")
DATA_PLANE_REFUSALS = {
    401: "the token was not accepted by the Application Insights API",
    403: ("the identity probably has no Reader or Monitoring Reader role on the component or above it (a new role takes minutes to apply), "
          "or the component refuses queries from this network"),
}
QUEUE_REFUSALS = {
    401: "the token was not accepted by the Queue service",
    403: ("the identity probably has no Storage Queue Data Contributor role on the queue yet (a new role takes up to ten minutes to apply), "
          "or the storage account is not reached through its queue private endpoint from this network"),
    404: "the queue is not there: the action cases makes it",
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


def queue_host(account: str) -> str:
    name = account.strip().lower().removesuffix(".queue.core.windows.net")
    if not STORAGE_ACCOUNT.match(name):
        raise Problem("--storage-account is the name of the storage account: 3 to 24 lowercase letters and digits")
    return f"{name}.queue.core.windows.net"


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


def queue_error(answer, token: str) -> str:
    """What the Queue service says about a refusal, in one short line: its error code and the first line of its message (it answers in XML). The token is never in it."""
    text = answer.decode("utf-8", "replace") if isinstance(answer, (bytes, bytearray)) else str(answer or "")
    code = re.search(r"<Code>([^<]{1,80})</Code>", text)
    message = re.search(r"<Message>([^<]*)</Message>", text)
    if code or message:
        text = ": ".join(part for part in (code.group(1).strip() if code else "", (message.group(1).strip() if message else "")) if part)
    return said(text, token)


def send_control_message(azure: Azure, account: str, job: str, request_id: str, queue: str) -> None:
    """One message to the control queue, with the Operator's own Microsoft Entra token (no key, no shared access signature). Put Message answers 201 and nothing else.

    The text of the message is the JSON of the job and the request id, base64-encoded: the Functions host decodes the text of a queue message from base64 before the app reads it."""
    if not QUEUE_NAME.match(queue):
        raise Problem("the queue name is 3 to 63 lowercase letters, digits and hyphens")
    url = f"https://{queue_host(account)}/{queue}/messages?messagettl={MESSAGE_TTL_SECONDS}&timeout=30"
    token = azure.token(STORAGE_RESOURCE)
    headers = {"Authorization": f"Bearer {token}", "x-ms-version": QUEUE_SERVICE_VERSION, "Content-Type": "application/xml"}
    text = base64.b64encode(json.dumps({"job": job, "requestId": request_id}, separators=(",", ":")).encode("utf-8")).decode("ascii")
    body = f"<QueueMessage><MessageText>{text}</MessageText></QueueMessage>".encode("utf-8")
    try:
        status, answer = azure.post(url, headers, body)
    except (OSError, http.client.HTTPException) as e:
        raise Problem(f"the control message could not be sent: {said(f'{type(e).__name__}: {e}', token)}")
    if status != 201:
        cause = QUEUE_REFUSALS.get(status)
        detail = queue_error(answer, token)
        raise Problem(f"putting the control message in the queue answered {status}" + (f" ({cause})" if cause else "") + (f": {detail}" if detail else ""))


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
