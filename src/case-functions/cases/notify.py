"""Tells the people: the letter about a plan that needs an answer, the letter about a change that ran, the first contact and the weekly summary.

The hooks are given to the loop when a sender is set. They never raise: a letter that cannot be sent is a line in the log and a record in the store, and the
loop goes on. A letter goes to a person on the list of people and to nobody else (mail.py checks that again), and the same letter is not sent twice. A letter
that was held or failed is offered again by the timer (every call of a hook sends a letter only when it is due): after 15 minutes, at most 12 times. Exchange
can take up to two hours to apply a new right to send, so the first letters of a new mailbox are tried more than once. A finding that only asks a person whether it
is worth acting on (an advise plan) gets no letter of its own: it waits on the page and in the weekly summary, which is sent only when something waits.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Callable, Mapping

from . import letters
from .brief import contact_text
from .http import Client
from .loop_config import LoopSettings
from .mail import Mailer, mail_calls
from .memory_store import parse
from .models import ADVISE, ActionRecord, CaseRecord, PlanRecord, RunRecord, Store
from .people import People, Person

LOG = logging.getLogger("meternaut.notify")
EPOCH = "2000-01-01T00:00:00Z"
RETRY_MINUTES = 15  # a letter that was not sent is offered again after this long
MAX_TRIES = 12  # and given up after this many tries: the record of each try says why, and the console shows the plan whatever happened to the letter


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

    def due(person: Person, kind: str, plan_id: str | None = None) -> bool:
        """True when a letter of this kind is to be tried now: none was sent, the last try is old enough and the tries are not used up."""
        tries = [m for m in store.mails_since(person.oid, EPOCH) if m.kind == kind and (plan_id is None or m.plan_id == plan_id)]
        if any(m.status == "sent" for m in tries) or len(tries) >= MAX_TRIES:
            return False
        return not tries or clock() - parse(max(m.sent_at for m in tries)) >= dt.timedelta(minutes=RETRY_MINUTES)

    def safely(what: str, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as error:  # noqa: BLE001 (a letter never stops the loop)
            LOG.error(redact(f"{what} could not be sent: {type(error).__name__}: {error}"))

    def contacts() -> tuple[str, ...]:
        """The people to talk to, for the last line of a letter: those with the role owner or ops (or everybody listed, when none has one), each as a name with the address, in
        plain text. A letter names the first of them who is not the person who reads it."""
        chosen = [p for p in people.persons if "ops" in p.roles or "owner" in p.roles] or list(people.persons)
        return tuple(contact_text(p.name, p.mail) for p in chosen[:3])

    def on_plan(plan: PlanRecord, case: CaseRecord) -> None:
        def work() -> None:
            if plan.family == ADVISE:
                return  # advice is not urgent: it waits on the page and in the weekly summary, and one letter for each finding would be a flood
            now = clock()
            for oid in plan.approvers:
                person = people.by_oid(oid)
                if person is None or not person.mail:
                    continue
                if due(person, "first_contact"):
                    mailer.send(person, letters.first_contact_letter(person, base, now, contacts(), plan.plan_id), "first_contact")
                if due(person, "approval", plan.plan_id):
                    mailer.send(person, letters.approval_letter(plan, case, person, base, now, contacts()), "approval", plan.plan_id)
        safely("the letter about a plan", work)

    def on_action(action: ActionRecord, plan: PlanRecord | None, case: CaseRecord | None) -> None:
        def work() -> None:
            if plan is None or case is None:
                return
            kinds = ("notice", "verified") if action.state == "verified" else ("notice",)
            now = clock()
            for oid in plan.approvers:
                person = people.by_oid(oid)
                if person is None or not person.mail:
                    continue
                for kind in kinds:
                    if due(person, kind, plan.plan_id):
                        mailer.send(person, letters.done_letter(plan, action, case, person, base, now, contacts()), kind, plan.plan_id)
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
                mine = [(plan, store.case_get(plan.case_id)) for plan in store.plans_open() if plan.state == "open" and person.oid.lower() in {a.lower() for a in plan.approvers}]
                letter = letters.digest_letter(person, base, now, mine, contacts())
                if letter is not None:  # the summary is sent only when something waits for this person
                    mailer.send(person, letter, "digest")
        safely("the weekly desk", work)

    return on_plan, on_action, on_run
