"""A request ends when the bill shows what it suggested (docs/proposals/30-escalation.md, item 20).

No clock closes a request (AGENTS.md rule 38), so somebody who did what a request of advice suggests, and never answered it, would be reminded and passed on for ever. After the daily cost of the open
requests is read (cases/run.py read_cost_series: nothing is read twice, no model takes part and no new kind of call is made), this step holds each open request of advice against it. When what the
finding costs has gone down by at least half of the saving that the request stated, and has stayed down for two weeks, the request is taken back with the reason `verified` (cases/approvals.py
take_back_verified). Meternaut changed nothing and does not know why the cost went down: a cost can also fall for another reason, and a request that nobody answered is then closed as if somebody had acted.

The 30 closed days are cut into the four whole weeks that end LAG days before the newest day (the bill is one to two days late), each scaled to a month. The first time that the step sees an open request with
a whole daily cost it keeps what the cheapest of those weeks that cost anything came to (`COST_AT_ASK`): not the cost of the 30 days, which a spike of a few days or a cost that fell before the request
would make wrong. The request is judged from the next Watch on: it is verified when each of the two newest weeks costs at most that, less half of the saving (the saving is never more than the cost).

It judges only what it can hold the bill against, and says why when it could not (a typed word, once for each Watch):

* a finding with a saving of its own, a figure that code worked out from the bill (Azure Advisor's own figure has no cost to be held against, and a whole subscription or resource group moves for
  too many reasons);
* a daily cost that was read whole up to yesterday and in US dollars: a read that failed, was partial or was not in dollars leaves the series as it was, which ends earlier and is never used (`stale`);
* a resource that Resource Graph shows to be still there: one that is gone ends the request as `gone` in the step before this one, and one whose existence was not checked is left alone.

A cost that fell in a single week, or for a few days, is no fall, and a request that a person answered in any way is theirs and stays.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from typing import Callable, Mapping, Sequence

from . import costs as cost_words
from .detectors import ADVISOR
from .meters import MONTH, WEEK
from .models import ADVISE, COST_AT_ASK, CaseRecord, PlanRecord
from .roles import clean_text

LAG = 2  # the newest closed days that are left out: the bill is one to two days behind
SAID = "closed: the cost has gone down as the request suggested"  # what the History says when a request is closed
WHY = {"stale": "the daily cost was not read in full up to yesterday", "currency": "the cost lines are not in US dollars"}  # the reasons that the History says; every other one says nothing


def _dollars(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def weeks(series: Sequence[float]) -> list[float]:
    """What a month costs by each whole week of the closed days, the oldest first, without the newest LAG days: a week of 7 days scaled to the 30 of a month."""
    return [MONTH / WEEK * sum(series[n:n + WEEK]) for n in range(0, len(series) - LAG, WEEK)]


def cheapest(series: Sequence[float]) -> float:
    """What a month costs by the cheapest of those weeks that cost anything, 0 when none did: the lowest that the cost had been, so a spike does not raise it and a cost that already fell does not hide."""
    return min((week for week in weeks(series) if week > 0), default=0.0)


def fall(series: Sequence[float], before: float, saving: float) -> float | None:
    """What a month costs now by the bill, when each of the two newest weeks costs at most `before` less half of `saving`, else None. The saving counts for no more than `before` (nothing saves more than
    it costs). Both weeks have to be down, so a cost that fell by less, or for a few days, or only lately, is no fall. Returns the dearer of the two weeks: what the verdict rests on."""
    older, newer = weeks(series)[-2:]
    return max(older, newer) if max(older, newer) <= before - min(saving, before) / 2 else None


def judge(plan: PlanRecord, case: CaseRecord | None, last: dt.date, there: str) -> tuple[str, float]:
    """What the bill says about an open request of advice: (`verified`, what a month costs now), (`baseline`, the cost to keep as the cost at the request: it has none yet), or a word that says why it
    cannot be said: `unpriced` (nothing to hold the bill against), `currency`, `unread` (no whole series), `stale` (the series does not end yesterday), `unchecked` (whether the resource is still
    there was not checked: `there` is the word of cases/escalation.py existence), or `still` (the cost has not gone down, or not for long enough). The second number is 0 for those. `last` is yesterday."""
    if case is None or case.detector == ADVISOR or not (case.saving_usd_month or 0) > 0 or cost_words.is_container(case.resource_id):
        return "unpriced", 0.0
    if case.cost_state == cost_words.CURRENCY:
        return "currency", 0.0
    series = case.cost_series
    if not isinstance(series, list) or len(series) != MONTH or any(_dollars(day) is None for day in series):
        return "unread", 0.0
    if case.cost_series_end != last.isoformat():
        return "stale", 0.0
    before = _dollars((plan.preconditions or {}).get(COST_AT_ASK))
    if before is None:
        usual = cheapest(series)
        return ("baseline", usual) if usual > 0 else ("unpriced", 0.0)
    if there != "there":
        return "unchecked", 0.0
    after = fall(series, before, max(_dollars(plan.saving_usd_month) or 0.0, _dollars(case.saving_usd_month) or 0.0))
    return ("still", 0.0) if after is None else ("verified", after)


def step(s, there: Mapping[str, str], say: Callable[[str], None]) -> None:
    """A step of a Watch, after read_cost_series: closes the open requests of advice whose cost has gone down as they suggested (`judge`), says each in the History (`case.verified`: no amount of money),
    and keeps, for a request that has none, the cost to hold the bill against (Approvals.keep_cost: it is judged from the next Watch on, never in the one that keeps it). `there` is what
    escalation.existence said of each open request in this Watch. A request that could not be judged for a reason that is said (`WHY`) is counted, once for each reason. It never fails the run."""
    ex = s.extras
    if ex is None:
        return
    try:
        last = s.clock().astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)
        keep: dict[str, float] = {}
        seen: dict[str, float] = {}
        cases: dict[str, CaseRecord] = {}
        why: Counter[str] = Counter()
        for plan in ex.store.plans_open():
            if plan.state != "open" or plan.family != ADVISE:
                continue
            case = ex.store.case_get(plan.case_id)
            word, figure = judge(plan, case, last, there.get(plan.plan_id, ""))
            if word == "verified":
                seen[plan.plan_id], cases[plan.plan_id] = figure, case  # type: ignore[assignment]
            elif word == "baseline":
                keep[plan.plan_id] = figure
            elif word in WHY:
                why[word] += 1
        ex.approvals.keep_cost(keep)
        for plan in ex.approvals.take_back_verified(seen):
            case = cases[plan.plan_id]
            s.history.emit("case.verified", caseId=case.case_id, detector=case.detector, resourceType=clean_text(case.resource_type, 120), resourceName=clean_text(case.resource_name, 120), reason=SAID)
        for word, count in why.items():
            say(f"{count} request{'s' if count != 1 else ''}: whether the cost has gone down was not checked ({WHY[word]})")
    except Exception as error:  # noqa: BLE001 (this step never stops the run)
        say(f"whether the cost of the open requests has gone down could not be checked ({clean_text(s.redact(f'{type(error).__name__}: {error}'), 200)})")
