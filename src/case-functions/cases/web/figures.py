"""The figures of the page of the decisions: money as a person reads it, and the small charts and chips that go with it.

A chart is an inline SVG with no script. Its colours and the size of its text are the classes of the stylesheet (never a value of its own), and every number in it was checked here.
A series is the cost of each day, oldest first, as a case keeps it.
"""
from __future__ import annotations

import math
from typing import Sequence

from .core import Safe, fmt

SERIES_MIN = 2
SERIES_MAX = 60
NO_LINES = "Cost Management reports a cost 8 to 72 hours after it happens."
READ_LATER = "The next search reads them."
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
