"""A virtual machine as the families of a machine read it: where it is, how it is powered, its size and the state of its last operation.

Every value is taken from Azure's answer and checked against a pattern before code uses it: a word of the power state, the name of a size, a region. A value that does not fit is empty, and
an empty value is never one that a plan or a check treats as good.
"""
from __future__ import annotations

import re

from . import calls
from .base import Env, Located, locate, read_resource
from .gates import Gates
from .words import SIZE_NAME

REGION = re.compile(r"[a-z0-9]{3,40}")
POWER = re.compile(r"[a-z]{3,20}")
# Learn, "States and billing status of Azure Virtual Machines": a machine that is Running, Starting, Stopping or Stopped (allocated) is billed for compute; one that is Deallocating or
# Deallocated is not, and its disks and network resources keep billing.
BILLED = ("running", "starting", "stopping", "stopped")


def locate_machine(gates: Gates, resource_id: str) -> Located:
    """The machine of an id, in a scope. Raises Stop when the id is not a virtual machine in a resource group of Meternaut's own."""
    return locate(resource_id, gates, (calls.VIRTUAL_MACHINE,))


def read_vm(env: Env, located: Located) -> dict | None:
    """The machine with its instance view (Learn, Virtual Machines - Get, `$expand=instanceView`): its power state is in the instance view's statuses."""
    return read_resource(env, located, query="$expand=instanceView")


def _properties(vm: dict) -> dict:
    return vm.get("properties") if isinstance(vm.get("properties"), dict) else {}


def power_of(vm: dict) -> str:
    """The power state as one lower-case word (running, stopped, deallocated, deallocating, starting, stopping ...), or an empty text when the instance view shows none."""
    view = _properties(vm).get("instanceView")
    statuses = view.get("statuses") if isinstance(view, dict) and isinstance(view.get("statuses"), list) else []
    for status in statuses:
        code = status.get("code") if isinstance(status, dict) else None
        if isinstance(code, str) and code.startswith("PowerState/"):
            word = code.split("/", 1)[1].lower()
            return word if POWER.fullmatch(word) else ""
    return ""


def provisioning_of(vm: dict) -> str:
    """The provisioning state of the last operation, in lower case: succeeded, updating, failed, creating, deleting ...; empty when none is shown."""
    state = _properties(vm).get("provisioningState")
    return state.strip().lower()[:30] if isinstance(state, str) else ""


def size_of(vm: dict) -> str:
    """The size that the model of the machine asks for (hardwareProfile.vmSize). It shows the size that was asked for last, even when that resize did not take effect: Learn, "Resize a
    virtual machine"."""
    profile = _properties(vm).get("hardwareProfile")
    size = profile.get("vmSize") if isinstance(profile, dict) else None
    return size if isinstance(size, str) and SIZE_NAME.fullmatch(size) else ""


def has_size_properties(vm: dict) -> bool:
    """Whether the machine has constrained vCPU settings (hardwareProfile.vmSizeProperties): a resize of it is not planned, because the sizes' numbers no longer say what it runs on."""
    profile = _properties(vm).get("hardwareProfile")
    return isinstance(profile, dict) and bool(profile.get("vmSizeProperties"))


def region_of(vm: dict) -> str:
    place = vm.get("location")
    return place.strip().lower() if isinstance(place, str) and REGION.fullmatch(place.strip().lower()) else ""
