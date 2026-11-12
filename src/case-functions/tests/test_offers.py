"""The cards that Meternaut sends on its own (cases/offers.py): who gets one, when, what is written about each try, and the message that goes on the queue.

The Queue service is a fake and the stores are in memory. A card is for a person who chose Teams, goes through the same checks in the same order as a letter (mail.py), and is written about in the
same store of mail records, so that the letter and the card count the same things and never go twice for one request.
"""
import dataclasses
import json
import logging
import re
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import cardcheck, cardlinks, cards, offers, teamsqueue
from cases.identity import IdentityError
from cases.models import ActionRecord, MailRecord, SwitchRecord
from test_cards import make_case


def advice(world: cs.World, plan_id: str = cs.PLAN_ID, case_id: str = "c1", **changes):
    return world.open_plan(cs.advice_plan(plan_id, case_id=case_id, expires_at="2026-12-01T00:00:00Z", **changes))


def link_of(card: dict) -> dict:
    """The one action of a card: its link."""
    found = [node for node in walk(card) if str(node.get("type", "")).startswith("Action.")]
    assert len(found) == 1, found
    return found[0]


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


class TheCardOfARequest(unittest.TestCase):
    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        advice(self.world)
        self.world.channel(cs.MAYA)
        self.world.introduce(cs.MAYA)

    def test_a_person_who_chose_teams_gets_the_card_as_one_message_on_the_queue_of_the_cards(self):
        self.assertEqual(self.world.run(), 1)
        (call,) = self.fake.calls
        self.assertEqual((call["method"], call["url"]), ("POST", cs.QUEUE_URL))
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {cs.STORAGE_TOKEN}")
        self.assertEqual((call["headers"]["x-ms-version"], call["headers"]["Content-Type"]), (teamsqueue.VERSION, "application/xml"))
        (message,) = self.fake.messages()
        (card,) = self.fake.cards()
        self.assertEqual(cardcheck.check(card), [])
        (record,) = self.world.tries()
        self.assertEqual((record.kind, record.status, record.plan_id), ("advice-card", "sent", cs.PLAN_ID))
        self.assertEqual(record.mail_id, message["id"], "the record and the message have one id, so that a run of the flow and the record can be put side by side")

    def test_the_message_is_the_one_json_text_that_the_flow_reads(self):
        self.world.run()
        (text,) = self.fake.texts()
        message = json.loads(text)
        self.assertTrue(text.startswith('{"v":1,"id":"'), "plain JSON text, not base64")
        self.assertEqual(list(message), ["v", "id", "to", "title", "card", "request"])
        self.assertEqual(message["request"], cs.PLAN_ID, "the flow writes it back with the Teams message, so that the app can replace the card")
        self.assertEqual((message["v"], message["to"], message["title"]), (1, "maya@example.com", "[Meternaut] A decision waits for you"))
        self.assertLessEqual(len(text.encode("utf-8")), teamsqueue.MAX_BYTES)
        self.assertEqual(message["card"]["version"], "1.4")

    def test_the_address_is_the_one_of_the_list_of_people_and_never_a_text_of_the_estate(self):
        hostile = "attacker@evil.example"
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(cs.PLAN_ID), resource_name=hostile, resource_group=hostile))
        self.world.store.case_put(make_case(resource_name=hostile, summary=hostile, owner={"lookedUp": True, "tagOwner": hostile, "createdBy": hostile}, status="proposed",
                                            plan_id=cs.PLAN_ID))
        self.world.run()
        (message,) = self.fake.messages()
        self.assertEqual(message["to"], "maya@example.com")
        self.assertIn(hostile, json.dumps(message["card"]), "the estate's own text is on the card, as data (the card tests hold that it is inert)")
        self.assertEqual(json.dumps(message).count('"to":'), 1)
        self.assertNotIn(hostile, json.dumps({k: v for k, v in message.items() if k != "card"}))

    def test_the_card_holds_buttons_that_open_pages_of_the_app_and_nothing_to_fill_in(self):
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.run()
        self.assertEqual(len(self.fake.cards()), 2)
        for message in self.fake.messages():
            card = message["card"]
            kinds = {node.get("type") for node in walk(card)}
            self.assertFalse({kind for kind in kinds if str(kind).startswith("Input.")} | (kinds & {"Action.Execute", "Action.Submit", "Action.Http", "Action.ShowCard"}), kinds)
            page = re.search(r"Open it on the page: (\S+)", card["fallbackText"]).group(1)
            self.assertIn(page, {f"{cs.BASE}/ok/{cs.PLAN_ID}", f"{cs.BASE}/ok/p3change"})
            for node in walk(card):
                if node.get("type") == "Action.OpenUrl":
                    self.assertTrue(node["url"] == page or node["url"].startswith(f"{page}/"), node["url"])
            self.assertNotIn("nonce", json.dumps(message))

    def test_the_notification_names_no_resource_and_no_amount(self):
        self.world.run()
        self.assertEqual(self.fake.messages()[0]["title"], "[Meternaut] A decision waits for you")
        (record,) = self.world.tries()
        self.assertEqual(record.subject, "[Meternaut] A decision waits for you")
        self.assertNotIn("disk", record.detail.lower())

    def test_the_record_says_that_a_sent_card_is_not_a_delivered_card(self):
        self.world.run()
        (record,) = self.world.tries()
        self.assertIn("not delivery", record.detail)
        self.assertIn("the message on teams-posted says when it did", record.detail)

    def test_a_card_that_was_sent_is_not_sent_again(self):
        self.world.run()
        self.world.clock.advance(hours=2)
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(len(self.fake.calls), 1)

    def test_only_the_people_who_chose_teams_get_a_card(self):
        self.world.introduce(cs.ANNA)
        for channel in ("email", "desk"):
            self.world.channel(cs.ANNA, channel)
            self.world.channel(cs.MAYA, channel)
            self.assertEqual(self.world.run(), 0, channel)
        self.assertEqual((self.fake.calls, self.world.tries(cs.MAYA), self.world.tries(cs.ANNA)), ([], [], []))
        self.world.channel(cs.ANNA)
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([message["to"] for message in self.fake.messages()], ["anna@example.com"])

    def test_nobody_who_may_not_answer_gets_a_card(self):
        self.world.open_plan(cs.advice_plan("p2ops", case_id="c2", approvers=(cs.OMAR,), expires_at="2026-12-01T00:00:00Z"))
        self.world.channel(cs.OMAR)
        self.world.introduce(cs.OMAR)
        self.world.run()
        self.assertEqual(self.world.tries(cs.OMAR), [])

    def test_a_person_with_no_address_on_the_list_gets_no_card_and_no_try(self):
        self.world.offers.people = cs.People((cs.Person(cs.MAYA, "Maya", ("owner", "approver", "ops"), ""),))
        self.assertEqual(self.world.run(), 0)
        self.assertEqual((self.fake.calls, self.world.tries()), ([], []))

    def test_a_request_that_is_over_or_that_a_person_answered_is_not_offered(self):
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(cs.PLAN_ID), state="declined"))
        self.assertEqual(self.world.run(), 0)
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(cs.PLAN_ID), state="open", expires_at="2026-11-05T10:00:00Z"))
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(self.fake.calls, [])

    def test_a_letter_that_went_already_stops_the_card_of_an_approval(self):
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.store.mail_put(MailRecord("m1", cs.MAYA, "approval", "[Meternaut] x", "2026-11-05T10:00:00Z", "sent", "p3change", ""))
        self.world.run()
        self.assertEqual([m.kind for m in self.world.tries()], ["approval", "advice-card"], "the advice card of the other request went; the approval card did not")

    def test_the_card_of_a_change_has_the_buttons_of_the_decision_and_the_page_of_the_request(self):
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.run()
        card = next(c for c in self.fake.cards() if "p3change" in str(c))
        self.assertEqual([a["title"] for a in by_id(card)["decisions"]["actions"]], ["Approve", "Decline", "Open the request"])
        self.assertEqual(by_id(card)["decisions"]["actions"][2]["url"], f"{cs.BASE}/ok/p3change")
        self.assertEqual(by_id(card)["sure-yes"]["title"], "Yes, delete it", "a delete cannot be undone, so the card asks twice")
        self.assertEqual(sorted(m.kind for m in self.world.tries()), ["advice-card", "approval-card"])

    def test_the_card_of_advice_has_worth_acting_on_and_not_worth_it(self):
        self.world.run()
        (card,) = self.fake.cards()
        self.assertEqual([a["title"] for a in by_id(card)["decisions"]["actions"]], ["Worth acting on", "Not worth it", "Open the request"])

    def test_a_pause_of_the_changes_is_said_on_the_card_of_a_change(self):
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(cs.PLAN_ID), state="declined"))
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.store.switch_put(SwitchRecord(name="changes", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.world.run()
        (card,) = self.fake.cards()
        self.assertNotIn("Review and decide", "\n".join(cs.texts(card)))
        self.assertIn("Changes are paused here.", "\n".join(cs.texts(card)))
        self.assertEqual(link_of(card)["title"], "See the request")
        self.assertEqual(self.world.store.nonces, {}, "a card that has no answer has no link token")


def by_id(card: dict) -> dict:
    return {node["id"]: node for node in walk(card) if isinstance(node.get("id"), str)}


class TheLinkTokensOfACard(unittest.TestCase):
    """Each button that answers carries a one-time token that the app made for this person and this request when it built the card (cases/cardlinks.py): nothing else is made to send a card."""

    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        for oid in (cs.MAYA, cs.ANNA):
            self.world.channel(oid)
            self.world.introduce(oid)

    def answers(self, card: dict) -> dict[str, dict]:
        """The buttons of a card that carry a token, by answer: the address, split."""
        found = {}
        for node in walk(card):
            if node.get("type") == "Action.OpenUrl" and "token=" in node["url"]:
                match = cardlinks.ANSWER_ADDRESS.fullmatch(node["url"])
                assert match is not None, node["url"]
                found[match["verb"]] = {"url": node["url"], "code": match["code"], "token": match["token"]}
        return found

    def cards_by_person(self) -> dict[str, dict]:
        return {message["to"]: message["card"] for message in self.fake.messages()}

    def test_a_token_is_made_for_each_answer_and_each_person_and_keeps_what_the_link_does(self):
        self.world.run()
        by_person = self.cards_by_person()
        self.assertEqual(sorted(by_person), ["anna@example.com", "maya@example.com"])
        tokens = []
        for address, oid in (("maya@example.com", cs.MAYA), ("anna@example.com", cs.ANNA)):
            found = self.answers(by_person[address])
            self.assertEqual(sorted(found), ["approve", "decline"])
            for verb, link in found.items():
                self.assertEqual(link["code"], cs.CODE, "the code of the plan at the time of the card")
                kept = json.loads(self.world.store.nonce_peek(link["token"], oid, "p3change"))
                self.assertEqual(kept, [verb, cs.CODE, 1 if verb == "approve" else 0], "a delete asks twice on the card: its approve says so")
                tokens.append(link["token"])
        self.assertEqual(len(set(tokens)), 4, "no token is shared between two buttons or two people")

    def test_a_token_is_good_for_the_person_and_the_request_that_it_was_made_for_and_for_nobody_else(self):
        self.world.run()
        link = self.answers(self.cards_by_person()["maya@example.com"])["approve"]
        peek = self.world.store.nonce_peek
        self.assertIsNotNone(peek(link["token"], cs.MAYA, "p3change"))
        self.assertIsNone(peek(link["token"], cs.ANNA, "p3change"), "another approver of the same request")
        self.assertIsNone(peek(link["token"], cs.MAYA, cs.PLAN_ID), "another request")
        self.assertIsNone(peek(link["token"], cs.MAYA.upper() + "x", "p3change"))

    def test_a_token_lives_as_long_as_the_request_is_open_and_is_used_up_once(self):
        self.world.run()
        link = self.answers(self.cards_by_person()["maya@example.com"])["decline"]
        self.world.clock.advance(days=24)
        self.assertIsNotNone(self.world.store.nonce_peek(link["token"], cs.MAYA, "p3change"), "the request is open until 2026-12-01")
        self.world.clock.advance(days=2)
        self.assertIsNone(self.world.store.nonce_peek(link["token"], cs.MAYA, "p3change"), "the request has expired")
        self.world.clock.advance(days=-2)
        self.assertTrue(self.world.store.nonce_use(link["token"], cs.MAYA, "p3change"))
        self.assertIsNone(self.world.store.nonce_peek(link["token"], cs.MAYA, "p3change"))

    def test_a_request_that_is_about_to_expire_still_gets_a_quarter_of_an_hour(self):
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get("p3change"), expires_at="2026-11-05T10:20:00Z"))
        self.world.run()
        link = self.answers(self.cards_by_person()["maya@example.com"])["decline"]
        self.world.clock.advance(minutes=14)
        self.assertIsNotNone(self.world.store.nonce_peek(link["token"], cs.MAYA, "p3change"))

    def test_a_card_that_cannot_get_its_tokens_goes_with_the_link_to_the_page_of_the_request(self):
        def down(*args, **kwargs):
            raise RuntimeError("the records are down")
        self.world.store.nonce_new = down
        with self.assertLogs("meternaut.teams.offers", level="ERROR") as logged:
            self.world.run()
        self.assertTrue(any("buttons of a card could not be made" in line for line in logged.output), logged.output)
        self.assertEqual([m.status for m in self.world.tries(cs.MAYA, "approval-card")], ["sent"])
        card = self.cards_by_person()["maya@example.com"]
        self.assertEqual([a["title"] for a in by_id(card)["decisions"]["actions"]], ["Review and decide"])
        self.assertNotIn("token=", json.dumps(card))

    def test_the_short_card_of_a_card_that_did_not_fit_carries_no_token(self):
        from unittest import mock
        with mock.patch.object(cardcheck, "MAX_BYTES", 2500):
            self.world.run()
        card = self.cards_by_person()["maya@example.com"]
        self.assertEqual([a["title"] for a in by_id(card)["decisions"]["actions"]], ["Review and decide"])
        self.assertNotIn("token=", json.dumps(card))
        self.assertIn(offers.SHORT_SENT, self.world.tries(cs.MAYA, "approval-card")[0].detail)

    def test_the_message_has_no_token_outside_the_addresses_of_the_buttons(self):
        self.world.run()
        for message in self.fake.messages():
            if message["to"] != "maya@example.com" or "decisions" not in json.dumps(message["card"]):
                continue
            text = json.dumps({k: v for k, v in message.items() if k != "card"}) + message["card"]["fallbackText"]
            self.assertNotIn("token", text)
            self.assertNotIn("code=", text)

    def test_the_two_people_of_a_change_that_needs_two_have_a_confirm_and_an_approve_token_each_as_their_turn_comes(self):
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get("p3change"), approval_class="R3", digest="d" * 64))
        self.world.run()
        for address, oid in (("maya@example.com", cs.MAYA), ("anna@example.com", cs.ANNA)):
            found = self.answers(self.cards_by_person()[address])
            self.assertEqual(sorted(found), ["confirm", "decline"], "nobody has confirmed yet: each is the first")
            self.assertEqual(json.loads(self.world.store.nonce_peek(found["confirm"]["token"], oid, "p3change"))[0], "confirm")


class TheChecksBeforeACard(unittest.TestCase):
    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        advice(self.world)
        self.world.channel(cs.MAYA)
        self.world.introduce(cs.MAYA)

    def held(self, words):
        (record,) = self.world.tries()
        self.assertEqual(record.status, "held")
        self.assertIn(words, record.detail)
        self.assertEqual(self.fake.calls, [])

    def test_a_switch_that_is_pulled_holds_the_card(self):
        for name in ("messages", "all"):
            self.world.store.mails[:] = [m for m in self.world.store.mails if m.mail_id.startswith("told-")]
            self.world.store.switch_put(SwitchRecord(name=name, paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
            self.world.run()
            self.held(f'The switch "{name}"')
            self.world.store.switch_put(SwitchRecord(name=name))

    def test_a_switch_that_cannot_be_read_counts_as_pulled(self):
        def broken(name):
            raise RuntimeError("down")
        self.world.store.switch_get = broken
        self.world.run()
        self.held("pulled, or cannot be read")

    def test_a_person_who_paused_messages_gets_none_until_it_is_over(self):
        self.world.channel(cs.MAYA, paused_until="2026-11-06T00:00:00Z")
        self.world.run()
        self.held("paused messages until 2026-11-06T00:00:00Z")
        self.world.clock.advance(days=1)
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([m.status for m in self.world.tries()], ["held", "sent"])

    def test_a_card_that_was_held_is_offered_again_after_fifteen_minutes_and_not_sooner(self):
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.world.run()
        self.world.store.switch_put(SwitchRecord(name="messages"))
        self.world.clock.advance(minutes=14)
        self.assertEqual(self.world.run(), 0)
        self.world.clock.advance(minutes=1)
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([m.status for m in self.world.tries()], ["held", "sent"])

    def test_the_tries_are_used_up_after_twelve(self):
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        for _ in range(offers.MAX_TRIES + 3):
            self.world.run()
            self.world.clock.advance(minutes=offers.RETRY_MINUTES)
        self.assertEqual(len(self.world.tries()), offers.MAX_TRIES)

    def test_the_weekly_budget_holds_the_cards_of_advice_and_nothing_else(self):
        self.world.channel(cs.MAYA, weekly_budget=1)
        advice(self.world, "p2second", "c2")
        self.world.run()
        self.assertEqual(sorted(m.status for m in self.world.tries(kind="advice-card")), ["held", "sent"])
        self.assertIn("The weekly budget of 1 messages is reached", next(m.detail for m in self.world.tries() if m.status == "held"))
        self.world.channel(cs.MAYA, weekly_budget=0)
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.run()
        self.assertEqual([m.status for m in self.world.tries(kind="approval-card")], ["sent"], "an approval is asked for: the budget does not hold it, as it does not hold its letter")

    def test_a_new_week_has_a_new_budget(self):
        self.world.channel(cs.MAYA, weekly_budget=1)
        advice(self.world, "p2second", "c2")
        self.world.run()
        self.world.clock.advance(days=4)  # Monday 2026-11-09
        self.world.run()
        self.assertEqual(sorted(m.status for m in self.world.tries(kind="advice-card")), ["held", "sent", "sent"])

    def test_the_weekly_summary_is_not_a_card(self):
        self.world.channel(cs.MAYA, "desk")
        self.assertEqual(self.world.run(), 0)


class TheQueue(unittest.TestCase):
    """What the card goes through to get to the flow, and what a try that goes wrong is: a failed try, written in plain words, after which the letter goes as it always does."""

    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        advice(self.world)
        self.world.channel(cs.MAYA)
        self.world.introduce(cs.MAYA)

    def only_try(self):
        (record,) = self.world.tries()
        return record

    def test_a_queue_that_refuses_the_app_is_a_failed_try_that_says_why(self):
        self.fake.replies = [(403, b"<Error><Code>AuthorizationPermissionMismatch</Code><Message>This request is not authorized.</Message></Error>")]
        self.assertEqual(self.world.run(), 1)
        record = self.only_try()
        self.assertEqual(record.status, "failed")
        self.assertIn("Storage Queue Data Contributor", record.detail)
        self.assertNotIn(cs.STORAGE_TOKEN, record.detail)

    def test_a_queue_that_is_not_there_is_a_failed_try_that_says_so(self):
        self.fake.replies = [404]
        self.world.run()
        self.assertEqual((self.only_try().status, "The queue is not there" in self.only_try().detail), ("failed", True))

    def test_a_network_failure_is_a_failed_try_that_may_have_been_carried_out_and_is_not_repeated_at_once(self):
        self.fake.replies = [OSError("the network is down")]
        self.world.run()
        self.assertEqual(len(self.fake.calls), 1)
        record = self.only_try()
        self.assertEqual(record.status, "failed")
        self.assertIn("may have been taken", record.detail)

    def test_a_server_error_is_not_tried_again_inside_the_try_but_a_busy_queue_is(self):
        self.fake.replies = [500]
        self.world.run()
        self.assertEqual((len(self.fake.calls), self.only_try().status), (1, "failed"))
        self.world.store.mails[:] = [m for m in self.world.store.mails if m.mail_id.startswith("told-")]
        self.fake.calls.clear()
        self.fake.replies = [503, 429, 201]
        self.world.run()
        self.assertEqual(len(self.fake.calls), 3, "503 and 429 are what the service says before it takes a message")
        self.assertEqual(self.only_try().status, "sent")
        self.assertEqual(len(self.fake.texts()), 3, "each call carried the same message")

    def test_a_failed_try_is_offered_again_after_fifteen_minutes_and_the_card_goes_once(self):
        self.fake.replies = [500]
        self.world.run()
        self.world.clock.advance(minutes=15)
        self.world.run()
        self.world.clock.advance(hours=1)
        self.assertEqual(self.world.run(), 0)
        self.assertEqual([m.status for m in self.world.tries()], ["failed", "sent"])

    def test_the_identity_that_gives_no_token_is_a_failed_try_and_nothing_is_sent(self):
        def none(resource):
            raise IdentityError("the platform's managed identity endpoint is not available")
        self.world.queue.token = none
        self.world.run()
        self.assertEqual(self.fake.calls, [])
        self.assertEqual((self.only_try().status, "No token for the queue" in self.only_try().detail), ("failed", True))

    def test_a_failure_is_not_the_end_of_the_round(self):
        self.world.channel(cs.ANNA)
        self.world.introduce(cs.ANNA)
        real = self.world.store.settings_get

        def flaky(oid):
            if oid == cs.MAYA:
                raise RuntimeError("the table is down")
            return real(oid)
        self.world.store.settings_get = flaky
        with self.assertLogs("meternaut.teams.offers", level=logging.ERROR):
            self.world.run()
        self.assertEqual(self.world.tries(cs.MAYA), [])
        self.assertEqual([m.status for m in self.world.tries(cs.ANNA)], ["sent"])

    def test_a_card_that_cannot_be_made_is_a_failed_try_and_nothing_is_sent(self):
        self.world.offers.base_url = "http://not-secure.example"
        self.world.run()
        self.assertEqual(self.fake.calls, [])
        record = self.only_try()
        self.assertEqual(record.status, "failed")
        self.assertIn("The card could not be made", record.detail)

    def test_a_message_that_is_too_big_is_replaced_by_the_short_card_and_the_record_says_so(self):
        probe = cs.World()
        advice(probe)
        probe.channel(cs.MAYA)
        probe.introduce(cs.MAYA)
        probe.run()
        full = len(probe.queue_fake.texts()[0].encode("utf-8"))
        with mock.patch.object(teamsqueue, "MAX_BYTES", full - 1):
            self.world.run()
        (message,) = self.fake.messages()
        self.assertLess(len(self.fake.texts()[0].encode("utf-8")), full - 1)
        self.assertEqual([node["id"] for node in message["card"]["body"] if "id" in node], ["header", "headline", "short", "decisions", "ai-footer"])
        self.assertEqual(link_of(message["card"])["url"], f"{cs.BASE}/ok/{cs.PLAN_ID}")
        record = self.only_try()
        self.assertEqual(record.status, "sent")
        self.assertIn(offers.SHORT_SENT, record.detail)
        json.loads(self.fake.texts()[0])

    def test_a_card_that_is_too_large_for_a_card_is_replaced_in_the_same_way(self):
        with mock.patch.object(cardcheck, "MAX_BYTES", 2500):
            self.world.run()
        (card,) = self.fake.cards()
        self.assertIn("short", [node.get("id") for node in card["body"]])
        self.assertIn(offers.SHORT_SENT, self.only_try().detail)

    def test_when_even_the_short_card_does_not_fit_the_try_fails_and_nothing_is_cut(self):
        with mock.patch.object(teamsqueue, "MAX_BYTES", 300):
            self.world.run()
        self.assertEqual(self.fake.calls, [])
        record = self.only_try()
        self.assertEqual(record.status, "failed")
        self.assertIn("The card could not be made", record.detail)


class TheIntroduction(unittest.TestCase):
    """A person who chose Teams is told who writes before the first card of a request, as a person who gets letters is by the first-contact letter."""

    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        advice(self.world)
        self.world.channel(cs.MAYA)

    def test_the_first_card_says_who_writes_and_the_card_of_the_request_follows_in_the_same_round(self):
        self.assertEqual(self.world.run(), 2)
        first, second = self.fake.messages()
        self.assertEqual(first["title"], "[Meternaut] An AI assistant for Azure costs will write to you")
        self.assertEqual(second["title"], "[Meternaut] A decision waits for you")
        self.assertEqual(link_of(first["card"])["url"], f"{cs.BASE}/")
        self.assertIn("You got this because you chose Teams", json.dumps(first["card"]))
        for message in (first, second):
            self.assertEqual((message["to"], cardcheck.check(message["card"])), ("maya@example.com", []))
        self.assertEqual([(m.kind, m.status, m.plan_id) for m in self.world.tries()], [("first-contact-card", "sent", None), ("advice-card", "sent", cs.PLAN_ID)])

    def test_it_goes_once(self):
        self.world.run()
        self.world.clock.advance(hours=2)
        advice(self.world, "p2second", "c2")
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([m.kind for m in self.world.tries()], ["first-contact-card", "advice-card", "advice-card"])

    def test_a_person_who_got_the_letter_of_the_same_name_is_not_introduced_again(self):
        self.world.store.mail_put(MailRecord("m0", cs.MAYA, "first_contact", "[Meternaut] x", "2026-11-01T10:00:00Z", "sent", None, ""))
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([m.kind for m in self.world.tries() if m.kind.endswith("-card")], ["advice-card"])

    def test_an_introduction_that_failed_holds_the_card_of_the_request_back_until_it_goes(self):
        self.fake.replies = [500]
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([(m.kind, m.status) for m in self.world.tries()], [("first-contact-card", "failed")])
        self.world.clock.advance(minutes=14)
        self.assertEqual(self.world.run(), 0)
        self.world.clock.advance(minutes=1)
        self.assertEqual(self.world.run(), 2)
        self.assertEqual([(m.kind, m.status) for m in self.world.tries()], [("first-contact-card", "failed"), ("first-contact-card", "sent"), ("advice-card", "sent")])

    def test_when_its_tries_are_used_up_the_card_of_the_request_goes_without_it(self):
        for _ in range(offers.MAX_TRIES):
            self.fake.replies.append(500)
            self.world.run()
            self.world.clock.advance(minutes=offers.RETRY_MINUTES)
        self.assertEqual(len(self.world.tries(kind="first-contact-card")), offers.MAX_TRIES)
        self.assertEqual(self.world.tries(kind="advice-card"), [])
        self.assertEqual(self.world.run(), 1)
        self.assertEqual([m.status for m in self.world.tries(kind="advice-card")], ["sent"])

    def test_nobody_is_introduced_while_the_card_is_held(self):
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.world.run()
        self.assertEqual([(m.kind, m.status) for m in self.world.tries()], [("advice-card", "held")])
        self.assertEqual(self.fake.calls, [])

    def test_the_card_of_a_change_that_ran_is_preceded_by_it_too(self):
        world = cs.World()
        world.open_plan(cs.change_plan(expires_at="2026-12-01T00:00:00Z", state="consumed"))
        world.channel(cs.MAYA)
        world.store.action_put(ActionRecord(plan_id=cs.PLAN_ID, case_id="c1", family="delete-disk", resource_id="r1", state="done", queued_at="2026-11-05T10:00:00Z",
                                            finished_at="2026-11-05T10:10:00Z", result="Deleted.", correlation_id="x"))
        self.assertEqual(world.run(), 2)
        self.assertEqual([m.kind for m in world.tries()], ["first-contact-card", "notice-card"])


class TheCardsAboutAChange(unittest.TestCase):
    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        self.plan = self.world.open_plan(cs.change_plan(expires_at="2026-12-01T00:00:00Z", state="consumed"))
        self.world.channel(cs.MAYA)
        self.world.introduce(cs.MAYA)

    def action(self, state="done", **changes):
        values = dict(plan_id=cs.PLAN_ID, case_id="c1", family="delete-disk", resource_id=self.plan.resource_id, state=state, queued_at="2026-11-05T10:00:00Z",
                      finished_at="2026-11-05T10:10:00Z", result="Deleted.", correlation_id="x")
        values.update(changes)
        self.world.store.action_put(ActionRecord(**values))

    def test_a_change_that_ran_gets_a_card_of_what_became_of_it_with_one_link_and_no_answer(self):
        self.action()
        self.assertEqual(self.world.run(), 1)
        (message,) = self.fake.messages()
        card = message["card"]
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(link_of(card)["title"], "See the request")
        self.assertNotIn("nonce", json.dumps(message))
        self.assertEqual(message["title"], "[Meternaut] A change to Azure has run")
        self.assertEqual([(m.kind, m.status) for m in self.world.tries()], [("notice-card", "sent")])

    def test_the_check_afterwards_is_a_second_card_and_neither_goes_twice(self):
        self.action("verified", verification={"gone": True})
        self.world.run()
        self.world.run()
        self.assertEqual(sorted(m.kind for m in self.world.tries()), ["notice-card", "verified-card"])
        self.assertEqual(len(self.fake.calls), 2)

    def test_a_change_of_long_ago_and_a_letter_that_went_are_left_alone(self):
        self.action(finished_at="2026-11-01T10:10:00Z")
        self.assertEqual(self.world.run(), 0)
        self.action()
        self.world.store.mail_put(MailRecord("m1", cs.MAYA, "notice", "[Meternaut] x", "2026-11-05T10:12:00Z", "sent", cs.PLAN_ID, ""))
        self.assertEqual(self.world.run(), 0)

    def test_a_person_who_did_not_choose_teams_gets_no_card_about_a_change(self):
        self.action()
        self.world.channel(cs.MAYA, "email")
        self.assertEqual(self.world.run(), 0)


class TheTexts(unittest.TestCase):
    def test_the_card_texts_carry_no_name_of_the_estate(self):
        self.assertEqual(set(offers.SUMMARY_OF.values()) - set(cards.SUMMARIES), set())
        for text in cards.SUMMARIES.values():
            self.assertNotRegex(text, r"\d")


if __name__ == "__main__":
    unittest.main()
