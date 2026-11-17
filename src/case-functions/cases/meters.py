"""What a resource, or a kind of resource, is billed for, meter by meter: the daily cost lines of Cost Management made into one line for each meter, with the numbers of its daily shape.
Standard library only. It holds numbers and the platform's words, and decides nothing: a tool shows the words through its own word check.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Iterable, Mapping, NamedTuple


class Meter(NamedTuple):
    """One meter of one scope over the closed days from `start`: the scope (the handle of a resource, or a resource type) and the service that was asked for (None for any), the six words of
    the meter as Cost Management gives them (category, subcategory, name, pricing model, kind of charge, unit of measure: for the code, never shown as they are), the quantity and the cost
    over the window, the cost of each day that has a line, and how many resources carry it (None for a single resource)."""

    scope: str
    service: str | None
    words: tuple[str, ...]
    quantity: float
    usd: float
    daily: Mapping[dt.date, float]
    resources: int | None
    start: dt.date
    days: int


def fold(rows: Iterable[tuple[dt.date, tuple[str, ...], float, float]]) -> dict[tuple[str, ...], tuple[float, float, dict[dt.date, float]]]:
    """The lines of every day as one line for each meter: (the quantity, the cost, the cost of each day) by the six words of the meter."""
    found: dict[tuple[str, ...], tuple[float, float, dict[dt.date, float]]] = {}
    for day, words, cost, quantity in rows:
        used, spent, daily = found.setdefault(words, (0.0, 0.0, {}))
        daily[day] = daily.get(day, 0.0) + cost
        found[words] = (used + quantity, spent + cost, daily)
    return found


def shape(meter: Meter, today: dt.date) -> dict:
    """The daily shape of a meter, in numbers: `days` (the days that have a cost), the average, the smallest and the greatest cost of those days, `cv` (the spread of the daily cost over every day
    of the window, divided by its mean: None when the mean is not above 0) and `first_day` and `last_day`, how many days ago the first and the last of those days were. Nothing of it is a verdict."""
    series = [meter.daily.get(meter.start + dt.timedelta(days=n), 0.0) for n in range(meter.days)]
    paid = [(day, cost) for day, cost in sorted(meter.daily.items()) if cost != 0 and meter.start <= day < meter.start + dt.timedelta(days=meter.days)]
    costs = [cost for _, cost in paid]
    mean = math.fsum(series) / meter.days
    spread = math.sqrt(math.fsum((cost - mean) ** 2 for cost in series) / meter.days)
    return {"days": len(paid), "avg_day": math.fsum(costs) / len(costs) if costs else None, "min_day": min(costs, default=None), "max_day": max(costs, default=None),
            "cv": spread / mean if mean > 0 else None, "first_day": (today - paid[0][0]).days if paid else None, "last_day": (today - paid[-1][0]).days if paid else None}
