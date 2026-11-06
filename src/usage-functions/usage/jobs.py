"""The three scheduled export jobs: Application Insights custom metrics to Cosmos DB.

A run reads the marker document of the job, queries the window from the marker to now, writes one document per result
row and then moves the marker. The marker moves only after every document is written. The document ids are random, as
in the kit, so a run that failed half way writes some documents again on the next run.
"""
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from . import clients, config, queries, system
from .documents import agent_document, llm_document, mcp_document
from .protocols import Clock, ContainerLike, IdFactory, LogsClientLike
from .results import CONTROL, TIMER, JobResult, describe_error

MARKER_PARTITION_KEY = "default"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
TIMESPAN_MARGIN = timedelta(days=2)
COUNT_QUERY = "SELECT VALUE COUNT(1) FROM c"


@dataclass(frozen=True)
class JobSpec:
    name: str
    marker_id: str
    container_setting: str
    id_prefix: str
    query: str
    to_document: Callable[[Mapping[str, Any], str], dict[str, Any]]


LLM_JOB = JobSpec("llm-usage-ingestion", "002", config.COSMOS_CONTAINER_LLM_USAGE, "llm-", queries.LLM_QUERY, llm_document)
MCP_JOB = JobSpec("mcp-usage-ingestion", "003", config.COSMOS_CONTAINER_MCP_USAGE, "mcp-", queries.MCP_QUERY, mcp_document)
AGENT_JOB = JobSpec("agent-usage-ingestion", "004", config.COSMOS_CONTAINER_AGENT_USAGE, "agent-", queries.AGENT_QUERY, agent_document)
JOBS = {spec.name: spec for spec in (LLM_JOB, MCP_JOB, AGENT_JOB)}
JOB_NAMES = tuple(JOBS)


@dataclass(frozen=True)
class JobDeps:
    """Everything a run uses from outside: the containers, the logs client, the clock and the id factory."""

    config_container: ContainerLike
    usage_container: ContainerLike
    logs: LogsClientLike
    resource_id: str
    now: Clock
    new_id: IdFactory


@dataclass
class JobProgress:
    """What a run has done so far. The result line reports it also when the run fails."""

    first_run: bool = False
    window_from: str | None = None
    window_to: str | None = None
    rows: int = 0
    written: int = 0
    marker: str | None = None


class QueryStatusError(RuntimeError):
    """Log Analytics did not return a complete result."""


DepsFactory = Callable[[JobSpec], JobDeps]


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def format_timestamp(value: datetime) -> str:
    return value.strftime(TIMESTAMP_FORMAT)


def parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("The marker has no lastExportDate string")
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError as exc:
        raise ValueError("The lastExportDate of the marker is not an ISO 8601 timestamp") from exc


def read_marker(container: ContainerLike, marker_id: str) -> Mapping[str, Any] | None:
    """The marker document, or None when it does not exist. Every other error propagates."""
    try:
        return container.read_item(item=marker_id, partition_key=MARKER_PARTITION_KEY)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise


def write_marker(container: ContainerLike, marker_id: str, last_export: str, total: int) -> None:
    container.upsert_item(
        {"id": marker_id, "type": MARKER_PARTITION_KEY, "lastExportDate": last_export, "totalExportedRecords": total}
    )


def status_value(result: object) -> str:
    status = getattr(result, "status", None)
    return str(getattr(status, "value", status))


def query_rows(logs: LogsClientLike, resource_id: str, query: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Run the query. A partial or failed result is an error, never an empty result."""
    result = logs.query_resource(
        resource_id,
        query,
        # Cost bound: the scan starts at most 2 days before the window. The window itself is applied in the KQL.
        timespan=(start - TIMESPAN_MARGIN, end),
    )
    status = status_value(result)
    if status.lower() != "success":
        error = getattr(result, "partial_error", None)
        detail = f" ({getattr(error, 'code', '')}: {getattr(error, 'message', '')})" if error is not None else ""
        raise QueryStatusError(f"Log Analytics query ended with status {status}{detail}")
    tables = list(getattr(result, "tables", None) or [])
    if not tables:
        raise QueryStatusError("Log Analytics returned no result table")
    columns = list(tables[0].columns)
    return [dict(zip(columns, row)) for row in tables[0].rows]


def count_documents(container: ContainerLike) -> int:
    counts = list(container.query_items(query=COUNT_QUERY, enable_cross_partition_query=True))
    if not counts or not all(isinstance(count, int) for count in counts):
        raise RuntimeError("The document count query did not return a count")
    return sum(counts)


def export_window(spec: JobSpec, deps: JobDeps, progress: JobProgress) -> None:
    end = as_utc(deps.now()).replace(second=0, microsecond=0)
    marker = read_marker(deps.config_container, spec.marker_id)
    progress.first_run = marker is None
    if marker is None:
        start = end
        write_marker(deps.config_container, spec.marker_id, format_timestamp(end), 0)
        progress.marker = format_timestamp(end)
    else:
        start = parse_timestamp(marker.get("lastExportDate"))
        progress.marker = marker["lastExportDate"]
    progress.window_from = format_timestamp(start)
    progress.window_to = format_timestamp(end)

    query = queries.build_query(spec.query, progress.window_from, progress.window_to)
    rows = query_rows(deps.logs, deps.resource_id, query, start, end)
    progress.rows = len(rows)
    documents = [spec.to_document(row, spec.id_prefix + deps.new_id()) for row in rows]
    for document in documents:
        deps.usage_container.upsert_item(document)
        progress.written += 1
    write_marker(deps.config_container, spec.marker_id, progress.window_to, len(rows))
    progress.marker = progress.window_to


def run_job(spec: JobSpec, make_deps: DepsFactory, trigger: str, request_id: str | None = None) -> JobResult:
    """Run one export and log its result line. A failure is logged and then raised for a timer, returned for a control run."""
    if trigger not in (TIMER, CONTROL):
        raise ValueError(f"Unknown trigger: {trigger!r}")
    progress = JobProgress()
    container_count: int | None = None
    failure: Exception | None = None
    try:
        deps = make_deps(spec)
        export_window(spec, deps, progress)
        container_count = count_documents(deps.usage_container)
    except Exception as exc:
        failure = exc
    result = JobResult(
        job=spec.name,
        request_id=request_id,
        trigger=trigger,
        ok=failure is None,
        first_run=progress.first_run,
        window_from=progress.window_from,
        window_to=progress.window_to,
        rows=progress.rows,
        written=progress.written,
        container_count=container_count,
        marker=progress.marker,
        error=None if failure is None else describe_error(failure),
    )
    logging.info(result.to_line())
    if failure is not None and trigger == TIMER:
        raise failure
    return result


def production_deps(spec: JobSpec) -> JobDeps:
    values = config.get_settings(
        (
            config.COSMOS_ENDPOINT,
            config.COSMOS_DATABASE,
            config.COSMOS_CONTAINER_CONFIG,
            spec.container_setting,
            config.GATEWAY_APPINSIGHTS_ID,
        )
    )
    client_id = config.client_id()

    def container(setting: str) -> ContainerLike:
        return clients.cosmos_container(client_id, values[config.COSMOS_ENDPOINT], values[config.COSMOS_DATABASE], values[setting])

    return JobDeps(
        config_container=container(config.COSMOS_CONTAINER_CONFIG),
        usage_container=container(spec.container_setting),
        logs=clients.logs_client(client_id),
        resource_id=values[config.GATEWAY_APPINSIGHTS_ID],
        now=system.utc_now,
        new_id=system.new_uuid,
    )


def run_named(job_name: str, trigger: str, request_id: str | None = None, make_deps: DepsFactory | None = None) -> JobResult:
    """The one code path of a job run, used by the timers and by the control function."""
    return run_job(JOBS[job_name], make_deps or production_deps, trigger, request_id)


def run_scheduled(job_name: str) -> None:
    run_named(job_name, TIMER)
