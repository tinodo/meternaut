"""The cards that close themselves (cases/teamsqueue.py, cases/offers.py, cases/cards.closed_card, cases/loop.card_posted).

The flow tells the app which Teams message a card became (a message on the queue teams-posted), and when the request is decided, declined or over the app puts the card that replaces it
on the queue of the cards. The Queue service is a fake and the stores are in memory (cardsupport.py); every name is invented.
"""
import dataclasses
import json
import types
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import cardcheck, cards, loop, offers, teamsqueue
from cases.models import DecisionRecord, SwitchRecord
from test_cards import actions_of, brief_of, by_id, ctx_for, make_advice_plan, make_case, make_plan, texts

MESSAGE, CONVERSATION = "1731331200000", "19:abc-def@unq.gbl.spaces"
GOOD = {"v": 1, "request": cs.PLAN_ID, "to": "maya@example.com", "message": MESSAGE, "conversation": CONVERSATION}
CLOSED_LINE = "Decided: Declined by Anna, 5 Nov 10:30 UTC. Nothing more to do."


def written(**changes) -> str:
    """What the flow writes to the queue teams-posted, as the Functions host hands it over (the host has decoded the base64)."""
    return json.dumps({**GOOD, **changes})


class TheMessageThatTheFlowWritesAfterThePost(unittest.TestCase):
    def test_it_is_read_as_it_is_written(self):
        self.assertEqual(teamsqueue.read_posted(written()), (cs.PLAN_ID, "maya@example.com", MESSAGE, CONVERSATION))

    def test_anything_else_is_not_a_message_of_the_flow(self):
        wrong = ["not json", "[]", "null", written(v=2), written(request="a b"), written(request=7), written(to="maya"), written(message=""), written(message="a b"), written(conversation=None),
                 written(conversation="x" * 201), json.dumps({k: v for k, v in GOOD.items() if k != "to"})]
        for text in wrong:
            with self.subTest(text=text[:40]), self.assertRaises(teamsqueue.MessageError):
                teamsqueue.read_posted(text)


class TheMessageOfACard(unittest.TestCase):
    CARD = {"type": "AdaptiveCard", "$schema": cardcheck.SCHEMA, "version": cardcheck.VERSION, "fallbackText": "x", "body": [{"type": "TextBlock", "text": "x", "wrap": True}]}

    def test_a_request_is_named_by_its_plan_and_an_update_by_the_message(self):
        asking = json.loads(teamsqueue.render("d1", "maya@example.com", "A title", self.CARD, request=cs.PLAN_ID))
        self.assertEqual((asking["request"], "op" in asking, "message" in asking), (cs.PLAN_ID, False, False))
        replacing = json.loads(teamsqueue.render("d2", "maya@example.com", "A title", self.CARD, update=MESSAGE))
        self.assertEqual((replacing["op"], replacing["message"], "request" in replacing), ("update", MESSAGE, False))
        self.assertEqual(list(json.loads(teamsqueue.render("d3", "maya@example.com", "A title", self.CARD))), ["v", "id", "to", "title", "card"])

    def test_an_id_that_is_not_an_id_is_refused(self):
        for more in ({"request": "a b"}, {"update": "a b"}, {"update": ""}):
            with self.subTest(more=more), self.assertRaises(teamsqueue.MessageError):
                teamsqueue.render("d1", "maya@example.com", "A title", self.CARD, **more)


class TheCardThatReplacesAnother(unittest.TestCase):
    ANNA = DecisionRecord(plan_id=cs.PLAN_ID, approver_oid=cs.ANNA, approver_name="Anna", decision="decline", at="2026-11-05T10:30:00Z", plan_code=cs.CODE)

    def closing(self, plan=None, **kw):
        brief = brief_of(plan=plan, may_answer=False, **kw)
        card = cards.closed_card(brief, ctx_for(brief))
        self.assertEqual((cardcheck.check(card), actions_of(card)), ([], []), "a card that is closed has no button")
        return by_id(card)

    def test_a_declined_request_says_who_and_when_and_that_nothing_more_is_to_be_done(self):
        plan = make_plan(state="declined")
        ids = self.closing(plan, decisions=[self.ANNA])
        self.assertEqual((ids["closed"]["text"], ids["kind"]["text"]), (CLOSED_LINE, "Closed"))
        brief = brief_of(plan=plan, may_answer=False, decisions=[self.ANNA])
        self.assertEqual(ids["headline"]["text"], by_id(cards.result_card(brief, ctx_for(brief)))["headline"]["text"], "the headline of the request, as on every card")

    def test_an_approval_and_an_answer_to_advice_use_the_words_of_the_page(self):
        approve = dataclasses.replace(self.ANNA, decision="approve")
        self.assertIn("Decided: Approved by Anna, 5 Nov 10:30 UTC.", self.closing(make_plan(state="consumed"), decisions=[approve])["closed"]["text"])
        self.assertIn("Decided: Worth acting on by Anna", self.closing(make_advice_plan(state="consumed"), case=make_case(status="acknowledged"), decisions=[approve])["closed"]["text"])

    def test_an_expired_request_says_expired(self):
        self.assertEqual(self.closing(make_plan(expires_at="2026-11-04T09:30:00Z"))["closed"]["text"], "Expired. Nothing more to do.")

    def test_a_name_cannot_start_a_link_or_a_list(self):
        hostile = dataclasses.replace(self.ANNA, approver_name="[x](https://evil.example) **b**")
        text = self.closing(make_plan(state="declined"), decisions=[hostile])["closed"]["text"]
        self.assertNotIn("](", text)
        self.assertNotIn("**b**", text)
        self.assertIn("\\*\\*b\\*\\*", text)

    def test_a_request_that_is_open_has_no_closing_card(self):
        brief = brief_of(may_answer=False)
        with self.assertRaises(cards.CardError):
            cards.closed_card(brief, ctx_for(brief))


class TheFlowAndTheAppAgreeOnTheMessages(unittest.TestCase):
    """The flow is a file of the repository (powerplatform/solution/src/Workflows): what it parses is what the app writes, and what it writes is what the app reads."""
    FLOW = json.loads((support.REPO_ROOT / "powerplatform" / "solution" / "src" / "Workflows" / "MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json").read_text(encoding="utf-8"))
    ACTIONS = FLOW["properties"]["definition"]["actions"]
    CARD = TheMessageOfACard.CARD

    def test_every_message_that_the_app_puts_on_the_queue_of_the_cards_is_one_that_the_flow_parses(self):
        schema = self.ACTIONS["Parse_message"]["inputs"]["schema"]
        for kind, more in (("a card of a request", {"request": cs.PLAN_ID}), ("a card that replaces one", {"update": MESSAGE}), ("any other card", {})):
            message = json.loads(teamsqueue.render("d1", "maya@example.com", "A title", self.CARD, **more))
            with self.subTest(kind):
                self.assertLessEqual(set(message), set(schema["properties"]), "a field that the flow does not know")
                self.assertLessEqual(set(schema["required"]), set(message))
                self.assertIn(message["v"], schema["properties"]["v"]["enum"])
                self.assertIn(message.get("op", "update"), schema["properties"]["op"]["enum"])

    def test_the_message_that_the_flow_writes_after_a_post_is_the_one_that_the_app_reads(self):
        compose = self.ACTIONS["Condition_The_message_replaces_a_card"]["else"]["actions"]["Compose_what_was_posted"]["inputs"]
        values = {"@body('Parse_message')?['request']": cs.PLAN_ID, "@body('Parse_message')?['to']": "maya@example.com",
                  "@body('Post_card_in_a_chat_or_channel')?['id']": MESSAGE, "@body('Post_card_in_a_chat_or_channel')?['conversationId']": CONVERSATION}
        written_by_the_flow = {key: values.get(value, value) for key, value in compose.items()}
        self.assertEqual(teamsqueue.read_posted(json.dumps(written_by_the_flow)), (cs.PLAN_ID, "maya@example.com", MESSAGE, CONVERSATION))


class TheFlowSaysThatItPostedACard(unittest.TestCase):
    def setUp(self):
        self.world = cs.World()
        self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))

    def keep(self, text: str) -> str:
        return offers.record_posted(text, self.world.store, self.world.people, self.world.clock)

    def posted(self, oid=cs.MAYA):
        return [m for m in self.world.store.mails if m.oid == oid and m.kind == offers.POSTED]

    def test_the_message_is_kept_for_the_person_and_the_request(self):
        self.assertEqual(self.keep(written()), "kept")
        (record,) = self.posted()
        self.assertEqual((record.plan_id, record.status, record.detail), (cs.PLAN_ID, "posted", f"{MESSAGE} {CONVERSATION}"))
        self.assertEqual(self.keep(written(to="anna@example.com", message="1731331299999")), "kept")
        self.assertEqual(len(self.posted(cs.ANNA)), 1)

    def test_a_message_that_names_nobody_who_may_answer_the_request_keeps_nothing(self):
        for text in ("garbage", written(request="nosuchplan"), written(to="omar@example.com"), written(to="stranger@example.com")):
            with self.subTest(text=text[:50]):
                self.assertTrue(self.keep(text).startswith("refused"))
        self.assertEqual(self.world.store.mails, [])

    def test_a_record_of_a_posted_card_is_no_try_and_no_message_to_count(self):
        self.keep(written())
        self.world.channel(cs.MAYA)
        self.world.introduce(cs.MAYA)
        self.assertEqual(self.world.run(), 1, "the card of the request is still due: a posted record is not a card that was sent")
        self.assertEqual([m.status for m in self.world.tries(cs.MAYA, offers.ADVICE)], ["sent"])

    def test_a_store_that_cannot_be_written_raises_so_that_the_host_tries_again(self):
        def refuse(record):
            raise OSError("table storage is not reachable")
        self.world.store.mail_put = refuse
        with self.assertRaises(OSError):
            self.keep(written())

    def test_the_function_keeps_what_the_queue_hands_it_and_does_nothing_when_the_loop_is_off(self):
        message = types.SimpleNamespace(get_body=lambda: written().encode("utf-8"))
        extras = types.SimpleNamespace(store=self.world.store, people=self.world.people)
        with unittest.mock.patch.object(loop.wiring, "build_extras", return_value=extras), unittest.mock.patch.object(loop, "Identity"):
            self.assertEqual(loop.card_posted(message, env={}, clock=self.world.clock), "kept")
        with unittest.mock.patch.object(loop.wiring, "build_extras", return_value=None), unittest.mock.patch.object(loop, "Identity"):
            self.assertEqual(loop.card_posted(message, env={}, clock=self.world.clock), "the loop is off")
        self.assertEqual(len(self.posted()), 1)


class TheCardClosesWhenTheRequestEnds(unittest.TestCase):
    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        self.plan = self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        for oid in (cs.MAYA, cs.ANNA):
            self.world.channel(oid)
        self.world.introduce(cs.MAYA, cs.ANNA)
        self.world.run()
        for to, message in (("maya@example.com", "1731331200001"), ("anna@example.com", "1731331200002")):
            offers.record_posted(written(to=to, message=message), self.world.store, self.world.people, self.world.clock)
        self.fake.calls.clear()

    def end(self, state: str, decision: str | None = "decline") -> None:
        self.world.store.plan_put(dataclasses.replace(self.plan, state=state))
        if decision:
            self.world.store.decision_put(DecisionRecord(cs.PLAN_ID, cs.ANNA, "Anna", decision, "2026-11-05T10:30:00Z", cs.CODE))

    def updates(self) -> dict[str, dict]:
        return {message["to"]: message for message in self.fake.messages()}

    def test_nothing_is_put_while_the_request_waits(self):
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(self.fake.calls, [])

    def test_each_person_who_got_the_card_gets_a_card_without_a_button_in_its_place_whoever_decided(self):
        self.end("declined")
        self.assertEqual(self.world.run(), 2)
        got = self.updates()
        self.assertEqual(sorted(got), ["anna@example.com", "maya@example.com"])
        for to, message in got.items():
            self.assertEqual((message["op"], message["title"]), ("update", cards.SUMMARIES["closed"]))
            self.assertNotIn("request", message)
            self.assertEqual(cardcheck.check(message["card"]), [])
            self.assertEqual(actions_of(message["card"]), [])
            self.assertIn("Not worth it by Anna", " ".join(texts(message["card"])))
        self.assertEqual((got["maya@example.com"]["message"], got["anna@example.com"]["message"]), ("1731331200001", "1731331200002"), "each person's own message")

    def test_it_is_done_once_and_each_try_is_written(self):
        self.end("declined")
        self.world.run()
        self.world.clock.advance(minutes=30)
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual([(m.kind, m.status) for m in self.world.tries(cs.MAYA, offers.CLOSED)], [("card-closed", "sent")])

    def test_an_approval_an_answer_to_advice_and_an_expiry_close_it_too(self):
        for make, state, decision, words in ((cs.change_plan, "approved", "approve", "Decided: Approved by Anna"), (cs.change_plan, "consumed", "approve", "Decided: Approved by Anna"),
                                             (cs.advice_plan, "consumed", "approve", "Decided: Worth acting on by Anna"), (cs.advice_plan, "expired", None, "Expired. Nothing more to do.")):
            with self.subTest(state=state, plan=make.__name__):
                world = cs.World()
                plan = world.open_plan(make(expires_at="2026-12-01T00:00:00Z"))
                world.channel(cs.MAYA)
                world.introduce(cs.MAYA)
                offers.record_posted(written(), world.store, world.people, world.clock)
                world.store.plan_put(dataclasses.replace(plan, state=state))
                if decision:
                    world.store.decision_put(DecisionRecord(cs.PLAN_ID, cs.ANNA, "Anna", decision, "2026-11-05T10:30:00Z", cs.CODE))
                self.assertEqual(world.run(), 1)
                self.assertIn(words, " ".join(texts(world.queue_fake.messages()[0]["card"])))

    def test_a_card_that_the_flow_never_reported_is_left_alone(self):
        world = cs.World()
        plan = world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        world.store.plan_put(dataclasses.replace(plan, state="declined"))
        self.assertEqual((world.run(), world.queue_fake.calls), (0, []))

    def test_a_queue_that_does_not_take_it_is_tried_again_after_fifteen_minutes_and_not_before(self):
        self.end("declined")
        self.fake.replies.extend([500, 500])
        self.world.run()
        self.assertEqual(sorted(m.status for m in self.world.tries(cs.MAYA, offers.CLOSED)), ["failed"])
        self.world.clock.advance(minutes=10)
        self.assertEqual(self.world.run(), 0)
        self.world.clock.advance(minutes=6)
        self.assertEqual(self.world.run(), 2)
        self.assertEqual(sorted(m.status for m in self.world.tries(cs.MAYA, offers.CLOSED)), ["failed", "sent"])
        self.world.clock.advance(hours=1)
        self.assertEqual(self.world.run(), 0)

    def test_a_pulled_switch_or_a_pause_does_not_keep_a_card_open_because_it_tells_nobody_anything_new(self):
        self.end("declined")
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.world.channel(cs.MAYA, paused_until="2026-12-31T00:00:00Z")
        self.assertEqual(self.world.run(), 2)


if __name__ == "__main__":
    unittest.main()
