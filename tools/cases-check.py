#!/usr/bin/env python3
"""Checks the first cases: that the cases app lists its two functions, and that one run of the Watch ends and says what it found (standard library only).

    python tools/cases-check.py whoami
    python tools/cases-check.py functions --site <resource id of the cases app> [--minutes 15]
    python tools/cases-check.py run --storage-account <storage account of the base> --insights <resource id of the cases app's Application Insights>
                                    [--minutes 30] [--summary <file>] [--query-via arm|data-plane] [--counts-only]
    python tools/cases-check.py study --storage-account <storage account of the base> --insights <resource id of the cases app's Application Insights>
                                      [--minutes 20] [--summary <file>] [--query-via arm|data-plane]

It uses the helpers of tools/check-helpers.py, which it loads from its own folder: the same Azure CLI, which the workflow has signed in, and tokens that are used and never printed.

whoami     Read only. Prints the object id of the identity that the CLI is signed in as, read from the claims of its own token (the workflow's identity may not read the directory).
           The Hub workflow uses it to read the condition of the deploy identity's right to assign roles, before the action aigateway makes the gateway.
functions  Read only. Waits until the cases app lists its five functions (the app has to be started and has to have read its package) and
           prints their names.
run        Puts one message in the control queue of the cases (cases-control, in the storage account of the base) with the identity that the CLI is signed in as: in the Hub workflow that is the
           Operator's identity, which holds Storage Queue Data Contributor on that one queue, and the tool runs inside the network, because the storage account takes no
           public traffic. The app runs one Watch now,
           through the same code as its daily timer, and writes the History of that run to its telemetry, one line per step (docs/proposals/02-first-cases.md
           has the lines). This waits for the end of the run and for the lines that the end counts, prints what the run found and what each
           case came to, and fails when the run failed, when a case ended in an error, when the investigation was meant to run and did not, or when no end arrived. Only a GitHub Actions run
           may put the message in the queue (AGENTS.md rule 18). Nothing in the estate is changed by the run: it only reads. (The investigation makes its own agents and
           conversations in its own Foundry project: docs/proposals/06-foundry-agents.md.)
study      Puts the control message of the job study in the control queue the way `run` does for the Watch, waits for the History lines study.started, study.claim and study.finished of that request,
           and prints what one run of the Study came to (cases/study.py, docs/proposals/15-learning.md): its state, the kinds of resource given to the Scholar and read about, the pages read, the claims
           kept and thrown away, the tokens, the seconds and the notes of the run, with every identifier masked. It always prints for a public log: counts and plain words, never a kind of resource, an address,
           a name or a warning of the app. It fails when the Study did not end well (it is off, held or failed, or it ran and read no page although a kind of resource waited), when the app refused the message
           and when no line of the Study arrived in time, and it says in plain words what to check. It changes nothing in the estate: the Study reads public documentation and the estate's kinds of resource,
           keeps its claims in the app's own store and makes its own agent and conversations in the app's own Foundry project.

--query-via (run) How the History is read from the telemetry: arm (the default, through Azure Resource Manager, which needs a component that accepts queries
           from public networks) or data-plane (through https://api.applicationinsights.io with a Microsoft Entra token, for a component that is private; run it
           from inside the network). The same option and the same rules as in tools/check-helpers.py, which has the details.
--counts-only (run) Prints counts, statuses and numbers, and no text from the estate or from an agent: no name of a resource, no resource group, no subscription, no note, no
           reason and no text of a finding, a case or a warning. The Watch reads every subscription that the app's identity can read, so its History names resources of other teams, and the
           log and the summary of a run of a public repository are public (AGENTS.md rule 37). The History itself stays in the app's telemetry. The Hub passes it for the action cases-run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path

_spec = importlib.util.spec_from_file_location("check_helpers", Path(__file__).with_name("check-helpers.py"))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

Problem = rc.Problem
Azure = rc.Azure

FUNCTIONS = ("watch-daily", "cases-control", "runner-tick", "console", "drift-daily", "study-weekly", "cards-posted")
CONTROL_QUEUE = "cases-control"
EVENT_PREFIX = "meternaut_event "
ENDS = ("run.finished", "run.failed")
SECTION_TITLE = "### The Watch, started once, and what it said"
STUDY_JOB = "study"
STUDY_ENDS = ("study.finished", "run.failed")  # run.failed is how the app refuses a control message
STUDY_TITLE = "### The Study, started once, and what it said"


def clean(value, limit: int = 300) -> str:
    """Text from the estate or from a model, for a log line: one line, no control characters, nothing that a runner or Markdown would act on."""
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]+", " ", "" if value is None else str(value))).strip()
    text = text.replace("::", ": :").replace("##[", "# #[").replace("`", "'")
    return text if len(text) <= limit else text[: limit - 3] + "..."


RESOURCE_ID = re.compile(r"(?i)/(?:subscriptions|resourcegroups|providers|tenants)/[^\s'\",;)]*")
GROUP_NAME = re.compile(r"(?i)\b(resource ?groups?)[ =:/]+[^\s'\",;)]+|\brg-[\w.()-]+")
GUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
ESTATE_HOST = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:azurewebsites\.net|windows\.net|azure\.net|azure\.com|azure-api\.net|azurecr\.io|azconfig\.io|microsoft\.com|microsoftonline\.com|trafficmanager\.net)\b")
PUBLIC_HOSTS = ("learn.microsoft.com", "azure.microsoft.com", "prices.azure.com", "management.azure.com", "login.microsoftonline.com")


def public(value, limit: int = 300) -> str:
    """Text of the app for a public log: clean(), and no identifier of the estate in it: no resource id or path, no resource group, no GUID and no host name of the estate (a few public hosts stay)."""
    text = clean(value, 1_000_000)
    text = RESOURCE_ID.sub("<resource id>", text)
    text = GROUP_NAME.sub(lambda found: f"{found.group(1)} <name>" if found.group(1) else "<group>", text)
    text = GUID_TEXT.sub("<id>", text)
    text = ESTATE_HOST.sub(lambda found: found.group(0) if found.group(0).lower() in PUBLIC_HOSTS else "<host>", text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def wait_for_functions(azure: Azure, site: str, minutes: float, interval: float = 20.0) -> list[str]:
    """The function names once all of them are listed. An app that has just started, or has just been given a package, lists fewer first."""
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
            raise Problem(f"the cases app does not list its functions after {minutes:g} minutes ({last})")
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


def wait_for_run(azure: Azure, insights: str, request_id: str, minutes: float, interval: float = 30.0, counts_only: bool = False, ends: tuple[str, ...] = ENDS,
                 late=missing_lines, strict: bool = True) -> list[dict]:
    """The run's lines once its end (one of `ends`) has arrived and every line that `late` says the end counts. After the deadline, whatever has arrived; with `strict`, a deadline without an end is a Problem."""
    deadline = azure.clock() + minutes * 60
    events: list[dict] = []
    while True:
        try:
            events = events_for(azure, insights, request_id)
        except Problem as e:
            print("The telemetry could not be read yet (what Azure said is not shown in a public log); waiting." if counts_only else f"The telemetry could not be read yet ({e}); waiting.", flush=True)
        ended = any(e["type"] in ends for e in events)
        if ended and not late(events):
            return events
        if azure.clock() >= deadline:
            if strict and not ended:
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


def word(value, limit: int = 20) -> str:
    """A value that is one plain lower-case word (a verdict, a kind of proposal), or nothing: a public log never prints the free text of an agent."""
    text = "" if value is None else str(value)
    return text if re.fullmatch(r"[a-z][a-z-]{0,%d}" % (limit - 1), text) else ""


def investigation_lines(events: list[dict], counts_only: bool = False) -> list[str]:
    """What the investigation did, in plain words: its budget, how it ended, what it says it examined, and each finding with what the checks of code made of it.

    With counts_only (a public log) the numbers and the words of code stay, and no text of an agent does: not what it examined, not why it ended, not the text or the reason of a finding."""
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
            lines.append("  Why: not shown in a public log; it is in the History, in the app's telemetry." if counts_only else f"  Why: {clean(finished.get('note'), 300)}")
        examined = finished.get("examined")
        if isinstance(examined, list) and examined and not counts_only:
            lines.append("  What it says it examined: " + "; ".join(clean(x, 160) for x in examined[:10]))
    else:
        lines.append("  The end of the investigation did not arrive.")
    lines.extend(beat_lines(events))
    lines.extend(call_lines(events))
    findings = sorted((e for e in events if e["type"] == "investigation.finding"), key=lambda e: e["finding"] if isinstance(e.get("finding"), int) else 0)
    lines.extend(claim_lines(findings))
    for e in findings:
        if counts_only:
            outcome = "kept" if e.get("kept") is True else "dropped"
            basis, proposal, verdict = "", word(e.get("proposal"), 30) or "none", word(e.get("verdict"), 30) or "no verdict"
        else:
            outcome = "kept" if e.get("kept") is True else f"dropped: {clean(e.get('reason'), 200) or 'no reason given'}"
            basis, proposal, verdict = clean(e.get("basis"), 60) or "no basis", clean(e.get("proposal"), 30) or "none", clean(e.get("verdict"), 30) or "no verdict"
        lines.append(f"  Finding {clean(e.get('finding'), 6)}: {basis + ', ' if basis else ''}proposal {proposal}, "
                     f"confidence {clean(e.get('confidence'), 10)}; {clean(e.get('claimed'), 6)} resources claimed, {clean(e.get('handles'), 6)} left after the checks of code "
                     f"(unknown handles {clean(e.get('unknown'), 6)}, not proven by a measurement on enough days {clean(e.get('unproven'), 6)}, repeated {clean(e.get('repeated'), 6)}, "
                     f"judged lately {clean(e.get('judgedLately'), 6)}, held back by a guard {clean(e.get('guarded'), 6)}, beyond the cap {clean(e.get('capped'), 6)}); "
                     f"their cost of the last 30 days {money(e.get('coveredCostUsd30d'))} (Cost Management cost lines, not an invoice); "
                     f"the Skeptic: {verdict}; {outcome}")
        if e.get("summary") and not counts_only:
            lines.append(f"     {clean(e.get('summary'), 600)}")
    return lines


TOOL_NAME = re.compile(r"[a-z][a-z_]{0,31}")
TOOLS_SHOWN = 12  # the tools that the line "by tool" names; the others are counted


def seconds_of(value) -> float:
    """The seconds of a tool call from a line of the History: a number that is not negative and not absurd, else 0. Never text."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 100_000 else 0.0


def claim_lines(findings: list[dict]) -> list[str]:
    """Why the claims of the findings were not confirmed, from the counts on the lines `investigation.finding`, added up (no text of the estate: a count for each reason of the code), and how many
    resources were too small to open a case. Nothing when no finding carries the counts."""
    reasons = (("noEntry", "listed with no measurement cited"), ("notMeasured", "cited for a resource that no tool measured"), ("metricUnknown", "cited for a metric that no tool returned for the resource"),
               ("totalDiffers", "cited with a total that none of the tools' totals equals"), ("showsUse", "cited with a total that shows use, against a claim of no usage"),
               ("tooBrief", "cited with a measurement of too few days to prove no usage"), ("tooSmall", "too small to open a case"))
    shown = [f"{sum(whole(e.get(key)) or 0 for e in findings)} {what}" for key, what in reasons if any(key in e for e in findings)]
    return [f"  Claims of the findings, over all of them: " + "; ".join(shown) + "."] if shown else []


def beat_lines(events: list[dict]) -> list[str]:
    """One line for each beat of the investigation (docs/proposals/25-beats.md), from the lines `investigation.beat`: counts and one word of code, and no kind of resource, which the line has not."""
    beats = sorted((e for e in events if e["type"] == "investigation.beat"), key=lambda e: whole(e.get("beat")) or 0)
    return [f"  Beat {figure(e.get('beat'))} of {figure(e.get('of'))}: {figure(e.get('kinds'))} kinds{' and the lines of the bill that no resource owns' if e.get('billing') is True else ''}; "
            f"{figure(e.get('seeded'))} resources read by code first, {figure(e.get('looked'))} kinds looked at; {figure(e.get('toolCalls'))} tool calls, {figure(e.get('tokens'))} tokens, "
            f"{figure(e.get('seconds'))} seconds; it ended {word(e.get('end'), 12) or 'unknown'}{' and gave its answer when it was asked once more' if e.get('salvaged') is True else ''}; findings {figure(e.get('findings'))}." for e in beats]


def call_lines(events: list[dict]) -> list[str]:
    """What the tool calls of the investigation took, from the lines `investigation.call`: how many ran and how long, how many of them gave no answer and why (a word of the toolbox), how many more
    were asked for after a budget was used up, the reads that code made against the calls of the Investigator, and the calls and seconds of each tool. Counts, seconds and the names of the tools
    (a name that is not a plain lower-case word is `other`); never the resource type, which the lines carry, and nothing else of the estate."""
    calls = [e for e in events if e["type"] == "investigation.call"]
    if not calls:
        return []
    ran = [e for e in calls if e.get("error") != "budget-used-up"]
    why = Counter(word(e.get("error"), 24) or "other" for e in ran if e.get("ok") is not True)
    tools: dict[str, list[float]] = {}
    for e in ran:
        name = e["tool"] if isinstance(e.get("tool"), str) and TOOL_NAME.fullmatch(e["tool"]) else "other"
        found = tools.setdefault(name, [0, 0.0])
        found[0] += 1
        found[1] += seconds_of(e.get("seconds"))
    sides = {who: [seconds_of(e.get("seconds")) for e in ran if e.get("by") == who] for who in ("code", "agent")}
    lines = [f"  Tool calls in the History: {len(ran)} ran in {sum(seconds_of(e.get('seconds')) for e in ran):.1f} seconds in all, {sum(why.values())} gave no answer, "
             f"{len(calls) - len(ran)} more were asked for after a budget was used up (the first few are counted).",
             f"  The reads that code made for the beats: {len(sides['code'])} calls, {sum(sides['code']):.1f} seconds; the calls of the Investigator: {len(sides['agent'])} calls, {sum(sides['agent']):.1f} seconds."]
    shown = sorted(tools.items(), key=lambda item: (-item[1][1], item[0]))
    lines.append("  By tool, the calls and the seconds: " + "; ".join(f"{name} {int(n)}, {seconds:.1f}" for name, (n, seconds) in shown[:TOOLS_SHOWN])
                 + (f"; {len(shown) - TOOLS_SHOWN} more tools" if len(shown) > TOOLS_SHOWN else "") + ".")
    if why:
        lines.append("  Why calls gave no answer, by the word of the toolbox: " + ", ".join(f"{name} {n}" for name, n in sorted(why.items())) + ".")
    kept = [seconds_of(e.get("savedSeconds")) for e in ran if seconds_of(e.get("savedSeconds")) > 0]
    if kept:
        lines.append(f"  Pictures that were kept and answered again with no read: {len(kept)} calls, {sum(kept):.1f} seconds that their reads took and that were not spent again.")
    return lines


def case_lines(number: int, result: dict, steps: list[dict], counts_only: bool = False) -> list[str]:
    """One case: with counts_only no name of the resource, no resource group and no text of the Detective or the Skeptic, which come from the estate."""
    where = ", ".join(x for x in (clean(result.get("resourceType"), 80), clean(result.get("resourceGroup"), 80)) if x)
    if counts_only:
        lines = [f"  {number}. {clean(result.get('detector'), 60)}: {clean(result.get('resourceType'), 80) or 'a resource'}",
                 f"     status {clean(result.get('status'), 30)}, confidence {clean(result.get('confidence'), 20)}; cost of the last 30 days {money(result.get('costUsd30d'))} "
                 f"(Cost Management cost lines, not an invoice); monthly saving if removed {money(result.get('monthlySavingUsd'))}"]
    else:
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
        note = f" ({clean(step.get('note'), 200)})" if step.get("note") and not counts_only else ""
        lines.append(f"     step {clean(step.get('step'), 30)}{model}: {'ok' if step.get('ok') else 'FAILED'}{tokens}, {clean(step.get('ms'), 12)} ms{note}")
    return lines


def failed(events: list[dict]) -> bool:
    finished = next((e for e in events if e["type"] == "run.finished"), None)
    if count(events, "run.failed") or not finished or finished.get("ok") is not True:
        return True
    return (bool(finished.get("errors")) or any(e.get("status") == "error" for e in events if e["type"] == "case.result") or finished.get("investigation") == "failed"
            or investigation_failed(events))


def subscriptions_line(started: dict, counts_only: bool = False) -> str | None:
    """How many subscriptions the Watch read, and where its list came from, from the run.started line. None for a run whose line carries no count (an older app).

    With counts_only the first subscriptions are not named: the start of a subscription id is an identifier of the estate."""
    number = started.get("subscriptions")
    if isinstance(number, bool) or not isinstance(number, int):
        return None
    where = {"estate": "every subscription that the app's identity can read",
             "setting": "the subscriptions of the app's setting",
             "setting-fallback": "the subscriptions of the app's setting, because the list that its identity can read could not be had"}.get(started.get("scopeFrom"), "")
    first = ", ".join(clean(x, 8) for x in (started.get("scopes") or [])[:5] if isinstance(x, str)) if isinstance(started.get("scopes"), list) and not counts_only else ""
    return (f"  The Watch read {number} subscription{'' if number == 1 else 's'}" + (f" ({where})" if where else "") + (f"; the first: {first}" if first else "") + ".")


def summary_lines(request_id: str, events: list[dict], counts_only: bool = False) -> list[str]:
    started = next((e for e in events if e["type"] == "run.started"), {})
    finished = next((e for e in events if e["type"] == "run.finished"), None)
    broken = [e for e in events if e["type"] == "run.failed"]
    lines = [f"Request {request_id}:"]
    reading = subscriptions_line(started, counts_only)
    if reading:
        lines.append(reading)
    for e in broken:
        lines.append("  The run failed. Why: not shown in a public log; it is in the History, in the app's telemetry." if counts_only else f"  The run failed: {clean(e.get('reason'), 400)}")
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
    notes = [e for e in events if e["type"] == "run.note"]
    if counts_only and notes:
        lines.append(f"  Notes of the run: {len(notes)}, not shown in a public log; they are in the History, in the app's telemetry.")
    else:
        for e in notes:
            lines.append(f"  Note: {clean(e.get('note'), 400)}")
    leads = [e for e in events if e["type"] == "lead.found"]
    if leads:
        by_detector: dict[str, int] = {}
        for e in leads:
            by_detector[clean(e.get("detector"), 60)] = by_detector.get(clean(e.get("detector"), 60), 0) + 1
        lines.append("  Leads by detector: " + ", ".join(f"{name} {n}" for name, n in sorted(by_detector.items())))
    lines.extend(investigation_lines(events, counts_only))
    results = [e for e in events if e["type"] == "case.result"]
    if results:
        lines.append("Cases:")
        for number, result in enumerate(results, 1):
            steps = [e for e in events if e["type"] == "case.step" and e.get("caseId") == result.get("caseId")]
            lines.extend(case_lines(number, result, steps, counts_only))
    return lines


def whole(value) -> int | None:
    """A count from a line of the History: a whole number, else None. Never text."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def figure(value) -> str:
    return "unknown" if whole(value) is None else str(value)


def study_missing(events: list[dict]) -> list[str]:
    """The claim lines that the end of the Study counts and the telemetry has not delivered yet."""
    finished = next((e for e in events if e["type"] == "study.finished"), None)
    kept, have = whole(finished.get("kept")) if finished else None, count(events, "study.claim")
    return [f"study.claim: {have} of {kept}"] if kept is not None and have < kept else []


# What a person checks for each note of the app that says that the Study did not work: the first line whose words the notes hold. The notes are the app's own fixed words (cases/study.py).
STUDY_ADVICE = (
    ("the Study is switched off", "STUDY is off in the app: set the variable STUDY of the environment hub to on, run the action cases (it gives the app the setting), and run study-run again."),
    ("no Foundry endpoint is set", "The app has no Foundry project: run foundry and then cases. The Study needs the project, as the investigation does."),
    ("no store keeps the claims", "The app has no store for the claims: run cases, which gives it its storage settings."),
    ("the switch all or the switch investigation is pulled", "A switch stops the Study: the switch all or the switch investigation is pulled, by a person or by the safeguards, or it could not be read. Release it, or find out why it was pulled."),
    ("the Scholar could not be made ready", "The Scholar was not made: the Foundry project refused it, or its stored definition is not the one in the lock. Run agents-drift, and check that the app's identity holds Foundry User on the project."),
    ("the Scholar gave no answer that could be read", "The Scholar's last text was not one list of claims: the model answered in another form."),
    ("the Scholar gave no answer", "The Scholar's run did not end well: the note says why (a model call that the AI Gateway refused, a limit, or a time-out). Check the AI Gateway's limits and that the app's identity holds AI Gateway Models User."),
    ("the survey or the re-read of the claims could not be made", "The app could not read the estate or its store of claims: check its read roles (Reader and Cost Management Reader) and its roles on the storage account."),
)
NO_NETWORK = ("No page could be read, and every call of the page reader was unavailable, so the app's network may not let the documentation through. The landing zone's firewall, or its DNS, has to let "
              "the app's subnet reach learn.microsoft.com, azure.microsoft.com and prices.azure.com on port 443. Meternaut opens nothing itself: the platform team decides.")
NO_PAGES = ("No page could be read, although the Scholar asked for some. The notes above say how the calls of the page reader ended; a network that does not let the documentation through is only one cause, "
            "and it shows as every call unavailable.")
NO_CALLS = "The Scholar made no call of the page reader: the model did not use its one tool. Check the model of the Scholar and the AI Gateway."
# The notes of the Study that a public log shows are the words that the app wrote itself, and nothing that follows them in brackets: the text of an error of Azure or of Foundry can name a resource.
STUDY_NOTE_WORDS = (
    "the Study is switched off", "no Foundry endpoint is set", "no store keeps the claims, so there is nothing to study for", "the switch all or the switch investigation is pulled, or cannot be read",
    "no kind of resource waits to be studied", "the survey or the re-read of the claims could not be made", "the Scholar could not be made ready", "the Scholar gave no answer that could be read",
    "the Scholar gave no answer", "the cost of some kinds of resource could not be read, so they are studied after the kinds that have a cost, the most common first",
)
STUDY_NOTE_COUNTS = re.compile(r"claims thrown away: (?:[a-z]+ [0-9]+(?:, )?)+|[0-9]+ of [0-9]+ calls of the page reader were refused or failed(?: \((?:[a-z-]+ [0-9]+(?:, )?)+\))?")
NOT_SHOWN = "a note that is not shown in a public log; it is in the History, in the app's telemetry"
UNAVAILABLE_ONLY = re.compile(r"calls of the page reader were refused or failed \(unavailable [0-9]+\)")


def study_note(text) -> str:
    """A note of the Study as a public log shows it: the fixed words of the app, with the counts that it writes, and nothing else; the rest of a note is in the History."""
    said = clean(text, 1_000)
    if STUDY_NOTE_COUNTS.fullmatch(said):
        return said
    for words in STUDY_NOTE_WORDS:
        if said == words:
            return words
        if said.startswith(words + " ("):
            return words + " (what follows is not shown in a public log)"
    return NOT_SHOWN if said else ""
NOT_ARRIVED = ("that the message was put in the queue (the lines above say so); that the cases app is running and has the code of the Study (run cases: its functions include study-weekly); "
               "that the queue cases-control-poison holds no message; and that its telemetry reaches its Application Insights.")


def study_lines(request_id: str, events: list[dict], minutes: float) -> tuple[list[str], bool]:
    """What one run of the Study came to, in plain words for a public log, and whether the check fails: counts and the words of code, the app's notes with every identifier masked, and what to check."""
    started = next((e for e in events if e["type"] == "study.started"), None)
    finished = next((e for e in events if e["type"] == "study.finished"), None)
    refused = next((e for e in events if e["type"] == "run.failed"), None)
    lines = [f"Request {request_id}:"]
    if started:
        lines.append(f"  The Study started (by the {word(started.get('trigger'), 12) or 'unknown'}); its limits: {figure(started.get('maxTypes'))} kinds of resource, {figure(started.get('maxPages'))} pages, "
                     f"{figure(started.get('maxSeconds'))} seconds, {figure(started.get('maxTokens'))} tokens.")
    if finished is None:
        if refused:
            reason = public(refused.get("reason"), 200)
            lines.append(f"  The app refused the message: {reason}.")
            lines.append("  What to check: " + ("the app is older than the Study: run cases to publish the current code, and run study-run again." if "does not know" in reason
                                                else "the app read the message too late (it waited more than 15 minutes in the queue): run study-run again." if "stale" in reason
                                                else "the reason above says why."))
        elif started:
            lines.append(f"  The Study started and its end did not arrive in the telemetry within {minutes:g} minutes: the run may have been stopped, or the telemetry is late.")
            lines.append("  What to check: the History of the app in its Application Insights, and whether the platform restarted the app (a deploy while the Study ran).")
        else:
            lines.append(f"  No line of the Study arrived in the telemetry within {minutes:g} minutes.")
            lines.append("  What to check: " + NOT_ARRIVED)
        lines.append("  The Study did not pass.")
        return lines, True
    state, ok = word(finished.get("state"), 12) or "unknown", finished.get("ok") is True
    lines.append(f"  The Study ended: {state}, {'well' if ok else 'badly'}, after {figure(finished.get('seconds'))} seconds.")
    lines.append(f"  Kinds of resource given to the Scholar: {figure(finished.get('types'))}; it says it read about: {figure(finished.get('studied'))}.")
    lines.append("  Pages read: " + (figure(finished.get("pages")) if "pages" in finished else "not reported (the app is older than this change)")
                 + f"; tool calls of the page reader: {figure(finished.get('toolCalls'))}.")
    kinds = Counter(word(e.get("claimKind"), 30) or "other" for e in events if e["type"] == "study.claim")
    lines.append(f"  Claims kept: {figure(finished.get('kept'))}" + (f" ({', '.join(f'{name} {n}' for name, n in sorted(kinds.items()))})" if kinds else "")
                 + f"; thrown away: {figure(finished.get('rejected'))}; read again and still on their page: {figure(finished.get('rechecked'))}; read again and stale: {figure(finished.get('stale'))}.")
    lines.append(f"  Tokens through Foundry: {figure(finished.get('tokens'))}.")
    late = study_missing(events)
    if late:
        lines.append(f"  Lines that the end counts and the telemetry has not delivered: {', '.join(late)}.")
    notes: list[str] = []
    for text in [e.get("note") for e in events if e["type"] == "study.note"] + [finished.get("note")]:
        shown = study_note(text)
        if shown and shown not in notes:
            notes.append(shown)
    if notes:
        lines.append("  Notes of the run (the app's own words only; the detail of an error is not shown in a public log):")
        lines.extend(f"    - {text}" for text in notes[:12])
        if len(notes) > 12:
            lines.append(f"    ... and {len(notes) - 12} more, in the History.")
    passed, types, pages = state == "ran" and ok, whole(finished.get("types")), whole(finished.get("pages"))
    checks: list[str] = []
    if not passed:
        said = " | ".join(notes)
        checks.append(next((advice for words, advice in STUDY_ADVICE if words in said), f"The Study did not do its work (state {state}): the notes above say why, and the History in the app's Application Insights has the rest."))
    elif types == 0:
        lines.append("  Nothing waited to be studied: every kind of resource of the estate has a claim that is current or a mark that it was studied.")
    elif pages == 0:
        passed = False
        asked = (whole(finished.get("toolCalls")) or 0) > 0
        checks.append((NO_NETWORK if any(UNAVAILABLE_ONLY.search(note) for note in notes) else NO_PAGES) if asked else NO_CALLS)
    elif whole(finished.get("kept")) == 0:
        lines.append("  No claim was kept: the quotes did not hold, or the pages held nothing worth filing. The notes say how many claims were thrown away, and why.")
    if passed:
        lines.append("  The Study ran and read pages: passed." if pages else "  The Study ran: passed.")
    else:
        lines.append("  The Study did not pass.")
        lines.extend(f"  What to check: {advice}" for advice in checks)
    return lines, not passed


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
    rc.send_control_message(azure, args.storage_account, "watch", request_id, queue=CONTROL_QUEUE)
    print(f"Put the control message for one Watch in the queue (request {request_id}); waiting for the History of the run in the telemetry.", flush=True)
    try:
        events = wait_for_run(azure, insights, request_id, args.minutes, counts_only=args.counts_only)
        lines = summary_lines(request_id, events, args.counts_only)
        bad = failed(events)
    except Problem as e:
        if args.counts_only:
            lines = [f"Request {request_id}: {e}", "The last warnings and errors of the cases app are not shown in a public log: they are in its Application Insights (traces of severity 2 or more, and exceptions)."]
        else:
            lines = [f"Request {request_id}: {e}", "The last warnings and errors of the cases app:", *rc.problem_lines(azure, insights)]
        bad = True
    print("\n".join(lines))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(SECTION_TITLE + "\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 1 if bad else 0


def command_study(args, azure: Azure) -> int:
    rc.only_in_actions()
    insights = rc.check_insights(args.insights)
    rc.choose_query_path(azure, args.query_via, insights)
    request_id = uuid.uuid4().hex
    rc.send_control_message(azure, args.storage_account, STUDY_JOB, request_id, queue=CONTROL_QUEUE)
    print(f"Put the control message for one Study in the queue (request {request_id}); waiting for the History of the run in the telemetry.", flush=True)
    events = wait_for_run(azure, insights, request_id, args.minutes, counts_only=True, ends=STUDY_ENDS, late=study_missing, strict=False)
    lines, bad = study_lines(request_id, events, args.minutes)
    print("\n".join(lines))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(STUDY_TITLE + "\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 1 if bad else 0


def main(argv=None, azure: Azure | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("whoami", help="print the object id of the signed-in identity")
    functions = commands.add_parser("functions", help="wait for the cases app's five functions and list them")
    functions.add_argument("--site", required=True)
    functions.add_argument("--minutes", type=float, default=15)
    run = commands.add_parser("run", help="put one control message in the queue and read the History of the run from the telemetry")
    run.add_argument("--storage-account", required=True)
    run.add_argument("--insights", required=True)
    run.add_argument("--minutes", type=float, default=30)
    run.add_argument("--summary")
    run.add_argument("--counts-only", action="store_true", help="print counts, statuses and numbers, and no text from the estate or from an agent (for the log of a public repository)")
    rc.add_query_via(run)
    study = commands.add_parser("study", help="put the control message of the job study in the queue and read the History of the run from the telemetry; prints counts and plain words only")
    study.add_argument("--storage-account", required=True)
    study.add_argument("--insights", required=True)
    study.add_argument("--minutes", type=float, default=20)
    study.add_argument("--summary")
    rc.add_query_via(study)
    args = parser.parse_args(argv)
    azure = azure or Azure()
    try:
        return {"whoami": rc.command_whoami, "functions": command_functions, "run": command_run, "study": command_study}[args.command](args, azure)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
