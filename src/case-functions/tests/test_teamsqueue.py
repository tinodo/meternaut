"""The message that carries a Teams card (cases/teamsqueue.py): its shape, its size, the one call that puts it on the queue, and what a try that goes wrong says.

The Queue service is a fake. No test touches the network.
"""
import json
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import cardcheck, cards, teamsqueue
from cases.http import Client, Refused
from cases.redact import Redactor
from test_cards import BASE, brief_of, ctx_for

TITLE = "[Meternaut] A decision waits for you"
TO = "maya@example.com"
ID = "a1b2c3d4e5f6"


def a_card() -> dict:
    brief = brief_of()
    return cards.decision_card(brief, ctx_for(brief))


def a_text_card(text: str) -> dict:
    card = a_card()
    card["body"].insert(2, {"type": "TextBlock", "id": "filler", "text": text, "wrap": True})
    return card


class TheMessage(unittest.TestCase):
    def test_it_is_one_json_text_of_five_keys_in_this_order(self):
        text = teamsqueue.render(ID, TO, TITLE, a_card())
        message = json.loads(text)
        self.assertEqual(list(message), ["v", "id", "to", "title", "card"])
        self.assertEqual((message["v"], message["id"], message["to"], message["title"]), (1, ID, TO, TITLE))
        self.assertEqual(message["card"], a_card())
        self.assertTrue(text.startswith('{"v":1,"id":"a1b2c3d4e5f6","to":"maya@example.com","title":'), "compact, and not base64")
        self.assertNotIn("\n", text)

    def test_it_is_utf_8_and_not_ascii_escapes(self):
        card = a_text_card("The disk costs \u20ac 41 a month, caf\u00e9")
        text = teamsqueue.render(ID, TO, TITLE, card)
        self.assertIn("\u20ac 41 a month, caf\u00e9", text)
        self.assertEqual(json.loads(text)["card"], card)

    def test_it_is_far_below_its_limit_for_a_real_card_and_the_limit_is_the_one_that_was_set(self):
        self.assertEqual(teamsqueue.MAX_BYTES, 30000)
        self.assertLess(len(teamsqueue.render(ID, TO, TITLE, a_card()).encode("utf-8")), 8000)

    def test_a_message_over_the_limit_is_too_big_and_is_never_cut(self):
        with mock.patch.object(teamsqueue, "MAX_BYTES", 2000):
            with self.assertRaises(teamsqueue.TooBig):
                teamsqueue.render(ID, TO, TITLE, a_card())
        exact = len(teamsqueue.render(ID, TO, TITLE, a_card()).encode("utf-8"))
        with mock.patch.object(teamsqueue, "MAX_BYTES", exact):
            self.assertEqual(json.loads(teamsqueue.render(ID, TO, TITLE, a_card()))["id"], ID, "a message of exactly the limit is let through")
        with mock.patch.object(teamsqueue, "MAX_BYTES", exact - 1):
            with self.assertRaises(teamsqueue.TooBig):
                teamsqueue.render(ID, TO, TITLE, a_card())

    def test_a_card_that_is_too_large_for_a_card_is_a_message_that_is_too_big(self):
        with self.assertRaises(teamsqueue.TooBig):
            teamsqueue.render(ID, TO, TITLE, a_text_card("x" * 21000))

    def test_a_text_that_grows_when_it_is_escaped_for_the_queue_is_held_to_the_size_of_the_queue(self):
        card = a_text_card("&" * 12500)
        self.assertEqual(cardcheck.check(card), [])
        self.assertLess(len(json.dumps(card)), teamsqueue.MAX_BYTES)
        with self.assertRaises(teamsqueue.TooBig):
            teamsqueue.render(ID, TO, TITLE, card)
        self.assertEqual(json.loads(teamsqueue.render(ID, TO, TITLE, a_text_card("&" * 3000)))["card"]["body"][2]["text"], "&" * 3000)

    def test_the_address_is_an_address_and_nothing_that_could_be_two_or_hide_something(self):
        for bad in ("", "maya", "maya@", "@example.com", "a b@example.com", "maya@example.com\n", "maya@example.com, evil@example.com", '"maya"@example.com', "maya@example..com;x",
                    "maya@example.com>", "x" * 250 + "@example.com", None, 5):
            with self.subTest(to=bad):
                with self.assertRaises(teamsqueue.MessageError):
                    teamsqueue.render(ID, bad, TITLE, a_card())

    def test_the_id_and_the_title_are_what_they_have_to_be(self):
        for bad in ("", "a b", "a/b", "a" * 65, None, "a\n"):
            with self.subTest(id=bad):
                with self.assertRaises(teamsqueue.MessageError):
                    teamsqueue.render(bad, TO, TITLE, a_card())
        for bad in ("", " ", "two\nlines", "bidi\u202e", "x" * 121, None):
            with self.subTest(title=bad):
                with self.assertRaises(teamsqueue.MessageError):
                    teamsqueue.render(ID, TO, bad, a_card())

    def test_a_card_that_does_not_pass_the_check_is_not_a_message(self):
        for change in (lambda c: c.update({"version": "1.5"}), lambda c: c["body"].append({"type": "Input.Text", "id": "x", "label": "x"}),
                       lambda c: c["body"].append({"type": "ActionSet", "actions": [{"type": "Action.Execute", "title": "x", "verb": "x"}]}), lambda c: c.pop("fallbackText")):
            card = a_card()
            change(card)
            with self.subTest(problem=cardcheck.check(card)[:1]):
                with self.assertRaises(teamsqueue.MessageError) as raised:
                    teamsqueue.render(ID, TO, TITLE, card)
                self.assertNotIsInstance(raised.exception, teamsqueue.TooBig)
        with self.assertRaises(teamsqueue.MessageError):
            teamsqueue.render(ID, TO, TITLE, "not a card")


def client(fake: cs.FakeQueue, account: str = cs.ACCOUNT, queue: str = cs.QUEUE) -> Client:
    return Client(teamsqueue.queue_calls(account, queue), Redactor(), transport=fake, sleep=lambda seconds: None)


class TheCallThatPutsIt(unittest.TestCase):
    def test_the_list_of_calls_holds_one_post_to_this_queue_of_this_account(self):
        calls = teamsqueue.queue_calls(cs.ACCOUNT, cs.QUEUE)
        self.assertEqual([method for method, _ in calls], ["POST"])
        fake = cs.FakeQueue()
        http = client(fake)
        http.check("POST", cs.QUEUE_URL)
        http.check("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net/{cs.QUEUE}/messages")
        for method, url in (("GET", cs.QUEUE_URL), ("DELETE", cs.QUEUE_URL), ("PUT", cs.QUEUE_URL), ("POST", cs.QUEUE_URL.replace("https", "http")),
                            ("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net/cases-control/messages"), ("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net/{cs.QUEUE}"),
                            ("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net/{cs.QUEUE}/messages/x"), ("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net/{cs.QUEUE}-poison/messages"),
                            ("POST", f"https://other.queue.core.windows.net/{cs.QUEUE}/messages"), ("POST", f"https://{cs.ACCOUNT}.table.core.windows.net/{cs.QUEUE}/messages"),
                            ("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net.evil.example/{cs.QUEUE}/messages")):
            with self.subTest(method=method, url=url):
                with self.assertRaises(Refused):
                    http.check(method, url)

    def test_the_names_are_the_names_of_an_account_and_of_a_queue(self):
        for account, queue in (("", cs.QUEUE), ("ST", cs.QUEUE), ("st", cs.QUEUE), ("st-example", cs.QUEUE), (cs.ACCOUNT, ""), (cs.ACCOUNT, "Teams-Cards"), (cs.ACCOUNT, "te"),
                               (cs.ACCOUNT, "teams--cards"), (cs.ACCOUNT, "-teams"), (cs.ACCOUNT, "teams-"), (cs.ACCOUNT, "teams_cards"), (cs.ACCOUNT, "teams/cards"), (cs.ACCOUNT, "a" * 64)):
            with self.subTest(account=account, queue=queue):
                with self.assertRaises(ValueError):
                    teamsqueue.queue_calls(account, queue)

    def test_one_put_is_one_post_of_xml_with_the_token_of_the_identity_and_a_ttl(self):
        fake = cs.FakeQueue()
        resources: list[str] = []
        queue = teamsqueue.CardQueue(client(fake), lambda resource: resources.append(resource) or cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE, Redactor(), cs.Moving())
        text = teamsqueue.render(ID, TO, TITLE, a_card())
        delivery = queue.put(text)
        self.assertEqual(delivery.status, "sent")
        self.assertEqual(resources, ["https://storage.azure.com/"])
        (call,) = fake.calls
        self.assertEqual((call["method"], call["url"]), ("POST", f"https://{cs.ACCOUNT}.queue.core.windows.net/{cs.QUEUE}/messages?messagettl=86400"))
        self.assertEqual({key: call["headers"][key] for key in ("Authorization", "x-ms-version", "Content-Type")},
                         {"Authorization": f"Bearer {cs.STORAGE_TOKEN}", "x-ms-version": "2020-12-06", "Content-Type": "application/xml"})
        self.assertRegex(call["headers"]["x-ms-date"], r"^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} 2026 \d{2}:\d{2}:\d{2} GMT$")
        document = ET.fromstring(call["data"].decode("utf-8"))
        self.assertEqual((document.tag, [child.tag for child in document]), ("QueueMessage", ["MessageText"]))
        self.assertEqual(document.find("MessageText").text, text, "what the flow reads is the text, unescaped by the service")

    def test_ampersands_angle_brackets_and_non_ascii_survive_the_xml(self):
        text = teamsqueue.render(ID, TO, TITLE, a_text_card("R&D <b>caf\u00e9</b> & \u20ac"))
        fake = cs.FakeQueue()
        teamsqueue.CardQueue(client(fake), lambda resource: cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE).put(text)
        self.assertEqual(fake.texts(), [text])
        self.assertIn("&amp;", fake.calls[0]["data"].decode("utf-8"))
        self.assertEqual(fake.messages()[0]["card"]["body"][2]["text"], "R&D <b>caf\u00e9</b> & \u20ac")

    def test_a_text_that_is_too_big_is_not_put(self):
        fake = cs.FakeQueue()
        queue = teamsqueue.CardQueue(client(fake), lambda resource: cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE)
        for text in ("x" * (teamsqueue.MAX_BYTES + 1), "&" * 20000, None, 5):
            with self.subTest(size=len(str(text))):
                self.assertEqual(queue.put(text).status, "failed")
        self.assertEqual(fake.calls, [])

    def test_a_token_that_is_not_a_token_is_never_sent(self):
        for token in ("", "two words", "line\nbreak", None, 5):
            fake = cs.FakeQueue()
            delivery = teamsqueue.CardQueue(client(fake), lambda resource, token=token: token, cs.ACCOUNT, cs.QUEUE).put("{}")
            with self.subTest(token=token):
                self.assertEqual((delivery.status, fake.calls), ("failed", []))

    def test_what_a_refusal_says_never_holds_the_token(self):
        fake = cs.FakeQueue()
        fake.replies = [(403, f"<Error><Code>AuthorizationFailure</Code><Message>token {cs.STORAGE_TOKEN} is not allowed</Message></Error>".encode())]
        delivery = teamsqueue.CardQueue(client(fake), lambda resource: cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE).put("{}")
        self.assertEqual(delivery.status, "failed")
        self.assertNotIn(cs.STORAGE_TOKEN, delivery.detail)
        self.assertLessEqual(len(delivery.detail), 400)

    def test_the_answers_in_plain_words(self):
        said = {}
        for status in (401, 403, 404, 413, 400, 500, 503, 0):
            fake = cs.FakeQueue()
            fake.replies = [OSError("down")] if status == 0 else [status] * 3
            said[status] = teamsqueue.CardQueue(client(fake), lambda resource: cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE).put("{}")
            self.assertEqual(said[status].status, "failed", status)
        self.assertIn("did not accept the app's token", said[401].detail)
        self.assertIn("Storage Queue Data Contributor", said[403].detail)
        self.assertIn("The queue is not there", said[404].detail)
        self.assertIn("too big", said[413].detail)
        self.assertIn("may have been taken", said[500].detail)
        self.assertIn("may have been taken", said[0].detail)
        self.assertNotIn("may have been taken", said[400].detail)

    def test_a_put_that_succeeds_says_that_this_is_not_delivery(self):
        delivery = teamsqueue.CardQueue(client(cs.FakeQueue()), lambda resource: cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE).put("{}")
        self.assertEqual(delivery, teamsqueue.Delivery("sent", teamsqueue.SENT))
        self.assertIn("not delivery", delivery.detail)


class TheClientSendsXml(unittest.TestCase):
    def test_a_call_has_one_kind_of_body_at_the_most(self):
        fake = cs.FakeQueue()
        http = client(fake)
        with self.assertRaises(ValueError):
            http.request("POST", cs.QUEUE_URL, body={"a": 1}, xml="<a/>")
        with self.assertRaises(ValueError):
            http.request("POST", cs.QUEUE_URL, form={"a": "1"}, xml="<a/>")
        self.assertEqual(fake.calls, [])
        http.request("POST", cs.QUEUE_URL, xml="<a>\u00e9</a>")
        self.assertEqual((fake.calls[0]["data"], fake.calls[0]["headers"]["Content-Type"]), ("<a>\u00e9</a>".encode("utf-8"), "application/xml"))


class TheSettingThatSwitchesTheCardsOn(unittest.TestCase):
    def test_the_queue_is_named_by_the_setting_and_without_it_no_card_is_sent(self):
        from cases import loop_config
        from test_notify import ENV
        self.assertIsNone(loop_config.load(ENV).cards_queue)
        self.assertEqual(loop_config.load({**ENV, "TEAMS_CARDS_QUEUE": " teams-cards "}).cards_queue, "teams-cards")
        self.assertEqual(loop_config.TEAMS_CARDS_QUEUE, "TEAMS_CARDS_QUEUE")
        for bad in ("Teams-Cards", "te", "teams--cards", "-teams", "teams_cards", "a/b", "x" * 64):
            with self.subTest(queue=bad):
                with self.assertRaises(loop_config.LoopConfigError) as raised:
                    loop_config.load({**ENV, "TEAMS_CARDS_QUEUE": bad})
                self.assertIn("TEAMS_CARDS_QUEUE is not a queue name", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
