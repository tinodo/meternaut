import datetime as dt
import logging
import unittest
from unittest import mock

from support import ENV, Ticker

from cases import loop
from cases.store import TableStore

from test_loop_end_to_end import LOOP_ENV, fetch
from test_store import FakeTables

HOUR = dt.datetime(2026, 11, 5, 11, 0, 0, tzinfo=dt.timezone.utc)


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
