"""The Teams card of a decision brief (cases/cards.py) and its structural check (cases/cardcheck.py).

Every name below is invented (AGENTS.md rule 17): the cards are made from a disk that nobody uses. No test touches the network.
"""
import dataclasses
import datetime as dt
import json
import re
import unicodedata
import unittest

import support  # noqa: F401  (puts the app on the path)
from cases import cardcheck, cards
from cases.brief import Brief, build_brief
from cases.cards import CardContext, CardError
from cases.models import ADVISE, ActionRecord, CaseRecord, DecisionRecord, PlanRecord

NOW = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)
BASE = "https://meternaut.example"
OID = "11111111-1111-1111-1111-111111111111"
NAME = "disk-zq7-name"
GROUP = "rg-zq7-group"
PLAN_ID = "p1a2b3c4d5"
NONCE = "N0nce-0123456789abcdefghijklmnop"
CONTACTS = ("Maya (maya@example.com)", "Ops (ops@example.com)")
URL = f"{BASE}/ok/{PLAN_ID}"
HOSTILE = ("[click](https://evil.example/x) **bold** _italic_ `code` # head > quote - item 1. one \u202e\u200bhidden\x00\nsecond line <at>Maya</at> www.evil.example "
           "{{DATE(2000-01-01T00:00:00Z,LONG)}} {{{TIME(2000-01-01T00:00:00Z)}}}")


def make_plan(**changes) -> PlanRecord:
    values = dict(
        plan_id=PLAN_ID, case_id="c1", family="delete-disk", resource_id=f"/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/{NAME}",
        resource_name=NAME, resource_group=GROUP, subscription_id="11111111-2222-3333-4444-555555555555", code="7F3K92QD",
        title=f"Delete an unattached managed disk in resource group {GROUP}",
        what_changes=f"When you approve and sign in to Azure, Meternaut deletes the disk named {NAME} with your own permissions. It changes nothing else.",
        saving_usd_month=41.2, waiting_costs_usd_day=1.37, could_go_wrong="If something still uses the disk, that use stops.", undo="A deleted disk cannot be restored.",
        evidence_level="Observed now: the disk is unattached.", approvers=(OID,), created_at="2026-11-02T09:00:00Z", expires_at="2026-11-08T09:30:00Z")
    values.update(changes)
    return PlanRecord(**values)


def make_case(**changes) -> CaseRecord:
    values = dict(case_id="c1", resource_id="r1", resource_name=NAME, resource_type="microsoft.compute/disks", resource_group=GROUP,
                  subscription_id="11111111-2222-3333-4444-555555555555", detector="orphan-managed-disk", run_id="run1", status="awaiting_ok", saving_usd_month=41.2,
                  cost_usd_30d=41.2, models={"detective": "model-d", "skeptic": "model-s"}, first_seen_at="2026-11-02T09:00:00Z",
                  facts={"ageDays": 41, "sizeGb": "up to 256", "sku": "premium_lrs"}, owner={"lookedUp": True, "tagOwner": "alice@example.com", "tagName": "owner"})
    values.update(changes)
    return CaseRecord(**values)


def make_advice_plan(**changes) -> PlanRecord:
    return make_plan(family=ADVISE, title=f"Look at the disk {NAME} in group {GROUP}", what_changes="Nothing changes in Azure. Your answer is recorded with your name.",
                     undo="Nothing is changed, so there is nothing to undo.", could_go_wrong="If the finding is wrong, time goes to a resource that is needed.", approval_class="R1",
                     **changes)


def brief_of(plan=None, case=None, action=None, decisions=(), **kw) -> Brief:
    kw.setdefault("may_answer", True)
    return build_brief(case if case is not None else make_case(), plan if plan is not None else make_plan(), action, list(decisions), now=NOW, **kw)


def ctx_for(brief: Brief, **changes) -> CardContext:
    values = dict(page_url=f"{BASE}/ok/{brief.plan_id}", nonce=NONCE, contacts=CONTACTS)
    values.update(changes)
    return CardContext(**values)


def walk(node):
    """Every dict of a card, at any depth."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def texts(card) -> list[str]:
    out: list[str] = []
    for node in walk(card):
        for key, value in node.items():
            if key in ("text", "title", "value", "label", "placeholder", "errorMessage", "fallbackText", "tooltip") and isinstance(value, str):
                out.append(value)
    return out


def by_id(card) -> dict[str, dict]:
    return {node["id"]: node for node in walk(card) if isinstance(node.get("id"), str)}


def actions_of(card) -> list[dict]:
    return [node for node in walk(card) if str(node.get("type", "")).startswith("Action.")]


class TheDecisionCardOfAChange(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of()
        self.card = cards.decision_card(self.brief, ctx_for(self.brief))
        self.ids = by_id(self.card)

    def test_it_passes_the_check_and_is_a_card_of_schema_1_5(self):
        self.assertEqual(cardcheck.check(self.card), [])
        self.assertEqual((self.card["type"], self.card["version"], self.card["$schema"]), ("AdaptiveCard", "1.5", "http://adaptivecards.io/schemas/adaptive-card.json"))
        self.assertEqual(self.card["msteams"], {"width": "Full"})
        json.dumps(self.card)

    def test_it_holds_what_a_person_needs_to_decide_and_nothing_else(self):
        self.assertEqual([n["id"] for n in self.card["body"] if "id" in n],
                         ["header", "headline", "value-tile", "confidence", "facts", "change", "undo", "risk", "owner", "decisions", "message", "ask", "ai-footer"])
        self.assertEqual(self.ids["headline"]["text"], "Delete the unattached disk disk-zq7-name in group rg-zq7-group")
        self.assertEqual(self.ids["value"]["text"], "About 41.20 US dollars a month")
        self.assertEqual(self.ids["saving-word"]["text"], "Expected saving")
        self.assertIn("the cost lines of the last 30 days", self.ids["price-basis"]["text"], "every figure carries its basis")
        self.assertNotIn("waiting", self.ids, "what waiting costs is on the page: it does not help a person decide, and it pushes")
        self.assertNotIn("when", self.ids, "how long ago it was found and until when it is open are on the page")
        self.assertTrue(self.ids["confidence"]["text"].startswith("**How sure: "))
        self.assertLessEqual(len(self.ids["facts"]["facts"]), 3)
        self.assertTrue(self.ids["change"]["text"].startswith("**If you approve:** "))
        self.assertIn("with your own permissions, after you sign in to Azure", self.ids["change"]["text"], "whose rights it uses")
        self.assertEqual(self.ids["undo"]["text"], "Undo: This cannot be undone.")
        self.assertEqual(self.ids["undo"]["weight"], "Bolder", "an irreversible change is one bold line")
        self.assertTrue(self.ids["risk"]["text"].startswith("**Risk, medium:** "))
        self.assertIn("alice@example.com", self.ids["owner"]["text"])

    def test_the_only_link_is_the_page_of_the_request_and_the_approval_is_made_there(self):
        self.assertEqual({a["url"] for a in actions_of(self.card) if "url" in a}, {URL})
        (page,) = [a for a in self.ids["decisions"]["actions"] if a["type"] == "Action.OpenUrl"]
        self.assertEqual((page["title"], page["url"]), ("Review and decide", URL))
        executes = [a for a in actions_of(self.card) if a["type"] == "Action.Execute" and "verb" in a]
        self.assertEqual(sorted(a["verb"] for a in executes), ["ask", "later", "not_mine"])
        self.assertNotIn("approve", [a["verb"] for a in executes], "no card approves a change in Azure")
        self.assertNotIn("decline", [a["verb"] for a in executes])
        self.assertFalse(any(a["type"] in ("Action.Submit", "Action.Http", "Action.ShowCard", "Action.ToggleVisibility") for a in actions_of(self.card)))
        urls = re.findall(r"https?://\S+", " ".join(texts(self.card)))
        self.assertEqual({u.rstrip(".") for u in urls}, {URL}, "the address is in the text of the fallback and nowhere else")

    def test_every_action_carries_the_id_the_code_and_the_one_time_token_and_says_whether_it_takes_input(self):
        for action in actions_of(self.card):
            if action["type"] != "Action.Execute" or "verb" not in action:
                continue
            self.assertEqual(action["data"], {"requestId": PLAN_ID, "planCode": "7F3K92QD", "nonce": NONCE}, action["verb"])
            self.assertEqual(action["associatedInputs"], "auto" if action["verb"] == "ask" else "none", action["verb"])
            self.assertEqual(action["fallback"], {"type": "Action.OpenUrl", "title": "Open on the page", "url": URL})
        (ask,) = [a for a in actions_of(self.card) if a.get("verb") == "ask"]
        self.assertEqual(ask["title"], "Ask or tell")

    def test_the_one_text_box_is_ask_or_tell_and_is_needed_only_by_that_button(self):
        box = self.ids["message"]
        self.assertEqual((box["type"], box["label"], box["isRequired"], box["maxLength"], box["isMultiline"]), ("Input.Text", "Ask or tell", True, 300, True))
        self.assertTrue(box["errorMessage"])
        self.assertEqual([n["id"] for n in walk(self.card) if str(n.get("type", "")).startswith("Input.")], ["message"])

    def test_the_titles_are_the_words_of_the_page(self):
        titles = {a.get("verb", "link"): a["title"] for a in actions_of(self.card) if a["type"] != "Action.OpenUrl" or "id" in a}
        self.assertEqual(titles, {"link": "Review and decide", "not_mine": "This is not mine", "later": "Decide later", "ask": "Ask or tell"})
        for action in actions_of(self.card):
            self.assertLessEqual(len(action["title"]), 24, "a button title is short")

    def test_it_says_that_an_ai_wrote_it_and_why_the_person_got_it_in_one_footer_line(self):
        self.assertEqual(self.ids["ai-label"]["text"], "Meternaut (AI)")
        footer = self.ids["ai-footer"]["text"]
        self.assertTrue(footer.startswith("Written by an AI (models: model-d, model-s); a person approves every change."), footer)
        self.assertIn("You got this because you are named as an approver of this request.", footer)
        self.assertIn("Talk to a person: Maya (maya@example.com), Ops (ops@example.com).", footer)
        self.assertNotIn("\n", footer)
        self.assertEqual(self.card["body"][-1]["id"], "ai-footer")
        self.assertIn("Written by an AI.", self.card["fallbackText"])
        self.assertIn(URL, self.card["fallbackText"])
        self.assertIn("Meternaut (AI)", self.card["fallbackText"])

    def test_there_is_no_urgency_no_guilt_no_countdown_and_no_exclamation(self):
        everything = " ".join(texts(self.card))
        self.assertNotRegex(everything, r"(?i)\burgent\b|\bact now\b|\bhurry\b|\blast chance\b|\blimited time\b|!|\bonly \d+ (?:hours?|minutes?) left\b|we noticed you")
        self.assertNotRegex(everything, r"\d\s*[\u2013\u2014-]\s*\d", "no dash between figures")
        self.assertNotIn("\u00b7", everything)

    def test_it_is_far_below_the_size_of_a_message(self):
        self.assertLess(len(json.dumps(self.card).encode()), 6000)

    def test_the_notification_text_holds_no_name_and_no_amount(self):
        activity = cards.message_activity(self.card, "change")
        self.assertEqual(activity["type"], "message")
        self.assertEqual(activity["summary"], "[Meternaut] A change to Azure waits for your OK")
        self.assertNotIn(NAME, activity["summary"])
        self.assertNotRegex(activity["summary"], r"\d")
        self.assertEqual(activity["attachments"], [{"contentType": "application/vnd.microsoft.card.adaptive", "content": self.card}])
        self.assertEqual(cards.message_activity(self.card, "advice")["summary"], "[Meternaut] A decision waits for you")


class TheDecisionCardOfAdvice(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of(plan=make_advice_plan(), case=make_case(status="needs_human"))
        self.card = cards.decision_card(self.brief, ctx_for(self.brief))
        self.ids = by_id(self.card)

    def test_it_answers_in_the_card_and_changes_nothing_in_azure(self):
        self.assertEqual(cardcheck.check(self.card), [])
        executes = {a["verb"]: a for a in actions_of(self.card) if a["type"] == "Action.Execute" and "verb" in a}
        self.assertEqual(sorted(executes), ["approve", "ask", "decline", "later", "not_mine"])
        self.assertEqual([executes[v]["title"] for v in ("approve", "decline", "not_mine", "later", "ask")], ["Worth acting on", "Not worth it", "This is not mine", "Decide later", "Ask or tell"])
        self.assertTrue(self.ids["change"]["text"].startswith("**If you answer:** Nothing changes in Azure."))
        self.assertEqual(self.ids["undo"]["text"].split(":**")[0], "**Undo", "advice can be undone: there is nothing to undo, and no bold warning")
        self.assertNotIn("weight", self.ids["undo"])
        (link,) = [a for a in actions_of(self.card) if a["type"] == "Action.OpenUrl" and "id" in a]
        self.assertEqual((link["title"], link["url"]), ("See the evidence", URL))

    def test_six_buttons_at_the_most_in_one_row(self):
        self.assertLessEqual(len(self.ids["decisions"]["actions"]), 6)
        self.assertEqual(len(self.ids["ask"]["actions"]), 1)


class WhenASwitchHoldsTheAnswer(unittest.TestCase):
    def test_a_change_that_is_held_has_no_review_and_decide_and_says_so(self):
        brief = brief_of(changes_paused=True)
        self.assertNotIn("approve", brief.answers)
        card = cards.decision_card(brief, ctx_for(brief))
        ids = by_id(card)
        self.assertEqual(ids["paused"]["text"], "Changes are paused here. Nothing has changed, and your OK cannot be recorded now.")
        (link,) = [a for a in actions_of(card) if a["type"] == "Action.OpenUrl" and "id" in a]
        self.assertEqual(link["title"], "See the request")
        self.assertNotIn("style", link)
        self.assertEqual(cardcheck.check(card), [])

    def test_advice_that_is_held_has_no_worth_acting_on(self):
        brief = brief_of(plan=make_advice_plan(), case=make_case(status="needs_human"), changes_paused=True)
        card = cards.decision_card(brief, ctx_for(brief))
        self.assertEqual(sorted(a["verb"] for a in actions_of(card) if a.get("verb")), ["ask", "decline", "later", "not_mine"])
        self.assertIn("Meternaut is paused here.", by_id(card)["paused"]["text"])


class TheCardOfWhatBecameOfARequest(unittest.TestCase):
    def test_a_declined_request_shows_who_and_has_no_answer_and_no_token(self):
        plan = make_plan(state="declined")
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name="Maya", decision="decline", at="2026-11-05T10:00:00Z", plan_code="7F3K92QD")
        brief = brief_of(plan=plan, decisions=[decision])
        card = cards.card_for(brief, ctx_for(brief, nonce=""))
        ids = by_id(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(ids["outcome"]["text"], "Declined")
        self.assertIn("Declined by Maya.", ids["outcome-line-1"]["text"])
        self.assertEqual([a["type"] for a in actions_of(card)], ["Action.OpenUrl"])
        self.assertNotIn(NONCE, json.dumps(card))
        self.assertNotIn("planCode", json.dumps(card))
        self.assertEqual(ids["kind"]["text"], "Recorded")

    def test_advice_that_was_answered_says_that_nothing_changed_in_azure(self):
        plan = make_advice_plan(state="consumed")
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name="Maya", decision="approve", at="2026-11-05T10:00:00Z", plan_code="7F3K92QD")
        brief = brief_of(plan=plan, case=make_case(status="acknowledged"), decisions=[decision])
        ids = by_id(cards.card_for(brief, ctx_for(brief, nonce="")))
        self.assertEqual(ids["outcome"]["text"], "Worth acting on")
        self.assertIn("Nothing was changed in Azure.", ids["outcome-line-2"]["text"])

    def test_an_expired_request_says_so(self):
        brief = brief_of(plan=make_plan(expires_at="2026-11-04T09:30:00Z"))
        self.assertEqual(brief.state, "expired")
        ids = by_id(cards.card_for(brief, ctx_for(brief, nonce="")))
        self.assertEqual(ids["outcome"]["text"], "Expired")

    def test_a_change_that_ran_has_a_result_card_with_what_it_saved_and_the_undo_line(self):
        plan = make_plan(state="consumed")
        action = ActionRecord(plan_id=PLAN_ID, case_id="c1", family="delete-disk", resource_id="r1", state="verified", queued_at="2026-11-05T09:00:00Z", finished_at="2026-11-05T09:05:00Z",
                              result="Deleted. Azure no longer lists the resource.", verification={"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 41.2, "checkedAt": "2026-11-05T09:05:00Z"})
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name="Maya", decision="approve", at="2026-11-05T09:00:00Z", plan_code="7F3K92QD")
        brief = brief_of(plan=plan, action=action, decisions=[decision])
        card = cards.result_card(brief, ctx_for(brief, nonce=""))
        ids = by_id(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(ids["outcome"]["text"], "Done and checked")
        self.assertEqual(ids["saving-word"]["text"], "Verified saving")
        self.assertEqual(ids["undo"]["text"], "Undo: This cannot be undone.")
        self.assertEqual(cards.message_activity(card, "result")["summary"], "[Meternaut] A change to Azure has run")

    def test_the_card_after_a_question_is_the_decision_card_again_with_a_notice_and_a_fresh_token(self):
        brief = brief_of()
        card = cards.card_for(brief, ctx_for(brief, nonce="Fresh-0123456789abcdefghijklmnopq"), "Recorded with your name. It approves nothing. The request stays open.")
        ids = by_id(card)
        self.assertEqual(ids["notice"]["text"], "Recorded with your name. It approves nothing. The request stays open.")
        self.assertEqual(card["body"][2]["id"], "notice")
        self.assertIn("Fresh-0123456789abcdefghijklmnopq", json.dumps(card))
        self.assertNotIn(NONCE, json.dumps(card))

    def test_the_invoke_answers(self):
        card = cards.card_for(brief_of(), ctx_for(brief_of()))
        self.assertEqual(cards.invoke_card(card), {"statusCode": 200, "type": "application/vnd.microsoft.card.adaptive", "value": card})
        self.assertEqual(cards.invoke_message("I cannot take your OK on this request.\nsecond"),
                         {"statusCode": 200, "type": "application/vnd.microsoft.activity.message", "value": "I cannot take your OK on this request. second"})


class TheFirstContactCard(unittest.TestCase):
    def test_three_sentences_one_link_and_the_footer(self):
        card = cards.first_contact_card("Maya", BASE, CONTACTS)
        ids = by_id(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual({a["url"] for a in actions_of(card)}, {f"{BASE}/"})
        self.assertEqual([a["type"] for a in actions_of(card)], ["Action.OpenUrl"])
        self.assertTrue(ids["hello"]["text"].startswith("Hello Maya, I am Meternaut"))
        self.assertTrue(ids["ai-footer"]["text"].startswith("Written by an AI; a person approves every change."))
        self.assertEqual(card["body"][-1]["id"], "ai-footer")
        self.assertNotIn("planCode", json.dumps(card))

    def test_a_name_is_data(self):
        card = cards.first_contact_card(HOSTILE, BASE, ())
        self.assertEqual(cardcheck.check(card), [])
        self.assertNotIn("](", json.dumps(card))
        with self.assertRaises(CardError):
            cards.first_contact_card("Maya", "http://meternaut.example")


class WhatComesFromTheEstateIsData(unittest.TestCase):
    """Text from the estate or from a model goes through brief.plain and is escaped for Markdown: it cannot start a link, a list or a bold run, hide itself or become an address."""

    def hostile_card(self, **extra):
        plan = make_plan(resource_name=HOSTILE, resource_group=HOSTILE, **extra)
        case = make_case(resource_name=HOSTILE, resource_group=HOSTILE, summary=HOSTILE, objections=(HOSTILE,), models={"detective": HOSTILE, "skeptic": "model-s"},
                         owner={"lookedUp": True, "tagOwner": HOSTILE, "createdBy": HOSTILE, "changedBy": HOSTILE, "changedAt": "2026-03-01"},
                         facts={"ageDays": 41, "basis": HOSTILE, "sizeGb": HOSTILE, "sku": HOSTILE, "sizeFamily": HOSTILE})
        brief = brief_of(plan=plan, case=case)
        return cards.decision_card(brief, ctx_for(brief, why=HOSTILE, contacts=(f"{HOSTILE} ({HOSTILE})",)))

    def assert_inert(self, card):
        self.assertEqual(cardcheck.check(card), [])
        allowed = {URL}
        for action in actions_of(card):
            for key in ("url",):
                if key in action:
                    self.assertIn(action[key], allowed)
            self.assertNotIn("evil", json.dumps({k: v for k, v in action.items() if k in ("url", "verb", "data", "title")}))
        for text in texts(card):
            self.assertFalse(any(unicodedata.category(c) in ("Cc", "Cf", "Cs", "Co", "Cn") for c in text), repr(text))
            self.assertNotIn("](", text, "no Markdown link can be made")
            self.assertNotIn("{{", text, "the text features of an Adaptive Card ({{DATE(...)}}) are not given to the estate")
            self.assertNotRegex(text.replace(URL, ""), r"(?i)\b[a-z][a-z0-9+.-]*://", "no scheme is followed by two slashes, so that nothing is made a link")
            bare = re.sub(r"\*\*[A-Za-z ,.:]{1,40}\*\*", "", text)  # the bold labels of the card's own
            self.assertNotRegex(bare, r"(?<!\\)[*_`\[\]<]", f"an unescaped Markdown character in {text!r}")
            self.assertNotRegex(bare, r"(?<!\\)#|(?<!\\)>", f"an unescaped # or > in {text!r}")

    def test_a_hostile_name_group_owner_fact_reason_model_and_contact_is_inert_in_a_card_of_a_change(self):
        self.assert_inert(self.hostile_card())

    def test_the_same_in_a_card_of_advice(self):
        plan = make_advice_plan(resource_name=HOSTILE, resource_group=HOSTILE)
        brief = brief_of(plan=plan, case=make_case(resource_name=HOSTILE, resource_group=HOSTILE, status="needs_human"))
        self.assert_inert(cards.decision_card(brief, ctx_for(brief)))

    def test_the_same_in_the_card_of_what_became_of_a_request(self):
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name=HOSTILE, decision="decline", at="2026-11-05T10:00:00Z", plan_code="7F3K92QD", note=HOSTILE)
        brief = brief_of(plan=make_plan(state="declined", resource_name=HOSTILE), decisions=[decision])
        self.assert_inert(cards.result_card(brief, ctx_for(brief, nonce=""), notice=HOSTILE))

    def test_markdown_in_a_name_shows_as_written(self):
        self.assertEqual(cards.md("[click](https://evil.example/x)"), "\\(click\\)\\(https: //evil.example/x\\)")
        self.assertEqual(cards.md("**bold** _it_ `code` # head > quote"), "\\*\\*bold\\*\\* \\_it\\_ \\`code\\` \\# head \\> quote")
        self.assertEqual(cards.md("<at>Maya</at>"), "\\<at\\>Maya\\</at\\>", "a mention is not made from text")
        self.assertEqual(cards.md("back\\slash"), "back\\\\slash")
        self.assertEqual(cards.md("- item"), "\\- item")
        self.assertEqual(cards.md("1. item"), "1\\. item", "a list marker at the start is not one")
        self.assertEqual(cards.md("1) item"), "1\\) item")
        self.assertEqual(cards.md("a - b 2. c"), "a - b 2. c", "a dash or a number in the middle of a line is not a list")
        self.assertEqual(cards.md("{{DATE(2026-01-01T00:00:00Z,LONG)}}"), "{ {DATE\\(2026-01-01T00:00:00Z,LONG\\)}}", "the date function of a TextBlock is not run on text of the estate")
        self.assertEqual(cards.md("{{{x}}}"), "{ { {x}}}")
        self.assertEqual(cards.gentle("{{TIME(2026-01-01T00:00:00Z)}}"), "{ {TIME(2026-01-01T00:00:00Z)}}")
        self.assertEqual(cards.md("disk-name_01"), "disk-name\\_01")
        self.assertEqual(cards.md("a\u202eb\u200bc\x00d\ne"), "abcd e")
        self.assertEqual(cards.md("x" * 500, 40), "x" * 37 + "...")
        self.assertEqual(cards.gentle("Maya (maya@example.com) *x*"), "Maya (maya@example.com) \\*x\\*")

    def test_no_text_of_the_estate_is_ever_in_an_address(self):
        card = self.hostile_card()
        for node in actions_of(card):
            for key in ("url",):
                if key in node:
                    self.assertEqual(node[key], URL)
        body = {k: v for k, v in card.items() if k != "$schema"}
        self.assertEqual(sorted(set(re.findall(r"https?://[^\s\"\\]+", json.dumps(body)))), [URL])


class TheAddressOfThePage(unittest.TestCase):
    def test_it_is_made_from_the_base_and_the_id_alone(self):
        self.assertEqual(cards.page_url(BASE, "p1a2b3c4d5"), f"{BASE}/ok/p1a2b3c4d5")
        self.assertEqual(cards.page_url(BASE + "/", "p1"), f"{BASE}/ok/p1")
        self.assertEqual(cards.page_url("https://meternaut.example:8443/app", "p_1-2"), "https://meternaut.example:8443/app/ok/p_1-2")

    def test_anything_else_is_refused(self):
        for base in ("", "http://meternaut.example", "meternaut.example", "https://", "https://x.example/../a", "https://x.example/?q=1", "https://x.example/#f", "javascript:alert(1)",
                     "https://x.example/a b", "https://user@x.example", None):
            with self.subTest(base=base):
                with self.assertRaises(CardError):
                    cards.page_url(base, "p1")
        for plan_id in ("", "a/b", "a b", "a?x=1", "../x", "a" * 65, "p1\n", None, "<x>", "a#b"):
            with self.subTest(plan_id=plan_id):
                with self.assertRaises(CardError):
                    cards.page_url(BASE, plan_id)


class WhatACardNeeds(unittest.TestCase):
    def test_a_decision_card_needs_a_token_the_code_and_the_page_of_its_own_request(self):
        brief = brief_of()
        for bad in ("", "short", "has space-0123456789abcdefghij", "x" * 65, None):
            with self.subTest(nonce=bad):
                with self.assertRaises(CardError):
                    cards.decision_card(brief, ctx_for(brief, nonce=bad))
        for url in ("", f"{BASE}/ok/other", "http://meternaut.example/ok/p1a2b3c4d5", f"{BASE}/x/{PLAN_ID}", f"{BASE}/ok/{PLAN_ID}?x=1"):
            with self.subTest(url=url):
                with self.assertRaises(CardError):
                    cards.decision_card(brief, ctx_for(brief, page_url=url))
        with self.assertRaises(CardError):
            cards.decision_card(dataclasses.replace(brief, plan_code=""), ctx_for(brief))

    def test_only_a_request_that_is_open_and_that_the_person_may_answer_has_a_decision_card(self):
        for brief in (brief_of(may_answer=False), brief_of(plan=make_plan(state="declined")), brief_of(plan=make_plan(expires_at="2026-11-04T09:30:00Z")),
                      build_brief(make_case(), None, None, (), now=NOW)):
            with self.subTest(state=brief.state, answers=brief.answers):
                with self.assertRaises(CardError):
                    cards.decision_card(brief, ctx_for(brief))
        brief = brief_of(may_answer=False)
        self.assertEqual(cardcheck.check(cards.card_for(brief, ctx_for(brief, nonce=""))), [], "the card of a request that this person may not answer holds no answer")

    def test_a_card_that_does_not_pass_the_check_is_not_made(self):
        brief = dataclasses.replace(brief_of(), headline="")
        with self.assertRaises(CardError):
            cards.decision_card(brief, ctx_for(brief))


class TheCheckOfACard(unittest.TestCase):
    def good(self):
        brief = brief_of()
        return cards.decision_card(brief, ctx_for(brief))

    def problems(self, change):
        card = self.good()
        change(card)
        return cardcheck.check(card)

    def test_a_good_card_has_no_problem(self):
        self.assertEqual(cardcheck.check(self.good()), [])

    def test_what_the_schema_does_not_know_or_the_project_does_not_use_is_a_problem(self):
        def item(card, id_):
            return by_id(card)[id_]
        cases = {
            "type": (lambda c: c.update({"type": "Card"}), "must be AdaptiveCard"),
            "schema": (lambda c: c.update({"$schema": "x"}), "$schema"),
            "version": (lambda c: c.update({"version": "1.6"}), "must be 1.5"),
            "fallback text": (lambda c: c.update({"fallbackText": ""}), "fallbackText"),
            "an unknown property of the card": (lambda c: c.update({"colour": "red"}), "is not a property of an Adaptive Card"),
            "an unknown element": (lambda c: c["body"].append({"type": "Image", "url": "https://x.example/a.png"}), "is not one that cards use"),
            "a typo in a property": (lambda c: item(c, "headline").update({"wrapp": True}), "is not a property of TextBlock"),
            "no wrap": (lambda c: item(c, "headline").update({"wrap": False}), "wrap must be true"),
            "no text": (lambda c: item(c, "headline").update({"text": " "}), "has no text"),
            "a number as text": (lambda c: item(c, "headline").update({"text": 5}), "must be a string"),
            "a size that does not exist": (lambda c: item(c, "headline").update({"size": "Huge"}), "must be one of"),
            "a weight that does not exist": (lambda c: item(c, "headline").update({"weight": "Heavy"}), "must be one of"),
            "an empty FactSet": (lambda c: item(c, "facts").update({"facts": []}), "has no fact"),
            "a fact with an extra key": (lambda c: item(c, "facts")["facts"][0].update({"x": "y"}), "a fact has a title and a value"),
            "an Action.Submit": (lambda c: item(c, "decisions")["actions"].append({"type": "Action.Submit", "title": "x"}), "no Action.Submit"),
            "an execute without a fallback": (lambda c: item(c, "later").pop("fallback"), "an Action.OpenUrl as its fallback"),
            "an execute that does not say whether it takes input": (lambda c: item(c, "later").pop("associatedInputs"), "associatedInputs says auto or none"),
            "a second link": (lambda c: item(c, "page").update({"url": "https://other.example/x"}), "different links"),
            "a link that is not https": (lambda c: item(c, "page").update({"url": "http://meternaut.example/ok/p"}), "must be an https address"),
            "a required input with no message": (lambda c: item(c, "message").pop("errorMessage"), "errorMessage"),
            "an input with no label": (lambda c: item(c, "message").update({"label": ""}), "needs a label"),
            "a duplicate id": (lambda c: item(c, "headline").update({"id": "ai-footer"}), "used twice"),
            "seven actions": (lambda c: item(c, "decisions")["actions"].extend([dict(item(c, "later"), id=f"x{i}") for i in range(4)]), "at most 6"),
            "a hidden character": (lambda c: item(c, "headline").update({"text": "a\u202eb"}), "direction"),
            "a card that is too large": (lambda c: c["body"].append({"type": "TextBlock", "text": "x" * 21000, "wrap": True}), "at most 20000"),
            "data that is not flat": (lambda c: item(c, "later")["data"].update({"x": {"a": 1}}), "must be a string, a whole number or a boolean"),
            "a width that is not Full": (lambda c: c.update({"msteams": {"width": "Narrow"}}), "may only set the width to Full"),
            "a fallback on an element": (lambda c: item(c, "headline").update({"fallback": "drop"}), "needs a fallback is not used"),
        }
        for name, (change, needle) in cases.items():
            with self.subTest(name):
                found = self.problems(change)
                self.assertTrue(any(needle in line for line in found), (needle, found))

    def test_what_is_not_a_card(self):
        for value in (None, [], "card", 5, {}):
            self.assertTrue(cardcheck.check(value), value)


if __name__ == "__main__":
    unittest.main()
