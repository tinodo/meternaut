"""The start page, "Decisions": what waits for the person, and what was decided lately. Nothing else.

"Waiting for you" lists the requests that this person may answer, the larger saving first and then the one that has waited longest; each row is the headline, what it is
worth, the risk, how long ago it was found and one button. "Recently decided" is five one-line rows. When nothing waits, one sentence says so and says when the Watch looks
next. The switches, the runs and what Meternaut can change in Azure are on the pages of the platform team (ops.py), not here.
"""
from __future__ import annotations

import datetime as dt

from ..brief import Brief, ago_text, order_key, plan_headline, usd_text
from ..models import ADVICE_QUIET_DAYS, ADVISE, INVESTIGATION, DecisionRecord
from .common import brief_of, cases_by_id, effective_state, is_expired, may_answer, read
from .core import Ctx, Response, Safe, fmt, join, link_part, stamp
from .layout import block, notice, page, paragraph

WAITING_SHOWN = 10
WAITING_MAX = 100
DECIDED_SHOWN = 5
DECIDED_CONSIDERED = 12
HELD_CASES = 300  # the cases of each status that are looked at for the findings that are held back (the same number as cases/learning.py reads)
HELD_PLANS = 200  # the plans that are looked at for the answers that people gave lately (the same number as cases/learning.py reads)


def _waiting_line(ctx: Ctx, brief: Brief, later: bool) -> Safe:
    saving = fmt("About {amount} a month, {level}.", amount=usd_text(brief.saving.monthly), level=brief.saving.level) if brief.saving.monthly is not None else "No figure."
    _, ago = ago_text(ctx.now, brief.found_at)
    found = fmt(" Found {ago}.", ago=ago) if ago else Safe("")
    snoozed = " You chose to decide later." if later else ""
    return fmt("{saving} Risk: {risk}.{found}{snoozed}", saving=saving, risk=brief.risk.level, found=found, snoozed=snoozed)


def _row(ctx: Ctx, brief: Brief, later: bool) -> Safe:
    return fmt('<li><p class="row-title">{headline}</p><p class="row-meta">{meta}</p><p><a class="btn primary" href="{href}">Open<span class="visually-hidden">: {headline}</span></a></p></li>',
               headline=brief.headline, meta=_waiting_line(ctx, brief, later), href=ctx.url(f"/ok/{link_part(brief.plan_id)}"))


def held_count(ctx: Ctx) -> int:
    """How many findings of the investigation are held back: a case that needs a person or is proposed, with no request waiting for its resource, that nobody answered lately and that
    nobody marked do-not-touch. It is the set that cases/learning.OpenQuestions gives the Investigator as the questions with no request (a test pins that the two agree); the pages know
    the records and nothing of how they are read, so the count is made here from the records."""
    waiting = {p.resource_id.lower() for p in ctx.store.plans_open() if p.state == "open"}
    quiet = stamp(ctx.now - dt.timedelta(days=ADVICE_QUIET_DAYS))
    answered = {p.resource_id.lower() for p in ctx.store.plans_recent(HELD_PLANS) if p.family == ADVISE and p.state in ("declined", "consumed", "withdrawn") and p.created_at >= quiet}
    left = waiting | answered | {key.lower() for key in ctx.store.do_not_touch()}
    return sum(1 for status in ("needs_human", "proposed") for case in ctx.store.cases_recent(HELD_CASES, status)
               if case.detector == INVESTIGATION and case.resource_id.lower() not in left)


def _held(ctx: Ctx) -> Safe:
    """One sentence for the findings that no request waits for: nothing measured backs them yet, or the places for requests are full (approvals.py). The AIs look at them again at every
    search, so a person is told that they exist and that nothing is dropped. A store that cannot be read says nothing here: the list above says so."""
    held, _ = read(lambda: held_count(ctx), 0)
    if held <= 0:
        return Safe("")
    many = held != 1
    return paragraph(f"{held} finding{'s are' if many else ' is'} held back: no measurement backs {'them' if many else 'it'} yet, or the places for requests are full. "
                     f"The AIs look at {'them' if many else 'it'} again at the next investigation.")


def _waiting(ctx: Ctx) -> Safe:
    plans, ok = read(lambda: ctx.store.plans_open(), [])
    if not ok:
        return notice("error", "The requests cannot be read", "I cannot read the open requests now. Nothing has changed.")
    mine = [p for p in plans if p.state == "open" and may_answer(ctx.principal, p) and not is_expired(ctx, p)]  # type: ignore[arg-type]
    later_ids = {d.plan_id for d in read(lambda: ctx.store.decisions_by(ctx.principal.oid, 200), [])[0] if d.decision == "later"}  # type: ignore[union-attr]
    cases = cases_by_id(ctx, {p.case_id for p in mine})
    briefs = sorted(((brief_of(ctx, plan, cases.get(plan.case_id)), plan.plan_id in later_ids) for plan in mine), key=lambda item: (item[1], order_key(item[0])))
    heading = Safe(f"<h2>Waiting for you ({len(briefs)})</h2>")
    if not briefs:
        return join([heading, paragraph(f"Nothing waits for you. The next search is {ctx.next_search()}."), _held(ctx)])
    every = ctx.request.query.get("all") == "1"
    shown = briefs[:WAITING_MAX if every else WAITING_SHOWN]
    rest = len(briefs) - len(shown)
    more = paragraph(fmt('{n} more wait. <a href="{href}">Show all</a>.', n=rest, href=ctx.url("/?all=1"))) if rest > 0 else Safe("")
    return join([heading, fmt('<ol class="rows">{rows}</ol>', rows=join(_row(ctx, brief, later) for brief, later in shown)), more, _held(ctx)])


def _recently(ctx: Ctx) -> Safe:
    """The last five requests that were decided (or that nobody answered), for the person who is named in them: what, who, when and the result."""
    plans, ok = read(lambda: ctx.store.plans_recent(60), [])
    heading = Safe("<h2>Recently decided</h2>")
    if not ok:
        return join([heading, notice("error", "The decisions cannot be read", "I cannot read the recent decisions now. Nothing has changed.")])
    actions = {a.plan_id: a for a in read(lambda: ctx.store.actions_recent(100), [])[0]}
    rows: list[tuple[str, Safe]] = []
    for plan in [p for p in plans if may_answer(ctx.principal, p) and effective_state(ctx, p) != "open"][:DECIDED_CONSIDERED]:  # type: ignore[arg-type]
        decisions: list[DecisionRecord] = read(lambda plan=plan: ctx.store.decisions_of_plan(plan.plan_id), [])[0]
        outcome = brief_of(ctx, plan, None, action=actions.get(plan.plan_id), decisions=decisions).outcome
        if not outcome.state:
            continue
        by = fmt(", {who}", who=outcome.by) if outcome.by else Safe("")
        rows.append((outcome.at or plan.created_at, fmt("{headline}: {result}{by} on {day}.", headline=plan_headline(plan), result=outcome.result, by=by, day=ctx.day(outcome.at or plan.created_at))))
    rows.sort(key=lambda item: item[0], reverse=True)
    if not rows:
        return join([heading, paragraph("Nothing was decided yet.")])
    return join([heading, fmt('<ul class="feed">{rows}</ul>', rows=join(fmt("<li>{row}</li>", row=row) for _, row in rows[:DECIDED_SHOWN]))])


def home(ctx: Ctx) -> Response:
    parts: list[object] = [Safe("<h1>Decisions</h1>"), _waiting(ctx), _recently(ctx)]
    return page(ctx, "Decisions", join(block(p) for p in parts), current="/", ai=True, why="you are signed in and listed as a person who may use this page")
