"""What Azure Monitor offers for a metric, and how its answers are made into daily buckets: the time grain and the aggregations that a definition allows, the daily buckets that a finer grain
is made into, and the greatest value and the 95th percentile of the finer grain itself. Standard library only; it reads the answer of Azure and gives numbers and words.
"""
from __future__ import annotations

import math
from typing import Mapping, NamedTuple, Sequence

GRAINS = {"PT1M": 60, "PT5M": 300, "PT15M": 900, "PT30M": 1800, "PT1H": 3600, "PT6H": 21600, "PT12H": 43200, "P1D": 86400}  # the time grains of Azure Monitor, in seconds
DAY = "P1D"
READ = ("Total", "Maximum", "Average")  # the aggregations that the answers hold
MAX_POINTS = 8640  # the points of one series that one request asks for: 30 days of five minutes


class MetricPoint(NamedTuple):
    """One bucket of a metric. An aggregation that the metric does not have, or that has no value in the bucket, is None."""

    time: str
    total: float | None
    maximum: float | None
    average: float | None


class Plan(NamedTuple):
    """How one metric is read: the time grain (ISO 8601), the aggregations that are asked for, and the field of a bucket that stands for it (`level`)."""

    grain: str
    aggregations: tuple[str, ...]
    level: str


DAILY = Plan(DAY, READ, "average")  # what every metric was read with before the definitions were asked


def plan_of(definition: Mapping, hourly: bool = False) -> Plan | None:
    """How a metric is read, from its definition: only the aggregations that it supports (Total, Maximum, Average, or Count alone, which is shown as the total), the day when it offers
    one and else the largest grain below a day; with `hourly` the hour when it offers one, else the largest grain below an hour, else its finest. A list that the definition lacks is
    the primary aggregation, or the day. None when it supports no such aggregation or offers no grain of a day or less."""
    supported = [kind for kind in definition.get("supportedAggregationTypes") or [definition.get("primaryAggregationType")] if isinstance(kind, str)]
    kinds = [kind for kind in READ if kind in supported] or (["Count"] if "Count" in supported else [])
    listed = [item.get("timeGrain") for item in definition.get("metricAvailabilities") or [] if isinstance(item, dict)]
    offered = sorted({grain for grain in listed if isinstance(grain, str) and grain in GRAINS}, key=GRAINS.get) if listed else [DAY]
    below = [grain for grain in offered if GRAINS[grain] <= (3600 if hourly else GRAINS[DAY] - 1)]
    grain = (below[-1] if below else offered[0] if offered else None) if hourly else (DAY if DAY in offered else below[-1] if below else None)
    if not kinds or grain is None:
        return None
    level = next(kind for kind in (definition.get("primaryAggregationType"), "Average", "Total", "Maximum", "Count") if kind in kinds)
    return Plan(grain, tuple(kinds), "total" if level == "Count" else level.lower())


def daily(points: Sequence[MetricPoint]) -> list[MetricPoint]:
    """The buckets of a grain below a day as daily buckets (UTC days): the total is the sum of the totals, the maximum the greatest maximum and the average the mean of the averages,
    each over the buckets that have one."""
    days: dict[str, list[MetricPoint]] = {}
    for point in points:
        days.setdefault(point.time[:10], []).append(point)
    found = []
    for day, group in days.items():
        totals, maxima, averages = ([value for value in values if value is not None] for values in zip(*((p.total, p.maximum, p.average) for p in group)))
        found.append(MetricPoint(f"{day}T00:00:00Z", math.fsum(totals) if totals else None, max(maxima) if maxima else None, math.fsum(averages) / len(averages) if averages else None))
    return found


def fine(points: Sequence[MetricPoint], level: str) -> tuple[float | None, float | None]:
    """The greatest value of any bucket (a maximum, or the level of the bucket) and the 95th percentile of the levels of the buckets, by nearest rank: the least value that at least 95
    percent of the buckets are at or below. (None, None) when no bucket has a value."""
    levels = sorted(value for point in points if (value := getattr(point, level)) is not None)
    maxima = [point.maximum for point in points if point.maximum is not None]
    return (max([*maxima, *levels]) if levels or maxima else None), (levels[math.ceil(0.95 * len(levels)) - 1] if levels else None)
