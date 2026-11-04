"""Event Hub ingestion: stores the AI usage events and the PII usage events in Cosmos DB.

The body of an event is a JSON object. It is stored as it is; an id is added when the body has none.
The log lines hold counts and sequence numbers only, because an event can carry personal data.
"""
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from . import clients, config, system
from .protocols import ContainerLike, EventLike, IdFactory

SUMMARY_PREFIX = "usage_events_result "
NOT_JSON = "not_json"
NOT_AN_OBJECT = "not_an_object"


class BodyError(ValueError):
    """The body of an event is not a JSON object. The reason is a fixed code that is safe to log."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class IngestionError(RuntimeError):
    """At least one event of a batch could not be written to Cosmos DB."""


@dataclass(frozen=True)
class Stream:
    name: str
    container_setting: str


AI_STREAM = Stream("ai", config.COSMOS_CONTAINER_AI_USAGE)
PII_STREAM = Stream("pii", config.COSMOS_CONTAINER_PII_USAGE)


@dataclass
class BatchSummary:
    received: int = 0
    written: int = 0
    skipped: int = 0
    ids_added: int = 0
    failed: int = 0

    def to_line(self, stream: str) -> str:
        payload = {
            "stream": stream,
            "received": self.received,
            "written": self.written,
            "skipped": self.skipped,
            "idsAdded": self.ids_added,
            "failed": self.failed,
        }
        return SUMMARY_PREFIX + json.dumps(payload, separators=(",", ":"))


def sequence_number(event: object) -> int | None:
    """The sequence number of an event, or None when it has none."""
    try:
        value = getattr(event, "sequence_number", None)
    except Exception:
        return None
    return value if isinstance(value, int) else None


def parse_object(event: EventLike) -> dict[str, Any]:
    """The JSON object in the body of an event. Anything else raises BodyError."""
    try:
        value = json.loads(event.get_body())
    except Exception as exc:
        raise BodyError(NOT_JSON) from exc
    if not isinstance(value, dict):
        raise BodyError(NOT_AN_OBJECT)
    return value


def has_id(document: dict[str, Any]) -> bool:
    return isinstance(document.get("id"), str) and document["id"] != ""


def ingest_batch(stream: str, events: Iterable[EventLike], container: ContainerLike, new_id: IdFactory) -> BatchSummary:
    """Store every JSON object of the batch. A bad body is skipped. A write error is raised after the whole batch was tried."""
    summary = BatchSummary()
    first_failure: Exception | None = None
    for event in events:
        summary.received += 1
        number = sequence_number(event)
        try:
            document = parse_object(event)
        except BodyError as exc:
            summary.skipped += 1
            logging.error("%s usage event skipped: %s (sequence_number=%s)", stream, exc.reason, number)
            continue
        if not has_id(document):
            document["id"] = new_id()
            summary.ids_added += 1
            logging.warning("%s usage event has no id, an id was added (sequence_number=%s)", stream, number)
        try:
            container.upsert_item(document)
        except Exception as exc:
            summary.failed += 1
            if first_failure is None:
                first_failure = exc
            logging.error(
                "%s usage event not written: %s, status %s (sequence_number=%s)",
                stream,
                type(exc).__name__,
                getattr(exc, "status_code", None),
                number,
            )
        else:
            summary.written += 1
    logging.info(summary.to_line(stream))
    if first_failure is not None:
        raise IngestionError(f"{summary.failed} of {summary.received} {stream} usage events were not written") from first_failure
    return summary


def ingest_from_hub(stream: Stream, batch: Iterable[EventLike]) -> BatchSummary:
    values = config.get_settings(
        (config.AZURE_CLIENT_ID, config.COSMOS_ENDPOINT, config.COSMOS_DATABASE, stream.container_setting)
    )
    container = clients.cosmos_container(
        values[config.AZURE_CLIENT_ID],
        values[config.COSMOS_ENDPOINT],
        values[config.COSMOS_DATABASE],
        values[stream.container_setting],
    )
    return ingest_batch(stream.name, batch, container, system.new_uuid)


def ingest_ai(batch: Iterable[EventLike]) -> BatchSummary:
    return ingest_from_hub(AI_STREAM, batch)


def ingest_pii(batch: Iterable[EventLike]) -> BatchSummary:
    return ingest_from_hub(PII_STREAM, batch)
