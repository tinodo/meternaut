"""Quiet hours (cases/quiet.py): the window, the zone, and what the letters and the Teams cards do while it lasts.

Every clock here is a fake. A person's quiet hours hold every letter and every card: nothing is sent and nothing is written inside them, what is due is sent by the first round after them,
and nothing is lost or sent twice. No test touches the network.
"""
import datetime as dt
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import cardsupport as cs
from cases import alerts, loop_config, notify, quiet
from cases.models import MailRecord, SettingsRecord, SwitchRecord
from test_letters import make_action, make_case
from test_mail import Fixture as MailFixture
from test_notify import ENV, Fixture, TINO, plan

UTC = dt.timezone.utc


def at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def settings(start="", end="", zone="UTC", **more) -> SettingsRecord:
    return SettingsRecord(oid=TINO, quiet_from=start, quiet_to=end, timezone=zone, **more)


class TheWindow(unittest.TestCase):
    def test_no_quiet_hours_is_the_default_and_never_inside(self):
        record = SettingsRecord(oid=TINO)
        self.assertEqual((record.quiet_from, record.quiet_to), ("", ""))
        self.assertIsNone(quiet.window(record))
        self.assertFalse(any(quiet.inside(record, at(3, hour)) for hour in range(24)))
        self.assertIsNone(quiet.last_end(record, at(3, 12)))

    def test_only_two_different_times_of_the_form_hh_mm_make_a_window(self):
        for start, end in (("22:00", ""), ("", "07:00"), ("07:00", "07:00"), ("7:00", "08:00"), ("24:00", "08:00"), ("08:00", "noon"), ("08:00:00", "09:00")):
            with self.subTest(start=start, end=end):
                self.assertIsNone(quiet.window(settings(start, end)))
                self.assertFalse(quiet.inside(settings(start, end), at(3, 8, 30)))

    def test_a_window_that_stays_in_one_day_holds_its_start_and_not_its_end(self):
        record = settings("12:00", "13:00")
        self.assertEqual([quiet.inside(record, at(3, h, m)) for h, m in ((11, 59), (12, 0), (12, 30), (12, 59), (13, 0), (13, 1))], [False, True, True, True, False, False])

    def test_a_window_across_midnight_holds_the_night_on_both_sides_of_it(self):
        record = settings("22:00", "07:00")
        checks = {(21, 59): False, (22, 0): True, (23, 59): True, (0, 0): True, (3, 0): True, (6, 59): True, (7, 0): False, (7, 1): False, (12, 0): False}
        for (hour, minute), expected in checks.items():
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(quiet.inside(record, at(4, hour, minute)), expected)

    def test_the_hours_follow_the_clock_of_the_persons_zone_and_utc_is_the_zone_when_there_is_none(self):
        plus_two = dt.timezone(dt.timedelta(hours=2))
        with mock.patch.object(quiet, "zone_for", return_value=plus_two):
            record = settings("22:00", "07:00", zone="Anywhere/Seen")
            self.assertEqual([quiet.inside(record, at(3, h, m)) for h, m in ((19, 59), (20, 0), (20, 30), (4, 59), (5, 0))], [False, True, True, True, False])
        for name in ("", "Mars/Olympus_Mons", "../../etc/passwd", None):
            with self.subTest(zone=name):
                self.assertEqual(quiet.zone_for(name), UTC)
        self.assertEqual(quiet.zone_for("UTC"), UTC)
        self.assertTrue(quiet.inside(settings("22:00", "07:00", zone=""), at(3, 23)))
        self.assertFalse(quiet.inside(settings("22:00", "07:00", zone="Mars/Olympus_Mons"), at(3, 12)))

    def test_a_clock_change_moves_the_hours_with_the_wall_clock(self):
        try:
            import zoneinfo
            zoneinfo.ZoneInfo("Europe/Amsterdam")
        except Exception:  # noqa: BLE001
            self.skipTest("this machine has no time zone database")
        record = settings("01:30", "03:30", zone="Europe/Amsterdam")  # the clocks went from 02:00 to 03:00 at 01:00 UTC on Sunday 29 March 2026
        spring = dt.datetime(2026, 3, 29, tzinfo=UTC)
        self.assertEqual([quiet.inside(record, spring + dt.timedelta(hours=h, minutes=m)) for h, m in ((0, 15), (0, 45), (1, 0), (1, 29), (1, 30), (2, 0))],
                         [False, True, True, True, False, False])
        autumn = dt.datetime(2026, 10, 25, tzinfo=UTC)  # 03:00 became 02:00 at 01:00 UTC: the wall clock showed 02:30 twice
        wide = settings("02:15", "02:45", zone="Europe/Amsterdam")
        self.assertEqual([quiet.inside(wide, autumn + dt.timedelta(hours=h, minutes=m)) for h, m in ((0, 20), (0, 50), (1, 20), (1, 50))], [True, False, True, False])

    def test_the_last_end_is_the_most_recent_end_of_the_window_and_none_inside_it(self):
        record = settings("22:00", "07:00")
        self.assertIsNone(quiet.last_end(record, at(4, 3)))
        self.assertEqual(quiet.last_end(record, at(4, 7, 0)), at(4, 7, 0))
        self.assertEqual(quiet.last_end(record, at(4, 20)), at(4, 7, 0))
        self.assertIsNone(quiet.last_end(record, at(4, 1)))
        with mock.patch.object(quiet, "zone_for", return_value=dt.timezone(dt.timedelta(hours=2))):
            self.assertEqual(quiet.last_end(record, at(4, 9)), at(4, 5, 0), "07:00 at +02:00 is 05:00 UTC")


class Rig(Fixture):
    """The hooks of the letters over a store with a fake clock, and the hook that sends what the hours held back."""

    def __init__(self):
        super().__init__()
        loop = loop_config.load(ENV)
        options = dict(transport=self.graph, sleep=lambda s: None, monotonic=lambda: 0.0, clock=self.clock)
        self.waiting = notify.waiting_hook(loop, self.store, self.people, lambda resource: "tok", lambda text: text, **options)
        self.alert = notify.alert_hook(loop, self.store, self.people, lambda resource: "tok", lambda text: text, **options)

    def go(self, moment: dt.datetime) -> None:
        self.clock.now = moment

    def rounds(self, start: dt.datetime, end: dt.datetime, step: int = 1, request=None) -> int:
        """The timer's round (the letters about an open request) every `step` minutes from `start` up to, and not including, `end`; returns how many rounds it made."""
        count, moment = 0, start
        while moment < end:
            self.go(moment)
            self.on_plan(request or plan(), make_case())
            count, moment = count + 1, moment + dt.timedelta(minutes=step)
        return count


class TheLettersWait(unittest.TestCase):
    def setUp(self):
        self.f = Rig()
        self.f.store.settings_put(settings("22:00", "07:00"))

    def test_nothing_is_sent_or_written_all_night_and_the_first_round_after_it_sends_each_letter_once(self):
        made = self.f.rounds(at(3, 22), at(4, 7))
        self.assertEqual(made, 9 * 60)
        self.assertEqual((self.f.graph.sent, self.f.store.mails), ([], []), "no letter, and no record of a try: waiting uses up no try of the twelve")
        self.f.go(at(4, 7))
        self.f.on_plan(plan(), make_case())
        self.assertEqual(sorted(kind for kind, _, _ in self.f.records()), ["approval", "first_contact"])
        self.assertEqual({status for _, status, _ in self.f.records()}, {"sent"})
        self.f.rounds(at(4, 7, 1), at(4, 12))
        self.assertEqual(len(self.f.graph.sent), 2, "what was sent is not sent again")

    def test_the_start_of_the_hours_holds_a_letter_that_was_due_a_minute_before_and_a_letter_before_it_goes(self):
        self.f.go(at(3, 21, 59))
        self.f.on_plan(plan(), make_case())
        self.assertEqual(len(self.f.graph.sent), 2)
        other = plan(plan_id="p2", case_id="c2")
        self.f.go(at(3, 22))
        self.f.on_plan(other, make_case(case_id="c2"))
        self.assertEqual(len(self.f.graph.sent), 2, "the second request waits for the morning")
        self.f.go(at(4, 7))
        self.f.on_plan(other, make_case(case_id="c2"))
        self.assertEqual(self.f.graph.subjects()[-1], self.f.graph.subjects()[1], "its approval letter is the one that goes")
        self.assertEqual(len(self.f.graph.sent), 3)

    def test_the_letter_about_a_change_waits_too_and_every_kind_goes_once(self):
        action = make_action(state="done", finished_at="2026-11-03T21:00:00Z")
        self.f.go(at(3, 23))
        self.f.on_action(action, plan(state="consumed"), make_case())
        self.assertEqual((self.f.graph.sent, self.f.store.mails), ([], []))
        self.f.go(at(4, 7))
        self.f.on_action(action, plan(state="consumed"), make_case())
        self.f.on_action(action, plan(state="consumed"), make_case())
        self.assertEqual([kind for kind, _, _ in self.f.records()], ["notice"])

    def test_a_person_who_changes_the_hours_while_a_letter_waits_gets_it_at_the_next_round(self):
        self.f.rounds(at(3, 23), at(3, 23, 10))
        self.assertEqual(self.f.graph.sent, [])
        self.f.store.settings_put(settings("", ""))  # no quiet hours any more
        self.f.go(at(3, 23, 10))
        self.f.on_plan(plan(), make_case())
        self.assertEqual(len(self.f.graph.sent), 2)

    def test_hours_that_move_away_from_the_moment_let_the_letter_go_and_hours_that_move_over_it_hold_it(self):
        self.f.store.settings_put(settings("08:00", "09:00"))  # 23:00 is outside the new window
        self.f.go(at(3, 23))
        self.f.on_plan(plan(), make_case())
        self.assertEqual(len(self.f.graph.sent), 2)
        other = plan(plan_id="p2", case_id="c2")
        self.f.store.settings_put(settings("23:00", "23:30"))  # the same moment is inside the new window
        self.f.on_plan(other, make_case(case_id="c2"))
        self.assertEqual(len(self.f.graph.sent), 2)
        self.f.go(at(3, 23, 30))
        self.f.on_plan(other, make_case(case_id="c2"))
        self.assertEqual(len(self.f.graph.sent), 3)

    def test_the_hours_follow_the_persons_own_zone(self):
        self.f.store.settings_put(settings("22:00", "07:00", zone="Somewhere/Plus-two"))
        with mock.patch.object(quiet, "zone_for", return_value=dt.timezone(dt.timedelta(hours=2))):
            self.f.rounds(at(3, 20, 0), at(3, 21, 0), 15)  # 22:00 to 23:00 there
            self.f.rounds(at(4, 4, 0), at(4, 5, 0), 15)  # 06:00 to 07:00 there
            self.assertEqual(self.f.graph.sent, [])
            self.f.go(at(4, 5, 0))
            self.f.on_plan(plan(), make_case())
            self.assertEqual(len(self.f.graph.sent), 2)

    def test_the_mailer_holds_every_kind_for_the_hours_in_its_own_words_for_a_caller_that_does_not_look_first(self):
        fixture = MailFixture(now=at(5, 23))
        fixture.settings(quiet_from="22:00", quiet_to="07:00", timezone="UTC")
        for kind in ("approval", "first_contact", "notice", "verified", "digest", "alert", "reminder"):
            with self.subTest(kind=kind):
                result = fixture.send(kind=kind)
                self.assertEqual((result.status, result.detail), ("held", quiet.WAITING))
        self.assertEqual(fixture.graph.calls, [])
        self.assertEqual(fixture.tokens, [])
        fixture.now = at(6, 7)
        self.assertEqual(fixture.send(kind="approval").status, "sent")


class TheLettersThatNothingElseOffersAgain(unittest.TestCase):
    def setUp(self):
        self.f = Rig()
        self.f.store.plan_put(plan())
        self.f.store.case_put(make_case())

    def digests(self):
        return [m for m in self.f.graph.sent if "decision" in m[1]["subject"] and "wait" in m[1]["subject"]]

    def test_the_weekly_summary_that_the_hours_held_is_sent_once_after_them(self):
        self.f.store.settings_put(settings("08:00", "12:00"))
        self.f.go(at(3, 10))  # a Tuesday, the desk day, inside the hours
        self.f.on_run(None)
        self.assertEqual(self.f.graph.sent, [])
        self.assertEqual([(m.kind, m.status, m.detail) for m in self.f.store.mails], [("digest", "held", quiet.WAITING)])
        for minute in range(0, 120, 7):
            self.f.go(at(3, 10) + dt.timedelta(minutes=minute))
            self.f.waiting()
        self.assertEqual(self.f.graph.sent, [], "nothing during the hours")
        self.f.go(at(3, 12))
        self.f.waiting()
        self.f.waiting()
        self.f.go(at(3, 12, 30))
        self.f.waiting()
        self.assertEqual(len(self.digests()), 1, "once")
        self.assertEqual([m.status for m in self.f.store.mails if m.kind == "digest"], ["held", "sent"])

    def test_a_summary_for_which_nothing_waits_any_more_is_not_sent(self):
        self.f.store.settings_put(settings("08:00", "12:00"))
        self.f.go(at(3, 10))
        self.f.on_run(None)
        self.f.store.plan_put(plan(state="declined"))
        self.f.go(at(3, 12))
        self.f.waiting()
        self.assertEqual(self.f.graph.sent, [])

    def test_a_summary_that_was_not_held_is_not_made_again(self):
        self.f.go(at(3, 10))
        self.f.on_run(None)
        self.assertEqual(len(self.digests()), 1)
        self.f.go(at(3, 12))
        self.f.waiting()
        self.assertEqual(len(self.digests()), 1)

    def test_the_letter_of_a_trip_waits_for_the_owner_and_is_sent_once_after_the_hours(self):
        self.f.store.settings_put(settings("08:00", "12:00"))
        self.f.store.switch_put(SwitchRecord(name="investigation", paused=True, by="harness", at="2026-11-03T09:00:00Z", reason=alerts.switch_reason("tokens")))
        self.f.go(at(3, 10))
        self.f.alert("tokens", "an agent used 90000 tokens")
        self.assertEqual(self.f.graph.sent, [])
        self.assertEqual([(m.kind, m.status) for m in self.f.store.mails], [("alert", "held")])
        self.f.waiting()
        self.assertEqual(self.f.graph.sent, [])
        self.f.go(at(3, 12))
        self.f.waiting()
        self.f.waiting()
        (letter,) = self.f.graph.sent
        self.assertEqual(letter[1]["subject"], alerts.SUBJECT)
        self.assertIn("used up the token budget", letter[1]["body"]["content"])
        self.assertNotIn("90000", letter[1]["body"]["content"], "the detail was in the first letter and is not kept for the second")

    def test_a_trip_that_a_person_released_while_the_hours_lasted_is_not_told_after_them(self):
        self.f.store.settings_put(settings("08:00", "12:00"))
        self.f.store.switch_put(SwitchRecord(name="investigation", paused=True, by="harness", at="2026-11-03T09:00:00Z", reason=alerts.switch_reason("tokens")))
        self.f.go(at(3, 10))
        self.f.alert("tokens", "")
        self.f.store.switch_put(SwitchRecord(name="investigation", paused=False, by="Tino", at="2026-11-03T11:00:00Z"))
        self.f.go(at(3, 12))
        self.f.waiting()
        self.assertEqual(self.f.graph.sent, [])

    def test_only_the_owner_is_told_of_a_trip(self):
        self.f.store.switch_put(SwitchRecord(name="investigation", paused=True, by="harness", at="2026-11-03T09:00:00Z", reason=alerts.switch_reason("drift")))
        self.f.go(at(3, 10))
        self.f.alert("drift", "")
        self.assertEqual(self.f.graph.to(), ["tino@example.com"])


class TheTeamsCardsWait(unittest.TestCase):
    def setUp(self):
        self.world = cs.World()
        self.fake = self.world.queue_fake
        self.world.open_plan(cs.advice_plan(expires_at="2026-12-01T00:00:00Z"))
        self.world.channel(cs.MAYA, "teams", quiet_from="22:00", quiet_to="07:00", timezone="UTC")
        self.world.introduce(cs.MAYA)

    def run_round(self) -> int:
        return self.world.run()

    def tries(self):
        return self.world.tries()

    def test_no_card_is_sent_or_written_inside_the_hours_and_one_goes_when_they_end(self):
        for start, hours in ((cs.START.replace(hour=22, minute=0), 9),):
            self.world.clock.now = start
            for _ in range(hours * 4):
                self.assertEqual(self.run_round(), 0)
                self.world.clock.advance(minutes=15)
        self.assertEqual((self.fake.calls, self.tries()), ([], []), "no try was made and none was written")
        self.assertEqual(self.world.clock.now, cs.START.replace(day=cs.START.day + 1, hour=7, minute=0))
        self.assertEqual(self.run_round(), 1)
        self.assertEqual(self.run_round(), 0)
        self.assertEqual([(m.kind, m.status) for m in self.tries()], [("advice-card", "sent")])
        self.assertEqual(len(self.fake.cards()), 1)

    def test_a_person_who_changes_the_hours_while_a_card_waits_gets_it_at_the_next_round(self):
        self.world.clock.now = cs.START.replace(hour=23)
        self.assertEqual(self.run_round(), 0)
        self.world.channel(cs.MAYA, "teams", quiet_from="", quiet_to="")
        self.assertEqual(self.run_round(), 1)

    def test_the_card_of_a_change_and_the_card_of_its_result_wait_in_the_same_way(self):
        self.world.channel(cs.MAYA, "teams", quiet_from="22:00", quiet_to="07:00", timezone="UTC")
        self.world.open_plan(cs.change_plan("p3change", case_id="c3", expires_at="2026-12-01T00:00:00Z"))
        self.world.clock.now = cs.START.replace(hour=23)
        self.assertEqual(self.run_round(), 0)
        self.assertEqual(self.tries(), [])

    def test_the_introduction_waits_too(self):
        self.world.store.mails[:] = []
        self.world.clock.now = cs.START.replace(hour=23)
        self.assertEqual(self.run_round(), 0)
        self.assertEqual((self.fake.calls, self.world.store.mails), ([], []))
        self.world.clock.now = cs.START.replace(day=cs.START.day + 1, hour=7)
        self.assertEqual(self.run_round(), 2)
        self.assertEqual([m.kind for m in self.world.store.mails], ["first-contact-card", "advice-card"])


class TheLetterOfAPersonWhoChoseTeams(unittest.TestCase):
    """The card has its twenty minutes after the hours end, so that the letter does not overtake it and a request is never told twice."""

    def setUp(self):
        self.f = Rig()
        self.f.store.settings_put(settings("22:00", "07:00", channel="teams"))
        self.request = plan(created_at="2026-11-03T23:00:00Z")

    def test_the_letter_waits_for_twenty_minutes_after_the_hours_when_no_card_went(self):
        self.f.rounds(at(3, 23), at(4, 7), 30, self.request)
        self.assertEqual(self.f.graph.sent, [])
        for moment in (at(4, 7, 0), at(4, 7, 10), at(4, 7, 19)):
            self.f.go(moment)
            self.f.on_plan(self.request, make_case())
        self.assertEqual(self.f.graph.sent, [], "the card has the first go")
        self.f.go(at(4, 7, 20))
        self.f.on_plan(self.request, make_case())
        self.assertEqual(sorted(kind for kind, _, _ in self.f.records()), ["approval", "first_contact"])

    def test_no_letter_goes_when_the_card_went_after_the_hours(self):
        self.f.go(at(4, 7, 5))
        self.f.store.mail_put(MailRecord("c1", TINO, "approval-card", "[Meternaut] A change to Azure waits for your OK", "2026-11-04T07:05:00Z", "sent", self.request.plan_id, ""))
        self.f.go(at(4, 8))
        self.f.on_plan(self.request, make_case())
        self.assertNotIn("approval", [kind for kind, _, _ in self.f.records()], "the approval went as a card, so no letter of the same request goes")


if __name__ == "__main__":
    unittest.main()
