"""A Teams card as one message on a private Storage queue, and the message that comes back: what is written, how it must fit and how it is put there.

Meternaut has no bot that receives anything: no endpoint that Teams calls. This is the way of the default, TEAMS_DELIVERY=queue; with TEAMS_DELIVERY=bot the cards only go out, straight to Teams, through
cases/teamsbot.py (his plain yes of 2026-11-13). This way puts one message on the queue `teams-cards`
(TEAMS_CARDS_QUEUE) of the storage account of the base, with the app's managed identity and no key (the app holds Storage Queue Data Contributor on the account, which takes traffic only through its
private endpoints). A flow of Power Automate reads the queue and posts the card as the Flow bot in the chat of the person that the message names (docs/proposals/19-teams-cards-through-power-automate.md
says what is proved and what is not).

The message is one JSON text in UTF-8, not base64, and at most MAX_BYTES bytes:

    {"v": 1, "id": "<delivery id>", "to": "<mail address>", "title": "<short plain title>", "card": {<Adaptive Card 1.4>}, "request": "<plan id>"}

`id` is the id of the record of the try (offers.py), `to` the address that the list of people holds, `title` the fixed words of a notification (cards.SUMMARIES). `request` is on the card of a request that
waits: after the post the flow writes it, with the id of the Teams message and of the conversation, to the queue `teams-posted` (read_posted), and the app keeps them (offers.record_posted). When the request
ends the app puts `{"v": 1, "op": "update", "id", "to", "title", "card", "message"}` on the queue, and the flow replaces that message with the card, which has no button. A card that does
not fit is not cut: offers.py puts cards.minimal_card in its place.

Delivery is best effort. `sent` means that the queue took the message, not that the flow posted it: the message on `teams-posted` says that, and the letter follows (cases/notify.py) when no card was sent.
A call that failed on the network or with a 5xx answer may have been carried out, so it is not made again here (only 429 and 503, which the service gives before it takes a message).
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
TEAMS_ID = re.compile(r"[!-~]{1,200}")  # an id that Teams made: printable, no space
SENT = "The queue took the message. That is not delivery: the flow posts the card, and the message on teams-posted says when it did."
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


def render(delivery_id: str, to: str, title: str, card: dict, *, request: str | None = None, update: str | None = None) -> str:
    """The text of the message: a card to post (`request`: the plan that it is about) or a card that replaces one (`update`: the Teams message id). Raises TooBig when it is over MAX_BYTES (or its XML over
    MAX_BODY_BYTES), and MessageError when anything in it is not what it has to be."""
    if not isinstance(delivery_id, str) or not ID.fullmatch(delivery_id):
        raise MessageError("the delivery id is not an opaque id")
    if not isinstance(to, str) or len(to) > 254 or not ADDRESS.fullmatch(to):
        raise MessageError("the address of the person is not an address")
    if not _one_line(title) or len(title) > MAX_TITLE:
        raise MessageError("the title is not one short line")
    if request is not None and not ID.fullmatch(request) or update is not None and not TEAMS_ID.fullmatch(update):
        raise MessageError("the request or the Teams message is not an id")
    problems = cardcheck.check(card)
    if problems:
        if len(problems) == 1 and (cardcheck.size_of(card) or 0) > cardcheck.MAX_BYTES:
            raise TooBig(problems[0])
        raise MessageError("the card does not pass the check: " + "; ".join(problems[:3]))
    document = {"v": FORMAT, "id": delivery_id, "to": to, "title": title, "card": card, **({"request": request} if request else {}), **({"op": "update", "message": update} if update else {})}
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES or len(_body(text).encode("utf-8")) > MAX_BODY_BYTES:
        raise TooBig(f"the message is {size} bytes, at most {MAX_BYTES}")
    return text


def read_posted(text: str) -> tuple[str, str, str, str]:
    """(the plan, the address, the Teams message and the conversation) of a message that the flow wrote to the queue `teams-posted`. Raises MessageError for anything else."""
    try:
        found = json.loads(text)
        request, to, message, conversation = (found[key] for key in ("request", "to", "message", "conversation"))
        if found["v"] == FORMAT and ID.fullmatch(request) and ADDRESS.fullmatch(to) and TEAMS_ID.fullmatch(message) and TEAMS_ID.fullmatch(conversation):
            return request, to, message, conversation
    except (TypeError, KeyError, ValueError):
        pass
    raise MessageError("the message is not what the flow writes after a post: v, request, to, message and conversation")


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
