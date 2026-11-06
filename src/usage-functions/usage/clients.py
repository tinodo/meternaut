"""The only module that builds Azure SDK clients. Each client is built once and reused.

The SDK modules are imported when a client is first built, not when the app is indexed.
Every client authenticates with the managed identity of the function app: the user-assigned identity of the client id that is given or, with no client id,
the system-assigned identity of the app.
"""
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential
    from azure.cosmos import CosmosClient
    from azure.cosmos.container import ContainerProxy
    from azure.monitor.query import LogsQueryClient

# The SDKs log every HTTP request and response at INFO. Only their warnings and errors reach the telemetry.
logging.getLogger("azure").setLevel(logging.WARNING)


@lru_cache(maxsize=None)
def credential(client_id: str) -> "TokenCredential":
    from azure.identity import ManagedIdentityCredential

    if not client_id:
        return ManagedIdentityCredential()
    return ManagedIdentityCredential(client_id=client_id)


@lru_cache(maxsize=None)
def cosmos_client(client_id: str, endpoint: str) -> "CosmosClient":
    from azure.cosmos import CosmosClient

    return CosmosClient(endpoint, credential=credential(client_id))


def cosmos_container(client_id: str, endpoint: str, database: str, container: str) -> "ContainerProxy":
    return cosmos_client(client_id, endpoint).get_database_client(database).get_container_client(container)


@lru_cache(maxsize=None)
def logs_client(client_id: str) -> "LogsQueryClient":
    from azure.monitor.query import LogsQueryClient

    return LogsQueryClient(credential(client_id))
