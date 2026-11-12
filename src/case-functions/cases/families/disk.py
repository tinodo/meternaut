"""The families of a managed disk: delete an unattached one, and change the tier of one.

`delete-disk` is the first family and behaves as it did when it was written in runner.py and approvals.py. `change-disk-tier` moves a disk one step down the tiers of Azure managed disks
(Premium SSD to Standard SSD, Standard SSD to Standard HDD, and the zone-redundant Premium SSD to the zone-redundant Standard SSD), which Azure documents as a change that needs no new
disk: Learn, "Convert managed disks storage between different disk types" (read on 2026-11-08): the disk has to be unattached, or its machine stopped and released; the type can be changed
twice a day; Standard HDD has no zone-redundant form; a disk of an Ultra or Premium SSD v2 type is not changed.
"""
from __future__ import annotations

import re

from ..models import CaseRecord, PlanRecord
from ..roles import clean_text
from . import calls
from .base import Env, Family, Located, Planned, Stop, Unreadable, Verdict, evidence_text, per_day_check, skeptic_sentence
from .delete import DeleteFamily
from .gates import Gates
from .machine import locate_machine, power_of, read_vm
from .words import KNOWN, tier_words

SKU_NAME = re.compile(r"[A-Za-z0-9_]{1,40}")
# One step down, by the name of the type as Azure writes it (Learn, Disks - Update: sku.name is one of Standard_LRS, Premium_LRS, StandardSSD_LRS, UltraSSD_LRS, Premium_ZRS,
# StandardSSD_ZRS, PremiumV2_LRS). Nothing else is moved: an Ultra Disk and a Premium SSD v2 are not converted in place.
STEPS = {"premium_lrs": "StandardSSD_LRS", "standardssd_lrs": "Standard_LRS", "premium_zrs": "StandardSSD_ZRS"}
# Learn, "Select a disk type for Azure IaaS VMs" (read on 2026-11-08): a managed disk is billed at the nearest offered size above the provisioned one, and the smallest Standard HDD offer
# (S4) is 32 GiB, while a Standard SSD is offered from 4 GiB (E1, E2 and E3 are 4, 8 and 16 GiB). So a Standard SSD of up to 16 GiB would be billed at 32 GiB on a Standard HDD, which costs
# more. A move to Standard HDD is planned for a larger disk only.
HDD_COSTS_LESS_ABOVE_GIB = 16


def sku_of(disk: dict) -> str:
    sku = disk.get("sku")
    name = sku.get("name") if isinstance(sku, dict) else None
    return KNOWN.get(str(name).lower(), "") if isinstance(name, str) and SKU_NAME.fullmatch(name) else ""


def size_gb_of(disk: dict) -> int | None:
    properties = disk.get("properties") if isinstance(disk.get("properties"), dict) else {}
    size = properties.get("diskSizeGB")
    return size if isinstance(size, int) and not isinstance(size, bool) and 1 <= size <= 65536 else None


def aim_of(plan: PlanRecord) -> tuple[str, str]:
    """The tier a plan moves a disk from and to. It has to be exactly one step of the table, spelled as Azure spells it; any other plan is refused before it is used in a call."""
    target = plan.target if isinstance(plan.target, dict) else {}
    frm, to = target.get("fromSkuName"), target.get("skuName")
    if not isinstance(frm, str) or not isinstance(to, str) or KNOWN.get(frm.lower()) != frm or STEPS.get(frm.lower()) != to:
        raise Stop("the plan names a tier change that Meternaut does not make")
    return frm, to


class DeleteDisk(DeleteFamily):
    name = "delete-disk"
    summary = "delete an unattached managed disk"
    kinds = (calls.DISK,)
    recommendations = ("delete",)
    detectors = ("orphan-managed-disk",)

    def why_not_idle(self, located, resource: dict) -> str | None:
        properties = resource.get("properties") if isinstance(resource.get("properties"), dict) else {}
        if str(properties.get("diskState", "")).lower() != "unattached" or resource.get("managedBy"):
            return "the disk is not unattached any more"
        return None


class ChangeDiskTier(Family):
    """Moves a disk one tier down. The target is chosen by code from the table above; no model supplies it."""

    name = "change-disk-tier"
    summary = "move a managed disk one tier down (Premium SSD to Standard SSD, Standard SSD to Standard HDD)"
    does = "change the type of the disk"
    kinds = (calls.DISK_TIER,)
    recommendations = ("change",)
    reads_to_plan = True
    verb = "Move the disk"

    def facts(self, env: Env, lead: object, located: Located) -> dict:
        try:
            disk = self.read(env, located)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        if disk is None:
            raise Unreadable("the disk does not exist any more")
        sku = sku_of(disk)
        if not sku:
            raise Unreadable("the disk is not of a tier that Meternaut moves")
        try:
            attached = self.attachment_of(env, disk)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        return {"sku": sku, "attached": attached, "sizeGb": size_gb_of(disk)}

    def attachment_of(self, env: Env, disk: dict) -> str:
        """`unattached`, or `stopped` when the disk is attached to a machine of Meternaut's own that is stopped and released. Raises Stop for anything else: Azure documents that a disk has to be
        unattached, or its machine stopped and released, before its type is changed (Learn, "Convert managed disks storage between different disk types")."""
        properties = disk.get("properties") if isinstance(disk.get("properties"), dict) else {}
        owner = str(disk.get("managedBy") or "")
        state = str(properties.get("diskState", "")).lower()
        if not owner:
            if state != "unattached":
                raise Stop(f"the disk is not unattached (Azure shows it as {clean_text(state, 30) or 'in an unknown state'})")
            return "unattached"
        machine = locate_machine(env.gates, owner)  # a machine that is not in one of Meternaut's own groups is not one that Meternaut may touch through its disk either
        vm = read_vm(env, machine)
        if vm is None:
            raise Stop("the machine that the disk is attached to cannot be found")
        tags = vm.get("tags") if isinstance(vm.get("tags"), dict) else {}
        if env.gates.why_not_planted(tags, calls.VIRTUAL_MACHINE.type, machine.name) is not None:
            raise Stop("the disk is attached to a machine that Meternaut did not plant")
        if power_of(vm) != "deallocated":
            raise Stop("the disk is attached to a machine that is not stopped and released")
        return "stopped"

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned | str:
        frm = facts.get("sku", "")
        to = STEPS.get(frm.lower())
        if not to:
            return f"there is no lower tier to move this disk to ({tier_words(frm)})"
        size = facts.get("sizeGb")
        if to == "Standard_LRS" and (not isinstance(size, int) or size <= HDD_COSTS_LESS_ABOVE_GIB):
            return ("a Standard HDD is billed from 32 GiB up, so a Standard SSD of "
                    f"{f'{size} GiB' if isinstance(size, int) else 'a size that Azure does not show'} would cost more there, not less")
        group = clean_text(getattr(lead, "resource_group"), 90)
        name = clean_text(getattr(lead, "name"), 120)
        wait = ("The disk is not attached to anything, so nothing stops while it changes." if facts.get("attached") == "unattached"
                else "The disk is attached to a machine that is stopped and released, so nothing runs while it changes.")
        return Planned(
            title=f"Move a managed disk to {tier_words(to)} in resource group {group}",
            what_changes=(f"When you approve, Meternaut changes the type of the disk named {name} in resource group {group} "
                          f"(subscription {getattr(lead, 'subscription_id')[:8]}) from {tier_words(frm)} to {tier_words(to)}, with your own permissions. It changes nothing else: not the data and not the size. "
                          f"{wait} Right before it acts, it reads the disk again and stops unless it is still {tier_words(frm)} and still in that state, still tagged as planted by Meternaut, "
                          "still in this resource group and not locked."),
            could_go_wrong=("A disk of a lower tier has lower limits on operations and throughput, so a workload that needs them slows down. Azure allows the type of a disk to be changed twice a day. "
                            f"If your account may not change the disk, Azure refuses and nothing changes. {skeptic_sentence(case)}"),
            undo=(f"Change the disk back to {tier_words(frm)} in the Azure portal or with the Azure CLI. It keeps its data; the type can be changed twice a day, and a disk that is attached "
                  "to a machine needs the machine stopped and released first."),
            evidence=evidence_text(lead, f"the disk is a {tier_words(frm)} and is {facts.get('attached')}, as Azure shows it now (read by code)."),
            target={"skuName": to, "fromSkuName": frm},
            preconditions={"family": self.name, "resourceType": getattr(lead, "resource_type"), "tag": gates.planted_tag, "resourceGroup": getattr(lead, "resource_group").lower()},
            saving_usd_month=None)

    def saving(self, case: CaseRecord, lead: object, facts: dict) -> float | None:
        return None

    def check_state(self, env: Env, plan: PlanRecord, located: Located, resource: dict) -> None:
        frm, to = aim_of(plan)
        now = sku_of(resource)
        if now not in (frm, to):
            raise Stop("the disk is not of the tier that the plan was made for any more")
        if now == to:
            return  # it is the aim already: `already` says so
        self.attachment_of(env, resource)

    def already(self, plan: PlanRecord, resource: dict) -> str:
        try:
            _, to = aim_of(plan)
        except Stop:
            return ""
        if sku_of(resource) == to:
            return f"The disk was already a {tier_words(to)} when Meternaut looked. Nothing to change."
        return ""

    def call(self) -> calls.Call:
        return calls.write_for(calls.PATCH, calls.DISK_TIER)

    def write(self, env: Env, plan: PlanRecord, located: Located):
        _, to = aim_of(plan)
        return env.azure.write(self.call(), located.url(), {"sku": {"name": to}})

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        located = self.locate(plan.resource_id, env.gates)
        try:
            disk = self.read(env, located)
        except Stop:
            return Verdict("unknown", "The disk could not be read, so it is not known which tier it has.")
        if disk is None:
            return Verdict("unknown", "The disk could not be found, so it is not known which tier it has.")
        try:
            _, target = aim_of(plan)
        except Stop:
            return Verdict("unknown", "The plan does not name a tier change that Meternaut makes, so the disk is not judged against it.")
        now = sku_of(disk)
        properties = disk.get("properties") if isinstance(disk.get("properties"), dict) else {}
        provisioning = str(properties.get("provisioningState", "")).lower()
        evidence = {"sku": now}
        if provisioning == "failed":
            return Verdict("failed", "Azure shows that the last operation on the disk failed.", evidence)
        if now == target and provisioning in ("", "succeeded"):
            return Verdict("done", f"Azure shows the disk as a {tier_words(now)}.", {**evidence, "now": f"{tier_words(now)}"})
        return Verdict("pending", "Azure does not show the new tier yet.", evidence)

    def cost_check(self, before_30d, after_total, days_after):
        return per_day_check(before_30d, after_total, days_after, "the disk")
