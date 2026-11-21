"""The tools of the investigator: read-only reads of the estate whose answers hold typed values only, and opaque handles instead of names.

A tool answer is a JSON string of at most MAX_RESULT_CHARS characters (result_cap(name): MEASURE_RESULT_CHARS for measure and metric_summary, which answer for a whole type, and a cap of its own for profile). A resource is named by a handle (r1, r2, ...) that means something only in this run: the id,
the name, the tags and every other text that somebody wrote about a resource stay in the Resource below and never go into an answer. What does go into an answer is a
number, a flag, a GUID, or a short word in the form that the platform itself uses. The checks bound the alphabet, the length and the number of parts of a word, and
that does not say what a word means, so a text goes into an answer only where the platform, and not the owner of the estate, chooses it:
  - a text of a property (STRING_LEAVES, KNOWN_PATHS) only under a key that is one of a fixed list of names of enumerations, never by the end of a key; and a property is shown at all
    only at a path that the platform lists for the type of the resource (the aliases of Azure Policy: Arm.provider_paths, read once for each namespace, kept for the run as a Listing),
    every key of the path included, so that a key that somebody chose in a map is never a part of a path. When the list cannot be read or the type has none, only the exact paths of
    KNOWN_PATHS are shown, and the answer says property_list: unavailable or not-offered;
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
by whether the metric had data in the window. no_data is a resource with no value on any day, positive one with any aggregation above 0 (the total, the maximum or the average: a metric
that offers no total has none), and zero any other resource that has data (every aggregation that it has is 0, in practice); with_data is zero plus positive and resources is with_data
plus no_data. For metric_summary it counts the resources of the call. For measure
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
      "limits"                            {key path: {"lowest": a whole number, "highest": a whole number}}: for a count or a size among the properties, the range that Microsoft's reference
                                          page of the type documents for the last key of its path (cases/ranges.py), a bound that the page does not give left out. It is there only when the toolbox
                                          has a reader (`Toolbox.ranges`) that read the page, and holds no path that "properties" does not: a property with no entry has no range that was read, which is
                                          not the same as none
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
      "history"                           {"age_days", "created_by", "changed_days", "changed_by", "written_14d"}: what changes or profile showed of the age of h and its last change, as numbers
                                          and words (ownership.history): a kind of identity is a word and never an identity, and what no source said is "not-recorded"
  Toolbox.meters[m]     the Meter (cases/meters.py) of a meter handle m (m1, m2, ...) that cost_meters showed: its scope (the handle of a resource, or a resource type), the six words of the meter as Cost
                        Management gives them (for the code, never shown as they are), the quantity and the cost over its window, the cost of each day and how many resources carry it. The same meter of
                        the same scope has the same handle all through the run, and the numbers are those of the longest window that a call showed it for. A line that no resource owns has no handle.
  Toolbox.prices[p]     the Line (cases/prices.py) of a price handle p (p1, p2, ...) that price_alternatives showed: its service, product, SKU, meter, unit of measure, the price of one unit in US dollars, its region
                        (`Global` for a price that holds in every region) and how many price steps it has. The same line has the same handle all through the run. Only a line with ONE price (tiers == 1) and a price
                        above nothing has a handle and is in the table: a price with steps shows with `steps` and no handle, and a price of nothing (a free line of the list, which would save all that a meter costs) is
                        no price and is not shown, so that the code which prices a switch to a line cannot take the price of a first step for the price of a quantity, nor a free line for an alternative. That code
                        must still refuse tiers > 1 and a price of nothing, a unit that is not the meter's and a service that is not the meter's: the register does not know the meter.
  Toolbox.retail[m]     the list price of one unit of the line that the words of the meter handle m name, as price_alternatives showed it (its `retail`): the like-for-like price against which the code that prices a
                        switch compares an alternative, whatever the bill pays. It depends on the words of the meter and not on its window or on the ask, so a longer window does not drop it and neither does a
                        later ask that did not reach the line (a cap may have cut the read before it). A meter has none when neither it nor a meter that shares its list was asked about, when no line has its words
                        so far, or when an ask found that its list price has steps or that several lines with its words disagree (which takes it away). No list price, no switch is priced.
  Toolbox.offers[m]     the price handles that price_alternatives showed for the meter handle m in this run (the rows of the pages that it showed and its current line, never a price with steps or of nothing). The
                        form `alternative` of cases/pricing.py takes a price handle only from here, so that a price that no tool showed for that meter (and so for its service and region) is never priced.
                        The prices of one product in one unit are the prices of every meter of the same resource that has the same service, product and unit, so an ask for one of them registers `offers`, `retail`
                        and `ages` for each of the others too: the same rows and current line, and the line that the words of that meter name. The answer of the tool is the same.
  Toolbox.ages[h]       how many whole days old the copy of the price book was that last showed the handle h, a meter handle m (for its `retail`) or a price handle p (for its line), when it was a copy of at least
                        a day: a handle that a read of the list showed, or a copy of today, has no entry. The code that prices a switch (cases/pricing.py) says it to the owner with the figure, so that a list price
                        that may be weeks old is never shown as if it were today's.
  Toolbox.log           one dict for each call: {"name", "arguments", "ok", "chars"}. Toolbox.call never raises.

neighbors, profile and changes. neighbors reads the references that the resources of the estate hold to one another once for a run (cases/neighbors.py), and shows what one resource refers to and what
refers to it, with one of two words of code for each (`parent` for the structure of an id, `refers` for a reference in a property) and never the key that held it. profile gives the picture of up to five resources in one call (cases/dossier.py: the same function, build_dossier, is for code that does not
use the tools); its answer has a cap of its own, result_cap("profile"), because a picture of five resources does not fit under MAX_RESULT_CHARS, and a part of it that did not finish in the time of the call is
`unread`, by handle. changes shows the age of a resource and its last change as numbers and the kind of identity as a word. Their numbers are in Toolbox.evidence like those of the other tools.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

from . import capability, deeper, dossier, learning, library, prices, ranges
from . import metrics as mx
from . import neighbors as nb
from . import ownership
from .arm import SCOPE_ID, Arm, CostLine, MetricPoint, TimeUp
from .detectors import some
from .foundry import FunctionTool
from .http import HttpError, Refused
from .identity import IdentityError
from .memory_store import parse, stamp
from .meters import Meter, fold, shape
from .models import CapabilityRecord, PriceBookRecord, StoreError
from .roles import MAX_CITED_NAME

MAX_RESULT_CHARS = 6000
MEASURE_RESULT_CHARS = 12000  # for measure and metric_summary, which answer for a whole type: 54 resources with 3 metrics are about 8,500 characters, and 80 with 4 are cut, the last ones named as unread
MAX_CALLS = 40  # calls of one Toolbox; the next ones answer "limit"
MAX_LISTED = 40  # resources or cost lines in one answer
TRIAL_LINES = 200  # the most lines of a price list that a trial read keeps for the run: a product has a few dozen, and a whole service is never kept from a trial
WARM_PRODUCTS = 12  # the dearest meters of the last 30 days that the warm-up of the price book reads the products of (cases/investigate.py asks for it before the first beat)
WARM_RESOURCES = 24  # the dearest resources, by the cost lines, whose meters it asks about, in one query for each subscription: no meter costs more than its resource
WARM_SECONDS = 180.0  # what the whole warm-up may take: the reads, the gaps between them and the waits that the list asks for
WARM_GAP = 6.0  # seconds between two reads of the list in the warm-up: the list showed a window of 60 seconds and ten requests, and one read of a product is one request
WARM_WAIT = 60.0  # the longest wait that the warm-up takes for a list that asks to wait: the window that the list showed
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
PRELOAD_WORKERS = 5  # the types whose resources `preload` reads at the same time: one question of Resource Graph each, and the quota of Resource Graph is one for the whole identity
READ_WORKERS = 4  # subscriptions whose cost lines, recommendations or plans are read at the same time in one call: Cost Management allows 12 query units in 10 seconds for a tenant, and a 30 day read costs one
READ_BUDGET_SECONDS = 60.0  # of one measurement
SUBSCRIPTION_SECONDS = 45.0  # what the reads of the subscriptions in one tool call may take in all: a call that has used it reads no further subscription (what it read is kept)
NOT_READ_SHOWN = 5  # the subscriptions that an answer names, by label, when some were not read or could not be: it counts the rest
MAX_BLOCKS = 20  # the subscriptions that estate_overview and paid_features show when the estate has more: the dearest ones, with a count of the others
SUBSCRIPTION_NOTES = 10  # the notes about one subscription that could not be read: the later ones are counted in one note
MAX_NODES = 4000  # values looked at in the properties of one resource
MAX_NAMESPACES = 80  # the namespaces whose lists of property paths one run reads: the next ones are `unavailable`
LIST_SECONDS = 20.0  # what the reads of the platform's lists of property paths may take in one call, besides the SUBSCRIPTION_SECONDS of the reads of the subscriptions: a list that is not started in it waits for a later call
MAX_PENDING = 2000  # the resources that wait, with their properties as they were read, for a list that a call had no time to read
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
OPEN_COLUMNS = ("handle", "type", "seen", "days_open", "confidence", "request", "why")
OPEN_SOURCE = "earlier findings that no person has decided: counts and words that Meternaut kept, not facts about this estate"
QUERY_SECONDS = 45.0  # what one read of a resource's own records may take
NOT_VISIBLE = "not visible with this access"  # what an answer says of a part that the access of the run cannot read: never "none"
NO_METRICS = "no-metrics"  # what an answer says of a type that offers no platform metrics: nothing to read, and not use
NO_METRICS_TEXT = "is not a supported platform metric namespace"  # how Azure Monitor refuses the definitions of such a type (HTTP 400)
NOT_DOLLARS = "not in dollars"  # what an answer says of a scope whose cost is in another currency: it is never added up
MAX_METRICS = 8  # the metrics that one call of metric_summary or measure reads
METER_WORDS = ("category", "subcategory", "name", "pricing", "charge", "unit")  # the six words of a meter, in the order of the dimensions that Cost Management groups by
METER_COLUMNS = ("meter", *METER_WORDS, "quantity", "usd", "share", "days", "avg_day", "min_day", "max_day", "cv", "first_day", "last_day")
READER_SOURCES = ("rules", "saved_searches", "workbooks", "analytics_rules")  # what data_readers counts, in the order of its columns
NEIGHBOR_COLUMNS = ("handle", "type", "relation", "usd30d", "sku", "kind", "state")  # what neighbors tells of each resource that a reference joins, in the order of its columns
NEIGHBOR_ROWS = 20  # the handles of one page of neighbors
FAN_IN = 10  # the resources that refer to one resource, above which neighbors also gives a row for each type and relation
NEIGHBOR_GROUPS = 12  # the rows of that summary
DOSSIER_WORKERS = 6  # the reads of one profile that are made at the same time
OWNER_READS = 24  # the Activity Logs that the tools read in one beat: a picture of five resources reads five of them and a beat makes up to five pictures (it was 12)
OWNER_SECONDS = 150.0  # and the seconds that those reads may take in one beat, added up over the reads that run at the same time (ownership.OwnerReader), and not the time between them: five reads were measured at 31 seconds (6.2 each, one picture), so at 150 the 24 reads bind first and the seconds bind only when the log is slower than 6.25 seconds a read (it was 30, used up by the first picture of a beat)
HISTORY_COLUMNS = ("handle", "age_days", "created_by", "changed_days", "changed_by", "written_14d")
AGES = ("// meternaut:ages\nresources\n| where id in~ ({ids})\n| project id, sd = systemData, made = coalesce(tostring(properties.timeCreated), tostring(properties.creationTime), "
        "tostring(properties.createdTime), tostring(properties.creationDate), tostring(properties.CreationDate), tostring(properties.createdDate), tostring(properties.dateCreated), "
        "tostring(properties.createdAt))")
CHILD_COLUMNS = ("model", "version", "sku", "capacity", "requests_per_minute", "tokens_per_minute", "state", "upgrade")  # what children tells of each part, in the order of its columns

ERRORS = ("bad-arguments", "unknown-tool", "unknown-handle", "unknown-metric", "not-offered", "unavailable", "limit", "too-large", "failed", NO_METRICS)
READ_ERRORS = (HttpError, Refused, IdentityError, StoreError)
OTHER = "other"  # what an answer shows for a text that is there and fails its check: never the text itself
UNAVAILABLE = "unavailable"  # what property_list says when the platform's list of property paths for a namespace could not be read
NOT_OFFERED = "not-offered"  # and when the platform lists none for the type

# The word checks. The patterns of the four arguments are written once, as the schema of the tools gives them to the agent, and compiled here; every check is a full match.
# The other checks keep a text that somebody could have written to the forms that the platform itself uses: a bound on the alphabet, the length and the number of parts.
TYPE_PATTERN = r"^[a-z0-9.]+(/[a-z0-9._-]+){1,4}$"
SERVICE_PATTERN = r"^[A-Za-z0-9 .&()-]{1,40}$"
METRIC_PATTERN = r"^[A-Za-z0-9_./ ]{1,64}$"
HANDLE_PATTERN = r"^r[0-9]{1,4}$"
METER_PATTERN = r"^m[0-9]{1,4}$"  # the handle of a meter that cost_meters showed
TABLE_PATTERN = r"^(t[0-9]{1,4}|[A-Za-z][A-Za-z0-9]{0,63})$"  # a kind of data of a resource: a handle of this run or the name that the platform gave it
DIMENSION_PATTERN = r"^[A-Za-z][A-Za-z0-9]{0,40}$"  # the name of a dimension of a metric, as metric_names shows it
TYPE, SERVICE, METRIC, HANDLE, METER, TABLE, DIMENSION = (re.compile(pattern) for pattern in (TYPE_PATTERN, SERVICE_PATTERN, METRIC_PATTERN, HANDLE_PATTERN, METER_PATTERN, TABLE_PATTERN, DIMENSION_PATTERN))
SERVICE_FORM = re.compile(r"[A-Za-z0-9.&()-]+(?: [A-Za-z0-9.&()-]+){0,4}")  # one to five words, one space between them
METER_FORM = re.compile(r"[A-Za-z0-9.&()/:+-]+(?: [A-Za-z0-9.&()/:+-]+){0,9}")  # one to ten words, one space between them
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
# The exact paths of properties that are shown whatever the platform's list for the type says (those lists are not complete), and the only ones that are shown when that list could not be
# read or the type has none. Each is a path that the platform itself defines, with no key that somebody could choose.
KNOWN_PATHS = frozenset(tuple(path.split(".")) for path in (
    "privateLinkServiceConnections.properties.privateLinkServiceConnectionState.status",
    "manualPrivateLinkServiceConnections.properties.privateLinkServiceConnectionState.status",
    "privateEndpointConnections.properties.privateLinkServiceConnectionState.status",
    "extended.instanceView.powerState.code", "powerState.code", "agentPoolProfiles.powerState.code",
    "functionAppConfig.scaleAndConcurrency.alwaysReady.instanceCount",
    "virtualRouterAutoScaleConfiguration.minCapacity"))
def _lowered(path: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(key.lower() for key in path)


# The paths of KNOWN_PATHS and every beginning of them, found by their keys in lower case, each as the platform spells it.
_KNOWN_SPELLED = {_lowered(path[:length]): path[:length] for path in sorted(KNOWN_PATHS) for length in range(1, len(path) + 1)}
# Names that hold somebody's text, an address or a secret, or that hold a dictionary whose keys somebody chose. A property is not shown by this list: the platform's list for the type decides
# (Listing), and a list of names is incomplete by nature. cases/neighbors.py uses it for the one thing that is left, which keys of a resource it reads a reference from. A key is denied when the
# whole of it is one of these names, or when one of the words of its camel case is one of the DENIED_WORDS (nodeLabels, appSettings).
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


def meter_word(value: object) -> str | None:
    """A field of a meter as Cost Management gives it (category, subcategory, name, pricing, charge, unit): at most 64 characters of the letters, digits and . & ( ) / : + - in at most ten
    words with one space between them, written as the platform writes its names (see _titled; a word that is one hyphen stands between two names). The platform makes these words: the owner
    of an estate cannot write one, so the alphabet is wider than a service name's, which has no slash for a unit such as a month."""
    words = [word for word in value.split(" ") if word != "-"] if isinstance(value, str) else []
    return value if words and len(value) <= 64 and METER_FORM.fullmatch(value) and _titled(words) else None


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


class Listing:
    """The property paths that the platform lists for one resource type (cases/arm.py, provider_paths), as tuples of keys in the platform's own spelling. A key of a resource is found by its
    letters in lower case, and a path is shown as the platform spells it, never as the resource does, so that one property is not shown twice under two cases: `spelled` holds each listed path and
    each beginning of one, found by its lower-case keys, as the list gives it (the first in the order of the text when it gives a path in two spellings, and a listed path before the beginning of a
    longer one), and `whole` the lower-case paths that may be shown, which the others may only be followed to. A key that is not plain ASCII is never found."""

    __slots__ = ("spelled", "whole")

    def __init__(self, paths: "frozenset[tuple[str, ...]]") -> None:
        ordered = sorted(paths)
        self.spelled: dict[tuple[str, ...], tuple[str, ...]] = {}
        for path in ordered:
            self.spelled.setdefault(_lowered(path), path)
        self.whole = frozenset(self.spelled)
        for path in ordered:
            for length in range(1, len(path)):
                self.spelled.setdefault(_lowered(path[:length]), path[:length])


def _rank(leaf: str) -> int:
    lowered = leaf.lower()
    if "numberof" in lowered:
        return SUFFIXES.index("Count")
    return next((place for place, suffix in enumerate(SUFFIXES) if lowered.endswith(suffix.lower())), len(SUFFIXES))


def _order(path: str) -> tuple[int, int, int, str]:
    leaf = path.rsplit(".", 1)[-1]
    return (1 if leaf == "provisioningState" else 0, _rank(leaf), path.count("."), path)


def typed_properties(properties: object, sku: object = None, listed: "Listing | None" = None) -> list[tuple[str, "bool | int | float | str | list"]]:
    """The properties of a resource that an answer may show, the most informative first: a flag or a number under a key that ends in one of the SUFFIXES, a short word under a key that is one of
    the STRING_LEAVES, and the length of a list as <key>Count. A property is shown only at a path that `listed`, the platform's list for the type of the resource, names (every key of the
    path, the last one too, so a map that somebody fills shows at most as its own name, and nothing under it is followed) or at an exact path of KNOWN_PATHS; with no list (None: it could
    not be read, or the platform has none for the type) only at the paths of KNOWN_PATHS, and no length of a list.

    A path is shown as the platform spells it (Listing.spelled, and the paths of KNOWN_PATHS as they are written there), never as the resource spells it, so the keys of the answer are
    the same for every resource and one property is not shown twice under two cases (the values of the two are one list of up to three). A path of more than MAX_CITED_NAME characters, or that
    does not begin with a letter, is not shown: a finding cannot cite it.

    The items of a list are followed under the key of the list, so the value of a path is that of every item: one value when they agree, else up to three."""
    found: dict[str, list] = {}
    budget = [MAX_NODES]

    def add(shown: tuple[str, ...], value: "bool | int | float | str") -> None:
        text = ".".join(shown)
        if len(text) > MAX_CITED_NAME or not (text[:1].isascii() and text[:1].isalpha()):
            return
        values = found.setdefault(text, [])
        if not any(type(seen) is type(value) and seen == value for seen in values):
            values.append(value)

    def walk(node: object, lower: tuple[str, ...], shown: tuple[str, ...]) -> None:
        budget[0] -= 1
        if budget[0] < 0:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.isascii():
                    step = (*lower, key.lower())
                    named = _KNOWN_SPELLED.get(step) or (listed.spelled.get(step) if listed is not None else None)
                    if named is not None:
                        walk(value, step, named)
        elif isinstance(node, list):
            if shown:
                if listed is not None:
                    add((*shown[:-1], f"{shown[-1]}Count"), len(node))
                for item in node[:LIST_ITEMS]:
                    if isinstance(item, dict):
                        walk(item, lower, shown)
        elif shown and (shown in KNOWN_PATHS or (listed is not None and lower in listed.whole)):
            value = _leaf(shown, node)
            if value is not None:
                add(shown, value)

    walk(properties, (), ())
    if isinstance(sku, dict):
        walk({"sku": sku}, (), ())
    ranked = sorted(found.items(), key=lambda item: _order(item[0]))[:DESCRIBED_PROPERTIES]
    return [(path, values[0] if len(values) == 1 else values[:3]) for path, values in ranked]


def _largest(properties: list[tuple[str, "bool | int | float | str | list"]]) -> float:
    """The largest count, size or capacity among typed properties: what `count` orders by."""
    numbers = [number for path, value in properties if _rank(path.rsplit(".", 1)[-1]) in COUNT_LIKE for number in (value if isinstance(value, list) else [value])
               if isinstance(number, (int, float)) and not isinstance(number, bool)]
    return float(max(numbers, default=0))


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
    property_list: str = ""  # why its properties are the few of KNOWN_PATHS: `unavailable` (the platform's list for its namespace could not be read) or `not-offered` (the platform lists none for its type)
    raw: "tuple[object, object] | None" = None  # the properties and the sku as they were read, kept while the entry waits for a list that its call had no time to read (Toolbox._settle)

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
            body = {"type": "array", "items": {"type": "string", "pattern": HANDLE_PATTERN}, "minItems": 1, "maxItems": self.high or MAX_MEASURED}
        elif self.kind == "metrics":
            body = {"type": typed("array"), "items": {"type": "string", "pattern": METRIC_PATTERN}, "minItems": 1, "maxItems": MAX_METRICS}
        else:
            body = {"type": typed("string"), "pattern": {"type": TYPE_PATTERN, "service": SERVICE_PATTERN, "metric": METRIC_PATTERN, "handle": HANDLE_PATTERN, "meter": METER_PATTERN,
                                                        "table": TABLE_PATTERN, "dimension": DIMENSION_PATTERN}[self.kind]}
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
            if not isinstance(value, list) or not 1 <= len(value) <= (self.high or MAX_MEASURED) or not all(isinstance(item, str) and HANDLE.fullmatch(item) for item in value):
                raise BadArguments(self.name)
            return list(dict.fromkeys(value))
        if self.kind == "metrics":
            if not isinstance(value, list) or not 1 <= len(value) <= MAX_METRICS or not all(_match(METRIC, item) for item in value):
                raise BadArguments(self.name)
            return list(dict.fromkeys(value))
        text = {"type": type_word, "service": _service_form, "metric": lambda item: _match(METRIC, item), "handle": lambda item: _match(HANDLE, item),
                "meter": lambda item: _match(METER, item), "table": lambda item: _match(TABLE, item), "dimension": lambda item: _match(DIMENSION, item)}[self.kind](value)
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
_ONE = Param("metric", "metric", _METRIC + " Null when metrics is given.")
_MANY = Param("metrics", "metrics", "Up to 8 metric names, as metric_names shows them, read in one call. Null when metric is given: give one of the two, never both.")
_GRAIN = Param("grain", "choice", "day: daily buckets. hour: also the peak and p95 of the finer buckets, for a question about peaks. Null for day.", choices=("day", "hour"))
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
         "answer carries no names, tags or other text of the resources. limits is the same as in describe, one mapping for the whole table. When has_more is true, read the next page with next_offset.",
         (Param("type", "type", _TYPE, required=True),
          Param("order_by", "choice", "cost: the dearest first. count: the largest count, size or capacity property first. Null for cost.", choices=("cost", "count")),
          Param("limit", "integer", "How many resources to return, 1 to 40. Null for 40.", low=1, high=MAX_LISTED), _OFFSET)),
    Tool("metric_names",
         "Lists the metric names that Azure Monitor offers for the resources of one resource type, each with its unit and its primary aggregation. Use a name with "
         "metric_summary or measure. A type that offers no platform metrics answers no-metrics: nothing to measure, and no sign of use.",
         (Param("type", "type", _TYPE, required=True), _OFFSET)),
    Tool("metric_summary",
         "Measures Azure Monitor metrics for up to 60 resources, named by handle, in daily buckets over the last days (at most 30): one metric (metric) or up to 8 (metrics). For each "
         "resource (and metric): total (the sum of the daily totals), max (of the daily maximums), average (the mean of the daily averages) and days_with_data; null when the metric has none. "
         "With grain hour a row also has peak (the greatest value of any finer bucket) and p95 (95 percent of those buckets are at or below it); read_at names a finer grain that was read. "
         "summary counts the resources that were read by whether the metric had data in the window: resources, with_data (positive: the total, maximum or average is above 0; zero: none is), no_data and days. "
         "A type that offers no platform metrics answers no-metrics, which is no sign of use. A read that failed says unavailable with the platform's code word. After 60 seconds "
         "the answer says partial and lists the handles that were not read.",
         (Param("handles", "handles", "Handles of resources that earlier answers showed, 1 to 60 of them.", required=True), _ONE, _MANY,
          Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS), _GRAIN)),
    Tool("measure",
         "Measures Azure Monitor metrics across the resources of one type, the dearest first, in daily buckets over the last days (at most 30), as a table: one metric (metric) or "
         "up to 8 (metrics). Each array in rows follows cols: one resource and metric: handle, metric, usd30d (dollars), total, max and avg (the sum of the daily "
         "totals, greatest daily maximum, mean of the daily averages; null when the metric has none), days_with_data and, with grain hour, peak and p95 (95 percent of the "
         "buckets are at or below it); read_at names a finer grain that was read. summary counts the resources shown so far by whether the metric had data in the window: resources, "
         "with_data (positive: a total, maximum or average above 0; zero: none), no_data and days. failed lists the handles whose read failed, with failed_codes. A type that offers no platform "
         "metrics answers no-metrics, which is no sign of use. After 60 seconds partial is true and unread lists the handles not read. When has_more is true, use next_offset.",
         (Param("type", "type", _TYPE, required=True), _ONE, _MANY, Param("days", "integer", "How many closed days to look back, 1 to 30. Null for 30.", low=1, high=MAX_DAYS),
          Param("limit", "integer", "How many resources to measure, 1 to 80. Null for 40.", low=1, high=MAX_MEASURE_ROWS), _OFFSET, _GRAIN)),
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
         "or words. A property is shown only where the platform lists it for the type; property_list says unavailable or not-offered when that list could not be read or is none, and then few "
         "properties are shown. When the type has deeper reads, reads names them. limits gives, for a count or a size among the properties, the lowest and highest number that Microsoft's "
         "reference page of the type documents for it, and leaves out a bound that the page does not give. A property with no limits entry has none that was read, which is not the same as none. "
         "The answer carries no names, tags or other text of the resource.",
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
         "metric_names shows the dimensions that each metric has. A type that offers no platform metrics answers no-metrics.",
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
    Tool("cost_meters",
         "Shows what one resource (handle) or all resources of one type (type; service keeps one service) are billed for, meter by meter, over the last 7 to 30 closed days, dearest first, as a "
         "table (cols and rows; same holds a field that is the same in every row). A row: meter (m1, m2, ... for this run; null for a line that no resource owns), category, subcategory, name, "
         "pricing, charge and unit as short words of the platform, quantity and usd over the window, share of the scope's cost, and the daily shape: days (that have a cost), avg_day, min_day, "
         "max_day, cv (the spread of the daily cost over the whole window divided by its mean), first_day and last_day (how many days ago). For a type also resources, how many carry the meter. "
         "It says what is billed, not why. costs says not in dollars when the cost is in another currency. Give a handle or a type, never both. When next_offset is there, read the next page "
         "with it. An answer is kept for the run.",
         (Param("handle", "handle", "The handle of one resource that an earlier answer showed. Null when a type is given."),
          Param("type", "type", "A resource type, in lower case, as estate_overview shows it. Null when a handle is given."),
          Param("service", "service", "A service name, as estate_overview shows it, to keep one service of a type. Null for any service."),
          Param("days", "integer", "How many closed days to look back, 7 to 30. Null for 30.", low=7, high=MAX_DAYS), _OFFSET)),
    Tool("price_alternatives",
         "Shows Azure's public pay-as-you-go prices in US dollars for the service of one meter (meter: a handle from cost_meters), in its resource's region and the meter's unit, as a table, "
         "the lowest first, those with steps last. Lines: the meter's product, or the whole service (within). cols names the columns of each array in rows: a price handle for this "
         "run (none for a price with steps), its words, usd (price of a unit) and steps (above 1: the price changes with quantity); same holds what every row shares. current is the line of the "
         "meter's words: retail (its price), paid (what the bill paid for a unit) and rate_ratio (paid divided by retail); match says found, none or several. other_units counts the lines with another "
         "unit; complete says whether the whole list was read (ended: a failure cut it short). "
         f"source says list (read now) or book (a copy, age_days old; over {prices.FRESH_DAYS} days it is stale, shown because the list could not be read). "
         "It shows prices only. A failed read says unavailable.",
         (Param("meter", "meter", "The handle of a meter of one resource, as cost_meters showed it (m1, m2, ...). The meter of a whole type has no region and is not offered.", required=True),
          Param("within", "choice", "product: the lines of the product that the meter belongs to. service: every product of the service, which can be long, so read it page by page. Null for product.",
                choices=("product", "service")), _OFFSET)),
    Tool("neighbors",
         "Shows what one resource refers to and what refers to it, found from the references that the properties of the resources of the estate hold to one another, as tables of handles: "
         "refers_to and referred_by. A row: handle, type, relation (parent when the resource is a part of the other, refers for any other reference), usd30d, sku, kind and state as short words. "
         "A large referred_by also has a row of count and usd30d for each type and relation; read the handles "
         "page by page with offset. graph says how many resources and edges were read and how many references pointed outside this run. unavailable names subscriptions that could not be "
         "read; partial means that the pass has more to read, so call again to go on. It shows no name, tag or text and says nothing about what a reference means.",
         (Param("handle", "handle", "The handle of a resource that an earlier answer showed.", required=True),
          Param("direction", "choice", "refers_to: what it refers to. referred_by: what refers to it. Null for both; with an offset, null means referred_by.", choices=("refers_to", "referred_by")),
          _OFFSET)),
    Tool("profile",
         "Gives the whole picture of 1 to 5 resources, named by handle, in one call: facts, typed properties and their limits; meters (the dearest 6 of what it is billed for); metrics (every platform metric that has data, "
         "as rows of metric, unit, total, max, avg and days, read at the grain that it offers, and with grain hour also peak and p95, for the 20 with the greatest daily maximum if it offers more (at_hour; with_data counts all); the metrics with no data are listed by name); links (what it "
         "refers to and what refers to it, as count and usd30d for each type and relation: neighbors shows the handles); Advisor items; history (age_days, changed_days and written_14d, "
         "and created_by and changed_by as a kind of identity); its parts; and where it sends its own data. A part that was not read in time is in unread, by handle, and is not none; a "
         "part that failed says unavailable; no-metrics says that the type keeps none. It shows no name, tag or text. Its numbers can be cited as any tool's.",
         (Param("handles", "handles", "Handles of 1 to 5 resources that earlier answers showed.", required=True, high=dossier.MAX_HANDLES),
          Param("days", "integer", "How many closed days to look back, 7 to 30. Null for 30.", low=dossier.MIN_DAYS, high=MAX_DAYS), _GRAIN)),
    Tool("changes",
         "Shows how old each of 1 to 5 resources is and what was last written to it, as numbers and words: age_days, created_by and changed_by (the kind of identity that did it: person, application, "
         "managed-identity or unknown, never a name), changed_days and written_14d (true when something was written in the last 14 days). over-90 says that a log that was read to its end shows "
         "nothing in its 90 days, and not-recorded that no source says. A handle that was not read in time is in unread, and is not none. It says nothing about what an age or a change means.",
         (Param("handles", "handles", "Handles of 1 to 5 resources that earlier answers showed.", required=True, high=dossier.MAX_HANDLES),)),
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
PLACEHOLDER_METER = f"m{HANDLE_LIMIT}"
PLACEHOLDER_PRICE = f"p{HANDLE_LIMIT}"


def result_cap(name: object) -> int:
    """The most characters that the answer of a tool may have: MAX_RESULT_CHARS; MEASURE_RESULT_CHARS for `measure` and `metric_summary`, which answer for a whole type; and for `profile`, which
    answers for up to dossier.MAX_HANDLES resources, what a profile of that many may take."""
    if name == "profile":
        return dossier.MAX_HANDLES * dossier.PER_HANDLE
    return MEASURE_RESULT_CHARS if name in ("measure", "metric_summary") else MAX_RESULT_CHARS


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
    """How a measurement is counted in a summary: `no_data` when no day had a value or no aggregation has one, `positive` when any aggregation that the metric has (the total, the maximum or the
    average: a metric that offers no total has none) is above 0, and `zero` for any other measurement that has data. This only counts: it names no resource and says nothing about what a
    count means."""
    if summary["days_with_data"] == 0:
        return "no_data"
    found = [summary[name] for name in ("total", "max", "average") if summary.get(name) is not None]
    return "no_data" if not found else "positive" if any(value > 0 for value in found) else "zero"


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


def seen_hash(key: str) -> str:
    """What the record of an investigation (cases/activity.py) keeps of a resource that was looked at, and never its id: the first 12 hex characters of the SHA-256 of its lower-case id."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


class Toolbox:
    """The tools of one run: `specs` for the agent, `call` for each tool call that it makes, and, afterwards, `handles`, `evidence` and `log` for the investigation."""

    def __init__(self, arm: Arm, subscriptions: tuple[str, ...], now: dt.datetime, notes: list[str]) -> None:
        self.arm, self.subscriptions, self.now, self.notes = arm, subscriptions, now, notes
        self.memory: object | None = None  # the store of the loop, which the tools that recall read; the investigation sets it, and a run that keeps no memory has none
        self.ranges: ranges.Reader | None = None  # the reader of the documented limits of the numbers of a type (cases/ranges.py): the investigation sets it, and with none the tools show no limits
        self._unlimited: set[str] = set()  # the types whose limits were not read: `limits_note` counts them, for the one note of the run
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
        self.extra_calls = 0  # the calls beyond MAX_CALLS that this run allows: an investigation of beats makes the seeds of each beat and the calls of each, on this one toolbox (cases/beats.py)
        self._next_handle = 1
        self._entries: dict[str, _Entry] = {}  # every resource that a read returned, by lower-case id
        self._by_handle: dict[str, _Entry] = {}
        self._by_type: dict[tuple[str, str], list[str]] = {}
        self._counts: dict[str, tuple[int, dict[str, int]]] = {}
        self._costs: dict[str, _Costs | None] = {}
        self._advice: dict[str, list[_Advice]] = {}
        self._pricings: dict[str, list[dict]] = {}
        self._metric_names: dict[str, list[dict]] = {}
        self._plans: dict[str, dict[str, tuple[mx.Plan, mx.Plan]]] = {}  # type -> metric -> how to read it by the day and by the hour (metrics.plan_of)
        self._no_metrics: set[str] = set()  # the types that Azure Monitor keeps no platform metrics for
        self._without: set[str] = set()  # the types of which a read found no resource in any subscription, so that a later call does not look again
        self._reads: dict[tuple[str, str, int], dict[str, str]] = {}  # (type, metric, days) -> handle -> how its measurement counts: every resource whose numbers were shown
        self._missing: set[str] = set()  # ids that Resource Graph did not return
        self._unlisted: set[str] = set()  # the subscriptions whose resources Resource Graph could not give in this run: no listing asks for them again, and every answer that lists names them
        self._spaces: dict[str, _Space] = {}  # handle -> what is known of its settings and tables
        self._volumes: dict[tuple[str, int], tuple[list, float, str]] = {}  # (handle, days) -> the tables by volume, the billable MB, and the word that says whether it was read
        self._kept: dict[tuple, object] = {}  # what the deeper reads of the run have read, by what they asked for: a read is made once in a run, whether it worked or not
        self.meters: dict[str, Meter] = {}  # every meter that cost_meters has shown, by its handle (m1, m2, ...): the numbers of the last call that showed it
        self._meter_keys: dict[tuple, str] = {}  # (scope, service, the six words of the meter) -> its handle, so that the same meter of the same scope keeps its handle
        self.prices: dict[str, prices.Line] = {}  # every line of the price list that price_alternatives has shown, by its handle (p1, p2, ...): the same line has the same handle all through the run; only a line with one price has a handle
        self.retail: dict[str, float] = {}  # meter handle -> the list price of one unit of the line that the words of the meter name, as price_alternatives showed it, for the meter or for a meter of its resource that shares its list (a line with one price, above nothing); only an ask that finds that the line has steps, or that lines disagree, takes it away
        self.offers: dict[str, set[str]] = {}  # meter handle -> the price handles that price_alternatives showed for it in this run, or for a meter of its resource with the same service, product and unit: the rows of the pages that it showed, and its current line
        self.ages: dict[str, int] = {}  # meter handle or price handle -> how many whole days old the copy of the price book was that last showed it, when it was a copy of at least a day: a read of the list, or a copy of today, leaves none
        self._price_keys: dict[tuple, str] = {}
        self._books: "dict[tuple, prices.Book | Failed]" = {}  # (service, region, product or None) -> the prices read for it (or a copy of the price book), or the failure: a price list is read once in a run
        self._prices_down: Failed | None = None  # the failure of the first read of the price list that got no answer at all: the host is not asked again in the run
        self._hold = prices.Hold()  # what the list asked for in this run that was not waited for, and the reads that waited (cases/prices.py)
        self.emit: Callable[..., object] | None = None  # the `emit` of the History, which the investigation sets: a line `prices.read` for each try that reaches the list. A run that keeps no History has none
        self.trial = False  # True while a call is a trial: a read that code makes for a beat, which leaves no failure and no list that is not whole or is larger than a product behind (cases/investigate.py sets it)
        self.window: frozenset[str] = frozenset()  # the hashes (seen_hash) of the resources that the runs of the last days looked at, from the records of the investigations (cases/investigate.py sets it)
        self.rotate = False  # True while a call is a read that code makes for a beat: `list_resources` by cost then puts what the window does not hold first (cases/investigate.py sets it, as it sets `trial`)
        self.backfill: dict[str, int] = {}  # type -> how many of its dearest resources count as looked at for that read, beside `window`, as the runs from before the hashes seeded them (cases/investigate.py sets it)
        self._trials: list[Failed] = []  # the trial reads of the price list that failed one after the other: two end the trials of the run, and no call of the Investigator is held by them
        self._failures: dict[int, Failed] = {}  # the failures that have a note already, by id
        self.owners: ownership.OwnerReader | None = None  # the reader of the Activity Log of the tools (`changes`, `profile`): the investigation sets one that shares what it keeps with its own
        self._aged: dict[str, tuple[object, object]] = {}  # lower-case id -> the systemData and the creation time of the properties that Resource Graph gave (None for what it lacks)
        self._edges: nb.Edges | None = None  # the pass over the references of the estate (neighbors): read once in a run, a page at a time
        self._read: dict[str, str] | None = None  # for the tools that give a picture of resources: the handles that the call that is running held data of, with the letters of what (see Toolbox.log)
        self._pictures: dict[tuple, tuple[dict, float]] = {}  # the parts of a profile that were read in full, by handle, days and grain, with the seconds that their read took: a plain repeat is answered from them
        self._saved: float | None = None  # the seconds that the call that is running did not spend, because the pictures were kept
        self._lists: "dict[str, dict[str, frozenset[tuple[str, ...]]] | str]" = {}  # namespace -> the paths that the platform lists for each of its types, or the word that says why not: read once in a run
        self._listings: "dict[str, Listing | str]" = {}  # type -> its Listing, or the word that says why it has none
        self._held: dict[str, list[str]] = {}  # namespace -> the subscriptions that hold a resource of it, in the order that they were met: the list of a namespace is read with the first of them and, when that fails, one other
        self._late_lists: set[str] = set()  # the namespaces whose list the call that is running had no time to read: unavailable in this call only, and nothing is kept of it
        self._listed_seconds = 0.0  # what the call that is running has spent on reading lists (they have a time of their own: LIST_SECONDS)
        self._pending: dict[str, list[_Entry]] = {}  # namespace -> the entries that were typed without its list, which a later read of the list types again
        self._pending_count = 0

    @property
    def specs(self) -> tuple[FunctionTool, ...]:
        """The function tools that the agent is defined with."""
        return SPECS

    def known_of(self, handle: str) -> tuple[str | None, dict[str, "bool | int | float | str | list"]]:
        """The SKU name and the typed properties (typed_properties) of a resource, as the toolbox holds them for its handle: for the code of a case, never for an agent. (None, {}) for a handle that
        no answer has shown. A resource that was typed without the platform's list because its call had no time to read it gets the list now: outside a call nothing is late."""
        entry = self._by_handle.get(handle)
        if entry is not None and entry.raw is not None:
            self._prefetch_lists([(entry.resource.resource_type, entry.sub)])
        return (entry.sku, dict(entry.properties)) if entry is not None else (None, {})

    def looked_at(self) -> frozenset[str]:
        """For code (cases/activity.py): the hashes of the resources of which a call of `profile` in this run, the Investigator's or code's, read some of the picture. A resource that was only listed or
        described, or of which nothing could be read, is not one."""
        return frozenset(seen_hash(self._by_handle[handle].key) for call in self.log if call["name"] == "profile" for handle in call.get("read", ()))

    def seen_in(self, kinds: Iterable[str]) -> int:
        """For code (cases/beats.py): how many of the resources of these types that a read has listed were looked at by the runs of the last days, and not by this one: the resources that `window` holds
        and the `backfill` dearest of their type, which may be some of the same, counted once."""
        return sum(n < self.backfill.get(kind, 0) or seen_hash(entry.key) in self.window for kind in kinds for n, entry in enumerate(sorted(self._entries_of(kind), key=lambda entry: (-(self._cost_total(entry) or 0.0), entry.key))))

    def call(self, name: str, arguments: dict) -> str:
        """Runs one tool. It never raises: a tool that fails answers {"error": "<a word from a fixed list>"}.

        The reads of the subscriptions in one call take at most `read_seconds` in all. A call that has used that reads no further subscription (what it has read stays in the
        caches, so a later call goes on from there), and its answer says how many were not read (`not_read`) while a note says which."""
        with self._lock:
            self._calls += 1
            self._began, self._timed, self._skipped, self._read = self.monotonic(), True, {}, None
            self._listed_seconds, self._late_lists, self._saved = 0.0, set(), None
            try:
                answer = self._answer(name, arguments)
            finally:
                self._timed = False
                self._late_lists = set()
            if self._skipped:
                self.notes.append(f"{_logged_name(name)}: the time for reading the subscriptions ({self.read_seconds:g} seconds in one call) was used up, so "
                                  f"{len(self._skipped)} were not read in this call ({some(list(self._skipped))})")
            try:
                text = _dump(answer)
            except (TypeError, ValueError):  # a value that JSON cannot hold, such as a number that is not finite
                self.notes.append(f"{_logged_name(name)}: the answer could not be written")
                answer = {"error": "failed"}
                text = _dump(answer)
            if len(text) > result_cap(name):
                answer = {"error": "too-large"}
                text = _dump(answer)
            self.log.append({"name": _logged_name(name), "arguments": _logged_arguments(arguments), "ok": "error" not in answer, "chars": len(text),
                             **({"read": self._read} if self._read is not None and "error" not in answer else {}), **({"saved": self._saved} if self._saved else {})})
            return text

    def _answer(self, name: object, arguments: object) -> dict:
        if self._calls > MAX_CALLS + self.extra_calls:
            return {"error": "limit"}
        tool = TOOLS.get(name) if isinstance(name, str) else None
        if tool is None:
            return {"error": "unknown-tool"}
        try:
            if self._pending:
                self._prefetch_lists(())
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

    def _late(self, extra: float = 0.0) -> bool:
        """True when the call that is running has used the time that its reads of the subscriptions may take (read_seconds). The reads of the platform's lists of property paths are not a part of
        that time (they have their own: LIST_SECONDS): `extra` is the time of the block of them that is running."""
        return self._timed and self.monotonic() - self._began - self._listed_seconds - extra >= self.read_seconds

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

    def _pool(self, subs: list[str], read: Callable[[str], T], late: Callable[[], bool] | None = None, skip: Callable[[str], None] | None = None) -> "dict[str, T | Failed]":
        """Reads of the subscriptions of the list, `read_workers` at a time, in the order of the list. A read is started only while the time of the call is not used up (`late`: the time of the
        reads of the subscriptions; the subscriptions that are not started are `_skipped`, and the call goes on with the ones that are running). A read that fails with an error of the reads is a
        `Failed` in its place; any other error is raised when all that were started have ended. The reads of the lists of property paths use it with a `late` and a `skip` of their own."""
        late, skip = late or self._late, skip or self._skip
        outcomes: dict[str, "T | Failed"] = {}
        queue = list(subs)
        running: dict[Future, str] = {}
        workers = max(1, self.read_workers)
        pool = ThreadPoolExecutor(max_workers=workers)
        fault: BaseException | None = None
        try:
            while queue or running:
                while queue and len(running) < workers and fault is None and not late():
                    sub = queue.pop(0)
                    running[pool.submit(self._guarded, read, sub)] = sub
                if queue and not running:
                    for sub in queue:
                        skip(sub)
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
        properties, size, said = self._typed(resource.resource_type, sub, row.get("properties"), sku)
        entry = _Entry(resource, sub, _shown(sku_word, sku.get("name")), _shown(sku_word, row.get("kindName")), _shown(region_word, resource.location.lower()), properties, size, property_list=said)
        if resource.resource_type.partition("/")[0] in self._late_lists and self._pending_count < MAX_PENDING:
            entry.raw = (row.get("properties"), sku)
            self._pending.setdefault(resource.resource_type.partition("/")[0], []).append(entry)
            self._pending_count += 1
        self._entries[key] = entry
        return entry

    def _typed(self, kind: str, sub: str, properties: object, sku: object) -> tuple[list[tuple[str, "bool | int | float | str | list"]], float, str]:
        """The typed properties of a resource by the platform's list for its type, the largest of their numbers, and the word that says why they are few (property_list): the one place where
        the properties of a resource are made."""
        listed = self._listing_of(kind, sub)
        typed = typed_properties(properties, sku, listed if isinstance(listed, Listing) else None)
        return typed, _largest(typed), listed if isinstance(listed, str) else ""

    def _listing_of(self, kind: str, sub: str) -> "Listing | str":
        """The platform's list of property paths for a resource type, or the word that says why there is none: `unavailable` when the list of its namespace could not be read (or, in this call only,
        when the call had no time to read it), `not-offered` when the platform lists no path for the type. The list of a namespace is read once in a run (`_prefetch_lists`), and kept whether
        the read worked or not."""
        namespace, _, name = kind.partition("/")
        if namespace not in self._lists:
            self._prefetch_lists([(kind, sub)])
        if namespace not in self._lists:
            return UNAVAILABLE
        found = self._lists[namespace]
        if isinstance(found, str):
            return found
        if kind not in self._listings:
            paths = found.get(name)
            self._listings[kind] = Listing(paths) if paths else NOT_OFFERED
        return self._listings[kind]

    def _read_lists(self, namespace: str, holders: list[str]) -> "dict[str, frozenset[tuple[str, ...]]] | str":
        """The platform's lists of a namespace, read with the first subscription that holds a resource of it and, when that read fails, with one other that does (a limit or a failure for one
        subscription must not decide the whole run). `unavailable` when every try failed, and that is kept for the run."""
        error: Exception | None = None
        for sub in holders[:2]:
            try:
                return self.arm.provider_paths(sub, namespace)
            except READ_ERRORS as caught:
                error = caught
        if holders:
            self._say(f"{holders[0][:8]}: the property paths of {namespace[:40]} could not be read ({str(error)[:200]})")
        return UNAVAILABLE

    def _prefetch_lists(self, wanted: "Iterable[tuple[str, str]]") -> None:
        """Reads the lists of the namespaces of (type, subscription) pairs that no read has given yet, `read_workers` at a time (`_pool`), so that the ingest of the rows of one answer finds them in
        the cache. The time of these reads is the call's own (LIST_SECONDS): a namespace that is not started in it is `_late_lists` in this call, `unavailable` for its answers, and is read by
        a later call, which types again what was ingested without it (`_settle`). More namespaces than MAX_NAMESPACES in a run are `unavailable` for good."""
        todo: list[str] = []
        for kind, sub in wanted:
            namespace = kind.partition("/")[0]
            held = self._held.setdefault(namespace, [])
            if sub and sub not in held:
                held.append(sub)
            if namespace not in self._lists and namespace not in self._late_lists and namespace not in todo:
                todo.append(namespace)
        todo += [namespace for namespace in self._pending if namespace not in self._lists and namespace not in self._late_lists and namespace not in todo]
        room = max(0, MAX_NAMESPACES - len(self._lists))
        self._lists.update((namespace, UNAVAILABLE) for namespace in todo[room:])
        todo = todo[:room]
        if not todo:
            return
        began, spent = self.monotonic(), self._listed_seconds
        outcomes = self._pool(todo, lambda namespace: self._read_lists(namespace, self._held[namespace]),
                              late=lambda: self._timed and (self._late(self.monotonic() - began) or spent + self.monotonic() - began >= LIST_SECONDS), skip=self._late_lists.add)
        self._listed_seconds += self.monotonic() - began
        for namespace, found in outcomes.items():
            self._lists[namespace] = UNAVAILABLE if isinstance(found, Failed) else found
            self._settle(namespace)

    def _settle(self, namespace: str) -> None:
        """Types again, with the list of their namespace that has been read now, the resources that a call ingested without it."""
        for entry in self._pending.pop(namespace, []):
            self._pending_count -= 1
            properties, sku = entry.raw or (None, None)
            entry.properties, entry.size, entry.property_list = self._typed(entry.resource.resource_type, entry.sub, properties, sku)
            entry.raw = None

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
        if entry.property_list:
            facts["property_list"] = entry.property_list
        if limits := self._limits_of(type_word(entry.resource.resource_type), facts["properties"].items()):
            facts["limits"] = limits
        return facts

    def _limits_of(self, kind: str | None, shown: "Iterable[tuple[str, object]]") -> dict[str, dict[str, int]]:
        """The limits of the properties that an answer shows (path, value): for each count or size that is a number and whose last key the reference page of the type bounds (cases/ranges.py),
        {"lowest": N, "highest": M} with a bound that the page does not give left out. Nothing when the toolbox has no reader, when no such number is shown (no page is read for it), for a path that the
        page does not bound, and when the page was not read: the type is counted for the one note of the run (`limits_note`), and the answer says nothing, because a page that was not read is not a type
        with no limits."""
        counts = [path for path, value in shown if isinstance(value, (int, float)) and not isinstance(value, bool) and _rank(path.rsplit(".", 1)[-1]) in COUNT_LIKE]
        if self.ranges is None or kind is None or not counts:
            return {}
        try:
            found = self.ranges.limits(kind)
        except Exception:  # noqa: BLE001 (a reader that fails is a page that was not read, and it never costs an answer)
            found = None
        if found is None:
            self._unlimited.add(kind)
            return {}
        return {path: bounds for path in counts if (known := ranges.find(found, path)) is not None and (bounds := known.bounds())}

    def limits_note(self) -> str:
        """The one note of a run about the limits that were not read: how many kinds of resource asked for a page of the documentation that was not read (cases/ranges.py), or "" when none did. The
        investigation says it once, when it ends: a note for each kind would be as many as the kinds, and the run keeps a few of its notes."""
        count = len(self._unlimited)
        return f"the documented limits of {count} kind{'' if count == 1 else 's'} of resource were not read, so no tool shows any for {'it' if count == 1 else 'them'}" if count else ""

    @staticmethod
    def _unlimit(holder: dict, path: str) -> None:
        """Takes the limits of a property out of the part of an answer that holds both, when the property was cut from it to make the answer fit."""
        held = holder.get("limits")
        if isinstance(held, dict):
            held.pop(path, None)
            if not held:
                del holder["limits"]

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
        if shown.get("limits"):
            record.setdefault("limits", {}).update(shown["limits"])
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
            rows = [(row, self._owner_of(row, subs[0] if len(subs) == 1 else None)) for row in self.arm.graph_many(subs, RESOURCES_BY_ID.format(ids=", ".join(f"'{item}'" for _, item in chunk)))]
            self._prefetch_lists((str(row.get("type") or "").lower(), owner) for row, owner in rows if owner)
            for row, owner in rows:
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

    def _load_type(self, kind: str, read: "tuple[list[dict], list[str]] | None" = None) -> None:
        """The resources of one type in every subscription, from one query of Resource Graph for all of them (`_graph`). A subscription that has none has an empty list, and one that could not be
        read has no list: it is in `_unlisted`. `read` is that query's answer when `preload` has made it ahead."""
        if all((sub, kind) in self._by_type or sub in self._unlisted for sub in self.subscriptions):
            return
        rows, failed = read if read is not None else self._graph(TYPE_RESOURCES.format(type=kind))
        self._unlisted.update(failed)
        found: dict[str, list[str]] = {sub: [] for sub in self.subscriptions if sub not in self._unlisted}
        self._prefetch_lists((str(row.get("type") or "").lower(), owner) for row, owner in ((row, self._owner_of(row)) for row in rows) if owner in found)
        for row in rows:
            owner = self._owner_of(row)
            entry = self._ingest(row, owner) if owner in found else None
            if entry is not None and entry.sub == owner and entry.key not in found[owner]:
                found[owner].append(entry.key)
        for sub, keys in found.items():
            self._by_type[(sub, kind)] = keys

    def preload(self, kinds: Iterable[object]) -> int:
        """For code and never for an agent (cases/beats.py): reads the resources of several types at the same time, so that the listings that follow find them in the caches. The questions of
        Resource Graph, one for each type, go to a pool of at most PRELOAD_WORKERS, and the workers only read: what they read is registered here, by the thread that called, in the order of the
        types, as `_load_type` registers a read of its own, so that no state of the toolbox is touched by two threads. A call of a tool holds `_lock` for as long as it runs and this holds it too,
        so that nothing runs beside it. A type that is read already, or has not the shape of one, is left alone; one that fails is left to the listing, which says why in its own words. Returns
        how many types were read; fewer than two types are not worth a pool, and are read by the listing."""
        with self._lock:
            todo = [kind for kind in dict.fromkeys(kinds) if type_word(kind) and not all((sub, kind) in self._by_type or sub in self._unlisted for sub in self.subscriptions)]
            if len(todo) < 2:
                return 0
            with ThreadPoolExecutor(max_workers=min(len(todo), PRELOAD_WORKERS)) as pool:
                asked = {kind: pool.submit(self._graph, TYPE_RESOURCES.format(type=kind)) for kind in todo}
            read: dict[str, tuple[list[dict], list[str]]] = {}
            for kind, future in asked.items():
                try:
                    read[kind] = future.result()
                except READ_ERRORS:
                    continue
            for kind in todo:
                if kind in read:
                    self._load_type(kind, read[kind])
            return len(read)
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
        if self.rotate and order == "cost":  # code's read for a beat: what no run looked at lately comes first, each group by cost and then by key; the dearest `backfill` of the type count as looked at
            looked = self.window | self.looked_at()
            flags = [n < self.backfill.get(kind, 0) or seen_hash(entry.key) in looked for n, entry in enumerate(entries)]
            entries = [entry for _, entry in sorted(zip(flags, entries), key=lambda pair: pair[0])]
        return entries, [sub for sub in self.subscriptions if sub in self._unlisted]

    def _tool_list_resources(self, args: dict) -> dict:
        kind, order, limit, offset = args["type"], args["order_by"] or "cost", args["limit"] or DEFAULT_LISTED, args["offset"] or 0
        entries, failed = self._listed(kind, order)
        page = entries[offset:offset + limit]
        page = page[:self._within_handles(page)]
        cells = [self._cells(entry) for entry in page]
        caveats = self._caveats(failed, {entry.sub for entry in entries})
        if page and page[0].property_list:
            caveats["property_list"] = page[0].property_list  # every resource of one type has the same list

        def table(count: int) -> tuple[dict, list[list], set[str]]:
            same, columns, rows, visible = _layout([(PLACEHOLDER, cell) for cell in cells[:count]])
            more = offset + count < len(entries)
            limits = self._limits_of(kind, ((name, cell[name]) for name in sorted(visible, key=_order) for cell in cells[:count] if name in cell))
            answer = {"type": kind, "total": len(entries), "offset": offset, "has_more": more, **({"next_offset": offset + count} if more else {}), **caveats,
                      **({"reads": deeper.offered(kind)} if deeper.offered(kind) else {}), **({"same": same} if same else {}), **({"limits": limits} if limits else {}), "cols": columns, "rows": rows}
            return answer, rows, visible

        count = len(page)
        answer, rows, visible = table(count)
        while len(_dump(answer)) > MAX_RESULT_CHARS and count:
            count -= 1
            answer, rows, visible = table(count)
        for row, entry, cell in zip(rows, page, cells):
            shown: dict = {"managed": cell["managed"], "properties": {name: cell[name] for name in visible if name in cell}}
            shown.update({key: cell[name] for key, name in (("cost30d", "usd30d"), ("sku", "sku"), ("kind", "kind"), ("location", "region")) if name in cell})
            shown["limits"] = {name: answer["limits"][name] for name in shown["properties"] if name in answer.get("limits", {})}
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
            plans: dict[str, tuple[mx.Plan, mx.Plan]] = {}
            resource_id, complete = self._one_of_type(kind)
            definitions: list[dict] = []
            try:
                definitions = self.arm.metric_definitions(resource_id) if resource_id else []
            except HttpError as error:
                if error.status != 400 or NO_METRICS_TEXT not in str(error).lower():
                    raise
                self._no_metrics.add(kind)
            for definition in definitions:
                name = definition.get("name")
                word = metric_word(name.get("value") if isinstance(name, dict) else None)
                plan = mx.plan_of(definition)
                # A metric that is only offered for a chosen dimension cannot be measured without one, and metric_summary names none; nor one that offers no grain or aggregation to read.
                if word is not None and plan is not None and definition.get("isDimensionRequired") is not True:
                    dimensions = [token_word(item.get("value"), 41) for item in definition.get("dimensions") or [] if isinstance(item, dict)]
                    found.setdefault(word, {"name": word, "unit": token_word(definition.get("unit"), 16), "aggregation": token_word(definition.get("primaryAggregationType"), 16),
                                            **({"dimensions": [item for item in dimensions if item][:MAX_DIMENSIONS]} if any(dimensions) else {})})
                    plans.setdefault(word, (plan, mx.plan_of(definition, True)))
            if not complete:
                return []  # no resource was found in the subscriptions that were looked at, and the others were not: nothing is remembered, a later call looks again
            self._metric_names[kind], self._plans[kind] = sorted(found.values(), key=lambda item: item["name"].lower()), plans
        return self._metric_names[kind]

    def _offers(self, kind: str | None) -> "dict[str, tuple[mx.Plan, mx.Plan]] | str":
        """What Azure Monitor offers for a resource type (the metric_names of the type): for each metric its plan by the day and by the hour, NO_METRICS for a type that has no platform
        metrics, or `unavailable` when that could not be read. A metric that the tools did not list is never measured, so no text of an argument or of an answer reaches Azure Monitor or the
        agent through it."""
        if kind is None:
            return {}
        try:
            self._names_of(kind)
        except READ_ERRORS as error:
            self.notes.append(f"the metrics that Azure Monitor offers for a type could not be read ({str(error)[:200]})")
            return "unavailable"
        return NO_METRICS if kind in self._no_metrics else self._plans.get(kind, {})

    @staticmethod
    def _plan(offer: "dict[str, tuple[mx.Plan, mx.Plan]] | str", name: str, hourly: bool) -> "mx.Plan | str":
        """The plan to read one metric of a type with, or the word that says why there is none."""
        return offer if isinstance(offer, str) else offer[name][hourly] if name in offer else "unknown-metric"

    @staticmethod
    def _asked(args: dict) -> list[str]:
        """The metric names of a call: the one in `metric` or those in `metrics`, never both and never neither."""
        if (args["metric"] is None) == (args["metrics"] is None):
            raise BadArguments("metric")
        return [args["metric"]] if args["metric"] is not None else args["metrics"]

    @staticmethod
    def _why(error: object) -> dict:
        """What a row says of a metric that was not read: `failed` for a fault of the tool, else `unavailable` with the code word of the platform's error when it gave one (never its text)."""
        code = token_word(getattr(error, "code", None), 40)
        return {"error": "failed"} if error is None else {"error": "unavailable", **({"code": code} if code else {})}

    def _tool_metric_names(self, args: dict) -> dict:
        kind, offset = args["type"], args["offset"] or 0
        names = self._names_of(kind)
        if kind in self._no_metrics:
            return {"error": NO_METRICS}
        rows = [dict(item) for item in names[offset:]]
        answer: dict = {"type": kind, "total": len(names), "offset": offset, "returned": 0, "next_offset": None, **self._unread(), "metrics": rows}
        _page(answer, rows, offset, len(names))
        return answer

    def _window(self, days: int) -> tuple[dt.datetime, dt.datetime]:
        """The closed days that a measurement looks at: from midnight `days` days ago to the midnight that starts today, in UTC."""
        end = dt.datetime.combine(self._today(), dt.time(0, 0), tzinfo=dt.timezone.utc)
        return end - dt.timedelta(days=days), end

    @staticmethod
    def _outcome(future: Future, plans: dict) -> "dict | None":
        """What the read of one resource gave: for each metric its unit and buckets, or its error (None for a fault of the tool); None when the time was used up before the read began."""
        try:
            return future.result()
        except TimeUp:
            return None
        except READ_ERRORS as error:
            return dict.fromkeys(plans, error)
        except Exception:  # a fault in one read is that resource's word, not the end of the measurement
            return dict.fromkeys(plans)

    def _read_metrics(self, targets: "list[tuple[str, str, dict[str, mx.Plan]]]", start: dt.datetime, end: dt.datetime) -> tuple[dict, list[str]]:
        """Reads the metrics of every target (a handle, its id, and the plan of each metric), `workers` resources at a time, and starts no read after the time budget is spent. Returns what was
        read, by handle and metric (the unit and the buckets at the grain of the plan, or the error), and the handles that were not read."""
        read: dict[str, dict] = {}
        queue = list(targets)
        running: dict[Future, tuple[str, dict]] = {}
        workers = max(1, self.workers)
        began = self.monotonic()

        def late() -> bool:
            return self.monotonic() - began >= self.budget_seconds

        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            while queue or running:
                while queue and len(running) < workers and not late():
                    handle, resource_id, plans = queue.pop(0)
                    running[pool.submit(self.arm.metric_reads, resource_id, plans, start, end, late)] = (handle, plans)
                left = self.budget_seconds - (self.monotonic() - began)
                if not running or left <= 0:
                    break
                done, _ = wait(running, timeout=left, return_when=FIRST_COMPLETED)
                for future in done:
                    handle, plans = running.pop(future)
                    found = self._outcome(future, plans)
                    if found is not None:
                        read[handle] = found
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return read, [handle for handle, _, _ in targets if handle not in read]

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

    @staticmethod
    def _measured(found: tuple, plan: "mx.Plan", hourly: bool) -> tuple[dict, str | None]:
        """The numbers of one read, (the unit, the buckets at the grain of the plan): the daily summary, `peak` and `p95` of the buckets that were read when `hourly`, and `read_at`, the grain,
        when it is not a day."""
        unit, points = found
        row = _summarise(points if plan.grain == mx.DAY else mx.daily(points))
        if hourly:
            row["peak"], row["p95"] = (None if value is None else _measure(value) for value in mx.fine(points, plan.level))
        if plan.grain != mx.DAY:
            row["read_at"] = plan.grain
        return row, token_word(unit, 16)

    def _tool_metric_summary(self, args: dict) -> dict:
        handles, names, days, hourly, many = args["handles"], self._asked(args), args["days"] or MAX_DAYS, args["grain"] == "hour", args["metrics"] is not None
        start, end = self._window(days)
        known = [handle for handle in handles if handle in self.handles]
        kinds = {handle: type_word(self.handles[handle].resource_type) for handle in known}
        offers = {kind: self._offers(kind) for kind in set(kinds.values())}
        plans = {handle: {name: self._plan(offers[kinds[handle]], name, hourly) for name in names} for handle in known}
        refusals = {plan for each in plans.values() for plan in each.values()}
        if known and len(refusals) == 1 and refusals <= {"unknown-metric", NO_METRICS}:
            return {"error": refusals.pop()}  # no type of a handle offers a metric that was asked for, or none has platform metrics
        echoed = [name for name in names if any(isinstance(offer, dict) and name in offer for offer in offers.values())]  # a name is echoed only when Azure Monitor offers it for a type of a handle
        read, unread = self._read_metrics([(handle, self.handles[handle].resource_id, {name: plan for name, plan in plans[handle].items() if isinstance(plan, mx.Plan)})
                                           for handle in known if any(isinstance(plan, mx.Plan) for plan in plans[handle].values())], start, end)
        skipped, rows, units = set(unread), [], {}
        for handle in handles:
            if handle not in self.handles:
                rows.append({"handle": handle, "error": "unknown-handle"})
                continue
            said: set[tuple[str, str | None]] = set()
            for name in names:
                plan = plans[handle][name]
                if isinstance(plan, str):
                    if many and plan == "unknown-metric" and name not in echoed:
                        continue  # no type of a handle offers it: it is counted in unknown_metrics and never named
                    shown = name if many and plan == "unknown-metric" else None
                    if (plan, shown) not in said:
                        said.add((plan, shown))
                        rows.append({"handle": handle, **({"metric": shown} if shown else {}), "error": plan})  # a type that has no metrics or could not be asked is told once, whatever the names
                elif handle in read:
                    result = read[handle].get(name)
                    head = {"handle": handle, **({"metric": name} if many else {})}
                    if isinstance(result, tuple):
                        row, units[(handle, name)] = self._measured(result, plan, hourly)
                        rows.append({**head, **row})
                    else:
                        rows.append({**head, **self._why(result)})
        answer: dict = {"days": days, "partial": False, "summary": {}, "results": rows, **({} if many else {"unit": None})}
        if echoed:
            answer = {**({"metrics": echoed} if many else {"metric": echoed[0]}), **answer}
        if many and len(echoed) < len(names):
            answer["unknown_metrics"] = len(names) - len(echoed)

        def refresh() -> None:
            found: dict[str, str] = {}
            for row in rows:
                if "error" not in row and units.get((row["handle"], row.get("metric", names[0]))):
                    found.setdefault(row.get("metric", names[0]), units[(row["handle"], row.get("metric", names[0]))])
            answer.pop("units", None)
            if many:
                answer.update({"units": found} if found else {})
            else:
                answer["unit"] = found.get(names[0])
            answer["partial"] = bool(skipped)
            ok = [row for row in rows if "error" not in row]  # the measurements whose numbers are in the answer
            answer["summary"] = {name: _tally((_bucket(row) for row in ok if row["metric"] == name), days) for name in echoed} if many else _tally(map(_bucket, ok), days)
            if skipped:
                answer["unread"] = [handle for handle in handles if handle in skipped]

        refresh()
        while len(_dump(answer)) > result_cap("metric_summary") and rows:
            last = rows[-1]["handle"]
            skipped.add(last)
            rows[:] = [row for row in rows if row["handle"] != last]
            refresh()
        for row in rows:
            if "error" not in row:
                name = row.get("metric", names[0])
                self._record_metric(row["handle"], name, row, days, units.get((row["handle"], name)))
                self._count_read(kinds[row["handle"]], row["handle"], name, days, row)
        return answer

    def _tool_measure(self, args: dict) -> dict:
        kind, names, days, hourly, offset = args["type"], self._asked(args), args["days"] or MAX_DAYS, args["grain"] == "hour", args["offset"] or 0
        many = args["metrics"] is not None
        limit = args["limit"] or max(1, DEFAULT_LISTED // len(names))
        entries, failed = self._listed(kind, "cost")
        page = entries[offset:offset + limit]
        offer = self._offers(kind) if page else {}  # a name is echoed only when Azure Monitor offers it for the type, and that is read only when there is a resource to measure
        if isinstance(offer, str):
            return {"error": offer}
        plans = {name: offer[name][hourly] for name in names if name in offer}
        if page and not plans:
            return {"error": "unknown-metric"}
        page = page[:self._within_handles(page)]
        handles = [self._show(entry, {}) for entry in page]  # every resource of the page is named in the answer: as a row, as failed or as unread
        start, end = self._window(days)
        read, unread = self._read_metrics([(handle, entry.resource.resource_id, plans) for handle, entry in zip(handles, page)], start, end)
        costs = {handle: self._cost_total(entry) for handle, entry in zip(handles, page)}
        priced = any(cost is not None for cost in costs.values())
        summaries: dict[str, dict[str, tuple[dict, str | None]]] = {}
        broken: list[str] = []
        codes: set[str] = set()
        for handle in handles:
            for name, result in (read.get(handle) or {}).items():
                if isinstance(result, tuple):
                    summaries.setdefault(handle, {})[name] = self._measured(result, plans[name], hourly)
                else:
                    if handle not in broken:
                        broken.append(handle)
                    codes.add(self._why(result).get("code", ""))
        codes.discard("")
        read_at = any("read_at" in found[0] for each in summaries.values() for found in each.values())
        columns = ["handle", *(["metric"] if many else []), *(["usd30d"] if priced else []), "total", "max", "avg", "days_with_data", *(["peak", "p95"] if hourly else []),
                   *(["read_at"] if read_at else [])]
        caveats = self._caveats(failed, {entry.sub for entry in entries})
        more = offset + len(page) < len(entries)
        skipped = set(unread)
        counted = {name: dict(self._reads.get((kind, name, days), {})) for name in names}  # what the pages and the calls before this one showed

        def rows_of(handle: str) -> list[list]:
            cost = costs[handle]
            return [[handle, *([name] if many else []), *([None if cost is None else _cents(cost)] if priced else []), row["total"], row["max"], row["average"], row["days_with_data"],
                     *([row["peak"], row["p95"]] if hourly else []), *([row.get("read_at")] if read_at else [])]
                    for name in plans if name in summaries[handle] for row in [summaries[handle][name][0]]]

        def answer() -> dict:
            kept = [handle for handle in handles if handle in summaries and handle not in skipped]
            found = {name: next((summaries[handle][name][1] for handle in kept if name in summaries[handle] and summaries[handle][name][1]), None) for name in plans}
            seen = {name: {**counted[name], **{handle: _bucket(summaries[handle][name][0]) for handle in kept if name in summaries[handle]}} for name in names}
            said: dict = {}
            if page:  # the names and their units are echoed only when Azure Monitor offers them for the type
                said.update({"metrics": list(plans), "units": {name: unit for name, unit in found.items() if unit}} if many else {"metric": names[0]})
                if many and len(plans) < len(names):
                    said["unknown_metrics"] = len(names) - len(plans)
            if not many and any(found.values()):
                said["unit"] = next(iter(found.values()))
            if not said.get("units", True):
                del said["units"]
            tally = {name: _tally(seen[name].values(), days) for name in names if name in plans or counted[name]} if many else _tally(seen[names[0]].values(), days)
            return {"type": kind, **said, "days": days, "partial": bool(skipped), "total": len(entries), "offset": offset, "has_more": more,
                    **({"next_offset": offset + len(page)} if more else {}), **caveats, **({"failed": broken} if broken else {}), **({"failed_codes": sorted(codes)} if codes else {}),
                    **({"unread": [handle for handle in handles if handle in skipped]} if skipped else {}), "summary": tally, "cols": columns,
                    "rows": [row for handle in kept for row in rows_of(handle)]}

        built = answer()
        while len(_dump(built)) > result_cap("measure") and any(handle in summaries and handle not in skipped for handle in handles):
            skipped.add(next(handle for handle in reversed(handles) if handle in summaries and handle not in skipped))
            built = answer()
        for handle, entry in zip(handles, page):
            if handle in summaries and handle not in skipped:
                if costs[handle] is not None:
                    self._show(entry, {"cost30d": _cents(costs[handle])})
                for name, (row, unit) in summaries[handle].items():
                    self._record_metric(handle, name, row, days, unit)
                    self._count_read(kind, handle, name, days, row)
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
                    self._record_advice(row["handle"], advice)
        return answer

    def _record_advice(self, handle: str, advice: _Advice) -> None:
        """Keeps an Advisor item that an answer showed for a resource, as the evidence that the investigation reads (the saving in dollars only when Advisor says that it is in dollars)."""
        seen = self.evidence.setdefault(handle, {}).setdefault("advisor", [])
        facts = advice.facts
        month = _money(advice.annual / 12) if advice.annual is not None and advice.currency == "USD" else None  # a saving is in dollars only when Advisor says so
        item = {"savingUsdMonth": month, "annualSavings": advice.annual, "currency": advice.currency, "impact": facts["impact"], "typeId": facts["type_id"],
                "term": facts["term"], "lookback": facts["lookback"], "reservedType": facts["reserved_type"], "sku": facts["sku"]}
        if item not in seen:
            seen.append(item)

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
            self._unlimit(answer, answer["properties"].popitem()[0])
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
    def _fit(answer: dict, lists: "list[tuple[list | dict, dict, str]]", cap: int = MAX_RESULT_CHARS) -> None:
        """Takes rows off the longest of the lists of an answer (a dict loses its last item) until it fits under the cap, and counts what it left out under `<key>_not_shown` in the dict that holds the list."""
        while len(_dump(answer)) > cap:
            longest = max(((rows, holder, key) for rows, holder, key in lists if rows), key=lambda item: len(item[0]), default=None)
            if longest is None:
                raise TooLarge()
            rows, holder, key = longest
            gone = rows.popitem() if isinstance(rows, dict) else rows.pop()
            if key == "properties":
                Toolbox._unlimit(holder, gone[0])
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
        if kind in self._no_metrics:
            return {"error": NO_METRICS}
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
        plan = self._plans[kind][metric][0]
        unit, series = self.arm.metrics_split(entry.resource.resource_id, metric, dimension, start, end, top=limit, plan=plan)
        labels: dict[str, str] = {}
        found: list[tuple[object, dict, _Entry | None]] = []
        for value, points in series:
            summary = _summarise(points if plan.grain == mx.DAY else mx.daily(points))
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

    def _meter_handle(self, line: Meter) -> str | None:
        """The handle of a meter of a scope: the same one whenever it is shown again in the run. None when the handles are used up. The register keeps the longest window that was read for it: a
        later, shorter read does not replace it (the saving of a change counts only a meter read over the full window)."""
        key = (line.scope, line.service, line.words)
        if key not in self._meter_keys:
            if len(self._meter_keys) >= HANDLE_LIMIT:
                return None
            self._meter_keys[key] = f"m{len(self._meter_keys) + 1}"
        handle = self._meter_keys[key]
        held = self.meters.get(handle)
        if held is None or held.days < line.days:
            self.meters[handle] = line
        return handle

    def _meters_for(self, entry: _Entry, days: int) -> "tuple[list, dict] | Failed":
        """What one resource is billed for, meter by meter, for each of the last `days` closed days, as Cost Management gave it, read once in a run (the read of a handle that cost_meters makes is this one)."""
        today = self._today()
        start, end = today - dt.timedelta(days=days), today - dt.timedelta(days=1)
        return self._once(("meters", entry.sub, entry.resource.handle, None, days), lambda: (self.arm.meter_days(entry.sub, start, end, ("ResourceId", (entry.resource.resource_id,)), None), {}))

    def _tool_cost_meters(self, args: dict, shown: int = MAX_LISTED) -> dict:
        handle, kind, service, days, offset = args["handle"], args["type"], args["service"], args["days"] or MAX_DAYS, args["offset"] or 0
        if (handle is None) == (kind is None):
            raise BadArguments("handle")
        today = self._today()
        start, end = today - dt.timedelta(days=days), today - dt.timedelta(days=1)
        unlisted: list[str] = []
        if handle is not None:
            entry = self._entry(handle)
            if entry.part_of is not None:
                raise NotOffered(handle)  # a part of a resource is billed with the resource, and no cost line is its own
            subs, where, scope = [entry.sub], ("ResourceId", (entry.resource.resource_id,)), handle
        else:
            self._load_type(kind)
            unlisted = [sub for sub in self.subscriptions if sub in self._unlisted]
            subs, where, scope = sorted({item.sub for item in self._entries_of(kind)}, key=list(self.subscriptions).index), ("ResourceType", (kind,)), kind
        also = ("ServiceName", (service,)) if service else None

        def read(sub: str) -> "tuple[list, dict] | Failed":
            if handle is not None and service is None:
                return self._meters_for(entry, days)
            return self._once(("meters", sub, scope, service, days), lambda: (self.arm.meter_days(sub, start, end, where, also),
                                                                            {} if handle is not None else self.arm.meter_resources(sub, start, end, where, also)))

        ready = [sub for sub in subs if ("meters", sub, scope, service, days) in self._kept]  # a read that is kept is in the answer whatever the time: it costs none
        outcomes = self._pool([sub for sub in subs if sub not in ready], read)
        outcomes.update({sub: read(sub) for sub in ready})
        rows: list[tuple] = []
        carriers: dict[tuple[str, ...], int] = {}
        failed: list[str] = []
        dollars: list[str] = []
        last: Exception | None = None
        for sub in subs:
            found = outcomes.get(sub)
            if isinstance(found, Failed):
                self._note(sub, "what is billed", found.error)
                failed.append(sub)
                last = found.error
            elif found is not None and any(row[4] != "USD" for row in found[0]):
                self._say(f"{sub[:8]}: the cost is not in US dollars, so cost_meters does not show it")
                dollars.append(sub)
            elif found is not None:
                rows.extend(found[0])
                for words, count in found[1].items():
                    carriers[words] = carriers.get(words, 0) + count
        if last is not None and len(failed) == len([sub for sub in subs if sub in outcomes]):
            return self._why(last)  # unavailable with the platform's code word, never its text: the notes keep what the History needs
        folded = fold((day, words, cost, quantity) for day, words, cost, quantity, _ in rows)
        total = math.fsum(spent for _, spent, _ in folded.values())
        lines = [Meter(scope, service, words, used, spent, daily, None if handle is not None else carriers.get(words, 0), start, days)
                 for words, (used, spent, daily) in sorted(folded.items(), key=lambda item: (-item[1][1], item[0]))]
        said: dict = {}
        if failed or unlisted:
            self._listing(said, "unavailable", failed + [sub for sub in unlisted if sub not in failed])
        if dollars:
            said["costs"] = NOT_DOLLARS
            if len(dollars) < len(subs):
                self._listing(said, "not_in_dollars", dollars)
        said.update(self._unread())
        window = lines[offset:offset + shown]
        cells = []
        for line in window:
            numbers = shape(line, today)
            cells.append({"meter": PLACEHOLDER_METER if line.resources != 0 else None, **{name: _shown(meter_word, word) for name, word in zip(METER_WORDS, line.words)},
                          "quantity": _measure(line.quantity), "usd": _cents(_money(line.usd)), "share": round(line.usd / total, 4) if total > 0 else None, "days": numbers["days"],
                          **{name: None if numbers[name] is None else _cents(_money(numbers[name])) for name in ("avg_day", "min_day", "max_day")},
                          "cv": None if numbers["cv"] is None else round(numbers["cv"], 3), "first_day": numbers["first_day"], "last_day": numbers["last_day"],
                          **({"resources": line.resources} if handle is None else {})})
        same = {name: cells[0][name] for name in METER_WORDS if len(cells) > 1 and cells[0][name] is not None and all(cell[name] == cells[0][name] for cell in cells)}
        columns = [name for name in (*METER_COLUMNS, *(["resources"] if handle is None else [])) if name not in same]
        table = []
        for cell in cells:
            values = [cell.get(name) for name in columns]
            while len(values) > 1 and values[-1] is None:
                values.pop()
            table.append(values)
        answer: dict = {**({"handle": handle} if handle is not None else {"type": kind}), **({"service": service} if service else {}), "window_days": days, "usd_total": _cents(_money(total)),
                        "meters": len(lines), "offset": offset, "returned": 0, "next_offset": None, **said, **({"same": same} if same else {}), "cols": columns, "rows": table}
        _page(answer, table, offset, len(lines))
        for row, line, cell in zip(table, window, cells):
            if cell["meter"] is not None:
                row[0] = self._meter_handle(line)
        return answer

    def _price_handle(self, line: prices.Line, old: int | None = None) -> str | None:
        """The handle of a line of the price list that has one price: the same one whenever the line is shown again in the run, and None when the handles are used up. A line with price steps has none, so
        that no code can take the price of its first step for the price of a quantity. `old` is how many days old the copy was that showed it (`Book.aged`): it is kept with the handle, and a later ask that
        showed the line from a read of the list or from a copy of today takes it away."""
        if line.tiers > 1:
            return None
        key = (line.service, line.product, line.sku, line.meter, line.unit, line.region)
        if key not in self._price_keys:
            if len(self._price_keys) >= HANDLE_LIMIT:
                return None
            self._price_keys[key] = f"p{len(self._price_keys) + 1}"
        handle = self._price_keys[key]
        self.prices[handle] = line
        self._dated(handle, old)
        return handle

    def _dated(self, handle: str, old: int | None) -> None:
        """Keeps how old the copy was that showed a handle, or forgets it when the handle was shown from a read of the list or from a copy of today (`old` is None)."""
        if old is not None:
            self.ages[handle] = old
        else:
            self.ages.pop(handle, None)

    @staticmethod
    def _ended(book: prices.Book) -> dict:
        """What an answer says of a read that a failure cut short after some pages: `ended`, and the platform's code word for the failure when it gave one (never its text)."""
        if book.error is None:
            return {}
        code = token_word(getattr(book.error, "code", None), 40)
        return {"ended": "unavailable", **({"code": code} if code else {})}

    def _copy(self, key: tuple, fresh: bool) -> "prices.Book | None":
        """The price book's copy of a read of the list for `key` (service, region, product or None), and the run keeps it: None when the store has no book (the Table store has one, the memory store of the
        tests has none), has no copy, has one that is broken or not complete, has one that is not younger than FRESH_DAYS (`fresh`) or STALE_DAYS, or has one that was written more than a day ahead of
        the clock of the run (a copy of the future would count as fresh for ever, and a day between two clocks is no reason to refuse one). It never raises."""
        get = getattr(self.memory, "book_get", None)
        if get is None:
            return None
        service, region, scope = key
        try:
            record = get(service, region, scope or "")
            if record is None or not record.complete or (record.service, record.region, record.product) != (service, region, scope or ""):
                return None
            age, lines = self._moment() - parse(record.read_at), prices.unpack(service, record.lines, record.count)
        except Exception:  # noqa: BLE001 (the book never costs a call its answer)
            return None
        if not lines or not (-dt.timedelta(days=1) <= age < dt.timedelta(days=prices.FRESH_DAYS if fresh else prices.STALE_DAYS)):
            return None
        book = prices.Book(lines, True, None, "book", max(0, age.days))
        if not self.trial or len(lines) <= TRIAL_LINES:
            self._books[key] = book  # the copy answers the rest of the run
        return book

    def _keep(self, key: tuple, book: "prices.Book") -> None:
        """Writes a complete read of the list to the price book, when the store has one. A write that fails is a note and never costs a call its answer."""
        put = getattr(self.memory, "book_put", None)
        if put is None or not book.complete or not book.lines:
            return
        service, region, scope = key
        try:
            put(PriceBookRecord(service, region, scope or "", stamp(self._moment()), prices.pack(book.lines), len(book.lines)))
        except Exception as error:  # noqa: BLE001 (a write that fails never costs a call its answer)
            self.notes.append(f"price_alternatives: the price book could not keep this read ({str(error)[:200]})")

    def _tried(self, key: tuple, status: int, took: float, asked: float | None) -> None:
        """One line of the History for a try that reached the price list (events.PRICE_KINDS): typed words and numbers only, and never an address."""
        if self.emit is not None:
            service, region, scope = key
            try:
                self.emit("prices.read", service=service, region=region, **({"product": scope} if scope else {}), status=status, ms=round(took * 1000), **({"retryAfter": round(asked, 1)} if asked is not None else {}))
            except Exception:  # noqa: BLE001 (a line of the History never costs a call its answer)
                pass

    def _read_list(self, key: tuple, seconds: float, room: float, gap: float = 0.0) -> "prices.Book | Failed":
        """One read of the price list, for a call of a tool and for the warm-up: it waits as the Hold of the run allows (`room` is the longest wait that the caller can afford, `gap` the least pause between
        two of its requests), tells the History of each try, and writes a complete read to the price book."""
        service, region, scope = key
        book = self._guard(lambda: prices.read(self.arm.client, service, region, scope, self.monotonic, seconds, self._hold, room, lambda *tried: self._tried(key, *tried), gap))
        if isinstance(book, prices.Book):
            self._keep(key, book)
        return book

    def _warm_keys(self) -> list[tuple]:
        """The (service, region, product) of the dearest meters of the last 30 days, for the warm-up. The cost lines that the run holds (the Watch read them and the same client keeps them) say which resources cost
        most, and they hold no meters: one query for each subscription that has some of the WARM_RESOURCES dearest names what they were billed for, by the category and the subcategory of the meter, and the region
        of a resource is the region of its meters. The WARM_PRODUCTS dearest meters that have a product give the keys, each once. A meter with no product would ask for a whole service, which is up to five requests."""
        subs = [sub for sub in self.subscriptions if sub not in self._unlisted]
        self._prefetch_costs(subs)
        ranked = sorted(((sum(lines.values()), key, sub) for sub in subs if (costs := self._costs.get(sub)) is not None for key, lines in costs.by_resource.items() if key), reverse=True)[:WARM_RESOURCES]
        self._resolve_quietly([key for _, key, _ in ranked])
        wanted: dict[str, list[str]] = {}
        for _, key, sub in ranked:
            if key in self._entries:
                wanted.setdefault(sub, []).append(self._entries[key].resource.resource_id)
        today = self._today()
        start, end = today - dt.timedelta(days=MAX_DAYS), today - dt.timedelta(days=1)
        meters = []
        for sub, rows in self._pool(list(wanted), lambda sub: self.arm.meter_totals(sub, start, end, tuple(wanted[sub]))).items():
            if isinstance(rows, Failed):
                self._note(sub, "what the dearest resources are billed for", rows.error)
                continue
            for key, category, subcategory, amount, code in rows:
                entry = self._entries.get(key)
                region = prices.region_of(entry.location) if entry is not None and entry.part_of is None and entry.location != OTHER else None
                service, product = meter_word(category), meter_word(subcategory)
                if code == "USD" and amount > 0 and service and product and region:
                    meters.append((-amount, service, region, product))
        return list(dict.fromkeys(meter[1:] for meter in sorted(meters)[:WARM_PRODUCTS]))

    def warm_prices(self, seconds: float = WARM_SECONDS) -> tuple[int, int, int] | None:
        """For code (cases/investigate.py), before the first beat, and never for an agent: reads the public price list for the products of the dearest meters of the estate (`_warm_keys`) that the price book
        does not hold fresh, one read at a time with WARM_GAP seconds between two requests, so that the book has them when the questions come. A list that asks to wait is waited for up to WARM_WAIT
        seconds, and the whole of it, the reads for the products included, ends after `seconds`. It ends at once when the list says no: no answer at all, or a 429 that a wait did not change or that
        asked for more than the warm-up may wait (the list is not asked again, and the questions of the run read it as they need). It makes no call of a tool of a run and no model call, and never raises.
        (products read, products that the book held fresh, products not read: the list could not be read or the time ran out), or None when the store has no book."""
        if getattr(self.memory, "book_get", None) is None or getattr(self.memory, "book_put", None) is None:
            return None
        client = self.arm.client
        before, limit = client.deadline, client.monotonic() + seconds
        client.deadline = limit if before is None else min(limit, before)  # the reads of the warm-up end with it, whatever they wait for
        read = fresh = made = 0
        keys: list[tuple] = []
        try:
            with self._lock:
                stop = self.monotonic() + seconds
                keys = self._warm_keys()
                for key in keys:
                    if self._copy(key, True) is not None:
                        fresh += 1
                        continue
                    pause = max(WARM_GAP if made else 0.0, self._hold.until - self.monotonic())
                    left = stop - self.monotonic() - pause
                    if left < 2.0:
                        break  # no time for the wait and a try
                    if pause > 0:
                        client.sleep(pause)
                    spare = min(prices.SECONDS, left / 2)
                    book = self._read_list(key, spare, min(WARM_WAIT, left - spare), WARM_GAP)
                    made += 1
                    if isinstance(book, prices.Book):
                        read += int(book.complete and bool(book.lines))  # a list with no line for these words gives the book nothing
                    else:
                        self._fail("the price book", "the price list", book)
                    if getattr(book.error, "status", None) in (0, 429):
                        break  # no answer at all, or the list says no: after the wait that it asked for, or for a wait that is more than the warm-up takes
        except Exception as error:  # noqa: BLE001 (a warm-up never fails the run)
            self.notes.append(f"the price book could not be warmed ({type(error).__name__})")
        finally:
            client.deadline = before
        return read, fresh, len(keys) - read - fresh

    def _tool_price_alternatives(self, args: dict) -> dict:
        name, within, offset = args["meter"], args["within"] or "product", args["offset"] or 0
        held = self.meters.get(name)
        if held is None:
            raise UnknownHandle(name)
        entry = self._by_handle.get(held.scope)
        _, subcategory, meter, _, _, unit = held.words
        service, product = meter_word(held.words[0]), meter_word(subcategory)
        region = prices.region_of(entry.location) if entry is not None and entry.part_of is None and entry.location != OTHER else None
        if not service or not meter_word(meter) or not meter_word(unit) or region is None:
            raise NotOffered(name)  # a meter of a whole type has no region, and a word that is no word of the platform is never sent anywhere
        scope = product if within == "product" else None
        key = (service, region, scope)
        book = self._books.get(key)
        new = book is None  # no answer for this key in this run yet: a fresh copy of the price book, then the list, then an old copy of the book
        if new:
            book = self._copy(key, True) or self._prices_down
        if book is None and self.trial and len(self._trials) >= 2:
            book = self._trials[-1]  # two reads that code made did not get the list: code asks no more, and the Investigator's own call is not held by it
        if book is None:
            if sum(len(held_book.lines) for held_book in self._books.values() if isinstance(held_book, prices.Book)) >= prices.MAX_HELD:
                self.notes.append(f"price_alternatives: the run holds {prices.MAX_HELD} prices of the list already, and the app keeps no more")
                return {"error": "unavailable"}
            seconds = min(prices.SECONDS, self.read_seconds)
            book = self._read_list(key, seconds, min(prices.WAIT, max(0.0, self.read_seconds - seconds)))
            if isinstance(book, prices.Book):
                self._trials.clear()  # the host answered, to the Investigator or to code: the failures of the trials before it say nothing of the next one
            waiting = isinstance(book, Failed) and getattr(book.error, "retry_after", None) is not None  # the list asked to wait: the Hold of the run keeps its time, and it is asked again when that has passed
            if not self.trial:
                if not waiting:
                    self._books[key] = book
                if isinstance(book, Failed) and getattr(book.error, "status", None) == 0:
                    self._prices_down = book  # no answer at all: the host is not asked again in this run
                elif isinstance(book, prices.Book) and book.error is not None:
                    self.notes.append(f"price_alternatives: the price list was read in part only ({str(book.error)[:200]})")
            elif isinstance(book, prices.Book) and book.complete and len(book.lines) <= TRIAL_LINES:
                self._books[key] = book  # a whole list of the size of a product: the Investigator's own call for it is answered from it
            elif isinstance(book, Failed) and not waiting:
                self._trials.append(book)
        cut = book.error if isinstance(book, prices.Book) else None  # a read that a failure cut short after some pages is not whole: an old copy of the whole list serves better
        if new and (isinstance(book, Failed) or cut is not None) and (old := self._copy(key, False)) is not None:
            self._fail("price_alternatives", "the price list", book if isinstance(book, Failed) else Failed(cut))
            self.notes.append(f"price_alternatives: a copy of the price book, {old.age} days old, is shown instead")
            book = old
        if isinstance(book, Failed):
            self._fail("price_alternatives", "the price list", book)
            return self._why(book.error)
        same = sorted((line for line in book.lines if line.unit == unit), key=lambda line: (line.tiers > 1, line.usd, line.product, line.sku, line.meter, line.region))
        current, how = prices.match(book.lines, subcategory, meter, unit, region)
        paid = held.usd / held.quantity if held.usd > 0 and held.quantity > 0 else None
        ratio = round(paid / current.usd, 4) if current is not None and paid is not None and current.usd > 0 and current.tiers == 1 else None
        window = same[offset:offset + MAX_LISTED]
        cells = [[PLACEHOLDER_PRICE, _shown(meter_word, line.product), _shown(meter_word, line.sku), _shown(meter_word, line.meter), _measure(line.usd),
                  "global" if line.region == prices.GLOBAL else _shown(region_word, line.region), line.tiers if line.tiers > 1 else None] for line in window]
        shared, columns, table = prices.layout(("price", "product", "sku", "meter", "usd", "region", "steps"), cells)
        answer: dict = {"meter": name, "service": service, "region": entry.location, "within": "product" if scope else "service", "unit": _shown(meter_word, unit), "match": how, "lines": len(same),
                        "other_units": len(book.lines) - len(same), "complete": book.complete, "source": book.source, **({"age_days": book.age} if book.source == "book" else {}),
                        **self._ended(book), "offset": offset, "returned": 0, "next_offset": None, **({"same": shared} if shared else {}), "cols": columns, "rows": table}
        if current is not None:
            answer["current"] = {"line": PLACEHOLDER_PRICE, "retail": _measure(current.usd), **({"paid": _measure(paid)} if paid is not None else {}), "rate_ratio": ratio,
                                 **({"steps": current.tiers} if current.tiers > 1 else {})}
        _page(answer, table, offset, len(same))
        aged = book.aged  # how old the copy is that shows these prices, when it is at least a day: kept with the handles, for the owner
        shown: set[str] = set()
        for row, line in zip(table, window):
            row[0] = self._price_handle(line, aged)
            if row[0] is not None:
                shown.add(row[0])
        if current is not None:
            answer["current"]["line"] = self._price_handle(current, aged)
            if answer["current"]["line"] is not None:
                shown.add(answer["current"]["line"])
        self._keep_prices(name, shown, current, how, aged)
        for other, kin in self.meters.items():  # the prices of a product in a unit are the prices of every meter of the resource with the same service, product and unit, each with its own line
            if other != name and kin.scope == held.scope and (kin.words[0], kin.words[1], kin.words[5]) == (held.words[0], subcategory, unit):
                own, found = prices.match(book.lines, subcategory, kin.words[2], unit, region)
                handle = self._price_handle(own, aged) if own is not None else None
                self._keep_prices(other, shown | {handle} if handle is not None else shown, own, found, aged)
        return answer

    def _keep_prices(self, name: str, shown: set[str], current: "prices.Line | None", how: str, aged: int | None) -> None:
        """What an ask leaves in the registers for the meter `name`: the price handles that were shown for it, and the list price of its own line, with the age of the copy that showed it, when the line has one price."""
        self.offers.setdefault(name, set()).update(shown)
        if current is not None and current.tiers == 1:
            self.retail[name] = current.usd
            self._dated(name, aged)
        elif how != "none":  # this ask found the line and it has steps, or found lines that disagree: the list says that the meter has no one list price. A line that this ask did not find says nothing (a cap may have cut the read before it)
            self.retail.pop(name, None)
            self.ages.pop(name, None)

    # -- what a resource refers to and what refers to it ----------------------------------------------------------------------------------------
    def _load_edges(self) -> nb.Edges:
        """The references of the estate, read once in a run, a page at a time (cases/neighbors.py). Resource Graph is asked for the subscriptions of the run that no earlier listing gave up on, all at once; when it
        answers an error or a limit (a status from 400) they are asked one at a time, and one that cannot be read is named and not asked again. A call that has no time left ends, and the next one goes on from
        the page where this one ended, so no page is read twice. When no subscription can be read the error is raised."""
        state = self._edges
        if state is None:
            subs = [sub for sub in self.subscriptions if sub not in self._unlisted]
            state = self._edges = nb.Edges([subs] if subs else [])
        while state.todo and not self._late():
            group, skip = state.todo[0]
            if state.pages >= nb.MAX_PAGES:
                self.notes.append(f"the references of the estate need more than {nb.MAX_PAGES} pages of Resource Graph, and the app reads no more")
                state.failed += [sub for item, _ in state.todo for sub in item]
                state.todo.clear()
                break
            try:
                rows, skip = self.arm.graph_page(group, nb.QUERY, skip, nb.PAGE)
            except HttpError as error:
                if not 400 <= error.status < 600:
                    raise
                if len(group) > 1:
                    state.todo[0:1] = [[[sub], None] for sub in group]
                    continue
                self._note(group[0], "the references", error)
                state.failed.append(group[0])
                state.error = state.error or error
                state.todo.pop(0)
                if error.status == 429:
                    state.failed += [sub for item, _ in state.todo for sub in item]
                    state.todo.clear()
                    self.notes.append("the limit of Resource Graph holds, so the other subscriptions were not asked")
                continue
            state.pages += 1
            state.add(rows)
            if skip:
                state.todo[0][1] = skip
            else:
                state.todo.pop(0)
        if not state.todo and not state.done:
            state.finish()
        if state.subs and len(state.failed) == len(state.subs):
            raise state.error or HttpError(0, "no subscription could be read for the references")
        return state

    @staticmethod
    def _state_of(entry: _Entry) -> "tuple[str, bool | int | float | str] | None":
        """The first property of a resource whose key ends in State, Status or Code, other than the provisioning state, with its value (the first of them when the items of a list differ)."""
        for path, value in entry.properties:
            leaf = path.rsplit(".", 1)[-1]
            if leaf != "provisioningState" and _rank(leaf) <= SUFFIXES.index("Code"):
                return path, value[0] if isinstance(value, list) else value
        return None

    def _usd_of(self, key: str) -> float | None:
        sub = self._sub_of(key)
        costs = self._costs_of(sub) if sub else None
        return None if costs is None else _money(sum(costs.by_resource.get(key, {}).values()))

    def _links(self, state: nb.Edges, links: "list[tuple[int, str]]", offset: int) -> tuple[dict, list, list]:
        """One side of the answer of neighbors: the resources that a list of links joins, the dearest first, as a table, and a row of count and cost for each type and relation when there are more
        than FAN_IN of them. Returns the block, its rows, and for each row the entry that it stands for (the handle is given once the rows that fit are known)."""
        found = [(state.names[number], relation) for number, relation in links]
        self._prefetch_costs(sub for sub in (self._sub_of(key) for key, _ in found) if sub)
        priced = [(key, relation, self._usd_of(key)) for key, relation in found]
        ordered = sorted(priced, key=lambda item: (-(item[2] or 0.0), type_of_id(item[0]) or "", item[1], item[0]))
        page = ordered[offset:offset + NEIGHBOR_ROWS]
        self._resolve_quietly([key for key, _, _ in page])
        entries = [self._entries.get(key) for key, _, _ in page]
        rows = []
        for (key, relation, usd), entry in zip(page, entries):
            looked = self._state_of(entry) if entry is not None else None
            rows.append([PLACEHOLDER if entry is not None else None, type_word(type_of_id(key)) or OTHER, relation, None if usd is None else _cents(usd),
                         entry.sku if entry is not None else None, entry.kind if entry is not None else None, looked[1] if looked else None])
            while len(rows[-1]) > 1 and rows[-1][-1] is None:
                rows[-1].pop()
        block: dict = {"total": len(ordered), "cols": list(NEIGHBOR_COLUMNS), "rows": rows}
        if len(ordered) > FAN_IN and not offset:
            counted = self._grouped(ordered)
            block["summary"] = {"cols": ["type", "relation", "count", "usd30d"], "rows": counted[:NEIGHBOR_GROUPS]}
            if len(counted) > NEIGHBOR_GROUPS:
                block["summary"]["rows_not_shown"] = len(counted) - NEIGHBOR_GROUPS
        return block, rows, entries

    @staticmethod
    def _grouped(priced: "list[tuple[str, str, float | None]]") -> list[list]:
        """The resources that links join (their lower-case id, the relation and the cost) as a row for each type and relation, the dearest first: [type, relation, count, the cost of those that have one]."""
        groups: dict[tuple[str, str], list] = {}
        for key, relation, usd in priced:
            group = groups.setdefault((type_word(type_of_id(key)) or OTHER, relation), [0, None])
            group[0] += 1
            group[1] = group[1] if usd is None else (group[1] or 0.0) + usd
        ranked = sorted(groups.items(), key=lambda item: (-(item[1][1] or 0.0), -item[1][0], item[0]))
        return [[kind, relation, count, None if usd is None else _cents(_money(usd))] for (kind, relation), (count, usd) in ranked]

    def _tool_neighbors(self, args: dict) -> dict:
        entry, direction, offset = self._entry(args["handle"]), args["direction"], args["offset"] or 0
        self._read = {}  # an answer that holds no link of the resource credits it with nothing
        state = self._load_edges()
        said: dict = {}
        if state.failed:
            self._listing(said, "unavailable", [sub for sub in self.subscriptions if sub in set(state.failed)])
        answer: dict = {"handle": args["handle"], "type": type_word(entry.resource.resource_type)}
        if not state.done:
            return {**answer, "graph": {"resources": len(state.ids), "complete": False}, "partial": True, **said}
        answer["graph"] = {"resources": len(state.ids), "edges": state.count, "outside": state.outside, **({"not_kept": state.not_kept} if state.not_kept else {})}
        answer.update(said)
        number = state.ids.get(entry.key)
        if number is None:
            answer["listed"] = False  # a part that Resource Graph does not list as a resource, or one that this pass did not keep
        sides = {"refers_to": state.out.get(number, []), "referred_by": state.into.get(number, [])} if number is not None else {"refers_to": [], "referred_by": []}
        wanted = [direction] if direction else ["referred_by"] if offset else ["refers_to", "referred_by"]
        shown: list[tuple[list, list]] = []
        lists: list[tuple[list, dict, str]] = []
        for name in wanted:
            block, rows, entries = self._links(state, sides[name], offset)
            answer[name] = block
            shown.append((rows, entries))
            lists.append((rows, block, "rows"))
            if "summary" in block:
                lists.append((block["summary"]["rows"], block["summary"], "rows"))
        answer.update(self._caveats([], {self._sub_of(state.names[number]) for name in wanted for number, _ in sides[name]} - {None}))
        self._fit(answer, lists)
        for name, (rows, entries) in zip(wanted, shown):
            block = answer[name]
            block.pop("rows_not_shown", None)
            if offset + len(rows) < block["total"]:
                block["next_offset"] = offset + len(rows)
            for row, found in zip(rows, entries):
                if found is not None:
                    cell, looked = self._cells(found), self._state_of(found)
                    seen: dict = {"managed": cell["managed"], "properties": {looked[0]: looked[1]} if looked else {}}
                    seen.update({key: cell[field] for key, field in (("cost30d", "usd30d"), ("sku", "sku"), ("kind", "kind"), ("location", "region")) if field in cell})
                    row[0] = self._show(found, seen)
        if any(answer[name]["total"] for name in wanted):
            self._read = {args["handle"]: "d"}
        return answer

    # -- the whole picture of a few resources, and their age -------------------------------------------------------------------------------------
    def _run(self, tasks: "dict[object, Callable[[Callable[[], bool]], T]]") -> "tuple[dict[object, T | Failed], list]":
        """Runs the reads at the same time, at most DOSSIER_WORKERS of them (and not more than `workers`), and starts none once the time of a measurement is used up (`budget_seconds`). Each read is
        given the clock of the call, so that one that is under way can stop. Returns the result of each read, a Failed for one that ended in an error of the reads, and the keys of the reads that were
        not started or did not finish in time."""
        began = self.monotonic()

        def late() -> bool:
            return self.monotonic() - began >= self.budget_seconds

        def guarded(task: "Callable[[Callable[[], bool]], T]") -> "T | Failed | TimeUp":
            try:
                return task(late)
            except TimeUp as error:
                return error
            except READ_ERRORS as error:
                return Failed(error)

        queue, running, done = list(tasks), {}, {}
        workers = max(1, min(DOSSIER_WORKERS, self.workers))
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            while queue or running:
                while queue and len(running) < workers and not late():
                    key = queue.pop(0)
                    running[pool.submit(guarded, tasks[key])] = key
                left = self.budget_seconds - (self.monotonic() - began)
                if not running or left <= 0:
                    break
                finished, _ = wait(running, timeout=left, return_when=FIRST_COMPLETED)
                for future in finished:
                    key, found = running.pop(future), future.result()
                    if not isinstance(found, TimeUp):
                        done[key] = found
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return done, [key for key in tasks if key not in done]

    def _owners(self) -> ownership.OwnerReader:
        """The reader of the Activity Log that the tools of this run use: the investigation gives it one that shares what it keeps with the reads for its cases (so that nothing is read twice, and
        these reads do not use up the budget of those), and a toolbox that is used without one makes its own."""
        if self.owners is None:
            self.owners = ownership.OwnerReader(self.arm, self.now, max_reads=OWNER_READS, seconds=OWNER_SECONDS)
        return self.owners

    def _ages_of(self, entries: list[_Entry]) -> None:
        """What Resource Graph holds of the age of the resources (`systemData` and a creation time of their properties), read once for each of them: for a type that has neither, nothing."""
        wanted = [entry for entry in entries if entry.key not in self._aged and SCOPE_ID.fullmatch(entry.resource.resource_id)]
        if wanted:
            rows = self.arm.graph_many(list(dict.fromkeys(entry.sub for entry in wanted)), AGES.format(ids=", ".join(f"'{entry.resource.resource_id}'" for entry in wanted)))
            for entry in wanted:
                self._aged[entry.key] = next(((row.get("sd"), row.get("made")) for row in rows if str(row.get("id") or "").lower() == entry.key), (None, None))

    def _history(self, entries: list[_Entry], ages: object, logs: dict) -> dict[str, dict]:
        """The history of each resource (ownership.history), by handle: the age that Resource Graph holds and the Activity Log that was read, each as far as it was read. A source that failed is said
        once in a note and is `not-recorded` in the answer."""
        for found, what in [(ages, "the ages")] + [(found, "the Activity Log") for found in logs.values()]:
            if isinstance(found, Failed):
                self._fail("history", what, found)
        record: dict[str, dict] = {}
        for entry in entries:
            handle, found = entry.resource.handle, logs.get(entry.resource.handle)
            events, complete = found if isinstance(found, tuple) else (None, False)
            system, made = self._aged.get(entry.key, (None, None))
            record[handle] = ownership.history(self.now, system, made, events, complete, entry.resource.resource_id)
        if self.owners is not None and self.owners.notes:
            self.notes.extend(self.owners.notes)  # what the reader says of reads that its budget did not allow, or that failed
            self.owners.notes.clear()
        return record

    def _tool_changes(self, args: dict) -> dict:
        entries = [self._entry(handle) for handle in args["handles"]]
        tasks: dict = {("ages",): lambda late: self._ages_of(entries), **{(entry.resource.handle,): lambda late, entry=entry: self._owners().log(entry.resource.resource_id) for entry in entries}}
        done, left = self._run(tasks)
        found = self._history(entries, done.get(("ages",)), {entry.resource.handle: done.get((entry.resource.handle,)) for entry in entries})
        unread = [entry.resource.handle for entry in entries if ("ages",) in left or (entry.resource.handle,) in left]
        rows = []
        self._read = {}
        for entry in entries:
            handle = entry.resource.handle
            if handle not in unread:
                self.evidence.setdefault(handle, {})["history"] = dict(found[handle])
                rows.append([handle, *(found[handle][name] for name in HISTORY_COLUMNS[1:])])
                if dossier.counted(found[handle]):
                    self._read[handle] = "d"
        return {"log_days": ownership.WINDOW_DAYS, "cols": list(HISTORY_COLUMNS), "rows": rows, **({"unread": unread} if unread else {})}

    def _tool_profile(self, args: dict) -> dict:
        days, grain = args["days"] or MAX_DAYS, args["grain"] or "day"
        wanted = list(dict.fromkeys(args["handles"]))
        kept = [self._pictures.get((handle, days, grain)) for handle in wanted]
        if wanted and all(part is not None for part in kept):
            # A plain repeat: the parts were read in full already, at this grain and over these days, so the answer is what they showed and nothing is read again (the metrics were the only thing
            # that a repeat read again, and they are what takes the time).
            answer = {"days": days, "grain": grain, "partial": False, "profiles": [json.loads(json.dumps(part[0])) for part in kept]}  # type: ignore[index]
            self._saved = round(sum(part[1] for part in kept), 1)  # type: ignore[index]
        else:
            began = self.monotonic()
            answer = dossier.build_dossier(self, args["handles"], days, grain)
            each = max(0.0, self.monotonic() - began) / max(1, len(answer["profiles"]))
            for part in answer["profiles"]:
                if part["handle"] not in answer.get("unread", {}) and dossier.complete(part):
                    self._pictures[(part["handle"], days, grain)] = (json.loads(json.dumps(part)), each)
        self._read = {part["handle"]: letters for part in answer["profiles"] if (letters := dossier.read_by(part))}
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
            rows.append([handle, type_word(entry.resource.resource_type) or OTHER, question.runs_seen, question.days_open, question.confidence, question.request, question.why])
        answer: dict = {"source": OPEN_SOURCE, "total": len(pool), "cols": list(OPEN_COLUMNS), "rows": rows}  # type: ignore[arg-type]
        if len(found) > len(rows):
            answer["not_shown"] = len(found) - len(rows)
        for name, count in (("gone", gone), ("unread", unread)):
            if count:
                answer[name] = count
        return answer
