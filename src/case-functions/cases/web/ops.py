"""The pages for the platform team: Operations (the switches, the latest runs, what Meternaut may change), every run and every case, the standing permissions (none exist,
read-only) and the kill switch (four switches).

This is where the tables that the start page and History do not carry now live: the content is the earlier one, moved, not extended.
"""
from __future__ import annotations

import datetime as dt
import re

from ..brief import kinds as change_kinds
from ..models import CHECK_GAP_MINUTES, SWITCH_NAMES, CheckRecord, SwitchRecord, TwoPeopleRule
from . import words
from .common import CASE_HEADERS, case_rows, count, legend, read, run_result, switch_states
from .core import ID, MAX_REASON, Ctx, Response, Safe, fmt, join, link_part, parse_time, stamp, utc
from .figures import chip, dollars
from .layout import (TEXT, block, button, checks, error_summary, field, form, head, hidden, items, kpi, kpis, link, message_page, nowrap, notice, page, panel, paragraph, respond, table)

PERMISSIONS_WHY = "your role lets you see how Meternaut is allowed to act"
PAUSE_WHY = "your role ops lets you stop work at four levels"
OPS_WHY = "your role ops lets you see how Meternaut is running"
TWO_PEOPLE_WHY = "your role lets you see when a change needs two people, and the role owner lets you change it"
AMOUNT = re.compile(r"\d{1,7}(?:\.\d{1,2})?")
DRIFT_WHY = "your role ops lets you start the check of the AI agents"
RESULTS = {"PASS": ("Pass", "low", "circle"), "FAIL": ("Fail", "high", "diamond"), "UNKNOWN": ("Cannot be told", "mid", "triangle")}  # what a control found: a word and a shape, never a colour alone
BACK = ("/ops", "Back to Operations")
RUN_HEADERS = ["Started", "Trigger", "Result", "Candidates", "Findings", "Proposed", "Needs a person", "Dropped", "Errors", "Tokens", "Seconds", "Notes", "Findings of the run"]
LATEST_RUNS = ["Started", "Trigger", "Result", "Findings", "Proposed", "Needs a person", "Errors"]
RUNS_SHOWN = 20
CASES_SHOWN = 100
CASES_SEARCHED = 1000


def switch_text(ctx: Ctx, name: str, record) -> Safe:
    """The state of one switch: a chip (Running, Paused, or Cannot be read) and, for a switch that is pulled, who pulled it, when and why. A switch that cannot be read counts as pulled."""
    if record is None:
        return fmt("{chip}: treated as pulled.", chip=chip("Cannot be read", "high", "diamond"))
    if not record.paused:
        return chip("Running", "low", "circle")
    who = f" by {record.by}" if record.by else ""
    reason = f" Reason: {record.reason}" if record.reason else " No reason is recorded."
    return fmt("{chip}{who} on {when}.{reason}", chip=chip("Paused", "high", "diamond"), who=who, when=ctx.when(record.at, "a time that is not recorded"), reason=reason)


def _switches_table(ctx: Ctx) -> Safe:
    rows = []
    for name, record in switch_states(ctx):
        label, stops, _ = words.SWITCH[name]
        rows.append([label, stops, switch_text(ctx, name, record)])
    return table("switches", "State of each switch", ["Switch", "What it stops", "State"], rows, row_header=True)


def _tiles(ctx: Ctx, runs: list, runs_ok: bool) -> Safe:
    """Three tiles: how many switches run, how the latest run ended, and when the search looks next."""
    states = switch_states(ctx)
    pulled = [words.SWITCH[name][0] for name, record in states if record is None or record.paused]
    switches = kpi("Switches", f"{len(states) - len(pulled)} of {len(states)}", "running", "Nothing is paused." if not pulled else f"Pulled: {', '.join(pulled)}.")
    if not runs_ok:
        latest = kpi("Latest run", "—", "", "The runs cannot be read.")
    elif not runs:
        latest = kpi("Latest run", "—", "", "The search has not run yet.")
    else:
        run = runs[0]
        latest = kpi("Latest run", "Failed" if not run.ok else ("OK" if run.finished_at else "Not finished"), "",
                     fmt("{when} · {found} finding{s}", when=ctx.when(run.started_at), found=count(run.cases), s="" if run.cases == 1 else "s"))
    return kpis(switches, latest, kpi("Next search", ctx.next_search(), "", "The search runs every day."), label="How Meternaut is running")


def hub(ctx: Ctx, *, banner: Safe | None = None) -> Response:
    runs, ok = read(lambda: ctx.store.runs_recent(5), [])
    parts: list[object] = [
        head("Operations", "For the platform team: the switches, the latest runs and what Meternaut may change in Azure."),
    ]
    if banner is not None:
        parts.append(banner)
    parts += [
        _tiles(ctx, runs, ok),
        Safe("<h2>The four switches</h2>"), _switches_table(ctx), paragraph(link(ctx.url("/ops/pause"), "Pause or resume work")),
        Safe("<h2>When a change needs two people</h2>"), paragraph(rule_text(read(lambda: ctx.store.rule_get(), TwoPeopleRule())[0])),
        paragraph(link(ctx.url("/ops/two-people"), "See or change when a change needs two people")),
        Safe("<h2>Latest runs</h2>"),
    ]
    if not ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now. Nothing has changed."))
    elif not runs:
        parts.append(paragraph("No run is recorded yet."))
    else:
        parts.append(table("latest-runs", "The five latest runs, newest first", LATEST_RUNS,
                           [[nowrap(ctx.when(r.started_at)), r.trigger, run_result(r), count(r.cases), count(r.proposed), count(r.needs_human), count(r.errors)] for r in runs]))
    parts += [paragraph(link(ctx.url("/ops/runs"), "Every run and every finding")),
              Safe("<h2>The drift check</h2>"), *_drift_section(ctx),
              Safe("<h2>What people answered before</h2>"), *_answers_section(ctx),
              Safe("<h2>What Meternaut can change in Azure</h2>"),
              paragraph(fmt("On its own, nothing: Meternaut holds no right to change Azure. When a person approves a change, they sign in to Azure and Meternaut makes that one change "
                            "with their own permissions. The code makes only this change: {acts_on}.", acts_on=ctx.services.acts_on)),
              paragraph(link(ctx.url("/ops/permissions"), "The standing permissions"))]
    return page(ctx, "Operations", join(block(p) for p in parts), current="/ops", why=OPS_WHY)


def _next_check(latest: CheckRecord | None, now: dt.datetime) -> dt.datetime | None:
    """When the next check may start at the console, or None when one may start now: CHECK_GAP_MINUTES after the latest check began, whoever started it."""
    began = parse_time(latest.started_at) if latest is not None else None
    due = None if began is None else began + dt.timedelta(minutes=CHECK_GAP_MINUTES)
    return due if due is not None and due > utc(now) else None


def _started_by(latest: CheckRecord) -> str:
    return f"by {latest.by}" if latest.trigger == "console" and latest.by else "by the timer" if latest.trigger == "timer" else "at the console"


def _drift_result(ctx: Ctx, latest: CheckRecord) -> list[object]:
    """What the latest check found: when and by whom, how many controls came out each way, whether it paused the investigation, and one row for each control with the ones that need a
    look first. A check that has not reported says so."""
    if not latest.finished_at:
        return [paragraph(fmt("A check began {when} {by} and has not reported. If it does not report, the log of the app says why.", when=ctx.when(latest.started_at), by=_started_by(latest)))]
    rows = [item for item in latest.results if isinstance(item, dict)]
    states = [str(item.get("state", "")) for item in rows]
    parts: list[object] = [paragraph(fmt("Latest check: {when}, started {by}. {passed} pass, {failed} fail and {unknown} cannot be told.", when=ctx.when(latest.started_at), by=_started_by(latest),
                                        passed=states.count("PASS"), failed=states.count("FAIL"), unknown=states.count("UNKNOWN")))]
    if latest.tripped:
        parts.append(notice("warning", "This check paused the investigation", "A control that guards the AI agents failed. A person resumes the investigation on the page of the switches.",
                            paragraph(link(ctx.url("/ops/pause"), "Pause or resume work"))))
    order = {"FAIL": 0, "UNKNOWN": 1, "PASS": 2}
    shown = sorted(rows, key=lambda item: order.get(str(item.get("state", "")), 3))
    parts.append(table("drift", "What each control of the latest check found, the ones that need a look first", ["Control", "Result", "What it found"],
                       [[item.get("control", ""), chip(*RESULTS.get(str(item.get("state", "")), ("Cannot be told", "mid", "triangle"))), item.get("detail", "")] for item in shown],
                       row_header=True))
    return parts


def _drift_section(ctx: Ctx) -> list[object]:
    parts: list[object] = [paragraph("Every day Meternaut checks that its AI agents, their tools and its settings are still what the code says. The check reads and changes nothing in Azure. "
                                     "When a control that guards the agents fails, it pauses the investigation until a person resumes it.")]
    latest, ok = read(lambda: ctx.store.check_latest(), None)
    if not ok:
        return parts + [notice("error", "The check cannot be read", "I cannot read the latest check now. Nothing has changed.")]
    parts += _drift_result(ctx, latest) if latest is not None else [paragraph("No check is recorded yet.")]
    due = _next_check(latest, ctx.now)
    if ctx.services.drift is None:
        parts.append(paragraph("This console cannot start a check."))
    elif due is not None:
        parts.append(paragraph(fmt("The next check can start {when}. At most one check starts in {gap} minutes, whoever asks.", when=ctx.when(stamp(due)), gap=CHECK_GAP_MINUTES)))
    else:
        parts.append(form(ctx.url("/ops/drift"), hidden("nonce", ctx.nonce("drift")), fmt('<div class="acts">{b}</div>', b=button("Check now"))))
    return parts


def _too_soon(ctx: Ctx, latest: CheckRecord | None, due: dt.datetime | None) -> Response:
    when = ctx.when(latest.started_at) if latest is not None else "a moment ago"
    until = ctx.when(stamp(due)) if due is not None else "in a few minutes"
    return message_page(ctx, 429, "A check began a moment ago", paragraph(fmt("A check began {when}. The next one can start {until}.", when=when, until=until)),
                        f"At most one check starts in {CHECK_GAP_MINUTES} minutes, whoever asks. Nothing was started.", back=BACK, why=DRIFT_WHY)


def drift_run(ctx: Ctx) -> Response:
    """Starts the drift check of the app now (cases/drift.py), for a person with the role ops: the form's token is used up, the check is claimed in the store (so that two people who ask at
    the same moment start one), the check runs as the timer's does, and the Operations page shows what it found. At most one check begins in CHECK_GAP_MINUTES, the timer's included."""
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), ctx.principal.oid, "drift"):  # type: ignore[union-attr]
        return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. No check was started.",
                            "Open the page again and use the form there.", back=BACK, why=DRIFT_WHY)
    run = ctx.services.drift
    if run is None:
        return message_page(ctx, 503, "The check cannot be started here", "This console is not set up to run the check. Nothing was started.", back=BACK, why=DRIFT_WHY)
    latest = ctx.store.check_latest()
    due = _next_check(latest, ctx.now)
    if due is not None:
        return _too_soon(ctx, latest, due)
    claim = CheckRecord(started_at=stamp(ctx.now), trigger="console", by=ctx.principal.name)  # type: ignore[union-attr]
    if not ctx.store.check_claim(claim, latest.started_at if latest is not None else ""):
        newer = ctx.store.check_latest()
        return _too_soon(ctx, newer, _next_check(newer, ctx.now))
    run(claim.by, claim.started_at)
    return hub(ctx, banner=notice("success", "The check ran", f"Started by {claim.by}. What it found is below."))


def _answers_section(ctx: Ctx) -> list[object]:
    parts: list[object] = [paragraph("A developer can replay what people answered before against the thresholds that were written first, with the learning check. The file has one row for each "
                                     "closed request: the kind of resource, the kind of request, how sure the first AI was and the answer. It holds no name of a person and no name of a resource.")]
    if ctx.services.lessons is None:
        return parts + [paragraph("This console cannot make the file.")]
    return parts + [form(ctx.url("/ops/answers"), hidden("nonce", ctx.nonce("answers")), fmt('<div class="acts">{b}</div>', b=button("Download the answers")))]


def answers_export(ctx: Ctx) -> Response:
    """The past answers as the rows of the learning check, in JSON lines (cases/learning.py, replay_rows): typed values only, and nothing is changed."""
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), ctx.principal.oid, "answers"):  # type: ignore[union-attr]
        return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. No file was made.",
                            "Open the page again and use the form there.", back=BACK, why=OPS_WHY)
    make = ctx.services.lessons
    if make is None:
        return message_page(ctx, 503, "The file cannot be made here", "This console is not set up to make it. Nothing was changed.", back=BACK, why=OPS_WHY)
    return respond(200, make(), content_type=TEXT, headers={"Content-Disposition": 'attachment; filename="meternaut-answers.jsonl"'})


def _runs_table(ctx: Ctx, runs: list, selected: str) -> Safe:
    rows = []
    for run in runs:
        mark = Safe("<strong>Selected.</strong> ") if run.run_id == selected else ""
        rows.append([
            fmt("{mark}{when}", mark=mark, when=nowrap(ctx.when(run.started_at))), run.trigger, run_result(run), count(run.leads), count(run.cases), count(run.proposed),
            count(run.needs_human), count(run.dropped), count(run.errors), count(run.tokens), count(run.seconds),
            items(run.notes) if run.notes else "none",
            fmt('<a href="{href}">Show them<span class="visually-hidden"> for run {run}</span></a>', href=ctx.url(f"/ops/runs?run={link_part(run.run_id)}"), run=run.run_id),
        ])
    return table("runs", f"The latest {RUNS_SHOWN} runs, newest first", RUN_HEADERS, rows)


def runs_page(ctx: Ctx) -> Response:
    """Every run of the search and every case that the runs looked at, newest first."""
    raw = ctx.request.query.get("run", "")
    selected = raw if raw and re.fullmatch(ID, raw) else ""
    runs, runs_ok = read(lambda: ctx.store.runs_recent(RUNS_SHOWN), [])
    cases, cases_ok = read(lambda: ctx.store.cases_recent(CASES_SEARCHED if selected else CASES_SHOWN), [])
    if selected:
        cases = [case for case in cases if case.run_id == selected]
    parts: list[object] = [
        head("Runs and findings", "Every run of the search and every finding that the runs looked at, newest first. This page shows what was found and what happened to it. It is not a cost report."),
        paragraph("A finding is a resource in the subscription that the search found and that may be unused or too big. Meternaut only reads it and does not use it. "
                  "Nothing is changed until a person approves the request."),
        paragraph("Money is in US dollars, and a year is twelve times the month."),
        Safe("<h2>Runs</h2>"),
    ]
    if not runs_ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now. Nothing has changed."))
    elif not runs:
        parts.append(paragraph("No run is recorded yet."))
    else:
        parts.append(_runs_table(ctx, runs, selected))
    parts.append(Safe("<h2>Findings</h2>"))
    if raw and not selected:
        parts.append(notice("warning", "That run id is not valid", "A run id has letters, digits, dots, hyphens and underscores only. All findings are shown."))
    if selected:
        parts.append(paragraph(fmt('Findings of the run {run}. <a href="{href}">Show all findings</a>.', run=selected, href=ctx.url("/ops/runs"))))
    else:
        parts.append(paragraph(f"The latest {CASES_SHOWN} findings, most recently updated first."))
    if not cases_ok:
        parts.append(notice("error", "The findings cannot be read", "I cannot read the findings now. Nothing has changed."))
    elif not cases:
        parts.append(paragraph("No finding is recorded for this run." if selected else "No finding is recorded yet."))
    else:
        parts.append(table("cases", "Findings with their status, recommendation and estimated saving", CASE_HEADERS, case_rows(ctx, cases)))
    parts += [Safe("<h2>What the status words mean</h2>"), legend()]
    return page(ctx, "Runs and findings", join(block(p) for p in parts), current="/ops", ai=True, why=OPS_WHY)


def permissions(ctx: Ctx) -> Response:
    parts: list[object] = [
        head("Standing permissions", "Meternaut holds no permission to change Azure."),
        notice("info", "", "A change is made only after a person approves that exact change on its own page and signs in to Azure: "
                          "it is made with that person's own permissions, and Azure refuses it if the person may not make it."),
        paragraph("This page only shows what exists. It cannot write, change or end a permission."),
        Safe("<h2>What Meternaut can change in Azure</h2>"),
        paragraph(fmt("On its own, nothing. The code makes only this change, and only for a person who approved it: {acts_on}.", acts_on=ctx.services.acts_on)),
    ]
    return page(ctx, "Standing permissions", join(block(p) for p in parts), current="/ops", why=PERMISSIONS_WHY)


def _switch_form(ctx: Ctx, name: str, record: SwitchRecord | None, errors: dict[str, str], values: dict[str, str]) -> Safe:
    label, stops, button_word = words.SWITCH[name]
    pause = record is None or not record.paused
    # A switch that cannot be read is offered only as a pause: the safe side.
    action = "pause" if pause else "resume"
    reason = field(f"reason-{name}", "reason", "Reason (optional)", values.get("reason", "") if values.get("name") == name else "", hint=f"Up to {MAX_REASON} characters. It is kept with the last change of this switch.",
                   error=errors.get(f"reason-{name}", ""), maxlength=MAX_REASON)
    return panel(f"switch-{name}", label,
                 paragraph(fmt("<strong>State:</strong> {state}", state=switch_text(ctx, name, record))),
                 paragraph(fmt("<strong>What it stops:</strong> {stops}", stops=stops)),
                 form(ctx.url("/ops/pause"), hidden("name", name), hidden("action", action), hidden("nonce", ctx.nonce("pause")), reason,
                      fmt('<div class="acts">{b}</div>', b=button(f"{'Pause' if pause else 'Resume'} {button_word}", kind="danger" if pause else "primary"))))


def pause_page(ctx: Ctx, *, banner: Safe | None = None, errors: dict[str, str] | None = None, values: dict[str, str] | None = None, status: int = 200) -> Response:
    errors, values = errors or {}, values or {}
    parts: list[object] = [
        head("The kill switch", "Pull a switch to stop the work that is written under its name. A change that was already sent to Azure is not recalled. Resume lets the work start again."),
        paragraph("Only the last change of each switch is kept, with the person, the time and the reason. Earlier changes are not kept."),
        paragraph("A switch that cannot be read counts as pulled."),
    ]
    if banner is not None:
        parts.append(banner)
    if errors:
        parts.append(error_summary(list(errors.items())))
    states = dict(switch_states(ctx))
    parts.append(fmt('<div class="grid">{panels}</div>', panels=join(_switch_form(ctx, name, states.get(name), errors, values) for name in SWITCH_NAMES)))
    return page(ctx, "The kill switch", join(block(p) for p in parts), current="/ops", status=status, why=PAUSE_WHY)


def pause_save(ctx: Ctx) -> Response:
    form_data = ctx.request.form
    if not ctx.store.nonce_use(form_data.get("nonce", ""), ctx.principal.oid, "pause"):  # type: ignore[union-attr]
        return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. Nothing was changed.",
                            "Open the page again and use the form there.", back=("/ops/pause", "Back to the kill switch"))
    name, action, reason = form_data.get("name", ""), form_data.get("action", ""), form_data.get("reason", "")
    if name not in SWITCH_NAMES or action not in ("pause", "resume"):
        return message_page(ctx, 400, "Nothing was changed", "The form did not name one of the four switches and one of the two actions.", back=("/ops/pause", "Back to the kill switch"))
    if len(reason) > MAX_REASON:
        return pause_page(ctx, errors={f"reason-{name}": f"The reason has {len(reason)} characters. The most is {MAX_REASON}."}, values=dict(form_data), status=400)
    try:
        ctx.store.switch_put(SwitchRecord(name=name, paused=action == "pause", by=ctx.principal.name, at=stamp(ctx.now), reason=reason))  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 (a switch that could not be written is said plainly, and the runbook is the way)
        return message_page(ctx, 503, "The switch was not written", "The store did not take the change. Nothing was changed.",
                            "If work must stop now, use the commands of the runbook.", back=("/ops/pause", "Back to the kill switch"))
    label = words.SWITCH[name][0]
    banner = notice("success", "Paused" if action == "pause" else "Resumed", f"{label}: {'paused' if action == 'pause' else 'resumed'} by {ctx.principal.name}.")  # type: ignore[union-attr]
    return pause_page(ctx, banner=banner)


# -- when a change needs two people -----------------------------------------------------------------------------------------------------------------

def rule_text(rule: TwoPeopleRule) -> str:
    """The rule in one sentence: off, or what makes a change need two people."""
    if not rule.on:
        return "Off. Every change needs one approver, who signs in to Azure and approves it."
    summaries = change_kinds()
    kinds = [summaries[name] for name in rule.families if name in summaries]
    parts = ([f"it saves at least {dollars(rule.min_usd_month)} a month"] if rule.min_usd_month is not None else []) + ([f"it is one of these: {'; '.join(kinds)}"] if kinds else [])
    return f"On. A change needs two people when {' or '.join(parts)}. One confirms the request, and another approves it and signs in to Azure."


def _approvers(ctx: Ctx) -> int:
    return len(ctx.services.people.with_role("approver"))


def two_people_page(ctx: Ctx, *, banner: Safe | None = None, errors: dict[str, str] | None = None, values: dict[str, str] | None = None, status: int = 200) -> Response:
    """When a change needs two people: the rule as it is, who changed it last, and, for the owner, the form that changes it. It applies to the requests that are made after it is saved."""
    errors = errors or {}
    rule, ok = read(lambda: ctx.store.rule_get(), TwoPeopleRule())
    owner = ctx.principal.has("owner")  # type: ignore[union-attr]
    people = _approvers(ctx)
    parts: list[object] = [head("Changes that need two people", "A change that is larger can need two people: one confirms the request, and another approves it and signs in to Azure. It is off until the owner turns it on.")]
    if banner is not None:
        parts.append(banner)
    if errors:
        parts.append(error_summary(list(errors.items())))
    if not ok:
        parts.append(notice("error", "The rule cannot be read", "I cannot read the rule now, so what is shown is the starting rule: off. Nothing has changed."))
    who = fmt(" It was last changed by {by} on {when}.", by=rule.by, when=ctx.when(rule.at)) if rule.by and rule.at else Safe("")
    parts.append(panel("rule-now", "How it is now", paragraph(fmt("{rule}{who}", rule=rule_text(rule), who=who)),
                       paragraph(f"{people} {'person has' if people == 1 else 'people have'} the role approver. It applies to the requests that are made after it is saved: a request that is open keeps what it was made with.")))
    if not owner:
        parts.append(paragraph("Only the owner changes it."))
    else:
        values = values if values is not None else {"min_usd": f"{rule.min_usd_month:g}" if rule.min_usd_month is not None else "", "families": ",".join(rule.families)}
        chosen = set(filter(None, values.get("families", "").split(",")))
        boxes = [(name, summary, name in chosen) for name, summary in change_kinds().items()]
        fields = [field("min_usd", "min_usd", "A change that saves at least this much a month, in US dollars", values.get("min_usd", ""), hint="Leave it empty for no amount. A change whose saving is not known is not covered by an amount: choose its kind below.",
                        error=errors.get("min_usd", ""), maxlength=10, attrs={"inputmode": "decimal"}),
                  checks("families", "Kinds of change that always need two people", "families", boxes, error=errors.get("families", ""))]
        parts.append(panel("rule-change", "Change the rule", form(ctx.url("/ops/two-people"), hidden("nonce", ctx.nonce("two-people")), *fields,
                                                                   fmt('<div class="acts">{b}</div>', b=button("Save the rule", kind="primary"))),
                           paragraph("Leave the amount empty and choose no kind to turn it off. It needs at least two people with the role approver.")))
    return page(ctx, "Changes that need two people", join(block(p) for p in parts), current="/ops", status=status, why=TWO_PEOPLE_WHY)


def two_people_save(ctx: Ctx) -> Response:
    """The owner saves the rule. The one-time token of the form is used up first; a rule that would need two people when fewer than two can approve is refused, and nothing is stored."""
    form_data = ctx.request.form
    if not ctx.store.nonce_use(form_data.get("nonce", ""), ctx.principal.oid, "two-people"):  # type: ignore[union-attr]
        return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. Nothing was changed.",
                            "Open the page again and use the form there.", back=("/ops/two-people", "Back to the rule"))
    errors: dict[str, str] = {}
    amount = form_data.get("min_usd", "").strip()
    if amount and (not AMOUNT.fullmatch(amount) or float(amount) <= 0):
        errors["min_usd"] = "Enter an amount above zero, with up to two decimals, or leave it empty."
    named = [name for name in form_data.get("families", "").split(",") if name]
    if any(name not in change_kinds() for name in named):
        errors["families"] = "Choose kinds of change from the list."
    families = tuple(name for name in change_kinds() if name in named)
    rule = TwoPeopleRule(min_usd_month=float(amount) if amount and "min_usd" not in errors else None, families=families if "families" not in errors else (),
                         by=ctx.principal.name, at=stamp(ctx.now))  # type: ignore[union-attr]
    if not errors and rule.on and _approvers(ctx) < 2:
        errors["min_usd"] = f"A rule that needs two people needs at least two people with the role approver, and {_approvers(ctx)} is listed. Nothing was saved."
    if errors:
        return two_people_page(ctx, errors=errors, values=dict(form_data), status=400)
    try:
        ctx.store.rule_put(rule)
    except Exception:  # noqa: BLE001 (a rule that could not be written is said plainly)
        return message_page(ctx, 503, "The rule was not saved", "The store did not take the change. Nothing was changed.", back=("/ops/two-people", "Back to the rule"))
    return two_people_page(ctx, banner=notice("success", "Saved", rule_text(rule)))
