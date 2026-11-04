"""The detectors: Resource Graph queries and Azure Advisor, each turned into leads whose facts are typed.

A fact is a boolean, a number or a word from a fixed list. A name, a tag or a description of the estate is kept in the lead for the History
and for the guards, and never goes into a prompt (evidence.py checks that).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable

from .arm import Arm
from .http import HttpError

ADVISOR = "advisor-cost"
RECENT_DAYS = 7

# Every query starts with a comment that names it, so that a test (and a person reading the log of Resource Graph) can tell which one it is.
PRIVATE_ENDPOINT = """// meternaut:orphan-private-endpoint
resources
| where type =~ 'microsoft.network/privateendpoints'
| extend connections = array_concat(coalesce(todynamic(properties.privateLinkServiceConnections), dynamic([])), coalesce(todynamic(properties.manualPrivateLinkServiceConnections), dynamic([])))
| extend connections = iff(array_length(connections) == 0, dynamic([{}]), connections)
| mv-expand connection = connections
| summarize states = make_set(tostring(connection.properties.privateLinkServiceConnectionState.status)), groups = make_set(tostring(connection.properties.groupIds[0])), tags = take_any(tags), managedBy = take_any(tostring(managedBy)) by id, name, type, resourceGroup, subscriptionId, location
| where not(set_has_element(states, 'Approved'))
| project id, name, type, resourceGroup, subscriptionId, location, tags, managedBy, states, groups"""

MANAGED_DISK = """// meternaut:orphan-managed-disk
resources
| where type =~ 'microsoft.compute/disks'
| where isempty(managedBy) and tostring(properties.diskState) =~ 'Unattached'
| project id, name, type, resourceGroup, subscriptionId, location, tags, managedBy = tostring(managedBy), skuName = tostring(sku.name), sizeGb = toint(properties.diskSizeGB), timeCreated = tostring(properties.timeCreated)"""

PUBLIC_IP = """// meternaut:orphan-public-ip
resources
| where type =~ 'microsoft.network/publicipaddresses'
| where isnull(properties.ipConfiguration) and isnull(properties.natGateway) and isnull(properties.linkedPublicIPAddress)
| project id, name, type, resourceGroup, subscriptionId, location, tags, managedBy = tostring(managedBy), skuName = tostring(sku.name), allocation = tostring(properties.publicIPAllocationMethod)"""

LOAD_BALANCER = """// meternaut:load-balancer-without-backends
resources
| where type =~ 'microsoft.network/loadbalancers' and tostring(sku.name) =~ 'Standard'
| extend pools = coalesce(todynamic(properties.backendAddressPools), dynamic([]))
| extend poolCount = array_length(pools), ruleCount = coalesce(array_length(properties.loadBalancingRules), 0), frontendCount = coalesce(array_length(properties.frontendIPConfigurations), 0)
| extend pools = iff(poolCount == 0, dynamic([{}]), pools)
| mv-expand pool = pools
| extend members = coalesce(array_length(pool.properties.loadBalancerBackendAddresses), 0) + coalesce(array_length(pool.properties.backendIPConfigurations), 0)
| summarize backends = sum(members), poolCount = max(poolCount), ruleCount = max(ruleCount), frontendCount = max(frontendCount), skuName = take_any(tostring(sku.name)), tags = take_any(tags), managedBy = take_any(tostring(managedBy)) by id, name, type, resourceGroup, subscriptionId, location
| where backends == 0
| project id, name, type, resourceGroup, subscriptionId, location, tags, managedBy, skuName, poolCount, ruleCount, frontendCount"""

APP_SERVICE_PLAN = """// meternaut:empty-app-service-plan
resources
| where type =~ 'microsoft.web/serverfarms'
| where toint(properties.numberOfSites) == 0
| where tostring(sku.tier) !in~ ('Free', 'Shared', 'Dynamic', 'FlexConsumption')
| project id, name, type, resourceGroup, subscriptionId, location, tags, managedBy = tostring(managedBy), tier = tostring(sku.tier), workers = toint(properties.numberOfWorkers)"""

STOPPED_VM = """// meternaut:stopped-vm
resources
| where type =~ 'microsoft.compute/virtualmachines'
| where tostring(properties.extended.instanceView.powerState.code) =~ 'PowerState/stopped'
| project id, name, type, resourceGroup, subscriptionId, location, tags, managedBy = tostring(managedBy), vmSize = tostring(properties.hardwareProfile.vmSize)"""

# Context, read once for each subscription: what was created in the last seven days, and which resource groups a platform manages.
RECENT_CREATIONS = """// meternaut:recent-creations
resourcechanges
| extend changeTime = todatetime(properties.changeAttributes.timestamp), changeType = tostring(properties.changeType), targetId = tolower(tostring(properties.targetResourceId))
| where changeTime > ago(7d) and changeType =~ 'Create'
| project targetId"""

MANAGED_GROUPS = """// meternaut:managed-groups
resourcecontainers
| where type =~ 'microsoft.resources/subscriptions/resourcegroups'
| where isnotempty(tostring(managedBy))
| project name = tolower(name)"""

CONNECTION_STATES = frozenset({"approved", "pending", "rejected", "disconnected"})
TARGET_SERVICES = frozenset({
    "blob", "file", "queue", "table", "dfs", "web", "vault", "sqlserver", "sites", "namespace", "account", "sql", "registry", "searchservice", "iotdps",
    "webpubsub", "signalr", "redis", "rediscache", "mongodb", "cassandra", "gremlin", "managedhsm", "configurationstores", "postgresqlserver", "mysqlserver",
    "mariadbserver", "topic", "domain", "iothub", "amlworkspace", "grafana", "azuremonitor", "cosmos", "eventhub", "servicebus", "healthcareworkspace",
})
DISK_SKUS = frozenset({"standard_lrs", "standardssd_lrs", "premium_lrs", "ultrassd_lrs", "premiumv2_lrs", "standardssd_zrs", "premium_zrs"})
PLAN_TIERS = frozenset({"basic", "standard", "premium", "premiumv2", "premiumv3", "premiumv4", "isolated", "isolatedv2", "elasticpremium", "workflowstandard"})
VM_SIZE = re.compile(r"^Standard_[A-Za-z0-9_]{1,30}$")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
RESOURCE_GROUP = re.compile(r"/resourcegroups/([^/]+)", re.I)

# The closed vocabulary of the facts: every word that a detector may put in a fact, and the few shapes of the rest. A prompt holds nothing else.
FACT_WORDS = frozenset().union(CONNECTION_STATES, TARGET_SERVICES, DISK_SKUS, PLAN_TIERS,
                               {"basic", "standard", "static", "dynamic", "high", "medium", "low", "other", "none", "unknown", "unattached", "stopped", "cost"})
FACT_SHAPES = (re.compile(r"^(up to|over) \d{1,5}$"), VM_SIZE, GUID)


def is_fact_word(value: str) -> bool:
    return value in FACT_WORDS or any(shape.match(value) for shape in FACT_SHAPES)


@dataclass
class Lead:
    detector: str
    resource_id: str
    resource_type: str
    name: str
    resource_group: str
    subscription_id: str
    location: str
    tags: dict[str, str]
    managed_by: str
    facts: dict
    age_days: int | None = None
    advisor_saving_usd: float | None = None
    cost_usd_30d: float | None = None

    @property
    def lead_id(self) -> str:
        return hashlib.sha256(f"{self.detector}|{self.resource_id.lower()}".encode("utf-8")).hexdigest()[:12]


@dataclass
class Context:
    """What the guards and the ranking need for one subscription. None means that it could not be read."""

    locks: list[str] | None = None
    recent: set[str] | None = None
    managed_groups: set[str] | None = None
    costs: dict[str, float] | None = None
    currency: str | None = None


@dataclass
class Collected:
    leads: list[Lead]
    context: Context
    sources_read: int
    sources_failed: int


def pick(value: object, allowed: frozenset[str], other: str = "other") -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else other


def bucket(number: object, edges: tuple[int, ...] = (32, 128, 512, 1024)) -> str:
    try:
        value = int(number)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return "unknown"
    for edge in edges:
        if value <= edge:
            return f"up to {edge}"
    return f"over {edges[-1]}"


def whole(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


def age_of(text: object, now: dt.datetime) -> int | None:
    try:
        created = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=dt.timezone.utc)
    return max(0, (now - created).days)


def _lead(detector: str, row: dict, facts: dict, age_days: int | None = None) -> Lead | None:
    resource_id = str(row.get("id") or "")
    if not resource_id.lower().startswith("/subscriptions/"):
        return None
    raw_tags = row.get("tags")
    tags = {str(k): str(v) for k, v in raw_tags.items()} if isinstance(raw_tags, dict) else {}
    return Lead(detector=detector, resource_id=resource_id, resource_type=str(row.get("type") or "").lower(), name=str(row.get("name") or ""),
                resource_group=str(row.get("resourceGroup") or ""), subscription_id=str(row.get("subscriptionId") or "").lower(),
                location=str(row.get("location") or ""), tags=tags, managed_by=str(row.get("managedBy") or ""), facts=facts, age_days=age_days)


def _private_endpoint(row: dict, now: dt.datetime) -> Lead | None:
    states = sorted({pick(s, CONNECTION_STATES) for s in (row.get("states") or []) if str(s).strip()}) or ["none"]
    groups = [g for g in (row.get("groups") or []) if str(g).strip()]
    return _lead("orphan-private-endpoint", row, {"connectionStates": states, "targetService": pick(groups[0] if groups else "", TARGET_SERVICES)})


def _managed_disk(row: dict, now: dt.datetime) -> Lead | None:
    age = age_of(row.get("timeCreated"), now)
    return _lead("orphan-managed-disk", row, {"diskState": "unattached", "sku": pick(row.get("skuName"), DISK_SKUS), "sizeGb": bucket(row.get("sizeGb")), "ageDays": age}, age)


def _public_ip(row: dict, now: dt.datetime) -> Lead | None:
    return _lead("orphan-public-ip", row, {"sku": pick(row.get("skuName"), frozenset({"basic", "standard"})),
                                           "allocation": pick(row.get("allocation"), frozenset({"static", "dynamic"}))})


def _load_balancer(row: dict, now: dt.datetime) -> Lead | None:
    return _lead("load-balancer-without-backends", row, {"sku": "standard", "backendPools": whole(row.get("poolCount")),
                                                         "loadBalancingRules": whole(row.get("ruleCount")), "frontends": whole(row.get("frontendCount"))})


def _plan(row: dict, now: dt.datetime) -> Lead | None:
    return _lead("empty-app-service-plan", row, {"tier": pick(row.get("tier"), PLAN_TIERS), "workers": whole(row.get("workers"))})


def _vm(row: dict, now: dt.datetime) -> Lead | None:
    size = str(row.get("vmSize") or "")
    return _lead("stopped-vm", row, {"powerState": "stopped", "size": size if VM_SIZE.match(size) else "other"})


@dataclass(frozen=True)
class Detector:
    name: str
    query: str
    build: Callable[[dict, dt.datetime], "Lead | None"]


DETECTORS = (
    Detector("orphan-private-endpoint", PRIVATE_ENDPOINT, _private_endpoint),
    Detector("orphan-managed-disk", MANAGED_DISK, _managed_disk),
    Detector("orphan-public-ip", PUBLIC_IP, _public_ip),
    Detector("load-balancer-without-backends", LOAD_BALANCER, _load_balancer),
    Detector("empty-app-service-plan", APP_SERVICE_PLAN, _plan),
    Detector("stopped-vm", STOPPED_VM, _vm),
)
DETECTOR_NAMES = tuple(d.name for d in DETECTORS) + (ADVISOR,)


def advisor_lead(recommendation: dict, subscription: str) -> Lead | None:
    properties = recommendation.get("properties")
    if not isinstance(properties, dict):
        return None
    metadata = properties.get("resourceMetadata") if isinstance(properties.get("resourceMetadata"), dict) else {}
    resource_id = str(metadata.get("resourceId") or "")
    if not resource_id.lower().startswith("/subscriptions/"):
        resource_id = f"/subscriptions/{subscription}"
    group = RESOURCE_GROUP.search(resource_id)
    extended = properties.get("extendedProperties") if isinstance(properties.get("extendedProperties"), dict) else {}
    saving = None
    try:
        if str(extended.get("savingsCurrency", "")).upper() == "USD":
            saving = round(float(extended.get("annualSavingsAmount")) / 12, 2)
    except (TypeError, ValueError):
        saving = None
    type_id = str(properties.get("recommendationTypeId") or "")
    facts = {"category": "cost", "impact": pick(properties.get("impact"), frozenset({"high", "medium", "low"})),
             "recommendationType": type_id.lower() if GUID.match(type_id) else "none"}
    return Lead(detector=ADVISOR, resource_id=resource_id, resource_type=str(properties.get("impactedField") or "").lower(),
                name=str(properties.get("impactedValue") or ""), resource_group=group.group(1) if group else "", subscription_id=subscription.lower(),
                location="", tags={}, managed_by="", facts=facts, advisor_saving_usd=saving)


def collect(arm: Arm, subscription: str, now: dt.datetime, notes: list[str]) -> Collected:
    """Every lead of one subscription, with the context for the guards and the cost lines. A source that cannot be read is a note, not a stop."""
    today = now.date()
    leads: list[Lead] = []
    context = Context()
    read = failed = 0

    def note(source: str, error: Exception) -> None:
        notes.append(f"{subscription[:8]}: {source} could not be read ({str(error)[:200]})")

    for detector in DETECTORS:
        try:
            rows = arm.graph(subscription, detector.query)
        except HttpError as error:
            failed += 1
            note(detector.name, error)
            continue
        read += 1
        for row in rows:
            lead = detector.build(row, now)
            if lead:
                leads.append(lead)
    try:
        for recommendation in arm.advisor_cost(subscription):
            lead = advisor_lead(recommendation, subscription)
            if lead:
                leads.append(lead)
        read += 1
    except HttpError as error:
        failed += 1
        note(ADVISOR, error)
    try:
        context.locks = arm.locks(subscription)
    except HttpError as error:
        note("management locks", error)
    try:
        context.recent = {str(row.get("targetId", "")).lower() for row in arm.graph(subscription, RECENT_CREATIONS)}
    except HttpError as error:
        note("recent creations", error)
    try:
        context.managed_groups = {str(row.get("name", "")).lower() for row in arm.graph(subscription, MANAGED_GROUPS)}
    except HttpError as error:
        note("managed resource groups", error)
    try:
        context.costs, context.currency = arm.costs(subscription, today - dt.timedelta(days=30), today - dt.timedelta(days=1))
    except HttpError as error:
        note("cost lines", error)
    return Collected(leads, context, read, failed)


def rank(leads: list[Lead], contexts: dict[str, Context]) -> list[Lead]:
    """One lead for each resource (a Resource Graph detector before Advisor), each with its 30-day cost, dearest first."""
    seen: set[str] = set()
    unique: list[Lead] = []
    for lead in sorted(leads, key=lambda l: (l.detector == ADVISOR, l.detector, l.resource_id.lower())):
        key = lead.resource_id.lower()
        if key not in seen:
            seen.add(key)
            unique.append(lead)
    for lead in unique:
        context = contexts.get(lead.subscription_id)
        if context and context.costs is not None and context.currency == "USD":
            lead.cost_usd_30d = round(context.costs.get(lead.resource_id.lower(), 0.0), 2)
    return sorted(unique, key=lambda l: (-(l.cost_usd_30d or 0.0), l.detector, l.resource_id.lower()))
