#!/usr/bin/env python3
"""Tests the way from the cases app to Teams, from inside the network, and prints plain words only (standard library only).

    python tools/teams-check.py egress
    python tools/teams-check.py run --storage-account <storage account of the base> --insights <resource id of the cases app's Application Insights>
                                    [--minutes 15] [--summary <file>] [--query-via arm|data-plane]

The Teams bot (docs/proposals/20-teams-cards-through-a-bot.md) sends its cards from the cases app to the Bot Connector at https://smba.trafficmanager.net/teams/, with a token that it gets from
https://login.microsoftonline.com. The cases app takes no public traffic and the landing zone routes what leaves the network, so whether those two hosts can be reached is a fact to find out, and this
tool finds it out from the pipeline instead of from a card that does not arrive. It runs in a short-lived container group of the Operator (operator/run-tool.sh), which is in the same virtual network as
the cases app, and it loads the helpers of tools/check-helpers.py from its own folder.

egress  Probes both hosts with a plain HTTPS request. Any HTTP answer, even 401 or 404, proves the path (the request carries no credential and asks for nothing), and the line says which status came.
        No answer says why in one word: the name did not resolve, the connection was refused, it timed out, or the TLS handshake failed. Nothing is changed anywhere.
run     The probe, and then the test card: puts the control message teams-card-test in the control queue (cases-control) with the identity that the CLI is signed in as, which in the Hub is the
        Operator's, the same way as the message that starts a Watch (only a GitHub Actions run may: AGENTS.md rule 18). The cases app sends one labelled test card to the owner and replaces it with a closing card,
        and writes one History line for each step of that to its telemetry (kinds teams.test.step and teams.test.finished). The tool reads those lines and prints, for each step, whether it went well:
          token exchange   the managed identity's token for api://AzureADTokenExchange, exchanged for a token of the app registration for https://api.botframework.com/.default; when it did not, only the
                           number after AADSTS, which is how a wrong subject, audience or issuer of the federated credential shows (Microsoft accepts a wrong value when it is made)
          create           the 1:1 chat with the owner, with the card in it (the Bot Connector's create-conversation call); 403 says whether the Teams app is not installed for him or is blocked
          send             only when the creation did not carry the card
          update           the card replaced by the closing card
        What is printed is a fixed word or a number that the tool checked: no id, name, address, URL or text of the app is ever printed, because the log of the Hub is public. It fails when a host gave
        no answer, when a step was not ok, or when the History did not arrive within --minutes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

_spec = importlib.util.spec_from_file_location("check_helpers", Path(__file__).with_name("check-helpers.py"))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

Problem = rc.Problem
Azure = rc.Azure

CONTROL_QUEUE = "cases-control"
JOB = "teams-card-test"
EVENT_PREFIX = "meternaut_event "
KIND_STEP = "teams.test.step"
KIND_END = "teams.test.finished"
STEPS = ("token", "create", "send", "update")
SECTION_TITLE = "### The Teams test, and the way out to Teams"
# The two hosts of the design: the sign-in service, which gives the token, and the Bot Connector, which takes the card. The addresses are public and carry no credential.
HOSTS = (("login.microsoftonline.com", "https://login.microsoftonline.com/"), ("smba.trafficmanager.net", "https://smba.trafficmanager.net/teams/"))
# What the cases app may say about a step that was not ok, one plain word, and what the word means here.
REASONS = {
    "not-installed": "the Teams app is not installed for the owner",
    "blocked": "the owner or the organisation blocks the app",
    "unauthorized": "the Bot Connector did not accept the token",
    "throttled": "Teams asked the app to slow down",
    "network": "there was no answer: the way out is blocked, or the name did not resolve",
    "other": "another reason",
}
STEP_TITLES = {
    "token": "Token exchange (the identity's token for the app registration's token for the Bot Connector)",
    "create": "Create the chat with the owner, with the test card in it",
    "send": "Send the test card",
    "update": "Replace the test card with the closing card",
}
PROBE_SECONDS = 15


def status_word(status: int) -> str:
    return f"{status // 100}xx"


def fetch(url: str) -> int:
    """One HTTPS GET with no credential and no redirect followed (a redirect is an answer too): the HTTP status. Raises OSError for no answer."""
    request = urllib.request.Request(url, headers={"User-Agent": "meternaut-teams-check", "Accept": "*/*"}, method="GET")
    try:
        with rc.OPENER.open(request, timeout=PROBE_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code


def no_answer_word(error: BaseException) -> str:
    """Why there was no answer, in one fixed word."""
    reason = error.reason if isinstance(error, urllib.error.URLError) and isinstance(error.reason, BaseException) else error
    if isinstance(reason, socket.gaierror):
        return "the name did not resolve"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "the connection timed out"
    if isinstance(reason, ConnectionRefusedError):
        return "the connection was refused"
    if isinstance(reason, ssl.SSLError):
        return "the TLS handshake failed"
    return "the connection failed"


def egress_lines(fetcher=fetch) -> tuple[list[str], bool]:
    """One line for each host and whether every host answered. The words are fixed; the status is a number that the probe read."""
    lines, every_host_answered = [], True
    for host, url in HOSTS:
        try:
            status = fetcher(url)
        except (OSError, ValueError, urllib.error.URLError) as e:
            lines.append(f"{host}: NO ANSWER over HTTPS ({no_answer_word(e)}). The way out of the network to this host is not open from here.")
            every_host_answered = False
            continue
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            lines.append(f"{host}: answered over HTTPS with {status} ({status_word(status)}). Any HTTP answer, even 401 or 404, proves that the path is open.")
        else:
            lines.append(f"{host}: answered over HTTPS, with a status that is not an HTTP status. The path is open, and the answer is not understood.")
    return lines, every_host_answered


def parse_event(message) -> dict | None:
    """One History line: `meternaut_event ` and a JSON object that has a type. Anything else is not one."""
    if not isinstance(message, str) or not message.startswith(EVENT_PREFIX):
        return None
    try:
        event = json.loads(message[len(EVENT_PREFIX):])
    except ValueError:
        return None
    return event if isinstance(event, dict) and isinstance(event.get("type"), str) else None


def events_for(azure: Azure, insights: str, request_id: str) -> list[dict]:
    kql = (f"traces | where timestamp > ago(3h) | where message startswith '{EVENT_PREFIX.strip()}' and message has '{request_id}' "
           "| project timestamp, message | order by timestamp asc")
    found = []
    for row in rc.query_telemetry(azure, insights, kql):
        event = parse_event(row[1]) if len(row) > 1 else None
        if event and event.get("requestId") == request_id and event["type"] in (KIND_STEP, KIND_END):
            found.append(event)
    return found


def wait_for_test(azure: Azure, insights: str, request_id: str, minutes: float, interval: float = 30.0) -> list[dict]:
    """The lines of the test once its end has arrived. After the deadline, whatever has arrived."""
    deadline = azure.clock() + minutes * 60
    events: list[dict] = []
    while True:
        try:
            events = events_for(azure, insights, request_id)
        except Problem:
            print("The telemetry could not be read yet (what Azure said is not shown in a public log); waiting.", flush=True)
        if any(e["type"] == KIND_END for e in events):
            return events
        if azure.clock() >= deadline:
            return events
        azure.sleep(interval)


def whole_number(value, low: int, high: int) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high else None


def step_line(step: str, event: dict | None) -> tuple[str, bool]:
    """One step of the test as one line, and whether it went well. Only a fixed word and numbers that were checked are used; the app's own text is never printed."""
    title = STEP_TITLES[step]
    if event is None:
        return (f"{title}: not needed, the creation of the chat carried the card." if step == "send" else f"{title}: not tried, or its History line did not arrive."), step == "send"
    status = whole_number(event.get("status"), 100, 599)
    if event.get("ok") is True:
        return f"{title}: ok" + (f" (HTTP {status}, {status_word(status)})" if status else "") + ".", True
    detail = []
    code = whole_number(event.get("aadsts"), 1, 9_999_999)
    if step == "token" and code:
        detail.append(f"AADSTS{code}")
    if status:
        detail.append(f"HTTP {status}, {status_word(status)}")
    reason = event.get("reason") if event.get("reason") in REASONS else "other"
    return f"{title}: NOT ok" + (f" ({', '.join(detail)})" if detail else "") + f"; {REASONS[reason]}.", False


def result_lines(events: list[dict]) -> tuple[list[str], bool]:
    """The test as lines, and whether it passed: every step that the app tried went well, the token exchange and the creation were tried, and the end arrived and says ok."""
    by_step = {e.get("step"): e for e in events if e["type"] == KIND_STEP and e.get("step") in STEPS}
    finished = next((e for e in events if e["type"] == KIND_END), None)
    lines, passed = [], finished is not None and finished.get("ok") is True
    for step in STEPS:
        line, good = step_line(step, by_step.get(step))
        lines.append(f"  {line}")
        passed = passed and good
    if finished is None:
        lines.append("  The end of the test did not arrive in the telemetry. Has the cases app the new code (the action cases), and are its Teams settings set? Its History lines arrive a few minutes late.")
    elif finished.get("ok") is not True:
        lines.append("  The cases app says that the test did not end well.")
    return lines, passed


def command_egress(args, azure: Azure, fetcher=fetch) -> int:
    lines, answered = egress_lines(fetcher)
    print("\n".join(["Egress from the Operator's subnet, the same network as the cases app:", *[f"  {line}" for line in lines]]))
    return 0 if answered else 1


def command_run(args, azure: Azure, fetcher=fetch) -> int:
    rc.only_in_actions()
    insights = rc.check_insights(args.insights)
    rc.choose_query_path(azure, args.query_via, insights)
    lines = ["Egress from the Operator's subnet, the same network as the cases app:"]
    probe, answered = egress_lines(fetcher)
    lines += [f"  {line}" for line in probe]
    print("\n".join(lines), flush=True)
    request_id = uuid.uuid4().hex
    rc.send_control_message(azure, args.storage_account, JOB, request_id, queue=CONTROL_QUEUE)
    print(f"Put the control message {JOB} in the queue (request {request_id}); waiting for the History of the test in the telemetry.", flush=True)
    events = wait_for_test(azure, insights, request_id, args.minutes)
    results, passed = result_lines(events)
    lines.append(f"The test card, as the cases app reports it (request {request_id}):")
    lines += results
    good = answered and passed
    lines.append("The Teams test passed: both hosts answer, and the owner got a test card and then its closing card." if good else
                 "The Teams test did not pass: the lines above say which host or step is the reason.")
    print("\n".join(lines[len(probe) + 1:]))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(SECTION_TITLE + "\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 0 if good else 1


def main(argv=None, azure: Azure | None = None, fetcher=fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("egress", help="probe the two hosts that the cases app talks to, and nothing else")
    run = commands.add_parser("run", help="probe them, put the control message teams-card-test in the queue and read the History of the test from the telemetry")
    run.add_argument("--storage-account", required=True)
    run.add_argument("--insights", required=True)
    run.add_argument("--minutes", type=float, default=15)
    run.add_argument("--summary")
    rc.add_query_via(run)
    args = parser.parse_args(argv)
    azure = azure or Azure()
    try:
        return {"egress": command_egress, "run": command_run}[args.command](args, azure, fetcher)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
