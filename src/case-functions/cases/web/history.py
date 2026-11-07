"""What Meternaut did: every run, and the cases that the runs looked at. It replaces a workbook, so it is complete. It is not a cost report."""
from __future__ import annotations

import re

from .common import CASE_HEADERS, case_rows, count, legend, read, run_result
from .core import ID, Ctx, Response, Safe, fmt, join, link_part
from .layout import block, items, notice, page, paragraph, table

RUN_HEADERS = ["Started", "Trigger", "Result", "Leads", "Cases", "Proposed", "Needs a person", "Dropped", "Errors", "Tokens", "Seconds", "Notes", "Cases of the run"]
RUNS_SHOWN = 20
CASES_SHOWN = 100
CASES_SEARCHED = 1000


def _runs_table(ctx: Ctx, runs: list, selected: str) -> Safe:
    rows = []
    for run in runs:
        mark = Safe('<strong>Selected.</strong> ') if run.run_id == selected else ""
        rows.append([
            fmt("{mark}{when}", mark=mark, when=ctx.when(run.started_at)), run.trigger, run_result(run), count(run.leads), count(run.cases), count(run.proposed),
            count(run.needs_human), count(run.dropped), count(run.errors), count(run.tokens), count(run.seconds),
            items(run.notes) if run.notes else "none",
            fmt('<a href="{href}">Show them<span class="visually-hidden"> for run {run}</span></a>', href=ctx.url(f"/history?run={link_part(run.run_id)}"), run=run.run_id),
        ])
    return table("runs", f"The latest {RUNS_SHOWN} runs, newest first", RUN_HEADERS, rows)


def history(ctx: Ctx) -> Response:
    raw = ctx.request.query.get("run", "")
    selected = raw if raw and re.fullmatch(ID, raw) else ""
    runs, runs_ok = read(lambda: ctx.store.runs_recent(RUNS_SHOWN), [])
    cases, cases_ok = read(lambda: ctx.store.cases_recent(CASES_SEARCHED if selected else CASES_SHOWN), [])
    if selected:
        cases = [case for case in cases if case.run_id == selected]
    parts: list[object] = [
        Safe("<h1>What Meternaut did</h1>"),
        paragraph("Every run of the search and every case that the runs looked at, newest first. This page shows what was found and what happened to it. It is not a cost report.", "lead"),
        paragraph("A case is a resource in the subscription that the search found and that may be unused or too big. Meternaut only reads it and does not use it. Nothing is changed until a person approves a plan."),
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
        parts.append(paragraph(fmt('Cases of the run {run}. <a href="{href}">Show all cases</a>.', run=selected, href=ctx.url("/history"))))
    else:
        parts.append(paragraph(f"The latest {CASES_SHOWN} cases, most recently updated first."))
    if not cases_ok:
        parts.append(notice("error", "The cases cannot be read", "I cannot read the cases now. Nothing has changed."))
    elif not cases:
        parts.append(paragraph("No case is recorded for this run." if selected else "No case is recorded yet."))
    else:
        parts.append(table("cases", "Cases with their status, recommendation and estimated saving", CASE_HEADERS, case_rows(ctx, cases)))
    parts += [Safe("<h2>What the status words mean</h2>"), legend()]
    return page(ctx, "What Meternaut did", join(block(p) for p in parts), current="/history", ai=True,
                why="You opened the record of the runs and the cases of Meternaut.")
