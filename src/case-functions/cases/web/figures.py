"""The figures of the page of the decisions: money as a person reads it, and the small charts and chips that go with it.

A chart is an inline SVG with no script. Its colours and the size of its text are the classes of the stylesheet (never a value of its own), and every number in it was checked here.
A series is the cost of each day, oldest first, as a case keeps it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from ..brief import Brief, Saving, things
from ..models import GROUP_FACT, CaseRecord
from .core import Safe, esc, fmt

WEAKEST_FIRST = ("Scenario", "Expected", "Verified")
RISKS = {"low": ("Low risk", "low", "circle", 0), "medium": ("Medium risk", "mid", "triangle", 1), "high": ("High risk", "high", "diamond", 2)}
SERIES_MIN = 2
SERIES_MAX = 60
NO_LINES = "Cost Management reports a cost 8 to 72 hours after it happens."
READ_LATER = "The next search reads them."
WHEN_JUDGED = "They are read when the AIs judge this finding again."
SHAPES = {"circle": '<circle cx="6" cy="6" r="4"/>', "triangle": '<path d="M6 1.5 11 10.5H1z"/>', "diamond": '<path d="M6 1 11 6 6 11 1 6z"/>',
          "square": '<rect x="2" y="2" width="8" height="8" rx="1.5"/>'}  # a chip says what it is in words and in a shape, never by colour alone
NICE = (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)


def number_of(value: object) -> float | None:
    """A finite number, or None for anything else (a bool is not a number here)."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def series_of(value: object) -> list[float] | None:
    """A series of daily costs as a case keeps it, or None when it is not what it should be: a list of 2 to 60 finite numbers, none of them below zero."""
    if not isinstance(value, list) or not SERIES_MIN <= len(value) <= SERIES_MAX:
        return None
    numbers = [number_of(item) for item in value]
    return None if any(n is None or n < 0 for n in numbers) else numbers  # type: ignore[return-value]


def summed(series: Sequence[list[float] | None]) -> list[float] | None:
    """The sum of series of one length, day by day; None when one is missing or the lengths differ (a sum of some of them would be a figure that nobody asked for)."""
    if not series or any(s is None for s in series) or len({len(s) for s in series}) != 1:  # type: ignore[arg-type]
        return None
    return [sum(day) for day in zip(*series)]  # type: ignore[arg-type]


@dataclass(frozen=True)
class Figure:
    """What is at stake in a request, in a month: a saving (with its level and its basis), a cost (the most that a change could save, which nothing has measured), or nothing that can be
    shown (and why). The list of the decisions and the page of one request draw the same figure from the same code."""

    state: str  # save, cost or none
    label: str
    monthly: float | None
    level: str
    note: str


def figure_of(savings: Sequence[Saving], costs: Sequence[float | None], basis: str = "") -> Figure:
    """The figure of one request, or of the requests that a row stands for: their savings when every one has a figure (the weakest level of them, and `basis` when they have many), else
    what they cost in 30 days, else nothing and the reason."""
    if savings and all(s.monthly is not None for s in savings):
        levels = {s.level for s in savings}
        level = savings[0].level if len(levels) == 1 else next((w for w in WEAKEST_FIRST if w in levels), "Scenario")
        return Figure("save", f"Saves, {level}", sum(s.monthly for s in savings), level, f"Based on {basis or savings[0].basis}.")  # type: ignore[misc]
    known = [c for c in costs if c is not None]
    if known and sum(known) > 0:
        return Figure("cost", "Costs, saving not measured", sum(known), "", "The most that a change could save: what it would save was not worked out.")
    return Figure("none", "Cost not visible", None, "", "No cost line in the last 30 days." if known else "No cost line was read yet.")


def cost_of(brief: Brief, case: CaseRecord | None) -> float | None:
    """What the finding costs in 30 days, from the cost lines: everything that it stands for when it is a group. None when no cost line was read."""
    if brief.group is not None and brief.group.cost is not None:
        return brief.group.cost
    return number_of(case.cost_usd_30d) if case is not None else None


def ids_known(brief: Brief, case: CaseRecord | None) -> bool:
    """Whether the daily cost of the finding can be read: that of one resource always can, that of a group only when its case kept the ids of its resources (a case of an earlier search
    kept their short hashes and nothing else)."""
    if brief.group is None or case is None:
        return True
    group = case.facts.get(GROUP_FACT) if isinstance(case.facts, dict) else None
    return isinstance(group, dict) and bool(group.get("resourceIds"))


def series_reason(brief: Brief, case: CaseRecord | None) -> str:
    """Why a request has no chart: its cost lines are there and the next search reads the series, the finding of an earlier search has to be judged again before its series can be read,
    or no cost line exists yet."""
    if not ids_known(brief, case):
        return WHEN_JUDGED
    return READ_LATER if (cost_of(brief, case) or 0) > 0 else NO_LINES


def title_of(brief: Brief) -> tuple[Safe, str]:
    """The title of one request as markup and as plain text: how many of what and where when it stands for many resources, else the headline without its place (the line under it says the
    place), with "Review" for "Look at" and the name of the resource in code type."""
    if brief.group is not None:
        text = things(brief.group.count, brief.group.kind, brief.group.groups)
        return esc(text), text
    text, place = brief.headline, f" in group {brief.where.group}" if brief.where.group else ""
    text = text[: -len(place)] if place and text.endswith(place) else text
    text = "Review " + text[8:] if text.startswith("Look at ") else text
    name = brief.where.name
    before, found, after = text.partition(name) if name else (text, "", "")
    return (fmt("{before}<code>{name}</code>{after}", before=before, name=name, after=after) if found else esc(text)), text


def dollars(value: float, cents: bool = True) -> str:
    return f"${value:,.2f}" if cents else f"${round(value):,}"


def a_year(monthly: float) -> str:
    """A monthly figure in a year, in whole dollars: twelve times the month."""
    year = round(monthly * 12)
    return "under $1" if year == 0 and monthly > 0 else f"${year:,}"


def describe(series: Sequence[float]) -> str:
    """The shape of a series in words, for a person who cannot see the chart."""
    low, high, mean = min(series), max(series), sum(series) / len(series)
    if high == 0:
        return "no cost on any day"
    if high - low <= 0.15 * mean:
        return f"flat at about {dollars(mean)} a day"
    return f"from {dollars(low)} to {dollars(high)} a day, {dollars(series[-1])} on the last day"


def _nice(value: float) -> float:
    scale = 10 ** math.floor(math.log10(value)) if value > 0 else 1
    return next((step * scale for step in NICE if value <= step * scale), 10 * scale)


def _axis(value: float) -> str:
    return f"${value:,.2f}".rstrip("0").rstrip(".")


def _shape(series: Sequence[float], left: int, right: int, top: int, bottom: int, ceiling: float) -> tuple[str, str, tuple[float, float]]:
    """The line, the area under it and the last point of a series, in the units of the chart: from zero at the bottom to `ceiling` at the top."""
    step = (right - left) / (len(series) - 1)
    points = [(left + i * step, bottom - (bottom - top) * value / ceiling) for i, value in enumerate(series)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))
    return line, f"{line} L{points[-1][0]:.1f},{bottom} L{points[0][0]:.1f},{bottom} Z", points[-1]


def spark(series: list[float] | None, reason: str = NO_LINES) -> Safe:
    """The small chart of a row: the cost of each of the last days, from zero, with a dot on the last day. Without a series the chart says so, and `reason` says why a screen reader."""
    if series is None:
        return fmt('<svg class="sp none" viewBox="0 0 120 32" role="img" aria-label="No daily costs yet: {reason}"><path class="ln" d="M2,22 L118,22"/>'
                   '<text class="ax" x="60" y="12" text-anchor="middle">No daily costs yet</text></svg>', reason=reason)
    line, area, (x, y) = _shape(series, 2, 118, 6, 30, max(series) or 1)
    return fmt('<svg class="sp" viewBox="0 0 120 32" role="img" aria-label="Cost per day, last {days} days: {words}."><path class="ar" d="{area}"/><path class="ln" d="{line}"/>'
               '<circle class="dt" cx="{x}" cy="{y}" r="2"/></svg>', days=len(series), words=describe(series), area=area, line=line, x=f"{x:.1f}", y=f"{y:.1f}")


def chart(series: list[float] | None, reason: str = NO_LINES) -> Safe:
    """The larger chart of the decision in focus: the cost of each of the last days on a scale that starts at zero, with its caption."""
    if series is None:
        return fmt('<figure class="chart"><figcaption>Cost per day <span>no daily costs yet</span></figcaption><p class="m">{reason} The chart fills in then.</p></figure>', reason=reason)
    ceiling = _nice(max(series))
    line, area, (x, y) = _shape(series, 40, 352, 8, 96, ceiling)
    grid = "".join(f'<line class="gl" x1="40" y1="{at}" x2="352" y2="{at}"/>' for at in (8, 52, 96))
    labels = ("".join(f'<text class="ax" x="34" y="{at + 4}" text-anchor="end">{text}</text>' for at, text in ((8, _axis(ceiling)), (52, _axis(ceiling / 2)), (96, "$0")))
              + f'<text class="ax" x="40" y="110">{len(series)} days ago</text><text class="ax" x="352" y="110" text-anchor="end">yesterday</text>')  # numbers only: nothing to escape
    return fmt('<figure class="chart"><figcaption>Cost per day <span>last {days} days, yesterday {last}</span></figcaption>'
               '<svg viewBox="0 0 360 112" role="img" aria-label="Cost per day for the last {days} days: {words}.">{grid}{labels}<path class="ar" d="{area}"/><path class="ln" d="{line}"/>'
               '<circle class="dt" cx="{x}" cy="{y}" r="3"/></svg></figure>', days=len(series), last=dollars(series[-1]), words=describe(series), grid=Safe(grid), labels=Safe(labels),
               area=area, line=line, x=f"{x:.1f}", y=f"{y:.1f}")


def bar(share: float) -> Safe:
    """The bar under a figure: its share of the largest figure on the page, never less than a sliver."""
    width = max(2, min(100, round(100 * share)))
    return Safe(f'<svg class="bar" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true"><rect class="bt" width="100" height="4" rx="2"/>'
                f'<rect class="bv" width="{width}" height="4" rx="2"/></svg>')


def chip(label: str, kind: str = "", shape: str = "square") -> Safe:
    """A chip: a word and a shape. `kind` is low, mid, high or info (its colours), or empty."""
    return fmt('<span class="chip{kind}"><svg viewBox="0 0 12 12" aria-hidden="true">{shape}</svg>{label}</span>', kind=f" {kind}" if kind else "", shape=Safe(SHAPES[shape]), label=label)


def risk_chip(level: str) -> Safe:
    """The chip of a risk: a circle (low), a triangle (medium) or a diamond (high), and a word."""
    label, kind, shape, _ = RISKS.get(level, RISKS["medium"])
    return chip(label, kind, shape)
