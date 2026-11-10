"""The figures of the page of the decisions: money as a person reads it, and the small charts and chips that go with it.

A chart is an inline SVG with no script. Its colours and the size of its text are the classes of the stylesheet (never a value of its own), and every number in it was checked here.
A series is the cost of each day, oldest first, as a case keeps it. The use of a resource is a second series, with a gap for a day that has no value, and its chart (use_chart) is the
second figure of a decision card: it starts at zero, it is broken at a gap and it shows the line that the kind of use is read against, when it has one (cases/usage.py).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Callable, Sequence

from ..brief import Brief, Saving, things
from ..models import GROUP_FACT, CaseRecord
from ..usage import DAYS as USE_DAYS
from ..usage import MIN_DAYS as USE_MIN_DAYS
from ..usage import Use, axis_text, entry_of, scale_of, value_text
from .core import DAYS, MONTHS, Safe, esc, fmt, join, utc

WEAKEST_FIRST = ("Scenario", "Expected", "Verified")
RISKS = {"low": ("Low risk", "low", "circle", 0), "medium": ("Medium risk", "mid", "triangle", 1), "high": ("High risk", "high", "diamond", 2)}
SERIES_MIN = 2
SERIES_MAX = 60
NO_LINES = "Cost Management reports a cost 8 to 72 hours after it happens."
READ_LATER = "The next search reads them."
WHEN_JUDGED = "They are read when the AIs judge this finding again."
USE_LATER = (f"Azure Monitor shows use a few hours after it happens. The next search reads it. A chart is drawn once {USE_MIN_DAYS} of the last {USE_DAYS} days have a value: "
             "a new resource, a stopped machine and a resource that does not offer this metric have fewer.")
USE_MANY = "Use is not drawn for a finding about many resources."
SHAPES = {"circle": '<circle cx="6" cy="6" r="4"/>', "triangle": '<path d="M6 1.5 11 10.5H1z"/>', "diamond": '<path d="M6 1 11 6 6 11 1 6z"/>',
          "square": '<rect x="2" y="2" width="8" height="8" rx="1.5"/>'}  # a chip says what it is in words and in a shape, never by colour alone
NICE = (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)
USE_NICE = (1, 2, 4, 6, 8, 10)  # the ceilings of a chart of use: the line in the middle is a round number too
PLOT = (40, 352, 8, 96)  # left, right, top and bottom of the plot of a chart: the two charts of a card line up


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


def short_title(headline: str, group: str = "") -> str:
    """A headline as the title of a row, of a page and of a line of the history: without its place (the line under it says the place), with "Review" for "Look at"."""
    place = f" in group {group}" if group else ""
    text = headline[: -len(place)] if place and headline.endswith(place) else headline
    return "Review " + text[8:] if text.startswith("Look at ") else text


def title_of(brief: Brief) -> tuple[Safe, str]:
    """The title of one request as markup and as plain text: how many of what and where when it stands for many resources, else the headline without its place (the line under it says the
    place), with "Review" for "Look at" and the name of the resource in code type."""
    if brief.group is not None:
        text = things(brief.group.count, brief.group.kind, brief.group.groups)
        return esc(text), text
    text = short_title(brief.headline, brief.where.group)
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


# -- the use of a resource ----------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class UseData:
    """The use of one resource, or of several added up, as a page may draw it: the kind (cases/usage.py), the value of each day (None for a day that has none) and the day that the series
    ends on (YYYY-MM-DD), or None when that is not known."""

    use: Use
    values: list[float | None]
    end: str | None


def kept_day(value: object) -> dt.date | None:
    """A day as a case keeps it (YYYY-MM-DD), or None."""
    try:
        return dt.date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def use_values(value: object) -> list[float | None] | None:
    """A series of use as a case keeps it, or None when it is not what it should be: a list of 2 to 60 entries, each a finite number that is not below zero or None, and at least one number."""
    if not isinstance(value, list) or not SERIES_MIN <= len(value) <= SERIES_MAX:
        return None
    values: list[float | None] = []
    for item in value:
        number = None if item is None else number_of(item)
        if item is not None and (number is None or number < 0):
            return None
        values.append(number)
    return values if any(v is not None for v in values) else None


def use_of(case: CaseRecord | None) -> UseData | None:
    """The stored use of a case as it can be drawn: the case is of one resource (a case of a group has none) of a type that has a kind of use, it was stored under that kind, and its series
    is what it should be."""
    if case is None or (isinstance(case.facts, dict) and GROUP_FACT in case.facts):
        return None
    use, values = entry_of(case.resource_type), use_values(case.use_series)
    if use is None or values is None or case.use_kind != use.kind:
        return None
    return UseData(use, values, case.use_series_end if kept_day(case.use_series_end) is not None else None)


def use_summed(parts: Sequence[UseData | None]) -> UseData | None:
    """The use of several requests added up, day by day, for a kind whose numbers may be added (bytes, calls); None when one of them has no series, they are not of one kind, the kind may not
    be added (a percentage, connections at one time) or the lengths differ. A day that any of them has no value for is a gap: the sum of the others would be less than the use."""
    if not parts or any(part is None for part in parts):
        return None
    first = parts[0]  # type: ignore[index]
    if not first.use.additive or any(part.use.kind != first.use.kind or len(part.values) != len(first.values) for part in parts):  # type: ignore[union-attr]
        return None
    values = [None if any(v is None for v in day) else math.fsum(day) for day in zip(*(part.values for part in parts))]  # type: ignore[union-attr]
    ends = {part.end for part in parts}  # type: ignore[union-attr]
    return UseData(first.use, values, ends.pop() if len(ends) == 1 else None)


def _nice_use(value: float) -> float:
    """The smallest of 1, 2, 4, 6, 8 or 10 times a power of ten that is not below the value."""
    if value <= 0:
        return 1.0
    scale = 10 ** math.floor(math.log10(value))
    return next(step * scale for step in USE_NICE if value <= step * scale * (1 + 1e-9))


def _short_day(day: dt.date) -> str:
    return f"{DAYS[day.weekday()][:3]} {day.day} {MONTHS[day.month - 1]}"


def _line(label: str) -> str:
    return label if label.endswith("line") else f"{label} line"


def describe_use(use: Use, values: Sequence[float | None]) -> str:
    """The shape of a series of use in words, for a person who cannot see the chart: how it runs, how it stands to the line of its kind, and how many days have no value."""
    present = [v for v in values if v is not None]
    low, high, mean = min(present), max(present), math.fsum(present) / len(present)
    if high == 0:
        shape = "zero on every day with data"
    elif high - low <= 0.15 * mean:
        shape = f"flat at about {value_text(use.unit, mean)}"
    else:
        last = f"{value_text(use.unit, present[-1])} on the last day" + ("" if values[-1] is not None else " with data")
        shape = f"from {value_text(use.unit, low)} to {value_text(use.unit, high)}, {last}"
    if use.threshold is not None:
        shape += f", at or under the {_line(use.threshold_label)} on {sum(1 for v in present if v <= use.threshold)} of {len(present)} days with data"
    blank = len(values) - len(present)
    return shape + ("." if not blank else f". {blank} day{'' if blank == 1 else 's'} without data {'is' if blank == 1 else 'are'} left blank.")


def use_quiet(use: Use, reason: str, said: str = "no use figures yet") -> Safe:
    """The chart of use of a resource that has none to draw: the title, what is missing, and why."""
    return fmt('<figure class="chart"><figcaption>{title} <span>{said}</span></figcaption><p class="m">{reason}</p></figure>', title=use.title, said=said, reason=reason)


def _use_scale(use: Use, peak: float) -> tuple[float, float, str]:
    """The ceiling of a chart of use and what its labels divide by and end with: a round number that is not below the largest value, holds the line of the kind with room above it, and (for
    a count) is not below 2, so that the line in the middle is a whole number."""
    divisor, suffix = scale_of(use.unit, peak)
    if use.unit == "bytes" and peak == 0:
        divisor, suffix = 1024.0, "KB"
    ceiling = _nice_use(max(peak, 1.5 * (use.threshold or 0.0)) / divisor) * divisor
    return (max(2.0, ceiling) if use.unit == "count" else ceiling), divisor, suffix


def _runs(values: Sequence[float | None], left: float, step: float, at: Callable[[float], float]) -> list[list[tuple[float, float]]]:
    """The stretches of days that have a value, as points of the chart: a day with no value ends a stretch, so that the line is broken there."""
    runs: list[list[tuple[float, float]]] = []
    inside = False
    for i, value in enumerate(values):
        if value is None:
            inside = False
            continue
        if not inside:
            runs.append([])
            inside = True
        runs[-1].append((left + i * step, at(value)))
    return runs


def _use_days(end: str | None, today: dt.date | None, days: int, last_index: int) -> tuple[str, str, str]:
    """The two labels of the time axis and the day of the last value in the caption: "yesterday" when it was yesterday, else the date, else "the last day"."""
    last = kept_day(end)
    if last is None:
        return "first day", "last day", "the last day" if last_index == days - 1 else "the last day with data"
    yesterday = today - dt.timedelta(days=1) if today is not None else None
    value_day = last - dt.timedelta(days=days - 1 - last_index)
    when = "yesterday" if value_day == yesterday else _short_day(value_day)
    if last == yesterday:
        return f"{days} days ago", "yesterday", when
    return _short_day(last - dt.timedelta(days=days - 1)), _short_day(last), when


def _path(run: list[tuple[float, float]]) -> str:
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in run)


def use_chart(use: Use, values: Sequence[float | None], end: str | None = None, today: dt.date | None = None) -> Safe:
    """The large chart of the use of a resource: the value of each of the last days on a scale that starts at zero and has a round ceiling that holds the line of its kind with room above it.
    A day with no value is a gap: the line is broken there (and a value with no neighbour is a dot). The last day with a value has a dot, the line of the kind (when it has one) is dashed
    and named, and a sentence says in words what the chart shows. `end` is the day that the series ends on and `today` the day it is now (UTC): they decide whether the chart says "yesterday"."""
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(values) < SERIES_MIN or not present:
        return use_quiet(use, USE_LATER)
    left, right, top, bottom = PLOT
    middle = (top + bottom) // 2
    ceiling, divisor, suffix = _use_scale(use, max(v for _, v in present))

    def at(value: float) -> float:
        return bottom - (bottom - top) * value / ceiling

    runs = _runs(values, left, (right - left) / (len(values) - 1), at)
    drawn = [run for run in runs if len(run) > 1]
    last_point = runs[-1][-1]
    line = " ".join(_path(run) for run in drawn)
    area = " ".join(f"{_path(run)} L{run[-1][0]:.1f},{bottom} L{run[0][0]:.1f},{bottom} Z" for run in drawn)
    lone = "".join(f'<circle class="dt" cx="{x:.1f}" cy="{y:.1f}" r="2"/>' for run in runs if len(run) == 1 and run[0] != last_point for x, y in run)
    grid = "".join(f'<line class="gl" x1="{left}" y1="{y}" x2="{right}" y2="{y}"/>' for y in (top, middle, bottom))
    labels = join(fmt('<text class="ax" x="{x}" y="{y}" text-anchor="end">{text}</text>', x=left - 6, y=y + 4, text=axis_text(use.unit, value, divisor, suffix))
                  for y, value in ((top, ceiling), (middle, ceiling / 2), (bottom, 0)))
    start_label, end_label, when = _use_days(end, today, len(values), present[-1][0])
    axes = join([fmt('<text class="ax" x="{x}" y="110">{text}</text>', x=left, text=start_label),
                 fmt('<text class="ax" x="{x}" y="110" text-anchor="end">{text}</text>', x=right, text=end_label)])
    threshold = Safe("")
    if use.threshold is not None:
        y = at(use.threshold)
        threshold = fmt('<line class="thr" x1="{left}" y1="{y}" x2="{right}" y2="{y}"/><text class="thr-t" x="{x}" y="{up}" text-anchor="end">{label}</text>', left=left, right=right,
                        y=f"{y:.1f}", x=right - 4, up=f"{y - 4:.1f}", label=use.threshold_label)
    caption = ", ".join(part for part in (use.daily, f"last {len(values)} days", f"yesterday {value_text(use.unit, present[-1][1])}" if when == "yesterday"
                                          else f"{value_text(use.unit, present[-1][1])} on {when}") if part)
    words = f"{use.title}{f' ({use.daily})' if use.daily else ''} for the last {len(values)} days: {describe_use(use, values)}"
    shape = fmt('<path class="ar" d="{area}"/><path class="ln" d="{line}"/>', area=area, line=line) if drawn else Safe("")
    return fmt('<figure class="chart"><figcaption>{title} <span>{caption}</span></figcaption>'
               '<svg viewBox="0 0 360 112" role="img" aria-label="{words}">{grid}{labels}{axes}{threshold}{shape}{lone}<circle class="dt" cx="{x}" cy="{y}" r="3"/></svg></figure>',
               title=use.title, caption=caption, words=words, grid=Safe(grid), labels=labels, axes=axes, threshold=threshold, shape=shape, lone=Safe(lone), x=f"{last_point[0]:.1f}",
               y=f"{last_point[1]:.1f}")


def use_block(members: Sequence[tuple[Brief, CaseRecord | None]], now: dt.datetime) -> Safe:
    """What a decision card shows of use, under the chart of its cost: nothing for a resource of a type that has no kind of use; the chart when the case has a series of use; and, for a type
    that has one and a case that has none yet, the same figure made quiet, with the reason (a finding about many resources has none, and says so). `members` are the requests that the card
    stands for, each with its case: one for a card, several for a row that stands for many, which draws the sum of their use only for a kind that may be added and only when each has a series
    of it."""
    today = utc(now).date()
    if len(members) == 1:
        brief, case = members[0]
        if brief.group is not None:
            kind = entry_of(brief.group.kind)
            return use_quiet(kind, USE_MANY, "not drawn") if kind is not None else Safe("")
        kind = entry_of(case.resource_type) if case is not None else None
        if kind is None:
            return Safe("")
        data = use_of(case)
        return use_chart(data.use, data.values, data.end, today) if data is not None else use_quiet(kind, USE_LATER)
    total = use_summed([use_of(case) for _, case in members])
    return use_chart(total.use, total.values, total.end, today) if total is not None else Safe("")


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
