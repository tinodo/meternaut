"""The cards that Meternaut sends on its own: of a request that waits for a person, of a change that ran, of a check that came after it, and the card that replaces one when its request ends. Each is
one message on the queue that a flow of Power Automate reads (cases/teamsqueue.py): the flow posts it into the chat of the person, or replaces a card with it.

It does for the people who chose Teams what mail.py and notify.py do for the letters, with the same checks in the same order and the same words for what came of each try. A person who chose e-mail
(the default) or the weekly summary gets no card; a person who chose Teams gets the card first, and the letter follows (notify.py) only when no card was sent in the first twenty minutes.

Before a card goes, in this order, the first check that fails ends the try and is written as its outcome (a record of kind `approval-card`, `advice-card`, `notice-card`, `verified-card` or
`first-contact-card`, in the store of mail records that the letters count in too):
1. the person is on the list of people, has an address there, is named on the plan, and may answer it (the role approver; for advice, the owner too);
2. held: the switch `messages` or `all` is pulled (a switch that cannot be read counts as pulled);
3. held: the person paused messages (`SettingsRecord.paused_until` is in the future);
3a. held: the person is inside their quiet hours (cases/quiet.py): nothing is written while they last, so that waiting uses up no try, and the letter waits for twenty minutes after them (notify.py);
4. held: the person's weekly budget is reached. Only the card of advice counts against it: an approval, a notice and a check are asked for or owed, as with the letters;
5. introduced: a person who was never told who writes gets the card that says so first, and the card of the request goes when that one was sent or its twelve tries are used up;
6. failed: the card or the message could not be made, or the queue did not take it. The try is written, and the letter follows after the twenty minutes.
A try that was held or failed is offered again after 15 minutes, at most 12 times. A card that was sent is never sent again for the same request, and none is sent for a request whose letter went.

When the flow has posted the card of a request it writes the Teams message to the queue `teams-posted`, and record_posted keeps it (a record of kind `card-posted`, which no count of letters sees). When
the request has ended (declined, expired, withdrawn, answered, or its approved change was made or was not made) the next round puts the card that replaces it (cards.closed_card, worded from what became
of the change) on the queue for each posted message that no closing replaced yet (a record of kind `card-closed`, tried again like a card that failed, and no message that a budget counts). An approval
that waits for the extra sign-in check, and a change that is being made or is not confirmed yet, have not ended: their card stays. No check above holds a closing back: it tells nobody anything new. A card
that was closed is not a card that was sent for a request that is open again: that request gets a new card, which closes in its turn.

`sent` means that the queue took the message; whether the person saw the card, or Teams replaced it, Meternaut cannot tell, which is why the letter is the fallback. Of a try only its outcome is written: no body, no name and no
figure of the card, and its id is the id of the message.

With TEAMS_DELIVERY=bot (cases/teamsbot.py; the queue stays the default) the same rounds send each card straight to the person through the Bot Connector, with the app's own identity, and nothing goes on the
queue: `sent` then means that Teams accepted the card, the record `card-posted` is written at once with the activity and the conversation (and the word `bot`, so that a card is replaced only by the way that
posted it), and a card is replaced by an update of that activity. A person for whom Teams says that the app is not installed, or that it was blocked, is a failed try with that plain reason, tried again
at most as often as any other, and the other approvers go on; the letter follows after the twenty minutes as ever. A bot way whose settings are missing or wrong is off: no card is tried (loop_config.TeamsWay).
AGENTS.md rule 25 (no bot) is replaced by the owner's ruling of 2026-11-13 (his plain yes of 2026-11-13) for this way, and nothing here runs unless TEAMS_DELIVERY says bot, except the test card (card_test), which goes by the settings of the bot alone.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import functools
import logging
import time
import uuid
from typing import Callable, Mapping

from . import cardlinks, cards, loop_config, people as people_mod, quiet, switches, teamsbot, teamsqueue, wiring
from .brief import Brief, build_brief, contact_text
from .cards import CardContext, CardError
from .events import History
from .http import Client, default_transport
from .identity import Identity
from .loop_config import LoopSettings
from .mail import BUDGET_FREE_KINDS, NOT_MESSAGES
from .memory_store import parse, stamp, utc_now
from .models import ADVISE, TIME_FORMAT, ActionRecord, CaseRecord, MailRecord, PlanRecord, Store
from .people import People, Person
from .redact import Redactor

LOG = logging.getLogger("meternaut.teams.offers")
EPOCH = "2000-01-01T00:00:00Z"
RETRY_MINUTES = 15  # a card that was not sent is offered again after this long
MAX_TRIES = 12  # and given up after this many tries
ROUND_SECONDS = 25  # the bot's time for the calls of one round: the letters follow the cards in the same minute, and a slow Bot Connector must not hold them back
RESULT_DAYS = 3  # the cards about a change are offered for this long after it
APPROVAL, ADVICE, NOTICE, VERIFIED, FIRST_CONTACT = "approval-card", "advice-card", "notice-card", "verified-card", "first-contact-card"
POSTED, CLOSED = "card-posted", "card-closed"
BOT = "bot"  # the last word of the detail of a `card-posted` record that the bot made
WORKING = ("queued", "running", "unknown")  # an action that is not over
FREE_KINDS = (APPROVAL, NOTICE, VERIFIED, FIRST_CONTACT)
CARD_KINDS = (*FREE_KINDS, ADVICE, CLOSED)
SUMMARY_OF = {APPROVAL: "change", ADVICE: "advice", NOTICE: "result", VERIFIED: "result", FIRST_CONTACT: "first_contact", CLOSED: "closed"}
LETTER_OF = {APPROVAL: "approval", NOTICE: "notice", VERIFIED: "verified"}
SWITCHES = ("messages", "all")
MAX_DETAIL = 240
WHY_TEAMS = "You got this because you chose Teams for my messages, and you are on my list of people."
SHORT_SENT = "The whole card did not fit in a message, so the short card went: the details are on the page."


def _short(text: object, limit: int = MAX_DETAIL) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 3].rstrip() + "..."


def _week_start(now: dt.datetime) -> dt.datetime:
    """Monday 00:00 UTC of the ISO week that holds `now`."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=now.weekday())


def _last_sent(mails: list[MailRecord], *kinds: str) -> str:
    return max((m.sent_at for m in mails if m.kind in kinds and m.status == "sent"), default="")


def _spent(tries: list[MailRecord]) -> bool:
    """True when the tries are used up, or when one of them may have put the card in Teams (a post whose answer was lost: teamsbot.NOT_RETRIED): that card is not posted again, and the letter follows."""
    return len(tries) >= MAX_TRIES or any(m.detail == teamsbot.NOT_RETRIED for m in tries)


def contacts_of(people: People, reader: str = "") -> tuple[str, ...]:
    """The people who are responsible for Meternaut, for the last line of a card: those with the role owner or ops (or everybody listed, when none has one), each as a name with the
    address, in plain text. A card names the first of them, and never the person who reads it (`reader` is that person's object id) when somebody else is listed, as the page and the letters do."""
    chosen = [p for p in people.persons if "ops" in p.roles or "owner" in p.roles] or list(people.persons)
    others = [p for p in chosen if p.oid.lower() != reader.lower()] if reader else chosen
    return tuple(contact_text(p.name, p.mail) for p in (others or chosen)[:3])


def may_answer(principal, plan: PlanRecord) -> bool:
    """Only a person named in the plan may answer it, checked by directory object id, and with the role approver. Advice changes nothing in Azure, so the owner may answer it too."""
    named = principal.oid.lower() in {a.lower() for a in plan.approvers}
    return named and (principal.has("approver") or (plan.family == ADVISE and principal.has("owner")))


class Offers:
    def __init__(self, store: Store, people: People, queue: teamsqueue.CardQueue | None, base_url: str, clock: Callable[[], dt.datetime], redact: Callable[[str], str],
                 ids: Callable[[], str] = lambda: uuid.uuid4().hex[:12], bot: teamsbot.TeamsBot | None = None) -> None:
        self.store, self.people, self.queue, self.base_url, self.clock, self.redact, self.ids, self.bot = store, people, queue, base_url, clock, redact, ids, bot

    # -- the round -----------------------------------------------------------------------------------------------------------------------------

    def run(self) -> int:
        """One round: the cards that are due, for the open requests and for the changes of the last days. Returns how many tries it made. It never raises: a card that cannot be sent is a
        record, and the round goes on."""
        tries = 0
        now = self.clock()
        if self.bot is not None:
            self.bot.client.deadline = self.bot.client.monotonic() + ROUND_SECONDS
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
            tries += self._close(now)
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
        """The tries of this kind for this request. A closed card is no sent card when the request is open again: a card counts from its last closing on, a closing from the last card on."""
        mails = [m for m in self.store.mails_since(person.oid, EPOCH) if plan_id is None or m.plan_id == plan_id]
        tries = [m for m in mails if m.kind == kind]
        if kind == CLOSED:
            return [m for m in tries if m.sent_at >= _last_sent(mails, APPROVAL, ADVICE)]
        return [m for m in tries if m.sent_at > _last_sent(mails, CLOSED)] if kind in (APPROVAL, ADVICE) else tries

    def _letter_sent(self, person: Person, kind: str, plan_id: str) -> bool:
        letter = LETTER_OF.get(kind)
        return letter is not None and any(m.kind == letter and m.status == "sent" and m.plan_id == plan_id for m in self.store.mails_since(person.oid, EPOCH))

    def _due(self, person: Person, kind: str, plan_id: str | None) -> bool:
        """True when a card of this kind is to be tried now: none was sent, the last try is old enough, the tries are not used up, and no letter went for the same request."""
        tries = self._tries(person, kind, plan_id)
        if any(m.status == "sent" for m in tries) or _spent(tries) or (plan_id is not None and self._letter_sent(person, kind, plan_id)):
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
        if quiet.inside(settings, now):
            return quiet.WAITING
        if kind not in FREE_KINDS:
            sent = [m for m in self.store.mails_since(person.oid, _week_start(now).strftime(TIME_FORMAT)) if m.status == "sent" and m.kind not in FREE_KINDS + BUDGET_FREE_KINDS + NOT_MESSAGES]
            if len(sent) >= settings.weekly_budget:
                return f"The weekly budget of {settings.weekly_budget} messages is reached ({len(sent)} sent since Monday)."
        return None

    def _introduce(self, person: Person, now: dt.datetime) -> tuple[int, bool]:
        """The card that says who writes, before the first card of a request goes to a person who chose Teams. Returns (the tries made, whether the card of the request may go now): it may when the person
        was told already (by this card or by the letter) or when the tries of this card are used up (the card of the request tells them itself), and not before the next try."""
        told = any(m.status == "sent" and m.kind in (FIRST_CONTACT, "first_contact") for m in self.store.mails_since(person.oid, EPOCH))
        if told or _spent(self._tries(person, FIRST_CONTACT, None)):
            return 0, True
        if not self._due(person, FIRST_CONTACT, None):
            return 0, False

        def card() -> dict:
            return cards.first_contact_card(person.name, self.base_url, contacts_of(self.people, person.oid), why=WHY_TEAMS)
        return 1, self._deliver(person, FIRST_CONTACT, None, now, card) == "sent"

    # -- one card ------------------------------------------------------------------------------------------------------------------------------

    def _context(self, person: Person, plan: PlanRecord, brief: Brief | None = None) -> CardContext:
        return CardContext(page_url=cards.page_url(self.base_url, plan.plan_id), contacts=contacts_of(self.people, person.oid), links=self._links(person, plan, brief) if brief is not None else {})

    def _links(self, person: Person, plan: PlanRecord, brief: Brief) -> dict[str, str]:
        """The addresses of the answer buttons of this brief's card (cards.answers_of), each with a link token made now for this person that lives as long as the request is open. If a token cannot be
        made the card has the link to the page only."""
        wanted = cards.answers_of(brief)
        if not wanted or not plan.code:
            return {}
        try:
            seconds = (parse(plan.expires_at) - self.clock()).total_seconds()
            page = cards.page_url(self.base_url, plan.plan_id)
            return {answer: cardlinks.answer_url(page, answer, plan.code, cardlinks.mint(self.store.nonce_new, person.oid, plan.plan_id, plan.code, answer, twice, seconds))
                    for answer, twice in wanted}
        except Exception as error:  # noqa: BLE001 (a card without buttons is better than no card)
            LOG.error(self.redact(f"the buttons of a card could not be made: {type(error).__name__}"))
            return {}

    def _request(self, oid: str, plan: PlanRecord, case: CaseRecord | None) -> int:
        person = self.people.by_oid(oid)
        principal = self.people.principal(oid)
        wants, settings = self._wants_cards(person) if person is not None and person.mail else (False, None)
        kind = ADVICE if plan.family == ADVISE else APPROVAL
        if not wants or principal is None or not may_answer(principal, plan) or not self._due(person, kind, plan.plan_id):  # type: ignore[arg-type]
            return 0
        now = self.clock()
        if quiet.inside(settings, now):
            return 0  # the person's quiet hours: nothing is tried and nothing is written, so that waiting uses up no try; the round after the hours sends it
        held = self._hold(person, settings, kind, now)  # type: ignore[arg-type]
        if held is not None:
            return self._record(person, kind, plan.plan_id, now, "held", held)  # type: ignore[arg-type]
        tries, told = self._introduce(person, now)  # type: ignore[arg-type]
        if not told:
            return tries

        @functools.cache
        def brief() -> Brief:
            # The switches that hold the answer that approves: `all`, which is checked above, and `changes` for a change (the page and the brief say so in the same way).
            paused = plan.family != ADVISE and switches.pulled(self.store, "changes")
            return build_brief(case, plan, None, self.store.decisions_of_plan(plan.plan_id), now=now, may_answer=True, changes_paused=paused, viewer=person.oid)  # type: ignore[union-attr]

        @functools.cache
        def with_buttons() -> CardContext:
            return self._context(person, plan, brief())  # type: ignore[arg-type]
        self._deliver(person, kind, plan.plan_id, now, lambda: cards.decision_card(brief(), with_buttons()),
                      lambda: cards.minimal_card(brief(), self._context(person, plan)))  # type: ignore[arg-type]
        return tries + 1

    def _change(self, oid: str, plan: PlanRecord, action: ActionRecord, case: CaseRecord | None) -> int:
        person = self.people.by_oid(oid)
        wants, settings = self._wants_cards(person) if person is not None and person.mail else (False, None)
        if not wants:
            return 0
        kinds = (NOTICE, VERIFIED) if action.state == "verified" else (NOTICE,)
        total = 0
        for kind in kinds:
            if not self._due(person, kind, plan.plan_id):  # type: ignore[arg-type]
                continue
            now = self.clock()
            if quiet.inside(settings, now):
                continue  # the person's quiet hours: nothing is tried and nothing is written
            held = self._hold(person, settings, kind, now)  # type: ignore[arg-type]
            if held is not None:
                total += self._record(person, kind, plan.plan_id, now, "held", held)  # type: ignore[arg-type]
                continue
            tries, told = self._introduce(person, now)  # type: ignore[arg-type]
            total += tries
            if not told:
                continue

            @functools.cache
            def brief(now=now) -> Brief:
                return build_brief(case, plan, action, self.store.decisions_of_plan(plan.plan_id), now=now, may_answer=False)
            self._deliver(person, kind, plan.plan_id, now, lambda: cards.result_card(brief(), self._context(person, plan)),  # type: ignore[arg-type]
                          lambda: cards.minimal_card(brief(), self._context(person, plan)))  # type: ignore[arg-type]
            total += 1
        return total

    def _close(self, now: dt.datetime) -> int:
        """Replaces the card of each ended request, for each posted message that no closing replaced yet (cards.closed_card). Returns how many tries it made."""
        tries = 0
        for person in self.people.persons:
            mails = self.store.mails_since(person.oid, EPOCH)
            for plan_id in {m.plan_id for m in mails if m.kind == POSTED}:
                closed = _last_sent([m for m in mails if m.plan_id == plan_id], CLOSED)
                posted = [m for m in mails if m.kind == POSTED and m.plan_id == plan_id and m.sent_at > closed]
                if posted:
                    tries += self._safely("a card that closes", lambda person=person, plan_id=plan_id, posted=posted: self._replace(person, plan_id, posted, now))
        return tries

    def _replace(self, person: Person, plan_id: str, posted: list[MailRecord], now: dt.datetime) -> int:
        plan, action = self.store.plan_get(plan_id), self.store.action_get(plan_id)
        if plan is None or plan.state in ("open", "approved") or (action is not None and action.state in WORKING) or not self._due(person, CLOSED, plan_id):
            return 0
        brief = build_brief(self.store.case_get(plan.case_id), plan, action, self.store.decisions_of_plan(plan_id), now=now)
        tried = 0
        for m in posted:
            parts = m.detail.split()
            if (parts[2:] == [BOT]) != (self.bot is not None):
                continue  # a card that the other way posted is replaced by that way or not at all
            tried += 1
            self._deliver(person, CLOSED, plan_id, now, lambda: cards.closed_card(brief, self._context(person, plan)), update=parts[0], conversation=parts[1] if len(parts) > 1 else "")
        return tried

    def _message(self, person: Person, kind: str, delivery_id: str, make_card: Callable[[], dict], make_short: Callable[[], dict] | None, **extra: object) -> tuple[str | None, str]:
        """(the text of the message, a note for the record), or (None, why not). The address is the one that the list of people holds, and nothing else; a card that is too big for its message is
        replaced by the short one, and one that cannot be made is a failed try. `extra` is what teamsqueue.render takes besides (`request`, `update`)."""
        listed = self.people.by_oid(person.oid)
        if listed is None or not listed.mail or listed.mail.lower() not in self.people.allowed_addresses():
            return None, "This person has no address on the list of people, so no card was sent."
        title = cards.SUMMARIES[SUMMARY_OF[kind]]
        try:
            try:
                return teamsqueue.render(delivery_id, listed.mail, title, make_card(), **extra), ""
            except (cards.CardTooLarge, teamsqueue.TooBig):
                if make_short is None:
                    raise
                return teamsqueue.render(delivery_id, listed.mail, title, make_short(), **extra), SHORT_SENT
        except (CardError, teamsqueue.MessageError) as error:
            return None, f"The card could not be made: {_short(self.redact(str(error)))}"

    def _deliver(self, person: Person, kind: str, plan_id: str | None, now: dt.datetime, make_card: Callable[[], dict], make_short: Callable[[], dict] | None = None,
                 update: str | None = None, conversation: str = "") -> str:
        """Makes the message, puts it on the queue and writes what came of it. Returns `sent` or `failed`. The card of a request that waits carries the request, so that the flow can say which message it
        posted; `update` (a Teams message id) makes it a card that replaces that message. With the bot way (`conversation` is the one that holds the message) the card goes straight to Teams instead."""
        if self.bot is not None:
            return self._deliver_bot(person, kind, plan_id, now, make_card, make_short, update, conversation)
        delivery_id = self.ids()
        extra = {"request": plan_id} if kind in (APPROVAL, ADVICE) else {"update": update} if update else {}
        text, note = self._message(person, kind, delivery_id, make_card, make_short, **extra)
        if text is None:
            self._record(person, kind, plan_id, now, "failed", note, delivery_id)
            return "failed"
        put = self.queue.put(text)
        status = "sent" if put.status == "sent" else "failed"
        self._record(person, kind, plan_id, now, status, f"{note} {put.detail}".strip(), delivery_id)
        return status

    def _deliver_bot(self, person: Person, kind: str, plan_id: str | None, now: dt.datetime, make_card: Callable[[], dict], make_short: Callable[[], dict] | None, update: str | None,
                     conversation: str) -> str:
        """The card goes to the person through the bot (cases/teamsbot.py), or replaces the activity `update` in `conversation`. What came of it is written as the outcome, in the plain words of
        teamsbot.REASONS; a card of a request that waits is kept at once with the activity and the conversation, so that it can be replaced when the request ends."""
        delivery_id, note = self.ids(), ""
        if self.bot.late():  # type: ignore[union-attr]
            return "failed"  # the time of this round is used up: nothing is written, so that waiting uses up no try, and the card goes in the next round
        try:
            try:
                card = make_card()
            except cards.CardTooLarge:
                if make_short is None:
                    raise
                card, note = make_short(), SHORT_SENT
            summary = cards.SUMMARIES[SUMMARY_OF[kind]]
            if update:
                self.bot.update(conversation, update, card, summary)  # type: ignore[union-attr]
            else:
                conversation, update = self.bot.send(person.oid, card, summary)  # type: ignore[union-attr]
        except CardError as error:
            self._record(person, kind, plan_id, now, "failed", f"The card could not be made: {_short(self.redact(str(error)))}", delivery_id)
            return "failed"
        except teamsbot.BotError as error:
            self._record(person, kind, plan_id, now, "failed", str(error), delivery_id)
            return "failed"
        self._record(person, kind, plan_id, now, "sent", f"{note} {teamsbot.SENT}".strip(), delivery_id)
        if kind in (APPROVAL, ADVICE):
            try:
                self.store.mail_put(MailRecord(mail_id=self.ids(), oid=person.oid, kind=POSTED, subject="A card was posted", sent_at=stamp(now), status="posted", plan_id=plan_id,
                                               detail=f"{update} {conversation} {BOT}"))
            except Exception as error:  # noqa: BLE001 (the card is out: it cannot be replaced later, and that is all)
                LOG.error(self.redact(f"the ids of a posted card could not be kept: {type(error).__name__}"))
        return "sent"

    def _record(self, person: Person, kind: str, plan_id: str | None, now: dt.datetime, status: str, detail: str, mail_id: str | None = None) -> int:
        record = MailRecord(mail_id=mail_id or self.ids(), oid=person.oid, kind=kind, subject=cards.SUMMARIES[SUMMARY_OF[kind]], sent_at=stamp(now), status=status, plan_id=plan_id,
                            detail=_short(detail))
        try:
            self.store.mail_put(record)
        except Exception as error:  # noqa: BLE001 (the card is out or held already: a failed record must not make the next round send it again at once)
            LOG.error(self.redact(f"the outcome of a card could not be written: {type(error).__name__}"))
        return 1


def build_bot(settings: LoopSettings, assertion: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic, clock: Callable[[], dt.datetime]) -> teamsbot.TeamsBot:
    """The bot of the settings (TEAMS_DELIVERY=bot, complete): `assertion` is the token of the managed identity of the bot for a resource, and the client has a list of calls of its own."""
    client = teamsbot.new_client(settings.teams, redact, transport=transport, sleep=sleep, monotonic=monotonic)
    return teamsbot.TeamsBot(settings.teams, assertion, client, clock)


def cards_hook(settings: LoopSettings, store: Store, people: People, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic,
               clock: Callable[[], dt.datetime], assertion: Callable[[str], str] | None = None) -> Callable[[], int]:
    """What the timer calls every minute when the cards are on: one round of cards, which returns how many tries it made. It never raises. The way is the queue (TEAMS_CARDS_QUEUE, in the storage
    account of the records, with a client of its own whose list of calls holds the one POST of a message to that queue) or, when the settings say TEAMS_DELIVERY=bot and `assertion` is the token of the
    bot's identity, the bot (build_bot)."""
    if settings.teams.way == "bot" and assertion is not None:
        return Offers(store, people, None, settings.base_url, clock, redact, bot=build_bot(settings, assertion, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)).run
    if not settings.cards_queue:
        raise ValueError("no queue is set for the cards")
    client = Client(teamsqueue.queue_calls(settings.store_account, settings.cards_queue), redact, transport=transport, sleep=sleep, monotonic=monotonic)
    queue = teamsqueue.CardQueue(client, token, settings.store_account, settings.cards_queue, redact, clock)
    return Offers(store, people, queue, settings.base_url, clock, redact).run


def card_test(env: Mapping[str, str], request_id: str, *, transport=default_transport, sleep=time.sleep, monotonic=time.monotonic, clock: Callable[[], dt.datetime] = utc_now, fetch=None) -> bool:
    """The proof of the way through the bot, started by the control message `teams-card-test`: one test card (no request, no figure, no name of the estate) to the first person with the role owner,
    replaced at once by a closing card. The History says only what came of each step (`teams.test.step`: the step, whether it worked, the HTTP status, the number of an error of Microsoft Entra, the error
    code word of Teams (letters alone) and one plain word for why not) and, at the end, `teams.test.finished`. It goes by the settings of the bot alone (loop_config.bot_way: the Teams settings and the sign-in settings are complete) and not by
    TEAMS_DELIVERY, so that the way is proved before the delivery is switched to `bot`; it sends nothing when they are not complete, and nothing while the switch `messages` or `all` is pulled.
    It never raises."""
    redact = Redactor()
    history = History(uuid.uuid4().hex, request_id, clock, redact)

    def finish(ok: bool, **why: object) -> bool:
        history.emit("teams.test.finished", ok=ok, **why)
        return ok

    try:
        settings = loop_config.load(env)
        way = loop_config.bot_way(env, settings.signin_tenant_id) if settings else None
        if way is None or way.way != "bot":
            return finish(False, reason="off")
        settings = dataclasses.replace(settings, teams=way)
        people = people_mod.load(env)
        owner = next(iter(people.with_role("owner")), None)
        if owner is None:
            return finish(False, reason="no-owner")
        options = {"sleep": sleep, **({"fetch": fetch} if fetch else {})}
        store = wiring.build_store(settings, Identity(env, **options).token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        if switches.pulled(store, *SWITCHES):
            return finish(False, reason="held")
        assertion = Identity({**env, "AZURE_CLIENT_ID": settings.teams.identity_client_id}, **options).token
        bot = build_bot(settings, assertion, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        contacts, summary = contacts_of(people, owner.oid), cards.SUMMARIES["test"]
    except Exception as error:  # noqa: BLE001 (a control message is not tried again: the History says that it did not run)
        LOG.error(redact(f"the test of the Teams cards could not start: {type(error).__name__}"))
        return finish(False, reason="other")

    def step(name: str, work: Callable[[], object]) -> object:
        try:
            found = work()
        except teamsbot.BotError as error:
            history.emit("teams.test.step", step=error.step, ok=False, reason=error.reason, **({"status": error.status} if error.status else {}),
                         **({"aadsts": error.aadsts} if error.aadsts else {}), **({"code": error.code} if error.code else {}))
            raise
        history.emit("teams.test.step", step=name, ok=True, **({"status": bot.status} if bot.status else {}))
        return found

    try:
        step("token", bot.token)
        conversation = str(step("create", lambda: bot.create(owner.oid)))
        activity = str(step("send", lambda: bot.post(conversation, cards.probe_card(contacts=contacts), summary)))
        step("update", lambda: bot.update(conversation, activity, cards.probe_card(True, contacts=contacts), summary))
    except teamsbot.BotError:
        return finish(False)
    except Exception as error:  # noqa: BLE001 (the card could not be made, or anything else: the History still gets its last line)
        LOG.error(redact(f"the test of the Teams cards failed: {type(error).__name__}"))
        return finish(False, reason="other")
    return finish(True)


def teams_status(settings: LoopSettings, store: Store, people: People, now: dt.datetime) -> tuple[str, str]:
    """The two sentences of the block "Teams cards" of the Operations page: which way the cards go, and what the last try came to. Counts only: no name and no id."""
    way = settings.teams
    went = {"bot": "The cards go straight to Teams through the Bot Connector, with the identity of the function app.", "off": way.why}.get(
        way.way, "The cards go on a queue that a flow of Power Automate reads and posts." if settings.cards_queue else "The Teams cards are off: no queue is set.")
    try:
        since = stamp(now - dt.timedelta(days=RESULT_DAYS))
        latest = [max(tries, key=lambda m: m.sent_at) for tries in ([m for m in store.mails_since(p.oid, since) if m.kind in CARD_KINDS and m.status in ("sent", "failed")]
                                                                      for p in people.persons) if tries]
    except Exception as error:  # noqa: BLE001 (the page says that it cannot tell)
        LOG.error(f"the last result of the Teams cards could not be read: {type(error).__name__}")
        return went, "Last result: it cannot be read now."
    if not latest:
        return went, f"Last result: no card was tried in the last {RESULT_DAYS} days."

    def reason_of(m: MailRecord) -> str:
        return "ok" if m.status == "sent" else teamsbot.REASON_OF.get(m.detail, "other")
    newest, refused = reason_of(max(latest, key=lambda m: m.sent_at)), sum(reason_of(m) in ("not-installed", "blocked") for m in latest)
    said = {"ok": "ok", "unauthorized": "identity error", "network": "no answer from Teams", "throttled": "Teams asked the function app to slow down", "other": "the last card was not sent"}
    return went, "Last result: " + (said.get(newest) or f"the Teams app is not installed for, or blocked by, {refused} approver{'' if refused == 1 else 's'}") + "."


def record_posted(text: str, store: Store, people: People, clock: Callable[[], dt.datetime]) -> str:
    """The flow says that it posted a card (a message of the queue teams-posted): keeps which Teams message it is, for the person and the request that the message names, so that the card can be
    replaced when the request ends. Returns what it did, in words. A message that is not what the flow writes, or names no approver of a request, is refused. A store that cannot be written raises, so
    that the host tries again (five times in all)."""
    try:
        request, to, message, conversation = teamsqueue.read_posted(text)
    except teamsqueue.MessageError as error:
        return f"refused: {error}"
    plan = store.plan_get(request)
    person = next((p for p in people.persons if (p.mail or "").lower() == to.lower()), None)
    if plan is None or person is None or person.oid.lower() not in {a.lower() for a in plan.approvers}:
        return "refused: no request of that person"
    store.mail_put(MailRecord(mail_id=uuid.uuid4().hex[:12], oid=person.oid, kind=POSTED, subject="A card was posted", sent_at=stamp(clock()), status="posted", plan_id=request,
                              detail=f"{message} {conversation}"))
    return "kept"
