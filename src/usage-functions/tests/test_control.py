import os
import unittest
from unittest import mock

from support import FakeEvent, Harness, LogCapture, json_event, llm_row, request_row, result_payloads

from usage import control, jobs

IGNORED = "usage_control_ignored "


class Recorder:
    """A job runner that records its calls and can fail."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self.error = error

    def __call__(self, job_name, request_id):
        self.calls.append((job_name, request_id))
        if self.error is not None:
            raise self.error


class HandleEventsTests(unittest.TestCase):
    def handle(self, batch, runner=None):
        runner = Recorder() if runner is None else runner
        with LogCapture() as logs:
            control.handle_events(batch, runner)
        return runner, logs

    def lines(self, logs, prefix):
        return [record.getMessage() for record in logs.records if record.getMessage().startswith(prefix)]

    def test_each_job_runs_with_the_request_id_of_the_message(self):
        for name in jobs.JOB_NAMES:
            with self.subTest(job=name):
                runner, _ = self.handle([json_event({"job": name, "requestId": "r1"}, 1)])
                self.assertEqual(runner.calls, [(name, "r1")])

    def test_all_runs_the_three_jobs_one_after_the_other(self):
        runner, _ = self.handle([json_event({"job": "all", "requestId": "r1"}, 1)])
        self.assertEqual(
            runner.calls,
            [("llm-usage-ingestion", "r1"), ("mcp-usage-ingestion", "r1"), ("agent-usage-ingestion", "r1")],
        )

    def test_a_request_id_that_is_missing_or_not_a_string_is_none(self):
        for body in ({"job": "llm-usage-ingestion"}, {"job": "llm-usage-ingestion", "requestId": 5}, {"job": "llm-usage-ingestion", "requestId": None}):
            with self.subTest(body=body):
                runner, _ = self.handle([json_event(body, 1)])
                self.assertEqual(runner.calls, [("llm-usage-ingestion", None)])

    def test_a_long_request_id_is_cut(self):
        runner, _ = self.handle([json_event({"job": "llm-usage-ingestion", "requestId": "r" * 1000}, 1)])
        self.assertEqual(runner.calls, [("llm-usage-ingestion", "r" * 256)])

    def test_an_unknown_job_is_logged_in_one_line_and_nothing_runs(self):
        runner, logs = self.handle([json_event({"job": "nope", "requestId": "r2"}, 5)])
        self.assertEqual(runner.calls, [])
        self.assertEqual(
            self.lines(logs, IGNORED),
            [IGNORED + '{"reason":"unknown_job","sequenceNumber":5,"job":"nope","requestId":"r2"}'],
        )

    def test_a_job_that_is_not_a_known_name_is_ignored(self):
        for body in ({"requestId": "r"}, {"job": 5}, {"job": ["all"]}, {"job": None}, {"job": "ALL"}, {"job": "llm"}, {"job": {"a": 1}}):
            with self.subTest(body=body):
                runner, logs = self.handle([json_event(body, 1)])
                self.assertEqual(runner.calls, [])
                self.assertEqual(len(self.lines(logs, IGNORED)), 1)

    def test_a_job_that_is_not_a_string_is_not_written_to_the_log(self):
        _, logs = self.handle([json_event({"job": ["secret"], "requestId": "r"}, 1)])
        self.assertEqual(self.lines(logs, IGNORED), [IGNORED + '{"reason":"unknown_job","sequenceNumber":1,"job":null,"requestId":"r"}'])

    def test_a_long_job_name_is_cut_in_the_log(self):
        _, logs = self.handle([json_event({"job": "j" * 500}, 1)])
        self.assertIn('"job":"' + "j" * 64 + '"', self.lines(logs, IGNORED)[0])

    def test_a_body_that_is_not_json_is_logged_and_nothing_runs(self):
        for body in (b"{", b"", b"\xff\xfe", b"load the job"):
            with self.subTest(body=body):
                runner, logs = self.handle([FakeEvent(body, 2)])
                self.assertEqual(runner.calls, [])
                self.assertEqual(
                    self.lines(logs, IGNORED),
                    [IGNORED + '{"reason":"not_json","sequenceNumber":2,"job":null,"requestId":null}'],
                )

    def test_a_json_body_that_is_not_an_object_is_logged_and_nothing_runs(self):
        for body in (b"[]", b'"all"', b"7", b"null"):
            with self.subTest(body=body):
                runner, logs = self.handle([FakeEvent(body, 3)])
                self.assertEqual(runner.calls, [])
                self.assertEqual(
                    self.lines(logs, IGNORED),
                    [IGNORED + '{"reason":"not_an_object","sequenceNumber":3,"job":null,"requestId":null}'],
                )

    def test_the_log_does_not_hold_the_body(self):
        _, logs = self.handle([FakeEvent('{"job": "nope", "other": "CANARY-Jane-Doe", "note": ', 1), json_event({"job": "all", "other": "CANARY-Jane-Doe"}, 2)])
        for record in logs.records:
            self.assertNotIn("CANARY", record.getMessage())

    def test_a_message_that_cannot_be_used_does_not_stop_the_next_one(self):
        batch = [FakeEvent(b"{", 1), json_event({"job": "nope"}, 2), json_event({"job": "mcp-usage-ingestion", "requestId": "r"}, 3)]
        runner, logs = self.handle(batch)
        self.assertEqual(runner.calls, [("mcp-usage-ingestion", "r")])
        self.assertEqual(len(self.lines(logs, IGNORED)), 2)


class NeverRaisesTests(unittest.TestCase):
    def test_a_runner_that_fails_does_not_stop_the_other_jobs_or_messages(self):
        runner = Recorder(RuntimeError("boom\nsecond line"))
        batch = [json_event({"job": "all", "requestId": "r"}, 1), json_event({"job": "llm-usage-ingestion", "requestId": "s"}, 2)]
        with self.assertLogs(level="ERROR") as logs:
            control.handle_events(batch, runner)
        self.assertEqual(len(runner.calls), 4)
        self.assertEqual({record.getMessage() for record in logs.records}, {"usage_control_failed RuntimeError: boom"})

    def test_a_batch_that_fails_while_it_is_read_does_not_raise(self):
        def batch():
            yield json_event({"job": "llm-usage-ingestion", "requestId": "r"}, 1)
            raise RuntimeError("the hub failed")

        runner = Recorder()
        with self.assertLogs(level="ERROR") as logs:
            control.handle_events(batch(), runner)
        self.assertEqual(runner.calls, [("llm-usage-ingestion", "r")])
        self.assertEqual([record.getMessage() for record in logs.records], ["usage_control_failed RuntimeError: the hub failed"])

    def test_a_batch_that_is_not_iterable_does_not_raise(self):
        with self.assertLogs(level="ERROR") as logs:
            control.handle_events(None, Recorder())
        self.assertTrue(logs.records[0].getMessage().startswith("usage_control_failed TypeError"))

    def test_an_event_that_cannot_give_its_body_is_logged_and_skipped(self):
        class Unreadable:
            sequence_number = 9

            def get_body(self):
                raise OSError("gone")

        runner = Recorder()
        with self.assertLogs(level="INFO") as logs:
            control.handle_events([Unreadable(), json_event({"job": "llm-usage-ingestion"}, 2)], runner)
        self.assertEqual(runner.calls, [("llm-usage-ingestion", None)])
        self.assertIn(IGNORED + '{"reason":"not_json","sequenceNumber":9,"job":null,"requestId":null}', [record.getMessage() for record in logs.records])


class CodePathTests(unittest.TestCase):
    def test_the_default_runner_is_the_control_path_of_the_jobs(self):
        with mock.patch.object(jobs, "run_named") as run_named:
            control.handle_events([json_event({"job": "mcp-usage-ingestion", "requestId": "abc"}, 1)])
        run_named.assert_called_once_with("mcp-usage-ingestion", "control", "abc")

    def test_all_runs_each_job_through_the_job_code_and_each_writes_its_result_line(self):
        harnesses = {
            "llm-usage-ingestion": Harness(jobs.LLM_JOB, marker_date="2026-11-04T09:00:00", rows=[llm_row()]),
            "mcp-usage-ingestion": Harness(jobs.MCP_JOB, marker_date="2026-11-04T09:00:00", rows=[request_row()]),
            "agent-usage-ingestion": Harness(jobs.AGENT_JOB, marker_date="2026-11-04T09:00:00", rows=[request_row(), request_row()]),
        }
        with mock.patch.object(jobs, "production_deps", side_effect=lambda spec: harnesses[spec.name].deps), \
                self.assertLogs(level="INFO") as logs:
            control.handle_events([json_event({"job": "all", "requestId": "abc123"}, 1)])
        payloads = result_payloads(logs.records)
        self.assertEqual([payload["job"] for payload in payloads], list(jobs.JOB_NAMES))
        self.assertEqual({(payload["trigger"], payload["requestId"], payload["ok"]) for payload in payloads}, {("control", "abc123", True)})
        self.assertEqual([payload["written"] for payload in payloads], [1, 1, 2])

    def test_a_failing_job_is_reported_and_the_others_still_run(self):
        harnesses = {spec.name: Harness(spec, marker_date="2026-11-04T09:00:00", rows=[llm_row() if spec is jobs.LLM_JOB else request_row()]) for spec in jobs.JOBS.values()}
        harnesses["mcp-usage-ingestion"].usage.fail_on_attempt = 1
        with mock.patch.object(jobs, "production_deps", side_effect=lambda spec: harnesses[spec.name].deps), \
                self.assertLogs(level="INFO") as logs:
            control.handle_events([json_event({"job": "all", "requestId": "abc123"}, 1)])
        self.assertEqual([(payload["job"], payload["ok"]) for payload in result_payloads(logs.records)],
                         [("llm-usage-ingestion", True), ("mcp-usage-ingestion", False), ("agent-usage-ingestion", True)])

    def test_missing_app_settings_are_reported_in_the_result_line(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertLogs(level="INFO") as logs:
            control.handle_events([json_event({"job": "llm-usage-ingestion", "requestId": "abc123"}, 1)])
        (payload,) = result_payloads(logs.records)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"].startswith(
            "ConfigError: Missing required app setting(s): COSMOS_ENDPOINT, COSMOS_DATABASE, COSMOS_CONTAINER_CONFIG, COSMOS_CONTAINER_LLM_USAGE, GATEWAY_APPINSIGHTS_ID"))
        self.assertNotIn("AZURE_CLIENT_ID", payload["error"], "the client id is not required: without it the app runs as its system-assigned identity")
        self.assertEqual((payload["trigger"], payload["requestId"]), ("control", "abc123"))


if __name__ == "__main__":
    unittest.main()
