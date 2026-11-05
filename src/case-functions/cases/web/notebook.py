"""The notebook: the full record behind one case.

What came from the estate or from a model is escaped and set in a labelled quote, never as a link or a control. The words of the two models are
marked as written by AI. The page shows only fields of the stored records.
"""
from __future__ import annotations

import json

from ..models import CaseRecord, PlanRecord
from . import words
from .common import action_block, confidence, detector_cell, figure, kind_text, may_answer, read
from .core import Ctx, Response, Safe, esc, fmt, join, link_part, number, usd
from .layout import block, code, link, message_page, page, paragraph, quoted, summary, table

STEP_HEADERS = ["Step", "Model", "Tokens in", "Tokens out", "Milliseconds", "Result", "Note"]


def _fact(value: object) -> Safe:
    if isinstance(value, bool):
        return esc("yes" if value else "no")
    if value is None:
        return esc("not known")
    if isinstance(value, (list, tuple)):
        return join((_fact(item) for item in value), ", ")
    if isinstance(value, dict):
        return code(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)[:500])
    return esc(value)


def _model(case: CaseRecord, role: str) -> str:
    models = case.models if isinstance(case.models, dict) else {}
    return str(models.get(role) or "")


def _steps(case: CaseRecord) -> Safe:
    if not case.steps:
        return paragraph("No step is recorded for this case.")
    rows = []
    for step in case.steps:
        step = step if isinstance(step, dict) else {}
        ok = step.get("ok")
        rows.append([code(step.get("step") or ""), step.get("model") or "none", number(step.get("promptTokens")) or "none", number(step.get("completionTokens")) or "none",
                     number(step.get("ms")) or "none", "ok" if ok is True else "not ok" if ok is False else "not known", step.get("note") or ""])
    return table("steps", "Every step of the case", STEP_HEADERS, rows)


def _models_section(case: CaseRecord) -> Safe:
    """Both models' words, marked as AI text. A case that ended in an error has no model text: its summary is the reason that it ended."""
    if case.status == "error":
        return join([Safe("<h2>Why the case ended</h2>"), quoted("Recorded by Meternaut", case.summary or "No reason is recorded.")])
    first, second = _model(case, "detective"), _model(case, "skeptic")
    verdict = summary([("Recommendation", (case.recommendation or "none").capitalize() if case.recommendation else "none"), ("Confidence (0 to 1)", confidence(case.confidence))])
    first_block = join([
        Safe("<h3>First model: judges whether the resource is waste</h3>"), paragraph(f"Model: {first or 'not recorded'}."), verdict,
        quoted(f"Written by AI (model: {first or 'not recorded'}): summary", case.summary or "No text is recorded."),
    ])
    if not second:
        second_block = join([Safe("<h3>Second model: looks for reasons to keep the resource</h3>"), paragraph("The second model was not asked.")])
    else:
        objections = (join(quoted(f"Written by AI (model: {second}): objection {number_}", text) for number_, text in enumerate(case.objections, 1))
                      if case.objections else paragraph("The second model raised no objection."))
        second_block = join([Safe("<h3>Second model: looks for reasons to keep the resource</h3>"), paragraph(f"Model: {second}."), objections])
    return join([Safe("<h2>What the models wrote</h2>"), paragraph("Written by AI. Treat it as text, not as fact."), first_block, second_block])


def _evidence(case: CaseRecord, plan: PlanRecord | None) -> Safe:
    cost = (paragraph(f"Cost lines of the last 30 days for this resource: {usd(case.cost_usd_30d)}.") if case.cost_usd_30d is not None
            else paragraph("No cost lines of the last 30 days were read for this resource."))
    level = (paragraph(plan.evidence_level) if plan is not None
             else paragraph("No plan was made for this case, so no evidence level is stored. The figures above are what the records hold."))
    return join([Safe("<h2>Evidence level</h2>"), level, cost])


def _afterwards(ctx: Ctx, plan: PlanRecord | None, action) -> Safe:
    if plan is None:
        return Safe("")
    title = (link(ctx.url(f"/ok/{link_part(plan.plan_id)}"), plan.title) if may_answer(ctx.principal, plan) else esc(plan.title))  # type: ignore[arg-type]
    rows = summary([("Plan", title), ("State of the plan", words.PLAN_STATE.get(plan.state, plan.state)), ("Plan code", code(plan.code)), ("Answer by", ctx.when(plan.expires_at))])
    return join([Safe("<h2>What happened afterwards</h2>"), rows, action_block(ctx, action) if action is not None else paragraph("No change has been made for this plan.")])


def notebook(ctx: Ctx, case_id: str) -> Response:
    case = ctx.store.case_get(case_id)
    if case is None:
        return message_page(ctx, 404, "I cannot find this case", "No case has this address. Nothing has changed.", back=("/history", "Back to what Meternaut did"), ai=True,
                            why="You opened an address that holds no case.")
    plan, action = None, None
    if case.plan_id:
        plan, _ = read(lambda: ctx.store.plan_get(case.plan_id), None)
        action, _ = read(lambda: ctx.store.action_get(case.plan_id), None)
    status_word, meaning = words.CASE_STATUS.get(case.status, (case.status, ""))
    seen = "1 run" if case.runs_seen == 1 else f"{case.runs_seen} runs"
    found = summary([
        ("Resource name", case.resource_name),
        ("Resource group", case.resource_group),
        ("Kind", kind_text(case.resource_type)),
        ("Resource id", code(case.resource_id)),
        ("Subscription", code(case.subscription_id)),
        ("Found by", detector_cell(case.detector)),
        ("Status", f"{status_word}. {meaning}".strip()),
        ("Run", link(ctx.url(f"/history?run={link_part(case.run_id)}"), case.run_id)),
        ("First seen", ctx.when(case.first_seen_at)),
        ("Last updated", ctx.when(case.updated_at)),
        ("Seen in", seen),
    ])
    figures = summary([
        ("Cost lines, last 30 days", usd(case.cost_usd_30d) if case.cost_usd_30d is not None else "not available"),
        ("Estimated saving a month", f"{figure(case.saving_usd_month)}. An estimate from cost lines of the last 30 days." if case.saving_usd_month is not None else "no figure"),
    ])
    facts = (table("facts", "The typed facts that the models saw", ["Fact", "Value"], [[code(name), _fact(value)] for name, value in sorted(case.facts.items())], row_header=False)
             if isinstance(case.facts, dict) and case.facts else paragraph("No typed fact is recorded for this case."))
    guards = (join([paragraph("These guards fired. A guard stops a case from becoming a proposal, and no model can lift it."),
                    summary([(guard, words.GUARD.get(guard, "")) for guard in case.guards])]) if case.guards else paragraph("No guard fired."))
    parts: list[object] = [
        fmt("<h1>Notebook: {name}</h1>", name=case.resource_name),
        paragraph("The full record behind one case: what was found, what the models saw and wrote, and every step. Text that came from the estate or from a model is "
                  "shown as quoted text. It is never a link or a control.", "lead"),
        Safe("<h2>What was found</h2>"), found, Safe("<h2>Cost lines and estimated saving</h2>"), figures,
        Safe("<h2>What the models saw</h2>"), paragraph("Typed facts only. A name, a tag or a description from the estate never reaches a model."), facts,
        Safe("<h2>Guards that fired</h2>"), guards,
        _models_section(case),
        Safe("<h2>Steps</h2>"), _steps(case),
        _evidence(case, plan),
        _afterwards(ctx, plan, action),
    ]
    return page(ctx, f"Notebook: {case.resource_name}", join(block(p) for p in parts), ai=True, why="You opened the record of one case that Meternaut looked at.")
