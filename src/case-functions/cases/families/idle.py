"""The family `delete-idle-resource`: delete a resource of a CLOSED list of kinds when nothing uses it.

Each kind is listed here explicitly, with its own reader of what "nothing uses it" means for that kind, read from Azure's own answer. There is no wildcard and no default: a kind that is not
in READERS is not deleted by this family, and the closed list is also the closed list of DELETE calls that calls.py holds for it. The list is: a snapshot, a network interface, a NAT gateway,
a load balancer and a private endpoint. A resource of one of these kinds is deleted only when it passed the same two gates as every change (the scope and the planted list: gates.py), when a
person has not marked it do-not-touch, when it has no management lock, and when its reader finds it unused, at the plan and again right before the change.

The properties that the readers look at are the ones that Microsoft's REST reference shows for each kind (Learn, "Network Interfaces - Get", "Nat Gateways - Get", "Load Balancers - Get",
"Private Endpoints - Get" and "Snapshots - Get", read on 2026-11-08). A property that is not shown counts as "nothing there", so a reader refuses only on what Azure does show.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..roles import clean_text
from . import calls
from .base import Located
from .calls import Kind
from .delete import DeleteFamily


def _props(resource: object) -> dict:
    properties = resource.get("properties") if isinstance(resource, dict) else None
    return properties if isinstance(properties, dict) else {}


def _items(value: object) -> list:
    return value if isinstance(value, list) else []


def snapshot_in_use(resource: dict) -> str | None:
    properties = _props(resource)
    if str(properties.get("provisioningState", "")).lower() not in ("", "succeeded"):
        return "the snapshot is still being made or changed"
    state = str(properties.get("diskState", "")).lower()
    if state not in ("", "unattached"):
        return f"the snapshot is in use (Azure shows it as {clean_text(state, 30)})"
    return None


def network_interface_in_use(resource: dict) -> str | None:
    properties = _props(resource)
    if properties.get("virtualMachine"):
        return "the network interface is attached to a virtual machine"
    if properties.get("privateEndpoint") or properties.get("privateLinkService"):
        return "the network interface belongs to a private endpoint or a private link service"
    for configuration in _items(properties.get("ipConfigurations")):
        found = _props(configuration)
        if any(_items(found.get(key)) for key in ("loadBalancerBackendAddressPools", "loadBalancerInboundNatRules", "applicationGatewayBackendAddressPools")):
            return "the network interface is in the backend of a load balancer or an application gateway"
    return None


def nat_gateway_in_use(resource: dict) -> str | None:
    if _items(_props(resource).get("subnets")):
        return "the NAT gateway serves a subnet"
    return None


def load_balancer_in_use(resource: dict) -> str | None:
    properties = _props(resource)
    for key, what in (("loadBalancingRules", "load balancing rules"), ("inboundNatRules", "inbound NAT rules"), ("inboundNatPools", "inbound NAT pools"), ("outboundRules", "outbound rules")):
        if _items(properties.get(key)):
            return f"the load balancer has {what}"
    for pool in _items(properties.get("backendAddressPools")):
        found = _props(pool)
        if _items(found.get("backendIPConfigurations")) or _items(found.get("loadBalancerBackendAddresses")):
            return "a backend pool of the load balancer has members"
    return None


def private_endpoint_in_use(resource: dict) -> str | None:
    """A private endpoint is idle when every connection that it has is Disconnected (Learn, Private Endpoints - Get: the state of a connection is Approved, Pending, Rejected or
    Disconnected). One with no connection at all, or with any other state, is not judged idle here."""
    properties = _props(resource)
    states: list[str] = []
    for key in ("privateLinkServiceConnections", "manualPrivateLinkServiceConnections"):
        for connection in _items(properties.get(key)):
            state = _props(connection).get("privateLinkServiceConnectionState")
            states.append(str(state.get("status", "")).lower() if isinstance(state, dict) else "")
    if not states:
        return "the private endpoint shows no connection to judge"
    other = sorted({s for s in states if s != "disconnected"})
    if other:
        return f"a connection of the private endpoint is not Disconnected (Azure shows {clean_text(', '.join(other), 60) or 'no state'})"
    return None


@dataclass(frozen=True)
class Reader:
    """One kind that is deleted when it is idle: the kind and the check of what idle means for it. The words of the kind are in words.py."""

    kind: Kind
    in_use: Callable[[dict], str | None]


READERS = (
    Reader(calls.SNAPSHOT, snapshot_in_use),
    Reader(calls.NETWORK_INTERFACE, network_interface_in_use),
    Reader(calls.NAT_GATEWAY, nat_gateway_in_use),
    Reader(calls.LOAD_BALANCER, load_balancer_in_use),
    Reader(calls.PRIVATE_ENDPOINT, private_endpoint_in_use),
)
BY_TYPE = {reader.kind.type: reader for reader in READERS}


class DeleteIdleResource(DeleteFamily):
    """Deletes a resource of one of the kinds in READERS when its reader finds that nothing uses it."""

    name = "delete-idle-resource"
    summary = "delete a snapshot, a network interface, a NAT gateway, a load balancer or a private endpoint that nothing uses"
    kinds = tuple(reader.kind for reader in READERS)
    recommendations = ("delete",)

    def why_not_idle(self, located: Located, resource: dict) -> str | None:
        return BY_TYPE[located.kind.type].in_use(resource)
