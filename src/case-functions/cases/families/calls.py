"""Every call that a family of change makes to Azure Resource Manager, in one place.

This is the one module of the families that names a method that writes. A person who wants to know everything that Meternaut can do to an estate reads `WRITES` below: ten calls,
each on one kind of resource, each in a resource group of `CHANGE_SCOPES` (gates.py), each made with the token of the person who approved it and no other (AGENTS.md rule 29).
`READS` are what the checks before and after a change read. The lists that the HTTP client holds (`patterns`) are built from these two tuples and from nothing else, so a call that is not
here cannot leave the app: the client refuses it before it is sent.

The api-versions are the ones that the REST reference of each call shows (Microsoft Learn, read on 2026-11-08). A call that has not changed since the first family keeps the version that
it had: the disk and the public IP address are deleted with the versions that were tested on a real estate on 2026-11-05.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .gates import ChangeScope

ARM_HOST = "management.azure.com"
ARM_RESOURCE = "https://management.azure.com/"
GET, POST, PATCH, DELETE = "GET", "POST", "PATCH", "DELETE"
COMPUTE, NETWORK = "Microsoft.Compute", "Microsoft.Network"
LOCKS_API = "2016-09-01"

# Learn, "Virtual Machines - Get / Update / Deallocate / List Available Sizes", and "Usage - List": api-version 2026-04-01.
VM_API = "2026-04-01"
# Learn, "Disks - Update", "Disks - Get" and "Snapshots - Delete": api-version 2026-03-02.
DISK_API = "2026-03-02"
# Learn, "Network Interfaces", "Nat Gateways", "Load Balancers" and "Private Endpoints" - Delete: api-version 2026-01-01.
NETWORK_API = "2026-01-01"
# The first two families, unchanged: Disks - Delete 2024-03-02 and Public IP Addresses - Delete 2024-05-01.
DISK_DELETE_API = "2024-03-02"
PUBLIC_IP_API = "2024-05-01"

# A name of one or two dots would walk up the address once a server reads it, so it is not a name.
NAME = r"(?!\.{1,2}(?:/|$))[A-Za-z0-9_.-]{1,80}"
# The id of one resource in a resource group, as a plan holds it: every part is checked, and nothing may follow the name.
RESOURCE_ID = re.compile(
    r"/subscriptions/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/resourceGroups/([A-Za-z0-9._()-]{1,90})"
    rf"/providers/([A-Za-z0-9.]{{1,80}})/([A-Za-z0-9]{{1,40}})/({NAME})", re.I)


@dataclass(frozen=True)
class Kind:
    """One kind of resource that a family reads, and for a delete, removes. `type` is as Resource Graph names it (lower case)."""

    type: str
    provider: str
    collection: str
    api: str

    def path(self, scope: ChangeScope, name: str) -> str:
        return f"/subscriptions/{scope.subscription}/resourceGroups/{scope.group}/providers/{self.provider}/{self.collection}/{name}"


DISK = Kind("microsoft.compute/disks", COMPUTE, "disks", DISK_DELETE_API)
DISK_TIER = Kind("microsoft.compute/disks", COMPUTE, "disks", DISK_API)
PUBLIC_IP = Kind("microsoft.network/publicipaddresses", NETWORK, "publicIPAddresses", PUBLIC_IP_API)
VIRTUAL_MACHINE = Kind("microsoft.compute/virtualmachines", COMPUTE, "virtualMachines", VM_API)
SNAPSHOT = Kind("microsoft.compute/snapshots", COMPUTE, "snapshots", DISK_API)
NETWORK_INTERFACE = Kind("microsoft.network/networkinterfaces", NETWORK, "networkInterfaces", NETWORK_API)
NAT_GATEWAY = Kind("microsoft.network/natgateways", NETWORK, "natGateways", NETWORK_API)
LOAD_BALANCER = Kind("microsoft.network/loadbalancers", NETWORK, "loadBalancers", NETWORK_API)
PRIVATE_ENDPOINT = Kind("microsoft.network/privateendpoints", NETWORK, "privateEndpoints", NETWORK_API)
KINDS = (DISK, DISK_TIER, PUBLIC_IP, VIRTUAL_MACHINE, SNAPSHOT, NETWORK_INTERFACE, NAT_GATEWAY, LOAD_BALANCER, PRIVATE_ENDPOINT)


@dataclass(frozen=True)
class Call:
    """One call on a kind of resource: the method, the kind and what follows the name in the address."""

    method: str
    kind: Kind
    suffix: str = ""

    def url(self, scope: ChangeScope, name: str, query: str = "") -> str:
        extra = f"&{query}" if query else ""
        return f"https://{ARM_HOST}{self.kind.path(scope, name)}{self.suffix}?api-version={self.kind.api}{extra}"


# The reads: the resource itself, and what the checks of a family look at. No write.
READS = tuple(Call(GET, kind) for kind in KINDS) + (Call(GET, VIRTUAL_MACHINE, "/vmSizes"),)

# The one write of a machine that is not a PATCH: Learn, Virtual Machines - Deallocate. 200, or 202 with a Location header.
DEALLOCATE = Call(POST, VIRTUAL_MACHINE, "/deallocate")

# The writes: every one is one change to one resource, and the person's own token is the only token that makes it. The two deletes of the first families come first.
WRITES = (
    Call(DELETE, DISK),
    Call(DELETE, PUBLIC_IP),
    DEALLOCATE,
    Call(PATCH, VIRTUAL_MACHINE),  # Learn: Virtual Machines - Update. The body changes properties.hardwareProfile.vmSize and nothing else.
    Call(PATCH, DISK_TIER),  # Learn: Disks - Update. The body changes sku.name and nothing else. 200, or 202 with a Location header.
    Call(DELETE, SNAPSHOT),
    Call(DELETE, NETWORK_INTERFACE),
    Call(DELETE, NAT_GATEWAY),
    Call(DELETE, LOAD_BALANCER),
    Call(DELETE, PRIVATE_ENDPOINT),
)
DELETES = tuple(call for call in WRITES if call.method == DELETE)

# The quota of a region (Learn: Usage - List): read to see that a larger size fits, never written.
USAGE_API = VM_API


def usage_url(subscription: str, location: str) -> str:
    return f"https://{ARM_HOST}/subscriptions/{subscription}/providers/{COMPUTE}/locations/{location}/usages?api-version={USAGE_API}"


def write_for(method: str, kind: Kind, suffix: str = "") -> Call:
    """The write call of a family: it has to be one of WRITES, so that a family cannot invent a call."""
    for call in WRITES:
        if call.method == method and call.kind == kind and call.suffix == suffix:
            return call
    raise LookupError(f"{method} {kind.collection}{suffix} is not a call that Meternaut may make")


def _base(scope: ChangeScope) -> str:
    return re.escape(f"https://{ARM_HOST}/subscriptions/{scope.subscription}/resourceGroups/{scope.group}")


def _pattern(scope: ChangeScope, call: Call) -> "re.Pattern[str]":
    return re.compile(_base(scope) + rf"/providers/{re.escape(call.kind.provider)}/{re.escape(call.kind.collection)}/{NAME}{re.escape(call.suffix)}", re.I)


def _locks(scope: ChangeScope) -> "re.Pattern[str]":
    """The locks of the subscription, of the group and of one resource of it."""
    host = re.escape(f"https://{ARM_HOST}")
    covered = (host + re.escape(f"/subscriptions/{scope.subscription}") + rf"(?:/resourceGroups/{re.escape(scope.group)}"
               rf"(?:/providers/[A-Za-z0-9.]{{1,80}}/[A-Za-z0-9]{{1,40}}/{NAME})?)?")
    return re.compile(covered + r"/providers/Microsoft\.Authorization/locks", re.I)


def _operations(scope: ChangeScope) -> "re.Pattern[str]":
    """The status of an asynchronous operation of Compute or Network in the subscription (Learn, "Status of asynchronous operations": the address that the header Azure-AsyncOperation or
    Location of the answer gives, under /subscriptions/<id>/providers/<provider>/locations/<region>/). It reads a status and changes nothing."""
    return re.compile(re.escape(f"https://{ARM_HOST}/subscriptions/{scope.subscription}/providers/") + r"(?:Microsoft\.Compute|Microsoft\.Network)/locations/[A-Za-z0-9]{1,40}"
                      r"/[A-Za-z]{3,30}/[A-Za-z0-9._~-]{1,100}", re.I)


def _usage(scope: ChangeScope) -> "re.Pattern[str]":
    return re.compile(re.escape(f"https://{ARM_HOST}/subscriptions/{scope.subscription}/providers/{COMPUTE}/locations/") + r"[A-Za-z0-9]{1,40}/usages", re.I)


def _once(calls: Sequence[tuple[str, "re.Pattern[str]"]]) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The same list without a call twice: two kinds of one collection (the disk is read and deleted with one api-version and read and moved with another) have one address."""
    seen: set[tuple[str, str]] = set()
    kept = []
    for method, pattern in calls:
        if (method, pattern.pattern) not in seen:
            seen.add((method, pattern.pattern))
            kept.append((method, pattern))
    return tuple(kept)


def read_patterns(scopes: Sequence[ChangeScope]) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of the reads that the checks make: each kind of resource in each scope, the sizes a machine can be resized to, the locks and the quota. No write."""
    calls: list[tuple[str, "re.Pattern[str]"]] = []
    for scope in scopes:
        calls += [(call.method, _pattern(scope, call)) for call in READS]
        calls += [(GET, _locks(scope)), (GET, _usage(scope))]
    return _once(calls)


def change_patterns(scopes: Sequence[ChangeScope]) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that a change makes with the approver's token: the reads, the writes of WRITES and the status of an asynchronous operation."""
    calls = list(read_patterns(scopes))
    for scope in scopes:
        calls += [(call.method, _pattern(scope, call)) for call in WRITES]
        calls.append((GET, _operations(scope)))
    return _once(calls)
