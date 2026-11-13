"""The Teams cards through the bot (TEAMS_DELIVERY=bot): what the rounds of cards (cases/offers.py) do when the card goes straight to the person, what each answer of Teams means for the
person, the letter that follows, the settings that fail closed, the block of the Operations page and the test card that proves the way.

The Bot Connector and Microsoft Entra are one fake transport (test_teamsbot.py), the stores are in memory, the clock is moved by the tests. Every id is invented.
"""
import dataclasses
import importlib.util
import json
import re
import socket
import sys
import unittest
import urllib.error
from dataclasses import dataclass, field
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import cardcheck, cards, control, events as history, loop_config, notify, offers, teamsbot, wiring
from cases.identity import IdentityError
from cases.memory_store import MemoryStore, stamp
from cases.models import ActionRecord, DecisionRecord, MailRecord, SwitchRecord
from cases.redact import Redactor
from support import REPO_ROOT, LogCapture, fixed_clock
from test_control import FakeMessage, Recorder
from test_notify import ENV as LOOP_ENV, Graph
from test_teamsbot import ACCESS, ACTIVITY, APP, ASSERTION, BAD_ARGUMENT, CODES, CONVERSATION, FORBIDDEN, IDENTITY, TENANT, WAY, WRITES_BLOCKED, FakeTeams, answer
from test_web_support import Console

SIGNIN = {"SIGNIN_TENANT_ID": TENANT, "SIGNIN_CLIENT_ID": "44444444-aaaa-4bbb-8ccc-000000000004", "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID": "55555555-aaaa-4bbb-8ccc-000000000005"}
BOT = {"TEAMS_DELIVERY": "bot", "TEAMS_BOT_APP_ID": APP, "TEAMS_BOT_IDENTITY_CLIENT_ID": IDENTITY}
PEOPLE_OF_THE_TESTS = json.dumps([{"oid": p.oid, "name": p.name, "roles": list(p.roles), "mail": p.mail} for p in cs.people().persons])
ENV = {**LOOP_ENV, "CONSOLE_PEOPLE": PEOPLE_OF_THE_TESTS, **SIGNIN, **BOT}
LATER = "1731331200002"


@dataclass
class BotWorld(cs.World):
    """The round of cards with the bot way on: the same stores, people and clock as cs.World, a fake Teams, and no queue at all."""

    teams: FakeTeams = field(default_factory=FakeTeams)

    def __post_init__(self) -> None:
        super().__post_init__()
        client = teamsbot.new_client(WAY, Redactor(), transport=self.teams, sleep=lambda seconds: None)
        self.bot = teamsbot.TeamsBot(WAY, lambda resource, within=None: ASSERTION, client, self.clock)
        self.offers = offers.Offers(self.store, self.people, None, cs.BASE, self.clock, Redactor(), bot=self.bot)

    def posted(self, oid: str = cs.MAYA) -> list[MailRecord]:
        return [m for m in self.store.mails if m.oid == oid and m.kind == offers.POSTED]

    def attempts(self, oid: str = cs.MAYA, kind: str | None = None) -> list[MailRecord]:
        """The tries of the cards, without the records of the cards that were posted."""
        return [m for m in self.tries(oid, kind) if m.kind != offers.POSTED]

    def bodies(self, step: str) -> list[dict]:
        return [json.loads(call["data"]) for call in self.teams.calls if call["step"] == step]

    def ready(self, *oids: str) -> None:
        for oid in oids:
            self.channel(oid)
        self.introduce(*oids)


def end(world: BotWorld, plan, state: str = "declined", by: str = cs.ANNA) -> None:
    world.store.plan_put(dataclasses.replace(plan, state=state))
    world.store.decision_put(DecisionRecord(plan.plan_id, by, "Anna", "decline", "2026-11-05T10:30:00Z", cs.CODE))


class TheCardGoesStraightToTeams(unittest.TestCase):
    def setUp(self):
        self.world = BotWorld()
        self.plan = self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        self.world.ready(cs.MAYA)

    def test_a_person_who_chose_teams_gets_the_card_straight_and_nothing_is_put_on_a_queue(self):
        self.assertEqual(self.world.run(), 1)
        self.assertEqual(self.world.teams.steps(), ["token", "create", "send"])
        self.assertEqual(self.world.queue_fake.calls, [])
        self.assertEqual(self.world.bodies("create")[0]["members"], [{"id": cs.MAYA}], "the person is named by the object id of the list of people")
        (activity,) = self.world.bodies("send")
        (card,) = [a["content"] for a in activity["attachments"]]
        self.assertEqual((activity["summary"], cardcheck.check(card)), (cards.SUMMARIES["advice"], []))
        (record,) = self.world.attempts()
        self.assertEqual((record.kind, record.status, record.plan_id, record.detail), (offers.ADVICE, "sent", cs.PLAN_ID, teamsbot.SENT))

    def test_the_ids_of_the_posted_card_are_kept_at_once_and_nothing_else_of_it(self):
        self.world.run()
        (record,) = self.world.posted()
        self.assertEqual((record.status, record.plan_id, record.subject, record.detail), ("posted", cs.PLAN_ID, "A card was posted", f"{ACTIVITY} {CONVERSATION} bot"))
        text = json.dumps([record.subject, record.detail, record.status, record.plan_id])
        for hidden in ("Maya", "maya@example.com", "disk", "Look at", ACCESS):
            self.assertNotIn(hidden, text)
        self.assertEqual(self.world.tries(cs.MAYA, offers.POSTED), self.world.posted())

    def test_a_card_is_sent_once_for_a_plan(self):
        self.world.run()
        self.world.clock.advance(hours=3)
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(self.world.teams.steps(), ["token", "create", "send"])

    def test_every_approver_who_chose_teams_gets_a_card_of_their_own(self):
        self.world.ready(cs.ANNA)
        self.world.teams.replies["create"] = [answer(201, {"id": "a:maya"}), answer(201, {"id": "a:anna"})]
        self.world.teams.replies["send"] = [answer(201, {"id": "m1"}), answer(201, {"id": "m2"})]
        self.assertEqual(self.world.run(), 2)
        self.assertEqual(sorted(member["id"] for body in self.world.bodies("create") for member in body["members"]), sorted([cs.MAYA, cs.ANNA]))
        self.assertEqual(self.world.teams.steps().count("token"), 1, "one token for the round")
        self.assertEqual([m.detail for m in self.world.posted(cs.ANNA)], ["m2 a:anna bot"])

    def test_a_card_that_does_not_fit_is_replaced_by_the_short_one_and_the_record_says_so(self):
        with mock.patch.object(cards, "decision_card", side_effect=cards.CardTooLarge("too big")):
            self.world.run()
        (card,) = [a["content"] for a in self.world.bodies("send")[0]["attachments"]]
        self.assertIn(cards.SHORT_CARD, cs.texts(card))
        self.assertEqual(self.world.attempts()[0].detail, f"{offers.SHORT_SENT} {teamsbot.SENT}")
        self.assertEqual(len(self.world.posted()), 1)

    def test_a_card_that_cannot_be_made_is_a_failed_try_and_nothing_is_called(self):
        with mock.patch.object(cards, "decision_card", side_effect=cards.CardError("the card is wrong")):
            self.world.run()
        (record,) = self.world.attempts()
        self.assertEqual((record.status, record.detail), ("failed", "The card could not be made: the card is wrong"))
        self.assertEqual((self.world.teams.calls, self.world.posted()), ([], []))

    def test_the_card_that_says_who_writes_goes_first_the_same_way_and_is_not_a_card_that_can_be_replaced(self):
        world = BotWorld()
        world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        world.channel(cs.MAYA)
        world.teams.replies["send"] = [answer(201, {"id": "hello"}), answer(201, {"id": "decision"})]
        self.assertEqual(world.run(), 2)
        self.assertEqual([m.kind for m in world.attempts()], [offers.FIRST_CONTACT, offers.ADVICE])
        self.assertEqual([m.detail for m in world.posted()], ["decision a:1Abc-DEF_ghi bot"], "only the card of a request is kept for its closing")

    def test_the_weekly_budget_and_the_free_kinds_count_as_they_did(self):
        world = BotWorld()
        world.ready(cs.MAYA)
        world.channel(cs.MAYA, weekly_budget=1)
        for number in range(3):
            world.open_plan(cs.advice_plan(f"padvice{number}", case_id=f"c{number}", expires_at="2026-12-01T00:00:00Z"))
        world.open_plan(cs.change_plan("pchange", case_id="c9", approvers=(cs.MAYA,), expires_at="2026-12-01T00:00:00Z"))
        world.run()
        by_plan = {m.plan_id: m.status for m in world.attempts() if m.kind in (offers.ADVICE, offers.APPROVAL)}
        self.assertEqual(sorted(status for plan, status in by_plan.items() if plan.startswith("padvice")), ["held", "held", "sent"], "a budget of one: the first advice goes, the rest wait")
        self.assertEqual(by_plan["pchange"], "sent", "an approval is asked for, so no budget holds it")
        self.assertIn("The weekly budget of 1 messages is reached", next(m.detail for m in world.attempts() if m.status == "held"))

    def test_a_pulled_switch_a_pause_and_quiet_hours_hold_the_card_as_they_always_did(self):
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.world.run()
        self.assertEqual(([m.status for m in self.world.attempts()], self.world.teams.calls), (["held"], []))

    def test_a_card_about_a_change_goes_the_same_way_and_is_not_kept_for_a_closing(self):
        world = BotWorld()
        world.ready(cs.MAYA)
        plan = world.open_plan(cs.change_plan(approvers=(cs.MAYA,), expires_at="2026-12-01T00:00:00Z", state="consumed"))
        world.store.action_put(ActionRecord(plan.plan_id, plan.case_id, plan.family, plan.resource_id, "done", "2026-11-05T10:00:00Z", finished_at="2026-11-05T10:05:00Z", result="Deleted."))
        world.run()
        self.assertEqual([(m.kind, m.status) for m in world.attempts()], [(offers.NOTICE, "sent")])
        self.assertEqual((world.posted(), world.teams.steps()), ([], ["token", "create", "send"]))


class TheCardClosesByAnUpdateOfItsActivity(unittest.TestCase):
    def setUp(self):
        self.world = BotWorld()
        self.plan = self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        self.world.ready(cs.MAYA)
        self.world.run()
        self.world.teams.calls.clear()

    def test_nothing_is_called_while_the_request_waits(self):
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(self.world.teams.calls, [])

    def test_a_request_that_ended_is_closed_with_a_card_without_a_button_in_the_place_of_the_card(self):
        end(self.world, self.plan)
        self.assertEqual(self.world.run(), 1)
        (call,) = [c for c in self.world.teams.calls if c["step"] == "update"]
        self.assertEqual((call["method"], call["url"]), ("PUT", f"https://smba.trafficmanager.net/teams/v3/conversations/{CONVERSATION}/activities/{ACTIVITY}"))
        (card,) = [a["content"] for a in self.world.bodies("update")[0]["attachments"]]
        self.assertEqual((cardcheck.check(card), "Action." in json.dumps(card)), ([], False))
        self.assertIn("Not worth it by Anna", " ".join(cs.texts(card)))
        self.assertEqual(self.world.bodies("update")[0]["summary"], cards.SUMMARIES["closed"])
        self.assertEqual([(m.kind, m.status, m.detail) for m in self.world.tries(cs.MAYA, offers.CLOSED)], [(offers.CLOSED, "sent", teamsbot.SENT)])
        self.assertEqual(self.world.queue_fake.calls, [], "nothing is put on a queue")

    def test_it_is_done_once(self):
        end(self.world, self.plan)
        self.world.run()
        self.world.clock.advance(hours=1)
        self.assertEqual(self.world.run(), 0)
        self.assertEqual(self.world.teams.steps().count("update"), 1)

    def test_a_request_that_has_not_really_ended_keeps_its_card(self):
        for state, action in (("open", None), ("approved", None)):
            self.world.store.plan_put(dataclasses.replace(self.plan, state=state))
            self.assertEqual(self.world.run(), 0, state)
        made = ActionRecord(cs.PLAN_ID, "c1", "delete-disk", "r1", "running", "2026-11-05T10:30:00Z")
        self.world.store.action_put(made)
        self.world.store.plan_put(dataclasses.replace(self.plan, state="consumed"))
        self.assertEqual(self.world.run(), 0, "a change that is being made is not over")
        self.assertEqual(self.world.teams.calls, [])
        self.world.store.action_put(dataclasses.replace(made, state="done", finished_at="2026-11-05T10:40:00Z", result="Deleted."))
        self.world.clock.advance(minutes=1)
        self.world.run()
        self.assertEqual(self.world.teams.steps().count("update"), 1, "the change is over: the card is replaced now")

    def test_a_change_that_was_not_made_is_closed_with_the_reason_that_the_page_gives(self):
        world = BotWorld()
        plan = world.open_plan(cs.change_plan(approvers=(cs.MAYA,), expires_at="2026-12-01T00:00:00Z"))
        world.ready(cs.MAYA)
        world.run()
        reason = "Azure refused to delete the disk: your account has no right to do this here. Nothing was changed."
        world.store.plan_put(dataclasses.replace(plan, state="failed"))
        world.store.action_put(ActionRecord(plan.plan_id, plan.case_id, plan.family, plan.resource_id, "failed", "2026-11-05T10:30:00Z", finished_at="2026-11-05T10:31:00Z", error=reason, result=reason))
        world.store.decision_put(DecisionRecord(plan.plan_id, cs.MAYA, "Maya", "approve", "2026-11-05T10:30:00Z", cs.CODE))
        world.clock.advance(minutes=1)
        world.run()
        (card,) = [a["content"] for a in world.bodies("update")[0]["attachments"]]
        self.assertIn(f"Approved by Maya, not made: {cards.md(reason)}", " ".join(cs.texts(card)))

    def test_a_request_that_is_open_again_gets_a_new_card_and_only_that_one_is_closed_in_its_turn(self):
        end(self.world, self.plan)
        self.world.run()
        self.world.store.plan_put(dataclasses.replace(self.plan, state="open"))
        self.world.clock.advance(minutes=20)
        self.world.teams.replies["send"] = [answer(201, {"id": LATER})]
        self.assertEqual(self.world.run(), 1, "a card that was closed is no card that was sent for a request that is open again")
        self.assertEqual([m.detail for m in self.world.posted()], [f"{ACTIVITY} {CONVERSATION} bot", f"{LATER} {CONVERSATION} bot"])
        self.world.teams.calls.clear()
        self.world.clock.advance(minutes=20)
        end(self.world, self.plan)
        self.assertEqual(self.world.run(), 1)
        (call,) = [c for c in self.world.teams.calls if c["step"] == "update"]
        self.assertTrue(call["url"].endswith(f"/activities/{LATER}"), "the new card, and not the first one again")

    def test_a_closing_that_teams_refuses_is_a_failed_try_in_plain_words_and_is_given_up_after_twelve(self):
        end(self.world, self.plan)
        self.world.teams.replies["update"] = [answer(404, {"error": {"code": "ActivityNotFound"}})] * 40
        for _ in range(30):
            self.world.run()
            self.world.clock.advance(minutes=offers.RETRY_MINUTES + 1)
        tries = self.world.tries(cs.MAYA, offers.CLOSED)
        self.assertEqual((len(tries), {m.status for m in tries}, {m.detail for m in tries}), (offers.MAX_TRIES, {"failed"}, {teamsbot.NOT_REPLACED}))
        self.assertEqual(self.world.teams.steps().count("update"), offers.MAX_TRIES)

    def test_a_card_that_cannot_be_replaced_because_the_app_is_gone_says_so_and_promises_no_letter(self):
        end(self.world, self.plan)
        self.world.teams.replies["update"] = [answer(403, FORBIDDEN)]
        self.world.run()
        (record,) = self.world.tries(cs.MAYA, offers.CLOSED)
        self.assertEqual((record.status, record.detail), ("failed", teamsbot.REPLACE["not-installed"]))
        self.assertNotIn("letter", record.detail)

    def test_a_pulled_switch_does_not_keep_a_card_open_because_it_tells_nobody_anything_new(self):
        end(self.world, self.plan)
        self.world.store.switch_put(SwitchRecord(name="messages", paused=True, by="Maya", at="2026-11-05T10:00:00Z"))
        self.assertEqual(self.world.run(), 1)

    def test_a_card_that_the_other_way_posted_is_replaced_by_that_way_or_not_at_all(self):
        queue = cs.World()
        plan = queue.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        queue.channel(cs.MAYA)
        queue.introduce(cs.MAYA)
        queue.store.mail_put(MailRecord("m1", cs.MAYA, offers.POSTED, "A card was posted", "2026-11-05T10:20:00Z", "posted", cs.PLAN_ID, f"{ACTIVITY} {CONVERSATION} bot"))
        queue.store.plan_put(dataclasses.replace(plan, state="declined"))
        self.assertEqual((queue.run(), queue.queue_fake.calls), (0, []), "a card of the bot is not replaced through the queue")
        flow = BotWorld()
        plan = flow.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        flow.ready(cs.MAYA)
        flow.store.mail_put(MailRecord("m2", cs.MAYA, offers.POSTED, "A card was posted", "2026-11-05T10:20:00Z", "posted", cs.PLAN_ID, f"{ACTIVITY} {CONVERSATION}"))
        flow.store.mail_put(MailRecord("m3", cs.MAYA, offers.ADVICE, "x", "2026-11-05T10:20:00Z", "sent", cs.PLAN_ID, ""))
        flow.store.plan_put(dataclasses.replace(plan, state="declined"))
        self.assertEqual((flow.run(), flow.teams.calls), (0, []), "a card of the flow is not replaced by the bot")


class WhenTeamsSaysNo(unittest.TestCase):
    def setUp(self):
        self.world = BotWorld()
        self.plan = self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        self.world.ready(cs.MAYA, cs.ANNA)

    def test_a_person_without_the_app_is_a_failed_try_with_that_reason_and_the_other_approver_still_gets_the_card(self):
        self.world.teams.replies["create"] = [answer(403, FORBIDDEN)]
        self.assertEqual(self.world.run(), 2)
        (maya,), (anna,) = self.world.attempts(cs.MAYA), self.world.attempts(cs.ANNA)
        self.assertEqual((maya.status, maya.detail), ("failed", teamsbot.REASONS["not-installed"]))
        self.assertEqual((anna.status, len(self.world.posted(cs.ANNA)), self.world.posted(cs.MAYA)), ("sent", 1, []))

    def test_a_person_who_blocked_the_app_is_told_apart_and_gets_no_posted_record(self):
        self.world.teams.replies["send"] = [answer(403, WRITES_BLOCKED)]
        self.world.run()
        (maya,) = self.world.attempts(cs.MAYA)
        self.assertEqual((maya.status, maya.detail, self.world.posted(cs.MAYA)), ("failed", teamsbot.REASONS["blocked"], []))

    def test_it_is_tried_again_after_fifteen_minutes_and_not_before_and_never_more_than_twelve_times(self):
        self.world.teams.replies["create"] = [answer(403, FORBIDDEN)] * 60
        self.world.run()
        self.world.clock.advance(minutes=14)
        self.assertEqual(self.world.run(), 0, "the try is not made again before 15 minutes")
        for _ in range(30):
            self.world.clock.advance(minutes=offers.RETRY_MINUTES + 1)
            self.world.run()
        self.assertEqual(len(self.world.attempts(cs.MAYA)), offers.MAX_TRIES)
        self.assertEqual(self.world.teams.steps().count("create"), offers.MAX_TRIES + len(self.world.attempts(cs.ANNA)), "Anna's one card is the other create")

    def test_an_identity_that_is_wrong_fails_every_card_of_the_round_with_one_token_request(self):
        self.world.teams.replies["token"] = [answer(401, {"error": "invalid_client", "error_description": "AADSTS700213: no federated identity record"})]
        self.assertEqual(self.world.run(), 2)
        self.assertEqual(self.world.teams.steps(), ["token"], "the second person's card waits for nothing: the same failure is given")
        self.assertEqual({m.detail for oid in (cs.MAYA, cs.ANNA) for m in self.world.attempts(oid)}, {teamsbot.REASONS["unauthorized"]})

    def test_a_throttle_and_a_silence_are_failed_tries_that_say_so(self):
        self.world.teams.replies["send"] = [answer(429, {}, retry_after="3600"), OSError("lost")]
        self.world.run()
        self.assertEqual([self.world.attempts(cs.MAYA)[0].detail, self.world.attempts(cs.ANNA)[0].detail], [teamsbot.REASONS["throttled"], teamsbot.NOT_RETRIED],
                         "a silence after the post may be a card that arrived: it says so")

    def test_a_try_never_holds_a_token_an_id_or_what_teams_said(self):
        self.world.teams.replies["create"] = [answer(403, FORBIDDEN)]
        self.world.run()
        text = json.dumps([dataclasses.asdict(m) for m in self.world.store.mails])
        for hidden in (ACCESS, ASSERTION, "ForbiddenOperationException", "personal scope", APP, TENANT, IDENTITY):
            self.assertNotIn(hidden, text)

    def test_a_card_that_teams_did_not_take_leaves_the_letter_to_follow_after_twenty_minutes_and_a_card_that_it_took_leaves_none(self):
        world = BotWorld()
        graph = Graph()
        plan = world.open_plan(cs.change_plan(approvers=(cs.MAYA, cs.ANNA), created_at=stamp(cs.START), expires_at="2026-12-01T00:00:00Z"))
        world.ready(cs.MAYA, cs.ANNA)
        env = {**LOOP_ENV, "CONSOLE_PEOPLE": PEOPLE_OF_THE_TESTS}
        on_plan, _, _ = notify.hooks(env, loop_config.load(env), world.store, world.people, lambda resource: "tok", lambda text: text, transport=graph, sleep=lambda s: None,
                                     monotonic=lambda: 0.0, clock=world.clock)
        world.teams.replies["create"] = [answer(403, FORBIDDEN)]
        world.run()
        case = world.store.case_get(plan.case_id)
        on_plan(plan, case)
        self.assertEqual(graph.sent, [], "the card has the first twenty minutes, whatever came of it")
        world.clock.advance(minutes=21)
        on_plan(plan, case)
        self.assertEqual(graph.to(), ["maya@example.com"], "the person for whom Teams said no gets the letter, and the person whose card went gets none")

    def test_a_post_whose_answer_was_lost_is_never_posted_again_and_the_letter_follows_after_twenty_minutes(self):
        for lost in (TimeoutError("slow"), answer(502), answer(201, {})):
            with self.subTest(lost=str(lost)[:20]):
                world, graph = BotWorld(), Graph()
                plan = world.open_plan(cs.change_plan(approvers=(cs.MAYA,), created_at=stamp(cs.START), expires_at="2026-12-01T00:00:00Z"))
                world.ready(cs.MAYA)
                env = {**LOOP_ENV, "CONSOLE_PEOPLE": PEOPLE_OF_THE_TESTS}
                on_plan, _, _ = notify.hooks(env, loop_config.load(env), world.store, world.people, lambda resource: "tok", lambda text: text, transport=graph, sleep=lambda s: None,
                                             monotonic=lambda: 0.0, clock=world.clock)
                world.teams.replies["send"] = [lost]
                for _ in range(3):
                    world.run()
                    world.clock.advance(minutes=offers.RETRY_MINUTES + 1)
                self.assertEqual(world.teams.steps().count("send"), 1, "the card may have arrived: no round posts it again, and the next post would have worked")
                (record,) = world.attempts(cs.MAYA)
                self.assertEqual((record.status, record.detail, world.posted(cs.MAYA)), ("failed", teamsbot.NOT_RETRIED, []))
                on_plan(plan, world.store.case_get(plan.case_id))
                self.assertEqual(graph.to(), ["maya@example.com"], "the letter follows when the first twenty minutes are over")

    def test_a_failure_before_the_post_is_tried_again_in_the_next_round(self):
        self.world.teams.replies["create"] = [answer(503), answer(503)]
        self.world.run()
        self.world.clock.advance(minutes=offers.RETRY_MINUTES + 1)
        self.world.run()
        self.assertEqual(([m.status for m in self.world.attempts(cs.MAYA)], self.world.teams.steps().count("send"), len(self.world.posted(cs.MAYA))), (["failed", "sent"], 2, 1))

    def test_a_post_that_could_not_connect_is_tried_again_in_the_next_round_and_is_no_card_that_may_have_arrived(self):
        self.world.teams.replies["send"] = [urllib.error.URLError(ConnectionRefusedError()), urllib.error.URLError(socket.gaierror(-2, "no such host"))]
        self.world.run()
        self.assertEqual([[(m.status, m.detail) for m in self.world.attempts(oid)] for oid in (cs.MAYA, cs.ANNA)], [[("failed", teamsbot.REASONS["network"])]] * 2)
        self.assertEqual(self.world.teams.steps().count("send"), 2, "one post for each card of the round")
        self.world.clock.advance(minutes=offers.RETRY_MINUTES + 1)
        self.world.run()
        self.assertEqual(([[m.status for m in self.world.attempts(oid)] for oid in (cs.MAYA, cs.ANNA)], len(self.world.posted(cs.MAYA)), len(self.world.posted(cs.ANNA))), ([["failed", "sent"]] * 2, 1, 1))


class WhenTheSettingsAreNotComplete(unittest.TestCase):
    def way(self, **env):
        return loop_config.load({**LOOP_ENV, **SIGNIN, **env}).teams

    def test_the_default_is_the_queue_whatever_the_other_settings_say(self):
        for env in ({}, {"TEAMS_DELIVERY": ""}, {"TEAMS_DELIVERY": " Queue "}, {"TEAMS_DELIVERY": "queue", **{k: v for k, v in BOT.items() if k != "TEAMS_DELIVERY"}}):
            with self.subTest(env=env):
                self.assertEqual(self.way(**env), loop_config.TeamsWay())
        self.assertEqual(loop_config.TeamsWay().way, "queue")

    def test_the_bot_way_is_on_only_when_every_setting_is_there_and_right(self):
        way = self.way(**BOT, TEAMS_SERVICE_URL=" HTTPS://SMBA.trafficmanager.net/teams ")
        self.assertEqual((way.way, way.why, way.app_id, way.identity_client_id, way.tenant_id, way.service_url), ("bot", "", APP, IDENTITY, TENANT, "https://smba.trafficmanager.net/teams/"),
                         "the one address that is allowed, in any case and without its last slash, is the address of the public cloud")
        self.assertEqual(self.way(**{**BOT, "TEAMS_DELIVERY": "BOT"}).service_url, "https://smba.trafficmanager.net/teams/", "the default is the public cloud")

    def test_a_missing_or_wrong_part_turns_the_way_off_with_one_plain_sentence_and_never_stops_the_loop(self):
        wrong = "TEAMS_SERVICE_URL is not the Bot Connector's address"
        for change, said in (({"TEAMS_BOT_APP_ID": ""}, "TEAMS_BOT_APP_ID is not set"), ({"TEAMS_BOT_IDENTITY_CLIENT_ID": ""}, "TEAMS_BOT_IDENTITY_CLIENT_ID is not set"),
                             ({"TEAMS_BOT_APP_ID": "not a guid"}, "TEAMS_BOT_APP_ID is not a client id"), ({"TEAMS_BOT_IDENTITY_CLIENT_ID": "x" * 36}, "TEAMS_BOT_IDENTITY_CLIENT_ID is not a client id"),
                             ({"TEAMS_SERVICE_URL": "http://smba.trafficmanager.net/teams/"}, wrong), ({"TEAMS_SERVICE_URL": "https://smba.trafficmanager.net/"}, wrong),
                             ({"TEAMS_SERVICE_URL": "https://smba.trafficmanager.net:8443/teams/"}, wrong), ({"TEAMS_SERVICE_URL": "https://evil/teams/"}, wrong),
                             ({"TEAMS_DELIVERY": "banana"}, "TEAMS_DELIVERY is neither queue nor bot")):
            with self.subTest(change=change):
                way = self.way(**{**BOT, **change})
                self.assertEqual(way.way, "off")
                self.assertTrue(way.why.startswith("No Teams card is tried and the letters go instead: ") and said in way.why and way.why.endswith("."), way.why)
                self.assertNotIn("\n", way.why)

    def test_the_address_of_the_bot_connector_is_one_that_is_allowed_and_not_one_that_has_a_shape(self):
        for url in ("https://evil.example/teams/", "https://smba.trafficmanager.net.evil.example/teams/", "https://login.microsoftonline.com/teams/", "https://smba.trafficmanager.net/teams/x/",
                    "https://user@smba.trafficmanager.net/teams/", "https://smba.trafficmanager.net/teams/?a=b", "https://smba.infra.gcc.teams.microsoft.com/teams/", "https://smba.infra.gov.teams.microsoft.us/teams/",
                    "https://smba.infra.dod.teams.microsoft.us/teams/"):
            with self.subTest(url=url):
                way = self.way(**BOT, TEAMS_SERVICE_URL=url)
                self.assertEqual((way.way, "TEAMS_SERVICE_URL is not the Bot Connector's address" in way.why, url in way.why, "evil" in way.why), ("off", True, False, False), "the value is never printed")

    def test_the_tenant_of_the_sign_in_is_needed_and_the_sign_in_is_not_made_up_for_it(self):
        env = {k: v for k, v in {**LOOP_ENV, **BOT}.items() if k not in SIGNIN}
        way = loop_config.load(env).teams
        self.assertEqual((way.way, "SIGNIN_TENANT_ID is not set" in way.why), ("off", True))

    def test_every_part_that_is_wrong_is_named_in_the_one_sentence(self):
        way = self.way(TEAMS_DELIVERY="bot")
        self.assertIn("TEAMS_BOT_APP_ID is not set, TEAMS_BOT_IDENTITY_CLIENT_ID is not set", way.why)

    def test_the_names_of_the_settings_are_the_ones_that_the_template_sets(self):
        self.assertEqual([loop_config.TEAMS_DELIVERY, loop_config.TEAMS_BOT_APP_ID, loop_config.TEAMS_BOT_IDENTITY_CLIENT_ID, loop_config.TEAMS_SERVICE_URL],
                         ["TEAMS_DELIVERY", "TEAMS_BOT_APP_ID", "TEAMS_BOT_IDENTITY_CLIENT_ID", "TEAMS_SERVICE_URL"])
        self.assertEqual(loop_config.DEFAULT_SERVICE_URL, "https://smba.trafficmanager.net/teams/")

    def test_the_loop_stays_on_the_queue_whatever_the_settings_of_the_bot_say_and_the_test_has_a_way_of_its_own(self):
        ids = {name: value for name, value in BOT.items() if name != "TEAMS_DELIVERY"}
        bad = {"TEAMS_BOT_APP_ID": "garbage", "TEAMS_BOT_IDENTITY_CLIENT_ID": "", "TEAMS_SERVICE_URL": "https://evil.example/teams/"}
        for env in (ids, {**ids, "TEAMS_DELIVERY": "queue"}, bad, {**bad, "TEAMS_DELIVERY": "queue"}):
            with self.subTest(env=sorted(env.values())):
                self.assertEqual((self.way(**env), loop_config._teams({**LOOP_ENV, **env}, TENANT)), (loop_config.TeamsWay(), loop_config.TeamsWay()), "the way of the loop is the queue, and the bot is not looked at")
        for delivery, loop in ((None, "queue"), ("queue", "queue"), ("bot", "bot"), ("banana", "off")):
            env = {**ids, **({} if delivery is None else {"TEAMS_DELIVERY": delivery})}
            with self.subTest(delivery=delivery):
                way = loop_config.bot_way(env, TENANT)
                self.assertEqual((way.way, way.why, way.app_id, way.identity_client_id, way.tenant_id, way.service_url), ("bot", "", APP, IDENTITY, TENANT, loop_config.DEFAULT_SERVICE_URL))
                self.assertEqual(self.way(**env).way, loop, "the same settings: the loop's way is what it was")

    def test_the_way_of_the_test_has_the_rules_of_the_bot_way_of_the_loop_and_says_what_is_wrong_in_the_same_words(self):
        for change in ({"TEAMS_BOT_APP_ID": ""}, {"TEAMS_BOT_IDENTITY_CLIENT_ID": "x" * 36}, {"TEAMS_SERVICE_URL": "https://evil.example/teams/"}, {"TEAMS_BOT_APP_ID": "", "TEAMS_BOT_IDENTITY_CLIENT_ID": ""}):
            for delivery in (None, "queue", "banana"):
                env = {**BOT, **change, **({} if delivery is None else {"TEAMS_DELIVERY": delivery})}
                with self.subTest(change=sorted(change), delivery=delivery):
                    before = dict(env)
                    way = loop_config.bot_way(env, TENANT)
                    self.assertEqual((way.way, way, env), ("off", self.way(**{**BOT, **change}), before), "the words of the loop's own bot way, and the settings are left alone")
        self.assertEqual((loop_config.bot_way(BOT, None).way, "SIGNIN_TENANT_ID is not set" in loop_config.bot_way(BOT, None).why), ("off", True))


class TheWiringOfTheWays(unittest.TestCase):
    def extras(self, env, transport=None, fetch=None):
        calls = []

        def refuse(method, url, headers, data, timeout):
            calls.append(url)
            raise AssertionError("no call is expected")
        return wiring.build_extras(env, lambda resource: "tok", Redactor(), transport=transport or refuse, sleep=lambda s: None, monotonic=lambda: 0.0, clock=cs.Moving(), fetch=fetch), calls

    def test_the_queue_is_the_way_unless_the_settings_say_bot_and_its_cards_are_the_ones_of_before(self):
        for env in ({**ENV, "TEAMS_DELIVERY": "queue", "TEAMS_CARDS_QUEUE": "teams-cards"}, {k: v for k, v in {**ENV, "TEAMS_CARDS_QUEUE": "teams-cards"}.items() if k not in BOT}):
            with self.subTest(env=env.get("TEAMS_DELIVERY")):
                extras, calls = self.extras(env)
                offering = extras.on_cards.__self__
                self.assertEqual((type(offering).__name__, offering.bot, offering.queue is not None, calls), ("Offers", None, True, []))

    def test_without_a_queue_the_queue_way_sends_no_card_as_it_always_did(self):
        extras, calls = self.extras({k: v for k, v in ENV.items() if k not in BOT})
        self.assertEqual((extras.on_cards(), calls), (0, []))

    def test_the_bot_way_has_no_queue_and_asks_the_platform_for_the_token_of_the_identity_that_was_named(self):
        asked = []

        def fetch(url, headers, timeout):
            asked.append(url)
            return 200, json.dumps({"access_token": ASSERTION, "expires_on": "4102444800"}).encode()
        fake = FakeTeams()
        extras, _ = self.extras({**ENV, "TEAMS_CARDS_QUEUE": "teams-cards", "IDENTITY_ENDPOINT": "http://localhost:8081/msi/token", "IDENTITY_HEADER": "h"}, transport=fake, fetch=fetch)
        offering = extras.on_cards.__self__
        self.assertEqual((type(offering.bot).__name__, offering.queue), ("TeamsBot", None), "the queue is not used even when it is set")
        self.assertEqual(offering.bot.way, WAY)
        offering.bot.token()
        self.assertEqual(len(asked), 1)
        self.assertIn(f"client_id={IDENTITY}", asked[0], "the user-assigned identity of the bot is selected by its client id")
        self.assertIn("resource=api%3A%2F%2FAzureADTokenExchange", asked[0])
        self.assertEqual(fake.form()["client_assertion"], ASSERTION)

    def test_a_way_that_is_not_complete_is_off_whatever_else_is_set_and_no_call_is_made(self):
        for change in ({"TEAMS_BOT_APP_ID": ""}, {"TEAMS_DELIVERY": "banana"}):
            with self.subTest(change=change):
                extras, calls = self.extras({**ENV, **change, "TEAMS_CARDS_QUEUE": "teams-cards"})
                self.assertEqual((extras.on_cards(), calls), (0, []), "no card is tried, not even through the queue that is set: the letters go")

    def test_the_round_of_the_timer_sends_the_card_through_the_bot(self):
        world = BotWorld()
        world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        world.ready(cs.MAYA)
        with mock.patch.object(wiring, "Identity") as identity:
            identity.return_value.token = lambda resource, within=None: ASSERTION
            extras, _ = self.extras(ENV, transport=world.teams)
        extras.on_cards.__self__.store = world.store
        extras.on_cards.__self__.people = world.people
        extras.on_cards.__self__.clock = world.clock
        extras.on_cards.__self__.bot.clock = world.clock
        self.assertEqual(extras.on_cards(), 1)
        self.assertEqual(world.teams.steps(), ["token", "create", "send"])


class ASlowBotConnectorHoldsBackNothing(unittest.TestCase):
    """The round of cards runs before the letters in the same minute: the bot has 25 seconds for its calls (offers.ROUND_SECONDS), and what does not fit waits for the next round."""

    def slow(self, seconds, **steps):
        """A world whose calls take `seconds` of a clock that the test holds (the step that a name says, `steps`, takes what it says)."""
        self.world, self.now = BotWorld(), [1000.0]
        self.world.bot.client.monotonic = lambda: self.now[0]
        self.fast = self.world.bot.client.transport

        def transport(method, url, headers, data, timeout):
            answer = self.fast(method, url, headers, data, timeout)
            self.now[0] += steps.get(self.world.teams.calls[-1]["step"], seconds)
            return answer
        self.world.bot.client.transport = transport
        self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        self.world.ready(cs.MAYA, cs.ANNA)

    def test_a_card_that_does_not_fit_in_the_time_of_the_round_waits_for_the_next_round_and_uses_up_no_try(self):
        self.slow(1.0, send=24.0)
        self.world.run()
        self.assertEqual((self.world.teams.steps(), len(self.world.posted(cs.MAYA)), self.world.tries(cs.ANNA)), (["token", "create", "send"], 1, []))
        self.world.run()
        self.assertEqual((self.world.teams.steps(), len(self.world.posted(cs.ANNA))), (["token", "create", "send", "create", "send"], 1))
        self.assertEqual(offers.ROUND_SECONDS, 25)

    def test_a_post_that_would_get_less_than_ten_seconds_is_not_made_and_the_next_round_tries_the_card_again(self):
        self.slow(1.0, create=17.0)
        self.world.run()
        self.assertEqual(self.world.teams.steps(), ["token", "create", "create"], "no post: the time that is left of the round is less than a post is given")
        self.assertEqual([[(m.status, m.detail) for m in self.world.attempts(oid)] for oid in (cs.MAYA, cs.ANNA)], [[("failed", teamsbot.REASONS["network"])]] * 2,
                         "a card that was not posted is not a card that may have arrived")
        self.world.bot.client.transport = self.fast
        self.world.clock.advance(minutes=offers.RETRY_MINUTES + 1)
        self.world.run()
        self.assertEqual(([[m.status for m in self.world.attempts(oid)] for oid in (cs.MAYA, cs.ANNA)], self.world.teams.steps().count("send"), len(self.world.posted(cs.MAYA))),
                         ([["failed", "sent"]] * 2, 2, 1), "the conversation is made again, which Teams answers with the same one, and the card is posted once")

    def test_an_identity_that_stalls_costs_one_stall_for_the_round_and_every_due_card_its_try(self):
        self.slow(0.0)
        asked = []

        def stalls(resource, within=None):
            asked.append(within)
            took = 52.0 if within is None else min(52.0, within)  # the real identity gives up when the time that it was given is used up
            self.now[0] += took
            self.world.clock.advance(seconds=took)
            error = IdentityError("the managed identity endpoint gave no answer (TimeoutError) after 3 tries")
            error.transient = True
            raise error
        self.world.bot.assertion = stalls
        self.world.run()
        self.assertEqual(asked, [25.0], "the identity is given the time of the round, and only the first card asks it")
        self.assertEqual(self.now[0] - 1000.0, 25.0, "the letters that follow the cards in the same minute wait for the round and not for the stall")
        self.assertEqual([[m.detail for m in self.world.attempts(oid)] for oid in (cs.MAYA, cs.ANNA)], [[teamsbot.REASONS["network"]]] * 2, "every due card has its try, so the next round does not ask again")
        self.assertEqual(self.world.teams.calls, [])
        self.world.clock.advance(minutes=1)
        self.world.run()
        self.assertEqual(len(asked), 1, "nothing is due before the tries are fifteen minutes old")


class TheBlockOfTheOperationsPage(unittest.TestCase):
    def setUp(self):
        self.world = BotWorld()
        self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        self.world.ready(cs.MAYA, cs.ANNA)

    def status(self, **env):
        settings = loop_config.load({**ENV, **env})
        return offers.teams_status(settings, self.world.store, self.world.people, self.world.clock())

    def test_it_says_which_way_the_cards_go(self):
        self.assertIn("straight to Teams through the Bot Connector", self.status()[0])
        self.assertIn("queue that a flow of Power Automate reads", self.status(TEAMS_DELIVERY="queue", TEAMS_CARDS_QUEUE="teams-cards")[0])
        self.assertEqual(self.status(TEAMS_DELIVERY="queue")[0], "The Teams cards are off: no queue is set.")
        off = self.status(TEAMS_BOT_APP_ID="")[0]
        self.assertTrue(off.startswith("No Teams card is tried and the letters go instead: TEAMS_BOT_APP_ID is not set"), off)

    def test_the_last_result_is_ok_when_the_last_card_went(self):
        self.assertEqual(self.status()[1], "Last result: no card was tried in the last 3 days.")
        self.world.run()
        self.assertEqual(self.status()[1], "Last result: ok.")

    def test_the_last_result_counts_the_approvers_for_whom_the_app_is_not_installed_and_names_nobody(self):
        self.world.teams.replies["create"] = [answer(403, FORBIDDEN), answer(403, FORBIDDEN)]
        self.world.run()
        said = self.status()[1]
        self.assertEqual(said, "Last result: the Teams app is not installed for, or blocked by, 2 approvers.")
        for hidden in ("Maya", "Anna", "maya@", "anna@", cs.MAYA, cs.ANNA):
            self.assertNotIn(hidden, " ".join(self.status()))
        self.world.clock.advance(minutes=20)
        self.world.teams.replies["create"] = []
        self.world.run()
        self.assertEqual(self.status()[1], "Last result: ok.", "the latest card of each person counts, and the last one went")

    def test_an_identity_that_is_wrong_and_a_silence_are_told_in_their_own_words(self):
        self.world.teams.replies["token"] = [answer(401, {"error": "invalid_client", "error_description": "AADSTS7000229"})]
        self.world.run()
        self.assertEqual(self.status()[1], "Last result: identity error.")
        self.world.clock.advance(minutes=20)
        self.world.teams.replies["token"] = []
        self.world.teams.replies["create"] = [OSError("x")] * 3
        self.world.run()
        self.assertEqual(self.status()[1], "Last result: no answer from Teams.")

    def test_a_card_that_may_have_arrived_is_told_as_no_answer_from_teams(self):
        self.world.teams.replies["send"] = [OSError("x")] * 2
        self.world.run()
        self.assertEqual(self.status()[1], "Last result: no answer from Teams.")

    def test_a_card_of_the_queue_that_failed_is_a_card_that_was_not_sent_and_an_unreadable_store_is_said(self):
        self.world.store.mail_put(MailRecord("q1", cs.MAYA, offers.APPROVAL, "x", stamp(cs.START), "failed", None, "The queue did not accept the app's token."))
        self.assertEqual(self.status(TEAMS_DELIVERY="queue")[1], "Last result: the last card was not sent.")
        broken = mock.Mock(side_effect=OSError("down"))
        self.world.store.mails_since = broken
        with LogCapture():
            self.assertEqual(self.status()[1], "Last result: it cannot be read now.")

    def test_the_page_shows_the_two_sentences_in_one_block_and_has_no_block_without_them(self):
        console = Console()
        self.assertNotIn("Teams cards", console.get("/ops").content)
        console.services = dataclasses.replace(console.services, teams=lambda: ("The cards go straight to Teams.", "Last result: ok."))
        page = console.get("/ops")
        self.assertEqual(page.status, 200)
        self.assertEqual(page.content.count("Teams cards"), 1)
        self.assertIn("The cards go straight to Teams.", page.content)
        self.assertIn("Last result: ok.", page.content)

        def broken():
            raise OSError("down")
        console.services = dataclasses.replace(console.services, teams=broken)
        self.assertIn("I cannot tell now which way the Teams cards go.", console.get("/ops").content)


class TheTestCard(unittest.TestCase):
    OWNER = "aaaaaaaa-1111-4222-8333-444444444444"  # the owner of test_notify.ENV
    ID = "a" * 32
    ALLOWED = {"v", "ts", "runId", "requestId", "type", "step", "ok", "status", "aadsts", "code", "reason"}

    def setUp(self):
        self.teams, self.clock, self.asked = FakeTeams(), cs.Moving(), []
        self.store = MemoryStore(self.clock)

    def fetch(self, url, headers, timeout):
        self.asked.append(url)
        return 200, json.dumps({"access_token": ASSERTION, "expires_on": "4102444800"}).encode()

    def run_test(self, env=None, request_id=None):
        """Runs the test card with the settings of ENV and `env` on top; a setting whose value in `env` is None is not set at all."""
        env = {**ENV, "CONSOLE_PEOPLE": LOOP_ENV["CONSOLE_PEOPLE"], "IDENTITY_ENDPOINT": "http://localhost:8081/msi/token", "IDENTITY_HEADER": "h", **(env or {})}
        env = {name: value for name, value in env.items() if value is not None}
        with mock.patch.object(wiring, "build_store", return_value=self.store), LogCapture() as capture:
            ok = offers.card_test(env, request_id or self.ID, transport=self.teams, sleep=lambda s: None, monotonic=lambda: 0.0, clock=self.clock, fetch=self.fetch)
        return ok, capture.events(), "\n".join(capture.messages())

    def test_it_sends_one_test_card_to_the_owner_and_replaces_it_with_a_closing_card(self):
        ok, events, text = self.run_test()
        self.assertTrue(ok)
        self.assertEqual(self.teams.steps(), ["token", "create", "send", "update"])
        self.assertEqual(json.loads(self.teams.calls[1]["data"])["members"], [{"id": self.OWNER}])
        sent, closing = (json.loads(call["data"])["attachments"][0]["content"] for call in self.teams.calls[2:])
        self.assertIn("Test card from Meternaut: nothing to do.", cs.texts(sent))
        self.assertIn("Test card from Meternaut: closed, nothing to do.", cs.texts(closing))
        self.assertEqual([(e["type"], e.get("step"), e["ok"], e.get("status")) for e in events],
                         [("teams.test.step", "token", True, 200), ("teams.test.step", "create", True, 201), ("teams.test.step", "send", True, 201), ("teams.test.step", "update", True, 200),
                          ("teams.test.finished", None, True, None)])
        self.assertEqual({e["requestId"] for e in events}, {self.ID})
        self.assertTrue(any(f"client_id={IDENTITY}" in url for url in self.asked), "the identity of the bot is the one that gave the assertion")

    def test_the_history_holds_only_plain_words_and_numbers(self):
        for replies in ({}, {"create": [answer(403, FORBIDDEN)]}, {"token": [answer(400, {"error": "invalid_client", "error_description": "AADSTS700213 " + ACCESS})]}):
            with self.subTest(replies=list(replies)):
                self.teams.replies, self.teams.calls = replies, []
                ok, events, text = self.run_test()
                for event in events:
                    self.assertLessEqual(set(event), self.ALLOWED)
                self.assertNotRegex(text, r"https?:|@|[0-9a-f]{8}-[0-9a-f]{4}-|" + "|".join(re.escape(x) for x in (ACCESS, ASSERTION, CONVERSATION, ACTIVITY, "Bearer")))
                self.assertNotIn(self.OWNER, text)

    def test_what_teams_says_is_one_word_a_status_and_for_the_token_the_number_of_the_error(self):
        for step, status, body, fields in (("create", 403, FORBIDDEN, {"reason": "not-installed", "status": 403}), ("send", 403, WRITES_BLOCKED, {"reason": "blocked", "status": 403}),
                                           ("create", 401, None, {"reason": "unauthorized", "status": 401}), ("send", 429, None, {"reason": "throttled", "status": 429}),
                                           ("update", 404, None, {"reason": "other", "status": 404}), ("token", 400, {"error": "invalid_client", "error_description": "AADSTS700213: x"},
                                                                                                    {"reason": "unauthorized", "status": 400, "aadsts": 700213}),
                                           ("create", 503, None, {"reason": "network", "status": 503})):
            with self.subTest(step=step, status=status):
                self.teams.replies, self.teams.calls = {step: [answer(status, body, retry_after="3600")] * 3}, []
                ok, events, _ = self.run_test()
                self.assertFalse(ok)
                *steps, last = events
                self.assertEqual({k: v for k, v in steps[-1].items() if k in ("step", "ok", "reason", "status", "aadsts")}, {"step": step, "ok": False, **fields})
                self.assertEqual((last["type"], last["ok"]), ("teams.test.finished", False))
                self.assertEqual(self.teams.steps()[-1], step, "nothing is called after the step that failed")

    def test_a_step_that_teams_refused_says_the_code_word_that_teams_gave_and_nothing_else_of_its_answer(self):
        for body, code in CODES:
            with self.subTest(body=str(body)[:50]):
                self.fresh()
                self.teams.replies = {"create": [answer(403, body)]}
                ok, events, text = self.run_test()
                (line,) = [e for e in events if e["type"] == "teams.test.step" and e["step"] == "create"]
                self.assertEqual((ok, line["ok"], line["status"], line.get("code"), "code" in line), (False, False, 403, code or None, bool(code)))
                self.assertLessEqual(set(line), self.ALLOWED)
                self.assertNotRegex(text, r"https?:|@|[0-9a-f]{8}-[0-9a-f]{4}-|personal scope|Bot is not|Authorization has been|Access denied|html|subCode")

    def test_the_token_step_says_its_number_and_no_code_word_and_a_step_that_went_well_none_either(self):
        for body in ({"error": "invalid_client", "error_description": "AADSTS700213: x"}, {"error": {"code": "BadArgument", "message": "x"}}):
            with self.subTest(body=str(body)[:40]):
                self.fresh()
                self.teams.replies = {"token": [answer(400, body)]}
                _, events, _ = self.run_test()
                self.assertEqual(("code" in events[0], events[0].get("aadsts")), (False, 700213 if "error_description" in body else None))
        self.fresh()
        _, events, _ = self.run_test()
        self.assertEqual([e for e in events if "code" in e], [])

    def test_the_card_of_a_request_that_teams_refuses_for_a_code_that_is_not_known_keeps_the_plain_reason_and_no_code(self):
        world = BotWorld()
        world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        world.ready(cs.MAYA)
        world.teams.replies["create"] = [answer(403, BAD_ARGUMENT)]
        world.run()
        (record,) = world.attempts()
        self.assertEqual((record.status, record.detail), ("failed", teamsbot.REASONS["other"]))
        self.assertNotIn("BadArgument", json.dumps([dataclasses.asdict(m) for m in world.store.mails]), "the records of the real cards are what they were")

    def test_a_step_that_made_no_call_has_no_status(self):
        self.teams.replies = {}
        with mock.patch.object(wiring, "build_store", return_value=self.store):
            def broken(url, headers, timeout):
                raise OSError("no endpoint")
            with LogCapture() as capture:
                offers.card_test({**ENV, "CONSOLE_PEOPLE": LOOP_ENV["CONSOLE_PEOPLE"]}, self.ID, transport=self.teams, sleep=lambda s: None, clock=self.clock, fetch=broken)
        (step, finished) = [e for e in capture.events() if e["type"].startswith("teams.test")]
        self.assertEqual((step["step"], step["ok"], step["reason"], "status" in step, finished["ok"]), ("token", False, "unauthorized", False, False))

    DELIVERIES = (None, "", "queue", " Queue ", "bot", "BOT", "banana")  # not set, the default, the way of the loop, the way that the test proves, and a typo

    def fresh(self):
        self.teams.calls, self.teams.replies, self.asked, self.store = [], {}, [], MemoryStore(self.clock)

    def test_the_test_ignores_what_teams_delivery_says_so_that_the_bot_is_proved_before_it_is_switched_on(self):
        for delivery in self.DELIVERIES:
            with self.subTest(delivery=delivery):
                self.fresh()
                ok, events, _ = self.run_test({"TEAMS_DELIVERY": delivery})
                self.assertEqual((ok, self.teams.steps(), [(e["type"], e["ok"]) for e in events][-1]), (True, ["token", "create", "send", "update"], ("teams.test.finished", True)))
                self.assertEqual((self.teams.form()["client_id"], json.loads(self.teams.calls[1]["data"])["members"]), (APP, [{"id": self.OWNER}]), "the app registration of the bot and the owner")
                self.assertTrue(any(f"client_id={IDENTITY}" in url for url in self.asked), "the identity of the bot gave the assertion, whatever the delivery is")

    def test_the_address_of_the_bot_connector_may_be_empty_and_is_the_one_that_is_allowed_either_way(self):
        for url in (None, "", " HTTPS://SMBA.trafficmanager.net/teams "):
            with self.subTest(url=url):
                self.fresh()
                ok, _, _ = self.run_test({"TEAMS_DELIVERY": "queue", "TEAMS_SERVICE_URL": url})
                self.assertEqual((ok, {call["url"].rsplit("/v3/", 1)[0] for call in self.teams.calls[1:]}), (True, {"https://smba.trafficmanager.net/teams"}))

    def test_a_setting_of_the_bot_that_is_missing_or_wrong_is_off_whatever_the_delivery_says_and_nothing_at_all_is_called(self):
        no_sign_in = {name: None for name in SIGNIN}
        for change in ({"TEAMS_BOT_APP_ID": ""}, {"TEAMS_BOT_APP_ID": "not a guid"}, {"TEAMS_BOT_IDENTITY_CLIENT_ID": None}, {"TEAMS_BOT_IDENTITY_CLIENT_ID": "x" * 36},
                       {"TEAMS_SERVICE_URL": "http://smba.trafficmanager.net/teams/"}, {"TEAMS_SERVICE_URL": "https://evil.example/teams/"}, no_sign_in):
            for delivery in self.DELIVERIES:
                with self.subTest(change=sorted(change), delivery=delivery):
                    self.fresh()
                    ok, events, _ = self.run_test({**change, "TEAMS_DELIVERY": delivery})
                    self.assertEqual((ok, [(e["type"], e["ok"], e.get("reason")) for e in events], self.teams.calls, self.asked), (False, [("teams.test.finished", False, "off")], [], []))

    def test_a_switch_that_is_pulled_and_a_missing_owner_stop_the_test_whatever_the_delivery_says(self):
        no_owner = json.dumps([{"oid": cs.OMAR, "name": "Omar", "roles": ["ops"], "mail": "omar@example.com"}])
        for delivery in self.DELIVERIES:
            for env, reason, switch in (({}, "held", "messages"), ({}, "held", "all"), ({"CONSOLE_PEOPLE": no_owner}, "no-owner", None)):
                with self.subTest(delivery=delivery, reason=reason, switch=switch):
                    self.fresh()
                    if switch:
                        self.store.switch_put(SwitchRecord(name=switch, paused=True, by="Ops", at="2026-11-05T10:00:00Z"))
                    ok, events, _ = self.run_test({**env, "TEAMS_DELIVERY": delivery})
                    self.assertEqual((ok, [(e["type"], e["ok"], e.get("reason")) for e in events], self.teams.calls, self.asked), (False, [("teams.test.finished", False, reason)], [], []))

    def test_the_check_of_the_pipeline_reads_what_the_test_writes(self):
        """tools/teams-check.py, which the Hub action teams-test runs in the Operator, reads these History lines: the kinds, the steps and the words of the reasons are the same on both sides."""
        spec = importlib.util.spec_from_file_location("teams_check_of_the_app_tests", REPO_ROOT / "tools" / "teams-check.py")
        check = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = check
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(check)
        self.assertEqual((check.KIND_STEP, check.KIND_END, check.JOB, check.EVENT_PREFIX, set(check.REASONS)), (*history.TEAMS_KINDS, control.TEAMS_JOB, history.EVENT_PREFIX, set(teamsbot.REASONS)))

        def read(env=None, before=None, **replies):
            self.teams.replies, self.teams.calls, self.store = replies, [], MemoryStore(self.clock)
            if before:
                before()
            _, _, text = self.run_test(env)
            return check.result_lines([e for e in map(check.parse_event, text.splitlines()) if e and e["requestId"] == self.ID])

        lines, passed = read()
        self.assertTrue(passed, lines)
        denied = {"error": "invalid_client", "error_description": "AADSTS700213: x"}
        for step, status, body, reason, said in (("create", 403, FORBIDDEN, "not-installed", ""), ("send", 403, WRITES_BLOCKED, "blocked", ""), ("create", 401, None, "unauthorized", ""),
                                                 ("send", 429, None, "throttled", ""), ("update", 404, None, "other", ""), ("create", 503, None, "network", ""),
                                                 ("token", 400, denied, "unauthorized", "AADSTS700213")):
            with self.subTest(step=step, status=status):
                lines, passed = read(**{step: [answer(status, body, retry_after="3600")] * 3})
                self.assertFalse(passed)
                self.assertTrue(any(check.STEP_TITLES[step] in line and "NOT ok" in line and said in line and check.REASONS[reason] in line for line in lines), lines)
        lines, passed = read(create=[answer(403, BAD_ARGUMENT)])
        self.assertFalse(passed)
        self.assertTrue(any(check.STEP_TITLES["create"] in line and "NOT ok (HTTP 403, 4xx; Microsoft's error code: BadArgument); " + check.REASONS["other"] in line for line in lines), lines)
        lines, _ = read(create=[answer(403, {"error": {"code": TENANT, "message": "x"}})])
        self.assertEqual([line for line in lines if "error code" in line], [], "a code that is not letters alone is never printed")
        no_owner = json.dumps([{"oid": cs.OMAR, "name": "Omar", "roles": ["ops"], "mail": "omar@example.com"}])
        pull = (lambda: self.store.switch_put(SwitchRecord(name="all", paused=True, by="Ops", at="2026-11-05T10:00:00Z")))
        for env, before, reason in (({"TEAMS_BOT_APP_ID": ""}, None, "off"), ({"CONSOLE_PEOPLE": no_owner}, None, "no-owner"), ({}, pull, "held"), ({"CONSOLE_PEOPLE": "not json"}, None, "other")):
            with self.subTest(reason=reason):
                lines, passed = read(env, before)
                self.assertFalse(passed)
                self.assertIn(f"The cases app sent nothing: {check.FINISHED_REASONS[reason]}.", lines[-1])

    def test_a_card_that_cannot_be_made_after_the_token_and_the_conversation_still_ends_the_test_with_its_last_line(self):
        with mock.patch.object(cards, "probe_card", side_effect=cards.CardError("the card is wrong")):
            ok, events, _ = self.run_test()
        self.assertEqual((ok, self.teams.steps(), [(e["type"], e.get("step"), e["ok"], e.get("reason")) for e in events]),
                         (False, ["token", "create"], [("teams.test.step", "token", True, None), ("teams.test.step", "create", True, None), ("teams.test.finished", None, False, "other")]))

    def test_a_loop_that_is_not_set_up_is_one_plain_word_and_never_a_crash(self):
        with LogCapture() as capture:
            self.assertFalse(offers.card_test({}, self.ID, transport=self.teams, clock=self.clock))
        self.assertEqual([(e["type"], e["reason"]) for e in capture.events()], [("teams.test.finished", "off")])
        with LogCapture() as capture:
            self.assertFalse(offers.card_test({**ENV, "CONSOLE_PEOPLE": "not json"}, self.ID, transport=self.teams, clock=self.clock))
        self.assertEqual([(e["type"], e["reason"]) for e in capture.events()], [("teams.test.finished", "other")])
        self.assertEqual(self.teams.calls, [])


class TheControlMessage(unittest.TestCase):
    GOOD = {"job": "teams-card-test", "requestId": "b" * 32}

    def test_the_message_starts_the_test_for_its_request_and_nothing_else(self):
        teams, run, study = Recorder(), Recorder(), Recorder()
        self.assertTrue(control.handle_message(FakeMessage(self.GOOD), fixed_clock, run, study, teams=lambda request: teams.calls.append(request)))
        self.assertEqual((teams.calls, run.calls, study.calls), (["b" * 32], [], []))

    def test_a_message_that_names_a_recipient_or_anything_else_still_carries_no_choice(self):
        called = []
        control.handle_message(FakeMessage({**self.GOOD, "to": "anybody@example.com", "oid": cs.STRANGER}), fixed_clock, Recorder(), Recorder(), teams=called.append)
        self.assertEqual(called, ["b" * 32], "the app reads the job and the request id and nothing else")

    def test_an_old_message_is_refused_and_the_other_jobs_are_as_before(self):
        import datetime as dt
        from support import NOW
        called = []
        with LogCapture() as capture:
            started = control.handle_message(FakeMessage(self.GOOD, NOW - dt.timedelta(seconds=901)), fixed_clock, Recorder(), Recorder(), teams=called.append)
        self.assertEqual((started, called, capture.events()[0]["reason"]), (False, [], "stale control message"))
        run = Recorder()
        self.assertTrue(control.handle_message(FakeMessage({"job": "watch", "requestId": "c" * 32}), fixed_clock, run, Recorder(), teams=called.append))
        self.assertEqual((run.calls, called), ([("control", "c" * 32)], []))
        self.assertEqual(control.TEAMS_JOB, "teams-card-test")

    def test_without_a_function_of_its_own_the_message_runs_the_test_with_the_settings_of_the_app(self):
        with mock.patch.object(offers, "card_test") as card_test:
            control.handle_message(FakeMessage(self.GOOD), fixed_clock, Recorder(), Recorder())
        (call,) = card_test.call_args_list
        self.assertEqual((call.args[1], call.kwargs["clock"]), ("b" * 32, fixed_clock))


if __name__ == "__main__":
    unittest.main()
