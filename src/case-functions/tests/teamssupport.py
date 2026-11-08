"""What the tests of the Teams bot share: the Connector as a fake, the services of the bot built on in-memory stores, an authenticated request, and the activities that Teams sends.

Every name is invented (AGENTS.md rule 17). The key that signs the tokens is the invented one of test_botauth.py. No test touches the network.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

import support  # noqa: F401  (puts the app on the path)
import test_botauth as ba
from cases import teams, wiring
from cases.approvals import Approvals
from cases.botauth import BotAuthenticator, KeyStore
from cases.connector import Connector, connector_calls
from cases.families.gates import ChangeScope
from cases.http import Client
from cases.loop_config import LoopSettings
from cases.memory_store import MemoryStore, stamp
from cases.models import ADVISE, CaseRecord, PlanRecord, SettingsRecord
from cases.people import People, Person
from cases.redact import Redactor
from cases.references import MemoryReferences
from test_cards import make_case, make_plan

APP_ID = ba.APP_ID
TENANT = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-zq7-group"
MAYA, ANNA, OMAR, STRANGER = ("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333",
                              "99999999-9999-9999-9999-999999999999")
START = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)
PLAN_ID, CASE_ID, CODE = "p1a2b3c4d5", "c1", "7F3K92QD"
SERVICE = ba.SERVICE_URL  # https://smba.trafficmanager.net/emea/
CONVERSATION = "a:1Hq-conversation_0123456789"
BOT_TOKEN = "bot-token-for-the-connector-0123456789"


class Moving:
    """A clock that tests move."""

    def __init__(self, now: dt.datetime = START) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += dt.timedelta(**kwargs)


class FakeConnector:
    """The Bot Connector: records the calls and answers from a queue of (status, body), or with a plain success."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.replies: list[tuple[int, object]] = []

    def __call__(self, method, url, headers, data, timeout):
        body = json.loads(data.decode("utf-8")) if data else None
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "timeout": timeout})
        if self.replies:
            status, payload = self.replies.pop(0)
        else:
            status, payload = 201, ({"id": "a:started-0123456789"} if url.endswith("/v3/conversations") else {"id": "activity-1"})
        return status, {}, json.dumps(payload).encode("utf-8")

    def sent(self) -> list[dict]:
        """The activities that went into a conversation (not the starts of one)."""
        return [call for call in self.calls if call["url"].endswith("/activities")]

    def cards(self) -> list[dict]:
        return [attachment["content"] for call in self.sent() for attachment in (call["body"].get("attachments") or [])]


class Req:
    def __init__(self, body: bytes = b"", headers: dict | None = None, method: str = "POST") -> None:
        self.method, self.headers, self._body = method, headers or {}, body

    def get_body(self) -> bytes:
        return self._body


class Resp:
    def __init__(self, body: bytes = b"", status_code: int = 200, headers: dict | None = None) -> None:
        self.body, self.status_code, self.headers = body, status_code, headers or {}

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def people() -> People:
    return People((Person(MAYA, "Maya", ("owner", "approver", "ops"), "maya@example.com"), Person(ANNA, "Anna", ("approver",), "anna@example.com"),
                   Person(OMAR, "Omar", ("ops",), "omar@example.com")))


def loop_settings() -> LoopSettings:
    return LoopSettings(store_account="stexample", change_scopes=(ChangeScope(SUBSCRIPTION, GROUP),), console_host="meternaut.example", mail_sender=None,
                        planted_tag="meternaut-planted", plan_ttl_hours=72, recheck_days=7)


def advice_plan(plan_id: str = PLAN_ID, approvers=(MAYA, ANNA), **changes) -> PlanRecord:
    values = dict(plan_id=plan_id, family=ADVISE, title="Look at the disk disk-zq7-name in group rg-zq7-group", what_changes="Nothing changes in Azure. Your answer is recorded with your name.",
                  undo="Nothing is changed, so there is nothing to undo.", could_go_wrong="If the finding is wrong, time goes to a resource that is needed.", approval_class="R1",
                  approvers=approvers, created_at="2026-11-05T09:00:00Z", expires_at="2026-11-08T09:30:00Z", code=CODE)
    values.update(changes)
    return make_plan(**values)


def change_plan(plan_id: str = PLAN_ID, approvers=(MAYA, ANNA), **changes) -> PlanRecord:
    values = dict(plan_id=plan_id, approvers=approvers, created_at="2026-11-05T09:00:00Z", expires_at="2026-11-08T09:30:00Z", code=CODE)
    values.update(changes)
    return make_plan(**values)


@dataclass
class World:
    """The services of the bot on in-memory stores and fakes, and the ways to call it the way that Teams does."""

    clock: Moving = field(default_factory=Moving)
    connector_fake: FakeConnector = field(default_factory=FakeConnector)

    def __post_init__(self) -> None:
        self.store = MemoryStore(self.clock)
        self.references = MemoryReferences()
        self.people = people()
        self.loop = loop_settings()
        redact = Redactor()
        self.approvals = Approvals(self.store, wiring.approval_settings(self.loop), self.clock)
        self.connector = Connector(Client(connector_calls(), redact, transport=self.connector_fake, sleep=lambda seconds: None), lambda resource: BOT_TOKEN, APP_ID, redact)
        self.key_clock = ba.Clock()
        self.keys = KeyStore(ba.Documents(), self.key_clock)
        self.services = teams.Services(teams.TeamsSettings(APP_ID, TENANT, self.loop), self.store, self.people, self.approvals, self.references, self.connector,
                                       BotAuthenticator(APP_ID, self.keys, self.key_clock), self.clock, redact)

    # -- the records ---------------------------------------------------------------------------------------------------------------------------
    def open_plan(self, plan: PlanRecord | None = None, case: CaseRecord | None = None) -> PlanRecord:
        plan = plan or advice_plan()
        self.store.plan_put(plan)
        self.store.case_put(case or make_case(case_id=plan.case_id, status="proposed" if plan.family == ADVISE else "awaiting_ok", plan_id=plan.plan_id))
        return plan

    def nonce(self, oid: str = MAYA, plan_id: str = PLAN_ID, seconds: int = 3600) -> str:
        return self.store.nonce_new(oid, plan_id, seconds)

    def channel(self, oid: str, channel: str = "teams", **changes) -> None:
        self.store.settings_put(SettingsRecord(oid=oid, channel=channel, **changes))

    # -- the calls -----------------------------------------------------------------------------------------------------------------------------
    def call(self, activity: dict, *, authorization: str | None = None, token_kwargs: dict | None = None, method: str = "POST", body: bytes | None = None) -> Resp:
        """What Teams does: POST the activity with the token of the Connector."""
        header = authorization if authorization is not None else f"Bearer {ba.token(**(token_kwargs or {}))}"
        raw = json.dumps(activity).encode("utf-8") if body is None else body
        return teams.handle(Req(raw, {"Authorization": header, "Content-Type": "application/json"}, method), Resp, prepared=self.services)

    def answer(self, verb: str, *, plan_id: str = PLAN_ID, code: str = CODE, nonce: str | None = None, oid: str = MAYA, data: dict | None = None, **more) -> dict:
        """A tap on a button: the body of the answer to the invoke."""
        nonce = self.nonce(oid, plan_id) if nonce is None else nonce
        payload = {"requestId": plan_id, "planCode": code, "nonce": nonce, **(data or {})}
        reply = self.call(invoke(verb, payload, oid=oid, **more))
        assert reply.status_code == 200, reply.status_code
        return reply.json()


def activity(kind: str, *, oid: str = MAYA, conversation: str = CONVERSATION, personal: bool = True, tenant: str = TENANT, service: str = SERVICE, **more) -> dict:
    """An activity as Teams sends it to a bot in the personal scope."""
    value = {"type": kind, "id": "f:0123456789", "serviceUrl": service, "channelId": "msteams", "timestamp": "2026-11-05T10:18:00.000Z",
             "from": {"id": "29:1abc-teams-user-id", "name": "Maya", "aadObjectId": oid}, "recipient": {"id": f"28:{APP_ID}", "name": "Meternaut (AI)"},
             "conversation": {"id": conversation, "tenantId": tenant, **({"conversationType": "personal"} if personal else {"conversationType": "channel"})},
             "channelData": {"tenant": {"id": tenant}}}
    value.update(more)
    return value


def invoke(verb: str, data: dict, *, oid: str = MAYA, name: str = "adaptiveCard/action", **more) -> dict:
    return activity("invoke", oid=oid, name=name, value={"action": {"type": "Action.Execute", "verb": verb, "data": data, "id": verb}, "trigger": "manual"}, **more)


def card_of(body: dict) -> dict:
    assert body["statusCode"] == 200 and body["type"] == "application/vnd.microsoft.card.adaptive", body
    return body["value"]


def texts(card: dict) -> list[str]:
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            out.extend(value for key, value in node.items() if key in ("text", "title", "value", "fallbackText") and isinstance(value, str))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(card)
    return out


def stamped(moment: dt.datetime) -> str:
    return stamp(moment)
