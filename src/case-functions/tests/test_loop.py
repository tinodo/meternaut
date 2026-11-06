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

    def test_it_never_raises_even_when_the_store_cannot_be_reached(self):
        def down(method, url, headers, data, timeout):
            return 503, {}, b'{"odata.error":{"code":"ServerBusy","message":{"value":"busy"}}}'

        with self.assertLogs("meternaut.loop", level=logging.ERROR):
            self.assertIsNone(loop.tick(dict(LOOP_ENV), transport=down, sleep=lambda s: None, monotonic=Ticker(), clock=lambda: HOUR, fetch=fetch))


if __name__ == "__main__":
    unittest.main()
