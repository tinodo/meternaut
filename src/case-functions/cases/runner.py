"""The change and the checks after it. Meternaut holds no right to change Azure: a change is made with the token of the person who approved it.

`execute` makes the change of an approved plan with the token that it is given (the approver's own token from the sign-in to Azure, see delegated.py), after it has read the resource
again, and checks it afterwards. What a change is, is the family of the plan (cases/families): the runner knows the interface and nothing of any one family. The calls that it may make
are on a list of their own (`change_calls`, built from cases/families/calls.py): the reads of the families and the writes that are listed there, in the resource groups of the change
scopes, and the status of an asynchronous operation. Azure checks the person's own rights on top of that.

Before it acts, the runner refuses unless the plan is the one that was approved (its digest: cases/families/digest.py) and a person's approval of that exact plan is recorded; the family
then re-checks the facts that the plan states, and a check that fails stops the change and says why. When Azure answers the write with a claims challenge (the person signed in without
the extra check that a change needs), nothing was changed: the action waits in the queue for that check, and `execute` is called again after it (delegated.py). A write that Azure
carries out later (a stop, a resize, a change of a disk's tier) is followed for a few seconds with the same token; when it is not finished by then the action is `running`, the person is
told so, and `tick` reads the resource later with the reader's token and settles it. A change that has no known end is `unknown`, and nothing here ever makes a second write: a retry is a
new approval by a person. An approval that found nothing to change (the resource was as the plan wants, or gone) is marked `noChange`: no write was made, and no saving is ever claimed for it.
The saving of a change that was made is confirmed later by the cost lines, from whole days only (cost_window) and asked for once a day, never from a line that is not in yet. Every step is
recorded. `tick` is the timer of the loop: it closes plans, checks what was done, and cannot change Azure (its list of calls is `read_calls`).
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Sequence

from . import switches
from .approvals import Approvals, ApprovalSettings
from .arm import Arm
from .claims import claims_challenge
from .families import digest as plan_digest
from .families import lro, registry
from .families.azure import Azure
from .families.base import Env, Family, Stop, Verdict, refusal
from .families.calls import change_patterns, read_patterns
from .families.gates import ChangeScope
from .http import Client, HttpError, Refused
from .memory_store import parse, stamp, utc_now
from .models import ActionRecord, PlanRecord, Store, StoreError

POLL_ATTEMPTS = 6
POLL_SECONDS = 5
STUCK_MINUTES = 15
QUEUED_MINUTES = 10
# The check by cost lines reads whole days only. Cost Management shows the usage of a day typically within 8 to 24 hours on Enterprise Agreement and Microsoft Customer Agreement subscriptions
# and up to 72 hours on pay-as-you-go ones, and each service emits usage at its own interval, so some lines come before others (Learn, "Understand Cost Management data"). So the day of the
# change is left out (it is part before and part after the change), and so is every day that ended less than COST_SETTLE_DAYS full days ago: the last day that is read is the day before
# yesterday or an earlier one. A pay-as-you-go subscription would need a larger number. Cost Management is asked once a day at most, until the lines are there or GIVE_UP_AFTER_DAYS are over.
COST_SETTLE_DAYS = 1
GIVE_UP_AFTER_DAYS = 7
# An approved plan whose action is still `unknown` after this many days (the app stopped between the start and the write, and the resource has not shown the change since) is closed as failed.
APPROVED_UNKNOWN_DAYS = 2
# An operation that Azure accepted and has not shown the end of, after this long, is `unknown`: the timer then goes on reading the resource, and it never makes a second write.
RUNNING_GIVE_UP_MINUTES = 60
# What the record of an action says while its change waits for the approver's extra sign-in check, when that check was asked for twice, and when it was never completed.
STEP_UP_WAIT = ("Azure asked for an extra sign-in check before it would delete the resource. Nothing was changed yet. "
                "The change waits until the approver has completed the check.")
ASKED_AGAIN = ("Azure asked for the extra sign-in check a second time, so the change was not made. Nothing was changed. "
               "Meternaut does not ask a second time. The request is closed.")
STEP_UP_ABANDONED = ("The extra sign-in check that Azure asked for was not completed in time, so the change was not made. Nothing was changed. "
                     "A new plan is made when the Watch finds the resource again.")
RUNNING_TEXT = ("Azure accepted the change and is still making it. Meternaut reads the resource again in a few minutes and records what it finds. "
                "It makes no second try: if it does not work, a new try is a new approval by a person.")
UNKNOWN_END = ("Azure accepted the change and has not shown its end. Meternaut makes no second try. Look at the resource in Azure: a new try is a new approval by a person.")
# What the record says when the cost lines gave no figure for the resource in all the days that Meternaut waited: the saving stays unconfirmed, and the change itself was checked.
COST_GAVE_UP = (f"Not confirmed: in the {GIVE_UP_AFTER_DAYS} days after the change the cost lines gave no figure for this resource to compare with, so Meternaut stopped asking. "
                "The change itself was checked.")
# What the record says of a plan that was approved, whose change never showed in the resource, and whose action stayed unknown for APPROVED_UNKNOWN_DAYS: nothing was made.
NOT_MADE_APP_STOPPED = (f"The change was not made: the app stopped before it could say, and in the {APPROVED_UNKNOWN_DAYS} days since, the resource has not shown the change. "
                        "Nothing is known to have been changed. A new plan is made when the Watch finds the resource again.")


def read_calls(scopes: Sequence[ChangeScope]) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of the reads that the checks make: each kind of resource that a family reads, in the resource groups of the change scopes, and locks and the
    quota. No write."""
    return read_patterns(scopes)


def change_calls(scopes: Sequence[ChangeScope]) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that a change makes with the approver's token: the reads, the writes of cases/families/calls.py (each on its own kind of resource,
    in the resource groups of the change scopes) and the status of an asynchronous operation. The Watch's list and the timer's list hold no write."""
    return change_patterns(scopes)


@dataclass
class RunnerServices:
    store: Store
    client: Client  # change_calls() for a change made with the approver's token, read_calls() for the timer's checks, and nothing else
    token: Callable[[str], str]  # the approver's token for a change, the reader's token for the timer's checks
    settings: ApprovalSettings
    arm: Arm | None = None  # the Watch's reader, for the cost lines that confirm a saving; None skips that check
    clock: Callable[[], dt.datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep
    emit: Callable[..., object] = lambda kind, **fields: None  # the History: one line for each step


@dataclass(frozen=True)
class Executed:
    """What `execute` did: the action as it was recorded, and what kind of end it came to: ran, ran_unconfirmed, running, unchanged, stopped, azure_refused or failed.

    The kind unchanged is an end with no write: when the runner looked, the resource was in the state that the plan wants (or gone), and the action is marked `noChange`.
    The kind running is not an end: Azure accepted the change and is still making it. The kind step_up is not an end either: Azure asked for an extra sign-in check (a claims challenge) in
    answer to the write, so nothing was changed, the action waits in the queue and the plan stays approved. `claims` is the claims request that Microsoft Entra has to be given, as compact JSON
    text. It is not a record, and it is on no page and in no log."""

    action: ActionRecord
    kind: str
    claims: str = field(default="", repr=False)


@dataclass
class TickResult:
    expired: list[PlanRecord] = field(default_factory=list)
    finished: list[ActionRecord] = field(default_factory=list)
    verified: list[ActionRecord] = field(default_factory=list)


def _env(s: RunnerServices, correlation: str = "") -> Env:
    return Env(Azure(s.client, s.token, correlation), s.settings.gates, s.store.do_not_touch)


def _finish(s: RunnerServices, action: ActionRecord, plan: PlanRecord, *, state: str, result: str, plan_state: str, case_status: str, **changes) -> ActionRecord:
    action = replace(action, state=state, result=result, finished_at=stamp(s.clock()), **changes)
    s.store.action_put(action)
    s.store.plan_put(replace(plan, state=plan_state))
    case = s.store.case_get(plan.case_id)
    if case is not None:
        s.store.case_put(replace(case, status=case_status, updated_at=stamp(s.clock())))
    return action


def _stopped(why: str) -> str:
    return f"Stopped before the change: {why}. Nothing was changed."


def execute(s: RunnerServices, action: ActionRecord, *, approved_digest: str) -> Executed:
    """Makes the change of one approved plan with the token of `s`, or stops before it. Never raises for a failed check or a failed call: the record says what happened.

    `approved_digest` is the digest of the plan that the person approved at the sign-in (delegated.py keeps it with the state of the round trip). A plan whose digest is not that one, or
    is not the one that its fields give now, is refused: nothing is changed, and the record says so."""
    plan = s.store.plan_get(action.plan_id)
    family = registry.get(plan.family) if plan is not None else None
    if plan is None or family is None:
        return _failed(s, action, None, "the plan is not there, or names a change that Meternaut does not make")
    problem = plan_digest.problem(plan, approved_digest)
    if problem:
        return _failed(s, action, plan, _stopped(problem), kind="stopped")
    decisions = [d for d in s.store.decisions_of_plan(plan.plan_id)
                 if d.decision == "approve" and d.plan_code == plan.code and d.plan_digest == plan.digest and d.approver_oid in plan.approvers]
    if plan.state != "approved" or not decisions:
        return _failed(s, action, plan, "no approval by a named approver is recorded for this exact plan")
    started = replace(action, state="running", started_at=stamp(s.clock()), result="")
    s.store.action_put(started)
    s.emit("action.started", planId=plan.plan_id, family=plan.family, correlationId=action.correlation_id)
    env = _env(s, action.correlation_id)
    try:
        located, resource = family.recheck(env, plan)
    except Stop as error:
        text = str(error) if error.kind == "azure_refused" else _stopped(str(error))
        return _failed(s, started, plan, text, kind=error.kind)
    except (HttpError, Refused, StoreError) as error:
        return _failed(s, started, plan, f"Stopped before the change: a check could not be made ({str(error)[:120]}). Nothing was changed.", kind="stopped")
    if resource is None:
        if not family.deletes:
            return _failed(s, started, plan, _stopped("the resource does not exist any more"), kind="stopped")
        done = _finish(s, started, plan, state="done", result="The resource did not exist any more when Meternaut looked. Nothing to delete.", plan_state="consumed",
                       case_status="done", verification={"gone": True, "noChange": True, "note": "already gone"})
        s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
        return Executed(done, "unchanged")
    already = family.already(plan, resource)
    if already:
        # Nothing is written: when Meternaut looked, the resource was in the state that the plan wants. `noChange` keeps it out of every later claim of a saving (see _verify and brief.py).
        done = _finish(s, started, plan, state="done", result=already, plan_state="consumed", case_status="done",
                       verification={"now": already, "noChange": True, "note": "nothing to change"})
        s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
        return Executed(done, "unchanged")
    if switches.pulled(s.store, "all", "changes"):
        return _failed(s, started, plan, "Stopped before the change: changes were paused after the approval. Nothing was changed.", kind="stopped")
    # The plan is read once more and compared with the digest that was approved, as late as it can be: nothing between here and the call can change what is made.
    latest = s.store.plan_get(plan.plan_id)
    late = plan_digest.problem(latest, approved_digest) if latest is not None else "the plan is not there any more"
    if late or latest is None or latest.state != "approved":
        return _failed(s, started, plan, _stopped(late or "the plan is not approved any more"), kind="stopped")
    try:
        response = family.write(env, plan, located)
    except HttpError as error:
        if error.status in (401, 403):
            claims = claims_challenge(error.challenge) if error.status == 401 else None
            if claims:
                return _step_up(s, started, plan, claims)
            return _failed(s, started, plan, refusal(error, family.does), kind="azure_refused")
        if error.status != 404 or not family.deletes:
            return _failed(s, started, plan, f"The {family.called} was refused or failed ({str(error)[:160]}). Check the resource before anything is tried again.",
                           unknown=error.status == 0)
        accepted = lro.Initiated(404)  # the resource was gone already: the read below says so
    except Stop as error:
        return _failed(s, started, plan, _stopped(str(error)), kind="stopped")
    except Refused as error:
        return _failed(s, started, plan, f"The app may not make this call ({str(error)[:120]}). Nothing was changed.", kind="stopped")
    else:
        accepted = lro.initiated(response)
    return _settle(s, env, family, plan, started, accepted)


def _settle(s: RunnerServices, env: Env, family: Family, plan: PlanRecord, started: ActionRecord, accepted: lro.Initiated) -> Executed:
    """Follows a change that Azure accepted, for a bounded time and with the token of the call, and records what became of it.

    Each round looks at the operation (when Azure gave an address for it, and the person may read it) and then reads the resource itself with the family's own check. The change is done
    when the read says so, failed when Azure says so, and otherwise, when the time is over, `running` (Azure is still making it) or `unknown` (it answered at once and the resource does
    not show it yet). Nothing here writes a second time."""
    if accepted.failed:
        return _failed(s, started, plan, f"Azure answered that the change did not work (its provisioning state is {accepted.provisioning}). Look at the resource in Azure before anything "
                                         "is tried again.")
    follow = accepted.asynchronous
    watching = bool(accepted.url)
    verdict = Verdict("pending", "")
    for attempt in range(POLL_ATTEMPTS):
        if watching:
            progress = lro.check(env.azure, accepted)
            if progress.state == "failed":
                return _failed(s, started, plan, f"Azure did not finish the change ({progress.text}). Look at the resource in Azure before anything is tried again.")
            watching = progress.readable
        try:
            verdict = family.verify(env, plan)
        except (Stop, HttpError, Refused):
            verdict = Verdict("unknown", "The resource could not be read.")
        if verdict.state == "done":
            s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
            done = _finish(s, started, plan, state="done", result=verdict.text, plan_state="consumed", case_status="done",
                           verification={**verdict.evidence, "checkedAt": stamp(s.clock())})
            return Executed(done, "ran")
        if verdict.state == "failed":
            return _failed(s, started, plan, f"{verdict.text} Look at the resource in Azure before anything is tried again.")
        if attempt < POLL_ATTEMPTS - 1:
            s.sleep(lro.pause(accepted) if follow else POLL_SECONDS)
    if follow:
        return _running(s, started, plan, accepted)
    text = ("Azure accepted the delete and still lists the resource. The next check will look again." if family.deletes
            else "Azure accepted the change and does not show it yet. The next check will look again.")
    unconfirmed = _finish(s, started, plan, state="unknown", result=text, plan_state="consumed", case_status="running")
    return Executed(unconfirmed, "ran_unconfirmed")


def _running(s: RunnerServices, started: ActionRecord, plan: PlanRecord, accepted: lro.Initiated) -> Executed:
    """Azure accepted the change and has not finished it: the plan is used (a plan runs once), the case is running, and the action keeps the marker that tells the timer to read the
    resource later. This is not a failure and not an end."""
    running = replace(started, state="running", result=RUNNING_TEXT, finished_at=None, operation={"pending": True, "acceptedAt": stamp(s.clock()), "via": accepted.via or "none"})
    s.store.action_put(running)
    s.store.plan_put(replace(plan, state="consumed"))
    case = s.store.case_get(plan.case_id)
    if case is not None:
        s.store.case_put(replace(case, status="running", updated_at=stamp(s.clock())))
    return Executed(running, "running")


def _step_up(s: RunnerServices, started: ActionRecord, plan: PlanRecord, claims: str) -> Executed:
    """Azure answered the write with a claims challenge: the approver has to pass an extra sign-in check first. Nothing was changed, so the plan stays approved and the action
    goes back to the queue, for the retry that follows the check (delegated.py). A challenge in answer to that retry is final: Meternaut asks for the check once."""
    if started.step_up:
        return _failed(s, started, plan, ASKED_AGAIN, kind="azure_refused")
    waiting = replace(started, state="queued", started_at=None, result=STEP_UP_WAIT, step_up=True)
    s.store.action_put(waiting)
    return Executed(waiting, "step_up", claims)


def _failed(s: RunnerServices, action: ActionRecord, plan: PlanRecord | None, text: str, unknown: bool = False, kind: str = "failed") -> Executed:
    s.emit("action.finished", planId=action.plan_id, family=action.family, ok=False)
    if plan is None:
        failed = replace(action, state="failed", result=text, finished_at=stamp(s.clock()), error=text)
        s.store.action_put(failed)
        return Executed(failed, kind)
    return Executed(_finish(s, action, plan, state="unknown" if unknown else "failed", result=text, plan_state="failed", case_status="failed", error=text), kind)


def _read_env(s: RunnerServices) -> Env:
    """The checks after a change read with the token of `s`: the timer's own, which is the reader's and has no write on its list."""
    return _env(s)


def _verdict(s: RunnerServices, family: Family, plan: PlanRecord) -> Verdict:
    try:
        return family.verify(_read_env(s), plan)
    except (Stop, HttpError, Refused):
        return Verdict("unknown", "The resource could not be read.")


def _settle_pending(s: RunnerServices, action: ActionRecord) -> ActionRecord | None:
    """Reads the resource of a change that Azure accepted and was still making, with the reader's token. Returns the action when it changed: done, failed, or unknown when the end is not
    shown after RUNNING_GIVE_UP_MINUTES. A change that is still being made is left as it is."""
    plan = s.store.plan_get(action.plan_id)
    family = registry.get(plan.family) if plan is not None else None
    if plan is None or family is None:
        return None
    now = s.clock()
    verdict = _verdict(s, family, plan)
    ended = {**action.operation, "pending": False}
    if verdict.state == "done":
        updated = replace(action, state="done", result=verdict.text.rstrip(".") + " (confirmed by the later check).", finished_at=stamp(now),
                          verification={**verdict.evidence, "checkedAt": stamp(now)}, operation=ended)
        s.store.action_put(updated)
        case = s.store.case_get(plan.case_id)
        if case is not None:
            s.store.case_put(replace(case, status="done", updated_at=stamp(now)))
        s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
        return updated
    if verdict.state == "failed":
        text = f"{verdict.text} Look at the resource in Azure before anything is tried again."
        updated = replace(action, state="failed", result=text, error=text, finished_at=stamp(now), operation=ended)
        s.store.action_put(updated)
        s.store.plan_put(replace(plan, state="failed"))
        case = s.store.case_get(plan.case_id)
        if case is not None:
            s.store.case_put(replace(case, status="failed", updated_at=stamp(now)))
        s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=False)
        return updated
    since = action.operation.get("acceptedAt") or action.started_at
    if since and now - parse(since) > dt.timedelta(minutes=RUNNING_GIVE_UP_MINUTES):
        updated = replace(action, state="unknown", result=UNKNOWN_END, finished_at=stamp(now), operation=ended)
        s.store.action_put(updated)
        return updated
    return None


def cost_window(finished: dt.datetime, now: dt.datetime) -> tuple[dt.date, dt.date] | None:
    """The whole days whose cost lines say what the change did, both days included as Cost Management asks: from the day after the change to the last day that ended at least
    COST_SETTLE_DAYS full days ago. None while there is no such day yet."""
    first = finished.date() + dt.timedelta(days=1)
    last = now.date() - dt.timedelta(days=1 + COST_SETTLE_DAYS)
    return (first, last) if last >= first else None


def _cost_check(s: RunnerServices, plan: PlanRecord, family: Family, finished: dt.datetime, now: dt.datetime, verification: dict) -> tuple[bool, bool]:
    """The step of `_verify` that asks the cost lines whether the saving is there. It writes into `verification`. Returns (the record of the check changed, the lines confirm the saving).

    It reads whole days only (cost_window) and asks once a day at most, whatever came of the ask. A resource with no line yet is "no data yet", never a cost of zero: for a change that
    leaves the resource billing (a resize, a change of tier) a missing line or a line of zero is not an answer, and for every family an answer without a single line is not one. Nothing is
    stored then, and the next day asks again, until GIVE_UP_AFTER_DAYS are over: the record then says that no figure came."""
    if "costAfterUsd" in verification or verification.get("costGaveUp"):
        return False, False
    if now - finished > dt.timedelta(days=GIVE_UP_AFTER_DAYS):
        verification.update(costGaveUp=True, note=COST_GAVE_UP)
        return True, False
    window = cost_window(finished, now)
    today = now.date().isoformat()
    if window is None or verification.get("costAskedOn") == today:
        return False, False
    first_day, last_day = window
    verification["costAskedOn"] = today
    try:
        totals, currency = s.arm.costs(plan.subscription_id, first_day, last_day)  # type: ignore[union-attr]
    except (HttpError, Refused):
        return True, False
    amount = totals.get(plan.resource_id.lower(), 0.0)
    if not totals or (not family.cost_ends and amount <= 0):
        return True, False
    after = round(amount, 2)
    case = s.store.case_get(plan.case_id)
    before = case.cost_usd_30d if case else None
    confirmed, note, saved = family.cost_check(before, after, (last_day - first_day).days + 1)
    verification.update(costAfterUsd=after, currency=currency or "USD", costLinesFrom=first_day.isoformat(), costLinesTo=last_day.isoformat(), costBeforeUsd30d=before)
    verification["note"] = note
    if saved is not None:
        verification["savedUsdMonth"] = saved
    return True, confirmed


def _verify(s: RunnerServices, action: ActionRecord) -> ActionRecord | None:
    """The check after the change: first that it took effect (the family's own read), later that the cost lines show it. Returns the action when it changed.

    An action that changed nothing (`noChange`: the resource was as the plan wants when Meternaut looked) has nothing to check, and no saving is ever booked for it."""
    plan = s.store.plan_get(action.plan_id)
    family = registry.get(plan.family) if plan is not None else None
    if plan is None or family is None or action.no_change:
        return None
    now = s.clock()
    verification = dict(action.verification)
    changed = False
    settled = bool(verification.get("gone")) if family.deletes else bool(verification.get("now"))
    if not settled:
        verdict = _verdict(s, family, plan)
        if verdict.state == "done":
            verification.update(verdict.evidence, checkedAt=stamp(now))
            settled, changed = True, True
    if settled and action.state in ("unknown", "done") and action.finished_at and s.arm is not None:
        touched, confirmed = _cost_check(s, plan, family, parse(action.finished_at), now, verification)
        changed = changed or touched
        if confirmed:
            updated = replace(action, state="verified", verified_at=stamp(now), verification=verification)
            s.store.action_put(updated)
            case = s.store.case_get(plan.case_id)
            if case is not None:
                s.store.case_put(replace(case, status="verified", updated_at=stamp(now)))
            return updated
    if changed:
        updated = replace(action, state="done" if action.state == "unknown" else action.state, verification=verification)
        if action.state == "unknown" and settled and not updated.finished_at:
            updated = replace(updated, finished_at=stamp(now))  # seen done only now: the whole days of cost lines count from here
        s.store.action_put(updated)
        if action.state == "unknown" and settled:
            s.store.plan_put(replace(plan, state="consumed"))
            case = s.store.case_get(plan.case_id)
            if case is not None and case.status in ("approved", "failed", "running"):
                s.store.case_put(replace(case, status="done", updated_at=stamp(now)))
            updated = replace(updated, result=verdict_text(family, verification, updated.result))
            s.store.action_put(updated)
        return updated
    return None


def verdict_text(family: Family, verification: dict, said: str) -> str:
    """What the action says once a later check has confirmed it: the family's own words, and that it was the later check."""
    now = verification.get("now")
    if family.deletes:
        return "Deleted. Azure no longer lists the resource (confirmed by the later check)."
    return (str(now).rstrip(".") if now else said.rstrip(".")) + " (confirmed by the later check)."


def tick(s: RunnerServices) -> TickResult:
    """What runs every minute: closes the plans that have expired and the approvals whose change never started or never showed, and checks the changes that were made.

    It makes no change: its token is the reader's and its list of calls holds no write."""
    result = TickResult()
    result.expired = Approvals(s.store, s.settings, s.clock).expire()
    now = s.clock()
    for action in s.store.actions_recent(50):
        if action.state == "queued" and parse(action.queued_at) < now - dt.timedelta(minutes=QUEUED_MINUTES):
            plan = s.store.plan_get(action.plan_id)
            text = STEP_UP_ABANDONED if action.step_up else (
                "The change did not start: the request that was to make it ended first, for example at a restart. Nothing was changed. "
                "A new plan is made when the Watch finds the resource again.")
            result.finished.append(_failed(s, action, plan, text).action)
            continue
        if action.state == "running" and action.operation.get("pending"):
            settled = _settle_pending(s, action)
            if settled is not None:
                result.finished.append(settled)
            continue
        if action.state == "running" and action.started_at and now - parse(action.started_at) > dt.timedelta(minutes=STUCK_MINUTES):
            stuck = replace(action, state="unknown", result="The change stopped in the middle of the request that was making it. The next check looks at the resource.")
            s.store.action_put(stuck)
            action = stuck
        if action.state in ("done", "unknown") and not action.verified_at:
            check = action.verification
            if action.no_change or check.get("costGaveUp"):
                continue  # nothing to check afterwards, or the days of waiting for cost lines are used up (the record says so)
            if action.finished_at and now - parse(action.finished_at) > dt.timedelta(days=GIVE_UP_AFTER_DAYS) and "costAfterUsd" in check:
                continue
            changed = _verify(s, action)
            if changed is not None and changed.state == "verified":
                result.verified.append(changed)
                s.emit("action.verified", planId=changed.plan_id, family=changed.family)
            closed = _close_unmade(s, changed or action, now)
            if closed is not None:
                result.finished.append(closed)
    return result


def _close_unmade(s: RunnerServices, action: ActionRecord, now: dt.datetime) -> ActionRecord | None:
    """Closes an approved plan whose change never showed: the app stopped after the action began and before it could write or say (a restart), the action became `unknown`, and for
    APPROVED_UNKNOWN_DAYS the resource has not shown the change in the reads of `_verify`. Without this the plan stays `approved` for ever, and "a plan for this resource is open
    already" holds the resource for good. The plan, the action and the case close as failed, through the same transition as every other failure. Returns the closed action, or None."""
    if action.state != "unknown":
        return None
    since = action.started_at or action.queued_at
    if not since or now - parse(since) <= dt.timedelta(days=APPROVED_UNKNOWN_DAYS):
        return None
    plan = s.store.plan_get(action.plan_id)
    if plan is None or plan.state != "approved":
        return None
    return _failed(s, action, plan, NOT_MADE_APP_STOPPED).action
