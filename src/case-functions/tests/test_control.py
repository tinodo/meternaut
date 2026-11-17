import datetime as dt
import json
import unittest

from support import LogCapture, NOW, fixed_clock
from cases import control


class FakeMessage:
    """What the queue trigger hands over: the decoded text as bytes, the time at which the queue says that the message was inserted, and how many times the queue has handed it over (1 the first time)."""

    def __init__(self, body, inserted=None, dequeue_count=None):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.insertion_time = inserted
        self.dequeue_count = dequeue_count

    def get_body(self):
        return self._body


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, trigger, request_id):
        self.calls.append((trigger, request_id))


GOOD = {"job": "watch", "requestId": "a" * 32}


def handle(message, run=None):
    run = run or Recorder()
    with LogCapture() as capture:
        started = control.handle_message(message, fixed_clock, run)
    return started, run, capture.events()


class Control(unittest.TestCase):
    def test_a_good_message_starts_one_watch_for_its_request(self):
        started, run, events = handle(FakeMessage(GOOD, NOW - dt.timedelta(seconds=5)))
        self.assertEqual((started, run.calls, events), (True, [("control", "a" * 32)], []))

    def test_a_message_without_an_insertion_time_is_accepted_and_a_naive_time_is_read_as_utc(self):
        self.assertTrue(handle(FakeMessage(GOOD, None))[0])
        self.assertTrue(handle(FakeMessage(GOOD, (NOW - dt.timedelta(seconds=30)).replace(tzinfo=None)))[0])

    def test_a_message_older_than_fifteen_minutes_is_refused_and_recorded(self):
        for age in (901, 3600, 86400):
            started, run, events = handle(FakeMessage(GOOD, NOW - dt.timedelta(seconds=age)))
            self.assertEqual((started, run.calls), (False, []))
            (event,) = events
            self.assertEqual((event["type"], event["reason"], event["requestId"]), ("run.failed", "stale control message", "a" * 32))
        self.assertTrue(handle(FakeMessage(GOOD, NOW - dt.timedelta(seconds=900)))[0])

    def test_the_age_is_the_age_in_the_queue_and_a_naive_old_time_is_stale_too(self):
        started, run, events = handle(FakeMessage(GOOD, (NOW - dt.timedelta(seconds=3600)).replace(tzinfo=None)))
        self.assertEqual((started, run.calls, events[0]["reason"]), (False, [], "stale control message"))

    def test_another_job_is_refused_and_recorded(self):
        for job in ("all", "WATCH", None, 5, "watch; drop"):
            started, run, events = handle(FakeMessage({"job": job, "requestId": "a" * 32}))
            self.assertEqual((started, run.calls), (False, []), str(job))
            self.assertEqual(events[0]["type"], "run.failed")
            self.assertIn("job that the app does not know", events[0]["reason"])

    def test_a_request_id_that_is_not_32_hex_digits_is_refused(self):
        for request_id in (None, "", "A" * 32, "a" * 31, "a" * 33, "g" * 32, 5, ["a" * 32]):
            started, run, events = handle(FakeMessage({"job": "watch", "requestId": request_id}))
            self.assertEqual((started, run.calls, events[0]["reason"]), (False, [], "the control message has no valid request id"))

    def test_a_body_that_is_not_json_is_refused(self):
        for body in (b"not json", b"\xff\xfe", b"[1]", b"5", b"null"):
            started, run, events = handle(FakeMessage(body))
            self.assertEqual((started, run.calls), (False, []), body)
            self.assertEqual(events[0]["type"], "run.failed")

    def test_nothing_but_the_job_and_the_request_matter(self):
        started, run, _ = handle(FakeMessage({**GOOD, "scopes": ["other"], "model": "x", "maxCases": 99, "detectors": ["all"]}))
        self.assertEqual((started, run.calls), (True, [("control", "a" * 32)]))

    def test_the_hostile_text_of_a_refused_job_is_cut_and_cleaned(self):
        _, _, events = handle(FakeMessage({"job": "x\n::error::" + "y" * 500, "requestId": "a" * 32}))
        self.assertLess(len(events[0]["reason"]), 200)
        self.assertNotIn("\n", events[0]["reason"])

    def test_a_refusal_raises_nothing_so_the_host_deletes_the_message_and_does_not_retry_it(self):
        for message in (FakeMessage(b"not json"), FakeMessage({"job": "all", "requestId": "a" * 32}), FakeMessage(GOOD, NOW - dt.timedelta(days=1))):
            self.assertIs(handle(message)[0], False)

    def test_a_failure_of_the_run_is_not_hidden_so_the_host_tries_again_and_then_poisons_the_message(self):
        def broken(trigger, request_id):
            raise RuntimeError("the run broke")

        with LogCapture(), self.assertRaises(RuntimeError):
            control.handle_message(FakeMessage(GOOD, NOW), fixed_clock, broken)

    def test_a_message_that_the_queue_hands_over_again_is_refused_and_recorded_because_a_run_that_was_begun_is_never_begun_again(self):
        for count in (2, 3, 5):
            started, run, events = handle(FakeMessage(GOOD, NOW - dt.timedelta(seconds=5), count))
            self.assertEqual((started, run.calls), (False, []), str(count))
            (event,) = events
            self.assertEqual((event["type"], event["requestId"]), ("run.failed", "a" * 32))
            self.assertIn(f"delivered {count} times", event["reason"])
            self.assertIn("each run costs money", event["reason"])

    def test_the_first_delivery_and_a_message_that_has_no_count_are_run_as_before(self):
        for count in (1, None):
            started, run, events = handle(FakeMessage(GOOD, NOW - dt.timedelta(seconds=5), count))
            self.assertEqual((started, run.calls, events), (True, [("control", "a" * 32)], []), str(count))

    def test_a_run_that_was_cut_off_and_handed_over_again_is_not_run_a_second_time_not_even_within_the_fifteen_minutes_of_the_message(self):
        def broken(trigger, request_id):
            raise RuntimeError("the host stopped the function")

        with LogCapture(), self.assertRaises(RuntimeError):
            control.handle_message(FakeMessage(GOOD, NOW - dt.timedelta(minutes=2), 1), fixed_clock, broken)
        started, run, events = handle(FakeMessage(GOOD, NOW - dt.timedelta(minutes=12), 2))
        self.assertEqual((started, run.calls, events[0]["reason"].startswith("the control message was delivered 2 times")), (False, [], True))

    def test_the_study_is_a_paid_run_too_and_the_card_test_is_not_held_by_the_count(self):
        study = Recorder()
        with LogCapture() as capture:
            self.assertFalse(control.handle_message(FakeMessage({"job": "study", "requestId": "a" * 32}, NOW, 2), fixed_clock, Recorder(), study))
            self.assertTrue(control.handle_message(FakeMessage({"job": "study", "requestId": "a" * 32}, NOW, 1), fixed_clock, Recorder(), study))
        self.assertEqual(study.calls, [("control", "a" * 32)])
        self.assertEqual([e["type"] for e in capture.events()], ["run.failed"])
        sent = []
        self.assertTrue(control.handle_message(FakeMessage({"job": "teams-card-test", "requestId": "a" * 32}, NOW, 3), fixed_clock, Recorder(), study, sent.append))
        self.assertEqual(sent, ["a" * 32])


if __name__ == "__main__":
    unittest.main()
