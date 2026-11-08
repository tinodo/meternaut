"""The families of a virtual machine: stop it (deallocate), and resize it.

Both change a machine that Meternaut planted itself, in its own resource group, with the approver's token. The calls are in calls.py: the deallocate of a machine (Learn, Virtual Machines -
Deallocate: a POST on the machine) and the update of a machine with the one property `hardwareProfile.vmSize` (Learn, Virtual Machines - Update: a PATCH), both api-version 2026-04-01, both
asynchronous (lro.py). What is read: the machine with its instance view (Virtual Machines - Get), the sizes that it can be resized to (List Available Sizes) and the regional quota (Usage - List).

What Azure documents and the plans say (Learn, "States and billing status of Azure Virtual Machines" and "Resize a virtual machine", read on 2026-11-08): a machine that is stopped from
inside, or is Stopped (allocated), is still billed for compute; only a deallocated one is not, and its disks and network resources keep billing. A resize restarts a running machine, and
may need the machine deallocated first when the new size is not on the hardware that hosts it. When a resize fails, the model of the machine still shows the size that was asked for, and
the machine keeps running at the old one: so a check of the size alone proves nothing, and the checks here ask for the provisioning state too.
"""
from __future__ import annotations

import re

from ..http import HttpError, Refused
from ..models import CaseRecord, PlanRecord
from ..roles import clean_text
from . import calls
from .base import Env, Family, Located, Planned, Stop, Unreadable, Verdict, evidence_text, per_day_check, skeptic_sentence
from .gates import Gates
from .machine import has_size_properties, power_of, provisioning_of, read_vm, region_of, size_of
from .words import SIZE_NAME

STOPPABLE = ("running", "stopped")
RESIZABLE = ("running", "stopped", "deallocated")
SIZE_PARTS = re.compile(r"Standard_([A-Za-z]{1,3})(\d{1,3})([A-Za-z0-9_]*)")
MAX_CORES = 4096
MAX_MEMORY_MB = 100_000_000
LAST_FAILED = "Azure shows that the last operation on the machine failed."
BEING_CHANGED = "something else is changing the machine right now"


def _machine_checks(resource: dict) -> None:
    """The checks that every change of a machine makes on what Azure shows: a machine that belongs to a scale set or is managed by a platform is not Meternaut's to change, and one that is
    being changed already is not changed a second time."""
    properties = resource.get("properties") if isinstance(resource.get("properties"), dict) else {}
    if resource.get("managedBy") or properties.get("virtualMachineScaleSet"):
        raise Stop("the machine is managed by a scale set or by a platform")
    state = provisioning_of(resource)
    if state != "succeeded":
        raise Stop(f"the last operation on the machine is not finished or did not work (its provisioning state is {clean_text(state, 20) or 'not shown'}): {BEING_CHANGED}")


def _preconditions(family: str, lead: object, gates: Gates, **more: object) -> dict:
    return {"family": family, "resourceType": getattr(lead, "resource_type"), "tag": gates.planted_tag, "resourceGroup": getattr(lead, "resource_group").lower(), **more}


class StopVm(Family):
    """Stops a machine and releases its compute (deallocate), so that it is no longer billed for compute."""

    name = "stop-vm"
    summary = "stop a virtual machine and release its compute (deallocate it)"
    does = "stop the machine"
    kinds = (calls.VIRTUAL_MACHINE,)
    recommendations = ("delete",)  # the machine is unused: the closest change that Meternaut makes to it is to stop it; it never deletes a machine
    detectors = ("stopped-vm",)
    reads_to_plan = True

    def facts(self, env: Env, lead: object, located: Located) -> dict:
        try:
            vm = read_vm(env, located)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        if vm is None:
            raise Unreadable("the machine does not exist any more")
        try:
            _machine_checks(vm)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        return {"power": power_of(vm), "size": size_of(vm), "location": region_of(vm)}

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned | str:
        power = facts.get("power", "")
        if power not in STOPPABLE:
            return f"the machine is not running or stopped ({clean_text(power, 20) or 'its power state is not shown'}), so there is nothing to stop"
        group = clean_text(getattr(lead, "resource_group"), 90)
        name = clean_text(getattr(lead, "name"), 120)
        size = facts.get("size") or "an unknown size"
        billed = "is billed for compute while it stands" if power == "running" else "is stopped but not released, which Azure still bills for compute"
        return Planned(
            title=f"Stop (deallocate) a virtual machine in resource group {group}",
            what_changes=(f"When you approve and sign in to Azure, Meternaut stops the virtual machine named {name} in resource group {group} (subscription {getattr(lead, 'subscription_id')[:8]}) and "
                          "releases its compute (it deallocates it) with your own permissions, so that it is no longer billed for compute. It changes nothing else: its disks and any public IP address "
                          "stay and keep billing. Right before it acts, it reads the machine again and stops unless it is still running or stopped, still tagged as planted by Meternaut, still in this "
                          "resource group and not locked."),
            could_go_wrong=("Whatever runs on the machine stops. Only its compute is saved: its disks, its network interface and any public IP address stay and keep billing. A dynamic address may "
                            f"change when the machine starts again. If your account may not stop the machine, Azure refuses and nothing changes. {skeptic_sentence(case)}"),
            undo=("Start the machine again, in the Azure portal or with the Azure CLI. It comes back with its disks and its size, and a dynamic address may be another one. A start can fail when the "
                  "region has no room for the size at that moment."),
            evidence=evidence_text(lead, f"the machine is {power} at size {size} and {billed}, as Azure shows it now (read by code)."),
            target={"endState": "deallocated"}, preconditions=_preconditions(self.name, lead, gates, power=list(STOPPABLE)),
            saving_usd_month=self.saving(case, lead, facts))

    def check_state(self, env: Env, plan: PlanRecord, located: Located, resource: dict) -> None:
        power = power_of(resource)
        if power in ("deallocated", "deallocating"):
            return  # the aim already: `already` says so
        _machine_checks(resource)
        if power not in STOPPABLE:
            raise Stop(f"the machine is not running or stopped any more (its power state is {clean_text(power, 20) or 'not shown'})")

    def already(self, plan: PlanRecord, resource: dict) -> str:
        if power_of(resource) in ("deallocated", "deallocating"):
            return "The machine was already stopped and released when Meternaut looked. Nothing to change."
        return ""

    def call(self) -> calls.Call:
        return calls.DEALLOCATE

    def write(self, env: Env, plan: PlanRecord, located: Located):
        return env.azure.write(self.call(), located.url(calls.DEALLOCATE.suffix))

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        located = self.locate(plan.resource_id, env.gates)
        try:
            vm = read_vm(env, located)
        except Stop:
            return Verdict("unknown", "The machine could not be read, so it is not known whether it is stopped.")
        if vm is None:
            return Verdict("unknown", "The machine could not be found, so it is not known whether it is stopped.")
        power = power_of(vm)
        evidence = {"power": power}
        if power == "deallocated":
            return Verdict("done", "Azure shows the machine as stopped and released (deallocated).", {**evidence, "now": "Stopped and released (deallocated)."})
        if provisioning_of(vm) == "failed":
            return Verdict("failed", LAST_FAILED, evidence)
        return Verdict("pending", "Azure does not show the machine as released yet.", evidence)


class ResizeVm(Family):
    """Changes the size of a machine to a smaller one of the same series. The size is chosen by code from the sizes that Azure lists for this machine; no model supplies it."""

    name = "resize-vm"
    summary = "resize a virtual machine to a smaller size of the same series"
    does = "change the size of the machine"
    kinds = (calls.VIRTUAL_MACHINE,)
    recommendations = ("change",)
    reads_to_plan = True

    def facts(self, env: Env, lead: object, located: Located) -> dict:
        try:
            vm = read_vm(env, located)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        if vm is None:
            raise Unreadable("the machine does not exist any more")
        try:
            _machine_checks(vm)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        if has_size_properties(vm):
            raise Unreadable("the machine has its own vCPU settings, so the numbers of a size do not say what it runs on")
        try:
            sizes = available_sizes(env, located)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        return {"power": power_of(vm), "size": size_of(vm), "location": region_of(vm), "sizes": sizes}

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned | str:
        power, current, sizes = facts.get("power", ""), facts.get("size", ""), facts.get("sizes", {})
        if power not in RESIZABLE:
            return f"the machine is not running, stopped or released ({clean_text(power, 20) or 'its power state is not shown'}), so it is not resized now"
        if current not in sizes:
            return "the size of the machine is not in the list of sizes that Azure gives for it, so there is nothing to compare with"
        target = smaller(current, sizes)
        if target is None:
            return f"no smaller size of the same series than {current} is listed for this machine"
        cores, memory = sizes[current]
        t_cores, t_memory = sizes[target]
        group = clean_text(getattr(lead, "resource_group"), 90)
        name = clean_text(getattr(lead, "name"), 120)
        saving = self.saving(case, lead, {"cores": cores, "targetCores": t_cores})
        restart = ("The machine is running, so it restarts to take the new size." if power == "running" else
                   "The machine is not running, so it does not restart now; the new size applies when it starts.")
        return Planned(
            title=f"Resize a virtual machine to {target} in resource group {group}",
            what_changes=(f"When you approve and sign in to Azure, Meternaut changes the size of the virtual machine named {name} in resource group {group} (subscription "
                          f"{getattr(lead, 'subscription_id')[:8]}) from {current} ({cores} vCPUs, {round(memory / 1024, 1):g} GB) to {target} ({t_cores} vCPUs, {round(t_memory / 1024, 1):g} GB) "
                          f"with your own permissions. {restart} It changes nothing else. Right before it acts, it reads the machine and the sizes that it can take again and stops unless it is "
                          f"still {current}, running, stopped or released, {target} is still one of the sizes that it can take, it is still tagged as planted by Meternaut, still in this resource "
                          "group and not locked."),
            could_go_wrong=("A running machine restarts, so whatever runs on it stops for a few minutes. A smaller size has fewer processors and less memory, so a workload that needs them slows "
                            "down or fails. The new size may not be on the hardware that hosts the machine: then Azure refuses, or the machine has to be released first. When a resize fails, Azure "
                            "may still show the new size while the machine keeps running at the old one. If your account may not change the machine, Azure refuses and nothing changes. "
                            f"{skeptic_sentence(case)}"),
            undo=(f"Resize the machine back to {current} in the Azure portal or with the Azure CLI. That restarts a running machine again, and {current} has to be available on its hardware then."),
            evidence=evidence_text(lead, f"the machine is {power} at size {current}, and Azure lists {target} among the sizes that it can take (read by code)."),
            target={"vmSize": target, "fromVmSize": current}, preconditions=_preconditions(self.name, lead, gates, power=list(RESIZABLE), location=facts.get("location", "")),
            saving_usd_month=saving)

    def saving(self, case: CaseRecord, lead: object, facts: dict) -> float | None:
        """The cost lines of the last 30 days of the machine, scaled by the share of its processors that is left. An estimate (the price list is not read), so a person reads it as Scenario."""
        cost, cores, target = case.cost_usd_30d, facts.get("cores"), facts.get("targetCores")
        if not cost or not cores or not target or target >= cores:
            return None
        return round(cost * (1 - target / cores), 2)

    def check_state(self, env: Env, plan: PlanRecord, located: Located, resource: dict) -> None:
        target = plan.target if isinstance(plan.target, dict) else {}
        want, was = str(target.get("vmSize", "")), str(target.get("fromVmSize", ""))
        if not SIZE_NAME.fullmatch(want) or not SIZE_NAME.fullmatch(was):
            raise Stop("the plan names a size that is not a size name")
        now = size_of(resource)
        if now == want and provisioning_of(resource) == "succeeded":
            return  # the aim already: `already` says so
        _machine_checks(resource)
        if now != was:
            raise Stop("the machine is not of the size that the plan was made for any more")
        power = power_of(resource)
        if power not in RESIZABLE:
            raise Stop(f"the machine is not running, stopped or released any more (its power state is {clean_text(power, 20) or 'not shown'})")
        if has_size_properties(resource):
            raise Stop("the machine has its own vCPU settings now")
        sizes = available_sizes(env, located)
        if want not in sizes or was not in sizes:
            raise Stop("the new size is not one of the sizes that this machine can take now")
        added = sizes[want][0] - sizes[was][0]
        if added > 0:
            self.quota(env, located, region_of(resource) or str((plan.preconditions or {}).get("location", "")), added)

    def quota(self, env: Env, located: Located, region: str, added: int) -> None:
        """A larger size needs room in the regional quota of vCPUs (Learn, Usage - List). The quota of the size's own family is not read here: Azure refuses at the change if that is short."""
        if not re.fullmatch(r"[a-z0-9]{3,40}", region or ""):
            raise Stop("the region of the machine is not known, so the quota cannot be read")
        try:
            usage = env.azure.get(calls.usage_url(located.scope.subscription, region)).json()
        except (HttpError, Refused) as error:
            if isinstance(error, HttpError) and error.status in (401, 403):
                raise Stop("Azure refused to read the quota (your account has no right to do this here). Nothing was changed.", "azure_refused") from error
            raise Stop("the quota could not be read") from error
        rows = usage.get("value") if isinstance(usage, dict) and isinstance(usage.get("value"), list) else []
        for row in rows:
            label = row.get("name") if isinstance(row, dict) else None
            if isinstance(label, dict) and label.get("value") == "cores":
                used, limit = row.get("currentValue"), row.get("limit")
                if isinstance(used, int) and isinstance(limit, int) and not isinstance(used, bool) and limit - used < added:
                    raise Stop(f"the region has no room in its quota of vCPUs for {added} more")
                return
        raise Stop("the quota of vCPUs of the region could not be read")

    def already(self, plan: PlanRecord, resource: dict) -> str:
        target = plan.target if isinstance(plan.target, dict) else {}
        if size_of(resource) == str(target.get("vmSize", "")) and provisioning_of(resource) == "succeeded":
            return f"The machine was already of size {target.get('vmSize')} when Meternaut looked. Nothing to change."
        return ""

    def call(self) -> calls.Call:
        return calls.write_for(calls.PATCH, calls.VIRTUAL_MACHINE)

    def write(self, env: Env, plan: PlanRecord, located: Located):
        want = str((plan.target or {}).get("vmSize", ""))
        if not SIZE_NAME.fullmatch(want):
            raise Stop("the plan names a size that is not a size name")
        return env.azure.write(self.call(), located.url(), {"properties": {"hardwareProfile": {"vmSize": want}}})

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        located = self.locate(plan.resource_id, env.gates)
        try:
            vm = read_vm(env, located)
        except Stop:
            return Verdict("unknown", "The machine could not be read, so it is not known which size it has.")
        if vm is None:
            return Verdict("unknown", "The machine could not be found, so it is not known which size it has.")
        want, state, now = str((plan.target or {}).get("vmSize", "")), provisioning_of(vm), size_of(vm)
        evidence = {"size": now, "provisioning": state}
        if state == "failed":
            return Verdict("failed", LAST_FAILED + " The size that Azure shows is the one that was asked for, and the machine may keep running at the old one.", evidence)
        if now == want and state == "succeeded":
            return Verdict("done", f"Azure shows the machine at size {now}, and its last operation worked.", {**evidence, "now": f"Size {now}."})
        return Verdict("pending", "Azure does not show the new size as made yet.", evidence)

    def cost_check(self, before_30d, after_total, days_after):
        return per_day_check(before_30d, after_total, days_after, "the machine")


def available_sizes(env: Env, located: Located) -> dict[str, tuple[int, int]]:
    """The sizes that Azure says the machine can be resized to, as name -> (cores, memory in MB). A row that does not fit the shape is left out. Raises Stop when the list cannot be read."""
    data = None
    try:
        data = env.azure.get(located.url("/vmSizes")).json()
    except HttpError as error:
        if error.status in (401, 403):
            raise Stop("Azure refused to read the sizes of the machine (your account has no right to do this here). Nothing was changed.", "azure_refused") from error
        raise Stop(f"the sizes that the machine can take could not be read ({error.status or 'no answer'})") from error
    except Refused as error:
        raise Stop("the app may not read the sizes of the machine") from error
    rows = data.get("value") if isinstance(data, dict) and isinstance(data.get("value"), list) else None
    if rows is None:
        raise Stop("the sizes that the machine can take could not be read")
    sizes: dict[str, tuple[int, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, cores, memory = row.get("name"), row.get("numberOfCores"), row.get("memoryInMB")
        if (isinstance(name, str) and SIZE_NAME.fullmatch(name) and isinstance(cores, int) and not isinstance(cores, bool) and 0 < cores <= MAX_CORES
                and isinstance(memory, int) and not isinstance(memory, bool) and 0 < memory <= MAX_MEMORY_MB):
            sizes[name] = (cores, memory)
    return sizes


def series_of(size: str) -> tuple[str, str] | None:
    """The family letters and what follows the number of a size name, in lower case: Standard_D4s_v5 is ("d", "s_v5"). None for a name of another shape."""
    found = SIZE_PARTS.fullmatch(size or "")
    return (found.group(1).lower(), found.group(3).lower()) if found else None


def smaller(current: str, sizes: dict[str, tuple[int, int]]) -> str | None:
    """The smallest step down: of the sizes of the same series that have fewer processors (or as many and less memory), the one with the most processors, then the most memory. None when there is none."""
    series, here = series_of(current), sizes.get(current)
    if series is None or here is None:
        return None
    options = [(cores, memory, name) for name, (cores, memory) in sizes.items()
               if name != current and series_of(name) == series and (cores < here[0] or (cores == here[0] and memory < here[1]))]
    return max(options)[2] if options else None
