"""The words that a person reads: the pages of a request, a letter, a card, read as the text that a person sees and held to the style of the words.

Every case below is built from the test fakes (invented names, no network). Each is rendered by the real code and cut into the blocks that a person reads (`Reader`): a paragraph, a list item, a
cell, a heading, a button. The lint (TheWordsReadAsSentences) holds every block to the rules of docs/ui/style-guide.html, section 7 "Writing": whole sentences, full stops, no stray space or
punctuation, no sentence over 40 words, none of the phrases that the owner threw out, no id outside the Details. The module is also read by a script that prints the same cases before and after a
change (the gallery of the words), so it imports nothing that a change of the words could remove.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import functools
import re
import unittest
from html.parser import HTMLParser
from unittest import mock

from test_web_support import NOW, SUB, TINO, VM, Console, FailingStore, at, make_action, make_advice, make_advice_case, make_case, make_decision, make_plan

import support  # noqa: F401  (puts the app on the path)
from cases import brief as brief_mod
from cases import cards, letters
from cases.models import AUTOMATED, COST_AT_ASK, COST_SEEN, GROUP_FACT, HELD, EscalationRecord
from cases.people import Person

OLGA = "22222222-3333-4444-5555-666666666666"
BASE = "https://meternaut.example"
CONTACTS = ("Maya Fabrikam (maya@fabrikam.example)",)
PERSON = Person(TINO, "Maya", ("owner", "approver"), "maya@fabrikam.example")
GUID_OF_AN_APP = "3f2a9c1e-5b7d-4e8a-9c3b-1d2e3f4a5b6c"
AI_GROUP, AI_NAME = "rg-fabrikam-ai", "fabrikam-ai-weu"
AI = f"/subscriptions/{SUB}/resourceGroups/{AI_GROUP}/providers/Microsoft.CognitiveServices/accounts/{AI_NAME}"
BATCH = f"/subscriptions/{SUB}/resourceGroups/rg-fabrikam-batch/providers/Microsoft.Compute/virtualMachines/fabrikam-batch-01"
PE = f"/subscriptions/{SUB}/resourceGroups/rg-fabrikam-net/providers/Microsoft.Network/privateEndpoints/pe-fabrikam-1"
SUBSCRIPTION_NAME = "fabrikam-prod"


@dataclasses.dataclass(frozen=True)
class Block:
    """One thing that a person reads: its kind (heading, paragraph, item, term, value, cell, label, button, quote, chart), its text as a person reads it, the text as the code wrote it (to find a
    double space), whether it stands in the Details, the part of the page that it is in (`region`) and, for a cell, the number of its row."""

    kind: str
    text: str
    raw: str
    details: bool = False
    region: str = "main"
    row: int = 0


@dataclasses.dataclass(frozen=True)
class Rendered:
    name: str
    kind: str  # page, letter or card
    blocks: tuple[Block, ...]


INLINE = {"a", "span", "strong", "em", "b", "i", "small", "code", "time", "abbr", "mark", "q", "sup", "sub"}
TEXT_TAGS = {"p": "paragraph", "li": "item", "dt": "term", "dd": "value", "th": "cell", "td": "cell", "h1": "heading", "h2": "heading", "h3": "heading", "h4": "heading",
             "figcaption": "label", "summary": "label", "caption": "label", "label": "label", "button": "button", "legend": "label", "blockquote": "quote", "option": "label"}
LABEL_CLASSES = {"chips", "notice-title", "eyebrow", "brand", "who", "skip", "k", "v", "mn-label", "meta", "event"}  # a label is a short noun phrase: it needs no full stop; a line of the History is a chip and a title, and its one sentence is the quiet part under it
SPAN_BLOCKS = {"t": "label", "m": "paragraph", "quiet": "paragraph", "lab": "label", "y": "label", "mo": "label", "chips": "label"}  # the parts of a row of a list, which are lines of their own
BUTTON_CLASSES = {"btn", "mn-button"}
SKIPPED = {"style", "script", "title"}
GAP = "\x01"  # what the end of a span leaves in a block, so that two chips are two words and a full stop after a span is not set apart


class Reader(HTMLParser):
    """The blocks of a document, in the order of the page. Text goes to the innermost block that is open; a link or a span is part of its block, except a button (a link that looks like one).
    A paragraph that holds nothing but a link is a button, one that holds nothing but a time is a label, and a line of places and days set apart by a middle dot is a label too."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.open: list[dict] = []
        self.skipped = 0
        self.svg = 0
        self.details = 0
        self.region = ["main"]
        self.row = 0

    def _kind_of(self, tag: str, classes: set[str]) -> str:
        if tag == "a":
            return "button"
        if tag in ("p", "li") and classes & LABEL_CLASSES:
            return "label"
        return TEXT_TAGS[tag]

    def handle_starttag(self, tag, attrs):
        attributes = {name: value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").split())
        if tag in SKIPPED:
            self.skipped += 1
        if tag == "svg":
            self.svg += 1
            if attributes.get("aria-label"):
                self.blocks.append(Block("chart", attributes["aria-label"], attributes["aria-label"], self.details > 0, self.region[-1]))
        if tag == "details":
            self.details += 1
        if tag == "tr":
            self.row += 1
        if tag in ("header", "nav", "footer", "main"):
            self.region.append(tag)
        if tag == "br" and self.open:
            self.open[-1]["parts"].append(GAP)
        span = next((SPAN_BLOCKS[name] for name in classes if name in SPAN_BLOCKS), "") if tag == "span" else ""
        if tag in TEXT_TAGS or (tag == "a" and classes & BUTTON_CLASSES) or span:
            self.open.append({"tag": tag, "kind": span or self._kind_of(tag, classes), "parts": [], "details": self.details > 0, "region": self.region[-1], "inside": {"a": 0, "time": 0},
                              "loose": False, "linked": False, "timed": False, "inner": 0, "row": self.row if tag in ("th", "td") else 0})
        elif tag in ("a", "time") and self.open:
            self.open[-1]["inside"][tag] += 1
        elif tag == "span" and self.open and self.open[-1]["tag"] == "span":
            self.open[-1]["inner"] += 1

    def handle_endtag(self, tag):
        if tag in SKIPPED:
            self.skipped -= 1
        if tag == "svg":
            self.svg -= 1
        if tag == "span" and self.open and self.open[-1]["tag"] == "span" and self.open[-1]["inner"]:
            self.open[-1]["inner"] -= 1
        elif self.open and self.open[-1]["tag"] == tag:
            self._close()
        elif tag in ("a", "time") and self.open and self.open[-1]["inside"][tag]:
            self.open[-1]["inside"][tag] -= 1
        elif tag == "span" and self.open:
            self.open[-1]["parts"].append(GAP)
        if tag == "details":
            self.details -= 1
        if tag in ("header", "nav", "footer", "main") and len(self.region) > 1:
            self.region.pop()

    def _close(self) -> None:
        found = self.open.pop()
        raw = "".join(found["parts"])
        text = " ".join(re.sub(rf"{GAP}(?=[.,;:!?)])", "", raw).replace(GAP, " ").split())
        kind = found["kind"]
        if kind in ("paragraph", "item") and text:
            if not found["loose"] and found["linked"]:
                kind = "button"
            elif not found["loose"] and found["timed"]:
                kind = "label"
            elif " · " in text:
                kind = "label"
        if found["tag"] == "span" and self.open:
            self.open[-1]["parts"].append(GAP)
        if text:
            self.blocks.append(Block(kind, text, raw.replace(GAP, ""), found["details"], found["region"], found["row"]))

    def handle_data(self, data):
        if self.skipped or self.svg or not data:
            return
        if self.open:
            block = self.open[-1]
            block["parts"].append(data)
            if data.strip():
                if block["inside"]["a"]:
                    block["linked"] = True
                elif block["inside"]["time"]:
                    block["timed"] = True
                else:
                    block["loose"] = True
        elif data.strip():
            self.blocks.append(Block("label", " ".join(data.split()), data, self.details > 0, self.region[-1]))  # text outside every block: the text of a link of the page


def blocks_of_html(document: str) -> tuple[Block, ...]:
    reader = Reader()
    reader.feed(document)
    reader.close()
    return tuple(reader.blocks)


LABEL_IDS = {"header", "ai-label", "kind", "headline", "place", "chips"}


def blocks_of_card(card: dict) -> tuple[Block, ...]:
    """The text of an Adaptive Card in the order of its body: each TextBlock, each fact of a FactSet (its title is a label, its value a cell) and the title of each button."""
    found: list[Block] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            kind = node.get("type")
            if kind == "TextBlock":
                text = str(node.get("text", ""))
                found.append(Block("label" if node.get("id") in LABEL_IDS else "paragraph", re.sub(r"\\([\\`*_\[\]()#<>])", r"\1", re.sub(r"(?<!\\)\*\*", "", text)), text))
            elif kind == "FactSet":
                for fact in node.get("facts", []):
                    found.append(Block("label", str(fact.get("title", "")), str(fact.get("title", ""))))
                    found.append(Block("cell", str(fact.get("value", "")), str(fact.get("value", ""))))
            elif str(kind).startswith("Action."):
                found.append(Block("button", str(node.get("title", "")), str(node.get("title", ""))))
            for key, value in node.items():
                if key not in ("fallbackText",) and isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(card)
    return tuple(found)


# -- the cases ------------------------------------------------------------------------------------------------------------------------------------

def _page(name: str, case, plan, console: Console | None = None, **more) -> Rendered:
    console = console or Console()
    if case is not None:
        console.store.case_put(case)
    console.store.plan_put(plan)
    reply = console.get(f"/ok/{plan.plan_id}")
    if reply.status != 200:
        raise AssertionError(f"the page of {name} answered {reply.status}")
    return Rendered(name, "page", blocks_of_html(reply.text))


def _ai_account(**changes):
    """The finding of the example that the owner read: an AI services account that costs $848.30 a month, no saving worked out, the AI not sure, a second AI that doubted it, and a resource that an
    application changed a week ago. Its three-line history is invented."""
    values = dict(case_id="case0102", resource_id=AI, resource_name=AI_NAME, resource_type="microsoft.cognitiveservices/accounts", resource_group=AI_GROUP, subscription_name=SUBSCRIPTION_NAME,
                  recommendation="change", confidence=0.62, saving_usd_month=None, cost_usd_30d=848.30, cost_state="lines", plan_id="plan0102",
                  summary="Almost no call reached the account in the last 30 days, yet its capacity is billed in full.", objections=("A monthly reporting job may still call the account.",),
                  facts={"basis": "no-usage", "proposal": "change", "metrics": {"Total Calls": 2929.0}, "metricUnits": {"Total Calls": "Count"}, "metricDays": {"Total Calls": 30},
                         "metricDaysWithData": {"Total Calls": 30}, "citedMetrics": 1},
                  owner={"lookedUp": True, "tagOwner": "platform-team", "tagName": "owner", "changedBy": GUID_OF_AN_APP, "changedAt": at(days=-7), "automatedAt": ""})
    values.update(changes)
    return make_advice_case(**values)


def _ai_plan(**changes):
    values = dict(plan_id="plan0102", case_id="case0102", resource_id=AI, resource_name=AI_NAME, resource_group=AI_GROUP, saving_usd_month=None, waiting_costs_usd_day=None,
                  title=f"Look at the AI services account {AI_NAME} in group {AI_GROUP}", created_at=at(days=-3))
    values.update(changes)
    return make_advice(**values)


def _priced_machine(**changes):
    """A virtual machine whose finding states a change (reduce) that code priced from its bill lines, as a Scenario: $144 a month."""
    from test_brief import pricing_line, pricing_words
    from types import SimpleNamespace

    from cases import pricing

    meters = {"m1": pricing_line("r1", 360.0, pricing_words(1)), "m2": pricing_line("r1", 120.0, pricing_words(2))}
    box = SimpleNamespace(meters=meters, evidence={"r1": {"properties": {"units": 12}}})
    change = pricing.parse({"action": "reduce", "effects": [{"handle": "r1", "meters": ["m1", "m2"], "remains": {"form": "assumed", "low": 0.4, "high": 0.7}}],
                            "how": "Move the batch machine to the next size down and keep its disks."})
    facts = {"basis": "oversized", "proposal": "change", "metrics": {"Percentage CPU": 3.2}, "metricUnits": {"Percentage CPU": "Percent"}, "metricDays": {"Percentage CPU": 30},
             "citedMetrics": 1, pricing.KEY: pricing.digest(change, pricing.price(change, ("r1",), box, {"r1": 480.0}, None), "r1")}
    values = dict(case_id="case0103", resource_id=BATCH, resource_name="fabrikam-batch-01", resource_type="microsoft.compute/virtualmachines", resource_group="rg-fabrikam-batch",
                  subscription_name=SUBSCRIPTION_NAME, recommendation="change", confidence=0.88, saving_usd_month=None, cost_usd_30d=480.0, cost_state="lines", plan_id="plan0103",
                  summary="The machine used under 5 percent of its CPU in the last 30 days.", objections=(), status="proposed", facts=facts, owner={"lookedUp": True, "tagOwner": "batch-team", "tagName": "team"})
    values.update(changes)
    return make_advice_case(**values)


def _machine_plan(**changes):
    values = dict(plan_id="plan0103", case_id="case0103", resource_id=BATCH, resource_name="fabrikam-batch-01", resource_group="rg-fabrikam-batch", saving_usd_month=144.0,
                  waiting_costs_usd_day=4.8, created_at=at(days=-3), preconditions={"family": "advise", "caseStatus": "proposed"})
    values.update(changes)
    return make_advice(**values)


def _stop_machine():
    """A request to stop a virtual machine (a change that Meternaut would make after an approval): its finding of the investigation and its plan."""
    case = make_case(case_id="case0108", plan_id="plan0108", resource_id=BATCH, resource_name="fabrikam-batch-01", resource_type="microsoft.compute/virtualmachines",
                     resource_group="rg-fabrikam-batch", subscription_name=SUBSCRIPTION_NAME, detector="investigation", saving_usd_month=140.16, cost_usd_30d=140.16, cost_state="lines",
                     summary="The machine used under 5 percent of its CPU in the last 30 days.", facts={"basis": "no-usage", "proposal": "change", "metrics": {}})
    plan = make_plan(plan_id="plan0108", case_id="case0108", family="stop-vm", resource_id=BATCH, resource_name="fabrikam-batch-01", resource_group="rg-fabrikam-batch",
                     saving_usd_month=140.16, waiting_costs_usd_day=4.67, created_at=at(days=-3), preconditions={"family": "stop-vm", "resourceType": "microsoft.compute/virtualmachines"})
    return case, plan


def _group_finding():
    group = {"count": 50, "groups": 8, "type": "microsoft.network/privateendpoints", "names": ["pe-fabrikam-2", "pe-fabrikam-3", "pe-fabrikam-4"], "costUsd30d": 345.0}
    case = make_advice_case(case_id="case0104", resource_id=PE, resource_name="pe-fabrikam-1", resource_type="microsoft.network/privateendpoints", resource_group="rg-fabrikam-net",
                            subscription_name=SUBSCRIPTION_NAME, recommendation="investigate", saving_usd_month=None, cost_usd_30d=345.0, cost_state="lines", plan_id="plan0104",
                            confidence=0.74, facts={"basis": "no-usage", "proposal": "investigate", GROUP_FACT: group, "metrics": {}})
    plan = make_advice(plan_id="plan0104", case_id="case0104", resource_id=PE, resource_name="pe-fabrikam-1", resource_group="rg-fabrikam-net", saving_usd_month=None,
                       title="Look at 50 private endpoints")
    return case, plan


def _held_finding():
    case = _ai_account(case_id="case0105", plan_id="plan0105", status="needs_human", recommendation="delete", owner={})
    plan = _ai_plan(plan_id="plan0105", case_id="case0105", state=HELD, preconditions={"family": "advise", "caseStatus": "needs_human", HELD: "unchecked"})
    return case, plan


def _taken_back():
    case = _ai_account(case_id="case0106", plan_id="plan0106")
    plan = _ai_plan(plan_id="plan0106", case_id="case0106", state="expired", preconditions={"family": "advise", "caseStatus": "needs_human", "takenBack": "rules"})
    return case, plan


def _letter(name: str, letter: letters.Letter) -> Rendered:
    return Rendered(name, "letter", blocks_of_html(letter.html))


def _card_of(case, plan) -> dict:
    brief = brief_mod.build_brief(case, plan, None, (), now=NOW, may_answer=True)
    return cards.decision_card(brief, cards.CardContext(page_url=f"{BASE}/ok/{plan.plan_id}", contacts=CONTACTS))


def _decisions() -> Rendered:
    """The start page of a person who is asked about two advice requests, a change that stops a machine and a change that deletes a disk: the focus, the two lanes and the figures of the tiles."""
    console = Console()
    for case, plan in ((_ai_account(), _ai_plan()), (_priced_machine(), _machine_plan()), _stop_machine(), (make_case(plan_id="plan0001"), make_plan(created_at=at(days=-3)))):
        console.store.case_put(case)
        console.store.plan_put(plan)
    reply = console.get("/")
    if reply.status != 200:
        raise AssertionError(f"the start page answered {reply.status}")
    return Rendered("Decisions page", "page", blocks_of_html(reply.text))


def _savings() -> Rendered:
    """The page of savings found, for the findings above: what became of each, and the figures of each row."""
    console = Console()
    for case, plan in ((_ai_account(), _ai_plan()), (_priced_machine(), _machine_plan()), _stop_machine()):
        console.store.case_put(case)
        console.store.plan_put(plan)
    reply = console.get("/ops/savings")
    if reply.status != 200:
        raise AssertionError(f"the page of savings answered {reply.status}")
    return Rendered("Savings page", "page", blocks_of_html(reply.text))


def _history(console: Console | None = None) -> Rendered:
    """What happened in the last days, as a person who may answer every request reads it: a decline, a request that a timer closed, a change that was made and checked, a request that the bill closed,
    advice that was answered, advice that Meternaut took back, a change that failed and the findings of a day."""
    console = console or Console()
    store = console.store
    store.plan_put(make_plan(state="declined"))
    store.decision_put(make_decision(decision="decline", reason="handled", at=at(days=-1)))
    store.case_put(make_case(case_id="case0004", first_seen_at=at(days=-1), resource_name="fabrikam-disk-4", plan_id="plan0004"))
    store.plan_put(make_plan(plan_id="plan0004", case_id="case0004", resource_name="fabrikam-disk-4", state="consumed", created_at=at(days=-4), expires_at=at(days=-1)))
    store.decision_put(make_decision(plan_id="plan0004", at=at(days=-3, hours=-1)))
    store.action_put(make_action(plan_id="plan0004", case_id="case0004", state="verified", finished_at=at(days=-3), verified_at=at(days=-1, hours=-2),
                                 result="Deleted. Azure no longer lists the resource.", verification={"gone": True, "note": "Cost lines show no cost."}))
    store.plan_put(make_plan(plan_id="plan0005", case_id="case0005", state="expired", created_at=at(days=-6), expires_at=at(days=-2)))
    store.case_put(make_advice_case())
    store.plan_put(make_advice(state="consumed", created_at=at(days=-2)))
    store.decision_put(make_decision(plan_id="plan0002", decision="approve", at=at(days=-2, hours=-1)))
    store.plan_put(make_advice(plan_id="plan0006", case_id="case0006", state="expired", created_at=at(days=-3), expires_at=at(days=-1, hours=-3), preconditions={"family": "advise", "takenBack": "rules"}))
    store.plan_put(make_advice(plan_id="plan0007", case_id="case0007", state="expired", created_at=at(days=-14), expires_at=at(days=-1, hours=-5),
                               preconditions={"family": "advise", "caseStatus": "needs_human", "takenBack": "verified", COST_AT_ASK: 300.0, COST_SEEN: 120.0}))
    store.plan_put(make_plan(plan_id="plan0008", case_id="case0008", resource_name="fabrikam-disk-8", state="consumed", created_at=at(days=-3), expires_at=at(days=-1)))
    store.decision_put(make_decision(plan_id="plan0008", at=at(days=-2, hours=-3)))
    store.action_put(make_action(plan_id="plan0008", case_id="case0008", state="failed", finished_at=at(days=-2, hours=-2), error="Azure refused: the disk is locked."))
    reply = console.get("/history")
    if reply.status != 200:
        raise AssertionError(f"the history answered {reply.status}")
    return Rendered("History page", "page", blocks_of_html(reply.text))


def _history_cannot_be_read() -> Rendered:
    """The History when the store cannot be read: the notice of an error, and what stays."""
    reply = Console(store=FailingStore(fail={"plans_recent", "plans_expired"}, clock=lambda: NOW)).get("/history")
    return Rendered("History page, cannot be read", "page", blocks_of_html(reply.text))


def _done_change():
    """A change that was made, and that the cost lines of the bill then confirmed: its case, plan, action and the decision that approved it."""
    case, plan = make_case(plan_id="plan0001"), make_plan(state="consumed")
    action = make_action(state="verified", queued_at=at(minutes=-40), finished_at=at(minutes=-30), verified_at=at(minutes=-5), result="Deleted. Azure no longer lists the resource.",
                         verification={"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 41.2, "checkedAt": at(minutes=-5)})
    return case, plan, action, [make_decision(at=at(minutes=-41))]


@functools.lru_cache(maxsize=1)
def cases() -> dict[str, Rendered]:
    """The typical pages and messages, by name, rendered with the test fakes. The order is the order of the gallery."""
    found: dict[str, Rendered] = {}
    machine = (_priced_machine(), _machine_plan())
    found["advice, priced"] = _page("advice, priced", *machine)
    found["advice, nothing priced (the owner's example)"] = _page("advice, nothing priced (the owner's example)", _ai_account(), _ai_plan())
    found["advice, with the heads-up"] = _page("advice, with the heads-up", machine[0], _machine_plan(preconditions={"family": "advise", "caseStatus": "proposed", AUTOMATED: at(days=-2)}))
    found["advice, the cost is not visible"] = _page("advice, the cost is not visible", _ai_account(case_id="case0107", plan_id="plan0107", cost_usd_30d=None, cost_state="failed"),
                                                     _ai_plan(plan_id="plan0107", case_id="case0107"))
    found["advice, one request for many resources"] = _page("advice, one request for many resources", *_group_finding())
    found["change, delete a disk"] = _page("change, delete a disk", make_case(plan_id="plan0001"), make_plan(created_at=at(days=-3)))
    found["change, stop a machine"] = _page("change, stop a machine", *_stop_machine())
    found["held finding"] = _page("held finding", *_held_finding())
    found["request taken back"] = _page("request taken back", *_taken_back())
    case, plan = _ai_account(), _ai_plan()
    steps = [EscalationRecord(plan.plan_id, "step", 1, at(days=-6), "same", (OLGA,), ("Olga Contoso",), (OLGA,), "email", "sent"),
             EscalationRecord(plan.plan_id, "step", 2, at(days=-2), "manager", (TINO,), ("Maya Fabrikam",), (), "email", "held", detail="The mail sender is not set up yet.")]
    told, pending = brief_mod.told_lines(steps, 3)
    found["escalation letter, one request"] = _letter("escalation letter, one request", letters.escalation_letter(
        plan, case, PERSON, BASE, NOW + dt.timedelta(days=9), CONTACTS, source="manager", asked="Olga Contoso", told=told, pending=pending, put_off=1))
    found["digest letter"] = _letter("digest letter", letters.digest_letter(PERSON, BASE, NOW, [(plan, case), (_machine_plan(), _priced_machine())], CONTACTS))
    found["escalation digest letter"] = _letter("escalation digest letter", letters.escalation_digest_letter(
        PERSON, BASE, NOW + dt.timedelta(days=9), [(plan, case, "same"), (_machine_plan(), _priced_machine(), "manager")], CONTACTS))
    found["approval letter"] = _letter("approval letter", letters.approval_letter(plan, case, PERSON, BASE, NOW, CONTACTS))
    found["Teams card, advice"] = Rendered("Teams card, advice", "card", blocks_of_card(_card_of(case, plan)))
    found["Teams card, change"] = Rendered("Teams card, change", "card", blocks_of_card(_card_of(make_case(plan_id="plan0001"), make_plan())))
    found["Decisions page"] = _decisions()
    found["Savings page"] = _savings()
    found["History page"] = _history()
    found["History page, cannot be read"] = _history_cannot_be_read()
    done_case, done_plan, done_action, done_decisions = _done_change()
    done_brief = brief_mod.build_brief(done_case, done_plan, done_action, done_decisions, now=NOW)
    found["Teams card, a change that was made and checked"] = Rendered("Teams card, a change that was made and checked", "card", blocks_of_card(
        cards.result_card(done_brief, cards.CardContext(page_url=f"{BASE}/ok/{done_plan.plan_id}", contacts=CONTACTS))))
    taken_case, taken_plan = _taken_back()
    taken_brief = brief_mod.build_brief(taken_case, taken_plan, None, (), now=NOW)
    found["Teams card, a request that was taken back"] = Rendered("Teams card, a request that was taken back", "card", blocks_of_card(
        cards.closed_card(taken_brief, cards.CardContext(page_url=f"{BASE}/ok/{taken_plan.plan_id}", contacts=CONTACTS))))
    found["Teams card, the first one"] = Rendered("Teams card, the first one", "card", blocks_of_card(cards.first_contact_card("Maya", BASE, CONTACTS)))
    found["done letter"] = _letter("done letter", letters.done_letter(done_plan, done_action, done_case, PERSON, BASE, NOW, CONTACTS))
    found["first-contact letter"] = _letter("first-contact letter", letters.first_contact_letter(PERSON, BASE, NOW, CONTACTS, plan.plan_id))
    return found


def gallery() -> str:
    """The cases as plain text, a block to a line, for a person to read (a script outside the repository prints it, before and after a change). The cells of a row of a table are one line,
    a term and its value are one line, the buttons are in square brackets and the Details are cut to their first lines."""
    out: list[str] = []
    for name, shown in cases().items():
        out += [f"=== {name} ({shown.kind}) ===", ""]
        lines: list[str] = []
        details = 0
        previous = None
        for block in shown.blocks:
            if block.region == "nav" or block.text in ("Skip to the content",):
                continue
            if block.details and block.region == "main":
                details += 1
                if details > 14:
                    continue
            if block.kind == "cell" and previous is not None and previous.kind == "cell" and previous.row == block.row:
                lines[-1] += f" | {block.text}"
            elif block.kind == "value" and previous is not None and previous.kind == "term":
                lines[-1] += f" | {block.text}"
            else:
                mark = {"heading": "# ", "item": "- ", "quote": "> ", "button": "[", "chart": "(chart) ", "term": "  ", "cell": "  ", "label": ""}.get(block.kind, "")
                lines.append(("  >> " if block.details else "") + f"{mark}{block.text}" + ("]" if block.kind == "button" else ""))
            previous = block
        if details > 14:
            lines.append(f"  >> ({details - 14} more lines in the Details)")
        out += lines + [""]
    return "\n".join(out)


# -- the lint -------------------------------------------------------------------------------------------------------------------------------------

GUID_FORM = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# What the owner threw out (and the shapes that go with it): each makes the lint fail when it is put back, and a test below puts each back.
BANNED = ("saving not measured", "The most that a change could save", "Money is in US dollars", "Unproven:", "code checked", "not checked by code", "Why you are told", "nothing to undo",
          "Consider changing")
SENTENCE_START = re.compile(r"(?<=[.?!])\s+(?=[\"“(]?[A-Z0-9$])")
LOWER_AFTER_STOP = re.compile(r"[.?!]\s+([a-z]+)(?![\w.\-/@])")
PUNCTUATION = re.compile(r"\s[.,;:!?]|\.\.|,,|,\s*\.|;\s*\.|:\s*\.")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")  # a day is said as "2 November", and an ISO date belongs in the Details
OLD_MONEY = re.compile(r"\b(?:saves|could save|costs),\s+(?:scenario|expected|verified)\b|\bbased on the \d+ (?:bill )?lines?\b|\ba year is twelve times the month\b", re.IGNORECASE)  # the money line of the old pages: a level as a label, "Based on the 2 bill lines" and the note that a year is twelve months
OLD_RISK = re.compile(r"(?:^|[.!?]\s+)risk[:,]\s+(?:low|medium|high)\b", re.IGNORECASE)  # the risk of the old pages said as a label that starts a sentence ("Risk: high.", "Risk, medium:"); the chip says "Medium risk, High confidence"
DOUBLED = re.compile(r"\b([A-Za-z]{3,})\s+\1\b", re.IGNORECASE)
LABEL_COLON = re.compile(r"^([^:.?!]{3,60}): (?=[A-Z][a-z])")  # "Impact not analysed: Meternaut did not look ...": a sentence after a colon starts with a capital letter
RUN_IN = ("Heads-up", "If you answer", "If you approve", "What could go wrong", "Whose is it", "Undo", "Source")  # the bold labels of a line of a card or a letter and the source of a fact of a card, which a colon sets apart
MOST_WORDS = 40
NOT_YET = {"Teams card, a change that was made and checked", "done letter"}  # the cases that phase 2 has not rewritten yet; each step takes its cases out
STOPS = ".?!"
SENTENCES_ONLY = ("paragraph", "item")  # these end with a full stop, a question mark or an exclamation mark; a heading, a label, a term, a cell and a button need none
SHORT_VALUE = 5  # a value of a list of facts that is shorter than this many words is a name or a number, not a sentence


def problems(shown: Rendered) -> list[str]:
    """What is wrong with the words of one rendered case, one line for each fault, empty when it reads as sentences: no banned phrase, no id outside the Details, no stray space or punctuation, no
    sentence that starts in lower case or runs over forty words, no sentence with two colons, and a paragraph, a list item and a value of five words or more that start with a capital letter and end
    with a full stop, a question mark or an exclamation mark. The Details are the record for a person who wants all of it, names, dates and ids, so they are read for the phrases that were thrown
    out, for ids (which belong there) and for stray punctuation, and not for whole sentences. What an AI or the estate wrote (a quote) is not Meternaut's wording and is not read."""
    found: list[str] = []
    for block in shown.blocks:
        if block.kind == "quote":
            continue
        text, where = block.text, f"{shown.name}, {block.kind} \"{block.text[:60]}\""
        found += [f"{where}: says '{fragment}'" for fragment in BANNED if fragment.lower() in text.lower()]
        if GUID_FORM.search(text) and not block.details:
            found.append(f"{where}: an id outside the Details")
        if ISO_DATE.search(text) and not block.details:
            found.append(f"{where}: an ISO date outside the Details")
        if OLD_MONEY.search(text):
            found.append(f"{where}: an old money label")
        if OLD_RISK.search(text):
            found.append(f"{where}: an old risk label")
        if DOUBLED.search(text):
            found.append(f"{where}: a doubled word")
        if block.kind == "chart" or not re.search(r"[A-Za-z]", text):
            continue
        if PUNCTUATION.search(text):
            found.append(f"{where}: stray punctuation")
        if re.search(r"[^\n] {2,}", block.raw):
            found.append(f"{where}: a double space")
        if LOWER_AFTER_STOP.search(text):
            found.append(f"{where}: a sentence starts in lower case")
        if block.details:
            continue
        for sentence in SENTENCE_START.split(text):
            if len(sentence.split()) > MOST_WORDS:
                found.append(f"{where}: a sentence of {len(sentence.split())} words")
            if sentence.count(": ") > 1 and block.kind != "button":  # the name of a button is its words and the title of the request after a colon
                found.append(f"{where}: a colon chain")
            label = LABEL_COLON.match(sentence)
            if label and label.group(1) not in RUN_IN and block.kind not in ("button", "heading", "label"):
                found.append(f"{where}: a capital letter after the colon of '{label.group(1)}'")
        sentence = block.kind in SENTENCES_ONLY or (block.kind == "value" and len(text.split()) >= SHORT_VALUE)
        if sentence and re.sub(r"[)\"”’']+$", "", text)[-1:] not in tuple(STOPS):
            found.append(f"{where}: no full stop at the end")
        if sentence and text[:1].islower() and re.match(r"[a-z]+\b(?![\w.\-/@])", text):
            found.append(f"{where}: starts in lower case")
    return found


def family_words() -> dict[str, Rendered]:
    """The words of every family of change, as paragraphs: what the change does, what is read again, the risk and the undo, and the sentences of its saving. The family that deletes has words for each
    kind of resource that it deletes."""
    from cases.families import words as family

    found: dict[str, Rendered] = {}

    def shown(name: str, said) -> None:
        lines = [said.change, said.rechecked, said.risk, said.undo]
        found[name] = Rendered(name, "page", tuple(Block("paragraph", line, line) for line in lines if line))

    for name, how in family.SHOWN.items():
        if name == "delete-idle-resource":
            for kind in family.DELETE_WORDING:
                shown(f"{name}, {kind}", how.words(None, kind, "fabrikam-x", "rg-fabrikam"))
        else:
            shown(name, how.words(None, how.resource_type, "fabrikam-x", "rg-fabrikam"))
        lines = [line for line in (how.saving_basis, how.no_figure) if line]
        found[f"{name}, saving"] = Rendered(f"{name}, saving", "page", tuple(Block("paragraph", line, line) for line in lines))
    return {name: shown for name, shown in found.items() if shown.blocks}


def _made(kind: str, *texts: str, details: bool = False) -> Rendered:
    return Rendered("made", "page", tuple(Block(kind, text, text, details) for text in texts))


class TheWordsReadAsSentences(unittest.TestCase):
    """The lint holds every case of the gallery, and the words of every family, to the style of the words. Each rule is shown to catch the fault that it is for, and each phrase that the owner
    threw out is put back into the real code to show that the lint sees it."""

    def test_every_case_reads_as_sentences(self):
        for name, shown in {**cases(), **family_words()}.items():
            if name in NOT_YET:
                continue
            with self.subTest(name):
                self.assertEqual([], problems(shown))

    def test_the_gallery_holds_the_pages_and_messages_that_the_owner_named(self):
        self.assertGreaterEqual(len(cases()), 15)
        for wanted in ("advice, priced", "advice, nothing priced (the owner's example)", "advice, with the heads-up", "advice, one request for many resources", "change, delete a disk", "held finding",
                       "request taken back", "escalation letter, one request", "digest letter", "Teams card, advice"):
            self.assertIn(wanted, cases())

    def test_every_rule_catches_its_fault(self):
        faults = {
            "starts in lower case": _made("paragraph", "it costs $848 a month."),
            "a sentence starts in lower case": _made("paragraph", "It costs a lot. nobody knows why."),
            "stray punctuation": [_made("paragraph", "It costs a lot ."), _made("paragraph", "It costs a lot.."), _made("paragraph", "It costs a lot,, and more."), _made("paragraph", "It costs a lot, ."),
                                  _made("paragraph", "It costs a lot , and more.")],
            "a double space": Rendered("made", "page", (Block("paragraph", "It costs a lot.", "It  costs a lot."),)),
            "a sentence of 41 words": _made("paragraph", " ".join(["word"] * 40).capitalize() + " end."),
            "a colon chain": _made("paragraph", "What could go wrong: if you act on it: nothing shows that it is unused."),
            "no full stop at the end": [_made("paragraph", "It costs a lot"), _made("item", "It costs a lot"), _made("value", "It costs a lot of money here")],
            "an id outside the Details": _made("paragraph", f"It was changed by {GUID_OF_AN_APP}."),
            "an ISO date outside the Details": _made("paragraph", "It has waited since 2026-11-02."),
            "an old money label": [_made("paragraph", "Saves, Scenario. $144.00 a month. Based on the 2 bill lines."), _made("paragraph", "Costs, Expected. It is based on the 2 bill lines."),
                                   _made("paragraph", "Based on the 2 bill lines of this resource."), _made("paragraph", "A year is twelve times the month."),
                                   _made("paragraph", "SAVES, SCENARIO. A YEAR IS TWELVE TIMES THE MONTH.")],
            "an old risk label": [_made("paragraph", "Risk: medium."), _made("paragraph", "Risk, high: it could break traffic."), _made("item", "RISK: LOW.")],
            "a doubled word": [_made("paragraph", "The Watch's own investigation investigation found it."), _made("value", "Found by the Watch's own investigation investigation", details=True)],
            "a capital letter after the colon": [_made("paragraph", "Impact not analysed: Meternaut did not look at what depends on it."), _made("item", "If you act: What depends on it can slow down or stop.")],
        }
        for fault, made in faults.items():
            for one in made if isinstance(made, list) else [made]:
                with self.subTest(fault, text=one.blocks[0].raw):
                    self.assertTrue(any(fault.split(" of ")[0] in line for line in problems(one)), problems(one))

    def test_what_is_allowed_passes(self):
        allowed = [_made("label", "Medium risk if you act"), _made("heading", "What it costs"), _made("button", "Open in the Azure portal"), _made("cell", "Could save about $1,682 a year ($140 a month)"),
                   _made("term", "Resource id"), _made("value", "case0102"), _made("value", "$848", details=True), _made("paragraph", "It costs $848 a month, about $10,180 a year."),
                   _made("value", "Mon 2 Nov 2026 08:00 UTC (09:00 CET), run 2026-11-02", details=True), _made("paragraph", "Look at the disk x, because it may be larger than its use needs."),
                   _made("label", "Medium risk, High confidence, Cannot be undone"), _made("paragraph", "A high risk, low confidence request is still a question."),
                   _made("paragraph", f"The id {GUID_OF_AN_APP} is in the Details.", details=True), _made("quote", "it  costs, ,nothing . and the AI wrote this lower case"),
                   _made("paragraph", "Nobody has worked out what a change would save. (It is an estimate.)"), _made("item", "Heads-up: An automation changed this 2 days ago.")]
        for one in allowed:
            with self.subTest(one.blocks[0].kind, text=one.blocks[0].text):
                self.assertEqual([], problems(one))

    def test_each_phrase_that_the_owner_threw_out_makes_the_lint_fail_when_it_is_put_back(self):
        # `ADVICE_WHO` is a sentence that the page, the letter and the card all say to a person who is asked about advice: putting a phrase back into it puts it back on all three.
        for fragment in BANNED:
            said = f"This says {fragment} again."
            with self.subTest(fragment), mock.patch.object(brief_mod, "ADVICE_WHO", said):
                account, plan = _ai_account(), _ai_plan()
                brief = brief_mod.build_brief(account, plan, None, (), now=NOW, may_answer=True)
                on = {"page": _page("page", account, plan),
                      "letter": _letter("letter", letters.approval_letter(plan, account, PERSON, BASE, NOW, CONTACTS)),
                      "card": Rendered("card", "card", blocks_of_card(cards.decision_card(brief, cards.CardContext(page_url=f"{BASE}/ok/{plan.plan_id}", contacts=CONTACTS))))}
                for surface, shown in on.items():
                    self.assertTrue(any(f"says '{fragment}'" in line for line in problems(shown)), f"the {surface} does not fail for '{fragment}'")

    def test_what_is_put_back_by_hand_makes_the_lint_fail_on_the_page_the_letter_and_the_card(self):
        # The shapes that came back by hand after the reviews of the words: a date in the form of a record in the body of a page, the money line of the old pages (in any case of letters), the risk
        # of the old pages said as a label, a label with a colon before a sentence, and a word twice. Each is said where a sentence of the real code is said, and each of the three surfaces must fail.
        put_back = (
            ("an ISO date outside the Details", "It has waited since 2026-11-02."),
            ("an old money label", "Saves, Scenario. $144.00 a month. Based on the 2 bill lines."),
            ("an old money label", "saves, scenario. based on the 2 bill lines."),
            ("an old money label", "A year is twelve times the month."),
            ("an old risk label", "Risk: medium."),
            ("a capital letter after the colon of 'Impact not analysed'", "Impact not analysed: Meternaut did not look at what depends on it."),
            ("a doubled word", "The Watch's own investigation investigation found it."),
        )
        for fault, said in put_back:
            with self.subTest(fault, said=said), mock.patch.object(brief_mod, "ADVICE_WHO", said):
                account, plan = _ai_account(), _ai_plan()
                brief = brief_mod.build_brief(account, plan, None, (), now=NOW, may_answer=True)
                on = {"page": _page("page", account, plan),
                      "letter": _letter("letter", letters.approval_letter(plan, account, PERSON, BASE, NOW, CONTACTS)),
                      "card": Rendered("card", "card", blocks_of_card(cards.decision_card(brief, cards.CardContext(page_url=f"{BASE}/ok/{plan.plan_id}", contacts=CONTACTS))))}
                for surface, shown in on.items():
                    self.assertTrue(any(fault in line for line in problems(shown)), f"the {surface} does not fail for '{fault}': {problems(shown)}")

    def test_the_detector_that_the_details_say_twice_makes_the_lint_fail(self):
        from cases.web import brief_page
        from cases.web.core import Safe

        with mock.patch.object(brief_page, "detector_cell", lambda detector: Safe("Found by the Watch's own investigation<br><code>investigation</code>")):
            shown = _page("page", _ai_account(), _ai_plan())
        self.assertTrue(any("a doubled word" in line and "own investigation investigation" in line for line in problems(shown)), problems(shown))
        self.assertEqual([], [line for line in problems(_page("page", _ai_account(), _ai_plan())) if "a doubled word" in line], "the real row says it once")

    def test_an_id_that_a_page_shows_outside_the_details_makes_the_lint_fail(self):
        with mock.patch.object(brief_mod, "ADVICE_WHO", f"The id is {GUID_OF_AN_APP}."):
            shown = _page("page", _ai_account(), _ai_plan())
        self.assertTrue(any("an id outside the Details" in line for line in problems(shown)))
        details = [block for block in _page("page", _ai_account(), _ai_plan()).blocks if GUID_OF_AN_APP in block.text]
        self.assertTrue(details and all(block.details for block in details), "the id of the application is in the Details only")


if __name__ == "__main__":
    unittest.main()
