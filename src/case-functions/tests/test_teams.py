"""The Teams bot (cases/teams.py): the settings, the endpoint with its token check, the answer on a card, and what the bot does with a message and with the installation of the app.

The token that Teams sends is made with the invented key of test_botauth.py and checked by the real verifier; the stores are in memory and the Connector is a fake. What these tests hold
is the design: a call that is not let in gets an empty 401 or 403 and touches nothing; an answer on a card goes through the page's decider for the person who tapped, and a forged call can at
most record a low-stakes answer for a listed person who knows a plan, its code and a live one-time token; no card ever approves a change in Azure.
"""
import json
import time
import unittest

import support  # noqa: F401  (puts the app on the path)
import teamssupport as ts
import test_botauth as ba
from cases import cardcheck, teams
from cases.botauth import BotAuthenticator, KeyStore
from cases.models import SwitchRecord
from cases.people import PeopleError
from cases.references import made
from test_store import ACCOUNT, FakeTables

PEOPLE = [{"oid": ts.MAYA, "name": "Maya", "roles": ["owner", "approver", "ops"], "mail": "maya@example.com"},
          {"oid": ts.ANNA, "name": "Anna", "roles": ["approver"], "mail": "anna@example.com"}]


def env(**changes) -> dict:
    values = {"TEAMS_BOT_APP_ID": ts.APP_ID, "TEAMS_TENANT_ID": ts.TENANT, "STORE_ACCOUNT_NAME": ACCOUNT, "CHANGE_SCOPES": f"{ts.SUBSCRIPTION}/{ts.GROUP}",
              "CONSOLE_HOST": "meternaut.example", "CONSOLE_PEOPLE": json.dumps(PEOPLE), "IDENTITY_ENDPOINT": "http://127.0.0.1:8081/msi/token", "IDENTITY_HEADER": "header-value",
              "AZURE_CLIENT_ID": "99999999-8888-7777-6666-555555555555"}
    values.update(changes)
    return {key: value for key, value in values.items() if value is not None}


def executes(card: dict) -> list[dict]:
    found = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "Action.Execute":
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(card)
    return found


def nonce_of(card: dict) -> str:
    (nonces,) = {execute["data"]["nonce"] for execute in executes(card)}
    return nonces


class TheSettings(unittest.TestCase):
    def test_a_bot_that_is_not_set_up_is_none(self):
        self.assertIsNone(teams.load({}))
        self.assertIsNone(teams.load({"STORE_ACCOUNT_NAME": ACCOUNT}))

    def test_the_settings_are_read_in_lower_case(self):
        settings = teams.load(env(TEAMS_BOT_APP_ID=ts.APP_ID.upper(), TEAMS_TENANT_ID=ts.TENANT.upper()))
        self.assertEqual((settings.app_id, settings.tenant_id, settings.loop.store_account), (ts.APP_ID, ts.TENANT, ACCOUNT))

    def test_a_half_set_up_bot_says_what_is_missing(self):
        for changes, words in (({"TEAMS_TENANT_ID": None}, "TEAMS_TENANT_ID"), ({"TEAMS_BOT_APP_ID": None}, "TEAMS_BOT_APP_ID"), ({"TEAMS_BOT_APP_ID": "not-a-guid"}, "TEAMS_BOT_APP_ID"),
                               ({"STORE_ACCOUNT_NAME": None}, "the loop is not configured"), ({"CHANGE_SCOPES": "x"}, "CHANGE_SCOPES")):
            with self.assertRaises(teams.TeamsConfigError, msg=changes) as caught:
                teams.load(env(**changes))
            self.assertIn(words, str(caught.exception))

    def test_a_bot_without_people_does_not_start(self):
        with self.assertRaises(PeopleError):
            teams.build_services(env(CONSOLE_PEOPLE=None))


class TheServices(unittest.TestCase):
    def test_the_tables_use_the_system_identity_and_the_connector_the_bot_identity(self):
        fetched = []

        def fetch(url, headers, timeout):
            fetched.append(url)
            return 200, json.dumps({"access_token": "t0ken-for-the-test-0123456789", "expires_on": str(int(time.time()) + 3600)}).encode()
        tables = FakeTables()
        built = teams.build_services(env(), transport=tables.transport, fetch=fetch, keys_fetch=ba.Documents(), clock=ts.Moving(), sleep=lambda seconds: None)
        built.connector.token("https://api.botframework.com")
        built.store.token("https://storage.azure.com/")
        built.references.token("https://storage.azure.com/")
        self.assertEqual(len(fetched), 2, "the store and the references share the one token of the system identity")
        self.assertIn(f"client_id={ts.APP_ID}", fetched[0])
        self.assertIn("resource=https%3A%2F%2Fapi.botframework.com", fetched[0])
        self.assertNotIn("client_id", fetched[1], "the tables are read as the app's own system-assigned identity, whatever AZURE_CLIENT_ID says")

    def test_the_stores_and_the_decider_are_the_ones_of_the_loop(self):
        tables = FakeTables()
        built = teams.build_services(env(), transport=tables.transport, fetch=lambda url, headers, timeout: (200, b'{"access_token":"t0ken-for-the-test-0123456789","expires_on":"9999999999"}'),
                                     keys_fetch=ba.Documents(), clock=ts.Moving(), sleep=lambda seconds: None)
        self.assertEqual(built.store.account, ACCOUNT)
        self.assertEqual(tuple((s.subscription, s.group) for s in built.approvals.settings.change_scopes), ((ts.SUBSCRIPTION, ts.GROUP),))
        built.references.reference_get(ts.MAYA)
        built.store.plan_get("x")
        self.assertEqual({method for method, url in tables.calls}, {"GET"})

    def test_none_when_the_bot_is_not_set_up(self):
        self.assertIsNone(teams.build_services({}))


class TheEndpoint(unittest.TestCase):
    """A call that is not let in gets an empty 401 or 403, and nothing is read or written for it."""

    def setUp(self):
        self.world = ts.World()
        self.world.open_plan()

    def untouched(self):
        self.assertEqual(self.world.connector_fake.calls, [])
        self.assertEqual((self.world.store.decisions, self.world.store.mails, self.world.references.rows), ({}, [], {}))

    def refused(self, reply, status):
        self.assertEqual((reply.status_code, reply.body), (status, b""))
        self.untouched()

    def test_a_call_with_a_good_token_is_let_in(self):
        reply = self.world.call(ts.activity("typing"))
        self.assertEqual((reply.status_code, reply.body), (200, b""))

    def test_no_token_is_a_401_with_an_empty_body(self):
        for header in ("", "Bearer", "Bearer ", "Basic abc", "bearer x.y", "Bearer a.b.c", f"Bearer {ba.token()} extra"):
            self.refused(self.world.call(ts.activity("typing"), authorization=header), 401)

    def test_a_token_that_is_wrong_is_a_401(self):
        for kwargs in ({"payload": {"aud": "99999999-0000-0000-0000-000000000000"}}, {"payload": {"iss": "https://sts.windows.net/x/"}}, {"payload": {"exp": ba.NOW - 3600}},
                       {"payload": {"serviceurl": "https://smba.trafficmanager.net/amer/"}}, {"header": {"alg": "none"}}, {"header": {"alg": "HS256"}}, {"header": {"kid": "unknown-key"}},
                       {"signature": b"\x01" * ba.K}):
            self.refused(self.world.call(ts.activity("typing"), token_kwargs=kwargs), 401)

    def test_a_key_that_is_not_endorsed_for_teams_is_a_403(self):
        self.world.services.authenticator = BotAuthenticator(ts.APP_ID, KeyStore(ba.Documents(keys={"keys": [ba.jwk(endorsements=("skype",))]}), self.world.key_clock), self.world.key_clock)
        self.refused(self.world.call(ts.activity("typing")), 403)

    def test_only_a_post_with_a_small_json_object_is_looked_at(self):
        self.refused(self.world.call(ts.activity("typing"), method="GET"), 405)
        self.refused(self.world.call(ts.activity("typing"), body=b"{" + b" " * 70000 + b"}"), 413)
        for body in (b"", b"not json", b"[]", b'"text"', b"123", b"null", b"\xff\xfe"):
            self.refused(self.world.call(ts.activity("typing"), body=body), 401)

    def test_a_bot_that_is_not_set_up_answers_503(self):
        reply = teams.handle(ts.Req(b"{}", {}), ts.Resp, env={})
        self.assertEqual((reply.status_code, reply.body), (503, b""))

    def test_the_tenant_the_recipient_and_the_address_have_to_be_the_ones_of_the_bot(self):
        other = "https://smba.trafficmanager.net/amer/"
        for what, activity, kwargs in (("tenant", ts.activity("typing", tenant="bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee"), {}),
                                       ("recipient", ts.activity("typing", recipient={"id": "28:99999999-0000-0000-0000-000000000000"}), {}),
                                       ("channelData", ts.activity("typing", channelData="tenant"), {}),
                                       ("address", ts.activity("typing", service="https://evil.example/emea/"), {"payload": {"serviceurl": "https://evil.example/emea/"}}),
                                       ("no conversation", ts.activity("typing", conversation=""), {})):
            reply = self.world.call(activity, token_kwargs=kwargs)
            self.assertEqual((reply.status_code, reply.body), (400, b""), what)
        self.assertEqual(self.world.call(ts.activity("typing", service=other), token_kwargs={"payload": {"serviceurl": other}}).status_code, 200, "another region is fine")
        self.assertEqual(self.world.connector_fake.calls, [])

    def test_what_teams_sends_that_the_bot_does_not_use_is_taken_and_ignored(self):
        for kind in ("typing", "endOfConversation", "event", "messageReaction", "contactRelationUpdate", "somethingNew"):
            reply = self.world.call(ts.activity(kind))
            self.assertEqual((reply.status_code, reply.body), (200, b""), kind)
        reply = self.world.call(ts.activity("invoke", name="composeExtension/query", value={}))
        self.assertEqual((reply.status_code, reply.body), (501, b""))
        self.untouched()

    def test_the_log_says_why_in_one_word_and_holds_no_token(self):
        good = f"Bearer {ba.token()}"
        with support.LogCapture() as capture:
            self.world.call(ts.activity("typing"), token_kwargs={"signature": b"\x01" * ba.K})
            self.world.call(ts.activity("message"), authorization=good)
        text = "\n".join(capture.messages())
        self.assertIn("not let in (signature)", text)
        self.assertNotIn(good.split(" ", 1)[1], text)
        self.assertNotIn(ts.BOT_TOKEN, text)


class TheAnswersOnACard(unittest.TestCase):
    def setUp(self):
        self.world = ts.World()
        self.store = self.world.store

    def decisions(self, plan_id=ts.PLAN_ID):
        return self.store.decisions_of_plan(plan_id)

    def message(self, body, words):
        self.assertEqual(body["type"], "application/vnd.microsoft.activity.message", body)
        self.assertIn(words, body["value"])

    def test_later_keeps_the_request_open_and_replaces_the_card_with_one_that_has_a_new_token(self):
        self.world.open_plan()
        old = self.world.nonce()
        body = self.world.answer("later", nonce=old)
        card = ts.card_of(body)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual([d.decision for d in self.decisions()], ["later"])
        self.assertEqual(self.store.plan_get(ts.PLAN_ID).state, "open")
        self.assertEqual(card["body"][2]["text"], "Noted. Nothing is approved. The request stays open, in your list.")
        fresh = nonce_of(card)
        self.assertNotEqual(fresh, old)
        self.assertIsNone(self.store.nonce_take(old, ts.MAYA, ts.PLAN_ID), "the token of the card that was tapped is used up")
        self.assertIsNotNone(self.store.nonce_take(fresh, ts.MAYA, ts.PLAN_ID), "the new card holds a live token, made for this person and this request")
        self.assertEqual(self.world.connector_fake.calls, [])

    def test_a_question_is_recorded_with_its_words_and_approves_nothing(self):
        self.world.open_plan()
        card = ts.card_of(self.world.answer("ask", data={"message": "  Is this the disk of the test team?  "}))
        (decision,) = self.decisions()
        self.assertEqual((decision.decision, decision.note, decision.approver_oid), ("ask", "Is this the disk of the test team?", ts.MAYA))
        self.assertEqual(self.store.plan_get(ts.PLAN_ID).state, "open")
        self.assertIn("Recorded with your name. It approves nothing.", "\n".join(ts.texts(card)))
        self.assertTrue(executes(card), "the request is open: the new card carries its answers again")

    def test_a_question_without_words_or_with_too_many_is_not_taken_and_uses_no_token(self):
        self.world.open_plan()
        nonce = self.world.nonce()
        for text in (None, "", "   ", 7, ["x"], "x" * 301):
            body = self.world.answer("ask", nonce=nonce, data={} if text is None else {"message": text})
            self.message(body, "Nothing was recorded.")
        self.assertEqual(self.decisions(), [])
        self.assertIsNotNone(self.store.nonce_take(nonce, ts.MAYA, ts.PLAN_ID))

    def test_the_words_of_a_question_are_cleaned_by_the_decider(self):
        self.world.open_plan()
        self.world.answer("ask", data={"message": "a\x00b\u202ec  d"})
        (decision,) = self.decisions()
        self.assertTrue(all(ch.isprintable() or ch == " " for ch in decision.note), repr(decision.note))

    def test_not_worth_it_closes_advice_and_the_card_shows_what_became_of_it_without_a_token(self):
        self.world.open_plan()
        card = ts.card_of(self.world.answer("decline"))
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(self.store.plan_get(ts.PLAN_ID).state, "declined")
        self.assertEqual(self.store.case_get("c1").status, "declined")
        self.assertEqual(executes(card), [])
        self.assertNotIn("nonce", json.dumps(card))
        self.assertIn("Declined. Nothing has changed.", "\n".join(ts.texts(card)))

    def test_worth_acting_on_is_the_answer_of_advice_and_changes_nothing_in_azure(self):
        self.world.open_plan()
        card = ts.card_of(self.world.answer("approve"))
        (decision,) = self.decisions()
        self.assertEqual(decision.decision, "approve")
        self.assertEqual((self.store.plan_get(ts.PLAN_ID).state, self.store.case_get("c1").status), ("consumed", "acknowledged"))
        self.assertIsNone(self.store.action_get(ts.PLAN_ID), "no action is queued: advice changes nothing in Azure")
        self.assertIn("Nothing was changed in Azure.", "\n".join(ts.texts(card)))

    def test_not_mine_withdraws_the_request(self):
        self.world.open_plan()
        card = ts.card_of(self.world.answer("not_mine"))
        self.assertEqual((self.store.plan_get(ts.PLAN_ID).state, self.store.case_get("c1").status), ("withdrawn", "needs_human"))
        self.assertEqual(executes(card), [])

    def test_the_answers_work_for_a_change_too_but_the_approval_of_a_change_never_comes_from_a_card(self):
        self.world.open_plan(ts.change_plan())
        card = ts.card_of(self.world.answer("later"))
        self.assertEqual({e["verb"] for e in executes(card)}, {"not_mine", "later", "ask"}, "a card of a change has no answer that approves or declines it")
        for nonce in (self.world.nonce(), card and nonce_of(card)):
            self.message(self.world.answer("approve", nonce=nonce), "An approval of a change is made on the page")
        plan = self.store.plan_get(ts.PLAN_ID)
        self.assertEqual(plan.state, "open")
        self.assertEqual([d.decision for d in self.decisions()], ["later"])
        self.assertIsNone(self.store.action_get(ts.PLAN_ID))
        self.assertIsNotNone(self.store.nonce_take(nonce_of(card), ts.MAYA, ts.PLAN_ID), "a refused answer uses no token")

    def test_a_token_works_once(self):
        self.world.open_plan()
        nonce = self.world.nonce()
        self.world.answer("later", nonce=nonce)
        again = self.world.answer("later", nonce=nonce)
        self.message(again, "no longer valid")
        self.assertEqual(len(self.decisions()), 1)

    def test_a_token_that_ran_out_is_refused(self):
        self.world.open_plan()
        nonce = self.world.nonce(seconds=60)
        self.world.clock.advance(minutes=5)
        self.message(self.world.answer("later", nonce=nonce), "no longer valid")
        self.assertEqual(self.decisions(), [])

    def test_a_token_made_for_somebody_else_or_for_another_request_is_refused_and_not_used_up(self):
        self.world.open_plan()
        self.world.open_plan(ts.advice_plan("p2other", case_id="c2"))
        annas = self.world.nonce(ts.ANNA)
        self.message(self.world.answer("later", nonce=annas), "no longer valid")
        other = self.world.nonce(ts.MAYA, "p2other")
        self.message(self.world.answer("later", nonce=other), "no longer valid")
        self.assertEqual(self.decisions() + self.decisions("p2other"), [])
        self.assertIsNotNone(self.store.nonce_take(annas, ts.ANNA, ts.PLAN_ID))
        self.assertIsNotNone(self.store.nonce_take(other, ts.MAYA, "p2other"))

    def test_a_forged_nonce_records_nothing(self):
        self.world.open_plan()
        for nonce in ("A" * 32, "0123456789abcdefghijABCDEFGHIJ-_", "x" * 20):
            self.message(self.world.answer("later", nonce=nonce), "no longer valid")
        self.assertEqual(self.decisions(), [])

    def test_a_plan_code_that_is_not_the_plans_is_refused_and_uses_no_token(self):
        self.world.open_plan()
        nonce = self.world.nonce()
        self.message(self.world.answer("later", nonce=nonce, code="WRONG123"), "This plan changed")
        self.assertEqual(self.decisions(), [])
        self.assertIsNotNone(self.store.nonce_take(nonce, ts.MAYA, ts.PLAN_ID))

    def test_the_tapper_is_the_person_of_the_activity_and_nobody_else(self):
        self.world.open_plan()
        data = {"oid": ts.ANNA, "aadObjectId": ts.ANNA, "approver": ts.ANNA, "from": {"aadObjectId": ts.ANNA}, "principal": ts.ANNA}
        self.world.answer("later", data=data)
        (decision,) = self.decisions()
        self.assertEqual((decision.approver_oid, decision.approver_name), (ts.MAYA, "Maya"))

    def test_a_stray_text_is_not_a_note_unless_the_answer_is_a_question(self):
        self.world.open_plan()
        self.world.answer("later", data={"message": "this is not a question"})
        self.assertEqual(self.decisions()[0].note, "")

    def test_somebody_who_is_not_on_the_list_is_refused_in_plain_words(self):
        self.world.open_plan()
        nonce = self.world.nonce(ts.STRANGER)
        self.message(self.world.answer("later", nonce=nonce, oid=ts.STRANGER), "not on my list of people")
        self.assertEqual(self.decisions(), [])
        self.assertIsNotNone(self.store.nonce_take(nonce, ts.STRANGER, ts.PLAN_ID))

    def test_somebody_who_is_listed_but_not_named_on_the_request_or_may_not_answer_is_refused(self):
        self.world.open_plan(ts.advice_plan(approvers=(ts.MAYA, ts.OMAR)))
        self.world.channel(ts.ANNA)
        self.message(self.world.answer("later", oid=ts.ANNA), "I cannot take your OK on this request")
        self.message(self.world.answer("later", oid=ts.OMAR), "I cannot take your OK on this request")
        self.assertEqual(self.decisions(), [])

    def test_a_request_that_does_not_exist_is_not_found_for_an_approver_and_refused_for_the_rest(self):
        self.message(self.world.answer("later", plan_id="nosuchplan"), "I cannot find this request")
        self.assertEqual(self.store.decisions, {})

    def test_a_request_that_expired_shows_what_became_of_it(self):
        self.world.open_plan()
        nonce = self.world.nonce(seconds=10 * 86400)
        self.world.clock.advance(days=4)
        card = ts.card_of(self.world.answer("later", nonce=nonce))
        self.assertEqual(self.store.plan_get(ts.PLAN_ID).state, "expired")
        self.assertEqual(executes(card), [])
        self.assertIn("expired", "\n".join(ts.texts(card)).lower())
        self.assertEqual(self.decisions(), [])

    def test_a_request_that_was_answered_already_is_shown_as_it_is_now(self):
        self.world.open_plan()
        first = ts.card_of(self.world.answer("decline"))
        self.assertEqual(executes(first), [])
        card = ts.card_of(self.world.answer("later", oid=ts.ANNA))
        self.assertEqual(executes(card), [], "a request that is closed carries no answer and no token")
        self.assertEqual(len(self.decisions()), 1)

    def test_a_switch_that_holds_the_answer_is_said_on_the_card_and_in_the_refusal(self):
        self.world.open_plan()
        self.store.switch_put(SwitchRecord(name="all", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.message(self.world.answer("approve"), "paused")
        card = ts.card_of(self.world.answer("later"))
        self.assertEqual([d.decision for d in self.decisions()], ["later"], "the answers that approve nothing still work")
        self.assertNotIn("approve", {e["verb"] for e in executes(card)})
        self.assertIn("Meternaut is paused here.", "\n".join(ts.texts(card)))

    def test_data_that_is_not_what_a_card_sends_is_not_read_and_records_nothing(self):
        self.world.open_plan()
        good = {"requestId": ts.PLAN_ID, "planCode": ts.CODE, "nonce": self.world.nonce()}
        shapes = [{"verb": "Approve"}, {"verb": " later"}, {"verb": "later\n"}, {"verb": "delete"}, {"verb": 5}, {"verb": None}, {"data": []}, {"data": "x"}, {"data": {}},
                  {"data": {**good, "requestId": "p1'; drop"}}, {"data": {**good, "requestId": "../x"}}, {"data": {**good, "requestId": ""}}, {"data": {**good, "requestId": ["a"]}},
                  {"data": {**good, "planCode": "a b"}}, {"data": {**good, "planCode": 7}}, {"data": {**good, "nonce": "short"}}, {"data": {**good, "nonce": "x" * 65}},
                  {"data": {**good, "nonce": None}}]
        for shape in shapes:
            action = {"type": "Action.Execute", "verb": "later", "data": good, **shape}
            reply = self.world.call(ts.activity("invoke", name="adaptiveCard/action", value={"action": action}))
            self.assertEqual(reply.status_code, 200)
            self.message(reply.json(), "Nothing was recorded.")
        for value in (None, "x", [], {"action": None}, {"action": "later"}, {"action": []}, {}):
            reply = self.world.call(ts.activity("invoke", name="adaptiveCard/action", value=value))
            self.message(reply.json(), "Nothing was recorded.")
        self.assertEqual(self.decisions(), [])
        self.assertIsNotNone(self.store.nonce_take(good["nonce"], ts.MAYA, ts.PLAN_ID))

    def test_a_call_that_has_a_valid_token_of_the_connector_but_no_nonce_cannot_record_anything(self):
        """The bound of a forged call: the attacker holds a valid token of the Connector and knows a person and a request. Without a live one-time token, made for that person and that
        request, nothing is recorded, and nothing that changes Azure is ever possible."""
        self.world.open_plan()
        self.world.open_plan(ts.change_plan("p3change", case_id="c3"))
        for plan_id in (ts.PLAN_ID, "p3change"):
            for verb in ("approve", "decline", "not_mine", "later", "ask"):
                for nonce in (None, "", "A" * 32):
                    data = {"requestId": plan_id, "planCode": ts.CODE, **({} if nonce is None else {"nonce": nonce}), "message": "forged"}
                    reply = self.world.call(ts.invoke(verb, data))
                    self.assertEqual(reply.json()["type"], "application/vnd.microsoft.activity.message")
        self.assertEqual((self.store.decisions, self.store.actions), ({}, {}))
        self.assertEqual({self.store.plan_get(p).state for p in (ts.PLAN_ID, "p3change")}, {"open"})

    def test_the_decider_that_fails_is_a_line_and_not_a_crash(self):
        self.world.open_plan()

        class Broken:
            def decide(self, *args, **kwargs):
                raise RuntimeError("the decider broke")
        self.world.services.approvals = Broken()
        self.message(self.world.answer("later"), "I could not take your answer")

    def test_a_store_that_cannot_be_read_is_said_and_records_nothing(self):
        from cases.models import StoreError

        class Down(type(self.store)):
            def plan_get(self, plan_id):
                raise StoreError("down")
        down = Down(self.world.clock)
        self.world.services.store = down
        self.message(self.world.answer("later", nonce="A" * 32), "I cannot reach my records")

    def test_a_card_that_cannot_be_made_after_an_answer_still_tells_what_was_recorded(self):
        self.world.open_plan()
        original = teams._card_after

        def broken(*args, **kwargs):
            raise RuntimeError("no card")
        teams._card_after = broken
        try:
            body = self.world.answer("later")
        finally:
            teams._card_after = original
        self.message(body, "Noted.")
        self.assertEqual([d.decision for d in self.decisions()], ["later"])


class TheEvents(unittest.TestCase):
    def setUp(self):
        self.world = ts.World()
        self.fake = self.world.connector_fake

    def test_a_message_from_a_listed_person_keeps_the_conversation_and_gets_one_plain_line(self):
        reply = self.world.call(ts.activity("message", text="hello"))
        self.assertEqual((reply.status_code, reply.body), (200, b""))
        reference = self.world.references.reference_get(ts.MAYA)
        self.assertEqual((reference.conversation_id, reference.service_url, reference.user_id, reference.tenant_id), (ts.CONVERSATION, ts.SERVICE, "29:1abc-teams-user-id", ts.TENANT))
        (call,) = self.fake.sent()
        self.assertEqual(call["url"], f"{ts.SERVICE}v3/conversations/{ts.CONVERSATION}/activities")
        body = call["body"]
        self.assertEqual((body["type"], body["textFormat"]), ("message", "plain"))
        self.assertNotIn("attachments", body)
        self.assertTrue(body["text"].startswith("I am Meternaut, an AI") and body["text"].endswith("Written by an AI."), body["text"])
        self.assertIn("I do not chat here", body["text"])
        self.assertIn("https://meternaut.example/", body["text"])

    def test_a_message_from_somebody_who_is_not_listed_gets_a_refusal_and_is_not_kept(self):
        self.world.call(ts.activity("message", text="hello", oid=ts.STRANGER))
        (call,) = self.fake.sent()
        self.assertIn("not on my list of people", call["body"]["text"])
        self.assertNotIn("@", call["body"]["text"], "no address of anybody goes to somebody who is not listed")
        self.assertEqual(self.world.references.rows, {})

    def test_a_message_without_a_directory_id_is_not_the_message_of_a_listed_person(self):
        activity = ts.activity("message", text="hello")
        activity["from"].pop("aadObjectId")
        self.world.call(activity)
        self.assertIn("not on my list", self.fake.sent()[0]["body"]["text"])
        self.assertEqual(self.world.references.rows, {})

    def test_what_is_written_outside_the_personal_chat_is_left_alone(self):
        self.world.call(ts.activity("message", text="hello", personal=False))
        self.assertEqual((self.fake.calls, self.world.references.rows), ([], {}))

    def test_adding_the_app_keeps_the_conversation_and_sends_the_one_welcome_card(self):
        self.world.call(ts.activity("installationUpdate", action="add"))
        self.assertIsNotNone(self.world.references.reference_get(ts.MAYA))
        (card,) = self.fake.cards()
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(self.fake.sent()[0]["body"]["summary"], "[Meternaut] An AI assistant for Azure costs will write to you")
        self.assertIn("Written by an AI", "\n".join(ts.texts(card)))
        self.assertIn("Hello Maya", "\n".join(ts.texts(card)))
        (record,) = self.world.store.mails
        self.assertEqual((record.oid, record.kind, record.status, record.plan_id), (ts.MAYA, "first-contact-card", "sent", None))
        self.assertNotIn("Maya", record.subject + record.detail)

    def test_a_welcome_that_cannot_be_sent_is_a_record_and_the_app_is_still_kept(self):
        self.fake.replies = [(403, {"error": {"code": "MessageWritesBlocked", "message": "blocked"}})]
        reply = self.world.call(ts.activity("installationUpdate", action="add"))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(self.world.store.mails[0].status, "failed")
        self.assertIsNotNone(self.world.references.reference_get(ts.MAYA))

    def test_somebody_who_is_not_listed_adds_the_app_and_nothing_is_sent_or_kept(self):
        self.world.call(ts.activity("installationUpdate", action="add", oid=ts.STRANGER))
        self.assertEqual((self.fake.calls, self.world.references.rows, self.world.store.mails), ([], {}, []))

    def test_removing_the_app_forgets_the_conversation_and_an_upgrade_does_nothing(self):
        self.world.call(ts.activity("installationUpdate", action="add"))
        self.fake.calls.clear()
        self.world.call(ts.activity("installationUpdate", action="add-upgrade"))
        self.world.call(ts.activity("installationUpdate", action="remove-upgrade"))
        self.assertEqual(len(self.fake.calls), 0)
        self.assertIsNotNone(self.world.references.reference_get(ts.MAYA))
        self.world.call(ts.activity("installationUpdate", action="remove"))
        self.assertIsNone(self.world.references.reference_get(ts.MAYA))

    def test_a_conversation_update_that_adds_the_bot_keeps_the_conversation_and_sends_no_card(self):
        self.world.call(ts.activity("conversationUpdate", membersAdded=[{"id": f"28:{ts.APP_ID}"}]))
        self.assertIsNotNone(self.world.references.reference_get(ts.MAYA))
        self.assertEqual(self.fake.calls, [], "the welcome is the installation's: one card, not two")
        self.world.references.reference_delete(ts.MAYA)
        self.world.call(ts.activity("conversationUpdate", membersAdded=[{"id": "29:somebody-else"}]))
        self.world.call(ts.activity("conversationUpdate"))
        self.assertIsNone(self.world.references.reference_get(ts.MAYA))

    def test_a_line_that_cannot_be_sent_does_not_fail_the_call(self):
        self.fake.replies = [(500, {})]
        self.assertEqual(self.world.call(ts.activity("message", text="hello")).status_code, 200)

    def test_the_log_holds_no_token_and_no_name(self):
        with support.LogCapture() as capture:
            self.fake.replies = [(403, {})]
            self.world.call(ts.activity("installationUpdate", action="add"))
            self.world.call(ts.activity("message", text="hello"))
        text = "\n".join(capture.messages())
        self.assertNotIn(ts.BOT_TOKEN, text)
        self.assertNotIn("Maya", text)


class TheTimer(unittest.TestCase):
    def test_the_timer_offers_the_cards_that_are_due_and_says_how_many_tries_it_made(self):
        world = ts.World()
        world.open_plan()
        world.channel(ts.MAYA)
        world.references.reference_put(made(ts.MAYA, ts.CONVERSATION, ts.SERVICE, "29:abc", ts.TENANT, ts.START))
        self.assertEqual(teams.tick(prepared=world.services), 1)
        self.assertEqual(len(world.connector_fake.cards()), 1)
        self.assertEqual(teams.tick(prepared=world.services), 0, "a card that was sent is not sent again")

    def test_without_settings_it_does_nothing(self):
        self.assertIsNone(teams.tick(env={}))

    def test_it_never_raises(self):
        class Broken:
            def offers(self):
                raise RuntimeError("broken")
        self.assertIsNone(teams.tick(prepared=Broken()))


if __name__ == "__main__":
    unittest.main()
