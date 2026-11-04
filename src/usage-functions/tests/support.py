"""Helpers shared by the tests: fakes for Cosmos DB, Log Analytics, the clock and the id factory.

The tests use the standard library only and need no network and no Azure. Run them from the repository root:

    python -m unittest discover -s src/usage-functions/tests
"""
import copy
import itertools
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# With a handler on the root logger, logging.info() does not configure logging by itself and print to the console.
logging.getLogger().addHandler(logging.NullHandler())

from usage import jobs  # noqa: E402  (needs the path above)

# The kit's clone: the owner's working copy, or the checkout of the CI workflows. None of them is required.
KIT_ROOTS = (REPO_ROOT / "local" / "working-files" / "citadel", REPO_ROOT / "kit")

NOW = datetime(2026, 11, 4, 12, 0, 37, 250000, tzinfo=timezone.utc)
NOW_TEXT = "2026-11-04T12:00:00"
MARKER_TEXT = "2026-11-04T09:00:00"
RESOURCE_ID = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.Insights/components/gateway"

ENV = {
    "AZURE_CLIENT_ID": "11111111-1111-1111-1111-111111111111",
    "COSMOS_ENDPOINT": "https://account.documents.azure.com:443/",
    "COSMOS_DATABASE": "usage-db",
    "COSMOS_CONTAINER_CONFIG": "config-container",
    "COSMOS_CONTAINER_AI_USAGE": "ai-container",
    "COSMOS_CONTAINER_PII_USAGE": "pii-container",
    "COSMOS_CONTAINER_LLM_USAGE": "llm-container",
    "COSMOS_CONTAINER_MCP_USAGE": "mcp-container",
    "COSMOS_CONTAINER_AGENT_USAGE": "agent-container",
    "GATEWAY_APPINSIGHTS_ID": RESOURCE_ID,
}

LLM_COLUMNS = (
    "timestamp", "appId", "deploymentName", "productName", "backendId", "gatewayName", "gatewayRegion",
    "promptTokens", "responseTokens", "totalTokens", "completionAcceptedPredictionTokens", "completionAudioTokens",
    "completionReasoningTokens", "completionRejectedPredictionTokens", "promptAudioTokens", "promptCachedTokens",
)
REQUEST_COLUMNS = (
    "timestamp", "appId", "deploymentName", "productName", "backendId", "assetType", "operationName", "gatewayName",
    "gatewayRegion", "requestCount",
)


def kit_workflow(job: str) -> dict | None:
    """The kit's workflow.json of a job ("llm", "mcp", "agent", "ai" or "pii"), or None when no kit clone is present."""
    for root in KIT_ROOTS:
        path = root / "src" / "usage-ingestion-logicapp" / f"{job}-usage-ingestion" / "workflow.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def kit_query(job: str, start: str, end: str) -> str | None:
    """The kit's KQL of a job with the window put in, or None when no kit clone is present."""
    workflow = kit_workflow(job)
    if workflow is None:
        return None
    body = workflow["definition"]["actions"]["Run_query_and_list_results"]["inputs"]["body"]
    return body.replace("@{variables('LastExportDate')}", start).replace("@{variables('CurrentTime')}", end)


def llm_row(**changes) -> dict:
    row = {
        "timestamp": "11/4/2026 9:00:00 AM", "appId": "app-1", "deploymentName": "gpt-4o", "productName": "contract-1",
        "backendId": "backend-1", "gatewayName": "gateway-1", "gatewayRegion": "Sweden Central",
        "promptTokens": 17.0, "responseTokens": 5.0, "totalTokens": 22.0, "completionAcceptedPredictionTokens": 0.0,
        "completionAudioTokens": 0.0, "completionReasoningTokens": 3.0, "completionRejectedPredictionTokens": 0.0,
        "promptAudioTokens": 0.0, "promptCachedTokens": 2,
    }
    row.update(changes)
    return row


def request_row(**changes) -> dict:
    row = {
        "timestamp": "11/4/2026 9:00:00 AM", "appId": "subscription-1", "deploymentName": "tool-server",
        "productName": "contract-1", "backendId": "backend-1", "assetType": "mcp", "operationName": "tools/call",
        "gatewayName": "gateway-1", "gatewayRegion": "Sweden Central", "requestCount": 3.0,
    }
    row.update(changes)
    return row


class NotFoundError(Exception):
    """Like azure.cosmos CosmosResourceNotFoundError: an HTTP error with status 404."""

    status_code = 404


class ServiceError(Exception):
    """Like azure.cosmos CosmosHttpResponseError with status 503."""

    status_code = 503


class FakeContainer:
    """An in-memory Cosmos DB container. Fakes that share a journal show the order of their calls."""

    def __init__(self, name: str, items=(), journal: list | None = None) -> None:
        self.name = name
        self.items = {item["id"]: copy.deepcopy(item) for item in items}
        self.journal = [] if journal is None else journal
        self.upserts: list[dict] = []
        self.queries: list[tuple] = []
        self.attempts = 0
        self.fail_on_attempt: int | None = None
        self.read_error: Exception | None = None
        self.query_error: Exception | None = None

    def read_item(self, item, partition_key):
        self.journal.append(f"{self.name}.read:{item}:{partition_key}")
        if self.read_error is not None:
            raise self.read_error
        if item not in self.items:
            raise NotFoundError(f"{item} does not exist")
        return copy.deepcopy(self.items[item])

    def upsert_item(self, body):
        self.attempts += 1
        if self.fail_on_attempt == self.attempts:
            raise ServiceError("The write failed")
        self.journal.append(f"{self.name}.upsert:{body['id']}")
        self.upserts.append(copy.deepcopy(body))
        self.items[body["id"]] = copy.deepcopy(body)
        return body

    def query_items(self, query, enable_cross_partition_query=None):
        self.journal.append(f"{self.name}.query")
        self.queries.append((query, enable_cross_partition_query))
        if self.query_error is not None:
            raise self.query_error
        return iter([len(self.items)])


class FakeTable:
    def __init__(self, columns, rows) -> None:
        self.name = "PrimaryResult"
        self.columns = list(columns)
        self.rows = [tuple(row[column] for column in self.columns) if isinstance(row, dict) else tuple(row) for row in rows]


class FakeResult:
    """A Log Analytics result. A partial result has no tables, as azure.monitor.query LogsQueryPartialResult."""

    def __init__(self, status, tables=None, partial_error=None) -> None:
        self.status = status
        if tables is not None:
            self.tables = tables
        if partial_error is not None:
            self.partial_error = partial_error


class FakeError:
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


def success(columns, rows) -> FakeResult:
    return FakeResult("Success", tables=[FakeTable(columns, rows)])


class FakeLogs:
    def __init__(self, result=None, error: Exception | None = None, journal: list | None = None) -> None:
        self.result = result
        self.error = error
        self.journal = [] if journal is None else journal
        self.calls: list[dict] = []

    def query_resource(self, resource_id, query, *, timespan):
        self.calls.append({"resource_id": resource_id, "query": query, "timespan": timespan})
        self.journal.append("logs.query")
        if self.error is not None:
            raise self.error
        return self.result


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class FakeEvent:
    """An Event Hub event: a body and a sequence number, as azure.functions EventHubEvent."""

    def __init__(self, body, sequence_number: int | None = None) -> None:
        self._body = body.encode("utf-8") if isinstance(body, str) else body
        self.sequence_number = sequence_number

    def get_body(self) -> bytes:
        return self._body


def json_event(document, sequence_number: int | None = None, **dumps_options) -> FakeEvent:
    return FakeEvent(json.dumps(document, **dumps_options), sequence_number)


def sequential_ids():
    """An id factory that returns 00000000-0000-0000-0000-000000000001, then ...02, and so on."""
    counter = itertools.count(1)
    return lambda: str(uuid.UUID(int=next(counter)))


def marker_item(marker_id: str, last_export: str, total: int = 5) -> dict:
    return {"id": marker_id, "type": "default", "lastExportDate": last_export, "totalExportedRecords": total}


class Harness:
    """One run of an export job with fakes. The containers and the logs client share one journal."""

    def __init__(self, spec, rows=(), marker_date: str | None = None, now: datetime = NOW, usage_items=(), result=None) -> None:
        self.spec = spec
        self.journal: list[str] = []
        markers = [] if marker_date is None else [marker_item(spec.marker_id, marker_date)]
        self.config = FakeContainer("config", markers, self.journal)
        self.usage = FakeContainer("usage", usage_items, self.journal)
        columns = LLM_COLUMNS if spec is jobs.LLM_JOB else REQUEST_COLUMNS
        self.logs = FakeLogs(result if result is not None else success(columns, rows), journal=self.journal)
        self.deps = jobs.JobDeps(
            config_container=self.config,
            usage_container=self.usage,
            logs=self.logs,
            resource_id=RESOURCE_ID,
            now=FixedClock(now),
            new_id=sequential_ids(),
        )

    def run(self, trigger: str = "timer", request_id: str | None = None):
        return jobs.run_job(self.spec, lambda spec: self.deps, trigger, request_id)


def result_payloads(records) -> list[dict]:
    """The parsed result lines among the log records."""
    prefix = "usage_job_result "
    messages = [record.getMessage() for record in records]
    return [json.loads(message[len(prefix):]) for message in messages if message.startswith(prefix)]


class LogCapture(logging.Handler):
    """Collects the records of the root logger while it is in a with block, also when nothing is logged."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def __enter__(self) -> "LogCapture":
        root = logging.getLogger()
        self._level = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(self)
        return self

    def __exit__(self, *exc_info) -> None:
        root = logging.getLogger()
        root.removeHandler(self)
        root.setLevel(self._level)
