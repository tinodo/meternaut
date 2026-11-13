"""A Teams card sent straight to the person through the Bot Connector, with the function app's own identity: no queue, no flow, no user account and no secret.

It is the way TEAMS_DELIVERY=bot (cases/loop_config.py); the default is the queue (cases/teamsqueue.py). The app holds a user-assigned managed identity that an app registration of the tenant trusts through a
federated identity credential, as the sign-in to Azure of cases/delegated.py does with its own registration and identity, so the code is shared: the identity's token for api://AzureADTokenExchange is the
client assertion of a client-credentials request, whose scope is https://api.botframework.com/.default. No person signs in, no delegated scope is asked and nothing is consented to. With that token the
app creates the one-to-one conversation with a person (by the directory object id, which Teams accepts in the personal scope only), posts the card in it and, when the request has ended, replaces the
card with the closing one. Learn: "Send proactive messages" (Microsoft Teams platform, read on 2026-11-13) and "Authentication with the Bot Connector API" (Azure Bot Service).

Nothing here receives anything: there is no route, no token of Microsoft is checked, no Graph call is made and the Teams app is never installed for a person. The client has a list of calls of its own: HTTPS
only, the token endpoint of the tenant and the three calls of the service URL, with ids that are checked before they go into an address. What came of a call is one plain reason (REASONS): never the answer of
the service, a token or an id.
"""
from __future__ import annotations

import datetime as dt
import functools
import re
from typing import Callable

from .delegated import ASSERTION_RESOURCE, ASSERTION_TYPE, LOGIN_HOST, oauth_error
from .http import RETRY_STATUSES, Client, HttpError, Refused, default_transport
from .loop_config import TeamsWay

SCOPE = "https://api.botframework.com/.default"
CARD = "application/vnd.microsoft.card.adaptive"
ID = re.compile(r"(?!\.+(?:/|$))[A-Za-z0-9:@._=-]{1,200}")  # an id of Teams in an address: no escape, no slash, and never a folder that is only dots
SAFE = re.compile(r"[A-Za-z0-9:@._=/-]+")  # every character that an address of this client may hold: no query, fragment, escape, space or backslash
TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,16000}")
MAX_ANSWER = 65536  # the answers are a few hundred bytes
MIN_POST = 10.0  # a post that has less of the round than this is not made: with a shortened timeout a Connector that is merely slow would be taken for a lost answer, and the card would never be posted
REFRESH = dt.timedelta(minutes=5)  # a token is asked for again when less than this is left
DOWN = dt.timedelta(minutes=1)  # after a token that failed nothing is asked for this long, so that a round of cards waits once and not for every card
RETRY_ONLY = frozenset({429})  # a card that may have been posted is not posted again
TRANSIENT = RETRY_STATUSES | {412}  # Learn, "Rate limiting for agents": 412, 502 and 504 must be retried as well as 429, for the calls that can be repeated (a conversation is made once, a card is replaced in place)
REASONS = {
    "not-installed": "The Teams app is not installed for this person, so no card could be sent: the e-mail letter goes instead.",
    "blocked": "This person blocked the Teams app or removed it, so no card could be sent: the e-mail letter goes instead.",
    "unauthorized": "Microsoft Entra or Teams did not accept the identity of the function app: the identity or its federated credential is not right.",
    "throttled": "Teams asked the function app to slow down, so the card is tried again later.",
    "network": "Teams did not answer, so the card is tried again later.",
    "other": "Teams refused the card.",
}
REPLACE = {  # the words for a card that was posted and cannot be replaced: nobody promises a letter here
    "not-installed": "The card could not be replaced: Teams says that the app is not installed for this person any more.",
    "blocked": "The card could not be replaced: this person blocked the Teams app or removed it.",
}
NOT_REPLACED = "The card cannot be replaced: Teams refused the change."
SENT = "Teams accepted the card."
NOT_RETRIED = "Teams gave no usable answer after the card was posted. Not retried: the card may have arrived, so the e-mail letter follows."  # the text of a post whose answer was lost: cases/offers.py gives that card up, so that nobody gets two
REASON_OF = {**{text: reason for reason, text in REASONS.items()}, **{text: reason for reason, text in REPLACE.items()}, NOT_REPLACED: "other", NOT_RETRIED: "network"}


class BotError(Exception):
    """A try that did not work, in one plain reason (a key of REASONS). `step` is token, create, send or update, `status` the HTTP status (0: none) and `aadsts` the number that Microsoft Entra
    gave (0: none). `maybe_sent` says that the card was posted and the answer was lost or is no answer, so that the card may have arrived. The text is a plain sentence and never holds a token, an id or
    the answer of the service."""

    def __init__(self, step: str, reason: str, status: int = 0, aadsts: int = 0, maybe_sent: bool = False) -> None:
        super().__init__(NOT_RETRIED if maybe_sent else NOT_REPLACED if (step, reason) == ("update", "other") else (REPLACE.get(reason) if step == "update" else None) or REASONS[reason])
        self.step, self.reason, self.status, self.aadsts, self.maybe_sent = step, reason, status, aadsts, maybe_sent


def _failed(step: str, error: HttpError) -> BotError:
    """What an answer that is not a success means: Teams says in the text of its 403 whether the app is not installed for the person or the person blocked or removed it (Learn, "Send proactive
    messages"), a 401 or any refusal of the token endpoint is the identity, a 429, a 412 or a 5xx or no answer is waited out, and the rest is a refusal. A post whose answer was lost (no answer after the
    request left the app, a 5xx, a 2xx that is no answer) may have been carried out: `maybe_sent`. A request that never left (no time, no connection: `error.unsent`) was not."""
    status, said = error.status, str(error)
    if 200 <= status < 300:
        return BotError(step, "other", status, maybe_sent=step == "send")
    if status in (0, 412, 429) or status >= 500:
        lost = step == "send" and (status >= 500 or (status == 0 and not error.unsent))
        return BotError(step, "throttled" if status == 429 else "network", status, maybe_sent=lost)
    if step == "token":
        return BotError(step, "unauthorized", status, int(oauth_error(error)[1] or 0))
    if status == 403 and ("MessageWritesBlocked" in said or "ConversationBlockedByUser" in said):
        return BotError(step, "blocked", status)
    if status == 403 and ("ForbiddenOperationException" in said or "BotNotInConversationRoster" in said):
        return BotError(step, "not-installed", status)
    return BotError(step, "unauthorized" if status == 401 else "other", status)


def token_url(way: TeamsWay) -> str:
    return f"https://{LOGIN_HOST}/{way.tenant_id}/oauth2/v2.0/token"


def bot_calls(way: TeamsWay) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The four calls of this module and no other: the token endpoint of the tenant, and, under the service URL, the creation of a conversation, the post of an activity in one and the replacement of one."""
    base = re.escape(way.service_url) + "v3/conversations"
    return (("POST", re.compile(re.escape(token_url(way)))), ("POST", re.compile(base)), ("POST", re.compile(rf"{base}/{ID.pattern}/activities")),
            ("PUT", re.compile(rf"{base}/{ID.pattern}/activities/{ID.pattern}")))


class _Client(Client):
    """The client of this module: an address that holds more than the characters of such an address (a query, a fragment, an escape, a space) is refused before the list is asked."""

    def check(self, method: str, url: str) -> None:
        if not SAFE.fullmatch(url):
            raise Refused("the app makes no call to an address with those characters")
        super().check(method, url)


def new_client(way: TeamsWay, redact: Callable[[str], str], *, transport=default_transport, **options) -> Client:
    """The client with the list of calls of `way`; the real transport reads at most MAX_ANSWER bytes of an answer."""
    return _Client(bot_calls(way), redact, transport=functools.partial(default_transport, limit=MAX_ANSWER) if transport is default_transport else transport, **options)


def _activity(card: dict, summary: str) -> dict:
    return {"type": "message", "summary": summary, "attachments": [{"contentType": CARD, "content": card}]}


class TeamsBot:
    def __init__(self, way: TeamsWay, assertion: Callable[..., str], client: Client, clock: Callable[[], dt.datetime]) -> None:
        """`assertion` gives the token of the managed identity for a resource (identity.Identity.token of the identity TEAMS_BOT_IDENTITY_CLIENT_ID); while the client has the deadline of a round it is given
        the seconds that are left of it as `within`."""
        self.way, self.assertion, self.client, self.clock = way, assertion, client, clock
        self.status = 0  # the HTTP status of the last call that a step made; 0 when it made none
        self._token: tuple[str, dt.datetime] | None = None
        self._down: tuple[dt.datetime, BotError] | None = None

    def token(self) -> str:
        """The token of the bot, kept until REFRESH before it expires, and used until it does expire when a new one cannot be had. After a failure the same failure is given for DOWN from its end, without a call."""
        now, self.status = self.clock(), 0
        cached = self._token if self._token and self._token[1] > now else None
        if cached and cached[1] - now > REFRESH:
            return cached[0]
        if self._down and now - self._down[0] < DOWN:
            if cached:
                return cached[0]
            raise self._down[1]
        try:
            self._token = self._fetch(now)
        except BotError as error:
            self._down = (self.clock(), error)  # the end of the failure: an identity that stalled for a minute would leave no shield if this were the start
            if cached:
                return cached[0]
            raise
        return self._token[0]

    def _fetch(self, now: dt.datetime) -> tuple[str, dt.datetime]:
        left = self.client.remaining()
        try:
            proof = self.assertion(ASSERTION_RESOURCE, **({} if left is None else {"within": left}))
        except Exception as error:  # noqa: BLE001 (the platform gave no token: the identity is not attached or its client id is wrong, or its endpoint did not answer)
            raise BotError("token", "network" if getattr(error, "transient", False) else "unauthorized") from None
        form = {"grant_type": "client_credentials", "client_id": self.way.app_id, "client_assertion_type": ASSERTION_TYPE, "client_assertion": proof, "scope": SCOPE}
        answer = self._call("token", "POST", token_url(self.way), form=form)
        found = answer if isinstance(answer, dict) else {}
        token, seconds = found.get("access_token"), str(found.get("expires_in"))
        if not (isinstance(token, str) and TOKEN.fullmatch(token)) or str(found.get("token_type", "")).lower() != "bearer":
            raise BotError("token", "unauthorized", self.status)
        return token, now + dt.timedelta(seconds=int(seconds) if seconds.isdecimal() and seconds.isascii() else 0)

    def _call(self, step: str, method: str, url: str, **options: object) -> object:
        try:
            response = self.client.request(method, url, timeout=20, **{"retries": 1, "retry_after_max": 15, **options})  # type: ignore[arg-type]
            self.status = response.status
            return response.json()
        except HttpError as error:
            if error.status == 401 and step != "token":
                self._token = self._down = None  # the Connector did not take the token: the next call asks for a new one at once
            raise _failed(step, error) from None
        except Refused:
            raise BotError(step, "other") from None

    def late(self) -> bool:
        """True when the time of this round is used up (the deadline of the client): no call is started, and the card waits for the next round. Not while the failure of a token is remembered: a card that is
        tried then gets that failure at once, has its try written and waits its fifteen minutes, so that the next round does not meet the same failure at every card."""
        left = self.client.remaining()
        return self._down is None and left is not None and left <= 0

    def _id(self, step: str, answer: object) -> str:
        found = answer.get("id") if isinstance(answer, dict) else None
        if not (isinstance(found, str) and ID.fullmatch(found)):
            raise BotError(step, "other", self.status, maybe_sent=step == "send")
        return found

    def _url(self, step: str, conversation: str, activity: str = "") -> str:
        if not (ID.fullmatch(conversation) and (not activity or ID.fullmatch(activity))):
            raise BotError(step, "other")
        return f"{self.way.service_url}v3/conversations/{conversation}/activities" + (f"/{activity}" if activity else "")

    def create(self, oid: str) -> str:
        """The id of the one-to-one conversation with the person whose directory object id this is. Teams makes it once and gives the same one after."""
        tenant = self.way.tenant_id
        body = {"bot": {"id": f"28:{self.way.app_id}"}, "isGroup": False, "members": [{"id": oid}], "channelData": {"tenant": {"id": tenant}}, "tenantId": tenant}
        return self._id("create", self._call("create", "POST", f"{self.way.service_url}v3/conversations", headers={"Authorization": f"Bearer {self.token()}"}, body=body, retry_statuses=TRANSIENT))

    def post(self, conversation: str, card: dict, summary: str) -> str:
        """Posts the card in the conversation and returns the id of the activity. Only a 429 is tried again: a card that may have gone is not posted twice. A post that has less than MIN_POST seconds of the
        round is not made (the card was not posted, and the next round makes the conversation again, which Teams answers with the same one)."""
        url = self._url("send", conversation)
        headers = {"Authorization": f"Bearer {self.token()}"}
        left = self.client.remaining()
        if left is not None and left < MIN_POST:
            raise BotError("send", "network")
        return self._id("send", self._call("send", "POST", url, headers=headers, body=_activity(card, summary), retry_statuses=RETRY_ONLY, retry_network=False))

    def send(self, oid: str, card: dict, summary: str) -> tuple[str, str]:
        """(the conversation, the activity) of a card that was posted to the person."""
        conversation = self.create(oid)
        return conversation, self.post(conversation, card, summary)

    def update(self, conversation: str, activity: str, card: dict, summary: str) -> None:
        """Replaces the card of the activity with another."""
        url = self._url("update", conversation, activity)
        self._call("update", "PUT", url, headers={"Authorization": f"Bearer {self.token()}"}, body=_activity(card, summary), retry_statuses=TRANSIENT)
