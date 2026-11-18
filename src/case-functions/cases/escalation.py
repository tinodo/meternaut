"""The escalation of a request that waits: a request that nobody answers is never closed by a clock and never forgotten (AGENTS.md rule 38).

A request waits as long as it is open. Its ladder is a row of steps, each made once (`Store.escalation_claim`): step 1 a reminder to the people that it was made for, step 2 the next person (the
manager that the directory names, an escalation tag, the escalation contacts, or the owners: cases/directory.py), step 3 the next level, step 4 the escalation contacts, and then, every week for
as long as it waits, the contacts and the people of the chain together. The days are the setting ESCALATION_DAYS (3, 7, 14, 21 by default) and ESCALATION_REPEAT_DAYS (7). A step is due when the
request is old enough, counted from the moment it was made, and when the step before it is a day old, so that a request that has waited long is
caught up one step at a time. Nothing here asks a model, and nothing here changes Azure.

Each step is one record: who it goes to, by which source, what could not be looked up on the way, and what became of the message. A message that is held (a pulled switch, a pause, quiet hours, the
rule of one message a day for a person) or that failed is kept, shown and tried again: delayed, never lost. A person who put the request off ("later") puts the next step off by up to
ESCALATION_SNOOZE_DAYS, and only the first ESCALATION_SNOOZES times: a put-off never silences. A person who says that it is not theirs makes the next step due at once.

A person is told at most once a day, however many requests have come to them: one letter lists them. A person who never heard from Meternaut is told who writes and why. The weekly letter goes to
the escalation contacts (and to the owners when something stops the ladder: a permission that is missing, a message that cannot be delivered).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Mapping, Sequence

from . import brief as brief_mod
from . import letters
from .directory import Directory, Next, NOTES, Target, of_person
from .http import GUID, SCOPE, Client, directory_calls
from .loop_config import EscalationSettings, LoopSettings
from .mail import ESCALATION_KINDS, Mailer
from .memory_store import parse, stamp
from .models import ADVISE, EscalationRecord, PlanRecord, Store, StoreError, started
from .people import People, Person

EPOCH = "2000-01-01T00:00:00Z"
MIN_GAP = dt.timedelta(days=1)  # a request that has waited long is caught up one step a day, never in a burst
GONE_BATCH = 40  # the ids of a Resource Graph query that asks whether resources are still there
RETRY_MINUTES, FAST_TRIES = 15, 12  # a message that failed is tried again every 15 minutes, 12 times, and after that once a day for as long as it is not delivered
ROUND_PLANS = 25  # the requests that one round of the ladder looks at: a round is a minute of the timer, and each request costs one read of the table, so no round reads more than this
WEEK = dt.timedelta(days=7)
CLOCK_TTL_HOURS = range(1, 337)  # what the old setting PLAN_TTL_HOURS allowed: a request closed at its creation plus a whole number of these hours was closed by the clock


def waited(plan: PlanRecord, now: dt.datetime) -> int:
    return letters.waited_days(plan, now)


def wait_days(number: int, settings: EscalationSettings) -> int:
    """The age of a request at which step `number` is due: the four days of the setting, then one more repeat for each step after the fourth."""
    return settings.days[number - 1] if number <= len(settings.days) else settings.days[-1] + (number - len(settings.days)) * settings.repeat_days


def due_number(plan: PlanRecord, steps: list[EscalationRecord], snoozes: list[EscalationRecord], passed: bool, settings: EscalationSettings, now: dt.datetime) -> int | None:
    """The number of the step that is due now, or None. At most one: the next after the last made, and never less than the second when somebody said that the request is not theirs. The
    first `settings.snoozes` put-offs each hold it back until they are `settings.snooze_days` old."""
    number = max((s.number for s in steps), default=0) + 1
    if passed:
        return max(number, 2)
    if steps and now < parse(steps[-1].at) + MIN_GAP:
        return None
    due = parse(started(plan)) + dt.timedelta(days=wait_days(number, settings))
    for put_off in snoozes[:settings.snoozes]:
        due = max(due, parse(put_off.at) + dt.timedelta(days=settings.snooze_days))
    return number if now >= due else None


def clock_closed(plan: PlanRecord) -> bool:
    """Whether the clock closed this request: it is `expired`, Meternaut gave no reason for taking it back, and it ended at its creation plus a whole number of hours, which the setting that
    existed once allowed. A request that was taken back ended at the moment it was taken back."""
    try:
        hours = (parse(plan.expires_at) - parse(plan.created_at)).total_seconds() / 3600
    except ValueError:
        return False
    return plan.state == "expired" and not brief_mod.taken_back(plan) and hours == int(hours) and int(hours) in CLOCK_TTL_HOURS


def revive(store: Store, now: dt.datetime, emit: Callable[..., object] = lambda kind, **fields: None) -> list[PlanRecord]:
    """Opens again, with their own start, the newest request of each resource that the clock closed and that nobody answered, and puts its case back to what it was before. Nothing is changed
    for a resource that has an open request, a request that a person answered, a case that moved on (its request now is another one), or a request that Meternaut took back with a reason. It is the same at
    each run: a request that is open is not touched. Returns the requests that it opened."""
    try:
        waiting = {plan.resource_id.lower() for plan in store.plans_open()}
        opened = []
        for plan in store.plans_expired():  # newest first
            if not clock_closed(plan) or plan.resource_id.lower() in waiting:  # the cheap tests first: a request that was taken back with a reason costs no read
                continue
            case = store.case_get(plan.case_id)
            if case is None or case.status != "expired" or case.plan_id != plan.plan_id:
                continue
            if any(d.decision in ("approve", "decline", "not_mine") for d in store.decisions_of_plan(plan.plan_id)):
                continue
            store.plan_put(replace(plan, state="open"))
            waiting.add(plan.resource_id.lower())
            before = (plan.preconditions or {}).get("caseStatus") if plan.family == ADVISE else "awaiting_ok"
            store.case_put(replace(case, status=before if before in ("proposed", "needs_human", "awaiting_ok") else "needs_human", plan_id=plan.plan_id, updated_at=stamp(now)))
            emit("plan.revived", planId=plan.plan_id, family=plan.family, daysWaiting=waited(plan, now))
            opened.append(plan)
        return opened
    except StoreError:
        return []


def tag_reader(arm: object, name: str) -> Callable[[PlanRecord], str]:
    """The reader of the escalation tag: the value on the resource, else on its resource group, else on its subscription, from two Resource Graph queries of fixed text that name only the ids of the
    request (checked against the shape of an id). Anything else of the resource stays unread, and a read that fails is no tag."""
    def read(plan: PlanRecord) -> str:
        found = re.match(rf"(/subscriptions/{GUID})(/resourceGroups/[^/]+)?", plan.resource_id or "", re.I)
        if found is None or not re.fullmatch(SCOPE, plan.resource_id, re.I):
            return ""
        subscription, group = found.group(1), (found.group(1) + found.group(2) if found.group(2) else "")
        queries = [f"// meternaut:escalation-tag\nresources | where id =~ '{plan.resource_id}' | project tags"] if "/providers/" in plan.resource_id else []
        queries.append("// meternaut:escalation-tag\nresourcecontainers | where id =~ '" + "' or id =~ '".join(i for i in (group, subscription) if i) + "' | project id, tags")
        rows: list[dict] = []
        for query in queries:
            try:
                rows += arm.graph(subscription.rsplit("/", 1)[-1], query)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 (a tag that cannot be read is no tag)
                continue
        order = {plan.resource_id.lower(): 0, group.lower(): 1, subscription.lower(): 2}
        for row in sorted(rows, key=lambda r: order.get(str(r.get("id") or plan.resource_id).lower(), 3)):
            tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}
            value = next((str(v) for k, v in tags.items() if str(k).lower() == name.lower() and v), "")
            if value:
                return value
        return ""
    return read


UNCHECKED = {"partial": "the subscription was not read in full", "read": "the read failed or the service asked to wait", "invisible": "the subscription did not answer",
             "type": "Resource Graph does not list this type of resource", "members": "the request does not name all of its resources"}
LISTED = ("microsoft.compute/disks", "microsoft.compute/virtualmachines", "microsoft.network/publicipaddresses", "microsoft.network/loadbalancers", "microsoft.network/privateendpoints",
          "microsoft.web/serverfarms")  # the types that the detectors read from Resource Graph


def existence(arm: object, plans: Iterable[PlanRecord], in_full: Callable[[str], bool] = lambda subscription: True,
              members: Callable[[PlanRecord], Sequence[str]] | None = None) -> dict[str, str]:
    """Whether what each request is about is still in Azure: `gone`, `there`, or a word of UNCHECKED that says why nobody knows. A resource is gone only when it is certain: the reads of Resource Graph
    for its subscription all worked, `in_full` calls the subscription read in full, the subscription answered, and either the resource group is not there or the resource is not there and Resource Graph
    lists its type (a type that it does not list would look gone for ever). A request about several resources (a group: `members` names them) is gone only when every one of them is, and is not checked
    when `members` cannot name all of them. Only an id of the shape of an id goes into a query."""
    def subscription_of(resource_id: str) -> str:
        found = re.match(rf"/subscriptions/({GUID})/", resource_id or "", re.I)
        return found.group(1).lower() if found is not None and re.fullmatch(SCOPE, resource_id, re.I) else ""

    def group_of(resource_id: str) -> str:
        parts = resource_id.split("/")
        return "/".join(parts[:5]) if len(parts) > 4 and parts[3].lower() == "resourcegroups" else ""

    def type_of(resource_id: str) -> str:
        tail = resource_id.lower().partition("/providers/")[2].split("/")
        return "/".join([tail[0], *tail[1::2]]) if len(tail) > 2 else ""
    answer: dict[str, str] = {}
    wanted: dict[str, list[str]] = {}
    for plan in plans:
        named = list(members(plan)) if members is not None else [plan.resource_id]
        if not named:
            answer[plan.plan_id] = "members"
        elif all(subscription_of(i) for i in named):
            wanted[plan.plan_id] = named
    by_subscription: dict[str, set[str]] = {}
    for named in wanted.values():
        for i in named:
            by_subscription.setdefault(subscription_of(i), set()).add(i)
    verdict: dict[str, str] = {}
    for subscription, found in by_subscription.items():
        if not in_full(subscription):
            verdict.update({i: "partial" for i in found})
            continue
        ids = sorted({f"/subscriptions/{subscription}", *found, *(group_of(i) for i in found)} - {""}, key=str.lower)
        seen: set[str] = set()
        try:
            for start in range(0, len(ids), GONE_BATCH):
                match = "' or id =~ '".join(ids[start:start + GONE_BATCH])
                for table in ("resourcecontainers", "resources"):
                    seen |= {str(row.get("id") or "").lower() for row in arm.graph(subscription, f"// meternaut:existence\n{table} | where id =~ '{match}' | project id")}  # type: ignore[attr-defined]
            listed = {str(row.get("type") or "").lower() for row in arm.graph(subscription, "// meternaut:existence-types\nresources | summarize count() by type")}  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 (a read that failed or was told to wait tells nothing)
            verdict.update({i: "read" for i in found})
            continue
        for i in found:
            group = group_of(i)
            verdict[i] = ("invisible" if f"/subscriptions/{subscription}" not in seen else "there" if i.lower() in seen
                          else "gone" if (group and group.lower() not in seen) or type_of(i) in {*listed, *LISTED} else "type")
    for plan_id, named in wanted.items():
        words = {verdict[i] for i in named}
        answer[plan_id] = "gone" if words == {"gone"} else "there" if "there" in words else next(word for word in UNCHECKED if word in words)
    return answer


@dataclass
class Ladder:
    """What one round of the ladder works with."""

    store: Store
    people: People
    mailer: Mailer
    directory: Directory
    settings: EscalationSettings
    base: str
    clock: Callable[[], dt.datetime]
    contacts: tuple[str, ...] = ()  # the people responsible for Meternaut, for the last line of a letter
    tag: Callable[[PlanRecord], str] = lambda plan: ""
    emit: Callable[..., object] = lambda kind, **fields: None


def _names(targets: tuple[Target, ...]) -> tuple[str, ...]:
    return tuple(t.name for t in targets)


def _audience(ladder: Ladder, plan: PlanRecord, number: int, steps: list[EscalationRecord]) -> Next:
    """Who step `number` goes to. Step 1: the people that the request was made for, who did not say that it is not theirs. Steps 2 and 3: the next person after those who said it is not theirs or, when
    nobody did, after the people that it was made for, and after the people of the step before. Step 4: the escalation contacts. After that: the contacts and every person that the chain told."""
    directory, store = ladder.directory, ladder.store
    refused = [d.approver_oid.lower() for d in store.decisions_of_plan(plan.plan_id) if d.decision == "not_mine"]
    named = [p for p in (ladder.people.by_oid(o) for o in plan.approvers) if p is not None and p.mail and p.oid.lower() not in refused]
    if number == 1 and named:
        return Next(tuple(of_person(p) for p in named), "same")
    if number in (2, 3):
        previous = next((s for s in reversed(steps) if s.number >= 2), None)
        by = list(previous.who) if previous is not None else (refused or [p.oid for p in named] or list(plan.approvers))
        told = {oid.lower() for s in steps for oid in s.who} | {p.oid.lower() for p in named} | set(refused)
        return directory.next_after(by, after=previous.source if previous is not None else "", tag=lambda: ladder.tag(plan), skip=told)
    found = directory.contacts()
    if number <= 4:
        return found
    chain, notes = {t.oid: t for t in found.targets}, list(found.notes)
    for oid in dict.fromkeys(o for s in steps if s.number >= 2 for o in s.who):
        target, note = directory.by_oid(oid)
        if target is not None:
            chain.setdefault(target.oid, target)
        elif note:
            notes.append(note)
    return Next(tuple(chain.values()), found.source, tuple(dict.fromkeys(notes)))


def _who(records: Iterable[EscalationRecord], *kinds: str, below: int = 10**9) -> set[str]:
    return {oid.lower() for r in records if r.kind in kinds and r.number < below for oid in r.who}


def audience(ladder: Ladder, plan: PlanRecord, number: int, steps: list[EscalationRecord], records: Sequence[EscalationRecord] = ()) -> Next:
    """Who step `number` goes to (`_audience`) and the people who were added to the approvers of the request after it was made and that no step has told yet (Approvals.keep_approvers): the next step
    tells them too, whatever its source."""
    found = _audience(ladder, plan, number, steps)
    wanted = _who(records, "added") - _who(steps, "step")
    if wanted:
        wanted -= {d.approver_oid.lower() for d in ladder.store.decisions_of_plan(plan.plan_id) if d.decision == "not_mine"}
    news = tuple(of_person(p) for p in (ladder.people.by_oid(o) for o in plan.approvers) if p is not None and p.mail and p.oid.lower() in wanted)
    return Next(tuple({t.oid: t for t in (*found.targets, *news)}.values()), found.source, found.notes) if news else found


def _was_added(records: Sequence[EscalationRecord], record: EscalationRecord, oid: str) -> bool:
    """Whether this step is the first to tell the person, who was added to the approvers of the request after it was made: the letter says so."""
    return oid.lower() in _who(records, "added") - _who(records, "step", below=record.number)


def make_step(ladder: Ladder, plan: PlanRecord, number: int, steps: list[EscalationRecord], records: Sequence[EscalationRecord] = ()) -> bool:
    """Makes step `number` of the plan once: who it goes to is worked out, and the record is claimed; False when another round made it first."""
    found = audience(ladder, plan, number, steps, records)
    record = EscalationRecord(plan.plan_id, "step", number, stamp(ladder.clock()), found.source, tuple(t.oid for t in found.targets), _names(found.targets), (), "email",
                              "due" if found.targets else "failed", found.notes, "" if found.targets else "Nobody on the list has a mail address.")
    if not ladder.store.escalation_claim(record):
        return False
    ladder.emit("escalation.step", planId=plan.plan_id, step=number, source=found.source, people=len(found.targets), notes=",".join(found.notes))
    return True


def _asked(ladder: Ladder, plan: PlanRecord, steps: list[EscalationRecord]) -> str:
    first = next((s for s in steps if s.kind == "step" and s.number == 1), None)
    return ", ".join(first.names) if first is not None else ", ".join(p.name for p in (ladder.people.by_oid(o) for o in plan.approvers) if p is not None)


def _first_contact(ladder: Ladder, oid: str) -> bool:
    return not any(m.status == "sent" for m in ladder.store.mails_since(oid, EPOCH))


def _mark(ladder: Ladder, record: EscalationRecord, **changes: object) -> EscalationRecord:
    changed = replace(record, **changes)
    if changed != record:
        ladder.store.escalation_put(changed)
    return changed


def _records(store: Store, plans: Iterable[PlanRecord]) -> dict[str, list[EscalationRecord]]:
    """The records of the ladder of each request, read for the request itself: a store that lists by key cannot be asked for the newest rows of all of them."""
    return {plan.plan_id: store.escalations_of(plan.plan_id) for plan in plans}


def _window(plans: list[PlanRecord], now: dt.datetime) -> list[PlanRecord]:
    """The requests that a round looks at: all of them while there are no more than ROUND_PLANS, else the next ROUND_PLANS in the order of their start (who waits longest first), a different part each
    minute, so that every request is looked at within a few minutes and no round costs more than ROUND_PLANS reads, however many requests wait."""
    ordered = sorted(plans, key=lambda plan: (started(plan), plan.plan_id))
    part = int(now.timestamp() // 60) % max(-(-len(ordered) // ROUND_PLANS), 1)
    return ordered[part * ROUND_PLANS:(part + 1) * ROUND_PLANS]


def deliver(ladder: Ladder, plans: Mapping[str, PlanRecord] | None = None, records: Mapping[str, list[EscalationRecord]] | None = None) -> int:
    """Tells the people that the steps have come to, once a day at most for each person: one letter for one request, one letter that lists several. A person that is not to be written to now (a
    switch, a pause, quiet hours, the rule of a message a day) keeps the step as held, with the reason, and is tried again; a message that failed is tried again later. The requests and their records
    are the ones that the round read (`tick`). Returns the letters sent."""
    now, store = ladder.clock(), ladder.store
    by_person: dict[str, list[tuple[PlanRecord, EscalationRecord]]] = {}
    if plans is None:
        plans = {p.plan_id: p for p in store.plans_open() if p.state == "open"}
    if records is None:
        records = _records(store, plans.values())
    for record in (r for rs in records.values() for r in rs if r.kind == "step"):
        if record.outcome == "failed" and record.last_try and now < parse(record.last_try) + dt.timedelta(minutes=RETRY_MINUTES if record.tries < FAST_TRIES else 1440):
            continue
        for oid in record.who:
            if oid not in record.delivered:
                by_person.setdefault(oid, []).append((plans[record.plan_id], record))
    sent = 0
    latest: dict[tuple[str, int], EscalationRecord] = {}  # a step that goes to several people is marked once for each person: each mark starts from the newest version of the record

    def mark(record: EscalationRecord, build: Callable[[EscalationRecord], dict]) -> None:
        key = (record.plan_id, record.number)
        latest[key] = _mark(ladder, latest.get(key, record), **build(latest.get(key, record)))
    for oid, items in by_person.items():
        items.sort(key=lambda item: (item[1].at, item[1].number))
        reason = ladder.mailer.hold_reason(oid, "escalation")
        today = [m for m in store.mails_since(oid, stamp(now - dt.timedelta(days=1))) if m.kind in ESCALATION_KINDS and m.status == "sent"]
        if reason or today:
            for plan, record in items:
                mark(record, lambda r: {"outcome": "held", "detail": reason or "One message a day: this goes tomorrow."})
            continue
        target, note = ladder.directory.by_oid(oid)
        if target is None:
            for plan, record in items:
                mark(record, lambda r: {"outcome": "failed", "tries": r.tries + 1, "last_try": stamp(now), "detail": NOTES.get(note, "The person could not be looked up."),
                                        "notes": tuple(dict.fromkeys(r.notes + ((note,) if note else ())))})
            continue
        person, first = ladder.people.by_oid(oid) or Person(oid, target.name, (), target.mail), _first_contact(ladder, oid)
        rows = [(plan, store.case_get(plan.case_id), record, _was_added(records[plan.plan_id], record, oid)) for plan, record in items]
        if len(rows) == 1:
            plan, case, record, added = rows[0]
            steps = store.escalations_of(plan.plan_id)
            told, pending = brief_mod.told_lines(steps, record.number)
            letter = letters.escalation_letter(plan, case, person, ladder.base, now, ladder.contacts, source="same" if added else record.source, asked=_asked(ladder, plan, steps),
                                               notes=tuple(NOTES.get(n, "") for n in record.notes), told=told, pending=pending, first=first,
                                               put_off=sum(1 for r in steps if r.kind == "snooze"), added=added)
            result = ladder.mailer.send_escalation(target, letter, "escalation", plan.plan_id, record.number, record.source)
        else:
            letter = letters.escalation_digest_letter(person, ladder.base, now, [(plan, case, "same" if added else record.source) for plan, case, record, added in rows], ladder.contacts, first=first,
                                                      added=any(added for *_, added in rows))
            result = ladder.mailer.send_escalation(target, letter, "escalation", rows[0][0].plan_id, rows[0][2].number, f"{rows[0][2].source}, with {len(rows) - 1} more")
        for _, record in items:
            if result.status == "sent":
                mark(record, lambda r: {"delivered": r.delivered + (oid,), "outcome": "sent" if set(r.who) <= set(r.delivered + (oid,)) else r.outcome, "detail": "", "last_try": stamp(now)})
            else:
                mark(record, lambda r: {"outcome": "held" if result.status == "held" else "failed", "tries": r.tries + (result.status != "held"), "last_try": stamp(now), "detail": result.detail[:240]})
        sent += result.status == "sent"
    return sent


def weekly(ladder: Ladder, plans: Iterable[PlanRecord] | None = None, records: Mapping[str, list[EscalationRecord]] | None = None) -> int:
    """The weekly letter, while a request has waited more than a week: to every escalation contact (the owners when none is set), every request that waits with its own figure and how long, and, to
    the owners as well, what stops the ladder (a permission that is missing, a message that could not be delivered, as far as the records of this round show). Not more than once in six days for a
    person, not on a day that another escalation letter went to them. A weekly letter that fails is tried again every 15 minutes, 12 times, and then once a day, like the other letters."""
    now, store = ladder.clock(), ladder.store
    waiting = [p for p in (store.plans_open() if plans is None else plans) if p.state == "open"]
    due = any(waited(p, now) > 7 for p in waiting)
    recent = [r for rs in (_records(store, waiting) if records is None else records).values() for r in rs]
    problems = []
    if any("no_permission" in r.notes and r.at >= stamp(now - WEEK) for r in recent):
        problems.append(NOTES["no_permission"] + " The permission is Microsoft Graph User.Read.All for the app's identity, which a person with the right Entra role grants (docs/proposals/30-escalation.md).")
    if any(r.outcome == "failed" and r.kind == "step" and r.tries >= FAST_TRIES for r in recent):
        problems.append("A message about a waiting request could not be delivered after many tries. It is tried again every day, and the pages show which.")
    contacts = ladder.directory.contacts().targets
    owners = ladder.directory.owners()
    sent = 0
    for target in dict.fromkeys(contacts + (owners if problems else ())):
        if not (due or problems):
            break
        tried = [m for m in store.mails_since(target.oid, stamp(now - dt.timedelta(days=6))) if m.kind in ESCALATION_KINDS]
        week = [m for m in tried if m.status == "sent"]
        failed = sum(1 for m in tried if m.kind == "escalation-weekly" and m.status == "failed")
        again = stamp(now - (dt.timedelta(minutes=RETRY_MINUTES) if failed < FAST_TRIES else dt.timedelta(days=1)))
        if (any(m.kind == "escalation-weekly" for m in week) or any(m.sent_at >= stamp(now - dt.timedelta(days=1)) for m in week) or ladder.mailer.hold_reason(target.oid, "escalation-weekly")
                or any(m.kind == "escalation-weekly" and m.sent_at > again for m in tried)):
            continue
        person = ladder.people.by_oid(target.oid) or Person(target.oid, target.name, (), target.mail)
        mine = waiting if due and target in contacts else []
        letter = letters.escalation_weekly_letter(person, ladder.base, now, [(p, store.case_get(p.case_id)) for p in sorted(mine, key=started)], ladder.contacts, problems, first=_first_contact(ladder, target.oid))
        if (mine or problems) and ladder.mailer.send_escalation(target, letter, "escalation-weekly", None, 0, "weekly").status == "sent":
            sent += 1
    return sent


def tick(ladder: Ladder) -> int:
    """One round of the ladder: the steps that are due (at most one for each request), then the letters that wait to go, then the weekly letter. A round looks at ROUND_PLANS requests at most (see
    `_window`), and each of them is read once for the three parts of it. Returns the steps made. It never raises."""
    made = 0
    try:
        now = ladder.clock()
        plans = [p for p in ladder.store.plans_open() if p.state == "open"]
        looked = _window(plans, now)
        records = _records(ladder.store, looked)
        for plan in looked:
            mine = sorted(records[plan.plan_id], key=lambda r: r.number)
            steps, snoozes = [r for r in mine if r.kind == "step"], [r for r in mine if r.kind == "snooze"]
            last = steps[-1].at if steps else ""
            number = due_number(plan, steps, snoozes, any(r.kind == "pass" and r.at > last for r in mine), ladder.settings, now)
            if number is not None and make_step(ladder, plan, number, steps, mine):
                made += 1
                records[plan.plan_id] = ladder.store.escalations_of(plan.plan_id)  # the new step goes out in this round
        deliver(ladder, {plan.plan_id: plan for plan in looked}, records)
        weekly(ladder, plans, records)
    except Exception as error:  # noqa: BLE001 (a round of the ladder never stops the timer; the next minute tries again)
        ladder.emit("run.note", note=f"the ladder could not finish a round: {type(error).__name__}")
    return made


def hook(env: Mapping[str, str], settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic,
         clock: Callable[[], dt.datetime]) -> Callable[..., int]:
    """What the timer calls every minute: `on_round(arm, emit)` makes one round of the ladder (`tick`) with the directory of this round, and returns the steps made. The timer never takes a request
    back, whatever it reads of Azure: that is the Watch's, which has read the subscription in full (`existence`)."""
    from .notify import build_mailer, contacts_of  # imported here: notify imports the web pages, which import a good part of the app
    mailer = build_mailer(settings, store, people, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    mailer.deny = tuple(item.strip().lower() for item in settings.escalation.deny)

    def on_round(arm: object = None, emit: Callable[..., object] = lambda kind, **fields: None) -> int:
        client = Client(directory_calls(), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        found = Directory(client, token, people, managers=settings.escalation.managers, deny=settings.escalation.deny)
        reader = tag_reader(arm, settings.escalation.tag) if arm is not None else (lambda plan: "")
        return tick(Ladder(store, people, mailer, found, settings.escalation, settings.base_url, clock, contacts_of(people), reader, emit))

    return on_round
