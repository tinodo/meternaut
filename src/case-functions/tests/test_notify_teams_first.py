"""The letter and the card of a person who chose Teams (cases/notify.py): the card goes first, and the letter follows only when no card was sent in the first twenty minutes.

The cards themselves are the bot app's (cases/offers.py); here only the rule of the letters is held: what the letter looks at, and that it is the fallback in every case that cannot be read.
"""
import datetime as dt
import unittest

import support  # noqa: F401  (puts the app on the path)
from cases import notify
from cases.memory_store import stamp
from cases.models import MailRecord, SettingsRecord
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


if __name__ == "__main__":
    unittest.main()
