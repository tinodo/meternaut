"""What the families that delete have in common: the plan text, the re-check, the call and the check afterwards.

A family that deletes (an unattached disk, an unassigned public IP address, and the closed list of idle resources) writes one plan text from the lead, re-checks one state of the
resource, makes one DELETE and reads until Azure says that the resource is gone. Each has its own wording and its own state check; the rest is here, so that the text of two families
that delete never differs for a reason that is not theirs.
"""
from __future__ import annotations

from ..http import HttpError, Refused
from ..models import CaseRecord, PlanRecord
from ..roles import clean_text
from . import calls
from .base import Env, Family, Located, Planned, Stop, Unreadable, Verdict, evidence_text, skeptic_sentence
from .calls import Kind
from .gates import Gates
from .words import DELETE_WORDING, Wording

GONE = "Deleted. Azure no longer lists the resource."
STILL_THERE = "Azure still lists the resource."


class DeleteFamily(Family):
    """A family whose change is one DELETE of a resource that nothing uses."""

    deletes = True

    def wording(self, kind: Kind) -> Wording:
        """The words of the kind that this family deletes, which are in words.py (the brief reads them from there too)."""
        return DELETE_WORDING[kind.type]

    def why_not_idle(self, located: Located, resource: dict) -> str | None:
        """None when the resource, as Azure shows it, is not used by anything; else the plain reason why not. The check that is the family's own."""
        raise NotImplementedError

    def check_state(self, env: Env, plan: PlanRecord, located: Located, resource: dict) -> None:
        why = self.why_not_idle(located, resource)
        if why is not None:
            raise Stop(why)

    def facts(self, env: Env, lead: object, located: Located) -> dict:
        resource = self.snapshot(env, located)
        why = self.why_not_idle(located, resource)
        if why is not None:
            raise Unreadable(why)
        return {"idle": True}

    def snapshot(self, env: Env, located: Located) -> dict:
        """The resource as Azure shows it, for a plan: Unreadable when it cannot be read, or is gone."""
        try:
            resource = self.read(env, located)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        if resource is None:
            raise Unreadable("the resource does not exist any more")
        return resource

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned | str:
        w = self.wording(located.kind)
        group = clean_text(getattr(lead, "resource_group"), 90)
        name = clean_text(getattr(lead, "name"), 120)
        return Planned(
            title=f"{w.title} in resource group {group}",
            what_changes=(f"When you approve and sign in to Azure, Meternaut deletes the {w.noun} named {name} in resource group {group} "
                          f"(subscription {getattr(lead, 'subscription_id')[:8]}) with your own permissions. It changes nothing else. "
                          f"Right before it deletes, it reads the resource again and stops unless {w.recheck}."),
            could_go_wrong=(f"{w.gone_wrong} If your account may not delete the resource, Azure refuses and nothing changes. {skeptic_sentence(case)}"),
            undo=w.undo, evidence=evidence_text(lead, w.observed), saving_usd_month=self.saving(case, lead, facts), target={},
            preconditions={"family": self.name, "resourceType": getattr(lead, "resource_type"), "tag": gates.planted_tag, "resourceGroup": getattr(lead, "resource_group").lower()})

    def call(self) -> calls.Call:
        return calls.write_for(calls.DELETE, self.kinds[0])

    def write(self, env: Env, plan: PlanRecord, located: Located):
        return env.azure.write(calls.write_for(calls.DELETE, located.kind), located.url())

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        located = self.locate(plan.resource_id, env.gates)
        try:
            env.azure.get(located.url())
        except HttpError as error:
            if error.status == 404:
                return Verdict("done", GONE, {"gone": True})
            return Verdict("unknown", "The resource could not be read, so it is not known whether it is gone.")
        except Refused:
            return Verdict("unknown", "The resource could not be read, so it is not known whether it is gone.")
        return Verdict("pending", STILL_THERE, {"gone": False})

    def needs_reads(self, lead: object) -> bool:
        """A lead of an older detector says by its query that the resource is not used (Resource Graph lists it as unattached or unassigned), and the re-check right before the change reads it
        again. A lead of the investigation says nothing of the kind, so the plan reads the resource first."""
        return getattr(lead, "detector", "") not in self.detectors
