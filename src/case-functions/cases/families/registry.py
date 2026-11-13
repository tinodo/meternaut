"""The registry of the families of change (AGENTS.md rule 26 (a)).

A new kind of change is a new family: a class in one of the modules of this package, an entry in `REGISTRY` below, and its words in words.py. Nothing else in the app has to know its name:
the approval loop, the runner, the sign-in and the decision brief all go through the registry (and the brief through words.py, which holds no way to reach Azure).
"""
from __future__ import annotations

from .base import Family
from .disk import ChangeDiskTier, DeleteDisk
from .gates import ChangeScope
from .gateway import ScaleVpnGateway
from .idle import DeleteIdleResource
from .public_ip import DeletePublicIp
from .vm import ResizeVm, StopVm
from .words import SHOWN

REGISTRY: tuple[Family, ...] = (DeleteDisk(), DeletePublicIp(), StopVm(), ResizeVm(), ChangeDiskTier(), DeleteIdleResource(), ScaleVpnGateway())
BY_NAME = {family.name: family for family in REGISTRY}
# The older detectors lead to a family by their own name; they stay only for waste that Meternaut plants itself (AGENTS.md rule 30 (c)).
DETECTOR_FAMILY = {detector: family.name for family in REGISTRY for detector in family.detectors}
INVESTIGATION = "investigation"

if len(BY_NAME) != len(REGISTRY) or set(BY_NAME) != set(SHOWN):
    # A family that nobody can read about is not offered to a person: this stops the app at its first import, long before a plan is made.
    raise RuntimeError("every family of the registry needs its words in families/words.py, and every entry there a family: " + ", ".join(sorted(set(BY_NAME) ^ set(SHOWN))))
if any(family.summary != SHOWN[family.name].summary for family in REGISTRY):
    # The pages that cannot import the registry (they reach no Azure code) say what a family does with the phrase in words.py: it has to be the family's own.
    raise RuntimeError("the summary of every family in families/words.py must be the family's own: " + ", ".join(f.name for f in REGISTRY if f.summary != SHOWN[f.name].summary))


def get(name: str | None) -> Family | None:
    """The family of this name, or None. `advise` is not one: it changes nothing and has no entry here."""
    return BY_NAME.get(name or "")


def names() -> tuple[str, ...]:
    return tuple(BY_NAME)


def candidates(detector: str, resource_type: str, recommendation: str | None) -> list[Family]:
    """The families that a finding may lead to, in the order of the registry. A lead of an older detector has its own family; a case of the investigation leads to the families that match
    the type of its resource and are selected by its recommendation. The model's recommendation only chooses among these: it makes no plan and gives no parameter of one."""
    if detector == INVESTIGATION:
        return [family for family in REGISTRY if family.matches(resource_type) and family.selects(recommendation)]
    family = BY_NAME.get(DETECTOR_FAMILY.get(detector, ""))
    return [family] if family is not None and family.selects(recommendation) else []


def acts_on(planted_tag: str, scopes: tuple[ChangeScope, ...]) -> str:
    """What the function app says that Meternaut changes, in one sentence, made from the registry and the scopes so that it is never typed by hand a second time."""
    groups = " and ".join(scope.group for scope in scopes)
    kinds = "; ".join(family.summary for family in REGISTRY)
    return (f"one of these, on a resource that Meternaut planted itself, that carries the tag {planted_tag} and is in resource group {groups}, and nowhere else: {kinds}")
