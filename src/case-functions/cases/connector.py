"""The Bot Connector: how the bot speaks to Teams, with the standard library alone.

Two calls, both a POST to the Connector's address in the region of the person (`serviceUrl`, which Teams puts in every activity): one sends an activity into a conversation, and one
starts the personal conversation with a person who has the app. The call carries the token of the bot's own identity for https://api.botframework.com, from the platform's local
endpoint (identity.py): the app type of the bot is a user-assigned managed identity, and Learn, "Authentication with the Bot Connector API" (read 2026-11-08), says that such a bot asks the
managed identity endpoint for this resource with its own client id and sends the token as it is. There is no secret, no certificate and no federated credential in it.

What is checked before a call leaves: the address is the Connector of Teams (https://smba.trafficmanager.net/<region>/ and nothing else: the token is never sent beyond it), and the id of a
conversation has the characters of an id. The list of calls that the client allows says the same once more, so that a mistake here cannot send the token elsewhere.

Delivery is not proof. A 2xx answer means that the Connector took the activity; only a person's answer on a card shows that it arrived. A call that failed on the network, or with a 5xx, may
have been carried out, so it is not made again here (only a 429, which the Connector gives before it takes anything, is): the caller decides whether to offer it again. Nothing in this module
logs or returns a token, and an error text is cut and redacted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

from .http import Client, HttpError, Refused

BOT_RESOURCE = "https://api.botframework.com"
NAME = "Meternaut (AI)"
SERVICE_URL = re.compile(r"https://smba\.trafficmanager\.net/[a-z0-9-]{1,32}/")
CONVERSATION_ID = re.compile(r"[A-Za-z0-9:@._-]{1,300}")
MEMBER_ID = re.compile(r"[A-Za-z0-9:@._-]{1,200}")
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
RETRY_ONLY = frozenset({429})
MAX_DETAIL = 240


def connector_calls() -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The two calls that this module makes, as the entries of the list that the HTTP client allows: both are POSTs, on the Connector of Teams and nowhere else."""
    base = r"https://smba\.trafficmanager\.net/[a-z0-9-]{1,32}/v3/conversations"
    return (("POST", re.compile(base)), ("POST", re.compile(base + r"/[A-Za-z0-9:@._-]{1,300}/activities")))


@dataclass(frozen=True)
class Delivery:
    """What a call to the Connector came to. `sent`: the Connector took it (which is not delivery). `blocked`: Teams refused (403): the app is not installed for the person, or the person
    blocked it. `gone`: the conversation is not there (404): a reference that was kept is out of date. `failed`: anything else; the text says what, in plain words."""

    status: str
    detail: str
    id: str = ""


def _short(text: object, limit: int = MAX_DETAIL) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 3].rstrip() + "..."


class Connector:
    def __init__(self, client: Client, token: Callable[[str], str], app_id: str, redact: Callable[[str], str]) -> None:
        if not GUID.fullmatch(app_id or ""):
            raise ValueError("the app id of the bot is a GUID")
        self.client, self.token, self.app_id, self.redact = client, token, app_id.lower(), redact
        self.bot = {"id": f"28:{self.app_id}", "name": NAME}

    def _post(self, url: str, body: object) -> Delivery:
        try:
            token = self.token(BOT_RESOURCE)
        except Exception as error:  # noqa: BLE001 (whatever the reason, there is no call without a token)
            return Delivery("failed", _short(self.redact(f"No token for the Bot Framework: {type(error).__name__}")))
        if not isinstance(token, str) or not token or any(ord(ch) <= 32 or ord(ch) == 127 for ch in token):
            return Delivery("failed", "No token for the Bot Framework: the identity gave an empty answer or one that is not a token.")
        try:
            response = self.client.request("POST", url, headers={"Authorization": f"Bearer {token}"}, body=body, timeout=20, retry_statuses=RETRY_ONLY, retry_network=False)
        except Refused:
            return Delivery("failed", "The call is not one that the bot makes.")
        except HttpError as error:
            text = _short(self.redact(str(error).replace(token, "[redacted]")))
            if error.status == 403:
                return Delivery("blocked", "Teams refused: the app is not installed for this person, or the person blocked it. " + text)
            if error.status == 404:
                return Delivery("gone", "Teams does not know this conversation. " + text)
            if error.status == 0 or error.status >= 500:
                return Delivery("failed", f"{text} The activity may have been taken: look in Teams before it is sent again.")
            return Delivery("failed", text)
        try:
            document = response.json()
        except HttpError:
            document = None
        found = document.get("id") if isinstance(document, dict) else None
        return Delivery("sent", "The Connector accepted it. That is not delivery: only an answer on the card shows that it arrived.", found if isinstance(found, str) and len(found) <= 300 else "")

    def send(self, service_url: str, conversation_id: str, activity: dict, user_id: str = "") -> Delivery:
        """Sends an activity into one conversation. The bot is the sender; `user_id` (the person's id in Teams) names the recipient when it is known."""
        if not isinstance(service_url, str) or not SERVICE_URL.fullmatch(service_url) or not isinstance(conversation_id, str) or not CONVERSATION_ID.fullmatch(conversation_id):
            return Delivery("failed", "The address or the conversation is not one of Teams, so nothing was sent.")
        body = {**activity, "from": self.bot, "conversation": {"id": conversation_id}}
        if user_id and MEMBER_ID.fullmatch(user_id):
            body["recipient"] = {"id": user_id}
        return self._post(f"{service_url}v3/conversations/{quote(conversation_id, safe=':@._-')}/activities", body)

    def start(self, service_url: str, member_id: str, tenant_id: str) -> Delivery:
        """Starts the personal conversation with one person (their id in Teams, or their directory object id) and gives the id of it. It works only for a person who has the app."""
        if not isinstance(service_url, str) or not SERVICE_URL.fullmatch(service_url) or not MEMBER_ID.fullmatch(member_id or "") or not GUID.fullmatch(tenant_id or ""):
            return Delivery("failed", "The address, the person or the tenant is not one of Teams, so nothing was started.")
        body = {"bot": self.bot, "isGroup": False, "members": [{"id": member_id}], "tenantId": tenant_id.lower(), "channelData": {"tenant": {"id": tenant_id.lower()}}}
        made = self._post(f"{service_url}v3/conversations", body)
        if made.status == "sent" and not made.id:
            return Delivery("failed", "Teams started a conversation but did not say which, so nothing was sent.")
        return made
