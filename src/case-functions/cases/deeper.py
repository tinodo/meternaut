"""What the investigation's deeper reads make of the answers of Azure, as typed facts, and which kinds of resource they are offered for.

The tools of toolbox.py are generic: they take a handle and answer numbers, flags and short words. A few kinds of resource keep more than their properties and their platform metrics
show: a workspace keeps records of the data written to it, an account of AI services keeps its deployments, and a subscription has the platform's own purchase recommendations. The
reads for those are written from Microsoft Learn (each one names its page in arm.py), and this module is the only place that says which kind of resource each is for. It says what can
be read, never what to look for, and a test scans it for words that would.

Every function here takes what Azure answered (text that somebody in the estate may have written is in it) and returns numbers, flags and words that passed a check, or counts that
code made. A table name is a word only when the platform made the table (the closed set of names that the workspace itself lists as Microsoft's); any other table is a handle (t1, t2, ...)
that means something in this run only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

from . import kql
from .http import WORKSPACE as _WORKSPACE_PATTERN

WORKSPACE = "microsoft.operationalinsights/workspaces"
ACCOUNT = "microsoft.cognitiveservices/accounts"
DEPLOYMENT = "microsoft.cognitiveservices/accounts/deployments"
SCHEDULED_RULES = "microsoft.insights/scheduledqueryrules"
COLLECTION_RULES = "microsoft.insights/datacollectionrules"
WORKSPACE_ID = re.compile(_WORKSPACE_PATTERN, re.I)
# The columns of a read of Resource Graph that the tools take a resource from (the same projection as toolbox.py's): the two text columns that are turned into words get names of their own,
# because Resource Graph refuses an alias that is the name of a column of the table.
COLUMNS = "project id, name, type, resourceGroup, subscriptionId, location, tags, managedByText = tostring(managedBy), kindName = tostring(kind), sku, properties"

# The deeper reads that are offered for a kind of resource, in the order of the tools. A table of resources and a description name them for a type that has them, so that the agent
# finds them from what it is looking at and no description has to name a kind of resource.
OFFERS: dict[str, tuple[str, ...]] = {WORKSPACE: ("data_volume", "data_readers", "data_writers"), ACCOUNT: ("children",)}

TOKEN = re.compile(r"[A-Za-z0-9]+")
BUILT_IN = re.compile(r"[A-Za-z][A-Za-z0-9]{0,63}")  # the name of a table that the platform made
WORD = re.compile(r"[A-Za-z0-9_.-]{1,24}")  # a SKU, a model or a version as the platform writes it
TABLE_HANDLE = re.compile(r"t[0-9]{1,4}")
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
BUCKETS = 6  # the equal parts of a window that a trend is told in
DATA_SOURCES = ("performanceCounters", "windowsEventLogs", "syslog", "extensions", "logFiles", "iisLogs", "prometheusForwarder", "platformTelemetry", "windowsFirewallLogs",
                "dataImports", "otelMetrics", "snmp")
MAX_TABLES = 12  # the tables whose volume goes into the evidence of a workspace


def offered(kind: str | None) -> list[str]:
    """The deeper reads that are offered for a resource type."""
    return list(OFFERS.get(kind or "", ()))


# -- the typed words and numbers ------------------------------------------------------------------------------------------------------------------

def word(value: object, limit: int = 32) -> str | None:
    """A word of the platform that has no separator (a tier, a state, a plan): letters and digits only, at most `limit` of them."""
    return value if isinstance(value, str) and len(value) <= limit and TOKEN.fullmatch(value) else None


def form(value: object) -> str | None:
    """A SKU, a model or a version as the platform writes it: at most 24 letters, digits and _ . -."""
    return value if isinstance(value, str) and WORD.fullmatch(value) else None


def count(value: object) -> int | None:
    """A whole number of at least 0, or None for anything else (a flag, a text, a number with a fraction)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value if isinstance(value, int) and 0 <= value <= 10**15 else None


def real(value: object) -> float | None:
    """A finite number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def number(value: float) -> int | float:
    """A measured number as an answer gives it: a whole number as it is, any other with six significant digits."""
    if value == int(value) and abs(value) < 1e15:
        return int(value)
    return float(f"{value:.6g}")


def day_of(value: object) -> dt.date | None:
    """The day of a time as the Logs query API gives it (2026-10-09T00:00:00Z)."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


# -- a workspace -----------------------------------------------------------------------------------------------------------------------------------

def customer_id(workspace: Mapping) -> str | None:
    """The id that the Logs query API names a workspace by (a GUID, in lower case)."""
    properties = workspace.get("properties") if isinstance(workspace.get("properties"), Mapping) else {}
    value = properties.get("customerId")
    return value.lower() if isinstance(value, str) and GUID.fullmatch(value) else None


def pricing(workspace: Mapping) -> dict:
    """How a workspace is priced and kept (Learn, "Workspaces - Get"): the pricing tier, the commitment level in GB a day when it has one, the retention in days, the daily cap in GB
    (None when there is none: Azure writes -1), the state of the ingestion and whether the workspace takes queries from the public network."""
    properties = workspace.get("properties") if isinstance(workspace.get("properties"), Mapping) else {}
    sku = properties.get("sku") if isinstance(properties.get("sku"), Mapping) else {}
    capping = properties.get("workspaceCapping") if isinstance(properties.get("workspaceCapping"), Mapping) else {}
    quota = real(capping.get("dailyQuotaGb"))
    found = {"tier": word(sku.get("name"), 24), "commitment_gb": count(sku.get("capacityReservationLevel")), "retention_days": count(properties.get("retentionInDays")),
             "daily_cap_gb": None if quota is None or quota < 0 else number(round(quota, 3)), "ingestion": word(capping.get("dataIngestionStatus"), 24),
             "query_access": word(properties.get("publicNetworkAccessForQuery"), 16)}
    return {key: value for key, value in found.items() if value is not None}


def table_index(tables: Iterable[Mapping]) -> dict[str, dict]:
    """The tables of a workspace by name, each with its plan, its retention in days, how long it is kept in all, and whether the platform made it (`built_in`). A name that the platform
    did not make is never shown as text (TableBook)."""
    index: dict[str, dict] = {}
    for item in tables:
        name = item.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 120:
            continue
        index[name] = {"plan": word(item.get("plan"), 16), "retention": count(item.get("retentionInDays")), "total_retention": count(item.get("totalRetentionInDays")),
                       "built_in": item.get("type") == "Microsoft" and BUILT_IN.fullmatch(name) is not None and not name.endswith("_CL")}
    return index


@dataclass
class TableBook:
    """The tables of one workspace as the agent names them: a table that the platform made by its name, any other by a handle (t1, t2, ...) in the order that it was first shown."""

    index: dict[str, dict]
    _handles: dict[str, str] = field(default_factory=dict)
    _names: dict[str, str] = field(default_factory=dict)

    def label(self, name: str) -> str:
        if self.index.get(name, {}).get("built_in"):
            return name
        if name not in self._handles:
            handle = f"t{len(self._handles) + 1}"
            self._handles[name], self._names[handle] = handle, name
        return self._handles[name]

    def name_of(self, label: object) -> str | None:
        """The name of the table that a label stands for, when the workspace has such a table that the agent may name."""
        if not isinstance(label, str):
            return None
        if TABLE_HANDLE.fullmatch(label):
            return self._names.get(label)
        return label if self.index.get(label, {}).get("built_in") else None

    def known(self) -> set[str]:
        return set(self.index)

    def handled(self) -> dict[str, str]:
        """The table that each handle of this run stands for (t1 is the name of a table that the platform did not make). It is for the page of a person and never for an agent."""
        return dict(self._names)


# -- what a workspace records about the data written to it -----------------------------------------------------------------------------------------

def usage_query(days: int) -> str:
    """The query for the volume of a workspace by table and day (Learn, "Analyze usage in a Log Analytics workspace": the records of the Usage table, hourly, in megabytes): the closed days
    of the window, the billable volume and the rest. The text is made here and never takes anything from an argument but the number of days."""
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 90:
        raise ValueError("days is a number from 1 to 90")
    return (f"// meternaut:usage\nUsage | where TimeGenerated > ago({days + 2}d) | where StartTime >= startofday(ago({days}d)) and EndTime < startofday(now()) "
            "| summarize BillableMB = sumif(Quantity, IsBillable == true), FreeMB = sumif(Quantity, IsBillable != true) by Day = bin(StartTime, 1d), DataType")


@dataclass
class TableUse:
    """The volume of one table over a window: the billable and the other megabytes, and the billable megabytes of each day."""

    name: str
    billable_mb: float = 0.0
    free_mb: float = 0.0
    daily: dict[int, float] = field(default_factory=dict)  # the day (0 is the first day of the window) -> billable megabytes


def usage_by_table(rows: Iterable[Mapping], first_day: dt.date, days: int) -> dict[str, TableUse]:
    """The rows of usage_query as the volume of each table. A row that is not in the window or has no table or no number is left out."""
    found: dict[str, TableUse] = {}
    for row in rows:
        table, day = row.get("DataType"), day_of(row.get("Day"))
        billable, free = real(row.get("BillableMB")), real(row.get("FreeMB"))
        if not isinstance(table, str) or not 1 <= len(table) <= 120 or day is None or (billable is None and free is None):
            continue
        place = (day - first_day).days
        if not 0 <= place < days:
            continue
        use = found.setdefault(table, TableUse(table))
        use.billable_mb += max(billable or 0.0, 0.0)
        use.free_mb += max(free or 0.0, 0.0)
        use.daily[place] = use.daily.get(place, 0.0) + max(billable or 0.0, 0.0)
    return found


def trend(use: TableUse, days: int) -> list[int | float]:
    """The billable gigabytes of a table in equal parts of the window, the oldest first (as many parts as there are days when there are fewer days than BUCKETS)."""
    parts = min(BUCKETS, days)
    sums = [0.0] * parts
    for place, megabytes in use.daily.items():
        sums[min(parts - 1, place * parts // days)] += megabytes
    return [number(round(total / 1000, 3)) for total in sums]


def volume_rows(uses: Mapping[str, TableUse], days: int) -> tuple[list[TableUse], float]:
    """The tables in the order of their billable volume, the largest first, and the billable megabytes of all of them."""
    ranked = sorted(uses.values(), key=lambda use: (-use.billable_mb, -use.free_mb, use.name))
    return ranked, sum(use.billable_mb for use in ranked)


# -- who reads from a workspace ---------------------------------------------------------------------------------------------------------------------

def scheduled_rules(rows: Iterable[Mapping], workspace_id: str) -> list[tuple[bool, list[str]]]:
    """The scheduled query rules (as Resource Graph rows) whose scopes name the workspace: whether each is enabled and the texts of its queries. The texts are for code to count with, and
    never leave it."""
    found = []
    wanted = workspace_id.lower()
    for row in rows:
        properties = row.get("properties") if isinstance(row.get("properties"), Mapping) else {}
        scopes = properties.get("scopes") if isinstance(properties.get("scopes"), list) else []
        if not any(isinstance(scope, str) and scope.lower() == wanted for scope in scopes):
            continue
        criteria = properties.get("criteria") if isinstance(properties.get("criteria"), Mapping) else {}
        conditions = criteria.get("allOf") if isinstance(criteria.get("allOf"), list) else []
        found.append((properties.get("enabled") is not False, [condition["query"] for condition in conditions if isinstance(condition, Mapping) and isinstance(condition.get("query"), str)]))
    return found


MAX_WORKBOOK = 2_000_000  # the characters of the content of one workbook that are looked at
MAX_NODES = 100_000  # the values of the content of one workbook that are looked at


def _queries_of(content: str) -> list[str]:
    """The texts of the queries in the content of a workbook: the values of every key `query`, at any depth. The content is JSON, so a query in it is a string that has its own escapes."""
    try:
        tree = json.loads(content[:MAX_WORKBOOK]) if len(content) <= MAX_WORKBOOK else None
    except (ValueError, RecursionError):
        return []
    found, stack, looked = [], [tree], 0
    while stack and looked < MAX_NODES:
        node = stack.pop()
        looked += 1
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key == "query" and isinstance(value, str):
                    found.append(value)
                elif isinstance(value, (Mapping, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(item for item in node if isinstance(item, (Mapping, list)))
    return found


def workbook_texts(items: Iterable[Mapping], workspace_id: str) -> list[list[str]]:
    """The texts of the queries of each workbook that is for the workspace: one that names it as its source, or whose content names it. A workbook that takes its workspace from a parameter
    or from the page that shows it names none, and is not counted."""
    found = []
    wanted = workspace_id.lower()
    for item in items:
        properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
        content, source = properties.get("serializedData"), properties.get("sourceId")
        if isinstance(content, str) and (wanted in content.lower() or (isinstance(source, str) and source.lower() == wanted)):
            found.append(_queries_of(content))
    return found


def query_texts(items: Iterable[Mapping], kinds: tuple[str, ...] = ()) -> list[list[str]]:
    """The query of each saved search or Sentinel rule (`properties.query`), one list of texts for each; with `kinds`, only the rules of those kinds (a Sentinel rule has a kind)."""
    found = []
    for item in items:
        properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
        if kinds and item.get("kind") not in kinds:
            continue
        if isinstance(properties.get("query"), str):
            found.append([properties["query"]])
    return found


def mention_counts(groups: Mapping[str, list[list[str]]], known: set[str]) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """For each table that some item mentions, how many items of each kind of reader mention it, and for each kind how many items read every table at once. An item is a list of query texts
    (a workbook has several); it counts once for a table however often, and in however many of its texts, it names it."""
    per_table: dict[str, dict[str, int]] = {}
    scanning: dict[str, int] = {}
    for kind, items in groups.items():
        scanning[kind] = 0
        for texts in items:
            names: set[str] = set()
            for text in texts:
                names |= kql.mentioned(text, known)
            for name in names:
                counts = per_table.setdefault(name, {})
                counts[kind] = counts.get(kind, 0) + 1
            if any(kql.scans_every_table(text) for text in texts):
                scanning[kind] += 1
    return per_table, scanning


MAX_AUDIT_TEXTS = 300  # the distinct texts of queries that the read of the record of the runs keeps: the ones that were run most often
LOG_AUDIT_TOTALS = ("// meternaut:audit\nLAQueryLogs | where QueryText !contains \"meternaut:\" | summarize Runs = count(), Callers = dcount(AADObjectId)")
LOG_AUDIT_TEXTS = (f"// meternaut:audit\nLAQueryLogs | where QueryText !contains \"meternaut:\" | summarize Runs = count() by QueryText | top {MAX_AUDIT_TEXTS} by Runs desc")


def audit_counts(rows: Iterable[Mapping], known: set[str]) -> dict[str, int]:
    """From the rows of LOG_AUDIT_TEXTS: for each table, how many of the recorded runs of queries named it. A table that no text names is not in it, and that is none only when the rows are all
    there are: a read that returned MAX_AUDIT_TEXTS rows may have left texts out (see audit_cut)."""
    found: dict[str, int] = {}
    for row in rows:
        runs = count(row.get("Runs"))
        if runs is None:
            continue
        for name in kql.mentioned(row.get("QueryText"), known):
            found[name] = found.get(name, 0) + runs
    return found


def audit_cut(rows: Sequence[Mapping]) -> bool:
    """Whether the read of LOG_AUDIT_TEXTS may have left texts out: it returned as many rows as it may, so a table that none of them names is not known to be read by no query."""
    return len(rows) >= MAX_AUDIT_TEXTS


# -- who writes to a workspace ----------------------------------------------------------------------------------------------------------------------

def table_of_stream(stream: object) -> str | None:
    """The table that a stream of a data collection rule writes to: Microsoft-<Table>, Microsoft-Table-<Table> and Custom-<Table>."""
    if not isinstance(stream, str):
        return None
    for prefix in ("Microsoft-Table-", "Microsoft-", "Custom-"):
        if stream.startswith(prefix):
            name = stream[len(prefix):]
            return name if 1 <= len(name) <= 120 else None
    return None


def collection_rule(row: Mapping, workspace_id: str) -> dict | None:
    """One data collection rule (a Resource Graph row) as typed facts, when it sends data to the workspace: the kinds of data source that it has and how many of each, how many flows go to
    the workspace and how many of those have a transformation (a filter that runs before the data is stored), and the names of the tables that the flows write to. None when it sends
    nothing to the workspace."""
    properties = row.get("properties") if isinstance(row.get("properties"), Mapping) else {}
    destinations = properties.get("destinations") if isinstance(properties.get("destinations"), Mapping) else {}
    wanted = workspace_id.lower()
    names = {str(item.get("name")) for item in destinations.get("logAnalytics") or []
             if isinstance(item, Mapping) and isinstance(item.get("workspaceResourceId"), str) and item["workspaceResourceId"].lower() == wanted}
    if not names:
        return None
    flows = [flow for flow in properties.get("dataFlows") or [] if isinstance(flow, Mapping) and names & {str(item) for item in flow.get("destinations") or []}]
    sources = properties.get("dataSources") if isinstance(properties.get("dataSources"), Mapping) else {}
    kinds = {}
    for key, value in sources.items():
        label = key if key in DATA_SOURCES else "other"
        size = len(value) if isinstance(value, list) else 1 if value else 0
        if size:
            kinds[label] = kinds.get(label, 0) + size
    tables = set()
    for flow in flows:
        output = table_of_stream(flow.get("outputStream"))
        if output:
            tables.add(output)
        else:
            tables.update(name for name in (table_of_stream(stream) for stream in flow.get("streams") or []) if name)
    kind = row.get("kindName") if isinstance(row.get("kindName"), str) else None
    return {"kind": word(kind, 24), "sources": kinds, "flows": len(flows), "transforms": sum(1 for flow in flows if isinstance(flow.get("transformKql"), str) and flow["transformKql"].strip()),
            "tables": sorted(tables)}


def _in_workspace(workspace_id: str) -> str:
    """The id of a workspace, when it is one: it is put into a query, so nothing else may enter."""
    if not WORKSPACE_ID.fullmatch(workspace_id) or "'" in workspace_id:
        raise ValueError("the scope is not the id of a workspace")
    return workspace_id


def rules_query(workspace_id: str) -> str:
    """The Resource Graph query for the scheduled query rules that have the workspace among their scopes."""
    return (f"// meternaut:rules-of-workspace\nresources\n| where type =~ '{SCHEDULED_RULES}'\n"
            f"| where tostring(properties.scopes) contains '{_in_workspace(workspace_id)}'\n| {COLUMNS}")


def collection_rules_query(workspace_id: str) -> str:
    """The Resource Graph query for the data collection rules that have the workspace among their destinations."""
    return (f"// meternaut:collection-rules-of-workspace\nresources\n| where type =~ '{COLLECTION_RULES}'\n"
            f"| where tostring(properties.destinations) contains '{_in_workspace(workspace_id)}'\n| {COLUMNS}")


SOURCES_QUERY = ("// meternaut:sources\nlet All = {table} | where TimeGenerated >= startofday(ago(1d)) and TimeGenerated < startofday(now()) | where _IsBillable == true "
                 "| summarize Bytes = sum(_BilledSize) by ResourceId = tolower(_ResourceId); let Whole = toscalar(All | summarize sum(Bytes)); "
                 "All | top {top} by Bytes desc | extend Whole = Whole")


TABLE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,119}")  # a table that a query may name: what the platform allows in a name


def queryable(table: str) -> bool:
    """Whether a table name is one that a query of this module may name."""
    return TABLE_NAME.fullmatch(table) is not None


def sources_query(table: str, top: int) -> str:
    """The query for the resources that wrote the most billable data to one table in the last whole day, and the whole that the table took in (Learn, "Analyze usage in a Log Analytics
    workspace": the columns _ResourceId, _BilledSize and _IsBillable of every table). `table` is a name that the workspace itself lists; nothing else of an argument enters the text."""
    if not queryable(table) or isinstance(top, bool) or not isinstance(top, int) or not 1 <= top <= 100:
        raise ValueError("the table is a name and top a number from 1 to 100")
    return SOURCES_QUERY.format(table=table, top=top)


def sources(rows: Iterable[Mapping]) -> tuple[list[tuple[str, float]], float | None]:
    """From the rows of sources_query: the id of each resource (lower case) and the billable megabytes that it wrote, the largest first, and the megabytes that the table took in on that
    day in all (None when the answer has no number for it)."""
    found = []
    whole: float | None = None
    for row in rows:
        resource, size = row.get("ResourceId"), real(row.get("Bytes"))
        if isinstance(resource, str) and size is not None and size >= 0:
            found.append((resource.lower(), size / 1_000_000))
        total = real(row.get("Whole"))
        if total is not None and total >= 0:
            whole = total / 1_000_000
    return sorted(found, key=lambda item: (-item[1], item[0])), whole


def diagnostic_setting(item: Mapping) -> tuple[dict, str | None]:
    """One diagnostic setting of a resource as typed facts: how many categories of logs and of metrics it sends, whether it sends to a workspace, a storage account, an event hub or a
    partner, and whether the logs go to tables of their own; and the id of the workspace that it sends to (lower case), which is for code to look up and is never shown."""
    properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}

    def enabled(entries: object) -> int:
        return sum(1 for entry in entries if isinstance(entry, Mapping) and entry.get("enabled") is True) if isinstance(entries, list) else 0

    target = properties.get("workspaceId")
    workspace = target.lower() if isinstance(target, str) and WORKSPACE_ID.fullmatch(target) else None
    return ({"logs": enabled(properties.get("logs")), "metrics": enabled(properties.get("metrics")), "workspace": bool(target), "storage": bool(properties.get("storageAccountId")),
             "event_hub": bool(properties.get("eventHubAuthorizationRuleId")), "partner": bool(properties.get("marketplacePartnerId")),
             "own_tables": properties.get("logAnalyticsDestinationType") == "Dedicated"}, workspace)


# -- the deployments of an account ---------------------------------------------------------------------------------------------------------------

def per_minute(limits: object) -> dict[str, int | float]:
    """The rate limits of a deployment (a count in a period of seconds, for requests and for tokens) as a number a minute each."""
    found: dict[str, int | float] = {}
    for item in limits if isinstance(limits, list) else []:
        if not isinstance(item, Mapping):
            continue
        key, amount, period = item.get("key"), real(item.get("count")), real(item.get("renewalPeriod"))
        if key in ("request", "token") and amount is not None and period is not None and period > 0 and amount >= 0:
            found[str(key)] = number(round(amount * 60 / period, 2))
    return found


def deployment_row(item: Mapping, account: Mapping) -> dict | None:
    """A deployment of an account (as the list of deployments gives it) as a row that the tools of resources take: its id, its type, the subscription and the group, the model as the
    kind and its SKU and properties. None when it has no id of its own."""
    resource_id = item.get("id")
    if not isinstance(resource_id, str) or "/deployments/" not in resource_id.lower():
        return None
    properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
    model = properties.get("model") if isinstance(properties.get("model"), Mapping) else {}
    return {"id": resource_id, "name": item.get("name"), "type": DEPLOYMENT, "resourceGroup": account.get("resourceGroup"), "subscriptionId": account.get("subscriptionId"),
            "location": account.get("location"), "tags": None, "managedByText": "", "kindName": form(model.get("name")) or "", "sku": item.get("sku") if isinstance(item.get("sku"), Mapping) else None,
            "properties": properties}


def deployment_facts(item: Mapping) -> dict:
    """The typed facts of a deployment: its model (as a word when it is one of 24 letters, digits and _ . -), the version, who made the model, the SKU, the capacity in units, the
    rate limits a minute for requests and for tokens, the state and what happens to it when a model version is retired."""
    properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
    model = properties.get("model") if isinstance(properties.get("model"), Mapping) else {}
    sku = item.get("sku") if isinstance(item.get("sku"), Mapping) else {}
    rates = per_minute(properties.get("rateLimits"))
    found = {"model": form(model.get("name")), "version": form(model.get("version")), "format": word(model.get("format"), 24), "sku": form(sku.get("name")),
             "capacity": count(sku.get("capacity")), "requests_per_minute": rates.get("request"), "tokens_per_minute": rates.get("token"), "state": word(properties.get("provisioningState"), 24),
             "upgrade": word(properties.get("versionUpgradeOption"), 32)}
    return {key: value for key, value in found.items() if value is not None}


# -- commitments ------------------------------------------------------------------------------------------------------------------------------------

def pricing_lines(rows: Iterable[tuple[str, str, float, str]]) -> tuple[list[dict], str | None]:
    """The amortized cost of a subscription by how it was paid for and what kind of charge it is, the largest first, and the currency (None when the lines are in more than one or have none).
    A word that Cost Management gives is a word here when it is letters and digits (24 at most) and `other` when it is not."""
    totals: dict[tuple[str, str], float] = {}
    currencies = set()
    for pricing_model, charge, amount, currency in rows:
        key = (word(pricing_model, 24) or ("none" if not pricing_model else "other"), word(charge, 24) or ("none" if not charge else "other"))
        totals[key] = totals.get(key, 0.0) + amount
        if currency:
            currencies.add(currency)
    lines = [{"pricing": key[0], "charge": key[1], "amount": number(round(value, 2))} for key, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))]
    return lines, (next(iter(currencies)) if len(currencies) == 1 else None)


def savings_plan(item: Mapping) -> dict | None:
    """One of the platform's recommendations to buy a savings plan (Learn, "Benefit Recommendations - List") as typed facts: the SKU, the term, how far back it looked, the hourly
    commitment, the share of the cost that it would cover, the average use of the commitment, and the saving; the amounts are in the currency that it names."""
    properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
    details = properties.get("recommendationDetails") if isinstance(properties.get("recommendationDetails"), Mapping) else {}
    found = {"sku": form(properties.get("armSkuName")), "term": word(properties.get("term"), 8), "lookback": word(properties.get("lookBackPeriod"), 16),
             "granularity": word(properties.get("commitmentGranularity"), 16), "commitment_per_hour": real(details.get("commitmentAmount")),
             "coverage": real(details.get("coveragePercentage")), "average_use": real(details.get("averageUtilizationPercentage")), "saving": real(details.get("savingsAmount")),
             "cost_without": real(properties.get("costWithoutBenefit")), "currency": word(properties.get("currencyCode"), 3)}
    return {key: (number(round(value, 3)) if isinstance(value, float) else value) for key, value in found.items() if value is not None} or None


def reservation(item: Mapping) -> dict | None:
    """One of the platform's recommendations to buy a reservation (Learn, "Reservation Recommendations - List") as typed facts, under the names that the answer has for them."""
    properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
    found = {"sku": form(item.get("sku") or properties.get("skuName") or properties.get("normalizedSize")), "term": word(properties.get("term"), 8),
             "lookback": word(properties.get("lookBackPeriod"), 16), "resource_type": word(properties.get("resourceType"), 32), "quantity": real(properties.get("recommendedQuantity")),
             "cost_without": real(properties.get("costWithNoReservedInstances")), "cost_with": real(properties.get("totalCostWithReservedInstances")),
             "saving": real(properties.get("netSavings")), "currency": word(properties.get("currencyCode"), 3)}
    return {key: (number(round(value, 3)) if isinstance(value, float) else value) for key, value in found.items() if value is not None} or None
