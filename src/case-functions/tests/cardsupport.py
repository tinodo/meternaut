"""What the tests of the Teams cards share: the Queue service as a fake, the round of cards on in-memory stores, and the people and the plans of the examples.

Every name is invented (AGENTS.md rule 17). No test touches the network.
"""
from __future__ import annotations

import datetime as dt
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import support  # noqa: F401  (puts the app on the path)
from cases import offers, teamsqueue
from cases.http import Client
from cases.memory_store import MemoryStore
from cases.models import ADVISE, CaseRecord, MailRecord, PlanRecord, SettingsRecord
from cases.people import People, Person
from cases.redact import Redactor
from test_cards import make_case, make_plan

ACCOUNT = "stexample"
QUEUE = "teams-cards"
BASE = "https://meternaut.example"
QUEUE_URL = f"https://{ACCOUNT}.queue.core.windows.net/{QUEUE}/messages?messagettl={teamsqueue.TTL_SECONDS}"
MAYA, ANNA, OMAR, STRANGER = ("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333",
                              "99999999-9999-9999-9999-999999999999")
START = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)
PLAN_ID, CASE_ID, CODE = "p1a2b3c4d5", "c1", "7F3K92QD"
STORAGE_TOKEN = "storage-token-for-the-queue-0123456789"


class Moving:
    """A clock that tests move."""

    def __init__(self, now: dt.datetime = START) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += dt.timedelta(**kwargs)


class FakeQueue:
    """The Queue service as the transport of the HTTP client: records the calls, and answers 201 or the next of the answers that a test has queued (a number, or an error to raise)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.replies: list[object] = []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "data": data, "timeout": timeout})
        reply = self.replies.pop(0) if self.replies else 201
        if isinstance(reply, BaseException):
            raise reply
        status, body = reply if isinstance(reply, tuple) else (reply, b"")
        if status == 201 and not body:
            body = b'<?xml version="1.0" encoding="utf-8"?><QueueMessagesList><QueueMessage><MessageId>m</MessageId></QueueMessage></QueueMessagesList>'
        return status, {}, body

    def texts(self) -> list[str]:
        """The text of each message that was put: what the flow reads."""
        found = []
        for call in self.calls:
            if call["method"] == "POST" and call["url"] == QUEUE_URL and call["data"]:
                found.append(ET.fromstring(call["data"].decode("utf-8")).find("MessageText").text)
        return found

    def messages(self) -> list[dict]:
        return [json.loads(text) for text in self.texts()]

    def cards(self) -> list[dict]:
        return [message["card"] for message in self.messages()]


def people() -> People:
    return People((Person(MAYA, "Maya", ("owner", "approver", "ops"), "maya@example.com"), Person(ANNA, "Anna", ("approver",), "anna@example.com"),
                   Person(OMAR, "Omar", ("ops",), "omar@example.com")))


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
    """The round of cards on an in-memory store, a fake Queue service and a clock that a test moves."""

    clock: Moving = field(default_factory=Moving)
    queue_fake: FakeQueue = field(default_factory=FakeQueue)

    def __post_init__(self) -> None:
        self.store = MemoryStore(self.clock)
        self.people = people()
        redact = Redactor()
        client = Client(teamsqueue.queue_calls(ACCOUNT, QUEUE), redact, transport=self.queue_fake, sleep=lambda seconds: None)
        self.queue = teamsqueue.CardQueue(client, lambda resource: STORAGE_TOKEN, ACCOUNT, QUEUE, redact, self.clock)
        self.offers = offers.Offers(self.store, self.people, self.queue, BASE, self.clock, redact)

    def run(self) -> int:
        return self.offers.run()

    # -- the records ---------------------------------------------------------------------------------------------------------------------------
    def open_plan(self, plan: PlanRecord | None = None, case: CaseRecord | None = None) -> PlanRecord:
        plan = plan or advice_plan()
        self.store.plan_put(plan)
        self.store.case_put(case or make_case(case_id=plan.case_id, status="proposed" if plan.family == ADVISE else "awaiting_ok", plan_id=plan.plan_id))
        return plan

    def channel(self, oid: str, channel: str = "teams", **changes) -> None:
        self.store.settings_put(SettingsRecord(oid=oid, channel=channel, **changes))

    def introduce(self, *oids: str) -> None:
        """Marks people as told who writes, so that the tests of the card of a request need not look at the card that comes before it."""
        for oid in oids:
            self.store.mail_put(MailRecord(f"told-{oid[:4]}", oid, offers.FIRST_CONTACT, "[Meternaut] x", "2026-11-01T10:00:00Z", "sent", None, ""))

    def tries(self, oid: str = MAYA, kind: str | None = None) -> list[MailRecord]:
        return [m for m in self.store.mails if m.oid == oid and (kind is None or m.kind == kind) and not m.mail_id.startswith("told-")]


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
