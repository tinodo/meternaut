"""The cards that Meternaut sends on its own (cases/offers.py): who gets one, when, and what is written about each try.

The Connector is a fake and the stores are in memory. A card is for a person who chose Teams, goes through the same checks in the same order as a letter (mail.py), and is written about in the
same store of mail records, so that the letter and the card count the same things and never go twice for one request.
"""
import dataclasses
import unittest

import support  # noqa: F401  (puts the app on the path)
import teamssupport as ts
from cases import cardcheck, cards, offers
from cases.models import ActionRecord, MailRecord, SwitchRecord
from cases.references import made
from cases.teams import Services  # noqa: F401  (the bot's services are what the round runs on)


def kept(world: ts.World, oid: str = ts.MAYA, conversation: str = ts.CONVERSATION) -> None:
    world.references.reference_put(made(oid, conversation, ts.SERVICE, "29:abc", ts.TENANT, ts.START))


def tries(world: ts.World, oid: str = ts.MAYA, kind: str | None = None) -> list[MailRecord]:
    return [m for m in world.store.mails if m.oid == oid and (kind is None or m.kind == kind)]


def run(world: ts.World) -> int:
    return world.services.offers().run()


def advice(world: ts.World, plan_id: str = ts.PLAN_ID, case_id: str = "c1", **changes):
    return world.open_plan(ts.advice_plan(plan_id, case_id=case_id, expires_at="2026-12-01T00:00:00Z", **changes))


class TheCardOfARequest(unittest.TestCase):
    def setUp(self):
        self.world = ts.World()
        self.fake = self.world.connector_fake
        advice(self.world)
        self.world.channel(ts.MAYA)
        kept(self.world)

    def test_a_person_who_chose_teams_gets_the_card_in_the_conversation_that_is_kept(self):
        self.assertEqual(run(self.world), 1)
        (call,) = self.fake.sent()
        self.assertEqual((call["method"], call["url"]), ("POST", f"{ts.SERVICE}v3/conversations/{ts.CONVERSATION}/activities"))
        self.assertEqual(call["body"]["recipient"], {"id": "29:abc"})
        (card,) = self.fake.cards()
        self.assertEqual(cardcheck.check(card), [])
        (record,) = tries(self.world)
        self.assertEqual((record.kind, record.status, record.plan_id), ("advice-card", "sent", ts.PLAN_ID))
        self.assertEqual(self.world.store.mails, [record])

    def test_the_token_of_the_card_is_made_for_that_person_and_that_request_and_lives_until_the_request_expires(self):
        run(self.world)
        (card,) = self.fake.cards()
        (nonce,) = {action["data"]["nonce"] for action in _executes(card)}
        self.assertEqual(self.world.store.nonces[nonce][:2], (ts.MAYA, ts.PLAN_ID))
        left = (self.world.store.nonces[nonce][2] - self.world.clock()).total_seconds()
        self.assertEqual(left, offers.NONCE_SECONDS[1], "a request that expires in 26 days gets the longest life: 14 days")

    def test_the_notification_names_no_resource_and_no_amount(self):
        run(self.world)
        self.assertEqual(self.fake.sent()[0]["body"]["summary"], "[Meternaut] A decision waits for you")
        record = self.world.store.mails[0]
        self.assertEqual(record.subject, "[Meternaut] A decision waits for you")
        self.assertNotIn("disk", record.detail.lower())

    def test_a_card_that_was_sent_is_not_sent_again(self):
        run(self.world)
        self.world.clock.advance(hours=2)
        self.assertEqual(run(self.world), 0)
        self.assertEqual(len(self.fake.sent()), 1)

    def test_only_the_people_who_chose_teams_get_a_card(self):
        kept(self.world, ts.ANNA, "a:1anna-conversation")
        for channel in ("email", "desk"):
            self.world.channel(ts.ANNA, channel)
            self.world.channel(ts.MAYA, channel)
            self.assertEqual(run(self.world), 0, channel)
        self.assertEqual((self.fake.calls, self.world.store.mails), ([], []))
        self.world.channel(ts.ANNA)
        self.assertEqual(run(self.world), 1)
        self.assertIn("a:1anna-conversation", self.fake.sent()[0]["url"])

    def test_nobody_who_may_not_answer_gets_a_card(self):
        self.world.open_plan(ts.advice_plan("p2ops", case_id="c2", approvers=(ts.OMAR,), expires_at="2026-12-01T00:00:00Z"))
        self.world.channel(ts.OMAR)
        kept(self.world, ts.OMAR, "a:1omar-conversation")
        run(self.world)
        self.assertEqual(tries(self.world, ts.OMAR), [])

    def test_a_request_that_is_over_or_that_a_person_answered_is_not_offered(self):
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(ts.PLAN_ID), state="declined"))
        self.assertEqual(run(self.world), 0)
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(ts.PLAN_ID), state="open", expires_at="2026-11-05T10:00:00Z"))
        self.assertEqual(run(self.world), 0)
        self.assertEqual(self.fake.calls, [])

    def test_a_letter_that_went_already_stops_the_card_of_an_approval(self):
        self.world.open_plan(ts.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.store.mail_put(MailRecord("m1", ts.MAYA, "approval", "[Meternaut] x", "2026-11-05T10:00:00Z", "sent", "p3change", ""))
        run(self.world)
        self.assertEqual([m.kind for m in tries(self.world)], ["approval", "advice-card"], "the advice card of the other request went; the approval card did not")

    def test_the_card_of_a_change_has_the_link_to_the_page_and_no_answer_that_approves(self):
        self.world.open_plan(ts.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        run(self.world)
        card = next(c for c in self.fake.cards() if "Review and decide" in str(c))
        self.assertEqual({a["verb"] for a in _executes(card)}, {"not_mine", "later", "ask"})
        self.assertEqual(sorted(m.kind for m in tries(self.world)), ["advice-card", "approval-card"])

    def test_a_pause_of_the_changes_is_said_on_the_card_of_a_change(self):
        self.world.store.plan_put(dataclasses.replace(self.world.store.plan_get(ts.PLAN_ID), state="declined"))
        self.world.open_plan(ts.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.store.switch_put(SwitchRecord(name="changes", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        run(self.world)
        (card,) = self.fake.cards()
        self.assertNotIn("Review and decide", "\n".join(ts.texts(card)))
        self.assertIn("Changes are paused here.", "\n".join(ts.texts(card)))


class TheChecksBeforeACard(unittest.TestCase):
    def setUp(self):
        self.world = ts.World()
        self.fake = self.world.connector_fake
        advice(self.world)
        self.world.channel(ts.MAYA)
        kept(self.world)

    def held(self, words):
        (record,) = tries(self.world)
        self.assertEqual(record.status, "held")
        self.assertIn(words, record.detail)
        self.assertEqual(self.fake.calls, [])

    def test_a_switch_that_is_pulled_holds_the_card(self):
        for name in ("messages", "all"):
            self.world.store.mails.clear()
            self.world.store.switch_put(SwitchRecord(name=name, paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
            run(self.world)
            self.held(f'The switch "{name}"')
            self.world.store.switch_put(SwitchRecord(name=name))

    def test_a_switch_that_cannot_be_read_counts_as_pulled(self):
        def broken(name):
            raise RuntimeError("down")
        self.world.store.switch_get = broken
        run(self.world)
        self.held("pulled, or cannot be read")

    def test_a_person_who_paused_messages_gets_none_until_it_is_over(self):
        self.world.channel(ts.MAYA, paused_until="2026-11-06T00:00:00Z")
        run(self.world)
        self.held("paused messages until 2026-11-06T00:00:00Z")
        self.world.clock.advance(days=1)
        self.assertEqual(run(self.world), 1)
        self.assertEqual([m.status for m in tries(self.world)], ["held", "sent"])

    def test_a_card_that_was_held_is_offered_again_after_fifteen_minutes_and_not_sooner(self):
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        run(self.world)
        self.world.store.switch_put(SwitchRecord(name="messages"))
        self.world.clock.advance(minutes=14)
        self.assertEqual(run(self.world), 0)
        self.world.clock.advance(minutes=1)
        self.assertEqual(run(self.world), 1)
        self.assertEqual([m.status for m in tries(self.world)], ["held", "sent"])

    def test_the_tries_are_used_up_after_twelve(self):
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        for _ in range(offers.MAX_TRIES + 3):
            run(self.world)
            self.world.clock.advance(minutes=offers.RETRY_MINUTES)
        self.assertEqual(len(tries(self.world)), offers.MAX_TRIES)

    def test_the_weekly_budget_holds_the_cards_of_advice_and_nothing_else(self):
        self.world.channel(ts.MAYA, weekly_budget=1)
        advice(self.world, "p2second", "c2")
        run(self.world)
        self.assertEqual(sorted(m.status for m in tries(self.world, kind="advice-card")), ["held", "sent"])
        self.assertIn("The weekly budget of 1 messages is reached", next(m.detail for m in tries(self.world) if m.status == "held"))
        self.world.channel(ts.MAYA, weekly_budget=0)
        self.world.open_plan(ts.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        run(self.world)
        self.assertEqual([m.status for m in tries(self.world, kind="approval-card")], ["sent"], "an approval is asked for: the budget does not hold it, as it does not hold its letter")

    def test_a_new_week_has_a_new_budget(self):
        self.world.channel(ts.MAYA, weekly_budget=1)
        advice(self.world, "p2second", "c2")
        run(self.world)
        self.world.clock.advance(days=4)  # Monday 2026-11-09
        run(self.world)
        self.assertEqual(sorted(m.status for m in tries(self.world, kind="advice-card")), ["held", "sent", "sent"])

    def test_the_weekly_summary_is_not_a_card(self):
        self.world.channel(ts.MAYA, "desk")
        self.assertEqual(run(self.world), 0)


class TheConversation(unittest.TestCase):
    def setUp(self):
        self.world = ts.World()
        self.fake = self.world.connector_fake
        advice(self.world)
        self.world.channel(ts.MAYA)

    def test_a_person_with_no_conversation_gets_one_started_and_it_is_kept(self):
        self.assertEqual(run(self.world), 1)
        start, send = self.fake.calls
        self.assertEqual(start["url"], "https://smba.trafficmanager.net/teams/v3/conversations")
        self.assertEqual(start["body"]["members"], [{"id": ts.MAYA}])
        reference = self.world.references.reference_get(ts.MAYA)
        self.assertEqual((reference.conversation_id, reference.service_url), ("a:started-0123456789", "https://smba.trafficmanager.net/teams/"))
        self.assertEqual(send["url"], "https://smba.trafficmanager.net/teams/v3/conversations/a:started-0123456789/activities")
        self.assertEqual(tries(self.world)[0].status, "sent")

    def test_an_app_that_is_not_installed_is_a_failed_try_that_says_so(self):
        self.fake.replies = [(403, {"error": {"code": "BotNotInConversationRoster", "message": "not installed"}})]
        run(self.world)
        (record,) = tries(self.world)
        self.assertEqual(record.status, "failed")
        self.assertIn("no conversation with this person", record.detail)
        self.assertIn("not installed", record.detail)
        self.assertIsNone(self.world.references.reference_get(ts.MAYA))
        self.assertEqual(len(self.fake.sent()), 0, "nothing was sent")

    def test_a_conversation_that_is_gone_is_forgotten_and_the_try_is_a_failure(self):
        kept(self.world)
        self.fake.replies = [(404, {"error": {"code": "ConversationNotFound", "message": "gone"}})]
        run(self.world)
        self.assertIsNone(self.world.references.reference_get(ts.MAYA))
        self.assertEqual(tries(self.world)[0].status, "failed")
        self.world.clock.advance(minutes=15)
        run(self.world)
        self.assertEqual([m.status for m in tries(self.world)], ["failed", "sent"], "the next try starts a new conversation")

    def test_a_failure_is_not_the_end_of_the_round(self):
        kept(self.world)
        kept(self.world, ts.ANNA, "a:1anna-conversation")
        self.world.channel(ts.ANNA)
        real = self.world.references.reference_get

        def flaky(oid):
            if oid == ts.MAYA:
                raise RuntimeError("the table is down")
            return real(oid)
        self.world.references.reference_get = flaky
        run(self.world)
        self.assertEqual(tries(self.world, ts.MAYA), [])
        self.assertEqual([m.status for m in tries(self.world, ts.ANNA)], ["sent"])


class TheCardsAboutAChange(unittest.TestCase):
    def setUp(self):
        self.world = ts.World()
        self.fake = self.world.connector_fake
        self.plan = self.world.open_plan(ts.change_plan(expires_at="2026-12-01T00:00:00Z", state="consumed"))
        self.world.channel(ts.MAYA)
        kept(self.world)

    def action(self, state="done", **changes):
        values = dict(plan_id=ts.PLAN_ID, case_id="c1", family="delete-disk", resource_id=self.plan.resource_id, state=state, queued_at="2026-11-05T10:00:00Z",
                      finished_at="2026-11-05T10:10:00Z", result="Deleted.", correlation_id="x")
        values.update(changes)
        self.world.store.action_put(ActionRecord(**values))

    def test_a_change_that_ran_gets_a_card_of_what_became_of_it_without_an_answer_or_a_token(self):
        self.action()
        self.assertEqual(run(self.world), 1)
        (card,) = self.fake.cards()
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(_executes(card), [])
        self.assertNotIn("nonce", str(card))
        self.assertEqual(self.fake.sent()[0]["body"]["summary"], "[Meternaut] A change to Azure has run")
        self.assertEqual([(m.kind, m.status) for m in tries(self.world)], [("notice-card", "sent")])

    def test_the_check_afterwards_is_a_second_card_and_neither_goes_twice(self):
        self.action("verified", verification={"gone": True})
        run(self.world)
        run(self.world)
        self.assertEqual(sorted(m.kind for m in tries(self.world)), ["notice-card", "verified-card"])
        self.assertEqual(len(self.fake.sent()), 2)

    def test_a_change_of_long_ago_and_a_letter_that_went_are_left_alone(self):
        self.action(finished_at="2026-11-01T10:10:00Z")
        self.assertEqual(run(self.world), 0)
        self.action()
        self.world.store.mail_put(MailRecord("m1", ts.MAYA, "notice", "[Meternaut] x", "2026-11-05T10:12:00Z", "sent", ts.PLAN_ID, ""))
        self.assertEqual(run(self.world), 0)

    def test_a_person_who_did_not_choose_teams_gets_no_card_about_a_change(self):
        self.action()
        self.world.channel(ts.MAYA, "email")
        self.assertEqual(run(self.world), 0)


class TheLifeOfAToken(unittest.TestCase):
    def test_it_lives_until_the_request_expires_between_fifteen_minutes_and_two_weeks(self):
        now = ts.START
        for expires, seconds in (("2026-11-05T10:20:00Z", 900), ("2026-11-05T09:00:00Z", 900), ("2026-11-08T10:18:00Z", 3 * 86400), ("2027-01-01T00:00:00Z", 14 * 86400), ("not a time", 900)):
            plan = ts.advice_plan(expires_at=expires)
            self.assertEqual(offers.nonce_seconds(plan, now), seconds, expires)

    def test_the_card_texts_carry_no_name_of_the_estate(self):
        self.assertEqual(set(offers.SUMMARY_OF.values()) - set(cards.SUMMARIES), set())
        for text in cards.SUMMARIES.values():
            self.assertNotRegex(text, r"\d")


def _executes(card):
    found = []

    def walk(node):
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


if __name__ == "__main__":
    unittest.main()
