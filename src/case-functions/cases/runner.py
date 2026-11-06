"""The change and the checks after it. Meternaut holds no right to change Azure: a change is made with the token of the person who approved it.

`execute` makes the change of an approved plan with the token that it is given (the approver's own token from the sign-in to Azure, see delegated.py), after
it has read the resource again, and checks it afterwards. The calls that it may make are on a list of their own (`change_calls`): a read and a delete of a disk
and of a public IP address in one resource group, and a read of locks. Azure checks the person's own rights on top of that. Before it deletes it re-checks the
facts that the plan states, and a check that fails stops the change and says why. When Azure answers the delete with a claims challenge (the person signed in without the
extra check that a change needs), nothing was deleted: the action waits in the queue for that check, and `execute` is called again after it (delegated.py). Every step is
recorded. `tick` is the timer of the loop: it closes plans, checks what was done, and cannot change Azure (its list of calls is `read_calls`).
"""
from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import dataclass, field, replace
from typing import Callable

from . import switches
from .approvals import Approvals, ApprovalSettings
from .arm import Arm
from .claims import claims_challenge
from .http import Client, HttpError, Refused
from .memory_store import parse, stamp, utc_now
from .models import ActionRecord, PlanRecord, Store, StoreError

ARM_HOST = "management.azure.com"
ARM_RESOURCE = "https://management.azure.com/"
LOCKS_API = "2016-09-01"
# provider, collection, API version, the kind of resource in words
KINDS = {
    "delete-disk": ("Microsoft.Compute", "disks", "2024-03-02", "disk"),
    "delete-public-ip": ("Microsoft.Network", "publicIPAddresses", "2024-05-01", "public IP address"),
}
NAME = r"[A-Za-z0-9_.-]{1,80}"
POLL_ATTEMPTS = 6
POLL_SECONDS = 5
STUCK_MINUTES = 15
QUEUED_MINUTES = 10
VERIFY_AFTER_DAYS = 2
GIVE_UP_AFTER_DAYS = 7
# What the record of an action says while its change waits for the approver's extra sign-in check, when that check was asked for twice, and when it was never completed.
STEP_UP_WAIT = ("Azure asked for an extra sign-in check before it would delete the resource. Nothing was changed yet. "
                "The change waits until the approver has completed the check.")
ASKED_AGAIN = ("Azure asked for the extra sign-in check a second time, so the change was not made. Nothing was changed. "
               "Meternaut does not ask a second time. The request is closed.")
STEP_UP_ABANDONED = ("The extra sign-in check that Azure asked for was not completed in time, so the change was not made. Nothing was changed. "
                     "A new plan is made when the Watch finds the resource again.")


def _patterns(subscription: str, group: str) -> tuple["re.Pattern[str]", "re.Pattern[str]", "re.Pattern[str]"]:
    host = re.escape(f"https://{ARM_HOST}")
    base = host + re.escape(f"/subscriptions/{subscription}/resourceGroups/{group}")
    scopes = (host + re.escape(f"/subscriptions/{subscription}") + rf"(?:/resourceGroups/{re.escape(group)}"
              rf"(?:/providers/[A-Za-z0-9.]{{1,80}}/[A-Za-z0-9]{{1,40}}/{NAME})?)?")
    disks = re.compile(base + rf"/providers/Microsoft\.Compute/disks/{NAME}", re.I)
    addresses = re.compile(base + rf"/providers/Microsoft\.Network/publicIPAddresses/{NAME}", re.I)
    return disks, addresses, re.compile(scopes + r"/providers/Microsoft\.Authorization/locks", re.I)


def read_calls(subscription: str, group: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of the reads that the checks make: a disk and a public IP address in one group, and locks. No write."""
    disks, addresses, locks = _patterns(subscription, group)
    return (("GET", disks), ("GET", addresses), ("GET", locks))


def change_calls(subscription: str, group: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that a change makes with the approver's token: the reads, and a delete of a disk and of a public IP
    address in one group. The Watch's list and the timer's list hold no write."""
    disks, addresses, locks = _patterns(subscription, group)
    return (
        ("GET", disks), ("DELETE", disks),
        ("GET", addresses), ("DELETE", addresses),
        ("GET", locks),
    )


@dataclass
class RunnerServices:
    store: Store
    client: Client  # change_calls() for a change made with the approver's token, read_calls() for the timer's checks, and nothing else
    token: Callable[[str], str]  # the approver's token for a change, the reader's token for the timer's checks
    settings: ApprovalSettings
    subscription: str
    arm: Arm | None = None  # the Watch's reader, for the cost lines that confirm a saving; None skips that check
    clock: Callable[[], dt.datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep
    emit: Callable[..., object] = lambda kind, **fields: None  # the History: one line for each step


@dataclass(frozen=True)
class Executed:
    """What `execute` did: the action as it was recorded, and what kind of end it came to: ran, ran_unconfirmed, stopped, azure_refused or failed.

    The kind step_up is not an end: Azure asked for an extra sign-in check (a claims challenge) in answer to the delete, so nothing was deleted, the action waits in the queue and
    the plan stays approved. `claims` is the claims request that Microsoft Entra has to be given, as compact JSON text. It is not a record, and it is on no page and in no log."""

    action: ActionRecord
    kind: str
    claims: str = field(default="", repr=False)


@dataclass
class TickResult:
    expired: list[PlanRecord] = field(default_factory=list)
    finished: list[ActionRecord] = field(default_factory=list)
    verified: list[ActionRecord] = field(default_factory=list)


class Stop(Exception):
    """A check that fails before the change: the text says which, and nothing has been changed."""

    def __init__(self, message: str, kind: str = "stopped") -> None:
        super().__init__(message)
        self.kind = kind


def _headers(s: RunnerServices) -> dict[str, str]:
    return {"Authorization": f"Bearer {s.token(ARM_RESOURCE)}"}


def _refusal(error: HttpError, what: str) -> str:
    """The plain words for an answer of Azure that says that the person may not do this, with the error's name."""
    named = re.search(r": \d{3} ([A-Za-z]{4,60})", str(error))
    return (f"Azure refused to {what} ({error.status}{', ' + named.group(1) if named else ''}): your account has no right to do this here. "
            "Nothing was changed.")


def _resource_url(plan: PlanRecord, s: RunnerServices) -> str:
    provider, collection, api, _ = KINDS[plan.family]
    name = plan.resource_id.rstrip("/").rsplit("/", 1)[-1]
    return (f"https://{ARM_HOST}/subscriptions/{s.subscription}/resourceGroups/{s.settings.change_group}/providers/{provider}/{collection}/{name}"
            f"?api-version={api}")


def _same(plan: PlanRecord, s: RunnerServices) -> None:
    """The plan names a resource that a change may be made on: this family, this subscription, this group, and the id that the plan was made for."""
    provider, collection, _, _ = KINDS[plan.family]
    expected = (f"/subscriptions/{s.subscription}/resourceGroups/{s.settings.change_group}/providers/{provider}/{collection}/").lower()
    rid = plan.resource_id.lower()
    if not rid.startswith(expected) or not re.fullmatch(NAME, plan.resource_id.rsplit("/", 1)[-1]):
        raise Stop("the plan names a resource that is not in the one resource group, subscription and kind that a change may be made on")
    if plan.preconditions.get("family") != plan.family or plan.preconditions.get("resourceGroup", "").lower() != s.settings.change_group.lower():
        raise Stop("the plan's own preconditions do not match what a change may be")


def _locked(plan: PlanRecord, s: RunnerServices) -> bool:
    for scope in (plan.resource_id, f"/subscriptions/{s.subscription}/resourceGroups/{s.settings.change_group}"):
        url = f"https://{ARM_HOST}{scope}/providers/Microsoft.Authorization/locks?api-version={LOCKS_API}"
        try:
            data = s.client.request("GET", url, headers=_headers(s), timeout=30).json()
        except HttpError as error:
            if error.status in (401, 403):
                raise Stop(_refusal(error, "read the locks"), "azure_refused") from error
            raise
        if not isinstance(data, dict) or not isinstance(data.get("value", []), list):
            raise Stop("the locks could not be read, and an unread guard counts as on")
        if data.get("value"):
            return True
    return False


def _recheck(plan: PlanRecord, s: RunnerServices) -> dict | None:
    """Reads the resource again and checks everything the plan states. Returns the resource, or None when it is gone already. Raises Stop when a check fails."""
    _same(plan, s)
    try:
        resource = s.client.request("GET", _resource_url(plan, s), headers=_headers(s), timeout=30).json()
    except HttpError as error:
        if error.status == 404:
            return None
        if error.status in (401, 403):
            raise Stop(_refusal(error, "read the resource"), "azure_refused") from error
        raise Stop(f"the resource could not be read ({error.status or 'no answer'})") from error
    if not isinstance(resource, dict) or str(resource.get("id", "")).lower() != plan.resource_id.lower():
        raise Stop("Azure answered with another resource than the one in the plan")
    tags = {str(k).lower(): str(v) for k, v in (resource.get("tags") or {}).items()} if isinstance(resource.get("tags"), dict) else {}
    tag = str(plan.preconditions.get("tag", "")).lower()
    if not tag or not tags.get(tag, "").strip():
        raise Stop(f"the resource does not carry the {plan.preconditions.get('tag')} tag any more")
    properties = resource.get("properties") if isinstance(resource.get("properties"), dict) else {}
    if plan.family == "delete-disk":
        if str(properties.get("diskState", "")).lower() != "unattached" or resource.get("managedBy"):
            raise Stop("the disk is not unattached any more")
    elif properties.get("ipConfiguration") or properties.get("natGateway") or properties.get("linkedPublicIPAddress"):
        raise Stop("the public IP address is not unassigned any more")
    if str(plan.resource_id).lower() in s.store.do_not_touch():
        raise Stop("a person marked the resource do-not-touch after the plan was made")
    if _locked(plan, s):
        raise Stop("the resource or its resource group has a management lock")
    return resource


def _gone(plan: PlanRecord, s: RunnerServices) -> bool | None:
    """True when Azure says the resource does not exist; False when it exists; None when that could not be told."""
    try:
        s.client.request("GET", _resource_url(plan, s), headers=_headers(s), timeout=30)
    except HttpError as error:
        return True if error.status == 404 else None
    return False


def _finish(s: RunnerServices, action: ActionRecord, plan: PlanRecord, *, state: str, result: str, plan_state: str, case_status: str, **changes) -> ActionRecord:
    action = replace(action, state=state, result=result, finished_at=stamp(s.clock()), **changes)
    s.store.action_put(action)
    s.store.plan_put(replace(plan, state=plan_state))
    case = s.store.case_get(plan.case_id)
    if case is not None:
        s.store.case_put(replace(case, status=case_status, updated_at=stamp(s.clock())))
    return action


def execute(s: RunnerServices, action: ActionRecord) -> Executed:
    """Makes the change of one approved plan with the token of `s`, or stops before it. Never raises for a failed check or a failed call: the record says what happened."""
    plan = s.store.plan_get(action.plan_id)
    if plan is None or plan.family not in KINDS:
        return _failed(s, action, None, "the plan is not there, or names a change that Meternaut does not make")
    decisions = [d for d in s.store.decisions_of_plan(plan.plan_id) if d.decision == "approve" and d.plan_code == plan.code and d.approver_oid in plan.approvers]
    if plan.state != "approved" or not decisions:
        return _failed(s, action, plan, "no approval by a named approver is recorded for this exact plan")
    started = replace(action, state="running", started_at=stamp(s.clock()), result="")
    s.store.action_put(started)
    s.emit("action.started", planId=plan.plan_id, family=plan.family, correlationId=action.correlation_id)
    try:
        resource = _recheck(plan, s)
    except Stop as error:
        text = str(error) if error.kind == "azure_refused" else f"Stopped before the change: {error}. Nothing was changed."
        return _failed(s, started, plan, text, kind=error.kind)
    except (HttpError, Refused, StoreError) as error:
        return _failed(s, started, plan, f"Stopped before the change: a check could not be made ({str(error)[:120]}). Nothing was changed.", kind="stopped")
    if resource is None:
        done = _finish(s, started, plan, state="done", result="The resource did not exist any more when Meternaut looked. Nothing to delete.", plan_state="consumed",
                       case_status="done", verification={"gone": True, "note": "already gone"})
        s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
        return Executed(done, "ran")
    if switches.pulled(s.store, "all", "changes"):
        return _failed(s, started, plan, "Stopped before the change: changes were paused after the approval. Nothing was changed.", kind="stopped")
    try:
        s.client.request("DELETE", _resource_url(plan, s), headers={**_headers(s), "x-ms-correlation-request-id": action.correlation_id or "none"}, timeout=60,
                         retries=0, retry_network=False)
    except HttpError as error:
        if error.status in (401, 403):
            claims = claims_challenge(error.challenge) if error.status == 401 else None
            if claims:
                return _step_up(s, started, plan, claims)
            return _failed(s, started, plan, _refusal(error, "delete the resource"), kind="azure_refused")
        if error.status != 404:
            return _failed(s, started, plan, f"The delete was refused or failed ({str(error)[:160]}). Check the resource before anything is tried again.",
                           unknown=error.status == 0)
    for attempt in range(POLL_ATTEMPTS):
        state = _gone(plan, s)
        if state:
            s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
            done = _finish(s, started, plan, state="done", result="Deleted. Azure no longer lists the resource.", plan_state="consumed", case_status="done",
                           verification={"gone": True, "checkedAt": stamp(s.clock())})
            return Executed(done, "ran")
        if attempt < POLL_ATTEMPTS - 1:
            s.sleep(POLL_SECONDS)
    unconfirmed = _finish(s, started, plan, state="unknown", result="Azure accepted the delete and still lists the resource. The next check will look again.",
                          plan_state="consumed", case_status="running")
    return Executed(unconfirmed, "ran_unconfirmed")


def _step_up(s: RunnerServices, started: ActionRecord, plan: PlanRecord, claims: str) -> Executed:
    """Azure answered the delete with a claims challenge: the approver has to pass an extra sign-in check first. Nothing was deleted, so the plan stays approved and the action
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


def _verify(s: RunnerServices, action: ActionRecord) -> ActionRecord | None:
    """The check after the change: first that the resource is gone, later that the cost lines stopped. Returns the action when it changed."""
    plan = s.store.plan_get(action.plan_id)
    if plan is None or plan.family not in KINDS:
        return None
    now = s.clock()
    verification = dict(action.verification)
    changed = False
    if not verification.get("gone"):
        if _gone(plan, s):
            verification.update(gone=True, checkedAt=stamp(now))
            changed = True
    if verification.get("gone") and action.state in ("unknown", "done") and action.finished_at:
        finished = parse(action.finished_at)
        if s.arm is not None and now - finished >= dt.timedelta(days=VERIFY_AFTER_DAYS) and "costAfterUsd" not in verification:
            first_day = finished.date() + dt.timedelta(days=1)
            try:
                totals, currency = s.arm.costs(s.subscription, first_day, now.date())
            except (HttpError, Refused):
                totals, currency = None, None
            if totals is not None:
                after = round(totals.get(plan.resource_id.lower(), 0.0), 2)
                case = s.store.case_get(plan.case_id)
                verification.update(costAfterUsd=after, currency=currency or "USD", costLinesFrom=first_day.isoformat(),
                                    costBeforeUsd30d=case.cost_usd_30d if case else None)
                verification["note"] = ("Confirmed: no cost lines for this resource after the day of the change." if after == 0
                                        else f"Not confirmed: cost lines of {after} still exist after the day of the change.")
                changed = True
                if after == 0:
                    updated = replace(action, state="verified", verified_at=stamp(now), verification=verification)
                    s.store.action_put(updated)
                    case = s.store.case_get(plan.case_id)
                    if case is not None:
                        s.store.case_put(replace(case, status="verified", updated_at=stamp(now)))
                    return updated
    if changed:
        updated = replace(action, state="done" if action.state == "unknown" else action.state, verification=verification)
        s.store.action_put(updated)
        if action.state == "unknown" and verification.get("gone"):
            s.store.plan_put(replace(plan, state="consumed"))
            case = s.store.case_get(plan.case_id)
            if case is not None and case.status in ("failed", "running"):
                s.store.case_put(replace(case, status="done", updated_at=stamp(now)))
            updated = replace(updated, result="Deleted. Azure no longer lists the resource (confirmed by the later check).")
            s.store.action_put(updated)
        return updated
    return None


def tick(s: RunnerServices) -> TickResult:
    """What runs every minute: closes the plans that have expired and the approvals whose change never started, and checks the changes that were made.

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
        if action.state == "running" and action.started_at and now - parse(action.started_at) > dt.timedelta(minutes=STUCK_MINUTES):
            stuck = replace(action, state="unknown", result="The change stopped in the middle of the request that was making it. The next check looks at the resource.")
            s.store.action_put(stuck)
            action = stuck
        if action.state in ("done", "unknown") and not action.verified_at:
            if action.finished_at and now - parse(action.finished_at) > dt.timedelta(days=GIVE_UP_AFTER_DAYS) and "costAfterUsd" in action.verification:
                continue
            changed = _verify(s, action)
            if changed is not None and changed.state == "verified":
                result.verified.append(changed)
                s.emit("action.verified", planId=changed.plan_id, family=changed.family)
    return result
