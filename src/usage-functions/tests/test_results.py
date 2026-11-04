import json
import unittest

import support  # noqa: F401  (puts the app folder on the path)

from usage.results import ERROR_MAX_LENGTH, RESULT_PREFIX, JobResult, describe_error

KEYS = ["job", "requestId", "trigger", "ok", "firstRun", "from", "to", "rows", "written", "containerCount", "marker", "error"]


def result(**changes) -> JobResult:
    values = dict(
        job="llm-usage-ingestion", request_id="0123456789abcdef0123456789abcdef", trigger="control", ok=True, first_run=False,
        window_from="2026-11-04T09:00:00", window_to="2026-11-04T12:00:00", rows=4, written=4, container_count=10,
        marker="2026-11-04T12:00:00", error=None,
    )
    values.update(changes)
    return JobResult(**values)


class ResultLineTests(unittest.TestCase):
    def test_the_prefix_and_the_twelve_keys_of_the_contract(self):
        self.assertEqual(RESULT_PREFIX, "usage_job_result ")
        line = result().to_line()
        self.assertTrue(line.startswith(RESULT_PREFIX))
        self.assertEqual(list(json.loads(line[len(RESULT_PREFIX):])), KEYS)

    def test_the_json_is_compact_and_the_line_is_one_line(self):
        line = result(error="ValueError: one\ntwo").to_line()
        self.assertNotIn("\n", line)
        body = line[len(RESULT_PREFIX):]
        self.assertEqual(body, json.dumps(json.loads(body), separators=(",", ":")))

    def test_the_values_of_a_good_run(self):
        payload = json.loads(result().to_line()[len(RESULT_PREFIX):])
        self.assertEqual(
            payload,
            {
                "job": "llm-usage-ingestion", "requestId": "0123456789abcdef0123456789abcdef", "trigger": "control", "ok": True,
                "firstRun": False, "from": "2026-11-04T09:00:00", "to": "2026-11-04T12:00:00", "rows": 4, "written": 4,
                "containerCount": 10, "marker": "2026-11-04T12:00:00", "error": None,
            },
        )

    def test_the_values_of_a_failed_run_that_stopped_early(self):
        line = result(
            request_id=None, trigger="timer", ok=False, first_run=True, window_from=None, window_to=None, rows=0, written=0,
            container_count=None, marker=None, error="ConfigError: Missing required app setting(s): COSMOS_ENDPOINT",
        ).to_line()
        payload = json.loads(line[len(RESULT_PREFIX):])
        self.assertEqual(list(payload), KEYS)
        self.assertEqual([payload[key] for key in ("requestId", "ok", "firstRun", "from", "to", "containerCount", "marker")],
                         [None, False, True, None, None, None, None])


class DescribeErrorTests(unittest.TestCase):
    def test_the_class_name_and_the_message(self):
        self.assertEqual(describe_error(ValueError("promptTokens is not a number")), "ValueError: promptTokens is not a number")

    def test_only_the_first_line_of_the_message(self):
        self.assertEqual(describe_error(RuntimeError("first line\nsecond line\nthird")), "RuntimeError: first line")

    def test_a_blank_first_line_is_skipped(self):
        self.assertEqual(describe_error(RuntimeError("\n\nmessage\nmore")), "RuntimeError: message")

    def test_the_message_is_cut_at_300_characters(self):
        text = describe_error(RuntimeError("x" * 1000))
        self.assertEqual(ERROR_MAX_LENGTH, 300)
        self.assertEqual(text, "RuntimeError: " + "x" * 300)

    def test_an_exception_without_a_message(self):
        self.assertEqual(describe_error(KeyError()), "KeyError: ")

    def test_the_name_is_the_class_of_the_exception(self):
        class OwnError(Exception):
            pass

        self.assertTrue(describe_error(OwnError("x")).startswith("OwnError: "))


if __name__ == "__main__":
    unittest.main()
