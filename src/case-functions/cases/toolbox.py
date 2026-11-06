"""The tools of the investigator: read-only reads of the estate whose answers hold typed values only, and opaque handles instead of names.

A tool answer is a JSON string of at most MAX_RESULT_CHARS characters. A resource is named by a handle (r1, r2, ...) that means something only in this run: the id,
the name, the tags and every other text that somebody wrote about a resource stay in the Resource below and never go into an answer. What does go into an answer is a
number, a flag, a GUID, or a word that matched a fixed pattern (a region, a SKU, a service name, a metric name, a resource type, a property whose key ends in a generic
suffix). A string that fails its pattern is left out, and a service name that fails is shown as "other". The tools list, measure and describe: no tool, description or
schema names a resource type, a metric or a rule for what to find, and a test scans this file and the specs for that.

The nine tools (Toolbox.specs) are estate_overview, list_resources, metric_names, metric_summary, measure, cost_lines, advisor_items, paid_features and describe. A call
that fails answers {"error": "<word>"} with one of the words in ERRORS. An answer of a tool that can fail for one subscription or one resource says so inside the answer.
list_resources and measure answer a table, to fit many resources in one answer: "cols" names the columns, each array in "rows" holds the values in that order, a value that
a row lacks is null and a null at the end of a row is left out, "same" holds the fields that have one value in every row, and "has_more" with "next_offset" says whether
and where the next page starts.

What the investigation may rely on after a run (it reads these and changes none):
  Toolbox.handles[h]    the Resource of handle h. A handle is in it only after an answer showed that resource, it is r<number> from r1 on, and it is never given to
                        another resource in the same run. Resource.cost_usd_30d is the sum of the cost lines of the resource over the 30 closed days, in USD, 2 decimals
                        (0.0 when it has no line), set when a tool shows the resource; it is None when the cost lines could not be read or are not in US dollars.
  Toolbox.evidence[h]   what the answers showed about h, as the same typed values that the agent read (same rounding). A key is there only when an answer showed it:
      "type"                              a word; every answer that shows a handle names the type
      "location", "sku", "kind"           a word; "managed" is a bool. list_resources leaves out a value that the resource lacks, describe gives None for it
      "cost30d", "costByService"          a number (a table gives whole dollars as an integer) and {service word: number}, when the cost lines are known and an answer
                                          showed them; only describe shows the split by service, a table shows the dearest service only
      "costLines"                         [{"service", "usd"}], the lines that cost_lines showed
      "properties"                        {key path: bool | number | word}: every property that an answer showed. The value is a list of up to three of those when the items
                                          of a list under that key differ in it
      "metrics"                           {metric name, exactly as metric_summary or measure showed it: {"total", "max", "average": a number, or None when the
                                          measurement was absent; "days_with_data": int; "days": int; "unit": a word or None}}. "total" is the number that the answer carried.
                                          A resource that measure or metric_summary could not read, or left out to fit the cap, has no entry.
      "advisor"                           [{"savingUsdMonth": number or None (a number only when Advisor gives the currency USD), "annualSavings", "currency", "impact",
                                          "typeId", "term", "lookback", "reservedType", "sku"}], one for each Advisor item that an answer showed for h
  Toolbox.log           one dict for each call: {"name", "arguments", "ok", "chars"}. Toolbox.call never raises.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from .arm import SCOPE_ID, Arm, CostLine, MetricPoint
from .foundry import FunctionTool
from .http import HttpError, Refused
from .identity import IdentityError

MAX_RESULT_CHARS = 6000
MAX_CALLS = 40  # calls of one Toolbox; the next ones answer "limit"
MAX_LISTED = 40  # resources or cost lines in one answer
MAX_MEASURE_ROWS = 80  # resources in one measure answer
DEFAULT_LISTED = 40  # resources in a list or a measurement when the agent gives no limit
DEFAULT_LINES = 20  # cost lines when the agent gives no limit
MAX_MEASURED = 60  # handles in one measurement
MAX_DAYS = 30  # the closed days of the cost lines and the most that a measurement looks back
HANDLE_LIMIT = 9999  # handles have at most four digits
SHOWN_PROPERTIES = 8  # varying properties, and as many properties that are the same, in a table of resources
DESCRIBED_PROPERTIES = 30
TOP_SERVICES = 20
TOP_TYPES = 30
TOP_COST_SERVICES = 3  # services of one resource in a list
ADVISOR_PAGE = 20
RESOLVE_CHUNK = 25  # resource ids in one read of Resource Graph
PARALLEL_READS = 8
READ_BUDGET_SECONDS = 60.0  # of one measurement
MAX_DEPTH = 4  # key levels of a property
MAX_NODES = 4000  # values looked at in the properties of one resource
LIST_ITEMS = 20  # items of a list that are looked at

ERRORS = ("bad-arguments", "unknown-tool", "unknown-handle", "unavailable", "limit", "too-large", "failed")
READ_ERRORS = (HttpError, Refused, IdentityError)

# The word checks. A pattern is written once, as the schema of the tools gives it to the agent, and compiled here; every check is a full match.
WORD_PATTERN = r"^[A-Za-z0-9_.-]{1,32}$"
TYPE_PATTERN = r"^[a-z0-9.]+(/[a-z0-9._-]+){1,4}$"
SERVICE_PATTERN = r"^[A-Za-z0-9 ().&+-]{1,60}$"
METRIC_PATTERN = r"^[A-Za-z0-9_./ -]{1,64}$"
HANDLE_PATTERN = r"^r[0-9]{1,4}$"
WORD, TYPE, SERVICE, METRIC, HANDLE = (re.compile(pattern) for pattern in (WORD_PATTERN, TYPE_PATTERN, SERVICE_PATTERN, METRIC_PATTERN, HANDLE_PATTERN))
VALUE = re.compile(r"[A-Za-z0-9_.-]{1,32}(?:/[A-Za-z0-9_.-]{1,32})?")  # a word, or two words with a slash between them
REGION = re.compile(r"[a-z0-9]{1,32}")
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# A property is shown only when the last part of its key ends in one of these, or is a number of something. The list is generic: it names no resource type.
SUFFIXES = ("State", "Status", "Code", "Tier", "Capacity", "Count", "Replicas", "Size", "GB", "Cores", "Mode", "Enabled", "Version", "Access", "Zone", "Zones",
            "Redundant", "Days", "Method", "Throughput")
COUNT_LIKE = frozenset(SUFFIXES.index(suffix) for suffix in ("Capacity", "Count", "Replicas", "Size", "GB", "Cores", "Throughput"))  # what `count` orders by
_ALTERNATIVES = "|".join(SUFFIXES)
LEAF = re.compile(rf"(?:[a-z][A-Za-z0-9]*)?(?:{_ALTERNATIVES})|(?:{_ALTERNATIVES.lower()})|(?:[a-z][A-Za-z0-9]*)?[Nn]umberOf[A-Z][A-Za-z0-9]*")
KEY = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")
# Names that hold somebody's text, or an address: never shown and never followed.
DENIED_KEYS = frozenset({"name", "id", "displayname", "description", "tags", "uri", "url", "endpoint", "endpoints", "host", "hostname", "ip", "address", "metadata",
                         "parameters", "labels", "annotations", "template", "definition", "variables", "outputs"})
# The fields of a table of resources that do not come from the properties, in the order of its columns. A property is never given one of these names.
FIXED_FIELDS = ("usd30d", "service", "sub", "sku", "kind", "region", "managed")

# Every read of Resource Graph starts with a comment that names it, as in detectors.py. Resource Graph refuses an alias that is the name of a column of the table
# (kind, here), so the two text columns that are turned into words get names of their own.
RESOURCE_COLUMNS = "project id, name, type, resourceGroup, subscriptionId, location, tags, managedByText = tostring(managedBy), kindName = tostring(kind), sku, properties"
TYPE_COUNTS = "// meternaut:estate-types\nresources\n| summarize n = count() by type"
TYPE_RESOURCES = "// meternaut:type-resources\nresources\n| where type =~ '{type}'\n| " + RESOURCE_COLUMNS
ONE_OF_TYPE = "// meternaut:one-of-type\nresources\n| where type =~ '{type}'\n| take 1\n| project id"
RESOURCES_BY_ID = "// meternaut:resources-by-id\nresources\n| where id in~ ({ids})\n| " + RESOURCE_COLUMNS

T = TypeVar("T")


def _match(pattern: "re.Pattern[str]", value: object) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def type_word(value: object) -> str | None:
    """A resource type as Azure names it, in lower case, or None when it has not the shape of one."""
    if not isinstance(value, str) or len(value) > 120 or not TYPE.fullmatch(value):
        return None
    return value if all(len(part) <= 50 for part in value.split("/")) else None


def kind_word(value: object) -> str | None:
    """A kind: one to four words, separated by commas."""
    if not isinstance(value, str) or len(value) > 48:
        return None
    parts = value.split(",")
    return value if len(parts) <= 4 and all(WORD.fullmatch(part) for part in parts) else None


def type_of_id(resource_id: str) -> str | None:
    """The resource type that an Azure resource id has, in lower case, or None when the id is not the id of a resource."""
    lowered = resource_id.lower()
    index = lowered.rfind("/providers/")
    if index < 0:
        return None
    parts = [part for part in lowered[index + len("/providers/"):].split("/") if part]
    if len(parts) < 3 or len(parts) % 2 == 0:
        return None
    return type_word("/".join([parts[0], *parts[1::2]]))


def _money(value: float) -> float:
    rounded = round(value, 2)
    return 0.0 if rounded == 0 else rounded


def _measure(value: float) -> int | float | None:
    """A measured number as the answers give it: a whole number as it is, any other with six significant digits, so that a small value is never rounded to zero."""
    if not math.isfinite(value):
        return None
    if value == int(value) and abs(value) < 1e15:
        return int(value)
    return float(f"{value:.6g}")


def _dump(answer: dict) -> str:
    return json.dumps(answer, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _cents(value: float) -> int | float:
    """A sum of money as the tables give it: dollars and cents, and a whole number of dollars as an integer."""
    return int(value) if value == int(value) else value


def _same(first: object, other: object) -> bool:
    """Equal and of the same type, item by item for a list, so that the flag true and the number one are two values."""
    if isinstance(first, list) and isinstance(other, list):
        return len(first) == len(other) and all(_same(one, two) for one, two in zip(first, other))
    return type(first) is type(other) and first == other


def _layout(rows: list[tuple[str, dict]]) -> tuple[dict, list[str], list[list], set[str]]:
    """A table of resources from (handle, fields) pairs. A field that every row has with the same value is given once, in `same`; any other field is a column, and
    a value that a row lacks is None (a None at the end of a row is left out). A field that no row has is not there at all. At most SHOWN_PROPERTIES properties that
    vary and as many that do not are shown, the most informative first. Returns `same`, the names of the columns (the handle first), the rows, and the properties
    that are shown, as a column or in `same`."""
    rows = [(handle, {name: value for name, value in cells.items() if value is not None}) for handle, cells in rows]
    present = {name for _, cells in rows for name in cells}
    properties = present - set(FIXED_FIELDS)

    def constant(name: str) -> bool:
        found = [cells.get(name) for _, cells in rows]
        return len(found) > 1 and found[0] is not None and all(value is not None and _same(found[0], value) for value in found)

    fixed = [name for name in FIXED_FIELDS if name in present]
    varying = sorted((name for name in properties if not constant(name)), key=_order)[:SHOWN_PROPERTIES]
    unchanged = sorted((name for name in properties if constant(name)), key=_order)[:SHOWN_PROPERTIES]
    columns = [name for name in fixed if not constant(name)] + varying
    same = {name: rows[0][1][name] for name in [*(name for name in fixed if constant(name)), *unchanged]}
    table: list[list] = []
    for handle, cells in rows:
        values = [handle, *(cells.get(name) for name in columns)]
        while len(values) > 1 and values[-1] is None:
            values.pop()
        table.append(values)
    return same, ["handle", *columns], table, {*varying, *unchanged}


def _scalar(value: object) -> bool | int | float | str | None:
    """A property value that may be shown: a flag, a number or a word; anything else is None."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) <= 10**15 else None
    if isinstance(value, float):
        return _measure(value)
    if isinstance(value, str) and VALUE.fullmatch(value):
        return value.lower() == "true" if value.lower() in ("true", "false") else value
    return None


def _rank(leaf: str) -> int:
    lowered = leaf.lower()
    if "numberof" in lowered:
        return SUFFIXES.index("Count")
    return next((place for place, suffix in enumerate(SUFFIXES) if lowered.endswith(suffix.lower())), len(SUFFIXES))


def _order(path: str) -> tuple[int, int, int, str]:
    leaf = path.rsplit(".", 1)[-1]
    return (1 if leaf == "provisioningState" else 0, _rank(leaf), path.count("."), path)


def typed_properties(properties: object, sku: object = None) -> list[tuple[str, "bool | int | float | str | list"]]:
    """The properties of a resource that an answer may show, the most informative first: a flag, a number or a word under a key that ends in one of the SUFFIXES,
    and the length of a list as <key>Count. A key comes from the shape of the resource and is checked like a word; a key that holds somebody's text is not followed.

    The items of a list are followed under the key of the list, so the value of a path is that of every item: one value when they agree, else up to three."""
    found: dict[str, list] = {}
    budget = [MAX_NODES]

    def add(path: tuple[str, ...], value: "bool | int | float | str") -> None:
        values = found.setdefault(".".join(path), [])
        if not any(type(seen) is type(value) and seen == value for seen in values):
            values.append(value)

    def walk(node: object, path: tuple[str, ...]) -> None:
        budget[0] -= 1
        if budget[0] < 0:
            return
        if isinstance(node, dict):
            if len(path) < MAX_DEPTH:
                for key, value in node.items():
                    if isinstance(key, str) and KEY.fullmatch(key) and key.lower() not in DENIED_KEYS:
                        walk(value, (*path, key))
        elif isinstance(node, list):
            if path:
                add((*path[:-1], f"{path[-1]}Count"), len(node))
                for item in node[:LIST_ITEMS]:
                    if isinstance(item, dict):
                        walk(item, path)
        elif path and LEAF.fullmatch(path[-1]):
            value = _scalar(node)
            if value is not None:
                add(path, value)

    walk(properties, ())
    if isinstance(sku, dict):
        walk({"sku": sku}, ())
    ranked = sorted(found.items(), key=lambda item: _order(item[0]))[:DESCRIBED_PROPERTIES]
    return [(path, values[0] if len(values) == 1 else values[:3]) for path, values in ranked]


@dataclass
class Resource:
    handle: str
    resource_id: str
    resource_type: str  # lower case, as Azure Resource Manager names it
    name: str
    resource_group: str
    subscription_id: str
    location: str
    tags: dict[str, str]
    managed_by: str
    cost_usd_30d: float | None = None


class BadArguments(Exception):
    """An argument is missing, of the wrong type, or outside its pattern or range."""


class UnknownHandle(Exception):
    """A handle that no answer has shown."""


class TooLarge(Exception):
    """An answer that cannot be made small enough, even with nothing left in its lists."""


@dataclass
class _Entry:
    """A resource that a read returned, with what an answer may say about it."""

    resource: Resource
    sub: str  # the subscription as the Toolbox has it
    sku: str | None
    kind: str | None
    location: str | None
    properties: list[tuple[str, "bool | int | float | str | list"]]
    size: float  # the largest count, size or capacity among the properties: what `count` orders by

    @property
    def key(self) -> str:
        return self.resource.resource_id.lower()


@dataclass
class _Costs:
    """The cost lines of one subscription over the closed days, added up."""

    by_resource: dict[str, dict[str, float]] = field(default_factory=dict)  # lower-case id -> service -> cost
    by_service: dict[str, float] = field(default_factory=dict)
    by_type: dict[str, float] = field(default_factory=dict)
    total: float = 0.0

    @classmethod
    def of(cls, lines: list[CostLine]) -> "_Costs":
        costs = cls()
        for line in lines:
            service = _match(SERVICE, line.service) or "other"
            costs.total += line.amount
            costs.by_service[service] = costs.by_service.get(service, 0.0) + line.amount
            per_service = costs.by_resource.setdefault(line.resource_id, {})  # a line that is tied to no resource has the empty id
            per_service[service] = per_service.get(service, 0.0) + line.amount
            kind = type_of_id(line.resource_id)
            if kind:
                costs.by_type[kind] = costs.by_type.get(kind, 0.0) + line.amount
        return costs


@dataclass
class _Advice:
    """One Advisor cost recommendation, as words and numbers that passed their checks."""

    facts: dict
    resource_id: str
    annual: float | None
    currency: str | None  # the word that Advisor gives; some recommendations give none


@dataclass(frozen=True)
class Param:
    """One argument of a tool. The same declaration gives the JSON schema that the agent reads and the check that a call must pass."""

    name: str
    kind: str  # type, service, metric, handle, handles, integer or choice
    description: str
    required: bool = False
    low: int = 0
    high: int = 0
    choices: tuple[str, ...] = ()

    def schema(self) -> dict:
        nullable = [] if self.required else ["null"]

        def typed(name: str) -> object:
            return [name, *nullable] if nullable else name

        if self.kind == "integer":
            body: dict = {"type": typed("integer"), "minimum": self.low, "maximum": self.high}
        elif self.kind == "choice":
            body = {"type": typed("string"), "enum": [*self.choices, None] if nullable else list(self.choices)}
        elif self.kind == "handles":
            body = {"type": "array", "items": {"type": "string", "pattern": HANDLE_PATTERN}, "minItems": 1, "maxItems": MAX_MEASURED}
        else:
            body = {"type": typed("string"), "pattern": {"type": TYPE_PATTERN, "service": SERVICE_PATTERN, "metric": METRIC_PATTERN, "handle": HANDLE_PATTERN}[self.kind]}
        return {**body, "description": self.description}

    def check(self, value: object) -> object:
        if self.kind == "integer":
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            if isinstance(value, bool) or not isinstance(value, int) or not self.low <= value <= self.high:
                raise BadArguments(self.name)
            return value
        if self.kind == "choice":
            if not isinstance(value, str) or value not in self.choices:
                raise BadArguments(self.name)
            return value
        if self.kind == "handles":
            if not isinstance(value, list) or not 1 <= len(value) <= MAX_MEASURED or not all(isinstance(item, str) and HANDLE.fullmatch(item) for item in value):
                raise BadArguments(self.name)
            return list(dict.fromkeys(value))
        text = {"type": type_word, "service": lambda item: _match(SERVICE, item), "metric": lambda item: _match(METRIC, item),
                "handle": lambda item: _match(HANDLE, item)}[self.kind](value)
        if text is None:
            raise BadArguments(self.name)
        return text


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: tuple[Param, ...] = ()

    def spec(self) -> FunctionTool:
        """Every parameter is listed as required and an optional one may be null, so that the schema is also valid where a schema must be strict."""
        return FunctionTool(self.name, self.description, {"type": "object", "properties": {param.name: param.schema() for param in self.params},
                                                          "required": [param.name for param in self.params], "additionalProperties": False})

    def check(self, arguments: object) -> dict:
        """The arguments of a call, checked and complete: an optional one that is missing or null is None."""
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict) or set(arguments) - {param.name for param in self.params}:
            raise BadArguments("arguments")
        checked: dict = {}
        for param in self.params:
            value = arguments.get(param.name)
            if value is None and param.required:
                raise BadArguments(param.name)
            checked[param.name] = None if value is None else param.check(value)
        return checked


_TYPE = "The resource type, in lower case, as estate_overview shows it."
_OFFSET = Param("offset", "integer", "How many entries to skip: the next_offset of the last answer. Null for 0.", low=0, high=100000)
TOOLS = {tool.name: tool for tool in (
    Tool("estate_overview",
         "Summarises the estate that this run may read. For each subscription (named s1, s2, ...): the number of resources, the cost of the last 30 days by service, "
         "and the resource types with their count and cost. The resource types are the names that the other tools take. It takes no arguments."),
    Tool("list_resources",
         "Lists the resources of one resource type, as a table. cols names the columns and each array in rows holds the values in that order; the first column is the "
         "handle (r1, r2, ...) that stands for the resource in this run only. A value that a row lacks is null, and a null at the end of a row is left out. same holds "
         "the fields that have the same value in every row. The fields are usd30d (the cost of the last 30 days, in dollars), service (the dearest service), sub "
         "(the subscription, when there are several), sku, kind, region, managed (true when another resource manages it) and a few properties, named by their key "
         "path, that are numbers, flags or words; the length of a list is given as <key>Count. The answer carries no names, tags or other text of the resources. Take "
         "the type from estate_overview. When has_more is true, read the next page with next_offset.",
         (Param("type", "type", _TYPE, required=True),
          Param("order_by", "choice", "cost: the dearest first. count: the largest count, size or capacity property first. Null for cost.", choices=("cost", "count")),
          Param("limit", "integer", "How many resources to return, 1 to 40. Null for 40.", low=1, high=MAX_LISTED), _OFFSET)),
    Tool("metric_names",
         "Lists the metric names that Azure Monitor offers for the resources of one resource type, each with its unit and its primary aggregation. Use a name with "
         "metric_summary or measure.",
         (Param("type", "type", _TYPE, required=True), _OFFSET)),
    Tool("metric_summary",
         "Measures one Azure Monitor metric for up to 60 resources, named by handle, in daily buckets over the last days (at most 30). For each resource: the total (the "
         "sum of the daily totals), the maximum (of the daily maximums), the average (the mean of the daily averages) and the number of days that have data. A value "
         "is null when the metric has none. A slow measurement stops after 60 seconds: the answer says partial and lists the handles that were not read.",
         (Param("handles", "handles", "Handles of resources that earlier answers showed, 1 to 60 of them.", required=True),
          Param("metric", "metric", "A metric name, as metric_names shows it.", required=True),
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS))),
    Tool("measure",
         "Measures one Azure Monitor metric across the resources of one resource type, the dearest first, in daily buckets over the last days (at most 30), as a table. "
         "cols names the columns and each array in rows holds the values in that order: handle (the same handle as in list_resources), usd30d (the cost of the last 30 "
         "days in dollars, left out when no cost is known), total (the sum of the daily totals), max (the greatest of the daily maximums), avg (the mean of the daily "
         "averages) and days_with_data (the number of days that have data). A value is null when the metric has none. failed lists the handles whose read failed. A slow "
         "measurement stops after 60 seconds: the answer says partial and lists the handles that were not read in unread. When has_more is true, read the next page with "
         "next_offset.",
         (Param("type", "type", _TYPE, required=True), Param("metric", "metric", "A metric name, as metric_names shows it.", required=True),
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS),
          Param("limit", "integer", "How many resources to measure, 1 to 80. Null for 40.", low=1, high=MAX_MEASURE_ROWS), _OFFSET)),
    Tool("cost_lines",
         "Lists the cost lines of the last 30 days, dearest first: for each one the handle of the resource (null when no such resource exists any more), the cost in US "
         "dollars, the service and the resource type. Filter by service name, as estate_overview shows it, and by resource type; with neither filter it lists the "
         "dearest lines of all.",
         (Param("service", "service", "A service name, as estate_overview shows it. Null for any service."),
          Param("type", "type", "A resource type, in lower case, as estate_overview shows it. Null for any type."),
          Param("limit", "integer", "How many lines to return, 1 to 40. Null for 20.", low=1, high=MAX_LISTED))),
    Tool("advisor_items",
         "Lists the cost recommendations of Azure Advisor as typed items, the largest annual savings first: the impact, the recommendation type id, the impacted "
         "resource type, the handle of the impacted resource (null when it is not a single resource), the annual savings and its currency (null when Advisor gives "
         "none), the term, the look-back period, the reserved resource type and the SKU. The answer carries no free text and no names. Read the next page with offset.",
         (_OFFSET,)),
    Tool("paid_features",
         "Lists, for each subscription, the plans and features that are billed per resource or per use once they are switched on, as Azure reports them: for each its "
         "name, its tier, its sub plan and its coverage, as short words. It takes no arguments."),
    Tool("describe",
         "Describes one resource by its handle: its type, SKU, kind, region, cost of the last 30 days, the cost by service and up to 30 properties that are numbers, flags "
         "or words. The answer carries no names, tags or other text of the resource.",
         (Param("handle", "handle", "The handle of a resource that an earlier answer showed.", required=True),)),
)}
SPECS = tuple(tool.spec() for tool in TOOLS.values())
PLACEHOLDER = f"r{HANDLE_LIMIT}"  # as long as any handle: an answer is cut to size with it, then given the real handles


def _page(answer: dict, rows: list, offset: int, total: int) -> None:
    """Keeps in the answer as many of its rows as fit under the cap, and says where the next page starts."""
    while True:
        answer["returned"] = len(rows)
        answer["next_offset"] = offset + len(rows) if offset + len(rows) < total else None
        if len(_dump(answer)) <= MAX_RESULT_CHARS or not rows:
            break
        rows.pop()
    if answer["next_offset"] is None:
        del answer["next_offset"]


def _summarise(points: list[MetricPoint]) -> dict:
    """The daily buckets of a metric as four numbers: the total is the sum of the daily totals, the maximum the greatest of the daily maximums, the average the mean
    of the daily averages. A number is None when no bucket has the aggregation."""
    totals = [point.total for point in points if point.total is not None]
    maxima = [point.maximum for point in points if point.maximum is not None]
    averages = [point.average for point in points if point.average is not None]
    return {"total": _measure(math.fsum(totals)) if totals else None, "max": _measure(max(maxima)) if maxima else None,
            "average": _measure(math.fsum(averages) / len(averages)) if averages else None,
            "days_with_data": sum(1 for point in points if point.total is not None or point.maximum is not None or point.average is not None)}


def _advice_of(record: dict) -> _Advice | None:
    properties = record.get("properties")
    if not isinstance(properties, dict):
        return None
    extended = properties.get("extendedProperties") if isinstance(properties.get("extendedProperties"), dict) else {}
    metadata = properties.get("resourceMetadata") if isinstance(properties.get("resourceMetadata"), dict) else {}
    raw = extended.get("annualSavingsAmount")
    try:
        amount = math.nan if isinstance(raw, bool) else float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        amount = math.nan
    annual = _money(amount) if math.isfinite(amount) and amount >= 0 else None
    currency = (_match(WORD, extended.get("savingsCurrency")) or "").upper() or None
    lookback = extended.get("lookbackPeriod")
    facts = {
        "impact": (_match(WORD, properties.get("impact")) or "").lower() or None,
        "type_id": (_match(GUID, properties.get("recommendationTypeId")) or "").lower() or None,
        "resource_type": type_word(str(properties.get("impactedField") or "").lower()),
        "annual_savings": annual,
        "currency": currency,
        "term": _match(WORD, extended.get("term")),
        "lookback": _match(WORD, lookback if isinstance(lookback, str) else str(lookback) if isinstance(lookback, int) and not isinstance(lookback, bool) else None),
        "reserved_type": _match(WORD, extended.get("reservedResourceType")),
        "sku": _match(WORD, extended.get("displaySKU")),
    }
    return _Advice(facts, str(metadata.get("resourceId") or ""), annual, currency)


def _logged_name(name: object) -> str:
    return name if isinstance(name, str) and name in TOOLS else re.sub(r"[^A-Za-z0-9_.-]", "?", str(name))[:40]


def _logged_arguments(arguments: object) -> dict:
    if not isinstance(arguments, dict):
        return {}
    try:
        return dict(arguments) if len(json.dumps(arguments)) <= 1000 else {"truncated": True}
    except (TypeError, ValueError):
        return {"truncated": True}


class Toolbox:
    """The tools of one run: `specs` for the agent, `call` for each tool call that it makes, and, afterwards, `handles`, `evidence` and `log` for the investigation."""

    def __init__(self, arm: Arm, subscriptions: tuple[str, ...], now: dt.datetime, notes: list[str]) -> None:
        self.arm, self.subscriptions, self.now, self.notes = arm, subscriptions, now, notes
        self.handles: dict[str, Resource] = {}  # every resource that an answer has shown, by handle
        self.evidence: dict[str, dict] = {}  # handle -> what the answers showed about it so far (metric aggregates, cost lines, typed properties)
        self.log: list[dict] = []  # one dict per call: name, arguments, ok, chars
        self.monotonic: Callable[[], float] = time.monotonic  # the clock of the time budget of a measurement; a test replaces it
        self.workers = PARALLEL_READS
        self.budget_seconds = READ_BUDGET_SECONDS
        self._lock = threading.Lock()
        self._calls = 0
        self._next_handle = 1
        self._entries: dict[str, _Entry] = {}  # every resource that a read returned, by lower-case id
        self._by_handle: dict[str, _Entry] = {}
        self._by_type: dict[tuple[str, str], list[str]] = {}
        self._counts: dict[str, tuple[int, dict[str, int]]] = {}
        self._costs: dict[str, _Costs | None] = {}
        self._advice: dict[str, list[_Advice]] = {}
        self._metric_names: dict[str, list[dict]] = {}
        self._missing: set[str] = set()  # ids that Resource Graph did not return

    @property
    def specs(self) -> tuple[FunctionTool, ...]:
        """The function tools that the agent is defined with."""
        return SPECS

    def call(self, name: str, arguments: dict) -> str:
        """Runs one tool. It never raises: a tool that fails answers {"error": "<a word from a fixed list>"}."""
        with self._lock:
            self._calls += 1
            answer = self._answer(name, arguments)
            text = _dump(answer)
            if len(text) > MAX_RESULT_CHARS:
                answer = {"error": "too-large"}
                text = _dump(answer)
            self.log.append({"name": _logged_name(name), "arguments": _logged_arguments(arguments), "ok": "error" not in answer, "chars": len(text)})
            return text

    def _answer(self, name: object, arguments: object) -> dict:
        if self._calls > MAX_CALLS:
            return {"error": "limit"}
        tool = TOOLS.get(name) if isinstance(name, str) else None
        if tool is None:
            return {"error": "unknown-tool"}
        try:
            return getattr(self, f"_tool_{tool.name}")(tool.check(arguments))
        except BadArguments:
            return {"error": "bad-arguments"}
        except UnknownHandle:
            return {"error": "unknown-handle"}
        except TooLarge:
            return {"error": "too-large"}
        except READ_ERRORS as error:
            self.notes.append(f"{tool.name}: a read failed ({str(error)[:200]})")
            return {"error": "unavailable"}
        except Exception as error:  # a tool never raises: a fault in one is a word and a note
            self.notes.append(f"{tool.name}: failed ({type(error).__name__})")
            return {"error": "failed"}

    # -- what the tools share ------------------------------------------------------------------------------------------------------------------
    def _label(self, sub: str) -> str:
        return f"s{list(self.subscriptions).index(sub) + 1}"

    def _note(self, sub: str, what: str, error: Exception) -> None:
        self.notes.append(f"{sub[:8]}: {what} could not be read ({str(error)[:200]})")

    def _today(self) -> dt.date:
        moment = self.now if self.now.tzinfo else self.now.replace(tzinfo=dt.timezone.utc)
        return moment.astimezone(dt.timezone.utc).date()

    def _each(self, read: Callable[[str], T], what: str) -> tuple[list[tuple[str, T]], list[str]]:
        """Runs a read in every subscription. A subscription that cannot be read is a note and is returned in the second list; when none can be read, the error is raised."""
        done: list[tuple[str, T]] = []
        failed: list[str] = []
        last: Exception | None = None
        for sub in self.subscriptions:
            try:
                done.append((sub, read(sub)))
            except READ_ERRORS as error:
                self._note(sub, what, error)
                failed.append(sub)
                last = error
        if last is not None and not done:
            raise last
        return done, failed

    def _costs_of(self, sub: str) -> _Costs | None:
        """The cost lines of a subscription, read once in a run. None when they could not be read or are not in US dollars."""
        if sub not in self._costs:
            self._costs[sub] = self._read_costs(sub)
        return self._costs[sub]

    def _read_costs(self, sub: str) -> _Costs | None:
        today = self._today()
        try:
            lines = self.arm.cost_lines(sub, today - dt.timedelta(days=MAX_DAYS), today - dt.timedelta(days=1))
        except READ_ERRORS as error:
            self._note(sub, "the cost lines", error)
            return None
        if any(line.currency != "USD" for line in lines):
            self.notes.append(f"{sub[:8]}: the cost lines are not in US dollars, so no tool shows a cost for it")
            return None
        return _Costs.of(lines)

    def _cost_total(self, entry: _Entry) -> float | None:
        costs = self._costs_of(entry.sub)
        return None if costs is None else _money(sum(costs.by_resource.get(entry.key, {}).values()))

    def _ingest(self, row: dict, sub: str) -> _Entry | None:
        """A row of Resource Graph as an entry. A resource that was read before keeps its entry, and so its handle."""
        resource_id = str(row.get("id") or "")
        key = resource_id.lower()
        if not key.startswith("/subscriptions/"):
            return None
        if key in self._entries:
            return self._entries[key]
        tags = row.get("tags")
        sku = row.get("sku") if isinstance(row.get("sku"), dict) else {}
        resource = Resource(handle="", resource_id=resource_id, resource_type=str(row.get("type") or "").lower(), name=str(row.get("name") or ""),
                            resource_group=str(row.get("resourceGroup") or ""), subscription_id=str(row.get("subscriptionId") or sub).lower(),
                            location=str(row.get("location") or ""), tags={str(k): str(v) for k, v in tags.items()} if isinstance(tags, dict) else {},
                            managed_by=str(row.get("managedByText") or ""))
        properties = typed_properties(row.get("properties"), sku)
        numbers = [number for path, value in properties if _rank(path.rsplit(".", 1)[-1]) in COUNT_LIKE for number in (value if isinstance(value, list) else [value])
                   if isinstance(number, (int, float)) and not isinstance(number, bool)]
        entry = _Entry(resource, sub, _match(WORD, sku.get("name")), kind_word(row.get("kindName")), _match(REGION, resource.location.lower()), properties,
                       float(max(numbers, default=0)))
        self._entries[key] = entry
        return entry

    def _facts(self, entry: _Entry, shown: int) -> dict:
        """What describe says about one resource, except its handle."""
        facts: dict = {}
        costs = self._costs_of(entry.sub)
        if costs is not None:
            lines = costs.by_resource.get(entry.key, {})
            facts["cost30d"] = _money(sum(lines.values()))
            facts["cost_by_service"] = {name: _money(amount) for name, amount in sorted(lines.items(), key=lambda item: (-item[1], item[0]))[:TOP_COST_SERVICES]}
        facts.update(sku=entry.sku, kind=entry.kind, location=entry.location, managed=bool(entry.resource.managed_by), properties=dict(entry.properties[:shown]))
        return facts

    def _cells(self, entry: _Entry) -> dict:
        """The fields of one resource in a table, named as the table names them. A field that the resource lacks is not there."""
        cells: dict = {}
        costs = self._costs_of(entry.sub)
        if costs is not None:
            lines = costs.by_resource.get(entry.key, {})
            cells["usd30d"] = _cents(_money(sum(lines.values())))
            if lines:
                cells["service"] = min(lines.items(), key=lambda item: (-item[1], item[0]))[0]
        if len(self.subscriptions) > 1:
            cells["sub"] = self._label(entry.sub)
        for name, value in (("sku", entry.sku), ("kind", entry.kind), ("region", entry.location)):
            if value is not None:
                cells[name] = value
        cells["managed"] = bool(entry.resource.managed_by)
        cells.update(entry.properties)
        return cells

    def _show(self, entry: _Entry, shown: dict) -> str | None:
        """Gives the resource its handle the first time that an answer shows it, and keeps what the answer showed about it. `shown` has the sku, kind, location, managed,
        cost30d, cost_by_service and properties that the answer carried, or fewer of them. None when the handles are used up."""
        resource = entry.resource
        if not resource.handle:
            if self._next_handle > HANDLE_LIMIT:
                return None
            resource.handle = f"r{self._next_handle}"
            self._next_handle += 1
            self.handles[resource.handle] = resource
            self._by_handle[resource.handle] = entry
        total = self._cost_total(entry)
        if total is not None:
            resource.cost_usd_30d = total
        record = self.evidence.setdefault(resource.handle, {})
        record["type"] = type_word(resource.resource_type)
        record.update({key: shown[key] for key in ("sku", "kind", "location", "managed", "cost30d") if key in shown})
        if "cost_by_service" in shown:
            record["costByService"] = dict(shown["cost_by_service"])
        if shown.get("properties"):
            record.setdefault("properties", {}).update(shown["properties"])
        return resource.handle

    def _within_handles(self, page: list[_Entry]) -> int:
        """How many of the first resources of a page can be shown: one that has no handle yet needs a new one, and a run has HANDLE_LIMIT of them."""
        free = HANDLE_LIMIT - self._next_handle + 1
        for place, entry in enumerate(page):
            if not entry.resource.handle:
                if free <= 0:
                    return place
                free -= 1
        return len(page)

    def _caveats(self, failed: list[str]) -> dict:
        """The parts of an answer that say what could not be read: the subscriptions without costs, and the ones whose resources could not be read."""
        said: dict = {}
        blind = [self._label(sub) for sub in self.subscriptions if self._costs_of(sub) is None]
        if blind:
            said["costs"] = "unavailable"
            if len(blind) < len(self.subscriptions):
                said["costs_unavailable"] = blind
        if failed:
            said["unavailable"] = [self._label(sub) for sub in failed]
        return said

    def _sub_of(self, key: str) -> str | None:
        parts = key.split("/")
        return next((sub for sub in self.subscriptions if len(parts) > 2 and sub.lower() == parts[2]), None)

    def _resolve(self, resource_ids: list[str]) -> None:
        """Reads the resources that no read has returned yet, so that an id from a cost line or from Advisor can have a handle. An id that Resource Graph does
        not return is remembered as missing."""
        wanted: dict[str, list[str]] = {}
        for resource_id in dict.fromkeys(resource_ids):
            key = resource_id.lower()
            sub = self._sub_of(key)
            if sub and key not in self._entries and key not in self._missing and SCOPE_ID.fullmatch(resource_id) and type_of_id(resource_id):
                wanted.setdefault(sub, []).append(resource_id)
        for sub, ids in wanted.items():
            for start in range(0, len(ids), RESOLVE_CHUNK):
                chunk = ids[start:start + RESOLVE_CHUNK]
                rows = self.arm.graph(sub, RESOURCES_BY_ID.format(ids=", ".join(f"'{item}'" for item in chunk)))
                found = {entry.key for entry in (self._ingest(row, sub) for row in rows) if entry}
                self._missing.update(item.lower() for item in chunk if item.lower() not in found)

    def _resolve_quietly(self, resource_ids: list[str]) -> None:
        try:
            self._resolve(resource_ids)
        except READ_ERRORS as error:
            self.notes.append(f"the resources of some ids could not be read ({str(error)[:200]})")

    def _load_type(self, sub: str, kind: str) -> list[_Entry]:
        if (sub, kind) not in self._by_type:
            rows = self.arm.graph(sub, TYPE_RESOURCES.format(type=kind))
            self._by_type[(sub, kind)] = [entry.key for entry in (self._ingest(row, sub) for row in rows) if entry]
        return [self._entries[key] for key in self._by_type[(sub, kind)]]

    def _type_counts(self, sub: str) -> tuple[int, dict[str, int]]:
        if sub not in self._counts:
            total, counts = 0, {}
            for row in self.arm.graph(sub, TYPE_COUNTS):
                number = row.get("n")
                if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                    continue
                total += number
                kind = type_word(str(row.get("type") or "").lower())
                if kind:
                    counts[kind] = counts.get(kind, 0) + number
            self._counts[sub] = (total, counts)
        return self._counts[sub]

    def _entry(self, handle: str) -> _Entry:
        if handle not in self._by_handle:
            raise UnknownHandle(handle)
        return self._by_handle[handle]

    # -- the tools -----------------------------------------------------------------------------------------------------------------------------
    def _tool_estate_overview(self, args: dict) -> dict:
        blocks: list[dict] = []
        for sub in self.subscriptions:
            block: dict = {"subscription": self._label(sub)}
            try:
                total, counts = self._type_counts(sub)
            except READ_ERRORS as error:
                self._note(sub, "the resources", error)
                blocks.append({**block, "error": "unavailable"})
                continue
            costs = self._costs_of(sub)
            block["resources"] = total
            if costs is None:
                block["costs"] = "unavailable"
            else:
                services = sorted(costs.by_service.items(), key=lambda item: (-item[1], item[0]))
                block["cost30d"] = _money(costs.total)
                block["services"] = [{"service": name, "usd": _money(amount)} for name, amount in services[:TOP_SERVICES]]
                if len(services) > TOP_SERVICES:
                    block["services_not_shown"] = len(services) - TOP_SERVICES
            by_type = costs.by_type if costs is not None else {}
            kinds = sorted(set(counts) | set(by_type), key=lambda kind: (-by_type.get(kind, 0.0), -counts.get(kind, 0), kind))
            block["types"] = [{"type": kind, "count": counts.get(kind, 0), **({"usd": _money(by_type.get(kind, 0.0))} if costs is not None else {})}
                              for kind in kinds[:TOP_TYPES]]
            if len(kinds) > TOP_TYPES:
                block["types_not_shown"] = len(kinds) - TOP_TYPES
            blocks.append(block)
        if blocks and all("error" in block for block in blocks):
            return {"error": "unavailable"}
        answer = {"window_days": MAX_DAYS, "subscriptions": blocks}
        while len(_dump(answer)) > MAX_RESULT_CHARS:
            lists = [(len(block[key]), key == "types", block, key) for block in blocks for key in ("types", "services") if block.get(key)]
            if not lists:
                raise TooLarge()
            _, _, block, key = max(lists, key=lambda item: item[:2])
            block[key].pop()
            block[f"{key}_not_shown"] = block.get(f"{key}_not_shown", 0) + 1
        return answer

    def _listed(self, kind: str, order: str) -> tuple[list[_Entry], list[str]]:
        """The resources of one type in the order of a listing, and the subscriptions whose resources could not be read."""
        done, failed = self._each(lambda sub: self._load_type(sub, kind), "the resources of a type")
        entries = [entry for _, found in done for entry in found]

        def cost(entry: _Entry) -> float:
            total = self._cost_total(entry)
            return 0.0 if total is None else total

        entries.sort(key=(lambda entry: (-entry.size, -cost(entry), entry.key)) if order == "count" else (lambda entry: (-cost(entry), entry.key)))
        return entries, failed

    def _tool_list_resources(self, args: dict) -> dict:
        kind, order, limit, offset = args["type"], args["order_by"] or "cost", args["limit"] or DEFAULT_LISTED, args["offset"] or 0
        entries, failed = self._listed(kind, order)
        page = entries[offset:offset + limit]
        page = page[:self._within_handles(page)]
        cells = [self._cells(entry) for entry in page]
        caveats = self._caveats(failed)

        def table(count: int) -> tuple[dict, list[list], set[str]]:
            same, columns, rows, visible = _layout([(PLACEHOLDER, cell) for cell in cells[:count]])
            more = offset + count < len(entries)
            answer = {"type": kind, "total": len(entries), "offset": offset, "has_more": more, **({"next_offset": offset + count} if more else {}), **caveats,
                      **({"same": same} if same else {}), "cols": columns, "rows": rows}
            return answer, rows, visible

        count = len(page)
        answer, rows, visible = table(count)
        while len(_dump(answer)) > MAX_RESULT_CHARS and count:
            count -= 1
            answer, rows, visible = table(count)
        for row, entry, cell in zip(rows, page, cells):
            shown: dict = {"managed": cell["managed"], "properties": {name: cell[name] for name in visible if name in cell}}
            shown.update({key: cell[name] for key, name in (("cost30d", "usd30d"), ("sku", "sku"), ("kind", "kind"), ("location", "region")) if name in cell})
            row[0] = self._show(entry, shown)
        return answer

    def _one_of_type(self, kind: str) -> str | None:
        """The id of one resource of the type, from a list that was read before or else from a read of its own."""
        for sub in self.subscriptions:
            if self._by_type.get((sub, kind)):
                return self._entries[self._by_type[(sub, kind)][0]].resource.resource_id
        done, _ = self._each(lambda sub: self.arm.graph(sub, ONE_OF_TYPE.format(type=kind)), "a resource of the type")
        for _, rows in done:
            for row in rows:
                if str(row.get("id") or "").lower().startswith("/subscriptions/"):
                    return str(row["id"])
        return None

    def _names_of(self, kind: str) -> list[dict]:
        if kind not in self._metric_names:
            found: dict[str, dict] = {}
            resource_id = self._one_of_type(kind)
            for definition in self.arm.metric_definitions(resource_id) if resource_id else []:
                name = definition.get("name")
                word = _match(METRIC, name.get("value") if isinstance(name, dict) else None)
                # A metric that is only offered for a chosen dimension cannot be measured without one, and metric_summary names none.
                if word is not None and definition.get("isDimensionRequired") is not True:
                    found.setdefault(word, {"name": word, "unit": _match(WORD, definition.get("unit")), "aggregation": _match(WORD, definition.get("primaryAggregationType"))})
            self._metric_names[kind] = sorted(found.values(), key=lambda item: item["name"].lower())
        return self._metric_names[kind]

    def _tool_metric_names(self, args: dict) -> dict:
        kind, offset = args["type"], args["offset"] or 0
        names = self._names_of(kind)
        rows = [dict(item) for item in names[offset:]]
        answer: dict = {"type": kind, "total": len(names), "offset": offset, "returned": 0, "next_offset": None, "metrics": rows}
        _page(answer, rows, offset, len(names))
        return answer

    def _window(self, days: int) -> tuple[dt.datetime, dt.datetime]:
        """The closed days that a measurement looks at: from midnight `days` days ago to the midnight that starts today, in UTC."""
        end = dt.datetime.combine(self._today(), dt.time(0, 0), tzinfo=dt.timezone.utc)
        return end - dt.timedelta(days=days), end

    @staticmethod
    def _outcome(future: Future) -> "tuple[str, list[MetricPoint]] | str":
        try:
            return future.result()
        except READ_ERRORS:
            return "unavailable"
        except Exception:  # a fault in one read is that resource's word, not the end of the measurement
            return "failed"

    def _read_metrics(self, targets: list[tuple[str, str]], metric: str, start: dt.datetime, end: dt.datetime) -> tuple[dict, list[str]]:
        """Reads the metric of every target, `workers` at a time, and starts no read after the time budget is spent. Returns what was read, by handle (the unit and
        the points, or a word for a read that failed), and the handles that were not read."""
        read: dict[str, "tuple[str, list[MetricPoint]] | str"] = {}
        queue = list(targets)
        running: dict[Future, str] = {}
        workers = max(1, self.workers)
        began = self.monotonic()
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            while queue or running:
                while queue and len(running) < workers and self.monotonic() - began < self.budget_seconds:
                    handle, resource_id = queue.pop(0)
                    running[pool.submit(self.arm.metrics, resource_id, metric, start, end)] = handle
                left = self.budget_seconds - (self.monotonic() - began)
                if not running or left <= 0:
                    break
                done, _ = wait(running, timeout=left, return_when=FIRST_COMPLETED)
                for future in done:
                    read[running.pop(future)] = self._outcome(future)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return read, [handle for handle, _ in targets if handle not in read]

    def _record_metric(self, handle: str, metric: str, summary: dict, days: int, unit: str | None) -> None:
        """Keeps the numbers that an answer carried for one resource, as the investigation checks the claims of the agent against them."""
        self.evidence.setdefault(handle, {}).setdefault("metrics", {})[metric] = {
            "total": summary["total"], "max": summary["max"], "average": summary["average"], "days_with_data": summary["days_with_data"], "days": days, "unit": unit}

    def _tool_metric_summary(self, args: dict) -> dict:
        handles, metric, days = args["handles"], args["metric"], args["days"] or MAX_DAYS
        start, end = self._window(days)
        read, unread = self._read_metrics([(handle, self.handles[handle].resource_id) for handle in handles if handle in self.handles], metric, start, end)
        skipped, rows, units = set(unread), [], {}
        for handle in handles:
            outcome = read.get(handle)
            if handle not in self.handles:
                rows.append({"handle": handle, "error": "unknown-handle"})
            elif isinstance(outcome, str):
                rows.append({"handle": handle, "error": outcome})
            elif outcome is not None:
                units[handle] = _match(WORD, outcome[0])
                rows.append({"handle": handle, **_summarise(outcome[1])})
        answer: dict = {"metric": metric, "days": days, "unit": None, "partial": False, "results": rows}

        def refresh() -> None:
            answer["unit"] = next((units[row["handle"]] for row in rows if units.get(row["handle"])), None)
            answer["partial"] = bool(skipped)
            if skipped:
                answer["unread"] = [handle for handle in handles if handle in skipped]

        refresh()
        while len(_dump(answer)) > MAX_RESULT_CHARS and rows:
            skipped.add(rows.pop()["handle"])
            refresh()
        for row in rows:
            if "error" not in row:
                self._record_metric(row["handle"], metric, row, days, units.get(row["handle"]))
        return answer

    def _tool_measure(self, args: dict) -> dict:
        kind, metric, days, limit, offset = args["type"], args["metric"], args["days"] or MAX_DAYS, args["limit"] or DEFAULT_LISTED, args["offset"] or 0
        entries, failed = self._listed(kind, "cost")
        page = entries[offset:offset + limit]
        page = page[:self._within_handles(page)]
        handles = [self._show(entry, {}) for entry in page]  # every resource of the page is named in the answer: as a row, as failed or as unread
        start, end = self._window(days)
        read, unread = self._read_metrics([(handle, entry.resource.resource_id) for handle, entry in zip(handles, page)], metric, start, end)
        costs = {handle: self._cost_total(entry) for handle, entry in zip(handles, page)}
        priced = any(cost is not None for cost in costs.values())
        summaries: dict[str, tuple[dict, str | None]] = {}
        broken: list[str] = []
        for handle in handles:
            outcome = read.get(handle)
            if isinstance(outcome, str):
                broken.append(handle)
            elif outcome is not None:
                summaries[handle] = (_summarise(outcome[1]), _match(WORD, outcome[0]))
        skipped = set(unread)
        columns = ["handle", *(["usd30d"] if priced else []), "total", "max", "avg", "days_with_data"]
        caveats = self._caveats(failed)
        more = offset + len(page) < len(entries)

        def row_of(handle: str) -> list:
            summary = summaries[handle][0]
            cost = costs[handle]
            return [handle, *([None if cost is None else _cents(cost)] if priced else []), summary["total"], summary["max"], summary["average"], summary["days_with_data"]]

        def answer() -> dict:
            kept = [handle for handle in handles if handle in summaries and handle not in skipped]
            unit = next((summaries[handle][1] for handle in kept if summaries[handle][1]), None)
            return {"type": kind, "metric": metric, "days": days, **({"unit": unit} if unit else {}), "partial": bool(skipped), "total": len(entries), "offset": offset,
                    "has_more": more, **({"next_offset": offset + len(page)} if more else {}), **caveats, **({"failed": broken} if broken else {}),
                    **({"unread": [handle for handle in handles if handle in skipped]} if skipped else {}), "cols": columns, "rows": [row_of(handle) for handle in kept]}

        built = answer()
        while len(_dump(built)) > MAX_RESULT_CHARS and any(handle in summaries and handle not in skipped for handle in handles):
            skipped.add(next(handle for handle in reversed(handles) if handle in summaries and handle not in skipped))
            built = answer()
        for handle, entry in zip(handles, page):
            if handle in summaries and handle not in skipped:
                if costs[handle] is not None:
                    self._show(entry, {"cost30d": _cents(costs[handle])})
                self._record_metric(handle, metric, summaries[handle][0], days, summaries[handle][1])
        return built

    def _tool_cost_lines(self, args: dict) -> dict:
        service, kind, limit = args["service"], args["type"], args["limit"] or DEFAULT_LINES
        lines: list[tuple[float, str, str | None, str]] = []
        blind = 0
        for sub in self.subscriptions:
            costs = self._costs_of(sub)
            if costs is None:
                blind += 1
                continue
            for key, per_service in costs.by_resource.items():
                found = type_of_id(key)
                if kind and found != kind:
                    continue
                lines += [(amount, name, found, key) for name, amount in per_service.items() if not service or name.lower() == service.lower()]
        if self.subscriptions and blind == len(self.subscriptions):
            return {"costs": "unavailable", "lines": []}
        lines.sort(key=lambda line: (-line[0], line[3], line[1]))
        page = lines[:limit]
        self._resolve_quietly([key for _, _, _, key in page])
        entries = [self._entries.get(key) for _, _, _, key in page]
        rows = [{"handle": PLACEHOLDER if entry else None, "usd": _money(amount), "service": name, "type": found} for (amount, name, found, _), entry in zip(page, entries)]
        answer: dict = {"service": service, "type": kind, "total": len(lines), "usd_total": _money(sum(line[0] for line in lines)), "returned": 0, "lines": rows}
        if blind:
            answer["costs"] = "unavailable"
        while True:
            answer["returned"] = len(rows)
            if len(_dump(answer)) <= MAX_RESULT_CHARS or not rows:
                break
            rows.pop()
        for row, entry in zip(rows, entries):
            if entry is not None:
                row["handle"] = self._show(entry, {})
                if row["handle"] is not None:
                    seen = self.evidence[row["handle"]].setdefault("costLines", [])
                    line = {"service": row["service"], "usd": row["usd"]}
                    if line not in seen:
                        seen.append(line)
        return answer

    def _advice_for(self, sub: str) -> list[_Advice]:
        if sub not in self._advice:
            self._advice[sub] = [advice for advice in map(_advice_of, self.arm.advisor_cost(sub)) if advice]
        return self._advice[sub]

    def _tool_advisor_items(self, args: dict) -> dict:
        offset = args["offset"] or 0
        done, failed = self._each(self._advice_for, "the cost recommendations")
        items = sorted((advice for _, found in done for advice in found),
                       key=lambda advice: (-(advice.annual if advice.annual is not None else -1.0), advice.facts["type_id"] or "", advice.resource_id.lower()))
        page = items[offset:offset + ADVISOR_PAGE]
        self._resolve_quietly([advice.resource_id for advice in page if advice.resource_id])
        entries = [self._entries.get(advice.resource_id.lower()) for advice in page]
        rows = []
        for place, (advice, entry) in enumerate(zip(page, entries), start=offset + 1):
            facts = advice.facts
            rows.append({"index": place, "impact": facts["impact"], "type_id": facts["type_id"], "resource_type": facts["resource_type"],
                         "handle": PLACEHOLDER if entry else None, "annual_savings": facts["annual_savings"], "currency": facts["currency"], "term": facts["term"],
                         "lookback": facts["lookback"], "reserved_type": facts["reserved_type"], "sku": facts["sku"]})
        answer: dict = {"total": len(items), "offset": offset, "returned": 0, "next_offset": None}
        if failed:
            answer["unavailable"] = [self._label(sub) for sub in failed]
        answer["items"] = rows
        _page(answer, rows, offset, len(items))
        for row, advice, entry in zip(rows, page, entries):
            if entry is not None:
                row["handle"] = self._show(entry, {})
                if row["handle"] is not None:
                    seen = self.evidence[row["handle"]].setdefault("advisor", [])
                    facts = advice.facts
                    month = _money(advice.annual / 12) if advice.annual is not None and advice.currency == "USD" else None  # a saving is in dollars only when Advisor says so
                    item = {"savingUsdMonth": month, "annualSavings": advice.annual, "currency": advice.currency, "impact": facts["impact"], "typeId": facts["type_id"],
                            "term": facts["term"], "lookback": facts["lookback"], "reservedType": facts["reserved_type"], "sku": facts["sku"]}
                    if item not in seen:
                        seen.append(item)
        return answer

    def _tool_paid_features(self, args: dict) -> dict:
        done, _ = self._each(self.arm.security_pricings, "the paid features")
        found = dict(done)
        blocks: list[dict] = []
        for sub in self.subscriptions:
            block: dict = {"subscription": self._label(sub)}
            if sub not in found:
                block["error"] = "unavailable"
            else:
                plans = []
                for item in found[sub]:
                    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
                    plan = _match(WORD, item.get("name"))
                    if plan is not None:
                        plans.append({"plan": plan, "tier": _match(WORD, properties.get("pricingTier")), "sub_plan": _match(WORD, properties.get("subPlan")),
                                      "coverage": _match(WORD, properties.get("resourcesCoverageStatus"))})
                block["plans"] = sorted(plans, key=lambda plan: plan["plan"].lower())
            blocks.append(block)
        answer = {"subscriptions": blocks}
        while len(_dump(answer)) > MAX_RESULT_CHARS:
            longest = max((block for block in blocks if block.get("plans")), key=lambda block: len(block["plans"]), default=None)
            if longest is None:
                raise TooLarge()
            longest["plans"].pop()
            longest["plans_not_shown"] = longest.get("plans_not_shown", 0) + 1
        return answer

    def _tool_describe(self, args: dict) -> dict:
        entry = self._entry(args["handle"])
        facts = self._facts(entry, DESCRIBED_PROPERTIES)
        answer = {"handle": args["handle"], "type": type_word(entry.resource.resource_type), **facts}
        while len(_dump(answer)) > MAX_RESULT_CHARS and answer["properties"]:
            answer["properties"].popitem()
        self._show(entry, facts)
        return answer
