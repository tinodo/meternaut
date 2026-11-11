"""A second person for a larger change: the first confirms the plan, the second approves it and signs in to Azure.

A rule (models.TwoPeopleRule, set by the owner on the page of the platform team, off by default) names an amount that a change saves in a month and the kinds of change that always need two
people. A plan that the rule covers when it is made gets the approval class R3 (models.TWO_PEOPLE_CLASS). The class is a field of the plan, so it is in the plan's digest
(cases/families/digest.py): a plan cannot be turned into a one-person plan afterwards, whatever the rule says later. What the class asks:

1. Two DIFFERENT people from the list of approvers of the plan, told apart by their directory object ids.
2. The first gives a confirmation of the plan as it is: a decision of the kind `confirm` that records the plan's code and its digest. It makes no change and needs no sign-in to Azure, and it
   is taken on the page only, never on a card. Nobody who confirmed can be the second person.
3. The second person gives the approval that makes the change, as for every other change: their own sign-in to Azure, the digest bound into it, and the change made with their own
   permissions. It is refused until a confirmation of this exact plan, by somebody else, is recorded. The runner checks it once more before it acts.
4. Either can refuse: a decline or "not mine" by either ends the request. A plan that changed in any field after the confirmation has another digest, and the confirmation does not count.

What this does not stop: two accounts of one human are two people here, and an approver who agrees to a wrong plan agrees to it. Nothing here reads who a person is beyond the object id that
the platform's sign-in gives.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import ADVISE, TWO_PEOPLE_CLASS, DecisionRecord, PlanRecord, TwoPeopleRule

CLASS = TWO_PEOPLE_CLASS
# Why a person may not give the second approval, as plain sentences. Each ends in "Nothing is approved."
ALONE = "This change needs two people, and fewer than two are listed as approvers of this request, so nobody can approve it. Nothing is approved."
FIRST = "This change needs two people. Nobody has confirmed the request yet: one person confirms it, and then another approves it and signs in to Azure. Nothing is approved."
MINE = "You confirmed this request yourself, so a second person has to approve it and sign in to Azure. Nothing is approved."
STALE = "The request changed after {name} confirmed it, so that confirmation does not count any more. It has to be confirmed again. Nothing is approved."


def applies(rule: TwoPeopleRule, family: str, saving_usd_month: float | None) -> bool:
    """Whether the rule covers a change of this family with this saving: the family is named, or the saving is at least the amount. A saving that is not known reaches no amount."""
    if family in rule.families:
        return True
    return rule.min_usd_month is not None and saving_usd_month is not None and saving_usd_month >= rule.min_usd_month


def needs(plan: PlanRecord | None) -> bool:
    """A change of the class R3. A plan of advice changes nothing in Azure and never needs two people."""
    return plan is not None and plan.family != ADVISE and plan.approval_class == CLASS


def _named(plan: PlanRecord) -> set[str]:
    return {a.lower() for a in plan.approvers}


def confirmations(plan: PlanRecord, decisions: Sequence[DecisionRecord]) -> list[DecisionRecord]:
    """Every confirmation by a person named on the plan, of this plan or of an earlier form of it, oldest first."""
    named = _named(plan)
    return sorted((d for d in decisions if d.decision == "confirm" and d.approver_oid.lower() in named), key=lambda d: (d.at, d.approver_oid))


def counts(plan: PlanRecord, confirmation: DecisionRecord) -> bool:
    """Whether a confirmation is of this exact plan: its code and its digest are the plan's, and the plan has a digest."""
    return bool(plan.digest) and confirmation.plan_code == plan.code and confirmation.plan_digest == plan.digest


@dataclass(frozen=True)
class Standing:
    """Where a request that needs two people stands for one person. `stage`: `alone` (fewer than two people can approve it), `first` (nobody has confirmed it: this person may), `second`
    (somebody else confirmed it: this person may approve it), `mine` (this person confirmed it) or `stale` (it was confirmed and then changed: it has to be confirmed again). `by` and `at`
    are the name of the person who confirmed it, as the list of people has it, and when; empty for `first` and `alone`."""

    stage: str
    by: str = ""
    at: str = ""


def standing(plan: PlanRecord, decisions: Sequence[DecisionRecord], person: str = "") -> Standing:
    """The stage of a request of the class R3 for `person` (an object id; empty for a reader that is not a person, such as a letter)."""
    if len(_named(plan)) < 2:
        return Standing("alone")
    me = (person or "").lower()
    found = confirmations(plan, decisions)
    good = [d for d in found if counts(plan, d)]
    mine = next((d for d in good if d.approver_oid.lower() == me), None) if me else None
    if mine is not None:
        return Standing("mine", mine.approver_name, mine.at)
    if good:
        last = good[-1]
        return Standing("second", last.approver_name, last.at)
    if found:
        last = found[-1]
        return Standing("stale", last.approver_name, last.at)
    return Standing("first")


def problem(plan: PlanRecord, decisions: Sequence[DecisionRecord], person: str) -> str:
    """Why `person` may not give the approval that makes the change, or an empty text when they may: somebody who did not confirm the plan approves it, after a confirmation of this
    exact plan by another person."""
    found = standing(plan, decisions, person)
    if found.stage == "second":
        return ""
    return {"alone": ALONE, "first": FIRST, "mine": MINE}.get(found.stage) or STALE.format(name=found.by or "a person")


def satisfied(plan: PlanRecord, decisions: Sequence[DecisionRecord]) -> bool:
    """Whether the decisions hold what the class asks for this exact plan: an approval of it by a named person, and a confirmation of it by another named person. The runner asks this
    right before it acts."""
    named = _named(plan)
    approvals = [d for d in decisions if d.decision == "approve" and d.plan_code == plan.code and d.plan_digest == plan.digest and d.approver_oid.lower() in named]
    good = [d for d in confirmations(plan, decisions) if counts(plan, d)]
    return any(c.approver_oid.lower() != a.approver_oid.lower() for a in approvals for c in good)
