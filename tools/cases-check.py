#!/usr/bin/env python3
"""Checks the first cases: that the cases app lists its two functions, and that one run of the Watch ends and says what it found (standard library only).

    python tools/cases-check.py whoami
    python tools/cases-check.py functions --site <resource id of the cases app> [--minutes 15]
    python tools/cases-check.py run --namespace <Event Hubs namespace> --insights <resource id of the cases app's Application Insights>
                                    [--minutes 30] [--summary <file>] [--query-via arm|data-plane]

It uses the helpers of tools/check-helpers.py, which it loads from its own folder: the same Azure CLI, which the workflow has signed in, and tokens that are used and never printed.

whoami     Read only. Prints the object id of the identity that the CLI is signed in as, read from the claims of its own token (the workflow's identity may not read the directory).
           The Hub workflow uses it to find the deploy identity's own role assignment on the control hub cases-control, which the action cases retires.
functions  Read only. Waits until the cases app lists its four functions (the app has to be started and has to have read its package) and
           prints their names.
run        Sends one event to the control hub of the cases (cases-control) with the identity that the CLI is signed in as: in the Hub workflow that is the
           Operator's identity, which holds Azure Event Hubs Data Sender on that hub, and the tool runs inside the network, because the namespace takes no
           public traffic. The app runs one Watch now,
           through the same code as its daily timer, and writes the History of that run to its telemetry, one line per step (docs/proposals/02-first-cases.md
           has the lines). This waits for the end of the run and for the lines that the end counts, prints what the run found and what each
           case came to, and fails when the run failed, when a case ended in an error, when the investigation was meant to run and did not, or when no end arrived. Only a GitHub Actions run
           may send the event (AGENTS.md rule 18). Nothing in the estate is changed by the run: it only reads. (The investigation makes its own agents and
           conversations in its own Foundry project: docs/proposals/06-foundry-agents.md.)

--query-via (run) How the History is read from the telemetry: arm (the default, through Azure Resource Manager, which needs a component that accepts queries
           from public networks) or data-plane (through https://api.applicationinsights.io with a Microsoft Entra token, for a component that is private; run it
           from inside the network). The same option and the same rules as in tools/check-helpers.py, which has the details.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path

_spec = importlib.util.spec_from_file_location("check_helpers", Path(__file__).with_name("check-helpers.py"))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

Problem = rc.Problem
Azure = rc.Azure

FUNCTIONS = ("watch-daily", "cases-control", "runner-tick", "console")
CONTROL_HUB = "cases-control"
EVENT_PREFIX = "meternaut_event "
ENDS = ("run.finished", "run.failed")
SECTION_TITLE = "### The Watch, started once, and what it said"


def clean(value, limit: int = 300) -> str:
    """Text from the estate or from a model, for a log line: one line, no control characters, nothing that a runner or Markdown would act on."""
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]+", " ", "" if value is None else str(value))).strip()
    text = text.replace("::", ": :").replace("##[", "# #[").replace("`", "'")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def wait_for_functions(azure: Azure, site: str, minutes: float, interval: float = 20.0) -> list[str]:
    """The function names once both are listed. An app that has just started, or has just been given a package, lists fewer first."""
    deadline = azure.clock() + minutes * 60
    last = "no answer yet"
    while True:
        try:
            names = rc.function_names(azure, site)
            missing = [f for f in FUNCTIONS if f not in names]
            if not missing:
                return names
            last = f"{len(names)} functions are listed; missing: {', '.join(missing)}"
        except Problem as e:
            last = str(e)
        if azure.clock() >= deadline:
            raise Problem(f"the cases app does not list its two functions after {minutes:g} minutes ({last})")
        print(f"The cases app is not ready ({last}); waiting.", flush=True)
        azure.sleep(interval)


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
        if event and event.get("requestId") == request_id:
            found.append(event)
    return found


def count(events: list[dict], kind: str) -> int:
    return sum(1 for e in events if e["type"] == kind)


def missing_lines(events: list[dict]) -> list[str]:
    """What the end of the run counts and the telemetry has not delivered yet (lines arrive a few minutes late, and not in order)."""
    finished = next((e for e in events if e["type"] == "run.finished"), None)
    if not finished:
        return []
    wanted = {"lead.found": finished.get("leads"), "case.result": finished.get("cases")}
    missing = [f"{kind}: {count(events, kind)} of {n}" for kind, n in wanted.items() if isinstance(n, int) and count(events, kind) < n]
    written = finished.get("investigationLines")
    have = sum(1 for e in events if e["type"].startswith("investigation."))
    if isinstance(written, int) and not isinstance(written, bool) and have < written:
        missing.append(f"investigation lines: {have} of {written}")
    return missing


def wait_for_run(azure: Azure, insights: str, request_id: str, minutes: float, interval: float = 30.0) -> list[dict]:
    """The run's lines once its end has arrived and every line that the end counts. After the deadline, whatever has arrived."""
    deadline = azure.clock() + minutes * 60
    events: list[dict] = []
    while True:
        try:
            events = events_for(azure, insights, request_id)
        except Problem as e:
            print(f"The telemetry could not be read yet ({e}); waiting.", flush=True)
        ended = any(e["type"] in ENDS for e in events)
        if ended and not missing_lines(events):
            return events
        if azure.clock() >= deadline:
            if not ended:
                raise Problem(f"no end of the run arrived in the telemetry within {minutes:g} minutes ({len(events)} lines of the run arrived)")
            return events
        azure.sleep(interval)


def money(value) -> str:
    return f"{value:.2f} USD" if isinstance(value, (int, float)) and not isinstance(value, bool) else "unknown"


# What the app says when the investigation did not run for a reason that is no failure: it is switched off, or the app has no Foundry project to ask.
BENIGN_NOT_RUN = ("it is switched off", "no Foundry endpoint is set")
NOT_RUN = "the investigation did not run: "


def investigation_failed(events: list[dict]) -> bool:
    """The investigation was meant to run and did not: it ended badly, or the app says that it did not run for a reason other than being off."""
    if any(e["type"] == "investigation.finished" and e.get("ok") is not True for e in events):
        return True
    for e in events:
        note = e.get("note")
        if e["type"] == "run.note" and isinstance(note, str) and note.startswith(NOT_RUN) and note[len(NOT_RUN):].strip() not in BENIGN_NOT_RUN:
            return True
    return False


def investigation_lines(events: list[dict]) -> list[str]:
    """What the investigation did, in plain words: its budget, how it ended, what it says it examined, and each finding with what the checks of code made of it."""
    started = next((e for e in events if e["type"] == "investigation.started"), None)
    finished = next((e for e in events if e["type"] == "investigation.finished"), None)
    if not started and not finished:
        return []
    lines = ["Investigation (two agents in Foundry, with read-only tools):"]
    if started:
        lines.append(f"  The Investigator ran on {clean(started.get('modelInvestigator'), 40)} and the Skeptic on {clean(started.get('modelSkeptic'), 40)}; "
                     f"the budget was {clean(started.get('maxCalls'), 6)} tool calls and {clean(started.get('maxSeconds'), 6)} seconds.")
    if finished:
        lines.append(f"  It ended {'well' if finished.get('ok') is True else 'badly'} after {clean(finished.get('seconds'), 12)} seconds: "
                     f"{clean(finished.get('toolCalls'), 12)} tool calls and {clean(finished.get('tokens'), 12)} tokens through Foundry; findings kept "
                     f"{clean(finished.get('findingsKept'), 12)}, dropped {clean(finished.get('findingsDropped'), 12)}; cases opened {clean(finished.get('cases'), 12)}, "
                     f"resources held back by a guard {clean(finished.get('guarded'), 12)}.")
        if finished.get("note"):
            lines.append(f"  Why: {clean(finished.get('note'), 300)}")
        examined = finished.get("examined")
        if isinstance(examined, list) and examined:
            lines.append("  What it says it examined: " + "; ".join(clean(x, 160) for x in examined[:10]))
    else:
        lines.append("  The end of the investigation did not arrive.")
    findings = sorted((e for e in events if e["type"] == "investigation.finding"), key=lambda e: e["finding"] if isinstance(e.get("finding"), int) else 0)
    for e in findings:
        outcome = "kept" if e.get("kept") is True else f"dropped: {clean(e.get('reason'), 200) or 'no reason given'}"
        lines.append(f"  Finding {clean(e.get('finding'), 6)}: {clean(e.get('basis'), 60) or 'no basis'}, proposal {clean(e.get('proposal'), 30) or 'none'}, "
                     f"confidence {clean(e.get('confidence'), 10)}; {clean(e.get('claimed'), 6)} resources claimed, {clean(e.get('handles'), 6)} left after the checks of code "
                     f"(unknown handles {clean(e.get('unknown'), 6)}, not proven by a measurement {clean(e.get('unproven'), 6)}, repeated {clean(e.get('repeated'), 6)}, "
                     f"judged lately {clean(e.get('judgedLately'), 6)}, held back by a guard {clean(e.get('guarded'), 6)}, beyond the cap {clean(e.get('capped'), 6)}); "
                     f"their cost of the last 30 days {money(e.get('coveredCostUsd30d'))} (Cost Management cost lines, not an invoice); "
                     f"the Skeptic: {clean(e.get('verdict'), 30) or 'no verdict'}; {outcome}")
        if e.get("summary"):
            lines.append(f"     {clean(e.get('summary'), 600)}")
    return lines


def case_lines(number: int, result: dict, steps: list[dict]) -> list[str]:
    where = ", ".join(x for x in (clean(result.get("resourceType"), 80), clean(result.get("resourceGroup"), 80)) if x)
    lines = [f"  {number}. {clean(result.get('detector'), 60)}: {clean(result.get('resourceName'), 120)} ({where})",
             f"     status {clean(result.get('status'), 30)}, confidence {clean(result.get('confidence'), 20)}; cost of the last 30 days {money(result.get('costUsd30d'))} "
             f"(Cost Management cost lines, not an invoice); monthly saving if removed {money(result.get('monthlySavingUsd'))}"]
    for label, key in (("recommendation", "recommendation"), ("summary", "summary"), ("objections", "objections"), ("guards", "guards")):
        value = result.get(key)
        if isinstance(value, (list, tuple)):
            value = "; ".join(clean(v, 200) for v in value)
        if value:
            lines.append(f"     {label}: {clean(value, 600)}")
    for step in steps:
        tokens = ""
        if isinstance(step.get("promptTokens"), int) or isinstance(step.get("completionTokens"), int):
            tokens = f", {step.get('promptTokens') or 0}+{step.get('completionTokens') or 0} tokens"
        model = f" {clean(step.get('model'), 40)}" if step.get("model") else ""
        note = f" ({clean(step.get('note'), 200)})" if step.get("note") else ""
        lines.append(f"     step {clean(step.get('step'), 30)}{model}: {'ok' if step.get('ok') else 'FAILED'}{tokens}, {clean(step.get('ms'), 12)} ms{note}")
    return lines


def failed(events: list[dict]) -> bool:
    finished = next((e for e in events if e["type"] == "run.finished"), None)
    if count(events, "run.failed") or not finished or finished.get("ok") is not True:
        return True
    return (bool(finished.get("errors")) or any(e.get("status") == "error" for e in events if e["type"] == "case.result") or finished.get("investigation") == "failed"
            or investigation_failed(events))


def subscriptions_line(started: dict) -> str | None:
    """How many subscriptions the Watch read, and where its list came from, from the run.started line. None for a run whose line carries no count (an older app)."""
    number = started.get("subscriptions")
    if isinstance(number, bool) or not isinstance(number, int):
        return None
    where = {"estate": "every subscription that the app's identity can read",
             "setting": "the subscriptions of the app's setting",
             "setting-fallback": "the subscriptions of the app's setting, because the list that its identity can read could not be had"}.get(started.get("scopeFrom"), "")
    first = ", ".join(clean(x, 8) for x in (started.get("scopes") or [])[:5] if isinstance(x, str)) if isinstance(started.get("scopes"), list) else ""
    return (f"  The Watch read {number} subscription{'' if number == 1 else 's'}" + (f" ({where})" if where else "") + (f"; the first: {first}" if first else "") + ".")


def summary_lines(request_id: str, events: list[dict]) -> list[str]:
    started = next((e for e in events if e["type"] == "run.started"), {})
    finished = next((e for e in events if e["type"] == "run.finished"), None)
    broken = [e for e in events if e["type"] == "run.failed"]
    lines = [f"Request {request_id}:"]
    reading = subscriptions_line(started)
    if reading:
        lines.append(reading)
    for e in broken:
        lines.append(f"  The run failed: {clean(e.get('reason'), 400)}")
    if finished:
        lines.append(f"  The run ended {'well' if finished.get('ok') is True else 'badly'} after {clean(finished.get('seconds'), 12)} seconds "
                     f"(started by the {clean(started.get('trigger'), 20) or 'unknown'}).")
        lines.append(f"  Leads {finished.get('leads')}; cases taken {finished.get('cases')}: proposed {finished.get('proposed')}, needs a person {finished.get('needsHuman')}, "
                     f"dropped {finished.get('dropped')}, errors {finished.get('errors')}; tokens of the Detective and the Skeptic {finished.get('tokens')}.")
        words = {"ran": "The investigation ran.", "failed": "The investigation was meant to run and did not, or it ended badly.",
                 "off": "The investigation did not run: it is switched off or the app has no Foundry project."}
        if isinstance(finished.get("investigation"), str):
            lines.append("  " + words.get(finished["investigation"], f"The investigation: {clean(finished['investigation'], 20)}."))
    elif not broken:
        lines.append("  The end of the run did not arrive.")
    late = missing_lines(events)
    if late:
        lines.append(f"  Lines that the end counts and the telemetry has not delivered: {', '.join(late)}.")
    for e in events:
        if e["type"] == "run.note":
            lines.append(f"  Note: {clean(e.get('note'), 400)}")
    leads = [e for e in events if e["type"] == "lead.found"]
    if leads:
        by_detector: dict[str, int] = {}
        for e in leads:
            by_detector[clean(e.get("detector"), 60)] = by_detector.get(clean(e.get("detector"), 60), 0) + 1
        lines.append("  Leads by detector: " + ", ".join(f"{name} {n}" for name, n in sorted(by_detector.items())))
    lines.extend(investigation_lines(events))
    results = [e for e in events if e["type"] == "case.result"]
    if results:
        lines.append("Cases:")
        for number, result in enumerate(results, 1):
            steps = [e for e in events if e["type"] == "case.step" and e.get("caseId") == result.get("caseId")]
            lines.extend(case_lines(number, result, steps))
    return lines


def command_functions(args, azure: Azure) -> int:
    names = wait_for_functions(azure, rc.check_site(args.site), args.minutes)
    print(f"The cases app lists {len(names)} functions:")
    for name in names:
        print(f"  {name}")
    return 0


def command_run(args, azure: Azure) -> int:
    rc.only_in_actions()
    insights = rc.check_insights(args.insights)
    rc.choose_query_path(azure, args.query_via, insights)
    request_id = uuid.uuid4().hex
    rc.send_control_event(azure, args.namespace, "watch", request_id, hub=CONTROL_HUB)
    print(f"Sent the control event for one Watch (request {request_id}); waiting for the History of the run in the telemetry.", flush=True)
    try:
        events = wait_for_run(azure, insights, request_id, args.minutes)
        lines = summary_lines(request_id, events)
        bad = failed(events)
    except Problem as e:
        lines = [f"Request {request_id}: {e}", "The last warnings and errors of the cases app:", *rc.problem_lines(azure, insights)]
        bad = True
    print("\n".join(lines))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(SECTION_TITLE + "\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 1 if bad else 0


def main(argv=None, azure: Azure | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("whoami", help="print the object id of the signed-in identity")
    functions = commands.add_parser("functions", help="wait for the cases app's four functions and list them")
    functions.add_argument("--site", required=True)
    functions.add_argument("--minutes", type=float, default=15)
    run = commands.add_parser("run", help="send one control event and read the History of the run from the telemetry")
    run.add_argument("--namespace", required=True)
    run.add_argument("--insights", required=True)
    run.add_argument("--minutes", type=float, default=30)
    run.add_argument("--summary")
    rc.add_query_via(run)
    args = parser.parse_args(argv)
    azure = azure or Azure()
    try:
        return {"whoami": rc.command_whoami, "functions": command_functions, "run": command_run}[args.command](args, azure)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
