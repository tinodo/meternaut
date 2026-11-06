import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from support import (
    ENV, MARKER_TEXT, NOW_TEXT, RESOURCE_ID, FakeError, FakeResult, Harness, ServiceError, llm_row, request_row,
    result_payloads,
)

from usage import clients, config, jobs, system

DOC_1 = "00000000-0000-0000-0000-000000000001"
DOC_2 = "00000000-0000-0000-0000-000000000002"
DOC_3 = "00000000-0000-0000-0000-000000000003"


class WindowAndMarkerTests(unittest.TestCase):
    def run_job(self, harness, **kwargs):
        with self.assertLogs(level="INFO"):
            return harness.run(**kwargs)

    def test_first_run_creates_the_marker_and_the_window_starts_now(self):
        harness = Harness(jobs.LLM_JOB)
        result = self.run_job(harness)
        self.assertTrue(result.first_run)
        self.assertEqual((result.window_from, result.window_to), (NOW_TEXT, NOW_TEXT))
        self.assertEqual(harness.journal[0], "config.read:002:default")
        self.assertEqual(harness.config.upserts[0], {"id": "002", "type": "default", "lastExportDate": NOW_TEXT, "totalExportedRecords": 0})
        query = harness.logs.calls[0]["query"]
        self.assertIn(f"let startTime = todatetime('{NOW_TEXT}');", query)
        self.assertIn(f"let endTime = todatetime('{NOW_TEXT}');", query)

    def test_first_run_moves_the_marker_after_the_query(self):
        harness = Harness(jobs.LLM_JOB)
        self.run_job(harness)
        self.assertEqual(harness.journal[:4], ["config.read:002:default", "config.upsert:002", "logs.query", "config.upsert:002"])
        self.assertEqual(harness.config.items["002"], {"id": "002", "type": "default", "lastExportDate": NOW_TEXT, "totalExportedRecords": 0})

    def test_an_existing_marker_sets_the_start_of_the_window(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row()])
        result = self.run_job(harness)
        self.assertFalse(result.first_run)
        self.assertEqual((result.window_from, result.window_to), (MARKER_TEXT, NOW_TEXT))
        query = harness.logs.calls[0]["query"]
        self.assertIn(f"let startTime = todatetime('{MARKER_TEXT}');", query)
        self.assertIn(f"let endTime = todatetime('{NOW_TEXT}');", query)
        self.assertEqual(harness.config.upserts, [{"id": "002", "type": "default", "lastExportDate": NOW_TEXT, "totalExportedRecords": 1}])

    def test_the_end_of_the_window_has_minute_precision(self):
        late = datetime(2026, 11, 4, 12, 0, 59, 999999, tzinfo=timezone.utc)
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, now=late)
        self.assertEqual(self.run_job(harness).window_to, NOW_TEXT)

    def test_a_clock_with_another_offset_is_converted_to_utc(self):
        local = datetime(2026, 11, 4, 13, 0, 5, tzinfo=timezone(timedelta(hours=1)))
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, now=local)
        self.assertEqual(self.run_job(harness).window_to, NOW_TEXT)

    def test_the_marker_may_carry_an_offset(self):
        harness = Harness(jobs.LLM_JOB, marker_date="2026-11-04T10:00:00+01:00")
        result = self.run_job(harness)
        self.assertEqual(result.window_from, MARKER_TEXT)
        self.assertEqual(result.marker, NOW_TEXT)

    def test_the_timespan_reaches_two_days_before_the_window_and_ends_with_it(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT)
        self.run_job(harness)
        start, end = harness.logs.calls[0]["timespan"]
        self.assertEqual(start, datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(harness.logs.calls[0]["resource_id"], RESOURCE_ID)

    def test_each_job_has_its_own_marker_container_prefix_and_query(self):
        expected = (
            (jobs.LLM_JOB, "002", "llm-", "COSMOS_CONTAINER_LLM_USAGE", llm_row()),
            (jobs.MCP_JOB, "003", "mcp-", "COSMOS_CONTAINER_MCP_USAGE", request_row()),
            (jobs.AGENT_JOB, "004", "agent-", "COSMOS_CONTAINER_AGENT_USAGE", request_row(assetType="a2a")),
        )
        for spec, marker_id, prefix, setting, row in expected:
            with self.subTest(job=spec.name):
                harness = Harness(spec, rows=[row])
                self.run_job(harness)
                self.assertEqual(harness.journal[0], f"config.read:{marker_id}:default")
                self.assertEqual(harness.config.upserts[0]["id"], marker_id)
                self.assertEqual(harness.usage.upserts[0]["id"], f"{prefix}{DOC_1}")
                self.assertEqual(spec.container_setting, setting)
        self.assertEqual(list(jobs.JOBS), ["llm-usage-ingestion", "mcp-usage-ingestion", "agent-usage-ingestion"])

    def test_only_a_missing_marker_starts_a_first_run(self):
        harness = Harness(jobs.LLM_JOB, rows=[llm_row()])
        harness.config.read_error = ServiceError("busy")
        with self.assertLogs(level="INFO") as logs, self.assertRaises(ServiceError):
            harness.run()
        self.assertEqual(harness.config.upserts, [])
        self.assertEqual(harness.logs.calls, [])
        payload = result_payloads(logs.records)[0]
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["firstRun"])

    def test_an_unreadable_marker_stops_the_run_before_the_query(self):
        for last_export in ("yesterday", None, 20261104):
            with self.subTest(last_export=last_export):
                harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT)
                harness.config.items["002"]["lastExportDate"] = last_export
                with self.assertLogs(level="INFO"), self.assertRaises(ValueError):
                    harness.run()
                self.assertEqual(harness.logs.calls, [])
                self.assertEqual(harness.config.upserts, [])


class WriteOrderTests(unittest.TestCase):
    def test_the_marker_moves_after_every_document_is_written(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row(), llm_row(appId="app-2"), llm_row(appId="app-3")])
        with self.assertLogs(level="INFO"):
            harness.run()
        self.assertEqual(
            harness.journal,
            [
                "config.read:002:default",
                "logs.query",
                f"usage.upsert:llm-{DOC_1}",
                f"usage.upsert:llm-{DOC_2}",
                f"usage.upsert:llm-{DOC_3}",
                "config.upsert:002",
                "usage.query",
            ],
        )
        self.assertEqual(harness.config.items["002"]["totalExportedRecords"], 3)

    def test_the_marker_does_not_move_when_a_write_fails(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row(), llm_row(), llm_row()])
        harness.usage.fail_on_attempt = 2
        with self.assertLogs(level="INFO") as logs, self.assertRaises(ServiceError):
            harness.run()
        self.assertEqual(harness.config.upserts, [])
        self.assertEqual(harness.config.items["002"]["lastExportDate"], MARKER_TEXT)
        self.assertEqual(len(harness.usage.upserts), 1)
        payload = result_payloads(logs.records)[0]
        self.assertEqual((payload["ok"], payload["rows"], payload["written"]), (False, 3, 1))
        self.assertEqual((payload["marker"], payload["containerCount"]), (MARKER_TEXT, None))
        self.assertEqual(payload["error"], "ServiceError: The write failed")

    def test_a_failed_first_run_keeps_the_marker_that_it_created(self):
        harness = Harness(jobs.LLM_JOB, rows=[llm_row()])
        harness.usage.fail_on_attempt = 1
        with self.assertLogs(level="INFO") as logs, self.assertRaises(ServiceError):
            harness.run()
        self.assertEqual(harness.config.items["002"], {"id": "002", "type": "default", "lastExportDate": NOW_TEXT, "totalExportedRecords": 0})
        payload = result_payloads(logs.records)[0]
        self.assertTrue(payload["firstRun"])
        self.assertEqual(payload["marker"], NOW_TEXT)

    def test_a_row_that_cannot_be_converted_stops_the_run_before_any_write(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row(), llm_row(promptTokens=1.5)])
        with self.assertLogs(level="INFO") as logs, self.assertRaises(ValueError):
            harness.run()
        self.assertEqual(harness.usage.upserts, [])
        self.assertEqual(harness.config.upserts, [])
        payload = result_payloads(logs.records)[0]
        self.assertEqual((payload["rows"], payload["written"]), (2, 0))
        self.assertEqual(payload["error"], "ValueError: promptTokens is not a whole number")

    def test_the_documents_are_counted_after_the_marker_moved(self):
        old = [{"id": f"old-{n}", "productName": "contract-1"} for n in range(4)]
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row(), llm_row()], usage_items=old)
        with self.assertLogs(level="INFO") as logs:
            result = harness.run()
        self.assertEqual(result.container_count, 6)
        self.assertEqual(harness.usage.queries, [("SELECT VALUE COUNT(1) FROM c", True)])
        self.assertEqual(harness.journal[-2:], ["config.upsert:002", "usage.query"])
        self.assertEqual(result_payloads(logs.records)[0]["containerCount"], 6)

    def test_a_failing_count_fails_the_run_but_the_marker_has_moved(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row()])
        harness.usage.query_error = ServiceError("count failed")
        with self.assertLogs(level="INFO") as logs, self.assertRaises(ServiceError):
            harness.run()
        payload = result_payloads(logs.records)[0]
        self.assertEqual((payload["ok"], payload["written"], payload["marker"], payload["containerCount"]), (False, 1, NOW_TEXT, None))

    def test_a_count_that_is_not_a_number_fails_the_run(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT)
        harness.usage.query_items = lambda query, enable_cross_partition_query=None: iter([])
        with self.assertLogs(level="INFO"), self.assertRaises(RuntimeError):
            harness.run()


class FailureHandlingTests(unittest.TestCase):
    def test_a_timer_run_raises_the_failure_after_it_logged_the_line(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row()])
        harness.usage.fail_on_attempt = 1
        with self.assertLogs(level="INFO") as logs:
            with self.assertRaises(ServiceError):
                harness.run(trigger="timer")
        self.assertEqual(len(result_payloads(logs.records)), 1)

    def test_a_control_run_returns_the_failure_and_does_not_raise(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[llm_row()])
        harness.usage.fail_on_attempt = 1
        with self.assertLogs(level="INFO") as logs:
            result = harness.run(trigger="control", request_id="abc")
        self.assertFalse(result.ok)
        payload = result_payloads(logs.records)[0]
        self.assertEqual((payload["trigger"], payload["requestId"], payload["ok"]), ("control", "abc", False))

    def test_an_unknown_trigger_is_refused(self):
        with self.assertRaises(ValueError):
            Harness(jobs.LLM_JOB).run(trigger="manual")

    def test_a_failure_to_build_the_dependencies_is_a_failed_result(self):
        def make_deps(spec):
            raise config.ConfigError("Missing required app setting(s): COSMOS_ENDPOINT")

        with self.assertLogs(level="INFO") as logs:
            result = jobs.run_job(jobs.LLM_JOB, make_deps, "control", "r1")
        self.assertFalse(result.ok)
        payload = result_payloads(logs.records)[0]
        self.assertEqual(payload["error"], "ConfigError: Missing required app setting(s): COSMOS_ENDPOINT")
        self.assertEqual((payload["from"], payload["to"], payload["rows"], payload["written"]), (None, None, 0, 0))

    def test_the_result_line_holds_no_content_of_the_rows(self):
        canary = "CANARY-Jane-Doe"
        for failing in (False, True):
            with self.subTest(failing=failing):
                rows = [llm_row(appId=canary, productName=canary), llm_row(totalTokens=1.5 if failing else 22.0, appId=canary)]
                harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=rows)
                with self.assertLogs(level="DEBUG") as logs:
                    try:
                        harness.run(trigger="control")
                    except ValueError:
                        self.fail("a control run does not raise")
                self.assertTrue(logs.records)
                for record in logs.records:
                    self.assertNotIn(canary, record.getMessage())

    def test_one_result_line_per_run_and_the_line_of_a_good_run(self):
        harness = Harness(jobs.MCP_JOB, marker_date=MARKER_TEXT, rows=[request_row()])
        with self.assertLogs(level="INFO") as logs:
            harness.run()
        self.assertEqual(
            result_payloads(logs.records),
            [
                {
                    "job": "mcp-usage-ingestion", "requestId": None, "trigger": "timer", "ok": True, "firstRun": False,
                    "from": MARKER_TEXT, "to": NOW_TEXT, "rows": 1, "written": 1, "containerCount": 1, "marker": NOW_TEXT,
                    "error": None,
                }
            ],
        )


class QueryStatusTests(unittest.TestCase):
    def assert_fails_without_writing(self, result, status):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, result=result)
        with self.assertLogs(level="INFO") as logs, self.assertRaises(jobs.QueryStatusError):
            harness.run()
        self.assertEqual(harness.usage.upserts, [])
        self.assertEqual(harness.config.upserts, [])
        payload = result_payloads(logs.records)[0]
        self.assertFalse(payload["ok"])
        self.assertIn(status, payload["error"])

    def test_a_partial_result_is_an_error(self):
        partial = FakeResult("PartialError", partial_error=FakeError("PartialError", "The query hit a limit"))
        self.assert_fails_without_writing(partial, "PartialError (PartialError: The query hit a limit)")

    def test_a_failed_result_is_an_error(self):
        self.assert_fails_without_writing(FakeResult("Failure"), "status Failure")

    def test_a_result_without_a_status_is_an_error(self):
        self.assert_fails_without_writing(FakeResult(None, tables=[]), "status None")

    def test_a_success_without_a_table_is_an_error(self):
        self.assert_fails_without_writing(FakeResult("Success", tables=[]), "no result table")

    def test_an_error_of_the_service_propagates(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT)
        harness.logs.error = ServiceError("The service answered 503")
        with self.assertLogs(level="INFO"), self.assertRaises(ServiceError):
            harness.run()
        self.assertEqual(harness.usage.upserts, [])

    def test_a_success_without_rows_writes_nothing_and_moves_the_marker(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, rows=[])
        with self.assertLogs(level="INFO"):
            result = harness.run()
        self.assertEqual((result.ok, result.rows, result.written, result.marker), (True, 0, 0, NOW_TEXT))
        self.assertEqual(harness.config.upserts[0]["totalExportedRecords"], 0)


class EntryPointTests(unittest.TestCase):
    def test_a_timer_and_a_control_run_use_the_same_code_path(self):
        with mock.patch.object(jobs, "run_job") as run_job:
            jobs.run_scheduled("mcp-usage-ingestion")
            jobs.run_named("mcp-usage-ingestion", "control", "abc")
        timer_call, control_call = run_job.call_args_list
        self.assertEqual(timer_call.args, (jobs.MCP_JOB, jobs.production_deps, "timer", None))
        self.assertEqual(control_call.args, (jobs.MCP_JOB, jobs.production_deps, "control", "abc"))

    def test_the_production_dependencies_come_from_the_app_settings(self):
        with mock.patch.dict("os.environ", ENV, clear=True), \
                mock.patch.object(clients, "cosmos_container", side_effect=lambda *args: args) as container, \
                mock.patch.object(clients, "logs_client", side_effect=lambda client_id: ("logs", client_id)):
            deps = jobs.production_deps(jobs.AGENT_JOB)
        endpoint = ENV["COSMOS_ENDPOINT"]
        client_id = ENV["AZURE_CLIENT_ID"]
        self.assertEqual(deps.config_container, (client_id, endpoint, "usage-db", "config-container"))
        self.assertEqual(deps.usage_container, (client_id, endpoint, "usage-db", "agent-container"))
        self.assertEqual(deps.logs, ("logs", client_id))
        self.assertEqual(deps.resource_id, RESOURCE_ID)
        self.assertEqual(container.call_count, 2)
        self.assertIs(deps.now, system.utc_now)
        self.assertIs(deps.new_id, system.new_uuid)

    def test_a_missing_app_setting_is_named(self):
        needed = ("COSMOS_ENDPOINT", "COSMOS_DATABASE", "COSMOS_CONTAINER_CONFIG", "COSMOS_CONTAINER_LLM_USAGE", "GATEWAY_APPINSIGHTS_ID")
        for name in needed:
            with self.subTest(setting=name):
                env = {key: value for key, value in ENV.items() if key != name}
                with mock.patch.dict("os.environ", env, clear=True), self.assertRaises(config.ConfigError) as caught:
                    jobs.production_deps(jobs.LLM_JOB)
                self.assertEqual(str(caught.exception), f"Missing required app setting(s): {name}")

    def test_the_client_id_is_not_required_and_without_it_the_app_runs_as_its_system_assigned_identity(self):
        without = {key: value for key, value in ENV.items() if key != "AZURE_CLIENT_ID"}
        for env in (without, {**without, "AZURE_CLIENT_ID": ""}, {**without, "AZURE_CLIENT_ID": "   "}):
            with self.subTest(client_id=env.get("AZURE_CLIENT_ID")), mock.patch.dict("os.environ", env, clear=True), \
                    mock.patch.object(clients, "cosmos_container", side_effect=lambda *args: args) as container, \
                    mock.patch.object(clients, "logs_client", side_effect=lambda client_id: ("logs", client_id)):
                deps = jobs.production_deps(jobs.AGENT_JOB)
            endpoint = ENV["COSMOS_ENDPOINT"]
            self.assertEqual(deps.config_container, ("", endpoint, "usage-db", "config-container"))
            self.assertEqual(deps.usage_container, ("", endpoint, "usage-db", "agent-container"))
            self.assertEqual(deps.logs, ("logs", ""))
            self.assertEqual(container.call_count, 2)

    def test_an_empty_client_id_gives_a_credential_without_one_all_the_way_down(self):
        identity = types.ModuleType("azure.identity")
        identity.ManagedIdentityCredential = mock.Mock(name="ManagedIdentityCredential")
        cosmos = types.ModuleType("azure.cosmos")
        cosmos.CosmosClient = mock.Mock(name="CosmosClient")
        query = types.ModuleType("azure.monitor.query")
        query.LogsQueryClient = mock.Mock(name="LogsQueryClient")
        without = {key: value for key, value in ENV.items() if key != "AZURE_CLIENT_ID"}
        for cached in (clients.credential, clients.cosmos_client, clients.logs_client):
            cached.cache_clear()
            self.addCleanup(cached.cache_clear)
        with mock.patch.dict(sys.modules, {"azure.identity": identity, "azure.cosmos": cosmos, "azure.monitor.query": query}), \
                mock.patch.dict("os.environ", without, clear=True):
            jobs.production_deps(jobs.LLM_JOB)
        identity.ManagedIdentityCredential.assert_called_once_with()
        self.assertEqual(cosmos.CosmosClient.call_count, 1, "one client, two containers")
        query.LogsQueryClient.assert_called_once_with(identity.ManagedIdentityCredential.return_value)

    def test_an_app_setting_of_another_job_is_not_needed(self):
        env = {key: value for key, value in ENV.items() if key != "COSMOS_CONTAINER_MCP_USAGE"}
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch.object(clients, "cosmos_container"), mock.patch.object(clients, "logs_client"):
            jobs.production_deps(jobs.LLM_JOB)


if __name__ == "__main__":
    unittest.main()
