"""The two pages about what happened to a person's own requests: the decisions they made, and what the runner did for their plans."""
from __future__ import annotations

import re

from ..models import ActionRecord, DecisionRecord, PlanRecord
from . import words
from .common import action_rows, read, start_block, verification_text
from .core import Ctx, Response, Safe, fmt, join, link_part
from .layout import block, code, link, notice, page, paragraph, summary, table

SCOPE = re.compile(r"/subscriptions/([^/]+)/resourceGroups/([^/]+)", re.I)
DECISIONS_SHOWN = 50
ACTIONS_SHOWN = 100


def _plans(ctx: Ctx, wanted: set[str]) -> dict[str, PlanRecord]:
    """The plans of these ids: the recent plans in one read, and the others one by one."""
    recent, _ = read(lambda: ctx.store.plans_recent(200), [])
    found = {plan.plan_id: plan for plan in recent}
    for plan_id in sorted(wanted - found.keys()):
        plan, _ = read(lambda plan_id=plan_id: ctx.store.plan_get(plan_id), None)
        if plan is not None:
            found[plan_id] = plan
    return found


def _actions(ctx: Ctx, wanted: set[str]) -> dict[str, ActionRecord]:
    recent, _ = read(lambda: ctx.store.actions_recent(200), [])
    found = {action.plan_id: action for action in recent}
    for plan_id in sorted(wanted - found.keys()):
        action, _ = read(lambda plan_id=plan_id: ctx.store.action_get(plan_id), None)
        if action is not None:
            found[plan_id] = action
    return found


def _outcome(ctx: Ctx, decision: DecisionRecord, plan: PlanRecord | None, action: ActionRecord | None) -> Safe:
    """What came of one decision, in plain words. A deletion that ran is said to be one that cannot be undone."""
    lines: list[object] = []
    if decision.decision == "decline":
        lines.append("You said no. Nothing changed, and the request is closed.")
    elif decision.decision == "not_mine":
        lines.append("You said that this is not yours. Nothing is approved.")
    elif decision.decision == "ask":
        lines.append("You asked a question or made a suggestion. It approves nothing. " + (words.PLAN_STATE.get(plan.state, plan.state) if plan is not None else ""))
    elif action is not None:
        state = words.ACTION_STATE.get(action.state, action.state)
        lines.append(state)
        if action.state == "queued" and action.start_after:
            lines.append(fmt("It starts at {when}.", when=ctx.when(action.start_after)))
        if action.result and action.result != state:
            lines.append(action.result)
        if action.error and action.error != action.result:
            lines.append(action.error)
        if action.verification:
            lines.append(verification_text(ctx, action.verification))
        if plan is not None and plan.family.startswith("delete") and action.state in ("queued", "running", "done", "verified", "unknown"):
            lines.append("Once it has run, a deletion cannot be undone." if action.state == "queued" else "A deletion cannot be undone.")
    else:
        lines.append(words.PLAN_STATE.get(plan.state, plan.state) if plan is not None else "The request is no longer stored.")
    return join(paragraph(line) for line in lines)


def _request_cell(ctx: Ctx, decision: DecisionRecord, plan: PlanRecord | None) -> Safe:
    """The request that a decision was about. The plan's page is linked only for a person who may answer it."""
    if plan is None:
        return fmt('The request is no longer stored.<br><span class="muted">Plan code {code}</span>', code=decision.plan_code)
    named = ctx.principal.oid in {a.lower() for a in plan.approvers}  # type: ignore[union-attr]
    title = link(ctx.url(f"/ok/{link_part(plan.plan_id)}"), plan.title) if named else plan.title
    return fmt('{title}<br><span class="muted">Plan code {code}</span>', title=title, code=plan.code)


def decisions(ctx: Ctx) -> Response:
    mine, ok = read(lambda: ctx.store.decisions_by(ctx.principal.oid, DECISIONS_SHOWN), [])  # type: ignore[union-attr]
    parts: list[object] = [
        Safe("<h1>My decisions</h1>"),
        paragraph("Every answer given in your name: what you decided, when, what the runner did and what came of it. Check that each approval is one that you gave. "
                  "If one is not, use Talk to a person below.", "lead"),
    ]
    if not ok:
        parts.append(notice("error", "Your decisions cannot be read", "I cannot read your decisions now. Nothing has changed."))
    elif not mine:
        parts.append(paragraph("You have not answered a request yet."))
    else:
        plans = _plans(ctx, {d.plan_id for d in mine})
        actions = _actions(ctx, {d.plan_id for d in mine if d.decision == "approve"})
        rows = []
        for decision in mine:
            plan, action = plans.get(decision.plan_id), actions.get(decision.plan_id)
            answer = fmt("{word}{note}", word=words.DECISION.get(decision.decision, decision.decision),
                         note=fmt('<br><span class="muted">Your note: </span>{note}', note=decision.note) if decision.note else "")
            rows.append([ctx.when(decision.at), _request_cell(ctx, decision, plan), answer, _outcome(ctx, decision, plan, action)])
        parts.append(table("decisions", f"Your latest {DECISIONS_SHOWN} decisions, newest first", ["When", "Request", "Your answer", "What came of it"], rows))
    return page(ctx, "My decisions", join(block(p) for p in parts), current="/me/decisions", why="This page lists the answers that were recorded in your name.")


def _where(action: ActionRecord, plan: PlanRecord | None) -> str:
    if plan is not None:
        return f"Resource group {plan.resource_group}, subscription {plan.subscription_id}"
    match = SCOPE.search(action.resource_id or "")
    return f"Resource group {match.group(2)}, subscription {match.group(1)}" if match else "not recorded"


def activity(ctx: Ctx) -> Response:
    me = ctx.principal.oid  # type: ignore[union-attr]
    mine, _ = read(lambda: ctx.store.decisions_by(me, 200), [])
    mine_ids, approved = {d.plan_id for d in mine}, {d.plan_id for d in mine if d.decision == "approve"}
    actions, ok = read(lambda: ctx.store.actions_recent(ACTIONS_SHOWN), [])
    plans = _plans(ctx, mine_ids & {a.plan_id for a in actions})
    ours = [a for a in actions if a.plan_id in mine_ids or (a.plan_id in plans and me in {x.lower() for x in plans[a.plan_id].approvers})]
    parts: list[object] = [
        Safe("<h1>What I did here</h1>"),
        paragraph("Every change that the runner made, or was asked to make, for a plan that names you as an approver or that you answered: what changed, where, when, "
                  "the result and what the check afterwards found.", "lead"),
        paragraph("No standing permission exists yet. Meternaut changes something only after a person approves that exact change on its own page."),
    ]
    if not ok:
        parts.append(notice("error", "The changes cannot be read", "I cannot read the changes now. Nothing has changed."))
    elif not ours:
        parts.append(paragraph("Nothing was changed for your plans yet."))
    for index, action in enumerate(ours, 1):
        plan = plans.get(action.plan_id)
        title = plan.title if plan is not None else words.family_words(action.family)
        name = plan.resource_name if plan is not None else action.resource_id.rsplit("/", 1)[-1]
        rows = [("What changed", title), ("Resource", fmt("{name}<br>{rid}", name=name, rid=code(action.resource_id))), ("Where", _where(action, plan))] + action_rows(ctx, action)
        extra = start_block(ctx, plan, action, action.plan_id in approved) if plan is not None else Safe("")
        parts.append(fmt('<section aria-labelledby="change-{n}"><h2 id="change-{n}">{title}: {name}</h2>{rows}{extra}</section>', n=index, title=words.family_words(action.family),
                         name=name, rows=summary(rows), extra=extra))
    return page(ctx, "What I did here", join(block(p) for p in parts), current="/me/activity", why="This page lists the changes made for plans that name you or that you answered.")
