"""What a case comes to: code decides, from the two answers and the guards. A model's answer can only make a case weaker."""
from __future__ import annotations

from dataclasses import dataclass

from .detectors import ADVISOR, Lead
from .guards import Guards
from .roles import DetectiveAnswer, SkepticAnswer

PROPOSE_CONFIDENCE = 0.7
STATUSES = ("proposed", "needs_human", "dropped", "error")
# A case is proposed under the same conditions for a recommendation to delete the resource and for one to change it (a smaller size, another tier).
PROPOSALS = ("delete", "change")


@dataclass(frozen=True)
class Decision:
    status: str
    recommendation: str
    confidence: float
    summary: str
    objections: tuple[str, ...]
    guards: list[str]
    monthly_saving_usd: float | None


def saving_of(lead: Lead) -> float | None:
    """What removing the resource would save in a month: Advisor's own figure for an Advisor lead, else the resource's 30-day cost lines."""
    if lead.detector == ADVISOR and lead.advisor_saving_usd is not None:
        return lead.advisor_saving_usd
    return lead.cost_usd_30d


def decide(lead: Lead, guards: Guards, detective: DetectiveAnswer, skeptic: SkepticAnswer | None) -> Decision:
    if detective.recommendation == "keep":
        status = "dropped"
    elif guards.names:
        status = "needs_human"
    elif skeptic is None or skeptic.verdict != "agree":
        status = "needs_human"
    elif detective.recommendation in PROPOSALS and detective.confidence >= PROPOSE_CONFIDENCE:
        status = "proposed"
    else:
        status = "needs_human"
    saving = None
    if status != "dropped":
        if detective.recommendation == "delete":
            saving = saving_of(lead)
        elif detective.recommendation == "change":
            saving = lead.advisor_saving_usd  # a change has no figure of its own: only Advisor's, when a finding cites one
    objections = skeptic.objections if skeptic else ()
    if skeptic and not objections and skeptic.verdict != "agree" and skeptic.summary:
        objections = (skeptic.summary,)
    return Decision(status, detective.recommendation, detective.confidence, detective.summary, objections, guards.names, saving)
