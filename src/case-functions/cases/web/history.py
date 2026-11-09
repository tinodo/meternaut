"""History, "What happened": a plain feed of the last 30 days, a line for each thing that happened, newest day first.

Three kinds of line: what people decided (with their reason, for a decline), the changes that were made and checked, and, for each day, how many new findings there were. A
person sees the decisions and the changes of the requests that they are named in, and the number of findings; the run tables and the cases are on the pages of the platform
team (ops.py). The old addresses of "My decisions" and "What I did here" answer with this page.
"""
from __future__ import annotations

import datetime as dt

from ..brief import REASON_WORDS, plan_headline
from ..models import ActionRecord, DecisionRecord, PlanRecord
from .common import effective_state, may_answer, read
from .core import Ctx, Response, Safe, fmt, join, link_part, stamp
from .layout import block, link, notice, page, paragraph

DAYS = 30
PLANS_READ = 40
MAX_DECISION_AGE = 15  # a request is answered within days of its making; an older plan has nothing to say in the last 30 days
COUNTED = ("proposed", "needs_human", "awaiting_ok", "approved", "running", "done", "failed", "declined", "expired", "verified", "acknowledged")


def _headline(ctx: Ctx, plan: PlanRecord) -> Safe:
    return link(ctx.url(f"/ok/{link_part(plan.plan_id)}"), plan_headline(plan))


def _decision_line(ctx: Ctx, plan: PlanRecord, decision: DecisionRecord) -> tuple[str, Safe] | None:
    advice = plan.family == "advise"
    who = decision.approver_name or "A person"
    reason = REASON_WORDS.get(decision.reason, "")
    if decision.decision == "decline":
        said = "said it is not worth acting on" if advice else "declined"
        return decision.at, fmt("{who} {said}: {headline}.{reason}", who=who, said=said, headline=_headline(ctx, plan), reason=f" Reason: {reason}." if reason else "")
    if decision.decision == "not_mine":
        return decision.at, fmt("{who} said that this is not theirs: {headline}.", who=who, headline=_headline(ctx, plan))
    if decision.decision == "approve":
        said = "said it is worth acting on" if advice else "approved"
        return decision.at, fmt("{who} {said}: {headline}.", who=who, said=said, headline=_headline(ctx, plan))
    return None


def _action_lines(ctx: Ctx, plan: PlanRecord, action: ActionRecord) -> list[tuple[str, Safe]]:
    lines: list[tuple[str, Safe]] = []
    if action.finished_at and action.state in ("done", "verified", "unknown"):
        made = "Nothing was changed" if action.no_change else "Change made"  # an approval that found nothing to change wrote nothing
        lines.append((action.finished_at, fmt("{made}: {headline}. {result}", made=made, headline=_headline(ctx, plan), result=action.result)))
    elif action.finished_at and action.state == "failed":
        lines.append((action.finished_at, fmt("Change not made: {headline}. {result}", headline=_headline(ctx, plan), result=action.error or action.result)))
    if action.verified_at:
        note = action.verification.get("note", "") if isinstance(action.verification, dict) else ""
        lines.append((action.verified_at, fmt("Change checked: {headline}. {note}", headline=_headline(ctx, plan), note=note or "Cost lines confirm it.")))
    return lines


def _events(ctx: Ctx, since: str) -> tuple[list[tuple[str, Safe]], bool]:
    """The lines of the feed, each with its time: the decisions and the changes of the requests that the person is named in, then the findings of each day."""
    plans, ok = read(lambda: ctx.store.plans_recent(100), [])
    old = stamp(ctx.now - dt.timedelta(days=DAYS + MAX_DECISION_AGE))
    quiet: dict[str, list[str]] = {}  # the advice that nobody answered, for each day: one line, not one for each, and none of them takes a place of the plans that are read
    mine = []
    for plan in plans:
        if may_answer(ctx.principal, plan) and plan.created_at >= old:  # type: ignore[arg-type]
            if plan.family == "advise" and effective_state(ctx, plan) == "expired":
                quiet.setdefault(ctx.day_key(plan.expires_at), []).append(plan.expires_at)
            else:
                mine.append(plan)
    mine = mine[:PLANS_READ]
    actions = {a.plan_id: a for a in read(lambda: ctx.store.actions_recent(100), [])[0]}
    lines: list[tuple[str, Safe]] = []
    for plan in mine:
        for decision in read(lambda plan=plan: ctx.store.decisions_of_plan(plan.plan_id), [])[0]:
            line = _decision_line(ctx, plan, decision)
            if line is not None:
                lines.append(line)
        if plan.family != "advise" and plan.plan_id in actions:
            lines += _action_lines(ctx, plan, actions[plan.plan_id])
        if effective_state(ctx, plan) == "expired":
            lines.append((plan.expires_at, fmt("Nobody answered in time: {headline}.", headline=_headline(ctx, plan))))
    for found in quiet.values():
        lines.append((max(found), fmt("Closed with no answer: {n} request{s} to look at a finding.", n=len(found), s="" if len(found) == 1 else "s")))
    cases = read(lambda: ctx.store.cases_recent(1000), [])[0]
    per_day: dict[str, list[str]] = {}
    for case in cases:
        if case.status in COUNTED and case.first_seen_at >= since:
            per_day.setdefault(ctx.day_key(case.first_seen_at), []).append(case.first_seen_at)
    for found in per_day.values():
        lines.append((max(found), fmt("{n} new finding{s}.", n=len(found), s="" if len(found) == 1 else "s")))
    return [(at, line) for at, line in lines if at >= since], ok


def history(ctx: Ctx) -> Response:
    since = stamp(ctx.now - dt.timedelta(days=DAYS))
    lines, ok = _events(ctx, since)
    parts: list[object] = [Safe("<h1>What happened</h1>"), paragraph(f"The last {DAYS} days: what was decided, what was changed and checked, and how many new findings there were each day.", "lead")]
    if not ok:
        parts.append(notice("error", "The history cannot be read", "I cannot read the requests now. Nothing has changed."))
    if not lines:
        parts.append(paragraph(f"Nothing has happened in the last {DAYS} days."))
    days: dict[str, list[tuple[str, Safe]]] = {}
    for at, line in sorted(lines, key=lambda item: item[0], reverse=True):
        days.setdefault(ctx.day_key(at), []).append((at, line))
    for key in sorted(days, reverse=True):
        parts += [fmt("<h2>{day}</h2>", day=ctx.day(days[key][0][0])), fmt('<ul class="feed">{rows}</ul>', rows=join(fmt("<li>{row}</li>", row=line) for _, line in days[key]))]
    return page(ctx, "What happened", join(block(p) for p in parts), current="/history", ai=True, why="you are signed in and listed as a person who may use this page")
