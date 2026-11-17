"""Savings found, for the roles ops and owner: every saving that Meternaut found, each finding counted once, by what became of it. Counts and money only; it changes nothing.

A line of the table is one level (Scenario, Expected or Verified) with its basis. A confirmed finding shows what Cost Management confirmed. What was declined, dropped or not finished is counted
and not added up. It reads at most PER findings of each status and says "at least" for what may be more, or could not be read.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import words
from .common import MORE, brief_of, counted, figure_cell, measured_tile, read, verified_brief
from .core import Ctx, Response, Safe, fmt, join, number
from .figures import NO_LINES, WEAKEST_FIRST, a_year, cost_of, figure_for
from .layout import head, kpi, kpis, link, notice, page, paragraph, table

PER = 1000  # the most that one read of the store gives
LEAD = ("Every saving that Meternaut found, each finding counted once, by what became of it. Money is in US dollars, and a year is twelve times the month. "
        "A saving is an estimate until Cost Management confirms it.")
NOTE = (f'It reads up to {PER:,} findings of each status, and a status that holds that many says "at least". '
        "No saving is added up for a finding that was declined, taken back, dropped or not finished. "
        '"Saving measured" counts every change that Cost Management confirmed, so it can be larger than the row "Confirmed by Cost Management".')
# Row, statuses, what became of them, and whether their savings are added up
GROUPS = (
    ("Waiting for a person", ("needs_human", "proposed", "awaiting_ok"), "A person has to answer or look at it before anything changes. Nothing closes it by time: if nobody answers, it goes on to the next person. "
     "Findings that are held back, with no request yet, are here too.", True),
    ("Being made", ("approved", "running"), "A person approved. The change is being made now.", True),
    ("Made, not yet confirmed", ("done",), f"The change was made. {NO_LINES}", True),
    ("Confirmed by Cost Management", ("verified",), words.CASE_STATUS["verified"][1], True),
    ("Worth acting on", ("acknowledged",), words.CASE_STATUS["acknowledged"][1], True),
    ("Declined", ("declined",), "A person said no. Nothing changed.", False),
    ("Taken back", ("expired",), "Meternaut took the request back, and the request says why. A finding that is still true is asked about again. Nothing changed.", False),
    ("Dropped", ("dropped",), "No change is suggested. The AIs advised keeping the resource.", False),
    ("Could not be finished", ("error", "failed"), "A check or a model call failed, or the change failed or was stopped.", False),
)


@dataclass
class Group:
    """A row: its findings, what could not be read, and its savings by level (a month, what each is based on, how many findings)."""

    name: str
    meaning: str
    added: bool
    cases: list = field(default_factory=list)
    failed: bool = False  # a status could not be read
    cut: bool = False  # a status holds as many findings as one read gives
    dead: bool = False  # no status could be read
    levels: dict = field(default_factory=dict)
    none: dict = field(default_factory=dict)  # why a finding has no saving figure -> how many

    @property
    def lower(self) -> bool:
        return self.failed or self.cut


def _read(ctx: Ctx, name: str, statuses: tuple, meaning: str, added: bool) -> Group:
    group, readable = Group(name, meaning, added), []
    for status in statuses:
        found, ok = read(lambda status=status: ctx.store.cases_recent(PER, status), [])
        group.cases += found
        readable.append(ok)
        group.cut = group.cut or len(found) >= PER
    group.failed, group.dead = not all(readable), not any(readable)
    return group


def _changes(ctx: Ctx) -> tuple[list, dict, bool, bool]:
    """What Cost Management confirmed (the id of the finding, the brief of the change), the newest action of each finding with its plan, and whether a read failed or is full."""
    plans, ok = read(lambda: ctx.store.plans_recent(PER), [])
    actions, ok_actions = read(lambda: ctx.store.actions_recent(PER), [])
    by_id, newest = {plan.plan_id: plan for plan in plans}, {}
    for action in actions:  # newest first
        newest.setdefault(action.case_id, (action, by_id.get(action.plan_id)))
    confirmed = [(action.case_id, brief) for action in actions if action.state == "verified" and (brief := verified_brief(ctx, by_id.get(action.plan_id), action)) is not None]
    return confirmed, newest, not (ok and ok_actions), max(len(plans), len(actions)) >= PER


def _add(ctx: Ctx, group: Group, confirmed: dict, newest: dict) -> None:
    for case in group.cases:
        action, plan = newest.get(case.case_id, (None, None))
        if case.status == "done" and action is not None and action.no_change:
            brief = brief_of(ctx, plan, case, action=action)  # nothing was written: the brief claims no saving
        else:
            brief = (confirmed.get(case.case_id) if case.status == "verified" else None) or brief_of(ctx, None, case)
        figure = figure_for([brief], [cost_of(brief, case)])
        if figure.state == "save":
            line = group.levels.setdefault(figure.level, [0.0, set(), 0])
            line[0] += figure.monthly  # type: ignore[operator]
            line[1].add(figure.note)
            line[2] += 1
        else:
            why = brief.saving.why_none if brief.saving.specific else figure.note
            group.none[why] = group.none.get(why, 0) + 1


def _tile(label: str, groups: list, value: str, unit: str, note: str, good: bool = False) -> Safe:
    """A tile over some rows: a dash when none could be read, and a plus and "there may be more" when one could not be read in full."""
    if all(group.dead for group in groups):
        return kpi(label, "—", "", "Cannot be read now.")
    lower = any(group.lower for group in groups)
    return kpi(label, value + ("+" if lower and value != "—" else ""), unit, note + (MORE if lower else ""), good)


def _money(label: str, groups: list, tail: str) -> Safe:
    lines = [line for group in groups for line in group.levels.values()]
    if not lines:
        return _tile(label, groups, "—", "", "No saving is known yet.")
    n, found = sum(line[2] for line in lines), sum(len(group.cases) for group in groups)
    levels = ", ".join(level for level in WEAKEST_FIRST if any(level in group.levels for group in groups))
    rest = counted(n, "finding") if n == found else f"{n:,} of {found:,} findings have a saving figure"
    return _tile(label, groups, a_year(sum(line[0] for line in lines)), "a year", f"{rest} · {levels}. {tail}", True)


def _tiles(groups: list, measured: list, failed: bool, cut: bool) -> Safe:
    """Saving measured adds up every confirmed change, as the Decisions page does for the changes of one person."""
    saved = kpi("Saving measured", "—", "", "Cannot be read now.") if failed else measured_tile(sum(measured), len(measured), cut)
    return kpis(_money("Found in all", [group for group in groups if group.added], "The basis is in the table."), _money("Waiting for a person", groups[:1], "A person has to answer or look at it."), saved)


def _row(group: Group) -> list:
    name = fmt('{name}<br><span class="muted">{meaning}</span>', name=group.name, meaning=group.meaning)
    if group.dead:
        return [name, "Cannot be read now.", "Not known.", "Not known."]
    lead = "At least " if group.lower else ""
    found = fmt("{lead}{n}{part}", lead=lead, n=number(len(group.cases)), part=Safe("<br>Part of it cannot be read now.") if group.failed else "")
    if not group.added:
        return [name, found, "No saving is claimed.", "Not added up."]
    saving = [figure_cell(f"Saves, {level}", line[0], next(iter(line[1])) if len(line[1]) == 1 else "Based on the figures of each, added up.", lead)
              for level in WEAKEST_FIRST if (line := group.levels.get(level))]
    none = [f"{lead}{counted(n, 'finding')} · {why}" for why, n in sorted(group.none.items(), key=lambda item: (-item[1], item[0]))]
    return [name, found, join(saving, "<br>") if saving else "Nothing to add up.", join(none, "<br>") if none else "None."]


def _longest_wait(ctx: Ctx) -> Safe:
    """The request that has waited longest: how long, with whom it is now and what waiting has cost it so far (by code, from its own figure). Nothing when none waits or the store cannot say."""
    plans, ok = read(lambda: ctx.store.plans_open(), [])
    waiting = [p for p in plans if p.state == "open"]
    if not ok or not waiting:
        return Safe("")
    plan = min(waiting, key=lambda p: (p.created_at, p.plan_id))
    case, _ = read(lambda: ctx.store.case_get(plan.case_id), None)
    waited = brief_of(ctx, plan, case).waiting
    if waited is None:
        return Safe("")
    return paragraph(f"The request that has waited longest has waited {waited.days} day{'s' if waited.days != 1 else ''}, and it is with {waited.with_whom}. {waited.cost}".rstrip())


def savings_page(ctx: Ctx) -> Response:
    groups = [_read(ctx, *spec) for spec in GROUPS]
    changes, newest, failed, cut = _changes(ctx)
    confirmed = dict(reversed(changes))  # the newest change of a finding wins
    for group in groups:
        if group.added:
            _add(ctx, group, confirmed, newest)
    parts = [head("Savings found", LEAD), _tiles(groups, [brief.saving.monthly for _, brief in changes], failed, cut)]
    if failed or any(group.failed for group in groups):
        title = "The findings cannot be read" if all(group.dead for group in groups) else "Part of the findings cannot be read"
        parts.append(notice("error", title, "I cannot read all of them now, so some counts and figures are missing or are at least. Nothing has changed."))
    headers = ["What became of it", "Findings", "Saving a year", "Findings with no saving figure"]
    parts += [table("savings", "Savings found, by what became of each finding", headers, [_row(group) for group in groups], row_header=True), _longest_wait(ctx), paragraph(NOTE)]
    if ctx.principal.has("ops"):  # the page of every run is for that role alone
        parts.append(paragraph(link(ctx.url("/ops/runs"), "Every run and every finding")))
    return page(ctx, "Savings found", join(parts), current="/ops/savings", ai=True, why="your role ops or owner lets you see every saving that was found", wide=True)
