"""The cards that Meternaut sends on its own: the card of a request that waits for a person, of a change that ran, and of a check that came after it.

It does for the people who chose Teams what mail.py and notify.py do for the letters, with the same checks, in the same order, and the same words for what came of each try. A person
who chose e-mail (the default) gets no card, a person who chose the weekly summary gets none either, and a person who chose Teams gets the card first: the letter follows (notify.py) only
when no card was sent in the first twenty minutes.

Before a card goes, in this order, and the first check that fails ends the try and is written as its outcome (a record of kind `approval-card`, `advice-card`, `notice-card` or
`verified-card` in the store of mail records, which is the one place that the letters and the cards both count in):
1. the person is on the list of people and is named on the plan, and may answer it (the role approver; for advice, the owner too);
2. held: the switch `messages` or `all` is pulled (a switch that cannot be read counts as pulled);
3. held: the person paused messages (`SettingsRecord.paused_until` is in the future);
4. held: the person's weekly budget is reached. Only the card of advice counts against it: an approval, a notice and a check are asked for or owed, as with the letters, and the weekly
   budget does not hold them; advice is not urgent, and one card for each finding would be a flood;
5. failed: the person has no conversation with the bot that Meternaut knows of (references.py) and Teams will not start one (the app is not installed for the person, or the person
   blocked it). The try is written, and the letter follows after the twenty minutes.
A try that was held or failed is offered again after 15 minutes, at most 12 times. A card that was sent is never sent again for the same request, and a card is not sent for a request whose
letter went already.

Delivery is not proof: `sent` means that the Connector took the card. What came of the try is the only thing that is written: no body, no name and no figure of the card is kept in the record.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Callable

from . import cards, switches
from .brief import build_brief, contact_text
from .cards import CardContext, CardError
from .connector import Connector
from .mail import BUDGET_FREE_KINDS
from .memory_store import parse, stamp
from .models import ADVISE, TIME_FORMAT, ActionRecord, CaseRecord, MailRecord, PlanRecord, Store
from .people import People, Person
from .references import MemoryReferences, ReferenceTable, made

LOG = logging.getLogger("meternaut.teams.offers")
EPOCH = "2000-01-01T00:00:00Z"
RETRY_MINUTES = 15  # a card that was not sent is offered again after this long
MAX_TRIES = 12  # and given up after this many tries
RESULT_DAYS = 3  # the cards about a change are offered for this long after it
APPROVAL, ADVICE, NOTICE, VERIFIED, FIRST_CONTACT = "approval-card", "advice-card", "notice-card", "verified-card", "first-contact-card"
FREE_KINDS = (APPROVAL, NOTICE, VERIFIED, FIRST_CONTACT)
SUMMARY_OF = {APPROVAL: "change", ADVICE: "advice", NOTICE: "result", VERIFIED: "result", FIRST_CONTACT: "first_contact"}
LETTER_OF = {APPROVAL: "approval", NOTICE: "notice", VERIFIED: "verified"}
SWITCHES = ("messages", "all")
MAX_DETAIL = 240
FIRST_URL = "https://smba.trafficmanager.net/teams/"  # the Connector that Teams names for an app that has no region yet; a person's own region is kept once they write or add the app
NONCE_SECONDS = (900, 14 * 86400)


def _short(text: object, limit: int = MAX_DETAIL) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 3].rstrip() + "..."


def _week_start(now: dt.datetime) -> dt.datetime:
    """Monday 00:00 UTC of the ISO week that holds `now`."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=now.weekday())


def contacts_of(people: People, reader: str = "") -> tuple[str, ...]:
    """The people who are responsible for Meternaut, for the last line of a card: those with the role owner or ops (or everybody listed, when none has one), each as a name with the address, in
    plain text. A card names the first of them, and never the person who reads it (`reader` is that person's object id) when somebody else is listed, as the page and the letters do."""
    chosen = [p for p in people.persons if "ops" in p.roles or "owner" in p.roles] or list(people.persons)
    others = [p for p in chosen if p.oid.lower() != reader.lower()] if reader else chosen
    return tuple(contact_text(p.name, p.mail) for p in (others or chosen)[:3])


def may_answer(principal, plan: PlanRecord) -> bool:
    """Only a person named in the plan may answer it, checked by directory object id, and with the role approver. Advice changes nothing in Azure, so the owner may answer it too."""
    named = principal.oid.lower() in {a.lower() for a in plan.approvers}
    return named and (principal.has("approver") or (plan.family == ADVISE and principal.has("owner")))


def nonce_seconds(plan: PlanRecord, now: dt.datetime) -> int:
    """How long the one-time token of a card lives: until the plan expires, and not less than 15 minutes or more than 14 days."""
    low, high = NONCE_SECONDS
    try:
        left = int((parse(plan.expires_at) - now).total_seconds())
    except ValueError:
        left = low
    return max(low, min(high, left))


class Offers:
    def __init__(self, store: Store, people: People, references: ReferenceTable | MemoryReferences, connector: Connector, tenant_id: str, base_url: str,
                 clock: Callable[[], dt.datetime], redact: Callable[[str], str], ids: Callable[[], str] = lambda: uuid.uuid4().hex[:12]) -> None:
        self.store, self.people, self.references, self.connector = store, people, references, connector
        self.tenant_id, self.base_url, self.clock, self.redact, self.ids = tenant_id, base_url, clock, redact, ids

    # -- the round -----------------------------------------------------------------------------------------------------------------------------

    def run(self) -> int:
        """One round: the cards that are due, for the open requests and for the changes of the last days. Returns how many tries it made. It never raises: a card that cannot be sent is a
        record, and the round goes on."""
        tries = 0
        now = self.clock()
        try:
            for plan in self.store.plans_open():
                if plan.state != "open" or parse(plan.expires_at) <= now:
                    continue
                case = self.store.case_get(plan.case_id)
                for oid in plan.approvers:
                    tries += self._safely("a card about a request", lambda oid=oid, plan=plan, case=case: self._request(oid, plan, case))
            since = now - dt.timedelta(days=RESULT_DAYS)
            for action in self.store.actions_recent(10):
                moment = action.finished_at or action.queued_at
                if action.state in ("done", "failed", "verified") and moment and parse(moment) >= since:
                    plan = self.store.plan_get(action.plan_id)
                    case = self.store.case_get(action.case_id)
                    if plan is not None:
                        for oid in plan.approvers:
                            tries += self._safely("a card about a change", lambda oid=oid, plan=plan, action=action, case=case: self._change(oid, plan, action, case))
        except Exception as error:  # noqa: BLE001 (the timer must go on)
            LOG.error(self.redact(f"the cards could not be offered: {type(error).__name__}"))
        return tries

    def _safely(self, what: str, work: Callable[[], int]) -> int:
        try:
            return work()
        except Exception as error:  # noqa: BLE001 (a card never stops the round)
            LOG.error(self.redact(f"{what} could not be sent: {type(error).__name__}: {error}"))
            return 0

    # -- what is due ---------------------------------------------------------------------------------------------------------------------------

    def _tries(self, person: Person, kind: str, plan_id: str | None) -> list[MailRecord]:
        return [m for m in self.store.mails_since(person.oid, EPOCH) if m.kind == kind and (plan_id is None or m.plan_id == plan_id)]

    def _letter_sent(self, person: Person, kind: str, plan_id: str) -> bool:
        letter = LETTER_OF.get(kind)
        return letter is not None and any(m.kind == letter and m.status == "sent" and m.plan_id == plan_id for m in self.store.mails_since(person.oid, EPOCH))

    def _due(self, person: Person, kind: str, plan_id: str) -> bool:
        """True when a card of this kind is to be tried now: none was sent, the last try is old enough, the tries are not used up, and no letter went for the same request."""
        tries = self._tries(person, kind, plan_id)
        if any(m.status == "sent" for m in tries) or len(tries) >= MAX_TRIES or self._letter_sent(person, kind, plan_id):
            return False
        return not tries or self.clock() - parse(max(m.sent_at for m in tries)) >= dt.timedelta(minutes=RETRY_MINUTES)

    def _wants_cards(self, person: Person) -> tuple[bool, object]:
        settings = self.store.settings_get(person.oid)
        return settings.channel == "teams", settings

    def _hold(self, person: Person, settings, kind: str, now: dt.datetime) -> str | None:
        for name in SWITCHES:
            if switches.pulled(self.store, name):
                return f'The switch "{name}" is pulled, or cannot be read.'
        if settings.paused_until:
            try:
                until = parse(settings.paused_until)
            except ValueError:
                return "The date until which this person paused messages cannot be read."
            if until > now:
                return f"This person paused messages until {settings.paused_until}."
        if kind not in FREE_KINDS:
            sent = [m for m in self.store.mails_since(person.oid, _week_start(now).strftime(TIME_FORMAT)) if m.status == "sent" and m.kind not in FREE_KINDS and m.kind not in BUDGET_FREE_KINDS]
            if len(sent) >= settings.weekly_budget:
                return f"The weekly budget of {settings.weekly_budget} messages is reached ({len(sent)} sent since Monday)."
        return None

    # -- one card ------------------------------------------------------------------------------------------------------------------------------

    def _request(self, oid: str, plan: PlanRecord, case: CaseRecord | None) -> int:
        person = self.people.by_oid(oid)
        principal = self.people.principal(oid)
        wants, settings = self._wants_cards(person) if person is not None else (False, None)
        kind = ADVICE if plan.family == ADVISE else APPROVAL
        if not wants or principal is None or not may_answer(principal, plan) or not self._due(person, kind, plan.plan_id):  # type: ignore[arg-type]
            return 0
        now = self.clock()
        held = self._hold(person, settings, kind, now)  # type: ignore[arg-type]
        if held is not None:
            return self._record(person, kind, plan.plan_id, now, "held", held)  # type: ignore[arg-type]

        def card() -> dict:
            # The switches that hold the answer that approves: `all`, which is checked above, and `changes` for a change (the page and the brief say so in the same way).
            paused = plan.family != ADVISE and switches.pulled(self.store, "changes")
            brief = build_brief(case, plan, None, self.store.decisions_of_plan(plan.plan_id), now=now, may_answer=True, changes_paused=paused)
            nonce = self.store.nonce_new(person.oid, plan.plan_id, nonce_seconds(plan, now))  # type: ignore[union-attr]
            return cards.decision_card(brief, CardContext(page_url=cards.page_url(self.base_url, plan.plan_id), nonce=nonce, contacts=contacts_of(self.people, person.oid)))  # type: ignore[union-attr]
        return self._deliver(person, kind, plan.plan_id, now, card)  # type: ignore[arg-type]

    def _change(self, oid: str, plan: PlanRecord, action: ActionRecord, case: CaseRecord | None) -> int:
        person = self.people.by_oid(oid)
        wants, settings = self._wants_cards(person) if person is not None else (False, None)
        if not wants:
            return 0
        kinds = (NOTICE, VERIFIED) if action.state == "verified" else (NOTICE,)
        total = 0
        for kind in kinds:
            if not self._due(person, kind, plan.plan_id):  # type: ignore[arg-type]
                continue
            now = self.clock()
            held = self._hold(person, settings, kind, now)  # type: ignore[arg-type]
            if held is not None:
                total += self._record(person, kind, plan.plan_id, now, "held", held)  # type: ignore[arg-type]
                continue

            def card() -> dict:
                brief = build_brief(case, plan, action, self.store.decisions_of_plan(plan.plan_id), now=now, may_answer=False)
                return cards.result_card(brief, CardContext(page_url=cards.page_url(self.base_url, plan.plan_id), contacts=contacts_of(self.people, person.oid)))  # type: ignore[union-attr]
            total += self._deliver(person, kind, plan.plan_id, now, card)  # type: ignore[arg-type]
        return total

    def _deliver(self, person: Person, kind: str, plan_id: str, now: dt.datetime, make_card: Callable[[], dict]) -> int:
        """Makes the card, finds the conversation, sends, and writes what came of it. Returns 1: a try was made."""
        try:
            card = make_card()
        except CardError as error:
            return self._record(person, kind, plan_id, now, "failed", f"The card could not be made: {_short(self.redact(str(error)))}")
        activity = cards.message_activity(card, SUMMARY_OF[kind])
        reference = self.references.reference_get(person.oid)
        if reference is None:
            started = self.connector.start(FIRST_URL, person.oid, self.tenant_id)
            if started.status != "sent":
                return self._record(person, kind, plan_id, now, "failed", f"Meternaut has no conversation with this person and could not start one. {started.detail}")
            reference = made(person.oid, started.id, FIRST_URL, "", self.tenant_id, now)
            self.references.reference_put(reference)
        sent = self.connector.send(reference.service_url, reference.conversation_id, activity, reference.user_id)
        if sent.status == "gone":
            self.references.reference_delete(person.oid)  # the conversation is gone: the next try starts a new one
        return self._record(person, kind, plan_id, now, "sent" if sent.status == "sent" else "failed", sent.detail)

    def _record(self, person: Person, kind: str, plan_id: str, now: dt.datetime, status: str, detail: str) -> int:
        record = MailRecord(mail_id=self.ids(), oid=person.oid, kind=kind, subject=cards.SUMMARIES[SUMMARY_OF[kind]], sent_at=stamp(now), status=status, plan_id=plan_id, detail=_short(detail))
        try:
            self.store.mail_put(record)
        except Exception as error:  # noqa: BLE001 (the card is out or held already: a failed record must not make the next round send it again at once)
            LOG.error(self.redact(f"the outcome of a card could not be written: {type(error).__name__}"))
        return 1
