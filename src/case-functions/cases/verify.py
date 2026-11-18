"""A request ends when the bill shows what it suggested (docs/proposals/30-escalation.md, item 20).

No clock closes a request (AGENTS.md rule 38), so somebody who did what a request of advice suggests, and never answered it, would be reminded and passed on for ever. After the daily cost of the open
requests is read (cases/run.py read_cost_series: nothing is read twice, no model takes part and no new kind of call is made), this step holds each open request of advice against it. When what the
finding costs has gone down by at least half of the saving that the request stated, and has stayed down for two weeks, the request is taken back with the reason `verified` (cases/approvals.py
take_back_verified). Meternaut changed nothing and does not know why the cost went down: a cost can also fall for another reason, and a request that nobody answered is then closed as if somebody had acted.

The 30 closed days are cut into the four weeks that end LAG days before the newest day (the bill is one to two days late), each scaled to a month. A week with a day of nothing among days that cost something
is not whole: a day that is late or missing cannot be told from a fall, so that week says nothing. The first time that the step sees an open request with a whole daily cost it keeps what the cheapest of the
four weeks came to (`COST_AT_ASK`) and how far apart the weeks were (`COST_SPREAD`), and keeps nothing until all four are whole and cost something: not the cost of the 30 days, which a spike of a few days or
a cost that fell before the request would make wrong, and not from fewer weeks, which measure badly how far a cost moves by itself. The request is judged from the next Watch on: it is verified when each of
the two newest whole weeks costs at most that, less what it stated that it would save (half of
it for a resource, all of it for a group, whose request stands for each of its resources; never more than the cost) and less the spread, for a cost that moves by itself by more than the saving would
fall by chance (`fall`, the one place that says).

It judges only what it can hold the bill against, and says why when it could not (a typed word, once for each Watch):

* a finding with a saving of its own, a figure that code worked out from the bill (an estimate of Azure Advisor's, which no cost line backs, has nothing to be held against: brief.advisor_estimate,
  and a whole subscription or resource group moves for too many reasons);
* a daily cost that was read whole up to yesterday and in US dollars: a read that failed, was partial or was not in dollars leaves the series as it was, which ends earlier and is never used (`stale`);
* the amortized cost of a request that the actual cost shows to be down: a commitment (a reservation, a savings plan) that covers a resource makes its actual cost fall to nothing while the finding
  is still true, so the fall has to be there in the amortized cost too (which spreads a purchase over its term), and a request whose amortized cost was not read is left for the next Watch;
* the resources that the kept cost is the cost of: a request of a group whose resources are not the ones that it had when the cost was kept is not judged (`subject`);
* a resource that Resource Graph shows to be still there: one that is gone ends the request as `gone` in the step before this one, and one whose existence was not checked is left alone;
* a request that carries the warning that something which is no person changed the resource lately (`automated`, from the Activity Log): the bill cannot tell what that did from what a person did, and
  such a request is never verified.

A cost that fell in a single week, or for a few days, is no fall, and a request that a person answered in any way is theirs and stays.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
from collections import Counter
from typing import Callable, Mapping, Sequence

from . import brief
from . import costs as cost_words
from .meters import MONTH, WEEK
from .models import ADVISE, ADVISOR, AUTOMATED, COST_AT_ASK, COST_DAYS, COST_OF, COST_SPREAD, GROUP_FACT, CaseRecord, PlanRecord, members
from .roles import clean_text

LAG = 2  # the newest closed days that are left out: the bill is one to two days behind
SAID = "closed: the cost has gone down as the request suggested"  # what the History says when a request is closed
WHY = {"stale": "the daily cost was not read in full up to yesterday", "currency": "the cost lines are not in US dollars", "amortized": "the amortized cost could not be read"}  # the reasons that the History says; every other one says nothing


def _dollars(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def weeks(series: Sequence[float]) -> list[float | None]:
    """What a month costs by each whole week of the closed days, the oldest first, without the newest LAG days: a week of 7 days scaled to the 30 of a month. A week with a day of nothing among days that cost
    something is None: Cost Management has no line for a day that is late or missing, and that cannot be told from a fall. A week of nothing at all is 0: nothing was billed, as for what was stopped."""
    found: list[float | None] = []
    for n in range(0, len(series) - LAG, WEEK):
        days = series[n:n + WEEK]
        found.append(MONTH / WEEK * sum(days) if all(days) or not any(days) else None)
    return found


def baseline(series: Sequence[float]) -> tuple[float, float] | None:
    """What the cost had been: what a month costs by the cheapest of the weeks, and how far apart the weeks were (the dearest less the cheapest), or None unless every one of the four weeks is whole and cost
    something: fewer weeks measure badly how far a cost moves by itself (two weeks let a flat noisy cost pass for a fall twice as often as four). The cheapest, so that a spike does not raise it and a cost
    that already fell does not hide; the spread, so that a cost that moves by itself by more than the saving is no fall."""
    every = weeks(series)
    found = [week for week in every if week]
    return (min(found), max(found) - min(found)) if found and len(found) == len(every) else None


def subject(case: CaseRecord) -> str:
    """A short digest of the resources that the daily cost of a case is the cost of: the ids that a group names (the cost is their sum), else its own resource. A finding that is found again with other
    resources has another cost to be held against, and the baseline of the first is no baseline for it."""
    return hashlib.sha256("\n".join(sorted(members(case))).encode("utf-8")).hexdigest()[:12]


def fall(series: Sequence[float], plan: PlanRecord, case: CaseRecord) -> float | None:
    """What a month costs now by the bill (the dearer of the two newest weeks) when it is lower than the cost that was kept by more than that cost moved of itself (the spread) and by what the request
    stated that it would save: half of it for a resource, all of it for a group, whose request is one for each of its resources. A saving counts for no more than the cost (nothing saves more than it
    costs). Both weeks have to be whole and down, so a cost that fell for a few days, or only lately, or by less than it moves, is no fall. This is the one place that says."""
    kept = plan.preconditions or {}
    before, spread = _dollars(kept.get(COST_AT_ASK)) or 0.0, _dollars(kept.get(COST_SPREAD)) or 0.0
    saving = min(max(_dollars(plan.saving_usd_month) or 0.0, _dollars(case.saving_usd_month) or 0.0), before)
    older, newer = weeks(series)[-2:]
    if older is None or newer is None:
        return None
    after = max(older, newer)
    needed = saving if GROUP_FACT in (case.facts if isinstance(case.facts, dict) else {}) else saving / 2
    return after if before - after >= needed and before - after > spread else None


def judge(plan: PlanRecord, case: CaseRecord | None, last: dt.date, there: str, amortized: Sequence[float] | None = None) -> tuple[str, tuple[float, ...]]:
    """What the bill says about an open request of advice: (`verified`, (what a month costs now,)), (`baseline`, (the cost, and its spread) to keep as the cost at the request: it has none yet), or a
    word that says why it cannot be said, with no figures: `unpriced` (nothing to hold the bill against), `currency`, `unread` (no whole series), `stale` (the series does not end yesterday), `short` (the
    four weeks are not all whole and costing something yet: there is no cost to keep, and the next Watch looks again), `changed` (the resources of the finding are not the ones that the kept cost is
    of), `unchecked` (whether the resource is still there was not checked: `there` is the word of cases/escalation.py existence) or `still` (the cost has not gone down, or not for long enough).
    `last` is yesterday. `amortized` is the amortized daily cost of the same days, which a request that the actual cost shows to be down is held against again: a commitment makes the actual cost of what
    it covers fall to nothing, and that is no reason to close a request."""
    if case is None or brief.advisor_estimate(case) or not (case.saving_usd_month or 0) > 0 or cost_words.is_container(case.resource_id):
        return "unpriced", ()
    if case.cost_state == cost_words.CURRENCY:
        return "currency", ()
    series = case.cost_series if amortized is None else amortized
    if not isinstance(series, list) or len(series) != COST_DAYS or any(_dollars(day) is None for day in series):
        return "unread", ()
    if case.cost_series_end != last.isoformat():
        return "stale", ()
    kept = plan.preconditions or {}
    if _dollars(kept.get(COST_AT_ASK)) is None or _dollars(kept.get(COST_SPREAD)) is None:
        usual = baseline(series)
        return ("baseline", usual) if usual else ("short", ())
    if kept.get(COST_OF) != subject(case):
        return "changed", ()
    if there != "there":
        return "unchecked", ()
    after = fall(series, plan, case)
    return ("still", ()) if after is None else ("verified", (after,))


def step(s, there: Mapping[str, str], say: Callable[[str], None], amortized: Callable[[object, Mapping[str, CaseRecord], dt.date], Mapping[str, Sequence[float] | None]]) -> None:
    """A step of a Watch, after read_cost_series: closes the open requests of advice whose cost has gone down as they suggested (`judge`), says each in the History (`case.verified`: no amount of money),
    and keeps, for a request that has none, the cost to hold the bill against (Approvals.keep_cost: it is judged from the next Watch on, never in the one that keeps it). `there` is what
    escalation.existence said of each open request in this Watch. A request that shows a fall is held against the amortized cost as well (`amortized` reads it, for these requests only, by the
    key that it is given): the fall has to be there in both, and what the request keeps is the dearer of the two. A request that could not be judged for a reason that is said (`WHY`) is counted,
    once for each reason. It never fails the run."""
    ex = s.extras
    if ex is None:
        return
    try:
        last = s.clock().astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)
        keep: dict[str, tuple[float, float, str]] = {}
        seen: dict[str, float] = {}
        shown: dict[str, tuple[PlanRecord, CaseRecord]] = {}
        why: Counter[str] = Counter()
        for plan in ex.store.plans_open():
            kept = plan.preconditions or {}
            if plan.state != "open" or plan.family != ADVISE or kept.get("source") == ADVISOR or kept.get(AUTOMATED):
                continue  # Advisor's recommendation has no cost to be held against, and the bill cannot tell what an automation did from what a person did: their cases are not even read
            case = ex.store.case_get(plan.case_id)
            word, figures = judge(plan, case, last, there.get(plan.plan_id, ""))
            if word == "verified":
                seen[plan.plan_id], shown[plan.plan_id] = figures[0], (plan, case)  # type: ignore[assignment]
            elif word == "baseline":
                keep[plan.plan_id] = (*figures, subject(case))  # type: ignore[arg-type,assignment]
            elif word in WHY:
                why[word] += 1
        ex.approvals.keep_cost(keep)  # before the amortized cost is read: what that does never stops a cost from being kept
        series = amortized(s, {plan_id: case for plan_id, (_, case) in shown.items()}, last) if shown else {}
        for plan_id, (plan, case) in shown.items():
            if plan_id not in series:
                why["amortized"] += 1
            word, figures = judge(plan, case, last, there.get(plan_id, ""), series[plan_id]) if series.get(plan_id) else ("still", ())
            if word == "verified":
                seen[plan_id] = max(seen[plan_id], figures[0])
            else:
                del seen[plan_id]
        for plan in ex.approvals.take_back_verified(seen):
            case = shown[plan.plan_id][1]
            s.history.emit("case.verified", caseId=case.case_id, detector=case.detector, resourceType=clean_text(case.resource_type, 120), resourceName=clean_text(case.resource_name, 120), reason=SAID)
        for word, count in why.items():
            say(f"{count} request{'s' if count != 1 else ''}: whether the cost has gone down was not checked ({WHY[word]})")
    except Exception as error:  # noqa: BLE001 (this step never stops the run)
        say(f"whether the cost of the open requests has gone down could not be checked ({clean_text(s.redact(f'{type(error).__name__}: {error}'), 200)})")
