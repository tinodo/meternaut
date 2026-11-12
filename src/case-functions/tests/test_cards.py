"""The Teams card of a decision brief (cases/cards.py) and its structural check (cases/cardcheck.py).

Every name below is invented (AGENTS.md rule 17): the cards are made from a disk that nobody uses. No test touches the network.

The tests of the decision card in this file make it from a context with no buttons (`ctx_for`), which is the card that goes when the app cannot make the links of its buttons: the facts, the
words and the link to the page of the request only. The card with its buttons (`buttons_for`) is in test_card_buttons.py.
"""
import dataclasses
import datetime as dt
import json
import re
import unicodedata
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
from cases import cardcheck, cardlinks, cards
from cases.brief import Brief, build_brief
from cases.cards import CardContext, CardError, CardTooLarge
from cases.models import ADVISE, ActionRecord, CaseRecord, DecisionRecord, PlanRecord

NOW = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)
BASE = "https://meternaut.example"
OID = "11111111-1111-1111-1111-111111111111"
NAME = "disk-zq7-name"
GROUP = "rg-zq7-group"
PLAN_ID = "p1a2b3c4d5"
CONTACTS = ("Maya (maya@example.com)", "Ops (ops@example.com)")
URL = f"{BASE}/ok/{PLAN_ID}"
TOKEN = "t" * 24  # a link token is 20 to 64 characters of a URL-safe alphabet
HOSTILE = ("[click](https://evil.example/x) **bold** _italic_ `code` # head > quote - item 1. one \u202e\u200bhidden\x00\nsecond line <at>Maya</at> www.evil.example "
           "{{DATE(2000-01-01T00:00:00Z,LONG)}} {{{TIME(2000-01-01T00:00:00Z)}}}")


def make_plan(**changes) -> PlanRecord:
    values = dict(
        plan_id=PLAN_ID, case_id="c1", family="delete-disk", resource_id=f"/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/{NAME}",
        resource_name=NAME, resource_group=GROUP, subscription_id="11111111-2222-3333-4444-555555555555", code="7F3K92QD",
        title=f"Delete an unattached managed disk in resource group {GROUP}",
        what_changes=f"When you approve, Meternaut deletes the disk named {NAME} with your own permissions. It changes nothing else.",
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
    values = dict(page_url=f"{BASE}/ok/{brief.plan_id}", contacts=CONTACTS)
    values.update(changes)
    return CardContext(**values)


def links_for(brief: Brief, *answers: str) -> dict[str, str]:
    """The addresses of the buttons of a card as offers.py makes them (cardlinks.answer_url), with one fixed token for each answer."""
    return {answer: cardlinks.answer_url(f"{BASE}/ok/{brief.plan_id}", answer, brief.plan_code, f"{answer}-{TOKEN}") for answer in (answers or ("approve", "decline"))}


def buttons_for(brief: Brief, *answers: str, **changes) -> CardContext:
    """The context of a card that has its buttons."""
    return ctx_for(brief, links=links_for(brief, *answers), **changes)


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
            if key in ("text", "title", "value", "fallbackText", "tooltip") and isinstance(value, str):
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

    def test_it_passes_the_check_and_is_a_card_of_schema_1_4(self):
        self.assertEqual(cardcheck.check(self.card), [])
        self.assertEqual((self.card["type"], self.card["version"], self.card["$schema"]), ("AdaptiveCard", "1.4", "http://adaptivecards.io/schemas/adaptive-card.json"))
        self.assertEqual(self.card["msteams"], {"width": "Full"})
        self.assertFalse(any("style" in node and node.get("type") == "TextBlock" for node in walk(self.card)), "the style heading came with 1.5, and the card says 1.4")
        json.dumps(self.card)

    def test_it_holds_what_a_person_needs_to_decide_and_nothing_else(self):
        self.assertEqual([n["id"] for n in self.card["body"] if "id" in n],
                         ["header", "headline", "place", "chips", "value-tile", "confidence", "facts", "change", "undo", "risk", "owner", "decisions", "ai-footer"])
        self.assertEqual(self.ids["headline"]["text"], "Delete the unattached disk disk-zq7-name", "the title of the page: the place is on the line under it")
        self.assertEqual(self.ids["place"]["text"], "Managed disk, resource group rg-zq7-group")
        self.assertEqual(self.ids["chips"]["text"], "Medium risk, High confidence, Cannot be undone", "the chips of the page as words")
        self.assertEqual([n["id"] for n in self.ids["value-tile"]["items"]], ["value", "saving-word", "price-basis", "money"])
        self.assertEqual(self.ids["value"]["text"], "$494 a year")
        self.assertEqual(self.ids["saving-word"]["text"], "Saves, Expected. $41.20 a month.")
        self.assertEqual(self.ids["price-basis"]["text"], "Based on the cost lines of the last 30 days.", "every figure carries its basis")
        self.assertEqual(self.ids["money"]["text"], "Money is in US dollars, and a year is twelve times the month.")
        self.assertNotIn("waiting", self.ids, "what waiting costs is on the page: it does not help a person decide, and it pushes")
        self.assertNotIn("when", self.ids, "how long ago it was found and until when it is open are on the page")
        self.assertTrue(self.ids["confidence"]["text"].startswith("**How sure: "))
        self.assertLessEqual(len(self.ids["facts"]["facts"]), 3)
        self.assertTrue(self.ids["change"]["text"].startswith("**If you approve:** "))
        self.assertIn("It runs with your own permissions.", self.ids["change"]["text"], "whose rights it uses")
        self.assertEqual(self.ids["change"]["text"].count("own permissions"), 1)
        self.assertEqual(self.ids["undo"]["text"], "Undo: This cannot be undone.")
        self.assertEqual(self.ids["undo"]["weight"], "Bolder", "an irreversible change is one bold line")
        self.assertTrue(self.ids["risk"]["text"].startswith("**Risk, medium:** "))
        self.assertIn("alice@example.com", self.ids["owner"]["text"])

    def test_no_text_and_no_button_of_the_card_says_sign_in_and_who_makes_the_change_is_said_once(self):
        everything = " ".join(texts(self.card))
        self.assertEqual(re.findall(r"(?i)\bsign(?:s|ed|ing)?[ -]in\b", everything), [])
        self.assertEqual(everything.count("own permissions"), 1)

    def test_the_only_link_is_the_page_of_the_request_and_the_approval_is_made_there(self):
        (page,) = actions_of(self.card)
        self.assertEqual((page["type"], page["title"], page["url"], page["style"]), ("Action.OpenUrl", "Review and decide", URL, "positive"))
        self.assertEqual(self.ids["decisions"]["actions"], [page])
        urls = re.findall(r"https?://\S+", " ".join(texts(self.card)))
        self.assertEqual({u.rstrip(".") for u in urls}, {URL}, "the address is in the text of the fallback and nowhere else")

    def test_it_holds_nothing_to_fill_in_and_nothing_that_sends_an_answer(self):
        # The action of Power Automate that posts the card takes no answer: a button other than a link shows an error there. So no input, no Action.Execute, no Action.Submit, and none of what
        # the answers that a card of the earlier design carried: the code of the plan, a one-time token, a verb.
        kinds = {node.get("type") for node in walk(self.card)}
        self.assertFalse({kind for kind in kinds if str(kind).startswith("Input.")}, kinds)
        self.assertFalse(kinds & {"Action.Execute", "Action.Submit", "Action.Http", "Action.ShowCard", "Action.ToggleVisibility"}, kinds)
        everything = json.dumps(self.card)
        for word in ("nonce", "planCode", "verb", "associatedInputs", "requestId", "7F3K92QD"):
            self.assertNotIn(word, everything)

    def test_the_title_of_the_link_is_the_word_of_the_page(self):
        (page,) = actions_of(self.card)
        self.assertEqual(page["title"], "Review and decide")
        self.assertLessEqual(len(page["title"]), 24, "a button title is short")

    def test_it_says_that_an_ai_wrote_it_why_the_person_got_it_and_who_is_responsible_in_one_footer_line(self):
        self.assertEqual(self.ids["ai-label"]["text"], "Meternaut (AI)")
        footer = self.ids["ai-footer"]["text"]
        self.assertTrue(footer.startswith("Written by an AI (models: model-d, model-s); a person approves every change."), footer)
        self.assertIn("You got this because you are named as an approver of this request.", footer)
        self.assertTrue(footer.endswith("Responsible for Meternaut: Maya (maya@example.com)."), "one person, as on the page: the first of the contacts")
        self.assertNotIn("Ops (ops@example.com)", footer)
        self.assertNotIn("Talk to a person", footer)
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
        for kind, words in (("change", "[Meternaut] A change to Azure waits for your OK"), ("advice", "[Meternaut] A decision waits for you"), ("result", "[Meternaut] A change to Azure has run"),
                            ("first_contact", "[Meternaut] An AI assistant for Azure costs will write to you")):
            self.assertEqual(cards.SUMMARIES[kind], words)
            self.assertNotIn(NAME, cards.SUMMARIES[kind])
            self.assertNotRegex(cards.SUMMARIES[kind], r"\d")
        self.assertFalse(hasattr(cards, "message_activity"), "no activity of a bot: the card goes on a queue, in a message that teamsqueue.py makes")


class TheDecisionCardOfAdvice(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of(plan=make_advice_plan(), case=make_case(status="needs_human"))
        self.card = cards.decision_card(self.brief, ctx_for(self.brief))
        self.ids = by_id(self.card)

    def test_it_holds_the_link_to_the_page_where_the_answer_is_given_and_changes_nothing_in_azure(self):
        self.assertEqual(cardcheck.check(self.card), [])
        self.assertEqual([a["type"] for a in actions_of(self.card)], ["Action.OpenUrl"], "the answers of advice are given on the page, as the approval of a change is")
        self.assertTrue(self.ids["change"]["text"].startswith("**If you answer:** Nothing changes in Azure."))
        self.assertEqual(self.ids["undo"]["text"].split(":**")[0], "**Undo", "advice can be undone: there is nothing to undo, and no bold warning")
        self.assertNotIn("weight", self.ids["undo"])
        (link,) = actions_of(self.card)
        self.assertEqual((link["title"], link["url"]), ("Review and decide", URL))

    def test_one_action_and_nothing_else_on_the_card(self):
        self.assertEqual(len(self.ids["decisions"]["actions"]), 1)
        self.assertEqual(len(actions_of(self.card)), 1)


class TheDecisionCardOfAChangeThatNeedsTwoPeople(unittest.TestCase):
    """The card says that two people are needed and where the request stands for this person. It never confirms or approves: both are made on the page, which is the link."""
    OTHER = "22222222-2222-2222-2222-222222222222"
    DIGEST = "d" * 64

    def card_of(self, viewer=OID, decisions=(), **plan):
        brief = brief_of(plan=make_plan(approval_class="R3", approvers=(OID, self.OTHER), digest=self.DIGEST, **plan), decisions=decisions, viewer=viewer)
        return brief, cards.decision_card(brief, ctx_for(brief))

    def test_it_says_that_two_people_approve_it_and_each_card_says_where_it_stands_for_its_reader(self):
        confirmed = DecisionRecord(PLAN_ID, self.OTHER, "Olga", "confirm", "2026-11-05T09:00:00Z", "7F3K92QD", plan_digest=self.DIGEST)
        stale = DecisionRecord(PLAN_ID, self.OTHER, "Olga", "confirm", "2026-11-05T09:00:00Z", "7F3K92QD", plan_digest="e" * 64)
        for label, viewer, decisions, words in (("first", OID, (), "Nobody has confirmed it yet."), ("mine", self.OTHER, (confirmed,), "You confirmed the request"),
                                                ("second", OID, (confirmed,), "Olga confirmed the request"), ("stale", OID, (stale,), "that confirmation does not count any more")):
            with self.subTest(label):
                _, card = self.card_of(viewer, decisions)
                text = by_id(card)["change"]["text"]
                self.assertIn(words, text)
                self.assertTrue(text.startswith("**If you approve:** "))
                self.assertIn("Two people approve this.", text)
                self.assertEqual(re.findall(r"(?i)\bsign(?:s|ed|ing)?[ -]in\b", " ".join(texts(card))), [])
                self.assertEqual(" ".join(texts(card)).count("own permissions"), 1, "who makes the change is said once, whatever the stage")
                self.assertEqual(cardcheck.check(card), [])

    def test_no_card_has_a_button_that_confirms_or_approves_and_the_link_is_the_way_to_both(self):
        for viewer, decisions in ((OID, ()), (self.OTHER, ())):
            _, card = self.card_of(viewer, decisions)
            self.assertEqual([a["type"] for a in actions_of(card)], ["Action.OpenUrl"])
            (page,) = [a for a in by_id(card)["decisions"]["actions"] if a["type"] == "Action.OpenUrl"]
            self.assertEqual((page["title"], page["url"]), ("Review and decide", URL))

    def test_a_request_that_nobody_can_approve_says_so_and_offers_only_the_page(self):
        brief = brief_of(plan=make_plan(approval_class="R3", approvers=(OID,)), viewer=OID)
        card = cards.decision_card(brief, ctx_for(brief))
        self.assertIn("fewer than two people are listed as approvers", by_id(card)["change"]["text"])
        (page,) = [a for a in by_id(card)["decisions"]["actions"] if a["type"] == "Action.OpenUrl"]
        self.assertEqual(page["title"], "See the request")

    def test_a_request_for_one_person_says_nothing_of_two(self):
        self.assertNotIn("Two people", by_id(cards.decision_card(brief_of(), ctx_for(brief_of())))["change"]["text"])


class TheFigureOnTheCard(unittest.TestCase):
    """The tile of the card says what the page says: the year, the label with the month, the basis or the reason, and once that money is in US dollars."""

    MONEY = "Money is in US dollars, and a year is twelve times the month."

    def tile(self, saving=41.2, cost=41.2, **case_changes):
        brief = brief_of(plan=make_plan(saving_usd_month=saving), case=make_case(saving_usd_month=saving, cost_usd_30d=cost, **case_changes))
        card = cards.decision_card(brief, ctx_for(brief))
        self.assertEqual(cardcheck.check(card), [])
        ids = by_id(card)
        return card, {name: ids[name]["text"] for name in ("value", "saving-word", "price-basis", "money") if name in ids}

    def test_a_saving_is_the_year_in_large_type_the_label_with_the_month_the_basis_and_the_line_about_money(self):
        card, tile = self.tile()
        self.assertEqual(tile, {"value": "$494 a year", "saving-word": "Saves, Expected. $41.20 a month.", "price-basis": "Based on the cost lines of the last 30 days.", "money": self.MONEY})
        self.assertEqual(by_id(card)["value"]["size"], "Large")
        self.assertEqual([item["id"] for item in by_id(card)["value-tile"]["items"]], ["value", "saving-word", "price-basis", "money"])

    def test_the_level_is_in_the_label_a_scenario_says_what_it_rests_on(self):
        _, tile = self.tile(detector="advisor-cost")
        self.assertEqual((tile["saving-word"], tile["price-basis"]), ("Saves, Scenario. $41.20 a month.", "Based on Azure Advisor's own estimate: no cost line of this resource backs it."))

    def test_a_cost_is_the_most_that_a_change_could_save_and_says_that_no_saving_was_measured(self):
        _, tile = self.tile(saving=None, cost=358.11)
        self.assertEqual(tile, {"value": "$4,297 a year", "saving-word": "Costs, saving not measured. $358.11 a month.",
                                "price-basis": "The most that a change could save: what it would save was not worked out.", "money": self.MONEY})

    def test_nothing_that_can_be_shown_has_no_year_and_no_money_line_and_says_why(self):
        for cost, why in ((0.0, "Azure has no cost line for this yet."), (None, "No cost line was read yet.")):
            with self.subTest(cost=cost):
                card, tile = self.tile(saving=None, cost=cost)
                self.assertEqual(tile, {"saving-word": "Cost not visible.", "price-basis": why})
                self.assertNotIn("a year", " ".join(texts(card)))

    def test_the_line_about_money_is_said_once_on_a_card(self):
        for kwargs in ({}, {"saving": None, "cost": 80.0}):
            card, _ = self.tile(**kwargs)
            self.assertEqual(sum(text.count(self.MONEY) for text in texts(card)), 1)

    def test_no_card_says_no_figure_no_saving_is_shown_or_talk_to_a_person(self):
        for kwargs in ({}, {"saving": None, "cost": 80.0}, {"saving": None, "cost": None}):
            card, _ = self.tile(**kwargs)
            everything = " ".join(texts(card))
            for old in ("No figure", "No saving is shown", "Talk to a person", "About 41.20 US dollars"):
                self.assertNotIn(old, everything)


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

    def test_advice_that_is_held_has_no_review_and_decide_and_says_so(self):
        brief = brief_of(plan=make_advice_plan(), case=make_case(status="needs_human"), changes_paused=True)
        self.assertNotIn("approve", brief.answers)
        card = cards.decision_card(brief, ctx_for(brief))
        self.assertIn("Meternaut is paused here.", by_id(card)["paused"]["text"])
        (link,) = actions_of(card)
        self.assertEqual(link["title"], "See the request")


class TheCardOfWhatBecameOfARequest(unittest.TestCase):
    def test_a_declined_request_shows_who_and_has_no_answer(self):
        plan = make_plan(state="declined")
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name="Maya", decision="decline", at="2026-11-05T10:00:00Z", plan_code="7F3K92QD")
        brief = brief_of(plan=plan, decisions=[decision])
        card = cards.result_card(brief, ctx_for(brief))
        ids = by_id(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(ids["outcome"]["text"], "Declined")
        self.assertIn("Declined by Maya.", ids["outcome-line-1"]["text"])
        self.assertEqual([a["type"] for a in actions_of(card)], ["Action.OpenUrl"])
        self.assertNotIn("planCode", json.dumps(card))
        self.assertEqual(ids["kind"]["text"], "Recorded")

    def test_advice_that_was_answered_says_that_nothing_changed_in_azure(self):
        plan = make_advice_plan(state="consumed")
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name="Maya", decision="approve", at="2026-11-05T10:00:00Z", plan_code="7F3K92QD")
        brief = brief_of(plan=plan, case=make_case(status="acknowledged"), decisions=[decision])
        ids = by_id(cards.result_card(brief, ctx_for(brief)))
        self.assertEqual(ids["outcome"]["text"], "Worth acting on")
        self.assertIn("Nothing was changed in Azure.", ids["outcome-line-2"]["text"])

    def test_an_expired_request_says_so(self):
        brief = brief_of(plan=make_plan(expires_at="2026-11-04T09:30:00Z"))
        self.assertEqual(brief.state, "expired")
        ids = by_id(cards.result_card(brief, ctx_for(brief)))
        self.assertEqual(ids["outcome"]["text"], "Expired")

    def test_a_change_that_ran_has_a_result_card_with_what_it_saves_in_the_words_of_the_pages_and_the_undo_line(self):
        plan = make_plan(state="consumed")
        action = ActionRecord(plan_id=PLAN_ID, case_id="c1", family="delete-disk", resource_id="r1", state="verified", queued_at="2026-11-05T09:00:00Z", finished_at="2026-11-05T09:05:00Z",
                              result="Deleted. Azure no longer lists the resource.", verification={"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 41.2, "checkedAt": "2026-11-05T09:05:00Z"})
        decision = DecisionRecord(plan_id=PLAN_ID, approver_oid=OID, approver_name="Maya", decision="approve", at="2026-11-05T09:00:00Z", plan_code="7F3K92QD")
        brief = brief_of(plan=plan, action=action, decisions=[decision])
        card = cards.result_card(brief, ctx_for(brief))
        ids = by_id(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(ids["outcome"]["text"], "Done and checked")
        self.assertEqual((ids["value"]["text"], ids["saving-word"]["text"]), ("$494 a year", "Saves, Verified. $41.20 a month."), "Verified, and only because the cost lines confirm it")
        self.assertEqual(ids["price-basis"]["text"], "Based on the cost lines after the change, which show no cost for this resource.")
        self.assertEqual(ids["place"]["text"], "Managed disk, resource group rg-zq7-group")
        self.assertEqual(ids["undo"]["text"], "Undo: This cannot be undone.")
        self.assertEqual([a["title"] for a in actions_of(card)], ["See the request"])


class TheShortCard(unittest.TestCase):
    """The card for a message that cannot hold the whole card: the headline, one line, the one link and the footer, made from the same brief."""

    def short_of(self, brief):
        card = cards.minimal_card(brief, ctx_for(brief))
        self.assertEqual(cardcheck.check(card), [])
        return card, by_id(card)

    def test_a_request_that_waits_gets_its_headline_the_link_that_decides_and_the_footer(self):
        brief = brief_of()
        card, ids = self.short_of(brief)
        self.assertEqual([n["id"] for n in card["body"] if "id" in n], ["header", "headline", "short", "decisions", "ai-footer"])
        self.assertEqual(ids["headline"]["text"], by_id(cards.decision_card(brief, ctx_for(brief)))["headline"]["text"])
        self.assertEqual(ids["short"]["text"], cards.SHORT_CARD)
        self.assertEqual(ids["kind"]["text"], "Needs your OK")
        (page,) = actions_of(card)
        self.assertEqual((page["title"], page["url"]), ("Review and decide", URL))
        self.assertEqual(ids["ai-label"]["text"], "Meternaut (AI)")
        self.assertIn("Written by an AI", ids["ai-footer"]["text"])
        self.assertLess(cardcheck.size_of(card), 2000)

    def test_advice_and_a_request_that_is_over_are_told_in_the_same_way(self):
        for label, brief, kind, title in (("advice", brief_of(plan=make_advice_plan(), case=make_case(status="needs_human")), "Needs your answer", "Review and decide"),
                                          ("over", brief_of(plan=make_plan(state="declined")), "Recorded", "See the request"),
                                          ("held", brief_of(changes_paused=True), "Needs your OK", "See the request")):
            with self.subTest(label):
                card, ids = self.short_of(brief)
                self.assertEqual((ids["kind"]["text"], [a["title"] for a in actions_of(card)]), (kind, [title]))

    def test_a_hostile_name_is_inert_on_it_too(self):
        brief = brief_of(plan=make_plan(resource_name=HOSTILE), case=make_case(resource_name=HOSTILE, summary=HOSTILE))
        card = cards.minimal_card(brief, ctx_for(brief))
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual({a["url"] for a in actions_of(card)}, {URL})
        self.assertNotIn("](", json.dumps(card))

    def test_a_card_that_passes_every_check_but_its_size_is_too_large_and_the_short_card_still_fits(self):
        brief = brief_of()
        short = cardcheck.size_of(cards.minimal_card(brief, ctx_for(brief)))
        with mock.patch.object(cardcheck, "MAX_BYTES", short + 100):
            with self.assertRaises(CardTooLarge):
                cards.decision_card(brief, ctx_for(brief))
            self.assertEqual(cardcheck.check(cards.minimal_card(brief, ctx_for(brief))), [])
        with mock.patch.object(cardcheck, "MAX_BYTES", 100):
            with self.assertRaises(CardError) as raised:
                cards.minimal_card(brief, ctx_for(brief))
            self.assertIsInstance(raised.exception, CardTooLarge, "nothing smaller exists: the caller says that the card could not be made")

    def test_a_card_that_fails_for_another_reason_is_not_a_card_that_is_too_large(self):
        brief = dataclasses.replace(brief_of(), headline="")
        with mock.patch.object(cardcheck, "MAX_BYTES", 100):
            with self.assertRaises(CardError) as raised:
                cards.decision_card(brief, ctx_for(brief))
        self.assertNotIsInstance(raised.exception, CardTooLarge)


class TheFirstContactCard(unittest.TestCase):
    def test_three_sentences_one_link_and_the_footer(self):
        card = cards.first_contact_card("Maya", BASE, CONTACTS)
        ids = by_id(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual({a["url"] for a in actions_of(card)}, {f"{BASE}/"})
        self.assertEqual([a["type"] for a in actions_of(card)], ["Action.OpenUrl"])
        self.assertTrue(ids["hello"]["text"].startswith("Hello Maya, I am Meternaut"))
        self.assertEqual(ids["rules"]["text"], "I change nothing myself. You answer a request with the buttons on its card: an answer button opens a page of mine that sends your answer, "
                                               "and a change to Azure runs with your own Azure rights.")
        self.assertNotIn("cannot answer", json.dumps(card), "a card can be answered now")
        self.assertEqual(re.findall(r"(?i)\bsign(?:s|ed|ing)?[ -]in\b", json.dumps(card)), [])
        self.assertTrue(ids["ai-footer"]["text"].startswith("Written by an AI; a person approves every change."))
        self.assertEqual(card["body"][-1]["id"], "ai-footer")
        self.assertNotIn("planCode", json.dumps(card))
        self.assertEqual(card["version"], "1.4")

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
        self.assert_inert(cards.result_card(brief, ctx_for(brief)))

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
    def test_a_decision_card_needs_the_page_of_its_own_request(self):
        brief = brief_of()
        for url in ("", f"{BASE}/ok/other", "http://meternaut.example/ok/p1a2b3c4d5", f"{BASE}/x/{PLAN_ID}", f"{BASE}/ok/{PLAN_ID}?x=1"):
            with self.subTest(url=url):
                with self.assertRaises(CardError):
                    cards.decision_card(brief, ctx_for(brief, page_url=url))
                with self.assertRaises(CardError):
                    cards.minimal_card(brief, ctx_for(brief, page_url=url))
        with self.assertRaises(TypeError, msg="a card takes no token: the context has none"):
            CardContext(page_url=URL, nonce="N0nce-0123456789abcdefghijklmnop")

    def test_only_a_request_that_is_open_and_that_the_person_may_answer_has_a_decision_card(self):
        for brief in (brief_of(may_answer=False), brief_of(plan=make_plan(state="declined")), brief_of(plan=make_plan(expires_at="2026-11-04T09:30:00Z")),
                      build_brief(make_case(), None, None, (), now=NOW)):
            with self.subTest(state=brief.state, answers=brief.answers):
                with self.assertRaises(CardError):
                    cards.decision_card(brief, ctx_for(brief))
        brief = brief_of(may_answer=False)
        self.assertEqual(cardcheck.check(cards.result_card(brief, ctx_for(brief))), [], "the card of a request that this person may not answer holds no answer")

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
            "version 1.6": (lambda c: c.update({"version": "1.6"}), "must be 1.4"),
            "version 1.5": (lambda c: c.update({"version": "1.5"}), "must be 1.4"),
            "fallback text": (lambda c: c.update({"fallbackText": ""}), "fallbackText"),
            "an unknown property of the card": (lambda c: c.update({"colour": "red"}), "is not a property of an Adaptive Card"),
            "an unknown element": (lambda c: c["body"].append({"type": "Image", "url": "https://x.example/a.png"}), "is not one that cards use"),
            "a text box": (lambda c: c["body"].append({"type": "Input.Text", "id": "message", "label": "Ask"}), "is not one that cards use"),
            "a typo in a property": (lambda c: item(c, "headline").update({"wrapp": True}), "is not a property of TextBlock"),
            "the style heading, which came with 1.5": (lambda c: item(c, "headline").update({"style": "heading"}), "is not a property of TextBlock"),
            "no wrap": (lambda c: item(c, "headline").update({"wrap": False}), "wrap must be true"),
            "no text": (lambda c: item(c, "headline").update({"text": " "}), "has no text"),
            "a number as text": (lambda c: item(c, "headline").update({"text": 5}), "must be a string"),
            "a size that does not exist": (lambda c: item(c, "headline").update({"size": "Huge"}), "must be one of"),
            "a weight that does not exist": (lambda c: item(c, "headline").update({"weight": "Heavy"}), "must be one of"),
            "an empty FactSet": (lambda c: item(c, "facts").update({"facts": []}), "has no fact"),
            "a fact with an extra key": (lambda c: item(c, "facts")["facts"][0].update({"x": "y"}), "a fact has a title and a value"),
            "an Action.Submit": (lambda c: item(c, "decisions")["actions"].append({"type": "Action.Submit", "title": "x"}), "no Action.Submit"),
            "an Action.Execute": (lambda c: item(c, "decisions")["actions"].append({"type": "Action.Execute", "title": "x", "verb": "later"}), "no Action.Execute"),
            "more actions than a card has": (lambda c: item(c, "decisions")["actions"].extend({"type": "Action.OpenUrl", "title": f"Again {n}", "url": URL} for n in range(6)),
                                             "has 7 actions, and a card has at most 6"),
            "a fallback on an action": (lambda c: item(c, "page").update({"fallback": {"type": "Action.OpenUrl", "title": "x", "url": URL}}), "is not a property of Action.OpenUrl"),
            "a second page": (lambda c: item(c, "page").update({"url": "https://other.example/x"}) or c.update({"actions": [{"type": "Action.OpenUrl", "title": "x", "url": URL}]}), "different pages"),
            "a link that is not https": (lambda c: item(c, "page").update({"url": "http://meternaut.example/ok/p"}), "must be an https address"),
            "a duplicate id": (lambda c: item(c, "headline").update({"id": "ai-footer"}), "used twice"),
            "a hidden character": (lambda c: item(c, "headline").update({"text": "a\u202eb"}), "direction"),
            "a card that is too large": (lambda c: c["body"].append({"type": "TextBlock", "text": "x" * 21000, "wrap": True}), "at most 20000"),
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
