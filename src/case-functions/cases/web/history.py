"""History, "What happened": a feed of the last 30 days, newest day first, drawn from the style guide.

At the top three tiles count what happened (decisions, changes made, new findings). Under them each day is a list of lines, and a line is a chip that says what kind of thing it was, the title of
the request as a link (or, for the findings of a day, how many) and one quiet part: who, why, or what came of it. Three kinds of line: what people decided (with their reason, for a decline),
the changes that were made and checked, and, for each day, how many new findings there were. A person sees the decisions and the changes of the requests that they are named in, and the number
of findings; the run tables and the cases are on the pages of the platform team (ops.py). The old addresses of "My decisions" and "What I did here" answer with this page.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..brief import REASON_WORDS, plan_headline
from ..models import ActionRecord, DecisionRecord, PlanRecord
from .common import effective_state, may_answer, read
from .core import Ctx, Response, Safe, fmt, join, link_part, stamp
from .figures import chip, short_title
from .layout import head, kpi, kpis, link, notice, page, paragraph

DAYS = 30
PLANS_READ = 40
MAX_DECISION_AGE = 15  # a request is answered within days of its making; an older plan has nothing to say in the last 30 days
COUNTED = ("proposed", "needs_human", "awaiting_ok", "approved", "running", "done", "failed", "declined", "expired", "verified", "acknowledged")
# What kind of line it is, as the chip says it: the word, the colour class and the shape (the guide: a chip is a word and a shape, never a colour alone).
KINDS = {"approved": ("Approved", "info", "square"), "worth": ("Worth acting on", "info", "square"), "declined": ("Declined", "", "square"), "not-worth": ("Not worth it", "", "square"),
         "not-mine": ("Not theirs", "", "square"), "made": ("Change made", "low", "circle"), "unchanged": ("Nothing changed", "", "square"), "failed": ("Change not made", "high", "diamond"),
         "checked": ("Checked", "low", "circle"), "expired": ("Expired", "", "square"), "closed": ("Closed", "", "square"), "search": ("Search", "info", "square")}
DECISIONS = ("approved", "worth", "declined", "not-worth", "not-mine")


@dataclass(frozen=True)
class Event:
    """One line of the feed: when, what kind (a key of KINDS), the main part, the quiet part, and how many findings it counts (a line of findings only)."""

    at: str
    kind: str
    what: Safe | str
    note: Safe | str = ""
    count: int = 0


def _title(plan: PlanRecord) -> str:
    return short_title(plan_headline(plan), plan.resource_group)


def _headline(ctx: Ctx, plan: PlanRecord) -> Safe:
    return link(ctx.url(f"/ok/{link_part(plan.plan_id)}"), _title(plan))


def _decision_event(ctx: Ctx, plan: PlanRecord, decision: DecisionRecord) -> Event | None:
    advice = plan.family == "advise"
    who = decision.approver_name or "A person"
    if decision.decision == "decline":
        reason = REASON_WORDS.get(decision.reason, "")
        return Event(decision.at, "not-worth" if advice else "declined", _headline(ctx, plan), fmt("{who}{reason}", who=who, reason=f" · reason: {reason}" if reason else ""))
    if decision.decision == "not_mine":
        return Event(decision.at, "not-mine", _headline(ctx, plan), who)
    if decision.decision == "approve":
        return Event(decision.at, "worth" if advice else "approved", _headline(ctx, plan), who)
    return None


def _action_events(ctx: Ctx, plan: PlanRecord, action: ActionRecord) -> list[Event]:
    events: list[Event] = []
    if action.finished_at and action.state in ("done", "verified", "unknown"):
        events.append(Event(action.finished_at, "unchanged" if action.no_change else "made", _headline(ctx, plan), action.result))  # an approval that found nothing to change wrote nothing
    elif action.finished_at and action.state == "failed":
        events.append(Event(action.finished_at, "failed", _headline(ctx, plan), action.error or action.result))
    if action.verified_at:
        note = action.verification.get("note", "") if isinstance(action.verification, dict) else ""
        events.append(Event(action.verified_at, "checked", _headline(ctx, plan), note or "Cost lines confirm it."))
    return events


def _events(ctx: Ctx, since: str) -> tuple[list[Event], bool]:
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
    events: list[Event] = []
    for plan in mine:
        for decision in read(lambda plan=plan: ctx.store.decisions_of_plan(plan.plan_id), [])[0]:
            event = _decision_event(ctx, plan, decision)
            if event is not None:
                events.append(event)
        if plan.family != "advise" and plan.plan_id in actions:
            events += _action_events(ctx, plan, actions[plan.plan_id])
        if effective_state(ctx, plan) == "expired":
            events.append(Event(plan.expires_at, "expired", _headline(ctx, plan), "Nobody answered in time."))
    for found in quiet.values():
        events.append(Event(max(found), "closed", f"{len(found)} request{'' if len(found) == 1 else 's'} to look at a finding", "Closed with no answer."))
    cases = read(lambda: ctx.store.cases_recent(1000), [])[0]
    per_day: dict[str, list[str]] = {}
    for case in cases:
        if case.status in COUNTED and case.first_seen_at >= since:
            per_day.setdefault(ctx.day_key(case.first_seen_at), []).append(case.first_seen_at)
    for found in per_day.values():
        events.append(Event(max(found), "search", f"{len(found)} new finding{'' if len(found) == 1 else 's'}", "", len(found)))
    return [event for event in events if event.at >= since], ok


def _line(event: Event) -> Safe:
    label, kind, shape = KINDS[event.kind]
    note = fmt('<span class="quiet">{note}</span>', note=event.note) if event.note else Safe("")
    return fmt("<li>{chip}<span>{what}</span>{note}</li>", chip=chip(label, kind, shape), what=event.what, note=note)


def _tiles(events: list[Event]) -> Safe:
    decided = sum(1 for e in events if e.kind in DECISIONS)
    made = sum(1 for e in events if e.kind == "made")
    found = sum(e.count for e in events)
    return kpis(kpi("Decisions", str(decided), "", f"Answers that people gave in the last {DAYS} days."),
                kpi("Changes made", str(made), "", "Made in Azure with the approver's own rights."),
                kpi("New findings", str(found), "", f"Found by the search in the last {DAYS} days."), label=f"The last {DAYS} days")


def history(ctx: Ctx) -> Response:
    since = stamp(ctx.now - dt.timedelta(days=DAYS))
    events, ok = _events(ctx, since)
    parts: list[object] = [head("What happened", f"The last {DAYS} days: what was decided, what was changed and checked, and how many new findings there were each day.")]
    if not ok:
        parts.append(notice("error", "The history cannot be read", "I cannot read the requests now. Nothing has changed."))
    if not events:
        parts.append(paragraph(f"Nothing has happened in the last {DAYS} days."))
    else:
        parts.append(_tiles(events))
    days: dict[str, list[Event]] = {}
    for event in sorted(events, key=lambda item: item.at, reverse=True):
        days.setdefault(ctx.day_key(event.at), []).append(event)
    for key in sorted(days, reverse=True):
        anchor = f"day-{link_part(key)}"
        parts.append(fmt('<section aria-labelledby="{anchor}"><div class="sec"><h2 id="{anchor}">{day}</h2></div><ul class="recent">{rows}</ul></section>', anchor=anchor,
                         day=ctx.day(days[key][0].at), rows=join(_line(event) for event in days[key])))
    return page(ctx, "What happened", join(parts), current="/history", ai=True, why="you are signed in and listed as a person who may use this page")
