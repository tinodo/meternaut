"""The runner: the one component that changes Azure. It makes the change of an approved plan, after it has read the resource again, and checks it afterwards.

It has its own identity, whose one custom role can read and delete a disk and a public IP address in one resource group and read locks, and its own
list of calls (`runner_calls`): the Watch's list holds no write, and this one holds a delete for those two kinds of resource in that one group and nothing
else. Before it deletes it re-checks the facts that the plan states, and a check that fails stops the change and says why. Every step is recorded.
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
POLL_SECONDS = 10
STUCK_MINUTES = 15
VERIFY_AFTER_DAYS = 2
GIVE_UP_AFTER_DAYS = 7
MAX_PER_TICK = 3


def runner_calls(subscription: str, group: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that the runner makes: reads and deletes of a disk and a public IP address in one group, and locks."""
    host = re.escape(f"https://{ARM_HOST}")
    base = host + re.escape(f"/subscriptions/{subscription}/resourceGroups/{group}")
    scopes = (host + re.escape(f"/subscriptions/{subscription}") + rf"(?:/resourceGroups/{re.escape(group)}"
              rf"(?:/providers/[A-Za-z0-9.]{{1,80}}/[A-Za-z0-9]{{1,40}}/{NAME})?)?")
    disks = re.compile(base + rf"/providers/Microsoft\.Compute/disks/{NAME}", re.I)
    addresses = re.compile(base + rf"/providers/Microsoft\.Network/publicIPAddresses/{NAME}", re.I)
    return (
        ("GET", disks), ("DELETE", disks),
        ("GET", addresses), ("DELETE", addresses),
        ("GET", re.compile(scopes + r"/providers/Microsoft\.Authorization/locks", re.I)),
    )


@dataclass
class RunnerServices:
    store: Store
    client: Client  # the runner's own client: runner_calls() and nothing else
    token: Callable[[str], str]  # the token of the writer's identity
    settings: ApprovalSettings
    subscription: str
    arm: Arm | None = None  # the Watch's reader, for the cost lines that confirm a saving; None skips that check
    clock: Callable[[], dt.datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep
    emit: Callable[..., object] = lambda kind, **fields: None  # the History: one line for each step


@dataclass
class TickResult:
    expired: list[PlanRecord] = field(default_factory=list)
    finished: list[ActionRecord] = field(default_factory=list)
    verified: list[ActionRecord] = field(default_factory=list)


class Stop(Exception):
    """A check that fails before the change: the text says which, and nothing has been changed."""


def _headers(s: RunnerServices) -> dict[str, str]:
    return {"Authorization": f"Bearer {s.token(ARM_RESOURCE)}"}


def _resource_url(plan: PlanRecord, s: RunnerServices) -> str:
    provider, collection, api, _ = KINDS[plan.family]
    name = plan.resource_id.rstrip("/").rsplit("/", 1)[-1]
    return (f"https://{ARM_HOST}/subscriptions/{s.subscription}/resourceGroups/{s.settings.writer_group}/providers/{provider}/{collection}/{name}"
            f"?api-version={api}")


def _same(plan: PlanRecord, s: RunnerServices) -> None:
    """The plan names a resource that this runner may act on: this family, this subscription, this group, and the id that the plan was made for."""
    provider, collection, _, _ = KINDS[plan.family]
    expected = (f"/subscriptions/{s.subscription}/resourceGroups/{s.settings.writer_group}/providers/{provider}/{collection}/").lower()
    rid = plan.resource_id.lower()
    if not rid.startswith(expected) or not re.fullmatch(NAME, plan.resource_id.rsplit("/", 1)[-1]):
        raise Stop("the plan names a resource that is not in the one resource group, subscription and kind that the writer may act on")
    if plan.preconditions.get("family") != plan.family or plan.preconditions.get("resourceGroup", "").lower() != s.settings.writer_group.lower():
        raise Stop("the plan's own preconditions do not match what the writer may do")


def _locked(plan: PlanRecord, s: RunnerServices) -> bool:
    for scope in (plan.resource_id, f"/subscriptions/{s.subscription}/resourceGroups/{s.settings.writer_group}"):
        url = f"https://{ARM_HOST}{scope}/providers/Microsoft.Authorization/locks?api-version={LOCKS_API}"
        data = s.client.request("GET", url, headers=_headers(s), timeout=30).json()
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


def execute(s: RunnerServices, action: ActionRecord) -> ActionRecord:
    """Makes the change of one approved plan, or stops before it. Never raises for a failed check or a failed call: the record says what happened."""
    plan = s.store.plan_get(action.plan_id)
    if plan is None or plan.family not in KINDS:
        return _failed(s, action, None, "the plan is not there, or names an action that the writer does not have")
    if plan.state == "withdrawn":
        done = replace(action, state="withdrawn", result="Withdrawn before it started. Nothing changed.", finished_at=stamp(s.clock()))
        s.store.action_put(done)
        return done
    decisions = [d for d in s.store.decisions_of_plan(plan.plan_id) if d.decision == "approve" and d.plan_code == plan.code and d.approver_oid in plan.approvers]
    if plan.state != "approved" or not decisions:
        return _failed(s, action, plan, "no approval by a named approver is recorded for this exact plan")
    started = replace(action, state="running", started_at=stamp(s.clock()))
    s.store.action_put(started)
    s.emit("action.started", planId=plan.plan_id, family=plan.family, correlationId=action.correlation_id)
    try:
        resource = _recheck(plan, s)
    except Stop as error:
        return _failed(s, started, plan, f"Stopped before the change: {error}. Nothing was changed.")
    except (HttpError, Refused, StoreError) as error:
        return _failed(s, started, plan, f"Stopped before the change: a check could not be made ({str(error)[:120]}). Nothing was changed.")
    if resource is None:
        return _finish(s, started, plan, state="done", result="The resource did not exist any more when the writer looked. Nothing to delete.", plan_state="consumed",
                       case_status="done", verification={"gone": True, "note": "already gone"})
    try:
        s.client.request("DELETE", _resource_url(plan, s), headers={**_headers(s), "x-ms-correlation-request-id": action.correlation_id or "none"}, timeout=60)
    except HttpError as error:
        if error.status != 404:
            return _failed(s, started, plan, f"The delete was refused or failed ({str(error)[:160]}). Check the resource before anything is tried again.", unknown=error.status == 0)
    for attempt in range(POLL_ATTEMPTS):
        state = _gone(plan, s)
        if state:
            s.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=True)
            return _finish(s, started, plan, state="done", result="Deleted. Azure no longer lists the resource.", plan_state="consumed", case_status="done",
                           verification={"gone": True, "checkedAt": stamp(s.clock())})
        if attempt < POLL_ATTEMPTS - 1:
            s.sleep(POLL_SECONDS)
    return _finish(s, started, plan, state="unknown", result="Azure accepted the delete and still lists the resource. The next check will look again.",
                   plan_state="consumed", case_status="running")


def _failed(s: RunnerServices, action: ActionRecord, plan: PlanRecord | None, text: str, unknown: bool = False) -> ActionRecord:
    s.emit("action.finished", planId=action.plan_id, family=action.family, ok=False)
    if plan is None:
        failed = replace(action, state="failed", result=text, finished_at=stamp(s.clock()), error=text)
        s.store.action_put(failed)
        return failed
    return _finish(s, action, plan, state="unknown" if unknown else "failed", result=text, plan_state="failed", case_status="failed", error=text)


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
    """What runs every minute: closes the plans that have expired, makes the changes whose start time has come, and checks the changes that were made."""
    result = TickResult()
    result.expired = Approvals(s.store, s.settings, s.clock).expire()
    now = s.clock()
    if not switches.pulled(s.store, "all", "changes"):
        queued = [a for a in s.store.actions_recent(50) if a.state == "queued" and a.start_after and parse(a.start_after) <= now]
        for action in sorted(queued, key=lambda a: a.queued_at)[:MAX_PER_TICK]:
            result.finished.append(execute(s, action))
    for action in s.store.actions_recent(50):
        if action.state == "running" and action.started_at and now - parse(action.started_at) > dt.timedelta(minutes=STUCK_MINUTES):
            stuck = replace(action, state="unknown", result="The writer stopped in the middle of this change. The next check looks at the resource.")
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
