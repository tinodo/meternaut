"""The start page: what needs your OK, what Meternaut did lately, the state of the three switches and what the runner may change."""
from __future__ import annotations

from . import words
from .common import CASE_HEADERS, case_rows, count, is_expired, may_answer, read, run_result, switch_states
from .core import Ctx, Response, Safe, esc, fmt, join, link_part, usd
from .layout import block, link, notice, page, paragraph, table

ABOUT = ("Meternaut finds Azure resources that may cost money for nothing. Two AI models review each finding, and a person approves every change on a page of this "
         "console. After an OK, the runner, a separate part of Meternaut, makes the one approved change, checks the result and records it.")


def switch_text(ctx: Ctx, name: str, record) -> Safe:
    """The state of one switch in words. A switch that cannot be read counts as pulled."""
    if record is None:
        return esc("Cannot be read: treated as pulled.")
    if not record.paused:
        return esc("Running.")
    who = f" by {record.by}" if record.by else ""
    reason = f" Reason: {record.reason}" if record.reason else " No reason is recorded."
    return fmt("Paused{who} on {when}.{reason}", who=who, when=ctx.when(record.at, "a time that is not recorded"), reason=reason)


def switches_table(ctx: Ctx) -> Safe:
    rows = []
    for name, record in switch_states(ctx):
        label, stops, _ = words.SWITCH[name]
        rows.append([label, stops, switch_text(ctx, name, record)])
    return table("switches", "State of each switch", ["Switch", "What it stops", "State"], rows, row_header=True)


def _needs_ok(ctx: Ctx) -> Safe:
    plans, ok = read(lambda: ctx.store.plans_open(), [])
    if not ok:
        return notice("error", "The requests cannot be read", "I cannot read the open requests now. Nothing has changed.")
    mine = sorted((p for p in plans if p.state == "open" and may_answer(ctx.principal, p) and not is_expired(ctx, p)), key=lambda p: (p.expires_at, p.plan_id))  # type: ignore[arg-type]
    if not mine:
        return paragraph("Nothing needs your OK now.")
    rows = [[fmt('{title}<br><span class="muted">{name}</span>', title=p.title, name=p.resource_name),
             usd(p.saving_usd_month) if p.saving_usd_month is not None else "no figure", ctx.when(p.expires_at),
             fmt('<a class="btn primary" href="{href}">Review and give your OK<span class="visually-hidden"> for {title}</span></a>', href=ctx.url(f"/ok/{link_part(p.plan_id)}"),
                 title=p.title)] for p in mine]
    return join([paragraph("Each request is answered on its own page. Opening a page approves nothing."),
                 table("needs-ok", "Requests that wait for your OK", ["Request", "Estimated saving a month", "Answer by", "Open"], rows)])


def home(ctx: Ctx) -> Response:
    runs, runs_ok = read(lambda: ctx.store.runs_recent(5), [])
    cases, cases_ok = read(lambda: ctx.store.cases_recent(10), [])
    run_rows = [[ctx.when(r.started_at), r.trigger, run_result(r), count(r.cases), count(r.proposed), count(r.needs_human), count(r.errors)] for r in runs]
    parts: list[object] = [
        Safe("<h1>Meternaut</h1>"), paragraph(ABOUT, "lead"),
        Safe("<h2>Needs your OK now</h2>"), _needs_ok(ctx),
        Safe("<h2>What the runner may change</h2>"), paragraph(fmt("The runner may only {writer}. It changes nothing else.", writer=ctx.services.writer)),
        Safe("<h2>The three switches</h2>"), switches_table(ctx),
    ]
    if ctx.principal.has("ops"):  # type: ignore[union-attr]
        parts.append(paragraph(link(ctx.url("/ops/pause"), "Open the kill switch")))
    parts.append(Safe("<h2>Latest runs</h2>"))
    if not runs_ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now. Nothing has changed."))
    elif not runs:
        parts.append(paragraph("No run is recorded yet."))
    else:
        parts.append(table("latest-runs", "The five latest runs, newest first", ["Started", "Trigger", "Result", "Cases", "Proposed", "Needs a person", "Errors"], run_rows))
    parts.append(Safe("<h2>Latest cases</h2>"))
    if not cases_ok:
        parts.append(notice("error", "The cases cannot be read", "I cannot read the cases now. Nothing has changed."))
    elif not cases:
        parts.append(paragraph("No case is recorded yet."))
    else:
        parts.append(table("latest-cases", "The ten latest cases, most recently updated first", CASE_HEADERS, case_rows(ctx, cases)))
    parts.append(paragraph(link(ctx.url("/history"), "See every run and every case")))
    return page(ctx, "Home", join(block(p) for p in parts), current="/", ai=True, why="You are signed in and listed as a person who may use this console.")
