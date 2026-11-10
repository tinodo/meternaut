"""What is at stake in a request, as the plain lines that a letter and a Teams card say.

The page of a request, the letter and the card show one figure, and it comes from one piece of code: `figure_of`, `a_year`, `dollars` and `title_of` of cases/web/figures.py, which the pages
use, and the cost of the finding that the brief holds (`Brief.cost`, the number that the pages read with `cost_of`; a test holds the two to each other). This module only sets what that code
works out into lines, so that the three can never differ: the figure a year (whole dollars, twelve times the month) and a month (cents), its label ("Saves, Expected", "Costs, saving not
measured" or "Cost not visible") and its basis or its reason in one line, the title, the place under it, the risk, how sure the AIs are and what a change leaves behind, each as words. It
holds no markup: the letter lays the lines out as HTML and as text, the card as TextBlocks.

Nothing here reads a clock, a store or the network. A letter and a card say neither how long a request has waited nor what waiting costs: that is on the page, and it pushes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .brief import Brief
from .models import CaseRecord
from .web.figures import RISKS, Figure, a_year, dollars, figure_of, title_of
from .web.home import Row, unit_title, units_of

MONEY = "Money is in US dollars, and a year is twelve times the month."  # the page says it in the same words, once under its figure


@dataclass(frozen=True)
class Stake:
    """The figure of one request in words. `year` and `month` are empty when there is no figure to show (state none), and then `note` says why."""

    state: str  # save, cost or none, as web/figures.Figure
    level: str  # Verified, Expected or Scenario for a saving, empty otherwise
    label: str
    year: str  # "$1,682 a year"
    month: str  # "$140.16"
    note: str  # the basis ("Based on the cost lines of the last 30 days.") or the reason
    monthly: float | None = None  # the figure of a month as a number, for the order of a list

    @property
    def line(self) -> str:
        """The line under the figure, as the page has it: the label, the month and the basis or the reason."""
        return " ".join(part for part in (f"{self.label}.", f"{self.month} a month." if self.month else "", self.note) if part)

    @property
    def short(self) -> str:
        """The figure in a few words, for a list of requests: "$1,682 a year, Expected", "costs $4,297 a year, saving not measured" or "cost not visible"."""
        if self.state == "save":
            return f"{self.year}, {self.level}"
        return f"costs {self.year}, saving not measured" if self.state == "cost" else "cost not visible"

    @property
    def money(self) -> str:
        """The one line that says what the money is in: only where a figure is shown."""
        return MONEY if self.year else ""


def stake_of_figure(figure: Figure, note: str | None = None) -> Stake:
    """The figure of the page (a request's, or a row's that stands for several) in words: its year, its month, its label and its basis, or what is known when there is no figure."""
    note = figure.note if note is None else note
    if figure.monthly is None:
        return Stake(figure.state, "", figure.label, "", "", note)
    return Stake(figure.state, figure.level, figure.label, f"{a_year(figure.monthly)} a year", dollars(figure.monthly), note, figure.monthly)


def stake_of(brief: Brief) -> Stake:
    """The figure of a request as its page shows it: a saving when the brief has one (with its level and its basis), else what the finding costs in 30 days (the most that a change could
    save, which nothing has measured), else nothing, and why. A finding's own reason for having no saving takes the place of the general one. The cost is the brief's own (`Brief.cost`),
    the number that the page reads with `cost_of`: a test holds the two to each other."""
    figure = figure_of([brief.saving], [brief.cost])
    return stake_of_figure(figure, figure.note if figure.state == "save" or not brief.saving.specific else brief.saving.why_none)


def title_text(brief: Brief) -> str:
    """The title of the request as its page has it ("Review the disk x", "Delete the unattached disk x"), as plain text: the place is not in it."""
    return title_of(brief)[1]


@dataclass(frozen=True)
class Decision:
    """One row of the Decisions page as a letter lists it: the title and the figure that the page has for it, and the request when the row stands for one request. A row for findings of
    one kind about several resources has no request of its own: it opens on the page."""

    title: str
    stake: Stake
    brief: Brief | None


def decisions_of(waiting: Sequence[tuple[Brief, CaseRecord | None, bool]]) -> list[Decision]:
    """The rows that the Decisions page shows for these requests (each a brief, its case and whether the person put it off), in its order: what is at stake first, what a person put off last.
    The code of the page groups and ranks them, so a letter counts what the page counts and never lists the same kind of finding once for each resource."""
    units = units_of([Row(brief, case, later) for brief, case, later in waiting])
    return [Decision(unit_title(unit), stake_of_figure(unit.figure), unit.first.brief if len(unit.members) == 1 else None) for unit in units]


def place_of(brief: Brief) -> str:
    """The line under the title: what kind of resource, and in which resource group. A request for many resources has none: its title counts them and the groups that they are in."""
    if brief.group is not None:
        return ""
    group = f"resource group {brief.where.group}" if brief.where.group else ""
    return ", ".join(bit for bit in (brief.where.kind, group) if bit)


def chips_of(brief: Brief) -> tuple[str, ...]:
    """The chips of the page as words (a letter has no shapes): the risk, how sure the AIs are, and what a change leaves behind, or that an answer changes nothing in Azure."""
    chips = [RISKS.get(brief.risk.level, RISKS["medium"])[0], f"{brief.confidence.level} confidence"]
    if brief.kind == "change":
        chips.append("Can be undone" if brief.undo.reversible else "Cannot be undone")
    elif brief.kind == "advice":
        chips.append("Changes nothing in Azure")
    return tuple(chips)
