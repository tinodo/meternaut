#!/usr/bin/env python3
"""Checks the usage recording: that the Logic App is up with its workflows, that its copy job runs, and what it wrote (standard library only).

    python tools/recording-check.py whoami
    python tools/recording-check.py workflows --site <resource id of the Logic App> [--expect 5] [--minutes 10]
    python tools/recording-check.py run --site <resource id> --cosmos-account <name> [--workflow llm-usage-ingestion] [--minutes 10] [--summary <file>]

It calls the Azure CLI, which the workflow has signed in. The tokens that the CLI hands out are used and never printed.

whoami     Read only. Prints the object id of the identity that the CLI is signed in as, read from the claims of its own token
           (the workflow's identity may not read the directory). The usage store is given a data role for that id.
workflows  Read only. Waits until the Logic App answers and lists at least --expect workflows, then prints each one's name and
           state. A Logic App whose workflows were not published yet lists none, and this says so.
run        Starts the copy job once by hand (the trigger of --workflow), waits for the run to end, prints how each of its
           actions ended, and then reads the usage store (Cosmos DB) with the workflow's identity: the documents of the usage
           container and the export marker of the job. It fails when the run does not end as Succeeded (any other end, Failed,
           Cancelled, Aborted, Suspended or Skipped, is a failure), and when the store cannot be read. Only a GitHub Actions run
           may start the job (AGENTS.md rule 18). The first run of a job that has never run
           copies nothing (it only writes its marker); the next run copies what the gateway recorded since the marker.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import formatdate

API = "2018-11-01"
MANAGEMENT = "/hostruntime/runtime/webhooks/workflow/api/management/workflows"
SITE_ID = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.Web/sites/[A-Za-z0-9-]{2,60}$", re.I)
WORKFLOW_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
COSMOS_ACCOUNT = re.compile(r"^[a-z0-9][a-z0-9-]{2,43}$")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DATABASE = "ai-usage-db"
USAGE_CONTAINER = "llm-usage-container"
MARKER_CONTAINER = "streaming-export-config"
USAGE_FIELDS = "c.id, c.timestamp, c.productName, c.deploymentName, c.promptTokens, c.responseTokens, c.totalTokens, c._ts"


class Problem(Exception):
    """Something the owner can fix or must know; printed without a trace."""


def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *args], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def post_cosmos(url: str, headers: dict, body: bytes) -> tuple[int, bytes, dict]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


class Azure:
    def __init__(self, runner=run_az, post=post_cosmos, sleep=time.sleep, clock=time.monotonic):
        self.runner, self.post, self.sleep, self.clock = runner, post, sleep, clock

    def rest(self, method: str, url: str):
        code, out, err = self.runner(["rest", "--method", method, "--url", url, "--only-show-errors", "--output", "json"])
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
        raise Problem("--site is the resource id of the Logic App (a Microsoft.Web/sites resource)")
    return site


def items(answer) -> list[dict]:
    if isinstance(answer, dict):
        answer = answer.get("value", [])
    return [item for item in (answer or []) if isinstance(item, dict)]


def list_workflows(azure: Azure, site: str) -> list[dict]:
    return items(azure.rest("get", f"https://management.azure.com{site}{MANAGEMENT}?api-version={API}"))


def wait_for_workflows(azure: Azure, site: str, expect: int, minutes: float, interval: float = 20.0) -> list[dict]:
    """The workflows once at least `expect` of them are listed. A runtime that has just started, or has just been given a new package, answers with an error first."""
    deadline = azure.clock() + minutes * 60
    last = "no answer yet"
    while True:
        try:
            found = list_workflows(azure, site)
            if len(found) >= expect:
                return found
            last = f"{len(found)} of {expect} workflows are listed"
        except Problem as e:
            last = str(e)
        if azure.clock() >= deadline:
            raise Problem(f"the Logic App does not list {expect} workflows after {minutes:g} minutes ({last})")
        print(f"The Logic App is not ready ({last}); waiting.", flush=True)
        azure.sleep(interval)


def describe(workflow: dict) -> str:
    name = workflow.get("name", "?")
    kind = workflow.get("kind", "")
    state = "disabled" if workflow.get("isDisabled") else (workflow.get("health", {}) or {}).get("state", "enabled")
    return f"{name} ({kind or 'workflow'}, {state})"


def started_after(run: dict, moment: datetime) -> bool:
    started = (run.get("properties") or {}).get("startTime", "")
    try:
        return datetime.fromisoformat(started.replace("Z", "+00:00")) >= moment
    except ValueError:
        return False


def wait_for_run(azure: Azure, site: str, workflow: str, moment: datetime, minutes: float, interval: float = 10.0) -> dict:
    deadline = azure.clock() + minutes * 60
    while True:
        runs = items(azure.rest("get", f"https://management.azure.com{site}{MANAGEMENT}/{workflow}/runs?api-version={API}"))
        mine = sorted((r for r in runs if started_after(r, moment)), key=lambda r: (r.get("properties") or {}).get("startTime", ""))
        if mine:
            status = ((mine[-1].get("properties") or {}).get("status") or "").lower()
            if status and status != "running" and status != "waiting":
                return mine[-1]
        if azure.clock() >= deadline:
            raise Problem(f"the run of {workflow} did not end within {minutes:g} minutes")
        azure.sleep(interval)


def action_lines(azure: Azure, site: str, workflow: str, run_name: str) -> list[str]:
    actions = items(azure.rest("get", f"https://management.azure.com{site}{MANAGEMENT}/{workflow}/runs/{run_name}/actions?api-version={API}"))
    lines = []
    for action in sorted(actions, key=lambda a: (a.get("properties") or {}).get("startTime", "")):
        props = action.get("properties") or {}
        error = props.get("error") or {}
        first = str(error.get("message", "")).strip().splitlines()[:1]
        detail = f": {error.get('code', '')} {first[0][:200] if first else ''}".rstrip() if error else ""
        lines.append(f"  {action.get('name', '?')}: {props.get('status', '?')}{detail}")
    return lines


def cosmos_documents(azure: Azure, account: str, database: str, container: str, query: str) -> list[dict]:
    """The documents that a plain query returns. No ORDER BY, TOP or aggregate: the gateway of the service answers only the plain shapes of a cross-partition query without a query plan.

    The token is asked for the account's own address first, which is what the service's own SDKs ask for, and for the service's
    general address when the first one is refused (401): both are documented, and an account answers to the one its tenant knows.
    """
    endpoint = f"https://{account}.documents.azure.com"
    url = f"{endpoint}/dbs/{database}/colls/{container}/docs"
    body = json.dumps({"query": query, "parameters": []}).encode("utf-8")
    audiences = (endpoint, "https://cosmos.azure.com")
    for number, audience in enumerate(audiences, start=1):
        outcome = read_pages(azure, url, azure.token(audience), body)
        if isinstance(outcome, list):
            return outcome
        status, message = outcome
        if status == 401 and number < len(audiences):
            continue
        raise Problem(f"reading {container} answered {status}: {message}")
    raise Problem(f"reading {container} was refused")


def read_pages(azure: Azure, url: str, token: str, body: bytes):
    """The documents of every page, or (status, first line of the service's message) for the first page that is not a 200."""
    documents: list[dict] = []
    continuation = None
    while True:
        headers = {
            "Authorization": urllib.parse.quote(f"type=aad&ver=1.0&sig={token}", safe=""),
            "x-ms-date": formatdate(usegmt=True),
            "x-ms-version": "2018-12-31",
            "Content-Type": "application/query+json",
            "Accept": "application/json",
            "x-ms-documentdb-isquery": "True",
            "x-ms-documentdb-query-enablecrosspartition": "True",
            "x-ms-max-item-count": "200",
        }
        if continuation:
            headers["x-ms-continuation"] = continuation
        status, answer, response_headers = azure.post(url, headers, body)
        if status != 200:
            try:
                message = str(json.loads(answer).get("message", "")).strip().splitlines()[:1]
            except (ValueError, AttributeError):
                message = []
            return status, (message[0][:200] if message else "no message")
        documents += [d for d in json.loads(answer).get("Documents", []) if isinstance(d, dict)]
        continuation = {k.lower(): v for k, v in response_headers.items()}.get("x-ms-continuation")
        if not continuation:
            return documents


def iso(seconds) -> str:
    try:
        return datetime.fromtimestamp(int(seconds), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def usage_lines(documents: list[dict], shown: int = 5) -> list[str]:
    lines = [f"{USAGE_CONTAINER}: {len(documents)} documents"]
    for doc in sorted(documents, key=lambda d: d.get("_ts") or 0, reverse=True)[:shown]:
        lines.append(f"  written {iso(doc.get('_ts'))}  product {doc.get('productName')}  model {doc.get('deploymentName')}  "
                     f"prompt {doc.get('promptTokens')}  response {doc.get('responseTokens')}  total {doc.get('totalTokens')}")
    return lines


def marker_lines(documents: list[dict]) -> list[str]:
    lines = [f"{MARKER_CONTAINER}: {len(documents)} documents"]
    for doc in documents:
        lines.append(f"  {doc.get('id')}: copied up to {doc.get('lastExportDate')}, {doc.get('totalExportedRecords')} records in the last run")
    return lines


def only_in_actions() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise Problem("this command starts a run that writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)")


def command_whoami(args, azure: Azure) -> int:
    print(object_id(azure.token("https://management.azure.com")))
    return 0


def command_workflows(args, azure: Azure) -> int:
    found = wait_for_workflows(azure, check_site(args.site), args.expect, args.minutes)
    print(f"The Logic App lists {len(found)} workflows:")
    for workflow in sorted(found, key=lambda w: w.get("name", "")):
        print(f"  {describe(workflow)}")
    return 0


def command_run(args, azure: Azure) -> int:
    only_in_actions()
    site = check_site(args.site)
    if not WORKFLOW_NAME.match(args.workflow) or not WORKFLOW_NAME.match(args.trigger):
        raise Problem("--workflow and --trigger are names")
    if not COSMOS_ACCOUNT.match(args.cosmos_account):
        raise Problem("--cosmos-account is the name of the Cosmos DB account")
    wait_for_workflows(azure, site, 1, args.minutes)
    moment = datetime.now(timezone.utc).replace(microsecond=0)
    azure.rest("post", f"https://management.azure.com{site}{MANAGEMENT}/{args.workflow}/triggers/{args.trigger}/run?api-version={API}")
    print(f"Started {args.workflow}; waiting for the run to end.", flush=True)
    run = wait_for_run(azure, site, args.workflow, moment, args.minutes)
    status = (run.get("properties") or {}).get("status", "?")
    lines = [f"Run {run.get('name', '?')} of {args.workflow}: {status}", *action_lines(azure, site, args.workflow, run.get("name", ""))]
    failed = status.lower() != "succeeded"
    try:
        lines += usage_lines(cosmos_documents(azure, args.cosmos_account, DATABASE, USAGE_CONTAINER, f"SELECT {USAGE_FIELDS} FROM c"))
        lines += marker_lines(cosmos_documents(azure, args.cosmos_account, DATABASE, MARKER_CONTAINER, "SELECT c.id, c.lastExportDate, c.totalExportedRecords FROM c"))
    except Problem as e:
        lines.append(f"The usage store could not be read: {e}")
        failed = True
    print("\n".join(lines))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write("### The copy job and the usage store\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 1 if failed else 0


def main(argv=None, azure: Azure | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("whoami", help="print the object id of the signed-in identity")
    workflows = commands.add_parser("workflows", help="wait for the Logic App's workflows and list them")
    workflows.add_argument("--site", required=True)
    workflows.add_argument("--expect", type=int, default=5)
    workflows.add_argument("--minutes", type=float, default=10)
    run = commands.add_parser("run", help="start the copy job once and read the usage store")
    run.add_argument("--site", required=True)
    run.add_argument("--cosmos-account", required=True)
    run.add_argument("--workflow", default="llm-usage-ingestion")
    run.add_argument("--trigger", default="Recurrence")
    run.add_argument("--minutes", type=float, default=10)
    run.add_argument("--summary")
    args = parser.parse_args(argv)
    azure = azure or Azure()
    try:
        return {"whoami": command_whoami, "workflows": command_workflows, "run": command_run}[args.command](args, azure)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
