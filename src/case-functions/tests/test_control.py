import datetime as dt
import json
import unittest

from support import LogCapture, NOW, fixed_clock
from cases import control


class FakeEvent:
    def __init__(self, body, enqueued=None):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.enqueued_time = enqueued

    def get_body(self):
        return self._body


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, trigger, request_id):
        self.calls.append((trigger, request_id))


GOOD = {"job": "watch", "requestId": "a" * 32}


def handle(event, run=None):
    run = run or Recorder()
    with LogCapture() as capture:
        started = control.handle_event(event, fixed_clock, run)
    return started, run, capture.events()


class Control(unittest.TestCase):
    def test_a_good_event_starts_one_watch_for_its_request(self):
        started, run, events = handle(FakeEvent(GOOD, NOW - dt.timedelta(seconds=5)))
        self.assertEqual((started, run.calls, events), (True, [("control", "a" * 32)], []))

    def test_an_event_without_an_enqueued_time_is_accepted_and_a_naive_time_is_read_as_utc(self):
        self.assertTrue(handle(FakeEvent(GOOD, None))[0])
        self.assertTrue(handle(FakeEvent(GOOD, (NOW - dt.timedelta(seconds=30)).replace(tzinfo=None)))[0])

    def test_an_event_older_than_fifteen_minutes_is_refused_and_recorded(self):
        for age in (901, 3600, 86400):
            started, run, events = handle(FakeEvent(GOOD, NOW - dt.timedelta(seconds=age)))
            self.assertEqual((started, run.calls), (False, []))
            (event,) = events
            self.assertEqual((event["type"], event["reason"], event["requestId"]), ("run.failed", "stale control event", "a" * 32))
        self.assertTrue(handle(FakeEvent(GOOD, NOW - dt.timedelta(seconds=900)))[0])

    def test_another_job_is_refused_and_recorded(self):
        for job in ("all", "WATCH", None, 5, "watch; drop"):
            started, run, events = handle(FakeEvent({"job": job, "requestId": "a" * 32}))
            self.assertEqual((started, run.calls), (False, []), str(job))
            self.assertEqual(events[0]["type"], "run.failed")
            self.assertIn("job that the app does not know", events[0]["reason"])

    def test_a_request_id_that_is_not_32_hex_digits_is_refused(self):
        for request_id in (None, "", "A" * 32, "a" * 31, "a" * 33, "g" * 32, 5, ["a" * 32]):
            started, run, events = handle(FakeEvent({"job": "watch", "requestId": request_id}))
            self.assertEqual((started, run.calls, events[0]["reason"]), (False, [], "the control event has no valid request id"))

    def test_a_body_that_is_not_json_is_refused(self):
        for body in (b"not json", b"\xff\xfe", b"[1]", b"5", b"null"):
            started, run, events = handle(FakeEvent(body))
            self.assertEqual((started, run.calls), (False, []), body)
            self.assertEqual(events[0]["type"], "run.failed")

    def test_nothing_but_the_job_and_the_request_matter(self):
        started, run, _ = handle(FakeEvent({**GOOD, "scopes": ["other"], "model": "x", "maxCases": 99, "detectors": ["all"]}))
        self.assertEqual((started, run.calls), (True, [("control", "a" * 32)]))

    def test_the_hostile_text_of_a_refused_job_is_cut_and_cleaned(self):
        _, _, events = handle(FakeEvent({"job": "x\n::error::" + "y" * 500, "requestId": "a" * 32}))
        self.assertLess(len(events[0]["reason"]), 200)
        self.assertNotIn("\n", events[0]["reason"])


if __name__ == "__main__":
    unittest.main()
