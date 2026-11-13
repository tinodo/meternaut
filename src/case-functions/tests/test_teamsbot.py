"""The Teams client of the bot way (cases/teamsbot.py): the token of the app principal, the three calls of the Bot Connector, what each failure means in plain words, and the list of calls that is exact.

The token endpoint of Microsoft Entra and the Bot Connector are one fake transport; nothing touches a network. Every id is invented.
"""
import json
import socket
import ssl
import unittest
import urllib.error
from http.client import RemoteDisconnected
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import cards, http, teamsbot
from cases.delegated import ASSERTION_RESOURCE, ASSERTION_TYPE
from cases.http import Refused
from cases.identity import Identity, IdentityError
from cases.loop_config import TeamsWay
from cases.redact import Redactor

TENANT, APP, IDENTITY, PERSON = "11111111-aaaa-4bbb-8ccc-000000000001", "22222222-aaaa-4bbb-8ccc-000000000002", "33333333-aaaa-4bbb-8ccc-000000000003", cs.MAYA
WAY = TeamsWay("bot", "", APP, IDENTITY, TENANT)
SERVICE = "https://smba.trafficmanager.net/teams/"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
CREATE_URL = f"{SERVICE}v3/conversations"
CONVERSATION, ACTIVITY = "a:1Abc-DEF_ghi", "1731331200000"
POST_URL = f"{CREATE_URL}/{CONVERSATION}/activities"
UPDATE_URL = f"{POST_URL}/{ACTIVITY}"
ACCESS = "bot-access-token-0123456789abcdef"
ASSERTION = "assertion-of-the-managed-identity-0123456789"
CARD = {"type": "AdaptiveCard", "version": "1.4", "body": []}


def answer(status, body=None, **headers):
    return status, {k.replace("_", "-"): v for k, v in headers.items()}, (body if isinstance(body, bytes) else json.dumps(body).encode("utf-8") if body is not None else b"")


GOOD = {
    "token": answer(200, {"token_type": "Bearer", "expires_in": 3599, "access_token": ACCESS}), "create": answer(201, {"id": CONVERSATION}),
    "send": answer(201, {"id": ACTIVITY}), "update": answer(200, {"id": ACTIVITY}),
}


class FakeTeams:
    """Microsoft Entra's token endpoint and the Bot Connector: records every call, answers the next reply that a test queued for the step, or the good one."""

    def __init__(self):
        self.calls, self.replies = [], {}

    def __call__(self, method, url, headers, data, timeout):
        step = "token" if url == TOKEN_URL else "create" if url == CREATE_URL else "send" if method == "POST" else "update"
        self.calls.append({"step": step, "method": method, "url": url, "headers": dict(headers), "data": data})
        reply = self.replies[step].pop(0) if self.replies.get(step) else GOOD[step]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def steps(self):
        return [call["step"] for call in self.calls]

    def body(self, step):
        return json.loads(next(call for call in self.calls if call["step"] == step)["data"])

    def form(self, step=None):
        from urllib.parse import parse_qs
        return {k: v[0] for k, v in parse_qs(next(call for call in self.calls if call["step"] == "token")["data"].decode("utf-8")).items()}


class Case(unittest.TestCase):
    def setUp(self):
        self.clock, self.fake, self.asked = cs.Moving(), FakeTeams(), []
        self.bot = self.make()

    def make(self, way=WAY, assertion=None):
        client = teamsbot.new_client(way, Redactor(), transport=self.fake, sleep=lambda seconds: None)
        return teamsbot.TeamsBot(way, assertion or (lambda resource: (self.asked.append(resource), ASSERTION)[1]), client, self.clock)

    def script(self, step, *replies):
        self.fake.replies[step] = list(replies)

    def refused(self, call):
        with self.assertRaises(teamsbot.BotError) as raised:
            call()
        return raised.exception


class TheTokenOfTheApp(Case):
    def test_the_assertion_of_the_managed_identity_is_the_client_assertion_of_a_client_credentials_request_for_the_scope_of_the_bot_connector(self):
        self.assertEqual(self.bot.token(), ACCESS)
        self.assertEqual(self.asked, [ASSERTION_RESOURCE], "the identity is asked for api://AzureADTokenExchange")
        (call,) = self.fake.calls
        self.assertEqual((call["method"], call["url"]), ("POST", TOKEN_URL))
        self.assertEqual(call["headers"]["Content-Type"], "application/x-www-form-urlencoded")
        self.assertNotIn("Authorization", call["headers"], "the request proves itself with the assertion, not with a token")
        self.assertEqual(self.fake.form(), {"grant_type": "client_credentials", "client_id": APP, "client_assertion_type": ASSERTION_TYPE, "client_assertion": ASSERTION,
                                            "scope": "https://api.botframework.com/.default"})
        self.assertEqual(ASSERTION_TYPE, "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")

    def test_a_token_is_kept_until_five_minutes_before_it_expires_and_then_asked_for_again(self):
        self.bot.token()
        self.clock.advance(seconds=3599 - 301)
        self.assertEqual((self.bot.token(), self.fake.steps()), (ACCESS, ["token"]), "still more than five minutes left: no second request")
        self.assertEqual(self.bot.status, 0, "no call was made")
        self.clock.advance(seconds=2)
        self.script("token", answer(200, {"token_type": "Bearer", "expires_in": 3599, "access_token": ACCESS + "-two"}))
        self.assertEqual((self.bot.token(), self.fake.steps()), (ACCESS + "-two", ["token", "token"]))

    def test_a_token_that_lives_five_minutes_or_less_is_not_kept(self):
        self.script("token", answer(200, {"token_type": "Bearer", "expires_in": 300, "access_token": ACCESS}))
        self.bot.token()
        self.bot.token()
        self.assertEqual(self.fake.steps(), ["token", "token"])

    def test_an_answer_that_is_not_a_bearer_token_is_not_used(self):
        for body in ({"token_type": "Bearer", "expires_in": 3599}, {"token_type": "Bearer", "expires_in": 3599, "access_token": "short"}, {"token_type": "MAC", "expires_in": 1, "access_token": ACCESS},
                     {"token_type": "Bearer", "access_token": ACCESS + " x\n"}, ["not", "an", "object"]):
            with self.subTest(body=body):
                self.clock.advance(minutes=5)
                self.script("token", answer(200, body))
                self.assertEqual(self.refused(self.bot.token).reason, "unauthorized")

    def test_the_numbers_of_an_error_of_microsoft_entra_are_kept_and_nothing_of_its_text(self):
        for status, code, aadsts in ((400, "invalid_client", 700213), (401, "invalid_client", 7000229), (400, "unauthorized_client", 700016), (400, "invalid_request", 0)):
            with self.subTest(code=code, aadsts=aadsts):
                self.clock.advance(minutes=5)
                description = f"AADSTS{aadsts}: the long text, with a trace id {ACCESS}" if aadsts else "the text"
                self.script("token", answer(status, {"error": code, "error_description": description, "error_codes": [aadsts]}))
                error = self.refused(self.bot.token)
                self.assertEqual((error.step, error.reason, error.status, error.aadsts), ("token", "unauthorized", status, aadsts))
                self.assertEqual(str(error), teamsbot.REASONS["unauthorized"])

    def test_a_managed_identity_that_gives_no_token_is_an_identity_that_is_wrong_and_no_call_is_made(self):
        def broken(resource):
            raise RuntimeError("the endpoint says " + ACCESS)
        error = self.refused(self.make(assertion=broken).token)
        self.assertEqual((error.step, error.reason, error.status, str(error)), ("token", "unauthorized", 0, teamsbot.REASONS["unauthorized"]))
        self.assertEqual(self.fake.calls, [])

    def test_a_throttled_or_unanswered_token_request_is_waited_out(self):
        self.script("token", answer(429, {"error": "x"}, retry_after="120"))
        self.assertEqual(self.refused(self.bot.token).reason, "throttled")
        self.clock.advance(minutes=2)
        self.script("token", answer(503), answer(503), answer(503))
        self.assertEqual(self.refused(self.bot.token).reason, "network")
        self.clock.advance(minutes=2)
        self.script("token", OSError("down"), OSError("down"), OSError("down"))
        self.assertEqual(self.refused(self.bot.token).reason, "network")

    def test_after_a_failure_no_call_is_made_for_a_minute_so_that_a_round_of_cards_waits_once(self):
        self.script("token", answer(401, {"error": "invalid_client"}))
        first = self.refused(self.bot.token)
        calls = len(self.fake.calls)
        self.clock.advance(seconds=59)
        self.assertIs(self.refused(self.bot.token), first)
        self.assertEqual(len(self.fake.calls), calls)
        self.clock.advance(seconds=2)
        self.assertEqual((self.bot.token(), len(self.fake.calls)), (ACCESS, calls + 1))

    def test_the_minute_without_a_call_counts_from_the_end_of_the_failure_and_not_from_its_start(self):
        asked = []

        def stalls(resource):
            asked.append(resource)
            self.clock.advance(seconds=52)  # the platform's identity endpoint gave no answer for 52 seconds
            error = IdentityError("the managed identity endpoint gave no answer (TimeoutError) after 3 tries")
            error.transient = True
            raise error
        bot = self.make(assertion=stalls)
        first = self.refused(bot.token)
        self.clock.advance(seconds=30)  # 82 seconds after the start of the failure and 30 after its end
        self.assertIs(self.refused(bot.token), first)
        self.assertEqual(len(asked), 1, "the later cards of the round do not stall again")
        self.clock.advance(seconds=31)
        self.refused(bot.token)
        self.assertEqual(len(asked), 2, "a minute after the end of the failure the identity is asked again")

    def test_the_identity_is_given_the_time_that_is_left_of_the_round_and_none_without_a_round(self):
        given = []
        bot = self.make(assertion=lambda resource, within=None: (given.append(within), ASSERTION)[1])
        bot.token()
        bot.client.monotonic, bot.client.deadline = (lambda: 100.0), 125.0
        self.clock.advance(hours=2)
        bot.token()
        self.assertEqual(given, [None, 25.0])

    def test_a_token_that_is_still_valid_is_used_when_a_new_one_cannot_be_had_and_no_card_fails_for_it(self):
        self.bot.token()
        self.clock.advance(seconds=3599 - 200)  # inside the last five minutes: a new one is asked for, and the Microsoft Entra ID service is down
        self.script("token", answer(503), answer(503), answer(503))
        self.assertEqual(self.bot.token(), ACCESS)
        asked = self.fake.steps().count("token")
        self.clock.advance(seconds=30)
        self.assertEqual((self.bot.token(), self.fake.steps().count("token")), (ACCESS, asked), "for a minute after the failure nothing is asked for, and the token that is valid is used")
        self.clock.advance(seconds=31)
        self.script("token", answer(200, {"token_type": "Bearer", "expires_in": 3599, "access_token": ACCESS + "-two"}))
        self.assertEqual(self.bot.token(), ACCESS + "-two")

    def test_a_token_that_has_expired_is_not_used_when_a_new_one_cannot_be_had(self):
        self.bot.token()
        self.clock.advance(seconds=3600)
        self.script("token", answer(503), answer(503), answer(503))
        self.assertEqual(self.refused(self.bot.token).reason, "network")

    def test_an_expiry_that_is_not_a_plain_number_does_not_crash_and_the_token_is_not_kept(self):
        for seconds in ("\u00b2", "\u0663\u0665\u0669\u0669", "\uff13\uff15\uff19\uff19", "3.5", "-5", "", None, True, [3599]):
            with self.subTest(seconds=seconds):
                self.fake.calls.clear()
                self.script("token", *[answer(200, {"token_type": "Bearer", "expires_in": seconds, "access_token": ACCESS})] * 2)
                self.assertEqual((self.bot.token(), self.bot.token(), self.fake.steps()), (ACCESS, ACCESS, ["token", "token"]))

    def test_a_managed_identity_that_did_not_answer_is_no_answer_and_one_that_refused_is_a_wrong_identity(self):
        def identity(status):
            return Identity({"IDENTITY_ENDPOINT": "http://localhost:8081/msi/token", "IDENTITY_HEADER": "h"}, fetch=lambda url, headers, timeout: (status, b""), sleep=lambda seconds: None).token

        def lost(url, headers, timeout):
            raise TimeoutError("slow")
        for token, reason in ((identity(503), "network"), (identity(429), "network"), (Identity({"IDENTITY_ENDPOINT": "http://localhost:8081/msi/token", "IDENTITY_HEADER": "h"}, fetch=lost,
                                                                                                    sleep=lambda seconds: None).token, "network"), (identity(400), "unauthorized"), (identity(404), "unauthorized")):
            with self.subTest(reason=reason):
                error = self.refused(self.make(assertion=token).token)
                self.assertEqual((error.reason, str(error), self.fake.calls), (reason, teamsbot.REASONS[reason], []))


class TheCallsOfTheBotConnector(Case):
    def test_the_conversation_is_made_with_the_object_id_of_the_person_and_the_card_is_posted_in_it(self):
        self.assertEqual(self.bot.send(PERSON, CARD, "A title"), (CONVERSATION, ACTIVITY))
        self.assertEqual(self.fake.steps(), ["token", "create", "send"])
        create, send = self.fake.calls[1], self.fake.calls[2]
        self.assertEqual((create["method"], create["url"], send["method"], send["url"]), ("POST", CREATE_URL, "POST", POST_URL))
        for call in (create, send):
            self.assertEqual((call["headers"]["Authorization"], call["headers"]["Content-Type"]), (f"Bearer {ACCESS}", "application/json"))
        self.assertEqual(self.fake.body("create"), {"bot": {"id": f"28:{APP}"}, "isGroup": False, "members": [{"id": PERSON}], "channelData": {"tenant": {"id": TENANT}}, "tenantId": TENANT})
        self.assertEqual(self.fake.body("send"), {"type": "message", "summary": "A title", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": CARD}]})

    def test_a_card_is_replaced_by_a_put_to_its_activity(self):
        self.bot.update(CONVERSATION, ACTIVITY, {**CARD, "body": [1]}, "Closed")
        (_, call) = self.fake.calls
        self.assertEqual((call["method"], call["url"]), ("PUT", UPDATE_URL))
        self.assertEqual(self.fake.body("update")["attachments"][0]["content"]["body"], [1])

    def test_the_token_is_asked_for_once_for_the_three_calls(self):
        self.bot.send(PERSON, CARD, "x")
        self.bot.update(CONVERSATION, ACTIVITY, CARD, "x")
        self.assertEqual(self.fake.steps(), ["token", "create", "send", "update"])

    def test_an_answer_without_a_usable_id_is_a_refusal_and_no_further_call_is_made(self):
        for step, bad in (("create", {}), ("create", {"id": "../x"}), ("create", {"id": "a b"}), ("create", {"id": "x" * 201}), ("create", ["id"]), ("send", {"id": "%2e%2e"}), ("send", {"id": 7})):
            with self.subTest(step=step, bad=bad):
                self.fake.calls.clear()
                self.script(step, answer(201, bad))
                error = self.refused(lambda: self.bot.send(PERSON, CARD, "x"))
                self.assertEqual((error.step, error.reason), (step, "other"))
                self.assertNotIn("send" if step == "create" else "update", self.fake.steps())

    def test_an_id_that_is_not_an_id_never_gets_into_an_address(self):
        for conversation, activity in (("..", "1"), (".", "1"), ("a/b", "1"), ("a%2fb", "1"), ("a?x=1", "1"), ("a b", "1"), ("", "1"), (CONVERSATION, ".."), (CONVERSATION, "1/2"), (CONVERSATION, "1#"),
                                       ("a" * 201, "1"), ("a\\b", "1"), ("a\u00e9b", "1")):
            with self.subTest(conversation=conversation[:20], activity=activity):
                error = self.refused(lambda: self.bot.update(conversation, activity, CARD, "x"))
                self.assertEqual((error.step, error.reason, str(error)), ("update", "other", teamsbot.NOT_REPLACED))
        self.assertEqual(self.refused(lambda: self.bot.post("../x", CARD, "x")).step, "send")
        self.assertEqual(self.fake.calls, [])

    def test_the_card_is_posted_once_even_when_the_answer_is_lost_and_is_tried_again_only_after_a_throttle(self):
        self.bot.create(PERSON)
        for replies, calls in (([answer(500), answer(201, {"id": ACTIVITY})], 1), ([OSError("lost")], 1), ([answer(502)], 1), ([answer(429, {}, retry_after="1"), answer(201, {"id": ACTIVITY})], 2)):
            with self.subTest(replies=len(replies), calls=calls):
                self.fake.calls.clear()
                self.script("send", *replies)
                try:
                    self.bot.post(CONVERSATION, CARD, "x")
                except teamsbot.BotError:
                    pass
                self.assertEqual(self.fake.steps(), ["send"] * calls)

    def test_a_replacement_and_the_creation_of_a_conversation_may_be_tried_again_for_they_change_nothing_twice(self):
        self.script("update", answer(503), answer(200, {"id": ACTIVITY}))
        self.bot.update(CONVERSATION, ACTIVITY, CARD, "x")
        self.assertEqual(self.fake.steps(), ["token", "update", "update"])
        self.fake.calls.clear()
        self.script("create", answer(502), answer(201, {"id": CONVERSATION}))
        self.assertEqual(self.bot.create(PERSON), CONVERSATION)
        self.assertEqual(self.fake.steps(), ["create", "create"])

    def test_a_status_that_a_call_made_is_known_to_the_caller(self):
        self.bot.create(PERSON)
        self.assertEqual(self.bot.status, 201)
        self.bot.update(CONVERSATION, ACTIVITY, CARD, "x")
        self.assertEqual(self.bot.status, 200)

    def test_a_412_is_tried_again_for_the_calls_that_can_be_repeated_and_not_for_the_post_of_a_card(self):
        self.script("create", answer(412), answer(201, {"id": CONVERSATION}))
        self.script("update", answer(412), answer(200, {"id": ACTIVITY}))
        self.assertEqual(self.bot.create(PERSON), CONVERSATION)
        self.bot.update(CONVERSATION, ACTIVITY, CARD, "x")
        self.assertEqual(self.fake.steps(), ["token", "create", "create", "update", "update"])
        self.fake.calls.clear()
        self.script("send", answer(412), answer(201, {"id": ACTIVITY}))
        error = self.refused(lambda: self.bot.post(CONVERSATION, CARD, "x"))
        self.assertEqual((error.reason, error.status, error.maybe_sent, self.fake.steps()), ("network", 412, False, ["send"]), "a 412 says that the card was not taken: the next round tries again")

    def test_a_401_of_the_bot_connector_drops_the_token_so_that_the_next_call_asks_for_a_new_one(self):
        self.bot.create(PERSON)
        self.script("send", answer(401, {"message": "Authorization has been denied for this request."}))
        self.assertEqual(self.refused(lambda: self.bot.post(CONVERSATION, CARD, "x")).reason, "unauthorized")
        self.script("token", answer(200, {"token_type": "Bearer", "expires_in": 3599, "access_token": ACCESS + "-two"}))
        self.bot.post(CONVERSATION, CARD, "x")
        self.assertEqual(self.fake.steps(), ["token", "create", "send", "token", "send"])
        self.assertEqual(self.fake.calls[-1]["headers"]["Authorization"], f"Bearer {ACCESS}-two")


class WhenTheAnswerOfAPostIsLost(Case):
    """A card whose post was sent and whose answer is no answer (no answer at all, a 5xx, a 2xx without an id) may have arrived: the error says so, and nobody posts it again."""

    def post(self, *replies):
        self.bot.token()
        self.script("send", *replies)
        return self.refused(lambda: self.bot.post(CONVERSATION, CARD, "x"))

    def test_a_post_without_a_usable_answer_may_have_arrived_and_is_made_once(self):
        for reply in (answer(500), answer(502), answer(504), OSError("lost"), TimeoutError("slow"), RemoteDisconnected("closed"), ConnectionResetError("reset"), answer(201, {}), answer(201, {"id": "../x"}),
                      answer(200, b"not json")):
            with self.subTest(reply=str(reply)[:30]):
                self.fake.calls.clear()
                error = self.post(*[reply] * 3)
                self.assertEqual((error.step, error.maybe_sent, str(error), teamsbot.REASON_OF[str(error)], self.fake.steps().count("send")), ("send", True, teamsbot.NOT_RETRIED, "network", 1))

    def test_a_post_that_was_refused_or_not_made_may_not_have_arrived(self):
        for reply in (answer(429, {}, retry_after="3600"), answer(403, FORBIDDEN), answer(400, {"error": {"code": "BadArgument"}}), answer(401), answer(412)):
            with self.subTest(reply=str(reply)[:30]):
                error = self.post(*[reply] * 3)
                self.assertEqual((error.maybe_sent, str(error) == teamsbot.NOT_RETRIED), (False, False))

    def test_a_post_that_could_not_connect_was_never_sent_and_is_tried_again(self):
        # urllib raises URLError while the connection is made (no such host, refused, a certificate that is not accepted), so the request never left: the card may be posted by the next round
        for failure in (urllib.error.URLError(ConnectionRefusedError()), urllib.error.URLError(socket.gaierror(-2, "no such host")), urllib.error.URLError(ssl.SSLCertVerificationError("no")),
                        urllib.error.URLError(TimeoutError("timed out"))):
            with self.subTest(failure=repr(failure.reason)[:40]):
                self.fake.calls.clear()
                error = self.post(*[failure] * 3)
                self.assertEqual((error.maybe_sent, error.reason, str(error), self.fake.steps().count("send")), (False, "network", teamsbot.REASONS["network"], 1))

    def test_a_post_that_was_not_started_for_the_time_of_the_round_is_used_up_may_not_have_arrived(self):
        self.bot.token()
        self.bot.client.deadline = self.bot.client.monotonic() - 1
        self.assertTrue(self.bot.late())
        error = self.refused(lambda: self.bot.post(CONVERSATION, CARD, "x"))
        self.assertEqual((error.maybe_sent, error.reason, self.fake.steps()), (False, "network", ["token"]))

    def test_a_post_that_would_get_less_than_ten_seconds_is_not_made_so_that_a_slow_connector_is_not_taken_for_a_lost_answer(self):
        self.bot.token()
        self.bot.client.monotonic = lambda: 100.0
        for left in (9.9, 0.5):
            with self.subTest(left=left):
                self.bot.client.deadline = 100.0 + left
                error = self.refused(lambda: self.bot.post(CONVERSATION, CARD, "x"))
                self.assertEqual((error.step, error.reason, error.maybe_sent, str(error), self.fake.steps()), ("send", "network", False, teamsbot.REASONS["network"], ["token"]))
        for left in (10.0, 24.0):
            with self.subTest(left=left):
                self.bot.client.deadline = 100.0 + left
                self.assertEqual(self.bot.post(CONVERSATION, CARD, "x"), ACTIVITY)
        self.assertEqual(self.fake.steps(), ["token", "send", "send"])

    def test_the_time_that_the_token_took_counts_for_the_post(self):
        now = [100.0]

        def slow(resource, within=None):
            now[0] += 20
            return ASSERTION
        bot = self.make(assertion=slow)
        bot.client.monotonic, bot.client.deadline = (lambda: now[0]), 125.0
        error = self.refused(lambda: bot.post(CONVERSATION, CARD, "x"))
        self.assertEqual((error.maybe_sent, error.reason, self.fake.steps()), (False, "network", ["token"]))

    def test_no_other_step_may_have_put_a_card_in_teams(self):
        self.bot.token()
        for step, reply in (("create", answer(503)), ("create", OSError("lost")), ("create", answer(201, {})), ("update", answer(503)), ("update", OSError("lost")), ("update", answer(200, b"x"))):
            with self.subTest(step=step, reply=str(reply)[:30]):
                self.script(step, *[reply] * 3)
                self.assertFalse(self.refused({"create": lambda: self.bot.create(PERSON), "update": lambda: self.bot.update(CONVERSATION, ACTIVITY, CARD, "x")}[step]).maybe_sent)


class TheTimeOfARound(Case):
    """The client has a deadline for a round (cases/offers.py gives it): `late` says that nothing is started any more, unless a failure of the token is remembered, which is the one answer that every card of the
    round gets at once, so that each card has its try written and none of them stalls the next round again."""

    @staticmethod
    def broken(resource, within=None):
        raise IdentityError("the managed identity endpoint answered 404")

    def test_a_round_whose_time_is_used_up_is_late_and_a_client_without_a_round_never(self):
        self.assertFalse(self.bot.late())
        self.bot.client.monotonic, self.bot.client.deadline = (lambda: 100.0), 125.0
        self.assertFalse(self.bot.late())
        self.bot.client.deadline = 100.0
        self.assertTrue(self.bot.late())

    def test_a_token_that_failed_in_the_round_leaves_every_card_the_same_failure_at_once(self):
        bot = self.make(assertion=self.broken)
        bot.client.monotonic, bot.client.deadline = (lambda: 100.0), 100.0
        self.assertTrue(bot.late())
        first = self.refused(bot.token)
        self.assertFalse(bot.late(), "the card is tried, gets the failure that is remembered and has its try written")
        self.assertIs(self.refused(lambda: bot.send(PERSON, CARD, "x")), first)
        self.assertEqual(self.fake.calls, [])

    def test_a_token_that_was_had_does_not_make_a_round_that_is_used_up_any_less_late(self):
        self.bot.token()
        self.bot.client.monotonic, self.bot.client.deadline = (lambda: 100.0), 100.0
        self.assertTrue(self.bot.late())


FORBIDDEN = {"error": {"code": "ForbiddenOperationException", "message": "Bot is not installed in user's personal scope"}}
ROSTER = {"error": {"code": "BotNotInConversationRoster", "message": "The bot is not part of the conversation roster."}}
BLOCKED_BY_USER = {"error": {"code": "ConversationBlockedByUser", "message": "User blocked the conversation with the bot."}}
WRITES_BLOCKED = {"errorCode": 209, "message": "{\n  \"subCode\": \"MessageWritesBlocked\",\n  \"details\": \"Thread is blocked from message writes.\",\n  \"errorCode\": null\n}"}


class WhatEachFailureMeans(Case):
    TABLE = (
        # (step, status, body, reason): what Teams says, and the one plain word for it
        ("create", 403, FORBIDDEN, "not-installed"), ("send", 403, FORBIDDEN, "not-installed"), ("create", 403, ROSTER, "not-installed"),
        ("send", 403, WRITES_BLOCKED, "blocked"), ("send", 403, BLOCKED_BY_USER, "blocked"), ("create", 403, WRITES_BLOCKED, "blocked"),
        ("create", 401, {"message": "Authorization has been denied for this request."}, "unauthorized"), ("send", 401, None, "unauthorized"),
        ("create", 403, {"error": {"code": "NotEnoughPermissions", "message": "x"}}, "other"), ("send", 403, None, "other"), ("create", 404, None, "other"), ("send", 400, {"error": {"code": "BadArgument"}}, "other"),
        ("update", 404, None, "other"), ("update", 400, {"error": {"code": "BadArgument"}}, "other"), ("update", 403, FORBIDDEN, "not-installed"),
        ("create", 429, None, "throttled"), ("send", 429, None, "throttled"), ("update", 429, None, "throttled"),
        ("create", 500, None, "network"), ("send", 503, None, "network"), ("update", 504, None, "network"),
        ("create", 412, None, "network"), ("send", 412, None, "network"), ("update", 412, None, "network"),
    )

    def run_step(self, step):
        self.bot.token()
        return {"create": lambda: self.bot.create(PERSON), "send": lambda: self.bot.post(CONVERSATION, CARD, "x"), "update": lambda: self.bot.update(CONVERSATION, ACTIVITY, CARD, "x")}[step]

    def test_what_teams_says_is_one_plain_reason_for_the_step_that_it_said_it_to(self):
        for step, status, body, reason in self.TABLE:
            with self.subTest(step=step, status=status, reason=reason):
                self.script(step, *[answer(status, body, retry_after="3600")] * 3)
                error = self.refused(self.run_step(step))
                self.assertEqual((error.step, error.reason, error.status), (step, reason, status))

    def test_the_words_are_plain_and_never_the_answer_of_the_service_a_token_or_an_id(self):
        for step, status, body, reason in self.TABLE:
            with self.subTest(step=step, status=status):
                self.script(step, *[answer(status, body, retry_after="3600")] * 3)
                error = self.refused(self.run_step(step))
                text = str(error)
                self.assertEqual(text, teamsbot.NOT_RETRIED if error.maybe_sent else teamsbot.NOT_REPLACED if (step, reason) == ("update", "other")
                                 else (teamsbot.REPLACE.get(reason) if step == "update" else None) or teamsbot.REASONS[reason])
                for hidden in (ACCESS, ASSERTION, CONVERSATION, PERSON, TENANT, APP, "Authorization", "ForbiddenOperationException", "MessageWritesBlocked", "smba", "http"):
                    self.assertNotIn(hidden, text)

    def test_a_guest_without_the_app_is_told_in_plain_words_that_the_letter_goes_instead(self):
        self.script("create", answer(403, FORBIDDEN))
        self.assertEqual(str(self.refused(self.run_step("create"))), "The Teams app is not installed for this person, so no card could be sent: the e-mail letter goes instead.")
        self.assertIn("e-mail letter goes instead", teamsbot.REASONS["blocked"])

    def test_the_reasons_have_a_sentence_each_that_the_operations_page_can_read_back(self):
        self.assertEqual(sorted(teamsbot.REASONS), ["blocked", "network", "not-installed", "other", "throttled", "unauthorized"])
        self.assertEqual({teamsbot.REASON_OF[text] for text in teamsbot.REASONS.values()}, set(teamsbot.REASONS))
        self.assertEqual(teamsbot.REASON_OF[teamsbot.NOT_REPLACED], "other")
        self.assertEqual({teamsbot.REASON_OF[text] for text in teamsbot.REPLACE.values()}, {"not-installed", "blocked"})
        self.assertEqual(teamsbot.REASON_OF[teamsbot.NOT_RETRIED], "network")
        self.assertTrue(all(len(text) < 240 for text in (*teamsbot.REASONS.values(), *teamsbot.REPLACE.values(), teamsbot.NOT_REPLACED, teamsbot.NOT_RETRIED)), "a record keeps at most 240 characters of a detail")

    def test_a_card_that_cannot_be_replaced_does_not_promise_a_letter_which_belongs_to_a_card_that_could_not_be_sent(self):
        for reason, body in (("not-installed", FORBIDDEN), ("blocked", WRITES_BLOCKED)):
            with self.subTest(reason=reason):
                self.script("update", answer(403, body))
                text = str(self.refused(self.run_step("update")))
                self.assertEqual((text, teamsbot.REASON_OF[text]), (teamsbot.REPLACE[reason], reason))
                self.assertNotIn("letter", text)
                self.assertNotIn("could be sent", text)

    def test_a_call_that_the_list_refuses_is_a_refusal_and_not_a_crash(self):
        way = TeamsWay("bot", "", APP, IDENTITY, TENANT, "https://smba.infra.gcc.teams.microsoft.com/teams/")
        client = teamsbot.new_client(way, Redactor(), transport=self.fake, sleep=lambda seconds: None)
        bot = teamsbot.TeamsBot(WAY, lambda resource: ASSERTION, client, self.clock)
        error = self.refused(lambda: bot.create(PERSON))
        self.assertEqual((error.step, error.reason, str(error)), ("create", "other", teamsbot.REASONS["other"]))
        self.assertEqual(self.fake.steps(), ["token"], "the address of the service is not on this list: only the token was asked for")


class TheListOfCallsIsExact(Case):
    PASS = (
        ("POST", TOKEN_URL), ("POST", CREATE_URL), ("POST", POST_URL), ("PUT", UPDATE_URL), ("POST", f"{CREATE_URL}/19:abc-def_9@unq.gbl.spaces/activities"),
        ("PUT", f"{CREATE_URL}/a:1x/activities/f:1a2b3c"), ("PUT", f"{CREATE_URL}/{'a' * 200}/activities/{'1' * 200}"), ("POST", f"{CREATE_URL}/a..b/activities"),
    )
    FAIL = (
        # the scheme and the host
        ("POST", CREATE_URL.replace("https:", "http:")), ("POST", TOKEN_URL.replace("https:", "http:")), ("PUT", UPDATE_URL.replace("https:", "http:")), ("POST", "ftp://smba.trafficmanager.net/teams/v3/conversations"),
        ("POST", "https://evil.example/teams/v3/conversations"), ("POST", "https://smba.trafficmanager.net.evil.example/teams/v3/conversations"), ("POST", "https://evil.smba.trafficmanager.net/teams/v3/conversations"),
        ("POST", "https://smba.trafficmanager.net@evil.example/teams/v3/conversations"), ("POST", "https://evil.example@smba.trafficmanager.net/teams/v3/conversations"),
        ("POST", "https://evil.example/https://smba.trafficmanager.net/teams/v3/conversations"), ("POST", "https://SMBA.trafficmanager.net/teams/v3/conversations"),
        ("POST", "https://smba.trafficmanager.net:443/teams/v3/conversations"), ("POST", "https://smba.trafficmanager.net:8080/teams/v3/conversations"), ("POST", "https://login.microsoftonline.com/teams/v3/conversations"),
        ("POST", "https://smba.trafficmanager.net/oauth2/v2.0/token"), ("POST", "https://login.microsoftonline.com/common/oauth2/v2.0/token"),
        ("POST", f"https://login.microsoftonline.com/{TENANT.replace('1', '2')}/oauth2/v2.0/token"), ("POST", f"https://login.microsoftonline.com/{TENANT}/oauth2/token"),
        ("POST", f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"), ("POST", "https://graph.microsoft.com/v1.0/users"),
        # the path
        ("POST", f"{SERVICE}v3/conversations/"), ("POST", f"{SERVICE}v3/conversations//activities"), ("POST", f"{SERVICE}v3/conversations/activities"), ("POST", f"{CREATE_URL}/{CONVERSATION}"),
        ("POST", f"{CREATE_URL}/{CONVERSATION}/members"), ("POST", f"{POST_URL}/"), ("PUT", f"{UPDATE_URL}/"), ("PUT", f"{UPDATE_URL}/x"), ("POST", "https://smba.trafficmanager.net/emea/v3/conversations"),
        ("POST", "https://smba.trafficmanager.net/v3/conversations"), ("POST", "https://smba.trafficmanager.net/teams/v2/conversations"), ("POST", "https://smba.trafficmanager.net/teams/v3/conversation"),
        ("POST", "https://smba.trafficmanager.net/teams/v3/conversationsx"), ("POST", "https://smba.trafficmanager.net/teams/v3/Conversations"),
        # path tricks
        ("POST", f"{CREATE_URL}/..%2f..%2fv3/conversations"), ("POST", f"{CREATE_URL}/%2e%2e/activities"), ("POST", f"{CREATE_URL}/../activities"), ("POST", f"{CREATE_URL}/./activities"),
        ("PUT", f"{POST_URL}/.."), ("PUT", f"{POST_URL}/."), ("PUT", f"{POST_URL}/..."), ("PUT", f"{CREATE_URL}/{CONVERSATION}/activities/..%2fx"), ("POST", f"{CREATE_URL}/a%2fb/activities"),
        ("POST", f"{CREATE_URL}/a;b/activities"), ("POST", f"{CREATE_URL}/a\\b/activities"), ("POST", f"{CREATE_URL}/a b/activities"), ("POST", f"{CREATE_URL}/a\tb/activities"), ("POST", f"{CREATE_URL}/a\nb/activities"),
        ("POST", f"{CREATE_URL}/{'a' * 201}/activities"), ("POST", f"{CREATE_URL}/a\u00e9/activities"), ("POST", f"{CREATE_URL}/x@evil.example/activities/..//"), ("POST", "https://smba.trafficmanager.net/teams/../teams/v3/conversations"),
        # a query, a fragment, an encoding
        ("POST", f"{CREATE_URL}?x=1"), ("POST", f"{CREATE_URL}?"), ("POST", f"{CREATE_URL}#x"), ("POST", f"{POST_URL}?api-version=1"), ("PUT", f"{UPDATE_URL}?x"), ("POST", f"{TOKEN_URL}?x=1"),
        ("POST", f"{CREATE_URL}%3fx=1"), ("POST", f"{CREATE_URL}%00"), ("POST", ""), ("POST", "/teams/v3/conversations"), ("POST", "smba.trafficmanager.net/teams/v3/conversations"),
        # a different method
        ("GET", TOKEN_URL), ("GET", CREATE_URL), ("GET", POST_URL), ("GET", UPDATE_URL), ("DELETE", UPDATE_URL), ("DELETE", CREATE_URL), ("PATCH", UPDATE_URL), ("PUT", CREATE_URL), ("PUT", POST_URL),
        ("PUT", TOKEN_URL), ("POST", UPDATE_URL), ("HEAD", CREATE_URL), ("post", CREATE_URL), ("OPTIONS", POST_URL),
    )

    def test_exactly_the_four_calls_pass(self):
        client = teamsbot.new_client(WAY, Redactor(), transport=self.fake)
        for method, url in self.PASS:
            with self.subTest(method=method, url=url[:90]):
                client.check(method, url)
        self.assertEqual(len(teamsbot.bot_calls(WAY)), 4)

    def test_nothing_else_passes_and_the_transport_is_not_reached(self):
        client = teamsbot.new_client(WAY, Redactor(), transport=self.fake)
        for method, url in self.FAIL:
            with self.subTest(method=method, url=url[:90]), self.assertRaises(Refused):
                client.check(method, url)
            with self.subTest(sent=method, url=url[:90]), self.assertRaises(Refused):
                client.request(method, url)
        self.assertEqual(self.fake.calls, [])

    def test_the_list_of_the_whole_app_is_not_widened_and_this_client_is_not_the_one_of_the_watch(self):
        self.assertFalse([1 for method, pattern in http.allowed_calls() if pattern.fullmatch(CREATE_URL) or pattern.fullmatch(TOKEN_URL)], "the client of the Watch cannot reach Teams or the token endpoint")
        self.assertEqual(sorted({"smba.trafficmanager.net", "login.microsoftonline.com"}), sorted({url.split("/")[2] for _, url in self.PASS}))

    def test_a_service_url_that_was_changed_adds_its_own_host_and_removes_the_default(self):
        way = TeamsWay("bot", "", APP, IDENTITY, TENANT, "https://smba.infra.gcc.teams.microsoft.com/teams/")
        client = teamsbot.new_client(way, Redactor(), transport=self.fake)
        client.check("POST", "https://smba.infra.gcc.teams.microsoft.com/teams/v3/conversations")
        client.check("PUT", f"https://smba.infra.gcc.teams.microsoft.com/teams/v3/conversations/{CONVERSATION}/activities/{ACTIVITY}")
        client.check("POST", TOKEN_URL)
        for method, url in (("POST", CREATE_URL), ("POST", "https://smba.infra.gcc.teams.microsoft.com/amer/v3/conversations"), ("POST", "https://smba.infra.gcc.teams.microsoft.com.evil.example/teams/v3/conversations")):
            with self.subTest(url=url), self.assertRaises(Refused):
                client.check(method, url)

    def test_the_real_transport_reads_at_most_a_small_answer_and_a_fake_one_is_left_as_it_is(self):
        client = teamsbot.new_client(WAY, Redactor())
        self.assertEqual((client.transport.func, client.transport.keywords), (http.default_transport, {"limit": teamsbot.MAX_ANSWER}))
        self.assertIs(teamsbot.new_client(WAY, Redactor(), transport=self.fake).transport, self.fake)
        reads = []

        class Opened:
            status, headers = 200, {"X-A": "b"}

            def __enter__(self):
                return self

            def __exit__(self, *details):
                return False

            def read(self, limit=None):
                reads.append(limit)
                return b"x" * (limit or 10)
        with mock.patch.object(http._OPENER, "open", return_value=Opened()):
            self.assertEqual(client.transport("POST", CREATE_URL, {}, b"{}", 5)[2], b"x" * teamsbot.MAX_ANSWER)
            self.assertEqual(http.default_transport("GET", CREATE_URL, {}, None, 5)[2], b"x" * 10, "without a limit the whole answer is read, as it always was")
        self.assertEqual(reads, [teamsbot.MAX_ANSWER, None])

    def test_no_redirect_is_followed_so_the_token_cannot_be_sent_to_another_address(self):
        self.assertIs(http._NoRedirect.redirect_request(None, None, None, 307, "", {}, "https://evil.example/"), None)


class TheCardsOfTheTest(unittest.TestCase):
    def test_the_test_card_says_that_it_is_a_test_and_holds_nothing_of_the_estate_and_the_closing_card_replaces_it(self):
        first, closing = cards.probe_card(), cards.probe_card(True, contacts=("Maya (maya@example.com)",))
        self.assertIn("Test card from Meternaut: nothing to do.", cs.texts(first))
        self.assertIn("Test card from Meternaut: closed, nothing to do.", cs.texts(closing))
        for card in (first, closing):
            self.assertEqual(cards.cardcheck.check(card), [])
            self.assertNotIn("Action.", json.dumps(card), "no button: there is nothing to open")
            self.assertIn("Meternaut (AI)", cs.texts(card))
            self.assertIn("Written by an AI", " ".join(cs.texts(card)))
        self.assertNotIn("Responsible for Meternaut", json.dumps(first))
        self.assertIn("Responsible for Meternaut: Maya (maya@example.com).", json.dumps(closing))
        self.assertRegex(cards.SUMMARIES["test"], r"^\[Meternaut\] [^0-9]+$")


if __name__ == "__main__":
    unittest.main()
