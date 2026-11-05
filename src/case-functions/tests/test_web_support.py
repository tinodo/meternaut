"""Fixtures and helpers for the tests of the web console: people, records, a clock, two fake deciders, a console that sends requests, and a small reader of HTML.

This file holds no test. The reader of HTML builds a tree and notes every tag that is closed wrongly, so that a test can say that a page is well formed.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlencode

from support import APP_ROOT  # noqa: F401  (puts the app on the path)

from cases.memory_store import MemoryStore, stamp
from cases.models import ActionRecord, Begun, CaseRecord, DecideResult, DecisionRecord, PlanRecord, RunRecord, SettingsRecord, StoreError
from cases.people import People, Person
from cases.web import Services, handle, parse_request

NOW = dt.datetime(2026, 11, 5, 9, 0, 0, tzinfo=dt.timezone.utc)
SUB = "bbbbbbbb-2222-4333-9444-555555555555"
GROUP = "meternaut-test-rg"
DISK = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1"
ACTS_ON = "delete an unattached disk or public IP address in resource group meternaut-test-rg"
SIGNIN_URL = "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?state=state-from-the-delegate"
MODELS = ("model-detective-x", "model-skeptic-y")
HOST = "console.example.test"

TINO = "aaaaaaaa-1111-4222-8333-444444444444"  # owner, approver and ops
MAYA = "11111111-2222-3333-4444-555555555555"  # approver only
OWNER = "22222222-3333-4444-5555-666666666666"  # owner only
OPS = "33333333-4444-5555-6666-777777777777"  # ops only
STRANGER = "99999999-8888-7777-6666-555555555555"  # not in the list

XSS = "<script>alert(1)</script>\"'><img src=x onerror=alert(2)>"
XSS_ESCAPED = html.escape(XSS, quote=True)

PEOPLE = People((
    Person(TINO, "Tino", ("owner", "approver", "ops"), "tino@example.com"),
    Person(MAYA, "Maya", ("approver",), ""),
    Person(OWNER, "Olga", ("owner",), "olga@example.com"),
    Person(OPS, "Otto", ("ops",), ""),
))

DEFAULT_SETTINGS = SettingsRecord(oid=TINO)


def at(**delta) -> str:
    return stamp(NOW + dt.timedelta(**delta))


def make_run(**changes) -> RunRecord:
    base = dict(run_id="run00001", trigger="timer", started_at=at(hours=-2), finished_at=at(hours=-2, seconds=28), ok=True, leads=4, cases=3, proposed=3, needs_human=0,
                dropped=0, errors=0, tokens=2089, seconds=28, notes=("one source was not read",), reason=None)
    base.update(changes)
    return RunRecord(**base)


def make_case(**changes) -> CaseRecord:
    base = dict(case_id="case0001", resource_id=DISK, resource_name="planted-disk-1", resource_type="microsoft.compute/disks", resource_group=GROUP, subscription_id=SUB,
                detector="orphan-managed-disk", run_id="run00001", status="proposed", recommendation="delete", confidence=0.91, saving_usd_month=7.17, cost_usd_30d=7.17,
                summary="The disk is not attached and nothing uses it.", objections=("It may hold data that somebody wants.",), guards=(),
                models={"detective": "model-detective-x", "skeptic": "model-skeptic-y"},
                steps=({"step": "evidence", "model": None, "promptTokens": None, "completionTokens": None, "ms": 3, "ok": True, "note": None},
                       {"step": "detective", "model": "model-detective-x", "promptTokens": 702, "completionTokens": 307, "ms": 1200, "ok": True, "note": None},
                       {"step": "skeptic", "model": "model-skeptic-y", "promptTokens": 857, "completionTokens": 223, "ms": 1500, "ok": False, "note": "a note of the step"}),
                facts={"diskState": "unattached", "sizeBucket": "up to 128", "flags": {"locked": False}, "states": ["disconnected", "pending"]}, plan_id=None,
                first_seen_at=at(days=-3), updated_at=at(hours=-2), runs_seen=2)
    base.update(changes)
    return CaseRecord(**base)


def make_plan(**changes) -> PlanRecord:
    base = dict(plan_id="plan0001", case_id="case0001", family="delete-disk", resource_id=DISK, resource_name="planted-disk-1", resource_group=GROUP, subscription_id=SUB,
                code="7F3K92QD", title=f"Delete an unattached managed disk in resource group {GROUP}",
                what_changes="When you approve and sign in to Azure, Meternaut deletes the disk named planted-disk-1 with your own permissions. It changes nothing else.",
                saving_usd_month=7.17, waiting_costs_usd_day=0.24,
                could_go_wrong="If something still uses the disk, that use stops.", undo="A deleted disk cannot be restored and its data is lost.",
                evidence_level="Observed now: the disk is unattached. Not measured yet: the saving.", approvers=(TINO,), created_at=at(hours=-1), expires_at=at(hours=71),
                state="open", approval_class="R2", preconditions={"family": "delete-disk", "tag": "meternaut-planted"})
    base.update(changes)
    return PlanRecord(**base)


def make_action(**changes) -> ActionRecord:
    base = dict(plan_id="plan0001", case_id="case0001", family="delete-disk", resource_id=DISK, state="queued", queued_at=at(minutes=-1))
    base.update(changes)
    return ActionRecord(**base)


def make_decision(**changes) -> DecisionRecord:
    base = dict(plan_id="plan0001", approver_oid=TINO, approver_name="Tino", decision="approve", at=at(minutes=-1), plan_code="7F3K92QD", note="")
    base.update(changes)
    return DecisionRecord(**base)


def snapshot(store: MemoryStore) -> dict:
    """Everything that a store holds, except the one-time tokens: a page that only shows something may mint tokens and may change nothing else."""
    return copy.deepcopy({"runs": store.runs, "cases": store.cases, "plans": store.plans, "decisions": store.decisions, "actions": store.actions,
                          "switches": store.switch_records, "settings": store.settings, "notes": store.notes, "mails": store.mails})


# -- deciders ------------------------------------------------------------------------------------------------------------------------------------

class ScriptedDecider:
    """Answers what a test says and keeps what it was asked. It decides declines, questions and "not mine"; an approval goes through the delegate."""

    def __init__(self, result: DecideResult | None = None) -> None:
        self.result = result or DecideResult(True, "declined", "Declined.")
        self.calls: list[dict] = []

    def decide(self, principal, plan_id, decision, code, nonce, note=""):
        self.calls.append(dict(oid=principal.oid, plan_id=plan_id, decision=decision, code=code, nonce=nonce, note=note))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ScriptedDelegate:
    """The two steps of an approval, answered as a test says, with what each was asked. `begun` is what `begin` gives; `finished` is what `finish` gives."""

    def __init__(self, begun: Begun | None = None, finished: DecideResult | None = None) -> None:
        self.begun = begun or Begun(location=SIGNIN_URL)
        self.finished = finished or DecideResult(True, "ran", "Deleted. Azure no longer lists the resource.")
        self.begins: list[dict] = []
        self.finishes: list[dict] = []

    def begin(self, principal, plan_id, code, nonce, note="", hint=""):
        self.begins.append(dict(oid=principal.oid, plan_id=plan_id, code=code, nonce=nonce, note=note, hint=hint))
        if isinstance(self.begun, Exception):
            raise self.begun
        return self.begun

    def finish(self, principal, query):
        self.finishes.append(dict(oid=principal.oid, query=dict(query)))
        if isinstance(self.finished, Exception):
            raise self.finished
        return self.finished


class LoopDecider:
    """A small approval loop over the same store: it checks the code and the one-time token like the real one, and records what it accepts (not an approval)."""

    def __init__(self, store: MemoryStore, clock) -> None:
        self.store, self.clock = store, clock
        self.calls = 0

    def decide(self, principal, plan_id, decision, code, nonce, note=""):
        self.calls += 1
        plan = self.store.plan_get(plan_id)
        if plan is None:
            return DecideResult(False, "refused_state", "no such plan")
        if code != plan.code:
            return DecideResult(False, "refused_code", "the code is not the code of the plan", plan)
        if not self.store.nonce_use(nonce, principal.oid, plan_id):
            return DecideResult(False, "error", "This form is no longer valid.", plan)
        if not self.store.decision_put(DecisionRecord(plan_id, principal.oid, principal.name, decision, stamp(self.clock()), plan.code, note)):
            return DecideResult(False, "duplicate", "answered already", plan)
        kind = {"decline": "declined", "ask": "asked", "not_mine": "not_mine"}[decision]
        if decision in ("decline", "not_mine"):
            plan = _replace(self.store, plan, state="declined" if decision == "decline" else "withdrawn")
        return DecideResult(True, kind, kind, plan)


def _replace(store: MemoryStore, plan: PlanRecord, **changes) -> PlanRecord:
    changed = PlanRecord(**{**plan.__dict__, **changes})
    store.plan_put(changed)
    return changed


class FailingStore(MemoryStore):
    """A store whose named calls fail with a StoreError."""

    def __init__(self, fail=(), clock=None) -> None:
        super().__init__(clock) if clock is not None else super().__init__()
        self.fail = set(fail)

    def __getattribute__(self, name):
        if name in object.__getattribute__(self, "fail"):
            raise StoreError("the store is down", 503)
        return super().__getattribute__(name)


# -- a reader of HTML ----------------------------------------------------------------------------------------------------------------------------

VOID = {"meta", "input", "br", "hr", "link", "img"}
INLINE = {"a", "span", "strong", "em", "b", "i", "small", "code", "time", "label", "q", "abbr", "mark", "button", "option", "legend"}


class Node:
    def __init__(self, tag: str, attrs: dict, parent: "Node | None") -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list = []

    def _text(self) -> str:
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag in ("style", "script"):
                continue
            elif child.tag == "br":
                parts.append(" ")
            elif child.tag in INLINE:
                parts.append(child._text())
            else:
                parts.append(f" {child._text()} ")
        return "".join(parts)

    def text(self) -> str:
        return " ".join(self._text().split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def find_all(self, tag: str | None = None, **attrs) -> list["Node"]:
        found = []
        for node in self.walk():
            if tag is not None and node.tag != tag:
                continue
            if all(node.attrs.get(name.rstrip("_").replace("_", "-")) == value for name, value in attrs.items()):
                found.append(node)
        return found

    def find(self, tag: str | None = None, **attrs) -> "Node | None":
        found = self.find_all(tag, **attrs)
        return found[0] if found else None

    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root
        self.problems: list[str] = []

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {name: (value if value is not None else "") for name, value in attrs}, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.current = self.current.parent

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.current.tag != tag:
            self.problems.append(f"</{tag}> closes <{self.current.tag}>")
            node = self.current
            while node is not None and node.tag != tag:
                node = node.parent
            if node is None:
                return
            self.current = node
        self.current = self.current.parent or self.root

    def handle_data(self, data):
        self.current.children.append(data)

    def close(self):
        super().close()
        if self.current is not self.root:
            self.problems.append(f"<{self.current.tag}> is not closed")


class Table:
    def __init__(self, caption: str, headers: list[str], cells: list[list[Node]]) -> None:
        self.caption, self.headers, self.cells = caption, headers, cells
        self.rows = [dict(zip(headers, (cell.text() for cell in row))) for row in cells]


class Form:
    def __init__(self, node: Node) -> None:
        self.node = node
        self.action = node.attrs.get("action", "")
        self.method = node.attrs.get("method", "get").lower()
        self.fields: dict[str, str] = {}
        for item in node.walk():
            name = item.attrs.get("name")
            if item.tag == "input" and name:
                kind = item.attrs.get("type", "text")
                if kind in ("checkbox", "radio"):
                    if "checked" in item.attrs:
                        self.fields[name] = ",".join(filter(None, [self.fields.get(name), item.attrs.get("value", "on")]))
                else:
                    self.fields[name] = item.attrs.get("value", "")
            elif item.tag == "textarea" and name:
                self.fields[name] = item.text()
            elif item.tag == "select" and name:
                options = item.find_all("option")
                chosen = next((o for o in options if "selected" in o.attrs), options[0] if options else None)
                self.fields[name] = chosen.attrs.get("value", "") if chosen is not None else ""
        self.buttons = [(b.attrs.get("name", ""), b.attrs.get("value", ""), b.text()) for b in node.find_all("button")]

    def has_button(self, text: str) -> bool:
        return any(text == label for _, _, label in self.buttons)

    def button_value(self, label: str) -> tuple[str, str]:
        for name, value, text in self.buttons:
            if text == label:
                return name, value
        raise KeyError(label)


class Reply:
    """A response with the reader of HTML on it."""

    def __init__(self, response) -> None:
        self.response = response
        self.status, self.headers, self.body = response.status, response.headers, response.body
        self.text = response.body.decode("utf-8")
        self._root: Node | None = None
        self.problems: list[str] = []

    @property
    def root(self) -> Node:
        if self._root is None:
            builder = _Builder()
            builder.feed(self.text)
            builder.close()
            self._root, self.problems = builder.root, builder.problems
        return self._root

    def table(self, table_id: str) -> "Table":
        """The data table whose caption has this id."""
        caption = self.root.find("caption", id=table_id)
        if caption is None:
            raise AssertionError(f"no table {table_id!r} on the page: {[c.attrs.get('id') for c in self.root.find_all('caption')]}")
        node = caption.parent
        headers = [th.text() for th in node.find("thead").find_all("th")]
        cells = [[cell for cell in row.children if isinstance(cell, Node)] for row in node.find("tbody").find_all("tr")]
        return Table(caption.text(), headers, cells)

    def has_table(self, table_id: str) -> bool:
        return self.root.find("caption", id=table_id) is not None

    def summary(self, which: int = 0) -> dict[str, str]:
        """The names and values of the n-th summary list of the page."""
        lists = self.main.find_all("dl", class_="summary")
        found = {}
        for div in lists[which].find_all("div"):
            dt, dd = div.find("dt"), div.find("dd")
            if dt is not None and dd is not None:
                found[dt.text()] = dd.text()
        return found

    @property
    def content(self) -> str:
        """The text of the page body, as a person reads it."""
        return self.root.find("body").text()

    @property
    def main(self) -> Node:
        return self.root.find("main")

    def forms(self) -> list[Form]:
        return [Form(node) for node in self.root.find_all("form")]

    def form(self, action_ends: str | None = None, has_button: str | None = None) -> Form:
        for candidate in self.forms():
            if action_ends is not None and not candidate.action.endswith(action_ends):
                continue
            if has_button is not None and not candidate.has_button(has_button):
                continue
            return candidate
        raise AssertionError(f"no form with action {action_ends!r} and button {has_button!r} on the page: {[f.action for f in self.forms()]}")

    def links(self) -> list[str]:
        return [a.attrs.get("href", "") for a in self.root.find_all("a")]

    def headings(self, level: int | None = None) -> list[str]:
        tags = [f"h{level}"] if level else [f"h{n}" for n in range(1, 7)]
        return [node.text() for node in self.root.walk() if node.tag in tags]

    def json(self):
        return json.loads(self.text)


class Console:
    """The console with a store, a clock and people, and a way to send a request as a person."""

    def __init__(self, decider=None, store=None, people=PEOPLE, base: str = "", models=MODELS, acts_on=ACTS_ON, host=HOST, delegate=None) -> None:
        self.now = NOW
        self.store = store if store is not None else MemoryStore(clock=lambda: self.now)
        if decider == "loop":
            decider = LoopDecider(self.store, lambda: self.now)
        self.decider = decider if decider is not None else ScriptedDecider()
        self.delegate = delegate if delegate is not None else ScriptedDelegate()
        self.services = Services(store=self.store, decider=self.decider, delegate=self.delegate, people=people, now=lambda: self.now, host=host, acts_on=acts_on,
                                 models=models, base=base)
        self.base = base

    def send(self, method: str, path: str, *, oid: str | None = TINO, form: dict | None = None, query: dict | None = None, headers: dict | None = None,
             body: bytes | str | None = None, content_type: str | None = "default") -> Reply:
        url = f"https://{HOST}{self.base}{path}" + (f"?{urlencode(query)}" if query else "")
        sent = dict(headers or {})
        if oid is not None:
            sent["X-MS-CLIENT-PRINCIPAL-ID"] = oid
            sent["X-MS-CLIENT-PRINCIPAL-NAME"] = "someone@example.com"
        if form is not None and body is None:
            body = urlencode(form)
        if method == "POST" and content_type == "default":
            sent["Content-Type"] = "application/x-www-form-urlencoded"
        elif content_type not in (None, "default"):
            sent["Content-Type"] = content_type
        return Reply(handle(parse_request(method, url, sent, body), self.services))

    def get(self, path: str, **kwargs) -> Reply:
        return self.send("GET", path, **kwargs)

    def use(self, decider) -> None:
        """Replaces the decider, for a test that brings the real approval loop."""
        self.decider = decider
        self.services = dataclasses.replace(self.services, decider=decider)

    def use_delegate(self, delegate) -> None:
        """Replaces the delegate, for a test that brings the real sign-in to Azure."""
        self.delegate = delegate
        self.services = dataclasses.replace(self.services, delegate=delegate)

    def post(self, path: str, form: dict | None = None, **kwargs) -> Reply:
        return self.send("POST", path, form=form or {}, **kwargs)

    def submit(self, form: Form, button: str | None = None, oid: str | None = TINO, **fields) -> Reply:
        """Sends a form as a browser would: the fields that the form holds, then the changes, then the button that was pressed."""
        data = dict(form.fields)
        data.update(fields)
        if button is not None:
            name, value = form.button_value(button)
            if name:
                data[name] = value
        return self.post(form.action, data, oid=oid)

    def seed(self, *, plan=True, case=True, run=True) -> None:
        if run:
            self.store.run_put(make_run())
        if case:
            self.store.case_put(make_case(plan_id="plan0001" if plan else None))
        if plan:
            self.store.plan_put(make_plan())
