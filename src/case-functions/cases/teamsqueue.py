"""A Teams card as one message on a private Storage queue: what is written, how it must fit and how it is put there.

Meternaut has no bot in Teams: no Azure Bot resource, no Teams app, no app registration, no Microsoft Graph permission and no endpoint that Teams calls. A card reaches a person like this.
Meternaut puts one message on the queue `teams-cards` (the setting TEAMS_CARDS_QUEUE) of the storage account of the base, with the app's managed identity and no key: the app already holds
Storage Queue Data Contributor on the account, and the account takes traffic only through its private endpoints. A flow of Power Automate reads the queue through the virtual network support
of the Power Platform and posts the card with the action "Post card in a chat or channel" of the Teams connector, as the Flow bot, in the chat of the person that the message names
(docs/proposals/13-teams-and-outlook.md has the whole path and says what is proved and what is not).

The message is one JSON text in UTF-8, not base64, and at most MAX_BYTES bytes:

    {"v": 1, "id": "<delivery id>", "to": "<mail address of the person>", "title": "<short plain title>", "card": {<Adaptive Card 1.4>}}

`id` is the id of the record that Meternaut writes about the try (cases/offers.py), so that a run of the flow and the record can be put side by side. `to` is the address that the list of people
holds for the person, and never a text of the estate. `title` is the fixed words of a notification (cards.SUMMARIES), with no resource name and no amount. `card` has one link, to the page
of its request, and nothing to fill in: the action that posts it takes no answer. A card that does not fit is not cut (cut JSON is not a card): offers.py puts cards.minimal_card in its
place, which holds the headline, the link and the footer.

Delivery is best effort and there is no receipt. `sent` means that the queue took the message. It does not mean that the flow read it, that the Flow bot posted it, or that the person saw it:
nothing comes back to Meternaut, and the letter follows after the time that cases/notify.py says when no card was sent. A call that failed on the network or with a 5xx answer may have
been carried out, so it is not made again here (only the answers that the service gives before it takes a message are: 429 and 503), and the record says to look at the queue first.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from dataclasses import dataclass
from email.utils import format_datetime
from typing import Callable
from xml.sax.saxutils import escape

from . import cardcheck
from .http import Client, HttpError, Refused
from .loop_config import ACCOUNT, QUEUE
from .memory_store import utc_now
from .people import ADDRESS

RESOURCE = "https://storage.azure.com/"
VERSION = "2020-12-06"  # the Queue service version; Microsoft Entra authorization needs 2017-11-09 or later (Learn, "Authorize with Microsoft Entra ID")
FORMAT = 1  # the "v" of the message
MAX_BYTES = 30000  # the whole message, as UTF-8 text
MAX_BODY_BYTES = 60000  # the XML that carries it: the queue takes 64 KiB, and a text with many ampersands grows when it is escaped
TTL_SECONDS = 24 * 3600  # a card that nobody has read in a day is of no use: the letter went long before
MAX_TITLE = 120
RETRY_ONLY = frozenset({429, 503})  # the answers that the Queue service gives before it takes a message
MAX_DETAIL = 240
ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
SENT = "The queue took the message. That is not delivery: the flow posts the card, and nothing tells Meternaut whether it arrived."
REFUSALS = {
    401: "The queue did not accept the app's token.",
    403: ("The queue refused the app: its identity needs Storage Queue Data Contributor on the storage account (a new role takes up to ten minutes to apply), and the account is reached "
          "through its queue private endpoint."),
    404: "The queue is not there: it is made with the rest of the Azure side of the cards.",
    413: "The queue says that the message is too big.",
}


class MessageError(Exception):
    """A message that is not one that may be put on the queue. The text says why and never holds a token."""


class TooBig(MessageError):
    """A message that is right in every way but its size."""


def _one_line(text: object) -> bool:
    return isinstance(text, str) and bool(text.strip()) and not any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in text)


def _body(text: str) -> str:
    return f"<QueueMessage><MessageText>{escape(text)}</MessageText></QueueMessage>"


def render(delivery_id: str, to: str, title: str, card: dict) -> str:
    """The text of the message. Raises TooBig when it is over MAX_BYTES (or its XML over MAX_BODY_BYTES), and MessageError when anything in it is not what it has to be."""
    if not isinstance(delivery_id, str) or not ID.fullmatch(delivery_id):
        raise MessageError("the delivery id is not an opaque id")
    if not isinstance(to, str) or len(to) > 254 or not ADDRESS.fullmatch(to):
        raise MessageError("the address of the person is not an address")
    if not _one_line(title) or len(title) > MAX_TITLE:
        raise MessageError("the title is not one short line")
    problems = cardcheck.check(card)
    if problems:
        if len(problems) == 1 and (cardcheck.size_of(card) or 0) > cardcheck.MAX_BYTES:
            raise TooBig(problems[0])
        raise MessageError("the card does not pass the check: " + "; ".join(problems[:3]))
    text = json.dumps({"v": FORMAT, "id": delivery_id, "to": to, "title": title, "card": card}, ensure_ascii=False, separators=(",", ":"))
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES or len(_body(text).encode("utf-8")) > MAX_BODY_BYTES:
        raise TooBig(f"the message is {size} bytes, at most {MAX_BYTES}")
    return text


def queue_calls(account: str, queue: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The one call that the card queue makes, as the entry that the HTTP client allows: a POST of a message to this queue of this account's queue service, and nothing else."""
    if not ACCOUNT.fullmatch(account or "") or not QUEUE.fullmatch(queue or ""):
        raise ValueError("the account is a storage account name and the queue a queue name")
    return (("POST", re.compile(re.escape(f"https://{account}.queue.core.windows.net/{queue}/messages"))),)


@dataclass(frozen=True)
class Delivery:
    """What the put came to. `sent`: the queue took the message (which is not delivery). `failed`: anything else; the text says what, in plain words."""

    status: str
    detail: str


def _short(text: object, limit: int = MAX_DETAIL) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 3].rstrip() + "..."


class CardQueue:
    def __init__(self, client: Client, token: Callable[[str], str], account: str, queue: str, redact: Callable[[str], str] = lambda text: text,
                 clock: Callable[[], dt.datetime] = utc_now) -> None:
        self.client, self.token, self.redact, self.clock = client, token, redact, clock
        queue_calls(account, queue)
        self.url = f"https://{account}.queue.core.windows.net/{queue}/messages?messagettl={TTL_SECONDS}"

    def put(self, text: str) -> Delivery:
        """Puts one message on the queue. It never raises: a try that failed is a Delivery that says so."""
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES or len(_body(text).encode("utf-8")) > MAX_BODY_BYTES:
            return Delivery("failed", "The message is not one that may be put on the queue, so nothing was sent.")
        try:
            token = self.token(RESOURCE)
        except Exception as error:  # noqa: BLE001 (whatever the reason, there is no call without a token)
            return Delivery("failed", _short(self.redact(f"No token for the queue: {type(error).__name__}")))
        if not isinstance(token, str) or not token or any(ord(ch) <= 32 or ord(ch) == 127 for ch in token):
            return Delivery("failed", "No token for the queue: the identity gave an empty answer or one that is not a token.")
        headers = {"Authorization": f"Bearer {token}", "x-ms-version": VERSION, "x-ms-date": format_datetime(self.clock(), usegmt=True)}
        try:
            self.client.request("POST", self.url, headers=headers, xml=_body(text), timeout=20, retry_statuses=RETRY_ONLY, retry_network=False)
        except Refused:
            return Delivery("failed", "The call is not one that the app makes.")
        except HttpError as error:
            said = _short(self.redact(str(error).replace(token, "[redacted]")))
            if error.status in REFUSALS:
                return Delivery("failed", f"{REFUSALS[error.status]} {said}")
            if error.status == 0 or error.status >= 500:
                return Delivery("failed", f"{said} The message may have been taken: look at the queue before it is sent again.")
            return Delivery("failed", said)
        return Delivery("sent", SENT)
