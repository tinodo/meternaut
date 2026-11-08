"""The Bot Connector client (cases/connector.py) and the conversation references (cases/references.py).

The Connector is a fake that records what the bot sends. The token is a made-up string: the tests check that it goes only in the Authorization header and never in a text that the bot returns.
"""
import datetime as dt
import json
import unittest

import support  # noqa: F401  (puts the app on the path)
import teamssupport as ts
from cases.connector import Connector, connector_calls
from cases.http import Client, Refused
from cases.models import StoreError
from cases.redact import Redactor
from cases.references import MemoryReferences, Reference, ReferenceTable, made, references_calls
from test_store import ACCOUNT, FakeTables

NOW = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)


def connector(fake: ts.FakeConnector, token=lambda resource: ts.BOT_TOKEN) -> Connector:
    redact = Redactor()
    return Connector(Client(connector_calls(), redact, transport=fake, sleep=lambda seconds: None), token, ts.APP_ID, redact)


class TheRequestsToTheConnector(unittest.TestCase):
    def setUp(self):
        self.fake = ts.FakeConnector()
        self.connector = connector(self.fake)

    def test_a_card_is_one_post_to_the_conversation_with_the_token_of_the_bot(self):
        delivery = self.connector.send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "hello"}, "29:1abc")
        self.assertEqual((delivery.status, delivery.id), ("sent", "activity-1"))
        (call,) = self.fake.calls
        self.assertEqual((call["method"], call["url"]), ("POST", f"{ts.SERVICE}v3/conversations/{ts.CONVERSATION}/activities"))
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {ts.BOT_TOKEN}")
        self.assertEqual(call["body"], {"type": "message", "text": "hello", "from": {"id": f"28:{ts.APP_ID}", "name": "Meternaut (AI)"}, "conversation": {"id": ts.CONVERSATION},
                                        "recipient": {"id": "29:1abc"}})

    def test_the_token_is_asked_for_the_bot_framework_and_goes_nowhere_else(self):
        asked = []
        connector(self.fake, lambda resource: asked.append(resource) or ts.BOT_TOKEN).send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x"})
        self.assertEqual(asked, ["https://api.botframework.com"])
        self.assertNotIn(ts.BOT_TOKEN, json.dumps(self.fake.calls[0]["body"]))

    def test_starting_a_conversation_names_the_person_the_bot_and_the_tenant(self):
        delivery = self.connector.start(ts.SERVICE, ts.MAYA, ts.TENANT)
        self.assertEqual((delivery.status, delivery.id), ("sent", "a:started-0123456789"))
        (call,) = self.fake.calls
        self.assertEqual((call["method"], call["url"]), ("POST", f"{ts.SERVICE}v3/conversations"))
        self.assertEqual(call["body"], {"bot": {"id": f"28:{ts.APP_ID}", "name": "Meternaut (AI)"}, "isGroup": False, "members": [{"id": ts.MAYA}], "tenantId": ts.TENANT,
                                        "channelData": {"tenant": {"id": ts.TENANT}}})

    def test_a_start_that_names_no_conversation_is_a_failure(self):
        self.fake.replies = [(201, {})]
        self.assertEqual(self.connector.start(ts.SERVICE, ts.MAYA, ts.TENANT).status, "failed")

    def test_the_bot_is_the_sender_whatever_the_activity_says(self):
        self.connector.send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x", "from": {"id": "29:somebody-else"}, "conversation": {"id": "a:other"}})
        body = self.fake.calls[0]["body"]
        self.assertEqual((body["from"]["id"], body["conversation"]["id"]), (f"28:{ts.APP_ID}", ts.CONVERSATION))

    def test_what_teams_says_is_told_in_plain_words(self):
        for status, expected in ((403, "blocked"), (404, "gone"), (400, "failed"), (500, "failed"), (502, "failed")):
            self.fake.calls.clear()
            self.fake.replies = [(status, {"error": {"code": "SomethingFailed", "message": "the reason"}})]
            delivery = self.connector.send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x"})
            self.assertEqual(delivery.status, expected, status)
            self.assertNotIn(ts.BOT_TOKEN, delivery.detail)
            self.assertEqual(len(self.fake.calls), 1, f"{status} is not tried again: the activity may have been taken")

    def test_a_server_error_says_that_the_activity_may_have_arrived(self):
        self.fake.replies = [(503, {})]
        self.assertIn("may have been taken", self.connector.send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x"}).detail)

    def test_only_a_429_is_tried_again(self):
        self.fake.replies = [(429, {"error": {"code": "Throttled", "message": "slow"}}), (201, {"id": "activity-2"})]
        self.assertEqual(self.connector.send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x"}).status, "sent")
        self.assertEqual(len(self.fake.calls), 2)

    def test_no_token_is_no_call(self):
        def refuse(resource):
            raise RuntimeError("no identity endpoint")
        delivery = connector(self.fake, refuse).send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x"})
        self.assertEqual(delivery.status, "failed")
        self.assertEqual(self.fake.calls, [])
        for bad in ("", None, "two words", "line\nbreak"):
            self.assertEqual(connector(self.fake, lambda resource, bad=bad: bad).send(ts.SERVICE, ts.CONVERSATION, {"type": "message", "text": "x"}).status, "failed")
        self.assertEqual(self.fake.calls, [])

    def test_the_token_never_leaves_for_an_address_that_is_not_the_connector_of_teams(self):
        for service in ("https://evil.example/emea/", "http://smba.trafficmanager.net/emea/", "https://smba.trafficmanager.net.evil.example/emea/", "https://smba.trafficmanager.net/emea",
                        "https://smba.trafficmanager.net/emea/extra/", "https://smba.trafficmanager.net/EMEA/", "https://user@smba.trafficmanager.net/emea/", ""):
            self.assertEqual(self.connector.send(service, ts.CONVERSATION, {"type": "message", "text": "x"}).status, "failed", service)
            self.assertEqual(self.connector.start(service, ts.MAYA, ts.TENANT).status, "failed", service)
        self.assertEqual(self.fake.calls, [])

    def test_a_conversation_id_cannot_change_the_path_of_the_call(self):
        for bad in ("a:1/../x", "a:1?x=1", "a:1#x", "a:1 b", "a:1\nb", "", "a" * 301, "a:1%2Fb"):
            self.assertEqual(self.connector.send(ts.SERVICE, bad, {"type": "message", "text": "x"}).status, "failed", repr(bad))
        self.assertEqual(self.connector.start(ts.SERVICE, "29:abc/../x", ts.TENANT).status, "failed")
        self.assertEqual(self.connector.start(ts.SERVICE, ts.MAYA, "not-a-tenant").status, "failed")
        self.assertEqual(self.fake.calls, [])

    def test_the_list_of_calls_holds_the_two_posts_and_nothing_else(self):
        calls = connector_calls()
        self.assertEqual({method for method, _ in calls}, {"POST"})
        client = Client(calls, Redactor(), transport=self.fake, sleep=lambda seconds: None)
        for method, url in (("GET", f"{ts.SERVICE}v3/conversations"), ("POST", "https://smba.trafficmanager.net/emea/v3/other"), ("POST", "https://login.botframework.com/v3/conversations"),
                            ("DELETE", f"{ts.SERVICE}v3/conversations/{ts.CONVERSATION}/activities"), ("POST", f"{ts.SERVICE}v3/conversations/{ts.CONVERSATION}/members")):
            with self.assertRaises(Refused):
                client.request(method, url, body={})
        self.assertEqual(self.fake.calls, [])

    def test_the_app_id_is_a_guid(self):
        with self.assertRaises(ValueError):
            Connector(Client(connector_calls(), Redactor(), transport=self.fake), lambda resource: "x", "not-a-guid", Redactor())


class TheReferences(unittest.TestCase):
    def test_a_reference_is_made_in_the_form_that_is_kept(self):
        reference = made(ts.MAYA.upper(), ts.CONVERSATION, "https://smba.trafficmanager.net/emea", "29:abc", ts.TENANT.upper(), NOW)
        self.assertEqual((reference.oid, reference.service_url, reference.tenant_id, reference.updated_at), (ts.MAYA, ts.SERVICE, ts.TENANT, "2026-11-05T10:18:00Z"))
        self.assertEqual(Reference.from_json(reference.to_json()), reference)

    def test_what_is_not_the_connector_of_teams_is_not_kept(self):
        for field, value in (("service_url", "https://evil.example/emea/"), ("conversation_id", "a:1/../x"), ("oid", "not-a-guid"), ("tenant_id", "x"), ("user_id", "29:a b")):
            arguments = dict(oid=ts.MAYA, conversation_id=ts.CONVERSATION, service_url=ts.SERVICE, user_id="29:abc", tenant_id=ts.TENANT)
            arguments[field] = value
            with self.assertRaises(ValueError, msg=field):
                made(now=NOW, **arguments)

    def test_the_memory_and_the_table_keep_one_row_for_each_person(self):
        tables = FakeTables()
        client = Client(references_calls(ACCOUNT), Redactor(), transport=tables.transport, sleep=lambda seconds: None)
        for keeper in (MemoryReferences(), ReferenceTable(client, lambda resource: ts.BOT_TOKEN, ACCOUNT, clock=lambda: NOW)):
            self.assertIsNone(keeper.reference_get(ts.MAYA))
            first = made(ts.MAYA, ts.CONVERSATION, ts.SERVICE, "29:abc", ts.TENANT, NOW)
            keeper.reference_put(first)
            second = made(ts.MAYA, "a:1other", "https://smba.trafficmanager.net/amer/", "29:abc", ts.TENANT, NOW)
            keeper.reference_put(second)
            self.assertEqual(keeper.reference_get(ts.MAYA.upper()), second)
            self.assertIsNone(keeper.reference_get(ts.ANNA))
            keeper.reference_delete(ts.MAYA)
            self.assertIsNone(keeper.reference_get(ts.MAYA))
            keeper.reference_delete(ts.MAYA)  # forgetting what is not there is not an error

    def test_a_row_that_is_not_valid_is_not_trusted_when_it_is_read(self):
        keeper = MemoryReferences()
        keeper.rows[ts.MAYA] = Reference(ts.MAYA, ts.CONVERSATION, "https://evil.example/emea/", "29:abc", ts.TENANT, "2026-11-05T10:18:00Z")
        self.assertIsNone(keeper.reference_get(ts.MAYA))
        with self.assertRaises(StoreError):
            keeper.reference_put(keeper.rows[ts.MAYA])

    def test_the_table_is_its_own_and_the_list_of_calls_holds_this_table_alone(self):
        tables = FakeTables()
        client = Client(references_calls(ACCOUNT), Redactor(), transport=tables.transport, sleep=lambda seconds: None)
        keeper = ReferenceTable(client, lambda resource: ts.BOT_TOKEN, ACCOUNT, clock=lambda: NOW)
        keeper.reference_put(made(ts.MAYA, ts.CONVERSATION, ts.SERVICE, "29:abc", ts.TENANT, NOW))
        self.assertEqual(list(tables.tables), ["mnteams"])
        for method, url in (("PUT", f"https://{ACCOUNT}.table.core.windows.net/mnplans(PartitionKey='p',RowKey='x')"), ("GET", f"https://{ACCOUNT}.table.core.windows.net/mnteams()"),
                            ("PUT", "https://other.table.core.windows.net/mnteams(PartitionKey='r',RowKey='x')")):
            with self.assertRaises(Refused):
                client.request(method, url, body={})


if __name__ == "__main__":
    unittest.main()
