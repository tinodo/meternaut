"""The sender: one letter to one person, from the one shared mailbox, through Microsoft Graph `sendMail`.

`mail_calls(sender)` is the one call that this module makes, as the entry that the list of allowed calls of http.py needs. The call is a POST to
`https://graph.microsoft.com/v1.0/users/<sender>/sendMail`, made with the token of the app's managed identity. The identity holds no Microsoft Entra
permission for mail: Exchange Online's role `Application Mail.Send`, limited to the one shared mailbox (tools/exchange-setup.py), is its only right.

Graph answers 202 Accepted with no body. That means Graph took the letter, not that it arrived: delivery is proved by receipt in the recipient's inbox
(build plan, check C4), never by this call. The message carries two headers: `x-ai-generated: true`, the machine-readable mark of the AI label, and
`x-auto-response-suppress: All`, which asks Exchange and Outlook for no automatic replies and receipts. The message is saved in the Sent Items of the mailbox.

Kinds of letter: the notifier sends `digest` (the weekly desk), `approval` (a plan waits for an OK), `notice` (a change ran or failed), `verified` (the check
afterwards), `unsure` (the result of a change stays unknown), `first_contact` (the one-time introduction) and `alert` (an agent safeguard stopped the investigation: cases/alerts.py); the weekly budget neither counts nor holds any of
these seven. Any other name of the shape
`[a-z][a-z0-9_-]{0,31}` is valid and counts against the weekly budget (and is not allowed for a person of the weekly desk).

Before a call the mailer checks, in this order, and the first check that fails ends the send and is written as the outcome:
1. refused: the address is empty, is not on the list of people (`People.allowed_addresses`), or is not the address of that person on the list.
   Only the address of the list is ever used as the recipient. A letter has no recipient of its own, so it cannot name another one.
2. refused: the kind of letter or the subject is not valid.
3. held: the switch `messages` or the switch `all` is pulled. A switch that cannot be read counts as pulled.
4. held: the person paused messages (`SettingsRecord.paused_until` is in the future).
4a. held: the person is inside their quiet hours (`SettingsRecord.quiet_from` to `quiet_to`, by the clock of their time zone: cases/quiet.py). Every kind of letter waits, an approval
   letter and the letter of a trip included: nothing that Meternaut sends is urgent, so nothing goes around the hours. The callers that offer a letter again (notify.py) look at the hours first
   and write nothing while they last, so that waiting uses up no try; the one that gets here records the hold once, with the words of quiet.WAITING, and the timer sends the letter
   after the hours (notify.waiting_hook for the weekly summary and the letter of a trip; the rounds of notify.hooks for the others).
5. held: the person's weekly budget (`SettingsRecord.weekly_budget`) is reached. It counts the messages of the person with the status sent since Monday
   00:00 UTC of the current ISO week. The kinds of BUDGET_FREE_KINDS (`approval`, `first_contact`, `notice`, `verified`, `unsure`, `digest`, `alert`) are not counted
   against the budget and are not held by it: they ask for an OK, introduce Meternaut once, tell a person the outcome of a decision of theirs (an
   approver must always be told), or are the weekly desk itself, which is what a budget of 0 leaves (docs/experience/06 and 08). Every other kind
   counts and can be held. A record of NOT_MESSAGES (`card-closed`, a card that closes itself: cases/offers.py) is no message and is not counted.
6. held: the person chose the weekly desk (`SettingsRecord.channel == "desk"`) and the kind is not `digest`. The other free kinds are held here too.
Settings or records that cannot be read hold the letter as well. A held letter is not queued here: the caller decides whether to offer it again.

The outcome is written with `Store.mail_put` and nothing else of the letter is kept: no body, no address. Status `failed` is not always "not sent": after a
network error or a 5xx answer the letter may have been taken, so the mailer does not retry it (only a 429, which Graph gives before it takes a letter) and
the detail says to look at the Sent Items of the mailbox first.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

from . import quiet
from .http import Client, HttpError, Refused
from .letters import Letter
from .models import TIME_FORMAT, MailRecord, Store
from .people import People, Person

GRAPH_RESOURCE = "https://graph.microsoft.com"
SENDER = re.compile(r"^[A-Za-z0-9._-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,24}$")
KIND = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
BUDGET_FREE_KINDS = ("approval", "first_contact", "notice", "verified", "unsure", "digest", "alert")
NOT_MESSAGES = ("card-closed",)  # a card that closes itself is edited in place (cases/offers.py): no message, so no budget counts it
DESK_KINDS = ("digest",)
SWITCHES = ("messages", "all")
RETRY_ONLY = frozenset({429})
MAX_DETAIL = 240
LOG = logging.getLogger("meternaut.mail")


def _url(sender: str) -> str:
    if not isinstance(sender, str) or not SENDER.fullmatch(sender):
        raise ValueError("the sender is not an address")
    return f"{GRAPH_RESOURCE}/v1.0/users/{sender}/sendMail"


def mail_calls(sender: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The one call that the mailer makes: the entry for the list of calls that the HTTP client allows."""
    return (("POST", re.compile(re.escape(_url(sender)), re.I)),)


@dataclass(frozen=True)
class MailResult:
    status: str  # sent (Graph accepted it, which is not delivery), held, refused or failed
    detail: str  # plain words


def _stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime(TIME_FORMAT)


def _week_start(now: dt.datetime) -> dt.datetime:
    """Monday 00:00 UTC of the ISO week that holds `now`."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=now.weekday())


def _short(text: object, limit: int = MAX_DETAIL) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 3].rstrip() + "..."


def _one_line(text: object) -> bool:
    """Whether a subject is one line of visible text: not empty, and without a control, a format (direction mark, zero-width) or a line or paragraph separator character."""
    return isinstance(text, str) and bool(text.strip()) and not any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in text)


class Mailer:
    def __init__(self, sender: str, client: Client, token: Callable[[str], str], people: People, store: Store, clock: Callable[[], dt.datetime],
                 redact: Callable[[str], str], ids: Callable[[], str]) -> None:
        self.url = _url(sender)
        self.sender, self.client, self.token, self.people, self.store, self.clock, self.redact, self.ids = sender, client, token, people, store, clock, redact, ids

    def send(self, person: Person, letter: Letter, kind: str, plan_id: str | None = None) -> MailResult:
        """Sends `letter` to `person` if every check allows it, and writes the outcome. It does not raise for a problem of the send.

        The status `sent` means that Graph accepted the letter (202). Delivery is proved by receipt in the inbox, not by this call. The kinds of
        BUDGET_FREE_KINDS (approval, first_contact, notice, verified, unsure, digest, alert) are neither counted against the weekly budget nor held by it; every other
        kind is. With a budget of 0 only those other kinds are held: the weekly desk (the digest) still goes.
        """
        now = self.clock()
        now = now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)
        listed = self.people.by_oid(person.oid)
        result = self._refusal(person, listed, letter, kind) or self._hold(listed, kind, now)
        if result is None:
            result = self._post(listed.mail, letter)
        return self._record(person, listed, letter, kind, plan_id, now, result)

    def _refusal(self, person: Person, listed: Person | None, letter: Letter, kind: str) -> MailResult | None:
        address = (person.mail or "").strip().lower()
        if not address:
            return MailResult("refused", "This person has no address.")
        if address not in self.people.allowed_addresses():
            return MailResult("refused", "This address is not on the list of people.")
        if listed is None or listed.mail.strip().lower() != address:
            return MailResult("refused", "This person is not the person that the list holds for this address.")
        if not isinstance(kind, str) or not KIND.fullmatch(kind):
            return MailResult("refused", "The kind of letter is not valid.")
        if not _one_line(letter.subject):
            return MailResult("refused", "The subject is empty or is not one line.")
        return None

    def _hold(self, listed: Person, kind: str, now: dt.datetime) -> MailResult | None:
        for name in SWITCHES:
            try:
                pulled = self.store.switch_get(name).paused
            except Exception as error:  # noqa: BLE001 (a switch that cannot be read counts as pulled)
                LOG.error(self.redact(f"mail: the switch {name} could not be read: {type(error).__name__}"))
                return MailResult("held", "A switch could not be read, so it counts as pulled.")
            if pulled:
                return MailResult("held", f'The switch "{name}" is pulled.')
        try:
            settings = self.store.settings_get(listed.oid)
            if settings.paused_until:
                try:
                    until = dt.datetime.strptime(settings.paused_until, TIME_FORMAT).replace(tzinfo=dt.timezone.utc)
                except ValueError:
                    return MailResult("held", "The date until which this person paused messages cannot be read.")
                if until > now:
                    return MailResult("held", f"This person paused messages until {settings.paused_until}.")
            if quiet.inside(settings, now):
                return MailResult("held", quiet.WAITING)
            if kind not in BUDGET_FREE_KINDS:
                sent = [m for m in self.store.mails_since(listed.oid, _stamp(_week_start(now))) if m.status == "sent" and m.kind not in BUDGET_FREE_KINDS + NOT_MESSAGES]
                if len(sent) >= settings.weekly_budget:
                    return MailResult("held", f"The weekly budget of {settings.weekly_budget} messages is reached ({len(sent)} sent since Monday).")
            if settings.channel == "desk" and kind not in DESK_KINDS:
                return MailResult("held", "This person gets the weekly desk only.")
        except Exception as error:  # noqa: BLE001 (settings that cannot be read hold the letter)
            LOG.error(self.redact(f"mail: the settings or the record of messages could not be read: {type(error).__name__}"))
            return MailResult("held", "The settings or the record of messages could not be read, so nothing was sent.")
        return None

    def _post(self, address: str, letter: Letter) -> MailResult:
        try:
            token = self.token(GRAPH_RESOURCE)
        except Exception as error:  # noqa: BLE001 (whatever the reason, there is no call without a token)
            return MailResult("failed", _short(self.redact(f"No token for Graph: {type(error).__name__}: {error}")))
        if not isinstance(token, str) or not token or any(ord(ch) <= 32 or ord(ch) == 127 for ch in token):
            return MailResult("failed", "No token for Graph: the identity gave an empty answer or one that is not a token.")
        message = {
            "subject": letter.subject,
            "body": {"contentType": "HTML", "content": letter.html},
            "toRecipients": [{"emailAddress": {"address": address}}],
            "internetMessageHeaders": [{"name": "x-ai-generated", "value": "true"}, {"name": "x-auto-response-suppress", "value": "All"}],
        }
        try:
            self.client.request("POST", self.url, headers={"Authorization": f"Bearer {token}"}, body={"message": message, "saveToSentItems": True},
                                retry_statuses=RETRY_ONLY, retry_network=False)
        except (HttpError, Refused) as error:
            text = _short(self.redact(str(error).replace(token, "[redacted]")))
            if isinstance(error, HttpError) and (error.status == 0 or error.status >= 500):
                return MailResult("failed", f"{text} The letter may have been taken: look at the Sent Items of the mailbox before it is sent again.")
            return MailResult("failed", text)
        return MailResult("sent", "Graph accepted the letter (202). That is not delivery: only receipt in the inbox shows that it arrived.")

    def _record(self, person: Person, listed: Person | None, letter: Letter, kind: str, plan_id: str | None, now: dt.datetime, result: MailResult) -> MailResult:
        record = MailRecord(mail_id=self.ids(), oid=listed.oid if listed else _short(person.oid, 64), kind=kind if isinstance(kind, str) and KIND.fullmatch(kind) else "unknown",
                            subject=_short(letter.subject, 200), sent_at=_stamp(now), status=result.status, plan_id=_short(plan_id, 64) if plan_id else None,
                            detail=_short(result.detail))
        try:
            self.store.mail_put(record)
        except Exception as error:  # noqa: BLE001 (the letter is out or held already: a failed record must not make the caller send it again)
            LOG.error(self.redact(f"mail: the outcome could not be written: {type(error).__name__}"))
            return MailResult(result.status, _short(f"{result.detail} The record of it could not be written."))
        return result
