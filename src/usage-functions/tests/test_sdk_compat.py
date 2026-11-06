"""Checks of the app's calls against the installed Azure SDKs. A test is skipped when its SDK is not installed."""
import inspect
import json
import re
import unittest
from datetime import datetime, timezone

from support import LLM_COLUMNS, MARKER_TEXT, RESOURCE_ID, FakeLogs, Harness, llm_row

from usage import jobs

try:
    from azure.monitor.query import LogsQueryClient, LogsQueryError, LogsQueryPartialResult, LogsQueryResult, LogsQueryStatus, LogsTable
except ImportError:
    LogsQueryClient = None

try:
    from azure.cosmos import CosmosClient
    from azure.cosmos.container import ContainerProxy
    from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
except ImportError:
    CosmosClient = None

try:
    from azure.identity import ManagedIdentityCredential
except ImportError:
    ManagedIdentityCredential = None

START = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
LLM_TYPES = ["string"] * 7 + ["real"] * 9


def real_table(rows) -> "LogsTable":
    return LogsTable(
        name="PrimaryResult",
        columns=list(LLM_COLUMNS),
        columns_types=LLM_TYPES,
        rows=[[row[column] for column in LLM_COLUMNS] for row in rows],
    )


@unittest.skipIf(LogsQueryClient is None, "azure-monitor-query is not installed here; the CI runner installs it")
class LogsQuerySdkTests(unittest.TestCase):
    def test_the_status_values_are_the_ones_that_the_code_compares(self):
        self.assertEqual(LogsQueryStatus.SUCCESS.value, "Success")
        self.assertEqual(LogsQueryStatus.PARTIAL.value, "PartialError")
        self.assertEqual(LogsQueryStatus.FAILURE.value, "Failure")

    def test_query_resource_takes_the_resource_id_the_query_and_a_keyword_timespan(self):
        parameters = inspect.signature(LogsQueryClient.query_resource).parameters
        self.assertEqual(list(parameters)[1:3], ["resource_id", "query"])
        self.assertEqual(parameters["timespan"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_the_rows_of_a_real_result_are_read_by_column_name(self):
        result = LogsQueryResult(tables=[real_table([llm_row(), llm_row(appId="app-2", promptTokens=18)])])
        rows = jobs.query_rows(FakeLogs(result), RESOURCE_ID, "query", START, END)
        self.assertEqual([row["appId"] for row in rows], ["app-1", "app-2"])
        self.assertEqual(rows[1]["promptTokens"], 18)
        self.assertIsInstance(rows[0]["responseTokens"], float)

    def test_a_real_result_gives_documents_with_whole_number_strings(self):
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, result=LogsQueryResult(tables=[real_table([llm_row()])]))
        with self.assertLogs(level="INFO"):
            harness.run()
        (document,) = harness.usage.upserts
        self.assertEqual((document["promptTokens"], document["promptCachedTokens"]), ("17", "2"))
        self.assertIsNone(re.search(r'"-?\d+\.\d+"', json.dumps(document)))

    def test_a_real_partial_result_is_an_error(self):
        partial = LogsQueryPartialResult(
            partial_data=[real_table([llm_row()])], partial_error=LogsQueryError(code="PartialError", message="The query hit a limit")
        )
        harness = Harness(jobs.LLM_JOB, marker_date=MARKER_TEXT, result=partial)
        with self.assertLogs(level="INFO"), self.assertRaises(jobs.QueryStatusError) as caught:
            harness.run()
        self.assertEqual(str(caught.exception), "Log Analytics query ended with status PartialError (PartialError: The query hit a limit)")
        self.assertEqual((harness.usage.upserts, harness.config.upserts), ([], []))

    def test_a_real_failure_object_has_the_status_failure(self):
        self.assertEqual(jobs.status_value(LogsQueryError(code="Failure", message="bad")), "Failure")


@unittest.skipIf(CosmosClient is None, "azure-cosmos is not installed here; the CI runner installs it")
class CosmosSdkTests(unittest.TestCase):
    class Raising:
        def __init__(self, error):
            self.error = error

        def read_item(self, item, partition_key):
            raise self.error

    def test_a_missing_document_of_the_sdk_is_recognised_as_a_missing_marker(self):
        error = CosmosResourceNotFoundError(status_code=404, message="Entity with the specified id does not exist in the system.")
        self.assertIsNone(jobs.read_marker(self.Raising(error), "002"))

    def test_another_error_of_the_sdk_is_not(self):
        for status in (401, 403, 429, 503):
            with self.subTest(status=status), self.assertRaises(CosmosHttpResponseError):
                jobs.read_marker(self.Raising(CosmosHttpResponseError(status_code=status, message="no")), "002")

    def test_the_calls_match_the_signatures_of_the_sdk(self):
        self.assertEqual(list(inspect.signature(CosmosClient.__init__).parameters)[1:3], ["url", "credential"])
        self.assertEqual(list(inspect.signature(ContainerProxy.read_item).parameters)[1:3], ["item", "partition_key"])
        self.assertEqual(list(inspect.signature(ContainerProxy.upsert_item).parameters)[1], "body")


@unittest.skipIf(ManagedIdentityCredential is None or LogsQueryClient is None, "azure-identity or azure-monitor-query is not installed here")
class ClientConstructionTests(unittest.TestCase):
    def test_the_logs_client_is_built_from_a_managed_identity_credential_without_a_network_call(self):
        from usage import clients

        clients.credential.cache_clear()
        clients.logs_client.cache_clear()
        self.addCleanup(clients.credential.cache_clear)
        self.addCleanup(clients.logs_client.cache_clear)
        client = clients.logs_client("11111111-1111-1111-1111-111111111111")
        self.assertIsInstance(client, LogsQueryClient)
        self.assertIsInstance(clients.credential("11111111-1111-1111-1111-111111111111"), ManagedIdentityCredential)

    def test_a_credential_without_a_client_id_is_built_from_the_sdk_too_without_a_network_call(self):
        from usage import clients

        clients.credential.cache_clear()
        self.addCleanup(clients.credential.cache_clear)
        self.assertIsInstance(clients.credential(""), ManagedIdentityCredential)


if __name__ == "__main__":
    unittest.main()
