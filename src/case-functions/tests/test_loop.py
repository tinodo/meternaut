import datetime as dt
import logging
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from support import ENV, Ticker

from cases import loop
from cases.memory_store import MemoryStore
from cases.store import TableStore

from test_loop_end_to_end import LOOP_ENV, fetch
from test_store import FakeTables
from test_web_support import NOW, at, make_action, make_case, make_plan

HOUR = dt.datetime(2026, 11, 5, 11, 0, 0, tzinfo=dt.timezone.utc)


class TheLettersOfAnApprovalThatWaitsForTheExtraCheck(unittest.TestCase):
    """A plan that was approved, whose change waits in the queue for the approver's extra sign-in check, is not a plan that waits for an OK and not a change that ended: the timer
    offers no letter for it. When the change ends as failed, it offers the one letter about a change that did not run, as for any other change."""

    def setUp(self):
        self.store = MemoryStore(clock=lambda: NOW)
        self.plan = make_plan(state="approved")
        self.action = make_action(state="queued", step_up=True, result="waits for the check")
        self.store.plan_put(self.plan)
        self.store.case_put(make_case(status="approved", plan_id="plan0001"))
        self.store.action_put(self.action)
        self.offered = []
        self.extras = SimpleNamespace(store=self.store, on_plan=lambda plan, case: self.offered.append(("plan", plan.state)),
                                      on_action=lambda action, plan, case: self.offered.append(("action", action.state, plan.state)))

    def remind(self, **later):
        loop._remind(self.extras, lambda: NOW + dt.timedelta(**later), lambda text: text)

    def test_no_letter_is_offered_while_the_change_waits(self):
        for minutes in (0, 5, 9):
            self.remind(minutes=minutes)
        self.assertEqual(self.offered, [])

    def test_a_change_that_ends_as_failed_is_offered_once_per_round_and_the_hook_sends_it_once(self):
        self.store.action_put(replace(self.action, state="failed", finished_at=at(), result="not completed", error="not completed"))
        self.store.plan_put(replace(self.plan, state="failed"))
        self.remind()
        self.assertEqual(self.offered, [("action", "failed", "failed")], "a plan that is closed is not offered as one that waits for an OK")
        self.remind(minutes=1)
        self.assertEqual([entry[0] for entry in self.offered], ["action", "action"], "each round offers it; the hook sends a letter that is due only")

    def test_a_plan_that_waits_for_an_ok_is_still_offered_and_one_that_is_approved_is_not(self):
        self.store.plan_put(replace(self.plan, state="open"))
        self.remind()
        self.assertEqual(self.offered, [("plan", "open")])


class TheLettersOfAResultThatIsNotKnown(unittest.TestCase):
    """A change whose result is not known (Azure accepted it and the resource does not show it) is offered to the hook of the letters like one that ran or failed, for the same three days.
    The hook decides when its letter is due (test_notify)."""

    def setUp(self):
        self.store = MemoryStore(clock=lambda: NOW)
        self.store.plan_put(make_plan(state="consumed"))
        self.store.case_put(make_case(status="running", plan_id="plan0001"))
        self.store.action_put(make_action(state="unknown", finished_at=at(hours=-3), result="Azure accepted the change and has not shown its end."))
        self.offered = []
        self.extras = SimpleNamespace(store=self.store, on_plan=lambda plan, case: None,
                                      on_action=lambda action, plan, case: self.offered.append((action.state, plan.state)))

    def remind(self, **later):
        loop._remind(self.extras, lambda: NOW + dt.timedelta(**later), lambda text: text)

    def test_it_is_offered_each_round_and_the_hook_sends_one_letter_only(self):
        self.remind()
        self.remind(minutes=1)
        self.assertEqual(self.offered, [("unknown", "consumed")] * 2)

    def test_it_is_not_offered_once_the_three_days_are_over(self):
        self.remind(days=loop.LETTER_DAYS - 1, hours=20)
        self.assertEqual(len(self.offered), 1)
        self.remind(days=loop.LETTER_DAYS)
        self.assertEqual(len(self.offered), 1, "the three days count from when it became unknown (here three hours before NOW)")


class TheTimer(unittest.TestCase):
    def setUp(self):
        self.tables = FakeTables()
        self.calls = []

        def transport(method, url, headers, data, timeout):
            self.calls.append((method, url))
            return self.tables.transport(method, url, headers, data, timeout)

        self.transport = transport

    def tick(self, env, at):
        return loop.tick(dict(env), transport=self.transport, sleep=lambda s: None, monotonic=Ticker(), clock=lambda: at, fetch=fetch)

    def test_it_does_nothing_and_says_nothing_when_the_loop_is_not_set_up(self):
        self.assertIsNone(self.tick(ENV, HOUR))
        self.assertEqual(self.calls, [])

    def test_a_half_set_up_loop_is_logged_and_the_next_minute_tries_again(self):
        with self.assertLogs("meternaut.loop", level=logging.ERROR) as logged:
            self.assertIsNone(self.tick({**ENV, "STORE_ACCOUNT_NAME": "stexample"}, HOUR))
        self.assertIn("the tick failed: LoopConfigError", logged.output[0])
        self.assertEqual(self.calls, [])

    def test_a_round_with_nothing_to_do_only_reads_and_makes_no_table(self):
        result = self.tick(LOOP_ENV, HOUR)
        self.assertEqual((result.expired, result.finished, result.verified), ([], [], []))
        self.assertEqual({m for m, _ in self.calls}, {"GET"})
        self.assertEqual(self.tables.tables, {})

    def test_the_used_form_tokens_are_cleared_in_the_first_minute_of_an_hour_only(self):
        with mock.patch.object(TableStore, "nonces_purge") as purge:
            self.tick(LOOP_ENV, HOUR)
            self.tick(LOOP_ENV, HOUR + dt.timedelta(minutes=1))
            self.tick(LOOP_ENV, HOUR + dt.timedelta(minutes=59))
            self.tick(LOOP_ENV, HOUR + dt.timedelta(hours=1))
        self.assertEqual(purge.call_count, 2)

    def test_the_timer_says_at_most_once_an_hour_why_the_bot_way_is_off_and_never_the_value_of_a_setting(self):
        loop._teams_off_said.clear()
        self.addCleanup(loop._teams_off_said.clear)
        ticker, env = Ticker(), {**LOOP_ENV, "TEAMS_DELIVERY": "bot", "TEAMS_BOT_APP_ID": "a-typo-that-must-not-be-printed", "TEAMS_BOT_IDENTITY_CLIENT_ID": "", "TEAMS_SERVICE_URL": "https://evil.example/teams/"}

        def tick():
            return loop.tick(dict(env), transport=self.transport, sleep=lambda s: None, monotonic=ticker, clock=lambda: HOUR, fetch=fetch)
        with self.assertLogs("meternaut.loop", level=logging.WARNING) as logged:
            tick()
            tick()
            ticker.jump(3599)
            tick()
            ticker.jump(2)
            tick()
        said = [line for line in logged.output if "No Teams card is tried" in line]
        self.assertEqual(len(said), 2, "once in the first hour and once after it, not at every minute")
        for text in said:
            self.assertIn("TEAMS_BOT_APP_ID is not a client id", text)
            self.assertIn("TEAMS_BOT_IDENTITY_CLIENT_ID is not set", text)
            self.assertIn("TEAMS_SERVICE_URL is not the Bot Connector's address", text)
            self.assertNotIn("a-typo-that-must-not-be-printed", text)
            self.assertNotIn("evil", text)

    def test_the_timer_says_nothing_about_the_cards_when_they_are_on_the_queue_or_the_bot_way_is_complete(self):
        loop._teams_off_said.clear()
        with self.assertNoLogs("meternaut.loop", level=logging.WARNING):
            self.tick(LOOP_ENV, HOUR)
            self.tick({**LOOP_ENV, "TEAMS_DELIVERY": "queue"}, HOUR)

    def test_it_never_raises_even_when_the_store_cannot_be_reached(self):
        def down(method, url, headers, data, timeout):
            return 503, {}, b'{"odata.error":{"code":"ServerBusy","message":{"value":"busy"}}}'

        with self.assertLogs("meternaut.loop", level=logging.ERROR):
            self.assertIsNone(loop.tick(dict(LOOP_ENV), transport=down, sleep=lambda s: None, monotonic=Ticker(), clock=lambda: HOUR, fetch=fetch))


if __name__ == "__main__":
    unittest.main()
