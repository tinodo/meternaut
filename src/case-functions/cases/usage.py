"""What the use of a resource is, for the chart of its daily use on the card of a decision: the table of the kinds of resource that have one, how each is read from Azure Monitor, and the
numbers and words that go with it.

Pure data and pure functions, standard library only: the pages import this module (so it holds no call, no file and no clock), and the Watch reads from it (cases/run.py, read_use_series).
It is for a person who looks at a request. Nothing that decides reads it: no agent, no tool of the investigation and no rule of waste (a test pins that), so a line on a chart is a way to
read a series and never a rule that says what is waste.

A kind is one row of the table: the type of resource it is for (as Azure writes it, in lower case), a key that a case stores with its series (`CaseRecord.use_kind`, a constant of this
file and never text from the estate or from a model), the platform metrics of Azure Monitor that make it and how they are put together, which aggregation of a daily bucket is the day's
value, the unit, the title of the chart, and whether the series of several requests may be added up on one row (bytes and calls: yes; a percentage and a count of connections at one time:
no). Every metric name and its default aggregation was read on the page of Learn that the row names ("Supported metrics for ...", in `LEARN`) on 2026-11-09; a kind that could not be
confirmed there is not in the table. Time in a series is UTC: a bucket of Azure Monitor is a UTC day.

What this repository has not seen from a live Azure Monitor, and the code therefore does not assume: that a read in daily buckets (interval P1D, as Arm.metrics asks for it) is answered for a metric
whose page of Learn lists the time grain PT1M only (most of the table), whether a day without traffic comes back as a bucket with a zero or as a bucket with no value (a gap here, and a series
with fewer than MIN_DAYS values is not kept), and what Azure answers for a metric that a resource does not offer (a case that takes the larger of its metrics reads it as a 400 and leaves it out).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

DAYS = 30  # the closed days of a series, the last of them yesterday (UTC): the same thirty as the daily cost (cases/run.py: COST_DAYS)
MIN_DAYS = 20  # a series is kept only when at least this many of its days have a value: fewer would be a chart made of the days that are missing
LEARN = "https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/"
# The one threshold of the table that is a CPU figure. It is the default of the low-use check of Azure Advisor for a virtual machine (Learn, "Tutorial: Optimize costs from
# recommendations": a machine whose CPU use is five percent or less, and whose network use is seven MB or less, for four days or more, is a low-use machine; five percent is the default
# and can be set). It is a line to read a chart against, drawn for the person who decides. No agent is given it and no code decides on it (rule 30 (a) of AGENTS.md: nothing tells an agent
# what to find), and the Investigator keeps no threshold of its own.
IDLE_CPU_PERCENT = 5.0
UNITS = ("percent", "bytes", "count")
AGGREGATES = ("average", "maximum", "total")
COMBINES = ("sum", "max")
# What a day's value is, in the words of a caption: a total needs none (the title says per day).
DAILY_WORDS = {"average": "daily average", "maximum": "daily highest", "total": ""}
BYTE_WORDS = ("bytes", "KB", "MB", "GB", "TB")
BYTE_SUFFIXES = ("B", "KB", "MB", "GB", "TB")


@dataclass(frozen=True)
class Use:
    """One kind of use. `metrics` are the platform metrics of Azure Monitor (the names of the REST API) that the series is made of; `combine` says how they are put together: `sum` adds them
    (every one has to be read, or the sum would be less than the use) and `max` takes the largest of them for each day (they are alternatives that count the same calls in different
    places, so that adding them could count a call twice; one that the resource does not have may be missing). `aggregate` is the aggregation of a daily bucket that is the day's value, and
    `unit` is what the number is: a percentage, bytes or a count. `threshold` is the line that the chart is read against, with its `threshold_label`, or None."""

    kind: str
    resource_type: str
    metrics: tuple[str, ...]
    combine: str
    aggregate: str
    unit: str
    title: str
    additive: bool
    learn: str
    threshold: float | None = None
    threshold_label: str = ""

    @property
    def daily(self) -> str:
        """What the day's value is, in words, for a caption ("daily average"), or empty."""
        return DAILY_WORDS[self.aggregate]


TABLE: dict[str, Use] = {use.resource_type: use for use in (
    Use("vm-cpu", "microsoft.compute/virtualmachines", ("Percentage CPU",), "sum", "average", "percent", "CPU use per day", False, "microsoft-compute-virtualmachines-metrics",
        IDLE_CPU_PERCENT, f"{IDLE_CPU_PERCENT:g}% idle line"),
    Use("plan-cpu", "microsoft.web/serverfarms", ("CpuPercentage",), "sum", "average", "percent", "CPU use per day", False, "microsoft-web-serverfarms-metrics"),
    # Learn gives the unit of the two metrics of a private endpoint as Count; their names and descriptions are "Bytes In" and "Bytes Out", the total number of bytes.
    Use("pe-traffic", "microsoft.network/privateendpoints", ("PEBytesIn", "PEBytesOut"), "sum", "total", "bytes", "Traffic per day", True,
        "microsoft-network-privateendpoints-metrics"),
    Use("storage-transactions", "microsoft.storage/storageaccounts", ("Transactions",), "sum", "total", "count", "Transactions per day", True,
        "microsoft-storage-storageaccounts-metrics"),
    # Total Calls is not for Azure OpenAI ("Do not use for Azure OpenAI service", Learn), and Model Requests counts every model of the resource, Azure OpenAI included ("The Models category
    # contains all the models available in the resource, including Azure OpenAI, DeepSeek, and Phi", Learn, "Monitor model deployments in Microsoft Foundry Models"). The larger of the
    # two is the number of calls that is not a call too many, and zero only when both are.
    Use("ai-calls", "microsoft.cognitiveservices/accounts", ("TotalCalls", "ModelRequests"), "max", "total", "count", "Calls per day", True,
        "microsoft-cognitiveservices-accounts-metrics"),
    Use("ip-traffic", "microsoft.network/publicipaddresses", ("ByteCount",), "sum", "total", "bytes", "Traffic per day", True, "microsoft-network-publicipaddresses-metrics"),
    Use("lb-traffic", "microsoft.network/loadbalancers", ("ByteCount",), "sum", "total", "bytes", "Traffic per day", True, "microsoft-network-loadbalancers-metrics"),
    # The default aggregation on Learn is Total; the highest number of connections at one time is the figure that says whether anybody was connected.
    Use("p2s-connections", "microsoft.network/p2svpngateways", ("P2SConnectionCount",), "sum", "maximum", "count", "Connections per day", False,
        "microsoft-network-p2svpngateways-metrics", 0.0, "no connection"),
)}
KINDS: dict[str, Use] = {use.kind: use for use in TABLE.values()}


def entry_of(resource_type: object) -> Use | None:
    """The kind of use that a type of resource has, or None. The type is read as Azure writes it, in any case."""
    return TABLE.get(resource_type.strip().lower()) if isinstance(resource_type, str) else None


def for_resource(resource_id: object, resource_type: object) -> Use | None:
    """The kind of use of one resource: its type is in the table and its id is the id of one resource of that type, in a resource group of a subscription (not of a part of one)."""
    use = entry_of(resource_type)
    if use is None or not isinstance(resource_id, str):
        return None
    parts = resource_id.strip().split("/")
    if len(parts) != 9 or parts[0] or {".", ".."} & set(parts) or not all(parts[1:]):
        return None
    shape = [part.lower() for part in (parts[1], parts[3], parts[5])]
    return use if shape == ["subscriptions", "resourcegroups", "providers"] and f"{parts[6]}/{parts[7]}".lower() == use.resource_type else None


def day_of(stamp: object) -> dt.date | None:
    """The day of a bucket of Azure Monitor, when its time is the start of a UTC day (2026-10-05T00:00:00Z); None for any other time."""
    try:
        moment = dt.datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return moment.date() if moment.time() == dt.time(0, 0) else None


def daily(points: Iterable[tuple[object, object]], first: dt.date, days: int = DAYS) -> list[float | None]:
    """The value of each of `days` days from `first`, as a list of numbers with None for a day that has no value. `points` are (the time of a bucket, its value). A value that is not a finite
    number, one that is below zero, a bucket that is not a UTC day and a day outside the span are left out: they are a gap, never a zero."""
    series: list[float | None] = [None] * days
    for stamp, value in points:
        day = day_of(stamp)
        if day is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            continue
        index = (day - first).days
        if 0 <= index < days:
            series[index] = round(float(value), 4)
    return series


def combine(parts: Sequence[Sequence[float | None]], how: str) -> list[float | None]:
    """The series of one kind from the series of its metrics, day by day. `sum`: a day has a value when every metric has one, and it is their sum. `max`: a day has a value when any metric
    has one, and it is the largest."""
    out: list[float | None] = []
    for day in zip(*parts):
        found = [value for value in day if value is not None]
        if how == "max":
            out.append(max(found) if found else None)
        else:
            out.append(round(math.fsum(found), 4) if len(found) == len(day) else None)
    return out


def days_with_value(series: Sequence[float | None]) -> int:
    return sum(1 for value in series if value is not None)


# -- the numbers as a person reads them ---------------------------------------------------------------------------------------------------------

def _plain(number: float, places: int) -> str:
    text = f"{number:,.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _scaled(size: float) -> tuple[float, int]:
    """A size in bytes as a number of the largest unit that keeps it at 1 or more, and the position of that unit in BYTE_WORDS."""
    index = 0
    while size >= 1024 and index < len(BYTE_WORDS) - 1:
        size, index = size / 1024, index + 1
    return size, index


def value_text(unit: str, value: float) -> str:
    """A number of the unit of a kind, as a person reads it: 2.1%, 1.5 GB, 1,204. Bytes go by 1,024 to KB, MB, GB and TB, as the rest of the pages show them."""
    if unit == "percent":
        if 0 < value < 0.01:
            return "under 0.01%"
        return _plain(value, 2 if 0 < value < 0.1 else (1 if value < 10 else 0)) + "%"
    if unit == "bytes":
        size, index = _scaled(abs(value))
        word = BYTE_WORDS[index]
        if index == 0:
            return f"{_plain(size, 0)} {'byte' if round(size) == 1 else word}"
        return f"{_plain(size, 0 if size >= 100 else (1 if size >= 10 else 2))} {word}"
    return _plain(value, 0 if abs(value - round(value)) < 0.005 else 2)


def scale_of(unit: str, peak: float) -> tuple[float, str]:
    """What an axis divides by and the suffix of its labels, chosen by the size of the largest value: bytes go to the unit that keeps the number below 1,024."""
    if unit == "bytes":
        index = _scaled(abs(peak))[1]
        return float(1024 ** index), BYTE_SUFFIXES[index]
    return 1.0, "%" if unit == "percent" else ""


def axis_text(unit: str, value: float, divisor: float = 1.0, suffix: str = "") -> str:
    """The label of a line of a chart, short (the margin that it stands in is narrow): 4%, 2GB, 500K, 0."""
    if value == 0:
        return "0%" if unit == "percent" else "0"
    if unit == "count":
        for step, letter in ((1e9, "G"), (1e6, "M"), (1e3, "K")):
            if value >= step:
                return f"{value / step:g}{letter}"
        return f"{value:g}"
    return f"{value / divisor:g}{suffix}"
