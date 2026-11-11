"""The letter and the card of a person who chose Teams (cases/notify.py): the card goes first, and the letter follows only when no card was sent in the first twenty minutes.

The cards themselves are made and put on the queue by cases/offers.py; here only the rule of the letters is held: what the letter looks at, that it is the fallback in every case that cannot be
read, and that a card that the queue did not take leaves the letter to go.
"""
import datetime as dt
import unittest

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import notify, offers, teamsqueue
from cases.http import Client
from cases.memory_store import stamp
from cases.models import MailRecord, SettingsRecord
from cases.redact import Redactor
from test_letters import make_action, make_case
from test_notify import TINO, TUESDAY, Fixture, plan

LONG_AGO = stamp(TUESDAY - dt.timedelta(minutes=notify.TEAMS_FIRST_MINUTES + 1))
JUST_NOW = stamp(TUESDAY - dt.timedelta(minutes=2))


def card(kind: str, status: str = "sent", plan_id: str | None = "p1a2b3c4d5", mail_id: str = "card1") -> MailRecord:
    return MailRecord(mail_id, TINO, kind, "[Meternaut] x", stamp(TUESDAY - dt.timedelta(minutes=1)), status, plan_id, "")


class TheCardHasTheFirstGo(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.f.store.settings_put(SettingsRecord(oid=TINO, channel="teams"))

    def kinds(self):
        return sorted(m.kind for m in self.f.store.mails if m.status == "sent" and not m.kind.endswith("-card"))

    def test_while_the_card_has_its_time_no_letter_is_sent_and_nothing_is_written(self):
        self.f.on_plan(plan(created_at=JUST_NOW), make_case())
        self.assertEqual((self.f.graph.sent, self.f.store.mails), ([], []))

    def test_when_no_card_was_sent_in_twenty_minutes_the_letter_follows(self):
        self.f.on_plan(plan(created_at=LONG_AGO), make_case())
        self.assertEqual(self.kinds(), ["approval", "first_contact"])

    def test_a_card_that_was_sent_means_that_no_letter_is_ever_sent_for_the_request(self):
        self.f.store.mail_put(card("approval-card"))
        self.f.store.mail_put(card("first-contact-card", plan_id=None, mail_id="card2"))
        self.f.on_plan(plan(created_at=LONG_AGO), make_case())
        self.f.on_plan(plan(created_at=JUST_NOW), make_case())
        self.assertEqual(self.f.graph.sent, [])

    def test_the_card_of_another_request_does_not_count(self):
        self.f.store.mail_put(card("approval-card", plan_id="another"))
        self.f.on_plan(plan(created_at=LONG_AGO), make_case())
        self.assertIn("approval", self.kinds())

    def test_a_card_that_was_held_or_failed_does_not_stop_the_letter_after_the_time(self):
        for status in ("held", "failed", "refused"):
            self.f.store.mails.clear()
            self.f.store.mail_put(card("approval-card", status))
            self.f.on_plan(plan(created_at=LONG_AGO), make_case())
            self.assertIn("approval", self.kinds(), status)

    def test_a_person_who_chose_e_mail_or_the_weekly_summary_gets_the_letter_at_once_as_before(self):
        self.f.store.settings_put(SettingsRecord(oid=TINO, channel="email"))
        self.f.on_plan(plan(created_at=JUST_NOW), make_case())
        self.assertEqual(self.kinds(), ["approval", "first_contact"])
        self.f.store.mails.clear()
        self.f.store.settings_put(SettingsRecord(oid=TINO, channel="desk"))
        self.f.on_plan(plan(created_at=JUST_NOW), make_case())
        self.assertEqual({m.status for m in self.f.store.mails}, {"held"}, "the weekly summary holds the letter, as it always did")

    def test_a_channel_that_cannot_be_read_does_not_hold_the_letter_back_for_a_card(self):
        def broken(oid):
            raise RuntimeError("down")
        self.f.store.settings_get = broken
        self.f.on_plan(plan(created_at=JUST_NOW), make_case())
        self.assertEqual(sorted(m.kind for m in self.f.store.mails), ["approval", "first_contact"], "the mailer was reached: its own checks hold the letter, and say so in a record")
        self.assertEqual({m.status for m in self.f.store.mails}, {"held"})

    def test_the_letters_about_a_change_follow_the_same_rule(self):
        done = make_action(finished_at=JUST_NOW)
        self.f.on_action(done, plan(), make_case())
        self.assertEqual(self.f.graph.sent, [])
        self.f.on_action(make_action(finished_at=LONG_AGO), plan(), make_case())
        self.assertEqual(self.kinds(), ["notice"])

    def test_a_card_about_a_change_that_was_sent_means_no_letter_about_it(self):
        self.f.store.mail_put(card("notice-card"))
        self.f.on_action(make_action(finished_at=LONG_AGO), plan(), make_case())
        self.assertEqual(self.f.graph.sent, [])
        self.f.on_action(make_action(state="verified", finished_at=LONG_AGO), plan(), make_case())
        self.assertEqual(self.kinds(), ["verified"], "the card of the check afterwards did not go, so its letter does")

    def test_a_result_that_stays_unknown_has_no_card_so_its_letter_goes_to_a_person_who_chose_teams_when_it_is_due(self):
        self.f.on_action(make_action(state="unknown", finished_at=LONG_AGO), plan(), make_case())
        self.assertEqual(self.f.graph.sent, [], "it has not stayed unknown long enough")
        self.f.on_action(make_action(state="unknown", finished_at=stamp(TUESDAY - dt.timedelta(hours=notify.UNKNOWN_HOURS))), plan(), make_case())
        self.assertEqual(self.kinds(), ["unsure"])


class TheLetterIsTheFallbackOfACardThatTheQueueDidNotTake(unittest.TestCase):
    """The round of cards (cases/offers.py) and the hooks of the letters (cases/notify.py) on one store: a failed put on the queue is a failed try, and the letter goes."""

    def setUp(self):
        self.f = Fixture()
        self.f.store.settings_put(SettingsRecord(oid=TINO, channel="teams"))
        self.fake = cs.FakeQueue()
        client = Client(teamsqueue.queue_calls(cs.ACCOUNT, cs.QUEUE), Redactor(), transport=self.fake, sleep=lambda seconds: None)
        queue = teamsqueue.CardQueue(client, lambda resource: cs.STORAGE_TOKEN, cs.ACCOUNT, cs.QUEUE, Redactor(), self.f.clock)
        self.offers = offers.Offers(self.f.store, self.f.people, queue, "https://func.example.net", self.f.clock, Redactor())
        self.request = plan(created_at=JUST_NOW, expires_at="2026-12-01T00:00:00Z")
        self.f.store.plan_put(self.request)
        self.f.store.case_put(make_case(case_id=self.request.case_id))

    def letters(self):
        return sorted(m.kind for m in self.f.store.mails if m.status == "sent" and not m.kind.endswith("-card"))

    def test_a_put_that_failed_leaves_the_letter_to_go_after_the_twenty_minutes_and_not_before(self):
        self.fake.replies = [403]
        self.assertEqual(self.offers.run(), 1)
        self.assertEqual([(m.kind, m.status) for m in self.f.store.mails], [("first-contact-card", "failed")])
        self.f.on_plan(self.request, make_case(case_id=self.request.case_id))
        self.assertEqual((self.letters(), self.f.graph.sent), ([], []), "the card has its twenty minutes")
        self.f.clock.now += dt.timedelta(minutes=notify.TEAMS_FIRST_MINUTES - 1)
        self.f.on_plan(self.request, make_case(case_id=self.request.case_id))
        self.assertEqual(self.letters(), ["approval", "first_contact"], "no card was sent in twenty minutes, so the letter goes")
        calls = len(self.fake.calls)
        self.f.clock.now += dt.timedelta(hours=1)
        self.assertEqual(self.offers.run(), 0, "a letter went for the request: no card follows it")
        self.assertEqual(len(self.fake.calls), calls)

    def test_a_card_that_was_put_on_the_queue_means_that_no_letter_follows(self):
        self.assertEqual(self.offers.run(), 2)
        self.assertEqual([(m.kind, m.status) for m in self.f.store.mails], [("first-contact-card", "sent"), ("approval-card", "sent")])
        self.f.clock.now += dt.timedelta(hours=1)
        self.f.on_plan(self.request, make_case(case_id=self.request.case_id))
        self.assertEqual((self.letters(), self.f.graph.sent), ([], []), "the app cannot tell that the card arrived: the queue took it, which is what the letter looks at")


if __name__ == "__main__":
    unittest.main()
