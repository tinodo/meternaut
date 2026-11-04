"""The parts of the SDK objects that the app calls, so that tests can pass fakes."""
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any, Protocol

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


class ContainerLike(Protocol):
    """The part of azure.cosmos ContainerProxy that the app calls."""

    def read_item(self, item: str, partition_key: str) -> Mapping[str, Any]: ...

    def upsert_item(self, body: dict[str, Any]) -> Any: ...

    def query_items(self, query: str, enable_cross_partition_query: bool) -> Iterable[Any]: ...


class LogsClientLike(Protocol):
    """The part of azure.monitor.query LogsQueryClient that the app calls."""

    def query_resource(self, resource_id: str, query: str, *, timespan: tuple[datetime, datetime]) -> Any: ...


class EventLike(Protocol):
    """The part of azure.functions EventHubEvent that the app reads."""

    @property
    def sequence_number(self) -> int | None: ...

    def get_body(self) -> bytes: ...
