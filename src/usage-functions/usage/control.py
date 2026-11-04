"""usage-control: runs an export job on demand, from a message on the control Event Hub.

The body of a message is {"job": "<job name>" or "all", "requestId": "<string>"}. The job runs through the same code as its
timer (jobs.run_named) and writes its result line, with the request id in it. This module never raises: a message that cannot be
used must not block the hub.
"""
import json
import logging
from collections.abc import Callable, Iterable

from . import events, jobs, results
from .protocols import EventLike

IGNORED_PREFIX = "usage_control_ignored "
ALL_JOBS = "all"
UNKNOWN_JOB = "unknown_job"
MAX_JOB_LENGTH = 64
MAX_REQUEST_ID_LENGTH = 256

JobRunner = Callable[[str, str | None], object]


def run_control_job(job_name: str, request_id: str | None) -> object:
    return jobs.run_named(job_name, results.CONTROL, request_id)


def limited(value: object, length: int) -> str | None:
    return value[:length] if isinstance(value, str) else None


def job_names(job: object) -> tuple[str, ...] | None:
    if job == ALL_JOBS:
        return jobs.JOB_NAMES
    if isinstance(job, str) and job in jobs.JOBS:
        return (job,)
    return None


def log_ignored(reason: str, number: int | None, job: str | None = None, request_id: str | None = None) -> None:
    payload = {"reason": reason, "sequenceNumber": number, "job": job, "requestId": request_id}
    logging.warning(IGNORED_PREFIX + json.dumps(payload, separators=(",", ":")))


def log_failure(exc: Exception) -> None:
    logging.error("usage_control_failed %s", results.describe_error(exc))


def handle_event(event: EventLike, run: JobRunner) -> None:
    number = events.sequence_number(event)
    try:
        payload = events.parse_object(event)
    except events.BodyError as exc:
        log_ignored(exc.reason, number)
        return
    job = payload.get("job")
    request_id = limited(payload.get("requestId"), MAX_REQUEST_ID_LENGTH)
    names = job_names(job)
    if names is None:
        log_ignored(UNKNOWN_JOB, number, limited(job, MAX_JOB_LENGTH), request_id)
        return
    for name in names:
        try:
            run(name, request_id)
        except Exception as exc:
            log_failure(exc)


def handle_events(batch: Iterable[EventLike], run: JobRunner = run_control_job) -> None:
    """Handle every message of the batch. A failure is logged and never raised."""
    try:
        for event in batch:
            try:
                handle_event(event, run)
            except Exception as exc:
                log_failure(exc)
    except Exception as exc:
        log_failure(exc)
