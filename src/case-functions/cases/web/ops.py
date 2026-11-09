"""The pages for the platform team: Operations (the switches, the latest runs, what Meternaut may change), every run and every case, the standing permissions (none exist,
read-only) and the kill switch (four switches).

This is where the tables that the start page and History do not carry now live: the content is the earlier one, moved, not extended.
"""
from __future__ import annotations

import re

from ..models import SWITCH_NAMES, SwitchRecord
from . import words
from .common import CASE_HEADERS, case_rows, count, legend, read, run_result, switch_states
from .core import ID, MAX_REASON, Ctx, Response, Safe, fmt, join, link_part, stamp
from .figures import chip
from .layout import block, button, error_summary, field, form, head, hidden, items, kpi, kpis, link, message_page, notice, page, panel, paragraph, table

PERMISSIONS_WHY = "your role lets you see how Meternaut is allowed to act"
PAUSE_WHY = "your role ops lets you stop work at four levels"
OPS_WHY = "your role ops lets you see how Meternaut is running"
RUN_HEADERS = ["Started", "Trigger", "Result", "Leads", "Cases", "Proposed", "Needs a person", "Dropped", "Errors", "Tokens", "Seconds", "Notes", "Cases of the run"]
LATEST_RUNS = ["Started", "Trigger", "Result", "Cases", "Proposed", "Needs a person", "Errors"]
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
                     fmt("{when} · {cases} case{s}", when=ctx.when(run.started_at), cases=count(run.cases), s="" if run.cases == 1 else "s"))
    return kpis(switches, latest, kpi("Next search", ctx.next_search(), "", "The search runs every day."), label="How Meternaut is running")


def hub(ctx: Ctx) -> Response:
    runs, ok = read(lambda: ctx.store.runs_recent(5), [])
    parts: list[object] = [
        head("Operations", "For the platform team: the switches, the latest runs and what Meternaut may change in Azure."),
        _tiles(ctx, runs, ok),
        Safe("<h2>The four switches</h2>"), _switches_table(ctx), paragraph(link(ctx.url("/ops/pause"), "Pause or resume work")),
        Safe("<h2>Latest runs</h2>"),
    ]
    if not ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now. Nothing has changed."))
    elif not runs:
        parts.append(paragraph("No run is recorded yet."))
    else:
        parts.append(table("latest-runs", "The five latest runs, newest first", LATEST_RUNS,
                           [[ctx.when(r.started_at), r.trigger, run_result(r), count(r.cases), count(r.proposed), count(r.needs_human), count(r.errors)] for r in runs]))
    parts += [paragraph(link(ctx.url("/ops/runs"), "Every run and every case")),
              Safe("<h2>What Meternaut can change in Azure</h2>"),
              paragraph(fmt("On its own, nothing: Meternaut holds no right to change Azure. When a person approves a change, they sign in to Azure and Meternaut makes that one change "
                            "with their own permissions. The code makes only this change: {acts_on}.", acts_on=ctx.services.acts_on)),
              paragraph(link(ctx.url("/ops/permissions"), "The standing permissions"))]
    return page(ctx, "Operations", join(block(p) for p in parts), current="/ops", why=OPS_WHY)


def _runs_table(ctx: Ctx, runs: list, selected: str) -> Safe:
    rows = []
    for run in runs:
        mark = Safe("<strong>Selected.</strong> ") if run.run_id == selected else ""
        rows.append([
            fmt("{mark}{when}", mark=mark, when=ctx.when(run.started_at)), run.trigger, run_result(run), count(run.leads), count(run.cases), count(run.proposed),
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
        head("Runs and cases", "Every run of the search and every case that the runs looked at, newest first. This page shows what was found and what happened to it. It is not a cost report."),
        paragraph("A case is a resource in the subscription that the search found and that may be unused or too big. Meternaut only reads it and does not use it. "
                  "Nothing is changed until a person approves a plan."),
        paragraph("Money is in US dollars. An estimated saving is an estimate from cost lines of the last 30 days."),
        Safe("<h2>Runs</h2>"),
    ]
    if not runs_ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now. Nothing has changed."))
    elif not runs:
        parts.append(paragraph("No run is recorded yet."))
    else:
        parts.append(_runs_table(ctx, runs, selected))
    parts.append(Safe("<h2>Cases</h2>"))
    if raw and not selected:
        parts.append(notice("warning", "That run id is not valid", "A run id has letters, digits, dots, hyphens and underscores only. All cases are shown."))
    if selected:
        parts.append(paragraph(fmt('Cases of the run {run}. <a href="{href}">Show all cases</a>.', run=selected, href=ctx.url("/ops/runs"))))
    else:
        parts.append(paragraph(f"The latest {CASES_SHOWN} cases, most recently updated first."))
    if not cases_ok:
        parts.append(notice("error", "The cases cannot be read", "I cannot read the cases now. Nothing has changed."))
    elif not cases:
        parts.append(paragraph("No case is recorded for this run." if selected else "No case is recorded yet."))
    else:
        parts.append(table("cases", "Cases with their status, recommendation and estimated saving", CASE_HEADERS, case_rows(ctx, cases)))
    parts += [Safe("<h2>What the status words mean</h2>"), legend()]
    return page(ctx, "Runs and cases", join(block(p) for p in parts), current="/ops", ai=True, why=OPS_WHY)


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
