"""What a person reads of each family of change: the words that the decision brief shows for a plan.

The decision brief (cases/brief.py) shows a plan of any family with the same fields: the request in one line, what changes, what is read again, what could go wrong, how big the saving is
and how sure it is, and whether the change can be undone. Each family supplies those words here, written by code from its own kind of change and from the typed values of the plan, never by
a model and never from text of the estate (the name and the group arrive already cut to one line by the brief). So a page, a letter and a card show a new family without a line of their own.

This module imports only the standard library and the records, so that whatever renders a decision can show a family without being able to reach Azure by importing it. What a family does
in Azure is in the modules next to this one. A family that has no entry in `SHOWN` is refused when the registry is first imported (registry.py), and a test holds the two lists together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..models import PlanRecord

# What a plan of a delete says that its re-check looks at: the words are those of the two families that were first, and a test holds them.
RE_CHECK = ("the resource is still unattached or unassigned, still carries the tag that marks it as planted by Meternaut, is still in this resource group "
            "and has no management lock")
SIZE_NAME = re.compile(r"[A-Za-z]{1,10}_[A-Za-z0-9_]{1,40}")
RESOURCE_TYPE = re.compile(r"microsoft\.[a-z0-9]{2,30}/[a-z0-9]{2,40}")


@dataclass(frozen=True)
class Words:
    """What the decision brief shows for a plan of one family."""

    headline: str  # the request in one line: a verb, the thing and the place
    change: str
    rechecked: str
    risk: str
    level: str  # low, medium or high
    undo: str
    reversible: bool


@dataclass(frozen=True)
class Wording:
    """The words of one kind of resource that a family deletes: for the plan (what code writes when the plan is made) and for the brief."""

    noun: str  # the resource in a sentence
    title: str  # a verb and an object: "Delete an unattached managed disk"
    verb: str  # the headline: "Delete the unattached disk"
    state: str  # what the resource still is when it is deleted: "unattached"
    observed: str  # what code read, for the evidence of the plan
    risk: str
    undo: str  # in the plan
    recheck: str = RE_CHECK
    level: str = "medium"
    gone_wrong: str = "If something still uses the resource, that use stops. The re-check stops the change when anything is attached or assigned."
    brief_undo: str = ""  # in the brief, when it says it shorter than the plan does


def _idle(noun: str, title: str, verb: str, state: str, observed: str, recheck: str, risk: str, undo: str) -> Wording:
    return Wording(noun=noun, title=title, verb=verb, state=state, observed=observed, risk=risk, undo=undo, recheck=recheck, gone_wrong=f"{risk} The re-check stops the change when the resource is in use.")


# The words of every kind that a family deletes, by the type of the resource as Resource Graph names it (lower case).
DELETE_WORDING = {
    "microsoft.compute/disks": Wording(
        noun="disk", title="Delete an unattached managed disk", verb="Delete the unattached disk", state="unattached",
        observed="Azure Resource Graph lists the resource as unattached or unassigned and as planted by Meternaut.",
        risk="If something still uses the disk, that use stops, and the data on it is lost for good.",
        undo="A deleted disk cannot be restored and its data is lost. A new disk with the same name can be made, empty.",
        brief_undo="A deleted disk cannot be restored. A new, empty disk can be made."),
    "microsoft.network/publicipaddresses": Wording(
        noun="public IP address", title="Delete an unassigned public IP address", verb="Delete the unassigned public IP address", state="unassigned",
        observed="Azure Resource Graph lists the resource as unattached or unassigned and as planted by Meternaut.",
        risk="If something still points at the address, that traffic stops, and the same address may not be given again.",
        undo="A deleted public IP address cannot be restored. The address is released and may not be given again; a new one can be made.",
        brief_undo="A deleted public IP address cannot be restored. The address is released, and a new one can be made."),
    "microsoft.compute/snapshots": _idle(
        "snapshot", "Delete a snapshot", "Delete the snapshot", "not in use",
        "Azure shows the snapshot as finished and not in use, and as planted by Meternaut.",
        "the snapshot is still finished and not in use, still carries the tag that marks it as planted by Meternaut, is still in this resource group and has no management lock",
        "The data in the snapshot is lost for good: if a disk or a restore still needs it, that need is lost.",
        "A deleted snapshot cannot be restored. A new snapshot can be taken of the disk, if the disk still exists."),
    "microsoft.network/networkinterfaces": _idle(
        "network interface", "Delete an unattached network interface", "Delete the unattached network interface", "unattached",
        "Azure shows the network interface as belonging to no machine, no private endpoint and no load balancer, and as planted by Meternaut.",
        "the network interface still belongs to no machine, no private endpoint and no load balancer, still carries the tag that marks it as planted by Meternaut, is still in this "
        "resource group and has no management lock",
        "If something still uses the interface or its settings, that use stops. A public IP address that it holds stays and keeps billing.",
        "A deleted network interface cannot be restored. A new one can be made, with another private address."),
    "microsoft.network/natgateways": _idle(
        "NAT gateway", "Delete a NAT gateway that serves no subnet", "Delete the NAT gateway that serves no subnet", "serving no subnet",
        "Azure shows the NAT gateway as serving no subnet, and as planted by Meternaut.",
        "the NAT gateway still serves no subnet, still carries the tag that marks it as planted by Meternaut, is still in this resource group and has no management lock",
        "If a subnet still sends its outbound traffic through the gateway, that traffic stops. The public IP addresses of the gateway stay and keep billing.",
        "A deleted NAT gateway cannot be restored. A new one can be made and attached to the subnets again."),
    "microsoft.network/loadbalancers": _idle(
        "load balancer", "Delete a load balancer with no backends and no rules", "Delete the load balancer with no backends and no rules", "without backends and rules",
        "Azure shows the load balancer as having no rules and no backend that has a member, and as planted by Meternaut.",
        "the load balancer still has no rules and no backend with a member, still carries the tag that marks it as planted by Meternaut, is still in this resource group and has no "
        "management lock",
        "If something still sends traffic to a frontend of the load balancer, that traffic stops. Its public IP addresses stay and keep billing.",
        "A deleted load balancer cannot be restored. A new one can be made and set up again."),
    "microsoft.network/privateendpoints": _idle(
        "private endpoint", "Delete a disconnected private endpoint", "Delete the disconnected private endpoint", "disconnected",
        "Azure shows every connection of the private endpoint as Disconnected, and the endpoint as planted by Meternaut.",
        "every connection of the private endpoint is still Disconnected, it still carries the tag that marks it as planted by Meternaut, is still in this resource group and has no "
        "management lock",
        "If the service that it pointed at is connected again, the endpoint has to be made again. Its network interface goes with it.",
        "A deleted private endpoint cannot be restored. A new one can be made and its connection approved again."),
}
# What a plan that names a kind that is not listed above says: a plan of a delete is made only for a listed kind, so this is for a record that an older or a damaged store holds.
UNLISTED = Wording(noun="resource", title="Delete a resource", verb="Delete the resource", state="not in use", observed="Azure shows the resource as not in use.",
                   risk="If something still uses the resource, that use stops.", undo="A deleted resource cannot be restored.")

# One step down, by the name of the type as Azure writes it (Learn, Disks - Update: sku.name is one of Standard_LRS, Premium_LRS, StandardSSD_LRS, UltraSSD_LRS, Premium_ZRS,
# StandardSSD_ZRS, PremiumV2_LRS). Only the five that a disk is moved between are known here: an Ultra Disk and a Premium SSD v2 are not converted in place.
KNOWN = {name.lower(): name for name in ("Standard_LRS", "StandardSSD_LRS", "Premium_LRS", "Premium_ZRS", "StandardSSD_ZRS")}
TIER_WORDS = {"standard_lrs": "Standard HDD", "standardssd_lrs": "Standard SSD", "premium_lrs": "Premium SSD", "premium_zrs": "Premium SSD (zone-redundant)",
              "standardssd_zrs": "Standard SSD (zone-redundant)"}


def tier_words(sku: object) -> str:
    """A tier as a person reads it, with the name that Azure uses after the words; "another tier" for a name that is not one of the five."""
    name = KNOWN.get(str(sku).lower(), "")
    return f"{TIER_WORDS[name.lower()]} ({name})" if name else "another tier"


def _place(group: str) -> str:
    return f" in group {group}" if group else ""


def _target(plan: PlanRecord | None) -> dict:
    return plan.target if plan is not None and isinstance(plan.target, dict) else {}


def deletes(default_type: str) -> Callable[[PlanRecord | None, str, str, str], Words]:
    """The words of a family that deletes. The kind of resource comes from the type in the plan's own preconditions, else from the type that the caller knows (the case's), and
    `default_type` stands in when neither says."""
    def words(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
        pre = plan.preconditions if plan is not None and isinstance(plan.preconditions, dict) else {}
        w = DELETE_WORDING.get(str(pre.get("resourceType", "")).lower()) or DELETE_WORDING.get((rtype or "").lower()) or DELETE_WORDING.get(default_type) or UNLISTED
        label = name or "this resource"
        return Words(
            headline=f"{w.verb} {label}{_place(group)}",
            change=f"Deletes the {w.noun} {label} in resource group {group or 'this group'}. Nothing else changes.",
            rechecked=(f"Right before it acts, Meternaut reads the {w.noun} again. It stops unless the {w.noun} is still {w.state}, still tagged as planted by "
                       "Meternaut, still in this resource group and not locked."),
            risk=w.risk, level=w.level, undo=w.brief_undo or w.undo, reversible=False)
    return words


def stop_vm(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    label = name or "this resource"
    return Words(
        headline=f"Stop (deallocate) the virtual machine {label}{_place(group)}",
        change=(f"Stops the virtual machine {label} in resource group {group or 'this group'} and releases its compute. Its disks and any public IP address stay and keep billing. "
                "Nothing else changes."),
        rechecked=("Right before it acts, Meternaut reads the machine again. It stops unless the machine is still running or stopped, still tagged as planted by Meternaut, still in this "
                   "resource group and not locked."),
        risk="Whatever runs on the machine stops. Only its compute is saved: its disks and any public IP address keep billing.", level="medium",
        undo="Start the machine again, in the Azure portal or with the Azure CLI. A dynamic address may be another one, and a start can fail when the region has no room for the size.",
        reversible=True)


def resize_vm(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    target = _target(plan)
    was, want = str(target.get("fromVmSize", "")), str(target.get("vmSize", ""))
    was, want = (was if SIZE_NAME.fullmatch(was) else "its size"), (want if SIZE_NAME.fullmatch(want) else "the new size")
    label = name or "this resource"
    return Words(
        headline=f"Resize the virtual machine {label} to {want}{_place(group)}",
        change=f"Changes the size of the virtual machine {label} in resource group {group or 'this group'} from {was} to {want}. A running machine restarts. Nothing else changes.",
        rechecked=("Right before it acts, Meternaut reads the machine again. It stops unless the machine is still of the same size, running, stopped or released, the new size is still one "
                   "that it can take, and it is still tagged as planted by Meternaut, still in this resource group and not locked."),
        risk="A running machine restarts, and a smaller size has fewer processors and less memory, so a workload that needs them slows down or fails.", level="medium",
        undo=f"Resize the machine back to {was} in the Azure portal or with the Azure CLI. That restarts a running machine again.", reversible=True)


def change_disk_tier(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    target = _target(plan)
    frm, to = tier_words(target.get("fromSkuName")), tier_words(target.get("skuName"))
    label = name or "this resource"
    return Words(
        headline=f"Move the disk {label} to {to}{_place(group)}",
        change=f"Changes the type of the disk {label} in resource group {group or 'this group'} from {frm} to {to}. Nothing else changes.",
        rechecked=("Right before it acts, Meternaut reads the disk again. It stops unless the disk is still the same tier, still unattached (or attached to a machine that is stopped and "
                   "released), still tagged as planted by Meternaut, still in this resource group and not locked."),
        risk="A lower tier has lower limits on operations and throughput, so a workload that needs them slows down.", level="medium",
        undo=f"Change the disk back to {frm} in the Azure portal or with the Azure CLI. It keeps its data. The type can be changed twice a day.", reversible=True)


@dataclass(frozen=True)
class Shown:
    """How one family shows itself to a person. `words` takes the plan (None for a case that has none yet), the type of the resource that the caller knows, the name and the group."""

    words: Callable[[PlanRecord | None, str, str, str], Words]
    called: str  # the change as a noun of a sentence: "The delete was refused or failed ..."
    resource_type: str = ""  # the type that a plan of the family changes when its own preconditions do not say
    saving_level: str = "Expected"  # Verified, Expected or Scenario: only used with a basis of the family's own
    saving_basis: str = ""  # what the figure is computed from, when it is not the cost lines of the last 30 days as they are (the brief says that for a family without one)
    no_figure: str = ""  # why a plan that has no figure claims none
    # The change ends the cost of the resource (a delete, a stop), so that cost lines which show none afterwards are the aim. A change that only lowers the cost (a resize, a change of tier)
    # leaves the resource billing: for it a missing cost line is a line that is not in yet, never "no cost", and a family has to say so to be read the other way.
    cost_ends: bool = False


SHOWN: dict[str, Shown] = {
    "delete-disk": Shown(deletes("microsoft.compute/disks"), "delete", "microsoft.compute/disks", cost_ends=True),
    "delete-public-ip": Shown(deletes("microsoft.network/publicipaddresses"), "delete", "microsoft.network/publicipaddresses", cost_ends=True),
    "stop-vm": Shown(
        stop_vm, "stop", "microsoft.compute/virtualmachines", cost_ends=True,
        saving_basis="the cost lines of the machine in the last 30 days (its disks and public IP addresses keep billing and are not counted)"),
    "resize-vm": Shown(
        resize_vm, "resize", "microsoft.compute/virtualmachines", saving_level="Scenario",
        saving_basis=("the cost lines of the last 30 days, scaled by the share of the machine's processors that is left in the same size series (the price list was not read, "
                      "so it is an estimate)")),
    "change-disk-tier": Shown(
        change_disk_tier, "change of tier", "microsoft.compute/disks",
        no_figure="The price of a disk depends on its size and its type, and Meternaut does not read the price list, so it claims no figure for this change."),
    "delete-idle-resource": Shown(deletes(""), "delete", cost_ends=True),
}


def shown(family: str | None) -> Shown | None:
    """How the family of this name shows itself, or None when it is not a family of change (`advise` is not: it changes nothing)."""
    return SHOWN.get(family or "")


def words_of(family: str | None, plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words | None:
    """The words of a plan of this family (or of a case that has none yet), or None for a name that is not a family of change."""
    found = shown(family)
    return found.words(plan, rtype, name, group) if found is not None else None


def called_of(family: str | None) -> str:
    """The change of a family as a noun of a sentence ("delete", "stop", "resize"); "change" for a name that is not a family of change."""
    found = shown(family)
    return found.called if found is not None else "change"


def type_of(family: str | None, preconditions: object) -> str:
    """The type of the resource that a plan of this family changes: the type that the plan's own preconditions hold when it is a type, else the family's own."""
    found = shown(family)
    if found is None:
        return ""
    wanted = str(preconditions.get("resourceType", "")).lower() if isinstance(preconditions, dict) else ""
    return wanted if RESOURCE_TYPE.fullmatch(wanted) else found.resource_type
