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


WEEK, MONTH, FEWEST = 7, 30, 3  # the days of the recent rate, the days that a month is worked out from, and the fewest days of life that a rate rests on


class Rates(NamedTuple):
    """What a meter costs a month at three rates. `week` is the mean of its last 7 closed days times 30, days without a line counting as nothing (a meter that began later has only the days that it has).
    `since` is the mean from its first day that has a cost to the last day of the window times 30, where a read can say it: the meter began inside the window, or the window is a month. `steady` is 30 times
    the median of the days that have a cost, when 3 or more have: a charge made once, or a rise of the last days, does not move a median. `life` is the days from the first day that has a cost to the last day,
    `began` says that the first day is after the window began, `cv` is the spread of the daily cost over those days divided by its mean."""

    week: float
    since: float | None
    life: int
    began: bool
    cv: float | None
    steady: float | None

    @property
    def high(self) -> float:
        return self.week if self.since is None else max(self.week, self.since)

    @property
    def low(self) -> float:
        return min(self.week, self.week if self.since is None else self.since, self.week if self.steady is None else self.steady)


def rates(meter: Meter) -> Rates | None:
    """The rates of a meter, or None when its days cannot give one: a window under 7 days, a number that is not one, no day with a cost, or fewer than FEWEST days from the first cost to the last
    day (a single day may be a part of a day, a charge made once or a bill that is late, so it is not stretched into a month)."""
    last = meter.start + dt.timedelta(days=meter.days - 1)
    inside = {day: cost for day, cost in meter.daily.items() if meter.start <= day <= last}
    paid = sorted(day for day, cost in inside.items() if cost != 0)
    if meter.days < WEEK or not paid or not all(math.isfinite(cost) for cost in inside.values()):
        return None
    life = (last - paid[0]).days + 1
    if life < FEWEST:
        return None
    series = [inside.get(paid[0] + dt.timedelta(days=n), 0.0) for n in range(life)]
    mean, span, began = math.fsum(series) / life, min(WEEK, life), paid[0] > meter.start
    spread = math.sqrt(math.fsum((cost - mean) ** 2 for cost in series) / life)
    costs = sorted(cost for cost in series if cost != 0)
    steady = (costs[len(costs) // 2] + costs[(len(costs) - 1) // 2]) / 2 * MONTH if len(costs) >= FEWEST else None
    return Rates(math.fsum(series[-span:]) / span * MONTH, mean * MONTH if life > WEEK and (began or meter.days == MONTH) else None, life, began, spread / mean if mean > 0 else None, steady)


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
