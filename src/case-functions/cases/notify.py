"""Tells the people: the letter about a plan that needs an answer, the letter about a change that ran, the first contact and the weekly desk.

The hooks are given to the loop when a sender is set. They never raise: a letter that cannot be sent is a line in the log and a record in the store, and the
loop goes on. A letter goes to a person on the list of people and to nobody else (mail.py checks that again), and the same letter is not sent twice.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Callable, Mapping

from . import letters
from .http import Client
from .loop_config import LoopSettings
from .mail import Mailer, mail_calls
from .models import ActionRecord, CaseRecord, PlanRecord, RunRecord, Store
from .people import People, Person

LOG = logging.getLogger("meternaut.notify")
EPOCH = "2000-01-01T00:00:00Z"


def build_mailer(settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep,
                 monotonic, clock: Callable[[], dt.datetime]) -> Mailer:
    sender = settings.mail_sender or ""
    client = Client(mail_calls(sender), redact, transport=transport, sleep=sleep, monotonic=monotonic)
    return Mailer(sender, client, token, people, store, clock, redact, ids=lambda: uuid.uuid4().hex[:12])


def hooks(env: Mapping[str, str], settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *,
          transport, sleep, monotonic, clock: Callable[[], dt.datetime]):
    """(on_plan, on_action, on_run): what the loop calls when a plan is made, when a change ran or was checked, and when a Watch finished."""
    mailer = build_mailer(settings, store, people, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    base = settings.base_url

    def already(person: Person, kind: str, plan_id: str | None = None, since: str = EPOCH) -> bool:
        return any(m.kind == kind and m.status == "sent" and (plan_id is None or m.plan_id == plan_id) for m in store.mails_since(person.oid, since))

    def safely(what: str, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as error:  # noqa: BLE001 (a letter never stops the loop)
            LOG.error(redact(f"{what} could not be sent: {type(error).__name__}: {error}"))

    def on_plan(plan: PlanRecord, case: CaseRecord) -> None:
        def work() -> None:
            now = clock()
            for oid in plan.approvers:
                person = people.by_oid(oid)
                if person is None or not person.mail:
                    continue
                if not already(person, "first_contact"):
                    mailer.send(person, letters.first_contact_letter(person, base, now), "first_contact")
                if not already(person, "approval", plan.plan_id):
                    mailer.send(person, letters.approval_letter(plan, case, person, base, now), "approval", plan.plan_id)
        safely("the letter about a plan", work)

    def on_action(action: ActionRecord, plan: PlanRecord | None, case: CaseRecord | None) -> None:
        def work() -> None:
            if plan is None or case is None:
                return
            kind = "verified" if action.state == "verified" else "notice"
            now = clock()
            for oid in plan.approvers:
                person = people.by_oid(oid)
                if person is None or not person.mail or already(person, kind, plan.plan_id):
                    continue
                mailer.send(person, letters.done_letter(plan, action, case, person, base, now), kind, plan.plan_id)
        safely("the letter about a change", work)

    def on_run(run: RunRecord) -> None:
        def work() -> None:
            now = clock()
            for person in people.persons:
                if not person.mail or "approver" not in person.roles and "owner" not in person.roles:
                    continue
                settings_of = store.settings_get(person.oid)
                if now.isoweekday() != settings_of.desk_day or already(person, "digest", since=(now - dt.timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ")):
                    continue
                week = (now - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
                runs = [r for r in store.runs_recent(30) if r.started_at >= week]
                cases = [c for c in store.cases_recent(100) if c.updated_at >= week]
                mailer.send(person, letters.digest_letter(person, base, now, runs, cases, store.plans_open()), "digest")
        safely("the weekly desk", work)

    return on_plan, on_action, on_run
