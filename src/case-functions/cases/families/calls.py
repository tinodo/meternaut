"""Every call that a family of change makes to Azure Resource Manager, in one place.

This is the one module of the families that names a method that writes. A person who wants to know everything that Meternaut can do to an estate reads `WRITES` below: eleven calls,
each on one kind of resource, each in a resource group of `CHANGE_SCOPES` (gates.py), each made with the token of the person who approved it and no other (AGENTS.md rule 29), and then one write more,
`RESOURCE_PUT`: the PUT of the one resource that an approved plan of the family `change-setting` names, in a group of `REAL_CHANGE_SCOPES`, which is on no list of kinds. It is made only by the client of
that one request (`one_write`), whose list holds no write and no other address than that resource's own, at the plan's own api-version, and which is never built while the owner's line in gates.py is off.
`READS` are what the checks before and after a change read. The lists that the HTTP client holds (`patterns`) are built from these tuples and from nothing else, so a call that is not here
cannot leave the app: the client refuses it before it is sent.

The api-versions are the ones that the REST reference of each call shows (Microsoft Learn, read on 2026-11-08). A call that has not changed since the first family keeps the version that
it had: the disk and the public IP address are deleted with the versions that were tested on a real estate on 2026-11-05. The api-version of `RESOURCE_PUT` is the one that the provider itself lists
(Learn, "Providers - Get", api-version 2021-04-01), the newest that is not a preview, read when the plan is made.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable, Sequence
from urllib.parse import urlsplit

from ..http import Client, Refused
from .gates import ChangeScope, Gates

ARM_HOST = "management.azure.com"
ARM_RESOURCE = "https://management.azure.com/"
GET, POST, PATCH, PUT, DELETE = "GET", "POST", "PATCH", "PUT", "DELETE"
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
# Learn, "P 2 s Vpn Gateways - Get" and "P 2 s Vpn Gateways - Create Or Update" (Virtual WAN REST reference, read on 2026-11-11): api-version 2026-01-01. A gateway's scale units are changed by
# the PUT only: the one PATCH of the resource ("Update Tags") changes tags and nothing else.
P2S_API = "2026-01-01"
# Learn, "Metrics - List" (read on 2026-11-11): api-version 2023-10-01, `timespan` as start/end, `interval` as an ISO 8601 duration, `aggregation` a comma separated list.
METRICS_API = "2023-10-01"

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
P2S_GATEWAY = Kind("microsoft.network/p2svpngateways", NETWORK, "p2svpnGateways", P2S_API)
KINDS = (DISK, DISK_TIER, PUBLIC_IP, VIRTUAL_MACHINE, SNAPSHOT, NETWORK_INTERFACE, NAT_GATEWAY, LOAD_BALANCER, PRIVATE_ENDPOINT, P2S_GATEWAY)


@dataclass(frozen=True)
class Call:
    """One call on a kind of resource: the method, the kind and what follows the name in the address."""

    method: str
    kind: Kind
    suffix: str = ""

    def url(self, scope: ChangeScope, name: str, query: str = "") -> str:
        extra = f"&{query}" if query else ""
        return f"https://{ARM_HOST}{self.kind.path(scope, name)}{self.suffix}?api-version={self.kind.api}{extra}"


# What follows the name of a resource in the address of its metrics (Learn, "Metrics - List"): the one read of a gateway that is not the gateway itself.
METRICS = "/providers/Microsoft.Insights/metrics"

# The reads: the resource itself, and what the checks of a family look at. No write.
READS = tuple(Call(GET, kind) for kind in KINDS) + (Call(GET, VIRTUAL_MACHINE, "/vmSizes"), Call(GET, P2S_GATEWAY, METRICS))

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
    Call(PUT, P2S_GATEWAY),  # Learn: P 2 s Vpn Gateways - Create Or Update. The one PUT: the body is the gateway as it was read, with one number changed (gateway.py). 200, or 201 with Azure-AsyncOperation.
)
DELETES = tuple(call for call in WRITES if call.method == DELETE)

# The one write that no list of kinds holds: Learn, "Resources - Create Or Update By Id" (the PUT of one resource, in the api-version that its provider lists). The body is the resource as it was read with
# the numbers of an approved plan changed (setting.py). It is made only through `one_write` below.
RESOURCE_PUT = Call(PUT, Kind("", "", "", ""))

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


def read_patterns(scopes: Sequence[ChangeScope], real: Sequence[ChangeScope] = ()) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of the reads that the checks make: each kind of resource in each scope, the sizes a machine can be resized to, the locks and the quota. No write.
    `real` (REAL_CHANGE_SCOPES) adds, for the groups of the owner's real resources only, the reads that the family `change-setting` makes (`real_reads`)."""
    calls: list[tuple[str, "re.Pattern[str]"]] = []
    for scope in scopes:
        calls += [(call.method, _pattern(scope, call)) for call in READS]
        calls += [(GET, _locks(scope)), (GET, _usage(scope))]
    return _once(calls + real_reads(real))


def change_patterns(scopes: Sequence[ChangeScope]) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that a change makes with the approver's token: the reads, the writes of WRITES and the status of an asynchronous operation. It holds
    nothing of the real groups: the change of the family `change-setting` is made with a client of its own (`one_write`)."""
    calls = list(read_patterns(scopes))
    for scope in scopes:
        calls += [(call.method, _pattern(scope, call)) for call in WRITES]
        calls.append((GET, _operations(scope)))
    return _once(calls)


# -- the family `change-setting`: reads in the groups of REAL_CHANGE_SCOPES, and the one write -----------------------------------------------------------------------------------------------------

# A resource provider's namespace, a collection and the id of a resource of the top level of a group (a child resource has more segments and is not changed here); the name cannot walk up an address.
PROVIDER = r"[A-Za-z][A-Za-z0-9]{0,39}(?:\.[A-Za-z][A-Za-z0-9]{0,39}){1,3}"
COLLECTION = r"[A-Za-z][A-Za-z0-9]{0,39}"
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
GROUP = r"[A-Za-z0-9._()-]{1,90}"
GENERIC_ID = re.compile(rf"/subscriptions/({GUID})/resourceGroups/({GROUP})/providers/({PROVIDER})/({COLLECTION})/({NAME})", re.I)
RELEASED = re.compile(r"\d{4}-\d{2}-\d{2}")  # an api-version that is not a preview
PROVIDERS_API = "2021-04-01"  # Learn, "Providers - Get": the api-versions of each resource type of a namespace


def _in(scope: ChangeScope, tail: str) -> "re.Pattern[str]":
    return re.compile(_base(scope) + tail, re.I)


def real_reads(scopes: Sequence[ChangeScope]) -> list[tuple[str, "re.Pattern[str]"]]:
    """The reads of the groups of REAL_CHANGE_SCOPES: one resource of any provider of the group, its metrics, the locks of the subscription, the group and a resource, and the list of the resource
    types of one provider in the subscription (their api-versions). No write: no pattern here has another method than GET."""
    found: list[tuple[str, "re.Pattern[str]"]] = []
    for scope in scopes:
        one = rf"/providers/{PROVIDER}/{COLLECTION}/{NAME}"
        found += [(GET, _in(scope, one)), (GET, _in(scope, one + "/providers/Microsoft\\.Insights/metrics")), (GET, _locks(scope)),
                  (GET, re.compile(re.escape(f"https://{ARM_HOST}/subscriptions/{scope.subscription}/providers/") + PROVIDER, re.I))]
    return found


def operation_reads(scope: ChangeScope, provider: str, collection: str, name: str) -> list[tuple[str, "re.Pattern[str]"]]:
    """The status of an asynchronous operation of one provider in one subscription (Learn, "Status of asynchronous operations"): under the subscription's locations of that provider, or under the
    resource itself. GET only."""
    ident = r"(?!\.{1,2}$)[A-Za-z0-9._~-]{1,100}"
    own = f"/providers/{re.escape(provider)}/{re.escape(collection)}/{re.escape(name)}"
    return [(GET, re.compile(re.escape(f"https://{ARM_HOST}/subscriptions/{scope.subscription}/providers/{provider}/locations/") + rf"[A-Za-z0-9]{{1,40}}/[A-Za-z]{{3,30}}/{ident}", re.I)),
            (GET, _in(scope, own + rf"/(?:operationResults|operationStatuses|operations)/{ident}"))]


def located_for(resource_id: str, gates: Gates) -> tuple[ChangeScope, Kind, str] | None:
    """The scope, the kind (with no api-version yet) and the name of a resource of the top level of a group of REAL_CHANGE_SCOPES; None for an id or a group that is not one."""
    found = GENERIC_ID.fullmatch(resource_id or "")
    if found is None:
        return None
    subscription, group, provider, collection, name = found.groups()
    scope = gates.real_scope_of(subscription, group)
    return None if scope is None else (scope, Kind(f"{provider}/{collection}".lower(), provider, collection, ""), name)


class OneWrite(Client):
    """The client of the ONE request that makes an approved plan of the family `change-setting` (AGENTS.md rule 29, with the approver's own token). Its list holds reads only, and its one write is a PUT
    to one address that is compared as a whole, the plan's own resource at the plan's own api-version: any other method, host, path, id or api-version is refused before it is sent. With no address
    (the owner's line is off, or the plan does not name a resource of a real group) it makes no write at all."""

    def __init__(self, put_url: str | None, allowed: Sequence[tuple[str, "re.Pattern[str]"]], redact: Callable[[str], str], **options) -> None:
        if any(method != GET for method, _ in allowed):
            raise ValueError("the list of the client of one change holds reads only")
        super().__init__(tuple(allowed), redact, **options)
        self.put_url = put_url

    def check(self, method: str, url: str) -> None:
        if method == PUT:
            if self.put_url is None or url != self.put_url:
                parts = urlsplit(url)
                raise Refused(f"the app makes no {method} call to {parts.netloc}{parts.path[:80]}")
            return
        super().check(method, url)


def one_write(resource_id: str, api: str, gates: Gates, redact: Callable[[str], str], **options) -> OneWrite:
    """The client for the change of one approved plan: reads of the real groups, the status of that resource's operations, and the one PUT of `resource_id` at `api`, only while the owner's line is on
    and the resource is in a real group (Gates.why_not_real). Otherwise it holds the reads and no write."""
    found = located_for(resource_id, gates)
    allowed = real_reads(gates.real_scopes)
    put = None
    if found is not None and RELEASED.fullmatch(api or ""):
        scope, kind, name = found
        allowed += operation_reads(scope, kind.provider, kind.collection, name)
        if gates.why_not_real(scope.subscription, scope.group) is None:
            put = Call(PUT, replace(kind, api=api)).url(scope, name)
    return OneWrite(put, _once(allowed), redact, **options)
