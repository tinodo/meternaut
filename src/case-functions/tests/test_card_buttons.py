"""The buttons of the Teams card that answer (cases/cards.py, cases/cardlinks.py, and the check of a card in cases/cardcheck.py).

A card carries the decision: "Approve" and "Decline" (a change), "Confirm" (the first of two people), "Worth acting on" and "Not worth it" (advice), and "Open the request". Each is a link to a page of
the function app, because the action of Power Automate that posts the card takes no answer. A change that cannot be undone asks twice on the card itself ("Approve" shows the question, and only
"Yes, delete it" is the link). Every name below is invented (AGENTS.md rule 17). No test touches the network.
"""
import json
import re
import unittest
from dataclasses import replace

import familysupport as fs
from test_cards import (BASE, CONTACTS, GROUP, HOSTILE, NAME, OID, PLAN_ID, TOKEN, URL, actions_of, brief_of, buttons_for, by_id, ctx_for, links_for, make_advice_plan, make_case,
                        make_plan, texts, walk)
from test_families_briefs import MAKERS, REVERSIBLE, a_brief, made

from cases import cardcheck, cardlinks, cards
from cases.brief import Brief
from cases.cards import CardContext, CardError
from cases.models import DecisionRecord

OTHER = "22222222-2222-2222-2222-222222222222"
DIGEST = "d" * 64
APPROVE_URL = f"{URL}/approve?code=7F3K92QD&token=approve-{TOKEN}"
DECLINE_URL = f"{URL}/decline?code=7F3K92QD&token=decline-{TOKEN}"
CONFIRM_URL = f"{URL}/confirm?code=7F3K92QD&token=confirm-{TOKEN}"


def setUpModule():
    global _planting
    _planting = fs.as_if_gateways_were_planted()  # the family that scales a gateway needs one on the planted list, as test_families_briefs does
    _planting.start()


def tearDownModule():
    _planting.stop()


def reversible_plan(**changes):
    """A change that can be undone: stop a machine."""
    return make_plan(family="stop-vm", title="Stop the virtual machine vm-zq7 in group rg-zq7-group", resource_name="vm-zq7", undo="Start the machine again.", **changes)


def titles(card) -> list[str]:
    return [action["title"] for action in by_id(card)["decisions"]["actions"]]


def urls(card) -> list[str]:
    return [node["url"] for node in walk(card) if node.get("type") == "Action.OpenUrl"]


class TheButtonsOfAChangeThatCanBeUndone(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of(plan=reversible_plan(), case=make_case(resource_type="microsoft.compute/virtualmachines", resource_name="vm-zq7"))
        self.card = cards.decision_card(self.brief, buttons_for(self.brief))
        self.ids = by_id(self.card)

    def test_approve_and_decline_are_links_and_the_page_of_the_request_is_the_third_button(self):
        self.assertEqual(cardcheck.check(self.card), [])
        self.assertTrue(self.brief.undo.reversible)
        approve, decline, page = self.ids["decisions"]["actions"]
        self.assertEqual((approve["type"], approve["title"], approve["url"], approve["style"]), ("Action.OpenUrl", "Approve", APPROVE_URL, "positive"))
        self.assertEqual((decline["type"], decline["title"], decline["url"]), ("Action.OpenUrl", "Decline", DECLINE_URL))
        self.assertNotIn("style", decline, "one main button")
        self.assertEqual((page["type"], page["title"], page["url"]), ("Action.OpenUrl", "Open the request", URL))
        self.assertNotIn("sure", self.ids, "a change that can be undone asks once, on the button")
        self.assertEqual({node.get("type") for node in walk(self.card)} & {"Action.ToggleVisibility", "Action.Submit", "Action.Execute", "Action.ShowCard"}, set())

    def test_it_holds_the_same_facts_as_the_card_without_buttons_and_only_the_buttons_differ(self):
        plain = cards.decision_card(self.brief, ctx_for(self.brief))
        self.assertEqual([n["id"] for n in self.card["body"] if "id" in n], [n["id"] for n in plain["body"] if "id" in n])
        for name in ("headline", "place", "chips", "value-tile", "confidence", "facts", "change", "undo", "risk", "owner", "ai-footer"):
            self.assertEqual(by_id(plain)[name], self.ids[name], name)
        self.assertEqual(titles(plain), ["Review and decide"])
        self.assertEqual(titles(self.card), ["Approve", "Decline", "Open the request"])

    def test_the_fallback_text_names_the_page_and_no_token(self):
        self.assertIn(URL, self.card["fallbackText"])
        self.assertNotIn("token", self.card["fallbackText"])
        self.assertNotIn("code=", self.card["fallbackText"])

    def test_every_title_is_short_and_none_says_sign_in(self):
        for text in texts(self.card):
            self.assertNotRegex(text, r"(?i)\bsign(?:s|ed|ing)?[ -]in\b")
        for action in actions_of(self.card):
            self.assertLessEqual(len(action["title"]), 24)

    def test_the_text_says_once_that_the_change_runs_with_the_persons_own_permissions_and_asks_nothing(self):
        self.assertEqual(" ".join(texts(self.card)).count("own permissions"), 1)
        self.assertNotIn("?", " ".join(t for t in texts(self.card) if t != self.card["fallbackText"]))


class TheQuestionOfAChangeThatCannotBeUndone(unittest.TestCase):
    """The card asks twice itself, so that nobody is sent to a second page to be asked again: "Approve" shows the question (Teams does that without calling anybody), and only "Yes, delete it" is a
    link that approves."""

    def setUp(self):
        self.brief = brief_of()
        self.card = cards.decision_card(self.brief, buttons_for(self.brief))
        self.ids = by_id(self.card)

    def test_approve_opens_the_question_and_is_no_link(self):
        self.assertEqual(cardcheck.check(self.card), [])
        self.assertFalse(self.brief.undo.reversible)
        approve, decline, page = self.ids["decisions"]["actions"]
        self.assertEqual((approve["type"], approve["title"], approve["style"]), ("Action.ToggleVisibility", "Approve", "positive"))
        self.assertNotIn("url", approve)
        self.assertEqual(approve["targetElements"], [{"elementId": "sure", "isVisible": True}], "it shows the question and never hides it, so that a second press cannot turn it off")
        self.assertTrue(approve["tooltip"], "what a screen reader says")
        self.assertEqual((decline["type"], decline["url"], page["url"]), ("Action.OpenUrl", DECLINE_URL, URL))

    def test_the_question_is_hidden_until_approve_is_pressed_and_says_what_is_lost_and_where(self):
        sure = self.ids["sure"]
        self.assertEqual((sure["type"], sure["isVisible"]), ("Container", False))
        text = self.ids["sure-text"]["text"]
        self.assertEqual(text, "This cannot be undone: Managed disk disk-zq7-name in resource group rg-zq7-group is lost. A deleted disk cannot be restored. A new, empty disk can be made.")
        self.assertEqual(self.ids["sure-text"]["weight"], "Bolder")
        self.assertEqual([n["id"] for n in self.card["body"] if "id" in n][-3:], ["decisions", "sure", "ai-footer"], "the question follows the buttons that open it")

    def test_no_go_back_comes_first_and_is_the_main_button_and_yes_is_the_only_link_that_approves(self):
        back, yes = self.ids["sure-actions"]["actions"]
        self.assertEqual((back["type"], back["title"], back["style"]), ("Action.ToggleVisibility", "No, go back", "positive"))
        self.assertEqual(back["targetElements"], [{"elementId": "sure", "isVisible": False}])
        self.assertTrue(back["tooltip"])
        self.assertEqual((yes["type"], yes["title"], yes["url"], yes["style"]), ("Action.OpenUrl", "Yes, delete it", APPROVE_URL, "destructive"))
        self.assertEqual(urls(self.card).count(APPROVE_URL), 1, "the address that approves is on the Yes alone")
        self.assertEqual(sorted(urls(self.card)), sorted([APPROVE_URL, DECLINE_URL, URL]))

    def test_the_word_after_yes_is_the_verb_of_the_family_and_only_a_change_that_cannot_be_undone_asks(self):
        asked = {}
        for name in MAKERS:
            _, plan, case = made(name)
            b = a_brief(plan, case)
            context = buttons_for(b)
            card = cards.decision_card(b, context)
            self.assertEqual(cardcheck.check(card), [], name)
            has_question = "sure" in by_id(card)
            asked[name] = has_question
            self.assertEqual(has_question, not REVERSIBLE[name], name)
            if has_question:
                self.assertEqual(by_id(card)["sure-yes"]["title"], f"Yes, {b_called(b)} it", name)
            else:
                self.assertEqual(by_id(card)["approve"]["type"], "Action.OpenUrl", name)
        self.assertEqual(sorted(name for name, yes in asked.items() if yes), ["delete-disk", "delete-idle-resource", "delete-public-ip"])

    def test_a_name_from_the_estate_is_data_in_the_question_too(self):
        brief = brief_of(plan=make_plan(resource_name=HOSTILE, resource_group=HOSTILE), case=make_case(resource_name=HOSTILE, resource_group=HOSTILE))
        card = cards.decision_card(brief, buttons_for(brief))
        self.assertEqual(cardcheck.check(card), [])
        text = by_id(card)["sure-text"]["text"]
        self.assertTrue(text.startswith("This cannot be undone: "))
        self.assertNotIn("](", text)
        self.assertNotIn("{{", text)
        self.assertEqual(sorted(set(re.findall(r"https?://[^\s\"\\]+", json.dumps({k: v for k, v in card.items() if k != "$schema"})))), sorted([URL, APPROVE_URL, DECLINE_URL]))


def b_called(b: Brief) -> str:
    from cases.brief import called_of
    return called_of(b.family)


class TheButtonsOfAChangeThatNeedsTwoPeople(unittest.TestCase):
    """The first person confirms (which changes nothing, so the card does not ask twice), the second approves, and a person who confirmed already or who has nobody to approve with is sent to the
    page."""

    def card_of(self, viewer=OID, decisions=(), approvers=(OID, OTHER), **links):
        brief = brief_of(plan=make_plan(approval_class="R3", approvers=approvers, digest=DIGEST), decisions=decisions, viewer=viewer)
        answers = links.get("answers", ("confirm", "approve", "decline"))
        return brief, cards.decision_card(brief, buttons_for(brief, *answers))

    def test_the_first_person_has_confirm_and_decline_and_the_card_says_that_two_people_approve(self):
        brief, card = self.card_of()
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(titles(card), ["Confirm", "Decline", "Open the request"])
        first, decline, _ = by_id(card)["decisions"]["actions"]
        self.assertEqual((first["type"], first["url"], first["style"]), ("Action.OpenUrl", CONFIRM_URL, "positive"))
        self.assertNotIn("sure", by_id(card), "confirming changes nothing, so the card does not ask twice")
        self.assertIn("Two people approve this.", by_id(card)["change"]["text"])
        self.assertIn("Nobody has confirmed it yet.", by_id(card)["change"]["text"])
        self.assertEqual(cards.answers_of(brief), (("confirm", False), ("decline", False)))

    def test_the_second_person_approves_and_a_delete_asks_twice(self):
        confirmed = DecisionRecord(PLAN_ID, OTHER, "Olga", "confirm", "2026-11-05T09:00:00Z", "7F3K92QD", plan_digest=DIGEST)
        brief, card = self.card_of(OID, (confirmed,))
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(titles(card), ["Approve", "Decline", "Open the request"])
        self.assertEqual(by_id(card)["approve"]["type"], "Action.ToggleVisibility")
        self.assertEqual(by_id(card)["sure-yes"]["url"], APPROVE_URL)
        self.assertIn("Olga confirmed the request", by_id(card)["change"]["text"])
        self.assertEqual(cards.answers_of(brief), (("approve", True), ("decline", False)))

    def test_a_confirmation_that_is_out_of_date_has_to_be_made_again(self):
        stale = DecisionRecord(PLAN_ID, OTHER, "Olga", "confirm", "2026-11-05T09:00:00Z", "7F3K92QD", plan_digest="e" * 64)
        brief, card = self.card_of(OID, (stale,))
        self.assertEqual(titles(card), ["Confirm", "Decline", "Open the request"])
        self.assertEqual(by_id(card)["decisions"]["actions"][0]["url"], CONFIRM_URL)

    def test_a_person_who_confirmed_already_and_a_request_with_nobody_to_approve_it_get_the_page_only(self):
        confirmed = DecisionRecord(PLAN_ID, OID, "Maya", "confirm", "2026-11-05T09:00:00Z", "7F3K92QD", plan_digest=DIGEST)
        for label, (brief, card) in (("mine", self.card_of(OID, (confirmed,), approvers=(OID, OTHER))), ("alone", self.card_of(OID, (), approvers=(OID,)))):
            with self.subTest(label):
                self.assertEqual(cardcheck.check(card), [])
                self.assertEqual(cards.answers_of(brief), ())
                self.assertEqual(titles(card), ["See the request"])
                self.assertEqual(urls(card), [URL])


class TheButtonsOfAdvice(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of(plan=make_advice_plan(), case=make_case(status="needs_human"))
        self.card = cards.decision_card(self.brief, buttons_for(self.brief))

    def test_the_answers_are_worth_acting_on_and_not_worth_it_and_both_are_links(self):
        self.assertEqual(cardcheck.check(self.card), [])
        yes, no, page = by_id(self.card)["decisions"]["actions"]
        self.assertEqual((yes["type"], yes["title"], yes["url"], yes["style"]), ("Action.OpenUrl", "Worth acting on", APPROVE_URL, "positive"))
        self.assertEqual((no["type"], no["title"], no["url"]), ("Action.OpenUrl", "Not worth it", DECLINE_URL))
        self.assertEqual((page["title"], page["url"]), ("Open the request", URL))
        self.assertNotIn("sure", by_id(self.card), "advice changes nothing in Azure: nothing is asked twice")
        self.assertTrue(by_id(self.card)["change"]["text"].startswith("**If you answer:** Nothing changes in Azure."))

    def test_the_words_are_those_of_the_page(self):
        from cases.web import words
        labels = words.ANSWER_LABEL["advice"]
        self.assertEqual((labels["approve"], labels["decline"]), ("Worth acting on", "Not worth it"))
        self.assertEqual(cardlinks.LABEL["advice"], {"approve": labels["approve"], "decline": labels["decline"]})
        self.assertEqual((cardlinks.LABEL["change"]["approve"], cardlinks.LABEL["change"]["decline"], words.ANSWER_LABEL["change"]["approve"], words.ANSWER_LABEL["change"]["decline"]),
                         ("Approve", "Decline", "Approve", "Decline"))


class WhenNothingCanBeAnsweredOnTheCard(unittest.TestCase):
    def test_a_switch_that_holds_the_answers_leaves_the_link_to_the_page_and_says_so(self):
        for label, brief in (("a change", brief_of(changes_paused=True)), ("advice", brief_of(plan=make_advice_plan(), case=make_case(status="needs_human"), changes_paused=True))):
            with self.subTest(label):
                card = cards.decision_card(brief, buttons_for(brief))
                self.assertEqual(cardcheck.check(card), [])
                self.assertEqual(cards.answers_of(brief), ())
                self.assertEqual(titles(card), ["See the request"])
                self.assertIn("paused", by_id(card)["paused"]["text"])
                self.assertEqual(urls(card), [URL], "no button that answers is on a card that nothing can answer")

    def test_a_request_that_is_over_or_that_this_person_may_not_answer_has_no_answers_either(self):
        for label, brief in (("declined", brief_of(plan=make_plan(state="declined"))), ("expired", brief_of(plan=make_plan(expires_at="2026-11-04T09:30:00Z"))),
                             ("not theirs", brief_of(may_answer=False)), ("a finding", brief_of(plan=make_advice_plan(state="consumed")))):
            with self.subTest(label):
                self.assertEqual(cards.answers_of(brief), ())

    def test_a_look_that_refuses_the_change_takes_the_answer_that_approves_away_from_the_card_too(self):
        from cases.models import REFUSED, Readiness
        brief = brief_of(ready=Readiness(REFUSED, "the disk is attached now"))
        self.assertNotIn("approve", brief.answers)
        self.assertEqual(cards.answers_of(brief), ())
        card = cards.decision_card(brief, buttons_for(brief))
        self.assertEqual(titles(card), ["See the request"])


class WhenTheLinksCannotBeMade(unittest.TestCase):
    """The records may be out of reach when the card is built. The person still gets the card, with the link to the page of the request, where every answer can be given."""

    def test_a_card_without_its_links_has_the_page_only_and_the_older_words(self):
        brief = brief_of()
        for label, context in (("none", ctx_for(brief)), ("only decline", ctx_for(brief, links=links_for(brief, "decline"))), ("only approve", ctx_for(brief, links=links_for(brief, "approve")))):
            with self.subTest(label):
                card = cards.decision_card(brief, context)
                self.assertEqual(cardcheck.check(card), [])
                self.assertEqual(titles(card), ["Review and decide"])
                self.assertEqual(urls(card), [URL])
                self.assertNotIn("sure", by_id(card))

    def test_the_short_card_of_a_request_that_did_not_fit_has_no_buttons_even_when_it_is_given_the_links(self):
        brief = brief_of()
        card = cards.minimal_card(brief, buttons_for(brief))
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual((titles(card), urls(card)), (["Review and decide"], [URL]), "a person does not decide on a card whose details were left out")

    def test_the_card_of_what_became_of_a_request_has_the_page_only(self):
        brief = brief_of(plan=make_plan(state="declined"))
        card = cards.result_card(brief, buttons_for(brief))
        self.assertEqual((titles(card), urls(card)), (["See the request"], [URL]))


class TheAddressesOfTheButtons(unittest.TestCase):
    def test_a_context_takes_only_the_addresses_that_cardlinks_makes_for_this_request(self):
        brief = brief_of()
        good = links_for(brief)
        other = cardlinks.answer_url(f"{BASE}/ok/other", "approve", "7F3K92QD", "x" * 24)
        for label, links in (("the page of another request", {**good, "approve": other}), ("an answer that is not one", {**good, "later": good["approve"]}),
                             ("an address under another answer", {**good, "approve": good["decline"]}), ("not https", {**good, "approve": good["approve"].replace("https", "http")}),
                             ("a query that is more", {**good, "approve": good["approve"] + "&x=1"}), ("no token", {**good, "approve": f"{URL}/approve?code=7F3K92QD"}),
                             ("text of the estate", {**good, "approve": f"{URL}/approve?code=7F3K92QD&token={'x' * 24}#{HOSTILE}"})):
            with self.subTest(label):
                with self.assertRaises(CardError):
                    cards.decision_card(brief, ctx_for(brief, links=links))

    def test_an_address_is_the_page_the_answer_the_code_and_the_token_and_nothing_else(self):
        self.assertEqual(cardlinks.answer_url(URL, "approve", "7F3K92QD", "a" * 24), f"{URL}/approve?code=7F3K92QD&token={'a' * 24}")
        for page, verb, code, token in ((URL + "?x=1", "approve", "7F3K92QD", "a" * 24), ("http://meternaut.example/ok/p1", "approve", "7F3K92QD", "a" * 24), (URL, "later", "7F3K92QD", "a" * 24),
                                        (URL, "approve", "7F3K92QD&x=1", "a" * 24), (URL, "approve", "7F3K92QD", "short"), (URL, "approve", "7F3K92QD", "a" * 24 + "&x=1"),
                                        (URL, "approve", "", "a" * 24), (None, "approve", "7F3K92QD", "a" * 24), (URL, "approve", "7F3K92QD", None)):
            with self.subTest(page=page, verb=verb, code=code, token=token):
                with self.assertRaises(ValueError):
                    cardlinks.answer_url(page, verb, code, token)

    def test_the_card_needs_no_link_for_an_answer_that_it_does_not_carry(self):
        brief = brief_of(plan=reversible_plan(), case=make_case(resource_type="microsoft.compute/virtualmachines", resource_name="vm-zq7"))
        card = cards.decision_card(brief, ctx_for(brief, links={**links_for(brief), "confirm": links_for(brief, "confirm")["confirm"]}))
        self.assertEqual(titles(card), ["Approve", "Decline", "Open the request"], "a link in the context that no button uses is not on the card")


class WhatTheCheckOfACardRefuses(unittest.TestCase):
    def good(self) -> dict:
        brief = brief_of()
        return cards.decision_card(brief, buttons_for(brief))

    def problems(self, change) -> list[str]:
        card = self.good()
        change(card)
        return cardcheck.check(card)

    def test_a_good_card_with_buttons_has_no_problem(self):
        self.assertEqual(cardcheck.check(self.good()), [])

    def test_what_a_button_that_shows_a_part_of_the_card_may_do(self):
        def item(card, id_):
            return by_id(card)[id_]
        cases = {
            "a toggle with no tooltip": (lambda c: item(c, "approve").pop("tooltip"), "has a tooltip"),
            "a toggle with an empty tooltip": (lambda c: item(c, "approve").update({"tooltip": " "}), "has a tooltip"),
            "a toggle that names nothing": (lambda c: item(c, "approve").update({"targetElements": []}), "at least one target"),
            "a toggle with no targets": (lambda c: item(c, "approve").pop("targetElements"), "needs targetElements"),
            "a target that is a bare id": (lambda c: item(c, "approve").update({"targetElements": ["sure"]}), "a target is the id of an element"),
            "a target that does not say show or hide": (lambda c: item(c, "approve").update({"targetElements": [{"elementId": "sure"}]}), "a target is the id of an element"),
            "a target with another key": (lambda c: item(c, "approve").update({"targetElements": [{"elementId": "sure", "isVisible": True, "x": 1}]}), "a target is the id of an element"),
            "a target that is not on the card": (lambda c: item(c, "approve").update({"targetElements": [{"elementId": "nothing", "isVisible": True}]}), "not an element of the card"),
            "a target that is an action": (lambda c: item(c, "approve").update({"targetElements": [{"elementId": "decline", "isVisible": True}]}), "not an element of the card"),
            "a part that nobody can show": (lambda c: item(c, "approve").update({"targetElements": [{"elementId": "sure", "isVisible": False}]}), "no button of the card shows 'sure'"),
            "a hidden part without an id": (lambda c: c["body"].insert(1, {"type": "TextBlock", "text": "hidden", "wrap": True, "isVisible": False}), "has no id, so no button can show it"),
            "a part that is hidden and that nothing opens": (lambda c: c["body"].insert(1, {"type": "TextBlock", "id": "secret", "text": "hidden", "wrap": True, "isVisible": False}),
                                                             "no button of the card shows 'secret'"),
            "a toggle with a style that does not exist": (lambda c: item(c, "approve").update({"style": "scary"}), "must be one of"),
            "a toggle with a property of a link": (lambda c: item(c, "approve").update({"url": URL}), "is not a property of Action.ToggleVisibility"),
        }
        for name, (change, needle) in cases.items():
            with self.subTest(name):
                found = self.problems(change)
                self.assertTrue(any(needle in line for line in found), (needle, found))

    def test_what_a_link_may_be(self):
        def item(card, id_):
            return by_id(card)[id_]
        cases = {
            "a link with a query that is not an answer": (lambda c: item(c, "page").update({"url": URL + "?x=1"}), "must be an https address"),
            "an answer link with another answer in its path": (lambda c: item(c, "decline").update({"url": APPROVE_URL.replace("approve", "later")}), "must be an https address"),
            "an answer link with a long token": (lambda c: item(c, "decline").update({"url": DECLINE_URL + "x" * 80}), "must be an https address"),
            "an answer link with a word of text in it": (lambda c: item(c, "decline").update({"url": DECLINE_URL + "&note=free text"}), "must be an https address"),
            "an answer link for another request": (lambda c: item(c, "decline").update({"url": cardlinks.answer_url(f"{BASE}/ok/other", "decline", "7F3K92QD", "z" * 24)}), "different pages"),
            "two buttons that decline": (lambda c: item(c, "decisions")["actions"].append({"type": "Action.OpenUrl", "title": "Not this", "url": DECLINE_URL.replace(TOKEN, "n" * 24)}),
                                         "has two buttons that decline"),
            "a link in a toggle": (lambda c: item(c, "sure-back").update({"url": URL}), "is not a property of Action.ToggleVisibility"),
            "a link that is not https": (lambda c: item(c, "decline").update({"url": DECLINE_URL.replace("https", "http")}), "must be an https address"),
        }
        for name, (change, needle) in cases.items():
            with self.subTest(name):
                found = self.problems(change)
                self.assertTrue(any(needle in line for line in found), (needle, found))

    def test_a_card_has_at_most_the_buttons_that_the_question_needs(self):
        self.assertEqual(sum(1 for node in walk(self.good()) if str(node.get("type", "")).startswith("Action.")), 5)
        self.assertEqual(cardcheck.MAX_ACTIONS, 6)

    def test_the_start_page_of_the_web_page_is_still_a_link_of_the_first_card(self):
        self.assertEqual(cardcheck.check(cards.first_contact_card("Maya", BASE, CONTACTS)), [])


class WhatComesFromTheEstateIsDataOnACardWithButtons(unittest.TestCase):
    def test_no_text_of_the_estate_is_in_an_address_or_makes_one(self):
        plan = make_plan(resource_name=HOSTILE, resource_group=HOSTILE)
        case = make_case(resource_name=HOSTILE, resource_group=HOSTILE, summary=HOSTILE, objections=(HOSTILE,), models={"detective": HOSTILE, "skeptic": "model-s"},
                         owner={"lookedUp": True, "tagOwner": HOSTILE, "createdBy": HOSTILE, "changedBy": HOSTILE, "changedAt": "2026-03-01"}, facts={"ageDays": 41, "basis": HOSTILE})
        brief = brief_of(plan=plan, case=case)
        card = cards.decision_card(brief, buttons_for(brief, why=HOSTILE, contacts=(f"{HOSTILE} ({HOSTILE})",)))
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(sorted(urls(card)), sorted([URL, APPROVE_URL, DECLINE_URL]))
        for text in texts(card):
            self.assertNotIn("](", text)
            self.assertNotIn("{{", text)
        body = {k: v for k, v in card.items() if k != "$schema"}
        self.assertEqual(sorted(set(re.findall(r"https?://[^\s\"\\]+", json.dumps(body)))), sorted([URL, APPROVE_URL, DECLINE_URL]))


class TheContextOfACard(unittest.TestCase):
    def test_it_takes_the_links_and_nothing_else_that_a_token_could_hide_in(self):
        with self.assertRaises(TypeError, msg="a card takes no token of its own: the links carry them"):
            CardContext(page_url=URL, nonce="N0nce-0123456789abcdefghijklmnop")
        self.assertEqual(CardContext(page_url=URL).links, {})
        self.assertEqual(replace(CardContext(page_url=URL), links={"approve": APPROVE_URL}).links, {"approve": APPROVE_URL})


if __name__ == "__main__":
    unittest.main()
