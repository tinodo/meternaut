"""The tools of the investigator: read-only reads of the estate whose answers hold typed values only, and opaque handles instead of names.

A tool answer is a JSON string of at most MAX_RESULT_CHARS characters. A resource is named by a handle (r1, r2, ...) that means something only in this run: the id,
the name, the tags and every other text that somebody wrote about a resource stay in the Resource below and never go into an answer. What does go into an answer is a
number, a flag, a GUID, or a short word in the form that the platform itself uses. The checks bound the alphabet, the length and the number of parts of a word, and
that does not say what a word means, so a text goes into an answer only where the platform, and not the owner of the estate, chooses it:
  - a text of a property (STRING_LEAVES, KNOWN_PATHS) only under a key that is one of a fixed list of names of enumerations, never by the end of a key, and the keys of a
    property are plain names of at most MAX_SEGMENT characters, at most MAX_DEPTH levels down, that are not a container of somebody's text (DENIED_KEYS, DENIED_WORDS);
  - a SKU, a kind and a region of at most 24 characters, a service name of at most 40 characters and five words, a metric name that Azure Monitor offers for the type
    (and nothing else is ever measured), and the words of Advisor, of the paid plans and of Azure Monitor that have no separator (sku_word, service_word, metric_word,
    token_word). The names of several words are written as the platform writes them, each word with a capital letter (a short word such as "for" apart), which a sentence
    in lower case is not. A text that is there and fails its check is shown as "other", never as the text; a metric name or a plan that fails is left out.
The tools list, measure and describe: no tool, description or schema names a resource type, a metric or a rule for what to find, and a test scans this file and the specs
for that.

The nine tools (Toolbox.specs) are estate_overview, list_resources, metric_names, metric_summary, measure, cost_lines, advisor_items, paid_features and describe. A call
that fails answers {"error": "<word>"} with one of the words in ERRORS. An answer of a tool that can fail for one subscription or one resource says so inside the answer.
list_resources and measure answer a table, to fit many resources in one answer: "cols" names the columns, each array in "rows" holds the values in that order, a value that
a row lacks is null and a null at the end of a row is left out, "same" holds the fields that have one value in every row, and "has_more" with "next_offset" says whether
and where the next page starts.
measure and metric_summary also answer a "summary": {"resources", "with_data", "no_data", "zero", "positive", "days"}, the resources whose numbers an answer showed, counted
by whether the metric had data in the window. no_data is a resource with no value on any day, positive one with a total above 0, and zero any other resource that has data
(a total of 0, in practice); with_data is zero plus positive and resources is with_data plus no_data. For metric_summary it counts the resources of the call. For measure
it counts the resources of the type that this run has shown for that metric and window, in this answer and in the pages and calls before it, each resource once with its
latest measurement, so that the last page of a type covers all of it. A resource that failed (it is in "failed"), was not read in time or was cut from the answer (it is
in "unread") is in none of the counts until a read shows it; a read that fails changes no count. The summary is a count and nothing more: it names no resource, and the
evidence does not hold it.

What the investigation may rely on after a run (it reads these and changes none):
  Toolbox.handles[h]    the Resource of handle h. A handle is in it only after an answer showed that resource, it is r<number> from r1 on, and it is never given to
                        another resource in the same run. Resource.cost_usd_30d is the sum of the cost lines of the resource over the 30 closed days, in USD, 2 decimals
                        (0.0 when it has no line), set when a tool shows the resource; it is None when the cost lines could not be read or are not in US dollars.
  Toolbox.evidence[h]   what the answers showed about h, as the same typed values that the agent read (same rounding). A key is there only when an answer showed it:
      "type"                              a word; every answer that shows a handle names the type
      "location", "sku", "kind"           a word, or "other"; "managed" is a bool. list_resources leaves out a value that the resource lacks, describe gives None for it
      "cost30d", "costByService"          a number (a table gives whole dollars as an integer) and {service word: number}, when the cost lines are known and an answer
                                          showed them; only describe shows the split by service, a table shows the dearest service only
      "costLines"                         [{"service", "usd"}], the lines that cost_lines showed
      "properties"                        {key path: bool | number | word}: every property that an answer showed. The value is a list of up to three of those when the items
                                          of a list under that key differ in it
      "metrics"                           {metric name, exactly as metric_summary or measure showed it: {"total", "max", "average": a number, or None when the
                                          measurement was absent; "days_with_data": int; "days": int; "unit": a word or None; "totals": [a number or None]}}. "total" and
                                          the others are those of the last measurement, and "total" is the number that the answer carried. "totals" holds the total of every
                                          measurement of that metric of that resource that an answer carried, the oldest first, at most MAX_TOTALS of them (the last ones).
                                          A resource that measure or metric_summary could not read, or left out to fit the cap, has no entry and adds no total.
      "advisor"                           [{"savingUsdMonth": number or None (a number only when Advisor gives the currency USD), "annualSavings", "currency", "impact",
                                          "typeId", "term", "lookback", "reservedType", "sku"}], one for each Advisor item that an answer showed for h
      "volume"                            {"billable_gb": the whole volume that was charged for, "days": the window, "tables": how many tables had data}: what data_volume read for a
                                          resource that keeps records of the data written to it. `metrics` holds the first tables of it, as "Billable GB <table>"
      "writers"                           {a kind of data as data_volume names it: [the resource types that wrote most of it on the last closed day, the largest first, at most
                                          MAX_WRITER_KINDS]}: what data_writers showed for a kind of data
  Toolbox.table_names(h)  what the table handles of h stand for in this run (t1 is the name of a table that the platform did not make), for the page of a person and never for an agent
  Toolbox.log           one dict for each call: {"name", "arguments", "ok", "chars"}. Toolbox.call never raises.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

from . import capability, deeper, learning, library
from .arm import SCOPE_ID, Arm, CostLine, MetricPoint
from .detectors import some
from .foundry import FunctionTool
from .http import HttpError, Refused
from .identity import IdentityError
from .models import CapabilityRecord, StoreError

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
READ_WORKERS = 4  # subscriptions whose cost lines, recommendations or plans are read at the same time in one call: Cost Management allows 12 query units in 10 seconds for a tenant, and a 30 day read costs one
READ_BUDGET_SECONDS = 60.0  # of one measurement
SUBSCRIPTION_SECONDS = 45.0  # what the reads of the subscriptions in one tool call may take in all: a call that has used it reads no further subscription (what it read is kept)
NOT_READ_SHOWN = 5  # the subscriptions that an answer names, by label, when some were not read or could not be: it counts the rest
MAX_BLOCKS = 20  # the subscriptions that estate_overview and paid_features show when the estate has more: the dearest ones, with a count of the others
SUBSCRIPTION_NOTES = 10  # the notes about one subscription that could not be read: the later ones are counted in one note
MAX_DEPTH = 3  # key levels of a property; only the exact paths of KNOWN_PATHS may have one more
MAX_SEGMENT = 32  # characters of one key of a property
MAX_NODES = 4000  # values looked at in the properties of one resource
LIST_ITEMS = 20  # items of a list that are looked at
MAX_TOTALS = 20  # the totals of one metric of one resource that the evidence keeps
MAX_DIMENSIONS = 10  # the names of the dimensions of one metric that metric_names shows
MAX_SPLIT = 20  # values of a dimension in one answer of metric_split
DEFAULT_SPLIT = 10
MAX_HISTORY = 90  # the closed days that cost_history looks back, at most
DEFAULT_HISTORY = 30
DEFAULT_TABLES = 20  # kinds of data in one answer of data_readers when the agent gives no limit
MAX_SOURCES = 12  # the resources that data_writers shows for one kind of data
MAX_WRITER_KINDS = 3  # the kinds of resource that the evidence keeps for the writers of one kind of data
MAX_RULES = 20  # the collection rules that data_writers shows
MAX_CHILDREN = 40  # the parts of one resource that children shows
MAX_RESOURCES = 10  # the resources of a type that cost_history shows with their totals
MAX_LINES = 8  # the lines of one list of one subscription in the answer of commitments
MAX_OPEN_QUESTIONS = 15  # the rows of the answer of recall_open_questions
OPEN_COLUMNS = ("handle", "type", "seen", "days_open", "confidence", "request")
OPEN_SOURCE = "earlier findings that no person has decided: counts and words that Meternaut kept, not facts about this estate"
QUERY_SECONDS = 45.0  # what one read of a resource's own records may take
NOT_VISIBLE = "not visible with this access"  # what an answer says of a part that the access of the run cannot read: never "none"
READER_SOURCES = ("rules", "saved_searches", "workbooks", "analytics_rules")  # what data_readers counts, in the order of its columns
CHILD_COLUMNS = ("model", "version", "sku", "capacity", "requests_per_minute", "tokens_per_minute", "state", "upgrade")  # what children tells of each part, in the order of its columns

ERRORS = ("bad-arguments", "unknown-tool", "unknown-handle", "unknown-metric", "not-offered", "unavailable", "limit", "too-large", "failed")
READ_ERRORS = (HttpError, Refused, IdentityError, StoreError)
OTHER = "other"  # what an answer shows for a text that is there and fails its check: never the text itself

# The word checks. The patterns of the four arguments are written once, as the schema of the tools gives them to the agent, and compiled here; every check is a full match.
# The other checks keep a text that somebody could have written to the forms that the platform itself uses: a bound on the alphabet, the length and the number of parts.
TYPE_PATTERN = r"^[a-z0-9.]+(/[a-z0-9._-]+){1,4}$"
SERVICE_PATTERN = r"^[A-Za-z0-9 .&()-]{1,40}$"
METRIC_PATTERN = r"^[A-Za-z0-9_./ ]{1,64}$"
HANDLE_PATTERN = r"^r[0-9]{1,4}$"
TABLE_PATTERN = r"^(t[0-9]{1,4}|[A-Za-z][A-Za-z0-9]{0,63})$"  # a kind of data of a resource: a handle of this run or the name that the platform gave it
DIMENSION_PATTERN = r"^[A-Za-z][A-Za-z0-9]{0,40}$"  # the name of a dimension of a metric, as metric_names shows it
TYPE, SERVICE, METRIC, HANDLE, TABLE, DIMENSION = (re.compile(pattern) for pattern in (TYPE_PATTERN, SERVICE_PATTERN, METRIC_PATTERN, HANDLE_PATTERN, TABLE_PATTERN, DIMENSION_PATTERN))
SERVICE_FORM = re.compile(r"[A-Za-z0-9.&()-]+(?: [A-Za-z0-9.&()-]+){0,4}")  # one to five words, one space between them
SKU_FORM = re.compile(r"[A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+){0,2}")  # a SKU or a kind: one to three parts, separated by commas
TOKEN = re.compile(r"[A-Za-z0-9]+")  # a word of the platform that has no separator: an impact, a unit, a plan, a tier
VERSIONED = re.compile(r"[a-z][0-9]{1,3}")  # a word such as v2, which a name may have in lower case
VALUE = re.compile(r"[A-Za-z0-9_.-]{1,24}(?:/[A-Za-z0-9_.-]{1,24})?")  # the value of a property: a word, or two words with a slash between them
REGION = re.compile(r"[a-z0-9]{1,24}")
CURRENCY = re.compile(r"[A-Za-z]{3}")
NUMBER = re.compile(r"-?[0-9]{1,15}(?:\.[0-9]{1,9})?")  # a number that a property gives as text
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# A flag or a number of a property is shown only when the last part of its key ends in one of these, or is a number of something. The list is generic: it names no resource type. The last four
# are the units that a size is given in (scale units, bandwidth): without them a gateway's or a hub's size is a number that no tool could show.
SUFFIXES = ("State", "Status", "Code", "Tier", "Capacity", "Count", "Replicas", "Size", "GB", "Cores", "Mode", "Enabled", "Version", "Access", "Zone", "Zones",
            "Redundant", "Days", "Method", "Throughput", "Unit", "Units", "Mbps", "Gbps")
COUNT_LIKE = frozenset(SUFFIXES.index(suffix) for suffix in ("Capacity", "Count", "Replicas", "Size", "GB", "Cores", "Throughput", "Unit", "Units", "Mbps", "Gbps"))  # what `count` orders by
_ALTERNATIVES = "|".join(SUFFIXES)
LEAF = re.compile(rf"(?:[a-z][A-Za-z0-9]*)?(?:{_ALTERNATIVES})|(?:{_ALTERNATIVES.lower()})|(?:[a-z][A-Za-z0-9]*)?[Nn]umberOf[A-Z][A-Za-z0-9]*")
KEY = re.compile(rf"[A-Za-z][A-Za-z0-9]{{0,{MAX_SEGMENT - 1}}}")
# A text of a property is shown only when its key is exactly one of these names, which hold the values of an enumeration of the platform and never a text that somebody wrote
# (compared without regard to case, never by the end of a key). The list names no resource type and says nothing about what to look for.
STRING_LEAVES = frozenset(name.lower() for name in (
    "state", "status", "provisioningState", "powerState", "runningStatus", "availabilityState", "replicaState", "diskState", "jobState", "peeringState", "usageState",
    "largeFileSharesState", "statusOfPrimary", "statusOfSecondary", "healthStatus",
    "sku", "skuName", "skuTier", "skuFamily", "kind", "tier", "accessTier", "family", "size", "vmSize", "workerSize", "currentWorkerSize", "billingSku", "auxiliarySku",
    "offerType", "edition", "storageAccountType", "requestedServiceObjectiveName", "currentServiceObjectiveName", "osType", "licenseType", "priority",
    "mode", "computeMode", "capacityMode", "auxiliaryMode", "hostingMode", "environmentMode", "activeRevisionsMode", "patchingMode", "redundancyMode", "ipMode",
    "isolationMode", "zoneRedundancy", "replicationType", "redundancy", "storageRedundancy", "defaultConsistencyLevel",
    "version", "minimumTlsVersion", "minTlsVersion", "minimalTlsVersion", "gatewayVersion", "privateIPAddressVersion", "ipVersionType", "ipAddressType",
    "publicNetworkAccess", "publicNetworkAccessForIngestion", "publicNetworkAccessForQuery", "networkAccessPolicy", "defaultAction", "access", "direction",
    "privateIPAllocationMethod", "publicIPAllocationMethod", "ingestionAccessMode", "queryAccessMode"))
# The exact paths of properties that are shown whatever their key, and that may be a level deeper than MAX_DEPTH or have a part that is longer than MAX_SEGMENT.
KNOWN_PATHS = frozenset(tuple(path.split(".")) for path in (
    "privateLinkServiceConnections.properties.privateLinkServiceConnectionState.status",
    "manualPrivateLinkServiceConnections.properties.privateLinkServiceConnectionState.status",
    "privateEndpointConnections.properties.privateLinkServiceConnectionState.status",
    "extended.instanceView.powerState.code", "powerState.code", "agentPoolProfiles.powerState.code",
    "functionAppConfig.scaleAndConcurrency.alwaysReady.instanceCount",
    "virtualRouterAutoScaleConfiguration.minCapacity"))  # the key of a hub's units is longer than MAX_SEGMENT
_KNOWN_PREFIXES = frozenset(path[:length] for path in KNOWN_PATHS for length in range(1, len(path) + 1))
# Names that hold somebody's text, an address or a secret, or that hold a dictionary whose keys somebody chose: never shown and never followed, wherever they are in a
# path. A key is denied when the whole of it is one of these names, or when one of the words of its camel case is one of the DENIED_WORDS (nodeLabels, appSettings).
# (A text is shown only under the keys of STRING_LEAVES, so a key that holds one of a secret is hidden whether it is named here or not.)
DENIED_KEYS = frozenset({"name", "id", "displayname", "description", "tags", "uri", "url", "endpoint", "endpoints", "host", "hostname", "ip", "address", "metadata",
                         "parameters", "labels", "annotations", "template", "definition", "variables", "outputs",
                         "nodelabels", "nodetaints", "resourcetags", "settings", "protectedsettings", "publicsettings", "appsettings", "environmentvariables", "env",
                         "userdata", "customdata", "extensions", "secrets", "config", "credentials", "adminusername",
                         "username", "login", "owner", "contact", "email", "phone", "comment", "comments", "notes", "message", "messages", "title", "summary", "text",
                         "content", "body", "script", "command", "commands", "args", "arguments", "cloudinit", "query", "expression", "keys"})
DENIED_WORDS = frozenset({"label", "labels", "tag", "tags", "annotation", "annotations", "variable", "variables", "env", "secret", "secrets",
                          "credential", "credentials", "metadata", "extension", "extensions", "parameter", "parameters", "taint", "taints"})
# The fields of a table of resources that do not come from the properties, in the order of its columns. A property of the same name is not put in a table.
FIXED_FIELDS = ("usd30d", "service", "sub", "sku", "kind", "region", "managed")

# Every read of Resource Graph starts with a comment that names it, as in detectors.py. Resource Graph refuses an alias that is the name of a column of the table
# (kind, here), so the two text columns that are turned into words get names of their own.
RESOURCE_COLUMNS = "project id, name, type, resourceGroup, subscriptionId, location, tags, managedByText = tostring(managedBy), kindName = tostring(kind), sku, properties"
TYPE_COUNTS = "// meternaut:estate-types\nresources\n| summarize n = count() by type, subscriptionId"
TYPE_RESOURCES = "// meternaut:type-resources\nresources\n| where type =~ '{type}'\n| " + RESOURCE_COLUMNS
ONE_OF_TYPE = "// meternaut:one-of-type\nresources\n| where type =~ '{type}'\n| take 1\n| project id"
RESOURCES_BY_ID = "// meternaut:resources-by-id\nresources\n| where id in~ ({ids})\n| " + RESOURCE_COLUMNS

T = TypeVar("T")


def _match(pattern: "re.Pattern[str]", value: object) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def type_word(value: object) -> str | None:
    """A resource type as Azure names it, in lower case, or None when it has not the shape of one. The types of a custom provider have a part that the customer chose, so
    they have no word."""
    if not isinstance(value, str) or len(value) > 120 or not TYPE.fullmatch(value):
        return None
    parts = value.split("/")
    if any(len(part) > 50 for part in parts) or (parts[0] == "microsoft.customproviders" and len(parts) > 2):
        return None
    return value


def sku_word(value: object) -> str | None:
    """A SKU or a kind as the platform names it: at most 24 characters, of the letters, digits and _ . -, in at most three parts that are separated by commas."""
    return value if isinstance(value, str) and len(value) <= 24 and SKU_FORM.fullmatch(value) else None


def region_word(value: object) -> str | None:
    return value if isinstance(value, str) and REGION.fullmatch(value) else None


def token_word(value: object, limit: int = 32) -> str | None:
    """A word of the platform that has no separator (an impact, a unit, a plan, a tier) of at most `limit` letters and digits."""
    return value if isinstance(value, str) and len(value) <= limit and TOKEN.fullmatch(value) else None


def _titled(words: list[str]) -> bool:
    """Whether the words of a name that has several are written as the platform writes them: each starts with a capital letter, a digit, ( or &, apart from a short word
    such as "for" or "of" and a version such as "v2". A sentence in lower case is not written so."""
    return len(words) == 1 or all(word[0].isupper() or word[0].isdigit() or word[0] in "(&" or (word.isalpha() and len(word) <= 3) or VERSIONED.fullmatch(word) is not None
                                  for word in words)


def _service_form(value: object) -> str | None:
    return value if isinstance(value, str) and len(value) <= 40 and SERVICE_FORM.fullmatch(value) else None


def service_word(value: object) -> str | None:
    """A service name as Azure Cost Management gives it: at most 40 characters of the letters, digits and . & ( ) -, in at most five words with one space between them,
    written as the platform writes its names (see _titled)."""
    text = _service_form(value)
    return text if text is not None and _titled(text.split(" ")) else None


def metric_word(value: object) -> str | None:
    """A metric name as Azure Monitor gives it: at most 64 characters of the letters, digits and _ . / and spaces, in at most eight words, written as the platform writes its
    names (see _titled): the names of the platform are written so, and a sentence is not."""
    if not isinstance(value, str) or not METRIC.fullmatch(value):
        return None
    words = value.split(" ")
    if len(words) > 8 or not all(words):
        return None
    return value if _titled(words) else None


def property_value(value: object) -> str | None:
    """The value of a property that is shown as text: a word of at most 24 characters, or two such words with a slash between them (32 characters in all)."""
    return value if isinstance(value, str) and len(value) <= 32 and VALUE.fullmatch(value) else None


def _shown(check: "Callable[[object], str | None]", value: object) -> str | None:
    """A text as an answer gives it: the text when it passes its check, the word `other` when it is there and does not, None when there is none."""
    if not isinstance(value, str) or not value.strip():
        return None
    return check(value) or OTHER


def _words(key: str) -> list[str]:
    """The words of a key written in camel case, in lower case."""
    return [word.lower() for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", key)]


def _denied(key: str) -> bool:
    return key.lower() in DENIED_KEYS or any(word in DENIED_WORDS for word in _words(key))


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


def _leaf(path: tuple[str, ...], node: object) -> "bool | int | float | str | None":
    """The value of a leaf of the properties that an answer may show. A flag or a number is shown under a key that ends in one of the SUFFIXES, and so are the text "true"
    or "false" and a number that is given as text, as what they say. Any other text is shown only under a key that is one of the STRING_LEAVES, and then as a short word,
    or as `other` when it is not one. The exact paths of KNOWN_PATHS are shown whatever their key."""
    exact = path in KNOWN_PATHS
    generic = exact or bool(LEAF.fullmatch(path[-1]))
    if isinstance(node, bool):
        return node if generic else None
    if isinstance(node, int):
        return node if generic and abs(node) <= 10**15 else None
    if isinstance(node, float):
        return _measure(node) if generic else None
    if not isinstance(node, str):
        return None
    if generic and node.lower() in ("true", "false"):
        return node.lower() == "true"
    if generic and NUMBER.fullmatch(node):
        return int(node) if "." not in node else _measure(float(node))
    return _shown(property_value, node) if exact or path[-1].lower() in STRING_LEAVES else None


def _may_follow(path: tuple[str, ...]) -> bool:
    """Whether a key path may be followed: an exact path of KNOWN_PATHS or a part of one, or else a path of at most MAX_DEPTH keys of which the last is a plain name of
    at most MAX_SEGMENT characters that does not hold somebody's text. (The keys before it were followed, so they passed.)"""
    return path in _KNOWN_PREFIXES or (len(path) <= MAX_DEPTH and KEY.fullmatch(path[-1]) is not None and not _denied(path[-1]))


def _rank(leaf: str) -> int:
    lowered = leaf.lower()
    if "numberof" in lowered:
        return SUFFIXES.index("Count")
    return next((place for place, suffix in enumerate(SUFFIXES) if lowered.endswith(suffix.lower())), len(SUFFIXES))


def _order(path: str) -> tuple[int, int, int, str]:
    leaf = path.rsplit(".", 1)[-1]
    return (1 if leaf == "provisioningState" else 0, _rank(leaf), path.count("."), path)


def typed_properties(properties: object, sku: object = None) -> list[tuple[str, "bool | int | float | str | list"]]:
    """The properties of a resource that an answer may show, the most informative first: a flag or a number under a key that ends in one of the SUFFIXES, a short word
    under a key that is one of the STRING_LEAVES, and the length of a list as <key>Count. The keys come from the shape of the resource, so a key is followed only when it is
    a plain name of at most MAX_SEGMENT characters, at most MAX_DEPTH levels down, and does not hold somebody's text or a dictionary whose keys somebody chose.

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
            for key, value in node.items():
                if isinstance(key, str) and _may_follow((*path, key)):
                    walk(value, (*path, key))
        elif isinstance(node, list):
            if path:
                counted = (*path[:-1], f"{path[-1]}Count")
                if _may_follow(counted):
                    add(counted, len(node))
                for item in node[:LIST_ITEMS]:
                    if isinstance(item, dict):
                        walk(item, path)
        elif path:
            value = _leaf(path, node)
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
    part_of: str | None = None  # the key of the resource that keeps it inside itself: a part is billed with that resource and has no cost of its own, which is not a cost of nil


class BadArguments(Exception):
    """An argument is missing, of the wrong type, or outside its pattern or range."""


class UnknownHandle(Exception):
    """A handle that no answer has shown."""


class NotOffered(Exception):
    """A tool that has nothing to read on the type of the resource that the handle stands for."""


class TooLarge(Exception):
    """An answer that cannot be made small enough, even with nothing left in its lists."""


@dataclass(frozen=True)
class Failed:
    """The outcome of a read of one subscription that ended in an error of the reads (READ_ERRORS)."""

    error: Exception


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
    part_of: str | None = None  # the key of the resource that keeps it inside itself, for a part that Resource Graph does not list: it has no cost of its own

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
            service = service_word(line.service) or OTHER
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


@dataclass
class _Space:
    """What one run knows of a resource that keeps records of the data written to it: its settings and its list of tables, each as a word that says whether it was read."""

    pricing: dict
    customer: str | None  # the id that the query API names it by
    tables: "deeper.TableBook"
    settings: str  # `read`, NOT_VISIBLE or `unavailable`
    listing: str  # the same, for the list of tables


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
            body = {"type": typed("string"), "pattern": {"type": TYPE_PATTERN, "service": SERVICE_PATTERN, "metric": METRIC_PATTERN, "handle": HANDLE_PATTERN, "table": TABLE_PATTERN,
                                                        "dimension": DIMENSION_PATTERN}[self.kind]}
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
        text = {"type": type_word, "service": _service_form, "metric": lambda item: _match(METRIC, item), "handle": lambda item: _match(HANDLE, item),
                "table": lambda item: _match(TABLE, item), "dimension": lambda item: _match(DIMENSION, item)}[self.kind](value)
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
_METRIC = "A metric name, as metric_names shows it. A name that metric_names does not show for the type answers unknown-metric."
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
         "path, that are numbers, flags or words; the length of a list is given as <key>Count. A text that is not a short word of the platform is shown as other. The "
         "answer carries no names, tags or other text of the resources. Take the type from estate_overview. When has_more is true, read the next page with next_offset.",
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
         "is null when the metric has none. summary counts the resources that were read in this call by whether the metric had data in the window: resources, with_data "
         "(zero has a total of 0, positive a total above 0), no_data and days. A slow measurement stops after 60 seconds: the answer says partial and lists the handles "
         "that were not read.",
         (Param("handles", "handles", "Handles of resources that earlier answers showed, 1 to 60 of them.", required=True),
          Param("metric", "metric", _METRIC, required=True),
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS))),
    Tool("measure",
         "Measures one Azure Monitor metric across the resources of one resource type, the dearest first, in daily buckets over the last days (at most 30), as a table. "
         "cols names the columns and each array in rows holds the values in that order: handle (as in list_resources), usd30d (the cost of the last 30 days in dollars; "
         "left out when unknown), total (the sum of the daily totals), max (the greatest daily maximum), avg (the mean of the daily averages) and days_with_data (the "
         "days that have data). A value is null when the metric has none. summary counts the resources of the type shown so far, in this answer "
         "and earlier ones, by whether the metric had data in the window: resources, with_data (zero has a total of 0, positive a total above 0), no_data and days. "
         "failed lists the handles whose read failed. A measurement stops after 60 seconds: partial is then true and unread lists the handles that were not read. "
         "When has_more is true, read the next page with next_offset.",
         (Param("type", "type", _TYPE, required=True), Param("metric", "metric", _METRIC, required=True),
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS),
          Param("limit", "integer", "How many resources to measure, 1 to 80. Null for 40.", low=1, high=MAX_MEASURE_ROWS), _OFFSET)),
    Tool("cost_lines",
         "Lists the cost lines of the last 30 days, dearest first: for each one the handle of the resource (null when no such resource exists any more), the cost in US "
         "dollars, the service and the resource type. Filter by service name, as estate_overview shows it, and by resource type; with neither filter it lists the "
         "dearest lines of all.",
         (Param("service", "service", "A service name, as estate_overview shows it (at most 5 words). Null for any service."),
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
         "or words. When the type has deeper reads, reads names them. The answer carries no names, tags or other text of the resource.",
         (Param("handle", "handle", "The handle of a resource that an earlier answer showed.", required=True),)),
    Tool("data_volume",
         "Reads what a resource records about the data written to it, over the closed days of a window, as a table: for each kind of data its plan, how long it is kept, the "
         "volume that is charged for in GB, its share of the whole, how many days had data, the free volume when there is some, and its trend in equal parts of the "
         "window, the oldest first. It also gives the resource's pricing tier, retention and daily cap. A kind of data that the platform made is named; any other is a "
         "handle (t1, t2, ...) for this run only. A volume can be cited as the metric 'Billable GB <kind of data>'. What this run's access cannot read is said so and is "
         "never counted as none. When has_more is true, read the next page with next_offset.",
         (Param("handle", "handle", "The handle of a resource whose reads field names data_volume.", required=True),
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS), _OFFSET)),
    Tool("data_readers",
         "Counts what reads the kinds of data that a resource keeps: for each kind of data, how many rules, saved searches, workbooks and analytics rules name it, and how many times what "
         f"people ran named it, when the resource records that (it reads the {deeper.MAX_AUDIT_TEXTS} texts that were run most often: when there were more, a kind that none of them names is null, "
         "and the source says texts_cut). Each source says how many of its items were read, so that 0 means that none of those named it; a source that this run's "
         "access cannot read says so and its counts are null. Items that read every kind of data at once name none: they are counted apart, as scanning_all. A count can be cited as the "
         "metric 'Readers <kind of data>' (the items that name it plus those that read every kind) and 'Runs <kind of data>'; a source that was not read makes it null. It shows no name "
         "and no text of an item. Kinds of data are named as data_volume names them.",
         (Param("handle", "handle", "The handle of a resource whose reads field names data_readers.", required=True),
          Param("limit", "integer", "How many kinds of data to return, 1 to 40. Null for 20.", low=1, high=MAX_LISTED), _OFFSET)),
    Tool("data_writers",
         "Shows what writes to a resource that takes in data, or where a resource sends its own data. For a resource whose reads field names data_writers: the collection rules that send "
         "to it, as handles with typed facts (the kinds and number of their data sources, their flows, how many flows filter the data before it is stored, the kinds of data that they "
         "write); and, with table, the resources that wrote the most of that kind of data on the last closed day, as handles with their share (only for a kind of data on the plan that "
         "is free to read: any other says so). For any other resource: its diagnostic settings, as the number of categories of logs and of metrics that each sends and the kinds of "
         "destination.",
         (Param("handle", "handle", "The handle of a resource that takes in data (its reads field names data_writers), or of any resource to see where it sends its own data.", required=True),
          Param("table", "table", "One kind of data, as data_volume names it: the platform's name or a handle t1, t2, .... Null for none.")), ),
    Tool("children",
         "Lists the parts that a resource keeps inside itself and that Resource Graph does not list as resources, as a table of handles: for each its model (as kind), "
         "version, SKU, capacity, rate limits a minute for requests and for tokens, state and what happens to it when its version is retired, as typed values. A handle "
         "that this shows can be given to describe, to metric_summary, and metric_split names it for a value of a dimension. The reads field of list_resources and describe "
         "says which types have such parts.",
         (Param("handle", "handle", "The handle of a resource whose reads field names children.", required=True),)),
    Tool("metric_split",
         "Measures one Azure Monitor metric of one resource split by one dimension of it, in daily buckets over the last days (at most 30), as a table of values: for each "
         "value its total, maximum, average and the days that have data. A value that is the name of a part that children showed is given as that part's handle, a whole "
         "number as that number, any other value as a label (v1, v2, ...) that stands for it in this answer only. A value with no data in the window has no row. "
         "metric_names shows the dimensions that each metric has.",
         (Param("handle", "handle", "The handle of a resource that an earlier answer showed.", required=True), Param("metric", "metric", _METRIC, required=True),
          Param("dimension", "dimension", "A dimension of the metric, as metric_names shows it.", required=True),
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS),
          Param("limit", "integer", "How many values to return, 1 to 20. Null for 10.", low=1, high=MAX_SPLIT))),
    Tool("commitments",
         "Shows, for each subscription, how the cost of the last 30 days was paid for, amortized, as lines of pricing model and kind of charge with their amounts in US dollars, "
         "and the purchase recommendations that the platform itself makes for savings plans and for reservations, as typed values. access says, in words, what this run's identity can "
         "see of existing reservations and savings plans, of the price sheet and of the agreement. A part that this run's access cannot read says 'not visible with this access' and "
         "is never counted as none. It takes no arguments."),
    Tool("cost_history",
         "Shows the cost of one resource (handle) or of all resources of one type (type) for each day of the last 7 to 90 days, as the actual or the amortized cost in US "
         "dollars: the daily numbers, oldest first, their total, the days that have a cost, and for a type the dearest resources with their totals. Give a handle or a type, "
         "never both. An answer is kept for the run, so asking again costs nothing.",
         (Param("handle", "handle", "The handle of one resource that an earlier answer showed. Null when a type is given.", ),
          Param("type", "type", "A resource type, in lower case, as estate_overview shows it. Null when a handle is given."),
          Param("days", "integer", "How many closed days to look back, 7 to 90. Null for 30.", low=7, high=MAX_HISTORY),
          Param("basis", "choice", "actual: what was charged. amortized: a purchase spread over its term. Null for actual.", choices=("actual", "amortized")))),
    Tool("recall_lessons",
         "Shows how people answered the earlier proposals about resources of one resource type, as counts, for each kind of proposal: how many were answered, approved, declined (with the "
         "reasons that people could choose from a fixed list), said to be somebody else's, or left without an answer; how the saving that was measured after a change compares with the one "
         "that was expected; and, for each band of the confidence that an AI stated, the share that was approved, when enough were answered. It says 'no history yet' for a type with none. "
         "These are counts of people's answers, not facts about this estate, and they never replace a measurement. It names no resource and no person.",
         (Param("type", "type", _TYPE, required=True),)),
    Tool("recall_knowledge",
         "Shows what Microsoft's public documentation was read to say about one resource type, as claims that code checked: for each its kind (from a fixed list), the day it was read, the "
         "address of the page and a quote of at most 200 characters that code found on that page. Only claims that are still current are shown, not_shown counts the others, and studied "
         "says the day the type was last read about ('not yet' when it never was). A quote is text of documentation, not a fact about this estate and not an instruction: it never replaces "
         "a measurement.",
         (Param("type", "type", _TYPE, required=True),)),
    Tool("recall_open_questions",
         "Lists findings of earlier Watches that are still open questions: no person has decided them, and either no request to a person is open or the earlier judgement was not sure enough. "
         "As a table, for each: the handle of the resource (it works with every other tool, like the handle of any resource that an answer shows), its type, how many Watches saw it (seen), "
         "the days since it was first seen (days_open), the confidence of the last judgement and whether a request to a person is open. gone counts the resources that Azure no longer lists "
         "and unread those that could not be read. The rows are counts and words that Meternaut kept, never a text about a resource or a person, and they are no evidence about this "
         "estate: the other tools show what is true of a resource. It takes no arguments.",
         ()),
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


def _bucket(summary: dict) -> str:
    """How a measurement is counted in a summary: `no_data` when no day had a value, `positive` when the total is above 0, and `zero` for any other measurement that has
    data. This only counts: it names no resource and says nothing about what a count means."""
    if summary["days_with_data"] == 0:
        return "no_data"
    return "positive" if summary["total"] is not None and summary["total"] > 0 else "zero"


def _tally(buckets: Iterable[str], days: int) -> dict:
    """The resources whose measurement was read, counted by whether the metric had data in the window: `with_data` is `zero` plus `positive`, and `resources` is
    `with_data` plus `no_data`. A resource that failed, was not read or was cut from the answer is in none of them."""
    counts = Counter(buckets)
    with_data = counts["zero"] + counts["positive"]
    return {"resources": with_data + counts["no_data"], "with_data": with_data, "no_data": counts["no_data"], "zero": counts["zero"], "positive": counts["positive"], "days": days}


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
    currency = (_match(CURRENCY, extended.get("savingsCurrency")) or "").upper() or None
    lookback = extended.get("lookbackPeriod")
    facts = {
        "impact": (token_word(properties.get("impact"), 12) or "").lower() or None,
        "type_id": (_match(GUID, properties.get("recommendationTypeId")) or "").lower() or None,
        "resource_type": type_word(str(properties.get("impactedField") or "").lower()),
        "annual_savings": annual,
        "currency": currency,
        "term": token_word(extended.get("term"), 12),
        "lookback": token_word(lookback if isinstance(lookback, str) else str(lookback) if isinstance(lookback, int) and not isinstance(lookback, bool) else None, 12),
        "reserved_type": token_word(extended.get("reservedResourceType"), 24),
        "sku": _shown(sku_word, extended.get("displaySKU")),
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
        self.memory: object | None = None  # the store of the loop, which the tools that recall read; the investigation sets it, and a run that keeps no memory has none
        self.profile: object | None = None  # what the identity can see (cases/capability.py): the investigation sets it, and `commitments` shows its four words
        self.handles: dict[str, Resource] = {}  # every resource that an answer has shown, by handle
        self.evidence: dict[str, dict] = {}  # handle -> what the answers showed about it so far (metric aggregates, cost lines, typed properties)
        self.log: list[dict] = []  # one dict per call: name, arguments, ok, chars
        self.monotonic: Callable[[], float] = time.monotonic  # the clock of the time budget of a measurement; a test replaces it
        self.workers = PARALLEL_READS
        self.read_workers = READ_WORKERS  # subscriptions read at the same time; 1 reads them one after the other
        self.budget_seconds = READ_BUDGET_SECONDS
        self.read_seconds = SUBSCRIPTION_SECONDS  # the time of the reads of the subscriptions in one call; the investigation or a test sets it
        self._began = 0.0  # when the call that is running began
        self._timed = False  # whether a call is running, so that its time can be used up
        self._skipped: dict[str, None] = {}  # the subscriptions that this call did not read because its time was used up, in the order of the list
        self._noted = 0
        self._lock = threading.Lock()
        self._notes_lock = threading.Lock()  # the reads of several subscriptions at once write their notes through it
        self._calls = 0
        self._next_handle = 1
        self._entries: dict[str, _Entry] = {}  # every resource that a read returned, by lower-case id
        self._by_handle: dict[str, _Entry] = {}
        self._by_type: dict[tuple[str, str], list[str]] = {}
        self._counts: dict[str, tuple[int, dict[str, int]]] = {}
        self._costs: dict[str, _Costs | None] = {}
        self._advice: dict[str, list[_Advice]] = {}
        self._pricings: dict[str, list[dict]] = {}
        self._metric_names: dict[str, list[dict]] = {}
        self._without: set[str] = set()  # the types of which a read found no resource in any subscription, so that a later call does not look again
        self._reads: dict[tuple[str, str, int], dict[str, str]] = {}  # (type, metric, days) -> handle -> how its measurement counts: every resource whose numbers were shown
        self._missing: set[str] = set()  # ids that Resource Graph did not return
        self._unlisted: set[str] = set()  # the subscriptions whose resources Resource Graph could not give in this run: no listing asks for them again, and every answer that lists names them
        self._spaces: dict[str, _Space] = {}  # handle -> what is known of its settings and tables
        self._volumes: dict[tuple[str, int], tuple[list, float, str]] = {}  # (handle, days) -> the tables by volume, the billable MB, and the word that says whether it was read
        self._kept: dict[tuple, object] = {}  # what the deeper reads of the run have read, by what they asked for: a read is made once in a run, whether it worked or not
        self._failures: dict[int, Failed] = {}  # the failures that have a note already, by id

    @property
    def specs(self) -> tuple[FunctionTool, ...]:
        """The function tools that the agent is defined with."""
        return SPECS

    def table_names(self, handle: str) -> dict[str, str]:
        """What the table handles of one resource stand for in this run (t1 is the name of a table that the platform did not make): for the page of a person, never for an agent."""
        space = self._spaces.get(handle)
        return space.tables.handled() if space is not None else {}

    def call(self, name: str, arguments: dict) -> str:
        """Runs one tool. It never raises: a tool that fails answers {"error": "<a word from a fixed list>"}.

        The reads of the subscriptions in one call take at most `read_seconds` in all. A call that has used that reads no further subscription (what it has read stays in the
        caches, so a later call goes on from there), and its answer says how many were not read (`not_read`) while a note says which."""
        with self._lock:
            self._calls += 1
            self._began, self._timed, self._skipped = self.monotonic(), True, {}
            try:
                answer = self._answer(name, arguments)
            finally:
                self._timed = False
            if self._skipped:
                self.notes.append(f"{_logged_name(name)}: the time for reading the subscriptions ({self.read_seconds:g} seconds in one call) was used up, so "
                                  f"{len(self._skipped)} were not read in this call ({some(list(self._skipped))})")
            try:
                text = _dump(answer)
            except (TypeError, ValueError):  # a value that JSON cannot hold, such as a number that is not finite
                self.notes.append(f"{_logged_name(name)}: the answer could not be written")
                answer = {"error": "failed"}
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
        except NotOffered:
            return {"error": "not-offered"}
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

    def _say(self, text: str) -> None:
        """A note about a subscription that could not be read. The first SUBSCRIPTION_NOTES of a run are kept and the others are counted in one note, so that an estate with many
        subscriptions does not write a line for each."""
        with self._notes_lock:
            self._noted += 1
            if self._noted <= SUBSCRIPTION_NOTES:
                self.notes.append(text)
            elif self._noted == SUBSCRIPTION_NOTES + 1:
                self.notes.append(f"more subscriptions could not be read, and the notes about them are not repeated after the first {SUBSCRIPTION_NOTES}")

    def _note(self, sub: str, what: str, error: Exception) -> None:
        self._say(f"{sub[:8]}: {what} could not be read ({str(error)[:200]})")

    def _late(self) -> bool:
        """True when the call that is running has used the time that its reads of the subscriptions may take (read_seconds)."""
        return self._timed and self.monotonic() - self._began >= self.read_seconds

    def _skip(self, sub: str) -> None:
        self._skipped[sub] = None

    def _labels(self, subs: Iterable[str]) -> list[str]:
        return [self._label(sub) for sub in subs]

    def _listing(self, said: dict, key: str, subs: list[str]) -> None:
        """Puts a list of subscriptions in an answer by label: all of them when there are few, and else the first few and the count under `<key>_count`."""
        said[key] = self._labels(subs[:NOT_READ_SHOWN])
        if len(subs) > NOT_READ_SHOWN:
            said[f"{key}_count"] = len(subs)

    def _unread(self) -> dict:
        """What an answer says of the subscriptions that this call did not read because its time was used up: how many and which first, and what to do."""
        if not self._skipped:
            return {}
        subs = list(self._skipped)
        return {"not_read": {"count": len(subs), "first": self._labels(subs[:NOT_READ_SHOWN]),
                             "why": "the time of one call for reading subscriptions was used up; call again to go on with them"}}

    def _today(self) -> dt.date:
        moment = self.now if self.now.tzinfo else self.now.replace(tzinfo=dt.timezone.utc)
        return moment.astimezone(dt.timezone.utc).date()

    def _each(self, read: Callable[[str], T], what: str, ready: Callable[[str], bool] = lambda sub: False) -> tuple[list[tuple[str, T]], list[str]]:
        """Runs a read in every subscription, `read_workers` of them at a time. A subscription that cannot be read is a note and is returned in the second list; when none can be read, the
        error is raised. The results are in the order of the subscriptions, whichever read ended first.

        A subscription that the call has no time left for is not read, unless `ready` says that its read is in a cache already: it is in `_skipped` and in neither list."""
        outcomes = self._pool([sub for sub in self.subscriptions if not ready(sub)], read)
        done: list[tuple[str, T]] = []
        failed: list[str] = []
        last: Exception | None = None
        for sub in self.subscriptions:
            if ready(sub):
                try:
                    done.append((sub, read(sub)))
                except READ_ERRORS as error:
                    self._note(sub, what, error)
                    failed.append(sub)
                    last = error
            elif sub in outcomes:
                found = outcomes[sub]
                if isinstance(found, Failed):
                    self._note(sub, what, found.error)
                    failed.append(sub)
                    last = found.error
                else:
                    done.append((sub, found))
        if last is not None and not done:
            raise last
        return done, failed

    def _pool(self, subs: list[str], read: Callable[[str], T]) -> "dict[str, T | Failed]":
        """Reads of the subscriptions of the list, `read_workers` at a time, in the order of the list. A read is started only while the time of the call is not used up (the subscriptions
        that are not started are `_skipped`, and the call goes on with the ones that are running). A read that fails with an error of the reads is a `Failed` in its place; any other
        error is raised when all that were started have ended."""
        outcomes: dict[str, "T | Failed"] = {}
        queue = list(subs)
        running: dict[Future, str] = {}
        workers = max(1, self.read_workers)
        pool = ThreadPoolExecutor(max_workers=workers)
        fault: BaseException | None = None
        try:
            while queue or running:
                while queue and len(running) < workers and fault is None and not self._late():
                    sub = queue.pop(0)
                    running[pool.submit(self._guarded, read, sub)] = sub
                if queue and not running:
                    for sub in queue:
                        self._skip(sub)
                    break
                finished, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in finished:
                    sub = running.pop(future)
                    try:
                        outcomes[sub] = future.result()
                    except BaseException as error:  # noqa: BLE001 (it is raised below, once the reads that were started have ended)
                        fault = fault or error
                if fault is not None and not running:
                    break
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        if fault is not None:
            raise fault
        return outcomes

    @staticmethod
    def _guarded(read: Callable[[str], T], sub: str) -> "T | Failed":
        try:
            return read(sub)
        except READ_ERRORS as error:
            return Failed(error)

    def _costs_of(self, sub: str, force: bool = False) -> _Costs | None:
        """The cost lines of a subscription, read once in a run. None when they could not be read or are not in US dollars, and, when the call has no time left to read them
        (the subscription is then in `_skipped`, and nothing is remembered, so a later call reads them), None as well. `force` reads them whatever the time."""
        if sub not in self._costs:
            if not force and self._late():
                self._skip(sub)
                return None
            self._costs[sub] = self._read_costs(sub)
        return self._costs[sub]

    def _prefetch_costs(self, subs: Iterable[str]) -> None:
        """Reads the cost lines of the subscriptions that have none yet, `read_workers` at a time, so that the answer that follows finds them in the cache. What cannot be started in the
        time of the call is `_skipped` and read by a later call."""
        todo = [sub for sub in dict.fromkeys(subs) if sub not in self._costs]
        for sub, outcome in self._pool(todo, self._read_costs).items():
            self._costs[sub] = None if isinstance(outcome, Failed) else outcome

    def _read_costs(self, sub: str) -> _Costs | None:
        today = self._today()
        try:
            lines = self.arm.cost_lines(sub, today - dt.timedelta(days=MAX_DAYS), today - dt.timedelta(days=1))
        except READ_ERRORS as error:
            self._note(sub, "the cost lines", error)
            return None
        if any(line.currency != "USD" for line in lines):
            self._say(f"{sub[:8]}: the cost lines are not in US dollars, so no tool shows a cost for it")
            return None
        return _Costs.of(lines)

    def _cost_total(self, entry: _Entry) -> float | None:
        if entry.part_of is not None:
            return None  # a part of a resource is billed with the resource, and no cost line is its own
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
        entry = _Entry(resource, sub, _shown(sku_word, sku.get("name")), _shown(sku_word, row.get("kindName")), _shown(region_word, resource.location.lower()), properties,
                       float(max(numbers, default=0)))
        self._entries[key] = entry
        return entry

    def _facts(self, entry: _Entry, shown: int) -> dict:
        """What describe says about one resource, except its handle."""
        facts: dict = {}
        costs = None if entry.part_of is not None else self._costs_of(entry.sub)
        if costs is not None:
            lines = costs.by_resource.get(entry.key, {})
            facts["cost30d"] = _money(sum(lines.values()))
            facts["cost_by_service"] = {name: _money(amount) for name, amount in sorted(lines.items(), key=lambda item: (-item[1], item[0]))[:TOP_COST_SERVICES]}
        if entry.part_of is not None and entry.part_of in self._entries:
            facts["part_of"] = self._entries[entry.part_of].resource.handle or None
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
        cells.update((name, value) for name, value in entry.properties if name not in FIXED_FIELDS)
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

    def _caveats(self, failed: list[str], subs: Iterable[str] | None = None) -> dict:
        """The parts of an answer that say what could not be read: the subscriptions without costs (the ones that the answer is about: `subs`, every subscription when it is not given), the ones
        whose resources could not be read, and the ones that this call had no time to read (their costs, which a later call reads, are not counted as unavailable). A list of subscriptions
        names the first few and counts the rest."""
        said: dict = {}
        about = list(self.subscriptions) if subs is None else [sub for sub in self.subscriptions if sub in set(subs)]
        blind = [sub for sub in about if self._costs_of(sub) is None and sub not in self._skipped]
        if blind:
            said["costs"] = "unavailable"
            if len(blind) < len(about):
                self._listing(said, "costs_unavailable", blind)
        if failed:
            self._listing(said, "unavailable", failed)
        said.update(self._unread())
        return said

    def _sub_of(self, key: str) -> str | None:
        parts = key.split("/")
        return next((sub for sub in self.subscriptions if len(parts) > 2 and sub.lower() == parts[2]), None)

    def _owner_of(self, row: dict, fallback: str | None = None) -> str | None:
        """The subscription of the list that a row of Resource Graph belongs to: the one that the row names (subscriptionId, or the id in the id of the resource), or the only one that was asked."""
        for value in (row.get("subscriptionId"), str(row.get("id") or "").split("/")[2] if str(row.get("id") or "").lower().startswith("/subscriptions/") else None):
            sub = next((item for item in self.subscriptions if isinstance(value, str) and item.lower() == value.strip().lower()), None)
            if sub is not None:
                return sub
        return fallback

    def _resolve(self, resource_ids: list[str]) -> None:
        """Reads the resources that no read has returned yet, so that an id from a cost line or from Advisor can have a handle. An id that Resource Graph does
        not return is remembered as missing. The ids of several subscriptions are read together: one query for each RESOLVE_CHUNK of them."""
        wanted: list[tuple[str, str]] = []
        for resource_id in dict.fromkeys(resource_ids):
            key = resource_id.lower()
            sub = self._sub_of(key)
            if sub and key not in self._entries and key not in self._missing and SCOPE_ID.fullmatch(resource_id) and type_of_id(resource_id):
                wanted.append((sub, resource_id))
        for start in range(0, len(wanted), RESOLVE_CHUNK):
            chunk = wanted[start:start + RESOLVE_CHUNK]
            subs = list(dict.fromkeys(sub for sub, _ in chunk))
            found: set[str] = set()
            for row in self.arm.graph_many(subs, RESOURCES_BY_ID.format(ids=", ".join(f"'{item}'" for _, item in chunk))):
                owner = self._owner_of(row, subs[0] if len(subs) == 1 else None)
                entry = self._ingest(row, owner) if owner else None
                if entry is not None:
                    found.add(entry.key)
            self._missing.update(item.lower() for _, item in chunk if item.lower() not in found)

    def _resolve_quietly(self, resource_ids: list[str]) -> None:
        try:
            self._resolve(resource_ids)
        except READ_ERRORS as error:
            self.notes.append(f"the resources of some ids could not be read ({str(error)[:200]})")

    def _graph(self, query: str) -> tuple[list[dict], list[str]]:
        """The rows of one query of Resource Graph over the subscriptions of the list that no earlier listing of this run gave up on, and the subscriptions that could not be read now.

        Resource Graph is asked once for all of them, and for no subscription that is not on the list: one query costs less of the quota than one for each (Learn, "Guidance for throttled
        requests in Azure Resource Graph"). When it answers an error or a limit (an HTTP status from 400 up: the client has waited for a limit already), the subscriptions are asked one at a time,
        in the order of the list, so that one that is denied or fails does not take the others with it: it is a note and is returned, and the answers that follow name it. A limit that holds for
        the first of them holds for all (the quota is the identity's), so the others are not asked. When none can be read, the error of the first question is raised."""
        subs = [sub for sub in self.subscriptions if sub not in self._unlisted]
        if not subs:
            raise HttpError(0, "no subscription could be listed in this run")
        try:
            return self.arm.graph_many(subs, query), []
        except HttpError as error:
            if len(subs) < 2 or not 400 <= error.status < 600:
                raise
            first = error
        rows: list[dict] = []
        failed: list[str] = []
        for index, sub in enumerate(subs):
            try:
                rows += self.arm.graph_many([sub], query)
            except HttpError as error:
                if not 400 <= error.status < 600:
                    raise
                self._note(sub, "the resources", error)
                failed.append(sub)
                if error.status == 429:
                    failed += subs[index + 1:]
                    self.notes.append("the limit of Resource Graph holds, so the other subscriptions were not asked")
                    break
        if len(failed) == len(subs):
            raise first
        return rows, failed

    def _load_type(self, kind: str) -> None:
        """The resources of one type in every subscription, from one query of Resource Graph for all of them (`_graph`). A subscription that has none has an empty list, and one that could not be
        read has no list: it is in `_unlisted`."""
        if all((sub, kind) in self._by_type or sub in self._unlisted for sub in self.subscriptions):
            return
        rows, failed = self._graph(TYPE_RESOURCES.format(type=kind))
        self._unlisted.update(failed)
        found: dict[str, list[str]] = {sub: [] for sub in self.subscriptions if sub not in self._unlisted}
        for row in rows:
            owner = self._owner_of(row)
            entry = self._ingest(row, owner) if owner in found else None
            if entry is not None and entry.sub == owner and entry.key not in found[owner]:
                found[owner].append(entry.key)
        for sub, keys in found.items():
            self._by_type[(sub, kind)] = keys

    def _entries_of(self, kind: str, subs: Iterable[str] | None = None) -> list[_Entry]:
        return [self._entries[key] for sub in self.subscriptions if subs is None or sub in set(subs) for key in self._by_type.get((sub, kind), [])]

    def _load_counts(self) -> None:
        """The number of resources of each type in every subscription, from one query of Resource Graph for all of them (`_graph`)."""
        if all(sub in self._counts or sub in self._unlisted for sub in self.subscriptions):
            return
        rows, failed = self._graph(TYPE_COUNTS)
        self._unlisted.update(failed)
        found: dict[str, tuple[int, dict[str, int]]] = {sub: (0, {}) for sub in self.subscriptions if sub not in self._unlisted}
        for row in rows:
            owner = self._owner_of(row)
            number = row.get("n")
            if owner not in found or isinstance(number, bool) or not isinstance(number, int) or number < 0:
                continue
            total, counts = found[owner]
            kind = type_word(str(row.get("type") or "").lower())
            found[owner] = (total + number, {**counts, **({kind: counts.get(kind, 0) + number} if kind else {})})
        self._counts.update(found)

    def _entry(self, handle: str) -> _Entry:
        if handle not in self._by_handle:
            raise UnknownHandle(handle)
        return self._by_handle[handle]

    # -- the tools -----------------------------------------------------------------------------------------------------------------------------
    def _tool_estate_overview(self, args: dict) -> dict:
        try:
            self._load_counts()
        except READ_ERRORS as error:
            for sub in self.subscriptions:
                self._note(sub, "the resources", error)
            return {"error": "unavailable"}
        self._prefetch_costs([sub for sub in self.subscriptions if sub not in self._unlisted])
        blocks: list[dict] = []
        for sub in self.subscriptions:
            if sub in self._skipped or sub in self._unlisted:
                continue
            block: dict = {"subscription": self._label(sub)}
            total, counts = self._counts[sub]
            costs = self._costs.get(sub)
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
        said: dict = {}
        if self._unlisted:
            self._listing(said, "unavailable", [sub for sub in self.subscriptions if sub in self._unlisted])  # the subscriptions that Resource Graph could not list: not "none"
        answer = {"window_days": MAX_DAYS, "subscriptions": blocks, **said, **self._unread()}
        if len(blocks) > MAX_BLOCKS:
            # An estate with many subscriptions: the dearest are shown, and the count of the others says that there are more.
            blocks.sort(key=lambda block: (-(block.get("cost30d") or 0.0), len(block["subscription"]), block["subscription"]))
            answer["subscriptions_not_shown"] = len(blocks) - MAX_BLOCKS
            del blocks[MAX_BLOCKS:]
        while len(_dump(answer)) > MAX_RESULT_CHARS:
            lists = [(len(block[key]), key == "types", block, key) for block in blocks for key in ("types", "services") if block.get(key)]
            if not lists:
                if len(blocks) <= 1:
                    raise TooLarge()
                blocks.pop()
                answer["subscriptions_not_shown"] = answer.get("subscriptions_not_shown", 0) + 1
                continue
            _, _, block, key = max(lists, key=lambda item: item[:2])
            block[key].pop()
            block[f"{key}_not_shown"] = block.get(f"{key}_not_shown", 0) + 1
        return answer

    def _listed(self, kind: str, order: str) -> tuple[list[_Entry], list[str]]:
        """The resources of one type in the order of a listing, and the subscriptions whose resources could not be read (`_graph`: one read of Resource Graph covers every subscription, and the
        ones that it could not give are named, never counted as having none). The cost lines of the subscriptions that have such a resource are read at the same time, `read_workers` of them
        at once."""
        self._load_type(kind)
        entries = self._entries_of(kind)
        self._prefetch_costs(sorted({entry.sub for entry in entries}, key=list(self.subscriptions).index))

        def cost(entry: _Entry) -> float:
            total = self._cost_total(entry)
            return 0.0 if total is None else total

        entries.sort(key=(lambda entry: (-entry.size, -cost(entry), entry.key)) if order == "count" else (lambda entry: (-cost(entry), entry.key)))
        return entries, [sub for sub in self.subscriptions if sub in self._unlisted]

    def _tool_list_resources(self, args: dict) -> dict:
        kind, order, limit, offset = args["type"], args["order_by"] or "cost", args["limit"] or DEFAULT_LISTED, args["offset"] or 0
        entries, failed = self._listed(kind, order)
        page = entries[offset:offset + limit]
        page = page[:self._within_handles(page)]
        cells = [self._cells(entry) for entry in page]
        caveats = self._caveats(failed, {entry.sub for entry in entries})

        def table(count: int) -> tuple[dict, list[list], set[str]]:
            same, columns, rows, visible = _layout([(PLACEHOLDER, cell) for cell in cells[:count]])
            more = offset + count < len(entries)
            answer = {"type": kind, "total": len(entries), "offset": offset, "has_more": more, **({"next_offset": offset + count} if more else {}), **caveats,
                      **({"reads": deeper.offered(kind)} if deeper.offered(kind) else {}), **({"same": same} if same else {}), "cols": columns, "rows": rows}
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

    def _one_of_type(self, kind: str) -> tuple[str | None, bool]:
        """The id of one resource of the type, from a list that was read before or else from one read of Resource Graph for every subscription (`_graph`), and whether the search was complete:
        it is not when none was found and a subscription could not be read, so that nothing is remembered about the type and a later call looks again."""
        for sub in self.subscriptions:
            if self._by_type.get((sub, kind)):
                return self._entries[self._by_type[(sub, kind)][0]].resource.resource_id, True
        if kind in self._without or all((sub, kind) in self._by_type for sub in self.subscriptions):
            return None, True
        rows, failed = self._graph(ONE_OF_TYPE.format(type=kind))
        self._unlisted.update(failed)
        for row in rows:
            if str(row.get("id") or "").lower().startswith("/subscriptions/") and self._owner_of(row) is not None:
                return str(row["id"]), True
        if self._unlisted:
            return None, False
        self._without.add(kind)
        return None, True

    def _names_of(self, kind: str) -> list[dict]:
        if kind not in self._metric_names:
            found: dict[str, dict] = {}
            resource_id, complete = self._one_of_type(kind)
            for definition in self.arm.metric_definitions(resource_id) if resource_id else []:
                name = definition.get("name")
                word = metric_word(name.get("value") if isinstance(name, dict) else None)
                # A metric that is only offered for a chosen dimension cannot be measured without one, and metric_summary names none.
                if word is not None and definition.get("isDimensionRequired") is not True:
                    dimensions = [token_word(item.get("value"), 41) for item in definition.get("dimensions") or [] if isinstance(item, dict)]
                    found.setdefault(word, {"name": word, "unit": token_word(definition.get("unit"), 16), "aggregation": token_word(definition.get("primaryAggregationType"), 16),
                                            **({"dimensions": [item for item in dimensions if item][:MAX_DIMENSIONS]} if any(dimensions) else {})})
            if not complete:
                return []  # no resource was found in the subscriptions that were looked at, and the others were not: nothing is remembered, a later call looks again
            self._metric_names[kind] = sorted(found.values(), key=lambda item: item["name"].lower())
        return self._metric_names[kind]

    def _offered(self, kinds: "set[str | None]", metric: str) -> "dict[str | None, bool | None]":
        """For each resource type, whether Azure Monitor offers the metric for it (the metric_names of the type): True or False, or None when it could not be read.
        A metric that the tools did not list is never measured, so no text of an argument or of an answer reaches Azure Monitor or the agent through it."""
        verdict: "dict[str | None, bool | None]" = {}
        for kind in kinds:
            if kind is None:
                verdict[kind] = False
                continue
            try:
                verdict[kind] = any(item["name"] == metric for item in self._names_of(kind))
            except READ_ERRORS as error:
                self.notes.append(f"the metrics that Azure Monitor offers for a type could not be read ({str(error)[:200]})")
                verdict[kind] = None
        return verdict

    def _tool_metric_names(self, args: dict) -> dict:
        kind, offset = args["type"], args["offset"] or 0
        names = self._names_of(kind)
        rows = [dict(item) for item in names[offset:]]
        answer: dict = {"type": kind, "total": len(names), "offset": offset, "returned": 0, "next_offset": None, **self._unread(), "metrics": rows}
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
        """Keeps the numbers that an answer carried for one resource, as the investigation checks the claims of the agent against them: those of the last measurement,
        and in `totals` the total of every measurement that an answer carried (the last MAX_TOTALS of them, the oldest first)."""
        metrics = self.evidence.setdefault(handle, {}).setdefault("metrics", {})
        seen = metrics.get(metric, {}).get("totals", [])
        metrics[metric] = {"total": summary["total"], "max": summary["max"], "average": summary["average"], "days_with_data": summary["days_with_data"], "days": days,
                           "unit": unit, "totals": [*seen, summary["total"]][-MAX_TOTALS:]}

    def _count_read(self, kind: str | None, handle: str, metric: str, days: int, summary: dict) -> None:
        """Remembers how the measurement that an answer showed for a resource counts (see _bucket), so that the summary of another page of the same type covers it too.
        A resource is counted once for a type, a metric and a window: a later measurement of it replaces the earlier."""
        if kind is not None:
            self._reads.setdefault((kind, metric, days), {})[handle] = _bucket(summary)

    def _tool_metric_summary(self, args: dict) -> dict:
        handles, metric, days = args["handles"], args["metric"], args["days"] or MAX_DAYS
        start, end = self._window(days)
        known = [handle for handle in handles if handle in self.handles]
        kinds = {handle: type_word(self.handles[handle].resource_type) for handle in known}
        offered = self._offered(set(kinds.values()), metric)
        if known and not any(offered.values()) and None not in offered.values():
            return {"error": "unknown-metric"}
        read, unread = self._read_metrics([(handle, self.handles[handle].resource_id) for handle in known if offered[kinds[handle]]], metric, start, end)
        skipped, rows, units = set(unread), [], {}
        for handle in handles:
            outcome = read.get(handle)
            if handle not in self.handles:
                rows.append({"handle": handle, "error": "unknown-handle"})
            elif offered[kinds[handle]] is False:
                rows.append({"handle": handle, "error": "unknown-metric"})
            elif offered[kinds[handle]] is None:
                rows.append({"handle": handle, "error": "unavailable"})
            elif isinstance(outcome, str):
                rows.append({"handle": handle, "error": outcome})
            elif outcome is not None:
                units[handle] = token_word(outcome[0], 16)
                rows.append({"handle": handle, **_summarise(outcome[1])})
        answer: dict = {"days": days, "unit": None, "partial": False, "summary": {}, "results": rows}
        if any(offered.values()):
            answer = {"metric": metric, **answer}  # the name is echoed only when Azure Monitor offers it for a type of a handle

        def refresh() -> None:
            answer["unit"] = next((units[row["handle"]] for row in rows if units.get(row["handle"])), None)
            answer["partial"] = bool(skipped)
            answer["summary"] = _tally((_bucket(row) for row in rows if "error" not in row), days)  # the resources whose numbers are in the answer
            if skipped:
                answer["unread"] = [handle for handle in handles if handle in skipped]

        refresh()
        while len(_dump(answer)) > MAX_RESULT_CHARS and rows:
            skipped.add(rows.pop()["handle"])
            refresh()
        for row in rows:
            if "error" not in row:
                self._record_metric(row["handle"], metric, row, days, units.get(row["handle"]))
                self._count_read(kinds[row["handle"]], row["handle"], metric, days, row)
        return answer

    def _tool_measure(self, args: dict) -> dict:
        kind, metric, days, limit, offset = args["type"], args["metric"], args["days"] or MAX_DAYS, args["limit"] or DEFAULT_LISTED, args["offset"] or 0
        entries, failed = self._listed(kind, "cost")
        page = entries[offset:offset + limit]
        vetted = bool(page)  # the name of the metric is echoed only when Azure Monitor offers it for the type, and that is read only when there is a resource to measure
        if vetted and not any(item["name"] == metric for item in self._names_of(kind)):
            return {"error": "unknown-metric"}
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
                summaries[handle] = (_summarise(outcome[1]), token_word(outcome[0], 16))
        skipped = set(unread)
        columns = ["handle", *(["usd30d"] if priced else []), "total", "max", "avg", "days_with_data"]
        caveats = self._caveats(failed, {entry.sub for entry in entries})
        more = offset + len(page) < len(entries)
        counted = dict(self._reads.get((kind, metric, days), {}))  # what the pages and the calls before this one showed

        def row_of(handle: str) -> list:
            summary = summaries[handle][0]
            cost = costs[handle]
            return [handle, *([None if cost is None else _cents(cost)] if priced else []), summary["total"], summary["max"], summary["average"], summary["days_with_data"]]

        def answer() -> dict:
            kept = [handle for handle in handles if handle in summaries and handle not in skipped]
            unit = next((summaries[handle][1] for handle in kept if summaries[handle][1]), None)
            seen = {**counted, **{handle: _bucket(summaries[handle][0]) for handle in kept}}
            return {"type": kind, **({"metric": metric} if vetted else {}), "days": days, **({"unit": unit} if unit else {}), "partial": bool(skipped), "total": len(entries),
                    "offset": offset, "has_more": more, **({"next_offset": offset + len(page)} if more else {}), **caveats, **({"failed": broken} if broken else {}),
                    **({"unread": [handle for handle in handles if handle in skipped]} if skipped else {}), "summary": _tally(seen.values(), days), "cols": columns,
                    "rows": [row_of(handle) for handle in kept]}

        built = answer()
        while len(_dump(built)) > MAX_RESULT_CHARS and any(handle in summaries and handle not in skipped for handle in handles):
            skipped.add(next(handle for handle in reversed(handles) if handle in summaries and handle not in skipped))
            built = answer()
        for handle, entry in zip(handles, page):
            if handle in summaries and handle not in skipped:
                if costs[handle] is not None:
                    self._show(entry, {"cost30d": _cents(costs[handle])})
                self._record_metric(handle, metric, summaries[handle][0], days, summaries[handle][1])
                self._count_read(kind, handle, metric, days, summaries[handle][0])
        return built

    def _tool_cost_lines(self, args: dict) -> dict:
        service, kind, limit = args["service"], args["type"], args["limit"] or DEFAULT_LINES
        lines: list[tuple[float, str, str | None, str]] = []
        blind = 0
        self._prefetch_costs(self.subscriptions)
        for sub in self.subscriptions:
            costs = self._costs_of(sub)
            if costs is None:
                if sub not in self._skipped:
                    blind += 1
                continue
            for key, per_service in costs.by_resource.items():
                found = type_of_id(key)
                if kind and found != kind:
                    continue
                lines += [(amount, name, found, key) for name, amount in per_service.items() if not service or name.lower() == service.lower()]
        if self.subscriptions and blind + len(self._skipped) == len(self.subscriptions):
            return {"costs": "unavailable", "lines": [], **self._unread()}
        lines.sort(key=lambda line: (-line[0], line[3], line[1]))
        page = lines[:limit]
        self._resolve_quietly([key for _, _, _, key in page])
        entries = [self._entries.get(key) for _, _, _, key in page]
        rows = [{"handle": PLACEHOLDER if entry else None, "usd": _money(amount), "service": name, "type": found} for (amount, name, found, _), entry in zip(page, entries)]
        answer: dict = {"service": service, "type": kind, "total": len(lines), "usd_total": _money(sum(line[0] for line in lines)), "returned": 0, "lines": rows}
        if blind:
            answer["costs"] = "unavailable"
        answer.update(self._unread())
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
        done, failed = self._each(self._advice_for, "the cost recommendations", ready=lambda sub: sub in self._advice)
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
            self._listing(answer, "unavailable", failed)
        answer.update(self._unread())
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

    def _pricings_for(self, sub: str) -> list[dict]:
        if sub not in self._pricings:
            self._pricings[sub] = self.arm.security_pricings(sub)
        return self._pricings[sub]

    def _tool_paid_features(self, args: dict) -> dict:
        done, _ = self._each(self._pricings_for, "the paid features", ready=lambda sub: sub in self._pricings)
        found = dict(done)
        blocks: list[dict] = []
        for sub in self.subscriptions:
            if sub in self._skipped:
                continue
            block: dict = {"subscription": self._label(sub)}
            if sub not in found:
                block["error"] = "unavailable"
            else:
                plans = []
                for item in found[sub]:
                    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
                    plan = token_word(item.get("name"), 32)
                    if plan is not None:
                        plans.append({"plan": plan, "tier": token_word(properties.get("pricingTier"), 16), "sub_plan": token_word(properties.get("subPlan"), 24),
                                      "coverage": token_word(properties.get("resourcesCoverageStatus"), 24)})
                block["plans"] = sorted(plans, key=lambda plan: plan["plan"].lower())
            blocks.append(block)
        answer = {"subscriptions": blocks, **self._unread()}
        if len(blocks) > MAX_BLOCKS:
            # An estate with many subscriptions: those with the most plans that are not free are shown, and the count of the others says that there are more.
            blocks.sort(key=lambda block: (-sum(1 for plan in block.get("plans", []) if plan["tier"] not in (None, "Free")), len(block["subscription"]), block["subscription"]))
            answer["subscriptions_not_shown"] = len(blocks) - MAX_BLOCKS
            del blocks[MAX_BLOCKS:]
        while len(_dump(answer)) > MAX_RESULT_CHARS:
            longest = max((block for block in blocks if block.get("plans")), key=lambda block: len(block["plans"]), default=None)
            if longest is None:
                if len(blocks) <= 1:
                    raise TooLarge()
                blocks.pop()
                answer["subscriptions_not_shown"] = answer.get("subscriptions_not_shown", 0) + 1
                continue
            longest["plans"].pop()
            longest["plans_not_shown"] = longest.get("plans_not_shown", 0) + 1
        return answer

    def _tool_describe(self, args: dict) -> dict:
        entry = self._entry(args["handle"])
        facts = self._facts(entry, DESCRIBED_PROPERTIES)
        kind = type_word(entry.resource.resource_type)
        answer = {"handle": args["handle"], "type": kind, **({"reads": deeper.offered(kind)} if deeper.offered(kind) else {}), **facts}
        while len(_dump(answer)) > MAX_RESULT_CHARS and answer["properties"]:
            answer["properties"].popitem()
        self._show(entry, facts)
        return answer

    # -- the deeper reads: what a resource records about the data written to it, who reads and writes it, the parts inside it, a metric by dimension, commitments, cost by day ------------------
    def _offered_entry(self, handle: str, tool: str) -> _Entry:
        entry = self._entry(handle)
        if tool not in deeper.offered(type_word(entry.resource.resource_type)):
            raise NotOffered(handle)
        return entry

    @staticmethod
    def _guard(read: "Callable[[], T]") -> "T | Failed":
        try:
            return read()
        except READ_ERRORS as error:
            return Failed(error)

    def _together(self, reads: "list[Callable[[], T]]") -> "list[T | Failed]":
        """Runs the reads at the same time, at most `workers` of them, and gives each one's result in its place, or a Failed for a read that ended in an error of the reads."""
        if len(reads) == 1:
            return [self._guard(reads[0])]
        pool = ThreadPoolExecutor(max_workers=max(1, min(self.workers, len(reads))))
        try:
            return [future.result() for future in [pool.submit(self._guard, read) for read in reads]]
        finally:
            pool.shutdown(wait=True)

    def _fail(self, tool: str, what: str, failed: Failed) -> str:
        """The note for a read that failed (written once for each failure), and the word that the answer says for it: a refusal of the platform (401, 403) is NOT_VISIBLE, and anything
        else is `unavailable`."""
        if id(failed) not in self._failures:
            self._failures[id(failed)] = failed  # kept, so that the id stays this failure's
            self.notes.append(f"{tool}: {what} could not be read ({str(failed.error)[:200]})")
        return NOT_VISIBLE if getattr(failed.error, "status", None) in (401, 403) else "unavailable"

    def _space(self, entry: _Entry, tool: str) -> _Space:
        """The settings and the tables of a resource that keeps records of the data written to it, read once in a run (the two reads are made at the same time). When neither can be read the
        error is raised."""
        handle, resource_id = entry.resource.handle, entry.resource.resource_id
        if handle not in self._spaces:
            settings, tables = self._together([lambda: self.arm.workspace(resource_id), lambda: self.arm.workspace_tables(resource_id)])
            if isinstance(settings, Failed) and isinstance(tables, Failed):
                raise settings.error
            found = _Space({}, None, deeper.TableBook({}), "read", "read")
            if isinstance(settings, Failed):
                found.settings = self._fail(tool, "the settings", settings)
            else:
                found.pricing, found.customer = deeper.pricing(settings), deeper.customer_id(settings)
            if isinstance(tables, Failed):
                found.listing = self._fail(tool, "the list of tables", tables)
            else:
                found.tables = deeper.TableBook(deeper.table_index(tables))
            self._spaces[handle] = found
        return self._spaces[handle]

    def _moment(self) -> dt.datetime:
        return self.now if self.now.tzinfo else self.now.replace(tzinfo=dt.timezone.utc)

    def _records(self, space: _Space, tool: str, text: str, start: dt.datetime, end: dt.datetime) -> "tuple[list[dict] | None, str]":
        """The rows of one read of the resource's own records over the time from start to end, or None and the word that says why there are none."""
        if space.customer is None:
            return None, (space.settings if space.settings != "read" else "unavailable")
        try:
            return self.arm.log_query(space.customer, text, start, end, timeout=QUERY_SECONDS), "read"
        except READ_ERRORS as error:
            return None, self._fail(tool, "the records", Failed(error))

    @staticmethod
    def _gb(mb: float) -> "int | float":
        return deeper.number(round(mb / 1000, 3))

    def _volume(self, entry: _Entry, space: _Space, days: int) -> "tuple[list[deeper.TableUse], float, str]":
        """The tables of a resource by the volume that is charged for over the last `days` closed days, the volume of all of them in MB, and the word that says whether it was read.
        The read is made once for a handle and a window, and a read that failed is not made again in the run."""
        key = (entry.resource.handle, days)
        if key not in self._volumes:
            first, _ = self._window(days)
            # The records of an hour are made after the hour ends, so the read starts two days before the window and ends now: the query itself keeps to the closed days.
            rows, word = self._records(space, "data_volume", deeper.usage_query(days), first - dt.timedelta(days=2), self._moment())
            if rows is None:
                self._volumes[key] = ([], 0.0, word)
            else:
                ranked, total = deeper.volume_rows(deeper.usage_by_table(rows, first.date(), days), days)
                self._volumes[key] = (ranked, total, "read")
        return self._volumes[key]

    @staticmethod
    def _fit(answer: dict, lists: "list[tuple[list, dict, str]]") -> None:
        """Takes rows off the longest of the lists of an answer until it fits under the cap, and counts what it left out under `<key>_not_shown` in the dict that holds the list."""
        while len(_dump(answer)) > MAX_RESULT_CHARS:
            longest = max(((rows, holder, key) for rows, holder, key in lists if rows), key=lambda item: len(item[0]), default=None)
            if longest is None:
                raise TooLarge()
            rows, holder, key = longest
            rows.pop()
            holder[f"{key}_not_shown"] = holder.get(f"{key}_not_shown", 0) + 1

    def _tool_data_volume(self, args: dict) -> dict:
        entry = self._offered_entry(args["handle"], "data_volume")
        handle, days, offset = args["handle"], args["days"] or MAX_DAYS, args["offset"] or 0
        space = self._space(entry, "data_volume")
        ranked, total, word = self._volume(entry, space, days)
        answer: dict = {"handle": handle, "days": days, "settings": space.settings, "tables_listed": space.listing, **({"pricing": space.pricing} if space.pricing else {}), "volume": word}
        if word != "read":
            return answer
        self.evidence.setdefault(handle, {})["volume"] = {"billable_gb": self._gb(total), "days": days, "tables": len(ranked)}  # the whole volume, of which the first tables are kept below
        free = sum(use.free_mb for use in ranked)
        extra = free > 0
        shown = ranked[offset:]
        rows: list[list] = []
        for use in shown:
            info = space.tables.index.get(use.name, {})
            row = [space.tables.label(use.name), info.get("plan"), info.get("retention"), info.get("total_retention"), self._gb(use.billable_mb),
                   deeper.number(round(use.billable_mb / total, 3)) if total > 0 else 0, sum(1 for mb in use.daily.values() if mb > 0), deeper.trend(use, days)]
            rows.append([*row, self._gb(use.free_mb)] if extra else row)
        answer.update({"billable_gb": self._gb(total), **({"free_gb": self._gb(free)} if extra else {}), "tables_with_data": len(ranked), "tables_in_workspace": len(space.tables.index),
                       "cols": ["table", "plan", "retention_days", "total_retention_days", "gb", "share", "days", "trend", *(["free_gb"] if extra else [])], "rows": rows})
        _page(answer, rows, offset, len(ranked))
        for place, (use, row) in enumerate(zip(shown, rows), start=offset):
            if place >= deeper.MAX_TABLES:
                break
            daily = [mb / 1000 for mb in use.daily.values() if mb > 0]
            self._record_metric(handle, f"Billable GB {row[0]}", {"total": row[4], "max": deeper.number(round(max(daily), 3)) if daily else None,
                                                                "average": deeper.number(round(math.fsum(daily) / len(daily), 3)) if daily else None, "days_with_data": row[6]}, days, "GB")
        return answer

    def _readers(self, entry: _Entry, space: _Space, records: str) -> dict:
        """What reads the tables of a workspace, read once in a run: how many of the items of each source name each table, and how many of them read every table at once. The sources are read at
        the same time. The texts of the items are counted by code and leave it as numbers. `records` says whether the records of the workspace could be read (the volume's word): when they
        could not, the record of the runs is not asked for, and says the same."""
        key = ("readers", entry.resource.handle)
        if key in self._kept:
            return self._kept[key]  # type: ignore[return-value]
        workspace_id, sub, known = entry.resource.resource_id, entry.sub, space.tables.known() if space.listing == "read" else set()

        def rules() -> tuple[list[list[str]], int]:
            found = deeper.scheduled_rules(self.arm.graph_many(list(self.subscriptions), deeper.rules_query(workspace_id)), workspace_id)
            return [texts for enabled, texts in found if enabled], sum(1 for enabled, _ in found if not enabled)

        def audit() -> tuple[list[dict], list[dict]]:
            if space.customer is None or records != "read":
                raise HttpError(0, "the records of the workspace could not be read")
            start = self._window(MAX_DAYS)[0]
            return (self.arm.log_query(space.customer, deeper.LOG_AUDIT_TOTALS, start, self._moment(), timeout=QUERY_SECONDS),
                    self.arm.log_query(space.customer, deeper.LOG_AUDIT_TEXTS, start, self._moment(), timeout=QUERY_SECONDS))

        done = self._together([rules, lambda: deeper.query_texts(self.arm.saved_searches(workspace_id)), lambda: deeper.workbook_texts(self.arm.workbooks(sub), workspace_id),
                               lambda: deeper.query_texts(self.arm.sentinel_rules(workspace_id), ("Scheduled", "NRT")), audit])
        sources: dict[str, object] = {}
        groups: dict[str, list[list[str]]] = {}
        disabled = 0
        for name, outcome in zip(READER_SOURCES, done):
            if isinstance(outcome, Failed):
                onboarded = name == "analytics_rules" and getattr(outcome.error, "status", None) == 400 and "onboard" in str(outcome.error).lower()
                sources[name] = "not enabled" if onboarded else self._fail("data_readers", f"the {name.replace('_', ' ')}", outcome)
            elif name == "rules":
                groups[name], disabled = outcome  # type: ignore[misc]
            else:
                groups[name] = outcome  # type: ignore[assignment]
        mentions, scanning = deeper.mention_counts(groups, known)
        for name, items in groups.items():
            sources[name] = {"read": len(items), **({"disabled": disabled} if name == "rules" and disabled else {}), "scanning_all": scanning[name]}
        runs: dict[str, int] | None = None
        cut = False  # the read of the texts came back as full as it may be, so a table that none of them names is not known to be read by nothing
        log = done[len(READER_SOURCES)]
        if isinstance(log, Failed):
            if records != "read":
                sources["query_log"] = records
            else:
                sources["query_log"] = "not recorded" if getattr(log.error, "status", None) == 400 else self._fail("data_readers", "the record of the runs", log)
        else:
            totals, texts = log  # type: ignore[misc]
            first = totals[0] if totals else {}
            cut = deeper.audit_cut(texts)
            sources["query_log"] = {"runs": deeper.count(first.get("Runs")) or 0, "callers": deeper.count(first.get("Callers")) or 0, "texts_read": len(texts), **({"texts_cut": True} if cut else {})}
            runs = deeper.audit_counts(texts, known)
        self._kept[key] = {"sources": sources, "mentions": mentions, "runs": runs, "runs_cut": cut}
        return self._kept[key]  # type: ignore[return-value]

    def _tool_data_readers(self, args: dict) -> dict:
        entry = self._offered_entry(args["handle"], "data_readers")
        handle, limit, offset = args["handle"], args["limit"] or DEFAULT_TABLES, args["offset"] or 0
        space = self._space(entry, "data_readers")
        ranked, _, word = self._volume(entry, space, MAX_DAYS)
        answer: dict = {"handle": handle, "days": MAX_DAYS, "tables_listed": space.listing, "volume": word}
        if space.listing != "read":
            return answer  # without the list of its tables nothing can be counted by table, and a count of 0 would say what was not read
        found = self._readers(entry, space, word)
        sources = found["sources"]
        answer["sources"] = sources
        if word != "read":
            return answer
        counted = {name: sources[name] if isinstance(sources[name], dict) else 0 if sources[name] == "not enabled" else None for name in READER_SOURCES}
        runs = found["runs"]
        rows = [[space.tables.label(use.name), *[None if counted[name] is None else found["mentions"].get(use.name, {}).get(name, 0) for name in READER_SOURCES],
                 None if runs is None or (found["runs_cut"] and use.name not in runs) else runs.get(use.name, 0)] for use in ranked[offset:offset + limit]]  # null: not known to be none
        answer.update({"tables_with_data": len(ranked), "cols": ["table", *READER_SOURCES, "runs"], "rows": rows})
        _page(answer, rows, offset, len(ranked))
        broad = sum(source.get("scanning_all", 0) for source in sources.values() if isinstance(source, dict))  # the items that read every table at once
        for place, row in enumerate(rows, start=offset):
            if place >= deeper.MAX_TABLES:
                break
            named = row[1:1 + len(READER_SOURCES)]
            complete = None not in named  # the number is the items that name the table and those that read every table, and only when every source was read
            self._record_metric(handle, f"Readers {row[0]}", {"total": sum(named) + broad if complete else None, "max": None, "average": None, "days_with_data": 1 if complete else 0},
                                MAX_DAYS, None)
            if row[-1] is not None:
                self._record_metric(handle, f"Runs {row[0]}", {"total": row[-1], "max": None, "average": None, "days_with_data": 1}, MAX_DAYS, None)
        return answer

    def _once(self, key: tuple, read: "Callable[[], T]") -> "T | Failed":
        """The result of one read of the deeper tools, made once in a run: a read that failed gives the same Failed again, and its note is written once."""
        if key not in self._kept:
            self._kept[key] = self._guard(read)
        return self._kept[key]  # type: ignore[return-value]

    def _access(self, sub: str, what: str, outcome: "T | Failed") -> "T | str":
        """The value of a read, or the word that says why there is none: NOT_VISIBLE when the platform refused the access of the run, `unavailable` for any other failure."""
        if not isinstance(outcome, Failed):
            return outcome
        self._note(sub, what, outcome.error)
        return NOT_VISIBLE if getattr(outcome.error, "status", None) in (401, 403) else "unavailable"

    @staticmethod
    def _tables_named(space: _Space, names: Iterable[str]) -> list[str]:
        """Tables as the agent names them: the ones that the workspace lists, and `other` for a name that it does not list."""
        return sorted({space.tables.label(name) if name in space.tables.index else OTHER for name in names})[:8]

    def _collection_rules(self, entry: _Entry) -> "list[tuple[_Entry, dict]]":
        found: list[tuple[_Entry, dict]] = []
        for row in self.arm.graph_many(list(self.subscriptions), deeper.collection_rules_query(entry.resource.resource_id)):
            facts = deeper.collection_rule(row, entry.resource.resource_id)
            owner = self._owner_of(row)
            rule = self._ingest(row, owner) if facts is not None and owner else None
            if rule is not None:
                found.append((rule, facts))  # type: ignore[arg-type]
        found.sort(key=lambda item: (-item[1]["flows"], -sum(item[1]["sources"].values()), item[0].key))
        return found

    def _table_sources(self, space: _Space, name: str) -> "tuple[list[tuple[str, float]], float | None, str]":
        """The resources that wrote the most billable data to one table on the last closed day, as ids and MB, the MB that the table took in that day, and the word that says
        whether it was read. The resources of the ids are read, so that they can have handles."""
        start, end = self._window(1)
        rows, word = self._records(space, "data_writers", deeper.sources_query(name, MAX_SOURCES), start, end)
        if rows is None:
            return [], None, word
        found, whole = deeper.sources(rows)
        self._resolve_quietly([resource for resource, _ in found])
        return found, whole, "read"

    def _writers_to(self, entry: _Entry, table: str | None) -> dict:
        handle = entry.resource.handle
        space = self._space(entry, "data_writers")
        answer: dict = {"handle": handle, "tables_listed": space.listing}
        lists: list[tuple[list, dict, str]] = []
        named: list[tuple[list, list[tuple[list, _Entry | None]]]] = []  # a list of rows, and each of its rows with the entry that it stands for
        rules = self._once(("collection-rules", handle), lambda: self._collection_rules(entry))
        if isinstance(rules, Failed):
            answer["collection_rules"] = self._fail("data_writers", "the collection rules", rules)
        else:
            rows = [[PLACEHOLDER, facts["kind"], facts["sources"], facts["flows"], facts["transforms"], self._tables_named(space, facts["tables"])] for _, facts in rules[:MAX_RULES]]
            answer["collection_rules"] = {"total": len(rules), "cols": ["handle", "kind", "sources", "flows", "transforms", "tables"], "rows": rows}
            lists.append((rows, answer["collection_rules"], "rows"))
            named.append((rows, [(row, rule) for row, (rule, _) in zip(rows, rules)]))
        if table is not None:
            name = space.tables.name_of(table)
            if name is None:
                raise BadArguments("table")
            plan = space.tables.index.get(name, {}).get("plan")
            block: dict = {"table": space.tables.label(name), "plan": plan}
            answer["table"] = block
            if plan != "Analytics" or not deeper.queryable(name):
                block["writers"] = "not read for this plan"  # a read of any other plan is charged by the volume that it scans
            else:
                found = self._once(("sources", handle, name), lambda: self._table_sources(space, name))
                if isinstance(found, Failed):
                    block["writers"] = self._fail("data_writers", "the writers of the table", found)
                elif found[2] != "read":
                    block["writers"] = found[2]
                else:
                    sources, whole, _ = found
                    rows = []
                    owners = []
                    for resource_id, mb in sources[:MAX_SOURCES]:
                        owner = self._entries.get(resource_id)
                        rows.append([PLACEHOLDER if owner else None, type_of_id(resource_id), self._gb(mb), deeper.number(round(mb / whole, 3)) if whole else None])
                        owners.append((rows[-1], owner))
                    shares = [row[3] for row in rows if row[3] is not None]
                    block["writers"] = {"day": self._window(1)[0].date().isoformat(), **({"billable_gb": self._gb(whole)} if whole is not None else {}),
                                        **({"other_share": deeper.number(round(max(0.0, 1 - math.fsum(shares)), 3))} if whole and len(shares) == len(rows) else {}),
                                        "cols": ["handle", "type", "gb", "share"], "rows": rows}
                    lists.append((rows, block["writers"], "rows"))
                    named.append((rows, owners))
        self._fit(answer, lists)
        if table is not None and isinstance(block.get("writers"), dict):
            kinds = list(dict.fromkeys(row[1] for row in block["writers"]["rows"] if row[1]))[:MAX_WRITER_KINDS]
            self.evidence.setdefault(handle, {}).setdefault("writers", {})[block["table"]] = kinds  # the kinds of the writers that the answer showed, the largest writer first
        for rows, pairs in named:
            kept = {id(row) for row in rows}
            for row, owner in pairs:
                if id(row) in kept and owner is not None:
                    row[0] = self._show(owner, {})
        return answer

    def _sends_to(self, entry: _Entry) -> dict:
        handle = entry.resource.handle
        answer: dict = {"handle": handle, "type": type_word(entry.resource.resource_type)}
        found = self._once(("diagnostics", handle), lambda: self.arm.diagnostic_settings(entry.resource.resource_id))
        if isinstance(found, Failed):
            answer["diagnostic_settings"] = self._fail("data_writers", "the diagnostic settings", found)
            return answer
        built = [deeper.diagnostic_setting(item) for item in found]
        self._resolve_quietly([workspace for _, workspace in built if workspace])
        rows = []
        for facts, workspace in built:
            owner = self._entries.get(workspace) if workspace else None
            target = self._show(owner, {}) if owner is not None else OTHER if facts["workspace"] else None
            rows.append([facts["logs"], facts["metrics"], target, facts["storage"], facts["event_hub"], facts["partner"], facts["own_tables"]])
        rows.sort(key=lambda row: (-row[0], -row[1], str(row[2])))
        answer["diagnostic_settings"] = {"total": len(rows), "cols": ["logs", "metrics", "workspace", "storage", "event_hub", "partner", "own_tables"], "rows": rows}
        return answer

    def _tool_data_writers(self, args: dict) -> dict:
        entry = self._entry(args["handle"])
        if "data_writers" in deeper.offered(type_word(entry.resource.resource_type)):
            return self._writers_to(entry, args["table"])
        if args["table"] is not None:
            raise BadArguments("table")
        return self._sends_to(entry)

    def _deployments(self, entry: _Entry) -> "list[tuple[_Entry, dict]]":
        """The parts that an AI services account keeps inside itself, as entries (they get their handles when an answer shows them) with their typed facts. They have no cost of their own."""
        account = {"resourceGroup": entry.resource.resource_group, "subscriptionId": entry.resource.subscription_id, "location": entry.resource.location}
        built: list[tuple[_Entry, dict]] = []
        for item in self.arm.deployments(entry.resource.resource_id):
            row = deeper.deployment_row(item, account)
            child = self._ingest(row, entry.sub) if row else None
            if child is not None:
                child.part_of = child.resource.part_of = entry.key
                built.append((child, deeper.deployment_facts(item)))
        built.sort(key=lambda item: (-(item[1].get("capacity") or 0), item[1].get("model") or "", item[0].key))
        return built

    def _tool_children(self, args: dict) -> dict:
        entry = self._offered_entry(args["handle"], "children")
        handle = args["handle"]
        found = self._once(("children", handle), lambda: self._deployments(entry))
        if isinstance(found, Failed):
            return {"handle": handle, "children": self._fail("children", "the parts", found)}
        rows = [[PLACEHOLDER, *(facts.get(column) for column in CHILD_COLUMNS)] for _, facts in found[:MAX_CHILDREN]]
        answer: dict = {"handle": handle, "total": len(found), "returned": len(rows), "cols": ["handle", *CHILD_COLUMNS], "rows": rows}
        self._fit(answer, [(rows, answer, "rows")])
        answer["returned"] = len(rows)
        for row, (child, facts) in zip(rows, found):
            shown: dict = {key: value for key, value in (("sku", facts.get("sku")), ("kind", facts.get("model"))) if value is not None}
            shown["properties"] = {name: facts[key] for name, key in (("version", "version"), ("capacity", "capacity"), ("requestsPerMinute", "requests_per_minute"),
                                                                     ("tokensPerMinute", "tokens_per_minute"), ("state", "state"), ("upgrade", "upgrade")) if key in facts}
            row[0] = self._show(child, shown)
        return answer

    def _tool_metric_split(self, args: dict) -> dict:
        handle, metric, dimension, days, limit = args["handle"], args["metric"], args["dimension"], args["days"] or MAX_DAYS, args["limit"] or DEFAULT_SPLIT
        entry = self._entry(handle)
        kind = type_word(entry.resource.resource_type)
        offered = next((item for item in self._names_of(kind) if item["name"] == metric), None) if kind else None
        if offered is None:
            return {"error": "unknown-metric"}
        if dimension not in offered.get("dimensions", []):
            raise BadArguments("dimension")
        parts: dict[str, _Entry] = {}
        if "children" in deeper.offered(kind):
            known = self._once(("children", handle), lambda: self._deployments(entry))
            if not isinstance(known, Failed):
                parts = {child.resource.name.lower(): child for child, _ in known}
        start, end = self._window(days)
        unit, series = self.arm.metrics_split(entry.resource.resource_id, metric, dimension, start, end, top=limit)
        labels: dict[str, str] = {}
        found: list[tuple[object, dict, _Entry | None]] = []
        for value, points in series:
            summary = _summarise(points)
            if _bucket(summary) == "no_data":
                continue
            text, part = value.strip(), parts.get(value.strip().lower())
            if part is not None:
                said: object = PLACEHOLDER
            elif re.fullmatch(r"[0-9]{1,9}", text):
                said = int(text)
            else:
                said = labels.setdefault(text, f"v{len(labels) + 1}")
            found.append((said, summary, part))
        found.sort(key=lambda item: (-(item[1]["total"] if item[1]["total"] is not None else -1), str(item[0])))
        rows = [[said, summary["total"], summary["max"], summary["average"], summary["days_with_data"]] for said, summary, _ in found]
        shown_unit = token_word(unit, 16)
        answer: dict = {"handle": handle, "metric": metric, "dimension": dimension, "days": days, **({"unit": shown_unit} if shown_unit else {}), "values": len(rows),
                        "limit_reached": len(series) >= limit, "cols": ["value", "total", "max", "avg", "days_with_data"], "rows": rows}
        self._fit(answer, [(rows, answer, "rows")])
        for row, (_, summary, part) in zip(rows, found):
            if part is not None:
                row[0] = self._show(part, {})
                if row[0] is not None:
                    self._record_metric(row[0], metric, summary, days, shown_unit)
        return answer

    def _read_commitments(self, sub: str) -> dict:
        """What one subscription's commitments read: how the cost of the last 30 days was paid for, and the platform's own purchase recommendations. Each part is a list, or the word that says why
        there is none."""
        today = self._today()
        start, end = today - dt.timedelta(days=MAX_DAYS), today - dt.timedelta(days=1)

        def paid() -> list[dict]:
            lines, currency = deeper.pricing_lines(self.arm.cost_models(sub, start, end))
            if lines and currency != "USD":
                raise HttpError(0, "the cost is not in US dollars")
            return [{"pricing": line["pricing"], "charge": line["charge"], "usd": line["amount"]} for line in lines[:MAX_LINES]]

        def savings() -> list[dict]:
            found = [fact for term in ("P1Y", "P3Y") for item in self.arm.benefit_recommendations(sub, term) for fact in [deeper.savings_plan(item)] if fact]
            return sorted(found, key=lambda fact: (-(fact.get("saving") or 0), str(fact.get("term")), str(fact.get("sku"))))[:MAX_LINES]

        def reservations() -> list[dict]:
            found = [fact for item in self.arm.reservation_recommendations(sub) for fact in [deeper.reservation(item)] if fact]
            return sorted(found, key=lambda fact: (-(fact.get("saving") or 0), str(fact.get("term")), str(fact.get("sku"))))[:MAX_LINES]

        return {name: self._access(sub, what, self._guard(read)) for name, what, read in (
            ("paid_for", "the cost by how it was paid for", paid), ("savings_plan", "the savings plan recommendations", savings), ("reservation", "the reservation recommendations", reservations))}

    def _tool_commitments(self, args: dict) -> dict:
        for sub, outcome in self._pool([sub for sub in self.subscriptions if ("commitments", sub) not in self._kept], self._read_commitments).items():
            self._kept[("commitments", sub)] = outcome
        blocks = []
        for sub in self.subscriptions:
            kept = self._kept.get(("commitments", sub))
            if isinstance(kept, dict):
                blocks.append({"subscription": self._label(sub), **{name: list(value) if isinstance(value, list) else value for name, value in kept.items()}})
        answer: dict = {"window_days": MAX_DAYS, "basis": "amortized", "subscriptions": blocks, **self._unread()}
        if isinstance(self.profile, CapabilityRecord):
            answer["access"] = capability.words_of(self.profile)
        if len(blocks) > MAX_BLOCKS:
            blocks.sort(key=lambda block: (-sum(len(value) for value in block.values() if isinstance(value, list)), len(block["subscription"]), block["subscription"]))
            answer["subscriptions_not_shown"] = len(blocks) - MAX_BLOCKS
            del blocks[MAX_BLOCKS:]
        self._fit(answer, [(block[name], block, name) for block in blocks for name in ("paid_for", "savings_plan", "reservation") if isinstance(block.get(name), list)])
        return answer

    def _tool_cost_history(self, args: dict) -> dict:
        handle, kind, days, basis = args["handle"], args["type"], args["days"] or DEFAULT_HISTORY, args["basis"] or "actual"
        if (handle is None) == (kind is None):
            raise BadArguments("handle")
        today = self._today()
        start, end = today - dt.timedelta(days=days), today - dt.timedelta(days=1)
        amortized = basis == "amortized"
        subs: list[str]
        unlisted: list[str] = []
        if handle is not None:
            entry = self._entry(handle)
            if entry.part_of is not None:
                raise NotOffered(handle)  # a part of a resource is billed with the resource, and no cost line is its own
            subs, where, scope = [entry.sub], ("ResourceId", (entry.resource.resource_id,)), entry.key
        else:
            self._load_type(kind)
            unlisted = [sub for sub in self.subscriptions if sub in self._unlisted]
            subs = sorted({item.sub for item in self._entries_of(kind)}, key=list(self.subscriptions).index)
            where, scope = ("ResourceType", (kind,)), kind

        def read(sub: str) -> "list[tuple[dt.date, str, float, str]] | Failed":
            return self._once(("history", sub, scope, days, amortized), lambda: self.arm.cost_days(sub, start, end, amortized=amortized, where=where))

        outcomes = self._pool(subs, read)
        rows: list[tuple[dt.date, str, float, str]] = []
        failed: list[str] = []
        last: Exception | None = None
        for sub in subs:
            found = outcomes.get(sub)
            if isinstance(found, Failed):
                self._note(sub, "the cost by day", found.error)
                failed.append(sub)
                last = found.error
            elif found is not None:
                rows.extend(found)
        if last is not None and len(failed) == len([sub for sub in subs if sub in outcomes]):
            raise last
        if any(code != "USD" for _, _, _, code in rows):
            self.notes.append("cost_history: the cost is not in US dollars, so it is not shown")
            return {"error": "unavailable"}
        daily = [0.0] * days
        per_resource: dict[str, float] = {}
        for day, resource, amount, _ in rows:
            place = (day - start).days
            if 0 <= place < days and (handle is None or resource == entry.key):
                daily[place] += amount
                per_resource[resource] = per_resource.get(resource, 0.0) + amount
        total, with_cost = _money(sum(daily)), [amount for amount in daily if amount > 0]
        said: dict = {}
        if failed or unlisted:
            self._listing(said, "unavailable", failed + [sub for sub in unlisted if sub not in failed])
        said.update(self._unread())
        answer: dict = {**({"handle": handle} if handle is not None else {"type": kind}), "basis": basis, "days": days, "from": start.isoformat(), "to": end.isoformat(),
                        "total": total, "days_with_cost": len(with_cost), "daily": [_cents(_money(amount)) for amount in daily], **said}
        ranked: list[tuple[str, float]] = []
        if handle is None:
            ranked = sorted(per_resource.items(), key=lambda item: (-item[1], item[0]))[:MAX_RESOURCES]
            self._resolve_quietly([resource for resource, _ in ranked])
            answer["resources_total"] = len(per_resource)
            answer["resources"] = [[PLACEHOLDER if resource in self._entries else None, _cents(_money(amount))] for resource, amount in ranked]
            self._fit(answer, [(answer["resources"], answer, "resources")])
            for row, (resource, _) in zip(answer["resources"], ranked):
                if resource in self._entries:
                    row[0] = self._show(self._entries[resource], {})
        elif len(_dump(answer)) > MAX_RESULT_CHARS:
            raise TooLarge()
        if handle is not None:
            self._record_metric(handle, f"Cost {basis} USD {days}d", {"total": total, "max": _cents(_money(max(daily))), "average": _money(math.fsum(with_cost) / len(with_cost)) if with_cost else None,
                                                                   "days_with_data": len(with_cost)}, days, "USD")
        return answer

    # -- what was learned: answers about people's earlier answers and about documentation that code checked, never about this estate ---------------------------------
    def _remembered(self, read: Callable[[object], object]) -> object:
        """What the memory of the loop holds. A run that keeps none has nothing to recall, which is not the same as no history: the answer is `unavailable` and a note says so."""
        if self.memory is None:
            raise StoreError("this run keeps no memory")
        return read(self.memory)

    def _tool_recall_lessons(self, args: dict) -> dict:
        kind = args["type"]
        return learning.recall(self._remembered(lambda memory: memory.lessons_of(kind)), kind)  # type: ignore[attr-defined,arg-type]

    def _tool_recall_knowledge(self, args: dict) -> dict:
        kind = args["type"]
        return library.knowledge_answer(self._remembered(lambda memory: memory.claims_of(kind)), kind, self.now)  # type: ignore[attr-defined,arg-type]

    def _tool_recall_open_questions(self, args: dict) -> dict:
        """The open questions of the store (learning.OpenQuestions), each with the handle of its resource: the resources are read by id, like those of an id from a cost line, so that a handle
        is issued by the same rules and works with every other tool. A resource that Resource Graph does not return is counted as gone, and one that could not be read as unread."""
        pool = self._remembered(lambda memory: learning.OpenQuestions(memory, self.now).rows(learning.OPEN_POOL))
        self._resolve_quietly([question.resource_id for question in pool])  # type: ignore[attr-defined]
        found: list[tuple] = []
        gone = unread = 0
        for question in pool:  # type: ignore[attr-defined]
            entry = self._entries.get(question.resource_id.lower())
            if entry is not None:
                found.append((question, entry))
            elif question.resource_id.lower() in self._missing:
                gone += 1
            else:
                unread += 1
        shown = found[:MAX_OPEN_QUESTIONS]
        self._prefetch_costs([entry.sub for _, entry in shown])
        rows: list[list] = []
        for question, entry in shown:
            handle = self._show(entry, {})
            if handle is None:
                break
            rows.append([handle, type_word(entry.resource.resource_type) or OTHER, question.runs_seen, question.days_open, question.confidence, question.request])
        answer: dict = {"source": OPEN_SOURCE, "total": len(pool), "cols": list(OPEN_COLUMNS), "rows": rows}  # type: ignore[arg-type]
        if len(found) > len(rows):
            answer["not_shown"] = len(found) - len(rows)
        for name, count in (("gone", gone), ("unread", unread)):
            if count:
                answer[name] = count
        return answer
