"""The Teams bot: the one public endpoint of Meternaut, `POST /api/messages`, and the timer that offers cards.

Teams talks to a bot through the Bot Framework Connector, which POSTs an activity (JSON) to the bot's messaging endpoint with a signed token. This module is that endpoint, written on the
standard library: no Bot Framework SDK, because the Python SDK has no routing for the Universal Actions (`Action.Execute`) that the cards use, and the wire protocol is plain REST and a
JWT (docs/proposals/13-teams-and-outlook.md has the sources and the dates).

What is public, and why. Microsoft publishes no service tag or address list for the Connector, so the endpoint cannot be closed to it by address. It is open to every caller on the internet
and trusts none: the first thing it does with a request is botauth.py (the token, the audience, the issuer, the service URL, the signature, the channel), and a request that fails gets a
status and an empty body. Everything that follows is bounded by design: an approval that changes Azure is never taken from a card (the card's one link goes to the page, where the person
signs in to Azure and Azure checks the person's own rights); what a card can record is an answer that changes nothing in Azure (a decline, a question, "not mine", "later", and "worth acting
on" for advice), for a person on the list of people, with the plan's code and a one-time token that the server made for that person and that plan. A forged call therefore cannot approve
anything, and at the most records one low-stakes answer for a listed person who knows a plan id, its code and a live one-time token.

What a person sees: a card in the personal chat with the app. The answer on it goes through the same decider as the page's form (Approvals.decide), and the card is replaced by the new state
within the response to the tap. A message that a person writes to the app gets one plain line: this is a card channel, not a chat. Adding the app gets one welcome card.

Nothing here keeps a token or a secret. The app has two identities and uses them apart: its system-assigned identity reads and writes the tables (the loop's store and the references), and the
user-assigned identity that IS the bot (its client id is the bot's app id) is used for one thing, the token for the Connector (connector.py).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Mapping

from . import brief as brief_mod, cards, loop_config, offers, people as people_mod, switches, wiring
from .approvals import Approvals
from .botauth import BotAuthenticator, KeyStore, Rejected, botauth_calls
from .cards import MAX_NOTE, NONCE, OPAQUE, PLAN_CODE, CardContext, CardError
from .connector import CONVERSATION_ID, GUID, SERVICE_URL, Connector, connector_calls
from .http import Client, default_transport
from .identity import Identity
from .loop_config import LoopSettings
from .memory_store import stamp, utc_now
from .models import ADVISE, MailRecord, Principal, Store, StoreError
from .people import People, Person
from .redact import Redactor
from .references import MemoryReferences, ReferenceTable, made, references_calls
from .store import TableStore, table_calls

LOG = logging.getLogger("meternaut.teams")
APP_ID = "TEAMS_BOT_APP_ID"
TENANT_ID = "TEAMS_TENANT_ID"
MAX_BODY = 65536
INVOKE_NAME = "adaptiveCard/action"
_RUNTIME: dict[str, object] = {}

NOT_LISTED = "I do not write to you: you are not on my list of people. Nothing was recorded. Talk to the person who runs Meternaut in your organisation if this should be different."
NOT_LISTED_ANSWER = "I cannot take your answer: you are not on my list of people. Nothing was recorded."
UNREADABLE = "I could not read this answer. Nothing was recorded."
NO_RECORDS = "I cannot reach my records right now. Nothing was recorded. Try again in a few minutes."
NOT_FOUND = "I cannot find this request. Nothing was recorded."
REFUSED_ROLE = "I cannot take your OK on this request. Nothing was recorded."
APPROVE_ON_THE_PAGE = "An approval of a change is made on the page, where you sign in to Azure, not on a card. Nothing was approved."
WRITE_FIRST = "Write a few words first. Nothing was recorded."
FAILED = "I could not take your answer. Open the request on the page to see where it stands."
HELP = ("I am Meternaut, an AI that looks for Azure resources that cost money and are not used. I do not chat here: when a decision waits for you, I send you a card, and you "
        "answer it there. Everything else is on the web page: {page} Written by an AI.")


class TeamsConfigError(Exception):
    """The settings of the bot are half set or wrong; the text lists every problem."""


@dataclass(frozen=True)
class TeamsSettings:
    app_id: str  # the client id of the bot's user-assigned identity: the app id of the bot, the audience of every token that Teams sends, and the id in the manifest of the Teams app
    tenant_id: str  # the tenant of the people: every activity has to come from it
    loop: LoopSettings


def load(env: Mapping[str, str]) -> TeamsSettings | None:
    """None when the bot is not set up (neither setting is there); the settings when it is; TeamsConfigError when it is half set up."""
    app, tenant = (env.get(APP_ID) or "").strip(), (env.get(TENANT_ID) or "").strip()
    if not app and not tenant:
        return None
    problems = [f"{name} is not a GUID" for name, value in ((APP_ID, app), (TENANT_ID, tenant)) if not GUID.fullmatch(value)]
    try:
        loop = loop_config.load(env)
    except loop_config.LoopConfigError as error:
        loop, problems = None, [*problems, f"the loop's settings are wrong: {error}"]
    if loop is None and not any(problem.startswith("the loop") for problem in problems):
        problems.append("the loop is not configured (STORE_ACCOUNT_NAME and the settings with it): the bot has nothing to answer about")
    if problems:
        raise TeamsConfigError("; ".join(problems))
    return TeamsSettings(app.lower(), tenant.lower(), loop)  # type: ignore[arg-type]


@dataclass
class Services:
    settings: TeamsSettings
    store: Store
    people: People
    approvals: Approvals
    references: ReferenceTable | MemoryReferences
    connector: Connector
    authenticator: BotAuthenticator
    clock: Callable[[], dt.datetime]
    redact: Callable[[str], str]

    def offers(self) -> offers.Offers:
        return offers.Offers(self.store, self.people, self.references, self.connector, self.settings.tenant_id, self.settings.loop.base_url, self.clock, self.redact)


def build_services(env: Mapping[str, str], *, transport=default_transport, sleep=time.sleep, monotonic=time.monotonic, clock=utc_now, fetch=None, keys_fetch=None) -> Services | None:
    """The bot's services from the settings, or None when the bot is not set up. Raises TeamsConfigError, or PeopleError, when it is set up wrongly: a half bot answers nobody."""
    settings = load(env)
    if settings is None:
        return None
    people = people_mod.load(env)
    redact = Redactor()
    options = {"sleep": sleep, **({"fetch": fetch} if fetch else {})}
    account = settings.loop.store_account
    tables = Client(table_calls(account) + references_calls(account), redact, transport=transport, sleep=sleep, monotonic=monotonic)
    # The tables are read and written with the app's system-assigned identity: no client id, whatever the app's settings hold.
    reader = Identity({**env, "AZURE_CLIENT_ID": ""}, **options)
    store = TableStore(tables, reader.token, account, clock=clock)
    references = ReferenceTable(tables, reader.token, account, clock=clock)
    approvals = Approvals(store, wiring.approval_settings(settings.loop), clock)
    # The bot is its user-assigned identity: its token for the Connector is the only thing that it is used for.
    bot = Identity({**env, "AZURE_CLIENT_ID": settings.app_id}, **options)
    connector = Connector(Client(connector_calls(), redact, transport=transport, sleep=sleep, monotonic=monotonic), bot.token, settings.app_id, redact)
    key_client = Client(botauth_calls(), redact, transport=transport, sleep=sleep, monotonic=monotonic)
    keys = KeyStore(keys_fetch or (lambda url: key_client.request("GET", url, timeout=10, retries=1).body))
    return Services(settings, store, people, approvals, references, connector, BotAuthenticator(settings.app_id, keys), clock, redact)


def services(env: Mapping[str, str], **options) -> Services | None:
    """One set of services for the life of the process: the keys of the Connector and the tokens of the identities are worth keeping."""
    if "services" not in _RUNTIME:
        built = build_services(env, **options)
        if built is None:
            return None
        _RUNTIME["services"] = built
    return _RUNTIME["services"]  # type: ignore[return-value]


# -- what an activity says -----------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Context:
    service_url: str
    conversation_id: str
    personal: bool
    user_id: str  # the person's id in Teams (29:...)
    oid: str  # the person's directory object id, in lower case, or empty
    bot_id: str


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def context_of(s: Services, activity: dict) -> Context | None:
    """What an authenticated activity says about where it came from, or None when it is not what Teams sends to this bot: the Connector's address, the tenant of the people, the bot's own
    id as the recipient, and a conversation with an id. The token was checked already (botauth.py); this is the shape of what it vouched for."""
    service = _text(activity.get("serviceUrl"))
    service = service if service.endswith("/") else service + "/"
    if not SERVICE_URL.fullmatch(service):
        return None
    tenant = _text(_dict(_dict(activity.get("channelData")).get("tenant")).get("id")).lower()
    if tenant != s.settings.tenant_id:
        return None
    app = s.settings.app_id
    recipient = _text(_dict(activity.get("recipient")).get("id")).lower()
    if recipient not in (app, f"28:{app}"):
        return None
    conversation = _dict(activity.get("conversation"))
    conversation_id = _text(conversation.get("id"))
    if not CONVERSATION_ID.fullmatch(conversation_id):
        return None
    sender = _dict(activity.get("from"))
    oid = _text(sender.get("aadObjectId")).lower()
    return Context(service, conversation_id, _text(conversation.get("conversationType")).lower() == "personal", _text(sender.get("id")), oid if GUID.fullmatch(oid) else "", f"28:{app}")


# -- the activities ------------------------------------------------------------------------------------------------------------------------------

def _page(s: Services) -> str:
    return s.settings.loop.base_url + "/"


def _remember(s: Services, ctx: Context, person: Person | None) -> None:
    """Keeps the conversation with a person on the list, so that a card can be sent into it later."""
    if person is None or not ctx.personal:
        return
    try:
        s.references.reference_put(made(person.oid, ctx.conversation_id, ctx.service_url, ctx.user_id, s.settings.tenant_id, s.clock()))
    except (ValueError, StoreError) as error:
        LOG.warning(s.redact(f"teams: a conversation could not be kept: {type(error).__name__}"))


def _say(s: Services, ctx: Context, text: str) -> None:
    delivery = s.connector.send(ctx.service_url, ctx.conversation_id, {"type": "message", "text": text, "textFormat": "plain"}, ctx.user_id)
    if delivery.status != "sent":
        LOG.warning(s.redact(f"teams: a line could not be sent ({delivery.status})"))


def _on_message(s: Services, ctx: Context) -> None:
    if not ctx.personal:
        return
    person = s.people.by_oid(ctx.oid) if ctx.oid else None
    if person is None:
        _say(s, ctx, NOT_LISTED)
        return
    _remember(s, ctx, person)
    _say(s, ctx, HELP.format(page=_page(s)))


def _welcome(s: Services, ctx: Context, person: Person) -> None:
    """The one card that the app sends when a person adds it: who it is, what it does and does not do, and the link to the web page."""
    now = s.clock()
    try:
        card = cards.first_contact_card(person.name, s.settings.loop.base_url, offers.contacts_of(s.people), why="You got this because you added me in Teams, and you are on my list of people.")
        delivery = s.connector.send(ctx.service_url, ctx.conversation_id, cards.message_activity(card, "first_contact"), ctx.user_id)
        status, detail = ("sent" if delivery.status == "sent" else "failed"), delivery.detail
    except CardError as error:
        status, detail = "failed", f"The card could not be made: {s.redact(str(error))[:150]}"
    try:
        s.store.mail_put(MailRecord(mail_id=os.urandom(6).hex(), oid=person.oid, kind=offers.FIRST_CONTACT, subject=cards.SUMMARIES["first_contact"], sent_at=stamp(now), status=status,
                                    plan_id=None, detail=" ".join(detail.split())[:240]))
    except Exception as error:  # noqa: BLE001 (the welcome is out already)
        LOG.warning(s.redact(f"teams: the outcome of the welcome could not be written: {type(error).__name__}"))


def _on_installation(s: Services, ctx: Context, activity: dict) -> None:
    person = s.people.by_oid(ctx.oid) if ctx.oid else None
    action = _text(activity.get("action")).lower()
    if person is None or not ctx.personal:
        return  # an app that a person who is not listed adds is not written to, and nothing about them is kept
    if action == "add":
        _remember(s, ctx, person)
        _welcome(s, ctx, person)
    elif action == "remove":
        try:
            s.references.reference_delete(person.oid)
        except StoreError as error:
            LOG.warning(s.redact(f"teams: a conversation could not be forgotten: {type(error).__name__}"))


def _on_conversation_update(s: Services, ctx: Context, activity: dict) -> None:
    """A person who adds the app in the personal scope: the conversation is kept (the welcome is the installation's)."""
    added = activity.get("membersAdded")
    if isinstance(added, list) and any(_text(_dict(member).get("id")).lower() == ctx.bot_id.lower() for member in added):
        person = s.people.by_oid(ctx.oid) if ctx.oid else None
        _remember(s, ctx, person)


# -- the answer on a card ------------------------------------------------------------------------------------------------------------------------

def may_answer(principal: Principal, plan) -> bool:
    return offers.may_answer(principal, plan)


def _brief(s: Services, principal: Principal, plan) -> brief_mod.Brief:
    """The brief of a plan as this person sees it now (the page's brief_of): a switch that holds the answer that approves takes it out."""
    def read(fn, default):
        try:
            return fn()
        except Exception:  # noqa: BLE001 (a part that cannot be read is a part that the card leaves out)
            return default
    case = read(lambda: s.store.case_get(plan.case_id), None)
    decisions = read(lambda: s.store.decisions_of_plan(plan.plan_id), [])
    action = read(lambda: s.store.action_get(plan.plan_id), None)
    answerable = may_answer(principal, plan)
    paused = answerable and plan.state == "open" and switches.pulled(s.store, *(("all",) if plan.family == ADVISE else ("all", "changes")))
    return brief_mod.build_brief(case, plan, action, decisions, now=s.clock(), may_answer=answerable, changes_paused=paused)


def _card_after(s: Services, principal: Principal, plan, notice: str) -> dict:
    """The card that replaces the one that was tapped: the request as it is now, and a plain line that says what was recorded. A request that is still open gets a new one-time token (the
    one of the old card is used up); a closed one shows what became of it and carries no token."""
    brief = _brief(s, principal, plan)
    answers = brief.kind in ("change", "advice") and brief.state == "open" and bool(brief.answers)
    nonce = s.store.nonce_new(principal.oid, plan.plan_id, offers.nonce_seconds(plan, s.clock())) if answers else ""
    context = CardContext(page_url=cards.page_url(s.settings.loop.base_url, plan.plan_id), nonce=nonce, contacts=offers.contacts_of(s.people))
    return cards.invoke_card(cards.card_for(brief, context, notice))


def _render(s: Services, principal: Principal, result, plan_id: str) -> dict:
    """What the tapper sees: the card, replaced, when the decider took the answer or when the request is closed; a line otherwise."""
    plan = result.plan or s.store.plan_get(plan_id)
    taken = result.ok and result.kind in ("asked", "later", "declined", "not_mine", "acknowledged")
    closed = result.kind in ("expired", "refused_state") and plan is not None and plan.state != "open"
    if plan is not None and (taken or closed):
        return _card_after(s, principal, plan, result.message)
    return cards.invoke_message(result.message or FAILED)


def _answer(s: Services, ctx: Context, activity: dict) -> dict:
    """The body of the answer to `adaptiveCard/action`: the person is the tapper, the answer is the verb, and the decider is the page's."""
    value = _dict(activity.get("value"))
    action = _dict(value.get("action"))
    verb, data = action.get("verb"), _dict(action.get("data"))
    plan_id, code, nonce = data.get("requestId"), data.get("planCode"), data.get("nonce")
    if (verb not in cards.VERBS or not isinstance(plan_id, str) or not OPAQUE.fullmatch(plan_id) or not isinstance(code, str) or not PLAN_CODE.fullmatch(code)
            or not isinstance(nonce, str) or not NONCE.fullmatch(nonce)):
        return cards.invoke_message(UNREADABLE)
    principal = s.people.principal(ctx.oid) if ctx.oid else None
    if principal is None:
        return cards.invoke_message(NOT_LISTED_ANSWER)
    note = ""
    if verb == "ask":
        # The words are the person's own: nothing is changed in them but the characters that hide text or change its order on a screen (the decider cleans the rest).
        note = brief_mod.visible(data.get("message")).strip() if isinstance(data.get("message"), str) else ""
        if not note:
            return cards.invoke_message(WRITE_FIRST)
        if len(note) > MAX_NOTE:
            return cards.invoke_message(f"The text has {len(note)} characters. The most is {MAX_NOTE}. Nothing was recorded.")
    try:
        plan = s.store.plan_get(plan_id)
    except StoreError:
        return cards.invoke_message(NO_RECORDS)
    # The checks of the page's gate, in its order, before anything is used up: a person who may not answer learns nothing about which ids exist.
    if not (principal.has("approver") or principal.has("owner")) or (plan is not None and not may_answer(principal, plan)):
        return cards.invoke_message(REFUSED_ROLE)
    if plan is None:
        return cards.invoke_message(NOT_FOUND if principal.has("approver") else REFUSED_ROLE)
    if verb == "approve" and plan.family != ADVISE:
        return cards.invoke_message(APPROVE_ON_THE_PAGE)
    try:
        result = s.approvals.decide(principal, plan_id, verb, code, nonce, note, "")
    except Exception as error:  # noqa: BLE001 (a decider that fails has recorded nothing that this module knows of)
        LOG.error(s.redact(f"teams: the decider failed: {type(error).__name__}"))
        return cards.invoke_message(FAILED)
    LOG.info("teams: an answer was taken: %s", result.kind)
    try:
        return _render(s, principal, result, plan_id)
    except Exception as error:  # noqa: BLE001 (what the decider said is true, whether or not the new card could be made)
        LOG.error(s.redact(f"teams: the card after an answer could not be made: {type(error).__name__}"))
        return cards.invoke_message(result.message or FAILED)


# -- the endpoint --------------------------------------------------------------------------------------------------------------------------------

def respond(s: Services, activity: dict) -> tuple[int, dict | None]:
    """The status and the body of the answer to one activity whose token was checked. Nothing here raises for a request: an answer that cannot be made is a line to the person."""
    ctx = context_of(s, activity)
    if ctx is None:
        return 400, None
    kind = activity.get("type")
    if kind == "invoke":
        if activity.get("name") != INVOKE_NAME:
            return 501, None
        try:
            return 200, _answer(s, ctx, activity)
        except Exception as error:  # noqa: BLE001 (nothing is recorded by a step that failed before the decider)
            LOG.error(s.redact(f"teams: an answer failed: {type(error).__name__}"))
            return 200, cards.invoke_message(FAILED)
    handlers: dict[str, Callable[[], None]] = {
        "message": lambda: _on_message(s, ctx),
        "installationUpdate": lambda: _on_installation(s, ctx, activity),
        "conversationUpdate": lambda: _on_conversation_update(s, ctx, activity),
    }
    work = handlers.get(kind) if isinstance(kind, str) else None
    if work is not None:
        try:
            work()
        except Exception as error:  # noqa: BLE001 (Teams is told that the activity was taken: a line that cannot be sent is not a reason to send it again)
            LOG.error(s.redact(f"teams: an activity of kind {kind} failed: {type(error).__name__}"))
    return 200, None  # a typing indicator, a reaction, the end of a conversation: nothing to do


def _reply(response_cls: Callable, status: int, body: dict | None = None):
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    data = b""
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return response_cls(body=data, status_code=status, headers=headers)


def handle(req, response_cls: Callable, env: Mapping[str, str] | None = None, *, prepared: Services | None = None, **options):
    """One request to the messaging endpoint. `req` is what the platform hands over (method, headers, get_body); `response_cls` is how an answer is made. It never raises.

    A request that is not let in (botauth.py) gets 401, or 403 for a key that is not endorsed for Teams, with an empty body: nothing is told to a caller who fails. Nothing of the request
    is looked at before that but its size, its method, its JSON and the two fields that the token has to match."""
    env = os.environ if env is None else env
    redact = Redactor()
    try:
        s = prepared or services(env, **options)
        if s is None:
            return _reply(response_cls, 503)
        if (getattr(req, "method", "") or "").upper() != "POST":
            return _reply(response_cls, 405)
        raw = req.get_body() or b""
        if len(raw) > MAX_BODY:
            return _reply(response_cls, 413)
        try:
            activity = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            activity = None
        headers = {str(k).lower(): str(v) for k, v in req.headers.items()}
        if not isinstance(activity, dict):
            return _reply(response_cls, 401)
        try:
            s.authenticator.authenticate(headers.get("authorization"), activity.get("serviceUrl"), activity.get("channelId"))
        except Rejected as rejected:
            LOG.warning("teams: a call was not let in (%s)", rejected.reason)
            return _reply(response_cls, rejected.status)
        status, body = respond(s, activity)
        return _reply(response_cls, status, body)
    except Exception as error:  # noqa: BLE001 (an endpoint that fails says nothing about why)
        LOG.error(redact(f"teams: the endpoint failed: {type(error).__name__}: {error}"))
        return _reply(response_cls, 500)


def tick(env: Mapping[str, str] | None = None, *, prepared: Services | None = None, **options) -> int | None:
    """The timer, every minute: the cards that are due. It never raises: a failure is logged, and the next minute tries again. None when the bot is not set up."""
    env = os.environ if env is None else env
    try:
        s = prepared or services(env, **options)
        return None if s is None else s.offers().run()
    except Exception as error:  # noqa: BLE001 (the timer must go on)
        LOG.error(Redactor()(f"teams: the cards could not be offered: {type(error).__name__}: {error}"))
        return None
