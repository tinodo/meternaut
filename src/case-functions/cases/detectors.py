"""The detectors: Resource Graph queries and Azure Advisor, each turned into leads whose facts are typed.

A fact is a boolean, a number or a word from a fixed list. A name, a tag or a description of the estate is kept in the lead for the History
and for the guards, and never goes into a prompt (evidence.py checks that).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence

from . import costs as cost_words
from . import estimate as estimates
from .arm import Arm, ScopeCost
from .http import HttpError
from .identity import IdentityError
from .roles import clean_text

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

# Context, read once for each subscription: what was created in the last seven days, and which resource groups a platform manages. A query that runs for several subscriptions at once
# names the subscription of a row in its `targetId` and its `id`.
RECENT_CREATIONS = """// meternaut:recent-creations
resourcechanges
| extend changeTime = todatetime(properties.changeAttributes.timestamp), changeType = tostring(properties.changeType), targetId = tolower(tostring(properties.targetResourceId))
| where changeTime > ago(7d) and changeType =~ 'Create'
| project targetId"""

MANAGED_GROUPS = """// meternaut:managed-groups
resourcecontainers
| where type =~ 'microsoft.resources/subscriptions/resourcegroups'
| where isnotempty(tostring(managedBy))
| project id = tolower(id), name = tolower(name)"""

CONNECTION_STATES = frozenset({"approved", "pending", "rejected", "disconnected"})
TARGET_SERVICES = frozenset({
    "blob", "file", "queue", "table", "dfs", "web", "vault", "sqlserver", "sites", "namespace", "account", "sql", "registry", "searchservice", "iotdps",
    "webpubsub", "signalr", "redis", "rediscache", "mongodb", "cassandra", "gremlin", "managedhsm", "configurationstores", "postgresqlserver", "mysqlserver",
    "mariadbserver", "topic", "domain", "iothub", "amlworkspace", "grafana", "azuremonitor", "cosmos", "eventhub", "servicebus", "healthcareworkspace",
})
DISK_SKUS = frozenset({"standard_lrs", "standardssd_lrs", "premium_lrs", "ultrassd_lrs", "premiumv2_lrs", "standardssd_zrs", "premium_zrs"})
PLAN_TIERS = frozenset({"basic", "standard", "premium", "premiumv2", "premiumv3", "premiumv4", "isolated", "isolatedv2", "elasticpremium", "workflowstandard"})
VM_FAMILY = re.compile(r"^Standard_([A-Za-z]{1,3})([0-9]{1,3})")
VM_FAMILIES = frozenset({"a", "b", "d", "dc", "dl", "dp", "e", "ec", "ep", "f", "fx", "g", "h", "hb", "hc", "hx", "l", "m", "nc", "nd", "ng", "np", "nv"})
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
RESOURCE_GROUP = re.compile(r"/resourcegroups/([^/]+)", re.I)

# The resource type of a lead, from a closed list: each Resource Graph detector has one type, and Advisor's own types are those of its cost recommendations.
DETECTOR_TYPES = {
    "orphan-private-endpoint": "microsoft.network/privateendpoints",
    "orphan-managed-disk": "microsoft.compute/disks",
    "orphan-public-ip": "microsoft.network/publicipaddresses",
    "load-balancer-without-backends": "microsoft.network/loadbalancers",
    "empty-app-service-plan": "microsoft.web/serverfarms",
    "stopped-vm": "microsoft.compute/virtualmachines",
}
ADVISOR_TYPES = frozenset({
    "microsoft.compute/virtualmachines", "microsoft.compute/virtualmachinescalesets", "microsoft.compute/disks", "microsoft.compute/reservedinstances",
    "microsoft.sql/servers/databases", "microsoft.sql/servers/elasticpools", "microsoft.sql/managedinstances", "microsoft.storage/storageaccounts",
    "microsoft.web/serverfarms", "microsoft.web/sites", "microsoft.network/publicipaddresses", "microsoft.network/loadbalancers",
    "microsoft.network/applicationgateways", "microsoft.network/virtualnetworkgateways", "microsoft.network/azurefirewalls", "microsoft.network/privateendpoints",
    "microsoft.dbforpostgresql/servers", "microsoft.dbforpostgresql/flexibleservers", "microsoft.dbformysql/servers", "microsoft.dbformysql/flexibleservers",
    "microsoft.documentdb/databaseaccounts", "microsoft.cache/redis", "microsoft.synapse/workspaces", "microsoft.operationalinsights/workspaces",
    "microsoft.containerservice/managedclusters", "microsoft.subscriptions/subscriptions", "microsoft.eventhub/namespaces", "microsoft.servicebus/namespaces",
    "microsoft.kusto/clusters", "microsoft.recoveryservices/vaults",
})
KNOWN_TYPES = frozenset(DETECTOR_TYPES.values()) | ADVISOR_TYPES | {"other"}

# The closed vocabulary of the facts: every word that a detector may put in a fact, and the few shapes of the rest. A prompt holds nothing else.
FACT_WORDS = frozenset().union(CONNECTION_STATES, TARGET_SERVICES, DISK_SKUS, PLAN_TIERS, VM_FAMILIES,
                               {"basic", "standard", "static", "dynamic", "high", "medium", "low", "other", "none", "unknown", "unattached", "stopped", "cost"})
FACT_SHAPES = (re.compile(r"^(up to|over) \d{1,5}$"), GUID)


def is_fact_word(value: str) -> bool:
    return value in FACT_WORDS or any(shape.match(value) for shape in FACT_SHAPES)


def known_type(value: str) -> str:
    return value if value in KNOWN_TYPES else "other"


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
    # How cost_usd_30d was read (cases/costs.py), what it is made of when the lead is about a whole subscription or resource group, an estimate at list price for a managed disk that Azure has no cost
    # line for, the display name of the subscription and Advisor's own words for an Advisor lead. None of them goes to a model: evidence.py builds what a model sees from the typed facts alone.
    cost_state: str = ""
    cost_by_service: dict = field(default_factory=dict)
    estimate: dict = field(default_factory=dict)
    subscription_name: str = ""
    advice: dict = field(default_factory=dict)

    @property
    def lead_id(self) -> str:
        return hashlib.sha256(f"{self.detector}|{self.resource_id.lower()}".encode("utf-8")).hexdigest()[:12]


@dataclass
class Context:
    """What the guards and the ranking need for one subscription. None means that it could not be read.

    `costs` are the cost lines of the resources of the subscription (lower-case resource id and the sum of its lines, the lines that no resource has under ""), and `cost_error` says that they could
    not be read (as opposed to a read that found none). `containers` holds, for each lead that is about the whole subscription or a whole resource group of it, the cost of every line in it, by
    service (lower-case id of the scope): None when that read failed."""

    locks: list[str] | None = None
    recent: set[str] | None = None
    managed_groups: set[str] | None = None
    costs: dict[str, float] | None = None
    currency: str | None = None
    cost_error: bool = False
    containers: dict[str, "ScopeCost | None"] = field(default_factory=dict)


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
    lead = _lead("orphan-managed-disk", row, {"diskState": "unattached", "sku": pick(row.get("skuName"), DISK_SKUS), "sizeGb": bucket(row.get("sizeGb")), "ageDays": age}, age)
    if lead is not None:
        lead.estimate = estimates.disk_estimate(row.get("skuName"), row.get("sizeGb"))  # kept only when Azure has no cost line for the disk (rank)
    return lead


def _public_ip(row: dict, now: dt.datetime) -> Lead | None:
    return _lead("orphan-public-ip", row, {"sku": pick(row.get("skuName"), frozenset({"basic", "standard"})),
                                           "allocation": pick(row.get("allocation"), frozenset({"static", "dynamic"}))})


def _load_balancer(row: dict, now: dt.datetime) -> Lead | None:
    return _lead("load-balancer-without-backends", row, {"sku": "standard", "backendPools": whole(row.get("poolCount")),
                                                         "loadBalancingRules": whole(row.get("ruleCount")), "frontends": whole(row.get("frontendCount"))})


def _plan(row: dict, now: dt.datetime) -> Lead | None:
    return _lead("empty-app-service-plan", row, {"tier": pick(row.get("tier"), PLAN_TIERS), "workers": whole(row.get("workers"))})


def _vm(row: dict, now: dt.datetime) -> Lead | None:
    # The number in a size name is the vCPU count for most families (not for a size with constrained vCPUs); the model gets it as a rough size.
    size = VM_FAMILY.match(str(row.get("vmSize") or ""))
    return _lead("stopped-vm", row, {"powerState": "stopped", "sizeFamily": pick(size.group(1) if size else "", VM_FAMILIES), "vcpu": int(size.group(2)) if size else None})


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


ADVICE_PROBLEM = 160  # the characters of Advisor's own short problem that a record keeps: it is the title of a request
ADVICE_SOLUTION = 300


def advisor_words(properties: dict) -> dict:
    """Advisor's own words for a recommendation (Learn, "Recommendations - List": properties.shortDescription has a problem and a solution, each a sentence that Advisor wrote), one line each, with
    one standing in for the other when Advisor gave only one. Empty when it gave neither. It is text that Advisor wrote, kept for a person to read: it never goes into a prompt."""
    short = properties.get("shortDescription") if isinstance(properties.get("shortDescription"), dict) else {}
    problem = clean_text(short.get("problem"), ADVICE_PROBLEM) if isinstance(short.get("problem"), str) else ""
    solution = clean_text(short.get("solution"), ADVICE_SOLUTION) if isinstance(short.get("solution"), str) else ""
    if not problem and not solution:
        return {}
    return {"problem": problem or clean_text(solution, ADVICE_PROBLEM), "solution": solution or problem}


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
                location="", tags={}, managed_by="", facts=facts, advisor_saving_usd=saving, advice=advisor_words(properties))


GRAPH_CHUNK = 50  # the subscriptions that one Resource Graph query reads: Learn recommends groups of fewer than 300 (the guidance for throttled requests)
SHOWN = 3  # the ids of subscriptions that a note names, at eight characters each
SUBSCRIPTION_OF_ID = re.compile(r"^/subscriptions/([0-9a-fA-F-]{36})(?:/|$)")

# What a source is called in a note, and the order in which the notes of the sources are kept.
LOCKS, RECENT, GROUPS, COSTS = "management locks", "recent creations", "managed resource groups", "cost lines"
SOURCES = (*(d.name for d in DETECTORS), ADVISOR, LOCKS, RECENT, GROUPS, COSTS)


def some(subscriptions: Sequence[str], shown: int = SHOWN) -> str:
    """The first few subscriptions, at eight characters each, and how many more there are: a note names a few and counts the rest."""
    first = ", ".join(sub[:8] for sub in subscriptions[:shown])
    return first + (f" and {len(subscriptions) - shown} more" if len(subscriptions) > shown else "")


class Problems:
    """What could not be read, by source. A source that failed in one subscription is a note of its own, as it always was; one that failed in several is one note that counts them,
    so that an estate with many subscriptions does not write a line for each."""

    def __init__(self) -> None:
        self.failed: dict[str, dict[str, str]] = {}

    def add(self, source: str, subscription: str, error: object) -> None:
        self.failed.setdefault(source, {})[subscription] = str(error)[:200]

    def notes(self) -> list[str]:
        notes = []
        for source in SOURCES:
            found = self.failed.get(source)
            if not found:
                continue
            if len(found) == 1:
                ((sub, text),) = found.items()
                notes.append(f"{sub[:8]}: {source} could not be read ({text})")
            else:
                reason = Counter(found.values()).most_common(1)[0][0][:120]
                notes.append(f"{source} could not be read in {len(found)} subscriptions ({some(list(found))}): {reason}")
        return notes


@dataclass
class Estate:
    """What the reading of many subscriptions came to: the leads, the context of each subscription that was read, and the subscriptions that were not read (`unread`, in the order
    of reading) with the reason: "time" (the time for reading them was used up) or "identity" (the identity gave no token; `reason` has the text)."""

    leads: list[Lead] = field(default_factory=list)
    contexts: dict[str, Context] = field(default_factory=dict)
    collected: dict[str, Collected] = field(default_factory=dict)
    sources_read: int = 0
    sources_failed: int = 0
    unread: list[str] = field(default_factory=list)
    stopped: str = ""
    reason: str = ""


@dataclass
class _Graph:
    """What the Resource Graph queries of one group of subscriptions gave for one of them."""

    leads: list[Lead] = field(default_factory=list)
    read: int = 0
    failed: int = 0
    recent: set[str] | None = None
    groups: set[str] | None = None


def _owner(row: dict, chunk: Sequence[str], members: set[str]) -> str | None:
    """The subscription that a row of a query for several belongs to: the one that the row names (its subscriptionId, or the id in its `id` or its `targetId`) when it is one
    of the group, and the group's own when the group is one subscription. A row of no subscription of the group is nobody's."""
    for value in (row.get("subscriptionId"), row.get("id"), row.get("targetId")):
        text = str(value or "").strip().lower()
        found = SUBSCRIPTION_OF_ID.match(text)
        candidate = found.group(1) if found else text
        if candidate in members:
            return candidate
    return chunk[0] if len(chunk) == 1 else None


def _read_graph(arm: Arm, chunk: Sequence[str], now: dt.datetime, problems: Problems) -> dict[str, _Graph]:
    """The eight Resource Graph queries (the six detectors and the two of the context) for a group of subscriptions, each one query for the whole group."""
    members = set(chunk)
    graph = {sub: _Graph() for sub in chunk}
    for detector in DETECTORS:
        try:
            rows = arm.graph_many(chunk, detector.query)
        except HttpError as error:
            for sub in chunk:
                graph[sub].failed += 1
                problems.add(detector.name, sub, error)
            continue
        for sub in chunk:
            graph[sub].read += 1
        for row in rows:
            owner = _owner(row, chunk, members)
            lead = detector.build(row, now) if owner else None
            if lead:
                graph[owner].leads.append(lead)
    for query, source, key in ((RECENT_CREATIONS, RECENT, "targetId"), (MANAGED_GROUPS, GROUPS, "name")):
        try:
            rows = arm.graph_many(chunk, query)
        except HttpError as error:
            for sub in chunk:
                problems.add(source, sub, error)
            continue
        found: dict[str, set[str]] = {sub: set() for sub in chunk}
        for row in rows:
            owner = _owner(row, chunk, members)
            if owner:
                found[owner].add(str(row.get(key, "")).lower())
        for sub in chunk:
            if source == RECENT:
                graph[sub].recent = found[sub]
            else:
                graph[sub].groups = found[sub]
    return graph


def _read_subscription(arm: Arm, subscription: str, today: dt.date, graph: _Graph, problems: Problems) -> Collected:
    """What is read for one subscription alone (Advisor, its locks and its cost lines) joined to what its group's queries gave."""
    leads = list(graph.leads)
    context = Context(recent=graph.recent, managed_groups=graph.groups)
    read, failed = graph.read, graph.failed
    try:
        for recommendation in arm.advisor_cost(subscription):
            lead = advisor_lead(recommendation, subscription)
            if lead:
                leads.append(lead)
        read += 1
    except HttpError as error:
        failed += 1
        problems.add(ADVISOR, subscription, error)
    try:
        context.locks = arm.locks(subscription)
    except HttpError as error:
        problems.add(LOCKS, subscription, error)
    start, end = today - dt.timedelta(days=30), today - dt.timedelta(days=1)
    try:
        context.costs, context.currency = arm.costs(subscription, start, end)
    except HttpError as error:
        context.cost_error = True
        problems.add(COSTS, subscription, error)
    for lead in leads:
        # A finding about the whole subscription, or about a whole resource group, costs what every cost line in it costs (also the lines that no resource and no resource group have): one read
        # of Cost Management by service, however many findings are about the same scope.
        key = cost_words.container_key(lead.resource_id)
        if key and key not in context.containers:
            try:
                context.containers[key] = arm.scope_costs(subscription, start, end, cost_words.scope_of(lead.resource_id).group)
            except HttpError as error:
                context.containers[key] = None
                problems.add(COSTS, subscription, error)
    if leads:
        named = arm.subscription_name(subscription)  # once for the subscription: the list of the subscriptions has it already, or one read of the subscription gives it
        for lead in leads:
            lead.subscription_name = named
            if named and cost_words.scope_of(lead.resource_id).kind == "subscription":
                lead.name = named  # a finding about the subscription itself is about "this subscription", and a person knows it by its name
    return Collected(leads, context, read, failed)


def collect_estate(arm: Arm, subscriptions: Sequence[str], now: dt.datetime, notes: list[str], out_of_time: Callable[[], bool] = lambda: False) -> Estate:
    """Every lead, and the context for the guards and the cost lines, of every subscription of the list, in the order of the list.

    The Resource Graph queries run for a group of GRAPH_CHUNK subscriptions at a time, one query for the whole group; Advisor, the locks and the cost lines for each subscription.
    A source that cannot be read is a note, not a stop. `out_of_time` is asked before every group and every subscription: when it says yes, no further subscription is started and the
    rest are `unread`. A subscription is read as a whole or not at all, so the rest of a group whose time ran out is unread, and its leads are not used. When the identity gives no
    token nothing could be read after that either, and the reading stops with that reason. The notes of what could not be read are added to `notes`."""
    today = now.date()
    problems = Problems()
    estate = Estate()
    order = list(dict.fromkeys(subscriptions))
    done = 0
    try:
        stop = False
        for start in range(0, len(order), GRAPH_CHUNK):
            if out_of_time():
                break
            chunk = order[start:start + GRAPH_CHUNK]
            graph = _read_graph(arm, chunk, now, problems)
            for sub in chunk:
                if out_of_time():
                    stop = True
                    break
                collected = _read_subscription(arm, sub, today, graph[sub], problems)
                estate.collected[sub], estate.contexts[sub] = collected, collected.context
                estate.leads += collected.leads
                estate.sources_read += collected.sources_read
                estate.sources_failed += collected.sources_failed
                done += 1
            if stop:
                break
    except IdentityError as error:
        estate.stopped, estate.reason = "identity", str(error)
    if done < len(order) and not estate.stopped:
        estate.stopped = "time"
    estate.unread = order[done:]
    notes.extend(problems.notes())
    return estate


def collect(arm: Arm, subscription: str, now: dt.datetime, notes: list[str]) -> Collected:
    """Every lead of one subscription, with the context for the guards and the cost lines. A source that cannot be read is a note, not a stop. An identity that gives no token
    raises IdentityError."""
    estate = collect_estate(arm, [subscription], now, notes)
    if estate.stopped == "identity":
        raise IdentityError(estate.reason)
    return estate.collected[subscription]


def _cost_of_resource(lead: Lead, context: Context) -> None:
    """The 30-day cost of a lead about one resource, from the cost lines of its subscription, found by the id in lower case (Cost Management gives ids in lower case whatever the case of the id that
    Resource Graph or Advisor gave). A subscription whose cost lines could not be read says so (FAILED), one whose lines are not in dollars says that (CURRENCY), and a resource that has no
    line is NONE (0.0, as it always was): not a cost of nothing, and the pages say so. A subscription that has no cost line at all is NONE too, with no figure: no currency is known without a line."""
    if context.costs is None:
        lead.cost_state = cost_words.FAILED if context.cost_error else ""
    elif context.currency == "USD":
        if lead.resource_id.lower() in context.costs:
            lead.cost_usd_30d, lead.cost_state = round(context.costs[lead.resource_id.lower()], 2), cost_words.LINES
        else:
            lead.cost_usd_30d, lead.cost_state = 0.0, cost_words.NONE
    else:
        lead.cost_state = cost_words.CURRENCY if context.costs else cost_words.NONE
    if lead.cost_state != cost_words.NONE:
        lead.estimate = {}  # an estimate at list price is for a resource that Azure has no cost line for, and for no other


def _cost_of_container(lead: Lead, context: Context, key: str) -> None:
    """The 30-day cost of a lead about a whole subscription or resource group: the sum of every cost line in it, by service (the read of Cost Management that _read_subscription made)."""
    if key not in context.containers:
        return
    scoped = context.containers[key]
    if scoped is None:
        lead.cost_state = cost_words.FAILED
    elif scoped.currency not in (None, "USD"):
        lead.cost_state = cost_words.CURRENCY
    elif scoped.rows == 0:
        lead.cost_usd_30d, lead.cost_state = 0.0, cost_words.NONE
    else:
        lead.cost_usd_30d, lead.cost_state, lead.cost_by_service = round(scoped.total, 2), cost_words.LINES, cost_words.parts_of(scoped.services)


def rank(leads: list[Lead], contexts: dict[str, Context]) -> list[Lead]:
    """One lead for each resource (a Resource Graph detector before Advisor), each with its 30-day cost, dearest first. What a whole subscription or resource group costs is not what a resource
    costs, so a finding about one of them does not rank by it."""
    seen: set[str] = set()
    unique: list[Lead] = []
    for lead in sorted(leads, key=lambda l: (l.detector == ADVISOR, l.detector, l.resource_id.lower())):
        key = lead.resource_id.lower()
        if key not in seen:
            seen.add(key)
            unique.append(lead)
    for lead in unique:
        context = contexts.get(lead.subscription_id)
        if context is None:
            continue
        key = cost_words.container_key(lead.resource_id)
        if key:
            _cost_of_container(lead, context, key)
        else:
            _cost_of_resource(lead, context)
    return sorted(unique, key=lambda l: (-((l.cost_usd_30d or 0.0) if not cost_words.is_container(l.resource_id) else 0.0), l.detector, l.resource_id.lower()))
