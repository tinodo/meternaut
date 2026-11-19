"""What is at stake in a request, as the plain sentences that a letter and a Teams card say.

The page of a request, the letter and the card show one figure, and it comes from one piece of code: `figure_for`, `says`, `a_year_text`, `dollars` and `title_of` of cases/web/figures.py, which the
pages use, and the cost of the finding that the brief holds (`Brief.cost`, the number that the pages read with `cost_of`; a test holds the two to each other). This module only sets what that code
works out into sentences, so that the three can never differ: the sentence that opens the money block ("Meternaut worked out that this could save about $1,682 a year ($140 a month)." or "It costs
$848 a month, about $10,180 a year."), the sentences under it (what the figure rests on, or that nobody has worked out the saving, or why not), the title, the place under it, the risk, how sure the
AIs are and what a change leaves behind, each as words. It holds no markup: the letter lays the lines out as HTML and as text, the card as TextBlocks.

Nothing here reads a clock, a store or the network. A letter and a card for a request that was just made say neither how long it has waited nor what waiting costs; the messages of an escalation do
(`waited_line`), because the owner's rule is that a request that waits is never silent (AGENTS.md rule 38), and the page of a request says it too.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from . import estimate as estimates
from .brief import IF_ACTED, Brief, waiting_cost
from .models import CaseRecord
from .web.figures import RISKS, Figure, figure_for, says, short_of, title_of
from .web.home import Row, unit_title, units_of

NOTE_CHARS = 840  # the most of the sentences under the figure that a card shows, and with the first one, the most that a letter shows: the longest basis of a figure fits (a test in test_pricing.py: a switch with both names at 40 characters and every number at its longest is 810 characters)
LINE_CHARS = NOTE_CHARS + 70


@dataclass(frozen=True)
class Stake:
    """The figure of one request in words. `lead` is the sentence that opens the money block and `note` the sentences under it (what the figure rests on, or that nobody has worked out the saving,
    or why none was); a row of a list that stands for several requests has no `lead`, only its `short` sentence. With no figure to show (state none) `monthly` is None and `note` or `lead` says why."""

    state: str  # save, cost or none, as web/figures.Figure
    level: str  # Verified, Expected or Scenario for a saving, empty otherwise
    note: str
    monthly: float | None = None  # the figure of a month as a number, for the order of a list
    lead: str = ""
    made_of: str = ""  # what the cost of a whole subscription or resource group is made of ("It is made of Virtual Network $88.10, ...")
    estimate: str = ""  # the estimate at list price for a disk that Azure has no cost line for, with its label and the date of its price table: never part of the figure

    @property
    def extra(self) -> str:
        """What the page puts under the money sentences: what a whole subscription or resource group costs is made of, and the estimate at list price. Each says what it is."""
        return " ".join(part for part in (self.made_of, self.estimate) if part)

    @property
    def short(self) -> str:
        """The figure in one sentence, for a list of requests: "It could save about $1,682 a year.", "It costs $4,297 a year; nobody has worked out the saving." or the reason why there is none."""
        return short_of(self.state, self.level, self.monthly, self.lead or self.note)


def stake_of_figure(figure: Figure, note: str | None = None) -> Stake:
    """The figure of the page (a request's, or a row's that stands for several) in words: its basis, or what is known when there is no figure, and, under it, what the cost is made of and the
    estimate at list price when the figure has them."""
    return Stake(figure.state, figure.level if figure.monthly is not None else "", figure.note if note is None else note, figure.monthly, "", figure.made_of,
                 estimates.words(figure.estimate) if figure.estimate is not None else "")


def stake_of(brief: Brief) -> Stake:
    """The figure of a request as its page shows it: a saving when the brief has one (with its level and its basis), else what the finding costs in 30 days (the most that a change could save,
    which nothing has measured), else nothing, and why. A finding's own reason for having no saving takes the place of the general one. The cost is the brief's own (`Brief.cost`), the number that the
    page reads with `cost_of`: a test holds the two to each other."""
    figure = figure_for([brief], [brief.cost])
    lead, note = says(brief, figure)
    return replace(stake_of_figure(figure, note), lead=lead)


def waited_line(stake: Stake, days: int, before: float = 0.0, own: int | None = None) -> str:
    """What waiting has cost so far, by code (brief.waiting_cost), as a sentence: the figure of a month over thirty days, for the days that the request has waited, in whole dollars. A Scenario figure
    says "about". A request that stands for others adds what they cost (`before`) to what it has cost in the `own` days since it was made. Empty when the request has no measured saving: waiting
    cost nothing that anybody measured, and the message then says so in its own words."""
    return waiting_cost(stake.monthly if stake.state == "save" else None, stake.level, days, before, own)


def title_text(brief: Brief) -> str:
    """The title of the request as its page has it ("Look at the disk x", "Delete the unattached disk x"), as plain text: the place is not in it."""
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
    """The line under the title: what kind of resource, in which resource group and in which subscription (by its name, when it was read: a person reads a name before an id; the title of a
    request about a subscription has the name already). A request for many resources has none: its title counts them and the groups that they are in."""
    if brief.group is not None:
        return ""
    group = f"resource group {brief.where.group}" if brief.where.group else ""
    named = f"subscription {brief.where.subscription_name}" if brief.where.subscription_name and brief.scope != "subscription" else ""
    return ", ".join(bit for bit in (brief.where.kind, group, named) if bit)


def chips_of(brief: Brief) -> tuple[str, ...]:
    """The chips of the page as words (a letter has no shapes): the risk (of acting, for advice: answering changes nothing), how sure the AIs are, and what a change leaves behind, or that an
    answer changes nothing in Azure."""
    chips = [RISKS.get(brief.risk.level, RISKS["medium"])[0] + (IF_ACTED if brief.risk.acting else ""), f"{brief.confidence.level} confidence"]
    if brief.kind == "change":
        chips.append("Can be undone" if brief.undo.reversible else "Cannot be undone")
    elif brief.kind == "advice":
        chips.append("Answering changes nothing in Azure")
    return tuple(chips)
