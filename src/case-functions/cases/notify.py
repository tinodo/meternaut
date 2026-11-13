"""Tells the people: the letter about a plan that needs an answer, the letter about a change that ran, failed or stayed unknown, the first contact and the weekly summary.

The hooks are given to the loop when a sender is set. They never raise: a letter that cannot be sent is a line in the log and a record in the store, and the
loop goes on. A letter goes to a person on the list of people and to nobody else (mail.py checks that again), and the same letter is not sent twice. A letter
that was held or failed is offered again by the timer (every call of a hook sends a letter only when it is due): after 15 minutes, at most 12 times. Exchange
can take up to two hours to apply a new right to send, so the first letters of a new mailbox are tried more than once. A finding that only asks a person whether it
is worth acting on (an advise plan) gets no letter of its own: it waits on the page and in the weekly summary, which is sent only when something waits. A change whose result stays unknown
gets one letter of its own kind (`unsure`) once the result has been unknown for UNKNOWN_HOURS, and no card: it goes to a person who chose Teams as well, and a later letter about what
came of the change is still sent.

A person who chose Teams (the setting `channel`) gets the card first (it goes on the queue `teams-cards`: cases/offers.py) and the letter follows only when no card was put on the queue in the first twenty minutes, so
that a person whose card could not be queued still hears about a request. A card and a letter for one request never both go: each looks at the other's record.

Quiet hours (cases/quiet.py): nothing is offered to a person inside their quiet hours. The rounds that offer a letter again look at the hours first and write nothing while they last, so that
the wait uses up none of the twelve tries; the first round after the hours sends what is still due. A letter that nothing else offers again, the weekly summary and the letter of a trip, is
offered by `waiting_hook` once the hours are over, when the mailer recorded that it held it for them.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Callable, Mapping

from . import alerts, letters, quiet
from .brief import contact_text
from .http import Client
from .loop_config import LoopSettings
from .mail import Mailer, mail_calls
from .memory_store import parse
from .models import ADVISE, TIME_FORMAT, ActionRecord, CaseRecord, PlanRecord, RunRecord, Store
from .people import People, Person
from .web.common import may_answer

LOG = logging.getLogger("meternaut.notify")
EPOCH = "2000-01-01T00:00:00Z"
RETRY_MINUTES = 15  # a letter that was not sent is offered again after this long
MAX_TRIES = 12  # and given up after this many tries: the record of each try says why, and the pages show the plan whatever happened to the letter
TEAMS_FIRST_MINUTES = 20  # the card of a person who chose Teams has this long to go before the letter does
WAITING_DAYS = 7  # a letter that quiet hours held back is looked for this long
UNKNOWN_HOURS = 2  # a result that is not known is told after it has stayed so this long: most are known within minutes, by the checks that follow a change


def build_mailer(settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep,
                 monotonic, clock: Callable[[], dt.datetime]) -> Mailer:
    sender = settings.mail_sender or ""
    client = Client(mail_calls(sender), redact, transport=transport, sleep=sleep, monotonic=monotonic)
    return Mailer(sender, client, token, people, store, clock, redact, ids=lambda: uuid.uuid4().hex[:12])


def contacts_of(people: People) -> tuple[str, ...]:
    """The people who are responsible for Meternaut, for the last line of a letter: those with the role owner or ops (or everybody listed, when none has one), each as a name with the
    address, in plain text. A letter names the first of them who is not the person who reads it."""
    chosen = [p for p in people.persons if "ops" in p.roles or "owner" in p.roles] or list(people.persons)
    return tuple(contact_text(p.name, p.mail) for p in chosen[:3])


def digest_for(person: Person, store: Store, people: People, base: str, now: dt.datetime) -> letters.Letter | None:
    """The weekly summary for a person, or None when nothing waits for them (it is sent only then). The requests that the Decisions page shows this person: the ones that they may answer (the
    page's own rule), and the ones that they put off are marked, as the page marks them."""
    principal = people.principal(person.oid)
    mine = [(plan, store.case_get(plan.case_id)) for plan in store.plans_open() if plan.state == "open" and principal is not None and may_answer(principal, plan)]
    later = {d.plan_id for d in store.decisions_by(person.oid, 200) if d.decision == "later"}
    return letters.digest_letter(person, base, now, mine, contacts_of(people), later)


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

    def quiet_now(person: Person) -> bool:
        """True while the person is inside their quiet hours: nothing is tried for them, and nothing is written, so that waiting uses up no try. Settings that cannot be read are not a reason to
        wait here: the mailer holds the letter for them in its own words."""
        try:
            return quiet.inside(store.settings_get(person.oid), clock())
        except Exception as error:  # noqa: BLE001 (the mailer looks at the settings again)
            LOG.error(redact(f"the quiet hours of a person could not be read: {type(error).__name__}"))
            return False

    def card_goes_first(person: Person, card_kind: str, since: str, plan_id: str | None = None) -> bool:
        """True while the card of a person who chose Teams has the first go: a card of this kind was sent (the letter is not needed), or it is less than TEAMS_FIRST_MINUTES since the
        request was made, or since the person's quiet hours ended when they ended after that. Anything that cannot be read, and any other channel, is False: the letter is the fallback."""
        try:
            settings_of = store.settings_get(person.oid)
            if settings_of.channel != "teams":
                return False
            if any(m.kind == card_kind and m.status == "sent" and (plan_id is None or m.plan_id == plan_id) for m in store.mails_since(person.oid, EPOCH)):
                return True
            begun = parse(since)
            ended = quiet.last_end(settings_of, clock())  # the card could not go while the hours lasted, so its twenty minutes begin when they end
            if ended is not None and ended > begun:
                begun = ended
            return clock() - begun < dt.timedelta(minutes=TEAMS_FIRST_MINUTES)
        except Exception as error:  # noqa: BLE001 (the letter is the fallback)
            LOG.error(redact(f"the channel of a person could not be read: {type(error).__name__}"))
            return False

    def contacts() -> tuple[str, ...]:
        return contacts_of(people)

    def on_plan(plan: PlanRecord, case: CaseRecord) -> None:
        def work() -> None:
            if plan.family == ADVISE:
                return  # advice is not urgent: it waits on the page and in the weekly summary, and one letter for each finding would be a flood
            now = clock()
            for oid in plan.approvers:
                person = people.by_oid(oid)
                if person is None or not person.mail or quiet_now(person):
                    continue
                if due(person, "first_contact") and not card_goes_first(person, "first-contact-card", plan.created_at):
                    mailer.send(person, letters.first_contact_letter(person, base, now, contacts(), plan.plan_id), "first_contact")
                if due(person, "approval", plan.plan_id) and not card_goes_first(person, "approval-card", plan.created_at, plan.plan_id):
                    mailer.send(person, letters.approval_letter(plan, case, person, base, now, contacts()), "approval", plan.plan_id)
        safely("the letter about a plan", work)

    def on_action(action: ActionRecord, plan: PlanRecord | None, case: CaseRecord | None) -> None:
        def work() -> None:
            if plan is None or case is None:
                return
            now = clock()
            since = action.finished_at or action.queued_at
            if action.state == "unknown":
                if now - parse(since) < dt.timedelta(hours=UNKNOWN_HOURS):
                    return
                kinds = ("unsure",)  # its own kind: the letter that says what happened when the result is known later is still due
            else:
                kinds = ("notice", "verified") if action.state == "verified" else ("notice",)
            for oid in plan.approvers:
                person = people.by_oid(oid)
                if person is None or not person.mail or quiet_now(person):
                    continue
                for kind in kinds:
                    if due(person, kind, plan.plan_id) and not card_goes_first(person, f"{kind}-card", since, plan.plan_id):
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
                letter = digest_for(person, store, people, base, now)
                if letter is not None:  # the summary is sent only when something waits for this person; inside their quiet hours the mailer holds it, and waiting_hook sends it after them
                    mailer.send(person, letter, "digest")
        safely("the weekly desk", work)

    return on_plan, on_action, on_run


def waiting_hook(settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic,
                 clock: Callable[[], dt.datetime]) -> Callable[[], None]:
    """What the timer calls every minute for the two letters that nothing else offers again: the weekly summary and the letter of a trip. The mailer recorded that quiet hours held one back
    (the record is `held`, with the words of quiet.WAITING); once the person's hours are over and no letter of that kind was sent since, it is made again from what is true now and sent. A
    summary for which nothing waits any more is not sent, and a trip that a person released since is not told. It never raises."""
    mailer = build_mailer(settings, store, people, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    base = settings.base_url

    def pending(person: Person, kind: str, now: dt.datetime) -> bool:
        since = (now - dt.timedelta(days=WAITING_DAYS)).strftime(TIME_FORMAT)
        mails = [m for m in store.mails_since(person.oid, since) if m.kind == kind]
        held = [m.sent_at for m in mails if m.status == "held" and m.detail == quiet.WAITING]
        return bool(held) and not any(m.status == "sent" and m.sent_at >= max(held) for m in mails)

    def for_person(person: Person, now: dt.datetime) -> None:
        if quiet.inside(store.settings_get(person.oid), now):
            return
        if pending(person, "digest", now):
            letter = digest_for(person, store, people, base, now)
            if letter is not None:
                mailer.send(person, letter, "digest")
        if "owner" in person.roles and pending(person, "alert", now):
            trip = store.switch_get("investigation")
            code = alerts.code_of(trip.reason) if trip.paused else None
            if code is not None:
                mailer.send(person, alerts.letter(code, "", base, now), "alert")

    def on_tick() -> None:
        now = clock()
        for person in people.persons:
            if not person.mail:
                continue
            try:
                for_person(person, now)
            except Exception as error:  # noqa: BLE001 (a letter never stops the timer)
                LOG.error(redact(f"a letter that quiet hours held back could not be sent: {type(error).__name__}"))

    return on_tick


def alert_hook(settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic,
               clock: Callable[[], dt.datetime]) -> Callable[[str, str], None]:
    """The hook of a trip (cases/harness.py): the one letter to each person with the role owner, from the same mailer as every other letter. It never raises. The letter says what stopped
    and how to release it, in fixed sentences (cases/alerts.py); it is sent as the kind `alert`, which the weekly budget does not hold."""
    mailer = build_mailer(settings, store, people, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)

    def on_alert(code: str, detail: str) -> None:
        try:
            now = clock()
            for person in people.with_role("owner"):
                if person.mail:
                    mailer.send(person, alerts.letter(code, detail, settings.base_url, now), "alert")
        except Exception as error:  # noqa: BLE001 (a letter never stops the brake)
            LOG.error(redact(f"the letter of a trip could not be sent: {type(error).__name__}"))

    return on_alert
