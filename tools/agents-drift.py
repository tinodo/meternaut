#!/usr/bin/env python3
"""The drift check of the agents from inside the network, with the Operator's identity (standard library only).

    python tools/agents-drift.py run --endpoint <project endpoint> [--gateway-host <host of the AI Gateway>] [--lock FILE] [--summary FILE]
    python tools/agents-drift.py --selftest

The cases app runs the same check every day at 05:10 UTC with its own identity (cases/drift.py). This tool reads the Foundry project with ANOTHER identity and judges what it reads by the
same rules (cases/drift_rules.py, loaded from its own folder or from the repository), so that an app that reports nothing, or reports a lie, is noticed by a second reader. It makes GET calls
only: the list of the agents, each agent that the lock names, and the list of the connections. It judges eight of the thirteen controls of the app's check, the ones that are about the project:

  A-AGENTS-LISTED  A-DEF-MODEL  A-DEF-INSTRUCTIONS  A-DEF-TOOLS  A-DEF-OPTIONS  A-CONNECTIONS  A-NO-DIRECT-MODEL  A-TRACING

and prints one line for each, in the report shape of every drift check: `drift.pass|drift.fail|drift.unknown {"control", "layer", "state", "detail", "readAt"}`. The controls that only the app
can see (its code, its files, its settings, its lists of calls, its switches) are not judged here. A text of the project never gets into a line (the rules write plain words and counts), and a
token is never printed. The Operator needs the role Foundry User on the project for these reads: the action foundry gives it, and the control I-operator-role of tools/drift-check.py reads it back (docs/proposals/11-agent-harness-and-evaluation.md).

The exit code is 0 when no control failed, 1 when one failed or the project could not be read at all, 2 when the tool refused to run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

helpers = sys.modules.get("aisec_helpers")
if helpers is None:  # a test has loaded it already; a tool run on its own loads it from its own folder
    _spec = importlib.util.spec_from_file_location("aisec_helpers", Path(__file__).with_name("aisec-helpers.py"))
    helpers = importlib.util.module_from_spec(_spec)
    sys.modules["aisec_helpers"] = helpers
    _spec.loader.exec_module(helpers)
Problem = helpers.Problem

API = "api-version=v1"
PAGE = 100
PAGES = 5
JUDGED = ("A-AGENTS-LISTED", "A-DEF-MODEL", "A-DEF-INSTRUCTIONS", "A-DEF-TOOLS", "A-DEF-OPTIONS", "A-CONNECTIONS", "A-NO-DIRECT-MODEL", "A-TRACING")


def why(status: int, document: object) -> str:
    code = helpers.error_words(document)
    return f"HTTP {status}" + (f" {code}" if code else "") if status else "no answer"


def read_listing(client, name_ok) -> tuple[list[dict], bool, str]:
    """(agents as {"name"}, whether the list goes on, why it could not be read)."""
    found: list[dict] = []
    after = ""
    for _ in range(PAGES):
        status, document = client.request("GET", f"/agents?{API}&limit={PAGE}" + (f"&after={after}" if after else ""))
        if status != 200 or not isinstance(document, dict):
            return found, False, f"the project could not be read ({why(status, document)})"
        page = document.get("data") if isinstance(document.get("data"), list) else document.get("value") if isinstance(document.get("value"), list) else []
        found += [{"name": item.get("name") if isinstance(item, dict) and name_ok(item.get("name")) else None} for item in page]
        last = document.get("last_id")
        if document.get("has_more") is not True or not isinstance(last, str):
            return found, False, ""
        after = last
    return found, True, ""


def read_stored(client, name: str) -> tuple[str, object]:
    status, document = client.request("GET", f"/agents/{name}?{API}")
    if status == 404:
        return "missing", None
    if status != 200 or not isinstance(document, dict):
        return "unreadable", why(status, document)
    versions = document.get("versions")
    latest = versions.get("latest") if isinstance(versions, dict) else None
    return ("ok", latest) if isinstance(latest, dict) else ("unreadable", "the answer shows no latest version")


def read_connections(client) -> tuple[list[dict], bool, str]:
    found: list[dict] = []
    path = f"/connections?{API}"
    for _ in range(PAGES):
        status, document = client.request("GET", path)
        if status != 200 or not isinstance(document, dict):
            return found, False, f"the project could not be read ({why(status, document)})"
        page = document.get("value") if isinstance(document.get("value"), list) else document.get("data") if isinstance(document.get("data"), list) else []
        for item in page:
            item = item if isinstance(item, dict) else {}
            credentials = item.get("credentials") if isinstance(item.get("credentials"), dict) else {}
            found.append({"name": item.get("name") if isinstance(item.get("name"), str) else None, "type": item.get("type") if isinstance(item.get("type"), str) else None,
                          "target": item.get("target") if isinstance(item.get("target"), str) else None,
                          "credentials": credentials.get("type") if isinstance(credentials.get("type"), str) else None})
        link = document.get("nextLink")
        if not isinstance(link, str) or not link.startswith(client.base + "/"):
            return found, False, ""
        path = link[len(client.base):]
    return found, True, ""


def judge(client, lock, rules, gateway_host: str) -> list:
    import re

    name_ok = lambda value: isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", value) is not None  # noqa: E731
    items, more, problem = read_listing(client, name_ok)
    found = [rules.judge_listed(lock, items, more, problem)]
    stored = {name: read_stored(client, name) for name in sorted(lock.agents)}
    found += rules.judge_definitions(lock, stored)
    items, more, problem = read_connections(client)
    found += rules.judge_connections(lock, gateway_host, items, more, problem)
    order = {control: index for index, control in enumerate(JUDGED)}
    return sorted(found, key=lambda item: order.get(item.control, 99))


def report(findings: list, rules, now: dt.datetime, out=None) -> int:
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    prefixes = {"PASS": "drift.pass", "FAIL": "drift.fail", "UNKNOWN": "drift.unknown"}
    for item in findings:
        print(f"{prefixes[item.state]} {json.dumps(item.payload(read_at), separators=(',', ':'))}", file=out or sys.stdout, flush=True)
    counts = {state: sum(1 for item in findings if item.state == state) for state in ("PASS", "FAIL", "UNKNOWN")}
    helpers.say(f"agents-drift: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['UNKNOWN']} could not be told (the controls that only the app can judge are not judged here)", out)
    return 1 if counts["FAIL"] else 0


def run(args, client=None, now: dt.datetime | None = None) -> int:
    lockfile, rules, _ = helpers.load_cases()
    account, project = helpers.check_endpoint(args.endpoint)
    host = (args.gateway_host or "").strip().lower()
    path = Path(args.lock) if args.lock else next((p for p in (helpers.HERE / lockfile.FILE_NAME, helpers.CASES / lockfile.FILE_NAME) if p.is_file()), None)
    if path is None:
        raise Problem(f"{lockfile.FILE_NAME} is neither next to the tool nor in the repository", 2)
    try:
        lock = lockfile.load(path)
    except lockfile.LockError as error:
        raise Problem(f"the lock cannot be used: {error}", 1) from None
    client = client or helpers.Client(args.endpoint, helpers.FOUNDRY_RESOURCE)
    findings = judge(client, lock, rules, host)
    code = report(findings, rules, now or dt.datetime.now(dt.timezone.utc))
    helpers.say(f"agents-drift: {len(client.calls)} calls to the project, all of them reads ({account}/{project} is not printed in full)".replace(f"{account}/{project}", "the project"))
    return code


class FakeProject:
    """A fake of the project for the self-test and for the tests of the tool: what a lock made from `definitions` says, served as the data plane shows it."""

    base = "https://acct.services.ai.azure.com/api/projects/p"

    def __init__(self, definitions: dict, connection: str, host: str, *, status: int = 200, extra_agents: tuple = (), edit=None, connections=None) -> None:
        import copy

        self.calls: list[str] = []
        self.status, self.extra = status, list(extra_agents)
        self.versions = {name: {"name": name, "version": "1", "definition": copy.deepcopy(definition)} for name, definition in definitions.items()}
        if edit:
            edit(self.versions)
        self.connections = connections if connections is not None else [
            {"name": connection, "type": "ApiManagement", "target": f"https://{host}/default/models/openai/v1", "credentials": {"type": "ProjectManagedIdentity"}},
            {"name": "appi", "type": "AppInsights", "target": "x", "credentials": {"type": "ProjectManagedIdentity"}}]

    def request(self, method, path, body=None, **options):
        self.calls.append(method)
        if self.status != 200:
            return self.status, {"error": {"code": "AuthorizationFailed", "message": "SECRET-TEXT-OF-THE-SERVICE"}}
        if path.startswith("/agents?"):
            return 200, {"data": [{"name": name} for name in [*self.versions, *self.extra]], "has_more": False}
        if path.startswith("/agents/"):
            name = path.split("/")[2].split("?")[0]
            return (200, {"name": name, "versions": {"latest": self.versions[name]}}) if name in self.versions else (404, None)
        return 200, {"value": self.connections}


SELFTEST_DEFINITIONS = {"agent-one": {"kind": "prompt", "model": "aigateway/model-one", "instructions": "Find waste."},
                        "agent-two": {"kind": "prompt", "model": "aigateway/model-two", "instructions": "Check the finding."}}
SELFTEST_HOST = "aigw-test.ai.gateway.azure.com"


def selftest() -> int:
    """The tool against a fake project and a lock made for the purpose: the drift that it must find, the read that it must not call a failure, and no call that is not a read."""
    lockfile, rules, _ = helpers.load_cases()
    lock = lockfile.validate(lockfile.build(SELFTEST_DEFINITIONS, {}, "a" * 64, "aigateway"))
    problems: list[str] = []

    def states(**options) -> tuple[dict, FakeProject]:
        fake = FakeProject(SELFTEST_DEFINITIONS, "aigateway", SELFTEST_HOST, **options)
        return {item.control: item.state for item in judge(fake, lock, rules, SELFTEST_HOST)}, fake

    healthy, fake = states()
    if set(healthy.values()) != {"PASS"} or set(healthy) != set(JUDGED):
        problems.append(f"a healthy project did not pass every control: {healthy}")
    if set(fake.calls) != {"GET"}:
        problems.append("a call that is not a read was made")
    edited, _ = states(edit=lambda versions: versions["agent-one"]["definition"].update(instructions="Delete everything."))
    if edited["A-DEF-INSTRUCTIONS"] != "FAIL" or any(state == "FAIL" for control, state in edited.items() if control != "A-DEF-INSTRUCTIONS"):
        problems.append(f"edited instructions were not found as the one failure: {edited}")
    extra, _ = states(extra_agents=("another-agent",))
    if extra["A-AGENTS-LISTED"] != "FAIL":
        problems.append("an agent that the lock does not list was not found")
    refused, _ = states(status=403)
    if set(refused.values()) != {"UNKNOWN"}:
        problems.append("a project that cannot be read was not UNKNOWN everywhere")
    for line in problems:
        helpers.say(f"selftest FAIL: {line}")
    helpers.say("selftest: " + ("ok" if not problems else f"{len(problems)} problems"))
    return 1 if problems else 0


def main(argv=None, client=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    commands = parser.add_subparsers(dest="command")
    command = commands.add_parser("run", help="read the project and judge it")
    command.add_argument("--endpoint", required=True)
    command.add_argument("--gateway-host", default="")
    command.add_argument("--lock")
    command.add_argument("--summary")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.command != "run":
            parser.error("name the command run, or give --selftest")
        return run(args, client)
    except Problem as error:
        helpers.say(f"error: {error}", sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
