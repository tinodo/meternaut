"""The start page, "Decisions": what waits for the person, ranked by what is at stake, and what was decided lately. Nothing else.

It is built from the style guide (docs/ui/style-guide.html). The decision with the most at stake is in focus, with its figures and a chart of its cost. The others follow in two lanes, the
changes that are ready to decide and the findings that are worth a closer look: one row for each decision, with its figure a year and a month, its risk and a small chart of its cost.
Findings of one kind that nobody asked about as a group are one row that opens. Money is what Cost Management reports, in US dollars, and a year is twelve times a month. When nothing waits,
one sentence says so and says when the Watch looks next. The switches, the runs and what Meternaut can change in Azure are on the pages of the platform team (ops.py), not here.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..brief import Brief, ago_text, plain, plan_headline, things
from ..models import ADVICE_QUIET_DAYS, ADVISE, INVESTIGATION, ActionRecord, CaseRecord, PlanRecord
from .common import brief_of, cases_by_id, effective_state, is_expired, may_answer, read
from .core import Ctx, Response, Safe, esc, fmt, join, link_part, stamp
from .figures import NO_LINES, READ_LATER, a_year, bar, chart, chip, dollars, number_of, series_of, spark, summed
from .layout import code, details, notice, page, paragraph, table

ROWS_SHOWN = 12  # the rows of each lane that the page shows, unless a person asks for all of them
ROWS_MAX = 100
DECIDED_SHOWN = 5
DECIDED_CONSIDERED = 12
RECENT_PLANS = 60
RECENT_ACTIONS = 100
HELD_CASES = 300  # the cases of each status that are looked at for the findings that are held back (the same number as cases/learning.py reads)
HELD_PLANS = 200  # the plans that are looked at for the answers that people gave lately (the same number as cases/learning.py reads)
SORTS = (("impact", "Impact", "Most at stake first."), ("age", "Age", "Waiting longest first."), ("risk", "Risk", "Lowest risk first."))
RISKS = {"low": ("Low risk", "low", "circle", 0), "medium": ("Medium risk", "mid", "triangle", 1), "high": ("High risk", "high", "diamond", 2)}
WEAKEST_FIRST = ("Scenario", "Expected", "Verified")
OUTCOMES = {"done": ("Done", "low", "circle"), "verified": ("Done", "low", "circle"), "unchanged": ("Nothing to change", "", "square"), "declined": ("Declined", "", "square"),
            "failed": ("Failed", "high", "diamond"), "approved": ("Approved", "info", "square"), "running": ("Running", "info", "square"), "answered": ("Answered", "info", "square"),
            "withdrawn": ("Withdrawn", "", "square"), "expired": ("Expired", "", "square")}


@dataclass(frozen=True)
class Row:
    """One open request of this person, with its case."""

    brief: Brief
    case: CaseRecord | None
    later: bool

    @property
    def cost(self) -> float | None:
        """What the finding costs in 30 days, from the cost lines: everything that it stands for when it is a group. None when no cost line was read."""
        group = self.brief.group
        if group is not None and group.cost is not None:
            return group.cost
        return number_of(self.case.cost_usd_30d) if self.case is not None else None

    @property
    def series(self) -> list[float] | None:
        return series_of(self.case.cost_series) if self.case is not None else None


@dataclass(frozen=True)
class Figure:
    """What is at stake in a row, in a month: a saving (with its level and its basis), a cost (the most that a change could save, which nothing has measured), or nothing that can be
    shown (and why)."""

    state: str  # save, cost or none
    label: str
    monthly: float | None
    level: str
    note: str


@dataclass(frozen=True)
class Unit:
    """What a row of the page stands for: one request, or the requests of one kind that are shown as one row."""

    members: tuple[Row, ...]
    figure: Figure
    series: list[float] | None

    @property
    def first(self) -> Row:
        return self.members[0]

    @property
    def later(self) -> bool:
        return all(m.later for m in self.members)

    @property
    def age(self) -> int:
        return max(m.brief.age_days or 0 for m in self.members)

    @property
    def risk(self) -> int:
        return max(RISKS.get(m.brief.risk.level, RISKS["medium"])[3] for m in self.members)

    @property
    def reason(self) -> str:
        """Why there is no chart: the cost lines are there and the series is read at the next search, or no cost line exists yet."""
        return READ_LATER if any((m.cost or 0) > 0 for m in self.members) else NO_LINES


def _figure(members: Sequence[Row]) -> Figure:
    savings = [m.brief.saving for m in members]
    if all(s.monthly is not None for s in savings):
        levels = {s.level for s in savings}
        level = savings[0].level if len(levels) == 1 else next((w for w in WEAKEST_FIRST if w in levels), "Scenario")
        basis = savings[0].basis if len(members) == 1 else "the figures of each, added up"
        return Figure("save", f"Saves, {level}", sum(s.monthly for s in savings), level, f"Based on {basis}.")  # type: ignore[misc]
    known = [m.cost for m in members if m.cost is not None]
    if known and sum(known) > 0:
        return Figure("cost", "Costs, saving not measured", sum(known), "", "The most that a change could save: what it would save was not worked out.")
    return Figure("none", "Cost not visible", None, "", "No cost line in the last 30 days." if known else "No cost line was read yet.")


def _unit(members: Sequence[Row]) -> Unit:
    ranked = sorted(members, key=lambda m: -(m.brief.saving.monthly or m.cost or 0.0))
    series = ranked[0].series if len(ranked) == 1 else summed([m.series for m in ranked])
    return Unit(tuple(ranked), _figure(ranked), series)


def _units(rows: Sequence[Row]) -> list[Unit]:
    """The rows of the page. A change is a row of its own: a person approves one change at a time. A finding that stands for many resources is a row of its own already. Advice about
    one resource each, of one kind and one recommendation, is one row that opens."""
    kinds: dict[tuple, list[Row]] = {}
    units = []
    for row in rows:
        if row.brief.kind == "change" or row.brief.group is not None:
            units.append(_unit([row]))
        else:
            kinds.setdefault((row.brief.family, row.brief.where.kind, row.case.recommendation if row.case is not None else "", row.later), []).append(row)
    return units + [_unit(members) for members in kinds.values()]


def _ranked(units: Sequence[Unit], sort: str) -> list[Unit]:
    """In the order that was asked for: by what is at stake (what has no figure last), by how long it has waited, or by risk. What a person put off is last, and ties go by plan."""
    def key(unit: Unit) -> tuple:
        stake = unit.figure.monthly
        amount = (0, -stake) if stake is not None else (1, 0.0)
        waited = -unit.age
        order = {"age": (waited, *amount), "risk": (unit.risk, *amount, waited)}.get(sort, (*amount, waited))
        return (unit.later, *order, unit.first.brief.plan_id)
    return sorted(units, key=key)


def _title(unit: Unit) -> tuple[Safe, str]:
    """The title of a row as markup and as plain text: how many of what and where when it stands for many, else the headline without its place (the line under it says the place), with
    the name of the resource in code type."""
    first = unit.first.brief
    if len(unit.members) > 1:
        rtype = unit.first.case.resource_type if unit.first.case is not None else ""
        text = things(len(unit.members), rtype, len({m.brief.where.group for m in unit.members if m.brief.where.group}))
        return esc(text), text
    if first.group is not None:
        text = things(first.group.count, first.group.kind, first.group.groups)
        return esc(text), text
    text, place = first.headline, f" in group {first.where.group}" if first.where.group else ""
    text = text[: -len(place)] if place and text.endswith(place) else text
    text = "Review " + text[8:] if text.startswith("Look at ") else text
    name = first.where.name
    before, found, after = text.partition(name) if name else (text, "", "")
    return (fmt("{before}<code>{name}</code>{after}", before=before, name=name, after=after) if found else esc(text)), text


def _meta(ctx: Ctx, unit: Unit) -> str:
    oldest = max(unit.members, key=lambda m: m.brief.age_days or 0).brief
    _, ago = ago_text(ctx.now, oldest.found_at)
    one = unit.first.brief
    place = f"resource group {one.where.group}" if len(unit.members) == 1 and one.where.group else ""
    return " · ".join(part for part in (one.where.kind, place, f"found {ago}" if ago else "") if part)


def _chips(unit: Unit) -> Safe:
    label, kind, shape, _ = RISKS.get(max((m.brief.risk.level for m in unit.members), key=lambda level: RISKS.get(level, RISKS["medium"])[3]), RISKS["medium"])
    chips = [chip(label, kind, shape)]
    if unit.figure.state != "save":
        chips.append(chip("Needs measuring"))
    elif len(unit.members) == 1:
        level = unit.first.brief.confidence.level
        chips.append(chip(f"{level} confidence", "info" if level == "High" else ""))
    if unit.later:
        chips.append(chip("You chose to decide later"))
    return join(chips)


def _impact(unit: Unit, top: float) -> Safe:
    figure = unit.figure
    if figure.monthly is None:
        return fmt('<span class="impact none"><span class="lab">{label}</span><span class="y">—</span><span class="mo">{note}</span></span>', label=figure.label, note=figure.note)
    return fmt('<span class="impact {state}"><span class="lab">{label}</span><span class="y">{year}<small> a year</small></span><span class="mo">{month} a month</span>{bar}</span>',
               state=figure.state, label=figure.label, year=a_year(figure.monthly), month=dollars(figure.monthly), bar=bar(figure.monthly / top))


def _members(ctx: Ctx, unit: Unit, name: str) -> Safe:
    """What a row that opens holds: the first few resources of a finding that stands for many (and the one request about all of them), or each request of a row of advice of one kind."""
    first = unit.first.brief
    anchor = f"members-{link_part(first.plan_id)}"
    if first.group is not None:
        names = [n for n in dict.fromkeys([first.where.name, *first.group.names]) if n]
        rest = first.group.count - len(names)
        more = (paragraph(f"{rest} more. All {first.group.count} are in {first.group.groups} resource groups." if first.group.groups else f"{rest} more.", "quiet") if rest > 0 else Safe(""))
        listing = table(anchor, f"The first {len(names)} of {first.group.count}", ["Resource"], [[code(n)] for n in names], quiet_caption=True)
        buttons = fmt('<p class="acts"><a class="btn sm primary" href="{href}">Review all {count}</a></p>', href=ctx.url(f"/ok/{link_part(first.plan_id)}"), count=first.group.count)
        return join([listing, more, buttons])
    rows = [[code(m.brief.where.name), code(m.brief.where.group) if m.brief.where.group else "", dollars(m.cost) if m.cost is not None else "—",
             fmt('<a class="btn sm" href="{href}">Review<span class="visually-hidden">: {name}</span></a>', href=ctx.url(f"/ok/{link_part(m.brief.plan_id)}"), name=m.brief.where.name)]
            for m in unit.members]
    return table(anchor, f"The {len(unit.members)} requests: {name}", ["Resource", "Resource group", "A month", "Request"], rows, quiet_caption=True)


def _row(ctx: Ctx, unit: Unit, rank: int, top: float, primary: bool) -> Safe:
    markup, name = _title(unit)
    basis = fmt('<span class="m">{note}</span>', note=unit.figure.note) if unit.figure.state == "save" else Safe("")
    parts = fmt('<span class="rank">{rank}</span><span class="main"><span class="t">{title}</span><span class="m">{meta}</span>{basis}<span class="chips">{chips}</span></span>'
                '{impact}<span class="spark">{spark}</span>', rank=rank, title=markup, meta=_meta(ctx, unit), basis=basis, chips=_chips(unit), impact=_impact(unit, top),
                spark=spark(unit.series, unit.reason))
    if len(unit.members) == 1 and unit.first.brief.group is None:
        button = fmt('<span class="act"><a class="btn sm{primary}" href="{href}">Review<span class="visually-hidden">: {name}</span></a></span>',
                     primary=" primary" if primary else "", href=ctx.url(f"/ok/{link_part(unit.first.brief.plan_id)}"), name=name)
        return fmt('<li class="item">{parts}{button}</li>', parts=parts, button=button)
    count = unit.first.brief.group.count if unit.first.brief.group is not None else len(unit.members)
    toggle = fmt('<span class="act"><span class="btn sm"><span class="when-closed">Show {count}</span><span class="when-open">Hide</span></span></span>', count=count)
    return fmt('<li><details class="grp"><summary class="item">{parts}{toggle}</summary><div class="members">{members}</div></details></li>', parts=parts, toggle=toggle,
               members=_members(ctx, unit, name))


def _focus(ctx: Ctx, unit: Unit) -> Safe:
    """The decision with the most at stake, large: its figures, what changes and why, what was checked, how to undo it, and a chart of its cost."""
    brief, figure = unit.first.brief, unit.figure
    markup, name = _title(unit)
    if figure.monthly is not None:
        big = fmt('<p class="fig{save}">{year}<small> a year</small></p>', save=" save" if figure.state == "save" else "", year=a_year(figure.monthly))
        sub = f"{figure.label}. {dollars(figure.monthly)} a month. {figure.note}"
    else:
        big, sub = Safe('<p class="fig">—</p>'), f"{figure.label}. {figure.note}"
    facts = [("What changes", brief.change), ("Why", plain(brief.reasoning, 240)), ("Checked", brief.rechecked), ("Undo", brief.undo.how)]
    return fmt('<article class="focus" aria-labelledby="focus-title"><div><p class="eyebrow"><span class="rank first" aria-hidden="true">1</span>Start here</p>'
               '<h3 id="focus-title">{title}</h3><p class="m">{meta}</p>{big}<p class="figsub">{sub}</p><p class="chips">{chips}</p><dl class="facts">{facts}</dl>'
               '<p class="acts"><a class="btn primary" href="{href}">Review and decide<span class="visually-hidden">: {name}</span></a></p></div><div>{chart}</div></article>',
               title=markup, meta=_meta(ctx, unit), big=big, sub=sub, chips=_chips(unit),
               facts=join(fmt("<dt>{name}</dt><dd>{text}</dd>", name=label, text=text) for label, text in facts if text), href=ctx.url(f"/ok/{link_part(brief.plan_id)}"), name=name,
               chart=chart(unit.series, unit.reason))


def _lane(ctx: Ctx, anchor: str, title: str, blurb: str, units: Sequence[Unit], top: float, show: int, focus: bool) -> Safe:
    if not units:
        return Safe("")
    shown = units[:show]
    rows = join(_row(ctx, unit, rank, top, focus) for rank, unit in enumerate(shown[1:] if focus else shown, 2 if focus else 1))
    first = _focus(ctx, shown[0]) if focus else Safe("")
    items = fmt('<ol class="items">{rows}</ol>', rows=rows) if len(shown) > (1 if focus else 0) else Safe("")
    return fmt('<section aria-labelledby="{anchor}"><div class="sec"><h2 id="{anchor}">{title}</h2><p>{blurb}</p></div>{first}{items}</section>', anchor=anchor,
               title=title, blurb=blurb, first=first, items=items)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _kpi(label: str, value: str, unit: str, note: str, good: bool = False) -> Safe:
    return fmt('<li class="kpi{good}"><p class="k">{label}</p><p class="v">{value}{unit}</p><p class="n">{note}</p></li>', good=" good" if good else "", label=label, value=value,
               unit=Safe(f"<small> {unit}</small>") if unit else Safe(""), note=note)


def _summary(units: Sequence[Unit], measured: tuple[float, int]) -> Safe:
    saves = [u for u in units if u.figure.state == "save"]
    costs = [u for u in units if u.figure.state == "cost"]
    levels = ", ".join(w for w in WEAKEST_FIRST if w in {u.figure.level for u in saves})
    ready = (_kpi("Ready to save", a_year(sum(u.figure.monthly for u in saves)), "a year", f"{_count(len(saves), 'decision')} · {levels}. The basis is in each row.", True)  # type: ignore[misc]
             if saves else _kpi("Ready to save", "—", "", "No saving is known yet."))
    under = (_kpi("Cost under review", a_year(sum(u.figure.monthly for u in costs)), "a year", f"{_count(len(costs), 'decision')} · saving not measured. Cost Management, 30 days.")  # type: ignore[misc]
             if costs else _kpi("Cost under review", "—", "", "Nothing is under review."))
    total, count = measured
    done = (_kpi("Saving measured", a_year(total), "a year", f"{dollars(total)} a month, confirmed by Cost Management after {_count(count, 'change')}.", True)
            if total > 0 else _kpi("Saving measured", "—", "", "Nothing measured yet. Cost lines arrive 8 to 72 hours after a change."))
    return fmt('<ul class="kpis" aria-label="Summary">{ready}{under}{done}</ul>', ready=ready, under=under, done=done)


def _head(ctx: Ctx, units: Sequence[Unit], sort: str) -> Safe:
    saves = sum(u.figure.monthly for u in units if u.figure.state == "save")  # type: ignore[misc]
    costs = sum(u.figure.monthly for u in units if u.figure.state == "cost")  # type: ignore[misc]
    if not units:
        lead = f"Nothing waits for you. The next search is {ctx.next_search()}."
    else:
        lead = f"{_count(len(units), 'decision')}."
        if saves > 0:
            lead += f" {a_year(saves)} a year is ready to save" + (f", and {a_year(costs)} a year more is under review." if costs > 0 else ".")
        elif costs > 0:
            lead += f" {a_year(costs)} a year is under review."
        lead += " Money is in US dollars, and a year is twelve times the month."
    links = join(fmt('<a href="{href}"{current}>{label}</a>', href=ctx.url(f"/?sort={key}"), label=label, current=Safe(' aria-current="true"') if key == sort else Safe(""))
                 for key, label, _ in SORTS)
    seg = fmt('<div class="seg" role="group" aria-label="Sort the decisions"><span>Sort by</span>{links}</div>', links=links) if len(units) > 1 else Safe("")
    return fmt('<div class="head"><div><h1>Decisions</h1><p>{lead}</p></div>{seg}</div>', lead=lead, seg=seg)


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
    """The findings that no request waits for: nothing measured backs them yet, or the places for requests are full (approvals.py). The AIs look at them again at every search, so a person
    is told that they exist and that nothing is dropped. A store that cannot be read says nothing here: the list above says so."""
    held, _ = read(lambda: held_count(ctx), 0)
    if held <= 0:
        return Safe("")
    many = held != 1
    return details(f"Held back: {_count(held, 'finding')}", paragraph(f"No measurement backs {'them' if many else 'it'} yet, or the places for requests are full. "
                                                                     f"The AIs look at {'them' if many else 'it'} again at the next investigation."))


def _open(ctx: Ctx) -> tuple[list[Row], bool]:
    plans, ok = read(lambda: ctx.store.plans_open(), [])
    if not ok:
        return [], False
    mine = [p for p in plans if p.state == "open" and may_answer(ctx.principal, p) and not is_expired(ctx, p)]  # type: ignore[arg-type]
    later_ids = {d.plan_id for d in read(lambda: ctx.store.decisions_by(ctx.principal.oid, 200), [])[0] if d.decision == "later"}  # type: ignore[union-attr]
    cases = cases_by_id(ctx, {p.case_id for p in mine})
    return [Row(brief_of(ctx, plan, cases.get(plan.case_id)), cases.get(plan.case_id), plan.plan_id in later_ids) for plan in mine], True


def _measured(ctx: Ctx, plans: Sequence[PlanRecord], actions: Mapping[str, ActionRecord]) -> tuple[float, int]:
    """What Cost Management confirmed after the changes of this person's requests, a month, and after how many changes: what code measured, never what was expected."""
    total, count = 0.0, 0
    for plan in plans:
        action = actions.get(plan.plan_id)
        if action is not None and action.state == "verified" and may_answer(ctx.principal, plan):  # type: ignore[arg-type]
            saving = brief_of(ctx, plan, None, action=action).saving
            if saving.level == "Verified" and saving.monthly:
                total, count = total + saving.monthly, count + 1
    return total, count


def _recently(ctx: Ctx, plans: Sequence[PlanRecord], ok: bool, actions: Mapping[str, ActionRecord]) -> Safe:
    """The last five requests that were decided (or that nobody answered, for a change), for the person who is named in them: what, who, when and the result."""
    heading = Safe('<div class="sec"><h2 id="recent">Recently decided</h2></div>')
    if not ok:
        return join([heading, notice("error", "The decisions cannot be read", "I cannot read the recent decisions now. Nothing has changed.")])
    rows: list[tuple[str, Safe]] = []
    for plan in [p for p in plans if may_answer(ctx.principal, p) and effective_state(ctx, p) != "open" and not (p.family == ADVISE and effective_state(ctx, p) == "expired")][:DECIDED_CONSIDERED]:  # type: ignore[arg-type]
        outcome = brief_of(ctx, plan, None, action=actions.get(plan.plan_id), decisions=read(lambda plan=plan: ctx.store.decisions_of_plan(plan.plan_id), [])[0]).outcome
        if not outcome.state:
            continue
        label, kind, shape = OUTCOMES.get(outcome.state, (outcome.state.capitalize(), "", "square"))
        who = fmt("{by}, {day}", by=outcome.by, day=ctx.day(outcome.at or plan.created_at)) if outcome.by else ctx.day(outcome.at or plan.created_at)
        rows.append((outcome.at or plan.created_at, fmt('<li>{chip}<span>{headline}: {result}</span><span class="quiet">{who}</span></li>', chip=chip(label, kind, shape),
                                                        headline=plan_headline(plan), result=outcome.result, who=who)))
    rows.sort(key=lambda item: item[0], reverse=True)
    if not rows:
        return join([heading, paragraph("Nothing was decided yet.")])
    return join([heading, fmt('<ul class="recent">{rows}</ul>', rows=join(row for _, row in rows[:DECIDED_SHOWN]))])


def home(ctx: Ctx) -> Response:
    sort = ctx.request.query.get("sort")
    sort = sort if sort in {key for key, _, _ in SORTS} else "impact"
    rows, ok = _open(ctx)
    plans, plans_ok = read(lambda: ctx.store.plans_recent(RECENT_PLANS), [])
    actions = {a.plan_id: a for a in read(lambda: ctx.store.actions_recent(RECENT_ACTIONS), [])[0]}
    units = _ranked(_units(rows), sort)
    if not ok:
        top = join([Safe("<h1>Decisions</h1>"), notice("error", "The requests cannot be read", "I cannot read the open requests now. Nothing has changed.")])
    else:
        ready = [u for u in units if u.first.brief.kind == "change"]
        look = [u for u in units if u.first.brief.kind != "change"]
        show = ROWS_MAX if ctx.request.query.get("all") == "1" else ROWS_SHOWN
        largest = max((u.figure.monthly for u in units if u.figure.monthly), default=1.0)
        rest = max(0, len(ready) - show) + max(0, len(look) - show)
        order = next(blurb for key, _, blurb in SORTS if key == sort)
        more = paragraph(fmt('{n} more wait. <a href="{href}">Show all</a>.', n=rest, href=ctx.url(f"/?sort={sort}&all=1"))) if rest else Safe("")
        top = join([_head(ctx, units, sort), _summary(units, _measured(ctx, plans, actions)) if units else Safe(""),
                    _lane(ctx, "ready", "Ready to decide", f"A change in Azure that you may approve. {order}", ready, largest, show, True),
                    _lane(ctx, "look", "Worth a closer look", f"No change is proposed yet. A saving here is an estimate, and a cost is the most that a change could save. {order}", look, largest,
                          show, False),
                    more, _held(ctx)])
    return page(ctx, "Decisions", join([top, _recently(ctx, plans, plans_ok, actions)]), current="/", ai=True, why="you are signed in and listed as a person who may use this page", wide=True)
