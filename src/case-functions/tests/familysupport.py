"""A fake Azure Resource Manager for the tests of the families of change, and the parts of the loop around it. Everything in it is invented.

The fake answers like Azure does for what the families ask: a resource with its tags and properties, the locks of a scope, the sizes that a machine can take, the quota of a region, the
status of an operation, and the writes of the families (a delete, the deallocate of a machine, an update of a machine or of a disk). A write is carried out later, as Azure does: the
resource shows the effect after a number of reads, and the answer of the write says 202 with the address of the operation unless the test says otherwise.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, replace
from typing import Callable
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from support import APP_ROOT  # noqa: F401

from cases.approvals import Approvals, ApprovalSettings
from cases.detectors import Lead
from cases.families import digest as plan_digest
from cases.families.azure import Azure
from cases.families.gates import ChangeScope
from cases.http import Client, HttpError
from cases.memory_store import MemoryStore, stamp
from cases.models import ActionRecord, CaseRecord, PlanRecord, Principal
from cases.runner import Executed, RunnerServices, change_calls, execute, read_calls, tick

OID = "aaaaaaaa-1111-4222-8333-444444444444"
OTHER = "11111111-2222-3333-4444-555555555555"
SUB = "bbbbbbbb-2222-4333-9444-555555555555"
OTHER_SUB = "cccccccc-3333-4444-8555-666666666666"
GROUP = "meternaut-fam-rg"
REGION = "swedencentral"
NOW = dt.datetime(2026, 11, 8, 9, 0, 0, tzinfo=dt.timezone.utc)
SCOPES = (ChangeScope(SUB, GROUP),)
SETTINGS = ApprovalSettings(change_scopes=SCOPES)
APPROVER = Principal(OID, "Tino", ("owner", "approver", "ops"))
PLANTED = {"meternaut-planted": "demo"}
VM_API, DISK_API, NETWORK_API = "2026-04-01", "2026-03-02", "2026-01-01"

# short name -> (provider, collection, the type as Resource Graph names it)
KINDS = {
    "disk": ("Microsoft.Compute", "disks", "microsoft.compute/disks"),
    "vm": ("Microsoft.Compute", "virtualMachines", "microsoft.compute/virtualmachines"),
    "snapshot": ("Microsoft.Compute", "snapshots", "microsoft.compute/snapshots"),
    "ip": ("Microsoft.Network", "publicIPAddresses", "microsoft.network/publicipaddresses"),
    "nic": ("Microsoft.Network", "networkInterfaces", "microsoft.network/networkinterfaces"),
    "nat": ("Microsoft.Network", "natGateways", "microsoft.network/natgateways"),
    "lb": ("Microsoft.Network", "loadBalancers", "microsoft.network/loadbalancers"),
    "pe": ("Microsoft.Network", "privateEndpoints", "microsoft.network/privateendpoints"),
    "p2s": ("Microsoft.Network", "p2svpnGateways", "microsoft.network/p2svpngateways"),
}
NAMES = {"disk": "planted-disk-1", "vm": "planted-vm-1", "snapshot": "planted-snapshot-1", "ip": "planted-ip-1", "nic": "planted-nic-1", "nat": "planted-nat-1", "lb": "planted-lb-1",
         "pe": "planted-pe-1", "p2s": "planted-p2s-1"}
# The planted list holds no gateway and none may be added (AGENTS.md rule 15 (g): a virtual hub costs about 450 US dollars a month). A test module that exercises the family of gateways holds
# this entry in place for the time of the module, as if a planting existed, and a test of its own says that the real list has none.
GATEWAY_PLANTED = {"microsoft.network/p2svpngateways": re.compile(r"planted-p2s-[a-z0-9]{1,12}")}


def as_if_gateways_were_planted():
    return mock.patch.dict("cases.families.gates.PLANTED_NAMES", GATEWAY_PLANTED)


def rid(kind: str, name: str | None = None, group: str = GROUP, subscription: str = SUB) -> str:
    provider, collection, _ = KINDS[kind]
    return f"/subscriptions/{subscription}/resourceGroups/{group}/providers/{provider}/{collection}/{name or NAMES[kind]}"


def operation_url(operation: str = "op-1", region: str = REGION) -> str:
    return f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Compute/locations/{region}/operations/{operation}?api-version={VM_API}"


def power_statuses(power: str) -> list[dict]:
    return [{"code": "ProvisioningState/succeeded"}, {"code": f"PowerState/{power}"}]


def vm(name: str = "planted-vm-1", size: str = "Standard_D4s_v5", power: str = "running", provisioning: str = "Succeeded", tags: dict | None = None, **more) -> dict:
    resource = {"id": rid("vm", name), "name": name, "location": REGION, "tags": dict(PLANTED if tags is None else tags),
                "properties": {"hardwareProfile": {"vmSize": size}, "provisioningState": provisioning, "instanceView": {"statuses": power_statuses(power)}}}
    resource.update(more)
    return resource


def disk(name: str = "planted-disk-1", sku: str = "Premium_LRS", state: str = "Unattached", managed_by: str = "", tags: dict | None = None, size_gb: int | None = 4, **more) -> dict:
    resource = {"id": rid("disk", name), "name": name, "location": REGION, "tags": dict(PLANTED if tags is None else tags), "sku": {"name": sku},
                "properties": {"diskState": state, "provisioningState": "Succeeded"}}
    if size_gb is not None:
        resource["properties"]["diskSizeGB"] = size_gb
    if managed_by:
        resource["managedBy"] = managed_by
    resource.update(more)
    return resource


def simple(kind: str, name: str | None = None, tags: dict | None = None, properties: dict | None = None, **more) -> dict:
    resource = {"id": rid(kind, name), "name": name or NAMES[kind], "location": REGION, "tags": dict(PLANTED if tags is None else tags), "properties": dict(properties or {})}
    resource.update(more)
    return resource


def p2s(name: str = "planted-p2s-1", units: int = 12, provisioning: str = "Succeeded", tags: dict | None = None, **more) -> dict:
    """A point-to-site gateway as Azure shows it (Learn, "P 2 s Vpn Gateways - Get"), with what Azure fills in itself and what a person set: a connection configuration, DNS servers, the hub."""
    path = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Network"
    resource = {"id": rid("p2s", name), "name": name, "type": "Microsoft.Network/p2sVpnGateways", "etag": 'W/"11111111-2222-3333-4444-555555555555"', "location": REGION,
                "tags": dict(PLANTED if tags is None else tags),
                "properties": {"vpnGatewayScaleUnit": units, "provisioningState": provisioning, "isRoutingPreferenceInternet": False, "customDnsServers": ["10.0.0.4"],
                               "virtualHub": {"id": f"{path}/virtualHubs/hub-1"}, "vpnServerConfiguration": {"id": f"{path}/vpnServerConfigurations/config-1"},
                               "vpnClientConnectionHealth": {"vpnClientConnectionsCount": 0, "allocatedIpAddresses": [], "totalIngressBytesTransferred": 0, "totalEgressBytesTransferred": 0},
                               "p2SConnectionConfigurations": [{"name": "default", "id": f"{path}/p2sVpnGateways/{name}/p2sConnectionConfigurations/default",
                                                                "etag": 'W/"11111111-2222-3333-4444-666666666666"',
                                                                "properties": {"enableInternetSecurity": False, "provisioningState": "Succeeded", "previousConfigurationPolicyGroupAssociations": [],
                                                                               "vpnClientAddressPool": {"addressPrefixes": ["10.99.0.0/24"]},
                                                                               "routingConfiguration": {"associatedRouteTable": {"id": f"{path}/virtualHubs/hub-1/hubRouteTables/default"}}}}]}}
    resource.update(more)
    return resource


def sizes_of(*rows: tuple[str, int, int]) -> list[dict]:
    """The list that Azure gives for a machine: (name, cores, memory in MB)."""
    return [{"name": name, "numberOfCores": cores, "memoryInMB": memory, "osDiskSizeInMB": 1047552, "resourceDiskSizeInMB": 65536, "maxDataDiskCount": 8} for name, cores, memory in rows]


D_SERIES = sizes_of(("Standard_D2s_v5", 2, 8192), ("Standard_D4s_v5", 4, 16384), ("Standard_D8s_v5", 8, 32768), ("Standard_E4s_v5", 4, 32768), ("Standard_B2s", 2, 4096))


@dataclass
class Effect:
    """What a write does to a resource once enough reads have been made."""

    reads: int
    apply: Callable[[dict | None], dict | None]


class Arm:
    """Resource Manager for the calls of the families. `resources` holds the resources by their lower-case id."""

    def __init__(self) -> None:
        self.resources: dict[str, dict] = {}
        self.locks: dict[str, list] = {}
        self.sizes: dict[str, list[dict]] = {}
        self.usage: dict[str, tuple[int, int]] = {REGION: (10, 100)}
        self.effects: dict[str, Effect] = {}
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[object] = []
        self.headers: list[dict] = []
        self.write_answers: list[tuple[int, dict, bytes]] = []  # the answers of the next writes, one each, before the defaults apply
        self.reads_before_effect = 1
        self.async_writes = True
        self.via = "both"  # which headers an asynchronous answer carries: Azure-AsyncOperation, Location, both or none
        self.provisioning_in_body = False  # an answer that says 200 and a provisioning state that is not final
        self.delete_status = 200
        self.operation_polls = ["InProgress", "Succeeded"]  # what the status of the operation says at each look; the last one stays
        self.operation_error: dict | None = None
        self.operation_http_status = 200
        self.operation_looks = 0
        self.read_status = 200
        self.read_headers: dict = {}
        self.locks_status = 200
        self.sizes_status = 200
        self.usage_status = 200
        self.resize_fails = False
        self.resize_never = False
        self.stop_never = False
        self.tier_never = False
        self.units_never = False  # a PUT of a gateway that is accepted and never shows its effect
        self.units_fail = False  # a PUT of a gateway whose operation ends as Failed
        self.connections: dict[str, list[float | None]] = {}  # the daily highest connection count of a gateway, by its lower-case id: 7 days, None for a day with no value; default: 7 days of 0
        self.metrics_status = 200
        self.metrics_body: bytes | None = None  # an answer of another shape, for a test of it
        self.url = ""
        self.hold_after: Callable[[str, str], None] | None = None  # called with (method, key) after each call, for a test that changes the estate while a change is made

    # -- the estate -----------------------------------------------------------------------------------------------------------------------------------

    def add(self, resource: dict) -> dict:
        self.resources[resource["id"].lower()] = resource
        return resource

    def get(self, resource_id: str) -> dict:
        return self.resources[resource_id.lower()]

    def writes(self) -> list[tuple[str, str]]:
        return [(method, url) for method, url in self.calls if method != "GET"]

    def writes_of(self, method: str) -> list[str]:
        return [url for m, url in self.calls if m == method]

    # -- the transport ----------------------------------------------------------------------------------------------------------------------------------

    def transport(self, method, url, headers, data, timeout):
        self.calls.append((method, url))
        self.url = url
        self.headers.append(dict(headers))
        self.bodies.append(json.loads(data.decode("utf-8")) if data else None)
        key = urlsplit(url).path.lower()
        answer = self.answer(method, key, self.bodies[-1])
        if method == "GET" and "$expand=instanceView" not in url and answer[0] == 200:
            answer = self.without_instance_view(answer)  # Azure shows a machine's power state only when the read asks for its instance view
        if self.hold_after is not None:
            self.hold_after(method, key)
        return answer

    @staticmethod
    def without_instance_view(answer):
        status, headers, body = answer
        found = json.loads(body)
        if isinstance(found, dict) and isinstance(found.get("properties"), dict):
            found["properties"].pop("instanceView", None)
        return status, headers, json.dumps(found).encode()

    def answer(self, method: str, key: str, body):
        if "/providers/microsoft.authorization/locks" in key:
            if self.locks_status >= 300:
                return self.locks_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to read the locks"}}'
            scope = key.split("/providers/microsoft.authorization/locks")[0]
            return 200, {}, json.dumps({"value": self.locks.get(scope, [])}).encode()
        if "/operations/" in key and "/locations/" in key:
            return self.operation(key)
        if key.endswith("/providers/microsoft.insights/metrics"):
            return self.metrics(key[:-len("/providers/microsoft.insights/metrics")])
        if key.endswith("/usages"):
            if self.usage_status >= 300:
                return self.usage_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right"}}'
            region = key.split("/locations/")[1].split("/")[0]
            used, limit = self.usage.get(region, (0, 0))
            return 200, {}, json.dumps({"value": [{"name": {"value": "cores"}, "currentValue": used, "limit": limit}, {"name": {"value": "availabilitySets"}, "currentValue": 0, "limit": 2500}]}).encode()
        if key.endswith("/vmsizes"):
            if self.sizes_status >= 300:
                return self.sizes_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right"}}'
            return 200, {}, json.dumps({"value": self.sizes.get(key[:-len("/vmsizes")], [])}).encode()
        if method == "GET":
            return self.read(key)
        return self.write(method, key, body)

    def read(self, key: str):
        if self.read_status >= 300:
            return self.read_status, dict(self.read_headers), b'{"error":{"code":"AuthorizationFailed","message":"no right to read"}}'
        effect = self.effects.get(key)
        if effect is not None:
            effect.reads -= 1
            if effect.reads < 0:
                del self.effects[key]
                changed = effect.apply(self.resources.get(key))
                if changed is None:
                    self.resources.pop(key, None)
        if key not in self.resources:
            return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
        return 200, {}, json.dumps(self.resources[key]).encode()

    def metrics(self, key: str):
        """The daily highest connection count of a gateway (Azure Monitor, Metrics - List) for the days of the timespan that was asked for, one bucket for each day from its start."""
        if self.metrics_status >= 300:
            return self.metrics_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to read the metrics"}}'
        if self.metrics_body is not None:
            return 200, {}, self.metrics_body
        span = parse_qs(urlsplit(self.url).query).get("timespan", [""])[0]
        first = dt.datetime.strptime(span.split("/")[0], "%Y-%m-%dT%H:%M:%SZ")
        values = self.connections.get(key, [0.0] * 7)
        data = [{"timeStamp": (first + dt.timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ"), **({} if value is None else {"maximum": value})} for n, value in enumerate(values)]
        return 200, {}, json.dumps({"value": [{"errorCode": "Success", "name": {"value": "P2SConnectionCount"}, "unit": "Count", "timeseries": [{"data": data}]}]}).encode()

    def operation(self, key: str):
        self.operation_looks += 1
        if self.operation_http_status >= 300:
            return self.operation_http_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to read the operation"}}'
        status = self.operation_polls[min(self.operation_looks - 1, len(self.operation_polls) - 1)]
        body: dict = {"name": "op-1", "status": status}
        if status == "Failed":
            body["error"] = self.operation_error or {"code": "AllocationFailed", "message": "no room for the size at this moment"}
        return 200, {}, json.dumps(body).encode()

    def started(self, status: int | None = None) -> tuple[int, dict, bytes]:
        """The answer of a write that Azure carries out later."""
        if not self.async_writes:
            return (status or 200), {}, b"{}"
        headers: dict = {"Retry-After": "1"}
        if self.via in ("both", "Azure-AsyncOperation"):
            headers["Azure-AsyncOperation"] = operation_url()
        if self.via in ("both", "Location"):
            headers["Location"] = operation_url("op-2")
        body = b'{"properties":{"provisioningState":"Updating"}}' if self.provisioning_in_body else b"{}"
        return (status or 202), headers, body

    def write(self, method: str, key: str, body):
        if self.write_answers:
            status, answer_headers, answer = self.write_answers.pop(0)
            if status >= 300:
                return status, dict(answer_headers), answer
        base_key = key[:-len("/deallocate")] if key.endswith("/deallocate") else key
        if base_key not in self.resources:
            return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
        resource = self.resources[base_key]
        if method == "DELETE":
            self.effects[key] = Effect(self.reads_before_effect, lambda found: None)
            return self.delete_status, {}, b""
        properties = resource.setdefault("properties", {})
        if method == "POST" and key.endswith("/deallocate"):
            resource["properties"]["instanceView"] = {"statuses": power_statuses("deallocating")}
            if not self.stop_never:
                self.effects[base_key] = Effect(self.reads_before_effect, lambda found: self.set_power(found, "deallocated"))
            return self.started()
        if method == "PATCH" and "/virtualmachines/" in key:
            want = body["properties"]["hardwareProfile"]["vmSize"]
            properties["hardwareProfile"]["vmSize"] = want
            properties["provisioningState"] = "Updating"
            if not self.resize_never:
                self.effects[key] = Effect(self.reads_before_effect, lambda found: self.set_provisioning(found, "Failed" if self.resize_fails else "Succeeded"))
            return self.started()
        if method == "PATCH" and "/disks/" in key:
            resource["sku"] = {"name": body["sku"]["name"]}
            properties["provisioningState"] = "Updating"
            if not self.tier_never:
                self.effects[key] = Effect(self.reads_before_effect, lambda found: self.set_provisioning(found, "Succeeded"))
            return self.started()
        if method == "PUT" and "/p2svpngateways/" in key:
            # A PUT states the whole gateway: what it does not state is gone. The stored gateway is what was sent, with what Azure fills in itself.
            stated = {"id": resource["id"], "name": resource["name"], "type": resource["type"], "etag": resource["etag"], **body}
            stated["properties"] = {**body["properties"], "provisioningState": "Updating"}
            self.resources[base_key] = stated
            if not self.units_never:
                self.effects[key] = Effect(self.reads_before_effect, lambda found: self.set_provisioning(found, "Failed" if self.units_fail else "Succeeded"))
            return self.started(201)
        return 405, {}, b"{}"

    @staticmethod
    def set_power(found: dict | None, power: str) -> dict | None:
        if found is not None:
            found["properties"]["instanceView"] = {"statuses": power_statuses(power)}
        return found

    @staticmethod
    def set_provisioning(found: dict | None, state: str) -> dict | None:
        if found is not None:
            found["properties"]["provisioningState"] = state
        return found


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += dt.timedelta(**kwargs)


class FakeCosts:
    """Cost Management for the check that the cost lines confirm a saving: `totals` is what the lines hold for each resource after the change, whatever the days that are asked for.

    A test that needs the days to count gives `days` instead: {a date: {a resource id in lower case: its cost that day}}, and the answer adds up the days from start to end (both included),
    as Cost Management does. `asked` is every (subscription, start, end) that was asked for."""

    def __init__(self, totals: dict | None = None, fail: bool = False, days: dict | None = None) -> None:
        self.totals, self.fail, self.days, self.asked = totals or {}, fail, days, []

    def costs(self, subscription, start, end):
        self.asked.append((subscription, start, end))
        if self.fail:
            raise HttpError(500, "boom")
        if self.days is None:
            return self.totals, "USD"
        summed: dict[str, float] = {}
        for day, lines in self.days.items():
            if start <= day <= end:
                for resource, amount in lines.items():
                    summed[resource] = summed.get(resource, 0.0) + amount
        return summed, "USD"


class World:
    """The loop around the families: a store, the approvals with a reader, the runner of the person's token, and the runner of the timer."""

    def __init__(self, arm: Arm | None = None, settings: ApprovalSettings = SETTINGS, reader: bool = True) -> None:
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.arm = arm or Arm()
        self.settings = settings
        self.events: list[tuple[str, dict]] = []
        self.sleeps: list[float] = []
        self.person_tokens: list[str] = []
        self.reader_tokens: list[str] = []
        self.costs = FakeCosts()
        self.reader = Azure(self.client(read_calls(settings.change_scopes)), lambda resource: (self.reader_tokens.append(resource), "reader-token")[1]) if reader else None
        self.approvals = Approvals(self.store, settings, self.clock, reader=self.reader)
        emit = lambda kind, **fields: self.events.append((kind, fields))  # noqa: E731
        person = lambda resource: (self.person_tokens.append(resource), "person-token")[1]  # noqa: E731
        self.s = RunnerServices(self.store, self.client(change_calls(settings.change_scopes)), person, settings, clock=self.clock, sleep=self.sleeps.append, emit=emit)
        self.t = RunnerServices(self.store, self.client(read_calls(settings.change_scopes)), lambda resource: (self.reader_tokens.append(resource), "reader-token")[1], settings,
                                arm=self.costs, clock=self.clock, sleep=self.sleeps.append, emit=emit)

    def client(self, calls) -> Client:
        return Client(calls, lambda text: text, transport=self.arm.transport, sleep=lambda seconds: None, monotonic=lambda: 0.0)

    # -- findings and plans -----------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def lead(resource: dict, kind: str, detector: str = "investigation", group: str = GROUP, subscription: str = SUB) -> Lead:
        return Lead(detector=detector, resource_id=resource["id"], resource_type=KINDS[kind][2], name=resource["name"], resource_group=group, subscription_id=subscription,
                    location=REGION, tags=dict(resource.get("tags") or {}), managed_by=str(resource.get("managedBy", "")), facts={}, age_days=30)

    def case(self, lead: Lead, recommendation: str = "delete", cost: float | None = None, **more) -> CaseRecord:
        values = dict(case_id="k" + lead.lead_id, resource_id=lead.resource_id, resource_name=lead.name, resource_type=lead.resource_type, resource_group=lead.resource_group,
                      subscription_id=lead.subscription_id, detector=lead.detector, run_id="r1", status="proposed", recommendation=recommendation, confidence=0.9,
                      cost_usd_30d=cost, saving_usd_month=cost, summary="the model said so", updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        values.update(more)
        case = CaseRecord(**values)
        self.store.case_put(case)
        return case

    def plan(self, resource: dict, kind: str, recommendation: str = "delete", cost: float | None = None, detector: str = "investigation", **more) -> PlanRecord | None:
        """The plan that the approvals make for a finding about the resource (None when they make none)."""
        item = self.lead(resource, kind, detector)
        return self.approvals.create(self.case(item, recommendation, cost, **more), item, (OID,))

    def approve(self, plan: PlanRecord) -> ActionRecord:
        """A person's approval at the sign-in to Azure: the decision is recorded and the action waits to be made."""
        checked, refusal = self.approvals.check_approve(APPROVER, plan.plan_id, plan.code)
        assert refusal is None, refusal
        result, action = self.approvals.record_approval(APPROVER, checked, "")
        assert result.kind == "recorded", result
        return action

    def approved(self, resource: dict, kind: str, recommendation: str = "delete", cost: float | None = None, detector: str = "investigation",
                 mutate: dict | None = None) -> tuple[PlanRecord, ActionRecord]:
        """A plan that a person approved. `mutate` changes fields of the plan before the approval, and seals it again, so that what is approved is that plan: only the re-check of the
        family and the gates of the runner can stop it then."""
        plan = self.plan(resource, kind, recommendation, cost, detector)
        assert plan is not None, "no plan was made"
        if mutate:
            plan = plan_digest.sealed(replace(plan, **mutate))
            self.store.plan_put(plan)
        return plan, self.approve(plan)

    def run(self, plan: PlanRecord, digest: str | None = None) -> Executed:
        """Makes the change of the plan with the token of the person, as the sign-in to Azure does."""
        return execute(self.s, self.store.action_get(plan.plan_id), approved_digest=plan.digest if digest is None else digest)

    def tick(self):
        return tick(self.t)

    def action(self, plan: PlanRecord) -> ActionRecord:
        return self.store.action_get(plan.plan_id)

    def state(self, plan: PlanRecord) -> tuple[str, str, str]:
        """The state of the plan, of its action and of its case."""
        return self.store.plan_get(plan.plan_id).state, self.action(plan).state, self.store.case_get(plan.case_id).status


def changed(plan: PlanRecord, **fields) -> PlanRecord:
    return replace(plan, **fields)
