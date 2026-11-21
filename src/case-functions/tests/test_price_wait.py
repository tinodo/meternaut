"""The wait for the public price list (cases/prices.py, and price_alternatives in cases/toolbox.py): a list that asks to wait is waited for once when the call can afford it, what it asked for that was not waited
for holds the list in the run for that time, and each try that reaches the list is one line of the History. A fake clock and an INVENTED list answer at the level of the transport; every service, product and
price in it is invented, and the one header of the list that is real is the one that carries its wait (the list shows it on every answer)."""
import json
import unittest
from unittest import mock

import support  # noqa: F401  (it puts the app on the path)
from cases import prices
from cases.events import History, PRICE_KINDS
from cases.http import HttpError, Client, allowed_calls
from cases.redact import Redactor
from test_prices import PRODUCT, SERVICE, PricedEstate, priced, swallowing
from test_toolbox import SUB, Clock, ask

WAIT_HEADER = "x-ms-ratelimit-retailprices-retry-after"
BUSY = b'{"message":"Too many requests at this point. Please retry after some time."}'  # a body that has no code word of its own


def scripted(estate, clock, *steps, took=0.0):
    """A list that answers each call with the next step, whatever the filter says, and after that with its invented lines: a number is the status that it answers (200 is the list), a pair (429, n) is a 429 that
    asks to wait n seconds in the header that the real list uses, and (429, None) one that says nothing of it. Each answer takes `took` seconds on the clock."""
    queue = list(steps)

    def hook(found, url, timeout):
        clock.advance(took)
        step = queue.pop(0) if queue else 200
        status, wait = step if isinstance(step, tuple) else (step, None)
        if status == 200:
            return found.price_answer(url)
        return status, {WAIT_HEADER: str(wait)} if wait is not None else {}, BUSY

    estate.hook = hook


class TheWait(unittest.TestCase):
    def setUp(self):
        self.estate, self.clock, self.slept = PricedEstate(), Clock(), []
        self.client = Client(allowed_calls(), Redactor(), transport=self.estate, sleep=self.sleep, jitter=lambda: 0.5)

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.clock.advance(seconds)

    def read(self, hold=None, product=PRODUCT, **more):
        return prices.read(self.client, SERVICE, "swedencentral", product, self.clock, hold=hold, **more)

    def test_a_list_that_asks_to_wait_12_seconds_is_waited_for_once_and_then_asked_again(self):
        scripted(self.estate, self.clock, (429, 12))
        book = self.read()
        self.assertEqual((self.slept, len(self.estate.price_calls), book.complete, len(book.lines)), ([12.0], 2, True, 5), "the header that the list really sends is the one that is read")

    def test_the_wait_is_not_a_part_of_the_time_that_a_read_may_take(self):
        scripted(self.estate, self.clock, (429, 12), took=1.0)
        book = self.read(seconds=10.0)
        self.assertEqual((self.slept, book.complete, self.clock.now), ([12.0], True, 14.0), "10 seconds for the tries and 12 for the wait: the read took 14")
        self.assertEqual([call["timeout"] for call in self.estate.price_calls], [8.0, 8.0], "and the second try had the time that was left, not the time that the wait used")

    def test_a_list_that_asks_for_60_seconds_ends_the_read_with_the_words_of_what_it_asked_and_nothing_is_waited_for(self):
        scripted(self.estate, self.clock, (429, 60))
        with self.assertRaises(HttpError) as raised:
            self.read()
        failure = raised.exception
        self.assertEqual((str(failure), failure.status, failure.code, failure.retry_after, self.slept, len(self.estate.price_calls)), ("the price list asked to wait 60 seconds (429)", 429, "429", 60.0, [], 1))
        for word in ("prices.azure.com", "https", "retry-after", "x-ms"):
            self.assertNotIn(word, str(failure).lower(), "no address and no header in the words of a failure")

    def test_the_code_word_that_the_body_gives_is_kept_and_a_429_that_says_nothing_of_a_wait_says_so(self):
        self.estate.failure, self.estate.wait = 429, 60
        with self.assertRaises(HttpError) as raised:
            self.read()
        self.assertEqual((str(raised.exception), raised.exception.code), ("the price list asked to wait 60 seconds (429)", "Failed"))
        scripted(self.estate, self.clock, (429, None), (429, None))
        with self.assertRaises(HttpError) as raised:
            self.read(hold=prices.Hold())
        self.assertEqual((str(raised.exception), raised.exception.retry_after, self.slept), ("the price list answered 429 and gave no time to wait", None, [1.5]), "one try more after a pause that the client chose: 1 second and its jitter")

    def test_a_wait_is_taken_once_for_an_address_in_a_run_and_never_twice(self):
        hold = prices.Hold()
        scripted(self.estate, self.clock, (429, 12), (429, 12))
        with self.assertRaises(HttpError) as raised:
            self.read(hold)
        self.assertEqual((self.slept, len(self.estate.price_calls), str(raised.exception)), ([12.0], 2, "the price list asked to wait 12 seconds (429)"), "the second try was refused too, and it was not waited for")
        self.clock.advance(20)
        scripted(self.estate, self.clock, (429, 12))
        with self.assertRaises(HttpError):
            self.read(hold)
        self.assertEqual((self.slept, len(self.estate.price_calls)), ([12.0], 3), "the same address asked again: one try, no second wait")
        self.clock.advance(12)  # what the list asked for this time, and was not waited for, holds the list
        scripted(self.estate, self.clock, (429, 12))
        self.assertTrue(self.read(hold, product="Premium Tier").complete)
        self.assertEqual(self.slept, [12.0, 12.0], "another address has a wait of its own")

    def test_a_list_that_was_asked_to_wait_for_and_not_waited_for_is_not_asked_again_before_that_time_has_passed_by_any_address(self):
        hold = prices.Hold()
        scripted(self.estate, self.clock, (429, 60))
        with self.assertRaises(HttpError):
            self.read(hold)
        self.assertEqual((hold.until, len(self.estate.price_calls)), (60.0, 1))
        self.clock.advance(10)
        with self.assertRaises(HttpError) as raised:
            self.read(hold, product="Premium Tier")
        self.assertEqual((str(raised.exception), len(self.estate.price_calls)), ("the price list asked to wait, and 50 seconds of it are left (429)", 1), "no call went to the list")
        self.clock.advance(50)
        self.assertTrue(self.read(hold, product="Premium Tier").complete)
        self.assertEqual(len(self.estate.price_calls), 2)

    def test_a_wait_is_taken_only_when_it_is_no_longer_than_the_room_that_the_caller_has(self):
        for room, asked, waits in ((20.0, 20, True), (20.0, 21, False), (6.0, 12, False), (6.0, 6, True), (0.0, 1, False)):
            with self.subTest(room=room, asked=asked):
                self.setUp()
                scripted(self.estate, self.clock, (429, asked))
                if waits:
                    self.assertTrue(self.read(room=room).complete)
                else:
                    with self.assertRaises(HttpError):
                        self.read(room=room)
                self.assertEqual(self.slept, [float(asked)] if waits else [])

    def test_a_wait_that_leaves_no_time_for_a_try_ends_the_read(self):
        scripted(self.estate, self.clock, (429, 5), took=23.5)
        with self.assertRaises(HttpError):
            self.read()
        self.assertEqual((self.slept, len(self.estate.price_calls)), ([], 1), "0.5 of the 24 seconds were left")

    def test_the_longest_wait_and_the_read_fit_in_the_time_of_a_call_of_the_toolbox(self):
        self.assertEqual((prices.SECONDS, prices.WAIT), (24.0, 20.0))
        self.assertLessEqual(prices.SECONDS + prices.WAIT, 45.0, "a call may take 45 seconds: 24 for the read and one wait of 20")


class ThePriceToolInARun(unittest.TestCase):
    """price_alternatives on the fake estate: the room of a call, what the run remembers of a wait that was not taken, and what the note says."""

    def clocked(self):
        estate, box = priced()
        clock, self.slept = Clock(), []
        box.monotonic = clock
        box.arm.client.sleep = lambda seconds: (self.slept.append(seconds), clock.advance(seconds))
        return estate, box, clock

    def test_a_call_waits_as_long_as_the_time_of_a_call_leaves_over_the_time_of_a_read(self):
        for read_seconds, waits in ((45.0, True), (30.0, False), (10.0, False)):
            with self.subTest(read_seconds=read_seconds):
                estate, box, clock = self.clocked()
                box.read_seconds = read_seconds
                scripted(estate, clock, (429, 12))
                answer = ask(box, "price_alternatives", meter="m1")
                self.assertEqual(("error" in answer, self.slept), (not waits, [12.0] if waits else []), "a read has 24 seconds, so a call of 30 has 6 for a wait and one of 10 has none")

    def test_a_wait_that_was_not_taken_holds_the_list_for_the_run_and_the_second_call_does_not_reach_it_before_the_time_has_passed(self):
        estate, box, clock = self.clocked()
        scripted(estate, clock, (429, 60))
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "429"})
        self.assertEqual(len(estate.price_calls), 1)
        clock.advance(10)
        for arguments in ({"within": "service"}, {"within": "product"}):
            self.assertEqual(ask(box, "price_alternatives", meter="m1", **arguments), {"error": "unavailable", "code": "429"})
        self.assertEqual(len(estate.price_calls), 1, "neither the other set of prices nor the same one went to the list while it asked to wait")
        clock.advance(51)
        self.assertEqual(ask(box, "price_alternatives", meter="m1", within="service")["match"], "found")
        self.assertEqual(len(estate.price_calls), 2)
        notes = [note for note in box.notes if note.startswith("price_alternatives")]
        self.assertTrue(notes[0].endswith("(the price list asked to wait 60 seconds (429))"), notes[0])
        for note in notes:
            self.assertNotIn("prices.azure.com", note)

    def test_a_list_that_asked_to_wait_does_not_make_the_host_down_for_the_run(self):
        estate, box, clock = self.clocked()
        scripted(estate, clock, (429, 60))
        ask(box, "price_alternatives", meter="m1")
        self.assertIsNone(box._prices_down, "a host that answered 429 answered: only one that gives no answer at all is not asked again")

    def test_trials_of_code_that_the_list_asked_to_wait_for_do_not_end_the_trials_of_the_run_and_are_made_again_when_the_time_has_passed(self):
        estate, box, clock = self.clocked()
        box.trial = True
        scripted(estate, clock, (429, 60))
        for within in ("product", "service"):
            self.assertEqual(ask(box, "price_alternatives", meter="m1", within=within), {"error": "unavailable", "code": "429"})
        self.assertEqual((len(estate.price_calls), box._trials), (1, []), "the second ask was held: no try reached the list, and neither counts as a failed trial")
        clock.advance(61)
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found")
        self.assertEqual(len(estate.price_calls), 2)


class TheLinesOfTheHistory(unittest.TestCase):
    def setUp(self):
        self.estate, self.box = priced()
        self.clock, self.seen = Clock(), []
        self.box.monotonic = self.clock
        self.box.arm.client.sleep = self.clock.advance
        self.box.emit = lambda kind, **fields: self.seen.append((kind, fields))

    def test_each_try_that_reaches_the_list_is_one_line_with_the_status_the_milliseconds_and_the_wait_that_the_list_asked_for(self):
        scripted(self.estate, self.clock, (429, 12), took=0.25)
        ask(self.box, "price_alternatives", meter="m1")
        words = {"service": SERVICE, "region": "swedencentral", "product": PRODUCT}
        self.assertEqual(self.seen, [("prices.read", {**words, "status": 429, "ms": 250, "retryAfter": 12.0}), ("prices.read", {**words, "status": 200, "ms": 250})])
        text = json.dumps(self.seen)
        for private in ("prices.azure.com", "https", SUB, "w1", "rg-app", "subscriptions", "Example Service"):
            self.assertNotIn(private, text, "no address, id or name of the estate")

    def test_the_whole_service_has_no_product_and_a_try_that_got_no_answer_has_the_status_0(self):
        self.estate.hook = swallowing(self.clock)
        ask(self.box, "price_alternatives", meter="m1", within="service")
        (kind, fields), = self.seen
        self.assertEqual((kind, fields["status"], fields["ms"], "product" in fields, "retryAfter" in fields), ("prices.read", 0, 8000, False, False))

    def test_a_call_that_the_list_was_not_asked_for_leaves_no_line_and_a_line_that_cannot_be_written_costs_no_answer(self):
        scripted(self.estate, self.clock, (429, 60))
        ask(self.box, "price_alternatives", meter="m1")
        self.assertEqual(len(self.seen), 1)
        ask(self.box, "price_alternatives", meter="m1", within="service")
        self.assertEqual(len(self.seen), 1, "held: no try reached the list")
        self.clock.advance(61)
        self.box.emit = mock.Mock(side_effect=ValueError("not a kind"))
        self.assertEqual(ask(self.box, "price_alternatives", meter="m1", within="service")["match"], "found")

    def test_the_history_knows_the_kind_and_no_other_price_kind(self):
        self.assertEqual(PRICE_KINDS, ("prices.read",))
        history = History("r" * 32, None, self.clock_of_the_day, Redactor())
        history.emit("prices.read", service=SERVICE, region="swedencentral", status=200, ms=300)
        self.assertEqual(history.counts["prices.read"], 1)
        with self.assertRaises(ValueError):
            history.emit("prices.write")

    @staticmethod
    def clock_of_the_day():
        import datetime as dt
        return dt.datetime(2026, 11, 21, 8, 0, 0, tzinfo=dt.timezone.utc)


if __name__ == "__main__":
    unittest.main()
